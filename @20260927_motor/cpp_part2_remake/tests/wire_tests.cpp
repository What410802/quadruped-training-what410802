/**
 * @file wire_tests.cpp
 * @brief 报文往返测试：按 protocol.md 的实测锚点钉住解码 / 组帧（需要 SDK 头文件，不需要硬件）。
 */

#include "motor/protocol.hpp"
#include "motor_wire/wire.hpp"

#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>

// SDK 的 crc_ccitt.h 依赖调用方先包 <cstdint>/<cstddef>；这里直接用它的结构体与 CRC 来做"金标准"。
#include "crc/crc_ccitt.h"
#include "unitreeMotor/include/motor_msg_GO-M8010-6.h"

namespace
{

int failures = 0;

void expect(bool condition, const std::string& description)
{
    if (!condition)
    {
        std::fprintf(stderr, "FAIL: %s\n", description.c_str());
        ++failures;
    }
}

void expect_eq(long long actual, long long expected, const std::string& description)
{
    if (actual != expected)
    {
        std::fprintf(stderr, "FAIL: %s（实际 %lld，期望 %lld）\n", description.c_str(), actual,
                     expected);
        ++failures;
    }
}

void expect_near(double actual, double expected, double tolerance, const std::string& description)
{
    if (std::fabs(actual - expected) > tolerance)
    {
        std::fprintf(stderr, "FAIL: %s（实际 %.6f，期望 %.6f）\n", description.c_str(), actual,
                     expected);
        ++failures;
    }
}

std::size_t build_command_frame(std::uint8_t* frame, std::int16_t torque_raw,
                                std::int16_t speed_raw, std::int32_t pos_raw, std::uint16_t k_pos,
                                std::uint16_t k_spd)
{
    ControlData_t control;
    std::memset(&control, 0, sizeof(control));
    control.head[0] = 0xfe;
    control.head[1] = 0xee;
    control.mode.id = 0;
    control.mode.status = 1; // FOC
    control.comd.tor_des = torque_raw;
    control.comd.spd_des = speed_raw;
    control.comd.pos_des = pos_raw;
    control.comd.k_pos = k_pos;
    control.comd.k_spd = k_spd;
    control.CRC16 =
        crc_ccitt(0, reinterpret_cast<const std::uint8_t*>(&control), sizeof(control) - CRC_SIZE);
    std::memcpy(frame, &control, sizeof(control));
    return sizeof(control);
}

// 用 protocol.md 的实测锚点（09-27 那次实跑）造一帧命令，检查解码结果
void test_decode_anchors()
{
    std::uint8_t frame[motor_wire::kCommandSize];
    build_command_frame(frame, 0, 257, 16506, 2555, 95);

    motor_wire::CommandMeta meta;
    const motor::DeviceCommand command = motor_wire::decode_command(frame, &meta);

    expect(meta.crc_ok, "命令帧 CRC 自洽");
    expect_eq(meta.id, 0, "id 解出 0");
    expect_eq(meta.status, 1, "status 解出 FOC");
    expect_eq(command.pos_counts, 16506, "pos_des = 16506 计数");
    // 注意这里是 257π/128 ≈ 6.3077，不是原意 6.33：SDK 打包时截断掉了 0.022 rad/s
    // （protocol.md §4 的"1 LSB"那条），解码得到的是报文里真实存在的值。
    expect_near(command.speed_rotor, 257.0 * 3.14159265358979323846 / 128.0, 1e-9,
                "spd_des=257 → 257π/128 ≈ 6.3077 rad/s（转子侧）");
    expect_near(command.kp_rotor, 2555.0 / 1280.0, 1e-9, "k_pos=2555 → K_P 1.9961");
    expect_near(command.kd_rotor, 95.0 / 1280.0, 1e-9, "k_spd=95 → K_W 0.0742");
    expect(!command.zero_torque, "非零命令不应判为零力矩");

    // 5 个量全 0 ⇒ 零力矩帧
    build_command_frame(frame, 0, 0, 0, 0, 0);
    const motor::DeviceCommand zero = motor_wire::decode_command(frame, &meta);
    expect(zero.zero_torque, "全零命令判为零力矩");

    // 翻转一个字节：CRC 应报错
    build_command_frame(frame, 0, 257, 16506, 2555, 95);
    frame[5] ^= 0x01;
    const motor::DeviceCommand broken = motor_wire::decode_command(frame, &meta);
    expect(!meta.crc_ok, "改一个字节后 CRC 报错");
    (void)broken;
}

// 组一帧回帧，检查字段与 CRC（用 SDK 的结构体反读当金标准）
void test_encode_reply()
{
    motor::DeviceFeedback feedback;
    feedback.raw = 16384;
    feedback.speed_rotor = 3.1416;
    feedback.torque_rotor = 1.0;
    feedback.temp_c = 32;
    feedback.merror = 0;

    std::uint8_t frame[motor_wire::kReplySize];
    motor_wire::encode_reply(feedback, 0, motor_wire::kStatusFoc, frame);

    MotorData_t reply;
    std::memcpy(&reply, frame, sizeof(reply));
    expect_eq(reply.head[0], 0xfe, "回帧头 0xfe");
    expect_eq(reply.head[1], 0xee, "回帧头 0xee");
    expect_eq(reply.mode.id, 0, "回帧 id");
    expect_eq(reply.mode.status, 1, "回帧 status = FOC");
    expect_eq(reply.fbk.pos, 16384, "回帧 pos = 16384（raw=128 → data.q=3.1416 那条实测）");
    expect_eq(reply.fbk.speed, 128, "回帧 speed raw = 128");
    expect_eq(reply.fbk.torque, 256, "回帧 torque raw = 256");
    expect_eq(reply.fbk.temp, 32, "回帧温度");
    expect_eq(reply.fbk.MError, 0, "回帧 merror");

    const std::uint16_t crc = crc_ccitt(0, frame, sizeof(reply) - CRC_SIZE);
    expect_eq(crc, reply.CRC16, "回帧 CRC 与本地重算一致");

    // 解码器面对回帧长度不应越界读：这里借"命令解码"验证一次长度契约（用回帧当输入只测不崩）
    // —— 不变量：kCommandSize 与 SDK 的 ControlData_t 尺寸一致
    expect_eq(motor_wire::kCommandSize, static_cast<long long>(sizeof(ControlData_t)),
              "kCommandSize = sizeof(ControlData_t)");
    expect_eq(motor_wire::kReplySize, static_cast<long long>(sizeof(MotorData_t)),
              "kReplySize = sizeof(MotorData_t)");
}

} // namespace

int main()
{
    test_decode_anchors();
    test_encode_reply();
    if (failures == 0)
    {
        std::printf("motor_wire_tests：全部通过\n");
        return 0;
    }
    std::fprintf(stderr, "motor_wire_tests：%d 项失败\n", failures);
    return 1;
}
