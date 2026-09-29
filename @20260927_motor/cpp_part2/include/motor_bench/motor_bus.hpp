/**
 * @file motor_bus.hpp
 * @brief 串口与报文这一层的封装：打开端口、按转子侧参数发一帧、把反馈读成整数 tick。
 *
 * 这一层只做"怎么收发"，不做控制逻辑；位置一律是 `ticks::Feedback`（整数），
 * 命令一律用转子侧的物理量（位置 tick、速度 rad/s、增益 N·m 量纲），由调用方换算。
 */
#pragma once

#include "motor_bench/ticks.hpp"
#include "serialPort/SerialPort.h"
#include "unitreeMotor/unitreeMotor.h"

#include <cstdint>
#include <string>

namespace motor_bench
{

/** 一帧命令（转子侧） */
struct RotorCommand
{
    int64_t q_ticks = 0; // 目标位置（转子 tick）
    double dq = 0.0;     // 目标速度（转子 rad/s）
    double tau = 0.0;    // 前馈力矩（转子 N·m）
    double kp = 0.0;     // 刚度（转子侧）
    double kd = 0.0;     // 阻尼（转子侧）
};

class MotorBus
{
  public:
    /** 打开串口；失败时抛 SDK 的异常，由调用方捕获 */
    MotorBus(const std::string& port, int id, int baud = 4000000);

    /** 发一帧命令并读反馈；返回 false = 这一帧没收到回复 */
    bool Send(const RotorCommand& cmd, ticks::Feedback* fb);

    /** 五个命令量全 0 的"零力矩"帧 */
    bool SendZero(ticks::Feedback* fb = nullptr);

    int frames() const { return frames_; }
    int ok_frames() const { return ok_frames_; }
    int timeouts() const { return timeouts_; }
    int timeout_streak() const { return timeout_streak_; }

  private:
    SerialPort serial_;
    MotorCmd cmd_{};
    MotorData data_{};
    int id_ = 0;
    bool warned_precision_ = false;
    int frames_ = 0;
    int ok_frames_ = 0;
    int timeouts_ = 0;
    int timeout_streak_ = 0;
};

} // namespace motor_bench
