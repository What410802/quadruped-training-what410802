# 部署栈对比：rl_sar vs quadruped_control（2026-10-22）

> 回答两个问题：上次 assignment 的 rl_sar 是否弃用；这次为什么选 `quadruped_control`，两者部署差别在哪。结论先行：**比赛主部署选 `quadruped_control`；rl_sar 不删除，作为参考资料和备选路径保留，但不维护两套并行主栈。**

## 1. 两套栈是什么

- `rl_sar`：上次 `@20261007_assignment` 移植的开源控制器框架，上游 `fan-ziqi/rl_sar` commit `e5c2f41`（Apache-2.0）。移植后是 ROS 2 控制器节点 `rl_sim`：订阅 `/motor_state`、`/imu`、`/joy`、`/cmd_vel`，输出 `/mit_command`；状态机为 Passive/GetUp/RL_Locomotion/GetDown，策略为 270 维 HIM 6 帧历史；当时接到 `@20261005_ros2` 的 `sim_node`，仿真节点和手柄节点未改。
- `quadruped_control`：团队 C++/ROS 控制工程（`N-W-wolf/quadruped_control`，上游 `coverMoon/quadruped_control`，本地 fork `What410802/quadruped_control`）。核心 `core/` + `motion/` + `policy/torch/` + MuJoCo 后端；支持 `Passive → GetUp → Stand → Running`、策略切换、Retry、Event chain、blackW 轮足行为；正式三进程 `ros2_gateway → motiond → mujoco_backendd`，单进程 `mujoco_sim` 用于调试。

## 2. 部署维度对比

| 维度 | rl_sar（上次 assignment） | quadruped_control（本次） |
|---|---|---|
| 架构 | 单体 ROS 2 控制器节点；FSM/SDK/输入都在一个包 | 控制核心与后端/ROS 适配/IPC 分层；单进程与三进程两种入口 |
| 状态机 | Passive/GetUp/RL/GetDown；策略切换和输入是 assignment 里新写的补丁 | MotionRuntime 原生状态机 + policy switch + Retry/Event chain；切换时清策略历史、必要时姿态过渡 |
| 策略契约 | 270 维 HIM（45×6 history，estimator+actor） | 配置化 TorchScript：45/270、`history_frames`、action scale、默认姿态、关节映射都能配 |
| 当前可用策略 | best.pt 270；45 维 flat 需改配置/适配 | 已接 45 维 `flat_ft`，policy 切换/GUI 已验证 |
| 仿真 | 接上次自建 `sim_node`；不是本任务自带 | 自带 MuJoCo backend + `mujoco_sim` GUI；本任务 Part1/Part2 scene 可直接开 |
| ROS 2 | 单节点 topic；`rl_sim` 已做相对名/namespace | 三进程正式路径有 gateway/daemon/IPC；单进程调试不必上 ROS |
| 安全/限位 | assignment 新写 `command_limit`；MIT 指令层 | `CommandFrame` 显式控制模式/KP/KD/前馈；motion 层可做 target expiry；可接同款限位 |
| 测试 | 输入/限位自检、ROS 链路检查、参考实现 | 单元/MuJoCo 集成/三进程 headless 测试；black/blackW 配置测试 |
| 实机 | 上游有 `rl_real` 路径，但这次未接本队实机 | 有三进程/真实后端迁移计划；black 实机 v1 计划在 coverMoon 上游文档里 |
| 维护 | 上次 assignment 的端口，非本任务主线；上游外部 | 团队主控制仓库；`coverMoon` 上游活跃，团队 fork 落后 17 commits |
| 当前风险 | 与本次 Part1/Part2 场景/资产不直接配套；45 维策略需再适配；状态机补丁多 | 团队 fork 落后上游；部分功能（blackW/Wolf/ROS2 多进程）当前不用；CMake 依赖需自己维护 |

## 3. 为什么本次主部署选 quadruped_control

1. **和本次场地/资产直接配套**：Part1/Part2 场景、Black MJCF、MuJoCo backend、GUI 都在同一仓库体系里；P0 已用它打开 Part1 场景并验证 `GetUp → Running → policy switch`。
2. **状态机/策略切换是原生能力**：我们手动保底需要按障碍切策略/限速；`MotionRuntime` 已有 policy switch、姿态过渡、Retry 等，rl_sar 那套是我们 assignment 里临时补的。
3. **策略契约更灵活**：当前 `flat_ft` 45 维、未来 HIM 270 都能用配置表达；rl_sar 的 HIM 输出/观测拼装是硬编码在 assignment 端口里的。
4. **长期可维护**：团队主控制仓库；`coverMoon` 上游有测试、target-expiry 修复、实机计划；相比之下 rl_sar 端口是本任务一次性产物。
5. **可以只使用子集**：当前只编 black 单进程；blackW/Wolf/ROS2 三进程不需要也不影响。

## 4. rl_sar 是否弃用？

**作为主部署栈：暂不用于比赛部署。作为资料和备选：保留。**

保留它的价值：

- `@20261007_assignment/docs/policy-model.md` 是 `best.pt` 的逐层/部署语义参考；
- `@20261007_assignment/docs/porting.md` 记录了 HIM 270、MIT 指令、状态机斜坡、限位和 ROS 2 接口；
- 若实机接口更接近 `rl_real` 或 `quadruped_control` 真实后端短期不可用，可回退到 rl_sar 做对照；
- 它的一些做法（输入边沿、指令限位、仿真时间驱动）可以作为 `quadruped_control` 的测试/设计参照，但不要直接复制两套代码。

不维护的理由：

- 两套 C++ 部署同时改会重复验证、分散时间；
- 本次 P0/P1 的策略/场景/评测都围绕 `quadruped_control` + 本任务 MJCF；
- 训练仓库输出策略后，只需要部署到主栈；rl_sar 作为对照/回退即可。

## 5. 当前决定

- **主栈：`quadruped_control` 个人 fork**；P0 commit `f2b37dc` 已推送。
- **rl_sar：归档为参考/备选**，不删除 `@20261007_assignment`；不在 P1 并行维护。
- **控制仓库上游**：`coverMoon` 比团队 fork 领先 17 commits；P1 训练不依赖它，P1 baseline 稳定后做一次受控 rebase（见 `quadruped-control-study.md` §1.1）。
- 若出现以下情况再重新评估：实机接口只支持 rl_sar 的 `rl_real`；quadruped_control 真实后端无法按期接入；需要把 rl_sar 作为比赛前短期保底。
