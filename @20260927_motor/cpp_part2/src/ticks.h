// 定点数的唯一入口：**内部一律用"转子侧 tick"表示位置**（int64，1 tick = 1/32768 转子圈），
// 只在三个边界上与别的表示打交道：
//   1. 收（回帧 → tick）：`ReadFeedback()`，直接读回帧里的整数 `fbk.pos`（不经过 SDK 的 float）；
//   2. 发（tick → cmd.q）：`CmdQRotor()`，按 **SDK 用的那个 π′ = 3.1416** 换算，这样 SDK 打包回整数时
//      得到的 `pos_des` 正好是我们想要的 tick（若用真 π 会有 2.34 ppm 的标度差，见 docs/fixed_point.md §4）；
//   3. 与人打交道（tick ↔ 度）：`TicksToDeg()` / `DegToTicks()`，**只在打印与命令行输入处调用**。
//
// 为什么内部用**转子侧**而不是输出端：报文的 pos 就是转子侧的整数 tick，零点跳变是"整 32768"，
// 减速比是 19:3（有理数）——在转子 tick 上这些都是精确整数运算。输出端的角度是给人看的派生量，
// 换算时用**真实减速比 19:3**（`kGearTrue`）；SDK 的 `queryGearRatio()` 返回 6.33，
// 只在"走 SDK 的 float 接口"时要按 SDK 的口径算，见 CmdQRotor() 的注释。
#pragma once

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>

#include "unitreeMotor/unitreeMotor.h"

namespace ticks {

constexpr int64_t kTicksPerTurn = 32768;          // pos 的定点：q15 圈（转子侧）
constexpr double kGearTrue = 19.0 / 3.0;          // 真实减速比（讲义 §2.4：转子 19 圈 / 输出端 3 圈）
constexpr double kGearSdk = 6.33;                 // SDK queryGearRatio() 返回的值（差 5.26e-4 相对）
constexpr double kPiSdk = 3.1416;                 // SDK 实际用的 π（实测，不是真 π）

// ---------- 三个边界上的换算 ----------

// tick → 转子侧弧度、转子侧弧度 → tick（用的是"发/收报文时该用的 π"）
inline double TicksToRadRotor(int64_t t) { return double(t) * (2.0 * kPiSdk / kTicksPerTurn); }
inline int64_t RadRotorToTicks(double rad) { return std::llround(rad / (2.0 * kPiSdk) * kTicksPerTurn); }

// tick → 输出端角度（真实减速比 19:3）；输出端角度 → tick
inline double TicksToDeg(int64_t t) { return double(t) / kTicksPerTurn * (360.0 / kGearTrue); }
inline int64_t DegToTicks(double deg) { return std::llround(deg / (360.0 / kGearTrue) * kTicksPerTurn); }

// tick → 输出端弧度（只在需要物理量时用；注意 kGearSdk 与 kGearTrue 差 0.05%，换算"输出端物理量"要用真值）
inline double TicksToRadOut(int64_t t) { return TicksToDeg(t) * M_PI / 180.0; }

// 一个零点区间 = 转子整圈 = 32768 tick = 输出端 360°/(19/3) = 56.8421°

// ---------- 收：回帧 → 整数 tick ----------

struct Feedback {
    int64_t pos = 0;         // 转子侧位置（tick）—— 唯一"权威"的位置量
    int32_t pos_raw = 0;     // 报文里的原始 int32（= pos，留一份便于对拍/打印）
    int speed_raw = 0;       // int16：ω_rotor = raw × π/128（手册 §8.2 的 256/2π）
    int torque_raw = 0;      // int16：τ_rotor = raw/256
    int temp = 0;            // °C
    unsigned merror = 0;     // 0 正常 / 1 过热 / 2 过流 / 3 过压 / 4 编码器故障 / 5 母线欠压 / 6 绕组过热
    bool from_raw = false;   // true = 读到了原始帧；false = 退化成用 SDK 的 float q 反算
    double q_float = 0.0;    // SDK 的 data.q（只用于对拍/显示；它不是权威值）
};

// 读一帧反馈。优先用 public 的 `get_motor_recv_data()`（16 B 原始帧），拿不到时退回 SDK 的 float q。
// `warn` 非空时，若 float 反算与整数差得超过 2 tick 就打印一次提醒（防 SDK 版本换实现）。
inline void ReadFeedback(const MotorData &d, Feedback *fb, bool *warned = nullptr) {
    fb->q_float = d.q;
    fb->temp = d.temp;
    fb->merror = static_cast<unsigned>(d.merror);
    const uint8_t *raw = const_cast<MotorData &>(d).get_motor_recv_data();
    if (raw != nullptr) {
        MotorData_t frame;
        std::memcpy(&frame, raw, sizeof(frame));
        fb->pos_raw = frame.fbk.pos;
        fb->pos = static_cast<int64_t>(frame.fbk.pos);
        fb->speed_raw = frame.fbk.speed;
        fb->torque_raw = frame.fbk.torque;
        fb->temp = frame.fbk.temp;
        fb->merror = frame.fbk.MError;
        fb->from_raw = true;
    } else {
        fb->pos = RadRotorToTicks(d.q);
        fb->pos_raw = static_cast<int32_t>(fb->pos);
        fb->speed_raw = static_cast<int>(std::llround(static_cast<double>(d.dq) / 2.0));  // π/128 → rad/s
        fb->torque_raw = static_cast<int>(std::llround(d.tau * 256.0));
        fb->from_raw = false;
    }
    if (fb->from_raw && warned != nullptr && !*warned) {
        const int64_t via_float = RadRotorToTicks(d.q);
        if (std::llabs(via_float - fb->pos) > 2) {
            std::printf("    ⚠ SDK 的 data.q 反算得 %lld tick，与回帧整数 %lld tick 差 %lld "
                        "（≥2 tick：SDK 版本换了换算常数？）\n",
                        static_cast<long long>(via_float), static_cast<long long>(fb->pos),
                        static_cast<long long>(via_float - fb->pos));
            *warned = true;
        }
    }
}

// ---------- 发：tick → cmd.q（走 SDK 的 float 接口） ----------

// **必须经过 SDK 时**这样写：cmd.q 用 SDK 的 π′ 换算 —— 因为 SDK 打包时算 `q/(2π′)×32768`，
// 两边用同一个 π′ 才能让报文里的 `pos_des` 正好等于我们要的 tick。
// （若自己组帧就没有这个问题：`TicksToRaw()` 直接就是 pos_des，见 docs/fixed_point.md §5.2。）
inline float CmdQRotor(int64_t t) { return static_cast<float>(TicksToRadRotor(t)); }

// 自己组帧时的 pos_des（int32）
inline int32_t TicksToRaw(int64_t t) { return static_cast<int32_t>(t); }

} // namespace ticks
