cmake_minimum_required(VERSION 3.22)
project(essential_sim LANGUAGES CXX)

# MuJoCo 与 glfw 都由 pixi 环境提供（与 @20260927_motor/cpp 的完整版同一个环境）
find_package(mujoco REQUIRED)
find_package(glfw3 REQUIRED)
find_package(Threads REQUIRED)    # 控制线程（外加官方界面自己的线程）

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)    # 给 VS Code 的 C++ 智能提示用

if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

# 窗口 = MuJoCo **官方** Simulate 界面（由 libmujoco_simulate 提供，它自己会链 glfw），
# 所以这里链 mujoco::libmujoco_simulate，不自己写窗口——自己写窗口只有在"要在窗口里挂自定义按键"
# 时才划算（完整版 ../src/viewer.h 就是为这个写的）；我们改成从终端读按键，于是省掉一整个头文件。
# 头文件与 main.cpp 平铺在同一个 src/ 里，所以不用 target_include_directories。
add_executable(essential_sim src/main.cpp)
target_link_libraries(essential_sim PRIVATE mujoco::mujoco mujoco::libmujoco_simulate glfw
                                           Threads::Threads)
target_compile_options(essential_sim PRIVATE -Wall -Wextra)
