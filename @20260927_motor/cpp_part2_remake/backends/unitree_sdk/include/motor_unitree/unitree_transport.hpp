/**
 * @file unitree_transport.hpp
 * @brief 实机传输：官方宇树 SDK 的薄封装（SerialPort + MotorCmd / MotorData ↔ 设备帧）。
 *
 * SDK 的头文件不出现在本头里（PIMPL）：谁 include 本文件都不会被拖进 SDK 的包含路径。
 */

#pragma once

#include "motor/transport.hpp"

#include <memory>
#include <string>

namespace motor_unitree
{

class UnitreeTransport final : public motor::Transport
{
  public:
    /** 打开串口；失败时返回 nullptr 并把原因写进 error（捕获 SDK 的异常） */
    static std::unique_ptr<UnitreeTransport> open(const std::string& port, int id, int baud,
                                                  std::string* error);

    ~UnitreeTransport() override;

    bool send(const motor::DeviceCommand& command, motor::DeviceFeedback* feedback) override;
    const char* name() const override;

  private:
    UnitreeTransport(const std::string& port, int id, int baud);

    struct Impl;
    std::unique_ptr<Impl> impl_;
};

} // namespace motor_unitree
