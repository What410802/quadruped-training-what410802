# 移植说明：把 rl_sar 接到上次写的仿真节点上

本文回答四个问题：rl_sar 在系统里替换的是哪一层（§1）、从上游拿了什么、改了什么（§2、§3）、它和仿真节点之间怎么接（§4、§5、§6），以及上游有哪些不足、为什么保留原样（§7）。实验数字都在 [`experiments.md`](experiments.md)。

## 1. rl_sar 的生态位：替换控制器节点这一层

上次（`@20261005_ros2`）的系统是三个节点：手柄节点 → 控制器节点 ⇄ 仿真节点。rl_sar 正好占**控制器节点**这一格：它订阅关节反馈与 IMU，输出 MIT 五参数（kp、kd、q、dq、tau），力矩仍由仿真节点里的电机模型算——分工与上次完全一样，所以**仿真节点和手柄节点一行没改**，只把 `controller_node` 换成了 `rl_sim`。

```mermaid
flowchart LR
    JOY["joy_node<br/>（@20261005_ros2，原样）"]
    RL["rl_sim<br/>（本任务：rl_sar 移植）"]
    SIM["sim_node<br/>（@20261005_ros2，原样）"]
    JOY -->|"/joy"| RL
    RL -->|"/mit_command（MitCommand）"| SIM
    SIM -->|"/motor_state（MotorState）+ /imu"| RL
    RL -.->|"/sim_reset（服务）"| SIM
```

rl_sar 内部分三层，移植只动后两层：

| 层 | 位置（`ws/src/rl_sar/`） | 作用 | 本任务 |
|---|---|---|---|
| 框架 | `library/core/`（`rl_sdk`、`observation_buffer`、`fsm_core`、`loop`） | 拼观测、维护历史帧、推理、把动作换算成关节目标、读 yaml、调度状态机 | **逐字复制**，一字未改 |
| 机器人 | `policy/black/`（`base.yaml`、`himloco/config.yaml`、`best.pt`、`fsm.hpp`） | 这台狗的参数、策略与状态机 | 新写（照上游 go2 的模板） |
| 通信 | `src/rl_sim.cpp`、`include/rl_sim.hpp` | `RL` 的子类：实现 `GetState` / `SetCommand`，接 ROS 话题 | 改写上游的 Gazebo 版，接我们的话题 |

## 2. 文件清单：逐字复制 / 改写 / 新写

上游是 `fan-ziqi/rl_sar` 的 commit `e5c2f41`（2025-07-25，`main` 分支），许可证 Apache-2.0（[`../ws/src/rl_sar/LICENSE`](../ws/src/rl_sar/LICENSE)）。文件头口径（2026-10-10 起）：**改写过的文件**保留上游的 `Copyright` + `SPDX` 两行，并加一行 `Modified for @20261007_assignment from rl_sar e5c2f41 <上游路径>` 指向本节的清单——这是 Apache-2.0 第 4 条要求的"显著的修改声明"；**逐字复制**的 `library/core/**` 保持上游原样；**新写**的文件不带上游声明（与本仓既有新文件一致，许可由包内 `LICENSE` 覆盖）。**改动摘要只维护在下表**，文件头不再重复。

| 文件 | 来源 | 状态 | 改了什么 |
|---|---|---|---|
| `library/core/**`（6 个文件） | 同路径 | 逐字复制 | — |
| `LICENSE` | 仓库根 | 逐字复制 | — |
| `src/rl_sim.cpp` | `src/rl_sim.cpp` | 改写 | 见下面 7 + 4 条（第 12–15 条是后续阶段追加的） |
| `include/rl_sim.hpp` | `include/rl_sim.hpp` | 改写（删 74 行、加 19 行） | 成员换成我们的消息类型；删 ROS 1 / Gazebo / 画图 |
| `policy/fsm.hpp` | `policy/fsm.hpp` | 改写 | 只注册 `black` 一个机器人 |
| `policy/black/fsm.hpp` | `policy/go2/fsm.hpp` | 改写 | 改名 go2 → black（namespace、factory、头文件保护宏）；起身前的蹲姿换成 black 的（§6.2）；旋钮改从 `base.yaml` 读、RL 状态读局部副本、状态行移走（下面第 9–11 条）。**状态、转移与斜坡结构本身与 go2 相同** |
| `policy/black/knobs.hpp` | — | 新写 | 四个部署旋钮（`kd_passive`、三段斜坡周期数）从 `base.yaml` 读，加两份 yaml 的 7 个同名字段自检；`fsm.hpp` 只调用它 |
| `policy/black/base.yaml`、`himloco/config.yaml` | 照 go2 的模板 | 新写 | 字段来源见 §3 |
| `policy/black/himloco/best.pt` | 大作业附件 | 原样 | md5 `7af7bab2cc1cb559000551f2637e0649`，与主办方分支里 `black/himloco/best.pt` 相同 |
| `CMakeLists.txt`、`package.xml` | — | 新写 | 上游 344 行大多是 ROS 1 与实机 SDK；这里只编 `rl_sim` 一个目标 |
| `launch/rl_sim.launch.py` | — | 新写 | 起 sim_node + joy_node + rl_sim |
| `.clang-format` | — | 新写 | `DisableFormat: true`：不许重排上游代码，否则 diff 会被格式变动淹没 |

`src/rl_sim.cpp` 的 7 处改动：

1. `robot_name` 改成本节点自己的参数（默认 `black`）。上游要另起一个 `/param_node` 来问，启动时会一直等它。
2. 删掉 `StartJointController()`。上游在启动时 fork 一个 `ros2 run controller_manager spawner`，失败就抛异常；我们没有 ros2_control。
3. 状态输入改成 `/motor_state`（`quadruped_ros2/MotorState`）+ `/imu`，**QoS 改成 best_effort**（§4 的坑）。
4. 指令输出改成 `/mit_command`（`quadruped_ros2/MitCommand`），字段一一对应，`dq` 对应我们的 `w`。
5. 复位从 `/reset_world` 改成我们的 `/sim_reset`；删掉 Gazebo 的暂停 / 继续（Enter / RB+X），我们的仿真在窗口里按空格暂停。
6. `JoyCallback` 加一处长度检查，摇杆满偏对应的速度改成参数 `joy_command_scale`（§6.1）。
7. 补 `#include <torch/utils.h>`：libtorch 2.12 的 `torch/script.h` 不再带出 `torch::set_num_threads`（见 [`../../docs/pitfalls/environment.md`](../../docs/pitfalls/environment.md)「libtorch / pytorch」一节）。

另外删掉了 ROS 1 分支与 matplotlib 画图（`PLOT`，需要 Python 开发头与 numpy）。控制流程——两条墙钟线程 + 状态机——**一行没改**。

后续按 `status.md` 的阶段清单又改了八处（都在本包自己的文件里，`library/core/**` 仍未动一行）：

8. **不再 push `output_dof_tau_queue`**（S1/P1-b）：上游从 `src/rl_sim.cpp` 与 5 个 `rl_real_*.cpp` push、但没有任何 FSM pop，队列无界 → 纯泄漏；本移植不用前馈 `tau`（fsm 里恒 0），所以删掉那次 push。
9. **RL 状态读局部副本**（S1/P2-c）：`policy/black/fsm.hpp` 的 RL 状态本来就 `try_pop` 出 `_output_dof_pos`/`_output_dof_vel`，却去读成员 `rl.output_dof_pos`；现在改读副本，pos/vel 保证同帧、也没有 Tensor 句柄竞争。
10. **状态行改成节点参数**（S1/P1-a）：原来 RL 状态每个控制周期（200 Hz）用 `\r` 打一行 `RL Controller x:…`；现在由 `rl_sim` 的 ROS 参数 `status_period_ms`（默认 0 = 关）节流，打印移到 `RL_Sim::RobotControl()`。
11. **四个部署旋钮进 `base.yaml` + 进 RL 前自检**（S2/P1-a、P2-e）：`kd_passive`（默认 8.0）、`getup_pre_cycles`（200）、`getup_cycles`（400）、`getdown_cycles`（500）——上游把前三个值写死在 `policy/go2/fsm.hpp` 的斜坡里；现在由**新写的** [`policy/black/knobs.hpp`](../ws/src/rl_sar/policy/black/knobs.hpp) 读 `base.yaml`（缺键/缺文件就用默认值并告警）。同时在进 Passive 与每次进 RL 时比对 `base.yaml` 与 `himloco/config.yaml` 的 7 个同名字段，不一致就 WARN（[`../../docs/learn/rl-sar.md`](../../docs/learn/rl-sar.md) §3）。**这段机制刻意不写在 `fsm.hpp` 里**：`fsm.hpp` 是与上游 `policy/go2/fsm.hpp` 对照的文件，抽出后它相对上游只剩调用点，机制本身作为一个新文件单独记在这里。

12. ~~**复位与导航模式改成边沿触发**（P1-e）~~：**已被 S3.5 的输入层统一取代**（见第 17 条），保留这段作为过程记录——原来用 `control.current_gamepad` 判断 `R`/`RB+Y` 与 `N`/`X`，而 `JoyCallback` 只在"按下"时 `SetGamepad()`、松开没有任何调用清零，于是按一次 X 就会每 5 ms 翻转一次导航模式；现在改成看 `/joy` 原始按键的上升沿（`reset_pressed`/`nav_pressed`），一次按键一次动作。键盘路径保持上游语义（触发后清 `current_keyboard` 以便连按再次触发）。顺带在 `RL_Sim` 构造里把 `control` 的四个输入枚举显式置 `None`——`library/core` 的 `Control` 成员没有初值。
13. ~~**进状态时清输入锁存**（P1-g）~~：**已被 S3.5 取代**（`SeenIntents` 天然只认「进入该状态之后按下过的键」），保留作为过程记录——四个状态的 `Enter()` 都调 `black_fsm::ClearInputState(rl)`（定义在 `policy/black/knobs.hpp` 旁边、`fsm.hpp` 顶部）。因为 `Input` 只记录**变化**，上一步动作留下的值会被后面的状态当成"还按着"——实测反例是手柄按过 A 之后用键盘 `1` 进 RL，RL 的 `A → GetUp` 分支立刻命中，`RL → GetUp → RL …` 无限弹回。清锁存后过渡只认"在该状态下按的键"。
14. **进 RL 打一行提示**（P1-f）：`RLFSMStateRL_Locomotion::Enter()` 打 `Entered RL_Locomotion; … status_period_ms …`。S1 把 200 Hz 的状态行改成默认关闭的 `status_period_ms` 之后，终端上不再有新输出、最后停着 GetUp 的 `\r` 进度行，容易被误判为"卡在起身、进不了 RL"。
15. **`cmd_vel` / `joy` 改成相对名**（S3①，接口层面的说明见 §4）：本节点原来是全仓唯一混用绝对名的；改后默认解析结果不变（`/cmd_vel`、`/joy`），但 `--namespace` 能把六个接口（含服务 `sim_reset`）整体搬走。
16. ~~**十字键不再吞按键**（P1-h）~~：**已被 S3.5 取代**（十字键只是普通 bit，组合就是多个 bit，不再有「最后写入者赢」），保留作为过程记录——`JoyCallback()` 的映射是"最后写入者赢"（`SetGamepad()` 只有一个值），而四条十字键规则写在按键规则**之后**——手柄 D-pad 被按住（虚拟手柄更是"点一下锁存"、一直发 ±1）时，按 A 会被写成 `DPadDown`，状态机读到的永远不是 `Gamepad::A`，实测"趴卧下按 A 起不来"。现在把四条十字键规则**收进 `if (!any_gamepad_button)`**：任何按键按下时十字键让位，组合键（`RB+十字键上` 等自带按键条件）不受影响。
17. **输入层换成「每键电平+边沿 → 意图」**（S3.5）：新增 [`include/input_map.hpp`](../ws/src/rl_sar/include/input_map.hpp) 与自检 [`test/input_map_selftest.cpp`](../ws/src/rl_sar/test/input_map_selftest.cpp)（放在 `test/` 而不是 `src/`：它不是节点的一部分；CMake 里无条件构建、并在 `BUILD_TESTING` 下用 `add_test` 注册，于是 `colcon test --packages-select rl_sar` 也会跑它）。
`JoyCallback()` 现在只做长度护栏 + 存帧；每周期 `RobotControl()` 把 `/joy` 的按钮/十字键与键盘锁存翻译成 `KeyBits`（每键 1 bit 电平 + 1 bit 上帧电平，±1 的十字键也是普通 bit），`input_map::BeginCycle()` 按 `kBindings` 表解析出**意图**（StandUp / LieDown / EnterRL / Damp / ResetSim / ToggleNavigation / 键盘微调那一组）；
四个 FSM 状态改用 `SeenIntents`（进入清零、每周期累积、命中即用）读意图，`RobotControl()` 也读意图处理复位/导航/微调。
这一层一次性取代了第 12/13/16 三条补丁：边沿是纯函数、天生只发生一次（不需要「消费/清除」协议）、组合键就是多个 bit（不再有枚举别名与写入顺序之争）、`library/core` 的 `Input` 完全不再参与状态转移（它仍在原地、一字未改，只有键盘锁存还被适配器读）。
意图表就是 §6.2 那张键位表的代码版：以后加键位只改 `kBindings` 一行 + 文档表一行。
18. **控制栈改由仿真时间驱动**（S4，2026-10-11）：删掉 `loop_control` / `loop_rl` 两条墙钟 `LoopFunc`，改由 `/motor_state` 的回调驱动
`MotorStateCallback()` → `ControlStep(sim_time)`：控制按 `dt`（5 ms **仿真时间**）、推理按 `decimation`（4）个控制周期（20 ms 仿真时间）补步推进；
`SetCommand()` 加了变更检测（目标没变就只发心跳，每 20 个控制周期一条）；`base.yaml` 的 `dt`/`decimation` 回到上游的 0.005/4（`dt` 的本义就是控制周期，之前被误解成仿真的物理步长）。
好处与实测：1x 下策略周期 20.00 ms、全速 25x 仍 7/7、暂停时一步不跑；还顺带把跨线程共享数据消到只剩键盘一处（见 §7）。
频率总表在 [`control-stack-rates.md`](control-stack-rates.md)，反面教材（按"每条反馈一次控制"时通信量被打爆）记在 `status.md` 的 S4 行。
和上游逐行对照（先把上游 clone 到临时目录）：

```bash
git clone https://github.com/fan-ziqi/rl_sar.git /tmp/rl_sar_upstream && git -C /tmp/rl_sar_upstream checkout e5c2f41
U=/tmp/rl_sar_upstream/src/rl_sar; P=@20261007_assignment/ws/src/rl_sar   # 从仓库根执行
diff -u $U/src/rl_sim.cpp $P/src/rl_sim.cpp
diff -u $U/policy/go2/fsm.hpp $P/policy/black/fsm.hpp
diff -r $U/library/core $P/library/core | grep -v -E 'thirdparty|matplotlibcpp'   # 框架层：应只报上游独有的目录
```

## 3. 配置字段的来源

**功能/行为差异汇总**（相对上游 `e5c2f41`；括号里注明主办方 fork 的不同做法。接口与文件层面的差异见 §4 与上表）：

| 变更 | 上游行为 | 本仓行为 | 依据 |
|---|---|---|---|
| `output_dof_tau_queue` | 每次推理 push，但没有任何 FSM pop（无界队列持续增长） | **不 push** | 我方不需要前馈 `tau`（fsm 里恒 0）；见 [`status.md`](status.md) P1-b |
| RL 状态取数 | 读成员 `rl.output_dof_pos`（Tensor 句柄竞争；`try_pop` 出的副本被丢掉） | 读 `try_pop` 出的 `_output_dof_pos`/`_output_dof_vel`（保证 pos/vel 同帧） | P2-c |
| 状态行 | RL 状态每个控制周期（5 ms、200 Hz）打一行 `\r` | `status_period_ms` 节流（默认 **0 = 不打**），打印移到 `RL_Sim::RobotControl()` | P1-a |
| 部署旋钮 | `kd=8`、三段斜坡 200/400/500 写死在 `policy/go2/fsm.hpp` | `kd_passive` / `getup_pre_cycles` / `getup_cycles` / `getdown_cycles` 从 `base.yaml` 读（缺省 = 原值） | P1-a、S2 |
| 两份 yaml 一致性 | 没有检查（上游 go2 模板自己就 base 80/3 vs config 60/5） | 进 Passive 与每次进 RL 各查 7 个同名字段，不一致 WARN（主办方同样没有） | P2-e |
| 手柄快捷键（导航模式 `X`、复位 `RB+Y`） | 按一次之后**每 5 ms 重复**：`current_gamepad` 只被"按下"设置、从不回 `None`，而分支只清键盘 | 按 `/joy` **原始按键的上升沿**触发：一次按键一次动作（主办方 fork 在分支末尾补了 `current_gamepad = None`，能止住"永远刷"，但按住期间仍按 /joy 的 100 Hz 重复） | P1-e |
| `Control` 的输入状态 | `library/core` 里四个枚举成员**没有初值** | `RL_Sim` 构造里显式置 `Gamepad::None`/`Keyboard::None` | P1-e |
| 复位 / 暂停 | Gazebo `/reset_world`、`/pause_physics`、`/unpause_physics` | `/sim_reset`（**保留仿真时间轴**，只复位姿态）+ 窗口空格暂停 | §4 |
| 机器人名 / 参数来源 | 启动时向独立 `/param_node` 要 `robot_name` | 本节点 ROS 参数 `robot_name`（+ `joy_command_scale`、`status_period_ms`） | §4 |
| 画图与平台 | matplotlib/`PLOT`、ROS 1 分支、`ros2_control` spawner | 全部删掉（本仓不需要） | 上表 |

**本仓另外加了四个 `base.yaml` 专属键**（上游没有，值以前写死在 `policy/black/fsm.hpp`）：`kd_passive: 8.0`（Passive 的 kd）、`getup_pre_cycles: 200` / `getup_cycles: 400` / `getdown_cycles: 500`（三段斜坡的控制周期数）。它们只被 [`policy/black/knobs.hpp`](../ws/src/rl_sar/policy/black/knobs.hpp) 读、由 `fsm.hpp` 调用，不进 `RL` 的参数结构，所以也不受「7 个同名字段」的约束。

`ReadYamlBase()` / `ReadYamlRL()`（`library/core/rl_sdk/rl_sdk.cpp:360`、`:388`）缺任何一个字段都会抛异常，而大作业给的 `config.yaml` 只有一部分，所以要补。来源分三类：

先说明这两份 yaml 的分工：`base.yaml` 在**节点构造时**读（`dt`/`decimation`/关节表/`fixed_kp` 等，进 RL 之前就要用），`himloco/config.yaml` 在**每次进 RL** 时读；两边有 **7 个同名字段**（`default_dof_pos`、`fixed_kp`、`fixed_kd`、`joint_mapping`、`num_of_dofs`、`torque_limits`、`wheel_indices`），进 RL 时 config 的那份会**覆盖** base 的——所以这 7 项必须逐项相同，不一致不会报错、只会"分时刻生效"（逐一后果与两处真实实例列在 [`../../docs/learn/rl-sar.md`](../../docs/learn/rl-sar.md) §3；本任务打算加的护栏见 [`status.md`](status.md) P2-e。**black 这套数的来历，以及与 go2 等机型的逐项对照见同文 §9**——大作业给的 `config.yaml` 是主办方 black 策略配置的子集，缺的字段从主办方分支补，三处独立文件互证）：

| 字段 | 值 | 来源 |
|---|---|---|
| `observations`、`observations_history`、各 `*_scale`、`action_scale`、`rl_kp`、`rl_kd`、`torque_limits`、`default_dof_pos`、`joint_names` | 大作业给定 | 大作业 `config.yaml` |
| `dt`、`decimation` | 0.005、4（策略 50 Hz） | 大作业资料中没给；取主办方 rl_sar 分支（只读材料 `rl_sar-black-W`）`policy/black/base.yaml`，也是 legged_gym 的默认 |
| `fixed_kp`、`fixed_kd`（起身 / 趴下用） | 80、3 | 同上；恰好也是上次控制器（`@20261005_ros2`）的 kp / kd |
| `clip_obs`、`clip_actions_*` | 100、±100 | 同上 |
| `model_name`、`num_of_dofs`、`wheel_indices` | `best.pt`、12、`[]` | 显然值 |
| `joint_mapping` | `[0, 1, 2, `<br/>`  3, 4, 5,  `<br/>` 9, 10,11,`<br/>` 6, 7, 8 ]` | 本仓库仿真的执行器顺序选定 FL/FR/RR/RL，策略是 FL/FR/RL/RR。主办方分支是 `[3,4,5, 0,1,2,…]`，不应照抄 |

`joint_mapping[i]` 的含义是"策略第 i 个关节在仿真消息里的下标"：`GetState` 用它读（`src/rl_sim.cpp:138`），`SetCommand` 用它写（`src/rl_sim.cpp:148`）。`base.yaml` 与 `config.yaml` 里各有一份，`ReadYamlRL` 会用后者覆盖前者，所以两份必须相同。

关节符号已经核对过：我们模型的关节限位与 `default_dof_pos` 的符号一致（左腿大腿 +0.80 / 小腿 −1.53，右腿相反），基座 x 朝前、y 朝左，与训练约定相同。

### 3.1 各字段的单位

两份 yaml 里物理量字段的单位（12 维数组都是**策略顺序** FL / FR / RL / RR × hip / thigh / calf；这些名字来自上游 rl_sar / legged_gym，不带单位后缀，单位按这张表）：

| 字段 | 物理量 | 单位 |
|---|---|---|
| `dt` | 控制环周期 | s |
| `decimation` | 每几个控制周期推一次策略（策略周期 = `dt` × `decimation` = 20 ms） | 控制周期数（无量纲） |
| `default_dof_pos` | 12 个关节的站姿角 | rad |
| `action_scale` | 策略输出 1 个单位对应的关节角增量 | rad |
| `rl_kp`、`fixed_kp` | MIT 公式 τ = kp·(q_des − q) + kd·(w_des − q̇) 里的位置刚度 | N·m/rad（关节侧，不是转子侧；见 [`MitCommand.msg`](../../@20261005_ros2/ws/src/quadruped_ros2/msg/MitCommand.msg) 的注释） |
| `rl_kd`、`fixed_kd` | 同上的速度阻尼 | N·m·s/rad |
| `torque_limits` | 关节力矩上限 | N·m |
| `lin_vel_scale`、`ang_vel_scale`、`dof_pos_scale`、`dof_vel_scale`、`commands_scale` | 把物理量缩放成**无量纲**网络输入的系数（观测 = 物理量 × 系数） | 无量纲（数值上是"每物理单位"，如 `lin_vel_scale: 2.0` 作用在 m/s 上） |
| `clip_obs`、`clip_actions_lower`、`clip_actions_upper` | 观测 / 动作的截断阈值 | 无量纲 |
| `observations`、`observations_history`、`num_observations`、`num_of_dofs`、`wheel_indices`、`joint_names`、`joint_mapping`、`model_name`、`joint_controller_names` | 结构、名字、映射 | 非物理量 |

观测里各物理量的单位见 §5 的表。字段之外，代码里的连续量一律是 SI（米 / 秒 / 弧度 / N·m 系），名称里不带单位后缀是常态；少数非 SI 的量靠名字标注：`tilt_warn_deg` 与 `quadruped::attitude::TiltDeg()`（度，见 [`../../@20261005_ros2/docs/ros2-nodes.md`](../../@20261005_ros2/docs/ros2-nodes.md) §1.2）、诊断脚本的 `--period-ms` / `--delay-ms`（毫秒）。

例外的例外是上游框架层逐字拷来的 [`rl_sdk.cpp:228`](../ws/src/rl_sar/library/core/rl_sdk/rl_sdk.cpp) 的 `AttitudeProtect()`：阈值按度用（内部 `rad2deg`），名字却没带后缀；本移植里没人调用它（相关的 `TorqueProtect` 调用也被注释掉了，[`rl_sim.cpp:351`](../ws/src/rl_sar/src/rl_sim.cpp)）。

## 4. 接口对照

| 方向 | 上游 rl_sar（ROS 2 / Gazebo 版） | 本仓库 | 改法 |
|---|---|---|---|
| 状态入 | `robot_joint_controller/state`（`robot_msgs/RobotState`，float32，reliable） | `/motor_state`（`MotorState`，float64[12]，best_effort） | 换消息类型；按 `joint_mapping` 取下标 |
| IMU 入 | `/imu`（`sensor_msgs/Imu`，**reliable**） | `/imu`（同类型、同语义，best_effort） | **只改 QoS** |
| 手柄入 | `/joy`（摇杆上 / 左为正、十字键上 / 右为正） | `/joy`（同一约定，见 §6.1） | 只加长度检查 |
| 指令出 | `robot_joint_controller/command`（`RobotCommand`） | `/mit_command`（`MitCommand`，kp/kd/q/w/tau） | 换消息类型 |
| 复位 | `/reset_world`、`/pause_physics`、`/unpause_physics` | `/sim_reset` | 只接复位 |
| 参数 | 启动时向 `/param_node` 要 `robot_name` | 本节点参数 `robot_name`、`joy_command_scale`、`status_period_ms`（状态行周期 ms，0 = 关） | 改成 `declare_parameter` |

**话题名的前缀：已全部改成相对名**（S3①，2026-10-11）。原来本节点是全仓唯一混用绝对名的：`/cmd_vel`、`/joy` 绝对，`imu`、`motor_state`、`mit_command`、`sim_reset` 相对（上游也混：`/cmd_vel`、`/joy`、`/imu` 绝对 + `<namespace>robot_joint_controller/*` 相对，我们此前只把 `imu` 改成相对）。默认（无命名空间）解析结果与改前完全一样，实测 `ros2 topic list` 仍是 `/cmd_vel` `/imu` `/joy` `/mit_command` `/motor_state`；加上命名空间后六个接口一起搬：`ros2 run rl_sar rl_sim --ros-args -r __ns:=/robot1` → `ros2 topic list` 得到 `/robot1/{cmd_vel,imu,joy,mit_command,motor_state}`、`ros2 service list` 得到 `/robot1/sim_reset`（`ros2 node info /robot1/rl_sim_node` 可看到全部）。两端一起搬的端到端验证：把仿真节点与 `rl_sim` 都加 `-r __ns:=/robot1` 起起来，`ros2 topic list` 只剩 `/robot1/{cmd_vel,imu,joy,mit_command,motor_state}`，且 `mit_command`/`motor_state` 各有 1 发布 1 订阅（数据流仍然是通的，不是各自搬完就断线）。这条改动让本节点与 `@20261005_ros2` 的 `sim_node`/`controller_node`/`joy_node`（都已是相对名）能一起被 `--namespace` 整体搬走；混用时绝对名会留在根下、**静默对不上**，这是改它的唯一原因。

**`/cmd_vel` 与导航模式**：这条话题全仓没有发布者——它是给外部/人用的（主办方那边由 `ros2_gateway.cpp` 收）。用之前要先按 `N`（键盘）或手柄 `X` 切到 navigation mode——**只有在 ON 时** `RunModel()` 才把 `cmd_vel.linear.x/linear.y/angular.z` 当策略指令，OFF 时用摇杆的 `control.x/y/yaw`（摇杆在导航模式下被忽略，但按钮/状态切换照旧）：`pixi run ros2 topic pub -r 10 /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.5}, angular: {z: 0.3}}"`；再按一次切回摇杆。单位是 m/s、m/s、rad/s（与摇杆同量纲，满偏 = `joy_command_scale`）。本次任务不需要它，但按上游与主办方的做法保留（决定见 [`status.md`](status.md) P2-a）。

**QoS 的坑**：仿真节点的 `/motor_state` 与 `/imu` 是 best_effort 发的（500 Hz，只要最新）。ROS 2 里 **reliable 订阅者收不到 best_effort 发布者**（两端不匹配，不报错，只是一条也收不到），所以上游那种 `SystemDefaultsQoS()`（= reliable）订阅必须改成 best_effort（`src/rl_sim.cpp:19` 的 `LatestQoS()`，与仿真节点同一个定义）。反过来不受影响：reliable 发布、best_effort 订阅可以匹配，所以 `/joy` 不用改。

## 5. 一帧观测与动作是怎么算出来的

**一条线程就是全部**：控制与推理都在 ROS 执行器线程上，由 `/motor_state` 的回调 `MotorStateCallback()` → `ControlStep(sim_time)` 驱动（S4 之前是两条墙钟 `LoopFunc`，计时在 `library/core/loop/loop.hpp:70-80`，已删）：

* **控制**，仿真时间每 5 ms（`dt`）一次 `RobotControl()`：`GetState()` 把最新收到的消息拷进 `robot_state` → 状态机 `Run()` 填 MIT 五参数 → `SetCommand()` 发 `/mit_command`。
* **推理**，每 `decimation`（4）个控制周期、即 20 ms 仿真时间一次 `RunModel()`：拼观测 → 推理 → 换算成关节目标，放进队列；控制线程在 RL 状态下从队列里取（`policy/black/fsm.hpp:216`）。这个队列是 TBB 的 `tbb::concurrent_queue`——它是什么、为什么用它见 [`../../docs/learn/tbb.md`](../../docs/learn/tbb.md)。

观测（45 维，顺序按 `config.yaml` 的 `observations`，拼接在 `library/core/rl_sdk/rl_sdk.cpp:26` 起的 `ComputeObservation()`）：

| 段 | 维数 | 算法 | 缩放 |
|---|---|---|---|
| `commands` | 3 | 摇杆或键盘给的 (vx, vy, wz) [m/s, m/s, rad/s] | × (2.0, 2.0, 0.25) |
| `ang_vel` | 3 | IMU 陀螺 [rad/s]（机体系；`ang_vel` 在 `InitRL` 里被换成 `ang_vel_body`） | × 0.25 |
| `gravity_vec` | 3 | 无量纲（单位向量）。(0, 0, −1) 用 IMU 四元数转到机体系（`QuatRotateInverse`，`rl_sdk.cpp:178`） | 不缩放 |
| `dof_pos` | 12 | 关节角 [rad] − `default_dof_pos` | × 1.0 |
| `dof_vel` | 12 | 关节角速度 [rad/s] | × 0.05 |
| `actions` | 12 | 上一帧的网络输出（无量纲，未缩放） | 不缩放 |

然后整体截到 ±`clip_obs`，插进 6 帧的历史缓冲，**最新一帧排在最前**（`observation_buffer.cpp:49` 的 `get_obs_vec`，`observations_history: [0..5]` 里 0 是最新）——这个顺序不能反：`best.pt` 是 HIMLoco，actor 只取 270 维输入的**前 45 维**当"当前帧"，其余交给速度估计器（`.pt` 内部就是 `estimator` + `actor` 两个子网络，逐层结构、参数量与"顺序反了会怎样"的实测见 [`policy-model.md`](policy-model.md)）。

动作（`rl_sdk.cpp:161` 的 `ComputeOutput()`）：网络输出 12 维 → 截到 ±100 → × `action_scale`（0.25）→ 加 `default_dof_pos` = 关节目标 `q`；`dq` = 0；kp / kd 取 `rl_kp` / `rl_kd`（40 / 1.2）。仿真节点按 τ = kp·(q − q_now) + kd·(0 − dq_now) 算力矩，再在 ±20 N·m 限幅（实验表明这个限幅够用，见 [`experiments.md`](experiments.md) §2）。

这套拼法有一个**独立实现**做对照：[`../scripts/agent_scripts/policy_reference.py`](../scripts/agent_scripts/policy_reference.py) 按大作业说明在 Python 里重写了一遍观测与动作，不经 ROS、按仿真时间锁步跑；两边在同一指令下的结果对得上（[`experiments.md`](experiments.md) §3）。

## 6. 手柄与状态机

### 6.1 手柄的轴与正负号

`/joy` 的接口（8 轴 / 12 按钮的顺序与正负号）定义在 [`../../@20261005_ros2/docs/joystick.md`](../../@20261005_ros2/docs/joystick.md) §3，本节只讲 rl_sar 这一侧。

上游 `JoyCallback` 按"摇杆上 / 左为正、十字键上 / 右为正"读：`control.x = axes[1]`（前后）、`control.y = axes[0]`（左右）、`control.yaw = axes[3]`（转向），十字键上是 `axes[7] > 0`。这正是主办者 `gamepads.yaml` 的约定，也是我们的 `joy_node` 从 2026-10-08 起输出的约定，所以**这个函数只加了一处长度检查**（消息短于 8 轴 / 11 键时直接返回，免得越界），再把写死的 1.5 换成参数 `joy_command_scale`。

过程记录：一开始 `joy_node` 照搬内核的正负号（摇杆上 / 左为负、十字键上为负），rl_sim 里曾对 axes 0、1、3、4、7 取反来适配；同时发现上次的仿真手柄十字键竖轴与实体手柄相反。理清后把正负号统一放进 `joy_node`（与主办者把它放在手柄节点里的做法一致），仿真手柄也改成内核的约定，rl_sim 里的取反就删掉了。细节与内核源码出处见上面那节。

### 6.2 按键与状态

状态机是上游 go2 的那套（`policy/black/fsm.hpp`），一共 **4 个状态**，上电在 `RLFSMStatePassive`（阻尼：kp = 0、kd = 8）。状态名、转移条件与按键（手柄 / 键盘）画在下面这张图里，箭头上的标签是"手柄键 / 键盘键"；只有 `GetUp` 出去的那两条带前提（"站完"= `running_percent == 1`），其余按下就切：

```mermaid
stateDiagram-v2
    state "<code>RLFSMStatePassive</code><br/> 阻尼（kp = 0、kd = 8）" as Passive
    state "<code>RLFSMStateGetUp</code><br/> 起身（蹲姿 1 s → 站姿 2 s）" as GetUp
    state "<code>RLFSMStateRL_Locomotion</code><br/> 策略（加载 best.pt）" as RL
    state "<code>RLFSMStateGetDown</code><br/> 趴下（2.5 s 推回按 A 那一刻的关节角）" as GetDown

    [*] --> Passive
    Passive --> GetUp: A || 0
    GetUp --> Passive: LB+X || P
    GetUp --> RL: 站完&&(RB+十字键上 || 1)
    GetUp --> GetDown: 站完&&(B || 9)
    GetDown --> GetUp: A || 0
    GetDown --> Passive: 推完 || LB+X || P
    RL --> GetUp: A || 0
    RL --> GetDown: B || 9
    RL --> Passive: LB+X || P

    note right of RL: 注：在 RL 下再按 1（RB+十字键上）不改状态——FSM 只在目标状态名与当前不同时才切换（<code>library/core/fsm/fsm_core.hpp</code> <code>FSM#colon;#colon;RequestStateChange</code>）
```

① 从 `GetUp` 进 `RL_Locomotion` 要求起身斜坡已经走完（`running_percent == 1`；`RLFSMStateGetUp::CheckChange()` 里那个 `if`），斜坡没走完时按 `1` / RB+十字键上不会有反应；\
② `R` / RB+Y 不进状态机——它在 `RobotControl()` 里直接调 `/sim_reset`（[`../ws/src/rl_sar/src/rl_sim.cpp:223`](../ws/src/rl_sar/src/rl_sim.cpp)），状态保持不变。

| 操作（手柄 / 键盘） | 从 | 到 | 做什么 |
|---|---|---|---|
| A / `0` | Passive、GetDown | GetUp | 1 s 推到蹲姿，再 2 s 推到站姿 `default_dof_pos`（kp 80 / kd 3） |
| RB + 十字键上 / `1` | GetUp（站完后） | RL_Locomotion | 加载 `best.pt`，按策略走；左摇杆前后 / 左右、右摇杆转向，满偏 = 1.5 m/s 或 rad/s |
| B / `9` | GetUp、RL_Locomotion | GetDown | 2.5 s 把关节推回**按 A 那一刻**的关节角，然后转 Passive |
| LB + X / `P` | 任意 | Passive | 立刻转阻尼（⚠ `LB+X` 含原始 `X`，会同时翻转一次导航模式；键盘 `P` 不会） |
| RB + Y / `R` | 任意 | （不变） | 调 `/sim_reset` 复位仿真 |
| X / `N` | 任意 | （不变） | 切**导航模式**：ON 时策略指令改从 `/cmd_vel` 取（`linear.x`/`linear.y`/`angular.z`），摇杆被忽略；OFF 时用摇杆（详见 §4） |

**状态切换只认"当前状态下按的键"**（P1-g）：四个状态的 `Enter()` 都会清一次输入锁存（`black_fsm::ClearInputState`），因为 `library/core` 的 `Input` 只记录**变化**、按钮松开也不会回到 `None`，上一步动作留下的值会被后面的状态当成"还按着"。修复前的实测反例：先用手柄按 A 起身（`current_gamepad` 粘在 `A`），再用键盘 `1` 进 RL → RL 的 `A → GetUp` 分支第一个周期就命中 → `RL→GetUp→RL→…` 无限弹回（实测 5 次进 RL 全被弹回去，看起来就是"进不了 RL"）。清锁存后同一场景只进 1 次并停住；`RL` 下按 A / 按 B 分别进 GetUp / GetDown 仍然正常。

**输入层语义（S3.5 之后）**：转移由 [`input_map.hpp`](../ws/src/rl_sar/include/input_map.hpp) 解析出的**意图**驱动。吃透三条规则就够：

* **意图 = 边沿**：按下的那一周期产生一次，之后按住不再重复；「按着 RB 再按 A」里 A 照样是一次按下 ⇒ 现在**不再有**旧模型那种「变成 `RB_A`、谁都不认」的坑，只有**没绑定**的组合（如 `LB+A`）才什么都不做。
* **「在该状态下按下过就算」**：每个状态进状态时清零、每周期累积（`SeenIntents`），所以 `GetUp` 里「提前按一下 `RB+↑`、站完再生效」可以，和「一直按着」等效——但要**先站完**（斜坡 3 s，`running_percent == 1.0f` 是闸门）才会真的切过去；在此之前按过的键会被记住。
* **键盘源只有「最后一个键」**：`library/core` 的 `KeyboardInterface()` 是单值锁存、终端也不报抬起，所以键盘一次只能有一个键被认（`W`/`S`/`A`/`D`/`Q`/`E`/空格是「每按一次走一步」的微调），手柄按键与键盘可以同时产生意图。
* **长按**目前没有需求；`KeyBits` 就是加「按住时长」的地方（rl_sim 每周期都看得到帧，自己计时即可，不用改消息）。

**「按了没反应」怎么快速定位**（两条命令，各开一个终端）：

```bash
pixi run ros2 topic echo /joy                      # 勾选 RB「锁定按下」+ 点 ↑：应看到 buttons[5]=1 且 axes[7]=1.0
pixi run ros2 topic echo /mit_command --field kp   # 状态探针：kp=80 → GetUp/fixed_kp；kp=40 → 已在 RL（rl_kp）
```

第一条对不上 = 手柄→`/joy` 这一段（先看是不是旧实例、或别的设备被 `joy_node` 认领了）；第一条对而上不了 RL = 看第二条判状态、再看是否真的「站完」（斜坡共 3 s，`kp=80` 就是还在 GetUp）。虚拟手柄的十字键是**点一下锁存**（点 `●` 或「全部归中 / 松开」才回中），锁存本身不影响按键。
另外要记得：**`joy_node` 在 `install/` 里是源码的副本**，改完 `joy_node.py` 必须 `pixi run ros2-build` 才生效（`rl_sim` 是指向 `build/` 的符号链接，手柄脚本直接从源码运行，都不会「陈旧」）。

蹲姿：go2 的四条腿同号，而 black 的右腿关节是镜像的（符号相反），且 go2 的小腿 −2.65 超出 black 的小腿限位 [−2.5, −0.85]。所以换成主办方分支里 black 的蹲姿 (0, ±1.40, ∓2.20)，四条腿都在我们模型的限位内。

**键位是哪来的**：上游 rl_sar 自带一张参考键位表（只读材料里那份 e5c2f41 副本的 `README.md` 第 197–227 行 `Gamepad and Keyboard Controls`，线上同表见 [README_CN.md 的「使用手柄或键盘控制」](https://github.com/fan-ziqi/rl_sar/blob/main/README_CN.md)）。我们这套就是它的 go2 那一组——含"RB + 十字键上 = 进 Locomotion"这个组合键——不是自己编的；大作业要求文档里没有任何键位规定。与主办方 black 分支逐条对照只有一处不同：趴下用上游的 `B`（主办方改成 `RB + B`）。上游表里其余那些（`LB+A`/`LB+B` 电机使能、`LB+RB` 急停、`Num2`–`Num8` 技能槽、`Enter`/`RB+X` Gazebo 暂停）本移植没有实现：我们没有 ros2_control 与 Gazebo，暂停在仿真窗口里按空格。

键盘：rl_sim 直接读终端的 stdin，所以只在 `ros2 run` 独占一个终端时有效（launch 里不行）。另外，`joy_node` 在跑时每 10 ms 发一条 `/joy`，会把键盘 WASD 累加的速度覆盖掉——用键盘控速度时要 `joy:=false`。

## 7. 上游的不足与处理

按"先做实验，不严重就保留原样"的原则处理（数字见 [`experiments.md`](experiments.md)）：

| 不足 | 位置 | 影响 | 处理 |
|---|---|---|---|
| ~~两条墙钟线程，与仿真时间无关~~ | `loop.hpp:70-80` | 实时运行时策略周期在仿真时间里是 20.8 ms（训练是 20 ms）；暂停时还会"空转着把动作做完"；快放 3x 就摔 | **已修（S4，2026-10-11）**：控制与推理都由 `/motor_state` 的 `sim_time` 定节拍 → 1x 下 20.00 ms、25x 全速仍 7/7，暂停时一步不跑（[`control-stack-rates.md`](control-stack-rates.md)） |
| ~~线程间共享数据不加锁~~ | 见下 | 实测不出问题，理论上最坏是同一条指令里混入相邻两帧的数据 | **S4 之后基本消失**：控制与推理都在 ROS 执行器这一条线程上，只剩键盘轮询一处（见下） |
| 策略输出与控制之间靠队列传递（P2-c） | `src/rl_sim.cpp` 的 `try_pop`/`InitRL` | 上游用 `std::vector` 重新赋值，读端可能看到"半个"新向量 | **已修（2026-10-10）**：改成定长槽位、只在原地写（下面的第 3 条） |

**S4 之后的线程与共享数据**：进程里只剩两条线程——ROS 执行器线程（`/motor_state`、`/imu`、`/joy`、`/cmd_vel` 的回调 + 控制 + 推理，全都串行）和键盘轮询的墙钟 `LoopFunc`（50 ms，调 `library/core` 的 `KeyboardInterface()` 写 `control.current_keyboard`）。因此：

1. `motor_state_msg` / `imu_msg` / `robot_state` / `output_dof_pos` 这些"回调线程写、控制线程读"的模式**没有了**——写和读都在同一条线程上（`MotorStateCallback()` → `ControlStep()` → `GetState()`）✓。
2. 唯一剩下的跨线程项是**键盘锁存**：墙钟线程写 `control.current_keyboard`，控制线程读（[`input_map.hpp`](../ws/src/rl_sar/include/input_map.hpp) 的 `KeyboardMask()`）。它是一个 `enum`，最坏是读到相邻一次按键（人手的量级，无实际影响）；要彻底消掉就得把键盘轮询也搬进控制节拍，暂时不值得。
3. **P2-c 的历史记录**（2026-10-10，S4 之前修的）：那时策略线程给 `output_dof_pos` 重新赋值、控制线程读，`std::vector<double>` 的重新分配会让读端拿到"半个新向量"；改成定长槽位原地写之后消失。这条现在只作为"当时的线程模型"留档。

**2026-10-09 的复查结论**（针对当时的两处上游写法）：消息与 `robot_state` 都是定长、运行期从不重新分配，最坏只混入相邻一帧（差 2 ms），不值得为"形式上不再是数据竞争"（严格说都是 C++ 未定义行为、TSAN 会报）去加锁或改成槽位拷贝。S4 合并线程之后这两处自然不存在了。
