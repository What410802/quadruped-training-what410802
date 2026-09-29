/**
 * @file motor_bus.cpp
 * @brief MotorBus 的实现：组 `MotorCmd`（转子侧）→ sendRecv → 把回帧读成整数 tick。
 */
#include "motor_bench/motor_bus.hpp"

namespace motor_bench
{

MotorBus::MotorBus(const std::string& port, int id, int baud) : serial_(port, 16, baud), id_(id)
{
    cmd_.motorType = MotorType::GO_M8010_6;
    data_.motorType = MotorType::GO_M8010_6;
    cmd_.mode = static_cast<unsigned short>(queryMotorMode(MotorType::GO_M8010_6, MotorMode::FOC));
    cmd_.id = static_cast<unsigned short>(id);
    cmd_.kp = 0.0f;
    cmd_.kd = 0.0f;
    cmd_.q = 0.0f;
    cmd_.dq = 0.0f;
    cmd_.tau = 0.0f;
}

bool MotorBus::Send(const RotorCommand& c, ticks::Feedback* fb)
{
    cmd_.q = ticks::CmdQRotor(c.q_ticks);
    cmd_.dq = static_cast<float>(c.dq);
    cmd_.tau = static_cast<float>(c.tau);
    cmd_.kp = static_cast<float>(c.kp);
    cmd_.kd = static_cast<float>(c.kd);

    ++frames_;
    const bool ok = serial_.sendRecv(&cmd_, &data_);
    if (!ok)
    {
        ++timeouts_;
        ++timeout_streak_;
        return false;
    }
    ++ok_frames_;
    timeout_streak_ = 0;
    if (fb != nullptr)
    {
        ticks::ReadFeedback(data_, fb, &warned_precision_);
    }
    return true;
}

bool MotorBus::SendZero(ticks::Feedback* fb)
{
    RotorCommand zero{};
    return Send(zero, fb);
}

} // namespace motor_bench
