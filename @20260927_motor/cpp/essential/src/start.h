// 起点：把狗摆到 `--start` 指定的位形。
//
// 为什么它是一个独立的头文件：写 qpos/复位这件事与"怎么读状态"（observation.h）、"控制怎么算"（state.h）
// 都不同，它是"摆姿势"这一件事。
//
// 本文件是 [`../../src/start.h`](../../src/start.h) 的最简版，两处不同：
//   * 地面一律水平，所以没有"先把狗摆成水平姿态、再刚体旋转到地面朝向"那一支，也不再需要 ground.h
//     （`Pose` 因此少了 feet / foot_radius / plane 三个参数）；
//   * 那边的 `start::Reset`（回到起点 = 摆位 + 前后对比 + 切回阻尼）在这里**没有**：那是一个胶水函数，
//     在 `../src` 里有窗口与录像两个调用点才值得成函数；最简版只有"按 R"一个调用点，就写在 main.cpp 的
//     按键分支里，跟它被使用的地方摆在一起。
//
// 一条容易踩的约束（实测出来的，别顺手"简化"掉）：复位要**保留仿真时间轴**——斜坡进度按 d->time 走，
// mj_resetData 会把 time 清零，那样"按 R 之后"的目标斜坡就卡在起点（狗塌下去再也起不来）。
#pragma once

#include "stance.h"

#include <mujoco/mujoco.h>

#include <cmath>
#include <cstdio>
#include <string>

namespace start {

// 把狗摆到 --start 指定的起点（搜索会改 qpos，所以每次复位都调用它）
inline bool Pose(const mjModel *m, mjData *d, const std::string &start,
                 const stance::Target &target) {
    // 复位姿态但**保留仿真时间轴**：斜坡进度、脚本时刻、录像出帧都按 d->time 走，
    // mj_resetData 会把 time 清零，那样"按 R 之后"的目标斜坡就卡在起点（实测：狗塌下去再也起不来）。
    const double t_keep = d->time;
    if (start == "raw") {
        mj_resetData(m, d); // 模型原姿态：直立直腿、脚底刚好触地
    } else if (start == "stance") {
        if (!target.ok)
            return false;
        mj_resetData(m, d);
        for (int i = 0; i < m->nu; ++i)
            d->qpos[m->jnt_qposadr[m->actuator_trnid[2 * i]]] = target.q[static_cast<size_t>(i)];
        d->qpos[2] = target.z; // 搜索里算出来的基座高度
    } else if (start == "rest") {
        if (m->nkey == 0) {
            std::fprintf(stderr, "场景里没有 keyframe，无法用 --start rest\n");
            return false;
        }
        mj_resetDataKeyframe(m, d, 0); // 场景自带的趴卧姿态
    } else if (start == "side") {
        mj_resetData(m, d);
        // 侧躺：基座绕 x 轴转 90°、再抬高 0.25 m —— 用来验证"任意初始位置"
        const double s = std::sin(M_PI / 4.0), c = std::cos(M_PI / 4.0);
        d->qpos[3] = c;
        d->qpos[4] = s;
        d->qpos[5] = 0.0;
        d->qpos[6] = 0.0;
        d->qpos[2] += 0.25;
    } else {
        std::fprintf(stderr, "未知起点：%s\n", start.c_str());
        return false;
    }
    mj_forward(m, d);
    d->time = t_keep;
    return true;
}

} // namespace start
