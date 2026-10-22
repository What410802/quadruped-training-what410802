# 人工标定集（G1 的锚）

## 它属于哪个阶段？（用户 2026-10-22 问）

- **C1 评测器标定阶段**（`comp/PLAN.md` 的 C1），即：judge P0 实现完成 → G1 审计通过/冻结之前。
- 时间顺序：C0 契约 → **C1 evaluator + 人工标定 + G1** → C2 baseline 分 → C3 每日 triage/train/eval/score。
- 具体触发点：judge 冻结（本版 V2.1）且预审（BYOK flash×2、pro）通过后、送 Codex G1 终审前后；
  标定结果既是 G1 的证据，也是 judge 回归测试集。
- 你现在**还不需要**标注：等我把 64 条轨迹包（视频+状态+标注表）准备好并通知你，你按表标 `success/fail+原因` 即可，
  预计 2–4 小时；视频放 `RoboCon/prep.d/videos/`（不入库），本目录只放 `labels.jsonl`。

目标：≥64 条 rollout（Part1 32 = 8 障碍×4；Part2 24 = 6 类×4；会话状态 8），覆盖成功/失败/边界情形，
人工只标 `success/fail + failure_reason`。

`labels.jsonl` 一行一条：

```json
{"trial_id": "cal-001", "obstacle": "height_bar", "video": "<prep.d 路径>", "human": {"success": true, "failure_reason": null}, "notes": "从门洞中心通过，杆未落"}
```

**它不是用来训练判定神经网络的。** judge 是规则程序（读仿真接触/位姿，按规则判 success/fail），
人工标签是它的**测试集/ground truth**，用来发现规则误判、做回归、并与盲写第二实现交叉比对。
训练一个学习型 judge 会让评分不可复现、不可审计，也不会被官方接受。

用途：
1. judge 与人工标签一致性（默认要求 100%，例外需逐条规则依据）；
2. 盲写第二实现与现有 judge 的逐条比对（`audits/JUDGE_CROSSCHECK.md`）；
3. judge 语义变更后重跑标定。

当前状态：空（G1 阻塞项之一）。
