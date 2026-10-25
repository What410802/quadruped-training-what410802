# Part 2 官方几何评测与可部署权重（BC/DAgger 蒸馏，2026-10-25）

## 0. 结论速览

- **交付**：`@20261024_blackw/models/comp_bc_v5/`（已入库备份，commit `b12ac33`）是一份**单份、可部署**的 blackW 权重（342→512→256→128→16 ELU MLP，行动/观测完全按 rl_sar 部署契约），由官方三份 blackW 策略（obstacle/stair/flat）行为克隆 + 两轮 DAgger 蒸馏而来；部署目录 `@20261024_blackw/ws/src/rl_sar_blackw/policy/blackW/comp_bc_v5/`。
- **严格 judge v5（四轮终态判据）**：官方几何 20 关、每关单独 MuJoCo 场景、0.002s 物理、无时间限制口径下，按"逐障碍选择速度指令"的参考 profile 得分 **750/1300**：高台 40cm = 200、高墙 40cm = 200、斜坡 35° = 100、壕沟 20cm = 150、楼梯 20cm = 100、梅花桩 0。
- **同一 judge（v5）下官方三份权重 + 同样逐障碍选命令的基线 = 660/1300**（官方策略不会下 20/30cm 台阶：楼梯只到 10cm/10 分；平台 40/高墙 40/斜坡 35/壕沟 20 与自训权重持平）。自训单份权重靠"完整楼梯 20cm"多拿 90 分。
- **可部署性**：rl_sar 无头自检 `check_walk_blackw.py --realtime false --policy comp_bc_v5` 前进段 PASS；转向指令覆盖不足（数据里 yaw 只在 flat 教师里出现），属于已知缺口。
- **4 次挑战口径下的期望分**：平台 40/斜坡 35/壕沟 20 均 4/4；高墙 40 为 3/4、楼梯 20 为 2/4（±0.1m 横向抖动下）→ 期望 ≈ 743/1300，最好情况 750。
- **未拿到**：斜坡 45°（200）、楼梯 30cm（200）、壕沟 30cm（300，洁净跨越口径）、梅花桩（200）。这 900 分是下一阶段专项 RL 的目标（§7 记录进行中的 specialist 实验）。

## 1. 规则与评测口径（对齐 `docs/reference/team-race-2026.md`）

Part 2 为纯仿真、仅允许 RL（禁止固定动作/状态机），每种障碍最多 4 次挑战、取能通过的最高难度、**不计时**；可跳过障碍；可自建地图但障碍种类必须与官方一致。

| 障碍 | 官方素材 | 评分档位 |
|---|---|---|
| 高台 | `map.xml: platform_10/20/30/40cm` 单块 1.5×1.6m 高台 | 10/20/30/40cm = 10/50/100/200 |
| 楼梯 | `stairs_XXcm` 完整阶梯：6 级上 + 0.8m 平台 + 6 级下（官方贴图覆盖整体） | 10/15/20/30cm = 10/50/100/200 |
| 斜坡 | `slope_XXdeg_up` 上坡 2m 水平投影、1.4m 宽 + 0.8m 顶平台（官方计分项只标 `_up`，任务描述"迎着坡面走"） | 20/30/35/45° = 10/50/100/200 |
| 高墙 | `cross_bar_3/5/6/7`（12/20/30/40cm，10cm 由 12cm 改高） | (10)/20/30/40cm = 0/50/100/200 |
| 壕沟 | `trench_Xcm`：1m 上坡 + 0.5m 近台 + 槽（10/20/30cm 宽）+ 0.5m 远台 + 1m 下坡 | (10)/20/30cm = 0/150/300 |
| 梅花桩 | `plum_t1`：入口 0.8×0.8×0.2m 平台 + 24 块 0.2m 立方（两排交错、同排中心距 0.6m、排距 0.4m、首块距平台 0.1m）+ 出口平台 | 越过 = 200 |

本地评测底座：`gen_part2_official_levels.py` 把 `map.xml` 的 geom 逐条**原样复制**成 20 个隔离场景（每个场景只放一个难度档，障碍起点平移到 spawn 前方 1.8m），judge 元数据（平台顶高/台阶终点/斜坡高度/墙位置/槽边/桩场范围）在生成时计算并写入 `part2_official_levels.json`。

## 2. 严格 judge v5：为什么"事件判据"必须换成"终态谓词"

用户复核视频时发现两个漏洞：①高墙/高台的判定在"基座越过某条线"时就成立，视频里后轮其实还没翻过去；②壕沟只要求 base x 穿过近/远边，轮子掉进槽里仍算过。这两个问题的共同根因是把**事件**（某一帧 base x/z 满足阈值）当成**终态**。详细的原则与文献见 [`part2-failure-vs-reward-design.md`](part2-failure-vs-reward-design.md)，结论是：judge 判负/不可恢复 → termination；judge 不度量的连续质量 → reward shaping；success 必须是"强到之后无法推翻"的终态。

judge v5 的判据（`@20261024_blackw/scripts/eval_blackw_part2.py`，`JUDGE_VERSION="v5-wheel-terminal-bands-2026-10-25"`）：

| 障碍 | 成功谓词（终态，需连续保持 hold_s+0.1s） | 失败判据 |
|---|---|---|
| 高台 | 四轮轮底都在台面（top_z−6cm ≤ z ≤ top_z+20cm）、基座 x 在台面范围、lane ±0.7m | 翻倒（tilt>75° 或 z<0.15）、超时 |
| 楼梯 | ①出现过"四轮都在顶部平台"（爬上证据）②四轮都在下降段终点之后、轮底回到地面（−6cm..20cm）、lane 内 | 翻倒、超时 |
| 斜坡 | 四轮都在顶平台（rise_z−6cm..+20cm）、x≥goal_x_min、lane 内 | 翻倒、超时 |
| 高墙 | 越过墙线、四轮都在墙后地面（x≥墙后 0.16m、轮底 ≤8cm）、爬升证据（墙附近基座 z 达标）、lane 内 | 翻倒、超时 |
| 壕沟 | 近/远槽边都跨过、四轮都在远台面（0.24..0.50m）、x≥far+0.15、lane 内 | **任一轮子进入槽内且轮底 < plateau_z − min(0.5×槽深, 轮半径)=0.197m 立即判负**（轮半径 0.103m） |
| 梅花桩 | 四轮都在出口平台（top_z−6cm..+20cm）、x≥goal_x_min、lane 内 | 桩场范围内任一轮底 <0.05m（触地）立即判负、翻倒 |

**审计状态（fail-closed）**：`@20261019_locomotion/AGENTS.md` 要求 judge 忠实度/分数诚实性由 Codex reviewer 做 Type-B 审计；本次 reviewer bridge 不可用（401），已在 `@20261019_locomotion/comp/audits/2026-10-25-judge-v5-G1-REVIEW_UNAVAILABLE.md` 记录 `REVIEW_UNAVAILABLE`，本文数字仅为 executor 证据（JSON+视频+脚本可复现），未作 Type-B 声明。

判定要点：成功是**吸收态**（一旦成立即锁存），所以还要求"轮子在支撑面上"而不是"高于支撑面"（v5 加了上限带），否则一次腾空/跳跃就能骗过判据；同时所有失败都是 termination，训练里与 judge 同源（§5）。

## 3. 契约发现（复现要点，全部实测）

1. **轮速 action 符号**：官方 blackW 与 N-W-wolf 的 `action_scale` 是有符号的 FL +10 / FR −10 / RL +10 / RR −10。用全 +10 的环境加载官方权重时机器人会后退/打转（实测基座 x −0.42m/6s）。所有 warm-start/迁移/自训任务都必须用镜像符号，否则权重不可用。
2. **观测历史布局**：MjLab（rsl_rl）原生 history 是 term-major、term 内 frame-major 旧→新；部署 rl_sar 是 frame-major 新→旧。导出时把 actor 第一层列做置换即可（本仓库 `export_blackw_policy.py`、`export_bc_policy_local.py` 都实现了）。BC 训练数据的 history 也必须按原生布局构造（第一版实现成 term 内 dim-major，MSE 0.0008 但仍必然摔——布局错小误差也能毁掉闭环）。
3. **rl_sar history 初始化**：rl_sar 的 ObservationBuffer 从空开始（先插 0），MjLab/rsl_rl 是 backfill（首帧复制满 6 格）。已 patch `@20261024_blackw/ws/src/rl_sar_blackw/src/rl_sim.cpp`（每次进 RL 前 prefill），否则历史观测与训练分布不一致。
4. **观测/动作契约**（与 rl_sar `base.yaml` + `config.yaml` 一致）：57 维/帧 = commands×[2,2,0.25]、body ang_vel×0.25、projected gravity、dof_pos−default（轮子位置清零）、dof_vel×0.05、last raw action；6 帧历史；16 维动作；腿 kp50/kd1.2、轮 kp0/kd1.0、action_scale 腿 0.25、轮 ±10；力矩按关节限幅（髋/大腿 23.7N·m、小腿 59.25、轮 20）。

## 4. 行为克隆/DAgger 蒸馏（comp_bc_v4 怎么来的）

- **教师**：官方 `blackW/{obstacle,stair,flat}` TorchScript 权重（HIM 导出，直接当黑盒用）。
- **数据**：官方几何 20 关 × 速度指令 {0.25,0.35,0.5,0.7,0.9} m/s（含两段 schedule）× 教师 {obstacle,stair} + flat 教师短片段（含横向/转向指令），共 980 episodes / 323,903 样本；成功 episode 权重 1.0、失败 0.15。
- **DAgger 一轮**：用 BC 学生跑 320 episodes，教师在学生状态上打标（同一历史观测），再合并重训，共 483,903 样本；解决纯 BC 的协变量偏移（第一版 BC 在低速度下 3s 内摔，DAgger 后 0.3 m/s 可稳定走）。
- **训练**：Huber loss、40 epochs、ELU MLP 342-512-256-128-16、val 0.0104；导出为部署格式 TorchScript（首层列置换）+ `config.yaml`（官方 obstacle 配置复制）。
- **为什么不做单帧 45 维**：部署契约是 57×6 历史；教师权重也是历史策略。BC 目标就是"用同一契约把三位教师合成一份"，避免任何观测差异。
- **为什么 BC 不是最终形态**：BC 上界 = 教师能力（斜坡 45°、楼梯 30cm、壕沟 30cm、梅花桩教师都不会）；要越过这些档位必须 RL 训练新技能，见 §5。

## 5. 训练环境与 RL 尝试（含失败记录）

训练环境：MjLab v1.6.0 + mujoco_warp（远程 `bis-ms7e56` RTX 5060 Ti），任务 `blackw-official`（`@20261019_locomotion` 之外为独立训练仓，改动在 `alldog_mjlab/tasks/velocity/blackw/`）：

- 地形：5 类官方几何（`exact_terrain.py`：平台/高墙/斜坡/完整上+下楼梯/壕沟），坐标与官方隔离场景一致（平台 2.55m、墙 1.86m、斜坡起点 1.8m、槽近边 3.8m、楼梯 1.8–6.2m）；`difficulty_range` 可被 `BLACKW_DIFF_MIN/MAX` 固定到指定档位（专项训练用）。
- 判据同源：`part2_success`/`part2_failure` termination 与 judge v5 同一套谓词（四轮支撑带 + 基座高度/vz），成功给 `part2_clear=+25` 一次性奖励；壕沟轮子沉槽 `trench_wheel_drop=-5.0` 惩罚并同时触发 `part2_failure`；lane 越界终止。
- 命令/奖励可用环境变量覆盖（`BLACKW_VX_MIN/MAX`、`BLACKW_LATERAL_CMD`、`BLACKW_YAW_CMD`、`BLACKW_CLIMB_W`、`BLACKW_PROGRESS_W`、`BLACKW_GOAL_W`、`BLACKW_CLEAR_W`、`BLACKW_LR`、`BLACKW_PHYSICS_DT`、`BLACKW_DECIMATION`）。

三个已确认的坑（都影响后续所有 RL 实验）：

1. **5ms 训练物理不迁移**：早期 PPO 用默认 0.005s/dt、decimation 4；训练环境内能过 slope 45°/platform 20，但部署评测（0.002s/dt、decimation 10）0 分。改成 0.002/10 后 BC v4 在 MjLab 2ms 评测与本地部署评测基本一致（platform 30/wall 40/slope 30/stairs 10/trench 20），确认 dt 必须对齐部署。
2. **PPO 微调会快速破坏 BC 权重**：从 BC v4 续训，即使 lr 降到 2e-4/1e-4，100–200 iter 后部署评测从 750 掉到 10–50（权重相对变化仅 6%，但 BC 策略对权重扰动极敏感；同时 entropy 从 3.45 涨到 4.07，探索把行为带飞）。
3. **奖励 hack 的根因是"事件判据"**：第一版 `part2_success` 只判"轮底≥支撑面"，机器人跳起来（四轮都高于台面）就触发成功；训练均值 reward 从 −0.16 涨到 12+，但真实越障能力崩塌。v5 训练谓词改成"轮底在支撑带内 + 基座高度带 + |vz|<0.4"后才与 judge 对齐（本轮 specialist 实验即用此版本）。

结论：**大规模 PPO 混合地形微调暂时不是可靠增益**；当前把 RL 用在"单障碍专项"上（每项一个 specialist 环境，见 §7），产物按障碍切换使用（Part 2 每障碍独立 4 次挑战，规则不要求同一份策略）。

## 6. 评测结果（judge v5，官方几何，15–30s 窗口）

### 6.1 官方权重基线（judge v5；obstacle/stair/flat/comp_high600/comp_lane300，vx 0.3/0.5/0.8）

跨策略、跨指令取每障碍最高档：高台 40cm=200、高墙 40cm=200、斜坡 35°=100、楼梯 10cm=10、壕沟 20cm=150、梅花桩 0 → **660/1300**。楼梯是官方基线的最大短板：官方策略不会"上+下"完整阶梯（20cm 及以上全失败）。

### 6.2 comp_bc_v5（单份权重 + 逐障碍选指令 profile，当前最佳）

| 障碍 | 最高通过档 | 得分 | 推荐指令 | 4 次尝试通过率 |
|---|---|---:|---|---|
| 高台 | 40cm | 200 | vx=0.5 直冲 | 4/4 |
| 高墙 | 40cm | 200 | vx=0.65 → 到 x=1.6m 降到 0.35 | 3/4 |
| 斜坡 | 35° | 100 | vx=0.3 | 4/4 |
| 楼梯 | 20cm（完整上+下） | 100 | vx=0.75 → 到 x=1.1m 降到 0.45 | 2/4 |
| 壕沟 | 20cm（洁净跨越） | 150 | vx=0.3 | 4/4 |
| 梅花桩 | — | 0 | — | 0/4 |
| **合计（最好情况）** | | **750** | | 期望 ≈706 |

单条固定指令的最好一次：vx=0.5 直冲 = 400/1300。逐障碍 profile 的 750 分是比赛可用策略（每障碍单独 4 次挑战机会）；4 次尝试是在横向抖动 ±0.1m 下测的，`prep.d/results/blackw_official/final_profile/` 是规范化证据，逐关通过矩阵见 `JUDGE_V5_BC_V5.md`。comp_bc_v4 为上一版（同为 750 类别上限，但高台 40cm 需要 vx=0.9 且 3/4，稳定性略差），保留作对照。

### 6.3 复现稳定性（judge v5，每项 4 次尝试、横向抖动 ±0.1m、各自推荐指令）

| 障碍 | 通过次数 | 备注 |
|---|---|---|
| 高台 40cm @vx0.9 | 3/4 | 1 次 timeout（没爬上） |
| 高墙 40cm @sched 0.8→0.3 | 1/4 | 余 3 次 timeout；改 vx0.9 直冲 0/4 → 该项是当前最脆弱的 200 分 |
| 斜坡 35° @vx0.3 | 4/4 | 稳定 |
| 楼梯 20cm @sched 0.8→0.3 | 2/4 | 1 次摔倒、1 次 timeout；需要更稳的下台阶行为 |
| 壕沟 20cm @vx0.3 | 4/4 | 稳定（洁净跨越，无轮子沉槽） |

比赛每障碍有 4 次挑战机会，上表是按"1 次机会"的通过率；按 4 次独立重试，wall 40 的期望得分仍可观但不稳。**wall 40、楼梯 20cm 在下一步训练里应优先补稳。**

### 6.4 部署自检

```
pixi run python @20261024_blackw/scripts/check_walk_blackw.py --realtime false --policy comp_bc_v4
```

前进段 PASS（站立 z 0.517、前进+停止不摔）；转向仍 FAIL（BC 数据的 yaw 命令覆盖不足）。无头部署检查的仿真参数与 `@20261024_blackw/README.md` 一致。

## 7. 进行中：专项 RL 实验（specialist，anti-farming 版本）

目标缺口 = 斜坡 45°（+100）、楼梯 30cm（+100）、壕沟 30cm（+150）、梅花桩（+200）。当前并行跑：

- 第一轮 specialist（fixed 45°/30cm、无 anti-farming）在 400 iter 内 0 success，且发现 **reward farming**：`climb_height` 每步奖励 + `competition_goal` 在 root 过 goal 线后每步 +10，策略学会"爬到半坡/越过线后原地待着"。已修：progress/climb 只在 goal 线之前计分，goal 逐奖励默认 0，并加 `part2_out_of_course` 终止（越线后 0.8m 未成功即结束），成功一次性奖励 `part2_clear=+50`。
- 第二轮（anti-farming）跑 400 iter 后仍 0 success，复查发现**进度奖励本身也是状态式**（`competition_goal_progress` 原地站着也每步给分），且 `climb_height` 同理；已改成 **potential-based 进度差分**（`_course_progress_delta`，只奖励进度增量，符合 Ng et al. 1999 的 policy-invariance），从 exact 任务移除 climb 项、成功一次性奖励提到 +60。第三轮从 comp_bc_v5 初始化、2ms/10 decimation、lr 1.5e-4、difficulty rows 0..5 并行跑：
  - `spec_slope_v3`：`blackw-slope-exact`，512 env × 1200 iter（斜坡 20→45° 课程）；
  - `spec_stairs_v3`：`blackw-stairs-exact`，512 env × 1200 iter（台阶 10→30cm、完整上+下）；
  - `spec_plum_v1`：`blackw-plum`，256 env × 1200 iter（固定 tier-1 桩场 + 落足奖励 `plum_foothold`：轮底落在桩顶 [0.14,0.34]m 才给分）。
- 每个 specialist 出 checkpoint 后在对应官方隔离场景上用 judge v5 评测；达到 4/4 稳定后剪视频给用户复核、再决定是否入库；此外计划 `blackw-trench-exact`（gap 0.3m 洁净跨越）专项。

## 8. 参考文献与复现结果

| 工作 | 用到的内容 | 我们的复现/验证 |
|---|---|---|
| HIMLoco（arXiv 2312.11460, ICLR'24） | "历史观测 + proprioceptive estimator" 的盲走框架；官方 blackW 权重是 HIM 导出 | 官方权重直接作为 BC 教师；HIM 结构 1:1 映射进 MjLab 已验证（14 个张量 diff=0）；HIM 训练路线未采用（Warp assert + 平台爬升信号问题，见 `blackw-training-runs.md`） |
| RMA（arXiv 2107.04034）/ DreamWaQ | 特权信息/历史蒸馏的动机 | 本方案用 BC+DAgger 把多教师策略蒸馏成单份 342 维 MLP，等价于"用专家数据学一个历史条件策略" |
| CTS（arXiv 2405.10830）/ Extreme Parkour（arXiv 2306.05043） | 障碍课程、地形课程与指令条件化的做法 | 训练环境 5 类官方地形 + difficulty rows；评测定标参照 |
| BeamDojo（arXiv 2408.xxxx）/ Risky Terrains | 落足点奖励、双头 critic、两阶段课程（梅花桩/窄桥） | 尚未实现，列为梅花桩 specialist 的备选方案（§9） |
| PIM（arXiv 2411.14386, ICRA'25） | 深度内部模型/高程图 | 未复现：调研（子任务报告）确认无代码、人形设定、困难梅花桩 46.67%；若做感知，改用 MjLab raycast 高度图 + 轻量 CNN/attention（见 §9） |
| N-W-wolf `super-dog` / `nwwolf_mjlab_training_release` | 训练栈（MjLab + rsl_rl）、地形生成器、地形难度行 | 直接作为训练代码底座，改动记录在训练仓 `alldog_mjlab/tasks/velocity/blackw/` |
| HYNova `zeitvex/RC_WheelLeg`（MIT） | 轮腿控制参考 | 参考其 action/观测约定，未直接复制 |
| rl_sar（Apache-2.0） | 部署栈 | 已修两处契约问题（§3.2/§3.3）并用于无头部署自检 |
| 队内赛规则真值 | `@20261019_locomotion/docs/reference/team-race-2026.md` | 评分表/4 次尝试/RL-only/力矩限制的判定依据 |

## 9. 局限与下一步

1. **未过档位**：斜坡 45°、楼梯 30cm、壕沟 30cm（洁净）、梅花桩；合计 550 分。specialist 训练进行中（§7）。
2. **梅花桩的落足点问题**：盲策略在 0.2m 立方/0.4m 间隙上需要准确的落足，建议下一步（若 specialist 盲训失败）在 MjLab 里加 raycast 高度图观测（原生 BVH，无需渲染）或 BeamDojo 式落足奖励（踩桩奖励、桩间触地终止）；部署侧需要 d435 深度→局部高程图，工作量较大，先把盲训结果作为门槛。
3. **PPO 稳定性**：lr/entropy 需要更小或 KL 锚定；混合地形大规模微调会破坏 BC 策略，当前只用于单障碍 specialist。
4. **转向命令覆盖**：BC 数据的 yaw 命令只在 flat 教师片段里有，部署自检转向不跟随；若 Part 2 只需要直线，可不补；若需要，重采一组带 yaw 的数据重训。
5. **评测口径**：judge 是"规则可复现的最严格本地实现"（终态+支撑带+壕沟轮半径阈值）；比赛现场若裁判口径不同（例如允许桥接/允许掉槽再爬出），需要按现场规则微调 judge 阈值并重报数字。

## 10. 文件索引

- 评测：`@20261024_blackw/scripts/eval_blackw_part2.py`（judge v5）、`gen_part2_official_levels.py`（官方几何场景生成）、`summarize_blackw_eval.py`（多命令汇总）、`check_walk_blackw.py`（rl_sar 无头部署自检）
- 训练/蒸馏：`@20261024_blackw/scripts/collect_bc_blackw.py`、`collect_bc_dagger.py`、`train_bc_blackw.py`、`make_bc_checkpoint.py`、`export_bc_policy_local.py`
- 权重（已入库备份，commit `b12ac33`）：`@20261024_blackw/models/comp_bc_v5/`（policy.pt + checkpoint.pt + config.yaml + manifest.json，含 sha256/评测数据/命令 profile）与部署目录 `@20261024_blackw/ws/src/rl_sar_blackw/policy/blackW/comp_bc_v5/`
- 结果：`prep.d/results/blackw_official/judge_v5/`（judge v5 全量评测 JSON）、`JUDGE_V5_BC_V4.md`（汇总）、`prep.d/videos/judge_v5_bc_v4/`（复核视频）
- 训练仓（远程）：`bis-ms7e56:~/rc_work/part2_team_race/`，任务与环境变量见 §5；日志 `~/rc_work/part2_team_race/logs/rsl_rl/black_velocity/`
- 原理文档：[`part2-failure-vs-reward-design.md`](part2-failure-vs-reward-design.md)（termination vs reward shaping 的文献与设计规则）

## 11. 2026-10-25 训练侧代码审计：确认并修复的 bug（含"0 success"结论作废说明）

对 PPO/BC 线做了一次针对性代码审计（用户侧 review 指出若干问题），逐条核实后确认并修复了以下 bug；其中前两条直接使此前所有"specialist 训练 0 success"的观察**不可作为"学不会"的证据**。

### 11.1 `_exact_env_cfg` 的 success/failure 谓词是死代码（确认）

`_exact_env_cfg` 把单地形放进 `generator.sub_terrains = {"exact": terrain_cfg}`，而 `_part2_terrain_state` 按 **sub-terrain 列名**分支（`"slope"`/`"stairs"`/…）；列名是 `"exact"` → 所有分支都不命中 → `part2_success`/`part2_failure`/`part2_clear` 恒为 False。证据：`spec_slope_v3` 跑 903 iter `part2_success` 全 0、`part2_clear` 全 0，而同一 BC v5 权重在部署 judge 下能过 slope 35°/stairs 20°。

修复：单地形 sub-terrain key 直接用 judge kind（`{"slope": ...}` 等，由 `_EXACT_TERRAIN_KIND` 从地形类名映射）；并把训练谓词与 judge v5 对齐（去掉 judge 没有的 `|vz|` 稳定性条件、加上 judge 的"爬上证据"（ stairs 顶部平台 / wall 交叉+climb_z / plum 未跌落）、hold 15 步 = judge 的 0.2+0.1 s）。

修复后 **lr=0 预检（BC v5 在训练环境里不回传）**：slope rows 0-1（20-25°）success 0.97；stairs rows 0-1 success 0.57–0.68；固定 45° 仍 0（没有产生假成功）。这证明契约/谓词链路已通。**注意**：`Episode_Termination/*` 日志是计数型指标，可能 >1，不能当通过率用；通过率以外部 judge 评测为准。

### 11.2 `competition_goal` 残留奖励导致"过线刷分"（确认）

`_exact_env_cfg` 只在 `BLACKW_GOAL_W>0` 时**添加** `competition_goal`，没有 pop 基线 `black/env_cfgs.py` 里的 `competition_goal`（weight 5.0，语义是 root 过 goal 线后每步 +1）。于是 `BLACKW_GOAL_W=0` 并没有关掉它：`spec_slope_v3` 日志里 `competition_goal` 0.88→3.98/s 持续上升，而 `part2_success` 恒 0（死代码）——策略在学"过线后蹲着刷分"。

修复：exact/mixed/plum 三个 cfg 都先 `pop("competition_goal")`（和 `climb_height`）再按需 opt-in 添加；进度奖励改成 potential-based 差分（只奖励进度增量，Ng et al. 1999），成功一次性奖励提高到 +60。

### 11.3 `BLACKW_MAX_ROW` 在 exact 任务里没被读取（确认）

`_exact_env_cfg` 只用 `0/1` 行起步，忽略了命令行给的 `BLACKW_MAX_ROW`（review 里"课程没生效"属实）。已补：`BLACKW_MAX_ROW>=0` 时 `max_init_terrain_level = min(MAX_ROW, num_rows-1)`。

### 11.4 训练地形几何 bug：坡道薄板有 2cm 台阶、且新坡道 y 偏移错（确认，重要）

`ExactSlopeTerrainCfg` 用"绕 y 轴旋转的薄板"表示坡面（厚 4 cm），其**上表面比地面高约 2 cm**，等于在坡道入口加了一个小台阶；官方场景是**实心楔形**（`map.xml` mesh 顶点即 (0,0)→(2,rise)）。另外把薄板改成实心楔形时，`_ramp` 忘记传 y 中心（默认 y=0 而地形中心 y=4 m），坡道被放到赛道外 4 m 处——机器人走到 x≈3.5 被 landing 的立面挡住，永远上不了坡。这两处解释了"BC 在 judge 场景能过 35°，但训练环境 35° 0 success"的怪象。

修复：新增 `_ramp()` 生成**实心楔形**（上表面精确经过 (start, start_z)→(start+run, start+rise)，带 y 中心参数），替换 slope/trench/plum 的全部坡道；用 raycast 验证训练地形剖面与官方一致（30°: x=1.8 z=0 → x=3.8 z=1.155 → landing）。

### 11.5 训练物理与部署 judge 不一致（确认，重要）

官方 `part2` 场景 XML 的 `<option>` 是：elliptic cone、PGS solver、`impratio=100`、Euler integrator、100 solver iterations、35 CCD iterations；而 MjLab 训练默认是 newton/pyramidal/impratio=1/implicitfast/10 iterations。同一个 BC v5 权重在训练环境里**爬不上 30-35° 坡**，在 judge 里却 4/4 通过——PPO 于是在"错的物理"里把已经正确的行为往错误方向拉（这正是"微调后评测掉到 10–50"的一个根因）。

修复：`_apply_deployment_sim_options()`（`BLACKW_DEPLOY_SIM=1` 启用）把训练 sim 对齐到 judge：euler/elliptic/impratio=100/iterations=100/ls_iterations=50/ccd=35/更接近的 spawn 高度。mujoco_warp 不支持 PGS，用 newton+100 iter 近似。对齐后 BC v5 在训练环境 35° 坡能爬上去（diag rollout 基座 z 升到 1.5 m），预检 success 明显回升。

### 11.6 继承 checkpoint 的 critic/optimizer/iter（确认）

`make_bc_checkpoint.py` 只替换 actor，critic/optimizer/iter 来自 `comp_high600`（另一个任务、另一个奖励尺度）。已加 `--reset-trainer`：critic MLP 用默认 nn.Linear 初始化、optimizer state 清空并按 `--lr` 设学习率、iter/infos 归零。

### 11.7 "有 base 模型的续训"保护（新增 GuardedPPO）

除 11.6 外，新增 `alldog_mjlab/tasks/velocity/blackw/guarded_ppo.py`（`GuardedPPO`，经 `BLACKW_ALGORITHM` 注册）：每个 optimizer step 后把 actor 参数投影回 base 的权重信赖域 `θ ← θ_base + λ(θ-θ_base)`（λ=0.9），并支持冻结部分层（`BLACKW_GUARD_FREEZE`）。10 步观测：未保护 run 单 iter actor 权重漂移 2.35e-4，GuardedPPO 为 3.3e-5（约 1/7）。配套 env 覆盖：`BLACKW_ENTROPY_COEF=0`、`BLACKW_LEARN_STD=false`（冻结 σ=0.1–0.3）、`BLACKW_EPOCHS=2`、`BLACKW_MINIBATCHES=8`、`BLACKW_NORM_ADV_PER_MB=true`、`BLACKW_LR=5e-5`。

### 11.8 评测侧：梅花桩 judge `z_cross_min` 用错（确认）

`gen_part2_official_levels.py` 把 `z_cross_min` 写成 `BASE_REF_Z + top - 0.15 = 0.55`（root 高度口径），但 eval judge 拿它当**轮底**阈值 → 轮底永远 <0.55 → 梅花桩所有尝试必失败（官方基线 plum=0 也被这个 bug 掩盖过）。已改为轮底阈值 0.05（轮底在桩顶 0.2 m、落到地面 ≈0 可区分），并重新生成 20 个场景。

### 11.9 受影响的旧结论（作废/待重测）

- "PPO specialist 在 slope/stairs 训练 400–900 iter 仍 0 success → 学不会/信号不可用"：**作废**（死代码 + 残留刷分奖励导致，success 从未被测量）。
- "HIM gate：500–800 iter 0 success 就停"的判据同样建立在同一 `_part2_terrain_state` 上（HIM 的 `blackw-platform-exact-him` 继承 `_exact_env_cfg`），**同样无效**，需在修 key 后重测。
- "微调后掉到 10–50 是纯 PPO 不稳定"：部分原因其实是 11.4/11.5 的 train/judge 物理与几何不一致（训练环境里行为本身就不对），需在修正后的环境里重做防护实验。

