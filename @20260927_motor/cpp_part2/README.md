# 第三部分（实机）预备：不接电机也能跑的 dry run

第三部分要控制真实电机（GO-8010-6）。实机不在手边时也要能把**上位机 ↔ 官方 SDK ↔ 报文**这条链路
跑通、把标度（定点标度、减速比、CRC）确定下来，于是有了这个 dry run：进程自己造一对 PTY，
一边交给官方 `SerialPort`（与实机同一套代码），另一边当"假电机"，按 GO-8010-6 的报文格式收命令、回反馈。

```
上位机（我们的控制律）          官方 SDK                            假电机（本目录）
关节侧 τ/q/dq/kp/kd  ──ToRotor()──▶  MotorCmd  ──打包+CRC──▶  PTY  ──▶ 解帧/回帧
   ▲                                                                       │
   └───────── q = data.q/N + offset  ◀── MotorData ◀──解包 ◀──────────────┘
```

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
g++ -O2 -std=c++14 -I$S/include -I$S/include/unitreeMotor @20260927_motor/cpp_part2/src/fake_motor_dryrun.cpp \
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

1. 把假电机那条线程换成**一台虚拟电机**（可以只是一个一阶惯性 + 摩擦 + 限幅的模型），
   这样"回归零点 → 插值到目标角 → 标记零点 → 偏移 +30° → 零点跳变"整套逻辑都能先在这里验证；
2. 用 dry run 把 `offset` 标定流程走一遍（`q = data.q/N + offset`、`cmd.Pos = (q_des − offset)·N`），
   包括人工制造"认错零点"（把回帧的 pos 加上 `1/6.33` 圈）来看跳变检测是否报警；
3. 再接实机：`sudo`、确认串口设备（`/dev/ttyUSB0` 看实际枚举）与电机 ID、先用小角度 + 插值缓慢动。
