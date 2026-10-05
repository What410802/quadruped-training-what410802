# cpp_part2_remake（子任务项二 · 实体电机控制 · 正式代码）

本目录是子任务项二（实体电机控制）的**正式代码**：任务书四条（回编码器零点 → 键盘给角度 → 记号笔标零点并正向偏移 30° → 处理零点跳变）全部完成并验收通过（2026-10-03）；按只读参考工程 `ReadOnly.d/quadruped_control/` 的分层与命名规范组织，并修掉历史版本（[`../cpp_part2/`](../cpp_part2/README.md)，仅作对照）的缺陷。设计（需求、符号约定、伪代码、决策、测试矩阵、里程碑）在 [docs/design.md](docs/design.md)（v2；v1 在 [docs/v1/](docs/v1/)）。

## 构建

下面命令里的 `<仓库路径>` 都要换成**你自己的仓库根目录**（含 `pixi.toml` 与 `@20260927_motor/` 的那一级，例如 `/home/<用户名>/.../MyMonoRepo.d`）。

```bash
cd <仓库路径>                                        # 构建在仓库根做（pixi 环境按仓库根的 pixi.toml）
pixi run cmake -S @20260927_motor/cpp_part2_remake -B @20260927_motor/cpp_part2_remake/build
pixi run cmake --build @20260927_motor/cpp_part2_remake/build
```

不需要宇树 SDK 的环境（只构建核心与测试）：给 cmake 加 `-DMOTOR_ENABLE_SDK=OFF`。
SDK 默认按"与本仓库根同级的 `ReadOnly.d/unitree_actuator_sdk`"推算，可用 `-DMOTOR_SDK_DIR=<路径>` 覆盖。

## 运行

```bash
B=<仓库路径>/@20260927_motor/cpp_part2_remake/build     # <仓库路径> 换成你的仓库根目录（绝对路径）

$B/tests/motor_core_tests                          # 核心自检（无硬件）
$B/tests/motor_sim_tests                           # 模型自检（无硬件）：折圈 / 里程计 / 整圈漂移
$B/tests/motor_wire_tests                          # 报文往返（无硬件；需 SDK 头文件）
# 或一次跑完：pixi run ctest --test-dir <仓库路径>/@20260927_motor/cpp_part2_remake/build

sudo $B/apps/motor_ctl/motor_ctl --port /dev/ttyUSB0 --id 0        # 实机交互（要 sudo 或 dialout 权限）
sudo $B/apps/motor_ctl/motor_ctl --no-send                         # 只看配置，不开串口
sudo $B/apps/motor_ctl/motor_ctl --port /dev/ttyUSB0 <<< "move 0; wait 3; mark; move 30; wait 3; zero move 30; state; move 30; wait 3; quit"

# ④b（可重启 + 启动自动对齐）：把上次标定与参考姿态带进新会话
sudo $B/apps/motor_ctl/motor_ctl --port /dev/ttyUSB0 --offset-deg -30 --pose-ref 14960tick
```

没有实机时，用虚拟实验台演练同一条主线（两个终端，见 [docs/runbook.md](docs/runbook.md) §8）：

```bash
$B/apps/motor_sim/motor_sim                        # 终端 2：假电机
```

终端 2 启动时会打印一行**可直接复制**的命令（里面有本机实际的 PTY 路径与垫片路径），把那行粘到终端 1 执行即可；形如：

```bash
LD_PRELOAD=<仓库路径>/.../libpty_serial_shim.so <仓库路径>/.../motor_ctl --port /dev/pts/N
```

注意 **`/dev/pts/N` 每次启动都不同，必须用终端 2 打印的那个**：机器上每个终端自己就是一个 `/dev/pts/N`，填错了会连到别的终端上去（现象：控制程序一直收不到回复、被填的那个终端刷出乱码）。

实机执行卡（步骤、记录表、异常处置、实验台演练）见 [docs/runbook.md](docs/runbook.md)。

stdin 就是命令通道：`;` 与换行等效，`wait <秒>` 与 `quit` 是语句；重定向即脚本模式。命令表与角度显示 / 输入单位约定见 [docs/design.md](docs/design.md) §3.8。

## 目录

两种场景（实机 / 实验台）共用同一条上层链路，只差最后一跳——实验台把端口换成 PTY，代码一行不改；`tools/pty_shim` 只在实验台里给 SDK 的**构造期**补两个 ioctl（运行期的 17 B / 16 B 收发不经过它）：

```text
实机:   core（会话）→ backends/unitree_sdk → 官方 SDK ──▶ /dev/ttyUSB0 ──▶ 真驱动板
实验台: core（会话）→ backends/unitree_sdk → 官方 SDK ──▶ /dev/pts/N  ──▶ wire → sim → 回帧
                                                              （同一进程 motor_sim）
```

```text
# 两种场景共用
core/       不依赖 SDK 与硬件的核心：换算（含 π′）、账本、梯形插值、语句解析、会话状态机、格式化
backends/   控制侧传输（unitree_sdk）：把设备帧送到"设备"那一头；实验台只是那头换成了 PTY
# 只在实验台里参与（按数据流方向）
tools/      pty_shim：补 SDK 构造期的两个 ioctl（注入控制进程；运行期数据面不经过它）
wire/       设备侧帧编解码：收 17 B 解帧 / 组 16 B 回帧（实验台进程）
sim/        电机 + 驱动板模型：动力学、最高转速、手握住/恒力矩、记号线（实验台进程，不依赖 SDK）
# 入口 / 验证 / 文档
apps/       motor_ctl（验收，两种场景都用）· motor_sim（实验台）
tests/      motor_core_tests（核心）· motor_wire_tests（报文往返）
docs/       设计文档与执行卡
```

细分依据：`core/` 与 `backends/` 在实机与实验台里都被用到；`wire/` 与 `sim/` 只在实验台进程里参与，二者分开是**依赖边界**——模型不依赖 SDK（`-DMOTOR_ENABLE_SDK=OFF` 也能构建），帧层要用 SDK 头文件（结构体与 CRC 表）。

离线只走**实验台**一条通道（进程内确定性通道 M2a 记为可选思路、暂不实施，理由见 [docs/design.md](docs/design.md) §4 D11）。

## 文档

| 文档 | 一句话 |
|---|---|
| [docs/design.md](docs/design.md) | **唯一权威设计文档（v2）**：需求（R1–R17）、符号与变量约定（§2.6）、设计、伪代码、决策记录（D1–D18）、测试矩阵（T1–T23）与里程碑 |
| [docs/runbook.md](docs/runbook.md) | 实机执行卡（v2）：批次 0–7 步骤卡、现场规则（手动转动允许范围）、记录表、异常处置与虚拟实验台演练 |
| [docs/control-loop.md](docs/control-loop.md) | 板子里的控制环（MIT / FOC）与实机停稳偏差（静摩擦死区）的来源分析 |
| [docs/v1/](docs/v1/) | v1 存档（[design.md](docs/v1/design.md) / [runbook.md](docs/v1/runbook.md)，2026-10-01 之前的版本，仅作对照） |
