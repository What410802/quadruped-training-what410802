cmake_minimum_required(VERSION 3.8)

project(cpp_hello)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
    add_compile_options(-Wall -Wextra -Wpedantic)
endif()
set(CMAKE_EXPORT_COMPILE_COMMANDS ON) # For IDE IntelliSense

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(std_msgs REQUIRED)

add_executable(hello_node
    src/hello_node.cpp
)
ament_target_dependencies(hello_node
    rclcpp
)

add_executable(talker
    src/talker.cpp
)
ament_target_dependencies(talker
    rclcpp std_msgs
)

add_executable(listener
    src/listener.cpp
)
ament_target_dependencies(listener
    rclcpp std_msgs
)

install(TARGETS
    hello_node
    talker
    listener
    DESTINATION lib/${PROJECT_NAME})

install(DIRECTORY launch
    DESTINATION share/${PROJECT_NAME})

# 说明：本包不启用模板自带的 ament_lint 测试块 —— uncrustify 按 ROS 风格（2 空格）校验，
# 与本目录的 4 空格 / 100 列风格（.clang-format）冲突。见 @20261005_ros2/docs/pixi-ros2.md。

ament_package()
