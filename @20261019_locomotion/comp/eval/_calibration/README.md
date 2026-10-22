# 人工标定集（G1 的锚）

目标：≥30 条 rollout，覆盖 8 个障碍 × 成功/失败 × 边界情形，人工只标：
`success/fail + failure_reason`。视频放 `RoboCon/prep.d/videos/`（不入库），本目录只放 `labels.jsonl`。

`labels.jsonl` 一行一条：

```json
{"trial_id": "cal-001", "obstacle": "height_bar", "video": "<prep.d 路径>", "human": {"success": true, "failure_reason": null}, "notes": "从门洞中心通过，杆未落"}
```

用途：
1. judge 与人工标签一致性（默认要求 100%，例外需逐条规则依据）；
2. 盲写第二实现与现有 judge 的逐条比对（`audits/JUDGE_CROSSCHECK.md`）；
3. judge 语义变更后重跑标定。

当前状态：空（G1 阻塞项之一）。
