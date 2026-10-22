**verdict：CONCERN**  
未发现新的 scorer blocker，但第 9 轮 5 项中仍有 **2 项未完全闭合**，因此不满足“进入 Codex 前的 flash 验收（无问题）”。

---

## 一、第 9 轮 5 项逐项结论

| # | 结论 | 代码/证据依据 |
|---|---|---|
| ① attempt/event 快照深拷贝并重生成证据 | **PASS** | `comp_part1_course.py::Part1Course.summary` 对 `attempts/events/attempt_results` 做了 `json.loads(json.dumps(...))` 深拷贝；`comp/audits/evidence/part1_course_pause_resume_drill.json` 中 attempt 1 的 `report.summary.attempts` 只含 attempt 1，后续 attempt 未回写污染；attempt 2 含 1–2 是当时 session 快照，未被 attempt 3 追改。 |
| ② official Part2 summary 纳入 HASHES | **PASS** | `comp_audit_hashes.py::main` 对四个 eval 目录循环 `manifest.json/trials.jsonl/summary.json`；`HASHES.json` 存在 `eval_flat-ft-2500-part2-official-diag_summary`，其 sha256=`e2b277...` 与 `summary.json` 文件头一致。 |
| ③ formal Part2 attempts_used 与 trials 不一致报错 | **STILL-BROKEN（主路径已修，但仍可绕过）** | `comp_score.py::validate_summary` 已把非 diagnostic 的不一致改为 `_err`，但它仍写成 `if obs_trials and ... != len(obs_trials)`。若 formal summary 写 `attempts_used=4` 而 `trials.jsonl` 中该 Part2 obstacle **0 条**，`obs_trials=[]`，条件短路，不报错；`validate_external_evidence` 的 `part2_has_evidence` 仍可由 summary 的 `attempts_used>0` 触发，只要求 scenes，不强制 trials。这是正式证据链缺口。 |
| ④ fixes 文档补第 8 轮记录 | **PASS** | `BYOK_JUDGE_V2_FIXES.md` 已有“Flash 验收（第 8 轮）后修复（2026-10-23）”节；虽排在第 9 轮节之后，但记录存在。 |
| ⑤ official trial_id 命名 / pause_timeout operator_t | **STILL-BROKEN** | ① `comp_import_part2_diag.py` 中 `trial_id` 仍用局部 `for i, run in enumerate(att.get("attempts")...)` 的 `i`；official 每条 record 只有一次 run，`i` 恒为 1，24 条仍全是 `...-a1-rN`。显式 `attempt` 字段 1–4 正确，但 trial_id 的 `aN` 仍有歧义。② `run_part1_course.py` 在 `pause_timeout` 时先 `course.abort_attempt(fake, "pause_timeout")`，再向 `course._current_events` append `pause_timeout` 事件；而 `comp_part1_course.py::abort_attempt` 已在内部 `events=list(self._current_events)` 复制并落入 `AttemptResult`，所以该 `operator_t` 事件不会出现在导出的 attempt_result 中，`manager.skip` 也没有 `operator_t`。 |

---

## 二、N1–N4 / P1–P4 与历史 PASS 项回归

均 **仍 PASS，未见回归**：

- **N1**：`run_part1_course.py::run_policy_step` 每 4 个物理步逐步 `physics_step()` 后 `feed()`。
- **N2**：`comp_import_course_diag.py` 用 per-attempt `attempt_result`，按 `(score, -duration)` 选 best。
- **N3**：`Part1Course.summary` 与 `AttemptManager.summary` 均为最高分内取最快，并写 `final_time_scope`。
- **N4**：`comp_score.curve_points` 与 `comp_part2_judge.curve_points_floor` 均 `float(value) == 1.0` 才给 bool 分。
- **P1**：`run_part1_course.py::run_attempt` 用 `dt_phys = cpr.model.opt.timestep` 更新 `StableStopTracker`。
- **P2**：暂停循环只推进 operator 时钟和 `apply_events`，不调用 `course.update`。
- **P3**：`comp_score.score_one` 已调用 `validate_external_evidence`，检查 contract/scenes/judge hash、Part2 合法档位、Part1 final_time 复算。
- **P4**：`comp_part1_geom_tags.GROUND_GEOM_NAMES` 为精确白名单，`is_ground_geom()` 不再 `startswith("ground")`。

四份 eval 产物（part1-diag-v2、part2-diag-v2、part2-official-diag、part1-course-diag）的 manifest/trials/summary 均已在 `HASHES.json`；给定文件头 sha256 与 HASHES 条目一致，未发现 mismatch。`HASHES.json` 的 `audited:false / verdict:pending` 符合 G1 前状态，不是本轮 blocker。

---

## 三、新问题 / 是否仍有 blocker

**没有新的 scorer blocker。**  
但按“无问题”标准，仍有必须清理项：

1. **formal Part2 空 trials 仍可绕过 attempts 对账**：`validate_summary` 的 `obs_trials and ...` 条件导致 `attempts_used>0`、trials 0 条时不报错。  
2. **official trial_id 的 `a1` 命名仍歧义**：显式 `attempt` 正确，但 trial_id 未编码真实 attempt。  
3. **pause_timeout 的 `operator_t` 未进入最终 `AttemptResult.events`**：当前 append 时机晚于 `abort_attempt` 的拷贝。

---

## 四、是否满足“进入 Codex 前的 flash 验收（无问题）”

**no。**

最小修复：

1. `comp_score.py::validate_summary`：formal 下改为无条件核对 `attempts_used == len(part2 trials for obstacle)`；至少当 `attempts_used>0` 时 trials 必须非空。  
2. `comp_import_part2_diag.py`：official trial_id 使用真实 `attempt`，如 `...-a{attempt}-r{trial_seq}`；或明确废弃 `aN` 解析并写进 G1 说明。  
3. `run_part1_course.py`：在 `abort_attempt("pause_timeout")` 前把 timeout 事件加入 `_current_events`，或让 `abort_attempt/skip` 接收 extra event，确保 `AttemptResult.events` 和 manager 事件均含 `operator_t`；补一次 pause_timeout 演练并刷新 HASHES。  
4. 修完后重跑 flash 验收；当前只能判 **CONCERN**。

---

## 五、G1 必写残余风险

1. Q2 已确认 ×2/3：T 台阶两侧 100、仅上 50、仅下 33；返回奖励只认单项满分。  
2. 分数最高优先、同分取最快；稳定停表；恢复不消耗尝试。  
3. 返回奖励必须“全部障碍满分后重新进入出发区”。  
4. Part2 仅 RL、每项 4 次；official 重复最高档在确定性策略下稳定性统计意义有限，需说明“4 次中的重复档”口径。  
5. Part1 手动/自动均允许，自动无加分；正式手动 3 次演练仍未在真实赛程上做，当前主要是脚本化诊断。  
6. 砂砾坑真实“坑+碎木”几何未 recut，本地仍为凸起盒代理。  
7. Part2 官方能力场未逐档交叉核对，本地为同种类参数化 level。  
8. soft-reset 阈值与相邻 zone 重叠仍是启发式。  
9. 每个 attempt 新建 runner，模拟器时间从 0.5 重置，跨 attempt 事件时间线不可全局排序。
