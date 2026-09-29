# 第三次培训：关节电机

> 任务书 [`docs/teaching-materials/第三次培训任务.pdf.md`](docs/teaching-materials/第三次培训任务.pdf.md)、
> 讲义 [`docs/teaching-materials/motor.pdf.md`](docs/teaching-materials/motor.pdf.md)（随 git 同步）。
>
> **两个子任务项的相关性不强**（共用讲义与模型，但程序、工具、文档各自独立），所以本 README 只做索引，
> 每部分的说明与细节文档都在各自的子工程里：
>
> | 部分 | 任务书要求 | 代码 | 说明 | 细节文档 |
> |---|---|---|---|---|
> | 子任务项一（仿真部分） | 加控制程序模拟关节电机特性，控制程序写成状态机（阻尼 / 站立两个状态，按键切换） | [`cpp/`](cpp/) | [`cpp/README.md`](cpp/README.md) | [`cpp/docs/sim.md`](cpp/docs/sim.md) |
> | 子任务项二（实体电机控制） | 官方 SDK 例程让电机转起来 → 写程序慢慢回归 0 位、键盘输入角度并缓慢转过去 → 标零点并正向偏移 30° → 处理零点跳变 | [`cpp_part2/`](cpp_part2/) | [`cpp_part2/README.md`](cpp_part2/README.md) | [`cpp_part2/docs/real.md`](cpp_part2/docs/real.md)（缩写见 [`cpp_part2/docs/glossary.md`](cpp_part2/docs/glossary.md)） |
>
> 目录（TOC）：[状态一览](#状态一览) · [目录结构](#目录结构) · [环境](#环境) ·
> 缩写表（主要针对子任务项二）：[`cpp_part2/docs/glossary.md`](cpp_part2/docs/glossary.md)
> （TTY/PTY、Mbaud、LSB、TTL/RS485、CRC、q7/q8/q15…看不懂先翻它）。

## 状态一览

| 阶段 | 状态 |
|---|---|
| 子任务项一：状态机仿真（窗口 / 无窗口回归 / 录像） | ✅ 完成；实测数字见 [`cpp/docs/sim.md`](cpp/docs/sim.md) §3 |
| 子任务项一附加：倾斜地面、可调摩擦、与第二次培训控制程序的对照 | ✅ 完成（同上 §2.5 / §2.6 / §6） |
| 子任务项二 S0：端口探针（转接头能不能配 4 Mbaud、SDK 能不能开端口） | ✅ 通过（FT232H + `ftdi_sio`，4 Mbaud 整除） |
| 子任务项二 S1：让电机转起来（带斜坡与限幅） | ✅ 通过（6 次实跑：0 丢帧、温度 30–31 °C、`merror=0`） |
| 子任务项二 S2：零力矩手转找零点 + 定“里程计/锯齿” + kd 扫描 + 量断链行为 + 上电基准 | 🔧 **工具与手册已就绪**（[`cpp_part2/docs/real.md`](cpp_part2/docs/real.md) §3.7 的 S2a–S2f），待实机执行（执行卡：[`cpp_part2/docs/runbook.md`](cpp_part2/docs/runbook.md) §4 批次 3） |
| 子任务项二 S1b：官方 SDK 例程（任务书第 1 条的字面要求） | 🔧 **命令与安全注意事项已就绪**（[`cpp_part2/docs/runbook.md`](cpp_part2/docs/runbook.md) §4 批次 2），待实机执行 |
| 子任务项二 S3–S5：回归 0 + 键盘给角度 / 标零点 + 偏移 30° / 零点跳变 | 🔧 **程序已就绪**（[`cpp_part2/apps/motor_ctl.cpp`](cpp_part2/apps/motor_ctl.cpp)；离线自检八种情形都跑通，见 [cli.md §1](cpp_part2/docs/cli.md) 与 [real.md §3.8](cpp_part2/docs/real.md)），待实机执行（执行卡：runbook §4 批次 4–6） |
| 子任务项二收尾：实机记录表 → 填回文档 → 提交 → 当面验收演示 | ⏳ 记录表与演示脚本已备好（[`cpp_part2/docs/runbook.md`](cpp_part2/docs/runbook.md) §5 / §7），等实机数据 |
| 工程结构对齐：`include/<项目>/**/*.hpp` + `src/*.cpp` + `apps/`，C++17 | 🔧 **`cpp_part2/` 已完成**（2026-09-29：拆成 5 个头文件 + 4 个实现 + 4 个入口，换 Allman/C++17）；`cpp/` 与 `@20260923_mujoco/` 待做，计划见 [`../docs/learn/cpp-cmake.md`](../docs/learn/cpp-cmake.md) 的「落地计划」一节 |

## 目录结构

```
@20260927_motor/
├── README.md                  # 本文件：只做索引
├── cpp/                       # 子任务项一（仿真部分）的 C++ 工程
│   ├── CMakeLists.txt
│   ├── README.md              # 怎么建、怎么跑、实测摘要、参数
│   ├── docs/sim.md            # 实现、全部实测数字、踩坑；§6 与第二次培训控制程序的对照
│   ├── src/                   # 完整版：main.cpp（只做编排）+ cli.h / scene_setup.h / motor.h / stance.h / state.h
│   │                          #   / observation.h / start.h / viewer.h / recorder.h / ground.h / args.h
│   └── essential/             # 最简版（官方 Simulate 窗口 + 终端按键，站姿从 models/stance.txt 加载）
├── cpp_part2/                 # 子任务项二（实体电机控制）的程序与工具
│   ├── CMakeLists.txt         # motor_bench_core 静态库 + 四个可执行 + PTY 垫片；生成 compile_commands.json
│   ├── README.md              # 入口：四个程序、怎么建怎么跑、文档地图
│   ├── docs/                  # runbook.md（现场执行清单：批次 0–7、记录表、故障处置、验收演示）
│   │                          #   / real.md（硬件现状、成熟度、S0–S5 计划与手册、实测记录）
│   │                          #   / zero_semantics.md（上电/运行/离线的零点语义、CLI 设计、验收时序）
│   │                          #   / protocol.md（报文与定点标度实测）/ fixed_point.md（定点 vs 浮点）
│   │                          #   / fake_motor.md（仿真电机：层级、接口、时序、保真度边界）
│   │                          #   / cli.md（motor_ctl 参数与命令）/ setup.md（构建、布局与选型理由）
│   │                          #   / pitfalls.md（无硬件阶段的坑）/ glossary.md（缩写表）
│   ├── include/motor_bench/   # 公开接口（.hpp）：ticks / motor_bus / zero_tracking / trajectory / console
│   │   └── sim/fake_motor.hpp # 假电机 + 假驱动板（不用于控制实机）
│   ├── src/                   # 实现（.cpp）+ pty_serial_shim.c（PTY 垫片）
│   └── apps/                  # 可执行入口：motor_ctl（验收）/ spin_test（S1）/ serial_probe（S2）/ sim_fake_motor_dryrun
├── docs/                      # 两个子任务项共用的资料（子工程的文档已移到各自的 docs/）
│   └── teaching-materials/    # 讲义与任务书
├── scripts/
│   ├── run_log.sh             # 实机命令的包装：行缓冲（stdbuf -oL）+ 按时间自动命名日志
│   └── agent_scripts/         # AI 用来分析/诊断的脚本（不阻塞任务主线）：analyse_spin_log.py / analyse_watch_log.py / analyse_ctl_log.py / check_md_links.py
├── models/ + scenes/          # 两个子任务项共用：模型与场景（从 @20260923_mujoco 复制）+ 搜好存下的 stance.txt
└── output/                    # 产物：cpp/（录像）、terminal/（实机终端日志）
```

## 环境

两个子任务项都用仓库根 [`pixi.toml`](../pixi.toml) 的那一个 pixi 环境：子任务项一用里面的 MuJoCo C++ 库 + glfw；
子任务项二用里面的 g++/cmake，并链接 `ReadOnly.d/unitree_actuator_sdk` 里**预编译**的宇树 SDK（不需要额外安装东西）。
实机跑程序需要串口权限（当前 `/dev/ttyUSB0` 是 `root:dialout 660`），见 [`cpp_part2/docs/real.md`](cpp_part2/docs/real.md) §1。

与第二次培训的关系：模型、场景、站姿搜索、录像管线这套基础设施沿用
[`@20260923_mujoco/`](../@20260923_mujoco/)；控制程序是重写的，逐条对照见
[`cpp/docs/sim.md`](cpp/docs/sim.md) §6。子任务项二与第二次培训没有代码关系（同一系列电机而已）。

## AI 助手的使用

本任务的代码与文档有 **AI 助手（GitHub Copilot）参与编写**，按验收规范 §8（允许辅助学习与改代码，
但要求本人能解释）执行：每一处改动都经本人复核、能对着文档与实机数据解释，并记录"为什么这么做"
（[`AGENTS.md`](../AGENTS.md) “提交”一节）。
