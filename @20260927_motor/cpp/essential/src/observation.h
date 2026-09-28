// 观测：把"这一次运行现在是什么状态"取成一行数（四足触地数、基座高度、竖直度、漂移、最大关节速度/力矩），
// 外加"算不算起身完成"这个判据。
//
// 从 main.cpp 搬出来（行为逐字不变）：原先它散在匿名命名空间里，和"起点怎么摆""HUD 怎么画""判定怎么打"
// 混在一起。这里只回答两个问题——**量什么**（Snapshot/Sample）与**算不算到位**（StoodUp）；
// 至于"任务判定通过与否"（退出码 0/2）用的阈值不同，那一段留在 main 里。
//
// 量测本身（四足触地 / 高度 / 倾斜 / 漂移的口径）在 stance.h 的 stance::Metrics，
// 本文件只是把一次采样拍平成一行数、方便打印与比较。
//
// 本文件是 [`../../src/observation.h`](../../src/observation.h) 的最简版：那边每个函数末尾还要传一个
// `stance::Plane`（地面），这里地面一律水平，所以不用传。
#pragma once

#include "stance.h"

#include <mujoco/mujoco.h>

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <vector>

namespace observation {

// 一行指标：四足触地数、基座高度、竖直度、漂移、最大关节速度、最大力矩
struct Snapshot {
    double t = 0, z = 0, tilt = 0, xy = 0, qvel_max = 0, ctrl_max = 0;
    int feet = 0;
};

inline Snapshot Sample(const mjModel *m, const mjData *d, const std::vector<int> &feet,
                       const double *ref) {
    Snapshot s;
    s.t = d->time;
    const stance::Metrics mm = stance::Measure(m, d, feet, ref);
    s.feet = mm.feet;
    s.z = mm.z;
    s.tilt = mm.tilt_deg;
    s.xy = mm.xy;
    for (int v = 0; v < m->nv; ++v)
        s.qvel_max = std::max(s.qvel_max, std::fabs(d->qvel[v]));
    for (int a = 0; a < m->nu; ++a)
        s.ctrl_max = std::max(s.ctrl_max, std::fabs(d->ctrl[a]));
    return s;
}

inline void PrintSnapshot(const char *label, const Snapshot &s) {
    std::printf("%-22s t=%6.3f s  z=%.4f m  竖直度 %5.2f°  四足触地 %d  xy %.4f m  "
                "max|q̇| %.3f  max|τ| %.2f\n",
                label, s.t, s.z, s.tilt, s.feet, s.xy, s.qvel_max, s.ctrl_max);
}

// “起身完成” = 四足触地 + 高度到位 + 机身基本竖直。只看高度不行：从原姿态（基座 0.5786，
// 比站姿还高）刚开始键时它已经“比目标高”了，会误判成“0.00 s 就起身完成”。
inline bool StoodUp(const Snapshot &s, const stance::Target &target) {
    return s.feet == 4 && std::fabs(s.z - target.z) <= 0.03 && s.tilt <= 10.0;
}

} // namespace observation
