# rl_sar 内部机制速查：分层、两份 yaml、三条队列、五套时基

> rl_sar（[fan-ziqi/rl_sar](https://github.com/fan-ziqi/rl_sar)，Apache-2.0）是"让策略跑起来"的框架：订阅关节与 IMU、拼观测、推理、把动作换算成电机指令。本仓只在 [`@20261007_assignment/`](../../@20261007_assignment/README.md) 用它（移植成 ROS 2 节点 `rl_sim`），但下面这些机制、坑与"培训方怎么做的"跟哪次任务无关，所以放仓库级 `docs/learn/`；与那次移植一一对应的文件清单、话题接口、观测/动作算法见该任务的 [`porting.md`](../../@20261007_assignment/docs/porting.md)。
>
> 版本基准：上游 `e5c2f41`（2025-07-25）、主办方分支 `N-W-wolf/rl_sar-black-W`（`cd46b93`，2026-09-14）、主办方自己的控制栈 `quadruped_control`（都是本机只读材料）。本文的 `文件:行` 指的是这三份**上游/主办方代码**；本仓副本（`@20261007_assignment/ws/src/rl_sar/`）与上游的差异逐项记在那份 `porting.md` §2。
>
> 相关：[`tbb.md`](tbb.md)（三条队列用的容器语义）、[`ros2-params-and-launch.md`](ros2-params-and-launch.md)（ROS 参数机制）、[`runtime-timing.md`](runtime-timing.md)（时序与线程方案）。

## 1 分层：框架 / 机器人 / 通信

| 层 | 位置（上游） | 作用 |
|---|---|---|
| 框架 | `library/core/`：`rl_sdk`、`observation_buffer`、`fsm_core`、`loop` | 拼观测、维护 6 帧历史、推理、动作→关节目标、读 yaml、调度状态机、两条墙钟循环 |
| 机器人 | `policy/<robot>/`：`base.yaml`、`fsm.hpp`、`<policy>/config.yaml`、`*.pt` | 这台狗的参数、状态机、策略与其参数 |
| 通信 | `src/rl_sim.cpp`（Gazebo）、`src/rl_real_*.cpp`（实机）等 | `RL` 的子类：实现 `GetState`/`SetCommand`，接各自的通信 |
| 上游独有、我们没拷 | `library/core/matplotlibcpp/`、`library/thirdparty/`（宇树/云深处等 SDK）、`worlds/`、`scripts/` | 见 §7、§8 |

一台机器人可以挂多份策略（上游 `policy/go2/` 下就有 `himloco/` 与 `robot_lab/`），共用一份 `base.yaml`——这是 §3 那份分工的由来。

## 2 键位从哪来：枚举 + 终端解码 + README 参考表

`library/core/rl_sdk/rl_sdk.hpp` 里有两个枚举 `Input::Keyboard`（`rl_sdk.hpp:71-79`）与 `Input::Gamepad`（`:86-93`），上面各有一段 "Recommend:" 注释写推荐键位；键盘侧的**解码**在 `rl_sdk.cpp:286-346` 的 `KeyboardInterface()`（读 stdin：数字、字母、空格、回车、ESC、方向键转义序列），以 0.05 s 一条的 `loop_keyboard` 线程调用；手柄侧由各通信层把 `/joy` 的轴与按钮映射成枚举值。

**上游自带一张参考键位表**：`README.md:197-227`（中文版 `README_CN.md` 同名节）的 `Gamepad and Keyboard Controls`，五组：Basic（A/Num0 起身、B/Num9 趴下、X/N 导航模式）、Simulation（RB+Y/R 复位、RB+X/Enter 暂停）、Motor（LB+A/M 使能、LB+B/K 失能、LB+X/P 阻尼、LB+RB 急停）、Skill（RB/LB + 十字键 = Num1–Num8 技能槽）、Movement（LY/LX/RX ↔ W/S/A/D/Q/E、Space 清零）。上游没有 `docs/`、没有 wiki、没有文档站；**除 README 这张表之外，没有任何地方记载"每个机器人用哪几个键"**——10 份 policy 的 `fsm.hpp` 各自只用到其中一个子集（go2/a1/b2/b2w/go2w 是同一组四个输入，g1 多四个技能槽）。

主办方分支把键位表写进了自己的 README（键盘表 `README.md:210-232`、手柄表 `:234-253`），但它的 `black` 状态机把**趴下**从上游的 `B` 改成 `RB + B`（另外加了 `T`/`Y` 策略切换、`5`/`B` 重试搬运）；它的 `rl_sdk.hpp:82` 的 "Recommend" 注释还是旧的 `B-GetDown`，与自己的代码不一致——**这类注释会过期，以 `fsm.hpp` 的 `CheckChange()` 为准**。

本仓那次移植用的是上游 go2 那一组（趴下仍是 `B`），逐个键的出处与我们自己的映射见 [`porting.md`](../../@20261007_assignment/docs/porting.md) §6.2 的状态转移图。

## 3 两份 yaml：谁读、什么时候读、同名项谁说了算

| | `policy/<robot>/base.yaml` | `policy/<robot>/<policy>/config.yaml` |
|---|---|---|
| 谁读 | `ReadYamlBase()`（`rl_sdk.cpp:360-386`），在**节点构造时**调一次 | `ReadYamlRL()`（`rl_sdk.cpp:388-441`），在**每次进 RL 状态**时由状态机的 `Enter()` 调 |
| 独有字段 | `dt`、`decimation`、`joint_names`、`joint_controller_names` | `model_name`、`num_observations`、`observations`、`observations_history`、`clip_obs`、`clip_actions_lower/upper`、`action_scale`、`lin_vel_scale`、`ang_vel_scale`、`dof_pos_scale`、`dof_vel_scale`、`commands_scale`、`rl_kp`、`rl_kd` |
| **同名（7 个）** | `default_dof_pos`、`fixed_kp`、`fixed_kd`、`joint_mapping`、`num_of_dofs`、`torque_limits`、`wheel_indices` | 同左，**进 RL 时覆盖** `base.yaml` 读到的那一份 |

分工仍然有意义：`base.yaml` 是"机器人级"，上电、阻尼、起身/趴下就要用（`dt`/`decimation` 甚至在构造时决定了那两条循环线程的周期）；`config.yaml` 是"策略级"，只有进 RL 才需要。上游给的策略模板里 `joint_names` 只出现在 `base.yaml`（`config.yaml` 里那份是文档性质，`ReadYamlRL()` 并不读它），数组顺序以 `joint_mapping` 为准。

**同名项如果不一致，不是"谁覆盖谁"，而是"分时刻生效"**：进 RL 之前用 `base.yaml` 的值，`InitRL()` 一跑就被 `config.yaml` 悄悄换掉。后果逐项：① `joint_mapping` 不一致 → 起身/站立按 base 的顺序、进 RL 后按 config 的顺序，**同一台狗的腿序在按键那一刻变了**；② `default_dof_pos` 不一致 → 策略的零动作站姿 ≠ 刚站好的姿势，进 RL 时会跳一下（`InitObservations()` 也用它）；③ `fixed_kp`/`fixed_kd` 不一致 → 只有起身/趴下用，但**进过一次 RL 之后**再按起身键用的已经是 config 的增益（`params` 只有一份），表现为"同样按键、第一次和后来手感不同"；④ `num_of_dofs` 不一致 → 缓冲区按 base 的值在构造时定尺寸、循环却按 config 的值跑，会读到 `joint_mapping` 越界；⑤ `torque_limits`/`wheel_indices` 只在 RL 侧生效，base 那份是摆设。**这不是假想的风险，上游与主办方自己就踩了**：上游 go2 的 `base.yaml` 与 `himloco/config.yaml` 在 `fixed_kp`/`fixed_kd`（80/3 vs 60/5）、`torque_limits`（23.5 vs 33.5）、`default_dof_pos` 的髋（0.00 vs 0.10）上都不同；主办方 black 的两份在 `default_dof_pos` 上不同（base 0.82/−1.5 vs config 0.8014/−1.527）。也就是说「站着时和进 RL 后，腿的零位与增益悄悄换了」这件事在他们仓库里是实际存在的。

**结论：这 7 项必须逐项相同**；要加护栏就在进 RL 前自己读一遍 base、逐项比对并告警（本仓的做法见任务 [`status.md`](../../@20261007_assignment/docs/status.md) 的 P2-e）。

## 4 参数机制：这套工程里"运行期改参数"不是常态

| 代码 | 参数怎么来 | 支持运行期改吗 |
|---|---|---|
| 上游 `rl_sar` | **没有** ROS 参数：启动时向独立的 `/param_node` 要一个 `robot_name`（`src/rl_sim.cpp:22-23`），其余全在 `policy/<robot>/*.yaml` | 否 |
| 主办方 `rl_sar-black-W` | `declare_parameter` 三个：`robot_name`、`gazebo_model_name`、`policy_config`（`src/rl_sim.cpp:150-152`） | 否（读一次，无回调） |
| 主办方 `quadruped_control` | gateway 7 个 `declare_parameter`（`adapters/ros2/quadruped_gateway/src/ros2_gateway.cpp:183-202`）＋ 一套 `config_loader` 读 yaml 预设 | 否 |

三份工程代码都没有 `add_on_set_parameters_callback`（只读材料里这个 API 只出现在 ROS 2 官方文档里）。所以往 rl_sar 这类节点上加"热改参数"是**超出培训方口径**的事：要改就写进 yaml，重启生效；ROS 参数只当启动时的开关。一般性的机制与讲义口径见 [`ros2-params-and-launch.md`](ros2-params-and-launch.md) §7。

一个容易踩的点：rl_sar 的 `policy/**/*.yaml` **不是** ROS 参数文件——它由 yaml-cpp 从源码目录读（编译期把 `CMAKE_CURRENT_SOURCE_DIR` 注入），`--params-file` 管不到。

## 5 三条队列：`pos` / `vel` / `tau`，以及 `tau` 只进不出

推理线程算完一帧后，把三种输出分别 push 进三条 `tbb::concurrent_queue<torch::Tensor>`（`rl_sdk.hpp:180-182`），控制线程用 `try_pop` 取（`policy/go2/fsm.hpp:208` 一次取 pos 与 vel）。三条队列是上游 `v2.3`（`87be546`，2025-03-13，"Reorganized the project structure… moved core libraries to `core/`"）一次性引进的，同一提交把 `ComputeOutput()` 拆成 `pos`/`vel`/`tau` 三个输出。

引入初衷（推断）：一套策略要同时支持三种驱动方式——腿式用位置 `pos`、轮式（go2w/b2w/l4w4）用速度 `vel`、纯力矩接口用 `tau`；三条队列就是"推理线程 → 控制线程"的三种交接通道。

**但 `tau` 那条自诞生起就没有消费者**：上游全仓没有一处 `output_dof_tau_queue.try_pop`（`rl_sim.cpp` 与 5 个 `rl_real_*.cpp` 只 push，10 份 policy 的 fsm 都只取 pos + vel）。上游对 `output_dof_tau` 的另两处用处也只是旁路：`TorqueProtect()`（调用被注释）与 `CSVLogger`。主办方分支**发现了这个问题**，在 `library/core/rl_sdk/rl_sdk.cpp:233` 加了 `RL::ClearOutputQueues()`（三条一起排空），在自己的状态机里于状态切换时调用。

坑在容器语义上：`tbb::concurrent_queue` **无界**（见 [`tbb.md`](tbb.md) §3），没人取就随推理次数一直涨——50 Hz、每次一个 1×12 float32 张量，5 分钟约 1.5 万个（量级几 MB）。pos/vel 两条因为控制线程每 5 ms 取一次、稳定在 0~1 个，只有 `tau` 会一直涨。处理方式有三种，代价从小到大：不 push（我们完全不用 `output_dof_tau`，fsm 里的前馈 `tau` 恒 0）、每次推理后自己排空、或照主办方加 `ClearOutputQueues()`（要动 `library/core`）。

**顺手做过一次容器审计**：rl_sar 与仿真节点里唯一"内存行为不确定"的就是这三条队列；其余都是有界或一次性的——`RobotState`/`RobotCommand` 的 6 组 `std::vector` 固定 32、运行期从不 `resize`、`ComputeObservation()` 的 `obs_list` 每次调用临时建（≤6 个）、`ReadVectorFromYaml()` 启动时按 yaml 长度、`ObservationBuffer::obs_buf` 是固定 1×270 张量、仿真节点 `idx.qpos/dof` 启动时 `resize` 一次、`motor::Bank::hist_` 按 `delay+1` 建一次；拿 `std::vector` 当 FIFO 的地方（仿真窗口的 `keys_`，`erase(begin())`）每帧被取空，增长只跟人手速有关。

## 6 时基：五套，以及 2 ms / 5 ms / 20 ms 的非整数倍

rl_sim 这条链路里同时存在**五套时基**：

| 时基 | 谁在用 |
|---|---|
| 仿真时间（MuJoCo `d->time`，2 ms/步） | 物理；对外是 `MotorState.sim_time` |
| 仿真节点墙钟（`steady_clock`） | realtime 节流、窗口锚点、状态行、看门狗（按步数） |
| rl_sim 的三条墙钟线程（5 / 20 / 50 ms） | 控制、推理、键盘（`library/core/loop/loop.hpp:70-80`） |
| 控制周期计数 | fsm 的斜坡（200/400/500 步）、`episode_length_buf` |
| ROS 时间戳 | 三条 `header.stamp`（一般只作诊断） |

**"周期"名义上都是整毫秒，实际不是**：`LoopFunc` 每圈"先干活、再睡 `period − 已用时间`"，而已用时间被 `duration_cast<milliseconds>` 截成**整毫秒**（`loop.hpp:75-76`），所以实际周期只长不短——本仓实测策略周期在仿真时间里是 20.76 ms 而不是 20（数字与影响见任务 [`experiments.md`](../../@20261007_assignment/docs/experiments.md) §3–§5）。这不是 `steady_clock` 的问题：它在 Linux 上就是 `clock_gettime(CLOCK_MONOTONIC)`（本机实测 `period = 1/1e9 s`、`is_steady = 1`）。

**"把内部时基一律改成纳秒"不划算**：① 时钟源本来就是那个，真正的缺陷只是上面那两行的截断；② 连续量用 SI（秒）是本仓约定；③ 换表示不换轴——墙钟与仿真时间仍是两条轴，暂停/慢放/快放的问题一个都解决不了；④ ROS 时间戳本来就是"秒 + 纳秒"两个整数域。

**培训方两边的做法**：rl_sar 这条线（上游与主办方 fork 的 `loop.hpp` 逐字节相同）**和我们一样是纯墙钟**，没有任何仿真时间驱动的设计；主办方自己的栈 `quadruped_control` 则是"**仿真时间的纳秒整数 + 事件驱动**"——状态帧时间戳由 `data->time` 转成 ns（`backends/mujoco/src/mujoco_robot_io.cpp:291-304`），控制器只在"来了新帧且 `latest_state_ns >= next_control_ns`"时算一次、`next_control_ns += control_period_ns`（`apps/runtime_daemons/motiond.cpp:455-471`），墙钟只负责物理推进（`steady_clock` 绝对期限 + `tick = timestep / real_time_factor`，渲染另按 `visual_sync_hz`）。**他们用 ns 表示的是"仿真时间"，不是把墙钟换成 ns。**

**"2 ms 步长 vs 5 ms 控制"这个非整数倍，两边都不当问题**：上游压根没把三者耦合（三条独立线程 + 仿真器自己的节拍，靠消息交接）；`quadruped_control` 也用 2 ms 步长（`assets/robots/black/mujoco/black_description.xml:3`）配 `control_period_ms: 5`（`configs/controllers/black.yaml:6`），它的帧门控会把 5 ms 期限量化到 2 ms 网格上 → **实际控制周期 6 ms**（多付 20%），也没当成 bug。所以不整除本身没有正确性问题，只在"把节拍改成按仿真步计数"时才必须凑成整数倍。

**改法（按仿真步计数）**：把两条墙钟热循环换成由反馈驱动——每收到 1 条 `/motor_state` 跑一次控制（2 ms，与仿真步长和实机 500 Hz 驱动板同级）、每 10 条跑一次推理（正好 20 ms）；`base.yaml` 的 `dt`/`decimation` 相应写成 0.002/10（或换成两个 tick 数参数），fsm 的斜坡常数按 2 ms 换算（200/400/500 → 500/1000/1250）。收益是策略周期在仿真时间里精确 20 ms、暂停/慢放/快放自动正确、全速回归（`realtime:=false`）顺带可用；代价是重写那段线程代码 + 全部数字重测。**要防的坑**：控制器看不到仿真步长（`MotorState` 只有 `sim_time`），"每 10 条"把 2 ms 硬编码进了语义——建议启动时用相邻两条 `sim_time` 的差自动量出步长并校验整除关系，否则将来仿真改成 1 ms 步长（或 `publish_every > 1`）时策略周期会悄悄变成 10 ms。

## 7 matplotlib / `PLOT` 与它的两个替代品

上游 `library/core/matplotlibcpp/` 是单头文件的 matplotlib-cpp；`include/rl_sim.hpp` 里有 `// #define PLOT`（默认关），打开后会启一条 **1 ms** 的 `loop_plot` 线程周期性调 `Plot()`（上游 `src/rl_sim.cpp:583-601`），用 matplotlib 画 12 行子图，每行"实际关节角（红）vs 目标关节角（蓝）"，横轴是 `motiontime` 计数器——这也是 `motiontime` 唯一的用途（关掉 PLOT 后它就只剩自增）。主办方分支同样保留了这个目录、同样默认关。

值不值得恢复？它画的是位置跟踪，而更省的两条路已经现成：① `rl_sdk.cpp:443-482` 的 `CSVInit`/`CSVLogger`（打开 `#define CSV_LOGGER` 就输出 `tau_cal`/`tau_est`/`joint_pos`/`joint_pos_target`/`joint_vel` 到 `policy/<robot>/motor.csv`，零额外依赖；注意 `tau_cal` 是 `ComputeOutput()` 顺手算的那份、不等于真正下发的指令）；② 不经 ROS 的参考实现可以直接读仿真真值。matplotlib 那条路的代价是要 Python 开发头 + numpy + matplotlib，而且一条 1 ms 的绘图线程就挂在实时控制旁边。

## 8 框架层里没被用到的东西

按"上游逐字复制"保留，列在这里免得下次有人当新发现：

- `RL::TorqueProtect()`：调用处被注释（上游 `rl_sim.cpp:542`；只有 l4w4 的实机文件真调用）。
- `RL::AttitudeProtect()`：上游只在实机文件里以注释形式出现，没有真调用点。
- `CSVInit` / `CSVLogger`：由 `#ifdef CSV_LOGGER` 关着（各通信文件的 `include` 里那行是注释）。
- `ObservationBuffer::reset()`、`FSM::RequestStateChange()`、`FSMManager::GetSupportedTypes()`：上游也没有调用点。
- 观测分支里只有 config 选中的那几个会走到；`lin_vel`、`ang_vel_world`、`phase`、`g1_phase`、`g1_mimic_phase` 五个分支（`rl_sdk.cpp:32/40/69/83/95`）只在别的机型/观测定义下用，连带 `motion_length` 与 `lin_vel_scale`（只有 `lin_vel` 分支用）也是死的。
- `ModelParams::damping` / `stiffness`（从不赋值）、`MotorCommand::mode`（32 个 int，从不读）、`RobotState::IMU::accelerometer` 与 `MotorState::ddq` / `cur`（各通信层只填自己填的那几个）、`LoopFunc` 的 `bindCPU`/`setThreadAffinity()`（默认 -1，从不绑核）。
- `KeyboardInterface()` 会把全部数字/字母/方向键解码成枚举，但多数机型的状态机只消费其中几个；`Escape`、`Enter`、`Num2`–`Num8`、多数手柄组合在上游也只被部分机型用到。

## 9 black 的规格从哪来、与 go2 等机型差在哪

### 9.1 三条来源，以及为什么大作业给的那份不够

- **大作业给的 `config.yaml`**（1172 B）是**策略级**的一份子集：`num_observations`、`observations`、`observations_history`、`rl_kp`/`rl_kd`、`action_scale`、`lin_vel_scale`/`ang_vel_scale`/`dof_pos_scale`/`dof_vel_scale`/`commands_scale`、`torque_limits`、`default_dof_pos`、`joint_names`。它**没有** `model_name`、`clip_obs`、`clip_actions_lower/upper`、`num_of_dofs`、`fixed_kp`/`fixed_kd`、`wheel_indices`、`joint_mapping`——而 `ReadYamlBase()` / `ReadYamlRL()` 对这些字段是**无条件读**的（缺一个就抛异常），所以必须补齐。
- **补齐的来源是主办方分支** `rl_sar-black-W` 的 `policy/black/{base.yaml, himloco/config.yaml}`。把大作业那份与主办方的 `black/himloco/config.yaml` 逐字段比过：**大作业里出现的每个数值都与之完全相同**，差别只是大作业少了上面那批字段、并用 `joint_names` 代替 `joint_mapping` → 可以认为大作业那份就是从它摘出来的（`dt`/`decimation` 大作业没给，同样取自这份）。
- **第三方交叉验证**：主办方自己的控制栈 `quadruped_control` 里，`configs/policies/black/flat.yaml` 与 `configs/controllers/black.yaml` 的同一批数字逐项一致——`command_scale [2.0, 2.0, 0.25]`、`angular_velocity_scale 0.25`、`joint_position_scale 1.0`、`joint_velocity_scale 0.05`、`kp 40`、`kd 1.2`、`action_scale 0.25`、`action_clip 100`，`joint_names` 也是 FL/FR/RL/RR。三处独立文件互相印证，所以这批数可以放心当"训练时的真值"。
- **上游 `policy/go2/*` 只提供字段结构**（有哪些键、什么形状、怎么命名）；数值上与 black 不同之处见下表。我们那份 `base.yaml` 里的 `dt`/`decimation`/`fixed_kp`/`fixed_kd`/`torque_limits`/`default_dof_pos` 直接继承主办方的 black，而不是照 go2 抄的。

### 9.2 black vs go2：同一套框架、同一个网络结构，几组数不同

| 字段 | black（大作业 / 主办方） | go2（上游模板） | 说明 |
|---|---|---|---|
| `model_name` | `best.pt` | `himloco.pt` | 两者都是 HIMLoco 的 TorchScript：输入 `[B, 270]`、输出 12 维，**参数量完全相同（243231）**——同构，差别全在训练出来的权重 |
| 观测 | 45 维，6 组（commands/ang_vel/gravity_vec/dof_pos/dof_vel/actions），`history [0..5]`，`clip_obs 100` | 完全相同 | 观测布局没有机型差异，**顺序与缩放必须严格照 config** |
| `dt` / `decimation` | 0.005 / 4（控制 200 Hz、策略 50 Hz） | 相同 | = HIMLoco 训练时的 `sim dt × decimation` |
| `rl_kp` / `rl_kd` | 40 / **1.2** | 40 / **1.0** | RL 状态的 PD 增益 |
| `fixed_kp` / `fixed_kd`（config 里那份） | 80 / 3 | **60 / 5** | go2 的 `base.yaml` 是 80 / 3——**它自己两份文件就不一致**（见 §3） |
| `action_scale` | 均匀 **0.25** | 髋 **0.125**、大腿/小腿 0.25 | 动作到关节目标的比例；髋减半是 go2 的训练选择，black 没有 |
| `torque_limits`（config 里那份） | 33.5 | 33.5（`base.yaml` 里是 **23.5**） | 又一处同名项不一致；另外两台的**仿真模型**都把执行器夹在 ±20 |
| `default_dof_pos` | [0.0, **0.8014**, **−1.527**] ×4 | [0.1, 0.80, −1.50] ×4 | 站姿，也是 RL 动作的零点 |
| 配置里的关节顺序 | FL / FR / RL / RR（大作业的 `joint_names`） | FR / FL / RR / RL（`base.yaml` 的 `joint_names`） | 训练框架（IsaacGym / legged_gym）的顺序是 FL/FR/RL/RR；go2 那份配置直接用了 Unitree MJCF 的顺序 |
| `joint_mapping` | `[0,1,2,3,4,5,9,10,11,6,7,8]`（我们）/ `[3,4,5,0,1,2,9,10,11,6,7,8]`（主办方 fork） | `[0..11]`（恒等） | go2 的配置顺序 = 它的 MJCF 顺序，恒等就够；black 的 MJCF 是 FL/FR/**RR/RL**、配置是 FL/FR/**RL/RR**，必须换后两条腿 |
| 物理模型 | 13.25 kg，`nq=19 nu=12`，步长 2 ms | 15.21 kg，`nq=19 nu=12`，步长 2 ms | 同一类平台，black 略轻 |

相邻机型也放在一张尺子上（都取各自 `base.yaml` 的第一个元素；`—` = 该机型没有 himloco 策略配置）：

| 机型 | 自由度 | `fixed_kp`/`kd` | `torque_limits` | `rl_kp`/`kd` | `action_scale[0]` | `joint_mapping[0]` |
|---|---|---|---|---|---|---|
| go2 | 12 | 80 / 3 | 23.5 | 40 / 1.0 | 0.125 | 0（恒等） |
| a1 | 12 | 80 / 3 | 33.5 | — | — | 0 |
| b2 | 12 | 200 / 3 | 200.0 | — | — | 0 |
| lite3 | 12 | 60 / 1 | 30.0 | 40 / 1.0 | 0.25 | 0 |
| **black** | 12 | 80 / 3 | 33.5 | 40 / 1.2 | 0.25 | **0**（主办方 fork 是 3） |
| go2w / b2w | 12 + 4 轮 | 70 / 5、200 / 3 | 23.5 / 200 | — | — | 0 |
| blackW | 16（+4 轮） | 80 / 3 | 33.5 | 50 / 1.2 | 0.25 | 4 |

（`blackW` 就是 black 加四个轮子：`num_of_dofs: 16`、`wheel_indices: [3, 7, 11, 15]`；轮式的策略与 black 不是同一个 `.pt`。）

### 9.3 对"用 black 跑 `best.pt`"这件事来说

1. **必须跟着 black 走、不能照抄 go2 的几组数**：`joint_mapping`（后两条腿互换）、`torque_limits`、`rl_kd`（1.2 vs 1.0）、`action_scale`（均匀 0.25 vs 髋 0.125）；`default_dof_pos` 只是精度差异。
2. **网络结构没有机型差异**：go2 与 black 的 `.pt` 参数量逐位相同，"跑的是哪个机器人"完全由**观测的顺序/缩放 + 动作的顺序/缩放 + `action_scale`** 决定——错一处，权重再好也是错的。
3. `torque_limits` 33.5 是**训练时**的限幅；我们与主办方的仿真模型都把执行器夹在 `ctrlrange="-20 20"`，实测 1.5 m/s 以内峰值 ≤ 20 N·m，不影响验收（本仓数字见 [`../../@20261007_assignment/docs/experiments.md`](../../@20261007_assignment/docs/experiments.md) §2）。
4. `dt`/`decimation` 决定"策略 50 Hz、控制 200 Hz"，与 §6 的时基是同一件事——改这两个值等于改控制周期。

### 9.4 复现

只读材料在本机与仓库**同级**（`../ReadOnly.d/`，不在仓库里、不入库；大作业 handout 在 `../ReadOnly.d/Downloaded.d/大作业/`）。下面命令都在仓库根 `MyMonoRepo.d/` 下跑：

```bash
D=../ReadOnly.d
# ① 大作业那份与主办方 black 的策略配置逐字段比（应只有"缺少的字段"与 joint_names/joint_mapping 的差别）
diff <(grep -v '^#' "$D/Downloaded.d/大作业/config.yaml") \
     <(grep -v '^#' "$D/rl_sar-black-W/src/rl_sar/policy/black/himloco/config.yaml")
# ② 两个 .pt 的结构与参数量（应同为 243231，输出 [1,270]->(1,12)）
pixi run python -c "import torch;p='$D/rl_sar-black-W/src/rl_sar/policy';[print(n,sum(x.numel() for x in torch.jit.load(p+'/'+n).parameters()),tuple(torch.jit.load(p+'/'+n)(torch.zeros(1,270)).shape)) for n in ['go2/himloco/himloco.pt','black/himloco/best.pt']]"
# ③ 质量与自由度（13.25 kg / 19 / 12 / 0.002）
pixi run python -c "import mujoco;m=mujoco.MjModel.from_xml_path('@20261005_ros2/models/black_description.xml');print(sum(m.body_mass),m.nq,m.nu,m.opt.timestep)"
# ④ 同名项不一致的两处实例（go2 的 base vs config）
grep -A1 'fixed_kp\|torque_limits' "$D/rl_sar-black-W/src/rl_sar/policy/go2/base.yaml" "$D/rl_sar-black-W/src/rl_sar/policy/go2/himloco/config.yaml" | head -12
```

## 10 复现与出处

```bash
# 本仓副本与上游的差异（先把上游 clone 到 /tmp）
git clone https://github.com/fan-ziqi/rl_sar.git /tmp/rl_sar_upstream && git -C /tmp/rl_sar_upstream checkout e5c2f41
U=/tmp/rl_sar_upstream/src/rl_sar; P=@20261007_assignment/ws/src/rl_sar
diff -r $U/library/core $P/library/core          # 应只报上游独有的 matplotlibcpp
diff -u $U/policy/go2/fsm.hpp $P/policy/black/fsm.hpp

# 三条队列的消费者：全仓搜 try_pop（只有 pos/vel 有；tau 一条都没有）
grep -rn "try_pop" $U/ | grep -v thirdparty

# 队列是哪个提交引进的（当前 HEAD 的历史里搜）
git -C /tmp/rl_sar_upstream log --oneline -S "output_dof_tau_queue" -- src/rl_sar/library/core/rl_sdk/rl_sdk.hpp

# 键位参考表在 README 的哪一节
grep -n "Gamepad and Keyboard Controls" $U/README.md
```

- 行号基线：`library/core/*` 本仓与上游**逐字节相同**，可以直接在本仓副本上核对；`src/rl_sim.cpp`、`policy/*/fsm.hpp`、`README.md` 那几处是上游文件，按上面的 commit 克隆后核对（主办方那两份代码在本机只读材料里，路径以其仓库为准）。
- **上游**：<https://github.com/fan-ziqi/rl_sar>，Apache-2.0；本文基准 `e5c2f41`。
- **主办方分支**：<https://github.com/N-W-wolf/rl_sar-black-W>（Apache-2.0，同源分支），基准 `cd46b93`。
- **主办方控制栈** `quadruped_control`、**讲义**（`ros2基本概念.md` 等）都是本机只读材料，不入库。
- 本仓副本、移植改动与逐项来源：[`@20261007_assignment/docs/porting.md`](../../@20261007_assignment/docs/porting.md)；实测数字：[`experiments.md`](../../@20261007_assignment/docs/experiments.md)；`.pt` 内部：[`policy-model.md`](../../@20261007_assignment/docs/policy-model.md)。
