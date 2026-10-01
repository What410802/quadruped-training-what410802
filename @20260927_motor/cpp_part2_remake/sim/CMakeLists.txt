# 文件：CMakeLists.txt
# 作用：构建电机 + 驱动板模型库 motor_sim_model（只依赖 core，无 SDK、无 I/O）。

add_library(motor_sim_model
    src/model.cpp
)

add_library(motor::sim_model ALIAS motor_sim_model)

target_include_directories(motor_sim_model
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
)

target_link_libraries(motor_sim_model PUBLIC motor::core)

target_compile_features(motor_sim_model PUBLIC cxx_std_17)

if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(motor_sim_model PRIVATE -Wall -Wextra -Wpedantic -Wconversion)
endif()
