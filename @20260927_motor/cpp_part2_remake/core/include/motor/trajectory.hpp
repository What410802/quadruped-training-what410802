/**
 * @file trajectory.hpp
 * @brief 梯形速度插值（计数空间）：给定目标与速度 / 加速度上限，每帧给出下一步的位置与速度。
 *
 * 与旧版 cpp_part2 的插值同一套算法（旧版实测平稳）：v² = 2a|Δ| 限速 + 加速度斜坡。
 * 长距离是梯形速度剖面、短距离退化成三角；每帧可重规划，改目标 / 被打断都安全。
 */

#pragma once

#include "motor/counts.hpp"

#include <algorithm>
#include <cmath>
#include <cstdlib>

namespace motor
{

class TrapezoidPlanner
{
  public:
    void set_limits(double vmax_deg_per_s, double amax_deg_per_s2)
    {
        vmax_cps_ = static_cast<double>(output_deg_to_counts(vmax_deg_per_s));
        amax_cps2_ = static_cast<double>(output_deg_to_counts(amax_deg_per_s2));
        v_plan_ = 0.0;
    }

    /** 设置新目标（计数）；插值位置不动 */
    void set_target(Counts target) { target_ = target; }

    Counts target() const { return target_; }
    Counts position() const { return std::llround(position_); }
    double velocity_counts_per_s() const { return v_plan_; }

    /** 位置贴到某个值，并把目标设成它（启动、hold 用） */
    void snap_to(Counts position)
    {
        position_ = static_cast<double>(position);
        target_ = position;
        v_plan_ = 0.0;
    }

    /** 只把位置跟着某个值走（free 时每帧调用；目标不动） */
    void track(Counts position)
    {
        position_ = static_cast<double>(position);
        v_plan_ = 0.0;
    }

    /** 位置与目标同时平移（改 offset 时用；保证下发的板子目标不变） */
    void relocate(Counts delta)
    {
        position_ += static_cast<double>(delta);
        target_ += delta;
    }

    /** 走一步，返回这一步之后的命令位置（计数，double 以便平滑） */
    double step(double dt)
    {
        const double err = static_cast<double>(target_) - position_;
        const double a_step = amax_cps2_ * dt;
        if (std::fabs(err) <= 1e-9)
        {
            v_plan_ = 0.0;
        }
        else
        {
            // 该踩的最高速度：v² = 2·a·|Δ|（这样才煞得住），再按加速度斜坡逼近
            const double v_cap = std::min(std::sqrt(2.0 * amax_cps2_ * std::fabs(err)), vmax_cps_);
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
        const double step_counts = v_plan_ * dt;
        if (std::fabs(err) <= std::fabs(step_counts))
        {
            position_ = static_cast<double>(target_);
            v_plan_ = 0.0;
        }
        else
        {
            position_ += step_counts;
        }
        return position_;
    }

    bool settled(Counts tol_counts) const
    {
        return std::llabs(target_ - position()) <= tol_counts && v_plan_ == 0.0;
    }

  private:
    double vmax_cps_ = static_cast<double>(output_deg_to_counts(90.0));   // 计数/秒
    double amax_cps2_ = static_cast<double>(output_deg_to_counts(180.0)); // 计数/秒²
    double position_ = 0.0;
    Counts target_ = 0;
    double v_plan_ = 0.0;
};

} // namespace motor
