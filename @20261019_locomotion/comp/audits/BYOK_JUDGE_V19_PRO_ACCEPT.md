## verdict：PASS（本轮第十九轮 flash 验收范围；不是最终 G1 结论）

## 1. 全 skipped importer 逐项

| 项 | 结论 | 依据 |
|---|---|---|
| 置空顺序 | **已闭环** | `comp_import_course_diag.py::main` 先计算 `non_skipped`，当 `if not non_skipped` 时执行 `best_rec = {}; best_states = {}`，该分支位于 `part1_obstacles`、`sum1`、`all_full`、`return_bonus` 计算**之前**，不再是死赋值。 |
| best score / final_time | **已闭环** | 全 skipped 时 `best_states` 已被清空，后续每障碍取 `st = best_states.get(oid) or {}`，全部为 `pending/0`；随后 `if not non_skipped: session = {"final_score": 0.0, "final_time_s": 0.0}`，summary 强制 0/0。 |
| obstacles 状态 | **已闭环** | 同上，`part1_obstacles` 全为 `success=False, score=0, evidence=[]`，不会把 skipped attempt 内先前的 success/正分带进汇总。 |
| trials 层 | **已闭环** | skipped attempt 的 trial 被强制 `status="skipped"`、`score=0`、`duration_s=0`、`skipped=true`，均在 `comp_import_course_diag.py::main` 的 trial 生成循环内完成。 |
| evidence | **已闭环** | evidence 过滤条件同时要求 `not t.get("skipped")` 且 `judge.status=="success"`；全 skipped 时无任何成功 trial 可被引用。 |
| 返回奖励 | **已闭环** | `all_full` 基于已清空的 `best_states`，必然为 `False`，`return_bonus=0`，不会生成 `return_to_start` 成功 trial。 |
| comp_score 侧 | **已闭环** | `comp_score.py::validate_external_evidence` 的 `by_attempt` 对 `t.get("skipped")` 先 `continue`；`validate_summary` 的 `succ_trials` 排除 skipped；evidence 指向 skipped 会报错；`validate_trials` 要求 skipped trial `duration_s==0`。 |
| 自检 fixture | **已闭环** | `comp_import_selftest.py::main` 构造两轮 skipped attempt，且第一轮 judge states 含 `height_bar.success/100`、第二轮含 `high_wall.success/100`，并注入 `session_summary.final_score=999`，断言导入后 0/0、obstacles 全 false/0、evidence 空、trials 全 skipped/0。 |
| 历史 skipped 语义残留 | **无残留** | `comp_part1_judge.py::AttemptManager.summary` 仍以 `scored = [a for a in attempts if not a.get("skipped")]` 计算 best；与 course importer/comp_score 口径一致。 |

## 2. 测试、回归与产物哈希

- **conformance 13 组**：`comp_judge_conformance.py::main` 明确列出 13 个测试函数；按源码静态复核应通过，未发现新改动导致的反例。
- **comp_score self-test**：`comp_score.py::run_self_test` 已覆盖 skipped 正分不计入、skipped 0 秒 + 完成 0 分 10 秒、非法 Part2 档位、篡改 hash、错误 final_time 等；静态复核应通过。
- **importer self-test**：`comp_import_selftest.py::main` 静态复核通过，fixture 正好命中第十八轮指出的“全 skipped + skipped judge states 含 success”路径。
- **历史 PASS 回归**：未发现 N1–N4、P1–P4、HighWall 墙段 x 约束、T 台阶 n/e 臂 33 分、bool 只认 1、StableStopTracker 物理 dt、pause/resume/abort/pause_timeout、证据链强校验的直接回归。
- **四份产物与 HASHES**：`flat-ft-2500-part1-diag-v2`、`flat-ft-2500-part2-diag-v2`、`flat-ft-2500-part2-official-diag`、`flat-ft-2500-part1-course-diag` 的 manifest/trials/summary sha256 与 `comp/audits/HASHES.json` 中对应对象一致；evidence 三份 drill JSON 也在 HASHES 中且匹配。

> 说明：本轮 artifact 未附 stdout；以上通过是基于源码路径与给定哈希的静态验收结论，不是实际执行日志的形式证明。

## 3. 仍有 blocker / 必须清理项

**没有新的 blocker。**

非阻塞清理项：

1. `comp/audits/HASHES.json` 仍为 `audited=false / verdict=pending`（Codex/G1 结论后应更新）。
2. `comp_import_selftest.py` 是新文件，但当前 `HASHES.json` 的 `OBJECTS` 未列出它；建议纳入审计对象，避免该自检文件变更后旧门禁不被无效化。
3. `comp/CONTRACT.md` §6 资产表仍列 V1 场景/旧 judge，需文档清理。
4. `comp/eval/_protocol.md` 仍为 draft，未冻结正式 `protocol_version`。
5. `comp_score.py` 顶部仍有重复 `import tempfile`，非阻塞清理。
6. 全 skipped 自检目前只校验 importer summary/trials；若想更完整，可再对生成的 policy_dir 跑一次 `comp_score.score_one`，但不是当前 blocker。

## 4. 是否满足“进入 Codex 前的 flash 验收（无问题）”

**yes。**

本轮修复已覆盖第 18 轮 blocker，skipped 语义在 importer、trials、evidence、summary、comp_score 侧链路闭环，且新增自检 fixture 能防止回归。

## G1 必写残余

- 砂砾坑真实“坑 + 碎木”几何未 recut，当前本地仍为凸起盒代理。
- Part2 官方能力场逐档交叉核对未完成，本地为同种类参数化 level。
- Part1 soft-reset 阈值与相邻 zone 重叠仍为启发式。
- 正式手动/操作手 3 次整场演练尚未在真实赛程完成；当前为脚本化 route 与 pause/resume/abort/pause_timeout 演练证据。
- T 台阶“上/下 ↔ s/n/e”与 50/33 部分分映射虽已按 Q2 ×2/3 落地，仍建议最终书面确认。
- Part2 official 重复最高档在确定性策略下统计意义有限；稳定性 ≥100 次、目标 0 失败未执行；`comp/eval/_calibration/` 标定集仍为空。
- 跨 attempt 模拟器时间重置后，事件时间线不可全局排序。
- Part1 单障碍诊断 importer 的 per-obstacle 汇总口径仅用于诊断，正式以 course importer 为准。
- `comp/eval/_protocol.md` 仍为 draft，未冻结正式 `protocol_version`。
- `HASHES.json` 仍为 `audited=false / verdict=pending`，需 G1/Codex 结论后更新。
