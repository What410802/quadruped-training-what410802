// 第三次培训 · 第一部分（仿真）：把关节电机当 MIT 混合控制器自己算，控制程序写成状态机。
//
//   阻尼模式（上电默认）：12 个关节都下阻尼指令（kp=0、kd=--kd-damp、pos=0）⇒ τ = −kd·q̇
//   站立模式：按 S 键，位置项目标 q_des 从"按下那一刻的关节角"在 --ramp 秒内平滑推到站姿
//             （kp/kd 默认 80/3 = 讲义 §1.4 提到的实机输出侧配置那一组）；按 D 键切回阻尼。
//
// 用法：
//   pixi run cmake -S @20260927_motor/cpp -B @20260927_motor/cpp/build -G Ninja -DCMAKE_PREFIX_PATH="$CONDA_PREFIX"
//   pixi run cmake --build @20260927_motor/cpp/build
//   pixi run @20260927_motor/cpp/build/motor_sim                                   # 开窗口，键盘切换
//   pixi run @20260927_motor/cpp/build/motor_sim --mode sim --seconds 8 --script "1:stand,5:damp"
//
// 细节（为什么这么建模、实测数字、与实机的对应关系）见 ../docs/sim.md（= 任务目录下的 cpp/docs/sim.md）。
// 退出码：0 = 判定通过（含 --help）、1 = 参数错误、2 = 判定不通过。
//
// 本文件只做**编排**：从上往下读就是"一次运行"的故事，每件事各有一个头文件负责：
//   cli.h          命令行面：用法文本、选项表、取值与校验（`--mode view|sim|record` 等）
//   scene_setup.h  现场装配：场景 XML → 地面/脚 → 站姿搜索 → 地面倾角 → 摆到起点（并持有 model/data）
//   motor.h        关节电机：MIT 公式、限幅/死区/延迟/噪声、统计（讲义 §1.2/§1.4）
//   state.h        控制程序状态机：阻尼 / 站立 + 自动斜坡（本任务的正文）
//   observation.h  量测：Snapshot/Sample + "算不算起身完成"
//   start.h        起点：摆位与"回到起点"（= 窗口按 R / 脚本 reset）
//   viewer.h       自己写的窗口（键盘 + 鼠标相机 + HUD）
//   recorder.h     无窗口录像（隐藏窗口离屏渲染 → ffmpeg）
// HUD 只能用 ASCII：MuJoCo 内置位图字体没有 CJK 字形，中文留给终端日志（见 viewer.h）。

#include "cli.h"
#include "motor.h"
#include "observation.h"
#include "recorder.h"
#include "scene_setup.h"
#include "stance_file.h"
#include "start.h"
#include "state.h"
#include "viewer.h"

#include <mujoco/mujoco.h>

#include <GLFW/glfw3.h>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <memory>
#include <string>
#include <vector>

namespace fs = std::filesystem;

namespace {

// HUD（左上/右上那两块字）在窗口与录像两个循环里都要画，内容只差一两行，所以公共片段抽出来，
// 免得改一处漏一处。字符串必须与原来逐字相同：视频最外圈就是它。
const char *kTitle = "3rd training, part 1: joint-motor state machine";

// 左上第一行：当前状态 + （已经起身完成的话）起身用时
void HudStateLine(char *out, size_t n, const ctrl::StateMachine &sm, double t_stand_start,
                  double t_stand_done) {
    char up[64] = "";
    if (sm.state() == ctrl::State::Standing && t_stand_done >= 0.0)
        std::snprintf(up, sizeof(up), "  (up in %.2f s, ramp %.2f s)", t_stand_done - t_stand_start,
                      sm.chosen_ramp());
    std::snprintf(out, n, "state: %s%s\n", ctrl::NameAscii(sm.state()), up);
}

// 右上那几个数（两处一样；extra 是插在"ground tilt"与"|tau| peak"之间的那一行，可为空串）
void HudRight(char *out, size_t n, const observation::Snapshot &now, const stance::Plane &plane,
              double tau_peak, const char *extra) {
    std::snprintf(out, n,
                  "t = %.2f s\nfeet on ground: %d\nbase z = %.4f m\ntilt = %.2f deg\n"
                  "ground tilt = %.1f deg\n%s|tau| peak = %.1f N*m",
                  now.t, now.feet, now.z, now.tilt,
                  std::acos(std::clamp(plane.up[2], -1.0, 1.0)) * 180.0 / M_PI,
                  extra == nullptr ? "" : extra, tau_peak);
}

} // namespace

int main(int argc, char **argv) {
    // 交互式运行（窗口模式）时日志要立刻可见：不重定向的话 stdout 是块缓冲，
    // 万一中途被 Ctrl-C/信号打断，缓冲区里的日志就全丢了。
    std::setvbuf(stdout, nullptr, _IOLBF, 0);
    const cli::Options opt = cli::ParseOptions(argc, argv);

    // 现场：加载场景 → 地面/脚 → 站姿搜索 → 地面倾角 → 摆到起点（失败原因已经打到 stderr）
    setup::Scene scene;
    if (!setup::Prepare(opt, &scene))
        return 1;
    mjModel *m = scene.model;
    mjData *d = scene.data;
    const std::vector<int> &feet = scene.feet;
    const stance::Plane &ground_plane = scene.plane;
    const stance::Target &target = scene.target;
    const double *ref = scene.ref; // 漂移参考点 = 起点基座位置

    // --dump-stance：把刚搜出来的站姿写到文件就收工（给 cpp/essential 用；格式见 stance_file.h）
    if (!opt.dump_stance.empty()) {
        if (!stance::SaveToFile(opt.dump_stance, m, feet, scene.foot_radius, target)) {
            std::fprintf(stderr, "站姿文件写不进：%s\n", opt.dump_stance.c_str());
            return 1;
        }
        std::printf("站姿已写入：%s（供 cpp/essential 加载）\n", opt.dump_stance.c_str());
        return 0;
    }

    motor::JointMotors motors(m, opt.tau_max, opt.deadzone, opt.delay_cycles, opt.noise);
    ctrl::Config cfg;
    cfg.kp = opt.kp;
    cfg.kd = opt.kd;
    cfg.kd_damp = opt.kd_damp;
    cfg.ramp = opt.ramp;
    cfg.ramp_fast = opt.ramp_fast;
    cfg.z_stand = target.z;
    cfg.auto_ramp = opt.auto_ramp;
    cfg.gravity_comp = opt.gravity_comp;
    cfg.ground = ground_plane;
    ctrl::StateMachine sm(m, &motors, target.q, cfg);
    std::printf("电机模型：%s\n",
                (opt.tau_max > 0.0 || opt.deadzone > 0.0 || opt.delay_cycles > 0 || opt.noise > 0.0)
                    ? "含非理想项（见下面几个开关的取值）"
                    : "理想力矩源（τ = τ_ff + kp·(q_des − q) + kd·(q̇_des − q̇)，只做限幅）");
    std::printf("电机非理想项：限幅 ±%.1f N·m、死区 %.3f N·m、指令延迟 %d 周期、噪声 %.3f N·m\n",
                opt.tau_max > 0.0 ? opt.tau_max : m->actuator_ctrlrange[1], opt.deadzone,
                opt.delay_cycles, opt.noise);
    std::printf("状态机：%s；初始 = %s（上电默认）；起点 = %s\n", sm.desc(),
                ctrl::Name(sm.state()), opt.start.c_str());

    // 讲义 §2.3 的换算：第二部分对实机下发的就是右边这组（本模型 gear=1，仿真里用不到）
    {
        const motor::Cmd c = motor::Mit(target.q[0], opt.kp, opt.kd);
        const motor::RotorCmd r = motor::ToRotor(c, opt.gear);
        std::printf("转子侧换算（讲义 §2.3，N=%.2f，仅演示）：关节侧 kp=%.3g kd=%.3g q_des=%.3f rad"
                    " → cmd.K_P=%.4g cmd.K_W=%.4g cmd.Pos=%.4g；反馈 q = Pos/N + offset\n",
                    opt.gear, opt.kp, opt.kd, c.pos, r.K_P, r.K_W, r.Pos);
    }

    const observation::Snapshot start_row = observation::Sample(m, d, feet, ref, ground_plane);
    observation::PrintSnapshot("起点", start_row);

    if (opt.mode == "view") {
        // ---------------------------------------------------------------- 窗口模式
        viewer::Window win(m, "motor_sim | 第三次培训·第一部分", opt.width, opt.height);
        auto wall0 = std::chrono::steady_clock::now();
        const double sim0 = d->time;
        long steps = 0;
        bool quit = false;
        double t_stand_start = -1.0, t_stand_done = -1.0;
        char hud_left[512], hud_right[512];
        while (win.Poll() && !quit) {
            int key = 0;
            while (win.TakeKey(&key)) {
                if (key == GLFW_KEY_S) {
                    if (sm.Request(ctrl::State::Standing, d)) {
                        t_stand_start = d->time;
                        t_stand_done = -1.0;
                    }
                } else if (key == GLFW_KEY_D) {
                    sm.Request(ctrl::State::Damping, d);
                } else if (key == GLFW_KEY_R) {
                    // 回到起点，重新演示
                    start::Reset(m, d, opt.start, target, feet, scene.foot_radius, ground_plane, &sm,
                                 ref);
                    t_stand_start = t_stand_done = -1.0;
                } else if (key == GLFW_KEY_Q || key == GLFW_KEY_ESCAPE) {
                    quit = true;
                }
            }
            if (quit)
                break;
            // 把仿真时间轴钉在墙钟上（单线程：物理跑满这一帧该走的步，再渲染一次）
            const double elapsed =
                std::chrono::duration<double>(std::chrono::steady_clock::now() - wall0).count();
            int guard = 0;
            while (d->time < sim0 + elapsed && ++guard < 5000) {
                sm.Update(d);
                motors.Apply(d);
                mj_step(m, d);
                ++steps;
                if (sm.state() == ctrl::State::Standing && t_stand_start >= 0.0 &&
                    t_stand_done < 0.0 &&
                    observation::StoodUp(observation::Sample(m, d, feet, ref, ground_plane), target))
                    t_stand_done = d->time;
            }
            const observation::Snapshot now =
                observation::Sample(m, d, feet, ref, ground_plane);
            // HUD 全用 ASCII：MuJoCo 内置位图字体不含中文/希腊字母，画出来是乱码块（终端日志仍用中文）
            char state_line[128];
            HudStateLine(state_line, sizeof(state_line), sm, t_stand_start, t_stand_done);
            std::snprintf(hud_left, sizeof(hud_left),
                          "motor_sim  |  %s\n%s%s\n"
                          "S = stand   D = damp   R = reset   Q/Esc = quit",
                          kTitle, state_line, sm.last_event_ascii());
            char switches[64] = "";
            std::snprintf(switches, sizeof(switches), "switches: %d\n", sm.switches());
            HudRight(hud_right, sizeof(hud_right), now, ground_plane, motors.stats().tau_peak,
                     switches);
            win.Draw(m, d, hud_left, hud_right);
        }
        const observation::Snapshot end = observation::Sample(m, d, feet, ref, ground_plane);
        observation::PrintSnapshot("收工", end);
        std::printf("窗口：物理 %ld 步 / 仿真 %.3f s，状态切换 %d 次\n", steps, end.t,
                    sm.switches());
        motor::PrintStats(motors);
        if (t_stand_done >= 0.0)
            std::printf("起身：从按下站立键到 z 到位共用 %.2f s（斜坡 %.2f s，q_des 是连续的）\n",
                        t_stand_done - t_stand_start, sm.chosen_ramp());
        return 0;
    }

    // ---------------------------------------------------------------- 无窗口（只仿真 / 录像）
    std::unique_ptr<FrameRecorder> rec;
    if (opt.mode == "record") {
        const fs::path out =
            opt.out.empty() ? scene.root / "output/cpp/state_machine.mp4" : opt.out;
        fs::create_directories(out.parent_path());
        rec = std::make_unique<FrameRecorder>(m, out.string(), opt.width, opt.height, opt.fps);
        char off[96];
        if (rec->scaled())
            std::snprintf(off, sizeof(off), "离屏缓冲 %dx%d → 缩放输出 %dx%d", rec->viewport_width(),
                          rec->viewport_height(), opt.width, opt.height);
        else
            std::snprintf(off, sizeof(off), "离屏缓冲 = 输出 %dx%d", rec->viewport_width(),
                          rec->viewport_height());
        std::printf("录像：%.0f fps → %s（%s）\n", opt.fps, rec->path().c_str(), off);
    }
    std::printf("%s：无窗口，全速跑 %.3f 仿真秒", opt.mode == "record" ? "录像 + 仿真" : "只仿真",
                opt.seconds);
    if (!opt.script.empty()) {
        std::printf("，脚本 ");
        for (const auto &e : opt.script)
            std::printf("%.2f s→%s ", e.first,
                        e.second == cli::Action::Reset ? "重置" : ctrl::Name(cli::ToState(e.second)));
    }
    std::printf("\n");

    // 视频里也画 HUD（ASCII）；左侧把脚本写出来，方便看视频的人知道在演什么
    char script_text[256] = "no script (pure damping)";
    if (!opt.script.empty()) {
        script_text[0] = '\0';
        for (const auto &e : opt.script)
            std::snprintf(script_text + std::strlen(script_text),
                          sizeof(script_text) - std::strlen(script_text), "%.2f s -> %s   ", e.first,
                          cli::NameAscii(e.second));
    }

    const auto t_start = std::chrono::steady_clock::now();
    size_t next_event = 0;
    long steps = 0;
    double t_stand_start = -1.0, t_stand_done = -1.0;
    char hud_left[512], hud_right[384];
    while (d->time < opt.seconds - 1e-12) {
        while (next_event < opt.script.size() && d->time >= opt.script[next_event].first - 1e-12) {
            const observation::Snapshot before =
                observation::Sample(m, d, feet, ref, ground_plane);
            observation::PrintSnapshot(ctrl::Name(sm.state()), before); // 上一段的末态
            if (sm.state() == ctrl::State::Standing && t_stand_start >= 0.0)
                std::printf("    上一段（站立）：起身用时 %.2f s（斜坡 %.2f s）\n",
                            (t_stand_done >= 0.0 ? t_stand_done : before.t) - t_stand_start,
                            sm.chosen_ramp());
            if (opt.script[next_event].second == cli::Action::Reset) {
                start::Reset(m, d, opt.start, target, feet, scene.foot_radius, ground_plane, &sm, ref);
                t_stand_start = t_stand_done = -1.0;
            } else if (sm.Request(cli::ToState(opt.script[next_event].second), d)) {
                std::printf("--- t=%.3f s 切换 → %s\n", d->time, ctrl::Name(sm.state()));
                if (sm.state() == ctrl::State::Standing) {
                    t_stand_start = d->time;
                    t_stand_done = -1.0;
                }
            }
            ++next_event;
        }
        sm.Update(d);
        motors.Apply(d);
        mj_step(m, d);
        ++steps;
        if (sm.state() == ctrl::State::Standing && t_stand_start >= 0.0 && t_stand_done < 0.0 &&
            observation::StoodUp(observation::Sample(m, d, feet, ref, ground_plane), target))
            t_stand_done = d->time;
        if (rec) {
            const observation::Snapshot now =
                observation::Sample(m, d, feet, ref, ground_plane);
            char state_line[128];
            HudStateLine(state_line, sizeof(state_line), sm, t_stand_start, t_stand_done);
            std::snprintf(hud_left, sizeof(hud_left), "%s\n%s" "script: %s", kTitle, state_line,
                          script_text);
            HudRight(hud_right, sizeof(hud_right), now, ground_plane, motors.stats().tau_peak, "");
            rec->Capture(m, d, hud_left, hud_right);
        }
    }
    const double wall_ms =
        std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t_start).count();

    const observation::Snapshot end = observation::Sample(m, d, feet, ref, ground_plane);
    observation::PrintSnapshot(ctrl::Name(sm.state()), end);
    std::printf("仿真 %.3f s（%ld 步，wall %.1f ms，单步 %.4f ms，%.1fx 实时）\n", end.t, steps,
                wall_ms, wall_ms / std::max(1L, steps), 1000.0 * end.t / std::max(1e-9, wall_ms));
    if (rec) {
        // 计时已经按下：Close() 要等 ffmpeg 写完 moov，不该算进“单步耗时/实时率”
        std::printf("录像：%d 帧 → %s（wall 不含 ffmpeg 收尾）\n", rec->frames(), rec->path().c_str());
        rec->Close();
        rec.reset(); // 显式收掉：让渲染资源先于 Scene（模型）释放，与搬出 main 之前的顺序一致
    }
    if (t_stand_done >= 0.0)
        std::printf("起身：从按下站立键到四足站定共用 %.2f s（斜坡 %.2f s，q_des 是连续的）\n",
                    t_stand_done - t_stand_start, sm.chosen_ramp());
    motor::PrintStats(motors);

    // 判定：任务的两条要求各自的可测形式
    bool ok = true;
    if (sm.state() == ctrl::State::Standing) {
        const double z_err = std::fabs(end.z - target.z);
        const bool stable = end.feet == 4 && z_err <= 0.03 && end.tilt <= 5.0 && end.qvel_max < 0.5;
        ok = stable && t_stand_done >= 0.0;
        std::printf("判定：站立模式——四足触地 %d、基座 z %.4f（目标 %.4f，差 %.4f m）、竖直度 %.2f°、"
                    "末段 max|q̇| %.3f → %s\n",
                    end.feet, end.z, target.z, z_err, end.tilt, end.qvel_max, ok ? "站住了 ✓" : "没站住 ✗");
    } else {
        const bool collapsed = end.feet == 4 && end.z < target.z - 0.15 && end.qvel_max < 0.5;
        ok = collapsed;
        std::printf("判定：阻尼模式——四足触地 %d、基座 z %.4f（站姿 %.4f，低 %.3f m）、末段 max|q̇| "
                    "%.3f → %s\n",
                    end.feet, end.z, target.z, target.z - end.z, end.qvel_max,
                    ok ? "松手后塌回趴卧 ✓" : "没塌住 ✗");
    }
    return ok ? 0 : 2;
}
