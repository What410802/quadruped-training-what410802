# 仓库与文档重组清点（2026-10-26，只清点不实改）

> 目的：回答两件事——① 训练仓（远端）/ 部署仓（本地）按 Part 1/2、HIM/PPO 划分目录/改名的收益是否大于成本；本地 `@20261024_blackw` 是否应该并进 `@20261019_locomotion`。② 本地 200+ 份文档按"竞赛共用 / Part1 / Part2 共用 / HIM / PPO"聚类后的目标目录树与每份文档内容。**本文件只做清点与方案，未移动/拆分/删除任何文件。**

## 0. 结论速览

| 拟议改动 | 收益 | 成本/风险 | 建议 |
|---|---|---|---|
| 远端训练仓源码目录按 Part1/2/HIM/PPO 重排 | 低（概念清晰） | **高**：上游 fork 结构、import/task 注册、共享 `.venv`、日志路径全挂 | **不做**；改用分支/tag + run/job/model 命名规范 |
| 本地 `@20261024_blackw` 并入 `@20261019_locomotion` | 低（少一个顶层目录） | 中：11 个仓内文件/103 行路径、ROS workspace 嵌套、180 个未入库文件、AGENTS/约定引用 | **不做**；用 `docs/INDEX.md` + 文档迁移解决 |
| 重命名两个本地任务目录 | 低（纯命名） | 中：251 行引用 + 仓库级约定/AGENTS 要改 | **不做**；写术语表 + 命名规范 |
| 远端 `gpu_jobs/` 分 `ppo/`、`him/`、`common/` | 中（防误交、可读） | 低（21 个脚本 + 提交命令） | **可做**（等审计闭环后，约 1 h） |
| 远端 `models/`、`logs/` 新产物按线/Part 分目录 | 中（109 个混放目录） | 低（旧的不动，只规范新产物） | **可做**（导出脚本 30 min/个） |
| 本地 `prep.d/` 分 `part1/`、`part2-ppo/`、`part2-him/`、`shared/` | 中 | 低（全被 gitignore，72 行脚本引用） | **可做**（约 1 h） |
| 文档按分类重组 + 归档 + 单源化 | **高**（当前 200+ 份、入口多源） | 中（链接重写 + 验证） | **优先做**（1–1.5 天） |
| `@20261024_blackw/ws` 源码入库 | **高**（180 个未入库文件，含刚修的 sim/motor） | 低 | **必须做**（先于任何移动） |

## 1. 仓库清点

### 1.1 本地：一个 monorepo，8 个任务目录

仓库根 `MyMonoRepo.d/` 是**单一 git 仓**（871 个 tracked 文件），任务按 `@<日期>_<主题>/` 平铺：

```
MyMonoRepo.d/
  AGENTS.md  README.md  pixi.toml  pixi.lock  docs/  scripts/  log/  prep.d/  .git/
  @20260922_robot_cpp_training/  @20260923_mujoco/  @20260927_motor/
  @20261005_ros2/  @20261005_ros2_example/  @20261007_assignment/
  @20261019_locomotion/          # 本次竞赛任务目录（35M，452 tracked）
  @20261024_blackw/              # blackW 部署工作区（263M，61 tracked + 180 未入库）
```

所以"两个本地仓"严格说是**同一 git 仓里的两个任务目录**（不是两个独立仓库）：仓库根 `README.md` 的"任务记录"表也只登记了 `@20261019_locomotion`（`@20261024_blackw` 是按 `@<日期>_<主题>` 惯例后建的，表里没更新）。

**`@20261019_locomotion`（竞赛任务目录）**
- `docs/` 58 md（896K）：竞赛规则/Part1/Part2/HIM/PPO/参考/运维混放，本文件 §3 逐个清点。
- `comp/` 330 文件（23M，其中 `traces/` 20M 已被 `comp/.gitignore` 忽略）：C0–C6 比赛流水线，含契约、记分板、run ledger、131 md 的审计归档（46 轮 judge 审计 + 31 个 prompt + 标定集）。
- `scripts/agent_scripts/` 52 个：`comp_*`（流水线）、`part1_*`/`comp_part1_*`（Part1 judge）、`part2_*`/`eval_blackw_*`（Part2 judge/评测）、`him_*`（HIM gate/导出/微调）、`check_*`/`make_*` 工具。
- `cpp/`、`config/`、`assets/`：Part1 场景 viewer、部署/Part1/Part2 配置、官方地形/策略/视频资源（`assets/policies/flat-ft-2500`、`assets/terrain/part1|part2`、`assets/videos/nan_debug`）。
- `AGENTS.md`：任务级工作流（C0–C6、Codex reviewer、comp/ 为状态入口）；**它把 `comp/STATUS.md` 定为必读**，所以 `comp/` 不能随便挪。

**`@20261024_blackw`（部署/Part2 blackW 工作区）**
- `ws/` 254M：ROS 2 工作区，`src/quadruped_ros2_blackw`（sim_node/电机模型/viewer）+ `src/rl_sar_blackw`（策略栈、launch、scenes、132 个 `policy/blackW/*` 策略目录）；`ws/build`、`ws/install` 被 gitignore。
- `scripts/` 21 个：Part2 judge/评测/BC/导出/检查（`eval_blackw_part2.py`、`gate_stage.py`、`collect_bc_*`、`train_bc_*`、`import_blackw_policy.py` 等）。
- `training/` 7 个：训练侧代码只读快照（`blackw/env_cfgs.py`、`guarded_ppo.py`、`black/…` 等）+ README。
- `models/` 4 个文件：`comp_bc_v5` 交付包（policy/config/checkpoint/manifest）。
- `output/`、`ws/**` 里 180 个文件**未入库**（含本轮修的 `sim_node.cpp`、`motor.hpp`、CMake、msg、launch、`.clang-format` 等）——这是当前最大的版本控制缺口，先 `git add` 再谈重组。

### 1.2 远端：两个训练仓 + 一个共享 venv

```
~/rc_work/
  nwwolf_mjlab_training_release/   13G  HIM 线/基线 release 仓（git 有历史；logs 5.7G）
  part2_team_race/                 2.8G PPO/BC 线的 fork（git 仅 2 commit，且当前 dirty）
    .venv -> ../nwwolf_mjlab_training_release/.venv   # 共享 venv（软链）
    src/alldog_mjlab/{tasks/velocity/{black,blackw}, robots/{black,blackw}, algorithms/him,…}
    scripts/agent_scripts/ 18 个
    logs/ 92 个 run（2.8G）  README.md  REMOTE_SETUP.md
  models/ 109 个目录（PPO 导出 101 个 contract.json、HIM 少量，混放）
  gpu_jobs/ 21 个脚本（ppo_*、him_*、common.sh、probe/smoke 混放）
  logs/ 81M（job summary/log 平铺）  videos/ 61M  results/ 42M  baseline/ 16M
```

关键事实：**两个仓的 `src/` 目录结构相同**（`black`=Part1 四足基座、`blackw`=Part2 blackW、`him.py`/`him_rl_cfg.py`/`algorithms/him`=HIM）。HIM 代码在 release 仓开发后被 PPO fork 继承，因此"HIM 代码在 PPO 仓里"不是事故，是 fork 同源；两条线的真实区分是"改哪个仓 + 用哪个 job/label/模型目录"，不是源码目录。

### 1.3 命名造成的路径混乱（具体清单）

| # | 混乱点 | 证据/位置 | 影响 |
|---|---|---|---|
| N1 | `black` 与 `blackw` 相邻但含义不同（Part1 12-dof 四足 vs Part2 16-dof 轮足） | 两个仓的 `src/alldog_mjlab/tasks/velocity/{black,blackw}`、`robots/{black,blackw}` | 新人按名字猜功能；文档"Part1/Part2"与"black/blackw"混用 |
| N2 | 两个 "training" 位置 + 一个 "docs/training" | 远端训练仓、`@20261024_blackw/training/` 快照、`@20261019_locomotion/docs/training/` | "训练代码/训练文档/训练快照"三处同名 |
| N3 | 两套关卡 JSON 同名不同义 | 部署场景 `scenes/blackW/part2_levels.json`（含修正出生高度）vs judge `part2_official_levels.json`（judge 规则/原始 start） | 跑错关卡集/出生点 |
| N4 | 两个 Part2 评测口径 | 本地 `eval_blackw_part2.py`（权威 judge v5）vs 远端 `eval_blackw_official.py`（旧口径，审计已标"第二 judge"） | 数字不可比 |
| N5 | run/log 命名无分类 | 92 个 run tag：`spec_*`、`guard4_*`、`ppo_*`、`m0_*`、`smoke_*`、`ts_trial_*`、`speed_*`… | 分不清 Part1/Part2/HIM/PPO、也分不清实验/调试 |
| N6 | 产物根分散 | `prep.d/results`、`prep.d/bc_data`、`~/rc_work/models`、`~/rc_work/logs`、`~/rc_work/videos`、`@20261024_blackw/output` | 同一策略的 ckpt/导出/评测/视频不在一处 |
| N7 | job 脚本平铺 | `gpu_jobs/` 里 `ppo_*`/`him_*`/`smoke_*`/`probe_*` 混放，共享 `common.sh` | 误交对方线、cleanup 难 |
| N8 | docs 目录无结构 | `docs/training/` 混 Part1/Part2/HIM/PPO/参考；`comp/` 与 `docs/` 两套元数据 | 见 §3–§4 |

### 1.4 路径引用成本（改动的真实代价）

- `@20261024_blackw` 路径名：**仓内 tracked 引用 30 个文件 / 103 行**；其中在 `@20261024_blackw` 之外的 11 个文件（`@20261019_locomotion/docs/*` 9 个 + `scripts/agent_scripts/probe_slope_friction.py` + status/plan）。移动/改名还会影响 `ws/build` 的 colcon 路径（自动重建可解）、`AGENTS.md`/根 `README.md`/任务 README 的目录惯例说明。
- `@20261019_locomotion` 路径名：**73 个文件 / 251 行**引用（含两个训练仓里的文档指针、`@20261024_blackw` 的 10 个文件）。
- 文档路径引用：`docs/training/` 67 行/29 文件、`docs/reference/` 88 行/59 文件，说明 docs 内部交叉引用密集——**重排文档必须用链接检查器逐批验证**。
- `comp/` 路径引用：1608 行/154 文件（`comp/STATUS.md`、`comp/CONTRACT.md` 是 AGENTS 硬编码必读）——**`comp/` 目录位置不动**。

## 2. 仓库/目录重组方案（收益 vs 成本）

### 2.1 `@20261024_blackw` 是否并进 `@20261019_locomotion`：**不建议**

理由：① 它本质是**独立 ROS 2 workspace + 部署工作区**（254M，`ws/src` 下两个包，`colcon build` 与策略目录、scenes 强绑定），塞进竞赛文档/评测目录会让"任务目录"同时承担编译工作区职责；② 合并只省一个顶层目录，收益低，但要改 11 个仓内文件/103 行引用、AGENTS/README 惯例说明，并重测 `ros2-build` 与 launch 路径；③ 仓库根本来就是"多任务目录平铺"的 monorepo，两个目录并列是符合既有惯例的。**推荐：保持并列，用 `docs/INDEX.md` 声明两者角色与关系。**

### 2.2 重命名（如 `@20261019_locomotion` → `part12-competition`、`@20261024_blackw` → `part2-deploy`）：**不建议现在做**

收益只是可读性；成本是 251+103 行路径、仓库级 AGENTS/README/约定、两个远端仓的文档指针、`ws/build` 重建。**替代做法**：在 `docs/INDEX.md` 写死"术语—目录"对照表（black=Part1、blackw=Part2、him=HIM、part2-ppo=PPO），并规定**新文件/新目录**用统一前缀（见 §5.2），旧目录不动。

### 2.3 远端训练仓源码树按 Part/线重排：**不建议**

`src/alldog_mjlab` 是 mjlab 上游 fork 的包布局，task 注册表、import、`uv.lock`、venv 共享、日志里的 run 路径都依赖它；重排是"结构性重构"，成本数天且高风险。**替代**：① HIM/PPO 用分支/tag（如 `line/ppo`、`line/him`，冻结时打 tag）；② 所有新 run/job/model 用 §5.2 命名规范；③ 在 `docs/INDEX.md` 维护"哪个仓/哪个目录归哪条线"的归属表。

### 2.4 远端 `gpu_jobs/` 分目录：**可做（低风险）**

建议 `gpu_jobs/{common.sh,on_finish.sh,kill_test.sh,ppo/,him/,probe/}`；21 个脚本里 `common.sh` 由各脚本 `source`（相对/绝对都要改），提交命令改为 `~/rc_work/gpu_jobs/ppo/<name>.sh`。成本约 1 h，收益是"不会误交对方线任务"。**建议在审计闭环结束后执行**（避免与当前验证 job 抢改）。

### 2.5 产物目录分类：**可做（低风险）**

- 本地 `prep.d/`（全部 gitignored）：`part1/`、`part2-ppo/{judge,gate,robust,exports,regression}/`、`part2-him/`、`shared/{audits,terrain}/`；现有 5 个子目录 + `bc_data` 按此归类，脚本里 72 行/40 文件路径同步（可先加符号链接过渡）。
- 远端 `~/rc_work/models/`：旧 109 个目录不动；新导出落 `models/<line>/<part>/<name>/`（`ppo/part2/...`、`him/part2/...`），导出脚本加 `--line/--part` 参数（每脚本约 30 min）。
- 远端 `~/rc_work/logs/`：job log/summary 保持平铺可 grep，但 job 名规范后自然可筛；92 个训练 run 目录建议**只读归档**到 `~/rc_work/archive/<line>/<part>/`（移动会破坏 tensorboard 引用，先用 `RUN_LEDGER` 建立旧→新映射再决定）。

### 2.6 必须先做的版本控制修复

`@20261024_blackw` 有 **180 个未入库文件**（含刚修的 sim_node/motor/CMake/msg/launch、`.clang-format` 等），`ws/build|install` 已 ignore。**任何移动/合并之前先 `git add` 这些部署源码**，否则一次 `git clean` 就会丢本轮修复。建议提交信息 `feat(blackw): version the deployment workspace sources`。

## 3. 文档清点与分类

### 3.1 总量与分类维度

- `@20261019_locomotion/docs/`：58 md（896K）。
- `@20261019_locomotion/comp/`：131 md（含 46 个审计正文 + 31 个 prompt + 标定/协议/状态）。
- 仓库根 `docs/`：13 md（仓库级约定 + 学习笔记 + 踩坑，**不属于竞赛任务文档**，位置不动）。
- `@20261024_blackw/`：3 md（README、training/README、him_row0 artifact README）。
- 合计约 205 md。按用户口径分 5 类：**共用（竞赛/评测/契约/治理）、Part1、Part2 共用、HIM、PPO**；另加 2 个横切类：**运维/环境**、**参考/学习**，以及 **归档（过期/被取代）**。

### 3.2 目标目录树（建议）

前缀/编号约定：`00` 竞赛共用、`10` Part1、`20` Part2 共用、`21` Part2-PPO、`22` Part2-HIM、`30` 运维、`40` 参考、`90` 归档。`comp/` 保持任务根目录不动（AGENTS 硬编码 `comp/STATUS.md`），只在 `docs/00-competition/pipeline.md` 放指针与状态说明。

```text
@20261019_locomotion/
  docs/
    INDEX.md                         # 新增：全文档地图 + 阅读顺序 + 线归属 + 术语表
    00-competition/                  # 竞赛共用（规则/契约/判定/计分/流水线/演示）
      rules-team-race-2026.md        # ← reference/team-race-2026.md
      contract.md                    # ← comp/CONTRACT.md 的指针（正文留在 comp/）
      judge-design.md                # ← training/competition-judge.md
      scoring-and-evidence.md        # 新增：分数证据链/记分板口径（从 comp/README+SCORING 抽取）
      pipeline.md                    # 新增：C0–C6 工作流索引，指向 comp/
      demo-guide.md                  # ← demo/acceptance-demo-guide.md
      fallback-state-machine.md      # ← training/manual-fallback-state-machine.md
    10-part1/                        # Part1（black 四足、障碍赛、8 障碍）
      plan.md                        # ← training/training-plan.md
      baseline.md                    # ← training/training-baseline.md
      health.md                      # ← training/training-health.md
      budget-and-recipes.md          # ← training/training-budget-and-recipes.md
      record-checklist.md            # ← training/training-record-checklist.md
      experiments.md                 # ← training/experiments.md
      stage4-migration.md            # ← training/stage4-migration-diagnosis.md
      visualization.md               # ← training/visualization.md
      eval-protocol.md               # ← training/eval-protocol.md（Part1 阶段 gate，顶部标注"Part2 用 20-…"）
      terrain-assets.md              # ← terrain/competition-assets.md
      terrain-materials.md           # ← terrain/materials.md
      gravel-feasibility.md          # ← terrain/gravel-feasibility.md
      gravel-penetration.md          # ← terrain/gravel-penetration.md
      p1-basic-obstacle.md           # ← training/p1-basic-obstacle.md
      terrain-coverage.md            # ← training/competition-terrain-and-symmetry-plan.md（Part1 部分）
    20-part2-shared/                 # Part2 共用（与路线无关：几何/档位/judge/验收/平台）
      geometry-and-levels.md         # ← training/part2-terrain-audit.md + 部分 competition-terrain-and-symmetry-plan
      acceptance-eval-protocol.md    # 新增（必写）：§0.3 的可执行 spec（采样/判据/schema/held-out）
      failure-vs-reward.md           # ← training/part2-failure-vs-reward-design.md
      architecture-decision.md       # ← training/blackw-architecture-decision.md
      strict-baseline.md             # ← training/blackw-strict-baseline-and-training-plan.md
      camera-depth.md                # ← training/camera-depth.md
      methodology.md                 # ← training/methodology-inventory.md
      reference-recipes.md           # ← training/reference-recipes.md
      deployment-contract.md         # 新增：从 @20261024_blackw/README.md 抽取（launch/policy 契约/键位/多策略切换）
      blackw-training-runs.md        # ← training/blackw-training-runs.md（Part2 全部 run 记录）
    21-part2-ppo/                    # PPO/BC 线
      handoff.md                     # ← training/part2-ppo-handoff-2026-10-26.md
      execution-plan.md              # ← training/part2-ppo-execution-plan-2026-10-26.md
      bc-policy-report.md            # ← training/part2-bc-policy-report.md
      blind-depth-curriculum.md      # ← training/part2-blind-depth-curriculum-plan.md
      history-part1-bugs.md          # ← 从 part2-ppo-training-history 拆：bug 审计/修复（§1–§11）
      history-experiments.md         # ← 拆分：验证实验/负结果（§12–§19）
      history-archive.md             # ← 拆分：早期记录/已作废（保留时间线）
      audits/                        # ← prep.d/audits/*.md 移入（core/deploy 两份 + 后续轮次）
    22-part2-him/                    # HIM 线
      route-overview.md              # ← training/cross-agent-comparison.md
      best-pt-zero-shot.md           # ← training/him-best-zero-shot.md
      deploy-him-best.md             # ← training/deploy-him-best.md
      gate-curriculum.md             # ← training/him-part2-gate-curriculum-plan.md
      gate-vs-judge-contract.md      # ← training/him-gate-vs-judge-contract.md
      export-baseline.md             # ← training/him-judge-export-baseline.md
      code-audit-2026-10-26.md       # ← training/him-code-audit-2026-10-26.md
      independent-audit-2026-10-26.md# ← training/him-independent-audit-2026-10-26.md
      path-trace-2026-10-26.md       # ← training/him-path-trace-2026-10-26.md
      nan-video-diagnosis.md         # ← training/nan-video-diagnosis.md
    30-ops/                          # 运维/环境/机器/队列/复现
      environment.md                 # ← environment.md
      remote-training-workflow.md    # ← training/remote-training-workflow.md
      gpu-queue.md                   # 新增：单一队列协议（从 8 处重复抽取）
      repo-layout.md                 # ← reference/repos.md（更新为现状）
      blackw-deploy-workspace.md     # ← @20261024_blackw/README.md 的部署章节（工作区 README 保留指针）
    40-reference/                    # 参考/学习/工具（跨线路）
      literature.md                  # ← reference/literature.md
      open-source.md                 # ← reference/open-source.md
      open-source-locomotion-survey.md # ← reference/open-source-locomotion-survey.md
      motor-model-and-viewer.md      # ← reference/motor-model-and-viewer.md
      quadruped-control-study.md     # ← reference/quadruped-control-study.md
      quadruped-control-pixi-migration.md # ← reference/quadruped-control-pixi-migration.md
      deployment-stack-comparison.md # ← reference/deployment-stack-comparison.md
      rl-sar-migration-plan.md       # ← reference/rl-sar-migration-plan.md
      rl-sar-fallback.md             # ← reference/rl-sar-fallback.md
      agent-visual-checklist.md      # ← reference/agent-visual-checklist.md
    90-archive/                      # 被取代/过期（保留文件头加 superseded 横幅 + 原路径说明）
      part1-eval-protocol-2026-10-20/…（若 §10 的 Part1 协议也过期）
      handoff-readiness-review-2026-10-26.md  # ← 本次评审（历史留档）
      reorg-inventory-2026-10-26.md           # ← 本文件（执行后归档）
  comp/                              # 不动位置（AGENTS 入口）；只做内部归档（见 §3.4）
```

### 3.3 `docs/` 58 份逐文档内容与去向

| 现路径 | 内容（一句） | 目标 | 动作 |
|---|---|---|---|
| demo/acceptance-demo-guide.md | 最终演示的 P0 验收流程与命令 | 00-competition/demo-guide.md | 移 |
| environment.md | 本地 pixi、远程 GPU、EGL/TensorBoard、C++ 视窗 | 30-ops/environment.md | 移 |
| plan.md | Part2/HIM 当前计划与待办（跨线） | docs/INDEX.md 的"状态"节 + 30-ops/status.md（或留作 live status） | 合并/瘦身 |
| status.md | 推进情况（跨对话对齐） | 同上 | 合并/保留 |
| reference/agent-visual-checklist.md | AI 动手前障碍方向/门洞视觉自检 | 40-reference/ | 移 |
| reference/deployment-stack-comparison.md | rl_sar vs quadruped_control 部署栈对比 | 40-reference/ | 移 |
| reference/literature.md | 训练/地形/鲁棒性文献清单 | 40-reference/ | 移 |
| reference/motor-model-and-viewer.md | 电机模型与 MuJoCo 窗口对齐 | 40-reference/ | 移 |
| reference/open-source-locomotion-survey.md | 开源四足训练仓调研 | 40-reference/ | 移 |
| reference/open-source.md | 可复用开源实现与许可 | 40-reference/ | 移 |
| reference/quadruped-control-pixi-migration.md | quadruped_control 迁 Pixi 实测 | 40-reference/ | 移 |
| reference/quadruped-control-study.md | quadruped_control 研读/接入方案 | 40-reference/ | 移 |
| reference/repos.md | 仓库划分与分支策略 | 30-ops/repo-layout.md | 移+更新 |
| reference/rl-sar-fallback.md | rl_sar 后备栈 | 40-reference/ | 移 |
| reference/rl-sar-migration-plan.md | 主控制栈迁 rl_sar 评估/计划 | 40-reference/ | 移 |
| reference/team-race-2026.md | 2026 队内赛任务真值（规则/计分/限制） | 00-competition/rules-team-race-2026.md | 移 |
| terrain/competition-assets.md | 赛方地形资产盘点 | 10-part1/terrain-assets.md | 移 |
| terrain/gravel-feasibility.md | 砂砾/碎石地形可行性实验 | 10-part1/gravel-feasibility.md | 移 |
| terrain/gravel-penetration.md | 砂砾踩入深度实验 | 10-part1/gravel-penetration.md | 移 |
| terrain/materials.md | 地形/资源盘点与 mjlab 映射 | 10-part1/terrain-materials.md | 移 |
| training/blackw-architecture-decision.md | Part2 用 HIM 类结构的架构决策 | 20-part2-shared/architecture-decision.md | 移 |
| training/blackw-strict-baseline-and-training-plan.md | blackW 固定动作/严格 Part2 baseline 计划 | 20-part2-shared/strict-baseline.md | 移 |
| training/blackw-training-runs.md | Part2 全部训练 run 记录（280 行） | 20-part2-shared/blackw-training-runs.md | 移 |
| training/camera-depth.md | 深度相机接入（C2 视觉主线） | 20-part2-shared/camera-depth.md | 移 |
| training/competition-judge.md | 队内赛判定器设计（Part1+2 共用） | 00-competition/judge-design.md | 移 |
| training/competition-terrain-and-symmetry-plan.md | 地形覆盖/对称性/blind vs depth 裁决（Part1+2 混合） | 拆：10-part1/terrain-coverage.md + 20-part2-shared/geometry-and-levels.md | 拆分 |
| training/cross-agent-comparison.md | 与另一 agent 的 Part2 路线对比 | 22-part2-him/route-overview.md | 移 |
| training/deploy-him-best.md | HIM best.pt 部署到手动演示环境 | 22-part2-him/deploy-him-best.md | 移 |
| training/eval-protocol.md | 2026-10-20 初版评测协议（Part1 flat/rough gate，已过时） | 10-part1/eval-protocol.md（+ 顶部标 Part2 见新 spec） | 移+改 |
| training/experiments.md | 实验记录模板/历史 | 10-part1/experiments.md | 移 |
| training/handoff-readiness-review-2026-10-26.md | 本次交接就绪度评审 | 90-archive/ | 移 |
| training/him-best-zero-shot.md | HIM best.pt zero-shot 评测 | 22-part2-him/best-pt-zero-shot.md | 移 |
| training/him-code-audit-2026-10-26.md | HIM 主链路代码审查 | 22-part2-him/code-audit-2026-10-26.md | 移 |
| training/him-gate-vs-judge-contract.md | HIM gate 与 judge 契约差异 | 22-part2-him/gate-vs-judge-contract.md | 移 |
| training/him-independent-audit-2026-10-26.md | HIM 独立审计结果 | 22-part2-him/independent-audit-2026-10-26.md | 移 |
| training/him-judge-export-baseline.md | HIM 导出与 judge proxy 基线 | 22-part2-him/export-baseline.md | 移 |
| training/him-part2-gate-curriculum-plan.md | HIM 最低档 gate 与课程推进 | 22-part2-him/gate-curriculum.md | 移 |
| training/him-path-trace-2026-10-26.md | HIM 实际代码路径推演 | 22-part2-him/path-trace-2026-10-26.md | 移 |
| training/manual-fallback-state-machine.md | 运行时状态机/手动保底/宏观导航 | 00-competition/fallback-state-machine.md | 移 |
| training/methodology-inventory.md | 方法论弹药库（跨线） | 20-part2-shared/methodology.md | 移 |
| training/nan-video-diagnosis.md | HIM platform NaN 崩溃录像与诊断 | 22-part2-him/nan-video-diagnosis.md | 移 |
| training/p1-basic-obstacle.md | Part1 slope+stairs 训练入口 | 10-part1/p1-basic-obstacle.md | 移 |
| training/part2-bc-policy-report.md | Part2 官方几何评测与可部署权重（PPO/BC） | 21-part2-ppo/bc-policy-report.md | 移 |
| training/part2-blind-depth-curriculum-plan.md | Part2 盲/深度模型分工与课程计划 | 21-part2-ppo/blind-depth-curriculum.md | 移 |
| training/part2-failure-vs-reward-design.md | Part2 失败/终止 vs 奖励分工 | 20-part2-shared/failure-vs-reward.md | 移 |
| training/part2-ppo-execution-plan-2026-10-26.md | PPO/BC 线执行计划（现行） | 21-part2-ppo/execution-plan.md | 移 |
| training/part2-ppo-handoff-2026-10-26.md | PPO/BC 线交接（入口） | 21-part2-ppo/handoff.md | 移 |
| training/part2-ppo-training-history.md | PPO/BC 历史归档（382 行，§1–§19） | 拆 3 份 history-*.md + archive | 拆分 |
| training/part2-terrain-audit.md | Part2 训练地形审计（proxy vs 官方） | 20-part2-shared/geometry-and-levels.md（并入） | 合并 |
| training/reference-recipes.md | N-W-wolf/HYNova/官方权重配方盘点 | 20-part2-shared/reference-recipes.md | 移 |
| training/remote-training-workflow.md | 远程 GPU 训练工作流 | 30-ops/remote-training-workflow.md | 移 |
| training/stage4-migration-diagnosis.md | stage4 blind 策略迁移诊断 | 10-part1/stage4-migration.md | 移 |
| training/training-baseline.md | flat/rough 训练基线 | 10-part1/baseline.md | 移 |
| training/training-budget-and-recipes.md | 训练预算/env/step/iter/配方 | 10-part1/budget-and-recipes.md | 移 |
| training/training-health.md | rough 基线健康检查 | 10-part1/health.md | 移 |
| training/training-plan.md | 训练计划与方法论（Part1 主导） | 10-part1/plan.md | 移 |
| training/training-record-checklist.md | 每轮训练记录清单 | 10-part1/record-checklist.md | 移 |
| training/visualization.md | 训练场景/节点视频可视化 | 10-part1/visualization.md | 移 |

> 说明：上表 58 行覆盖 `docs/` 全部 md；"拆/并"的 4 处（competition-terrain、PPO history、part2-terrain-audit、plan/status）是本次建议的少数内容性操作，其余为纯移动。

### 3.4 `comp/` 131 份文档：保持位置，内部归档

`comp/` 是 C0–C6 工作流的状态目录（AGENTS 规定必读 `comp/STATUS.md`），**不迁移到 docs**；但当前 131 md 里 77 份是 judge 审计轮次与 prompt，建议：

| 子目录/文件 | 内容 | 建议 |
|---|---|---|
| `CONTRACT.md/json`、`COMPLIANCE.*`、`reviewer.json` | 比赛契约与合规 | 不动 |
| `STATUS.md`、`PLAN*.md`、`RUN_LEDGER.md`、`SCOREBOARD.*`、`findings.md`、`README.md`、`DEV_OPS.md` | 工作流状态/账本/计划 | 不动；README 加"文档地图" |
| `audits/JUDGE_AUDIT.md`、`G1_SELFCHECK.md`、`C1_CALIBRATION_REPORT.md`、`README.md` | 最终审计结论/自检 | 保留顶层 |
| `audits/BYOK_*`（40+ 个）、`audits/prompts/`（31 个） | 历史轮次审计正文与 prompt | 归 `audits/archive/rounds/<version>/`；顶层留 `JUDGE_ACCEPTANCE_INDEX.md`（最终 verdict 汇总） |
| `eval/_protocol.md`、`eval/_calibration/` | 评测协议草稿、人工标定 | 不动（与 Part2 新 spec 建指针） |
| `defense/README.md`、`freeze/README.md` | C6 答辩、C5 冻结占位 | 不动 |
| `traces/`（20M，已 gitignore） | 审计 trace | 不入库；清理旧 trace 前先导 `RUN_LEDGER` |

### 3.5 仓库根 `docs/`（13 份）与 `@20261024_blackw`（3 份）

- 根 `docs/`：`conventions.md`（仓库约定，必须保留在根）、`learn/**`（11 份学习笔记：CMake/MuJoCo/ROS2/rl_sar/时序/TBB/unitree 等）、`pitfalls/environment.md`（环境踩坑）。**属仓库级共享知识，与竞赛任务目录无关，位置不动**；在 `docs/INDEX.md` 里以指针收录即可。
- `@20261024_blackw/README.md`（167 行）：部署工作区总览 + Part2 现状表 + 部署契约/自检命令。建议：**保留为工作区 README**（ROS 工作区自解释），把"部署契约/策略切换/自检"抽成 `20-part2-shared/deployment-contract.md`，README 里放指针。
- `@20261024_blackw/training/README.md`（15 行）：训练侧只读快照说明。建议移到 `20-part2-shared/code-snapshot.md`（说明"快照只读、远程仓为准、与哪个 commit 对齐"），原位置保留 1 行指针。
- `ws/src/rl_sar_blackw/policy/blackW/him_row0/README.md`：HIM 模型产物说明，留在产物目录，不动。

## 4. 文档重排的执行方案（若批准）

1. **Step 0（先决，必须）**：把 `@20261024_blackw` 180 个未入库文件 `git add` 并提交（`feat(blackw): version deployment workspace sources`）；同时把当前 6 个 `@20261019_locomotion` 修改一起提交，保证移动前基线干净。
2. **Step 1（0.5 天）**：建 `docs/INDEX.md`（角色/术语表/阅读顺序/归属表）与空目录骨架；按 §3.3 逐批 `git mv` + 用 `check_md_links.py` 每批自检；同步改 `git grep` 到的 67+88 行跨文档链接。
3. **Step 2（0.5 天）**：内容性操作——拆 `competition-terrain-and-symmetry-plan`、把 `part2-terrain-audit` 并入 geometry、`part2-ppo-training-history` 拆 3 份、`plan/status` 瘦身为 `30-ops/status.md`；把 §0.3 口径落成 `20-part2-shared/acceptance-eval-protocol.md`（本项已在执行计划 §0.3 有草稿，需补可执行细节）。
4. **Step 3（0.5 天）**：`comp/` 审计归档 + `JUDGE_ACCEPTANCE_INDEX.md`；`docs/90-archive/` 收录过期文档（旧 Part1 评测协议、本清点文件、交接评审）；所有归档文件顶部加 3 行 superseded 横幅。
5. **Step 4（0.5 天）**：`prep.d/` 分类与脚本路径同步（72 行/40 文件）；`gpu_jobs/` 分目录（21 脚本，审计闭环后做）。
6. **Step 5（半天，可选）**：远端 `models/` 新产物按线/Part 分目录 + 导出脚本加 `--line/--part`；旧目录不动；`RUN_LEDGER` 建旧→新映射。

总工时约 **2–2.5 天**（含链接检查与两次全量 md 检查）；风险低（不动源码、不动物理/评测逻辑），前提是 Step 0 先完成。

## 5. 命名与路径规范（建议写入 INDEX/约定）

### 5.1 规范路径（写文档时一律用这个表）

| 概念 | 规范写法 | 说明 |
|---|---|---|
| 仓库根 | `<REPO>` | 文档里不写 `/home/bis/...` 绝对路径 |
| 竞赛任务目录 | `@20261019_locomotion/` | 不动 |
| 部署工作区 | `@20261024_blackw/` | 不动；含 `ws/`（ROS 2）与 `models/`（交付包） |
| 远端 PPO 训练仓 | `~/rc_work/part2_team_race/` | PPO/BC 线改动仓 |
| 远端 HIM/基线仓 | `~/rc_work/nwwolf_mjlab_training_release/` | HIM 线 + 共享 `.venv` |
| 共享 venv | `~/rc_work/nwwolf_mjlab_training_release/.venv` | 两个仓共用（软链） |
| 本地临时产物 | `prep.d/` | 已 gitignore；分类见 §2.5 |
| 远端产物 | `~/rc_work/{models,logs,videos,results}/` | 新产物加线/Part 前缀 |

### 5.2 新文件/新 run 命名

- 文档：`<前缀>-<主题>.md`，前缀 `competition-`、`part1-`、`part2-shared-`、`part2-ppo-`、`part2-him-`、`ops-`、`reference-`；日期后缀只给一次性记录（`-2026-10-26`）。
- 训练 run：`<line>_<part>_<family>_<purpose>_<MMDD>`，如 `ppo_p2_stairs_exact_s100b_1026`、`him_p2_row0_mixed_1026`。
- job 脚本：`gpu_jobs/<line>/<same-as-run>.sh`；label 与 run 名一致。
- 模型/导出目录：`models/<line>/<part>/<run-or-policy>/`；policy 目录内部保持 `policy.pt + config.yaml + manifest.json`（现有工具已强制）。
- 术语表（写进 INDEX）：`black`=Part1 四足基座；`blackw`=Part2 16 关节轮足；`him`=HIM 线（含 depth/HIMLoco）；`part2-ppo`/`ppi`=PPO/BC 线；`comp/`=比赛流水线；`judge v5`=权威本地判据。

## 6. 风险与待确认

- **版本控制缺口**：`@20261024_blackw` 180 个未入库文件（含本轮修复）必须先入库，否则任何清理/移动都可能丢代码。
- **文档所有权**：HIM agent 已停止；`docs/plan.md`、`docs/status.md`、`him-*.md`、`comp/` 后续由谁维护需你确认（我暂按"全部可由我整理"处理，但会保留署名/历史）。
- **`comp/` 不能动位置**：`@20261019_locomotion/AGENTS.md` 硬编码 `comp/STATUS.md` 为必读顺序；若移动必须同步改 AGENTS 且可能破坏工作流脚本。
- **旧 run/模型目录重命名**：会破坏 tensorboard 引用与现有 job 脚本；建议只规范新产物 + `RUN_LEDGER` 建映射，不物理移动旧目录。
- **两套关卡 JSON 合并**（N3）：语义不同（部署修正出生高度 vs judge 规则），建议保留两份但在两份文件头互写指针（不改数据）。
- **`docs/plan.md` / `status.md` 与 `comp/STATUS.md` 的双状态源**：现状是 3 个"状态"入口，建议 INDEX 明确"任务进度看 docs/status，流水线看 comp/STATUS，PPO 线看 21-part2-ppo/execution-plan §0.2"。
