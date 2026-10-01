/**
 * @file unitree_transport.cpp
 * @brief UnitreeTransport 的实现：组 MotorCmd（按 π′ 把计数换成 float 弧度）→ sendRecv →
 * 解回设备帧。
 */

#include "motor_unitree/unitree_transport.hpp"

#include "motor/counts.hpp"
#include "motor/protocol.hpp"

#include "serialPort/SerialPort.h"
#include "unitreeMotor/unitreeMotor.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace motor_unitree
{

struct UnitreeTransport::Impl
{
    Impl(const std::string& port, int motor_id, int baud)
        : serial(port, 16, static_cast<uint32_t>(baud)), id(motor_id)
    {
        command.motorType = MotorType::GO_M8010_6;
        data.motorType = MotorType::GO_M8010_6;
        command.mode =
            static_cast<unsigned short>(queryMotorMode(MotorType::GO_M8010_6, MotorMode::FOC));
        command.id = static_cast<unsigned short>(motor_id);
        command.tau = 0.0f;
        command.dq = 0.0f;
        command.q = 0.0f;
        command.kp = 0.0f;
        command.kd = 0.0f;
    }

    SerialPort serial;
    MotorCmd command{};
    MotorData data{};
    int id = 0;
    bool warned_float_mismatch = false;
};

UnitreeTransport::UnitreeTransport(const std::string& port, int id, int baud)
    : impl_(new Impl(port, id, baud))
{
}

UnitreeTransport::~UnitreeTransport() = default;

std::unique_ptr<UnitreeTransport> UnitreeTransport::open(const std::string& port, int id, int baud,
                                                         std::string* error)
{
    try
    {
        std::unique_ptr<UnitreeTransport> transport(new UnitreeTransport(port, id, baud));
        return transport;
    }
    catch (const std::exception& exception)
    {
        if (error != nullptr)
        {
            *error = exception.what();
        }
        return nullptr;
    }
    catch (...)
    {
        if (error != nullptr)
        {
            *error = "未知异常（不是 std::exception）";
        }
        return nullptr;
    }
}

bool UnitreeTransport::send(const motor::DeviceCommand& command, motor::DeviceFeedback* feedback)
{
    Impl& impl = *impl_;
    if (command.zero_torque)
    {
        impl.command.q = 0.0f;
        impl.command.dq = 0.0f;
        impl.command.tau = 0.0f;
        impl.command.kp = 0.0f;
        impl.command.kd = 0.0f;
    }
    else
    {
        // 位置：计数 → 转子侧 float 弧度（用实测的 π′）。SDK 打包时按同一个 π′ 除回去，
        // 报文里的 pos_des 因此正好等于想要的位置计数（±1 LSB 截断）。
        impl.command.q = motor::counts_to_sdk_q(command.pos_counts);
        impl.command.dq = static_cast<float>(command.speed_rotor);
        impl.command.tau = static_cast<float>(command.torque_rotor);
        impl.command.kp = static_cast<float>(command.kp_rotor);
        impl.command.kd = static_cast<float>(command.kd_rotor);
    }

    if (!impl.serial.sendRecv(&impl.command, &impl.data))
    {
        return false;
    }
    if (feedback == nullptr)
    {
        return true;
    }

    // 优先用 16 B 原始回帧里的整数（权威值，见 docs/protocol.md）；拿不到再退回 SDK 的 float。
    feedback->raw = static_cast<motor::RawCounts>(motor::rotor_rad_to_counts(impl.data.q));
    feedback->speed_rotor = impl.data.dq;
    feedback->torque_rotor = impl.data.tau;
    feedback->temp_c = impl.data.temp;
    feedback->merror = static_cast<unsigned>(impl.data.merror);
    feedback->status_bits = 0;

    uint8_t* raw = impl.data.get_motor_recv_data();
    if (raw != nullptr)
    {
        MotorData_t frame;
        std::memcpy(&frame, raw, sizeof(frame));
        feedback->raw = frame.fbk.pos;
        feedback->speed_rotor = motor::rotor_rad_from_speed_raw(frame.fbk.speed);
        feedback->torque_rotor = motor::rotor_nm_from_torque_raw(frame.fbk.torque);
        feedback->temp_c = frame.fbk.temp;
        feedback->merror = frame.fbk.MError;
        feedback->status_bits = frame.mode.status & 0x7u;

        if (!impl.warned_float_mismatch)
        {
            const motor::Counts via_float = motor::rotor_rad_to_counts(impl.data.q);
            if (std::llabs(via_float - feedback->raw) > 2)
            {
                std::printf(
                    "    ⚠ 回帧整数 %lld 与 SDK 的 float q 反算 %lld 差 >2 计数（SDK 换实现？）\n",
                    static_cast<long long>(feedback->raw), static_cast<long long>(via_float));
                impl.warned_float_mismatch = true;
            }
        }
    }
    return true;
}

const char* UnitreeTransport::name() const
{
    return "unitree-sdk";
}

} // namespace motor_unitree
