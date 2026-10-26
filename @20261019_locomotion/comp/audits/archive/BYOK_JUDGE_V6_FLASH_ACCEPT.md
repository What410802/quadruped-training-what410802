## verdict

**FAIL（验收建议）**。

第 5 轮点名的 P3 指定路径、P4 指定路径、暂停内 abort 外传路径**按代码看已修**；N1–N4、P1–P2 仍 PASS。但本轮发现新的 blocker/high 问题，主要集中在：

1. **pause/resume 时间账本被二次扣减**：`resume()` 用“操作手 fake 时钟”写回 `prev_t`，导致恢复后 `active_time` 少算暂停时长，可能伪造更快的 `final_time`；
2. **`validate_external_evidence` 对“整条证据缺失”仍静默通过**：非 diagnostic manifest 可省略 `contract`、`scenes`、`judge.file_hashes` 而仍被判 valid；
3. **all-skipped / abort drill 的 course importer fallback 仍会把 skipped attempt 当 best**，且 `final_time_s=0` 与 trials 中非零 duration 冲突，abort drill 不能作为干净证据导入；
4. **Part 2 `--official` 仍不是“每项恰好 4 次”**：trench 只有 3 档、plum 只有 1 档时会只跑 3/1 次，不满足已确认规则。

因此目前**仍有 blocker**，不满足“进入 Codex 前的深 flash 验收”。

---

## 一、第 5 轮遗留项逐项结论

| 项 | 结论 | 代码依据 |
|---|---|---|
| N1 逐物理步采样 | **PASS** | `run_part1_course.py::run_policy_step()` 中 `cpr.set_action(command)` 后 `for _ in range(4): cpr.physics_step(); sample = feed()`；`feed()` 内调用 `course.update()`，即 5 ms 物理步后进 judge。 |
| N2 per-attempt best | **PASS** | `run_part1_course.py::run_attempt()` 返回 `attempt_result = course.results[-1].to_dict()`；`comp_import_course_diag.py::_att_rec()` 读取 `attempt_result`；best key 为 `(score, -duration_s)`，不再用 session 全局 summary 选 best。 |
| N3 同分最快只在最高分尝试内 | **PASS** | `comp_part1_judge.py::AttemptManager.summary()` 先求 `best_score`，再在 `best_candidates` 中取 `min(duration_s)`；`comp_part1_course.py::Part1Course.summary()` 同样按 `r.score == best_score` 过滤后取最快。 |
| N4 bool 只认 `value == 1.0` | **PASS** | `comp_score.py::curve_points()`：`if unit == "bool": return ... if float(value) == 1.0 else 0`；`comp_part2_judge.py::curve_points_floor()` 同样。 |
| P1 stable-stop 用真实物理 dt | **PASS** | `run_part1_course.py::run_attempt()` stable-stop 块：`dt_phys = float(cpr.model.opt.timestep)`，`speed = norm(pos - prev) / dt_phys`，`StableStopTracker.update(..., dt_phys)`。 |
| P2 暂停期间不向 judge 喂冻结位姿 | **PASS（主项）** | `run_policy_step()` 的 pause 循环只推进 `fake` 并 `apply_events(course, events, ev_idx, fake, ...)`，**不调用** `course.update()`。 |
| P3 `validate_external_evidence` 接线 / scene 键 / 缺 sha / 篡改 hash / 非法档位 / final_time | **指定项 PASS，但整体仍有新 bypass** | `comp_score.py::score_one()` 已实际调用：`validate_external_evidence(manifest, summary, contract, task_root, row["diagnostic"], trials)`；`_check_hash()` 支持 `entry.get("scene")`；对已存在但缺 `sha256` 的条目，非 diagnostic 会 error，diagnostic 仅 warning；self-test 覆盖 tampered hash、非法 Part2 档位、错误 final_time。**但** `_check_hash()` 在 `file/path/scene` 整条缺失时直接 `return`，且 `REQUIRED_MANIFEST` 不要求 `contract`，`scenes` 可为空，`judge.file_hashes` 可省略——非 diagnostic manifest 可绕过外部证据校验。 |
| P4 `ramp_blocks_l/r` 等非 plane 接近面进入 ground | **PASS** | `comp_part1_geom_tags.py::is_ground_geom()` 与 `GROUND_GEOM_NAMES` 已包含 `ramp_blocks_l/r`、`floor`、`trench_bottom`、`level_floor`、`ground*`；`run_part1_course.py::CoursePolicyRunner.__init__()` 与 `run_part1_judged_rollout_v2.py::V2Runner.__init__()` 均使用 `is_ground_geom()`。conformance 断言 `bridge/slope/step` 不是 ground。 |
| 暂停内 abort 终止信号外传 | **代码路径 PASS；演练证据 UNVERIFIED** | `run_policy_step()` pause 循环里 `apply_events()` 后执行 `if not course.active: return False`；`run_attempt()` 外层据此 `break`，不会再用 inactive course 调 `course.update()`。但验收包中未提供 `part1_course_abort_drill.json`，该文件也不在 `HASHES.json`，因此“3 次 pause→resume→abort”无法独立复核。 |

---

## 二、P3 细查结果

### 已修复的指定路径

1. **`score_one()` 确实调用 `validate_external_evidence`**  
   代码路径：
   - `comp_score.py::score_one()` 中：
     - `validate_manifest(...)`
     - `load_trials(...)`
     - `validate_summary(...)`
     - `validate_trials(...)`
     - `validate_external_evidence(manifest, summary, contract, task_root, row["diagnostic"], trials)`
   - `trials` 已加载并传入，`task_root` 也由 CLI 参数传入。

2. **`scene` 键的 level hash 已复核**  
   `comp_score.py::_check_hash()`：
   - `rel = entry.get("file") or entry.get("path") or entry.get("scene")`
   - Part 2 manifest 的 level 条目使用 `scene`，现在会被检查。

3. **缺 `sha256` 对已存在条目会报错（非 diagnostic）**  
   `_check_hash()` 中：
   - `if not recorded: (_warn if diagnostic else _err)(...)`
   - 即 formal/non-diagnostic 下缺 sha 是 error；diagnostic 下仅 warning。

4. **篡改 hash / 非法 Part2 档位 / 错误 final_time**  
   - 篡改 hash：`actual != recorded` 时 `_err(errors, ...)`。
   - 非法 Part2 档位：`best_success_value` 不在 `score_curve` 的 `value` 集合，或 bool 不为 `1.0`，会 `_err`。
   - 错误 final_time：用 trials 按 attempt 重算最高分尝试中最快 duration，不一致会 `_err`。
   - `run_self_test()` 中已有对应断言。

### 新发现的 P3 bypass

**严重度：blocker/high**  
文件/函数：`comp_score.py::validate_external_evidence` / `_check_hash` / `REQUIRED_MANIFEST`

利用路径：
- manifest 写 `"scenes": {}`：`scenes` 键存在但为空，`validate_manifest` 通过；`validate_external_evidence` 循环不到任何条目，不报错。
- manifest 省略 `"contract"`：`contract_meta = manifest.get("contract") or {}`，`_check_hash({})` 因无 `rel` 直接 `return`。
- manifest 写 `"judge": {"version": "fake"}` 但不写 `file_hashes`：不会校验 judge 文件 hash。
- 对已存在条目，若整条 entry 无 `file/path/scene`，`_check_hash()` 也直接 `return`，不报错。

结论：**“缺 sha256 是否报错”只对“有条目但缺 sha”成立；整条证据缺失仍可绕过。** 这仍是外部证据链的 blocker。

建议：
- 非 diagnostic 下必须要求 `scenes.part1`、`scenes.part2`、`contract.sha256`、`judge.file_hashes` 非空；
- `REQUIRED_MANIFEST` 增加 `contract`；
- `_check_hash()` 对非 diagnostic 缺 `file/path/scene` 应 error，而不是静默 return；
- 自检补：空 `scenes`、空 `contract`、空 `judge.file_hashes`、`scene` 键 level hash 被篡改。

---

## 三、P4 细查结果

**结论：PASS。**

代码依据：
- `comp_part1_geom_tags.py`：
  - `GROUND_GEOM_NAMES = {"floor", "trench_bottom", "level_floor", "ramp_blocks_l", "ramp_blocks_r"}`
  - `is_ground_geom(name, is_plane)` 返回 `is_plane or name in GROUND_GEOM_NAMES or name.startswith("ground")`
- `run_part1_course.py::CoursePolicyRunner.__init__()`：
  - `self.floor_geoms = {g for g in range(self.model.ngeom) if is_ground_geom(self.geom_names.get(g, ""), self.model.geom_type[g] == mujoco.mjtGeom.mjGEOM_PLANE)}`
- `run_part1_judged_rollout_v2.py::V2Runner.__init__()` 同样使用 `is_ground_geom()`。
- conformance `test_scene_geom_tags_complete()` 断言：
  - `is_ground_geom("ramp_blocks_l")`、`ramp_blocks_r` 为 true；
  - `bridge_blocks_0`、`slope_a`、`t_stairs_y_low1` 为 false。

因此原 P4 利用路径（两足触 `ramp_blocks_l/r` 不进入 `ground_feet`）已关闭；桥/坡/台阶不会被误判为 ground。

---

## 四、暂停内 abort 与新时序问题

### abort 外传

**代码路径 PASS。**  
`run_part1_course.py::run_policy_step()` pause 循环中：
- `apply_events()` 处理 `abort` 后，`course.abort_attempt()` 设置 `course.active = False`；
- 紧接着 `if not course.active: return False`；
- 外层 `run_attempt()` 的 `if not run_policy_step(cmd): aborted = True; break` 终止 route loop；
- 之后 `if course.active:` 为 false，不再 `end_attempt()`，也不会再 `course.update()`。

所以“inactive course 继续”的崩溃路径已关闭。

### 新 blocker：pause/resume 时间账本被二次扣减

**严重度：blocker/high**  
文件/函数：`run_part1_course.py::run_policy_step()` + `comp_part1_course.py::Part1Course.resume()`

代码路径：
- pause 循环里用 fake 操作手时钟：
  - `fake += 0.02`
  - `apply_events(course, events, ev_idx, fake, ...)`
- `apply_events()` 对 `resume` 调用 `course.resume(t, ...)`，这里 `t = fake`。
- `Part1Course.resume()` 中：
  - `self.prev_t = float(t)`  // 写成 fake 时钟
- 但物理在本轮暂停期间是
