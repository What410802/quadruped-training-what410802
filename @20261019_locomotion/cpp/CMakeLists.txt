cmake_minimum_required(VERSION 3.22)
project(scene_viewer LANGUAGES CXX)

# MuJoCo and glfw come from the repository-root pixi environment (MuJoCo 3.12).
find_package(mujoco REQUIRED)
find_package(glfw3 REQUIRED)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

# Rendering uses mjv/mjr + a self-written GLFW window (viewer.h reused from
# @20260927_motor). No dependency on the official MuJoCo Simulate UI library.
add_executable(scene_viewer src/main.cpp)
target_link_libraries(scene_viewer PRIVATE mujoco::mujoco glfw)
target_compile_options(scene_viewer PRIVATE -Wall -Wextra)
