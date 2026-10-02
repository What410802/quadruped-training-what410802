/**
 * @file core_tests.cpp
 * @brief motor_core 的自检：换算、报文标度、账本、插值、语句解析、显示格式与会话状态机（无硬件）。
 */

#include "motor/command.hpp"
#include "motor/counts.hpp"
#include "motor/format.hpp"
#include "motor/protocol.hpp"
#include "motor/session.hpp"
#include "motor/trajectory.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <string>
#include <vector>

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
        std::fprintf(stderr, "FAIL: %s（实际 %.9f，期望 %.9f）\n", description.c_str(), actual,
                     expected);
        ++failures;
    }
}

using motor::Counts;

// ---------- 换算与显示 ----------

void test_counts()
{
    expect_eq(motor::output_deg_to_counts(30.0), 17294, "30° → 17294 计数");
    expect_near(motor::counts_to_output_deg(17294), 29.9996, 0.001, "17294 计数 → 29.9996°");
    expect_near(motor::kZoneDegrees, 56.8421, 0.0001, "一个零点区间 = 56.8421°");
    expect_eq(motor::output_turns_to_counts(1.0), 207531, "1 输出圈 → 207530.67 → 207531 计数");
    expect_eq(motor::turns_of_delta(32768), 1, "整圈判定 +1");
    expect_eq(motor::turns_of_delta(-32769), -1, "整圈判定 -1");
    expect_eq(motor::turns_of_delta(16383), 0, "不到半圈判 0");
    expect_eq(motor::turns_of_delta(16384), 1, "正好半圈向上判 1（四舍五入）");
}

void test_protocol()
{
    // 实测锚点（旧版 docs/protocol.md）：SDK 打包用整数除法，写进去会掉 1 LSB
    expect_eq(motor::speed_raw_from_rotor_rad(6.33), 257, "6.33 rad/s → spd_des 257");
    expect_eq(motor::gain_raw_from_rotor_gain(1.9966), 2555, "K_P 1.9966 → 2555");
    expect_eq(motor::gain_raw_from_rotor_gain(0.0749), 95, "K_W 0.0749 → 95");
    expect_eq(motor::gain_raw_from_rotor_gain(100.0), motor::kGainRawMax, "增益超量程钳位 32766");
    expect_eq(motor::torque_raw_from_rotor_nm(1.0), 256, "1 N·m → 256");
    // 计数 ↔ SDK 的 float 弧度（π′ = 3.1416）
    expect_eq(motor::rotor_rad_to_counts(3.16498), 16506, "3.165 rad ↔ pos_des 16506");
    expect_near(motor::counts_to_sdk_q(16506), 3.16498, 0.001, "16506 计数 → SDK q ≈ 3.165");
}

void test_format()
{
    // 取"恰好能整除"的计数：77824 计数 = 135.000°（每 77824 个计数正好 135°）
    expect(motor::format_output_angle(466944) == "+2 圈 +90.000°", "810° 显示为 +2 圈 +90.000°");
    expect(motor::format_output_angle(-466944) == "-2 圈 -90.000°", "-810° 显示为 -2 圈 -90.000°");
    expect(motor::format_output_angle(-77824) == "+0 圈 -135.000°",
           "T-135° 显示为 +0 圈 -135.000°");
    expect(motor::format_output_angle(0) == "+0 圈 +0.000°", "0 计数显示为 +0 圈 +0.000°");
    expect(motor::format_output_angle(motor::output_deg_to_counts(-0.009)) == "+0 圈 -0.009°",
           "近零负角显示为 +0 圈 -0.009°");
}

// ---------- 账本 ----------

void test_ledger()
{
    motor::Ledger ledger;
    ledger.anchor(0, 0.0);
    expect_eq(ledger.raw_to_q(1000), 1000, "raw → q（offset 0）");
    expect_eq(ledger.q_to_board(1000), 1000, "q → 板子（offset 0）");

    const Counts delta = motor::output_deg_to_counts(30.0);
    ledger.shift_offset(delta, 1.0);
    expect_eq(ledger.raw_to_q(1000), 1000 + delta, "offset 收到加：同一读数 q +30°");
    expect_eq(ledger.q_to_board(delta), 0, "下发减：q = 30° 对应板子 0");
    expect(ledger.events().size() == 2, "锚定 + 偏移两条事件");

    motor::Ledger other;
    other.anchor(1, 0.0);
    expect_eq(other.raw_to_q(100), 100 + motor::kCountsPerTurn, "k=1 圈基准");
}

// ---------- 插值 ----------

void test_trajectory()
{
    motor::TrapezoidPlanner planner;
    planner.set_limits(90.0, 180.0);
    planner.snap_to(0);
    const Counts target = motor::output_deg_to_counts(30.0);
    planner.set_target(target);

    const double vmax = static_cast<double>(motor::output_deg_to_counts(90.0));
    double max_velocity = 0.0;
    double previous = 0.0;
    int steps = 0;
    bool monotone = true;
    while (!planner.settled(0) && steps < 10000)
    {
        const double position = planner.step(0.005);
        max_velocity = std::max(max_velocity, std::fabs(planner.velocity_counts_per_s()));
        if (position < previous - 1e-9)
        {
            monotone = false;
        }
        previous = position;
        ++steps;
    }
    expect(planner.settled(0), "插值在有限步内收敛");
    expect_eq(planner.position(), target, "终止位置 = 目标");
    expect(monotone, "位置单调不回头");
    expect(max_velocity <= vmax * 1.0001, "速度不超过 vmax");
    expect(steps > 100, "30° 行程不会一步到位（按 90°/s 约 0.7 s）");
}

// ---------- 语句解析 ----------

void test_command()
{
    const auto command_of = [](const char* text) { return motor::parse_command(text, nullptr); };

    expect(command_of("move 30").kind == motor::CommandKind::kMove, "解析 move 30");
    expect_eq(command_of("move 30").value, command_of("move 30deg").value, "move 30 == move 30deg");
    expect_eq(command_of("move 0.5r").value, command_of("move 180deg").value, "0.5r == 180deg");
    expect_eq(command_of("move 0.5rev").value, command_of("move 0.5r").value, "rev 与 r 同义");
    expect_near(motor::counts_to_output_deg(command_of("move 3.14159265rad").value), 180.0, 0.01,
                "π rad ≈ 180°");
    expect_eq(command_of("jog -30").value, -motor::output_deg_to_counts(30.0), "jog 支持负号");
    expect_eq(command_of("zero move 30").value, motor::output_deg_to_counts(30.0), "zero move 30");
    expect_eq(command_of("zero move -30").value, -motor::output_deg_to_counts(30.0),
              "zero move 支持负号");
    expect_eq(command_of("move 32768tick").value, 32768, "move 32768tick = 一个转子圈（计数）");
    expect_eq(command_of("move 21845ticks").value, 21845, "ticks 同义，直接按计数取值");
    expect_near(motor::counts_to_output_deg(command_of("move 32768tick").value), motor::kZoneDegrees,
                1e-9, "32768 tick = 一个零点区间（56.8421° 输出端）");
    expect(command_of("offset set 30").kind == motor::CommandKind::kOffsetSet, "offset set");
    expect(command_of("offset add 30").kind == motor::CommandKind::kUnknown,
           "offset add 已移除（改为 zero move）");
    expect(command_of("mark goto").kind == motor::CommandKind::kMarkGoto, "mark goto");
    expect(command_of("MOVE   30DEG").kind == motor::CommandKind::kMove, "大小写与空白不敏感");
    expect(command_of("wait 2.5").kind == motor::CommandKind::kWait, "wait 语句");
    expect_near(command_of("wait 2.5").wait_s, 2.5, 1e-12, "wait 秒数");
    expect(command_of("quit").kind == motor::CommandKind::kQuit, "quit");
    expect(command_of("move 30foo").kind == motor::CommandKind::kUnknown, "非法单位应失败");
    expect(command_of("jog").kind == motor::CommandKind::kUnknown, "缺参数应失败");
    expect(command_of("wait -1").kind == motor::CommandKind::kUnknown, "负等待应失败");

    const std::vector<std::string> statements = motor::split_statements("move 0; wait 1\nstate;");
    expect(statements.size() == 3, "分号与换行都切句");
    expect(statements[0] == "move 0" && statements[1] == "wait 1" && statements[2] == "state",
           "切句内容正确");
}

// ---------- 会话状态机（用"理想驱动板"喂反馈） ----------

motor::DeviceFeedback feedback_at(Counts board_counts)
{
    motor::DeviceFeedback feedback;
    feedback.raw = static_cast<motor::RawCounts>(board_counts);
    feedback.temp_c = 30;
    feedback.merror = 0;
    feedback.torque_rotor = 0.0;
    return feedback;
}

/** 喂一帧"理想驱动板"的反馈 */
void feed(motor::Session* session, Counts board_counts, double now_s)
{
    const motor::DeviceFeedback feedback = feedback_at(board_counts);
    session->on_feedback(&feedback, now_s);
}

/** 理想驱动板：下一帧就把命令位置当读数回报（瞬时到位） */
void settle(motor::Session* session, int frames, double* now_s)
{
    for (int i = 0; i < frames; ++i)
    {
        session->step(0.005);
        const motor::DeviceCommand command = session->device_command();
        const motor::DeviceFeedback feedback = feedback_at(command.pos_counts);
        session->on_feedback(&feedback, *now_s);
        *now_s += 0.005;
    }
}

void test_session_basic()
{
    motor::Session session({});
    double now = 0.0;
    session.step(0.005);
    expect(session.device_command().zero_torque, "握手期只发零力矩");
    feed(&session, 1000, now);
    now += 0.005;
    expect(session.link_state() == motor::LinkState::kOnline, "首帧后进入 Online");
    expect(session.enabled(), "首帧后默认位置保持");
    expect_eq(session.target(), 1000, "上电目标 = 当前位置");

    const motor::Command move = motor::parse_command("move 30", nullptr);
    const motor::ApplyResult result = session.apply(move, now);
    expect(result.ok, "move 30 可执行");
    const Counts want = motor::output_deg_to_counts(30.0);
    expect_eq(session.target(), want, "目标 = 30° 计数");
    session.step(0.005);
    const motor::DeviceCommand command = session.device_command();
    expect(!command.zero_torque, "move 后开始出力");
    expect(command.pos_counts > 0 && command.pos_counts <= want,
           "插值：板子目标朝 30° 走（不会一步阶跃到目标）");

    settle(&session, 400, &now);
    expect_eq(session.q_now(), want, "理想板：到达 30°");
    expect(session.arrived(), "到位判据成立");

    // free / hold
    session.apply(motor::parse_command("free", nullptr), now);
    session.step(0.005);
    expect(session.device_command().zero_torque, "free 后只发零力矩");
    session.apply(motor::parse_command("hold", nullptr), now);
    session.step(0.005);
    expect(!session.device_command().zero_torque, "hold 后恢复出力");
}

void test_session_zero_move_keeps_physical_target()
{
    motor::Session session({});
    double now = 0.0;
    feed(&session, 0, now);
    now += 0.005;
    settle(&session, 50, &now);
    session.apply(motor::parse_command("move 30", nullptr), now);
    settle(&session, 400, &now);

    const Counts board_before = session.device_command().pos_counts;
    const Counts q_before = session.q_now();
    session.apply(motor::parse_command("mark", nullptr), now);
    const Counts mark_before = session.mark_q();

    const motor::ApplyResult result =
        session.apply(motor::parse_command("zero move 30", nullptr), now);
    expect(result.ok, "zero move 30 可执行");
    now += 0.005;
    session.step(0.005);
    const Counts delta = motor::output_deg_to_counts(30.0);
    expect_eq(session.device_command().pos_counts, board_before, "移零点后下发的板子目标不变");
    expect_eq(session.q_now(), q_before - delta, "零点正向移 30° ⇒ 同一物理点读数 −30°");
    expect_eq(session.ledger().offset(), -delta, "内部 offset 变量 = −30°");
    expect_eq(session.target(), board_before - delta, "目标在 q 空间同步平移");
    expect_eq(session.mark_q(), mark_before - delta, "标记点在 q 空间同步平移");

    // 同一个角度命令（move 30）的板子目标比标定前多 30°（零点沿正方向挪了）
    session.apply(motor::parse_command("move 30", nullptr), now);
    expect_eq(session.ledger().q_to_board(session.target()), 2 * delta,
              "移零点后 move 30 的板子目标 = 60°（比标定前多 30°）");

    // 回到标记点：目标仍是同一个物理点
    session.apply(motor::parse_command("mark goto", nullptr), now);
    settle(&session, 200, &now);
    expect_eq(session.device_command().pos_counts, board_before, "mark goto 落回原物理位置");
}

void test_session_link_lost()
{
    motor::Session session({});
    double now = 0.0;
    feed(&session, 0, now);
    const int offline_frames = motor::SessionConfig{}.offline_frames;
    for (int i = 0; i < offline_frames; ++i)
    {
        session.on_feedback(nullptr, now);
        now += 0.005;
    }
    expect(session.faulted(), "连续 N 帧无回复 ⇒ 保护");
    expect(session.fault_reason().find("失联") != std::string::npos, "故障原因含失联");
    session.step(0.005);
    expect(session.device_command().zero_torque, "故障后只发零力矩");
}

// ---------- M4：启动检查 / 自动对齐 / P6 / 标度（T19–T24） ----------

/** 与 design.md §5.4 算例同源：δ = -10° ⇒ 首帧 raw 27003（ref = 0 计数的记号点） */
constexpr Counts kRawAtMinus10Deg = 27003;

void test_scale_three_turns()
{
    // T19：输出端 3 圈 = 19 转子圈 = 622592 计数 = 1080.0000°（不是 1080.5687°）
    expect_eq(motor::output_turns_to_counts(3.0), 622592, "3 圈 = 622592 计数");
    expect_near(motor::counts_to_output_deg(622592), 1080.0, 1e-9, "622592 计数 = 1080°");
    expect_near(motor::counts_to_output_deg(32768), 56.842105263157894, 1e-9, "1 转子圈 = 56.8421°");
}

void test_check_report_decomposition()
{
    motor::SessionConfig config;
    config.pose_ref_raw = 0;
    motor::Session session(config);

    // δ = -10°：k = +1、r = -5765 计数（-10.0004°，量化来自半计数）
    const motor::CheckReport report = session.check_report(kRawAtMinus10Deg, 0);
    expect_eq(report.k, 1, "δ=-10° ⇒ k=+1");
    expect_eq(report.r, -5765, "δ=-10° ⇒ r=-5765 计数");
    expect(report.warn_band && !report.ambiguous, "δ=-10° 落在提示带（|r|>9.47°）");
    expect(report.text.find("两种解释") != std::string::npos, "报告含两种解释");

    // 恰在半格：二义点
    const motor::CheckReport half = session.check_report(motor::kHalfZoneCounts, 0);
    expect(half.ambiguous, "恰在半格 ⇒ 二义点");

    // 整格：与 0° 同读数（反例 1，作为已知局限——raw 无法区分"+L 位移"与"没动"）
    const motor::CheckReport zone = session.check_report(0, 0);
    expect(zone.k == 0 && zone.r == 0, "整格错位读数发现不了（已知局限）");
}

void test_auto_fix_on_startup()
{
    // T24：护栏通过 ⇒ 启动即自动对齐（kAlignFix 事件 +1、电机不动）
    motor::SessionConfig config;
    config.pose_ref_raw = 0;
    motor::Session session(config);
    double now = 0.0;
    feed(&session, kRawAtMinus10Deg, now);

    expect(!session.awaiting_confirm(), "护栏通过不 gate");
    expect_eq(session.ledger().offset(), -motor::kCountsPerTurn, "自动对齐：offset = -32768");
    expect_eq(session.fixes(), 1, "自动对齐记 1 次 fix");
    expect(session.ledger().events().size() == 2, "事件：锚定 + 区间对齐");
    expect_eq(session.q_now(), kRawAtMinus10Deg - motor::kCountsPerTurn, "q = raw + offset");
    now += 0.005;
    session.step(0.005);
    expect_eq(session.device_command().pos_counts, kRawAtMinus10Deg,
              "物理目标不动：下发的板子目标仍 = 当前 raw");
}

void test_startup_guard_blocks()
{
    // T24 负例：|r| > W（位移 25°）⇒ 不自动、停在 gate
    {
        motor::SessionConfig config;
        config.pose_ref_raw = 0;
        motor::Session session(config);
        double now = 0.0;
        const Counts raw = motor::kCountsPerTurn - 14412; // δ = -25.0°（|r| = 25° > W = 20°）
        feed(&session, raw, now);
        expect(session.awaiting_confirm(), "|r| > W ⇒ 停在 gate");
        expect_eq(session.ledger().offset(), 0, "gate 时不动账本");
    }
    // --no-auto-fix：护栏本身能过，但开关关掉 ⇒ 停在 gate，人工 fix 才动
    {
        motor::SessionConfig config;
        config.pose_ref_raw = 0;
        config.auto_fix = false;
        motor::Session session(config);
        double now = 0.0;
        feed(&session, kRawAtMinus10Deg, now);
        expect(session.awaiting_confirm(), "auto_fix 关 ⇒ 停在 gate");
        const motor::ApplyResult result = session.apply(motor::parse_command("fix", nullptr), now);
        expect(result.ok, "人工 fix 可执行");
        expect_eq(session.ledger().offset(), -motor::kCountsPerTurn, "人工 fix 后 offset = -32768");
        expect(!session.awaiting_confirm(), "显式命令解除 gate");
    }
    // 首帧 raw ≥ 32768（更像"电机没断电、只是程序重启"）⇒ 不自动
    {
        motor::SessionConfig config;
        config.pose_ref_raw = 0;
        motor::Session session(config);
        double now = 0.0;
        feed(&session, motor::kCountsPerTurn + kRawAtMinus10Deg, now);
        expect(session.awaiting_confirm(), "首帧 raw ≥ C ⇒ 停在 gate");
        expect_eq(session.ledger().offset(), 0, "gate 时不动账本");
    }
}

void test_runtime_datum_change()
{
    // T4（兜底）：运行中基准挪了 k 格（Δraw 正好是整格）⇒ 只补账本、物理目标不动
    motor::SessionConfig config;
    motor::Session session(config);
    double now = 0.0;
    feed(&session, 5, now);
    for (int i = 0; i < 5; ++i)
    {
        now += 0.005;
        session.step(0.005);
        feed(&session, 5, now);
    }
    const Counts q_before = session.q_now();
    const size_t events_before = session.ledger().events().size();
    // 板子换基准：datum 挪 +1 个转子圈 ⇒ 上报 raw 少 32768
    feed(&session, 5 - motor::kCountsPerTurn, now + 0.005);
    expect_eq(session.q_now(), q_before, "运行中换基准：q 不变（账本补上）");
    expect(session.ledger().events().size() == events_before + 1, "运行中换基准记 1 条对齐事件");
}

void test_move_limit_p6()
{
    // T20：单次 move / jog 超上限被拒绝
    motor::Session session({});
    double now = 0.0;
    feed(&session, 0, now);
    const motor::ApplyResult too_far = session.apply(motor::parse_command("move 720", nullptr), now);
    expect(!too_far.ok, "move 720 超上限被拒（P6）");
    expect(too_far.message.find("P6") != std::string::npos, "拒绝原因提到 P6");
    const motor::ApplyResult ok = session.apply(motor::parse_command("move 350", nullptr), now);
    expect(ok.ok, "move 350 在上限内");
    const motor::ApplyResult jog_far = session.apply(motor::parse_command("jog 400", nullptr), now);
    expect(!jog_far.ok, "jog 400 超上限被拒（P6）");
}

void test_fix_max_fixes()
{
    motor::SessionConfig config;
    config.pose_ref_raw = 0;
    config.auto_fix = false;
    config.max_fixes = 1;
    motor::Session session(config);
    double now = 0.0;
    feed(&session, kRawAtMinus10Deg, now);
    const motor::ApplyResult first =
        session.apply(motor::parse_command("check 0tick", nullptr), now);
    expect(first.ok && first.message.find("k = +1") != std::string::npos, "check 报告 k = +1");
    expect(session.apply(motor::parse_command("fix", nullptr), now).ok, "第一次 fix 成功");
    expect(!session.apply(motor::parse_command("fix", nullptr), now).ok, "超过 max-fixes 被拒");
}

// ---------- 保护（沿用 M1 用例） ----------

void test_session_protection()
{
    // merror
    {
        motor::Session session({});
        double now = 0.0;
        feed(&session, 0, now);
        motor::DeviceFeedback feedback = feedback_at(0);
        feedback.merror = 2;
        session.on_feedback(&feedback, now);
        expect(session.faulted() && session.fault_reason().find("merror") != std::string::npos,
               "merror ⇒ 保护");
    }
    // 温度
    {
        motor::Session session({});
        double now = 0.0;
        motor::DeviceFeedback feedback = feedback_at(0);
        feedback.temp_c = 85;
        session.on_feedback(&feedback, now);
        expect(session.faulted() && session.fault_reason().find("温度") != std::string::npos,
               "超温 ⇒ 保护");
    }
    // 卡住：输出端力矩 = 转子力矩 × N，超过 1.5 N·m 并持续 1 s
    {
        motor::Session session({});
        double now = 0.0;
        feed(&session, 0, now);
        bool raised = false;
        for (int i = 0; i < 400 && !raised; ++i)
        {
            motor::DeviceFeedback feedback = feedback_at(0);
            feedback.torque_rotor = 0.3; // 0.3 × 6.333 ≈ 1.9 N·m（输出端）
            now += 0.005;
            session.on_feedback(&feedback, now);
            raised = session.faulted();
        }
        expect(raised && session.fault_reason().find("卡住") != std::string::npos,
               "力矩持续超限 ⇒ 判卡住");
    }
}

} // namespace

int main()
{
    test_counts();
    test_protocol();
    test_format();
    test_ledger();
    test_trajectory();
    test_command();
    test_session_basic();
    test_session_zero_move_keeps_physical_target();
    test_session_link_lost();
    test_scale_three_turns();
    test_check_report_decomposition();
    test_auto_fix_on_startup();
    test_startup_guard_blocks();
    test_runtime_datum_change();
    test_move_limit_p6();
    test_fix_max_fixes();
    test_session_protection();

    if (failures == 0)
    {
        std::printf("motor_core_tests：全部通过\n");
        return 0;
    }
    std::fprintf(stderr, "motor_core_tests：%d 项失败\n", failures);
    return 1;
}
