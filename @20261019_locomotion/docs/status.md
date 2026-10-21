# 推进情况

> 只保留**当前状态、待决问题、下一步**；已完成且稳定的细节、历史问题与原始数据放在对应文档，不在本文件重复。入口见 [`../README.md`](../README.md)。

## 实施阶段长期提醒（2026-10-22）

- **可视化是实施的一部分**：复杂、多步、需要视觉确认、结果精彩或能说明问题的过程，默认留视频/截图/contact sheet + 文本诊断（JSON/CSV/日志）。视频/大图放本地 `prep.d/videos/`，诊断 JSON/CSV 放本地 `prep.d/results/`，不入库；文档里记路径、结论和可复现命令。
- **当前示例**：Part 1 zero-shot judge 汇总图 `/home/bis/BiS.d/Code.d/RoboCon/prep.d/videos/part1_judged_zero_shot_contact.png`，逐障碍 JSON `/home/bis/BiS.d/Code.d/RoboCon/prep.d/results/part1_zero_shot.json`；Part 2 能力场 stand 视频 `prep.d/videos/part2_ability_field_stand.mp4`。
- **Git 授权**：2026-10-22 起用户允许 AI 助手直接提交 Git（直到用户明确撤销）；任务级授权覆盖仓库级默认“AI 不代为提交”的约定，记录在本文件。提交仍不推 GitHub，不提交 `.vscode/settings.json`。
- 该授权和可视化规则只约束本任务；仓库级默认仍见 [`docs/conventions.md`](/home/bis/BiS.d/Code.d/RoboCon/MyMonoRepo.d/docs/conventions.md) 与 `AGENTS.md`。

## 任务真值校准（2026-10-21）

- **唯一主目标改为 2026-11-04 队内赛**：两个赛项（障碍赛遥控满分 900；越障能力测试满分 1300），两项得分和占 70%，7 分钟答辩占 30%；距当前约 14 天。完整真值见 [`reference/team-race-2026.md`](reference/team-race-2026.md)。
- **旧 2027 路线降级**：2027 赛季、2026 V2.0 八障碍、rough-first、S1b-first、sim2sim 长周期研究都不再是主进度；保留为研究性 backlog。
- **当前有效资产**：`flat-ft-2500`（flat gate + 固定/自由砂砾 zero-shot 初版可用）可当基础 locomotion；训练/评测/渲染/踩入实验基础设施可复用。
- **当前最大缺口**：正式障碍场/能力场任务、成功判定与计分器、手动部署接口、传感器/力矩合规检查，以及 slope/stairs/T 台阶/高墙/限高杆/木桥/沟壑/梅花桩专项策略都尚未建立。

### P0 实施进度（2026-10-21，节点 1）

- **足端 clearance 视觉+数值诊断（2026-10-22）**：本地 runner 在 Part 1 平地 4 s 前进，四足中心最大高度均值约 **0.022 m**（foot 半径 0.02 m，相当于足底几乎擦地），与视频“蹭地”一致；`flat-ft` 的 `foot_clearance` 目标 0.09 m 没有达到。桥面 zero-shot 只是把足抬到桥面高度，不会主动增加离地 clearance；桥/台阶专项训练需要更强 foot clearance/edge 奖励。
- ✅ 本地策略 runner：`scripts/agent_scripts/run_policy_scene.py` 在 `part1_eval_scene.xml`/`part2_plum_eval_scene.xml` 上加载 `flat-ft-2500`，Part 1 出发区 stand 约 3 s（base z≈0.419、tilt≈2.6°），Part 2 左平台 stand 约 2 s（z≈0.615、tilt≈2.3°）；视频 `prep.d/videos/part1_flat_stand.mp4`、`part2_plum_stand.mp4`；补充非零指令 walking 视频 `part1_flat_walk_back.mp4`、`part1_flat_turn.mp4`、`part2_field_walk.mp4`，以及桥/限高杆 zero-shot 诊断视频。
- ✅ Part 1 scene working copy：`assets/terrain/part1/part1_scene.xml`（从 `scene_terrain (1).xml` 复制；include 换成 Black、移除训练 hfield、标注 judge 锚点名；桥面 `bridge_blocks_0..4`=5 方墩、`bridge_bands_0..2`=3 窄带）；本地 MuJoCo 编译通过（20 body / 184 geom / nq 19）。
- ✅ `scripts/agent_scripts/part1_judge.py`：足端/限高杆接触判定骨架；初始四足 ground、bar 未触碰。
- ✅ `assets/terrain/part2/part2_plum.xml`：按 PDF 200 mm 方块/平台/100–400 mm/200 mm/400 mm 参数自建；`official_catalog.yaml` 映射官方档位。
- ✅ `config/manual-state-machine.yaml` + `scripts/agent_scripts/check_state_machine.py`：flat/loose/limit_bar/bridge/stairs/high_wall/slope/slalom 8 状态，默认 flat；`bridge` 含 blocks/bands 子型；validator 通过。
- ✅ `quadruped_control` GUI/策略已在本机跑通：Pixi 依赖 + 本地 Simulate 源码构建 `quadruped_mujoco_sim`；Part 1 场景启动、`0→GetUp→1→Running→2/3` 策略切换均 Accepted/Completed；8 个状态 policy 目前都是 `flat_ft` 占位，尚未具名键直选。
- ✅ `quadruped_control` 研读与本地接入：只读源 commit `e0fb567`；本地副本 `prep.d/quadruped_control_local` 已加入 45 维 `flat_ft` policy 配置与 policy_switch；在 Pixi 依赖下已编译 `core/mujoco/motion/torch/config/ipc/replay` 库（MuJoCo 3.12 + LibTorch 2.12），GUI `mujoco_sim` 已用本地 MuJoCo Simulate 源码构建并启动；研读见 [`reference/quadruped-control-study.md`](reference/quadruped-control-study.md)。
- ✅ VS Code/pixi 排查：tracked `settings.json` 只保留 pixi 解释器；本地 ROS extraPaths 已移除；`c_cpp_properties.json`/`browse.vc.db*` 已加入 `.gitignore`。见 [`environment.md`](environment.md)。
- ✅ 手动运行时状态键：`quadruped_control` `mujoco_sim` 已加 `F/G/J/B/T/Y/U/N` 具名 policy 切换，Part 1 场景 smoke test 通过；8 个 runtime policy 仍共用 `flat_ft`。
- ✅ Part 2 官方能力场本地 eval：`assets/terrain/part2/ability_field/part2_ability_field.xml`（`terrain.zip` map+labels+Black policy）编译通过；本地 runner 可在原点平地 stand。
- ✅ 部署审计：`audit_deployment.py` 检查 45 维 actor、无禁用传感器、12 轴 effor 20 N·m、控制仓库 hip/thigh 23.7 / calf 59.25 在规则 25/60 内；通过。
- ✅ Part 1 zero-shot 诊断：`run_part1_judged_rollout.py` 对 8 障碍做独立脚本尝试；当前全部 0 分/pending，JSON `prep.d/results/part1_zero_shot.json`。这是诊断，不是官方整场成绩。
- ⏳ 下一步：Part 1 success judge 用真实手动轨迹校准；Part 2 六类地形 training task 化（本地 eval 场已就绪）；官方整场 zero-shot 计分；状态专项策略需训练机。

### 比赛要求 vs 当前进度

| 要求 | 当前状态 | 缺口 | 优先级 |
|---|---|---|---|
| flat/手动基础 locomotion | `flat-ft-2500` flat gate 通过；无比赛手动接口/计分器 | 仿真部署、手柄命令、摔倒恢复、计分 | P0 |
| 传感器/力矩合规 | actor 45 维不含禁用传感器；当前关节限 20 N·m | 需按部署链路审计；力矩限制 25/60 N·m 未压测 | P0 |
| 斜坡（赛项一 + 能力 20–45°） | 仅 `black-rough` 里夹带坡；未单独评测，综合 zero-shot 失败 | 专用 slope 地形/课程/成功判据 | P1 |
| 楼梯 / T 字形台阶 | 仅 legacy rough stairs；flat 模型综合失败；T 布局未建 | T 台阶任务、逐级足接触判据、上/下训练 | P1 |
| 高台（10–40 cm） | 无任务 | 高台地形 + 攀爬课程 | P1/P2 |
| 高墙（10–40 cm） | 无任务 | 高墙地形 + 越障/攀爬策略 | P2 |
| 沟壑（10–30 cm） | 无任务 | 沟壑地形 + 跨越策略 | P2 |
| 直角绕杆 | 无任务 | 绕杆地形 + 手动/局部自动 | P1 |
| 限高杆 | 无任务 | 低姿态/限高杆地形 | P1/P2 |
| 砂砾碎木坑 | composite 石床 zero-shot 可用；不是正式坑 | 坑体/碎木、1 m 短边进出、1/2 足触地失败判据 | P2 |
| 木桥 A/B | 无任务 | 窄桥/木桥地形 + 平衡策略 | P2 |
| 梅花桩 | 无任务 | 200 mm 方块交错桩阵；困难 | P2/P3 |
| 计分/答辩 | 无比赛计分器/答辩材料 | 计分脚本 + 7 分钟答辩 | P0/P3 |

判定器设计见 [`training/competition-judge.md`](training/competition-judge.md)：先建官方成功/计分判定器，再训练；training terminate 只是简化子集。运行时先做**纯手动+状态机**保底（flat/loose/limit_bar/bridge/stairs/high_wall/slope/slalom），judge 只做外部计分；相机放 P2 之后，见 [`training/manual-fallback-state-machine.md`](training/manual-fallback-state-machine.md)。地形资产审计（Part 1 `scene_terrain (1).xml`、Part 2 `terrain.zip`、必须修改项）见 [`terrain/competition-assets.md`](terrain/competition-assets.md)。

### 14 天路线（按得分/风险排序）

1. **P0（10-21 ~ 10-23）比赛闭环**：做正式场地/能力场地形与成功判定、手动部署接口、计分器、传感器/力矩审计；冻结 `flat-ft-2500` 作为基线，不再做 flat 美化。
2. **P1（10-23 ~ 10-27）基础越障**：斜坡、楼梯/T 台阶、高台 10–20 cm；从 flat 权重做地形课程，目标先拿“可控的 50–100 分档”。
3. **P2（10-26 ~ 11-01）赛项一关键障碍**：绕杆、限高杆、高墙、木桥 A/B、砂砾碎木坑；按“得分/风险”选择尝试项；固定动作/局部自动需用户确认（规则允许，自动无加分）。
4. **P2/P3（10-28 ~ 11-02）能力测试**：沟壑、高墙、梅花桩、高台/楼梯/斜坡高档；每项 4 次，优先 30 cm 沟壑、20–30 cm 高台/楼梯、30–35° 斜坡等中档分数。
5. **P3（11-01 ~ 11-04）整合与答辩**：整场多次尝试、操作手练习、失败恢复、冻结权重；完成 7 分钟答辩材料（奖励/论文/机制/对比实验）。

### 有效 / 不再作为主进度

| 类别 | 内容 |
|---|---|
| 有效 | flat-ft-2500；固定/自由砂砾 zero-shot；训练/评测/渲染工具；踩入深度实验；训练仓库 terrain/reward 基础设施 |
| 降级为研究 | 2027 赛季地形；2026 V2.0 官方场（旧口径）；rough baseline；dense80 大石块；S1b 2 天 gate；flat 对称性长尾实验；HIM/论文探索 |
| 作废 | “只做手动、其他不用管”的全局假设；把 S1b 砂砾 gate 当比赛完成标准；把 rough 综合套件当障碍基线 |

## 当前结论（研究性，非比赛验收；2026-10-21 更新）

- **flat baseline 健康**：2000 iteration 完成，G1/G2/G4/G5 通过；导出策略和评测 JSON 在 [`../assets/policies/baseline-2000/`](../assets/policies/baseline-2000/README.md)。
- **S1b 平地+砂砾 gate**：初版通过。`black-gravel-flat`（50% flat + 30% 细砾石 + 20% 粗砾石，无台阶）上 32 envs 的 flat / mirror / gravel-2100 / flat-ft 四版均 0 摔倒；flat-ft-2500 在 64 envs 复测为摔倒率 1.56%（1/64，门槛 ≤5%）、0.3/0.5 m/s vx MAE 0.140/0.133、p95 tilt 7.1°/7.8°。gravel-2100 的 0.3/0.5 m/s MAE 为 0.147/0.092（0.3 刚过 0.15 线），只训练约 115 iteration；flat-ft-2500 是当前更好的候选。权重 [`flat-ft-2500`](../assets/policies/flat-ft-2500/README.md)、[`gravel-flat-2100`](../assets/policies/gravel-flat-2100/README.md)，均不是验收策略。
- **S1b-free（自由关节砂砾）**：按用户审查继续修正为**抬高石床 + 3–8 cm 碎石**：**6 cm 基座 + 6 cm 低 curb + 700 块静态预沉降石 + 120 块 free-joint 碎石子**（1.5×1.5 m，无高围栏；石-石接触关闭）。6 cm 来自独立踩入实验的 3.3 kg 单足 p95 5.3 cm + 0.7 cm 余量（见 [`terrain/gravel-penetration.md`](terrain/gravel-penetration.md)）。投影覆盖率：自由层 11.5%、静态层 58.4%、合计 63.2%；俯视图 `prep.d/videos/overview/black-gravel-free_composite_final_overview.png`。820 个石体/每 world，训练成本高；composite 本身尚未训练。但 `flat-ft-2500` zero-shot 在 composite 4 envs 评测 **0 摔倒、0.3/0.5 m/s MAE 0.089/0.049、p95 tilt 4.1°/3.1°**，provisional pass（4 envs/单布局，不是正式多 seed 验收）；诊断视频 `prep.d/videos/flat_ft_composite_zero_shot.mp4`。旧 24 石块和 **dense80 大石块（15–19 cm，尺寸不符实际碎石）** 的 pass 都只作历史/木块参考。
- **flat 对称候选（2026-10-21）**：`flat_ft_mirror01_footclear_500` 从 `baseline-2000/model_1999` resume 500 iteration，最终 `model_2498` 的 flat gate 无摔倒、stand 漂移 0.275 m、fwd-nominal MAE 0.0687；RL−RR x 差从 0.155 m 降到 0.051 m，S1b 32 envs 0 摔倒、0.3/0.5 m/s MAE 0.134/0.178。权重在 [`../assets/policies/flat-ft-2500/`](../assets/policies/flat-ft-2500/README.md)；这是当前候选，不是最终验收。
- **rough baseline 完成但质量不足**：`model_3999.pt` 正常保存（含两次崩溃/恢复）；数值不稳定与地形课程卡住两个问题的证据链见 [`training/training-health.md`](training/training-health.md)。G3 初判**未通过**（terrain level 未推进、stairs_down/discrete 卡住），逐地形通过率尚待测；策略已导出到 [`../assets/policies/baseline-rough-3999/`](../assets/policies/baseline-rough-3999/README.md)，仅作对照。注意：legacy rough 的 G3 **不是**台阶正式训练的硬门槛（见 [`training/eval-protocol.md`](training/eval-protocol.md) §6.1 H5）；当前真正卡住的是 H2 数值安全、H3 地形管线与 H4 步态硬故障。
- **当前 flat 模型地形 zero-shot（2026-10-21）**：flat ✅；固定砂砾 ✅（64 envs 摔倒 1.56%）；composite 自由砂砾 ✅ 4 envs 0 摔倒、0.3/0.5 MAE 0.089/0.049；`black-rough` 综合套件 ❌ 4 envs max fall 25%（slopes/rough/discrete/stairs 混合）。结论：flat 模型已能应对 mild 固定/自由砂砾，但**不能直接上队内赛/往年综合地形**；台阶/梅花桩/离散障碍仍需专项训练。培训方后续文件收到后按正式图/尺寸再校准；当前 PDF 已作为主真值。
- **可视化 / 记录 / 材料**：视频 wrapper、图例、箭头错开已完成；训练记录清单已建立；培训方 7 个 PDF 与新版 `scene_terrain (1).xml` 已登记（[`terrain/materials.md`](terrain/materials.md)、[`reference/literature.md`](reference/literature.md)）。
- **台阶/梅花桩**：**尚未启动正式训练**。诊断性集成测试可以先做；正式训练要先过 H1–H4（[`training/eval-protocol.md`](training/eval-protocol.md) §6.1）。flat 的“满意/完全对称”与 legacy rough 的台阶通过率都不是启动门槛。

## 研究性阶段状态（非比赛主进度）

| 阶段 | 状态 | 入口 |
|---|---|---|
| 任务范围、材料、环境、评测协议 | ✅ 已就绪 | [`terrain/materials.md`](terrain/materials.md)、[`environment.md`](environment.md)、[`training/eval-protocol.md`](training/eval-protocol.md) |
| flat baseline 训练 + gate | ✅ 完成（stand 阈值按校准后 0.30 m） | [`training/experiments.md`](training/experiments.md) §3 |
| flat 对称性 fine-tune | ✅ 候选 `flat-ft-2500`（x 差 0.051 m；G1/S1b 初版通过，非最终验收） | [`../assets/policies/flat-ft-2500/`](../assets/policies/flat-ft-2500/README.md) |
| S1b-fixed 平地+砂砾 gate | ✅ 初版通过（flat-ft 64 envs 摔倒 1.56%、0.3/0.5 MAE 0.140/0.133） | [`training/eval-protocol.md`](training/eval-protocol.md) §6.2、[`training/experiments.md`](training/experiments.md) §3.9.1 |
| S1b-free 自由关节砂砾 | ✅ zero-shot provisional（flat-ft 在 composite 4 envs 0 摔倒、MAE 0.089/0.049）；4 envs/单布局，多 seed 正式复测未做；旧大石块不作证据 | [`terrain/gravel-feasibility.md`](terrain/gravel-feasibility.md) §6 |
| rough baseline | ⚠️ 完成但质量不足；G3 初判未通过 | [`training/training-health.md`](training/training-health.md)、[`../assets/policies/baseline-rough-3999/`](../assets/policies/baseline-rough-3999/README.md) |
| 训练可视化 + 手工记录流程 | ✅ 完成 | [`training/visualization.md`](training/visualization.md)、[`training/training-record-checklist.md`](training/training-record-checklist.md) |
| 台阶 / 梅花桩 | ⬜ 可先做诊断集成测试；正式训练需 H1–H4 | [`training/eval-protocol.md`](training/eval-protocol.md) §6.1、[`training/training-plan.md`](training/training-plan.md) |
| flat 优化实验 A/B/B+约束/C | ⬜ 待 baseline 问题处理后 | [`training/training-baseline.md`](training/training-baseline.md) §5 |
| DR / 鲁棒性 / sim2sim | ⬜ 后续 | [`training/training-plan.md`](training/training-plan.md) |

## 本轮结果（2026-10-21）

- **训练仓库改动（工作区，未 commit）**：新增 `reward_safety.py`（per-step reward clamp ±50、return/advantage clamp、非有限值记录；环境变量 `BLACK_REWARD_CLIP`）、`symmetry.py`（actor 左右镜像 loss；`BLACK_MIRROR_LOSS_COEFF`）、`foot_clearance` reward（HIM 论文的 0.09 m/−0.01）、`black-gravel-flat` task（50% flat + 30% 细砾石 + 20% 粗砾石，无台阶/离散障碍）与 `black-gravel-free` task（6 cm 基座 + 120 自由碎石 + 700 静态石、3–8 cm，4–8 envs 小 batch）；`black-flat` 的 500-iteration A/B 见 [`training/experiments.md`](training/experiments.md) §3.9。
- **步态对称初步结果**：200 iteration 时 mirror loss 把 RL/RR 平均 x 差从 0.255 m 降到 0.047 m，但 rear 接触两者都是 1.00（疑似双后腿拖地）；加 foot clearance 后 500 iteration 的 RL/RR x 差约 0.006 m、接触 0.94/0.99、足端最高约 4.5/5.1 cm，明显好于 mirror-only；footclear-only 500 iteration 在约 100/500 时因让出 GPU 给砾石 gate 训练而停止，尚未完成，不能单独归因。
- **砾石 gate**：mild `black-gravel-flat`（50% flat + 30% 细砾石 + 20% 粗砾石，无台阶）上 32 envs、play 模式，flat `model_1999` / mirror+footclear 500 / gravel-2100 / flat-ft-2500 四版都是 **0 摔倒**；flat-ft-2500 的 0.3/0.5 m/s vx MAE 0.134/0.178、p95 tilt 8.8°/8.6°，gravel-2100 为 0.147/0.092、5.3°/5.9°，均 provisional pass。当前代理尚不能区分策略好坏（flat 策略零样本已过），正式复测要固定 terrain level/种子并扩展到更高速度/更粗砾石。
- **数值安全网**：rough 的 `Loss/value` 问题用 reward/return clamp 处理；`rough_safety_200` 从 `model_3999` resume 200 iteration **已完成、无崩溃**；但 `Loss/value` 仍有 4 次尖峰（最高 1.89e4，均回落），说明 clamp 只降低了后果，未消除尖峰；正式训练前还要 per-term clamp / value target 保护。
- **文献**：5 篇论文原文已读，关键点、可复用项与“不要照搬”的边界写在 [`reference/literature.md`](reference/literature.md) §9。
- **可视化闭环**：`render_policy_commands.py` 固定命令序列（含 arc-left/right，箭头已错开）；已录 flat / fixed gravel / free dense 三条 v2 视频，放在本地 `prep.d/videos/`（不入库）；视频先于数值 gate 检查。

## 已知问题（当前）

- **rough 数值不稳定（部分缓解，未根治）**：`Loss/value` 在旧 run 崩溃前约 90 iteration 出现 1e4–1e31→inf；平方类 reward 项先爆；`std >= 0` 只是末端症状。2026-10-21 已加 reward/return clamp，`rough_safety_200` 完成 200/200 无崩溃，但仍有 4 次尖峰（最高 1.89e4，均回落）；per-term clamp、value target 保护与 `njmax` 台阶多接触检查仍待做；见 [`training/training-health.md`](training/training-health.md) §3。
- **rough 地形课程卡住**：`stairs_down` 0.85、`discrete_obstacles` 1.51，占 45% env；rough 最终约 31% episode 摔倒、reward 只有 flat 的 59%。当前生成器含 50% stairs，是 legacy 鲁棒性配置，不是 rough-flat 目标；建议拆 rough-flat 与 obstacle 阶段；见 [`training/training-health.md`](training/training-health.md) §4、[`training/training-plan.md`](training/training-plan.md) §2。
- **flat 步态不对称（已缓解）**：原始 baseline RL 比 RR 平均靠前 0.155 m、RR 接触 1.00 vs RL 0.84；2026-10-21 在 `flat_ft_mirror01_footclear_500` 上降到 x 差 0.051 m、接触 0.85/0.89，但还没有完全对称；mirror-only 会把双后腿压成拖地，不能单独用。见 [`training/experiments.md`](training/experiments.md) §3.7/§3.9。
- **yaw / 躯干朝向“超前 30°”**：纯前进+转向时 trunk yaw 与实际运动方向夹角仅 1–3°，不是持续 30°；30° 出现在带横向速度的命令（如 `(0.5,0.3,0.5)` 的 sideslip 约 −30°，等于 `atan2(vy,vx)`），是 body-frame 横移命令的正常表现，暂不认为是奖励 bug。若 `vy=0` 仍复现 30°，需要具体命令/视频段复测；见 [`training/experiments.md`](training/experiments.md) §3.8。
- **可视化/资料**：新版 `scene_terrain (1).xml` 仍只是只读素材，尚未接入评测；培训方 5 篇英文 PDF 已读并记录，中文翻译未逐页对照。

## 已定决策（摘要）

- **赛项一默认手动**，但规则允许自动/固定动作且自动无额外分；**赛项二仅允许 RL、不能写固定动作**。是否在赛项一使用局部自动/固定动作待用户确认。
- **当前唯一主路线是 2026-11-04 队内赛**；2026 V2.0/2027 材料只作历史/备选，不再按旧 S1b-first / rough-first 路线推进。
- **正式场/能力场优先**：先建 task + 成功判定 + 计分器 + 手动部署，再训练；避免继续在旧代理地形上堆实验。Part 1 用 `scene_terrain (1).xml`，Part 2 用 `terrain.zip` 的 85 个难度标签做能力场基础；资产审计/修改项见 [`terrain/competition-assets.md`](terrain/competition-assets.md)。
- **传感器合规**：最终 actor 只用 IMU+编码器（+可选相机/雷达）；height scan/foot force/foot height/body height 等只能进训练 critic/teacher，不能进部署 actor。
- **运行时先手动状态机保底**：操作手按键切 flat/loose/limit_bar/bridge/stairs/high_wall/slope/slalom；flat 与 loose 语义分开，可暂时共用策略；judge 只做外部计分，不做运行时自动切换。见 [`training/manual-fallback-state-machine.md`](training/manual-fallback-state-machine.md)。
- **相机分阶段**：最终版本保留深度相机方案；P0/P1 先盲策略+状态机，P2 后做深度 teacher/student + DR；不现在把相机塞进 actor。
- **研究性 baseline-first**：flat gate → rough-flat → 台阶/梅花桩诊断测试 → 正式台阶训练；这是底层模型 pipeline，**不是 11-04 比赛主路线**。
- **砂砾踩入深度（2026-10-21，独立实验）**：2 cm 足端球 + 216 块 3–5 cm 自由椭球深床；3.3 kg 单足静载 5 个种子 **p50 4.1 cm、p95 5.3 cm、max 5.5 cm**（1/5 触底，p95 是下界）；6.6 kg 2× 动载 p95 5.7 cm 但 4/5 触底，结果被床深截断；13.17 kg 一足极限不成立。结论：composite 先取 **6 cm 预烘焙基座**（p95 + 0.7 cm）。详见 [`terrain/gravel-penetration.md`](terrain/gravel-penetration.md)。
- **“平地”的宏观边界（2026-10-21，先取 1/3）**：障碍/围栏/地形最高点 < 狗质心离地高度的 **1/3**（Black 约 0.43 m → 0.14 m，2026-10-21 先取 1/3）算平地；低 curb/基座/3–8 cm 碎石属于平地，0.25 m 以上围栏不算。细节待实例校准，已写入 [`training/eval-protocol.md`](training/eval-protocol.md) §6.3。
- **大块/整片石**：80 块 15–19 cm 大石块结果降级为**木块/大障碍仿真思路**（调密度、摩擦、质量），不再作为 3–10 cm 碎石 S1b-free 的尺寸基准。
- **S1b 2 天时间盒（研究性，已不阻塞比赛）**：mild `black-gravel-flat` 与 composite 已 provisional；固定地形/多 seed 复测移入 research backlog，不再占用 P0/P1 训练时间。
- **台阶/梅花桩两级门槛（研究性）**：正式训练过 H1–H4 的研究性门槛；比赛 P0/P1 的正式场 evaluator 优先于旧 H1–H4，不能因研究 gate 阻塞 11-04 比赛。
- 训练用远程原生 uv；mjlab 作为锁定依赖，不 fork 本体；训练代码在训练仓库，运行/评测在本仓库。
- **可视化闭环**：每个里程碑/最终候选用 `render_policy_commands.py` 录固定命令序列（stand/fwd/bwd/lat/yaw/combined），flat、fixed gravel、free gravel 各至少一条；视频先于数值 gate 检查，发现拖腿/卡边/抖动即使数字过线也不能进入下一阶段；视频不入库，放 `prep.d/videos/`。
- **模型权重可入库**：精选 `policy.pt` / `model_*.pt` 按 [`training/training-plan.md`](training/training-plan.md) §7 提交；每 50 iter 原始 checkpoint、日志、视频、PDF 不入库。
- rough 后续按 **rough-flat（坡/粗糙/砂砾/低摩擦）与 obstacle（台阶/梅花桩/沟/桥）分开** 的路线推进，不沿用 50% stairs 的 rough 配比。

## 待确认 / 待决

1. 赛项一是否允许局部自动/固定动作（规则允许、自动无加分）；赛项二确认纯 RL。
2. 培训方“具体文件”/场地 XML/资产何时到位；正式场地是否与 PDF 图一致。
3. 相机/雷达按“P0/P1 盲策略、P2 后深度 teacher/student、最终版保留相机”推进；是否接受这个阶段化？
4. 培训方说的“需要修改的一处”具体指哪一项；我目前最确定的是 `scene_terrain (1).xml` 的 `include` 从 blackW 换成 our Black，另标注了限高杆静态、砂砾坑实心两个规则关键项。
5. 手柄映射、安全边界、状态机接口沿用哪份配置。
6. 训练仓库 `REMOTE_SETUP.md` 与 `mjlab==1.6.0` 精确锁的提交/推送（AI 不代为 commit）。

## 下一步（按比赛优先级，非研究 backlog）

1. **P0 比赛闭环**：节点 1 已完成 scene/judge skeleton/plum/state config；节点 2 建 Part 2 六类 task + Part 1 逐障碍 success judge + 手动 runner；节点 3 官方场 zero-shot 得分与传感器/力矩审计。
2. **P1 基础越障**：斜坡/楼梯/T 台阶/高台 10–20 cm；从 flat 权重做课程，先拿低档分。
3. **P2 赛项一障碍**：绕杆、限高杆、高墙、木桥 A/B、砂砾碎木坑；按得分/风险决定尝试顺序。
4. **P2/P3 能力测试**：沟壑、高墙、梅花桩、各级高台/楼梯/斜坡；优先中档分数。
5. **P3 整合与答辩**：整场多次尝试、恢复、操作手练习、冻结权重、7 分钟答辩材料。
6. **研究 backlog（不阻塞比赛）**：rough-flat 数值安全、HIM/非对称 AC、sim2sim、flat 长尾实验；等比赛闭环后再排。

## 证据与入口

- 训练/评测数据：[`training/experiments.md`](training/experiments.md)、[`training/training-health.md`](training/training-health.md)
- 环境与基准：[`environment.md`](environment.md)
- 地形与资料：[`terrain/materials.md`](terrain/materials.md)、[`reference/literature.md`](reference/literature.md)
- 视频与记录：[`training/visualization.md`](training/visualization.md)、[`training/training-record-checklist.md`](training/training-record-checklist.md)
