# 控制栈频率总表（我们这条 ROS 2 链路）

这份文档回答一个问题：**我们这套控制栈，每一层多久跑一次、由谁定、改一个值会牵动什么。**
上游 rl_sar 自己的五套时间基（`dt`、`decimation`、观测历史 6 帧、`motiontime`、`episode_length_buf`）见 [`rl-sar.md`](../../docs/learn/rl-sar.md) §6；这里只讲**我们的链路**（`@20261005_ros2` 的 `sim_node` + `@20261007_assignment` 的 `rl_sim`）。
数字是 2026-10-11 在本机（Ubuntu 24.04 + MuJoCo 3.12 + libtorch 2.12）实测的，命令都在 §6。

## 1 两种钟：仿真时间与墙钟

S4（`@20261007_assignment/docs/porting.md` §5）之后，**控制栈的主时钟是仿真时间**（= MuJoCo 的 `d->time`，由 `/motor_state.sim_time` 带过来）：

| 按**仿真时间**走（S4 起） | 按**墙钟**走（有意为之） |
|---|---|
| 控制周期 `dt` = 5 ms | 仿真自身的实时配速（`realtime:=true` 时按真实时间走；`false` = 全速） |
| 策略周期 `dt × decimation` = 20 ms | 键盘轮询 50 ms（`LoopFunc`，唯一剩下的墙钟循环） |
| FSM 斜坡（`getup_pre/up/down_cycles`） | 状态行打印（`status_period_ms`） |
| `/mit_command` 心跳（100 ms 仿真时间一条） | 查看器刷新（自建窗口，与物理线程解耦；`viewer:=false` 时完全不跑） |
| 推理节拍（`ControlStep()` 里按 `sim_time` 对齐） | 手柄节点发布 `/joy` 的 100 Hz（`joy_node.py` 的 `rate_hz`） |

判据很简单：**暂停（没有反馈）时，上表左列一步都不跑；右列照跑**。这条由 `scripts/agent_scripts/check_feedback_clock.py` 守着（§5）。

## 2 频率总表

| 层 | 名义频率（仿真时间） | 1x 运行时的墙钟 | 由谁定 | 约束 / 备注 |
|---|---|---|---|---|
| MuJoCo 物理步 | 500 Hz（2 ms/步） | 500 Hz | 模型 `opt.timestep`（`scene_ground_extents` 那类场景脚本也按它） | `mj_step` 实测 38–44 µs（[`runtime-timing.md`](../../docs/learn/runtime-timing.md) §13） |
| `/motor_state` 反馈 | 500 Hz | 500 Hz | `sim_node` 的 `publish_every`（默认 1 = 每步） | **必须不慢于控制周期**，否则控制被反馈拖长（`publish_every` ≤ 2） |
| `/imu` | 500 Hz | 500 Hz | 同上 | 策略每次推理取最新一条（不缓存历史） |
| `rl_sim` 控制 | 200 Hz（5 ms） | 200 Hz | `base.yaml` 的 `dt` | 由反馈的 `sim_time` 补步：正常一条反馈一步，丢包时最多补 10 步再重新对齐 |
| 策略推理 | 50 Hz（20 ms） | 50 Hz | `dt × decimation`（= HIMLoco 训练时的 20 ms，**不能改**） | 实测 20.00 ms（1x）、20.51 ms（25x）；[`policy-model.md`](policy-model.md) §4 那张表的「周期」行对应这里 |
| `/mit_command` | 目标变化时立即发；不变时每 20 个控制周期（100 ms）一条心跳 | 同上 | `src/rl_sim.cpp` 的 `SetCommand()` 变更检测 | ⚠ 仿真侧看门狗**当前不生效**（见 §4 的跨任务发现），心跳是按「设计意图 200 ms 的一半」留的 |
| `/joy` → 意图 | 边沿，按控制周期消费 | 手柄 100 Hz | `joy_node.py` 的 `rate_hz` | 边沿由 rl_sim 自己从连续帧推（[`input_map.hpp`](../ws/src/rl_sar/include/input_map.hpp)） |
| `/cmd_vel` | 外部任意 | — | 导航模式（`X` / `N` 切换）时读 | 导航模式下摇杆被忽略 |
| 状态行（rl_sim） | — | `status_period_ms`（默认 0 = 关） | ROS 参数 | 打开后每次控制周期检查一次时间，够不上就跳过 |
| 状态行（sim_node） | — | 每 5 s 墙钟一行 | `status_period_s` | 打 `仿真 X s / 墙钟 Y s = Zx 实时；N 步，发反馈 M 条` |

一句话版：**物理 500 Hz → 控制 200 Hz → 策略 50 Hz**，反馈最快、策略最慢，三者都锚在仿真时间上。

## 3 为什么要把控制栈挂到仿真时间（S4 的实测）

| 场景 | S4 之前（两条墙钟循环） | S4 之后（反馈驱动） |
|---|---|---|
| 1x 实时 | 策略周期均值 20.65–20.80 ms（墙钟 5 ms/20 ms 与仿真的 2 ms 步长不同步，实测 20.76 ms） | **20.00 ms**（p5/p95 都是 20.0，998 次里 0~1 次超 30 ms——偶发一次 32 ms，是宿主机的调度毛刺） |
| 全速 `realtime:=false` | 文档记录：3x 就摔 | **22~25x**（带检查脚本，多次实测）下 7/7 全过，策略周期 20.5~25.6 ms；栈自身 **39–42x**（§6 的命令 ④） |
| 暂停（仿真冻结） | 两条墙钟循环照跑 → 斜坡继续推进（1.5 s 能推进 ~75%） | 一步都不跑：SIGSTOP 1.5 s 只前进 3.5%（在途反馈），`SIGCONT` 后接着跑 |
| 慢放 | 同样是"墙钟每 20 ms"，仿真时间里的周期被拉长 | 不受影响（周期按仿真时间定义） |

第三条是 S4 的核心收益：**暂停时不再"空转着把动作做完"**，这对"人在窗口里按空格暂停着调"这种用法是硬要求。

## 4 外部扰动会带来什么（CPU、网络、刷新率）

S4 之后一条总原则：**栈内的时间关系（控制 5 ms、推理 20 ms、斜坡 1/2/2.5 s）只由仿真时间决定，外部资源只影响「墙钟跑多快」。**
唯一的例外是反馈流本身变慢或断掉——那会直接改掉控制的有效节拍，属于安全项（S5）。

| 扰动 | 会发生什么 | 依据 |
|---|---|---|
| CPU 被抢 / 降频（rl_sim 或仿真被饿） | 反馈回调变稀：控制按 `sim_time` **补步**（最多 10 步 = 50 ms 仿真时间），超过就重新对齐；再久一点就「没有反馈 → 什么都不跑」。策略周期在仿真时间里不变 | `ControlStep()`；实测 rl_sim 被 `SIGSTOP` 1.5 s 时斜坡停在 12.00% 不动，`SIGCONT` 后接着走到 33.25% |
| 网络阻塞 / 反馈丢包（`/motor_state` 是 best_effort + KeepLast(1)） | 丢几帧无影响（按 sim_time 补步）；丢得多时控制周期被「能用到的 sim_time」拉长（实测 1x 下 998 次里有 0~1 次超 30 ms）。**不能靠丢包省事**：`publish_every` 必须 ≤ 2（4 ms ≤ `dt`） | §2、`check_walk` 的周期统计 |
| `/mit_command` 丢包 | 目标变化时发、不变时 100 ms 一条心跳，丢一条不影响（下一条会带同样的目标） | `SetCommand()` |
| 屏幕刷新率提高 / 渲染变重（`viewer:=true`） | 渲染与物理在同一条线程上（S7 之前）：渲染变重会**拖慢仿真在墙钟上的推进**，但仿真时间里的节拍不变——所以策略行为不变，只是墙上变慢。想要更快就 `viewer:=false` 或全速跑 | [`../../docs/learn/runtime-timing.md`](../../docs/learn/runtime-timing.md) §13/§14.1；实测全速 25x 仍 7/7 |
| **自己跑太快**（`realtime:=false` 不限速） | 本机 20~25x 时策略周期仍是 20.5 ms；再快（实测一次 22x、宿主更忙）时 rl_sim 的单执行器线程吃不下反馈流，控制只能按 `sim_time` 补步（每帧最多 10 步）→ 推理节拍在仿真时间里退化（实测均值 26.3 ms、p95 54 ms），**但起身/走/转/趴下仍全过**。另一个可见后果：反馈间隙超过补步上限（10 步 = 50 ms 仿真时间）时控制会跳过仿真时间，于是**斜坡在仿真时间里略微拉长**（起身可能比 3 s 久一点）。栈自身的上限约 39~42x（§6） | 实测；`check_walk.py --realtime false` 该项已按速度放宽判据 |
| 核更多 / 更少 | 物理在一条线程、rl_sim 的执行器一条线程；`torch::set_num_threads(4)` 是唯一写死的并行项（见 status 的 P1-d）。栈自身吞吐实测 39~42x，两条线程之外仍有余量 | §6 |

**跨任务发现（2026-10-11，未修）**：仿真侧那句「200 ms 没收到 `/mit_command` 就退回阻尼」**当前不生效**。`sim_node.cpp:808` 是 `stale = !got || (steps - last_cmd_step) > timeout_steps`，而 `TakeCommand()` 是「只要收到过一次就每次返回 true」，于是 `if (got) last_cmd_step = steps;` 每步都在刷新时间戳，差值恒为 0。实测：`SIGSTOP` rl_sim 1.5 s（≈750 步 ≫ 100 步）期间状态行一直是 `cmd=ok`，没有任何看门狗打印。修法是一行——把 `last_cmd_step` 改成在 `/mit_command` 的订阅回调里更新——但那属于上一个任务的节点，本次只记录；本任务 S5 的「反馈陈旧检测 + 退回阻尼」要独立兜底，因为反馈一断、rl_sim 就一步都不跑，连阻尼指令也发不出去。

## 5 改一个值会牵动什么

| 想改 | 能不能改 | 牵动 |
|---|---|---|
| `base.yaml` 的 `dt` | 能，但 `dt × decimation` 必须保持 20 ms | FSM 的 `*_cycles` 按控制周期计数，要同步换算（`getup_pre_cycles`/`getup_cycles`/`getdown_cycles`）；`porting.md` §2 第 18 条 |
| `base.yaml` 的 `decimation` | 同上 | 同上（它只决定"几个控制周期推一次策略"） |
| `sim_node` 的 `publish_every` | ≤ 2 | 让反馈周期 > 控制周期会**悄悄**把控制拖慢（控制靠反馈的 `sim_time` 补步，反馈太慢就没有新时间可补） |
| 模型的 `opt.timestep` | **不要动** | 策略按 20 ms 训练、增益/滤波都按它调过；改它等于换一套动力学 |
| `status_period_ms` / `status_period_s` | 随便改 | 只影响打印（状态行本身在工作线程里做，默认关闭） |
| `torch::set_num_threads(4)` | 可做成参数 | 见 [`status.md`](status.md) 的 P1-d 盘点 |
| 键盘轮询 50 ms | 能 | 它是墙钟循环；键盘只有"最后一个键"这一种信息（[`porting.md`](porting.md) §6.2） |

## 6 怎么自己量

```bash
# ① 1x：策略周期应当是 20.00 ms（仿真时间），7/7 全过
pixi run python @20261007_assignment/scripts/agent_scripts/check_walk.py

# ② 全速：时间线自动改成按仿真时间推进，实测 ~25x、仍然 7/7
pixi run python @20261007_assignment/scripts/agent_scripts/check_walk.py --realtime false

# ③ 暂停：SIGSTOP 仿真 1.5 s，斜坡几乎不动；SIGCONT 后继续
pixi run python @20261007_assignment/scripts/agent_scripts/check_feedback_clock.py

# ④ 栈自身的吞吐（不含 Python 检查脚本的负载）：每 5 s 墙钟打一行
pixi run ros2 run quadruped_ros2 sim_node --ros-args -p viewer:=false -p realtime:=false -p status_period_s:=0.25
# 另开一个终端：pixi run ros2 run rl_sar rl_sim
```

实测（2026-10-11，多次）：① 1x 策略周期 20.00 ms（997~998 次）；② 全速 22~25x、7/7；③ 停顿期间只前进 3.5 个百分点（24.5% → 27.5%），`SIGCONT` 后继续到 48%；
④ 连续三行 `仿真 207.86 s / 墙钟 5.00 s = 41.6x`、`39.3x`、`40.3x`，每 5 s 墙钟发 10 万条出头反馈。
