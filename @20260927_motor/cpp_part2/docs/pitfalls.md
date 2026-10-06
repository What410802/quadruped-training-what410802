# 踩过的坑（无硬件阶段就能撞上的那些）

> 每条都附"当时看到的原始输出"或可复现命令。**协议与定点标度**那两个坑（π′=3.1416、截断与 1 LSB） 在 [`fixed-point.md`](fixed-point.md) §2–§4；**假电机的保真度**在 [`fake-motor.md`](fake-motor.md) §5/§7； **本机环境**（图形栈、镜像、`tee` 的管道缓冲）在仓库 [`../../../docs/pitfalls/environment.md`](../../../docs/pitfalls/environment.md)。

## 1 官方例程没有异常处理：没有设备就是 `core dumped`

任务书第 1 条要"用官方 SDK 例程让电机转起来"。**编译不需要硬件**（预编译的 `lib/libUnitreeMotorSDK_Linux64.so` 直接链），但例程不接没有设备时会直接死掉：

```bash
S=$(sed -n 's/^set(UNITREE_SDK_DIR "\(.*\)")$/\1/p' local_paths.cmake)   # 宇树 SDK：只读材料，路径从本机配置里读
g++ -O2 -std=c++14 -I$S/include example/example_goM8010_6_motor.cpp -L$S/lib \
    -lUnitreeMotorSDK_Linux64 -Wl,-rpath,"$PWD/$S/lib" -o /tmp/example_go   # 能编译
/tmp/example_go                                                            # 没有 /dev/ttyUSB0
# → terminate called after throwing an instance of 'IOException'
#   what(): IO Exception (2): No such file or directory, file .../SerialPort.cpp, line 230
#   [1] IOT instruction (core dumped)
```

`SerialPort` 构造失败（设备不存在）就 `std::terminate`——例程里没有 `try/catch`。 所以"跑通例程"必须要么真有设备，要么把串口换成假的（下面这条），**不能靠"先跑一下看看"**： 在没有电机的机器上跑它一定崩，这不是环境配错了。

## 2 PTY 不能直接当串口：`TIOCGSERIAL` / `TIOCSSERIAL`

想用伪终端（PTY）顶替真串口时，`SerialPort::SerialPort` 会在 `open` 之后做一次 `ioctl(TIOCGSERIAL)`（读 `serial_struct`）与 `ioctl(TIOCSSERIAL)`（设置自定义除数，用于非标准波特率）：

```bash
# PTY：slave=/dev/pts/9
# 异常：IO Exception (25): Inappropriate ioctl for device, file .../SerialPort.cpp, line 487
```

这两个 ioctl 只有真串口驱动支持，PTY 一律回 `ENOTTY`。**与波特率无关**：115200 / 1 M / 2 M / 4 M 都在同一行炸（所以"换个标准波特率就行"不成立）。

修法（`src/pty_serial_shim.c`，编成 `.so` 后用 `LD_PRELOAD` 加载）：

* `TIOCGSERIAL` ⇒ 回一份 `PORT_16550A` + `baud_base=4000000` 的 `serial_struct`（真 FTDI 上实测是 `baud_base=60000000`，但 PTY 这条路径只需要"能整除且非零"，见 [`fake-motor.md`](fake-motor.md) §3.3）；
* `TIOCSSERIAL` ⇒ 直接回成功；
* 其余 ioctl 与读写全部透传。

不需要 root、不需要内核模块；只在 `--self-test` 时加载，实机路径上不生效。

## 3 `crc/crc_ccitt.h` 自身缺 include

SDK 里那份 CRC 头文件没有自己 `#include <stdint.h>` / `<stddef.h>`（官方 `.so` 的编译单元先包了别的头才过）。 手工编译任何**直接**引用它的源文件时要先包：

```cpp
#include <cstdint>
#include <cstddef>
#include <crc/crc_ccitt.h>
```

CMake 构建下已经处理好了（`include/motor_bench/ticks.hpp` 自己先包），只有"单独 `g++` 一个文件试试"时才会撞上。

## 4 断链之后驱动板**不卸力**（S2e 实测）

程序被强杀（`Ctrl-C` / `SIGKILL`）时不会发收尾零力矩，**驱动板会一直执行最后一条指令**：电机继续转， 直到断电。所以"停"只有两种办法：程序自己发零力矩（`q`/`stop`/收尾 20 帧），或者把电机断电。 据此，`motor_ctl` 的收尾路径、以及"离线 40 帧 ⇒ 切零力矩"都是按"程序是唯一能停它的人"设计的 （[`zero-semantics.md`](zero-semantics.md) §4）。
