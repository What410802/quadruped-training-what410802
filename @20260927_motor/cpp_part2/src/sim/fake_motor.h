// 假电机（dry run / `--self-test` 用）：按 GO-8010-6 的报文收命令、回反馈，内部是一个"像个电机"的小模型。
//
// 为什么需要它：实机一次只能试一次，S3–S5（回归零点、插值到位、标零、零点跳变）那套逻辑必须能在
// 无硬件时反复跑。模型故意简单，但**收发格式与定点标度按实测值来**（见 ../README.md §4）：
//   pos = 圈 × 32768、speed = rad/s × 128/π、torque = N·m × 256、K_P/K_W = ×1280（超 32766 截断）
// 这样"我们下发的指令 → 报文 → 反馈 → 解回物理量"整条链路与实机是同一套代码，只差真实链路本身。
//
// 模型（转子侧）：τ = K_P·(Pos_des − p) + K_W·(W_des − ω)，|τ| ≤ τ_max；库仑摩擦 |ω| 大于阈值时
// 减去 τ_fric·sign(ω)；ω 以一阶时间常数跟随（简化掉真实转动惯量），p 积分 ω。
#pragma once

#include <cstdint>
#include <cstring>
#include <cmath>
#include <cstdio>
#include <fcntl.h>
#include <stdlib.h>
#include <unistd.h>

#include <atomic>
#include <string>
#include <thread>

#include "crc/crc_ccitt.h"
#include "unitreeMotor/unitreeMotor.h"

namespace fakemotor {

// 开一对 PTY：返回 slave 设备名（给 SDK 当串口），master 由调用方拿去做"驱动器板"
inline std::string MakePty(int *master) {
    const int fd = posix_openpt(O_RDWR | O_NOCTTY);
    if (fd < 0) {
        std::perror("posix_openpt");
        return std::string();
    }
    grantpt(fd);
    unlockpt(fd);
    *master = fd;
    return std::string(ptsname(fd));
}

// 假电机的状态与参数
struct Model {
    double p = 0.0;         // 转子位置 [rad]
    double w = 0.0;         // 转子角速度 [rad/s]
    double tau = 0.0;       // 上一次算出的转子力矩 [N·m]（回帧要用）
    double tau_max = 20.0;  // 力矩限幅（转子侧；默认与仿真模型 ±20 N·m 一致，GO 铭牌值待确认）
    double tau_fric = 0.002; // 库仑摩擦（转子侧 [N·m]）—— 死区/静态误差就来自它；
                             // 调到 0.02 就能看到"速度环稳态误差 = τ_fric/K_W"（0.02/0.0125 = 1.6 rad/s）
    double tau_lag = 0.02;  // 速度一阶时间常数 [s]（代替转动惯量，简化）
    double temp = 30.0;     // 温度 [°C]
    uint8_t merror = 0;     // 0 正常 / 1 过热 / 2 过流 / 3 过压 / 4 编码器故障

    // 解一帧命令（raw → 物理量）；标度用实测值
    static void Decode(const ControlData_t &c, double *tau_des, double *w_des, double *p_des,
                       double *k_pos, double *k_spd) {
        *tau_des = c.comd.tor_des / 256.0;
        *w_des = c.comd.spd_des * M_PI / 128.0;
        *p_des = c.comd.pos_des * 2.0 * M_PI / 32768.0;
        *k_pos = c.comd.k_pos / 1280.0;
        *k_spd = c.comd.k_spd / 1280.0;
    }

    // 走一步（dt = 帧间隔）。转子等效惯量挑一个"像个电机"的量级（1e-3），闭环时间常数 J/K_W
    // 在 5 ms 步长下稳定：K_W=0.0125（输出端 kd=0.5）时 80 ms，K_W=0.0749（输出端 kd=3）时 13 ms。
    void Step(const ControlData_t &c, double dt) {
        constexpr double kJ = 1e-3; // 转子等效惯量 [kg·m²]（假模型的旋钮，不改标度那部分）
        double tau_des = 0, w_des = 0, p_des = 0, k_pos = 0, k_spd = 0;
        Decode(c, &tau_des, &w_des, &p_des, &k_pos, &k_spd);
        double tau_cmd = tau_des + k_pos * (p_des - p) + k_spd * (w_des - w);
        if (tau_cmd > tau_max)
            tau_cmd = tau_max;
        else if (tau_cmd < -tau_max)
            tau_cmd = -tau_max;

        if (std::fabs(w) > 1e-3) { // 在转：库仑摩擦与运动方向相反
            const double tau_net = tau_cmd - tau_fric * (w > 0.0 ? 1.0 : -1.0);
            const double w_new = w + tau_net * dt / kJ;
            if ((w > 0.0 && w_new < 0.0) || (w < 0.0 && w_new > 0.0)) {
                w = 0.0;   // 摩擦在这一拍里刚好把速度吃光（粘滞）
                tau = 0.0;
            } else {
                w = w_new;
                tau = tau_net;
            }
        } else if (std::fabs(tau_cmd) > tau_fric) { // 本来停着：要先克服静摩擦才动
            tau = tau_cmd - tau_fric * (tau_cmd > 0.0 ? 1.0 : -1.0);
            w += tau * dt / kJ;
        } else { // 静摩擦：这么小的力矩推不动
            tau = 0.0;
            w = 0.0;
        }
        p += w * dt;
        temp += 0.05 * dt * std::fabs(tau) / tau_max; // 力矩越大慢慢越热（演示用，不是热模型）
        if (temp > 89.0)
            merror = 1; // 90 °C 触发保护（报文的 merror 位）
    }

    // 打包一帧反馈（物理量 → raw）
    void Fill(const ControlData_t &cmd, MotorData_t *r) const {
        std::memset(r, 0, sizeof(*r));
        r->head[0] = 0xfe;
        r->head[1] = 0xee;
        r->mode.id = cmd.mode.id;
        r->mode.status = 1; // FOC
        r->fbk.torque = static_cast<int16_t>(std::lround(tau * 256.0));
        r->fbk.speed = static_cast<int16_t>(std::lround(w * 128.0 / M_PI));
        r->fbk.pos = static_cast<int32_t>(std::lround(p * 32768.0 / (2.0 * M_PI)));
        r->fbk.temp = static_cast<int8_t>(std::lround(temp));
        r->fbk.MError = merror;
        const uint16_t crc =
            crc_ccitt(0, reinterpret_cast<const uint8_t *>(r), sizeof(*r) - CRC_SIZE);
        std::memcpy(reinterpret_cast<uint8_t *>(r) + sizeof(*r) - CRC_SIZE, &crc, CRC_SIZE);
    }
};

// 起一条线程当"驱动器板"：收 17 字节命令 → Step → 回 16 字节反馈；stop 置 true 后退出
inline std::thread Start(int master_fd, std::atomic<bool> *stop, Model model) {
    return std::thread([master_fd, stop, model]() mutable {
        unsigned char buf[sizeof(ControlData_t)];
        int got = 0;
        const double dt = 0.005; // 与调用方 5 ms 一帧对应
        while (!stop->load()) {
            const ssize_t n = ::read(master_fd, buf + got, sizeof(buf) - static_cast<size_t>(got));
            if (n > 0) {
                got += static_cast<int>(n);
                if (got == static_cast<int>(sizeof(buf))) {
                    got = 0;
                    ControlData_t c;
                    std::memcpy(&c, buf, sizeof(c));
                    model.Step(c, dt);
                    MotorData_t r;
                    model.Fill(c, &r);
                    if (::write(master_fd, &r, sizeof(r)) != static_cast<ssize_t>(sizeof(r)))
                        std::printf("假电机：回帧写失败\n");
                }
            } else if (n < 0) {
                usleep(200);
            }
        }
    });
}

} // namespace fakemotor
