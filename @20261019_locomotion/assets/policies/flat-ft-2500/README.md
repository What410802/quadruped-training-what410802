# flat-ft-2500

2026-10-21 的 flat 候选策略：在 `baseline-2000/model_1999.pt` 上继续训练 500 iteration，启用左右 mirror loss（0.1）和 HIM 风格 `foot_clearance`（目标 0.09 m、权重 −0.01）；目标是在不丢 flat 性能的前提下压低 RL/RR 步态不对称。**可作为当前 flat/S1b 候选，但不是最终验收策略。**

| 项 | 值 |
|---|---|
| 训练 task | `black-flat`（PPO，45 维单帧 obs） |
| 训练仓库 | `nwwolf_mjlab_training_release` 基线 commit `24c7f16` + 2026-10-21 工作区改动（foot_clearance / mirror loss / reward safety；未 commit） |
| run 目录（远程） | `logs/rsl_rl/black_velocity/2026-10-21_11-59-36_flat_ft_mirror01_footclear_500/` |
| checkpoint | `model_2498.pt` |
| 初始化 | flat `baseline-2000/model_1999.pt` resume；`--agent.command-curriculum-restore full` |
| 训练命令 | `MUJOCO_GL=egl BLACK_REWARD_CLIP=50 BLACK_MIRROR_LOSS_COEFF=0.1 .venv/bin/train black-flat --env.scene.num-envs 2048 --agent.max-iterations 500 --agent.save-interval 100 --agent.logger tensorboard --agent.resume True --agent.load-run 2026-10-20_18-12-54_baseline-2000 --agent.load-checkpoint model_1999.pt --agent.command-curriculum-restore full --agent.run-name flat_ft_mirror01_footclear_500` |
| 导出 | `.venv/bin/export --task-id black-flat --load-run 2026-10-21_11-59-36_flat_ft_mirror01_footclear_500 --checkpoint model_2498.pt --output-dir ~/rc_work/baseline/exported_flat_ft_mirror01_footclear_500` |
| `policy.pt` | 770,774 B，sha256 `332737933d750815ed5f7bde9863f6f282b29aadc7babe5c698aaed5b41b564b` |
| 契约 | TorchScript actor-only；输入 `[1,45]`；输出 `[1,12]` raw action；`q_target = q_default + 0.25·raw`；Kp=40/Kd=1.2；50 Hz |
| 评测 | [`eval-flat.json`](eval-flat.json)（local `eval_flat.py`，flat scene）、[`eval-gravel.json`](eval-gravel.json)（远程 `black-gravel-flat`，32 envs play）、[`eval-gravel-64.json`](eval-gravel-64.json)（64 envs 复测）、[`eval-free-composite-4.json`](eval-free-composite-4.json)（composite 自由砂砾 zero-shot，4 envs）、[`eval-rough-zero-shot-4.json`](eval-rough-zero-shot-4.json)（`black-rough` 全 rough/台阶套件 zero-shot，4 envs，失败） |

## Flat gate（local `eval_flat.py`，flat scene）

| 段 | 摔倒 | MAE vx | MAE wz | max tilt | 终点 xy |
|---|---|---|---|---|---|
| stand（5 s） | 否 | 0.0039 | 0.0128 | 3.4° | −0.270, 0.050（漂移 0.275 m ≤0.30） |
| fwd-slow | 否 | 0.0459 | 0.0556 | 3.8° | 0.800, 0.040 |
| fwd-nominal | 否 | **0.0687** | 0.0299 | 3.2° | 4.680, 0.170 |
| fwd-fast | 否 | 0.1087 | 0.0440 | 6.6° | 8.910, 0.380 |
| bwd | 否 | 0.0947 | 0.0630 | 4.0° | −1.880, −0.220 |
| lat-pos | 否 | 0.0230 | 0.0587 | 3.6° | −0.240, 2.020 |
| yaw-pos | 否 | 0.0421 | 0.1690 | 4.6° | −0.180, 0.050 |
| combined | 否 | 0.0705 | 0.0442 | 3.3° | −0.510, 4.210 |

G1 的 stand 漂移 0.275 m、fwd-nominal MAE 0.0687；G1/G2/G4/G5 通过（G2 日志的 `vx_min/vx_max` 到 ±2.0；见 [`../../../docs/training/experiments.md`](../../../docs/10-part1/experiments.md)）。

## 地形 zero-shot（2026-10-21）

| 地形 | 规模 | 结果 | 结论 |
|---|---|---|---|
| flat | local gate | 无摔倒；stand 漂移 0.275 m、fwd MAE 0.0687 | 通过 |
| 固定砂砾 `black-gravel-flat` | 64 envs | 摔倒 1.56%（1/64）；0.3/0.5 MAE 0.140/0.133 | S1b-fixed 初版通过 |
| 自由砂砾 composite（6 cm 基座 + 120 自由 + 700 静态、3–8 cm） | 4 envs | **0 摔倒**；0.3/0.5 MAE 0.089/0.049；p95 tilt 4.1°/3.1°；arc 也 0 摔倒 | zero-shot provisional pass；4 envs 单布局，不是正式验收 |
| `black-rough`（7 类：slopes/rough/discrete/stairs up/down） | 4 envs | **max fall 25%**（每段 1/4）；fwd-slow MAE 0.058、fwd-nominal 0.098；fwd-fast p95 27° | **失败**；平地模型不能直接上队内赛/往年综合地形 |

自由砂砾诊断视频：`prep.d/videos/flat_ft_composite_zero_shot.mp4`（本地，不入库；zero-shot，不是训练后结果）。composite 的 4 envs/单布局还不足以替代多 seed/固定布局的正式评测。

## 步态与 S1b

- 0.8 m/s 前进、暖机后 6 s：RL−RR 平均 x 差 **0.051 m**（原始 `model_1999` 为 0.155 m）；RL/RR 接触比例 0.85/0.89，后腿足端最高 z 4.7/4.2 cm；不是完全对称，但拖腿明显缓解。
- `black-gravel-flat` 32 envs play：全段 0 摔倒；0.3/0.5 m/s vx MAE **0.134/0.178**、p95 tilt 8.8°/8.6°。64 envs 复测：fwd-slow 摔倒率 1.56%（1/64，≤5%）、0.3/0.5 m/s vx MAE 0.140/0.133、p95 tilt 7.1°/7.8°；按 [`../../../docs/training/eval-protocol.md`](../../../docs/10-part1/eval-protocol.md) §6.2 初版 S1b **provisional pass**。
- 仍不是最终验收策略：只在 2048 envs、500 iteration fine-tune；没有经过多 seed、正式固定地形/种子评测和 sim2sim。权重入库策略见 [`../../../docs/training/experiments.md`](../../../docs/10-part1/experiments.md) §5。
