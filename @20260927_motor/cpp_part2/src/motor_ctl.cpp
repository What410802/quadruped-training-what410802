// 实机 S3–S5（任务书第二部分第 2–4 条）：**回归 0 + 键盘给角度 + 零点标定 + 零点跳变处理**。
//
// 偏移的写法（讲义 §2.5；课程视频讲的是同一件事："对电机的输出加上偏移、对输入减去偏移"）：
//     q     = q_enc + offset          读回来的（板子报的）角度，**加上** offset
//     cmd.q = (q_des − offset) · N    要下发的目标，**减去** offset 再换到转子侧
// 两个方向必须反号：写成同号就是正反馈，一给目标就飞（推导见 ../docs/real.md §5.2）。
// 注意 `cmd.q / cmd.dq / cmd.kd` 都是**转子侧** —— 官方 SDK 不做换算，官方例程自己 `×N`
// （example/example_goM8010_6_motor.cpp 里的 `-6.28*queryGearRatio(...)` 就是证据）。
//
// 三件事：
//   S3 回归 0 + 键盘角度：`0` 回 0 位、输入数字（度）去那个角度；全程梯形插值（速度/加速度上限）
//   S4 标零点：`o+30` 把零点正向偏移 30°（验收：记号笔那个点从 0 变成 +30.00°，而输出端没动）；
//              改完 offset 后**同一个目标角**会落在记号笔那一点上（= 朝反方向少转 30°）
//   S5 零点跳变：每帧用**整数 raw 差**判"整圈跳变"（一个零点区间 = 转子 360° = raw 32768），
//              检测到就把 offset 反向补回同样的量（q_des 不变 ⇒ **物理目标不动**），并在日志里报出来
//
// "0 位"是**板子报的 0**：驱动板用单圈绝对值编码器（讲义 §2.4），上电时读数落在 0…1/6.33 圈内，
// 之后累计（S1 实测，见 ../docs/real.md §3.6）。所以：
//   * 会话内转了几圈，读数就攒到几百上千度 —— `0` 会是一次**多圈**行程（程序会先打印预计时间）；
//   * 掉电再上电，读数可能换一个候选零点当基准（"认错零点"，讲义 §2.6）—— 用 `--expect-deg`
//     或运行时的 `expect` 与记号笔那个点对照，差 ≈1 个区间就用 `fix` 修回来。
//
// 编译与运行见 ../README.md §6；实机执行手册见 ../docs/real.md §3.8。
//
// 退出码：0 正常；1 参数错；2 打不开串口；3 一帧回复都没收到；4 电机报错/温度高；5 中途掉线；
//         7 零点跳变修正次数用尽（停下来检查）。

#include <cstdint>
#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cmath>
#include <algorithm>
#include <string>
#include <vector>

#include <chrono>
#include <unistd.h>

#include <atomic>
#include <mutex>
#include <thread>

#include "serialPort/SerialPort.h"
#include "unitreeMotor/unitreeMotor.h"

#include "sim/fake_motor.h"   // 只在 --self-test 里用到（src/sim/ = 不控制实机的代码）

namespace {

constexpr double kDt = 0.005;                  // 名义 5 ms/帧（实测约 5.6 ms，见 README §4）
constexpr double kDegToRad = M_PI / 180.0;
constexpr int64_t kRawPerTurn = 32768;         // pos 是 int32 q15 圈（转子侧）⇒ 一个转子圈 = 32768

struct Options {
    std::string port = "/dev/ttyUSB0";
    int id = 0;
    int baud = 4000000;
    double kp_out = 80.0;         // 输出端位置刚度 [N·m/rad]（讲义那组 80/3；下发时 ÷N²）
    double kd_out = 3.0;          // 输出端阻尼（同上）
    double tau_out_limit = 1.5;   // 输出端力矩上限 [N·m]：**持续**超过它 = 卡住/顶住，才报错退出
    double stall_s = 1.0;         // 超过上限持续这么多秒 ⇒ 判定卡住，卸力退出
    double vmax_deg = 90.0;       // 插值速度上限 [°/s]（输出端）
    double amax_deg = 180.0;      // 插值加速度上限 [°/s²]
    double tol_deg = 1.0;         // 到位判据 [°]
    double offset_deg = 0.0;      // 上电时的 offset（标定结果；S4 就是把它 +30）
    double expect_deg = 0.0;      // 启动检查：**板子读数 q_enc** 应等于这个值（0 也是合法期望）
    bool expect_set = false;      // 给过 --expect-deg 没有（不能用 0 当"没给"）
    double expect_tol_deg = 3.0;
    double jump_tol_deg = 8.0;    // 判"整圈跳变"的残差容差（输出端 °）。为什么要留这么大：跳变那一帧
                                  // 驱动板自己也会因为位置环而"抡"一下（实测单帧能多走 ~3°），而且
                                  // 半间隔是 28.4° —— 8° 离两边都远，既不会漏判也不会把正常步进当跳变
    int max_fixes = 3;            // 一次会话最多自动修正几次零点跳变
    bool set_zero_read = false;   // 把启动位置定义成 0（offset = −q_enc）——0 位放到区间中部，避开边界
    bool fix_startup = true;      // 启动检查发现差 ≈1 个区间时自动修正 offset（--no-fix-startup 关掉）
    bool no_send = false;
    int every = 20;               // 每 N 帧打印一行状态
    bool self_test = false;
    std::string script;           // 非交互：用 ';' 分隔的一串键盘命令，逐条执行
    double script_step = 2.0;     // 每条命令之间等多少秒（留给电机转）
    double settle = 0.5;          // 脚本跑完后再等这么多秒，才允许退出
    double seconds = 0.0;         // >0：跑这么多秒就自动收尾退出（非交互/CI 用，避免一直挂着）

    // --self-test 专用的"驱动板"注入（见 src/sim/fake_motor.h 的 Encoder）
    int fake_datum_turns = 0;     // 上电基准平移 k 个转子整圈 = 认错零点
    bool fake_sawtooth = false;   // 板子只报"相对最近零点"的角度（讲义 §2.4）
    long fake_jump_frame = -1;    // 第 N 帧注入一次中途换基准
    int fake_jump_turns = 1;
};

void Usage(const char *prog) {
    std::printf(
        "用法：%s [--port /dev/ttyUSB0] [--id N] [--offset-deg D] [--script \"...\"] [--self-test]\n"
        "  --port/--id/--baud   串口、电机 ID、波特率（默认 /dev/ttyUSB0、0、4000000；实机要 sudo）\n"
        "  --kp-out/--kd-out    输出端增益（默认 80 / 3；下发时 ÷N²）\n"
        "  --tau-out-limit      输出端力矩上限 [N·m]（默认 1.5）：**持续**超过 --stall-s 秒 = 卡住，卸力退出\n"
        "  --stall-s            上面的“持续”是多久（默认 1.0 s）\n"
        "  --vmax-deg/--amax-deg/--tol-deg   插值速度、加速度上限与到位判据（默认 90°/s、180°/s²、1°）\n"
        "  --offset-deg         offset 初值（默认 0；S4 的标定结果放这里，可存档）\n"
        "  --set-zero-read      把“启动时那个位置”定义成 0（offset = −q_enc）：0 位落在区间中部，\n"
        "                       避开“上电认错零点”最容易发生的零点边界（讲义 §2.6）\n"
        "  --expect-deg D       启动检查：**q** 应 ≈ D 度（记号笔那个点 mark 出来的 q 值；offset 要用同一个），\n"
        "                       差 ≈1 个零点区间就报警并按 fix 的规则自动修（--no-fix-startup 只报警）\n"
        "  --no-send            只打印配置，不打开串口、不发字节\n"
        "  --script \"a;b;c\"     非交互执行命令（每条之间等 --script-step 秒，默认 2 s；最后再稳 --settle 秒）\n"
        "  --seconds SEC        跑 SEC 秒后自动收尾退出（默认 0 = 一直跑；非交互场景建议给一个）\n"
        "  --self-test          无硬件自检：PTY + 假电机（要 LD_PRELOAD 垫片，见 README §3）\n"
        "  --fake-datum-turns N / --fake-sawtooth / --fake-jump-frame N [--fake-jump-turns K]\n"
        "                       自检时给“驱动板”注入：认错零点 / 锯齿读数 / 中途换基准\n"
        "\n键盘命令（交互；--script 用同样的字符串，以 ';' 分隔）：\n"
        "  0               回 0 位（插值慢慢转）\n"
        "  <数字>          去那个角度，单位度（30 / -45 / 180 …）\n"
        "  travel <数字>   本会话相对“现在”再多转 D 度（找记号笔位置用；与 mark 配合）\n"
        "  mark / m        把“此刻读数”记成记号笔那个点（S4 的验收基准就是它）\n"
        "  goto-mark       转到记号笔那个点（第 4 条“把输出端转到零点附近”用）\n"
        "  o+30 / o-30     把 offset 加/减 30°（S4 的“零点正向偏移 30°”）\n"
        "  o 30            把 offset 直接设成 30°\n"
        "  expect          与记号笔那个点对照（没 mark 过就与 0° 比），看零点有没有跳变（差 ≈1 个区间就是跳了）\n"
        "  fix             按上面的建议修正 offset（只改 offset：q 连续、物理目标不动）\n"
        "  hold / stop     位置保持（kp/kd）/ 立刻零力矩卸力\n"
        "  p               打印状态；h 帮助；q / quit / exit  先卸力再退出\n",
        prog);
}

bool Parse(int argc, char **argv, Options *o) {
    for (int i = 1; i < argc; ++i) {
        const std::string a = argv[i];
        const bool next = i + 1 < argc;
        if (a == "--help" || a == "-h")
            return false;
        else if (a == "--no-send")
            o->no_send = true;
        else if (a == "--self-test")
            o->self_test = true;
        else if (a == "--set-zero-read")
            o->set_zero_read = true;
        else if (a == "--no-fix-startup")
            o->fix_startup = false;
        else if (a == "--fake-sawtooth")
            o->fake_sawtooth = true;
        else if (a == "--port" && next)
            o->port = argv[++i];
        else if (a == "--id" && next)
            o->id = std::atoi(argv[++i]);
        else if (a == "--baud" && next)
            o->baud = std::atoi(argv[++i]);
        else if (a == "--kp-out" && next)
            o->kp_out = std::atof(argv[++i]);
        else if (a == "--kd-out" && next)
            o->kd_out = std::atof(argv[++i]);
        else if (a == "--tau-out-limit" && next)
            o->tau_out_limit = std::atof(argv[++i]);
        else if (a == "--stall-s" && next)
            o->stall_s = std::atof(argv[++i]);
        else if (a == "--vmax-deg" && next)
            o->vmax_deg = std::atof(argv[++i]);
        else if (a == "--amax-deg" && next)
            o->amax_deg = std::atof(argv[++i]);
        else if (a == "--tol-deg" && next)
            o->tol_deg = std::atof(argv[++i]);
        else if (a == "--offset-deg" && next)
            o->offset_deg = std::atof(argv[++i]);
        else if (a == "--expect-deg" && next) {
            o->expect_deg = std::atof(argv[++i]);
            o->expect_set = true;
        }
        else if (a == "--expect-tol-deg" && next)
            o->expect_tol_deg = std::atof(argv[++i]);
        else if (a == "--jump-tol-deg" && next)
            o->jump_tol_deg = std::atof(argv[++i]);
        else if (a == "--max-fixes" && next)
            o->max_fixes = std::atoi(argv[++i]);
        else if (a == "--script" && next)
            o->script = argv[++i];
        else if (a == "--script-step" && next)
            o->script_step = std::atof(argv[++i]);
        else if (a == "--settle" && next)
            o->settle = std::atof(argv[++i]);
        else if (a == "--seconds" && next)
            o->seconds = std::atof(argv[++i]);
        else if (a == "--fake-datum-turns" && next)
            o->fake_datum_turns = std::atoi(argv[++i]);
        else if (a == "--fake-jump-frame" && next)
            o->fake_jump_frame = std::atol(argv[++i]);
        else if (a == "--fake-jump-turns" && next)
            o->fake_jump_turns = std::atoi(argv[++i]);
        else if (a == "--every" && next)
            o->every = std::max(1, std::atoi(argv[++i]));
        else {
            std::fprintf(stderr, "未知参数：%s\n", a.c_str());
            return false;
        }
    }
    if (o->kp_out < 0.0 || o->kd_out < 0.0) {
        std::fprintf(stderr, "--kp-out/--kd-out 不能为负\n");
        return false;
    }
    if (o->vmax_deg <= 0.0 || o->amax_deg <= 0.0) {
        std::fprintf(stderr, "--vmax-deg/--amax-deg 必须为正\n");
        return false;
    }
    if (o->tau_out_limit <= 0.0) {
        std::fprintf(stderr, "--tau-out-limit 必须为正（保护靠它兜底）\n");
        return false;
    }
    if (o->script_step <= 0.0) {
        std::fprintf(stderr, "--script-step 必须为正\n");
        return false;
    }
    return true;
}

const char *kHelp =
    "命令：0 = 回 0 位；<数字> = 去那个角度（度）；travel D = 相对现在多转 D 度；mark/m = 记记号笔位置；\n"
    "      goto-mark = 转到记号笔位置；o+30 / o-30 / o 30 = 改 offset；expect = 查零点跳变；\n"
    "      fix = 按建议修正；hold/stop = 位置保持/零力矩；p = 状态；h = 本帮助；q = 卸力退出\n";

} // namespace

int main(int argc, char **argv) {
    Options opt;
    if (!Parse(argc, argv, &opt)) {
        Usage(argv[0]);
        return 1;
    }

    const double N = queryGearRatio(MotorType::GO_M8010_6);   // 6.33
    const double zone_deg = 360.0 / N;                        // 一个零点区间（输出端）= 56.872°
    const double zone_rad = zone_deg * kDegToRad;
    const double kp_rotor = opt.kp_out / (N * N);             // 下发用（转子侧）
    const double kd_rotor = opt.kd_out / (N * N);
    const double tau_rotor_limit = opt.tau_out_limit / N;     // 转子侧力矩上限

    std::printf("=== S3–S5：回归 0 / 键盘给角度 / 零点标定 / 零点跳变处理 ===\n");
    std::printf("GO-M8010-6：N = %.4f ⇒ 一个零点区间 = %.4f°（输出端）= 转子 360°；FOC 模式号 %d\n",
                N, zone_deg, queryMotorMode(MotorType::GO_M8010_6, MotorMode::FOC));
    std::printf("增益：输出端 kp=%.3g kd=%.3g → 转子侧 K_P=%.4f K_W=%.5f；力矩上限 %.3f N·m（输出端）"
                "→ tor_des=%d（转子侧 raw）；插值 vmax=%.0f°/s、amax=%.0f°/s²、到位判据 %.2f°\n",
                opt.kp_out, opt.kd_out, kp_rotor, kd_rotor, opt.tau_out_limit,
                static_cast<int>(std::lround(tau_rotor_limit * 256.0)), opt.vmax_deg, opt.amax_deg,
                opt.tol_deg);
    std::printf("偏移写法（讲义 §2.5）：q = q_enc + offset（收到加）、cmd.q = (q_des − offset)·N（下发减）；"
                "offset 初值 %+.3f°\n",
                opt.offset_deg);
    std::printf("跳变判据：整数 pos 差 ≈ k×32768（= k 个转子圈 = k×%.3f° 输出端），残差 ≤ %.2f° ⇒ "
                "offset 反向补回去（物理目标不动）；一次会话最多修 %d 次\n",
                zone_deg, opt.jump_tol_deg, opt.max_fixes);

    if (opt.no_send) {
        std::printf("--no-send：到此为止，没有打开串口、没有发任何字节。\n");
        return 0;
    }

    // ---------- 打开串口（实机 / 自检） ----------
    SerialPort *serial = nullptr;
    std::thread fake_motor;
    std::atomic<bool> fake_stop{false};
    try {
        if (opt.self_test) {
            int master = -1;
            const std::string slave = fakemotor::MakePty(&master);
            if (slave.empty())
                return 1;
            fakemotor::Model model;
            model.enc.mode = opt.fake_sawtooth ? 1 : 0;
            model.enc.datum = opt.fake_datum_turns;
            model.enc.jump_frame = opt.fake_jump_frame;
            model.enc.jump_turns = opt.fake_jump_turns;
            std::printf("自检：PTY slave=%s（假电机在另一头：读数形态=%s、上电基准 %+d 个转子圈%s）\n",
                        slave.c_str(), model.enc.mode == 1 ? "锯齿" : "里程计", model.enc.datum,
                        opt.fake_jump_frame > 0 ? "、注入一次中途换基准" : "");
            fake_motor = fakemotor::Start(master, &fake_stop, model);
            serial = new SerialPort(slave, 16, opt.baud);
        } else {
            serial = new SerialPort(opt.port, 16, opt.baud);
        }
    } catch (const std::exception &e) {
        std::printf("**SerialPort 构造失败**：%s\n", e.what());
        if (fake_motor.joinable()) {
            fake_stop = true;
            fake_motor.join();
        }
        return 2;
    }
    std::printf("串口已打开（%s）\n", opt.self_test ? "自检 PTY" : opt.port.c_str());

    MotorCmd cmd;
    MotorData data;
    cmd.motorType = MotorType::GO_M8010_6;
    data.motorType = MotorType::GO_M8010_6;
    cmd.mode = queryMotorMode(MotorType::GO_M8010_6, MotorMode::FOC);
    cmd.id = opt.id;
    cmd.q = 0.0f;
    cmd.dq = 0.0f;
    cmd.tau = 0.0f;

    // ---------- 状态 ----------
    double offset = opt.offset_deg * kDegToRad;  // 唯一的 offset（收到加、下发减）
    double q_cmd = 0.0;                          // 插值出来的"当前命令角度"（q 空间）
    double q_target = 0.0;                       // 目标（q 空间）
    bool hold_torque = true;                     // true = 位置保持；false = 零力矩（卸力）
    bool have_mark = false;
    double mark_q = 0.0;                         // 记号笔那个点在**我们的 q 空间**的坐标
    double mark_enc = 0.0;                       // 记号笔那个点的**板子读数**（q_enc）——与 offset 无关，
                                                 // 所以它才是"跨界会话也不变"的锚点：上电时用它查跳变
    bool have_prev_raw = false;
    int64_t prev_raw = 0;
    int fixes = 0;
    int cmd_seq = 0;
    double q_first = 0.0, last_q = 0.0, q_min = 1e9, q_max = -1e9;
    double tau_peak = 0.0, tau_hold_max = 0.0, travel_planned = 0.0;
    double v_plan = 0.0;                         // 梯形速度曲线里的"当前计划速度"
    int temp_max = -128;
    unsigned merror_last = 0;
    double tau_over_since = -1.0;                // 力矩超过上限是从什么时候开始的
    int frames = 0, ok_frames = 0, timeouts = 0, timeout_streak = 0;
    double last_send_wall = 0.0;

    // ---------- 键盘（线程读 stdin，主循环消费；与 serial_probe 同一套写法） ----------
    std::mutex mu;
    std::vector<std::string> pending;
    std::atomic<bool> quit{false};
    const auto wall0 = std::chrono::steady_clock::now();
    const auto wall_now = [&wall0] {
        return std::chrono::duration<double>(std::chrono::steady_clock::now() - wall0).count();
    };
    if (!opt.script.empty()) {
        std::string rest = opt.script;
        while (!rest.empty()) {
            const size_t pos = rest.find(';');
            const std::string tok = rest.substr(0, pos);
            rest = pos == std::string::npos ? std::string() : rest.substr(pos + 1);
            if (tok.find_first_not_of(" \t") != std::string::npos)
                pending.push_back(tok);
        }
        std::printf("--script：共 %zu 条命令（每条间隔 %.1f s）：%s\n", pending.size(), opt.script_step,
                    opt.script.c_str());
    } else if (::isatty(0)) {
        std::printf("键盘就绪（h = 帮助）：0 回 0 位、数字 = 目标角度、o+30 = 零点正向偏移、mark = 记记号笔、"
                    "goto-mark = 去记号笔、expect = 查跳变、q = 退出\n");
        std::thread([&mu, &pending] {
            char buf[512];
            std::string carry;
            while (true) {
                const ssize_t n = ::read(0, buf, sizeof(buf));
                if (n <= 0)
                    break;
                carry.append(buf, static_cast<size_t>(n));
                size_t pos;
                while ((pos = carry.find('\n')) != std::string::npos) {
                    std::string line = carry.substr(0, pos);
                    carry.erase(0, pos + 1);
                    {
                        std::lock_guard<std::mutex> lk(mu);
                        pending.push_back(line);
                    }
                }
            }
        }).detach();
    } else {
        std::printf("stdin 不是终端、也没给 --script：只能靠 --expect-deg 做启动检查，之后会一直保持不动。\n");
    }

    // ---------- 改 offset 的"安全动作" ----------
    // offset 一变，同样的 q 对应的**物理**目标就变了（cmd.q = (q_des − offset)·N）。要让电机不动，
    // 必须把 q 空间的三个量（插值中的 q_cmd、目标 q_target、记号笔坐标 mark_q）**同一帧**一起挪同样的量：
    // offset 与 q 同向挪 ⇒ (q_des − offset) 不变 ⇒ 物理目标不变。反过来只改一半就会让驱动板"跳"一下
    // （dry run 实测过一次：只挪目标不挪 q_cmd，力矩峰值冲到 41.8 N·m）。
    const auto shift_q = [&](double d) {
        if (d == 0.0)
            return;
        q_cmd += d;
        q_target += d;
        if (have_mark)
            mark_q += d;
    };

    // 跳变检测与修正（S5）：板子的读数跳了 k 个零点区间（读数是**先**跳的，物理位置没变）。
    // 只做一件事：把 offset 反向补 k 个区间。为什么这样就够（而且必须**只**做这一件）：
    //   报文里的目标 = q_des − offset；offset 少 k 个区间 ⇒ 目标读数自动多 k 个区间，
    //   正好抵消板子基准的漂移 ⇒ **同一个 q_des 仍然对应同一个物理位置，电机不会去别的地方**。
    //   同时 q = q_enc + offset 在这一帧是连续的（跳多少补多少），所以目标/记号笔都不用动。
    //   反过来"顺手挪一下 q_des/q_cmd"就错了：那等于把物理目标整体挪一个区间（dry run 里实测过）。
    const auto apply_jump_fix = [&](double k, const char *why) {
        const double before = offset;
        offset -= k * zone_rad;
        v_plan = 0.0;   // 当成一次扰动：插值从当前速度重新起步（目标不变）
        ++fixes;
        std::printf("    修正（%s）：offset %+.3f° → %+.3f°（%+.0f 个区间 = %+.3f°）；q 连续、"
                    "q_des 不动 ⇒ 物理目标没变（%d/%d 次）\n",
                    why, before / kDegToRad, offset / kDegToRad, -k, -k * zone_deg, fixes, opt.max_fixes);
    };

    const auto send_frame = [&](double q_out, double dq_out) {
        cmd.q = static_cast<float>((q_out - offset) * N);
        cmd.dq = static_cast<float>(dq_out * N);
        cmd.kp = static_cast<float>(hold_torque ? kp_rotor : 0.0);
        cmd.kd = static_cast<float>(hold_torque ? kd_rotor : 0.0);
        cmd.tau = 0.0f;
        last_send_wall = wall_now();
        return serial->sendRecv(&cmd, &data);
    };
    MotorCmd zero = cmd;
    zero.kp = zero.kd = zero.q = zero.dq = zero.tau = 0.0f;   // 五个量全 0 = 零力矩（自由可拖动）

    // ---------- 启动：零力矩先读一帧，确定"我在哪" ----------
    {
        bool ok = false;
        for (int i = 0; i < 3 && !ok; ++i) {
            ok = serial->sendRecv(&zero, &data);
            if (!ok)
                usleep(20000);
        }
        if (!ok) {
            std::printf("启动时零力矩读一帧就失败：检查 ID（--id）、接线（TX/RX/共地）、供电、权限。\n");
            delete serial;
            if (fake_motor.joinable()) {
                fake_stop = true;
                fake_motor.join();
            }
            return 3;
        }
        prev_raw = static_cast<int64_t>(std::llround(data.q * 32768.0 / (2.0 * M_PI)));
        have_prev_raw = true;
        last_q = data.q / N + offset;
        q_first = last_q;
        const double q_enc_0 = data.q / N;
        std::printf("启动读数：q_enc %+.3f°（第 %d 区、区内 %+.3f°）、offset %+.3f° → q %+.3f°；"
                    "pos raw %lld\n",
                    q_enc_0 / kDegToRad, static_cast<int>(std::floor(q_enc_0 / zone_rad)),
                    q_enc_0 / kDegToRad - std::floor(q_enc_0 / zone_rad) * zone_deg,
                    offset / kDegToRad, last_q / kDegToRad, static_cast<long long>(prev_raw));
        if (opt.set_zero_read) {
            const double enc_deg = q_enc_0 / kDegToRad;
            const double in_zone = std::fmod(enc_deg + zone_deg, zone_deg);
            std::printf("--set-zero-read：把此刻定义成 0 ⇒ offset = %+.3f°（q_enc 原本 %+.3f°）。"
                        "0 位就落在这里，离候选零点边界 %.3f°\n",
                        -enc_deg, enc_deg, std::min(in_zone, zone_deg - in_zone));
            offset = -q_enc_0;
            last_q = 0.0;
        }
        q_cmd = q_target = last_q;   // 先把"当前位置"当成目标：不给目标就不会动

        if (opt.expect_set) {
            // 比 q（和记号笔那个点的记录值同一个空间）；q_enc 一起打出来，方便跨会话抄录
            const double d = (last_q - opt.expect_deg * kDegToRad) / kDegToRad;
            const double k = std::round(d / zone_deg);
            std::printf("★ 启动检查：q %+.3f°（板子读数 q_enc %+.3f°），记录值 %+.3f°（差 %+.3f°）。",
                        last_q / kDegToRad, (last_q - offset) / kDegToRad, opt.expect_deg, d);
            if (std::fabs(d) <= opt.expect_tol_deg) {
                std::printf("在容差 %.2f° 内 ⇒ **零点没跳变**，可以继续。\n", opt.expect_tol_deg);
            } else if (k != 0.0 && std::fabs(d - k * zone_deg) <= opt.jump_tol_deg) {
                std::printf("差了 %+.0f 个零点区间（%+.3f° ≈ %+.0f×%.3f°）⇒ **疑似上电认错零点**"
                            "（讲义 §2.6）。\n", k, d, k, zone_deg);
                if (opt.fix_startup) {
                    std::printf("   自动修正：\n");
                    apply_jump_fix(k, "启动检查");
                    last_q = q_enc_0 + offset;   // 板子读数没变，变的是它对应的 q
                    q_cmd = q_target = last_q;   // 启动阶段：把"当前位置"当目标，电机不动
                    std::printf("   板子读数仍是 %+.3f°（物理位置没动），但现在它对应 q %+.3f°；"
                                "目标已同步到当前位置，电机不会动。不想自动修就加 --no-fix-startup。\n",
                                q_enc_0 / kDegToRad, last_q / kDegToRad);
                } else {
                    std::printf("   没有自动修（去掉 --no-fix-startup，或运行时 fix）。\n");
                }
            } else {
                std::printf("既不是容差内、也不是整数个区间 ⇒ **先别动电机**：手转回去对记号、查接线。\n");
            }
        }
    }

    // ---------- 状态行（`p` 命令与"到位/周期性打印"共用） ----------
    const auto print_status = [&]() {
        const double q_enc = last_q - offset;
        const double zone = std::floor(q_enc / zone_rad);
        const double in_zone = q_enc / kDegToRad - zone * zone_deg;
        char mark[80];
        if (have_mark)
            std::snprintf(mark, sizeof(mark), "记号笔 q %+.3f°（q_enc %+.3f°）", mark_q / kDegToRad,
                          mark_enc / kDegToRad);
        else
            std::snprintf(mark, sizeof(mark), "未记记号笔（用 mark）");
        std::printf("状态：q_enc %+9.3f°（第 %d 区、区内 %+7.3f°） offset %+8.3f° → q %+9.3f°；"
                    "目标 %+9.3f°（差 %+7.3f°）、插值位置 %+9.3f°；%s；%s\n",
                    q_enc / kDegToRad, static_cast<int>(zone), in_zone, offset / kDegToRad,
                    last_q / kDegToRad, q_target / kDegToRad, (q_target - last_q) / kDegToRad,
                    q_cmd / kDegToRad, hold_torque ? "位置保持" : "**零力矩（卸力）**", mark);
        std::printf("      帧 %d（收到 %d）、零点跳变修正 %d 次、力矩峰值 %.3f N·m、温度峰值 %d °C\n",
                    frames, ok_frames, fixes, tau_peak, temp_max);
    };

    // ---------- 主循环 ----------
    const int every = opt.every;
    double script_next_cmd = 0.0;      // 脚本模式：下一条命令最早的发射时刻
    double script_last = 0.0;          // 脚本模式：最后一条命令发出的时刻
    bool script_last_set = false;
    double arrived_since = -1.0;
    bool arrived_printed = false;
    int exit_code = 0;

    for (int frame = 1;; ++frame) {
        const double now = wall_now();

        // ---- 1. 取一条键盘/脚本命令 ----
        std::string c;
        {
            std::lock_guard<std::mutex> lk(mu);
            const bool allowed = opt.script.empty() || now >= script_next_cmd;
            if (allowed && !pending.empty()) {
                c = pending.front();
                pending.erase(pending.begin());
                if (!opt.script.empty()) {
                    script_next_cmd = now + opt.script_step;
                    script_last = now;
                    script_last_set = true;
                }
            }
        }
        if (!c.empty()) {
            while (!c.empty() && (c[0] == ' ' || c[0] == '\t'))
                c.erase(0, 1);
            while (!c.empty() && (c.back() == ' ' || c.back() == '\r'))
                c.pop_back();
            std::printf("命令#%d：\"%s\"\n", ++cmd_seq, c.c_str());
            const double before_target = q_target;
            if (c == "h" || c == "help" || c == "?") {
                std::printf("%s", kHelp);
            } else if (c == "p" || c == "print") {
                print_status();
            } else if (c == "hold") {
                hold_torque = true;
                q_cmd = q_target = last_q;
                travel_planned = 0.0;
                std::printf("回到位置保持（kp=%.3g kd=%.3g 输出端），目标 = 当前位置 %+.3f°\n",
                            opt.kp_out, opt.kd_out, last_q / kDegToRad);
            } else if (c == "stop" || c == "free") {
                hold_torque = false;
                std::printf("**零力矩（卸力）**：电机自由、可手转；用 hold 回到位置保持\n");
            } else if (c == "q" || c == "quit" || c == "exit") {
                std::printf("退出：先发零力矩，然后再退。\n");
                quit = true;
            } else if (c == "m" || c == "mark") {
                mark_q = last_q;
                mark_enc = last_q - offset;     // = q_enc，与 offset 无关（跨会话的锚点）
                have_mark = true;
                const double in_zone = std::fmod(mark_enc / kDegToRad + zone_deg, zone_deg);
                std::printf("MARK：记号笔那个点 = q %+.3f°、板子读数 q_enc %+.3f°（区内 %+.3f°）。"
                            "★ 把它抄下来：上电检查用 q_enc\n",
                            mark_q / kDegToRad, mark_enc / kDegToRad, in_zone);
                if (std::min(in_zone, zone_deg - in_zone) < 10.0)
                    std::printf("    ⚠ 这个点离候选零点边界只有 %.2f°：上电最容易“认错零点”。"
                                "用 --set-zero-read 把 0 位放到别处，或者实验时都把电机停在这里\n",
                                std::min(in_zone, zone_deg - in_zone));
            } else if (c == "goto-mark" || c == "gm") {
                if (!have_mark) {
                    std::printf("还没记过记号笔位置：先 mark。\n");
                } else {
                    q_target = mark_q;
                    std::printf("去记号笔那个点：目标 %+.3f°（第 4 条“把输出端转到零点附近”就用它）\n",
                                mark_q / kDegToRad);
                }
            } else if (c == "expect") {
                const double want = have_mark ? mark_q : 0.0;   // 比 q（记号笔那个点）；q_enc 也一起打出来
                const double q_enc_now = last_q - offset;
                const double d = (last_q - want) / kDegToRad;
                const double k = std::round(d / zone_deg);
                std::printf("对照（q 空间）：现在 %+.3f°、记录值 %+.3f°（差 %+.3f°）；"
                            "板子读数 q_enc %+.3f°", last_q / kDegToRad, want / kDegToRad, d,
                            q_enc_now / kDegToRad);
                if (std::fabs(d) <= opt.expect_tol_deg)
                    std::printf(" ⇒ ≈0，**零点没跳变**。\n");
                else if (k != 0.0 && std::fabs(d - k * zone_deg) <= opt.jump_tol_deg)
                    std::printf(" ⇒ 差了 %+.0f 个区间（≈%+.3f°），**疑似认错零点**：用 fix 修。\n", k,
                                k * zone_deg);
                else
                    std::printf(" ⇒ 既不是 0 也不是整数个区间：先别动电机（也可能是位置被手动挪过）。\n");
            } else if (c == "fix") {
                const double want = have_mark ? mark_q : 0.0;
                const double d = (last_q - want) / kDegToRad;
                const double k = std::round(d / zone_deg);
                if (k == 0.0 || std::fabs(d - k * zone_deg) > opt.jump_tol_deg) {
                    std::printf("与记录值相差 %+.3f°，不是整数个区间 ⇒ fix 不动"
                                "（先确认电机停在记号笔那个位置、或者先 mark）\n", d);
                } else {
                    const double q_enc_now = last_q - offset;   // 修正前那个板子读数
                    apply_jump_fix(-k, "fix 命令");
                    last_q = q_enc_now + offset;   // 同一个板子读数、用新 offset 解释 ⇒ q 回到记录值
                    std::printf("    记号笔那个点读 %+.3f°（S4 验收：+30 之后这里应该是 +30.00°）；"
                                "电机没动\n",
                                mark_q / kDegToRad);
                }
            } else if (c.size() > 1 && c[0] == 'o' && (c[1] == '+' || c[1] == '-' || c[1] == ' ')) {
                const double d = std::atof(c.c_str() + 1);
                const double old_offset = offset;
                if (c[1] == ' ')
                    offset = d * kDegToRad;
                else
                    offset += (c[1] == '+' ? d : -d) * kDegToRad;
                const double delta = offset - old_offset;
                std::printf("offset %+.3f° → %+.3f°（收到加、下发减；差 %+.3f°）\n", old_offset / kDegToRad,
                            offset / kDegToRad, delta / kDegToRad);
                if (hold_torque)
                    shift_q(delta);
                if (have_mark)
                    std::printf("    q 空间同步挪 %+.3f°（物理目标不动）；记号笔那个点现在读 %+.3f°"
                                "（先 mark 在 0 位的话，这里就应该是 +30.00°）\n",
                                delta / kDegToRad, mark_q / kDegToRad);
            } else if (c.size() > 7 && c.compare(0, 7, "travel ") == 0) {
                const double d = std::atof(c.c_str() + 7);
                q_target = last_q + d * kDegToRad;
                std::printf("本会话相对“现在”再转 %.2f° ⇒ 目标 %+.3f°（找记号笔位置用；"
                            "对准之后请 mark）\n", d, q_target / kDegToRad);
            } else if (std::isdigit(static_cast<unsigned char>(c[0])) || c[0] == '-' || c[0] == '+' ||
                       c[0] == '.') {
                q_target = std::atof(c.c_str()) * kDegToRad;
            } else {
                std::printf("没看懂：\"%s\"（h 看帮助）\n", c.c_str());
            }
            if (std::fabs(q_target - before_target) > 1e-12 && c != "fix")
                travel_planned += std::fabs(q_target - before_target);
            if (std::fabs(q_target - last_q) > opt.tol_deg * kDegToRad && c != "hold" && c != "stop") {
                const double travel = (q_target - last_q) / kDegToRad;
                std::printf("   目标 %+.3f°（现在 %+.3f°）：要转 %+.2f° ≈ %.2f 圈输出端 ≈ %.2f 圈转子，"
                            "按 vmax=%.0f°/s 直线时间 %.1f s\n",
                            q_target / kDegToRad, last_q / kDegToRad, travel, travel / 360.0,
                            travel / 360.0 * N, opt.vmax_deg, std::fabs(travel) / opt.vmax_deg);
                if (std::fabs(travel) > 360.0)
                    std::printf("   ⚠ 这是一次多圈行程（读数是从上电起累计的）：确认输出端能自由转、周围没人\n");
            }
        }
        if (quit)
            break;

        // ---- 2. 插值：梯形速度曲线（加/减速受 amax 限制、最高 vmax），一步一步走向 q_target ----
        {
            const double err = q_target - q_cmd;
            const double a_step = opt.amax_deg * kDegToRad * kDt;      // 每帧允许的速度变化
            if (std::fabs(err) <= 1e-12) {
                v_plan = 0.0;
            } else {
                // 该踩的最高速度：v² = 2·a·|Δ|（这样才煞得住）；先取方向，再按斜坡逼近
                const double v_cap = std::min(std::sqrt(2.0 * opt.amax_deg * kDegToRad * std::fabs(err)),
                                              opt.vmax_deg * kDegToRad);
                const double v_want = (err > 0.0) ? v_cap : -v_cap;
                if (std::fabs(v_want - v_plan) <= a_step)
                    v_plan = v_want;                                    // 这条边已经走完（加速段/减速段交接）
                else
                    v_plan += (v_want > v_plan ? a_step : -a_step);      // 还在按加速度斜坡爬/收
            }
            const double step = v_plan * kDt;
            if (std::fabs(err) <= std::fabs(step)) {
                q_cmd = q_target;                                       // 这一帧就能到
                v_plan = 0.0;
            } else {
                q_cmd += step;
            }
        }
        const double v_cmd = v_plan;

        // ---- 3. 发一帧 ----
        const bool ok = send_frame(q_cmd, v_cmd);
        ++frames;
        if (!ok) {
            ++timeouts;
            ++timeout_streak;
            if (timeouts <= 3)
                std::printf("  第 %d 帧没收到回复（超时）——ID 对不对？线松了？\n", frames);
            if (timeout_streak >= 40) {
                std::printf("**连续 %d 帧无回复 ⇒ 判定掉线**：卸力（零力矩）退出。"
                            "（驱动板自己会保持还是卸力见 docs/real.md §3.7 的 S2e）\n", timeout_streak);
                exit_code = 5;
                break;
            }
            usleep(5000);
            continue;
        }
        timeout_streak = 0;
        ++ok_frames;
        temp_max = std::max(temp_max, static_cast<int>(data.temp));
        merror_last = data.merror;

        // ---- 4. 反馈 → 我们的量：q = q_enc + offset ----
        const double dq_out = data.dq / N;          // 板子报的速度（输出端 rad/s）
        const double tau_out = data.tau * N;        // 讲义 §2.3：τ_out = N·τ_rotor
        const int64_t raw = static_cast<int64_t>(std::llround(data.q * 32768.0 / (2.0 * M_PI)));
        const double q_enc = data.q / N;
        last_q = q_enc + offset;
        q_min = std::min(q_min, last_q);
        q_max = std::max(q_max, last_q);
        tau_peak = std::max(tau_peak, std::fabs(tau_out));
        if (hold_torque && std::fabs(q_target - last_q) <= opt.tol_deg * kDegToRad)
            tau_hold_max = std::max(tau_hold_max, std::fabs(tau_out));

        // ---- 5. 零点跳变检测：用**整数 raw 差**（1 个零点区间 = k 个转子整圈 = k×32768） ----
        if (have_prev_raw) {
            const int64_t d_raw = raw - prev_raw;
            const double k = std::round(static_cast<double>(d_raw) / kRawPerTurn);
            // 残差换算到输出端 °：raw 是 q15 圈（转子侧）⇒ 1 圈 = 360°/N（输出端） = 一个零点区间
            const double resid_deg =
                (static_cast<double>(d_raw) - k * kRawPerTurn) / kRawPerTurn * (360.0 / N);
            if (k != 0.0 && std::fabs(resid_deg) <= opt.jump_tol_deg) {
                std::printf("  **零点跳变：pos 差 %+lld（%+.0f 个转子圈 ≈ %+.3f° 输出端）** 帧 %d t=%.3f s\n",
                            static_cast<long long>(d_raw), k, k * zone_deg, frame, wall_now());
                apply_jump_fix(k, "运行中检测到");
                last_q = q_enc + offset;   // 同一个板子读数、用新 offset 解释 ⇒ q 连续（不跳）
                if (fixes > opt.max_fixes) {
                    std::printf("**跳变次数超过 %d 次 ⇒ 停下来查（接线/编码器/供电），不要继续。**\n",
                                opt.max_fixes);
                    exit_code = 7;
                    break;
                }
            } else if (k != 0.0) {
                std::printf("  本帧步进 %+lld（≈%+.2f 个转子圈）但不是整圈（残差 %+.2f°）——"
                            "先怀疑手转太快/换了方向，不算跳变\n",
                            static_cast<long long>(d_raw), static_cast<double>(d_raw) / kRawPerTurn,
                            resid_deg);
            }
        }
        prev_raw = raw;
        have_prev_raw = true;

        // ---- 6. 打印 + 到位 ----
        const bool arrive = std::fabs(q_target - last_q) <= opt.tol_deg * kDegToRad;
        if (frame % every == 0 || arrive != arrived_printed || (arrive && arrived_since < 0.0)) {
            const double zone = std::floor(q_enc / zone_rad);
            std::printf("  帧 %5d t=%6.3f：q_enc %+9.3f°（第 %d 区） offset %+8.3f° → q %+9.3f°；"
                        "目标 %+9.3f° 差 %+7.3f°；dq %+6.2f°/s、tau %+6.3f N·m%s、temp %d、merror %u\n",
                        frame, wall_now(), q_enc / kDegToRad, static_cast<int>(zone),
                        offset / kDegToRad, last_q / kDegToRad, q_target / kDegToRad,
                        (q_target - last_q) / kDegToRad, dq_out / kDegToRad, tau_out,
                        (std::fabs(q_target - last_q) / kDegToRad > 2.0 &&
                         std::fabs(tau_out) >= 0.5 * opt.tau_out_limit) ? " ← 力矩接近上限" : "",
                        static_cast<int>(data.temp), static_cast<unsigned>(data.merror));
            if (arrive)
                std::printf("  ⇒ 到位（|差| ≤ %.2f°），保持中\n", opt.tol_deg);
            arrived_printed = arrive;
        }
        if (arrive) {
            if (arrived_since < 0.0)
                arrived_since = now;
        } else {
            arrived_since = -1.0;
        }

        // ---- 7. 保护：报错 / 温度 / 力矩上限 ----
        if (merror_last != 0) {
            std::printf("**电机报错 merror=%u**（1 过热/2 过流/3 过压/4 编码器）⇒ 卸力退出\n",
                        static_cast<unsigned>(merror_last));
            exit_code = 4;
            break;
        }
        if (data.temp >= 80) {
            std::printf("**温度 %d °C 偏高**（90 °C 触发保护）⇒ 卸力退出\n", static_cast<int>(data.temp));
            exit_code = 4;
            break;
        }
        if (hold_torque && std::fabs(tau_out) >= opt.tau_out_limit) {
            if (tau_over_since < 0.0) {
                tau_over_since = now;
            } else if (now - tau_over_since >= opt.stall_s) {
                std::printf("**力矩连续 %.2f s 超过上限 %.3f N·m（现在 %.3f）⇒ 判定卡住**：卸力退出。"
                            "把 --kp-out 调小、或让输出端别顶着东西\n",
                            now - tau_over_since, opt.tau_out_limit, std::fabs(tau_out));
                exit_code = 4;
                break;
            }
        } else {
            tau_over_since = -1.0;
        }

        // ---- 8. 脚本模式：等都发完 + 到位 + 稳住 --settle 秒才退出 ----
        if (opt.seconds > 0.0 && now >= opt.seconds) {
            std::printf("--seconds %.1f 到 ⇒ 收尾退出（差 %+.3f°）\n", opt.seconds,
                        (q_target - last_q) / kDegToRad);
            break;
        }
        if (!opt.script.empty() && script_last_set) {
            bool empty;
            {
                std::lock_guard<std::mutex> lk(mu);
                empty = pending.empty();
            }
            if (empty && now - script_last >= opt.script_step &&
                (arrived_since >= 0.0 && now - arrived_since >= opt.settle)) {
                std::printf("脚本跑完（最后一条命令后已等 %.1f s、且到位后稳了 %.1f s）⇒ 收尾退出\n",
                            now - script_last, now - arrived_since);
                break;
            }
            if (empty && now - script_last > opt.script_step + 30.0) {
                std::printf("脚本跑完但 30 s 内没能到位（差 %+.3f°）⇒ 按超时收尾\n",
                            (q_target - last_q) / kDegToRad);
                exit_code = 6;
                break;
            }
        }
        usleep(static_cast<useconds_t>(kDt * 1e6));
    }

    // 收尾：连发零力矩（卸力），不要留下"最后一条指令"让驱动板自己撑着
    int zero_sent = 0;
    for (int i = 0; i < 20; ++i) {
        if (!serial->sendRecv(&zero, &data))
            break;
        ++zero_sent;
        usleep(5000);
    }
    std::printf("收尾：已发 %d 帧零力矩（%s）\n", zero_sent, opt.self_test ? "自检假电机" : "实机");

    std::printf("=== 汇总 ===\n");
    if (ok_frames == 0) {
        std::printf("一帧回复都没收到（超时 %d 帧）：ID、TX/RX 交叉、共地、供电、权限。\n", timeouts);
        if (exit_code == 0)
            exit_code = 3;
    } else {
        std::printf("帧 %d（回复 %d、超时 %d）；q %+.3f°…%+.3f°（首帧 %+.3f°、末帧 %+.3f°）；"
                    "offset 末值 %+.3f°；力矩峰值 %.3f N·m（保持时 %.3f）；温度峰值 %d °C；末次 merror=%u\n",
                    frames, ok_frames, timeouts, q_min / kDegToRad, q_max / kDegToRad, q_first / kDegToRad,
                    last_q / kDegToRad, offset / kDegToRad, tau_peak, tau_hold_max, temp_max, merror_last);
        std::printf("零点跳变修正 %d 次；记号笔那个点 %s%s；本次计划行程合计 %.1f°；真实帧周期 %.3f ms"
                    "（名义 %.1f ms）\n",
                    fixes, have_mark ? "已记录" : "未记录（mark）",
                    have_mark ? "" : "（S4 的验收要用它）", travel_planned / kDegToRad,
                    ok_frames > 1 ? 1000.0 * wall_now() / ok_frames : 0.0, kDt * 1000.0);
    }
    delete serial;
    if (fake_motor.joinable()) {
        fake_stop = true;
        fake_motor.join();
    }
    return exit_code;
}
