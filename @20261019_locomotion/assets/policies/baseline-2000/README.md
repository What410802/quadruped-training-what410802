# baseline-2000

2026-10-20 的 `black-flat` PPO 基线策略（现有 reward/curriculum/DR，未改训练代码）。

| 项 | 值 |
|---|---|
| 训练 task | `black-flat`（PPO，45 维单帧 obs） |
| 训练仓库 commit | `nwwolf_mjlab_training_release` `24c7f16` |
| run 目录（远程） | `logs/rsl_rl/black_velocity/2026-10-20_18-12-54_baseline-2000/` |
| checkpoint | `model_1999.pt` |
| 训练命令 | 见 [`../../../docs/training/experiments.md`](../../../docs/10-part1/experiments.md) §3.1 |
| 训练时长 | 47:19（4096 envs × 2000 iter） |
| `policy.pt` | 770,774 B，sha256 `ac4652b8c5bc63a12e1e4813270f6a1252ced61df9255b61a2839f222f4b6f71` |
| 契约 | TorchScript actor-only；输入 `[1,45]`；输出 `[1,12]` raw action；`q_target = q_default + 0.25·raw`；Kp=40/Kd=1.2；50 Hz |
| 本地评测 | [`eval-flat.json`](eval-flat.json)，脚本 [`eval_flat.py`](../../../scripts/agent_scripts/eval_flat.py)，场景 `@20261005_ros2/scenes/flat_scene.xml` |
| Gate | G1 条件通过（stand 漂移 0.273 m；其余通过）、G2 通过、G3 rough 初判未通过（[`baseline-rough-3999`](../baseline-rough-3999/README.md)）、G4/G5 通过 |

> 该策略只用于**基线对照**，不是验收策略；后续 rough/台阶/梅花桩与优化实验的对照都相对它记录（见 [`../../../docs/training/experiments.md`](../../../docs/10-part1/experiments.md)）。
