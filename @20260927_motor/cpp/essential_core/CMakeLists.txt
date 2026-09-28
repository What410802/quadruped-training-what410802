cmake_minimum_required(VERSION 3.22)
project(essential_core LANGUAGES CXX)

# MuJoCo 与 glfw 都由 pixi 环境提供（与 @20260927_motor/cpp 的完整版、essential/ 同一个环境）
find_package(mujoco REQUIRED)
find_package(glfw3 REQUIRED)
find_package(Threads REQUIRED)    # 控制线程（外加官方界面自己的线程）

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)    # 给 VS Code 的 C++ 智能提示用

if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

# 窗口 = MuJoCo **官方** Simulate 界面（由 libmujoco_simulate 提供，它自己会链 glfw）；
# 头文件与 main.cpp 平铺在同一个 src/ 里，所以不用 target_include_directories。
add_executable(essential_core src/main.cpp)
target_link_libraries(essential_core PRIVATE mujoco::mujoco mujoco::libmujoco_simulate glfw
                                             Threads::Threads)
target_compile_options(essential_core PRIVATE -Wall -Wextra)
