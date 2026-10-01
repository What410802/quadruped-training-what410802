/**
 * @file wire.cpp
 * @brief wire.hpp 的实现：直接借用 SDK 的报文结构体与 CRC 表（只包含头文件，不链 .so）。
 *
 * SDK 的 crc_ccitt.h 自己没有 include <stdint.h>/<stddef.h>，所以标准头必须排在它前面。
 */

#include "motor_wire/wire.hpp"

#include "motor/protocol.hpp"

#include <cstddef>
#include <cstdint>

#include "crc/crc_ccitt.h"
#include "unitreeMotor/include/motor_msg_GO-M8010-6.h"

#include <algorithm>
#include <cstring>

namespace motor_wire
{
namespace
{

std::int16_t clamp_i16(double value)
{
    return static_cast<std::int16_t>(std::clamp(value, -32768.0, 32767.0));
}

std::uint16_t frame_crc(const std::uint8_t* frame, std::size_t size)
{
    return crc_ccitt(0, frame, size - CRC_SIZE);
}

} // namespace

motor::DeviceCommand decode_command(const std::uint8_t* frame, CommandMeta* meta)
{
    ControlData_t control;
    std::memcpy(&control, frame, sizeof(control));

    if (meta != nullptr)
    {
        meta->id = control.mode.id;
        meta->status = control.mode.status;
        meta->crc_ok = (frame_crc(frame, sizeof(control)) == control.CRC16);
    }

    motor::DeviceCommand command;
    command.zero_torque = false; // 由字段全零与否体现；调用方（实验台）直接用这些字段
    command.torque_rotor = motor::rotor_nm_from_torque_raw(control.comd.tor_des);
    command.speed_rotor = motor::rotor_rad_from_speed_raw(control.comd.spd_des);
    command.pos_counts = control.comd.pos_des;
    command.kp_rotor = motor::rotor_gain_from_gain_raw(control.comd.k_pos);
    command.kd_rotor = motor::rotor_gain_from_gain_raw(control.comd.k_spd);
    if (control.comd.tor_des == 0 && control.comd.spd_des == 0 && control.comd.pos_des == 0 &&
        control.comd.k_pos == 0 && control.comd.k_spd == 0)
    {
        command.zero_torque = true;
    }
    return command;
}

void encode_reply(const motor::DeviceFeedback& feedback, unsigned id, unsigned status,
                  std::uint8_t* frame)
{
    MotorData_t reply;
    std::memset(&reply, 0, sizeof(reply));
    reply.head[0] = 0xfe;
    reply.head[1] = 0xee;
    reply.mode.id = static_cast<std::uint8_t>(id & 0xf);
    reply.mode.status = static_cast<std::uint8_t>(status & 0x7);
    reply.fbk.torque = clamp_i16(motor::torque_raw_from_rotor_nm(feedback.torque_rotor));
    reply.fbk.speed = clamp_i16(motor::speed_raw_from_rotor_rad(feedback.speed_rotor));
    reply.fbk.pos = static_cast<std::int32_t>(feedback.raw);
    reply.fbk.temp = static_cast<std::int8_t>(std::clamp(feedback.temp_c, -128, 127));
    reply.fbk.MError = static_cast<std::uint8_t>(feedback.merror & 0x7);
    reply.CRC16 = frame_crc(reinterpret_cast<const std::uint8_t*>(&reply), sizeof(reply));
    std::memcpy(frame, &reply, sizeof(reply));
}

} // namespace motor_wire
