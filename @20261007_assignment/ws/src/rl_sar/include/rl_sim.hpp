/*
 * Copyright (c) 2024-2025 Ziqi Fan
 * SPDX-License-Identifier: Apache-2.0
 *
 * Modified for @20261007_assignment from rl_sar e5c2f41 include/rl_sim.hpp.
 * Change list: @20261007_assignment/docs/porting.md §2.
 */

#ifndef RL_SIM_HPP
#define RL_SIM_HPP

// #define CSV_LOGGER

#include "rl_sdk.hpp"
#include "observation_buffer.hpp"
#include "loop.hpp"
#include "fsm.hpp"

#include <chrono>
#include <vector>
#include <string>
#include <fstream>

#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/imu.hpp>
#include <sensor_msgs/msg/joy.hpp>
#include <geometry_msgs/msg/twist.hpp>
#include <std_srvs/srv/empty.hpp>
#include "quadruped_ros2/msg/mit_command.hpp"
#include "quadruped_ros2/msg/motor_state.hpp"

class RL_Sim : public RL, public rclcpp::Node
{
public:
    RL_Sim();
    ~RL_Sim();

private:
    // rl functions
    torch::Tensor Forward() override;
    void GetState(RobotState<double> *state) override;
    void SetCommand(const RobotCommand<double> *command) override;
    void RunModel();
    void RobotControl();

    // status line (node parameter; 0 = off)
    int status_period_ms = 0;
    std::chrono::steady_clock::time_point last_status_print{};

    // loop
    std::shared_ptr<LoopFunc> loop_keyboard;
    std::shared_ptr<LoopFunc> loop_control;
    std::shared_ptr<LoopFunc> loop_rl;

    // ros interface
    sensor_msgs::msg::Imu imu_msg;
    geometry_msgs::msg::Twist cmd_vel;
    sensor_msgs::msg::Joy joy_msg;
    quadruped_ros2::msg::MitCommand mit_command_msg;
    quadruped_ros2::msg::MotorState motor_state_msg;
    rclcpp::Subscription<sensor_msgs::msg::Imu>::SharedPtr imu_subscriber;
    rclcpp::Subscription<geometry_msgs::msg::Twist>::SharedPtr cmd_vel_subscriber;
    rclcpp::Subscription<sensor_msgs::msg::Joy>::SharedPtr joy_subscriber;
    rclcpp::Subscription<quadruped_ros2::msg::MotorState>::SharedPtr motor_state_subscriber;
    rclcpp::Publisher<quadruped_ros2::msg::MitCommand>::SharedPtr mit_command_publisher;
    rclcpp::Client<std_srvs::srv::Empty>::SharedPtr sim_reset_client;
    void ImuCallback(const sensor_msgs::msg::Imu::SharedPtr msg);
    void CmdvelCallback(const geometry_msgs::msg::Twist::SharedPtr msg);
    void MotorStateCallback(const quadruped_ros2::msg::MotorState::SharedPtr msg);
    void JoyCallback(const sensor_msgs::msg::Joy::SharedPtr msg);

    // others
    int motiontime = 0;
    double joy_command_scale = 1.5;
};

#endif // RL_SIM_HPP
