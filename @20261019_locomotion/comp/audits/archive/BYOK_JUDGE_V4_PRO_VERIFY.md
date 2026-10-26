## Verdict

**FAIL（预审建议）**。

N1–N4 四项本身均已修复；但本轮逐物理步采样重构暴露出两个新的正式链路问题：**Part 1 稳定停表的时间/速度口径错误**、**暂停期间继续把冻结位姿喂给 judge**。另外 `comp_score` 仍不能机器复核外部哈希、最终用时与 Part2 合法档位。因此不建议现在以 PASS 预期送 Codex G1。

---

## N1–N4 逐项核验

### N1：正式 course runner 是否逐物理步采样

**PASS**

代码依据：`scripts/agent_scripts/run_part1_course.py`

- `CoursePolicyRunner.step_policy()` 仍然是一次执行 4 个 `mujoco.mj_step`，但它现在只用于 `run_attempt()` 的 **warmup**，不在计分过程中。
- 计分路径在 `run_policy_step()`：

```python
cpr.set_action(command)
for _ in range(4):
    cpr.physics_step()
    sample = feed()   # feed() -> course.update(...)
```

这样每个 5 ms 物理步后都调用一次 `course.update()`，judge/course 观测频率与物理步一致。

**原利用路径已关闭**：<20 ms 的“任意瞬间 ≥2 足触地”不再被漏判。

**仍存在的相关问题**：不是 N1 本身，而是同一区域里稳定停表 dt 口径错误（见新问题 P1），以及暂停分支仍把冻结位姿送入 judge（见 P2）。

---

### N2：course importer 是否基于 per-attempt `AttemptResult` 选择 best

**PASS**

代码依据：`scripts/agent_scripts/run_part1_course.py`、`comp_import_course_diag.py`

- runner 每次 attempt 返回：

```python
"attempt_result": course.results[-1].to_dict()
```

- importer 现在读取 per-attempt 记录：

```python
def _att_rec(att: dict) -> dict:
    return dict(att.get("attempt_result") or {})
```

- best 选择使用 per-attempt `score` / `duration_s`：

```python
key = (float(rec.get("score", 0.0)), -float(rec.get("duration_s", 0.0)))
```

- trials 的 `duration_s` 也来自该 attempt 自己的 `duration_s`，不再使用全局 `final_time_s`。

原 N2 的“第二次及以后 attempt 被全局 summary 污染”路径已关闭。

残余小问题：如果所有 attempt 都被 `skipped`，`best_idx` 会停留在第 0 个 attempt，可能把 skipped attempt 当 best；当前诊断数据未触发，但正式 importer 语义应处理。

---

### N3：同分最快时间是否只在最高分尝试内取

**PASS**

代码依据：

`comp_part1_judge.py::AttemptManager.summary`

```python
best_score = max((a["score"] for a in scored), default=0.0)
best_candidates = [a for a in scored if a["score"] == best_score]
fastest = min((a["duration_s"] for a in best_candidates), default=0.0)
```

`comp_part1_course.py::Part1Course.summary`

```python
best_score = max((r.score for r in scored), default=0.0)
best_candidates = [r for r in scored if r.score == best_score]
summary["final_score"] = best_score
summary["final_time_s"] = min((r.duration_s for r in best_candidates), default=0.0)
summary["final_time_scope"] = "min_duration_among_best_score_attempts"
```

原 N3 的“低分短用时抢跑最终时间”路径已关闭。

残余：`Part1Course.export_report()` 的 `rules.final_time` 仍写 `"min_over_attempts"`，与真实语义不一致；`comp_score` 目前完全不校验 `final_time_s`。

---

### N4：bool 曲线是否只认 `value == 1`

**PASS**

代码依据：

`scripts/agent_scripts/comp_score.py::curve_points`

```python
if unit == "bool":
    return int(math.floor(curve[-1]["points"])) if float(value) == 1.0 else 0
```

`scripts/agent_scripts/comp_part2_judge.py::curve_points_floor`

```python
if unit == "bool":
    return int(math.floor(curve[-1]["points"])) if float(value) == 1.0 else 0
```

原 N4 的“任意非零都给满分”路径已关闭。

残余：`comp_score` 仍未校验 Part2 `best_success_value` 是否为合法档位/声明 level；例如一个构造的 `value=2` bool“成功” trial 仍可通过匹配逻辑，虽然曲线不再给分，但证据链没有拒绝这种非法档位。

---

## 新问题清单

### P1 — 稳定停表用错 dt，导致可能提前停车计时

- **严重度**：blocker  
- **文件/函数**：`scripts/agent_scripts/run_part1_course.py`，`run_attempt()` 内 stable-stop 块  
- **错误路径**：
  - 每个物理步是 5 ms，但速度计算用：

    ```python
    speed = float(np.linalg.norm(pos - prev)) / 0.02
    ```

  - `stable` 也每次加 `0.02`：

    ```python
    if speed < 0.15 and tilt < 10.0:
        stable += 0.02
    ```

  这意味着：
  - 0.5 s 的稳定判定，实际约 25 次采样即可能达到：25 × 5 ms = **0.125 s**；
  - 速度阈值被放大 4 倍：真实速度约 0.6 m/s 仍可能被算成 `<0.15`；
  - 返回出发区后可提前停止计时，正式同分排序会拿到不公平的短用时。

- **建议**：使用真实 `sample["t"]` 增量或 `model.opt.timestep` 计算速度，并用真实秒数累计 `stable`。

---

### P2 — 暂停期间仍把冻结位姿喂给 judge，且 resume 后时钟可能非单调

- **严重度**：blocker  
- **文件/函数**：
  - `run_part1_course.py`，`run_policy_step()` 的 pause 循环
  - `comp_part1_course.py`，`Part1Course.update()`

- **错误路径**：

  `Part1Course.update()` 即使 `self.paused == True` 仍会执行：

  ```python
  report = self.judge.update(t, base_xyz, yaw, **kwargs)
  ```

  暂停循环中：

  ```python
  while course.paused and course.active:
      fake += 0.02
      course.update(fake, sample["base_xyz"], ...)
  ```

  后果：
  - 冻结位姿被重复送入障碍状态机，`in_zone_samples`、`bridge_hits`、`cross_valid` 等可能持续累积；
  - 若位姿恰好位于 `y == wall_cross_y` / `y == -9` 等边界上，`prev_y == cur_y` 会使 `cross_valid` 反复增加；
  - 暂停中可能把本不该发生的 success/fail 判出来；
  - resume 后 `prev_t` 被设成 fake clock，后续真实物理时间可能小于 fake 时间，导致事件时间非单调；
  - 若 abort 事件在 pause 循环内被 `apply_events` 处理，`run_policy_step()` 仍返回 `True`，下一轮可能调用已无 active attempt 的 `course.update`。

- **建议**：暂停期间只推进操作手事件/超时时钟，不调用 `judge.update`；resume 后恢复真实物理时钟，并把 abort 终止信号显式往外传。

---

### P3 — `comp_score` 仍不机器复核外部哈希、最终用时和合法档位

- **严重度**：high  
- **文件/函数**：
  - `comp_score.py::validate_manifest`
  - `comp_score.py::validate_summary`

- **错误路径**：
  - `validate_manifest` 只检查 manifest 里有没有 `sha256` 字段，不重新计算场景、judge、policy、route/level 文件的实际 sha256。
  - `validate_summary` 完全不校验 `final_time_s` / attempt duration。
  - Part2 `best_success_value` 没有与 `score_curve` 的档位或 `part2-levels.json` 的合法 level 集合比对。

- **建议**：正式前 `comp_score` 至少应：
  1. 重新计算 manifest 引用的 scene/judge/policy/route/levels 文件哈希并拒绝不一致；
  2. 校验 Part1 final_time 来自可靠 per-attempt 结果；
  3. 校验 Part2 best_success_value 必须属于合法档位，bool 只允许 1。

---

### P4 — Part1 course runner 的 ground 识别只认 `mjGEOM_PLANE`

- **严重度**：high  
- **文件/函数**：
  - `run_part1_course.py::CoursePolicyRunner.__init__`
  - `run_part1_course.py::CoursePolicyRunner.sample`

- **错误路径**：

  ```python
  self.floor_geoms = {g for g in range(self.model.ngeom)
                      if self.model.geom_type[g] == mujoco.mjtGeom.mjGEOM_PLANE}
  ```

  只有 plane 被识别为 ground。

  但 Part1 scene 中有非 plane 的地面/接近结构，例如 `ramp_blocks_l`（x=1.8,y=-0.88）位于 `bridge_blocks` zone 内。它既不是 `bridge`/`platform` tag，也不是 `floor_geoms`。若机器人从桥上掉到该 ramp 上，两只脚可能既不产生 `ground_feet`，也不产生 bridge/platform 证据，从而漏掉 “≥2 足触地” 或 “掉桥” 判罚。

- **建议**：ground 不应只包含 plane；应显式定义 Part1 场景中所有“非目标任务表面”的 ground/环境 geom，或至少把 ramp 等接近面映射为 ground 判据。

---

### P5 — recovery violation 状态泄漏 + pause 记录未闭合

- **严重度**：medium  
- **文件/函数**：
  - `comp_part1_course.py::begin_attempt` / `abort_attempt`
  - `comp_part1_judge.py::AttemptManager.note_recovery`

- **错误路径**：
  - `recovery_violation` 在 `abort_attempt()` 中没有复位；若某个 attempt 因恢复位姿违规后被 abort，下一个 attempt 正常结束时仍会被判成 `recovery_pose_violation`。
  - `AttemptManager.note_recovery()` 记录 `[t, t]`，`resume` 没有更新结束时间，账本里的 pause 区间一直是 0 长度，暂停时长证据不完整。

---

### P6 — course importer 的全 skipped 场景 fallback

- **严重度**：minor  
- **文件/函数**：`comp_import_course_diag.py` main 中 `best_idx` / best fallback

- **错误路径**：若全部 attempt 均 skipped，best 会落到第一个 skipped attempt。当前诊断数据无此情况，但正式 3 次尝试可能主动重跑后出现。

---

## 既有残余风险（仍未清零）

1. **砂砾坑真实“坑 + 碎木”几何未 recut**：当前 scene v2 仍是凸起盒代理，不能作为正式 Part1 能力证据。
2. **Part2 官方能力场逐档交叉核对未做**：当前结论只覆盖自定义参数化 level。
3. **正式 3 次 manual/pause/resume/stable-stop 演练仍未做**：当前 course diag 只有脚本化 2 次尝试。
4. **`comp_score` 对哈希的核验只是人工完成，工具本身不强制**。

---

## 三份 diagnostic 的哈希与 summary 复算

手工核验结果：

| artifact | manifest judge version 与当前代码 | 场景/配置 hash | summary 是否能由 trials 复算 |
|---|---|---:|---|
| `flat-ft-2500-part1-diag-v2` | `850caa35ee23`，匹配当前 `comp_part1_judge.py` 前 6 位 `850caa`、`geom_tags` `35ee23` | scene v2 sha 匹配当前文件 | 8 条 trial 全 fail，obstacle/evidence/total 一致，total=0 |
| `flat-ft-2500-part2-diag-v2` | `850caabb43b1`，匹配 part1 judge 前 6 位 `850caa`、part2 judge `bb43b1` | `config/part2-levels.json` sha 匹配当前文件 | 每类 attempts_used 与 trials 条数一致，全部 fail，best=null，total=0 |
| `flat-ft-2500-part1-course-diag` | `850caa35ee233e1e3b`，匹配 part1 judge + geom tags + course 前 6 位 | scene v2、route sha 均匹配 | 2 attempts × 8 obstacles = 16 trials，全 fail，total=0，return=0 |

**注意**：Part2 manifest 里每个 level scene XML 的 sha256 未能在本轮提供文件范围内独立复算；`comp_score.py` 自身也不会复算这些哈希。

---

## 是否可送 Codex G1

**No，暂不建议送审。**

当前 N1–N4 已经修好，但 P1、P2 会直接影响正式 Part 1 计时和恢复语义，P3/P4 影响证据链与核心两足触地判罚。现在送 Codex，大概率仍会得到 FAIL 或至少 CONCERN。

### 送审前必须完成的最小修复集合

1. **修 P1**：稳定停表必须使用真实物理 dt；
2. **修 P2**：暂停期间只推进事件/超时时钟，不调用 judge；resume 后恢复真实时间；
3. **修 P3**：`comp_score` 重算外部文件哈希，校验 Part1 final_time，校验 Part2 legal level/bool 值；
4. **修 P4**：Part1 course runner 的 ground 分类覆盖非 plane 环境表面；
5. **重新生成并核验三份 diagnostic + HASHES.json**；
6. 至少执行一次包含 **pause/resume/abort/stable-stop** 的 3-attempt course 链路，确认不会出现 P1/P2 现象；
7. 砂砾坑、Part2 官方能力场、正式手动 3 次演练若仍不能完成，必须在送审材料中明确标为 “禁止正式计分的已知缺口”。

### Codex G1 应重点检查的 3–5 项

1. `run_part1_course.py` 的 stable-stop 与 pause 循环是否仍会提前停表或在冻结时改变 judge 状态；
2. `comp_import_course_diag.py` / `comp_part1_course.py` 是否真的按 per-attempt score/duration 选 best，且同分取最快只发生在最高分尝试内；
3. `comp_score.py` 是否已经机器复核外部文件哈希、Part1 final_time、Part2 合法档位和 bool `==1`；
4. Part1 course runner 的 ground/contact 分类是否能完整覆盖“≥2 足触地”与“掉桥/掉坡”语义；
5. 砂砾坑真实几何、Part2 官方能力场、正式 3-attempt 操作手演练是否仍保留为不可正式计分的残余风险。
