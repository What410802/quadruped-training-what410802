# PPO/BC 线审计（round 1，2026-10-26）

- [`ppo-core-audit-round1.md`](ppo-core-audit-round1.md)：训练/评测核心代码审计（BLOCKED：DR 丢失、resume lr 覆盖、plum 状态奖励等）。
- [`ppo-deploy-audit-round1.md`](ppo-deploy-audit-round1.md)：部署链路与作业脚本审计（BLOCKED：sim 力矩标量、无 Part2 逐档 smoke、导出契约不自足等）。

> 两份报告是 2026-10-26 的只读独立审计原文；修复进度见 [`../history-experiments.md`](../history-experiments.md) §19 与 [`../handoff.md`](../handoff.md) 的"审计闭环"节。round-2 审计在修复完成后进行。
