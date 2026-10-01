/**
 * @file session.cpp
 * @brief Session 的实现：命令生效、插值推进、反馈处理（握手 / 保护）与设备帧组装。
 */

#include "motor/session.hpp"

#include "motor/format.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>

namespace motor
{
namespace
{

std::string format_seconds(double seconds)
{
    char buffer[32];
    std::snprintf(buffer, sizeof(buffer), "%.2f", seconds);
    return std::string(buffer);
}

} // namespace

Session::Session(const SessionConfig& config) : config_(config), ledger_(config.initial_offset)
{
    kp_rotor_ = config.kp_out / (kGearRatio * kGearRatio);
    kd_rotor_ = config.kd_out / (kGearRatio * kGearRatio);
    tol_counts_ = std::max<Counts>(1, output_deg_to_counts(config.tol_deg));
    planner_.set_limits(config.vmax_deg_per_s, config.amax_deg_per_s2);
}

void Session::set_fault(const std::string& reason)
{
    link_ = LinkState::kFault;
    enabled_ = false;
    fault_reason_ = reason;
}

void Session::step(double dt)
{
    if (link_ != LinkState::kOnline || !enabled_)
    {
        if (have_feedback_)
        {
            planner_.track(q_now()); // 自由 / 未对齐：插值器贴着实际位置
        }
        device_command_ = DeviceCommand{}; // zero_torque = true
        return;
    }
    const double q_cmd = planner_.step(dt);
    DeviceCommand command;
    command.zero_torque = false;
    command.pos_counts = ledger_.q_to_board(std::llround(q_cmd));
    command.speed_rotor =
        planner_.velocity_counts_per_s() * (2.0 * kSdkPi / static_cast<double>(kCountsPerTurn));
    command.torque_rotor = 0.0;
    command.kp_rotor = kp_rotor_;
    command.kd_rotor = kd_rotor_;
    device_command_ = command;
}

void Session::on_feedback(const DeviceFeedback* feedback, double now_s)
{
    ++frames_;
    if (feedback == nullptr)
    {
        ++timeouts_;
        ++miss_;
        if (link_ == LinkState::kOnline && miss_ >= config_.offline_frames)
        {
            set_fault("连续 " + std::to_string(config_.offline_frames) + " 帧无回复（失联）");
        }
        return;
    }
    ++ok_frames_;
    miss_ = 0;

    if (link_ == LinkState::kHandshake)
    {
        ledger_.anchor(0, now_s); // 接受当前位置：turn_base = 0
        last_raw_ = feedback->raw;
        have_feedback_ = true;
        target_ = ledger_.raw_to_q(last_raw_);
        planner_.snap_to(target_);
        enabled_ = true;
        link_ = LinkState::kOnline;
    }
    else
    {
        last_raw_ = feedback->raw;
        have_feedback_ = true;
    }

    last_temp_c_ = feedback->temp_c;
    last_merror_ = feedback->merror;
    temp_peak_c_ = std::max(temp_peak_c_, feedback->temp_c);
    last_torque_nm_ = feedback->torque_rotor * kGearRatio;
    torque_peak_nm_ = std::max(torque_peak_nm_, std::fabs(last_torque_nm_));

    if (link_ == LinkState::kFault)
    {
        return;
    }
    if (feedback->merror != 0)
    {
        set_fault("电机报错 merror=" + std::to_string(feedback->merror));
        return;
    }
    if (feedback->temp_c >= config_.temp_limit_c)
    {
        set_fault("温度 " + std::to_string(feedback->temp_c) + " °C 达到上限");
        return;
    }
    if (enabled_ && std::fabs(last_torque_nm_) >= config_.tau_out_limit_nm)
    {
        if (fault_since_over_s_ < 0.0)
        {
            fault_since_over_s_ = now_s;
        }
        else if (now_s - fault_since_over_s_ >= config_.stall_s)
        {
            set_fault("力矩持续 " + format_seconds(now_s - fault_since_over_s_) + " s 超过 " +
                      format_seconds(config_.tau_out_limit_nm) + " N·m（判定卡住）");
        }
    }
    else
    {
        fault_since_over_s_ = -1.0;
    }
}

void Session::shift_offset(Counts delta, double now_s)
{
    if (delta == 0)
    {
        return;
    }
    ledger_.shift_offset(delta, now_s);
    if (enabled_)
    {
        // 物理目标不动：目标与插值位置同步平移（I3）
        target_ += delta;
        planner_.relocate(delta);
    }
    if (have_mark_)
    {
        mark_q_ += delta; // 标记点是物理点：offset 一动，它的 q 读数跟着挪
    }
}

ApplyResult Session::set_target_from_here(Counts target, double now_s, const std::string& what)
{
    (void)now_s;
    if (!have_feedback_)
    {
        return {false, "还没收到板子回复，先别给目标"};
    }
    target_ = target;
    planner_.set_target(target_);
    enabled_ = true;
    const Counts distance = target_ - q_now();
    const double vmax_cps = static_cast<double>(output_deg_to_counts(config_.vmax_deg_per_s));
    const double seconds = std::fabs(static_cast<double>(distance)) / std::max(1.0, vmax_cps);
    return {true, what + " " + format_output_angle(target_) + "（现在 " +
                      format_output_angle(q_now()) + "，要转 " + format_output_angle(distance) +
                      "，按 vmax 直线约 " + format_seconds(seconds) + " s）"};
}

ApplyResult Session::apply(const Command& command, double now_s)
{
    switch (command.kind)
    {
    case CommandKind::kWait:
        gate_until_s_ = now_s + command.wait_s;
        return {true, "等 " + format_seconds(command.wait_s) + " s"};
    case CommandKind::kQuit:
        quit_ = true;
        return {true, "先卸力再退出"};
    case CommandKind::kFree:
        enabled_ = false;
        return {true, "零力矩（电机自由，可手转）"};
    case CommandKind::kHold:
    {
        if (!have_feedback_)
        {
            return {false, "还没收到板子回复，不能保持位置"};
        }
        target_ = q_now();
        planner_.snap_to(target_);
        enabled_ = true;
        return {true, "位置保持，目标 = 当前位置 " + format_output_angle(target_)};
    }
    case CommandKind::kMove:
        return set_target_from_here(command.value, now_s, "目标");
    case CommandKind::kJog:
    {
        if (!have_feedback_)
        {
            return {false, "还没收到板子回复，不能给目标"};
        }
        return set_target_from_here(q_now() + command.value, now_s, "目标（相对）");
    }
    case CommandKind::kZeroMove:
    case CommandKind::kOffsetSet:
    {
        const Counts before = ledger_.offset();
        const Counts delta =
            (command.kind == CommandKind::kZeroMove) ? -command.value : command.value - before;
        shift_offset(delta, now_s);
        std::string message;
        if (command.kind == CommandKind::kZeroMove)
        {
            message = "零点沿正方向移动 " + format_output_angle(command.value);
        }
        else
        {
            message = "offset 变量设为 " + format_output_angle(ledger_.offset());
        }
        message += "：offset " + std::to_string(before) + " → " +
                   std::to_string(ledger_.offset()) + " 计数（" +
                   format_output_angle(ledger_.offset()) + "）；电机不动、物理目标不变";
        if (have_feedback_)
        {
            message += "；离零点边界 " +
                       format_output_angle(
                           distance_to_zone_edge(ledger_.raw_to_pos(last_raw_)));
        }
        if (have_mark_)
        {
            message += "；标记点读数 " + format_output_angle(mark_q_);
        }
        return {true, message};
    }
    case CommandKind::kMark:
    {
        if (!have_feedback_)
        {
            return {false, "还没收到板子回复，不能打标记"};
        }
        mark_q_ = q_now();
        have_mark_ = true;
        const Counts pos = ledger_.raw_to_pos(last_raw_);
        return {true, "标记点 q " + format_output_angle(mark_q_) + "（pos " +
                          format_output_angle(pos) + "）；离零点边界 " +
                          format_output_angle(distance_to_zone_edge(pos))};
    }
    case CommandKind::kMarkGoto:
        if (!have_mark_)
        {
            return {false, "还没打过标记（先 mark）"};
        }
        return set_target_from_here(mark_q_, now_s, "目标（标记点）");
    default:
        return {false, "这条命令不该走到执行阶段"};
    }
}

bool Session::arrived() const
{
    if (!have_feedback_ || !enabled_)
    {
        return false;
    }
    return std::llabs(target_ - q_now()) <= tol_counts_;
}

} // namespace motor
