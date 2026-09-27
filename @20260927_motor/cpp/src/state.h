// 控制程序的状态机——这次培训任务的正文。两个状态，切换**只改指令**，
// 电机侧始终是同一条 MIT 公式（见 motor.h）：
//
//   阻尼模式：kp = 0、kd = --kd-damp、pos/vel/ff = 0 ⇒ τ = −kd·q̇。
//             这就是讲义 §1.3 的"阻尼模式"：像粘稠液体，甩一下就停。没有位置项，所以它
//             永远不会自己站起来——上电默认停在这个状态。
//   站立模式：kp/kd = --kp/--kd（默认 80 / 3，取讲义 §1.4 提到的实机输出侧配置那一组），
//             位置项目标 q_des 从"按下按键那一刻的关节角"用 smoothstep 推到站姿。控制器没变，
//             变的只是随时间的目标 ⇒ 不管起点是趴卧、半站还是还在往下掉，同一段代码都能把它
//             带回站姿（不是瞬移，也不会一路打满力矩硬拉）。
//
// 斜坡时长按**按下那一刻的姿态**自动选（`--ramp auto`，默认）：
//   * 还在站姿附近（基座高度 ≥ 0.9×站姿 且 竖直度 ≤ 30°）→ 0.1 s：必须赶紧收腿，
//     否则等它倒下去就来不及了（实测 raw 起点 0.1 s ✓ / 1.5 s ✗ 倒）；
//   * 已经趴下/躺着 → 1.5 s：慢慢起，猛拉会被自己掀翻（实测趴卧 1.5 s ✓ / 0.1 s ✗ 翻过去）。
// 想看固定斜坡就写 `--ramp 1.5`（这时两个分支都用这个值）。
//
// 切回阻尼 = 松开位置项，狗在重力下自己塌回去——这本身就是"阻尼"这一项的演示。
// 切换是幂等的：重复按同一个键不会重启斜坡。
#pragma once

#include "motor.h"
#include "stance.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <string>
#include <utility>
#include <vector>

namespace ctrl {

enum class State { Damping, Standing };

inline const char *Name(State s) {
    return s == State::Damping ? "阻尼模式" : "站立模式";
}

// 窗口 HUD 只能用 ASCII：MuJoCo 内置位图字体只覆盖 ASCII，中文/希腊字母/·/° 都会画成乱码块，
// 所以 HUD 里用英文名，终端日志照旧用中文（终端字体没问题）。
inline const char *NameAscii(State s) {
    return s == State::Damping ? "DAMPING" : "STANDING";
}

// 从字符串解析状态（给脚本用：--script "1:stand,5:damp"）
inline bool ParseState(const std::string &text, State *out) {
    if (text == "damp" || text == "damping") {
        *out = State::Damping;
        return true;
    }
    if (text == "stand" || text == "standing") {
        *out = State::Standing;
        return true;
    }
    return false;
}

// 一处集中放状态机用到的参数，省得构造函数一长串位置参数
struct Config {
    double kp = 80.0;      // 站立模式的位置刚度（关节侧）
    double kd = 3.0;       // 站立模式的阻尼
    double kd_damp = 0.5;  // 阻尼模式的阻尼
    double ramp = 1.5;     // 固定斜坡时长（--ramp SEC 时用）
    double ramp_fast = 0.1; // auto：还在站姿附近时用这个（赶紧收腿）
    double z_stand = 0.5;  // 站姿的基座高度（auto 判断"还在站姿附近"用）
    bool auto_ramp = true; // 默认按姿态自动选斜坡
    bool gravity_comp = false;
};

class StateMachine {
  public:
    StateMachine(const mjModel *m, motor::JointMotors *motors, std::vector<double> q_stand,
                 const Config &cfg)
        : m_(m), motors_(motors), q_stand_(std::move(q_stand)), cfg_(cfg) {
        qadr_.resize(static_cast<size_t>(m->nu));
        vadr_.resize(static_cast<size_t>(m->nu));
        for (int i = 0; i < m->nu; ++i) {
            const int j = m->actuator_trnid[2 * i]; // 该执行器作用的关节 id
            qadr_[static_cast<size_t>(i)] = m->jnt_qposadr[j];
            vadr_[static_cast<size_t>(i)] = m->jnt_dofadr[j];
        }
        q_from_ = q_stand_;
        q_des_ = q_stand_;
        chosen_ramp_ = cfg_.auto_ramp ? cfg_.ramp_fast : cfg_.ramp;
        if (cfg_.auto_ramp)
            std::snprintf(desc_, sizeof(desc_),
                          "阻尼模式：kp=0 kd=%.3g；站立模式：kp=%.3g kd=%.3g、斜坡 auto"
                          "（近站姿 %.2f s / 趴卧 %.2f s）%s",
                          cfg_.kd_damp, cfg_.kp, cfg_.kd, cfg_.ramp_fast, cfg_.ramp,
                          cfg_.gravity_comp ? "、叠加 qfrc_bias 前馈" : "");
        else
            std::snprintf(desc_, sizeof(desc_),
                          "阻尼模式：kp=0 kd=%.3g；站立模式：kp=%.3g kd=%.3g、斜坡固定 %.2f s%s",
                          cfg_.kd_damp, cfg_.kp, cfg_.kd, cfg_.ramp,
                          cfg_.gravity_comp ? "、叠加 qfrc_bias 前馈" : "");
    }

    State state() const { return state_; }
    const char *desc() const { return desc_; }
    int switches() const { return switches_; }
    const char *last_event() const { return last_event_; }
    // 同一条事件，但只有 ASCII —— 给窗口 HUD 用（内置字体没有 CJK 字形）
    const char *last_event_ascii() const { return last_event_ascii_; }
    const std::vector<double> &q_des() const { return q_des_; }
    // 本次起身实际用的斜坡时长（auto 时是按下那一刻选出来的）
    double chosen_ramp() const { return chosen_ramp_; }

    // 斜坡进度 0→1（阻尼模式下不看它）
    double Alpha(const mjData *d) const {
        if (chosen_ramp_ <= 0.0)
            return 1.0;
        return stance::Smoothstep((d->time - ramp_t0_) / chosen_ramp_);
    }

    bool Ramping(const mjData *d) const {
        return state_ == State::Standing && chosen_ramp_ > 0.0 &&
               (d->time - ramp_t0_) < chosen_ramp_;
    }

    // 切换请求（键盘回调 / 脚本里调；返回 true 表示状态真的变了）
    bool Request(State s, const mjData *d) {
        if (s == state_)
            return false; // 幂等：重复按同一个键不重启斜坡
        state_ = s;
        ++switches_;
        if (s == State::Standing) {
            // 起点 = 按下按键那一刻的关节角：这就是"从任意初始位置、连续地站起来"里"任意"的落点
            q_from_ = stance::JointAngles(m_, d);
            ramp_t0_ = d->time;
            const bool near = NearStance(d);
            if (cfg_.auto_ramp)
                chosen_ramp_ = near ? cfg_.ramp_fast : cfg_.ramp;
            else
                chosen_ramp_ = cfg_.ramp;
            std::snprintf(last_event_, sizeof(last_event_),
                          "按键 → 站立模式：q_des 在 %.2f s 内推到站姿（%s）", chosen_ramp_,
                          near ? "还在站姿附近，得快收腿" : "已经趴下，慢慢起");
            std::snprintf(last_event_ascii_, sizeof(last_event_ascii_),
                          "key -> STANDING: q_des ramps to stance in %.2f s (%s)", chosen_ramp_,
                          near ? "near stance: hurry" : "lying: go slowly");
        } else {
            std::snprintf(last_event_, sizeof(last_event_),
                          "按键 → 阻尼模式：松开位置项，只留 −kd·q̇");
            std::snprintf(last_event_ascii_, sizeof(last_event_ascii_),
                          "key -> DAMPING: position term released (tau = -kd*qdot)");
        }
        return true;
    }

    // 每步调用一次：按当前状态组好 12 个关节的指令，交给电机模型（之后由它 Apply 到 d->ctrl）
    void Update(const mjData *d) {
        if (state_ == State::Damping) {
            motors_->Set(motor::Damping(cfg_.kd_damp)); // τ = −kd·q̇
            return;
        }
        const double a = Alpha(d);
        for (size_t i = 0; i < q_des_.size(); ++i)
            q_des_[i] = q_from_[i] + (q_stand_[i] - q_from_[i]) * a;
        for (int i = 0; i < motors_->size(); ++i) {
            motor::Cmd c = motor::Mit(q_des_[static_cast<size_t>(i)], cfg_.kp, cfg_.kd);
            if (cfg_.gravity_comp)
                c.ff = d->qfrc_bias[vadr_[static_cast<size_t>(i)]]; // 试验用：实机拿不到这个量
            motors_->Set(i, c);
        }
    }

  private:
    // "还在站姿附近"：基座没怎么降、机身也没歪 —— 这时必须快收腿（raw 起点实测）
    bool NearStance(const mjData *d) const {
        double rot[9];
        mju_quat2Mat(rot, d->qpos + 3);
        const double tilt = std::acos(std::clamp(rot[8], -1.0, 1.0)) * 180.0 / M_PI;
        return d->qpos[2] >= 0.9 * cfg_.z_stand && tilt <= 30.0;
    }

    const mjModel *m_ = nullptr;
    motor::JointMotors *motors_ = nullptr;
    State state_ = State::Damping; // 任务要求：上电 = 阻尼模式
    std::vector<double> q_stand_, q_from_, q_des_;
    std::vector<int> qadr_, vadr_;
    Config cfg_;
    double chosen_ramp_ = 1.5;
    double ramp_t0_ = 0.0;
    int switches_ = 0;
    char desc_[256] = "";
    char last_event_[256] = "（还没切换过，当前是上电默认的阻尼模式）";
    char last_event_ascii_[128] = "startup: DAMPING (power-on default)";
};

} // namespace ctrl
