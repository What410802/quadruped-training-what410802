# 子任务项二（实体电机控制）：程序与工具

真实电机是宇树 **GO-8010-6**，走官方 SDK（[`../../../ReadOnly.d/unitree_actuator_sdk`](../../../ReadOnly.d/unitree_actuator_sdk)）。
本目录放五件东西：

| 程序 | 干什么 | 需要硬件吗 |
|---|---|---|
| `include/motor_bench/ticks.hpp` | **内部定点表示**：位置类量一律是"转子侧 int64 tick"（1 tick = 1/32768 转子圈），收/发/人机三个边界上的换算都在这一个文件里；减速比用真值 19:3 | 不要 |
| `include/motor_bench/sim/fake_motor.hpp` | **假电机 + 假驱动板**：一阶速度响应 + 库仑摩擦 + 力矩限幅；报文与全部定点标度按实测值收发；`Encoder` 那层带**单圈绝对值编码器语义**（里程计/锯齿、上电认错零点 ±k 个区间、中途换基准），用来复现 S5 | 不要 |
| `apps/sim_fake_motor_dryrun.cpp` | dry run：PTY + 假电机，跑通"上位机 → SDK → 报文 → 反馈" | 不要 |
| `apps/serial_probe.cpp` | **实机探针 / S2 找零点**：只开端口、零力矩读反馈（默认一个字节都不发）；`--watch` 里加 `--every/--jump-deg/--log` 与回车打 MARK，手转输出端就能看读数形态与跨零点 | 要（`sudo`） |
| `apps/spin_test.cpp` | **S1**：带斜坡与限幅地让电机慢慢转起来，并打印每帧到底发了什么；`--kd-out` 做 kd 扫描、`--drop-after` 模拟掉线 | 要（`sudo`） |
| `apps/motor_ctl.cpp` | **S3–S5**：回归 0 + 键盘给角度（梯形插值）+ `offset` 标定（收到加、下发减）+ 零点跳变检测与修正；`--self-test` 能注入"认错零点/锯齿/中途跳变"离线跑通整条流程 | 实机要（`sudo`）；dry run 不要 |

> 布局：`include/motor_bench/`（公开接口，`.hpp`）、`src/`（实现与 PTY 垫片）、`apps/`（可执行入口）；
> `include/motor_bench/sim/` 与 `apps/sim_fake_motor_dryrun.cpp` 是**不用于控制实机**的那部分。
>
> 硬件现状（转接头型号/驱动/权限）、成熟度评估、**S0–S5 的完整计划与验收标准**、实机实测记录都在
> [`docs/real.md`](docs/real.md)；**实机怎么一步步做**（批次 0–7 的执行卡、记录表、故障处置、验收演示）见
> [`docs/runbook.md`](docs/runbook.md)；S3–S5 的上机手册在 [`docs/real.md`](docs/real.md) §3.8，缩写
> （TTY/PTY、Mbaud、LSB、CRC、offset…）见 [`docs/glossary.md`](docs/glossary.md)；
> **仿真电机**（向 SDK 伪装成实体电机的那一层：层级、接口、时序、能证明什么）见
> [`docs/fake_motor.md`](docs/fake_motor.md)；
> **零点的上电/运行/离线语义、程序自维护的状态与验收程序的设计**见
> [`docs/zero_semantics.md`](docs/zero_semantics.md)。

```
上位机（我们的控制律）          官方 SDK                            假电机 / 真电机
关节侧 τ/q/dq/kp/kd  ──ToRotor()──▶  MotorCmd  ──打包+CRC──▶  串口  ──▶ 解帧/回帧
   ▲                                                                       │
   └───────── q = data.q/N + offset  ◀── MotorData ◀──解包 ◀──────────────┘
```

## 0. 怎么建（比手写 g++ 省事，还顺带生成 `compile_commands.json`）

```bash
cd ..                       # 仓库根目录（有 pixi.toml；ReadOnly.d 与它同级）
pixi run cmake -S @20260927_motor/cpp_part2 -B @20260927_motor/cpp_part2/build
pixi run cmake --build @20260927_motor/cpp_part2/build
```

（这一半只用 g++ / cmake 与 SDK 预编译的 `.so`，用不到 MuJoCo，所以不用传 `-DCMAKE_PREFIX_PATH`——
传了 CMake 会警告 `Manually-specified variables were not used`。子任务项一 `cpp/` 才需要。）

`CMAKE_EXPORT_COMPILE_COMMANDS` 打开后会在 `build/compile_commands.json` 写入每个源文件的
编译命令（含 SDK 的 `-I`），**编辑器（clangd / VS Code C++）靠它才知道 `serialPort/SerialPort.h` 在哪**——
不建一次就会"代码标红"。SDK 目录可用 `-DUNITREE_SDK_DIR=<路径>` 覆盖（默认按"与本仓库根同级的
`ReadOnly.d/unitree_actuator_sdk`"算绝对路径）。

## 1. 不接电机直接跑官方例程会怎样（实测）

```bash
S=../ReadOnly.d/unitree_actuator_sdk
g++ -O2 -std=c++14 -I$S/include example/example_goM8010_6_motor.cpp -L$S/lib \
    -lUnitreeMotorSDK_Linux64 -Wl,-rpath,"$PWD/$S/lib" -o /tmp/example_go   # 能编译
/tmp/example_go                                                            # 没有 /dev/ttyUSB0
# → terminate called after throwing an instance of 'IOException'
#   what(): IO Exception (2): No such file or directory, file .../SerialPort.cpp, line 230
#   [1] IOT instruction (core dumped)
```

两条结论：**编译不需要硬件**（预编译的 `lib/libUnitreeMotorSDK_Linux64.so` 直接链）；但例程**没有异常处理**，
`SerialPort` 构造失败（没有设备）就 `std::terminate`。所以"跑通例程"必须要么有设备、要么把串口换成假的。

## 2. 为什么不能直接把 PTY 当串口

```bash
g++ ... /tmp/pty_probe.cpp -o /tmp/pty_probe && /tmp/pty_probe
# PTY：slave=/dev/pts/9
# 异常：IO Exception (25): Inappropriate ioctl for device, file .../SerialPort.cpp, line 487
```

`SerialPort` 构造时会对串口做一次 `TIOCGSERIAL`（读 `serial_struct`）/ `TIOCSSERIAL`（自定义除数），
这两个 ioctl 只有真串口驱动支持，PTY 一律回 `ENOTTY`。**与波特率无关**：115200 / 1 M / 2 M / 4 M 都在同一行炸
（所以"换个标准波特率就行"是不成立的）。

修法：`src/pty_serial_shim.c` 把这两个 ioctl 拦下来（`TIOCGSERIAL` 回一份 `PORT_16550A` +
`baud_base=4000000` 的 `serial_struct`，`TIOCSSERIAL` 直接回成功），其余 ioctl 透传。不需要 root、
不需要内核模块，`LD_PRELOAD` 即可。

## 3. 怎么跑

```bash
cd ..                                          # 仓库根目录（MyMonoRepo.d/，与 ReadOnly.d 同级）
S=../ReadOnly.d/unitree_actuator_sdk
gcc -O2 -fPIC -shared -o /tmp/pty_serial_shim.so @20260927_motor/cpp_part2/src/pty_serial_shim.c -ldl
g++ -O2 -std=c++14 -I$S/include -I$S/include/unitreeMotor @20260927_motor/cpp_part2/apps/sim_fake_motor_dryrun.cpp \
    -L$S/lib -lUnitreeMotorSDK_Linux64 -Wl,-rpath,"$PWD/$S/lib" -pthread -o /tmp/fake_motor_dryrun
LD_PRELOAD=/tmp/pty_serial_shim.so /tmp/fake_motor_dryrun
```

`crc/crc_ccitt.h` 自身没有 include `<stdint.h>`/`<stddef.h>`（官方 .so 的编译单元先包了别的头才能过），
所以本文件先包 `<cstdint>`/`<cstddef>`。

## 4. 实测结果（本机，2026-09-27）

```
gear ratio = 6.330000（queryGearRatio），mode = 1（queryMotorMode）
下发（关节侧 kp=80 kd=3 q_des=0.50 dq_des=1.00）→ 转子侧 K_P=1.9966 K_W=0.0749 Pos=3.165 W=6.330 T=0.000
  命令#1：head=fe ee id=0 status=1（0 锁定/1 FOC/2 校准） tor_des=0 spd_des=257 pos_des=16506 k_pos=2555 k_spd=95
       CRC：报文 0x0adc，本地重算 0x0adc → 一致
#0 sendRecv=true  data.q=3.1416 rad（转子侧）→ 关节侧 q=0.4963 rad；data.dq=3.1416、data.tau=1.0000 N·m、temp=32、merror=0
```

连上之后能确认的东西（这些以前只能"看手册猜"）：

| 事实 | 证据 |
|---|---|
| 命令帧 17 字节：`fe ee` + 1 字节 mode + 12 字节 `comd` + 2 字节 CRC | 假电机收到 `fe ee 10 00 … 15 d0` |
| mode 字节 = `(status<<4) \| id`，`status=1` 就是 FOC（`queryMotorMode` 返回 1） | `fe ee 10` + id=0 |
| CRC 是仓库里那份 `crc_ccitt`（多项式 0x8408，无反射、初值 0），覆盖前 15 字节 | 本地重算 = 报文里那 2 字节 |
| 反馈帧 16 字节：`fe ee` + mode + 11 字节 `fbk` + CRC | 我们的回帧被 SDK 接受（`sendRecv=true`，`temp/merror/tau/q/dq` 全部解出来了） |
| 不需要设备也能拿到 `queryGearRatio(GO_M8010_6)=6.33`、`queryMotorMode(GO,FOC)=1` | 同一份输出 |

**定点标度（用我们控制的 raw 值反推，全部实测）**：

| 量 | 报文（raw，定点） | 物理量 | 备注 |
|---|---|---|---|
| 位置 `pos_des` / `pos` | `q15` **圈**（转子侧）= **32768 tick/转子圈** | `rad = raw × 2π/32768`（程序内部直接用整数 tick，见 [`docs/fixed_point.md`](docs/fixed_point.md) §5） | `q_des=0.5 rad`、N=6.33 → `pos_des=16506` ✓；回帧 raw=16384 → `data.q=3.1416` ✓ |
| 速度 `spd_des` / `speed` | `raw = ω × 256/(2π)`（= ω×128/π；手册 §8.2 写的就是 `ω_set = ω_des/(2π) × 256`） | `rad/s = raw × π/128` | `W=6.33` → `spd_des=257`（截断）；回帧 raw=128 → `data.dq=3.1416` ✓ —— **与手册一致**；容易看错的是 SDK **头文件注释**把它写成 "rad/s (q7)"（读起来像 ×128），照它写会得到 810 而不是 257 |
| 力矩 `tor_des` / `torque` | `q8` | `N·m = raw/256` | 回帧 raw=256 → `data.tau=1.0` ✓ |
| 刚度 `k_pos` / 阻尼 `k_spd` | `q15` + **归一化** | `raw = K_P × 1280`（≈ 归一化 `0…25.6` → `0…32766`，**截断**） | `K_P=1.9966 → 2555`、`K_W=0.0749 → 95`（两点都是 ×1280 后截断；这两点区分不出 1280 与 32767/25.6）。**超量程被静默截断**：K_P = 49.9 和 99.8 都变成 `32766`（K_W 同理），所以关节侧 kp 上限 ≈ 32766/1280×N² = 1026 |

> **位置在程序内部一律是整数 tick**（`include/motor_bench/ticks.hpp`）：`pos` 就是 q15 圈，1 tick = 1/32768 转子圈；
> 减速比用真值 **19:3 = 6.3333**（SDK 的 `queryGearRatio` 给 6.33，差 5.26e-4 ⇒ 一个零点区间是
> 56.842° 而不是 56.872°，每输出圈差 0.19°）。SDK 的 float 换算用的 π 是 **3.1416**（不是真 π，
> 实测见 [`docs/fixed_point.md`](docs/fixed_point.md) §4），走它的 float 接口时要按同一个 π 反算。
>
> 那两处截断（`257` 而不是 258、`2555` 而不是 2556）说明 SDK 打包时用的是整数除法，所以**"写进去的"与
> "实际生效的"会有 1 个 LSB 的差**：1 LSB 分别等于 0.0245 rad/s（速度）、0.00078 的 K_P（刚度）。
> 对 kp=1.9966 来说是 0.04%，可以忽略；但要知道它存在（实机调零/标定时如果发现"总是差一点点"，多半是这个）。

## 5. 下一步（子任务项二真正要做的）

**硬件现状、成熟度评估与分阶段计划（含验收标准）已经单独成文：[`docs/real.md`](docs/real.md)。**
这里只留结论：

| 层 | 状态 |
|---|---|
| 报文 / CRC / 定点标度 / 关节↔转子换算 / 反馈解码 | ✅ 已实测证明（本文件 §4）；无硬件时由[仿真电机](docs/fake_motor.md)按同一套标度收发，官方 SDK 原样解析 |
| 真串口链路（4 Mbaud、半双工、时序/抖动） | ✅ **S1 实测通过**：6 次 × 1601 帧、0 丢帧 0 超时（见 [`docs/real.md`](docs/real.md) §3.6） |
| S2 找零点 / 读数形态 / 断链行为 / 上电基准 | 🔧 工具与手册就绪（[`docs/real.md`](docs/real.md) §3.7），**待实机执行** |
| 官方例程（任务书 1 的字面要求） | 🔧 命令与安全注意事项就绪（[`docs/runbook.md`](docs/runbook.md) §4 批次 2），**待实机执行** |
| 零点标定（`offset`）与零点跳变处理（S3–S5） | 🔧 **程序已就绪**（`apps/motor_ctl.cpp`，§6 的 dry run 已把标定/跳变/认错零点整套流程跑通），**待实机执行** |
| 安全层（看门狗、斜率/速度/力矩上限、温度与错误处理） | 🔧 `motor_ctl` 已有：插值限速限加速度、连续 40 帧无回复卸力退出、`merror`/温度退出、力矩持续超限判卡住；**“断链后驱动板自己怎么办”仍要 S2e 量** |

顺手能跑的分析脚本（都在 `scripts/agent_scripts/`，用 `pixi run python` 跑）：

| 脚本 | 干什么 |
|---|---|
| `analyse_spin_log.py` | 分析 `spin_test` 的输出：每次跑的命令转速 vs 实测转速、丢帧、温度 |
| `analyse_watch_log.py` | 分析 S2 的 `--watch --log`：读数形态（里程计/锯齿）、手转量、±1 区间的跳变清单、MARK 读数 |
| `analyse_ctl_log.py` | 分析 `motor_ctl` 的一次/多次运行：每条命令的到位情况、跳变修正、保护触发、并给出"可直接抄进记录表"的一行摘要 |
| `check_md_links.py` | 文档自检：断链/锚点/表格列数 |

**定点数 vs 浮点**（协议量化、SDK 的 π′=3.1416、编码器分辨率、内部改 int64 tick 的收益边界）与
**"待实机复验"清单**在 [`docs/fixed_point.md`](docs/fixed_point.md)。

**实机的执行顺序与记录表**见 [`docs/runbook.md`](docs/runbook.md)（批次 0–7）。一句话：
先 **S2**（手册 [`docs/real.md`](docs/real.md) §3.7）：手转找零点 + 定“里程计/锯齿” + 量断链行为 + 查上电基准；
再按 §3.8 用 `motor_ctl` 做 S3–S5（标定与跳变处理的符号约定见 [`docs/real.md`](docs/real.md) §5）。
实机跑要 `sudo`（或把自己加进 `dialout`）、先确认串口设备与电机 ID、先从**小角度 + 插值**开始。

## 6. S3–S5：`motor_ctl` 怎么用（离线先跑，再上机）

程序：[`apps/motor_ctl.cpp`](apps/motor_ctl.cpp)。它一次把三件事都做了：**回 0 位、键盘给角度、`offset` 标定与零点跳变处理**。

```bash
cd ..                       # 仓库根目录
B=@20260927_motor/cpp_part2/build/motor_ctl
$B --help                                        # 全部参数与键盘命令
$B --no-send                                     # 只看配置（不发字节）

# ① 离线自检（不接电机；PTY 垫片由 CMake 一起编好，见 §0）
export LD_PRELOAD=$PWD/@20260927_motor/cpp_part2/build/libpty_serial_shim.so
$B --self-test --script "0;30;mark;o+30;expect;30"     # 回归 0 → 30° → 记零点 → 正向偏移 30° → 再回 30°
$B --self-test --fake-datum-turns 1 --expect-deg 0 --seconds 3     # 假板子“上电认错零点”，看启动检查与自动修正
$B --self-test --fake-jump-frame 40 --fake-jump-turns 1 --script "60" --seconds 4   # 运行中注入一次跳变
$B --self-test --fake-sawtooth --script "100" --seconds 4         # 板子只报相对最近零点的角度（锯齿）
$B --self-test --fake-hand-deg 120 --fake-hand-period-s 6 --script "free;state" --seconds 8   # "手推输出端"来回 ±120°（跨 2 个零点区间）
$B --self-test --fake-off-after 200 --fake-off-frames 200 --fake-hand-deg 80 --script "free;state" --seconds 6   # 断电 + 期间手推 + 重上电
$B --self-test --fake-cycle-frame 250 --script "60" --seconds 4 --every 50                        # 单次上电复位（读数跳一个区间）

# ② 实机（sudo；先小角度、手边能断电）
sudo $B --port /dev/ttyUSB0 --id 0 --script "0"          # 回归 0 位（多圈行程会先打印预计时间）
sudo $B --port /dev/ttyUSB0 --id 0 --script "0;mark;30;o+30;expect;30"   # S3→S4：回 0 → 记零点 → 去 30° → 偏移 30° → 复查 → 再回 30°（会落回记号笔那一点）
sudo $B --port /dev/ttyUSB0 --id 0 --expect-deg 0        # 上电检查（记号笔那个点的记录值）：差 ≈1 个区间会自动修
```

`--script` 只是"非交互地敲键盘"；真机上手时**不带 `--script`** 直接在终端敲命令更顺手（`h` 看帮助：

| 命令 | 作用 |
|---|---|
| `0` / `<数字>` | 回 0 位 / 去那个角度（度） |
| `travel D` | 本会话相对"现在"再多转 D 度（找记号笔位置用） |
| `mark` | 把此刻记成记号笔那个点（同时打出 `q` 与 `q_enc`，**抄下 `q_enc` 供以后上电检查**） |
| `goto-mark` | 转到记号笔那个点（第 4 条"手转到零点附近"就用它） |
| `o+30` / `o-30` / `o 30` | `offset` 加/减/设为 30°（S4 的"零点正向偏移 30°"；改的时候电机不会动） |
| `expect` / `fix` | 对照记录值查零点有没有跳变 / 按建议把 `offset` 补回来 |
| `hold` / `stop`（=`free`） | 位置保持 / 立刻零力矩卸力（**手转只能在零力矩下发**：带位置环时手只能把它推开几度） |
| `p` / `h` / `q` | 打印状态 / 帮助 / 卸力退出 |

**几件必须知道的事**（理由与实测见 [`docs/real.md`](docs/real.md) §3.8 与 §5）：

* **位置在内部是 tick**（转子侧 int64）：`q_ticks = pos_ticks + offset_ticks`、`cmd.q_ticks = q_des_ticks − offset_ticks`
  —— 就是纯加减；度只在命令输入与打印处出现（[`docs/fixed_point.md`](docs/fixed_point.md) §5）；
* `cmd.dq / cmd.kd` 仍是**转子侧**：程序里已经换算好（速度按 tick→rad、增益 ÷N²），别再换一遍；
* `offset` 的方向是**收到加、下发减**；`o+30` 之后，**同一个物理点（记号笔那个点）读数 +30°**，而"同一个目标角度"会落在记号笔那一点上（= 朝反方向少转 30°）；
* 回归 0 可能是**多圈**行程（读数从上次上电起一直累计），程序会先打印"要转多少度、直线时间多少秒"；
* 跳变判据用**整数 raw 差 ≈ k×32768**（k 个转子圈 = k×56.842° 输出端）：检测到就只把 `offset` 反向补 k 个区间 —— 这样同一个 `q_des` 仍对应同一个物理位置；**顺手挪 q_des 是错的**（会把物理目标整段挪一个区间，dry run 里实测过）；
* 上电时"认错零点"用 `--expect-deg <记号笔那点的 q>` 或 `expect` 发现（差 ≈1 个区间），`--no-fix-startup` 可以只报警不动手；
* **离线时（连续 40 帧无回复）程序自动切零力矩**，回来那一帧先重锚圈数再恢复出力——所以断链/断电再上电都不会有"追一个差一整圈的目标"的力矩冲击（离线自检里量过：52.5 N·m → 0.3 N·m）；
* 0 位最好**离候选零点边界 ≥10°**（`mark` 会提示），因为板子以"最近经过的零点"为基准，边界附近最容易认错（`--set-zero-read` 可以帮你把 0 位放到别处）。
