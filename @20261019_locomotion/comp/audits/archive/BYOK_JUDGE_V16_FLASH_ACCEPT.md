verdict：**FAIL**

> 说明：以下按函数/变量名定位；artifact 未给行号，我不臆造行号。

## 1. 3 项逐项

① `final_time_s` 复算排除 skipped trial：**原问题已修，但 skipped 处理未闭环。**  
`comp_score.py::validate_external_evidence` 的 `by_attempt` 汇总段已用  
`best_records = [r for r in by_attempt.values() if r["score"] == best and not r["skipped"]]`，  
因此 skipped attempt 的 `duration_s=0` 不会再直接把 `final_time_s` 拉到 0；self-test 的 `trials3_skipped` 也覆盖了这个断言。  
**但**同一段里 `best = max(r["score"] for r in by_attempt.values())` 仍把 skipped trial 的 judge score 计入；`validate_summary` 的 Part1 `succ_trials` 也未过滤 `skipped`。这会产生新的正式链路 blocker（见 §4）。

② formal `attempts_used>0` 但 trials 为空：**已修。**  
`comp_score.py::validate_external_evidence` 中 `p1_attempts` 用 set 去重，随后有  
`if not diagnostic and reported_p1 > 0 and not p1_attempts: _err(...)`；  
并且 `reported_p1 != len(p1_attempts)` 做双向对账。formal 下 `attempts_used>0` 且无可复算 Part1 attempt 会报 error。

③ conformance n/e 臂用例：**已修。**  
`comp_judge_conformance.py::test_t_stairs_full_partial_and_history` 的 n 臂序列中，`step:s:1` 放在 `y=-5.3`，落在 `ZONES["t_stairs"]` 下界 `-4.95` 之外，因此 s 臂只记录 `{2,3}`，不完整；e 臂序列的 s 臂只记录 `{1,3}`，也不完整。  
所以 `complete == [arm]` 与 `score == 33.0` 对 n/e 单臂成立。`TStairs` 默认值也仍是 `partial_up=50.0 / partial_down=33.0`。

## 2. conformance / self-test / HASHES

- `comp_judge_conformance.py` 的 13 组测试列表完整；按给定源码静态复核，n/e 臂目标断言可通过，未发现会使 13 组失败的直接矛盾。  
  但 artifact 中没有本轮 stdout/测试报告，`HASHES.json` 只记录 hash，不能独立证明“实际执行过”；只能证明代码可复算。
- `comp_score.py --self-test` 的既有用例按源码静态复核可通过；但它**没有覆盖“skipped attempt 带正分”**的场景，因此不能证明 skipped 处理已无问题。
- `HASHES.json` 为 62 objects 可复算：26 个 `OBJECTS` + 19 个 level XML + 12 个 eval 产物（4 目录 × manifest/trials/summary）+ 2 个额外场景 + 3 个 evidence drill = 62。  
  四份产物 hash 均与 HASHES 一致：
  - `flat-ft-2500-part1-diag-v2`：`4476…/1cf4…/bc12…`
  - `flat-ft-2500-part2-diag-v2`：`3dcc…/2e21…/13a9…`
  - `flat-ft-2500-part2-official-diag`：`ca98…/fa76…/e2b2…`
  - `flat-ft-2500-part1-course-diag`：`604c…/f5fb…/74ca…`
  - 两个 Part2 场景与三份 evidence drill 也在 HASHES 中且 hash 匹配。  
  注意 `HASHES.json` 仍是 `audited=false`、`verdict=pending`，这是 G1 前状态，不是最终 G1 结论。

## 3. 历史 PASS 项回归

未发现 N1–N4 / P1–P4 / HighWall / TStairs / HASHES 的历史 PASS 项回归：

- **N1**：`run_part1_course.py::run_policy_step` 每个物理步后 `feed()`，不是每 20 ms 才采样。
- **N2**：`comp_import_course_diag.py` 用每次 `attempt_result` 选 best，不用全局 session summary。
- **N3**：`Part1Course.summary` / `AttemptManager.summary` 的 `final_time_s` 仍是最高分尝试内最快 duration；`final_time_scope` 存在。
- **N4**：`comp_score.curve_points` 与 `comp_part2_judge.curve_points_floor` 的 bool 仍只认 `value == 1.0`。
- **P1**：`StableStopTracker` 使用真实物理 dt（`model.opt.timestep`）。
- **P2**：暂停循环只推进 operator 事件/超时，不重复 `course.update`。
- **P3**：`validate_external_evidence` 已接入 `score_one`；外部 hash、Part2 合法档位、Part1 final_time 均在校验链中。  
  但 P3 内部 skipped 处理仍有新缺口，见 §4。
- **P4**：`comp_part1_geom_tags.is_ground_geom()` 仍被两个 Part1 runner 共用。
- **HighWall**：`WALL_X_MIN=1.30 / WALL_X_MAX=2.30` 仍生效；`outside_x_cross` 用例仍打中修复分支。
- **TStairs**：`_score_for` 仍为两臂 100、s 单臂 50、n/e 单臂 33；partial→full 升级逻辑仍在。

## 4. 新问题 / “无问题”验收必须清理项

### 正式链路 blocker：skipped trial 在 comp_score 中未统一排除

1. **`comp_score.py::validate_summary` 的 Part1 失败分支**  
   `succ_trials = [t for t in obs_trials if (t.get("judge") or {}).get("status") == "success"]`  
   没有过滤 `t.get("skipped")`。  
   后果：
   - 合法 formal 中，若某次 attempt 被 abort/skip 前已有障碍 success，而 summary 取另一次非 skipped 的 best attempt 且该障碍失败，`succ_trials` 仍含 skipped 成功记录，合法 summary 会被误判为 “标 fail 但 trials 中存在 success”。
   - 反过来，若 summary 把 skipped attempt 的 success trial 当作 evidence，当前只检查 `judge.status=="success"`，不检查 `skipped`，存在把已跳过 attempt 计分的假成功风险。

2. **`comp_score.py::validate_external_evidence` 的 `by_attempt` 复算**  
   `best = max(r["score"] for r in by_attempt.values())` 仍包含 skipped attempt 的分数；只有 `best_records` 过滤了 `skipped`。  
   后果：若 abort attempt 已有正分且高于完成 attempt，`best` 取 skipped 分，`best_records` 为空，`expected=0`，合法 `final_time_s/final_score` 会被误判；同时没有机器拒绝 “skipped attempt 计分”。

这是正式 Part1 整场链路的 blocker，尤其是规则允许主动 abort/重跑，且 abort 前可能已有障碍成功。当前四份诊断产物未触发，是因为 course diag 全是非 skipped，abort drill 的 skipped 分数为 0；不能据此认为 formal 链路完整。

### 最小修复
- 在 `comp_score.validate_summary` 的 Part1 success 证据与 `succ_trials` 中排除 `skipped=true` 的 trial；Part1 success evidence 指向 skipped trial 时应报 error。
- 在 `comp_score.validate_external_evidence` 的 `by_attempt` 汇总中不要累计 skipped trial 的 score/seen，或至少在 `best` 计算前排除 skipped；全 skipped 时保持 `final_score=0/final_time_s=0`。
- 或在 `comp_import_course_diag.py` 对 skipped attempt 的 trial 显式写 `judge.status="skipped"`、`score=0`，并保证 comp_score 同口径。二者必须一致。
- 增加 self-test：skipped attempt 带正分 + 后续完成 attempt 较低分，summary 取完成 attempt 时应 valid；skipped 正分不得作为 evidence。

### 非阻塞备注
- `comp_part1_judge.py::HighWall` 的 `WALL_CLIMB_Z=0.55` 仍未实际使用，实际阈值是字面量 `0.60`。
- `comp/CONTRACT.md` §6 资产表仍列 V1 场景/旧 judge，机器契约与 HASHES 已用 V2，建议 G1 文档清理。
- n 臂 conformance 通过依赖 `step:s:1` 落在 zone 外这一几何事实，建议注释写清，避免未来 zone 调整后测试脆弱。
- `comp/eval/_protocol.md` 仍是 draft，未冻结正式 `protocol_version`。

## 5. 是否满足“进入 Codex 前的 flash 验收（无问题）”

**no。**

虽然第 15 轮 pro 的 3 个指定项中，② formal 空 trials、③ n/e conformance 已修，① 的 `final_time_s` 子问题已修；但 skipped trial 在 `comp_score` 的 Part1 evidence / best-score 复算中仍未统一排除，存在正式链路误判与假成功风险。必须先按 §4 最小修复，重跑 conformance 与 `comp_score --self-test`（补 skipped 正分用例），刷新 HASHES，再走 flash/pro 复验。

## 6. G1 必写残余

- 砂砾坑真实几何未 recut，当前仍是凸起盒代理。
- Part2 官方能力场逐档交叉核对未完成，本地为同种类参数化 level。
- Part1 soft-reset 阈值与相邻 zone 重叠仍是启发式。
- 正式手动/操作手 3 次整场演练未在真实赛程完成；当前为脚本化诊断与演练。
- T 台阶“上/下 ↔ s/n/e”映射建议最终书面确认。
- Part2 official 重复最高档在确定性策略下统计意义有限。
- 跨 attempt 模拟器时间重置后，事件时间线不可全局排序。
- Part1 单障碍诊断 importer 的 per-obstacle 汇总口径仅用于诊断，正式仍以 course importer 为准。
- Part2 稳定性 ≥100 次、目标 0 失败未执行。
- `comp/eval/_calibration/` 人工标定集仍为空。
- 协议仍为 draft，未冻结正式 `protocol_version`。
- `HASHES.json` 仍为 `audited=false / verdict=pending`，需 G1 结论后更新。
