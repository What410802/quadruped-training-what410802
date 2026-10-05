# 文件：CMakeLists.txt
# 作用：配置 cpp_part2_remake（子任务项二正式实现）的工程入口：核心库、SDK 后端、motor_ctl 与测试。

cmake_minimum_required(VERSION 3.16)

project(motor_real LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON) # 给编辑器 / clangd 的智能提示用

if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

option(MOTOR_ENABLE_SDK "构建链接宇树官方 SDK 的实机后端与 motor_ctl" ON)

# 仓库根（本工程在仓库里的位置是 @<任务>/<子工程>）：用来推算与仓库根同级的只读资源。
get_filename_component(MOTOR_REPO_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../.." ABSOLUTE)

find_package(Threads REQUIRED) # motor_ctl 的 stdin 读线程

add_subdirectory(core)
add_subdirectory(sim)

if(MOTOR_ENABLE_SDK)
    add_subdirectory(backends/unitree_sdk)
    add_subdirectory(wire)
    add_subdirectory(tools/pty_shim)
    add_subdirectory(apps/motor_ctl)
    add_subdirectory(apps/motor_sim)
endif()

include(CTest)
if(BUILD_TESTING)
    add_subdirectory(tests)
endif()
