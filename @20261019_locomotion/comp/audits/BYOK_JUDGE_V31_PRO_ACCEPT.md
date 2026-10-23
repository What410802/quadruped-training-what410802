## 结论

**verdict：CONCERN**  
**blocker：无**  
**是否建议进入下一阶段：yes（C1 可进；C2 若复用当前脚本 route，需先处理 `height_bar: wrong_exit_side`，或明确该 route 为非计分诊断链路）**

本次基于给定源码、conformance、四份产物、三份演练证据与 `HASHES.json` 做静态独立复核，未附本轮 stdout，因此“通过”指代码路径与证据链静态一致，不构成实际执行日志的形式证明。

---

## 1. B1：离障落地门控

结论：**主语义通过**。五个 `ground_fail` 障碍均已覆盖，不是四个。

判定位置：

- `comp_part1_judge.py::_Obstacle.update`  
  在 `inside` 分支和退出成功分支都保留双侧门控：
  - `inside` 成功分支：`if ok and self.ground_fail and not self.supported: _fail("insufficient_obstacle_support")`
  - `elif self.prev_in_zone` 退出成功分支同样有该检查。

  `two_feet_ground` 判罚在 `_on_sample` 之前触发，但各障碍通过 `_ground_penalty_active` 在“完成跨越证据后”关闭，落地不再被误判。

逐障碍：

| 障碍 | 关闭门控 | 判罚保留 | 覆盖 |
|---|---|---|---|
| `bridge_blocks` / `bridge_bands` | `TraversalBridge._ground_penalty_active`：`bridge_hits>=3` 且两个 platform tag 命中后关闭 | 桥面中段双足触地仍失败 | conformance 有 landing 与 mid-fall |
| `gravel_pit` | `GravelPit._ground_penalty_active`：`gravel_hits>=3` 后，距出口短边 `EXIT_GRACE_M=0.35` 内关闭 | 坑中段双足触地仍失败 | 有 legal landing 与 mid-pit |
| `t_stairs` | `TStairs._ground_penalty_active`：`top + 至少一条完整臂` 后关闭 | top/完整臂证据未完成前双足触地仍失败 | 有 partial landing 与 early_ground |
| `slope` | `Slope._ground_penalty_active`：累计 y 投影 `>=1.0 m` 后关闭 | 距离 <1 m 前的双足触地仍失败 | 有 landing 与 mid-slope fall |

反伪成功路径也存在：`insufficient_obstacle_support` 覆盖“地面行走 + 单足蹭障碍 tag”的情况；conformance 中 `bridge_blocks` graze 反例已覆盖。

补充一个边界风险（非本轮 blocker）：`_ground_penalty_active` 在 `_on_sample` 之前执行，若某条合法路径第一次触达远端平台 tag 时同帧已有 2 只脚在地面，可能仍判失败。现有 conformance 通过“远端平台无地面样本先到、下一采样再落地”规避，真实物理步态通常也会先有平台接触帧。建议 C1 标定集补一个“同帧首次远端平台 tag + 2 ground feet”的对抗用例确认。

---

## 2. B2：绕杆拐角与乱序

结论：**通过**。

- `comp_part1_judge.py::Slalom._on_sample` 不再用单次 `corner_after` 锁存，而是维护 `corner_visits` 列表，记录每次进入拐角圆时的 `len(order)`。
- `_check_immediate` 与 `_check_exit` 都要求 `expected_corner_after in corner_visits`，因此提前扫过拐角后仍可合法通过。
- `SLALOM_CORNER_RADIUS_M = 0.30`，能区分 post2 的 0.35 m 圈。
- `early_posts` 记录后期杆的提前到访；`_check_exit` 要求 `early_posts` 为空，否则 `post_out_of_order`，故乱序/未来杆提前触碰仍拒绝。

conformance 已覆盖：

- `early_then_legal`：提前扫拐角后再合法通过；
- `early_corner`：拐角时序仍错时拒绝；
- `early_future_post`：提前触碰未来杆后补全顺序仍失败；
- 缺拐角由 `missing_corner_checkpoint` 拒绝。

**minor**：judge 拐角半径 0.30 m 与场景显示圆半径 0.5 m 不一致；合法路径若只走显示圆 0.30–0.50 m 外缘会被判缺拐角。当前 route 走圆心不受影响，建议 C1 标定时定口径。

---

## 3. B3 / B5

### B3：T 台阶“另一臂缺级 + 本臂完整”

结论：**通过**。

- `TStairs._has_incomplete_arm()` 对任一臂 `levels` 非空且 `< {1,2,3}` 返回 True。
- `TStairs._check_exit()` 在 `top` 存在后检查 `_has_incomplete_arm()`，命中则 `incomplete_step_history` 失败。
- 当前 conformance 的 `skipped_level_plus_complete_other` 用例中，补全臂的 `s:1` 样本位于 `y=-4.9`，在 `t_stairs` zone 内；此前某轮担心的 `y=-5.3` 已不在当前工件，反例有效。
- 单臂完整仍保留 50/33 部分分；同 zone 地面重置后第二臂被 `arms_before_ground`/`_eligible_arms()` 封住，分数最高 50，不会升到 100。

因此 B3 修复生效，且不存在“另一臂缺级仍得 33”的问题。

### B5：Part2 hold 连续

结论：**通过**。

- `comp_part2_judge.py::Part2JudgeV2.update` 中 `cond` 为假时执行 `self.held = 0.0`，中断清零。
- `run_self_test` 的 `interrupted` 与 `continuous` 用例分别验证中断不清零会失败、连续满足会成功。

---

## 4. route

结论：**route 核心方向已修复，但 `height_bar` 仍非 scorer blocker 的链路缺口**。

- **slope**：`config/part1-route.json` 中 `to_slope [5.2,-6.3]` → `cross_slope [5.2,-4.2]`，沿 y 跨度 2.1 m；与 `Slope._on_sample` 的 y 投影累计一致。
- **slalom**：route 含 `slalom_corner [1.55,-12.75]`，正好是 judge 拐角圆心；路径顺序为 post0→post1→post2→corner→post3→end，符合 A 方向 `corner_after=3`。
- **bridge_blocks**：`to_bridge_blocks [0.8,0.0]` 在 zone 西侧外，`cross_bridge_blocks [6.5,0.0]` 从 xmin 进、xmax 出；B1 修复后远端平台落地不再误判。
- **bridge_bands**：`stage_bridge_bands_south [5.7,-4.5]` 在 zone 南侧外，`to_bridge_bands [5.7,-3.6]` 从 ymin 进，`cross_bridge_bands [5.7,-0.5]` 从 ymax 出；入口/出口 opposite 正确。
- **height_bar**：当前 course diag 三次 attempt 仍为 `height_bar: wrong_exit_side`；演练证据 `part1_course_pause_resume_drill.json` 也显示 `in_zone_samples=15770, touched=false, failures=["wrong_exit_side"]`。这是脚本 waypoint 跟踪/进入侧稳定性问题，不是当前 scorer blocker，但正式链路需处理。

---

## 5. 回归与证据链

- **conformance 13 组**：`comp_judge_conformance.py::main` 仍列出 13 组；B1/B2/B3/B5 对应反例存在。当前工件中，早期担心的 `j_merge` 出 zone、B3 `s:1` 出 zone 问题已不存在。
- **self-test**：`comp_part1_course.run_self_test`、`comp_part2_judge.run_self_test`、`comp_score.run_self_test`、`comp_import_selftest.py`、`check_part1_scene_v2.py` 的用例路径存在，静态合理。
- **四份产物 summary↔trials**：
  - Part1 diag：8 trials，summary `attempts_used=8`；
  - Part2 diag：20 trials，summary `attempts_used=4/4/4/4/3/1`；
  - Part2 official：24 trials，每 category 4 次，attempt 1–4 正确；
  - Part1 course：24 trials（3×8），attempts_used=3，`final_time_s=109.25999999997266` 与 trial `109.26` 在 `comp_score` 容差内一致。
- **HASHES**：`comp/audits/HASHES.json` 当前 66 objects；四份产物 manifest/trials/summary、三份演练证据、judge/geom/course/scene/route/levels 等 hash 与给定文件头 payload sha256 匹配。四份 manifest 的 judge hash 均为当前 `comp_part1_judge.py=98ee9…`、`comp_part1_geom_tags.py=79ce2…`、`comp_part1_course.py=9adf6…`、`comp_part2_judge.py=733aa…`。
- 未发现由本轮修复直接引入的旧回归或新的可复现 scorer blocker。

---

## 6. 新问题 / 残余

非 blocker，但建议 C1/正式协议前处理：

1. `height_bar` course diag 仍 `wrong_exit_side`：脚本 route 跟踪不鲁棒，C2 复用当前 route 会缺项。
2. B1 边界：同帧“首次远端平台 tag + 2 ground feet”可能仍失败，需 C1 对抗用例确认。
3. `TraversalBridge` 未用 `axis` 强制 x/y 穿越方向，仅按 opposite side 合法；理论上有侧向穿过桥的语义宽度，建议 C1 复核。
4. slalom judge 拐角半径 0.30 m 与场景显示圆 0.5 m 不一致。
5. `comp/CONTRACT.md §6` 仍列旧 V1 judge/scene 资产，文档陈旧。
6. `HASHES.json` 仍 `audited=false / verdict=pending`，需 G1 结论后更新。

---

## 7. G1 必写残余

1. 砂砾坑真实“坑 + 碎木”几何未 recut；当前仍为凸起盒代理。
2. Part2 官方能力场未逐档交叉核对；official 重复最高档在确定性策略下统计意义有限。
3. Part1 正式手动/操作手 3 次整场演练未在真实赛程完成；当前只有脚本化诊断与 pause/resume、abort、pause_timeout 演练。
4. `height_bar` course diag 仍 `wrong_exit_side`；route 语义正确但实际跟踪鲁棒性不足。
5. Part2 稳定性 ≥100 次、目标 0 失败未执行；`comp/eval/_calibration/` 人工标定集仍为空。
6. B4/B6/B7 保守向判罚留待 C1 标定：限高杆未校验“从下方”、Part2 高墙必须墙接触、沟壑 lane ±0.7 偏保守。
7. Part1 单障碍诊断 importer 的 per-obstacle 汇总口径仅用于诊断；正式以 course importer 为准。
8. `comp/eval/_protocol.md` 仍为 draft；`HASHES.json` 仍 `audited=false / verdict=pending`。
9. 跨 attempt 模拟器时间重置后，事件时间线不能全局排序。
10. slalom judge 拐角半径 0.30 m 与场景显示圆 0.5 m 不一致，需在标定集或协议中定口径。
