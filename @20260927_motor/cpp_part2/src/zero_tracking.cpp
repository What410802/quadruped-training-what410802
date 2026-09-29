/**
 * @file zero_tracking.cpp
 * @brief ZeroTracker 的实现：每一处"动账"都记一条事件，便于验收时说明这次会话动过几次账。
 */
#include "motor_bench/zero_tracking.hpp"

namespace motor_bench
{

void ZeroTracker::AnchorAtStartup(int64_t raw_ticks, int64_t k)
{
    (void)raw_ticks; // 上电首帧只用来"接受当前位置"，k 由调用方给（默认 0）
    turn_base_ = k * ticks::kTicksPerTurn;
    events_.push_back({"上电锚定", k, offset_, offset_, 0.0});
}

int64_t ZeroTracker::AlignTo(int64_t raw_ticks, int64_t want_q_ticks, double wall)
{
    const int64_t before = offset_;
    const int64_t delta = want_q_ticks - RawToQ(raw_ticks);
    if (delta == 0)
    {
        return 0;
    }
    offset_ += delta;
    events_.push_back({"对齐记录值", delta / ticks::kTicksPerTurn, before, offset_, wall});
    return delta;
}

void ZeroTracker::ReanchorAfterOffline(int64_t raw_ticks, int64_t last_pos_ticks, double wall)
{
    // 物理位置没动 ⇒ q 连续：raw + turn_base 保持不变
    const int64_t k = TurnsOfDelta(last_pos_ticks - raw_ticks);
    const int64_t before = turn_base_;
    turn_base_ = k * ticks::kTicksPerTurn;
    if (turn_base_ != before)
    {
        events_.push_back({"离线重锚", k, before, turn_base_, wall});
    }
}

void ZeroTracker::FixJump(int64_t k, double wall)
{
    const int64_t before = offset_;
    offset_ -= k * ticks::kTicksPerTurn;
    events_.push_back({"跳变修正", k, before, offset_, wall});
}

} // namespace motor_bench
