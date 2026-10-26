# 第七轮 BYOK（deepseek-v4.1-flash）验收结论

## verdict

**FAIL（验收建议）**。

第 6 轮 4 个 blocker 的**主路径**中 ①③④ 已修复、② 的“整条缺失”已修复；但仍有 **证据链 blocker 级残留**（正式 manifest 的 `judge.file_hashes`/`scenes.*.levels` 条目可空转而静默 valid）与 **high 级新问题**（official 重复最高档导致 trial_id 冲突、abort/pauses 仍写 fake 时钟）。因此**不满足“进入 Codex 前的 flash 验收（无问题）”**。

---

## 一、第 6 轮 4 个 blocker 逐项

| # | 结论 | 代码依据 |
|---|---|---|
| ① pause/resume 时间账本 | **主路径 PASS；abort/pauses 记录 STILL-PARTIAL（medium）** | `Part1Course.begin_attempt` 记录 `attempt_start_t = float(t)`；`end_attempt` 用 `duration = float(t) - attempt_start_t`；`resume` 中已**没有** `self.prev_t = float(t)`（`prev_t` 实为死字段）；`run_policy_step` 暂停循环只推进 `fake` 与 `apply_events`，不调用 `physics_step`/`course.update`，故物理冻结、正常完成路径 duration=end−start 天然不含暂停。但 `abort_attempt(t)` 仍用调用者 t：`run_policy_step` 的 `pause_timeout` 传 `fake`，暂停循环内 `apply_events` 的 `abort` 也传 `fake`，此时 `duration = fake − start` 会把 fake 暂停时长算入 `attempt_result.duration_s`；`resume` 中 `manager._current["pauses"][-1][1] = float(t)` 也写 fake t，使 `pauses` 区间为 `[模拟器 pause t, fake resume t]`。虽 skipped 不进 final_time，但账本与审计不一致。 |
| ② 正式 manifest 缺 contract/scenes/judge.file_hashes | **主项 PASS；条目空转 STILL-BROKEN（blocker/high）** | `validate_external_evidence` 非 diagnostic 已强制 `contract.file+sha256`、`scenes` 非空、`scenes.part1/part2.file`、`judge.file_hashes` 非空；`scenes` 条目缺 file 会 `_err`。但 `_check_hash` 对 `entry` 无 `file/path/scene` 直接 `return`；`judge.file_hashes` 只检查“列表非空”，写 `[{}]` 可通过；`scenes.part2.levels` 列表条目只经 `_check_hash`，缺 `scene/sha256` 时静默跳过。即“整条缺失”已堵，**“空条目代替”仍可让正式 manifest valid 而不实际核 judge/level XML**。 |
| ③ all-skipped / abort drill duration 与 final_time | **PASS** | `comp_import_course_diag`：`duration = 0.0 if rec_att.get("skipped") else ...`；全 skipped 时 `session = {"final_score": 0.0, "final_time_s": 0.0}`；`best_idx` fallback 保留首条 attempt 不崩溃。`comp_score.validate_external_evidence` 由 trials 复算 `expected=0`，与 `final_time_s=0` 一致；abort drill 证据（`comp/audits/evidence/part1_course_abort_drill.json`，sha256 `5f8d4729…`）与 HASHES 一致。 |
| ④ Part2 official 每 category 恰好 4 次 | **计数 PASS；trial 唯一性 BROKEN（high）** | `run_part2_judged_eval`：`ordered = sorted(..., -level)`，`ordered[:4]`，再 `for _ in range(4 - min(4, len(ordered))): official.append(ordered[0])`；trench=3 档→`[30,20,10,30]`，plum=1→`[1,1,1,1]`；`n_attempts = 1 if args.official`，每 category 恰 4 个 entry。但同一 level（30/1）的两次运行在 `comp_import_part2_diag` 生成相同 `trial_id`（`...-trench-30cm-a1` / `...-plum-1bool-a1`），`trials.jsonl` 出现重复 id，`comp_score` 的 `by_id` 被覆盖，证据无法唯一复核。 |

---

## 二、N1–N4、P1–P4 回归

| 项 | 结论 | 依据 |
|---|---|---|
| N1 逐物理步采样 | **PASS** | `run_part1_course.py::run_policy_step`：`cpr.set_action(command)` 后 `for _ in range(4): cpr.physics_step(); sample = feed()`，`feed()` 内 `course.update`。 |
| N2 per-attempt best | **PASS** | `run_attempt` 返回 `attempt_result = course.results[-1].to_dict()`；`comp_import_course_diag::_att_rec` 读 `attempt_result`，key `(score, -duration)`。 |
| N3 同分最快只在最高分尝试内 | **PASS** | `AttemptManager.summary` 先 `best_score` 再 `min(duration_s)`；`Part1Course.summary` 同口径并写 `final_time_scope`。 |
| N4 bool 只认 1.0 | **PASS** | `comp_score.curve_points` 与 `comp_part2_judge.curve_points_floor` 均 `float(value) == 1.0`。 |
| P1 stable-stop 物理 dt | **PASS** | `run_attempt` 中 `dt_phys = float(cpr.model.opt.timestep)`，`StableStopTracker.update(speed, tilt, dt_phys)`。 |
| P2 暂停不喂 judge | **PASS（主项）** | pause 循环只推进 `fake` + `apply_events`，不调用 `course.update`；`if not course.active: return False` 外传 abort。 |
| P3 validate_external_evidence 接线 | **PASS（主项）** | `score_one` 调用 `validate_external_evidence(..., trials)`；但见上方 ② 的条目空转残留。 |
| P4 ground 分类 | **PASS** | `comp_part1_geom_tags.is_ground_geom` 含 `floor/trench_bottom/level_floor/ramp_blocks_l/r` 与 `ground*`；`CoursePolicyRunner`/`V2Runner` 共用；conformance 断言 bridge/slope/step 不是 ground。 |

---

## 三、新问题清单

1. **[blocker/high] `comp_score.py::validate_external_evidence` / `_check_hash` 条目空转**
   - 路径：非 diagnostic manifest 写 `"judge": {"version": "j", "file_hashes": [{}]}`，或用 `scenes.part2.levels: [{}]`；`_check_hash({})` 因无 `rel` 直接 `return`，`not (judge.get("file_hashes") or [])` 为假（列表非空）→ 不报错，正式 manifest valid 但 judge/level XML 未被核。
   - 建议：非 diagnostic 下每个 `file_hashes` 条目必须含 `path/file` 与非空 `sha256`；`scenes.*.levels` 每个条目必须含 `scene/file` 与非空 `sha256`；`_check_hash` 对非 diagnostic 缺 `rel` 改 `_err`；自检补空条目用例。

2. **[high] `run_part2_judged_eval.py` official 重复最高档 + `comp_import_part2_diag.py` trial_id**
   - 路径：trench `[30,20,10,30]`、plum `[1,1,1,1]` 两次 entry 的 `attempts[].attempt` 都从 1 开始，`trial_id = f"...-{cat}-{level}{unit}-a{i}"` 重复；`by_id` 覆盖，G4 无法唯一定位 trial；重复档位在确定性策略下两次结果完全一致，稳定性统计意义也降低。
   - 建议：importer 用 entry 序号或全局计数器生成唯一 `trial_id`（如 `-e{entry_idx}-a{i}`），runner 记录 `entry_seq`；文档注明重复档位为“凑满 4 次”而非独立难度。

3. **[medium] `comp_part1_course.py::abort_attempt` 在暂停循环内用 fake t**
   - 路径：`apply_events` 的 `abort` 与 `pause_timeout` 传入 `fake`，`duration = fake − attempt_start_t` 把 fake 暂停时长计入 `attempt_result.duration_s`；虽 skipped 不进 final_time，但账本 duration 与模拟器活跃时间不一致。
   - 建议：abort 统一用模拟器时钟（runner 传 `cpr.data.time`），或 `Part1Course` 内部累加 `active_time`（pause 不累加）。

4. **[medium] `comp_part1_course.py::resume` 的 pauses 区间仍写 fake t**
   - 路径：`manager._current["pauses"][-1][1] = float(t)`，t 为 fake；`pause` 时用模拟器 t，导致区间 `[sim, fake]`。不影响 duration，但审计误读。
   - 建议：resume 闭合区间用模拟器时间，或显式记录 `pause_sim_t/resume_sim_t` 双字段。

5. **[low] `comp_part1_geom_tags.is_ground_geom` 的 `name.startswith("ground")` 过宽**
   - 路径：未来场景若命名 `ground_wall`/`ground_obstacle` 会被误判为地面。建议精确白名单（`ground_left/right/...`）。

6. **[low/medium] `run_part1_course.py` 每个 attempt 新建 `ScenePolicyRunner`，模拟器时间从 0.5 重置**
   - 路径：`AttemptManager.events` 三次 attempt 的 `t` 完全重叠（0.5→94.68），账本无法全局排序，跨 attempt 的暂停/超时无法按统一时间线审计。建议 runner 维护单调 `session_time` 或事件加 `attempt` 前缀（已有 attempt 字段，但 t 不单调）。

7. **[low] 全 skipped 时 trial `duration_s=0` 与 `attempt_result.duration_s` 非零不一致**
   - 路径：`comp_import_course_diag` skipped 的 trial duration=0，而 abort drill attempt_result duration=2.505；审计可能误读。建议 trial 加 `"skipped": true` 或 `duration_note`。

---

## 四、证据与 HASHES 一致性

- `comp/audits/HASHES.json` 共 53 个 objects，已包含 pause/abort 两份演练 JSON；artifacts 头部的 sha256 与 HASHES 中 `evidence_part1_course_pause_resume_drill`（`b8477ed1…`）、`evidence_part1_course_abort_drill`（`5f8d4729…`）一致；三个 eval 产物的 manifest/trials/summary 与 HASHES 一致。
- **但**：HASHES 的 `audited: false`、`verdict: pending`；且 official Part2 重复档位的 trial_id 冲突使“trials 可逐条复核”受损（见新问题 2）。

---

## 五、是否满足“进入 Codex 前的 flash 验收”

**no。**

最小修复清单（按优先级）：

1. `comp_score.py`：非 diagnostic 下强制每个 `judge.file_hashes` 条目与每个 `scenes.*.levels` 条目含 `path/file/scene` + 非空 `sha256`；`_check_hash` 缺 `rel` 在非 diagnostic 时报错；补自检（空 `file_hashes` 条目、空 `levels` 条目、level hash 篡改）。
2. `comp_import_part2_diag.py` / `run_part2_judged_eval.py`：official 重复档位的 `trial_id` 唯一化（entry 序号/重复计数），并确保 `attempts_used` 与 trials 条数可对账。
3. `comp_part1_course.py`：`abort_attempt` 与 `resume` 的账本时间改用模拟器时钟（或在 `Part1Course` 内维护 `active_time`），消除 abort/pauses 的 fake 污染。
4. `comp_import_course_diag.py`：全 skipped 的 trial 标注 `skipped`/`duration_note`，避免与 attempt_result 非零 duration 混淆。
5. `comp_part1_geom_tags.is_ground_geom`：将 `startswith("ground")` 改为精确白名单。

---

## 六、仍保留、必须写进 G1 报告的已知残余

1. 砂砾坑真实几何未 recut（本地为凸起盒代理，`comp/CONTRACT.md` §5.1/`_protocol.md` §8）。
2. Part2 官方能力场（`terrain.zip` 地图）未逐档交叉核对；本地为同种类参数化 level。
3. soft-reset 阈值与相邻 zone 重叠仍为启发式（`BYOK_JUDGE_V2_FIXES.md` #13/#26）。
4. Part1 单障碍诊断 importer 的 per-obstacle 汇总口径（#21，仅诊断用）。
5. 正式 Part1 3 次手动演练未做（当前脚本化诊断）；账本每 attempt 模拟器时间从 0.5 重置，跨 attempt 不可全局排序。
6. official 重复最高档在确定性策略下两次结果可能完全一致，稳定性统计意义有限；需在 G1 说明“4 次中的重复档”口径。
7. `HASHES.json` 仍 `audited:false / verdict:pending`；本轮修复后的 `comp_score.py`、importers、course 文件在 HASHES 中未重新生成（本轮 artifacts 为新 sha，需重新落 HASHES 后再送 G1）。
