verdict：**FAIL**  
blocker：**有**。B2 的“乱序”仍可产生假成功；T 台阶在 B1 落地门控后，第二臂可在地面蹭级/乱序收集而拿满分。二者都是 scorer 侧假成功，不是单纯证据链问题。  
是否建议进入 C1/C2：**no**。

> artifact 未附行号；以下按 `文件::函数/代码段` 定位，不臆造行号。未附本轮 stdout，以下为源码 + 产物的静态复核，不是执行日志的形式证明。

---

## 1. B1：离障落地门控

### 主语义：PASS（但 T 台阶门控范围过宽，见新问题）
`comp_part1_judge.py::_Obstacle.update` 对 `ground_fail` 障碍有两个关键门控：

- `inside` 分支付 `_check_immediate` 成功后：若 `ground_fail and not supported`，转 `_fail("insufficient_obstacle_support")`；
- `elif self.prev_in_zone` 退出成功分支同样有 `if ok and ground_fail and not supported`。

因此 V25 flash 的“合法入口 + 单足蹭 tag + 地面行走”假成功已被封住。

五个 ground_fail ID 覆盖完整：

- `TraversalBridge._ground_penalty_active`：`bridge_hits>=3` 且两个平台 tag 命中后关闭判罚；覆盖 `bridge_blocks` / `bridge_bands`。
- `GravelPit._ground_penalty_active`：`supported` 且 `gravel_hits>=3` 后，按入口侧距出口短边 `EXIT_GRACE_M=0.35` 关闭；中途不靠近出口仍判。
- `TStairs._ground_penalty_active`：`top` + 至少一条完整臂后关闭。
- `Slope._ground_penalty_active`：累计投影 `>=1 m` 后关闭。

`comp_judge_conformance.py::test_bridge_ground_and_success`、`test_gravel_short_edges_and_long_edge`、`test_t_stairs_full_partial_and_history`、`test_slope_projection_and_graze_reset` 已覆盖 bridge_blocks / bridge_bands / gravel / t_stairs / slope 的 landing 与 mid-fall 主路径。  
B1 的“完成跨越后落地合法 / 中途真坠落仍失败”主语义成立。

soft-reset 残留也已清：`_Obstacle.update` 的 soft-reset 分支已同时清 `supported=False`、`prev_touched=False` 和 `detail["touched"]`，V26 flash 指出的 slope soft-reset 条件性误判失败边缘已闭环。

但 T 台阶门控“`top` + 一条完整臂”即关闭，范围过宽；这不是 landing 语义本身的问题，而是给第二臂地面蹭级留下通道，详见新问题 2。

---

## 2. B2：绕杆拐角与乱序

### 拐角部分：PASS
`comp_part1_judge.py::Slalom._on_sample` 已用 `corner_visits` 记录所有进入拐角圆时的杆数，`SLALOM_CORNER_RADIUS_M=0.30`；`_check_immediate` / `_check_exit` 要求期望时序 `A=3 / B=2` 出现在访问集合中。  
`comp_judge_conformance.py::test_slalom_forward_reverse_and_spoof` 的 `early_then_legal` 覆盖“提前扫过拐角后仍可合法通过”；`early_corner`、缺拐角仍拒绝。拐角提前扫过不再误杀合法路径。

### 乱序部分：FAIL
`Slalom._on_sample` 仍只接受当前期望杆：

```text
idx = len(order)
target = expected[idx]
if near(xy, post[target]):
    order.append(target)
```

它没有像 `corner_visits` 那样记录“非目标杆的提前访问”。因此可构造：

```text
start A -> 先扫过 post1（被忽略） -> post0 -> post1 -> post2 -> 拐角 -> post3 -> 终点
```

最终 `order=[0,1,2,3]`、`sides` 仍可交替、`corner_visits` 含 3，`_check_immediate` / `_check_exit` 会判 success。  
但规则是“漏杆/顺序错/出场”失败；提前扫过 post1 再回头按正确序列走，属于乱序，却被静默忽略。

`comp_judge_conformance.py::test_slalom_forward_reverse_and_spoof` 的 `out_of_order` 用例实际只走到 post1/post2/post3 后结束，从未补 post0，失败原因是 `missing_posts`，不是“乱序拒绝”。因此 13 组全绿不能证明乱序已拒绝。  
这是 scorer 假成功，blocker。

minor：judge 拐角半径 `0.30 m` 与场景显示圆 `0.5 m` 仍不一致；当前 route 走圆心不受影响，但 C1 标定需定口径。

---

## 3. B3 / B5

### B3 窄口径：PASS
`TStairs._has_incomplete_arm()` 对任一臂 `levels` 非空且 `< {1,2,3}` 返回 True；`TStairs._check_exit` 中 `incomplete_step_history` 拒绝。  
`comp_judge_conformance.py::test_t_stairs_full_partial_and_history` 的 `skipped_level_plus_complete_other` 已断言“n 臂缺级 + s 臂完整”不成功。  
单臂完整仍给部分分：s=50、n/e=33，保留。

### 但 T 台阶仍有新的满分假成功：FAIL 级新问题
`TStairs._on_sample` 只把每臂已触 level 累成集合；`TStairs._check_exit` 只检查：

- `top` 是否存在；
- `_complete_arms()` 是否非空；
- `_has_incomplete_arm()` 是否为假。

它没有使用已记录的 `entry_arm` / `exit_arm`，也没有要求“上臂与下臂不同”或第二臂触级顺序。  
更关键的是 `TStairs._ground_penalty_active` 在 `top` + 一条完整臂后即返回 False。于是：

```text
合法完成 s 臂 + top（partial 50）
-> 下到地面，仍 supported=True
-> 走到 e 臂，在地面用单足蹭 e:1/e:2/e:3
-> 因 ground penalty 已关闭，不会 two_feet_ground
-> _check_exit 看到 s、e 两臂完整，返回 100
```

`comp_judge_conformance.py` 的 `partial_landing` 已证明“top+一完整臂后 2 足地面不判失败”；`upgrade` 用例只在无地面接触的合成样本中升级；没有覆盖“第二臂在地面蹭级/乱序收集”。  
这是 B1 门控与 B3 历史检查共同导致的满分假成功，blocker。

### B5：PASS
`comp_part2_judge.py::Part2JudgeV2.update` 中 `cond` 为假时 `self.held = 0.0`，断续满足不再累计。  
`run_self_test` 的 `interrupted` / `continuous` 用例覆盖“中断清零、连续成功”。`_hold_ok` 仍是 dead code，minor。

---

## 4. route

- **slope：PASS。** `config/part1-route.json` 的 `to_slope=(5.2,-6.3)`、`cross_slope=(5.2,-4.2)`，沿 y 跨度 2.1 m；`Slope._on_sample` 只累计坡面接触期间 `|Δy|`，判分轴匹配。
- **slalom：PASS。** route 有 `slalom_corner=(1.55,-12.75)`，且 `to_slalom -> slalom_p1 -> slalom_p2 -> slalom_posts -> slalom_corner -> slalom_exit` 形成交替 S 形；拐角半径 0.30 m 可命中。
- **bridge_blocks：PASS。** `to_bridge_blocks=(0.8,0.0)` 从西侧进入，`cross_bridge_blocks=(6.5,0.0)` 从 xmin 进、xmax 出；`TraversalBridge._check_exit` 的 opposite-side 条件满足。B1 落地门控修复后，东侧平台外落地不再误判。
- **bridge_bands：PASS。** `stage_bridge_bands_south=(5.7,-4.5)` 在 zone 南侧外，`to_bridge_bands=(5.7,-3.6)` 从 ymin 进，`cross_bridge_bands=(5.7,-0.5)` 从 ymax 出；方向与 `_check_exit` 匹配。
- **height_bar：route 语义正确，但 course diag 仍 `wrong_exit_side`。**  
  `comp/eval/flat-ft-2500-part1-course-diag/summary.json` 三次尝试均为 `height_bar: wrong_exit_side`；`comp/audits/evidence/part1_course_pause_resume_drill.json` 也显示 height_bar `in_zone_samples=15770, touched=false, failures=["wrong_exit_side"]`。  
  这不是 gate 语义 blocker，但说明脚本化 route 对跟踪误差不鲁棒；C2 若复用该 route 会缺一项。属正式链路缺口/G1 残余。

---

## 5. 回归与证据链

### conformance 13 组
`comp_judge_conformance.py::main` 仍列 13 组；B1/B2/B3/B5 对应用例存在。静态复核通过，但如上述：

- B2 的 `out_of_order` 只测“缺杆”，未测“提前扫过非目标杆后再补正确序列”；
- T 台阶未测“partial 后在地面蹭第二臂/乱序收集”。

所以 13 组全绿不能证明 B2 乱序与 T 台阶第二臂假成功已封。

### self-test
`comp_part1_course.run_self_test`、`comp_part2_judge.run_self_test`、`comp_score.run_self_test`、`comp_import_selftest.py`、`check_part1_scene_v2.py` 的用例路径存在；未发现本轮修复直接引入的旧回归。仍无 stdout，不能形式证明实际执行。

### 四份产物 summary↔trials
- `flat-ft-2500-part1-diag-v2`：8 trials，summary 8 障碍 fail，失败原因逐条一致。
- `flat-ft-2500-part2-diag-v2`：20 trials；summary `attempts_used=4/4/4/4/3/1` 与 trials 计数一致。
- `flat-ft-2500-part2-official-diag`：24 trials；每 category 4 次，attempt 1–4 编号正确，summary 一致。
- `flat-ft-2500-part1-course-diag`：24 trials（3×8）；summary `final_time_s=109.25999999997266` 与 trial 109.26 在 `comp_score` 1e-6 容差内一致；attempts_used=3 一致。

### HASHES
`comp/audits/HASHES.json` 当前 **66 objects**；四份产物 manifest/trials/summary、三份演练证据、judge/geom/course/scene/route/levels 等与 payload sha256 匹配。  
四份 manifest 的 judge hash 已统一为当前 `comp_part1_judge.py = 7d6aa6d985…`，V25 flash 指出的旧 judge hash 问题已解决。  
`HASHES` 仍 `audited=false / verdict=pending`，属 G1 前状态，不是当前 blocker。

### 新假成功 / 误判失败 / 链路缺口
- **新假成功 1（blocker）**：B2 乱序 post 提前访问被忽略，后续补正确序列可成功。
- **新假成功 2（blocker）**：T 台阶 partial 后，第二臂可在地面蹭级/乱序收集，拿满分。
- **链路缺口**：height_bar course diag 仍 `wrong_exit_side`；route 语义正确但跟踪不鲁棒。
- **minor**：slalom judge 半径 0.30 m vs 场景显示 0.5 m；`comp_import_diagnostic.py` 默认 judge 仍指旧 V1；`comp/CONTRACT.md §6` 资产表仍列旧 V1；`_protocol.md` 仍 draft；`HASHES` pending。

---

## 6. 结论

- **verdict：FAIL**
- **blocker：有**
  1. B2 乱序假成功：`Slalom._on_sample` 只接受期望杆，不记录非目标杆提前访问；`test_slalom...out_of_order` 未覆盖真正乱序。
  2. T 台阶第二臂假成功：`TStairs._ground_penalty_active` 在 `top+一条完整臂` 后即关闭，`_check_exit` 又不用 `entry_arm/exit_arm` 或触级顺序；partial 后可在地面蹭第二臂拿 100。
- **是否建议进入下一阶段（C1/C2）：no**。先修 B2 乱序历史、T 台阶第二臂支持/顺序约束，并补对应 conformance 反例；再复核 height_bar route 跟踪余量，重跑 13 组 conformance、各 self-test、四份产物与演练，刷新 HASHES 后再做 delta 复验。

---

## G1 必写残余

1. 砂砾坑真实“坑 + 碎木”几何未 recut；当前仍是凸起盒代理；recut 后需复核 gravel 出口 0.35 m grace。
2. Part2 官方能力场未逐档交叉核对；official 重复最高档在确定性策略下统计意义有限。
3. soft-reset 阈值与相邻 zone 重叠仍是启发式；soft-reset 已清 `supported/prev_touched`，但边界阈值仍需标定。
4. T 台阶 s/n/e ↔ 上/下映射、障碍级跳过是否消耗整场尝试、pause_timeout 120 s 自定协议常量仍需书面确认。
5. 正式手动/操作手 3 次整场演练未在真实赛程完成；当前只有脚本化诊断与 pause/resume、abort、pause_timeout 演练。
6. B4/B6/B7 保守向判罚留待 C1 标定裁决：限高杆未校验“从下方”、Part2 高墙必须墙接触、沟壑 lane ±0.7 偏保守。
7. Part1 单障碍诊断 importer 的 per-obstacle 汇总口径仅用于诊断；正式以 course importer 为准。
8. `comp/eval/_protocol.md` 仍为 draft；`HASHES.json` 仍 `audited=false / verdict=pending`。
9. 跨 attempt 模拟器时钟重置后，事件时间线不能全局排序。
10. Part2 稳定性 ≥100 次、目标 0 失败未执行；`comp/eval/_calibration/` 人工标定集仍为空。
11. slalom judge 拐角半径 0.30 m 与场景显示圆 0.5 m 不一致，需在标定集或协议中定口径。
12. height_bar course diag 仍 `wrong_exit_side`；route 语义正确但实际跟踪鲁棒性不足。
13. **本轮新增必写**：B2 乱序 post 提前访问未被记录/拒绝；conformance `out_of_order` 实际只测缺杆。
14. **本轮新增必写**：T 台阶 partial 后第二臂可在地面蹭级/乱序收集拿满分；`TStairs._ground_penalty_active` 关闭过早，`entry_arm/exit_arm` 未用于判定。
