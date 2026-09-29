# 第三次培训：关节电机

> 任务书 [`docs/teaching-materials/第三次培训任务.pdf.md`](docs/teaching-materials/第三次培训任务.pdf.md)、 讲义 [`docs/teaching-materials/motor.pdf.md`](docs/teaching-materials/motor.pdf.md)（随 git 同步）。
>
> **两个子任务项的相关性不强**（共用讲义与模型，但程序、工具、文档各自独立），所以本 README 只做索引， 每部分的说明与细节文档都在各自的子工程里：
>
> | 部分 | 任务书要求 | 代码 | 说明 | 细节文档 | |---|---|---|---|---| | 子任务项一（仿真部分） | 加控制程序模拟关节电机特性，控制程序写成状态机（阻尼 / 站立两个状态，按键切换） | [`cpp/`](cpp/) | [`cpp/README.md`](cpp/README.md) | [`cpp/docs/sim.md`](cpp/docs/sim.md) | | 子任务项二（实体电机控制） | 官方 SDK 例程让电机转起来 → 写程序慢慢回归 0 位、键盘输入角度并缓慢转过去 → 标零点并正向偏移 30° → 处理零点跳变 | [`cpp_part2/`](cpp_part2/) | [`cpp_part2/README.md`](cpp_part2/README.md) | [`cpp_part2/docs/real.md`](cpp_part2/docs/real.md)（缩写见 [`cpp_part2/docs/glossary.md`](cpp_part2/docs/glossary.md)） |
>
> 目录（TOC）：[目录结构](#目录结构) · [环境](#环境)。 缩写表（主要针对子任务项二）：[`cpp_part2/docs/glossary.md`](cpp_part2/docs/glossary.md) （TTY/PTY、Mbaud、LSB、TTL/RS485、CRC、q7/q8/q15…看不懂先翻它）。
>
> **任务推进情况**（各阶段做到哪、还差什么、阻滞项、提交与分支）见 [`docs/status.md`](docs/status.md)—— 本 README 只做入口，不记进度（[`../docs/conventions.md`](../docs/conventions.md) §2）。

## 目录结构

```
@20260927_motor/
├── README.md                  # 本文件：只做索引
├── cpp/                       # 子任务项一（仿真部分）：完整版 + 两个精简版（essential / essential_core）
│   └── docs/                  #   sim.md（实现与全部实测）、essential.md（精简版的理由与验证）
├── cpp_part2/                 # 子任务项二（实体电机控制）：include/ + src/（无 main）+ apps/（有 main）
│   └── docs/                  #   runbook / real / zero-semantics / protocol / fixed-point
│                              #   / fake-motor / cli / setup / pitfalls / glossary
├── docs/                      # 两个子任务项共用的资料
│   ├── status.md              # 任务推进情况（阶段状态、下一步、阻滞项、提交与分支）
│   └── teaching-materials/    # 讲义与任务书
├── scripts/
│   ├── run_log.sh             # 实机命令的包装：行缓冲（stdbuf -oL）+ 按时间自动命名日志
│   └── agent_scripts/         # AI 用来分析/诊断的脚本（不阻塞任务主线）
├── models/ + scenes/          # 两个子任务项共用：模型与场景（从 @20260923_mujoco 复制）+ 搜好存下的 stance.txt
└── output/                    # 产物：cpp/（录像）、terminal/（实机终端日志）
```

每个子工程的**目录树、逐文件作用、怎么建怎么跑**都在它自己的 README 里： [`cpp/README.md`](cpp/README.md)（及其 [`docs/essential.md`](cpp/docs/essential.md)）、 [`cpp_part2/README.md`](cpp_part2/README.md)（及其 [`docs/setup.md`](cpp_part2/docs/setup.md)）； 每个脚本/程序干什么也在那几份文档与各自的文件头注释里，本文件不重复。

## 环境

两个子任务项都用仓库根 [`pixi.toml`](../pixi.toml) 的那一个 pixi 环境：子任务项一用里面的 MuJoCo C++ 库 + glfw； 子任务项二用里面的 g++/cmake，并链接 `ReadOnly.d/unitree_actuator_sdk` 里**预编译**的宇树 SDK（不需要额外安装东西）。 实机跑程序需要串口权限（当前 `/dev/ttyUSB0` 是 `root:dialout 660`），见 [`cpp_part2/docs/real.md`](cpp_part2/docs/real.md) §1。

与第二次培训的关系：模型、场景、站姿搜索、录像管线这套基础设施沿用 [`@20260923_mujoco/`](../@20260923_mujoco/)；控制程序是重写的，逐条对照见 [`cpp/docs/sim.md`](cpp/docs/sim.md) §6。子任务项二与第二次培训没有代码关系（同一系列电机而已）。

## AI 助手的使用

本任务的代码与文档有 **AI 助手（GitHub Copilot）参与编写**，按验收规范 §8（允许辅助学习与改代码， 但要求本人能解释）执行：每一处改动都经本人复核、能对着文档与实机数据解释，并记录"为什么这么做" （[`AGENTS.md`](../AGENTS.md) “提交”一节）。
