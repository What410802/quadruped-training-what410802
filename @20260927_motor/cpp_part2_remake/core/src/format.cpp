/**
 * @file format.cpp
 * @brief format_output_angle / format_output_angle_with_counts 的实现。
 */

#include "motor/format.hpp"

#include <cmath>
#include <cstdio>

namespace motor
{

std::string format_output_angle(Counts counts)
{
    const double deg = counts_to_output_deg(counts);
    const double turns = std::trunc(deg / 360.0);
    double rest = std::round((deg - turns * 360.0) * 1000.0) / 1000.0;
    double turns_shown = turns;
    // 浮点边界：四舍五入到毫度后可能正好顶到 ±360，挪回上一圈
    if (rest >= 360.0)
    {
        rest -= 360.0;
        turns_shown += 1.0;
    }
    else if (rest <= -360.0)
    {
        rest += 360.0;
        turns_shown -= 1.0;
    }
    char buffer[64];
    std::snprintf(buffer, sizeof(buffer), "%+lld 圈 %+.3f°", static_cast<long long>(turns_shown),
                  rest);
    return std::string(buffer);
}

std::string format_output_angle_with_counts(Counts counts)
{
    char buffer[48];
    std::snprintf(buffer, sizeof(buffer), "%+lld 计数", static_cast<long long>(counts));
    return format_output_angle(counts) + "（" + buffer + "）";
}

} // namespace motor
