# 训练计划与方法论

> **2026-10-21 任务真值校准**：当前主目标是 **2026-11-04 队内赛**（障碍赛 + 越障能力测试，见 [`../reference/team-race-2026.md`](../00-competition/rules-team-race-2026.md)）；下面的 S0–S4 是研究性 pipeline，不再当作比赛主进度。比赛路线见 §0。阶段状态在 [`status.md`](../status.md)；地形尺寸在 [`materials.md`](terrain-materials.md)；论文与代码索引在 [`literature.md`](../40-reference/literature.md) 与 [`open-source.md`](../40-reference/open-source.md)。

## 0. 2026-11-04 队内赛路线（2026-10-21 校准）

真值：赛项一障碍赛遥控满分 900（8×100+返回 100），赛项二能力测试满分 1300；两项和 70%，答辩 30%；14 天。详细规则见 [`../reference/team-race-2026.md`](../00-competition/rules-team-race-2026.md)，逐项差距见 [`../status.md`](../status.md)，地形资产与修改项见 [`../terrain/competition-assets.md`](terrain-assets.md)。

| 优先级 | 时间窗 | 目标 | 产出/验收 |
|---|---|---|---|
| P0 比赛闭环 | 10-21 ~ 10-23 | 正式障碍场/能力场 task、官方成功/计分判定器、手动部署接口、传感器/力矩审计 | judge 设计见 [`competition-judge.md`](../00-competition/judge-design.md)；能在官方障碍/能力图上跑 `flat-ft-2500` 并出得分；禁用传感器不进 actor |
| P1 基础越障 | 10-23 ~ 10-27 | 斜坡、楼梯/T 台阶、高台 10–20 cm | 先接手动状态机保底（[`manual-fallback-state-machine.md`](../00-competition/fallback-state-machine.md)）；逐障碍通过率/得分 |
| P2 赛项一 | 10-26 ~ 11-01 | 绕杆、限高杆、高墙、木桥 A/B、砂砾碎木坑 | 按得分/风险选尝试项；手动（或用户批准的局部自动/固定动作） |
| P2/P3 能力测试 | 10-28 ~ 11-02 | 沟壑、高墙、梅花桩、高档高台/楼梯/斜坡 | 每项 4 次，优先中档分数；仅 RL |
| P3 整合答辩 | 11-01 ~ 11-04 | 整场尝试、恢复、操作手练习、冻结权重、7 分钟答辩 | 最终权重/得分记录/PPT |

- **冻结研究性改动**：比赛前不再做 flat 美化、长周期 HIM/非对称 AC、sim2sim、rough 数值安全长跑；这些都进 research backlog。
- **复用资产**：`flat-ft-2500` 作 flat 基线；固定/自由砂砾作“碎木坑”代理起点；训练/评测/渲染/踩入实验工具继续用。
- **比赛成功判据不是速度跟踪**：障碍要按 PDF 的“1/2 足接触地面即失败”“每级台阶至少一次足接触”“限高杆不能掉”“返回启动区”等定义单独实现 evaluator。
- **运行时先手动保底**：flat/loose/limit_bar/bridge/stairs/high_wall/slope/slalom 状态机；judge 只做外部计分；flat 与 loose 语义分开，可暂时共用策略。见 [`manual-fallback-state-machine.md`](../00-competition/fallback-state-machine.md)。
- **赛项二仅 RL**：不能写固定动作；赛项一允许固定动作/局部自动但无额外分，是否使用待用户确认。
- **相机分阶段**：P0/P1 先盲策略；P2 后做深度 teacher/student + DR；最终版保留相机，不现在把相机塞进 actor。
- **传感器红线**：部署 actor 只用 IMU+编码器（+可选相机/雷达）；height scan/foot force/foot height/body height 等不能进 actor。当前 45 维 actor 合规，但不能把 critic 的 height scan 直接接到部署网络。
- **答辩 30%**：至少预留 1 天整理奖励/论文/机制/对比实验，不能全部时间用来追最后一个 checkpoint。

## 1. 阶段总览（研究性 pipeline，非比赛主进度）

| 阶段 | 目标 | 通过标准（初定，待任务书校准） | 产出 |
|---|---|---|---|
| S0 材料与环境 | 地形/资源确定，mjlab 接入方案，远程训练环境，C++ 视窗，TensorBoard | 地形单帧可视化尺寸与规则一致；远程冒烟训练通过；本地能看场景 | 本任务文档 + `cpp/scene_viewer` + 原生 uv 训练环境 |
| S1 基础模型 | 平地 + 光滑/粗糙/碎石地面；站立、前后/横移/转向、小跑、平滑切换 | 平/糙地速度跟踪误差达标、长时间不摔；指令平滑切换不摔、恢复时间可量化；碎石地形通过率记录 | 第一版 TorchScript 策略 + 实验记录 |
| S2 台阶与梅花桩 | 上/下 T 字形台阶、单级/多级台阶、梅花桩阵 | 逐地形通过率/摔倒次数/用时；台阶满足“每级顶面至少一次足底接触”；梅花桩不掉桩 | 第二阶段策略 + 逐地形评测表 |
| S3 鲁棒性 | 域随机化、外扰、非理想电机、sim2sim | 在固定压力测试下性能退化可量化且可接受；sim2sim 与训练环境行为一致 | 压力测试报告 + 最终候选权重 |
| S4（按需） | 相机/深度、teacher-student、多策略/多专家 | 相机版本在仿真与实机延迟预算内、不低于盲策略基线 | 视觉版策略/报告 |

## 1.5 建议推进顺序：基线优先，实验后置（2026-10-20，待确认）

先跑通既有基线（现有课程 + 奖励），再跑台阶/梅花桩，最后回头做“更本质优化”实验——这个顺序总体合适，但建议把它定义成 **pipeline 验证优先，而不是成绩调优优先**：

1. **冻结评测协议**：固定命令 suite、起点/地形、种子、通过判据、导出/回放流程；先记录“基线”三个数字：速度跟踪误差、摔倒/卡死次数、逐地形通过率（平/坡/粗糙/刚性碎石/低摩擦）。
2. **复现 flat 基线**：`black-flat` + 现有 10 项 reward + command curriculum，从零训练（建议 4096 envs，先 1–2k iteration 看曲线，再按需延长）；导出 `policy.pt`，用本地 MuJoCo/C++ 视窗确认可回放、可换策略。
3. **复现 rough 基线**：从 flat checkpoint full resume 到 `black-rough`（现有 terrain generator 已含坡/粗糙/离散障碍/金字塔 stairs up/down），验证 terrain curriculum；**不修改 reward/curriculum**，只记录表现。
4. **台阶/梅花桩诊断性集成测试**：把 2026 T 台阶、2027 沟壑/梅花桩作为自定义地形接进训练仓库；用现有基线策略做 1–3 episode 推理评测，检查地形/height scan/碰撞/终止/回放，目标是暴露“现有手工设计在哪里不够”，**不训练、不调参**。blind 基线在这些离散地形上表现差是预期结果，不代表失败；结果标为 `diagnostic`，不计入台阶阶段成绩。
5. **正式台阶/梅花桩训练**：只在 [`eval-protocol.md`](eval-protocol.md) §6.1 的 H1–H4 通过后启动；建地形课程、按阶段训练，并用逐地形通过率评测。rough 的 legacy 配置不阻塞这一步，但 rough-flat 拆分与数值安全要按 H2/H5 记录。
6. **再做优化实验**：在 flat 上跑 A/B/B+约束/C 对照（见 [`training-baseline.md`](baseline.md) §5），确认“不差于手工基线”后，把赢家带到台阶/梅花桩；每一组都复用第 1 步冻结的评测协议。
7. **最后做 DR/鲁棒性与 sim2sim**。

这样排的理由：先有可复现基线和端到端管线，后面的实验才有可信对照；同时用台阶/梅花桩的“诊断性集成测试”暴露管线问题，而不是在基线上做大量会被后续设计推翻的调参。诊断测试可以早做，但**正式训练不跳过 H1–H4**：flat 硬故障、数值崩溃、契约/地形管线错误必须先解决，否则台阶训练的失败无法归因。风险是“等待实验”的时间变长；缓解办法是把实验开关（reward profile）、台阶/梅花桩地形和评测脚本在基线训练期间并行准备好，基线一通过就开跑。

## 2. S1：基础模型（平地/粗糙/碎石）

- **动作与观测契约先冻结**：沿用队内训练仓库的 45 维 obs（命令 3 + 角速度 3 + 重力投影 3 + 关节位置 12 + 关节速度 12 + 上一动作 12）、12 维动作、`kp=40/kd=1.2`、策略 50 Hz（物理 5 ms × decimation 4）、动作尺度 0.25；HIM 变体为 6 帧 ×45。**不要在 S1 改契约**，否则和 `best.pt`、rl_sar 部署口径没法对照。
- **命令与平滑切换**：命令 = `(vx, vy, wz)`，训练时按范围随机、周期性重采样，并保留一定比例的零指令（站立）；“平滑切换”不是单独技能，而是命令阶跃下的表现——评测时专门做 0 → 走（0.4–0.6 m/s）→ 小跑（1.0–1.5 m/s）→ 横移 → 转向 → 0 的阶跃序列，记录超调、恢复时间、是否摔倒；训练侧用命令重采样分布、动作变化率/力矩平滑惩罚、足端 air time 与接触模式奖励来改善。
- **“平地”的宏观定义（2026-10-21 提案）**：最高起伏 < 狗质心离地高度的 **1/3**（Black 约 0.14 m）算平地（2026-10-21 先取 1/3）；低 curb/基座和 3–8 cm 碎石都归入平地，高围栏不算；定义与实例见 [`eval-protocol.md`](eval-protocol.md) §6.3。
- **地形**：先 100% flat 复现 `black-flat` 训练；S1b 做两套砂砾：`black-gravel-flat`（固定 heightfield 代理，50% flat + 30% 细砾石 + 20% 粗砾石，无台阶/离散障碍）**批量预训练**，`black-gravel-free`（6 cm 预烘焙基座 + 120 自由碎石 + 700 静态预沉降石、3–8 cm，4–8 envs）**小 batch 微调/评测**；真正的 rough（`HfRandomUniform`/`HfPerlin` + `HfPyramidSloped`）与 obstacle 地形留到 rough-flat/台阶阶段。
- **关于 rough 里的阶梯（2026-10-20 明确）**：最初设计 rough 只放“粗糙/砂砾等异形平地”，但训练仓库现有 `black_rough_terrain_generator_cfg()` 是 legacy super-dog rough 配置：flat 0.10、smooth slope up/down 各 0.05、rough slope 0.10、discrete obstacles 0.20、stairs up/down **各 0.25**。其中 stairs/discrete 主要是为了鲁棒性与兼容原基线，不是“粗糙平地”最终效果目标；实际训练也显示 `stairs_down` 从 2.5 掉到 0.85、`discrete_obstacles` 到 1.51，占 45% env 却长期学不会（[`training-health.md`](health.md) §4）。
- **建议**：rough 阶段拆成 “rough-flat（平/坡/粗糙坡/碎石/低摩擦）” 与 “obstacle（台阶/梅花桩/沟/桥）” 两套 generator/课程；在 rough-flat gate 通过前不要把 50% stairs 混进来。若暂时保留 stairs 作鲁棒性，至少先降比例并单独看分地形 level，不要把它的失败算成 rough-flat 的失败。**2026-10-21 已实现第一个拆分：`black-gravel-flat`（无台阶/离散障碍）**，命令范围可显式从 ±1 起步（`--agent.command-curriculum-restore none`），不要直接继承 flat 的 ±2。
- **域随机化（先轻后重）**：摩擦、基座质量/负载、电机强度/延迟、观测噪声、间歇推力；先保证能学会，再逐步加宽；每加一档都做对照实验，记录性能与曲线。
- **特权信息**：训练仓库已有 `terrain_scan`（17×11 = 187 条射线，帧 `trunk`）作 critic 的 height scan；S1 先跑“actor 盲 + critic 特权”的基线，与 HIM（历史估计）对照，决定后续主线。
- **评测**：速度跟踪误差（线性/角速度）、摔倒率、存活时长、力矩/功率/平滑度、足端滑移；固定一组命令序列与随机种子，在本地 MuJoCo（CPU）上用导出策略复跑。

## 3. S2：台阶与梅花桩

- **启动门槛**：正式训练需先过 [`eval-protocol.md`](eval-protocol.md) §6.1 的 H1–H4；在此之前只做诊断性推理评测，训练阶段不启动。
- **地形实现**：按 [`materials.md`](terrain-materials.md) §4 的映射，在训练仓库 `terrain.py` 里加自定义 `SubTerrainCfg`：
  - 台阶：先单级/低台阶 → T 字形台阶（2026：总高 400、级高 120、级深 320、宽 1900）→ 上行/下行组合；训练侧可先用“重复横台阶”加快学习，再换按规则的 T 字形布局。
  - 梅花桩：按 2027 规则尺寸（200×200×200 方块，排距 200、同排间距 400、两侧 800×800×200 平台）建交错桩阵；训练可先放宽间距/降低高度，再收紧到规则尺寸。
- **课程与奖励**：地形 level 课程（由易到难）+ 障碍释放课程；奖励除速度跟踪外，加足端离地高度/落脚点、髋膝碰撞、基座高度、姿态、越障进度；终止条件加“长时间无前进/卡住”“基座过低/翻倒”。
- **方法论对照**（先读论文再定实验，见 [`literature.md`](../40-reference/literature.md)）：
  1. **基线**：现有 PPO（45 维盲 actor + 特权 critic）。
  2. **HIM**（`black-rough-him`）：历史帧 + 估计器，提升地形感知/鲁棒性；接口 270 维，和 `best.pt` 同型，部署可行。
  3. **特权高度扫描 + teacher-student**：先用 height scan/地形真值做 teacher，再蒸馏到盲 student；对应“先不接相机”的过渡方案。
  4. **MoE/多专家**：若单一策略在“台阶 vs 梅花桩”上明显互相拖累，再试专家门控或按技能切换（参考队内 MoE 经验与公开实现）。
  5. **AMP/动作先验**（可选）：用来改善自然步态与平滑切换，但引入 motion 数据与额外调参成本，排在 PPO/HIM 之后。
- **评测口径**：台阶要求每级顶面至少一次足底接触（按规则表 2 的思路）；梅花桩记录“上桩/过桩/掉桩/若干秒内通过”；每地形固定起始位姿、命令序列与重复次数，避免“一次碰巧”。

## 4. 手动模式、状态机与“专家模型”

- **结论：基本方案是“单策略 + 部署状态机”，不是“专家模型”。** 手动模式下手柄给出 `(vx, vy, wz)`，策略按速度指令输出关节目标；`rl_sar` 已有 Passive → GetUp → RL 的状态机与安全限制，沿用即可。状态机负责“什么时候允许走、什么时候阻尼/趴下、如何限速”，策略负责“怎么走”。
- **“专家模型”什么时候才需要**：当单一策略无法同时覆盖差异很大的技能（如平地小跑 vs 低姿态钻限高 vs 高墙攀爬），才考虑 teacher-student、多专家/MoE、或按场景切换的多策略（`rl_sar` 的 `policy_switch`）。在 S1/S2 之前引入会显著增加工程与 sim2real 复杂度，且难以判断收益来自哪一层。
- **手柄层要做的事**：死区、指令低通/限斜率、指令范围限制（和训练命令范围一致）、模式切换键的边沿触发；这些在 `@20261007_assignment` 的 rl_sar 输入层已有实现可参考。

## 5. 相机/深度：先不进入训练，后续按 teacher-student 引入

- 当前只做基本 locomotion + 手动模式：**盲策略 + 本体感知**足够，2026 手动模式不需要机器人自主感知；先把盲策略、DR 和 sim2sim 做扎实。
- 视觉的第一种用法不是直接进 actor，而是**特权 teacher**：训练时用地形高度扫描/深度真值训练 teacher（或 critic），再蒸馏到用历史/本体输入的 student；mjlab 侧已有 `terrain_scan`（187 ray）可立刻用，不必先上深度相机。
- 若后续确认要上深度：需要同时解决仿真渲染开销（相机训练比无相机贵）、仿真深度噪声/时延、实机标定与外参、策略周期内推理预算（深度常 30 Hz，控制 50 Hz，需要保持/插值）；建议先做小范围对照（盲 vs teacher-student vs 直接深度 actor），再决定是否进入主线。

## 6. PPO 改进：先基线、后对照

- 基线：mjlab/rsl_rl 的 PPO，按 [`literature.md`](../40-reference/literature.md) 的 PPO 调参经验（实现细节、advantage/归一化、KL 自适应等）先跑稳。
- 第一层改进：**历史/估计器**（HIM 类）与**特权 critic**；训练仓库已经支持 HIM 与 height-scan critic，优先做这两组对照。
- 第二层改进：域随机化强度、课程、奖励整形（足端/姿态/接触）；只有在基线明显不够时才上 AMP、MoE、teacher-student。
- 实验纪律：一次只改一层，固定随机种子与评测协议；曲线进 TensorBoard，结论写 [`status.md`](../status.md)。

## 7. 评测与产出

- **训练期**：TensorBoard（reward、episode 指标、课程 level、地形比例）；每 N 次保存 checkpoint，按地形通过率挑模型（不是只看 reward）。
- **离线评测**：导出 TorchScript/ONNX，在本地 MuJoCo 用固定命令序列、多种子复跑；C++ `scene_viewer`（后续接策略）用于人工看 rollout；指标包括速度跟踪、摔倒、逐地形通过率、用时、力矩/功率/平滑度、越障进度。
- **sim2sim**：延迟/抖动、摩擦、质量、IMU 噪声/零偏、力矩上限等压力测试；与训练环境不一致处逐项记录。
- **权重管理（2026-10-21 更新）**：模型权重**可以入库**，但默认只入**精选**权重：验收/对照用的导出 `policy.pt`（约 0.75 MB）放任务 `assets/policies/<version>/`；需要复现的精选 `model_*.pt`（约 5.9 MB）放 `assets/checkpoints/<run>/` 或 `weights/<阶段>` 分支。每 50 iteration 的原始 checkpoint、日志、视频、PDF 仍不入库；单个权重超过约 10 MB 时用 Git LFS 或 GitHub Release。每个入库权重都要有来源实验、commit、sha256 与评测数字（[`eval-protocol.md`](eval-protocol.md) §1）。

## 8. 风险与待定

- 台阶/梅花桩的具体版本与验收口径未定（见 [`status.md`](../status.md) 待确认项），先按 2026/2027 规则尺寸做参数化地形。
- 远程 16 GB 显存下并行环境数、训练时长与收敛性需要先做基准；决定 S1/S2 的 env 数量与课程节奏。
- 手动模式的实际手柄映射与安全边界要等任务/实机确认；仿真里先用速度指令模拟。
- 相机方案是否进入主线取决于任务是否要求自主感知；当前按“先盲、后 teacher-student”处理。
