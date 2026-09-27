// 关节电机模型：把培训讲义（`motor.pdf.md`）§1.2 的 MIT 混合控制搬到仿真里**自己算**。
//
// 实机：驱动板里封好了 FOC 电流环，上层只发 5 个量，而且都是**转子侧**的（手册第 4 节）：
//     τ_rotor = T_ff + K_P·(Pos_des − p) + K_W·(W_des − ω)
// 仿真：我们的执行器是 <motor>（gear=1，data.ctrl 直接就是**关节侧**力矩），所以照 §2.3 的映射
//     （位置/速度 ×N、力矩 ÷N、刚度/阻尼 ÷N²）把同一条公式写在关节侧：
//     τ = τ_ff + kp·(q_des − q) + kd·(q̇_des − q̇)
// 本文件只算关节侧这一条（仿真里没有转子）。转子侧的换算放在 ToRotor()，第二部分对实机时
// 直接用同一组输出侧参数（讲义 §1.4 第 2 条：仿真与实机必须用同一条控制律、同一组值）。
//
// 与"理想力矩源"的差别，按讲义 §1.1 需要补三类，都做成开关（默认全关 = 理想力矩源）：
//   * 限幅：`ctrlrange`（本模型 ±20 N·m）= 恒力矩区的天花板（讲义说 r1_sar 的 black 配置是
//     33.5 N·m，所以给了 --tau-max 覆盖）；
//   * 死区 / 静摩擦：|τ| 小于阈值就当 0（小力矩时摩擦占主导，讲义 §1.1 的第一类非线性）；
//   * 指令延迟 + 编码器噪声：--delay-cycles 个控制周期、--noise N·m 白噪声（固定种子，可复现）。
// 讲义里还有"高速段力矩随转速下降（电压/反电动势限制）"，本仿真**不建**：本模型的关节转速
// 远低于电机基速，且不建它也不改变"给定力矩出多少力矩"的结论（理由见 docs/sim.md）。
#pragma once

#include <mujoco/mujoco.h>

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <random>
#include <vector>

namespace motor {

// 关节侧的 MIT 指令（仿真里真正要算的东西，也是我们思考控制问题时用的那组量）
struct Cmd {
    double ff = 0.0;  // 前馈力矩 τ_ff [N·m]
    double pos = 0.0; // 期望角度 q_des [rad]（要按插值缓慢变化，别给阶跃）
    double vel = 0.0; // 期望角速度 q̇_des [rad/s]
    double kp = 0.0;  // 位置刚度 [N·m/rad]
    double kd = 0.0;  // 速度刚度（阻尼）[N·m·s/rad]
};

// 转子侧（宇树 SDK）的 5 个字段：第二部分对实机时按这张表下发
struct RotorCmd {
    double T = 0.0;   // ⬅ cmd.T
    double Pos = 0.0; // ⬅ cmd.Pos
    double W = 0.0;   // ⬅ cmd.W
    double K_P = 0.0; // ⬅ cmd.K_P
    double K_W = 0.0; // ⬅ cmd.K_W
};

// 输出端（关节）→ 转子（电机）命令：位置/速度 ×N，力矩 ÷N，刚度/阻尼 ÷N²（讲义 §2.3 的表格）
inline RotorCmd ToRotor(const Cmd &c, double gear) {
    RotorCmd r;
    r.T = c.ff / gear;
    r.Pos = c.pos * gear;
    r.W = c.vel * gear;
    r.K_P = c.kp / (gear * gear);
    r.K_W = c.kd / (gear * gear);
    return r;
}

// 反馈方向：转子侧读数 → 输出端角度（讲义 §2.5：q = data.Pos/N + offset，offset 是标定值）
inline double RotorToJointAngle(double rotor_pos, double gear, double offset) {
    return rotor_pos / gear + offset;
}

// 讲义 §1.3：所有模式都是同一条公式的特例。这里把最常用的几个写成小函数，让"模式"在代码里
// 一眼可见——它们最后都会被塞进同一台 JointMotors。
inline Cmd Damping(double kd) {
    return Cmd{0.0, 0.0, 0.0, 0.0, kd}; // 阻尼模式：τ = −kd·q̇（量纲上就是"粘稠液体"）
}
inline Cmd ZeroTorque() {
    return Cmd{}; // 零力矩模式：主动抵消自身摩擦（仿真里就是 ctrl=0）
}
inline Cmd Torque(double tau) {
    Cmd c;
    c.ff = tau;
    return c; // 力矩模式：空载会一直加速
}
inline Cmd Stiffness(double pos, double kp) {
    Cmd c;
    c.pos = pos;
    c.kp = kp;
    return c; // 位置模式：像弹簧拉向目标（没有阻尼，会来回荡）
}
inline Cmd Mit(double pos, double kp, double kd, double ff = 0.0) {
    Cmd c;
    c.ff = ff;
    c.pos = pos;
    c.kp = kp;
    c.kd = kd;
    return c; // 力位混合（MIT）：四足实际使用的模式
}

// 12 个关节电机：每步算 τ 并写进 d->ctrl。
// 关节顺序（哪个执行器作用在哪根关节上）不写死，构造时按 actuator→joint 现查，换模型不用改这里。
class JointMotors {
  public:
    JointMotors(const mjModel *m, double tau_max = 0.0, double deadzone = 0.0, int delay_cycles = 0,
                double noise = 0.0)
        : tau_max_(tau_max), deadzone_(deadzone), noise_(noise), rng_(12345) {
        const int nu = m->nu;
        qadr_.resize(nu);
        vadr_.resize(nu);
        limit_.resize(nu);
        cmd_.assign(nu, Cmd{});
        for (int i = 0; i < nu; ++i) {
            const int j = m->actuator_trnid[2 * i]; // 该执行器作用的关节 id
            qadr_[i] = m->jnt_qposadr[j];
            vadr_[i] = m->jnt_dofadr[j];
            // 限幅取上界（模型里是对称的 ±20）；--tau-max 给了就用它，用来对照实机的 33.5 N·m
            limit_[i] = tau_max_ > 0.0 ? tau_max_ : m->actuator_ctrlrange[2 * i + 1];
        }
        delay_ = std::max(0, delay_cycles);
        hist_.assign(static_cast<size_t>(nu) * static_cast<size_t>(delay_ + 1), Cmd{});
        in_dead_.assign(static_cast<size_t>(nu), false);
    }

    int size() const { return static_cast<int>(qadr_.size()); }

    // 12 个关节下同一条指令（本任务只用得着这一种）
    void Set(const Cmd &c) {
        for (int i = 0; i < size(); ++i)
            cmd_[i] = c;
    }
    // 个别关节单独下指令（留作扩展：将来做步态时用）
    void Set(int i, const Cmd &c) { cmd_[i] = c; }
    const Cmd &command(int i) const { return cmd_[i]; }

    // 每步调用一次：τ = τ_ff + kp·(q_des − q) + kd·(q̇_des − q̇) → 死区 → 限幅 → 噪声 → d->ctrl
    //
    // 死区这里有两个容易搞错的细节（实测踩过，见 docs/sim.md §4 踩坑 15）：
    //   * **本来就正好是 0 的力矩不算“落死区”**：阻尼模式下狗停下来后 q̇ = 0 ⇒ τ = −kd·0 = 0，
    //     旧写法（|τ| < 死区 就 +1）会把“没在输出的每一个电机·步”都算进来 —— 5 s 的仿真能报出
    //     三万多次；现在只统计真的“被削掉”的那部分（0 < |τ| < 死区）；
    //   * `dead` 是**采样计数**（电机·步），不是“穿越次数”：一次穿越若在死区里停留多步就按步数累加。
    //     要按“次”看用 `dead_events`：每个关节从死区外进入死区内记一次（上升沿）。
    void Apply(mjData *d) {
        const Cmd *c = EffectiveCommand();
        for (int i = 0; i < size(); ++i) {
            const double q = d->qpos[qadr_[i]];
            const double dq = d->qvel[vadr_[i]];
            double tau = c[i].ff + c[i].kp * (c[i].pos - q) + c[i].kd * (c[i].vel - dq);
            const double a = std::fabs(tau);
            if (deadzone_ > 0.0) {
                // “在死区里”包含 a == 0（完全没指令），这样狗停着不动时不会反复记“进入”
                const bool inside = a < deadzone_;
                if (inside && a > 0.0) {
                    tau = 0.0; // 静摩擦死区：这么小的力矩推不动电机
                    ++stats_.dead;
                    if (!in_dead_[static_cast<size_t>(i)])
                        ++stats_.dead_events;
                }
                in_dead_[static_cast<size_t>(i)] = inside;
            }
            if (tau > limit_[i]) {
                tau = limit_[i];
                ++stats_.sat; // 打满 = 恒力矩区的天花板，讲义 §1.1 的第一类非线性
            } else if (tau < -limit_[i]) {
                tau = -limit_[i];
                ++stats_.sat;
            }
            if (noise_ > 0.0)
                tau += noise_ * normal_(rng_); // 编码器/电流环噪声（固定种子，可复现）
            d->ctrl[i] = tau;
            stats_.steps++;
            const double mag = std::fabs(tau);
            stats_.tau_peak = std::max(stats_.tau_peak, mag);
            stats_.tau_abs_sum += mag;
        }
    }

    // 统计（写进摘要，用来说明"非理想项到底起没起作用"）
    struct Stats {
        long steps = 0;        // 累计"电机·步"
        long sat = 0;          // 撞限幅的电机·步
        long dead = 0;         // 落进死区、被当成 0 的电机·步（**不含**本来就正好是 0 的力矩）
        long dead_events = 0;  // 进入死区的次数（每个关节一次上升沿算一次）
        double tau_peak = 0.0; // |τ| 峰值
        double tau_abs_sum = 0.0;
        double tau_mean_abs() const {
            return steps > 0 ? tau_abs_sum / static_cast<double>(steps) : 0.0;
        }
    };
    const Stats &stats() const { return stats_; }
    void ResetStats() { stats_ = Stats{}; }
    int delay_cycles() const { return delay_; }

  private:
    // 取"现在真正生效"的指令：--delay-cycles N 就是用 N 个控制周期之前下发的那条
    const Cmd *EffectiveCommand() {
        if (delay_ == 0)
            return cmd_.data();
        const size_t slots = static_cast<size_t>(delay_ + 1);
        const size_t now_slot = static_cast<size_t>(hist_step_) % slots;
        std::copy(cmd_.begin(), cmd_.end(), hist_.begin() + static_cast<long>(now_slot) * size());
        const size_t use_slot = (static_cast<size_t>(hist_step_) + slots - static_cast<size_t>(delay_)) % slots;
        ++hist_step_;
        return hist_.data() + static_cast<long>(use_slot) * size();
    }

    double tau_max_ = 0.0;
    double deadzone_ = 0.0;
    double noise_ = 0.0;
    int delay_ = 0;
    size_t hist_step_ = 0;
    std::vector<int> qadr_, vadr_;
    std::vector<double> limit_;
    std::vector<Cmd> cmd_;
    std::vector<Cmd> hist_;  // [步][关节] 摊平存放，长度 = size()×(delay_+1)
    std::vector<bool> in_dead_; // 每个关节上一拍是否在死区里（用来数“进入死区”的上升沿）
    std::mt19937 rng_;
    std::normal_distribution<double> normal_{0.0, 1.0};
    Stats stats_;
};

} // namespace motor
