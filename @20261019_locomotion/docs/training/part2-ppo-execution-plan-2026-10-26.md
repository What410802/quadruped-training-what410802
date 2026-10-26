# Part 2 PPO/BC 线执行计划（2026-10-26 上午接手后）

> 本文件是 [`part2-ppo-handoff-2026-10-26.md`](part2-ppo-handoff-2026-10-26.md) §4「明天执行清单」的落地版：把交接里"上机先核对"的假设换成 2026-10-26 08:30–10:00 实测状态，修正目标分数，给出到 11-04 的分阶段计划、远程机（task-spooler 单卡队列）使用协议与待用户确认项。规则与课程口径仍以交接 §3 为准，模型分工见 [`part2-blind-depth-curriculum-plan.md`](part2-blind-depth-curriculum-plan.md)；本文件只回答"今天起按什么顺序、花多少算力、到什么算成功"。

## 0. 结论（先读）

- **guard4 长跑已完成但无可捞档位**：`guard4_{slope,stairs,plum}` 三个 800-iter run 全部跑完（`model_799.pt` 落盘）；导出 5 个 checkpoint/run 做 judge 复核，**slope 45° 0/16、stairs 30cm 0/15、plum 0**，slope35°/stairs20cm 只在部分 checkpoint 保持。唯一一次 stairs30 4/4 是确定性单轨迹，±0.1 m 横向抖动重测 3 次全挂。结论与交接 §3.3 一致：**混合难度行（row 0..5 随机）的 guarded 微调不会凭空长出 45°/30cm**；guard4 只作历史证据，不续训。
- **slope 45° 在官方 judge 物理下基本不可达，盲侧目标由 950 修正为 850**：judge 场景 geom 摩擦系数全为 **1.0**（`ability_field/map.xml`），45° 爬坡所需 tan45° = 1.0 → **零余量**；摩擦探针实测同一 comp_bc_v5 权重在 μ=1.0 只爬到 root z≈0.79 m（滑住），把摩擦抬到 μ=1.5 后同一权重能爬到 z≈2.08 m（几乎登顶）。这是物理口径上限，不是策略能力问题；**不再给 slope45 分配训练算力**（待用户确认，见 §9）。
- **修正后的分数账**：当前交付 `comp_bc_v5` = **750/1300**（4 次挑战期望 ≈743）；可争取 = stairs30（+100，盲专项）+ trench30（+150，深度）+ plum（+200，深度）；不可达 = slope45（+100）。**盲侧实际天花板 = 850**（当前 750 + stairs30 的 100），**全体实际上限 = 1200/1300**。
- **今日关键路径**：① stairs30 盲专项 A/B（GPU 队列，约 80 min，本文件 §4/§7 给了可直接提交的 job）；② gate 工具扩展 + comp_bc_v5 全程 placement（本地 CPU，不占 GPU）；③ 深度 D0（训练侧相机移植 + rl_sar 渲染/CNN 最小链路，GPU 只占 ~20 min smoke）。
- **task-spooler 已实测可用**（3 个 job：中断清理 / 11 s 训练 smoke / 85.6 s 批量导出 15 个 checkpoint，单槽串行、排队与日志/完成标记均正常），使用协议见 [`remote-training-workflow.md`](remote-training-workflow.md) §5 与本文 §6。

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

命令 sweep 复核（±0.1 m 横向抖动、每配置 3 次；`prep.d/results/guard4_ts_trial/sweep/`）：comp_bc_v5 / guard4_plum_m200 / guard4_stairs_m0 / guard4_stairs_m799 × stairs30 的 8 组速度指令（0.4–1.0 m/s 直冲、0.65→0.35、0.75→0.45、0.8→0.3、0.9→0.35、1.0）× 3 次 = **0/24 全挂**；同 4 个权重 × slope45 的 4 组指令 = **0/8 全挂**。→ 现有 checkpoint 无法用"换指令"白拿 stairs30/slope45。

**slope45 摩擦探针**（`@20261019_locomotion/scripts/agent_scripts/probe_slope_friction.py`，改 `model.geom_friction` 后同场景重跑 comp_bc_v5，vx=0.3）：

| μ | judge | max root z | 说明 |
|---|---|---|---|
| 1.0（官方） | fail(timeout) | 0.79 m | 坡面滑住，爬不上去 |
| 1.2 | fail(timeout) | 0.82 m | 仍滑住 |
| 1.5 | fail(timeout) | 2.08 m | 几乎到顶（18 s 窗口不够），说明策略会爬 |
| 2.0 | fail(fell, tilt 76°) | 2.54 m | 能冲上去但控不住 |

→ 结论：45° 的瓶颈是摩擦余量（tan45°=μ=1.0），不是策略；**除非正式赛物理口径不同，slope45 不列入训练目标**。

复现命令（本地，CPU）：

```bash
cd /home/bis/BiS.d/Code.d/RoboCon/MyMonoRepo.d
pixi run python @20261019_locomotion/scripts/agent_scripts/probe_slope_friction.py
pixi run python @20261024_blackw/scripts/eval_blackw_part2.py \
  --policy @20261024_blackw/ws/src/rl_sar_blackw/policy/blackW/comp_bc_v5 \
  --only stairs_30cm --attempts 3 --jitter-y 0.1 --command 0.75 0 0 \
  --slow-from-x 1.1 --cmd-slow 0.45
```

## 3. 优先级与算力分配（修正后）

| 轨道 | 内容 | 价值 | 风险 | GPU 预算 | 决策点 |
|---|---|---|---|---|---|
| **P1** | stairs30 盲专项（exact r=0.75→1.0） | +100（750→850） | 中 | 今日约 30 min（含导出/诊断），明日 30–60 min | 今日 A/B 首 100 iter 是否有训练侧 success 信号 |
| **P2** | M0 逐档 gate（mixed official 失败档微调） | 鲁棒性/兜底（期望分 743→接近 750） | 低 | 合计 60–90 min | placement 结果出来即定（今天） |
| **P3** | 深度 D0（part2 接相机 + rl_sar 渲染/CNN 最小链路） | 深度专项前置，必须做 | 中 | ~20 min smoke | 今日 EOD 是否有 demo |
| **P4** | trench30 深度专项（D1/D2/D3） | +150 | **高** | 明日起 2–3 h/日 | 10-28 EOD 训练侧 success 是否从 0 起来 |
| **P5** | 梅花桩深度专项 | +200 | **最高** | 仅在 P4 达成后 | 10-29 再定 |
| ~~slope45~~ | 盲专项 | +100 | **物理不可达** | 0 | 已用摩擦探针判死（§2） |

原则：**盲侧 850 优先保稳，深度侧按 P3→P4→P5 顺序只做加分的**；任何一天 GPU 时间不足时，先保 P1/P3，P2 可顺延，P4/P5 降级。

## 4. 分阶段计划（10-26 → 11-04）

### 4.1 今天 10-26（剩余约 11 h）

1. **09:45–10:30 本地**：扩展 gate 工具（`eval_blackw_part2.py` 加 `--jitter-x/--jitter-yaw/--joint-offset` 随机化与 `--command-set` 三档指令；新增 `gate_stage.py` 输出每关×每指令档通过矩阵到 `prep.d/results/blackw_official/stage_gates/<stage>.json`）。不占 GPU。
2. **08:51 GPU 队列（已提交，job 7 → 8 依赖链）**：stairs30 盲专项按课程分两步，而不是直接跳 r=1.0：`ppo_st30_s075`（r=0.75 = 25 cm/step，300 iter，实测 ≈2.25 s/iter → 约 11–12 min）跑完自动导出 m100/200/300 并做训练侧 tiercheck；随后 `ppo_st30_s100`（r=1.0 = 30 cm/step，400 iter，≈15 min，`ts -d` 依赖前一 job 成功才启动）从 s075 的 model_300 热启动。两个 job 都是 GuardedPPO blend 0.95 / lr 4e-5 / 冻结 σ。收工后 scp 导出结果回本地 judge 选点；若两步都不出信号，再试 §3 的"更多塑性"配方（blend 0.85 / lr 8e-5）。
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
- **本线规则**：只用 `ts` 提交（不绕开队列 `nohup train`）；标签 `ppo_*`；提交前 `ts -l` + `nvidia-smi`；本线队列内最多 2 个 job；单 job ≤2 h（夜间关机），`--agent.save-interval 50` 续训；被 SIGKILL 中断后手工 `printf 0 > ~/5060ti_machine_use_flag.txt`。
- **与 HIM 线共享单槽**：FIFO，先提交先跑；每天开工时两条线各报当日 job 清单（用户协调顺序）；GPU 空转时谁有就绪 job 谁跑，不预占。
- **产物回收**：远程 `~/rc_work/models/<name>/` → `scp` 到本地 `prep.d/results/<topic>/`；export→judge 在本地做（CPU，不占 GPU）；gate JSON 落 `prep.d/results/blackw_official/stage_gates/`。
- **今日队列状态（2026-10-26 08:51）**：已提交 `ppo_st30_s075`（job 7，running）→ `ppo_st30_s100`（job 8，`ts -d` 依赖 job 7 成功）；预计 09:25 前后跑完（job 7 实测 ≈2.25 s/iter）。手动中断/抢占：`ts -k 7`（需手动把 flag 置 0），随后可直接跑 HIM 线任务；PPO 线要续跑时从 `~/rc_work/models/ppo_st30_s075_m300` 对应 checkpoint 重新提交。

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
