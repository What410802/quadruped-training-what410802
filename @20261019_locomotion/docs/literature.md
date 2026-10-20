# 文献清单：训练方法、地形与鲁棒性

> 这份清单服务于三个阶段：S1 基础 locomotion / S2 台阶与梅花桩 / S3 域随机化与鲁棒性。查文献时优先**代码可获取、可复现**的；论文 PDF 不入库，只记链接与访问情况（[`../../docs/conventions.md`](../../docs/conventions.md) §4.10）。
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
| Learning Quadrupedal Locomotion on Deformable Terrain | Science Robotics 2023 | [DOI](https://doi.org/10.1126/scirobotics.ade2256) | 无公开代码 | 可变形地形（松散/碎石）的建模与训练；S1 碎石地参考 |
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

## 7. 文献获取备注

- arXiv 可直接下载 PDF；Science Robotics 的 DOI 需要校园网/机构订阅，脚本访问返回 403 属反爬而非断网；如遇校园网也打不开，告诉我题名，我找开放获取版本或替代综述。
- 代码可用性以论文页/仓库为准，引用时记录版本或 commit（§6.1、§6.2）；不能复现的论文只作为方法参考。
- 本次清单只收录与本任务直接相关的；后续每读一篇，把“结论 + 对我们的影响 + 是否做实验”补在下方“阅读笔记”一节，避免重复读。
