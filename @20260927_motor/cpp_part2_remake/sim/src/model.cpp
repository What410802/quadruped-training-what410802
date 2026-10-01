/**
 * @file model.cpp
 * @brief MotorModel 的实现：一条 MIT 公式 + 库仑摩擦 + 一阶惯量积分（与旧版假电机同一套模型）。
 */

#include "motor_sim/model.hpp"

#include <algorithm>
#include <cmath>

namespace motor_sim
{
namespace
{

constexpr double kPi = 3.14159265358979323846;
constexpr double kTwoPi = 2.0 * kPi;

// 位置：板子读数空间是"转子侧计数"（q15 圈）；动力学在转子弧度里做。
// 这里的计数↔弧度只用真 π：π′ 只影响 SDK 的 float 接口（见 core/protocol.hpp 的说明）。
double counts_to_rad(motor::Counts counts)
{
    return static_cast<double>(counts) * kTwoPi / static_cast<double>(motor::kCountsPerTurn);
}

motor::Counts rad_to_counts(double rad)
{
    return std::llround(rad / kTwoPi * static_cast<double>(motor::kCountsPerTurn));
}

double wrap_deg(double deg)
{
    double wrapped = std::fmod(deg + 180.0, 360.0);
    if (wrapped < 0.0)
    {
        wrapped += 360.0;
    }
    return wrapped - 180.0;
}

} // namespace

MotorModel::MotorModel(const ModelParams& params) : params_(params) {}

void MotorModel::step(const motor::DeviceCommand& command, double dt)
{
    if (dt <= 0.0)
    {
        return;
    }
    ++frames_;

    // 位置环量的是"板子自己上报的角度"；本模型的上报就是真实位置（里程计）。
    const double position_rad = counts_to_rad(reported_raw());
    double tau_cmd = 0.0;
    if (!command.zero_torque)
    {
        const double p_des = counts_to_rad(command.pos_counts);
        tau_cmd = command.torque_rotor + command.kp_rotor * (p_des - position_rad) +
                  command.kd_rotor * (command.speed_rotor - speed_rad_s_);
    }
    tau_cmd = std::clamp(tau_cmd, -params_.tau_max_rotor_nm, params_.tau_max_rotor_nm);
    tau_cmd += hand_torque_rotor_nm(); // 人手给的力矩不受电机限幅

    const double friction = params_.tau_friction_nm;
    if (std::fabs(speed_rad_s_) > 1e-3)
    {
        const double tau_net = tau_cmd - friction * (speed_rad_s_ > 0.0 ? 1.0 : -1.0);
        const double speed_new = speed_rad_s_ + tau_net * dt / params_.inertia_kg_m2;
        if ((speed_rad_s_ > 0.0 && speed_new < 0.0) || (speed_rad_s_ < 0.0 && speed_new > 0.0))
        {
            speed_rad_s_ = 0.0; // 摩擦在这一拍里刚好把速度吃光（粘滞）
            torque_rotor_nm_ = 0.0;
        }
        else
        {
            speed_rad_s_ = speed_new;
            torque_rotor_nm_ = tau_net;
        }
    }
    else if (std::fabs(tau_cmd) > friction)
    {
        torque_rotor_nm_ = tau_cmd - friction * (tau_cmd > 0.0 ? 1.0 : -1.0);
        speed_rad_s_ += torque_rotor_nm_ * dt / params_.inertia_kg_m2;
    }
    else
    {
        torque_rotor_nm_ = 0.0; // 静摩擦：这么小的力矩推不动
        speed_rad_s_ = 0.0;
    }
    // 最高转速（电压 / 反电动势）限制：到顶就不再加速，多余的力矩被"吃掉"。
    // 没有它，自由轴上的恒力矩（实验台的 torque 命令）会一直线性加速到不现实的量级。
    const double limit = params_.max_speed_rotor_rad_s;
    if (speed_rad_s_ > limit)
    {
        speed_rad_s_ = limit;
    }
    else if (speed_rad_s_ < -limit)
    {
        speed_rad_s_ = -limit;
    }
    position_rad_ += speed_rad_s_ * dt;

    temp_c_ += params_.heat_rate * dt * std::fabs(torque_rotor_nm_) / params_.tau_max_rotor_nm;
    if (temp_c_ > 89.0)
    {
        merror_ = 1; // 90 °C 触发保护（报文的 merror 位）
    }
}

double MotorModel::hand_torque_rotor_nm() const
{
    if (interaction_ == Interaction::kTorque)
    {
        return torque_out_nm_ / motor::kGearRatio;
    }
    if (interaction_ != Interaction::kHold)
    {
        return 0.0;
    }
    const double target_rad = hold_target_out_deg_ * (kPi / 180.0) * motor::kGearRatio;
    const double tau = params_.hand_stiffness_rotor * (target_rad - position_rad_) -
                       params_.hand_damping_rotor * speed_rad_s_;
    return std::clamp(tau, -params_.hand_max_rotor_nm, params_.hand_max_rotor_nm);
}

motor::DeviceFeedback MotorModel::feedback() const
{
    motor::DeviceFeedback out;
    out.raw = reported_raw();
    out.speed_rotor = speed_rad_s_;
    out.torque_rotor = torque_rotor_nm_;
    out.temp_c = static_cast<int>(temp_c_);
    out.merror = merror_;
    out.status_bits = 0;
    return out;
}

void MotorModel::apply_torque_out(double torque_out_nm)
{
    interaction_ = Interaction::kTorque;
    torque_out_nm_ =
        std::clamp(torque_out_nm, -params_.torque_out_max_nm, params_.torque_out_max_nm);
}

void MotorModel::hold_output_deg(double output_deg)
{
    interaction_ = Interaction::kHold;
    hold_target_out_deg_ = output_deg;
}

void MotorModel::release()
{
    interaction_ = Interaction::kNone;
    torque_out_nm_ = 0.0;
}

void MotorModel::draw_line()
{
    line_output_deg_ = output_deg();
    has_line_ = true;
}

void MotorModel::clear_line()
{
    has_line_ = false;
}

double MotorModel::line_wrapped_deg() const
{
    return wrap_deg(output_deg() - line_output_deg_);
}

double MotorModel::line_cumulative_deg() const
{
    return output_deg() - line_output_deg_;
}

motor::Counts MotorModel::true_counts() const
{
    return rad_to_counts(position_rad_);
}

motor::RawCounts MotorModel::reported_raw() const
{
    return static_cast<motor::RawCounts>(true_counts());
}

double MotorModel::output_deg() const
{
    return motor::counts_to_output_deg(true_counts());
}

double MotorModel::output_speed_deg_s() const
{
    return speed_rad_s_ / motor::kGearRatio * 180.0 / kPi;
}

} // namespace motor_sim
