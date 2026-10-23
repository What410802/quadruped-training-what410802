## verdict

**CONCERN**。  
未发现已确认的 **scorer blocker**；核心规则语义（砂砾坑 L 形短边、限高杆 under-bar）在当前实现与 conformance 中基本成立。但存在若干证据链/文档漂移和新的非阻断风险，尤其是 C1 标签表备注仍残留旧砂砾描述、G1_SELFCHECK 的 HASHES 数量前后不一致、以及 slalom 终点圆与最后一根杆重叠可能形成假成功路径。  
**建议进入下一阶段 C2/轨迹训练：yes（有条件）**：先把 G1 残余和新发现写清，正式链路前修 pause/resume runner 与 slalom 端点/场景歧义。

---

## 1. 砂砾碎木坑

**几何与短边定义：成立。**

- 场景 `assets/terrain/part1/part1_eval_scene_v2.xml` 中：
  - `gravel_pit_a`：x 约 `[4.3361, 5.3361]`，y `[-13, -12]`；
  - `gravel_pit_b`：x 约 `[5.3361, 6.3361]`，y `[-13, -11]`；
  - 并集是 L 形，西侧 1 m 短边、北侧 1 m 短边；南/东为 2 m 长边。
- `comp_part1_judge.py::GravelPit` 的常量 `GRAVEL_X_LO/MID/HI`、`GRAVEL_Y_LO/MID/HI`、`GRAVEL_SHORT_EDGES` 与 XML 一致；`GRAVEL_BOUNDARY` 把 `west_short`、`north_short` 与南/东长边、凹口边区分开。

**进出判定：满足契约。**

- `GravelPit._track_footprint` 用 base xy 跨 L 形边界记录 `entry_edge/exit_edge`；进入时只接受恰好穿过一个短边，离开时要求恰好穿过另一个短边。
- `GravelPit._check_exit` 要求 `{entry, exit} == {"west", "north"}`，且 `gravel_hits >= 3`；长边进入/离开分别落到 `illegal_entry_side` / `illegal_exit_side`。
- `GravelPit._ground_penalty_active` 在已 `supported` 且尚未合法离开（`exit_edge is None`）时启用 2 足触地判罚；合法离开后 `exit_edge` 已设置，落地不判罚。

**Conformance 覆盖：**

- `comp_judge_conformance.py::test_gravel_short_edges_and_long_edge` 明确覆盖：
  - 合法 L 路径 `west -> north` success；
  - 合法离开后落地 success；
  - 坑中段 2 足触地 fail；
  - 旧路径南长边进入 fail；
  - 东长边进入/离开 fail。
- 结论：**合法 L 路径可 success；长边进入/退出失败；坑中段 2 足触地失败；合法离开后落地不判罚**。

**残余：** 本地场景仍是凸起盒代理，不是真实坑体/碎木；这是已知 G1 必写残余。另外边界顶点精确穿越可能较脆，但不构成当前 blocker。

---

## 2. 限高杆

**under-bar 判定：成立。**

- `comp_part1_judge.py::HeightBar`：
  - `_pre_sample` 用首次观察到的 `bar_z` 作为基线，下降 `> BAR_DROP_THRESHOLD_M` 记为 `bar_dropped_seen`；
  - `_on_sample` 要求 base 在 `BAR_OPENING_X = (5.2, 6.2)` 内穿过 `y = -9.0`，并记录穿越时的 `cross_max_z` 与 `cross_bar_z`；
  - `_check_exit` 要求入口/出口为相反 y 侧、`cross_valid >= 1`、未落杆、且 `cross_z <= cross_bar`，否则 `not_under_bar`。
- 因此不是“只看杆掉落”：必须从门洞下方穿过。

**Conformance：**

- `comp_judge_conformance.py::test_height_bar_touch_drop_and_gate` 覆盖：
  - 低姿态 `z=0.25`、`bar_z=0.325` -> success；
  - 站立高度 `z=0.45` -> fail，且记录 `not_under_bar`；
  - 杆下降 -> fail；
  - 入区前已落杆/从门洞外横向绕行 -> 不 success。
- 结论：**低姿态通过 success；站立高度通过 not_under_bar；杆掉落 fail；当前 conformance 未见 HeightBar 自身新误判。**

**残余：** under-bar 仍用 base z 代理，不是全身离地间隙；这是已知 G1 残余，需在 G1 写清。

---

## 3. route

**gravel 段：是合法 L 路径。**

- `config/part1-route.json`：
  - `to_gravel` 到 `(3.6, -12.5)`；
  - `cross_gravel_west` 到 `(5.8, -12.5)`：从西侧 1 m 短边进入；
  - `cross_gravel_north` 到 `(5.8, -10.6)`：从北侧 1 m 短边离开。
- `run_part1_judged_rollout_v2.py::SPECIAL_ROUTES["gravel_pit"]` 与 `comp/eval/_protocol.md §4.1` 的 gravel 描述一致：西短边进 -> 左转 -> 北短边出。
- 结论：**gravel route 与 judge 语义一致。**

**course/诊断路线整体：** 其他 waypoint 基本与 zone 方向一致；`height_bar` 路线先到区域外再沿 +y 穿门洞，`bridge_blocks` west->east、`bridge_bands` south->north、`slope` 沿 +y，均与 judge 入口/距离语义大体一致。  
但该 route 是 P0 诊断脚本路线，不是正式操作手赛程；正式手动 3 次整场演练视频仍是残余。

---

## 4. C1 标定

**数量与报告：基本一致。**

- `comp/eval/_calibration/records.jsonl`：92 条。
- `labels_template.csv`：92 条标签行。
- `C1_CALIBRATION_REPORT.md`：92 已加载、92 参与比较、92 一致、100%。
- `LABELS_PROVENANCE.md` 诚实记录：
  - 56 条真实 rollout 是用户盲标；
  - 28 条 rulecard 是“用户确认语义 + executor 补全”，非盲标；
  - 8 条 session_state 是用户确认 + executor 补全，非盲标；
  - 真实成功 rollout 缺失，成功侧主要靠 rulecard；
  - 砂砾坑/限高杆修复后未再请用户逐卡重看。
- 结论：**来源限制记录是诚实的；未发现 success/fail 层面的 judge-human 不一致。**

**但存在文档/证据链漂移：**

1. `labels_template.csv` 中 `cal-003/011/019/027` 的备注仍是  
   `short-edge approach along +y`，  
   而 `records.jsonl` 同 trial 已是  
   `legal L path: west 1m short edge in -> turn -> north 1m short edge out`，  
   `README_C1.md` 也写成功卡已改为 L 形。  
   这是明确的 C1 标签表备注与 records/README 不一致。
2. 多条 `human_failure_reason` 与 judge reason 不同，例如：
   - `cal-001` judge `timeout`，label `no_crossing`；
   - `cal-003` judge `timeout`，label `no_crossing`；
   - `cal-015` judge `two_feet_ground:FL,RL`，label `no_crossing`；
   - `cal-031` judge `timeout`，label `fell`。  
   由于 `check_calibration.py` 主要比较 success/fail，C1 的 100% 应理解为 **success/fail 一致率**，不是 reason 完全一致；provenance 已说明 reason 只做统计，但报告本身容易误读。
3. `C1_CALIBRATION_REPORT.md` 未出现在当前 `HASHES.json` 的 objects 中；C1 报告本身未被 hash 固定。不是 blocker，但证据链上是一个小缺口。

**结论：** C1 的 judge-human success/fail 无不一致；但 `labels_template.csv` 的 gravel 备注残留旧描述，必须作为 G1 残余/文档修复项记录。

---

## 5. 回归与证据链

**conformance 与 self-test：**

- `comp_judge_conformance.py` 当前 13 组测试，覆盖 spoof、approach ground、bridge、height_bar、high_wall、t_stairs、slope、gravel、slalom、AttemptManager、timeout finalize、scene geom tags。
- `G1_SELFCHECK.md` 记录的 `comp_score.py --self-test`、`comp_import_selftest.py`、`comp_part1_course.py`、`comp_part2_judge.py` 自检均 OK。
- 未发现这些自检与当前代码明显矛盾。

**四份产物 summary↔trials：**

- `flat-ft-2500-part1-diag-v2`：trials 8 条，summary `attempts_used=8`，8 个障碍各 0 分；与 summary 一致。`comp_score` 会因 diagnostic 行 `attempts_used=8 > 3` 给 warning，但不判 invalid。
- `flat-ft-2500-part2-diag-v2`：trials 20 条；summary 每类 attempts_used 为 4/4/4/4/3/1，与 trials 条数一致；全 0 分。
- `flat-ft-2500-part2-official-diag`：trials 24 条；summary 每类 4 次，与 trials 一致；全 0 分。
- `flat-ft-2500-part1-course-diag`：trials 24 条（3 attempts × 8 obstacles）；summary `attempts_used=3`，`final_time_s=113.56`，与 course drill/session summary 一致；全 0 分，无 return bonus。
- 结论：**四份产物的 summary↔trials 基本一致；当前没有看到 scorer 假成功。**

**三份演练：**

- `part1_course_pause_resume_drill.json` 与 `cal-086` 的 3 attempts、每 attempt pause/resume、duration 113.56 一致。
- `part1_course_abort_drill.json` 与 `cal-087/089` 的 3 attempts skipped、duration 2.505、final 0/0 一致。
- `part1_course_pause_timeout_drill.json` 与 `cal-088` 的 1 attempt、pause_timeout、duration 0.5 一致。
- `HASHES.json` 中三份 evidence 的 sha256 与提供文件一致。

**HASHES 与 G1_SELFCHECK：**

- 当前 `HASHES.json` 的 objects 数量为 **75**；`G1_SELFCHECK.md` 的 19:25 补充段也写 `HASHES(75)`。
- 但 `G1_SELFCHECK.md` 顶部命令日志仍写 `wrote comp/audits/HASHES.json (72 objects)`。  
  这是**历史残留/文档漂移**，不是 hash 错误，但说明 G1_SELFCHECK 文件内部不一致。
- `HASHES.json` 的 `audited=false`、`verdict=pending`，与“尚待 G1 复审”状态一致。

**新发现的正式链路缺口：**

- `run_part1_course.py::run_attempt.run_policy_step` 在 pause 后 resume 时，会在 4 个 physics substep 的循环中直接 `return bool(course.active)`，从而跳过该 policy step 剩余最多 3 个 5 ms substep。  
  这会影响正式 pause/resume 后的控制时序，但属于诊断 runner 集成问题，不是 judge 语义 blocker；正式操作手 runner 仍需修。
- **slalom 端点重叠风险：** `part1_eval_scene_v2.xml` 中终点圆 `(3.2, -12.5)` 半径 0.5，最后一根杆在 `(2.8, -12.5)`，距离 0.4，最后一根杆在终点圆内。`Slalom._on_sample` 的 end-area 判定只要求 `done_before == 4`，因此机器人到达最后一根杆并保持一个采样后，可能在下一采样同时满足 `end_area` 并触发 success。若规则要求“绕过最后一根杆后再进入终点区”，这是一个潜在假成功路径；若按当前场景“终点圆就是终点区域”理解，则更像场景/规则歧义。建议在 G1 明确记录并让用户/主办方口径确认。

---

## 6. 结论与 G1 必写残余

**verdict：CONCERN。**  
**blocker：无已确认 scorer blocker。**  
**建议进入 C2/轨迹训练：yes（有条件）**——先写入 G1 残余并修文档漂移；正式评测前再修 pause/resume runner 和确认 slalom 端点重叠语义。

**G1 必写残余：**

1. 砂砾坑真实坑体/碎木未 recut；当前是凸起盒代理。
2. Part2 官方能力场未逐档核对；当前只验证参数化同种类 level。
3. 限高杆 under-bar 仅用 base z 代理，未验证全身离地间隙。
4. soft-reset 启发式仍是 G1 残余。
5. 真实成功 rollout 缺失；C1 成功侧主要依赖 rulecard。
6. rulecard/session 标签非盲标；C1 的 100% 主要是 success/fail 与语义确认，不是独立盲测。
7. 正式手动 3 次整场演练视频未补；正式操作手 runner 未完全接好。
8. `labels_template.csv` 的 gravel 备注仍残留旧描述 `short-edge approach along +y`，与 records/README 的 L 形路径不一致。
9. `G1_SELFCHECK.md` 顶部仍写 `HASHES(72 objects)`，当前实际 `HASHES.json` 为 75 objects；需统一。
10. C1 report 未纳入 `HASHES.json` 固化对象；建议补入或说明其为派生产物。
11. slalom 终点圆与最后一根杆重叠，存在“到最后一根杆后停住仍可 next-sample 触发 end_area”的风险；需在 G1 写清并确认规则/场景口径。
12. `run_part1_course.py` pause/resume 后跳过当前 policy step 剩余 substep 的正式链路缺口，需在正式 runner 前修。
