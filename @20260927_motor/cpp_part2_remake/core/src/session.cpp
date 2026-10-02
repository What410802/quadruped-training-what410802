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

std::string format_counts(Counts counts)
{
    char buffer[32];
    std::snprintf(buffer, sizeof(buffer), "%+lld 计数", static_cast<long long>(counts));
    return std::string(buffer);
}

std::string format_signed(Counts value)
{
    char buffer[32];
    std::snprintf(buffer, sizeof(buffer), "%+lld", static_cast<long long>(value));
    return std::string(buffer);
}

} // namespace

Session::Session(const SessionConfig& config) : config_(config), ledger_(config.initial_offset)
{
    kp_rotor_ = config.kp_out / (kGearRatio * kGearRatio);
    kd_rotor_ = config.kd_out / (kGearRatio * kGearRatio);
    tol_counts_ = std::max<Counts>(1, output_deg_to_counts(config.tol_deg));
    max_move_counts_ = std::max<Counts>(0, output_deg_to_counts(config.max_move_deg));
    fix_window_counts_ = std::max<Counts>(0, output_deg_to_counts(config.fix_window_deg));
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
        if (!have_feedback_)
        {
            // 上电 / 程序接手（D19/D20）：锚定 → 启动检查 → 护栏通过就自动对齐
            ledger_.anchor(0, now_s); // 接受当前位置：turn_base = 0（事件：上电锚定）
            first_raw_ = feedback->raw;
            last_raw_ = feedback->raw;
            have_feedback_ = true;

            bool gated = false;
            if (config_.pose_ref_raw.has_value())
            {
                const CheckReport report = check_report(feedback->raw, *config_.pose_ref_raw);
                startup_report_ = report.text;
                if (report.k != 0)
                {
                    std::string why;
                    if (!config_.auto_fix)
                    {
                        why += "--no-auto-fix；";
                    }
                    if (feedback->raw < 0 || feedback->raw >= kCountsPerTurn)
                    {
                        why += "首帧 raw 不在 [0, C)（更像'电机没断电、只是程序重启'）；";
                    }
                    if (std::llabs(report.k) > 1)
                    {
                        why += "|k| ≥ 2（位移超半格，或重启期间累计了多圈）；";
                    }
                    if (std::llabs(report.r) > fix_window_counts_)
                    {
                        why += "|r| > W = " + format_output_angle(fix_window_counts_) +
                               "（位移太大）；";
                    }
                    if (auto_fix_ok(feedback->raw, report.k, report.r))
                    {
                        const ApplyResult fixed = apply_fix(report.k, now_s, true);
                        startup_report_ += "\n  " + fixed.message;
                        gated = !fixed.ok;
                    }
                    else
                    {
                        gated = true;
                        startup_report_ += "\n  不自动对齐：" + why +
                                           "先 fix（或确认位置后 hold / move / jog），"
                                           "否则可能偏一整格 56.8421°";
                    }
                }
            }

            // 无论是否 gate，目标先贴到当前位置（gate 时只是不出力，显示才自洽）
            target_ = q_now();
            planner_.snap_to(target_);
            if (gated)
            {
                // 停在 Handshake：只发零力矩，等任一显式命令确认（D5 / D20）。
                // 不 return：下面的保护检查（merror / 温度）在首帧同样要跑。
            }
            else
            {
                enabled_ = true;
                link_ = LinkState::kOnline;
            }
        }
        else
        {
            last_raw_ = feedback->raw; // 已经锚定过、仍在等人工确认：只更新读数
            have_feedback_ = true;
        }
    }
    else
    {
        if (link_ == LinkState::kOnline)
        {
            // 运行中换基准（兜底）：本帧读数正好跳了 k 个整格 ⇒ 只补账本、物理目标不动
            const Counts delta = static_cast<Counts>(feedback->raw) - static_cast<Counts>(last_raw_);
            const Counts k = zones_of_delta(delta);
            const Counts residual = delta - k * kCountsPerTurn;
            if (k != 0 && std::llabs(residual) <= config_.jump_tol_counts)
            {
                align_offset(k, now_s); // 运行中换基准（兜底）：只补账本、物理目标不动
            }
        }
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
    ledger_.shift_offset(delta, now_s); // 标定动作：记 kOffsetShift
    sync_after_offset(delta);
}

void Session::align_offset(Counts k, double now_s)
{
    if (k == 0)
    {
        return;
    }
    ledger_.align_fix(k, now_s); // 重对齐：offset -= k×C，记 kAlignFix
    sync_after_offset(-k * kCountsPerTurn);
}

void Session::sync_after_offset(Counts delta)
{
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

ApplyResult Session::apply_fix(Counts k, double now_s, bool automatic)
{
    if (k == 0)
    {
        return {true, "k = 0：无需修正"};
    }
    if (fixes_used_ >= config_.max_fixes)
    {
        return {false, "已达 max-fixes = " + std::to_string(config_.max_fixes) +
                           " 次，拒绝再修正（请人工检查）"};
    }
    const Counts before = ledger_.offset();
    align_offset(k, now_s);
    ++fixes_used_;
    const std::string head = automatic ? "自动对齐" : "对齐";
    return {true, head + "：k = " + format_signed(k) + " 格 ⇒ offset " +
                      std::to_string(before) + " → " + std::to_string(ledger_.offset()) +
                      " 计数；电机不动、物理目标不变"};
}

void Session::confirm_ledger()
{
    if (link_ != LinkState::kHandshake || !have_feedback_)
    {
        return; // 已经 Online（或还没收到帧）：无事可做
    }
    target_ = q_now();
    planner_.snap_to(target_);
    enabled_ = true;
    link_ = LinkState::kOnline;
}

CheckReport Session::check_report(Counts current_counts, Counts ref_counts) const
{
    CheckReport report;
    report.d = current_counts - ref_counts;
    report.k = zones_of_delta(report.d);
    report.r = report.d - report.k * kCountsPerTurn;
    const Counts magn = std::llabs(report.r);
    report.ambiguous = magn >= kHalfZoneCounts - 1;
    report.warn_band = magn > config_.pose_warn_counts && !report.ambiguous;
    report.branch_like = std::llabs(magn - kBranchStepCounts) <= 1000;

    std::string text;
    text += "检查（只报告）：参考 " + format_counts(ref_counts) + "（" +
            format_output_angle(ref_counts) + "）；当前 " + format_counts(current_counts) + "（" +
            format_output_angle(current_counts) + "）\n";
    text += "  分解：d = " + format_signed(report.d) + " = k = " + format_signed(report.k) +
            " 格 × 32768 + r = " + format_counts(report.r) + "（" + format_output_angle(report.r) +
            "）\n";
    text += "  两种解释都成立、读数无法区分：① 断电重上电过 ⇒ k 是板子基准挪动的格数；"
            "② 只是程序重启（电机没断电）⇒ k 是自参考以来累计的整圈数，读数本来就对、不该动账\n";
    text += "  侧面证据：本会话首帧 raw " + format_counts(first_raw_) + " " +
            (first_raw_ >= 0 && first_raw_ < kCountsPerTurn ? "落在" : "不在") +
            " [0, 32768)（断电重上电后必然落在里面；反之不一定）\n";
    if (report.ambiguous)
    {
        text += "  ⚠ 恰在半格：二义点，请改姿态后重测";
    }
    else if (report.warn_band)
    {
        text += "  提示：与标定姿态差 " + format_output_angle(report.r) +
                "（超过 ±1/38 圈 = 9.4737°）；不影响对齐";
        if (report.branch_like)
        {
            text += "\n  提示：≈1/19 圈特征——断电期间可能转过整圈（规则要求避免）；"
                    "也可能只是位移接近 18.9474°。程序不做自动修正";
        }
    }
    if (!text.empty() && text.back() == '\n')
    {
        text.pop_back();
    }
    report.text = text;
    return report;
}

bool Session::auto_fix_ok(RawCounts raw0, Counts k, Counts r) const
{
    return config_.auto_fix && raw0 >= 0 && raw0 < kCountsPerTurn && std::llabs(k) <= 1 &&
           std::llabs(r) <= fix_window_counts_;
}

Counts Session::resolve_reference(const Command& command, std::string* why) const
{
    if (command.has_value)
    {
        return command.value; // 显式给的参考按"转子计数（raw）"理解（与 --pose-ref 同层）
    }
    if (config_.pose_ref_raw.has_value())
    {
        return *config_.pose_ref_raw;
    }
    if (have_mark_)
    {
        return mark_q_;
    }
    if (why != nullptr)
    {
        *why = "没有参考：check <读数>，或启动时带 --pose-ref，或先 mark";
    }
    return 0;
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
        confirm_ledger();
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
    {
        confirm_ledger();
        if (std::llabs(command.value) > max_move_counts_)
        {
            return {false, "move 超上限（P6）：|转角| > " +
                               format_output_angle(max_move_counts_) + "；分两步或改小目标"};
        }
        return set_target_from_here(command.value, now_s, "目标");
    }
    case CommandKind::kJog:
    {
        confirm_ledger();
        if (!have_feedback_)
        {
            return {false, "还没收到板子回复，不能给目标"};
        }
        if (std::llabs(command.value) > max_move_counts_)
        {
            return {false, "jog 超上限（P6）：|增量| > " +
                               format_output_angle(max_move_counts_) + "；分两步"};
        }
        return set_target_from_here(q_now() + command.value, now_s, "目标（相对）");
    }
    case CommandKind::kCheck:
    {
        std::string why;
        const Counts ref = resolve_reference(command, &why);
        if (!why.empty())
        {
            return {false, why};
        }
        if (!have_feedback_)
        {
            return {false, "还没收到板子回复，不能对照"};
        }
        const bool raw_space = command.has_value || config_.pose_ref_raw.has_value();
        const Counts current = raw_space ? static_cast<Counts>(last_raw_) : q_now();
        const CheckReport report = check_report(current, ref);
        return {true, report.text};
    }
    case CommandKind::kFix:
    {
        confirm_ledger();
        std::string why;
        const Counts ref = resolve_reference(command, &why);
        if (!why.empty())
        {
            return {false, why};
        }
        if (!have_feedback_)
        {
            return {false, "还没收到板子回复，不能修正"};
        }
        const bool raw_space = config_.pose_ref_raw.has_value();
        const Counts current = raw_space ? static_cast<Counts>(last_raw_) : q_now();
        const CheckReport report = check_report(current, ref);
        std::string message = report.text + "\n";
        if (report.k == 0)
        {
            message += "  ⇒ k = 0：无需修正";
            return {true, message};
        }
        if (!auto_fix_ok(first_raw_, report.k, report.r))
        {
            message += "  （自动护栏未通过——你现在是手动 fix，请自行确认'确实断电重上电过'）\n";
        }
        const ApplyResult fixed = apply_fix(report.k, now_s, false);
        return {fixed.ok, message + "  ⇒ " + fixed.message};
    }
    case CommandKind::kZeroMove:
    case CommandKind::kOffsetSet:
    {
        confirm_ledger();
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
