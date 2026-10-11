/*
 * Copyright (c) 2024-2025 Ziqi Fan
 * SPDX-License-Identifier: Apache-2.0
 *
 * Modified for @20261007_assignment from rl_sar e5c2f41 src/rl_sim.cpp.
 * Change list: @20261007_assignment/docs/porting.md §2.
 */

#include "rl_sim.hpp"

#include "command_limit.hpp"
#include "input_map.hpp"

#include <torch/utils.h> // torch::set_num_threads (libtorch >= 2.x no longer pulls it in via torch/script.h)

#include <chrono>

namespace
{
// Same QoS as the sim node uses for its 500 Hz topics: keep only the latest sample, best effort.
// A reliable subscriber would never match the sim's best_effort publishers.
rclcpp::QoS LatestQoS()
{
    return rclcpp::QoS(rclcpp::KeepLast(1)).best_effort();
}
} // namespace

RL_Sim::RL_Sim()
    : rclcpp::Node("rl_sim_node")
{
    this->ang_vel_type = "ang_vel_body";
    this->robot_name = this->declare_parameter<std::string>("robot_name", "black");
    this->joy_command_scale = this->declare_parameter<double>("joy_command_scale", this->joy_command_scale);
    // Status line period in ms; 0 = off. The line used to be printed by the RL state on every control
    // cycle (200 Hz, '\r'-overwritten); it is throttled here instead so the rate is a node parameter.
    this->status_period_ms = this->declare_parameter<int>("status_period_ms", this->status_period_ms);
    std::cout << LOGGER::INFO << "robot_name: " << this->robot_name << std::endl;

    // library/core's Control has no initializer for its input enums, so the keyboard latch starts out
    // indeterminate; the keyboard adapter reads it, so make "nothing pressed" explicit. (The gamepad
    // latch is no longer read anywhere: input_map.hpp derives the pad state from the raw /joy frame.)
    this->control.current_keyboard = Input::Keyboard::None;
    this->control.last_keyboard = Input::Keyboard::None;

    // read params from yaml
    this->ReadYamlBase(this->robot_name);

    // auto load FSM by robot_name
    if (FSMManager::GetInstance().IsTypeSupported(this->robot_name))
    {
        auto fsm_ptr = FSMManager::GetInstance().CreateFSM(this->robot_name, this);
        if (fsm_ptr)
        {
            this->fsm = *fsm_ptr;
        }
    }
    else
    {
        std::cout << LOGGER::ERROR << "No FSM registered for robot: " << this->robot_name << std::endl;
    }

    // init torch
    torch::autograd::GradMode::set_enabled(false);
    torch::set_num_threads(4);

    // init robot
    this->InitOutputs();
    this->InitControl();

    // publisher
    this->mit_command_publisher = this->create_publisher<quadruped_ros2::msg::MitCommand>("mit_command", LatestQoS());

    // subscriber
    this->cmd_vel_subscriber = this->create_subscription<geometry_msgs::msg::Twist>(
        "cmd_vel", rclcpp::SystemDefaultsQoS(),
        [this] (const geometry_msgs::msg::Twist::SharedPtr msg) {this->CmdvelCallback(msg);}
    );
    // Relative topic names (P2-a): with absolute names a --namespace could move only half of the stack.
    // Without a namespace these still resolve to /joy, /cmd_vel, ... - see docs/porting.md §4.
    this->joy_subscriber = this->create_subscription<sensor_msgs::msg::Joy>(
        "joy", rclcpp::SystemDefaultsQoS(),
        [this] (const sensor_msgs::msg::Joy::SharedPtr msg) {this->JoyCallback(msg);}
    );
    this->imu_subscriber = this->create_subscription<sensor_msgs::msg::Imu>(
        "imu", LatestQoS(), [this] (const sensor_msgs::msg::Imu::SharedPtr msg) {this->ImuCallback(msg);}
    );
    this->motor_state_subscriber = this->create_subscription<quadruped_ros2::msg::MotorState>(
        "motor_state", LatestQoS(),
        [this] (const quadruped_ros2::msg::MotorState::SharedPtr msg) {this->MotorStateCallback(msg);}
    );

    // service
    this->sim_reset_client = this->create_client<std_srvs::srv::Empty>("sim_reset");
    auto empty_request = std::make_shared<std_srvs::srv::Empty::Request>();
    auto result = this->sim_reset_client->async_send_request(empty_request);

    // S4: no wall-clock loop for control or inference any more. /motor_state drives both through
    // ControlStep(): control every `dt` = 5 ms of SIM time, inference every `decimation` control cycles
    // (20 ms). Pause / slow-motion / fast-forward therefore behave, and everything runs on the ROS
    // executor thread (races gone) - docs/porting.md §5/§7. Only the keyboard keeps a 50 ms wall loop.
    std::cout << LOGGER::INFO << "Feedback-driven clock (sim time): control every " << this->params.dt * 1000.0
              << " ms, inference every " << this->params.dt * this->params.decimation * 1000.0
              << " ms; nothing runs while no feedback arrives" << std::endl;

    // keyboard
    this->loop_keyboard = std::make_shared<LoopFunc>("loop_keyboard", 0.05, std::bind(&RL_Sim::KeyboardInterface, this));
    this->loop_keyboard->start();

#ifdef CSV_LOGGER
    this->CSVInit(this->robot_name);
#endif

    std::cout << LOGGER::INFO << "RL_Sim start" << std::endl;
}

RL_Sim::~RL_Sim()
{
    this->loop_keyboard->shutdown();
    std::cout << LOGGER::INFO << "RL_Sim exit" << std::endl;
}

void RL_Sim::GetState(RobotState<double> *state)
{
    const auto &orientation = this->imu_msg.orientation;
    const auto &angular_velocity = this->imu_msg.angular_velocity;

    state->imu.quaternion[0] = orientation.w;
    state->imu.quaternion[1] = orientation.x;
    state->imu.quaternion[2] = orientation.y;
    state->imu.quaternion[3] = orientation.z;

    state->imu.gyroscope[0] = angular_velocity.x;
    state->imu.gyroscope[1] = angular_velocity.y;
    state->imu.gyroscope[2] = angular_velocity.z;

    // joint_mapping[i]: index in the sim's actuator order of policy joint i (policy/black/base.yaml)
    for (int i = 0; i < this->params.num_of_dofs; ++i)
    {
        state->motor_state.q[i] = this->motor_state_msg.q[this->params.joint_mapping[i]];
        state->motor_state.dq[i] = this->motor_state_msg.dq[this->params.joint_mapping[i]];
        state->motor_state.tau_est[i] = this->motor_state_msg.tau[this->params.joint_mapping[i]];
    }
}

void RL_Sim::SetCommand(const RobotCommand<double> *command)
{
    // S5: limit the command before it leaves this node. We do not send torque, so the rules in
    // command_limit.hpp work on what we do send (q_des / dq_des / kp / kd / tau_ff) and budget the
    // implied torque at the measured state. docs/safety-limits.md section 3 has the design and the
    // guarantees; the counters are reported once a second at most so a biting limit is visible.
    const black_fsm::Knobs &knobs = black_fsm::GetKnobs(this->robot_name);
    command_limit::Limits lim;
    lim.tau = knobs.command_tau_limit;
    lim.kp_max = knobs.command_kp_max;
    lim.kd_max = knobs.command_kd_max;
    lim.dq_max = knobs.command_dq_max;
    lim.slew = knobs.command_slew;
    command_limit::State lim_state;
    lim_state.q = this->robot_state.motor_state.q;
    lim_state.dq = this->robot_state.motor_state.dq;
    lim_state.q_des_prev = this->limited_q_des_prev;
    lim_state.has_prev = this->command_limited_once;
    std::vector<double> q_des(command->motor_command.q);
    std::vector<double> dq_des(command->motor_command.dq);
    std::vector<double> kp(command->motor_command.kp);
    std::vector<double> kd(command->motor_command.kd);
    std::vector<double> tau_ff(command->motor_command.tau);
    const command_limit::Counts limited = command_limit::Apply(q_des, dq_des, kp, kd, tau_ff,
                                                              lim_state, lim, this->params.dt);
    this->limited_q_des_prev = q_des;
    this->command_limited_once = true;
    if (limited.any())
    {
        this->limit_events++;
        const auto now = std::chrono::steady_clock::now();
        if (now - this->last_limit_warn >= std::chrono::seconds(1))
        {
            this->last_limit_warn = now;
            std::cout << std::endl << LOGGER::WARNING << "command limited (events " << this->limit_events
                      << "): slew=" << limited.slew << " torque=" << limited.torque
                      << " gains=" << limited.gains << " dq_des=" << limited.dq_des
                      << " window=" << limited.window << std::endl;
        }
    }

    for (int i = 0; i < this->params.num_of_dofs; ++i)
    {
        this->mit_command_msg.q[this->params.joint_mapping[i]] = q_des[i];
        this->mit_command_msg.w[this->params.joint_mapping[i]] = dq_des[i];
        this->mit_command_msg.kp[this->params.joint_mapping[i]] = kp[i];
        this->mit_command_msg.kd[this->params.joint_mapping[i]] = kd[i];
        this->mit_command_msg.tau[this->params.joint_mapping[i]] = tau_ff[i];
    }

    // S4: publish only when the target changes - the policy output is constant between inferences, so at
    // full speed this drops /mit_command from one per control cycle to one per 20 ms of sim time. The
    // heartbeat keeps the sim's watchdog fed (100 steps = 200 ms of sim time; we send every 100 ms).
    constexpr int kCommandHeartbeatCycles = 20;
    const bool changed = !this->command_sent_once || this->mit_command_msg.q != this->last_sent_command.q
        || this->mit_command_msg.kp != this->last_sent_command.kp
        || this->mit_command_msg.kd != this->last_sent_command.kd
        || this->mit_command_msg.w != this->last_sent_command.w
        || this->mit_command_msg.tau != this->last_sent_command.tau;
    if (!changed && ++this->cycles_since_command_publish < kCommandHeartbeatCycles)
    {
        return;
    }
    this->cycles_since_command_publish = 0;
    this->command_sent_once = true;
    this->last_sent_command = this->mit_command_msg;

    this->mit_command_msg.header.stamp = this->now();
    this->mit_command_publisher->publish(this->mit_command_msg);
}

std::uint32_t RL_Sim::KeyboardMask() const
{
    // library/core's KeyboardInterface() only ever stores the LAST key (and ignores a repeat of the same
    // key), so this adapter maps that single value to one bit; input_map then derives edges by comparing
    // it with the previous cycle. See input_map.hpp for why the keyboard cannot report two keys at once.
    switch (this->control.current_keyboard)
    {
    case Input::Keyboard::Num0: return input_map::Bit(input_map::KbKey::Num0);
    case Input::Keyboard::Num1: return input_map::Bit(input_map::KbKey::Num1);
    case Input::Keyboard::Num2: return input_map::Bit(input_map::KbKey::Num2);
    case Input::Keyboard::Num3: return input_map::Bit(input_map::KbKey::Num3);
    case Input::Keyboard::Num4: return input_map::Bit(input_map::KbKey::Num4);
    case Input::Keyboard::Num5: return input_map::Bit(input_map::KbKey::Num5);
    case Input::Keyboard::Num6: return input_map::Bit(input_map::KbKey::Num6);
    case Input::Keyboard::Num7: return input_map::Bit(input_map::KbKey::Num7);
    case Input::Keyboard::Num8: return input_map::Bit(input_map::KbKey::Num8);
    case Input::Keyboard::Num9: return input_map::Bit(input_map::KbKey::Num9);
    case Input::Keyboard::W: return input_map::Bit(input_map::KbKey::W);
    case Input::Keyboard::A: return input_map::Bit(input_map::KbKey::A);
    case Input::Keyboard::S: return input_map::Bit(input_map::KbKey::S);
    case Input::Keyboard::D: return input_map::Bit(input_map::KbKey::D);
    case Input::Keyboard::Q: return input_map::Bit(input_map::KbKey::Q);
    case Input::Keyboard::E: return input_map::Bit(input_map::KbKey::E);
    case Input::Keyboard::P: return input_map::Bit(input_map::KbKey::P);
    case Input::Keyboard::R: return input_map::Bit(input_map::KbKey::R);
    case Input::Keyboard::N: return input_map::Bit(input_map::KbKey::N);
    case Input::Keyboard::Space: return input_map::Bit(input_map::KbKey::Space);
    default: return 0;
    }
}

void RL_Sim::RobotControl()
{
    // Resolve the input edges once per cycle (input_map.hpp): an edge is a pure function of this cycle
    // and the previous one, so it fires exactly once and never has to be "consumed" — that replaces the
    // library's single-value latch and the four bugs it caused (status.md P1-e/P1-g/P1-h).
    input_map::Frame &in = input_map::Current();
    const std::uint32_t pad = input_map::PadMaskFromJoy(this->joy_msg.buttons, this->joy_msg.axes);
    const std::uint32_t kb = this->KeyboardMask();
    std::array<float, 8> axes{};
    if (this->joy_msg.axes.size() >= 8)
    {
        std::copy(this->joy_msg.axes.begin(), this->joy_msg.axes.begin() + 8, axes.begin());
    }
    input_map::BeginCycleWithJoy(pad, kb, axes, this->have_joy_frame);
    const bool keyboard_edge = in.kb.any_pressed();

    if (in.has(input_map::Intent::ResetSim))
    {
        auto empty_request = std::make_shared<std_srvs::srv::Empty::Request>();
        auto result = this->sim_reset_client->async_send_request(empty_request);
    }
    // The library's keyboard latch ignores a repeated key, so keep upstream's "act, then clear" for the
    // keyboard only: without it, pressing the same key twice in a row would look like one press.
    if (keyboard_edge)
    {
        this->control.current_keyboard = this->control.last_keyboard;
    }

    if (simulation_running)
    {
        this->motiontime++;

        if (in.has(input_map::Intent::JogForward)) this->control.x += 0.1;
        if (in.has(input_map::Intent::JogBackward)) this->control.x -= 0.1;
        if (in.has(input_map::Intent::JogLeft)) this->control.y += 0.1;
        if (in.has(input_map::Intent::JogRight)) this->control.y -= 0.1;
        if (in.has(input_map::Intent::JogYawLeft)) this->control.yaw += 0.1;
        if (in.has(input_map::Intent::JogYawRight)) this->control.yaw -= 0.1;
        if (in.has(input_map::Intent::ZeroCommand))
        {
            this->control.x = 0;
            this->control.y = 0;
            this->control.yaw = 0;
        }
        if (in.has(input_map::Intent::ToggleNavigation))
        {
            this->control.navigation_mode = !this->control.navigation_mode;
            std::cout << std::endl << LOGGER::INFO << "Navigation mode: " << (this->control.navigation_mode ? "ON" : "OFF") << std::endl;
        }

        this->GetState(&this->robot_state);
        this->StateController(&this->robot_state, &this->robot_command);
        this->SetCommand(&this->robot_command);

        if (this->status_period_ms > 0)
        {
            const auto now = std::chrono::steady_clock::now();
            if (now - this->last_status_print >= std::chrono::milliseconds(this->status_period_ms))
            {
                this->last_status_print = now;
                std::cout << "\r\033[K" << std::flush << LOGGER::INFO << "RL Controller x:" << this->control.x
                          << " y:" << this->control.y << " yaw:" << this->control.yaw
                          << " cmd_limit_events:" << this->limit_events << std::flush;
            }
        }
    }
}

void RL_Sim::ImuCallback(const sensor_msgs::msg::Imu::SharedPtr msg)
{
    this->imu_msg = *msg;
}

void RL_Sim::CmdvelCallback(const geometry_msgs::msg::Twist::SharedPtr msg)
{
    this->cmd_vel = *msg;
}

void RL_Sim::JoyCallback(const sensor_msgs::msg::Joy::SharedPtr msg)
{
    // Our joy_node (@20261005_ros2) already publishes the layout and signs used by input_map.hpp
    // (@20261005_ros2/docs/joystick.md §3, porting.md §6.1), so here we only guard the length: indexing
    // a shorter message would read past the end. The key map itself lives in input_map.hpp and is
    // resolved once per control cycle in RobotControl() - see status.md S3.5.
    if (msg->axes.size() < 8 || msg->buttons.size() < 11)
    {
        return;
    }
    this->joy_msg = *msg;
    this->have_joy_frame = true;

    // Continuous commands stay LEVELS applied once per /joy frame (same place and timing as upstream):
    // input_map.hpp above only resolves edges. Keyboard jogging still happens in RobotControl() at
    // 200 Hz, which is why the keyboard path is documented with `joy:=false` (no /joy frames, so these
    // three lines cannot zero the jog).
    this->control.x = this->joy_msg.axes[1] * this->joy_command_scale;   // LY
    this->control.y = this->joy_msg.axes[0] * this->joy_command_scale;   // LX
    this->control.yaw = this->joy_msg.axes[3] * this->joy_command_scale; // RX
}

void RL_Sim::MotorStateCallback(const quadruped_ros2::msg::MotorState::SharedPtr msg)
{
    this->motor_state_msg = *msg;

    // S4: the feedback is the clock - each /motor_state drives the control step below.
    this->ControlStep(msg->sim_time);
}

void RL_Sim::ControlStep(double sim_time)
{
    // Both control and inference are paced by SIM time - not by "one step per feedback message" and not
    // by the wall clock: control every `params.dt` (5 ms), inference every `decimation` control cycles
    // (20 ms). That keeps the work per simulated second constant, and nothing runs while no feedback
    // arrives. Control-per-message instead pushed the feedback to 4-5 kHz at full speed (and /mit_command
    // with it) until the two ends starved each other - see docs/porting.md §2 item 18.
    const double control_period = this->params.dt;

    if (this->last_control_sim_time < 0.0 || sim_time < this->last_control_sim_time
        || sim_time - this->last_control_sim_time > 10.0 * control_period)
    {
        // First frame / sim time went backwards / feedback gap over 10 periods: re-anchor, do not catch up.
        this->last_control_sim_time = sim_time;
        this->cycles_since_inference = 0;
        return;
    }
    if (sim_time - this->last_control_sim_time < control_period)
    {
        return;   // next control period not reached yet
    }

    // Catch up along sim time: normally one step per feedback frame, at most 10 after dropped ones.
    while (sim_time - this->last_control_sim_time >= control_period)
    {
        this->last_control_sim_time += control_period;
        this->RobotControl();
        if (++this->cycles_since_inference >= this->params.decimation)
        {
            this->cycles_since_inference = 0;
            this->RunModel();
        }
    }
}

void RL_Sim::RunModel()
{
    if (this->rl_init_done && simulation_running)
    {
        this->episode_length_buf += 1;
        this->obs.ang_vel = torch::tensor(this->robot_state.imu.gyroscope).unsqueeze(0);
        if (this->control.navigation_mode)
        {
            this->obs.commands = torch::tensor({{this->cmd_vel.linear.x, this->cmd_vel.linear.y, this->cmd_vel.angular.z}});
        }
        else
        {
            this->obs.commands = torch::tensor({{this->control.x, this->control.y, this->control.yaw}});
        }
        this->obs.base_quat = torch::tensor(this->robot_state.imu.quaternion).unsqueeze(0);
        this->obs.dof_pos = torch::tensor(this->robot_state.motor_state.q).narrow(0, 0, this->params.num_of_dofs).unsqueeze(0);
        this->obs.dof_vel = torch::tensor(this->robot_state.motor_state.dq).narrow(0, 0, this->params.num_of_dofs).unsqueeze(0);

        this->obs.actions = this->Forward();
        this->ComputeOutput(this->obs.actions, this->output_dof_pos, this->output_dof_vel, this->output_dof_tau);

        if (this->output_dof_pos.defined() && this->output_dof_pos.numel() > 0)
        {
            output_dof_pos_queue.push(this->output_dof_pos);
        }
        if (this->output_dof_vel.defined() && this->output_dof_vel.numel() > 0)
        {
            output_dof_vel_queue.push(this->output_dof_vel);
        }
        // output_dof_tau is deliberately *not* pushed: upstream pushes it from here and from the five
        // rl_real_*.cpp, but no FSM anywhere pops it (grep try_pop), and tbb::concurrent_queue is
        // unbounded, so it is a pure leak that grows with every inference. This port never uses the
        // feed-forward tau (the FSM sets tau = 0), so we drop the push. See docs/porting.md §2 and
        // docs/learn/rl-sar.md §5.

        // this->TorqueProtect(this->output_dof_tau);

#ifdef CSV_LOGGER
        torch::Tensor tau_est = torch::tensor(this->robot_state.motor_state.tau_est).narrow(0, 0, this->params.num_of_dofs).unsqueeze(0);
        this->CSVLogger(this->output_dof_tau, tau_est, this->obs.dof_pos, this->output_dof_pos, this->obs.dof_vel);
#endif
    }
}

torch::Tensor RL_Sim::Forward()
{
    torch::autograd::GradMode::set_enabled(false);

    torch::Tensor clamped_obs = this->ComputeObservation();

    torch::Tensor actions;
    if (this->params.observations_history.size() != 0)
    {
        this->history_obs_buf.insert(clamped_obs);
        this->history_obs = this->history_obs_buf.get_obs_vec(this->params.observations_history);
        actions = this->model.forward({this->history_obs}).toTensor();
    }
    else
    {
        actions = this->model.forward({clamped_obs}).toTensor();
    }

    if (this->params.clip_actions_upper.numel() != 0 && this->params.clip_actions_lower.numel() != 0)
    {
        return torch::clamp(actions, this->params.clip_actions_lower, this->params.clip_actions_upper);
    }
    else
    {
        return actions;
    }
}

int main(int argc, char **argv)
{
    rclcpp::init(argc, argv);
    rclcpp::spin(std::make_shared<RL_Sim>());
    rclcpp::shutdown();
    return 0;
}
