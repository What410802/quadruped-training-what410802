// 关节电机模型：把培训讲义（`motor.pdf.md`）§1.2 的 MIT 混合控制搬到仿真里**自己算**。
//
// 实机：驱动板里封好了 FOC 电流环，上层只发 5 个量，而且都是**转子侧**的（手册第 4 节）。
// 仿真：我们的执行器是 <motor>（gear=1，data.ctrl 直接就是**关节侧**力矩），所以照 §2.3 的映射
//     （位置/速度 ×N、力矩 ÷N、刚度/阻尼 ÷N²）把同一条公式写在关节侧：
//     τ = τ_ff + kp·(q_des − q) + kd·(q̇_des − q̇)
//
// 本文件是 [`../../src/motor.h`](../../src/motor.h) 的最简版：去掉了**转子侧换算**（ToRotor /
// RotorToJointAngle——那是子任务项二对实机才需要的）与**三类非理想项**，只留"同一条公式 +
// 模型自带的限幅"。被删掉的是什么、为什么值得单独做成开关：
//   * 限幅：`ctrlrange`（本模型 ±20 N·m）= 恒力矩区的天花板（讲义说 r1_sar 的 black 配置是 33.5 N·m）；
//   * 死区 / 静摩擦：|τ| 小于阈值就当 0（小力矩时摩擦占主导，讲义 §1.1 的第一类非线性）；
//   * 指令延迟 + 编码器噪声：延迟 N 个控制周期、白噪声（固定种子，可复现）。
// 讲义里还有"高速段力矩随转速下降（电压/反电动势限制）"，两个版本**都不建**：本模型的关节转速
// 远低于电机基速，且不建它也不改变"给定力矩出多少力矩"的结论（理由见 cpp/docs/sim.md）。
#pragma once

#include <mujoco/mujoco.h>

#include <algorithm>
#include <cmath>
#include <cstdio>
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

// 转子侧（宇树 SDK）的 5 个字段：子任务项二对实机时按这张表下发
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

// 讲义 §1.3：所有模式都是同一条公式的特例。本任务只用得着下面两个，其余（零力矩 / 纯力矩 /
// 纯位置）都是把别的系数填 0，需要时照 Mit 的样子加一个即可。
inline Cmd Damping(double kd) {
    return Cmd{0.0, 0.0, 0.0, 0.0, kd}; // 阻尼模式：τ = −kd·q̇（量纲上就是"粘稠液体"）
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
    explicit JointMotors(const mjModel *m) {
        const int nu = m->nu;
        qadr_.resize(nu);
        vadr_.resize(nu);
        limit_.resize(nu);
        cmd_.assign(nu, Cmd{});
        for (int i = 0; i < nu; ++i) {
            const int j = m->actuator_trnid[2 * i]; // 该执行器作用的关节 id
            qadr_[i] = m->jnt_qposadr[j];
            vadr_[i] = m->jnt_dofadr[j];
            // 限幅取上界（模型里是对称的 ±20 N·m）= 恒力矩区的天花板（讲义 §1.1 的第一类非线性）
            limit_[i] = m->actuator_ctrlrange[2 * i + 1];
        }
    }

    int size() const { return static_cast<int>(qadr_.size()); }

    // 12 个关节下同一条指令（本任务只用得着这一种）
    void Set(const Cmd &c) {
        for (int i = 0; i < size(); ++i)
            cmd_[i] = c;
    }
    // 个别关节单独下指令（状态机每步就是这么下发的）
    void Set(int i, const Cmd &c) { cmd_[i] = c; }

    // 每步调用一次：τ = τ_ff + kp·(q_des − q) + kd·(q̇_des − q̇) → 死区 → 限幅 → 噪声 → d->ctrl
    //
    void Apply(mjData *d) {
        const Cmd *c = cmd_.data();
        for (int i = 0; i < size(); ++i) {
            const double q = d->qpos[qadr_[i]];
            const double dq = d->qvel[vadr_[i]];
            double tau = c[i].ff + c[i].kp * (c[i].pos - q) + c[i].kd * (c[i].vel - dq);
            if (tau > limit_[i]) {
                tau = limit_[i];
                ++stats_.sat; // 打满 = 恒力矩区的天花板，讲义 §1.1 的第一类非线性
            } else if (tau < -limit_[i]) {
                tau = -limit_[i];
                ++stats_.sat;
            }
            d->ctrl[i] = tau;
            stats_.steps++;
            const double mag = std::fabs(tau);
            stats_.tau_peak = std::max(stats_.tau_peak, mag);
            stats_.tau_abs_sum += mag;
        }
    }

    // 统计（写进摘要，用来说明"限幅到底有没有起作用"）
    struct Stats {
        long steps = 0;        // 累计"电机·步"
        long sat = 0;          // 撞限幅的电机·步
        double tau_peak = 0.0; // |τ| 峰值
        double tau_abs_sum = 0.0;
        double tau_mean_abs() const {
            return steps > 0 ? tau_abs_sum / static_cast<double>(steps) : 0.0;
        }
    };
    const Stats &stats() const { return stats_; }

  private:
    std::vector<int> qadr_, vadr_;
    std::vector<double> limit_;
    std::vector<Cmd> cmd_;
    Stats stats_;
};

// 一行统计摘要：把 Stats 里那几个数翻译成给终端看的中文。放在 motor.h 里是因为"这几个数是什么"
// 属于电机模型自己的知识，与 main 无关。
inline void PrintStats(const JointMotors &motors) {
    const JointMotors::Stats &st = motors.stats();
    std::printf("电机：累计 %ld 电机·步，撞限幅 %ld 次（%.3f%%），|τ| 峰值 %.2f N·m、均值 %.2f N·m\n",
                st.steps, st.sat, 100.0 * static_cast<double>(st.sat) / std::max(1L, st.steps),
                st.tau_peak, st.tau_mean_abs());
}

} // namespace motor
