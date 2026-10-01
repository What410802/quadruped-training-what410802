/**
 * @file counts.hpp
 * @brief 位置与角度的换算：core 内部一律"转子侧计数"，只在人机边界与报文边界换出去。
 */

#pragma once

#include <cmath>
#include <cstdint>

namespace motor
{

// 位置在 core 内部一律用"转子侧计数"（int64）：1 计数 = 1/32768 转子圈，就是板子回帧 pos 的单位。
// 只有两处会换出去：人机边界（输出端度 / 弧度 / 圈）与报文边界（转子侧 float 弧度，见
// protocol.hpp）。
using Counts = std::int64_t;
using RawCounts = std::int32_t;

inline constexpr Counts kCountsPerTurn = 32768;
inline constexpr double kPi = 3.14159265358979323846;
inline constexpr double kGearRatio =
    19.0 / 3.0; // 真减速比（讲义 §2.4；SDK 的 queryGearRatio 报 6.33）
inline constexpr double kSdkPi = 3.1416; // SDK float 换算用的 π′（实测，不是真 π）
inline constexpr double kZoneDegrees =
    360.0 / kGearRatio; // 一个零点区间 = 一个转子圈 = 56.8421°（输出端）

/** 输出端角度（度）→ 计数 */
inline Counts output_deg_to_counts(double deg)
{
    return std::llround(deg * static_cast<double>(kCountsPerTurn) * kGearRatio / 360.0);
}

/** 计数 → 输出端角度（度） */
inline double counts_to_output_deg(Counts counts)
{
    return static_cast<double>(counts) / static_cast<double>(kCountsPerTurn) * (360.0 / kGearRatio);
}

/** 输出端弧度 → 计数 */
inline Counts output_rad_to_counts(double rad)
{
    return std::llround(rad * static_cast<double>(kCountsPerTurn) * kGearRatio / (2.0 * kPi));
}

/** 计数 → 输出端弧度 */
inline double counts_to_output_rad(Counts counts)
{
    return static_cast<double>(counts) / static_cast<double>(kCountsPerTurn) *
           (2.0 * kPi / kGearRatio);
}

/** 输出端圈数 → 计数 */
inline Counts output_turns_to_counts(double turns)
{
    return std::llround(turns * static_cast<double>(kCountsPerTurn) * kGearRatio);
}

/** 计数 → 输出端圈数 */
inline double counts_to_output_turns(Counts counts)
{
    return static_cast<double>(counts) / (static_cast<double>(kCountsPerTurn) * kGearRatio);
}

/** 计数 → 转子侧弧度；用 SDK 的 π′，保证与报文往返一致 */
inline double counts_to_rotor_rad(Counts counts)
{
    return static_cast<double>(counts) * (2.0 * kSdkPi / static_cast<double>(kCountsPerTurn));
}

/** 转子侧弧度 → 计数（与上面互逆） */
inline Counts rotor_rad_to_counts(double rad)
{
    return std::llround(rad / (2.0 * kSdkPi) * static_cast<double>(kCountsPerTurn));
}

/** 计数 → SDK 的 cmd.q（转子侧 float 弧度；只有实机后端用） */
inline float counts_to_sdk_q(Counts counts)
{
    return static_cast<float>(counts_to_rotor_rad(counts));
}

/** delta 是几个整圈（最近的整数倍） */
inline Counts turns_of_delta(Counts delta)
{
    const Counts t = kCountsPerTurn;
    return (delta >= 0 ? delta + t / 2 : delta - t / 2) / t;
}

/** 离最近零点边界的距离（计数），用于提示"这里上电最容易认错零点" */
inline Counts distance_to_zone_edge(Counts counts)
{
    const Counts in_zone = ((counts % kCountsPerTurn) + kCountsPerTurn) % kCountsPerTurn;
    const Counts rest = kCountsPerTurn - in_zone;
    return in_zone < rest ? in_zone : rest;
}

} // namespace motor
