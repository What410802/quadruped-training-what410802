# 第十五轮 BYOK（deepseek-v4-pro）最终验收：第 13 轮 4 项修复后

角色：Codex 前 pro 验收轮。第 12 轮 pro FAIL（HighWall x 段、T 台阶 n/e 未测、HASHES 覆盖、comp_score Part1 对账）。
作者已修复：HighWall `WALL_X_MIN/MAX` 穿越约束与 `outside_x_cross`、conformance 墙外/墙内用例（x=2.33 在 zone 内墙段外）、
T 台阶 s=50/n/e=33 用例、HASHES 增补 `part2_ability_field.xml`/`part2_plum_eval_scene.xml`（62 objects）、comp_score
Part1 distinct attempt 对账与 final_time 的 attempt 覆盖检查、TStairs 默认值 50/33；四份 eval 产物与三份演练证据已按修复后
judge 重新生成/导入。见 `BYOK_JUDGE_V2_FIXES.md` §"Pro 最终验收（第 12 轮）blocker 修复"。

## 必须回答

1. 第 12 轮 blocker 是否全部关闭：墙外侧抬高不再成功、墙内合法攀爬成功、T 台阶 s=50/n/e=33；HASHES 覆盖被引用的
   Part2 ability field/plum 场景；comp_score 的 Part1 attempts/final_time 正式校验是否成立、是否误伤合法证据。
2. 独立复核全部历史 PASS 项与证据链（四份产物 summary 可由 trials 复算、HASHES、重复 trial_id、Part2 合法档位）。
3. 是否仍有 blocker/可被利用假成功/合法通过被误判失败。
4. **是否同意"flash 与 pro 两轮均无问题"、可以向用户申请 Codex G1 终审**（yes/no）；若 yes 列 Codex 必查 3–5 项与 G1 必写残余；若 no 给最小修复。

## 文件（只给路径）
- `comp/audits/BYOK_JUDGE_V2_FIXES.md`、`comp/audits/BYOK_JUDGE_V12_PRO_ACCEPT.md`、`comp/audits/BYOK_JUDGE_V13_FLASH_ACCEPT.md`
- `scripts/agent_scripts/comp_part1_judge.py`、`comp_part1_geom_tags.py`、`comp_judge_conformance.py`、`comp_part1_course.py`、`run_part1_course.py`、`run_part1_judged_rollout_v2.py`
- `scripts/agent_scripts/comp_part2_judge.py`、`make_part2_levels.py`、`run_part2_judged_eval.py`
- `scripts/agent_scripts/comp_import_diagnostic.py`、`comp_import_part2_diag.py`、`comp_import_course_diag.py`、`comp_score.py`、`comp_audit_hashes.py`、`check_part1_scene_v2.py`
- `assets/terrain/part1/part1_eval_scene_v2.xml`、`assets/terrain/part2/ability_field/part2_ability_field.xml`、`assets/terrain/part2/part2_plum_eval_scene.xml`
- `config/part1-route.json`、`config/part1-course-events-pause.json`、`config/part1-course-events-abort.json`、`config/part1-course-events-pause-timeout.json`、`config/part2-levels.json`
- `comp/eval/flat-ft-2500-part1-diag-v2/`、`comp/eval/flat-ft-2500-part2-diag-v2/`、`comp/eval/flat-ft-2500-part2-official-diag/`、`comp/eval/flat-ft-2500-part1-course-diag/`
- `comp/audits/evidence/*.json`、`comp/CONTRACT.md`、`comp/CONTRACT.json`、`comp/eval/_protocol.md`、`comp/audits/HASHES.json`、`comp/DEV_OPS.md`、`docs/reference/team-race-2026.md`、`comp/audits/JUDGE_AUDIT.md`

## 已确认规则
Q2=×2/3（上 50/下 33）；分数最高优先、同分取最快；稳定停表；恢复不消耗；返回奖励需全满分后重进出发区；Part2 仅 RL、每项 4 次；Part1 手动/自动均允许（自动无加分）；砂砾坑真实几何、Part2 官方场交叉核对、soft-reset 启发式、手动 3 次演练为 G1 必写残余。

## 输出
verdict（PASS/CONCERN/FAIL）；blocker 逐项；误伤/假成功结论；是否同意申请 Codex（yes/no）；Codex 必查项；G1 必写残余。中文；引用函数/行号；不写补丁代码。
