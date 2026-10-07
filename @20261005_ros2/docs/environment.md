# 环境：单环境里有什么、MuJoCo 版本、以及迁移到稳定通道的结果

> 入口（怎么跑）见 [`../README.md`](../README.md)。ROS 2 装在 Pixi 里的**可行性实验**（版本对照、跨安装互通、三种装法）在 [`../../@20261005_ros2_example/docs/pixi-ros2.md`](../../@20261005_ros2_example/docs/pixi-ros2.md)——本文只写**环境本身**（依赖清单、版本口径、从零重建与迁移记录）。

## 1 一个环境，不是两个

2026-10-06 起仓库只用一个 pixi 环境 `default`，里面同时有 **MuJoCo（C++ 库 + Python 绑定）** 与 **ROS 2 Humble**，以及两边的工具链：

```toml
[dependencies]
python = "3.12.*"
cxx-compiler = "*"
cmake = "*"
ninja = "*"
mujoco = "3.12.*"          # C++ 库（mujoco::mujoco）+ Python 绑定
glfw = "*"                 # 我们的仿真窗口（自建，GLFW + mjv/mjr）直接链它
numpy / pyopengl / tk = "*"  # 仓库脚本直接 import 的三个包
ros-humble-ros-base = "*"  # RoboStack 稳定通道
ros-humble-demo-nodes-cpp / -py = "*"   # 教程示例的 talker/listener 用
ros-humble-rqt-graph = "*"     # 看节点图用
qt6-wayland / qt-wayland = "*"  # rqt 是 Qt5：两个平台的 wayland 插件都要（缺 Qt5 那份会告警退回 xcb）
colcon-common-extensions = "*"
evdev = "*"                # 手柄节点读设备 + 仿真手柄造设备
```

为什么能合成一个：两边都是 **Python 3.12 + numpy 2.x（`np2py312` 构建）**，不相冲；合成之后 MuJoCo 的版本只写一处，不会再出现"两个环境各链一份、数字对不上"。**代价与收益**（实测）：

| | 两个环境（2026-10-05～10-06） | 单环境（现在） |
|---|---|---|
| 磁盘 | 1.3 GB + 980 MB = **2.3 GB** | **3.3 GB**（2026-10-07 实测；合并当天是 2.0 GB） |
| 包数量 | 107 + 455 | **507**（2026-10-07 实测；合并当天 455，default 的 107 个是它的子集） |
| 命令 | 每个 ROS 命令都要带 `-e ros2`（当时的环境名） | 一律 `pixi run …` |
| 首装 | 分两次求解/下载 | 一次 |

**"省磁盘"不是合单环境的理由**：2026-10-07 又加了 `ros-humble-rqt-graph` + `qt6-wayland` + `qt-wayland`（画节点图用），单环境已经比合并前两个环境加起来还大；合的理由是**库版本只写一处**、命令不用再带 `-e`，以及依赖只求解一次。

重建（改了 `pixi.toml` 就要走一遍，否则 `.pixi/envs/default` 与锁文件会对不上）：

```bash
pixi lock && pixi install
pixi run python -c "import mujoco, evdev; print(mujoco.__version__)"   # 期望 3.12.0
pixi run cmake --version    # 编译期还要能 find_package(mujoco)/glfw3，见 §3
```

**从头重建**（换机器、或想确认"锁文件 + pixi.toml 就够"）：

```bash
rm -rf .pixi pixi.lock && pixi install    # 实测：包已缓存时 4.6 s，冷缓存是几分钟级
pixi run ros2-build                       # 自动发现并编译全部 colcon 工作空间，实测 39.5 s / 3 个
pixi run python @20261005_ros2/scripts/agent_scripts/check_headless.py          # 期望「全部通过」
pixi run python @20261005_ros2/scripts/agent_scripts/check_joystick_device.py   # 期望「全部通过」；这条要先跑过 `sudo @20261005_ros2/scripts/setup_joy_devices.sh`（见 joystick.md §2）
```

`mujoco` 是元包，带来 `libmujoco`（CMake 目标 `mujoco::mujoco`；元包也带官方 `libmujoco_simulate`，但本任务的自建窗口不用它）、`glfw`、Python 绑定与 `simulate` 程序；`evdev` 是 python-evdev（conda-forge 2.0.0）。

## 2 为什么把 MuJoCo 锁成 3.12.\*

**实测**：不写版本约束时，conda-forge 现在会解析到 **MuJoCo 3.14.0**（`pixi install` 后 `.pixi/envs/default/conda-meta/` 里出现 `mujoco-3.14.0-*`、`libmujoco-3.14.0-*`；2026-10-06 实测），而 `@20260923_mujoco` / `@20260927_motor` 量过的全部数字是 **3.12.0** 下的结果。这个仓库的验收手段之一就是 C++ 与 Python 两侧数字互相对照（[`../../docs/conventions.md`](../../docs/conventions.md) §5），库版本一漂，那些数字就得重测。

所以：`mujoco = "3.12.*"`，**全仓库只有这一处**（合成单环境之后不会再有两份版本漂移的问题）。顺便修正一条过时的说法：`@20260923_mujoco/README.md` 写的"conda-forge 的 mujoco 落后于 PyPI（conda-forge 最高 3.12.0）"在 2026-10 已经不成立——conda-forge 有 3.14.0 了。

## 3 编译期怎么找到 MuJoCo（colcon 之外还有一层）

`colcon build` 时 CMake 默认**不会**去搜 conda 前缀，所以包里显式加了一行（[`../ws/src/quadruped_ros2/CMakeLists.txt`](../ws/src/quadruped_ros2/CMakeLists.txt)）：

```cmake
if(DEFINED ENV{CONDA_PREFIX})
    list(APPEND CMAKE_PREFIX_PATH "$ENV{CONDA_PREFIX}")
endif()
find_package(mujoco REQUIRED)   # mujoco::mujoco（窗口在 include/quadruped_ros2/viewer.hpp 里自建）
find_package(glfw3 REQUIRED)
```

用环境变量而不是写死路径，换机器/换环境名都不用改（[`../../docs/conventions.md`](../../docs/conventions.md) §4）。别的任务里那些 C++ 工程是手工 `-DCMAKE_PREFIX_PATH="$CONDA_PREFIX"`，colcon 这条路没有地方塞这个参数，所以写进 CMakeLists 更稳。

## 4 已迁移到 `robostack-humble` 稳定通道（2026-10-06 完成）

原来用 `robostack-staging`（当时只是"能装"，通道是实验性的）。迁移前先逐条比过，**结论是两边完全等价**，于是直接换掉：

| 检查 | 结果 |
|---|---|
| 迁移前 `pixi.lock` 里来自 `robostack-staging` 的包 | 204 个（linux-64） |
| 这 204 个在 `robostack-humble` 里**同名同版本同构建号**存在的 | **204 / 204** |
| 例：`ros-humble-rclcpp-16.0.19-np2py312h2ed9cc7_18` | 两个通道都有（humble 侧 2026-05-17 上传） |
| 通道规模 | staging 10712 个 linux-64 文件 vs humble 7218 个 |
| 迁移后锁文件 | `robostack-humble` **409** 处、`robostack-staging` **0** 处 |
| 迁移后版本 | `mujoco 3.12.0` / `python 3.12.14` / `ros-humble-rclcpp 16.0.19-np2py312h2ed9cc7_18`——与迁移前**逐位相同** |
| 迁移后回归 | `pixi run ros2-build`（3 个工作空间，39.5 s）+ 两个自检全部通过；`pixi run ros2 pkg list` 195 个（192 来自环境 + 3 个本仓库包） |

上表都是**迁移当天（2026-10-06）**的实测值。现在再量会不一样：2026-10-07 实测 `pixi.lock` 里 `robostack-humble` **423** 处、`pixi run ros2 pkg list` **202** 个——多出来的是后来加的 `ros-humble-rqt-graph` / `qt6-wayland` / `qt-wayland`（见 §1），与通道迁移本身无关。

复现比对（只下压缩版 repodata，比 6 MB 的 json 快得多）：

```bash
curl -s -o /tmp/rd_robostack-humble.bz2 https://conda.anaconda.org/robostack-humble/linux-64/repodata.json.bz2
# 再用 python bz2+json 读它，把 pixi.lock 里的 robostack-staging 文件名逐条比对 → 204/204
```

**两条注意**：

1. **`pixi lock` 不会因为改了 `channels` 就重新求解**。实测：在临时目录里把 `channels` 换成 `robostack-humble`、带着旧锁跑 `pixi lock`，锁文件**逐字节没变**（仍 409 处 staging URL、0 处 humble）——必须 `rm pixi.lock`（或 `pixi update`）再 `pixi lock`。
2. 稳定通道的构建比 staging 少（7218 vs 10712），以后 `pixi add` 新 ROS 包时可选版本可能更旧或更少。
