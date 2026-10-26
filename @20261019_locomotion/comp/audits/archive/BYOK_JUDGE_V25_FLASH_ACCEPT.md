verdict：**FAIL**  
blocker：**有**。B1 的“非 `supported` 地面蹭 tag 假成功”在当前 `comp_part1_judge.py`（sha256=`127ddfcd…`）中仍成立；V24 指出的 scorer blocker 没有被 artifact 代码真正闭环。  
是否建议进入下一阶段（C1 / C2）：**no**。C1 也会被未冻结的 judge 语义污染；C2 更不应现在跑。

> artifact 未附行号，以下按 `文件::函数/代码段` 定位，不臆造行号。

## 1. B1：离障落地门控

### 1.1 `supported` 路径上的“落地合法 / 中途坠落失败”基本成立
`comp_part1_judge.py::_Obstacle.update` 中，`supported` 只在“碰到障碍 tag 且没有任何足在地面”时置 True；随后地面判罚由 `_ground_penalty_active` 控制。五个 `ground_fail` 障碍 ID 均有覆盖：

- `TraversalBridge._ground_penalty_active`：`bridge_hits>=3` 且两个平台 tag 命中后关闭判罚；
- `GravelPit._ground_penalty_active`：`gravel_hits>=3` 且接近出口短边 0.35 m 后关闭；
- `TStairs._ground_penalty_active`：`top` + 至少一条完整臂后关闭；
- `Slope._ground_penalty_active`：累计投影 >=1 m 后关闭。

因此在“机器人确实曾在障碍面全足支撑”的路径上，完成跨越后走下障碍/落地不再触发 `two_feet_ground`；中途真坠落在完成证据不足时仍会失败。bridge_blocks、bridge_bands、gravel、t_stairs 有对应 landing/mid-fall conformance；slope 有 landing，但没有明确的“supported 后、距离不足前双足触地”的 mid-fall 用例，覆盖不完整。

### 1.2 但 blocker 仍在：退出成功分支没有 `supported` 门控
关键问题在 `_Obstacle.update` 的两个分支：

- `inside` 分支里的 `_check_immediate()` 成功路径有 `if ok and self.ground_fail and not self.supported: _fail("insufficient_obstacle_support")`；
- 但绝大多数 ground_fail 障碍是在离开 zone 时走 `elif self.prev_in_zone and ...: ok, reason = self._check_exit(...)`，该分支的 `if ok:` 直接置 `success`，**没有检查 `self.supported`**。

同时，`TraversalBridge._check_exit`、`GravelPit._check_exit`、`TStairs._check_exit`、`Slope._check_exit` 都只检查入口/出口方向、命中次数、平台/臂/距离等证据，**都不要求 `supported == True`**。

而 `_ground_penalty_active` 在 `not self.supported` 时直接返回 False。于是可构造：

1. 从 zone 外合法进入，先有外部样本使 `entry_side_prev` 合法；
2. 机器人始终保留至少一只脚在地面，`supported` 永远为 False；
3. 另一只脚周期性蹭 `platform_left` / `bridge` / `gravel` / `step:*` / `top` / `slope` 等顶面 tag；
4. 因 `supported=False`，`_ground_penalty_active=False`，不会触发 `two_feet_ground`；
5. 但 `_on_sample` 仍会累计 `bridge_hits/platforms/gravel_hits/arms/top/slope distance`；
6. 从对侧出口离开时，`_check_exit` 返回成功。

这适用于 bridge_blocks、bridge_bands、gravel_pit、t_stairs、slope，仍是 **scorer blocker**。  
`comp_judge_conformance.py::test_bridge_ground_and_success` 的 graze 用例没有先给一个 zone 外样本，导致 `entry_side_prev=None`，最后以 `illegal_entry` 失败；它并没有测到“合法入口 + 单足蹭 tag + 地面行走”的路径，因此 13 组全绿不能证明 B1 完整。

**B1 结论：FAIL。**  
“合法 supported 路径落地”基本对；五个 ground_fail ID 都有门控函数；但门控整体不完整，非 `supported` 路径仍可假成功，且 slope mid-fall 用例缺失。

## 2. B2：绕杆拐角

**PASS。**  
`Slalom._on_sample` 已改为 `corner_visits` 记录每次进入拐角圆时的杆数；`_check_immediate` / `_check_exit` 要求期望时序 `A=3 / B=2` 出现在访问集合中。半径 `SLALOM_CORNER_RADIUS_M=0.30`，与 post2 半径 0.35 区分。  
conformance 中 `early_then_legal` 成功、`early_corner` 失败、`out_of_order` 与缺拐角均拒绝。提前扫过拐角不再误杀后续合法路径，乱序/缺拐角仍拒绝，未发现回归。

## 3. B3 / B5

**B3：PASS。**  
`TStairs._check_exit` 已加 `_has_incomplete_arm()`：任一臂 `levels` 非空且 `< {1,2,3}` 即 `incomplete_step_history` 失败。  
conformance 的 `skipped_level_plus_complete_other`（n 臂缺 n:2、s 臂完整）断言不成功，正确拒绝。同时保留两臂完整=100、s 单臂=50、n/e 单臂=33、partial 可升级 full。

**B5：PASS。**  
`Part2JudgeV2.update` 中 `cond` 为假时 `self.held = 0.0`，断续满足条件不再累计成功。`run_self_test` 的 `interrupted` / `continuous` 用例覆盖到位。`_hold_ok` 仍是 dead code，但属 minor。

## 4. route

- **slope：PASS。** `config/part1-route.json` 的 `to_slope` 为 `(5.2,-6.3)`，`cross_slope` 为 `(5.2,-4.2)`，跨度 2.1 m 沿 y；`Slope._on_sample` 只累计坡面接触期间的 `|Δy|`，判分轴匹配。
- **slalom：PASS。** route 已有 `(1.9,-10.5) / (1.7,-11.5) / (1.9,-12.5)` 交替 waypoint，再经 `slalom_corner (1.55,-12.75)`，拐角半径 0.30 可命中；S 形侧向判据不再明显退化。
- **bridge_blocks：PASS（条件性）。** `to_bridge_blocks (0.8,0.0)` 从西侧进入，`cross_bridge_blocks (6.5,0.0)` 从 xmin 进、xmax 出，`leave_bridge_blocks_east (6.6,-1.1)` 保持 x 在外；`TraversalBridge._check_exit` 的 opposite-side 条件满足。前提仍是 B1 的 `supported` 假成功问题不影响实际路径。
- **bridge_bands：FAIL（route 错配仍在）。** 上一段 `leave_bridge_blocks_east (6.6,-1.1)` 到 `to_bridge_bands (5.7,-3.6)`，实际从 **xmax** 进入；`cross_bridge_bands (5.7,-0.5)` 从 **ymax** 离开。`TraversalBridge._check_exit` 对 `entry=xmax` 期望 `exit=xmin`，因此即使理想 waypoint 跟踪也会 `wrong_exit_side`。当前 route 仍不能产出合法 bridge_bands 成功。
- height_bar / high_wall / gravel / t_stairs route 方向未发现新的 judge 侧方向错配；height_bar 的失败更像策略跟踪问题，不是 gate 语义错误。

## 5. 回归与证据链

### conformance 与 self-test
- `comp_judge_conformance.py::main` 仍列 13 组；B2/B3/B5 对应用例存在。
- `comp_part1_course.run_self_test` 覆盖 900 分、暂停排除、partial 不触发 return、recovery pose violation、StableStopTracker 物理 dt。
- `comp_part2_judge.run_self_test` 覆盖 B5 interrupted/continuous、lateral bypass、gap no_cross、wall 无墙接触、plum 地面伪成功、bool 只认 1、floor/端点 0。
- `comp_score.run_self_test` 覆盖 skipped、final_time、hash tamper、非法 Part2 档位、空 level 条目、重复 trial_id。
- `comp_import_selftest.py` 覆盖全 skipped 导入；`check_part1_scene_v2.py` 覆盖横梁静置稳定。
- 但 artifact 未附实际 stdout，以上只能静态确认“用例存在”；且 B1 合法入口 graze 防例缺失，13 组通过不能证明 B1。

### 四份产物 summary↔trials
- `flat-ft-2500-part1-diag-v2`：8 trials，summary 8 个障碍 fail，一致。
- `flat-ft-2500-part2-diag-v2`：20 trials；summary attempts_used 4/4/4/4/3/1 与 trials 计数一致。
- `flat-ft-2500-part2-official-diag`：24 trials，每 category 4 次，attempt 1–4 编号正确，summary attempts_used 一致。
- `flat-ft-2500-part1-course-diag`：24 trials（3×8）；summary `final_time_s=104.23999999997723` 与 trial 104.24 在 `comp_score` 1e-6 容差内一致。
- summary↔trials 本身基本一致。

### HASHES 与 manifest 内部证据链
`comp/audits/HASHES.json` 对文件对象的 sha256 基本匹配，当前 judge 记录为 `127ddfcd…`。但发现正式证据链不一致：

- `comp/eval/flat-ft-2500-part1-diag-v2/manifest.json` 的 `judge.file_hashes` 仍记录 `comp_part1_judge.py = bec8ff07…`；
- `flat-ft-2500-part2-diag-v2`、`flat-ft-2500-part2-official-diag` 的 manifest 也仍记录 `bec8ff07…`；
- 当前 `comp_part1_judge.py` 实际是 `127ddfcd…`，HASHES 也记录 `127ddfcd…`；
- `flat-ft-2500-part1-course-diag` manifest 用的是正确的 `127ddfcd…`。

`comp_score.py::validate_external_evidence` 的 `_check_hash` 对“manifest 记录 hash 与实际文件 hash 不一致”是无条件 error，即使 manifest 是 diagnostic。因此 part1-diag-v2、part2-diag-v2、part2-official-diag 在机器复核时会因 judge hash 过期而 invalid/diagnostic 不成立。这说明“四份产物已按最新 judge 重生成”的声明未被 artifact 支持，至少不是全部产物。

HASHES 仍为 `audited=false / verdict=pending`，这是 G1 前状态，但最终必须更新；HASHES 还有重复键/冗余键等 minor，不影响主结论。

## 6. 新问题

1. **B1 非 `supported` 假成功仍是 blocker。**  
   `_Obstacle.update` 只在 `_check_immediate` 成功分支检查 `not supported`；退出成功分支 `_check_exit` 不检查，且五个 ground_fail 的 `_check_exit` 均不要求 `supported`。合法入口 + 单足蹭 tag + 其他足地面行走可累计证据并从对侧成功。

2. **conformance 的 graze 反例不覆盖合法入口路径。**  
   `test_bridge_ground_and_success` 的 graze 没有 zone 外前置样本，失败原因是 `illegal_entry`，不是 `insufficient_obstacle_support`；因此没有防住上述 blocker。

3. **route bridge_bands 方向仍错配。**  
   `to_bridge_bands` 实际从 xmax 进入，`cross_bridge_bands` 从 ymax 离开，judge 期望 xmax→xmin，理想跟踪也会 `wrong_exit_side`。

4. **产物 manifest 的 judge hash 过期。**  
   part1-diag-v2/part2-diag-v2/part2-official-diag 仍引用 `bec8ff…`，当前 judge 为 `127ddf…`，证据链与当前代码不一致。

5. **slope mid-fall 证据缺失。**  
   slope 有 landing 用例，但没有“supported 后、累计距离不足前双足触地仍失败”的明确 conformance 反例。

6. **minor：** `comp_part2_judge._hold_ok` 仍为 dead code；`comp_score.py` 顶部有重复 `import tempfile`；HASHES 存在重复 summary 键；`comp/CONTRACT.md §6` 资产表仍列旧 V1 资产。

## 7. 结论

**verdict：FAIL**  
**blocker：有。** B1 的 `supported` 门控未覆盖退出成功路径，V24 指出的“非全足支撑地面蹭 tag 假成功”仍存在；这直接违反“实际跨越/任何瞬间 >=2 足触地失败”的语义。  
B2/B3/B5 代码层 PASS；slope/slalom route 基本 PASS；bridge_blocks route PASS；bridge_bands route 仍 FAIL。  
证据链 summary↔trials 基本一致，但三份产物 manifest 的 judge hash 过期，不能作为当前 judge 的完整证据。

**是否建议进入下一阶段：no。**  
先修 B1 退出成功分支的 `supported` 门控、补“合法入口 + 单足蹭 tag + 地面行走”的反例、修 bridge_bands route 方向、刷新三份产物 manifest 的 judge hash，并补 slope mid-fall 用例；然后重跑 conformance 13 组、各 self-test、四份产物与演练证据，再刷新 HASHES 做 delta 复验。

## 8. G1 必写残余

1. 砂砾坑真实“坑+碎木”几何未 recut；当前仍是凸起盒代理。recut 后必须复核 gravel 出口 0.35 m grace。
2. Part2 官方能力场未逐档交叉核对；本地为同种类参数化 level；official 重复最高档在确定性策略下统计意义有限；固定梯子策略可能低估边界能力。
3. soft-reset 阈值与相邻 zone 重叠仍是启发式；真实整场顺序通过时影响有限，但需保留说明。
4. T 台阶 s/n/e ↔ 上/下映射、障碍级跳过是否消耗整场尝试、pause_timeout 120 s 自定协议常量，仍需书面确认。
5. 正式手动/操作手 3 次整场演练未在真实赛程完成；当前只有脚本化诊断与 pause/resume、abort、pause_timeout 演练。
6. B4/B6/B7 保守向判罚留待 C1 标定裁决：限高杆未校验“从下方”、Part2 高墙必须墙接触、沟壑 lane ±0.7 偏保守。
7. Part1 单障碍诊断 importer 的 per-obstacle 汇总口径仅用于诊断；正式以 course importer 为准。
8. `comp/eval/_protocol.md` 仍为 draft，未冻结正式 `protocol_version`；HASHES 仍 `audited=false / verdict=pending`。
9. 跨 attempt 模拟器时钟重置后，事件时间线不能全局排序。
10. Part2 稳定性 ≥100 次、目标 0 失败未执行；`comp/eval/_calibration/` 人工标定集仍为空。
11. **本轮新增必写：B1 非 `supported` 地面接触假成功；conformance 合法入口 graze 用例缺失；slope mid-fall 证据缺失。**
12. **本轮新增必写：route bridge_bands 入口/出口方向错配。**
13. **本轮新增必写：part1-diag-v2、part2-diag-v2、part2-official-diag 三份 manifest 的 judge hash 过期，需重生成并刷新 HASHES。**
