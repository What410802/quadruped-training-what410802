# 文件：CMakeLists.txt
# 作用：构建报文编解码库 motor_wire（只依赖 SDK 头文件与 core 标度；不链 SDK 的 .so）。

add_library(motor_wire
    src/wire.cpp
)

add_library(motor::wire ALIAS motor_wire)

# SDK 的 include 分两层（crc/ 与 unitreeMotor/ 以 include 为根），两个都要；只在 PRIVATE 一侧。
target_include_directories(motor_wire
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    PRIVATE
        "${MOTOR_SDK_DIR}/include"
)

target_link_libraries(motor_wire PUBLIC motor::core)

target_compile_features(motor_wire PUBLIC cxx_std_17)

if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(motor_wire PRIVATE -Wall -Wextra -Wpedantic -Wconversion)
endif()
