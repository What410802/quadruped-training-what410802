# C++ 场景视窗（scene_viewer）

## 来源

`src/viewer.h` 逐字复用本仓库 `@20260927_motor/cpp/src/viewer.h`（自写代码：GLFW 窗口 + `mjv`/`mjr` 渲染 + 键盘/鼠标相机 + HUD），这样新任务不用重新写窗口；`src/main.cpp` 与 `CMakeLists.txt` 是本任务新加的。窗口沿用原文件的单把锁（渲染与物理同线程）；按 `@20260923_mujoco` 的实测结论，C++ 侧不存在 Python GIL 问题，先不换“锁只罩拷贝”的双缓冲版本，等接入策略、拷贝/推理开销变大时再换。

## 构建与运行

从仓库根目录执行（`build/` 已被 `.gitignore` 覆盖）：

```bash
pixi run cmake -S @20261019_locomotion/cpp -B @20261019_locomotion/cpp/build
pixi run cmake --build @20261019_locomotion/cpp/build -j
pixi run @20261019_locomotion/cpp/build/scene_viewer --scene @20261005_ros2/scenes/flat_scene.xml
```

常用参数：`--scene <MJCF>`（必填）、`--width/--height`（默认 1280×720）、`--paused`（打开时暂停）。需要显示服务（`DISPLAY`）；纯数字场景检查用 Python 或 `--paused` 静看。

按键：`Space` 暂停/继续、`R` 重置、`Esc`/`Q` 退出；鼠标左键旋转、右键平移（Shift + 右键竖直）、滚轮缩放。HUD 只支持 ASCII。

## 下一步

1. 接策略推理：用 pixi 环境的 CPU `libtorch` 加载 TorchScript（观测/动作拼法与 `@20261007_assignment/scripts/agent_scripts/policy_reference.py` 同一口径，配置读 rl_sar 的 `base.yaml`/`himloco/config.yaml`），实现“加载导出策略 → 仿真闭环 → 窗口看运行”。这一步放在 S1 产出第一版策略之后。
2. 若训练侧改用 mjlab 的任务场景/地形，视窗只负责加载 MJCF，不依赖训练框架。
3. 渲染锁升级（锁只罩拷贝）留到策略推理接入后，按实测帧时间决定。
