/**
 * @file console.hpp
 * @brief 验收程序的命令行：把一行输入解析成一条命令，并给帮助文本。
 *
 * 命令表（详见 cpp_part2/docs/zero_semantics.md §5）：
 *   state(p) 看账本 | reset [here|raw] 定零点 | raw 去编码器真值零点 | 0 去软件零点
 *   <角度> 去相对软件零点的角度 | +d/-d 相对当前位置挪 | offset <度> 设偏移 | o+30/o-30 加减偏移
 *   mark 记记号笔 | goto-mark | expect | fix | hold | stop | q
 */
#pragma once

#include <string>

namespace motor_bench
{

struct ConsoleCommand
{
    enum class Kind
    {
        kNone, // 空行（回车）＝回软件零点
        kHelp,
        kState,
        kGoTo,      // value = 角度（相对软件零点）
        kJog,       // value = 相对当前位置的角度增量
        kGoRaw,     // 去编码器真值零点
        kReset,     // arg = "here" / "raw" / ""（空 = 交互式问一句）
        kOffsetAbs, // value = 目标 offset（度）
        kOffsetRel, // value = offset 增量（度）
        kMark,
        kGoMark,
        kExpect,
        kFix,
        kHold,
        kStop,
        kQuit,
        kUnknown,
    };

    Kind kind = Kind::kNone;
    double value = 0.0; // 角度/偏移（度）
    std::string arg;    // reset 的参数、未知命令的原文
};

/** 解析一行；不认识时返回 kUnknown 并把原文放进 arg */
ConsoleCommand ParseCommand(const std::string& line);

/** 帮助文本（`h`） */
const char* HelpText();

} // namespace motor_bench
