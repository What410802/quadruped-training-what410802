# Part 2 PPO/BC 线执行计划（2026-10-26 上午接手后）

> 本文件是 [`part2-ppo-handoff-2026-10-26.md`](part2-ppo-handoff-2026-10-26.md) §4「明天执行清单」的落地版：把交接里"上机先核对"的假设换成 2026-10-26 08:30–10:00 实测状态，修正目标分数，给出到 11-04 的分阶段计划、远程机（task-spooler 单卡队列）使用协议与待用户确认项。规则与课程口径仍以交接 §3 为准，模型分工见 [`part2-blind-depth-curriculum-plan.md`](part2-blind-depth-curriculum-plan.md)；本文件只回答"今天起按什么顺序、花多少算力、到什么算成功"。

## 0. 结论（先读）

- **guard4 长跑已完成但无可捞档位**：`guard4_{slope,stairs,plum}` 三个 800-iter run 全部跑完（`model_799.pt` 落盘）；导出 5 个 checkpoint/run 做 judge 复核（15 个 checkpoint × 4 次；无抖动时 4 次等价确定性重复），**slope 45° 0/60、stairs 30cm 4/60（只有 1 个 checkpoint 的确定性轨迹过，±0.1 m 抖动重测 3 次全挂）、plum 0/60**，slope35°/stairs20cm 只在 9/15 与 3/15 个 checkpoint 保持。结论与交接 §3.3 一致：**混合难度行（row 0..5 随机）的 guarded 微调不会凭空长出 45°/30cm**；guard4 只作历史证据，不续训。
- **slope 45°：当前阶段不计入交付目标，但不判死（2026-10-26 第二轮修正）**：官方 judge 场景 geom 摩擦系数 = **1.0**（`ability_field/map.xml`），45° 稳态爬坡所需 tan45° = 1.0 → **静态零余量**，所以盲侧当前目标仍按 **850** 计。但按用户指示：① μ=1.2 训练只作诊断，**评测必须同时报 μ=1.2 与 μ=1.0**；② **冲坡（平地加速→入坡）可提供摩擦余量**：入坡 1.5 m/s 时等效需求 μ_eff≈0.943、2.0 m/s 时≈0.898（能量核算见 §2.4），且不会触发部署关节速度限幅；③ 后期可做 **μ 递减课程（1.5→1.3→1.2→1.1→1.0，逐档手动 gate）**。正式赛物理口径由用户向培训方沟通后再定。
- **修正后的分数账**：当前交付 `comp_bc_v5` = **750/1300**（4 次挑战期望 ≈743）；可争取 = stairs30（+100，盲专项）+ trench30（+150，深度）+ plum（+200，深度）；不可达 = slope45（+100）。**盲侧实际天花板 = 850**（当前 750 + stairs30 的 100），**全体实际上限 = 1200/1300**。
- **今日关键路径**：① stairs30 盲专项 A/B（GPU 队列，约 80 min，本文件 §4/§7 给了可直接提交的 job）；② gate 工具扩展 + comp_bc_v5 全程 placement（本地 CPU，不占 GPU）；③ 深度 D0（训练侧相机移植 + rl_sar 渲染/CNN 最小链路，GPU 只占 ~20 min smoke）。
- **task-spooler 已实测可用**（3 个 job：中断清理 / 11 s 训练 smoke / 85.6 s 批量导出 15 个 checkpoint，单槽串行、排队与日志/完成标记均正常），使用协议见 [`remote-training-workflow.md`](remote-training-workflow.md) §5 与本文 §6。

## 0.1 用户第二轮确认（2026-10-26 09:20，覆盖此前假设）

- **GPU 分配**：先到先得（与 HIM 线共享单槽队列），不预留静态时段；但**不许浪费算力**——只跑"课程逐档位 + 代码逐行审查过"的任务，跑前先自检/小 smoke。
- **夜间关机**：一般 **00:00–09:00** 关机；若 00:00 时仍有训练在跑可等到 **00:30**，所以单 job 应控制在 ~2 h 内、`save-interval 50` 保证被打断后可续。
- **交付形态**：允许按障碍切换策略，但**目标最多 3 份策略**（分析见 §3.1）。
- **成功率为王**：按对应分数优先级提升成功率；**当前阶段目标 = 除 30 cm 沟壑（trench30）与梅花桩（plum）外，Part 2 其余全部关卡 8/8 成功拿满分**（即盲侧 850 全拿满；trench30/plum 属深度项，另行争取）。
- **slope45 诊断（2026-10-26 第二轮补充）**：不直接判死——先把**训练环境**地形摩擦调到 μ=1.2 做课程训练，看训练侧成功率能否起来（judge 物理保持 μ=1.0 不变；该实验只用于判定瓶颈归属，不作为交付）。实现 `BLACKW_WORLD_FRICTION`（默认不生效）+ 自检脚本，见 §2.3。**评测时 μ=1.2 与 μ=1.0 都要报**（正式赛物理口径由用户告知培训方）。
- **冲坡缺口（用户 2026-10-26 第二轮要求核算）**：μ=1.0 时“平地加速冲坡”能否上顶、是否导致关节速度超限——核算见 §2.4；结论：纯惯性不可行（需 6.26 m/s，对应轮速 60.8 rad/s，超过部署 dq_des 上限 20 rad/s），但冲坡提供的 6–11% 摩擦余量是真实可用的，且 ≤2 m/s 入坡不会触发关节速度限幅 → 若 μ=1.2 训练有效，**后期可尝试 μ 递减课程 + 冲坡（手动 gate）**。

## 0.2 待办清单（Living TODO，2026-10-26 10:15 建立；每次 session 结束前更新）

> 规则：本清单是这条线**唯一的"说到就要做"记录处**——对话里新增的未完成事项先落到这里再执行；完成后打 `[x]` 并写证据路径/commit；每个工作时段结束复盘一次，长期项按日期推进。短期 = 今天/24 h；长期 = 到 11-04 赛前。

### 短期（今天 10-26 余下时间）

- [x] task-spooler 队列落地 + 3 类 job 实测（SIGTERM 清理 / 3 iter 训练 smoke / 15 个 checkpoint 批量导出）→ [`remote-training-workflow.md`](remote-training-workflow.md) §5
- [x] guard4 三个 800-iter run 复核：无可捞档位 → [`part2-ppo-training-history.md`](part2-ppo-training-history.md) §14.1
- [x] stairs30 专项 v0（r=0.75→1.0）首轮：judge 首次 stairs30 1/4（m350/m650）→ 历史归档 §14.4
- [x] slope45 μ=1.2 课程诊断（job 11）：BC 基线 40°=95.7%、45°=0%；stage A 40°→100%；**stage B（45°，再 350 iter）训练 0%，judge 双测 μ=1.2/1.0 均 fail** → 历史归档 §14.5
- [ ] **stairs30 续训 job 13**（10:39–约 11:10 运行）：结束后 **不要直接重训同配方**——先对 s100b 全部 checkpoint 做 judge（stairs30/20 + platform40/wall40/slope35/trench20 回归）选点；仍 <2/8 走单变量变体：**提高塑性应把 `BLACKW_GUARD_BLEND` 调到 0.98**（实现是 `θ=base+blend·Δ`，0.90 反而把锚加得更死；0.95→0.98 ≈ 有效步长 20×→50×），同时开 `BLACKW_GUARD_LOG=1` 记录每 iter actor drift，或插入 r=0.9 中间档
- [ ] **slope45 下一步（μ 递减课程起点）**：μ=1.2 学不会 → 改从 **μ=2.0 或 1.5** 先学 45°（BC v5 在 μ=1.5 可攀到 root z≈2.08、μ=2.0 能到顶），学会后逐档降 μ（2.0→1.7→1.5→1.3→1.2→1.1→1.0，每档 resume + ~200 iter + 手动 gate）；每档同时报 μ=1.2/1.0；排在主线空档，不抢 8/8 主线 GPU
- [ ] **gate 工具实现（本地，不占 GPU）**：`eval_blackw_part2.py` 加 `--jitter-x/--jitter-yaw/--joint-offset/--joint-vel/--command-set`（3 档速度指令 + 关节随机化）；新增 `gate_stage.py`（阶段表 → 每关×每指令档通过矩阵 + verdict）；自检后对 comp_bc_v5 跑 placement
- [ ] **comp_bc_v5 placement（本地）**：20 关 × 3 指令档 × 8/16 次 → 输出 `prep.d/results/blackw_official/stage_gates/`，得到"最低未通过 stage"清单
- [ ] **M0 逐档 gate 训练**：按 placement 结果只训未过档（mixed official 固定 r，每档 300 iter ≈10–12 min）；目标 platform40/wall40/slope35/stairs20/trench20 + stairs30 全部 8/8
- [x] **核实 10:45 交叉审计中 PPO 相关条目**（结论与证据见历史归档 §15）：配置/指标/guarded base/ blend 方向/早停缺口属实；"PREVDIR glob 匹配 s100b" 不属实；gate 工具欠账属实。**并确认 HIM 的 play=True 假测量 bug 在 PPO gate 链路上不存在**（tiercheck 用 play=False、输出 part2_terms；judge 是独立判据），但同构风险需加断言防复发
- [ ] **修文档/代码里的 blend 方向**（本行上面已改计划；`guarded_ppo.py` docstring 已有正确语义，但所有新脚本注释/汇总必须写"blend 越大越塑性"）
- [ ] **GuardedPPO 增补（审后改）**：新增 `BLACKW_GUARD_BASE_CKPT`（显式指定以哪个 checkpoint 的 actor 为锚，默认仍用加载权重）；每次 run 打印 base 来源与 sha；所有 guarded run 开 `BLACKW_GUARD_LOG=1`
- [ ] **评测脚本 fail-closed 断言**：`check_tier_success.py`（已 play=False）加 `assert "part2_success" in active_terms`；任何新 eval 脚本禁止用 `play=True` 读训练终止项（HIM 的假测量事故反例，只记录不改其仓）
- [ ] **job 提交前检查清单进 §6**：指标是否权威（judge/tiercheck 用途）、是否有 eval-gated 选点、anchor 是否显式、早停条件是否定义、是否走 common.sh、summary 是否写 gate verdict
- [ ] **早停规则（写进后续 job）**：每 100 iter 导出 checkpoint；连续 2 个 100-iter judge 评估无提升（或训练 success 与 judge 同时不涨）→ `ts -k` 停当日该线，从最近 checkpoint 人工导出后再决定
- [ ] **深度 D0-a**：把 `black/camera_depth.py` 的 `CameraSensorCfg` + camera obs group + `CNNModel` 接到 blackw exact/mixed 任务（只读参考 HIM 文件，不改其文件）；训练端 depth smoke（约 10 min GPU）
- [ ] **深度 D0-b**：本地 rl_sar 侧 MuJoCo 深度渲染 + TorchScript CNN 前向最小链路 + 与训练端深度统计对拍（不占 GPU）
- [ ] **今晚 00:00 前收工检查**：所有 job 结束/checkpoint 落盘、flag=0、summary 齐全；夜间关机 00:00–09:00（最晚等 00:30）

### 长期（到 11-04）

- [ ] **盲侧 8/8 拿满 850**：platform40 / wall40 / slope35 / stairs20 / trench20 / stairs30 全部 8/8（简单档 S0–S2 按 16/16）
- [ ] **3 份策略交付形态**（§3.1）：`M0(+St30 DAgger 合并)` + 深度 T30 + 深度 P；若深度只成一个则退化 2 份；始终保留单份盲 fallback
- [ ] **深度 T30（+150）**：D1 训练在 **10-28 前**看训练侧 trench success 是否从 0 起来；不过则 10-28 EOD 止损并记录负结果
- [ ] **深度 P 梅花桩（+200）**：仅在 T30 成功后启动；10-29 决策
- [ ] **slope45（+100，可争）**：μ 递减课程 + 冲坡（见 §2.4 与短期项）；正式赛物理口径由用户与培训方确认；过 8/8 gate 才把盲侧目标由 850 提到 950
- [ ] **10-30 冻结候选、11-01 冻结**（AGENTS：D-3 起不开新训练线）；11-02–11-04 复跑/视频/答辩
- [ ] **文档同步**：每次 gate/训练结论 → 历史归档 + 本文件 §1/§2 更新；不入库产物放 `prep.d/` 并写路径

### 当前在跑/排队（每次更新）

| 队列 job | 内容 | 状态 |
|---|---|---|
| job 13 | `ppo_st30_s100b`（stairs30 从 m650 续训 800 iter） | running（约 11:10 完成） |
| job 12 | HIM 线 `him_row0_mixed_gate.sh` | ✅ finished 10:39，但 **gate 结果无效**（HIM 侧 play=True 缺 part2 项；属 HIM 区，见历史归档 §15） |
| job 11 | slope μ=1.2 诊断 | ✅ finished（负结果，§14.5） |
| — | job 13 后队列空；下一步先做 s100b judge 选点，再决定是否排 stairs30 塑性变体（不盲目续训） | — |

## 1. 实测状态（2026-10-26 08:30–10:00）

| 项 | 实测结果 |
|---|---|
| 远程机 | 07:55 左右开机；RTX 5060 Ti 16 GB 空闲（179 MiB）；12 核 / 30 GB；`part2_team_race` 仓与 `.venv` 正常 |
| GPU 队列 | task-spooler v1.0.3，`TS_SOCKET=/tmp/gpu_queue.socket`，单槽；开工时队列空 |
| guard4 | 3 个 run 均完成 800 iter；每 50 iter 存档；已用 `ts_export_guard4` 导出 5 checkpoint/run（单次导出 5–6 s） |
| 本地 judge | 20 个官方隔离场景链路正常；4 attempt/关约 2–4 s（platform）/ 5–10 s（stairs），本地 6 并发可用 |
| 迭代耗时（实测） | 精确地形 512 env（部署对齐物理）：mixed-row guard4 约 5.9 s/iter（800 iter=79.6 min），定档 stairs-exact r=0.75 约 **2.25 s/iter**（300 iter≈11–12 min）；mixed official 1024 env ≈1.9–2.4 s/iter（300 iter≈10–12 min） |
| 深度链路 | 训练仓已有 `black/camera_depth.py`（48×64 深度、CNN latent 64）但 **part2 任务未接**；rl_sar 控制栈**没有**深度相机/CNN 推理（D0 的主要工作量） |

## 2. 关键证据（可复现）

**guard4 judge 复核**（每格 `success/4`；deterministic，无抖动；完整 JSON 在 `prep.d/results/guard4_ts_trial/judge/`）：

| checkpoint | slope_45deg | slope_35deg | stairs_30cm | stairs_20cm | plum_1 |
|---|---|---|---|---|---|
| guard4_slope m0/m200/m400/m600/m799 | 0/4 ×5 | 4/4 ×4、0/4 ×1 | 0/4 ×5 | 0/4 ×4、4/4 ×1 | 0/4 ×5 |
| guard4_stairs m0/m200/m400/m600/m799 | 0/4 ×5 | 4/4 ×3、0/4 ×2 | 0/4 ×5 | 4/4 ×1、0/4 ×4 | 0/4 ×5 |
| guard4_plum m0/m200/m400/m600/m799 | 0/4 ×5 | 4/4 ×2、0/4 ×3 | 4/4 ×1、0/4 ×4 | 4/4 ×1、0/4 ×4 | 0/4 ×5 |

命令 sweep 复核（±0.1 m 横向抖动；`prep.d/results/guard4_ts_trial/sweep/`）：comp_bc_v5 / guard4_plum_m200 / guard4_stairs_m0 / guard4_stairs_m799 × stairs30 的 8 组速度指令（0.4–1.0 m/s 直冲、0.65→0.35、0.75→0.45、0.8→0.3、0.9→0.35、1.0）× 3 次 = **0/96 全挂**；同 4 个权重 × slope45 的 4 组指令 × 2 次 = **0/32 全挂**。→ 现有 checkpoint 无法用"换指令"白拿 stairs30/slope45。

**slope45 摩擦探针**（`@20261019_locomotion/scripts/agent_scripts/probe_slope_friction.py`，改 `model.geom_friction` 后同场景重跑 comp_bc_v5，vx=0.3）：

| μ | judge | max root z | 说明 |
|---|---|---|---|
| 1.0（官方） | fail(timeout) | 0.79 m | 坡面滑住，爬不上去 |
| 1.2 | fail(timeout) | 0.82 m | 仍滑住 |
| 1.5 | fail(timeout) | 2.08 m | 几乎到顶（18 s 窗口不够），说明策略会爬 |
| 2.0 | fail(fell, tilt 76°) | 2.54 m | 能冲上去但控不住 |

→ 结论：45° 的瓶颈是摩擦余量（tan45°=μ=1.0），不是策略；**除非正式赛物理口径不同，slope45 不列入训练目标**。

### 2.3 slope45 训练环境 μ=1.2 诊断（用户 2026-10-26 要求）

- 目的：区分"策略学不会"与"judge 物理不允许"。做法 = **训练环境**地形摩擦由默认 1.0 调到 1.2（`BLACKW_WORLD_FRICTION=1.2`，MuJoCo 接触摩擦取两侧 geom 的最大值，机器人轮子仍 1.0 → 接触 μ=1.2），judge 物理保持 1.0；按课程 r=0.8（40°）→ r=1.0（45°）训练，看训练环境 `part2_success` 是否从 0 起来。
- 实现：`blackw/exact_terrain.py` 的 `_box()` 在环境变量存在时给每个地形 geom 写 `friction`（默认不写，官方/交付训练行为不变）；自检 `@20261019_locomotion/scripts/agent_scripts/check_world_friction.py`（远程 `scripts/agent_scripts/`）实测三种模式：unset→compiled 1.0、=1.2→compiled 1.2、=0.8→geom 0.8（接触仍取 max=1.0），slope 3 geoms / stairs 13 geoms 全部一致，SELFTEST PASS。
- 2026-10-26 实测基线（job 11，BC v5，训练环境 check_tier_success，128 env × 2 ep）：μ=1.2 时 r=0.8（40°）**95.7% 成功率（245/256）**；μ=1.2 时 r=1.0（45°）**0%**；μ=1.0 时 r=1.0 **0%**。→ BC 的步态在 μ=1.2 下也爬不上 45°，μ=1.2 的 20% 静态余量不足以覆盖它的动态需求；job 11 的 stage A（r=0.8 250 iter）→ stage B（r=1.0 350 iter）正在跑，用于判断"训练能否在 μ=1.2 学会 45°"。
- 判读（2026-10-26 第二轮修正）：① μ=1.2 学会、judge(μ=1.0) 不过 → 记录为"静态零余量下的物理限制"，**但不判死**：按 §2.4 的冲坡机制继续做 μ 递减课程；② μ=1.2 也学不会 → 提升训练摩擦到 1.5 先学技能，再逐档降 μ（1.5→1.3→1.2→1.1→1.0）；③ 每个阶段都同时报 μ=1.2 与 μ=1.0 的评测（judge 官方场景为 μ=1.0，μ=1.2 用改 friction 的同场景 `probe_slope_friction.py --mu 1.2` 测）。
- **job 11 结果（2026-10-26 10:00 完成）**：stage A（r=0.8，250 iter）把 40° 从 95.7% 提到 **100%**；**stage B（r=1.0，再 350 iter）训练侧 `part2_success` 全程 0**，结束时训练环境 r=1.0 在 μ=1.2 与 μ=1.0 下都是 **0/256**；把 B 的 4 个 checkpoint 导出后在 judge 场景双测（μ=1.2 与 μ=1.0）也全部 fail（max root z 0.69–0.96 m）。→ **μ=1.2 的 20% 静态余量不足以让该谱系学会 45°**；按用户指示不判死，下一步改从 μ=1.5/2.0 起学（短期待办已记）。

复现命令（本地，CPU）：

```bash
cd /home/bis/BiS.d/Code.d/RoboCon/MyMonoRepo.d
pixi run python @20261019_locomotion/scripts/agent_scripts/probe_slope_friction.py
pixi run python @20261024_blackw/scripts/eval_blackw_part2.py \
  --policy @20261024_blackw/ws/src/rl_sar_blackw/policy/blackW/comp_bc_v5 \
  --only stairs_30cm --attempts 3 --jitter-y 0.1 --command 0.75 0 0 \
  --slow-from-x 1.1 --cmd-slow 0.45
```

### 2.4 冲坡（run-up）与关节速度核算（用户 2026-10-26 第二轮要求）

- 场景参数：45° 坡 rise=2.0 m / run=2.0 m（坡面长 2.83 m），机器人总质量 **20.38 kg**（judge 场景里 `obstacle` 静态体 7840 kg 不计），ΔPE = **399.9 J**；轮半径 0.103 m。
- 纯惯性（不靠摩擦做功）登顶需要 `v=sqrt(2gh)=6.26 m/s`，对应轮速 **60.8 rad/s = 581 rpm**；而部署 `command_limit.hpp` 的 `dq_des` 上限是 **±20 rad/s（=2.06 m/s）**，MuJoCo 模型本身也不限关节速度 → 这个速度发不出去，**靠平路加速"飞"上 45° 坡不可行**。
- 但冲坡可以**减少所需摩擦系数**（用动能换高度）：入坡速度 v 时等效需求 `μ_eff = tan45°·(1 − v²/(2gh))`：

| 入坡速度 | 动能 | 占 ΔPE | 轮速 | 等效 μ_eff |
|---|---|---|---|---|
| 0.5 m/s | 2.5 J | 0.6% | 4.9 rad/s | 0.994 |
| 1.0 m/s | 10.2 J | 2.5% | 9.7 rad/s | 0.975 |
| 1.5 m/s | 22.9 J | 5.7% | 14.6 rad/s | **0.943** |
| 2.0 m/s | 40.8 J | 10.2% | 19.4 rad/s | **0.898** |
| 2.06 m/s（dq_des 上限） | 43.3 J | 10.8% | 20.0 rad/s | 0.892 |

- **实测**（comp_bc_v5，judge 场景，`--command 1.5` 冲坡）：1.8 m 助跑段内入坡速度可达 **1.86 m/s**；过程中最大轮速 **19.3 rad/s（<20 rad/s，未触发部署限幅）**，腿关节动态峰值 22–30 rad/s（模型无速度限位，30 rad/s=286 rpm 远低于实际电机上限，且这是被动动态峰值而非指令）。所有 μ=1.0/1.2 配置下 max root z 仍只有 0.79–0.82 m（当前 BC 不会用这股余量）。
- 结论：**冲坡不会造成关节速度超限**（前提：入坡 ≤2 m/s → 轮速 ≤20 rad/s），且能把 45° 的等效摩擦需求从 1.0 降到 0.89–0.94，是真实可用的机制；若 μ=1.2 训练有效，后期做 **μ 递减课程（1.5→1.3→1.2→1.1→1.0）+ 冲坡**（训练 vx 上限放到 1.5 m/s，逐档手动 gate）。复现：`pixi run python @20261019_locomotion/scripts/agent_scripts/probe_slope_friction.py --mu 1.0 --mu 1.2 --command 1.5`。


## 3. 优先级与算力分配（修正后）

| 轨道 | 内容 | 价值 | 风险 | GPU 预算 | 决策点 |
|---|---|---|---|---|---|
| **P1** | stairs30 盲专项（exact r=0.75→1.0） | +100（750→850） | 中 | 今日约 30 min（含导出/诊断），明日 30–60 min | 今日 A/B 首 100 iter 是否有训练侧 success 信号 |
| **P2** | M0 逐档 gate（mixed official 失败档微调） | 鲁棒性/兜底（期望分 743→接近 750） | 低 | 合计 60–90 min | placement 结果出来即定（今天） |
| **P3** | 深度 D0（part2 接相机 + rl_sar 渲染/CNN 最小链路） | 深度专项前置，必须做 | 中 | ~20 min smoke | 今日 EOD 是否有 demo |
| **P4** | trench30 深度专项（D1/D2/D3） | +150 | **高** | 明日起 2–3 h/日 | 10-28 EOD 训练侧 success 是否从 0 起来 |
| **P5** | 梅花桩深度专项 | +200 | **最高** | 仅在 P4 达成后 | 10-29 再定 |
| **D0-diag** | slope45 μ 诊断 + 冲坡核算（非交付；μ 递减课程为后期候选） | +100 是否可能（正式赛口径待培训方确认） | 中 | job 11 约 40 min；μ 递减课程后期再排 | r=1.0、μ=1.2 训练侧是否从 0 起来（§2.3/§2.4） |

原则：**盲侧 850 优先保稳，深度侧按 P3→P4→P5 顺序只做加分的**；任何一天 GPU 时间不足时，先保 P1/P3，P2 可顺延，P4/P5 降级。

### 3.1 交付策略数量：3 份够不够（2026-10-26 分析）

候选能力项与所需策略：

| 能力项 | 归属 | 说明 |
|---|---|---|
| 普通行走 + 平台/高墙/斜坡 35°/楼梯 20cm/沟壑 20cm | 盲策略 M0 | 现有 comp_bc_v5 谱系，已 4 次挑战口径 750 分 |
| 楼梯 30cm | 盲专项 St30 | 盲可训练；可与 M0 合并（DAgger）或单独切换 |
| 沟壑 30cm（+150 相对 20cm） | 深度专项 T30 | 盲不可达，需深度 |
| 梅花桩（+200） | 深度专项 P | 盲不可达，需落足感知 |

结论：候选是 4 份（M0、St30、T30、P），要压到 **≤3** 必须合并/取舍，推荐按以下优先级：

1. **首选（3 份）**：`M0(+St30 合并)` + `T30` + `P`——两份盲策略用 DAgger 合成一份（同一观测/动作契约，St30 只在楼梯场景提供专家标签，M0 在其余关卡提供标签），输出仍是单份盲 MLP，不增加切换成本。
2. **降级（2 份）**：若深度只能做出一个专项，取分数更高者（P +200 > T30 +150）或更容易者（T30 视觉信号更直接），另一项放弃；或者把 T30+P 合并成一份"深度通用" CNN 策略（两地形联合训练）也能压到 2 份。
3. **兜底（2 份）**：深度整体不达预期时 = `M0` + `St30` 两份盲策略，盲侧 850 拿满。
4. 不建议做成 4 份以上：每多一份都要单独的渲染/推理/切换验证预算，且不增加分数。

## 4. 分阶段计划（10-26 → 11-04）

### 4.1 今天 10-26（剩余约 11 h）

1. **09:45–10:30 本地**：扩展 gate 工具（`eval_blackw_part2.py` 加 `--jitter-x/--jitter-yaw/--joint-offset` 随机化与 `--command-set` 三档指令；新增 `gate_stage.py` 输出每关×每指令档通过矩阵到 `prep.d/results/blackw_official/stage_gates/<stage>.json`）。不占 GPU。
2. **GPU 队列（2026-10-26 上午进度）**：stairs30 盲专项按课程分两步：`ppo_st30_s075`（r=0.75 = 25 cm/step，300 iter）已完成（训练环境 part2_success 计数 0.40–0.58，≈12 min）；首个 `ppo_st30_s100` 因 checkpoint 名写死 `model_300.pt`（实际最终存档是 `model_299.pt`）启动失败，已修正为"自动取最新 checkpoint + 补齐导出"并重新排队（job 9，r=1.0，400 次额外 iter）。其后排队 `ppo_slope_mu12`（job 10，诊断：训练环境 μ=1.2 的 40°→45° 课程）。所有 job 都是 GuardedPPO blend 0.95 / lr 4e-5 / 冻结 σ。收工后 scp 导出回本地 judge 选点。
3. **10:30–11:30 本地**：comp_bc_v5 全 20 关 placement（3 指令档 × 16/8 次尝试，本地 6 并发，约 15–30 min）→ 得"最低未通过 stage"清单；同时把 S0–S6 各自的目标档名单固化进 gate JSON。
4. **11:30–12:00**：深度 D0-a —— 把 `black/camera_depth.py` 的 `CameraSensorCfg` + camera obs group + `CNNModel` 接到 blackw exact/mixed 任务（只读参考 HIM 线文件，不改其文件）；排一个 10 min 的 depth smoke（512 env × 3 iter）验证能渲染、无 OOM。
5. **下午**：stairs30 首轮结果判读（训练侧 `check_tier_success --difficulty 1.0` + 中途 checkpoint judge）；据此选配方并提交 400–800 iter 续训；M0 失败档微调（mixed official，固定 r，每档 300 iter ≈10–12 min）；D0-b（rl_sar 侧 MuJoCo 渲染 + CNN 前向最小链路 + 与训练端深度统计对拍，本地）。
6. **18:00–22:30 GPU 队列**：stairs30 winner 续训（最多 80 min）+ M0 剩余失败档（每档 ~12 min）+ 第一个 T30 深度 smoke（如 D0-a 已完成）。
7. **收尾**：commit 脚本/文档；写次日 checkpoint 清单；夜间关机前确认所有 job 已结束、checkpoint 已落盘。

### 4.2 10-27（D+1）

- stairs30：跑 8/8 gate（3 指令档全过）→ 过则入库候选并录视频；不过则继续当前档 / 换配方（只允许单变量改动）。
- M0：S0–S6 每档 gate（16/16 或 ≥8/8，含随机化），补齐未过档。
- 深度：D0 完成（训练侧可见性：trench30/plum/stairs 深度图 + "槽/桩可分辨"结论；部署侧最小链路 demo 日志 + 视频；warp vs MuJoCo 深度统计差异记录）；T30 exact 深度任务从盲 M0 初始化跑 200–400 iter，观察训练侧 trench success。

### 4.3 10-28（D+2）

- T30 深度课程（先只加深度 obs + 标准 PPO；不收敛再加 foothold/双 critic）。
- stairs30 gate 复核 + M0 全档 gate 快照。
- **决策点**：T30 训练侧 success 仍为 0 → 停 P4，转 plum 可见性评估或直接收盲侧；有效 → 继续 D3。

### 4.4 10-29（D+3）

- T30 judge 8/8 gate 尝试；plum 视进展（不新开长线）。
- 盲侧最终 profile 复测（20 关 × 4 次 × 逐障碍指令）；新通过权重重录视频。

### 4.5 10-30（D+4）冻结候选

- 组装当前最高分组合（M0 + stairs30 + T30 若过），落 manifest/sha256/评分 JSON/视频；深度未过则冻结盲侧 850（或 750 兜底）+ 记录深度未完成项。
- 更新 `models/<name>/manifest.json`、`final_profile.json`、`JUDGE_V5_*.md`。

### 4.6 10-31 / 11-01 / 11-02–11-04

- 10-31：稳定复跑、补视频、doc 归档（不新开训练线）。
- 11-01：**冻结**（对应 `@20261019_locomotion/AGENTS.md` D-3 起不开新线）。
- 11-02–11-04：复跑、答辩材料、演示，不再改策略。

## 5. gate 工具与执行口径（交接 §3 的落地）

- **新增 CLI**：`--jitter-x 0.10 --jitter-y 0.15 --jitter-yaw 0.05`（初始 root 位姿）、`--joint-offset-range 0.03 --joint-vel-range 1.0`（与训练 reset 一致）、`--command-set {lo,mid,hi}`（名义速度 ×0.6/1.0/1.3，clamp 0.2–1.1 m/s；`--slow-from-x/--cmd-slow` 同比例缩放）、`--attempts 16/8`；输出每关×每指令档的 success 矩阵与一句话结论。
- **placement**：先用 comp_bc_v5 对 20 关 ×3 指令档 ×8 次跑一遍（≈15–30 min 本地并发），按 stage 表（交接 §3.2）判定"最低未通过 stage"；只训练未过档，不重复已过档。
- **晋升**：简单档 S0–S2 每档 16/16、较难档 S3–S6 与专项最高档 ≥8/8，且 3 指令档每档全过；warp 训练环境成功率只作诊断下界，判定以 judge 为准。
- **每次 gate 产物**：`prep.d/results/blackw_official/stage_gates/<stage>_<policy>.json` + 一句话结论写进本文件 §4 对应日期。

## 6. 远程机与 GPU 队列使用协议

- 队列机制与实测见 [`remote-training-workflow.md`](remote-training-workflow.md) §5：单槽 task-spooler，`~/rc_work/gpu_jobs/{common.sh,on_finish.sh,<job>.sh}`，`ts -L ppo_xxx ~/rc_work/gpu_jobs/<job>.sh` 提交；`ts -l/-s/-c/-i/-k/-C` 查看与控制。
- **本线规则**：只用 `ts` 提交（不绕开队列 `nohup train`）；标签 `ppo_*`；提交前 `ts -l` + `nvidia-smi`；本线队列内最多 2 个 job；单 job ≤2 h（**00:00 关机，最晚可等到 00:30**），`--agent.save-interval 50` 续训；被 SIGKILL 中断后手工 `printf 0 > ~/5060ti_machine_use_flag.txt`。
- **与 HIM 线共享单槽**：FIFO，先提交先跑；每天开工时两条线各报当日 job 清单（用户协调顺序）；GPU 空转时谁有就绪 job 谁跑，不预占。
- **产物回收**：远程 `~/rc_work/models/<name>/` → `scp` 到本地 `prep.d/results/<topic>/`；export→judge 在本地做（CPU，不占 GPU）；gate JSON 落 `prep.d/results/blackw_official/stage_gates/`。
- **今日队列状态（2026-10-26 10:05）**：job 7（stairs r=0.75）✅、job 9（stairs r=1.0 续训）✅；job 11（`ppo_slope_mu12`）running；job 12（HIM 线 `him_row0_mixed_gate.sh`）queued；job 13（`ppo_st30_s100b`，stairs30 从 m650 续训 800 iter）queued。GPU 先到先得（FIFO），中断用 `ts -k <id>`（随后手动 `printf 0 > ~/5060ti_machine_use_flag.txt`）。

## 7. 快速命令（可直接提交的第一批 job）

```bash
# stairs30 盲专项（已提交的 job 7/8；脚本在远程 ~/rc_work/gpu_jobs/）
#   ppo_st30_s075.sh: r=0.75（25 cm/step），300 iter，从 BC v5 初始化
#   ppo_st30_s100.sh: r=1.0（30 cm/step），400 iter，从 s075/model_300 热启动
# 提交（job 8 依赖 job 7 成功才启动）：
ssh bis-ms7e56.tail4413b4.ts.net
export PATH="$HOME/.local/bin:$PATH" TS_SOCKET=/tmp/gpu_queue.socket
TS_ONFINISH=$HOME/rc_work/gpu_jobs/on_finish.sh ts -L ppo_st30_s075 ~/rc_work/gpu_jobs/ppo_st30_s075.sh
TS_ONFINISH=$HOME/rc_work/gpu_jobs/on_finish.sh ts -d -L ppo_st30_s100 ~/rc_work/gpu_jobs/ppo_st30_s100.sh
ts -l                       # 队列状态（run=1/1 表示 GPU 忙）
ts -c <id> | tail -20       # 完整输出；ts -i <id> 看开始/结束/耗时/退出码
```

```bash
# 中途 checkpoint 导出（把 ITERS 改成需要的点；与 guard4 导出一致）
# （远程）python scripts/agent_scripts/export_blackw_policy.py \
#   --task blackw-stairs-exact --checkpoint logs/rsl_rl/black_velocity/<run>/model_100.pt \
#   --out ~/rc_work/models/ppo_st30_a_m100/policy.pt
# （本地）judge 单档
pixi run python @20261024_blackw/scripts/eval_blackw_part2.py \
  --policy prep.d/results/<dir> --only stairs_30cm --attempts 4
```

```bash
# 训练侧成功信号（诊断，不替代 judge）
BLACKW_DEPLOY_SIM=1 .venv/bin/python scripts/agent_scripts/check_tier_success.py \
  --task blackw-stairs-exact --checkpoint <ckpt> --difficulty 1.0 --vx 0.5 \
  --envs 128 --episodes 3 --no-dr
```

## 8. 风险与兜底

- slope45 物理口径风险：若正式赛确实换更高摩擦/不同坡度或主办方另有口径，本结论需重测（探针脚本已入库，10 min 可复现）。
- GPU 与 HIM 线争用：P1（stairs30）与 P3（D0）为关键路径，队列满时优先这两个；长训拆 2×40 min。
- 夜间关机：所有 job ≤2 h；中断后从最近 checkpoint 续训，不复跑。
- 深度不收敛：10-28 决策点止损，11-01 前只交付盲侧并记录负结果；D0 链路本身仍按用户要求完成。
- gate 过严 vs 交付分数：8/8 只作训练晋升门；最终交付按 4 次挑战机会评估期望分（见 §9 问题 5）。
- warp 无 PGS：stairs 训练环境成功率天然偏低（55–75% vs judge 100%），gate 以 judge 为准。
- judge 审计状态：Codex Type-B 审计仍 `REVIEW_UNAVAILABLE`，本文所有数字是 executor 证据（JSON+脚本可复现）。

## 9. 待用户确认（文档无法回答）

1. **GPU 时间分配**：PPO 线与 HIM 线今天/未来几天各占多少、谁先跑？（建议今天 PPO 先跑 §4.1 的 stairs30 A/B 约 80 min，其余时段让 HIM 长跑，晚上 PPO 续；如你有固定顺序我按你的来。）
2. **夜间关机窗口**：是否每天约 23:00–08:00 关机？所有 job 按 ≤2 h 切分、save-interval 50 是否 OK？
3. **slope45 是否接受移除**：摩擦探针显示官方 judge 物理（μ=1.0、45°）零余量；若确认正式赛不改这个口径，是否同意盲侧目标由 950 改为 850、把算力全部转向 stairs30 与深度？
4. **交付形态**：正式提交允许"按障碍切换策略"（M0 盲 + stairs30 专项 + 深度专项）吗？还是必须单份模型（需额外 DAgger 合并工期）？
5. **截止前 gate 兜底**：若某档在 11-01 前只到 6/8 这类（4 次机会下期望分仍高），是否允许作为最终候选交付（仍以 8/8 为训练目标）？

## 10. 文档指针

| 文档 | 用途 |
|---|---|
| [`part2-ppo-handoff-2026-10-26.md`](part2-ppo-handoff-2026-10-26.md) | 规则、课程口径、远程路径、命令模板（本文件的上游） |
| [`part2-blind-depth-curriculum-plan.md`](part2-blind-depth-curriculum-plan.md) | 模型分工（M0/T30/S45/St30/P）与深度 D0–D5 课程 |
| [`part2-bc-policy-report.md`](part2-bc-policy-report.md) | 主报告：judge v5、BC/DAgger、当前 750 的证据 |
| [`part2-ppo-training-history.md`](part2-ppo-training-history.md) | 训练 bug 审计/修复归档；本日复核证据见 §14 |
| [`remote-training-workflow.md`](remote-training-workflow.md) | task-spooler GPU 队列契约与实测（§5） |
| `@20261024_blackw/README.md` | 部署栈、评测命令、权重索引 |
