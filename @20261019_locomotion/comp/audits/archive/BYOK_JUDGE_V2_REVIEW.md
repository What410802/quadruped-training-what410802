<!-- BYOK G1 预审（provisional） -->
# BYOK Judge V2 Pre-Audit（DeepSeek v4.1-flash，同模型自审 → same-model-provisional）

> **verdict（原始输出）**：FAIL（26 条：11 blocker / 13 major / 2 minor）
> **后端**：`comp_review.py` / DeepSeek relay / `deepseek-v4.1-flash`（SSE，reasoning 用尽后 max_tokens=64000 重试成功）
> **独立性**：executor 与 reviewer 同为 `deepseek-v4.1-flash` → `same-model-provisional`
> 只能驱动改进，**不能** acquit G1；G1 最终 verdict 由不同家族 Codex 给出。
> **meta**：`BYOK_JUDGE_V2_REVIEW.json`（prompt/payload/hash/usage/trace）
> **trace**：`comp/traces/comp-review/2026-10-22_run01`
> **修复记录**：`BYOK_JUDGE_V2_FIXES.md`；**G1 复审材料**：`prompts/g1-reaudit-prompt.md`
> 以下为 reviewer 原始输出，executor 未改写。

verdict: **FAIL**（G1 重审前 BYOK 预审）

---

## 编号问题清单

### 1. [blocker] 地面失败判据把“进场前地面”算进障碍区，合法通过会被误杀
- 涉及：`scripts/agent_scripts/comp_part1_judge.py::_Obstacle.update`、`ZONES`；`run_part1_judged_rollout_v2.py::V2Runner._sample_judge`。
- 为什么错/如何利用：`ground_fail` 在 base 中心一进入硬编码 `ZONES` 就立即检查 `len(ground_feet) >= 2`，但多个 zone 包含障碍前的缓冲/地面：`slope` 的 `x=3.8` 早于实物坡面约 `x≈4.06`，`t_stairs` 的 `y=-4.95` 早于第一级 `y=-4.75`，`gravel_pit` 的 `y=-10.9` 在坑外，`bridge_blocks` 的 `x=1.25` 早于平台 `x=1.3`。机器人尚在地面、以正常四足接近时就会被判 `two_feet_ground`。现有 `summary` 中 `slope`/`bridge_blocks` 的 `two_feet_ground` 不能排除就是这种误杀。
- 修复方向：把“进入障碍”与“进入外部缓冲”分开；只在机器人已经踩上目标障碍/跨越区后启用地面失败；或按接触面、支撑点、是否在坑/桥/坡上方判断，而不是只看 base 是否落入矩形。
- 对应用例：新增 `test_approach_ground_not_fail_slope/bridge/t_stairs/gravel`，合法路径在障碍外保留地面足接触，期望 `running/pending` 而非 `fail`。

### 2. [blocker] 高墙可用“地面行走 + 从 y 侧进入/离开”骗成功
- 涉及：`comp_part1_judge.py::HighWall._on_sample`、`HighWall._check_exit`、`WALL_TOP_Z`。
- 为什么错/如何利用：`max_z` 记录的是 trunk/base 高度，正常站立约 `0.4–0.55 m`，而 `WALL_TOP_Z=0.30`，所以“爬墙证据”几乎天然成立。`_check_exit` 只要求 `entry/exit` 为 y 两侧且 `max_z >= 0.30` 或脚碰 `wall`；没有要求跨过墙平面 `y=-7`、没有要求 base/足端高过墙顶，也不排除从墙端绕行。可从 `y=-7.8` 进入 zone，在 `x=1.27` 或墙端外沿地面走到 `y=-6.2`，直接成功。
- 修复方向：记录墙平面穿越事件；要求穿越时支撑足/机身相对墙顶有真实抬升，或脚/身体与墙顶/墙面有合法接触；禁止在墙宽外绕行。不要用绝对站高当爬墙证据。
- 对应用例：在 `test_high_wall_sideways_and_climb` 增加 `test_high_wall_ground_bypass_y_entry`：从 y 侧进入、地面高度 `z=0.45`、无 `wall` 接触、从另一 y 侧离开，期望非 success。

### 3. [blocker] 真实桥面接触标签缺失，合法过桥必然失败
- 涉及：`run_part1_judged_rollout_v2.py::GEOM_TAGS`、`comp_part1_judge.py::TraversalBridge._on_sample`。
- 为什么错/如何利用：`GEOM_TAGS` 没有把 `bridge_blocks_0..4`、`bridge_bands_0..2` 映射到 `bridge`，只映射了平台。真实 runner 过桥时 `bridge_hits` 仍为 0，`TraversalBridge._check_exit` 会以 `missing_bridge_contact` 失败。conformance 使用合成 `tags=["bridge"]`，所以测试通过但真实场景无证据。
- 修复方向：补齐桥面 geom 到统一 surface tag；用场景真实 geom 名做集成测试；最好从 XML/命名规则生成映射，避免手工漏项。
- 对应用例：新增 `test_actual_scene_geom_tags_bridge_blocks/bands`，直接用 `part1_eval_scene_v2.xml` 的 geom 名走接触分类。

### 4. [blocker] T 台阶没有强制逐级顶面接触，分支/部分分实现错误
- 涉及：`comp_part1_judge.py::TStairs._on_sample/_score_for/_check_exit`、`run_part1_judged_rollout_v2.py::GEOM_TAGS`。
- 为什么错/如何利用：
  - `_on_sample` 只把出现过的 `step:*` 塞进集合，`_check_exit` 只要求 `steps` 非空 + `top=True` + `branches>=1`，并不要求每一级都出现；只碰 `step:y:1` 和 `step:top` 也能成功。
  - `len(branches)>=2` 即满分，不要求两条分支完整逐级上下、也不要求从另一侧回到地面。
  - 实际场景把 `t_stairs_y_low*` 和 `t_stairs_y_high*` 都映射成同一个 `step:y:*`，南侧上、北侧下被合并成同一 branch，合法 `南→顶→北` 反而只拿一支部分分。
  - `_score_for` 用 `"main"` 判上坡、其它判下坡；实际 runner 只产生 `y/x` branch，不会产生 `main/side`。`partial_up=112.5` 又被 `max_score=100` 静默 clamp，且没有 flag。
  - 单支部分分仍返回 `status=success`，会参与 `Part1JudgeV2` 的 `all_success` 和返回奖励判定。
- 修复方向：建立显式臂/级编号（如 `y_low:1..3`、`y_high:1..3`、`x:1..3`、`top`），记录逐级顶面接触历史、进入臂、离开臂和回到地面的顺序；区分“完成障碍”和“只拿部分分”；Q2 未裁决前不要把 112.5 静默封顶或写死。
- 对应用例：扩展 `test_t_stairs_history_and_partial`：缺 `y:2` 仍 success；只碰 `y:1+top` success；`y_low→top→y_high` 合法但当前被合并；`y:1+top+x:1` 不应满分；上/下部分分具体值校验。

### 5. [blocker] 绕杆可提前经过终点后仍成功；反向合法路线不被支持；判定半径与场景不一致
- 涉及：`comp_part1_judge.py::Slalom._on_sample/_check_immediate/_check_exit`、`SLALOM_RADIUS_M/SLALOM_POST_RADIUS_M`；`part1_eval_scene_v2.xml` 的圆形标注 geom。
- 为什么错/如何利用：
  - `end_area` 只要曾经接近终点圆就永久记录；`_check_immediate` 只检查 `end_area` 存在，不要求最后一次进入终点圆发生在四根杆和拐角之后。可以先绕到终点再回去补杆，最后在别处成功。
  - `corner` 只要求 `len(posts)>=2`，可在第二根杆后提前触发，不要求在两杆之间的正确顺序位置。
  - posts 顺序固定为 `0,1,2,3`，从终点圆 `B` 出发的反向合法路线不被接受。
  - judge 用 `SLALOM_RADIUS_M=0.5`、`SLALOM_POST_RADIUS_M=0.35`，但 XML 中圆形标注意味 geom size 很小/注释的“直径 1 m”与实际 `size="0.1 0.001"` 不一致；post 判定半径也远大于实际柱半径。会允许远离实体的“靠近”计数。
- 修复方向：改为严格序列状态机：合法起点圆 → post0 → post1 → post2 → 拐角必达区 → post3 → 另一终点圆，且终点必须是最后事件；支持 A→B 与 B→A 两种方向；半径以场景实际 geom 或规则尺寸为准。 
- 对应用例：`test_slalom_sequence` 增加反向 B→A、提前到终点、拐角在 post1 后、post 顺序错、半径边缘。

### 6. [blocker] 限高杆“从门洞外穿过再横移到门洞内”可骗过；掉杆检测不覆盖进场前和成功后
- 涉及：`comp_part1_judge.py::HeightBar._on_sample/_check_exit`、`BAR_DROP_THRESHOLD_M`、`_Obstacle.update`。
- 为什么错/如何利用：
  - `bad_opening` 和 `through_opening` 只是 y 带内任意采样：先 `x` 在门洞外穿过 `y=-9`，再在 `y≈-9` 横向移到 `x∈(5.2,6.2)`，`through_opening=True`，最终仍可成功。
  - 没有记录“穿越 `y=-9` 平面时整机连续位于门洞内”，也没有检查机身宽度/高度。
  - `bar_z0` 取进入 zone 后第一次看到的杆高；如果杆在进入前已经掉落，`bar_z0` 直接变成低值，后续不再判掉杆。
  - `_Obstacle.update` 在 success/fail 后直接 return，穿过后出 zone 前碰落杆不会撤销成功；只在 `HeightBar` in-zone 采样时检测掉杆。
- 修复方向：记录墙平面穿越事件和穿越时的连续 x 区间/机器人包络；使用绝对初始杆高或进场前预检；掉杆检测覆盖整次 attempt，成功锁存前允许掉杆失败。
- 对应用例：新增 `test_height_bar_cross_outside_then_strafe`、`test_height_bar_predropped_before_zone`、`test_height_bar_drop_after_success_before_exit`。

### 7. [blocker] `_Obstacle.update` 成功后永久锁定，失败后也不允许同一 attempt 内重新越障
- 涉及：`comp_part1_judge.py::_Obstacle.update`。
- 为什么错/如何利用：`if self.result.status in ("success","fail","skipped"): return` 使障碍状态不可恢复。规则语义中“失败后必须重新越障”意味着同一 attempt 内应可重新尝试；现在一旦早期误判 fail 或合法失败，后续合法跨越不会计入。反过来，一旦提前 success，后续掉杆/落地等也不会撤销。
- 修复方向：把“障碍通过”与“本次进入失败”拆开；允许重新进入并重置本次进入证据，保留 attempt 级事件账本；success 是否可撤销需按规则明确。
- 对应用例：`test_fail_then_legal_retry_same_attempt`、`test_success_no_late_invalidating_event`。

### 8. [blocker] 返回奖励没有要求“全部成功之后重新进入出发区”
- 涉及：`scripts/agent_scripts/comp_part1_course.py::Part1Course.end_attempt`、`Part1JudgeV2.returned_to_start`。
- 为什么错/如何利用：`end_attempt` 使用 `all_success and self._start_area_hits >= 2`，没有要求第二次进入发生在全部障碍成功之后。机器人可在中途两次经过出发区，然后完成剩余障碍却不再返回，仍拿 +100。`Part1JudgeV2` 内部有 `_all_done_once and in_start` 逻辑，但 `Part1Course` 没有使用它。
- 另外：T 台阶单支 traversal 现在也会是 `status=success`，因此“部分分障碍”也可能被算入 `all_success`。
- 修复方向：使用“最后一个障碍 success 之后”的出发区进入事件；返回奖励的 `all_obstacles_success` 是否接受部分分需明确；conformance 覆盖中途两次出发区但不返回。
- 对应用例：新增 `test_return_bonus_requires_post_success_reentry`、`test_return_bonus_partial_t_stairs`。

### 9. [blocker] Part 2 低难度项可在未上台/未上楼梯/未越墙时成功
- 涉及：`scripts/agent_scripts/comp_part2_judge.py::Part2JudgeV2._cond`。
- 为什么错/如何利用：
  - `platform` 条件为 `goal_x` 范围且 `z >= top_z + 0.30`。正常地面站立 base `z≈0.55`；`top_z=0.10` 需 `z>=0.40`，`top_z=0.20` 需 `z>=0.50`，都不需要真正上平台。
  - `stairs` 同阈值：10/15/20 cm 都可在地面 `z≈0.55` 成立。
  - `wall` 用 `max_z_near >= wall_h + 0.30`，10/20 cm 墙在地面即可满足；且没有 y 范围或越过墙平面证据。
  - 没有要求脚/身体接触目标顶面或支撑在目标高度上。
- 修复方向：使用“相对支撑面高度 + 足底接触目标面”的判据；至少要求足端接触平台/楼梯顶面，或 base 高度达到“目标顶面 + 标定站高”的阈值；为平台/楼梯增加目标 y 范围和从地面到达的路径证据；低难度也要禁止地面伪成功。
- 对应用例：新增 `test_part2_platform_ground_no_success_10_20`、`test_part2_stairs_ground_no_success_10_15_20`、`test_part2_wall_ground_no_success_10_20`。

### 10. [blocker] Part 2 高墙/沟壑/梅花桩缺少横向约束，可绕行成功
- 涉及：`Part2JudgeV2._cond` 的 `wall/gap/plum` 分支、`config/part2-levels.json` 的 `judge`。
- 为什么错/如何利用：`wall` 只看 `x >= goal_x_min`、`max_z_near`；`gap` 只看 `x >= goal_x_min`、`z >= min_z`；`plum` 只看 `x >= goal_x_min`、`z >= goal_z_min`。都没有 y 范围、跨越平面、从哪一侧进入、是否绕过障碍端部。机器人可从 y 方向绕过高墙/沟壑/梅花桩后回到目标 x 得分。
- 修复方向：使用障碍局部坐标和有效宽度；记录从近侧到远侧的跨越事件；要求足/身体经过障碍上方/内部或接触目标面；对沟壑要求实际跨过 gap x 区间，不能从 y 端绕行。
- 对应用例：新增 `test_part2_wall_go_around_y`、`test_part2_gap_go_around_y`、`test_part2_plum_go_around_y`。

### 11. [blocker] Part 1 正式整场协议没有接入 runner / importer
- 涉及：`run_part1_judged_rollout_v2.py::run_task/main`、`comp_import_diagnostic.py`、`comp_part1_course.py`。
- 为什么错/如何利用：`run_part1_judged_rollout_v2.py` 仍是每个障碍独立 reset、独立 `Part1JudgeV2`，没有 `Part1Course`、没有整场 3 次尝试、没有连续 8 障碍、没有返回奖励。`comp_import_diagnostic.py` 把 8 个独立任务导入成 `attempts_used=8`，与 manifest 的 `attempts_part1_total=3` 冲突；即使标 `diagnostic=true`，也不能用于验证正式协议。
- 修复方向：提供真正的整场 runner：一个 attempt 连续喂给一个 judge，包含开始/暂停/恢复/重开/跳过事件，最终由 `Part1Course` 产出 attempt 账本；诊断 importer 与正式 importer 分离。
- 对应用例：新增 `test_end_to_end_three_attempts_whole_course`，从 trials/events 复算 best score、fastest time、return bonus。

### 12. [major] 恢复/暂停语义可被用来传送，且暂停时间账本不一致
- 涉及：`comp_part1_course.py::pause/resume`、`AttemptManager.note_recovery/end/summary`。
- 为什么错/如何利用：
  - `resume(t, base_xyz)` 接受任意姿态，不校验“倒下前原位置原朝向”，也不拒绝大幅传送；可借恢复把机器人放到有利位置。
  - 暂停期间若仍调用 `course.update`，虽然 `active_time` 不加，但仍会调用 `judge.update` 并累计 start hits/接触状态。
  - `AttemptManager.note_recovery` 只追加 `[t,t]`，没有真正扩展区间；`AttemptManager.end` 的 `duration_s` 仍是 `t-started_at`，包含暂停时间。`Part1Course.summary` 虽覆盖了 `final_time_s`，但 `attempts` 数组和 manager 侧账本仍不一致。
- 修复方向：暂停时保存完整 pose/yaw；恢复时强制相同位置/朝向或按规则重放；暂停期间冻结 judge；统一由 course 计算有效时长，manager 只记录事件，不另算一套含暂停时长。
- 对应用例：扩展 `test_attempt_manager_rules`、`run_self_test`：错误恢复位姿应拒绝；暂停期间喂 update 不应改变 judge；duration 等于 active_time。

### 13. [major] `_Obstacle.update` 的 soft-reset 由采样数决定，非法进出可被擦除
- 涉及：`comp_part1_judge.py::_Obstacle.update` 和各 `_check_exit` 中的 `in_zone_samples < 5`。
- 为什么错/如何利用：非法进入/非法出 zone 时，如果采样少于 5 次，各 obstacle 返回 `(False, "")`，generic 逻辑把状态重置为 `pending` 并清空 evidence。攻击者可快速进/出再重新进入，避免 `illegal_entry/illegal_exit` 失败；而从 zone 内开始的任务则 `entry_side_prev=None`，之后可能被判 `illegal_entry_side`。这与真实规则无关，只是采样频率 artifact。
- 修复方向：入场合法性必须由几何线段与进入边确定；不要因为本次采样少于 N 就清空失败；如果允许“试探后重来”，应显式按 attempt 事件而不是按采样数。
- 对应用例：新增 `test_fast_illegal_entry_exit_does_not_reset`、`test_start_inside_zone_entry_side`。

### 14. [major] 斜坡距离用欧氏距离、无长边投影，可用横向往返凑 1 m
- 涉及：`comp_part1_judge.py::Slope._on_sample`。
- 为什么错/如何利用：只要任意足带 `slope` tag，就累加 base 的 XY 欧氏距离；没有投影到坡面长边方向，也没有限制沿长边。机器人在坡面上横向 x 往返或斜向抖动都能凑够 1 m。Q4 要求“两侧合计沿 3 m 长边方向累计走 ≥1 m”。
- 修复方向：使用 slope 局部坐标，累计沿长边方向的位移；对退回/往返是否重复累计需按“累计行走距离”定义实现；区分两侧 slope geom；避免地面缓冲误判。
- 对应用例：`test_slope_distance_and_direction` 增加 `test_slope_lateral_does_not_count`、`test_slope_back_and_forth`。

### 15. [major] 接触标签只看 geom 名，不看接触法向/接触点/受力，侧面擦碰也当顶面接触
- 涉及：`run_part1_judged_rollout_v2.py::V2Runner._sample_judge`、`GEOM_TAGS`；`comp_part1_judge.py` 各 `_on_sample`。
- 为什么错/如何利用：只要脚 geom 与目标 geom 有任意接触，就添加 tag。脚擦到台阶侧面也会记作 `step:*`，擦到桥侧面也算 `bridge`，脚碰墙侧面也算 `wall`。T 台阶要求“顶面至少一次足底接触”，斜坡/桥也应按允许表面接触。
- 修复方向：接触判定要使用 contact normal 世界方向、接触点相对 geom 局部顶面、摩擦/法向力阈值；对 T 台阶只接受顶面法向朝上的接触；对墙接触区分可攀爬面/顶面。
- 对应用例：新增 `test_step_side_contact_not_top`、`test_bridge_side_contact_not_deck`、`test_wall_side_contact_not_climb`。

### 16. [major] 砂砾坑场景仍不是“坑 + 碎木”，且短边/L 形几何与 judge 不一致
- 涉及：`assets/terrain/part1/part1_eval_scene_v2.xml` 的 `gravel_pit_a/b`；`comp_part1_judge.py::GravelPit`。
- 为什么错/如何利用：场景中是两个静态 box，非真实坑体/碎木；其 L 形边界与 judge 假设的“ymin/ymax 两个短边”不一致。`GravelPit` 只要求 entry/exit 边为 y、`gravel_hits>=3`，没有校验实际短边线段、有没有从长边角穿入、是否跨越完整坑体。zone 还包含 `y=-10.9` 的坑外缓冲，会造成问题 1 的误杀/误判。
- 修复方向：按规则重建真实坑+碎木几何；为实际短边建立线段入口/出口；judge 记录进入段、坑内接触、离开段，不能只用矩形边名。
- 对应用例：新增 `test_gravel_actual_short_edges_from_xml`、`test_gravel_corner_entry_rejected`、`test_gravel_approach_ground_not_fail`。

### 17. [major] 场景接触映射仍有关键不一致：T 支路合并、共享平台 tag、绕杆半径不一致
- 涉及：`run_part1_judged_rollout_v2.py::GEOM_TAGS`；`part1_eval_scene_v2.xml`。
- 为什么错/如何利用：
  - `t_stairs_y_low*` 与 `t_stairs_y_high*` 被映射为同一 `step:y:*`，无法区分上/下臂。
  - `bridge_platform_r` 同时映射 `platform_right` 和 `platform_high`，bridge_blocks 与 bridge_bands 的 zone 有重叠时可能互相污染。
  - 绕杆圆形视觉 geom 与 judge 半径不一致，实际场景无法验证判定半径。
- 修复方向：surface tag 必须与障碍拓扑一致；平台 tag 分障碍实例命名；绕杆场景几何与规则尺寸统一，并由 judge 从场景/配置读取而不是硬编码两套值。
- 对应用例：`test_actual_geom_tags_t_stairs_branches`、`test_overlap_bridge_platform_isolation`、`test_slalom_radius_from_scene`。

### 18. [major] Part 2 “每项 4 次”协议没有在 runner/importer 中实现
- 涉及：`run_part2_judged_eval.py`、`comp_import_part2_diag.py`。
- 为什么错/如何利用：runner 对每个选中 level 跑 `--attempts` 次，而不是每个 category 总共最多 4 次挑战；importer 的 `attempts_used = len(cat_trials)` 把所有难度的一次尝试累加，例如 high_platform 的 4 个 level 变成 `attempts_used=4`，看似 4 次但实际是 4 个不同难度；超过 4 次也不会拒绝。
- 修复方向：实现 category 级 challenge scheduler：每次尝试选择 level，最多 4 次，记录 level 序列；import 时从 trials 校验每 category `<=4`，并按全部 valid attempts 重算最高成功难度。
- 对应用例：新增 `test_part2_category_4_attempt_cap`、`test_part2_best_level_from_trials`、`test_part2_5th_attempt_rejected`。

### 19. [major] Part 2 证据链不记录具体 level XML 哈希，trial score 也硬编码为 0
- 涉及：`comp/eval/flat-ft-2500-part2-diag-v2/manifest.json`、`comp_import_part2_diag.py`。
- 为什么错/如何利用：manifest 的 `scenes.part2.file` 指向 `config/part2-levels.json`，不是每个生成的 `assets/terrain/part2/levels/*.xml`，且 `part2_plum_eval_scene.xml` 只在 `config` 里引用，没有 hash。导入器对每个 trial 写 `judge.score: 0`，成功与否只靠 `success=true`，summary 分数另算；无法从 trial 的 judge score 直接审计。
- 修复方向：manifest 记录所有 level scene hash、plum scene hash、生成器 hash；trial 记录 level id、judge/score evidence；summary 分数必须可由 trials + CONTRACT 重算。
- 对应用例：`test_part2_manifest_contains_all_scene_hashes`、`test_part2_summary_recomputable_from_trials`、篡改 trial success 后必须被 comp_score 拒绝。

### 20. [major] Part 1 产物标签/算子/attempts 与真实运行不一致
- 涉及：`comp_import_diagnostic.py`、`comp/eval/flat-ft-2500-part1-diag-v2/manifest.json`。
- 为什么错/如何利用：manifest 的 `judge.version` 写 `part1_event_judge@cd31f...`，但文件是 `comp_part1_judge.py`；`operator`/`notes` 写 `run_part1_judged_rollout.py`，实际诊断是 V2 逻辑；summary `attempts_used=8` 与 protocol `attempts_part1_total=3` 冲突；没有记录原始 result JSON 的 hash。证据链无法证明产物确实由声明的 judge/runner 生成。
- 修复方向：importer 从 result payload/CLI 读取真实 runner 名和 judge 文件列表；记录 raw result hash；diagnostic 的 attempts 语义改为“per-obstacle trials”或单独字段，不与正式 attempts 混用。
- 对应用例：`test_part1_manifest_source_consistency`、`test_diagnostic_attempts_not_counted_as_formal`。

### 21. [major] importer 会丢重复尝试或把 score=0 的 success 提升成满分
- 涉及：`comp_import_diagnostic.py` 的 `per_task.setdefault` 与 `score = int(t["judge"].get("score") or per_obstacle_score)`。
- 为什么错/如何利用：同一障碍多次尝试时只用第一条，不能取最好/合法重试；如果某条 trial `status=success` 但 `judge.score=0`（当前 T/部分分或 bug），`or` 会回退到 100 分，可能伪造满分。Part2 importer 同样没有校验 trial 状态与分数/level 的对应。
- 修复方向：所有正式/诊断 importer 都必须保留全部 trial；成功分数由 judge report + contract 重算；`0` 不能被 `or` 当缺失值；缺失和零分分开建模。
- 对应用例：`test_import_duplicate_obstacle_attempts`、`test_import_success_zero_score_not_default_100`、`test_import_part2_success_below_threshold_zero_score`。

### 22. [major] conformance 测试覆盖是合成 data，未覆盖真实 runner/GEOM_TAGS/地面缓冲
- 涉及：`comp_judge_conformance.py`、`comp_part2_judge.py::run_self_test`。
- 为什么错/如何利用：现有测试多数直接喂 `tags=["bridge"]`、`ground=[]`、`bar_z` 常数，绕开真实场景接触分类、地面误杀、桥面 tag 缺失、T 支路别名、Part2 地面高度阈值。测试能通过，但仍留下 V1 同类漏洞。
- 修复方向：增加两类测试：
  - 纯 judge 反例：高墙地面绕行、限高杆先外穿再横移、绕杆提前终点、T 缺级、斜坡横移、回奖金前置、暂停传送。
  - 场景集成测试：直接加载 `part1_eval_scene_v2.xml` 的 geom 名和 `GEOM_TAGS`，构造脚接触；Part2 用 `config/part2-levels.json` 的 judge 条目跑反例。
- 对应用例：新增 `test_integration_part1_scene_tags`、`test_integration_part2_ground_bypass`、`test_integration_geofence_bypass`。

### 23. [major] Part 2 生成器只生成曲线节点，无法评测阈值间难度/比例分
- 涉及：`make_part2_levels.py::SPECS`、`config/part2-levels.json`。
- 为什么错/如何利用：例如高台只生成 10/20/30/40 cm，无法测量 35 cm 拿 150 分的中间能力；楼梯、墙面也同理。规则允许自定义地图并按难度比例计分，当前评测最高成功难度只会落在节点上，低估或无法验证中间阈值。
- 修复方向：为关键中间值生成 level，或在 runner 中支持连续高度/角度参数并记录实际难度；summary 记录最高成功实际值而非只记录离散 level。
- 对应用例：新增 `test_part2_intermediate_level_scoring`，例如 high_platform 35 cm 期望 150、wall 25 cm 期望 75。

### 24. [minor] Part2 bool 曲线对任意非零值给满分
- 涉及：`comp_part2_judge.py::curve_points_floor` 的 `unit=="bool"`。
- 为什么错/如何利用：`value=-1` 或 `0.5` 也会返回 200，而 bool 应只接受合法 `1/True`。当前 level 只有 1，故风险低。
- 修复方向：bool 明确 `value >= 1` 才满分，非法值 0 或错误。
- 对应用例：`test_part2_bool_curve_invalid_values`。

### 25. [minor] 诊断 runner 的总分可能把非目标任务的状态也累计
- 涉及：`run_part1_judged_rollout_v2.py::main`。
- 为什么错/如何利用：`total = sum(r["judge"]["score"] for r in results)` 会加总每个 per-task judge 报告里所有 obstacle 的分数；如果某次诊断路线意外穿过另一个障碍 zone 并触发 success，会重复累计。正式场景不应使用该总分。
- 修复方向：诊断汇总只取 `states[task]`；正式 runner 使用整场 judge。
- 对应用例：`test_diagnostic_total_only_target_obstacle`。

### 26. [minor] zone 重叠可能污染桥状态
- 涉及：`comp_part1_judge.py::ZONES` 的 `bridge_blocks` 与 `bridge_bands`；`bridge_platform_r` 共享 tag。
- 为什么错/如何利用：两 zone 在 `x≈5.0–6.3, y≈-1.0–-0.8` 重叠；共享平台的 `platform_right/platform_high` 可能同时被两个 obstacle 观测。若路线经过共享平台，bridge_blocks/bridge_bands 可能互相改写 evidence。
- 修复方向：将 zone 改为障碍局部、不重叠；平台 tag 分实例；测试共享平台的先后顺序。
- 对应用例：`test_overlapping_bridge_zones_isolation`。

---

## G1 重审前必须修的最小集合

1. **Part 1 成功语义先修到“无假成功”**：高墙、限高杆、绕杆、T 台阶四类优先。
   - 高墙必须检测墙平面穿越和真实抬升；
   - 限高杆必须检测连续门洞穿越、绝对杆高/全程掉杆；
   - 绕杆必须终点最后、支持双向、半径与场景一致；
   - T 台阶必须逐级顶面历史、显式分支、部分分与 success/return bonus 解耦。

2. **修正地面失败边界**：`ZONES` 不能把进场前地面当障碍内部；否则合法通过会被 `two_feet_ground` 误杀。必须先做 `test_approach_ground_not_fail_*`。

3. **补齐真实场景接触映射**：至少补 `bridge_blocks_0..4`、`bridge_bands_0..2`，修 T 台阶 y_low/y_high 分支，确认所有 `GEOM_TAGS` 与 judge 期望一致；用真实 XML geom 做集成测试。

4. **Part 2 低难度地面伪成功必须归零**：平台/楼梯/墙的 10/15/20 cm 级不能用地面站高满足；沟壑/墙/梅花桩不能绕过 y 端。先修 `_cond` 的支撑/接触/横向约束。

5. **接入正式整场 Part 1 attempt 协议**：一个 attempt 连续跑 8 障碍；`AttemptManager`/`Part1Course` 真正由 runner 使用；3 次尝试、恢复不消耗、重开/跳过消耗、best score/min time 从 trials 重算。当前 per-obstacle diagnostic runner 不能作为正式证据。

6. **修返回奖励前置条件**：必须“全部障碍完成之后重新进入出发区”；中途经过出发区不算；部分分障碍是否算“全过”需要明确。

7. **Part 2 每项 4 次协议和证据链**：runner/importer 强制 category 级 4 次上限；manifest 记录所有 level XML/plum scene hash；trial 记录真实 judge score/level 证据；summary 可由 trials + CONTRACT 复算。

8. **importers 不再信任/丢失信息**：保存全部 trial，不用 `or` 把 0 分变满分，不从首个 trial 覆盖重复尝试；Part1 manifest 的 judge/operator/attempts 字段与真实 runner 一致。

9. **conformance 补上本轮全部反例**：真实 XML/GEOM_TAGS 集成测试、地面缓冲误杀、高墙地面绕行、限高杆先外穿再横移、绕杆提前终点/反向、T 缺级/分支、斜坡横移、暂停传送、Part2 低难度地面伪成功和绕行。

---

## Codex 复核应重点看的问题

1. **是否仍存在“入口合法 + 地面高度/位姿”即可成功的路径**：高墙、Part2 平台/楼梯/墙尤其危险。
2. **场景 GEOM_TAGS 与 judge surface tag 是否一一对应**：桥面缺失是确定性 blocker；T 台阶 y_low/y_high 合并是确定性 blocker。
3. **T 台阶部分分与 return bonus 的关系**：单支 traversal 是 `success` 是否应允许拿“全障碍完成 +100”？Q2 的 112.5 目前被静默封顶。
4. **ground_fail 是否只在障碍内部生效**：当前 zone 缓冲会导致合法接近误杀，必须用真实接触/支撑面验证。
5. **限高杆穿越事件是否是连续、整机、门洞内穿越**：当前是一组 y 带内任意采样，可先门外穿越再横移。
6. **绕杆终点是否强制最后事件、是否支持反向**：当前 end_area 可提前记录。
7. **Part2 `_cond` 是否真正证明“在目标顶面上”而不是“x 到了且 base 足够高”**：低难度阈值明显不足。
8. **attempt ledger 是否成为唯一真相源**：`AttemptManager`、`Part1Course`、importer、summary 目前存在多套 duration/attempt 语义。
9. **manifest/summary/trials 是否能被 comp_score 强校验**：给定材料未包含 `comp_score.py`，本轮无法确认 V1 的 summary 信任问题是否修复；必须复核 success 与 evidence trial、Part2 最高难度、场景 hash、judge hash 的一致性。
10. **diagnostic 是否仍被误当正式分数**：当前 Part1 diagnostic summary 的 `attempts_used=8` 与整场 3 次协议冲突，必须保证 comp_score 不会把它计入正式榜。
