<!-- BYOK 第三轮预审（DeepSeek pro，provisional） -->
# BYOK Judge V3 Pro Review（DeepSeek v4-pro，same-family-provisional）

> **verdict（原始输出）**：FAIL。前两轮 blocker 中 23/26 PASS；正式整场链路 N1–N4 仍为 blocker：
> ① course runner 未逐物理步采样（漏判任意瞬间 1/2 足）；② course importer best-attempt/duration 口径错；
> ③ 同分最快时间口径未落到"最高分尝试内取最快"；④ bool 曲线仍非 ==1。
> **后端/模型**：DeepSeek relay，`deepseek-v4-pro`；executor `deepseek-v4.1-flash` → same-family-provisional
> **meta**：`BYOK_JUDGE_V3_PRO_REVIEW.json`；**trace**：`comp/traces/comp-review/2026-10-22_run03`
> 以下为 reviewer 原始输出，executor 未改写；修复映射见 `BYOK_JUDGE_V2_FIXES.md` §"Pro 预审后修复"。

## verdict：FAIL

预审建议仍为 **FAIL**。核心 judge 语义的大部分前两轮 blocker 已修，但正式整场链路里仍有 **bloker 级**的证据链/规则执行问题：Part1 正式 runner 没有逐物理步采样，导致“任何瞬间 ≥2 足触地”可被漏判；course importer 的 best-attempt 选择与 duration 口径是错的；bool 曲线任意非零给满分的修复声明与实际代码不符。另有 sand pit 真实几何未 recut 等已记录残余，仍不能给 PASS。

---

## 1. 前两轮 blocker 处置核验表

| # | 前两轮问题 | 结论 | 验证摘要 |
|---|---|---|---|
| 1 | ground_fail 把进场前地面算入障碍区 | **PASS** | `_Obstacle.supported` 门控：先有 surface 触碰且无地面支撑，之后 ≥2 足 ground 才 fail；conformance `test_approach_ground_is_not_failure` 覆盖 |
| 2 | 高墙可 y 侧进出/地面高度穿越骗成功 | **PASS（残余较小）** | `HighWall._on_sample` 要求穿越 y=-7 时 `base z>=0.60`；删除了 wall tag 作为证据；`test_high_wall_sideways_climb_and_bypass` 覆盖地面高、侧擦、wall-touch-at-ground |
| 3 | 真实桥面 geom 未映射 bridge tag | **PASS** | `GEOM_TAGS` 覆盖 `bridge_blocks_*`、`bridge_bands_*`；`test_scene_geom_tags_complete` 对 scene v2 做完整性检查 |
| 4 | T 台阶未逐级、分支/部分分错误 | **PASS** | `TStairs` 三臂 s/n/e + 每级 1..3；Part1JudgeV2 默认 50/33；partial->full 升级 conformance 覆盖 |
| 5 | 绕杆提前终点、反向不支持、半径不一致 | **PASS** | `Slalom` 推断 A/B 方向，corner_after 方向相关，终点区需已收齐 4 杆+corner；conformance forward/reverse/early-end/early-corner 覆盖 |
| 6 | 限高杆门外穿越、掉杆检测不完整 | **PASS** | `bar_base_seen/bar_dropped_seen` 为持久状态，预掉落不可重试洗掉；门洞 x∈[5.2,6.2] 且 y=-9 连续穿越 |
| 7 | 成功后永久锁定、失败后不能重试 | **PASS** | success finally locked；`_fail` 记录事件后重 arm；`test_failure_can_be_retried_and_success_is_final` |
| 8 | 返回奖励未要求全部满分后重新进出发区 | **PASS** | `Part1JudgeV2.update` 先检查 start entry 再更新 `all_full_done`，需全满分后再次 entry；course self-test |
| 9 | Part2 低难度“站地面”伪成功 | **PASS** | `Part2JudgeV2._cond` 对 platform/stairs/slope/plum 要求 `not ground_feet` 且对应 surface tag；self-test 覆盖离 lane 1m、无接触反例 |
| 10 | Part2 高墙/沟壑/梅花桩可绕行 | **PASS** | `wall` 需 lane 内跨 wall_x + wall_contact + max_z_near；`gap` 需先后跨 near/far 或一次越过；plum 需 tag+无 ground |
| 11 | 正式整场协议未接 runner/importer | **STILL-BROKEN** | `run_part1_course.py` 已有 course 会话，但采样频率、importer best attempt、正式 3 次演示仍存在问题，见新问题 N1/N2/N7 |
| 12 | 恢复/暂停可传送、账本时长不一致 | **PASS（正式链路未完全闭环）** | `Part1Course.pause/resume` 有姿态校验，active time 排除 pause；runner 有 pause timeout；但 stable wait 期间不处理 event，且正式 manual operator 仍未演练 |
| 13 | soft-reset 阈值启发式 | **STILL-BROKEN（已知残余）** | `_check_exit` 的 `in_zone_samples>=5` 等阈值仍是启发式；真实整场顺序通过时影响有限，但仍存在 |
| 14 | 斜坡欧氏距离/横向凑 | **PASS** | `Slope._on_sample` 只累计 `abs(y-last_y)`；斜向 x 不计；`test_slope_projection_and_graze_reset` |
| 15 | 接触只看法向 geom name | **PASS（实现存在采样粒度问题）** | `run_part1_course` 中 `CoursePolicyRunner.sample` 做 `normal_z>=0.5` 过滤，但采样粒度问题见 N1 |
| 16 | 砂砾坑非“坑+碎木” | **STILL-BROKEN（已知残余）** | scene v2 仍是两个凸起盒代理；judge 只验证 surface tag/short-edge，未验证真实坑几何 |
| 17 | 场景映射不一致 | **PASS** | T 三臂 tag、共享平台双 tag、显示圆半径 0.5m 已更新 |
| 18 | Part2 每项 4 次 runner/importer | **PASS（策略保守）** | `--official` 每 category 最多 4 档高→低；诊断默认 1 次。但“同一难度重试”未实现，作为正式策略可能过弱 |
| 19 | Part2 证据链缺 level XML hash | **PASS** | manifest 对每级 scene 记录 sha256 |
| 20 | Part1 产物 operator/attempts 与真实运行不符 | **PASS（诊断）** | manifest 标 diagnostic，operator/attempts 如实 |
| 21 | importer 丢重复尝试/0 分提升 | **PASS（course importer 仍有 N2）** | diagnostic importer 聚合口径仍为 per-task；course importer 有 best-attempt/duration bug |
| 22 | conformance 全是合成数据 | **PASS** | `comp_judge_conformance.py` 使用真实 scene v2 geom/tag 并覆盖行为反例 |
| 23 | 参数化 level 只生成曲线节点 | **PASS（接受）** | 曲线节点即官方档位 |
| 24 | bool 曲线任意非零满分 | **STILL-BROKEN** | `comp_part2_judge.curve_points_floor` 与 `comp_score.curve_points` 仍为 `value not in (0.0,)` 给满分，不是 `==1.0`；见 N4 |
| 25 | 诊断 runner 总分含非目标任务 | **PASS** | V2 runner/import 只汇总目标状态；course importer 逻辑另有 N2 |
| 26 | 相邻 zone 重叠污染桥状态 | **STILL-BROKEN（残余启发式）** | soft-reset 依赖，正式顺序通过影响有限 |

---

## 2. 新问题清单（严重度降序）

### N1 — Part1 正式 runner 没有逐物理步采样，违反“任何瞬间 ≥2 足触地”

- **严重度**：blocker
- **文件/函数**：`scripts/agent_scripts/run_part1_course.py`  
  - `CoursePolicyRunner.step_policy`
  - `run_attempt`
- **利用/错误路径**：  
  `step_policy` 一次执行 4 个 `mujoco.mj_step`，随后 `run_attempt` 才调用一次 `cpr.sample()` 并 `course.update(...)`。因此 judge/course 的观测频率是 20 ms，不是物理步 5 ms。  
  - 一个 <20 ms 的双足接地事件可完全不被 `ground_feet` 捕获，导致本应 fail 的“任何瞬间 ≥2 足触地”非法路径被判为成功。  
  - 短暂坡面/桥面/台阶 surface tag 接触也可能被漏掉，造成合法通过的误伤或必须重跑。
- **建议**：像 Part2 runner 一样，在 `mujoco.mj_step` 循环内对每一步物理步后采集 contact 并调用 `course.update`；不要只在 `step_policy` 结束后采样一次。  
  正式整场 runner 必须做到“judge 观测与物理步同频”。

---

### N2 — course importer 使用的 `report.summary` 是全局 summary，best attempt 选择与 duration 错误

- **严重度**：blocker（证据链）
- **文件/函数**：`scripts/agent_scripts/comp_import_course_diag.py`  
  - `attempt_summary`
  - main 中 `best_idx`/`key` 计算
  - trial `duration_s` 赋值
- **利用/错误路径**：  
  `run_part1_course.py` 的 `run_attempt` 在每个 attempt 结束后返回 `"report": course.export_report()`。  
  `course.export_report()` 调用 `Part1Course.summary()`，得到的是**当前已结束所有 attempts 的全局 final_score/final_time**，不是该 attempt 自己的结果。  
  importer 里：
  ```python
  s = attempt_summary(att)  # 实际是全局 summary
  key = (final_score, -final_time)
  ```
  如果 attempt1 score=900/duration=100，attempt2 score=800/duration=50：  
  - attempt1 的 report global final_time=100  
  - attempt2 的 report global final_time=50，global final_score=900  
  importer 会选 attempt2，因为 `(900, -50) > (900, -100)`，然后拿 attempt2 的 judge states 作为 best，导致最优 attempt 被漏选，最终 summary 报低分。  
  同时 trials 里的 `duration_s` 也用全局 `final_time_s`，导致非零分 attempt 的每个 trial 时长可能不是该 attempt 的真实 active time。
- **建议**：  
  - runner 应输出每个 attempt 的 `AttemptResult.to_dict()` 作为 per-attempt 结果，或 importer 应从最终 `session_summary.attempt_results` 选择 best attempt；  
  - importer 的 `duration_s` 应取 `attempt_results[i].duration_s`，不要用全局 `final_time_s`。

---

### N3 — `Part1Course.summary` 的 `final_time_s` 是“所有尝试最快者”，不是“最高分尝试中同分取最快者”

- **严重度**：blocker（会影响同分排序）
- **文件/函数**：  
  - `scripts/agent_scripts/comp_part1_course.py`, `Part1Course.summary`
  - `scripts/agent_scripts/comp_part1_judge.py`, `AttemptManager.summary`
- **错误路径**：  
  ```python
  summary["final_score"] = max(r.score for r in self.results if not r.skipped)
  summary["final_time_s"] = min(r.duration_s for r in self.results if not r.skipped)
  ```
  如果 attempt1 得分 900、用时 100s；attempt2 得分 800、用时 50s，最终上报 `(900, 50s)`。50s 不是 900 分那次尝试的成绩，排名同分时会获得不公平优势。  
  已确认口径是“分数最高优先，同分取最快”，应只在获得最高分的 attempt(s) 中取最快，而不是所有 attempt 中取最快。
- **建议**：  
  `final_score` 为最高分；`final_time_s` 应取达到该最高分的全部 attempt 的最短用时。若多个不同分数，低分 attempt 的时间不得作为最终时间。

---

### N4 — bool 曲线“任意非零满分”没有被修复，修复声明不符

- **严重度**：major
- **文件/函数**：  
  - `scripts/agent_scripts/comp_part2_judge.py`, `curve_points_floor`
  - `scripts/agent_scripts/comp_score.py`, `curve_points`
- **错误路径**：  
  ```python
  if unit == "bool":
      return int(curve[-1]["points"]) if float(value) not in (0.0,) else 0
  ```
  这等价于“任何非零值都给满分”。`value=2`、`value=-1`、`value=0.5` 都会拿到 200。  
  `BYOK_JUDGE_V2_FIXES.md` 声称“已修：bool 只认 value==1”，但当前代码不是只认 1。  
  `comp_score.validate_summary` 也没有校验 `best_success_value` 必须是合法档位，因此若 summary/trials 中构造 plum `value=2` 且 trial success，会被按 200 分接受。
- **建议**：  
  bool 单位应改为 `return full if float(value) == 1.0 else 0`；`comp_score` 应校验 Part2 每个 `best_success_value` 属于对应 `score_curve` 或级别清单。

---

### N5 — `comp_score` 不校验 scene/judge/policy 哈希的当前实际值

- **严重度**：major（证据链）
- **文件/函数**：`scripts/agent_scripts/comp_score.py`, `validate_manifest`
- **错误路径**：  
  `validate_manifest` 只检查 manifest 中有无 `judge.version`、`policy.checkpoint_sha256` 等字段，不重新计算当前 `scenes`、`judge.files`、`policy.pt` 的 sha256 做比较。  
  因此 manifest 可以声称任意的场景/判据/策略哈希，comp_score 仍可通过。  
  当前提供的三个 diagnostic manifest 的哈希与代码/配置看起来一致，但这是人工核对，不是 `comp_score` 自动保证。
- **建议**：  
  `comp_score` 应在 validate 阶段读取 manifest 中引用的 scene/judge/policy 文件，重新 sha256，并拒绝不一致的 manifest，至少对正式行强制。

---

### N6 — 砂砾坑真实“坑 + 碎木”几何仍未 recut

- **严重度**：major（已记录残余）
- **文件/场景**：`assets/terrain/part1/part1_eval_scene_v2.xml`, `comp_part1_judge.GravelPit`
- **错误路径**：  
  场景里 `gravel_pit_a/b` 只是两个凸起盒代理，不是规则要求的凹陷坑、碎木坑底。  
  当前 judge 只查 `gravel` tag 和短边进出，无法证明真实坑体可以通过。  
  即使 Part1 core judge 逻辑正确，场景几何不真实仍可能产生假成功/假失败，且无法在正式赛程中作为可信能力证据。
- **建议**：  
  正式前必须 recut 真实坑几何并重跑 conformance；在此之前最多标 `diagnostic`，不能作为正式 Part1 分数依据。

---

### N7 — 正式整场 3 次尝试/操作手演练仍未证明

- **严重度**：high（协议完整性）
- **文件/产物**：`comp/eval/flat-ft-2500-part1-course-diag/`、`comp/eval/_protocol.md` §8
- **错误路径**：  
  当前 course diagnostic 产物 `attempts_used=2`，是脚本化 waypoint，不是正式操作手；`_protocol.md` 也明确“正式整场 MuJoCo runner（操作手/键盘或控制仓接入）未接”。  
  `run_part1_course.py` 支持 `--attempts 3`，但尚未在真实 3 次整场运行过；pause/resume 事件在 stable stop 阶段不会被处理（`run_attempt` 的 stable wait 循环不调用 `apply_events`），可能造成正式运行中的事件丢失或暂停后处理不一致。
- **建议**：  
  G1 前至少要执行一次 3-attempt 正式脚本链路并记录 per-attempt 结果；stable wait 期间也要处理 operator events。

---

### N8 — Part2 官方能力场逐档交叉核对仍未做

- **严重度**：high（已知缺口）
- **文件/协议**：`comp/eval/_protocol.md` §8、`make_part2_levels.py`
- **错误路径**：  
  Part2 evaluator 只在自定义参数化 level 上验证，官方 `terrain.zip`/`part2_ability_field.xml` 地图未做逐档交叉核对。  
  参数化 level 的 judge 参数可能无法平滑迁移到官方场，尤其 lane_y、goal_x、platform/top_z 等依赖本地场景几何。
- **建议**：  
  至少逐一核对六类障碍的官方地图尺寸与 `part2-levels.json` 的 judge 参数；不做完，不应给正式 Part2 结论。

---

## 3. 证据链核验

- **当前三份 diagnostic summary/trials 的低分 0 分态可复算**：  
  - `flat-ft-2500-part1-diag-v2`：8 条 trial 与 summary 的 status/failure_reason/evidence 基本一致，total=0。  
  - `flat-ft-2500-part2-diag-v2`：每个 category 的 attempt 数量与 trials 数量一致，best_success_value=null，total=0。  
  - `flat-ft-2500-part1-course-diag`：2 次 attempts，每次 8 obstacle trials，均 fail/route_complete，summary total=0。  
  这些 artifact 自身无明显伪造，但都是 `diagnostic=true`，不能作为正式能力分数。

- **哈希一致性**：  
  - Part1 diag manifest 的 judge version `b1cda035ee23` 与当前 `comp_part1_judge.py` 前 6 位 `b1cda0`、`comp_part1_geom_tags.py` 前 6 位 `35ee23` 一致。  
  - Part2 manifest judge version `b1cda03f9bad` 与当前 part1/part2 judge 前 6 位一致。  
  - Course manifest judge version `b1cda035ee23bc2619` 与 course/judge/geom 前 6 位一致。  
  - Part1 scene sha `c03cd34...` 与提供文件 sha 一致；`config/part2-levels.json` sha `10c73...` 与提供文件一致。  
  - 但上述只是人工核验，`comp_score.py` 自身不会重新计算并拒绝不一致。

- **`comp_score` 覆盖缺口**：  
  - 覆盖了返回奖励前条件、Part1 部分分、Part2 曲线插值、总分重算。  
  - 不覆盖 scene/judge/policy 实际哈希复算；bool 单位也仍有非零给满分问题。  
  - 因此证据链仍不能算 machine-checked end-to-end。

---

## 4. Codex G1 必查项与是否送审建议

### 必查项

1. **Part1 course runner 的逐物理步采样**：确认 `run_part1_course.py` 是否真的每 5 ms 向 `Part1Course.update` 喂一次 judge 状态；当前代码不是。
2. **course importer 的 best attempt 语义**：确认 `comp_import_course_diag.py` 是否基于每 attempt 的 `AttemptResult` 选择 best，而不是基于全局 `export_report`。
3. **同分最快时间口径**：确认 `Part1Course.summary` 和 `AttemptManager.summary` 的 `final_time_s` 是否只在最高分尝试中取 min。
4. **bool 曲线**：确认 `comp_score.curve_points` 与 `comp_part2_judge.curve_points_floor` 是否真的只认 `value==1`。
5. **comp_score 外部哈希复核**：确认 manifest 中场景、judge、policy 的 sha256 是否由工具重新计算并校验。
6. **砂砾坑真实几何**：是否已 recut，或至少在 G1 报告明确阻断正式积分。
7. **正式 3-attempt + pause/resume/stable stop 演练**：当前只有 2 次脚本化诊断，不能替代正式链路。

### 是否建议送 Codex

**不建议现在以 PASS 预期送 Codex 终审。**  
至少 N1–N4 应修掉；若 N6/N8 仍保留，只能作为“已知残余、禁止正式分数”的 CONCERN，不能作为 G1 PASS。  
若时间紧迫，可以送 Codex 但预期 verdict 仍可能为 FAIL；送审前应把 `BYOK_JUDGE_V2_FIXES.md` 中已声称修复但实际未修复的 bool 项纠正。
