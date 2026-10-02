/**
 * @file command.cpp
 * @brief split_statements / parse_output_angle / parse_command 的实现：纯字符串处理，不碰硬件。
 */

#include "motor/command.hpp"

#include <cctype>
#include <cerrno>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace motor
{
namespace
{

std::string trim(const std::string& text)
{
    size_t begin = 0;
    size_t end = text.size();
    while (begin < end && std::isspace(static_cast<unsigned char>(text[begin])) != 0)
    {
        ++begin;
    }
    while (end > begin && std::isspace(static_cast<unsigned char>(text[end - 1])) != 0)
    {
        --end;
    }
    return text.substr(begin, end - begin);
}

bool iequals(const std::string& a, const std::string& b)
{
    if (a.size() != b.size())
    {
        return false;
    }
    for (size_t i = 0; i < a.size(); ++i)
    {
        if (std::tolower(static_cast<unsigned char>(a[i])) !=
            std::tolower(static_cast<unsigned char>(b[i])))
        {
            return false;
        }
    }
    return true;
}

std::vector<std::string> split_words(const std::string& text)
{
    std::vector<std::string> words;
    std::string current;
    for (char c : text)
    {
        if (std::isspace(static_cast<unsigned char>(c)) != 0)
        {
            if (!current.empty())
            {
                words.push_back(current);
                current.clear();
            }
        }
        else
        {
            current.push_back(c);
        }
    }
    if (!current.empty())
    {
        words.push_back(current);
    }
    return words;
}

} // namespace

std::vector<std::string> split_statements(const std::string& text)
{
    std::vector<std::string> statements;
    std::string current;
    for (char c : text)
    {
        if (c == ';' || c == '\n' || c == '\r')
        {
            const std::string one = trim(current);
            if (!one.empty())
            {
                statements.push_back(one);
            }
            current.clear();
        }
        else
        {
            current.push_back(c);
        }
    }
    const std::string one = trim(current);
    if (!one.empty())
    {
        statements.push_back(one);
    }
    return statements;
}

std::string parse_output_angle(const std::string& token, Counts* counts)
{
    const std::string text = trim(token);
    if (text.empty())
    {
        return "缺少数值";
    }
    errno = 0;
    char* end = nullptr;
    const double value = std::strtod(text.c_str(), &end);
    if (end == text.c_str())
    {
        return "不是数字：" + text;
    }
    if (errno == ERANGE || !std::isfinite(value))
    {
        return "数值超范围：" + text;
    }
    const std::string unit = trim(std::string(end));
    if (unit.empty() || iequals(unit, "deg"))
    {
        *counts = output_deg_to_counts(value);
    }
    else if (iequals(unit, "rad"))
    {
        *counts = output_rad_to_counts(value);
    }
    else if (iequals(unit, "r") || iequals(unit, "rev"))
    {
        *counts = output_turns_to_counts(value);
    }
    else if (iequals(unit, "tick") || iequals(unit, "ticks"))
    {
        *counts = std::llround(value); // 转子侧计数：1 转子圈 = 32768 tick = 56.8421°（输出端）
    }
    else
    {
        return "不认识的角度单位：" + unit + "（可用 deg / rad / r / rev / tick）";
    }
    return std::string();
}

Command parse_command(const std::string& statement, std::string* error)
{
    Command command;
    command.text = trim(statement);
    if (error != nullptr)
    {
        error->clear();
    }
    const std::vector<std::string> words = split_words(command.text);
    if (words.empty())
    {
        command.kind = CommandKind::kUnknown;
        if (error != nullptr)
        {
            *error = "空语句";
        }
        return command;
    }
    const std::string& head = words[0];
    const auto fail = [&](const std::string& why)
    {
        command.kind = CommandKind::kUnknown;
        if (error != nullptr)
        {
            *error = why;
        }
        return command;
    };
    const auto need_words = [&](size_t count) { return words.size() == count; };

    if (iequals(head, "help"))
    {
        command.kind = CommandKind::kHelp;
    }
    else if (iequals(head, "state"))
    {
        command.kind = CommandKind::kState;
    }
    else if (iequals(head, "quit") || iequals(head, "exit"))
    {
        command.kind = CommandKind::kQuit;
    }
    else if (iequals(head, "hold"))
    {
        command.kind = CommandKind::kHold;
    }
    else if (iequals(head, "free"))
    {
        command.kind = CommandKind::kFree;
    }
    else if (iequals(head, "mark"))
    {
        if (need_words(1))
        {
            command.kind = CommandKind::kMark;
        }
        else if (need_words(2) && iequals(words[1], "goto"))
        {
            command.kind = CommandKind::kMarkGoto;
        }
        else
        {
            return fail("mark 的用法：mark | mark goto");
        }
    }
    else if (iequals(head, "move") || iequals(head, "jog"))
    {
        if (!need_words(2))
        {
            return fail(head + " 的用法：" + head + " <角度>[deg|rad|r|rev]");
        }
        Counts counts = 0;
        const std::string why = parse_output_angle(words[1], &counts);
        if (!why.empty())
        {
            return fail(why);
        }
        command.kind = iequals(head, "move") ? CommandKind::kMove : CommandKind::kJog;
        command.value = counts;
    }
    else if (iequals(head, "zero"))
    {
        if (!need_words(3) || !iequals(words[1], "move"))
        {
            return fail("zero 的用法：zero move <角度>[deg|rad|r|rev]（把软件零点沿正方向移动该角度）");
        }
        Counts counts = 0;
        const std::string why = parse_output_angle(words[2], &counts);
        if (!why.empty())
        {
            return fail(why);
        }
        command.kind = CommandKind::kZeroMove;
        command.value = counts;
    }
    else if (iequals(head, "offset"))
    {
        if (!need_words(3) || !iequals(words[1], "set"))
        {
            return fail("offset 的用法：offset set <角度>（直接设定内部 offset 变量；日常用 zero move）");
        }
        Counts counts = 0;
        const std::string why = parse_output_angle(words[2], &counts);
        if (!why.empty())
        {
            return fail(why);
        }
        command.kind = CommandKind::kOffsetSet;
        command.value = counts;
    }
    else if (iequals(head, "check"))
    {
        command.kind = CommandKind::kCheck;
        if (words.size() == 1)
        {
            command.has_value = false;
        }
        else if (need_words(2))
        {
            Counts counts = 0;
            const std::string why = parse_output_angle(words[1], &counts);
            if (!why.empty())
            {
                return fail(why);
            }
            command.value = counts;
            command.has_value = true;
        }
        else
        {
            return fail("check 的用法：check [<参考读数>[deg|rad|r|rev|tick]]（缺省用 --pose-ref / 标记点）");
        }
    }
    else if (iequals(head, "fix"))
    {
        if (!need_words(1))
        {
            return fail("fix 的用法：fix（把软件零点按 k 个整格对齐；不动电机）");
        }
        command.kind = CommandKind::kFix;
    }
    else if (iequals(head, "wait"))
    {
        if (!need_words(2))
        {
            return fail("wait 的用法：wait <秒>");
        }
        errno = 0;
        char* end = nullptr;
        const double seconds = std::strtod(words[1].c_str(), &end);
        if (end == words[1].c_str() || *end != '\0' || errno == ERANGE || !std::isfinite(seconds) ||
            seconds < 0.0)
        {
            return fail("wait 的秒数不合法：" + words[1]);
        }
        command.kind = CommandKind::kWait;
        command.wait_s = seconds;
    }
    else
    {
        return fail("没看懂：" + command.text + "（输入 help 看命令）");
    }
    return command;
}

const char* command_help_text()
{
    return "命令（角度单位默认度，可加后缀 deg / rad / r / rev / tick；tick = 转子计数，"
           "32768 tick = 一个转子圈 = 56.8421° 输出端；多条语句用 ; 或换行分隔）：\n"
           "  state                 打印账本与状态\n"
           "  move <角度>           去相对软件零点的角度；默认 offset=0 时 move 0 就是回编码器零点\n"
           "  jog <增量>            相对当前位置挪（带符号）\n"
           "  zero move <角度>      把软件零点沿正方向移动该角度（标定；电机不动，标记点读数减少同样角度）\n"
           "  offset set <角度>     直接把内部 offset 变量设为该角度（复现标定值用；日常用 zero move）\n"
           "  mark | mark goto      记下 / 回到标记点（回零后打标记）\n"
           "  check [<参考>]        只报告：参考缺省用 --pose-ref / 标记点；打印 k 格 + 残差 r 与两种解释\n"
           "  fix                   区间重对齐（offset -= k×C；电机不动；受 max-fixes 限制）\n"
           "  hold | free           位置保持 / 零力矩（可手转）\n"
           "  wait <秒>             推迟后续语句（脚本节拍）\n"
           "  help | quit           本帮助 / 先卸力再退出\n";
}

} // namespace motor
