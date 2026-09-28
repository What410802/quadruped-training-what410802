// 核心版：把本次任务（第一部分·仿真）的控制程序压到最小 —— 两个状态、一条 MIT 公式、一个站姿。
//
// 与 [`../essential/`](../essential/README.md) 的差别（少了量测与遥测、命令行、站姿文件、自适应斜坡、
// 电机统计）、位置参数的含义与默认值、以及实测数据，都写在 [`README.md`](../README.md) 里，这里不重复。
//
// 用法：
//   pixi run cmake -S @20260927_motor/cpp/essential_core -B @20260927_motor/cpp/essential_core/build -G Ninja -DCMAKE_PREFIX_PATH="$CONDA_PREFIX"
//   pixi run cmake --build @20260927_motor/cpp/essential_core/build
//   pixi run @20260927_motor/cpp/essential_core/build/essential_core
//
// 位置参数（都可省；写 "/" 表示"这一位用默认值"，或者干脆不写后面的位）：
//   essential_core [场景.xml] [斜坡s] [kp] [kd] [kd_damp]
//     场景    默认：从可执行文件往上找带 scenes/ 的那一层里的 scenes/flat_scene.xml
//     斜坡    q_des 从按下那一刻的关节角推到站姿的时长 [s]，默认 1.0（固定值，不做自适应）
//     kp/kd   站立模式的位置刚度/阻尼，默认 80 / 3（讲义 §1.4 提到的实机输出侧那一组）
//     kd_damp 阻尼模式的阻尼，默认 0.5
//   例：essential_core / 0.5 120 6    （默认场景、斜坡 0.5 s、kp=120、kd=6）
//   命令行只有这 5 个位置参数，没有 --help：用法就写在这里与 [`README.md`](../README.md) 里。
//
// 两个线程（官方 `simulate` 的既定形状）：
//   * 主线程：`RenderLoop()` —— 窗口与渲染（GLFW 要求"谁建窗口谁用它"，窗口只能在主线程跑）；
//   * 控制线程：装配现场 → `sim.Load()` 把模型交给界面 → 一步一循环（按键 / 状态机 / mj_step）。
//   **顺序要紧**：`Load()` 会阻塞等渲染线程来接模型，所以要先让主线程进 `RenderLoop()` 再 Load；
//   反了就是"开一个空窗口然后死等"（踩坑过程见 cpp/docs/sim.md）。
//   两边共享 mjModel/mjData，所有访问都在 `sim.mtx` 里（官方那个递归锁）。

#include "state.h"
#include "tty.h"

#include <mujoco/mujoco.h>

#include <simulate/glfw_adapter.h> // mujoco::GlfwAdapter
#include <simulate/simulate.h>     // mujoco::Simulate（官方界面，由 mujoco::libmujoco_simulate 提供）

#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <memory>
#include <string>
#include <thread>

namespace {

namespace fs = std::filesystem;

// 官方窗口的"关窗"只有两条路：用户点掉窗口，或者我们自己把窗口标记成该关了。
// GlfwAdapter 把 GLFWwindow* 藏在私有成员里（拿不到它去调 glfwSetWindowShouldClose），
// 但 `ShouldCloseWindow()` 是虚函数 —— 子类加一个自己的标志位就能从代码里体面地关窗，
// 于是终端的 q 也走正常收尾（析构、恢复终端、退出码 0），不用 exit() 硬退。
class ClosableAdapter : public mujoco::GlfwAdapter {
  public:
    bool ShouldCloseWindow() const override {
        return quit_.load() || mujoco::GlfwAdapter::ShouldCloseWindow();
    }
    void RequestClose() { quit_ = true; }

  private:
    mutable std::atomic_bool quit_{false};
};

// 一次仿真要用的东西：模型 + 数据 + 实际加载的场景路径（官方界面的 Load() 要一个名字）。
// 自己持有 m/d、析构里释放（中途哪一步失败也不会漏）；交给官方界面之后用 Release() 把所有权让出去，
// 否则同一个指针会被释放两次（官方的析构里也会 mj_delete*）。
// 自己管资源就要显式表态能不能拷贝，见 docs/learn/cpp-cmake.md 的「= delete」那条问答。
struct Scene {
    mjModel *m = nullptr;
    mjData *d = nullptr;
    fs::path path;

    Scene() = default;
    ~Scene() {
        if (d != nullptr)
            mj_deleteData(d);
        if (m != nullptr)
            mj_deleteModel(m);
    }
    Scene(const Scene &) = delete;
    Scene &operator=(const Scene &) = delete;

    void Release() {
        m = nullptr;
        d = nullptr;
    }
};

// 命令行：只有位置参数，没有开关也没有 --help（用法在文件头与 README 里）。
// 位置：1 场景 XML、2 斜坡时长、3..5 kp / kd / kd_damp；某一位写 "/" = 用默认值，
// 后面的位不写也是默认值。
struct Options {
    fs::path scene;    // 空 = 往上找 scenes/flat_scene.xml
    ctrl::Param param; // 默认就是 state.h 里的那几个常数
};

bool ParsePositional(int argc, char **argv, Options *out) {
    for (int i = 1; i < argc; ++i) {
        const std::string a = argv[i];
        if (a == "/")
            continue; // 这一位用默认值
        if (i > 5) {
            std::fprintf(stderr, "参数太多：最多 [场景] [斜坡] [kp] [kd] [kd_damp]（用法见 README）\n");
            return false;
        }
        if (i == 1) {
            out->scene = a;
            continue;
        }
        char *end = nullptr;
        const double v = std::strtod(a.c_str(), &end);
        if (end == a.c_str() || *end != '\0') {
            std::fprintf(stderr, "第 %d 个参数不是数字：%s（用法见 README）\n", i, a.c_str());
            return false;
        }
        if (i == 2)
            out->param.ramp = v;
        if (i == 3)
            out->param.kp = v;
        if (i == 4)
            out->param.kd = v;
        if (i == 5)
            out->param.kd_damp = v;
    }
    return true;
}

// 加载场景：从**可执行文件所在目录往上找**带 scenes/ 的那一层（比"往上数两层"健壮，
// build/ 放在仓库根还是放在本项目下都适用）。场景也可以由第一个位置参数显式给。
bool LoadScene(Scene *out, const Options &opt) {
    const fs::path exe_dir = fs::read_symlink("/proc/self/exe").parent_path();
    fs::path root;
    for (fs::path p = exe_dir; p != p.parent_path(); p = p.parent_path()) {
        if (fs::is_directory(p / "scenes")) {
            root = p;
            break;
        }
    }
    if (opt.scene.empty() && root.empty()) {
        std::fprintf(stderr, "从可执行文件所在目录往上找不到带 scenes/ 的任务目录：%s\n"
                             "把场景 XML 作为第一个位置参数传进来，或按 README 的构建命令重新构建。\n",
                     exe_dir.c_str());
        return false;
    }
    out->path = opt.scene.empty() ? root / "scenes/flat_scene.xml" : opt.scene;

    std::printf("MuJoCo %s\n", mj_versionString());
    out->m = mj_loadXML(out->path.c_str(), nullptr, nullptr, 0);
    if (out->m == nullptr) {
        std::fprintf(stderr, "加载场景失败：%s\n", out->path.c_str());
        return false;
    }
    out->d = mj_makeData(out->m);
    std::printf("场景：%s\n", out->path.c_str());
    return true;
}

// 控制线程：装现场 → 交给界面 → 一步一循环。返回值 = 进程退出码（0 正常 / 1 装配失败）。
int ControlThread(mujoco::Simulate *sim, ClosableAdapter *adapter, const Options &opt) {
    Scene scene;
    if (!LoadScene(&scene, opt)) {
        adapter->RequestClose(); // 让主线程的 RenderLoop 收工（它只看窗口该不该关）
        sim->exitrequest = 1;
        return 1;
    }
    mjModel *m = scene.m;
    mjData *d = scene.d;

    // 站姿是 12 个关节的常量表（state.h 的 kStanceQ），换模型要同步改那里
    if (m->nu != 12) {
        std::fprintf(stderr, "本核心版的站姿表按 12 个关节写的，这个模型有 %ld 个执行器。\n",
                     static_cast<long>(m->nu));
        adapter->RequestClose();
        sim->exitrequest = 1;
        return 1;
    }

    sim->Load(m, d, scene.path.c_str()); // 交给官方界面（之后 m/d 归它释放）
    scene.Release();
    {
        const mujoco::MutexLock lock(sim->mtx);
        mj_forward(m, d); // 与官方一致：先算一遍派生量，窗口第一帧才不是空的
    }

    ctrl::StateMachine sm(m, kStanceQ, opt.param);
    std::printf("站姿：z=%.4f m（12 个关节角内联在 state.h）；阻尼 kd=%.3g；站立 kp=%.3g kd=%.3g、"
                "斜坡 %.2f s；状态 = %s（上电默认）\n",
                kStanceZ, opt.param.kd_damp, opt.param.kp, opt.param.kd, opt.param.ramp,
                ctrl::Name(sm.state()));

    tty::RawKeys keys;
    if (keys.ok())
        std::printf("按键（就在这个终端里按，不用回车）：S = 站立模式、D = 阻尼模式、R = 回到起点、"
                    "Q / Ctrl-C = 退出；窗口里空格 = 暂停/继续\n");
    else
        std::printf("注意：stdin 不是终端，按不了键 —— 在终端里直接运行本程序才有按键\n");

    auto wall0 = std::chrono::steady_clock::now();
    double sim0 = d->time; // 与 wall0 配对：把仿真时间轴钉在墙钟上（暂停时会重新对齐）
    while (!sim->exitrequest) {
        // 终端按键：非阻塞，一次读干净（不用等某一帧，按了就算数）
        char key = 0;
        bool quit = false;
        while (keys.TakeKey(&key)) {
            if (key == 's') {
                if (sm.Request(ctrl::State::Standing, d))
                    std::printf("按键 → %s\n", ctrl::Name(sm.state()));
            } else if (key == 'd') {
                if (sm.Request(ctrl::State::Damping, d))
                    std::printf("按键 → %s\n", ctrl::Name(sm.state()));
            } else if (key == 'r') {
                // 回到起点：摆回模型原姿态（`--start raw` 就是它），并切回上电默认的阻尼模式。
                // **保留仿真时间轴**：斜坡进度按 d->time 算，而 mj_resetData 会把 time 清零 ——
                // 那样"按 R 之后再按 S"的斜坡会先卡住 ramp_t0_ 那么久（这个坑完整版也踩过）。
                const double t_keep = d->time;
                mj_resetData(m, d);
                d->time = t_keep;
                sm.Request(ctrl::State::Damping, d);
                std::printf("按键 → 回到起点（模型原姿态），切回%s\n", ctrl::Name(sm.state()));
            } else if (key == 'q') {
                quit = true;
            }
        }
        if (quit) {
            adapter->RequestClose();
            break;
        }
        if (sim->run == 0) { // 窗口里按了空格：暂停。这段时间不算"落后"，时间轴重新对齐
            std::this_thread::sleep_for(std::chrono::milliseconds(5));
            wall0 = std::chrono::steady_clock::now();
            sim0 = d->time;
            continue;
        }
        // 一步一循环：跑满"这一帧该走的步"。guard 限的是**单帧最多补多少步**（5000 步 = 10 s 仿真
        // 时间）：万一渲染卡住（拖窗口、断点），elapsed 会突然变成好几秒，没有上限就会一次补几万步、
        // 把渲染线程锁在门外（看着像假死）。到上限就放弃这一帧的追赶，下一帧接着跑。
        const double elapsed =
            std::chrono::duration<double>(std::chrono::steady_clock::now() - wall0).count();
        int guard = 0;
        while (d->time < sim0 + elapsed && ++guard < 5000) {
            const mujoco::MutexLock lock(sim->mtx); // 渲染线程也在读 m/d
            sm.Apply(d);                            // 状态机 → d->ctrl
            mj_step(m, d);                          // 物理前进一步
        }
    }
    return 0;
}

} // namespace

int main(int argc, char **argv) {
    // 交互式运行：日志要立刻可见（不重定向时 stdout 是块缓冲，被 Ctrl-C/信号打断就全丢了）
    std::setvbuf(stdout, nullptr, _IOLBF, 0);
    Options opt;
    if (!ParsePositional(argc, argv, &opt))
        return 1;

    // 官方界面的相机/选项/扰动：给默认值即可（之后都在窗口里改）
    mjvCamera cam;
    mjvOption ui_opt;
    mjvPerturb pert;
    mjv_defaultCamera(&cam);
    mjv_defaultOption(&ui_opt);
    mjv_defaultPerturb(&pert);

    auto adapter = std::make_unique<ClosableAdapter>();
    ClosableAdapter *adapter_raw = adapter.get();
    auto sim = std::make_unique<mujoco::Simulate>(std::move(adapter), &cam, &ui_opt, &pert,
                                                  /*is_passive=*/false);
    std::printf("窗口：MuJoCo 官方 Simulate 界面（相机 / 暂停 / 调速都在窗口里；我们的按键在终端）\n");

    // 顺序要紧：控制线程里的 Load() 在等渲染线程，所以主线程先跑 RenderLoop，再起控制线程
    std::atomic<int> rc{0};
    std::thread control([&] { rc = ControlThread(sim.get(), adapter_raw, opt); });
    sim->RenderLoop();    // 阻塞：直到窗口被关（用户点掉，或控制线程收到 q 后 RequestClose）
    sim->exitrequest = 1; // 通知控制线程收工
    control.join();
    return rc.load();
}
