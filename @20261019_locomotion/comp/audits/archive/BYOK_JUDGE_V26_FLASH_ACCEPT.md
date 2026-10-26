verdict：**CONCERN**  
blocker：**无**（就本轮要求核验的 B1/B2/B3/B5/route 主路径而言）；但发现一个 **B1 相关的条件性误判失败边缘**，建议在 C1 人工标定前修掉。  
是否建议进入下一阶段（C1/C2）：**no**（先清掉软重置状态残留与 slope soft-reset 归因，再进 C1/C2）。

> 说明：artifact 未附行号，以下按 `文件::函数/代码段` 定位，不臆造行号。未附本轮 conformance/self-test stdout，所以“通过”是源码路径 + 产物一致性静态复核，不是实际执行日志的形式证明。

---

## 1. B1：离障落地门控

### 主语义：PASS
`comp_part1_judge.py::_Obstacle.update` 的 `inside` 分支与 `elif self.prev_in_zone` 退出成功分支都已加：

- `if ok and self.ground_fail and not self.supported: self._fail("insufficient_obstacle_support")`

因此 V24/V25 flash 指出的“合法入口 + 单足蹭 tag + 地面行走”假成功已被封：未全足支撑时，即使 `_check_exit` 证据凑齐，也会转失败。

`_ground_penalty_active` 覆盖：

- `TraversalBridge._ground_penalty_active`：`bridge_hits>=3` 且两个平台 tag 命中后关闭判罚；覆盖 `bridge_blocks` / `bridge_bands`。
- `GravelPit._ground_penalty_active`：`gravel_hits>=3` 且 supported 后，按入口侧接近出口短边 `0.35 m` 关闭；中途不靠近出口仍判。
- `TStairs._ground_penalty_active`：`top` + 至少一条完整臂后关闭。
- `Slope._ground_penalty_active`：累计投影 `>=1 m` 后关闭。

`comp_judge_conformance.py::test_bridge_ground_and_success`、`test_gravel_short_edges_and_long_edge`、`test_t_stairs_full_partial_and_history`、`test_slope_projection_and_graze_reset` 已补 landing 与 mid-fall 用例；`bridge_blocks`、`bridge_bands` 分开覆盖。  
结论：**“完成跨越后落地合法 / 中途真坠落仍失败”的主语义成立，五类 ground_fail ID 覆盖完整。**

### 但发现条件性误判失败边缘：CONCERN
`_Obstacle.update` 的 soft-reset 分支：

```python
elif self.prev_in_zone and self.result.status == "running":
    ...
    else:
        self.result.status = "pending"
        self.result.detail["aborted_exit"] = side
        self._reset_evidence()
        self.armed = True
```

没有清 `self.supported` / `self.prev_touched`。而 `Slope._check_exit` 在 `distance < 1.0` 时返回 `(False, "")`，即 soft-reset，不调用 `_fail()`。  
可构造：机器人曾全足支撑上坡（`supported=True`），累计不足 1 m 后离开 zone，触发 soft-reset；再次正常走入 zone 时，因 `supported` 仍为 True、`distance` 已清零，`_ground_penalty_active` 仍为 True，若此时 ≥2 足在地面，会在真正触碰坡面之前直接 `two_feet_ground` 失败。  
这属于 **B1 状态复位不完整**，会污染“失败/擦碰后重试”的合法路径；本轮要求的单次连续通过主路径不受影响，但 C1 人工标定若包含重试，会被污染。

---

## 2. B2：绕杆拐角

**PASS。**

`comp_part1_judge.py::Slalom._on_sample`：

- `corner_visits` 记录每次进入拐角圆时的 `len(order)`，不再首次锁存；
- `SLALOM_CORNER_RADIUS_M = 0.30`；
- `_check_immediate` / `_check_exit` 要求期望时序 `A=3 / B=2` 出现在 `corner_visits` 集合中。

`comp_judge_conformance.py::test_slalom_forward_reverse_and_spoof` 覆盖：

- `early_then_legal`：提前扫过拐角后仍可合法通过；
- `early_corner`：拐角时序不对拒绝；
- `out_of_order`：乱序拒绝；
- 缺拐角由 `_check_exit` 的 `missing_corner_checkpoint` 拒绝。

未发现提前扫过拐角误杀合法路径。  
minor：场景显示拐角圆半径仍是 0.5 m，judge 用 0.30 m；若正式标定只擦到显示圆外沿、未进 judge 0.30 m，会存在判罚偏严风险。本轮 route 走圆心，不受影响。

---

## 3. B3 / B5

### B3：PASS
`comp_part1_judge.py::TStairs._has_incomplete_arm()` 对任一臂 `levels` 非空且 `< {1,2,3}` 返回 True；`_check_exit` 中 `incomplete_step_history` 拒绝。  
`comp_judge_conformance.py::test_t_stairs_full_partial_and_history` 的 `skipped_level_plus_complete_other` 已断言“n 臂缺级 + s 臂完整”不成功。  
单臂完整仍给部分分：s=50、n/e=33，保留。

### B5：PASS
`comp_part2_judge.py::Part2JudgeV2.update` 中 `cond` 为假时 `self.held = 0.0`，断续满足不再累计成功。  
`run_self_test` 的 `interrupted` / `continuous` 用例覆盖。`_hold_ok` 仍是 dead code，minor。

---

## 4. route

- **slope：PASS。** `config/part1-route.json` 的 `to_slope=(5.2,-6.3)`、`cross_slope=(5.2,-4.2)`，沿 y 跨度 2.1 m；`Slope._on_sample` 只累计坡面接触期间 `|Δy|`，判分轴匹配。
- **slalom：PASS。** route 有 `slalom_corner=(1.55,-12.75)`，且 `to_slalom -> slalom_p1 -> slalom_p2 -> slalom_posts -> slalom_corner -> slalom_exit` 形成交替 S 形；拐角半径 0.30 m 可命中。
- **bridge_blocks：PASS。** `to_bridge_blocks=(0.8,0.0)` 从西侧 zone 外进入，`cross_bridge_blocks=(6.5,0.0)` 从 xmin 进、xmax 出；`TraversalBridge._check_exit` 的 opposite-side 条件满足。B1 落地门控修复后，东侧 `platform_r` 外 0.1 m 地面带落地不再误判。
- **bridge_bands：PASS。** `stage_bridge_bands_south=(5.7,-4.5)` 在 zone 南侧外，`to_bridge_bands=(5.7,-3.6)` 从 ymin 进，`cross_bridge_bands=(5.7,-0.5)` 从 ymax 出；方向与 `_check_exit` 的 ymin→ymax 匹配。conformance 的 `bands_landing` 也覆盖 south→north。
- **height_bar：route 语义本身可过，但 course diag 仍出现 `wrong_exit_side`。** 这不是 gate 语义 blocker，更像实际策略未稳定到达南侧起点/轨迹抖动；但说明 route 对跟踪误差不鲁棒，C1 前应复核进入方向余量。

---

## 5. 回归与证据链

- **conformance 13 组：** `comp_judge_conformance.py::main` 仍列 13 组；B1/B2/B3/B5 对应用例均存在。静态复核通过；未附 stdout，不能形式证明实际执行。
- **self-test：** `comp_part1_course.run_self_test`、`comp_part2_judge.run_self_test`、`comp_score.run_self_test`、`comp_import_selftest.py`、`check_part1_scene_v2.py` 的用例路径存在，未发现本轮修复直接引入的旧回归。
- **四份产物 summary↔trials：**
  - `flat-ft-2500-part1-diag-v2`：8 trials / summary 8 障碍 fail，原因逐条一致。
  - `flat-ft-2500-part2-diag-v2`：20 trials；summary `attempts_used=4/4/4/4/3/1` 与 trials 计数一致。
  - `flat-ft-2500-part2-official-diag`：24 trials；每 category 4 次，attempt 1–4 编号正确，summary 一致。
  - `flat-ft-2500-part1-course-diag`：24 trials（3×8）；summary `final_time_s=109.25999999997266` 与 trial 109.26 在 `comp_score` 1e-6 容差内一致；attempts_used=3 与不同 attempt 数一致。
- **HASHES：** 当前 `comp/audits/HASHES.json` 共 66 objects；四份产物 manifest/trials/summary、三份演练证据、judge/geom/course/scene/route/levels 等关键对象与 payload 中 sha256 匹配。  
  本轮四份 manifest 的 judge hash 已统一为当前 `comp_part1_judge.py = 0a65e5ac…`，V25 flash 指出的三份 manifest 旧 judge hash `bec8ff07/127ddf…` 问题在当前 artifact 中已解决。  
  `HASHES` 仍 `audited=false / verdict=pending`，这是 G1 前状态，不是当前 blocker。
- **新假成功：** 未发现。V24/V25 的非 `supported` 地面蹭 tag 假成功已被退出成功分支的 supported 门控封住。
- **新误判失败/链路缺口：** 见下节新问题 1；另有 height_bar course diag `wrong_exit_side` 的跟踪鲁棒性问题。

---

## 6. 新问题

1. **soft-reset 未清 `supported` / `prev_touched`，可导致条件性误判失败。**  
   `comp_part1_judge.py::_Obstacle.update` 的 `else` soft-reset 分支只 `_reset_evidence()`，未复位 `self.supported`、`self.prev_touched`；`Slope._check_exit` 又在 `distance<1.0` 时返回空 reason 走 soft-reset。  
   影响：曾全足支撑但未完成 1 m 的 slope 离开后重入，可能在触碰坡面前被 `two_feet_ground` 误判。建议 soft-reset 同时复位 `supported/prev_touched`，并让真实接触/长停留的 slope 未完成走 `_fail("distance_insufficient")`，与修复映射 #13 的“真实尝试仍记失败”一致。这不是当前单次连续通过主路径的 blocker，但会污染 C1 重试。

2. **slalom judge 拐角半径 0.30 m 与场景显示圆 0.5 m 不一致。**  
   `part1_eval_scene_v2.xml` 的拐角显示 geom 仍是 `size="0.5 ..."`，judge 用 `SLALOM_CORNER_RADIUS_M=0.30`。本轮 route 走圆心，不受影响；但正式标定若只擦到显示圆外沿，会偏严。建议在 G1 残余/标定集中写明。

3. **height_bar course diag 仍 `wrong_exit_side`。**  
   `config/part1-route.json` 的 `to_height_bar=(5.7,-10.2)`、`cross_height_bar=(5.7,-8.2)` 语义上是 ymin→ymax，但实际策略未稳定跟踪到南侧起点，course 产物 3 次均 `wrong_exit_side`。这不是 judge gate 语义错误，但说明 route 对跟踪误差不鲁棒，C1 前应复核进入方向余量。

4. **minor：** `comp_import_diagnostic.py` 的 `DEFAULT_JUDGE` 仍指向旧 V1 `part1_event_judge.py`；当前 diag-v2 产物通过 `--judge/--judge-extra` 覆盖生成，但默认用法有陈旧 hash 风险。  
   `comp_part2_judge._hold_ok` 仍 dead code；`comp_score.py` 顶部重复 `import tempfile`；`CONTRACT.md §6` 资产表仍列旧 V1 场景/judge；`HASHES` 仍 pending。

---

## 7. 结论

- **verdict：CONCERN**
- **blocker：无**（就 B1/B2/B3/B5/route 本轮主路径而言）；但存在 **soft-reset 状态未复位导致的条件性误判失败边缘**，建议在 C1 前修。
- **是否建议进入 C1/C2：no。**  
  先修 soft-reset 的 `supported/prev_touched` 复位与 slope 未完成归因，并复核 height_bar route 跟踪余量；然后重跑 conformance 13 组、各 self-test、四份产物与演练，刷新 HASHES，再做 delta 复验。
- B2/B3/B5 代码层 PASS；slope/slalom/bridge_blocks/bridge_bands route 方向 PASS；证据链 summary↔trials 与 HASHES 基本一致。

---

## G1 必写残余

1. 砂砾坑真实“坑+碎木”几何未 recut；当前仍是凸起盒代理；recut 后需复核 gravel 出口 0.35 m grace。
2. Part2 官方能力场未逐档交叉核对；official 重复最高档在确定性策略下统计意义有限。
3. soft-reset 阈值与相邻 zone 重叠仍是启发式；**新增：soft-reset 未清 `supported/prev_touched`，且 `Slope._check_exit` 对 `distance<1` 一律空 reason，存在重入误判风险。**
4. T 台阶 s/n/e ↔ 上/下映射、障碍级跳过是否消耗整场尝试、pause_timeout 120 s 自定协议常量仍需书面确认。
5. 正式手动/操作手 3 次整场演练未在真实赛程完成；当前只有脚本化诊断与 pause/resume、abort、pause_timeout 演练。
6. B4/B6/B7 保守向判罚留待 C1 标定裁决：限高杆未校验“从下方”、Part2 高墙必须墙接触、沟壑 lane ±0.7 偏保守。
7. Part1 单障碍诊断 importer 的 per-obstacle 汇总口径仅用于诊断；正式以 course importer 为准。
8. `comp/eval/_protocol.md` 仍为 draft；`HASHES.json` 仍 `audited=false / verdict=pending`。
9. 跨 attempt 模拟器时钟重置后，事件时间线不能全局排序。
10. Part2 稳定性 ≥100 次、目标 0 失败未执行；`comp/eval/_calibration/` 人工标定集仍为空。
11. **新增必写：slalom judge 拐角半径 0.30 m 与场景显示圆 0.5 m 不一致，需在标定集或协议中定口径。**
12. **新增必写：height_bar course diag 仍 `wrong_exit_side`，route 语义正确但实际跟踪鲁棒性不足。**
