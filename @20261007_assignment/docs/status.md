# 推进情况

> 本文记"做到哪、待决什么、下一步"，会随推进改；入口与用法在 [`../README.md`](../README.md)。约定来源：[`../../docs/conventions.md`](../../docs/conventions.md) §2.6。

## 阶段状态

| 阶段 | 状态 | 证据 |
|---|---|---|
| 环境与工具链（libtorch / tbb / pytorch、clangd 23、单 pixi 环境） | ✅ 2026-10-08 | `best.pt` 在 C++ 与 Python 两侧加载一致；回归 `check_headless.py` 全过——[`../../docs/pitfalls/environment.md`](../../docs/pitfalls/environment.md) |
| 移植 rl_sar → rl_sim（框架层逐字、适配层改写、black 配置与状态机） | ✅ 2026-10-08 | 首次编译即过；逐文件改动见 [`porting.md`](porting.md) §2 |
| 验证：无头自检 / 干净 clone / 传统 ROS 2 方式 / 手柄接口 | ✅ 2026-10-08 | `check_walk.py` 7 项（`rest`/`raw`/干净 clone 各一次）、`check_headless.py` 全过；`env -i` 干净 shell（bash、zsh）从零编两个工作空间能跑——[`joystick.md`](../../@20261005_ros2/docs/joystick.md) §3、[`../README.md`](../README.md)「怎么跑」 |
| 文档：README + porting / experiments / policy-model / status（含状态转移图） | ✅ 2026-10-09 | [`policy-model.md`](policy-model.md)（`best.pt` 内部结构、参数量、三条实测坑）、[`porting.md`](porting.md) §6.2 |
| 复查与改动建议（P1/P2/P3）＋ 实施顺序 | ✅ 2026-10-10：**S1、S2 已实施**（另加 P1-e 手柄粘滞输入修复、P1-f 进 RL 提示；§6.2 键位与「非理想电机」各回归一遍，见 [`experiments.md`](experiments.md) §7）（tau 队列不再 push、RL 读局部副本、`status_period_ms`、四个部署旋钮 + yaml 同名项自检），P2-f 已完成；**S3 也已完成（2026-10-11）**：话题名统一为相对名、README 补导航模式、检查器三条改进、`ros2-graph-and-clock.md` 加了「名字就是路径」一节；S4 起未实施 | 见下面「改动建议」「实施顺序」 |
| 交付前人工项 | ⏳ 实体手柄正负号复验 | 见「待人工确认」 |

## 已定的决策（2026-10-08）

- 移植底座：上游 `fan-ziqi/rl_sar` `e5c2f41`（大作业附件里那份）；主办方的 black 分支只作参照。
- 时钟：**S4 起不再沿用上游的两条墙钟线程**——控制（每 `dt` = 5 ms 仿真时间）与推理（每 `decimation` = 20 ms 仿真时间）都由 `/motor_state` 的 `sim_time` 定节拍，暂停/慢放/快放自动正确（1x 下策略周期 20.00 ms、全速 25x 仍 7/7）；频率总表见 [`control-stack-rates.md`](control-stack-rates.md)。原先的记录：实验表明实时运行时影响很小（速度 −4.5%），但暂停时会空转、快放 3x 会摔。
- 线程间不加锁：保留原样（5 分钟浸泡无异常）。→ **2026-10-09 复查**：前两处（消息副本、`robot_state`）结论不变、仍建议保留；第 3 处（Tensor 成员句柄）建议改一行，见 P2-c。
- `best.pt`（约 1 MB）入库。
- 本包代码沿用上游风格，放 `.clang-format`（`DisableFormat: true`）防止被重排；仓库的新 C++ 工程仍按 conventions §3.10 自带 100 列格式（方案 A）。

## 待人工确认

1. **实体手柄的正负号**：`joy_node` 的换算依据是内核驱动源码（`xpad.c`、`hid-input.c`），本机那台 Zikway 还没在新约定下复验。核实方法：`pixi run ros2 run quadruped_ros2 joy_node` 与 `pixi run ros2 topic echo /joy` 各开一个终端，左摇杆推上看 `axes[1]`、十字键按上看 `axes[7]`，都应为 **+1**。若不是，改 `@20261005_ros2/ws/src/quadruped_ros2/scripts/joy_node.py` 里的 `SLOT_SIGN`（rl_sim 不用动）。

（开窗口目视、VSCode/clangd 两项 2026-10-09 已由人工确认完成，不再列。）

## 限位与安全审计（2026-10-11）

起因：问"电机限位在哪几个文件""Sim2Real 够不够"。逐层查完的结论放在新文档 [`safety-limits.md`](safety-limits.md)（含实测命令），要点：

* **真正生效的力矩限位只有仿真侧两道**：`motor.hpp: Torque()` 的 `clamp(τ, ±tau_max)`（默认 **20 N·m**，`sim_node` 的 `tau_max` 参数）与 MJCF 的 `<motor ctrllimited ctrlrange="-20 20">`。
* **策略侧三处"像保护的东西"都不生效**：`TorqueProtect()` 函数体自己写着 "Just a reminder, no protection"，上游与主办方的调用点全是注释；`output_dof_tau` 的 ±33.5 N·m 裁剪只进 CSV 与没人 pop 的队列（RL 里 `tau=0`）；`clip_actions = ±100` 形同虚设。
* **关节限位是 MuJoCo 的软约束**，实测：**RL 行走阶段 0 越界** ✓；趴着/起身/趴下（kp=0 或 80）阶段 calf 最多压过 **82 mrad**、hip 6 mrad、thigh 1 mrad。
* 实测力矩：**标准行走峰值 19.19 N·m、撞限幅 0 次**（仿真侧自报 193452 电机·步）；**只有 `/sim_reset`（`RB+Y`）瞬间**会贴到 20.00（约 200 ms）——策略按 ±33.5 训练、仿真给 ±20，但行走期间根本碰不到。
* 新增仪器 [`../scripts/agent_scripts/check_limits.py`](../scripts/agent_scripts/check_limits.py)（跑狗时另开终端，实测 τ/q 相对 ±20 与 MJCF `range` 的余量）。

**本轮已做（S5-1）**：控制器侧指令限位——纯函数 [`../ws/src/rl_sar/include/command_limit.hpp`](../ws/src/rl_sar/include/command_limit.hpp) + [`SetCommand()`](../ws/src/rl_sar/src/rl_sim.cpp)，五条规则：增益上限、`dq_des` 上限、`q_des` 变化率、可选绝对窗口、**蕴含力矩预算**`|tau_ff| + kp·|q_des−q| + kd·|dq_des−dq| ≤ command_tau_limit`（`q/dq` 取 `/motor_state`）。默认 33.5 N·m / 60 rad/s，即「训练包络」而不是模型自己的 ±20——实测在 20 上游夹会改写 `q_des` 把步态带偏（30 s 内 108 次事件、`check_walk` 的策略周期代理指标从 20.00 掉到 14.92 ms），33.5/60 只有 22 次、集中在状态机切换；自检 [`../ws/src/rl_sar/test/command_limit_selftest.cpp`](../ws/src/rl_sar/test/command_limit_selftest.cpp) 27 项全过、`check_walk` 7/7 且策略周期仍 20.00 ms。取舍与"保证什么/不保证什么"见 [`safety-limits.md`](safety-limits.md) §3。

**仍未做的三条**（S5 剩下的）：① 断流兜底（墙钟 deadman）；② 把 `q_des` 夹到机械范围（需要模型侧 `range` 进 yaml，见 [`safety-limits.md`](safety-limits.md) §4）；③ 让仿真里的关节限位更接近硬挡（调 `solref`）。

## 已知的小问题（不阻塞）

- 参考实现里 0.5 m/s 指令只走到 0.36 m/s（1.0 与 1.5 m/s 都跟得上），原因没查（[`experiments.md`](experiments.md) §2）。
- `check_walk.py` 只能按真实时间跑（约 35 s），不能全速回归——墙钟方案的代价（experiments §5）；做了 P1-c 之后这条自动消失。

- **虚拟手柄的按键问题（两条，都已解决）**：① 「按 RB+十字键上没反应」：运行侧（旧实例 / 设备认领 / 没有可见反馈），非本包问题，排障两行命令见 [`porting.md`](porting.md) §6.2。② 「锁存的十字键吞掉按键」：是上游映射的毛病（十字键规则写在按键之后、最后写入者赢），**已修**（P1-h）——虚拟手柄十字键「点一下锁存」只是触发器，锁存本身是设计，不影响按键了 现场只查到"注入 `/joy` 能进 RL、设备层能发出 `buttons[5]=1 + axes[7]=+1.00`"，**没能复现失败本身**（用户确认手柄窗口是当场新起的，而 Python 缓存不能解释：`python 脚本.py` 从不读 `__pycache__` 里的同名条目，`__main__` 每次都从源码编译，导入的 .pyc 也按源码 mtime/size 失效）。**真实隐患**：`joy_node` 在 `install/` 里是**副本**（不是符号链接），改完源码必须 `pixi run ros2-build`；`rl_sim` 则是指向 `build/` 的符号链接、手柄脚本直接从源码跑，两者不会"陈旧"。再遇到时的排查两行命令见 [`porting.md`](porting.md) §6.2
- **跨任务发现（2026-10-11，未修）**：`@20261005_ros2` 的 `sim_node` 里那句「200 ms 没收到 `/mit_command` 就退回阻尼」**当前不生效**——`sim_node.cpp:808` 的 `stale = !got || (steps - last_cmd_step) > timeout_steps` 里 `TakeCommand()` 是「收到过一次就每次返回 true」，于是 `if (got) last_cmd_step = steps;` 每步刷新时间戳、差值恒为 0。实测 `SIGSTOP` rl_sim 1.5 s（≈750 步 ≫ 100 步）期间仿真状态行一直 `cmd=ok`、没有任何看门狗打印。修法一行（把 `last_cmd_step` 移到 `/mit_command` 的订阅回调里更新），但那属于上一个任务的节点，本次只记录——本任务 S5 的「反馈陈旧检测 + 退回阻尼」**必须独立兜底**：S4 之后反馈一断 rl_sim 就一步都不跑，连阻尼指令都发不出去，仿真侧又不会自己退回阻尼。

## 决定与计划（2026-10-09）

> **证据与调研细节不在本文**：rl_sar 的机制、键位出处、两份 yaml、三条队列、五套时基、框架层未用功能在 [`../../docs/learn/rl-sar.md`](../../docs/learn/rl-sar.md)；参数读取惯例在 [`../../docs/learn/ros2-params-and-launch.md`](../../docs/learn/ros2-params-and-launch.md) §7；渲染/物理拆线程的协议与实测在 [`../../docs/learn/runtime-timing.md`](../../docs/learn/runtime-timing.md) §13；场景里"三块地面"（碰撞面/可见地面/阴影覆盖区）的区别与支配设置见 [`../../docs/learn/mujoco.md`](../../docs/learn/mujoco.md) §6.10。本节点自身的接口与线程现状在 [`porting.md`](porting.md) §4/§7。本节只记"做什么、不做什么、为什么、落点、怎么验收"——截至 2026-10-10：**P2-f 已实施**（见下表），其余**全部未实施**。

| 编号 | 决定 | 一行理由 | 落点 | 验收 |
|---|---|---|---|---|
| **P1-a** | ✅ **已实施（S1③+S2，2026-10-10）**：`kd_passive`、`getup_pre_cycles`/`getup_cycles`/`getdown_cycles` 写进 `base.yaml`，由 `policy/black/fsm.hpp` 自己读；`status_period_ms` 做成 rl_sim 的 ROS 参数 | 现值写死在代码里，实机起身时长与阻尼强度要能整定；**不做运行期热改**（培训方三处工程代码都只在启动时读参数） | `policy/black/base.yaml`、`policy/black/fsm.hpp`、`src/rl_sim.cpp` | 改 yaml 重启后行为确实变；两个自检逐项不变 |
| **P1-b** | ✅ **已实施（S1①，2026-10-10）**：不再 push `output_dof_tau_queue` | 上游自 v2.3 起就没人 pop，队列无界 → 长跑持续涨；我们也不用 `output_dof_tau` | `src/rl_sim.cpp:379-383` | 两个自检逐项不变 |
| **P1-c** | ✅ **已实施（S4，2026-10-11）**：控制与推理改由 `/motor_state` 的 `sim_time` 定节拍 | 最终做法**不是**「每条 `/motor_state` 跑一次控制」——全速时反馈到 4~5 kHz、`/mit_command` 跟着 4~5 kHz，两端被打爆（实测策略周期 28.5 ms、p95 50 ms、斜坡走不完）；改成控制每 `dt` = 5 ms 仿真时间一步、推理每 4 个控制周期（20 ms 仿真时间）一次 | `src/rl_sim.cpp` 的 `ControlStep()` / `SetCommand()`、`include/rl_sim.hpp`、`policy/black/base.yaml` | 1x 策略周期 20.00 ms、全速 25.28x 7/7、暂停实验（`check_feedback_clock.py`）2/2 |
| **P1-d** | **记录，暂不改**：`torch::set_num_threads(4)` 可以改成 ROS 参数 `torch_threads`（默认 4 = 今天的行为，`0` = 不调用、交给 libtorch/环境变量），但**先不动** | 机器相关的性能开关不该写死在代码里。**注意它是上游的写法、不是我们加的**：主办方分支每个通信文件都写死 4（主办方 `rl_sim.cpp:227`、5 个 `rl_real_*.cpp:44`），我们照抄在 `src/rl_sim.cpp:63`——所以这是"有意偏离上游"，要记进 [`porting.md`](porting.md) §2 的清单。实测推理 0.08 ms/次、1 线程与 8 线程一样，它不在关键路径上，但「写死 4」会误导 | `src/rl_sim.cpp:63`（若改） | 验收：`ros2 param get /rl_sim torch_threads` 能读到 + 设 `0`/`8` 各跑一次 `check_walk.py` 不劣化 |
| **P1-e** | ✅ **已实施（后由 S3.5 的输入层统一取代）** — 原记录：**已实施（方案 B，2026-10-10）**：`RobotControl()` 的两个分支按 `current_gamepad` 做**副作用**却只清 `current_keyboard`（`R`/`RB_Y` 复位、`N`/`X` 切导航模式）→ 手柄状态是**粘滞**的（`JoyCallback` 只在"按下"时 `SetGamepad()`，松开时没有任何调用把它清回 `None`），于是按一次 X 就会**每 5 ms 翻转一次**导航模式、按一次 RB+Y 就会**每 5 ms 请求一次复位**。两种改法：**B（推荐）边沿检测**——记下原始按键的上一帧状态，只在上升沿动作（按住也只触发一次）；**A（主办方做法）**在分支末尾补一行 `current_gamepad = Input::Gamepad::None;`——能止住"永远刷"，但按住期间仍会按 /joy 的 100 Hz 重复。两种都建议顺带在 `RL_Sim` 构造里显式初始化 `control` 的四个输入枚举（`library/core` 的 `Control` 成员没有初值，是"没按任何键也刷"的可能来源） | 证据：上游 handout 的 `src/rl_sim.cpp:322`、`:402` 只清键盘；主办方 fork 的 `:577`、`:655` 补了 `Gamepad::None` —— **不是我们改坏的**，是逐字继承的；本地现象与复现方法见本条 | `src/rl_sim.cpp`、`include/rl_sim.hpp` | **实测**：用确定性 `/joy` 序列（X 按 3 s → 松 2 s → X 再按 3 s → 松）→ 日志里恰好 **2 次**（`ON`/`OFF` 各一次，= 一次按键一次动作；修前是 ~200 次/s）；RB+Y 期间机器狗姿态确实被复位（z 从 0.414 掉到 0.196 再爬起来）；`check_walk.py` 7/7 |
| **P1-f** | ✅ **已实施（2026-10-10）**：进 RL 时打一行 `Entered RL_Locomotion; … status_period_ms …`（`RLFSMStateRL_Locomotion::Enter()`），与 Passive 的进状态提示同风格。S1③ 把 200 Hz 状态行移走后终端上不再有新输出，屏幕最后停着 GetUp 用 `\r` 打的 `Getting up 100.00%`，会被误判成「卡在起身、进不了 RL」——状态机本身一直在正常切换 | 依据：[`experiments.md`](experiments.md) §7；修复前日志里 `[FSM] Switch from RLFSMStateGetUp to RLFSMStateRL_Locomotion` 一直在打 | `policy/black/fsm.hpp` | 手柄与键盘两条时间线都能看到该提示；`check_walk.py` 7/7 |
| **P1-g** | ✅ **已实施（后由 S3.5 的输入层统一取代）** — 原记录：**已实施（2026-10-10）**：四个状态的 `Enter()` 调 `black_fsm::ClearInputState(rl)` 清掉键盘/手柄锁存。`library/core` 的 `Input` 只记录**变化**、按钮松开不回 `None`，所以上一步动作的残留值会被下一个状态当成"还按着"：实测反例是**手柄按过 A + 键盘 `1` 进 RL** → RL 的 `A → GetUp` 分支立刻命中 → `RL→GetUp→RL…` 无限弹回（用户报告的"RL 下按 A/B 没用/进不了 RL"就是这个）；清锁存后同一场景只进 1 次并停住，RL 下按 A/B 仍分别进 GetUp/GetDown | 依据：[`experiments.md`](experiments.md) §7；[`porting.md`](porting.md) §6.2 也写了这条与「组合键别名」的坑 | `policy/black/fsm.hpp` | 混合输入时间线：修复前 5 次进 RL 全被弹回 → 修复后 1 次并保持；手柄/键盘两套键位扫描与 `check_walk.py` 7/7 全过 |
| **P1-h** | ✅ **已实施（后由 S3.5 的输入层统一取代）** — 原记录：**已实施（2026-10-11）**：把 `JoyCallback()` 里四条**十字键**规则收进 `if (!any_gamepad_button)` —— 上游映射是「最后写入者赢」，十字键写在按键之后，手柄 D-pad 被按住（虚拟手柄更是「点一下锁存」、一直发 ±1）时按 A/B 会被写成 `DPadDown/Up`，状态机读不到 `Gamepad::A`（实测「趴卧下按 A 起不来」）。组合键（`RB+十字键上` 等自带按键条件）不受影响 | 两组独立对照（只差十字键是否锁存）：修前 `hat=down` 无切换 / `hat=clear` `Passive→GetUp`；修后两组都 ✓，且「锁存 ↑ + RB」仍给出 `GetUp→RL`。见 [`experiments.md`](experiments.md) §7 | `src/rl_sim.cpp` | 上述对照 + 手柄键位扫描 5 段切换 + `check_walk.py` 7/7 |
| **P2-a** | ✅ **话题名已统一为相对名（S3①，2026-10-11）**；`/control_status` 断链**记录不改**；`/cmd_vel` **保留**并补文档（已写入 [`../README.md`](../README.md) 与 [`porting.md`](porting.md) §4） | 断链那条本次任务没要求、手柄收反馈也没有动作价值；相对名才能在 `--namespace` 下整体搬；`/cmd_vel` 是唯一的非手柄指令通路 | `src/rl_sim.cpp`（话题名）、[`../README.md`](../README.md)、[`porting.md`](porting.md) §4 | `--namespace` 起一次确认接口；README 补 `N`/`X` 与 `ros2 topic pub /cmd_vel` 例子 |
| **P2-b** | ✅ **已实施（S3③，2026-10-11）**：`check_md_links.py` 三处改进——① 标题扫描支持引用块标题（`> ### …` 也算标题）；② **链接目标在扫描范围之外时按需补算它的标题**（这才是那两条"锚点找不到"的真正原因：任务目录链接仓库根 `README.md`，它的标题从来没进过 `heads`）；③ 新增结构检查"引用块以「：」结尾、紧随的代码围栏却没写 `>`"。**六个目录现在全 0**（断链/锚点/表格/结构） | 它不是外部库、是本仓脚本；修前那两条「锚点找不到」（`@20261007_assignment/README.md`、`@20261005_ros2/README.md` 指向根 README 的传统 ROS 2 方式一节）都是误报 | `@20260927_motor/scripts/agent_scripts/check_md_links.py` | 全仓跑一遍 0 告警 |
| **P2-c** | ✅ **已实施（S1②，2026-10-10）**：fsm 读 `_output_dof_pos`/`_output_dof_vel` 而不是成员；前两处保留 | 三处都无锁；前两处数据不重分配、最坏只混入相邻一帧；第 3 处涉及 Tensor 句柄，改完还能保证 pos/vel 同帧 | `policy/black/fsm.hpp:260` | `check_walk.py` 7/7 |
| **P2-d** | 键位差异**不改代码**：README 的操作说明就是我们的键位出处 | 与主办方只差"趴下"一处（我们 `B` = 上游写法），整套键位有上游 README 参考表支撑 | [`../README.md`](../README.md)（顺带补 `N`/`X`） | 目视核对 README 列全 |
| **P2-e** | ✅ **已实施（S2，2026-10-10）**：新增 [`../ws/src/rl_sar/policy/black/knobs.hpp`](../ws/src/rl_sar/policy/black/knobs.hpp) 自读 `base.yaml`，与 `himloco/config.yaml` 的 7 个同名项比对，不一致就 WARNING；**初始化时查一次，每次进 RL 再查一次** | 同名项是"分时刻生效"，不一致不会报错、只会变样（上游 go2 的 80/3 vs 60/5、23.5 vs 33.5，主办方 black 的站姿 0.82/−1.5 vs 0.8014/−1.527 都是真实实例）；而且 `config.yaml` **每次进 RL 都被重新读**（`Enter()` → `InitRL()` → `ReadYamlRL()`，`policy/black/fsm.hpp:246`），只查初始化会漏掉"中途改文件再重进 RL"——这同时是一条可用的调参路径：改 `config.yaml` 后重进 RL 即生效，改 `base.yaml`（构造时读一次）则要重启。副作用要写进 README：kp/kd 变化会在切入 RL 那一刻跳一下，`joint_mapping`/`num_of_dofs` 更不该中途改 | `policy/black/fsm.hpp` | 故意改一个值：初始化时打出一次 WARNING，重进 RL 再打一次 |
| **P2-f** | ✅ **已实施（2026-10-10）**：4 个改写过的文件头压成 3 行内容（`Copyright` + `SPDX` + `Modified for … from rl_sar e5c2f41 <上游路径>` / `Change list: porting.md §2`），明细只在 [`porting.md`](porting.md) §2 维护；逐字复制的 `library/core/**` 未动；新写文件不加声明（与本仓既有新文件一致，许可由包内 `LICENSE` 覆盖） | 同一份清单原先有两处（4 个文件头共 38 行），而 Apache-2.0 §4(b) 只要求"显著的修改声明"，一行足够；整块移进文档反而会弱化这条 | `src/rl_sim.cpp`、`include/rl_sim.hpp`、`policy/fsm.hpp`、`policy/black/fsm.hpp`（38 → 24 行） | 编译过 + `check_walk.py` 7/7（改动只有注释）；`porting.md` §2 的表 + 7 条清单覆盖被删掉的每一条 |
| **P2-g** | **建议做（安全相关，未做）**：① `rl_sim` 加**反馈陈旧检测**（记最后一条 `/motor_state` 的 `sim_time`/到达时刻，超过 N 个策略周期没更新 → WARN + 退回阻尼）；② 首帧门控（收到第一条反馈前不推理）；③ `/joy` 超时（>0.5 s 无消息 → 清 `control`）并在 `frame_id == "joy_disconnected"` 时打一行；④ 把"落后"变可见（仿真节点撞补步上限时告警；rl_sim 状态行加"有效反馈率"） | 现状**反馈方向完全没有超时**：仿真节点挂住时 rl_sim 会一直拿最后一帧推理并发命令，没人会发现；`joy_node` 进程死掉同理会一直用最后一帧（拔掉设备那条已经安全：joy_node 会归零并继续发）。指令方向有仿真侧看门狗兜底，唯独这两条没有。逐条分析与边界见 [`../../docs/learn/runtime-timing.md`](../../docs/learn/runtime-timing.md) §14 | `src/rl_sim.cpp`、`include/rl_sim.hpp`（④ 另涉 `sim_node.cpp`） | 用 `kill -STOP` 冻住仿真节点：≤1 s 内出现 WARN 并退出 RL/退回阻尼，`kill -CONT` 后行为明确（回 RL 或要求重启）；两个自检仍全过 |
| **P2-h** | **记录，未做**：给激活/构建脚本加一个前置体检——① `AMENT_PREFIX_PATH`/`CMAKE_PREFIX_PATH` 里出现 `/opt/ros/` 或环境与仓库之外的路径就警告；② 两个工作空间提供同名包时警告；③ `ros2` 可执行文件不是环境里那个时警告 | pixi 激活时 RoboStack 的钩子只**替换** `AMENT_PREFIX_PATH` 与 `ROS_ETC_DIR`，**不清理** `CMAKE_PREFIX_PATH`/`PYTHONPATH`/`LD_LIBRARY_PATH`/`PATH`；自动发现脚本按字节序 source 各工作空间，而"同名包 / 用别的环境构建过的工作空间 / 调用方 shell 里 source 过系统 ROS"这三种冲突都不会报错，只会静默按前缀顺序解析 | `scripts/activate_ros2_workspaces.sh`、`scripts/build_ros2_workspaces.sh` | 造一个 PATH 里带系统 ROS 的 shell：激活时打得出警告；正常 shell 无输出 |
| **P3** | **不做**（记录在案）：`fixed_kp`/`fixed_kd`/`rl_kp`/`rl_kd` 的 ROS 覆盖；`config_name` 参数化；三轴指令限幅；`tilt_warn_deg` 接 `AttitudeProtect()`；力矩保护；`motiontime`、`simulation_running` 等死代码；matplotlib/PLOT 恢复；运行期热改；策略路径的 `policy_root`（不影响仓库可复现性） | 要么要动 `library/core`，要么验收前不必要；逐条理由与替代方案见 [`../../docs/learn/rl-sar.md`](../../docs/learn/rl-sar.md) §4/§7/§8 | — | — |
| **P3-a/b** | **触发式**：渲染/物理拆线程（物理按仿真步定节拍 + 渲染独立），现在不做 | 今天 1.00x、物理只占帧预算 2%，拆线程换来的是"隔离"而不是帧率；等做重场景或更高光栅化精度那一轮 | `viewer.hpp`、`sim_node.cpp` | 见 [`../../docs/learn/runtime-timing.md`](../../docs/learn/runtime-timing.md) §13 |

**P1-d 的性能开关盘点**（2026-10-10 全仓扫了一遍 `set_num_threads|OMP/MKL_NUM_THREADS|hardware_concurrency|num_threads|bindCPU|setThreadAffinity|parallel-workers`；代码里真正的"性能写死"只有一处，其余都是有意为之）：

| 位置 | 现值 | 性质 | 决定 |
|---|---|---|---|
| [`../ws/src/rl_sar/src/rl_sim.cpp:62`](../ws/src/rl_sar/src/rl_sim.cpp) `torch::set_num_threads(4)`（上游写法：主办方分支 `src/rl_sim.cpp:227` 与 5 个 `rl_real_*.cpp:44` 都是 4） | 4 | libtorch 推理线程池大小 | **暂不改**；真要改就做成参数 `torch_threads`（默认 4），并把「偏离上游写法」记进 [`porting.md`](porting.md) §2 |
| `src/rl_sim.cpp:62` `GradMode::set_enabled(false)` | off | 关 autograd | 留（纯收益） |
| `src/rl_sim.cpp:107` 唯一的 `LoopFunc`（键盘轮询）不传 `bindCPU` | -1（不绑核） | CPU 亲和（[`loop.hpp:23/30/33/103`](../ws/src/rl_sar/library/core/loop/loop.hpp) 已实现） | **仍未做**：S4 已把控制/推理合并到执行器线程、墙钟循环只剩键盘这一条；绑核要绑也得先量抖动 |
| `src/rl_sim.cpp:107` 键盘循环 0.05 s | 20 Hz | 输入轮询率 | 留（写死但无收益） |
| [`@20261005_ros2/…/sim_node.cpp`](../../@20261005_ros2/ws/src/quadruped_ros2/src/sim_node.cpp) `kMaxCatchupSteps = 200`、`kMaxLagSeconds = 0.2` | 200 步 / 0.2 s | 过载策略（渲染顶住物理的上限） | 记录：与 P3-b 的"降速告警"是同一件事，做 P3-b 时一起参数化 |
| 同文件 `kViewerWidth/Height = 1280×720` | 写死 | 窗口尺寸 = 渲染成本 | 可参数化（`viewer_width/height`），属 P3-a 的画质一族；**三项画质（shadow / msaa / render_scale）已经是参数** |
| [`viewer.hpp:58/60`](../../@20261005_ros2/ws/src/quadruped_ros2/include/quadruped_ros2/viewer.hpp) `kDefaultMsaa = 4`、`kDefaultRenderScale = 2` | 4 / 2× | 画质默认值 | 留（只是默认值，运行期由 sim_node 参数覆盖） |
| MuJoCo 侧 | 单线程 `mj_step`；`mju_threadpool` 未用；`<option timestep=…>` 在 XML 里 | 物理并行度 | **不用**：本模型 43 µs/步，单线程远够；要用得先在模型里做 island 并行 |
| 构建 | `CMAKE_BUILD_TYPE=Release`（未设时，[`CMakeLists.txt:12`](../ws/src/rl_sar/CMakeLists.txt)）；并行度交给 colcon 默认 | 编译优化 | 留（脚本里没写死 `-j`；pixi 环境也没设 OMP/MKL/TBB 变量） |

## 实施顺序（2026-10-10 定稿；S1 起逐段做）

原则：**按文件分组、风险从零到有、每段单独可验收**；每段跑现成的两个自检（`check_walk.py` 7 项、`check_headless.py` 7 项），并按「改代码时要顺带改的文档」那张表同步表述；`library/core/**` 一行都不动（P1-c 首选方案也不需要）。

| 阶段 | 做什么（对应上面的条目） | 动哪些文件 | 验收 | 风险 |
|---|---|---|---|---|
| **S1 零风险清理** ✅ 2026-10-10 | ① 不再 push `output_dof_tau_queue`（P1-b）；② `fsm.hpp` 改读 `_output_dof_pos`/`_output_dof_vel`（P2-c）；③ `status_period_ms` 参数 + 按周期打状态行（P1-a 第三条） | `src/rl_sim.cpp`、`include/rl_sim.hpp`、`policy/black/fsm.hpp` | 两个自检逐项与基线一致 | 无（不改控制律） |
| **S2 参数与自检** ✅ 2026-10-10 | ① `kd_passive`、`getup_pre_cycles`/`getup_cycles`/`getdown_cycles` 进 `base.yaml`、由新的 `policy/black/knobs.hpp` 读（P1-a 前两条）；② 进 RL 前比对两份 yaml 的 7 个同名项、不一致就 WARN（**初始化 + 每次进 RL 各查一次**，P2-e） | `policy/black/base.yaml`、`policy/black/knobs.hpp`（新）、`policy/black/fsm.hpp` | 两个自检 + 改 yaml 重启后起身时长/阻尼确实变；故意改一个同名项 → 两条 WARNING（初始化、进 RL 各一条） | 低（默认值 = 现值；错读要有兜底） |
| **S3 话题与文档面** ✅ 2026-10-11 | ① 话题名统一为相对名（P2-a）：`cmd_vel`/`joy` 去掉斜杠，默认名字不变、`--namespace` 下六个接口整体搬（+服务 `sim_reset`），端到端验证过；② README 补 `N`/手柄 `X` 导航模式与 `ros2 topic pub /cmd_vel` 例子（P2-a/P2-d），[`porting.md`](porting.md) §6.2 键位表也补了导航模式那一行；③ 检查器三条改进（P2-b）；④ 「哪些名字是真正的路径」写入 [`../../docs/learn/ros2-graph-and-clock.md`](../../docs/learn/ros2-graph-and-clock.md) §3（数据由子任务现场实测） | [`src/rl_sim.cpp`](../ws/src/rl_sar/src/rl_sim.cpp)、[`../README.md`](../README.md)、[`porting.md`](porting.md)、[`../../@20260927_motor/scripts/agent_scripts/check_md_links.py`](../../@20260927_motor/scripts/agent_scripts/check_md_links.py)、[`../../docs/learn/ros2-graph-and-clock.md`](../../docs/learn/ros2-graph-and-clock.md) | 六个目录文档自检全 0（断链/锚点/表格/引用块）；`check_walk.py` 仍 7/7；`--namespace` 起一次确认接口整体搬 | 低 |
| **S3.5 输入层** ✅ 2026-10-11 | 新增 [`../ws/src/rl_sar/include/input_map.hpp`](../ws/src/rl_sar/include/input_map.hpp)（每键 1 bit 电平 + 1 bit 上帧电平；`kBindings` 表把「组合 → 意图」写成数据）+ 自检 [`../ws/src/rl_sar/test/input_map_selftest.cpp`](../ws/src/rl_sar/test/input_map_selftest.cpp)；`JoyCallback()` 只存帧 + 赋值连续量，`RobotControl()` 与四个 FSM 状态改读意图（`SeenIntents`：进状态清零、每周期累积，"在该状态下按下过就算"）；`library/core` 一字未改，其 `Input` 不再参与状态转移。**这一层取代了 P1-e / P1-g / P1-h 三条补丁**：边沿是纯函数不需清除协议、组合就是多个 bit、不再有枚举别名 | [`porting.md`](porting.md) §2 第 17 条 + §6.2 的新语义、[`../../docs/learn/rl-sar.md`](../../docs/learn/rl-sar.md) §2 末段的偏离说明、[`experiments.md`](experiments.md) §7 的验证 | ✅ `input_map_selftest` 8 组全过（`ros2 run` 或 `colcon test --packages-select rl_sar`，都不接仿真/手柄）；锁存 hat+A、键位扫描 5 段+导航 2 次、键盘 pty 四段、混合输入弹回用例（1 次 RL 且停住）、`check_walk.py` 7/7 | 中 |
| **S4 时基改造** ✅ 2026-10-11 | 控制/推理改由 `/motor_state` 的 `sim_time` 定节拍（控制 5 ms、推理 20 ms 仿真时间，见 P1-c 的最终做法）；删掉 `loop_control`/`loop_rl`（只剩键盘那条 50 ms 墙钟循环）；`SetCommand()` 变更检测 + 100 ms 仿真时间心跳；`base.yaml` 的 `dt`/`decimation` 回到上游的 0.005/4；`check_walk.py` 加 `--realtime {true,false}`（全速时时间线按仿真时间推进）| `src/rl_sim.cpp`、`include/rl_sim.hpp`、`launch/rl_sim.launch.py`、[`scripts/agent_scripts/check_walk.py`](../scripts/agent_scripts/check_walk.py)、[`scripts/agent_scripts/check_feedback_clock.py`](../scripts/agent_scripts/check_feedback_clock.py)（新）、[`control-stack-rates.md`](control-stack-rates.md)（新）| ✅ 1x 7/7（策略周期 20.00 ms）、全速 25.28x 7/7、反馈时钟自检 2/2（停顿 1.5 s 只前进 3.5%）、`input_map_selftest` 8 组 | 大 |
| **S5 健壮性（安全相关）** | P2-g 四条：① 反馈陈旧检测（记最后一条 `/motor_state` 的 `sim_time`，超过 N 个策略周期 → WARN + 退回阻尼）；② 首帧门控；③ `/joy` 超时 + `frame_id == "joy_disconnected"` 日志；④ 「落后」可见化（仿真节点撞补步上限时告警、rl_sim 状态行加有效反馈率） | `src/rl_sim.cpp`、`include/rl_sim.hpp`、`@20261005_ros2/.../sim_node.cpp`（④） | `kill -STOP` 冻住仿真节点 → ≤1 s 出现 WARN 并退出 RL；`kill -CONT` 后行为明确；拔手柄 → 站住；两个自检仍全过；`../../docs/learn/runtime-timing.md` §14 的"建议"改成"已实现" | 中（新增状态判断，别误触发） |
| **S6 复核与交付** | 干净 clone 流程、更新本文件与 [`../README.md`](../README.md)、`git status` 确认无产物混入、把「文档联动清单」逐行勾掉 | 文档 | 三条自检 + 干净 clone 能编能跑 | 低 |
| **S7（触发式）** | 渲染/物理拆线程（P3-b）：只在开始做"重场景 / 更高光栅化精度"时做；**不要早于 S4**（否则调度要写两遍） | `@20261005_ros2/ws/src/quadruped_ros2/{viewer.hpp,src/sim_node.cpp}` | 见 [`../../docs/learn/runtime-timing.md`](../../docs/learn/runtime-timing.md) §13（1.00x、31 档速度、暂停/单步/复位、33 个显示开关、两个自检） | 高（新增线程 + GL 归属）；**触发条件量化**（2026-10-11 实测）：窗口 1280x720@60 Hz 下每帧 CPU 约 6.8~8.5 ms / 16.68 ms（物理 8 步约 0.34 ms + 渲染约 2.5 ms + ROS/传感器），整栈带窗口仍稳在 0.995~1.000x；因此触发线定为「每帧工作量 > 帧预算的 ~60%」或「要 120 Hz+ 渲染」或「场景显著变重（几何/接触大增）」——到了再做，方案是双 `mjData` + 锁只罩 `mjv_copyData`（`mujoco.h:256`，µs 级），并在做的前后各量一次 fps / 帧时 p95 / 实时率 |

**依赖与互斥**：S1/S2 都改 `fsm.hpp`，**串行做**；S2 的 yaml 字段是 S4 换算斜坡常数的基础；S3 与 S4 都改 `rl_sim.cpp`，S3 先做能让 S4 的 diff 更干净；**S5 放在 S4 之后**——S4 的 `sim_time` 触发逻辑天然就是陈旧检测的数据源（同一处代码、同一轮回归），反过来先做 S5 则要写两遍；S4 与 S7 在"物理节拍由谁定"上重叠，先 S4 后 S7，S7 时把 S4 的节拍整体搬进物理线程。P1-d（`torch_threads`）与 P3（其余"不做"项）不排期。

## 改代码时要顺带改的文档（防漏，2026-10-10 建立）

原则：**代码改了、表述跟着改**，同一句话只写一处。下表是"计划中的改动 → 会失效的文档位置"，动手时照着勾；发现新的失效点随时补进来。

| 阶段 | 会失效的表述（文件：位置） | 要改成 |
|---|---|---|
| ~~**S1** ① 不再 push `output_dof_tau_queue`~~ ✅ | [`../../docs/learn/rl-sar.md`](../../docs/learn/rl-sar.md) §5「`tau` 只进不出…处理方式有三种」、[`../../docs/learn/tbb.md`](../../docs/learn/tbb.md) §3 末句「只生产不消费（上游如此）」 | 标明"上游如此，本仓已改成不 push"，三种处理方式降为历史 |
| ~~**S1** ② `fsm.hpp` 改读局部副本~~ ✅ | [`porting.md`](porting.md) §7 第 3 处（已同步改成"**已修（P2-c）**"，`fsm.hpp:270` 取值、`:276`/`:280` 使用） | ✅ 两个自检 7/7 |
| ~~**S1** ③ 新增 `status_period_ms`~~ ✅ | [`../README.md`](../README.md) 的用法/参数段、[`porting.md`](porting.md) §4 的"参数"行（现在只有 `robot_name`/`joy_command_scale`）、[`experiments.md`](experiments.md) §6 的"每周期打一行" | 参数表加一行；状态行描述改成"按 `status_period_ms` 打印" |
| ~~**S2** `kd_passive`/`getup_pre_cycles`/`getup_cycles`/`getdown_cycles` 进 `base.yaml`~~ ✅ | [`porting.md`](porting.md) §3 的字段来源表（补四行 + "默认值 = 当前写死值"）、[`../../docs/learn/rl-sar.md`](../../docs/learn/rl-sar.md) §3 的"base 独有字段"一栏 | 表里补字段，并注明"上游没有这几个键，是本仓加的" |
| ~~**S3** 话题名统一为相对名~~ ✅ | [`porting.md`](porting.md) §4（已改成"已全部改成相对名"+ 单节点与两端一起搬的验证）、[`../README.md`](../README.md) 的导航模式段 | ✅ 默认名字不变（`ros2 topic list` 实测）；`-r __ns:=/robot1` 六个接口整体搬 |
| ~~**S3** README 补 `N`/`X` 与 `/cmd_vel`~~ ✅ | [`../README.md`](../README.md) 的操作段与「导航模式与 `/cmd_vel`」段、[`porting.md`](porting.md) §6.2 键位表多一行导航模式 | ✅ 文中例子与 `RunModel()` 的分支一致（ON 用 `/cmd_vel`） |
| ~~**P2-b** 检查器修好~~ ✅ | 本文件 P2-b 的理由（已改成"修前那两条是误报、原因是链接目标在扫描目录之外"）、检查器自身的三条改进 | ✅ 全仓 `check_md_links.py .`（66 个文件）0 断链 / 0 锚点 / 0 表格 / 0 引用块 |
| ~~**P2-e** 进 RL 前加同名项自检~~ ✅ | [`../../docs/learn/rl-sar.md`](../../docs/learn/rl-sar.md) §3 末句（现在写的是"要加护栏就在进 RL 前自己读一遍 base"）、[`porting.md`](porting.md) §3 的指针、[`../README.md`](../README.md) 的调参段 | 改成"本仓已加，行为是…"；并把"改 `config.yaml` 后重进 RL 即生效、`base.yaml` 要重启"写进 README |
| ~~**S4** 时基改造（**最重要**）~~ ✅ | ① [`../README.md`](../README.md):77 那句（已改成「全速现在是推荐用法」）、② `launch/rl_sim.launch.py` 开头与 `realtime` 参数说明、③ [`scripts/agent_scripts/check_walk.py`](../scripts/agent_scripts/check_walk.py) 的 docstring 与新增 `--realtime`、④ [`porting.md`](porting.md) §5 与 §7 表第 1 行、⑤ [`experiments.md`](experiments.md) §1/§5 与新增 §9、⑥ [`../../docs/learn/rl-sar.md`](../../docs/learn/rl-sar.md) §6、[`../../docs/learn/runtime-timing.md`](../../docs/learn/runtime-timing.md) §14.1 | 新增 [`control-stack-rates.md`](control-stack-rates.md)（频率总表，索引进根 `README.md`）、[`porting.md`](porting.md) §2 第 18 条；`experiments.md` §5 标为「S4 之前的记录」 |
| **S5** 健壮性（P2-g） | [`../../docs/learn/runtime-timing.md`](../../docs/learn/runtime-timing.md) §14.4 的「建议（未实施）」四条、§14.2 第 4/7 条（现在写的是「没有任何陈旧检测」）、本文件 P2-g | 改成「已实现 + 怎么验的（`kill -STOP` 的结果）」；§14.3 边界表里「反馈中断 / joy_node 死掉」两行从「无检测」改成「有检测」；**S5-1 已完成**（指令限位，见下面的安全审计一节）；**另外**：见「已知的小问题」里的跨任务发现（仿真侧看门狗不生效），所以 S5 还要**多一条**：rl_sim 侧加**墙钟兜底（deadman）**——反馈断流超过 N ms 就主动发一条阻尼指令（kp=0、kd=damp）+ WARN，否则仿真会一直沿用最后一条指令（它自己的看门狗不生效）。验收把 `check_feedback_clock.py` 扩展成「断流 → 狗转阻尼 + 有 WARN」；**再加**：`SetCommand()` 前对 `motor_command` 显式钳位（`q_des` 夹到关节软限位、`kp/kd` 夹到配置上限、`q_des` 加变化率限幅）——见 [`safety-limits.md`](safety-limits.md) §3 第 1 条 |
| **S7** 渲染/物理拆线程 | [`../../docs/learn/runtime-timing.md`](../../docs/learn/runtime-timing.md) §13（现在写成"设计草案/暂不实施"）、[`../../@20261005_ros2/docs/ros2-nodes.md`](../../@20261005_ros2/docs/ros2-nodes.md) §2（单线程 + 补齐）、本文件 P3-a/b | §13 改成"已实现 + 实测"；§2 改成"物理线程 + 渲染线程"并更新每帧构成 |
| 改 `src/rl_sim.cpp` / `policy/black/fsm.hpp` 的行数 | 全仓 `文件:行` 引用都要重扫：`grep -rn "rl_sim\.cpp:[0-9]\|fsm\.hpp:[0-9]" docs @2026*`，再逐条核对（2026-10-11 就因为 P1-e/P1-g/S3 各插了几十行，`porting.md`/`tbb.md`/`runtime-timing.md`/`policy-model.md`/本文件里二十多条引用集体失效） | |

**频率总表已写**（S4 的产出之一）：[`control-stack-rates.md`](control-stack-rates.md)——每层多久跑一次、由谁定、改一个值会牵动什么，含 1x / 全速 / 暂停三种场景的实测与三条复核命令；根 `README.md` 的 `docs/learn/` 索引里已加一行。

## 提交建议

按 conventions §1.3 分阶段（**AI 不代为提交**）。S4 那一批（时基 + 语言统一 + 频率总表 + 检查器）已提交；**当前这批是 S5-1（控制器侧指令限位）**：

```bash
# ① 指令限位：纯函数 + 接进 SetCommand + 自检 + 5 个旋钮
git add @20261007_assignment/ws/src/rl_sar/include/command_limit.hpp \
        @20261007_assignment/ws/src/rl_sar/test/command_limit_selftest.cpp \
        @20261007_assignment/ws/src/rl_sar/src/rl_sim.cpp \
        @20261007_assignment/ws/src/rl_sar/include/rl_sim.hpp \
        @20261007_assignment/ws/src/rl_sar/policy/black/knobs.hpp \
        @20261007_assignment/ws/src/rl_sar/policy/black/base.yaml \
        @20261007_assignment/ws/src/rl_sar/CMakeLists.txt
git commit -m "feat(rl_sim): clamp the outgoing MIT command so a bad policy cannot over-actuate"

# ② 限位仪器 + 安全文档
git add @20261007_assignment/scripts/agent_scripts/check_limits.py \
        @20261007_assignment/docs/safety-limits.md
git commit -m "test(rl_sar): measure the limit margins and document what is actually enforced"

# ③ 被这一轮带动的表述
git add @20261007_assignment/README.md @20261007_assignment/docs/porting.md \
        @20261007_assignment/docs/status.md
git commit -m "docs(rl_sar): document the command-side limits and their calibration"
```

**提交前核对**：`git status --porcelain` 无产物；文档跑 `check_md_links.py .`（68 个文件）；代码跑 `input_map_selftest`、`command_limit_selftest`、`colcon test --packages-select rl_sar`（2/2）、`check_walk.py`（1x 与 `--realtime false` 都 7/7）。

**之后各阶段的提交**（每段做完再提交）：

| 阶段 | 提交信息（建议） |
|---|---|
| S5 剩余（deadman / 关节窗口 / `sim_node` 看门狗 1 行） | `feat(rl_sim): damp and warn when the feedback stream goes stale` |
| S6 | `docs(rl_sar): finalise the delivery notes and the doc checklist` |
| S7（触发式） | `perf(sim): move physics to its own thread and render from a snapshot` |
