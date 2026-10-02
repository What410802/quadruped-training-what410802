# 文件：CMakeLists.txt
# 作用：构建自检：核心单元（无 SDK）+ 模型（无 SDK）+ 报文往返（需 SDK 头文件）。

function(motor_add_test target source)
    add_executable(${target} ${source})
    target_compile_features(${target} PRIVATE cxx_std_17)
    if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
        target_compile_options(${target} PRIVATE -Wall -Wextra -Wpedantic -Wconversion)
    endif()
    add_test(NAME ${target} COMMAND ${target})
endfunction()

motor_add_test(motor_core_tests core_tests.cpp)
target_link_libraries(motor_core_tests PRIVATE motor::core)

motor_add_test(motor_sim_tests sim_tests.cpp)
target_link_libraries(motor_sim_tests PRIVATE motor::sim_model)

if(TARGET motor::wire)
    motor_add_test(motor_wire_tests wire_tests.cpp)
    target_link_libraries(motor_wire_tests PRIVATE motor::wire)
    target_include_directories(motor_wire_tests PRIVATE "${MOTOR_SDK_DIR}/include")
endif()
