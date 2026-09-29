/**
 * @file trajectory.hpp
 * @brief 梯形速度插值（tick 空间）：给定目标与速度/加速度上限，每帧给出下一步的位置与速度。
 *
 * 用 tick 做单位，是因为位置账本本来就是
 * tick；时间仍是连续的（double），所以不会有"一格一格跳"的观感。 用法：SetLimits() 一次 →
 * SetTarget() 换目标 → 每帧 Step(dt) 取 q_cmd 与 v_cmd（v_cmd 传给驱动板做前馈）。
 */
#pragma once

#include "motor_bench/ticks.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>

namespace motor_bench
{

class TrapezoidPlanner
{
  public:
    void SetLimits(double vmax_deg_per_s, double amax_deg_per_s2)
    {
        vmax_tps_ = ticks::DegToTicks(vmax_deg_per_s);   // tick/s
        amax_tps2_ = ticks::DegToTicks(amax_deg_per_s2); // tick/s²
        v_plan_ = 0.0;
    }

    /** 设置新目标（tick）；从当前插值位置重新起步 */
    void SetTarget(int64_t target_ticks) { target_ = target_ticks; }

    int64_t target() const { return target_; }
    double position() const { return position_; }
    int64_t position_ticks() const { return std::llround(position_); }
    double velocity_tps() const { return v_plan_; }

    /** 走一步：返回这一步之后的"命令位置"（tick，double 以便平滑） */
    double Step(double dt)
    {
        const double err = static_cast<double>(target_) - position_;
        const double a_step = amax_tps2_ * dt;
        if (std::fabs(err) <= 1e-9)
        {
            v_plan_ = 0.0;
        }
        else
        {
            // 该踩的最高速度：v² = 2·a·|Δ|（这样才煞得住），再按加速度斜坡逼近
            const double v_cap = std::min(std::sqrt(2.0 * amax_tps2_ * std::fabs(err)), vmax_tps_);
            const double v_want = (err > 0.0) ? v_cap : -v_cap;
            if (std::fabs(v_want - v_plan_) <= a_step)
            {
                v_plan_ = v_want;
            }
            else
            {
                v_plan_ += (v_want > v_plan_) ? a_step : -a_step;
            }
        }
        const double step = v_plan_ * dt;
        if (std::fabs(err) <= std::fabs(step))
        {
            position_ = static_cast<double>(target_);
            v_plan_ = 0.0;
        }
        else
        {
            position_ += step;
        }
        return position_;
    }

    /** 让插值位置直接贴到某个值（启动、重锚后调用，避免"想起来再去追"） */
    void SnapTo(int64_t pos_ticks)
    {
        position_ = static_cast<double>(pos_ticks);
        target_ = pos_ticks;
        v_plan_ = 0.0;
    }

    bool settled(int64_t tol_ticks) const
    {
        return std::llabs(target_ - position_ticks()) <= tol_ticks && v_plan_ == 0.0;
    }

  private:
    double vmax_tps_ = ticks::DegToTicks(90.0);
    double amax_tps2_ = ticks::DegToTicks(180.0);
    double position_ = 0.0;
    int64_t target_ = 0;
    double v_plan_ = 0.0;
};

} // namespace motor_bench
