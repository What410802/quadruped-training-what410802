/**
 * @file wire.hpp
 * @brief 宇树 GO-M8010-6 报文的编解码：17 B 命令帧解帧 / 16 B 回帧组帧（含 CRC）。
 *
 * 只依赖 SDK 的**头文件**（结构体与 crc_ccitt 表）与 core 的标度定义（protocol.hpp），不链 SDK 的
 * `.so`。实验台（apps/motor_sim）与报文往返测试共用；实机运行时不走这里（那条路径是 SDK
 * 自己打包）。
 */

#pragma once

#include "motor/transport.hpp"

#include <cstdint>

namespace motor_wire
{

inline constexpr std::size_t kCommandSize = 17; // fe ee + mode + 12 B comd + crc16
inline constexpr std::size_t kReplySize = 16;   // fe ee + mode + 11 B fbk + crc16
inline constexpr unsigned kStatusFoc = 1;       // mode.status 的 FOC 值

struct CommandMeta
{
    unsigned id = 0;     // mode.id（4 bit）
    unsigned status = 0; // mode.status（3 bit：0 锁定 / 1 FOC / 2 校准）
    bool crc_ok = false; // 命令帧 CRC 是否自洽
};

/** 解 17 B 命令帧 → 设备命令（转子侧；位置是板子读数计数） */
motor::DeviceCommand decode_command(const std::uint8_t* frame, CommandMeta* meta);

/** 组 16 B 回帧（含 CRC）；id 与 status 由调用方给（实验台回 FOC） */
void encode_reply(const motor::DeviceFeedback& feedback, unsigned id, unsigned status,
                  std::uint8_t* frame);

} // namespace motor_wire
