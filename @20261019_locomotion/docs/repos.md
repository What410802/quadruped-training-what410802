# 仓库划分与分支策略（计划）

> 本文回答“训练代码放哪、运行代码放哪、权重放哪、远程机扮演什么角色”。当前许多组件还在搭建中，落地时以本文为准并同步更新 [`status.md`](status.md)。

## 1. 结论

- **不 fork mjlab 本体**，只把 mjlab 当**锁定版本的上游依赖**；训练侧的改动全部放在**训练仓库**（mjlab 之上的薄层）。理由：mjlab 带框架/环境注册/训练循环/导出，更新频繁；我们的增量只是地形、奖励、课程、配置与导出脚本，混进框架会失去“上游可升级、diff 可读、许可清晰”的优点。
- 训练仓库**建议 fork 现有队内仓库** `nwwolf_mjlab_training_release`（当前 `main` 只有 `24c7f16 first commit`，结构就是 `src/alldog_mjlab/{tasks,robots,algorithms,utils}` + `pyproject.toml` + `uv.lock`），而不是从零建。它的 `mjlab>=1.6.0` 改为**精确锁** `mjlab==1.6.0`，`uv.lock` 入库，这样远程复现的就是作者验证过的组合。
- 运行仓库（本仓库 `MyMonoRepo.d`）只做**运行时**：验收、部署、sim2sim、评测、C++ 视窗。它**不装训练依赖**，只接收导出的 `policy.pt` 与配置。这样“训练/运行分离”，运行侧替换 `.pt` 即可，不必改代码。
- 远程机是**训练执行器**，不是第三个“运行时”：它 clone 训练仓库、跑训练/导出/批量评测；**不需要**为“高效推理”单独维护一份运行仓库——策略推理在 CPU 上是亚毫秒级，远程 GPU 的价值在训练与批量评估，不在单次推理。
- GitHub 是两边的**唯一权威备份**：训练仓库（公开或私有）+ 运行仓库（公开，用于开源与备份）；远程机的 clone 是 disposable 的。

## 2. 仓库角色

| 仓库 | 角色 | 放什么 | 不放什么 |
|---|---|---|---|
| `MyMonoRepo.d`（本仓库，运行/验收） | 运行时、评测、部署、文档 | 任务目录（如 `@20261019_locomotion/`）、仿真/评测脚本、C++ 视窗、部署配置、导出的 `policy.pt`、实验记录 | 训练代码、训练依赖、日志、原始 checkpoint |
| `nwwolf_mjlab_training_release` fork（训练） | 训练/导出 | `src/alldog_mjlab/{tasks,robots,algorithms,utils}`、地形/奖励/课程/DR 配置、`uv.lock`、`pyproject.toml`、`REMOTE_SETUP.md`（训练机配置）、导出工具 | 运行时代码（rl_sar、sim2sim 部署）、评测报告正文 |
| `mujocolab/mjlab`（上游） | 框架依赖 | 只读；通过 `mjlab==1.6.0` + `uv.lock` 固定 | 我们的改动（除可上游的 bugfix，以 PR/patch 形式） |

## 3. 训练仓库（fork 后）建议结构

```text
nwwolf_mjlab_training_release/          # 我们的 fork，GitHub 私有/公开均可
├── pyproject.toml                      # mjlab==1.6.0（精确锁），项目名 alldog-mjlab
├── uv.lock                             # 提交；远程 uv sync --locked 的唯一依据
├── README.md                           # 训练/导出/评测命令、环境版本
├── REMOTE_SETUP.md                     # 远程训练机配置备份（从运行仓库的 environment.md 对应过去）
├── src/alldog_mjlab/
│   ├── tasks/velocity/black/           # 任务：flat / rough / him
│   │   ├── black_config.py             # TerrainParams、比例、课程
│   │   ├── terrain.py                  # 现有 BlackRoughSlopeTerrainCfg + 新地形（台阶/梅花桩/碎石）
│   │   ├── env_cfgs.py                 # 装配、sensor/critic、reward/termination
│   │   ├── rewards.py
│   │   ├── curriculums.py
│   │   └── him*.py                     # HIM 变体
│   ├── robots/black/                   # 机器人常量、xmls（与运行仓库模型同源）
│   ├── algorithms/him/                 # HIM 组件（如用）
│   └── utils/export_policy.py          # TorchScript 导出（policy.pt）
├── scripts/                            # 人跑的检查/实验脚本（不含一次性仪器）
├── docs/                               # 训练方法、实验记录、地形尺寸依据
└── logs/                               # .gitignore；checkpoint/曲线只在远程/本地，不进 Git
```

新增地形/实验只改 `tasks/velocity/black/` 下的配置，不动 `src/alldog_mjlab/` 之外的框架代码；确需修 mjlab 的问题时，优先上游 PR，退而在训练仓库 `patches/` 放可复现的 patch 并在 README 写清楚。

## 4. 运行仓库（本仓库）的对应结构

```text
MyMonoRepo.d/
├── @20261019_locomotion/               # 本任务：地形/材料/评测/视窗/文档
│   ├── docs/                           # status、environment、materials、training-plan、literature、open-source、repos
│   ├── cpp/                            # scene_viewer（复用 @20260927_motor 的 viewer）
│   ├── assets/policies/<version>/      # 导出的 policy.pt + 配置 + 评测记录（后续）
│   └── scripts/agent_scripts/          # 评测/分析脚本
├── @20261005_ros2/                     # 仿真/手柄/消息（运行时）
├── @20261007_assignment/               # rl_sar 部署（运行时）
└── docs/                               # 跨任务通用文档
```

运行侧与训练侧的接口只有：**observations/action 契约 + policy.pt + yaml 配置**。契约固定为 45 维 obs（HIM 为 270 = 6×45）、12 维动作、`q_target = q_default + 0.25 × raw`、`kp=40/kd=1.2`、50 Hz；换策略时先跑一个**契约校验脚本**（输入/输出 shape、obs 顺序、动作缩放、joint mapping），再进仿真/实机，避免“换 .pt 后行为不对但不知道哪层错”。

## 5. 分支与标签策略

| 仓库 | 分支 | 用途 |
|---|---|---|
| 训练仓库 | `main` | 稳定训练代码/配置；只接受已验证的实验配置 |
| 训练仓库 | `exp/<stage>-<topic>` | 例如 `exp/s1-him-vs-privileged`、`exp/s2-stairs-curriculum`；配置小改动在此迭代，结论回写 `main`/docs 后删除或留档 |
| 训练仓库 | `feat/terrain-*`、`fix/*` | 地形/奖励/导出等独立改动 |
| 训练仓库 | `weights/<stage>` | 可选：只放**选中的** checkpoint（`.pt` 约 1 MB，Git LFS 可选）与评测数字；更推荐用 GitHub Release 附加 `policy.pt`，避免仓库变重 |
| 训练仓库 | tag `s1-v1`、`s2-v1` | 每个里程碑（对照实验结束、验收通过）打 tag，记录 commit + lock 版本 + 评测 |
| 运行仓库 | `main` | 运行时/文档/评测；固定契约与已验收策略 |
| 运行仓库 | `weights/<stage>` 或 `assets/policies/` + tag | 验收用 policy.pt 与配置；推荐小文件直接放任务 `assets/policies/<version>/`，大文件走 Release |
| 运行仓库 | `release/<competition>` | 赛前冻结版本（代码+策略+配置），便于复现 |

提交信息统一按 [`../../docs/conventions.md`](../../docs/conventions.md) §1：一行英文 `type(scope): …`；训练仓库同样适用（fork 后改约定也可，但保持与运行仓库一致更省心）。

## 6. 制品流（训练 → 运行）

```text
训练仓库 main/exp  ──train──▶ logs/rsl_rl/<run>/model_*.pt
      │                            │
      │ 记录 commit + uv.lock      │ export --task-id … --load-run … --checkpoint …
      ▼                            ▼
 GitHub（训练仓库）          <run>/exported/policy.pt
                                   │
                                   │ 拷贝/下载 + 配置 + 评测记录
                                   ▼
运行仓库 @20261019_locomotion/assets/policies/<version>/
                                   │
                                   ▼
本地 MuJoCo 仿真 + C++ 视窗 + rl_sar 验收
```

- 每个 `policy.pt` 在运行仓库里带一份**最小元数据**：训练仓库 commit、`uv.lock` hash、任务 id、obs/action 契约、训练/评测命令、关键数字；没有元数据的权重不进入 `main`。
- 远程机只负责训练与导出；导出文件先回 GitHub（Release 或 weights 分支），再同步到运行仓库，避免“某台机器上的文件才是唯一版本”。

## 7. 远程机定位（回答“三端都放运行仓库值得吗”）

- **训练**：必须放远程机（GPU）；clone 训练仓库 + 原生 uv 环境（`uv sync --locked`）。
- **批量评估**：可以放远程机（例如一次跑几十个地形/种子的评测），但它跑的是**训练仓库的评测脚本**或运行仓库的评测脚本，不需要第三份“运行时仓库”。
- **单次推理/验收**：笔记本足够（策略 CPU 推理亚毫秒级），也是验收现场；远程 GPU 对单次推理没有收益。
- 因此“运行仓库三端都有”可行但不是最优：GitHub（备份/开源）+ 笔记本（验收运行时）是必需的；远程机按需 clone 运行仓库只为批量评测，不作为第三个长期运行副本，避免三个副本手工同步。

## 8. 落地顺序

1. 训练仓库 fork 已建（`What410802/nwwolf_mjlab_training_release`，`upstream` 指 N-W-wolf）；把 `mjlab>=1.6.0` 改成 `mjlab==1.6.0` 精确锁；把 `REMOTE_SETUP.md` 提交进 fork 并推送 GitHub（训练机配置备份）。
2. 训练仓库加地形（flat/rough/碎石 → 台阶 → 梅花桩）与对应实验分支；运行仓库加 policy 契约校验 + 评测脚本 + `assets/policies/` 约定。
3. 远程机原生 uv 已跑通 `black-flat` 冒烟与 512–8192 envs 基准；接着挂 4096 envs 做 S1 第一组对照（HIM vs privileged critic）。
4. 每次导出策略都写运行仓库任务 `docs/status.md` 与 `assets/policies/<version>/README`，保证“策略来自哪、怎么评测的”可追溯。
