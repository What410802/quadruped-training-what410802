# 文件：CMakeLists.txt
# 作用：构建不依赖 SDK 与硬件的核心库 motor_core。

add_library(motor_core
    src/ledger.cpp
    src/format.cpp
    src/command.cpp
    src/session.cpp
)

add_library(motor::core ALIAS motor_core)

target_include_directories(motor_core
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
)

target_compile_features(motor_core PUBLIC cxx_std_17)

if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(motor_core PRIVATE -Wall -Wextra -Wpedantic -Wconversion)
endif()
