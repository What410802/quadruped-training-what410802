## verdict: **CONCERN**

无 scorer blocker，但存在**证据链/文档一致性问题**与**限高杆语义边界**，不建议直接 PASS。是否进入下一阶段：**yes（有条件）**。

---

## 1. 砂砾碎木坑：语义与实现一致，但 C1 真实 rollout 证据与声称不一致

**几何对齐（通过）**

`assets/terrain/part1/part1_eval_scene_v2.xml`：
- `gravel_pit_a pos="4.8361 -12.5 0.075" size="0.5 0.5 0.075"` → x∈[4.3361,5.3361], y∈[-13.0,-12.0]
- `gravel_pit_b pos="5.8361 -12.0 0.075" size="0.5 1.0 0.075"` → x∈[5.3361,6.3361], y∈[-13.0,-11.0]

union = 2 m×2 m 去掉左上 1 m×1 m notch，与 `comp_part1_judge.py::GRAVEL_X_LO/MID/HI`、`GRAVEL_Y_LO/MID/HI` 完全一致。`GRAVEL_SHORT_EDGES` 的 `west`（x=4.3361, y∈[-13,-12]）与 `north`（y=-11.0, x∈[5.3361,6.3361]）就是两条真实 1 m 短边；`GRAVEL_BOUNDARY` 的 `south_long`/`east_long` 是 2 m 长边，`notch_h`/`notch_v` 是内凹边。

**进出判定（通过）**

`GravelPit._track_footprint` 用 base 轨迹与真实 pit 边界求交：
- 进入：只接受**恰好一条且为 short** 的边，否则 `illegal_entry`；
- 离开：只接受**与 entry 不同的另一条 short**，否则 `illegal_exit`；
- `_check_exit` 额外要求 `{entry,exit} == {west,north}` 且 `gravel_hits ≥ 3`。

`comp_judge_conformance.py::test_gravel_short_edges_and_long_edge` 覆盖：
- legal L（west 进、north 出）→ success；
- 合法离开后落地（exit_edge 已置位，`_ground_penalty_active` 返回 False）→ 不罚；
- 坑中段 2 足触地 → fail；
- south/east 长边进、east 长边出 → `illegal_entry_side` / `illegal_exit_side`；
- 从 notch 缺口进（隐含穿过 notch_h/notch_v）→ 非 short，`illegal_entry`。

**结论：契约“短边进、短边出、长边失败、中段 2 足失败、合法离开后落地不罚”全部满足。**

**但 C1 真实 rollout 与文档矛盾（CONCERN）**

`comp/eval/_calibration/records.jsonl` 的 `cal-003/011/019/027` 仍是：
```json
"command": [0.45, 0.0, 0.0], "route": null
```
即开环直行，不是闭环 L 路径；对应 `part1-diag-v2/trials.jsonl` 中 gravel 终点 base=(4.151,-12.523)，机器人只走了约 0.55 m，未执行“西短边进→左转→北短边出”。

而 `G1_SELFCHECK.md` 2026-10-23 19:25 称“**C1 records 的 gravel rollout 带 route 字段**”，`README_C1.md` 称“真实 rollout 的 gravel 视频已改用合法 L 形脚本路线”。二者与 records 实际内容不符。这是**可验证的文档/证据链不一致**，虽不影响 judge 语义，但不能 PASS。

---

## 2. 限高杆：under-bar 检查有效，但“对边离开”比规则字面更严

**实现（通过基本语义）**

`HeightBar._on_sample`：仅当 base 穿越 `y=-9.0` 且 `x∈BAR_OPENING_X=(5.2,6.2)` 时记 `cross_valid`，同时记录 `cross_max_z`（base z）与 `cross_bar_z`。

`HeightBar._check_exit` 要求：
- entry/exit 为 `ymin/ymax` 对边；
- `cross_valid ≥ 1`；
- `bar_base_seen` 存在、未 `bar_dropped_seen`；
- `cross_max_z ≤ cross_bar_z`，否则 `not_under_bar`。

`test_height_bar_touch_drop_and_gate` 覆盖：
- base z=0.25、bar_z=0.325 → success（低姿态通过）；
- z=0.45 → `not_under_bar`（站立高度失败）；
- bar_z 0.325→0.20 → `bar_dropped` fail；
- 进入前已掉杆 → fail；
- x=4.6 绕到门口再侧移 → 不产生 `cross_valid`，fail。

**结论：低姿态 success、站立 not_under_bar、杆落 fail、outside-then-lateral fail 均成立；碰柱/碰梁未掉杆不判失败（judge 只看 drop 与 base z），与 Q3 一致。**

**新误判风险（非阻塞，但应写入残余）**

`_check_exit` 要求 `side == _opposite(entry)`。若机器人已从门洞下方穿过（`cross_valid≥1`），随后折返从**原侧**离开 zone，会判 `wrong_exit_side` fail；而 `CONTRACT.md` §2 / `team-race-2026.md` §2.1 的字面是“任何运动姿态从限高杆下方穿过；横杆不掉落”，并未要求必须到对侧。这是潜在“真成功判失败”。真实比赛成功路径通常直穿到另一侧，影响有限，但应列为残余/待确认。

`comp/eval/flat-ft-2500-part1-course-diag/trials.jsonl` 的 height_bar `wrong_exit_side`、`in_zone_samples=17517`（约 87 s）、`touched=false`：证据指向机器人在 zone 内长时间停留后从侧边出界，属于**脚本 route/策略鲁棒性问题**，不是 judge 假成功；但也说明 course 诊断链路尚未证明成功侧。

---

## 3. route：gravel 段数学上合法 L，但 course/诊断路线执行鲁棒性不足

`config/part1-route.json`：
- `to_gravel` (3.6,-12.5) → `cross_gravel_west` (5.8,-12.5) → `cross_gravel_north` (5.8,-10.6)。

按直线段计算：
- 第一段只穿 `x=4.3361, y=-12.5` → west_short；
- 第二段只穿 `y=-11.0, x=5.8` → north_short；不穿 notch_h/notch_v（y=-12.5 不在 notch 范围；x=5.8 > MID）。
- 因此是**合法 L 路径**，与 judge 语义一致。

`run_part1_judged_rollout_v2.py::SPECIAL_WAYPOINTS["gravel_pit"] = [(4.6,-12.5),(5.8,-12.5),(5.8,-10.6)]` 同样合法。

**但 course 实测**：`part1-course-diag` 中 height_bar 报 `wrong_exit_side`，且 in_zone_samples 异常大，说明 `run_part1_course.py` 的 waypoint controller 在 height_bar 附近卡住；route 的“语义合法”不等于“实际可执行”。这是 course runner 残余，不是 route 语义错误。

---

## 4. C1 标定：92 条/标签/报告数字自洽，但标签来源限制已被诚实记录；发现一处文档不一致

**数量与组成（自洽）**

`records.jsonl` 共 92 条：
- `part1_obstacle` 32（cal-001..032）
- `part2_level` 24（cal-033..056）
- `part1_rulecard` 16（cal-057..072）
- `part2_rulecard` 12（cal-073..084）
- `session_state` 8（cal-085..092）

与 `README_C1.md` 的 32/24/16/12/8=92 一致；`DEV_OPS.md` 的“64 主记录（32+24+8）+28 rulecard”也一致。

**labels 与报告（自洽）**

`labels_template.csv` 92 行：
- 56 条真实 rollout 全 `human_success=false`（reason 为 `no_crossing/two_feet_ground/fell/timeout`），judge 也全 fail/timeout 或 fail/fell；
- 28 条 rulecard 的 `human_success` 与 judge status 一一对应，`human_judge_verdict_correct=true`；
- 8 条 session `human_protocol_ok=true`。

`C1_CALIBRATION_REPORT.md` 的 92/92、100%、分项 4/2/8 条与这些文件自洽。

**标签来源（诚实记录）**

`LABELS_PROVENANCE.md` 明确：
- 只有 56 条真实 rollout 是用户盲标；
- 28 rulecard 是“用户确认语义 + executor 按确认补全”，非盲标；
- 8 session 是“用户确认 + executor 补全”，非盲标；
- 真实成功 rollout 仍缺失，成功侧证据目前是 rulecard + judge 实现。

`README_C1.md`、`STATUS.md` 也重复了“当前真实 rollout 全失败”。**因此 C1 的 100% 主要说明规则语义与卡片一致，不构成对 judge 成功路径的独立盲测；这一限制已被诚实记录。没有新的 judge-human 不一致（在给定标签口径下）。**

**不一致（CONCERN）**

同上：`G1_SELFCHECK.md` 称 gravel rollout 带 route 字段，`README_C1.md` 称已改闭环 L 形；但 `records.jsonl` 的 cal-003/011/019/027 `route=null`、command 为开环直线。`part1-diag-v2/trials.jsonl` 的 gravel base=(4.151,-12.523) 证明未完成 L。文档与记录不一致，需修正。

另：题目未内联 `check_calibration.py`，只给了报告与 CSV；我无法独立复核其比较逻辑（该文件在 HASHES 中但未提供内容）。这属于证据链的外部依赖，不构成 blocker，但 reviewer 只能凭文件自洽性判断。

---

## 5. 回归与证据链：13 组/self-test/四产物/三演练/HASHES 基本一致

- `comp_judge_conformance.py` 的 tests 列表为 13 个函数（`test_spoof_exit_positions` … `test_scene_geom_tags_complete`），与 `G1_SELFCHECK.md` 的“13 groups”一致。
- `check_part1_scene_v2.py` 的 `REQUIRED_GEOMS` 28 个，报告 `scene v2 check: OK (28 geoms, beam stable)`、`drop=0.0000 m`，与自检一致。
- 各 self-test：`comp_score.py --self-test`、`comp_import_selftest`、`comp_part1_course` self-test、`comp_part2_judge` self-test 均声明 OK；对应代码中确有 `run_self_test`。
- 四份产物 summary↔trials：
  - `part1-diag-v2`：attempts_used=8，trials 8 条，8 障碍全 fail/timeout，grand_total=0；
  - `part2-diag-v2`：attempts_used 4/4/4/4/3/1，trials 20 条，best_success_value 全 null，total=0；
  - `part2-official-diag`：attempts_used 4×6，trials 24 条，total=0；
  - `part1-course-diag`：attempts_used=3，trials 24 条（8×3），final_score=0、final_time=113.56，与三次 attempt duration 113.56 一致。
- 三份演练：
  - `pause_resume`：3 attempts，duration 113.56，recoveries=3，pause/resume 事件，恢复不消耗；
  - `abort`：3 skipped，final_time=0，duration 2.505；
  - `pause_timeout`：1 skipped，operator_t≈121.02，duration 0.5。
  与 `AttemptManager`/`Part1Course` 语义一致。
- `HASHES.json`：76 objects，judge/scene/contract/route/levels/eval/evidence 的 sha 与 artifact 头部 sha 一致（如 `comp_part1_judge.py e1fe9849…`、`CONTRACT.json 627d6135…`、`part1_eval_scene_v2.xml c03cd34a…`、`part1-route.json db0640bc…`）；`audited=false`、`verdict=pending`、`reviewer=pending`，符合 G1 未冻结。
- 无 scorer 假成功：四产物全 0 分、无 success trial，summary 没有成功 evidence 指向失败 trial 的情况。误判失败方面，course height_bar `wrong_exit_side` 是脚本/几何导致，不是 judge 逻辑错误；judge 按契约要求对边+门洞，属于严格判定。

---

## 新问题

1. **C1 gravel 记录/文档不一致**：`records.jsonl` cal-003/011/019/027 `route=null`、开环 command；`G1_SELFCHECK.md` 称“带 route 字段”、`README_C1.md` 称“闭环 L 形”。真实 base 只到 (4.151,-12.523)，未完成 L。需重生成闭环 waypoint 记录或明确标注为开环意图。
2. **HeightBar 对边严格性**：已穿门后折返原侧会判 `wrong_exit_side` fail；规则字面只要求“从下方穿过一次”。建议在 G1 残余中明确该口径，或改为“只要 `cross_valid≥1` 且未掉杆即 success”（保留绕过检查）。
3. **course runner 暂停期间以 1 个 5 ms substep 近似冻结**：`run_part1_course.py` 在 paused 时仍执行一次 `physics_step`/`feed` 后才进入 fake clock loop；严格应为 0 substep。影响小，但应记录。
4. **C1 成功侧仍无真实视频**：56 条真实 rollout 全失败，rulecard/session 非盲；C1 100% 不构成独立盲测（已在 `LABELS_PROVENANCE.md` 记录，需在 G1 结论中再次明示）。
5. **`check_calibration.py` 未内联**：C1 报告只能凭 CSV/records 自洽性判断，无法独立复核 checker 逻辑。

---

## 是否建议进入下一阶段（C2/轨迹训练）：**yes（有条件）**

无 scorer blocker，judge 语义/conformance/route 数学合法、四产物与演练账本一致。建议：
- **先**低成本修正 C1 gravel records/README/G1_SELFCHECK 的一致性（重生成闭环 waypoint 记录，或在记录中明确 `route=null` 为开环、并同步删除“已改闭环”的表述）；
- **同时**可启动 C2 训练（reward 用仿真物理量，不依赖 judge 成功侧）；把“真实成功 rollout 重跑 C1”作为 G1 冻结前的前置证据，而不是训练启动的阻塞项。

若要求 G1 在本次直接冻结，则应判 **CONCERN 并暂缓冻结**，先关闭第 1、2 项。

---

## G1 必写残余（更新版）

- 砂砾坑真实坑体/碎木未 recut（本地为两个凸起盒代理）；C1 真实 gravel rollout 仍为开环、未执行合法 L（本次新发现）。
- Part2 官方能力场未逐档核对；参数化 level 与官方场只做同种类语义对齐。
- 限高杆 under-bar 用 base z 代理全身高度；且要求 entry/exit 对边，对“穿过后折返原侧”可能误判失败（本次新发现）。
- 真实成功 rollout 缺失：C1 56 条真实 rollout 全失败；48/48 预扫描 fail；成功侧只有 rulecard。
- 正式手动 3 次整场演练视频未补；course 为脚本化诊断链路，且 height_bar 段实测 `wrong_exit_side`，未证明整场成功侧。
- course runner 暂停期间以 1 个 5 ms substep 近似冻结（严格应 0 substep）。
- slalom 终点圆与最后一根杆显示重叠；judge 已用 `last_post_cleared` 处理，但场景显示未修。
- C1 的 rulecard/session 为非盲标语义确认，不构成独立盲测；`check_calibration.py` 未内联给 reviewer。
- T 台阶/沟壑等保守边界；Part2 计分曲线 floor 与 10 cm 端点 0 分已实现，但官方场未核。
- HASHES 当前 `audited=false`、`verdict=pending`，G1 尚未冻结；本 verdict=CONCERN 不改变该状态。
