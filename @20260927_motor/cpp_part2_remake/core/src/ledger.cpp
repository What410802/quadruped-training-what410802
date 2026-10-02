/**
 * @file ledger.cpp
 * @brief Ledger 的实现：每一处"动账"都记一条事件，便于验收时说明这次会话动过几次账。
 */

#include "motor/ledger.hpp"

namespace motor
{

const char* ledger_event_name(LedgerEventKind kind)
{
    switch (kind)
    {
    case LedgerEventKind::kAnchor:
        return "上电锚定";
    case LedgerEventKind::kAlignFix:
        return "区间对齐";
    case LedgerEventKind::kOffsetShift:
        return "偏移改动";
    }
    return "未知事件";
}

Ledger::Ledger(Counts offset) : offset_(offset) {}

void Ledger::anchor(Counts k, double now_s)
{
    const Counts before = turn_base_;
    turn_base_ = k * kCountsPerTurn;
    events_.push_back({LedgerEventKind::kAnchor, k, before, turn_base_, now_s});
}

void Ledger::shift_offset(Counts delta, double now_s)
{
    if (delta == 0)
    {
        return;
    }
    const Counts before = offset_;
    offset_ += delta;
    events_.push_back({LedgerEventKind::kOffsetShift, delta, before, offset_, now_s});
}

void Ledger::align_fix(Counts k, double now_s)
{
    if (k == 0)
    {
        return;
    }
    const Counts before = offset_;
    offset_ -= k * kCountsPerTurn;
    events_.push_back({LedgerEventKind::kAlignFix, k, before, offset_, now_s});
}

} // namespace motor
