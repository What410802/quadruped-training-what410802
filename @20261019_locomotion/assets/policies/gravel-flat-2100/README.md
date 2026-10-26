# gravel-flat-2100

2026-10-21 的 `black-gravel-flat` 策略：从 flat `baseline-2000/model_1999.pt` resume，训练约 115 iteration 后在 `model_2100` 停止（S1b gate 已通过，未跑满 1000）。**不是最终验收策略**。

| 项 | 值 |
|---|---|
| 训练 task | `black-gravel-flat`（50% flat + 30% 细砾石 + 20% 粗砾石代理，无台阶/离散障碍） |
| 训练仓库 | `nwwolf_mjlab_training_release` 基线 commit `24c7f16` + 2026-10-21 工作区改动（foot_clearance / mirror loss / reward safety / gravel task；未 commit） |
| run 目录（远程） | `logs/rsl_rl/black_velocity/2026-10-21_11-50-05_gravel_flat_from_flat_1000/` |
| checkpoint | `model_2100.pt` |
| 初始化 | flat `baseline-2000/model_1999.pt` resume；`--agent.command-curriculum-restore none`（command 从 ±1 重新起步） |
| 导出 | `.venv/bin/export --task-id black-gravel-flat --load-run 2026-10-21_11-50-05_gravel_flat_from_flat_1000 --checkpoint model_2100.pt --output-dir ~/rc_work/baseline/exported_gravel_flat_2100` |
| `policy.pt` | 770,774 B，sha256 `12f01f7f151b4842293ae16d4fcbd19d83f488a0cb04a8fa3bb8f10c9b5a2326` |
| 契约 | TorchScript actor-only；输入 `[1,45]`；输出 `[1,12]` raw action；`q_target = q_default + 0.25·raw`；Kp=40/Kd=1.2；50 Hz |

## S1b 评测（32 envs，play 模式，随机 terrain level 0–2）

按 [`../../../docs/training/eval-protocol.md`](../../../docs/10-part1/eval-protocol.md) §6.2 初版门槛：

| 指标 | 结果 |
|---|---|
| 摔倒率（全命令段） | 0 |
| 0.3 m/s vx MAE | 0.147 m/s（门槛 ≤0.15，刚过） |
| 0.5 m/s vx MAE | 0.092 m/s（门槛 ≤0.20） |
| 0.3 / 0.5 m/s p95 tilt | 5.3° / 5.9°（门槛 ≤25°） |
| 0.8 m/s（只记录） | 0 摔倒；MAE 未作为硬门槛 |

结论：**S1b provisional pass**；但这是 play 模式、随机地形 level 的 screening，正式 gate 还要固定地形/种子并统计更多 episode。

## 已知限制

- flat 步态仍有左右不对称：在 `black-flat` play 环境测 RL−RR 平均 x 差约 **0.129 m**（RL 0.79 / RR 0.92 接触），比原始 baseline 0.155 m 略好但没有解决；不要当验收策略。
- 只训练约 115 iteration；0.3 m/s 跟踪只是刚过线，速度裕度不足。
- 权重入库策略见 [`../../../docs/training/experiments.md`](../../../docs/10-part1/experiments.md) §5。
