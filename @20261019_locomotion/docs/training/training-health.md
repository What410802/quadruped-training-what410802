# 训练健康检查：rough 基线（2026-10-20）

> 来源：用户 2026-10-20 的 TensorBoard/事件文件体检笔记（本机 2026-10-20 临时体检笔记，未入库）与远程 `~/rc_work/baseline/*.log`。这里只保留可复现结论和下一步；原始日志/事件在远程机，不入库。相关：[`experiments.md`](experiments.md)、[`training-record-checklist.md`](training-record-checklist.md)。

## 1. 结论

- **flat 阶段健康**：2000 iteration 正常完成，reward/episode length/curriculum 都符合预期（见 [`experiments.md`](experiments.md) §3）。
- **rough 阶段正常跑完但质量不足**：`model_3999.pt` 已生成（`baseline-rough-2000-resume2`，3800→3999，10:52，期间 13 次数值异常但自愈）；但有两个问题：
  1. **数值不稳定**：两次崩溃不是突然发生，`Loss/value` 提前约 90 个 iteration 就有预警；`std >= 0` 只是末端症状。
  2. **策略/地形课程卡住**：`stairs_down`、`discrete_obstacles` 长期停在 1–2 级，占训练 env 的 45%，摔倒率约 31%，把整体指标拉低。
- rough 的 `command curriculum` 从 flat 继承了 ±2.0，且 terrain 课程/DR/resume 重置，rough 实际只相当于 2000 iteration 的 fine-tune，起步难度偏高。

## 2. Run 时间线

| run | 内容 | 结果 |
|---|---|---|
| `baseline-2000` | flat 0→1999 | 47:19 正常完成 |
| `baseline-rough-2000` | rough 1999→3999 | 3388 崩溃（`std >= 0` + Warp CUDA 710） |
| `baseline-rough-2000-resume` | 3350→3826 | 3826 再次崩溃（同一断言） |
| `baseline-rough-2000-resume2` | 3800→3999 | 10:52 正常完成；13 次数值异常自愈；`model_3999.pt` |

> 并发录像不是崩溃原因：run1 第一次异常在 20:31:39，录像 20:33 才开始；但录像期间 iteration time 从 3.3 s 涨到 4.4 s，读 `Perf/*` 时要注意。

## 3. 问题 1：数值不稳定（严重）

崩溃前的完整特征链（来自 TensorBoard event 文件）：

1. **平方类 reward 项先爆炸**：`Episode_Reward/action_rate_l2`、`smoothness` 从正常 −0.05/−0.11 跳到 **−7.7 → −466 → −8.6e13 → −7.2e17**；`mean_reward` 出现 −48.9、−633、−3.7e6 等离群值。
2. **value loss 爆炸**：`Loss/value` 从 ~0.01 出现 1e4、1e8、1e31，最后一次记录是 **`inf`**；两次崩溃都遵循这个模式。
3. **KL/LR 崩**：崩溃前 1–2 iteration `Loss/learning_rate` 从 2–3e-4 掉到下限 `1e-5`，`Loss/surrogate` 变 0。
4. **末端症状**：`normal expects all elements of std >= 0.0` 断言（std 变 NaN/负）→ Warp `CUDA error 710 device-side assert`。

解释：极端状态 → 平方正则项被放大到天文数字 → episode return/value target 巨大 → `Loss/value = inf` → 梯度 NaN → 网络权重 NaN → action std 非法。只要出现 `Loss/value = inf`，基本必崩；巨大的有限值可以靠梯度裁剪“扛过去”，所以会出现异常很多但偶尔自愈。

**2026-10-21 已实装的安全网（训练仓库工作区，未 commit）**：

- 新增 `src/alldog_mjlab/utils/reward_safety.py`：在 `RewardManager.compute()` 之后把 per-step 总 reward 限到 ±50（`BLACK_REWARD_CLIP`，0 关闭）；在 PPO `compute_returns()` 之后把 returns 限到 ±1000、advantages 限到 ±100；非有限值先置 0 并计数/打印。
- `BlackVelocityOnPolicyRunner.__init__` 安装两处 clamp；不改变 reward 公式、不剪动作/观测。
- `rough_safety_200`（2048 envs，从 `model_3999.pt` resume 200 iteration）已完成：**200/200 正常结束，无 NaN/`std>=0`/CUDA 710**；`Loss/value` 从 0.003 起，出现 4 次尖峰（108.7 / 133.5 / 163.7 / **18938.7**）后均回落到 ~0.01，`mean_reward` 最高 14.2、最后 12.1。对比旧 run 的 1e4/1e8/1e31→inf，clamp 明显降低了尖峰后果，但 **没有消除尖峰**，不能声称数值问题已根治。
- 尚未做：per-term 原始值 clamp（当前只 clamp 总 reward）、`njmax`/`nfeq` 溢出监控、`Loss/value` 非有限时自动保存并停训。`njmax=256` 仍需在台阶多接触场景验证。

- **自由关节砂砾（2026-10-21）**：`black-gravel-free` 先因 40 小块/初始穿透/石-石接触出现 NaN；后把石块做成 dense 80 布局（1.6 m 方阵、投影覆盖率 79%、无围墙），16 envs 需要 `nconmax=2048 / njmax=4096`，否则 `nefc overflow`。dense80 训练 100 iter 无 NaN、episode length 998；但 32 envs eval 的 arc-right 段出现一次指标 NaN，说明自由关节场景仍需独立的 sim/NaN guard。

高置信推测（尚未插桩确认）：
- 动作/观测没有 clip，极少见的物理极端状态（台阶边缘、多接触、约束容量接近上限）会让 policy/关节速度瞬间变大，平方项爆炸。
- `njmax=256` 只在“较容易状态”下测过 max nefc=80，台阶多接触场景是否溢出没有验证；溢出会让物理直接发散。
- 前两次崩溃的 `std >= 0` 不是根因，不要只修 action std。

**建议优先级**：
1. 给平方类 reward 项（`action_rate_l2`、`smoothness`、`dof_acc`）加 per-term clamp，或对总 reward / value target 做 clamp；`Loss/value` 非有限时提前保存并停训（数值安全网，不改变 reward 设计）。
2. 记录 `max|qvel|`、`max|action|`、`max nefc`、约束容量溢出标志；确认/加大 `njmax`/`nconmax` 再试。
3. 备选：降低 LR（3–5e-4）、减少 envs（4096→2048）只降低碰到病态样本的概率，治标不治本，不作为首选。

## 4. 问题 2：策略质量与地形课程卡住（中等）

最终 `model_3999` 近 20 iteration vs flat：

| 指标 | flat（1900–1999） | rough（3980–3999） |
|---|---|---|
| mean_reward | 22.6 | 13.3（flat 的 59%） |
| mean_episode_length | 995 | 833（17% 提前结束） |
| track_linear / angular | 0.89 / 0.42 | 0.67 / 0.31 |
| error_vel_xy / yaw | 0.32 / 0.39 | 0.41 / 0.51（约 0.25 m/s / 0.31 rad/s） |
| illegal_contact | 0.036 | **1.55（约 31% 摔倒）** |
| terrain mean level | — | **1.98 / 9** |
| action_acc / std / entropy | 0.57 / 0.29 / 2.2 | 0.82 / 0.43 / 6.8 |

**分地形课程**（关键）：
- `stairs_down` 从初始 2.5 跌到 **0.85**；`discrete_obstacles` 跌到 **1.51**。
- `smooth_slope_up` 3.30、`rough_slope` 3.13、`stairs_up` 2.44、`flat` 2.53。
- `terrain_levels/max=9` 说明少数 env 能到最高级，但均值被 45% 的 stairs_down + discrete_obstacles 拖住；这两类持续产生摔倒 episode。

其他现象：
- rough 的探索反而变大（std 0.30→0.43，entropy 2.3→6.8）；fine-tune 正常应下降。reward 缩小后 entropy bonus 相对权重变大是可能原因，会让策略停在高噪声状态、动作更抖。
- `Loss/learning_rate` 有 26%–44% 的 iteration 被自适应调度压到 <1e-4，实际学习率远低于名义 1e-3，rough 进步慢。
- command curriculum 从 flat 继承到 ±2.0，rough 一上来最高速度 + 高难度随机地形，起步难度偏高。

**建议**：
1. `model_3999.pt` 已导出（sha256 `b34b03e5…`）；训练曲线初判 G3 未通过，下一步补逐地形通过率与数值记录（见 [`../assets/policies/baseline-rough-3999/`](../../assets/policies/baseline-rough-3999/README.md)）。
2. rough 阶段**不要直接继承 ±2.0**；从较小范围起步或显式恢复 command curriculum。
3. 查明 `stairs_down` 为什么从 2.5 掉到 0.85（出生点/几何/纯能力）；它占 25% env，不解决会浪费近一半预算。
4. 分阶段：rough-flat（坡/粗糙/砂砾/低摩擦）与台阶/梅花桩/障碍分开训练；当前 `black-rough` 的 7 类地形里 stairs up/down 各 25%、discrete 20%，对“粗糙平地”目标不是最优配比。

## 5. 流程/记录注意

- 10 个基准/冒烟 run 混在 `logs/rsl_rl/black_velocity`，会污染曲线；以后基准写到单独 logdir。
- 每次 resume 会重置 terrain level（0–5 随机）与 command EMA/buffer，曲线在每段 run 起点跳变不是退化。
- `command_curriculum_restore` 默认值与 README 不一致（已在 [`experiments.md`](experiments.md) 记录）。
- 崩溃前有约 90 iteration 的可监控窗口：建议在训练记录清单中把 `Loss/value`、`action_rate_l2/smoothness`、`Loss/learning_rate`、分地形 level 加为必看项。

## 6. TensorBoard 快速查看顺序

1. RUNS 只勾 baseline 相关 run；smoothing 0.6；查 `Loss/value` 时关 smoothing，取消 “Ignore outliers”。
2. `Train/mean_reward` + `mean_episode_length`。
3. `Episode_Reward/track_linear_velocity`、`track_angular_velocity`。
4. `Episode_Termination/illegal_contact`（四项之和作分母换算摔倒率）。
5. `Curriculum/terrain_levels/*` 分地形看，重点 `stairs_down`、`discrete_obstacles`。
6. `Curriculum/command/*`。
7. `Loss/value`（>100/inf 预警）→ `Loss/entropy`、`Policy/mean_std` → `Loss/learning_rate`。
8. `Metrics/twist/error_*` → `Perf/*` → `*/time` 变体。

## 7. 2026-10-24 复发：Warp CUDA 710 的插桩复现与修复

> 本节是 2026-10-23 夜间 ~10-24 上午的排查记录。脚本/日志在远程训练仓与 `~/rc_work/logs/`（不入库），本地文档只留结论与可复现命令。

### 7.1 现象

从 p1 续训最终权重 `logs/rsl_rl/black_velocity/2026-10-22_16-44-17_p1_basic_obstacle_cont/model_5496.pt` 出发的 **4 次** run 全部在 100 iteration 内崩 `Warp CUDA error 710`（`normal expects all elements of std >= 0.0` 之后）：`basobstacle_from_p1_20261023`（~iter 5676）、`rough_from_p1_20261023`（~iter 5513）、`smoke100_resume_20261024`（100 iter 跑完但 23/100 iter 的 `action_rate_l2` 离群，最后一次 -1.5e6）与插桩 run。同一 checkpoint 所属的 `p1_basic_obstacle_cont` 自身 1500 iter **无异常**。

### 7.2 对照实验（全部 4096 envs、100 iter、同 seed 42、resume）

| 实验 | 初始化 | 结果 |
|---|---|---|
| E1 `e1_ctrl_3997_20261024` | 复现 `p1_cont` 起点：run1 `model_3997` | **100/100 clean**；指标与 10-22 的 `p1_cont` 前 100 iter 几乎逐位一致（action_rate max \|.\| 0.050 vs 0.051） |
| E5 `e5_5400` | `p1_cont` `model_5400` | **100/100 clean**（action_rate max \|.\| 0.088；value loss 尖峰 1.52 后回落） |
| probe `probe2_5496_20261024` | `p1_cont` `model_5496` + `BLACK_ANOMALY_PROBE=1` | 第 1 个 rollout 的 **step 29** 抓到跨阈值动作 |
| fixed `fixed2_5496_200_20261024` | 同上 + 三项安全网（§7.4） | 200 iter 无 CUDA 错误（见 §7.5） |

结论：**环境/机器/code 快照都没变**（run 目录里的 `git/` 快照逐字节相同），差异在 checkpoint 状态。`model_5400` 干净、`model_5496` 不稳定，说明 p1 续训最后 ~100 iter 把策略推进了一个"遇到离群状态会自激"的区域，但训练当次因为 rollout 未碰到而未暴露。

### 7.3 插桩：动作反馈环放大，不是物理先爆

新增 `src/alldog_mjlab/utils/anomaly_probe.py`（`BLACK_ANOMALY_PROBE=1` 时包装 `RslRlVecEnvWrapper.step`，记录每步 max \|action\|/max \|qvel\|/obs 并按阈值停训）。probe 在 resume 后第 29 个 env step（第一个 rollout 内）抓到：

```text
history step=18 |action|max=13.75 |joint_vel|max=27.64 gt5=30 gt10=3 gt50=0
history step=21 |action|max=22.94 |joint_vel|max=28.51 gt5=32 gt10=7 gt50=0
history step=24 |action|max=50.91 |joint_vel|max=28.29 gt5=44 gt10=10 gt50=1
history step=27 |action|max=56.54 |joint_vel|max=37.35 gt5=45 gt10=11 gt50=1
history step=28 |action|max=89.06 |joint_vel|max=35.29 gt5=42 gt10=10 gt50=1
history step=29 |action|max=135.3 |joint_vel|max=46.31 gt5=43 gt10=8 gt50=1
env 1690 ep_len=726 |a|max=135.3 |jv|max=46.31 root_lin=[0.46,1.37,-1.86] root_ang=[-14.64,-6.58,-6.33] root_pos=[-20.17,0.43,0.30]
```

关键读数：**动作在单个 env 内几何增长（~12 步 ×1.2–1.5），而 `|qvel|` 只有 ~20–46 rad/s（正常量级）、物理尚未爆**；`obs` 的 max 与 `action` 的 max 同步增长（obs 里含 `actions` 项）→ 放大机制是 **"上一帧动作 → 观测 → 下一帧动作"的自激环**，触发状态是坠落/翻滚（`|root_ang|` 14.6 rad/s、x=-20 已出界）。等到动作足够大，才由力矩/接触把物理打成 NaN，最后在 PPO 采样处报 `torch.normal` 断言 → Warp 710。所以"先修 action std / 先降 LR"都不是根因修复。

与 2026-10-20 那次（`Loss/value` 先到 inf）的区别：本轮 reward clamp ±50 与 return clamp ±1000/±100 **已经装上**，value loss 尖峰还在（`fixed` 之前的 smoke100 里 29% iteration 的 `action_rate_l2` < -100）但不再到 inf；致命路径变成动作自激。

### 7.4 修复（训练仓工作区，单开关之外的安全网）

1. **actor 观测 clip（部署一致）**：部署侧 `clip_obs=100`，训练侧原来没有 clip。mjlab 的 per-term clip 在 **scale 之前**执行，所以每项按 `100 / max(scale)` 折（如 joint_vel：raw ±2000、×0.05 后 ±100），等价于部署对拼接后观测的 ±100。配置项 `BLACK_CONFIG.observation.actor_obs_clip`（<=0 关闭）。
2. **动作 clip（部署一致）**：`clip_actions = BLACK_CONFIG.control.action_clip = 100`，进入 runner cfg；部署侧同样是 ±100。这一步把自激环里的动作上界钉住。
3. **数值安全终止 `bad_sim_state`**：`terminations.py` 新 term，任一 env 的 `joint_vel`/root 线角速度非有限，或超过 `100 / 40 / 20`（rad·s⁻¹）阈值就终止并 reset。它在 reward 之后、obs 之前执行，因此 NaN 物理状态不会进到策略输入（切断 NaN→policy→`torch.normal` 断言）。阈值远高于正常步态（正常 |qvel| < 40、|root ang| < 5），play 模式会移除该 term。

这三项都不改 reward 设计、不改动作/观测维数契约；`bad_sim_state` 只影响"物理异常 episode"的终止统计。

### 7.5 修复后冒烟

- `fixed2_5496_200_20261024`（4096 envs、resume `model_5496`、200 iter、probe 阈值放宽到 action>1000 / qvel>200 以免把 100–300 的饱和动作误报）：**200/200 完成，无 CUDA 错误、无 NaN、无 probe 硬触发**。整段 200 iter 的指标（tfevents 实测）：
  - `Episode_Reward/action_rate_l2` last=-0.044、max abs=0.047；`smoothness` last=-0.093、max abs=0.100（对比崩溃前 smoke100 的 -1.5e6 / -2.7e5，且 23% iteration 离群）；
  - `Episode_Metrics/mean_action_acc` max=0.764；`Loss/value` max=0.0225（对比崩溃前的 12.8/59.8/288）；
  - `reward clamp` 统计：`clipped_env_steps=0`、`max_abs_before_clip=1.65`（per-step 总 reward 根本不用裁剪了）；
  - 原始动作仍会在个别 env 饱和到 ~300（clip_actions=100 后实际下发的动作被钉住），但不再放大成 1e5、也不再产生 NaN。
  日志 `~/rc_work/logs/fixed2_5496_200_20261024.log`。
- 复现命令（远程训练仓）：

```bash
cd ~/rc_work/nwwolf_mjlab_training_release
export UV_CACHE_DIR="$HOME/rc_work/.uv-cache"
MUJOCO_GL=egl .venv/bin/train black-basic-obstacle \
  --agent.resume True \
  --agent.load-run 2026-10-22_16-44-17_p1_basic_obstacle_cont \
  --agent.load-checkpoint model_5496.pt \
  --agent.max-iterations 200 --agent.save-interval 100 \
  --agent.run-name fixed2_5496_200_20261024 \
  --agent.logger tensorboard --env.scene.num-envs 4096
```

### 7.6 仍未做 / 后续

- `model_5000` 的对照（E6）在拿到 E5 结果后主动中止，未测；"从哪一版开始不稳定"还没有精确到 checkpoint 粒度。
- 200 iter 不是长跑稳定性证明：长跑仍要 run card + 每 ~20% 检查 `Loss/value`、`action_rate_l2`、`Log/probe` 类指标；若再出现动作饱和到 1e3 量级，应停训看 `bad_sim_state` 触发次数。
- 长期根治方向（未做）：depth/相机观测上线后重新审视 `njmax/nconmax` 与 `torch.normal` 前端 NaN 检测；或把 PPO 的更新加 "non-finite loss → 保存并退出" 的干净停训。
