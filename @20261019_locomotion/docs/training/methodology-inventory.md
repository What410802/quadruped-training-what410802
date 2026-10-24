# 方法论"弹药库"：可用来把 blind 与 depth 都做到最好的招数、来源与使用状态（2026-10-24）

> 触发：用户要求"方法论拉满"——把开源代码/论文里行之有效的创新点尽量吸收，让 blind 和 depth 两条线都接近各自最好状态，而不是在"裸 PPO + 简单地形"上做最终裁决。
> 本文把可用的方法论分成四类：**① 本任务已使用并验证；② 训练仓已实现、本任务未启用/未训练；③ 未实现、需要引入（论文/开源代码）；④ 不建议投入的**。每条给出入手点、预期收益、成本、部署约束和优先级。
> 配套：最终实验设计见 [`competition-terrain-and-symmetry-plan.md`](competition-terrain-and-symmetry-plan.md)；相机/CNN 细节见 [`camera-depth.md`](camera-depth.md)；论文清单见 [`../reference/literature.md`](../reference/literature.md)。

## 1. 已使用并验证（不是"漏掉的招"）

| 方法 | 本仓落点 | 证据/状态 |
|---|---|---|
| **非对称 actor-critic（特权 critic）** | actor 45 维本体（depth 为 45+64 latent）；critic 259 维 = 72 本体 + 187 维 terrain height scan | 所有 PPO 任务默认；blind/depth 对照都跑在这套上 → 已证明可用 |
| **地形课程（procedural terrain curriculum）** | `TerrainGeneratorCfg(curriculum=True, num_rows=6, difficulty_range=(0,0.6))`，flat/smooth slope/stairs | 1500 iter 里 terrain level mean 从 0 爬到 ~1.46（depth）/1.34（blind）→ 已证明在推进；覆盖不足的缺陷见竞争地形计划 |
| **命令课程（command curriculum）** | `Curriculum/command`：vx 范围从 ±1 扩到 ±2 m/s、high/low buffer 自适应 | 1500 iter 时 `vx_max=2.0`；tracking reward 随命令范围上升 → 已证明 |
| **domain randomization** | `DomainRandomizationParams`：摩擦 0.2–1.25、payload −1~+2 kg、COM ±5 cm、kp/kd ×0.9–1.1、encoder bias ±0.015、push ±1 m/s；train 生效、play 移除。**2026-10-24 小修：push 间隔从固定 16 s 改为 per-env 随机 6–20 s**（原固定 16 s 在 20 s episode 里恰好每回合同相位一次，策略可能学到"日程"且大部分时间没有扰动；随机后部分 env 无 push、部分 1–2 次） | 已在所有训练 run 生效（baseline 级）；push 随机化后的 run 从竞争地形批次开始；未做"是否该加/减"的单独 A/B |
| **奖励塑形（当前 11 项）** | tracking_linear 1.0、tracking_angular 0.5、lin_vel_z −2、ang_vel_xy −0.05、orientation −0.2、base_height −1、foot_clearance −0.01、dof_acc −2.5e-7、joint_power −2e-5、action_rate −0.01、smoothness −0.01 | 已使用；foot_clearance 有 A/B 证据（§3.9） |
| **mirror loss 对称约束 + foot_clearance** | `symmetry.py` + `BLACK_MIRROR_LOSS_COEFF`；旧 A/B：mirror 0.1 把 RL−RR 前后差 0.255→0.047 m，mirror+clearance 到 0.006 m 且不拖腿 | **flat 上已验证**；当前 P1/depth 运行未开（默认 0）→ 竞争地形训练默认开 0.1 |
| **安全网（数值稳定性）** | reward clamp ±50、return clamp、actor obs clip ±100、action clip ±100、`bad_sim_state` 终止 | 修复 Warp CUDA 710 的 200-iter 验证（training-health §7）→ 已证明 |
| **深度相机 CNN + 端到端训练** | 64×48（对照 32×32）→ 3 层卷积（16/32/64，k5/k3/k3，s2）+ global avg pool → 64 维 latent；obs 噪声 ±0.02 | plumbing、成本、1500/3000 筛选都有数据（camera-depth §5/§7/§11） |
| **blind → depth warm start** | `depth_warm_start.py` + `BLACK_DEPTH_WARM_START`：blind actor 前 45 列复制、CNN 64 列置零、critic/action std 复制、command curriculum range 恢复 | 本 session 实现并 smoke 通过（45→109、2 iter 无错）；正式对照臂排队中 |
| **评测/可视化闭环** | Part1/Part2 judge、每障碍独立起点、rollout 视频、review 页、CSV/JSON | 已用于 zero-shot 与 P1 诊断，结论可复现 |
| **PPO 超参基础** | 5 epoch、4 mini-batch、lr 1e-3 adaptive、γ/λ 0.99/0.95、desired_kl 0.01、entropy 0.01、max_grad_norm 1.0 | 已验证可训，不是主要提升杠杆 |

## 2. 训练仓已实现、本任务还没启用/没训练（可直接试，性价比高）

| 方法 | 落点 | 现状 | 预期收益/风险 | 优先级 |
|---|---|---|---|---|
| **历史帧（actor history）** | HIM 任务 `black-flat-him`/`black-rough-him` 用 MjLab native `history_length=6`（45×6=270 维 actor）；也可只给普通 PPO 加 history | HIM 整套（estimator/Sinkhorn/contrastive/HIMPPO）在训练仓 worktree 已实现、**没有跑过任何 HIM 训练**；单加 history 是纯配置改动 | 对 blind 线：时序上下文 → 更稳的 rough/障碍步态；对 depth：可与 CNN latent 组合（如 45×6+64=334）；部署契约上 270 维已被 rl_sar/best.pt/quadruped_control 支持（history_frames 配置），**可部署**（深度版本仍需 CNN 推理） | **高** |
| **HIM estimator（估计速度/隐式状态 + 对比学习）** | `algorithms/him/{estimator,policy,ppo}`；encoder 128→64→(velocity 3 + latent 16)、target encoder、32 prototypes、HIMPPO | 已实现、未训练；官方 HIM 单测/plumbing 有，效果未验证 | 比裸 history 更强的本体自适应/抗扰；风险是训练复杂、调参成本高；作为 history 之后的第二级 A/B | 中高 |
| **RNN 策略（LSTM/GRU）** | rsl_rl `RNNModel`；`mjlab/rl/config.py` 支持 `rnn_type/rnn_hidden_dim/rnn_num_layers` | 可用但未注册任务、未训练 | 与 history 类似的时序能力，但**部署需要维护 hidden state**（rl_sar/quadruped_control 需改接口），比静态 270 维 history 难；优先级低于 history | 中低 |
| **Distillation runner（teacher-student）** | rsl_rl `runners/distillation_runner.py` + `algorithms.distillation` | 库里有；本任务没接教师/学生任务 | 用特权 actor（带 height scan）当教师，蒸馏到 blind/depth 学生；对 depth 尤其有价值（相机学生可先模仿"看得见地形"的教师） | **中高（depth 线）** |
| **mirror data augmentation** | `symmetry.py` 的 callback 已支持 `use_data_augmentation=True`，但 critic 的 height scan 镜像未实现 | 未启用 | 比 mirror loss 更强的对称约束；需补 critic 镜像变换；先做 mirror loss 0.1 的 A/B 再考虑 | 中 |
| **Auxiliary / privileged teacher actor** | 环境里可以给 actor 加 height_scan 组（当前只有 critic 有），作为蒸馏教师/辅助监督源 | 未实现（需新增 actor 组/任务注册） | 给 depth CNN 加"预测高度图/教师 latent"的 aux loss 是文献常用手段，可显著改善视觉表征 | 中 |
| **深度分辨率/延迟/噪声/外参 DR** | 深度 obs 只有 ±0.02 噪声；渲染级噪声/丢帧/延迟/外参/分辨率未做 | 未实现 | 视觉鲁棒性（sim-only 比赛里优先级低于"能不能过障碍"，但可减少评估波动） | 中（最后做） |
| **深度架构/潜维 A/B** | `DEPTH_CNN_CFG`（16/32/64、k5/k3/k3、global avg pool → 64）、BLACK_DEPTH_WIDTH/HEIGHT 环境变量 | 只测过成本（32×32 vs 64×48），无质量 A/B | 可能提升障碍细节判别；成本 ×1.7 | 中 |
| **DR 范围 A/B / 更强扰动** | 现有 DR 参数均可配 | 未做单项 A/B | 提高鲁棒性；sim-only 比赛里边际收益一般 | 低中 |
| **地形课程感知版本（perception curriculum）** | 目前地形课程与视觉无关；可让深度线先易后难、后期加视觉扰动 | 未实现 | 与 DR 一起作为第二阶段 | 中 |

## 3. 未实现、需引入（论文/开源代码的"弹药"）

| 方法 | 来源 | 用途 | 成本 | 建议 |
|---|---|---|---|---|
| **Teacher-student / privileged distillation**（教师 actor 用 height scan，学生用本体/深度） | Miki et al., *Science Robotics* 2022 ([DOI](https://doi.org/10.1126/scirobotics.abk2822))；Lee et al. 2020；rsl_rl `DistillationRunner` 已具备 | 给 depth 学生稠密监督，减少从零学视觉的样本成本；也可提升 blind | 中（教师任务 + 蒸馏任务 + 评测） | depth 线值得做；先做"高度 scan 教师" |
| **RMA / adaptation module**（快速运动自适应） | Kumar et al., RSS 2021（RMA） | 本体自适应；HIM 已经覆盖大半，额外引入收益有限 | 中 | 不做（HIM 替代） |
| **DreamWaQ CENet**（VAE context 估计 + 非对称 AC） | Nahrendra et al., ICRA 2023 ([arXiv 2301.10602](https://arxiv.org/abs/2301.10602)) | 类似 HIM 的 context 估计，工程更简单 | 中 | 备选，HIM 之后 |
| **深度辅助目标/自监督**（预测局部高度图、教师 latent、terrain 类别；或 contrastive/autoencoder 预训练 CNN） | 感知 locomotion 系列（Miki 2022；Agarwal et al., CoRL 2022, [arXiv 2211.07638](https://arxiv.org/abs/2211.07638)；Zhuang et al., CoRL 2023, [arXiv 2309.05665](https://arxiv.org/abs/2309.05665)） | 提升 depth CNN 样本效率/表征质量 | 中（改 loss + 任务） | **depth 线优先级最高之一** |
| **任务级成功/目标奖励（obstacle course）** | 课程式 RL / parkour 系列（Zhuang 2023 等） | 当前训练只有速度跟踪，没有"过桥/穿限高杆/到终点"的任务奖励；这与比赛得分最直接相关，比时间奖励更重要 | 中（地形+成功判定+奖励项） | **优先（与竞争地形一起做）** |
| **Gait 参数化/多行为**（Walk These Ways） | Margolis et al., CoRL 2023 ([arXiv 2212.03238](https://arxiv.org/abs/2212.03238)) | 步态自然性/多行为切换；对得分帮助有限 | 高 | 不做（答辩可讲） |
| **AMP / 运动先验** | Peng et al., RSS 2020 ([arXiv 2004.00784](https://arxiv.org/abs/2004.00784)) 等 | 自然步态/对称性；需要 motion 数据 | 高 | 不做（mirror 已够） |
| **Vision transformer / 更大视觉主干** | 视觉 locomotion 系列 | 表征能力；部署代价高 | 高 | 不做 |
| **多 seed / ensemble** | 通用实验方法 | 降低单 seed 偶然性；用于最终 gate 而不是提分 | 低（算力×k） | 只在最终冻结前对 winner 做 2–3 seed 复验 |

## 4. 完成时间/速度：奖励里要不要加？

**现状**：训练 reward（§1 的 11 项）里**没有任何"完成时间/到达目标"项**；速度只通过 `tracking_linear` 跟踪命令 + command curriculum 扩范围来间接鼓励；episode 上限 20 s。

**比赛规则**（`docs/reference/team-race-2026.md`、`comp/CONTRACT.md`）：
- **Part 1**：8 障碍 × 100 + 全部通过回启动区 +100；**速度不直接给分**，只在**同分时按用时排序**；3 次尝试、计时在机器人稳定停下后停止；恢复不消耗尝试。所以速度只在"已经拿满分/同分"时有用，属于 tie-break。
- **Part 2**：每项 4 次取最高难度，**不计时**，只按越障能力得分；稳定性目标失败率 <1%。所以速度不影响得分。
- 我们自己的 Part1/Part2 评测脚本有"每障碍/每档秒数窗口"（例如 Part2 6 s → 延长到 12 s 后 zero-shot 从 0/20 变 8/20），那是**诊断窗口**，不是官方计分规则；它说明"太慢会走不到障碍"，但不等于官方按时间打分。

**建议**：
1. **不要加 naive 的稠密时间奖励/速度奖励**：得分是 pass/fail，跑快没有额外分，反而增加：砂砾坑/桥/限高杆的"任何瞬间 ≥2 足触地"失败风险、摔倒风险、Part2 失败率风险（要求 <1%）。当前 command curriculum 已经把命令速度从 ±1 扩到 ±2 m/s，足以覆盖"走得到障碍"的需求。
2. **用"任务成功/到达终点"的稀疏奖励替代时间奖励**：在竞争地形训练里加 goal/完成奖励（过桥到对岸、穿限高杆、绕完杆、上到高台等），成功时给 bonus（可选带一个很小的 time-to-goal 系数）；这比"跑得快"更贴合得分。
3. **时间只作为评测指标**：每次 rollout 记录 time-to-goal/每个障碍耗时，用于：Part1 同分 tie-break 参考、判断是否太慢到不了障碍（检查评测窗口是否合理）、以及答辩展示"效率"；不进入训练 reward（除非之后 A/B 证明加 time 项不增加失败率）。
4. **确认官方评测窗口**：Part2 是否有每次尝试的时间上限目前规则未写；我们的 6/12 s 是自定窗口，最终评测协议要和官方对齐（若官方窗口更短，就提高命令速度/缩短路程，而不是加时间奖励）。
5. 如果最终 Part1 分数接近、需要 tie-break：在"障碍通过率已饱和"之后，才考虑加**很小的**时间惩罚/episode 时间 bonus 做微调，并 A/B 验证失败率不升。

## 5. 推荐下一步（同时服务 blind 与 depth）

1. **竞争地形 + 任务成功奖励**（最高优先级，见竞争地形计划）；
2. **历史帧 A/B**（blind：单帧 45 vs 6 帧 270；depth：45×6+64 vs 45+64）——部署契约可行，成本低；
3. **mirror 0.1 + foot_clearance** 默认开启并回归对称性指标；
4. **depth 线：teacher-student 蒸馏 + 深度 aux loss**（用 height scan 教师/辅助目标）；
5. **HIM 完整版**（若 history 不够）→ 训练仓已实现，作为第二级；
6. 最后做深度 DR/分辨率 A/B；多 seed 只用于最终 winner 复验。

> 结论：我们已用的方法（特权 critic、课程、DR、奖励塑形、foot clearance、mirror、安全网、depth CNN、warm-start）覆盖了基线和视觉主线；**还没用的高价值弹药是"历史帧/HIM""任务成功奖励""教师蒸馏/深度辅助监督""竞争地形"**。在最终裁决前应至少把前四项进入实验，否则 blind/depth 的比较仍是在"弱方法论"上做。

## 6. 现在是否值得引入（2026-10-24 逐项结论）

| 弹药 | 现在引入？ | 理由/成本 |
|---|---|---|
| **竞争地形代理 + 任务成功奖励** | **是，第一优先** | 决定训练分布和奖励与比赛得分对齐；不做的话后面所有比较都建立在错误环境上；地形约 1–1.5 天，任务奖励与地形一起做 |
| **历史帧（blind 45→270；depth 45×6+64）** | **是，第二优先** | 纯配置改动（MjLab native `history_length`），部署契约 270 维已被 rl_sar/quadruped_control 支持；预计对 rough/障碍稳定性提升；A/B 成本 2×~1–2 h |
| **mirror loss 0.1 + foot_clearance** | **是，与历史帧同批** | 已有 flat A/B 证据，改动只是环境变量；回归四个对称性指标即可；几乎零代码 |
| **HIM 完整版（estimator/对比学习）** | **是，第三优先（history 之后）** | 训练仓已实现但没训过；若 history 单独不够再上；成本中等、调参风险中 |
| **教师蒸馏（height scan 特权教师 → depth 学生）** | **是，depth 线第四优先** | 对 depth 最有价值的方法学升级；需要先训教师（带 height scan 的 actor）再蒸馏；总成本约 3–4 h GPU + 半天工程 |
| **深度 aux loss（从 CNN latent 预测 height scan/教师特征）** | **是，可与蒸馏并行或更早** | 训练-time 辅助头，部署不增加输入；实现约半天；文献支持（视觉 locomotion 系列） |
| **depth warm-start（blind→depth）** | **是，但要和 from-scratch 对照** | 机制已验证；但简单地形筛选里 warm-start@3000等效（12.83）≈ blind@3000（13.15）< depth-from-scratch（14.86）——不能预设 warm-start 更好；竞争地形批次两臂都跑 |
| **深度分辨率 64×48 vs 32×32、latent 结构 A/B** | **做小 A/B（预算内）** | 成本 ×1.7，先 300–500 iter 筛选再决定 |
| **mirror data augmentation** | **暂不** | mirror loss 0.1 先做；DA 需给 critic height scan 补镜像，收益不确定 |
| **RNN/GRU 策略** | **不做** | 部署要维护 hidden state，收益与 history 重叠，优先级低于 history |
| **渲染级深度 DR（噪声/丢帧/延迟/外参）** | **最后做** | sim-only 比赛优先级低于"能不能过障碍"；等地形/课程稳定后再 fine-tune |
| **AMP/运动先验、gait 参数化、ViT** | **不做** | 得分收益低、工期高；答辩可作背景 |
| **多 seed** | **只在最终 winner 复验** | 用于降低偶然性，不作为提分手段 |

## 7. 术语澄清（对应本轮提问）

- **warm-start 臂**：指"用 blind PPO 的 actor 权重初始化 depth actor"的对照 run（首层前 45 列复制、CNN latent 64 列置零、critic/action std 复制、command curriculum range 恢复）。当前排队的 `cmp_depth_warm_1500` 只是**简单地形上的机制验证 + 筛选数据**；最终 depth 候选会是"blind-final（竞争地形/全方法论）→ depth warm-start → 竞争地形续训"，因此**排队的 warm-start 臂会被全方法论长跑取代**，只保留其机制验证价值（若 GPU 冲突可取消）。
- **竞争地形代理**：不是直接拿 Part1/Part2 的 MJCF 场景训练，而是用 mjlab terrain generator 程序化生成大量"障碍类型/尺寸与比赛一致、但随机布局"的地形 patch（绕柱/桥/限高杆/高墙/砂砾/T 台阶/梅花桩/沟壑），以便有随机化与课程；真实 Part1/Part2 场景只用于最终 judge 评测。
- **任务成功奖励**：当前训练任务是"速度跟踪"基线——没有起点/终点/障碍成功定义；对比赛级任务，"过桥/穿限高杆/到终点"这类稀疏成功奖励是**基本要求但当前缺失**，所以列入第一优先级与竞争地形一起做（不是我们忘了一个开关，而是任务定义还没升级）。
- **teacher-student 蒸馏**：有意义的做法不是"从 blind 蒸馏"（blind 没有视觉信息，学生只会模仿盲走），而是**特权教师**——给 actor 加 height scan（或 heightmap 等训练期特权量）训一个"看得见地形"的教师，再蒸馏到 depth 学生（DAgger/KL/动作 MSE + PPO 微调）。和"从零学"比：蒸馏提供稠密监督、通常更省样本；和"续训已有 depth"比：如果已有 depth 是在别的分布上训的，不如从 blind-final warm-start 或从特权教师蒸馏。
- **aux loss（辅助损失）**：训练期额外加在深度 CNN 上的监督项，例如让 CNN latent 预测局部高度图/height scan、预测教师 latent、或做重建/对比学习；只用于训练，部署时去掉辅助头，不改变 actor 输入。它能让 CNN 更快学到"地形相关特征"，尤其当 depth 线落后 blind 时值得加。
- **push 随机化**：mjlab interval event 会在 reset/每次触发后按 `interval_range_s` 逐 env 采样，原先 `(16,16)` 等于固定日程；已改为 `(6,20)`，当前正在跑的 run 不受影响（配置在进程启动时读取），从竞争地形批次起生效。
