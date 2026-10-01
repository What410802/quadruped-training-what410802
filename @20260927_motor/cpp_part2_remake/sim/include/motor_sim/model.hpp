/**
 * @file model.hpp
 * @brief 电机 + 驱动板模型：转子动力学、上报语义、外部力矩（手）、记号线与线夹角。
 *
 * 单位约定（与 core 一致）：位置对外一律"转子侧计数"（板子 pos 的单位），速度 / 力矩 / 增益用
 * 转子侧 SI；只有"外部力矩 / 握住 / 记号线"这三个用户界面量用**输出端**单位（N·m、度）。
 *
 * 模型只依赖 core（设备帧与标度换算），不依赖 SDK、不做 I/O；实验台（apps/motor_sim）与将来的
 * 进程内传输都驱动同一份实现。
 */

#pragma once

#include "motor/counts.hpp"
#include "motor/transport.hpp"

#include <cstdint>

namespace motor_sim
{

/** 模型参数（转子侧物理量） */
struct ModelParams
{
    double tau_max_rotor_nm = 20.0; // 力矩限幅（GO-M8010-6 峰值 23.7 N·m 的保守值）
    double tau_friction_nm = 0.010;      // 库仑摩擦：静止时的死区来源。实机 2026-10-01 反推
                                         // τ ≈ 0.01 N·m（转子侧）⇒ kp=80 时死区 ±26 计数的停机偏差
    double inertia_kg_m2 = 1e-3;    // 转子等效惯量（速度时间常数 = J/kd）
    double max_speed_rotor_rad_s = 30.0; // 最高转速（手册值；电压 / 反电动势限制，超过就不再加速）
    double hand_stiffness_rotor = 1.0; // "手握住"的弹簧刚度 [N·m/rad]（转子侧）
    double hand_damping_rotor = 0.01;  // "手握住"的阻尼 [N·m·s/rad]（转子侧）
    double hand_max_rotor_nm = 1.0;    // 手能给出的力矩上限（≈ 输出端 6.3 N·m）
    double torque_out_max_nm = 30.0;   // torque 命令的限幅（输出端；保护实验台）
    double heat_rate = 0.05;           // 温度上升系数（演示用，不是热模型）
};

/** 外部交互方式（同一时刻只有一种） */
enum class Interaction
{
    kNone,   // 松手
    kTorque, // 恒力矩（给定输出端 N·m）
    kHold,   // 手握住：软弹簧拉向某个输出角
};

class MotorModel
{
  public:
    explicit MotorModel(const ModelParams& params = ModelParams{});

    /** 一帧：按报文命令推进一步（命令已解成转子侧设备帧） */
    void step(const motor::DeviceCommand& command, double dt);

    /** 组一帧反馈（转子侧；位置是板子上报的原始计数） */
    motor::DeviceFeedback feedback() const;

    // ---------- 外部交互（输出端） ----------
    void apply_torque_out(double torque_out_nm);
    void hold_output_deg(double output_deg);
    void release();
    Interaction interaction() const { return interaction_; }
    double torque_command_out_nm() const { return torque_out_nm_; }
    double hold_target_out_deg() const { return hold_target_out_deg_; }

    // ---------- 记号笔的线（输出端角度参考） ----------
    void draw_line(); // 在当前输出角画线（重画即换参考）
    bool has_line() const { return has_line_; }
    void clear_line();
    double line_wrapped_deg() const; // 当前位置与线的夹角，缠绕到 (-180, 180]
    double line_cumulative_deg() const; // 累计夹角（可超一圈，用于显示"±圈数 ±<360°"）

    // ---------- 状态（打印与测试用） ----------
    motor::Counts true_counts() const; // 真实位置（转子计数）
    motor::RawCounts reported_raw() const; // 板子上报的位置（本模型：里程计，与真实位置一致）
    double speed_rotor_rad_s() const { return speed_rad_s_; }
    double torque_rotor_nm() const { return torque_rotor_nm_; }
    double output_deg() const; // 输出端角度（度）
    double output_speed_deg_s() const;
    int temp_c() const { return static_cast<int>(temp_c_); }
    unsigned merror() const { return merror_; }
    long frames() const { return frames_; }

  private:
    double hand_torque_rotor_nm() const;

    ModelParams params_;
    double position_rad_ = 0.0;    // 转子位置（真实）
    double speed_rad_s_ = 0.0;     // 转子角速度
    double torque_rotor_nm_ = 0.0; // 上一次实际作用的转子力矩（摩擦之后）
    double temp_c_ = 30.0;
    unsigned merror_ = 0;
    long frames_ = 0;

    Interaction interaction_ = Interaction::kNone;
    double torque_out_nm_ = 0.0;
    double hold_target_out_deg_ = 0.0;

    bool has_line_ = false;
    double line_output_deg_ = 0.0;
};

} // namespace motor_sim
