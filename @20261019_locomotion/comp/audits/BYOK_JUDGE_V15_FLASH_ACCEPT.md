verdict：**PASS**

## 1. 四项逐项

① **HighWall 墙外抬升 conformance 用例：PASS。**  
`comp_judge_conformance.py::test_high_wall_sideways_climb_and_bypass` 的 `outside_x` 已改为 `x=2.33`。`ZONES["high_wall"]` 的 x 范围是 `(1.25, 2.35)`，墙实际 x 段是 `[1.30, 2.30]`，所以 `x=2.33` 确实在 zone 内、墙段外。轨迹会进入 zone，并在 `y=-7.0` 穿越时进入 `HighWall._on_sample`；因 `raised=True` 且 `within_x=False`，只增加 `outside_x_cross`，不增加 `cross_valid`。`HighWall._check_exit` 只认 `cross_valid >= 1`，因此最终非 success。该用例真正打到了修复分支。墙内合法抬升穿越仍可 success，行为正确。  
T 台阶：`TStairs.__init__` 默认 `partial_up=50.0/partial_down=33.0`，`_score_for` 对 `s` 给 50、对 `n/e` 给 33，两臂完整给 100；`Part1JudgeV2.__init__` 默认同样为 50/33。conformance 已覆盖 s=50、n=33、e=33、两臂=100、缺级失败。**PASS。**

② **HASHES 缺 `part2_ability_field.xml`、`part2_plum_eval_scene.xml`：PASS。**  
`comp_audit_hashes.py::main` 的 extra scenes 循环已纳入这两个文件；`HASHES.json` 中已有：
- `scene_part2_ability_field` = `f0b74bbebe5c5ee3de643a2ce8c369f9c9249be77e2c4d85618eab6cf1ad7823`
- `scene_part2_plum_eval_scene` = `8d44f16887899ff916261dbe7feca536e75beb789a9d146a34d8720a668910fc`

对象数 62 可复算：26 个 `OBJECTS` + 19 个 level XML + 12 个 eval 产物（4 目录 × manifest/trials/summary）+ 2 个额外场景 + 3 个 evidence drill = **62**。两个新增场景 hash 与文件头一致。

③ **comp_score 的 Part1 attempts_used/distinct attempt 对账与 final_time 覆盖校验：PASS。**  
`comp_score.py::validate_external_evidence` 已：
- 从 trials 抽取 Part1 distinct attempts，正式 manifest 下 `attempts_used` 不一致报 error，diagnostic 下报 warning；
- 复算 final_time 时构造 `by_attempt`，并用 `rec["seen"] != expected_obs` 要求该 attempt 覆盖全部 Part1 障碍，否则 `full=False`；
- 在 `score_one` 中已调用 `validate_external_evidence`。

④ **TStairs 默认值与 docstring 75/50：PASS。**  
`comp_part1_judge.py::TStairs.__init__` 已为 `partial_up=50.0, partial_down=33.0`，docstring 已写 `up/s=50, down/n,e=33`；`Part1JudgeV2` 传入默认值也是 50/33。与 Q2=×2/3 口径一致。

## 2. 历史 PASS 项与证据链回归

未发现 N1–N4 / P1–P4 回归：

- **N1**：`run_part1_course.py::run_attempt` 每 4 个物理步均 `feed()`，逐物理步喂 judge。
- **N2**：`comp_import_course_diag.py` 依据每次 `attempt_result` 选 best，而非全局 summary。
- **N3**：`Part1Course.summary` 与 `AttemptManager.summary` 均为最高分尝试内取最快 duration。
- **N4**：`comp_score.curve_points` 与 `comp_part2_judge.curve_points_floor` 的 bool 只认 `value == 1.0`。
- **P1**：`StableStopTracker` 使用 `model.opt.timestep` 的真实物理 dt。
- **P2**：暂停循环只推进 operator 事件/超时，不重复 `course.update`。
- **P3**：`validate_external_evidence` 已接入 `score_one`，并校验外部 hash、Part2 合法档位、Part1 final_time。
- **P4**：`comp_part1_geom_tags.is_ground_geom()` 覆盖 plane/floor/trench_bottom/level_floor/ramp 等，两个 Part1 runner 共用。

四份产物与 HASHES 一致可复算：

- `flat-ft-2500-part1-diag-v2`：manifest/trials/summary 的 sha256 分别匹配 HASHES 中 `4476…/1cf4…/bc12…`。
- `flat-ft-2500-part2-diag-v2`：匹配 `3dcc…/2e21…/13a9…`。
- `flat-ft-2500-part2-official-diag`：匹配 `ca98…/fa76…/e2b2…`；24 条 trial，每 category `attempts_used=4`。
- `flat-ft-2500-part1-course-diag`：匹配 `604c…/f5fb…/74ca…`；3 attempt × 8 障碍 trial 可对账。
- `HASHES.json` 62 objects 与上述产物、两个额外场景、3 份 evidence drill 均一致。

## 3. 新问题 / 必须清理项

未发现 blocker；未发现“无问题”验收必须清理项。  
仅有非阻塞备注（不影响本轮判定）：`comp_part1_judge.py::HighWall` 中 `WALL_CLIMB_Z = 0.55` 未被实际使用，实际阈值是字面量 `0.60`；`comp/CONTRACT.md` §6 资产表仍列 V1 场景/旧 judge，机器契约与 HASHES 已按 V2 使用，建议 G1 文档清理时顺手更新。

## 4. 是否满足进入 Codex 前 flash 验收（无问题）

**yes。**

G1 必写残余：

- 砂砾坑真实几何未 recut，当前为凸起盒代理；
- Part2 官方能力场逐档交叉核对未完成；
- Part1 soft-reset 阈值与相邻 zone 重叠仍为启发式；
- 正式手动 3 次整场演练未在真实赛程完成；
- T 台阶“上/下 ↔ s/n/e”建议书面确认，尽管 docstring 已留痕；
- Part2 official 重复最高档在确定性策略下统计意义有限；
- 跨 attempt 模拟器时间重置后事件时间线不可全局排序；
- Part1 单障碍诊断 importer 的 per-obstacle 汇总口径仅用于诊断，正式仍以 course importer 为准。
