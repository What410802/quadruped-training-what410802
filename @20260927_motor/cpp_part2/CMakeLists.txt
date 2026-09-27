cmake_minimum_required(VERSION 3.22)
project(motor_real LANGUAGES C CXX)

# 第三部分（实机）要用的东西：官方宇树电机 SDK（预编译 .so + 头文件）。
# SDK 不在本仓库里（克隆到 ReadOnly.d/unitree_actuator_sdk，与本仓库根同级），默认按这个位置算**绝对路径**
# （相对路径会被 CMake 当成相对源码目录解析，很容易找错），要换就传 -DUNITREE_SDK_DIR=<路径>。
set(_kRepoRoot "${CMAKE_CURRENT_SOURCE_DIR}/../..")
get_filename_component(_kSdkDefault "${_kRepoRoot}/../ReadOnly.d/unitree_actuator_sdk" ABSOLUTE)
set(UNITREE_SDK_DIR "${_kSdkDefault}" CACHE PATH "宇树官方电机 SDK 目录")

set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)    # 给 VS Code / clangd 的智能提示用（解决"代码标红"）

find_package(Threads REQUIRED)

if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

if(NOT EXISTS "${UNITREE_SDK_DIR}/include/unitreeMotor/unitreeMotor.h")
    message(FATAL_ERROR
        "找不到宇树 SDK：${UNITREE_SDK_DIR}\n"
        "请克隆 https://github.com/unitreerobotics/unitree_actuator_sdk 后用 "
        "-DUNITREE_SDK_DIR=<路径> 指定。")
endif()

# SDK 的 include 分两层（crc/crc_ccitt.h 按 include/ 为根，unitreeMotor/xxx.h 更深一层），
# 所以两个目录都加进去
include_directories(
    "${UNITREE_SDK_DIR}/include"
    "${UNITREE_SDK_DIR}/include/unitreeMotor"
    "${CMAKE_CURRENT_SOURCE_DIR}/src"
)

# 预编译的静态/动态库：Linux64 那份（aarch64 上换成 Arm64，与官方 CMakeLists 一致）
if(CMAKE_HOST_SYSTEM_PROCESSOR MATCHES "aarch64")
    set(UNITREE_SDK_LIB "${UNITREE_SDK_DIR}/lib/libUnitreeMotorSDK_Arm64.so")
else()
    set(UNITREE_SDK_LIB "${UNITREE_SDK_DIR}/lib/libUnitreeMotorSDK_Linux64.so")
endif()

find_package(Threads REQUIRED)

# 上面的路径可能是相对的（相对 build 目录以外的调用位置），rpath 要用绝对路径
get_filename_component(UNITREE_SDK_LIB_DIR "${UNITREE_SDK_DIR}/lib" ABSOLUTE)

# src/sim/ = **不用于控制实机**的代码（PTY 垫片、假电机、dry run）；src/ 下其余文件都要接实机。
#
# LD_PRELOAD 垫片：让 SDK 的 SerialPort 能挂在 PTY 上（--self-test 用），实机不需要
add_library(pty_serial_shim SHARED src/sim/pty_serial_shim.c)
target_link_libraries(pty_serial_shim PRIVATE dl)

# 无硬件自检：PTY + 假电机跑通"上位机 → SDK → 报文 → 反馈"
add_executable(fake_motor_dryrun src/sim/fake_motor_dryrun.cpp)
target_link_libraries(fake_motor_dryrun PRIVATE "${UNITREE_SDK_LIB}" Threads::Threads)

# 实机探针：只开端口 / 零力矩读反馈（默认不发字节）
add_executable(serial_probe src/serial_probe.cpp)
target_link_libraries(serial_probe PRIVATE "${UNITREE_SDK_LIB}" Threads::Threads)

# S1：带斜坡与限幅的"让电机慢慢转起来"
add_executable(spin_test src/spin_test.cpp)
target_link_libraries(spin_test PRIVATE "${UNITREE_SDK_LIB}" Threads::Threads)

foreach(t fake_motor_dryrun serial_probe spin_test)
    target_compile_options(${t} PRIVATE -Wall -Wextra)
endforeach()

# 运行时的 .so 搜索路径（不设的话要自己 export LD_LIBRARY_PATH，而且用 sudo 时会被清掉）
set_target_properties(fake_motor_dryrun serial_probe spin_test PROPERTIES
    BUILD_RPATH "${UNITREE_SDK_LIB_DIR}"
    INSTALL_RPATH "${UNITREE_SDK_LIB_DIR}")
