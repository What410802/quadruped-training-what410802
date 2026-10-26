## verdict

**CONCERN（不建议判定为“无问题”送 Codex）**。

- 正式计分主路径未发现新的 **scorer blocker**：空证据条目、trial_id 唯一化、official 每 category 4 次计数、全部 skipped 账本、ground 白名单的主逻辑均已落地。
- 但仍有 **high 级审计/证据问题**：Part2 official 的 `attempt` 编号仍不是 category 内 1–4；没有 official 4 次模式的落盘产物；另外 pause/resume/skip 仍有 fake 时钟残留。
- 因此：**是否还有 blocker：按正式分数门禁，无明确 blocker；按“无问题”验收标准，仍有必须清理项。**  
  **是否满足“进入 Codex 前的 flash 验收（无问题）”：no。**

---

## 一、第 7 轮 5 项逐项

| # | 结论 | 代码/证据依据 |
|---|---|---|
| 1. 空证据条目必报错 | **PASS（主逻辑）** | `comp_score.py::validate_external_evidence/_check_hash` 已加 `required`；正式 manifest 下 `judge.file_hashes`、`scenes.*.levels` 的空 `{}` 会因缺 `path/file/scene` 报错；`scenes.part2.levels` 为空也报错。 但 `comp_score.py::run_self_test` 未见空条目/level hash 篡改用例，与修复文档声明不完全一致（low）。 |
| 2. trial_id 唯一 | **PASS（唯一化）** | `comp_import_part2_diag.py` 使用全局 `trial_seq`：`trial_seq += 1`，`trial_id = ...-a{i}-r{trial_seq}`；official 重复最高档不会再生成相同 id。 |
| 3. abort/pause 用模拟器时钟 | **STILL-BROKEN（部分）** | `comp_part1_course.py::abort_attempt` 的 `duration` 已用 `last_sim_t`，`resume` 的 `pauses[-1][1]` 也已用 `last_sim_t`；但 `resume` 的 `_current_events` / `manager.events` 仍写 `float(t)`，`abort_attempt` 仍调用 `manager.skip(t, ...)`。`run_part1_course.py::run_policy_step` 的 pause-timeout 路径传入 `fake`，所以 `ended_at`、`skip` 事件仍是 fake 时钟。证据 `part1_course_pause_resume_drill.json` 中 `pauses=[1.0,1.0]`，但 `resume` 事件 `t=2.0`，可直接看到不一致。 |
| 4. skipped 标注 | **PASS（主字段）** | `comp_import_course_diag.py` trial 已加 `"skipped": bool(rec_att.get("skipped"))` 与 `"duration_note"`；skipped attempt 的 trial duration 置 0。问题仅是 `duration_note` 对非 skipped 也写 `"0 for skipped attempts"`，文案误导（low）。 |
| 5. ground 白名单 | **PASS** | `comp_part1_geom_tags.py::GROUND_GEOM_NAMES` 已改为精确集合；`is_ground_geom()` 只做 `name in GROUND_GEOM_NAMES`，不再 `startswith("ground")`。 |

---

## 二、N1–N4、P1–P4、第 6 轮 4 项回归

### N1–N4

| 项 | 结论 | 依据 |
|---|---|---|
| N1 逐物理步采样 | **PASS** | `run_part1_course.py::run_policy_step`：`set_action` 后 `for _ in range(4): physics_step(); sample = feed()`，`feed()` 内调用 `course.update`。 |
| N2 per-attempt best | **PASS** | `run_attempt` 返回 `attempt_result`；`comp_import_course_diag.py::_att_rec` 读取 `attempt_result`，按 `(score, -duration)` 选 best。 |
| N3 最高分内最快 | **PASS** | `Part1Course.summary` 与 `AttemptManager.summary` 均先取最高分，再在最高分尝试内取 `min(duration_s)`；写出 `final_time_scope`。 |
| N4 bool 只认 1.0 | **PASS** | `comp_score.curve_points` 与 `comp_part2_judge.curve_points_floor` 均为 `float(value) == 1.0` 才给 bool 分。 |

### P1–P4

| 项 | 结论 | 依据 |
|---|---|---|
| P1 stable-stop 物理 dt | **PASS** | `run_part1_course.py::run_attempt` 使用 `dt_phys = cpr.model.opt.timestep`，传给 `StableStopTracker.update(speed, tilt, dt_phys)`。 |
| P2 暂停不喂 judge | **PASS** | pause 循环只推进 fake 时钟与 `apply_events`，不调用 `course.update`/`physics_step`；`if not course.active: return False` 能外传 abort。 |
| P3 外部证据校验接线 | **PASS（主路径），但有严格校验回归风险** | `comp_score.score_one` 已调用 `validate_external_evidence(..., trials)`；hash、Part2 合法档位、Part1 final_time 复算均已接线。风险见“新问题 4”。 |
| P4 ground 分类 | **PASS** | `comp_part1_geom_tags.is_ground_geom` 精确白名单；`CoursePolicyRunner`/`V2Runner` 共用；conformance 断言 bridge/slope/step 不是 ground。 |

### 第 6 轮 4 项

| 项 | 结论 | 说明 |
|---|---|---|
| ① pause/resume 时间账本 | **PASS（主路径）** | duration 由模拟器开始/结束时间计算，暂停物理冻结，暂停时间不计入。残留：resume/skip 事件 t 仍可能 fake。 |
| ② 正式 manifest 缺 contract/scenes/judge.file_hashes | **PASS** | 非 diagnostic 已强制；空条目现在也会报错。 |
| ③ all-skipped duration/final_time | **PASS** | skipped trial duration=0；全 skipped 时 `final_score=0, final_time_s=0`；importer fallback 保留首 attempt。 |
| ④ Part2 official 每项 4 次 | **计数 PASS；审计字段残留** | `run_part2_judged_eval.py --official` 会补足 4 个 entry；importer `attempts_used=len(cat_trials)`。但 `attempt` 字段仍不是 category 内 1–4，见新问题 1。 |

---

## 三、新问题清单

### 1. [high] Part2 official 的 `attempt` 编号仍不是 category 内 1–4

- 文件：`run_part2_judged_eval.py`、`comp_import_part2_diag.py`
- 依据：
  - `run_part2_judged_eval.py --official` 对每个 official entry 设 `n_attempts = 1 if args.official else ...`，因此每个 entry 的 `attempts` 列表只有 1 条。
  - `comp_import_part2_diag.py` 内 `for i, run in enumerate(att.get("attempts") or [], 1): ... "attempt": i`，所以 official 下每个 trial 的 `attempt` 都是 1。
  - `trial_id` 因 `trial_seq` 唯一，但 `attempt` 字段重复。
- 利用路径：G4 审计按 `(obstacle, attempt)` 复核“每项 4 次”时会看到 4 条 trial 全是 `attempt=1`，无法按契约的 1–4 次对账；`comp_score` 只检查 `attempts_used == len(trials)`，不会拦住。
- 建议：importer 维护 per-category 的 `attempt_seq`（1–4），并另存 `entry_seq`/`repeat_index`；official runner 输出 entry 序号，确保 `attempts_used=4` 且 trials 的 attempt 为 1–4。

### 2. [medium/high] pause/resume/skip 账本仍有 fake 时钟残留

- 文件：`comp_part1_course.py::resume`、`abort_attempt`；`run_part1_course.py::run_policy_step`
- 依据：
  - `resume` 已用 `self.last_sim_t` 闭合 `pauses[-1][1]`，但随后 `self.manager.events.append({"t": float(t), "event": "resume", ...})` 和 `_current_events` 的 resume 事件仍使用传入的 `t`。pause 循环中传入的是 `fake`。
  - `abort_attempt` 的 duration 已用 `last_sim_t`，但 `self.manager.skip(t, reason=reason)` 仍用调用者 `t`；pause-timeout 路径 `course.abort_attempt(fake, "pause_timeout")` 会把 fake 写进 `ended_at` 和 `skip` 事件。
- 利用路径：pause-timeout 后账本出现 `started_at=sim 0.5, ended_at=fake 121.0, duration_s=sim 0.5`，审计无法按统一时间线解释。
- 建议：`abort_attempt` 内统一用 `self.last_sim_t` 调 `manager.skip` 并覆盖 skip 事件/ended_at；`resume` 事件也用 `last_sim_t`，fake 只用于触发 operator event。补 pause-timeout 自检。

### 3. [medium] `comp_score` 未机器拒绝重复 `trial_id`

- 文件：`comp_score.py::validate_trials`、`validate_summary`
- 依据：`validate_trials` 只检查 `trial_id` 非空，不检查唯一性；`validate_summary` 用 `by_id = {t.get("trial_id"): t ...}`，重复 id 会静默覆盖。
- 利用路径：即使 importer 已修，未来手写/旧 importer 产物仍可带重复 trial_id 进入 valid/diagnostic 行；Part1 evidence 复核可能被后出现的同 id trial 覆盖。
- 建议：`validate_trials` 增加 `seen_trial_ids`，重复即 `_err`。补自检。

### 4. [medium] 严格 evidence 校验的两个回归风险

- 文件：`comp_score.py::validate_external_evidence/_check_hash`
- 风险 A：`_check_hash(entry, ...)` 假定 `entry` 是 dict；若 manifest 写 `file_hashes: ["x"]` 或 `levels: [null]`，会 `AttributeError` 崩溃，而不是返回 invalid 行。
- 风险 B：非 diagnostic 下无条件要求 `scenes.part2.levels` 非空；如果正式 Part1-only manifest 的 `scenes.part2` 只是能力场/levels 配置而无 `levels` 列表，会被判 invalid。`comp_import_course_diag.py` 当前是 diagnostic，正式化后可能踩到。
- 建议：`_check_hash` 先判 `isinstance(entry, dict)`，否则 `_err`；`scenes.part2.levels` 仅在 manifest 声明 Part2 评分或 `scenes.part2.mode=="levels"` 时强制。

### 5. [low] 自检与修复文档不完全一致

- 文件：`comp_score.py::run_self_test`
- 依据：修复文档称补了“空条目/篡改 level hash”用例；当前自检可见部分没有空 `file_hashes` 条目、空 `levels` 条目、level hash 篡改用例。
- 建议：补三组自检，确保第 7 轮问题有回归保护。

### 6. [low] skipped 的 `duration_note` 文案对非 skipped 也固定写 “0 for skipped attempts”

- 文件：`comp_import_course_diag.py`
- 依据：trial dict 中 `"duration_note": "0 for skipped attempts"` 无条件写入；非 skipped trial 也带该文案。
- 建议：仅 skipped 写该 note，非 skipped 写 `"active attempt duration"` 或 `None`。

### 7. [medium，已知残余] 每个 attempt 新建 runner，模拟器时间重置

- 文件：`run_part1_course.py::main`
- 依据：每个 attempt 循环内 `cpr = CoursePolicyRunner(...)`，`data.time` 从 0.5 重置；证据中三次 attempt 的 `started_at` 全是 0.5，`manager.events` 的 t 在 attempt 间重叠。
- 影响：不影响单次 duration/final_time，但跨 attempt 审计无法全局排序。
- 建议：runner 维护单调 `session_time`，或 attempt/event 明确带 `attempt` 前缀并在 G1 说明。

---

## 四、是否还有 blocker / 是否满足 flash 验收

- **正式计分 blocker：无明确 blocker。**  
  空证据条目、trial_id 唯一化、official 次数计数、all-skipped 账本、ground 白名单的主路径均已堵住。
- **但未满足“进入 Codex 前 flash 验收（无问题）”：no。**  
  主要因为：
  1. Part2 official `attempt` 字段仍不是 category 内 1–4，且无 official 4 次模式落盘证据；
  2. abort/pause/resume/skip 事件仍有 fake 时钟残留；
  3. `comp_score` 不拒绝重复 trial_id；
  4. 严格 evidence 校验有 malformed-type 崩溃和 Part1-only false invalid 风险。

### 最小修复清单（按优先级）

1. `comp_part1_course.py`：`abort_attempt` 用 `last_sim_t` 调 `manager.skip` 并修正 skip 事件/`ended_at`；`resume` 事件也用 `last_sim_t`；补 pause-timeout 自检。
2. `comp_import_part2_diag.py` / `run_part2_judged_eval.py`：official 下 per-category `attempt` 固定 1–4，新增 `entry_seq/repeat_index`；重跑 official 并落盘，校验 `attempts_used=4`、trials 条数=4、trial_id 唯一。
3. `comp_score.py`：`validate_trials` 增加 trial_id 唯一性检查；`_check_hash` 增加非 dict 类型检查；`scenes.part2.levels` 强制条件化。
4. `comp_score.py::run_self_test`：补空 `file_hashes`、空 `levels`、level hash 篡改、重复 trial_id 用例。
5. `comp_import_course_diag.py`：`duration_note` 仅在 skipped 时写固定文案。
6. 重新生成 pause/abort/official Part2 证据并更新 `HASHES.json` / `SCOREBOARD`。

---

## 五、仍保留、必须写进 G1 报告的已知残余

1. 砂砾坑真实几何未 recut，本地仍为凸起盒代理；正式评测前需真实坑+碎木几何并重跑 conformance。
2. Part2 官方能力场未逐档交叉核对；本地为同种类参数化 level。
3. soft-reset 阈值与相邻 zone 重叠仍为启发式。
4. Part1 正式手动 3 次演练未做；当前主要是脚本化诊断。
5. official 重复最高档在确定性策略下两次结果可能相同，稳定性统计意义有限，需说明“4 次中的重复档”口径。
6. 每个 attempt 的模拟器时间从 0.5 重置，跨 attempt 事件时间线不可全局排序。
7. `HASHES.json` 仍 `audited:false / verdict:pending`；修复后的 official 4 次产物尚未落盘并入 HASHES。
