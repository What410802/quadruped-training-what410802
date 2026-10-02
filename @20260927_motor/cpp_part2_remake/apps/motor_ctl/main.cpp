/**
 * @file main.cpp
 * @brief motor_ctl：子任务项二 ②③ 的验收程序（M1 在线简版，假设"程序运行时段 ⊆ 电机上电时段"）。
 *
 * 用法与示例：
 *   sudo motor_ctl --port /dev/ttyUSB0 --id 0
 *   motor_ctl <<< "move 0; wait 3; mark; move 30; wait 3; zero move 30; state; move 30; wait 3;
 * quit"
 *
 * stdin 就是命令通道：换行与 ';' 等效，`wait <秒>` 与 `quit` 是语句；重定向 / here-string
 * 即脚本模式。 退出码：0 正常；1 参数错；2 打开串口失败；3 启动后收不到回复；4
 * 保护触发；128+信号（SIGINT = 130）。
 */

#include "motor/command.hpp"
#include "motor/format.hpp"
#include "motor/session.hpp"
#include "line_input.hpp"
#include "motor_unitree/unitree_transport.hpp"

#include <atomic>
#include <chrono>
#include <csignal>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <deque>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <unistd.h>

namespace
{

using motor::Counts;
using motor::DeviceCommand;
using motor::DeviceFeedback;
using motor::Session;
using motor::SessionConfig;

constexpr double kDt = 0.005; // 名义 5 ms/帧（实测约 6 ms，见旧版 docs/real.md §3.6）
constexpr int kZeroTorqueFrames = 20; // 收尾零力矩帧数
constexpr double kFirstReplyTimeoutS = 2.0;

volatile std::sig_atomic_t g_signal = 0;

/** 交互模式的输入行（非 TTY 时保持 inactive，全部方法都是空操作） */
motor_ctl::LineInput g_line_input;

/** 所有面向操作者的输出都走这里：交互模式下先清掉输入行、打完再重画 */
void emitf(const char* format, ...)
{
    va_list args;
    va_start(args, format);
    g_line_input.begin_output();
    std::vfprintf(stdout, format, args);
    g_line_input.end_output();
    va_end(args);
}

void handle_signal(int signum)
{
    g_signal = signum;
}

struct Options
{
    std::string port = "/dev/ttyUSB0";
    int id = 0;
    int baud = 4000000;
    SessionConfig session{};
    int print_every = 20;
    bool no_send = false;
};
void usage(const char* program)
{
    emitf("用法：%s [--port /dev/ttyUSB0] [--id N] [--baud N] [选项]\n", program);
    emitf(
        "  --port / --id / --baud       串口、电机 ID、波特率（默认 /dev/ttyUSB0、0、4000000）\n");
    emitf("  --kp-out / --kd-out          输出端增益（默认 kp=80、kd=3；下发时 ÷N²）\n");
    emitf("  --vmax-deg / --amax-deg      插值上限（默认 90 °/s、180 °/s²）\n");
    emitf("  --tol-deg                    到位判据（默认 1.0°）\n");
    emitf("  --tau-out-limit / --stall-s  力矩上限与“持续多久算卡住”（默认 1.5 N·m / 1.0 s）\n");
    emitf("  --temp-limit                 温度上限（默认 80 °C）\n");
    emitf("  --offline-frames             连续 N 帧无回复算失联（默认 40）\n");
    emitf("  --offset-deg                 软件零点偏移初值（默认 0；标定结果可写在这）\n");
    emitf("  --pose-ref <读数>            参考读数（约定启动姿态 / 记号线；如 14960tick 或 25.951deg）；\n");
    emitf("                               给了就做启动检查，护栏通过时自动对齐（D20）\n");
    emitf("  --no-auto-fix                关掉启动自动对齐（只打印检查、停在 gate 等命令）\n");
    emitf("  --fix-window-deg             自动对齐的位移窗口 W（默认 20°）\n");
    emitf("  --max-move-deg               单次 move / jog 的转角上限（默认 360°）\n");
    emitf("  --every N                    每 N 帧打印一行（默认 20）\n");
    emitf("  --no-send                    只打印配置，不打开串口\n");
    emitf("  --help                       本帮助\n\n%s", motor::command_help_text());
}

bool parse_options(int argc, char** argv, Options* options, bool* show_help)
{
    *show_help = false;
    for (int i = 1; i < argc; ++i)
    {
        const std::string argument = argv[i];
        const bool next = i + 1 < argc;
        if (argument == "--help" || argument == "-h")
        {
            *show_help = true;
        }
        else if (argument == "--no-send")
        {
            options->no_send = true;
        }
        else if (argument == "--port" && next)
        {
            options->port = argv[++i];
        }
        else if (argument == "--id" && next)
        {
            options->id = std::atoi(argv[++i]);
        }
        else if (argument == "--baud" && next)
        {
            options->baud = std::atoi(argv[++i]);
        }
        else if (argument == "--kp-out" && next)
        {
            options->session.kp_out = std::atof(argv[++i]);
        }
        else if (argument == "--kd-out" && next)
        {
            options->session.kd_out = std::atof(argv[++i]);
        }
        else if (argument == "--vmax-deg" && next)
        {
            options->session.vmax_deg_per_s = std::atof(argv[++i]);
        }
        else if (argument == "--amax-deg" && next)
        {
            options->session.amax_deg_per_s2 = std::atof(argv[++i]);
        }
        else if (argument == "--tol-deg" && next)
        {
            options->session.tol_deg = std::atof(argv[++i]);
        }
        else if (argument == "--tau-out-limit" && next)
        {
            options->session.tau_out_limit_nm = std::atof(argv[++i]);
        }
        else if (argument == "--stall-s" && next)
        {
            options->session.stall_s = std::atof(argv[++i]);
        }
        else if (argument == "--temp-limit" && next)
        {
            options->session.temp_limit_c = std::atoi(argv[++i]);
        }
        else if (argument == "--offline-frames" && next)
        {
            options->session.offline_frames = std::atoi(argv[++i]);
        }
        else if (argument == "--offset-deg" && next)
        {
            options->session.initial_offset = motor::output_deg_to_counts(std::atof(argv[++i]));
        }
        else if (argument == "--pose-ref" && next)
        {
            motor::Counts counts = 0;
            const std::string why = motor::parse_output_angle(argv[++i], &counts);
            if (!why.empty())
            {
                std::fprintf(stderr, "--pose-ref：%s\n", why.c_str());
                return false;
            }
            options->session.pose_ref_raw = counts;
        }
        else if (argument == "--no-auto-fix")
        {
            options->session.auto_fix = false;
        }
        else if (argument == "--fix-window-deg" && next)
        {
            options->session.fix_window_deg = std::atof(argv[++i]);
        }
        else if (argument == "--max-move-deg" && next)
        {
            options->session.max_move_deg = std::atof(argv[++i]);
        }
        else if (argument == "--every" && next)
        {
            options->print_every = std::atoi(argv[++i]);
        }
        else
        {
            std::fprintf(stderr, "未知参数：%s（--help 看用法）\n", argument.c_str());
            return false;
        }
    }
    return true;
}

/** stdin 读线程：按换行与 ';' 把输入切成语句，主循环按 wait 的门控取用 */
class StatementQueue
{
  public:
    void start()
    {
        std::thread([this] { read_loop(); }).detach();
    }

    /** 外部（交互模式的输入行）塞一条已经成行的语句 */
    void push(const std::string& statement)
    {
        std::lock_guard<std::mutex> lock(mutex_);
        pending_.push_back(statement);
    }

    bool try_pop(std::string* statement)
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (pending_.empty())
        {
            return false;
        }
        *statement = pending_.front();
        pending_.pop_front();
        return true;
    }

    bool finished()
    {
        std::lock_guard<std::mutex> lock(mutex_);
        return eof_ && pending_.empty();
    }

  private:
    void read_loop()
    {
        char buffer[512];
        std::string carry;
        while (true)
        {
            const ssize_t count = ::read(0, buffer, sizeof(buffer));
            if (count <= 0)
            {
                break;
            }
            carry.append(buffer, static_cast<size_t>(count));
            const size_t cut = carry.find_last_of(";\n\r");
            if (cut == std::string::npos)
            {
                continue;
            }
            const std::string chunk = carry.substr(0, cut + 1);
            carry.erase(0, cut + 1);
            for (const std::string& statement : motor::split_statements(chunk))
            {
                push(statement);
            }
        }
        for (const std::string& statement : motor::split_statements(carry))
        {
            push(statement);
        }
        std::lock_guard<std::mutex> lock(mutex_);
        eof_ = true;
    }

    std::mutex mutex_;
    std::deque<std::string> pending_;
    bool eof_ = false;
};

const char* link_name(motor::LinkState link)
{
    switch (link)
    {
    case motor::LinkState::kHandshake:
        return "握手";
    case motor::LinkState::kOnline:
        return "在线";
    case motor::LinkState::kOffline:
        return "离线";
    case motor::LinkState::kFault:
        return "故障";
    }
    return "?";
}

void print_config(const Options& options)
{
    const double gear_squared = motor::kGearRatio * motor::kGearRatio;
    emitf("=== motor_ctl（M4：可重启；启动检查 + 护栏通过时自动对齐）===\n");
    emitf("减速比 N = 19:3 = %.4f（SDK 报 6.33）⇒ 一个零点区间 = 32768 计数 = %.4f°（输出端）\n",
          motor::kGearRatio, motor::kZoneDegrees);
    emitf("1 计数 = %.7f°（输出端）；增益 kp=%.3g kd=%.3g → 转子侧 %.4f / %.5f\n",
          motor::counts_to_output_deg(1), options.session.kp_out, options.session.kd_out,
          options.session.kp_out / gear_squared, options.session.kd_out / gear_squared);
    emitf("vmax %.0f °/s、amax %.0f °/s²、到位 ±%.2f°；力矩上限 %.2f N·m / %.1f s；"
          "温度上限 %d °C；失联 %d 帧\n",
          options.session.vmax_deg_per_s, options.session.amax_deg_per_s2, options.session.tol_deg,
          options.session.tau_out_limit_nm, options.session.stall_s, options.session.temp_limit_c,
          options.session.offline_frames);
    emitf("软件零点偏移初值 %s\n",
          motor::format_output_angle(options.session.initial_offset).c_str());
    if (options.session.pose_ref_raw.has_value())
    {
        emitf("启动检查：参考 %s；自动对齐 %s（窗口 W = %.3g°）\n",
              motor::format_output_angle_with_counts(*options.session.pose_ref_raw).c_str(),
              options.session.auto_fix ? "开（护栏：首帧 raw ∈ [0, 32768) 且 |k| ≤ 1 且 |r| ≤ W）"
                                       : "关（--no-auto-fix：只报告、停在 gate）",
              options.session.fix_window_deg);
    }
    else
    {
        emitf("启动检查：未给 --pose-ref（不做检查；check / fix 也可以手动用参考）\n");
    }
    emitf("单次 move / jog 上限 %.4g°；fix 次数上限 %d\n", options.session.max_move_deg,
          options.session.max_fixes);
}

void print_frame_line(const Session& session, double now)
{
    const Counts q = session.q_now();
    const Counts target = session.target();
    const char* output = !session.have_feedback() ? "未对齐"
                         : !session.enabled()     ? "零力矩"
                                                  : "位置保持";
    emitf("帧 %5d t=%7.3f：raw %+8lld  q %s  目标 %s  差 %s  tau %+6.3f N·m  "
          "temp %3d  merror %u  %s\n",
          session.frames(), now, static_cast<long long>(session.last_raw()),
          motor::format_output_angle(q).c_str(), motor::format_output_angle(target).c_str(),
          motor::format_output_angle(target - q).c_str(), session.last_torque_nm(),
          session.last_temp_c(), session.last_merror(), output);
}

void print_state(const Session& session)
{
    const motor::Ledger& ledger = session.ledger();
    const Counts q = session.q_now();
    const Counts target = session.target();
    const Counts pos = ledger.raw_to_pos(session.last_raw());
    emitf("state：链路 %s；出力 %s；q %s（目标 %s，差 %s）\n", link_name(session.link_state()),
          session.enabled() ? "位置保持" : "零力矩", motor::format_output_angle(q).c_str(),
          motor::format_output_angle(target).c_str(),
          motor::format_output_angle(target - q).c_str());
    emitf("       raw %+lld 计数；turn_base %+lld；offset %+lld（%s）；离零点边界 %s\n",
          static_cast<long long>(session.last_raw()), static_cast<long long>(ledger.turn_base()),
          static_cast<long long>(ledger.offset()),
          motor::format_output_angle(ledger.offset()).c_str(),
          motor::format_output_angle(motor::distance_to_zone_edge(pos)).c_str());
    emitf("       事件 %zu 条", ledger.events().size());
    for (const motor::LedgerEvent& event : ledger.events())
    {
        emitf(" [%s %+lld]", motor::ledger_event_name(event.kind),
              static_cast<long long>(event.value));
    }
    emitf("\n");
    if (session.have_mark())
    {
        emitf("       标记点 q %s\n", motor::format_output_angle(session.mark_q()).c_str());
    }
}

} // namespace

int main(int argc, char** argv)
{
    Options options;
    bool show_help = false;
    if (!parse_options(argc, argv, &options, &show_help))
    {
        return 1;
    }
    if (show_help)
    {
        usage(argv[0]);
        return 0;
    }
    print_config(options);
    if (options.no_send)
    {
        emitf("--no-send：到此为止，没有打开串口、没有发任何字节。\n");
        return 0;
    }

    std::signal(SIGINT, handle_signal);
    std::signal(SIGTERM, handle_signal);

    std::string error;
    std::unique_ptr<motor::Transport> transport =
        motor_unitree::UnitreeTransport::open(options.port, options.id, options.baud, &error);
    if (transport == nullptr)
    {
        emitf("**串口打开失败**：%s\n", error.c_str());
        return 2;
    }
    emitf("串口已打开（%s：%s，id %d，%d baud）\n", transport->name(), options.port.c_str(),
          options.id, options.baud);

    Session session(options.session);
    StatementQueue queue;

    // 交互（stdin 是 TTY）：终端最后一行固定做输入行，自己回显与行编辑；
    // 非交互（脚本 / 管道）：仍用读线程按整行喂队列。
    bool interactive = ::isatty(0) != 0;
    if (interactive && !g_line_input.start(0))
    {
        interactive = false; // 进不了 raw 模式就退回普通读取
    }
    if (!interactive)
    {
        queue.start();
        emitf("stdin 非终端：按脚本模式执行（输入结束或 quit 后卸力退出）\n");
    }
    else
    {
        emitf("键盘就绪（输入 help 看命令；退格/Ctrl-U 编辑，Ctrl-D 或 quit 退出）\n");
    }

    const auto start_time = std::chrono::steady_clock::now();
    const auto elapsed = [&start_time] {
        return std::chrono::duration<double>(std::chrono::steady_clock::now() - start_time).count();
    };

    int exit_code = 0;
    int script_errors = 0;
    bool printed_startup = false;
    int last_arrived = -1;

    while (true)
    {
        const double now = elapsed();
        if (g_signal != 0)
        {
            emitf("收到信号 %d ⇒ 收尾\n", static_cast<int>(g_signal));
            exit_code = 128 + static_cast<int>(g_signal);
            break;
        }

        if (interactive)
        {
            std::string typed;
            if (g_line_input.poll(&typed))
            {
                for (const std::string& one : motor::split_statements(typed))
                {
                    queue.push(one); // 行内的 `;` 与脚本模式同样切分（D9）
                }
            }
        }
        if (session.can_apply(now))
        {
            std::string statement;
            if (queue.try_pop(&statement))
            {
                std::string parse_error;
                const motor::Command command = motor::parse_command(statement, &parse_error);
                emitf("命令：%s\n", statement.c_str());
                if (command.kind == motor::CommandKind::kHelp)
                {
                    emitf("%s", motor::command_help_text());
                }
                else if (command.kind == motor::CommandKind::kState)
                {
                    print_state(session);
                }
                else if (command.kind == motor::CommandKind::kUnknown)
                {
                    emitf("  → %s\n", parse_error.c_str());
                    ++script_errors;
                }
                else
                {
                    const motor::ApplyResult result = session.apply(command, now);
                    emitf("  → %s\n", result.message.c_str());
                    if (!result.ok)
                    {
                        ++script_errors;
                    }
                }
            }
        }

        session.step(kDt);
        DeviceFeedback feedback;
        bool received = false;
        try
        {
            received = transport->send(session.device_command(), &feedback);
        }
        catch (const std::exception& exception)
        {
            // 对端消失（实验台退出 / 真机上拔线）时 SDK 会抛异常而不是返回 false：
            // 按"保护触发"处理，走收尾零力矩路径（M1 只报警退出；自动恢复属 M3）。
            emitf("**传输异常**：%s\n", exception.what());
            session.on_feedback(nullptr, now);
            exit_code = 4; // 同"保护"：M1 只报警退出；自动恢复属 M3
            break;
        }
        session.on_feedback(received ? &feedback : nullptr, now);

        if (!printed_startup && session.ok_frames() > 0)
        {
            printed_startup = true;
            const Counts pos = session.ledger().raw_to_pos(session.last_raw());
            emitf("启动：板子读数 raw %+lld 计数（%s）—— 这就是它距“本次上电基准的编码器零点”"
                  "的距离；\n",
                  static_cast<long long>(session.last_raw()),
                  motor::format_output_angle(pos).c_str());
            emitf("      默认 offset = 0，软件零点与该点重合：move 0 会转回它。"
                  "现在就在输出端打记号笔标记（任务书 ②）。\n");
            if (!session.startup_report().empty())
            {
                emitf("%s\n", session.startup_report().c_str());
            }
            if (session.awaiting_confirm())
            {
                emitf("**已停下等确认**（零力矩）：确认位置后发 hold / move / jog / zero move / fix 之一继续。\n");
            }
        }

        if (session.faulted())
        {
            emitf("**保护触发**：%s\n", session.fault_reason().c_str());
            exit_code = 4;
            break;
        }

        if (!printed_startup && now > kFirstReplyTimeoutS)
        {
            emitf("**启动 %.0f s 内一帧回复都没收到**：检查 ID、接线（TX/RX/共地）、供电、"
                  "权限（sudo 或 dialout）。\n",
                  kFirstReplyTimeoutS);
            exit_code = 3;
            break;
        }

        if (session.quit_requested())
        {
            break;
        }
        if (printed_startup && queue.finished() && session.can_apply(now))
        {
            emitf("输入结束 ⇒ 收尾\n");
            break;
        }

        const int arrived = session.arrived() ? 1 : 0;
        if (arrived != last_arrived)
        {
            last_arrived = arrived;
            if (arrived == 1)
            {
                emitf("  ⇒ 到位（|差| ≤ %.2f°），保持中\n", options.session.tol_deg);
            }
        }
        if (session.frames() % options.print_every == 0)
        {
            print_frame_line(session, now);
        }

        ::usleep(static_cast<useconds_t>(kDt * 1e6));
    }

    // 收尾：先恢复终端（把输入行交还给 shell），再卸力、打印汇总
    g_line_input.finish();

    // 收尾：先卸力（S2e 实测：驱动板不会自己卸力），再打印汇总
    int zero_frames = 0;
    for (int i = 0; i < kZeroTorqueFrames; ++i)
    {
        DeviceFeedback feedback;
        try
        {
            if (!transport->send(DeviceCommand{}, &feedback))
            {
                break;
            }
        }
        catch (const std::exception&)
        {
            break; // 对端已经不在了：收尾尽力而为
        }
        ++zero_frames;
        ::usleep(5000);
    }
    emitf("收尾：已发 %d 帧零力矩\n", zero_frames);
    emitf("=== 汇总 ===\n");
    emitf("帧 %d（回复 %d、超时 %d）；q 末值 %s；offset %+lld（%s）；turn_base %+lld；"
          "事件 %zu 条；对齐 %d 次；力矩峰值 %.3f N·m；温度峰值 %d °C；末次 merror %u\n",
          session.frames(), session.ok_frames(), session.timeouts(),
          motor::format_output_angle(session.q_now()).c_str(),
          static_cast<long long>(session.ledger().offset()),
          motor::format_output_angle(session.ledger().offset()).c_str(),
          static_cast<long long>(session.ledger().turn_base()), session.ledger().events().size(),
          session.fixes(), session.torque_peak_nm(), session.temp_peak_c(), session.last_merror());
    if (!interactive && script_errors > 0 && exit_code == 0)
    {
        emitf("（脚本模式：有 %d 条语句没执行成功 ⇒ 退出码 2）\n", script_errors);
        exit_code = 2;
    }
    return exit_code;
}
