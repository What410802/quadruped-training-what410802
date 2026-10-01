// 文件：pty_serial_shim.c
// 作用：让宇树 SDK 的 SerialPort 以为 /dev/pts/N 是一块"真串口"（实验台与离线演练的粘合层，不需要 root）。
//
// 为什么需要它（旧版实测）：不接电机、直接把 PTY 交给 SerialPort 构造，会抛
//     IOException (25): Inappropriate ioctl for device   （SerialPort.cpp:487）
// 与波特率无关：SDK 构造时会做一次 TIOCGSERIAL（读 serial_struct）/ TIOCSSERIAL（设置自定义除数），
// 这两个 ioctl 只有真串口驱动支持，PTY 一律回 ENOTTY。这里把它们拦下、给一份合理的 serial_struct，
// 其余 ioctl 与读写全部透传。只在需要把 SDK 接到 PTY 时 LD_PRELOAD；实机不加载。
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
        ss.baud_base = 4000000;  // 声称基频就是 4 Mbaud ⇒ 自定义除数 = 1（PTY 不看真实波特率）
        ss.xmit_fifo_size = 16;
        ss.flags = 0;
        *(struct serial_struct *)arg = ss;
        return 0;
    }
    if (request == TIOCSSERIAL && arg != 0)
        return 0; // 假装设置成功
    return real(fd, request, arg);
}
