# `quadruped_control` 迁移到 Pixi 环境（2026-10-22 实测）

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

## 剩余缺口：GUI 单进程 app

`apps/mujoco_sim` 需要 MuJoCo 官方 `simulate/` 源码（`simulate.cc`、`glfw_adapter.cc`、`glfw_dispatch.cc`、`platform_ui_adapter.cc`），Pixi 只安装运行时/CMake 包，没有这些源码。

两条路：

1. **vendor MuJoCo 3.12 的 4 个 Simulate 源码文件**（BSD-3-Clause），接到 `apps/mujoco_sim`；改动小，但要保留来源/许可说明。
2. **不用官方 Simulate**：基于现有 `@20261019_locomotion/cpp/scene_viewer`（GLFW + MuJoCo + mjv）做一个最小 GUI runner，接 MotionRuntime/手柄；改动更大但 UI 可控。

P0 建议先做 1；P1 若需要自定义 overlay/录制再考虑 2。

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
