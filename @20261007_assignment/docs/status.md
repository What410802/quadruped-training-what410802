# 推进情况

> 本文记"做到哪、待决什么、下一步"，会随推进改；入口与用法在 [`../README.md`](../README.md)。约定来源：[`../../docs/conventions.md`](../../docs/conventions.md) §2.6。

## 阶段状态

| 阶段 | 状态 | 证据 |
|---|---|---|
| 环境与工具链（libtorch / tbb / pytorch、clangd 23、单 pixi 环境） | ✅ 2026-10-08 | `best.pt` 在 C++ 与 Python 两侧加载一致；回归 `check_headless.py` 全过——[`../../docs/pitfalls/environment.md`](../../docs/pitfalls/environment.md) |
| 移植 rl_sar → rl_sim（框架层逐字、适配层改写、black 配置与状态机） | ✅ 2026-10-08 | 首次编译即过；逐文件改动见 [`porting.md`](porting.md) §2 |
| 验证：无头自检 / 干净 clone / 传统 ROS 2 方式 / 手柄接口 | ✅ 2026-10-08 | `check_walk.py` 7 项（`rest`/`raw`/干净 clone 各一次）、`check_headless.py` 全过；`env -i` 干净 shell（bash、zsh）从零编两个工作空间能跑——[`joystick.md`](../../@20261005_ros2/docs/joystick.md) §3、[`../README.md`](../README.md)「怎么跑」 |
| 文档：README + porting / experiments / policy-model / status（含状态转移图） | ✅ 2026-10-09 | [`policy-model.md`](policy-model.md)（`best.pt` 内部结构、参数量、三条实测坑）、[`porting.md`](porting.md) §6.2 |
| 复查与改动建议（P1/P2/P3）＋ 实施顺序 S1–S6 | ✅ 2026-10-10：P2-f（文件头声明）已实施，其余未实施 | 见下面「改动建议」「实施顺序」 |
| 交付前人工项 | ⏳ 实体手柄正负号复验 | 见「待人工确认」 |

## 已定的决策（2026-10-08）

- 移植底座：上游 `fan-ziqi/rl_sar` `e5c2f41`（大作业附件里那份）；主办方的 black 分支只作参照。
- 时钟：沿用上游的两条墙钟线程。实验表明实时运行时影响很小（速度 −4.5%、转向 +3%、不摔），原计划的"改成仿真时间驱动"不做；只约束 `realtime:=true`。→ **2026-10-09 复查**：当时结论仍成立（不影响验收），但把"要不要换成仿真步驱动"的方案、成本与验收方法补进了下面「改动建议」P1-c，供交付后再决定。
- 线程间不加锁：保留原样（5 分钟浸泡无异常）。→ **2026-10-09 复查**：前两处（消息副本、`robot_state`）结论不变、仍建议保留；第 3 处（Tensor 成员句柄）建议改一行，见 P2-c。
- `best.pt`（约 1 MB）入库。
- 本包代码沿用上游风格，放 `.clang-format`（`DisableFormat: true`）防止被重排；仓库的新 C++ 工程仍按 conventions §3.10 自带 100 列格式（方案 A）。

## 待人工确认

1. **实体手柄的正负号**：`joy_node` 的换算依据是内核驱动源码（`xpad.c`、`hid-input.c`），本机那台 Zikway 还没在新约定下复验。核实方法：`pixi run ros2 run quadruped_ros2 joy_node` 与 `pixi run ros2 topic echo /joy` 各开一个终端，左摇杆推上看 `axes[1]`、十字键按上看 `axes[7]`，都应为 **+1**。若不是，改 `@20261005_ros2/ws/src/quadruped_ros2/scripts/joy_node.py` 里的 `SLOT_SIGN`（rl_sim 不用动）。

（开窗口目视、VSCode/clangd 两项 2026-10-09 已由人工确认完成，不再列。）

## 已知的小问题（不阻塞）

- 参考实现里 0.5 m/s 指令只走到 0.36 m/s（1.0 与 1.5 m/s 都跟得上），原因没查（[`experiments.md`](experiments.md) §2）。
- `check_walk.py` 只能按真实时间跑（约 35 s），不能全速回归——墙钟方案的代价（experiments §5）；做了 P1-c 之后这条自动消失。

## 决定与计划（2026-10-09）

> **证据与调研细节不在本文**：rl_sar 的机制、键位出处、两份 yaml、三条队列、五套时基、框架层未用功能在 [`../../docs/learn/rl-sar.md`](../../docs/learn/rl-sar.md)；参数读取惯例在 [`../../docs/learn/ros2-params-and-launch.md`](../../docs/learn/ros2-params-and-launch.md) §7；渲染/物理拆线程的协议与实测在 [`../../docs/learn/runtime-timing.md`](../../docs/learn/runtime-timing.md) §13；本节点自身的接口与线程现状在 [`porting.md`](porting.md) §4/§7。本节只记"做什么、不做什么、为什么、落点、怎么验收"——截至 2026-10-10：**P2-f 已实施**（见下表），其余**全部未实施**。

| 编号 | 决定 | 一行理由 | 落点 | 验收 |
|---|---|---|---|---|
| **P1-a** | **做**：`kd_passive`、`getup_pre_cycles`/`getup_cycles`/`getdown_cycles` 写进 `base.yaml`，由 `policy/black/fsm.hpp` 自己读；`status_period_ms` 做成 rl_sim 的 ROS 参数 | 现值写死在代码里，实机起身时长与阻尼强度要能整定；**不做运行期热改**（培训方三处工程代码都只在启动时读参数） | `policy/black/base.yaml`、`policy/black/fsm.hpp`、`src/rl_sim.cpp` | 改 yaml 重启后行为确实变；两个自检逐项不变 |
| **P1-b** | **做（一行）**：不再 push `output_dof_tau_queue` | 上游自 v2.3 起就没人 pop，队列无界 → 长跑持续涨；我们也不用 `output_dof_tau` | `src/rl_sim.cpp:311-314` | 两个自检逐项不变 |
| **P1-c** | **候选，交付后再定**：两条墙钟热循环改成由反馈驱动——**每条 `/motor_state` 跑一次控制、按 `sim_time` 增量 ≥ 20 ms 触发一次推理**（A1 的更稳写法：不数条数，抗丢包、也不怕 `publish_every > 1`；数条数只在"步长恒 2 ms 且一条不丢"时等价） | 策略周期在仿真时间里 20.76 → 20.0 ms；暂停/慢放/快放自动正确；状态机斜坡跟仿真时间；**`realtime:=false` 从"3 倍就摔"变成可用**（现在快放 3 倍时仿真时间里的策略周期是 60 ms，[`experiments.md`](experiments.md) §5；改造后恒为 20 ms，速度上限只剩 CPU：推理实测 0.08 ms/次、物理 43 µs/步，都不是瓶颈）。代价是重写线程段 + 全部数字重测 | `src/rl_sim.cpp`、`include/rl_sim.hpp`、`policy/black/fsm.hpp`、`base.yaml` | 见「实施顺序」S4 |
| **P1-d** | **记录，暂不改**：`torch::set_num_threads(4)` 可以改成 ROS 参数 `torch_threads`（默认 4 = 今天的行为，`0` = 不调用、交给 libtorch/环境变量），但**先不动** | 机器相关的性能开关不该写死在代码里。**注意它是上游的写法、不是我们加的**：主办方分支每个通信文件都写死 4（`src/rl_sim.cpp:227`、5 个 `rl_real_*.cpp:44`），我们照抄在 `src/rl_sim.cpp:50`——所以这是"有意偏离上游"，要记进 [`porting.md`](porting.md) §2 的清单。实测推理 0.08 ms/次、1 线程与 8 线程一样，它不在关键路径上，但"写死 4"会误导 | `src/rl_sim.cpp:50`（若改） | 验收：`ros2 param get /rl_sim torch_threads` 能读到 + 设 `0`/`8` 各跑一次 `check_walk.py` 不劣化 |
| **P2-a** | `/control_status` 断链**记录不改**；话题名**统一为相对名**；`/cmd_vel` **保留**并补文档 | 断链那条本次任务没要求、手柄收反馈也没有动作价值；相对名才能在 `--namespace` 下整体搬；`/cmd_vel` 是唯一的非手柄指令通路 | `src/rl_sim.cpp`（话题名）、[`../README.md`](../README.md)、[`porting.md`](porting.md) §4 | `--namespace` 起一次确认接口；README 补 `N`/`X` 与 `ros2 topic pub /cmd_vel` 例子 |
| **P2-b** | **做**：`check_md_links.py` 的标题扫描支持引用块标题（`^\s*>?\s*#{1,6}\s+`，并去掉行首 `>` 与实参里的 `*`/`_`） | 它不是外部库、是本仓脚本；现在全仓那两条"锚点找不到"（`@20261007_assignment/README.md`、`@20261005_ros2/README.md` 指向根 README 的传统 ROS 2 方式一节）都是误报 | `@20260927_motor/scripts/agent_scripts/check_md_links.py` | 全仓跑一遍 0 告警 |
| **P2-c** | **只改第 3 处（一行）**：fsm 读 `_output_dof_pos`/`_output_dof_vel` 而不是成员；前两处保留 | 三处都无锁；前两处数据不重分配、最坏只混入相邻一帧；第 3 处涉及 Tensor 句柄，改完还能保证 pos/vel 同帧 | `policy/black/fsm.hpp:222` | `check_walk.py` 7/7 |
| **P2-d** | 键位差异**不改代码**：README 的操作说明就是我们的键位出处 | 与主办方只差"趴下"一处（我们 `B` = 上游写法），整套键位有上游 README 参考表支撑 | [`../README.md`](../README.md)（顺带补 `N`/`X`） | 目视核对 README 列全 |
| **P2-e** | **做**：`fsm.hpp` 自读 `base.yaml`，与 `himloco/config.yaml` 的 7 个同名项比对，不一致就 WARNING；**初始化时查一次，每次进 RL 再查一次** | 同名项是"分时刻生效"，不一致不会报错、只会变样（上游 go2 的 80/3 vs 60/5、23.5 vs 33.5，主办方 black 的站姿 0.82/−1.5 vs 0.8014/−1.527 都是真实实例）；而且 `config.yaml` **每次进 RL 都被重新读**（`Enter()` → `InitRL()` → `ReadYamlRL()`，`policy/black/fsm.hpp:198`），只查初始化会漏掉"中途改文件再重进 RL"——这同时是一条可用的调参路径：改 `config.yaml` 后重进 RL 即生效，改 `base.yaml`（构造时读一次）则要重启。副作用要写进 README：kp/kd 变化会在切入 RL 那一刻跳一下，`joint_mapping`/`num_of_dofs` 更不该中途改 | `policy/black/fsm.hpp` | 故意改一个值：初始化时打出一次 WARNING，重进 RL 再打一次 |
| **P2-f** | ✅ **已实施（2026-10-10）**：4 个改写过的文件头压成 3 行内容（`Copyright` + `SPDX` + `Modified for … from rl_sar e5c2f41 <上游路径>` / `Change list: porting.md §2`），明细只在 [`porting.md`](porting.md) §2 维护；逐字复制的 `library/core/**` 未动；新写文件不加声明（与本仓既有新文件一致，许可由包内 `LICENSE` 覆盖） | 同一份清单原先有两处（4 个文件头共 38 行），而 Apache-2.0 §4(b) 只要求"显著的修改声明"，一行足够；整块移进文档反而会弱化这条 | `src/rl_sim.cpp`、`include/rl_sim.hpp`、`policy/fsm.hpp`、`policy/black/fsm.hpp`（38 → 24 行） | 编译过 + `check_walk.py` 7/7（改动只有注释）；`porting.md` §2 的表 + 7 条清单覆盖被删掉的每一条 |
| **P2-g** | **建议做（安全相关，未做）**：① `rl_sim` 加**反馈陈旧检测**（记最后一条 `/motor_state` 的 `sim_time`/到达时刻，超过 N 个策略周期没更新 → WARN + 退回阻尼）；② 首帧门控（收到第一条反馈前不推理）；③ `/joy` 超时（>0.5 s 无消息 → 清 `control`）并在 `frame_id == "joy_disconnected"` 时打一行；④ 把"落后"变可见（仿真节点撞补步上限时告警；rl_sim 状态行加"有效反馈率"） | 现状**反馈方向完全没有超时**：仿真节点挂住时 rl_sim 会一直拿最后一帧推理并发命令，没人会发现；`joy_node` 进程死掉同理会一直用最后一帧（拔掉设备那条已经安全：joy_node 会归零并继续发）。指令方向有仿真侧看门狗兜底，唯独这两条没有。逐条分析与边界见 [`../../docs/learn/runtime-timing.md`](../../docs/learn/runtime-timing.md) §14 | `src/rl_sim.cpp`、`include/rl_sim.hpp`（④ 另涉 `sim_node.cpp`） | 用 `kill -STOP` 冻住仿真节点：≤1 s 内出现 WARN 并退出 RL/退回阻尼，`kill -CONT` 后行为明确（回 RL 或要求重启）；两个自检仍全过 |
| **P3** | **不做**（记录在案）：`fixed_kp`/`fixed_kd`/`rl_kp`/`rl_kd` 的 ROS 覆盖；`config_name` 参数化；三轴指令限幅；`tilt_warn_deg` 接 `AttitudeProtect()`；力矩保护；`motiontime`、`simulation_running` 等死代码；matplotlib/PLOT 恢复；运行期热改；策略路径的 `policy_root`（不影响仓库可复现性） | 要么要动 `library/core`，要么验收前不必要；逐条理由与替代方案见 [`../../docs/learn/rl-sar.md`](../../docs/learn/rl-sar.md) §4/§7/§8 | — | — |
| **P3-a/b** | **触发式**：渲染/物理拆线程（物理按仿真步定节拍 + 渲染独立），现在不做 | 今天 1.00x、物理只占帧预算 2%，拆线程换来的是"隔离"而不是帧率；等做重场景或更高光栅化精度那一轮 | `viewer.hpp`、`sim_node.cpp` | 见 [`../../docs/learn/runtime-timing.md`](../../docs/learn/runtime-timing.md) §13 |

**P1-d 的性能开关盘点**（2026-10-10 全仓扫了一遍 `set_num_threads|OMP/MKL_NUM_THREADS|hardware_concurrency|num_threads|bindCPU|setThreadAffinity|parallel-workers`；代码里真正的"性能写死"只有一处，其余都是有意为之）：

| 位置 | 现值 | 性质 | 决定 |
|---|---|---|---|
| [`../ws/src/rl_sar/src/rl_sim.cpp:50`](../ws/src/rl_sar/src/rl_sim.cpp) `torch::set_num_threads(4)`（上游写法：主办方分支 `src/rl_sim.cpp:227` 与 5 个 `rl_real_*.cpp:44` 都是 4） | 4 | libtorch 推理线程池大小 | **暂不改**；真要改就做成参数 `torch_threads`（默认 4），并把「偏离上游写法」记进 [`porting.md`](porting.md) §2 |
| `src/rl_sim.cpp:49` `GradMode::set_enabled(false)` | off | 关 autograd | 留（纯收益） |
| `src/rl_sim.cpp:82-88` 三条 `LoopFunc` 不传 `bindCPU` | -1（不绑核） | CPU 亲和（[`loop.hpp:23/30/33/103`](../ws/src/rl_sar/library/core/loop/loop.hpp) 已实现） | **先不做**：S4 要重写这段线程结构，绑核等那时一起定（要绑也得先量抖动） |
| `src/rl_sim.cpp:88` 键盘循环 0.05 s | 20 Hz | 输入轮询率 | 留（写死但无收益） |
| [`@20261005_ros2/…/sim_node.cpp`](../../@20261005_ros2/ws/src/quadruped_ros2/src/sim_node.cpp) `kMaxCatchupSteps = 200`、`kMaxLagSeconds = 0.2` | 200 步 / 0.2 s | 过载策略（渲染顶住物理的上限） | 记录：与 P3-b 的"降速告警"是同一件事，做 P3-b 时一起参数化 |
| 同文件 `kViewerWidth/Height = 1280×720` | 写死 | 窗口尺寸 = 渲染成本 | 可参数化（`viewer_width/height`），属 P3-a 的画质一族；**三项画质（shadow / msaa / render_scale）已经是参数** |
| [`viewer.hpp:58/60`](../../@20261005_ros2/ws/src/quadruped_ros2/include/quadruped_ros2/viewer.hpp) `kDefaultMsaa = 4`、`kDefaultRenderScale = 2` | 4 / 2× | 画质默认值 | 留（只是默认值，运行期由 sim_node 参数覆盖） |
| MuJoCo 侧 | 单线程 `mj_step`；`mju_threadpool` 未用；`<option timestep=…>` 在 XML 里 | 物理并行度 | **不用**：本模型 43 µs/步，单线程远够；要用得先在模型里做 island 并行 |
| 构建 | `CMAKE_BUILD_TYPE=Release`（未设时，[`CMakeLists.txt:12`](../ws/src/rl_sar/CMakeLists.txt)）；并行度交给 colcon 默认 | 编译优化 | 留（脚本里没写死 `-j`；pixi 环境也没设 OMP/MKL/TBB 变量） |

## 实施顺序（2026-10-09 定；提交后从 S1 开始）

原则：**按文件分组、风险从零到有**；每步都能用现成的两个自检（`check_walk.py`、`check_headless.py`）单独验收；改到 `library/core` 的**一条都不做**（P1-c 首选方案也不需要）。S1–S3 互不冲突（各改各的文件），S4 是唯一的结构性改动，S5 是收尾。

| 阶段 | 做什么（对应上面的条目） | 动哪些文件 | 验收 | 风险 |
|---|---|---|---|---|
| **S1** | 零行为风险的三处清理：① 不再 push `output_dof_tau_queue`（P1-b ②）；② `fsm.hpp:222` 改读 `_output_dof_pos`/`_output_dof_vel`（P2-c）；③ `status_period_ms` 参数 + 按周期打状态行（P1-a 第三条） | `ws/src/rl_sar/src/rl_sim.cpp`、`include/rl_sim.hpp`、`policy/black/fsm.hpp` | `check_walk.py`（7/7，逐项与基线一致）、`check_headless.py`（7/7） | 无（不改控制律） |
| **S2** | 可调参数（P1-a 前两条）：`kd_passive`、`getup_pre_cycles`/`getup_cycles`/`getdown_cycles` 写进 `base.yaml`，由 `policy/black/fsm.hpp` 自己读（照主办方读 `retry_mode.yaml` 的写法） | `policy/black/base.yaml`、`policy/black/fsm.hpp` | 同上 + 改 yaml 后重启，量起身时长/阻尼强度确实变了 | 低（默认值 = 现值；错读要有兜底） |
| **S3** | 文档与自检收尾：① README 补 `N`/手柄 `X` 导航模式 + `ros2 topic pub /cmd_vel` 例子（P2-a/P2-d）；② 话题名统一为相对名（P2-a）；③ 修 `check_md_links.py` 的引用块标题（P2-b）并跑全仓。**两份 yaml 的分工表已在 2026-10-09 的文档迁移里写进 [`../../docs/learn/rl-sar.md`](../../docs/learn/rl-sar.md) §3，这里只剩在 [`porting.md`](porting.md) §3 加一句指针** | `README.md`、`docs/porting.md`、`src/rl_sim.cpp`（话题名）、`@20260927_motor/scripts/agent_scripts/check_md_links.py` | `check_md_links.py` 全仓 0 告警；`check_walk.py` 仍 7/7 | 低（③ 改话题名要确认 `--namespace` 下也对） |
| **S4** | 时基改造（P1-c 方案 A1）：两条墙钟热循环换成 `/motor_state` 驱动（每条 = 一次控制；`sim_time` 增量 ≥ 20 ms = 一次推理），`base.yaml` 的 `dt`/`decimation` 相应调整，fsm 斜坡常数按 2 ms 换算 | `src/rl_sim.cpp`、`include/rl_sim.hpp`、`policy/black/fsm.hpp`、`policy/black/base.yaml` | `check_walk.py`（策略周期均值 20.0、p95 20）、`check_headless.py`、`--start raw/rest` 各一次、**`realtime:=false` 全速下 3x/5x 不摔**（现在是 60/100 ms 仿真周期 → 摔）、暂停 2 s 后起身仍 3 s 仿真时间；**重测并更新 [`experiments.md`](experiments.md) 的旧数字，并按下节清单改文档** | 中高（改线程模型；数字全要重测） |
| **S5** | 复核与交付：跑干净 clone 流程、更新本文件与 [`../README.md`](../README.md)、`git status` 确认无产物混入 | 文档 | 三条自检 + 干净 clone 能编能跑 | 低 |
| **S6（触发式）** | 渲染/物理拆线程（P3-b）：只在开始做"重场景 / 更高光栅化精度"时做；**不要早于 S4**（否则调度要写两遍） | `@20261005_ros2/ws/src/quadruped_ros2/{viewer.hpp,src/sim_node.cpp}` | 见 [`../../docs/learn/runtime-timing.md`](../../docs/learn/runtime-timing.md) §13 的验收（1.00x、31 档速度、暂停/单步/复位、33 个显示开关、两个自检） | 高（新增线程 + GL 归属） |

依赖与互斥：S1/S2 都改 `fsm.hpp`，**串行做**（避免同文件冲突）；S2 的 yaml 字段是 S4 换算斜坡常数的基础；S3 的话题名改动与 S4 同改 `rl_sim.cpp`，可以先做 S3 让 S4 的 diff 更干净。P1-c（S4）与 P3-b（S6）在"物理节拍由谁定"上重叠——先 S4 后 S6，S6 时把 S4 的节拍整体搬进物理线程。

## 改代码时要顺带改的文档（防漏，2026-10-10 建立）

原则：**代码改了、表述跟着改**，同一句话只写一处。下表是"计划中的改动 → 会失效的文档位置"，动手时照着勾；发现新的失效点随时补进来。

| 阶段 | 会失效的表述（文件：位置） | 要改成 |
|---|---|---|
| **S1** ① 不再 push `output_dof_tau_queue` | [`../../docs/learn/rl-sar.md`](../../docs/learn/rl-sar.md) §5「`tau` 只进不出…处理方式有三种」、[`../../docs/learn/tbb.md`](../../docs/learn/tbb.md) §3 末句「只生产不消费（上游如此）」 | 标明"上游如此，本仓已改成不 push"，三种处理方式降为历史 |
| **S1** ② `fsm.hpp` 改读局部副本 | [`porting.md`](porting.md) §7 第 3 处（现在写"取了一份副本却没用"）、§7 的复查结论 | 改成"已读 `_output_dof_pos`/`_output_dof_vel`（P2-c）；前两处仍保留" |
| **S1** ③ 新增 `status_period_ms` | [`../README.md`](../README.md) 的用法/参数段、[`porting.md`](porting.md) §4 的"参数"行（现在只有 `robot_name`/`joy_command_scale`）、[`experiments.md`](experiments.md) §6 的"每周期打一行" | 参数表加一行；状态行描述改成"按 `status_period_ms` 打印" |
| **S2** `kd_passive`/`getup_pre_cycles`/`getup_cycles`/`getdown_cycles` 进 `base.yaml` | [`porting.md`](porting.md) §3 的字段来源表（补四行 + "默认值 = 当前写死值"）、[`../../docs/learn/rl-sar.md`](../../docs/learn/rl-sar.md) §3 的"base 独有字段"一栏 | 表里补字段，并注明"上游没有这几个键，是本仓加的" |
| **S3** 话题名统一为相对名 | [`porting.md`](porting.md) §4「话题名的前缀…要统一建议全部用相对名」、[`../README.md`](../README.md) 的话题清单、`launch/rl_sim.launch.py` 的说明 | 改成"已统一"；用 `--namespace` 起一次验证 |
| **S3** README 补 `N`/`X` 与 `/cmd_vel` | [`../README.md`](../README.md) 的"操作"段（现在只有 A/B/X 与复位） | 补导航模式与 `ros2 topic pub /cmd_vel` 例子（与 [`porting.md`](porting.md) §4 互指） |
| **P2-b** 检查器修好 | 本文件 P2-b 的理由、[`../README.md`](../README.md):41 那条链接、[`../../@20261005_ros2/README.md`](../../@20261005_ros2/README.md):67 | 两处误报消失后，删掉"已知误报/锚点找不到"的说法（连带本文件「提交建议」里的自检说明） |
| **P2-e** 进 RL 前加同名项自检 | [`../../docs/learn/rl-sar.md`](../../docs/learn/rl-sar.md) §3 末句（现在写的是"要加护栏就在进 RL 前自己读一遍 base"）、[`porting.md`](porting.md) §3 的指针、[`../README.md`](../README.md) 的调参段 | 改成"本仓已加，行为是…"；并把"改 `config.yaml` 后重进 RL 即生效、`base.yaml` 要重启"写进 README |
| **S4** 时基改造（**最重要**） | ① [`../README.md`](../README.md):59「**不要用 `realtime:=false`**…快 3 倍以上狗就会摔」；② `launch/rl_sim.launch.py`:16 同一句；③ [`scripts/agent_scripts/check_walk.py`](../scripts/agent_scripts/check_walk.py):7 的"按墙钟每 20 ms 推理一次"；④ [`porting.md`](porting.md) §5（两条墙钟线程、5 ms/20 ms）与 §7 表第 1 行；⑤ [`experiments.md`](experiments.md) §3–§5（20.76 ms、"快放到 3 倍会摔"、`--period-ms` 那组）与 §7 表里两行"保留原样"；⑥ [`../../docs/learn/rl-sar.md`](../../docs/learn/rl-sar.md) §6 的"改法"；⑦ `check_walk.py` 的周期提示（20.69 → 20.0） | 全部改成"按反馈 / `sim_time` 增量驱动"；`realtime:=false` 从"禁止"变成"支持，上限由 CPU 决定"；`experiments.md` 旧数字标注成"墙钟方案的实测（历史）"并补新数；本文件 P1-c/阶段状态同步 |
| **S6** 渲染/物理拆线程 | [`../../docs/learn/runtime-timing.md`](../../docs/learn/runtime-timing.md) §13（现在写成"设计草案/暂不实施"）、[`../../@20261005_ros2/docs/ros2-nodes.md`](../../@20261005_ros2/docs/ros2-nodes.md) §2（单线程 + 补齐）、本文件 P3-a/b | §13 改成"已实现 + 实测"；§2 改成"物理线程 + 渲染线程"并更新每帧构成 |

**待写的文档（S4 之后）**：本仓**没有**一份集中讲"我们的控制栈每层频率"的文档——现在只散在四处：[`../../@20261005_ros2/docs/ros2-nodes.md`](../../@20261005_ros2/docs/ros2-nodes.md)（物理 500 Hz / 反馈 500 Hz、看门狗 100 步 = 200 ms 仿真时间）、[`porting.md`](porting.md) §5（控制 5 ms、策略 20 ms）、[`../../docs/learn/rl-sar.md`](../../docs/learn/rl-sar.md) §6（五套时基）、[`../../docs/learn/runtime-timing.md`](../../docs/learn/runtime-timing.md) §13（线程方案）。计划：**时基改造完成后**写一份仓库级 `docs/learn/control-stack-rates.md`（现在还没建，所以这里先不写成链接、免得起断链）——每层频率 + 各自的时间轴 + 谁定节拍 + 过载时的表现（谁先掉队、怎么看）——把上面四处指过去，并在根 [`README.md`](../../README.md) 的文档索引里登记；建好后把本行的路径改成链接。

## 提交建议

按 conventions §1.3 分阶段（**AI 不代为提交**）。下面这版按 **2026-10-09 的实际 `git status`** 核过：

- **已提交**：① `dca0160`（pixi + libtorch/tbb/pytorch + clangd）、② `e8e98ec`（build 脚本）、③ `cceb7d0`（gitignore）、④ `89539fc`（手柄符号约定，已按建议**不含** `@20261005_ros2/README.md`）。
- **已 staged，可直接提交**：⑤ 包本体（`@20261007_assignment/ws/src/rl_sar`，18 个文件，含 `best.pt` 991 KB；`build/install/log/.cache` 全被忽略）。
- 原清单的两处过时已修正：`@20261007_assignment/.gitignore` **不存在**（`git add` 会整条报错），`docs/pitfalls/environment.md`、`docs/learn/cmake-intellisense.md` 等已在 `dca0160` 里。

```bash
# ① dca0160 / ② e8e98ec / ③ cceb7d0 / ④ 89539fc 已提交，不用再动

# ⑤ 包本体：已 staged，直接提交（25 个文件里的 18 个；含 best.pt 991 KB）
git commit -m "feat(rl_sar): port rl_sar to drive the ros2 sim node with the best.pt policy"

# ⑥ 自检脚本
git add @20261007_assignment/scripts
git commit -m "test(rl_sar): add a headless walk check and a lockstep policy reference"

# ⑦ 任务文档（README + porting/experiments/policy-model/status 五份）
git add @20261007_assignment/README.md @20261007_assignment/docs
git commit -m "docs(rl_sar): document the port, interfaces, policy model and plans"

# ⑧ 根 README + 上一任务的 README：都是"传统 ROS 2 方式"那一件事，合成一次
#    （根 README 引用 @20261007_assignment，所以排在 ⑤–⑦ 之后）
git add README.md @20261005_ros2/README.md
git commit -m "docs: add the plain ROS 2 workflow and register the assignment"

# ⑨ 约定补充（任务间依赖、SI 单位、环境里的 clang-format）
git add docs/conventions.md
git commit -m "docs(conventions): record task dependencies, the SI unit rule and the env clang-format"

# ⑩ 拆线程那条结论的探针（调查用仪器，按 conventions §3.7 放 agent_scripts）
git add @20260923_mujoco/scripts/agent_scripts/snapshot_copy_bench.cpp
git commit -m "test(mujoco): add the snapshot-copy probe behind the thread-split note"

# ⑪ 学习文档：rl_sar 速查（新）、TBB 笔记（新）、参数与 YAML 一节、时序图整理与拆线程协议、cpp-cmake/mujoco 排错
git add docs/learn/rl-sar.md docs/learn/tbb.md docs/learn/ros2-params-and-launch.md \
        docs/learn/runtime-timing.md docs/learn/cpp-cmake.md docs/learn/mujoco.md
git commit -m "docs(learn): add the rl_sar and tbb notes, the params-vs-yaml section and the thread-split protocol"
```

**提交前的核对（已做过一遍，结论：干净）**：

- `git add -An @20261007_assignment` = **25 个文件**（其中 ⑤ 的 18 个包文件 + ⑥⑦ 的脚本与文档），其中唯一的 >50 KB 文件是 `best.pt`（991679 B，入库是既定决策）；`ws/build`、`ws/install`、`ws/log`、`ws/.cache`、`output/log`、`__pycache__` 全部被忽略（逐一 `git check-ignore` 验过）。
- 这些文件里**没有** `/home/…`、`ReadOnly.d`、`Replicate.d` 之类仓库外路径（conventions §4.6/§4.7 的自查）。
- 建议在 ⑤ 之前跑一遍：`pixi run ros2-build`、`pixi run python @20261007_assignment/scripts/agent_scripts/check_walk.py`、`pixi run python @20261005_ros2/scripts/agent_scripts/check_headless.py`、`pixi run python @20260927_motor/scripts/agent_scripts/check_md_links.py @20261007_assignment`。
- ⚠ `@20261007_assignment/ws/log/build_*/events.log`（被忽略，不会入库）里是 colcon 的**完整环境变量转储**，含 `ANTHROPIC_AUTH_TOKEN=sk-…`；别用 `git add -f` 或整目录打包去碰它。
