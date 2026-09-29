// 第三次培训 · 子任务项一（仿真部分）的最简版：把关节电机当 MIT 混合控制器自己算，控制程序写成状态机。
//
//   阻尼模式（上电默认）：12 个关节都下阻尼指令（kp=0、kd=--kd-damp、pos=0）⇒ τ = −kd·q̇
//   站立模式：按 S，位置项目标 q_des 从"按下那一刻的关节角"在斜坡时长里平滑推到站姿
//             （kp/kd 默认 80/3 = 讲义 §1.4 提到的实机输出侧配置那一组）；按 D 切回阻尼。
//
// 窗口用 **MuJoCo 官方的 Simulate 界面**：相机、暂停/单步/调速、关节与执行器的面板都是现成的，
// 不用自己写窗口。代价是它的键是它自己的 UI（挂不上自定义回调），所以我们的键改成从**终端**读
// （见 tty.h），终端同时也充当 HUD —— 状态变化、起点/收工摘要都打在这里。
//
// 这是 [`../../src/`](../../src/) 那个版本的精简版：只留这一个模式（没有 `--mode sim/record`、没有 `--script`）、
// 地面恒为水平（没有 `--pitch/--roll/--floor-*`）、电机只有"MIT 公式 + 模型自带的限幅"。
//
// 用法（在终端里跑，按键才有用）：
//   pixi run cmake -S @20260927_motor/cpp/essential -B @20260927_motor/cpp/essential/build -G Ninja -DCMAKE_PREFIX_PATH="$CONDA_PREFIX"
//   pixi run cmake --build @20260927_motor/cpp/essential/build
//   pixi run @20260927_motor/cpp/essential/build/essential_sim
//
// 两个线程（官方 `simulate` 的既定形状）：
//   * 主线程：`RenderLoop()` —— 窗口与渲染（GLFW 要求"谁建窗口谁用它"，所以窗口在主线程里跑）；
//   * 控制线程：装配现场 → `sim.Load()` 把模型交给界面 → 一步一循环（按键 / 状态机 / 电机 / mj_step）。
//   两边共享 mjModel/mjData，所有访问都在 `sim.mtx` 里（官方那个递归锁）。
//   **顺序要紧**：`Load()` 会阻塞等渲染线程来接模型，所以要先让主线程进 `RenderLoop()` 再 Load；
//   反了就是"开一个空窗口然后死等"（踩坑记录见 README 与 cpp/src 版的同类实现）。

#include "cli.h"
#include "motor.h"
#include "observation.h"
#include "scene_setup.h"
#include "start.h"
#include "state.h"
#include "tty.h"

#include <mujoco/mujoco.h>

#include <simulate/glfw_adapter.h> // mujoco::GlfwAdapter
#include <simulate/simulate.h>     // mujoco::Simulate（官方界面，由 mujoco::libmujoco_simulate 提供）

#include <atomic>
#include <chrono>
#include <cstdio>
#include <memory>
#include <string>
#include <thread>
#include <vector>

namespace {

// 官方窗口的"关窗"只有两条路：用户点掉窗口，或者我们自己把窗口标记成该关了。
// GlfwAdapter 把 GLFWwindow* 藏在私有成员里（拿不到它去调 glfwSetWindowShouldClose），
// 但 `ShouldCloseWindow()` 是虚函数——子类加一个自己的标志位就能从代码里体面地关窗，
// 于是终端的 q 也走正常收尾（收工摘要、析构、退出码 0），不用 exit() 硬退。
class ClosableAdapter : public mujoco::GlfwAdapter {
  public:
    bool ShouldCloseWindow() const override {
        return quit_.load() || mujoco::GlfwAdapter::ShouldCloseWindow();
    }
    void RequestClose() { quit_ = true; }

  private:
    mutable std::atomic_bool quit_{false};
};

// 控制线程：装现场 → 交给界面 → 一步一循环。返回值 = 进程退出码（0 正常 / 1 装配失败）。
int ControlThread(mujoco::Simulate *sim, ClosableAdapter *adapter, const cli::Options &opt) {
    // 现场：加载场景 → 足底球 → 读站姿文件 → 摆到起点（失败原因已经打到 stderr）
    setup::Scene scene;
    if (!setup::Prepare(opt, &scene)) {
        adapter->RequestClose(); // 装配失败：让主线程的 RenderLoop 收工（它只看窗口该不该关）
        sim->exitrequest = 1;
        return 1;
    }
    mjModel *m = scene.model;
    mjData *d = scene.data;
    const std::vector<int> &feet = scene.feet;
    const stance::Target &target = scene.target;
    const double *ref = scene.ref; // 漂移参考点 = 起点基座位置
    const std::string scene_path = scene.scene_path.string();

    sim->Load(m, d, scene_path.c_str()); // 交给官方界面（之后 m/d 归它释放）
    scene.Release();                     // 我们这边放弃所有权，否则同一个指针会被释放两次
    {
        const mujoco::MutexLock lock(sim->mtx);
        mj_forward(m, d); // 与官方一致：先算一遍派生量，窗口第一帧才不是空的
    }

    motor::JointMotors motors(m);
    ctrl::Config cfg;
    cfg.kp = opt.kp;
    cfg.kd = opt.kd;
    cfg.kd_damp = opt.kd_damp;
    cfg.ramp = opt.ramp;
    cfg.ramp_fast = opt.ramp_fast;
    cfg.z_stand = target.z;
    cfg.auto_ramp = opt.auto_ramp;
    ctrl::StateMachine sm(m, &motors, target.q, cfg);
    std::printf("状态机：%s；初始 = %s（上电默认）；起点 = %s\n", sm.desc(), ctrl::Name(sm.state()),
                opt.start.c_str());

    tty::RawKeys keys;
    if (keys.ok())
        std::printf("按键（就在这个终端里按，不用回车）：S = 站立模式、D = 阻尼模式、R = 回到起点、"
                    "Q / Ctrl-C = 退出；窗口里空格 = 暂停/继续，关窗也能退出\n");
    else
        std::printf("注意：stdin 不是终端，按不了键——在终端里直接运行本程序才有按键\n");

    observation::PrintSnapshot("起点", observation::Sample(m, d, feet, ref));

    auto wall0 = std::chrono::steady_clock::now();
    double sim0 = d->time; // 与 wall0 配对：把仿真时间轴钉在墙钟上（暂停时会重新对齐）
    long steps = 0;
    double t_stand_start = -1.0, t_stand_done = -1.0;
    while (!sim->exitrequest) {
        // 终端按键：非阻塞，一次读干净（不用等某一帧，按了就算数）
        char key = 0;
        bool quit = false;
        while (keys.TakeKey(&key)) {
            if (key == 's') {
                if (sm.Request(ctrl::State::Standing, d)) {
                    t_stand_start = d->time;
                    t_stand_done = -1.0;
                    std::printf("%s\n", sm.last_event());
                }
            } else if (key == 'd') {
                if (sm.Request(ctrl::State::Damping, d))
                    std::printf("%s\n", sm.last_event());
            } else if (key == 'r') {
                // 回到起点：摆回 --start 的位姿，再把状态切回上电默认的阻尼模式。
                // 这段胶水在 ../src 里是函数 start::Reset（那边有窗口/录像两个调用点），这里只有一个，
                // 就写在按 R 的分支里——与它被使用的地方摆在一起。
                const observation::Snapshot before = observation::Sample(m, d, feet, ref);
                if (!start::Pose(m, d, opt.start, target))
                    std::printf("重置失败（--start %s）\n", opt.start.c_str());
                const observation::Snapshot after = observation::Sample(m, d, feet, ref);
                sm.Request(ctrl::State::Damping, d);
                std::printf("重置：回到 --start %s（t=%.3f s 保留）；基座 z %.4f → %.4f m、竖直度 "
                            "%.2f° → %.2f°；状态 → %s（会自然塌下，接着按 S 就能从起点重新起身）\n",
                            opt.start.c_str(), d->time, before.z, after.z, before.tilt, after.tilt,
                            ctrl::Name(sm.state()));
                t_stand_start = t_stand_done = -1.0;
            } else if (key == 'q') {
                quit = true;
            }
        }
        if (quit) {
            std::printf("收到 q：收工（窗口跟着关掉）\n");
            adapter->RequestClose();
            break;
        }
        if (sim->run == 0) { // 窗口里按了空格：暂停。这段时间不算"落后"，时间轴重新对齐
            std::this_thread::sleep_for(std::chrono::milliseconds(5));
            wall0 = std::chrono::steady_clock::now();
            sim0 = d->time;
            continue;
        }
        // 一步一循环：跑满"这一帧该走的步"（与 ../src 的窗口循环同一套时间轴算法）
        const double elapsed =
            std::chrono::duration<double>(std::chrono::steady_clock::now() - wall0).count();
        int guard = 0;
        while (d->time < sim0 + elapsed && ++guard < 5000) {
            const mujoco::MutexLock lock(sim->mtx); // 渲染线程也在读 m/d
            sm.Update(d);
            motors.Apply(d);
            mj_step(m, d);
            ++steps;
            if (sm.state() == ctrl::State::Standing && t_stand_start >= 0.0 && t_stand_done < 0.0 &&
                observation::StoodUp(observation::Sample(m, d, feet, ref), target)) {
                t_stand_done = d->time;
                std::printf("起身完成：从按下 S 到 z 到位共用 %.2f s（斜坡 %.2f s）\n",
                            t_stand_done - t_stand_start, sm.chosen_ramp());
            }
        }
    }

    const observation::Snapshot end = observation::Sample(m, d, feet, ref);
    observation::PrintSnapshot("收工", end);
    std::printf("控制线程：物理 %ld 步 / 仿真 %.3f s，状态切换 %d 次\n", steps, end.t, sm.switches());
    motor::PrintStats(motors);
    if (t_stand_done >= 0.0)
        std::printf("起身：从按下站立键到 z 到位共用 %.2f s（斜坡 %.2f s，q_des 是连续的）\n",
                    t_stand_done - t_stand_start, sm.chosen_ramp());
    return 0;
}

} // namespace

int main(int argc, char **argv) {
    // 交互式运行：日志要立刻可见（不重定向时 stdout 是块缓冲，被 Ctrl-C/信号打断就全丢了）
    std::setvbuf(stdout, nullptr, _IOLBF, 0);
    const cli::Options opt = cli::ParseOptions(argc, argv);

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
    std::printf("窗口已关闭，收工（退出码 %d）\n", rc.load());
    sim.reset(); // m/d 归官方界面管，我们不 delete
    return rc.load();
}
