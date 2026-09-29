# 构建、目录布局与工具链选型

> 面向"为什么这么搭"。**最短的三条构建命令在 [`../README.md`](../README.md)**，本文只讲布局、依赖与选型理由。 相关：[`pitfalls.md`](pitfalls.md)（本子任务项踩过的坑）、[`real.md`](real.md)（硬件与计划）。

## 1 目录布局

```
cpp_part2/
├── include/motor_bench/          # 公开接口（.hpp，Allman、100 列）
│   ├── ticks.hpp                 # 内部定点表示：转子侧 int64 tick + 边界换算
│   ├── motor_bus.hpp             # 串口 + SDK 的薄封装：发一帧、收一帧、去超时计数
│   ├── zero_tracking.hpp         # 零点账本：上电锚定 / 对齐 / 离线重锚 / 跳变修正
│   ├── trajectory.hpp            # 梯形/三次插值（限速限加速度）
│   ├── console.hpp               # 键盘命令解析（`0` / `30` / `mark` / `o+30` …）
│   └── sim/fake_motor.hpp        # 假电机 + 假驱动板（**不用于控制实机**）
├── src/                          # 没有 main() 的：库实现（进 motor_bench_core）+ PTY 垫片（编成 .so）
├── apps/                         # 有 main() 的：motor_ctl / spin_test / serial_probe / sim_fake_motor_dryrun
└── docs/                         # 本子任务项的文档（本文件所在处）
```

分层规则：**接口在 `include/`、实现与平台相关代码在 `src/`、可执行入口在 `apps/`**；`include/motor_bench/sim/` 与 `apps/sim_fake_motor_dryrun.cpp` 是"只在无硬件时用"的那部分，控制实机的三个入口都不依赖它们。

`motor_bench_core` 是一个静态库目标（`src/*.cpp`），四个可执行文件都链它——这样"控制律 / 账本 / 插值" 只有一份实现，dry run 与实机跑的是同一份代码，只差 `--self-test` 有没有打开（见 [`fake-motor.md`](fake-motor.md) §2）。

### 1.1 `apps/` 与 `src/` 的分界：看有没有 `main()`

判据只有一条——**这份 `.cpp` 能不能自己变成一个可执行文件**：

| 目录 | 判据 | 本工程里的文件 |
|---|---|---|
| `apps/` | 有 `main()` ⇒ `add_executable()` 的源文件 | `motor_ctl.cpp`（验收程序）、`spin_test.cpp`（S1）、`serial_probe.cpp`（S2）、`sim_fake_motor_dryrun.cpp`（dry run） |
| `src/` | 没有 `main()` ⇒ 库实现（`add_library()`）或平台垫片 | `motor_bus.cpp` / `zero_tracking.cpp` / `console.cpp`（链进 `motor_bench_core`）、`pty_serial_shim.c`（编成 `.so`） |
| `include/` | 只有声明与 inline，不产出目标 | `motor_bench/*.hpp`、`sim/fake_motor.hpp` |

**为什么不是别的做法**（以及它的代价）：

* **更大的工程**会让每个应用各自成一个 CMake 工程（`apps/<名字>/CMakeLists.txt`，自带依赖、可单独构建）。
  本项目只有 4 个入口 + 1 个库，一个 `CMakeLists.txt` 里四行 `add_executable` 就够，**不拆子目录**； 以后哪个入口长出自己独立的依赖或配置（比如要单独链 GLFW），再按那个方式拆。
* **严格说，这点体量本来都可以放 `src/`**（`src/` 里混放"有 `main()` 的"与"没有 `main()` 的"， 由 CMake 区分谁进库、谁成可执行文件），多一层 `apps/` 并不带来功能上的好处。
  保留它是为了把上面那条判据**摆在目录名上**：一眼能看出这四个源文件各自要变成一个可执行文件， 而 `src/` 里那四个只进库/垫片。代价就是多一层目录。
* 同理，`include/motor_bench/sim/` 里的假电机是"编进库、但只被 dry run 用"的代码——它不是应用， 所以留在 `include/` 一侧（谁都可以 include，靠目录名与 [`fake-motor.md`](fake-motor.md) §5 的 "能证明什么/不能证明什么"约束用途）。

## 2 依赖

| 依赖 | 从哪来 | 说明 |
|---|---|---|
| 宇树电机 SDK | 与仓库根同级的 `ReadOnly.d/unitree_actuator_sdk`（**预编译** `.so` + 头文件） | 不重新编译 SDK；`-DUNITREE_SDK_DIR=<路径>` 可覆盖 |
| g++ / CMake | 仓库根 `pixi.toml` 的 pixi 环境 | 不需要 apt 包、不需要 MuJoCo |
| POSIX（PTY、ioctl） | 系统 | 只在 `--self-test` 与 `src/pty_serial_shim.c` 里用到 |

SDK 的 include 分两层（`crc/crc_ccitt.h` 按 `include/` 为根、`unitreeMotor/xxx.h` 更深一层），所以 `CMakeLists.txt` 把两个目录都加进 include path——手工编译时要写两次 `-I`。

## 3 构建（三条命令，细节）

```bash
cd ..                       # 仓库根目录（有 pixi.toml；ReadOnly.d 与它同级）
pixi run cmake -S @20260927_motor/cpp_part2 -B @20260927_motor/cpp_part2/build
pixi run cmake --build @20260927_motor/cpp_part2/build
```

产物都在 `build/`：`motor_ctl`、`spin_test`、`serial_probe`、`fake_motor_dryrun` 四个可执行文件，以及 `libpty_serial_shim.so`（`--self-test` 的 `LD_PRELOAD` 目标，见 [`fake-motor.md`](fake-motor.md) §3.3）。

这一半只用 g++ / cmake 与 SDK 预编译的 `.so`，**用不到 MuJoCo**，所以不用传 `-DCMAKE_PREFIX_PATH`—— 传了 CMake 会警告 `Manually-specified variables were not used`（子任务项一 `cpp/` 才需要）。

`CMAKE_EXPORT_COMPILE_COMMANDS` 打开后会在 `build/compile_commands.json` 写入每个源文件的编译命令 （含 SDK 的 `-I`），**编辑器（clangd / VS Code C++）靠它才知道 `serialPort/SerialPort.h` 在哪**—— 不建一次就会"代码标红"（配置见仓库 [`../../../docs/learn/cmake-intellisense.md`](../../../docs/learn/cmake-intellisense.md)）。

## 4 选型理由（为什么不是别的做法）

| 选择 | 为什么 | 代价 |
|---|---|---|
| **CMake**（而不是 README 里那种手写 `g++` 一行） | 四个可执行 + 一个垫片 `.so` 要复用同一批源文件；手写命令每加一个文件就要改一遍，还容易漏 `-pthread`/`-ldl`；顺带产出 `compile_commands.json` | 多一层 `CMakeLists.txt`（约 70 行） |
| **C++17 + Allman + 100 列**（`.clang-format`） | 与第二次培训/队内 C++ 工程的风格对齐（`.hpp` 头文件、`include/` 独立目录），读代码时不用切换习惯；`-std=c++17` 对 `<filesystem>` / `std::optional` 之类是白拿的 | 与 SDK 自己的 C++14 头文件混编没问题（我们只调它的 public 接口） |
| **静态库 `motor_bench_core`** | 让"控制律"与"入口"分开：入口只解析参数、打日志；同一个控制律被 dry run 与实机共用 | 多一个 target |
| **PTY 垫片用 `LD_PRELOAD`**（不是改 SDK、不是内核模块） | 不动官方 `.so`、不需要 root、不需要内核模块；只在 `--self-test` 时加载，实机路径上不生效 | 只拦 `TIOCGSERIAL`/`TIOCSSERIAL`，别的问题不掩盖（见 [`pitfalls.md`](pitfalls.md)） |
| **假电机放在 `include/motor_bench/sim/`** | 它是"协议层 mock"，要和真实代码走同一个 SDK、同一套报文；放 `src/` 会让人以为实机也要链它 | 谁都可以 include，靠目录名与文档约束（[`fake-motor.md`](fake-motor.md) §5 说明它证明什么、不证明什么） |
