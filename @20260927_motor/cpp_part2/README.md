# 子任务项二（实体电机控制）：程序与工具

真实电机是宇树 **GO-8010-6**，走官方 SDK（[`../../../ReadOnly.d/unitree_actuator_sdk`](../../../ReadOnly.d/unitree_actuator_sdk)）。 本目录是任务书"二、实体电机控制"那部分的程序与工具：**让电机转起来 → 回 0 位 + 键盘给角度 → 标零点并正向偏移 30° → 处理零点跳变**。

```
上位机（我们的控制律）          官方 SDK                            假电机 / 真电机
关节侧 τ/q/dq/kp/kd  ──ToRotor()──▶  MotorCmd  ──打包+CRC──▶  串口  ──▶ 解帧/回帧
   ▲                                                                       │
   └───────── q = data.q/N + offset  ◀── MotorData ◀──解包 ◀──────────────┘
```

## 1 目录里的四件事

| 程序 | 干什么 | 需要硬件吗 |
|---|---|---|
| `include/motor_bench/ticks.hpp` | **内部定点表示**：位置类量一律是"转子侧 int64 tick"（1 tick = 1/32768 转子圈），收/发/人机三个边界上的换算都在这一个文件里；减速比用真值 19:3 | 不要 |
| `include/motor_bench/sim/fake_motor.hpp` | **假电机 + 假驱动板**：一阶速度响应 + 库仑摩擦 + 力矩限幅；报文与全部定点标度按实测值收发；`Encoder` 那层带**单圈绝对值编码器语义**（里程计/锯齿、上电认错零点 ±k 个区间、断电重上电、手推），用来离线复现 S2/S5 | 不要 |
| `apps/serial_probe.cpp` | **实机探针 / S2 找零点**：只开端口、零力矩读反馈（默认一个字节都不发）；`--watch` 里加 `--every/--jump-deg/--log` 与回车打 MARK，手转输出端就能看读数形态与跨零点 | 要（`sudo`） |
| `apps/spin_test.cpp` | **S1**：带斜坡与限幅地让电机慢慢转起来，并打印每帧到底发了什么；`--kd-out` 做 kd 扫描、`--drop-after` 模拟掉线 | 要（`sudo`） |
| `apps/motor_ctl.cpp` | **S3–S5**：回归 0 + 键盘给角度（梯形插值）+ `offset` 标定（收到加、下发减）+ 零点跳变检测与修正；`--self-test` 能离线跑通整条流程 | 实机要（`sudo`）；dry run 不要 |
| `apps/sim_fake_motor_dryrun.cpp` | 最小 dry run：PTY + 假电机，跑通"上位机 → SDK → 报文 → 反馈" | 不要 |

布局：`include/motor_bench/`（公开接口，`.hpp`）、`src/`（**没有 `main()`** 的：库实现 + PTY 垫片）、 `apps/`（**有 `main()`** 的：四个可执行入口）；`include/motor_bench/sim/` 与 `apps/sim_fake_motor_dryrun.cpp` 是**不用于控制实机**的那部分。选型理由、`apps/` 与 `src/` 的分界理由见 [`docs/setup.md`](docs/setup.md) §1。

## 2 怎么建、怎么跑

```bash
cd ..                       # 仓库根目录（有 pixi.toml；ReadOnly.d 与它同级）
pixi run cmake -S @20260927_motor/cpp_part2 -B @20260927_motor/cpp_part2/build
pixi run cmake --build @20260927_motor/cpp_part2/build

B=@20260927_motor/cpp_part2/build/motor_ctl
$B --help                                       # 全部参数与键盘命令

# 离线自检（不接电机；垫片 .so 由 CMake 一起编好）
export LD_PRELOAD=$PWD/@20260927_motor/cpp_part2/build/libpty_serial_shim.so
$B --self-test --script "0;30;mark;o+30;expect;30" --seconds 14

# 实机（sudo；先小角度、手边能断电）
sudo $B --port /dev/ttyUSB0 --id 0
```

全部参数、键盘命令与八条离线自检命令见 [`docs/cli.md`](docs/cli.md)；编译细节（SDK 路径、编辑器提示） 见 [`docs/setup.md`](docs/setup.md)。

## 3 结果与文档

| 文档 | 一句话 |
|---|---|
| [`docs/runbook.md`](docs/runbook.md) | **现场执行清单**：批次 0–7 的执行卡、记录表、故障处置、验收演示 |
| [`docs/real.md`](docs/real.md) | 硬件现状、成熟度评估、S0–S5 的完整计划与验收标准、实机实测记录 |
| [`docs/zero-semantics.md`](docs/zero-semantics.md) | 零点的上电/运行/离线语义、程序自维护的状态、验收时序 |
| [`docs/fixed-point.md`](docs/fixed-point.md) | 定点 vs 浮点：官方协议依据、误差预算、编码器精度、待实机复验清单 |
| [`docs/protocol.md`](docs/protocol.md) | **报文与定点标度的实测记录**（raw ↔ 物理量、截断、1 LSB） |
| [`docs/fake-motor.md`](docs/fake-motor.md) | 仿真电机：层级、接口、收发时序、注入开关、能证明什么 |
| [`docs/cli.md`](docs/cli.md) | `motor_ctl` 的参数与命令清单（离线 / 实机两种用法） |
| [`docs/setup.md`](docs/setup.md) | 构建、目录布局与工具链选型理由 |
| [`docs/pitfalls.md`](docs/pitfalls.md) | 无硬件阶段踩过的坑（例程崩溃、PTY ioctl、断链不卸力…） |
| [`docs/glossary.md`](docs/glossary.md) | 缩写（TTY/PTY、Mbaud、LSB、CRC、offset…） |
| [`../docs/status.md`](../docs/status.md) | **任务推进情况**（跨两个子任务项）：阶段状态、下一步、阻滞项、提交与分支（本 README 只做入口，不记进度） |

顺手能跑的分析脚本（在 [`../scripts/agent_scripts/`](../scripts/agent_scripts/)，用 `pixi run python` 跑）：

| 脚本 | 干什么 |
|---|---|
| `analyse_spin_log.py` | 分析 `spin_test` 的输出：每次跑的命令转速 vs 实测转速、丢帧、温度 |
| `analyse_watch_log.py` | 分析 S2 的 `--watch --log`：读数形态（里程计/锯齿）、手转量、±1 区间的跳变清单、MARK 读数 |
| `analyse_ctl_log.py` | 分析 `motor_ctl` 的一次/多次运行：每条命令的到位情况、跳变修正、保护触发，并给出"可直接抄进记录表"的一行摘要 |
| `check_md_links.py` | 文档自检：断链/锚点/表格列数 |
