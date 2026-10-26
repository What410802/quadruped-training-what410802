# 第二十一轮 BYOK GLM-5.3 delta 复验（B1 等修复闭环验证）

```text
reviewer:   glm-5.3 / BYOK zhipu backend / 2026-10-23
scope:      第 20 轮 GLM FAIL 后的修复 delta（B1/B2/B3/B5/route）+ 全量重生成的四份产物、
            三份演练、HASHES；含第 22–30 轮 flash 后续修复的当前终态
独立性:     executor=deepseek-v4.1-flash vs reviewer=glm-5.3 → different-family
verdict:    PASS（无 scorer blocker）
```

> 说明：artifact 未附行号与执行 stdout，以下按 `文件::函数/代码段` 定位，不臆造行号；"通过"指源码路径与证据链静态一致，不是执行日志的形式证明。本轮未因第 30 轮 flash CONCERN 或作者结论放行，全部独立重推。

## 1. B1：离障落地 1/2 足门控

**结论：PASS（五个 ground_fail 障碍全覆盖；未发现新的"合法通过被误判失败"或落地侧假成功）**

`comp_part1_judge.py::_Obstacle.update` 的双侧 `supported` 门控（`_check_immediate` 成功分支与 `prev_in_zone` 退出成功分支均检查 `insufficient_obstacle_support`）仍在；`_ground_penalty_active` 逐障碍核对：

| 障碍 | 门控 | 判定 |
|---|---|---|
| bridge_blocks / bridge_bands | `TraversalBridge._ground_penalty_active`：`supported` 且 `bridge_hits>=3` + 双平台 tag 后关闭 | 远端平台集齐证据后落地合法；桥面中段（远平台未达）双足触地仍 `two_feet_ground` |
| gravel_pit | `GravelPit._ground_penalty_active`：`gravel_hits>=3` 后按入口侧距出口短边 `EXIT_GRACE_M=0.35` 关闭 | 远短边落地合法；坑中段仍失败 |
| slope | `Slope._ground_penalty_active`：累计 y 投影 ≥1.0 m 后关闭 | 完成后落地合法；<1 m 双足触地仍失败 |
| t_stairs | `TStairs._ground_penalty_active`：`top` + ≥1 完整臂后关闭 | partial 落地合法；未完成臂/顶台前触地仍失败 |

conformance 覆盖完整：`test_bridge_ground_and_success`（blocks/bands 各含 landing + mid-fall + anti-graze）、`test_gravel_short_edges_and_long_edge`（landing/mid-pit/长边）、`test_t_stairs_full_partial_and_history`（early_ground/partial_landing）、`test_slope_projection_and_graze_reset`（landing/mid_fall/soft-reset 重入）。第 30 轮 flash 指出的两个无效用例**已在当前文件修正**：`j_merge` 的地面样本改为 y=−4.9/−4.6（zone ymin=−4.95 内），`skipped_level_plus_complete_other` 的 `s:1` 改为 y=−4.9（zone 内）——我逐样本核对了坐标，两例现在真正命中声称场景。

**T 台阶同 zone 合并（第 29 轮 blocker）已封住且比第 30 轮更强**：`TStairs._on_sample` 的 `arms_before_ground` 锁存条件是 `len(ground_feet) >= 1`（不是第 30 轮担心的 ≥2），即 partial 后**任意单足触地**即快照臂证据；`_score_for` 只用 `_eligible_arms()`（快照优先）。单足地面过渡绕过锁存的理论通道已关闭。连续 s 上→top→e 下用例仍 100（全程无地面足，不锁存）。

非阻塞边界（保守向，记 C1）：
- 合法连续第二臂下降中，若在末级 tag 记录前有单足提前触地，快照会封顶 50（正常步态先站末级再落地，不触发）；
- partial 后单足地面蹭另一臂的不完整级会记入 `evidence["arms"]`，退出时 `_has_incomplete_arm` 把已得 50 变整体 `incomplete_step_history` 失败——需要刻意路径才触发，方向保守；
- `len(ground_feet)>=2` 样本丢弃 step 证据仍严于规则字面（爬最低级时需出现 ≤1 地面足的样本才记录，正常抬升后满足）。

**gravel 出口余量复核**（静态几何推演）：坑北缘 −11.0、zone ymax=−10.9、grace 覆盖 base y≥−11.25。前足越过 −11.0 触地时 base ≈ −11.25+lag，lag≤0.35 m 时 grace 覆盖，lag≈0.25–0.30 的常规四足在临界内；因失败需 ≥2 地面足且 base 持续前移，正常步态不误杀。余量偏紧 + 坑仍是凸起盒代理 → 记残余（recut 后必须复核）。

## 2. B2：绕杆拐角

**结论：PASS**

`Slalom._on_sample`：`corner_visits` 记录每次进入拐角圆（`SLALOM_CORNER_RADIUS_M=0.30`）时的杆数，`_check_immediate`/`_check_exit` 只要求期望时序（A=3/B=2）**出现在集合中**——提前扫过不再锁死。半径 0.30 与 post2 圆（0.35，圆心距 0.354）区分：站在 post2 圆心不触发拐角。`early_posts` 记录未来杆提前到访，`post_out_of_order` 拒绝。conformance：`early_then_legal`（提前扫拐角后合法通过=success）、`early_corner`（时序不对拒绝）、`early_future_post`（提前碰未来杆后补序仍拒）、缺拐角 `missing_corner_checkpoint`。乱序/缺拐角/早终点均拒绝。

minor（沿用）：judge 拐角 0.30 m vs 场景显示圆 0.5 m——合法路径只经显示圆边缘（0.30–0.50 m）会被误拒，C1 定口径；当前 route 走圆心不受影响。

## 3. B3 / B5

**B3：PASS。** `TStairs._check_exit` 的 `_has_incomplete_arm()`（任一臂 levels 非空且 ⊂{1,2,3} 即拒）在位；conformance 反例现在是真"n 缺级 + s 完整"（s:1/2/3 全部在 zone 内），断言不成功。单臂 partial（s=50、n/e=33）用例保持。

**B5：PASS。** `comp_part2_judge.py::Part2JudgeV2.update`：`cond` 为假时 `held = 0.0`，成功需连续 `held >= hold_s`；self-test `interrupted`（断续=fail）/`continuous`（连续=success）覆盖。minor：`_hold_ok` 仍是 dead code。

## 4. route

**结论：PASS（height_bar 跟踪鲁棒性为已知残余）**

- **slope**：`config/part1-route.json` 的 `to_slope=[5.2,-6.3]`→`cross_slope=[5.2,-4.2]`，沿 y 走 2.1 m；x=5.2 正是 slope_a（x≤5.20）/slope_b（x≥5.19）屋脊衔接线，足接触坡面 tag、`Slope._on_sample` 累计 |Δy|——判分轴匹配。
- **slalom**：`slalom_corner=[1.55,-12.75]` 即 judge 拐角圆心；`to_slalom` 路径过 start circle A（直线在 y=−10.1 处 x≈2.11，距 A 心 0.31<0.5），杆序 0→1→2→corner→3→end，waypoint x 交替 1.9/1.7 保证 S 形侧向交替。
- **bridge_blocks**：`to_bridge_blocks=[0.8,0.0]`（西侧 zone 外）→`cross_bridge_blocks=[6.5,0.0]`，xmin 进/xmax 出；platform_r 东缘 6.2 < zone xmax 6.3，B1 修复后东出落地（证据已集齐、判罚关闭）合法——原被封方向已解封。
- **bridge_bands**：`stage_bridge_bands_south=[5.7,-4.5]`（南侧 zone 外）→`cross_bridge_bands=[5.7,-0.5]`，ymin 进/ymax 出；platform_high 覆盖ymax=−0.8 直至 0.5，北出在平台上完成，无落地争议。段间 `stage_bridge_bands_east (6.6,-4.6)` 避免从 xmax 误入。
- **height_bar**：route 语义正确（ymin 进/ymax 出），但 course diag 三次 attempt 均 `wrong_exit_side`（`in_zone_samples=15770, touched=false`）——脚本 route 对 flat 策略跟踪误差不鲁棒，非 gate 语义问题；C2 若复用脚本 route 会缺该项（见结论条件）。

## 5. 回归与证据链

- **conformance 13 组**：`comp_judge_conformance.py::main` 13 个测试齐备；B1/B2/B3/B5 对应用例逐条静态推演通过，包括第 30 轮两处无效用例的修正版、同 zone 合并封顶 50、partial 锁定不可升级、soft-reset 干净重入、graze 反例（含西侧合法接近样本）。
- **四份产物 summary↔trials**：part1-diag-v2 8 条全 fail、attempts_used=8 一致（slope `two_feet_ground` 伴 tilt 178° 为真实摔倒）；part2-diag-v2 20 条、4/4/4/4/3/1 与 trials 计数一致；official 24 条、每类 4 次、attempt 1–4 编号正确（trench 30/20/10/30、plum×4 符合"不足 4 档补最高档"）；course 24 条（3×8）、attempts_used=3、`final_time_s=109.25999999997266` 与 trial 109.26 差 ≈2.7e-11 < comp_score 1e-6 容差。course 7 项 `route_complete` + height_bar `wrong_exit_side` 与 trials/drill 证据逐条一致，无假成功。
- **HASHES**：66 objects（26 基础 + 19 level + 12 eval 条目 + 6 extra + 3 evidence），全部条目 sha256 与 artifact 头部哈希逐一相符；四份 manifest 的 judge hash 均为当前代码（`comp_part1_judge.py=98ee9b96…`、`comp_part1_geom_tags.py=79ce2d9d…`、`comp_part1_course.py=9adf6d36…`、`comp_part2_judge.py=733aa34f…`）——第 25 轮"manifest hash 过期"问题未复发。`audited=false/verdict=pending` 为 G1 前正常状态。
- **三份演练**：pause/resume（3 attempts、recoveries=3、pauses 用模拟器时钟闭合、时长不含暂停）、abort（3×skip、duration=2.505）、pause_timeout（operator_t=121.02、事件先 append 再 abort、duration 0.5）与 `Part1Course` 代码路径吻合。
- **第 30 轮 CONCERN 清理项核实**：`comp_import_diagnostic.py` 的 `DEFAULT_SCENE`/`DEFAULT_JUDGE` 已改指 V2 场景/V2 judge；`_protocol.md` §8 已无"75/50 未裁决"陈旧表述。
- **历史回归**：N1–N4（逐物理步采样、per-attempt best、final_time 口径、bool 只认 1）、P1–P4、HighWall 墙段 x∈[1.30,2.30]、skipped 语义、soft-reset 状态清理（V26）、early_posts（V27）均无回归。

## 6. 新问题（均非 blocker）

1. **TStairs 三条保守向边界**（见 §1）：单足提前触地封顶 50 / partial+单足蹭不完整级整体 fail / ≥2 地面足样本丢 step 证据——建议进 C1 对抗标定集。
2. **gravel 出口 grace 余量紧**（lag≤0.35 m 才安全），且坑几何是代理——recut 后必须重验。
3. **理论通道（不构成现实风险）**：桥/坡在 `supported` 后以全程 ≤1 地面足蹭 tag 累积证据可绕 `insufficient_obstacle_support`——需持续单足地面步态跨越数米，物理不可行且规则本身 ≥2 足即败；记录即可。
4. **route 直线段几何上会掠过 t_stairs zone 西南角**（(1.8,−6.0)→(0.8,0.0) 在 y∈[−4.95,−2.7] 段入 zone），依赖 soft-reset/失败可重试语义消化；course diag 中机器人实际未走到该处（t_stairs `detail` 为空）。正式顺序通过无影响，属 soft-reset 启发式残余的具体实例。
5. 文档/代码清理：`_hold_ok` dead code；`_protocol.md` §4.1 诊断起点表（gravel (3.5,−12.0)、slope (3.6,−5.5)）与 runner `TASKS` 不符；`CONTRACT.md` §6 仍列 V1 judge hash。

## 结论

- **verdict：PASS**。B1/B2/B3/B5/route 五项修复在源码与 conformance 层面真正闭环，且第 22–30 轮的后续加固（supported 双侧门控、soft-reset 清理、early_posts、arms_before_ground ≥1 足锁存）无回归；四份产物、三份演练、HASHES(66) 相互一致；未发现新的假成功或结构性误判失败。
- **blocker：无。**
- **是否建议进入下一阶段：yes**。C1 人工标定可立即进（上述保守向边界应纳入标定用例）；C2 基线 **yes（有条件）**——正式赛程为手动，不受影响；若 C2 复用脚本 route 作诊断基线，需先修或在 notes 声明 `height_bar: wrong_exit_side`（route 对跟踪误差不鲁棒），否则该项缺失会污染基线解读。

## G1 必写残余

1. 砂砾坑真实"坑 + 碎木"几何未 recut（凸起盒代理）；B1 的 `EXIT_GRACE_M=0.35` 出口余量与足-基座滞后同量级，recut 后必须复核。
2. Part2 官方能力场未逐档交叉核对；official 重复最高档（trench 30×2、plum×4）确定性下统计意义有限；固定梯子（B8）可能低估边界难度。
3. soft-reset 阈值与相邻 zone 重叠仍是启发式（本轮 route 掠过 t_stairs 西南角即为其具体暴露面）。
4. B4/B6/B7 保守向判罚留 C1 裁决：限高杆未校验"从下方"、Part2 高墙必须墙接触、沟壑 lane ±0.7。
5. TStairs 三条保守向边界（单足触地封顶/partial 蹭级整体 fail/≥2 足样本丢证据）+ `arms_before_ground` 与合法连续下降的时序边界，需 C1 对抗用例确认。
6. slalom judge 拐角半径 0.30 m vs 场景显示圆 0.5 m，需定口径。
7. height_bar course diag 三次均 `wrong_exit_side`：route 语义正确但跟踪鲁棒性不足；C2 复用脚本 route 时需处理或声明。
8. 正式手动/操作手 3 次整场演练未在真实赛程完成（当前仅脚本化诊断 + pause/resume/abort/pause_timeout 演练）。
9. T 台阶 s/n/e ↔ 上/下映射、障碍级跳过是否消耗整场尝试、pause_timeout 120 s 自定常量仍需书面确认。
10. Part1 单障碍诊断 importer 的 per-obstacle 汇总口径仅诊断用；正式以 course importer 为准。
11. `_protocol.md` 仍 draft、§4.1 起点表陈旧；`CONTRACT.md` §6 仍列 V1 资产；`HASHES.json` 仍 `audited=false/verdict=pending`（G1 结论后更新）；`_hold_ok` dead code。
12. 跨 attempt 模拟器时间重置后事件时间线不能全局排序。
13. Part2 稳定性 ≥100 次、目标 0 失败未执行；`comp/eval/_calibration/` 仍为空。
14. 本轮为静态复核（无执行 stdout）：conformance/self-test/产物"通过"指代码路径与证据链一致，最终 acquittal（Codex）时应附实际执行日志复核一次。
