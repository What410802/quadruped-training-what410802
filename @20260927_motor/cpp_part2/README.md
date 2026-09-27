# 第二部分（实机）：程序与工具

真实电机是宇树 **GO-8010-6**，走官方 SDK（[`../../../ReadOnly.d/unitree_actuator_sdk`](../../../ReadOnly.d/unitree_actuator_sdk)）。
本目录放四件东西：

| 程序 | 干什么 | 需要硬件吗 |
|---|---|---|
| `src/sim/fake_motor.h` | **假电机**：一阶速度响应 + 库仑摩擦 + 力矩限幅；报文与全部定点标度按实测值收发 | 不要 |
| `src/sim/fake_motor_dryrun.cpp` | dry run：PTY + 假电机，跑通"上位机 → SDK → 报文 → 反馈" | 不要 |
| `src/serial_probe.cpp` | **实机探针**：只开端口/零力矩读反馈（默认一个字节都不发） | 要（`sudo`） |
| `src/spin_test.cpp` | **S1**：带斜坡与限幅地让电机慢慢转起来，并打印每帧到底发了什么 | 要（`sudo`） |

> `src/sim/` 里是**不用于控制实机**的代码（PTY 垫片 + 假电机 + dry run），`src/` 下其余文件都要接实机。
>
> 硬件现状（转接头型号/驱动/权限）、成熟度评估、**S0–S5 的完整计划与验收标准**、实机实测记录都在
> [`docs/real.md`](docs/real.md)；缩写（TTY/PTY、Mbaud、LSB、CRC…）见 [`docs/glossary.md`](docs/glossary.md)。

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
传了 CMake 会警告 `Manually-specified variables were not used`。第一部分 `cpp/` 才需要。）

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

修法：`src/sim/pty_serial_shim.c` 把这两个 ioctl 拦下来（`TIOCGSERIAL` 回一份 `PORT_16550A` +
`baud_base=4000000` 的 `serial_struct`，`TIOCSSERIAL` 直接回成功），其余 ioctl 透传。不需要 root、
不需要内核模块，`LD_PRELOAD` 即可。

## 3. 怎么跑

```bash
cd ..                                          # 仓库根目录（MyMonoRepo.d/，与 ReadOnly.d 同级）
S=../ReadOnly.d/unitree_actuator_sdk
gcc -O2 -fPIC -shared -o /tmp/pty_serial_shim.so @20260927_motor/cpp_part2/src/sim/pty_serial_shim.c -ldl
g++ -O2 -std=c++14 -I$S/include -I$S/include/unitreeMotor @20260927_motor/cpp_part2/src/sim/fake_motor_dryrun.cpp \
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
| 位置 `pos_des` / `pos` | `q15` **圈**（转子侧） | `rad = raw × 2π/32768` | `q_des=0.5 rad`、N=6.33 → `pos_des=16506` ✓；回帧 raw=16384 → `data.q=3.1416` ✓ |
| 速度 `spd_des` / `speed` | `q7` 的**π 倍** | `rad/s = raw × π/128` | `W=6.33` → `spd_des=257`（截断）；回帧 raw=128 → `data.dq=3.1416` ✓ —— 注意手册/头文件注释写的是"rad/s (q7)"，**少了一个 π**，写侧 6.33 rad/s 要写 257 而不是 810 |
| 力矩 `tor_des` / `torque` | `q8` | `N·m = raw/256` | 回帧 raw=256 → `data.tau=1.0` ✓ |
| 刚度 `k_pos` / 阻尼 `k_spd` | `q15` + **归一化** | `raw = K_P × 1280`（≈ 归一化 `0…25.6` → `0…32766`，**截断**） | `K_P=1.9966 → 2555`、`K_W=0.0749 → 95`（两点都是 ×1280 后截断；这两点区分不出 1280 与 32767/25.6）。**超量程被静默截断**：K_P = 49.9 和 99.8 都变成 `32766`（K_W 同理），所以关节侧 kp 上限 ≈ 32766/1280×N² = 1026 |

> 那两处截断（`257` 而不是 258、`2555` 而不是 2556）说明 SDK 打包时用的是整数除法，所以**"写进去的"与
> "实际生效的"会有 1 个 LSB 的差**：1 LSB 分别等于 0.0245 rad/s（速度）、0.00078 的 K_P（刚度）。
> 对 kp=1.9966 来说是 0.04%，可以忽略；但要知道它存在（实机调零/标定时如果发现"总是差一点点"，多半是这个）。

## 5. 下一步（第二部分真正要做的）

**硬件现状、成熟度评估与分阶段计划（含验收标准）已经单独成文：[`docs/real.md`](docs/real.md)。**
这里只留结论：

| 层 | 状态 |
|---|---|
| 报文 / CRC / 定点标度 / 关节↔转子换算 / 反馈解码 | ✅ 已实测证明（本文件 §4） |
| 真串口链路（4 Mbaud、半双工、时序/抖动） | ❌ 未验证（`serial_probe` 的"端口探针"就是测它） |
| 零点标定（`offset`）与零点跳变处理 | ❌ 还没写代码 |
| 安全层（看门狗、斜率/速度/力矩上限、温度与错误处理） | ❌ 还没写代码 |

1. 把假电机那条线程换成**一台虚拟电机**（一阶惯性 + 摩擦 + 限幅），
   这样"回归零点 → 插值到目标角 → 标记零点 → 偏移 +30° → 零点跳变"整套逻辑都能先在这里验证；
2. 用 dry run 把 `offset` 标定流程走一遍（`q = data.q/N + offset`、`cmd.Pos = (q_des − offset)·N`），
   包括人工制造"认错零点"（把回帧的 pos 加上 `1/6.33` 圈）来看跳变检测是否报警；
3. 再接实机：`sudo`（或加进 `dialout`）、确认串口设备与电机 ID、先用小角度 + 插值缓慢动。
