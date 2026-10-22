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
