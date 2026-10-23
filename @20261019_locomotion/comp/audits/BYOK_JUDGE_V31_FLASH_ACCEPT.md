verdict：**CONCERN**  
blocker：**无当前可复现 scorer blocker**  
下一阶段：**C1 人工标定 = yes；C2 基线评测 = no（暂缓，需先清理 height_bar route 与 TStairs 单足边界）**

> artifact 未附行号；以下按 `文件::函数/代码段` 定位，不臆造行号。结论为静态源码 + 给定 conformance/产物/HASHES 复核；未附本轮 stdout，因此“通过”不等于执行日志形式证明。

---

## 1. B1：离障落地门控

### 主语义：PASS

`comp_part1_judge.py::_Obstacle.update` 仍有双侧门控：

- inside 分支：`if self.ground_fail and self._ground_penalty_active(xy, tags) and len(ground_feet) >= 2: self._fail("two_feet_ground:...")`
- 退出成功分支：`if ok and self.ground_fail and not self.supported: self._fail("insufficient_obstacle_support")`
- immediate 成功分支同样检查 `ground_fail and not self.supported`。

因此“从未全足支撑、仅单足蹭 tag 后从对侧离开”不能假成功。

`ground_fail` 实际覆盖 **5 个 ID**：`bridge_blocks`、`bridge_bands`、`gravel_pit`、`t_stairs`、`slope`。

| 障碍 | 门控函数/条件 | 结论 |
|---|---|---|
| `bridge_blocks` | `TraversalBridge._ground_penalty_active`：`bridge_hits >= 3` 且两个 platform tag 都命中后关闭地面判罚 | 完成跨越后落地合法；桥面中段双足触地仍在证据完成前判失败。conformance 覆盖 landing + mid-gap fall。 |
| `bridge_bands` | 同上 | 南→北 landing 合法；中段双足触地失败。conformance 覆盖 `bands_landing`/`bands_mid_fall`。 |
| `gravel_pit` | `GravelPit._ground_penalty_active`：`supported` 且 `gravel_hits >= 3` 后，按入口侧距出口短边 `EXIT_GRACE_M=0.35` 关闭 | 远短边落地合法；坑中段双足触地仍失败。conformance 覆盖 landing/mid-pit。 |
| `slope` | `Slope._ground_penalty_active`：累计 y 投影 `>= 1.0 m` 后关闭 | 完成后落地合法；中途双足触地仍失败。conformance 覆盖 landing/mid-fall/soft-reset。 |
| `t_stairs` | `TStairs._ground_penalty_active`：`top` + 至少一条完整臂后关闭 | partial 落地合法；未完成前双足触地仍失败。conformance 覆盖 `early_ground` 失败与 `partial_landing` 允许。 |

**B1 主语义成立，未发现“完成跨越后落地被误判失败”的可复现 blocker。**

### 但有一个 TStairs 过严边界需记入 C1/残余

`TStairs._on_sample` 当前快照条件是：

```text
if (len(ground_feet) >= 1 and self.evidence.get("top")
        and len(self._complete_arms()) >= 1
        and self.evidence.get("arms_before_ground") is None):
    self.evidence["arms_before_ground"] = ...
```

而 `BYOK_JUDGE_V2_FIXES.md` 第 29 轮写的是“首次出现 **≥2 足触地**时快照”。当前源码是 **≥1**，比修复声明和规则“≥2 足才失败”更严格。它不会造成假成功，反而可能把“单足落地且最后一级同采样”的合法连续 T 台阶压成 50 分。常规 route 会先记录最低级再落地，因此我暂不判 blocker，但这是 C1/对抗用例必须确认的边界；若确认可触发合法满分路径被压成 50，应升级为 blocker。

---

## 2. B2：绕杆拐角与乱序

### PASS

`comp_part1_judge.py::Slalom._on_sample`：

- `corner_visits` 记录每次进入拐角圆时的杆数，不再首次锁存；
- `SLALOM_CORNER_RADIUS_M = 0.30`；
- `early_posts` 记录 `idx` 之后未来杆的提前到访。

`Slalom._check_immediate` / `_check_exit` 要求：

- 期望时序 `A=3 / B=2` 出现在 `corner_visits`；
- `early_posts` 为空；
- 四杆顺序、终点区、S 形侧向交替均满足。

`comp_judge_conformance.py::test_slalom_forward_reverse_and_spoof` 覆盖：

- `early_then_legal`：提前扫过拐角后仍可合法通过；
- `early_future_post`：提前碰未来杆后再补正确顺序仍失败；
- `early_corner`：拐角时序不对拒绝；
- 缺杆/缺拐角拒绝。

**B2 的“提前扫拐角不误杀、乱序/缺拐角仍拒绝”成立。**

minor：judge 拐角半径 `0.30 m` 与场景显示圆 `0.5 m` 不一致；当前 route 走圆心不受影响，但合法路径只经过显示圆 0.30–0.50 m 边缘时可能被判 `missing_corner_checkpoint`，需 C1 定口径。

---

## 3. B3 / B5

### B3：PASS

`TStairs._has_incomplete_arm()`：

```text
any(levels and levels < {1, 2, 3} for levels in self.evidence["arms"].values())
```

`TStairs._check_exit` 对 `incomplete_step_history` 拒绝。  
conformance `skipped_level_plus_complete_other` 当前样本 `s:1` 在 `y=-4.9`，已在 `t_stairs` zone 内（zone ymin=-4.95），因此该反例这次真正覆盖“n 臂缺级 + s 臂完整”仍不得分。**B3 成立。**

### B5：PASS

`comp_part2_judge.py::Part2JudgeV2.update`：

```text
if cond:
    self.held += dt
    ...
else:
    self.held = 0.0
```

`run_self_test` 的 `interrupted` / `continuous` 覆盖“中断清零、连续成功”。**B5 成立。**  
minor：`_hold_ok` 仍是 dead code；不影响判分。

---

## 4. route

### slope：PASS

`config/part1-route.json`：

- `to_slope = [5.2, -6.3]`
- `cross_slope = [5.2, -4.2]`

沿 y 跨度约 2.1 m；`Slope._on_sample` 只累计 `"slope"` tag 接触期间的 `abs(y - last_y)`，判分轴匹配。conformance `test_slope_projection_and_graze_reset` 覆盖投影、横移不计、landing、mid-fall、soft-reset 重入。

### slalom：PASS（半径口径 minor）

route 含：

- `to_slalom -> slalom_p1 -> slalom_p2 -> slalom_posts -> slalom_corner -> slalom_exit`
- `slalom_corner = [1.55, -12.75]` 正好是 judge 拐角圆心。

A 方向 post0→post1→post2→corner→post3→end B 可命中；`slalom_exit` 路径经过 post3 附近。  
minor 同 B2：judge 0.30 m vs 场景显示 0.5 m。

### bridge_blocks：PASS

- `to_bridge_blocks = [0.8, 0.0]` 在 zone 西侧外；
- `cross_bridge_blocks = [6.5, 0.0]` 从 xmin 进、xmax 出；
- B1 修复后，到达 `platform_right` 后下地面不再误判。

### bridge_bands：PASS

- `stage_bridge_bands_south = [5.7, -4.5]` 在 zone 南侧外；
- `to_bridge_bands = [5.7, -3.6]` 从 ymin 进；
- `cross_bridge_bands = [5.7, -0.5]` 从 ymax 出；
- B1 修复后，北侧平台外落地不再误判。

### height_bar：route 语义正确，但脚本化 course diag 仍失败

`comp/eval/flat-ft-2500-part1-course-diag/summary.json` 三次 attempt 均为：

```text
height_bar: wrong_exit_side
```

`comp/audits/evidence/part1_course_pause_resume_drill.json` 也显示：

```text
height_bar: in_zone_samples=15770, touched=false, failures=["wrong_exit_side"]
```

这不是 judge gate 语义 blocker，而是脚本化 waypoint 对跟踪误差不鲁棒：`to_height_bar` 前缺少足够南侧 staging，机器人在实际跟踪中可能从 xmin 进入而最终从 ymax 离开。C2 若复用当前脚本 route，会缺 height_bar 一项。

---

## 5. 回归与证据链

### conformance 13 组

`comp_judge_conformance.py::main` 仍列 13 组；B1/B2/B3/B5 对应用例存在，且本轮关键反例已修正：

- `bridge_blocks`/`bridge_bands` landing 与 mid-fall；
- `gravel_pit` landing 与 mid-pit；
- `t_stairs` `early_ground` 失败、`partial_landing` 允许、`j_merge` 同 zone 合并封顶 50、`j_lock` 退出后 partial 不升级、`skipped_level_plus_complete_other` 缺级拒绝；
- `slope` landing/mid-fall/soft-reset；
- `slalom` early-corner 宽容、early-future-post 拒绝。

静态看无新回归；未附 stdout，不能形式证明实际执行。

### 四份产物 summary↔trials

| 产物 | trials | summary 对账 | 结论 |
|---|---:|---|---|
| `flat-ft-2500-part1-diag-v2` | 8 | `attempts_used=8`；8 障碍全 fail，失败原因与 trials 一致 | 一致 |
| `flat-ft-2500-part2-diag-v2` | 20 | `attempts_used=4/4/4/4/3/1`，与 trials 计数一致 | 一致 |
| `flat-ft-2500-part2-official-diag` | 24 | 每 category 4 次，attempt 1–4 编号正确 | 一致 |
| `flat-ft-2500-part1-course-diag` | 24（3×8） | `attempts_used=3`；`final_time_s=109.25999999997266` 与 trial 109.26 在 1e-6 容差内一致；`height_bar: wrong_exit_side` 与 trials 一致 | 一致 |

未发现新的假成功；course diag 的 `height_bar` 失败是正式链路缺口/route 鲁棒性问题，不是 judge 假成功。

### HASHES

`comp/audits/HASHES.json` 当前 **66 objects**；四份产物 manifest/trials/summary、三份演练证据、judge/geom/course/scene/route/levels 等 sha256 与 payload 一致。四份 manifest 的 judge hash 与当前源码一致：

- `comp_part1_judge.py = 98ee9b96...`
- `comp_part1_geom_tags.py = 79ce2d9d...`
- `comp_part1_course.py = 9adf6d36...`
- `comp_part2_judge.py = 733aa34f...`

`HASHES.json` 仍 `audited=false / verdict=pending`，属 G1 前状态，不是本轮 blocker。

---

## 6. 新问题 / 需 C1 或 G1 处理

1. **TStairs 快照阈值偏严**：`TStairs._on_sample` 当前用 `len(ground_feet) >= 1` 写 `arms_before_ground`，而修复说明写的是 `>=2`。它封住了 V29 的“同 zone 两臂合并”假成功，但可能把单足落地 + 最后一级同采样的合法 100 压成 50；需 C1/对抗用例确认。
2. **height_bar course diag 仍 `wrong_exit_side`**：route 语义正确但跟踪不鲁棒；C2 若复用脚本 route 会缺项。
3. **CONTRACT.json 时间口径陈旧**：`parts.part1.attempts.final_time` 仍写 `min_over_attempts`，而代码与 `comp_score.validate_external_evidence` 已按“最高分尝试内取最快”执行；建议 G1 前统一文案。
4. **CONTRACT.md §6 仍列旧 V1 judge/hash**：文档清理项。
5. **slalom judge 0.30 m vs 场景显示圆 0.5 m**：C1 标定口径待裁决。
6. **`comp_part2_judge._hold_ok` dead code；`comp_score.py` 顶部重复 `import tempfile`**：非阻塞 minor。
7. **`comp/eval/_protocol.md` 仍 draft；HASHES 仍 pending**：G1 前状态。

---

## 7. 结论

- **verdict：CONCERN**
- **blocker：无当前可复现 scorer blocker**。B1/B2/B3/B5 主路径与四份产物证据链静态一致；未发现新的假成功。
- **但不宜直接放行 C2 基线**：`height_bar` course route 仍失败；TStairs `>=1` 快照边界需确认；CONTRACT/协议/HASHES 仍有陈旧或 draft 项。
- **是否进入下一阶段**：  
  - **C1 人工标定：yes**（可先标定 judge 语义与 slalom 半径、TStairs 单足边界、B4/B6/B7 保守判罚）。  
  - **C2 基线评测：no（暂缓）**。若 C2 不复用当前脚本 route 且明确声明 height_bar 不计入 route 诊断，则可另行评估；但当前脚本 route 直接跑 C2 会把 height_bar route 缺口烧进基线。

### G1 必写残余

1. 砂砾坑真实“坑 + 碎木”几何未 recut；当前仍是凸起盒代理。
2. Part2 官方能力场未逐档交叉核对；official 重复最高档统计意义有限。
3. soft-reset 阈值与相邻 zone 重叠仍是启发式。
4. T 台阶 s/n/e ↔ 上/下映射、障碍级跳过是否消耗整场尝试、pause_timeout 120 s 自定协议常量仍需书面确认。
5. 正式手动/操作手 3 次整场演练未在真实赛程完成；当前只有脚本化诊断与 pause/resume、abort、pause_timeout 演练。
6. B4/B6/B7 保守向判罚留待 C1 裁决：限高杆未校验“从下方”、Part2 高墙必须墙接触、沟壑 lane ±0.7 偏保守。
7. Part1 单障碍诊断 importer 的 per-obstacle 汇总口径仅用于诊断；正式以 course importer 为准。
8. `comp/eval/_protocol.md` 仍 draft；`HASHES.json` 仍 `audited=false / verdict=pending`。
9. 跨 attempt 模拟器时间重置后，事件时间线不能全局排序。
10. Part2 稳定性 ≥100 次、目标 0 失败未执行；`comp/eval/_calibration/` 人工标定集仍为空。
11. slalom judge 拐角半径 0.30 m 与场景显示圆 0.5 m 不一致，需 C1 定口径。
12. height_bar course diag 仍 `wrong_exit_side`；route 语义正确但实际跟踪鲁棒性不足。
13. TStairs `arms_before_ground` 当前以 `len(ground_feet)>=1` 快照，严于 V2_FIXES 的 `>=2` 说明与规则“≥2 足才失败”；需 C1/对抗用例确认是否会把合法连续满分压成 50。
14. `CONTRACT.json` 的 `attempts.final_time` 仍写 `min_over_attempts`，与代码/`comp_score` 的“最高分尝试内取最快”不一致；`CONTRACT.md §6` 仍列旧 V1 judge/hash。
15. `comp_part2_judge._hold_ok` 为 dead code；`comp_score.py` 有重复 `import tempfile`，均 non-blocking。
