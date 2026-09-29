// 让宇树 SDK 的 SerialPort 以为 /dev/pts/N 是一块"真串口"（dry run 的粘合层，不需要 root、不需要内核模块）。
//
// 为什么要它（实测）：不接电机、直接把 PTY 交给 `SerialPort serial("/dev/pts/9")`，会抛
//     IOException (25): Inappropriate ioctl for device  （SerialPort.cpp:487）
// 与波特率无关（115200 / 1M / 2M / 4M 都在同一行炸）：SDK 在构造时会对串口做一次
// TIOCGSERIAL（读 serial_struct）/ TIOCSSERIAL（自定义除数）——这两个 ioctl 只有真串口驱动支持，
// PTY 一律回 ENOTTY。所以这里把它们拦下来、给一份合理的 serial_struct，其余 ioctl 原样透传。
//
// 编译：gcc -O2 -fPIC -shared -o pty_serial_shim.so pty_serial_shim.c -ldl
// 用法：LD_PRELOAD=./pty_serial_shim.so ./fake_motor_dryrun
//
// 它在整个"仿真电机"里的位置（层级图、接口、时序）见 ../docs/fake-motor.md §2–§4。
#define _GNU_SOURCE
#include <dlfcn.h>
#include <linux/serial.h>
#include <stdarg.h>
#include <string.h>
#include <sys/ioctl.h>

typedef int (*ioctl_fn)(int, unsigned long, ...);

int ioctl(int fd, unsigned long request, ...) {
    static ioctl_fn real = 0;
    if (!real)
        real = (ioctl_fn)dlsym(RTLD_NEXT, "ioctl");
    va_list ap;
    va_start(ap, request);
    void *arg = va_arg(ap, void *);
    va_end(ap);

    if (request == TIOCGSERIAL && arg != 0) {
        struct serial_struct ss;
        memset(&ss, 0, sizeof(ss));
        ss.type = PORT_16550A;   // 普通 UART
        ss.baud_base = 4000000;  // 声称基频就是 4 Mbaud ⇒ 自定义除数 = 1
        ss.xmit_fifo_size = 16;
        ss.flags = 0;
        *(struct serial_struct *)arg = ss;
        return 0;
    }
    if (request == TIOCSSERIAL && arg != 0)
        return 0; // 假装设置成功（PTY 上无所谓，dry run 不看真实波特率）
    return real(fd, request, arg);
}
