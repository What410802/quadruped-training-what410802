# 第三次培训：关节电机

> 任务书 [`docs/teaching-materials/第三次培训任务.pdf.md`](docs/teaching-materials/第三次培训任务.pdf.md)、
> 讲义 [`docs/teaching-materials/motor.pdf.md`](docs/teaching-materials/motor.pdf.md)（随 git 同步）。
>
> **两部分的相关性不强**（共用讲义与模型，但程序、工具、文档各自独立），所以本 README 只做索引，
> 每部分的说明与细节文档都在各自的子工程里：
>
> | 部分 | 任务书要求 | 代码 | 说明 | 细节文档 |
> |---|---|---|---|---|
> | 第一部分 · 仿真 | 加控制程序模拟关节电机特性，控制程序写成状态机（阻尼 / 站立两个状态，按键切换） | [`cpp/`](cpp/) | [`cpp/README.md`](cpp/README.md) | [`cpp/docs/sim.md`](cpp/docs/sim.md) |
> | 第二部分 · 实机 | 官方 SDK 例程让电机转起来 → 写程序慢慢回归 0 位、键盘输入角度并缓慢转过去 → 标零点并正向偏移 30° → 处理零点跳变 | [`cpp_part2/`](cpp_part2/) | [`cpp_part2/README.md`](cpp_part2/README.md) | [`cpp_part2/docs/real.md`](cpp_part2/docs/real.md)（缩写见 [`cpp_part2/docs/glossary.md`](cpp_part2/docs/glossary.md)） |
>
> 目录（TOC）：[状态一览](#状态一览) · [目录结构](#目录结构) · [环境](#环境) ·
> 缩写表（主要针对第二部分）：[`cpp_part2/docs/glossary.md`](cpp_part2/docs/glossary.md)
> （TTY/PTY、Mbaud、LSB、TTL/RS485、CRC、q7/q8/q15…看不懂先翻它）。

## 状态一览

| 阶段 | 状态 |
|---|---|
| 第一部分：状态机仿真（窗口 / 无窗口回归 / 录像） | ✅ 完成；实测数字见 [`cpp/docs/sim.md`](cpp/docs/sim.md) §3 |
| 第一部分附加：倾斜地面、可调摩擦、与第二次培训控制程序的对照 | ✅ 完成（同上 §2.5 / §2.6 / §6） |
| 第二部分 S0：端口探针（转接头能不能配 4 Mbaud、SDK 能不能开端口） | ✅ 通过（FT232H + `ftdi_sio`，4 Mbaud 整除） |
| 第二部分 S1：让电机转起来（带斜坡与限幅） | ✅ 通过（6 次实跑：0 丢帧、温度 30–31 °C、`merror=0`） |
| 第二部分 S2：零力矩手转找零点 + 定“里程计/锯齿” + kd 扫描 + 量断链行为 | 🔧 **工具与手册已就绪**（[`cpp_part2/docs/real.md`](cpp_part2/docs/real.md) §3.7 的 S2a–S2e），待实机执行 |
| 第二部分 S3–S5：回归 0 + 键盘给角度 / 标零点 + 偏移 30° / 零点跳变 | ⏳ 计划、验收标准与已知问题见 [`cpp_part2/docs/real.md`](cpp_part2/docs/real.md) §3；标定符号约定见 §5 |

## 目录结构

```
@20260927_motor/
├── README.md                  # 本文件：只做索引
├── cpp/                       # 第一部分（仿真）的 C++ 工程
│   ├── CMakeLists.txt
│   ├── README.md              # 怎么建、怎么跑、实测摘要、参数
│   ├── docs/sim.md            # 实现、全部实测数字、踩坑；§6 与第二次培训控制程序的对照
│   ├── src/                   # 完整版：main.cpp（只做编排）+ cli.h / scene_setup.h / motor.h / stance.h / state.h
│   │                          #   / observation.h / start.h / viewer.h / recorder.h / ground.h / args.h
│   └── essential/             # 最简版（官方 Simulate 窗口 + 终端按键，站姿从 models/stance.txt 加载）
├── cpp_part2/                 # 第二部分（实机）的程序与工具
│   ├── CMakeLists.txt         # 生成 compile_commands.json（编辑器智能提示）
│   ├── README.md              # 报文/定点标度实测、四个程序、怎么建怎么跑
│   ├── docs/                  # real.md（硬件现状、成熟度、S0–S5 计划）、glossary.md（缩写表）
│   └── src/                   # serial_probe.cpp / spin_test.cpp（要接实机）
│       └── sim/               # 不控制实机的代码：pty_serial_shim.c / fake_motor.h / fake_motor_dryrun.cpp
├── docs/                      # 两部分共用的资料（子工程的文档已移到各自的 docs/）
│   └── teaching-materials/    # 讲义与任务书
├── scripts/
│   └── agent_scripts/         # AI 用来分析/诊断的脚本（不阻塞任务主线）：analyse_spin_log.py / analyse_watch_log.py / check_md_links.py
├── models/ + scenes/          # 两部分共用：模型与场景（从 @20260923_mujoco 复制）+ 搜好存下的 stance.txt
└── output/                    # 产物：cpp/（录像）、terminal/（实机终端日志）
```

## 环境

两部分都用仓库根 [`pixi.toml`](../pixi.toml) 的那一个 pixi 环境：第一部分用里面的 MuJoCo C++ 库 + glfw；
第二部分用里面的 g++/cmake，并链接 `ReadOnly.d/unitree_actuator_sdk` 里**预编译**的宇树 SDK（不需要额外安装东西）。
实机跑程序需要串口权限（当前 `/dev/ttyUSB0` 是 `root:dialout 660`），见 [`cpp_part2/docs/real.md`](cpp_part2/docs/real.md) §1。

与第二次培训的关系：模型、场景、站姿搜索、录像管线这套基础设施沿用
[`@20260923_mujoco/`](../@20260923_mujoco/)；控制程序是重写的，逐条对照见
[`cpp/docs/sim.md`](cpp/docs/sim.md) §6。第二部分与第二次培训没有代码关系（同一系列电机而已）。
