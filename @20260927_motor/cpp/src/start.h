// 起点：把狗摆到 `--start` 指定的位形，以及"回到起点"（= 窗口里按 R / 脚本里的 reset）。
//
// 从 main.cpp 搬出来（行为逐字不变）。为什么它是一个独立的头文件而不是并进 observation.h：
// 这里做的是**改状态**（写 qpos、复位、切回阻尼），observation.h 做的是**读状态**，
// 两者的关键词不同、读代码时的目的也不同。
//
// 两条容易踩的约束（都是实测出来的，别顺手"简化"掉）：
//   * 复位要**保留仿真时间轴**：斜坡进度、脚本时刻、录像出帧都按 d->time 走，mj_resetData 会把
//     time 清零，那样"按 R 之后"的目标斜坡就卡在起点——狗塌下去再也起不来；
//   * 倾斜地面时先摆水平姿态、再把狗**刚体旋转**到与地面同朝向（相对几何不变 ⇒ 站姿搜索结果照旧成立）。
//     为什么不能改成"按到平面的法向距离"来摆：见下面的注释（实测差 5 mm，反而把狗往平面里压）。
#pragma once

#include "ground.h" // 倾斜地面那一支要用 ground::GroundFeet（见上面的第二条约束）
#include "observation.h"
#include "state.h"
#include "stance.h"

#include <mujoco/mujoco.h>

#include <cmath>
#include <cstdio>
#include <string>
#include <vector>

namespace start {

// 把狗摆到 --start 指定的起点（搜索会改 qpos，所以每次复位都调用它）
inline bool Pose(const mjModel *m, mjData *d, const std::string &start,
                 const stance::Target &target, const std::vector<int> &feet, double foot_radius,
                 const stance::Plane &plane) {
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
    if (!plane.level()) {
        // 倾斜地面：上面几支给的都是"水平地面"下的姿态，这里统一把狗旋到与地面同一朝向。
        // raw / stance：旋转后沿新法向落到斜面上（相对几何不变 ⇒ 站姿搜索结果照旧成立）；
        // rest：把趴卧位形**刚体旋转**（偏移与朝向一起转）—— 用"基座到平面的法向距离"算会得到
        //       0.1449·cos(pitch)（15° 时差 5 mm），反而把狗往平面里压；
        // side：只转朝向，z 已经在上面按"悬空 0.25 m"抬过了（侧躺本来就不着地）。
        if (start == "rest") {
            double offset[3], rotated[3], q_rest[4];
            mju_sub3(offset, d->qpos, plane.pt);
            mju_copy4(q_rest, d->qpos + 3);
            mju_mulQuat(d->qpos + 3, plane.quat, q_rest); // R ∘ q_rest
            mju_rotVecQuat(rotated, offset, plane.quat);  // 偏移也跟着转
            mju_add3(d->qpos, rotated, plane.pt);
            mj_forward(m, d);
        } else if (start == "side") {
            double q_side[4];
            mju_copy4(q_side, d->qpos + 3);
            mju_mulQuat(d->qpos + 3, plane.quat, q_side);
            mj_forward(m, d);
        } else { // raw / stance
            mju_copy4(d->qpos + 3, plane.quat);
            mj_forward(m, d);
            ground::GroundFeet(m, d, feet, foot_radius, plane);
        }
    }
    mj_forward(m, d);
    d->time = t_keep;
    return true;
}

// 回到起点（= 窗口里按 R / 脚本里的 reset）：姿态复位到 --start，状态切回上电默认的阻尼模式，
// 并打印一行日志“回到了哪、姿态变化多少”。**注意**：切回阻尼后狗会再次自然塌下（这正是上电后的样子），
// 想从起点重新站起来就接着按 S（或脚本里再给一个 stand）。
inline void Reset(const mjModel *m, mjData *d, const std::string &start, const stance::Target &target,
                  const std::vector<int> &feet, double foot_radius, const stance::Plane &ground,
                  ctrl::StateMachine *sm, const double *ref) {
    const observation::Snapshot before = observation::Sample(m, d, feet, ref, ground);
    if (!Pose(m, d, start, target, feet, foot_radius, ground)) {
        std::printf("重置失败（--start %s）\n", start.c_str());
        return;
    }
    const observation::Snapshot after = observation::Sample(m, d, feet, ref, ground);
    sm->Request(ctrl::State::Damping, d);
    std::printf("重置：回到 --start %s（t=%.3f s 保留）；基座 z %.4f → %.4f m、竖直度 %.2f° → "
                "%.2f°；状态 → %s（会自然塌下，接着按 S 就能从起点重新起身）\n",
                start.c_str(), d->time, before.z, after.z, before.tilt, after.tilt,
                ctrl::Name(sm->state()));
}

} // namespace start
