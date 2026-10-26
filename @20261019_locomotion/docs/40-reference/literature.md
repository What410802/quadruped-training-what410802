# 文献清单：训练方法、地形与鲁棒性

> 这份清单服务于三个阶段：S1 基础 locomotion / S2 台阶与梅花桩 / S3 域随机化与鲁棒性。查文献时优先**代码可获取、可复现**的；论文 PDF 不入库，只记链接与访问情况（[`../../docs/conventions.md`](../../../docs/conventions.md) §4.10）。
>
> 访问情况（2026-10-19 本机）：arXiv 摘要页可访问（HTTP 200），Science Robotics 的 DOI 页对脚本返回 403（反爬/订阅），校园网浏览器一般可打开；如遇打不开的论文告诉我，我列替代来源或找开放版本。代码列若写“无公开代码”，表示论文思路可读、复现需自己写。

## 1. 基础 locomotion 与地形学习

| 论文 | 年份/出处 | 链接 | 代码/可复现性 | 用途 |
|---|---|---|---|---|
| Learning Quadrupedal Locomotion over Challenging Terrain（Lee 等） | Science Robotics 2020 | [DOI](https://doi.org/10.1126/scirobotics.abc5986) | legged_gym（BSD-3）公开 | 地形课程 + privileged 训练的经典范式，S1/S2 的方法基础 |
| Learning to Walk in Minutes Using Massively Parallel Deep RL（Rudin 等） | CoRL 2022 | [arXiv 2109.11978](https://arxiv.org/abs/2109.11978) | legged_gym/rsl_rl 公开 | 大规模并行 PPO 的默认超参与地形课程；mjlab 的基线与之同源 |
| Learning Agile and Dynamic Motor Skills for Legged Robots（Hwangbo 等） | Science Robotics 2019 | [DOI](https://doi.org/10.1126/scirobotics.aau5872) | 无公开代码 | 模型 + RL 的早期范式；理解“仿真到实机的系统辨识”思路 |
| Rapid Locomotion via Reinforcement Learning（Margolis 等） | RSS 2022 | [arXiv 2205.02824](https://arxiv.org/abs/2205.02824) | 无公开代码 | 高速小跑、步频/占空比调节的奖励与课程；S1 小跑目标参考 |
| Walk These Ways: Tuning Robot Control for Generalization with Multiplicity of Behavior（Margolis 等） | CoRL 2023 | [arXiv 2212.03238](https://arxiv.org/abs/2212.03238) | 无公开代码（论文主页有视频） | 步态参数化与多行为泛化；S1“站/走/小跑平滑切换”的参考 |
| Learning Agile Robotic Locomotion Skills by Imitating Animals（Peng 等） | RSS 2020 | [arXiv 2004.00784](https://arxiv.org/abs/2004.00784) | 无公开代码 | 动物动作先验；自然步态/平滑切换的可选方案（AMP 系） |

## 2. 感知、状态估计与 teacher-student

| 论文 | 年份/出处 | 链接 | 代码/可复现性 | 用途 |
|---|---|---|---|---|
| Hybrid Internal Model: Learning Agile Legged Locomotion with Simulated Robot Response（HIMLoco） | ICLR 2024 | [arXiv 2312.11460](https://arxiv.org/abs/2312.11460) | [InternRobotics/HIMLoco](https://github.com/InternRobotics/HIMLoco)（代码可复现，许可未明） | `best.pt` 的算法来源；S2 的 HIM 对照（训练仓库已有 `black-rough-him`） |
| RMA: Rapid Motor Adaptation for Legged Robots | RSS 2021 | [arXiv 2107.04034](https://arxiv.org/abs/2107.04034) | 无公开代码（论文页有视频） | 在线适应/teacher-student 的早期代表；S2/S3 的适应路径参考 |
| CTS: Concurrent Teacher-Student Reinforcement Learning for Legged Locomotion | RA-L 2024 | [arXiv 2405.10830](https://arxiv.org/abs/2405.10830) | 见论文页 | 教师-学生联合训练；与 HIM/特权 critic 路线对照 |
| Learning H-Infinity Locomotion Control | 2024 | [arXiv 2404.14405](https://arxiv.org/abs/2404.14405) | 同上仓库内 | 扰动抑制/鲁棒性；S3 的理论参考 |
| DreamWaQ: Learning Robust Quadrupedal Locomotion With Implicit Terrain Imagination via Deep RL | ICRA 2023 | [arXiv 2301.10602](https://arxiv.org/abs/2301.10602) | [Manaro-Alpha/DreamWaQ](https://github.com/Manaro-Alpha/DreamWaQ)（社区实现） | 用历史隐式估计地形；与 HIM 同类，S1/S2 对照 |
| Concurrent Training of a Control Policy and a State Estimator for Dynamic and Robust Legged Locomotion | RA-L 2022 | [arXiv 2202.05481](https://arxiv.org/abs/2202.05481) | 无公开代码 | 策略与状态估计联合训练；部署侧观测估计的参考 |
| Learning robust perceptive locomotion for quadrupedal robots in the wild（Miki 等） | Science Robotics 2022 | [DOI](https://doi.org/10.1126/scirobotics.abk2822) | 无公开代码（论文有大量 sim2real 细节） | **teacher-student + 特权感知**的标准做法；后续接相机/高度扫描的主参考 |
| Learning Agile Locomotion on Risky Terrains | 2023 | [arXiv 2311.10484](https://arxiv.org/abs/2311.10484) | 无公开代码 | 可变形/危险地形上的训练技巧；S3 压力测试参考 |

## 3. 越障、跑酷、台阶与梅花桩

| 论文 | 年份/出处 | 链接 | 代码/可复现性 | 用途 |
|---|---|---|---|---|
| Robot Parkour Learning（Zhuang 等） | CoRL 2023（Oral） | [arXiv 2309.05665](https://arxiv.org/abs/2309.05665) | [ZiwenZhuang/parkour](https://github.com/ZiwenZhuang/parkour)（MIT） | 视觉跑酷与技能学习；台阶/障碍技能拆分参考 |
| Extreme Parkour with Legged Robots（Cheng 等） | ICRA 2024 | [arXiv 2309.14341](https://arxiv.org/abs/2309.14341) | [chengxuxin/extreme-parkour](https://github.com/chengxuxin/extreme-parkour)（CC BY-NC 4.0，**非商用**） | 高台/跳沟等极限技能的课程与奖励设计；只作参考不搬代码 |
| PIE: Parkour with Implicit-Explicit Learning Framework for Legged Robots | ICRA 2024 | [arXiv 2408.13740](https://arxiv.org/abs/2408.13740) | 见论文页 | 隐式/显式两段式跑酷；台阶+落点决策参考 |
| ANYmal Parkour: Learning Agile Navigation for Quadrupedal Robots | Science Robotics 2024 | [DOI](https://doi.org/10.1126/scirobotics.adi7566) | 无公开代码 | 感知式跑酷/导航；S2 的感知式扩展参考 |
| Learning Quadrupedal Locomotion on Deformable Terrain | Science Robotics 2023 | [DOI](https://doi.org/10.1126/scirobotics.ade2256) | 无公开代码 | 可变形地形（松散/碎石）的建模与训练；参数化 granular media 模型 + 在线地形参数辨识；S1 碎石地参考 |
| GM-Loco: Terrain-Adaptive Humanoid Locomotion on Granular Media | 2026 | [arXiv 2609.10286](https://arxiv.org/abs/2609.10286) | 项目页/代码见论文 | 3D RFT 颗粒接触模型 + MPM（NVIDIA Newton）验证 + teacher-student/VAE 地形隐变量；颗粒地形训练的可借鉴路线 |
| Robust Humanoid Walking on Compliant and Uneven Terrain with Deep RL | Humanoids 2024 | [arXiv 2504.13619](https://arxiv.org/abs/2504.13619) | [rohanpsingh/LearningHumanoidWalking](https://github.com/rohanpsingh/LearningHumanoidWalking) | 只靠本体感知 + 随机化地形课程过软/不平地形；支持“刚性随机起伏预训练”路线 |
| Go2 Extreme Parkour（仓库，非论文） | 2026 仓库 | [yobel-sungkooklee/extreme-quadruped-parkour](https://github.com/yobel-sungkooklee/extreme-quadruped-parkour)（BSD-3） | 可复现（IsaacLab） | Go2 80 cm 沟、45 cm 台阶的公开能力上限参考 |

## 4. PPO 与训练技巧

| 论文 | 年份/出处 | 链接 | 用途 |
|---|---|---|---|
| Proximal Policy Optimization Algorithms（Schulman 等） | 2017 | [arXiv 1707.06347](https://arxiv.org/abs/1707.06347) | PPO 原论文 |
| What Matters In On-Policy Reinforcement Learning? A Large-Scale Empirical Study | 2020 | [arXiv 2006.05990](https://arxiv.org/abs/2006.05990) | 超参/归一化/优势估计的实证优先级，先按它调再谈结构改动 |
| Implementation Matters in Deep Policy Gradients: A Case Study on PPO and TRPO | 2020 | [arXiv 2005.12729](https://arxiv.org/abs/2005.12729) | PPO 实现细节的影响；对应 rsl_rl 的默认实现 |
| AMP: Adversarial Motion Priors for Stylized Physics-Based Character Control（Peng 等） | 2021 | [arXiv 2104.02180](https://arxiv.org/abs/2104.02180) | 动作先验/自然步态；S1 平滑切换的后选方案 |
| Toward Reliable Sim-to-Real Predictability for MoE-based Robust Quadrupedal Locomotion | 2026 | [arXiv 2602.00678](https://arxiv.org/abs/2602.00678) | 队内/公开 MoE + 评测体系（RoboGauge）配套论文；S2/S3 的多专家与评测参考 |

## 5. 域随机化、鲁棒性与评测

| 论文/工具 | 年份/出处 | 链接 | 代码/可复现性 | 用途 |
|---|---|---|---|---|
| Learning Dexterous In-Hand Manipulation（OpenAI，DR 经典） | 2018 | [arXiv 1808.00177](https://arxiv.org/abs/1808.00177) | 训练代码未公开 | 域随机化的方法论；S3 的随机化清单参考 |
| Generating a Terrain-Robustness Benchmark for Legged Locomotion（GTRB） | ICRA 2023 | [arXiv 2208.07681](https://arxiv.org/abs/2208.07681) | [zita-ch/terrain_benchmark](https://github.com/zita-ch/terrain_benchmark) | 地形鲁棒性 benchmark；S3 评测地形多样性参考 |
| RoboGauge（评测工具） | 2026 | [wty-yy/RoboGauge](https://github.com/wty-yy/RoboGauge)（MIT） | 可复现（Python 3.8–3.11） | 指标定义：速度跟踪、关节限位、功率、力矩平滑、摩擦裕度、ZMP 裕度；S1/S3 的评测口径 |
| Learning-based legged locomotion: State of the art and future perspectives（综述） | 2025 | 待核对 arXiv 页 | — | 领域全景，写开题/汇报时用 |

## 6. 建议阅读顺序（与实验对应）

1. **先读**：Lee 2020（地形课程）、Rudin 2022（并行 PPO 基线）、Walk These Ways（步态/多行为）、HIMLoco（历史估计）——对应 S1。
2. **再做对照实验前读**：DreamWaQ、CTS、Miki 2022（teacher-student）——决定 S2 用 HIM 还是特权/蒸馏路线。
3. **台阶/梅花桩前读**：Robot Parkour、Extreme Parkour、PIE、ANYmal Parkour——课程、奖励、落点/足端设计。
4. **S3 前读**：H-Infinity、DR 原始文献、GTRB、RoboGauge——随机化清单与评测指标。
5. **PPO 调参时**：What Matters、Implementation Matters——避免重复调参。

## 7. 培训方补充材料（2026-10-20）

只读 `ReadOnly.d/Downloaded.d/` 新增 7 个 PDF，按标题对应 5 篇论文（两篇带中文翻译）：

| 文件 | 对应条目 |
|---|---|
| `2107.04034v1.pdf`、`2107.04034_zh-Hans.pdf` | RMA（§2 新增） |
| `2405.10830v2.pdf` | CTS（§2 新增） |
| `dreamwaq.pdf` | DreamWaQ（§2） |
| `2312.11460v3.pdf`、`2312.11460_zh-Hans.pdf` | HIMLoco（§2） |
| `Cheng 等 - 2023 - Extreme Parkour with Legged Robots.pdf` | Extreme Parkour（§3） |

看起来覆盖了训练计划里的 RMA、CTS、DreamWaQ 三篇，另含 HIMLoco 与 Extreme Parkour；文件指纹与来源记录见 [`materials.md`](../10-part1/terrain-materials.md) §8。PDF 不入库。

## 8. 文献获取备注

- arXiv 可直接下载 PDF；Science Robotics 的 DOI 需要校园网/机构订阅，脚本访问返回 403 属反爬而非断网；如遇校园网也打不开，告诉我题名，我找开放获取版本或替代综述。
- 代码可用性以论文页/仓库为准，引用时记录版本或 commit（§6.1、§6.2）；不能复现的论文只作为方法参考。
- 本次清单只收录与本任务直接相关的；后续每读一篇，把“结论 + 对我们的影响 + 是否做实验”补在下方“阅读笔记”一节，避免重复读。

## 9. 阅读笔记（2026-10-21，培训方 5 篇）

> 以下按 `ReadOnly.d/Downloaded.d/` 的 5 篇英文 PDF 原文整理，中文翻译只辅助理解；不把 AI 二手总结当事实。论文的仿真栈是 Isaac Gym/RaiSim，接触/驱动/PD 与 MuJoCo 不同，数值不能直接照搬，只拿结构和方法。

### 9.1 五篇各自的关键点

| 论文 | 核心方法 | 对当前阶段的可用点 | 不直接照搬的点 |
|---|---|---|---|
| **RMA**（[arXiv 2107.04034](https://arxiv.org/abs/2107.04034)） | 基础策略 + 环境因子编码器 `z`（17 维特权量→8 维），部署时用最近 50 步状态-动作历史回归 `z`；策略 100 Hz、适应 10 Hz | 10 项“生物能量”奖励（前进、横移/转向、机械功、地面冲击、平滑、动作幅值、关节速度、姿态、z 加速度、足端滑移）；惩罚系数先从很小逐步加大；摩擦/质量/电机强度 DR 范围 | 状态里含足端接触布尔量，比赛规则不允许进网络；无地形课程；MuJoCo 需重调 PD/摩擦 |
| **HIM**（[arXiv 2312.11460](https://arxiv.org/abs/2312.11460)） | 只用本体感知，从历史估计“系统响应”：显式速度 + 16 维隐式稳定性嵌入，用 prototypical contrastive learning 对齐 successor state；非对称 actor-critic | 奖励表与当前基线同源，额外列了 **foot clearance** 项（目标 0.09 m、权重 −0.01）；地形课程 20×10、跟踪 80% 升级；200M 样本/1 h RTX 4090 的样本效率目标 | 论文与官方 HIMLoco config 的 foot clearance 启用状态不一致（官方默认 scale 为 −0.0），必须自己做 A/B；HIM 需要 history/estimator，当前 45 维单帧 PPO 不能直接套 |
| **CTS**（[arXiv 2405.10830](https://arxiv.org/abs/2405.10830)） | 教师/学生并行环境（比例 3:1）共用一个策略/critic，学生仍用 PPO 目标更新；学生编码器对齐教师 32 维 latent | 奖励表比我们多：joint torque、collision、joint limit、feet regulation、feet distance、feet contact force、feet velocity；师生并发可避免两阶段蒸馏的信息损失 | 需要教师特权状态和额外编码器，不是当前 45 维盲策略的即插即用项；当前先不引入 |
| **DreamWaQ**（[arXiv 2301.10602](https://arxiv.org/abs/2301.10602)） | 非对称 actor-critic：actor 吃 5 帧本体历史，critic 吃特权状态；CENet 联合估计速度和环境 context | 结构最简单；奖励里有 foot clearance 和 **power distribution** `var(τ·q̇)²`，可用于抑制个别电机过热；适合做“历史 actor + 特权 critic”的第一版对照 | CENet 的 VAE latent 是否值得引入需要消融；本次不直接采用 CENet，先验非对称/历史路线 |
| **Extreme Parkour**（[arXiv 2309.14341](https://arxiv.org/abs/2309.14341)） | 统一内积奖励 `min(⟨v, d_w⟩, v_cmd)` + 足端离边缘 5 cm 惩罚 + 风格项；waypoint 地形课程；Phase 1 scandots teacher、Phase 2 depth student | 台阶/梅花桩阶段的**落足点/边缘安全**奖励可复用；世界系方向奖励避免原地转向骗奖励；视觉教师-学生路线 | 当前 2026 手动模式先不接相机；scandots/深度训练成本高，排到台阶/梅花桩阶段之后 |

### 9.2 对我们当前动作顺序的映射

1. **先做基础模型（flat + 砾石代理）**：RMA/HIM 的奖励表说明“能量/冲击/滑移/足端 clearance”是缺项；当前先补 **foot_clearance**（HIM 论文的 0.09 m/−0.01，做 A/B），不一次性把 CTS 的足端接触力/距离全塞进来。
2. **步态对称**：5 篇都没有直接处理“左右腿固定不对称”；RSL-RL 自带 `Symmetry` 扩展（mirror loss / data augmentation），比自写奖励更贴合策略等变性；mirror loss 必须配合足端 clearance，否则可能把不对称解压成“两条后腿都拖地”的对称解——这是我们要用 A/B 验证的风险。
3. **数值稳定性**：RMA 用“惩罚系数从小到大”的课程，HIM 用 `only_positive_rewards` 类做法；我们短期先加 per-step reward clamp、return/advantage clamp、stop-on-nonfinite，再考虑 reward 系数课程。
4. **砾石**：RMA/HIM 的粗糙地形都是随机高度场/起伏刚体代理，和我们的静态预沉降碎石 + `HfRandomUniform` 路线一致；自由关节碎石坑继续只做评测/保真，不进 4096 env 主训练。
5. **台阶/梅花桩**：Extreme Parkour 的 waypoint 内积奖励与 edge penalty 是后续 S2 的直接参考；现在只做地形/管线，不提前把视觉教师-学生拉进主线。

### 9.3 待验证

- foot clearance 的 0.09 m 目标是否适合 Black 的腿长/步高；先用 A/B 看足端高度、接触比例、跟踪误差，不直接当成正收益。
- mirror loss 系数（0.01/0.03/0.1）与是否同时做 data augmentation；当前只在 flat 上做 200–500 iteration 筛选。
- HIM 的 16 维 latent、CTS 的师生并发、DreamWaQ 的 CENet 均未在本仓库实现/验证，只能作为 S2/S3 的候选；先完成 flat+砾石 gate。
