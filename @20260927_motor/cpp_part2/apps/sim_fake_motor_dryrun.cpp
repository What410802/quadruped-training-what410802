// 子任务项二（实体电机控制）的 **dry run**：不接电机，把"上位机 → 官方 SDK → 报文 → 反馈"整条链路跑起来。
//
// 做法：进程自己开一对 PTY，slave 交给官方 `SerialPort`（要配合 pty_serial_shim.so，见那个文件），
// master 一侧起一个"假电机"线程：按 GO-8010-6 的报文格式收 17 字节命令、回 16 字节反馈。
// 打包/CRC/定点换算全部由官方 SDK 的 .so 做，我们只负责"另一头"，所以跑通的链路与实机是同一套代码。
//
// 编译与运行（在仓库根目录 MyMonoRepo.d/ 下；CMake 会一起编好 PTY 垫片与本程序）：
//   pixi run cmake -S @20260927_motor/cpp_part2 -B @20260927_motor/cpp_part2/build
//   pixi run cmake --build @20260927_motor/cpp_part2/build
//   LD_PRELOAD=@20260927_motor/cpp_part2/build/libpty_serial_shim.so \
//       @20260927_motor/cpp_part2/build/fake_motor_dryrun
//
// 实测结论（本文件自己会打印）见 docs/protocol.md。
// 注意：本文件里的假电机是最初那版（固定转速/力矩，只为验证协议）；S1 之后的自检都用更真的
// include/motor_bench/sim/fake_motor.hpp（一阶响应 + 摩擦 + 限幅），新的控制逻辑请用它，
// 不要再照这份抄。
// 头文件注意事项：`crc/crc_ccitt.h` 自己没有 include
// <stdint.h>/<stddef.h>，直接包会报 uint16_t / size_t 未定义（官方 .so
// 的编译单元应该是先包了别的头，所以能过），这里先补上。
// SDK 的 crc_ccitt.h 自己没有 include <stdint.h>/<stddef.h>，所以这两个标准头必须**放在最前**。
#include <cstddef>
#include <cstdint>

#include "crc/crc_ccitt.h"
#include "serialPort/SerialPort.h"
#include "unitreeMotor/unitreeMotor.h"

#include <atomic>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <thread>
#include <unistd.h>

namespace
{

constexpr int kCmdSize = sizeof(ControlData_t); // 17 = 2(head) + 1(mode) + 12(comd) + 2(CRC)
constexpr int kRspSize = sizeof(MotorData_t);   // 16 = 2(head) + 1(mode) + 11(fbk) + 2(CRC)

// 解开一帧命令，并用 SDK 自带的 crc_ccitt 重算 CRC 对拍（对上 = 我们对协议的理解正确）
void PrintCommand(const unsigned char* buf, int n)
{
    ControlData_t c;
    std::memcpy(&c, buf, kCmdSize);
    uint16_t crc_recv = 0;
    std::memcpy(&crc_recv, buf + kCmdSize - CRC_SIZE, CRC_SIZE);
    const uint16_t crc_calc = crc_ccitt(0, buf, kCmdSize - CRC_SIZE);
    std::printf("  命令#%d：head=%02x %02x id=%u status=%u（0 锁定/1 FOC/2 校准）"
                " tor_des=%d spd_des=%d pos_des=%d k_pos=%u k_spd=%u\n",
                n, c.head[0], c.head[1], c.mode.id, c.mode.status, c.comd.tor_des, c.comd.spd_des,
                c.comd.pos_des, c.comd.k_pos, c.comd.k_spd);
    std::printf("       CRC：报文 0x%04x，本地重算 0x%04x → %s\n", crc_recv, crc_calc,
                crc_recv == crc_calc ? "一致" : "**不一致**");
}

// 假电机的"物理"：这里只做定点常量回帧，用来验证反馈方向的标度；要模拟真实响应就把 raw 换成模型算出
void BuildReply(unsigned char* buf, int32_t pos_raw, int16_t spd_raw, int16_t tor_raw, int8_t temp)
{
    MotorData_t r;
    std::memset(&r, 0, sizeof(r));
    r.head[0] = 0xfe;
    r.head[1] = 0xee;
    r.mode.id = 0;
    r.mode.status = 1; // FOC
    r.fbk.torque = tor_raw;
    r.fbk.speed = spd_raw;
    r.fbk.pos = pos_raw;
    r.fbk.temp = temp;
    r.fbk.MError = 0; // 0 正常 / 1 过热 / 2 过流 / 3 过压 / 4 编码器故障
    const uint16_t crc = crc_ccitt(0, reinterpret_cast<const uint8_t*>(&r), kRspSize - CRC_SIZE);
    std::memcpy(reinterpret_cast<unsigned char*>(&r) + kRspSize - CRC_SIZE, &crc, CRC_SIZE);
    std::memcpy(buf, &r, kRspSize);
}

} // namespace

int main()
{
    const int master = posix_openpt(O_RDWR | O_NOCTTY);
    if (master < 0)
    {
        std::perror("posix_openpt");
        return 1;
    }
    grantpt(master);
    unlockpt(master);
    const char* slave = ptsname(master);
    std::printf("PTY：slave=%s（假电机在 master 一侧）\n", slave);

    // ---- 假电机线程：收命令 → 回帧。回帧值固定，方便验证标度
    std::atomic<bool> stop{false};
    std::atomic<int> frames{0};
    std::thread motor(
        [&]
        {
            unsigned char cmd[kCmdSize];
            int got = 0;
            while (!stop.load())
            {
                const ssize_t n = ::read(master, cmd + got, static_cast<size_t>(kCmdSize - got));
                if (n > 0)
                {
                    got += static_cast<int>(n);
                    if (got == kCmdSize)
                    {
                        got = 0;
                        const int idx = ++frames;
                        if (idx <= 2)
                            PrintCommand(cmd, idx);
                        // 回帧：pos_raw = 32768/2（半圈）、spd_raw = 128、tor_raw = 256、temp = 32
                        unsigned char rsp[kRspSize];
                        BuildReply(rsp, 32768 / 2, 128, 256, 32);
                        if (::write(master, rsp, kRspSize) != kRspSize)
                            std::printf("  回帧失败\n");
                    }
                }
                else if (n < 0)
                {
                    usleep(200);
                }
            }
        });

    // ---- 上位机一侧：完全按官方例程的用法，只把串口名换成 PTY
    try
    {
        SerialPort serial(slave);
        MotorCmd cmd;
        MotorData data;
        cmd.motorType = MotorType::GO_M8010_6;
        data.motorType = MotorType::GO_M8010_6;
        cmd.mode = queryMotorMode(MotorType::GO_M8010_6, MotorMode::FOC);
        cmd.id = 0;
        const double N = queryGearRatio(MotorType::GO_M8010_6); // 6.33，不用自己写
        std::printf("gear ratio = %.6f（queryGearRatio），mode = %d（queryMotorMode）\n", N,
                    cmd.mode);

        // 讲义 §2.3：关节侧 → 转子侧。这里用子任务项一同一组输出侧参数（kp=80、kd=3）
        const double kp = 80.0, kd = 3.0, q_des = 0.5, dq_des = 1.0, tau_ff = 0.0;
        cmd.kp = kp / (N * N);
        cmd.kd = kd / (N * N);
        cmd.q = q_des * N;
        cmd.dq = dq_des * N;
        cmd.tau = tau_ff / N;
        std::printf("下发（关节侧 kp=%.0f kd=%.0f q_des=%.2f dq_des=%.2f）→ 转子侧 K_P=%.4f "
                    "K_W=%.4f Pos=%.3f W=%.3f T=%.3f\n",
                    kp, kd, q_des, dq_des, cmd.kp, cmd.kd, cmd.q, cmd.dq, cmd.tau);
        for (int i = 0; i < 3; ++i)
        {
            const bool ok = serial.sendRecv(&cmd, &data);
            std::printf("#%d sendRecv=%s  data.q=%.4f rad（转子侧）→ 关节侧 q=%.4f rad；"
                        "data.dq=%.4f、data.tau=%.4f N·m、temp=%d、merror=%d\n",
                        i, ok ? "true" : "false", data.q, data.q / N, data.dq, data.tau, data.temp,
                        data.merror);
            usleep(20000);
        }
    }
    catch (const std::exception& e)
    {
        std::printf("异常：%s\n", e.what());
        std::printf("（没接电机时官方例程就是在这里崩的：IOException 未捕获 → terminate）\n");
    }
    stop.store(true);
    motor.join();
    std::printf("假电机共处理 %d 帧命令\n", frames.load());
    return 0;
}
