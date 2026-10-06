# 文件：CMakeLists.txt
# 作用：构建链接宇树官方 SDK 的实机传输后端 motor_unitree。

# 宇树官方 SDK **不在本仓库里**（只读材料 ReadOnly.d/unitree_actuator_sdk）：路径来源，优先级从高到低：
#   ① -DMOTOR_SDK_DIR=<路径>（或 -DUNITREE_SDK_DIR=<路径>）
#   ② 环境变量 MOTOR_SDK_DIR / UNITREE_SDK_DIR
#   ③ 仓库根的 local_paths.cmake（**不入库**，模板见 local_paths.cmake.example，与 cpp_part2 共用一份）
# 仓库同步内容里刻意不出现"仓库之外的路径"（约定见 docs/conventions.md §4）。
if(NOT MOTOR_SDK_DIR)
    include("${MOTOR_REPO_ROOT}/local_paths.cmake" OPTIONAL)
endif()
if(NOT MOTOR_SDK_DIR AND UNITREE_SDK_DIR)
    set(MOTOR_SDK_DIR "${UNITREE_SDK_DIR}")
endif()
if(NOT MOTOR_SDK_DIR AND DEFINED ENV{MOTOR_SDK_DIR})
    set(MOTOR_SDK_DIR "$ENV{MOTOR_SDK_DIR}")
endif()
if(NOT MOTOR_SDK_DIR AND DEFINED ENV{UNITREE_SDK_DIR})
    set(MOTOR_SDK_DIR "$ENV{UNITREE_SDK_DIR}")
endif()
set(MOTOR_SDK_DIR "${MOTOR_SDK_DIR}" CACHE PATH "宇树官方电机 SDK 目录（见仓库根 local_paths.cmake）")

if(NOT EXISTS "${MOTOR_SDK_DIR}/include/unitreeMotor/unitreeMotor.h")
    message(FATAL_ERROR
        "找不到宇树 SDK：${MOTOR_SDK_DIR}\n"
        "  · 仓库根放一份 local_paths.cmake（cp local_paths.cmake.example local_paths.cmake 后填好）\n"
        "  · 或 -DMOTOR_SDK_DIR=<只读材料 ReadOnly.d/unitree_actuator_sdk 的路径>\n"
        "  · 或 -DMOTOR_ENABLE_SDK=OFF 只构建 core 与测试。")
endif()

# 预编译库：Linux64 / Arm64（与官方 CMakeLists 一致）
if(CMAKE_HOST_SYSTEM_PROCESSOR MATCHES "aarch64")
    set(_kSdkLib "${MOTOR_SDK_DIR}/lib/libUnitreeMotorSDK_Arm64.so")
else()
    set(_kSdkLib "${MOTOR_SDK_DIR}/lib/libUnitreeMotorSDK_Linux64.so")
endif()
get_filename_component(MOTOR_SDK_LIB_DIR "${MOTOR_SDK_DIR}/lib" ABSOLUTE)
set(MOTOR_SDK_LIB_DIR "${MOTOR_SDK_LIB_DIR}" PARENT_SCOPE) # 给可执行文件设 rpath 用

add_library(motor_unitree
    src/unitree_transport.cpp
)

add_library(motor::unitree ALIAS motor_unitree)

# SDK 的 include 分两层（crc/ 与 unitreeMotor/ 以 include 为根），所以两个目录都加；
# 它们只在 PRIVATE 一侧，外部（core / 测试）看不到。
target_include_directories(motor_unitree
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    PRIVATE
        "${MOTOR_SDK_DIR}/include"
        "${MOTOR_SDK_DIR}/include/unitreeMotor"
)

target_link_libraries(motor_unitree
    PUBLIC motor::core
    PRIVATE "${_kSdkLib}"
)

target_compile_features(motor_unitree PUBLIC cxx_std_17)

if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(motor_unitree PRIVATE -Wall -Wextra -Wpedantic -Wconversion)
endif()
