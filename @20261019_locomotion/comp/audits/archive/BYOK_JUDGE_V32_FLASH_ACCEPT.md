verdict：**CONCERN**。  
没有发现足以判 FAIL 的 scorer blocker；砂砾坑与限高杆的核心判罚实现和 13 组 conformance 基本一致。但 C1/诊断证据链存在新的不一致：**单障碍 gravel 诊断起点仍是南侧长边进入**，而 `README_C1.md` 仍写“南短边进/西侧长边横穿”，与当前 L 形几何、`LABELS_PROVENANCE.md` 和 `records.jsonl` 不一致。应在 G1 前修正或写入残余。  
（artifacts 未带行号，以下按文件、函数、字段定位。）

---

## 1. 砂砾碎木坑：实现满足核心契约，但诊断/文档证据链有问题

**几何一致性：通过。**  
`assets/terrain/part1/part1_eval_scene_v2.xml` 中：
- `gravel_pit_a`：x∈[4.3361,5.3361], y∈[-13.0,-12.0]；
- `gravel_pit_b`：x∈[5.3361,6.3361], y∈[-13.0,-11.0]；

并集是 L 形，合法 1 m 短边应为：
- 外西边：x=4.3361, y∈[-13.0,-12.0]；
- 外北边：y=-11.0, x∈[5.3361,6.3361]。

`comp_part1_judge.py::GravelPit` 的 `GRAVEL_X_LO/MID/HI`、`GRAVEL_Y_LO/MID/HI`、`GRAVEL_SHORT_EDGES` 与上述 XML 一致；`GRAVEL_BOUNDARY` 明确把 `south_long`、`east_long`、`notch_h`、`notch_v` 与两个 `short` 边区分。

**进出判定：通过。**  
`GravelPit._track_footprint()` 用 `_crossed_edges()` 和 `_seg_cross()` 记录实际进入/离开边；`GravelPit._check_exit()` 要求：
- `entry_edge`、`exit_edge` 均存在；
- `{entry, exit} == {"west", "north"}`；
- `gravel_hits >= 3`；
- 无 `illegal_entry` / `illegal_exit`。

`comp_judge_conformance.py::test_gravel_short_edges_and_long_edge` 覆盖了：
- west short 进、north short 出的合法 L 路径 success；
- south long、east long 进入/退出 fail；
- 坑中段 2 足触地 fail；
- 合法离开后落地不判罚。

**实现层面的 caveat：**  
`GravelPit` 使用 base 中心轨迹判断进入/离开，不是全足端 footprint；精确擦过角点或“身体中心已过、足仍未过”时可能有代理误差。当前 conformance 不覆盖“恰好在 L 角点相交”的退化情形。不是 blocker，但应作为残余。

**证据链新问题：**  
`run_part1_judged_rollout_v2.py::TASKS["gravel_pit"]` 当前是：
- start `(5.0, -13.4, 0.55)`，yaw `π/2`，command `+vx` 沿 +y。

`x=5.0` 穿过的是 y=-13 的**南侧 2 m 长边**，不是 1 m 短边。`records.jsonl` cal-003/011/019/027 的 note 写“short-edge approach along +y”，这是错误的。实际这些真实 rollout 即使到达坑体，也应是 `illegal_entry_side`；当前因策略未走到坑内而 timeout。  
因此：**judge 对合法 L 路径的实现通过，但 C1 的真实 gravel rollout 起点不是合法短边起点。**

---

## 2. 限高杆：实现确实要求从杆下方穿过，核心行为通过

`comp_part1_judge.py::HeightBar`：

- `_pre_sample()` 用 `bar_base_seen - bar_z > BAR_DROP_THRESHOLD_M` 检测落杆；阈值 0.05 m。
- `_on_sample()` 只在通过 y=-9 且在 `BAR_OPENING_X=(5.2,6.2)` 内时计入 `cross_valid`，并记录 `cross_max_z` 和 `cross_bar_z`。
- `_check_exit()` 要求：
  - 入口为 `ymin/ymax`；
  - 出口为对侧；
  - `cross_valid >= 1`；
  - 未见 `bar_dropped_seen`；
  - `cross_z <= cross_bar`，否则 `not_under_bar`。

`test_height_bar_touch_drop_and_gate` 覆盖：
- 低姿态 z=0.25、bar_z=0.325：success；
- 站立高度 z=0.45：`not_under_bar`；
- 落杆：fail；
- 预进入已落杆：不能 success；
- outside-then-lateral 骗分：不能 success。

**误判风险：**  
under-bar 检查使用 base z 代理，不是全身/背部离地间隙；`cross_z <= cross_bar` 以杆中心高度比较，理论上可能比“全身完整低于杆底”宽松。该风险已在 `G1_SELFCHECK.md` 标为 base z 代理残余，不是当前 blocker。

---

## 3. route：`config/part1-route.json` gravel 段合法；单障碍诊断路线不合法

`config/part1-route.json` gravel 段：
- `to_gravel`: `(3.6,-12.5)`；
- `cross_gravel_west`: `(5.8,-12.5)`；
- `cross_gravel_north`: `(5.8,-10.6)`。

该路径：
- 从 x<4.336 进入，穿过 x=4.336, y=-12.5，即 **west short edge**；
- 再从 y<-11 穿到 y>-11，x=5.8，即 **north short edge**。

因此 `config/part1-route.json` 的 gravel 段是合法 L 路径，与 `GravelPit` 语义一致。

但“course/诊断路线”要分开看：
- **整场 course 诊断路线** `config/part1-route.json` 的 gravel 段合法；
- **单障碍诊断** `run_part1_judged_rollout_v2.py::TASKS["gravel_pit"]` 不合法，起点 `(5.0,-13.4)` 沿 +y 是南侧长边进入。

实际 `comp/eval/flat-ft-2500-part1-course-diag/` 中 gravel 仍是 `route_complete`，height_bar 是 `wrong_exit_side`，说明这是策略执行失败/路线未跑通，不是 judge success 证据。课程诊断路线本身不能作为正式成功证据。

---

## 4. C1 标定：标签布尔层一致，但文档/证据链有新的不一致

**数量与行级一致性：**
- `records.jsonl`：92 条；
- `labels_template.csv`：92 行；
- `C1_CALIBRATION_REPORT.md`：loaded 92 / labeled 92 / compared 92 / agree 92；
- `LABELS_PROVENANCE.md`：56 条真实 rollout + 28 rulecard + 8 session，来源限制写得较诚实。

按 success/fail 布尔层逐条看，`labels_template.csv` 与 `records.jsonl` 的 judge status 没有发现 true/false 冲突：part1_obstacle、part2_level 全部 fail 对应 human false；rulecard 的 success/fail 与 human_success 对应；session 标 `human_protocol_ok=true`。

**但要注意 C1 “100%” 的口径很窄：**
- 56 条真实 rollout 是用户盲标；
- 28 条 rulecard 与 8 条 session 是“用户确认语义 + executor 补全”，`LABELS_PROVENANCE.md` 已明确承认非盲标；
- session_state 的 8/8 更像协议语义确认，不是 judge-human 独立盲测。

**新的文档不一致：**
1. `README_C1.md` 写砂砾坑 success “从南短边进、北短边出”，但实际 L 形合法短边是 **west + north**；`LABELS_PROVENANCE.md` 自己写的是“西/北 1 m 边”。  
2. `README_C1.md` 写 fail “从西侧长边横穿（judge evidence 里 aborted_exit: xmax）”，但 `records.jsonl` cal-062 的实际 detail 是 `last_failure: "illegal_entry_side"`，没有 `aborted_exit: xmax`。  
3. 真实 gravel rollout 使用南侧长边起点，与“短边 approach” note 矛盾。

因此：**标签数据和报告本身在布尔层一致，来源限制诚实；但 C1 的 README/真实 rollout 起点与当前 L 形语义不一致，不能把 C1 当作完整独立成功侧验证。**

---

## 5. 回归与证据链：结构大体一致，无新 scorer 假成功；仍有正式链路缺口

- `comp_judge_conformance.py`：13 组测试覆盖 spoof exit、approach ground、retry、bridge、height_bar、high_wall、t_stairs、slope、gravel、slalom、AttemptManager、timeout、scene geom tags。与 `G1_SELFCHECK.md` 的 “13 groups” 一致。
- `comp_score.py --self-test`、`comp_import_selftest.py`、`comp_part1_course.py`、`comp_part2_judge.py` 自检在 `G1_SELFCHECK.md` 中均报 OK。
- 四份产物：
  - part1 diag：summary↔trials 结构一致，但 `attempts_used=8` 超 Part1 3 次预算；因为 manifest 标 diagnostic，`comp_score.py` 只给 warning。
  - part2 diag / official diag：summary↔trials attempts 数、best_success_value=null、best_score=0 一致。
  - course diag：summary↔trials 一致；实际 judge 有 height_bar `wrong_exit_side`，其余多为 `route_complete`，没有 success 证据。
- 三份演练 `part1_course_pause_resume_drill.json`、`part1_course_abort_drill.json`、`part1_course_pause_timeout_drill.json` 与 `records.jsonl` cal-085..088 的账本语义一致：恢复不消耗、abort/skip 消耗、pause_timeout 120 s、skipped 不计分/不计时。
- `HASHES.json`：`audited:false`、`verdict:"pending"`，与 `G1_SELFCHECK.md` 的 `--verdict pending` 一致；对象 hash 与提供的文件 hash 对应。`comp_audit_hashes.py` 也包含四份 eval 产物、C1 文件、演练文件。
- 未在现有产物中发现 scorer 假成功：所有 diagnostic 总分均为 0；part1 diag 的 failures 与 trials 的失败原因一致；course diag 没有把失败尝试误导入 success。

**新发现问题/缺口：**
- 单障碍 gravel 诊断起点为南侧长边，不是合法短边；C1 真实 gravel 失败样本因此没有验证合法短边入口。
- `README_C1.md` 的砂砾坑 success/fail 描述过时。
- `comp/CONTRACT.md` §6 资产清单仍列 V1 judge 文件（`part1_event_judge.py`、`part1_judge.py`）及其旧 hash；`HASHES.json` 已把它们放入 superseded，但 CONTRACT.md 未同步。非 blocker，但文档证据链需清理。
- 正式链路仍缺：真实成功 rollout、操作手 3 次整场视频、Part2 官方能力场逐档核对、真实坑体/碎木几何 recut。
- `AttemptManager`/course 账本实现与演练一致，但正式手动 runner 尚未用真实操作手事件跑完整 3 次整场视频。

---

## 6. 结论

- **verdict：CONCERN**。  
- **是否有 blocker：无 scorer/judge 实现 blocker。**  
  砂砾坑短边、长边失败、中段 2 足失败、合法离开后落地；限高杆 under-bar、低姿态 success、站立 not_under_bar、落杆 fail，核心实现均有 conformance 支撑。  
  **但 C1/诊断证据链存在必须修正或写入 G1 的文档与起点不一致。**
- **是否建议进入下一阶段（C2/轨迹训练）：yes（有条件）。**  
  C2/训练用的是仿真物理奖励，不依赖 judge 成功侧；可以开始轨迹训练。但正式基线/对外分数前必须修正 diagnostic gravel 起点与 C1 文档，并补真实成功 rollout。
- **G1 必写残余：**
  1. 砂砾坑真实坑体/碎木几何未 recut；当前为凸盒代理。
  2. Part2 官方能力场未逐档核对。
  3. 限高杆 under-bar 用 base z 代理，未做全身离地间隙检查。
  4. T 台阶/沟壑等保守边界仍留 G1。
  5. 真实成功 rollout 缺失；C1 成功侧主要是 rulecard/语义确认，不是独立盲测。
  6. 正式手动 3 次整场演练视频未补；course diag 只是脚本化协议链路。
  7. soft-reset 启发式仍为 G1 残余。
  8. **新写：单障碍 gravel 诊断起点 `(5.0,-13.4)+y` 是南侧长边，不是合法短边；C1 真实 gravel rollout 未覆盖合法短边进入。**
  9. **新写：`README_C1.md` 的“南短边进/西侧长边横穿/aborted_exit xmax”与当前 L 形几何、`LABELS_PROVENANCE.md`、`records.jsonl cal-062` 不一致，G1 前应修正。**
  10. **新写：`comp/CONTRACT.md` §6 仍列 V1 judge 资产，需与 V2.1/HASHES 对齐。**
