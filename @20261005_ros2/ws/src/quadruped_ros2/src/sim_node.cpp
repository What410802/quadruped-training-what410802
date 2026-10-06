/**
 * @file sim_node.cpp
 * @brief 仿真运行节点（C++）：MuJoCo 里的 black 四足，收 MIT 指令，发电机反馈与 IMU。
 *
 * 分工：本节点 = **电机 + 机器人**那一侧（实机上由驱动板 + 本体承担）。控制器节点发来的是
 * MIT 五参数（/mit_command），本节点用电机模型（include/quadruped_ros2/motor.hpp）把它算成
 * 关节力矩写进 `data.ctrl`，步进物理，再把 {q, dq, ddq, tau, cur} 与 IMU 发回去。
 *
 * 线程（窗口用 MuJoCo **官方** Simulate 界面，与 @20260927_motor/cpp/essential_core 同一套形状）：
 *   * 主线程：`sim->RenderLoop()` —— 窗口与渲染。GLFW 要求"谁建窗口谁用它"，窗口只能在主线程；
 *   * 物理线程：装现场 → `sim->Load()` 把模型交给界面 → 一步一循环（取指令 → 算力矩 →
 *     `mj_step` → 发反馈）。**顺序要紧**：`Load()` 会阻塞等渲染线程来接模型，所以必须先让主线程
 *     进 `RenderLoop()` 再起物理线程，反了就是"开一个空窗口然后死等"；
 *   * ROS 执行器线程：只收 `/mit_command`（单线程执行器）。物理线程不 spin，专心跑 `mj_step`。
 *   两边共享 `mjModel/mjData`，所有访问都在官方那个递归锁 `sim->mtx` 里。
 *
 * 为什么仿真也用 C++：官方界面的 `RenderLoop()` 在 `Render()` **之前**就放锁
 * （@20260923_mujoco/README.md 实测 1.00x 实时），物理线程不会被渲染顶住；Python 版
 * （launch_passive）受 GIL 限制，开窗口实测只有 0.93x。
 *
 * 时间：物理按墙钟节流（deadline pacing，与 @20260923_mujoco/python/simulator.py 同一套：
 * 误差不累积、落后就重新对齐不追赶）。`realtime:=false` 时全速跑，专供回归脚本。
 * 控制周期 = 物理步长 = 0.002 s（500 Hz，与实机主控同量级）。
 *
 * 看门狗：超过 `command_timeout_ms` 没收到指令（控制器挂了 / 还没起来），自动退回阻尼模式
 * （kp=0、kd=damp_kd），不是"保持最后一条"——真机上失联也是让它软下来，不是僵在那里。
 */

#include "quadruped_ros2/attitude.hpp" // 状态行里的倾角
#include "quadruped_ros2/control.hpp"  // kNu（与控制器、站姿表同源）
#include "quadruped_ros2/motor.hpp"

#include "quadruped_ros2/msg/mit_command.hpp"
#include "quadruped_ros2/msg/motor_state.hpp"

#include <mujoco/mujoco.h>

#include <simulate/glfw_adapter.h> // mujoco::GlfwAdapter
#include <simulate/simulate.h> // mujoco::Simulate（官方界面，由 mujoco::libmujoco_simulate 提供）

#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/imu.hpp>
#include <std_srvs/srv/empty.hpp>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

namespace
{

namespace fs = std::filesystem;

using quadruped_ros2::msg::MitCommand;
using quadruped_ros2::msg::MotorState;
using sensor_msgs::msg::Imu;
using std_srvs::srv::Empty;

constexpr int kNu = quadruped::control::kNu; // 12：与控制器、站姿表、模型 actuator 数一致

double WallNow()
{
    return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch())
        .count();
}

/// 只保留最新一条的 QoS（与控制器节点一致）：传感器流要的是"现在"。
/// best_effort 不会被 slow subscriber 的流控顶住；`ros2 topic echo` 的默认 QoS 是
/// sensor_data（best_effort），所以命令行看这几条开箱可用（见 docs/ros2-nodes.md）。
rclcpp::QoS LatestQoS()
{
    return rclcpp::QoS(rclcpp::KeepLast(1)).best_effort();
}

/// 一次仿真要用的东西：模型 + 数据 + 实际加载的场景路径。
/// 自己持有 m/d、析构里释放；交给官方界面之后用 Release() 把所有权让出去，
/// 否则同一个指针会被释放两次（官方的析构里也会 mj_delete*）。
struct Scene
{
    mjModel* m = nullptr;
    mjData* d = nullptr;
    fs::path path;

    Scene() = default;
    ~Scene()
    {
        if (d != nullptr)
        {
            mj_deleteData(d);
        }
        if (m != nullptr)
        {
            mj_deleteModel(m);
        }
    }
    Scene(const Scene&) = delete;
    Scene& operator=(const Scene&) = delete;

    void Release()
    {
        m = nullptr;
        d = nullptr;
    }
};

/// 每个执行器作用在哪根关节上（qpos / qvel·qacc 下标），启动时查一次。
/// 不写死关节名：换模型这里不用改（只有"站姿表 12 个数"是按本任务写死的）。
struct ActuatorIndex
{
    std::vector<int> qpos;
    std::vector<int> dof;
};

/// IMU 三个传感器在 sensordata 里的起始下标（模型见 models/black_description.xml 的 <sensor>）。
struct ImuAddress
{
    int quat = -1;
    int gyro = -1;
    int acc = -1;

    bool ok() const { return quat >= 0 && gyro >= 0 && acc >= 0; }
};

/// 官方界面的"关窗"只有两条路：用户点掉窗口，或者我们自己把窗口标记成该关。
/// GlfwAdapter 把 GLFWwindow* 藏在私有成员里，但 ShouldCloseWindow() 是虚函数 ——
/// 子类加一个标志位就能从物理线程里体面地关窗（Ctrl-C 走这条）。
class ClosableAdapter : public mujoco::GlfwAdapter
{
  public:
    bool ShouldCloseWindow() const override
    {
        return quit_.load() || mujoco::GlfwAdapter::ShouldCloseWindow();
    }
    void RequestClose() { quit_ = true; }

  private:
    mutable std::atomic_bool quit_{false};
};

/// 节点参数（启动时读一次，之后不变）。
struct Options
{
    std::string scene; ///< 场景 xml；空 = 从可执行文件往上找 scenes/
    /// 起点：raw（= `mj_resetData` 的模型原姿态，**默认**，与上次任务 `@20260927_motor` 的
    /// `--start` 默认一致）/ rest（场景里的趴卧 keyframe，方便"从趴着开始"看起身）。
    std::string start;
    bool viewer = true;    ///< 开不开官方窗口
    bool realtime = true;  ///< 按墙钟节流
    int publish_every = 1; ///< 每多少步发一次反馈（1 = 每步 = 500 Hz）
    double tau_max = quadruped::motor::kDefaultTauMax;
    double damp_kd = 0.5; ///< 看门狗退回阻尼模式时的 kd [N·m·s/rad]
    int command_timeout_ms = 200; ///< 多少个控制周期没收到指令就退回阻尼（折算成步数，见下）
    double status_period_s = 1.0; ///< 每多少仿真秒打一行状态（基座高度/倾角/接触点）；0 = 不打
};

class SimNode : public rclcpp::Node
{
  public:
    SimNode() : Node("sim_node")
    {
        Options opt;
        opt.scene = declare_parameter<std::string>("scene", "");
        opt.start = declare_parameter<std::string>("start", "raw");
        opt.viewer = declare_parameter<bool>("viewer", true);
        opt.realtime = declare_parameter<bool>("realtime", true);
        opt.publish_every = declare_parameter<int>("publish_every", 1);
        opt.tau_max = declare_parameter<double>("tau_max", opt.tau_max);
        opt.damp_kd = declare_parameter<double>("damp_kd", opt.damp_kd);
        opt.command_timeout_ms =
            declare_parameter<int>("command_timeout_ms", opt.command_timeout_ms);
        opt.status_period_s = declare_parameter<double>("status_period_s", opt.status_period_s);

        if (opt.start != "rest" && opt.start != "raw")
        {
            throw std::runtime_error("参数 start 只能是 rest 或 raw，收到：" + opt.start);
        }
        if (opt.publish_every < 1)
        {
            throw std::runtime_error("参数 publish_every 必须 ≥ 1");
        }
        // 没有显示服务时（纯 ssh / 无窗口环境）不能开官方界面，自动降级成无窗口跑，
        // 而不是让 GLFW 在 glfwInit 里把节点整个搞崩。
        if (opt.viewer && std::getenv("DISPLAY") == nullptr &&
            std::getenv("WAYLAND_DISPLAY") == nullptr)
        {
            RCLCPP_WARN(get_logger(),
                        "没有 DISPLAY / WAYLAND_DISPLAY：viewer 自动关掉，按无窗口跑");
            opt.viewer = false;
        }
        opt_ = opt;

        command_sub_ = create_subscription<MitCommand>(
            "mit_command", LatestQoS(), [this](MitCommand::SharedPtr msg) { OnCommand(msg); });
        state_pub_ = create_publisher<MotorState>("motor_state", LatestQoS());
        imu_pub_ = create_publisher<Imu>("imu", LatestQoS());
        reset_srv_ =
            create_service<Empty>("sim_reset", [this](const std::shared_ptr<Empty::Request>,
                                                      std::shared_ptr<Empty::Response>)
                                  { reset_requested_.store(true); });

        RCLCPP_INFO(get_logger(),
                    "仿真节点：起点=%s、viewer=%s、realtime=%s、每 %d 步发一次反馈、"
                    "力矩上限 %.4g N·m；cur 一律报 0（不做电流推定，理由见 Feedback()）",
                    opt.start.c_str(), opt.viewer ? "开" : "关", opt.realtime ? "开" : "关",
                    opt.publish_every, opt.tau_max);
        RCLCPP_INFO(get_logger(),
                    "等待 /mit_command（收到第一条之前按阻尼模式跑，与上电默认一致）");
    }

    const Options& options() const { return opt_; }

    /// 物理线程问"该收工了吗"：Ctrl-C（rclcpp 的 SIGINT）或窗口关了都算。
    bool quit_requested() const { return quit_.load() || !rclcpp::ok(); }

    void RequestQuit() { quit_.store(true); }

    /// 取最近一条 MIT 指令。返回 false = 一条都还没收到（看门狗由物理线程按步数判，见下）。
    bool TakeCommand(MitCommand* out)
    {
        std::lock_guard<std::mutex> lock(cmd_mutex_);
        if (!have_cmd_)
        {
            return false;
        }
        *out = cmd_;
        return true;
    }

    bool TakeReset() { return reset_requested_.exchange(false); }

    void PublishMotorState(const MotorState& msg) { state_pub_->publish(msg); }

    void PublishImu(const Imu& msg) { imu_pub_->publish(msg); }

  private:
    void OnCommand(const MitCommand::SharedPtr& msg)
    {
        std::lock_guard<std::mutex> lock(cmd_mutex_);
        cmd_ = *msg;
        cmd_wall_ = WallNow();
        if (!have_cmd_)
        {
            have_cmd_ = true;
            RCLCPP_INFO(get_logger(), "收到第一条 /mit_command：电机进入 MIT 模式"
                                      "（τ = tau + kp·(q_des − q) + kd·(w_des − q̇)）");
        }
    }

    Options opt_;
    std::atomic_bool quit_{false};
    std::atomic_bool reset_requested_{false};

    std::mutex cmd_mutex_;
    MitCommand cmd_;
    bool have_cmd_ = false;
    double cmd_wall_ = 0.0;

    rclcpp::Subscription<MitCommand>::SharedPtr command_sub_;
    rclcpp::Publisher<MotorState>::SharedPtr state_pub_;
    rclcpp::Publisher<Imu>::SharedPtr imu_pub_;
    rclcpp::Service<Empty>::SharedPtr reset_srv_;
};

/// 场景路径：参数给了就用它；没给就从**可执行文件所在目录往上找**带 scenes/ 的那一层
/// （比"往上数两层"健壮：build/、install/、或把可执行文件拷到别处都适用）。
bool ResolveScene(fs::path* out, const std::string& given, std::string* err)
{
    if (!given.empty())
    {
        *out = given;
        return true;
    }
    const fs::path exe_dir = fs::read_symlink("/proc/self/exe").parent_path();
    for (fs::path p = exe_dir; p != p.parent_path(); p = p.parent_path())
    {
        if (fs::is_directory(p / "scenes"))
        {
            *out = p / "scenes/flat_scene.xml";
            return true;
        }
    }
    *err = "从可执行文件所在目录往上找不到带 scenes/ 的任务目录（" + exe_dir.string() +
           "）：用 scene:=<路径> 显式指定场景";
    return false;
}

/// 装配现场：加载场景 + 建 data + 摆到起点。
bool LoadScene(const Options& opt, Scene* out, std::string* err)
{
    fs::path path;
    if (!ResolveScene(&path, opt.scene, err))
    {
        return false;
    }
    out->path = path;
    out->m = mj_loadXML(path.c_str(), nullptr, nullptr, 0);
    if (out->m == nullptr)
    {
        *err = "加载场景失败：" + path.string();
        return false;
    }
    out->d = mj_makeData(out->m);
    if (out->d == nullptr)
    {
        *err = "创建 mjData 失败";
        return false;
    }
    if (out->m->nu != kNu)
    {
        *err = "本任务的节点与站姿表都按 12 个执行器写死，这个模型有 " +
               std::to_string(out->m->nu) + " 个";
        return false;
    }
    // 起点：raw = 模型原姿态（mj_resetData 的 qpos0，**默认**）；rest = 场景里的 <keyframe
    // name="rest">（index 0，趴卧） （直腿站立、脚底刚好触地，零力矩下自然塌成趴卧）。keyframe
    // 不会自动加载， 见仓库 docs/learn/mujoco.md §6.2。
    if (opt.start == "rest")
    {
        if (out->m->nkey == 0)
        {
            *err = "场景里没有 keyframe，无法用 start:=rest（改用 start:=raw）";
            return false;
        }
        mj_resetDataKeyframe(out->m, out->d, 0);
    }
    mj_forward(out->m, out->d);
    return true;
}

/// 复位（手柄 X → /sim_reset）：回到起点姿态并回阻尼（控制器侧会同时切阻尼）。
/// **保留仿真时间轴**：控制器的斜坡按 sim_time 算，把 time 清零会让"复位后再起身"先卡住
/// （这个坑上一版也踩过，见 @20260927_motor/cpp/essential_core/src/main.cpp 的注释）。
void ResetToStart(const Options& opt, mjModel* m, mjData* d)
{
    const double t_keep = d->time;
    if (opt.start == "rest" && m->nkey > 0)
    {
        mj_resetDataKeyframe(m, d, 0);
    }
    else
    {
        mj_resetData(m, d);
    }
    d->time = t_keep;
    mj_forward(m, d);
}

ActuatorIndex BuildIndex(const mjModel* m)
{
    ActuatorIndex idx;
    idx.qpos.resize(static_cast<std::size_t>(m->nu));
    idx.dof.resize(static_cast<std::size_t>(m->nu));
    for (int i = 0; i < m->nu; ++i)
    {
        const int j = m->actuator_trnid[2 * i]; // 该执行器作用的关节 id
        idx.qpos[static_cast<std::size_t>(i)] = m->jnt_qposadr[j];
        idx.dof[static_cast<std::size_t>(i)] = m->jnt_dofadr[j];
    }
    return idx;
}

ImuAddress FindImu(const mjModel* m)
{
    ImuAddress adr;
    const auto find = [m](const char* name, int min_dim, int* out)
    {
        const int id = mj_name2id(m, mjOBJ_SENSOR, name);
        if (id >= 0 && m->sensor_dim[id] >= min_dim)
        {
            *out = m->sensor_adr[id];
        }
    };
    find("imu_quat", 4, &adr.quat);
    find("imu_gyro", 3, &adr.gyro);
    find("imu_acc", 3, &adr.acc);
    return adr;
}

/// 看门狗/未收到指令时的兜底：纯阻尼（kp = 0、kd = damp_kd）。
MitCommand DampingCommand(double kd)
{
    MitCommand cmd;
    cmd.kp.fill(0.0);
    cmd.kd.fill(kd);
    cmd.q.fill(0.0);
    cmd.w.fill(0.0);
    cmd.tau.fill(0.0);
    return cmd;
}

void PublishFeedback(SimNode* node, const mjData* d, const ActuatorIndex& idx,
                     const ImuAddress& imu, const Options& opt)
{
    MotorState state;
    state.header.stamp = node->now();
    state.sim_time = d->time;
    for (int i = 0; i < kNu; ++i)
    {
        const auto k = static_cast<std::size_t>(i);
        state.q[k] = d->qpos[idx.qpos[k]];
        state.dq[k] = d->qvel[idx.dof[k]];
        state.ddq[k] = d->qacc[idx.dof[k]];
        state.tau[k] = d->actuator_force[i];
        // cur **一律 0**：MuJoCo 的执行器是纯力矩源，模型里没有电流环，也没有传感器；
        // 按 tau/(减速比×Kt) 折算看似"有量纲"，其实 Kt 只能靠猜（讲义与手册都没给 GO-M8010-6 的
        // 值），算出来的数与实机电流没有可验证的对应关系——**没有支撑模型与数据就不编**。
        // 字段本身保留（任务书的接口定义就是 {q, dq, ddq, tau, cur}），含义明确为"未测量，置 0"。
        state.cur[k] = 0.0;
    }
    // 协方差一律留 0：仿真是确定性、无噪声的（要"有噪声的 IMU"就等电机非理想项那一轮再加）。
    node->PublishMotorState(state);

    if (!imu.ok())
    {
        return;
    }
    Imu out;
    out.header.stamp = state.header.stamp;
    out.header.frame_id = "imu"; // 本任务没有 TF 树，只是给这份数据标个来源
    // MuJoCo 的 framequat 是 (w, x, y, z)，ROS 的 Imu 是 (x, y, z, w) —— 顺序不能照抄
    out.orientation.w = d->sensordata[imu.quat + 0];
    out.orientation.x = d->sensordata[imu.quat + 1];
    out.orientation.y = d->sensordata[imu.quat + 2];
    out.orientation.z = d->sensordata[imu.quat + 3];
    // gyro / accelerometer 都是**机体系**：静止时加速度计 z ≈ +9.81 m/s²、自由落体时 ≈ 0
    out.angular_velocity.x = d->sensordata[imu.gyro + 0];
    out.angular_velocity.y = d->sensordata[imu.gyro + 1];
    out.angular_velocity.z = d->sensordata[imu.gyro + 2];
    out.linear_acceleration.x = d->sensordata[imu.acc + 0];
    out.linear_acceleration.y = d->sensordata[imu.acc + 1];
    out.linear_acceleration.z = d->sensordata[imu.acc + 2];
    node->PublishImu(out);
}

/// 物理线程主体：装现场 → 递给界面 → 一步一循环。返回值 = 进程退出码（0 正常 / 1 装配失败）。
int PhysicsLoop(SimNode* node, ClosableAdapter* adapter, mujoco::Simulate* sim)
{
    const Options& opt = node->options();

    Scene scene;
    std::string err;
    if (!LoadScene(opt, &scene, &err))
    {
        std::fprintf(stderr, "仿真节点装配失败：%s\n", err.c_str());
        if (adapter != nullptr)
        {
            adapter->RequestClose(); // 让主线程的 RenderLoop 收工（它只看窗口该不该关）
        }
        if (sim != nullptr)
        {
            sim->exitrequest = 1;
        }
        return 1;
    }
    mjModel* m = scene.m;
    mjData* d = scene.d;
    const ActuatorIndex idx = BuildIndex(m);
    const ImuAddress imu = FindImu(m);
    const double dt = m->opt.timestep;

    std::printf("MuJoCo %s\n场景：%s\n起点：%s（nq=%ld nv=%ld nu=%ld dt=%.4g s）\n",
                mj_versionString(), scene.path.c_str(), opt.start.c_str(), static_cast<long>(m->nq),
                static_cast<long>(m->nv), static_cast<long>(m->nu), m->opt.timestep);
    if (!imu.ok())
    {
        std::fprintf(stderr, "警告：模型里找不到 imu_quat / imu_gyro / imu_acc 传感器，"
                             "/imu 不会发（见 models/black_description.xml 的 <sensor>）\n");
    }

    if (sim != nullptr)
    {
        sim->Load(m, d, scene.path.c_str()); // 交给官方界面（之后 m/d 归它释放）
        scene.Release();
        {
            const mujoco::MutexLock lock(sim->mtx);
            mj_forward(m, d); // 与官方一致：先算一遍派生量，窗口第一帧才不是空的
        }
    }

    long steps = 0;
    long published = 0;
    long last_cmd_step = 0;
    const long timeout_steps =
        std::max(1L, static_cast<long>(opt.command_timeout_ms / (dt * 1000.0)));
    bool warned_stale = false;
    double status_sim = d->time;
    double report_wall = WallNow(); // 每 5 s 墙钟打一行吞吐统计；两个基准要一起推进
    double report_sim = d->time;
    double wall0 = report_wall; // 暂停后重新对齐用的墙钟基准
    double deadline = wall0;
    // 无窗口时没有官方那个递归锁，用一个本地互斥占位（没人和它抢，等价于不加锁；
    // 这样下面两条路径共用同一段循环体，不必写两遍）。
    mujoco::SimulateMutex local_mtx;

    while (!node->quit_requested())
    {
        if (sim != nullptr && sim->run == 0) // 窗口里按了空格：暂停。这段时间不算"落后"
        {
            std::this_thread::sleep_for(std::chrono::milliseconds(5));
            wall0 = WallNow();
            deadline = wall0;
            continue;
        }

        if (node->TakeReset())
        {
            const mujoco::MutexLock lock(sim != nullptr ? sim->mtx : local_mtx);
            ResetToStart(opt, m, d);
            std::printf("复位：回到起点（%s），保留仿真时间轴 t=%.3f s\n", opt.start.c_str(),
                        d->time);
        }

        // ① 取最近一条 MIT 指令；看门狗按**控制周期数**算（不是墙上时间）：
        //    500 Hz 下 200 ms = 100 步。用步数而不是墙钟，是为了让 realtime:=false 的
        //    全速回归与实时跑的行为完全一致（实机上驱动板也是数控制周期的）。
        MitCommand cmd;
        const bool got = node->TakeCommand(&cmd);
        if (got)
        {
            last_cmd_step = steps;
        }
        const bool stale = !got || (steps - last_cmd_step) > timeout_steps;
        if (stale)
        {
            cmd = DampingCommand(opt.damp_kd);
            if (!warned_stale)
            {
                warned_stale = true;
                if (got)
                {
                    std::printf(
                        "看门狗：连续 %ld 个控制周期（%.0f ms @ %.0f Hz）没收到 /mit_command，"
                        "退回阻尼模式\n",
                        steps - last_cmd_step, static_cast<double>(opt.command_timeout_ms),
                        1.0 / dt);
                }
                else
                {
                    std::printf("还没收到 /mit_command，按阻尼模式跑\n");
                }
            }
        }
        else
        {
            warned_stale = false;
        }

        // ② 电机模型：MIT 五参数 → 关节力矩（含限幅）→ data.ctrl
        //    ③ 步进。共享数据（含渲染线程读的）都在官方那把递归锁里。
        {
            const mujoco::MutexLock lock(sim != nullptr ? sim->mtx : local_mtx);
            for (int i = 0; i < kNu; ++i)
            {
                const auto k = static_cast<std::size_t>(i);
                const quadruped::motor::Cmd one{cmd.tau[k], cmd.kp[k], cmd.q[k], cmd.kd[k],
                                                cmd.w[k]};
                d->ctrl[i] = quadruped::motor::Torque(one, d->qpos[idx.qpos[k]],
                                                      d->qvel[idx.dof[k]], opt.tau_max);
            }
            mj_step(m, d);
        }
        ++steps;

        // ④ 反馈（默认每步一次 = 500 Hz）
        if (steps % opt.publish_every == 0)
        {
            PublishFeedback(node, d, idx, imu, opt);
            ++published;
        }

        // ⑤ 按墙钟节流（deadline pacing：误差不累积，落后就重新对齐不追赶）
        if (opt.realtime)
        {
            deadline += dt;
            const double delay = deadline - WallNow();
            if (delay > 0.0)
            {
                std::this_thread::sleep_for(std::chrono::duration<double>(delay));
            }
            else
            {
                deadline = WallNow();
            }
        }

        // 状态行（默认每秒仿真时间一行，回归脚本就 grep 它）：基座高度 / 倾角 / 接触点数
        if (opt.status_period_s > 0.0 && d->time - status_sim >= opt.status_period_s)
        {
            status_sim = d->time;
            double tilt = 0.0;
            if (imu.ok())
            {
                tilt = quadruped::attitude::TiltDeg(
                    d->sensordata[imu.quat + 0], d->sensordata[imu.quat + 1],
                    d->sensordata[imu.quat + 2], d->sensordata[imu.quat + 3]);
            }
            std::printf("t=%.3f z=%.4f tilt=%.1f ncon=%d cmd=%s\n", d->time, d->qpos[2], tilt,
                        d->ncon, (!stale && got) ? "ok" : "damping");
        }

        // 每 5 s 墙钟打一行：仿真秒 / 实时率 / 步数 / 发出去的反馈条数
        const double wall = WallNow() - report_wall;
        if (wall >= 5.0)
        {
            const double sim_seconds = d->time - report_sim;
            std::printf("仿真 %.2f s / 墙钟 %.2f s = %.3fx 实时；%ld 步，发反馈 %ld 条\n",
                        sim_seconds, wall, sim_seconds / wall, steps, published);
            report_wall = WallNow();
            report_sim = d->time;
        }
    }

    std::printf("仿真节点退出：%ld 步、发反馈 %ld 条、仿真时间 %.3f s\n", steps, published,
                d->time);
    return 0;
}

} // namespace

int main(int argc, char** argv)
{
    std::setvbuf(stdout, nullptr, _IOLBF, 0); // 交互式运行：日志要立刻可见，别等缓冲区满
    rclcpp::init(argc, argv);

    std::shared_ptr<SimNode> node;
    try
    {
        node = std::make_shared<SimNode>();
    }
    catch (const std::exception& e)
    {
        std::fprintf(stderr, "参数有问题：%s\n", e.what());
        rclcpp::shutdown();
        return 1;
    }

    // ROS 执行器自己一条线程：物理线程专心跑 mj_step，不被回调打断（回调只写一个槽位）。
    rclcpp::executors::SingleThreadedExecutor executor;
    executor.add_node(node);
    std::thread ros_thread([&executor] { executor.spin(); });

    const Options& opt = node->options();
    int rc = 0;
    if (opt.viewer)
    {
        // 官方界面：相机/选项/扰动给默认值（之后都在窗口里改）
        mjvCamera cam;
        mjvOption ui_opt;
        mjvPerturb pert;
        mjv_defaultCamera(&cam);
        mjv_defaultOption(&ui_opt);
        mjv_defaultPerturb(&pert);

        auto adapter = std::make_unique<ClosableAdapter>();
        ClosableAdapter* adapter_raw = adapter.get();
        auto sim = std::make_unique<mujoco::Simulate>(std::move(adapter), &cam, &ui_opt, &pert,
                                                      /*is_passive=*/false);

        // 顺序要紧：物理线程里的 Load() 在等渲染线程，所以主线程先跑 RenderLoop 再起物理线程
        std::thread physics(
            [&]
            {
                rc = PhysicsLoop(node.get(), adapter_raw, sim.get());
                adapter_raw->RequestClose(); // 物理线程先退出（Ctrl-C）时，让主线程的窗口也收工
                sim->exitrequest = 1;
            });
        sim->RenderLoop(); // 阻塞：直到窗口被关（用户点掉，或上面这行把标志置上）
        node->RequestQuit();
        physics.join();
    }
    else
    {
        rc = PhysicsLoop(node.get(), nullptr, nullptr);
    }

    executor.cancel();
    if (ros_thread.joinable())
    {
        ros_thread.join();
    }
    rclcpp::shutdown();
    return rc;
}
