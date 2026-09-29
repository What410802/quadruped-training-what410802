# MuJoCo 学习与 black 四足机器人仿真

本目录是第二次培训（MuJoCo 与机器人仿真基础）的任务工作区。环境（Python / MuJoCo / C++ 工具链）由**仓库根目录**的 `pixi.toml` 统一管理，本目录只放模型、场景与代码。仓库入口（任务记录、文档索引）：[`../README.md`](../README.md)。

## 文档

分工按 [`../docs/conventions.md`](../docs/conventions.md) §7：**本目录的文档只写本任务成立的事**（模型来源、本任务的过程与产出、本任务的数字），**通用知识与环境依据放仓库 `docs/`**，两边不重复、父文档只放飞指针。

| 文档 | 内容 |
|---|---|
| [`docs/model.md`](docs/model.md) | URDF 来源、URDF→MJCF 两条路线的差异、网站导出选项、本模型的两条坑（`meshdir` / 初始穿模）、`rest` keyframe 的来龙去脉 |
| [`docs/task2.md`](docs/task2.md) | 任务 2 的结果与 A/B 对照、录像与截图产物 |
| [`docs/stand.md`](docs/stand.md) | 额外 demo：平地站稳（`cpp_stand/`）与可调倾斜地面（`cpp_slope/`）的控制律、站姿搜索、实测数字与踩坑 |
| [`docs/recording.md`](docs/recording.md) | 录像工具怎么接进自己的仿真循环（Python 侧 `VideoRecorder`） |
| [`docs/replication.md`](docs/replication.md) | 复现上游 `unitree_mujoco` 的过程记录与预期效果 |
| [`docs/cpp.md`](docs/cpp.md) | 三个 C++ 工程（`cpp_task2` / `cpp_stand` / `cpp_slope`）：命令、对照表、录像细节、坑与实测 |
| [`docs/layout.md`](docs/layout.md) | 目录与文件清单（每个目录/文件干什么、为什么这么分） |

通用部分（MuJoCo 知识点与坑、图形栈、录像/渲染开销、编辑器提示、环境与镜像）在仓库 [`../docs/`](../docs/) 下。

## 运行方式

各任务做到哪一步见 `## 进度`；下面按任务分两段，都从仓库根目录执行（有 `pixi.toml` 的地方）。

### 任务 2（平地场景 + 零力矩静止趴卧）

```bash
cd ..                       # 到仓库根目录
pixi run python @20260923_mujoco/scripts/<目录>/<脚本>.py ...              # 旧入口：simulate / simulate_record / visualization / agent_scripts
pixi run python @20260923_mujoco/scripts/agent_scripts/rest_check.py       # 任务 2 的验收入口（静止判定）
pixi run cmake -S @20260923_mujoco/cpp_task2 -B @20260923_mujoco/cpp_task2/build -G Ninja -DCMAKE_PREFIX_PATH="$CONDA_PREFIX"
pixi run cmake --build @20260923_mujoco/cpp_task2/build
pixi run @20260923_mujoco/cpp_task2/build/rest_check                       # C++ 版：静止判定，同一场景、同一判据
pixi run @20260923_mujoco/cpp_task2/build/dog_sim                          # C++ 版：最小仿真（默认开官方 Simulate 窗口）
```

### 任务 4（新结构：Python 侧落在 `python/`；C++ 侧的结论是“不必复刻”，见 [`docs/cpp.md`](docs/cpp.md) §3）

开窗口要临时把图形后端换回 `glfw`（仓库默认是 `egl`，无窗口）：

```bash
pixi run env MUJOCO_GL=glfw python @20260923_mujoco/python/main.py          # 开窗口，零力矩跑（起点 = 模型原姿态）
pixi run python @20260923_mujoco/python/main.py --no-viewer --seconds 8     # 无窗口跑 8 仿真秒
pixi run python @20260923_mujoco/python/main.py --start rest                # 起点换成趴卧 keyframe（默认原姿态：直腿→自然塌下）
pixi run python @20260923_mujoco/scripts/agent_scripts/physics_pacing.py    # 检查：渲染不顶住物理
```

注意一个**开窗**才有的旧问题：“开窗 + `--seconds N` 自动退出”会在解释器收尾时**段错误**（退出码 139；`python -X faulthandler` 指到 `mujoco/viewer.py` 的 `_launch_internal`——viewer 自己的线程还在跑 GLFW，而主线程已经在收尾。旧代码同样崩，与本任务这次改动无关，属于 Python 侧 MuJoCo viewer 与 C++ 侧“不能调 `glfwTerminate`”一脉的收尾问题）。所以：**要数字用 `--no-viewer`**，要开窗就直接靠关窗退出（那条路径是干净的，退出码 0）。

**为什么非阻塞（双缓冲）是必要的**：`scripts/simulate.py` 是最朴素的单线程写法——一圈里 `mj_step` 之后紧跟 `viewer.sync()`，而 `viewer.sync()` 要等一个刷新周期（本机实测中位 **23.1 ms**）≫ `timestep`（0.002 s），一圈只推进 0.002 s 仿真，整个循环被显示刷新钉住。实测（本机 i5-1035G1、960×540、`MUJOCO_GL=glfw`）：

| 结构 | 开销 | 实时率 |
|---|---|---|
| 纯 `mj_step`（无窗口） | 0.0432 ms/步（C++ 侧 0.0404 ms） | — |
| `scripts/simulate.py`：`mj_step` + `viewer.sync()` 同线程、**每步都 sync** | 23.1 ms/圈，一圈才走 0.002 s | **0.089x** |
| `python/main.py`：物理线程 + 渲染线程、锁只罩快照 memcpy、deadline pacing | 渲染 20 ms/次也不顶住物理 | **0.998x**（复测 0.997–0.999x，与起点姿态无关；开窗口约 0.93x，复测 0.929–0.935x，GIL 限制） |
| `cpp_task2 --mode view`：物理线程 + 官方 `Simulate` 界面 | 官方 `RenderLoop` 在 `Render()` **之前**就放锁（源码注释 `// MutexLock (unblocks simulation thread)`） | **1.00x** |

也正因为如此，`scripts/simulate.py` 里那句被注释掉的 `[WARN] Simulation speed decreased.` 在本机是常态（每圈都会触发）；上游把 `SIMULATE_DT` 放大到 0.005 s 正是在迁就这件事（`config.py:13` 的注释明说）。**结论：要一边按墙钟实时看、一边推进物理，非阻塞（快照 + 双缓冲）不是可选优化，而是必要条件**——纯物理本身就够快（0.04 ms/步），问题全在「谁在等谁」。

## 目录结构

```text
@20260923_mujoco/
├── README.md      # 本文件：入口（做了什么、怎么跑、结果在哪）
├── docs/          # 本任务的文档（清单见 §文档 那张表）
├── assets/ + models/ + scenes/   # 原始 URDF 与 meshes、整理后的模型、三个场景（含 rest keyframe）
├── output/{python,cpp}/          # 产物：录像与截图（按语言分）
├── examples/      # 跟着教程敲的小例子（与任务 2 无关）
├── python/        # 任务 3：双缓冲 + 两线程的仿真循环（main / simulator / control）
├── scripts/       # simulate / simulate_record / visualization（录像库）/ onetime_tools / agent_scripts
├── cpp_task2/     # 任务 2 的 C++ 版（与 Python 侧同场景、同判据）
├── cpp_stand/     # 额外 demo：搜站姿 + 关节 PD 顶住（平地）
└── cpp_slope/     # 额外 demo：可调倾斜地面（重力不动）
```

**每个目录/文件干什么、为什么这么分**（含 `scripts/` 与 `cpp_*/src/` 的逐文件注释、软链接与 gitignore 说明）：
[`docs/layout.md`](docs/layout.md)。

## 环境与版本

| 项 | 版本 | 来源 |
|---|---|---|
| Python | 3.12.14 | conda-forge（经 pixi） |
| mujoco（Python 绑定） | 3.12.0 | conda-forge `mujoco-python` |
| libmujoco（C++ 库） | 3.12.0 | conda-forge `libmujoco` |
| mujoco-simulate（GUI） | 3.12.0 | conda-forge |
| numpy | 2.5.3 | conda-forge |

- **本任务不需要额外依赖，也不需要改环境**：直接用仓库根 `pixi.toml` 装出来的那一个环境（怎么搭出来、头文件是谁装的、镜像与工具链的取舍见 [`../docs/pitfalls/environment.md`](../docs/pitfalls/environment.md)）。
- conda-forge 的 `mujoco` **落后**于 PyPI（PyPI 已 3.14.0，conda-forge 最高 3.12.0）。为了 C++ 与 Python 用同一份库，本项目选 conda-forge。
- 本项目走 **CPU 仿真**：MuJoCo 本体就是 CPU 引擎（没有 GPU 版本），GPU 只影响 **渲染 / MJX / MJWarp** 三条支线，本项目用的是“渲染”这条。为什么本机用不了 MJX / MJWarp（显卡算力不够），见 [`../docs/pitfalls/environment.md`](../docs/pitfalls/environment.md) 的「图形后端 / GPU / 渲染性能」一节。

## 脚本

| 脚本 | 作用 |
|---|---|
| `scripts/simulate.py` | 自己的仿真程序：最小 `launch_passive` 循环（不录像） |
| `scripts/simulate_record.py` | 同上 + 录像（无窗口）；就是“只加一行 `rec.capture(data)` 就接上了”的样子 |
| `scripts/visualization/__init__.py` | 包入口：`from visualization import VideoRecorder`（把库的常用名字提到包一级） |
| `scripts/visualization/mujoco_video.py` | **录像工具库**：离屏取帧 → 管道给 ffmpeg(libx264)；`VideoRecorder` 可插进任意已有循环。用法见 [`docs/recording.md`](docs/recording.md) |
| `scripts/visualization/render_preview.py` | 离屏渲染单张截图（PNG 用标准库写出，不需要 pillow） |
| `scripts/visualization/examples/example_attach.py` | **接入示例**，同时是**零力矩录像的命令行入口**：照抄 `simulate.py` 的循环形状，只多 `rec.capture(data)` 一行（不开窗口）；`--scene/--start/--camera/--follow/--fps/--width/--height` 可调 |
| `scripts/visualization/examples/example_with_viewer.py` | 可选：一边开 `launch_passive` 看一边录（含 `viewer.sync()` 开销与实时节流的实测结论） |
| `scripts/onetime_tools/measure_and_fix_base_height.py` | 把网站导出整理成 `models/black_description.xml`（1 条手工补丁 + 断言 + 软链接自愈，可复现） |
| `scripts/agent_scripts/mujoco_facts.py` | 打印 geom type / friction / condim 的实测结论，供 [`../docs/learn/mujoco.md`](../docs/learn/mujoco.md) 引用 |
| `scripts/agent_scripts/ab_initial_state.py` | A/B 对照：原始导出 vs 补丁后模型的初始状态（穿模 / 弹飞量化） |
| `scripts/agent_scripts/rest_check.py` | 任务 2 验证：`--mode drop` 求趴卧姿态，`--mode keyframe` 验证零力矩静止 |
| `scripts/agent_scripts/compare_mjcf.py` | 打印多个模型的结构指标，用于对比转换结果 |
| `scripts/agent_scripts/urdf_to_mjcf.py` | 用 MuJoCo 自带能力把 URDF 转成 MJCF（`--method saveLastXML\|spec`） |
| `scripts/agent_scripts/physics_pacing.py` | 任务 3 检查：渲染开销不该影响物理步进（新循环 vs 上游式单锁写法） |
| `scripts/agent_scripts/geom_sameframe_check.py` | 复现「运行时改地面 `geom_quat` 被 `geom_sameframe` 吃掉」与「相机不会跟地面转」（供 [`../docs/learn/mujoco.md`](../docs/learn/mujoco.md) §6.7/§6.8 引用） |

## C++ 程序

三个独立工程，都用同一个 pixi 环境与同一份 MJCF，数字可直接与 Python 侧对照：

* **`cpp_task2/`**（任务 2 的 C++ 版）：`rest_check`（静止判定，与 `rest_check.py` 同一判据：末 1 s 漂移
  4.440e-10 m、`ncon=8`）与 `dog_sim`（最小仿真 / 离屏录像 / 官方 `Simulate` 窗口三种模式）；
* **`cpp_stand/` + `cpp_slope/`**（额外 demo）：关节 PD 顶住平地 / 可调倾斜地面（≤15° 能撑住，≥20° 滑走翻倒）；
* **任务 4 的结论**：不必再用手写双缓冲复刻 —— `cpp_task2 --mode view` 接官方 `Simulate` 界面实测
  **1.00x 实时**（官方 `RenderLoop` 在 `Render()` 之前就放锁），Python 侧那点缺口来自 GIL。

**命令与可执行文件对照表、录像的时间网格、官方界面的两个坑、全部实测数字**：见 [`docs/cpp.md`](docs/cpp.md)。

## 进度

- [x] 任务 1：认识 MuJoCo（作用、Python 接口、MJCF 结构）
- [x] 任务 2：URDF→MJCF、平地场景、零力矩静止趴卧、力矩执行器（结果见 [`docs/task2.md`](docs/task2.md)；C++ 侧 `cpp_task2/` 同判据）
- [x] 任务 3：参考 unitree_mujoco 优化代码结构与线程设计（研读笔记 → [`../docs/learn/unitree-mujoco.md`](../docs/learn/unitree-mujoco.md)，线程/通信细节与五种方案的每帧阻滞对比 → [`../docs/learn/runtime-timing.md`](../docs/learn/runtime-timing.md)；**Python 侧已落地**：[`python/`](python/) 用双缓冲把渲染与物理拆开。实测（`scripts/agent_scripts/physics_pacing.py`）：同等 20 ms/次渲染下，无窗口我们 499 步/秒（实时 0.998x，复测 0.997–0.999x）、上游式单锁写法 271 步/秒（0.542x），且物理结果与单线程裸循环逐位相同；开窗口时降到 0.93x（复测 0.929–0.935x；早期一次测得 0.863x，随窗口/viewer 开销浮动）——那是 Python 的 GIL 争用（渲染那一步在 Python 里），不是锁；C++ 侧用 MuJoCo 官方 `Simulate` 界面实测 **1.00x**，确认这个缺口只是 GIL。**起点默认是模型原姿态**（`--start default`，与 `simulate.py`/`example_attach.py` 一致；`--start rest` 可切成趴卧 keyframe，见 `python/simulator.py` 里的 `keyframe=` 参数）
- [x] 任务 4（选做）：用 C++ 重做——**结论是“不用重做”**：把 `cpp_task2` 接上 MuJoCo 官方 `Simulate` 界面（`--mode view`）实测就是 **1.00x 实时、画面流畅**（官方 `RenderLoop` 在 `Render()` 之前就放锁，渲染不在锁里），所以没有再手写一份 C++ 双缓冲（原来只留一份结论说明的 `cpp/` 目录已删，内容并进 [`docs/cpp.md`](docs/cpp.md) §3）
- [x] 额外 demo（非验收项）：平地站稳与可调倾斜地面（[`cpp_stand/`](cpp_stand/)、[`cpp_slope/`](cpp_slope/)，结果与踩坑见 [`docs/stand.md`](docs/stand.md)）

任务 3/4 的推进顺序：① C++ 工具链可行性验证（已完成）→ ② 研读 `unitree_mujoco`、写 `docs/learn/unitree-mujoco.md`（已完成）→ ③ Python 侧按新结构重构（**已完成**：`python/`，`scripts/` 里的旧脚本暂留作对照）→ ④ C++ 侧验证（**已完成**：`cpp_task2 --mode view` 接官方 `Simulate` 界面，实测 1.00x 且流畅，结论是不必再手写一份双缓冲）。

目前仿真、控制、渲染窗口/录制视频的逻辑以及场景物体概念、MJCF/URDF及其基本语法与使用已学会，由agent编写的主要代码（`cpp_task2/` `cpp_stand/` `cpp_slope/` `python/` `scripts/{simulate.py, simulate_record.py, visualization/}`）已理解，`docs/` 内讲解的C++进阶语法还在深化理解中。
