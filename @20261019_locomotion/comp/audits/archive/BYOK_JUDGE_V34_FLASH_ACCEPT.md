verdict：**CONCERN**  
- **Judge 代码层未发现新的 scorer 假成功/误判失败 blocker**（砂砾坑、限高杆核心语义与 conformance 基本一致）。
- **但存在 G1 证据链/规则文案 blocker 类问题**：`CONTRACT.md` 恢复语义自相矛盾、`G1_SELFCHECK.md` 与 `HASHES.json` 数量不一致、`STATUS.md` 明显过期；另有诊断起点/诊断 gravel 路线与 judge 合法进入语义不一致的问题。  
- 因此本轮不建议给 **PASS**，但可判定为 **CONCERN，无 scorer-code blocker**。

---

## 1. 砂砾碎木坑

### 几何
`assets/terrain/part1/part1_eval_scene_v2.xml`：
- `gravel_pit_a`：pos=(4.8361,-12.5)，size=(0.5,0.5)，即 x∈[4.3361,5.3361]，y∈[-13,-12]。
- `gravel_pit_b`：pos=(5.8361,-12.0)，size=(0.5,1.0)，即 x∈[5.3361,6.3361]，y∈[-13,-11]。

并集是 L 形：2 m×2 m 方块减去左上 1 m×1 m 缺口。合法 1 m 短边为：
- 西短边：x=4.3361，y∈[-13,-12]；
- 北短边：y=-11，x∈[5.3361,6.3361]。
南边 y=-13、东边 x=6.3361 是 2 m 长边。

`comp_part1_judge.py::GravelPit` 的常量：
- `GRAVEL_X_LO/MID/HI = 4.3361/5.3361/6.3361`
- `GRAVEL_Y_LO/MID/HI = -13.0/-12.0/-11.0`
- `GRAVEL_SHORT_EDGES = {"west": ..., "north": ...}`
- `GRAVEL_BOUNDARY` 包含 `south_long`、`east_long`、`west_short`、`notch_h`、`notch_v`、`north_short`

与 XML 一致。

### 判定逻辑
`GravelPit._track_footprint()`：
- 用 base xy 检测进入/离开 L 形坑体的边界穿越；
- 进入时：必须只穿越一个短边且没有其它边界，否则 `illegal_entry`；
- 离开时：必须只穿越一个短边，且与进入短边不同，否则 `illegal_exit`；
- 重复进入/离开也置非法。

`GravelPit._check_exit()` 要求：
- 无 `illegal_entry/illegal_exit`；
- `{entry, exit} == {"west","north"}`；
- `gravel_hits >= 3`。

`_Obstacle.update()` 在 `_check_exit` 成功后仍检查：
- `ok and self.ground_fail and not self.supported` → `insufficient_obstacle_support`，防止只擦碰表面但未真正支撑。

`GravelPit._ground_penalty_active()`：
- 未合法离开前，支持后 ≥2 足触地会失败；
- `exit_edge` 已合法设置后返回 False，即合法离开后落地不判罚。

### Conformance 覆盖
`comp_judge_conformance.py::test_gravel_short_edges_and_long_edge` 覆盖：
- 合法 L 路径 west→north success；
- 合法离开后 2 足落地仍 success；
- 坑中段 2 足触地 fail；
- 南长边进入 fail `illegal_entry`；
- 西短边进、东长边出 fail `illegal_exit`；
- 东长边进入 fail `illegal_entry`。

**结论：规则语义与 judge 实现满足契约。**  
残余：
- 使用 base footprint 代理，不是真实足端/坑体几何；
- 边界顶点附近精确穿越有退化风险；
- 真实坑体/碎木未 recut，C1 真实 rollout 因策略未进入坑体（如 cal-003 final base x=4.169 < 4.3361），没有真实 L 成功视频，成功侧仍主要靠 rulecard/conformance。

---

## 2. 限高杆

`comp_part1_judge.py::HeightBar`：
- `BAR_OPENING_X = (5.2, 6.2)`，对应 XML 两柱 x=5.2/6.2、杆体 y=-9、初始 z≈0.325。
- `_on_sample()`：只有当 base 穿越 y=-9、且 x 在门洞区间内时，才累计 `cross_valid`，并记录 `cross_max_z` 与 `cross_bar_z`。
- `_check_exit()` 要求：
  - 入口/出口为 ymin/ymax 且相反；
  - `cross_valid >= 1`；
  - 有初始 bar 状态；
  - 未检测到落杆；
  - `cross_max_z <= cross_bar_z`，否则 `not_under_bar`。
- `_pre_sample()` 与 `Part1JudgeV2.update()` 双重跟踪落杆，阈值 `BAR_DROP_THRESHOLD_M = 0.05`。

`comp_judge_conformance.py::test_height_bar_touch_drop_and_gate` 覆盖：
- 低姿态 `z=0.25`、`bar_z=0.325` 穿越 → success；
- 站立高度 `z=0.45` → fail `not_under_bar`；
- 杆下落 → fail；
- 入区前杆已落 → 不 success；
- 从门洞外侧绕过 → 不 success。

**结论：不是只看杆掉落，确实要求门洞下穿越；低姿态 success、站立高度 not_under_bar、落杆 fail 均有测试。**  
残余：
- “从杆下方穿过”仍用 **base z 代理**，没有全身/足端离地间隙检查；存在 base 低于杆但肢体高于杆的假成功风险。该点已在 G1 残余中承认，但 C1 后仍未关闭。
- 若场景在 judge 初始化前杆已处于低位，`bar_base_seen` 会以低位为基线，理论上不检测“此前已落”；当前 scene reset/check 使这条未在正式链路暴露，但仍是稳健性残余。

---

## 3. route 与诊断路线

### `config/part1-route.json` gravel 段
- `to_gravel` → (3.6,-12.5)，在西短边外；
- `cross_gravel_west` → (5.8,-12.5)，穿越西短边 x=4.3361、y=-12.5；
- `cross_gravel_north` → (5.8,-10.6)，穿越北短边 y=-11、x=5.8。

该段是合法 L 路径，与 `GravelPit` 语义一致。

### 诊断路线问题
`run_part1_judged_rollout_v2.py::SPECIAL_ROUTES["gravel_pit"]` 是开环命令：
- 3.0 s +x；
- 1.2 s yaw 0.75 rad/s；
- 3.0 s +x。

预期转角约 `0.75×1.2=0.9 rad≈51.6°`，不是 90°；且 C1 真实 rollout 最终 base 如 cal-003 为 x=4.169，尚未进入坑体。该诊断路线不能证明“合法 L 路径可跑通”，注释“legal L path”偏乐观。

更明显的诊断起点不一致：
- `TASKS["high_wall"]` 起点 (1.8,-7.8) 已在 `ZONES["high_wall"]` 的 y∈[-7.85,-6.15] 内；
- `TASKS["bridge_blocks"]` 起点 (1.8,0.0) 已在 x∈[1.25,6.3] 内；
- `TASKS["bridge_bands"]` 起点 (5.7,-3.5) 已在 y∈[-4.0,-0.8] 内。

这些起点导致 `_on_first_inside()` 观测不到合法进入侧，`entry_side_prev=None`。若未来策略完美向前通过：
- `TraversalBridge._check_exit()` 会返回 `illegal_entry`；
- `HighWall._check_exit()` 会返回 `illegal_entry`。

因此单障碍 diagnostic 对这些障碍**无法产生合法 success**。这不影响 `config/part1-route.json` 的整场 course route（其桥/高墙前有外部 staging 点），但会影响未来“补真实成功 rollout 重跑 C1”和 C2 单障碍成功评估。属新的正式链路缺口/残余。

---

## 4. C1 标定

- `records.jsonl`：cal-001…cal-092，共 92 条。
- `labels_template.csv`：92 条标签，覆盖 part1_obstacle、part2_level、rulecard、session_state。
- `C1_CALIBRATION_REPORT.md`：92/92 有标签，92/92 参与比较，一致率 100%。
- `LABELS_PROVENANCE.md` 诚实记录：
  - 56 条真实 rollout 为用户盲标；
  - 28 条 rulecard 与 8 条 session 不是盲标，是用户确认语义 + executor 补全；
  - 修复砂砾坑/限高杆后，未再请用户逐卡重看；
  - 真实成功 rollout 仍缺失。

因此：
- **92 条记录、labels、report、provenance 数量一致；标签来源限制被诚实记录。**
- C1 的“judge-human 100%”主要证明失败侧 + 规则语义确认，不构成成功路径独立盲测。这不是新 blocker，但必须作为 G1 残余。
- 未发现 judge-human 不一致条目；但 rulecard/session 的“一致”是弱证据。

---

## 5. 回归与证据链

### 通过项
- `comp_judge_conformance.py::main()` 列 13 组测试，与 `G1_SELFCHECK.md` 的 “13 groups” 一致。
- `comp_part1_course.py::run_self_test()`、`comp_part2_judge.py::run_self_test()`、`comp_score.py --self-test`、`comp_import_selftest.py` 在自检中均记录 OK。
- 四份产物 summary↔trials 数量：
  - part1-diag-v2：`attempts_used=8`，trials 8 条；超契约 3 次预算，但 manifest 标 diagnostic，`comp_score` 只 warning。
  - part2-diag-v2：high_platform/stairs/slope/high_wall=4，trench=3，plum=1，trials 条数匹配。
  - part2-official-diag：各类 attempts_used=4，trials 24 条匹配；trench/plum 用重复最高档补到 4 次，符合“每项最多 4 次”的诊断落盘。
  - part1-course-diag：attempts_used=3，trials 为 3 attempts × 8 obstacles，匹配。
- 三份演练：
  - pause_resume：3 attempts，recovery 不消耗，duration 113.56 排除暂停；
  - abort：3 skipped，duration 2.505，final_time=0；
  - pause_timeout：1 skipped，duration 0.5，final_time=0。
  与 `AttemptManager`/`Part1Course` 语义一致。

### 证据链/文档不一致（CONCERN 来源）
1. **`CONTRACT.md` 恢复语义自相矛盾**
   - `comp/CONTRACT.md` §1 写“整场 3 次尝试（开始/重试/恢复/跳过都消耗）”；
   - §5 Q1 表也写“开始/重试/恢复/跳过都消耗”；
   - 但 §4 写“恢复不额外消耗尝试”；
   - `CONTRACT.json.parts.part1.attempts.recovery_consumes_attempt=false` 且 Q1 resolution 也写恢复不消耗；
   - 用户已确认规则也是“恢复不消耗”。
   这是明确的规则文案 blocker 类问题，虽然 `AttemptManager` 实现正确。

2. **`HASHES.json` 与 `G1_SELFCHECK.md` 数量不一致**
   - `comp/audits/HASHES.json` 实际 objects 为 76：基础 OBJECTS + 19 个 level + 4 个 eval 产物 ×3 + extras + evidence；且包含 `extra_C1_CALIBRATION_REPORT`。
   - `G1_SELFCHECK.md` 命令块写 `wrote ... (76 objects)`，但 19:45 补充文字又写“HASHES 数量统一为 75”。同一文件内矛盾，且与 `HASHES.json` 实际 76 不一致。

3. **`comp/STATUS.md` 明显过期**
   - §0/§1 仍写 G1 FAIL、stage C1、Part2 evaluator 缺失、AttemptManager 未实现、calibration 为空；
   - §4.1 又记录 AttemptManager/Part2/C1 PASS/GLM provisional PASS。
   状态文档与当前终态不一致，会污染门禁证据链。

4. **`CONTRACT.md` §6 仍有旧资产**
   - 仍列 `assets/terrain/part1/judge_zones.yaml` “待补”；
   - 仍列 judge V1 历史条目；
   - 与 `G1_SELFCHECK.md` 中“已修：CONTRACT.md §6 移除 V1 judge 旧条目”的表述不一致（至少旧 judge_zones 仍残留）。

### 其他证据质量问题
- `comp_part2_judge.py::run_self_test()` 中 “lateral bypass” 用例复用了 plum 的 `e`，却传 `tags=("platform",)`；它失败是因为 plum 判据不满足，而不是实际测试 platform 横向绕行。该测试没有真正验证 platform lane bypass。
- `comp_import_part2_diag.py` 非 official 模式 `attempt_num = int(att.get("attempt_index") or i)`，每个 level 只有一次 run，因此同类 4 个 level 的 trials 都是 `attempt=1`，但 summary 的 `attempts_used=4`。数量校验不报错，但 attempt 编号语义弱。
- `run_part1_course.py::run_attempt()` 的 stable-stop 只在 `course.judge.report()["returned_to_start"]` 时启用；`returned_to_start` 只会在全 8 项满分后二次进入出发区时为真。若正式尝试未全满分但已回到出发区，计时不会执行稳定停表而直接 `route_complete` 结束。这是正式链路缺口，当前仅被 diagnostic 掩盖。

---

## 6. 结论

**verdict：CONCERN。**

**是否有 blocker：**
- **无 GravelPit / HeightBar / AttemptManager 的 scorer-code blocker。**
- **有 G1 证据链/规则文案 blocker 类问题**，至少：
  - `CONTRACT.md` §1/§5 Q1 的“恢复消耗”与 §4/CONTRACT.json/用户确认规则矛盾；
  - `HASHES.json` 76 与 `G1_SELFCHECK.md` “75”矛盾；
  - `STATUS.md` 过期且与 §4.1 冲突；
  - 单障碍 diagnostic 的 high_wall/bridge_blocks/bridge_bands 起点在 zone 内，未来真实成功 rollout 会被 `illegal_entry` 误杀；
  - gravel 单障碍 `SPECIAL_ROUTES` 开环转向/时长不能证明合法 L 路径。

**是否建议进入下一阶段（C2/轨迹训练）：**  
**yes（有条件）**。  
- C2/轨迹训练可继续，因为核心 judge 语义未发现新的 scorer-code blocker。
- 但在把单障碍 success 作为 C2 评估或补真实成功 C1 之前，必须先修 diagnostic 起点/路线；在最终 G1 PASS/对外分数前，必须修 `CONTRACT.md`、`G1_SELFCHECK.md`、`HASHES.json`、`STATUS.md` 的一致性。

**G1 必写残余：**
1. 砂砾坑真实坑体/碎木未 recut；judge 用 base footprint 代理；真实成功 rollout 缺失。
2. 限高杆 under-bar 用 base z 代理，无全身离地间隙/肢体高度检查。
3. Part2 官方能力场未逐档核对；`comp_part2_judge` 的 platform lateral bypass selftest 实际未覆盖。
4. 正式手动 3 次整场演练视频未补；course runner 为脚本化 diagnostic；stable-stop 只在 `returned_to_start` 时触发，未全满分返回场景未覆盖。
5. C1 的 28 rulecard + 8 session 非盲标，100% 一致率主要是语义确认；56 条真实 rollout 全失败，成功侧无真实盲测。
6. 单障碍 diagnostic 的 high_wall/bridge_blocks/bridge_bands 起点在 judge zone 内，未来成功 rollout 会被判 `illegal_entry`；gravel `SPECIAL_ROUTES` 开环路径未验证为合法 L。
7. `CONTRACT.md` Q1/§1 恢复语义、`HASHES` 数量、`STATUS.md`、`CONTRACT.md` §6 旧资产等文档一致性问题必须关闭后才能给 G1 PASS。
