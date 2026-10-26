# Part 2 官方几何评测与可部署权重（PPO/BC 线，2026-10-26 更新）

> **新会话先读**：[`part2-ppo-handoff-2026-10-26.md`](handoff.md)（交接：远程状态、明天命令、开放问题）；后续计划见 [`part2-blind-depth-curriculum-plan.md`](blind-depth-curriculum.md)；详细历史在 [`part2-ppo-training-history.md`](history-experiments.md)。本文件只保留结论、方法与当前状态。

## 0. 结论速览

> **2026-10-26 独立评审修正（必读）**：本文的 750/743/“每障碍 4/4”均为 **executor 自测（judge v5）证据，未通过 Type-B 审计**；两份 BYOK+RFR 独立评审（GLM-5.3 / GLM-5.3-Flash，different-family）对 judge v5 与分数/证据链均给出 **FAIL/REJECT**：
> - G1 judge v5：无标定/对照、与 V2 judge 语义漂移、成功谓词是"高度带"而非接触、阈值自拟 → [`../../comp/audits/2026-10-26-judge-v5-G1-BYOK-GLM.md`](../../comp/audits/2026-10-26-judge-v5-G1-BYOK-GLM.md)
> - G4 分数/证据链：comp_bc_v5 无 comp/eval 三件套、750 与部署栈证据矛盾、本文数字自相矛盾（743 vs 706、高墙 3/4 vs 1/4）→ [`../../comp/audits/2026-10-26-score-evidence-G4-BYOK-GLMFLASH.md`](../../comp/audits/2026-10-26-score-evidence-G4-BYOK-GLMFLASH.md)
> - **在重跑复核前，本文 §0/§6 的 750/743/"比赛可用"等表述不得对外引用或作为选型依据**；部署相关结论见 §8。


> **验收口径（2026-10-26 更新，用户明确）**：此前文档中的 `8/8`、`16/16`、`<1%` 等通过次数/百分比均为自拟指标，已作废。现行验收 = 覆盖的初始状态×指令集内"零摔倒 + 可行子集全部穿越 + held-out 同样成立"，逐 case 报告，不设固定次数门槛；详见 `part2-ppo-execution-plan-2026-10-26.md` §0.3。



- **交付**：`@20261024_blackw/models/comp_bc_v5/`（已入库备份，commit `b12ac33`）是一份**单份、可部署**的 blackW 权重（342→512→256→128→16 ELU MLP，行动/观测完全按 rl_sar 部署契约），由官方三份 blackW 策略（obstacle/stair/flat）行为克隆 + 两轮 DAgger 蒸馏而来；部署目录 `@20261024_blackw/ws/src/rl_sar_blackw/policy/blackW/comp_bc_v5/`。
- **严格 judge v5（四轮终态判据）**：官方几何 20 关、每关单独 MuJoCo 场景、0.002s 物理、无时间限制口径下，按"逐障碍选择速度指令"的参考 profile 得分 **750/1300**：高台 40cm = 200、高墙 40cm = 200、斜坡 35° = 100、壕沟 20cm = 150、楼梯 20cm = 100、梅花桩 0。
- **同一 judge（v5）下官方三份权重 + 同样逐障碍选命令的基线 = 660/1300**（官方策略不会下 20/30cm 台阶：楼梯只到 10cm/10 分；平台 40/高墙 40/斜坡 35/壕沟 20 与自训权重持平）。自训单份权重靠"完整楼梯 20cm"多拿 90 分。
- **可部署性**：rl_sar 无头自检 `check_walk_blackw.py --realtime false --policy comp_bc_v5` 前进段 PASS；转向指令覆盖不足（数据里 yaw 只在 flat 教师里出现），属于已知缺口。
- **4 次挑战口径的期望分（未审计，不得引用）**：平台 40/斜坡 35/壕沟 20 均 4/4；高墙 40 为 3/4、楼梯 20 为 2/4（±0.1m 横向抖动下）→ 期望 ≈ 743/1300，最好情况 750。**该数字已被 2026-10-26 G4 评审判 OVERCLAIMED（与部署证据矛盾、且内部 743 vs 706 不一致）**；最低档在 judge 上均覆盖集零失败（§0.3，旧口径，亦未审计）。档位结构验证见归档 §12.2。
- **未拿到**：斜坡 45°（200）、楼梯 30cm（200）、壕沟 30cm（300）、梅花桩（200）。按用户 2026-10-26 校正：前两者属**盲可训练**（继续 gated 课程，盲侧满分 950、当前 750 的缺口就是这两项 +200）；后两者**盲不可达**（trench30 gap 0.30 m > 前后轮触地跨距一半 0.213 m；梅花桩需落足感知）→ 深度依赖项目（500 分，必须开始做）。2026-10-25/26 的审计修复与训练现状见 §5/§7，后续计划见 [`part2-ppo-handoff-2026-10-26.md`](handoff.md)。

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

用户复核视频时发现两个漏洞：①高墙/高台的判定在"基座越过某条线"时就成立，视频里后轮其实还没翻过去；②壕沟只要求 base x 穿过近/远边，轮子掉进槽里仍算过。这两个问题的共同根因是把**事件**（某一帧 base x/z 满足阈值）当成**终态**。详细的原则与文献见 [`part2-failure-vs-reward-design.md`](../20-part2-shared/failure-vs-reward.md)，结论是：judge 判负/不可恢复 → termination；judge 不度量的连续质量 → reward shaping；success 必须是"强到之后无法推翻"的终态。

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

## 5. 训练环境与关键教训（详细实验记录见归档）

训练环境：MjLab v1.6.0 + mujoco_warp（远程 `bis-ms7e56` RTX 5060 Ti），任务 `blackw-official`（几何/判据改动在独立训练仓 `alldog_mjlab/tasks/velocity/blackw/`，代码快照见 `@20261024_blackw/training/`）。地形/判据/命令/奖励全部可用环境变量覆盖；`BLACKW_DEPLOY_SIM=1` 把训练物理对齐官方 judge（euler/elliptic/impratio=100/iterations=100/ccd=35；mujoco_warp 不支持 PGS，用 newton 近似）。

曾经导致"训练看起来在学、部署却是 0"的三类坑（已全部修复，证据见归档 §11/§12）：

1. **success 谓词死代码 + 训练/评测物理不一致**：exact 任务的 sub-terrain key 写成 `"exact"`，而 `part2_success/failure` 按列名分支 → 恒为 False；同时训练坡道是带 2cm 台阶的薄板、sim 物理与 judge 不同（newton/pyramidal/impratio=1 vs PGS/elliptic/impratio=100），导致 BC 在 judge 能过 35° 坡但训练环境爬不上去。修复后 lr=0 预检：BC v5 在 slope 20–25° success 0.97、stairs 10cm 0.57–0.68。
2. **可刷分奖励**：基线 `competition_goal`（过线后每步 +5）和状态式 progress/climb 让策略学会"原地站着刷分"；已改为 potential-based 进度差分（Ng et al. 1999）+ 一次性成功奖励（+60）+ 判负 termination，并加 `part2_out_of_course` 防越线滞留。
3. **直接 full-resume 微调会破坏 BC**：旧 checkpoint 的 critic/optimizer 来自别的任务、entropy 把 σ 从 0.30 推到 0.52+；已加 `make_bc_checkpoint.py --reset-trainer`（critic 重初始化、optimizer 清空、iter/info 归零）、冻结 σ/entropy=0、以及 `GuardedPPO` 权重信赖域（单 iter 漂移 2.35e-4 → 3.3e-5）。

更早的 5ms 物理不迁移、事件式判据 reward hack 等失败记录见归档 §13。

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

单条固定指令的最好一次：vx=0.5 直冲 = 400/1300。**逐障碍 profile 的 750 分仅为 executor 证据，并非"比赛可用策略"**（G4 评审否定了这一措辞；每障碍 4 次挑战的统计证据与 comp/eval 三件套均缺失）；4 次尝试是在横向抖动 ±0.1m 下测的，`prep.d/results/blackw_official/final_profile/` 是规范化证据，逐关通过矩阵见 `JUDGE_V5_BC_V5.md`。comp_bc_v4 为上一版（同为 750 类别上限，但高台 40cm 需要 vx=0.9 且 3/4，稳定性略差），保留作对照。

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

## 7. 专项 RL 现状（2026-10-26 交接时）

- **结论先行**：改 bug 之前所有 specialist 的"0 success"不可用（谓词死代码 + 刷分，见归档 §11）；修复 + 物理对齐后，200-iter GuardedPPO pilot 能**保住**已有技能（slope m20/m40 仍过 30°/35°，stairs m20/m80/m199 过 15cm），但 **45°/30cm 仍未出现**。
- **长跑**：`guard4_{slope,stairs,plum}`（800 iter、blend 0.95、aligned physics、每 50 iter 存档）在远程关机前状态未确认（SSH 已不可达）；中途快照 model_450：slope 仅 30°/35°、stairs 仅 15/20cm。上机后先按交接文档 Step 1 做 eval-gated 复核/续跑。
- **下一步**：① 按交接 §3/§4.2 做 M0 逐档 gate 课程（固定单档 stage → 鲁棒性 gate → 热启动升档；**禁止**多难度并行混合训练），盲侧缺口 slope45/stairs30 用 exact 盲专项补；② 深度部署必须开工：D0 可见性 + rl_sar 渲染/CNN 最小链路（交接 §4.3），T30 + 梅花桩 走深度专项（§4.4）；③ 计划与依据见 [`part2-blind-depth-curriculum-plan.md`](blind-depth-curriculum.md)。
## 8. 参考文献与复现结果

| 工作 | 用到的内容 | 我们的复现/验证 |
|---|---|---|
| HIMLoco（arXiv 2312.11460, ICLR'24） | "历史观测 + proprioceptive estimator" 的盲走框架；官方 blackW 权重是 HIM 导出 | 官方权重直接作为 BC 教师；HIM 结构 1:1 映射进 MjLab 已验证（14 个张量 diff=0）；HIM 训练路线未采用（Warp assert + 平台爬升信号问题，见 `blackw-training-runs.md`） |
| RMA（arXiv 2107.04034）/ DreamWaQ | 特权信息/历史蒸馏的动机 | 本方案用 BC+DAgger 把多教师策略蒸馏成单份 342 维 MLP，等价于"用专家数据学一个历史条件策略" |
| CTS（arXiv 2405.10830）/ Extreme Parkour（arXiv 2306.05043） | 障碍课程、地形课程与指令条件化的做法 | 训练环境 5 类官方地形 + difficulty rows；评测定标参照 |
| BeamDojo（arXiv:2502.10363, RSS 2025）/ Risky Terrains | sampling 落足奖励、double critic、两阶段课程（平地 + 任务地形感知观测 → 实际地形） | 尚未实现；列为梅花桩/壕沟 30cm 的深度路线核心配方，课程见 [`part2-blind-depth-curriculum-plan.md`](blind-depth-curriculum.md) §4 |
| PIM（arXiv 2411.14386, ICRA'25） | 深度内部模型/高程图 | 未复现：调研（子任务报告）确认无代码、人形设定、困难梅花桩 46.67%；若做感知，改用 MjLab raycast 高度图 + 轻量 CNN/attention（见 §9） |
| N-W-wolf `super-dog` / `nwwolf_mjlab_training_release` | 训练栈（MjLab + rsl_rl）、地形生成器、地形难度行 | 直接作为训练代码底座，改动记录在训练仓 `alldog_mjlab/tasks/velocity/blackw/` |
| HYNova `zeitvex/RC_WheelLeg`（MIT） | 轮腿控制参考 | 参考其 action/观测约定，未直接复制 |
| rl_sar（Apache-2.0） | 部署栈 | 已修两处契约问题（§3.2/§3.3）并用于无头部署自检 |
| 队内赛规则真值 | `@20261019_locomotion/docs/reference/team-race-2026.md` | 评分表/4 次尝试/RL-only/力矩限制的判定依据 |

## 9. 局限与下一步

1. **未过档位按盲/深度划分**：斜坡 45°、楼梯 30cm 是**盲可训练目标**（当前 750 → 盲侧 950 的 +200，用 M0 逐档 + exact 盲专项继续训，不转深度）；壕沟 30cm、梅花桩是**盲不可达**（深度依赖 500 分），深度部署必须开工。
2. **壕沟 30cm 判据**：槽宽 0.3 m > 前后轮触地跨距一半 0.213 m（也 > 轮径 0.206 m）、judge 只允许轮底下沉 0.103 m → 盲不可达；盲感知"前轮突降"无法区分窄槽/台阶/高台边缘，视觉（深度）是解法。
3. **梅花桩盲策略大概率不可行**：0.2m 桩、0.4m 缺口需要落足感知；走深度 + BeamDojo 式课程（plan §4）。
4. **PPO 保护机制已验证能防退化但不能快速长新技能**：后续考虑 BC 正则/残差/LoRA/更长的 gated 课程（交接文档 §4 风险与备选）。
5. **转向命令覆盖不足**（BC 数据里 yaw 只在 flat 教师片段出现）；Part2 以直线为主，暂缓。
6. **评测口径**：judge 是本地最严格实现；现场若口径不同（允许桥接/掉槽再爬出等）需按现场规则微调并重报数字。Type-B Codex 审计当前不可用（见 `comp/audits/2026-10-25-judge-v5-G1-REVIEW_UNAVAILABLE.md`），分数只作 executor 证据。
## 10. 文件索引

- **交接/计划**：[`part2-ppo-handoff-2026-10-26.md`](handoff.md)（明天上机步骤、命令、远程状态、开放问题）、[`part2-blind-depth-curriculum-plan.md`](blind-depth-curriculum.md)（模型分叉、盲课段 B0–B4、深度 BeamDojo 课程 D0–D5）
- **归档**：[`part2-ppo-training-history.md`](history-experiments.md)（训练侧 bug 审计与修复证据、最低档/档位结构验证、显存实测、早期 specialist 记录）
- **评测**：`@20261024_blackw/scripts/eval_blackw_part2.py`（judge v5）、`gen_part2_official_levels.py`（官方几何场景生成）、`summarize_blackw_eval.py`（多命令汇总）、`check_walk_blackw.py`（rl_sar 无头部署自检）
- **门控/诊断**：`@20261024_blackw/scripts/check_tier_success.py`（最低档/canonical+随机化成功率）、`check_tier_geometry.py`（档位结构无质变检查）、`diag_rollout.py`（训练环境 rollout 诊断）、`gpu_budget_check.py`（可选的手动显存/进程检查；算力机已启用 GPU 队列，正常训练按队列提交即可）
- **训练/蒸馏**：`@20261024_blackw/scripts/collect_bc_blackw.py`、`collect_bc_dagger.py`、`train_bc_blackw.py`、`make_bc_checkpoint.py`（含 `--reset-trainer`）、`export_bc_policy_local.py`
- **训练侧代码快照**：`@20261024_blackw/training/`（env_cfgs.py / exact_terrain.py / guarded_ppo.py / black_config.py / rl_cfg.py，对应远程仓 `~/rc_work/part2_team_race/src/`）
- **权重（已入库备份）**：`@20261024_blackw/models/comp_bc_v5/`（policy.pt + checkpoint.pt + config.yaml + manifest.json，含 sha256/评测数据/命令 profile）与部署目录 `@20261024_blackw/ws/src/rl_sar_blackw/policy/blackW/comp_bc_v5/`
- **结果/视频**：`prep.d/results/blackw_official/`（judge v5 全量 JSON、final_profile/、audit_fix/）、`prep.d/videos/comp_bc_v5/`（复核视频）
- **远程训练仓**：`bis-ms7e56:~/rc_work/part2_team_race/`；日志 `logs/rsl_rl/black_velocity/`
- **原理文档**：[`part2-failure-vs-reward-design.md`](../20-part2-shared/failure-vs-reward.md)（termination vs reward shaping 的设计规则与文献）
## 11. 历史与归档

详细审计/验证记录不再放在主报告里，见 [`part2-ppo-training-history.md`](history-experiments.md)：§11（训练侧 bug 审计与修复）、§12（最低档/档位结构/课程/显存验证）、§13（早期 specialist 训练记录，含已作废结论说明）。

## 8. 独立评审后的证据修订（2026-10-26）

- **评审结论**：G1（judge v5）与 G4（分数/证据链）均 FAIL/REJECT，见 [`../../comp/audits/2026-10-26-BYOK-RFR-SUMMARY.md`](../../comp/audits/2026-10-26-BYOK-RFR-SUMMARY.md)。
- **750/743 的降级**：本文所有 judge v5 分数改为"未审计 executor 证据"；不得用于选型、对外引用或冻结。要恢复为可引用数字，至少需要：① judge v5 通过 G1 复验；② comp_bc_v5 的 judge v5 逐 attempt 原始 JSON 导入 comp/eval 三件套并由 `comp_score.py` 重算；③ 4 次尝试/命令 profile 的统计口径统一。
- **数字矛盾修正**：§6.2 的 743 与 §6.3 的 706 是不同命令面统计，后续只保留一份计算式；高墙 3/4 与 1/4 分别是 `vx 0.65→0.35` 与 `0.8→0.3` 两个 profile，不得混引（见评审证据）。
- **部署证据更新**：旧部署 smoke 的 5/20 已作废（deploy levels 误用旧 proxy `part2_*.xml`，judge 用官方 `part2_off_*.xml`；20/20 不一致，已修 `part2_levels.json`）。官方场景重跑：`comp_bc_v5` **10/20 档（折算 best-case ≈400/1300）**，官方 `obstacle` 权重对照 **10/20（≈400）**，无数值爆炸。**judge 750 与部署 400 的差距待逐 case 解释；不得用 750 宣称"可部署能力"。**
- **合规**：轮腿构型/力矩表是否覆盖轮关节、4 次尝试的官方语义、judge 自拟阈值（hold 0.3 s、gap 下沉 0.103 m、wall climb_z_min 等）均需主办方书面确认后方可冻结。
