// 地面：可调倾角 + 可调摩擦。移植自 @20260923_mujoco/cpp_slope（那边是单独的斜面 demo）。
//
// 为什么把"倾斜"做得这么绕：MuJoCo 的平面 geom（type=plane）是**无限大**的，它的"倾斜"只能靠
// 旋转这个 geom；而地面 geom 的局部位姿本来是零/单位四元数，编译时 m->geom_sameframe[] 被标成 1，
// mj_kinematics 看到它就**直接抄世界体的位姿**、根本不读 geom_pos/geom_quat（源码：
// engine_core_smooth.c 的 mj_kinematics → mj_local2Global(..., m->geom_sameframe[g])）。
// 所以除了写 geom_quat，还必须把 sameframe 清掉，否则"地面转了"只存在于我们自己的 Plane.up 里：
// 碰撞面与渲染出来的地面都不动，狗只是自己歪了 15°。这里加了一道自检（比对 d->geom_xmat）兜住。
//
// 另外两点约定：
//   * **重力不动**（不动 m->opt.gravity）：狗与地面一起转，所以越陡越难站住，这才是这个开关的意义；
//   * 量测（高度/倾斜/漂移）统一相对**地面法向**，由 stance::Plane 提供——倾斜 15° 站好的狗，
//     "相对地面"仍然是竖直的，拿世界 z 去比会误判成"歪了 15°"。
#pragma once

#include <mujoco/mujoco.h>

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <vector>

#include "stance.h"

namespace ground {

// 把平面地面绕 y/x 轴转 (pitch, roll) 度。返回 false = 用不了（没有平面地面 / 自检不过），
// 原因写进 err。**默认 0/0 时是恒等操作**：一行都不改，仿真结果与加这个功能之前逐位相同。
inline bool ApplyTilt(mjModel *m, mjData *d, int floor_geom, double pitch_deg, double roll_deg,
                      stance::Plane *plane, char *err, size_t err_size) {
    if (pitch_deg == 0.0 && roll_deg == 0.0)
        return true;
    if (floor_geom < 0) {
        std::snprintf(err, err_size, "场景里没有名为 floor 的平面地面，--pitch/--roll 用不了");
        return false;
    }
    const double euler[3] = {roll_deg * M_PI / 180.0, pitch_deg * M_PI / 180.0, 0.0};
    double tilt[4];
    mju_euler2Quat(tilt, euler, "xyz"); // 平面的局部 z 轴就是它的法向；0/0 时是单位四元数
    mju_copy4(m->geom_quat + 4 * floor_geom, tilt);
    m->geom_sameframe[floor_geom] = 0; // 见文件头：不清这个，geom_quat 根本不会被读
    mju_copy4(plane->quat, tilt); // 存下来：SetStart 要拿它把狗"刚体旋转"到斜面上
    const double z_axis[3] = {0.0, 0.0, 1.0};
    mju_rotVecQuat(plane->up, z_axis, tilt); // 新法向（世界系）
    for (int k = 0; k < 3; ++k)
        plane->pt[k] = 0.0; // 只换法向、不抬地面：平面仍过原点
    mju_copy4(d->qpos + 3, tilt); // 狗跟着转同一个朝向（相对几何不变 ⇒ 站姿搜索结果照旧成立）
    mj_forward(m, d);
    // 自检：地面 geom 在世界系里的**实际**法向（d->geom_xmat 的第三列）必须等于 plane->up
    const double *xmat = d->geom_xmat + 9 * floor_geom;
    const double up_dot = xmat[2] * plane->up[0] + xmat[5] * plane->up[1] + xmat[8] * plane->up[2];
    if (up_dot < 1.0 - 1e-9) {
        std::snprintf(err, err_size,
                      "倾斜地面失败：想要的法向 (%.3f, %.3f, %.3f)，地面实际法向 (%.3f, %.3f, "
                      "%.3f)（dot=%.6f）",
                      plane->up[0], plane->up[1], plane->up[2], xmat[2], xmat[5], xmat[8], up_dot);
        return false;
    }
    return true;
}

// 沿地面法向把"最低的足底球"落到平面上，再按 0.5 mm 步长轻压，直到真的数出四足接触。
// 为什么要压："最低球的球面刚好切平面"时，接触点可能因为浮点误差而不生成（--start stance
// 一开场就"四足触地 0"）。水平地面（默认）走的是另一条更老的等价路径，见 main.cpp 的 SetStart。
inline void GroundFeet(const mjModel *m, mjData *d, const std::vector<int> &feet, double foot_radius,
                       const stance::Plane &plane) {
    double h_min = 1e9;
    for (int g : feet)
        h_min = std::min(h_min, plane.height(d->geom_xpos + 3 * g) - foot_radius);
    if (h_min < 1e9) {
        for (int k = 0; k < 3; ++k)
            d->qpos[k] -= h_min * plane.up[k];
    }
    mj_forward(m, d);
    for (int i = 0; i < 40 && stance::Measure(m, d, feet).feet < 4; ++i) {
        for (int k = 0; k < 3; ++k)
            d->qpos[k] -= 0.0005 * plane.up[k];
        mj_forward(m, d);
    }
}

// 摩擦 / 接触维度：**两边一起设**。
// MuJoCo 里一对接触的摩擦系数是**两个 geom 逐元素取较大者**（实测：只把地面调到 0.05，
// 接触仍然是足底球自带的 1，狗照旧不滑；把足底也调到 0.05 才真的滑），所以只改地面不生效。
// condim 同理：默认 3 只用第 1 个摩擦系数（滑动），自旋/滚动那两个只有在 condim ≥ 4/6 时才进求解。
inline void SetFriction(mjModel *m, int floor_geom, const std::vector<int> &feet, const double *fric,
                        int condim) {
    if (fric != nullptr) {
        if (floor_geom >= 0)
            std::memcpy(m->geom_friction + 3 * floor_geom, fric, 3 * sizeof(double));
        for (int g : feet)
            std::memcpy(m->geom_friction + 3 * g, fric, 3 * sizeof(double));
    }
    if (condim > 0) {
        if (floor_geom >= 0)
            m->geom_condim[floor_geom] = condim;
        for (int g : feet)
            m->geom_condim[g] = condim;
    }
}

} // namespace ground
