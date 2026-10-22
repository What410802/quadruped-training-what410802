<!-- BYOK 二次预审（provisional） -->
# BYOK Judge V2.1 Verification（DeepSeek v4.1-flash，same-model-provisional）

> **verdict（原始输出）**：FAIL（第一次预审 11 个 blocker 中 7 个仍 STILL-BROKEN，另有新问题）
> **后端**：`comp_review.py` / DeepSeek relay / `deepseek-v4.1-flash`；同模型自审 → 不能 acquit G1
> **meta**：`BYOK_JUDGE_V2_VERIFY.json`；**trace**：`comp/traces/comp-review/2026-10-22_run02`
> 以下为 reviewer 原始输出，executor 未改写。修复映射见 `BYOK_JUDGE_V2_FIXES.md` §"二次预审后修复"。

verdict: **FAIL**  
（预审建议：不能进入 G1 终审；第一次预审 11 个 blocker 中仍有 7 个未真正清零，且修复引入了暂停死锁、soft-reset 残留、证据链误算等新问题。）

> 说明：给定材料没有源码行号，以下用函数名/代码片段定位。

## 第一次预审 11 个 blocker 逐条核对

| # | 结论 | 代码依据 |
|---|---|---|
| 1 | **PASS** | `_Obstacle.update` 中新增 `if touched and not ground_feet: self.supported = True`，`ground_fail` 仅在 `self.supported and len(ground_feet) >= 2` 时触发。进场前未接触障碍时 `touched=False`，不会误杀。`test_approach_ground_is_not_failure` 覆盖。**残余**：soft-reset 分支未清 `supported/prev_touched/in_zone_samples`，可能造成后续误杀，见新问题。 |
| 2 | **STILL-BROKEN** | `HighWall._on_sample` 只要求 `WALL_CROSS_Y` 穿越，并在 `if self._last_z >= WALL_CLIMB_Z or "wall" in tags` 时记 `cross_valid`。`WALL_CLIMB_Z=0.55` 接近站立高度；runner `_sample_judge` 对 `wall` tag 不检查法向，脚侧面擦墙即可满足 `"wall" in tags`。没有要求穿越时 x 在真实墙宽内、没有要求支撑/抬升到墙顶、没有排除地面侧擦墙过平面。 |
| 3 | **PASS** | `comp_part1_geom_tags.GEOM_TAGS` 已补 `bridge_blocks_0..4`、`bridge_bands_0..2` 到 `{"bridge"}`，并补平台 tag。`test_scene_geom_tags_complete` 检查真实 XML 前缀覆盖。**残余**：共享平台 `bridge_platform_r -> {platform_right, platform_high}` 仍可能造成 zone 重叠噪声。 |
| 4 | **STILL-BROKEN** | `TStairs._on_sample` 只把 `step:<arm>:<level>` 塞入集合；`_complete_arms()` 只要求出现 `{1,2,3}`，不要求顺序、不要求从地面返回、不要求两臂才 success。`_check_exit` 只检查 `top` 和 `_complete_arms()` 非空，因此单臂 + top 仍 `status=success`、score=75/50；`ground_after_top` 被记录但从未参与判定。`_Obstacle.update` 对 `success` 永久锁定，部分成功后不能重试补第二臂。 |
| 5 | **STILL-BROKEN** | 双向与“终点最后”有改进，但半径仍不一致：judge 用 `SLALOM_RADIUS_M=0.5`、`SLALOM_POST_RADIUS_M=0.35`；场景 XML 圆形显示 geom 仍是 `size="0.1 0.001"`，柱底 `size="0.05 0.02"`、柱杆 `size="0.015 0.33"`。`corner_after in (2,3)` 还允许 A 方向在 post1 后提前触发 corner。 |
| 6 | **STILL-BROKEN** | `HeightBar._on_sample` 的 `bar_base` 是进入 zone 后第一次观测值；进门前杆已掉不会检测。`_fail("bar_dropped")` 会 `_reset_evidence()`，离开后重入会把当前低杆当新 `bar_base`，可能重试成功。`Part1JudgeV2.bar_dropped` 只是 report 字段，`HeightBar._check_exit` 不使用它；`_Obstacle.update` 对 `success` 提前 return，成功后掉杆/出门前掉杆不会撤销。穿越判定也只检查当前采样 x 在门洞内，不检查整机连续包络。 |
| 7 | **PASS** | `_fail` 把状态设回 `pending`、`armed=False`；离开 zone 后 `if not inside: self.armed=True`，再次进入可重试。`_Obstacle.update` 对 `success/skipped` 提前 return，符合“成功后锁定”。**注意**：该锁定与 #6 的“成功后掉杆撤销”冲突。 |
| 8 | **PASS** | `Part1JudgeV2.update` 在全部障碍 `status=="success"` 且 `score >= per_obstacle_score` 后才置 `all_full_done`；`return_after_full` 只在之后进入 start area 时置真。`Part1Course.end_attempt` 使用 `judge.report()["return_bonus"]`，T 台阶 75 分不会触发全满分返回奖励。**残余**：`comp_score` 不校验返回事件，只信 summary 的 `return_to_start`。 |
| 9 | **STILL-BROKEN** | `Part2JudgeV2._cond`：`platform/stairs/slope/plum` 主要是 `z >= top_z+0.38`、`x>=goal`、`_lateral_ok(y)`、`not ground_feet`，没有要求脚底接触目标顶面/楼梯顶/坡面/梅花桩。`wall` 分支甚至不检查 `ground_feet`。低难度 10/15/20 cm 仍可能用腾空/小跑/站立高度或侧向接触伪成功。 |
| 10 | **STILL-BROKEN** | `_cond` 的 `_lateral_ok(y)` 只在最终成功条件使用。`update` 中 `wall_crossed` 只在 x 跨 `wall_x` 时记录，不检查 y 是否在 lane；`max_z_near` 也只按 `abs(x-wall_x)<=0.8` 记录，不检查 y。`gap` 分支只有 `x>=goal_x_min and z>=min_z and _lateral_ok(y)`，没有跨越 gap 区间、没有 `not ground_feet`，可以绕到 y 外侧跨 x，再回 lane 在右侧地面成功。`plum` 也没有目标接触证据。 |
| 11 | **STILL-BROKEN** | `run_part1_course.py` 虽然调用 `Part1Course`，但 `main` 每次 attempt 都新建 `CoursePolicyRunner` 和 `run_attempt()` 内部新建 `Part1Course`，不是同一个 session 的 3 次 attempt 账本；runner 本身不限 3 次，也不汇总 best score/fastest time。`comp_import_course_diag.py` 用 `best_idx+1` 去匹配 `attempt_results`，但每个独立 course 的 `attempt` 都是 1，第二次及以后为 best 时 `best_attempt_rec={}`，返回奖励会丢。`manifest.scenes.part2` 还写成 part1 scene 且 sha 为空。 |

## 新问题清单

### Blocker / High

1. **Part2 gap 仍可明显绕行/地面成功**  
   - 文件/函数：`comp_part2_judge.py::Part2JudgeV2._cond` 的 `kind=="gap"`。  
   - 利用路径：从 y 外侧绕过 trench，回到 lane 内，站在 `ground_right` 上；只要 `x>=goal_x_min`、`z>=min_z`、`_lateral_ok(y)`，即使 `ground_feet` 非空也成功。  
   - 建议：要求跨越 `gap_x±width/2` 的连续事件、跨越时在 lane 内、跨越期间不得有地面足，或脚接触右侧地面必须发生在跨越事件之后。

2. **Part2 wall 穿越不在 lane 内也计数；低墙可站立高度伪成功**  
   - 文件/函数：`Part2JudgeV2.update` 的 `wall_crossed`、`max_z_near`；`_cond` 的 `kind=="wall"`。  
   - 利用路径：从墙端 y 外侧跨 `wall_x`，再回到 lane；`wall_crossed` 已置真，`max_z_near` 也记录，最终 `x>=goal_x_min`、`_lateral_ok(y)` 成功。10–30 cm 墙阈值 `max(wall_h+0.10,0.55)` 接近站立高度，且不检查 `ground_feet`。  
   - 建议：记录 lane 内 wall 平面穿越；要求穿越时支撑/抬升或接触墙面；低墙也要排除地面站立。

3. **HeightBar 掉杆状态可被失败重试洗掉；预掉落/成功后掉落未全局失效**  
   - 文件/函数：`HeightBar._on_sample`、`HeightBar._check_exit`、`_Obstacle._fail`、`Part1JudgeV2.update/report`。  
   - 利用路径：进门前杆已低 -> 第一次观测即为低 `bar_base`；掉杆失败后 `_reset_evidence()`，离开重入后低杆成为新基准；`Part1JudgeV2.bar_dropped` 不参与 obstacle 成功判定；成功后 `_Obstacle.update` 直接 return，出门前再掉杆不撤销。  
   - 建议：attempt 级绝对初始杆高，不从失败后重置；`bar_dropped` 与 HeightBar 成功强绑定；成功后到离开 zone 前仍采样/撤销。

4. **soft-reset 未清 `supported/prev_touched/in_zone_samples`，会产生误杀与新状态污染**  
   - 文件/函数：`_Obstacle.update` 的 `elif prev_in_zone and status=="running"` 中 `else` 软重置分支。  
   - 代码：`self.result.status="pending"; self._reset_evidence(); self.armed=True`，但没有清 `supported`、`prev_touched`、`in_zone_samples`。  
   - 利用/误伤：一次合法擦碰后软退出，`supported=True` 残留；再次进场时两脚在地面就立刻 `two_feet_ground`，即使尚未接触障碍。`in_zone_samples` 累计还会改变 `>=5` 的非法入口判定。  
   - 建议：软重置/重新武装时清完整单次进入状态，而不是只清 evidence。

5. **`run_part1_course.py` 暂停循环会死锁，未来 resume 事件永远不会被处理**  
   - 文件/函数：`run_attempt` 的 `while True` paused 分支、`apply_events` 的 `events[idx]["t"] <= t`。  
   - 问题：暂停后不再 `step_policy`，`s["t"]` 冻结；但 resume 事件通常在未来时间，`apply_events` 只处理 `<= t`，于是 `course.paused` 永远为真，循环不推进时间。  
   - 证据：course 自检只测 `pause/resume` 方法，不测 runner 的事件循环。  
   - 建议：暂停时仍需按 wall time 处理事件，或把 pause/resume 作为外部状态机而非在冻结仿真循环里等待未来事件。

6. **正式整场 runner/importer 仍不是单一 session 账本**  
   - 文件/函数：`run_part1_course.py::main/run_attempt`、`comp_import_course_diag.py`。  
   - 问题：每次 attempt 新 `Part1Course`，3 次预算、恢复不消耗、best score/fastest active time 没有由一个 session 统一产出；importer 又用 `best_idx+1` 匹配每个独立 course 的 `attempt=1`，第二次/第三次为 best 时返回奖励丢失。  
   - 建议：一次运行只建一个 `Part1Course`，attempt 事件在同一个 manager 里累计；importer 从该 ledger 复算，不按“第几个 course”猜 attempt 编号。

### Major

7. **T 台阶单臂 partial 仍锁死 success，不能重试补全；且不校验返回地面/逐级顺序**  
   - 文件/函数：`TStairs._on_sample/_score_for/_check_exit`、`_Obstacle.update`。  
   - 问题：单臂完整 + top 即 success，score 75/50；随后 `_Obstacle.update` 对 success 永久 return，同一 attempt 内再做第二臂也不会改分；`ground_after_top` 未用；`{1,2,3}` 只查集合，不查 1→2→3 顺序。  
   - 建议：把 partial 与 full 分成不同状态；partial 不应永久锁死，或规则明确 partial 即结束；full 要求两臂完整 + 返回地面。

8. **Slalom 半径仍与场景不一致，post 半径过大，A 方向 corner 可提前**  
   - 文件/函数：`Slalom._on_sample/_check_immediate/_check_exit`、`SLALOM_*` 常量、`part1_eval_scene_v2.xml`。  
   - 问题：场景显示圆半径 0.1，judge 用 0.5；柱底半径 0.05/杆 0.015，judge post 半径 0.35；`corner_after in (2,3)` 对 A 方向允许 post1 后提前触发。  
   - 建议：半径从 scene/config 读取；post 半径按实体尺寸；A/B 方向分别严格定义 corner 应在第 3/第 2 杆后。

9. **`comp_import_diagnostic.py` 仍会把 success+score=0 提升为满分，并丢重复 trial**  
   - 文件/函数：`comp_import_diagnostic.py` 的 `score = int(t["judge"].get("score") or per_obstacle_score)`、`per_task.setdefault(task, trial)`。  
   - 问题：`0` 被 `or` 当缺失值；同一障碍多 trial 只保留首条。虽然当前产物标 diagnostic，但这是第一次预审 #21 的原样残留。  
   - 建议：`score is None` 才回退；保留全部 trial，best/partial 按 contract 重算。

10. **`comp_score.py` 强校验仍不足：不校验场景/judge hash、不校验 trial judge score、不校验返回事件、attempts 不一致只 warning**  
   - 文件/函数：`validate_manifest`、`validate_summary`、`validate_trials`。  
   - 问题：`return_to_start` 只信 summary；Part1 evidence 只查 trial `status=="success"`，不查 trial `judge.score` 与 summary score 一致；Part2 只查 best value 有成功 trial，不查 trial score；`attempts_used` 与 trials 条数不一致只 `_warn`，正式行也可能放过；scenes/judge hash 不校验。  
   - 建议：返回奖励必须有 trial/event 证据；summary 分数从 trials+contract 全量复算；场景/judge/route hash 与 manifest 对齐；attempts 不一致对正式行升 error。

11. **Part2 “每项 4 次”仍没有 category 级 scheduler**  
   - 文件/函数：`run_part2_judged_eval.py` 对每个 level 循环 `--attempts`；`comp_import_part2_diag.py` 用 `len(cat_trials)` 当 `attempts_used`。  
   - 问题：high_platform 4 个 level × 1 次会写成 `attempts_used=4`，看似 4 次，实际是 4 个不同难度；若 `--attempts 4` 则变成 16 trial，importer 汇总成 16。  
   - 建议：category 级挑战队列，最多 4 次，记录 level 序列；import 时校验 trials 的 category attempt 数，而不是 level trial 数。

12. **conformance 有“测试自身掩盖问题”**  
   - `test_t_stairs_full_partial_and_history` 的 full/partial 路径都没有 `ground_feet`，`ground_after_top` 未触发却期望 success，因此测不出“必须返回地面”。  
   - `test_height_bar_touch_drop_and_gate` 没测进门前预掉落、失败重试后低杆、成功后出门前掉落。  
   - `test_high_wall_sideways_climb_and_bypass` 没测“地面 + 墙面侧擦 tag 过平面”。  
   - `test_spoof_exit_positions` 多数只有 1 个 zone 内样本，走 soft-reset，不是真正 failure。  
   - Part2 `run_self_test` 的 `_feed` 不传 `ground_feet`，所有 `not ground_feet` 分支天然为真；没测地面站立/腾空/绕行。  
   - `test_scene_geom_tags_complete` 只查前缀存在，不查 high_wall/height_bar/slalom 半径和 T 顺序语义。

### Minor

13. **bool 曲线仍任意非零给满分**  
   - `comp_part2_judge.curve_points_floor` 与 `comp_score.curve_points` 都是 `if unit=="bool": full if value not in (0.0,)`；`-1`、`0.5` 仍给满分。  
14. **`run_part1_judged_rollout_v2.py` 的 `total_score` 仍加总整份 judge report**  
   - `total = sum(r["judge"]["score"] for r in results)`，不是只取目标状态；诊断总分仍可能被非目标任务污染。

## 证据链/产物检查结论

- `flat-ft-2500-part1-diag-v2`：scene hash 与当前 `part1_eval_scene_v2.xml` 一致；judge version 包含 `comp_part1_judge.py` + `comp_part1_geom_tags.py` 前缀 hash；manifest 标 `diagnostic=true`；summary 的 8 条失败可由 trials 复算。  
  **但**：`operator` 仍写 `scripted:run_part1_judged_rollout.py`，不是 V2 runner；`attempts_used=8` 与正式 3 次协议冲突，仅因 diagnostic 被放过；summary evidence 对失败项也填 trial，虽不构成假成功，但语义混乱。
- `flat-ft-2500-part2-diag-v2`：level 场景 hash 已记录，summary 全 0 可由 trials 复算，diagnostic 标注正确。  
  **但**：`attempts_used` 是 level trial 数，不是 category 4 次挑战数；无法证明每项 4 次协议。
- `flat-ft-2500-part1-course-diag`：scene/route hash 与当前文件一致，diagnostic 标注正确，trials 全 fail 与 summary 一致。  
  **但**：manifest `scenes.part2.file` 指向 part1 scene 且 sha 空；course 只跑 1 attempt，未验证 3 次、恢复不消耗、best/fastest 的 runner 闭环；importer 的 best attempt 匹配有上述 #11 缺陷。
- `comp_score.py`：覆盖了部分分白名单、Part2 curve floor、部分 attempts 预算；**未覆盖**返回奖励事件证据、场景/judge hash 对齐、trial 分数与 summary 分数一致性、Part2 trial score、正式 attempts 不一致升级为 error。

## 给 Codex G1 终审的“必须重点验证项”

1. **高墙是否只靠地面侧擦墙 tag 就能过 `WALL_CROSS_Y`**：检查 `HighWall._on_sample` 的 `or "wall" in tags` 和 runner 对 wall 法向的无条件放行。
2. **限高杆进门前预掉落、掉杆失败后重试、成功后出门前掉落**：检查 `HeightBar.bar_base` 是否会被 `_fail` 重置、`Part1JudgeV2.bar_dropped` 是否真正影响成功。
3. **T 台阶单臂 partial 是否永久锁 success**：检查 `_Obstacle.update` 对 success 的 early return，以及 `TStairs._check_exit` 是否只要求非空 complete arm；验证 `ground_after_top` 是否被使用。
4. **绕杆半径是否仍用 0.5/0.35 而场景显示 0.1/0.05**：检查 `SLALOM_*` 常量与 XML `size`；验证 A 方向 corner 是否可在 post1 后提前触发。
5. **Part2 gap 是否可在 y 外侧绕过 trench、回 lane 站在 ground_right 成功**：检查 `_cond` gap 分支是否无 crossing、无 `not ground_feet`。
6. **Part2 wall 是否可在 y 外侧跨 `wall_x` 再回 lane 成功**：检查 `wall_crossed/max_z_near` 是否未绑定 lane 内穿越。
7. **Part2 platform/stairs 是否只靠腾空/小跑 + `not ground_feet` 成功**：检查 `_cond` 是否没有目标顶面接触/支撑证据。
8. **`run_part1_course.py` 暂停事件是否死锁**：用 pause@t、resume@t+5 的脚本事件跑一次；当前冻结 `s["t"]` 且只处理 `<=t` 事件，未来 resume 不会被处理。
9. **正式 3 次 attempt 是否由同一个 `Part1Course` ledger 产出**：当前 runner 每次 attempt 新建 course；importer 的 `best_idx+1` 与每个 course 的 `attempt=1` 不匹配，第二次/第三次 best 的返回奖励会丢。
10. **`comp_score.py` 是否仍信任 summary 的 `return_to_start`**：构造 trials 全 success、summary `return_to_start=true` 但无返回事件，看是否仍 valid。
11. **Part2 每 category 4 次是否真的在 runner/importer 中实现**：当前 `--attempts` 是 per level，不是 category scheduler；summary `attempts_used` 会把 4 个不同 level 写成 4 次。
12. **conformance 是否仍用“无 ground_feet”的合成路径掩盖 T 台阶/Part2 地面伪成功**：重点看 `test_t_stairs_*`、`comp_part2_judge.run_self_test` 的 `_feed`。

**结论：FAIL。** 当前仍存在多个可被利用的假成功路径（height_bar 预掉落/重试洗掉、high_wall 侧擦墙、Part2 gap/wall 绕行、Part2 低难度无接触、T 台阶 partial 锁死），以及正式整场协议/证据链未闭环的问题。建议在 G1 前至少清零 #2、#4、#5、#6、#9、#10、#11 及新问题 1–6。
