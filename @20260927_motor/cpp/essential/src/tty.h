// 终端按键：把 stdin 设成"不用回车、不回显、Ctrl-C 不当信号"，用非阻塞读轮询。
//
// 为什么按键从终端拿，而不是从窗口拿：这次用的是**官方** Simulate 窗口，它的键是它自己的 UI
// （空格 = 暂停/继续、Ctrl+ 各种快捷键），挂不上自定义回调——这正是完整版自己写窗口的原因。
// 而我们要的键只有 4 个，终端本来也是看日志的地方，从这里读反而更简单：
//   * ICANON 关掉 → 按下就生效，不用回车；
//   * ECHO   关掉 → 按键不会回显进日志；
//   * ISIG   关掉 → Ctrl-C 不当信号，而是当成一个键（'q'）交给我们，这样析构时能恢复终端。
// 三条都由析构函数还原（RAII）：正常退出、按 q 退出、按 Ctrl-C 退出都会恢复，不会留下一个
// "不回显"的终端。stdin 不是终端（重定向/管道）时什么都不做，ok() == false，程序照常跑。
#pragma once

#include <fcntl.h>    // fcntl / O_NONBLOCK
#include <termios.h>  // termios / tcgetattr / tcsetattr
#include <unistd.h>   // isatty / read

#include <deque>

namespace tty {

class RawKeys {
  public:
    RawKeys() : fd_(STDIN_FILENO) {
        if (::isatty(fd_) == 0)
            return; // 不是终端：不碰它，也就没有按键（例如 `essential_sim < /dev/null`）
        if (::tcgetattr(fd_, &original_) != 0)
            return;
        struct termios raw = original_;
        raw.c_lflag &= static_cast<tcflag_t>(~(ICANON | ECHO | ISIG)); // 见文件头
        raw.c_cc[VMIN] = 0;                                            // 非阻塞：有多少读多少
        raw.c_cc[VTIME] = 0;
        if (::tcsetattr(fd_, TCSANOW, &raw) != 0)
            return;
        original_flags_ = ::fcntl(fd_, F_GETFL, 0); // 连 O_NONBLOCK 一起开，避免任何一次读卡住
        if (original_flags_ >= 0)
            ::fcntl(fd_, F_SETFL, original_flags_ | O_NONBLOCK);
        ok_ = true;
    }

    ~RawKeys() {
        if (!ok_)
            return;
        ::tcsetattr(fd_, TCSANOW, &original_); // 恢复：不回显的终端就是从这里来的
        if (original_flags_ >= 0)
            ::fcntl(fd_, F_SETFL, original_flags_);
    }

    // 持有终端设置的设备，不许拷贝/移动（与 [`../../src/viewer.h`](../../src/viewer.h) 的 Window 同一套写法：
    // 自己管一份系统资源、析构里还回去；原因见 docs/learn/cpp-cmake.md 的「= delete」那条问答）
    RawKeys(const RawKeys &) = delete;
    RawKeys &operator=(const RawKeys &) = delete;

    bool ok() const { return ok_; }

    // 取一个键；没有就返回 false。只认 s / d / r / q（大小写都行），Ctrl-C 也算 q，
    // 其它字节（含方向键那种转义序列）直接丢掉。
    bool TakeKey(char *key) {
        for (;;) {
            if (pending_.empty()) {
                if (!ok_ || !ReadMore())
                    return false;
            }
            const char c = pending_.front();
            pending_.pop_front();
            switch (c) {
            case 's': case 'S': *key = 's'; return true;
            case 'd': case 'D': *key = 'd'; return true;
            case 'r': case 'R': *key = 'r'; return true;
            case 'q': case 'Q': case 3: *key = 'q'; return true; // 3 = Ctrl-C（ISIG 关了）
            default: break;                                      // 其它键：丢掉，接着找
            }
        }
    }

  private:
    // 非阻塞读一把：有就塞进队列，没有就算了
    bool ReadMore() {
        char buf[64];
        const ssize_t n = ::read(fd_, buf, sizeof(buf));
        if (n <= 0)
            return false;
        pending_.insert(pending_.end(), buf, buf + n);
        return true;
    }

    int fd_ = -1;
    bool ok_ = false;
    int original_flags_ = -1;
    struct termios original_ = {};
    std::deque<char> pending_;
};

} // namespace tty
