/**
 * @file ledger.hpp
 * @brief 零点账本：圈基准（turn_base）、软件零点（offset）与账本事件。
 */

#pragma once

#include "motor/counts.hpp"

#include <vector>

namespace motor
{

enum class LedgerEventKind
{
    kAnchor,      // 上电锚定（turn_base = k 个转子圈）
    kOffsetShift, // 标定 / 偏移改动（offset += delta）
};

/** 账本上发生过的一件事（打印与收尾汇总用） */
struct LedgerEvent
{
    LedgerEventKind kind = LedgerEventKind::kAnchor;
    Counts value = 0; // 圈基准 k；或 offset 的增量
    Counts before = 0;
    Counts after = 0;
    double now_s = 0.0;
};

const char* ledger_event_name(LedgerEventKind kind);

/**
 * 位置关系（全部是转子侧计数）：
 *   pos     = raw + turn_base               raw 是板子回帧的整数（上电后 ∈ [0, 32768)）
 *   q       = pos + offset                  软件零点坐标系（q = 0 就是软件零点）
 *   pos_des = q_des − offset − turn_base    收到加、下发减（讲义 §2.5）
 */
class Ledger
{
  public:
    explicit Ledger(Counts offset = 0);

    /** 上电锚定：turn_base = k × 32768（默认 k = 0：接受当前位置） */
    void anchor(Counts k, double now_s);

    Counts raw_to_pos(RawCounts raw) const { return raw + turn_base_; }
    Counts pos_to_q(Counts pos) const { return pos + offset_; }
    Counts raw_to_q(RawCounts raw) const { return pos_to_q(raw_to_pos(raw)); }
    Counts q_to_board(Counts q) const { return q - offset_ - turn_base_; }

    /** 软件零点平移 delta（只动账本；调用方负责把目标同步平移，保证物理目标不动） */
    void shift_offset(Counts delta, double now_s);

    Counts turn_base() const { return turn_base_; }
    Counts offset() const { return offset_; }
    const std::vector<LedgerEvent>& events() const { return events_; }

  private:
    Counts turn_base_ = 0;
    Counts offset_ = 0;
    std::vector<LedgerEvent> events_;
};

} // namespace motor
