// 站姿（控制目标）与量测：这两件事与"电机怎么建模"无关，所以单独一个头文件。
//
// 目标为什么不能直接用模型默认位形：默认位形（所有关节 = 0）对膝关节是**越界**的
// （本模型 calf 限位约 ±[0.85, 2.5] rad），一开场就被限位力踢出去，症状是"与增益无关的崩溃"；
// 而且即使把膝掰进合法区间，质心也落在四足中心后面 0.18 m。完整实测与成因见
// `@20260923_mujoco/docs/stand.md`（「控制律与站姿」一节）。
//
// 所以这里沿用那份 demo 的**搜索**：膝取几个合法弯曲量、大腿在限位内扫一遍，每次把基座平移到
// "最低那只脚底面刚好贴地"，取"质心水平投影离四足中心最近"的一组。搜索不读 keyframe、不改 XML。
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

// 按**执行器顺序**取当前关节角（12 个）：控制目标、斜坡起点都用这个顺序，不写死关节名
inline std::vector<double> JointAngles(const mjModel *m, const mjData *d) {
    std::vector<double> q(static_cast<size_t>(m->nu));
    for (int i = 0; i < m->nu; ++i)
        q[static_cast<size_t>(i)] = d->qpos[m->jnt_qposadr[m->actuator_trnid[2 * i]]];
    return q;
}

struct Metrics {
    int feet = 0;        // 四足触地数（只认 4 个脚底球，见 Measure）
    double z = 0.0;      // 基座高度 [m]
    double tilt_deg = 0; // 机身 z 轴与世界 z 轴的夹角 [°]
    double xy = 0.0;     // 基座相对参考点的水平位移 [m]
};

// "四足触地"只认那 4 个脚底球：趴卧时躯干/小腿也压在地面上，那些接触不能算"足"，
// 否则"没站起来"也会被数成四足触地。
inline Metrics Measure(const mjModel *m, const mjData *d, const std::vector<int> &feet, double ref_x,
                       double ref_y) {
    Metrics s;
    s.z = d->qpos[2];
    double rot[9];
    mju_quat2Mat(rot, d->qpos + 3);
    s.tilt_deg = std::acos(std::clamp(rot[8], -1.0, 1.0)) * 180.0 / M_PI;
    s.xy = std::hypot(d->qpos[0] - ref_x, d->qpos[1] - ref_y);
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

inline double Smoothstep(double u) {
    const double x = std::clamp(u, 0.0, 1.0);
    return x * x * (3.0 - 2.0 * x);
}

struct Target {
    std::vector<double> q;   // 目标关节角（执行器顺序）
    double z = 0.0;          // 该姿态下的基座高度
    double bend = 0.0;       // 搜出来的膝弯曲量 [rad]
    double frac = 0.0;       // 大腿 = frac × 膝
    double com_err = 0.0;    // 质心水平投影离四足中心的距离 [m]，越小越站得住
    int feet = 0;
    bool ok = false;
};

// 搜站姿。注意：**会改动传入的 mjData 的 qpos**（调用方之后自己复位到想要的起点）。
inline Target Search(const mjModel *m, mjData *d, const std::vector<int> &feet, double foot_radius) {
    Target best;
    if (feet.empty())
        return best;

    const int nleg = m->nu / 3;
    std::vector<double> calf_sign(static_cast<size_t>(nleg), 1.0);
    for (int leg = 0; leg < nleg; ++leg) {
        const int j = m->actuator_trnid[2 * (3 * leg + 2)]; // 该腿的膝
        // 左右腿的限位方向相反，符号由限位区间决定，不靠猜
        calf_sign[static_cast<size_t>(leg)] = (m->jnt_range[2 * j + 1] < 0.0) ? -1.0 : 1.0;
    }

    // 当前姿态下：最低脚的球心高度、四足中心的水平位置、质心的水平位置
    const auto probe = [&](double *foot_z, double *foot_xy, double *com_xy) {
        double minz = 1e9, fx = 0.0, fy = 0.0;
        for (int g : feet) {
            minz = std::min(minz, static_cast<double>(d->geom_xpos[3 * g + 2]));
            fx += d->geom_xpos[3 * g];
            fy += d->geom_xpos[3 * g + 1];
        }
        *foot_z = minz;
        foot_xy[0] = fx / static_cast<double>(feet.size());
        foot_xy[1] = fy / static_cast<double>(feet.size());
        com_xy[0] = d->subtree_com[3];
        com_xy[1] = d->subtree_com[4];
        return true;
    };

    const double z0 = d->qpos[2];
    std::vector<double> q_try(static_cast<size_t>(m->nu));
    double best_err = 1e9;
    for (double bend : {0.9, 1.1, 1.3}) {
        for (double frac = 0.1; frac <= 1.0 + 1e-9; frac += 0.05) {
            for (int leg = 0; leg < nleg; ++leg) {
                for (int k = 0; k < 3; ++k) {
                    const int i = 3 * leg + k;
                    const int j = m->actuator_trnid[2 * i];
                    const int adr = m->jnt_qposadr[j];
                    double v = m->qpos0[adr];                  // 髋：保持默认位形
                    if (k == 2)
                        v = calf_sign[static_cast<size_t>(leg)] * bend; // 膝：按限位方向弯
                    if (k == 1)
                        v = -calf_sign[static_cast<size_t>(leg)] * bend * frac; // 大腿：配对
                    if (m->jnt_limited[j])
                        v = std::clamp(v, m->jnt_range[2 * j], m->jnt_range[2 * j + 1]);
                    q_try[static_cast<size_t>(i)] = v;
                    d->qpos[adr] = v;
                }
            }
            d->qpos[2] = z0;
            mj_forward(m, d);
            double fz = 0, fxy[2] = {0, 0}, cxy[2] = {0, 0};
            probe(&fz, fxy, cxy);
            d->qpos[2] = z0 - (fz - foot_radius); // 基座平移到最低脚底面刚好贴地
            mj_forward(m, d);
            double fz2 = 0, fxy2[2] = {0, 0}, cxy2[2] = {0, 0};
            probe(&fz2, fxy2, cxy2);
            const double err = std::hypot(cxy2[0] - fxy2[0], cxy2[1] - fxy2[1]);
            if (err < best_err) {
                best_err = err;
                best.q = q_try;
                best.z = d->qpos[2];
                best.bend = bend;
                best.frac = frac;
                best.com_err = err;
            }
        }
    }
    if (best_err >= 1e9)
        return best;

    // 把最优姿态写回 d，再让它真的“四足触地”：几何上要求“最低脚的球面刚好切地面”，
    // 切点恰好相切时接触点可能因为浮点误差而不生成，所以按 1 mm 步长往下压，
    // 直到真的数出 4 个足底接触（最多 5 mm）。这样可以保证 --start stance 一开场就是四足着地。
    for (int i = 0; i < m->nu; ++i)
        d->qpos[m->jnt_qposadr[m->actuator_trnid[2 * i]]] = best.q[static_cast<size_t>(i)];
    d->qpos[2] = best.z;
    mj_forward(m, d);
    for (int press = 0; press < 5 && Measure(m, d, feet, 0.0, 0.0).feet < 4; ++press) {
        d->qpos[2] -= 0.001;
        mj_forward(m, d);
    }
    best.z = d->qpos[2];
    best.feet = Measure(m, d, feet, 0.0, 0.0).feet;
    best.ok = true;
    return best;
}

} // namespace stance
