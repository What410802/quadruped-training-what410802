verdict：**PASS**

## 一、第 10 轮 3 项逐项结论

| # | 结论 | 代码/证据依据 |
|---|---|---|
| ① formal Part2 `attempts_used` 与 trials 无条件对账 | **PASS** | `comp_score.py::validate_summary` 的 Part2 分支已改为先取 `reported = int(rec.get("attempts_used") or 0)`，再直接判断 `if reported != len(obs_trials)`；formal（`diagnostic=false`）下不一致一律 `_err`，不再有 `if obs_trials and ...` 短路。`attempts_used>0` 而该障碍 trials 为 0 时会报 error。 |
| ② official trial_id 使用真实 attempt | **PASS** | `comp_import_part2_diag.py` 已用 `attempt_num = int(att.get("attempt_index") or i)`，并生成 `trial_id = ...-a{attempt_num}-r{trial_seq}`；`run_part2_judged_eval.py --official` 用 `official_counter[cat]` 写入 `attempt_index`（1–4）。证据中 `flat-ft-2500-part2-official-diag/trials.jsonl` 已可见 `high_platform` 为 `a1-r1`、`a2-r2`、`a3-r3`、`a4-r4`，`high_wall` 为 `a1-r5`…`a4-r8`，不再全为 `-a1-`。 |
| ③ `pause_timeout` 的 `operator_t` 进入 AttemptResult/manager events | **PASS** | `run_part1_course.py` 的暂停超时分支先向 `course._current_events` append `{"event": "pause_timeout", "operator_t": fake}`，再调用 `course.abort_attempt(fake, "pause_timeout")`；`comp_part1_course.py::abort_attempt` 用 `list(self._current_events)` 落入 `AttemptResult.events`，随后 `manager.skip` 的 skip 事件补 `operator_t`。证据 `comp/audits/evidence/part1_course_pause_timeout_drill.json` 中：`attempt_result.events` 含 `pause_timeout` 且 `operator_t=121.01999999999306`；`session_summary.events` 的 `skip` 事件也带同一 `operator_t`，attempt reason 为 `pause_timeout`。 |

## 二、N1–N4 / P1–P4 与历史 PASS 回归

均未发现回归：

- **N1 PASS**：`run_part1_course.py::run_policy_step` 每个物理步 `physics_step()` 后立即 `feed()`，即 5 ms 级采样；暂停时冻结物理。
- **N2 PASS**：`comp_import_course_diag.py` 使用 per-attempt `attempt_result`，按 `(score, -duration)` 选 best。
- **N3 PASS**：`comp_part1_course.py::Part1Course.summary` 与 `AttemptManager.summary` 均为最高分尝试内取最快，并写 `final_time_scope`。
- **N4 PASS**：`comp_score.curve_points` 与 `comp_part2_judge.curve_points_floor` 的 bool 分支均只认 `float(value) == 1.0`。
- **P1 PASS**：稳定停表使用 `cpr.model.opt.timestep`，`StableStopTracker` 按真实物理 dt 累计。
- **P2 PASS**：暂停循环只推进 operator 时钟与 `apply_events`，不调用 `course.update`。
- **P3 PASS**：`comp_score.score_one` 已调用 `validate_external_evidence`，复核 scenes/judge/contract hash、Part2 合法档位、Part1 final_time。
- **P4 PASS**：`comp_part1_geom_tags.GROUND_GEOM_NAMES` 为精确白名单，`is_ground_geom()` 不再使用 `startswith("ground")`。
- 历史口径：Q2 ×2/3、最高分优先同分最快、稳定停表、恢复不消耗、返回奖励需全满分后重进出发区、Part2 仅 RL 且每项 4 次，均未在代码/证据中看到回归。

## 三、四份 eval 产物与 HASHES

**一致，可复算。**

- `HASHES.json` 的 `objects` 计 60 项，符合“60 objects”。
- 四份 eval 产物均纳入 manifest/trials/summary 共 12 项：
  - `flat-ft-2500-part1-diag-v2`
  - `flat-ft-2500-part2-diag-v2`
  - `flat-ft-2500-part2-official-diag`
  - `flat-ft-2500-part1-course-diag`
- 抽查文件头 sha256 与 `HASHES.json` 一致，例如：
  - official summary `e2b277...` 与 `HASHES.eval_flat-ft-2500-part2-official-diag_summary` 一致；
  - course summary `74ca66...` 与 `HASHES.eval_flat-ft-2500-part1-course-diag_summary` 一致；
  - part1-diag summary `bc128c...`、part2-diag summary `13a9c1...` 均一致；
  - `part1_course_pause_timeout_drill.json` 的 `f6b3aa...` 也在 HASHES 中。
- `HASHES.json` 的 `audited:false / verdict:pending` 是 G1 前预期状态，不是 blocker。
- 四份产物均为 diagnostic / official_diagnostic，不是正式分数；这符合当前链路诊断定位，不构成阻塞。

## 四、是否仍有 blocker 或必须清理项

**未发现新的 scorer blocker；在当前 60 个审计对象与四份 eval 产物范围内，未发现“无问题”验收的必须清理项。**

当前剩余项均为 G1 报告必须写明的已知残余/口径，不是本轮 blocker。

## 五、结论

**满足“进入 Codex 前的 flash 验收（无问题）”：yes。**

无需给最小修复补丁。

## 六、G1 必写残余

1. **Q2 ×2/3 口径**：T 台阶两侧都过 = 100；仅上 = 50；仅下 = 33；返回奖励只认单项满分。
2. **排序与计时**：分数最高优先、同分取最快；计时在机器人稳定停下后停止；恢复不消耗尝试。
3. **返回奖励**：必须“全部障碍满分后重新进入出发区”，部分分不触发返回奖励。
4. **Part2 口径**：仅 RL；每项最多 4 次；official 模式不足 4 档时重复最高档，确定性策略下重复档的稳定性统计意义有限，需写明“4 次中的重复档”口径。
5. **Part1 操作方式**：手动/自动均允许，自动无额外加分；正式手动 3 次尝试演练尚未在真实赛程上完成，当前主要是脚本化诊断链路。
6. **砂砾坑真实几何**：本地仍为凸起盒代理，不是真实“坑 + 碎木” recut 几何。
7. **Part2 官方能力场交叉核对**：尚未在官方 `terrain.zip` 能力场逐档交叉核对；当前验证的是同种类参数化 level。
8. **soft-reset 启发式**：soft-reset 阈值与相邻 zone 重叠仍是启发式，正式整场顺序通过时影响有限但需列明。
9. **跨 attempt 时间线**：每个 attempt 新建 runner，模拟器时间从 0.5 重置，跨 attempt 事件时间线不可全局排序，需在 G1 证据说明中保留。
