# `quadruped_control` 研读与接入方案（2026-10-22）

> 来源：只读仓库 `ReadOnly.d/quadruped_control`（commit `e0fb567`，101 MB，含 .git）；本地工作副本在 `prep.d/quadruped_control_local`（不入库，和只读源分离，便于按需修改）。本文记架构、可借鉴点、接入方式与风险，不复制第三方代码进任务仓库。

## 1. 架构结论

- 单仓库包含：`core/`（数据结构/RobotIO）、`motion/`（MotionRuntime、状态机、RL）、`policy/torch`（TorchScript）、`backends/mujoco`、`adapters/ipc`/`ros2`、`config_loader/`、`apps/`。
- 正式运行三进程：`ros2_gateway` → `motiond` → `mujoco_backendd`，通过本机 IPC；`apps/mujoco_sim` 是**单进程调试入口**，最适合 P0 本地手动验证。
- MotionRuntime 稳定状态：`Passive → GetUp → Stand → Running`；`Running` 下由 `behavior_name` 区分 `rl_locomotion/retry/event_chain/bridge_drive/low_bar_drive/car_drive`。
- 控制周期 5 ms（200 Hz），策略 50 Hz（每 4 周期推理一次）；命令为 `BaseCommand` 的 `(vx,vy,wz)`；`CommandFrame` 显式携带控制模式、目标、KP/KD、前馈。
- black 的现有 flat/obstacle 策略是 **6 帧历史 → 270 维输入**；我们的 `flat-ft-2500` 是 **45 维单帧**。控制仓库的 `rl_controller.cpp` 支持 `history_frames` 非空、`inference_input_dimension = observation_dimension × history_count`，所以单帧策略可以合法接入（`history_frames: [0]`）。

## 2. 可借鉴点

- **RobotIO 抽象**：MuJoCo、replay、实机共用一套运动层；我们的本地 eval 也应保持“策略层不直接依赖 MuJoCo”。
- **状态机与策略切换**：`MotionRuntime` 处理起立/站姿/姿态过渡/策略重置；切换策略时重置历史和旧动作，姿态差异大时先过渡，适合手动状态机。
- **显式 CommandFrame**：每个关节带控制模式和 KP/KD，便于 safety/限幅；比“直接下发 q_target”更可审计。
- **配置分层**：`configs/robots`（关节顺序/限制）、`controllers`（周期/站姿/固定增益）、`policies`（输入/动作/默认姿态）、`behaviors`（retry/event/fixed drive）、`simulation`、`input/gamepads`。
- **blackW 的 bridge/low_bar/car fixed drive**：证明“按障碍切换行为/固定动作”在控制层已有先例；black 目前只有 flat/obstacle 策略，Event chain 为空。
- **测试**：单元、MuJoCo 集成、三进程 headless 测试；本地接入应复用单进程测试路径。

## 3. 本地工作副本中已做的接入

位置：`prep.d/quadruped_control_local`（不入库）。

- 复制 `@20261019_locomotion/assets/policies/flat-ft-2500/policy.pt` → `assets/policies/black/flat_ft/policy.pt`。
- 新增 `configs/policies/black/flat_ft.yaml`：
  - `observation_dimension: 45`、`history_frames: [0]`、`inference_input_dimension: 45`；
  - 默认关节姿态/`kp=40`/`kd=1.2`/`action_scale=0.25` 与训练契约一致；
  - 策略顺序 FL/FR/RL/RR。
- `configs/policies/black/policy_switch.yaml` 改为循环 `[flat_ft, obstacle]`，用于先验证加载/切换路径（**未编译/未跑**；远程机已关机）。

## 4. 手动状态机接入方案

现有 `policy_switch` 只支持“循环切换”且 black 只有 flat/obstacle。P0 保底建议：

1. **不改 MotionRuntime 核心**：先把状态机放在输入/应用层（`apps/mujoco_sim` 或 gateway）。
2. 每个状态对应一个**具名策略**；`SwitchPolicy` 已支持 `policy_name`（非 toggle）在 `motion_requests.cpp:547` 附近。
3. 增加输入映射：键盘/手柄的 D-pad 或功能键选择 `flat_ft/loose/bridge/stairs/high_wall/limit_bar/slope/slalom`；状态切换调用 `SwitchPolicy(state)`，速度指令仍由摇杆给。
4. 初始阶段所有状态可先指向 `flat_ft`（临时共用），bridge/bands、limit_bar 等再逐步替换成专项策略。
5. 不把 judge/真值放进 MotionRuntime；judge 只做外部计分，状态切换由操作手触发。

需要修改的最小集合（P0）：

- `apps/mujoco_sim/sim_input.hpp`：新增 `policy_name` 或 `state_index`；
- `apps/mujoco_sim/terminal_input.cpp` / `sim_window` / gamepad 输入：状态键映射；
- `sim_controller.cpp`：`SwitchPolicy` 请求携带具名 policy；
- `configs/policies/black/policy_switch.yaml`：策略注册顺序；
- 新增各状态 policy YAML（先用 flat_ft 占位）。

不建议 P0 改 `MotionRuntime` 核心状态机；保留 Passive/GetUp/Stand/RL，状态层只做“选择哪个 RL 策略”。

## 5. 风险与未验证项

- 本地副本未编译：`quadruped_control` 需要系统 MuJoCo/LibTorch/ROS 依赖；远程机关机，P0 只做了配置级接入。
- 单帧 45 维策略与现有 270 维策略共用 `policy_switch` 时，切换会重置历史；单帧策略历史长度 1，需确认 C++ loader 的 `history_frame_count` 上限/下限实现（`rl_controller.cpp` 已支持非空 history，但要在编译后跑一帧验证）。
- `posture_transition_cycles`、默认姿态差异、旧动作清理需实测；不能只看 YAML。
- black 没有 blackW 的 wheel fixed drive；Part 1 木桥/限高不能直接复用 blackW 的 bridge/low_bar drive。
- 世界坐标/速度真值不能进 actor；控制层只用摇杆速度指令与状态切换。

## 6. 参考代码位置

- `motion/src/motion_runtime.cpp`（状态/行为/策略切换）
- `motion/src/motion_requests.cpp`（`dispatch_switch_policy`）
- `motion/src/rl_controller.cpp`（45/270 输入、history、动作转换）
- `configs/policies/black/flat.yaml` / `obstacle.yaml`
- `configs/policies/black/policy_switch.yaml`
- `apps/mujoco_sim/`（单进程调试入口）
- `docs/architecture.md`、`docs/robot_models_and_behaviors.md`、`configs/input/gamepads.yaml`
