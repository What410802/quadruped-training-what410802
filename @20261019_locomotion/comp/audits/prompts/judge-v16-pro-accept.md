# 第十六轮 BYOK（deepseek-v4-pro）最终验收：第 15 轮 FAIL 的 3 项修复后

角色：Codex 前 pro 验收轮。第 15 轮 pro 指出：final_time 复算未排除 skipped trial、formal attempts_used>0 而 trials 空可绕过、
n 臂 conformance 用例断言不精确。作者已修：skipped trial 不参与最快时间、attempts 双向对账并 formal 空 trials 报错、
n/e 臂用例断言"恰好一个完整臂 + score=33"；conformance 13 组、comp_score self-test 通过，HASHES 62 objects 刷新。
见 `BYOK_JUDGE_V2_FIXES.md` §"Pro 第 15 轮修复"。

## 必须回答
1. 3 项是否修好；是否存在新的正式链路边界（skipped、空 trials、返回奖励 full、final_time 口径）。
2. 独立复核全部历史 PASS 项与证据链（四份产物 summary 可由 trials 复算、HASHES、重复 trial_id、Part2 合法档位、HighWall/T 台阶）。
3. 是否仍有 blocker/假成功/误伤。
4. **是否同意"flash 与 pro 两轮均无问题"、可以向用户申请 Codex G1 终审**（yes/no）；若 yes 列 Codex 必查 3–5 项与 G1 必写残余；若 no 给最小修复。

## 文件（只给路径）
- `comp/audits/BYOK_JUDGE_V2_FIXES.md`、`comp/audits/BYOK_JUDGE_V15_PRO_ACCEPT.md`、`comp/audits/BYOK_JUDGE_V15_FLASH_ACCEPT.md`
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
verdict（PASS/CONCERN/FAIL）；3 项逐项；误伤/假成功结论；是否同意申请 Codex（yes/no）；Codex 必查项；G1 必写残余。中文；引用函数/行号；不写补丁代码。
