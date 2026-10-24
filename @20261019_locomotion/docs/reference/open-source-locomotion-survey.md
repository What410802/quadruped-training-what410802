# 开源四足训练仓库调研与借用建议（2026-10-24）

> 触发：stage4 blind 策略暴露两个问题——(1) **后腿几乎不动**（实测 lift：FL 9.6 cm、FR 3.8 cm、RL 0.3 cm、RR 0.4 cm，后腿基本拖地）；(2) 训练命令 `wz=0` 导致**转向不跟随**。用户提出"借鉴开源工作、从已有基础运动能力调优而不是从头造"，并计划增加"大脑"模型（视觉/IMU → 速度指令）。
> 本文件回答：是否合理、有哪些可带起来训练的仓库、推荐路线。

## 1. 结论先行

- **合理，且应尽快做**。我们目前的问题不是"框架不好"，而是**从零 PPO + 手调奖励**在 8k iter 内没有学出稳定四足步态与爬越技能；开源工作已经提供了成熟配方（奖励、课程、历史帧、teacher-student、步态先验、部署）。
- 但"直接拿别人 checkpoint 就能跑"只在**同一机器人 + 同一观测/动作/关节契约**时成立。对我们最有价值的是：
  1. **同机器人同契约的 `best.pt`（HIMLoco 270-D）** —— 主办方给的本机策略，之前 Part2 扩展窗口 8/20，远好于我们自训的 0/27；应作为**基座/教师**，而不是只当对照。
  2. **MuJoCo 系开源仓库的训练 recipe**（MuJoCo Playground / mjlab / legbot_lab 的 TS 配方）—— 在我们 5060 Ti 上能跑，不引入 IsaacGym/Isaac Sim 风险。
  3. **导航"大脑"**：Navigation Model Zoo（ONNX，Apache-2.0）直接输出 `[v, ω]`，可插在我们的低层策略前；但对本次比赛（Part1 人工遥控、Part2 固定障碍）**优先级最低**。
- **不建议**把主线切到 IsaacGym 系仓库（legged_gym / unitree_rl_gym / parkour / extreme-parkour / HIMLoco 原仓库）：IsaacGym 已停维护、依赖旧 CUDA/驱动，RTX 5060 Ti（Blackwell）大概率起不来；IsaacLab/Isaac Sim 4.5+ 虽可能支持新卡，但安装 ~10–20 GB、编译/驱动风险高，和 11 月 4 日赛期不匹配。

## 2. 可带起来训练的仓库清单

| 仓库 | 栈 | 机器人 / 任务 | 预训练权重 | 许可 | 5060Ti 可跑性 | 对本次比赛的价值 |
|---|---|---|---|---|---|---|
| [MuJoCo Playground](https://github.com/google-deepmind/mujoco_playground) | MJX / MuJoCo Warp / rsl-rl | Go1/Go2/Barkour、四足/双足 locomotion、vision（MJWarp batch renderer） | 需查 README/Colab（训练脚本齐全） | Apache-2.0 | **高**（MJX/Warp，与我们 mjlab 同生态） | **首选参考**：joystick 速度跟踪的奖励/课程/DR 配方、vision 方案、Colab 可直接训 |
| [mjlab](https://github.com/mujocolab/mjlab) | MuJoCo Warp + rsl_rl | 我们当前栈（velocity/parkour 等任务） | 无官方预训练 | Apache-2.0 | **高**（已在跑） | 继续用作训练/评测底座；把 Playground 配方移植进来 |
| [HIMLoco](https://github.com/InternRobotics/HIMLoco) | IsaacGym | 四足 HIM/H-infinity locomotion | 官方仓库/FLORES 有 policy（同 `best.pt` 系） | 代码可复现，许可待核 | 低（IsaacGym） | **算法与 270-D 历史帧契约来源**；`best.pt` 可直接在 rl_sar 中用（已验证） |
| [legbot_lab](https://github.com/Robot-Nav/legbot_lab) | Isaac Lab 2.2 | 自研 Legbot（Go2 同构 12 DoF），PPO + 10 帧历史、TS-MoE、MuJoCo DDS 部署 | 无（提供训练/部署全链） | Apache-2.0 | 中低（Isaac Lab 依赖） | **工程模板参考**：45 维×10 帧、非对称 AC、teacher-student、sim2real 部署 |
| [unitree_rl_gym](https://github.com/unitreerobotics/unitree_rl_gym) | IsaacGym | Go2/H1/G1 速度跟踪 + 真机部署 | 仓库含预训练（以 README 为准） | BSD-3（宇树） | 低（IsaacGym） | Go2 步态/奖励参考；可借 checkpoint 做 retarget 对比 |
| [robot_lab](https://github.com/fan-ziqi/robot_lab) | Isaac Lab | 20+ 机器人（含四足）locomotion/部署 | 部分 | Apache-2.0 | 中低 | 多机器人配置/部署模板参考 |
| [legged_gym](https://github.com/leggedrobotics/legged_gym) + [rsl_rl](https://github.com/leggedrobotics/rsl_rl) | IsaacGym + rsl_rl | ANYmal 等 | 无 | BSD-3 | 低（IsaacGym）；rsl_rl 我们已用 | 经典奖励/课程/DR 设计参考（rsl_rl 已是我们的训练器） |
| [Zhuang et al. parkour](https://github.com/ZiwenZhuang/parkour) | IsaacGym | 四足视觉跑酷、技能拆分 | 无/少量 | MIT | 低 | 障碍技能拆分、课程设计参考 |
| [extreme-parkour](https://github.com/chengxuxin/extreme-parkour) | IsaacGym | 极限跑酷（高台/跳沟） | 无 | **CC BY-NC 4.0（非商用）** | 低 | 只读方法，不搬代码 |
| [extreme-quadruped-parkour](https://github.com/yobel-sungkooklee/extreme-quadruped-parkour) | IsaacLab | Go2 80 cm 沟/45 cm 台阶 | 无 | BSD-3 | 中低 | 能力上限/奖励参考 |
| [DreamWaQ](https://github.com/Manaro-Alpha/DreamWaQ)（社区实现） | IsaacGym | 地形隐式估计 | 无 | 待核 | 低 | 历史帧/地形估计对照（我们已有 HIM 线） |
| [Navigation Model Zoo](https://huggingface.co/UCLA-VAIL/Navigation-Model-Zoo-Public) | PyTorch/ONNX（视觉导航） | GNM/ViNT/NoMaD 等，输入 RGB 历史 → 轨迹/`[v, ω]` | **有 ONNX 权重** | Apache-2.0 | **高**（CPU/GPU 推理） | **"大脑"直接可用**：接相机帧输出速度指令；先做 demo 不必训练 |
| [Nav2](https://github.com/ros-navigation/navigation2) | ROS 2 | 经典导航栈（地图/规划/控制） | — | Apache-2.0 | 高 | 若需要自动走全场，最稳的"大脑"其实是 waypoint + Nav2，而不是再训一个 VLA |

> 另：本地 `docs/reference/literature.md` 已收录的 HIMLoco、DreamWaQ、parkour、extreme-parkour、terrain_benchmark、RoboGauge、LearningHumanoidWalking 等，本轮都已纳入上表或作为对照；之前没用起来的主要原因是 **栈不兼容（IsaacGym）、许可限制（CC BY-NC）或与我们的 rl_sar/mjlab 部署契约不一致**，不是忽略。

## 3. 对"借用开源"的具体建议

### 3.1 基座运动能力（最优先，收益最大）

1. **先用 `best.pt`（HIMLoco 270-D）当基座/教师**：同一机器人、同一关节顺序、同一 45-D×6 帧契约；我们已实现 270-D 导出与 rl_sar 部署。把比赛任务奖励加在它的输出上做 **short fine-tune**（或用它做 DAgger/教师蒸馏），比从零训 8k iter 更可能得到稳定步态/爬越能力。
2. **用 MuJoCo Playground 的 joystick/rough terrain recipe 修步态**：包括步态相位/air-time/足端 clearance 奖励、命令课程、地形课程、DR；移植到 mjlab 的 `black-competition`，先只训平地/缓坡，把"后腿拖地+转向"修好（目标：四足都有摆动相、yaw 跟踪 ±1 rad/s）。
3. **步态修复的可量化验收**（用我们已有 gait 脚本扩展）：每腿摆动相占比、每腿 foot lift、RL/RR 与 FL/FR 的接触相位差、yaw 阶跃响应；当前实测 FL 9.6 cm / FR 3.8 cm / RL 0.3 cm / RR 0.4 cm，必须改到四腿同量级。

### 3.2 障碍技能（Part2）

- 借 **parkour 系列（Zhuang / extreme）** 的"技能拆分 + 课程 + 成功判定"设计，不搬其 IsaacGym 代码；在 mjlab 里用我们已有 competition terrain + goal 奖励实现。
- 若 `best.pt` 基座 + fine-tune 仍过不了爬台/沟，再考虑 **AMP/参考步态**（开源有 ANYmal/Go2 动作数据）或 **teacher-student 特权教师**（高度扫描/地形类型）蒸馏。

### 3.3 "大脑"（视觉导航高层策略）

- 用户设想合理：高层模型输入视觉/IMU → 输出 `(vx, vy, wz)`，低层策略跟踪。开源里 **Navigation Model Zoo** 最接近：GNM/ViNT/NoMaD 等 ONNX 权重，统一 `inference_vw()` 输出 `[v, ω]`，Apache-2.0；可先用它的 goal-free 模式做 demo。
- 但对本次比赛：**Part1 是人工遥控**（不需要大脑），**Part2 是固定障碍档位的能力测试**（不需要长距离导航）；大脑更多是"自动走全场/演示"的加分项，不应挤占低层步态与爬越技能的开发时间。
- 若要做自动走全场，最便宜可靠的方案是 **Nav2/waypoint + 纯跟踪**（或相机检测门柱后给目标点），而不是训练 VLA；等低层策略能稳定跟踪速度指令后再接。

## 4. 风险与边界

- **契约不匹配**：不同仓库的关节顺序、默认姿态、动作缩放、观测历史布局不同；直接加载权重会"能跑但不对"。必须像 best.pt 一样做 270-D 布局转换 + rl_sar config 校验（我们已有脚本/经验）。
- **许可**：extreme-parkour 是 CC BY-NC（非商用），只读思路；其余 Apache/BSD/MIT 可用但要在文档标注来源与版本。
- **算力/驱动**：IsaacGym 系不建议尝试；IsaacLab 系先做最小验证（能否在 5060Ti + 当前驱动上启动），不要一上来全量安装。
- **时间**：11 月 4 日赛期，优先"能出可演示/可评测结果"的路径：best.pt 基座 + 比赛场景 fine-tune + Nav2/脚本大脑（可选）> 重新搭 Isaac 栈。

## 5. 建议的下一步（待用户确认）

1. **停止从零手调步态**；以 `best.pt` 为基座，在 `black-competition` 上做 1–2k iter warm-start fine-tune（先平地+缓坡，验收四足摆动/转向），再上障碍课程。
2. 同时把 MuJoCo Playground 的 joystick 配方（奖励/课程/DR）移植到我们的 competition task，作为对照臂。
3. 障碍技能：保留我们已有的 competition terrain/goal 奖励，按 parkour 的"技能拆分"重排课程（先爬台/台阶，再沟/墙/桩）。
4. 大脑：只做 demo 级接入 Navigation Model Zoo 或 Nav2，不投入训练；等低层速度跟踪稳定后再说。

## 6. MuJoCo Playground 专项核查（2026-10-24，P1）

### 6.1 开源完整性

- **代码**：`google-deepmind/mujoco_playground` 为 **Apache-2.0**（LICENSE 与 README 均注明；非官方 Google 产品，但代码开源）。
- **机器人/场景资产**：Go1/Go2 等来自 MuJoCo Menagerie（各机器人目录自带许可，通常 Apache-2.0/BSD-3），Playground 的 `xmls/` 为仓库内 Apache-2.0 文件；rough terrain 纹理为 Polyhaven CC0。使用时需逐个资产核对许可。
- **预训练策略权重：仓库本身不附带**（2026-10-24 用 GitHub API 查过仓库根目录和 `mujoco_playground/_src/locomotion/go1/`：只有 `base.py`/`joystick.py`/`getup.py`/`xmls/` 等，没有 `checkpoints/` 或 `.pkl/.pt` 权重）。官方提供的是**训练脚本 + Colab 教程**：`train-jax-ppo`（JAX/brax）与 `train-rsl-ppo`（rsl_rl/PyTorch），需要自己训。
- 结论：**"完全开源"= 代码与资产开源可训练；但不是"下载即有可移植策略"**。要"移植他们的策略模型到 rl_sar"，第一步得在 5060Ti 上训练一个（Go1 平地 joystick 在 MJX/Warp 上通常几十分钟内可出可用步态）。

### 6.2 策略模型的输入/输出（以 `Go1JoystickFlatTerrain` 为例，源码 `go1/joystick.py`）

- **输入观测（单帧 48 维）**，按 `_get_obs()` 的 hstack 顺序：
  `local_linvel(3) + gyro(3) + gravity(3) + (joint_pos - default_pose)(12) + joint_vel(12) + last_action(12) + command(3)`。
  （另有 `privileged_state` 仅训练 critic 用，不部署。）
- **输出动作（12 维）**：`motor_targets = default_pose + action * action_scale`，其中 `action_scale = 0.5`；控制频率 `ctrl_dt = 0.02 s`（sim_dt 0.004、4 子步），`Kp=35`、`Kd=0.5`，default pose 取模型 `keyframe("home")` 的 qpos[7:]。
- **策略网络**：MLP（PPO），JAX/brax 或 rsl_rl 两种后端；JAX checkpoint 是 brax 参数字典（pickle），rsl_rl checkpoint 是 PyTorch `.pt`（含 actor/critic 权重）。
- **导出**：仓库没有现成的 TorchScript/ONNX 导出脚本；需要自己把 actor MLP 导出为 TorchScript（或训练时用 `train-rsl-ppo`，直接从 rsl_rl 权重导出）。

### 6.3 移植到 rl_sar 的可行性与差距

| 项 | Playground Go1 | 我们的 Black / rl_sar | 处理 |
|---|---|---|---|
| 观测维度/顺序 | 48：linvel, gyro, gravity, qpos, qvel, last_act, command | 45：command, ang_vel, gravity, qpos, qvel(×0.05), last_act | 写桥接 wrapper：45→48；无 base linvel（置 0 或由命令估计）；qvel 需 ×20（去 scale）；command 移到末尾 |
| 动作 | 12，`default + 0.5*a` | 12，`default + 0.25*a` | wrapper 输出 ×2（或临时改 rl_sar action_scale=0.5） |
| 关节顺序 | 常量里 feet 为 FR/FL/RR/RL（需按 XML actuator 顺序核对） | FL/FR/RL/RR（policy order） | 按 joint name 重排并做映射 |
| 增益/频率 | Kp 35 / Kd 0.5，20 ms | Kp 40 / Kd 1.2，20 ms | 测试时临时改 rl_sar config，或接受失配先看趋势 |
| 机器人动力 | Unitree Go1 | Black（Go1 同构但质量/惯量/限位不同） | 零样本预计只能"走起来"，不能指望性能；用于验证链路 |
| 权重 | 无预训练，需训练 | — | 训练 Go1 平地 joystick（JAX/rsl-ppo）→ 导出 TorchScript |

结论：**移植链路可行（观测/动作都是 12 关节 + MLP，桥接成本低）**，但需要先训练一份 Playground 权重；零样本跨机器人（Go1→Black）预计步态可用性一般，适合做"基座/步态参考"，最终仍要在我们的机器人上 fine-tune。P1 已在本机启动 Playground 环境安装（`~/rc_work/mujoco_playground` + uv venv），下一步训练 Go1 joystick 并导出 TorchScript 桥接测试。
