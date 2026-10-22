verdict：**FAIL**

> artifact 未附行号；以下按“文件::函数/代码段”定位，不臆造行号。

## 1. skipped 语义逐项结论

| 项 | 结论 | 依据 |
|---|---|---|
| best score 排除 skipped | **闭环** | `comp_part1_judge.py::AttemptManager.summary` 用 `scored = [a for a in attempts if not a.get("skipped")]`；`comp_import_course_diag.py::main` 选 best 时 `if rec.get("skipped"): continue`；`comp_score.py::validate_external_evidence` 的 `by_attempt` 已先 `if t.get("skipped"): continue`，再 `setdefault`，skipped 不再创建 `skipped=False` 的零分记录。 |
| final_time 排除 skipped | **comp_score 侧闭环；importer 全 skipped 路径不闭环** | `comp_score.py::validate_external_evidence` 的 `by_attempt` 已完全跳过 skipped，`best_records` 只含非 skipped；`trials_zero` / `trials3_skip_pos` 自检覆盖了“skipped 0 秒不得污染完成 attempt 的 10 秒”。但 `comp_import_course_diag.py::main` 全 skipped 时仍先从第一个 skipped attempt 取 `best_states` 计算 `part1_obstacles`/`sum1`，见下。 |
| evidence | **闭环** | `comp_score.py::validate_summary` 的 `succ_trials` 已排除 `t.get("skipped")`；evidence 指向 skipped trial 会 `_err(... "指向 skipped attempt")`。 |
| succ_trials | **闭环** | 同上，`succ_trials = [t for t in obs_trials if not t.get("skipped") and judge.status == "success"]`。 |
| importer 对 skipped trial 写 status/score | **trial 层闭环** | `comp_import_course_diag.py::main` 对 skipped attempt 强制 `status="skipped"`、`score=0`、`duration_s=0`、`skipped=true`。 |
| 全 skipped summary | **未闭环，仍有可利用/误判路径** | `comp_import_course_diag.py::main` 的 `non_skipped` 判断与 `best_states = {}` 出现在 `part1_obstacles`、`sum1`、`all_full`、`return_bonus` 计算之后，是**事后置空/dead assignment**。若第一个 skipped attempt 在 abort 前已有障碍 `success`，`part1_obstacles` 仍会写入 success/正分，`part1.total` 非 0，而 trials 全是 skipped/0；随后 `comp_score` 会因 success 缺非 skipped evidence 判 invalid。合法“全 skipped=0/0”不稳健。 |
| self-test | **覆盖不足** | `comp_score.py::run_self_test` 已补 skipped 正分、skipped 0 秒 + 完成 0 分 10 秒场景；但**缺**“全 skipped 且 skipped attempt 的 judge states 含 success”的 importer 场景，也没有 importer 自检。 |

**结论：skipped 语义未完全闭环。**  
`comp_score` 的 `by_attempt`/`best_records`/`final_time` 污染路径已修；但正式 Part1 整场 importer 的全 skipped 分支仍复用 skipped judge states，导致合法全 skipped 产物可能被写成“有 success/正分但无 evidence”的 invalid 产物。

## 2. conformance 13 组、comp_score self-test、历史 PASS、HASHES

- **conformance 13 组：源码静态复核应通过。**  
  `comp_judge_conformance.py::main` 仍列 13 组；`test_t_stairs_full_partial_and_history` 的 n/e 单臂仍通过“s 臂缺少完整 1/2/3 级”得到 33，s 单臂仍为 50；HighWall 的 `outside_x_cross`、ground-height crossing 用例仍打中修复分支；bridge/height_bar/slalom/slope/gravel 用例逻辑未见直接矛盾。  
  **但 artifact 没有本轮 stdout/测试日志，不能形式证明实际执行过；只能说明源码静态可判定通过。**

- **comp_score self-test：静态复核应通过，但覆盖仍不足。**  
  `run_self_test` 已包含 `trials3_skip_pos`（skipped 正分不计入 best/final_time）与 `trials_zero`（skipped 0 秒 + 完成 0 分 10 秒，final_time 必须为 10）。按源码应通过。  
  仍缺：全 skipped + skipped judge states 含 success 的 importer/summary 场景。

- **历史 PASS 项回归：未发现 N1–N4、P1–P4、HighWall、TStairs、bool 只认 1、StableStopTracker、pause/resume 的直接回归。**  
  相反，`comp_score.validate_external_evidence` 的 skipped 过滤顺序已修正。当前问题不是历史项回归，而是本轮“全 skipped importer”修复未真正生效。

- **四份产物与 HASHES：一致。**  
  `flat-ft-2500-part1-diag-v2`、`flat-ft-2500-part2-diag-v2`、`flat-ft-2500-part2-official-diag`、`flat-ft-2500-part1-course-diag` 的 manifest/trials/summary hash 均与 `comp/audits/HASHES.json` 一致；HASHES 为 62 objects 可复算；两个 Part2 场景与三份 evidence drill 也在 HASHES 中且匹配。  
  `HASHES.json` 仍 `audited=false / verdict=pending`，这是 G1 前状态，不是最终结论。

## 3. 仍有 blocker / “无问题”验收必须清理项

### Blocker（正式 Part1 整场链路）
1. **`comp_import_course_diag.py::main` 全 skipped 分支的置空顺序错误。**  
   代码顺序是：先由 `best_states` 计算 `part1_obstacles`/`sum1`/`all_full`/`return_bonus`，之后才：
   - `session = {"final_score": 0.0, "final_time_s": 0.0}`
   - `best_rec = {}`
   - `best_states = {}`  
   因此 `best_states = {}` 对已计算的 `part1_obstacles` 和 `sum1` 无效。若第一个 skipped attempt 的 judge states 含 success，summary 仍会写 success/正分、`part1.total` 非 0，但 evidence 为空；`comp_score` 会判 invalid，而不是合法的 0/0。  
   这与第 17 轮要求的“全 skipped importer 置空 best_states 并强制 0/0”不一致。

2. **缺少 importer 全 skipped + success states 的测试。**  
   `comp_score.py::run_self_test` 覆盖了 comp_score 侧，但没有覆盖 `comp_import_course_diag.py` 本身；现有 abort drill 的全 skipped attempt 状态全是 `pending`，所以没有触发该路径。必须补一个“第一个 skipped attempt judge states 含 success/正分”的 importer fixture，断言 summary 为 0/0、obstacles 全 false、evidence 为空。

### Minor / G1 文档清理
- `comp/CONTRACT.md` §6 资产表仍列 V1 场景/旧 judge；机器契约和 HASHES 已用 V2，G1 文档需清理。
- `comp/eval/_protocol.md` 仍是 draft，未冻结正式 `protocol_version`。
- `HASHES.json` 仍 `audited=false / verdict=pending`，G1 结论后需更新。
- `comp_score.py` 顶部重复 `import tempfile`，非阻塞清理。
- n 臂 conformance 注释与 `ZONES["t_stairs"]` 实际范围仍建议在 G1 文档中写清，避免未来 zone 调整后测试脆弱。

## 4. 是否满足“进入 Codex 前的 flash 验收（无问题）”

**no。**

### 最小修复
1. **`comp_import_course_diag.py::main`**：在计算 `part1_obstacles` 之前先判定是否存在非 skipped attempt；若没有，立即置空 `best_states`/`best_rec`，并强制：
   - `part1_obstacles` 全 `success=false, score=0`
   - `sum1=0`
   - `return_bonus=0`, `return_evidence=None`
   - `part1.total=0`, `grand_total=0`
   - `final_score=0.0`, `final_time_s=0.0`  
   不能只在循环之后置空 `best_states`。

2. **补 importer 自检/fixture**：全 attempts skipped，且第一个 skipped attempt 的 judge states 含 success/正分；断言导入后的 summary 仍为 0/0、obstacles 全 false、evidence 为空，`comp_score` 判 valid/diagnostic 而不是 invalid。

3. 重跑 conformance、`comp_score --self-test`，刷新四份产物与 HASHES 后再复验。

## G1 必写残余

- 砂砾坑真实几何未 recut，当前仍是凸起盒代理。
- Part2 官方能力场逐档交叉核对未完成，本地为同种类参数化 level。
- Part1 soft-reset 阈值与相邻 zone 重叠仍是启发式。
- 正式手动/操作手 3 次整场演练未在真实赛程完成；当前为脚本化诊断与演练。
- T 台阶“上/下 ↔ s/n/e”映射建议最终书面确认。
- Part2 official 重复最高档在确定性策略下统计意义有限。
- 跨 attempt 模拟器时间重置后，事件时间线不可全局排序。
- Part1 单障碍诊断 importer 的 per-obstacle 汇总口径仅用于诊断，正式以 course importer 为准。
- Part2 稳定性 ≥100 次、目标 0 失败未执行；`comp/eval/_calibration/` 人工标定集仍为空。
- 协议仍为 draft，未冻结正式 `protocol_version`。
- `HASHES.json` 仍为 `audited=false / verdict=pending`，需 G1 结论后更新。
- **本轮新增**：`comp_import_course_diag.py` 全 skipped + skipped judge states 含 success 的路径修复完成前，不得把 Part1 正式整场链路视为 skipped 语义闭环。
