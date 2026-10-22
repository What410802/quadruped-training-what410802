# 电机模型与 MuJoCo 窗口：与上次 assignment 的对齐情况

> 问题：`quadruped_control` 的电机模型和上次 task 是否一致；上次自写的高效 C++ 窗口能否接进来。

## 1. 结论

- **理想 MIT 力矩公式一致**：两套都是关节侧 `τ = τ_ff + kp·(q_des−q) + kd·(dq_des−dq)`，都写 MuJoCo `data.ctrl`，执行器都是 `<motor gear="1">`，物理步长都是 2 ms。
- **但完整电机模型没有对齐**：`quadruped_control` 目前是纯理想 PD/effort；上次 assignment 的 `sim_node` 有可选的非理想电机模型（死区/延迟/噪声），默认全关时才等价于理想。
- **模型参数也不同**：torque 限幅、trunk 初始高度、关节默认 damping/armature/frictionloss 不完全相同；不能假设“同一个 Black 模型”。
- **高效窗口可以复用，但不是 drop-in**：上次窗口是 `@20261005_ros2/ws/src/quadruped_ros2/include/quadruped_ros2/viewer.hpp`（GLFW + `mjv`/`mjr` 自建窗口）；`quadruped_control` 现在用官方 Simulate 源码。需要把 `apps/mujoco_sim` 的窗口层替换成 `viewer.hpp`，或走 ROS 桥接，不能直接换二进制。

## 2. 电机模型逐项对比

| 项 | 上次 assignment `sim_node` | `quadruped_control` 当前 |
|---|---|---|
| 理想公式 | `tau_ff + kp*(q_des-q) + kd*(w_des-dq)`，clamp | 同公式，`compute_joint_effort()` |
| 指令接口 | `/mit_command` 的 12×MIT 五参数 | `CommandFrame` 显式 ControlMode + target/KP/KD/feedforward |
| 执行器 | MuJoCo `<motor gear="1">`，`data.ctrl` 力矩 | 同 |
| 物理步长 | 0.002 s | 0.002 s |
| 控制周期 | 仿真节点物理 500 Hz；控制器 5 ms（200 Hz） | MotionRuntime 5 ms（200 Hz）；策略 50 Hz |
| 力矩限幅 | 默认 ±20 N·m（模型 ctrlrange），可参数覆盖 `tau_max` | RobotModel max_effort：hip/thigh 23.7、calf 59.25；MJCF ctrlrange 当前为 23.7/59.25 |
| 非理想项 | 死区/延迟/噪声，默认 0/0/0，可开启 | **没有**（当前只有理想 PD/effort） |
| 关节默认参数 | 关节 damping=0、frictionloss=0 | MJCF default damping=0.1、armature=0.01、frictionloss=0.2 |
| trunk 初始 z | 0.57858 m | 0.5 m |
| 传感器 | imu_quat/gyro/acc（site） | 同三项（site） |
| 反馈 `tau` | `data.actuator_force` | 控制层直接用 CommandFrame，不依赖反馈 tau |

结论分三档：

1. **纯理想、默认参数全关**：公式/执行器/步长一致，行为量级可比；但 torque 限幅和模型默认参数仍需统一。
2. **开启非理想项**：`quadruped_control` 没有对应实现，必须移植 `motor::Bank`（死区/延迟/噪声/seed）才可比。
3. **同一 Black MJCF**：两者不是同一模型文件（trunk z、默认阻尼/armature/frictionloss、actuator range 不同），不能直接拿两边数字做 sim2sim 结论。

## 3. 如果要真正对齐

P2/部署前建议新增一个 **legacy-black 验证 profile**，而不是改默认：

1. 使用上次 assignment 的 `black_description.xml`（或复制一份 `black_legacy`）作为控制仓库的验证场景；
2. RobotModel torque limit 设成 20 N·m，保持和上次 `tau_max` 一致；
3. 把 `quadruped_ros2/include/quadruped_ros2/motor.hpp` 的 `JointMotors`/`Bank` 移植到 `backends/mujoco`，作为可选 `motor_nonideal` 配置（默认全关，保持当前理想行为）；
4. 用同一命令序列、同一固定种子对比 `q/dq/tau` 曲线；
5. 再决定竞赛默认用哪套模型；不要在 P1 训练期间改默认。

## 4. 上次高效窗口能否接入

上次窗口：

```text
@20261005_ros2/ws/src/quadruped_ros2/include/quadruped_ros2/viewer.hpp
```

特点：GLFW + `mjv`/`mjr` 自建窗口；单线程、无官方 `Simulate` 的 UI 锁；鼠标负载下比官方窗口稳定（旧文档实测：自建 60 fps，官方在持续鼠标移动时掉帧）。

`quadruped_control` 当前窗口：

```text
apps/mujoco_sim/  ← 基于 MuJoCo 官方 Simulate 源码 + GLFW
```

接入方式：

- **方案 A（推荐，改动中等）**：保留 `MotionRuntime`/`MujocoRobotIO`，把 `apps/mujoco_sim` 的 `sim_window` 层换成 `viewer.hpp`；相机/HUD/按键接到现有 `SimInput`；编一个新 target `quadruped_mujoco_fastview`。这样 GUI 不再依赖官方 `simulate/` 源码。
- **方案 B（改动大）**：三进程模式下把 `mujoco_backendd` 的渲染层改为 `viewer.hpp`；`motiond` 走 IPC，保持控制/渲染分离。
- **方案 C（不推荐用于主栈）**：直接使用上次 `sim_node` + ROS 通信；这更接近 rl_sar 后备栈，不是 `quadruped_control` 的接入。

当前 P1 不切窗口：官方 Simulate 已能跑 Part1 场景和策略切换，P1 先训练；P2 若 GUI 交互/鼠标负载影响演示，再按 A 移植。窗口复用不影响训练/导出。

## 5. 当前决定

- 电机模型：**公式一致、完整模型未对齐**；P1 训练不依赖；P2 前做 `legacy-black` 对齐 profile，默认行为不变。
- 窗口：**可复用但需适配**；P1 继续官方 Simulate，P2 视演示/交互需要迁移 `viewer.hpp`。
- 后备 rl_sar 自带旧 `sim_node` + `viewer.hpp`，如果启用后备，窗口随之上；不需要把两套窗口同时维护。
