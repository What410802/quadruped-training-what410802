// 控制核心：站姿（控制目标）+ MIT 关节电机指令 + 两状态机。整个核心版就这一个头文件。
//
// 这是 [`../essential/`](../README.md) 再砍一刀的"只留核心"版：
//   * 没有命令行选项（参数全是下面的 constexpr）；
//   * **没有量测与遥测**（不算四足触地/高度/竖直度/漂移，不打摘要）；
//   * 没有自适应斜坡（固定 1.0 s，见 kRamp）、没有电机统计、没有站姿文件与指纹校验
//     （站姿直接内联在下面）；
//   * 键盘只有 S / D / R / Q，切状态时打一行日志，其余交给官方窗口自己显示。
//
// 本次任务（讲义 §1.3 / §1.4）要求的两状态，用的是**同一条** MIT 公式，只是系数不同：
//   阻尼模式（上电默认）：kp = 0、pos/vel/ff = 0 ⇒ τ = −kd·q̇。像粘稠液体，甩一下就停，
//                        永远不会自己站起来——这就是"上电默认"的含义。
//   站立模式（按 S）：位置项目标 q_des 从"按下那一刻的关节角"平滑推到站姿 ⇒ 不管起点是原姿态、
//                        半站还是正在往下掉，同一段代码都能把它连续地带回站姿（不是瞬移）。
//
//   τ = τ_ff + kp·(q_des − q) + kd·(q̇_des − q̇)
//
// 实机驱动板里封好了 FOC 电流环，上层只发这 5 个量；仿真里我们的执行器是 <motor>（gear=1，
// data.ctrl 就是关节侧的力矩），所以把同一条公式直接写在关节侧（映射关系见 cpp/docs/sim.md §2.3）。
//
// **限幅有两道，是故意的**：控制程序这一层先夹一次（kMaxTorque），模型自己的 actuator
// `ctrlrange` 还会再夹一次——"控制程序输出的力矩"与"电机能给出的力矩"本来就是两件事，
// 不能指望电机替我们把控制输出管住。
#pragma once

#include <mujoco/mujoco.h>

#include <algorithm>
#include <cmath>
#include <vector>

// ---------------------------------------------------------------- 站姿（控制目标）

// 12 个关节的目标角 [rad]，**按执行器顺序**（不是模型里的关节名顺序），以及该姿态下的基座高度 [m]。
//
// 这份站姿与 `../models/stance.txt` **逐位相同**（两个精简版共用同一份；也是重搜出来的低站姿，
// 旧的高站姿是膝 1.100 / 基座 z 0.497）：
// 低站姿离“阻尼模式下正在塌落”的狗更近，**上电后任意时刻按 S 都站得住**；再往前偏 1.0 cm，
// 稳态**四脚受力均匀**。代价、实测数据与生成办法见 [`../docs/essential.md`](../docs/essential.md) 的
// 「站姿为什么可以预存」「验证」两节，生成工具是 [`../agent_scripts/search_stance.cpp`](../agent_scripts/search_stance.cpp)。
//
// 为什么不能直接用模型默认位形（所有关节 = 0）：膝关节会越界、质心落在四足中心后面 0.18 m
// （本模型 calf 约 ±[0.85, 2.5] rad）。实测与成因见 @20260923_mujoco/docs/stand.md 的「控制律与站姿」。
inline constexpr double kStanceZ = 0.4000802544414247;
// 大腿 / 膝各写一个名字：数值是“0.55×1.7 − 0.011”与“1.7 − 0.011”**按浮点算出来**的结果
// （大腿那个比字面量 0.946 高 1 ulp——直接写计算结果，才能与搜索工具生成的站姿逐位相同）。
inline constexpr double kStanceThigh = 0.94600000000000006;
inline constexpr double kStanceCalf = 1.6890000000000001;
inline constexpr double kStanceQ[12] = {0.0,          kStanceThigh, -kStanceCalf,  0.0,
                                        -kStanceThigh, kStanceCalf,  0.0,          -kStanceThigh,
                                        kStanceCalf,   0.0,          kStanceThigh, -kStanceCalf};

namespace motor {

// 关节侧的 MIT 指令：讲义 §2.3 那 5 个量。控制程序只发这 5 个，怎么变成电流是驱动板的事。
struct Cmd {
    double ff = 0.0;  // 前馈力矩 τ_ff [N·m]
    double pos = 0.0; // 期望角度 q_des [rad]（要按插值缓慢变化，别给阶跃）
    double vel = 0.0; // 期望角速度 q̇_des [rad/s]
    double kp = 0.0;  // 位置刚度 [N·m/rad]
    double kd = 0.0;  // 速度刚度（阻尼）[N·m·s/rad]
};

// 控制这一层给出的力矩上限 [N·m]：取本模型 actuator 的 ctrlrange（±20）。
// 实机上是 33.5 N·m（讲义 §1.4 给的 black 配置）。模型自己还会按 ctrlrange 再夹一次（第二道）。
inline constexpr double kMaxTorque = 20.0;

// 阻尼模式：τ = −kd·q̇（其余系数全 0）
inline Cmd Damping(double kd) { return Cmd{0.0, 0.0, 0.0, 0.0, kd}; }

// 力位混合（MIT）：四足实际使用的模式
inline Cmd Mit(double pos, double kp, double kd) {
    Cmd c;
    c.pos = pos;
    c.kp = kp;
    c.kd = kd;
    return c;
}

// 一条指令 + 当前状态 → 关节力矩（含我们这一层的限幅）
inline double Torque(const Cmd &c, double q, double dq) {
    const double tau = c.ff + c.kp * (c.pos - q) + c.kd * (c.vel - dq);
    return std::clamp(tau, -kMaxTorque, kMaxTorque);
}

} // namespace motor

namespace ctrl {

// 参数：核心版不做命令行，直接写死。数值取自讲义 §1.4 提到的实机输出侧那一组（与 essential/ 默认一致）。
inline constexpr double kKp = 80.0;    // 站立模式：位置刚度
inline constexpr double kKd = 3.0;     // 站立模式：阻尼
inline constexpr double kKdDamp = 0.5; // 阻尼模式：阻尼
// q_des 从"按下那一刻的关节角"推到站姿所用的时长 [s]。固定值，不做自适应：
// 实测（`--start raw`，9 s 仿真）0.5 / 0.8 / 1.0 / 1.2 / 1.5 s 都能站住——"上电直接按 S"与
// "先塌下 3 s 再按 S"两种情形都是；只有 0.3 s 从趴卧起会被自己掀翻（猛拉）。
// 取中间的 1.0 s：既不会像 0.1 s 那样把还在站着的狗硬拽，也不会慢到让它先倒下去。
inline constexpr double kRamp = 1.0;

// 控制参数：默认就是上面那几个常数（= main 不给参数时的行为）。
// 想让它们可改（位置参数或实验脚本）就构造一份 Param 传进去，状态机自己不读命令行。
struct Param {
    double kp = kKp;
    double kd = kKd;
    double kd_damp = kKdDamp;
    double ramp = kRamp;
};

enum class State { Damping, Standing };

inline const char *Name(State s) { return s == State::Damping ? "阻尼模式" : "站立模式"; }

// 斜坡插值：u=0→0、u=1→1，两端导数为 0（平滑起步、平滑到位）
inline double Smoothstep(double u) {
    const double x = u < 0.0 ? 0.0 : (u > 1.0 ? 1.0 : u);
    return x * x * (3.0 - 2.0 * x);
}

class StateMachine {
  public:
    // 从模型里现查"每个执行器作用在哪根关节上"，不写死关节名：换模型这里不用改
    // （目标站姿的长度要与 m->nu 一致，12，见 main 里的检查）。
    // `q_stand` 默认就是内联的 `kStanceQ`（站姿内联是核心版的既定做法）；
    // 想试别的站姿（例如搜索出来的新姿态）就传一个 12 个数的数组进来。
    explicit StateMachine(const mjModel *m, const double *q_stand = kStanceQ,
                          const Param &p = Param{})
        : m_(m), p_(p) {
        target_.assign(q_stand, q_stand + m->nu);
        q_from_ = target_;
        qa_.resize(static_cast<size_t>(m->nu));
        va_.resize(static_cast<size_t>(m->nu));
        for (int i = 0; i < m->nu; ++i) {
            const int j = m->actuator_trnid[2 * i]; // 该执行器作用的关节 id
            qa_[static_cast<size_t>(i)] = m->jnt_qposadr[j];
            va_[static_cast<size_t>(i)] = m->jnt_dofadr[j];
        }
    }

    State state() const { return state_; }

    // 切换请求（按键盘时调）。返回 true 表示状态真的变了（幂等：重复按同一个键不重启斜坡）。
    bool Request(State s, const mjData *d) {
        if (s == state_)
            return false;
        state_ = s;
        if (s == State::Standing) {
            // 起点 = 按下那一刻的关节角：这就是"从任意初始位置、连续地站起来"里"任意"的落点
            for (int i = 0; i < m_->nu; ++i)
                q_from_[static_cast<size_t>(i)] =
                    d->qpos[qa_[static_cast<size_t>(i)]];
            ramp_t0_ = d->time;
        }
        return true;
    }

    // 每步调用一次：按当前状态算好 12 个关节的力矩，写进 d->ctrl
    void Apply(const mjData *d) const {
        if (state_ == State::Damping) {
            const motor::Cmd c = motor::Damping(p_.kd_damp);
            for (int i = 0; i < m_->nu; ++i)
                d->ctrl[i] = motor::Torque(c, d->qpos[qa_[static_cast<size_t>(i)]],
                                           d->qvel[va_[static_cast<size_t>(i)]]);
            return;
        }
        const double a = Smoothstep((d->time - ramp_t0_) / p_.ramp);
        for (int i = 0; i < m_->nu; ++i) {
            const size_t k = static_cast<size_t>(i);
            const double q_des = q_from_[k] + (target_[k] - q_from_[k]) * a; // 目标逐帧插值
            const motor::Cmd c = motor::Mit(q_des, p_.kp, p_.kd);
            d->ctrl[i] = motor::Torque(c, d->qpos[qa_[k]], d->qvel[va_[k]]);
        }
    }

  private:
    const mjModel *m_ = nullptr;
    Param p_;
    State state_ = State::Damping; // 任务要求：上电 = 阻尼模式
    std::vector<double> target_, q_from_;
    std::vector<int> qa_, va_; // 每个执行器对应的 qpos / qvel 下标
    double ramp_t0_ = 0.0;
};

} // namespace ctrl
