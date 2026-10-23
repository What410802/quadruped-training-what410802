# BYOK Judge V2 Pre-Audit → 修复映射（2026-10-22）

> 预审 verdict = FAIL（26 条）。本文件逐条记录处置；G1 最终结论以 Codex 复审为准。
> 预审报告：`BYOK_JUDGE_V2_REVIEW.md`（same-model-provisional）

| # | 严重度 | 问题 | 处置 | 证据/测试 |
|---|---|---|---|---|
| 1 | blocker | ground_fail 把进场前地面算入障碍区 | 已修：仅当"确实接触障碍面且曾有全足支撑（无脚在地面）"后才启用 1/2 足判罚 | `_Obstacle.supported`；`test_approach_ground_is_not_failure` |
| 2 | blocker | 高墙可用地面高度/从 y 侧进出骗成功 | 已修：必须发生墙平面 y=-7 的穿越事件且穿越时 base≥0.55 或有墙面接触；x 越界走外沿被 wrong_exit 拒绝 | `HighWall._on_sample/_check_exit`；`test_high_wall_*` |
| 3 | blocker | 真实桥面 geom 未映射 bridge tag（合法过桥必失败） | 已修：`bridge_blocks_0..4`、`bridge_bands_0..2` 全部映射；新增真实 XML 映射完整性测试 | `comp_part1_geom_tags.py`；`test_scene_geom_tags_complete` |
| 4 | blocker | T 台阶未强制逐级、分支/部分分错误 | 已修：显式三臂（s/n/e）+ 每级 1..3；满分需两臂完整；单臂=部分分（上 75/下 50）；单臂 success 不触发返回奖励 | `TStairs`；`test_t_stairs_full_partial_and_history`、course 自检 |
| 5 | blocker | 绕杆提前终点、反向不支持、半径不一致 | 已修：按起点圆决定杆序（双向）；拐角位于第 2/3 杆之后；终点区必须在四杆+拐角之后另一样本才生效；半径 0.5 m | `Slalom`；`test_slalom_forward_reverse_and_spoof` |
| 6 | blocker | 限高杆可门外穿越后横移；掉杆检测不完整 | 已修：必须发生穿过 y=-9 且在门洞 x∈[5.2,6.2] 内的连续穿越事件；杆基高从首次观测起全程跟踪，>5 cm 掉杆即失败 | `HeightBar`；`test_height_bar_touch_drop_and_gate` |
| 7 | blocker | 成功后永久锁定、失败后不能重试 | 已修：成功锁定（不可撤销）；失败记录为事件并允许离开后重试；返回奖励只认"全满分后"的出发区进入 | `_Obstacle._fail/update`；`test_failure_can_be_retried_and_success_is_final` |
| 8 | blocker | 返回奖励未要求"全部成功之后重新进入出发区" | 已修：judge 记录 all_full_done 之后才把出发区进入记为 return；course/comp_score 同口径 | `Part1JudgeV2.update`；course 自检 |
| 9 | blocker | Part2 低难度可用"站地面"伪成功 | 已修：平台/楼梯/斜坡/梅花桩成功需 z≥阈值+横向约束且**无脚接触地面**持续 hold | `comp_part2_judge._cond`；自检 |
| 10 | blocker | Part2 高墙/沟壑/梅花桩可绕行 | 已修：全部加 lane 横向约束；高墙要求穿越 wall_x 事件+抬升；沟壑要求跨越后 z 恢复 | 同上 |
| 11 | blocker | 正式整场协议未接 runner/importer | 已修：`run_part1_course.py`（3 次、暂停冻结、恢复位姿校验、返回奖励、best score/fastest time）+ `comp_import_course_diag.py`；已产出诊断行 | `comp/eval/flat-ft-2500-part1-course-diag/` |
| 12 | major | 恢复/暂停可传送、账本时长不一致 | 已修：暂停期间冻结物理；恢复必须原位置原朝向（>0.3 m/0.52 rad 判违规、该次 0 分）；账本 duration 用 active time | `Part1Course.pause/resume`；course 自检 |
| 13 | major | soft-reset 由采样数决定，可能擦除非法进出 | 部分修：仅在"无接触证据/短停留"时 soft-reset；真实尝试（≥5 样本或已接触）仍记失败。残余：边界阈值仍可讨论 | `_check_exit` soft 分支；文档 §6.2 |
| 14 | major | 斜坡用欧氏距离、可横向凑 | 已修：只累计坡面接触期间沿长轴（y）的投影距离，横向摆动不计 | `Slope._on_sample`；`test_slope_projection_and_graze_reset` |
| 15 | major | 接触只看 geom 名，不看法向 | 已修：runner 对桥/坡/台阶等顶面 tag 要求 |normal_z|≥0.5；墙面接触不受限 | `run_part1_judged_rollout_v2._sample_judge`、`run_part1_course` |
| 16 | major | 砂砾坑场景不是"坑+碎木" | **未修（记录为已知局限）**：本地场景用凸起盒代理；judge 语义按 surface tag/短边规则验证。正式评测前需 recut 真实坑几何并重跑 conformance | `comp/CONTRACT.md` §5.1/`eval/_protocol.md` §8 |
| 17 | major | 场景映射不一致（T 支路合并、共享平台、绕杆半径） | 已修：T 三臂 tag、共享平台双 tag、场景显示圆半径 0.5 m | `GEOM_TAGS`、scene v2 |
| 18 | major | Part2 每项 4 次未在 runner/importer 实现 | 部分修：runner 支持 `--attempts N`（正式=4），诊断行 attempts_used 记录真实次数；正式协议仍需 C3 冻结时固定 | `run_part2_judged_eval.py --attempts` |
| 19 | major | Part2 证据链无 level XML hash、trial score 硬编码 0 | 已修：manifest 记录每个 level scene sha256；trial score 按曲线计 | `comp_import_part2_diag.py` |
| 20 | major | Part1 产物 operator/attempts 与真实运行不一致 | 部分修：diagnostic manifest 如实标 operator/attempts；正式整场用 course importer（attempts_used=真实尝试数） | `comp_import_diagnostic.py`、`comp_import_course_diag.py` |
| 21 | major | importer 丢重复尝试/0 分被提升 | 部分修：Part1 保留 partial score；course importer 用 best attempt；Part2 trial 分数按曲线。残余：Part1 单障碍诊断 importer 仍按每障碍首条 trial 汇总（diagnostic 场景） | 三个 importer |
| 22 | major | conformance 全是合成数据 | 已补：真实 scene v2 geom→tag 完整性、approach-ground、retry、双向绕杆、T 缺级、斜坡横移、Part2 地面伪成功等 | `comp_judge_conformance.py`（13 组） |
| 23 | major | 参数化 level 只生成曲线节点 | 接受：曲线节点即官方档位；阈值间难度由曲线插值，不需要新场景 | `make_part2_levels.py` |
| 24 | minor | bool 曲线任意非零满分 | 接受：plum 只有 1/0 | 契约 |
| 25 | minor | 诊断 runner 总分可能含非目标任务 | 已修：V2 每 runner 独立 judge，汇总只用目标状态；course importer 用 best attempt | `run_part1_judged_rollout_v2.py`、`comp_import_course_diag.py` |
| 26 | minor | 相邻 zone 重叠污染桥状态 | 部分修：共享平台多 tag、重叠只会产生可 soft-reset 的噪声；正式整场按顺序经过时不影响已成功状态 | `GEOM_TAGS`、course 诊断 |

## 残余风险（G1 复审应重点看）

1. 砂砾坑真实几何未 recut（#16）；
2. soft-reset 阈值（#13）与相邻 zone 重叠（#26）仍是启发式；
3. Part1 单障碍诊断 importer 的 per-obstacle 汇总口径（#21，仅诊断用）；
4. Part2 官方能力场交叉核对未做（自定义同种类 level 已验证 evaluator 逻辑）。


## 二次预审后修复（2026-10-22 晚，BYOK 二次预审 verdict=FAIL）

| 二次预审项 | 结论/处置 |
|---|---|
| #2 高墙仍可用侧擦墙/地面过平面 | 已修：穿越必须 base z≥0.60（抬升），删掉 `wall tag` 作为抬升证据；conformance 增加"墙高度地面侧擦"用例 |
| #4 T 台阶 partial 锁死/不要求两臂 | 已修：partial 记录 `detail.partial` 并允许同 attempt 内二次进入升级为满分；两臂完整才 100；conformance 增加 partial→full 升级用例 |
| #5 绕杆半径/拐角时机 | 已修：场景显示圆半径改 0.5 m；拐角要求方向相关（A 向第 3 杆后、B 向第 2 杆后）；`_check_immediate` 也校验 corner_after；conformance 增加 early-corner 用例 |
| #6 限高杆预掉落/失败重试洗掉/成功后掉落 | 已修：横杆基高与掉落标记改为障碍对象持久状态（`bar_base_seen/bar_dropped_seen`），预掉落即失败且不可通过重试洗掉；失败前掉杆即失败；conformance 增加 pre-entry drop 用例 |
| #9 Part2 低难度无接触证据 | 已修：平台/楼梯/斜坡/梅花桩成功需对应 foot tag 接触 + 无地面足；self-test 增加"离 lane 1 m 伪成功" |
| #10 Part2 gap 绕行/墙未绑 lane | 已修：gap 需在 lane 内先后跨近/远边（或一次跃过）；wall 需 lane 内跨 wall_x 且 wall 接触 + 抬升；self-test 增加无跨越/无墙接触用例 |
| #11 正式整场不是同一 ledger / importer best 匹配 | 已修：`run_part1_course.py` 单 `Part1Course` 会话跑 2 次尝试（diagnostic 验证）；importer 用实际 attempt 编号匹配 best 并生成 return evidence trial；manifest part2 scene 指向 levels 配置 |
| 新问题：暂停无 resume 事件死锁 | 已修：暂停期间物理冻结但操作手时钟推进（>120 s 无 resume 则 abort）；runner 的 pause/resume 用冻结位姿 |
| 新问题：comp_score 信任 return_to_start | 已修：有返回奖励时必须有 `return_to_start_after_full` evidence trial，否则报错；course importer 生成该 trial |
| 新问题：Part2 每项 4 次未实现 | 已修：`run_part2_judged_eval.py --official` 每 category 最多 4 次（高→低档位），诊断模式仍每档 1 次 |
| 新问题：bool 曲线任意非零满分 | 已修：`comp_score`、`comp_part2_judge` 的 bool 只认 value==1 |
| 新问题：part1 V2 diag 总分含非目标状态 | 已修：只累计本 task 状态 |
| 新问题：diag operator 名不符 | 已修：importer `--operator` 默认 `scripted:run_part1_judged_rollout_v2.py` |

### 剩余未清零（已记录为已知局限，需在 G1 报告写明）

1. 砂砾坑场景仍是凸起盒代理，不是"坑 + 碎木"真实几何；
2. Part2 官方能力场（`terrain.zip` 地图）未做逐档交叉核对，本地为同种类参数化 level；
3. soft-reset 阈值与相邻 zone 重叠仍为启发式（真实整场顺序通过时影响有限）；
4. Part1 单障碍诊断 importer 的 per-obstacle 汇总口径（仅诊断用，正式用 course importer）；
5. 正式 3 次尝试的 runner/操作手演练尚未在真实赛程上做过（当前为脚本化 2 次尝试诊断）。


## Pro 预审后修复（2026-10-22 深夜，DeepSeek pro verdict=FAIL，N1–N4）

| 项 | 问题 | 修复 |
|---|---|---|
| N1 | `run_part1_course.py` 只在每个 policy step（20 ms）后采样，漏判"任意瞬间 ≥2 足触地" | 已重构：`CoursePolicyRunner` 拆成 `set_action`/`physics_step`，course runner **每个物理步（5 ms）**都 `course.update` + 事件处理；暂停时冻结物理但推进操作手时钟 |
| N2 | `comp_import_course_diag.py` 用全局 session summary 选 best，导致第二次及以后尝试的 score/duration/return bonus 错 | 已修：runner 每次尝试输出 `attempt_result`（AttemptResult），importer 用 per-attempt score/duration 选 best、取 duration、判定 return bonus |
| N3 | 同分最快时间口径未落到"最高分尝试内取最快" | 已修：`Part1Course.summary` 与 `AttemptManager.summary` 的 final_time = 最高分尝试中的最快 duration；新增 `final_time_scope` 字段 |
| N4 | bool 曲线 `value not in (0.0,)` 仍给满分（修复声明与代码不一致） | 已修：`comp_score.curve_points`、`comp_part2_judge.curve_points_floor` 均要求 `value == 1.0` |
| 附加 | 被中止的 Codex 会话提示限高杆静置可能掉落 | 已加 `check_part1_scene_v2.py`（空场景 5 s 仿真，横杆下落 <1 cm 才通过），并纳入复验流程 |

> 说明：前一轮"已修 bool"声明错误，本轮已纠正；pro 复审建议 N1–N4 修完前不要以 PASS 预期送 Codex。
> 砂砾坑真实几何、Part2 官方场交叉核对、soft-reset 启发式、正式手动 3 次演练仍是已知残余（G1 报告需写明）。


## 第四轮 Pro 复验后修复（N1–N4 已 PASS，P1–P4 新问题）

| 项 | 问题 | 修复 |
|---|---|---|
| P1 | 稳定停表用 policy dt（20 ms）而非物理 dt（5 ms），速度/累计时间错误 | 新增 `StableStopTracker`（stdlib，`comp_part1_course.py`），使用 `model.opt.timestep=0.005` 计算速度与 hold；course 自检断言 0.5 s 真实 hold 才停表、错误 dt 不提前停 |
| P2 | 暂停期间仍以冻结位姿反复调用 judge（可能改变状态/时间） | 暂停循环只推进操作手事件时钟与 120 s 超时，不再调用 `course.update`；恢复后继续真实物理步 |
| P3 | comp_score 不机器复核外部 hash、Part1 final_time、Part2 合法档位 | 已加 `validate_external_evidence`：重算 scenes（含 levels）、judge.file_hashes、contract sha256；校验 Part2 best value 是契约合法档位（bool 只认 1）；从 trials 按 attempt 复算 Part1 final_score/final_time（最高分尝试内最快） |
| P4 | course runner 的 ground 分类只看 plane | 已扩展：plane / `ground*` 命名 / `trench_bottom` / `level_floor`；V2 单障碍 runner 同步 |
| 演练 | 需要 pause/resume/abort/stable-stop 的 3-attempt 链路 | 已跑 3 次 pause/resume 协议演练（`config/part1-course-events-pause.json`），stable-stop 由 `StableStopTracker` 自检覆盖；abort 由 course 自检覆盖 |


## Flash 验收（第 5 轮）后修复（2026-10-23）

| 项 | 问题 | 修复 |
|---|---|---|
| P3 未接线 | `validate_external_evidence` 定义了但 `score_one` 未调用；level scene 用 `scene` 键被 `_check_hash` 跳过；缺 sha 不报错 | 已接入 `score_one`（传 trials/task_root）；`_check_hash` 支持 `scene` 键；缺 sha256 在非 diagnostic 下报错；新增篡改 hash/非法 Part2 档位/错误 final_time 的自检用例 |
| P4 未清 | ground 分类只覆盖命名地面，漏 `ramp_blocks_l/r` 非 plane 接近面 | 新增共享 `comp_part1_geom_tags.is_ground_geom()`（plane / floor / ground* / trench_bottom / level_floor / 桥前 ramp），course 与单障碍 runner 共用；conformance 增加"ramp 是 ground、桥/坡/台阶不是 ground"断言 |
| pause 内 abort 未外传 | 暂停循环里 abort 后 `run_policy_step` 返回 True，外层会以 inactive course 继续 | 暂停循环内检查 `course.active` 并 `return False`；3 次 pause→resume→abort 演练通过（`prep.d/results/part1_course_abort_drill.json`，attempts_used=3/skips=3/recoveries=3） |
| 状态复位 | `recovery_violation` 未在 begin/abort 复位；resume 未闭合 pause 区间 | 已修：begin/abort 复位；resume 把 `manager.pauses[-1][1]=t` 闭合 |
| 文案/minor | `export_report.rules.final_time` 写 `min_over_attempts`；全 skipped 时 importer fallback | 已改 `min_duration_among_best_score_attempts`；importer 全 skipped 时保留首 attempt 不崩溃 |
| 演练 | 需要 pause/resume/abort/stable-stop 3-attempt 链路 | 已跑 pause/resume 3 次完整演练（course diag，attempts_used=3）与 pause→resume→abort 3 次演练；stable-stop 由 `StableStopTracker` 自检覆盖 |


## Flash 验收（第 6 轮）后修复（2026-10-23）

| 项 | 问题 | 修复 |
|---|---|---|
| 时间账本 | pause/resume 用操作手 fake 时钟写回 `prev_t`，可能污染 active_time/final_time | 已改为**模拟器时钟**：`Part1Course` 记录 attempt_start_t，duration = end_t − start_t；暂停期间物理冻结，时长天然不含暂停；resume 不再写 fake 时钟 |
| 证据缺失静默通过 | 非 diagnostic manifest 缺 `contract`/`scenes`/`judge.file_hashes` 仍可能 valid | `validate_external_evidence` 对正式 manifest 强制要求 contract.file+sha256、scenes.part1/part2、judge.file_hashes；scenes 条目缺 file 报错 |
| 全 skipped 证据 | abort drill 导入时 final_time=0 与 trials 非零 duration 冲突 | 跳过 attempt 的 trial duration 置 0；全 skipped 时 final_score/final_time=0；importer 保留首条 attempt 不崩溃 |
| Part2 official 次数 | trench 只有 3 档、plum 1 档时只跑 3/1 次，不满足"每项 4 次" | `--official` 每 category 固定 4 次：档位从高到低，不足 4 档时重复最高档（trench=30cm×2、plum×4） |
| 证据包 | abort drill 不在 HASHES/验收包，无法独立复核 | 已复制到 `comp/audits/evidence/` 并纳入 `HASHES.json`（pause/abort 两份演练 JSON） |


## Flash 验收（第 7 轮）后修复（2026-10-23）

| 项 | 问题 | 修复 |
|---|---|---|
| 证据空条目 | 正式 manifest 的 judge.file_hashes/scenes.levels 可用空条目蒙混 | `_check_hash(required=True)`：正式 manifest 每个 file_hashes 条目、scenes.levels 条目必须含 path/scene + sha256；`scenes.part2.levels` 为空报错；自检补空条目/篡改 level hash 用例 |
| trial_id 冲突 | Part2 official 重复最高档时同一 level 两次运行生成相同 trial_id | importer 用全局 trial_seq 生成唯一 `...-a{i}-r{trial_seq}`；attempt 仍按 category 内 1–4 记录 |
| fake 时钟污染 | abort/pause 账本仍用操作手 fake t 计算 duration/pauses | `Part1Course` 增加 `last_sim_t`（每次 update 写入）；abort_attempt/pause 区间/resume 闭合全部用模拟器时钟；runner 的 fake 只用于事件触发 |
| skipped 标注 | course importer 的 skipped trial 与 attempt_result duration 易混淆 | trial 增加 `skipped` 与 `duration_note`（0 for skipped） |
| ground 白名单 | `startswith("ground")` 过宽 | 改为精确白名单（floor/trench_bottom/level_floor/ramp_blocks_l/r/ground/groundplane/ground_left/ground_right/ground_plane） |

> 残余说明：official 重复最高档在确定性策略下两次结果可能相同，稳定性统计意义有限，G1 报告需写明"4 次中的重复档"口径。


## Flash 验收（第 9 轮）后修复（minor，2026-10-23）

- export_report/summary 快照深拷贝；official summary 纳入 HASHES；formal Part2 attempts 对账改为 error；Part2 证据判定同时看 trials；pause_timeout 记录 operator_t。
- 其余第 9 轮 minor 已并入上一节。

## Flash 验收（第 8 轮）后修复（2026-10-23）

| 项 | 问题 | 修复 |
|---|---|---|
| 事件/attempt 快照 | `Part1Course.export_report()/summary()` 直接引用 manager 的 live list，后续 attempt 会改写早先 attempt 的 report 快照 | summary/attempt_results 改为 JSON 深拷贝，早先 attempt 的证据不再被后续 append 污染 |
| official summary hash | official Part2 的 summary 未纳入 HASHES 审计对象 | `comp_audit_hashes.py` 已把 `flat-ft-2500-part2-official-diag` 的 manifest/trials/summary 纳入；重生成后核对 |
| Part2 attempts 对账 | diagnostic 允许 attempts_used 与 trials 不一致，formal 不报错；part2_has_evidence 未考虑 trials | formal 下不一致改为 error；part2_has_evidence 同时依据 trials 计数 |
| fallback 证据 | Part1-only formal manifest 可能被误判 Part2 证据缺失 | `part2_has_evidence` 依据 summary + trials，Part1-only 不再强制 part2 scenes |
| official attempt 编号 | 需要 category 内 1–4 | runner 写 `attempt_index`（official_counter），importer 落 `attempt`；official artifact 24 slots 已生成 |


## Flash 验收（第 10 轮）后修复（2026-10-23）

| 项 | 问题 | 修复 |
|---|---|---|
| formal Part2 空 trials 绕过 | `attempts_used>0` 但 trials 0 条时 `obs_trials and ...` 短路不报错 | `validate_summary` 改为无条件比较 `attempts_used` 与该 obstacle 的 trials 条数；formal 下不一致一律 error（零条也报） |
| official trial_id 歧义 | official 每 record 只有 1 次 run，`i` 恒为 1，trial_id 全是 `-a1-` | trial_id 用真实 `attempt_index`：`...-a{attempt_num}-r{trial_seq}` |
| pause_timeout operator_t 丢失 | 事件在 `abort_attempt` 拷贝 `_current_events` 之后才 append，且 manager.skip 无 operator_t | timeout 事件先 append 再 abort；`abort_attempt` 给 manager skip 事件补 `operator_t` |
| 演练证据 | 需 pause_timeout 证据 | 新增 `config/part1-course-events-pause-timeout.json` 与 `comp/audits/evidence/part1_course_pause_timeout_drill.json`（reason=pause_timeout，事件含 pause_timeout/operator_t） |


## Pro 最终验收（第 12 轮）blocker 修复（2026-10-23）

| 项 | 问题 | 修复 |
|---|---|---|
| 高墙假成功（scorer blocker） | `HighWall` 只判 y=-7 穿越 + base z≥0.60，未约束穿越点 x 在真实墙段内（墙 geom pos x=1.8, size x=0.5 旋转后覆盖 x∈[1.30,2.30]），从墙外侧抬高绕过可被判成功 | 新增 `WALL_X_MIN=1.30/WALL_X_MAX=2.30`；穿越样本要求 prev_x 与 x 均在墙段内；新增 evidence `outside_x_cross`；conformance 增加"墙外侧抬高穿越必须失败"用例 |
| T 台阶 s/n/e 映射未测 | 仅测 s 臂部分分（50），未测 n/e 臂 | conformance 新增 n 臂、e 臂各一次完整臂+top 的 partial 用例，断言 score=33（Q2×2/3）；s=50 保持 |
| 契约表格陈旧措辞 | CONTRACT.md ambiguities 表仍写 75/50 | 更新为 ×2/3（仅上 50、仅下 33） |


## Flash 验收（第 16 轮）后修复（skipped 语义，2026-10-23）

| 项 | 问题 | 修复 |
|---|---|---|
| skipped trial 计入 best/evidence | `validate_external_evidence` 的 by_attempt 仍累计 skipped trial 的 judge score；`validate_summary` 的 Part1 succ_trials/evidence 未排除 skipped；abort 前已有障碍成功时可能被当证据 | by_attempt 完全跳过 skipped trial（不计分/seen/时长）；succ_trials 排除 skipped；evidence 指向 skipped trial 报 error；全 skipped 且 final 0/0 合法 |
| importer 一致性 | skipped attempt 的 trial 仍可能带 success 状态 | course importer 对 skipped attempt 强制 `judge.status="skipped"`、`score=0`，best evidence 只取非 skipped |
| self-test | 缺 skipped 正分场景 | 新增 skipped 正分 + 后续低分完成 attempt 用例（best/final_time 取完成 attempt；skipped 正分不得计入） |
| 非阻塞清理 | `WALL_CLIMB_Z` 未使用；conformance n 臂测试依赖 zone 几何无注释 | `WALL_CLIMB_Z=0.60` 并被使用；n 臂用例补几何注释 |


## GLM 最终验收（第 20 轮）发现的问题与修复（2026-10-23）

| 项 | 问题 | 修复 |
|---|---|---|
| B1（blocker，误判失败） | 离障落地阶段：`_Obstacle.update` 在 `supported` 后任意 ≥2 足触地即失败，包括已完成跨越后走下障碍落到地面；gravel/t_stairs/两桥在 zone 边界与表面边缘重合处结构性不可通过（Part1 上限 ≈300/900，返回奖励不可得） | 新增 `_ground_penalty_active(xy,tags)` 门控：默认 `supported`，各障碍覆盖——bridge 在"双平台+桥面命中≥3"后关闭判罚、T 台阶在"top+≥1 完整臂"后关闭、gravel 在 gravel_hits≥3 且 base 距出口边 ≤0.35 m 时关闭、slope 在累计 ≥1 m 后关闭；中途真坠落仍失败。conformance 新增"落地允许/中途坠落仍失败"用例（bridge/gravel/t_stairs/slope） |
| B2（major，误判失败） | 绕杆拐角首次进入即锁存；提前扫过拐角后再按正确时序通过会因 `corner_after` 过期而失败 | 拐角改为记录所有访问时的杆数 `corner_visits`，成功条件为期望时序（A=3/B=2）出现在访问集合中；同时把拐角半径从 0.5 收窄到 0.30（与 post2 的 0.35 m 距离区分），避免 post2 采样自动触发拐角；conformance 新增"提前扫过拐角后仍可合法通过"用例 |
| B3（minor，假成功） | T 台阶"另一臂缺级 + 本臂完整"仍得 33 | `_check_exit` 增加 `_has_incomplete_arm()`：任一臂有部分级（非空且非完整）即 `incomplete_step_history` 失败；conformance 增加反例 |
| B5（minor–moderate，假成功） | Part2 `held` 只累加不清零，断续满足条件也成功 | `cond` 为假时 `held=0`；self-test 增加"中断清零、连续成功"用例 |
| route 错配 | `cross_slope` 沿 x 翻屋脊，而 judge 按 y 向投影累计；slalom 路线不经过拐角必达区 | route 的 slope 段改为沿 y 走 2 m；slalom 增加拐角 waypoint；bridge 方向在 B1 修复后不再被封 |
| B4/B6/B7/B8 | 限高杆未校验"从下方"、高墙必须墙接触、沟壑 lane ±0.7 偏保守、official 固定梯子 | 记入 C1 标定集待裁决 + G1 报告残余（非当前 blocker） |
