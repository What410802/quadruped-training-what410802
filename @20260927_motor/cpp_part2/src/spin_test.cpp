// 实机 S1：让电机**慢速、有斜坡地**转起来（任务书第二部分第 1 条），并逐步告诉你在干什么。
//
// 与官方例程 `example/example_goM8010_6_motor.cpp` 的区别（那份也能跑，但不适合第一次上手）：
//   * 官方：`kd=0.01`（转子侧）、`dq = -6.28*N`（转子侧）= **输出端 1 圈/s（360°/s）**，while(true) 一直转，
//     没有斜坡、没有限幅、没有错误处理、Ctrl-C 之后驱动板手上的最后一条指令是什么也没管；
//   * 本程序：速度指令从 0 用 smoothstep **插值**升到目标（默认输出端 0.25 圈/s = 90°/s），保持几秒，
//     再插值降回 0，最后发 1 s 的"零速度"再退出；全程检查 `merror`/温度/超时，出错就立刻收速度。
//
// 速度指令是**速度环**：`kp=0、tau=0、q=0`，只给 `kd`（阻尼/速度刚度）与 `dq`，
// 即 τ = kd·(dq_des − dq)：不转的时候相当于阻尼模式，转起来时是速度控制 —— 手上不会被"硬顶"。
//
// 编译（仓库根目录）：
//   S=../ReadOnly.d/unitree_actuator_sdk
//   g++ -O2 -std=c++14 -I$S/include -I$S/include/unitreeMotor @20260927_motor/cpp_part2/src/spin_test.cpp -L$S/lib -lUnitreeMotorSDK_Linux64 -Wl,-rpath,"$PWD/$S/lib" -pthread -o /tmp/spin_test
//
// 用法（**需要 sudo**，而且电机要固定好、手上别拿东西）：
//   sudo /tmp/spin_test --port /dev/ttyUSB0 --id 0 --rev-per-s 0.1 --ramp 2 --hold 3
//   sudo /tmp/spin_test ... --no-send        # 只打印"将要下发什么"，一个字节都不发
//   LD_PRELOAD=/tmp/pty_serial_shim.so /tmp/spin_test --self-test   # 无硬件自检：PTY + 假电机，看真转速
//
// 退出码：0 正常；3 一帧回复都没收到；4 电机报错/温度高；5 中途掉线；1 参数错。

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cmath>
#include <string>

#include <chrono>
#include <unistd.h>

#include <vector>

#include "serialPort/SerialPort.h"
#include "unitreeMotor/unitreeMotor.h"

#include "sim/fake_motor.h"   // 只在 --self-test 里用到（src/sim/ = 不控制实机的代码）

#include <atomic>
#include <thread>

namespace {

struct Options {
    std::string port = "/dev/ttyUSB0";
    int id = 0;
    double rev_per_s = 0.25; // 输出端圈/秒（正负决定方向）
    double kd_out = 0.5;     // 输出端速度刚度 [N·m·s/rad]（转子侧 = kd_out/N²）
    double ramp = 2.0;       // 升/降速各用多少秒
    double hold = 3.0;       // 目标速度保持多少秒
    bool no_send = false;
    bool self_test = false;  // 用 PTY + 假电机自检（需要 LD_PRELOAD=pty_serial_shim.so）
};

void Usage(const char *prog) {
    std::printf("用法：%s [--port /dev/ttyUSB0] [--id N] [--rev-per-s R] [--kd-out K] [--ramp S] [--hold S] [--no-send]\n"
                "  --rev-per-s  输出端目标转速，圈/秒（默认 0.25 = 90°/s；负号反向；|R|>1 会被拒）\n"
                "  --kd-out     输出端速度刚度（默认 0.5 N·m·s/rad；转子侧自动 ÷N²）\n"
                "  --ramp/--hold  升/降速各 SEC 秒、目标保持 SEC 秒\n"
                "  --no-send    只打印将要下发的指令，不打开串口、不发字节\n"
                "  --self-test  无硬件自检：自己开一对 PTY、另一头放假电机（需要 LD_PRELOAD=pty_serial_shim.so）\n",
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
        else if (a == "--port" && next)
            o->port = argv[++i];
        else if (a == "--id" && next)
            o->id = std::atoi(argv[++i]);
        else if (a == "--rev-per-s" && next)
            o->rev_per_s = std::atof(argv[++i]);
        else if (a == "--kd-out" && next)
            o->kd_out = std::atof(argv[++i]);
        else if (a == "--ramp" && next)
            o->ramp = std::atof(argv[++i]);
        else if (a == "--hold" && next)
            o->hold = std::atof(argv[++i]);
        else {
            std::fprintf(stderr, "未知参数：%s\n", a.c_str());
            return false;
        }
    }
    if (std::fabs(o->rev_per_s) > 1.0) {
        std::fprintf(stderr, "--rev-per-s 太大：%.3f（第一次上手请 ≤ 0.25；本程序拒绝 |R| > 1）\n",
                     o->rev_per_s);
        return false;
    }
    if (o->ramp < 0.0 || o->hold < 0.0 || o->kd_out < 0.0) {
        std::fprintf(stderr, "--ramp/--hold/--kd-out 不能为负\n");
        return false;
    }
    return true;
}

double Smoothstep(double u) {
    if (u <= 0.0)
        return 0.0;
    if (u >= 1.0)
        return 1.0;
    return u * u * (3.0 - 2.0 * u);
}

} // namespace

int main(int argc, char **argv) {
    Options opt;
    if (!Parse(argc, argv, &opt)) {
        Usage(argv[0]);
        return 1;
    }
    const double N = queryGearRatio(MotorType::GO_M8010_6);
    const double w_out = opt.rev_per_s * 2.0 * M_PI;      // 输出端 rad/s
    const double w_rotor = w_out * N;                     // 转子侧 rad/s（要下发的 cmd.dq）
    const double kd_rotor = opt.kd_out / (N * N);         // 转子侧（要下发的 cmd.kd）
    const double total = 2.0 * opt.ramp + opt.hold + 1.0; // 含最后 1 s 收速度

    std::printf("=== 这次会下发什么（GO-M8010-6，N=%.3f）===\n", N);
    std::printf("  模式：FOC（mode=%d，就是讲义 §1.3 的\"速度模式\"：T=0、Pos=0、K_P=0、W≠0、K_W>0）\n",
                queryMotorMode(MotorType::GO_M8010_6, MotorMode::FOC));
    std::printf("  cmd.id   = %d\n", opt.id);
    std::printf("  cmd.kp   = 0            （位置刚度，输出端 0）\n");
    std::printf("  cmd.kd   = %.6f      （输出端 %.3g N·m·s/rad ÷ N² → 转子侧）\n", kd_rotor,
                opt.kd_out);
    std::printf("  cmd.tau  = 0            （前馈力矩）\n");
    std::printf("  cmd.q    = 0            （位置项不用，因为 kp=0）\n");
    std::printf("  cmd.dq   = 0 → %.4f    （转子侧 rad/s；输出端 %.4f 圈/s = %.1f °/s，方向%s）\n",
                w_rotor, opt.rev_per_s, opt.rev_per_s * 360.0, opt.rev_per_s > 0 ? "正" : "负");
    std::printf("  时序：%.1f s 升速（smoothstep）→ %.1f s 保持 → %.1f s 降回 0 → 再发 1 s 零速度后退出"
                "（共 %.1f s）\n",
                opt.ramp, opt.hold, opt.ramp, total);
    // 报文里最终长什么样：用实测标度反算（SDK 打包是**截断**不是四舍五入，见 ../README.md §4）
    {
        const auto trunc_raw = [](double x, double scale) { return static_cast<long>(x * scale); };
        std::printf("  报文（每帧 17 字节，200 Hz 下发）：head=fe ee、mode=0x%02x（id=%d、status=1 FOC）、"
                    "tor_des=%ld、spd_des=%ld、pos_des=%ld、k_pos=%ld、k_spd=%ld、CRC16\n",
                    static_cast<unsigned>((1U << 4) | static_cast<unsigned>(opt.id)),
                    opt.id, trunc_raw(0.0, 256.0), trunc_raw(w_rotor, 128.0 / M_PI),
                    trunc_raw(0.0, 32768.0 / (2.0 * M_PI)), trunc_raw(0.0, 1280.0),
                    trunc_raw(kd_rotor, 1280.0));
        std::printf("        （spd_des 在升/降速期间从 0 连续变到这个值；k_spd=%ld 只是它 1 LSB = 1/1280，"
                    "所以输出端 kd=%.3g 这种小阻尼在报文里很粗（量化误差 ~%.1f%%））\n",
                    trunc_raw(kd_rotor, 1280.0), opt.kd_out,
                    100.0 * (1.0 / 1280.0) / std::max(1e-9, kd_rotor));
    }
    std::printf("  电机侧效果：通电后先保持不动（kd 阻尼），随后缓慢加速到目标转速，中段匀速，然后缓慢停下。\n");
    std::printf("  **注意**：驱动板在\"收不到指令\"时会怎样（保持最后一条指令 / 自己卸力）**没有实测**，\n"
                "           所以退出前会先发 1 s 零速度；即便如此，第一次请把电机固定好、随时能断电。\n");
    if (opt.no_send) {
        std::printf("--no-send：到此为止，没有打开串口、没有发任何字节。\n");
        return 0;
    }

    SerialPort *serial = nullptr;
    std::thread fake_motor;
    std::atomic<bool> fake_stop{false};
    try {
        if (opt.self_test) {
            int master = -1;
            const std::string slave = fakemotor::MakePty(&master);
            if (slave.empty())
                return 1;
            std::printf("自检：PTY slave=%s（假电机在另一头）——下面看到的转速/位置是假电机跑出来的\n",
                        slave.c_str());
            fakemotor::Model model;
            fake_motor = fakemotor::Start(master, &fake_stop, model);
            serial = new SerialPort(slave, 16, 4000000);
        } else {
            serial = new SerialPort(opt.port, 16, 4000000);
        }
    } catch (const std::exception &e) {
        std::printf("**SerialPort 构造失败**：%s\n", e.what());
        return 2;
    }
    std::printf("串口已打开（%s，4 Mbaud）——开始发指令\n",
                opt.self_test ? "自检 PTY" : opt.port.c_str());

    MotorCmd cmd;
    MotorData data;
    cmd.motorType = MotorType::GO_M8010_6;
    data.motorType = MotorType::GO_M8010_6;
    cmd.mode = queryMotorMode(MotorType::GO_M8010_6, MotorMode::FOC);
    cmd.id = opt.id;
    cmd.kp = 0.0;
    cmd.kd = kd_rotor;
    cmd.q = 0.0;
    cmd.tau = 0.0;

    const double dt = 0.005; // 5 ms 一帧（200 Hz）
    int frames = 0, timeouts = 0, timeout_streak = 0, ok_frames = 0;
    double dq_min = 1e9, dq_max = -1e9, q_first = 0.0, q_last = 0.0;
    int temp_max = -128;
    unsigned merror_last = 0;
    bool have_reply = false;
    int exit_code = 0;
    std::string last_phase;
    // 阶段标记（帧号 / 转子位置 / **墙钟**）：名义 5 ms 一帧只是我们自己的定时，
    // 真实周期会被 usleep 的粒度与调度拉长（实测 ~5.6 ms），而"物理转速"只能用墙钟算，
    // 所以每次阶段切换都把墙钟与位置一起记下来。
    struct Mark { std::string name; int frame; double q; double wall; };
    std::vector<Mark> marks;
    const auto wall0 = std::chrono::steady_clock::now();
    const auto wall_now = [&wall0] {
        return std::chrono::duration<double>(std::chrono::steady_clock::now() - wall0).count();
    };

    for (double t = 0.0; t < total; t += dt) {
        // 目标输出端速度：升 → 保持 → 降 → 0
        double u;
        const char *phase;
        if (t < opt.ramp) {
            u = Smoothstep(t / opt.ramp);
            phase = "升速";
        } else if (t < opt.ramp + opt.hold) {
            u = 1.0;
            phase = "保持";
        } else if (t < 2.0 * opt.ramp + opt.hold) {
            u = 1.0 - Smoothstep((t - opt.ramp - opt.hold) / opt.ramp);
            phase = "降速";
        } else {
            u = 0.0;
            phase = "收速度（零速度）";
        }
        cmd.dq = w_rotor * u;

        const bool ok = serial->sendRecv(&cmd, &data);
        ++frames;
        if (ok) {
            ++ok_frames;
            timeout_streak = 0;
            const double dq_out = data.dq / N / (2.0 * M_PI); // 输出端 圈/s
            dq_min = std::min(dq_min, dq_out);
            dq_max = std::max(dq_max, dq_out);
            if (ok_frames <= 2)
                q_first = data.q;
            q_last = data.q;
            temp_max = std::max(temp_max, static_cast<int>(data.temp));
            merror_last = data.merror;
            have_reply = true;
        } else {
            ++timeouts;
            if (++timeout_streak == 20) {
                std::printf("**连续 20 帧没回复**：停下（可能是线松了/ID 不对/波特率）。\n");
                exit_code = 5;
                break;
            }
        }

        // 阶段切换时打一行汇总（升速 → 保持 → 降速 → 收速度）
        if (last_phase != phase) {
            std::printf("[t=%5.2f s|墙钟 %5.2f s] 阶段 → %s：cmd.dq=%.4f rad/s（转子）、输出端目标 %.3f 圈/s；"
                        "已发 %d 帧、收到 %d 帧\n",
                        t, wall_now(), phase, cmd.dq, cmd.dq / N / (2.0 * M_PI), frames, ok_frames);
            last_phase = phase;
            marks.push_back({phase, frames, have_reply ? data.q : 0.0, wall_now()});
        }
        if (ok && frames % 50 == 0) {
            std::printf("    帧 %5d：转子 实测 %.4f rad/s、tau=%+.4f N·m；输出端 %.4f 圈/s、累计转角 %.2f°、"
                        "temp=%d °C、merror=%u\n",
                        frames, data.dq, data.tau, data.dq / N / (2.0 * M_PI),
                        data.q / N * 180.0 / M_PI, data.temp, data.merror);
        }
        if (ok && data.merror != 0) {
            std::printf("**电机报错 merror=%u**（1 过热/2 过流/3 过压/4 编码器故障）：立刻收速度退出。\n",
                        data.merror);
            exit_code = 4;
            break;
        }
        if (ok && data.temp >= 80) {
            std::printf("**温度 %d °C 偏高**（90 °C 触发保护）：收速度退出。\n", data.temp);
            exit_code = 4;
            break;
        }
        usleep(static_cast<useconds_t>(dt * 1e6));
    }

    // 收尾：再发 0.5 s 零速度（如果还没到 0），让电机停下来
    if (exit_code == 0 || exit_code == 5) {
        cmd.dq = 0.0;
        for (int i = 0; i < 100; ++i) {
            serial->sendRecv(&cmd, &data);
            usleep(5000);
        }
        std::printf("已额外发送 0.5 s 零速度指令（最后一帧：dq=0、kd=%.6f、tau=0）\n", kd_rotor);
    }
    delete serial;
    if (fake_motor.joinable()) {
        fake_stop = true;
        fake_motor.join();
    }

    std::printf("=== 汇总 ===\n");
    if (!have_reply) {
        std::printf("一帧回复都没收到（超时 %d 帧）：检查 ID、接线（TX/RX 是否交叉）、共同接地、电机供电。\n",
                    timeouts);
        return 3;
    }
    std::printf("帧数 %d（收到回复 %d、超时 %d）；实测输出端转速区间 %.4f…%.4f 圈/s（指令 %.4f）；\n"
                "转子侧位置 %.4f → %.4f rad（输出端 %.2f° → %.2f°）；温度峰值 %d °C；最后一次 merror=%u\n",
                frames, ok_frames, timeouts, dq_min, dq_max, opt.rev_per_s, q_first, q_last,
                q_first / N * 180.0 / M_PI, q_last / N * 180.0 / M_PI, temp_max, merror_last);
    // 真实帧周期 + 用墙钟算的"物理转速"（这才是与用标志物量出来的速度对应的那个数）
    if (ok_frames > 1) {
        const double wall_total = wall_now();
        std::printf("真实帧周期 %.3f ms（名义 %.3f，即实际命令频率 %.1f Hz）\n",
                    1000.0 * wall_total / ok_frames, dt * 1000.0, ok_frames / wall_total);
        const Mark *hold = nullptr, *down = nullptr;
        for (const Mark &m : marks) {
            if (m.name.find("保持") != std::string::npos && hold == nullptr)
                hold = &m;
            if (m.name.find("降速") != std::string::npos && down == nullptr)
                down = &m;
        }
        if (hold != nullptr && down != nullptr && down->wall > hold->wall) {
            const double rev = (down->q - hold->q) / (2.0 * M_PI);
            const double secs = down->wall - hold->wall;
            std::printf("匀速段（用**墙钟**与位置反馈算）：%.2f s 转了 %.3f 圈转子 = %.3f 圈输出端"
                        " ⇒ **%.4f 圈/s**（指令 %.4f，达成 %.0f%%）\n",
                        secs, rev, rev / N, rev / N / secs, opt.rev_per_s,
                        100.0 * std::fabs(rev / N / secs) / std::max(1e-9, std::fabs(opt.rev_per_s)));
            std::printf("（同名物理量用 data.dq 读出来是 %.4f 圈/s，两者的差别就是\"速度反馈准不准\"）\n",
                        dq_max);
        }
    }
    std::printf("（结束时的转子位置是\"相对上电时那个零点\"的读数，下一阶段 S2/S3 就用它来标零。）\n");
    return exit_code;
}
