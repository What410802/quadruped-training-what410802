/**
 * @file zero_tracking.hpp
 * @brief 零点账本：圈基准、软件零点偏移、以及"什么时候要动账"的三件事。
 *
 * 位置关系（全部是转子侧 tick）：
 *   pos_ticks = raw + turn_base          raw 是板子报的整数（上电后 ∈ [0, 32768)）
 *   q_ticks   = pos_ticks + offset       软件零点：q_ticks = 0 就是 `0` 命令去的地方
 *
 * 三件事（设计与依据见 docs/zero-semantics.md）：
 *   1. AnchorAtStartup()      上电首帧：默认接受当前位置（k = 0）；
 *   2. AnchorTo(raw, ref)     有外部参考（上次记录的位置/已知姿势）时，求最近的整圈 k；
 *   3. ReanchorAfterOffline() 掉线又回来：按"物理位置没动"重新求 turn_base（只动账本，不动
 * offset）。 跳变兜底：FixJump(k) 把 offset 反向补 k 个区间，q 保持连续、物理目标不变。
 */
#pragma once

#include "motor_bench/ticks.hpp"

#include <cstdint>
#include <string>
#include <vector>

namespace motor_bench
{

/** 账本上发生过的一件事（打印 + 收尾汇总用） */
struct ZeroEvent
{
    std::string what;   // "上电锚定" / "离线重锚" / "跳变修正" / "启动检查修正"
    int64_t k = 0;      // 动了几圈（或几个区间）
    int64_t before = 0; // 动作前的 offset（tick）
    int64_t after = 0;  // 动作后的 offset（tick）
    double wall = 0.0;  // 墙钟秒（由调用方填）
};

class ZeroTracker
{
  public:
    /** 上电首帧：接受当前位置为参照（turn_base 保持 k 圈） */
    void AnchorAtStartup(int64_t raw_ticks, int64_t k = 0);

    /**
     * @brief 把"软件零点"对齐到记录值：offset += (want_q − 当前 q)。
     *
     * 用在"上电落在别的候选零点"（启动检查）与运行时的 `fix` 命令：读数和记录值差整数个区间时，
     * 让同一个物理点重新读回记录值。调用方随后要把 q_des 与插值位置一起挪同样的量，
     * 否则驱动板会按那 k 个区间的误差使劲（会真的转过去）。
     *
     * @return 挪了多少 tick（0 = 不用动）
     */
    int64_t AlignTo(int64_t raw_ticks, int64_t want_q_ticks, double wall);

    /** 掉线又回来：物理位置没动 ⇒ 保持 q 不变，重算 turn_base（last_pos 是掉线前最后一次
     * pos_ticks） */
    void ReanchorAfterOffline(int64_t raw_ticks, int64_t last_pos_ticks, double wall);

    /** 运行中的跳变兜底：offset 反向补 k×32768（q 连续、物理目标不变） */
    void FixJump(int64_t k, double wall);

    /** 某个 Δpos 是几圈（最近的整数倍），配合残差判据使用 */
    static int64_t TurnsOfDelta(int64_t delta)
    {
        const int64_t t = ticks::kTicksPerTurn;
        return (delta >= 0 ? delta + t / 2 : delta - t / 2) / t;
    }

    int64_t turn_base() const { return turn_base_; }
    int64_t offset() const { return offset_; }
    int64_t PositionTicks(int64_t raw) const { return raw + turn_base_; }
    int64_t PositionToQ(int64_t pos) const { return pos + offset_; }
    int64_t RawToQ(int64_t raw) const { return PositionToQ(PositionTicks(raw)); }

    /** 发给驱动板的 `pos_des`（板子读数空间）：pos_des = q − turn_base − offset */
    int64_t BoardTicks(int64_t q_ticks) const { return q_ticks - turn_base_ - offset_; }

    void SetOffset(int64_t offset) { offset_ = offset; }
    void ShiftOffset(int64_t delta) { offset_ += delta; }

    const std::vector<ZeroEvent>& events() const { return events_; }

  private:
    int64_t turn_base_ = 0;
    int64_t offset_ = 0;
    std::vector<ZeroEvent> events_;
};

} // namespace motor_bench
