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
#include <cmath>
#include <string>
#include <thread>

namespace {

struct Options {
    std::string port = "/dev/ttyUSB0";
    int id = 0;
    uint32_t baud = 4000000;
    double watch = 0.0;      // >0：零力矩跑这么多秒并打印反馈
    std::string mode = "zerotorque";
    bool self_test = false;
};

void Usage(const char *prog) {
    std::printf("用法：%s [--port /dev/ttyUSB0] [--id N] [--baud N] [--watch SEC]\n"
                "          [--mode zerotorque|brake] [--self-test]\n"
                "  --port   串口设备（默认 /dev/ttyUSB0）\n"
                "  --id     电机 ID（默认 0；驱动板出厂/用 changeID 例程设置）\n"
                "  --baud   波特率（默认 4000000，就是 SDK 例程那个）\n"
                "  --watch  零力矩跑 SEC 秒并打印反馈（默认 0 = 不发任何字节，只开端口）\n"
                "  --mode   zerotorque（默认，五量全 0：可自由拖动，用来找零点）/ brake（锁定）\n"
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
    std::printf("开始：id=%d、mode=%u（%s）、五个命令量全 0；跑 %.1f s（每帧 5 ms，每 5 帧打印一行）\n",
                opt.id, static_cast<unsigned>(cmd.mode), opt.mode.c_str(), opt.watch);

    int frames = 0, ok_frames = 0, bad = 0;
    for (int i = 0; i * 0.005 < opt.watch; ++i) {
        const bool ok = serial->sendRecv(&cmd, &data);
        ++frames;
        if (!ok) {
            if (++bad <= 3)
                std::printf("  第 %d 帧：没收到回复（超时）——ID 对不对？协议线接反？波特率？\n", frames);
            usleep(5000);
            continue;
        }
        ++ok_frames;
        if (frames % 5 == 0 || frames <= 2) {
            const double q_out_deg = data.q / N * 180.0 / M_PI;
            std::printf("  帧 %5d：转子 q=%+9.5f rad、dq=%+8.4f rad/s、tau=%+7.4f N·m、temp=%d °C、"
                        "merror=%u → 输出端 %+8.3f°（= q/N）\n",
                        frames, data.q, data.dq, data.tau, data.temp, data.merror, q_out_deg);
        }
        if (data.merror != 0)
            std::printf("  **电机报错**：merror=%u（1 过热 / 2 过流 / 3 过压 / 4 编码器故障）\n",
                        data.merror);
        if (data.temp >= 80)
            std::printf("  **温度偏高**：%d °C（90 °C 触发保护）\n", data.temp);
        usleep(5000);
    }
    std::printf("结束：共 %d 帧，收到回复 %d 帧、超时 %d 帧\n", frames, ok_frames, bad);
    delete serial;
    if (fake_motor.joinable()) {
        stop = true;
        fake_motor.join();
    }
    return ok_frames > 0 ? 0 : 3;
}
