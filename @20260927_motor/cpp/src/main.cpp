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
// 细节（为什么这么建模、实测数字、与实机的对应关系）见 ../docs/sim.md。
// 退出码：0 = 判定通过（含 --help）、1 = 参数错误、2 = 判定不通过。

#include "args.h"
#include "motor.h"
#include "stance.h"
#include "state.h"
#include "viewer.h"

#include <mujoco/mujoco.h>

#include <GLFW/glfw3.h>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <filesystem>
#include <stdexcept>
#include <string>
#include <thread>
#include <utility>
#include <vector>

namespace fs = std::filesystem;

namespace {

const char *kUsage =
    "用法：motor_sim [scene.xml] [--mode view|sim] [--start raw|stance|rest|side]\n"
    "                 [--kp N] [--kd N] [--kd-damp N] [--ramp SEC] [--gravity-comp]\n"
    "                 [--seconds N] [--script \"t:mode,...\"] [--width N] [--height N]\n"
    "                 [--tau-max N] [--deadzone N] [--delay-cycles N] [--noise N] [--gear N]\n"
    "\n"
    "第三次培训·第一部分（仿真）：关节电机 = MIT 混合控制器（讲义 §1.2），\n"
    "控制程序是两状态的**状态机**——阻尼模式 / 站立模式，窗口里按键实时切换。\n"
    "\n"
    "  --mode view     开窗口（自己写的窗口，才有键盘切换）；默认\n"
    "  --mode sim      无窗口只仿真，跑完 --seconds 打印指标与判定（回归用）\n"
    "  --start …       起点：raw = 模型原姿态（默认）、stance = 搜出来的站姿、\n"
    "                  rest = 场景自带的趴卧 keyframe、side = 侧躺（绕 x 转 90° 再抬高）\n"
    "  --script …      仅 --mode sim：形如 \"1:stand,5:damp\"（到该仿真时刻切状态）\n"
    "  --ramp auto|SEC  站立模式下 q_des 的斜坡：auto（默认）按按下那一刻的姿态选——\n"
    "                  还在站姿附近用 0.1 s（必须快收腿），已经趴下用 1.5 s（慢慢起）\n"
    "  --kp/--kd       站立模式的输出侧刚度/阻尼（默认 80 / 3，取讲义 §1.4 的实机配置）\n"
    "  --kd-damp       阻尼模式的阻尼（默认 0.5；这组增益决定了“软瘫”后落在什么姿势，\n"
    "                  越大腿越撑得住、越大越容易侧翻，实测见 ../docs/sim.md）\n"
    "  --gravity-comp  站立模式叠加 qfrc_bias 前馈（试验用；实机拿不到这个量）\n"
    "  --tau-max N     覆盖执行器限幅（默认用模型 ctrlrange ±20；实机 black 配置是 33.5）\n"
    "  --deadzone N    静摩擦死区：|τ| < N 时输出 0（默认 0 = 不建死区）\n"
    "  --delay-cycles N  指令延迟 N 个控制周期（默认 0）\n"
    "  --noise N       力矩噪声 [N·m]（默认 0；固定种子，可复现）\n"
    "  --gear N        减速比（默认 6.33）：只用于打印转子侧命令的换算，不影响仿真\n"
    "  --width/--height  窗口尺寸（默认 1280x720）\n"
    "\n"
    "退出码：0 = 判定通过（或 --help）、1 = 参数错误、2 = 判定不通过。\n";

const std::vector<OptionDef> kOptionDefs = {
    {"--mode", true},         {"--start", true},        {"--kp", true},
    {"--kd", true},           {"--kd-damp", true},      {"--ramp", true},
    {"--gravity-comp", false}, {"--seconds", true},     {"--script", true},
    {"--width", true},        {"--height", true},       {"--tau-max", true},
    {"--deadzone", true},     {"--delay-cycles", true}, {"--noise", true},
    {"--gear", true},
};

struct Options {
    std::string mode = "view";  // view / sim
    fs::path scene;             // 空 = <任务目录>/scenes/flat_scene.xml
    std::string start = "raw";  // raw / stance / rest / side
    double kp = 80.0;           // 站立模式的位置刚度（关节侧）
    double kd = 3.0;            // 站立模式的阻尼
    double kd_damp = 0.5;       // 阻尼模式的阻尼（小阻尼才像真狗那样“软瘫”趴下，见 docs/sim.md）
    bool auto_ramp = true;      // --ramp auto（默认）：按按下那一刻的姿态选斜坡
    double ramp = 1.5;          // --ramp SEC 时用（也是 auto 分支里“已经趴下”那支）
    double ramp_fast = 0.1;     // auto 分支里“还在站姿附近”用的快斜坡
    bool gravity_comp = false;
    double seconds = 8.0;       // sim 模式的仿真时长
    std::vector<std::pair<double, ctrl::State>> script;
    int width = 1280, height = 720;
    double tau_max = 0.0;       // 0 = 用模型 ctrlrange
    double deadzone = 0.0;
    int delay_cycles = 0;
    double noise = 0.0;
    double gear = 6.33;         // 宇树 GO-8010-6 的减速比（讲义 §2.1）
};

// 解析 "1:stand,5:damp" 这类脚本
bool ParseScript(const std::string &text, std::vector<std::pair<double, ctrl::State>> *out) {
    size_t pos = 0;
    while (pos <= text.size()) {
        const size_t comma = text.find(',', pos);
        const std::string item = text.substr(pos, comma == std::string::npos ? std::string::npos
                                                                            : comma - pos);
        if (!item.empty()) {
            const size_t colon = item.find(':');
            if (colon == std::string::npos) {
                std::fprintf(stderr, "--script 的每一项要写成 t:mode（如 1:stand）：%s\n", item.c_str());
                return false;
            }
            const std::string t_text = item.substr(0, colon);
            double t = 0.0;
            try {
                size_t used = 0;
                t = std::stod(t_text, &used);
                if (used != t_text.size())
                    throw std::invalid_argument("tail");
            } catch (const std::exception &) {
                std::fprintf(stderr, "--script 里的时刻不是数字：%s\n", t_text.c_str());
                return false;
            }
            ctrl::State s;
            if (!ctrl::ParseState(item.substr(colon + 1), &s)) {
                std::fprintf(stderr, "--script 里的状态只能是 stand / damp：%s\n",
                             item.substr(colon + 1).c_str());
                return false;
            }
            out->emplace_back(t, s);
        }
        if (comma == std::string::npos)
            break;
        pos = comma + 1;
    }
    std::stable_sort(out->begin(), out->end(),
                     [](const auto &a, const auto &b) { return a.first < b.first; });
    return true;
}

// 把狗摆到 --start 指定的起点（搜索会改 qpos，所以每次复位都调用它）
bool SetStart(const mjModel *m, mjData *d, const std::string &start, const stance::Target &target) {
    if (start == "raw") {
        mj_resetData(m, d); // 模型原姿态：直立直腿、脚底刚好触地
    } else if (start == "stance") {
        if (!target.ok)
            return false;
        mj_resetData(m, d);
        for (int i = 0; i < m->nu; ++i)
            d->qpos[m->jnt_qposadr[m->actuator_trnid[2 * i]]] = target.q[static_cast<size_t>(i)];
        d->qpos[2] = target.z; // 搜索里算出来的基座高度
    } else if (start == "rest") {
        if (m->nkey == 0) {
            std::fprintf(stderr, "场景里没有 keyframe，无法用 --start rest\n");
            return false;
        }
        mj_resetDataKeyframe(m, d, 0); // 场景自带的趴卧姿态
    } else if (start == "side") {
        mj_resetData(m, d);
        // 侧躺：基座绕 x 轴转 90°、再抬高 0.25 m —— 用来验证"任意初始位置"
        const double s = std::sin(M_PI / 4.0), c = std::cos(M_PI / 4.0);
        d->qpos[3] = c;
        d->qpos[4] = s;
        d->qpos[5] = 0.0;
        d->qpos[6] = 0.0;
        d->qpos[2] += 0.25;
    } else {
        std::fprintf(stderr, "未知起点：%s\n", start.c_str());
        return false;
    }
    mj_forward(m, d);
    return true;
}

// 一行指标：四足触地数、基座高度、竖直度、水平位移、最大关节速度、最大力矩
struct Snapshot {
    double t = 0, z = 0, tilt = 0, xy = 0, qvel_max = 0, ctrl_max = 0;
    int feet = 0;
};

Snapshot Sample(const mjModel *m, const mjData *d, const std::vector<int> &feet, double ref_x,
                double ref_y) {
    Snapshot s;
    s.t = d->time;
    const stance::Metrics mm = stance::Measure(m, d, feet, ref_x, ref_y);
    s.feet = mm.feet;
    s.z = mm.z;
    s.tilt = mm.tilt_deg;
    s.xy = mm.xy;
    for (int v = 0; v < m->nv; ++v)
        s.qvel_max = std::max(s.qvel_max, std::fabs(d->qvel[v]));
    for (int a = 0; a < m->nu; ++a)
        s.ctrl_max = std::max(s.ctrl_max, std::fabs(d->ctrl[a]));
    return s;
}

void PrintSnapshot(const char *label, const Snapshot &s) {
    std::printf("%-22s t=%6.3f s  z=%.4f m  竖直度 %5.2f°  四足触地 %d  xy %.4f m  "
                "max|q̇| %.3f  max|τ| %.2f\n",
                label, s.t, s.z, s.tilt, s.feet, s.xy, s.qvel_max, s.ctrl_max);
}

// “起身完成” = 四足触地 + 高度到位 + 机身基本竖直。只看高度不行：从原姿态（基座 0.5786，
// 比站姿还高）刚开始键时它已经“比目标高”了，会误判成“0.00 s 就起身完成”。
bool StoodUp(const Snapshot &s, const stance::Target &target) {
    return s.feet == 4 && std::fabs(s.z - target.z) <= 0.03 && s.tilt <= 10.0;
}

void PrintMotorStats(const motor::JointMotors &motors) {
    const motor::JointMotors::Stats &st = motors.stats();
    std::printf("电机：累计 %ld 电机·步，撞限幅 %ld 次（%.3f%%），落死区 %ld 次，"
                "|τ| 峰值 %.2f N·m、均值 %.2f N·m（延迟 %d 周期）\n",
                st.steps, st.sat, 100.0 * static_cast<double>(st.sat) / std::max(1L, st.steps),
                st.dead, st.tau_peak, st.tau_mean_abs(), motors.delay_cycles());
}

} // namespace

int main(int argc, char **argv) {
    // 交互式运行（窗口模式）时日志要立刻可见：不重定向的话 stdout 是块缓冲，
    // 万一中途被 Ctrl-C/信号打断，缓冲区里的日志就全丢了。
    std::setvbuf(stdout, nullptr, _IOLBF, 0);
    const Args args = ParseArgs(argc, argv, kUsage, kOptionDefs, /*max_positional=*/1);

    Options opt;
    opt.mode = args.value("--mode", opt.mode);
    if (args.has("--mode") && opt.mode != "view" && opt.mode != "sim") {
        std::fprintf(stderr, "--mode 只能是 view / sim：%s\n%s", opt.mode.c_str(), kUsage);
        return 1;
    }
    if (!args.positional.empty())
        opt.scene = args.positional[0];
    opt.start = args.value("--start", opt.start);
    if (opt.start != "raw" && opt.start != "stance" && opt.start != "rest" && opt.start != "side") {
        std::fprintf(stderr, "--start 只能是 raw / stance / rest / side：%s\n%s", opt.start.c_str(),
                     kUsage);
        return 1;
    }
    opt.kp = args.number("--kp", opt.kp, kUsage);
    opt.kd = args.number("--kd", opt.kd, kUsage);
    opt.kd_damp = args.number("--kd-damp", opt.kd_damp, kUsage);
    if (args.has("--ramp")) { // auto = 默认：按按下那一刻的姿态选（见 state.h）
        const std::string v = args.value("--ramp");
        if (v == "auto") {
            opt.auto_ramp = true;
        } else {
            opt.auto_ramp = false;
            opt.ramp = Args::ParseNum(v, "--ramp", kUsage);
        }
    }
    opt.gravity_comp = args.has("--gravity-comp");
    opt.seconds = args.number("--seconds", opt.seconds, kUsage);
    opt.width = args.integer("--width", opt.width, kUsage);
    opt.height = args.integer("--height", opt.height, kUsage);
    opt.tau_max = args.number("--tau-max", opt.tau_max, kUsage);
    opt.deadzone = args.number("--deadzone", opt.deadzone, kUsage);
    opt.delay_cycles = args.integer("--delay-cycles", opt.delay_cycles, kUsage);
    opt.noise = args.number("--noise", opt.noise, kUsage);
    opt.gear = args.number("--gear", opt.gear, kUsage);
    if (opt.ramp < 0.0 || opt.kp < 0.0 || opt.kd < 0.0 || opt.kd_damp < 0.0 || opt.seconds <= 0.0 ||
        opt.tau_max < 0.0 || opt.deadzone < 0.0 || opt.delay_cycles < 0 || opt.noise < 0.0 ||
        opt.gear <= 0.0) {
        std::fprintf(stderr, "参数取值不合法（时长/增益/限幅等不能为负）：见用法\n%s", kUsage);
        return 1;
    }
    if (args.has("--script") && !ParseScript(args.value("--script"), &opt.script))
        return 1;

    // 固定路径：可执行文件应为 <任务目录>/cpp/build/motor_sim，往上两层就是任务目录
    const fs::path exe_dir = fs::read_symlink("/proc/self/exe").parent_path();
    const fs::path root = exe_dir.parent_path().parent_path();
    if (opt.scene.empty() && !fs::is_directory(root / "scenes")) {
        std::fprintf(stderr, "预期可执行文件在 <任务目录>/cpp/build/ 下，但 %s 里没有 scenes/\n",
                     root.c_str());
        std::fprintf(stderr, "请用第一个参数指定场景，或按 README 的构建命令重新构建。\n");
        return 1;
    }
    const fs::path scene = opt.scene.empty() ? root / "scenes/flat_scene.xml" : opt.scene;

    std::printf("MuJoCo %s\n", mj_versionString());
    if (mjVERSION_HEADER != mj_version()) {
        std::fprintf(stderr, "头文件与库版本不一致，终止\n");
        return 1;
    }
    std::printf("场景：%s\n", scene.c_str());

    mjModel *m = mj_loadXML(scene.c_str(), nullptr, nullptr, 0);
    if (m == nullptr) {
        std::fprintf(stderr, "加载场景失败：%s\n", scene.c_str());
        return 1;
    }
    mjData *d = mj_makeData(m);
    double mass = 0.0;
    for (int b = 1; b < m->nbody; ++b)
        mass += m->body_mass[b];
    std::printf("模型：nq=%ld nv=%ld nu=%ld dt=%g s；总质量 %.3f kg；执行器 ctrlrange ±%.0f N·m\n",
                static_cast<long>(m->nq), static_cast<long>(m->nv), static_cast<long>(m->nu),
                m->opt.timestep, mass, m->actuator_ctrlrange[1]);

    // 脚（4 个足底碰撞球）+ 站姿搜索
    double foot_radius = 0.0;
    const std::vector<int> feet = stance::FindFeet(m, &foot_radius);
    std::printf("脚：%zu 个足底碰撞球（半径 %.3f m）\n", feet.size(), foot_radius);
    if (feet.size() != 4) {
        std::fprintf(stderr, "没找到 4 个足底球，模型不对？\n");
        mj_deleteData(d);
        mj_deleteModel(m);
        return 1;
    }
    const stance::Target target = stance::Search(m, d, feet, foot_radius);
    if (!target.ok) {
        std::fprintf(stderr, "站姿搜索失败\n");
        mj_deleteData(d);
        mj_deleteModel(m);
        return 1;
    }
    std::printf("站姿（搜索得到，不读 keyframe）：膝 %.2f rad、大腿 %.2f×膝；基座 z=%.4f m、"
                "质心离四足中心 %.4f m、四足触地 %d\n",
                target.bend, target.frac, target.z, target.com_err, target.feet);

    if (!SetStart(m, d, opt.start, target)) {
        mj_deleteData(d);
        mj_deleteModel(m);
        return 1;
    }
    const double ref_x = d->qpos[0], ref_y = d->qpos[1]; // 水平位移的参考点 = 起点

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

    const Snapshot start_row = Sample(m, d, feet, ref_x, ref_y);
    PrintSnapshot("起点", start_row);

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
                    SetStart(m, d, opt.start, target); // 回到起点，重新演示
                    sm.Request(ctrl::State::Damping, d);
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
                    StoodUp(Sample(m, d, feet, ref_x, ref_y), target))
                    t_stand_done = d->time;
            }
            const Snapshot now = Sample(m, d, feet, ref_x, ref_y);
            // HUD 全用 ASCII：MuJoCo 内置位图字体不含中文/希腊字母，画出来是乱码块（终端日志仍用中文）
            char up[64] = "";
            if (sm.state() == ctrl::State::Standing && t_stand_done >= 0.0)
                std::snprintf(up, sizeof(up), "  (up in %.2f s, ramp %.2f s)",
                              t_stand_done - t_stand_start, sm.chosen_ramp());
            std::snprintf(hud_left, sizeof(hud_left),
                          "motor_sim  |  3rd training, part 1: joint-motor state machine\n"
                          "state: %s%s\n%s\n"
                          "S = stand   D = damp   R = reset   Q/Esc = quit",
                          ctrl::NameAscii(sm.state()), up, sm.last_event_ascii());
            std::snprintf(hud_right, sizeof(hud_right),
                          "t = %.2f s\nfeet on ground: %d\nbase z = %.4f m\ntilt = %.2f deg\n"
                          "switches: %d\n|tau| peak = %.1f N*m",
                          now.t, now.feet, now.z, now.tilt, sm.switches(),
                          motors.stats().tau_peak);
            win.Draw(m, d, hud_left, hud_right);
        }
        const Snapshot end = Sample(m, d, feet, ref_x, ref_y);
        PrintSnapshot("收工", end);
        std::printf("窗口：物理 %ld 步 / 仿真 %.3f s，状态切换 %d 次\n", steps, end.t,
                    sm.switches());
        PrintMotorStats(motors);
        if (t_stand_done >= 0.0)
            std::printf("起身：从按下站立键到 z 到位共用 %.2f s（斜坡 %.2f s，q_des 是连续的）\n",
                        t_stand_done - t_stand_start, sm.chosen_ramp());
        mj_deleteData(d);
        mj_deleteModel(m);
        return 0;
    }

    // ---------------------------------------------------------------- 无窗口模式（回归用）
    std::printf("只仿真：无窗口，全速跑 %.3f 仿真秒", opt.seconds);
    if (!opt.script.empty()) {
        std::printf("，脚本 ");
        for (const auto &e : opt.script)
            std::printf("%.2f s→%s ", e.first, ctrl::Name(e.second));
    }
    std::printf("\n");

    const auto t_start = std::chrono::steady_clock::now();
    size_t next_event = 0;
    long steps = 0;
    double t_stand_start = -1.0, t_stand_done = -1.0;
    while (d->time < opt.seconds - 1e-12) {
        while (next_event < opt.script.size() && d->time >= opt.script[next_event].first - 1e-12) {
            const Snapshot before = Sample(m, d, feet, ref_x, ref_y);
            PrintSnapshot(ctrl::Name(sm.state()), before); // 上一段的末态
            if (sm.state() == ctrl::State::Standing && t_stand_start >= 0.0)
                std::printf("    上一段（站立）：起身用时 %.2f s（斜坡 %.2f s）\n",
                            (t_stand_done >= 0.0 ? t_stand_done : before.t) - t_stand_start,
                            sm.chosen_ramp());
            if (sm.Request(opt.script[next_event].second, d)) {
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
            StoodUp(Sample(m, d, feet, ref_x, ref_y), target))
            t_stand_done = d->time;
    }
    const double wall_ms =
        std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t_start).count();

    const Snapshot end = Sample(m, d, feet, ref_x, ref_y);
    PrintSnapshot(ctrl::Name(sm.state()), end);
    std::printf("仿真 %.3f s（%ld 步，wall %.1f ms，单步 %.4f ms，%.1fx 实时）\n", end.t, steps,
                wall_ms, wall_ms / std::max(1L, steps), 1000.0 * end.t / std::max(1e-9, wall_ms));
    if (t_stand_done >= 0.0)
        std::printf("起身：从按下站立键到四足站定共用 %.2f s（斜坡 %.2f s，q_des 是连续的）\n",
                    t_stand_done - t_stand_start, sm.chosen_ramp());
    PrintMotorStats(motors);

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
    mj_deleteData(d);
    mj_deleteModel(m);
    return ok ? 0 : 2;
}
