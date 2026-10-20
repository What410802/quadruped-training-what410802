# 强化学习 Locomotion：平地 → 台阶/梅花桩

> 任务范围已进一步明确：先做**基本平地/粗糙地面的 Locomotion**（站着、走、小跑、平滑切换），再做**台阶与梅花桩**；地形素材来自新给地形与 2026 官方赛题地形的共用部分，后续可扩展到 2027 障碍集。当前阶段只做**材料与环境准备**，训练尚未开始。详细计划见 [`docs/training-plan.md`](docs/training-plan.md)，推进情况见 [`docs/status.md`](docs/status.md)。
>
> 目录（TOC）：[做了什么](#做了什么) · [怎么跑](#怎么跑) · [目录与文件](#目录与文件) · [文档](#文档) · [来源与许可](#来源与许可)

## 做了什么

| 事项 | 状态 | 入口 |
|---|---|---|
| 地形与资源盘点：只读材料 `terrain.zip`、`scene_terrain.xml`，2026 V2.0 场地/规则，2027 规则中的台阶/沟壑/梅花桩尺寸 | 已盘点，映射到 mjlab 地形类的方案已写 | [`docs/materials.md`](docs/materials.md) |
| 本地环境：沿用仓库根 `pixi.toml` 的单环境（MuJoCo 3.12 + glfw + cmake + CPU libtorch），本任务不新开本地环境 | 已确认无需新增本地依赖 | [`docs/environment.md`](docs/environment.md) |
| 远程训练机：`bis-ms7e56`（RTX 5060 Ti 16 GB / 驱动 595.99.02 / CUDA 13.4 / 原生 uv 0.13.3），GPU、EGL 渲染与训练冒烟均通过 | 环境已核验；512–8192 envs 基准见环境文档 | [`docs/environment.md`](docs/environment.md) |
| C++ 视窗：复用 `@20260927_motor` 里自写的 GLFW + mjv/mjr 窗口，本任务先用它看场景，后续接策略推理 | 已拷贝源码并加最小可运行程序 | [`cpp/`](cpp/) |
| TensorBoard：训练仓库已支持 `--agent.logger tensorboard`；记录方式与查看方式已写 | 已定 | [`docs/environment.md`](docs/environment.md) |
| 文献与开源实现索引：论文清单 + 可复用仓库/许可 | 已整理初版 | [`docs/literature.md`](docs/literature.md)、[`docs/open-source.md`](docs/open-source.md) |

## 怎么跑

本地命令都从**仓库根目录**执行（环境只有根 `pixi.toml` 一个，[`docs/conventions.md`](../docs/conventions.md) §4.1）：

```bash
pixi install                                                        # 首次装环境
pixi run cmake -S @20261019_locomotion/cpp -B @20261019_locomotion/cpp/build
pixi run cmake --build @20261019_locomotion/cpp/build -j
pixi run @20261019_locomotion/cpp/build/scene_viewer --scene @20261005_ros2/scenes/flat_scene.xml
```

窗口操作：鼠标左键旋转、右键平移（Shift + 右键竖直平移）、滚轮缩放、Esc/Q 关闭；当前 `scene_viewer` 只按 MuJoCo 默认控制量空转物理，用来检查场景与地形；接策略推理的版本见 [`cpp/README.md`](cpp/README.md)。

远程训练机（`bis-ms7e56`，RTX 5060 Ti 16 GB；原生 uv；首次配置的完整备份见训练仓库根目录 `REMOTE_SETUP.md`）：

```bash
ssh bis-ms7e56.tail4413b4.ts.net
export RC_WORK=${RC_WORK:-$HOME/rc_work}
export UV_CACHE_DIR="$RC_WORK/.uv-cache"
cd "$RC_WORK/nwwolf_mjlab_training_release"
uv sync --locked
MUJOCO_GL=egl .venv/bin/train black-flat --env.scene.num-envs 4096 --agent.max-iterations 2000 --agent.logger tensorboard
```

实测（2026-10-20，原生 uv）：`black-flat` 512/1024/2048/4096/8192 envs 冒烟均通过；迭代时间 0.67/0.82/1.05/1.57/2.62 s，峰值显存约 1.8/2.4/3.9/6.8 GB，其中 4096 envs 约 167k env steps/s（基准细节见 [`docs/environment.md`](docs/environment.md) §3）。录屏/截图用 `MUJOCO_GL=egl`（远程简单场景 0.063 ms/帧 @320×240）。

TensorBoard（训练机或本地拉回日志后）：

```bash
tensorboard --logdir logs/rsl_rl
# 远程查看：ssh -L 6006:localhost:6006 bis-ms7e56.tail4413b4.ts.net，然后浏览器打开 http://localhost:6006
```

## 目录与文件

```text
@20261019_locomotion/
├── README.md                 # 本文件：入口与怎么跑
├── docs/
│   ├── status.md             # 进度、决策、下一步、阻滞项
│   ├── environment.md        # 本地 pixi / 远程原生 uv / EGL / TensorBoard / C++ 视窗
│   ├── materials.md          # 地形与资源盘点、mjlab 地形映射、许可
│   ├── training-plan.md      # 阶段计划、手动模式/状态机/相机/PPO 的取舍
│   ├── literature.md         # 论文清单、可获取性与代码
│   ├── open-source.md        # 可复用开源实现与许可
│   └── repos.md              # 仓库划分与分支策略
├── cpp/                      # C++ 场景视窗（复用 @20260927_motor 的自写窗口）
│   ├── CMakeLists.txt
│   ├── .clang-format         # 新任务 C++ 风格：Allman + 4 空格 + 100 列
│   └── src/{main.cpp, viewer.h}
```

## 文档

- 地形与素材从哪来、怎么映射到 mjlab：[`docs/materials.md`](docs/materials.md)
- 环境（本机 pixi / 远程原生 uv / EGL 渲染 / TensorBoard / C++ 视窗）：[`docs/environment.md`](docs/environment.md)
- 训练阶段与方法论（含手动/状态机、相机、PPO 改进的取舍）：[`docs/training-plan.md`](docs/training-plan.md)
- 文献清单：[`docs/literature.md`](docs/literature.md)
- 仓库划分与分支策略：[`docs/repos.md`](docs/repos.md)
- 开源实现与许可：[`docs/open-source.md`](docs/open-source.md)

## 来源与许可

- 地形素材：培训方提供的只读材料 `terrain.zip`（单位置能力测试场，unitree 场景布局）与 `scene_terrain.xml`（unitree 模板改出的组合地形 playground）；2026 官方规则 V2.0、场地图册与 2027 规则 V1.0 为本机只读材料，规则原文可从 ROBOCON 官网与 LocoWiki 查。
- 2026 场地 CAD 参考：`Ruixi-Cheng/26RC_Field`（MIT，SolidWorks 单场地 + 镜像拼图）；`Zbszbszbssca/RC_MAP`（无许可证，仅参考，不入库）。
- 训练框架：`mujocolab/mjlab`（Apache-2.0）、队内训练仓库 `N-W-wolf/nwwolf_mjlab_training_release`（基于 mjlab）。
- C++ 视窗：复用本仓库 `@20260927_motor/cpp/src/viewer.h`（自写代码，GLFW + mjv/mjr）。
- 参考实现与论文的来源、版本与许可见 [`docs/open-source.md`](docs/open-source.md) 与 [`docs/literature.md`](docs/literature.md)。
