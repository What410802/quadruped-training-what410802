verdict：**CONCERN**

## 1. HighWall / T 台阶逐项

**HighWall x 段约束：逻辑 PASS；新增 conformance 用例 STILL-BROKEN（测试未真正打到修复点）。**

- `HighWall._on_sample` 已使用 `WALL_X_MIN=1.30/WALL_X_MAX=2.30`，要求穿越时 `prev_x` 与当前 `x` 都在墙段内才增加 `cross_valid`；抬升但 x 越界只记 `outside_x_cross`。
- `HighWall._check_exit` 只认 `cross_valid >= 1`，所以 Pro 给出的 `x=1.25, z≥0.60` 路径不会成功。墙内合法抬升（如 x=1.8）仍可成功。就 judge 语义看，**“墙外侧抬高穿越”假成功已被代码关闭**。
- 但 `comp_judge_conformance.test_high_wall_sideways_climb_and_bypass` 新增的 `outside_x` 用例用的是 `x=2.7`，而 `ZONES["high_wall"]` 的 x 范围是 `(1.25, 2.35)`。因此该路径根本没进入 high_wall zone，也不会执行 `HighWall._on_sample` 的越界分支；就算没有本次修复，它也会“非 success”。**测试用例坐标放错，不能证明 blocker 已修**。应改为 zone 内、墙段外，例如 `x=1.25/1.29` 或 `x=2.31/2.34`。

**T 台阶：PASS（按当前落地口径）。**

- `Part1JudgeV2.__init__` 默认 `partial_up=50.0, partial_down=33.0`。
- `TStairs._score_for` 对唯一完整臂 `arm=="s"` 给 `partial_up=50`，对 `n/e` 给 `partial_down=33`。
- conformance 已覆盖：s 臂单臂=50，n 臂单臂=33，e 臂单臂=33；两臂完整=100。
- 残余：`TStairs` 自身构造默认值和 docstring 仍写 75/50，与 `Part1JudgeV2` 传入口径不一致；不影响当前评测，但属于无问题验收应清理的小项。另“上/下”与 s/n/e 的书面映射仍应留痕。

## 2. N1–N4 / P1–P4 与历史 PASS

静态检查未发现 HighWall/T 修复导致 N1–N4/P1–P4 回归：

- N1：`run_part1_course.CoursePolicyRunner`/`run_attempt` 每 4 个物理步均 `feed()`，逐物理步喂 judge。
- N2：`comp_import_course_diag` 用每次 `attempt_result` 选 best，而非全局 summary。
- N3：`Part1Course.summary` 与 `AttemptManager.summary` 均按最高分尝试内最快 duration。
- N4：`comp_score.curve_points` 与 `comp_part2_judge.curve_points_floor` 的 bool 只认 `value == 1.0`。
- P1：`StableStopTracker` 使用 `model.opt.timestep`。
- P2：暂停循环只推进 operator 事件/超时，不重复 `course.update`。
- P3：`validate_external_evidence` 已接入 `score_one`；但注意 Pro V12 §5.3 指出的两个正式链路缺口仍在（见下）。
- P4：`comp_part1_geom_tags.is_ground_geom()` 已覆盖 plane/floor/trench_bottom/level_floor/ramp 等。

四份 eval 产物：

- official Part2 的 24 条 trial、每 category `attempts_used=4` 与 summary/manifest 一致；
- part2-diag-v2 的 20 条 trial 与 4/4/4/4/3/1 一致；
- course-diag 的 3 attempt × 8 障碍 trial 与 summary 可复算；
- HASHES 中已列对象的 hash 与产物文件头一致。

但 **HASHES 覆盖不完整**：`flat-ft-2500-part1-diag-v2/manifest.json` 引用 `assets/terrain/part2/ability_field/part2_ability_field.xml`，`config/part2-levels.json` 及 part2 manifest 引用 `assets/terrain/part2/part2_plum_eval_scene.xml`，而 `comp_audit_hashes.OBJECTS` 和 `HASHES.json` 均未纳入这两个对象。当前 60 个已列对象可复算，但不能说 HASHES 已覆盖全部被引用场景。按 Pro 的最小修复要求，这两个场景应补入 HASHES；补齐后对象数应增加，而不是维持 60。

## 3. 新问题 / 无问题验收必须清理项

未发现新的 HighWall/T 分数 blocker，但存在以下“无问题验收必须清理项”：

1. `comp_judge_conformance.test_high_wall_sideways_climb_and_bypass` 的墙外抬升用例 `x=2.7` 不在 high_wall zone 内，未测试 `outside_x_cross` 分支。  
2. `comp_audit_hashes.OBJECTS` / `HASHES.json` 缺 `part2_ability_field.xml` 与 `part2_plum_eval_scene.xml`。  
3. `comp_score.validate_external_evidence` 中 Part1 final_time 复算的 `full` 初始为 True，未检查该 attempt 是否覆盖全部 Part1 障碍；`validate_summary` 对 Part1 `attempts_used` 与 distinct attempt 仍主要是 warning。这是 Pro V12 §5.3 已指出的正式链路缺口。  
4. `TStairs` 默认参数/docstring 的 75/50 与 `Part1JudgeV2` 的 50/33 不一致，属 minor 清理。

## 4. 是否满足进入 Codex 前 flash 验收（无问题）

**no。**

最小修复：

- 将 HighWall 墙外抬升 conformance 用例改到 zone 内、墙段外（如 x=1.25/1.29 或 2.31/2.34），确认 `cross_valid` 不增加且最终非 success。
- 将 `part2_ability_field.xml`、`part2_plum_eval_scene.xml` 加入 `comp_audit_hashes.OBJECTS` 并重新生成 HASHES；同步更新对象数说明。
- 在 `comp_score` 正式链路补充 Part1 distinct attempt 对账，并要求复算 best/final_time 的 attempt 覆盖全部 Part1 障碍。
- 顺手把 `TStairs` 默认值/docstring 调整为 50/33，避免后续误用。

修复后需重跑 conformance、`comp_score --self-test`、刷新 HASHES，再做 flash 复验。

**修复后进入 G1 仍必写的残余**：砂砾坑真实几何未 recut；Part2 官方能力场逐档交叉核对未完成；正式手动 3 次整场演练未在真实赛程完成；soft-reset 阈值与相邻 zone 重叠仍为启发式；T 台阶“上/下↔三臂”建议书面确认；Part2 official 重复最高档统计意义有限；跨 attempt 模拟器时间重置后事件时间线不可全局排序。
