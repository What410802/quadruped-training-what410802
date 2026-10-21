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
