# 推进情况

> 本文记“做到哪、待决什么、下一步”，会随推进改；入口与用法在 [`../README.md`](../README.md)。约定来源：[`../../docs/conventions.md`](../../docs/conventions.md) §2.6。

## 阶段状态

| 阶段 | 状态 | 证据 |
|---|---|---|
| 任务范围确认 | ✅ 2026-10-19 | 先平地/粗糙 locomotion，再台阶与梅花桩；只做手动模式；仿真为主、考虑 sim2sim |
| 材料盘点（地形/规则/许可） | ✅ 2026-10-19 | [`materials.md`](materials.md)：只读材料、2026/2027 规则尺寸、mjlab 地形映射 |
| 本地环境 | ✅ 2026-10-19 | 根 `pixi.toml` 单环境，MuJoCo 3.12 / glfw / cmake / CPU libtorch 已具备；本任务无新增依赖 |
| 远程训练机 + 原生 uv 环境 | ✅ 2026-10-20 | `bis-ms7e56` 驱动 595.99.02 / CUDA 13.4 / uv 0.13.3；`uv sync --locked` 成功；`black-flat` 512 envs × 11 iteration 通过（0.67 s/iter）；512–8192 envs 基准完成 |
| 远程训练机配置备份（GitHub） | ⏳ 文件已写好，待提交/推送 | 已 fork `What410802/nwwolf_mjlab_training_release`；配置过程写在 fork 的 `REMOTE_SETUP.md`（工作区，待 commit/push） |
| EGL 渲染（录屏/截图） | ✅ 2026-10-20 | 原生 `MUJOCO_GL=egl` 可用：320×240 约 0.063 ms/帧、640×480 约 0.159 ms/帧；osmesa 仅作兜底 |
| C++ 场景视窗 | ✅ 2026-10-19 | 复用 `@20260927_motor` 的 viewer，最小 `scene_viewer` 能加载 MJCF；策略推理待后续 |
| 基础模型（平地/粗糙/碎石，站/走/小跑/平滑切换） | ⬜ 未开始 | 方案见 [`training-plan.md`](training-plan.md) |
| 台阶与梅花桩 | ⬜ 未开始 | 方案见 [`training-plan.md`](training-plan.md)；地形尺寸见 [`materials.md`](materials.md) |
| 域随机化与鲁棒性实验 | ⬜ 未开始 | 方案见 [`training-plan.md`](training-plan.md) |

## 已定决策

- 仓库划分（2026-10-19）：不 fork mjlab 本体，把它当锁定版本依赖；训练代码放**训练仓库**（fork `nwwolf_mjlab_training_release`），运行仓库（本仓库）只做运行时/评测，训练与运行通过 `policy.pt` + 契约 + 元数据交接。详见 [`repos.md`](repos.md)。
- 训练底座（2026-10-19）：用队内 mjlab 训练仓库（`black-flat` / `black-rough`，PPO；HIM 变体作对照），不在本任务里重写 PPO/地形生成/导出。
- 远程训练环境（2026-10-20）：**原生 uv + 训练仓库 `uv.lock`**；Docker 方案已验证但**移除**，不维护镜像。
- 本地环境：仓库根 `pixi.toml` 单环境；训练依赖不进入本地环境。
- 渲染/录屏（2026-10-20）：`MUJOCO_GL=egl`；训练本身不走 MuJoCo GL（相机/深度传感器走 mjlab 的 `mujoco_warp` GPU RenderContext），osmesa 仅兜底。
- 手动模式（手柄）：速度指令 + 部署状态机，不引入“专家模型”作为基本方案；理由与状态机分工见 [`training-plan.md`](training-plan.md) §4。
- 相机/深度：先不进入 actor；先用地形高度扫描作 privileged critic/teacher 对照，后续按 teacher-student 引入视觉。
- PPO：先跑基线，再按论文对比 HIM（history 估计器）、privileged critic、domain randomization；MoE/AMP 作为后选。
- C++ 视窗：复用 `@20260927_motor/cpp/src/viewer.h`；先单锁渲染，“锁只罩拷贝”的双缓冲留到需要更多拷贝占用时再换（与 `@20260923_mujoco` 的结论一致）。
- 权重管理：有价值的 checkpoint 放训练仓库 `weights/<stage>` 分支或 GitHub Release，运行仓库只放验收用 `policy.pt` + 元数据；当前尚无权重。

## 历史问题（已解决）

- 2026-10-20 更新远程机 NVIDIA 驱动后，内核模块 595.71.05 与用户态 595.99.02 不匹配，`nvidia-smi` 报 `Failed to initialize NVML: Driver/library version mismatch`，Docker GPU 容器也因缺 `/run/nvidia-persistenced/socket` 起不来；重启远程机后内核/用户态统一到 595.99.02，GPU 恢复。处理方式已写进训练仓库 `REMOTE_SETUP.md`。
- 2026-10-19 曾用 Docker + CUDA 13.2 镜像跑通训练与基准；2026-10-20 原生 uv 验证通过（512 envs 0.67 s vs Docker 0.66 s/iteration）后删除 Docker 方案。Docker 期间的两个容器专属坑（DNS、triton 段错误）不再适用；原生 uv 下 triton 导入正常。

## 待确认 / 待决

1. 任务书/验收细则：平地/台阶/梅花桩各自的评价口径、是否只用手动、目标硬件的最终形态（2026 手动列计分？还是练习性质）。
2. 地形版本：台阶按 2026 T 字形台阶，还是 2027 沟壑组合里的 120 mm 台阶；梅花桩按 2027 规则尺寸（200×200×200 方块）是否就是目标。
3. 相机是否装在实机上、型号/帧率/安装位置；这决定 teacher-student 的数据与部署延迟预算。
4. 手柄映射与安全边界（速度上限、死区、模式切换键）沿用 `@20261007_assignment` 的 rl_sar 配置还是重新定。
5. 训练仓库配置文档 `REMOTE_SETUP.md` 与 `mjlab==1.6.0` 精确锁的提交/推送：按仓库约定，AI 不代为 commit，需要用户执行或明确授权。

## 下一步（按顺序）

1. 把地形生成接到训练仓库：先 flat/rough/碎石，再台阶、梅花桩（custom SubTerrainCfg），并用 mjlab 的地形可视化确认尺寸与规则一致。
2. 建立评测协议与脚本：本地 MuJoCo + C++ 视窗跑导出策略；记录逐地形通过率、速度跟踪、摔倒、能耗/力矩指标（RoboGauge 指标口径）。
3. 训练第一版基础模型（站/走/小跑/平滑切换），做 HIM 与 privileged critic 的对照实验；按 4096–8192 envs 起步，先跑 1–2k iteration 看收敛再决定是否加长。
4. 第二阶段台阶与梅花桩：课程/奖励/终止条件实验，记录每次实验配置与曲线。
5. 域随机化与鲁棒性实验；sim2sim 复查；最后再考虑相机（teacher-student）。

## 证据与命令

- 远程 GPU 核验（2026-10-20，主机 `bis-ms7e56`）：`nvidia-smi --query-gpu=name,driver_version --format=csv` → `NVIDIA GeForce RTX 5060 Ti, 595.99.02, 16311 MiB`；内核模块 `/proc/driver/nvidia/version` 同 595.99.02；`nvidia-smi` 正常。
- 原生 uv（2026-10-20）：`~/.local/bin/uv 0.13.3`；`UV_CACHE_DIR=~/rc_work/.uv-cache uv sync --locked` → 137 包、约 5 s（缓存已存在）；`torch 2.14.0+cu130` CUDA 可用；Warp 识别 `cuda:0`。
- 训练冒烟（2026-10-20）：`MUJOCO_GL=egl .venv/bin/train black-flat --env.scene.num-envs 512 --agent.max-iterations 11 --agent.logger tensorboard` → 退出 0，`Iteration time 0.67 s`；benchmark 1024/2048/4096/8192 envs → 0.82/1.05/1.57/2.62 s、峰值 1774/2444/3891/6828 MiB。
- EGL（2026-10-20）：原生 `MUJOCO_GL=egl` 简单场景 320×240 0.063 ms/帧、640×480 0.159 ms/帧；`import mujoco` 不需要 `DISPLAY`；640×480×60 帧的 PNG（26 KB）与 MP4（11 KB）写出成功。
- 只读材料指纹：`terrain.zip` sha256 `1419607a4458b889602a1d6b692ed97af72179c28f95ff141f0e5738f1b98fb0`；`scene_terrain.xml` sha256 `9da48640d354ba8b360fcf57e4e26d66f19a58bca19bc4d57bee4aaa1085ae29`。
- 本地 `pixi run python -c "import mujoco; print(mujoco.__version__)"` → `3.12.0`；`pixi run cmake --version` → `4.2.3`。
- C++ 视窗：`pixi run …scene_viewer --scene @20261005_ros2/scenes/flat_scene.xml` 输出 `Loaded …: nq=19 nv=18 nu=12 ngeom=50` 并保持窗口运行到超时（6 s）退出码 124。
- GitHub fork（2026-10-20）：`gh repo view What410802/nwwolf_mjlab_training_release` → `isFork=true`、`viewerPermission=ADMIN`；远程 clone 的 `origin` 已指向 fork、`upstream` 指向 N-W-wolf；`REMOTE_SETUP.md` 已在工作区（未 commit）。
