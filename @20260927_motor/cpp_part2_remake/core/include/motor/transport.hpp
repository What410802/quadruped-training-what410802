/**
 * @file transport.hpp
 * @brief 设备帧与传输接口：core 只认识这两个结构；实机（SDK）与仿真（假电机）各实现一个 Transport。
 */

#pragma once

#include "motor/counts.hpp"

namespace motor
{

/** 一帧命令（转子侧；位置是"板子读数空间"的计数） */
struct DeviceCommand
{
    Counts pos_counts = 0; // = q_des − offset − turn_base（板子的位置环按它自己的读数折）
    double speed_rotor = 0.0; // 转子侧速度前馈 [rad/s]（= 转子计数/秒 × 2π′/32768）
    double torque_rotor = 0.0; // 转子侧前馈力矩 [N·m]
    double kp_rotor = 0.0;     // 转子侧刚度 [N·m/rad]
    double kd_rotor = 0.0;     // 转子侧阻尼 [N·m·s/rad]
    bool zero_torque = true;   // true ⇒ 五个量全 0（明示零力矩，防止漏清）
};

/** 一帧反馈（转子侧；位置是板子回帧的原始整数） */
struct DeviceFeedback
{
    RawCounts raw = 0;         // 回帧 pos（q15 转子圈；上电后 ∈ [0, 32768)）
    double speed_rotor = 0.0;  // [rad/s]
    double torque_rotor = 0.0; // [N·m]
    int temp_c = 0;
    unsigned merror = 0;
    unsigned status_bits = 0; // bit1 期望速度超范围、bit2 期望位置超范围
};

class Transport
{
  public:
    virtual ~Transport() = default;

    /** 发一帧并读回一帧；false = 本帧没有回复（超时 / 掉线） */
    virtual bool send(const DeviceCommand& command, DeviceFeedback* feedback) = 0;

    /** 传输名（打印用） */
    virtual const char* name() const = 0;
};

} // namespace motor
