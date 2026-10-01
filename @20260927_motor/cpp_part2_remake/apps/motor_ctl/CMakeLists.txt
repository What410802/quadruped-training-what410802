# 文件：CMakeLists.txt
# 作用：构建验收程序 motor_ctl（链接 core 与实机后端）。

add_executable(motor_ctl main.cpp line_input.cpp)

target_include_directories(motor_ctl PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}") # app 私有头（line_input.hpp）

target_link_libraries(motor_ctl
    PRIVATE
        motor::core
        motor::unitree
        Threads::Threads
)

target_compile_features(motor_ctl PRIVATE cxx_std_17)

if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(motor_ctl PRIVATE -Wall -Wextra -Wpedantic -Wconversion)
endif()

# 运行时 .so 搜索路径：SDK 的 .so 不在系统目录里，而且 sudo 会清掉 LD_LIBRARY_PATH
set_target_properties(motor_ctl PROPERTIES
    BUILD_RPATH "${MOTOR_SDK_LIB_DIR}"
    INSTALL_RPATH "${MOTOR_SDK_LIB_DIR}")
