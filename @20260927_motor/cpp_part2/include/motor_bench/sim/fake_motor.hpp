// 假电机（dry run / `--self-test` 用）：按 GO-8010-6
// 的报文收命令、回反馈，内部是一个"像个电机"的小模型。
//
// 为什么需要它：实机一次只能试一次，S3–S5（回归零点、插值到位、标零、零点跳变）那套逻辑必须能在
// 无硬件时反复跑。模型故意简单，但**收发格式与定点标度按实测值来**（见 ../README.md §4）：
//   pos = 圈 × 32768、speed = rad/s × 128/π、torque = N·m × 256、K_P/K_W = ×1280（超 32766 截断）
// 这样"我们下发的指令 → 报文 → 反馈 → 解回物理量"整条链路与实机是同一套代码，只差真实链路本身。
//
// 模型（转子侧）：τ = K_P·(Pos_des − p) + K_W·(W_des − ω)，|τ| ≤ τ_max；库仑摩擦 |ω| 大于阈值时
// 减去 τ_fric·sign(ω)；ω 以一阶时间常数跟随（简化掉真实转动惯量），p 积分 ω。
//
// 第二层是**驱动板的上报层**（`Encoder`，讲义 §2.4–2.6）：真实转子位置 `p` 与"板子报出来的位置"
// 不是一回事 —— 板子用的是单圈绝对值编码器，所以
//   * `mode = 里程计`：读数连续累计（S1 实测就是这种，见 ../docs/real.md §3.6）；
//   * `mode = 锯齿`  ：只报"相对最近零点"的角度，0…1 圈（讲义 §2.4）；
//   * `datum`：上电时落在哪个候选零点（整数个转子圈；转子 1 圈 = 输出端 1/N 圈 = 一个零点区间）
//     —— 这就是"认错零点"，S3–S5 的 `offset` / 启动检查 / 跳变检测全靠它来复现；
//   * `jump_frame/jump_turns`：运行中注入一次"读数整体跳 k 个区间"（= 板子中途换基准）。
// 位置环读的是**板子自己那份**角度（所以 datum 一移、物理目标就动一个区间 —— 这正是要防的事）。
//
// 它与真机的层级关系、每个接口的契约、启动/一帧/结束/注入的时序图、以及"能证明什么、不能证明什么"，
// 见 ../docs/fake_motor.md（本文只负责实现）。
#pragma once

// SDK 的 crc_ccitt.h 自己没有 include <stdint.h>/<stddef.h>，所以标准头必须排在它前面。
#include <cstddef>
#include <cstdint>

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
#include "motor_bench/ticks.hpp"
#include "unitreeMotor/unitreeMotor.h"

#include <cstddef>
#include <cstdint>

namespace motor_bench::sim
{

// 开一对 PTY：返回 slave 设备名（给 SDK 当串口），master 由调用方拿去做"驱动器板"
inline std::string MakePty(int* master)
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

// 驱动板的上报层：单圈绝对值编码器 + 上电基准（讲义 §2.4–2.6）。
// 这是**故意可注入**的：`datum`（上电认错零点）与 `jump_frame`（运行中换基准）都是实机上偶发、
// 又必须在软件里处理掉的事件，所以让它们能在 dry run 里精确复现。
struct Encoder
{
    int mode = 0; // 0 = 里程计（连续累计，S1 实测）；1 = 锯齿（只报 0…1 圈，讲义 §2.4）
    int datum = 0; // 上电基准：读数整体平移 datum 个**转子整圈**（正负都行）= "认错零点"
    long jump_frame = -1; // >0：在第 N 帧注入一次"中途换基准"（实机上是跨零点/上电时才可能发生）
    int jump_turns = 1;   // 注入的方向与大小（转子整圈数）
    long off_after =
        -1; // >0：从第 N 帧起"板子断电"（不收命令、不积分、不回帧），持续 off_frames 帧
    int off_frames = 0; // 断电窗口长度（帧）
    long cycle_frame = -1; // >0：在第 N 帧模拟"上电复位"（丢圈数：报出来的 raw 回到 0…2π）
    // "手转"：模拟人手握住输出端，把它缓慢推着来回转（软弹簧 + 阻尼，带力矩上限）。
    // 断电窗口里也生效（那时电机没上电，转子本来就是自由的）。
    double hand_deg = 0.0;      // 手推的幅度（**输出端**角度 [°]，0 = 不打手）
    double hand_period_s = 8.0; // 手推的周期 [s]（默认 8 s：一个来回够慢，接近手拧的速度）
    // 回帧 mode 里的状态位（手册 §8.1：bit1 = 期望速度超范围、bit2 = 期望位置超范围）。
    // 真板子报这两个位时说明我们自己下发的期望值越界了 —— 注入它，好让告警路径也能离线跑。
    uint8_t status_bits = 0;
};

// 假电机的状态与参数
struct Model
{
    double p = 0.0;   // 真实转子位置 [rad]
    double w = 0.0;   // 转子角速度 [rad/s]
    double tau = 0.0; // 上一次算出的转子力矩 [N·m]（回帧要用）
    double tau_max = 20.0; // 力矩限幅（转子侧；默认与仿真模型 ±20 N·m 一致，GO 铭牌值待确认）
    double tau_fric =
        0.002; // 库仑摩擦（转子侧 [N·m]）—— 死区/静态误差就来自它；
               // 调到 0.02 就能看到"速度环稳态误差 = τ_fric/K_W"（0.02/0.0125 = 1.6 rad/s）
    double temp = 30.0; // 温度 [°C]
    uint8_t merror = 0; // 0 正常 / 1 过热 / 2 过流 / 3 过压 / 4 编码器故障

    Encoder enc;    // 上报层（上电基准 / 里程计还是锯齿 / 中途换基准）
    long frame = 0; // 已处理的帧数（统计用）
    bool jump_fired = false;  // 注入过跳变没有（自检的汇总里要报）
    bool cycle_fired = false; // 注入过"上电复位"没有

    // 手转：人握住输出端来回推 ⇒ 内部当成"转子端一个软弹簧 + 阻尼追一个缓慢变化的目标角"。
    // 力矩有个上限（人手也不是无限大），这样它在位置环闭合时也打不动闭环，只能贡献一个扰动。
    double HandTorque(double t, double p_now, double w_now) const
    {
        if (enc.hand_deg == 0.0)
            return 0.0;
        constexpr double kHand = 1.0;    // 手"刚度"（转子侧 [N·m/rad]）
        constexpr double dHand = 0.01;   // 手"阻尼"（转子侧 [N·m·s/rad]）
        constexpr double kHandMax = 1.0; // 人手能给的最大力矩（转子侧 [N·m]≈输出端 6.3 N·m：
                                         // 握着一个摇臂推得动，但比不上电机出力 20 N·m）
        const double ratio = 19.0 / 3.0;  // 转子圈 / 输出圈
        const double p_target =
            enc.hand_deg * M_PI / 180.0 * ratio * std::sin(2.0 * M_PI * t / enc.hand_period_s);
        double tau_hand = kHand * (p_target - p_now) - dHand * w_now;
        if (tau_hand > kHandMax)
            tau_hand = kHandMax;
        else if (tau_hand < -kHandMax)
            tau_hand = -kHandMax;
        return tau_hand;
    }

    // 断电（没上电）时的自由转子：只有手的外力 + 库仑摩擦，没有任何闭环力矩
    void FreeStep(double dt, double t)
    {
        const double tau_ext = HandTorque(t, p, w);
        if (powered) // 板子刚断电：真板子的速度和力矩在那一刻就不再更新了
        {
            powered = false;
            w = 0.0;
            tau = 0.0;
        }
        if (std::fabs(w) > 1e-3)
        {
            const double tau_net = tau_ext - tau_fric * (w > 0.0 ? 1.0 : -1.0);
            const double w_new = w + tau_net * dt / kJ_rotor;
            if ((w > 0.0 && w_new < 0.0) || (w < 0.0 && w_new > 0.0))
            {
                w = 0.0;
                tau = 0.0;
            }
            else
            {
                w = w_new;
                tau = tau_net;
            }
        }
        else if (std::fabs(tau_ext) > tau_fric)
        {
            tau = tau_ext - tau_fric * (tau_ext > 0.0 ? 1.0 : -1.0);
            w += tau * dt / kJ_rotor;
        }
        else
        {
            tau = 0.0;
            w = 0.0;
        }
        p += w * dt;
    }

    // "上电"这件事本身：单圈绝对值编码器上电时只知道自己落在哪个区间，圈数丢掉
    // ⇒ 报出来的读数重新落到 0…2π（等价于把基准重设成 -floor(p/2π)）
    void PowerCycle()
    {
        cycle_fired = true;
        enc.datum = -static_cast<int>(std::floor(p / (2.0 * M_PI)));
    }

    long RxFrame = 0; // 板子**收到**的命令帧数（断电窗口里也照数：窗口按它计时）
    bool powered = true; // 板子当前有没有上电（速度/力矩只有在通电时才更新，见 FreeStep）

    // 板子**对外报**的角度（转子侧 rad）：里程计 = 真实位置 + 基准；锯齿 = 再折回 0…2π
    double Reported() const
    {
        const double p_rep = p + enc.datum * 2.0 * M_PI;
        if (enc.mode != 1)
            return p_rep;
        double r = std::fmod(p_rep, 2.0 * M_PI);
        if (r < 0.0)
            r += 2.0 * M_PI;
        return r;
    }

    // 板子位置环用的角度：锯齿模式下板子自己知道圈数（对外只报一个区间），所以把上报值按
    // **最短有环差**折到 Pos_des 附近（|差| < 半圈）；采样足够密时成立（一帧最多转 2π
    // 的半圈以内）。
    double LoopPosition(double p_des) const
    {
        const double rep = Reported();
        if (enc.mode != 1)
            return rep;
        return rep + 2.0 * M_PI * std::floor((p_des - rep) / (2.0 * M_PI) + 0.5);
    }

    // 解一帧命令（raw → 物理量）；标度用实测值
    static void Decode(const ControlData_t& c, double* tau_des, double* w_des, double* p_des,
                       double* k_pos, double* k_spd)
    {
        *tau_des = c.comd.tor_des / 256.0;
        *w_des = c.comd.spd_des * M_PI / 128.0;
        *p_des = c.comd.pos_des * 2.0 * M_PI / 32768.0;
        *k_pos = c.comd.k_pos / 1280.0;
        *k_spd = c.comd.k_spd / 1280.0;
    }

    // 走一步（dt = 帧间隔）。转子等效惯量挑一个"像个电机"的量级（1e-3），闭环时间常数 J/K_W
    // 在 5 ms 步长下稳定：K_W=0.0125（输出端 kd=0.5）时 80 ms，K_W=0.0749（输出端 kd=3）时 13 ms。
    static constexpr double kJ_rotor = 1e-3; // 转子等效惯量 [kg·m²]

    void Step(const ControlData_t& c, double dt)
    {
        constexpr double kJ = kJ_rotor;
        ++frame;
        powered = true; // 有命令在处理 = 板子有电
        // 上电复位（丢圈数）：把基准设成"报出来的读数落回 0…2π"，与真板子上电的语义一致
        if (enc.cycle_frame > 0 && !cycle_fired && RxFrame >= enc.cycle_frame)
            PowerCycle();
        // 中途换基准（实机上是跨零点/上电才可能发生，见 docs/real.md §5.4 的第二种跨零点）。
        // 约定：jump_turns > 0 = 读数**往前**跳 k 个区间（报出来的 = 真值 + 基准，所以要 +）
        if (enc.mode != 1 && enc.jump_frame > 0 && !jump_fired && RxFrame >= enc.jump_frame)
        {
            jump_fired = true;
            enc.datum += enc.jump_turns;
        }
        double tau_des = 0, w_des = 0, p_des = 0, k_pos = 0, k_spd = 0;
        Decode(c, &tau_des, &w_des, &p_des, &k_pos, &k_spd);
        // 位置环量的是"板子报出来的角度"（所以上电认错零点 = 物理目标整段移一个区间，正好用来验证
        // S3–S5）
        double tau_cmd = tau_des + k_pos * (p_des - LoopPosition(p_des)) + k_spd * (w_des - w);
        if (tau_cmd > tau_max)
            tau_cmd = tau_max;
        else if (tau_cmd < -tau_max)
            tau_cmd = -tau_max;

        tau_cmd += HandTorque(RxFrame * dt, p, w); // 人手给的力矩不受电机限幅

        if (std::fabs(w) > 1e-3)
        { // 在转：库仑摩擦与运动方向相反
            const double tau_net = tau_cmd - tau_fric * (w > 0.0 ? 1.0 : -1.0);
            const double w_new = w + tau_net * dt / kJ;
            if ((w > 0.0 && w_new < 0.0) || (w < 0.0 && w_new > 0.0))
            {
                w = 0.0; // 摩擦在这一拍里刚好把速度吃光（粘滞）
                tau = 0.0;
            }
            else
            {
                w = w_new;
                tau = tau_net;
            }
        }
        else if (std::fabs(tau_cmd) > tau_fric)
        { // 本来停着：要先克服静摩擦才动
            tau = tau_cmd - tau_fric * (tau_cmd > 0.0 ? 1.0 : -1.0);
            w += tau * dt / kJ;
        }
        else
        { // 静摩擦：这么小的力矩推不动
            tau = 0.0;
            w = 0.0;
        }
        p += w * dt;
        temp += 0.05 * dt * std::fabs(tau) / tau_max; // 力矩越大慢慢越热（演示用，不是热模型）
        if (temp > 89.0)
            merror = 1; // 90 °C 触发保护（报文的 merror 位）
    }

    // 打包一帧反馈（物理量 → raw）
    void Fill(const ControlData_t& cmd, MotorData_t* r) const
    {
        std::memset(r, 0, sizeof(*r));
        r->head[0] = 0xfe;
        r->head[1] = 0xee;
        r->mode.id = cmd.mode.id;
        r->mode.status = static_cast<uint8_t>(1 | enc.status_bits); // 1 = FOC，另两位是注入的状态位
        r->fbk.torque = static_cast<int16_t>(std::lround(tau * 256.0));
        r->fbk.speed = static_cast<int16_t>(std::lround(w * 128.0 / M_PI));
        r->fbk.pos = static_cast<int32_t>(std::lround(Reported() * 32768.0 / (2.0 * M_PI)));
        r->fbk.temp = static_cast<int8_t>(std::lround(temp));
        r->fbk.MError = merror;
        const uint16_t crc =
            crc_ccitt(0, reinterpret_cast<const uint8_t*>(r), sizeof(*r) - CRC_SIZE);
        std::memcpy(reinterpret_cast<uint8_t*>(r) + sizeof(*r) - CRC_SIZE, &crc, CRC_SIZE);
    }
};

// 起一条线程当"驱动器板"：收 17 字节命令 → Step → 回 16 字节反馈；stop 置 true 后退出
inline std::thread Start(int master_fd, std::atomic<bool>* stop, Model model)
{
    return std::thread(
        [master_fd, stop, model]() mutable
        {
            unsigned char buf[sizeof(ControlData_t)];
            int got = 0;
            const double dt = 0.005; // 与调用方 5 ms 一帧对应
            long rx = 0;             // 收到的命令帧数（含断电窗口里被丢掉的）
            while (!stop->load())
            {
                const ssize_t n =
                    ::read(master_fd, buf + got, sizeof(buf) - static_cast<size_t>(got));
                if (n > 0)
                {
                    got += static_cast<int>(n);
                    if (got != static_cast<int>(sizeof(buf)))
                        continue;
                    got = 0;
                    ++rx;
                    model.RxFrame = rx;
                    // 断电窗口：板子"没上电" ⇒ 收到命令也不积分、不回帧（等价于掉线）。
                    // 计时必须用 rx（收到的帧数），不能用 Step 里的 frame —— 窗口内不 Step，
                    // 用 frame 计时窗口永远不结束。
                    if (model.enc.off_after > 0 && rx >= model.enc.off_after &&
                        rx < model.enc.off_after + model.enc.off_frames)
                    {
                        model.FreeStep(dt, rx * dt); // 没上电：转子自由，人手可以推着转
                        continue;
                    }
                    // 断电窗口刚结束 = 板子重新上电：单圈绝对值编码器丢掉圈数，
                    // 报出来的 raw 重新落回 0…2π（这正是 S2f/上电基准那件事）
                    if (model.enc.off_after > 0 && model.enc.off_frames > 0 && !model.cycle_fired &&
                        rx >= model.enc.off_after + model.enc.off_frames)
                        model.PowerCycle();
                    ControlData_t c;
                    std::memcpy(&c, buf, sizeof(c));
                    model.Step(c, dt);
                    MotorData_t r;
                    model.Fill(c, &r);
                    if (::write(master_fd, &r, sizeof(r)) != static_cast<ssize_t>(sizeof(r)))
                        std::printf("假电机：回帧写失败\n");
                }
                else if (n < 0)
                {
                    usleep(200);
                }
            }
        });
}

} // namespace motor_bench::sim
