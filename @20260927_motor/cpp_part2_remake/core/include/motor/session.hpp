/**
 * @file session.hpp
 * @brief 会话状态机：把"命令 + 反馈"变成"设备帧"，管理握手、出力开关、保护与账本事件。
 *
 * 链路状态（M1：在线简版）：
 *   Handshake ──首帧有效──▶ Online ──连续 N 帧无回复──▶ Fault（M1 直接报警退出）
 * 未对齐（Handshake）或未使能（free）或故障时，一律只发零力矩。
 */

#pragma once

#include "motor/command.hpp"
#include "motor/ledger.hpp"
#include "motor/trajectory.hpp"
#include "motor/transport.hpp"

#include <string>

namespace motor
{

/** 会话配置（对外单位：输出端度、N·m、°C、帧） */
struct SessionConfig
{
    double vmax_deg_per_s = 90.0;
    double amax_deg_per_s2 = 180.0;
    double tol_deg = 1.0;
    double kp_out = 80.0; // 输出端刚度（下发时 ÷N²）
    double kd_out = 3.0;  // 输出端阻尼（下发时 ÷N²）
    double tau_out_limit_nm = 1.5;
    double stall_s = 1.0;
    int temp_limit_c = 80;
    int offline_frames = 40;
    Counts initial_offset = 0;
};

enum class LinkState
{
    kHandshake, // 等待第一帧：只发零力矩
    kOnline,    // 正常出力
    kOffline,   // 预留（M3：失联后等待恢复；M1 不用）
    kFault,     // 保护触发：只发零力矩，准备退出
};

/** 一条命令的执行结果：给操作者看的文本（可空） */
struct ApplyResult
{
    bool ok = true;
    std::string message;
};

class Session
{
  public:
    explicit Session(const SessionConfig& config);

    // 命令：wait 由 can_apply() 门控；其余立即生效
    ApplyResult apply(const Command& command, double now_s);
    bool can_apply(double now_s) const { return now_s >= gate_until_s_; }

    // 周期：推进规划器并产出本帧设备命令
    void step(double dt);
    // 反馈：nullptr = 本帧没有回复
    void on_feedback(const DeviceFeedback* feedback, double now_s);

    const DeviceCommand& device_command() const { return device_command_; }

    LinkState link_state() const { return link_; }
    bool enabled() const { return enabled_; }
    bool quit_requested() const { return quit_; }
    bool faulted() const { return link_ == LinkState::kFault; }
    const std::string& fault_reason() const { return fault_reason_; }

    const Ledger& ledger() const { return ledger_; }
    RawCounts last_raw() const { return last_raw_; }
    bool have_feedback() const { return have_feedback_; }
    Counts q_now() const { return ledger_.raw_to_q(last_raw_); }
    Counts target() const { return target_; }
    bool arrived() const;
    bool have_mark() const { return have_mark_; }
    Counts mark_q() const { return mark_q_; }

    int frames() const { return frames_; }
    int ok_frames() const { return ok_frames_; }
    int timeouts() const { return timeouts_; }
    double torque_peak_nm() const { return torque_peak_nm_; }
    int temp_peak_c() const { return temp_peak_c_; }
    double last_torque_nm() const { return last_torque_nm_; }
    int last_temp_c() const { return last_temp_c_; }
    unsigned last_merror() const { return last_merror_; }

  private:
    void set_fault(const std::string& reason);
    void shift_offset(Counts delta, double now_s);
    ApplyResult set_target_from_here(Counts target, double now_s, const std::string& what);

    SessionConfig config_;
    Ledger ledger_;
    TrapezoidPlanner planner_;
    double kp_rotor_ = 0.0;
    double kd_rotor_ = 0.0;
    Counts tol_counts_ = 1;

    LinkState link_ = LinkState::kHandshake;
    DeviceCommand device_command_{};
    bool enabled_ = false;
    bool quit_ = false;
    bool have_feedback_ = false;
    RawCounts last_raw_ = 0;
    Counts target_ = 0;
    bool have_mark_ = false;
    Counts mark_q_ = 0;
    double gate_until_s_ = 0.0; // wait 语句的门控
    double fault_since_over_s_ = -1.0;

    std::string fault_reason_;
    int frames_ = 0;
    int ok_frames_ = 0;
    int timeouts_ = 0;
    int miss_ = 0;
    double torque_peak_nm_ = 0.0;
    int temp_peak_c_ = -128;
    double last_torque_nm_ = 0.0;
    int last_temp_c_ = 0;
    unsigned last_merror_ = 0;
};

} // namespace motor
