verdict：**FAIL**  
blocker：**有**。B1 的落地门控在“已全足支撑后落地”方向上修对了，但仍留下/暴露一个假成功通道：**从未出现 `supported=True` 时，2 足以上触地不会被判罚**，而各障碍 `_check_exit` 又不要求 `supported`，因此可在障碍 zone 内的地面上行走、用单足蹭障碍表面 tag 累积证据后从对侧出口成功。  
是否建议进入下一阶段：**no**（先修 B1 门控与 route 证据链，再进 C1/C2）。

> artifact 未附行号；以下按 `文件::函数/代码段` 定位。

## 1. B1：离障落地门控

### 1.1 目标行为：部分成立

`comp_part1_judge.py::_Obstacle.update` 当前判罚条件为：

- `ground_fail and self._ground_penalty_active(xy, tags) and len(ground_feet) >= 2`

`_Obstacle._ground_penalty_active` 默认返回 `self.supported`；各障碍覆盖：

- `TraversalBridge._ground_penalty_active`：未 `supported` 直接 `False`；`bridge_hits>=3` 且两个平台 tag 都出现后关闭判罚。
- `GravelPit._ground_penalty_active`：未 `supported` 或 `gravel_hits<3` 时返回 `bool(supported)`；达到条件后按出口短边 0.35 m grace 关闭。
- `TStairs._ground_penalty_active`：未 `supported` 直接 `False`；`top` 且至少一条完整臂后关闭。
- `Slope._ground_penalty_active`：未 `supported` 直接 `False`；累计投影 ≥1 m 后关闭。

因此，**在机器人确实曾全足支撑于障碍面后**：

- 完成跨越后走下障碍/落地：合法，不再 `two_feet_ground`。  
- 中途真坠落：若尚未集齐完成证据，`_ground_penalty_active` 仍为 True，2 足触地仍失败。  
- `bridge_blocks`、`bridge_bands`、`gravel_pit`、`t_stairs`、`slope` 五类 `ground_fail` 均有覆盖；`height_bar`、`high_wall`、`slalom` 为 `ground_fail=False`，不受该门控影响。  
- conformance 已补：bridge_blocks/bridge_bands 的 landing 与 mid fall、gravel landing/mid-pit、t_stairs partial landing/early ground、slope landing。

### 1.2 但存在 scorer blocker：非 `supported` 路径的 2 足触地假成功

`_Obstacle.update` 中：

- 只有 `touched and not ground_feet` 时才置 `self.supported = True`；
- 只要机器人始终保留至少 1 只脚在地面，`supported` 就永远是 False；
- 各 `_ground_penalty_active` 在 `not supported` 时直接返回 False；
- 但 `_on_sample` 仍会累积 `bridge_hits/platforms/gravel_hits/arms/top/slope distance`；
- `TraversalBridge._check_exit`、`GravelPit._check_exit`、`TStairs._check_exit`、`Slope._check_exit` **都不要求 `supported == True`**。

可构造的假成功路径：

- 机器人在 `bridge_blocks` zone 内沿地面 y≈0.7 行走；
- 单足周期性蹭到 platform_left、bridge_blocks_0..4、platform_right 的顶面 tag；
- 其他足仍在地面，`ground_feet` 每帧可能 ≥2；
- 因 `supported=False`，`_ground_penalty_active=False`，不触发 `two_feet_ground`；
- 最终 `bridge_hits>=3`、`platforms>=2`，从 xmin 进、xmax 出，`_check_exit` 判 success。

同理适用于：

- `gravel_pit`：单足蹭 gravel tag、地面行走、从短边出；
- `t_stairs`：单足蹭 step:s:1..3 + top，地面行走，`_check_exit` 只看 top/完整臂/无缺级；
- `slope`：单足蹭 slope tag，沿 y 方向移动累积投影，地面行走。

这违反“跨越过程中任何瞬间 ≥2 足触地即失败”和“实际跨越”的语义。conformance 的 `test_approach_ground_is_not_failure` 只测“无 tag 的进场地面”，`test_bridge_ground_and_success` 的 mid-gap 用例已先有平台且无地面足，`supported=True`，覆盖不到“有 tag 但从未全足支撑”的路径。

**结论：B1 的“落地合法/真坠落失败”在 supported 路径上 PASS，但门控整体仍是 blocker。**  
根因是把 `supported`（无脚在地面）当作判罚启动条件；规则只要求“跨越中 <2 足触地”，不要求“先全足离地”。应在首次实际接触障碍后即启用地面判罚，完成证据后再关闭。

## 2. B2：绕杆拐角

**PASS。**

`Slalom._on_sample` 已改为：

- 用 `corner_visits` 记录每次进入拐角圆时的 `len(ev["order"])`；
- `SLALOM_CORNER_RADIUS_M = 0.30`；
- `_check_immediate` / `_check_exit` 用 `expected_corner_after in ev["corner_visits"]`，A=3、B=2。

conformance 覆盖：

- `early_then_legal`：先 count=2 扫过拐角，再 count=3 合法经过，成功；
- `early_corner`：只有 count=2，不通过；
- `out_of_order`：漏 post0，`missing_posts`；
- 缺拐角：`missing_corner_checkpoint`；
- 早终点：`no_end_area` / `missing_posts`。

**提前扫过拐角不再误杀合法路径；乱序/缺拐角仍拒绝。无回归。**

## 3. B3 / B5

### B3：T 台阶“另一臂缺级”

**PASS。**

`TStairs._check_exit` 已加：

- `if self._has_incomplete_arm(): return False, "incomplete_step_history"`

`_has_incomplete_arm` 对任一 `levels` 非空且 `< {1,2,3}` 的臂返回 True。  
conformance 的 `skipped_level_plus_complete_other`（n 臂缺 n:2、s 臂完整+top）断言 `not_success`，正确拒绝。  
同时保留：两臂完整=100，s 单臂=50，n/e 单臂=33，partial 可升级 full。

### B5：Part2 hold 连续性

**PASS。**

`comp_part2_judge.Part2JudgeV2.update` 当前：

- `if cond: self.held += dt`；
- `else: self.held = 0.0`。

`run_self_test` 的 `interrupted`（2.5→1.0→2.5）断言 fail，`continuous` 断言 success。  
断续满足条件不再成功。

## 4. route

### slope：PASS

`config/part1-route.json`：

- `to_slope` target `(5.2,-6.3)`；
- `cross_slope` target `(5.2,-4.2)`；
- 跨度 2.1 m，沿 y 轴；`Slope._on_sample` 只累计坡面接触期间的 `abs(y-last_y)`，与判分轴一致。

### slalom：拐角 PASS，但整段 route 仍不能合法完成 S

- `slalom_corner` target `(1.55,-12.75)` 正是拐角圆心，半径 0.30 m 可命中；**拐角必达区 PASS**。
- 但 `slalom_posts` 从 `(1.8,-10.1)` 到 `(1.8,-12.6)` 是直线穿过杆列，未给出左右交替 waypoint；`Slalom._on_sample` 计算 `sides` 时，沿杆中心线行走的 side 叉积为 0 或不交替；`_check_exit` 要求 `all(a*b < 0 ...)`，因此 `not_s_shaped_sides` 失败。  
  **route 层仍不能产出合法绕杆成功，属于正式链路前必须清理的 CONCERN。**

### bridge_blocks：PASS（按实际 route 文件）

实际 `config/part1-route.json`：

- `to_bridge_blocks` target `(0.8,0.0)`，从西侧 zone 外进入；
- `cross_bridge_blocks` target `(6.5,0.0)`，从 xmin 进、xmax 出；
- `leave_bridge_blocks_east` target `(6.6,-1.1)`，保持 x>xmax。

`TraversalBridge._check_exit` 要求 `side == _opposite(entry)`，此方向满足。  
V23 文本里写的 `(6.0,0.0)` 与当前 artifact 不一致；以当前 route 文件为准是 PASS。

### bridge_bands：FAIL（route 错配仍在，且方向与 V23 判断不同）

当前 route：

- 上一段 `leave_bridge_blocks_east` target `(6.6,-1.1)`；
- `to_bridge_bands` target `(5.7,-3.6)`；
- `cross_bridge_bands` target `(5.7,-1.0)`；
- `to_gravel` target `(5.0,-13.4)`。

几何推演：

- `(6.6,-1.1) → (5.7,-3.6)` 先在 xmax=6.3 处进入 `bridge_bands` zone，y≈-1.93，**entry=xmax**；
- `cross_bridge_bands` 到 `(5.7,-1.0)` 仍在 zone 内，未从 ymax 出去；
- `to_gravel` 向南走，在 ymin=-4.0 处离开，**exit=ymin**；
- `TraversalBridge._check_exit` 对 entry=xmax 期望 exit=xmin，实际 ymin → `wrong_exit_side`。

因此 **bridge_bands 在理想 waypoint 跟踪下仍会被 judge 正确拒绝**。这不是 judge 误判，而是 route 方向错配；V23 把 entry 判成 ymax 的结论与当前实际 route 不符。属于 C2 前必须清理的正式链路缺口。

### 其余

- `height_bar` ideal route：`to_height_bar (5.7,-10.2)` 在 zone 南侧，`cross_height_bar (5.7,-8.2)` 从 ymin 进、ymax 出，x=5.7 在门洞 `[5.2,6.2]` 内，语义 PASS。course 证据中的 `wrong_exit_side` 更像实际策略未到达南侧起点/轨迹抖动导致，不是 gate 语义错误；但说明 route 对跟踪误差不鲁棒。
- `high_wall` route 本身没有抬升 waypoint，flat 策略无法完成 `WALL_CLIMB_Z`；这是策略/演练限制，不是 route 语义错误。
- `t_stairs`、`gravel` 按当前 waypoint 方向可进/出，未发现新的 judge 侧方向错配。

## 5. 回归与证据链

### conformance 13 组

`comp_judge_conformance.py::main` 仍列 13 组；B1/B2/B3/B5 对应用例均存在。  
但本轮 B1 新发现的“有 tag、无 supported、地面 2 足以上”路径**未覆盖**；因此“13 组全绿”不能证明 B1 门控完整。

### self-test

- `comp_part1_course.run_self_test`：900 分、pause 排除、partial 不触发 return、recovery pose violation、StableStopTracker 物理 dt 均在。
- `comp_part2_judge.run_self_test`：B5 interrupted/continuous、lateral bypass、gap no_cross、wall 无墙接触、plum 地面伪成功、bool 只认 1、floor/端点 0 均在。
- `comp_score.run_self_test`：skipped 正分排除、错误 final_time、tamper hash、非法 Part2 档位、空 hash/level 条目、重复 trial_id 均在。
- `comp_import_selftest.py`：全 skipped 场景 0/0/无 evidence。
- `check_part1_scene_v2.py`：空场景横梁静置 <1 cm。

静态复核未发现 B2/B3/B5 回归；但 B1 新门控路径未测。

### 四份产物 summary↔trials

- `flat-ft-2500-part1-diag-v2`：8 trials / summary 8 障碍 fail；attempts_used=8 为诊断值。
- `flat-ft-2500-part2-diag-v2`：20 trials，attempts_used 4/4/4/4/3/1 与 summary 一致。
- `flat-ft-2500-part2-official-diag`：24 trials，每 category 4 次，attempt 1–4 编号正确；summary attempts_used 一致。
- `flat-ft-2500-part1-course-diag`：24 trials（3×8），summary final_time 95.859999… 与 trial 95.86 在 `comp_score` 1e-6 容差内一致；未触发 return bonus。

### HASHES

`comp/audits/HASHES.json` 当前共 **66 objects**，覆盖 contract、protocol、judge/runner/importer、scene、19 个 level XML、四份产物 manifest/trials/summary、3 份演练证据、events 配置、selftest 等；与 payload 中给定 sha256 逐项一致。  
仍为 `audited=false / verdict=pending`，这是 G1 前预期状态，但 G1 报告前必须更新。  
存在 minor：`eval_part1_diag` / `eval_flat-ft-2500-part1-diag-v2_summary` 等指向同一文件，属冗余键；不破坏校验。

## 6. 新问题

1. **B1 非 supported 地面接触假成功（blocker）**  
   `_Obstacle.update` 用 `supported` 启动地面判罚；`supported` 要求 `not ground_feet`（零足在地面），而规则只要求 `<2 足触地`。各 `_check_exit` 又不要求 `supported`，导致单足蹭 tag、其他足在地面行走可累积证据并成功。影响 bridge_blocks/bridge_bands/gravel_pit/t_stairs/slope。  
   这是本轮最重要的新发现，且是 scorer blocker。

2. **route bridge_bands 方向错配（CONCERN，正式链路缺口）**  
   当前 route 从 xmax 进入、从 ymin 离开，`TraversalBridge._check_exit` 期望 xmax→xmin，判 `wrong_exit_side`。V23 的 bridge_bands PASS 结论与当前 route 文件不符。

3. **route slalom 只有拐角 waypoint，没有合法 S 形（CONCERN）**  
   `slalom_posts` 直线穿杆列，`sides` 不交替；即使完美跟踪也会 `not_s_shaped_sides`。拐角必达区本身 PASS，但整段 slalom route 不可得分。

4. **course 诊断中 height_bar `wrong_exit_side`**  
   不是 gate 语义错误，但说明 `to_height_bar` 的南侧前置 waypoint 对策略跟踪误差不鲁棒；正式 route 需复核进入方向。

5. **minor**  
   - `comp_part2_judge._hold_ok` 仍是 dead code（`update` 已内联清零）。
   - `comp_score.py` 顶部重复 `import tempfile`。
   - `comp/CONTRACT.md §6` 仍列 V1 场景/旧 judge，资产表陈旧。
   - `comp/eval/_protocol.md` 仍为 draft。
   - HASHES 冗余键。

## 7. 结论

**verdict：FAIL**  
**blocker：有**，B1 的 `supported` 门控仍允许“有障碍 tag 但从未全足支撑”的 2 足以上地面接触假成功；`_check_exit` 未要求 `supported`，conformance 未覆盖该路径。  
**是否建议进入 C1/C2：no**。  
C1 人工标定可以等 judge 语义冻结后再做；C2 基线更不能现在跑，否则会叠加 B1 假成功通道与 route bridge_bands/slalom 错配。建议先修：

1. B1 门控改为“首次实际接触后即启用地面判罚，完成证据后再关闭”，并补“地面行走+单足蹭 tag”反例到 conformance；
2. 修 `bridge_bands` route 进入/出口方向；
3. 补 `slalom` 合法 S 形 waypoint；
4. 重跑 conformance 13 组、course/Part2/score/importer self-test、四份产物与三份演练；
5. 刷新 HASHES 后再做 delta 复验。

## G1 必写残余

- 砂砾坑真实“坑+碎木”几何未 recut，当前仍是凸起盒代理；recut 后 B1 的 gravel 出口 0.35 m grace 必须按真实几何复核。
- Part2 官方能力场未逐档交叉核对；official 重复最高档在确定性策略下统计意义有限。
- soft-reset 阈值与相邻 zone 重叠仍是启发式。
- T 台阶 s/n/e ↔ 上/下映射、障碍级跳过是否消耗整场尝试、pause_timeout 120 s 自定协议常量需书面确认。
- 正式手动/操作手 3 次整场演练未在真实赛程完成；当前为脚本化诊断与 pause/resume/abort/pause_timeout 演练。
- B4/B6/B7 保守向判罚留待 C1 标定裁决：限高杆“从下方”未校验、Part2 高墙必须墙接触、沟壑 lane ±0.7 偏保守。
- Part1 单障碍诊断 importer 的 per-obstacle 汇总口径仅用于诊断；正式以 course importer 为准。
- `comp/eval/_protocol.md` 仍为 draft，`HASHES.json` 仍 `audited=false / verdict=pending`。
- 本轮新增必写：B1 `supported` 门控的“非全足支撑地面接触”假成功通道；route bridge_bands 方向错配；route slalom 缺合法 S 形 waypoint。
