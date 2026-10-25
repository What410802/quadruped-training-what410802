# Part2 无视觉阶段与深度相机阶段的模型分工与课程规划（2026-10-26 计划）

> 起因：壕沟 30 cm 档位存在"前轮突然降低"的本体感知歧义（可能是在高台上要下台阶，也可能是要跨过的窄槽）。本文先量化该歧义与可行解法，再给出无视觉阶段的模型/课程安排，以及上深度相机 + BeamDojo 后的课程顺序。规则依据 [`reference/team-race-2026.md`](../reference/team-race-2026.md) §3：赛项二每障碍最多 4 次、取最高档、不计时、可跳过；**仅允许 RL**（不能写固定动作）；actor 输入允许 IMU/编码器 + **相机/雷达**（必须模拟真实传感器），禁止 heightmap/足底力/机身高度等传感器；critic 用特权信息可以。当前交付：`comp_bc_v5` judge v5 下 750/1300（[`part2-bc-policy-report.md`](part2-bc-policy-report.md)）。

## 1. 场景分析：壕沟的"前轮下降"为什么是歧义

官方沟壑几何（`map.xml`）：入口 1 m 坡（0→0.30 m）→ 1 m 近台 → 槽（宽 10/20/30 cm，深 0.30 m）→ 1 m 远台 → 出口 1 m 坡；judge 规则：任一轮子进入槽区且**轮底低于 `plateau_z − min(0.5×0.30, r)=0.197 m`** 即判负（r=0.103 m）。

按几何算，轮子能否"滚过"槽：

| 槽宽 | 轮径 2r=0.206 m | 滚动跨槽时轮底最大下沉 | judge 允许下沉 min(0.15, r)=0.103 | 结论 |
|---|---|---|---|---|
| 10 cm | 2r > 槽宽 | ≈0.013 m | 0.103 m | 可滚过（BC v5 实测 4/4） |
| 20 cm | 2r > 槽宽 | ≈0.078 m | 0.103 m | 可滚过（BC v5 实测 4/4） |
| **30 cm** | **2r < 槽宽** | 轮子会整个掉进槽（底部接近地面） | 0.103 m | **不可能滚过，必须腾空/跨步** |

关键事实：
- 30 cm 档（300 分）**必须让轮子离开槽面**（前轮抬起跨过去，或整体小跳）；这不是"谨慎下台阶"能解决的，是**定性的新技能**。
- 盲策略的"前轮突然下降"信号是**姿态/轮速本体感知**，它同时出现在：沟壑槽、台阶下沿、高台边缘、坡道下行。信号本身无法区分；且轮子进入槽后约 0.14 s 就掉到 0.1 m 深，靠"掉下去再反应"来不及把 0.3 m 宽槽跨过去。
- 但**场景是固定的**（官方能力场几何固定、每障碍独立尝试、不计时），所以有两个可行方向：① 按障碍切换**专项策略**（把"壕沟"当成独立任务，可以学到"计时/步态跨槽"）；② 上**深度相机**（槽在 3.8 m 前方，相机 0.53 m 高、下俯 15°、fovy 70°，槽在俯角约 8°处，落在视野内，视觉直接消除歧义）。

## 2. 是否要模型课程分叉：建议"主线 + 专项"分叉

**规则允许**：赛项二不要求同一份策略；每障碍独立 4 次挑战、可切换策略；rl_sar 本就支持 `policy_name` 切换（`policy/blackW/<name>/`）。因此推荐：

| 模型 | 负责 | 部署形态 |
|---|---|---|
| **M0 主线（盲）** | 普通行走 + 平台/高墙/斜坡/楼梯 + 沟壑 10/20 cm（可滚过） | 单份盲策略（现有 comp_bc_v5 谱系），主用 |
| **T30 壕沟 30 cm 专项** | 沟壑 30 cm（300 分）：抬前轮/小跳跨槽 | 盲专项或深度专项，单独切换 |
| **S45 / St30 专项（按需要）** | 斜坡 45°（200）、楼梯 30 cm（200） | 单独切换 |
| **P 梅花桩专项** | 梅花桩（200）：0.2 m 桩、0.4 m 缺口 | 建议直接走深度路线 |

理由：
1. 30 cm 槽需要"腾空/跨步"技能，与 M0 的"滚过/谨慎下台阶"行为冲突；同一策略混训时，drop 信号歧义会把行为拉向平均（我们已实测：BC v5 能过 10/20 cm，30 cm 必失败）。
2. 规则允许切换、每障碍独立计分，专项化是当前 4 次机会/不计时规则下最省样本的路线；M0 不必被 30 cm 拖累。
3. **单策略 fallback**（若最终必须一份模型）：可训"通用 drop-safe 反射"——任何"前轮接触丢失/高度突降"都先抬前轮、不深陷、再落下；该行为对台阶/高台下沿安全，对 10/20 cm 槽等效滚过。但它对 30 cm 槽需要提前 0.2–0.4 s 触发，盲感知大概率不够，只作为兜底；真正的单策略解需要视觉。

## 3. 无视觉阶段（现在 → 深度链路可用前）训练与课程规划

### 3.1 总原则

- 每个障碍单独一个 exact 地形任务（现有 `blackw-*-exact` + `blackw-plum`），**手工 success-gated 课程**（mjlab 自带 `terrain_levels_vel` 按距离升级，与 goal 终止的障碍 episode 不兼容，训练时已 pop，见归档 [`part2-ppo-training-history.md`](part2-ppo-training-history.md) §12.3）。
- 升级门控：部署对齐环境（`BLACKW_DEPLOY_SIM=1`，官方场景物理近似）上 canonical + 随机化各 ≥100 episodes；deterministic ≥95%、随机化（初始状态 + 指令 + DR）≥90% 才升档/加宽指令；每档 judge 复核（warp 成功率只作下界，判定以 judge 为准，原因见归档 [`part2-ppo-training-history.md`](part2-ppo-training-history.md) §12.1）。
- 随机化：初始状态（root x±0.10、y±0.15、yaw±0.05；关节 offset/速度；现有 DR 保留）、指令（真实手柄线性映射：`joy_command_scale=1.5`，`rl_sim.cpp:394-396` axes→vx/vy/yaw；障碍训练 vx∈[0.2,0.8]、vy±0.2、wz±0.3，另留满杆上界测试）。
- 奖励：potential-based 进度差分 + 一次性成功奖励 ≥60 + 判负规则用 termination（壕沟"轮沉超限"判负）；不用状态式 goal/climb 刷分项（详见归档 [`part2-ppo-training-history.md`](part2-ppo-training-history.md) §11）。

### 3.2 阶段安排

| 阶段 | 任务/模型 | 课程 | 目标 |
|---|---|---|---|
| B0 | M0 主线（盲） | 以 comp_bc_v5 为起点；platform 10→40 / wall 10→40 / slope 20→45（但 45° 可留待专项）/ stairs 10→20（30 留专项）/ trench 10→20 | 保持 750 基线不再退化；4 次挑战稳定性 wall40≥3/4、stairs20≥3/4 |
| B1 | T30 专项（盲） | 固定 30 cm 槽；**起点位置随机化 ±0.2 m**、速度 0.2–0.5 m/s；rewards：跨槽成功 + 轮沉判负 + 进度差分；后期加"从不同接近速度触发"的随机化 | 先验证盲策略能否学到"抬前轮跨槽"；成功率≥90% 才进部署评测 |
| B2 | S45/St30 专项（盲，可选） | 固定最高档；gated 训练 | 45°/30 cm 若 400–800 iter 仍 0，则明确留待深度 |
| B3 | P 专项（盲，只做门槛判断） | 官方 tier-1 桩场固定 | 若盲策略 ≤10%，直接停，转深度路线（预计如此） |
| B4 | 合并/切换部署 | M0 + 可用专项；`vision` 未就绪时按障碍切换 policy_name；评测每障碍 4 次 | 先拿稳 750 + 任何新档位 |

**时间**（距 2026-11-04 约 9 天，11-01 前先攻分数）：B0/B1 并行 2–3 天；B2/B3 各 1 天为门槛；深度链路（§4）与 B1/B2 并行开发；10-31 做一次"当前最高分"冻结/录像，11-01 后只做稳定性和演示。

### 3.3 每类专项的训练细节

- **T30（关键新技能）**：固定 difficulty=1.0、`BLACKW_DEPLOY_SIM=1`；起点 x/y/yaw 随机、vx 0.2–0.5；观测用现有 57×6 历史；reward = 进度差分 + 成功一次性 + 轮沉即判负；先 200 iter 观察是否有"抬轮"倾向，再决定是否继续或转深度。若盲策略学到"踩边跨过"（前轮压在远台边缘、后轮跳上），即算成功（judge 只要求四轮最终都在远台面且不判负）。
- **M0 主线**：以现有 comp_bc_v5 为 base（不要从零），用 GuardedPPO（权重信赖域）+ 冻结 σ + entropy=0 + 小 lr 做 100–300 iter 门控微调；每 50 iter judge 评测（platform/wall/slope/stairs 各 4 次），掉分回滚。**目的不是冲新档，而是把 wall40/stairs20 从 3/4、2/4 提到稳定 4/4**。
- **P 梅花桩**：盲策略只做"能不能过 10% 门槛"的验证；预计不过，直接进深度阶段。

## 4. 深度相机 + BeamDojo 阶段课程规划

### 4.1 已有基础（训练仓实测，见 [`camera-depth.md`](camera-depth.md)）

- mjlab 1.6 原生深度相机：`CameraSensorCfg(data_types=("depth",))`，无 EGL，走 mujoco_warp 渲染，与 raycast 共用 sense graph；
- 现有 depth task：45 proprio + 64 维 CNN latent，CNN 输入 **48×64** 深度图；相机在 `robot/d435_link`（前 x≈0.235 m、高≈0.53 m），fovy 70°、**下俯 15°**、深度 0.1–3.0 m、只渲染地形 group（机器人本身不遮挡）；训练加 ±0.02 均匀深度噪声；
- 成本：depth 相对 blind ×1.54（500-iter 对照，[`camera-depth.md`](camera-depth.md) §5/§7），可接受；
- **部署缺口**：rl_sar 控制栈当前没有深度相机/CNN 推理链路，需要补 MuJoCo 相机渲染 + CNN TorchScript 推理 + 观测对齐（这是 D0）。

### 4.2 BeamDojo 的可借鉴点（arXiv:2502.10363, RSS 2025）

BeamDojo 解决"人形稀疏落脚点"的三件事：
1. **sampling-based foothold reward**（针对多边形脚掌的落足采样奖励）；
2. **double critic**：一个 critic 学 dense locomotion return，一个学 sparse foothold return，平衡两类奖励；
3. **two-stage RL**：stage 1 在**平地动力学**上训练、但给策略喂**任务地形的感知观测**（先学会"看"）；stage 2 到实际地形 fine-tune；真机用 onboard LiDAR elevation map。
→ 对我们的映射：actor 用**深度相机**（合法），critic 可用 privileged heightmap/足底接触（合法）；"感知 → 落足/跨槽 → 实地形 fine-tune"的课程顺序可以直接复用。

### 4.3 深度阶段课程（D0–D5）

| 阶段 | 内容 | 关键实现 | 门控/验收 |
|---|---|---|---|
| D0 | 基础设施 + 可见性验证 | 把 depth task 移植到 `part2` exact/mixed 地形；渲染 trench/platform/stairs/plum 场景深度图，确认 3.8 m 处 10/20/30 cm 槽、桩间隙在图中可分辨（48×64 下单槽可能只有 1–3 像素垂直高差；不够就升到 80×128 或在 body 系重建 ego 高度图） | 可视化 + 深度统计（槽区像素深度跳变） |
| D1 | 感知预训练（BeamDojo stage 1 风格） | 平地/低难度动力学 + 任务地形感知观测（相机看到真实障碍，机器人先在简单地形上走）；actor 用 CNN，trunk 从盲 M0 初始化，CNN 随机；先冻结 blind trunk 训 CNN 50 iter，再解冻联合训练 | 在低档 platform/stairs/slope 上达到盲策略水平 |
| D2 | 特权 critic + foothold reward + 双 critic | critic 用 heightmap/足底接触（合法）；T30/P 加 BeamDojo 式 foothold/落点奖励；double critic（dense + sparse foothold 两个 value）；plum 地形课程：大平台→小桩→官方 0.2 m 桩、间隙 0.1→0.4 m | plum 通过率从 0 提到可测；T30 轮沉判负下降 |
| D3 | 实际任务地形 fine-tune（BeamDojo stage 2） | 官方 trench30 / plum 实际地形；gated 难度；GuardedPPO/BC 正则保护已有技能；每 25–50 iter judge 评测 | T30 4 次挑战 ≥3/4；P ≥2/4 |
| D4 | 蒸馏/合并与切换 | 深度策略与盲 M0 按障碍切换；若最终要求单模型，用 DAgger 把深度策略蒸馏回单份 CNN 策略；保留盲 fallback | 单份/切换两种部署形态都跑通 judge |
| D5 | 部署整合 | rl_sar：MuJoCo 相机 → 深度图 → 归一化（与训练同参数）→ **ego 高度图重建（body 系 1.2×1.2 m、5 cm 分辨率，由深度反投影，合法因为来自相机）** → CNN/MLP TorchScript 推理；对齐 MjLab 渲染与 MuJoCo 渲染的差异（同一场景对拍深度统计）；延迟 <10 ms | 仿真部署自检 + 全 6 障碍评测 |

### 4.4 关键设计建议

1. **不要把原始 48×64 深度图直接喂 CNN 当作唯一方案**：槽宽 0.1 m 在 3.8 m 处只有 1–2 像素，建议同时做 **depth→ego height map**（点云反投影到 body 系格点，17×24 左右），CNN/MLP 在其上判断"前方是否有窄槽、槽宽多少、何时跨"；BeamDojo 真机也是 LiDAR elevation map。
2. **T30 的触发**：深度可提前 1–3 m 看到槽，策略可以学"看到窄槽→减速/抬前轮/跨步"；比盲策略的"掉下去再反应"（0.14 s）宽裕得多。
3. **规则合规**：相机/雷达必须"模拟真实相机"，禁止直接接入 heightmap 传感器；**由深度相机推导的 ego 高度图/点云属于相机处理，可进 actor**（与 PIM/BeamDojo 真机做法一致）；heightmap 只进 critic。
4. **渲染域差异**：训练用 mujoco_warp 渲染，部署用 MuJoCo/EGL；深度图统计（噪声、边缘、缺失值）要在两个渲染器上对拍，训练端加噪声/缺帧/遮挡增强（模拟真实 d435）。
5. **深度下坡/下台阶的歧义仍在**：但相机能区分"宽地面下降"（台阶/高台）与"窄槽"（沟壑）——这正是视觉要解决的核心问题；训练数据里要同时出现两者，避免 CNN 把"深度跳变"一律当槽。
6. **成本**：depth 训练 ×1.54、CNN 推理 <10 ms，在 8GB/线显存协议下用 256–512 env 可跑（见归档 [`part2-ppo-training-history.md`](part2-ppo-training-history.md) §12.4）。

## 5. 风险与备选

| 风险 | 影响 | 备选 |
|---|---|---|
| 盲 T30 学不会（轮沉判负太严） | 300 分丢失 | 直接走深度 D2/D3；或先只保 10/20 cm 档（150 分） |
| 深度渲染/部署链路来不及（rl_sar 无 CNN） | 深度模型无法部署 | 11-01 前以盲 M0 + 切换策略冻结分数；深度作为答辩内容/后续 |
| 48×64 深度分辨率看 0.1–0.3 m 槽不够 | D1/D2 学不到 | 升到 80×128 或用 ego heightmap；增加俯仰/ROI |
| 域差异（warp 渲染 vs MuJoCo 渲染） | 部署掉点 | 双渲染器对拍 + 噪声增强；必要时训练用 MuJoCo 渲染（离线生成深度数据集）做 DAgger |
| 规则解释风险（把相机推导高度图当"heightmap 传感器"） | 被判违规 | 保留纯深度 CNN 版本作为合规底线；答辩时说明来自相机、且规则只禁 heightmap 传感器 |

## 6. 下一步（按优先级）

1. **今天/明天**：M0 门控微调把 wall40/stairs20 稳定到 4/4；T30 盲专项 200–400 iter 门槛实验（同时验证 `blackw-trench-exact` 在 30 cm 下轮沉判负/成功判据）。
2. **并行**：depth task 移植到 `part2` exact/mixed + 可见性 smoke（槽/桩在深度图中是否可分辨）+ D0 部署侧 MuJoCo 相机渲染 demo。
3. **10-28 前**：若 T30 盲失败 → 启动 D1/D2；若成功 → 继续 B0/B2。
4. **11-01 前**：把当前最高分（M0 + 已过专项）冻结、录像、入库；深度路线成果作为增量。

## 7. 参考

- 规则真值：[`reference/team-race-2026.md`](../reference/team-race-2026.md)
- 评测与 judge：[`part2-bc-policy-report.md`](part2-bc-policy-report.md)、[`part2-failure-vs-reward-design.md`](part2-failure-vs-reward-design.md)
- 深度链路实测：[`camera-depth.md`](camera-depth.md)
- BeamDojo: Wang et al., *BeamDojo: Learning Agile Humanoid Locomotion on Sparse Footholds*, RSS 2025, [arXiv:2502.10363](https://arxiv.org/abs/2502.10363)
- 队内赛 GPU 共享协议与容量实测：归档 [`part2-ppo-training-history.md`](part2-ppo-training-history.md) §12.4；启动检查 `@20261024_blackw/scripts/gpu_budget_check.py`
