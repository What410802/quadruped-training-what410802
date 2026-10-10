# rl_sar（只编"仿真里跑 RL 策略"这一个可执行文件 rl_sim）。
#
# 上游 rl_sar e5c2f41 的 CMakeLists.txt 有 344 行，大部分是 ROS 1 / 实机 SDK（宇树、云深处等）
# 的分支；这里按它的 ROS 2 + rl_sim 那一支重写，取舍见 docs/porting.md §2。

cmake_minimum_required(VERSION 3.16)
project(rl_sar VERSION 3.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

# 与上游相同：策略与 yaml 按"源码目录/policy/<robot>/..."查找（rl_sdk.cpp 里拼路径）。
add_definitions(-DCMAKE_CURRENT_SOURCE_DIR="${CMAKE_CURRENT_SOURCE_DIR}")

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(std_srvs REQUIRED)
find_package(quadruped_ros2 REQUIRED) # 消息：MitCommand / MotorState（@20261005_ros2）
find_package(Torch REQUIRED)          # 环境里的 libtorch（根 pixi.toml）
find_package(TBB REQUIRED)
find_package(yaml-cpp REQUIRED)
find_package(Threads REQUIRED)

# 框架层：观测拼接 / 推理 / 动作换算 / yaml 读取 / 状态机（library/core，与上游逐字相同）
add_library(rl_sdk STATIC
    library/core/rl_sdk/rl_sdk.cpp
    library/core/observation_buffer/observation_buffer.cpp
)
target_include_directories(rl_sdk PUBLIC
    library/core/rl_sdk
    library/core/observation_buffer
    library/core/fsm
    library/core/loop
)
target_link_libraries(rl_sdk PUBLIC ${TORCH_LIBRARIES} TBB::tbb yaml-cpp Threads::Threads)

# 适配层：与 @20261005_ros2 仿真节点对接的 ROS 2 节点
add_executable(rl_sim src/rl_sim.cpp)
target_include_directories(rl_sim PRIVATE include policy)
target_link_libraries(rl_sim rl_sdk)
ament_target_dependencies(rl_sim rclcpp sensor_msgs geometry_msgs std_srvs quadruped_ros2)

install(TARGETS rl_sim DESTINATION lib/${PROJECT_NAME})
install(DIRECTORY launch DESTINATION share/${PROJECT_NAME})

ament_package()
