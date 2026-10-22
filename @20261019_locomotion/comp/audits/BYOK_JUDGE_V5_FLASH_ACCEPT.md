## verdict

**FAIL（验收建议）**。

N1–N4 仍 PASS；P1、P2 主问题已修；但 **P3 仍是 STILL-BROKEN**（`comp_score` 的外部证据校验函数没有被调用，且 level scene hash 实际会被跳过），**P4 仍为部分修复/STILL-BROKEN**（Part1 course runner 的 ground 分类没有覆盖原 pro 指出的 `ramp_blocks_l/r` 非 plane 接近面）。另外 pause 内 abort 的终止信号仍未正确外传。因此目前**存在 blocker**，不满足“进入 Codex 前的 flash 验收无问题”。

以下结论以代码路径为准，未把 conformance/self-test 通过当作充分证据。

---

## 一、N1–N4 逐项

### N1 — 逐物理步采样：**PASS**

代码依据：`run_part1_course.py::run_policy_step()`：

```python
cpr.set_action(command)
for _ in range(4):
    cpr.physics_step()
    sample = feed()
```

`feed()` 内调用 `course.update(...)`，即每个 5 ms 物理步后都进入 judge/course。warmup 的 `step_policy()` 不进入计分路径。原“<20 ms 任意瞬间 ≥2 足触地漏判”路径已关闭。

### N2 — per-attempt best：**PASS**

代码依据：

- `run_part1_course.py` 每次 attempt 返回 `attempt_result = course.results[-1].to_dict()`；
- `comp_import_course_diag.py::_att_rec()` 读取 `att["attempt_result"]`；
- best 选择：

```python
key = (float(rec.get("score", 0.0)), -float(rec.get("duration_s", 0.0)))
```

不再使用全局 `final_time_s` 选 best。N2 原路径已关闭。残余 minor：全部 attempt 都 `skipped` 时 `best_idx=0`，会把 skipped attempt 当 best，见新问题。

### N3 — 同分最快只在最高分尝试内：**PASS**

代码依据：

- `comp_part1_judge.py::AttemptManager.summary()`：

```python
best_score = max((a["score"] for a in scored), default=0.0)
best_candidates = [a for a in scored if a["score"] == best_score]
fastest = min((a["duration_s"] for a in best_candidates), default=0.0)
```

- `comp_part1_course.py::Part1Course.summary()`：

```python
best_candidates = [r for r in scored if r.score == best_score]
summary["final_time_s"] = min((r.duration_s for r in best_candidates), default=0.0)
summary["final_time_scope"] = "min_duration_among_best_score_attempts"
```

N3 语义已正确。残余低风险：`export_report()` 的 `rules.final_time` 仍写 `"min_over_attempts"`，与真实语义不一致。

### N4 — bool 只认 `value == 1`：**PASS**

代码依据：

- `comp_score.py::curve_points()`：

```python
if unit == "bool":
    return int(math.floor(curve[-1]["points"])) if float(value) == 1.0 else 0
```

- `comp_part2_judge.py::curve_points_floor()` 同样 `float(value) == 1.0`。

原“任意非零满分”路径已关闭。但注意：`comp_score` 对 Part2 合法档位的机器校验仍未生效，见 P3。

---

## 二、P1–P4 逐项

### P1 — 稳定停表真实物理 dt + 0.5 s stable：**PASS**

代码依据：`run_part1_course.py::run_attempt()` stable-stop 块：

```python
dt_phys = float(cpr.model.opt.timestep)   # 5 ms
...
speed = float(np.linalg.norm(pos - prev)) / dt_phys
...
if tracker.update(speed, tilt, dt_phys):
```

`StableStopTracker.update()` 用传入 `dt` 累加 `held`，`hold_s=0.5`。不再使用 policy dt 20 ms。P1 主问题已修。

### P2 — 暂停期间不向 judge 喂冻结位姿：**PASS（主项）**

代码依据：`run_part1_course.py::run_policy_step()` pause 循环：

```python
while course.paused and course.active:
    n += 1
    fake += 0.02
    if n * 0.02 > 120.0:
        course.abort_attempt(fake, "pause_timeout")
        return False
    ev_idx = apply_events(course, events, ev_idx, fake,
                          pose_xy=sample["base_xyz"], pose_yaw=sample["yaw"])
```

暂停期间只 `apply_events`，**不调用 `course.update()`**，因此 judge 不再收到重复冻结位姿。P2 主问题 PASS。

但 pause 内处理 `abort` 时仍有终止信号问题，见新问题 1。

### P3 — `comp_score` 机器复核外部证据：**STILL-BROKEN**

这是本轮最关键问题。

1. `comp_score.py` 新增了 `validate_external_evidence(...)`，但 `score_one()` **没有调用它**。`score_one()` 只调用：

```python
validate_manifest(...)
load_trials(...)
validate_summary(...)
validate_trials(...)
```

没有 `validate_external_evidence`。因此场景/judge/contract hash、Part2 合法档位、Part1 final_time 的机器复核实际上**全部未生效**。

2. 即使调用 `validate_external_evidence()`，Part2 level XML hash 仍会被跳过：

```python
def _check_hash(entry, label):
    rel = entry.get("file") or entry.get("path")
    if not rel:
        return
```

但 Part2 manifest 的 level 条目是：

```json
{"category": "...", "level": 10, "unit": "cm",
 "scene": "assets/terrain/part2/levels/high_platform_10cm.xml",
 "sha256": "..."}
```

没有 `file` 或 `path`，只有 `scene`，所以 `_check_hash()` 直接 return，level XML hash 不会被复核。

3. Part1 final_time 复算依赖：

```python
trials = manifest.get("__trials__") or []
```

但 `score_one()` 没有把已加载的 `trials` 注入 `manifest["__trials__"]`，所以该路径即使被调用也无法从 trials 复算 final_score/final_time。

4. `_check_hash()` 只在不一致时报错，manifest 缺 `sha256` 时不会拒绝。

结论：P3 **STILL-BROKEN**。原利用路径仍存在：篡改 manifest 记录的 scene/judge/contract hash、构造非法 Part2 `best_success_value=2` 但 `best_score=0`、手改 `final_time_s`，`comp_score` 仍可能标成 diagnostic/valid。

### P4 — course runner ground 分类覆盖非 plane 地面：**STILL-BROKEN（部分修复）**

代码依据：`run_part1_course.py::CoursePolicyRunner.__init__()`：

```python
self.floor_geoms = {g for g in range(self.model.ngeom)
                    if self.model.geom_type[g] == mujoco.mjtGeom.mjGEOM_PLANE
                    or self.geom_names.get(g, "").startswith("ground")
                    or self.geom_names.get(g, "") in {"trench_bottom", "level_floor"}}
```

这覆盖了 `ground*`、`trench_bottom`、`level_floor`，但**没有覆盖 Part1 场景中实际存在的 `ramp_blocks_l/r`**。`comp_part1_geom_tags.py` 中：

```python
"ramp_blocks_l": {"ramp"},
"ramp_blocks_r": {"ramp"},
```

而 `TraversalBridge.surface_tags` 只认 `"bridge"`、`"platform_left"`、`"platform_right"` 等；`_Obstacle.update()` 的两足地面判罚要求：

```python
if self.ground_fail and self.supported and len(ground_feet) >= 2:
    self._fail("two_feet_ground:...")
```

`ramp` 不在 `floor_geoms`，也不在 bridge/platform tags。原 pro 指出的路径仍在：机器人从桥/平台掉到 `ramp_blocks_l/r` 上时，两只脚既不产生 `ground_feet`，也不产生 bridge/platform 证据，可能漏掉“≥2 足触地/掉桥”判罚。

结论：P4 只修了命名地面，**没有关闭原 `ramp_blocks_l/r` 利用路径**，STILL-BROKEN。

---

## 三、新问题清单

| 严重度 | 文件/函数 | 问题/利用路径 | 建议 |
|---|---|---|---|
| **blocker/high** | `comp_score.py::score_one` / `validate_external_evidence` | 校验函数定义但未调用；level hash 用 `scene` 键被 `_check_hash` 跳过；final_time 依赖未注入的 `__trials__`。篡改 hash、非法 Part2 档位、错误 final_time 仍可能通过。 | 在 `score_one` 中调用 `validate_external_evidence`，显式传入已加载 `trials`，支持 `scene` 键，缺 `sha256` 报错，并加篡改 self-test。 |
| **high** | `run_part1_course.py::run_policy_step` | pause 循环内 `apply_events` 处理 `abort` 后 `course.active=False`，但函数仍 `return True`；外层继续调用 `feed()` 会触发 `Part1Course.update()` 的 `RuntimeError("no active attempt")`。 | pause 循环后加 `if not course.active: return False`，确保 abort 结果外传并终止 route loop。 |
| **high** | `run_part1_course.py::CoursePolicyRunner.__init__` / `sample` | `floor_geoms` 未包含 `ramp_blocks_l/r` 等 Part1 非 plane 接近面；两足触 ramp 不进入 `ground_feet`。 | 显式定义 Part1 非任务地面集合，或把 `ramp_blocks_l/r` 等映射为 ground/环境面；加“两足触 ramp 必须失败”测试。 |
| **medium** | `comp_part1_course.py::begin_attempt` / `abort_attempt` | `recovery_violation` 在 `abort_attempt()` 和下一次 `begin_attempt()` 未复位。某次恢复位姿违规后 abort，下一次正常 attempt 仍可能被判 0 分。 | `begin_attempt()` 和 `abort_attempt()` 都显式 `self.recovery_violation = False`。 |
| **medium** | `comp_part1_judge.py::AttemptManager.note_recovery` / `Part1Course.resume` | `note_recovery` 记录 `[t, t]`，`resume` 没有更新 `pauses[-1][1]`；账本中暂停区间长度恒为 0，暂停时长证据不完整。 | `resume` 时闭合最后一次 pause 区间，并记录 resume 事件时间。 |
| **medium/low** | `run_part1_course.py::main` | 每次 attempt 新建 `CoursePolicyRunner`，`data.time` 重置；共享 `Part1Course.manager` 的 `events` 出现 `attempt_end t=94` 后 `attempt_start t=0.5` 的非单调时间。 | 正式整场复用同一 runner/session，或在账本中同时记录 attempt-local 时间和 session 时间并保证单调。 |
| **minor** | `comp_import_course_diag.py::main` | 全部 attempt 都 `skipped` 时 `best_idx` 留在 0，可能把 skipped attempt 当 best。 | 过滤 skipped 后若无 scored attempt，显式报错或 best=null。 |
| **low** | `comp_part1_course.py::export_report` | `rules.final_time` 仍写 `"min_over_attempts"`，与 summary 的 `min_duration_among_best_score_attempts` 不一致。 | 改为与 N3 语义一致的字符串。 |

---

## 四、三份 diagnostic 与当前代码/HASHES 的一致性

| artifact | 结论 | 依据 |
|---|---|---|
| `flat-ft-2500-part1-diag-v2` | **基本一致** | manifest judge version `850caa35ee23` 与当前 `comp_part1_judge.py`/`geom_tags` 前 6 位匹配；scene `c03cd3…`、contract `627d61…` 与 HASHES 一致；summary sha `bc128c…` 与 HASHES 一致；8 trials 全 fail，total=0。 |
| `flat-ft-2500-part2-diag-v2` | **基本一致，但 level XML 未能由 HASHES 复核** | judge `850caabb43b1` 匹配当前 part1/part2 judge；levels json `10c73a…`、contract `627d61…`、summary sha `13a9c1…` 与 HASHES 一致；各 category attempts 数与 trials 条数一致，全部 fail，best=null。level XML hash 在 manifest 中有，但 `HASHES.json` 未包含这些 XML，且 `comp_score` 也未实际校验 `scene` key。 |
| `flat-ft-2500-part1-course-diag` | **基本一致** | judge `850caa35ee23a491b1` 匹配当前 part1 judge/geom_tags/course；scene `c03cd3…`、route `4ed5bc…`、contract `627d61…` 与 HASHES 一致；summary sha `25c9bf…` 与 HASHES 一致；3 attempts × 8 obstacles = 24 trials，全 fail，total=0，return=0。minor：manifest notes 写“单次尝试”，summary `attempts_used=3`。 |

但必须注意：

- `HASHES.json` 仍是 `"audited": false`，`reviewer: "pending"`；
- HASHES 只覆盖三份 summary，不覆盖 manifest/trials/Part2 level XML；
- `comp_score` 的 P3 外部证据校验未生效，因此“diagnostic 状态”不是由机器 hash/level/final_time 复核保证的。

---

## 五、结论：是否满足 Codex 前的 flash 验收

**No。** 不满足“flash 验收无问题”。

仍存在 blocker：

1. **P3 未生效**：`comp_score` 外部证据校验函数未接线，level hash 键不匹配，final_time 复算无 trials；
2. **P4 原利用路径未关闭**：Part1 course runner 未把 `ramp_blocks_l/r` 等非 plane 接近面纳入 ground；
3. **pause 内 abort 终止信号未外传**：可能在暂停恢复/中止链路触发 `no active attempt` 崩溃。

### 最小修复清单

1. `comp_score.py`：在 `score_one()` 中调用 `validate_external_evidence`，显式传入 `trials`；支持 Part2 level 的 `scene` 键；缺 `sha256` 报错；加篡改 hash/非法 bool 值/错误 final_time 的自检。
2. `run_part1_course.py`：pause 循环内 `apply_events` 后若 `not course.active` 立即 `return False`。
3. `run_part1_course.py`：Part1 ground 集合显式覆盖 `ramp_blocks_l/r` 及其他非任务非 plane 面；加“两足触 ramp 必须失败”测试。
4. `comp_part1_course.py`：`begin_attempt()` / `abort_attempt()` 复位 `recovery_violation`；`resume()` 闭合 pause 区间。
5. 重新跑一次包含 pause/resume/abort/stable-stop 的 3-attempt course 诊断，重新导入三份 diagnostic，并更新 `HASHES.json`（至少包含 manifest、trials、level XML）。
6. minor：修 `export_report` 的 `rules.final_time` 文案；修 course importer 全 skipped fallback。

### G1 报告必须写明的残余风险

- 砂砾坑真实“坑 + 碎木”几何未 recut，当前仍是凸起盒代理；
- Part2 官方能力场逐档交叉核对未做，当前只覆盖自定义参数化 level；
- soft-reset 阈值、相邻 zone 重叠仍是启发式；
- Part1 单障碍诊断 importer 的 per-obstacle 汇总口径仅诊断用；
- 正式手动 3 次尝试/pause/resume/stable-stop 尚未在真实赛程上演练，当前 course diag 是脚本化路线；
- `HASHES.json` 仍 `audited=false`，覆盖不完整；
- 人工标定集/ judge 与人工标签比对仍未完成。
