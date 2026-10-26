> artifact 未附行号，以下按 `文件::函数/代码段` 定位，不臆造行号。结论基于给定源码、conformance、四份产物与 HASHES 的静态复核；未附本轮 stdout，因此“通过”指代码路径与证据链一致，不是执行日志的形式证明。

## verdict：**CONCERN**

- **blocker：无**。未发现可复现的 scorer blocker；V29 指出的 `TStairs` 同 zone 内“两臂合并为 100”在源码上已被 `arms_before_ground`/`_eligible_arms()` 封住（有 ≥2 足地面样本时）。
- **但证据链仍有需清理项**：conformance 中 `t_stairs` 的 “同 zone 合并” 用例实际在 `y=-5.1` 已离开 zone；B3 “另一臂缺级 + 本臂完整” 用例的 `s:1` 在 `y=-5.3` 也已离开 zone。源码语义看起来正确，但这两个用例没有真正覆盖它们声称的场景。
- **是否建议进入下一阶段**：**yes（有条件）**。C1 人工标定可进；C2 基线若复用当前脚本 route，需先处理 `height_bar: wrong_exit_side` 或明确该 route 不计分，并补 conformance 反例。

---

## 1. B1：离障落地门控

### 主语义：PASS（T 台阶同 zone 合并有证据缺口，但未发现 blocker）

`comp_part1_judge.py::_Obstacle.update` 仍有双侧门控：

- `inside` 分支 `_check_immediate` 成功后，若 `ground_fail and not supported` → `insufficient_obstacle_support`；
- `elif self.prev_in_zone` 退出成功分支同样检查 `supported`。

`_ground_penalty_active` 覆盖实际五个 `ground_fail` ID：

| ID | 门控 | 判定 |
|---|---|---|
| `bridge_blocks` / `bridge_bands` | `TraversalBridge._ground_penalty_active`：`bridge_hits>=3` 且两个平台 tag 命中后关闭 | 合法落地允许；桥面中段双足触地仍失败 |
| `gravel_pit` | `GravelPit._ground_penalty_active`：`supported` 且 `gravel_hits>=3` 后，按入口侧距出口短边 `EXIT_GRACE_M=0.35` 关闭 | 远短边落地允许；坑中段仍失败 |
| `slope` | `Slope._ground_penalty_active`：累计投影 `>=1.0 m` 后关闭 | 完成后落地允许；中途双足触地仍失败 |
| `t_stairs` | `TStairs._ground_penalty_active`：`top` + 至少一条完整臂后关闭 | partial 落地允许；中途真坠落仍失败 |

`comp_judge_conformance.py` 的 `test_bridge_ground_and_success`、`test_gravel_short_edges_and_long_edge`、`test_t_stairs_full_partial_and_history`、`test_slope_projection_and_graze_reset` 已覆盖 bridge_blocks/bridge_bands/gravel/t_stairs/slope 的 landing 与 mid-fall 主路径。  
**B1 主语义成立；未发现新的“合法落地被误判失败”。**

### T 台阶同 zone 合并：源码封住，conformance 用例有缺口

`TStairs._on_sample` 在 `top + 至少一条完整臂` 后，若出现 `len(ground_feet)>=2`，会记录：

```text
evidence["arms_before_ground"] = 当前 arms 快照
```

`TStairs._eligible_arms()` 返回 `arms_before_ground or arms`；`_score_for()` 使用 `_eligible_arms()`。因此“s 上/下 + 地面移动 + e 上/下”若中间出现 ≥2 足地面样本，评分只看落地前快照，最高 50，不能变 100。  
`TStairs._check_exit()` 仍用实际 `_complete_arms()` 判成功，因此可能返回 `success` 但 `score=50`，这是 partial，不是假成功。

**但** `comp_judge_conformance.py::test_t_stairs_full_partial_and_history` 的 `j_merge` 用例在 `y=-5.1` 已离开 `t_stairs` zone（`ZONES["t_stairs"]` ymin=-4.95），实际走的是“退出后 partial 锁定”，不是“同 zone 内落地后第二臂”。因此该 conformance 用例不能证明同 zone 合并路径已被覆盖。源码静态看是有封堵的，但证据链需补真正留在 zone 内的反例。

**非阻塞边界**：当前锁存依赖采样到 `len(ground_feet)>=2`。若真实/对抗路径以单足地面接触完成从 s 到 e 的过渡，理论上可能不触发 `arms_before_ground` 锁存。常规 MuJoCo 步态和现有 conformance 未覆盖；建议 C1/对抗集补“单足地面过渡”用例确认。暂不判 blocker。

---

## 2. B2：绕杆拐角与乱序

### PASS（有半径口径 minor）

`comp_part1_judge.py::Slalom._on_sample` 当前：

- `corner_visits` 记录每次进入拐角圆时的 `len(order)`，不再首次锁存；
- `SLALOM_CORNER_RADIUS_M = 0.30`；
- `_check_immediate` / `_check_exit` 要求期望时序 `A=3 / B=2` 出现在 `corner_visits`；
- `early_posts` 记录 `idx` 之后的未来杆提前到访；`_check_immediate` / `_check_exit` 要求 `early_posts` 为空，否则 `post_out_of_order`。

`comp_judge_conformance.py::test_slalom_forward_reverse_and_spoof` 覆盖：

- `early_then_legal`：提前扫过拐角后仍可合法通过；
- `early_corner`：拐角时序不对拒绝；
- `early_future_post`：提前碰未来杆后再补正确序列仍失败；
- 缺拐角由 `_check_exit` 的 `missing_corner_checkpoint` 拒绝。

**结论：B2 的“提前扫拐角不误杀、乱序/缺拐角仍拒绝”在源码与 conformance 下成立。**  
**minor**：judge 拐角半径 0.30 m vs 场景显示圆 0.5 m。当前 route 走圆心不受影响，但合法路径若只经过显示圆边缘（0.30–0.50 m）会被判 `missing_corner_checkpoint`，需 C1 定口径。

---

## 3. B3 / B5

### B3：源码 PASS；conformance 反例有缺口

`TStairs._has_incomplete_arm()` 对任一臂 `levels` 非空且 `< {1,2,3}` 返回 True；`TStairs._check_exit` 中 `incomplete_step_history` 拒绝。  
因此“另一臂缺级 + 本臂完整”在源码上不会得分。

**但** `comp_judge_conformance.py::test_t_stairs_full_partial_and_history` 的 `skipped_level_plus_complete_other` 用例中：

```text
{"x":1.8,"y":-5.3,"tags":["step:s:1"]}
```

`t_stairs` zone 的 ymin=-4.95，`y=-5.3` 已在 zone 外，`s:1` 不会被记录；该用例实际是“n 缺级 + s 也不完整”，不是声称的“n 缺级 + s 完整”。  
所以 B3 源码语义正确，但该 conformance 反例没有真正证明目标场景。建议把 `s:1` 放到 zone 内（例如 y=-4.9 附近）并保留 n 缺级，再断言失败。

### B5：PASS

`comp_part2_judge.py::Part2JudgeV2.update` 中：

```text
if cond:
    self.held += dt
    if self.held >= hold_s: success
else:
    self.held = 0.0
```

`run_self_test` 的 `interrupted` / `continuous` 用例覆盖“中断清零、连续成功”。  
**minor**：`_hold_ok` 仍是 dead code。

---

## 4. route

### slope：PASS

`config/part1-route.json` 当前：

- `to_slope = [5.2, -6.3]`
- `cross_slope = [5.2, -4.2]`

沿 y 跨度 2.1 m；`Slope._on_sample` 只累计坡面接触期间 `abs(y - last_y)`，判分轴匹配。`test_slope_projection_and_graze_reset` 覆盖投影、横移不计、landing、mid-slope fall、soft-reset 后干净重入。

### slalom：PASS（有半径 minor）

route 含：

- `to_slalom -> slalom_p1 -> slalom_p2 -> slalom_posts -> slalom_corner -> slalom_exit`
- `slalom_corner = [1.55, -12.75]` 正好是 judge 拐角圆心。

0.30 m judge 半径可命中；路径也按 A 方向 post0→post1→post2→corner→post3→end 组织。  
**minor 同 B2：judge 0.30 m vs 场景显示 0.5 m。**

### bridge_blocks：PASS

- `to_bridge_blocks = [0.8, 0.0]` 在 zone 西侧外；
- `cross_bridge_blocks = [6.5, 0.0]` 从 xmin 进、xmax 出；
- B1 修复后东侧平台外落地不再误判。

### bridge_bands：PASS

- `stage_bridge_bands_south = [5.7, -4.5]` 在 zone 南侧外；
- `to_bridge_bands = [5.7, -3.6]` 从 ymin 进；
- `cross_bridge_bands = [5.7, -0.5]` 从 ymax 出；
- B1 修复后北侧平台外落地不再误判。

### height_bar：route 语义正确，但 course diag 仍失败

`comp/eval/flat-ft-2500-part1-course-diag/summary.json` 三次 attempt 均为：

```text
height_bar: wrong_exit_side
```

`comp/audits/evidence/part1_course_pause_resume_drill.json` 也显示：

```text
height_bar: in_zone_samples=15770, touched=false, failures=["wrong_exit_side"]
```

这不是 gate 语义 blocker，但说明脚本化 route 对跟踪误差不鲁棒；C2 若复用该 route 会缺一项。属正式链路缺口/G1 残余。

---

## 5. 回归与证据链

### conformance 13 组

`comp_judge_conformance.py::main` 仍列 13 组；B1/B2/B3/B5 对应用例存在。但有两个证据缺口：

1. `j_merge` 名义同 zone 合并，实际在 `y=-5.1` 已出 `t_stairs` zone；
2. `skipped_level_plus_complete_other` 的 `s:1` 在 `y=-5.3` 已出 zone，未真正覆盖“另一臂缺级 + 本臂完整”。

源码静态看 B1 同 zone 合并、B3 缺级拒绝均成立，但 conformance 反例需修正后才算证据闭环。

### self-test

`comp_part1_course.run_self_test`、`comp_part2_judge.run_self_test`、`comp_score.run_self_test`、`comp_import_selftest.py`、`check_part1_scene_v2.py` 用例路径存在；未附 stdout，不能形式证明实际执行。未发现本轮修复直接引入的旧回归。

### 四份产物 summary↔trials

| 产物 | trials | summary 对账 |
|---|---:|---|
| `flat-ft-2500-part1-diag-v2` | 8 | 8 障碍 fail，attempts_used=8；逐条失败原因一致 |
| `flat-ft-2500-part2-diag-v2` | 20 | `attempts_used=4/4/4/4/3/1` 与 trials 计数一致 |
| `flat-ft-2500-part2-official-diag` | 24 | 每 category 4 次，attempt 1–4 编号正确 |
| `flat-ft-2500-part1-course-diag` | 24（3×8） | attempts_used=3；`final_time_s=109.25999999997266` 与 trial 109.26 在 `comp_score` 1e-6 容差内一致 |

course diag 的 `height_bar: wrong_exit_side` 与 trials 一致；其余 7 项为 `route_complete`，无假成功。

### HASHES

`comp/audits/HASHES.json` 当前 **66 objects**；四份产物 manifest/trials/summary、三份演练证据、judge/geom/course/scene/route/levels 等与 payload sha256 匹配。四份 manifest 的 judge hash 均为当前：

- `comp_part1_judge.py = 7496f093...`
- `comp_part1_geom_tags.py = 79ce2d9d...`
- `comp_part1_course.py = 9adf6d36...`
- `comp_part2_judge.py = 733aa34f...`

与 HASHES 中条目一致。`HASHES` 仍 `audited=false / verdict=pending`，属 G1 前状态，不是本轮 blocker。

---

## 6. 新问题 / 残余

### 非 blocker，但需 G1/C1 处理

1. **conformance `j_merge` 无效**：实际在 `y=-5.1` 已出 `t_stairs` zone，未覆盖同 zone 内落地合并；需补真正留在 zone 内的反例。
2. **conformance B3 反例无效**：`s:1` 在 `y=-5.3` 已出 zone，未覆盖“n 缺级 + s 完整”；需把 `s:1` 放回 zone 内。
3. **TStairs 单足地面过渡边界**：`arms_before_ground` 只在 `len(ground_feet)>=2` 时锁存；若以单足地面接触完成 s→e 过渡，理论上可能绕过锁存。需 C1/对抗用例确认。
4. **slalom 半径口径**：judge 0.30 m vs 场景显示圆 0.5 m；合法路径只经显示圆边缘可能被误判 `missing_corner_checkpoint`。
5. **height_bar course diag 仍 `wrong_exit_side`**：route 语义正确但跟踪不鲁棒；C2 若复用脚本 route 会缺项。
6. **importer 默认旧 V1**：`comp_import_diagnostic.py` 默认 `DEFAULT_JUDGE` 仍指 `part1_event_judge.py`，`DEFAULT_SCENE` 仍指 V1 场景；当前产物因显式 override 正确，但默认路径是正式链路缺口。
7. **文档/协议陈旧**：`CONTRACT.md §6` 仍列旧 V1 场景/judge；`_protocol.md` 仍 draft，且 §8 仍写“T 台阶部分分 Q2 数值冲突未裁决（当前保守 75/50）”，与 §6.2 已确认 50/33 不一致。
8. **HASHES pending**：`audited=false / verdict=pending`，需 G1 结论后更新。

---

## 7. 结论

- **verdict：CONCERN**
- **blocker：无**。B1/B2/B3/B5/route 的当前源码主路径未发现可复现 scorer blocker；V29 的同 zone 合并路径在源码上被 `arms_before_ground`/`_eligible_arms()` 封住。
- **但 conformance 证据有两个无效反例**（`j_merge`、`skipped_level_plus_complete_other`），且 `height_bar` course route 仍失败；这些应在 G1 最终 acquittal 前清理。
- **是否建议进入下一阶段**：**yes（有条件）**。C1 人工标定可进；C2 基线若复用当前脚本 route，需先修/声明 `height_bar` route，并补上述 conformance 反例。若必须单一 yes/no：**C1 yes；C2 暂缓**。

## G1 必写残余

1. 砂砾坑真实“坑 + 碎木”几何未 recut；当前仍是凸起盒代理。
2. Part2 官方能力场未逐档交叉核对；official 重复最高档统计意义有限。
3. soft-reset 阈值与相邻 zone 重叠仍是启发式。
4. T 台阶 s/n/e ↔ 上/下映射、障碍级跳过是否消耗整场尝试、pause_timeout 120 s 自定协议常量仍需书面确认。
5. 正式手动/操作手 3 次整场演练未在真实赛程完成；当前只有脚本化诊断与 pause/resume、abort、pause_timeout 演练。
6. B4/B6/B7 保守向判罚留待 C1 标定裁决：限高杆未校验“从下方”、Part2 高墙必须墙接触、沟壑 lane ±0.7 偏保守。
7. Part1 单障碍诊断 importer 的 per-obstacle 汇总口径仅用于诊断；正式以 course importer 为准。
8. `comp/eval/_protocol.md` 仍为 draft；`HASHES.json` 仍 `audited=false / verdict=pending`。
9. 跨 attempt 模拟器时间重置后，事件时间线不能全局排序。
10. Part2 稳定性 ≥100 次、目标 0 失败未执行；`comp/eval/_calibration/` 人工标定集仍为空。
11. slalom judge 拐角半径 0.30 m 与场景显示圆 0.5 m 不一致，需在标定集或协议中定口径。
12. height_bar course diag 仍 `wrong_exit_side`；route 语义正确但实际跟踪鲁棒性不足。
13. **本轮新增必写**：conformance `j_merge` 在 `y=-5.1` 已出 `t_stairs` zone，未真正覆盖“同 zone 内落地后第二臂不得升级”；需补真正 zone 内反例。
14. **本轮新增必写**：conformance `skipped_level_plus_complete_other` 的 `s:1` 在 `y=-5.3` 已出 zone，未真正覆盖“另一臂缺级 + 本臂完整”；需把样本放回 zone 内重测。
15. **本轮新增必写**：`TStairs._on_sample` 的 `arms_before_ground` 仅由 `len(ground_feet)>=2` 样本锁存；单足地面过渡是理论未封边界，需 C1/对抗用例确认。
16. **本轮新增必写**：`comp_import_diagnostic.py` 默认 judge/scene 仍指 V1；`CONTRACT.md §6` 仍列旧 V1 资产；`_protocol.md §8` 仍有“75/50 未裁决”陈旧表述。
