# ROS 2 入门：工作空间、话题/参数与 launch（Pixi 环境）

> 本目录原为 `@20261005_ros2`，2026-10-05 第四次培训的正式任务（四足机器人的控制器/仿真/手柄节点）开始后改名为 `@20261005_ros2_example`；正式任务在新目录 [`../@20261005_ros2/`](../@20261005_ros2/README.md)，两者共用根 `pixi.toml` 的同一个 `ros2` 环境。改名只动了目录名与指向它的引用（`pixi.toml` 的若干行），内容未变。
>
> 目标：把 ROS 2 Humble 装进本仓库的 Pixi 环境（不依赖系统 `/opt/ros`），按教程 `ros2基本概念.md`（本机只读材料）走通"工作空间 → 话题/参数 → launch"的最小链路，并实验"Pixi 装的 Humble 与系统装的是否等效"。
>
> 结论、实测数字与复现命令在 [`docs/pixi-ros2.md`](docs/pixi-ros2.md)；推进状态（做到哪、下一步、阻滞项）在 [`docs/status.md`](docs/status.md)——本 README 只做入口，不记进度（[`../docs/conventions.md`](../docs/conventions.md) §2）。

## 做了什么

| 部分 | 内容 | 入口 |
|---|---|---|
| 环境 | 根 `pixi.toml` 的**同一个** `default` 环境：RoboStack **`robostack-humble` 稳定通道**装 Humble + conda-forge 的 colcon 与 MuJoCo（2026-10-06 起合成单环境，不再单独开 `ros2` 环境）；已锁 `pixi.lock` | [`../pixi.toml`](../pixi.toml)、[`docs/pixi-ros2.md`](docs/pixi-ros2.md) §1 |
| C++ 包 | `cpp_hello`：`hello_node`（定时打印）、`talker` / `listener`（话题 `hello`，消息内容与周期做成参数）、`talk_listener.launch.py`（一键起两个节点） | [`cpp/src/cpp_hello/`](cpp/src/cpp_hello/) |
| Python 包 | `py_hello`：`hello_node`（每秒打印） | [`python/src/py_hello/`](python/src/py_hello/) |
| 省 source | 激活环境时**自动发现并 source** 仓库里所有已构建工作空间的 `install/setup.sh`（没有 `install/` 就跳过）；脚本在仓库根，所以根 `pixi.toml` 不写任务级路径、新增 ROS 任务不用改它 | [`../scripts/activate_ros2_workspaces.sh`](../scripts/activate_ros2_workspaces.sh)、[`../pixi.toml`](../pixi.toml) 的 `[activation]`；三种用法见 [`docs/pixi-ros2.md`](docs/pixi-ros2.md) §2.2 |

## 环境与依赖

- ROS 2 Humble 由根 [`pixi.toml`](../pixi.toml) 的**唯一环境**提供（RoboStack **`robostack-humble` 稳定通道** + `conda-forge`；2026-10-06 起不再单开 `ros2` 环境），**不用系统 `/opt/ros/humble`**，也不用 `sudo apt`；两者混用/互通的注意事项见 [`docs/pixi-ros2.md`](docs/pixi-ros2.md) §3、§5。
- Python 锁 3.12（**可选约束**：不锁时会解析到 Python 3.14 + RoboStack 新代 `ros2-*`，实测同样可用；三种装法的对照见 [`docs/pixi-ros2.md`](docs/pixi-ros2.md) §6）。环境与其它任务隔离（`no-default-feature = true`）。

## 如何编译与运行

以下命令都在**仓库根**执行（环境由根 `pixi.toml` 声明，只有一个环境，不必带 `-e`）：

```bash
pixi run ros2-build                  # 编译仓库里所有 colcon 工作空间（自动发现，含本目录两个）
cd cpp    && pixi run colcon build --symlink-install   # 只编本目录的 cpp/（pixi 会往上找根 pixi.toml）
cd python && pixi run colcon build --symlink-install   # 只编本目录的 python/
pixi run ros2 run cpp_hello talker     # 话题发布（参数可覆盖）
pixi run ros2 run cpp_hello listener   # 话题订阅
pixi run ros2 launch cpp_hello talk_listener.launch.py   # 一键起一对（教程 §3）
pixi run ros2 run py_hello hello_node
```

`ros2-build`（不带后缀）会一次编译**全部三个** ROS 2 工作空间（本目录两个 + 正式任务的一个）。

`ros2-build` 之后**不必**再手动 `source install/setup.sh`（激活脚本代劳）；想在交互式 shell 里连续敲命令用 `pixi shell`；在仓库目录**之外**（既不在仓库里、也不在其子目录）运行用 `pixi run --manifest-path <仓库>/pixi.toml …`。

## 目录与文件

```text
@20261005_ros2_example/
├── README.md            # 本文件（入口）
├── docs/
│   ├── pixi-ros2.md     # 可行性实验：版本对照、跨安装互通、三种装法对照、坑与注意
│   └── status.md        # 推进情况
├── cpp/                 # colcon 工作空间（C++）
│   └── src/cpp_hello/   # 包：src/ + launch/ + CMakeLists.txt + package.xml
└── python/              # colcon 工作空间（Python）
    └── src/py_hello/    # 包：py_hello/ + resource/ + setup.py + package.xml
```

`cpp/` 与 `python/` 下的 `build/`、`install/`、`log/` 是 colcon 产物，已被根 [`.gitignore`](../.gitignore) 排除。
