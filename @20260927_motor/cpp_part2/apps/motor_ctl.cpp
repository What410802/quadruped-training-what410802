/**
 * @file motor_ctl.cpp
 * @brief 验收程序（任务书子任务项二 ②③④）：回 0
 * 位、键盘给角度、软件零点标定、上电/离线/跳变的零点处理。
 *
 * 这一层只做"编排 + 与人交互"：位置账本在 ZeroTracker，插值在 TrapezoidPlanner，收发在 MotorBus，
 * 命令行解析在 ParseCommand。设计说明见 ../../docs/zero-semantics.md，现场步骤见
 * ../../docs/runbook.md。
 *
 * 用法要点（完整列表见 --help）：
 *   sudo motor_ctl --port /dev/ttyUSB0 --id 0            # 实机
 *   motor_ctl --self-test --script "0;30;mark;o+30;expect;30"   # 假电机（需 LD_PRELOAD 垫片）
 * 键盘：state / reset / raw / 0 / <角度> / +d / offset / o+30 / mark / expect / fix / hold / stop /
 * q
 */
#include "motor_bench/console.hpp"
#include "motor_bench/motor_bus.hpp"
#include "motor_bench/sim/fake_motor.hpp"
#include "motor_bench/ticks.hpp"
#include "motor_bench/trajectory.hpp"
#include "motor_bench/zero_tracking.hpp"

#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <string>
#include <thread>
#include <unistd.h>
#include <vector>

namespace
{

using motor_bench::ConsoleCommand;
using motor_bench::MotorBus;
using motor_bench::RotorCommand;
using motor_bench::TrapezoidPlanner;
using motor_bench::ZeroTracker;
namespace ticks = motor_bench::ticks;

constexpr double kDt = 0.005; // 名义 5 ms/帧（实测约 5.6~6.4 ms，见 docs/real.md §3.6）

struct Options
{
    std::string port = "/dev/ttyUSB0";
    int id = 0;
    int baud = 4000000;
    double kp_out = 80.0;
    double kd_out = 3.0;
    double tau_out_limit = 1.5; // 超过它并持续 --stall-s 秒就判卡住
    double stall_s = 1.0;
    double vmax_deg = 90.0;
    double amax_deg = 180.0;
    double tol_deg = 1.0;
    double offset_deg = 0.0;
    double expect_deg = 0.0;
    bool expect_set = false;
    double expect_tol_deg = 3.0;
    double jump_tol_deg = 8.0;
    int max_fixes = 3;
    bool set_zero_read = false; // 启动时把当前位置定义成 0（等价于先跑一次 reset here）
    bool fix_startup = true;
    int every = 20;
    int offline_frames = 40; // 连续多少帧无回复算离线
    bool no_send = false;
    bool self_test = false;
    std::string script;
    double script_step = 2.0;
    double settle = 0.5;
    double seconds = 0.0;
    int fake_datum_turns = 0;
    bool fake_sawtooth = false;
    long fake_jump_frame = -1;
    int fake_jump_turns = 1;
    long fake_off_after = -1; // 模拟"板子断电"的起始帧（不再收命令/回帧）
    int fake_off_frames = 0;
    long fake_cycle_frame = -1;
    double fake_hand_deg = 0.0;      // 手转幅度（输出端角度 [°]；0 = 不打手）
    double fake_hand_period_s = 8.0; // 手转周期 [s]
    bool recover_hold = false;       // 离线恢复后：就地重新起目标（默认维持原目标）
    uint8_t fake_status_bits = 0;    // 假板子回帧里要塞的状态位（bit1 速度超范围、bit2 位置超范围）
};

void Usage(const char* prog)
{
    std::printf(
        "用法：%s [--port /dev/ttyUSB0] [--id N] [--offset-deg D] [--script \"...\"] [--self-test]\n"
        "  --port/--id/--baud      串口、电机 ID、波特率（默认 /dev/ttyUSB0、0、4000000）\n"
        "  --kp-out/--kd-out       输出端增益（默认 80 / 3；下发时 ÷N²）\n"
        "  --tau-out-limit/--stall-s  力矩上限与“持续多久算卡住”（默认 1.5 N·m / 1.0 s）\n"
        "  --vmax-deg/--amax-deg/--tol-deg  插值上限与到位判据（默认 90°/s、180°/s²、1°）\n"
        "  --offset-deg            软件零点偏移初值（默认 0；标定结果可存档到这里）\n"
        "  --set-zero-read         启动时把当前位置定义成 0（= 先执行一次 reset here）\n"
        "  --expect-deg D          启动检查：q 应 ≈ D 度（上次 mark 的 q），差 ≈1 个区间就按 fix 自动修\n"
        "  --no-fix-startup        启动检查只报警、不自动修\n"
        "  --offline-frames N      连续 N 帧无回复算离线（默认 40）\n"
        "  --recover-hold          离线恢复后就地重新起目标（默认维持原目标不动）\n"
        "  --every N               每 N 帧打印一行（默认 20）\n"
        "  --script \"a;b;c\"        非交互执行命令（每条间隔 --script-step 秒，默认 2 s）\n"
        "  --seconds SEC           跑 SEC 秒后收尾退出（默认 0 = 一直跑）\n"
        "  --no-send               只打印配置，不打开串口\n"
        "  --self-test             无硬件自检：PTY + 假电机（要 LD_PRELOAD 垫片）\n"
        "  --fake-datum-turns N / --fake-sawtooth / --fake-jump-frame N [--fake-jump-turns K]\n"
        "  --fake-off-after N [--fake-off-frames M] / --fake-cycle-frame N\n"
        "                          自检时给“驱动板”注入：上电落在别的候选零点 / 锯齿 / 运行中换基准 /\n"
        "                          第 N 帧起断电 M 帧（不收命令也不回帧）/ 第 N 帧上电复位（丢圈数）\n"
        "  --fake-hand-deg D [--fake-hand-period-s T]\n"
        "                          自检时模拟“手推输出端”：输出端在一根正弦上来回转 ±D 度、周期 T 秒\n"
        "  --fake-status-bits N    自检时把回帧 mode 的状态位写死（bit1 期望速度超范围、bit2 期望位置超范围）\n"
        "\n%s",
        prog, motor_bench::HelpText());
}

bool ParseOptions(int argc, char** argv, Options* o)
{
    for (int i = 1; i < argc; ++i)
    {
        const std::string a = argv[i];
        const bool next = i + 1 < argc;
        if (a == "--help" || a == "-h")
        {
            return false;
        }
        else if (a == "--no-send")
        {
            o->no_send = true;
        }
        else if (a == "--self-test")
        {
            o->self_test = true;
        }
        else if (a == "--set-zero-read")
        {
            o->set_zero_read = true;
        }
        else if (a == "--no-fix-startup")
        {
            o->fix_startup = false;
        }
        else if (a == "--fake-sawtooth")
        {
            o->fake_sawtooth = true;
        }
        else if (a == "--port" && next)
        {
            o->port = argv[++i];
        }
        else if (a == "--id" && next)
        {
            o->id = std::atoi(argv[++i]);
        }
        else if (a == "--baud" && next)
        {
            o->baud = std::atoi(argv[++i]);
        }
        else if (a == "--kp-out" && next)
        {
            o->kp_out = std::atof(argv[++i]);
        }
        else if (a == "--kd-out" && next)
        {
            o->kd_out = std::atof(argv[++i]);
        }
        else if (a == "--tau-out-limit" && next)
        {
            o->tau_out_limit = std::atof(argv[++i]);
        }
        else if (a == "--stall-s" && next)
        {
            o->stall_s = std::atof(argv[++i]);
        }
        else if (a == "--vmax-deg" && next)
        {
            o->vmax_deg = std::atof(argv[++i]);
        }
        else if (a == "--amax-deg" && next)
        {
            o->amax_deg = std::atof(argv[++i]);
        }
        else if (a == "--tol-deg" && next)
        {
            o->tol_deg = std::atof(argv[++i]);
        }
        else if (a == "--offset-deg" && next)
        {
            o->offset_deg = std::atof(argv[++i]);
        }
        else if (a == "--expect-deg" && next)
        {
            o->expect_deg = std::atof(argv[++i]);
            o->expect_set = true;
        }
        else if (a == "--expect-tol-deg" && next)
        {
            o->expect_tol_deg = std::atof(argv[++i]);
        }
        else if (a == "--jump-tol-deg" && next)
        {
            o->jump_tol_deg = std::atof(argv[++i]);
        }
        else if (a == "--max-fixes" && next)
        {
            o->max_fixes = std::atoi(argv[++i]);
        }
        else if (a == "--offline-frames" && next)
        {
            o->offline_frames = std::atoi(argv[++i]);
        }
        else if (a == "--every" && next)
        {
            o->every = std::atoi(argv[++i]);
        }
        else if (a == "--script" && next)
        {
            o->script = argv[++i];
        }
        else if (a == "--script-step" && next)
        {
            o->script_step = std::atof(argv[++i]);
        }
        else if (a == "--settle" && next)
        {
            o->settle = std::atof(argv[++i]);
        }
        else if (a == "--seconds" && next)
        {
            o->seconds = std::atof(argv[++i]);
        }
        else if (a == "--fake-datum-turns" && next)
        {
            o->fake_datum_turns = std::atoi(argv[++i]);
        }
        else if (a == "--fake-jump-frame" && next)
        {
            o->fake_jump_frame = std::atol(argv[++i]);
        }
        else if (a == "--fake-jump-turns" && next)
        {
            o->fake_jump_turns = std::atoi(argv[++i]);
        }
        else if (a == "--fake-off-after" && next)
        {
            o->fake_off_after = std::atol(argv[++i]);
        }
        else if (a == "--fake-off-frames" && next)
        {
            o->fake_off_frames = std::atoi(argv[++i]);
        }
        else if (a == "--fake-cycle-frame" && next)
        {
            o->fake_cycle_frame = std::atol(argv[++i]);
        }
        else if (a == "--fake-hand-deg" && next)
        {
            o->fake_hand_deg = std::atof(argv[++i]);
        }
        else if (a == "--fake-hand-period-s" && next)
        {
            o->fake_hand_period_s = std::atof(argv[++i]);
        }
        else if (a == "--recover-hold")
        {
            o->recover_hold = true;
        }
        else if (a == "--fake-status-bits" && next)
        {
            o->fake_status_bits = static_cast<uint8_t>(std::atoi(argv[++i]));
        }
        else
        {
            std::fprintf(stderr, "未知参数：%s\n", a.c_str());
            return false;
        }
    }
    return true;
}

/** 交互/脚本命令的来源：stdin 线程 + `--script` 列表（与旧版一致） */
class CommandQueue
{
  public:
    void LoadScript(const std::string& script)
    {
        std::string rest = script;
        while (!rest.empty())
        {
            const size_t pos = rest.find(';');
            const std::string tok = rest.substr(0, pos);
            rest = (pos == std::string::npos) ? std::string() : rest.substr(pos + 1);
            if (tok.find_first_not_of(" \t") != std::string::npos)
            {
                pending_.push_back(tok);
            }
        }
    }

    void StartStdinReader()
    {
        std::thread(
            [this]
            {
                char buf[512];
                std::string carry;
                while (true)
                {
                    const ssize_t n = ::read(0, buf, sizeof(buf));
                    if (n <= 0)
                    {
                        break;
                    }
                    carry.append(buf, static_cast<size_t>(n));
                    size_t pos;
                    while ((pos = carry.find('\n')) != std::string::npos)
                    {
                        const std::string line = carry.substr(0, pos);
                        carry.erase(0, pos + 1);
                        Push(line);
                    }
                }
            })
            .detach();
    }

    void Push(const std::string& line)
    {
        std::lock_guard<std::mutex> lock(mutex_);
        pending_.push_back(line);
    }

    bool TryPop(std::string* out)
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (pending_.empty())
        {
            return false;
        }
        *out = pending_.front();
        pending_.erase(pending_.begin());
        return true;
    }

    bool empty()
    {
        std::lock_guard<std::mutex> lock(mutex_);
        return pending_.empty();
    }

  private:
    std::mutex mutex_;
    std::vector<std::string> pending_;
};

} // namespace

int main(int argc, char** argv)
{
    Options opt;
    if (!ParseOptions(argc, argv, &opt))
    {
        Usage(argv[0]);
        return 1;
    }

    const double gear = ticks::kGearTrue;
    const double zone_deg = 360.0 / gear;
    const double kp_rotor = opt.kp_out / (gear * gear);
    const double kd_rotor = opt.kd_out / (gear * gear);
    const int64_t tol_ticks = std::max<int64_t>(1, ticks::DegToTicks(opt.tol_deg));
    const int64_t jump_tol_ticks = std::max<int64_t>(1, ticks::DegToTicks(opt.jump_tol_deg));
    const int64_t zone_ticks = ticks::kTicksPerZone;

    std::printf("=== 验收程序（回 0 / 键盘给角度 / 软件零点 / 上电与离线处理）===\n");
    std::printf(
        "减速比 N = 19:3 = %.6f（SDK 给 %.2f）⇒ 一个零点区间 = %lld tick = %.4f°（输出端）\n", gear,
        ticks::kGearSdk, static_cast<long long>(zone_ticks), zone_deg);
    std::printf(
        "位置用转子侧 tick：1 tick = %.6f°（输出端）；增益 kp=%.3g kd=%.3g → 转子侧 %.4f / %.5f\n",
        ticks::TicksToDeg(1), opt.kp_out, opt.kd_out, kp_rotor, kd_rotor);

    if (opt.no_send)
    {
        std::printf("--no-send：到此为止，没有打开串口、没有发任何字节。\n");
        return 0;
    }

    // ---------- 打开总线（实机或自检） ----------
    MotorBus* bus = nullptr;
    std::thread fake_motor;
    std::atomic<bool> fake_stop{false};
    try
    {
        if (opt.self_test)
        {
            int master = -1;
            const std::string slave = motor_bench::sim::MakePty(&master);
            if (slave.empty())
            {
                return 1;
            }
            motor_bench::sim::Model model;
            model.enc.mode = opt.fake_sawtooth ? 1 : 0;
            model.enc.datum = opt.fake_datum_turns;
            model.enc.jump_frame = opt.fake_jump_frame;
            model.enc.jump_turns = opt.fake_jump_turns;
            model.enc.off_after = opt.fake_off_after;
            model.enc.off_frames = opt.fake_off_frames;
            model.enc.cycle_frame = opt.fake_cycle_frame;
            model.enc.hand_deg = opt.fake_hand_deg;
            model.enc.hand_period_s = opt.fake_hand_period_s;
            model.enc.status_bits = opt.fake_status_bits;
            std::printf("自检：PTY slave=%s（假板子：读数形态=%s、上电基准 %+d 圈%s%s）\n",
                        slave.c_str(), model.enc.mode == 1 ? "锯齿" : "里程计", model.enc.datum,
                        opt.fake_jump_frame > 0 ? "、注入一次中途换基准" : "",
                        opt.fake_hand_deg != 0.0 ? "、手推输出端来回转" : "");
            fake_motor = motor_bench::sim::Start(master, &fake_stop, model);
            bus = new MotorBus(slave, opt.id, opt.baud);
        }
        else
        {
            bus = new MotorBus(opt.port, opt.id, opt.baud);
        }
    }
    catch (const std::exception& e)
    {
        std::printf("**串口打开失败**：%s\n", e.what());
        if (fake_motor.joinable())
        {
            fake_stop = true;
            fake_motor.join();
        }
        return 2;
    }
    std::printf("串口已打开（%s）\n", opt.self_test ? "自检 PTY" : opt.port.c_str());

    // ---------- 启动：零力矩读一帧，建立账本 ----------
    ZeroTracker zero;
    zero.SetOffset(ticks::DegToTicks(opt.offset_deg));
    TrapezoidPlanner planner;
    planner.SetLimits(opt.vmax_deg, opt.amax_deg);

    ticks::Feedback fb;
    bool ok = false;
    for (int i = 0; i < 3 && !ok; ++i)
    {
        ok = bus->SendZero(&fb);
        if (!ok)
        {
            usleep(20000);
        }
    }
    if (!ok)
    {
        std::printf("启动时零力矩读一帧就失败：检查 ID、接线（TX/RX/共地）、供电、权限。\n");
        delete bus;
        if (fake_motor.joinable())
        {
            fake_stop = true;
            fake_motor.join();
        }
        return 3;
    }
    zero.AnchorAtStartup(fb.pos);
    int64_t last_raw = fb.pos;
    bool online = true;
    // 账本与板子读数是否已经"对上"（上电握手成功 / 离线回来后重锚完成）。没对上之前只发零力矩。
    bool handshook = true;
    const auto wall0 = std::chrono::steady_clock::now();
    const auto wall_now = [&wall0]
    { return std::chrono::duration<double>(std::chrono::steady_clock::now() - wall0).count(); };
    std::printf("启动读数：pos %+lld tick（= %+.3f°，第 %lld 区、区内 %+.3f°）、offset %+lld tick"
                "（%+.3f°） → q %+.3f°%s\n",
                static_cast<long long>(fb.pos), ticks::TicksToDeg(fb.pos),
                static_cast<long long>(fb.pos / zone_ticks), ticks::TicksToDeg(fb.pos % zone_ticks),
                static_cast<long long>(zero.offset()), ticks::TicksToDeg(zero.offset()),
                ticks::TicksToDeg(zero.RawToQ(fb.pos)),
                fb.from_raw ? "" : "（注意：没读到原始帧，退化成用 float 反算）");
    std::printf("    ↑ 板子掉电会丢圈数：上电首帧 pos 的整数部分是 0，我们按“接受当前位置”锚定"
                "（turn_base=0），后面一切相对它算\n");

    if (opt.set_zero_read)
    {
        // 把"此刻"定义成软件零点：offset = −pos
        const int64_t pos = zero.PositionTicks(fb.pos);
        zero.SetOffset(-pos);
        std::printf(
            "--set-zero-read：把此刻定义成 0 ⇒ offset = %+lld tick（%+.3f°）；离零点边界 %.3f°\n",
            static_cast<long long>(zero.offset()), ticks::TicksToDeg(zero.offset()),
            ticks::TicksToDeg(ticks::DistanceToZoneEdge(pos)));
    }

    // 启动检查：与记录值对照（差 ≈ 整数个区间就是上电落在别的候选零点）
    if (opt.expect_set)
    {
        const int64_t want = ticks::DegToTicks(opt.expect_deg);
        const int64_t q_now = zero.RawToQ(fb.pos);
        const int64_t d = q_now - want;
        const int64_t k = ZeroTracker::TurnsOfDelta(d);
        std::printf("启动检查：q %+.3f°（pos %+lld tick），记录值 %+.3f°（差 %+lld tick = %+.3f°）",
                    ticks::TicksToDeg(q_now), static_cast<long long>(zero.PositionTicks(fb.pos)),
                    opt.expect_deg, static_cast<long long>(d), ticks::TicksToDeg(d));
        if (std::llabs(d) <= ticks::DegToTicks(opt.expect_tol_deg))
        {
            std::printf(" ⇒ 在容差内，零点没变。\n");
        }
        else if (k != 0 && std::llabs(d - k * zone_ticks) <= jump_tol_ticks)
        {
            std::printf(" ⇒ 差了 %+lld 个零点区间（≈%+.3f°），疑似上电落在别的候选零点。\n",
                        static_cast<long long>(k), ticks::TicksToDeg(k * zone_ticks));
            if (opt.fix_startup)
            {
                zero.AlignTo(fb.pos, want, wall_now());
                std::printf("   已自动对齐到记录值（见账本事件）；电机不会动。\n");
            }
            else
            {
                std::printf("   没有自动修（去掉 --no-fix-startup 或运行时 fix）。\n");
            }
        }
        else
        {
            std::printf(" ⇒ 既不是 0 也不是整数个区间，先别动电机。\n");
        }
    }

    planner.SnapTo(zero.RawToQ(fb.pos));
    int64_t q_target = zero.RawToQ(fb.pos);
    bool hold_torque = true;
    bool have_mark = false;
    int64_t mark_ticks = 0;
    int64_t mark_pos = 0;
    int fixes = 0;
    int cmd_seq = 0;
    double tau_over_since = -1.0;
    double tau_peak = 0.0;
    int temp_max = -128;
    unsigned merror_last = 0;
    int arrive_printed = -1;
    double arrived_since = -1.0;
    int exit_code = 0;

    // ---------- 命令来源 ----------
    CommandQueue queue;
    if (!opt.script.empty())
    {
        queue.LoadScript(opt.script);
        std::printf("--script：%s\n", opt.script.c_str());
    }
    else if (::isatty(0))
    {
        std::printf(
            "键盘就绪（h 看帮助）：state / reset / raw / 0 / <角度> / o+30 / mark / stop / q\n");
        queue.StartStdinReader();
    }
    else
    {
        std::printf("stdin 不是终端、也没给 --script：只做启动检查，之后保持不动。\n");
    }

    const auto deg = [](int64_t t) { return ticks::TicksToDeg(t); };
    const auto print_state = [&]()
    {
        const int64_t pos = zero.PositionTicks(last_raw);
        const int64_t q = zero.RawToQ(last_raw);
        std::printf(
            "state：pos %+lld tick（%+.3f°） turn_base %+lld offset %+lld tick（%+.3f°） → q %+.3f°；"
            "目标 %+.3f°（差 %+.3f°）；%s；在线 %s\n",
            static_cast<long long>(pos), deg(pos), static_cast<long long>(zero.turn_base()),
            static_cast<long long>(zero.offset()), deg(zero.offset()), deg(q), deg(q_target),
            deg(q_target - q), hold_torque ? "位置保持" : "零力矩",
            online ? "是" : "**否（最近一次是离线）**");
        if (have_mark)
        {
            std::printf(
                "      记号笔：q %+.3f°、pos %+lld tick（上电检查用 pos 或 --expect-deg 的 q）\n",
                deg(mark_ticks), static_cast<long long>(mark_pos));
        }
        if (!zero.events().empty())
        {
            std::printf("      账本事件 %zu 条：", zero.events().size());
            for (const auto& e : zero.events())
            {
                std::printf(" [%s k=%+lld]", e.what.c_str(), static_cast<long long>(e.k));
            }
            std::printf("\n");
        }
    };

    // ---------- 主循环 ----------
    double script_next = 0.0;
    double script_last = 0.0;
    bool script_last_set = false;
    int frame = 0;
    bool quit = false;

    while (!quit)
    {
        ++frame;
        const double now = wall_now();

        // 1) 取一条命令
        std::string line;
        if (!opt.script.empty())
        {
            if (now >= script_next && queue.TryPop(&line))
            {
                script_next = now + opt.script_step;
                script_last = now;
                script_last_set = true;
            }
        }
        else
        {
            queue.TryPop(&line);
        }

        if (!line.empty())
        {
            const ConsoleCommand c = motor_bench::ParseCommand(line);
            std::printf("命令#%d：\"%s\"\n", ++cmd_seq, line.c_str());
            const int64_t before_target = q_target;
            switch (c.kind)
            {
            case ConsoleCommand::Kind::kNone:
                q_target = 0;
                std::printf("  → 回软件零点\n");
                break;
            case ConsoleCommand::Kind::kHelp:
                std::printf("%s", motor_bench::HelpText());
                break;
            case ConsoleCommand::Kind::kState:
                print_state();
                break;
            case ConsoleCommand::Kind::kHold:
                hold_torque = true;
                q_target = zero.RawToQ(last_raw);
                planner.SnapTo(q_target);
                std::printf("  → 位置保持，目标 = 当前位置\n");
                break;
            case ConsoleCommand::Kind::kStop:
                hold_torque = false;
                std::printf("  → 零力矩（电机自由，可手转）\n");
                break;
            case ConsoleCommand::Kind::kQuit:
                std::printf("  → 先卸力再退出\n");
                quit = true;
                break;
            case ConsoleCommand::Kind::kGoTo:
                q_target = ticks::DegToTicks(c.value);
                break;
            case ConsoleCommand::Kind::kJog:
                q_target = zero.RawToQ(last_raw) + ticks::DegToTicks(c.value);
                break;
            case ConsoleCommand::Kind::kGoRaw:
                q_target = zero.PositionToQ(0); // pos = 0 那个点（当前 turn_base 下）
                std::printf("  → 去编码器真值零点（pos=0）\n");
                break;
            case ConsoleCommand::Kind::kMark:
                mark_pos = zero.PositionTicks(last_raw);
                mark_ticks = zero.RawToQ(last_raw);
                have_mark = true;
                std::printf(
                    "  → 记号笔那点：pos %+lld tick（%+.3f°）、q %+.3f°；离零点边界 %.3f°\n",
                    static_cast<long long>(mark_pos), deg(mark_pos), deg(mark_ticks),
                    deg(ticks::DistanceToZoneEdge(mark_pos)));
                break;
            case ConsoleCommand::Kind::kGoMark:
                if (!have_mark)
                {
                    std::printf("  → 还没记过记号笔位置（先 mark）\n");
                }
                else
                {
                    q_target = mark_ticks;
                    std::printf("  → 去记号笔那点：目标 %+.3f°\n", deg(mark_ticks));
                }
                break;
            case ConsoleCommand::Kind::kExpect:
            {
                const int64_t want = have_mark ? mark_ticks : 0;
                const int64_t q = zero.RawToQ(last_raw);
                const int64_t d = q - want;
                const int64_t k = ZeroTracker::TurnsOfDelta(d);
                std::printf("  → 对照：现在 %+.3f°、记录值 %+.3f°（差 %+lld tick = %+.3f°）。",
                            deg(q), deg(want), static_cast<long long>(d), deg(d));
                if (std::llabs(d) <= ticks::DegToTicks(opt.expect_tol_deg))
                {
                    std::printf("≈0，零点没跳变。\n");
                }
                else if (k != 0 && std::llabs(d - k * zone_ticks) <= jump_tol_ticks)
                {
                    std::printf("差 %+lld 个区间，疑似认错零点，用 fix 修。\n",
                                static_cast<long long>(k));
                }
                else
                {
                    std::printf("既不是 0 也不是整数个区间，先别动电机。\n");
                }
                break;
            }
            case ConsoleCommand::Kind::kFix:
            {
                const int64_t want = have_mark ? mark_ticks : 0;
                const int64_t q = zero.RawToQ(last_raw);
                const int64_t d = q - want;
                const int64_t k = ZeroTracker::TurnsOfDelta(d);
                if (k == 0 || std::llabs(d - k * zone_ticks) > jump_tol_ticks)
                {
                    std::printf("  → 与记录值差 %+.3f°，不是整数个区间，fix 不动。\n", deg(d));
                }
                else
                {
                    // 把"板子基准整体挪了 k 个区间"补回来：只改 offset，q 连续、物理目标不变
                    zero.FixJump(k, now); // 只改 offset：q 连续、物理目标不变
                    planner.SnapTo(zero.RawToQ(last_raw));
                    std::printf("  → 已修正：offset %+lld tick；记号笔那点现在读 %+.3f°\n",
                                static_cast<long long>(zero.offset()), deg(mark_ticks));
                }
                break;
            }
            case ConsoleCommand::Kind::kOffsetAbs:
            case ConsoleCommand::Kind::kOffsetRel:
            {
                const int64_t before = zero.offset();
                const int64_t delta = (c.kind == ConsoleCommand::Kind::kOffsetAbs)
                                          ? ticks::DegToTicks(c.value) - before
                                          : ticks::DegToTicks(c.value);
                zero.ShiftOffset(delta);
                // 物理目标不动：q_target 与插值位置一起挪同样的量
                if (hold_torque)
                {
                    q_target += delta;
                    planner.SnapTo(planner.position_ticks() + delta);
                }
                if (have_mark)
                {
                    mark_ticks += delta;
                }
                std::printf(
                    "  → offset %+lld → %+lld tick（%+.3f°），q 空间同步挪，物理目标不变%s\n",
                    static_cast<long long>(before), static_cast<long long>(zero.offset()),
                    deg(zero.offset()), have_mark ? "；记号笔那点读数已同步" : "");
                break;
            }
            case ConsoleCommand::Kind::kReset:
            {
                bool go_raw = false;
                if (c.arg == "raw")
                {
                    go_raw = true;
                }
                else if (c.arg.empty() && ::isatty(0))
                {
                    std::printf("  回到编码器真值零点吗？[y/N] ");
                    std::fflush(stdout);
                    char buf[16] = {0};
                    if (::read(0, buf, sizeof(buf) - 1) > 0 && (buf[0] == 'y' || buf[0] == 'Y'))
                    {
                        go_raw = true;
                    }
                }
                if (go_raw)
                {
                    q_target = zero.PositionToQ(0);
                    std::printf(
                        "  → 先转到编码器真值零点（pos=0），到位后请再按一次 reset here 定零点\n");
                }
                else
                {
                    zero.SetOffset(-zero.PositionTicks(last_raw));
                    q_target = zero.RawToQ(last_raw);
                    planner.SnapTo(q_target);
                    std::printf("  → 把此刻定义为软件零点：offset = %+lld tick；当前 q = %+.3f°\n",
                                static_cast<long long>(zero.offset()), deg(q_target));
                }
                break;
            }
            case ConsoleCommand::Kind::kUnknown:
            default:
                std::printf("  → 没看懂：\"%s\"（h 看帮助）\n", c.arg.c_str());
                break;
            }

            if (c.kind == ConsoleCommand::Kind::kGoTo || c.kind == ConsoleCommand::Kind::kJog ||
                c.kind == ConsoleCommand::Kind::kGoMark || c.kind == ConsoleCommand::Kind::kNone ||
                c.kind == ConsoleCommand::Kind::kGoRaw)
            {
                const int64_t q = zero.RawToQ(last_raw);
                if (std::llabs(q_target - q) > tol_ticks)
                {
                    std::printf("     目标 %+.3f°（现在 %+.3f°）：要转 %+.2f°（%lld tick），"
                                "按 vmax=%.0f°/s 直线时间约 %.1f s\n",
                                deg(q_target), deg(q), deg(q_target - q),
                                static_cast<long long>(q_target - q), opt.vmax_deg,
                                std::fabs(deg(q_target - q)) / opt.vmax_deg);
                }
            }
            if (q_target != before_target)
            {
                planner.SetTarget(q_target);
            }
        }

        // 2) 插值 → 发一帧
        const double q_cmd = planner.Step(kDt);
        const double v_rotor =
            planner.velocity_tps() * (2.0 * ticks::kPiSdk / ticks::kTicksPerTurn);
        RotorCommand rotor;
        // q_cmd 在"软件零点空间"，报文要的是"板子读数空间"：减去 offset 再下发（讲义 §2.5
        // 的"下发减"）。
        // **还没握过手之前一律零力矩**：板子刚上电/刚回来时，它自己的读数空间与我们的账本可能
        // 差整数个区间（单圈绝对值编码器一上电就丢圈数），此刻任何位置目标都可能让板子按"最短
        // 弧"去追一个差一圈的目标 ⇒ 力矩冲击。先零力矩拿到一帧读数、把账本锚好，再开始出力。
        rotor.q_ticks = online ? (std::llround(q_cmd) - zero.offset() - zero.turn_base()) : last_raw;
        const bool drive = online && handshook;
        rotor.dq = drive ? (hold_torque ? v_rotor : 0.0) : 0.0;
        rotor.kp = drive ? (hold_torque ? kp_rotor : 0.0) : 0.0;
        rotor.kd = drive ? (hold_torque ? kd_rotor : 0.0) : 0.0;
        const bool recv_ok = bus->Send(rotor, &fb);

        if (!recv_ok)
        {
            if (bus->timeout_streak() == 3)
            {
                std::printf("  第 %d 帧没收到回复（ID？线松了？）\n", bus->frames());
            }
            if (bus->timeout_streak() >= opt.offline_frames)
            {
                if (online)
                {
                    online = false;
                    handshook = false; // 先零力矩，等重锚完成再出力
                    std::printf(
                        "  **离线**：连续 %d 帧无回复，先零力矩（不再追目标）；回来后会按“位置没动”"
                        "重锚，锚好再恢复出力\n",
                        opt.offline_frames);
                }
            }
            usleep(static_cast<useconds_t>(kDt * 1e6));
            continue;
        }

        // 3) 在线：处理"恢复"与"跳变"
        const int64_t raw = fb.pos;
        if (!online)
        {
            online = true;
            zero.ReanchorAfterOffline(raw, zero.PositionTicks(last_raw), now);
            const int64_t recovered_pos = zero.PositionTicks(raw);
            const int64_t prev_pos = zero.PositionTicks(last_raw);
            const int64_t q_now = recovered_pos + zero.offset();
            std::printf(
                "  **恢复在线**：raw %+lld tick、上次 pos %+lld tick ⇒ 重锚 turn_base %+lld；"
                "位置真值 %+.3f°（= 掉线前的 %+.3f° + 离线期间被推的 %+.3f°）\n",
                static_cast<long long>(raw), static_cast<long long>(prev_pos),
                static_cast<long long>(zero.turn_base()), deg(recovered_pos), deg(prev_pos),
                deg(recovered_pos - prev_pos));
            last_raw = raw;
            handshook = true; // 账本已对上，本帧之后才开始出力
            // 掉线期间人手推过的话，位置真值已经变了：不能继续追旧目标（那等于让电机"追回丢掉的
            // 角度"，可能一帧就要跨一个区间、给出巨大目标跳变）。默认策略是**就地重新起一个目标**
            // —— 零力矩模式下本来就不该有目标；只有显式声明"要守住掉的这点角度"才继续追。
            if (opt.recover_hold)
            {
                planner.SnapTo(q_now);
                std::printf("  （--recover-hold：接受新位置，就地重新起目标 %+.3f°）\n", deg(q_now));
            }
            else
            {
                std::printf("  （目标维持 %+.3f°：电机按当前目标继续动作；要就地接管请加 --recover-hold）\n",
                            deg(q_target));
            }
        }
        else
        {
            const int64_t delta = raw - last_raw;
            const int64_t k = ZeroTracker::TurnsOfDelta(delta);
            const int64_t resid = delta - k * zone_ticks;
            if (k != 0 && std::llabs(resid) <= jump_tol_ticks)
            {
                std::printf(
                    "  **零点跳变**：Δpos %+lld tick = %+lld 个区间（≈%+.3f°），修正 offset\n",
                    static_cast<long long>(delta), static_cast<long long>(k), deg(k * zone_ticks));
                zero.FixJump(k, now);
                ++fixes;
            }
            else if (k != 0)
            {
                std::printf("  本帧步进 %+lld tick（≈%+.2f 圈）但不是整圈，先怀疑手转太快\n",
                            static_cast<long long>(delta), static_cast<double>(delta) / zone_ticks);
            }
            last_raw = raw;
        }

        temp_max = std::max(temp_max, fb.temp);
        merror_last = fb.merror;
        const double tau_out = (fb.torque_raw / 256.0) * gear;
        tau_peak = std::max(tau_peak, std::fabs(tau_out));
        const int64_t q_now = zero.RawToQ(raw);

        // 4) 打印 + 到位
        const bool arrive = std::llabs(q_target - q_now) <= tol_ticks;
        if (frame % opt.every == 0 || arrive != (arrive_printed == 1))
        {
            std::printf("  帧 %5d t=%6.3f：pos %+8lld tick（%+8.3f°、第 %lld 区） offset %+8.3f° → "
                        "q %+8.3f°；目标 %+8.3f° 差 %+7.3f°；tau %+6.3f N·m、temp %d、merror %u%s\n",
                        frame, now, static_cast<long long>(zero.PositionTicks(raw)),
                        deg(zero.PositionTicks(raw)),
                        static_cast<long long>(zero.PositionTicks(raw) / zone_ticks),
                        deg(zero.offset()), deg(q_now), deg(q_target), deg(q_target - q_now),
                        tau_out, fb.temp, fb.merror,
                        (fb.DesPosOutOfRange() || fb.DesSpeedOutOfRange()) ? "、**期望值超范围**" : "");
            arrive_printed = arrive ? 1 : 0;
            if (arrive)
            {
                std::printf("  ⇒ 到位（|差| ≤ %.2f°），保持中\n", opt.tol_deg);
            }
        }
        arrived_since = arrive ? (arrived_since < 0 ? now : arrived_since) : -1.0;

        // 5) 保护
        if (fb.merror != 0)
        {
            std::printf("**电机报错 merror=%u** ⇒ 卸力退出\n", fb.merror);
            exit_code = 4;
            break;
        }
        if (fb.temp >= 80)
        {
            std::printf("**温度 %d °C 偏高** ⇒ 卸力退出\n", fb.temp);
            exit_code = 4;
            break;
        }
        if (hold_torque && std::fabs(tau_out) >= opt.tau_out_limit)
        {
            if (tau_over_since < 0)
            {
                tau_over_since = now;
            }
            else if (now - tau_over_since >= opt.stall_s)
            {
                std::printf("**力矩连续 %.2f s 超过上限 %.3f N·m ⇒ 判定卡住**，卸力退出\n",
                            now - tau_over_since, opt.tau_out_limit);
                exit_code = 4;
                break;
            }
        }
        else
        {
            tau_over_since = -1.0;
        }

        // 6) 收尾条件
        if (opt.seconds > 0 && now >= opt.seconds)
        {
            std::printf("--seconds %.1f 到 ⇒ 收尾\n", opt.seconds);
            break;
        }
        if (!opt.script.empty() && script_last_set && queue.empty() &&
            now - script_last >= opt.script_step && arrived_since >= 0 &&
            now - arrived_since >= opt.settle)
        {
            std::printf("脚本跑完且已稳 %.1f s ⇒ 收尾\n", opt.settle);
            break;
        }
        usleep(static_cast<useconds_t>(kDt * 1e6));
    }

    // 收尾：先卸力（S2e 实测：驱动板不会自己卸力），再退出
    int zero_sent = 0;
    for (int i = 0; i < 20; ++i)
    {
        if (!bus->SendZero(&fb))
        {
            break;
        }
        ++zero_sent;
        usleep(5000);
    }
    std::printf("收尾：已发 %d 帧零力矩\n", zero_sent);
    std::printf("=== 汇总 ===\n");
    std::printf(
        "帧 %d（回复 %d、超时 %d）；pos 末值 %+lld tick（%+.3f°）；offset %+lld tick（%+.3f°）；"
        "turn_base %+lld；账本事件 %zu 条；跳变修正 %d 次；力矩峰值 %.3f N·m；温度峰值 %d °C；"
        "末次 merror=%u\n",
        bus->frames(), bus->ok_frames(), bus->timeouts(),
        static_cast<long long>(zero.PositionTicks(last_raw)), deg(zero.PositionTicks(last_raw)),
        static_cast<long long>(zero.offset()), deg(zero.offset()),
        static_cast<long long>(zero.turn_base()), zero.events().size(), fixes, tau_peak, temp_max,
        merror_last);
    if (bus->ok_frames() == 0)
    {
        exit_code = exit_code == 0 ? 3 : exit_code;
    }
    delete bus;
    if (fake_motor.joinable())
    {
        fake_stop = true;
        fake_motor.join();
    }
    return exit_code;
}
