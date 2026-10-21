# 强化学习 Locomotion：2026 队内赛（障碍赛 + 越障能力）

> **任务真值已校准（2026-10-21）**：当前目标是 **2026-11-04 队内赛**，不是 2027 赛季。比赛分两个赛项：24 届 RC 足式障碍赛（8 障碍 × 100 + 返回启动区 100，遥控满分 900）与越障能力测试（高台/楼梯/斜坡/高墙/沟壑/梅花桩，满分 1300）；两项得分和占 70%，7 分钟答辩占 30%。规则、成功定义、传感器/力矩限制见 [`docs/reference/team-race-2026.md`](docs/reference/team-race-2026.md)。
>
> 当前有效进度：`flat-ft-2500` 在 flat gate、固定砂砾、composite 自由砂砾 zero-shot 上初版可用；但没有正式障碍场/能力场任务，`black-rough` 综合 zero-shot 4 envs 仍 25% 摔倒，离比赛要求有明显差距。旧 2027/S1b-first/rough-first 路线降为研究性 backlog；14 天路线见 [`docs/status.md`](docs/status.md) 与 [`docs/training/training-plan.md`](docs/training/training-plan.md) §0。
>
> 目录（TOC）：[做了什么](#做了什么) · [怎么跑](#怎么跑) · [目录与文件](#目录与文件) · [文档](#文档)

## 做了什么

| 事项 | 状态 | 入口 |
|---|---|---|
| 任务真值：2026 队内赛 PDF（障碍赛 + 越障能力 + 答辩），取代旧 2027/V2.0 假设 | 已读取并校准路线 | [`docs/reference/team-race-2026.md`](docs/reference/team-race-2026.md) |
| 地形与资源盘点：只读材料 `terrain.zip`、`scene_terrain.xml`，旧 2026 V2.0/2027 规则仅作参考 | 已盘点；正式队内赛障碍场尚未建模 | [`docs/terrain/materials.md`](docs/terrain/materials.md) |
| 本地环境：沿用仓库根 `pixi.toml` 的单环境（MuJoCo 3.12 + glfw + cmake + CPU libtorch），本任务不新开本地环境 | 已确认无需新增本地依赖 | [`docs/environment.md`](docs/environment.md) |
| 远程训练机：`bis-ms7e56`（RTX 5060 Ti 16 GB / 驱动 595.99.02 / CUDA 13.4 / 原生 uv 0.13.3），GPU、EGL 渲染与训练冒烟均通过 | 环境已核验；512–8192 envs 基准见环境文档 | [`docs/environment.md`](docs/environment.md) |
| C++ 视窗：复用 `@20260927_motor` 里自写的 GLFW + mjv/mjr 窗口，本任务先用它看场景，后续接策略推理 | 已拷贝源码并加最小可运行程序 | [`cpp/`](cpp) |
| TensorBoard：训练仓库已支持 `--agent.logger tensorboard`；记录方式与查看方式已写 | 已定 | [`docs/environment.md`](docs/environment.md) |
| 文献与开源实现索引：论文清单 + 可复用仓库/许可 | 已整理初版 | [`docs/reference/literature.md`](docs/reference/literature.md)、[`docs/reference/open-source.md`](docs/reference/open-source.md) |

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

TensorBoard（`tensorboard` 只在训练仓库的 venv 里，远程 PATH 上没有；不要直接敲 `tensorboard`）：

```bash
cd ~/rc_work/nwwolf_mjlab_training_release
.venv/bin/tensorboard --logdir logs/rsl_rl/black_velocity --port 6006
# 本地先转发：ssh -L 6006:localhost:6006 bis-ms7e56.tail4413b4.ts.net，再打开 http://localhost:6006
```

## 目录与文件

```text
@20261019_locomotion/
├── README.md
├── config/
│   └── manual-state-machine.yaml    # 手动保底状态机配置
├── docs/
│   ├── status.md                     # 当前状态、待决、下一步（保持实时）
│   ├── environment.md                # 本地 pixi / 远程原生 uv / EGL / TensorBoard / C++ 视窗
│   ├── training/
│   │   ├── training-plan.md          # 阶段计划、手动/状态机/相机/PPO 取舍
│   │   ├── training-baseline.md      # 现有课程/奖励基线梳理
│   │   ├── training-health.md        # TensorBoard 体检与数值/地形问题
│   │   ├── training-record-checklist.md  # 每轮训练手工记录清单
│   │   ├── experiments.md            # run 表、指标、gate、步态/yaw 体检
│   │   ├── eval-protocol.md          # 评测协议与 G1–G5
│   │   └── visualization.md          # 训练场景/节点视频、图例、可视化代码分布
│   ├── terrain/
│   │   ├── materials.md              # 地形/资源盘点、尺寸、mjlab 映射、新资料
│   │   ├── gravel-feasibility.md     # 砂砾/碎石可行性原型与社区做法
│   │   ├── gravel-penetration.md     # 足端踩入深度实验（预烘焙深度依据）
│   │   ├── competition-assets.md     # Part 1/Part 2 地形资产审计与修改项
│   │   └── manual-fallback-state-machine.md  # 手动保底状态机/运行时真值/相机阶段
│   └── reference/
│       ├── team-race-2026.md         # 2026 队内赛真值：两个赛项/成功定义/得分/约束
│       ├── quadruped-control-study.md # quadruped_control 架构研读与状态机接入
│       ├── quadruped-control-pixi-migration.md # Pixi 依赖迁移实测与缺口
│       ├── literature.md             # 论文清单与培训方补充材料
│       ├── open-source.md            # 可复用实现、许可、本任务来源
│       └── repos.md                  # 仓库划分与分支策略
├── assets/
│   ├── terrain/
│   │   ├── part1/                   # Part 1 working scene (Black include, judge anchor names)
│   │   └── part2/                   # Part 2 plum XML + official level catalog
│   └── policies/
│       ├── baseline-2000/            # policy.pt、eval JSON、来源说明
│       ├── baseline-rough-3999/      # rough 对照权重（G3 未通过，不是验收策略）
│       ├── gravel-flat-2100/         # S1b-fixed 初版通过；步态仍不对称，不是验收策略
│       ├── free-gravel-v2-700/       # 旧稀疏布局，已作废（仅历史）
│       ├── free-gravel-dense80-3995/ # 旧 15–19 cm 大石块，过渡/木块参考，不是 S1b-free 证据
│       └── flat-ft-2500/             # 2026-10-21 flat/S1b 候选：G1 + S1b 初版通过
├── cpp/                              # C++ 场景视窗
│   ├── CMakeLists.txt
│   ├── .clang-format
│   └── src/{main.cpp, viewer.h}
└── scripts/
    └── agent_scripts/                # eval_flat.py、render_*.py、gravel_penetration_experiment.py、part1_judge.py、check_state_machine.py
```

## 文档

**状态与环境**

- 当前状态、待决、下一步：[`docs/status.md`](docs/status.md)
- 环境（pixi / 远程 uv / EGL / TensorBoard / C++ 视窗）：[`docs/environment.md`](docs/environment.md)

**训练与评测**

- 训练计划（阶段、手动/状态机、相机、PPO）：[`docs/training/training-plan.md`](docs/training/training-plan.md)
- 现有课程/奖励基线：[`docs/training/training-baseline.md`](docs/training/training-baseline.md)
- 实验记录（run 表、评测、gate、步态/yaw）：[`docs/training/experiments.md`](docs/training/experiments.md)
- 评测协议与 G1–G5：[`docs/training/eval-protocol.md`](docs/training/eval-protocol.md)
- 训练健康检查（数值不稳定、地形课程）：[`docs/training/training-health.md`](docs/training/training-health.md)
- 每轮训练记录清单：[`docs/training/training-record-checklist.md`](docs/training/training-record-checklist.md)
- 视频可视化（场景/节点、图例、代码分布）：[`docs/training/visualization.md`](docs/training/visualization.md)

**地形与素材**

- 2026 队内赛真值：[`docs/reference/team-race-2026.md`](docs/reference/team-race-2026.md)
- 手动保底状态机：[`docs/training/manual-fallback-state-machine.md`](docs/training/manual-fallback-state-machine.md)
- 地形/资源盘点与 mjlab 映射：[`docs/terrain/materials.md`](docs/terrain/materials.md)
- 砂砾/碎石可行性：[`docs/terrain/gravel-feasibility.md`](docs/terrain/gravel-feasibility.md)、踩入深度实验 [`docs/terrain/gravel-penetration.md`](docs/terrain/gravel-penetration.md)、比赛地形资产 [`docs/terrain/competition-assets.md`](docs/terrain/competition-assets.md)

**参考**

- 文献与培训方补充材料：[`docs/reference/literature.md`](docs/reference/literature.md)
- 开源实现、许可与任务来源：[`docs/reference/open-source.md`](docs/reference/open-source.md)
- 仓库划分与分支策略：[`docs/reference/repos.md`](docs/reference/repos.md)

## 来源与许可

统一记录在 [`docs/reference/open-source.md`](docs/reference/open-source.md) §7：地形/规则素材、2026 场地 CAD 参考、训练框架、C++ viewer 与本次培训方补充材料的来源与许可。
