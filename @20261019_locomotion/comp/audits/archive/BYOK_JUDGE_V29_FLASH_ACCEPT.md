# 第二十一轮 BYOK delta 复验结论

> artifact 未附行号，以下按 `文件::函数/代码段` 定位，不臆造行号。  
> 结论基于给定源码、conformance、四份产物与 HASHES 的静态复核；未附本轮 stdout，因此“通过”指代码路径/证据链一致，不是执行日志的形式证明。

## verdict：**FAIL**

- **blocker：有**
  - **T 台阶仍存在 scorer 假成功**：`TStairs._ground_penalty_active` 在 `top + 任一完整臂` 后关闭地面判罚，但 `TStairs._on_sample` 只对 `len(ground_feet)>=2` 的样本早退，**不会清空已记录的臂/级证据**；`TStairs._check_exit` 只检查 `top` 与“两条完整臂”，**不使用 `entry_arm/exit_arm`、方向或单次连续异臂上下约束**。机器人可在同一 `t_stairs` zone 内：上 s 臂 → 下 s 臂落地 → 地面走到 e 臂 → 再上 e 臂，最终 `_complete_arms()` 同时看到 s、e，被判 100。  
  - `locks_partial_on_exit` 只覆盖“先离开 zone、注册 partial success、再进入”的 V28 场景；**不能覆盖“未离开 zone、地面重置后继续第二臂”的合并路径**。因此 V28 指出的“两个分离 partial 合并为 100”在“同 zone 内落地再爬”变体下仍成立。
- **是否建议进入 C1/C2：no**。先修 T 台阶单次连续异臂约束并补“同 zone 内落地后第二臂不得升级”的 conformance 反例；再重跑 13 组 conformance、各 self-test、四份产物与三份演练，刷新 HASHES 后复审。

---

## 1. B1：离障落地门控

### 主语义：桥/砂砾/斜坡 PASS，T 台阶有交叉 blocker

`comp_part1_judge.py::_Obstacle.update` 有双侧门控：

- `inside` 分支 `_check_immediate` 成功后，若 `ground_fail and not supported` → `insufficient_obstacle_support`；
- `elif self.prev_in_zone` 退出成功分支同样检查 `supported`。

`_ground_penalty_active` 覆盖实际五个 ground_fail ID：

| ID | 门控 | 判定 |
|---|---|---|
| `bridge_blocks` / `bridge_bands` | `TraversalBridge._ground_penalty_active`：`bridge_hits>=3` 且两个平台 tag 命中后关闭 | 合法落地允许；桥面中段双足触地仍失败 |
| `gravel_pit` | `GravelPit._ground_penalty_active`：`supported` 且 `gravel_hits>=3` 后，按入口侧距出口短边 `EXIT_GRACE_M=0.35` 关闭 | 远短边落地允许；坑中段仍失败 |
| `slope` | `Slope._ground_penalty_active`：累计投影 `>=1.0 m` 后关闭 | 完成后落地允许；中途双足触地仍失败 |
| `t_stairs` | `TStairs._ground_penalty_active`：`top` + 至少一条完整臂后关闭 | partial 落地允许，但**门控范围过宽**，见下 |

`comp_judge_conformance.py::test_bridge_ground_and_success`、`test_gravel_short_edges_and_long_edge`、`test_t_stairs_full_partial_and_history`、`test_slope_projection_and_graze_reset` 已覆盖 bridge_blocks/bridge_bands/gravel/t_stairs/slope 的 landing 与 mid-fall 主路径。  
**B1 对桥/砂砾/斜坡的主语义成立；T 台阶门控与 B3 交叉产生假成功，不能算完全通过。**

### B1 的具体 blocker 路径

1. 进入 `t_stairs` zone，触碰 `step:s:1/2/3` 与 `step:top` → `_complete_arms()` 含 `s`。
2. `TStairs._ground_penalty_active` 因 `top` 且至少一条完整臂返回 `False`，之后双足落地不再触发 `two_feet_ground`。
3. `TStairs._on_sample` 在 `len(ground_feet)>=2` 时直接 `return`，但**不清空 `evidence["arms"]["s"]`**，也不把该次 traversal 锁定为 partial。
4. 机器人在同一 zone 内地面移动到 e 臂，再以 `<2` ground feet 攀爬 `step:e:1/2/3`；`_on_sample` 正常记录 e 臂。
5. 离开 zone 时 `TStairs._check_exit` 看到 `top` + `_complete_arms()` 含 s、e，`_has_incomplete_arm()` 为假 → success 100。

这不是“上 s、经 top、下 e”的单次异臂 traversal，而是“s 上/下 + e 上/下”的两次 partial 合并。`locks_partial_on_exit` 不触发，因为从未在 zone 外注册 partial success。

---

## 2. B2：绕杆拐角与乱序

### PASS（有半径口径 minor）

`comp_part1_judge.py::Slalom._on_sample`：

- `corner_visits` 记录每次进入拐角圆时的 `len(order)`，不再首次锁存；
- `SLALOM_CORNER_RADIUS_M = 0.30`；
- `_check_immediate` / `_check_exit` 要求期望时序 `A=3 / B=2` 出现在 `corner_visits`；
- `early_posts` 记录 `idx` 之后的未来杆提前到访；`_check_immediate` / `_check_exit` 要求 `early_posts` 为空，否则 `post_out_of_order`。

`comp_judge_conformance.py::test_slalom_forward_reverse_and_spoof` 覆盖：

- `early_then_legal`：提前扫过拐角后仍可合法通过；
- `early_corner`：拐角时序不对拒绝；
- `early_future_post`：提前碰未来杆后再补正确序列仍失败；
- `out_of_order`：缺杆/乱序拒绝；
- 缺拐角由 `_check_exit` 的 `missing_corner_checkpoint` 拒绝。

**结论：B2 的“提前扫拐角不误杀、乱序/缺拐角仍拒绝”在源码与 conformance 下成立。**  
**minor**：judge 拐角半径 0.30 m vs 场景显示圆 0.5 m；当前 route 走圆心不受影响，但合法路径若只经过显示圆边缘（0.30–0.50 m）会被判 `missing_corner_checkpoint`，需 C1 定口径或放宽/对齐显示几何。

---

## 3. B3 / B5

### B3 窄口径“另一臂缺级”：PASS

`TStairs._has_incomplete_arm()` 对任一臂 `levels` 非空且 `< {1,2,3}` 返回 True；`TStairs._check_exit` 中 `incomplete_step_history` 拒绝。  
`comp_judge_conformance.py::test_t_stairs_full_partial_and_history` 的 `skipped_level_plus_complete_other` 已断言“n 臂缺级 + s 臂完整”不成功。  
单臂完整仍保留 s=50、n/e=33 的部分分。

### 但 T 台阶整体仍有 blocker

如上节：`TStairs._check_exit` 只检查 `top` 和 `_complete_arms()`，**不使用 `entry_arm/exit_arm`，也不要求单次连续异臂上下**。  
`locks_partial_on_exit` + conformance 的 `j_lock` 用例覆盖了“partial 后退出 zone 再进入升级”的 V28 场景，但仍未覆盖：

```text
同一 zone 内：
s 臂完整 + top
→ 下 s 臂到地面（门控已关闭）
→ 地面走到 e 臂
→ 上 e 臂完整
→ 同一 zone 退出
→ _complete_arms() 见 s、e → 100
```

`TStairs._on_sample` 在 ground_feet≥2 时早退只能阻止“地面蹭级”，不能清空/作废此前的完整臂证据；因此仍存在 scorer 假成功。**这是 blocker。**

### B5：PASS

`comp_part2_judge.py::Part2JudgeV2.update` 中：

```python
if cond:
    self.held += dt
    if self.held >= hold_s:
        self.result.status = "success"
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

沿 y 跨度 2.1 m；`Slope._on_sample` 只累计坡面接触期间 `abs(y - last_y)`，判分轴匹配。  
`test_slope_projection_and_graze_reset` 覆盖投影、横移不计、landing、mid-slope fall、soft-reset 后干净重入。

### slalom：PASS（有半径 minor）

route 含：

- `to_slalom -> slalom_p1 -> slalom_p2 -> slalom_posts -> slalom_corner -> slalom_exit`
- `slalom_corner = [1.55, -12.75]` 正好是 judge 拐角圆心。

0.30 m judge 半径可命中；路径也按 A 方向 post0→post1→post2→corner→post3→end 组织。  
**minor 同 B2：judge 0.30 m vs 场景显示 0.5 m。**

### bridge_blocks：PASS

- `to_bridge_blocks = [0.8, 0.0]` 在 zone 西侧外；
- `cross_bridge_blocks = [6.5, 0.0]` 从 xmin 进、xmax 出；
- `TraversalBridge._check_exit` 的 opposite-side 条件满足；
- B1 修复后东侧平台外落地不再误判。

### bridge_bands：PASS

- `stage_bridge_bands_south = [5.7, -4.5]` 在 zone 南侧外；
- `to_bridge_bands = [5.7, -3.6]` 从 ymin 进；
- `cross_bridge_bands = [5.7, -0.5]` 从 ymax 出；
- B1 修复后北侧平台外落地不再误判。

### height_bar：route 语义正确，但 course diag 仍失败

`comp/eval/flat-ft-2500-part1-course-diag/summary.json` 三次 attempt 均：

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

`comp_judge_conformance.py::main` 仍列 13 组；B1/B2/B3/B5 对应用例存在：

- `test_bridge_ground_and_success`
- `test_gravel_short_edges_and_long_edge`
- `test_t_stairs_full_partial_and_history`
- `test_slope_projection_and_graze_reset`
- `test_slalom_forward_reverse_and_spoof`
- `test_scene_geom_tags_complete`

但 **T 台阶 conformance 缺少“同一 zone 内 s 上/下 + e 上/下 合并”的反例**；`j_lock` 只测“退出 zone 后重入升级”，不能证明本 blocker 已封。

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

`comp/audits/HASHES.json` 当前 **66 objects**；四份产物 manifest/trials/summary、三份演练证据、judge/geom/course/scene/route/levels 等与 payload sha256 匹配。  
四份 manifest 的 judge hash 均为当前：

- `comp_part1_judge.py = 825e6497...`
- `comp_part1_geom_tags.py = 79ce2d9d...`
- `comp_part1_course.py = 9adf6d36...`
- `comp_part2_judge.py = 733aa34f...`

与 HASHES 中条目一致。`HASHES` 仍 `audited=false / verdict=pending`，属 G1 前状态，不是本轮 blocker。

---

## 6. 新问题 / 残余

### 新 blocker

1. **T 台阶同 zone 内两臂合并**：`TStairs._ground_penalty_active` 在 `top + 一条完整臂` 后关闭地面判罚；`TStairs._on_sample` 只早退 ground 样本，不清空/锁定已记录臂；`TStairs._check_exit` 只检查完整臂集合，不检查单次连续异臂上下。机器人可在同一 zone 内 s 上/下 → 地面 → e 上/下，最终 100。  
   `locks_partial_on_exit` 与 `j_lock` 的 conformance 只覆盖“退出后再进入”，未覆盖此变体。

### 非 blocker / 需 C1 或 G1 记录

2. **slalom 半径口径**：judge 0.30 m vs 场景显示圆 0.5 m；合法路径只经过显示圆边缘可能被误判 `missing_corner_checkpoint`。
3. **height_bar course diag 仍 `wrong_exit_side`**：route 语义正确但跟踪不鲁棒；C2 复用脚本 route 会缺项。
4. **importer 默认旧 V1**：`comp_import_diagnostic.py` 默认 `DEFAULT_JUDGE` 仍指 `part1_event_judge.py`，`DEFAULT_SCENE` 仍指 V1 场景；当前产物因显式 override 正确，但默认路径是正式链路缺口。
5. **CONTRACT.md §6 仍列旧 V1 场景/judge**；`_protocol.md` 仍 draft；`HASHES` pending。
6. **T 台阶 `_on_sample` 在 ground_feet≥2 时丢弃 step 证据**：V27 修复地面蹭级所需，但严于“≥2 足触地失败”的字面语义；C1 需确认是否影响合法第一级接触记录。
7. **砂砾坑真实几何未 recut**；当前仍是凸起盒代理，B1 出口 grace 需在真实坑几何上复核。
8. **Part2 官方能力场未逐档交叉核对**；official 重复最高档在确定性策略下统计意义有限。
9. **soft-reset 阈值与相邻 zone 重叠仍是启发式**。
10. **正式手动/操作手 3 次整场演练未在真实赛程完成**；当前只有脚本化诊断与 pause/resume、abort、pause_timeout 演练。

---

## 7. 结论

- **verdict：FAIL**
- **blocker：有**  
  `comp_part1_judge.py::TStairs._ground_penalty_active` + `TStairs._on_sample` + `TStairs._check_exit` 仍允许同一 `t_stairs` zone 内“s 上/下 + 地面移动 + e 上/下”合并为 100。V28 指出的“退出后 partial→full 升级”已被 `locks_partial_on_exit` 与 `j_lock` conformance 部分封住，但“未退出 zone 的 partial 合并”仍成立。
- **是否建议进入下一阶段（C1 人工标定 / C2 基线评测）：no**。  
  先修 T 台阶单次连续异臂约束，补“同 zone 内落地后第二臂不得升级”的 conformance 反例；同时复核 slalom 0.30/0.5 半径口径与 height_bar course route 跟踪余量；再重跑 13 组 conformance、各 self-test、四份产物与三份演练，刷新 HASHES 后复审。

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
13. **本轮新增必写**：T 台阶在同一 zone 内可“s 上/下 + 地面移动 + e 上/下”合并为 100；`locks_partial_on_exit` 只覆盖退出后重入，不覆盖同 zone 地面重置后的第二臂证据。
14. **本轮新增必写**：`TStairs._on_sample` 以“任意 ground_feet≥2”丢弃 step 证据，严于规则“≥2 足触地失败”，需 C1 校准是否造成合法第一级接触漏记。
