# 任务推进情况（做到哪、还差什么）

> 本任务的阶段状态、下一步、阻滞项与提交情况。入口（怎么跑、文件地图）在 [`../README.md`](../README.md)，结论与实测数字在 [`pixi-ros2.md`](pixi-ros2.md)。约定来源：[`../../docs/conventions.md`](../../docs/conventions.md) §2、§7（README 只做入口，进度放这里）。

## 1 阶段状态

| 阶段 | 状态 |
|---|---|
| 环境：Pixi `ros2` 环境（RoboStack + conda-forge colcon）跑通 | ✅ 完成（2026-10-05）；版本对照见 [`pixi-ros2.md`](pixi-ros2.md) §1 |
| 教程 §1：工作空间、包、节点（`py_hello` / `cpp_hello`：`hello_node`） | ✅ 完成（Python 3.12 + conda gcc，`colcon build --symlink-install` 通过） |
| 教程 §2：话题（`talker` / `listener`）、参数（`message` / `period_ms`） | ✅ 完成；`ros2 topic hz` 实测 3.333 Hz（`period_ms:=300`） |
| 教程 §2.2 服务、§2.3 参数在线修改 | ✅ 用官方 demo 验证过链路（`add_two_ints` 返回 42；`param get/set`）；自写服务端/客户端未做 |
| 教程 §3：launch（`talk_listener.launch.py` + `CMakeLists.txt` 注册 + 参数内联） | ✅ 完成（2026-10-05 补齐；`ros2 launch` 输出周期 0.5 s，与教程预期一致） |
| 自动 source 工作空间（`[activation]` + 仓库根脚本） | ✅ 完成；编译后 `pixi run ros2 run …` 直接可用（脚本 2026-10-06 改为**自动发现**所有工作空间，根 `pixi.toml` 不再写任务级路径） |
| 可行性实验：Pixi 装 vs 系统装的等效性（行为 / 线级互通 / 二进制） | ✅ 完成（2026-10-05）：行为一致、DDS 线级双向互通、二进制各自绑定安装；见 [`pixi-ros2.md`](pixi-ros2.md) §2–§4 |
| `colcon` 声明对齐官方（`colcon-common-extensions` 元包） | ✅ 完成（2026-10-05）：手写 14 项 → 元包（20 组件，`version-check` 20/20）；`colcon-mixin` 不在元包内，已从依赖移除并记录 |
| 三种装法对照（系统 apt / Pixi+3.12 / Pixi 不锁 Python=3.14） | ✅ 完成（2026-10-05）：同源码三处编译运行 + 三向互通全通过；结论与数据在 [`pixi-ros2.md`](pixi-ros2.md) §6（结论：不锁可行，本仓库仍保留 3.12 锁定，理由是跨任务一致与 pip 生态） |
| `.gitignore` 排除 colcon 产物（`install/`、`log/`） | ✅ 完成（2026-10-05；`build/` 原本已覆盖） |

## 2 阻滞项

| 阻滞项 | 影响 | 现状 |
|---|---|---|
| 暂无 | — | — |

## 3 下一步（可选）

- 按需加 `ros-humble-desktop`（rviz / GUI）并验证渲染；跨机联调（`ROS_LOCALHOST_ONLY=0`）与部署方式（同路径环境 / `patchelf` / 容器）。
- 教程 §2.2 的自写服务端/客户端（"握手"例子）、参数 YAML 文件写法，可作为后续练习补进 `cpp_hello`。
- 未登记到仓库根 `README.md` 的任务记录（本次按要求暂不登记）。
