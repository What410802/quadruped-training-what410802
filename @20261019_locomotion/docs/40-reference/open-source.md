# 可复用的开源实现与许可（本任务相关）

> 2026-10-19 通过 GitHub 检索 + README/文件树/许可证核对整理；完整长清单见仓库外的临时调查表（未入库），本文件只保留与本任务直接相关、值得动手复用的部分。许可为仓库当时显示的 license；会随上游改动，导入前再核对一次。

## 1. 训练框架与工程结构

| 项目 | 许可 | 与本任务的关系 | 怎么用 |
|---|---|---|---|
| [mujocolab/mjlab](https://github.com/mujocolab/mjlab) | Apache-2.0 | 训练框架（MuJoCo Warp GPU 并行） | 训练仓库已基于它；不改框架，只在地形/奖励/课程层扩展 |
| [N-W-wolf/nwwolf_mjlab_training_release](https://github.com/N-W-wolf/nwwolf_mjlab_training_release) | 队内仓库（公开） | `black-flat`/`black-rough`/HIM 的现成任务与导出 | 直接作为训练底座；本任务不改它的基础契约（45 维 obs、50 Hz 等） |
| [unitreerobotics/unitree_rl_mjlab](https://github.com/unitreerobotics/unitree_rl_mjlab) | Apache-2.0 | 宇树官方的 mjlab 训练 + C++ ONNX 部署 | 参考工程组织、训练→play→Sim2Real 流程 |
| [pollen-robotics/microduck_rl](https://github.com/pollen-robotics/microduck_rl) | Apache-2.0 | mjlab 自定义机器人 + 完整 sim2real 配方 | 参考域随机化、ONNX 导出、项目结构 |
| [fan-ziqi/robot_lab](https://github.com/fan-ziqi/robot_lab) | Apache-2.0 | IsaacLab 扩展库（多种足式/人形） | 只作奖励/课程/配置参考（IsaacLab 训练栈不在本任务主线） |
| [fan-ziqi/rl_sar](https://github.com/fan-ziqi/rl_sar) | Apache-2.0 | 策略部署框架（TorchScript + ROS） | 后续实机/手柄联调沿用队内移植版，不重写 |

## 2. 与本任务地形/技能直接相关的公开实现

| 项目 | 许可 | 质量参考 | 可复用点 |
|---|---|---|---|
| [zeitvex/RC_WheelLeg](https://github.com/zeitvex/RC_WheelLeg) | MIT | 2026 障碍赛全国一等奖第 7（轮足） | **最接近**：mjlab 训练（Flat/Rough/Crawl）、竞赛地形（高墙/限高杆）、障碍释放课程、分轴命令/奖励、Sim2Sim、航点与 IK 绕桩 |
| [Ruixi-Cheng/26RC_Field](https://github.com/Ruixi-Cheng/26RC_Field) | MIT | 2026 场地 SolidWorks（单场地 + 镜像拼图） | 建 2026 正式场地的几何依据（砂砾碎木坑待补） |
| [Zbszbszbssca/RC_MAP](https://github.com/Zbszbszbssca/RC_MAP) | **无许可证** | 2026 场地 MuJoCo 场景 | 只做布局/尺寸交叉校验，代码与资产不复制、不入库 |
| [Taojunfeng123/quadruped_robot_lab](https://github.com/Taojunfeng123/quadruped_robot_lab) | Apache-2.0 | 福州大学 12DOF 点足，作者报告粗地形 ~3 m/s、楼梯 ~2 m/s、盲走楼梯 ≤15 cm | 任务/奖励/课程配置参考（IsaacLab，非本任务训练栈） |
| [uwvwko-zzz/uw-himloco](https://github.com/uwvwko-zzz/uw-himloco) | BSD-3（legged_gym 头） | 南华大学 HIMLoco 复现（`high` 上高台分支） | HIM 训练/导出/部署结构参考 |
| [InternRobotics/HIMLoco](https://github.com/InternRobotics/HIMLoco) | 许可未明 | ICLR 2024，`best.pt` 来源 | HIM 算法实现；引用为主，代码不直接搬 |
| [jindadu00/legged_robot_competition](https://github.com/jindadu00/legged_robot_competition) | 无许可证 | Go2 梅花桩（legged_gym） | 梅花桩类地形的课程/奖励思路参考 |

## 3. 越障/跑酷（算法参考，注意许可）

| 项目 | 许可 | 用途 |
|---|---|---|
| [ZiwenZhuang/parkour](https://github.com/ZiwenZhuang/parkour) | MIT | 视觉跑酷与技能学习（Robot Parkour Learning，CoRL 2023） |
| [chengxuxin/extreme-parkour](https://github.com/chengxuxin/extreme-parkour) | CC BY-NC 4.0（**非商用**） | 高台/跳沟技能课程；只读参考 |
| [yobel-sungkooklee/extreme-quadruped-parkour](https://github.com/yobel-sungkooklee/extreme-quadruped-parkour) | BSD-3 | Go2 极端跑酷（80 cm 沟、45 cm 台阶）能力上限参考（IsaacLab） |
| [Manaro-Alpha/DreamWaQ](https://github.com/Manaro-Alpha/DreamWaQ) | 无明确许可 | 隐式地形估计的实现参考 |

## 4. 评测与部署

| 项目 | 许可 | 用途 |
|---|---|---|
| [wty-yy/RoboGauge](https://github.com/wty-yy/RoboGauge) | MIT | MuJoCo 自动评测：速度跟踪/稳定性/关节限位/功率/力矩平滑/摩擦裕度/ZMP；指标口径直接借用 |
| [zita-ch/terrain_benchmark](https://github.com/zita-ch/terrain_benchmark) | 无许可（论文 ICRA 2023） | 地形鲁棒性 benchmark 的地形生成思路 |
| [wty-yy/unitree_cpp_deploy](https://github.com/wty-yy/unitree_cpp_deploy) | MIT | 多策略运行时切换的 C++ 部署参考 |
| [haozhang04/LeggedSkillDeploy](https://github.com/haozhang04/LeggedSkillDeploy) | 无许可证 | Python 多策略状态机部署（只参考设计，不复制） |
| [evronix/quadruped_sim2sim](https://github.com/evronix/quadruped_sim2sim) | MIT | IsaacGym→Gazebo 的 sim2sim 流程参考（我们用 MuJoCo，方法可借鉴） |

## 5. 明确不重复造 / 不采用

- **不重写**：PPO 训练循环、地形生成器、课程框架、TorchScript/ONNX 导出、sim2sim 加载链、部署状态机——队内仓库与 mjlab 生态都有。
- **不采用为训练栈**：IsaacGym 系（HIMLoco、legged_gym、extreme-parkour、utorch 等）在 RTX 50（sm_120）上无法训练；只作算法参考。
- **不复制**：无许可证仓库（RC_MAP、LeggedSkillDeploy、jindadu00、LocoWiki 内容等）的代码/资产；引用时给链接与说明。
- **不引入的依赖**：为了本任务的 locomotion + 地形，不需要在本地 pixi 环境里装训练依赖（见 [`environment.md`](../30-ops/environment.md) §3）。

## 6. 引用与许可记录要求

- 用到外部代码/资产时，在本文件 §7 或任务 README 写明上游名称、URL、版本/commit、许可证（[`../../docs/conventions.md`](../../../docs/conventions.md) §6.1）；移植/改写保留版权头（§6.2）。
- 本任务已确认的来源：mjlab（Apache-2.0）、训练仓库（队内）、`@20260927_motor` 的 C++ viewer（本仓库自写）、26RC_Field（MIT，引用时注明）。

## 7. 本任务来源与许可

- 地形素材：培训方提供的只读材料 `terrain.zip`（单位置能力测试场，unitree 场景布局）与 `scene_terrain.xml`（unitree 模板改出的组合地形 playground）；2026 官方规则 V2.0、场地图册与 2027 规则 V1.0 为本机只读材料，规则原文可从 ROBOCON 官网与 LocoWiki 查。
- 2026 场地 CAD 参考：`Ruixi-Cheng/26RC_Field`（MIT，SolidWorks 单场地 + 镜像拼图）；`Zbszbszbssca/RC_MAP`（无许可证，仅参考，不入库）。
- 训练框架：`mujocolab/mjlab`（Apache-2.0）、队内训练仓库 `N-W-wolf/nwwolf_mjlab_training_release`（基于 mjlab）。
- C++ 视窗：复用本仓库 `@20260927_motor/cpp/src/viewer.h`（自写代码，GLFW + mjv/mjr）。
- 参考实现与论文的来源、版本与许可见本文件 §1–§5 与 [`literature.md`](literature.md)。
