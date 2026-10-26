# Phase 1 训练主干迁移等价性证明

本文件是旧任务仓的最后一次文档提交，记录“旧仓代码 → 新训练仓 `~/RoboCon/training`”的迁移范围、逐条处置、等价性证据与有意变更，供追溯。新仓对应分支 `migrate/phase1`。

## 1. 来源与合并基线

| 代号 | 来源 | 说明 |
|---|---|---|
| upstream | `N-W-wolf/nwwolf_mjlab_training_release` @ `24c7f16` | 新仓 `main` 初始提交；第三方代码原样 |
| legacy/ppo | 旧仓工作线 PPO/BC（等价于远端 `part2_team_race` @ `04ae722`） | 合并基底：通用补丁、判据镜像、审计修复、导出/工具、PPO/BC 线 |
| legacy/him | 旧仓工作线 HIM（等价于远端 `nwwolf_mjlab_training_release` @ `e977ecb`） | HIM 算法守卫、官方 warm start、blackW HIM 集成、部分安全终止 |

两旧分支共同改动的 38 个文件中 26 个逐字节相同；12 个分叉按 §3 处置。

## 2. 迁移目标结构（新仓）

```text
training/
├── robots/{black,blackw}/                 # 硬件契约；blackW mesh 入库（42 MB，来自官方 blackW.zip）
├── tasks/velocity/
│   ├── black/                             # Part 1 / 通用 velocity 线（上游按关注点分模块）
│   ├── blackw/                            # Part 2 线：env_cfgs 装配 + actions + him*
│   └── profiles/
│       ├── part1/{terrain,rewards}.py     # 竞赛代理地形与 goal 奖励（从 black/ 拆出）
│       └── part2/{terrain,predicates,rewards,official_terrain_spec.json}
├── algorithms/{him,guarded_ppo,depth_warm_start}.py
├── utils/{knobs,export_policy,reward_safety,anomaly_probe}.py
├── external/policies/                     # 主办方官方策略（warm start/基线）
└── models/<round-id>/                     # 稳定完成一轮课程后的可部署权重 + manifest
```

## 3. 逐条处置（对应 Phase 1 审批卡 P1-01..P1-17）

| 卡 | 处置 |
|---|---|
| P1-02 | blackW `blackw_constants.py` + MJCF + 官方 mesh 入库；black 保持上游纯原生几何 |
| P1-03 | `control/physics/policy` 三频率字段（0.002/0.005/0.020），派生 `sim_decimation=10`、`deployment_decimation=4`，非法组合 fail-loud；env 变量统一 `RC_*`/`PART1_*`/`PART2_*`，39 项登记在 `utils/knobs.py`，未登记变量告警 |
| P1-04 | black 通用层按上游 `_configure_*` 划分原样迁入；26 个同源文件直接取；terminations 取 HIM 版轮速阈值拆分 |
| P1-05/06 | black HIM 集成 + `black/rl_cfg.py`（guard fail-loud、clip_actions、curriculum restore）迁入；HIM `class_name` 泄漏问题修复：仅显式设置 `RC_ALGORITHM` 时才覆盖算法类，避免 HIM runner 被降级为 base PPO |
| P1-07/08 | `algorithms/him` 用 HIM 守卫版（nan 跳过、std 清洗、anchor、estimator lr 解耦，全部改为非静默计数告警）；`guarded_ppo` 归位 `algorithms/`；`reward_safety`/`depth_warm_start` 迁入 |
| P1-09 | **方案 B**：`scripts/tools/gen_official_terrain_spec.py` 从官方 `map.xml` 生成 `official_terrain_spec.json`（含 map.xml sha256）；`profiles/part2/terrain.py` 全部尺寸读 spec；actions 采用 PPO 版 + HIM nan 守卫（计数告警） |
| P1-10 | blackW `env_cfgs.py` 拆出 `profiles/part2/{predicates,rewards}.py`；旧 proxy 任务（competition/platform/slope/trench 及 competition-him）不再注册 → 13 个 blackW 任务 |
| P1-11 | HIM 版 `blackw/{him,him_rl_cfg,him_runner}.py` 迁入（官方 TorchScript warm start、action guard、nefc/overflow 监视、std 冻结、nan_guard/nonfinite 终止） |
| P1-14 | GPU 队列基础设施（common/submit/on_finish）与 Part1/Part2 规范作业脚本迁入工作区 `jobs/`，env 改名、频率显式导出、`RC_ALGORITHM` 新路径 |
| P1-16 | mesh/官方策略入库；round-0 权重导入（`flat-ft-2500`、`comp_bc_v5`、`him_row0`）+ manifest |
| P1-12/13 | 导出链与工具脚本迁移：**未完成**（见 §6） |
| P1-17 | 结构解耦：`profiles/{part1,part2}` 已拆出；`common/` 抽取与 blackW 对 `black.env_cfgs` 的依赖消除**未完成**（见 §6） |

## 4. 等价性证据（L0/L1/L2）

**迁移前 golden 采集**（两个旧分支各自运行同一 dump 工具）：
`PYTHONPATH=src .venv/bin/python /tmp/dump_env_cfgs.py --out /tmp/golden_{ppo,him}_cfgs.json`
→ legacy/ppo 42 个任务、legacy/him 39 个任务（含 MjLab 自带 12 个）。

**迁移后对拍**（新仓 `scripts/checks/dump_env_cfgs.py`）：
- black 12 任务、blackW 13 任务全部注册并可构造；
- 与 golden_ppo 比较，过滤下列预期差异后 **0 unexpected diff**；
- 预期差异清单：`decimation 4→10`、`sim.mujoco.timestep 0.005→0.002`（频率契约）、模块路径 `profiles.*`（文件移动）、HIM `estimator_velocity.nan_policy disabled→sanitize` 与 `nan_guard.enabled`、`nonfinite_state` 终止（HIM 分支新增守卫）、dump 工具 property 表示、`plum.gap_before_exit 0.4→0.1`（官方几何修正：旧手抄值比官方 `map.xml` 大 0.3 m）。

**L2 GPU smoke**（新仓 pixi `train` 环境，16 envs × 2 iter，产物在 `artifacts/phase1/smoke/`）：
- `blackw-official` rc=0（PPO + Part2 判据/官方地形）；
- `black-flat-him` rc=0（HIMPPO + history/estimator 路径）；
- `blackw-official-him` rc=0（HIM + blackW signed wheel scale），HIM guard 打印 `nefc_max=32 overflow_nonzero=0 nonfinite_actions=0`。

**频率契约自检**：`RC_PHYSICS_DT=0.002/RC_CONTROL_PERIOD=0.005/RC_POLICY_PERIOD=0.020` → `sim_decimation=10, deployment_decimation=4`；非法组合（如 0.003）抛 `ValueError`。

## 5. 有意行为变更

1. `physics_dt` 训练默认 0.005→0.002（对齐官方 MJCF 与 judge；旧 job 已用 0.002/10，记录在此）；
2. env 变量前缀改名（`BLACKW_*` → `RC_*/PART1_*/PART2_*`），job 脚本同步，旧变量不再兼容；
3. HIM 任务新增 `nan_guard`/`nonfinite_state`（来自 HIM 分支的安全守卫，未在 PPO golden 中）；
4. 非 live proxy 任务（blackW competition/platform/slope/trench、competition-him）不再注册；
5. `plum.gap_before_exit` 按官方几何由 0.4 修正为 0.1；
6. HIMPPO 算法类不再被 `black_ppo_algorithm_kwargs()` 的默认 `class_name="PPO"` 覆盖（旧 PPO 分支引入的回归，HIM 路径此前无法通过 CLI 启动）。

## 6. P1-17 结构解耦（已完成）

目标结构 `common/`（训练/部署契约、PPO runner 配置、课程持久化、HIM runner 基类、通用 velocity 装配、course 机制） + `profiles/part1|part2`（赛项地形/判据/奖励） + `black/` `blackw/`（机器人契约与 task 注册）。

- 通用装配 `black/env_cfgs.py::_build_black_env_cfg` → `common/velocity_env.py::build_velocity_env_cfg`；`black_competition_env_cfg` 拆为 `profiles/part1/course.py`（地形）+ `common/course.py::apply_traversal_base`（命令/终止/奖励机制，Part2 任务复用）；
- `black_config.py`/`rl_cfg.py`/`curriculums.py`/`curriculum_checkpoint.py`/`him_runner.py`/`him_rl_cfg.py` → `common/`，全仓 import 重写；`symmetry.py` 仅在 mirror loss 开启时惰性导入（Black 专属契约）；
- blackW 任务基座由「import black 的 Part1 competition builder」改为「`common.velocity_env` + `common.course.apply_traversal_base` + Part2 6 行 × 0..1 难度 sweep」；`blackw-competition/platform/slope/trench` 等旧 proxy builder 不再注册；
- **直接依赖验收**：`blackw/` 对 `black/` 的 import 只剩 `black.him`（HIM observation/history/terminal 契约），满足审批卡 P1-17 的验收条件；`common/` 仍引用 black 的原生几何装配模块（`terrain/rewards/terminations/free_gravel`），彻底 robot-neutral 化留作 Phase 2 结构升级（不影响两机型×两赛项的接线）。

**P1-17 等价性证据**：解耦前后 37 个任务（12 black + 13 blackW + 12 mjlab 自带）`dump_env_cfgs` **逐字节一致**（唯一差异为 `blackw-flat` 的 Part1 代理地形按计划替换为通用 rough 地形，属结构解耦的有意变更，已在 golden 对比中单独确认）；runner 文件下移后再 dump 仍 `new == prev`；三条 smoke（`black-flat-him`、`blackw-official`、`blackw-official-him`）各 1 iter rc=0。

## 7. 新仓提交记录（migrate/phase1）

```text
028a657 feat(train): add blackW robot contract and official meshes (P1-02)
8f9742c feat(train): migrate black velocity/HIM stack with knobs registry and frequency contract (P1-03..P1-08)
4594479 feat(train): migrate blackW Part2 stack with official terrain spec and HIM guards (P1-09..P1-11)
ccaf3d8 fix(train): keep HIMPPO class for HIM runner cfg and repair split-module imports
21882ec feat(train): import round-0 deployable weights and official policies with manifests (P1-16)
1071403 feat(train): migrate training scripts and unify history exporter with deployment contract (P1-12, P1-13)
b812076 refactor(train): move shared config and PPO rl_cfg into tasks/velocity/common (P1-17 partial)
e9a8188 refactor(train): decouple robot contracts from event profiles; shared runner/config in common (P1-17)
```
