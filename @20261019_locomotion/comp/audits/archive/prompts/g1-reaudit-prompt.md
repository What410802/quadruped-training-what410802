# G1 重审任务：RoboCon 2026 队内赛评测器 V2（Part 1 / Part 2）

角色：独立 G1 审计者。你只依据本页列出的文件做判断；不要接受作者结论，也不要只看测试名。
这是对 2026-10-22 首轮 G1 FAIL 之后的**重审**，目标门禁：评测器能否作为比赛期间正式分数的依据（Type-B gate）。

## 审计对象（只给路径，自己读文件）

规则与契约：
- `docs/reference/team-race-2026.md`（主办方规则原文）
- `comp/CONTRACT.md`、`comp/CONTRACT.json`（判罚/计分契约）
- `comp/eval/_protocol.md`（评测协议草稿）
- `comp/audits/JUDGE_AUDIT.md`（首轮 FAIL 报告与主办方补充口径 §9/§9.1）

Part 1 评测器：
- `scripts/agent_scripts/comp_part1_judge.py`
- `scripts/agent_scripts/comp_judge_conformance.py`
- `scripts/agent_scripts/comp_part1_course.py`
- `scripts/agent_scripts/run_part1_judged_rollout_v2.py`
- `assets/terrain/part1/part1_eval_scene_v2.xml`

Part 2 评测器：
- `scripts/agent_scripts/comp_part2_judge.py`
- `scripts/agent_scripts/make_part2_levels.py`
- `scripts/agent_scripts/run_part2_judged_eval.py`
- `config/part2-levels.json`
- `assets/terrain/part2/`（levels 目录、part2_plum_eval_scene.xml、official_catalog.yaml）

证据链：
- `comp/eval/flat-ft-2500-part1-diag-v2/`（manifest.json、summary.json、trials.jsonl）
- `comp/eval/flat-ft-2500-part2-diag-v2/`（manifest.json、summary.json、trials.jsonl）
- `scripts/agent_scripts/comp_score.py`、`scripts/agent_scripts/comp_import_diagnostic.py`、`scripts/agent_scripts/comp_import_part2_diag.py`
- `comp/SCOREBOARD.md`、`comp/SCOREBOARD.json`

## 必须回答的问题

1. **成功语义与可欺骗性**：Part 1 八个障碍逐个检查，是否存在"不合法进入 / 无实际跨越或接触历史 / 不合法离开 / 只靠最终位姿"就能拿 success 的路径？T 台阶跨帧 history 与部分分、限高杆落杆检测、斜坡距离与方向、砂砾坑两端短边、绕杆顺序/交替/拐角/起终点、桥的平台+桥面证据、任意瞬间 ≥2 足触地——实现是否真的符合规则？
2. **误伤**：合法通过方式会不会被判失败？障碍邻接区的边界擦碰/路过（soft-reset）是否既避免误伤又没有造出新的骗分路径？
3. **尝试协议**：3 次尝试、恢复不消耗、暂停时间不计入时长、开始/重跑/跳过消耗、最终 score 取最好/ time 取最快、返回奖励前置条件；`comp_part1_course.py` 的状态机是否有不可达或重复计分漏洞？
4. **Part 2**：六类成功判据是否符合规则（高台/楼梯/斜坡/高墙/沟壑/梅花桩）；参数化 level 是否保持官方障碍种类与档位；水平/高度阈值是否会把"站地面"误判成"上平台"；计分 floor、低阈值 0、高墙/沟壑 10 cm 端点 0 是否正确；稳定性按失败比例测量（≥100 次）是否写清楚且不混入正式 4 次尝试。
5. **证据链**：`comp/eval` 产物 summary 的分数能否完全由 trials 复算；manifest 是否诚实（diagnostic 标记、seed 空、commit/dirty 说明）；`comp_score.py` 是否会接受伪造/自报分数；导入器有没有把 judge 结果映射错（例如部分分、Part2 difficulty/value）。
6. **场景与传感器红线**：`part1_eval_scene_v2.xml` 的可动横杆是否静置稳定、掉落判据阈值是否合理；接触标签与 judge surface tags 是否一致；runner 是否只把真值用于判分/生成速度指令，actor 观测是否不含禁止量（机身线速度/高程/足底力/足端高度/机身高度）。
7. **conformance 覆盖**：`comp_judge_conformance.py` 是否覆盖首轮审计的全部反例？缺哪些对 G1 结论最关键的用例？测试本身有没有"通过但实现仍有洞"的盲区？
8. **规则歧义**：Q2（T 台阶部分分 112.5 > 单项 100）、跳过/重跑是否消耗尝试、最终分数取 best 等未书面确认项，当前实现是否诚实标注，是否会在正式分数中造成可争议结果？

## 输出格式

- 先给 **verdict**：`PASS` / `CONCERN` / `FAIL`（G1 门禁结论；CONCERN 需列出通过前必须修复项）。
- 再给编号问题清单：严重度（blocker/major/minor）、涉及文件/函数/行号、可复现的利用路径或误伤场景、建议修复方向、对应缺失测试。
- 最后给"通过 G1 的最小修复集合"和"是否允许进入正式评测（C3）"。
- 中文；直接引用代码行号/函数名；不要写补丁代码；不要复述背景。
