/**
 * @file console.cpp
 * @brief ParseCommand / HelpText 的实现：纯字符串处理，不碰硬件。
 */
#include "motor_bench/console.hpp"

#include <cctype>
#include <cstdlib>
#include <string>

namespace motor_bench
{

namespace
{

std::string Trim(const std::string& in)
{
    size_t b = 0;
    size_t e = in.size();
    while (b < e && (in[b] == ' ' || in[b] == '\t' || in[b] == '\r'))
    {
        ++b;
    }
    while (e > b && (in[e - 1] == ' ' || in[e - 1] == '\t' || in[e - 1] == '\r'))
    {
        --e;
    }
    return in.substr(b, e - b);
}

bool IsNumberLike(char c)
{
    return std::isdigit(static_cast<unsigned char>(c)) != 0 || c == '-' || c == '+' || c == '.';
}

} // namespace

ConsoleCommand ParseCommand(const std::string& raw_line)
{
    ConsoleCommand out;
    const std::string line = Trim(raw_line);
    if (line.empty())
    {
        out.kind = ConsoleCommand::Kind::kNone; // 回车 = 回软件零点
        return out;
    }

    if (line == "h" || line == "help" || line == "?")
    {
        out.kind = ConsoleCommand::Kind::kHelp;
    }
    else if (line == "p" || line == "print" || line == "state")
    {
        out.kind = ConsoleCommand::Kind::kState;
    }
    else if (line == "hold")
    {
        out.kind = ConsoleCommand::Kind::kHold;
    }
    else if (line == "stop" || line == "free")
    {
        out.kind = ConsoleCommand::Kind::kStop;
    }
    else if (line == "q" || line == "quit" || line == "exit")
    {
        out.kind = ConsoleCommand::Kind::kQuit;
    }
    else if (line == "m" || line == "mark")
    {
        out.kind = ConsoleCommand::Kind::kMark;
    }
    else if (line == "goto-mark" || line == "gm")
    {
        out.kind = ConsoleCommand::Kind::kGoMark;
    }
    else if (line == "expect")
    {
        out.kind = ConsoleCommand::Kind::kExpect;
    }
    else if (line == "fix")
    {
        out.kind = ConsoleCommand::Kind::kFix;
    }
    else if (line == "raw")
    {
        out.kind = ConsoleCommand::Kind::kGoRaw;
    }
    else if (line.compare(0, 5, "reset") == 0)
    {
        out.kind = ConsoleCommand::Kind::kReset;
        out.arg = Trim(line.size() > 5 ? line.substr(5) : std::string());
    }
    else if (line.compare(0, 7, "offset ") == 0)
    {
        out.kind = ConsoleCommand::Kind::kOffsetAbs;
        out.value = std::atof(line.c_str() + 7);
    }
    else if (line.size() > 1 && line[0] == 'o' && (line[1] == '+' || line[1] == '-'))
    {
        out.kind = ConsoleCommand::Kind::kOffsetRel;
        const double d = std::atof(line.c_str() + 1);
        out.value = d;
    }
    else if (IsNumberLike(line[0]))
    {
        // 纯数字 = 去那个角度；带前导 +/- 视为相对增量，便于找记号笔位置
        const bool relative = (line[0] == '+' || line[0] == '-');
        out.kind = relative ? ConsoleCommand::Kind::kJog : ConsoleCommand::Kind::kGoTo;
        out.value = std::atof(line.c_str());
    }
    else
    {
        out.kind = ConsoleCommand::Kind::kUnknown;
        out.arg = line;
    }
    return out;
}

const char* HelpText()
{
    return "命令：\n"
           "  state(p)          看账本：pos tick / turn_base / offset / 在线 / 事件\n"
           "  reset [here|raw]  把此刻定义为软件零点；无参时问一句是否先回到编码器真值零点\n"
           "  raw               去编码器真值零点（上电首帧 pos=0 的那个候选零点）\n"
           "  0                 回软件零点（回车等效）\n"
           "  <角度>            去相对软件零点的角度（度），例如 30 / -45\n"
           "  +<角度> / -<角度> 相对当前位置挪这么多度（找记号笔位置用）\n"
           "  offset <度>       直接设置软件零点偏移量\n"
           "  o+30 / o-30       在现有偏移上加减（任务书③ 的“正向偏移 30°”）\n"
           "  mark / goto-mark  记下 / 回到记号笔那个点\n"
           "  expect / fix      与记录值对照（差≈整数个区间就是上电落在别的候选零点）/ 按建议修正\n"
           "  hold / stop       位置保持 / 零力矩（卸力）\n"
           "  q                 先卸力再退出\n";
}

} // namespace motor_bench
