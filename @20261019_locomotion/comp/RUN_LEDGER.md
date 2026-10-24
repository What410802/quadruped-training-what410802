# Run Ledger（训练/评测 run 账本，只追加）

> 现有 run 的细节仍在 `docs/training/experiments.md`；本表只做"一行一个 run + 可追溯字段"。
> 新 run 由 `/comp-train-loop` 追加；评测结果由 `comp_score.py` 写 `SCOREBOARD.md`。

| run_id | 日期 | task | 初始化 | envs | iters | 时长 | 训练仓 commit | 导出 sha256 | eval policy_id | 总分 | 状态 |
|---|---|---|---:|---:|---|---|---|---|---|---:|---|
| `baseline-2000` | 2026-10-20 | `black-flat` | 从零 | 4096 | 2000 | 47:19 | 训练仓 `24c7f16`（未改） | `ac4652b8c5bc…` | — | — | EVAL_DONE（flat gate 通过） |
| `baseline-rough-3999` | 2026-10-20 | `black-rough` | flat `model_1999` | 4096 | 3999 | 1:17 + 恢复 | 训练仓 `24c7f16` | `b34b03e5ae71…` | — | — | EVAL_DONE（G3 未通过） |
| `flat_ft_mirror01_footclear_500` | 2026-10-21 | `black-flat` | baseline `model_1999` resume | 2048 | 500 | 13:00 | 训练仓 `24c7f16` + mirror/footclear 改动 | `332737933d75…` | `flat-ft-2500-part1-diag-v1` | 0 | EVAL_DONE（诊断） |
| `p1_basic_obstacle` | 2026-10-22 | `black-basic-obstacle` | flat-ft `model_2498` | 4096 | 1500 | 1:11 | 训练仓 fork（`model_3997`） | `8deb41a6ab3b…` | `p1-basic-obstacle-part1-diag-v1` | 0 | EVAL_DONE（诊断；slope/stairs 未过） |
| `p1_basic_obstacle_cont` | 2026-10-22 | `black-basic-obstacle` | `model_3997` resume → `model_5496` | 4096 | 1500 | 1:11 | 训练仓 fork | `035749ffab32…` | `p1-cont-part1-diag-v1` | 0 | EVAL_DONE（诊断） |
| `eval-only:part1-v2` | 2026-10-22 | — | 复用 flat-ft-2500 | — | — | — | 训练仓 `24c7f16`（同 v1） | 同 `332737933d75…` | `flat-ft-2500-part1-diag-v2` | 0 | EVAL_DONE（V2 judge 诊断） |
| `eval-only:part2-v2` | 2026-10-22 | — | 复用 flat-ft-2500 | — | — | — | 训练仓 `24c7f16`（同 v1） | 同 `332737933d75…` | `flat-ft-2500-part2-diag-v2` | 0 | EVAL_DONE（V2 evaluator 诊断；20 档全失败） |
| `eval-only:course-v2` | 2026-10-22 | — | 复用 flat-ft-2500 | — | — | 94 s | 训练仓 `24c7f16`（同 v1） | 同 `332737933d75…` | `flat-ft-2500-part1-course-diag` | 0 | EVAL_DONE（整场协议诊断；1 次尝试） |
| `e1_ctrl_3997_20261024` | 2026-10-24 | `black-basic-obstacle` | resume p1 run1 `model_3997` | 4096 | 100 | 4:18 | 训练仓 `ab66f9c` + worktree diff（10-22 快照同） | — | — | — | CLEAN（对照：复现 p1_cont 前 100 iter） |
| `e5_5400_20261024` | 2026-10-24 | `black-basic-obstacle` | resume `p1_cont model_5400` | 4096 | 100 | 5:00 | 同上 | — | — | — | CLEAN（action_rate 峰值 0.088） |
| `probe2_5496_20261024` | 2026-10-24 | `black-basic-obstacle` | resume `model_5496` + `BLACK_ANOMALY_PROBE=1` | 4096 | 1（首个 rollout 内 step 29 停训） | — | 同上 + `utils/anomaly_probe.py` | — | — | — | ANOMALY CAUGHT（动作自激证据，见 training-health §7.3） |
| `fixed2_5496_200_20261024` | 2026-10-24 | `black-basic-obstacle` | resume `model_5496` + 三项安全网 | 4096 | 200 | ~12:00（含启动） | 同上 + obs/action clip + `bad_sim_state` | — | — | — | FIXED SMOKE（无 CUDA/NaN；动作饱和 ~300） |
| `eval-only:him-best-v2` | 2026-10-24 | — | 外部 HIMLoco `best.pt` zero-shot（frozen-start + time-extended） | — | — | ~6 min（CPU） | `@20261007_assignment` 权重 md5 `7af7bab2…` | — | — | — | EVAL_DONE（诊断；Part2 ext 300/1300） |
| `depth_plumbing_test_20261024` | 2026-10-24 | `black-basic-obstacle-depth` | 从零（10 iter 内） | 64 | 3 | — | 训练仓 + depth task 改动 | — | — | — | PLUMBING OK（CNNModel actor、obs 45+camera、3 次 PPO update） |
| `cost_smoke_20261024` | 2026-10-24 | `black-basic-obstacle` / `-depth` | 从零（成本测量，各 25 iter） | 1024 / 2048 | 25×4 | 1–3 min/case | 训练仓 + depth task 改动 | — | — | — | COST：blind 1.39 s/iter、depth32 2.12 s、depth64 3.53 s、depth64@2048 6.22 s（15 GB） |
| `depth_100iter_smoke_20261024` | 2026-10-24 | `black-basic-obstacle-depth` | 从零 | 1024 | 100 | 3:19 | 训练仓 + depth task 改动 | — | — | — | SMOKE PASS（100/100、无 CUDA/NaN、mean 2.11 s/iter、32×32） |

## 单开关说明

| run_id | 相对上一版改了什么（只许一项） | 预期 | 实际 |
|---|---|---|---|
| `flat_ft_mirror01_footclear_500` | 加 mirror loss 0.1 + foot_clearance | 步态对称性/离地高度改善 | 见 docs/training/experiments.md |
| `p1_basic_obstacle` | 混合 terrain generator（flat+smooth slope+stairs，无 rough/discrete） | 坡度/台阶通过 | 部分改善，未过 gate |
| `eval-only:part1-v2` / `part2-v2` / `course-v2` | 只替换评测器（judge V2 + 参数化 Part2 档位 + 整场协议），策略未变 | 得到可审计的 0 分诊断，验证评测链路 | 与 v1 一致（flat 策略 0 分），链路跑通 |
| `fixed2_5496_200_20261024` | 相对 `probe2` 只加三项安全网（obs clip / action clip / bad_sim_state 终止） | 同一崩点不再 NaN/CUDA 710 | 见 training-health §7.5 |

## 失败 run

| run_id | 现象 | 根因 | 处理 |
|---|---|---|---|
| `baseline-rough-2000` | `normal expects std >= 0` + Warp 710 崩溃 | 数值不稳定（见 training-health §3） | 从 checkpoint 恢复；后续加 reward/return 安全网 |
| `rough_from_p1_20261023` / `basobstacle_from_p1_20261023` / `smoke100_resume_20261024` | resume `model_5496` 后 100 iter 内 Warp 710；action_rate 离群 | 动作经 last-action 观测自激（training-health §7.3） | 加 obs/action clip + `bad_sim_state`；`fixed2` 200 iter 通过 |
