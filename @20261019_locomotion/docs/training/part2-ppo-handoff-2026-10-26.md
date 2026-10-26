# Part 2 PPO/BC 线交接（2026-10-26，远程机夜间关机）

> 给新会话的入口文档。先读 §0、§3（课程规则）、§4（明天步骤），再按需读 [`part2-bc-policy-report.md`](part2-bc-policy-report.md)（结论/方法）、[`part2-ppo-training-history.md`](part2-ppo-training-history.md)（历史/证据）、[`part2-blind-depth-curriculum-plan.md`](part2-blind-depth-curriculum-plan.md)（模型分工与深度课程）。
> **边界**：本线只负责 PPO/BC 区域（见 §1）；HIM 线由另一个 Agent 负责，不要动它的仓库/任务/文档。

## 0. 一句话交接

- **2026-10-26 复核修正（先读）**：guard4 三个 800-iter run 已确认真跑完，但复核**无可捞档位**（15 个 checkpoint 的 judge：slope45 0/60、stairs30 4/60、plum 0；±0.1 m 抖动复核同结论，证据见 [`part2-ppo-training-history.md`](part2-ppo-training-history.md) §14）；**slope45 稳态爬坡静态摩擦零余量**（官方 judge 场景 μ=1.0 = tan45°；μ=1.5 时同一权重可爬到 root z≈2.08 m），**但按用户 2026-10-26 第二轮指示不判死**：μ=1.2 训练只作诊断、评测同时报 μ=1.2 与 1.0，冲坡可把等效需求降到 0.89–0.94 且不超关节速度限幅，后期可试 μ 递减课程。**盲侧当前阶段目标仍按 850 计**（当前 750 的缺口 = stairs30 +100），全体实际上限 1200/1300。今日起的执行顺序、GPU 队列协议与待确认项见 [`part2-ppo-execution-plan-2026-10-26.md`](part2-ppo-execution-plan-2026-10-26.md)（本文件 §4 的"明天清单"以其为准）。
- **当前交付不变**：`comp_bc_v5` 单份可部署权重，judge v5 下 **750/1300**（最好情况，4 次挑战期望 ≈743），已入库 `@20261024_blackw/models/comp_bc_v5/`；官方权重基线 660。最低档 5 类 judge 全部 8/8。
- **训练目标与原则（最重要，先读 §3）**：目标是训练出**一个鲁棒的策略模型**，用 mjlab 的地形难度机制 + **逐档鲁棒性 gate 逐级提升**（单谱系、串行 stage、每档 gate 通过才升档、从上一档 best checkpoint 热启动）。**gate 标准（用户 2026-10-26 确认）**：简单档（S0–S2）judge **16/16**、较难档（S3–S6 及专项最高档）judge **≥8/8**，且 gate 必须包含合理的初始状态随机化 + 3 档速度指令随机化（见 §3.4）。**旧版"把不同难度混在一起并行训练"（`BLACKW_MAX_ROW` 随机混合 row 0..5）是严重错误，已废弃，不要再这样训**；那是做多难度对比实验的做法，不是课程学习，也不可能得到逐档鲁棒的模型。
- **训练侧已修复**：success 谓词死代码、可刷分奖励、训练地形几何（坡道薄板 2cm 台阶 / ramp y 偏移）、训练物理与 judge 不一致（euler/elliptic/impratio=100；warp 不支持 PGS）、critic/optimizer 继承、entropy 推大 σ、`BLACKW_MAX_ROW` 未生效等（细节见归档 §11）。
- **待做**：① 上机先确认 `guard4_*` 长跑是否跑完并做 eval-gated 选点（关机前状态未知）；② 用 §3/§4 的分档 gate 课程推进 M0 主线：**盲侧目标 950 分**（当前 750，缺口只有 slope45 +100、stairs30 +100，这两项继续盲训，§4.2）；③ **深度部署必须开始做**（用户 2026-10-26 确认）：深度依赖只有 **trench30 + 梅花桩**（盲侧先做到 ≥855/950），D0 可见性 + rl_sar 深度渲染/CNN 推理链路当天开工（§4.3），D1/D2/D3 专项按 8/8 gate（§4.4）。
- **壕沟 30cm 语义（行动前必读）**：盲策略的"前轮突然降低"无法区分窄槽/台阶下沿/高台边缘；且 30cm 槽宽 0.30 m > 前后轮触地跨距一半 0.213 m（也 > 轮径 0.206 m）→ **盲不可达，不做盲试**，直接进深度专项（§4.4）；trench 20cm 盲已实测 4/4，保留在盲侧。
- **11-01 前优先级（用户 2026-10-26 确认）**：M0 逐档 gate 推进（盲侧 950 目标）+ 深度部署 D0/D1 **并行**（不是只保分数）。
- **远程机今晚关机、已启用 GPU 队列**：上机先查看 GPU 队列状态再提交；所有 run 的 checkpoint 每 50 iter 已落盘，从最近 checkpoint 续训，不要从零重跑。`/tmp/part2_train/src` 可能丢失，代码快照在 `@20261024_blackw/training/`。

## 1. 工作边界（只在 PPO 区）

| 区域 | 我的范围（可写/可跑） | 另一 Agent 的 HIM 区（只读，不改不跑不杀） |
|---|---|---|
| 本地 | `@20261024_blackw/**`、`@20261019_locomotion/docs/training/part2-*.md`（我 authored 的 report/archive/plan/handoff/design）、`prep.d/results/blackw_official/**`、`prep.d/videos/comp_bc_v5/**` | `docs/training/blackw-*.md`、`cross-agent-comparison.md`、`him-part2-gate-curriculum-plan.md`、`nan-video-diagnosis.md`、`camera-depth.md`（HIM 的深度文档，我只引用不修改）、`docs/status.md`（共享，避免并发编辑）、`comp/` 下 RUN_LEDGER/findings/status 与 comp 脚本（别人在改） |
| 远程 | `bis-ms7e56:~/rc_work/part2_team_race/`（我的训练仓）+ `~/rc_work/models/` | `bis-ms7e56:~/rc_work/nwwolf_mjlab_training_release/`（HIM 训练仓） |
| GPU | **算力机已启用 GPU 队列**：训练任务按队列提交；上机先查看队列/GPU 状态（`nvidia-smi`、机器上的队列工具/说明），按队列规则使用，**不再需要手动限制半显存** | 同样按 GPU 队列使用；不要绕开队列直接抢卡 |

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
| `BLACKW_DIFF_MIN/MAX` | **课程 stage 的唯一难度开关**：b 固定为同一值 r → 整个 batch 都在同一难度行上训练（M0 主线的 stage 定义见 §3/§4.3） |
| `BLACKW_MAX_ROW` | 仅用于调试/复现旧实验：随机初始 row 上限。**用它随机混合多难度 = 旧版错误做法，禁止用于目标训练**（见 §3.3） |
| `BLACKW_NCONMAX` / `BLACKW_NJMAX` | 可选性能/显存参数（默认 1024/4096）；GPU 队列下无需为共享显存压缩，保留默认或按队列限额调整 |
| `BLACKW_LR` / `BLACKW_ENTROPY_COEF` / `BLACKW_LEARN_STD` / `BLACKW_EPOCHS` / `BLACKW_MINIBATCHES` / `BLACKW_NORM_ADV_PER_MB` | PPO 超参；guarded 建议 lr 2e-5~5e-5、entropy 0、learn_std false、epochs 2、minibatches 8、norm=true |
| `BLACKW_ALGORITHM="alldog_mjlab.tasks.velocity.blackw.guarded_ppo:GuardedPPO"` + `BLACKW_GUARD_BLEND=0.9~0.95` | 权重信赖域微调（防 BC 退化）；`BLACKW_GUARD_FREEZE` 可冻结指定层 |
| `BLACKW_VX_MIN/MAX`、`BLACKW_LATERAL_CMD`、`BLACKW_YAW_CMD` | 命令范围（真实手柄线性映射 `joy_command_scale=1.5`；障碍建议 vx 0.2–0.8、vy±0.2、wz±0.3） |
| `BLACKW_CLEAR_W=60`、`BLACKW_PROGRESS_W=8`、`BLACKW_GOAL_W=0`、`BLACKW_CLIMB_W=0`、`BLACKW_PLUM_FOOT_W=3` | 奖励（success 一次性 / potential 差分 / 关掉可刷分项 / 梅花桩落足） |
| `BLACKW_SUCCESS_HOLD_STEPS=15` | 训练 success 谓词 hold（= judge 0.2+0.1s @50Hz） |

### 2.3 关机前的运行状态（上机先核对）

- **2026-10-26 08:30 已核对（结论）**：`guard4_slope`/`guard4_stairs`（512 env）/`guard4_plum`（256 env）三个 run 全部完成 800 iter，`model_799.pt` 已落盘（10-25 23:09），GPU 空闲；按 §4 Step 1 导出+judge 复核后**无可捞档位**（见 §0 修正），结论与证据归档 [`part2-ppo-training-history.md`](part2-ppo-training-history.md) §14，不再续训。
- 原始记录：`guard4_*` 800 iter、blend 0.95、aligned physics、save 50；中途快照（model_450/旧 pilot）slope 只过 30°/35°（45° timeout），stairs 只过 15/20cm（30cm timeout）。
- 上机核对命令（GPU 队列状态下先看队列，再决定是否提交）：

```bash
ls -lt ~/rc_work/part2_team_race/logs/rsl_rl/black_velocity/ | grep guard4
ps aux | grep ".venv/bin/train" | grep -v grep
nvidia-smi
# 按机器说明查看 GPU 队列（队列查看/提交命令以机器上的工具为准）
```

若 guard4 已跑完：直接做 §4 Step 1；若被关机打断：从最近 `model_XXX.pt` 续训（§4 Step 1 命令）。BC 起始 checkpoint 仍在 `logs/rsl_rl/black_velocity/bc_v5_guarded{,_s01}/model_0_bc_v5_guarded{,_s01}.pt`。

## 3. 课程实施规则（必读：单谱系、逐档、鲁棒 gate）

### 3.1 mjlab 课程机制怎么用

MjLab 本身有课程基础设施：`TerrainGeneratorCfg.difficulty_range` 定义每类地形的难度区间的连续难度行（terrain rows）、`curriculum` manager 管理地形等级、内置 `terrain_levels_vel` term 在**按行走距离**达到阈值时提升行等级。但 `terrain_levels_vel` 的晋升判据（距离）**不适合 goal 终止的障碍 episode**（走一半就 goal/失败，距离信号无效；stage-3 曾出现 4 列长期 level 0），所以本任务在训练里 `pop("terrain_levels")`，用**同一套 terrain rows + 自己的 success-gated 晋升**实现 mjlab 课程语义：

- **stage 就是固定难度行**：`difficulty_range=(r,r)`（env 里用 `BLACKW_DIFF_MIN=BLACKW_DIFF_MAX=r`），整个 batch 同一难度，不允许同 batch 混多个难度；
- **晋升判据换成鲁棒性 gate**：每 stage 训练后做 canonical + 随机化评测（§3.4），通过才升到下一 stage 的 r；
- **单谱系**：stage k+1 从 stage k 的 best checkpoint 热启动（`--agent.resume True --agent.load-run <stage_k_run> --agent.load-checkpoint <best>`），全程只有一个模型谱系，最终得到**一个鲁棒策略**；
- 以后若想把晋升做成 mjlab 原生 curriculum term：新增一个 `terrain_levels_success_gated`（按 `part2_success` 计数/成功率提升行等级，失败降级），而不是改回距离判据。当前先用手工 stage + 外部 gate（简单、可复现、易审计）。

### 3.2 stage 定义与晋升流程（M0 主线）

M0 = `blackw-official` mixed 任务（5 类可滚障碍同场，单策略覆盖"普通行走 + 可通行障碍"）。难度行 r ∈ [0,1] 按官方档位对应的连续难度取 stage（平台 h=0.1+0.3r、墙 h=0.1+0.3r、坡 20+25r°、楼梯总高 0.6+1.2r、沟槽宽 0.1+0.2r）：

| stage | r | 平台 | 墙 | 坡 | 楼梯 | 沟槽 | 新增官方档（gate 目标） |
|---|---|---|---|---|---|---|---|
| S0 | 0.00 | 10cm | 10cm | 20° | 10cm | 10cm | 全部最低档（已过） |
| S1 | 0.25 | 17 | 17 | 26° | **15cm** | 15 | stairs 15cm |
| S2 | 1/3 | **20cm** | **20cm** | 28° | 17 | 17 | platform 20 / wall 20 |
| S3 | 0.40 | 22 | 22 | **30°** | 18 | 18 | slope 30° |
| S4 | 0.50 | 25 | 25 | 32° | **20cm** | **20cm** | stairs 20 / trench 20 |
| S5 | 0.60 | 28 | 28 | **35°** | 22 | 22 | slope 35° |
| S6 | 2/3 | **30cm** | **30cm** | 37° | 24 | 23 | platform 30 / wall 30 |
| S7 | 1.00 | **40cm** | **40cm** | **45°** | **30cm** | **30cm** | 不用于 M0 训练（trench30 盲不可达、混入会稀释样本）；slope45/stairs30 走 exact 盲专项（§4.2） |

**gate 次数标准**：简单档（S0–S2）每档 judge **16/16**；较难档（S3–S6 及盲/深度专项最高档）judge **≥8/8**（都要 100%，不是 3/4）。每次 attempt 随机采样初始状态与 3 档速度指令之一（§3.4），每个指令档都必须全过。

流程（每个 stage）：① 判定起点：先用 comp_bc_v5 跑一遍 gate（§3.4），从**最低的未通过 stage** 开始，不重复训练已过的档；② 在 stage r 训练 200–400 iter（guarded，save 50，每 50 iter export→judge）；③ 做 gate：该 stage "新增官方档"及以下都要按上述次数标准全过（judge 16/16 或 ≥8/8，3 档指令每档全过）；④ 过 → 记录 `stage_best`，升下一 stage 热启动；不过 → 继续当前 stage（降 lr/换 seed），或停在上一 stage 并记录（改用 exact 专项继续，见 §4.2）。M0 主线到 **S6 封顶**（S7 含盲不可达的 trench30，不做 mixed S7）；**slope45/stairs30 是盲可训练目标，用 exact 盲专项继续训到过（8/8 gate，§4.2）**；**trench30 盲不可达**（gap>0.213 m），不做盲试，交深度（§4.4）。

### 3.3 明令禁止的做法（旧版错误）

1. **禁止同一 batch 混合多个难度**（`BLACKW_MAX_ROW` 随机 row 0..5、`DIFF_MIN=0/MAX=1` 同时训）——这是"多难度对比实验"，不是课程学习；学出来的是各难度平均行为，低档不稳、高档学不出。目标训练只能用"固定 r 的 stage + gate 晋升"。
2. **禁止跳过 gate 直接升档**：每一档必须记录 gate 证据（judge JSON + 随机化成功率），否则不允许进入下一 stage。
3. **禁止把不同障碍的专项混成一个 batch 来"顺便"练**：M0 只在同一 stage 难度上混 5 类可滚障碍；壕沟 30cm（gap>支撑跨距一半）盲不可达 → 直接深度（§4.4），不要在 M0 的 S7 里硬混。

### 3.4 gate 判定细节（每 stage 必做；用户 2026-10-26 确认的标准）

- **档位分级**：简单档 = S0–S2（最低 3 个 stage，全部障碍的低档）；较难档 = S3–S6 及盲/深度专项最高档（统一 ≥8/8）。
- **authoritative judge gate（必须全过，不留失败）**：
  - 简单档每个目标档 **16/16**；较难档每个目标档 **≥8/8**（8 次也要求 100%；不要 3/4、2/4 这类"勉强过"）。
  - 16 次按 3 个指令档平衡分配（约 6/5/5），8 次约 3/3/2；**每个指令档都必须 100% 通过**，任一指档有失败则 gate 不通过。
  - 每个 attempt 随机采样：初始状态（root x±0.10 m、y±0.15 m、yaw±0.05 rad，关节 offset/速度与现有 reset 随机化一致）+ 3 档速度指令之一；judge 场景与 judge v5 一致（官方几何、0.002s 物理）。
  - **3 档速度指令（符合真实手柄线性映射）**：`joy_command_scale=1.5` 满杆可达 ±1.5 m/s，实际障碍操作范围取名义速度的 **0.6× / 1.0× / 1.3×**（clamp 0.2–1.1 m/s；wall/stairs 的 `--slow-from-x` schedule 按同一比例缩放）；另加 vy±0.2、wz±0.3 小随机。每个 attempt 固定一档（模拟操作手一次给一个速度），若想更严可选在 attempt 内按 0.5 s 间隔在 3 档间跳变。
  - 参考名义速度（profile）：platform 0.5、wall 0.65→0.35（x=1.6m 后）、slope 0.3、stairs 0.75→0.45（x=1.1m 后）、trench 0.3；3 档即各 ×0.6/×1.0/×1.3（如 platform 0.3/0.5/0.65；stairs 0.45/0.75/0.95 起步，0.27/0.45/0.59 慢段）。
  - **评测工具需要小扩展**：现有 `eval_blackw_part2.py` 只有 `--attempts/--command/--jitter-y`；下一步给它加 `--jitter-x/--jitter-yaw/--command-set`（或新写 `gate_stage.py` 包装），一次跑 16/8 次并输出每档/每指令的通过矩阵到 `prep.d/results/blackw_official/stage_gates/<stage>.json`。
- **robustness 辅助检查（诊断用，不是 gate 判据）**：部署对齐训练环境（`BLACKW_DEPLOY_SIM=1`）用 `check_tier_success.py`，同一初始状态随机化 + 3 档指令、每档 ≥100 episodes，报告成功率；warp 无 PGS 时 stairs 会偏低，只作下界与回归监控，**不能**代替 judge gate。
- **判定以 judge 为准**：judge 通过矩阵是唯一晋升依据；warp 训练环境与 judge 不一致时先查谓词/物理口径（归档 §11/§12）。
- 每次 gate 产物落盘 + 一句话结论，供交接与答辩引用。

## 4. 明天执行清单（按顺序，先攻分数）

### 4.0 启动前检查（2 分钟）

- **GPU 队列**：上机查 `nvidia-smi` 和机器上的 GPU 队列工具/说明；按队列提交训练（排队期间先做 eval/export 等 CPU/本地工作），不用再手动限显存。
- 训练物理/判据自检（不训练，~1 分钟）：

```bash
cd ~/rc_work/part2_team_race && export PYTHONPATH=$PWD/src MUJOCO_GL=egl
BLACKW_DEPLOY_SIM=1 .venv/bin/python scripts/agent_scripts/check_tier_success.py \
  --task blackw-stairs-exact --checkpoint logs/rsl_rl/black_velocity/bc_v5_guarded/model_0_bc_v5_guarded.pt \
  --difficulty 0.0 --vx 0.5 --envs 64 --episodes 2 --no-dr --exact-spawn --clean-obs
# 期望 platform/wall/slope/trench ≈100%；stairs 训练环境 55–75%（warp 无 PGS 的已知差距，judge 8/8）
```

### 4.1 Step 1：eval-gated 复核 guard4 长跑（**2026-10-26 已完成，无可捞档位**）

> 结论：三个 run 均完成 800 iter；导出 5 checkpoint/run 后 judge 复核 slope45 0/16、stairs30 0/15、plum 0；±0.1 m 抖动 sweep 复核同样全挂。guard4 不续训，直接进入 §4.2（stairs30 专项）+ §4.3（深度 D0）。执行细节与命令保留如下以便复现。

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

3. 判定：若某个 checkpoint 已过 45°/stairs30 → 立刻做完整 8/8 gate + 录视频复核，并把该权重视为最高档盲专项候选；若都不过 → 进入 §4.2（盲侧逐档课程）与 §4.3（深度 D0）。

### 4.2 Step 2：M0 主线逐档 gate（盲侧目标：750 → 850，2026-10-26 修正）

> **2026-10-26 修正**：slope45 被 judge 物理摩擦上限判死（μ=1.0、tan45°=1.0 零余量；证据 [`part2-ppo-training-history.md`](part2-ppo-training-history.md) §14.2），盲侧可拿分集合修正为 platform40 200 + wall40 200 + slope35 100 + stairs20 100 + trench20 150 = **750**，再加 **stairs30（+100）→ 850**；深度依赖仍为 trench30（+150）与梅花桩（+200）。今日起的执行顺序与算力分配见 [`part2-ppo-execution-plan-2026-10-26.md`](part2-ppo-execution-plan-2026-10-26.md)。
>
> 以下为原计划（目标数字按上述修正理解；"slope45 盲专项"不再执行）。

**盲可拿分集合（2026-10-26 修正后）**：platform40 200 + wall40 200 + slope35 100 + stairs20 100 + trench20 150 + stairs30 100 = **850**；深度依赖 = trench30（+150，相对 trench20）与梅花桩（+200）。
- 当前 750；盲侧缺口 = **stairs30（+100）**，用 `blackw-stairs-exact` 固定 r=1.0 的盲专项训练；slope45 因摩擦上限不再训练；
- 目标：盲侧先到 **850**（85%，也是实际天花板），深度项另行争取。

流程：① placement：用 comp_bc_v5 逐 stage 跑 gate（§3.4），从**最低未通过 stage** 开始；② 每 stage 固定 r 训练 200–400 iter（guarded，save 50，每 50 iter export→judge）；③ gate（S0–S2 每档 16/16，S3–S6 每档 ≥8/8，3 档指令每档全过 + 初始状态随机化）→ 过则记录 `stage_best` 热启动下一 stage；④ M0 到 **S6 封顶**；盲侧剩余 100 分（stairs30）用 `blackw-stairs-exact` **固定 r=1.0 的盲专项**训练 400–800 iter（8/8 gate），通过后按切换策略使用（规则允许；若需单模型再 DAgger 合并回 M0）；**不要转深度**、也不要跑 mixed S7（会混入盲不可达的 trench30）。

```bash
# 通用模板（把 STAGE_R / PREV_RUN / PREV_CK / RUN 名替换；按 GPU 队列提交）
nohup env BLACKW_DEPLOY_SIM=1 BLACKW_DIFF_MIN=<STAGE_R> BLACKW_DIFF_MAX=<STAGE_R> \
  BLACKW_PHYSICS_DT=0.002 BLACKW_DECIMATION=10 BLACKW_LR=4e-5 \
  BLACKW_ALGORITHM="alldog_mjlab.tasks.velocity.blackw.guarded_ppo:GuardedPPO" \
  BLACKW_GUARD_BLEND=0.95 BLACKW_ENTROPY_COEF=0.0 BLACKW_LEARN_STD=false \
  BLACKW_EPOCHS=2 BLACKW_MINIBATCHES=8 BLACKW_NORM_ADV_PER_MB=true \
  BLACKW_VX_MIN=0.3 BLACKW_VX_MAX=0.8 BLACKW_LATERAL_CMD=0.1 BLACKW_YAW_CMD=0.1 \
  BLACKW_CLEAR_W=60.0 BLACKW_PROGRESS_W=8.0 BLACKW_GOAL_W=0.0 BLACKW_CLIMB_W=0.0 \
  .venv/bin/train blackw-official \
  --agent.resume True --agent.load-run <PREV_RUN> --agent.load-checkpoint <PREV_CK> \
  --agent.max-iterations 300 --env.scene.num-envs 512 \
  --agent.run-name m0_s<k> --agent.logger tensorboard --agent.save-interval 50 \
  > /tmp/m0_s<k>.log 2>&1 &

# gate 工具（需按 §3.4 扩展 eval 脚本：--attempts 16/8 + --jitter-x/--jitter-yaw/--command-set）
# 产物: prep.d/results/blackw_official/stage_gates/<stage>.json
```

### 4.3 Step 3：深度部署 D0（必须开工，当天最小链路）

**定位（用户 2026-10-26 确认）**：不需要深度相机的任务先拿满/≥90%（盲侧 950 → ≥855）；**深度侧必须立即开工**，负责 trench30 + 梅花桩（300+200=500 分的深度依赖项目）。本 Step 当天就要有可演示的最小链路。

1. **训练侧 D0**：把 `camera-depth.md` 里已有的 `CameraSensorCfg` + `camera` obs group + `CNNModel` 配置移植到 `part2` exact/mixed 任务（**只读参考 HIM 的深度代码，不改其文件**）；渲染 trench30/plum/stairs 的深度图，确认 3.8m 处 0.1/0.2/0.3m 槽、桩间隙可分辨（48×64 可能只有 1–3 像素；不够就升分辨率或做 depth→ego 高度图）。
2. **部署侧最小链路（当天必须跑通）**：rl_sar 的 MuJoCo 场景加一个前向深度相机（与训练同安装位姿/内参/fovy），渲染深度图并与训练端 MjLab 渲染对拍统计（同场景、同帧，比较深度直方图/缺失率/边缘）；这是 D5 的前置，不能拖到"后面做"。
3. **CNN 推理链路**：先在 Python/离线脚本里跑通导出的 TorchScript CNN（单帧深度 → latent → 与训练同 obs 拼接）；再接到 rl_sar 控制循环（延迟 <10 ms 目标）；观测归一化参数与训练端逐项对齐。
4. **产出**：① depth vs RGB/几何对比图 + "槽/桩是否可见"结论；② rl_sar 深度渲染 + CNN 前向的 demo 日志/视频；③ "部署端与训练端深度统计差异"记录。若槽不可分辨，先解决分辨率/ego 高度图；但**链路本身必须当天通**。

### 4.4 Step 4：深度专项 T30 + 梅花桩（D1/D2/D3，按较难档 8/8 gate）

- **为什么不做盲试**：trench30 gap 0.30 m > 前后轮触地跨距一半 0.213 m（`blackW_description.xml` keyframe 0：前轮 +0.229、后轮 −0.197 → 跨距 0.426 m），且 > 轮径 0.206 m；梅花桩 0.2 m 桩 + 0.4 m 缺口需要落足感知——两者判为盲不可达，**不再浪费 GPU 做盲 T30/P**。
- D1（BeamDojo stage1 风格）：平地/低难度动力学 + 任务地形感知观测；CNN trunk 从盲 M0 初始化。
- D2：特权 critic（heightmap/足底接触）+ BeamDojo 式 foothold/落点奖励 + double critic；plum 地形课程：大平台→小桩→官方 0.2m 桩/0.4m 缺口；T30 固定 r=1.0。
- D3：实地形 fine-tune，每 25–50 iter judge；两者都按较难档 **8/8** gate 通过才进部署。
- D4：深度策略与盲 M0 按障碍切换（规则允许）；若要求单模型，DAgger 蒸馏；保留盲 fallback。

### 4.5 Step 5：最终评测、录像、入库

1. 全 20 关 judge v5 逐障碍 4 次，记录盲侧得分（目标 ≥855/950）与深度专项（T30/P 8/8）；
2. 每个通过的权重重录视频给用户复核，更新 `final_profile.json` 与 `models/<name>/manifest.json`；
3. 把本文件 §3 stage 表、gate JSON、深度里程碑记录到归档，供答辩引用。

## 5. 已知坑与不要重复的结论

1. **禁止不同难度并行混合训练**（旧版 `BLACKW_MAX_ROW` 随机 row 0..5 = 严重错误）：目标训练必须"固定 stage 难度 + 鲁棒 gate + 逐档热启动"（§3）。
2. **warp 无 PGS**：训练环境 stairs 成功率天然偏低（55–75% vs judge 100%）；gate/判定以 **judge** 为准，warp 只当下界。
3. **不要用 `Episode_Termination/*` 当日志成功率**：它是计数型指标，可能 >1；用 `check_tier_success.py` 或 judge 数真实通过率。
4. **不要状态式 shaping**：`competition_goal` 每步奖励、状态式 progress/climb 都会让策略原地刷分；只用 potential 差分 + 一次性 success。
5. **不要把"训练环境 0 success"当学不会**：先检查谓词/物理是否对齐（本会话曾因死代码+物理不一致误判，见归档 §11）。
6. **不要直接 full-resume 微调 BC**：旧 critic/optimizer/iter 会带偏；用 `make_bc_checkpoint.py --reset-trainer` + GuardedPPO + 冻结 σ。
7. **不要动 HIM 区**：对方仓的 `blackw-platform-exact-him` 继承同一套 `_part2_terrain_state`，其"0 success gate"在对方仓未修；发现类似问题只提醒，不改其仓。
8. Type-B Codex 审计不可用（`comp/audits/2026-10-25-judge-v5-G1-REVIEW_UNAVAILABLE.md`），分数是 executor 证据；不要对外声称"已审计"。
9. **GPU 队列（2026-10-26 已确认）**：机器装的是 task-spooler v1.0.3（`~/.local/bin/ts`，`TS_SOCKET=/tmp/gpu_queue.socket`，单槽），job 脚本在 `~/rc_work/gpu_jobs/`；提交 `TS_ONFINISH=$HOME/rc_work/gpu_jobs/on_finish.sh ts -L ppo_xxx $HOME/rc_work/gpu_jobs/<job>.sh`，查看 `ts -l/-c/-i`。契约与实测数字见 [`remote-training-workflow.md`](remote-training-workflow.md) §5；本线使用规则见执行计划 §6。**不要再绕开队列 nohup 起训练**。
10. **深度部署不是可选项**（用户 2026-10-26 确认）：不需要深度相机的任务先拿满/≥90% 分数；深度侧 D0 + rl_sar 渲染/CNN 推理最小链路当天必须跑通（§4.3），不要拖到"盲线结束再说"。

## 6. 文档地图

| 文档 | 用途 |
|---|---|
| [`part2-ppo-execution-plan-2026-10-26.md`](part2-ppo-execution-plan-2026-10-26.md) | **当前执行计划（2026-10-26 起）**：修正后的目标与分数账、分阶段排期、GPU 队列使用协议、待确认项；**§0.2 Living TODO = 短期/长期待办唯一记录处（新会话先看这里）**；本文件 §4 以其为准 |
| 本文件 | 交接：课程规则（§3）、原"明天清单"（§4，已被执行计划取代）、远程状态、边界、开放问题 |
| [`part2-bc-policy-report.md`](part2-bc-policy-report.md) | 主报告：judge v5、BC/DAgger、评测结果、参考文献、局限 |
| [`part2-ppo-training-history.md`](part2-ppo-training-history.md) | 归档：bug 审计/修复证据、最低档/档位结构验证、显存实测、早期 specialist 记录 |
| [`part2-blind-depth-curriculum-plan.md`](part2-blind-depth-curriculum-plan.md) | 模型分工（主线 M0 盲 + 深度 T30/P；S45/St30 为盲目标）、盲课段 B0–B4、深度 BeamDojo 课程 D0–D5（与本文 §3 一致） |
| [`part2-failure-vs-reward-design.md`](part2-failure-vs-reward-design.md) | termination vs reward shaping 的原则与文献 |
| `@20261024_blackw/README.md` | 部署栈、评测命令、权重/脚本索引 |
| `@20261024_blackw/training/README.md` | 训练侧代码快照说明（与远程仓对应关系） |

## 7. 开放问题与已确认事项

**已确认（无需再问）**：
- 从最近 checkpoint 续训是常规操作（不必重开 run）。
- gate 标准：简单档 S0–S2 judge 16/16；较难档 S3–S6 及专项最高档 judge ≥8/8；gate 含初始状态随机化 + 3 档速度指令随机化（§3.4）。
- 11-01 前优先级：M0 逐档 gate + stairs30 盲专项（盲侧目标 850，2026-10-26 由 950 修正）+ 深度部署 D0/D1 **并行**。
- 盲/深度划分（2026-10-26 修正）：盲可拿分 850（platform40/wall40/slope35/stairs20/trench20 + stairs30 增量）；深度依赖 = trench30（+150）与梅花桩（+200）。slope45 当前阶段不计入 850，但**不判死**：judge μ=1.0 静态零余量；按用户要求做 μ=1.2 诊断并双报 μ=1.2/1.0；冲坡可提供 6–11% 摩擦余量且不超 dq_des 20 rad/s，后期可试 μ 递减课程（1.5→1.0，手动 gate）。
- **深度部署必须开始做**：盲可达任务先拿满/≥90% 分数（850→≥850），深度侧 D0 + 部署最小链路当天开工（§4.3），深度专项 = trench30 + 梅花桩（§4.4）。
- **GPU 队列（2026-10-26）**：task-spooler 单槽已实测可用（见 §2.3 / `remote-training-workflow.md` §5），训练/导出任务一律经 `ts` 提交。
- **guard4 复核（2026-10-26）**：三个 800-iter run 跑完但无新档位（历史归档 §14.1），不续训。

**仍需确认/上机查**：
1. **GPU 时间分配**：PPO 线与 HIM 线今天/未来几天各占多少、谁先跑？（建议今天 PPO 先跑 stairs30 A/B ~80 min，其余时段让 HIM，晚上 PPO 续）
2. **夜间关机窗口**：是否每天约 23:00–08:00 关机？所有 job 按 ≤2 h 切分 + save-interval 50 是否 OK？
3. **slope45 是否接受移除**：摩擦探针显示官方 judge 物理下 45° 零余量（历史归档 §14.2）；若确认正式赛不改该口径，是否同意盲侧目标由 950 改为 850，把算力转向 stairs30 与深度？
4. **交付形态**：正式提交允许"按障碍切换策略"（M0 + stairs30 专项 + 深度专项）吗？还是必须单份模型（需额外 DAgger 合并工期）？
5. **截止前 gate 兜底**：若某档在 11-01 前只到 6/8 这类（4 次机会下期望分仍高），是否允许作为最终候选交付（仍以 8/8 为训练目标）？
6. **深度侧部署链路最小验收口径**：是否"当天能渲染 + 前向推理跑通"即可，还是要接完整 6 障碍闭环？默认按前者（最小链路可演示）推进。

## 8. 快速命令卡片

> 2026-10-26 起统一用 task-spooler 提交训练/导出任务：job 模板与提交命令见 [`part2-ppo-execution-plan-2026-10-26.md`](part2-ppo-execution-plan-2026-10-26.md) §7 与 [`remote-training-workflow.md`](remote-training-workflow.md) §5；下面的 `nohup` 模板只作参数参考（不再直接使用）。

```bash
# 远程训练（guarded 通用模板；按 GPU 队列提交）
ssh bis-ms7e56.tail4413b4.ts.net
cd ~/rc_work/part2_team_race && export PYTHONPATH=$PWD/src MUJOCO_GL=egl
nohup env BLACKW_DEPLOY_SIM=1 BLACKW_DIFF_MIN=<STAGE_R> BLACKW_DIFF_MAX=<STAGE_R> \
  BLACKW_PHYSICS_DT=0.002 BLACKW_DECIMATION=10 BLACKW_LR=4e-5 \
  BLACKW_ALGORITHM="alldog_mjlab.tasks.velocity.blackw.guarded_ppo:GuardedPPO" \
  BLACKW_GUARD_BLEND=0.95 BLACKW_ENTROPY_COEF=0.0 BLACKW_LEARN_STD=false \
  BLACKW_EPOCHS=2 BLACKW_MINIBATCHES=8 BLACKW_NORM_ADV_PER_MB=true \
  BLACKW_CLEAR_W=60.0 BLACKW_PROGRESS_W=8.0 BLACKW_GOAL_W=0.0 BLACKW_CLIMB_W=0.0 \
  .venv/bin/train <task> --agent.resume True --agent.load-run <prev> --agent.load-checkpoint <prev_best>.pt \
  --agent.max-iterations 300 --env.scene.num-envs 512 --agent.run-name <run> \
  --agent.logger tensorboard --agent.save-interval 50 > /tmp/<run>.log 2>&1 &

# 训练环境随机化 gate（check_tier_success.py；--difficulty 传 stage r）
BLACKW_DEPLOY_SIM=1 .venv/bin/python scripts/agent_scripts/check_tier_success.py \
  --task blackw-platform-exact --checkpoint <ckpt>.pt \
  --difficulty <STAGE_R> --vx <vx> --envs 128 --episodes 3 --no-dr  # 再去掉 --no-dr 做随机化 gate

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
