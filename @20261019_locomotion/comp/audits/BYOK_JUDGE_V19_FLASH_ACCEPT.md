verdict：**PASS**

> 说明：artifact 未附行号；以下按“文件::函数/代码段”定位，不臆造行号。测试结论以源码静态复核 + 现有 artifact/HASHES 为准；未附本轮 stdout，不能形式证明“实际执行过”，但未发现代码反例或 blocker。

## 1. 全 skipped importer 路径是否闭环

**结论：闭环；skipped 语义在 course importer / summary / evidence / final_time 侧无残留 blocker。**

逐项：

| 项 | 结论 | 依据 |
|---|---|---|
| best score 排除 skipped | 闭环 | `comp_part1_judge.py::AttemptManager.summary` 使用 `scored = [a for a in attempts if not a.get("skipped")]`；`comp_import_course_diag.py::main` 选 best 时 `if rec.get("skipped"): continue`。 |
| final_time 排除 skipped | 闭环 | `comp_score.py::validate_external_evidence` 的 `by_attempt` 先 `if t.get("skipped"): continue`；全 skipped 时 importer 强制 `session={"final_score":0.0,"final_time_s":0.0}`。 |
| evidence | 闭环 | 全 skipped 时 `best_states={}`，`part1_obstacles[*].evidence=[]`；`comp_score.py::validate_summary` 对 evidence 指向 skipped trial 报错。 |
| succ_trials | 闭环 | `comp_score.py::validate_summary` 的 `succ_trials` 排除 `t.get("skipped")`。 |
| trial 层 status/score | 闭环 | `comp_import_course_diag.py::main` 对 skipped attempt 强制 `status="skipped"`、`score=0`、`duration_s=0`、`skipped=true`。 |
| 全 skipped summary | 闭环 | 修复后顺序为：选 best（跳过 skipped）→ 载入 `best_states` → 计算 `non_skipped` → 若为空立即 `best_rec={}`、`best_states={}` → 再生成 trials、`part1_obstacles`、`sum1`、`all_full`、`return_bonus`、session summary。`best_states={}` 不再是 dead assignment。 |
| 自检 fixture | 覆盖关键场景 | `comp_import_selftest.py::main` 构造“全 attempts skipped，且第一个 skipped attempt 的 judge states 含 `height_bar=success/100`”，断言 `final_score=0/final_time=0`、`total=0`、`return_score=0`、obstacles 全 false/score0/evidence 空、所有 trial 均 skipped/0。 |

补充：`comp_import_selftest.py` 本身没有调用 `comp_score` 去断言 `diagnostic`，这是测试强度上的非阻塞缺口；但按当前 importer 输出和 `comp_score.py` 校验路径静态推导，该全 skipped 产物会判 `diagnostic` 而非 `invalid`。

## 2. conformance、self-test、历史 PASS、四份产物与 HASHES

### conformance 13 组
`comp_judge_conformance.py::main` 仍列 13 组，包含高墙、T 台阶、限高杆、绕杆、斜坡、砂砾坑、桥、attempt manager、timeout、scene geom tags 等。按源码静态复核应通过；未见本轮修复引入 judge 语义回归。

### comp_score self-test
`comp_score.py::run_self_test` 覆盖 skipped 正分、skipped 0 秒 + 完成 0 分、hash 篡改、非法 Part2 档位、错误 final_time 等。按源码静态复核应通过。

### importer self-test
`comp_import_selftest.py::main` 覆盖全 skipped + skipped judge states 含 success 的 importer 场景。按源码静态复核应通过。

### 历史 PASS 项回归
未发现 N1–N4、P1–P4、HighWall、TStairs、bool 只认 1、StableStopTracker、pause/resume、return evidence 等历史修复的直接回归。关键文件 hash 与 HASHES 一致：`comp_part1_judge.py`、`comp_part1_course.py`、`comp_part2_judge.py`、`comp_import_course_diag.py`、`comp_score.py` 均为当前修复后版本。

### 四份产物与 HASHES
四份产物的 manifest/trials/summary 均列在 `comp/audits/HASHES.json`，且 hash 匹配：

- `flat-ft-2500-part1-diag-v2`
- `flat-ft-2500-part2-diag-v2`
- `flat-ft-2500-part2-official-diag`
- `flat-ft-2500-part1-course-diag`

`HASHES.json` 仍为 `audited=false / verdict=pending`，这是 G1 前状态，不是本轮 blocker。

## 3. 是否仍有 blocker 或“无问题”验收必须清理项

**无 blocker。**

非阻塞清理建议，不阻止本轮 flash 验收：

- `comp_import_selftest.py` 未纳入 `comp_audit_hashes.py` 的 `OBJECTS`，因此未出现在 `HASHES.json`；修复后的 `comp_import_course_diag.py` 本身已入 HASHES。建议 G1 前顺手把 selftest 纳入审计对象。
- `comp_import_selftest.py` 可再调用 `comp_score.py` 断言全 skipped 产物为 `diagnostic`；当前靠静态推导成立。
- `comp/CONTRACT.md §6` 仍列 V1 场景/旧 judge，属文档清理。
- `comp/eval/_protocol.md` 仍 draft，未冻结正式 `protocol_version`。
- `comp_score.py` 顶部重复 `import tempfile`，非阻塞。
- `HASHES.json` 仍 `audited=false / verdict=pending`，G1 结论后更新。

## 4. 是否满足“进入 Codex 前的 flash 验收（无问题）”

**yes。**

### G1 必写残余

- 砂砾坑真实几何未 recut，当前仍是凸起盒代理。
- Part2 官方能力场逐档交叉核对未完成，本地为同种类参数化 level。
- Part1 soft-reset 阈值与相邻 zone 重叠仍是启发式。
- 正式手动/操作手 3 次整场演练未在真实赛程完成；当前为脚本化诊断与 pause/resume/abort 演练。
- T 台阶“上/下 ↔ s/n/e”映射建议最终书面确认。
- Part2 official 重复最高档在确定性策略下统计意义有限。
- 跨 attempt 模拟器时间重置后，事件时间线不能全局排序。
- Part1 单障碍诊断 importer 的 per-obstacle 汇总口径仅用于诊断，正式以 course importer 为准。
- Part2 稳定性 ≥100 次、目标 0 失败未执行；`comp/eval/_calibration/` 人工标定集仍为空。
- 协议仍为 draft，未冻结正式 `protocol_version`。
- `HASHES.json` 仍为 `audited=false / verdict=pending`，需 G1 结论后更新。
- 非阻塞审计完整性建议：将 `comp_import_selftest.py` 纳入 HASHES/审计对象。
