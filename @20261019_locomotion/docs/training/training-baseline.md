# 现有训练基线：课程与奖励（flat 优先）

> 依据：训练仓库 `nwwolf_mjlab_training_release` commit `24c7f16`（2026-10-20 读取）。本文只做**现状梳理**，为“接地形之前先做更本质的优化设计”提供对照基线；不改变训练代码。实际修改在训练仓库的 fork 中进行，改完需重新验证 S1 基线数字。

## 1. 现有课程模式

### 1.1 总览

| 任务 | 课程 | 说明 |
|---|---|---|
| `black-flat` | **只有 command curriculum** | 平地 = plane，无 terrain generator；`terrain_levels` 被移除（`env_cfgs.py:501-508`） |
| `black-rough` | **command curriculum + terrain curriculum** | native `terrain_levels_vel` + 自定义 command curriculum（`env_cfgs.py:579-591`、`745-787`） |
| `black-flat-him` / `black-rough-him` | 与对应 PPO 相同 | HIM 只改算法/观测/runner，env 的 curriculum、reward、DR 完全相同（`env_cfgs.py:813-837`） |
| `play` | **无课程** | `_configure_play()` 清空 `cfg.curriculum`（`env_cfgs.py:716-737`） |

另有一条“训练阶段”流程，不属于 env curriculum：`flat PPO → flat HIM → rough HIM`（warm start / full resume，见 `him_runner.py`）；它只在 checkpoint 上做 stage 切换，环境里的课程仍是上面两张表。

### 1.2 Command curriculum：性能驱动的前进速度课程

这是 `black-flat` 里**唯一的课程**，也是 `black-rough` 里除了地形课程之外的第二个课程。它不是 MjLab 自带的 time-based `command_vel` 阶段课程：代码显式 `cfg.curriculum.pop("command_vel", None)`（`env_cfgs.py:172-174`），改成按策略跟踪表现推进。

**被控对象**：只改 `UniformVelocityCommandCfg.ranges.lin_vel_x`。`lin_vel_y` 固定为 `[-1.0, 1.0]`、`ang_vel_z` 固定为 `[-π, π]`；`resampling_time = 10 s`；sampler 比例固定为 standing 10%、forward-only 20%、world-frame 0%（`black_config.py:125-137`）。

**判定流程**（`curriculums.py:61-356`）：

1. 每个 episode 结束时收集一个样本：`(episode 结束瞬间的 |vx 指令|, tracking ratio)`。
2. `tracking ratio = episode 的 track_linear_velocity reward 总和 / (episode 步数 × step_dt × |tracking weight|)`，理论上界为 1（`curriculums.py:241-283`）。即：**用线性速度跟踪项的 episode 平均奖励来判定是否“学会了”当前速度**。
3. buffer 累计到至少 `buffer_min = 256` 个有效样本后评估一次；样本按速度分两组：`low: 0.2 < |vx| <= 0.6·V`、`high: |vx| > 0.6·V`，其中 `V = max(|vx_min|, |vx_max|)`。若 low 或 high 样本不足（至少 8 / 4 个），本次不更新 EMA、streak 清零、**保留 buffer** 等下一批（`curriculums.py:285-356`）。
4. 两组的 tracking ratio 各自做 EMA（alpha = 0.20）；EMA 需要同时超过阈值：low > 0.70、high > 0.60（`threshold_high = threshold_low - 0.10`）。
5. 连续 `required_passes = 2` 次评估都过线 → `lin_vel_x` 双边各扩 `step = 0.1`，从初始 `[-1.0, 1.0]` 逐步扩到 `[-2.0, 2.0]` 封顶；达到后不再扩，只继续统计。
6. 每次真正完成的评估清空 buffer；EMA / streak 跨 episode 累计。`reset()` 不清课程状态（`curriculums.py:101-103`）。
7. TensorBoard 观测量：`Curriculum/command/{vx_min,vx_max,ema_low,ema_high,pass_streak,buffer_count,low_count,high_count,low_ratio,high_ratio,evaluated,progressed}`。

**checkpoint 恢复模式**（`curriculum_checkpoint.py:54-85`、`rl_cfg.py:59-74`）：`none`（不恢复）、`range`（只恢复 vx 范围，EMA/streak/buffer 清零）、`full`（range + EMA + streak + buffer 全恢复）、`auto`（同 stage resume→full；跨 stage→range；旧 checkpoint→none）。PPO→HIM warm start 固定用 `range`（`him_runner.py:88-104`）。

> **注意一处现状不一致**：`README.md` §9 写默认是 `auto`，但实际构造 runner 时取 `BLACK_CONFIG.runner.command_curriculum_restore`，其默认值是 `"range"`（`black_config.py:528-544`）；`rl_cfg.py:74` 的 dataclass 默认 `"auto"` 会被这个值覆盖。做续训实验时建议显式传 `--agent.command-curriculum-restore`，不要依赖默认。这一处应在训练仓库修正文档或默认值。

### 1.3 Terrain curriculum（仅 rough）

- 使用 MjLab native `terrain_levels_vel`（`env_cfgs.py:579-591`）；判定逻辑是 legged_gym 风格（`mjlab/tasks/velocity/mdp/curriculums.py:25-101`）：
  - 本 episode 沿 xy 走了 `distance > terrain size[0] / 2`（Black 是 8 m patch，即 > 4 m）→ 升一级；
  - `distance < ||command_xy|| × max_episode_length_s × 0.5`（20 s × 0.5 = 10 s × 指令速度）→ 降一级；
  - 第一次 reset（`common_step_counter == 0`）冻结 level，避免出生点误判。
- 地形生成器：7 类 sub-terrain、10 行难度、`difficulty_range = (0, 0.9)`；curriculum 模式下每类一列，`proportions` 是 env 分配权重（`black_config.py:333-399`、`terrain.py:233-322`）：
  - flat 0.10；smooth_slope_up 0.05；smooth_slope_down 0.05；rough_slope 0.10；discrete_obstacles 0.20；stairs_up 0.25；stairs_down 0.25；
  - `max_init_terrain_level = 5`；
  - 台阶 `step_height = 0.05 + 0.18 × difficulty`、宽 0.3 m；离散障碍高度 `0.06 + 0.2×d` 等。
- `black-flat` **没有**地形课程；把 terrain 设成 plane、generator 置 None，并把 `terrain_levels` 从 curriculum 里 pop 掉。

## 2. 奖励（惩罚）函数：flat 的 10/11 项

flat 与 rough 共用同一张 reward 表；rough 只把 `base_height` 的测量方式从 world-z 换成地形相对高度（见 §3）。HIM 任务同样共用。**`baseline-2000` 训练时是前 10 项；2026-10-21 增加第 11 项 `foot_clearance` 作为 A/B，见 [`experiments.md`](experiments.md) §3.9。**

| # | term | 公式（raw，未乘 dt） | 权重 | 类别/作用 |
|---|---|---|---|---|
| 1 | `track_linear_velocity` | `exp(-Σ_{x,y}(v_cmd − v_body)² / σ)`，σ=0.25 | **+1.0** | 任务：跟踪平面线速度；指数核，误差平方和作分子 |
| 2 | `track_angular_velocity` | `exp(-(ωz_cmd − ωz_body)² / σ)`，σ=0.25 | **+0.5** | 任务：跟踪偏航角速度 |
| 3 | `lin_vel_z` | `v_z²`（body frame 竖直速度） | −2.0 | 稳定性：抑制上下弹跳 |
| 4 | `body_ang_vel` | `ωx² + ωy²`（body frame roll/pitch 角速度） | −0.05 | 稳定性：抑制俯仰/横滚抖动 |
| 5 | `upright` | `gx² + gy²`（投影重力的水平分量，native `flat_orientation_l2`） | −0.2 | 姿态：保持机身水平 |
| 6 | `base_height` | flat：`(z_root − 0.43)²`（world z；reset 默认高度 0.45） | −1.0 | 高度：保持标称站姿高度 |
| 7 | `dof_acc` | `Σ((q̇_prev − q̇)/dt_control)²`，dt=0.02 s | −2.5e-7 | 正则：抑制关节加速度/抖动 |
| 8 | `joint_power` | `Σ|q̇|·|τ|`（执行器力矩） | −2e-5 | 能量：机械功率的 L1，量级上远小于跟踪项 |
| 9 | `action_rate_l2` | `Σ(a_t − a_{t−1})²`（raw action） | −0.01 | 正则：动作变化率 |
| 10 | `smoothness` | `Σ(a_t − 2a_{t−1} + a_{t−2})²`（native `action_acc_l2`） | −0.01 | 正则：动作二阶差分 |
| 11 | `foot_clearance`（2026-10-21 新增） | `Σ (p_z^target − p_z)² · ||v_foot,xy||`，目标 0.09 m | −0.01 | 步态：摆动腿离地；来自 HIM 论文 Table 5，仅 moving foot 受罚 |

实现位置：`env_cfgs.py` 的 `_configure_rewards()`（组装与权重）；公式在 `rewards.py`（自实现项）和 mjlab native 函数（`flat_orientation_l2`、`action_rate_l2`、`action_acc_l2`）。`RewardManager` 统一再乘 `dt`，所以表里权重是“每 step 系数”，实际 episode 回报还依赖 episode 长度（20 s，`black_config.py:16-22`）。

**flat 基线里没有的东西**（对“第一性原理”改造很关键）：

- **`baseline-2000`** 没有 foot clearance / air time / contact count / 步态相位 / 抬腿高度 / 落脚点等步态先验；2026-10-21 仅新增了 `foot_clearance` 一项做 A/B，其余仍是空白；
- 没有足端滑移惩罚、膝/髋碰撞惩罚、关节限位惩罚、力矩超限惩罚（碰撞与卡死走 termination，见 §3）；
- 没有 survival bonus、没有单独的前进距离奖励（前进只通过 velocity tracking 间接给）；
- 能量只通过很小的 `joint_power` L1 体现，不是 CoT/正机械功率/电机模型级成本。

也就是说：**这份基线在“少用手工步态先验”这一点上已经比较接近你链接里说的方向**；手工痕迹主要在跟踪核参数、稳定性/正则权重、课程阈值、DR 范围与终止阈值。

## 3. flat 与 rough 的差异（为什么说只有一套 reward）

- `base_height`：flat 用 world-z `(root_z − 0.43)²`；rough 用 35 条 terrain_scan 射线（0.6×0.4 m footprint）的局部离地高度均值再做同一 L2（`rewards.py:109-177`、`env_cfgs.py:467-484`）。权重、目标高度、其余 10 项完全一致；`foot_clearance` 也为二者共用。
- rough 额外：`cfg.sim.nconmax = 128`（MJWarp 多接触容量 workaround，`env_cfgs.py:487-498`）、terrain generator + terrain curriculum、`out_of_terrain_bounds` termination（`env_cfgs.py:683-696`）。flat 不注册 OOB。
- critic 维度：flat/rough 都是 259 维（末尾 187 维 height_scan）；actor 都是 45 维（不含 height_scan）。rough 的 height_scan 在 flat 里也存在，只是平地上数值恒为 0 附近。
- HIM：env 完全相同，HIM 只是在算法层加 estimator/latent 与 270 维 history 观测；reward 表没有任何 HIM 专用项。

## 4. 不在 reward 里、但同样在塑形优化的部分

要评估“换更本质的优化动力”，不能只看 reward 表，下面这些是当前手工设计的行为约束：

- **终止**（`env_cfgs.py:652-696`、`terminations.py`）：
  - `illegal_contact`：trunk / 四 thigh 与 terrain 接触力 > 1 N 终止（不是 reward 惩罚）；
  - `stuck`：有移动指令时，沿指令方向的 progress speed < 0.05 m/s 持续 > 4 s 终止（1 s grace）；
  - timeout：episode 20 s；
  - rough 追加 `out_of_terrain_bounds`（truncation，非 failure）。
- **指令分布**（`black_config.py:125-137`）：standing 10%、forward-only 20%；`vy ∈ [-1,1]`、`ωz ∈ [-π,π]`；10 s 重采样。
- **reset**（`black_config.py:171-202`）：root 六维速度 ±0.5；hip 不随机、thigh ±0.4007 rad、calf ±0.5945 rad；关节速度不随机。
- **域随机化**（`black_config.py:277-326`、`env_cfgs.py:266-388`）：foot friction 0.2–1.25、trunk payload −1～+2 kg、COM ±0.05 m、Kp/Kd 缩放 0.9–1.1、encoder bias ±0.015 rad、16 s 间隔 ±1 m/s xy push。
- **观测噪声**（`black_config.py:151-164`）：base ang vel ±0.3、projected gravity ±0.05、joint pos ±0.08、joint vel ±2.0（进 policy 前再乘 obs scale）。

## 5. 与你那份“第一性原理”调查的对照（初步）

你链接里的核心主张可概括为：任务用奖励、安全/运行极限用**约束（终止）**、步态偏好交给能量最小化、地形适应用外感知/环境保真；少用手工步态先验，但前提是环境本身足够真实。对应到这份基线：

| 主张 | 当前 flat 基线 | 差距/机会 |
|---|---|---|
| 步态先验最小化 | 已无 airtime/contact/foot clearance 项 | 方向一致；主要手工项是稳定性/正则权重 |
| 安全用约束而非软惩罚 | illegal_contact / stuck / timeout 已是终止 | 约束只覆盖 trunk/thigh 接触与无进展；足端/关节限位等仍是“物理/软限制”，没有显式约束 |
| 能量最小化 | 只有很小的 joint_power L1 | 可换成正机械功率/CoT/电机能量模型，并提高为一级目标 |
| 环境保真 | flat 是纯 plane；DR 手工范围 | 接地形前应先用现有 rough generator 做保真度对照，避免“在平面上去掉先验→拖脚/抖腿” |
| 自动/本质优化 | command 课程按 tracking EMA 手工阈值 | 可做约束优化/自适应权重/多目标 Pareto，但需先有可信的评测 gate |

**建议的 flat 对照实验（尚未实现，待确认后做）**：

1. **A 基线**：现有 10 项 + 现有 command curriculum（对照组，固定 seeds/命令序列）。
2. **B 任务+能量**：只保留 `track_linear`/`track_angular` + 机械功率/CoT 惩罚，去掉 lin_vel_z/body_ang_vel/upright/base_height/dof_acc/action_rate/smoothness（或保留 action rate 作为 sim2real 约束）。
3. **B+约束**：在 B 上把姿态/高度/接触安全从软惩罚改成 termination/可行域约束（例如 base height/orientation 越界终止），验证“约束 vs 惩罚”。
4. **C 环境保真**：在 B+约束 上把 flat 改成 mild rough/DR，观察“去掉手工项后靠环境能否避免拖脚/抖腿”（这是你链接里强调的前提）。
5. 评测 gate：速度跟踪误差不差于 A、摔倒率不高于 A、CoT 更低/持平、动作平滑度和力矩不退化；同一命令 suite、多种子、至少 3 次重复。

这组实验的第一步是**给训练仓库加 reward profile 开关**（同一 task id 下切换 reward dict、命令课程和 termination 组合），并固定评测脚本；不要直接在现有基线上替换权重，否则无法回答“是否不差于手工设计”。具体实现需要训练仓库 fork 的写入与一次 4096 envs 的短跑（约 1–2k iteration/组），等远程机训练资源排期后做。

## 6. 待核对

- 你链接是 AI 对话整理：其中 LoComposition（arXiv 2606.15896）可查；PACE / SafeSteps 的具体结论与代码可复现性我还没有逐篇核对原始论文，作为设计依据前应核一遍（尤其“删除 airtime/contact/foot clearance 后 CoT 降 56%”这类数字要按原文实验条件确认）。我已把这条列为下一步文献核对项，不会直接把二手结论当事实。
- `README.md` §9 的 command curriculum 默认恢复模式与代码实际默认值不一致（§1.2 注），需要修 README 或在训练仓库显式改默认。
- flat 的 `base_height_target = 0.43` 与 reset 默认 root 高度 0.45 的差异是否是有意（注释只说职责不同），做高度相关实验前应确认。

## 7. 代码索引

- 课程：`src/alldog_mjlab/tasks/velocity/black/curriculums.py`、`curriculum_checkpoint.py`、`black_config.py:55-110`、`env_cfgs.py:557-591`
- 奖励：`src/alldog_mjlab/tasks/velocity/black/rewards.py`、`black_config.py:245-269`、`env_cfgs.py:391-484`
- 终止：`src/alldog_mjlab/tasks/velocity/black/terminations.py`、`black_config.py:210-237`、`env_cfgs.py:652-696`
- 地形：`src/alldog_mjlab/tasks/velocity/black/terrain.py`、`black_config.py:333-399`、`env_cfgs.py:501-522`
- 环境契约：`src/alldog_mjlab/tasks/velocity/black/black_config.py:16-202`、`env_cfgs.py:146-388`
- HIM / stage：`him_runner.py`、`rl_cfg.py`、`env_cfgs.py:813-837`
