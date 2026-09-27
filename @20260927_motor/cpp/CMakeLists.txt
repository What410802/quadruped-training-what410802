cmake_minimum_required(VERSION 3.22)
project(motor_sim LANGUAGES CXX)

# MuJoCo 与 glfw 都由 pixi 环境提供（与 @20260923_mujoco 的 C++ 工程同一个环境）
find_package(mujoco REQUIRED)
find_package(glfw3 REQUIRED)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)    # 给 VS Code 的 C++ 智能提示用

if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

# 本任务的窗口是**自己写的**（任务要求用键盘切模式，而官方 Simulate 界面不支持自定义按键），
# 所以只链 mujoco + glfw，不链 libmujoco_simulate：渲染走 mjv/mjr，输入走 GLFW 回调。
add_executable(motor_sim src/main.cpp)
target_link_libraries(motor_sim PRIVATE mujoco::mujoco glfw)
target_compile_options(motor_sim PRIVATE -Wall -Wextra)
