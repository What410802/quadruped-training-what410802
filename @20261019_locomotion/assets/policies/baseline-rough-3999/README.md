# baseline-rough-3999

2026-10-20 的 `black-rough` PPO 基线策略（从 flat `baseline-2000` full resume；未改 reward/curriculum/终止设计）。

| 项 | 值 |
|---|---|
| 训练 task | `black-rough`（PPO，45 维单帧 obs） |
| 训练仓库 commit | `nwwolf_mjlab_training_release` `24c7f16` |
| run 目录（远程） | `logs/rsl_rl/black_velocity/2026-10-20_21-24-30_baseline-rough-2000-resume2/` |
| checkpoint | `model_3999.pt`（原始训练由 3 段 run 组成，见 [`../../../docs/training/experiments.md`](../../../docs/10-part1/experiments.md) §3.5） |
| 导出命令 | `.venv/bin/export --task-id black-rough --load-run 2026-10-20_21-24-30_baseline-rough-2000-resume2 --checkpoint model_3999.pt --output-dir ~/rc_work/baseline/exported_rough` |
| `policy.pt` | 770,774 B，sha256 `b34b03e5ae71a5b280ff4e85a6c9976bd4b1c8d7f262a91d95bb0e13221c628a` |
| 契约 | TorchScript actor-only；输入 `[1,45]`；输出 `[1,12]` raw action；`q_target = q_default + 0.25·raw`；Kp=40/Kd=1.2；50 Hz |
| 评测 | **未完成**：逐地形通过率尚未测；训练期 G3 初判不足，见下 |
| Gate | G3 **初判未通过**（当前证据；不是验收策略） |

G3 目前证据（TensorBoard 训练曲线，2026-10-21 读取）：

- 第一段 run 在 3388 iteration 因 `Loss/value=inf` 崩溃；恢复后的最终 run 在 3999 iteration 正常结束，但 200 iteration 内 `Loss/value` 仍出现最高约 `1.95e10` 的尖峰，数值问题没有消失。
- 地形课程最终均值约 `2.0`（首轮记录最高约 `2.49`），没有推进；`stairs_down` 从首轮最高约 `2.50` 掉到 `0.87`，`discrete_obstacles` 约 `1.54`，属于长期卡住。
- 因此这份权重只能作为 **rough 对照/诊断**，不能作为台阶/梅花桩正式训练的“已过 rough 门槛”证据；台阶/梅花桩正式训练门槛见 [`../../../docs/training/eval-protocol.md`](../../../docs/10-part1/eval-protocol.md) §6.1。

> 权重入库策略见 [`../../../docs/training/experiments.md`](../../../docs/10-part1/experiments.md) §5。该策略不是验收策略；后续 rough/台阶/梅花桩与优化实验相对它记录。
