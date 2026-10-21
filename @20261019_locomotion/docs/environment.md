# 环境：本地 pixi、远程 GPU、EGL/TensorBoard、C++ 视窗

## 1. 本地环境（沿用仓库根 `pixi.toml` 单环境）

本地开发与查看都从仓库根执行 `pixi run …`，不为本任务另开环境（[`../../docs/conventions.md`](../../docs/conventions.md) §4.1）。现有环境已经够用，**本任务目前没有新增本地依赖**：

| 能力 | 现成依赖 | 用途 |
|---|---|---|
| MuJoCo 仿真/加载 MJCF | `mujoco 3.12.*`（C++ 与 Python 同版本） | 场景、地形、sim2sim 检查 |
| C++ 视窗 | `glfw`、`cxx-compiler`、`cmake`、`ninja` | 本任务 `cpp/scene_viewer` |
| 策略推理（后续 C++ 视窗接策略） | `libtorch`（CPU generic）、`tbb-devel` | TorchScript 推理，路径与 `@20261007_assignment` 相同 |
| 手柄/输入 | `evdev` | 后续手动模式联调 |

本机 GPU 是 MX350（2 GB，compute 6.1），不满足 mjlab 的 Turing 及以上要求，**训练不在本机做**；本机只做场景查看、策略回放与文档工作。若后续需要画曲线，再按需加 `matplotlib`（现在环境里没有）。

## 2. 远程算力机

| 项 | 值（2026-10-20 实测） |
|---|---|
| SSH 主机 | `bis-ms7e56.tail4413b4.ts.net`（Tailscale），用户 `bis` |
| GPU | NVIDIA GeForce RTX 5060 Ti，16311 MiB |
| 驱动 | 内核模块与用户态均为 `595.99.02`（Open Kernel Module） |
| CUDA | 系统 toolkit 13.4（`/usr/local/cuda`，nvcc 13.4.92）；PyTorch 用 PyPI cu13 依赖 |
| uv | `0.13.3`，`~/.local/bin/uv`（训练环境用） |
| pixi | 主机级 `~/.pixi/bin/pixi`（运行时工具用，不参与训练环境） |
| CPU / 内存 / 磁盘 | 12 核 / 30 GB / 约 739 GB 可用 |
| 网络 | 可直连 PyPI 与 GitHub |
| Docker | 29.9.1 仍安装但不用于训练（原生 uv 已跑通，见 §3） |

驱动升级后的坑：内核模块与用户态版本可能不一致，`nvidia-smi` 报 `Failed to initialize NVML: Driver/library version mismatch`，此时任何 GPU 任务（Docker 或原生）都会失败；**重启机器**（或由 root 卸载/重载 nvidia 模块）后恢复。2026-10-20 更新驱动后就遇到一次，重启后内核/用户态统一为 595.99.02。

## 3. 远程训练环境：原生 uv（默认）

**决策（2026-10-20）**：原生 uv 已验证通过，Docker 方案移除。原生 uv 与 Docker 的 512 envs 冒烟数字基本一致（0.67 vs 0.66 s/iteration），且少一层镜像维护；训练仓库用它自己的 `uv.lock` 复现（`mjlab 1.6.0`、Python 3.12.15、torch 2.14.0+cu130、warp-lang 1.17.0）。本仓库本地仍保持 pixi 单环境；训练依赖不进入本地环境。

首次准备（远程机；训练机配置的完整备份见训练仓库根目录 `REMOTE_SETUP.md`）：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
export RC_WORK="$HOME/rc_work"
mkdir -p "$RC_WORK"
git clone https://github.com/What410802/nwwolf_mjlab_training_release.git "$RC_WORK/nwwolf_mjlab_training_release"
cd "$RC_WORK/nwwolf_mjlab_training_release"
git remote add upstream https://github.com/N-W-wolf/nwwolf_mjlab_training_release.git
export UV_CACHE_DIR="$RC_WORK/.uv-cache"
uv sync --locked
```

验证与训练（`MUJOCO_GL=egl` 是渲染/录屏所需，训练本身也可用）：

```bash
.venv/bin/python -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available())"
.venv/bin/python -c "import warp as wp; wp.init(); print(wp.__version__, wp.get_device())"
MUJOCO_GL=egl .venv/bin/train black-flat --env.scene.num-envs 512 --agent.max-iterations 11 --agent.logger tensorboard
```

实测（2026-10-20，原生 uv）：`uv sync --locked` 缓存已存在时约 5 s、137 个包；`torch 2.14.0+cu130` CUDA 可用；Warp 识别 `cuda:0`；`black-flat` 512 envs × 11 iteration 通过，`Iteration time 0.67 s`。

性能基准（`black-flat`，20 iteration 后取 iteration time，峰值显存由 `nvidia-smi` 采样）：

| envs | iteration time | 峰值显存 | 约合吞吐 |
|---|---|---|---|
| 512 | 0.67 s | — | — |
| 1024 | 0.82 s | 1774 MiB | ≈80k env steps/s |
| 2048 | 1.05 s | 2444 MiB | ≈125k env steps/s |
| 4096 | 1.57 s | 3891 MiB | ≈167k env steps/s |
| 8192 | 2.62 s | 6828 MiB | ≈200k env steps/s |

16 GB 显存余量充足；S1 从 4096 envs 起步，按收敛曲线决定是否上 8192，训练仓库默认 10k iteration 的上限不必跑满。

## 4. 渲染与录屏：用 EGL

- `MUJOCO_GL=egl` 在远程机原生环境可用（不需要 `DISPLAY`），实测简单 320×240 场景约 **0.063 ms/帧**、640×480 约 **0.159 ms/帧**；录屏/截图、`play` 的离屏渲染都应该用它。
- 对比 `MUJOCO_GL=osmesa`（纯 CPU 软件渲染）：简单场景 320×240 约 0.59 ms/帧，真实场景/分辨率更慢，且吃 CPU；只作为 EGL 不可用时的兼容兜底。
- EGL 退出时可能打印 `Exception ignored in … EGLError` 的清理告警，不影响渲染与训练，可忽略。
- 录屏/截图已实测：远程机原生 uv 环境 `MUJOCO_GL=egl` 渲染 640×480×60 帧并写出 PNG（26 KB）与 MP4（11 KB，imageio + imageio-ffmpeg），产物在 `~/rc_work/egl_screenshot.png`、`~/rc_work/egl_video.mp4`；C++ 视窗需要显示服务，远程录屏走 Python 侧 `mujoco.Renderer`。
- 训练本身（无相机传感器时）不逐帧走 MuJoCo GL；mjlab 1.6 的相机/深度传感器走 `mujoco_warp` 的 GPU RenderContext，不经过 EGL/OSMesa。因此之前 0.66–2.63 s/iteration 的训练基准与 GL 后端无关；以后接深度相机时，成本要按 mjlab GPU 渲染路径单独基准。
- 本地（有显示）也可用 `pixi run env MUJOCO_GL=glfw …`；注意命令行前缀会覆盖 `pixi.toml` 里的 `MUJOCO_GL=egl`。

## 5. TensorBoard 与替代

| 需求 | 选择 | 说明 |
|---|---|---|
| 标量曲线（reward / episode 指标 / 课程） | **TensorBoard**（训练仓库已内置 `--agent.logger tensorboard`） | 零额外开发，写入 `logs/rsl_rl/…`；**`tensorboard` 不在远程 PATH 上，要用训练仓库 venv 的 `.venv/bin/tensorboard`**；远程 `ssh -L 6006:localhost:6006` 看 |
| 训练过程视频/三维回放 | mjlab 自带的 `play`/`viser` + 本任务 C++ 视窗、本地 MuJoCo 回放 | 看 rollout 比看曲线更直接；`play` 的离屏渲染用 EGL |
| 多模态（曲线 + 3D + 图像）实验记录 | 可选 **Rerun**（后加） | 引入成本高，等有相机/视觉数据再考虑 |
| 团队/云端对比 | 可选 W&B（支持离线 `WANDB_MODE=offline`） | 需要账号与网络；不是必须 |
| 本地轻量对比 | CSV + 本任务脚本汇总 | 最终评审用表放任务 `docs/`，不依赖某个服务 |

结论：**先 TensorBoard**；需要可视化 rollout 或相机数据时再评估 Rerun/W&B，不提前引入。

## 6. C++ 场景视窗

- 源码：复用 `@20260927_motor/cpp/src/viewer.h`（自写 GLFW + mjv/mjr；鼠标左键旋转、右键平移、滚轮缩放、Esc/Q 退出；HUD 只支持 ASCII）。
- 本任务先加一个 `scene_viewer`（`--scene <MJCF>`）：加载模型、跑空转物理、显示场景，用于检查地形/MJCF 与规则尺寸是否对得上。
- 后续加策略推理：用环境里的 CPU `libtorch` 加载 TorchScript，观测/动作拼法与 `@20261007_assignment` 的 `policy_reference.py` 同一口径；这样能在本机不依赖 ROS 看导出的策略跑场地。
- 渲染锁：目前沿用源文件的单把锁（渲染与物理在同一线程阻塞）；按 `@20260923_mujoco` 的结论，官方 `RenderLoop` 在 `Render()` 之前放锁、C++ 不存 GIL 问题，**先不换**；等接入策略、拷贝/推理开销占比上来再换成“锁只罩拷贝”的双缓冲版本。
- 录屏/截图：本地可用 `pixi run env MUJOCO_GL=glfw` 开 GLFW 窗口；远程无显示时用 `MUJOCO_GL=egl` 的离屏渲染（Python 侧 `mujoco.Renderer`），C++ 视窗需要显示服务，不用于远程录屏。

## VS Code 本地设置与 pixi 可复现性（2026-10-21 排查）

- 本地 `.vscode/settings.json` 曾被加入 ROS 相关项（`ROS2.distro`、`python.autoComplete.extraPaths`、`python.analysis.extraPaths` 指向 `/opt/ros/humble/...`）。这些是**编辑器/Pylance 的本地路径**，不会影响 `pixi run` 的实际解释器、`pixi.lock` 或训练环境；但写在 tracked `settings.json` 里会污染仓库、在别的机器上指向不存在的路径。
- 已移除这三项；tracked `settings.json` 只保留 pixi 解释器、pixi clangd、通用编辑设置。
- `.vscode/c_cpp_properties.json` 含本机绝对路径，是本地 C/C++ IntelliSense 配置；已加入 `.gitignore`。
- `.vscode/browse.vc.db*` 是 C/C++ 扩展生成的索引数据库（本机约 1.1 GB），已加入 `.gitignore`，不应提交。
- 需要 ROS 自动补全时，请放到 **VS Code User Settings**（或本机不跟踪的配置），不要放回 tracked `.vscode/settings.json`；`pixi run` 不受影响。
- 验证：`git status --short .vscode` 应只显示本地未跟踪的 index/config，或者干净；`pixi run python -c 'import sys; print(sys.executable)'` 应指向 `.pixi/envs/default/bin/python`。
