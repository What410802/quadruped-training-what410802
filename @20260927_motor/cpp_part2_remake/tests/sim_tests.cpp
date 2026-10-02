/**
 * @file sim_tests.cpp
 * @brief 模型自检（不接硬件、不依赖 SDK）：折圈 / 里程计 / 上电复位 / 整圈漂移（T15–T18）。
 *
 * 与 design.md §3.7 的"上报层分层"和 §5.4 的表 A / 表 B 对齐：模型的真值层与上报层分开，
 * 板子（模型）只如实上报"本次上电从 datum 量起的里程计"，怎么解是被测程序的事。
 */

#include "motor/counts.hpp"
#include "motor/transport.hpp"
#include "motor_sim/model.hpp"

#include <cmath>
#include <cstdio>
#include <string>

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

void expect_near(double actual, double expected, double tolerance, const std::string& description)
{
    if (std::fabs(actual - expected) > tolerance)
    {
        std::fprintf(stderr, "FAIL: %s（实际 %.3f，期望 %.3f）\n", description.c_str(), actual,
                     expected);
        ++failures;
    }
}

/** 用位置环把"电机"开到一个转子计数目标（足够多的步数，等它稳下来） */
void drive(motor_sim::MotorModel* model, motor::Counts target, double seconds = 2.0)
{
    motor::DeviceCommand command;
    command.zero_torque = false;
    command.pos_counts = target;
    command.kp_rotor = 5.0;
    command.kd_rotor = 0.2;
    const double dt = 0.002;
    for (double t = 0.0; t < seconds; t += dt)
    {
        model->step(command, dt);
    }
}

// ---------- T15：上电折圈 + 会话内里程计 ----------

void test_power_on_fold_and_odometer()
{
    motor_sim::MotorModel model;
    expect_near(double(model.reported_raw()), 0.0, 1.0, "上电处 raw = 0（datum 按当前位置选）");

    drive(&model, motor::kCountsPerTurn); // 转一个转子圈 = 输出端 56.8421°
    const motor::Counts raw = model.reported_raw();
    expect_near(double(raw), double(motor::kCountsPerTurn), 200.0,
                "同一上电周期内是里程计（转过一个转子圈后 raw ≈ C，不折回 0）");

    // 断电重上电：整数部分清零（折圈），raw 回到 [0, C)
    model.set_powered(false);
    model.power_cycle();
    const motor::Counts folded = model.reported_raw();
    expect(folded >= 0 && folded < motor::kCountsPerTurn, "上电复位后 raw ∈ [0, C)");
}

// ---------- T15/表 A：折圈结果与 design §5.4 表 A 逐行一致 ----------

void test_fold_matches_design_table()
{
    struct Case
    {
        double delta_deg;
        motor::Counts raw0;
    };
    // 记号点（转子零点）处断电位移 δ → 首帧 raw（表 A 的列）
    const Case cases[] = {
        {-20.0, 21239}, {-10.0, 27003}, {0.0, 0}, {10.0, 5765}, {20.0, 11529}, {30.0, 17294},
    };
    for (const Case& item : cases)
    {
        motor_sim::MotorModel model;
        if (item.delta_deg != 0.0)
        {
            model.set_powered(false);
            model.offturns(item.delta_deg / 360.0); // 断电期间净位移 δ（输出端）
            model.power_cycle();
        }
        expect_near(double(model.reported_raw()), double(item.raw0), 5.0,
                    "δ=" + std::to_string(item.delta_deg) + "° ⇒ 首帧 raw=" +
                        std::to_string(item.raw0));
    }
}

// ---------- T17 / 表 B：断电期间净转整圈 ⇒ 读数漂移 ----------

void test_offturns_branch_drift()
{
    struct Case
    {
        double turns;
        motor::Counts raw0;
    };
    const Case cases[] = {
        {1.0, 10923}, {2.0, 21845}, {3.0, 0},
    };
    for (const Case& item : cases)
    {
        motor_sim::MotorModel model; // 上电处 = 记号点（raw = 0）
        model.set_powered(false);
        model.offturns(item.turns);
        model.power_cycle();
        expect_near(double(model.reported_raw()), double(item.raw0), 35.0,
                    "断电净转 " + std::to_string(item.turns) + " 整圈 ⇒ 首帧 raw=" +
                        std::to_string(item.raw0) + "（表 B）");
    }
}

// ---------- T16：直接换基准（注入） ----------

void test_datum_injection()
{
    motor_sim::MotorModel model;
    drive(&model, 5000);
    const motor::Counts before = model.reported_raw();
    model.datum_zones(1);
    expect_near(double(model.reported_raw()), double(before - motor::kCountsPerTurn), 1.0,
                "换基准 = 上报值整体平移 1 个转子圈（C 计数）");
}

} // namespace

int main()
{
    test_power_on_fold_and_odometer();
    test_fold_matches_design_table();
    test_offturns_branch_drift();
    test_datum_injection();

    if (failures == 0)
    {
        std::printf("motor_sim_tests：全部通过\n");
        return 0;
    }
    std::fprintf(stderr, "motor_sim_tests：%d 项失败\n", failures);
    return 1;
}
