/**
 * @file motor.hpp
 * @brief 仿真侧的"关节电机"：把 MIT 五参数变成关节力矩。
 *
 * 分工上这是**实机驱动板**那一侧：控制器节点只发 {kp, kd, q, w, tau}（msg/MitCommand.msg），
 * 电机（这里就是本文件）自己算
 *
 *     τ = τ_ff + kp·(q_des − q) + kd·(w_des − q̇)
 *
 * 再把结果按电机能力限幅，最后写进 MuJoCo 的 `data.ctrl`（本模型的执行器是 `<motor gear="1">`，
 * `ctrl` 就是关节侧力矩，见 models/black_description.xml 的 <actuator> 段）。
 *
 * 与第三次培训完整版（@20260927_motor/cpp/src/motor.h）的关系：
 *   * 这里只留"MIT 公式 + 一道限幅"；完整版还带限幅/死区/指令延迟/噪声四个开关与统计。
 *   * 本次任务做完基本功能后，把"非理想项"（`--deadzone` / `--delay-cycles` / `--noise`）
 *     补到这里即可 —— 它们本来就是电机侧的特性，放在仿真侧比放在控制器侧更贴实机
 *     （实机上死区、电流限幅、指令延迟都发生在驱动板，上层控制器看不见）。
 *
 * 量纲：全部是**关节侧**（输出端）。**本文件不做电流推定**：`MotorState.cur` 一律报 0，
 * 理由见 sim_node.cpp 里那一处注释（我们没有支撑它的电机模型与实测数据）。
 * 转子侧的换算（讲义 §2.3 的 ×N / ÷N / ÷N²）等将来真要做电流/力矩标定时再说，
 * 那时需要的是"电机电气模型 + 实测标定数据"，不是这里加一个除法。
 */

#pragma once

#include <algorithm>

namespace quadruped::motor
{

/// 关节侧力矩上限 [N·m] 的默认值：取本模型 actuator 的 `ctrlrange`（±20）。
/// 可被仿真节点的 tau_max 参数覆盖（实机 black 配置是 33.5 N·m，讲课义 §1.4）。
inline constexpr double kDefaultTauMax = 20.0;

/// 减速比：GO-M8010-6 是 6.33（讲义 §2.2：转子转 19 圈、输出端转 3 圈）。
/// 这是讲义给的真值，但**本任务不拿它算任何东西**——留在这里是为了将来做转子侧换算
/// （力矩标定、电流环建模）时有个出处，不要用它去"推"电流（见上面的说明）。
inline constexpr double kDefaultGear = 6.33;

/// 一条 MIT 指令（单个关节）。
struct Cmd
{
    double tau_ff = 0.0; ///< 前馈力矩 [N·m]
    double kp = 0.0;     ///< 位置刚度 [N·m/rad]
    double q_des = 0.0;  ///< 期望关节角 [rad]
    double kd = 0.0;     ///< 速度刚度 [N·m·s/rad]
    double w_des = 0.0;  ///< 期望关节角速度 [rad/s]
};

/// 一条指令 + 当前状态 → 关节力矩（含电机侧限幅）。
inline double Torque(const Cmd& c, double q, double dq, double tau_max)
{
    const double tau = c.tau_ff + c.kp * (c.q_des - q) + c.kd * (c.w_des - dq);
    return std::clamp(tau, -tau_max, tau_max);
}

} // namespace quadruped::motor
