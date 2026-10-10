# 大作业：移植 rl_sar，用强化学习策略让仿真里的狗走起来

> 任务书：`大作业要求.md`（本机只读材料）。要求是修改开源的 rl_sar（一个"控制器节点"），让它替换上次写的控制器节点，用主办方给的 `best.pt` 策略让上次的仿真节点里的狗走起来；验收时要能讲清楚是怎么做的。
>
> 目录（TOC）：[做了什么](#做了什么) · [怎么跑](#怎么跑) · [目录](#目录与文件) · [文档](#文档) · [来源与许可](#来源与许可)
>
> **推进情况**（做到哪、待决事项、下一步）在 [`docs/status.md`](docs/status.md)——本 README 只做入口，不记进度（[`../docs/conventions.md`](../docs/conventions.md) §2.6）。

## 做了什么

| 要求 | 实现 | 入口 |
|---|---|---|
| 移植 rl_sar，替换控制器节点 | 包 `rl_sar`：框架层（`library/core`）逐字复制上游，只改写与仿真节点对接的 `rl_sim.cpp`，新写 black 的配置与状态机 | [`ws/src/rl_sar/`](ws/src/rl_sar/)、[`docs/porting.md`](docs/porting.md) |
| 适配上次的仿真节点 | **仿真节点与手柄节点一行没改**：rl_sim 订阅 `/motor_state` + `/imu`、发 `/mit_command`，和上次的 controller_node 同一套接口 | [`docs/porting.md`](docs/porting.md) §4 |
| 按给定的观测 / 动作定义跑 `best.pt` | 45 维观测 × 6 帧历史 → 12 维动作 × 0.25 + 站姿；`joint_mapping` 处理两边的腿序差异 | [`docs/porting.md`](docs/porting.md) §3、§5 |
| 让狗走起来 | 起身 → 进 RL → 前进 / 横移 / 转向 → 趴下，无头自检 7 项通过 | [`scripts/agent_scripts/check_walk.py`](scripts/agent_scripts/check_walk.py) |
| 讲清楚怎么做的 | 另写了一份**不经 ROS 的参考实现**做对照，用实验量了 rl_sar 时钟与线程问题的影响；`best.pt` 的内部结构单独一篇 | [`docs/experiments.md`](docs/experiments.md)、[`docs/policy-model.md`](docs/policy-model.md) |

数据流（与上次相比只换了中间那个节点；带图的版本见 [`docs/porting.md`](docs/porting.md) §1）：`joy_node` →`/joy`→ **`rl_sim`** →`/mit_command`→ `sim_node` →`/motor_state` + `/imu`→ **`rl_sim`**。

## 环境与依赖

- 仍是仓库根 [`pixi.toml`](../pixi.toml) 的同一个环境。本任务新增 `libtorch`（C++ 推理）、`tbb-devel`（rl_sar 的线程间队列）、`pytorch`（只给参考实现用），都锁 CPU 的 generic 构建；为什么这样锁、带来的副作用见 [`../docs/pitfalls/environment.md`](../docs/pitfalls/environment.md)「libtorch / pytorch」一节。
- 依赖上次任务的 ROS 2 包 `quadruped_ros2`（消息定义 + sim_node + joy_node），在 [`../@20261005_ros2/ws/`](../@20261005_ros2/README.md)。`pixi run ros2-build` 会把两个工作空间都编了。
- 手柄的一次性权限配置与上次相同：[`../@20261005_ros2/scripts/setup_joy_devices.sh`](../@20261005_ros2/scripts/setup_joy_devices.sh)。

## 怎么跑

进入仓库根目录，执行：

```bash
pixi install                                                # 首次：装环境
pixi run ros2-build                                         # 编译所有 colcon 工作空间（含上次 quadruped_ros2 与本次 rl_sar）
pixi run ros2 launch rl_sar rl_sim.launch.py                # 仿真窗口 + 手柄节点 + rl_sim
pixi run ros2 launch rl_sar rl_sim.launch.py start:=rest    # 从趴卧姿态开始（更像实机上电）

pixi run python @20261007_assignment/scripts/agent_scripts/check_walk.py    # 自检（约 35 s）
pixi run python -I @20261007_assignment/scripts/agent_scripts/policy_reference.py --cmd 1.0,0,0    # 参考实现
```

> *对应传统 ROS 2 方式（传统指不用 `pixi run` 与仓库的辅助脚本）*：按 [仓库级 `README.md` 传统 ROS 2 方式](../README.md#如果你坚持用传统-ros-2-方式) 安装并激活环境，然后进仓库根执行：
>
> ```bash
> # （本包的消息 + 仿真节点 + 手柄节点依赖上次任务的 quadruped_ros2，需先构建它、source 它，再构建本包）
> cd @20261005_ros2/ws && colcon build --symlink-install && cd ../..
> source @20261005_ros2/ws/install/setup.bash    # zsh 用 setup.zsh，下同
> cd @20261007_assignment/ws && colcon build --symlink-install && cd ../..
> source @20261007_assignment/ws/install/setup.bash
> ros2 launch rl_sar rl_sim.launch.py            # 其余命令同上，去掉 pixi run 即可
> python @20261007_assignment/scripts/agent_scripts/check_walk.py
> ```
> 
> 以后新开终端只需激活环境，再 source 这两个 `install/setup.bash`（顺序同上）。这套命令 2026-10-08 在 `env -i` 的干净 shell 里从零跑过，自检 7 项全过。

**手柄操作**：A = 起身（约 3 s）→ 站稳后 **RB + 十字键上** = 进 RL → 左摇杆前后 / 左右走、右摇杆转向（满偏 1.5 m/s 或 rad/s）→ B = 趴下；LB + X = 立刻阻尼，RB + Y = 复位仿真。实体手柄与上次的仿真手柄（`@20261005_ros2/sim_joy/xbox_sim_joy.py`）都能用；`/joy` 的轴与正负号约定见 [`../@20261005_ros2/docs/joystick.md`](../@20261005_ros2/docs/joystick.md) §3。

**调参（改 yaml，不用重编）**：`ws/src/rl_sar/policy/black/base.yaml` 有四个「部署旋钮」——`kd_passive`（Passive 状态的阻尼，默认 8.0）、`getup_pre_cycles: 200` / `getup_cycles: 400` / `getdown_cycles: 500`（三段斜坡的控制周期数，5 ms/周期 → 1.0 / 2.0 / 2.5 s）；**它只在节点构造时读一次，改完要重启**。策略级的 `himloco/config.yaml`（`rl_kp`/`rl_kd`/`action_scale` 等）**每次进 RL 都会重新读**，所以改完趴下再起身重进 RL 即生效（代价是切入那一刻会跳一下，别改 `joint_mapping`/`num_of_dofs` 这类会错位的项）。两份 yaml 有 7 个同名字段、必须一致，不一致时节点会在启动和每次进 RL 时打 `[WARNING] [yaml] …`，而不是默默变样（[`docs/porting.md`](docs/porting.md) §3、[`../docs/learn/rl-sar.md`](../docs/learn/rl-sar.md) §3）。

**状态行**：rl_sim 的 `RL Controller x:… y:… yaw:…` 由 ROS 参数 `status_period_ms` 控制（默认 0 = 不打；`pixi run ros2 run rl_sar rl_sim --ros-args -p status_period_ms:=500` = 每 0.5 s 一行，原来是不管多快都每 5 ms 打一次）。仿真节点自己的状态行由它的 `status_period_s` 控制。

**键盘操作**：rl_sim 直接读终端，要单独占一个终端：`pixi run ros2 launch rl_sar rl_sim.launch.py rl:=false joy:=false`，另一个终端 `pixi run ros2 run rl_sar rl_sim`，然后按 `0` 起身、`1` 进 RL、`W/S` `A/D` `Q/E` 加减速度、空格清零、`9` 趴下、`P` 阻尼、`R` 复位。

> **不要用 `realtime:=false`**：rl_sim 按墙钟每 20 ms 推理一次，仿真跑得比真实时间快 3 倍以上狗就会摔（[`docs/experiments.md`](docs/experiments.md) §5）。

## 目录与文件

```text
@20261007_assignment/
├── README.md                     # 本文件（入口）
├── docs/
│   ├── porting.md                # 生态位、改了哪些文件、接口对照、观测/动作怎么算、手柄与状态转移图、上游的不足
│   ├── policy-model.md           # best.pt 内部：estimator + actor 的逐层结构与参数量、怎么被调用、三条实测坑
│   ├── experiments.md            # 策略能不能走、时钟与线程问题严不严重（含复现命令与数字）
│   └── status.md                 # 推进情况、已定决策、决定与计划（P1/P2/P3）、实施顺序 S1–S6、提交建议
├── ws/src/rl_sar/                # colcon 包（Apache-2.0，来自 fan-ziqi/rl_sar e5c2f41）
│   ├── library/core/             # 框架层（纯复制）：rl_sdk / observation_buffer / fsm_core / loop
│   ├── include/rl_sim.hpp        # 适配层（改写）
│   ├── src/rl_sim.cpp            #   同上。入 /motor_state /imu /joy，出 /mit_command
│   ├── policy/fsm.hpp            # 状态机注册表（只注册 black）
│   ├── policy/black/             # base.yaml（机器人参数）、fsm.hpp（状态机）、knobs.hpp（部署旋钮 + yaml 自检）、himloco/{config.yaml,best.pt}
│   ├── launch/rl_sim.launch.py   # sim_node + joy_node + rl_sim
│   ├── CMakeLists.txt  package.xml  LICENSE
│   └── .clang-format             # DisableFormat：不重排上游代码
├── scripts/agent_scripts/
│   ├── check_walk.py             # 无头自检（ROS 链路）
│   └── policy_reference.py       # 参考实现（不经 ROS、锁步，可注入时序误差）
└── output/log/                   # 自检日志（不入库）
```

## 文档

| 文档 | 内容 |
|---|---|
| [`docs/porting.md`](docs/porting.md) | rl_sar 替换的是哪一层、逐文件改动与上游对照命令、配置字段来源、话题与 QoS 对照、一帧观测/动作的算法（带代码行号）、手柄符号、**状态转移图**与键位出处、上游不足的处理 |
| [`docs/policy-model.md`](docs/policy-model.md) | `best.pt` 里是什么：HIMLoco 的 `estimator`（270 → 19）+ `actor`（64 → 12）、243231 个参数、与两份 yaml 的对应、部署时容易踩的三处（含实测），以及文件里看不出来的那部分 |
| [`docs/experiments.md`](docs/experiments.md) | 策略在我们模型上的速度跟踪与力矩、ROS 链路实测的策略周期、时序误差注入、暂停/慢放/快放的边界、5 分钟浸泡测试、结论表 |
| [`docs/status.md`](docs/status.md) | 推进情况：阶段状态、已定决策、待人工确认、决定与计划（P1/P2/P3，调研细节在仓库级学习文档里）、实施顺序 S1–S6、提交建议 |
| [`../../docs/learn/rl-sar.md`](../docs/learn/rl-sar.md) | **仓库级**（不属于本任务）：rl_sar 与主办方代码的内部机制速查——本任务的调研结论沉淀在这里，`status.md` 只留决定 |

## 来源与许可

- **rl_sar**：<https://github.com/fan-ziqi/rl_sar> commit `e5c2f41`（2025-07-25），Apache-2.0，许可证原文在 [`ws/src/rl_sar/LICENSE`](ws/src/rl_sar/LICENSE)。改过的文件在文件头注明了改动；逐文件清单与对照命令见 [`docs/porting.md`](docs/porting.md) §2。
- **`best.pt` 与策略参数**：大作业附件（`best.pt`、`config.yaml`）。附件没给的几个字段取自主办方的 rl_sar 分支（本机只读材料 `rl_sar-black-W`，同为 Apache-2.0），逐项来源见 [`docs/porting.md`](docs/porting.md) §3。
- **仿真节点、手柄节点、模型**：上次任务 [`../@20261005_ros2/`](../@20261005_ros2/README.md)。

**AI 参与边界**：配置与诊断本地环境、研究 rl_sar 内部原理、Agent 测试脚本、rl_sar 本身潜在问题实验，以及键位检查、文档工作等杂项。培训者初步编写 rl_sar 移植代码，协作进行改进并进行最后验收。[`docs/porting.md`](docs/porting.md) 记录改动。
