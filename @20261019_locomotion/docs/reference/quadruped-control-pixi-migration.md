# `quadruped_control` 迁移到 Pixi 环境（2026-10-22 实测）

## 仓库位置

- 上游/团队仓库：`N-W-wolf/quadruped_control`（fork 自 `coverMoon/quadruped_control`）；
- 个人 fork：`What410802/quadruped_control`；本地 clone 的 `origin` 指个人 fork，`upstream` 指团队仓库；
- P0 迁移提交 `f2b37dc` 已推送到个人 fork。

## 结论

**可以迁移，且不需要第二套环境。** 当前 Pixi 环境已经有：

- MuJoCo **3.12.0**（C++/Python；`libmujoco` + `mujoco::mujoco` CMake target）；
- LibTorch **2.12.0 CPU**（`TorchConfig.cmake`）；
- ROS 2 Humble、`yaml-cpp`、`tbb-devel`、GLFW、OpenGL、Eigen 等；
- 编译器/CMake；远程机关机也能本地构建。

实测在本地 clone `prep.d/quadruped_control_local` 上只改 CMake 就能编译：

- `quadruped_core`；
- `quadruped_mujoco`（MuJoCo 3.12 后端）；
- `quadruped_motion`（MotionRuntime/RL）；
- `quadruped_torch_policy`（LibTorch 2.12）；
- `quadruped_config`、`quadruped_ipc`、`quadruped_replay_backend`。

**源码本身没有改**；MuJoCo 3.9→3.12、LibTorch 2.0→2.12 在已编译模块上没有 API/ABI 阻塞。

## 改动清单（约 2 个 CMake 文件）

1. 根 `CMakeLists.txt`：
   - `find_package(mujoco 3.9.0 EXACT REQUIRED MODULE)` → `find_package(mujoco CONFIG REQUIRED)`；
   - 删除“必须来自 `.deps/libtorch-2.0.1-cpu`”的硬校验，改为 `find_package(Torch CONFIG REQUIRED)`；
   - 增加 `option(QUADRUPED_BUILD_APPS ...)`，允许在缺少 MuJoCo Simulate 源码时只构建核心库（P0 先跑 headless）。
2. `cmake/Findmujoco.cmake`：不再作为主路径（Pixi 提供 config target）；如保留，需改成查找 `CONDA_PREFIX`/`CMAKE_PREFIX_PATH`。
3. `scripts/build.sh`：绕过 `.deps` 存在性检查，直接用 Pixi 的 `cmake` 配置；或新增 `--pixi` profile。
4. `configs/policies/black/flat_ft.yaml`：把 45 维单帧 `flat-ft-2500` 接入控制仓库（已有工作副本）；`policy_switch.yaml` 暂时 `[flat_ft, obstacle]`。

## GUI 也已在本机跑起来

MuJoCo 3.12 的 `simulate/` 源码在只读 `Replicate.d/mujoco-3.12.0/simulate/`；把它复制到本地 clone 的 `third_party/mujoco_simulate/` 后，`apps/mujoco_sim` **已构建并通过启动测试**：

- `quadruped_mujoco_sim --help` 正常；
- 在 Part 1 工作场景上启动成功；
- 用伪终端发送 `0`（GetUp）→ `1`（RL）→ `w`（vx=0.1）可进入 `Running/rl_locomotion` 并接受命令；
- 加载 `flat_ft` 45 维策略的进程没有报错。

构建时的额外注意（Pixi + 本机系统库）：

- 用 Pixi 的 `x86_64-conda-linux-gnu-c++` 编译，避免系统 g++ 11 链接 Pixi 新版 libstdc++ 失败；
- PNG 用 Pixi 的 `libpng.so`，zlib 用系统 `/usr/lib/x86_64-linux-gnu/libz.so`（Pixi 只有 `libz.so.1` 符号链接）；
- 运行时需要 `LD_PRELOAD=<pixi>/lib/libstdc++.so.6` 和 `LD_LIBRARY_PATH=<pixi>/lib`，否则系统 libstdc++ 缺 `GLIBCXX_3.4.32`。

GUI 现在可用。已在本地副本加 8 个占位 policy（`flat_ft`/`loose_ft`/`limit_bar_ft`/`bridge_ft`/`stairs_ft`/`high_wall_ft`/`slope_ft`/`slalom_ft`，都暂时指向同一 45 维模型），并实测 `0` GetUp → `1` Running → `2/3` policy switch 全部 Accepted/Completed；这还不是“具名键直接选状态”，只是循环切换的 P0 保底壳。

## 复现命令（本地 Pixi）

```bash
cd prep.d/quadruped_control_local
cmake -S . -B /tmp/qc_pixi_build \
  -DQUADRUPED_ENABLE_MUJOCO=ON \
  -DQUADRUPED_ENABLE_TORCH=ON \
  -DQUADRUPED_BUILD_APPS=OFF \
  -DBUILD_TESTING=OFF \
  -DCMAKE_BUILD_TYPE=Release
cmake --build /tmp/qc_pixi_build -j4
```

`cmake`/`c++`/依赖均来自 Pixi 环境；不需要 `scripts/setup/*.sh` 下载 `.deps`。

## 风险

- 没有编译 `apps/mujoco_sim`，GUI/手柄端到端尚未验证；需要 vendor Simulate 源码或自写 viewer。
- 控制仓库的 45 维 `flat_ft`/270 维 `obstacle` 混合 policy_switch、单帧 history 切换、默认姿态过渡需要实际跑一帧验证。
- LibTorch 2.12 与训练侧 Python Torch 2.12 一致；TorchScript 导出/加载要实测。
- ROS 2 Humble 的 Pixi 包已装，但三进程/共享内存/手柄设备仍需在目标机验证。
