- **verdict：CONCERN**。  
  当前没有发现新的 scorer blocker；第 8 轮 4 项技术清理基本都已落地。但按“进入 Codex 前 flash 验收（无问题）”标准，仍有审计/证据覆盖问题，**不建议标为无问题 PASS**。

---

## 一、第 8 轮 4 项逐项

| # | 结论 | 代码/证据依据 |
|---|---|---|
| ① Part2 official attempt 1–4、24 条落盘证据 | **PASS** | `run_part2_judged_eval.py::main` 的 official 分支每 category 生成 4 个 entry，并用 `official_counter[cat]` 写 `attempt_index`；`comp_import_part2_diag.py` 用 `"attempt": int(att.get("attempt_index") or i)` 落盘。`flat-ft-2500-part2-official-diag/trials.jsonl` 共 24 条，六类各 4 条，`attempt` 均为 category 内 1–4；`summary.json` 六类 `attempts_used` 均为 4。 |
| ② abort/pause/resume/skip 事件 fake 时钟 | **PASS** | `comp_part1_course.py::pause` 用 `last_sim_t`；`resume` 用 `sim_t = float(self.last_sim_t)` 闭合 pauses 并写 `manager.events`；`abort_attempt` 用 `last_sim_t` 调 `manager.skip(sim_t, ...)`；`skip_obstacle` 也写 `last_sim_t`。证据 `part1_course_pause_resume_drill.json` 中 pause/resume 的 `t` 均为 `1.0000000000000007`，`operator_t` 才是 `2.0`；abort drill 中 skip 的 `t=3.004999999999958`，不是 fake `3.0`。 |
| ③ comp_score 重复 trial_id、_check_hash 非 dict、Part1-only manifest | **PASS** | `comp_score.py::validate_trials` 已加 `if tid in ids: _err("trials 重复 trial_id...")`；`_check_hash` 开头有 `if not isinstance(entry, dict): ... return`；`validate_external_evidence` 用 `part2_has_evidence` 决定是否强制 `scenes.part2`，不再无条件要求 Part2 levels。 |
| ④ 空条目/level hash 篡改/重复 trial_id 自检 | **PASS** | `comp_score.py::run_self_test` 已包含：`man_empty["judge"]["file_hashes"] = [{}]`、`man_level_empty["scenes"]["part2"]["levels"] = [{}]`、`man_level_bad` 篡改 level sha、`dup_root/trials.jsonl` 重复 trial_id 并断言报错。 |

> 备注：`BYOK_JUDGE_V2_FIXES.md` 实际最后只有“Flash 验收（第 7 轮）后修复”，没有第 8 轮修复记录节；这不影响上述技术核对，但属于审计追溯缺口。

---

## 二、N1–N4、P1–P4 回归

| 项 | 结论 | 依据 |
|---|---|---|
| N1 逐物理步采样 | **PASS** | `run_part1_course.py::run_policy_step` 每 policy step 后 `for _ in range(4): physics_step(); feed()`。 |
| N2 per-attempt best | **PASS** | `comp_import_course_diag.py::_att_rec` 读 `attempt_result`，按 `(score, -duration)` 选 best。 |
| N3 最高分内取最快 | **PASS** | `Part1Course.summary` 与 `AttemptManager.summary` 均先取最高分，再在最高分 attempt 内取 `min(duration_s)`，并写 `final_time_scope`。 |
| N4 bool 只认 1.0 | **PASS** | `comp_score.curve_points` 与 `comp_part2_judge.curve_points_floor` 均为 `float(value) == 1.0` 才给 bool 分。 |
| P1 stable-stop 物理 dt | **PASS** | `run_part1_course.py::run_attempt` 用 `dt_phys = float(cpr.model.opt.timestep)` 传给 `StableStopTracker.update`。 |
| P2 暂停不喂 judge | **PASS** | 暂停循环只推进 operator 时钟和 `apply_events`，不调用 `course.update`；`if not course.active: return False` 可外传 abort。 |
| P3 外部证据校验接线 | **PASS（主路径）** | `comp_score.score_one` 已调用 `validate_external_evidence(..., trials)`；hash、Part2 合法档位、Part1 final_time 复算均接线。 |
| P4 ground 分类 | **PASS** | `comp_part1_geom_tags.GROUND_GEOM_NAMES` 为精确白名单；`is_ground_geom()` 不再 `startswith("ground")`；conformance 仍断言 bridge/slope/step 不是 ground。 |

前几轮 judge 语义、场景 tag 映射、course 协议、Part2 evaluator 的 PASS 项未看到回归；`comp_part1_judge.py` 等关键 hash 与 HASHES 一致。

---

## 三、新问题清单（非 scorer blocker，但影响“无问题”验收）

1. **[medium] Part1 course 演练证据的 per-attempt report 存在共享引用污染。**  
   `comp_part1_judge.py::AttemptManager.summary` 返回 `"attempts": self.attempts`、`"events": self.events`（列表引用，不深拷贝）；`run_part1_course.py::run_attempt` 每个 attempt 后保存 `course.export_report()`。最终序列化时，早先 attempt 的 `report.summary.attempts/events` 会包含后续 attempt。证据中可直接看到：`part1_course_pause_resume_drill.json` 的第 1 次 attempt 里 `attempts_used=1`，但 `attempts` 列表含 attempt 1/2/3，`events` 也含全部三次事件。  
   → 影响 course 证据的 attempts/event 对账，不影响当前 scorer 主路径。最小修复：`summary()` 或 `export_report()` 对 `attempts/events` 做快照/深拷贝，再重生成 pause/abort 演练与 HASHES。

2. **[medium] HASHES 对象数 55，但 official Part2 summary 未入 HASHES。**  
   `HASHES.json` 当前有 55 个 objects，包含 `flat-ft-2500-part2-official-diag/manifest.json` 与 `trials.jsonl`，但未包含 `comp/eval/flat-ft-2500-part2-official-diag/summary.json`。`comp_audit_hashes.py` 的 loop 只对四个 eval 目录取 `manifest.json/trials.jsonl`；而其它 diag 的 summary 是显式 object。  
   → 不影响 24 条 official trials 的 attempt 对账，但 official 计分 summary 未被审计 hash 固定。最小修复：把 official summary 加入 `comp_audit_hashes.py` 并重生成 HASHES（或明确在 G1 说明其为非审计对象）。

3. **[medium] formal Part2 evidence 判定仍依赖 summary，可被不一致 summary 绕过。**  
   `validate_external_evidence` 的 `part2_has_evidence` 来自 summary 的 `attempts_used/best_success_value`；`validate_summary` 中 Part2 `attempts_used` 与 trials 条数不一致目前只是 `_warn`，formal 下也不报错。若 formal summary 把 Part2 `attempts_used` 写成 0、但 trials 有 Part2 fail 记录，可规避 `scenes.part2.levels` 强制。  
   → 当前 official 产物 summary 正确（4/4/4/4/4/4），不是当前 blocker；建议 formal 下把 mismatch 改为 error，或同时从 trials 推断 Part2 evidence。

4. **[low] official trial_id 命名仍有 `a1` 歧义。**  
   24 条 official trials 的 `trial_id` 形如 `...-a1-r1` 到 `...-a1-r24`，category 内 attempt 实际由 `attempt` 字段 1–4 表达。显式 `attempt` 正确，但若下游按 trial_id 的 `aN` 解析会误读。建议 G1 说明或以 attempt 编码 trial_id。

5. **[low] `BYOK_JUDGE_V2_FIXES.md` 缺第 8 轮修复记录节。**  
   文件末尾仍为“Flash 验收（第 7 轮）后修复”，没有用户所述“Flash 验收（第 8 轮）后修复”。技术项已由代码/产物验证，但审计追溯应补文档。

6. **[low/已知] 每个 attempt 新建 runner，模拟器时间重置。**  
   `run_part1_course.py::main` 每 attempt 仍 `cpr = CoursePolicyRunner(...)`，证据中三次 attempt 的 `started_at` 都是 `0.5`，事件时间跨 attempt 不可全局排序。这是 V8 已列残余，不是新 blocker。

---

## 四、是否满足“进入 Codex 前的 flash 验收（无问题）”

**no（不建议当前标为“无问题”）**。  
按 scorer 主路径：**没有新的 blocker**；第 8 轮 4 项技术项均已 PASS；trial_id 唯一性、official Part2 4 次 attempts、N1–N4/P1–P4 无回归。  
但按“无问题”审计标准，仍有上述证据/审计覆盖缺口，尤其是 course 演练 per-attempt 共享引用污染和 HASHES 未覆盖 official summary。

**最小修复建议：**
1. 修 `AttemptManager.summary`/`Part1Course.export_report` 的 attempts/events 快照问题，重生成 pause/abort 演练 JSON。
2. 把 official Part2 summary 纳入 HASHES 并重生成 `HASHES.json`（或 G1 明确排除理由）。
3. 在 formal 模式把 Part2 `attempts_used` 与 trials 条数不一致改为 error，并让 `part2_has_evidence` 同时考虑 trials。
4. 补 `BYOK_JUDGE_V2_FIXES.md` 第 8 轮修复记录节。
5. 低优先：official trial_id 的 `a1` 命名统一/说明；pause_timeout abort 记录 `operator_t` 便于审计。

---

## 五、G1 必写残余风险

1. Q2 已确认 ×2/3：T 台阶双侧 100、仅上 50、仅下 33；返回奖励只认单项满分。
2. 分数最高优先、同分取最快；计时在机器人稳定停下后停止；恢复不消耗尝试。
3. 返回奖励必须“全部障碍满分后重新进入出发区”。
4. Part2 仅 RL、每项 4 次；official 重复最高档在确定性策略下稳定性统计意义有限，需说明“4 次中的重复档”口径。
5. Part1 手动/自动均允许，自动无加分；正式手动 3 次演练仍未在真实赛程上做，当前主要是脚本化诊断。
6. 砂砾坑真实“坑+碎木”几何未 recut，本地仍为凸起盒代理；正式评测前需重做并重跑 conformance。
7. Part2 官方能力场未逐档交叉核对；本地为同种类参数化 level。
8. soft-reset 阈值与相邻 zone 重叠仍是启发式。
9. 每个 attempt 模拟器时间从 0.5 重置，跨 attempt 事件时间线不可全局排序。
10. `HASHES.json` 仍 `audited:false / verdict:pending`；official summary 的 hash 覆盖与 Part1 course 演练证据引用问题需在 G1 报告中说明或修复。
