# 任务推进情况（做到哪、还差什么）

> 这是**本任务的推进记录**：各任务的完成情况、推进顺序与学习进度。 入口（做了什么、怎么跑、结果在哪）在 [`../README.md`](../README.md)； 约定来源：[`../../docs/conventions.md`](../../docs/conventions.md) §2（README 只做入口，不记进度）。

## 1 任务完成情况

- [x] 任务 1：认识 MuJoCo（作用、Python 接口、MJCF 结构）
- [x] 任务 2：URDF→MJCF、平地场景、零力矩静止趴卧、力矩执行器（结果见 [`task2.md`](task2.md)；C++ 侧 `cpp_task2/` 同判据）
- [x] 任务 3：参考 unitree_mujoco 优化代码结构与线程设计（研读笔记 → [`../../docs/learn/unitree-mujoco.md`](../../docs/learn/unitree-mujoco.md)，线程/通信细节与五种方案的每帧阻滞对比 → [`../../docs/learn/runtime-timing.md`](../../docs/learn/runtime-timing.md)；**Python 侧已落地**：[`../python/`](../python/) 用双缓冲把渲染与物理拆开。实测（[`../scripts/agent_scripts/physics_pacing.py`](../scripts/agent_scripts/physics_pacing.py)）：同等 20 ms/次渲染下，无窗口我们 499 步/秒（实时 0.998x，复测 0.997–0.999x）、上游式单锁写法 271 步/秒（0.542x），且物理结果与单线程裸循环逐位相同；开窗口时降到 0.93x（复测 0.929–0.935x；早期一次测得 0.863x，随窗口/viewer 开销浮动）——那是 Python 的 GIL 争用（渲染那一步在 Python 里），不是锁；C++ 侧用 MuJoCo 官方 `Simulate` 界面实测 **1.00x**，确认这个缺口只是 GIL。**起点默认是模型原姿态**（`--start default`，与 `simulate.py`/`example_attach.py` 一致；`--start rest` 可切成趴卧 keyframe，见 `python/simulator.py` 里的 `keyframe=` 参数）
- [x] 任务 4（选做）：用 C++ 重做——**结论是"不用重做"**：把 `cpp_task2` 接上 MuJoCo 官方 `Simulate` 界面（`--mode view`）实测就是 **1.00x 实时、画面流畅**（官方 `RenderLoop` 在 `Render()` 之前就放锁，渲染不在锁里），所以没有再手写一份 C++ 双缓冲（原来只留一份结论说明的 `cpp/` 目录已删，内容并进 [`cpp.md`](cpp.md) §3）
- [x] 额外 demo（非验收项）：平地站稳与可调倾斜地面（[`../cpp_stand/`](../cpp_stand/)、[`../cpp_slope/`](../cpp_slope/)，结果与踩坑见 [`stand.md`](stand.md)）
- [ ] 工程结构对齐（`include/` + `src/` + C++17，规则见 [`../../docs/learn/cpp-cmake.md`](../../docs/learn/cpp-cmake.md)）：本目录三个小程序（3 个头文件）**待做**；`@20260927_motor/cpp_part2/` 已完成，可作参照

## 2 推进顺序（任务 3/4）

① C++ 工具链可行性验证（已完成）→ ② 研读 `unitree_mujoco`、写 `../../docs/learn/unitree-mujoco.md`（已完成） → ③ Python 侧按新结构重构（**已完成**：`../python/`，`../scripts/` 里的旧脚本暂留作对照） → ④ C++ 侧验证（**已完成**：`cpp_task2 --mode view` 接官方 `Simulate` 界面，实测 1.00x 且流畅， 结论是不必再手写一份双缓冲）。

## 3 学习进度

目前仿真、控制、渲染窗口/录制视频的逻辑以及场景物体概念、MJCF/URDF 及其基本语法与使用已学会； 由 agent 编写的主要代码（`../cpp_task2/` `../cpp_stand/` `../cpp_slope/` `../python/` `../scripts/{simulate.py, simulate_record.py, visualization/}`）已理解；仓库 `docs/` 内讲解的 C++ 进阶语法 还在深化理解中。

## 4 提交与分支

- 直接在 `master` 上提交；不开长期分支（提交信息规范见 [`../../docs/conventions.md`](../../docs/conventions.md) §1）。
