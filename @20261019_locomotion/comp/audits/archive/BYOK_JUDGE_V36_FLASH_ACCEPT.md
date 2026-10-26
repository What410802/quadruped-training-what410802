verdict：**CONCERN**。  
是否有 blocker：**无 scorer/judge 语义级 blocker**；但 C1 证据链与正式整场链路仍有残余，不能据此冻结正式分数。  
是否建议进入下一阶段：**yes（可进入 C2 基线/轨迹训练，但不能把当前诊断分或 C1 100% 当作正式冻结依据）**。

> 说明：工件未提供行号，以下用“文件::函数/常量/字段”定位。

---

## 1. 砂砾碎木坑：语义、实现、证据一致

**几何一致。**  
`assets/terrain/part1/part1_eval_scene_v2.xml` 中：
- `gravel_pit_a`：x span `[4.3361, 5.3361]`，y span `[-13, -12]`
- `gravel_pit_b`：x span `[5.3361, 6.3361]`，y span `[-13, -11]`

二者并集是 L 形，西北角缺 1×1 notch。合法短边是西边 `x=4.3361, y∈[-13,-12]` 与北边 `y=-11, x∈[5.3361,6.3361]`。  
`comp_part1_judge.py::GRAVEL_X_LO/X_MID/X_HI`、`GRAVEL_Y_LO/MID/HI`、`GRAVEL_SHORT_EDGES` 与 XML 数值一致；`GRAVEL_BOUNDARY` 明确区分 `south_long/east_long`、`west_short/north_short` 与 notch 边。

**GravelPit 进出判定满足主契约。**  
- `GravelPit._track_footprint` 只在 base footprint 跨越坑边界时记录 `entry_edge` / `exit_edge`。
- 进入时要求“恰好一条 short edge 且只有这一条边”，否则 `illegal_entry=True`；从 `south_long/east_long/notch_h/notch_v` 进入都会失败。
- 离开时要求“恰好一条 short edge、且与进入 short edge 不同”，否则 `illegal_exit=True`；从长边、同一条短边折返、notch 边离开都失败。
- `GravelPit._check_exit` 最终要求 `{entry, exit} == {"west","north"}`，并要求 `gravel_hits >= 3`。

**逐项回答：**
- 合法 L 路径能否 success：**能**。`comp_judge_conformance.py::test_gravel_short_edges_and_long_edge` 的 west→north 路径断言 success。
- 长边进入/退出是否失败：**是**。同一测试覆盖 south long entry、east long exit、east long entry，均非 success，并记录 `illegal_entry` / `illegal_exit`。
- 坑中段 2 足触地是否失败：**是**。`GravelPit` 继承 `ground_fail=True`；`_ground_penalty_active` 在未合法离开坑前启用，`mid_pit` 用例断言失败。
- 合法离开后落地是否不判罚：**是**。`GravelPit._ground_penalty_active` 在 `exit_edge` 已记录后返回 False；`landing` 用例插入合法出坑后的 2 足地面采样仍 success。

**残余：** 进出边界用的是 **base footprint**，不是足端接触面；极端贴角/单脚先入等边界仍可能误判。这是 G1 应写的代理语义残余，但未在当前 conformance 中形成 blocker。

---

## 2. 限高杆：确实要求“从杆下穿过”，不只是杆掉落

**实现要求 gate crossing。**  
`comp_part1_judge.py::HeightBar._on_sample` 要求：
- y 跨越 `-9.0`；
- `BAR_OPENING_X = (5.2, 6.2)` 内；
- `abs(prev_y - y) < 1.0`；
- 记录 `cross_valid`、`cross_max_z`、`cross_bar_z`。

`HeightBar._check_exit` 要求：
- entry/exit 必须是 `ymin/ymax` 且互为对边；
- `cross_valid >= 1`；
- `bar_base_seen` 已知；
- `bar_dropped_seen == False`；
- `cross_z <= cross_bar`，否则 `not_under_bar`。

**逐项回答：**
- 低姿态通过是否 success：**是**。conformance 中 `z=0.25 < bar_z=0.325` 断言 success。
- 站立高度通过是否 `not_under_bar`：**是**。`z=0.45` 用例非 success，并记录 `not_under_bar`。
- 杆掉落是否 fail：**是**。`BAR_DROP_THRESHOLD_M=0.05`；drop 用例失败；pre-entry drop 也不能成功。
- 是否只看杆掉落：**否**。必须有合法 gate crossing 且 `cross_z <= cross_bar`；仅杆不掉、从外侧横切或 x 不在开口内都不会 success。

**残余：** `cross_z` 用的是 **base z 代理**，不是全身离地间隙；`BAR_OPENING_X` 包含两柱中心，且 `cross_max_z` 对多次穿越取最大，偏保守。G1 已列残余；未发现新的假 success blocker。

---

## 3. route：gravel 段合法 L 路径；course 路线是诊断链路

`config/part1-route.json` 的 gravel 段：
- `to_gravel`: `(3.6, -12.5)`
- `cross_gravel_west`: `(5.8, -12.5)`
- `cross_gravel_north`: `(5.8, -10.6)`

第一段从西侧进入，在 `x≈4.3361, y=-12.5` 穿过 west short edge；第二段沿 `x=5.8` 向北，在 `y=-11` 穿过 north short edge。与 `GravelPit` 的 west→north 合法 L 语义一致。  
`run_part1_judged_rollout_v2.py::SPECIAL_WAYPOINTS["gravel_pit"]` 为 `(4.6,-12.5)→(5.8,-12.5)→(5.8,-10.6)`，其中 `(4.6,-12.5)` 在 `to_gravel→cross_gravel_west` 直线上，功能一致。

**但 course 路线是 diagnostic，不是正式手动赛程。**  
`comp/eval/flat-ft-2500-part1-course-diag/manifest.json` 明确 `mode=course_diagnostic, diagnostic=true`，`run_part1_course.py` 文档也说明脚本化 waypoint 只是 P0 诊断。  
另外 `config/part1-route.json` 的 `cross_slope` target `(5.2,-4.2)` 仍在 `ZONES["slope"]` 的 y 上界 `-4.0` 内，并不是一个干净的“出 slope zone”点；真正出区发生在下一段 `to_slalom`。由于 `Slope` 只要求沿长边累计距离，不要求固定 side，故不是 judge 语义 blocker，但属于诊断路线质量问题。

course-diag 中 height_bar `wrong_exit_side` 等失败原因是脚本策略实际执行结果，不是 judge 语义证明；该路线不能替代正式整场操作手演练。

---

## 4. C1 标定：数据一致，但 100% 的解释力有限

**数量与文件一致。**  
`comp/eval/_calibration/records.jsonl` 共 92 条：
- 32 条 `part1_obstacle`
- 24 条 `part2_level`
- 28 条 rulecard
- 8 条 `session_state`

`labels_template.csv` 有 92 行标签；`C1_CALIBRATION_REPORT.md` 显示 92/92、一致 92、100%；`check_calibration.py` 当前逻辑与报告输出一致。

**provenance 诚实记录了限制。**  
`LABELS_PROVENANCE.md` 明确写：
- 56 条真实 rollout 是用户盲标；
- 28 条 rulecard 是“用户确认语义 + executor 按确认补全”，**非盲标**；
- 8 条 session 是“用户确认 + executor 补全”，**非盲标**；
- 修复砂砾坑/限高杆后未再请用户逐卡重看；
- 真实成功 rollout 仍缺失。

所以“92/92  judge-human 一致”**不能理解为 92 条独立盲测**。

**是否还有 judge-human 不一致：**  
按 `check_calibration.py` 当前比较口径（`human_success` vs `judge.status == success`，session 只看 `human_protocol_ok`），**没有发现 success/fail 级不一致**。

**但存在 C1 证据链/C1 门禁实现问题：**
- `check_calibration.py` 完全没有比较 `human_judge_verdict_correct` 列；即使该列为 false，报告仍可能显示 100%。
- `check_calibration.py` 没有校验 `human_failure_reason` 是否符合失败原因字典，也没有比较 reason。
- rulecard 的 `human_success` 是按 judge 结论补的，因此 rulecard 的 100% 对 judge 独立性很弱。
- `LABELS_PROVENANCE.md` 引用了 `labels_user_partial_20261023.csv`，但该文件没有出现在 `HASHES.json` 对象中；原始盲标证据未进入哈希链。

因此 C1 数据本身一致、provenance 诚实；但“C1 PASS”只能作为主路径语义确认，不能作为完整独立盲测 acquittal。这是本轮主要 CONCERN 来源。

---

## 5. 回归与证据链

**conformance：**  
`comp_judge_conformance.py` 的 test list 为 13 组，与 `G1_SELFCHECK.md` 的 “13 groups” 一致；包含砂砾短边/长边、限高杆 under-bar、桥、墙、T 台阶、slope、slalom、attempt manager、timeout、scene geom tags。

**self-test：**  
`comp_part1_course.py`、`comp_part2_judge.py`、`comp_score.py`、`comp_import_selftest.py` 均存在 self-test；G1_SELFCHECK 记录 OK。未在提供证据中发现 self-test 输出与结论矛盾。

**四份产物 summary↔trials：**
- `flat-ft-2500-part1-diag-v2`：8 trials，summary `attempts_used=8`，8 障碍全 fail/timeout，evidence id 对得上。  
  但 `attempts_used=8` 超过契约整场 3 次，`comp_score.py` 会给出 diagnostic warning；这是诊断产物，不是正式整场。
- `flat-ft-2500-part2-diag-v2`：20 trials，summary 计数 4/4/4/4/3/1，全 fail，一致。
- `flat-ft-2500-part2-official-diag`：24 trials，6 类 ×4，summary 每类 `attempts_used=4`，一致。
- `flat-ft-2500-part1-course-diag`：24 trials = 3 attempts ×8 障碍；summary `attempts_used=3`、`final_time_s=113.56`、全 fail；无 success evidence，一致。

**三份演练：**
- pause/resume：3 attempts，recoveries 3，暂停期间 sim time 冻结，duration 不含暂停；与 `cal-085/086` 状态表一致。
- abort：3 attempts，`skipped=true, reason=operator_abort`，skip 消耗尝试；与 `cal-087/089` 一致。
- pause_timeout：1 attempt，pause 后无 resume，`operator_t≈121.02` 触发 skip，duration 0.5；与 `cal-088` 一致。

**HASHES/G1_SELFCHECK：**  
`HASHES.json` 当前列出 76 个对象，包含四份产物、levels、C1 records/labels/provenance、三份 evidence、C1 报告等；`G1_SELFCHECK.md` 记录 “HASHES(76)”，数量一致。  
但 `HASHES.json` 的 `audited=false, verdict=pending`，说明当前仍是待审状态，不是已冻结门禁。

**新 scorer 假成功/误判失败：**  
未发现新的 scorer 级假成功 blocker。  
主要残余是：C1 门禁未校验 `human_judge_verdict_correct`；原始盲标 CSV 未入 HASHES；限高杆 base-z 代理；砂砾坑 base footprint 代理；正式手动整场 runner/video 未补；Part2 官方能力场未逐档核对。

---

## 6. 结论

**verdict：CONCERN。**

- **blocker：无 scorer/judge 语义级 blocker。**  
  砂砾坑 west→north 合法 L、长边进出失败、坑中 2 足触地失败、合法出坑后落地不判罚，在当前实现和 conformance 中成立。  
  限高杆确实要求 gate crossing + under-bar，低姿态 success、站立 `not_under_bar`、杆掉落 fail，当前证据成立。

- **但不宜判定 PASS 的点：**  
  C1 的 100% 对 rulecard/session 不是独立盲测；`check_calibration.py` 未校验 `human_judge_verdict_correct`；原始盲标 CSV 未进 HASHES；正式手动整场链路和真实成功 rollout 仍缺失。

- **建议进入下一阶段：yes（有条件）。**  
  可进入 C2 基线/轨迹训练开发；但**不建议**在残余关闭前把当前 judge/C1 结果冻结为正式对外分数。

### G1 必写残余（含新增）

1. 砂砾坑真实坑体/碎木未 recut；当前为凸起盒代理。  
2. 砂砾坑 entry/exit 使用 base footprint，不是足端接触面；贴角/单脚先入等边界可能误判。  
3. 限高杆 under-bar 用 base z 代理，不是全身离地间隙；`BAR_OPENING_X` 含柱中心，多次穿越取 `cross_max_z` 偏保守。  
4. Part2 官方能力场未逐档核对。  
5. 真实成功 rollout 缺失；当前成功侧主要靠 rulecard。  
6. C1 的 rulecard/session 标签为非盲语义确认；`check_calibration.py` 未校验 `human_judge_verdict_correct` 和 failure reason；`labels_user_partial_20261023.csv` 未入 HASHES。  
7. 正式手动 3 次整场 runner/video 未补；`run_part1_course.py` 仍是脚本化 diagnostic。  
8. `flat-ft-2500-part1-diag-v2` 的 `attempts_used=8` 超契约 3 次，虽为 diagnostic 且 `comp_score.py` 仅 warning，但不能作为正式整场证据。  
9. slalom 终点圆与最后一根杆显示重叠，judge 已用 `last_post_cleared` 防护，但场景显示仍需修。  
10. soft-reset 启发式仍是 G1 残余；当前未见 blocker，但边界行为需继续审计。  
11. `HASHES.json` 仍 `audited=false / verdict=pending`，G1 未冻结。
