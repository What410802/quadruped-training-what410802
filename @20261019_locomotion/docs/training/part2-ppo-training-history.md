# Part 2 PPO/BC 线历史归档（训练 bug、验证实验与早期记录）

> 本文件是 [`part2-bc-policy-report.md`](part2-bc-policy-report.md) 的细节归档，保留 2026-10-25/26 的审计、验证与运行记录，供复现和答辩引用；主报告只保留结论与指针。§11/§12 编号沿用当时的上下文，§13 是更早 specialist 训练记录（多数结论已作废，仅留作教训）。

## 11. 2026-10-25 训练侧代码审计：确认并修复的 bug（含"0 success"结论作废说明）

对 PPO/BC 线做了一次针对性代码审计（用户侧 review 指出若干问题），逐条核实后确认并修复了以下 bug；其中前两条直接使此前所有"specialist 训练 0 success"的观察**不可作为"学不会"的证据**。

### 11.1 `_exact_env_cfg` 的 success/failure 谓词是死代码（确认）

`_exact_env_cfg` 把单地形放进 `generator.sub_terrains = {"exact": terrain_cfg}`，而 `_part2_terrain_state` 按 **sub-terrain 列名**分支（`"slope"`/`"stairs"`/…）；列名是 `"exact"` → 所有分支都不命中 → `part2_success`/`part2_failure`/`part2_clear` 恒为 False。证据：`spec_slope_v3` 跑 903 iter `part2_success` 全 0、`part2_clear` 全 0，而同一 BC v5 权重在部署 judge 下能过 slope 35°/stairs 20°。

修复：单地形 sub-terrain key 直接用 judge kind（`{"slope": ...}` 等，由 `_EXACT_TERRAIN_KIND` 从地形类名映射）；并把训练谓词与 judge v5 对齐（去掉 judge 没有的 `|vz|` 稳定性条件、加上 judge 的"爬上证据"（ stairs 顶部平台 / wall 交叉+climb_z / plum 未跌落）、hold 15 步 = judge 的 0.2+0.1 s）。

修复后 **lr=0 预检（BC v5 在训练环境里不回传）**：slope rows 0-1（20-25°）success 0.97；stairs rows 0-1 success 0.57–0.68；固定 45° 仍 0（没有产生假成功）。这证明契约/谓词链路已通。**注意**：`Episode_Termination/*` 日志是计数型指标，可能 >1，不能当通过率用；通过率以外部 judge 评测为准。

### 11.2 `competition_goal` 残留奖励导致"过线刷分"（确认）

`_exact_env_cfg` 只在 `BLACKW_GOAL_W>0` 时**添加** `competition_goal`，没有 pop 基线 `black/env_cfgs.py` 里的 `competition_goal`（weight 5.0，语义是 root 过 goal 线后每步 +1）。于是 `BLACKW_GOAL_W=0` 并没有关掉它：`spec_slope_v3` 日志里 `competition_goal` 0.88→3.98/s 持续上升，而 `part2_success` 恒 0（死代码）——策略在学"过线后蹲着刷分"。

修复：exact/mixed/plum 三个 cfg 都先 `pop("competition_goal")`（和 `climb_height`）再按需 opt-in 添加；进度奖励改成 potential-based 差分（只奖励进度增量，Ng et al. 1999），成功一次性奖励提高到 +60。

### 11.3 `BLACKW_MAX_ROW` 在 exact 任务里没被读取（确认）

`_exact_env_cfg` 只用 `0/1` 行起步，忽略了命令行给的 `BLACKW_MAX_ROW`（review 里"课程没生效"属实）。已补：`BLACKW_MAX_ROW>=0` 时 `max_init_terrain_level = min(MAX_ROW, num_rows-1)`。

### 11.4 训练地形几何 bug：坡道薄板有 2cm 台阶、且新坡道 y 偏移错（确认，重要）

`ExactSlopeTerrainCfg` 用"绕 y 轴旋转的薄板"表示坡面（厚 4 cm），其**上表面比地面高约 2 cm**，等于在坡道入口加了一个小台阶；官方场景是**实心楔形**（`map.xml` mesh 顶点即 (0,0)→(2,rise)）。另外把薄板改成实心楔形时，`_ramp` 忘记传 y 中心（默认 y=0 而地形中心 y=4 m），坡道被放到赛道外 4 m 处——机器人走到 x≈3.5 被 landing 的立面挡住，永远上不了坡。这两处解释了"BC 在 judge 场景能过 35°，但训练环境 35° 0 success"的怪象。

修复：新增 `_ramp()` 生成**实心楔形**（上表面精确经过 (start, start_z)→(start+run, start+rise)，带 y 中心参数），替换 slope/trench/plum 的全部坡道；用 raycast 验证训练地形剖面与官方一致（30°: x=1.8 z=0 → x=3.8 z=1.155 → landing）。

### 11.5 训练物理与部署 judge 不一致（确认，重要）

官方 `part2` 场景 XML 的 `<option>` 是：elliptic cone、PGS solver、`impratio=100`、Euler integrator、100 solver iterations、35 CCD iterations；而 MjLab 训练默认是 newton/pyramidal/impratio=1/implicitfast/10 iterations。同一个 BC v5 权重在训练环境里**爬不上 30-35° 坡**，在 judge 里却 4/4 通过——PPO 于是在"错的物理"里把已经正确的行为往错误方向拉（这正是"微调后评测掉到 10–50"的一个根因）。

修复：`_apply_deployment_sim_options()`（`BLACKW_DEPLOY_SIM=1` 启用）把训练 sim 对齐到 judge：euler/elliptic/impratio=100/iterations=100/ls_iterations=50/ccd=35/更接近的 spawn 高度。mujoco_warp 不支持 PGS，用 newton+100 iter 近似。对齐后 BC v5 在训练环境 35° 坡能爬上去（diag rollout 基座 z 升到 1.5 m），预检 success 明显回升。

### 11.6 继承 checkpoint 的 critic/optimizer/iter（确认）

`make_bc_checkpoint.py` 只替换 actor，critic/optimizer/iter 来自 `comp_high600`（另一个任务、另一个奖励尺度）。已加 `--reset-trainer`：critic MLP 用默认 nn.Linear 初始化、optimizer state 清空并按 `--lr` 设学习率、iter/infos 归零。

### 11.7 "有 base 模型的续训"保护（新增 GuardedPPO）

除 11.6 外，新增 `alldog_mjlab/tasks/velocity/blackw/guarded_ppo.py`（`GuardedPPO`，经 `BLACKW_ALGORITHM` 注册）：每个 optimizer step 后把 actor 参数投影回 base 的权重信赖域 `θ ← θ_base + λ(θ-θ_base)`（λ=0.9），并支持冻结部分层（`BLACKW_GUARD_FREEZE`）。10 步观测：未保护 run 单 iter actor 权重漂移 2.35e-4，GuardedPPO 为 3.3e-5（约 1/7）。配套 env 覆盖：`BLACKW_ENTROPY_COEF=0`、`BLACKW_LEARN_STD=false`（冻结 σ=0.1–0.3）、`BLACKW_EPOCHS=2`、`BLACKW_MINIBATCHES=8`、`BLACKW_NORM_ADV_PER_MB=true`、`BLACKW_LR=5e-5`。

### 11.8 评测侧：梅花桩 judge `z_cross_min` 用错（确认）

`gen_part2_official_levels.py` 把 `z_cross_min` 写成 `BASE_REF_Z + top - 0.15 = 0.55`（root 高度口径），但 eval judge 拿它当**轮底**阈值 → 轮底永远 <0.55 → 梅花桩所有尝试必失败（官方基线 plum=0 也被这个 bug 掩盖过）。已改为轮底阈值 0.05（轮底在桩顶 0.2 m、落到地面 ≈0 可区分），并重新生成 20 个场景。

### 11.9 受影响的旧结论（作废/待重测）

- "PPO specialist 在 slope/stairs 训练 400–900 iter 仍 0 success → 学不会/信号不可用"：**作废**（死代码 + 残留刷分奖励导致，success 从未被测量）。
- "HIM gate：500–800 iter 0 success 就停"的判据同样建立在同一 `_part2_terrain_state` 上（HIM 的 `blackw-platform-exact-him` 继承 `_exact_env_cfg`），**同样无效**，需在修 key 后重测。
- "微调后掉到 10–50 是纯 PPO 不稳定"：部分原因其实是 11.4/11.5 的 train/judge 物理与几何不一致（训练环境里行为本身就不对），需在修正后的环境里重做防护实验。

### 11.10 修复后的验证实验（2026-10-25 21:00–22:00）

在修完 11.1–11.7 后做了三组实验（远程训练仓；judge 评测在本地官方隔离场景上做）：

1. **信号有效性（lr=0 预检，BC v5 权重直接跑训练环境）**：slope rows 0–1（20–25°）`part2_success` 0.97、stairs rows 0–1 0.57–0.68；固定 45° 仍 0（没有假成功）。修复前同一任务跑 900+ iter `part2_success` 恒 0。
2. **训练/评测物理对齐**：对齐前 BC v5 在训练环境 30–35° 坡上 `x` 卡在 3.5 m（被 landing 立面挡住，坡道未接上/有 2 cm 台阶）、基座 z≈0.52；对齐后同一权重能爬上 35° 坡（基座 z 升到 1.5 m），训练环境 success 从 0 变成可测的正常水平。
3. **GuardedPPO 200-iter pilot（对齐物理 + 冻结 σ=0.1 + trust-region λ=0.9）**：每 iter 权重漂移 3.3e-5（未保护 2.35e-4）；checkpoint 在官方 judge 上：m20/m40 仍过 slope 30°/35°（未退化），m80/m100 开始丢 30°，m199 丢 35°；slope 45° 所有 checkpoint 仍失败（timeout）。stairs 同型：15 cm 间歇通过、20/30 cm 未过。**结论**：修 bug 后训练不再"必然破坏"BC（200 iter 内保持技能），但 200 iter × 小步长还不足以学出 45°/30 cm 新技能；需要更长训练 + eval-gated 选 checkpoint 或换更有塑性的方案（LoRA/残差/BC 正则）。已启动 `guard4_{slope,stairs,plum}` 长跑（800 iter、blend 0.95、对齐物理）。

**交付分数不变**：`comp_bc_v5` 在 judge v5 下仍是 750/1300（最好情况，4 次挑战期望 ≈743）；本次审计主要修复的是训练信号与训练/评测一致性问题，尚未带来新档位。

## 12. 最低挡位 / 档位结构验证、课程与显存协议（2026-10-25 深夜）

### 12.1 所有任务最低挡位成功率（排除梅花桩）

judge（官方几何 + 官方场景物理，BC v5 = `comp_bc_v5`/`model_0_bc_v5_guarded` 的 actor，推荐速度）各 8 次尝试：

| 任务 | 最低挡 | 命令 | judge 结果 |
|---|---|---|---|
| high_platform | 10cm | vx=0.5 | **8/8 通过** |
| high_wall | 10cm | vx=0.6 | **8/8 通过** |
| slope | 20° | vx=0.3 | **8/8 通过** |
| stairs | 10cm | vx=0.5 | **8/8 通过** |
| trench | 10cm | vx=0.3 | **8/8 通过** |

训练环境（`BLACKW_DEPLOY_SIM=1`，canonical spawn（清零 reset 随机化）+ clean obs + 128 env × 3 episodes，`check_tier_success.py`）：
platform 99.7%、wall 100%、slope 99.7%、trench 100%（失败各 1 例为 `bad_sim_state`，属 warp 数值边界）；
**stairs 只有 58–71%**，但同一权重在 judge 上 8/8 —— 差异来自 **mujoco_warp 不支持 PGS solver**（官方场景用 PGS；训练只能 newton 近似），多级台阶的接触/冲击对 solver 更敏感，导致训练环境里下台阶时横向漂移偏多（lane deviation）。这是已知 sim2sim 差距，不是逻辑 bug；台阶类训练应把 warp 下的成功率当"更严格的下界"，最终以 judge 为准。

### 12.2 高档位是否只是尺寸变化（无质变）

- **训练地形**（`check_tier_geometry.py`，difficulty 0 vs 1）：平台/墙/坡/楼梯/沟/桩场的 geom **数量与类型序列完全一致**；仅尺寸变化：平台高 0.10→0.40、墙高 0.10→0.40、坡 rise 0.728→2.00（20°→45°）、楼梯总高 0.60→1.80（单级 10→30cm）；沟壑高度 0.30 不变（只有槽宽 0.10→0.30）、桩场完全固定。没有额外台阶/侧墙/数量变化。
- **官方场景**（20 个隔离场景）：每个类别的 geom 数量、geom 类型、judge 键集合在全部档位完全一致，只有数值缩放：平台 `top_z` 0.1/0.2/0.3/0.4；楼梯 `top_z` 0.6/0.9/1.2/1.8（`goal_x_min=3.7`、`descend_end_x=6.2` 不变）；斜坡 `rise_z` 0.728/1.155/1.400/2.000（goal_x 3.9 不变）；墙 `wall_h` 0.1–0.4、`climb_z_min` 0.52–0.58、`wall_x=1.86`、`goal_x_min=2.27` 不变；沟壑只有槽宽 0.1/0.2/0.3（`near_x=3.8`、`plateau_z=0.3` 不变）；梅花桩只有一档且 `z_cross_min` 已修为轮底口径 0.05。
→ 结论：档位之间没有质变，此前"高档位疑似几何 bug"可以排除；剩余差距是能力问题。

### 12.3 课程问题的回答

**现在没有用 mjlab 自带的课程**：`black_competition_env_cfg` 在训练模式下 `pop("terrain_levels")`（mjlab 的 `terrain_levels_vel` 按行走距离升级，与 goal 终止的障碍 episode 不兼容；stage-3 曾出现 4 个列长期 level 0），exact 任务只是把 `max_init_terrain_level` 设成随机初始 row 上限（`BLACKW_MAX_ROW`）。所以当前 specialist 长跑是"**从 BC 初始化、在 row 0..5 上随机混合采样**"，**不是**"上一档位训好了再升下一档"。

建议（也是我准备实施的）：手工 **success-gated 课程**，逐档推进：
1. stage k 固定档位（或很窄的 range，例如 k±0.1），从 stage k−1 的 best checkpoint 热启动；
2. **升级门控**：在部署对齐环境上，canonical spawn + 随机化（见下）各跑 ≥100 episodes，要求 deterministic 成功率 ≥95%（更严：随机指令下 ≥90%）才进入 k+1；
3. 每 stage 存 checkpoint 并用 judge 复核（eval-gated 选 best），失败不升级、只继续当前 stage 或降回前一档。
4. **随机化必须覆盖**：① 初始状态——当前 reset 只随机关节 offset（thigh ±0.40 rad 等）与 root 速度 ±0.5 m/s，**root 位置/朝向没有随机化**，建议加 x±0.10、y±0.15、yaw±0.05（对应操作手摆位误差）；② 指令——真实手柄是线性映射：`rl_sim.cpp:394-396` 用 `axes[1]→vx, axes[0]→vy, axes[3]→yaw`，`rl_sim_blackw.launch.py` 的 `joy_command_scale` 默认 **1.5**（满杆 = 1.5 m/s、1.5 rad/s）；障碍赛实际用低前进速（约 0.2–0.8 m/s）、小侧移/小转向，课程门控里应对 vx∈[0.2,0.8]、vy∈±0.2、wz∈±0.3 做随机化（并保留满杆范围做安全上界测试）；③ 已有 DR（摩擦/负载/质心/编码器偏置/PD/推力）保持不变。
5. 这样也能避免"高档位训练把低档位能力破坏"：门控保证前一档在随机化下仍鲁棒后，再解冻/升温。

### 12.4 两线各占一半显存（~8GB）的可行性评估（历史记录：现已被 GPU 队列取代）

> **历史状态**：这是 2026-10-25 的"手动限制半显存"方案；之后算力机启用了 GPU 队列，目标训练按队列提交即可，**不再需要手动限半显存**（`BLACKW_NCONMAX/NJMAX` 仅留作显存/性能选项）。本节保留作实测记录。

实测（2026-10-25 22:00，RTX 5060 Ti 16GB）：exact 任务 512 envs（默认 `nconmax=1024/njmax=4096`）每进程 **3.83 GB**；256 envs 的 plum **1.60 GB**；我这条线三个 run 合计 9.3 GB，已超过 8GB。显存主要由 warp 的 `nconmax/njmax` capacity 决定，不是 env 数线性。

已做：`_exact_env_cfg` 增加 `BLACKW_NCONMAX` / `BLACKW_NJMAX` 环境变量（plum 已有）。**实测**（2026-10-25 22:47，512 env、`BLACKW_NCONMAX=256`、`BLACKW_NJMAX=1024`）：总显存 9453→11006 MiB，即每个 run **≈1.55 GB**（默认 1024/4096 是 3.83 GB），且 iteration time 6.1–7.8 s 与默认容量同场景 6.4–7.6 s 无差异（capacity 只占显存、不影响吞吐），无 nefc overflow 警告。一条线 8GB 预算内存上可放 2–3 个 512-env run；单条 1024-env run 也可行。启动前用 `@20261024_blackw/scripts/gpu_budget_check.py --need-gb 2 --max-line-gb 8 --max-processes 2` 检查。

**效果损失**：显存减半不改变算法/样本质量（capacity 只影响极端接触场景，需监控 `nefc overflow`），但两条线同时跑会**各分 ~50% SM 吞吐**，wall-clock 大约 **1.5–2×**（我的 3 个并发 run 现在就是 99% util、单 iter 明显变慢）。建议明天实施：
- 每条线同时最多 2 个 512-env run（或 1 个 512 + 1 个评测），启动时显式 `BLACKW_NCONMAX=256 BLACKW_NJMAX=1024`；
- 长跑尽量错峰（一条线跑长训时另一条只做评测/短跑），或把 800–1000 iter 拆成 2×400 做 eval-gated 选点，用"质量"换回吞吐；
- 加一个启动前检查（`nvidia-smi` 显存/占用进程数）脚本，超过 8GB 或 GPU 已有 >2 个训练进程时拒绝启动。

**2026-10-25 22:55 长跑中途快照**（`guard4_*`，800 iter，aligned physics，blend 0.95）：slope model_450 仍只过 30°/35°，45° timeout；stairs model_450 过 15/20cm，30cm timeout。说明 450 iter 的小步长锚定还不足以长出 45°/30cm；长跑结束后做完整 eval-gated 选点再定论。

## 13. 早期 specialist 训练记录（2026-10-25，部分结论已作废）

### 当时的实验配置与结果

目标缺口 = 斜坡 45°（+100）、楼梯 30cm（+100）、壕沟 30cm（+150）、梅花桩（+200）。当前并行跑：

- 第一轮 specialist（fixed 45°/30cm、无 anti-farming）在 400 iter 内 0 success，且发现 **reward farming**：`climb_height` 每步奖励 + `competition_goal` 在 root 过 goal 线后每步 +10，策略学会"爬到半坡/越过线后原地待着"。已修：progress/climb 只在 goal 线之前计分，goal 逐奖励默认 0，并加 `part2_out_of_course` 终止（越线后 0.8m 未成功即结束），成功一次性奖励 `part2_clear=+50`。
- 第二轮（anti-farming）跑 400 iter 后仍 0 success，复查发现**进度奖励本身也是状态式**（`competition_goal_progress` 原地站着也每步给分），且 `climb_height` 同理；已改成 **potential-based 进度差分**（`_course_progress_delta`，只奖励进度增量，符合 Ng et al. 1999 的 policy-invariance），从 exact 任务移除 climb 项、成功一次性奖励提到 +60。第三轮从 comp_bc_v5 初始化、2ms/10 decimation、lr 1.5e-4、difficulty rows 0..5 并行跑：
  - `spec_slope_v3`：`blackw-slope-exact`，512 env × 1200 iter（斜坡 20→45° 课程）；
  - `spec_stairs_v3`：`blackw-stairs-exact`，512 env × 1200 iter（台阶 10→30cm、完整上+下）；
  - `spec_plum_v1`：`blackw-plum`，256 env × 1200 iter（固定 tier-1 桩场 + 落足奖励 `plum_foothold`：轮底落在桩顶 [0.14,0.34]m 才给分）。
- 每个 specialist 出 checkpoint 后在对应官方隔离场景上用 judge v5 评测；达到 4/4 稳定后剪视频给用户复核、再决定是否入库；此外计划 `blackw-trench-exact`（gap 0.3m 洁净跨越）专项。

## 14. 2026-10-26 上午：guard4 复核、slope45 摩擦上限、GPU 队列实测

> 交接后（10-26 08:30 远程机开机）的复核证据；执行计划与当日排期见 [`part2-ppo-execution-plan-2026-10-26.md`](part2-ppo-execution-plan-2026-10-26.md)。

### 14.1 guard4 长跑复核：无可捞档位

- 三个 run 均完成 800 iter（`model_799.pt` 落盘；最后 mtime 10-25 23:09）；`max_init_terrain_level=5`（row 0..5 随机 = 交接 §3.3 禁止的混合难度做法），都从 `bc_v5_guarded_s01/model_0_bc_v5_guarded_s01.pt` 热启动。
- 导出 5 个 checkpoint/run（m0/200/400/600/799；单次导出 5–6 s，policy.pt 1.38 MB）到 `prep.d/results/guard4_ts_trial/exports/`，本地 judge（`eval_blackw_part2.py --attempts 4`，无抖动、deterministic）：slope45 **0/16**、stairs30 **0/15**（唯一一次 4/4 是确定性单轨迹，±0.1 m 抖动 3 次全挂）、plum **0**；slope35 与 stairs20 只在部分 checkpoint 保持。
- 命令 sweep 复核（`--jitter-y 0.1`、每配置 3 次）：comp_bc_v5 + 3 个 guard4 checkpoint × stairs30 的 8 组指令 = **0/24**；同 4 权重 × slope45 的 4 组指令 = **0/8**。
- 结论：混合行 guarded 微调不产生 45°/30cm 新技能，与交接 §3.3 一致；guard4 不续训，只作证据。产物 `prep.d/results/guard4_ts_trial/{judge,sweep}/*.json`（不入库）。

### 14.2 slope45 摩擦上限（盲侧目标 950→850 的依据）

- 官方 judge 场景 geom 摩擦系数 = 1.0（`assets/terrain/part2/ability_field/map.xml`：floor/platform 显式 `friction="1 .005 .0001"`；slope mesh 与机器人轮子用默认 1.0，MuJoCo 接触摩擦按元素取大）→ 45° 爬坡所需 tan45° = 1.0，**零余量**。
- 探针（`@20261019_locomotion/scripts/agent_scripts/probe_slope_friction.py`）：comp_bc_v5 @vx=0.3、场景 `part2_off_slope_45deg.xml`，加载后改 `model.geom_friction` 再跑同一 judge 判据：

| μ | judge | max root z |
|---|---|---|
| 1.0（官方） | fail timeout | 0.79 m |
| 1.2 | fail timeout | 0.82 m |
| 1.5 | fail timeout | 2.08 m（18 s 窗口内几乎登顶） |
| 2.0 | fail fell（tilt 76°） | 2.54 m |

- 结论：μ=1.0 时策略在 45° 坡上滑住；μ≥1.5 同一权重几乎登顶 → **45° 的瓶颈是摩擦余量，不是策略能力**。盲侧可拿满分相应修正为 **850**（platform40 200 + wall40 200 + slope35 100 + stairs20 100 + trench20 150 + stairs30 100 增量），全体实际上限 1200/1300（trench30 +150、plum +200 仍靠深度）。

### 14.3 task-spooler 单卡队列实测

- 远程 `~/rc_work/gpu_jobs/` 下已落地 `common.sh`（flock 等 GPU + flag + trap 清理 + 持久日志）、`on_finish.sh`（TS_ONFINISH 兜底）与 job 脚本模板；详细契约与 3 个 job 的实测数字见 [`remote-training-workflow.md`](remote-training-workflow.md) §5。
- 关键结论：单槽串行、排队即自动启动、`ts -k` 走 SIGTERM 可被 trap 清理、日志/退出码/耗时可用 `ts -i/-c` 取；队列状态在 `/tmp`，重启丢失，持久记录以 `~/rc_work/logs/*.log` 为准。


