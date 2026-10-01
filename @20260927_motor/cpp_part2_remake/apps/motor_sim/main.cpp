/**
 * @file main.cpp
 * @brief motor_sim：虚拟实验台（M2b）——PTY 冒充串口，另一头跑真实 SDK 的控制程序。
 *
 * 用法（两个终端）：
 *   终端 2（本程序）：motor_sim
 *     建一对 PTY，打印 slave 路径（如 /dev/pts/3）；本终端的 REPL 可以直接摆弄"电机"：
 *     torque <N·m>（给定力矩扳输出端；自由轴上会加速到最高转速）· hold [<角度>]（手握住）
 *     · release · line draw|angle|clear
 *     （记号线与实时夹角）· status · wait <s> · help · quit
 *   终端 1（控制程序，不需要 sudo）：
 *     LD_PRELOAD=<build>/tools/pty_shim/libpty_serial_shim.so \
 *       <build>/apps/motor_ctl/motor_ctl --port /dev/pts/3
 *
 * 物理模型在 sim/model.cpp（与旧版假电机同一套）；报文编解码在 wire/（与实机同一份结构体与 CRC）。
 */

#include "motor/command.hpp"
#include "motor/counts.hpp"
#include "motor/format.hpp"
#include "motor_sim/model.hpp"
#include "motor_wire/wire.hpp"

#include <algorithm>
#include <atomic>
#include <cerrno>
#include <chrono>
#include <cmath>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <fcntl.h>
#include <mutex>
#include <poll.h>
#include <string>
#include <thread>
#include <unistd.h>
#include <vector>

namespace
{

volatile std::sig_atomic_t g_signal = 0;

void handle_signal(int signum)
{
    g_signal = signum;
}

struct Options
{
    double frame_period = 0.005; // 模型积分的名义步长（秒；收到帧时用实测间隔，空闲时用它）
    double print_interval_s = 1.0; // 周期状态打印的间隔（秒；0 = 关闭周期打印）
};

void usage(const char* program)
{
    std::printf("用法：%s [--print-interval <秒>] [--frame-period <秒>]\n", program);
    std::printf("  --print-interval  周期状态打印的间隔（默认 1.0；0 = 关闭，日志更干净）\n");
    std::printf("  --frame-period    空闲推进的名义步长（默认 0.005 s；一般不用改）\n");
    std::printf("本程序建一对 PTY 并在另一头模拟 GO-M8010-6：把打印出来的 slave 路径交给\n");
    std::printf(
        "motor_ctl（配合 tools/pty_shim 的 LD_PRELOAD）即可。REPL 命令见下：\n\n%s",
        "  status                    模型与线的状态\n"
        "  torque <N·m>              以给定力矩扳动输出端（正方向 = 输出角增大；自由轴上会一直加速，\n"
        "                            到最高转速（约 271 °/s 输出端）为止；想模拟手扳请用 hold）\n"
        "  hold [<角度>[deg|rad|r]]  手握住：软弹簧拉向该输出角（无参 = 保持当前角）\n"
        "  release                   松手\n"
        "  line draw|angle|clear     记号线：在当前位置画线 / 查夹角 / 擦掉\n"
        "  wait <秒>                 推迟后续语句\n"
        "  help | quit               本帮助 / 退出（会把 PTY 一并关掉）\n");
}

bool parse_options(int argc, char** argv, Options* options, bool* show_help)
{
    *show_help = false;
    for (int i = 1; i < argc; ++i)
    {
        const std::string argument = argv[i];
        if (argument == "--help" || argument == "-h")
        {
            *show_help = true;
        }
        else if (argument == "--frame-period" && i + 1 < argc)
        {
            options->frame_period = std::atof(argv[++i]);
        }
        else if (argument == "--print-interval" && i + 1 < argc)
        {
            options->print_interval_s = std::atof(argv[++i]);
            if (options->print_interval_s < 0.0)
            {
                std::fprintf(stderr, "--print-interval 不能为负（0 = 关闭周期打印）\n");
                return false;
            }
        }
        else
        {
            std::fprintf(stderr, "未知参数：%s（--help 看用法）\n", argument.c_str());
            return false;
        }
    }
    return true;
}

/** 开一对 PTY：返回 slave 设备名（给 SDK 当串口），master 由实验台拿去做"驱动板" */
std::string make_pty(int* master)
{
    const int fd = posix_openpt(O_RDWR | O_NOCTTY);
    if (fd < 0)
    {
        std::perror("posix_openpt");
        return std::string();
    }
    grantpt(fd);
    unlockpt(fd);
    *master = fd;
    return std::string(ptsname(fd));
}

/** 模型 + PTY 线程 + REPL 共享的状态 */
class Bench
{
  public:
    explicit Bench(const Options& options) : options_(options) {}

    std::mutex* mutex() { return &mutex_; }
    motor_sim::MotorModel* model() { return &model_; }

    void start_pty_thread(int master_fd)
    {
        thread_ = std::thread([this, master_fd] { pty_loop(master_fd); });
    }

    void stop()
    {
        stop_ = true;
        if (thread_.joinable())
        {
            thread_.join();
        }
    }

  private:
    void pty_loop(int master_fd)
    {
        std::uint8_t buffer[motor_wire::kCommandSize];
        std::size_t got = 0;
        auto last = std::chrono::steady_clock::now();
        // 板子收不到命令时**继续执行最后一条指令**（S2e
        // 实测：断链后驱动板不卸力）。否则单独用实验台 （没有控制程序在跑）时给力矩 /
        // 握住都不会动，和真实电机的手感对不上。
        const double nominal_dt = options_.frame_period;
        motor::DeviceCommand last_command; // 默认 = 零力矩（还没收到任何命令时不动）
        while (!stop_)
        {
            // 用 poll 等数据（而不是直接阻塞 read）：这样 stop_ 一到就能退出，不会卡在关闭流程里
            struct pollfd descriptor;
            descriptor.fd = master_fd;
            descriptor.events = POLLIN;
            descriptor.revents = 0;
            const int ready = ::poll(&descriptor, 1, 5);
            if (ready < 0)
            {
                if (errno == EINTR)
                {
                    continue;
                }
                break;
            }
            if (ready == 0)
            {
                const auto now = std::chrono::steady_clock::now();
                const double idle = std::chrono::duration<double>(now - last).count();
                if (idle >= nominal_dt)
                {
                    last = now;
                    std::lock_guard<std::mutex> lock(mutex_);
                    model_.step(last_command, std::min(idle, 0.02));
                }
                continue; // 超时：回去看 stop_
            }
            const ssize_t count = ::read(master_fd, buffer + got, sizeof(buffer) - got);
            if (count <= 0)
            {
                if (count < 0 && errno == EINTR)
                {
                    continue;
                }
                break; // 主程序关闭 master（退出）或出错
            }
            got += static_cast<std::size_t>(count);
            if (got != sizeof(buffer))
            {
                continue;
            }
            got = 0;

            const auto now = std::chrono::steady_clock::now();
            double dt = std::chrono::duration<double>(now - last).count();
            last = now;
            dt = std::clamp(dt, 0.0, 0.02); // 防守：突然空转一大段时不要把状态推飞

            motor_wire::CommandMeta meta;
            const motor::DeviceCommand command = motor_wire::decode_command(buffer, &meta);
            last_command = command;
            motor::DeviceFeedback feedback;
            {
                std::lock_guard<std::mutex> lock(mutex_);
                if (!meta.crc_ok)
                {
                    ++crc_errors_;
                }
                model_.step(command, dt);
                feedback = model_.feedback();
            }
            std::uint8_t reply[motor_wire::kReplySize];
            motor_wire::encode_reply(feedback, meta.id, motor_wire::kStatusFoc, reply);
            if (::write(master_fd, reply, sizeof(reply)) != static_cast<ssize_t>(sizeof(reply)))
            {
                std::printf("**PTY 回帧写失败**：控制程序可能已经退出\n");
                break;
            }
            ++rx_frames_;
        }
    }

    Options options_;
    std::mutex mutex_;
    motor_sim::MotorModel model_;
    std::thread thread_;
    std::atomic<bool> stop_{false};
    std::atomic<long> rx_frames_{0};
    std::atomic<long> crc_errors_{0};

  public:
    long rx_frames() const { return rx_frames_.load(); }
    long crc_errors() const { return crc_errors_.load(); }
    double frame_period() const { return options_.frame_period; }
    double print_interval_s() const { return options_.print_interval_s; }
};

std::string format_plain_deg(double deg)
{
    char buffer[32];
    std::snprintf(buffer, sizeof(buffer), "%+.3f°", deg);
    return std::string(buffer);
}

void print_status(Bench& bench, double now)
{
    motor_sim::MotorModel& model = *bench.model();
    std::printf("[t=%7.3f] 模型：输出角 %s（转子 %lld 计数）；转速 %s/s；力矩 %+.3f N·m（输出端）；"
                "温度 %d °C；帧 %ld（CRC 错 %ld）\n",
                now, motor::format_output_angle(model.true_counts()).c_str(),
                static_cast<long long>(model.true_counts()),
                format_plain_deg(model.output_speed_deg_s()).c_str(),
                model.torque_rotor_nm() * motor::kGearRatio, model.temp_c(), bench.rx_frames(),
                bench.crc_errors());
    switch (model.interaction())
    {
    case motor_sim::Interaction::kNone:
        break;
    case motor_sim::Interaction::kTorque:
        std::printf("      交互：恒力矩 %+.3f N·m（输出端）\n", model.torque_command_out_nm());
        break;
    case motor_sim::Interaction::kHold:
        std::printf("      交互：握住 %s（输出端）\n",
                    format_plain_deg(model.hold_target_out_deg()).c_str());
        break;
    }
    if (model.has_line())
    {
        const motor::Counts cumulative = motor::output_deg_to_counts(model.line_cumulative_deg());
        std::printf("      记号线：缠绕 %s，累计 %s\n",
                    format_plain_deg(model.line_wrapped_deg()).c_str(),
                    motor::format_output_angle(cumulative).c_str());
    }
    else
    {
        std::printf("      记号线：无（line draw 画线）\n");
    }
}

void print_compact_status(Bench& bench, double now)
{
    motor_sim::MotorModel& model = *bench.model();
    std::printf("[t=%7.3f] 输出角 %s  转速 %s/s  力矩 %+.3f N·m（输出）  帧 %ld\n", now,
                motor::format_output_angle(model.true_counts()).c_str(),
                format_plain_deg(model.output_speed_deg_s()).c_str(),
                model.torque_rotor_nm() * motor::kGearRatio, bench.rx_frames());
}

class StatementQueue
{
  public:
    void start()
    {
        std::thread([this] { read_loop(); }).detach();
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

  private:
    void push(const std::string& statement)
    {
        std::lock_guard<std::mutex> lock(mutex_);
        pending_.push_back(statement);
    }

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
            carry.append(buffer, static_cast<std::size_t>(count));
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
    }

    std::mutex mutex_;
    std::deque<std::string> pending_;
};

bool parse_double(const std::string& text, double* value)
{
    char* end = nullptr;
    const double parsed = std::strtod(text.c_str(), &end);
    if (end == text.c_str() || *end != '\0' || !std::isfinite(parsed))
    {
        return false;
    }
    *value = parsed;
    return true;
}

std::vector<std::string> split_words(const std::string& text)
{
    std::vector<std::string> words;
    std::string current;
    for (char c : text)
    {
        if (std::isspace(static_cast<unsigned char>(c)) != 0)
        {
            if (!current.empty())
            {
                words.push_back(current);
                current.clear();
            }
        }
        else
        {
            current.push_back(c);
        }
    }
    if (!current.empty())
    {
        words.push_back(current);
    }
    return words;
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

    std::signal(SIGINT, handle_signal);
    std::signal(SIGTERM, handle_signal);
    std::setvbuf(stdout, nullptr, _IOLBF,
                 0); // 行缓冲：管道里也能按时刷出来（与 run_log.sh 的 stdbuf 同理）

    int master_fd = -1;
    const std::string slave = make_pty(&master_fd);
    if (slave.empty())
    {
        return 2;
    }
    std::printf("=== motor_sim：虚拟实验台（PTY + GO-M8010-6 模型）===\n");
    std::printf("PTY slave：%s\n", slave.c_str());
    std::printf("另一个终端跑控制程序（不需要 sudo；垫片让 SDK 认 PTY）：\n");
    // 尽量打印可直接复制粘贴的一行：可用路径按本程序自己的位置（/proc/self/exe）推算
    std::string control_command;
    {
        char buffer[4096];
        const ssize_t length = ::readlink("/proc/self/exe", buffer, sizeof(buffer) - 1);
        if (length > 0)
        {
            buffer[length] = '\0';
            std::string path(buffer);
            const size_t slash = path.find_last_of('/');
            const std::string dir =
                (slash == std::string::npos) ? std::string() : path.substr(0, slash);
            const std::string motor_ctl = dir + "/../motor_ctl/motor_ctl";
            const std::string shim = dir + "/../../tools/pty_shim/libpty_serial_shim.so";
            char real_ctl[4096];
            char real_shim[4096];
            if (!dir.empty() && ::realpath(motor_ctl.c_str(), real_ctl) != nullptr &&
                ::realpath(shim.c_str(), real_shim) != nullptr)
            {
                control_command =
                    std::string("LD_PRELOAD=") + real_shim + " " + real_ctl + " --port " + slave;
            }
        }
    }
    if (!control_command.empty())
    {
        std::printf("  %s\n", control_command.c_str());
        std::printf("（上面这一行可直接复制到另一个终端；路径按本程序的构建位置推算）\n\n");
    }
    else
    {
        std::printf("  LD_PRELOAD=<build>/tools/pty_shim/libpty_serial_shim.so "
                    "<build>/apps/motor_ctl/motor_ctl --port %s\n\n",
                    slave.c_str());
    }
    std::printf("本终端：status / torque / hold / release / line / wait / help / quit\n");

    Bench bench(options);
    bench.start_pty_thread(master_fd);

    StatementQueue queue;
    queue.start();
    const bool interactive = ::isatty(0) != 0;
    std::printf(
        interactive
            ? "键盘就绪（help 看命令；quit 或 Ctrl-C 结束）\n"
            : "stdin 非终端：执行完语句后**不会**自动退出（设备进程）；用 quit / Ctrl-C 结束\n");

    const auto start_time = std::chrono::steady_clock::now();
    const auto elapsed = [&start_time] {
        return std::chrono::duration<double>(std::chrono::steady_clock::now() - start_time).count();
    };
    double next_allowed = 0.0;
    const double print_interval = bench.print_interval_s();
    double next_print = (print_interval > 0.0) ? elapsed() + print_interval : 0.0;
    int errors = 0;
    bool quit = false;

    while (!quit && g_signal == 0)
    {
        const double now = elapsed();
        if (now >= next_allowed)
        {
            std::string statement;
            if (queue.try_pop(&statement))
            {
                const std::vector<std::string> words = split_words(statement);
                std::printf("命令：%s\n", statement.c_str());
                std::lock_guard<std::mutex> lock(*bench.mutex());
                motor_sim::MotorModel& model = *bench.model();
                const auto fail = [&](const std::string& why)
                {
                    std::printf("  → %s\n", why.c_str());
                    ++errors;
                };
                if (words.empty())
                {
                    // 空语句不会进队列
                }
                else if (words[0] == "help")
                {
                    usage(argv[0]);
                }
                else if (words[0] == "status")
                {
                    print_status(bench, now);
                }
                else if (words[0] == "quit")
                {
                    std::printf("  → 退出（PTY 关闭，控制程序会看到超时）\n");
                    quit = true;
                }
                else if (words[0] == "torque" && words.size() == 2)
                {
                    double value = 0.0;
                    if (!parse_double(words[1], &value))
                    {
                        fail("torque 要一个数（输出端 N·m）");
                    }
                    else
                    {
                        model.apply_torque_out(value);
                        std::printf(
                            "  → 恒力矩 %+.3f N·m（输出端）；注意自由轴上恒力矩会一直加速\n",
                            model.torque_command_out_nm());
                    }
                }
                else if (words[0] == "hold" && words.size() <= 2)
                {
                    double deg = model.output_deg();
                    bool ok = true;
                    if (words.size() == 2)
                    {
                        motor::Counts counts = 0;
                        const std::string why = motor::parse_output_angle(words[1], &counts);
                        if (!why.empty())
                        {
                            fail(why);
                            ok = false;
                        }
                        else
                        {
                            deg = motor::counts_to_output_deg(counts);
                        }
                    }
                    if (ok)
                    {
                        model.hold_output_deg(deg);
                        std::printf("  → 握住 %s（输出端）\n", format_plain_deg(deg).c_str());
                    }
                }
                else if (words[0] == "release")
                {
                    model.release();
                    std::printf("  → 松手\n");
                }
                else if (words[0] == "line")
                {
                    if (words.size() == 2 && words[1] == "draw")
                    {
                        model.draw_line();
                        std::printf("  → 已在输出角 %s 画线\n",
                                    format_plain_deg(model.output_deg()).c_str());
                    }
                    else if (words.size() == 2 && words[1] == "angle")
                    {
                        if (!model.has_line())
                        {
                            fail("还没画线（line draw）");
                        }
                        else
                        {
                            const motor::Counts cumulative =
                                motor::output_deg_to_counts(model.line_cumulative_deg());
                            std::printf("  → 线夹角：缠绕 %s；累计 %s\n",
                                        format_plain_deg(model.line_wrapped_deg()).c_str(),
                                        motor::format_output_angle(cumulative).c_str());
                        }
                    }
                    else if (words.size() == 2 && words[1] == "clear")
                    {
                        model.clear_line();
                        std::printf("  → 线已擦掉\n");
                    }
                    else
                    {
                        fail("line 的用法：line draw | line angle | line clear");
                    }
                }
                else if (words[0] == "wait" && words.size() == 2)
                {
                    double seconds = 0.0;
                    if (!parse_double(words[1], &seconds) || seconds < 0.0)
                    {
                        fail("wait 的秒数不合法");
                    }
                    else
                    {
                        next_allowed = now + seconds;
                        std::printf("  → 等 %.2f s\n", seconds);
                    }
                }
                else
                {
                    fail("没看懂：" + statement + "（help 看命令）");
                }
            }
        }

        if (print_interval > 0.0 && now >= next_print)
        {
            next_print = now + print_interval;
            std::lock_guard<std::mutex> lock(*bench.mutex());
            print_compact_status(bench, now);
        }
        ::usleep(20000); // 20 ms 轮询：REPL 手感与 CPU 占用折中
    }

    if (g_signal != 0)
    {
        std::printf("收到信号 %d ⇒ 退出\n", static_cast<int>(g_signal));
    }
    ::close(master_fd); // 让 PTY 线程的 read 返回
    bench.stop();
    std::printf("=== 汇总：收到 %ld 帧（CRC 错 %ld）===\n", bench.rx_frames(), bench.crc_errors());
    return (g_signal != 0) ? 128 + static_cast<int>(g_signal)
                           : (errors > 0 && !interactive ? 2 : 0);
}
