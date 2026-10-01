/**
 * @file format.hpp
 * @brief 给人看的格式化：角度按"±圈数 ± 一个绝对值小于 360 的度数"显示。
 */

#pragma once

#include "motor/counts.hpp"

#include <string>

namespace motor
{

/**
 * 角度显示（截断式）：x = k×360° + r，k = trunc(x/360)，r 与 x 同号且 |r| < 360。
 * 例：+3 圈 + 243.456°、+0 圈 - 0.009°、-1 圈 - 3.000°。
 */
std::string format_output_angle(Counts counts);

/** 角度 + 原始计数：+2 圈 + 45.000°（+622592 计数） */
std::string format_output_angle_with_counts(Counts counts);

} // namespace motor
