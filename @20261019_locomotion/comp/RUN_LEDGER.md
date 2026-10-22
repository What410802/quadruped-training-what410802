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

## 单开关说明

| run_id | 相对上一版改了什么（只许一项） | 预期 | 实际 |
|---|---|---|---|
| `flat_ft_mirror01_footclear_500` | 加 mirror loss 0.1 + foot_clearance | 步态对称性/离地高度改善 | 见 docs/training/experiments.md |
| `p1_basic_obstacle` | 混合 terrain generator（flat+smooth slope+stairs，无 rough/discrete） | 坡度/台阶通过 | 部分改善，未过 gate |
| `eval-only:part1-v2` / `part2-v2` | 只替换评测器（judge V2 + 参数化 Part2 档位），策略未变 | 得到可审计的 0 分诊断，验证评测链路 | 与 v1 一致（flat 策略 0 分），链路跑通 |

## 失败 run

| run_id | 现象 | 根因 | 处理 |
|---|---|---|---|
| `baseline-rough-2000` | `normal expects std >= 0` + Warp 710 崩溃 | 数值不稳定（见 training-health） | 从 checkpoint 恢复；后续加安全网 |
