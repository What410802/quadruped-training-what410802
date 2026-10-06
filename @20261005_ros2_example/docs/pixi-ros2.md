# Pixi 装 ROS 2 Humble：可行性与替代性实验

> 目的：回答"用 Pixi（RoboStack 通道）装的 ROS 2 Humble，和系统 apt 装的 `/opt/ros/humble` 是不是等效、能不能简化开发流程"。本文只记结论、实测数字与复现命令；怎么用（命令入口）见 [`../README.md`](../README.md)，推进状态见 [`status.md`](status.md)。
>
> 背景：ROS 2 已按本地教程 `ros2基本概念.md`（本机只读材料，下称"教程"）做到话题 / 参数，本次把 launch（教程 §3）补齐并做 Pixi 与系统两套安装的对照实验。
>
> 官方依据：[Pixi for Robotics](https://pixi.prefix.dev/latest/robotics/)（Quick Start 用 `robostack-humble` 通道 + `ros-humble-desktop` + `colcon-common-extensions`）。

## 1 环境与版本对照

本仓库只有**一个** pixi 环境 `default`（2026-10-06 起）：MuJoCo 与 ROS 2 Humble 装在同一个环境里，定义就是根 [`pixi.toml`](../../pixi.toml) 的 `[dependencies]`（原先那个独立的 `ros2` 环境已并入，原因见 [`../../@20261005_ros2/docs/environment.md`](../../@20261005_ros2/docs/environment.md) §1）；系统侧是 apt 装的 Humble。下面的对照表是 2026-10-05 实测，2026-10-06 复测过版本未变：

| 项目 | Pixi 环境 `ros2` | 系统 `/opt/ros/humble` | 复现命令 |
|---|---|---|---|
| 发行版 | Humble（`ROS_DISTRO=humble`） | Humble | `pixi run printenv ROS_DISTRO`；`source /opt/ros/humble/setup.bash && printenv ROS_DISTRO` |
| `rclcpp` | 16.0.19（`np2py312h2ed9cc7_18`） | 16.0.21（`1jammy.20260907.213403`） | `pixi list`；`dpkg-query -W ros-humble-rclcpp` |
| `rmw_fastrtps_cpp` | 6.2.10 | 6.2.10 | 同上 |
| `fastrtps`（Fast DDS） | 2.6.11 | 2.6.12 | 同上 |
| Python | 3.12.14（环境自带，`which python` 指向 `.pixi/envs/default`） | 3.10（`/usr/bin/python3`，rclpy 的 C 扩展编译在 3.10 下） | `pixi run python -V`；`python3 -V` |
| 编译器 | conda-forge gcc 15.3.0 | gcc 11.4.0（Ubuntu 22.04） | `pixi run gcc --version`；`gcc --version` |
| CMake | 4.2.3 | 3.22.1 | `pixi run cmake --version`；`cmake --version` |
| colcon | 元包 20 个组件，`colcon version-check` 20/20 up-to-date | `/usr/bin/colcon` | `pixi run colcon version-check`；`colcon version-check` |
| 包数量（`ros2 pkg list`） | 195（192 来自环境 + 本仓库 3 个包） | 284 | `pixi run ros2 pkg list \| wc -l`；`source /opt/ros/humble/setup.bash && ros2 pkg list \| wc -l` |
| 磁盘占用 | 2.0 GB（`.pixi/envs/default`，含编译器 / CMake / Python / 整套 ROS 2；原先 MuJoCo 环境 + ros2 环境合计 2.3 GB） | `/opt/ros` 204 MB；`ros-humble-*` 293 个包本体 168 MB（apt 依赖散落在 `/usr`） | `du -sh .pixi/envs/default /opt/ros`；`dpkg-query -W -f='${Installed-Size}\t${Package}\n' 'ros-humble-*'` |
| 激活开销 | `pixi run true` 约 0.40–0.42 s（3 次：0.42 / 0.40 / 0.41） | `source /opt/ros/humble/setup.bash` 即 shell 内建 | `/usr/bin/time -f '%e s' pixi run true` |

两边默认的中间件都是 `rmw_fastrtps_cpp`（`ros2 doctor --report` 的 MIDDLEWARE 一栏）；Pixi 侧还额外带了 `rmw_cyclonedds_cpp`，`RMW_IMPLEMENTATION=rmw_cyclonedds_cpp` 切换实测可用（见 §4）。

版本差异说明：ROS 2 的 ABI 兼容策略是"同一发行版内 patch 级兼容"，`rclcpp` 16.0.19 vs 16.0.21、Fast DDS 2.6.11 vs 2.6.12 都在 Humble 的兼容范围内，这也是 §3 跨安装互通能成立的前提。

## 2 三个问题的结论

### 2.1 可执行文件"效果相同"吗？

**行为相同、线上互通，但二进制不通用，各自绑定各自的安装。**

- 同一份源码（`cpp/src/cpp_hello`）在两边编译出的节点行为一致：话题名、消息类型、参数、launch 都按源码工作；跨安装互通实测见 §3。
- 但两边的可执行文件不是"一样的东西"：Pixi 编译的带 **`DT_RPATH`** 指向 `.pixi/envs/default/lib`（绝对路径），系统编译的带 **`DT_RUNPATH`** 指向 `/opt/ros/humble/lib`。

| 对照项 | Pixi 编译（`cpp/build/cpp_hello/talker`） | 系统编译（同一份源码，`colcon build` 于 `/opt/ros/humble` 环境） |
|---|---|---|
| 动态标签 | `DT_RPATH` → `.pixi/envs/default/lib` | `DT_RUNPATH` → `/opt/ros/humble/lib` |
| 裸跑（不 source 任何环境） | ✅ 正常发布 | ❌ `error while loading shared libraries: liblibstatistics_collector.so` |
| 直接 `NEEDED` 数 | 69 | 9 |
| 文件大小 | 673,632 B | 820,816 B |
| `libstdc++` 来源 | `.pixi/envs/default/lib`（conda-forge） | `/lib/x86_64-linux-gnu`（系统） |
| `libc` 来源 | 系统 `/lib/x86_64-linux-gnu` | 系统 |

命令：`readelf -d <exe> | grep -E 'RPATH\|RUNPATH'`；裸跑直接执行 exe；`ldd <exe>` 看库来源。

两条机制上的原因（都用小实验核实过，见 §4）：

1. **`DT_RPATH` 与 `DT_RUNPATH` 的查找语义不同**：`RPATH` 优先于 `LD_LIBRARY_PATH`、且对本进程所有（含间接）依赖生效；`RUNPATH` 排在 `LD_LIBRARY_PATH` 之后、只作用于直接依赖。系统 exe 缺的 `liblibstatistics_collector.so` 是 `librclcpp.so` 的依赖（间接），所以系统 exe 必须靠 `source` 提供的 `LD_LIBRARY_PATH` 才找得到；Pixi exe 靠 RPATH 自己就能找全。标签类型来自工具链默认值：conda-gcc 默认旧式 `--disable-new-dtags`（→ RPATH），Ubuntu gcc 默认新式（→ RUNPATH）。
2. **`--as-needed` 默认不同**：Ubuntu gcc 默认裁剪未直接使用的库，conda-forge gcc 不裁剪，所以 Pixi 二进制带 69 条 `NEEDED`（把间接依赖也显式链接/记录进来了）。

RPATH 是**本机绝对路径**，因此：

- Pixi 编译的 exe 拷到别的机器（或把仓库换目录）就跑不起来，跨机部署要带上同路径环境、或用 `patchelf` 改 RPATH、或进容器；
- 反过来，因为 `DT_RPATH` 优先于 `LD_LIBRARY_PATH`，**在系统 ROS 的 shell 里跑 Pixi 编译的 exe，加载的仍是 Pixi 的库**（实测 `LD_DEBUG=libs` 确认）——这既是"能裸跑"的原因，也意味着两套环境的产物不要混着用。

### 2.2 简化了什么，哪些仍然要手写

**简化（相对系统 ROS + 教程的流程）**：

- 不再需要每开一个终端 `source /opt/ros/humble/setup.bash`：`pixi run …` / `pixi shell` 自动进入环境；
- 不再需要 `sudo apt install`：装 / 删 / 换版本都改 `pixi.toml`（RoboStack + conda-forge），环境在 `.pixi/envs/default`，不碰系统；
- 工作空间的 `install/setup.sh` 也省了：根 `pixi.toml` 的 `[feature.ros2.activation]` 在环境激活时调用**仓库级** [`../../scripts/activate_ros2_workspaces.sh`](../../scripts/activate_ros2_workspaces.sh)，它**自动发现**仓库里所有 `@<任务>/**/install/setup.sh` 并依次 source（没构建过的跳过），`colcon build` 之后自动接上（官方 robotics 文档的 `[activation] scripts` 就是同样做法）；脚本放在仓库根而不是某个任务目录里，是为了让根 `pixi.toml` 不写任务级路径——新增 ROS 任务再也不用改根文件。
- 常用操作固化成任务：`pixi run ros2-build`——脚本**自动发现**仓库里所有 colcon 工作空间并逐个 `colcon build --symlink-install`（根 `pixi.toml` 里因此没有任务级路径）；只编一个时 `cd <工作空间> && pixi run colcon build --symlink-install`；
- 依赖可复现：`pixi.lock` 固化到具体构建号，换机器/换人重建结果一致；**只有一个环境**，MuJoCo 与 ROS 2 共用同一套 Python/编译器，不会出现两份库版本漂移。

**"每次都得 source"这件事：三种用法，按场合挑**

ROS 2 的官方实践是"每个新 shell `source` 一次环境与工作空间"。本仓库的取舍是把"环境"交给 pixi（`pixi run` / `pixi shell` 自动进环境），把"工作空间"交给上面那个激活脚本，于是三种用法分别是：

| 用法 | 命令 | 适合 | 代价 |
|---|---|---|---|
| 一次性命令（**默认推荐**） | `pixi run ros2 topic list` | 跑一条命令、写脚本、CI | 每次要带 `pixi run`（可写成 pixi 任务固化） |
| 交互会话 | `pixi shell` 之后随便敲 `ros2 …` | `ros2 topic echo`、反复试参数（实测：进去就能 `ros2 pkg prefix quadruped_ros2`，`ROS_DISTRO=humble`） | 多敲一条 `pixi shell`；只在**交互终端**里好用（管道喂命令进去不行，它要有 TTY） |
| 官方做法（手动 source） | `source @20261005_ros2/ws/install/setup.sh` | 在**已经有 ROS 2 的 shell**里（如系统装了 `/opt/ros/humble` 时），或要把环境接到别的工具（IDE、ros2 doctor…） | 每个新 shell 手敲一次；**在本仓库里它必须发生在 pixi 环境之内**——因为 ROS 2 只存在于 `.pixi/envs/default`（裸 shell 里 `command -v ros2` 是空的，`install/setup.sh` 只是往 PATH/AMENT_PREFIX_PATH 里加东西，它不提供 `ros2` 本体） |

所以"要不要遵守官方实践"的答案是：**在本仓库里两者并不冲突**——官方实践是"进环境 + source 工作空间"，pixi 负责前半句、激活脚本负责后半句；`pixi shell` 就是"进环境"那条命令的等价物，需要接外部工具时再手动 `source …/install/setup.sh`（这时环境已经在 pixi 里了，source 才有效）。真要脱开 pixi，就得自己装一套 ROS 2（系统或 robostack），那是另一个取舍。

**脚本里那个 `IFS` 是干什么的**（`scripts/activate_ros2_workspaces.sh` 与 `scripts/build_ros2_workspaces.sh` 都用了这一手）：

```sh
_list=$(find "$root" -maxdepth 4 -type d -name src … | LC_ALL=C sort)
IFS='
'
for _x in $_list; do …; done          # 循环留在当前 shell
IFS=$_ifs_saved                       # 用完还原
```

1. `$(…)` 的结果在 `for _x in $_list` 里是**按 `IFS` 拆词**的。默认 `IFS` 含空格，路径里只要有空格就会被拆成两段 → 把 `IFS` 单独设成"只有一个换行"，就只按行拆，路径原样保留。
2. `IFS` 是**当前 shell 的全局变量**，改完要恢复（所以脚本先存一份再还原），否则同一 shell 里后续命令的分词行为会跟着变。
3. **不能用最直观的 `find … | while read …`**：管道的每一段都在**子 shell** 里执行，循环里 `source` 出来的环境、`cd` 出来的目录、`export` 的变量，出了循环就没了。激活脚本必须在**当前** shell 里 `source`（否则工作空间根本没接上），所以只能用"变量 + 换行 `IFS`"这种留在本 shell 的迭代；构建脚本把 `cd` 放进 `( … )` 子 shell 里，正是为了只影响那一轮。

**改名会让 colcon 构建缓存失效**（实测踩到）：`build/` 里记着**绝对**源码路径，把任务目录从 `@20261005_ros2` 改成 `@20261005_ros2_example` 之后直接 `colcon build` 会报 `CMake Error: The source directory "…/@20261005_ros2/cpp/src/cpp_hello" does not exist`。处理就是删掉 `build/ install/ log/` 重编一次（都是 `.gitignore` 覆盖的产物，删了不心疼）；`install/` 里还有指向旧路径的脚本，所以三个都要删。

**仍然要手写（Pixi 管不到的）**：

- `CMakeLists.txt` / `package.xml` / `setup.py` 与系统 ROS **完全一样**——Pixi 不改变 ROS 的构建系统；教程里怎么写，这里还怎么写（本任务目录即按教程搭的）；
- "source 工作空间"这件事本身源自 ament/colcon 的工作空间模型，与包管理器无关，只是现在由激活脚本代劳；
- `.gitignore` 要排除 `build/`、`install/`、`log/`（本仓库已加，见根 [`.gitignore`](../../.gitignore)）；
- `rosdep` 不可用（官方明确说明：它绕开 Pixi 调 apt/pip），缺包时用 `pixi add`；
- 想在**工作空间目录外**用这个环境，要显式给 manifest：`pixi run --manifest-path <仓库>/pixi.toml …`（直接 `pixi run` 会报 "could not find pixi.toml"）。

### 2.3 与官方文档路径的差异

官方 Quick Start 是 `robostack-humble` 通道 + `ros-humble-desktop` + `colcon-common-extensions`；本仓库有三处差异，都是有意为之：

| 项 | 官方示例 | 本仓库 | 说明 |
|---|---|---|---|
| 通道 | `robostack-humble`（**现在用的就是这个**） | `robostack-staging`（当时的实验选择，2026-10-06 已迁走） | 两个通道有同一批 `ros-humble-*` 构建（`rclcpp 16.0.19` 的 `np2py312h2ed9cc7_18` 两边都有），staging 的构建更新一些（`ros-humble-rclcpp` 的 linux-64 文件：9 vs 7）；要切回稳定通道只改 `channels` 一行 |
| 包 | `ros-humble-desktop` | `ros-humble-ros-base` + demo 节点包 | 本环境是无 GUI 的编译/冒烟用途，desktop 的 rviz 等用不上；要 GUI 再加 `ros-humble-desktop`（通道里存在，已验证） |
| Python | 不锁 | `python = "3.12.*"` | RoboStack 新代包名是 `ros2-*`、目前只发 py314 构建（`ros2-rclcpp 16.0.19` 的 linux-64 只有 `np2py314h53a0733_20` 一条）；锁 3.12 解析到 `ros-humble-*` 一代，与仓库其它任务（MuJoCo 等）共用一套 Python 习惯 |

`colcon` 的处理也有过一轮修正（2026-10-05）：原先按 14 个组件逐个声明，理由是"conda-forge 的 `colcon-common-extensions` 只有 ≤py310 的旧构建"——这条已经过时，conda-forge 现在有 `colcon-common-extensions-0.3.0-py312h20c3967_5`（2026-09-19 上传），解析验证通过并换成元包写法。元包覆盖原清单 14 个里的 13 个（**`colcon-mixin` 不在元包里**），另多带 7 个（`colcon-cd` / `colcon-metadata` / `colcon-output` / `colcon-package-information` / `colcon-package-selection` / `colcon-powershell` / `colcon-zsh`），共 20 个。`colcon version-check` 实测 20/20 up-to-date。

## 3 跨安装互通实测（关键实验）

两台"节点"：系统 ROS 编译的 `cpp_hello`（同一份源码，`/opt/ros/humble` 环境 `colcon build`）与 Pixi 编译的 `cpp_hello`。话题名 `/hello`、类型 `std_msgs/msg/String` 相同。

| 实验 | 对端 `ROS_LOCALHOST_ONLY` | 结果 |
|---|---|---|
| Pixi talker → 系统 listener | 1 / 未设置（=0） | ❌ 收到 0 条 |
| 系统 talker → Pixi listener | 未设置 / 1 | ❌ 收到 0 条 |
| 两边都 = 1 | 1 / 1 | ✅ 系统 listener 收到 4 条 |
| 两边都 = 0（Pixi 侧 `env ROS_LOCALHOST_ONLY=0` 覆盖） | 0 / 0 | ✅ 系统 listener 收到 4 条 |
| Pixi 编译 talker → 系统编译 listener（都 =1） | 1 / 1 | ✅ 收到 4 条（`收到: cross`） |
| 系统编译 talker → Pixi 编译 listener（都 =1） | 1 / 1 | ✅ 收到 9 条（`收到: cross2`） |

`demo_nodes_cpp` 的标准 talker/listener 同样双向通过（收到 `Hello World: 1`…）。**结论：不是不兼容，而是 `ROS_LOCALHOST_ONLY` 必须两端一致**——本仓库环境里设了 `1`（只走回环），系统 ROS 默认不设（等效 0）。跨机联调、或与系统 ROS 混跑时，统一为 `0`（或两边都设 `1`）即可。

复现（仓库根；`ros2` 命令都用 `pixi run` 执行，仓库只有一个环境、不必带 `-e`）：

```bash
# 系统侧 listener（另开终端）
source /opt/ros/humble/setup.bash
export ROS_LOCALHOST_ONLY=1
ros2 run demo_nodes_cpp listener

# Pixi 侧 talker
pixi run ros2 run demo_nodes_cpp talker
```

## 4 实验记录（复现命令与实测结果）

| # | 命令（仓库根执行） | 结果 |
|---|---|---|
| 1 | `pixi run ros2-build` | cpp_hello、py_hello 各 `Finished`；增量 0.30 s / 1.75 s |
| 2 | `pixi run ros2 run cpp_hello talker` + `listener` | 话题 `/hello` 每秒一条，收发光字等 |
| 3 | `timeout 8 pixi run ros2 launch cpp_hello talk_listener.launch.py` | 一两行启动日志后按 launch 参数输出 `发布第 1 条: 你好，ros2` / `收到: 你好，ros2`，周期 0.5 s（教程 §3） |
| 4 | `ros2 topic hz /hello`（talker `period_ms:=300`） | `average rate: 3.333`，`std dev 0.00017s` |
| 5 | `ros2 node list` / `node info /talker` / `topic list -t` / `topic info /hello` | 全部正常（教程 §1.6 速查表） |
| 6 | `ros2 topic pub --once /hello std_msgs/msg/String "{data: 'manual'}"` | listener 收到 1 条 `收到: manual` |
| 7 | `ros2 param get /talker message` / `param set /talker message hi` | 读到 `hello`；设置返回 `Set parameter successful` |
| 8 | `ros2 run demo_nodes_cpp add_two_ints_server` + `ros2 service call /add_two_ints example_interfaces/srv/AddTwoInts "{a: 20, b: 22}"` | 返回 `sum=42`（服务链路） |
| 9 | `RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ros2 run cpp_hello hello_node` | 正常起节点（Pixi 侧带 CycloneDDS；系统侧未装） |
| 10 | `ros2 pkg create --build-type ament_cmake scratch_pkg --dependencies rclcpp` + `colcon build`（临时目录） | 骨架生成、编译 2.24 s 通过（`ros2 pkg list` 能查到） |
| 11 | `pixi run --manifest-path <仓库>/pixi.toml ros2 pkg list`（在 `/tmp` 下） | 正常（工作区外用法） |

§2.1 的机制实验：

```bash
# 工具链默认 dtags：conda-gcc 出 RPATH、系统 gcc 出 RUNPATH
printf 'int main(){return 0;}\n' > /tmp/dt.c
pixi run gcc /tmp/dt.c -Wl,-rpath,/tmp -o /tmp/dt_pixi && readelf -d /tmp/dt_pixi | grep -E 'RPATH|RUNPATH'
gcc /tmp/dt.c -Wl,-rpath,/tmp -o /tmp/dt_sys && readelf -d /tmp/dt_sys | grep -E 'RPATH|RUNPATH'
```

`colcon` 元包验证（不动仓库、在临时目录做）：

```bash
mkdir -p /tmp/pixi_colcon_test && cd /tmp/pixi_colcon_test   # 写一份含 colcon-common-extensions 的最小 pixi.toml
pixi lock && grep -o 'colcon-common-extensions[^ ]*\.conda' pixi.lock
```

## 5 坑与注意

1. **`ROS_LOCALHOST_ONLY` 必须两端一致**——不一致时两个节点互相发现不到（§3 实测 0 条，且不给任何报错）。本环境设 `1` 是"只在本机"的刻意选择，写在根 `pixi.toml` 的 `[activation.env]`。
2. **不要在同一个 shell 里混 source**：在 Pixi 环境里 `source /opt/ros/humble/setup.bash` 后，`which ros2` 变成系统的，且 Python 3.12 去 import 系统为 3.10 编译的 `rclpy` 会失败（实测报 `_rclpy_pybind11.cpython-312-...so isn't present`）。要用哪套就整条链路用哪套。
3. **不要复用别的环境编译出的 `build/` 目录**：`colcon build` 记录编译器与 `CMAKE_PREFIX_PATH`，换了环境要清掉 `build/` 重编，否则 CMake 缓存里是另一套路径。
4. **RPATH 优先级**：Pixi 编译的 exe 在系统环境里也会优先加载 Pixi 的库（`DT_RPATH` > `LD_LIBRARY_PATH`），别指望"用系统库覆盖"。
5. **绝对 RPATH → 不可搬迁**：exe 与 `.pixi/envs/default` 路径绑定；跨机部署要另想办法（同路径环境 / `patchelf` / 容器）。
6. **`colcon-mixin` 已不在依赖里**（不属于 `colcon-common-extensions`）：需要 `colcon mixin` 子命令时再 `pixi add colcon-mixin`。
7. **体积**：`ros2` 环境 1.9 GB（含 gcc / CMake / Python 3.12），`.pixi/` 不进 git；删环境用 `pixi clean` 之类的常规途径即可，不污染系统。

## 6 三种安装方式对照（2026-10-05 追加实验）

回答两个问题：**"其他人的机器上 `pixi install` 能不能自己搞定"、"ROS 部分能不能不锁 Python 版本"**。为此在同一台机器上实测了第三种装法：把 `python` 从依赖里去掉（实测解析到 **Python 3.14.7 + RoboStack 新代 `ros2-*` 包**，以下简称"不锁"），三个环境各自编译同一份 `cpp_hello` / `py_hello` 并做互通测试。

三种方式（A 系统 apt / B 本仓库锁定 3.12 / C 不锁 Python）：

| 维度 | A 系统 apt | B 本仓库（`python = "3.12.*"`） | C 不锁 Python |
|---|---|---|---|
| 安装位置 | `/opt/ros/humble` + `/usr`（要 `sudo`） | `.pixi/envs/default`（项目内，无 root） | `.pixi/envs/<名称>`（同左） |
| 包名世代 | `ros-humble-*`（distro 包） | `ros-humble-*`（`np2py312h2ed9cc7_18`） | **`ros2-*`**（`np2py314h53a0733_20`；`ros-humble-ros-base` 等元包仍在，只是变成指向 `ros2-*` 的壳） |
| `rclcpp` / `rclpy` / `rmw_fastrtps_cpp` | 16.0.21 / 3.3.21 / 6.2.10 | 16.0.19 / 3.3.21 / 6.2.10 | 16.0.19 / 3.3.21 / 6.2.10 |
| `fastrtps` | 2.6.12 | 2.6.11 | 2.6.11 |
| Python | 3.10（系统 `/usr/bin/python3`） | 3.12.14 | 3.14.7 |
| CMake / gcc | 3.22.1 / 11.4.0 | 4.2.3 / 15.3.0 | 4.4.4 / 15.3.0 |
| `ros2 pkg list` | 284 | 194（含本任务两个工作空间） | 192 |
| 环境体积 | `/opt/ros` 204 MB + apt 依赖散落 `/usr` | 1.9 GB | 2.0 GB |
| 激活开销（`pixi run … true`） | 0.15–0.18 s（`source /opt/ros/humble/setup.bash`，每个终端一次） | 0.45–0.49 s（含自动 source 两个工作空间 0.27–0.29 s） | 0.16–0.17 s（无自动 source） |
| 复现保证 | 无（apt 随机器/时间变） | `pixi.lock` 精确到构建号 | 同左（`pixi.lock`；`python` 只是没有**声明**约束） |

编译与运行结果（同一份源码，三处都编译 `cpp_hello` + `py_hello`）：

| 检查项 | A 系统 | B 锁定 3.12 | C 不锁（3.14） |
|---|---|---|---|
| `colcon build` C++ | ✅ | ✅ | ✅（CMake 4.x 对 `cmake_minimum_required(3.8)` 只报弃用警告） |
| `colcon build` Python（`ament_python`） | ✅ | ✅ | ✅（setuptools 79.0.1，**不需要**官方教程里的 `setuptools<=58.2.0`） |
| 运行节点 / 话题收发 | ✅ | ✅ | ✅ |
| `ros2 launch` | ✅ | ✅ | ✅ |
| 与系统 ROS 互通 | — | ✅（`ROS_LOCALHOST_ONLY` 同值） | ✅（同左） |
| 与 B 互通 | ✅ | — | ✅（B listener 收 7 条） |
| GUI 包（rviz2 / desktop / turtlesim） | 已装（apt，未跑 GUI） | 通道里有 py312 构建，未装 | 通道里有 py314 构建，未装；GUI 未跑 |
| 再 `pixi add` 新 ROS 包 | 不适用 | 仍解析到同代 `ros-humble-*`（实测加 `ros-humble-turtlesim` → `1.4.3-np2py312h2ed9cc7_18`） | 仍解析到同代 `ros2-*`（实测加 `ros-humble-turtlesim` → 元包 + `ros2-turtlesim-1.4.3-np2py314h580689a_20`） |
| `-G Ninja` | 系统自带 | ❌ 环境没装 ninja（走 make） | ❌ 同左（官方教程建议显式 `pixi add ninja`） |

**两个问题的结论**：

1. **"不锁 Python 行不行？"——行，而且实测全链路可用**（编译、运行、launch、与系统/B 互通都通过）。决定"跟哪一代 RoboStack 包"的是这三个字：不声明 `python`，解析器会挑最新的 Python（当前 3.14），整条链就落到新代 `ros2-*` 上；写了 `python = "3.12.*"`，就落回 `ros-humble-*` 一代。两种都是"一致的单一世代"，`pixi add` 新包也不会混代。
2. **"`pixi install` 能覆盖系统差异吗？"——能，但保证来自 `pixi.lock`，不是来自版本声明**。`pixi.lock` 里连 `python` 和每个包的构建串都钉死（`platforms = ["linux-64"]` 范围内）。**但只有 linux-64 被声明**：换平台的人拿不到锁文件条目，需要重新解析（`pixi lock`/`pixi install` 会现算），这时"锁不锁 Python"才会真正影响他拿到的结果——不锁的话他会拿到**当时最新**的 Python 与 ROS 包（今天 = 3.14 + `ros2-*`），以后可能又变。

**本仓库保留 `python = "3.12.*"` 的理由**（不是"不能用最新的"，而是取舍）：① 与仓库其它任务（MuJoCo 等默认环境）共用一套 Python，环境可组合、习惯一致；② Python 3.12 的第三方 wheel（pip 生态）覆盖率仍明显高于 3.14，后续接工具（numpy / transforms3d / 相机 SDK 之类）更省事；③ 旧代 `ros-humble-*` 与系统 apt 的 Humble 同代同命名，对照实验与踩坑检索更直接。要改用新代，只需删掉这一行并重新 `pixi lock`（或显式写 `python = "3.14.*"` 把意图写明）。

复现（临时目录，不动仓库；A/B/C 三个环境分别见 §1 与本节开头）：

```bash
# C：不锁 Python 的最小清单
mkdir -p /tmp/ros2gen_test && cd /tmp/ros2gen_test
# 写 pixi.toml：channels = ["robostack-staging", "conda-forge"]，deps 里只有
# cxx-compiler / ros-humble-ros-base / ros-humble-demo-nodes-cpp / demo-nodes-py / colcon-common-extensions
pixi lock && pixi install && pixi list | grep -E '^(python|ros2-rclcpp)\s'   # → python 3.14.7 / ros2-rclcpp 16.0.19 np2py314…

# 用仓库的包在 C 里编译、运行（源码直接复制到临时工作空间）
cp -r <仓库>/@20261005_ros2/cpp/src/cpp_hello /tmp/gen_ws/cpp/src/
pixi run bash -c 'cd /tmp/gen_ws/cpp && colcon build --symlink-install'
pixi run bash -c '. /tmp/gen_ws/cpp/install/setup.sh; ros2 launch cpp_hello talk_listener.launch.py'
```

官方教程（[ROS 2 on Pixi](https://pixi.prefix.dev/latest/tutorials/ros2/)）与本节的差异：教程不锁 Python（`pixi add ros-humble-desktop ros-humble-turtlesim` 等，当前会落到 3.14 + `ros2-*`），并且给 C++ 建议 `pixi add ros-humble-ament-cmake-auto compilers pkg-config "cmake<4" ninja colcon-common-extensions`（其中 `cmake<4`、`ninja` 我们**未采纳**：实测 CMake 4.2/4.4 能编过我们的包、只报弃用警告；`ninja` 需要时再加，当前任务用 make 即可）。

## 7 未验证与下一步

- 未验证：rviz / GUI（需加 `ros-humble-desktop`，通道里存在）、跨机联调、`ros2_control`、与实机/串口的对接、docker / patchelf 部署路线。
- 未验证：与教程 §2.2/§2.3 对应的自写服务端/客户端（服务链路只用官方 demo 验证过）、参数 YAML 文件写法。
- 下一步（若继续）：把本任务的 Python 包也加一个 launch 示例；按需评估 `ros-humble-desktop` 与 GUI 渲染（MuJoCo 那套图形栈结论见 [`../../docs/pitfalls/environment.md`](../../docs/pitfalls/environment.md)）。

## 参考

- [Pixi for Robotics](https://pixi.prefix.dev/latest/robotics/)（官方 Quick Start、`activation scripts`、`rosdep` 说明）
- [ROS 2 on Pixi 教程](https://pixi.prefix.dev/latest/tutorials/ros2/)（建包、`colcon`、`cmake<4` / `ninja` / `setuptools<=58.2.0` 等建议；与本仓库取舍的差异见 §6 末段）
- [RoboStack](https://robostack.github.io/)（conda 通道里的 ROS 打包）
- 教程 `ros2基本概念.md`（本机只读材料，任务目录工作按其展开）
- 根 [`pixi.toml`](../../pixi.toml) 的 `[dependencies]` / `[activation]` 与仓库级 [`../../scripts/activate_ros2_workspaces.sh`](../../scripts/activate_ros2_workspaces.sh)
- 正式任务目录 [`../../@20261005_ros2/README.md`](../../@20261005_ros2/README.md)（同一个 `ros2` 环境，四足控制器/仿真/手柄三个节点）
