/**
 * @file line_input.hpp
 * @brief 交互模式的输入行：终端最后一行固定为"提示符 + 正在输入的命令"，状态输出不再把它冲散。
 *
 * 只在 stdin 是 TTY 时启用（raw 模式：关 ICANON/ECHO、保留 ISIG，所以 Ctrl-C 仍是信号）；
 * 非 TTY（脚本 / 管道）走原来的整行读取，行为不变。实现细节见 line_input.cpp。
 */

#pragma once

#include <string>
#include <termios.h>

namespace motor_ctl
{

class LineInput
{
  public:
    ~LineInput();

    /** stdin 是 TTY 时进入 raw 模式；成功返回 true（失败则调用方按非交互处理） */
    bool start(int fd);

    bool active() const { return active_; }

    /** 读走当前可用的输入字节；凑满一行（回车）时写进 *line 并返回 true */
    bool poll(std::string* line);

    /** 输出前调用：把输入行清掉，给日志让位（非交互时无副作用） */
    void begin_output();
    /** 输出后调用：重画"提示符 + 已输入内容" */
    void end_output();

    /** 退出前恢复终端（析构里也会兜底调用一次） */
    void finish();

  private:
    void redraw();

    int fd_ = -1;
    bool active_ = false;
    termios saved_{};
    std::string buffer_;
};

} // namespace motor_ctl
