# Part 2 PPO/BC 线交接（2026-10-26，远程机夜间关机）

> 给新会话的入口文档。先读本文件，再按需读 [`part2-bc-policy-report.md`](part2-bc-policy-report.md)（结论/方法）、[`part2-ppo-training-history.md`](part2-ppo-training-history.md)（历史/证据）、[`part2-blind-depth-curriculum-plan.md`](part2-blind-depth-curriculum-plan.md)（模型分工与深度课程）。
> **边界**：本线只负责 PPO/BC 区域（见 §1）；HIM 线由另一个 Agent 负责，不要动它的仓库/任务/文档。

## 0. 一句话交接

- **当前交付不变**：`comp_bc_v5` 单份可部署权重，judge v5 下 **750/1300**（最好情况，4 次挑战期望 ≈743），已入库 `@20261024_blackw/models/comp_bc_v5/`；官方权重基线 660。最低档 5 类 judge 全部 8/8。
- **训练侧已修复**：success 谓词死代码、可刷分奖励、训练地形几何（坡道薄板 2cm 台阶 / ramp y 偏移）、训练物理与 judge 不一致（euler/elliptic/impratio=100；warp 不支持 PGS）、critic/optimizer 继承、entropy 推大 σ、`BLACKW_MAX_ROW` 未生效等（细节见归档 §11）。
- **待做**：① 上机先确认 `guard4_*` 长跑是否跑完并做 eval-gated 选点（关机前状态未知）；② 盲阶段冲 T30 壕沟 30cm/slope45/stairs30 专项（800–1200 iter 无果则转深度）；③ 深度 D0 可见性 + 部署链路（rl_sar 无 CNN 链路，是最大缺口）。
- **远程机今晚关机**：所有 run 的 checkpoint 每 50 iter 已落盘；上机后从最近 checkpoint 续训，不要从零重跑。`/tmp/part2_train/src` 可能丢失，代码快照在 `@20261024_blackw/training/`。

## 1. 工作边界（只在 PPO 区）

| 区域 | 我的范围（可写/可跑） | 另一 Agent 的 HIM 区（只读，不改不跑不杀） |
|---|---|---|
| 本地 | `@20261024_blackw/**`、`@20261019_locomotion/docs/training/part2-*.md`（我 authored 的 report/archive/plan/handoff/design）、`prep.d/results/blackw_official/**`、`prep.d/videos/comp_bc_v5/**` | `docs/training/blackw-*.md`、`cross-agent-comparison.md`、`him-part2-gate-curriculum-plan.md`、`nan-video-diagnosis.md`、`camera-depth.md`（HIM 的深度文档，我只引用不修改）、`docs/status.md`（共享，避免并发编辑）、`comp/` 下 RUN_LEDGER/findings/status 与 comp 脚本（别人在改） |
| 远程 | `bis-ms7e56:~/rc_work/part2_team_race/`（我的训练仓）+ `~/rc_work/models/` | `bis-ms7e56:~/rc_work/nwwolf_mjlab_training_release/`（HIM 训练仓） |
| GPU | 最多 2 个训练进程、显存 ≤8GB（见 §3.3 协议） | 同样 ≤8GB/2 进程；不要同时抢满 GPU |

## 2. 远程环境与当前状态

### 2.1 路径与启动方式

```bash
ssh bis-ms7e56.tail4413b4.ts.net
cd ~/rc_work/part2_team_race
export PYTHONPATH=$PWD/src MUJOCO_GL=egl
# 训练统一用:
.venv/bin/train <task_id> [--agent.*] [--env.*]
```

- 训练仓是 MjLab v1.6.0 + mujoco_warp；`.venv` 是共享环境的符号链接（不要动）。
- **本会话对训练代码的改动**（远程 `src/alldog_mjlab/tasks/velocity/blackw/`、`black/`）在本地有快照：`@20261024_blackw/training/{blackw,black}/*.py`。若远程被重置/换机，把快照文件拷回对应路径即可。
- 可用的 Part2 任务（注册在 `blackw/__init__.py`）：`blackw-platform-exact`、`blackw-wall-exact`、`blackw-slope-exact`、`blackw-stairs-exact`、`blackw-trench-exact`、`blackw-plum`、`blackw-official`（mixed 5 类）、`blackw-flat`。
- 关键脚本（远程 `scripts/agent_scripts/`）：`export_blackw_policy.py`、`diag_rollout.py`、`check_tier_success.py`、`check_tier_geometry.py`、`dump_terrain_png.py`、`raycast_terrain2.py` 等。

### 2.2 关键环境变量（我的线）

| 变量 | 作用/建议值 |
|---|---|
| `BLACKW_DEPLOY_SIM=1` | 训练物理对齐官方 judge（euler/elliptic/impratio=100/iterations=100/ccd=35；PGS 不支持用 newton 近似）。**所有 Part2 训练/门控都开** |
| `BLACKW_PHYSICS_DT=0.002`、`BLACKW_DECIMATION=10` | 部署契约（50Hz policy）；必须 |
| `BLACKW_NCONMAX=256`、`BLACKW_NJMAX=1024` | 半显存协议：512-env run ≈1.55GB（默认 1024/4096 是 3.83GB） |
| `BLACKW_DIFF_MIN/MAX` | 固定难度档（专项）；默认 0..1 |
| `BLACKW_MAX_ROW` | 随机初始 row 上限（0..num_rows-1） |
| `BLACKW_LR` / `BLACKW_ENTROPY_COEF` / `BLACKW_LEARN_STD` / `BLACKW_EPOCHS` / `BLACKW_MINIBATCHES` / `BLACKW_NORM_ADV_PER_MB` | PPO 超参；guarded 建议 lr 2e-5~5e-5、entropy 0、learn_std false、epochs 2、minibatches 8、norm=true |
| `BLACKW_ALGORITHM="alldog_mjlab.tasks.velocity.blackw.guarded_ppo:GuardedPPO"` + `BLACKW_GUARD_BLEND=0.9~0.95` | 权重信赖域微调（防 BC 退化）；`BLACKW_GUARD_FREEZE` 可冻结指定层 |
| `BLACKW_VX_MIN/MAX`、`BLACKW_LATERAL_CMD`、`BLACKW_YAW_CMD` | 命令范围（真实手柄线性映射 `joy_command_scale=1.5`；障碍建议 vx 0.2–0.8、vy±0.2、wz±0.3） |
| `BLACKW_CLEAR_W=60`、`BLACKW_PROGRESS_W=8`、`BLACKW_GOAL_W=0`、`BLACKW_CLIMB_W=0`、`BLACKW_PLUM_FOOT_W=3` | 奖励（success 一次性 / potential 差分 / 关掉可刷分项 / 梅花桩落足） |
| `BLACKW_SUCCESS_HOLD_STEPS=15` | 训练 success 谓词 hold（= judge 0.2+0.1s @50Hz） |

### 2.3 关机前的运行状态（上机先核对）

- `guard4_slope` / `guard4_stairs`（512 env）/ `guard4_plum`（256 env）：800 iter、blend 0.95、aligned physics、save 50。关机前最后 checkpoint 未确认（SSH 已不可达）。
- 已确认的中途结果（model_450/旧 pilot）：slope 只过 30°/35°（45° timeout），stairs 只过 15/20cm（30cm timeout）；盲阶段新档位尚未出现。
- 上机先跑：

```bash
ls -lt ~/rc_work/part2_team_race/logs/rsl_rl/black_velocity/ | grep guard4
ps aux | grep ".venv/bin/train" | grep -v grep
nvidia-smi --query-gpu=memory.used --format=csv,noheader
```

若 guard4 已跑完：直接做 §3 Step 1；若被关机打断：从最近 `model_XXX.pt` 续训（§3 Step 1 命令）。BC 起始 checkpoint 仍在 `logs/rsl_rl/black_velocity/bc_v5_guarded{,_s01}/model_0_bc_v5_guarded{,_s01}.pt`。

## 3. 明天执行清单（按顺序，先攻分数）

### 3.0 启动前检查（2 分钟）

- 显存/进程：`ssh` 上机后查 `nvidia-smi` 和训练进程数；本线 ≤2 进程、≤8GB。启动参数统一带 `BLACKW_NCONMAX=256 BLACKW_NJMAX=1024`。
- 训练物理/判据自检（不训练，~1 分钟）：

```bash
cd ~/rc_work/part2_team_race && export PYTHONPATH=$PWD/src MUJOCO_GL=egl
BLACKW_DEPLOY_SIM=1 .venv/bin/python scripts/agent_scripts/check_tier_success.py \
  --task blackw-stairs-exact --checkpoint logs/rsl_rl/black_velocity/bc_v5_guarded/model_0_bc_v5_guarded.pt \
  --difficulty 0.0 --vx 0.5 --envs 64 --episodes 2 --no-dr --exact-spawn --clean-obs
# 期望 platform/wall/slope/trench ≈100%；stairs 训练环境 55–75%（warp 无 PGS 的已知差距，judge 8/8）
```

### 3.1 Step 1：eval-gated 复核 guard4 长跑（~30–60 分钟）

1. 对每个 `guard4_*` 的 checkpoint（每 50 iter）连续 export + judge 评测；记录每个 checkpoint 的 slope 45/35、stairs 30/20/15、plum。
2. 具体命令（远程 export → 本地 judge）：

```bash
# 远程：导出 checkpoint
cd ~/rc_work/part2_team_race && export PYTHONPATH=$PWD/src MUJOCO_GL=egl
CK=$(ls logs/rsl_rl/black_velocity/2026-*guard4_slope/model_450.pt | head -1)
.venv/bin/python scripts/agent_scripts/export_blackw_policy.py --task blackw-slope-exact \
  --checkpoint "$CK" --out ~/rc_work/models/guard4_slope_450/policy.pt

# 本地：拷入策略目录 + 配置（复制 obstacle/config.yaml，改 model_path），再跑 judge
pixi run python @20261024_blackw/scripts/eval_blackw_part2.py \
  --policy @20261024_blackw/ws/src/rl_sar_blackw/policy/blackW/guard4_slope_450 \
  --only slope_45deg --only slope_35deg --command 0.3 0 0 --attempts 4
```

3. 判定：若所有 checkpoint 都不过 45°/30cm → 盲阶段收益到头，进入 Step 2（T30 专项门槛）和 Step 3（B0 稳定性）；若某个 checkpoint 过 45° → 立刻做 4 次稳定性复测 + 录制视频给用户复核。

### 3.2 Step 2：T30 壕沟 30cm 盲专项（B1，1–2 小时，最高优先级分数）

**依据**：槽宽 0.3m > 轮径 0.206m，judge 只允许轮底下沉 0.103m → 必须抬轮/腾空；盲感知只能靠"搏一把"的时序/反射（能否学到是门槛实验）。训练环境已与 judge 同源判据（轮沉即终止）。

```bash
cd ~/rc_work/part2_team_race && export PYTHONPATH=$PWD/src MUJOCO_GL=egl
nohup env BLACKW_DEPLOY_SIM=1 BLACKW_DIFF_MIN=1.0 BLACKW_DIFF_MAX=1.0 \
  BLACKW_NCONMAX=256 BLACKW_NJMAX=1024 \
  BLACKW_PHYSICS_DT=0.002 BLACKW_DECIMATION=10 \
  BLACKW_LR=4e-5 \
  BLACKW_ALGORITHM="alldog_mjlab.tasks.velocity.blackw.guarded_ppo:GuardedPPO" \
  BLACKW_GUARD_BLEND=0.95 BLACKW_GUARD_LOG=1 BLACKW_ENTROPY_COEF=0.0 BLACKW_LEARN_STD=false \
  BLACKW_EPOCHS=2 BLACKW_MINIBATCHES=8 BLACKW_NORM_ADV_PER_MB=true \
  BLACKW_VX_MIN=0.2 BLACKW_VX_MAX=0.5 BLACKW_LATERAL_CMD=0.05 BLACKW_YAW_CMD=0.05 \
  BLACKW_CLEAR_W=60.0 BLACKW_PROGRESS_W=8.0 BLACKW_GOAL_W=0.0 BLACKW_CLIMB_W=0.0 \
  .venv/bin/train blackw-trench-exact \
  --agent.resume True --agent.load-run bc_v5_guarded --agent.load-checkpoint model_0_bc_v5_guarded.pt \
  --agent.max-iterations 400 --env.scene.num-envs 512 \
  --agent.run-name t30_blind_v0 --agent.logger tensorboard --agent.save-interval 50 \
  > /tmp/t30_blind_v0.log 2>&1 &
```

- 观测指标：`part2_failure`（轮沉）占比应下降、`part2_clear` 出现；每 50 iter 导出→judge `trench_30cm` 4 次尝试。
- **门槛**：400 iter 内若 `trench_30cm` 4 次仍 0 且轮沉率不降 → 判盲不可行，转 Step 5 深度路线；若有 1–2 次通过 → 继续到 800–1200 iter 并加起点/速度随机化。

### 3.3 Step 3：B0 主线稳定性（低成本，1 小时；也可放夜里跑）

目标：把 wall40 从 3/4、stairs20 从 2/4 提到稳定 4/4（期望分 743 → 750 附近）。

- `blackw-wall-exact`：`BLACKW_DIFF_MIN=BLACKW_DIFF_MAX=1.0`（40cm）、`BLACKW_VX_MIN=0.5 BLACKW_VX_MAX=0.8`、guarded lr 2e-5、blend 0.9、300–500 iter、save 50；
- `blackw-stairs-exact`：`BLACKW_DIFF_MIN=BLACKW_DIFF_MAX=0.5`（20cm 步高，总高 1.2m）、vx 0.6–0.8 常数、同 guarded 参数；
- 每 50 iter 导出 → judge 对应档 4 次尝试 ×2 轮；稳定 4/4 才替换 profile；否则保留 comp_bc_v5。
- 若时间紧：用 `--agent.max-iterations 500 --agent.save-interval 50` 夜间跑，明早看结果。

### 3.4 Step 4：s45 / st30 门槛实验（可选，各 1 小时）

- slope：`blackw-slope-exact` + `BLACKW_DIFF_MIN=BLACKW_DIFF_MAX=1.0`（45°）、vx 0.3–0.6、guarded blend 0.95、400–800 iter；judge 45° 4 次。
- stairs30：`BLACKW_DIFF_MIN=BLACKW_DIFF_MAX=1.0`（30cm）、vx 0.6–0.8、400–800 iter；judge 30cm 4 次。
- 若仍 0 → 明确写进文档"盲阶段上限"，把预算转深度。

### 3.5 Step 5：深度 D0（与 Step 2/3 并行，1–2 小时）

1. 把 `camera-depth.md` 里已有的 `CameraSensorCfg` + `camera` obs group + `CNNModel` 配置移植到 `part2` exact/mixed 任务（**只读参考 HIM 的深度代码，不改其文件**）。
2. 渲染 trench30/plum/stairs 的深度图，确认 3.8m 处 0.1/0.2/0.3m 槽、桩间隙可分辨（48×64 可能只有 1–3 像素；不够就升分辨率或做 depth→ego 高度图）。
3. 部署侧：在 rl_sar 的 MuJoCo 场景加一个前向深度相机渲染 demo（不需要 CNN），先验证渲染幅面/时间戳；CNN 推理链路后续做（见 plan §4.3 D5）。
4. 产出：一张 depth vs RGB/几何对比图 + "槽是否可见"结论；若不可见，先解决分辨率/ego 高度图，再谈 D1/D2。

## 4. 已知坑与不要重复的结论

1. **warp 无 PGS**：训练环境 stairs 成功率天然偏低（55–75% vs judge 100%）；门控/判定以 **judge** 为准，warp 只当严格下界。
2. **不要用 `Episode_Termination/*` 当日志成功率**：它是计数型指标，可能 >1；用 `check_tier_success.py` 或 judge 数真实通过率。
3. **不要状态式 shaping**：`competition_goal` 每步奖励、状态式 progress/climb 都会让策略原地刷分；只用 potential 差分 + 一次性 success。
4. **不要把"训练环境 0 success"当学不会**：先检查谓词/物理是否对齐（本会话曾因死代码+物理不一致误判，见归档 §11）。
5. **不要直接 full-resume 微调 BC**：旧 critic/optimizer/iter 会带偏；用 `make_bc_checkpoint.py --reset-trainer` + GuardedPPO + 冻结 σ。
6. **不要动 HIM 区**：对方仓的 `blackw-platform-exact-him` 继承同一套 `_part2_terrain_state`，其"0 success gate"在对方仓未修；发现类似问题只提醒，不改其仓。
7. Type-B Codex 审计不可用（`comp/audits/2026-10-25-judge-v5-G1-REVIEW_UNAVAILABLE.md`），分数是 executor 证据；不要对外声称"已审计"。

## 5. 文档地图

| 文档 | 用途 |
|---|---|
| 本文件 | 交接：远程状态、明天步骤、命令、边界、开放问题 |
| [`part2-bc-policy-report.md`](part2-bc-policy-report.md) | 主报告：judge v5、BC/DAgger、评测结果、参考文献、局限 |
| [`part2-ppo-training-history.md`](part2-ppo-training-history.md) | 归档：bug 审计/修复证据、最低档/档位结构验证、显存实测、早期 specialist 记录 |
| [`part2-blind-depth-curriculum-plan.md`](part2-blind-depth-curriculum-plan.md) | 模型分工（主线 M0 + T30/S45/St30/P）、盲课段 B0–B4、深度 BeamDojo 课程 D0–D5 |
| [`part2-failure-vs-reward-design.md`](part2-failure-vs-reward-design.md) | termination vs reward shaping 的原则与文献 |
| `@20261024_blackw/README.md` | 部署栈、评测命令、权重/脚本索引 |
| `@20261024_blackw/training/README.md` | 训练侧代码快照说明（与远程仓对应关系） |

## 6. 开放问题（新会话开始可先问用户）

1. 远程机今晚关机后，明天是否允许我从最近 guard4 checkpoint 继续（而不是重开 guard4）？
2. 11-01 前优先保分数（只跑 Step 1–3 + 录视频）还是同时推进深度 D0（我建议并行走 D0，但不影响盲线）？
3. 课程门控的随机化范围是否按本文件 §3.3/plan 的数值执行（初始 root x±0.10/y±0.15/yaw±0.05；指令 vx 0.2–0.8、vy±0.2、wz±0.3；满杆 1.5 只做上界测试）？
4. 是否要提醒 HIM 线同步"exact-key 死代码"修复（我未改对方仓；不影响我的交付）？
5. 深度部署（rl_sar 加 MuJoCo 相机渲染 + CNN 推理）是否 11-01 前要做；若来不及，深度是否只作为答辩/后续内容？

## 7. 快速命令卡片

```bash
# 远程训练（guarded，通用模板）
ssh bis-ms7e56.tail4413b4.ts.net
cd ~/rc_work/part2_team_race && export PYTHONPATH=$PWD/src MUJOCO_GL=egl
nohup env BLACKW_DEPLOY_SIM=1 BLACKW_NCONMAX=256 BLACKW_NJMAX=1024 \
  BLACKW_PHYSICS_DT=0.002 BLACKW_DECIMATION=10 BLACKW_LR=4e-5 \
  BLACKW_ALGORITHM="alldog_mjlab.tasks.velocity.blackw.guarded_ppo:GuardedPPO" \
  BLACKW_GUARD_BLEND=0.95 BLACKW_ENTROPY_COEF=0.0 BLACKW_LEARN_STD=false \
  BLACKW_EPOCHS=2 BLACKW_MINIBATCHES=8 BLACKW_NORM_ADV_PER_MB=true \
  BLACKW_CLEAR_W=60.0 BLACKW_PROGRESS_W=8.0 BLACKW_GOAL_W=0.0 BLACKW_CLIMB_W=0.0 \
  .venv/bin/train <task> --agent.resume True --agent.load-run <run> --agent.load-checkpoint <model_X.pt> \
  --agent.max-iterations 400 --env.scene.num-envs 512 --agent.run-name <new-run> \
  --agent.logger tensorboard --agent.save-interval 50 > /tmp/<new-run>.log 2>&1 &

# 远程导出 + 本地 judge（以 slope 为例）
# （远程）CK=$(ls logs/rsl_rl/black_velocity/2026-*<run>/model_<iter>.pt | head -1)
# （远程）.venv/bin/python scripts/agent_scripts/export_blackw_policy.py --task blackw-slope-exact \
#   --checkpoint "$CK" --out ~/rc_work/models/<name>/policy.pt
# （本地）mkdir -p .../policy/blackW/<name> && scp 远程 policy.pt 进去，
#   再复制 policy/blackW/obstacle/config.yaml -> <name>/config.yaml 并改 model_path=<name>/policy.pt
pixi run python @20261024_blackw/scripts/eval_blackw_part2.py \
  --policy @20261024_blackw/ws/src/rl_sar_blackw/policy/blackW/<name> \
  --only slope_45deg --only slope_35deg --command 0.3 0 0 --attempts 4

# 最终 profile 复测（comp_bc_v5 当前 750；P=@20261024_blackw/ws/src/rl_sar_blackw/policy/blackW/comp_bc_v5）
P=@20261024_blackw/ws/src/rl_sar_blackw/policy/blackW/comp_bc_v5
pixi run python @20261024_blackw/scripts/eval_blackw_part2.py --policy $P --only high_platform_40cm --command 0.5 0 0 --attempts 4
pixi run python @20261024_blackw/scripts/eval_blackw_part2.py --policy $P --only high_wall_40cm --command 0.65 0 0 --slow-from-x 1.6 --cmd-slow 0.35 --attempts 4
pixi run python @20261024_blackw/scripts/eval_blackw_part2.py --policy $P --only slope_35deg --command 0.3 0 0 --attempts 4
pixi run python @20261024_blackw/scripts/eval_blackw_part2.py --policy $P --only stairs_20cm --command 0.75 0 0 --slow-from-x 1.1 --cmd-slow 0.45 --attempts 4
pixi run python @20261024_blackw/scripts/eval_blackw_part2.py --policy $P --only trench_20cm --command 0.3 0 0 --attempts 4
```
