/**
 * @file ticks.hpp
 * @brief 定点表示与三个边界上的换算：内部一律用"转子侧 tick"（int64，1 tick = 1/32768 转子圈）。
 *
 * 只在三处与别的表示打交道：
 *   1. 收（回帧 → tick）：ReadFeedback()，直接读回帧里的整数 `fbk.pos`，不经过 SDK 的 float；
 *   2. 发（tick → cmd.q）：CmdQRotor()，按 SDK 实际使用的 π′ = 3.1416 换算，使报文里的 `pos_des`
 *      正好等于我们想要的 tick；
 *   3. 与人（tick ↔ 度）：TicksToDeg() / DegToTicks()，只在打印与命令行输入处调用。
 *
 * 为什么内部用转子侧：报文的 `pos` 就是转子侧的整数 tick，零点跳变是"整 32768"，
 * 减速比是有理数 19:3 —— 这三件事在转子 tick 上都是精确整数运算。详见
 * docs/fixed_point.md §5 与 docs/zero_semantics.md。
 */
#pragma once

#include "unitreeMotor/unitreeMotor.h"

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace motor_bench::ticks
{

constexpr int64_t kTicksPerTurn = 32768;         // pos 的定点：q15 圈（转子侧）
constexpr int64_t kTicksPerZone = kTicksPerTurn; // 一个零点区间 = 转子整圈 = 输出端 56.8421°
constexpr double kGearTrue = 19.0 / 3.0; // 真实减速比（讲义 §2.4：转子 19 圈 / 输出端 3 圈）
constexpr double kGearSdk = 6.33; // SDK queryGearRatio() 返回的值（相对差 5.26e-4）
constexpr double kPiSdk = 3.1416; // SDK 实际使用的 π（实测，不是真 π）

/** tick → 输出端角度（用真实减速比） */
inline double TicksToDeg(int64_t t)
{
    return static_cast<double>(t) / kTicksPerTurn * (360.0 / kGearTrue);
}

/** 输出端角度 → tick */
inline int64_t DegToTicks(double deg)
{
    return std::llround(deg / (360.0 / kGearTrue) * kTicksPerTurn);
}

/** tick → 输出端弧度（只在需要物理量时用） */
inline double TicksToRadOut(int64_t t)
{
    return TicksToDeg(t) * M_PI / 180.0;
}

/** tick → 转子侧弧度；用 SDK 的那个 π′，保证往返一致 */
inline double TicksToRadRotor(int64_t t)
{
    return static_cast<double>(t) * (2.0 * kPiSdk / kTicksPerTurn);
}

/** 转子侧弧度 → tick（与上面互逆） */
inline int64_t RadRotorToTicks(double rad)
{
    return std::llround(rad / (2.0 * kPiSdk) * kTicksPerTurn);
}

/** tick → cmd.q（走 SDK 的 float 接口时必须这样换算，见文件头注释） */
inline float CmdQRotor(int64_t t)
{
    return static_cast<float>(TicksToRadRotor(t));
}

/** 离最近零点边界的距离（tick），用于提示"这个位置上电最容易认错零点" */
inline int64_t DistanceToZoneEdge(int64_t t)
{
    const int64_t in_zone = ((t % kTicksPerZone) + kTicksPerZone) % kTicksPerZone;
    const int64_t rest = kTicksPerZone - in_zone;
    return in_zone < rest ? in_zone : rest;
}

/** 一帧反馈：整数为主，`q_float` 只用于对拍/显示 */
struct Feedback
{
    int64_t pos = 0;     // 转子侧位置（tick）—— 唯一权威的位置量
    int32_t pos_raw = 0; // 报文里的原始 int32（= pos）
    int speed_raw = 0;   // int16：ω_rotor = raw × π/128
    int torque_raw = 0;  // int16：τ_rotor = raw/256
    int temp = 0;        // °C
    unsigned merror = 0; // 0 正常 / 1 过热 / 2 过流 / 3 过压 / 4 编码器 / 5 母线欠压 / 6 绕组过热
    unsigned status = 0; // 回帧 mode 字节的 3 bit 状态：bit1 = 期望速度超范围、bit2 = 期望位置超范围
    bool from_raw = false; // true = 读到原始帧；false = 退化成用 SDK 的 float q 反算
    double q_float = 0.0;  // SDK 的 data.q（不作权威值）

    bool DesSpeedOutOfRange() const { return (status & 0x2u) != 0; }
    bool DesPosOutOfRange() const { return (status & 0x4u) != 0; }
};

/**
 * @brief 读一帧反馈：优先用 public 的 get_motor_recv_data() 拿 16 B 原始帧里的整数，
 *        拿不到时退回 SDK 的 float q；`warned` 非空时，两者差 > 2 tick 只提醒一次。
 */
inline void ReadFeedback(const MotorData& d, Feedback* fb, bool* warned = nullptr)
{
    fb->q_float = d.q;
    fb->temp = d.temp;
    fb->merror = static_cast<unsigned>(d.merror);
    const uint8_t* raw = const_cast<MotorData&>(d).get_motor_recv_data();
    if (raw != nullptr)
    {
        MotorData_t frame;
        std::memcpy(&frame, raw, sizeof(frame));
        fb->pos_raw = frame.fbk.pos;
        fb->pos = static_cast<int64_t>(frame.fbk.pos);
        fb->speed_raw = frame.fbk.speed;
        fb->torque_raw = frame.fbk.torque;
        fb->temp = frame.fbk.temp;
        fb->merror = frame.fbk.MError;
        fb->status = frame.mode.status & 0x7u;
        fb->from_raw = true;
    }
    else
    {
        fb->pos = RadRotorToTicks(d.q);
        fb->pos_raw = static_cast<int32_t>(fb->pos);
        fb->speed_raw = static_cast<int>(std::llround(static_cast<double>(d.dq) / 2.0));
        fb->torque_raw = static_cast<int>(std::llround(d.tau * 256.0));
        fb->status = 0;
        fb->from_raw = false;
    }
    if (fb->from_raw && warned != nullptr && !*warned)
    {
        const int64_t via_float = RadRotorToTicks(d.q);
        if (std::llabs(via_float - fb->pos) > 2)
        {
            std::printf("    ⚠ SDK 的 data.q 反算得 %lld tick，与回帧整数 %lld tick 差 %lld"
                        "（≥2 tick：SDK 换实现？）\n",
                        static_cast<long long>(via_float), static_cast<long long>(fb->pos),
                        static_cast<long long>(via_float - fb->pos));
            *warned = true;
        }
    }
}

} // namespace motor_bench::ticks
