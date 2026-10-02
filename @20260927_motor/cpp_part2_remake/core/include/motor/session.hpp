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

#include <optional>
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

    // ---- M4：启动检查与自动对齐（§2.6 / §3.4 / D20）----
    std::optional<Counts> pose_ref_raw;   // 参考读数（--pose-ref）；缺省 = 不做启动检查
    Counts pose_warn_counts = 5461;       // T_w：|r| 超过它就打印提示（C/6 = 9.4737°）
    bool auto_fix = true;                 // 护栏通过时是否自动对齐（--no-auto-fix 关）
    double fix_window_deg = 20.0;         // W：自动路径额外要求 |r| ≤ W
    int max_fixes = 3;                    // fix（人工 + 自动）的次数上限
    double max_move_deg = 360.0;          // P6：单次 move / jog 的转角上限
    Counts jump_tol_counts = 2048;        // 运行中跳变判据的残差容差（C/16 ≈ 3.5° 输出端）
};

/** check / 启动检查的结果：唯一分解 d = kC + r，外加给人看的报告 */
struct CheckReport
{
    Counts d = 0;          // 差（计数，与 offset 无关）
    Counts k = 0;          // 整格数（= round(d/C)）
    Counts r = 0;          // 残差（|r| ≤ C/2）
    bool branch_like = false; // |r| 落在 S（1/19 圈）附近：可能是分支漂移
    bool ambiguous = false;   // 恰在半格：二义点
    bool warn_band = false;   // T_w < |r| < H：打印提示的区间
    std::string text;      // 完整报告（多行；app 直接打印）
};

enum class LinkState
{
    kHandshake, // 等待第一帧 / 等待人工确认：只发零力矩
    kOnline,    // 正常出力
    kOffline,   // 预留（M3：失联后等待恢复；验收不做）
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

    /** gate（D5/D20）：停在 Handshake 等人工确认；任一显式命令即解除 */
    bool awaiting_confirm() const { return link_ == LinkState::kHandshake && have_feedback_; }

    /** 启动检查的报告（没有 --pose-ref 或还没收到首帧时为空） */
    const std::string& startup_report() const { return startup_report_; }

    const Ledger& ledger() const { return ledger_; }
    RawCounts last_raw() const { return last_raw_; }
    bool have_feedback() const { return have_feedback_; }
    Counts q_now() const { return ledger_.raw_to_q(last_raw_); }
    Counts target() const { return target_; }
    bool arrived() const;
    bool have_mark() const { return have_mark_; }
    Counts mark_q() const { return mark_q_; }

    /** check / 启动检查：比较两个同层读数，给出唯一分解与报告（纯函数式，可单测） */
    CheckReport check_report(Counts current_counts, Counts ref_counts) const;
    /** 自动对齐的护栏（D20）：三条件同时成立才允许"自动"路径 */
    bool auto_fix_ok(RawCounts raw0, Counts k, Counts r) const;

    int frames() const { return frames_; }
    int ok_frames() const { return ok_frames_; }
    int timeouts() const { return timeouts_; }
    int fixes() const { return fixes_used_; }
    double torque_peak_nm() const { return torque_peak_nm_; }
    int temp_peak_c() const { return temp_peak_c_; }
    double last_torque_nm() const { return last_torque_nm_; }
    int last_temp_c() const { return last_temp_c_; }
    unsigned last_merror() const { return last_merror_; }

  private:
    void set_fault(const std::string& reason);
    void shift_offset(Counts delta, double now_s);
    /** 区间重对齐（fix / 启动自动对齐 / 运行中跳变）：offset -= kC，记 kAlignFix */
    void align_offset(Counts k, double now_s);
    /** 改 offset 之后同步目标 / 插值 / 标记（I3） */
    void sync_after_offset(Counts delta);
    /** 区间重对齐（fix / 启动自动对齐）：前提由调用方打印 */
    ApplyResult apply_fix(Counts k, double now_s, bool automatic);
    void confirm_ledger();
    ApplyResult set_target_from_here(Counts target, double now_s, const std::string& what);
    Counts resolve_reference(const Command& command, std::string* why) const;

    SessionConfig config_;
    Ledger ledger_;
    TrapezoidPlanner planner_;
    double kp_rotor_ = 0.0;
    double kd_rotor_ = 0.0;
    Counts tol_counts_ = 1;
    Counts max_move_counts_ = 0;
    Counts fix_window_counts_ = 0;

    LinkState link_ = LinkState::kHandshake;
    DeviceCommand device_command_{};
    bool enabled_ = false;
    bool quit_ = false;
    bool have_feedback_ = false;
    RawCounts first_raw_ = 0; // 会话首帧的 raw（"刚上电"的侧面证据）
    RawCounts last_raw_ = 0;
    Counts target_ = 0;
    bool have_mark_ = false;
    Counts mark_q_ = 0;
    double gate_until_s_ = 0.0; // wait 语句的门控
    double fault_since_over_s_ = -1.0;
    int fixes_used_ = 0;
    std::string startup_report_;
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
