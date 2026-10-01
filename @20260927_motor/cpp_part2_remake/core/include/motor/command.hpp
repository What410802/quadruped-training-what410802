/**
 * @file command.hpp
 * @brief 语句层：切分（换行与分号等效）、解析（含角度单位后缀）与命令定义。
 */

#pragma once

#include "motor/counts.hpp"

#include <string>
#include <vector>

namespace motor
{

enum class CommandKind
{
    kHelp,      // 帮助
    kState,     // 打印账本与状态
    kMove,      // value = 目标角度（相对软件零点）
    kJog,       // value = 相对当前位置的增量
    kZeroMove,  // value = 软件零点沿正方向移动的角度（内部 offset 减同样量）
    kOffsetSet, // value = offset 变量的目标值（高级：复现标定值用）
    kMark,      // 记下标记点
    kMarkGoto,  // 回到标记点
    kHold,      // 位置保持
    kFree,      // 零力矩
    kWait,      // wait_s 秒后再执行后续语句
    kQuit,      // 卸力退出
    kUnknown,   // 解析失败
};

struct Command
{
    CommandKind kind = CommandKind::kUnknown;
    Counts value = 0; // 角度类命令（计数）
    double wait_s = 0.0;
    std::string text; // 原文（回显与报错）
};

/** 按换行与 ';' 切语句（空语句丢弃） */
std::vector<std::string> split_statements(const std::string& text);

/**
 * 解析"角度"记号：数字 + 可选单位后缀（deg / rad / r / rev，大小写不敏感；默认 deg）。
 * 单位都是**输出端**的；不支持表达式运算。成功返回空串，失败返回原因。
 */
std::string parse_output_angle(const std::string& token, Counts* counts);

/** 解析一条语句；失败时 kind = kUnknown 且 error 非空 */
Command parse_command(const std::string& statement, std::string* error);

/** 给操作者看的命令表（help 用） */
const char* command_help_text();

} // namespace motor
