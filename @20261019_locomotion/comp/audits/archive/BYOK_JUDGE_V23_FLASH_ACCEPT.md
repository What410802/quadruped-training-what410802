verdict：**CONCERN**
- scorer blocker：**无**（B1/B2/B3/B5 的 judge 代码本身已不再构成“合法通过被误判失败”的结构性 blocker）。
- 正式链路缺口：有 1 项 —— 诊断 route 的 **bridge_blocks 出口方向仍错配**（`cross_bridge_blocks` target 未达 xmax，下一段从 ymin 离开，触发 `wrong_exit_side`）。这是 flash 第 22 轮已报的 CONCERN 遗留；本轮修复只改了入口 `to_bridge_blocks`，未改出口。属于 C2 基线前必须清理项，但不算 scorer blocker（route 明确是 P0 诊断 harness，正式赛程为操作手手动跑）。

> 说明：artifact 未附行号，以下按“文件::函数/代码段”定位，不臆造行号；结论以源码静态复核 + artifact/HASHES 为准，未附本轮 stdout，不能形式证明“实际执行过”。

---

## 1. B1：离障落地门控

### 结论：**代码层 PASS；证据层 CONCERN（route 侧，非 judge 侧）**

`comp_part1_judge.py::_Obstacle.update` 的判罚条件现为：

- `self.ground_fail and self._ground_penalty_active(xy, tags) and len(ground_feet) >= 2`

`_ground_penalty_active` 默认返回 `supported`；各障碍覆盖：

| 障碍 | 覆盖函数 | 复核 |
|---|---|---|
| `bridge_blocks` / `bridge_bands` | `TraversalBridge._ground_penalty_active` | `bridge_hits >= 3` 且 `platforms >= 2` 后关闭。中途坠落（未双平台/未满 3 桥面命中）仍 `ground_penalty_active=True`，`two_feet_ground` 仍触发。**代码 PASS** |
| `gravel_pit` | `GravelPit._ground_penalty_active` | `gravel_hits >= 3` 且 base 距对应短边 ≤ `EXIT_GRACE_M=0.35` 后关闭；entry 为 `xmin/xmax` 时返回 True（永不关闭），但规则要求短边进出，方向合法时通过。**代码 PASS** |
| `t_stairs` | `TStairs._ground_penalty_active` | `top=True` 且 `_complete_arms() >= 1` 后关闭；部分臂落地允许。**代码 PASS** |
| `slope` | `Slope._ground_penalty_active` | 累计投影 `distance >= 1.0` 后关闭；不足 1 m 时触地仍失败。**代码 PASS** |
| `height_bar` / `high_wall` / `slalom` | `ground_fail=False` | 不受门控影响。 |

`comp_judge_conformance.py::test_bridge_ground_and_success / test_t_stairs_full_partial_and_history / test_slope_projection_and_graze_reset / test_gravel_short_edges_and_long_edge` 已覆盖：
- bridge_blocks legal + landing + mid_gap；
- bridge_bands band_landing + band_mid_fall；
- t_stairs partial_landing（采样 y=-4.9 在 zone 内）+ early_ground；
- slope landing（>=1 m 后落地允许）；
- gravel landing（远短边落地允许）+ mid_pit（中段触地失败）。

四个 ground_fail 障碍（bridge_blocks / bridge_bands / gravel_pit / t_stairs / slope）**覆盖完整**。

### B1 证据侧 CONCERN

`comp_part1_judge.py::TraversalBridge._check_exit` 要求：

```python
entry = self.evidence.get("entry_side_prev")
if entry is None: return False, "illegal_entry"
if side != _opposite(entry): return False, "wrong_exit_side"
```

`config/part1-route.json::cross_bridge_blocks` target 是 `[6.0, 0.0]`，未达 zone xmax=6.3；下一段 `to_bridge_bands` target (5.7,-3.6) 会穿越 ymin=-1.0，因此 bridge_blocks 的 exit_side=ymin，而 entry_side=xmin → `_opposite("xmin")="xmax"` ≠ `"ymin"` → `wrong_exit_side` 失败。

这不是 judge 误判（judge 正确拒绝了错误出口），而是 route 出口方向仍在错配。GLM 第 20 轮 B1 修复关闭了地面判罚，但方向门控未变，route 的 bridge_blocks 出口仍未修正。

---

## 2. B2：绕杆拐角

### 结论：**PASS**

`comp_part1_judge.py::Slalom._on_sample` 已改为：

- 拐角改为 `corner_visits` 记录每次进入拐角圆时的杆数 `len(ev["order"])`（去重）；
- 拐角半径从 0.5 收窄到 `SLALOM_CORNER_RADIUS_M = 0.30`；
- 成功条件 `_check_immediate` / `_check_exit` 改为 `expected_corner_after in ev["corner_visits"]`（A=3、B=2）。

`comp_judge_conformance.py::test_slalom_forward_reverse_and_spoof` 已覆盖：
- `early_then_legal`：提前扫过拐角（count=2）后再合法经过（count=3），成功；
- `early_corner`：只有 count=2 不过合法点，拒绝；
- `out_of_order`：跳过 post0，`missing_posts` 拒绝；
- 缺拐角：`missing_corner_checkpoint` 拒绝；
- 早终点：`no_end_area` / `missing_posts` 拒绝。

**提前扫过拐角不再误杀合法路径；乱序/缺拐角仍拒绝。** 代码层 PASS。

---

## 3. B3 / B5

### B3：T 台阶另一臂缺级
### 结论：**PASS**

`comp_part1_judge.py::TStairs._check_exit` 已加：

```python
if self._has_incomplete_arm():
    return False, "incomplete_step_history"
```

`_has_incomplete_arm` 对任一 `levels` 非空且 `levels < {1,2,3}` 的臂返回 True。

`comp_judge_conformance.py::test_t_stairs_full_partial_and_history` 的 `skipped_level_plus_complete_other` 用例（n 臂缺 n:2、s 臂完整 +top）断言 `not_success`，正确拒绝。同时保留了 `n 臂完整 = 33`、`e 臂完整 = 33`、`s 臂完整 = 50`、`两臂完整 = 100`、`partial 可升级为 full` 的行为。

### B5：Part2 hold 连续
### 结论：**PASS**

`comp_part2_judge.Part2JudgeV2.update`：

```python
if cond:
    self.held += dt
    if self.held >= hold_s: self.result.status = "success"
else:
    self.held = 0.0   # "hold" means continuous; an interruption resets the timer
```

`run_self_test` 的 `interrupted` 用例（2.5→1.0→2.5，中途打断）断言 fail；`continuous` 用例（三次连续 2.5）断言 success。**断续满足条件不再成功。**

---

## 4. route

### 结论：slope（PASS）、slalom（PASS）、bridge_bands（PASS）、bridge_blocks（**CONCERN**）、其余（PASS）

`config/part1-route.json` 复核：

| 段 | 实际路径 | 判定 |
|---|---|---|
| `cross_slope` | `to_slope` target (5.2,-6.3) → `cross_slope` target (5.2,-4.2)，跨度 2.1 m 沿 y；`Slope._on_sample` 累计 `|Δy|` → 判分轴匹配 | **PASS**（沿判分轴走，≥1 m） |
| `slalom_corner` | target 恰为 `(1.55,-12.75)`（拐角圆心），半径 0.30 m 命中 | **PASS**（经过拐角必达区） |
| `cross_bridge_bands` | `to_bridge_bands` (5.7,-3.6) → `cross_bridge_bands` (5.7,-1.0)，`to_gravel` 从 ymin=-4.0 离开；entry=ymax、exit=ymin 正确 | **PASS** |
| `cross_bridge_blocks` | `to_bridge_blocks` (0.8,0.0) → `cross_bridge_blocks` (6.0,0.0)，下一段 `to_bridge_bands` 从 ymin=-1.0 离开，entry=xmin、exit=ymin → `wrong_exit_side` | **CONCERN**（正式链路缺口） |
| `cross_height_bar` | 从 (5.7,-10.2) 到 (5.7,-8.2)，穿过 y=-9.0 且 x∈门洞 [5.2,6.2] | **PASS**（gate 语义正确；不通过是策略问题） |
| `cross_high_wall` | 从 (1.8,-8.0) 到 (1.8,-6.0)，穿越 y=-7.0 且 x=1.8∈[1.30,2.30] | **PASS**（不通过是策略未抬升问题） |
| `cross_gravel` | 从 (5.0,-13.4) 到 (5.5,-10.9)，entry=ymin、exit=ymax | **PASS** |
| `cross_t_stairs` | 从 (1.8,-5.6) 到 (1.8,-2.0)，entry=ymin、exit=ymax | **PASS**（无完整臂是策略问题） |

**B1 修复只解决了地面判罚；bridge_blocks 方向错配是 route 层独立缺口，未被本轮修复覆盖。**

---

## 5. 回归与证据链

### HASHES

`comp/audits/HASHES.json` 共 66 objects（26 主+19 level+12 产物+6 extra+3 evidence），与 payload 中的 sha256 逐项一致：

- `judge_part1_v2_1` = `bec8ff07…`；
- `judge_part2_v2` = `733aa34f…`；
- `judge_course_protocol` = `9adf6d36…`；
- `scene_part1_v2` = `c03cd34a17…`；
- `part1_route` = `976bae80…`；
- 4 份产物的 manifest/trials/summary 均列入且匹配。

`audited=false / verdict=pending` 是 G1 前预期状态。

### 四份产物 summary↔trials

- `flat-ft-2500-part1-diag-v2`：8 trials / summary 8 障碍 fail；evidence trial_id 与对应 trial 一致。
- `flat-ft-2500-part2-diag-v2`：20 trials（4/4/4/4/3/1）/ summary attempts_used 一致；trial_id 唯一。
- `flat-ft-2500-part2-official-diag`：24 trials（每 category 4 次，attempt 1–4 正确编号）；summary attempts_used 一致。
- `flat-ft-2500-part1-course-diag`：24 trials（3 attempts × 8 障碍）；summary final_time_s=96.199… 与 trial duration 一致；未触发 return bonus（全 0）。

### self-test / conformance

- `comp_judge_conformance.py` 13 组静态复核自洽；用例覆盖 G1/GLM 历史反例（spoof 出口、approach ground、retry、bridge/bar/wall/stairs/slope/gravel/slalom、scene geom tags）。
- `comp_part1_course.py::run_self_test`：900 分全通过、暂停时间剔除、partial 不触发 return、recovery_pose_violation、StableStopTracker 物理 dt。
- `comp_part2_judge.py::run_self_test`：B5 interrupted/continuous、spoof/lateral bypass、gap no_cross、wall 无墙接触、plum 站地面、bool 只认 1、floor/端点 0。
- `comp_score.py::run_self_test`：skipped 正分排除、错误 final_time、tamper hash、非法 Part2 档位、空 hash/level 条目、重复 trial_id。
- `comp_import_selftest.py`：全 skipped 场景 → 0/0/无 evidence。
- `check_part1_scene_v2.py`：空场景横杆静置 <1 cm。

### 回归结论

B1/B2/B3/B5 修复、route slope/slalom 修复均未引入回归；judge 无新假成功通道（spoof 类封堵仍有效）。**无新 scorer blocker。**

---

## 6. 新问题

1. **route bridge_blocks 出口错配（CONCERN 级，正式链路缺口）** —— `cross_bridge_blocks` target (6.0,0.0) 未达 xmax=6.3；`to_bridge_bands` 从 ymin 离开触发 `wrong_exit_side`。flash 第 22 轮已报；本轮 fix map 22 轮只修了 `to_bridge_blocks` 入口，未改 `cross_bridge_blocks` 出口。属于 C2 前必须清理项，但不算 scorer blocker（route 是 P0 诊断 harness；正式赛程为手动）。
2. **HASHES 中 `eval_part1_diag` / `eval_part2_diag` / `eval_course_diag` 与 `eval_flat-ft-2500-*_summary` 是同一文件的两个键** —— 冗余哈希项，不破坏校验，但重复 I/O；minor。
3. `comp_part2_judge._hold_ok` 仍是 dead code（`update` 里已内联 else 清零）—— minor。
4. `comp_score.py` 顶部重复 `import tempfile` —— minor，不阻塞。

无新假成功通道；无新误判失败 blocker。

---

## 7. 结论

**verdict：CONCERN**

- blocker：**无**（B1 修复已消除结构性“合法通过被误判失败”；B2/B3/B5 修复闭环；spoof 类通道仍封堵）。
- 正式链路缺口：1 项（route bridge_blocks 出口方向），属 CONCERN 级，C2 前须清。
- 证据链（HASHES 66 objects、summary↔trials、conformance/self-test、course/part2/score/importer self-test、三份 drill 证据）：**一致**。
- 是否建议进入下一阶段：**yes**（C1 人工标定可开始；C2 基线评测前先修 route bridge_blocks 出口 —— 这是 CONCERN 清理项，不是 scorer blocker）。

---

## G1 必写残余

1. **砂砾坑真实“坑+碎木”几何未 recut**（本地为凸起盒代理）；recut 后 B1 的 gravel 出口 0.35 m grace 须按真实几何复核。
2. **Part2 官方能力场逐档交叉核对未做**；本地为同种类参数化 level；official 重复最高档在确定性策略下统计意义有限。
3. **soft-reset 阈值与相邻 zone 重叠仍是启发式**（真实整场顺序通过影响有限）。
4. **T 台阶 s/n/e ↔ 上/下映射（s=上、n/e=下）、障碍级跳过是否消耗整场尝试、pause_timeout 120 s（自定协议常量）** 需书面确认。
5. **正式手动 3 次整场演练未在真实赛程完成**；当前为脚本化 3-attempt 演练 + pause/abort/pause_timeout drill。
6. **B4/B6/B7 保守向判罚留待 C1 标定裁决**：限高杆跳过（理论性）、Part2 墙必须接触、沟壑 lane ±0.7 偏保守。
7. **Part1 单障碍诊断 importer 的 per-obstacle 汇总口径**仅用于诊断；正式以 course importer 为准。
8. **`comp/eval/_protocol.md` 仍为 draft**，未冻结正式 `protocol_version`。
9. **`HASHES.json` 仍 `audited=false / verdict=pending`**，需 G1 结论后更新。
10. **跨 attempt 模拟器时钟重置**后，事件时间线不能全局排序。
11. **Part2 稳定性 ≥100 次、目标 0 失败未执行**；`comp/eval/_calibration/` 人工标定集仍为空。
12. **本轮新增**：route bridge_blocks 出口方向错配（`cross_bridge_blocks` target 未达 xmax），需修 `config/part1-route.json` 才能完整验证诊断链路。
13. **HASHES 冗余键**（`eval_part1_diag`/`eval_part2_diag`/`eval_course_diag` 与 `eval_flat-ft-2500-*_summary` 指向同一文件）建议清理。
