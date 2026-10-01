/**
 * @file line_input.cpp
 * @brief LineInput 的实现：termios raw 模式 + 极简行编辑（退格 / Ctrl-U / Ctrl-D / 回车）。
 *
 * 为什么自己回显：raw 模式下终端不再替我们做行编辑，所以"提示符 + 缓冲"要由我们画；
 * 每段输出前用 `\r\x1b[K` 清掉这一行、输出完再重画，输入行就始终待在最后一行。
 */

#include "line_input.hpp"

#include <cstdio>
#include <termios.h>
#include <unistd.h>

namespace motor_ctl
{
namespace
{

constexpr const char* kPrompt = "> ";

bool is_utf8_continuation(char c)
{
    return (static_cast<unsigned char>(c) & 0xC0) == 0x80;
}

} // namespace

LineInput::~LineInput()
{
    finish();
}

bool LineInput::start(int fd)
{
    if (::isatty(fd) == 0)
    {
        return false;
    }
    if (::tcgetattr(fd, &saved_) != 0)
    {
        return false;
    }
    termios raw = saved_;
    raw.c_lflag &= static_cast<tcflag_t>(~(ICANON | ECHO)); // 保留 ISIG：Ctrl-C 仍是信号
    raw.c_cc[VMIN] = 0;
    raw.c_cc[VTIME] = 0;
    if (::tcsetattr(fd, TCSANOW, &raw) != 0)
    {
        return false;
    }
    fd_ = fd;
    active_ = true;
    redraw();
    return true;
}

void LineInput::finish()
{
    if (!active_)
    {
        return;
    }
    active_ = false;
    std::printf("\n");
    if (fd_ >= 0)
    {
        ::tcsetattr(fd_, TCSANOW, &saved_);
    }
    std::fflush(stdout);
    fd_ = -1;
}

void LineInput::begin_output()
{
    if (active_)
    {
        std::printf("\r\x1b[K");
    }
}

void LineInput::end_output()
{
    if (active_)
    {
        redraw();
    }
}

void LineInput::redraw()
{
    if (!active_)
    {
        return;
    }
    std::printf("\r\x1b[K%s%s", kPrompt, buffer_.c_str());
    std::fflush(stdout);
}

bool LineInput::poll(std::string* line)
{
    if (!active_)
    {
        return false;
    }
    char chunk[64];
    bool ready = false;
    bool changed = false;
    for (;;)
    {
        const ssize_t count = ::read(fd_, chunk, sizeof(chunk));
        if (count <= 0)
        {
            break;
        }
        for (ssize_t i = 0; i < count; ++i)
        {
            const unsigned char c = static_cast<unsigned char>(chunk[i]);
            if (c == '\n' || c == '\r')
            {
                std::printf("\r\n");
                *line = buffer_;
                buffer_.clear();
                ready = true;
                changed = true;
                continue;
            }
            if (c == 0x7f || c == 0x08) // Backspace / Delete
            {
                while (!buffer_.empty() && is_utf8_continuation(buffer_.back()))
                {
                    buffer_.pop_back();
                }
                if (!buffer_.empty())
                {
                    buffer_.pop_back();
                }
                changed = true;
                continue;
            }
            if (c == 0x15) // Ctrl-U：清掉整行
            {
                buffer_.clear();
                changed = true;
                continue;
            }
            if (c == 0x04) // Ctrl-D：空行时当成 quit（走正常的卸力退出路径）
            {
                if (buffer_.empty())
                {
                    *line = "quit";
                    ready = true;
                }
                continue;
            }
            if (c < 0x20) // 其他控制字符忽略（Ctrl-C 已由 ISIG 变成 SIGINT）
            {
                continue;
            }
            buffer_.push_back(chunk[i]);
            changed = true;
        }
        if (ready)
        {
            break; // 一次只交付一条语句，剩下的留在下次 poll
        }
    }
    if (changed || ready)
    {
        redraw();
    }
    return ready;
}

} // namespace motor_ctl
