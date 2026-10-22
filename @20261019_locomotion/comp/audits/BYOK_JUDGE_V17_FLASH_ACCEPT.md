verdict：**FAIL**

> 说明：artifact 未附行号；以下用“文件::函数/代码段”定位，不臆造行号。

## 1. skipped 逐项结论

| 项 | 结论 | 依据 |
|---|---|---|
| best score 排除 skipped | **部分闭环，仍有缺口** | `comp_part1_course.py::AttemptManager.summary` 用 `scored = [a for a in attempts if not skipped]`，正确；`comp_import_course_diag.py::main` 选 best 时跳过 `rec.skipped`，正确。但 `comp_score.py::validate_external_evidence` 的 `by_attempt` 段先 `setdefault(... "skipped": False)`，之后才 `if t.get("skipped"): continue`，所以 skipped trial 仍会创建一个 `skipped=False` 的零分 attempt 记录。 |
| final_time 排除 skipped | **未完全闭环，存在 blocker** | 同上。`rec["skipped"]` 在 `by_attempt` 中**从未被置为 True**，因此 `best_records = [r for ... and not r["skipped"]]` 实际无效。若最高分为 0，skipped attempt 的 `duration_s=0` 会进入 `best_records`，导致 `expected = 0`；合法“非 skipped 完成尝试 0 分、用时 10 s”会被误判，反过来 summary 写 `final_time_s=0` 也可能被错误接受。 |
| evidence | **基本闭环** | `comp_score.py::validate_summary` 中 success evidence 指向 `t.get("skipped")` 会报 error；`succ_trials` 已排除 skipped。 |
| succ_trials | **闭环** | `succ_trials = [t for t in obs_trials if not t.get("skipped") and judge.status == "success"]`。 |
| importer 对 skipped trial 写 status/score | **trial 层闭环** | `comp_import_course_diag.py::main` 对 skipped attempt 强制 `status="skipped"`、`score=0`，trial 也写 `skipped=true`、`duration_s=0`。 |
| 全 skipped 的 summary | **未完全闭环** | `comp_import_course_diag.py::main` 全 skipped 时 `best_idx=0`，仍从第一个 skipped attempt 的 `judge.states` 取 `best_states`。若该 skipped attempt 在 abort 前已有障碍 success，summary 仍可能写入 success/正分，而 trials 全是 skipped/0 分，随后 `comp_score` 会因缺 evidence 判 invalid；合法“全 skipped=0/0”不稳健。 |
| self-test | **有覆盖但不足** | 已有 skipped 正分 + 后续完成 attempt 用例；但**缺** “skipped attempt 0 分 + 完成 attempt 0 分”的同分场景，也缺“全 skipped 但 judge 状态含 success”的 importer 场景。 |

**可利用路径结论：**  
skipped 正分已不会直接计入 best score，但 **final_time 仍可被 skipped 的 0 时长污染**；存在“最高分 0 时，错误接受 final_time=0”的路径，也存在“合法 0 分完成尝试被误判 invalid”的路径。因此 skipped 语义**未闭环**。

## 2. conformance / self-test / 历史 PASS / HASHES

- **conformance 13 组：静态复核应可通过。**  
  `comp_judge_conformance.py::main` 列出的 13 组完整；`test_t_stairs_full_partial_and_history` 的 n 臂 `step:s:1` 在 `y=-5.3`，落在 `ZONES["t_stairs"]` 的 y 下界 `-4.95` 之外，故 s 臂不完整；e 臂序列缺 `s:2`，也只完整 e 臂。按当前源码，n/e 单臂应得 33。  
  **但 artifact 没有本轮 stdout/测试日志，不能形式证明实际执行过；只能说明源码静态可判定。**

- **comp_score self-test：静态复核应可通过，但覆盖不足。**  
  `comp_score.py::run_self_test` 已补 `trials3_skip_pos`，验证 skipped 正分不计入 best/final_time；但没有覆盖“skipped 与完成 attempt 同为 0 分”的 final_time 竞争，所以不能证明 skipped 的 final_time 语义已闭环。

- **历史 PASS 项回归：**  
  未发现 N1–N4、P1–P4、HighWall、TStairs、bool 只认 1、StableStopTracker、pause/resume、HASHES 对象覆盖等历史项的直接回归。  
  但本轮 skipped 修复在 `comp_score.validate_external_evidence` 内出现新的 formal 链路缺口，属于回归/未修净。

- **四份产物与 HASHES：一致。**  
  `flat-ft-2500-part1-diag-v2`、`flat-ft-2500-part2-diag-v2`、`flat-ft-2500-part2-official-diag`、`flat-ft-2500-part1-course-diag` 的 manifest/trials/summary hash 均与 `HASHES.json` 记录一致。  
  HASHES 为 62 objects 可复算；两个 Part2 场景与三份 evidence drill 也在 HASHES 中且匹配。  
  `HASHES.json` 仍是 `audited=false / verdict=pending`，这是 G1 前状态，不是最终结论。

## 3. 新问题 / 必须清理项

### Blocker（正式 Part1 链路）
1. `comp_score.py::validate_external_evidence` 的 `by_attempt`：
   - skipped trial 在 `continue` 之前已被 `setdefault` 创建记录；
   - `rec["skipped"]` 从未置 True；
   - `best_records` 的 `not r["skipped"]` 过滤无效；
   - 最高分 0 时 skipped 的 0 时长会污染 `final_time_s`。

2. `comp_import_course_diag.py::main` 全 skipped 时：
   - `best_idx=0` 仍取第一个 skipped attempt；
   - `best_states` 未清空；
   - abort 前已有 success 时 summary 可能写 success/正分，但 trials 全 skipped/0，导致合法全 skipped 场景 invalid。

### Minor / 清理
- `comp_score.py::validate_trials` 对 skipped 但 `duration_s != 0` 使用 `_warn([], ...)`，警告写入临时列表后丢弃，实际不告警。
- `comp/CONTRACT.md` §6 资产表仍列 V1 场景/旧 judge；机器契约与 HASHES 已用 V2，G1 文档需清理。
- `comp/eval/_protocol.md` 仍是 draft，未冻结正式 `protocol_version`。
- n 臂 conformance 注释写 `ZONES["t_stairs"]` 为 `-4.95..-3.05`，实际源码是 `-4.95..-2.1`；用例仍能过，但注释与代码不一致。
- `HASHES.json` 仍 `audited=false / verdict=pending`，G1 结论后需更新。

## 4. 是否满足“进入 Codex 前的 flash 验收（无问题）”

**no。**

最小修复：
1. `comp_score.py::validate_external_evidence`：在创建 `by_attempt` 记录前排除 skipped trial；或创建后显式 `rec["skipped"]=True` 且不把其 duration 用于 best/final_time。`best` 与 `best_records` 都只基于非 skipped attempt；全 skipped 时保持 `final_score=0/final_time_s=0`。
2. `comp_import_course_diag.py::main`：当没有任何非 skipped attempt 时，`best_rec`/`best_states` 置空，summary 强制 0/0，不得沿用第一个 skipped attempt 的 judge states。
3. `comp_score.py::validate_trials`：skipped 且 `duration_s != 0` 应实际进入 warnings/errors，不能 `_warn([])` 丢弃。
4. 补 self-test：
   - skipped attempt 0 分/0 s + 完成 attempt 0 分/10 s，summary `final_time_s=10` 应 valid；写 0 应 invalid；
   - 全 skipped 且 skipped attempt 的 judge 状态含 success，summary 仍应为 0/0。
5. 重跑 conformance、`comp_score --self-test`，刷新四份产物与 HASHES 后再复验。

## 5. G1 必写残余

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
- 本轮 skipped 的 `by_attempt`/全 skipped importer 修复完成前，不得把 Part1 正式链路视为闭环。
