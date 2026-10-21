# 实验记录

> 所有接受比较的训练/评测都记在这里。原始 TensorBoard 事件与日志在远程机（不入库）；模型权重按 §5 只入精选的 `policy.pt`/`model_*.pt`。入库的是“可追溯的实验记录 + 导出策略 + 评测 JSON + 命令”。协议见 [`eval-protocol.md`](eval-protocol.md)，基线代码/奖励背景见 [`training-baseline.md`](training-baseline.md)。

## 1. 记录规范

每个实验至少记录：任务、训练仓库 commit、训练命令、`num_envs`、`max_iterations`、种子、起止时间、关键曲线（TensorBoard 路径）、最终指标、导出的 `policy.pt` sha256、评测命令与结果文件。未导出/未评测的 run 只记为“训练完成，待评测”。

## 2. Run 总表

| Run | 日期 | task | 初始化 | envs | iters | 训练时长 | 导出 policy sha256 | 状态 |
|---|---|---|---|---|---|---|---|---|
| `baseline-2000` | 2026-10-20 | `black-flat`（PPO，45 维） | 从零 | 4096 | 2000 | 47:19 | `ac4652b8c5bc63a12e1e4813270f6a1252ced61df9255b61a2839f222f4b6f71` | 训练完成；flat gate 通过（G1 校准为 0.30 m 后通过，G2/G4/G5 通过） |
| `baseline-rough-2000` | 2026-10-20 | `black-rough`（PPO，45 维） | flat `model_1999.pt` full resume | 4096 | 2000（→ 3999） | 1:17 后崩溃于 3388/3999 | 待导出 | 见 §3.5：PPO update 中 `normal expects std >= 0` 断言 + Warp CUDA 710；最后 checkpoint `model_3350.pt` |
| `baseline-rough-2000-resume` | 2026-10-20 | `black-rough`（继续） | rough `model_3350.pt` resume | 4096 | 650（→ 3999） | 到 3826/4000 再次崩溃（同一 `std >= 0` 断言） | 待导出 | 最后 checkpoint `model_3800.pt`；见 §3.5 |
| `baseline-rough-2000-resume2` | 2026-10-20 | `black-rough`（继续） | rough `model_3800.pt` resume | 4096 | 200（→ 3999） | **10:52，正常完成**（3805–3867 有 13 次数值异常但自愈） | `b34b03e5ae71a5b280ff4e85a6c9976bd4b1c8d7f262a91d95bb0e13221c628a` | 最后 checkpoint `model_3999.pt`；G3 初判未通过；权重在 [`../assets/policies/baseline-rough-3999/`](../../assets/policies/baseline-rough-3999/README.md) |
| `asym_base_200` | 2026-10-21 | `black-flat` | 从零 | 2048 | 200 | 3:19 | 未导出 | 步态 A/B 对照；reward 仍 10 项 |
| `asym_mirror01_200` | 2026-10-21 | `black-flat` | 从零 | 2048 | 200 | 3:48 | 未导出 | mirror loss 0.1；步态 A/B |
| `asym_mirror01_500` | 2026-10-21 | `black-flat` | 从零 | 2048 | 500 | 9:24 | 未导出 | mirror loss 0.1；步态 A/B |
| `asym_mirror01_footclear_500` | 2026-10-21 | `black-flat` | 从零 | 2048 | 500 | 9:37 | 未导出 | mirror 0.1 + foot_clearance；步态 A/B |
| `gravel_flat_from_flat_1000` | 2026-10-21 | `black-gravel-flat` | flat `model_1999` resume；command range 重置 | 2048 | 1000（→ 2115 后停止） | 约 10 min | `12f01f7f151b4842293ae16d4fcbd19d83f488a0cb04a8fa3bb8f10c9b5a2326` | `model_2100` 在 32 envs 过 S1b（0 摔倒，0.3/0.5 MAE 0.147/0.092）；未跑满 1000，暂不作为最终权重 |
| `rough_safety_200` | 2026-10-21 | `black-rough` | rough `model_3999` resume | 2048 | 200（→ 4199） | 13:38 完成 | 未导出 | 200/200 无崩溃；`Loss/value` 4 次尖峰最高 1.89e4，均回落；clamp 降低后果但未消除 |
| `flat_ft_mirror01_footclear_500` | 2026-10-21 | `black-flat` | baseline `model_1999` resume | 2048 | 500（→ 2499） | 13:00 | `332737933d750815ed5f7bde9863f6f282b29aadc7babe5c698aaed5b41b564b` | 旧 flat 基线上继续训练，mirror 0.1 + foot clearance；权重在 [`../assets/policies/flat-ft-2500/`](../../assets/policies/flat-ft-2500/README.md) |
| `gravel_free_stable100` | 2026-10-21 | `black-gravel-free` | flat-ft resume；稳定化石块 | 32 | 100 | 1:48 | 未导出 | 无 NaN；episode length 998；用于调试 free task |
| `gravel_free_v2_700` | 2026-10-21 | `black-gravel-free` | 从 stable/v2 链继续；24 石块、中心清空 | 32 | 500 | 5:25 | `9b5dc867efe6b62155b3aa8734890b8d1dbd791526fd67d39d262239e73fb178` | **旧稀疏布局，已作废（仅历史）**；dense80 结果见 §3.10 |
| `gravel_free_v2_900` | 2026-10-21 | `black-gravel-free` | v2_700 resume | 32 | 200 | 3:30 | 未导出 | 16 envs 反而退化，不采用 |

## 3. `baseline-2000`（2026-10-20）

### 3.1 配置与命令

- 训练仓库：`nwwolf_mjlab_training_release` commit `24c7f16`（未做任何代码/奖励/课程修改）
- 环境：远程 `bis-ms7e56`（RTX 5060 Ti 16 GB），原生 uv；`MUJOCO_GL=egl`
- 命令：

```bash
MUJOCO_GL=egl .venv/bin/train black-flat \
  --env.scene.num-envs 4096 --agent.max-iterations 2000 \
  --agent.logger tensorboard --agent.run-name baseline-2000
```

- 默认配置：`RewardScales` 与 10 项奖励、command curriculum、DR、终止均保持训练仓库默认（[`training-baseline.md`](training-baseline.md)）；seed=42；episode 20 s。
- run 目录（远程）：`~/rc_work/nwwolf_mjlab_training_release/logs/rsl_rl/black_velocity/2026-10-20_18-12-54_baseline-2000/`
- 日志（远程）：`~/rc_work/baseline/flat_baseline_2000.log`

### 3.2 训练结果（iteration 1999/2000）

| 指标 | 值 |
|---|---|
| 总步数 / 吞吐 | 524,288,000 steps / 185,869 steps/s |
| 训练时长 | 47:19（1.41–1.57 s/iteration） |
| Mean reward | 23.01 |
| Mean episode length | 1000.0（满 20 s） |
| Mean action std | 0.29 |
| `Metrics/twist/error_vel_xy` | 0.3150 |
| `Metrics/twist/error_vel_yaw` | 0.3913 |
| curriculum `vx_min/vx_max` | **-2.0 / +2.0（已扩到上限）** |
| curriculum `ema_low/ema_high` | 0.8988 / 0.8758 |
| curriculum `low_ratio/high_ratio` | 0.9008 / 0.8867 |
| `Episode_Termination/illegal_contact` | 0.0312 |
| `Episode_Termination/stuck` | 0.0 |
| `Episode_Termination/time_out` | 4.3125 |
| Track reward（linear / angular） | 0.8912 / 0.4239 |

### 3.3 导出与本地评测

- 导出（CPU）：`.venv/bin/export --task-id black-flat --load-run 2026-10-20_18-12-54_baseline-2000 --checkpoint model_1999.pt --output-dir ~/rc_work/baseline/exported`；元数据 `actor_frame_dim=45, actor_history_length=1, action_dim=12`。
- 入库产物：[`../assets/policies/baseline-2000/policy.pt`](../../assets/policies/baseline-2000/policy.pt)（770,774 B）、[`eval-flat.json`](../../assets/policies/baseline-2000/eval-flat.json)。
- 评测命令（本机，pixi 环境，physics 5 ms / policy 20 ms，Kp=40/Kd=1.2，q_target=q_default+0.25·a）：

```bash
pixi run python @20261019_locomotion/scripts/agent_scripts/eval_flat.py \
  --json @20261019_locomotion/assets/policies/baseline-2000/eval-flat.json
```

- 评测场景：`@20261005_ros2/scenes/flat_scene.xml`；每段先固定 PD 稳定 1 s、零指令暖机 1 s，再进入命令段；`mae_*` 为命令段内平均绝对误差。

| 段 | cmd (vx,vy,wz) | 摔倒 | MAE vx | MAE vy | MAE wz | 最大 tilt | 终点 xy | rms Στ | action rate |
|---|---|---|---|---|---|---|---|---|---|
| stand | 0, 0, 0 | 否 | 0.0049 | 0.0030 | 0.0040 | 4.37° | -0.270, 0.037 | 12.04 | 0.0001 |
| fwd-slow | 0.3, 0, 0 | 否 | 0.0340 | 0.0290 | 0.0503 | 1.68° | 0.817, -0.027 | 14.97 | 0.1659 |
| fwd-nominal | 0.8, 0, 0 | 否 | 0.0668 | 0.0465 | 0.0293 | 4.98° | 4.709, 0.246 | 17.82 | 0.4599 |
| fwd-fast | 1.5, 0, 0 | 否 | 0.1089 | 0.0696 | 0.0427 | 5.76° | 8.911, 0.353 | 20.68 | 0.9495 |
| bwd | -0.5, 0, 0 | 否 | 0.0648 | 0.0231 | 0.0495 | 4.00° | -1.995, -0.200 | 15.27 | 0.2601 |
| lat-pos | 0, 0.5, 0 | 否 | 0.0137 | 0.0589 | 0.0601 | 3.47° | -0.182, 1.950 | 17.84 | 0.3667 |
| yaw-pos | 0, 0, 0.5 | 否 | 0.0354 | 0.0390 | 0.1632 | 7.57° | -0.239, 0.036 | 13.33 | 0.0500 |
| combined | 0.8, 0.3, 0.4 | 否 | 0.0563 | 0.0574 | 0.0437 | 6.34° | -0.685, 3.997 | 17.93 | 0.5643 |

### 3.4 Gate 结论

| Gate | 结论 | 说明 |
|---|---|---|
| G1 flat 基本可用 | **通过** | 所有段无摔倒；fwd-nominal MAE vx 0.0668、wz 0.0293（阈值 0.25 / 0.20）通过；stand 5 s 终点漂移 0.273 m，按 calibrate 后的 0.30 m 阈值通过（初版 0.15 m 过严，理由见下）。 |
| G2 command curriculum 推进 | **通过** | `vx_min/vx_max` 已到 ±2.0（上限），ema_low/high ≈0.90/0.88。 |
| G3 rough 可跑 | **初判未通过** | terrain level 最终均值约 2.0、未推进；`stairs_down` 0.87、`discrete_obstacles` 1.54 长期卡住；最终 run 的 `Loss/value` 仍有约 1.95e10 尖峰。逐地形通过率尚未测。详见 [`../assets/policies/baseline-rough-3999/`](../../assets/policies/baseline-rough-3999/README.md)。 |
| G4 导出/回放 | **通过** | TorchScript 导出 PASS；45 维输入/12 维输出；本地评测可重复加载并跑完命令 suite。 |
| G5 无异常 | **通过** | 训练无 NaN/崩溃；评测无异常退出。 |

关于 stand 漂移的处理建议（尚未执行）：

- 该漂移是“零指令下缓慢后退”，不是摔倒；训练没有位置保持奖励，零指令速度误差本身已很小（0.0049 m/s），说明 0.15 m 的初版阈值偏严。
- 若不接受，按“少量调参、不改变设计”的边界，可只调现有 `standing_fraction`（0.10→0.15/0.20）重训一次 2000 iteration；不改 reward/终止/课程类型。**当前不重训**，待你确认 gate 是否把 stand 阈值放宽到 0.30 m，或做这一次 standing 调参。

### 3.5 `baseline-rough-2000` 崩溃与恢复（2026-10-20）

- 第一轮：19:21 启动，约 3.28 s/iteration；到 **iteration 3388/3999** 时崩溃，已耗时 1:17。
- 报错顺序：PyTorch CUDA kernel `_assert_async_cuda_kernel: Assertion 'normal expects all elements of std >= 0.0' failed` → traceback 在 `rsl_rl/algorithms/ppo.py` 的 `update()` → 随后 Warp 报 `CUDA error 710: device-side assert triggered`。
- 解读：`std >= 0` 是末端症状，不是根因；事件文件里崩溃前约 90 iteration 已有 `action_rate_l2/smoothness` 巨大负值 → `Loss/value` 1e4/1e8/1e31 → `inf` → NaN 的链条；详见 [`training-health.md`](training-health.md) §3。flat 训练未出现。并发录像是 20:33 才开始，晚于第一次异常 20:31:39，故不能归因于录像；录像期间只是拖慢了 iteration。
- 最后 checkpoint：`model_3350.pt`（run `2026-10-20_19-21-04_baseline-rough-2000`）。
- 第一次恢复：从 `model_3350.pt` resume，追加 650 iteration（目标仍是 3999），run `baseline-rough-2000-resume`；未改 reward/curriculum/终止设计。该轮在 **3826/4000** 再次以同样的 `normal expects std >= 0` 断言 + Warp CUDA 710 崩溃，最后 checkpoint `model_3800.pt`。
- 第二次恢复：从 `model_3800.pt` resume 200 iteration（`baseline-rough-2000-resume2`），2026-10-20 21:24–21:35，10:52 正常跑完 3999；期间 3805–3867 有 13 次数值异常但未出现 `inf`，之后自愈；最后保存 `model_3999.pt`。未改 reward/curriculum/终止设计。
- 结论：rough 最后是“正常完成但质量不足”；数值不稳定与地形课程卡住两个问题已记录到 [`training-health.md`](training-health.md)。模型已导出（sha256 `b34b03e5…`，见 [`../assets/policies/baseline-rough-3999/`](../../assets/policies/baseline-rough-3999/README.md)）；G3 初判未通过，逐地形通过率待补测，再决定是否按数值安全网/地形拆分做少量重训。
- 训练崩溃时 GPU 已恢复健康（`nvidia-smi` 正常），新进程重新初始化 Warp 后正常。

### 3.6 视频记录

- 内置 `play --video` 生成过 5 个样例（默认相机/调试标记，保留作对比）。
- 补了 `render_training_video.py`：跟踪相机 + 打开碰撞组 + 关闭 sensor debug；command 线速度/角速度箭头按高度错开（避免同一位置互相遮挡）；生成 `flat_clean_model_1999.mp4`、`flat_clean_model_1999_stagger.mp4`、`rough_clean_model_3800.mp4`，并用 `overview` 生成 flat/rough 的 7-env 全局静态图。
- 所有视频/全局图暂存在远程 `~/rc_work/videos/`（本地 `prep.d/videos/`），不入库；图例、代码分布与原因见 [`visualization.md`](visualization.md)。

### 3.7 flat 基线步态体检（2026-10-20）

目的：确认视频里“左后腿总在右后腿前”和“旋转前进时本体 yaw 超前”的现象。

- 方法：`black-flat` 的 `model_1999.pt`，分别在（a）本地 `eval_flat.py` 的 flat_scene（补训练模型 joint damping/armature/frictionloss）和（b）训练环境 `ManagerBasedRlEnv` 的 `black-flat` 上跑恒定指令；先 1 s 零指令暖机，再记录 6 s。
- 参考系：以 `trunk` body 为原点，前向 x，左 y；FFT/接触只用足端 world z 判断近似接触（<0.035 m）。

| 腿 | 本地 eval 平均 x [m] | 本地接触比例 | 训练环境平均 x [m] | 训练环境接触比例 |
|---|---|---|---|---|
| FL | +0.173 | 0.847 | +0.175 | 0.84 |
| FR | +0.163 | 0.980 | +0.162 | 1.00 |
| RL | −0.261 | 0.853 | −0.265 | 0.84 |
| RR | **−0.423** | **1.000** | **−0.422** | **1.00** |

- **确认**：左后（RL）比右后（RR）平均靠前 **0.155–0.161 m**；RR 几乎全程保持“接触”，RL 有正常抬腿；前腿基本对称。训练环境和本地部署模型给出一致结果，排除“只是本地评测模型造成的假象”。
- 已核对：policy action order = FL→FR→RL→RR（`env_cfgs.py` 的 `BLACK_ACTION_TERM_ORDER`）、joint obs order 同序、模型左右腿关节范围/位置镜像；未发现动作/观测的顺序错位。policy 最后一层 bias 的 RL/RR 组也明显不对称（RL hip/thigh/calf ≈ −0.044/−0.053/−0.054；RR ≈ −0.023/−0.105/−0.086），说明是学到的非对称姿态，而不是固定 offset。
- 目前更像 **PPO 无对称约束下的 symmetry breaking / 局部最优**：右后腿拖地、左后腿承担更多摆动；不是已经定位到某行代码 bug。下一步需要不同 seed 对照 + 对称性奖励/mirror augmentation 才能确认是优化问题还是模型/奖励有隐藏偏向。

### 3.8 yaw：躯干朝向 vs 实际运动方向（2026-10-20 补测）

用户指出“旋转前进时躯干朝向角看起来超前约 30°”。这里把 **trunk world yaw** 与 **实际速度的 world heading** 分开量：`sideslip = wrap(ψ_trunk - atan2(v_y_w, v_x_w))`（正值表示躯干朝向在运动方向左侧/逆时针超前）。训练环境 `model_1999`，恒定命令，暖机后记录 2.5 s（`black-flat`，standing env 已关闭）：

| 命令 (vx, vy, wz) | 躯干 yaw 跟踪误差均值 | sideslip 均值 | sideslip 标准差 | sideslip p05/p95 | 机体系速度均值 |
|---|---|---|---|---|---|
| 0.8, 0, 0.3 | −0.016 rad | **−2.0°** | 5.8° | −13.6° / +3.5° | 0.765, 0.016 |
| 0.8, 0, 0.5 | −0.019 rad | **−2.0°** | 4.7° | −7.9° / +3.3° | 0.769, 0.020 |
| 0.8, 0, 0.8 | −0.017 rad | **−2.2°** | 5.8° | −10.0° / +3.9° | 0.764, 0.019 |
| 0.8, 0, 1.0 | −0.014 rad | **−2.7°** | 6.3° | −12.5° / +3.0° | 0.753, 0.024 |
| 0.5, 0, 0.5 | −0.041 rad | **−1.1°** | 5.0° | −10.7° / +5.4° | 0.485, 0.005 |
| 0.5, 0, 1.0 | −0.032 rad | **−3.0°** | 7.9° | −19.6° / +6.0° | 0.477, 0.016 |
| 1.0, 0, 0.5 | −0.003 rad | **−1.6°** | 3.6° | −6.8° / +2.8° | 0.951, 0.019 |
| 0.5, **0.3**, 0.5 | −0.031 rad | **−30.0°** | 3.7° | −36.7° / −23.6° | 0.454, **0.260** |
| 0.8, **−0.3**, 0.5 | +0.021 rad | **+18.0°** | 4.1° | +11.5° / +22.0° | 0.777, **−0.262** |

结论：

- **纯前进 + 转向（vy = 0）时没有 30° 的持续超前**：sideslip 均值只有 −1°~−3°，p95 约 +3°~+6°；躯干 yaw 对命令积分的误差也只有约 0.02–0.04 rad。
- **出现 ~30° 的是带横向速度的命令**：`(0.5, 0.3, 0.5)` 的 sideslip 恰好约 −30°，而 `atan2(0.3, 0.5) = 31.0°`；`(0.8, −0.3, 0.5)` 的 +18° 也接近 `atan2(−0.3, 0.8) = −20.6°`（符号按 body 朝向与运动方向定义）。这不是 yaw 跟踪异常，而是**训练命令是 body-frame 速度**：`vy≠0` 就是横移，躯干朝向本来就会与运动方向差 `atan2(vy, vx)`，视频里看起来像“摆尾/斜着走”。
- 所以“30°”更可能是命令本身包含横向分量（或手动端的 vx/vy 与 body/world 坐标系转换不一致），不是 `track_angular_velocity_z` 的奖励 bug；该公式（body-frame 角速度、sigma denominator）与契约一致。
- 仍待确认：用户看到的具体命令/视频段。如果当时 **vy = 0** 仍稳定出现 30°，那才需要继续查命令坐标系/奖励；请给出 `vx, vy, wz` 或对应片段，我按同段复测。

### 3.9 左右步态不对称与 foot clearance A/B（2026-10-21）

背景：`model_1999` 的 RL 比 RR 平均靠前 0.155 m、RR 接触 1.00 vs RL 0.84；此前只定位到“倾向 PPO symmetry breaking”，没有改训练代码。2026-10-21 在训练仓库加了两个可关的开关：

- **mirror loss**：RSL-RL 自带 `Symmetry` 扩展，对 actor 的 45 维观测/12 维动作做左右镜像；只做 loss，不做 data augmentation（critic 的 height_scan 镜像未实现）。环境变量 `BLACK_MIRROR_LOSS_COEFF`，默认 0。
- **foot_clearance**：HIM 论文 Table 5 的摆动腿离地项，目标 0.09 m、权重 −0.01；`rewards.py:foot_clearance`，只对水平速度非零的足端施加高度误差惩罚。

筛选 run（2048 envs，从零训练，同一 seed 42；后腿指标为 0.8 m/s 前进、暖机 2 s 后 6 s 的均值）：

| run | mirror coeff | foot clearance | RL−RR 平均 x [m] | 后腿接触（RL/RR） | 后腿足端最高 z（RL/RR） |
|---|---|---|---|---|---|
| `asym_base_200` | 0 | 否 | **0.255** | 0.953 / 1.000 | 4.1 / 2.1 cm |
| `asym_mirror01_200` | 0.1 | 否 | **0.047** | 1.000 / 1.000 | 2.4 / 2.9 cm |
| `asym_mirror01_500` | 0.1 | 否 | **0.014** | 1.000 / 0.993 | 3.1 / 3.7 cm |
| `asym_mirror01_footclear_500` | 0.1 | 是 | **0.006** | 0.937 / 0.987 | 4.5 / 5.1 cm |
| `baseline-2000` `model_500`（4096 envs 旧基线） | 0 | 否 | 0.182 | 0.837 / 1.000 | 4.4 / 2.4 cm |
| `baseline-2000` `model_1999`（旧基线，原始） | 0 | 否 | 0.155 | 0.84 / 1.00 | 未逐帧统计 |
| `flat_ft_mirror01_footclear_500` `model_2498` | 0.1 | 是 | **0.051** | 0.85 / 0.89 | 4.7 / 4.2 cm |

结论（筛选阶段，不是最终 gate）：

- **mirror loss 单独会把 x 差压到接近 0，但会把后腿压成两条都贴地**（200/500 iteration 两者接触都约 1.00，足端最高 <4 cm）；这说明“对称但拖腿”的退化解是真实风险。
- **foot clearance + mirror loss 在 500 iteration 同时把 x 差压到 0.006 m，后腿足端最高恢复到 4.5/5.1 cm，接触也不再是两条都 1.00**。这支持继续用组合项，而不是单独用 mirror loss。
- 仍缺少 `footclear-only` 的 500 iteration 对照（跑到约 100/500 时因排队让给砾石 gate 训练而停止）；需要补跑后才能区分“clearance 单独是否足够”。
- mirror loss 的系数只筛了 0.1；0.03/0.01 和 data augmentation 仍未测。

复现命令（训练仓库工作区，注意这些改动尚未 commit）：

```bash
MUJOCO_GL=egl BLACK_REWARD_CLIP=50 BLACK_MIRROR_LOSS_COEFF=0.1 \
  .venv/bin/train black-flat --env.scene.num-envs 2048 \
  --agent.max-iterations 500 --agent.save-interval 100 \
  --agent.logger tensorboard --agent.run-name asym_mirror01_footclear_500
```

**从旧 flat 基线 fine-tune 的结果（2026-10-21）**：`flat_ft_mirror01_footclear_500` 从 `baseline-2000/model_1999.pt` resume 500 iteration（mirror 0.1 + foot_clearance）。最终 `model_2498`：

- flat gate：stand 漂移 0.275 m（≤0.30）、fwd-nominal MAE vx 0.0687、全段无摔倒；G1/G4/G5 通过（G2 沿用 baseline 曲线）。
- 步态：RL−RR 平均 x 差 **0.051 m**（原 0.155 m）、接触 0.85/0.89、后腿足端最高 4.7/4.2 cm；仍不是完全对称，但比原 baseline 明显改善，且没有像 mirror-only 那样把后腿压成两条都贴地。
- S1b：32 envs、0 摔倒、0.3/0.5 m/s vx MAE 0.134/0.178、p95 tilt 8.8°/8.6°，provisional pass。
- 权重：[`../assets/policies/flat-ft-2500/`](../../assets/policies/flat-ft-2500/README.md)。这比 B 的 500-iteration 从零策略更适合作为当前 flat 候选，因为保留了原 baseline 的高速/跟踪能力。

### 3.9.1 平地 + 砂砾 S1b 评测（2026-10-21）

地形 task：`black-gravel-flat` = 50% flat + 30% 细砾石（±0.0125 m 量级起伏）+ 20% 粗砾石（±0.01 m、随难度缩放），无台阶/离散障碍；play 模式，8 envs，每段 3–4 s：

8 envs 初测：

| 策略 | 0.3 m/s 摔倒/最大 tilt | 0.5 m/s 摔倒/最大 tilt | 0.8 m/s 摔倒/最大 tilt | 0.5 m/s vx MAE |
|---|---|---|---|---|
| flat `model_1999` | 0 / 9.1° | 0 / 12.8° | 0 / 25.4° | 0.085 |
| mirror+footclear 500 | 0 / 14.2° | 0 / 9.1° | 0 / 11.2° | 0.165 |

32 envs 复测（每段 3–4 s；`p95` 为整段所有 env/step 的 95 分位，`max` 为离群最大值）：

| 策略 | 0.3 m/s 摔倒 / p95 tilt / vx MAE | 0.5 m/s 摔倒 / p95 tilt / vx MAE | 0.8 m/s 摔倒 / p95 tilt / vx MAE |
|---|---|---|---|
| flat `model_1999` | 0 / 9.4° / 0.127 | 0 / 7.9° / 0.128 | 0 / 8.5° / 0.200 |
| mirror+footclear 500 | 0 / 9.5° / 0.089 | 0 / 7.8° / 0.162 | 0 / 8.2° / 0.199 |

按 [`eval-protocol.md`](eval-protocol.md) §6.2 的初版 S1b 门槛（摔倒 0、0.3/0.5 m/s vx MAE ≤0.15/0.20、p95 tilt ≤25°），**两版都 provisional pass**；flat 策略 zero-shot 已能过，500 iteration 的 mirror+footclear 也没有明显回归（0.5 m/s 跟踪从 0.128 到 0.162，仍在线内）。这说明当前 mild gravel 代理不是“必摔”门，不能拿它区分策略好坏；砾石训练的意义主要是增加裕度、覆盖更高速度和更粗砾石，而不是把“不会走”变成“会走”。

训练后 checkpoint：`gravel_flat_from_flat_1000` 从 flat `model_1999` resume，只训练约 115 iteration（`model_2100`，之后因 gate 已过停止），32 envs 评测为 **0 摔倒、0.3/0.5 m/s vx MAE 0.147/0.092、p95 tilt 5.3°/5.9°**，也 provisional pass；p95 tilt 明显低于两版 flat 策略，但 0.3 m/s 跟踪只是刚过 0.15 线。这个 checkpoint 的 flat 步态仍有 RL−RR 0.129 m 的不对称，不能当最终验收策略。

64 envs 复测 `flat-ft-2500`（flat fine-tune，见 §3.9）：fwd-slow 摔倒率 **1.56%（1/64）**、0.3/0.5 m/s vx MAE **0.140/0.133**、p95 tilt 7.1°/7.8°，provisional pass；因此当前最适合做 S1b 候选的是 `flat-ft-2500`，不是 gravel-2100。

需要保留的保留意见：
- 这是 play 模式、随机 terrain level 0–2、32 envs 的 screening；正式 gate 应固定 level/命令/种子并统计更多 episode；
- flat 策略的 vx MAE 在 0.8 m/s 段已到 0.200，说明它接近自己的速度上限；0.8 m/s 只记录，不作为 S1b 硬门槛；
- 后腿不对称/拖地仍在 flat 策略上存在，S1b 门槛不检查它；它属于 H4/步态质量，不能因为“过了 S1b”就忽略。

### 3.10 自由关节砂砾（S1b-free，2026-10-21）

按用户要求，S1b 必须同时覆盖固定和自由关节砂砾；固定用 `black-gravel-flat` 批量预训练，自由用 `black-gravel-free` 小 batch（16–64 envs）微调。自由 task 在 flat 场景里通过 `scene.spec_fn` 加**抬高石床（6 cm 基座 + 6 cm 低 curb）+ 700 静态预沉降石 + 120 自由碎石子**（碎石 3–8 cm、随机椭球；自由/静态/合计投影 union 11.5%/58.4%/63.2%；6 cm 来自独立踩入实验 p95 5.3 cm）；实现见 [`../terrain/gravel-feasibility.md`](../terrain/gravel-feasibility.md) §6。

**2026-10-21 晚用户审查后修正**：旧 24 石块/带围墙布局过稀；80 块 15–19 cm 大石块也不符合实际 3–10 cm 碎石尺寸，只能作木块/过渡参考。两者都不作为 S1b-free 证据；新 composite 设计已完成但训练/评测未完成，历史表保留：

当前结果（play 模式、固定命令序列；dense80 主要看 16 envs）：

| 策略 | 训练 | 摔倒率 | 0.3 / 0.5 m/s vx MAE | p95 tilt（fwd-slow/fwd-nominal） | 结论 |
|---|---|---|---|---|---|
| `flat-ft-2500` | 无 free 训练 | 12.5%（8 envs） | 0.251 / 0.356 | — | 未过 |
| `gravel_free_ft200` `model_2697` | 32 envs × 200 iter | 6.25% | 0.189 / 0.227 | 175°（一次翻倒）/ 8.3° | 改善但仍未过 |
| `gravel_free_ft500` | 32 envs × 再 300 iter | — | — | — | 旧 40 石块版本的 300 iter 在 2883 因 NaN 崩溃；改为 32 石块 + 接触过滤/阻尼后重跑 |
| `gravel_free_stable100` `model_2899` | 32 envs × 100 iter（32 石块稳定版） | 6.25% | **0.143 / 0.167** | 45.6°（一次翻倒）/ 7.6° | 跟踪已进 S1b 线，但摔倒率仍略超 5% |
| `gravel_free_stable400` `model_3198` | 32 envs × 再 300 iter（旧 32 石块布局） | 12.5% | 0.127 / 0.168 | 175°（翻倒）/ 175° | 训练 mean reward 20.9，但评测反而不稳；旧布局中心留空只有 0.42 m，stand/fwd 有随机翻倒 |
| `gravel_free_v2_200` `model_3397` | 32 envs × 200 iter（24 石块、中心 0.65 m 清空、contact filter/damping） | 6.25% | 0.185 / 0.186 | 12.3° / 7.1°（翻倒在 fwd-fast/lat） | 0.3 m/s 仍 0.185；继续 500 iter |
| `gravel_free_v2_700` `model_3896` | 32 envs × 再 500 iter | **0%**（16 envs）；32 envs 0 | 0.166 / 0.154（16）；**0.129 / 0.084（32）** | 16 envs 9.4°/5.3°；32 envs 3.1°/2.8° | **32 envs provisional pass**；16 envs 的 0.3 略高，说明布局/批量方差仍大；权重 [`../assets/policies/free-gravel-v2-700/`](../../assets/policies/free-gravel-v2-700/README.md) |
| `gravel_free_v2_900` `model_4095` | 32 envs × 再 200 iter | 6.25%（16 envs） | 0.128 / 0.196 | 15.6° / 28.1° | 旧稀疏布局；已作废 |
| `free_dense80_ft100b` `model_3995` | 16 envs × 100 iter（80 块 15–19 cm 大石块） | 0% | 0.077/0.124 | 3.1°/2.9° | **大石块过渡结果，尺寸不符实际碎石；仅作木块参考，不作 S1b-free 证据** |
| `free_composite_ft100` | 4 envs × 100 iter（抬高石床 + 3–8 cm 碎石 120 自由 + 700 静态） | 未完成 | — | — | 820 石体/每 world，成本高；需先测吞吐/优化静态层 |
| **`flat_ft_composite_zero_shot`** | 4 envs play（零训练） | **0%** | **0.089 / 0.049** | **4.1° / 3.1°** | composite 上 flat-ft **zero-shot provisional pass**；4 envs 单布局，需多 seed/固定布局；视频 `prep.d/videos/flat_ft_composite_zero_shot.mp4` |


解读：

- 自由石块明显比固定 heightfield 代理难：flat-ft zero-shot 在 free task 上 12.5% 摔倒，固定 task 是 0–1.56%；说明“固定砂砾能过”不能替代 free 砂砾。
- 自由 task 旧 40 石块版本在训练到 2883 iteration 时出现 NaN（`check_nan` 捕获 actor obs）；原因是石块初始穿透地面/石块-石块大接触。已改为 32 石块、初始 z 抬离地面、free joint damping、`contype=2/conaffinity=1` 关闭石-石接触，并只在训练中加 `bad_orientation` 终止；新稳定版 100 iteration 无 NaN，mean reward 20.9、episode length 998。
- dense80（80 块 15–19 cm 大石块）的 0 摔倒结果只说明“大块/整片石”可走，**不符合实际碎石 3–10 cm**；已降级为木块/过渡参考，不作 S1b-free 证据。
- 新 composite（抬高石床 + 120 自由 3–8 cm + 700 静态 3–8 cm，6 cm 基座来自踩入实验 p95 5.3 cm，合计覆盖 63.2%）尚未完成训练/评测；820 石体/每 world，S1b-free 仍需先测吞吐/优化静态层。
- 视频：`free_dense80_commands.mp4`（本地 `prep.d/videos/`，不入库），可看狗在 80 石块层上行走、从石层走到平面；含弧线前进段。

### 3.11 可视化闭环诊断（2026-10-21）

新增 [`render_policy_commands.py`](../../scripts/agent_scripts/render_policy_commands.py)：固定 `stand → fwd 0.3/0.8/1.5 → bwd −0.5 → lat +0.5 → yaw +0.5 → combined` 序列，跟踪相机、关 sensor debug、保留 command 箭头，输出 mp4 + JSON。已生成（远程 `~/rc_work/videos/`，本地 `prep.d/videos/`，不入库）：

| 视频 | 策略/场景 | 用途 |
|---|---|---|
| `flat_ft_flat_commands_clean.mp4` / `_v2.mp4` | `flat-ft-2500` / black-flat | flat 全命令（v2 含 arc-left/right，箭头错开） |
| `flat_ft_gravel_fixed_commands.mp4` / `_v2.mp4` | `flat-ft-2500` / black-gravel-flat | 固定砾石地形；v2 含弧线 |
| `gravel_free_ft200_commands.mp4` | 旧自由石块布局（历史） | 推挤/打滑/翻倒 |
| `free_dense80_commands.mp4` | dense80 `model_3995` / black-gravel-free | 旧大石块，历史/木块参考 |
| `flat_ft_composite_zero_shot.mp4` | `flat-ft-2500` / composite free gravel | **最新 composite 石床上的 zero-shot 命令序列**（不是训练后）；0 摔倒 provisional |
| `overview/black-gravel-free_overview.png` | free 场景全局 | 石块/围墙/位置 |

诊断纪律：**视频先于数值 gate**；即使 S1b 数字过线，视频出现拖腿、卡边、抖动、原地摆尾也不直接进入下一阶段。里程碑视频的生成命令与责任已写入 [`training-record-checklist.md`](training-record-checklist.md)。

## 4. 后续记录（占位）

| Run | 目的 | 状态 |
|---|---|---|
| `baseline-rough-2000` | 从 flat checkpoint full resume，现有 terrain generator 的 rough 基线（含坡/粗糙/离散障碍/stairs up/down） | 训练完成（`model_3999`），权重已导出；G3 初判未通过（逐地形通过率待补测）；质量问题见 [`training-health.md`](training-health.md) |
| `black-gravel-flat` gate | flat 策略 / mirror+footclear 策略在平地+砂砾代理上的通过率与跟踪；训练后复测 | 零样本 8 envs 0 摔倒；训练中 |
| 台阶/梅花桩诊断测试 | 现有基线策略直接评估 T 台阶/沟壑/梅花桩，不训练、不调参 | 待地形配置；不阻塞正式训练门槛，见 [`eval-protocol.md`](eval-protocol.md) §6.1 |
| flat 优化实验 A/B/B+约束/C | 更本质的优化设计对照 | 待 baseline gate 确认 |

## 5. 远程日志与 checkpoint 策略

- TensorBoard：`ssh -L 6006:localhost:6006 bis-ms7e56…`，然后在训练仓库里用 venv 的命令：`cd ~/rc_work/nwwolf_mjlab_training_release && .venv/bin/tensorboard --logdir logs/rsl_rl/black_velocity --port 6006`（远程 PATH 上没有 `tensorboard`）。
- **模型权重可入库（2026-10-21 起）**：选中的 `policy.pt`（约 0.75 MB）与评测 JSON 放本仓库任务 `assets/policies/<version>/`；需要复现的精选 `model_*.pt`（约 5.9 MB）放 `assets/checkpoints/<run>/` 或 `weights/<阶段>` 分支/Release。每 50 iteration 的原始 checkpoint、TensorBoard 事件与日志仍不入库；单个权重超过约 10 MB 时用 Git LFS 或 Release。
