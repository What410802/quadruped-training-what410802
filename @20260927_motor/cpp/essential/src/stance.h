// 站姿（控制目标）与量测：这两件事与"电机怎么建模"无关，所以单独一个头文件。
//
// 本文件是 [`../../src/stance.h`](../../src/stance.h) 的最简版，三点不同：
//   * **没有 `Search`** —— 站姿预先算好存在 `<任务目录>/models/stance.txt` 里，启动时由
//     stance_file.h 加载（那个文件是完整版搜出来写的；站姿只由模型决定，所以每次搜出来都一样）；
//   * 地面一律水平，所以没有 `Plane` 及其"相对地面法向"的那套换算——高度就是世界 z、
//     竖直度就是机身 z 轴与世界 z 轴的夹角、漂移就是水平位移（那个版本为什么要跟着地面法向走，
//     见那边的文件头）；
//   * `Smoothstep`（斜坡插值）与 `JointAngles`（读关节角）搬去了 state.h —— 那两个只有状态机用，
//     住在这里会让"站姿与量测"这个概念不纯。
//
// 站姿为什么不能直接用模型默认位形（这条仍然要看）：默认位形（所有关节 = 0）对膝关节是**越界**的
// （本模型 calf 限位约 ±[0.85, 2.5] rad），一开场就被限位力踢出去，症状是"与增益无关的崩溃"；
// 而且即使把膝掰进合法区间，质心也落在四足中心后面 0.18 m。完整实测与成因见
// `@20260923_mujoco/docs/stand.md`（「控制律与站姿」一节）。
// 完整版那套搜索（膝取几个合法弯曲量、大腿在限位内扫一遍、每次把基座平移到"最低那只脚底面刚好
// 贴地"、取"质心水平投影离四足中心最近"的一组）就在上面那个文件里，这个文件只负责"用哪个站姿"。
#pragma once

#include <mujoco/mujoco.h>

#include <algorithm>
#include <cmath>
#include <vector>

namespace stance {

// 脚 = 模型里那 4 个半径为 2 cm 的**碰撞**球（contype≠0 且 type=SPHERE；视觉球 contype=0）。
// 用几何位置而不是接触点，这样"脚还没着地"时也能搜。
inline std::vector<int> FindFeet(const mjModel *m, double *radius) {
    std::vector<int> feet;
    for (int g = 0; g < m->ngeom; ++g) {
        if (m->geom_type[g] == mjGEOM_SPHERE && m->geom_contype[g] != 0) {
            feet.push_back(g);
            if (radius != nullptr)
                *radius = m->geom_size[3 * g];
        }
    }
    return feet;
}

// 按**执行器顺序**取当前关节角（12 个）的那个函数搬去了 state.h（只有状态机用）

struct Metrics {
    int feet = 0;        // 四足触地数（只认 4 个脚底球，见 Measure）
    double z = 0.0;      // 基座高度 [m]（世界 z）
    double tilt_deg = 0; // 机身 z 轴与世界 z 轴的夹角 [°]（= 竖直度）
    double xy = 0.0;     // 基座相对参考点的水平位移 [m]
};

// 机身 z 轴（世界系）与竖直方向的夹角：把四元数转成旋转矩阵，第三列就是机身 z 轴
inline double TiltDeg(const double *quat) {
    double rot[9];
    mju_quat2Mat(rot, quat);
    return std::acos(std::clamp(rot[8], -1.0, 1.0)) * 180.0 / M_PI;
}

// "四足触地"只认那 4 个脚底球：趴卧时躯干/小腿也压在地面上，那些接触不能算"足"，
// 否则"没站起来"也会被数成四足触地。ref = 参考点（起点基座位置，可为 nullptr = 不算漂移）。
inline Metrics Measure(const mjModel *m, const mjData *d, const std::vector<int> &feet,
                       const double *ref = nullptr) {
    Metrics s;
    s.z = d->qpos[2];
    s.tilt_deg = TiltDeg(d->qpos + 3);
    s.xy = ref == nullptr ? 0.0
                          : std::hypot(d->qpos[0] - ref[0], d->qpos[1] - ref[1]);
    std::vector<int> hit;
    for (int c = 0; c < d->ncon; ++c) {
        const int g1 = d->contact[c].geom[0], g2 = d->contact[c].geom[1];
        const bool floor1 = m->geom_bodyid[g1] == 0, floor2 = m->geom_bodyid[g2] == 0;
        if (floor1 == floor2)
            continue; // 只看"机器人 ↔ 地面"的接触
        const int foot = floor1 ? g2 : g1;
        if (std::find(feet.begin(), feet.end(), foot) == feet.end())
            continue; // 不是脚底球（躯干/小腿）→ 不算触地
        if (std::find(hit.begin(), hit.end(), foot) == hit.end())
            hit.push_back(foot);
    }
    s.feet = static_cast<int>(hit.size());
    return s;
}

// 斜坡插值 Smoothstep 搬去了 state.h（只有它用）

// 目标姿态：站姿文件给的就是这两样（外加"文件与模型对得上"这个校验结果）。
// 完整版还带 bend / frac / com_err / feet（搜索的内部量，日志里会报），最简版不搜也不报，就不留了。
struct Target {
    std::vector<double> q; // 目标关节角（执行器顺序）
    double z = 0.0;        // 该姿态下的基座高度 [m]
    bool ok = false;       // 文件加载成功（--start stance 要靠它判断能不能用）
};

} // namespace stance
