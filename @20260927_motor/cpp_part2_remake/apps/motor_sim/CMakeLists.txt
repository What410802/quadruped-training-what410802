# 文件：CMakeLists.txt
# 作用：构建虚拟实验台 motor_sim（PTY + 模型 + 报文编解码；只用 SDK 头文件，不链 .so）。

add_executable(motor_sim main.cpp)

target_link_libraries(motor_sim
    PRIVATE
        motor::core
        motor::sim_model
        motor::wire
        Threads::Threads
)

target_compile_features(motor_sim PRIVATE cxx_std_17)

if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(motor_sim PRIVATE -Wall -Wextra -Wpedantic -Wconversion)
endif()
