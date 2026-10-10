# RoboCon 培训学习仓库

四足组培训期间的任务工作区。每个任务一个 `@<日期>_<主题>` 目录；Python / MuJoCo / C++ 工具链由仓库根目录的 `pixi.toml` 统一声明，不依赖系统 apt 包。

项目约定（提交信息、文档、目录、Git 用法、环境）见 [`docs/conventions.md`](docs/conventions.md)。

## 任务记录

| 日期 | 任务 | 目录 | 任务文档 |
|---|---|---|---|
| 2026-09-22 | C++ / OOP / CMake 基础 | [`@20260922_robot_cpp_training/robot_cpp_oop_cmake_training/`](@20260922_robot_cpp_training/robot_cpp_oop_cmake_training/) | [`验收.md`](@20260922_robot_cpp_training/验收.md) |
| 2026-09-23 | URDF 转换、MuJoCo 仿真（含 C++ 复刻） | [`@20260923_mujoco/`](@20260923_mujoco/) | [`README.md`](@20260923_mujoco/README.md) |
| 2026-09-27 | 关节电机：MIT 混合控制 + 状态机（阻尼/站立）仿真 | [`@20260927_motor/`](@20260927_motor/) | [`README.md`](@20260927_motor/README.md) |
| 2026-10-05 | ROS 2：自定义消息 + 控制器/仿真/手柄三节点 + launch | [`@20261005_ros2/`](@20261005_ros2/) | [`README.md`](@20261005_ros2/README.md)（教程工作区在同期的 [`@20261005_ros2_example/`](@20261005_ros2_example/README.md)） |
| 2026-10-07 | 大作业：移植 rl_sar，用强化学习策略（`best.pt`）替换控制器节点，让仿真里的狗走起来 | [`@20261007_assignment/`](@20261007_assignment/) | [`README.md`](@20261007_assignment/README.md) |

## 快速开始

本仓库 Pixi 环境只有一个（根目录的 `pixi.toml` + `pixi.lock`），安装分两步：先装 `pixi` 本身（单文件包管理器，默认装到 `~/.pixi`，无需 sudo；官方说明见 <https://pixi.prefix.dev/latest/installation/>），再用它重建本仓库环境。

```bash
# ① 装 pixi（装完重开终端或 source 一下 shell 配置以更新 PATH；以后升级用 pixi self-update）
curl -fsSL https://pixi.sh/install.sh | sh

# ② 在仓库根目录还原环境
cd <本仓库根目录>  # 有 pixi.toml 的地方
pixi install

# ③ 验证：版本号，以及 C++ 侧要用的头文件与 CMake 配置都在
pixi run python -c "import mujoco; print(mujoco.__version__)"  # 期望 3.12.0
pixi run printenv ROS_DISTRO                                   # 期望 humble
pixi run ros2 pkg list | wc -l                                 # 期望 190+（含本仓库的包）
pixi run bash -lc 'ls "$CONDA_PREFIX/include/mujoco/mujoco.h" "$CONDA_PREFIX/lib/cmake/mujoco"'

# ④ 跑个 demo：平地场景零力矩仿真（开窗口，需显示服务；仓库默认 egl 无窗口）
pixi run env MUJOCO_GL=glfw python @20260923_mujoco/scripts/simulate.py
```

> ### *如果你坚持用传统 ROS 2 方式……*
> 
> `pixi install` 只负责把依赖装进 `.pixi/envs/default/`。装好之后可以完全不用 `pixi run` 和本仓库的辅助脚本，像用系统 ROS 2（`source /opt/ros/humble/setup.bash`）那样手动激活。
>
> 克隆仓库后在仓库根执行：
>
> ```bash
> pixi install
> ```
>
> 每个新终端在仓库根执行一次：
> 
> ```bash
> export CONDA_PREFIX="$PWD/.pixi/envs/default"
> export PATH="$CONDA_PREFIX/bin:$PATH"
> source "$CONDA_PREFIX/setup.bash"          # zsh 用 setup.zsh；作用相当于 source /opt/ros/humble/setup.bash
> export MUJOCO_GL=egl ROS_LOCALHOST_ONLY=1  # 照抄 pixi.toml 的 [activation.env]
> ```
> 
> 之后 `python`、`cmake`、`colcon`、`ros2` 都是环境里的那一份，各工作空间照常 `colcon build --symlink-install` 再 `source install/setup.bash`（zsh 用 `setup.zsh`），具体命令在各任务 README。与 `pixi run` 相比少了两件事：① 不会自动 source 仓库里所有已构建的工作空间（`scripts/activate_ros2_workspaces.sh` 做的事），要用哪个就自己 source 哪个；② 有依赖关系的工作空间要按顺序编、编完先 source 再编下一个（`pixi run ros2-build` 按日期顺序替你做了）。另外 pixi 还会跑 glib 与 libxml2 的两个激活钩子，本仓库的编译与运行用不到。2026-10-08 在 `env -i` 的干净 shell 里（bash 与 zsh 各一次）照上面四行激活，从零编了 `@20261005_ros2` 与 `@20261007_assignment` 两个工作空间，`ros2 launch` 三个节点能起，大作业的无头自检 7 项全过。

各任务的完整运行方式（脚本参数、C++ 构建与运行、产物位置）见对应任务文档；为什么这么搭环境、踩过哪些坑见 [`docs/pitfalls/environment.md`](docs/pitfalls/environment.md)；ROS 2 与 MuJoCo **合用一个环境**的理由、版本口径、从零重建与稳定通道迁移记录见 [`@20261005_ros2/docs/environment.md`](@20261005_ros2/docs/environment.md)。

## 文档索引

`docs/` 下分两类：`learn/`（研究与学习）、`pitfalls/`（踩坑记录）；项目约定单独一份放 `docs/conventions.md`。

**研究与学习（`docs/learn/`）**

| 文档 | 内容 |
|---|---|
| [`mujoco.md`](docs/learn/mujoco.md) | MuJoCo 知识点与坑点：`MjModel` / `MjData`、`geom` / `friction` / `condim`、坑点里含「运行时改 `geom_pos`/`geom_quat` 会被 `geom_sameframe` 吃掉」（§6.7）与「相机不会跟地面转 / 地面斜了画面却看不出」（§6.8）、渲染后端（§7）、决策反向索引（[§7.6](docs/learn/mujoco.md#76-这些结论驱动了哪些配置决策)）、复现命令（§8） |
| [`graphics-stack.md`](docs/learn/graphics-stack.md) | 图形 / 渲染 / 视频栈速查（OpenGL、Skia、DirectX、EGL、GLFW 各在哪一层） |
| [`unitree-mujoco.md`](docs/learn/unitree-mujoco.md) | 上游 `unitree_mujoco` 研读笔记：架构、线程、通信与目标设计 |
| [`runtime-timing.md`](docs/learn/runtime-timing.md) | 同上，展开到进程 / 线程 / 通信的时序细节；§11 是五种方案的每帧阻滞对比 |
| [`cpp-cmake.md`](docs/learn/cpp-cmake.md) | C++ 与 CMake 问答笔记（`virtual` / `explicit` / `override`、`const` 成员函数、`= delete` 特殊成员函数与 Rule of Three、头文件扩展名、类内 vs 类外定义、CMake target） |
| [`tbb.md`](docs/learn/tbb.md) | TBB（oneTBB）是什么：并行算法 / 并发容器 / 分配器工具箱，为什么 rl_sar 用它的 `concurrent_queue` 在两条线程间传动作（含最小用法与版本 / 许可） |
| [`rl-sar.md`](docs/learn/rl-sar.md) | rl_sar（上游 `e5c2f41` + 主办方分支 + 主办方控制栈）的内部机制速查：分层、键位出处、两份 yaml 的分工与同名项覆盖、参数只在启动时读、三条队列与 `tau` 只进不出、五套时基与 2/5/20 ms 非整数倍、matplotlib/`PLOT`、框架层没用到的功能；以及 black 规格的来源（大作业 handout / 主办方分支 / 主办方控制栈三方互证）与**与 go2 等机型的逐项对照** |
| [`cmake-intellisense.md`](docs/learn/cmake-intellisense.md) | VSCode C++ / CMake 智能提示配置（语言模式、clangd / cpptools、编译数据库） |
| [`ros2-graph-and-clock.md`](docs/learn/ros2-graph-and-clock.md) | ROS 2 两件小事：`/parameter_events` 为什么在 `rqt_graph` 里"有的节点只有去程"（图缓存假象，权威判断用 `ros2 topic info --verbose`）、以及 `/clock` + `use_sim_time` 的机制、好处、四个坑与本任务的取舍 |
| [`mujoco-viewer-keys.md`](docs/learn/mujoco-viewer-keys.md) | MuJoCo 官方窗口的**全量按键与显示开关**：12 个框架按键（含 `F6`/`F7`、`-`/`=` 速度 31 档、`[`/`]` 相机、Tab 收面板）、**42 个显示开关快捷键**（`mjVISSTRING`/`mjRNDSTRING` 两张表，含默认开关状态）、鼠标映射与扰动；并给出移植到自建窗口的**代价分档**（显示那组 ~55 行、扰动 ~100 行、面板类不建议）；**显示那组已实施**——我们的窗口现在有 33 个显示开关快捷键、`F6`/`F7`/`Home`、暂停单步与 31 档速度，键位是数据表（`kRemap` 一行可改） |
| [`ros2-params-and-launch.md`](docs/learn/ros2-params-and-launch.md) | ROS 2 的 launch 参数 / 节点参数 / 命令行参数：两套机制与五个名字、值怎么流（Mermaid）、三个坑、优先级；**核对版**——更正了「launch 把 parameters 写成临时文件后用 `--params-file` 传」这一处机制细节，并补了本仓库的实测证据；§6 讲"参数 YAML 文件"与 launch 桥接的区别（同一机制的两副面孔、写法与覆盖关系） |

**踩坑记录（`docs/pitfalls/`）**

| 文档 | 内容 |
|---|---|
| [`environment.md`](docs/pitfalls/environment.md) | 环境与踩坑记录（本机实测）：为什么用 pixi、conda / PyPI 镜像、URDF→MJCF 与 git 索引、图形后端与显卡、C++ 工具链与编辑器提示 |

**项目约定**

| 文档 | 内容 |
|---|---|
| [`conventions.md`](docs/conventions.md) | 提交信息、文档、目录与命名、环境、验证、外部代码与许可、新任务起步清单 |

`docs/` 与代码、配置之间是双向链接的：**结论写在文档里**（带实测数据与可复现命令），代码与配置的注释**回指结论**。例：`pixi.toml` 里 `MUJOCO_GL` 的注释指向 [`docs/learn/mujoco.md` §7.6](docs/learn/mujoco.md#76-这些结论驱动了哪些配置决策)。
