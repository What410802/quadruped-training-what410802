# 目录与文件清单

> 这是本任务**每个目录/文件干什么**的完整清单（注释里带"为什么这么分"）。
> 入口（怎么跑、结果在哪）见 [`../README.md`](../README.md)；模型来源见 [`model.md`](model.md)、
> 站立 demo 见 [`stand.md`](stand.md)、录像工具见 [`recording.md`](recording.md)。

本目录只放模型、场景与代码；环境（Python / MuJoCo / C++ 工具链）由仓库根 `pixi.toml` 统一管理。
分工按仓库 [`../../docs/conventions.md`](../../docs/conventions.md) §7：**本任务成立的**（模型来源、过程与产出、
本任务的数字）留在本目录，**跳任务也成立的**（MuJoCo 知识点与坑、图形栈、环境与镜像）放仓库 `docs/`。

```text
@20260923_mujoco/
├── README.md                     # 入口：做了什么、怎么跑、结果在哪（本任务 README）
├── docs/                         # 本任务的文档（分工见上）
│   ├── model.md                  # 模型来源与 URDF→MJCF 转换（含本模型的两条坑）
│   ├── task2.md                  # 任务 2 结果、A/B 对照、录像产物
│   ├── stand.md                  # 站立/斜面 demo 的控制与实测
│   ├── recording.md              # 录像工具怎么接进自己的循环
│   └── replication.md            # 复现上游 unitree_mujoco 的记录
├── assets/						  # 相较于models/, scenes/，本目录下模型不在运行时运行，是静态模型（未处理初始状态是否穿模、是否是预期位姿）
│   ├── urdf/                     # 原始 URDF + meshes（真实 STL 只存这一份，34 MB）
│   ├── black_description/        # 网站导出（Floating Base ON / Torque）；meshes 为软链接
│   │   └── meshes -> ../urdf/meshes
│   └── black_description.bak/    # 旧版导出（默认 Position、无 freejoint），仅作对照，已 gitignore
├── models/
│   ├── black_description.xml     # 整理后的机器人模型（freejoint + 12 个力矩电机），唯一能跑的本体
│   └── meshes -> ../assets/urdf/meshes
├── scenes/
│   ├── flat_scene.xml            # 正常：include 上面的模型 + 地面 + 灯光 + 静止 keyframe（自己写 <compiler meshdir>）
│   ├── slope_scene.xml           # 斜面 demo 用：include flat_scene.xml + 一张棋盘格地面材质
│   └── flat_scene_raw.xml        # 对照：直接 include 原始导出，用于复现弹飞
├── output/                       # 任务结果（按语言分；文档在仓库根的 docs/）
│   ├── python/                   # Python 侧：rest_down.mp4、rest_preview_{iso,side}.png（两个 example 脚本的产物与 rest_down.mp4 重复或只是演示，未入库）
│   └── cpp/                      # C++ 侧：rest_down.mp4、stand.mp4、stand_up.mp4、slope_stand.mp4、slope_stand_up_1080p{60,120}fps.mp4（同名对应关系见 docs/task2.md，产出命令见 docs/task2.md 与 docs/stand.md）
├── examples/                     # 跟着教程敲的小例子（与任务 2 无关）
│   └── 01_falling_box/           # 入门例：立方体落地（scene.xml + simulate.py）
├── python/                       # 任务 3：借鉴 unitree_mujoco 重塑的仿真循环（双缓冲 + 两线程）
│   ├── main.py                   # 入口：开窗口/无窗口、实时/全速
│   ├── simulator.py              # 物理线程独占 mjData；渲染只读快照副本；锁只罩 memcpy
│   └── control.py                # 控制输入：目前零力矩，键盘控制以后加在这里
├── scripts/
│   ├── simulate.py               # 自己的仿真程序（最小 viewer 循环）
│   ├── simulate_record.py        # 同上，接上录像（无窗口）
│   ├── visualization/            # 录像与截图
│   │   ├── __init__.py           # 包入口：`from visualization import VideoRecorder`
│   │   ├── mujoco_video.py       # 核心库（离屏渲染 + ffmpeg 管道）
│   │   ├── render_preview.py     # 离屏渲染单张截图
│   │   └── examples/             # 示例代码（兼零力矩录像的命令行入口）
│   │       ├── example_attach.py         # 把录像接进已有循环 + 命令行录像
│   │       └── example_with_viewer.py    # 可选：一边开窗口看一边录（默认也写 output/python/）
│   ├── onetime_tools/            # 一次性工具：measure_and_fix_base_height.py（量脚底高度、抬基座）
│   └── agent_scripts/            # 诊断小工具（facts / A-B / rest_check / compare / urdf_to_mjcf / physics_pacing）
├── cpp_task2/                    # 任务 2 的 C++ 版：同一场景、同一判据，数字与 Python 侧对照
│   ├── CMakeLists.txt            # find_package(mujoco / glfw3)，工具链取自 pixi 环境
│   └── src/
│       ├── main.cpp              # 最小仿真 + 录像（对标 scripts/simulate_record.py）
│       ├── rest_check.cpp        # 零力矩静止判定（对标 scripts/agent_scripts/rest_check.py）
│       └── record.h              # 离屏渲染 → ffmpeg 的录像器（header-only）
├── cpp_stand/                    # 额外 demo：搜站姿 + 关节 PD 顶住（平地）
│   ├── CMakeLists.txt
│   └── src/                      # control.h（站姿控制器）、stand.cpp（= main.cpp 副本 + 控制钩子）
└── cpp_slope/                    # 额外 demo：可调倾斜地面（重力不动）
    ├── CMakeLists.txt
    └── src/                      # slope.cpp = stand.cpp 副本 + --pitch/--roll/自检
```
