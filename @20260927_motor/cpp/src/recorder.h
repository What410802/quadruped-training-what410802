// 录像：无窗口（隐藏窗口 + 离屏 framebuffer）渲染 → 每帧喂给 ffmpeg 管道。
//
// 做法与 @20260923_mujoco/cpp_task2/src/record.h 一致（那边踩过的坑都带上）：
//   1. 离屏 framebuffer 的大小是模型里的 <visual><global offwidth/offheight>，**不是**窗口尺寸，
//      而且必须在 mjr_makeContext **之前**改，所以构造时就把它设成 --width/--height（原生分辨率）；
//   2. 出帧时刻钉在严格网格 k/fps（帧数 ≈ 时长×fps），MP4 的时间轴 = 仿真时间，与机器快慢无关；
//   3. mjr_readPixels 的行序自下而上，交给 ffmpeg 的 -vf vflip 翻；
//   4. 不要在 Linux 上调 glfwTerminate()（本机驱动会崩），只销毁窗口；
//   5. HUD 一律 ASCII（内置位图字体没有 CJK 字形，见 viewer.h 的说明）。
//
// header-only，直接 #include "recorder.h"。
#pragma once

#include <mujoco/mujoco.h>

#include <GLFW/glfw3.h>

#include <cstdio>
#include <filesystem>
#include <string>
#include <vector>

class FrameRecorder {
  public:
    FrameRecorder(mjModel *m, const std::string &path, int width, int height, double fps)
        : path_(std::filesystem::absolute(path).lexically_normal().string()), fps_(fps),
          out_width_(width), out_height_(height) {
        m->vis.global.offwidth = width; // 必须在 mjr_makeContext 之前（离屏 buffer 那时才分配）
        m->vis.global.offheight = height;
        if (!glfwInit())
            mju_error("glfwInit 失败");
        glfwWindowHint(GLFW_VISIBLE, 0);
        glfwWindowHint(GLFW_DOUBLEBUFFER, GLFW_FALSE);
        window_ = glfwCreateWindow(width, height, "offscreen", nullptr, nullptr);
        if (window_ == nullptr)
            mju_error("创建隐藏窗口失败（有显示服务/EGL 吗？）");
        glfwMakeContextCurrent(window_);

        mjv_defaultCamera(&cam_);
        mjv_defaultOption(&opt_);
        mjv_defaultScene(&scn_);
        mjr_defaultContext(&con_);
        mjv_makeScene(m, &scn_, 2000);
        mjr_makeContext(m, &con_, mjFONTSCALE_150);
        mjr_setBuffer(mjFB_OFFSCREEN, &con_);
        viewport_ = mjr_maxViewport(&con_); // 实际视口（正常就等于请求尺寸）

        // 万一驱动把视口夹小了，就再 scale 回输出尺寸，否则帧对不齐
        char scale[64] = "";
        if (viewport_.width != width || viewport_.height != height)
            std::snprintf(scale, sizeof(scale), ",scale=%d:%d", width, height);
        char cmd[1024];
        std::snprintf(cmd, sizeof(cmd),
                      "ffmpeg -y -loglevel error -f rawvideo -pix_fmt rgb24 -s %dx%d -r %g -i -"
                      " -vf vflip%s -c:v libx264 -pix_fmt yuv420p -crf 18 \"%s\"",
                      viewport_.width, viewport_.height, fps, scale, path_.c_str());
        pipe_ = ::popen(cmd, "w");
        if (pipe_ == nullptr)
            mju_error("打不开 ffmpeg 管道（PATH 里有 ffmpeg 吗？）");

        rgb_.resize(static_cast<size_t>(3) * viewport_.width * viewport_.height);

        cam_.type = mjCAMERA_FREE; // 与窗口/截图同一个视角，便于对照
        cam_.azimuth = 135.0;
        cam_.elevation = -20.0;
        cam_.distance = 2.0;
        cam_.lookat[0] = 0.0;
        cam_.lookat[1] = 0.0;
        cam_.lookat[2] = 0.15;
    }

    ~FrameRecorder() { Close(); }
    FrameRecorder(const FrameRecorder &) = delete;
    FrameRecorder &operator=(const FrameRecorder &) = delete;

    // 到点就出一帧（HUD 用 ASCII）。返回值表示这一帧有没有出。
    bool Capture(const mjModel *m, mjData *d, const char *hud_left, const char *hud_right) {
        if (have_frame_ && d->time < next_time_ - 1e-12)
            return false;
        mjv_updateScene(m, d, &opt_, nullptr, &cam_, mjCAT_ALL, &scn_);
        mjr_render(viewport_, &scn_, &con_);
        mjr_overlay(mjFONT_NORMAL, mjGRID_TOPLEFT, viewport_, hud_left, nullptr, &con_);
        mjr_overlay(mjFONT_NORMAL, mjGRID_TOPRIGHT, viewport_, hud_right, nullptr, &con_);
        mjr_readPixels(rgb_.data(), nullptr, viewport_, &con_);
        std::fwrite(rgb_.data(), 3, rgb_.size() / 3, pipe_);
        have_frame_ = true;
        ++frames_;
        next_time_ = frames_ / fps_; // 严格网格，不累加，避免浮点漂移
        if (next_time_ <= d->time)   // 落后了（fps > 1/dt）就跳到网格前方
            next_time_ = d->time + 1.0 / fps_;
        return true;
    }

    void Close() {
        if (pipe_ != nullptr) {
            ::pclose(pipe_); // 等 ffmpeg 写完 moov
            pipe_ = nullptr;
        }
        if (window_ != nullptr) {
            mjr_freeContext(&con_);
            mjv_freeScene(&scn_);
            glfwDestroyWindow(window_);
            window_ = nullptr;
            // 不调 glfwTerminate()：见文件头
        }
    }

    int frames() const { return frames_; }
    const std::string &path() const { return path_; }
    int viewport_width() const { return viewport_.width; }
    int viewport_height() const { return viewport_.height; }
    bool scaled() const {
        return viewport_.width != out_width_ || viewport_.height != out_height_;
    }

  private:
    std::string path_;
    double fps_ = 50.0;
    int out_width_ = 0, out_height_ = 0;
    GLFWwindow *window_ = nullptr;
    std::FILE *pipe_ = nullptr;
    mjvCamera cam_;
    mjvOption opt_;
    mjvScene scn_;
    mjrContext con_;
    mjrRect viewport_{};
    std::vector<unsigned char> rgb_;
    double next_time_ = 0.0;
    bool have_frame_ = false;
    int frames_ = 0;
};
