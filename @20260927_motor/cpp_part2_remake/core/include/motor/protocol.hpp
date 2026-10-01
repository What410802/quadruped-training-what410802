/**
 * @file protocol.hpp
 * @brief 报文层的定点标度（实测值）：raw 与物理量的换算、截断与钳位规则。
 *
 * 这里的数字来自实机实测（见旧版 docs/protocol.md）：位置就是计数（q15 转子圈），
 * 速度 raw = ω×128/π，力矩 raw = τ×256，增益 raw = K×1280 且超 32766 静默钳位；
 * 打包时用整数除法，所以"写进去的"会掉 1 LSB。实机链路由官方 SDK 打包，本文件供
 * 测试钉住这些数字、并供仿真后端按同一规则收发。
 */

#pragma once

#include "motor/counts.hpp"

#include <cstdint>

namespace motor
{

inline constexpr double kSpeedRawPerRotorRadPerSec = 128.0 / kPi; // 手册 §8.2：ω_set = ω/(2π)×256
inline constexpr double kTorqueRawPerNm = 256.0;                  // q8
inline constexpr double kGainRawPerUnit = 1280.0;                 // 实测：不随 N 变
inline constexpr std::int32_t kGainRawMax = 32766;                // 超量程静默钳位到 32766

/** 转子侧角速度 [rad/s] → 报文 spd_des（截断） */
inline std::int32_t speed_raw_from_rotor_rad(double speed_rad_per_s)
{
    return static_cast<std::int32_t>(speed_rad_per_s * kSpeedRawPerRotorRadPerSec);
}

/** 报文 speed → 转子侧角速度 [rad/s] */
inline double rotor_rad_from_speed_raw(std::int32_t raw)
{
    return static_cast<double>(raw) / kSpeedRawPerRotorRadPerSec;
}

/** 转子侧力矩 [N·m] → 报文 tor_des（截断） */
inline std::int32_t torque_raw_from_rotor_nm(double torque_nm)
{
    return static_cast<std::int32_t>(torque_nm * kTorqueRawPerNm);
}

/** 报文 torque → 转子侧力矩 [N·m] */
inline double rotor_nm_from_torque_raw(std::int32_t raw)
{
    return static_cast<double>(raw) / kTorqueRawPerNm;
}

/** 转子侧增益 → 报文 k_pos / k_spd（截断 + 钳位） */
inline std::int32_t gain_raw_from_rotor_gain(double gain)
{
    const double raw = gain * kGainRawPerUnit;
    if (raw <= 0.0)
    {
        return 0;
    }
    if (raw >= static_cast<double>(kGainRawMax))
    {
        return kGainRawMax;
    }
    return static_cast<std::int32_t>(raw);
}

/** 报文 k_pos / k_spd → 转子侧增益 */
inline double rotor_gain_from_gain_raw(std::int32_t raw)
{
    return static_cast<double>(raw) / kGainRawPerUnit;
}

} // namespace motor
