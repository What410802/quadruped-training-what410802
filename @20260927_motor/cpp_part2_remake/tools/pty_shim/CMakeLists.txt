# 文件：CMakeLists.txt
# 作用：构建 PTY 串口垫片（LD_PRELOAD 用；只服务实验台与离线演练，实机不加载）。

add_library(pty_serial_shim SHARED pty_serial_shim.c)

target_link_libraries(pty_serial_shim PRIVATE dl)
