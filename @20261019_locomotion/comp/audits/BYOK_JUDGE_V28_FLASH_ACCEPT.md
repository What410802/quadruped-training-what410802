按函数/代码段定位（artifact 未附行号，不臆造行号）。以下为源码 + 产物的静态复核，未附本轮 conformance/self-test stdout，因此“通过”是代码路径与哈希一致性结论，不是执行日志的形式证明。

## verdict：**FAIL**

- **blocker：有**。`TStairs` 的 partial→full 升级仍未被“单次异臂上下”约束：`TStairs._check_exit` 只检查 `top` 与“两条完整臂”，未使用 `entry_arm/exit_arm`；`_Obstacle.update` 又允许 partial success 重新进入并升级。当前 `TStairs._on_sample` 在 `ground_feet` 非空时直接返回，确实封住了 V27 指出的“地面蹭级”路径，但“落地后重新进入、真实攀爬第二臂”仍可把两个分离的 partial 合并成 100。按契约“任一方向上、另一侧下”的字面语义，这是 scorer 假成功。
- 是否建议进入 C1/C2：**no**。

---

## 1. B1：离障落地门控

### 主语义：PASS
`comp_part1_judge.py::_Obstacle.update` 对 `ground_fail` 障碍有双侧门控：

- `inside` 分支 `_check_immediate` 成功后，若 `ground_fail and not supported`，转 `insufficient_obstacle_support`；
- `elif self.prev_in_zone` 退出成功分支同样检查 `supported`。

`_ground_penalty_active` 覆盖五类 ground_fail ID：

- `TraversalBridge._ground_penalty_active`：`bridge_hits >= 3` 且两个平台 tag 命中后关闭判罚；覆盖 `bridge_blocks`、`bridge_bands`。中途真坠落仍由 `two_feet_ground` 失败。
- `GravelPit._ground_penalty_active`：`gravel_hits >= 3` 且 supported 后，按入口侧距出口短边 `EXIT_GRACE_M=0.35` 关闭；中段仍判。
- `TStairs._ground_penalty_active`：`top` + 至少一条完整臂后关闭；partial 落地合法。
- `Slope._ground_penalty_active`：累计投影 `>=1 m` 后关闭；中段仍判。

`comp_judge_conformance.py` 的 `test_bridge_ground_and_success`、`test_gravel_short_edges_and_long_edge`、`test_t_stairs_full_partial_and_history`、`test_slope_projection_and_graze_reset` 已覆盖 bridge_blocks/bridge_bands/gravel/t_stairs/slope 的 landing 与 mid-fall 主路径。  
**结论：B1 的“完成跨越后落地合法 / 中途真坠落仍失败”主语义成立，五类 ground_fail 覆盖完整。**

但注意：`TStairs` 的“partial 后关闭地面判罚”本身是 partial 落地所需，却与下面 B3 的 partial→full 升级共同构成假成功通道。

---

## 2. B2：绕杆拐角与乱序

### PASS
`comp_part1_judge.py::Slalom._on_sample` 当前：

- `corner_visits` 记录每次进入拐角圆时的 `len(order)`，不再首次锁存；
- `SLALOM_CORNER_RADIUS_M = 0.30`；
- `_check_immediate` / `_check_exit` 要求期望时序 `A=3 / B=2` 出现在 `corner_visits` 中；
- 新增 `early_posts`：对 `idx` 之后的未来杆提前到访记违规；`_check_immediate` / `_check_exit` 要求 `early_posts` 为空，否则 `post_out_of_order`。

`comp_judge_conformance.py::test_slalom_forward_reverse_and_spoof` 已包含：

- `early_then_legal`：提前扫过拐角后仍可合法通过；
- `early_corner`：拐角时序不对拒绝；
- `early_future_post`：提前碰未来杆后再补正确序列仍失败；
- 缺拐角由 `_check_exit` 的 `missing_corner_checkpoint` 拒绝。

**结论：B2 的“提前扫拐角不误杀、乱序/缺拐角拒绝”在当前源码下成立。**  
minor：judge 拐角半径 0.30 m 与场景显示圆 0.5 m 仍不一致，C1 需定口径；当前 route 走圆心，不受影响。

---

## 3. B3 / B5

### B3 窄口径：PASS
`TStairs._has_incomplete_arm()` 对任一臂 `levels` 非空且 `< {1,2,3}` 返回 True；`TStairs._check_exit` 中 `incomplete_step_history` 拒绝。  
`comp_judge_conformance.py::test_t_stairs_full_partial_and_history` 的 `skipped_level_plus_complete_other` 已断言“n 臂缺级 + s 臂完整”不成功。  
**因此“另一臂缺级仍能得分”在当前代码下不成立；单臂完整仍保留 s=50、n/e=33。**

### 但 T 台阶仍有 blocker：partial→full 升级未约束“单次异臂上下”
`TStairs._check_exit` 目前只检查：

- `top` 是否存在；
- `_complete_arms()` 是否非空；
- `_has_incomplete_arm()` 是否为假。

它**没有使用** `entry_arm` / `exit_arm`，也没有要求“上升臂与下降臂不同”或“一次连续 traversal 内完成”。  
`_Obstacle.update` 对 partial success 有特殊放行：`status=="success"` 且 `score < per_obstacle_score` 且未标 `upgrade_unavailable` 时，可重新进入并升级。  
`TStairs._on_sample` 新增的 `if ground_feet: return` 封住了“地面蹭级”，但未封住：

```text
合法完成 s 臂 + top（partial 50）
-> 落地/离开
-> 重新进入，真实攀爬 e 臂并完成 e:1/2/3
-> _complete_arms() 看到 s、e 两臂完整
-> 返回 100
```

这不是“上 s、下 e”的单次异臂 traversal，而是两个分离 partial 的合并。按契约“可从任一方向迈上台阶，通过另一个台阶回到地面”的字面语义，应判失败或至少不能由 partial 升级。  
`comp_judge_conformance.py` 的 `upgrade` 用例当前反而断言该路径可升级为 100，因此 conformance 未覆盖此反例。

**结论：B3 的“缺级”检查 PASS；但 T 台阶整体仍有 scorer 假成功 blocker。**

### B5：PASS
`comp_part2_judge.py::Part2JudgeV2.update` 中 `cond` 为假时 `self.held = 0.0`，断续满足不再累计；`run_self_test` 的 `interrupted` / `continuous` 用例覆盖“中断清零、连续成功”。  
`_hold_ok` 仍是 dead code，minor。

---

## 4. route

- **slope：PASS。** `config/part1-route.json` 的 `to_slope=(5.2,-6.3)`、`cross_slope=(5.2,-4.2)`，沿 y 跨度 2.1 m；`Slope._on_sample` 只累计坡面接触期间 `|Δy|`，判分轴匹配。
- **slalom：PASS。** route 有 `slalom_corner=(1.55,-12.75)`，且 `to_slalom -> slalom_p1 -> slalom_p2 -> slalom_posts -> slalom_corner -> slalom_exit` 形成经过拐角必达区的路径；0.30 m judge 半径可命中。
- **bridge_blocks：PASS。** `to_bridge_blocks=(0.8,0.0)` 从西侧 zone 外进入，`cross_bridge_blocks=(6.5,0.0)` 从 xmin 进、xmax 出；`TraversalBridge._check_exit` 的 opposite-side 条件满足。B1 修复后东侧平台外落地不再误判。
- **bridge_bands：PASS。** `stage_bridge_bands_south=(5.7,-4.5)` 在 zone 南侧外，`to_bridge_bands=(5.7,-3.6)` 从 ymin 进，`cross_bridge_bands=(5.7,-0.5)` 从 ymax 出；方向与 `_check_exit` 匹配。
- **height_bar：route 语义正确，但 course diag 仍 `wrong_exit_side`。**  
  `comp/eval/flat-ft-2500-part1-course-diag/summary.json` 三次尝试均为 `height_bar: wrong_exit_side`；`comp/audits/evidence/part1_course_pause_resume_drill.json` 也显示 height_bar `in_zone_samples=15770, touched=false, failures=["wrong_exit_side"]`。  
  这不是 gate 语义 blocker，但说明脚本化 route 对跟踪误差不鲁棒；C2 若复用该 route 会缺一项。属正式链路缺口/G1 残余。

---

## 5. 回归与证据链

### conformance 13 组
`comp_judge_conformance.py::main` 仍列 13 组；B1/B2/B3/B5 对应用例存在。静态复核未发现 B1/B2/B5 的直接回归；但如上，T 台阶 `upgrade` 用例本身把“partial→full 升级”当作合法，未覆盖“两个分离 partial 合并”的反例。

### self-test
`comp_part1_course.run_self_test`、`comp_part2_judge.run_self_test`、`comp_score.run_self_test`、`comp_import_selftest.py`、`check_part1_scene_v2.py` 的用例路径存在，未发现本轮修复直接引入的旧回归。未附 stdout，不能形式证明实际执行。

### 四份产物 summary↔trials
- `flat-ft-2500-part1-diag-v2`：8 trials，summary 8 障碍 fail，失败原因逐条一致。
- `flat-ft-2500-part2-diag-v2`：20 trials；summary `attempts_used=4/4/4/4/3/1` 与 trials 计数一致。
- `flat-ft-2500-part2-official-diag`：24 trials；每 category 4 次，attempt 1–4 编号正确，summary 一致。
- `flat-ft-2500-part1-course-diag`：24 trials（3×8）；summary `final_time_s=109.25999999997266` 与 trial 109.26 在 `comp_score` 1e-6 容差内一致；attempts_used=3 一致。

### HASHES
`comp/audits/HASHES.json` 当前 **66 objects**；四份产物 manifest/trials/summary、三份演练证据、judge/geom/course/scene/route/levels 等与 payload sha256 匹配。四份 manifest 的 `comp_part1_judge.py` hash 均为 `bc58e6e5...`，与当前文件一致。  
`HASHES` 仍 `audited=false / verdict=pending`，属 G1 前状态，不是当前 blocker。

### 新问题 / 残余
- **blocker**：T 台阶 partial→full 升级未约束 `entry_arm/exit_arm`，两个分离 partial 可合并为 100。
- **链路缺口**：height_bar course diag 仍 `wrong_exit_side`；route 语义正确但跟踪不鲁棒。
- **minor**：slalom judge 半径 0.30 m vs 场景显示 0.5 m；`comp_import_diagnostic.py` 默认 judge 仍指旧 V1；`comp/CONTRACT.md §6` 仍列旧 V1 资产；`_protocol.md` 仍 draft；HASHES pending。
- **需标定**：`TStairs._on_sample` 只要 `ground_feet` 非空就丢弃所有 step 证据，比规则“≥2 足触地失败”更严；可能影响第一级台阶的合法接触记录，需 C1 人工标定确认。

---

## 6. 结论

- **verdict：FAIL**
- **blocker：有**
  1. `comp_part1_judge.py::TStairs._check_exit` 未使用 `entry_arm/exit_arm`，未要求“单次异臂上下”；`_Obstacle.update` 又允许 partial success 重入升级，两个分离 partial 可合并为 100。地面蹭级虽已被 `_on_sample` 的 `ground_feet` 早返回封住，但结构性假成功仍在。
- **是否建议进入下一阶段（C1/C2）：no。**  
  先修 T 台阶 partial 升级/单次异臂约束，并补对应 conformance 反例；再复核 height_bar route 跟踪余量，重跑 13 组 conformance、各 self-test、四份产物与演练，刷新 HASHES 后再做 delta 复验。

---

## G1 必写残余

1. 砂砾坑真实“坑 + 碎木”几何未 recut；当前仍是凸起盒代理。
2. Part2 官方能力场未逐档交叉核对；official 重复最高档在确定性策略下统计意义有限。
3. soft-reset 阈值与相邻 zone 重叠仍是启发式；本轮 soft-reset 已清 `supported/prev_touched`，但边界阈值仍需标定。
4. T 台阶 s/n/e ↔ 上/下映射、障碍级跳过是否消耗整场尝试、pause_timeout 120 s 自定协议常量仍需书面确认。
5. 正式手动/操作手 3 次整场演练未在真实赛程完成；当前只有脚本化诊断与 pause/resume、abort、pause_timeout 演练。
6. B4/B6/B7 保守向判罚留待 C1 标定裁决：限高杆未校验“从下方”、Part2 高墙必须墙接触、沟壑 lane ±0.7 偏保守。
7. Part1 单障碍诊断 importer 的 per-obstacle 汇总口径仅用于诊断；正式以 course importer 为准。
8. `comp/eval/_protocol.md` 仍为 draft；`HASHES.json` 仍 `audited=false / verdict=pending`。
9. 跨 attempt 模拟器时钟重置后，事件时间线不能全局排序。
10. Part2 稳定性 ≥100 次、目标 0 失败未执行；`comp/eval/_calibration/` 人工标定集仍为空。
11. slalom judge 拐角半径 0.30 m 与场景显示圆 0.5 m 不一致，需在标定集或协议中定口径。
12. height_bar course diag 仍 `wrong_exit_side`；route 语义正确但实际跟踪鲁棒性不足。
13. **本轮新增必写**：T 台阶 partial 后可重入升级；`TStairs._check_exit` 未使用 `entry_arm/exit_arm`，未强制单次异臂上下，两个分离 partial 可合并为 100。
14. **本轮新增必写**：`TStairs._on_sample` 以“任意 ground_feet”丢弃 step 证据，严于规则“≥2 足触地失败”，需 C1 校准是否造成合法第一级接触漏记。
