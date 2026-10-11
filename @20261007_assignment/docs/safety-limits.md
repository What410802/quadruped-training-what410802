# 限位与安全：哪一层挡什么，Sim2Real 还缺什么

起因是 2026-10-11 的两个问题："电机动作的限位在哪些文件"、"Sim2Real 的安全保障够不够"。
先把结论放前面：**本任务这条链路里真正生效的力矩限位只有仿真侧的两道（电机模型 ±20 N·m、MJCF `ctrlrange` ±20）**；
策略侧三处看起来像保护的东西（`TorqueProtect`、`output_dof_tau` 的 ±33.5 裁剪、`clip_actions` ±100）**一个都不生效**；
关节限位是 MuJoCo 的**软**约束，实测在"躺着/起身"阶段会被压过约 82 mrad（**RL 行走阶段不越界**）；
指令断流的兜底（仿真侧看门狗）实测也是坏的。要接实机，至少得补 §3 的前三条。

## 1 一条指令的路径

```
策略 action ──ComputeOutput()──▶ output_dof_pos / _vel / _tau ──FSM 填 motor_command{q,w,kp,kd,tau}──▶ /mit_command
                                                                                                          │
                          sim_node：电机模型 Torque() ──▶ d->ctrl[i] ──▶ mj_step（MuJoCo 再夹 ctrlrange）──▶ 关节力矩 / 接触力
```

| 层 | 限位 | 位置 | 生效？ | 说明 |
|---|---|---|---|---|
| 策略动作 | `clip_actions_lower/upper = ±100` | [`himloco/config.yaml`](../ws/src/rl_sar/policy/black/himloco/config.yaml) 的 `clip_actions_*` → `rl_sdk.cpp:411-413` | ❌ 形同虚设 | 100 × `action_scale` 0.25 = ±25 rad 的关节偏移，等于没夹 |
| 策略力矩（前馈 τ） | `clamp(output_dof_tau, ±torque_limits)` = **±33.5 N·m** | `library/core/rl_sdk/rl_sdk.cpp:175`（`torque_limits` 见 `himloco/config.yaml`、`base.yaml`） | ❌ **不生效** | RL 状态里 `motor_command.tau = 0`（[`policy/black/fsm.hpp`](../ws/src/rl_sar/policy/black/fsm.hpp) 的 RL `Run()`）；这个 τ 只进 CSV 与一个没人 pop 的队列（P1-b） |
| 真正产生力矩的 PD 项 | **无** | `fsm.hpp` 只填 `kp = rl_kp`(40)、`kd = rl_kd`(1.2)、`q = output_dof_pos` | — | τ = `kp·(q_des − q) + kd·(0 − dq)`，完全靠下游限幅 |
| **控制器侧（本轮新增）** | 5 条：增益上限、`dq_des` 上限、`q_des` **变化率**上限、可选绝对窗口、**蕴含力矩预算**（`tau_ff` + `kp·|q_des−q|` + `kd·|dq_des−dq| ≤ tau_limit`） | [`command_limit.hpp`](../ws/src/rl_sar/include/command_limit.hpp)，在 [`SetCommand()`](../ws/src/rl_sar/src/rl_sim.cpp) 里对**下发的 MIT 指令**生效 | ✅ **已实施（S5-1）** | 见 §3；默认 `command_tau_limit=33.5`、`command_slew=60 rad/s`，都是"病态指令网"而不是步态整形 |
| 仿真电机模型 | `clamp(τ, ±tau_max)`，默认 **20 N·m**（`tau_max` 是 `sim_node` 参数） | [`motor.hpp`](../../@20261005_ros2/ws/src/quadruped_ros2/include/quadruped_ros2/motor.hpp) 的 `Torque()`、`kDefaultTauMax` | ✅ | 每步累计 `sat`（撞限幅的电机·步），非理想电机时退出打印 |
| 仿真模型（MuJoCo） | `<motor ctrllimited="true" ctrlrange="-20 20">` | [`black_description.xml`](../../@20261005_ros2/models/black_description.xml) 的 12 个 `<motor>` | ✅ | 第二道 ±20（与上面同值，重复保护） |
| 关节角 | `limited="true" range=…`（hip ±0.5、thigh −1.6…1.2、calf 0.85…2.5 一侧） | 同上的 12 个 `<joint>` | ⚠ **软约束** | MuJoCo 的 `jnt_range` 是约束力、不是硬挡：力矩够大就能压过去，之后按 `solref/solimp` 顶回来 |
| 关节角速度 / 加速度 / 加加速度 | 无 | — | ❌ | 模型里 `damping="0" frictionloss="0"`、没有 `armature`；MuJoCo 也不限制关节速度 |
| 指令断流（安全兜底） | 设计：100 步 = 200 ms 仿真时间 → 纯阻尼（`damp_kd = 0.5`） | `sim_node.cpp` 的看门狗与 `DampingCommand()` | ❌ **实测不生效** | `got` 每步为真、`last_cmd_step` 每步被刷新，见 [`control-stack-rates.md`](control-stack-rates.md) §4 |
| 姿态保护 | `AttitudeProtect(quaternion, pitch/roll 阈值)` | `library/core/rl_sdk/rl_sdk.cpp` 已实现 | ❌ 没人调用 | 上游与主办方都没接 |
| 力矩保护 | `TorqueProtect()` | `library/core/rl_sdk/rl_sdk.cpp:195-228` | ❌ **空转** | 函数体注释原文 "Just a reminder, no protection"；上游 `rl_sim.cpp` 与 5 个 `rl_real_*.cpp` 的调用点**全是注释掉的** |
| 手柄速度指令 | `joy_command_scale = 1.5`（摇杆满偏 = 1.5 m/s、1.5 rad/s） | [`launch/rl_sim.launch.py`](../ws/src/rl_sar/launch/rl_sim.launch.py) 参数 | 配置项 | 是"指令尺度"，不是安全限位 |

被我们替换掉的 `controller_node`（上一任务）**同样没有限位**（它只把 `tau` 与 PD 增益透传出去），所以"限位都在仿真侧"是这条链路一贯的结构，不是这次移植引入的。

## 2 实测（2026-10-11，`check_limits.py`）

命令：起仿真 + `rl_sim`，再发一遍键位序列（起身 → 进 RL → 走 → 转身 → 趴下），同时另开一个终端跑
`pixi run python @20261007_assignment/scripts/agent_scripts/check_limits.py --seconds 22`。

| 量 | 结果 |
|---|---|
| 实测力矩 \|τ\| | **标准行走（`check_walk.py`）：峰值 19.19 N·m、撞限幅 0 次**（仿真侧自报，193452 电机·步，`--sim-param motor_deadzone:=0.001` 打开统计）；含 `/sim_reset`（`RB+Y`）的键位序列里才会贴到 20.00（0.20% 采样）——**那 0.2% 来自复位瞬间的姿态跳变**，不是行走本身 |
| 关节角越界 | **RL 阶段（kp=40）：0 个采样越界** ✓；斜坡/被动阶段（kp=80 或 kp=0 的阻尼）：hip 越 6 mrad、thigh 越 1 mrad、**calf 越 82 mrad**，约占该阶段采样的一半 |
| 关节角速度 | 峰值 **11.6 rad/s**（模型不限速度，只有限位软约束 + 电机力矩在挡） |

两条解读：

1. **RL 行走阶段不越关节限位**——我们要交付的那条路径在机械范围内 ✓（calf 的越界发生在"趴着/起身/趴下"这些**被动或斜坡**阶段：那时 kp=0（纯阻尼）或 kp=80 追一个大目标，腿靠自重压过软限位 ✓）。真机上这表现为"腿软着顶到机械限位"，靠驱动器的电流限幅兜着，不暴力但不好看，也不该由策略负责。
2. **|τ| 峰值 19.19 N·m、行走期间 0 次撞限幅**——策略按 ±33.5 训练、我们在仿真里给 ±20（差 40%），但实测标准行走根本碰不到这道线 ✓；唯一打到 20.00 的是 `/sim_reset` 那一刻（关节姿态被瞬间改写 → PD 误差巨大 → 力矩顶到限幅，约 200 ms）。这也解释了 [`experiments.md`](experiments.md) §2 里"1.5 m/s 以内峰值不超过 20"的口径。

## 3 我们这层已实施：控制器侧指令限位（S5-1，2026-10-11）

`rl_sim` 不直接下发力矩，所以限位只能加在**我们真正下发的 MIT 指令**上。关键等式是
`τ = tau_ff + kp·(q_des − q) + kd·(dq_des − dq)`，而 `q/dq` 我们每条 `/motor_state` 都有——
于是"限制力矩"等价于"在测得的状态上给位置误差做预算"。实现是纯函数 [`command_limit.hpp`](../ws/src/rl_sar/include/command_limit.hpp)（可单测），在 [`SetCommand()`](../ws/src/rl_sar/src/rl_sim.cpp) 里对每条指令生效，五条规则按顺序：

| 规则 | 作用 | 默认 |
|---|---|---|
| ① 增益上限 | `kp ≤ kp_max`、`kd ≤ kd_max`（且非负） | 80 / 10（本移植用过的最大增益） |
| ② `dq_des` 上限 | 目标速度别乱来 | ±20 rad/s |
| ③ `q_des` 变化率 | `\|q_des − q_des_prev\| ≤ slew·dt`：把阶跃抹成斜坡 | 60 rad/s（= 每推理周期 1.2 rad，只抓"跳变"） |
| ④ 绝对窗口（可选） | 若 yaml 给了 `q_lower/q_upper` 就夹进机械范围 | 默认不启用（模型侧限位见 §4） |
| ⑤ **蕴含力矩预算** | `\|tau_ff\| + kp·\|q_des − q\| + kd·\|dq_des − dq\| ≤ tau_limit`；没预算时退化成"目标 = 实测位置 + 纯阻尼" | 33.5 N·m（= 训练时的包络） |

**它保证什么、不保证什么**（写进头文件了）：保证"按测得状态算出来的力矩不超过 `tau_limit`"——这正是驱动器下一个控制周期会算的量；不保证"关节跟不上时误差继续变大"（那一项由规则 ③ 限速，每周期最多 `kp·slew·dt ≈ 4 N·m`，所以 `slew` 不该随手调大）。

**校准是有代价的，实测记录在这里**（同一条键位序列，30 s）：

| 参数 | 限幅事件 | 后果 |
|---|---|---|
| `tau=20`（= 模型自己的限幅）+ `slew=20` | **108** 次（九成是 slew） | 策略输出被改写：`check_walk` 的"策略周期"代理指标从 20.00 ms 掉到 14.92 ms（目标每周期都在动），说明**在 20 N·m 上游夹会扭曲步态** |
| `tau=33.5`（训练包络）+ `slew=60` | **22** 次，集中在 FSM 切换瞬间 | `check_walk` 恢复 7/7、策略周期精确 20.00 ms；只在病态指令时才咬 |
| 演示：`tau=2`（故意压死） | **1351** 次 | 机制有效（目标被压到贴着实测位置），但也能看出来"夹太紧就不是那条策略了" |

**为什么不在 20 N·m 上游夹**：模型的 ±20 是**力矩**限幅，不改指令；我们在上游夹会改 `q_des`，等于替策略做决定。所以分工是：**我们这层挡"病态指令"（训练包络之外），模型/驱动器那层挡"瞬时力矩"**。

**可见性**：每次限幅计数，最多每秒打一条 `WARNING command limited (events N): slew=… torque=…`；`status_period_ms > 0` 时状态行也带 `cmd_limit_events:N`。自检：[`test/command_limit_selftest.cpp`](../ws/src/rl_sar/test/command_limit_selftest.cpp)（27 项，`ros2 run rl_sar command_limit_selftest` 或 `colcon test`）。

## 4 模型侧限位：现在哪些是 YAML 参数、哪些是硬编码

按"先记文档"处理（本轮不改模型侧）。要调的话从这里入手：

| 限位 | 现在的位置 | 性质 |
|---|---|---|
| `tau_max` = 20 N·m | `sim_node` 的 ROS 参数（`-p tau_max:=…`） | ✅ 已经是 YAML/命令行可调的 |
| `damp_kd` = 0.5、`command_timeout_ms` = 200 | 同上的 ROS 参数 | ✅ 可调 |
| 电机模型非理想项（`motor_deadzone`/`motor_delay_cycles`/`motor_noise`/`motor_seed`） | 同上的 ROS 参数 | ✅ 可调（自检用） |
| `<motor ctrllimited ctrlrange="-20 20">` | [`black_description.xml`](../../@20261005_ros2/models/black_description.xml) **硬编码** | ⚠ 想让它跟 `tau_max` 联动就得改模型生成/加载路径（未做） |
| 关节 `limited="true" range=…`（12 个） | 同文件**硬编码** | ⚠ 同上；这是"机械限位"的唯一来源，也是 §3 规则 ④ 的窗口来源 |
| `damping` / `frictionloss` / `armature` | 同文件（现在是 0） | ⚠ 与真机的被动特性有关，未标定 |

## 5 Sim2Real 差距清单（按风险排序）

| # | 差距 | 风险 | 建议 |
|---|---|---|---|
| 1 | ~~没有一层限制真正下发的力矩~~ | ~~高~~ | ✅ **已实施（S5-1，见 §3）**：`SetCommand()` 里对 MIT 指令做五条钳位（含蕴含力矩预算）。**仍未做**：把 `q_des` 夹到机械范围（需要模型侧 `range` 进 yaml，见 §4 规则 ④） |
| 2 | **断流没有兜底**（仿真看门狗坏 + rl_sim 在反馈断后一步不跑） | 高 | S5 的墙钟 deadman（反馈断 > N ms → 主动发阻尼 + WARN）；顺手修 `sim_node` 那 1 行看门狗 |
| 3 | **关节限位是软的**：仿真里腿能压过 82 mrad，而真机是硬机械挡 | 中 | 二选一：把 MJCF 的 `solref` 调硬（`solref="0.005 1"` 量级）让仿真更接近硬挡；或在实机侧把 `q_des` 先夹到 `range` 内（配合第 1 条） |
| 4 | **`TorqueProtect` / `AttitudeProtect` 是死代码**（core 里实现了、没人调用） | 中 | 要么接上（`TorqueProtect` 本体也只打印，得先改成真的动作），要么在 `porting.md` §2 明确写"不启用，理由 X"，别让它继续像保护 |
| 5 | **`clip_actions = ±100`** 等于没夹 | 低 | 改成有意义的范围（例如 ±3~±5，按 `action_scale` 反推），保留"策略疯了也不会给 ±25 rad 目标"这层意思 |
| 6 | **速度/加速度无限制**（dq 峰值 11.6 rad/s） | 低 | 模型加 `armature`/`damping` 更贴近真机；指令侧加 slew 之后自然缓解 |
| 7 | 急停 / 使能 / 失能流程 | 中 | 本任务范围外（实机侧要接主办方的 `robot_joint_controller`），但交付文档里要写明"我们这层没有急停" |

## 6 复核命令

```bash
# ① 量限位余量（跑狗的时候另开一个终端；数据来自 /motor_state 的实测 τ 与 q，MJCF 的 range 自动读）
pixi run ros2 run quadruped_ros2 sim_node --ros-args -p viewer:=false -p realtime:=true -p start:=rest &
pixi run ros2 run rl_sar rl_sim &
pixi run python /tmp/kb_test.py &                 # 或自己拿手柄操作
pixi run python @20261007_assignment/scripts/agent_scripts/check_limits.py --seconds 22

# ② 看电机模型的撞限幅统计（非理想参数任一项非 0 时，退出会打印 sat 比例）
pixi run python @20261007_assignment/scripts/agent_scripts/check_walk.py \
    --sim-param motor_deadzone:=0.001            # 用极小的死区把"打印统计"这条路打开，行为等价理想

# ③ 关节限位相关的模型定义
grep -nE "<joint|<motor" @20261005_ros2/models/black_description.xml
```
