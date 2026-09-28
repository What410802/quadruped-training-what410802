// 实机探针（第二部分第 1 步）：**先只看不动**，确认"这个 USB 转接头 + 官方 SDK 能不能用"，
// 再选择性地发一帧零力矩命令读反馈（零力矩 = 讲义 §1.3 那一行：5 个量全 0，可以自由拖动）。
//
// 它回答三个问题：
//   1. 端口能不能配置成 SDK 要的参数（USB 转接头的型号/驱动/波特率上限，见 --info 那段打印）；
//   2. `ioctl(TIOCGSERIAL)` 在**真**串口驱动上是否成功（SDK 构造时就要它；PTY 上实测会失败）；
//   3. 电机在不在、ID 对不对、反馈能不能解出来（q/dq/tau/temp/merror）。
//
// 安全：**本程序只会下发零力矩**（`--mode zerotorque`）或刹车（`--mode brake`），不会让电机转。
//       但"零力矩"要驱动板保持 FOC 闭环才回得及时，所以电机必须是**固定好**的（手能转但不会乱飞）。
//
// 编译（仓库根目录 MyMonoRepo.d/ 下）：
//   S=../ReadOnly.d/unitree_actuator_sdk
//   g++ -O2 -std=c++14 -I$S/include -I$S/include/unitreeMotor @20260927_motor/cpp_part2/src/serial_probe.cpp -L$S/lib -lUnitreeMotorSDK_Linux64 -Wl,-rpath,"$PWD/$S/lib" -pthread -o /tmp/serial_probe
//
// 用法：
//   /tmp/serial_probe --port /dev/ttyUSB0                     # 只开端口、打印参数，一个字节都不发
//   /tmp/serial_probe --port /dev/ttyUSB0 --id 0 --watch 10    # 零力矩跑 10 s，打印输出端角度（可手转输出端看它变）
//   LD_PRELOAD=/tmp/pty_serial_shim.so /tmp/serial_probe --self-test   # 无硬件自检（PTY + 假电机，验证本程序自己）
//
// ★ S2（找零点）主用法：零力矩、每帧都记、用手慢慢转输出端、回车打标记：
//   sudo /tmp/serial_probe --port /dev/ttyUSB0 --id 0 --watch 40 --every 1 --log /tmp/s2.log
//   然后（另开一个终端也行，这里是同一个终端的 stdin）在"手转到一个已知位置"时按一下回车，
//   日志里就会多一行 MARK —— 这就是"记号笔那个点"在读数上的坐标。见 docs/real.md §3.7。
//
// 注意：`--port /dev/ttyUSB0` 需要读写权限（本机是 root:dialout 660，bis 不在 dialout ⇒ 要么 `sudo`，
// 要么把自己加进 dialout 后重新登录）。跑**实机**时不要带 LD_PRELOAD（那是给 --self-test 用的）。

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include <fcntl.h>
#include <linux/serial.h>
#include <sys/ioctl.h>
#include <termios.h>
#include <unistd.h>

#include "crc/crc_ccitt.h"
#include "serialPort/SerialPort.h"
#include "unitreeMotor/unitreeMotor.h"

#include "sim/fake_motor.h"   // 只在 --self-test 里用到（src/sim/ = 不控制实机的代码）

#include <atomic>
#include <chrono>
#include <cmath>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

namespace {

struct Options {
    std::string port = "/dev/ttyUSB0";
    int id = 0;
    uint32_t baud = 4000000;
    double watch = 0.0;      // >0：零力矩跑这么多秒并打印反馈
    std::string mode = "zerotorque";
    bool self_test = false;
    // —— S2（找零点）用的三个旋钮 ——
    int every = 5;           // 每 N 帧打印一行（S2 建议 1：手转时看得清）
    double jump_deg = 2.0;   // 相邻采样间输出端角度变化 ≥ 这个值就报一行"步进"（手转时的正常速度要低于它）
    std::string log;         // 非空：把每帧写成一行 CSV（终端会折行，分析脚本看文件）
    bool stamp = true;       // 读 stdin：每收到一行就记一个 MARK（stdin 不是终端时自动关掉）
};

void Usage(const char *prog) {
    std::printf("用法：%s [--port /dev/ttyUSB0] [--id N] [--baud N] [--watch SEC]\n"
                "          [--mode zerotorque|brake] [--every N] [--jump-deg D] [--log FILE]\n"
                "          [--no-stamp] [--self-test]\n"
                "  --port   串口设备（默认 /dev/ttyUSB0）\n"
                "  --id     电机 ID（默认 0；驱动板出厂/用 changeID 例程设置）\n"
                "  --baud   波特率（默认 4000000，就是 SDK 例程那个）\n"
                "  --watch  零力矩跑 SEC 秒并打印反馈（默认 0 = 不发任何字节，只开端口）\n"
                "  --mode   zerotorque（默认，五量全 0：可自由拖动，用来找零点）/ brake（锁定）\n"
                "  --every  每 N 帧打印一行（默认 5；S2 手转时用 1）\n"
                "  --jump-deg  相邻采样间输出端变化 ≥ D 度就报一行「步进」（默认 2.0；手转太快会误报，看结尾的 max 步进）\n"
                "  --log    每帧写一行 CSV 到 FILE（分析脚本 scripts/agent_scripts/analyse_watch_log.py 用）\n"
                "  --no-stamp  不读 stdin 打标记（默认：stdin 是终端时就开着，回车=记一个 MARK）\n"
                "  --self-test  自己造一对 PTY + 假电机做无硬件自检（需要 LD_PRELOAD=pty_serial_shim.so）\n",
                prog);
}

bool Parse(int argc, char **argv, Options *o) {
    for (int i = 1; i < argc; ++i) {
        const std::string a = argv[i];
        const bool has_next = i + 1 < argc;
        if (a == "--help" || a == "-h") {
            return false;
        } else if (a == "--self-test") {
            o->self_test = true;
        } else if (a == "--port" && has_next) {
            o->port = argv[++i];
        } else if (a == "--id" && has_next) {
            o->id = std::atoi(argv[++i]);
        } else if (a == "--baud" && has_next) {
            o->baud = static_cast<uint32_t>(std::strtoul(argv[++i], nullptr, 10));
        } else if (a == "--watch" && has_next) {
            o->watch = std::atof(argv[++i]);
        } else if (a == "--every" && has_next) {
            o->every = std::atoi(argv[++i]);
            if (o->every < 1) {
                std::fprintf(stderr, "--every 至少 1\n");
                return false;
            }
        } else if (a == "--jump-deg" && has_next) {
            o->jump_deg = std::atof(argv[++i]);
        } else if (a == "--log" && has_next) {
            o->log = argv[++i];
        } else if (a == "--no-stamp") {
            o->stamp = false;
        } else if (a == "--mode" && has_next) {
            o->mode = argv[++i];
            if (o->mode != "zerotorque" && o->mode != "brake") {
                std::fprintf(stderr, "--mode 只能是 zerotorque / brake：%s\n", o->mode.c_str());
                return false;
            }
        } else {
            std::fprintf(stderr, "未知参数：%s\n", a.c_str());
            return false;
        }
    }
    return true;
}

// `cfgetospeed` 返回的是常量编号（例如 13 = B9600），直接打出来没人看得懂 → 翻个名字
const char *BaudName(speed_t sp) {
    static const struct { speed_t v; const char *n; } kTable[] = {
        {B0, "0"},           {B50, "50"},         {B75, "75"},
        {B110, "110"},       {B134, "134"},       {B150, "150"},
        {B200, "200"},       {B300, "300"},       {B600, "600"},
        {B1200, "1200"},     {B1800, "1800"},     {B2400, "2400"},
        {B4800, "4800"},     {B9600, "9600"},     {B19200, "19200"},
        {B38400, "38400"},   {B57600, "57600"},   {B115200, "115200"},
        {B230400, "230400"}, {B460800, "460800"}, {B500000, "500000"},
        {B576000, "576000"}, {B921600, "921600"}, {B1000000, "1000000"},
        {B1152000, "1152000"}, {B1500000, "1500000"}, {B2000000, "2000000"},
        {B2500000, "2500000"}, {B3000000, "3000000"}, {B3500000, "3500000"},
        {B4000000, "4000000"},
    };
    for (const auto &e : kTable)
        if (e.v == sp)
            return e.n;
    return "（非标准值）";
}

// 用**我们自己的 fd** 先探一遍端口：能读到什么就说什么（这对判断"转接头型号能不能满足 SDK"很关键）。
// 构造 SerialPort **之后**再调一次，就能看到 SDK 到底把端口配成了什么。
void InspectPort(const std::string &port, uint32_t baud, const char *when) {
    const int fd = ::open(port.c_str(), O_RDWR | O_NONBLOCK);
    if (fd < 0) {
        std::printf("端口探针[%s]：打不开 %s（%s）——权限？设备没插？\n", when, port.c_str(),
                    std::strerror(errno));
        std::printf("           本机权限是 root:dialout 660：用 sudo，或把自己加进 dialout 组后重新登录\n");
        return;
    }
    std::printf("端口探针[%s]：\n", when);
    struct termios tio;
    if (::tcgetattr(fd, &tio) == 0) {
        const speed_t in = cfgetispeed(&tio), out = cfgetospeed(&tio);
        std::printf("    termios：输入 %u (%s)、输出 %u (%s)\n", static_cast<unsigned>(in),
                    BaudName(in), static_cast<unsigned>(out), BaudName(out));
    }
    struct serial_struct ss;
    std::memset(&ss, 0, sizeof(ss));
    if (::ioctl(fd, TIOCGSERIAL, &ss) == 0) {
        std::printf("    serial_struct：type=%d baud_base=%u custom_divisor=%u xmit_fifo=%u\n",
                    ss.type, ss.baud_base, ss.custom_divisor, ss.xmit_fifo_size);
        if (ss.baud_base != 0) {
            std::printf("    想要 %u bps ⇒ 除数 %.3f（能整除就精确；现在设的 custom_divisor=%u ⇒ 实得 %s bps）\n",
                        baud, static_cast<double>(ss.baud_base) / static_cast<double>(baud),
                        ss.custom_divisor,
                        ss.custom_divisor == 0
                            ? "跟着 termios 走"
                            : std::to_string(ss.baud_base / ss.custom_divisor).c_str());
        }
    } else {
        std::printf("    TIOCGSERIAL 失败（errno=%d %s）——SDK 的 SerialPort 构造大概率也会抛在这个点上\n",
                    errno, std::strerror(errno));
    }
    ::close(fd);
}

// 无硬件自检：开一对 PTY，另一头放"假电机"（sim/fake_motor.h：一阶速度响应 + 摩擦 + 力矩限幅）
int SelfTest(SerialPort **out_port, std::thread *out_thread, std::atomic<bool> *stop) {
    int master = -1;
    const std::string slave = fakemotor::MakePty(&master);
    if (slave.empty())
        return 1;
    std::printf("自检：PTY slave=%s（假电机在另一头）\n", slave.c_str());
    *stop = false;
    fakemotor::Model model;
    *out_thread = fakemotor::Start(master, stop, model);
    *out_port = new SerialPort(slave, 16, 4000000);
    return 0;
}

// ===================== S2：零力矩“找零点” / 手转特性测试 =====================
//
// 这一块专门回答 S2 的几个问题（见 docs/real.md §3.7）：
//   1. 手转输出端时，读数是否**连续单调**？还是像“0…56.87° 反复循环”的锯齿（= 只报“相对最近零点”的读数，讲义 §2.4）？
//   2. 反向转时对称吗（里程计会不会退）？
//   3. 有没有**整间隔（≈1/N 圈 = 56.87°）的跳变**？（= 讲义 §2.6 的“认错零点”）
//   4. 手转到记号笔那个点时，读数是多少？（回车打 MARK，S4 标定就靠它）

struct Mark {
    double wall;
    std::string label;
    double out_deg;
    double q_raw;   // 反算的报文里的 int32 q15 圈数（浮点读出后 ×32768/2π）
};

// 手转时相邻采样的正常步进很小（200 Hz 下 0.1 圈/s 也才 0.18°/帧），所以“步进 ≥ --jump-deg”
// 基本只会被跳变/跨零点触发。
int WatchRun(SerialPort *serial, const Options &opt, double N) {
    const double zero_interval = 360.0 / N;   // 相邻两个“候选零点”在输出端上的间距（讲义 §2.4）
    const double dt = 0.005;

    // 打标记：只用 ::read 读 stdin（不碰 iostream），进程退出时阻塞的 read 不会拦住退出
    std::mutex mu;
    std::string pending_label;
    int pending_marks = 0;
    if (opt.stamp && ::isatty(0)) {
        std::printf("打标记：现在开始读 stdin——**转到记号笔那个位置时按一下回车**（先打几个字再回车就能给标记起名）\n");
        std::thread([&mu, &pending_label, &pending_marks] {
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
                    std::lock_guard<std::mutex> lk(mu);
                    pending_label = line;
                    ++pending_marks;
                }
            }
        }).detach();
    }

    MotorCmd cmd;
    MotorData data;
    cmd.motorType = MotorType::GO_M8010_6;
    data.motorType = MotorType::GO_M8010_6;
    cmd.mode = opt.mode == "brake" ? queryMotorMode(MotorType::GO_M8010_6, MotorMode::BRAKE)
                                   : queryMotorMode(MotorType::GO_M8010_6, MotorMode::FOC);
    cmd.id = opt.id;
    cmd.kp = 0.0;   // 五个量全 0 = 零力矩模式（可自由拖动）/ 刹车模式下无所谓
    cmd.kd = 0.0;
    cmd.q = 0.0;
    cmd.dq = 0.0;
    cmd.tau = 0.0;

    std::printf("减速比 N = %.6f ⇒ 一个零点区间 = 1/N 圈 = %.4f°（输出端）\n", N, zero_interval);
    std::printf("开始：id=%d、mode=%u（%s）、五个命令量全 0（零力矩 = 电机自由，可手转输出端）；"
                "跑 %.1f s（名义 5 ms/帧，每 %d 帧打印一行）\n",
                opt.id, static_cast<unsigned>(cmd.mode), opt.mode.c_str(), opt.watch, opt.every);

    FILE *log = nullptr;
    if (!opt.log.empty()) {
        log = std::fopen(opt.log.c_str(), "w");
        if (log == nullptr)
            std::fprintf(stderr, "打开日志 %s 失败：%s\n", opt.log.c_str(), std::strerror(errno));
        else
            std::fprintf(log, "# frame,t,q_raw,q_rotor_rad,out_deg,zone,in_zone_deg,dq,tau,temp,merror\n");
    }

    const auto wall0 = std::chrono::steady_clock::now();
    const auto wall_now = [&wall0] {
        return std::chrono::duration<double>(std::chrono::steady_clock::now() - wall0).count();
    };

    int frames = 0, ok_frames = 0, timeouts = 0;
    bool have_prev = false;
    double prev_out_deg = 0.0;
    double out_first = 0.0, out_last = 0.0, step_max = 0.0, step_sum = 0.0;
    int steps = 0, wrap_like = 0, reversals = 0;
    double last_dir = 0.0;
    int32_t zone_min = 1 << 30, zone_max = -(1 << 30);
    std::vector<Mark> marks;
    int stamp_seen = 0;

    const int total_frames = static_cast<int>(opt.watch / dt);
    for (int frame = 1; frame <= total_frames; ++frame) {
        const bool ok = serial->sendRecv(&cmd, &data);
        const double wall = wall_now();
        const double t = (frame - 1) * dt;
        ++frames;
        if (!ok) {
            if (++timeouts <= 3)
                std::printf("  第 %d 帧：没收到回复（超时）——ID 对不对？协议线接反？波特率？\n", frames);
            usleep(5000);
            continue;
        }
        ++ok_frames;

        const double q_rotor = data.q;                          // 转子侧 rad
        const double out_deg = q_rotor / N * 180.0 / M_PI;      // 输出端角度（= q/N）
        const double q_raw = q_rotor * 32768.0 / (2.0 * M_PI);  // 反算报文里的 int32 q15 圈数
        const double zone = std::floor(out_deg / zero_interval);
        const double in_zone = out_deg - zone * zero_interval;  // “相对最近穿过那个零点”的角度

        // 与上一采样的差值（先在更新 prev_out_deg 之前算好，后面打印还要用）
        const double step = have_prev ? out_deg - prev_out_deg : 0.0;
        if (!have_prev) {
            out_first = out_deg;
        } else {
            const double d = step;
            step_sum += std::fabs(d);
            if (std::fabs(d) > step_max)
                step_max = std::fabs(d);
            if (std::fabs(d) >= opt.jump_deg) {
                ++steps;
                const double ratio = d / zero_interval;
                const bool looks_like_one_zone = std::fabs(std::fabs(ratio) - 1.0) < 0.10;
                if (looks_like_one_zone)
                    ++wrap_like;
                std::printf("  **步进 %+.3f°（= %+.3f 个零点区间；转子 %+.1f°）** 帧 %d t=%.3f s%s\n",
                            d, ratio, d * N, frame, t,
                            looks_like_one_zone
                                ? "  ← 整一个零点区间：像“跨零点/认错零点”（讲义 §2.6）"
                                : (std::fabs(ratio) > 1.5 ? "  ← 比一个间隔还大：先怀疑接线/读数" : ""));
            }
            const double dir = d > 0.05 ? 1.0 : (d < -0.05 ? -1.0 : 0.0);
            if (dir != 0.0 && last_dir != 0.0 && dir != last_dir)
                ++reversals;
            if (dir != 0.0)
                last_dir = dir;
        }
        prev_out_deg = out_deg;
        have_prev = true;
        out_last = out_deg;
        zone_min = std::min(zone_min, static_cast<int32_t>(zone));
        zone_max = std::max(zone_max, static_cast<int32_t>(zone));

        if (log != nullptr) {
            std::fprintf(log, "%d,%.6f,%.1f,%.6f,%.6f,%d,%.6f,%.6f,%.6f,%d,%u\n", frame, wall, q_raw,
                         q_rotor, out_deg, static_cast<int>(zone), in_zone, data.dq, data.tau,
                         static_cast<int>(data.temp), static_cast<unsigned>(data.merror));
            std::fflush(log);
        }

        if (frame % opt.every == 0 || frame <= 2) {
            std::printf("  帧 %5d t=%6.3f：输出端 %+9.3f°（第 %d 区、区内 %+7.3f°）Δ%+7.3f°；"
                        "转子 %+9.5f rad（raw≈%+11.1f）；dq=%+7.4f、tau=%+7.4f、temp=%d、merror=%u\n",
                        frame, t, out_deg, static_cast<int>(zone), in_zone, step, q_rotor, q_raw,
                        data.dq, data.tau, static_cast<int>(data.temp),
                        static_cast<unsigned>(data.merror));
        }

        // 回车打的标记：记下“此刻的读数”，这就是记号笔那个点的坐标
        {
            std::lock_guard<std::mutex> lk(mu);
            if (pending_marks > stamp_seen) {
                stamp_seen = pending_marks;
                Mark m{wall, pending_label, out_deg, q_raw};
                marks.push_back(m);
                const std::string note = pending_label.empty() ? std::string() : ("  名字：" + pending_label);
                std::printf("  === MARK #%zu t=%.3f s：输出端 %+.3f°（第 %d 区、区内 %+.3f°，raw≈%.0f）%s ===\n",
                            marks.size(), wall, out_deg, static_cast<int>(zone), in_zone, q_raw,
                            note.c_str());
                if (log != nullptr) {
                    std::fprintf(log, "MARK,%.6f,%s,%.6f,%.1f\n", wall, pending_label.c_str(), out_deg, q_raw);
                    std::fflush(log);
                }
            }
        }

        if (data.merror != 0)
            std::printf("  **电机报错**：merror=%u（1 过热 / 2 过流 / 3 过压 / 4 编码器故障）\n",
                        static_cast<unsigned>(data.merror));
        if (data.temp >= 80)
            std::printf("  **温度偏高**：%d °C（90 °C 触发保护）\n", static_cast<int>(data.temp));
        usleep(5000);
    }

    if (log != nullptr)
        std::fclose(log);

    std::printf("结束：共 %d 帧，收到回复 %d 帧、超时 %d 帧\n", frames, ok_frames, timeouts);
    if (ok_frames > 0) {
        std::printf("输出端角度 %+.3f° → %+.3f°（区号 %d…%d，共覆盖 %d 个零点区间）；每帧步进 max |Δ| = %.3f°（平均 %.3f°）\n",
                    out_first, out_last, static_cast<int>(zone_min), static_cast<int>(zone_max),
                    zone_max - zone_min + 1, step_max, ok_frames > 1 ? step_sum / (ok_frames - 1) : 0.0);
        std::printf("步进 ≥ %.1f° 共 %d 次，其中 %d 次≈整一个零点区间（%.3f°）；换向 %d 次；打标记 %zu 个\n",
                    opt.jump_deg, steps, wrap_like, zero_interval, reversals, marks.size());
        std::printf("怎么读这些数（§3.7）：区内角度在“转一圈时反复回 0”⇒ 只报相对最近零点的读数，软件要自己补区间；\n"
                    "                             一直单调累计（S1 实测就是）⇒ 驱动板自己维护里程计，跨零点不用管，但上电落在哪个零点仍要靠启动姿态。\n");
        if (steps > wrap_like)
            std::printf("还有 %d 次不是整间隔的步进：先看是不是手转太快（把 --jump-deg 调大重跑一次就能区分）。\n",
                        steps - wrap_like);
    }
    return ok_frames > 0 ? 0 : 3;
}

} // namespace

int main(int argc, char **argv) {
    Options opt;
    if (!Parse(argc, argv, &opt)) {
        Usage(argv[0]);
        return 1;
    }
    const double N = queryGearRatio(MotorType::GO_M8010_6);
    std::printf("GO-M8010-6：减速比 N = %.6f（queryGearRatio）、FOC 模式号 = %d（queryMotorMode）、"
                "刹车模式号 = %d\n",
                N, queryMotorMode(MotorType::GO_M8010_6, MotorMode::FOC),
                queryMotorMode(MotorType::GO_M8010_6, MotorMode::BRAKE));

    if (!opt.self_test)
        InspectPort(opt.port, opt.baud, "构造 SerialPort 之前：端口原生参数");

    SerialPort *serial = nullptr;
    std::thread fake_motor;
    std::atomic<bool> stop{false};
    try {
        if (opt.self_test) {
            if (SelfTest(&serial, &fake_motor, &stop) != 0)
                return 1;
        } else {
            serial = new SerialPort(opt.port, 16, opt.baud); // 与官方例程同一个构造
        }
        std::printf("SerialPort 构造成功（%s）\n", opt.self_test ? "自检 PTY" : opt.port.c_str());
        if (!opt.self_test)
            InspectPort(opt.port, opt.baud, "构造 SerialPort 之后：SDK 配成的参数");
    } catch (const std::exception &e) {
        std::printf("**SerialPort 构造失败**：%s\n", e.what());
        std::printf("（官方例程在这一步没接异常，所以会直接 terminate + core dumped；这里接住了）\n");
        return 2;
    }

    if (opt.watch <= 0.0) {
        std::printf("只开了端口，没发任何字节（要看反馈就加 --watch SEC）\n");
        delete serial;
        if (fake_motor.joinable()) {
            stop = true;
            fake_motor.join();
        }
        return 0;
    }

    const int rc = WatchRun(serial, opt, N);
    delete serial;
    if (fake_motor.joinable()) {
        stop = true;
        fake_motor.join();
    }
    return rc;
}
