# 缩写与术语表（本次任务相关的）

> 目录（TOC）：[串口与终端](#串口与终端) · [硬件与电平](#硬件与电平) · [报文与定点](#报文与定点) ·
> [电机与模式](#电机与模式) · [构建与运行时](#构建与运行时)。

收录"这次新遇到、看文档时会被绊一下"的词。通用的 C++、MuJoCo 术语学习见仓库级文档。

## 串口与终端

| 缩写 | 全称 | 一句话解释 | 本任务哪里用到 |
|---|---|---|---|
| **TTY** | Teletype（电传打字机） | Linux 里"终端设备"的统称，`/dev/tty*` 都是它。**TTY ≠ 串口**：真串口是 USB 转接芯片驱动出来的 `/dev/ttyUSB0`，伪终端（下面那个）也叫 tty <br/>（另：[串口相关的硬件普及知识](https://yb.tencent.com/s/l76ZUePHO4ng)） | `serial_probe` / `spin_test` 打开的 `/dev/ttyUSB0` |
| **PTY** | Pseudo-Terminal（伪终端） | 内核给的一对"假串口"：一头当程序（`/dev/pts/N`），另一头当"设备"。`posix_openpt()` 开一对，我们用它做 dry run（无硬件跑通协议） | `fake_motor.h` / `fake_motor_dryrun.cpp` 的 `--self-test` |
| **termios** | terminal I/O settings | 串口参数的统一接口（波特率、数据位、校验、停止位、流控）。`tcgetattr`/`cfsetspeed` 都是它 | `serial_probe` 打印 `tcgetattr` 结果 |
| **ioctl** | I/O control | "给设备发命令"的通用系统调用（不是读写数据）。串口的很多设置只能这样改 | `TIOCGSERIAL`/`TIOCSSERIAL`（读/写 `serial_struct`）——SDK 构造时要它，PTY 上必失败，所以要有 `pty_serial_shim.c` |
| **Mbaud** | Megabaud（兆波特） | 每秒 100 万次信号变化；串口里通常等于 bit/s。4 Mbaud = 4 000 000 bit/s 是本任务 SDK 的默认速率 | `/dev/ttyUSB0` 上的 4 Mbaud；FT232H 最高 12 Mbaud |
| **UART** | Universal Asynchronous Receiver/Transmitter | 异步串口（起止位+数据位，无时钟线）。USB 转接芯片对主机是 USB、对外部就是一路 UART | FT232H 就是"USB ↔ UART" |
| **HS** | High Speed（USB 2.0 高速 480 Mbit/s） | 只有 HS 的 FTDI 芯片才支持 12 Mbaud；全速（FS）只有 3 Mbaud | 我们的 FT232H 描述符 `bcdUSB 2.00` + `MaxPower` 那条 |
| **dialout** | —— | Debian/Ubuntu 系给串口设备的组名，`/dev/ttyUSB0` 通常是 `root:dialout 660`。不在这个组里就得 `sudo` | 你第一次跑 `serial_probe` 时的 `Permission denied` |
| **udev** | —— | Linux 的设备管理（设备插上后谁创建设备节点、权限给谁）。要永久免 `sudo` 可以写 udev 规则 | 备用方案，见 [`real.md`](real.md) §1 |

## 硬件与电平

| 缩写 | 全称 | 一句话解释 | 本任务哪里用到 |
|---|---|---|---|
| **TTL** | Transistor-Transistor Logic | 这里指"单端电平的串口"（0/3.3/5 V 对地），一根 TX、一根 RX、一根 GND。与下面的 RS485 不是一回事 | FT232H 出来的是 TTL，接线要确认电机侧要什么 |
| **RS485 / RS-485** | —— | 差分（A/B 两根线）半双工串口，抗干扰、能挂多机。差分要专门的收发器 | 任务书让找老队员确认接线，见 [`real.md`](real.md) §4 |
| **FTDI / FT232H** | Future Technology Devices International | USB-串口芯片厂商/型号。FT232H 是"单通道 HS"那颗，最高 12 Mbaud | `/dev/ttyUSB0` 就是它（`0403:6014`） |
| **VID:PID** | Vendor ID : Product ID | USB 设备的厂商标识与产品标识，`lsusb` 里那个 `0403:6014` | 判定转接头型号 |

## 报文与定点

| 缩写 | 全称 | 一句话解释 | 本任务哪里用到 |
|---|---|---|---|
| **CRC** | Cyclic Redundancy Check（循环冗余校验） | 给一段字节算出的校验值，收方重算一遍就能发现位翻转。宇树用 **CRC-CCITT**（16 位，多项式 0x8408，初值 0） | 报文最后 2 字节；我们本地重算与它一致 |
| **LSB** | Least Significant Bit（最低有效位） | 定点数里的"1 个刻度"。1 LSB = 该字段的分辨率 | `k_spd` 的 1 LSB = 1/1280；速度的 1 LSB = π/128 rad/s |
| **q7 / q8 / q15** | Q 格式定点数 | 用整数表示小数：`q8` = 低 8 位是小数（÷256），`q15` = 低 15 位是小数（÷32768）。分辨率是 2^-n，但量程还看整数字段宽度（比如 `int32 q15`） | `tor_des` q8、`spd_des` q7、`pos_des` int32 q15（单位是圈！） |
| **raw** | —— | 本文里指"报文里的那个整数"，与物理量相对 | 报文表里的 `spd_des=162` 之类 |

## 电机与模式

| 缩写 | 全称 | 一句话解释 | 本任务哪里用到 |
|---|---|---|---|
| **FOC** | Field-Oriented Control（磁场定向控制） | 驱动板里跑的三相电流闭环。上层只管给力矩/位置/速度目标，FOC 负责把电流加到该加的地方 | 报文 `status=1` 就是 FOC；讲义 §1.3 的 `mode = 1` |
| **MIT（模式）** | —— | 这里指"力位混合控制"那种一条公式 5 个量的用法（不是学校），讲义 §1.2 | `cmd.{tau,q,dq,kp,kd}` 五个量 |
| **MERror** | Motor Error | 反馈里 3 个 bit 的错误位：0 正常 / 1 过热 / 2 过流 / 3 过压 / 4 编码器故障 | `spin_test` 里 `merror != 0` 就收速度退出 |

## 构建与运行时

| 缩写 | 全称 | 一句话解释 | 本任务哪里用到 |
|---|---|---|---|
| **`LD_PRELOAD`** | —— | 让动态链接器先加载我们自己的 `.so`，于是我们可以"替换"某个库函数（这里是 `ioctl`）。只用于 dry run，实机不要带 | `pty_serial_shim.c` → `LD_PRELOAD=.../pty_serial_shim.so` |
| **rpath** | —— | 可执行文件里写死的"运行时去哪里找 `.so`"。不设的话用 `sudo` 跑会找不到 SDK 的 `.so`（`sudo` 会清掉 `LD_LIBRARY_PATH`） | `cpp_part2/CMakeLists.txt` 里的 `BUILD_RPATH` |
