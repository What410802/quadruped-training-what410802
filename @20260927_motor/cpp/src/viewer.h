// 自己写的窗口：任务要求用**键盘**在两个状态之间切换，而官方 `Simulate` 界面（`mj::GlfwAdapter`）
// 的按键是它自己的 UI（暂停/单步/相机…），不能挂自定义回调——所以这个任务自己开窗口：
// 渲染用 mjv/mjr（与 record.h 同一套调用），输入用 GLFW 回调，鼠标用 mjv_moveCamera。
//
// 调用惯例照官方 sample/basic.cc：像素位移要除以窗口高度（y 方向取负，因为 GLFW 的 y 向下），
// 滚轮 = 5% 窗口高度；按键回调把键丢进队列，主循环每帧取一次（边沿触发，不重复触发）。
//
// 收尾照 @20260923_mujoco 的结论：**不要调 glfwTerminate()**（本机驱动上会崩），只销毁窗口，
// 进程退出时由系统回收。
#pragma once

#include <mujoco/mujoco.h>

#include <GLFW/glfw3.h>

#include <cstdio>
#include <vector>

namespace viewer {

class Window {
  public:
    Window(const mjModel *m, const char *title, int width, int height) : m_(m), width_(width), height_(height) {
        if (!glfwInit())
            mju_error("glfwInit 失败");
        glfwWindowHint(GLFW_VISIBLE, 1);
        glfwWindowHint(GLFW_DOUBLEBUFFER, 1);
        win_ = glfwCreateWindow(width, height, title, nullptr, nullptr);
        if (win_ == nullptr)
            mju_error("创建窗口失败（有显示服务吗？只要数字请用 --mode sim）");
        glfwMakeContextCurrent(win_);
        glfwSwapInterval(1); // 垂直同步：窗口里跑，省得空转烧 CPU
        glfwSetWindowUserPointer(win_, this);
        glfwSetKeyCallback(win_, OnKey);
        glfwSetMouseButtonCallback(win_, OnMouseButton);
        glfwSetCursorPosCallback(win_, OnCursorPos);
        glfwSetScrollCallback(win_, OnScroll);

        mjv_defaultCamera(&cam_);
        mjv_defaultOption(&opt_);
        mjv_defaultScene(&scn_);
        mjr_defaultContext(&con_);
        mjv_makeScene(m, &scn_, 2000);
        mjr_makeContext(m, &con_, mjFONTSCALE_150);
        mjr_setBuffer(mjFB_WINDOW, &con_); // 我们是画到窗口上（不是离屏）
        viewport_ = mjr_maxViewport(&con_);

        // 与 Python 侧 render_preview.py 的 iso 视角一致，便于和截图对照
        cam_.type = mjCAMERA_FREE;
        cam_.azimuth = 135.0;
        cam_.elevation = -20.0;
        cam_.distance = 2.0;
        cam_.lookat[0] = 0.0;
        cam_.lookat[1] = 0.0;
        cam_.lookat[2] = 0.15;
        std::printf("窗口：%dx%d（视口 %dx%d）；S = 站立模式、D = 阻尼模式、R = 回到起点、Q/Esc = 退出；"
                    "鼠标左键转、右键平移、滚轮缩放\n",
                    width_, height_, viewport_.width, viewport_.height);
    }

    ~Window() {
        if (win_ != nullptr) {
            mjr_freeContext(&con_);
            mjv_freeScene(&scn_);
            glfwDestroyWindow(win_);
            // 不调 glfwTerminate()：见文件头
        }
    }

    Window(const Window &) = delete;
    Window &operator=(const Window &) = delete;

    // 取一次事件；返回 false = 该退出了
    bool Poll() {
        glfwPollEvents();
        return win_ != nullptr && glfwWindowShouldClose(win_) == 0;
    }

    // 取一个"本帧按下"的键（没有则返回 false）
    bool TakeKey(int *key) {
        if (keys_.empty())
            return false;
        *key = keys_.front();
        keys_.erase(keys_.begin());
        return true;
    }

    void Draw(const mjModel *m, mjData *d, const char *hud_left, const char *hud_right) {
        // 视口每帧按**实际 framebuffer** 重取。只在构造时取一次的话，窗口被缩放/最大化之后
        // 画面会固定留在左下角一小块（Wayland 下尤其明显：窗口尺寸随时会被 compositor 改）。
        // 官方 GlfwAdapter 也是这么做的：渲染用 GetFramebufferSize()，鼠标位移也用它归一化。
        int fb_w = 0, fb_h = 0;
        glfwGetFramebufferSize(win_, &fb_w, &fb_h);
        if (fb_w <= 0 || fb_h <= 0)
            return; // 最小化时是 0×0，别画（也别除零）
        viewport_ = {0, 0, fb_w, fb_h};
        if (fb_w != last_fb_w_ || fb_h != last_fb_h_) { // 尺寸/缩放变了就报一声，便于排查
            int win_w = 0, win_h = 0;
            float sc_x = 1.0f, sc_y = 1.0f;
            glfwGetWindowSize(win_, &win_w, &win_h);
            glfwGetWindowContentScale(win_, &sc_x, &sc_y);
            std::printf("窗口：window %dx%d、framebuffer %dx%d（缩放 %.2fx）\n", win_w, win_h,
                        fb_w, fb_h, sc_x);
            last_fb_w_ = fb_w;
            last_fb_h_ = fb_h;
        }
        mjv_updateScene(m, d, &opt_, nullptr, &cam_, mjCAT_ALL, &scn_);
        mjr_render(viewport_, &scn_, &con_);
        // 内置字体只覆盖 ASCII：HUD 里混进非 ASCII 字节（中文/希腊字母/·/°）会被画成实心块 ——
        // 实测每字节的“墨迹”像素：ASCII 33~42，中文 95~122（就是那种“加粗乱码”）。
        // 这里挡一道（只报一次），免得以后改 HUD 又踩回去。
        if (!ascii_warned_ && (!IsAscii(hud_left) || !IsAscii(hud_right))) {
            std::printf("警告：HUD 里有非 ASCII 字符，MuJoCo 内置字体画不出来（会变成实心块）。\n"
                        "      HUD 一律用 ASCII，中文留给终端日志。\n");
            ascii_warned_ = true;
        }
        mjr_overlay(mjFONT_NORMAL, mjGRID_TOPLEFT, viewport_, hud_left, nullptr, &con_);
        mjr_overlay(mjFONT_NORMAL, mjGRID_TOPRIGHT, viewport_, hud_right, nullptr, &con_);
        glfwSwapBuffers(win_);
    }

    // 当前**窗口（逻辑）高度**：鼠标位移按它归一化。
    // 官方 platform_ui_adapter.cc:233-234 是“先把光标位移乘 buffer/window 比例换成 framebuffer 像素”，
    // 再 simulate.cc:2096 除以 rect[3].height（也是 framebuffer 高度）——两个比例相消，
    // 等价于“直接除以窗口高度”。这样转动角度与缩放比例无关，和官方一致。
    int window_height() const {
        int w = 0, h = 0;
        glfwGetWindowSize(win_, &w, &h);
        if (h > 0)
            return h;
        return viewport_.height > 0 ? viewport_.height : height_;
    }

  private:
    static Window *Self(GLFWwindow *w) { return static_cast<Window *>(glfwGetWindowUserPointer(w)); }

    static bool IsAscii(const char *text) {
        for (const unsigned char *p = reinterpret_cast<const unsigned char *>(text); *p != '\0'; ++p)
            if (*p >= 0x80)
                return false;
        return true;
    }

    static void OnKey(GLFWwindow *w, int key, int /*scancode*/, int action, int /*mods*/) {
        if (action == GLFW_PRESS || action == GLFW_REPEAT)
            Self(w)->keys_.push_back(key);
    }

    static void OnMouseButton(GLFWwindow *w, int button, int action, int mods) {
        Window *s = Self(w);
        s->dragging_ = (action == GLFW_PRESS);
        s->button_ = button;
        s->shift_ = (mods & GLFW_MOD_SHIFT) != 0;
        glfwGetCursorPos(w, &s->last_x_, &s->last_y_);
    }

    static void OnCursorPos(GLFWwindow *w, double x, double y) {
        Window *s = Self(w);
        if (!s->dragging_)
            return;
        // 归一化：除以**窗口（逻辑）高度**——等价于官方的“先乘 buffer/window 比例、再除以
        // framebuffer 高度”（platform_ui_adapter.cc:233-241 与 simulate.cc:2096），
        // 好处是转动灵敏度与缩放比例无关。
        // 方向：官方先把 y 翻成 y-up 再算 dy，然后 simulate.cc:2096 又传 -dy —— 两次取负抵消，
        // 等于"GLFW 的 y-down 位移直接传正值"，与 sample/basic.cc:92（不取负）一致。
        const double h = static_cast<double>(s->window_height());
        const double dx = (x - s->last_x_) / h;
        const double dy = (y - s->last_y_) / h; // 注意：**不要**取负
        s->last_x_ = x;
        s->last_y_ = y;
        int action;
        if (s->button_ == GLFW_MOUSE_BUTTON_RIGHT)
            action = s->shift_ ? mjMOUSE_MOVE_H : mjMOUSE_MOVE_V;
        else if (s->button_ == GLFW_MOUSE_BUTTON_MIDDLE)
            action = mjMOUSE_ZOOM;
        else
            action = s->shift_ ? mjMOUSE_ROTATE_H : mjMOUSE_ROTATE_V;
        mjv_moveCamera(s->m_, action, dx, dy, &s->cam_);
    }

    static void OnScroll(GLFWwindow *w, double /*xoffset*/, double yoffset) {
        Window *s = Self(w);
        mjv_moveCamera(s->m_, mjMOUSE_ZOOM, 0.0, -0.05 * yoffset, &s->cam_); // 5% 窗口高度
    }

    const mjModel *m_ = nullptr;
    GLFWwindow *win_ = nullptr;
    int width_ = 0, height_ = 0;
    mjvCamera cam_;
    mjvOption opt_;
    mjvScene scn_;
    mjrContext con_;
    mjrRect viewport_{};
    std::vector<int> keys_;
    bool dragging_ = false;
    bool shift_ = false;
    bool ascii_warned_ = false;
    int button_ = GLFW_MOUSE_BUTTON_LEFT;
    int last_fb_w_ = 0, last_fb_h_ = 0;
    double last_x_ = 0.0, last_y_ = 0.0;
};

} // namespace viewer
