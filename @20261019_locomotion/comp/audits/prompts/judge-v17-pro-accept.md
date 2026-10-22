# 第十七轮 BYOK（deepseek-v4-pro）最终验收：skipped 语义修复后

角色：Codex 前 pro 验收轮。第 16 轮 flash 指出 skipped trial 可计入 Part1 best/success evidence（正式链路假成功风险），
作者已修：by_attempt 完全跳过 skipped、succ_trials/evidence 排除 skipped、evidence 指向 skipped 报 error、importer 对
skipped 强制 status="skipped"/score=0、self-test 覆盖 skipped 正分；四份产物重新导入，HASHES 62 objects。见 FIXES §"Flash 第 16 轮后修复"。

## 必须回答
1. skipped 语义是否闭环；是否存在新的正式链路边界（abort 前部分成功、全 skipped、return bonus、final_time）。
2. 独立复核全部历史 PASS 项与证据链（Part1/Part2 judge 语义、HighWall/T 台阶、N1–N4/P1–P4、四份产物 summary 可由 trials 复算、HASHES）。
3. 是否仍有 blocker/假成功/误伤。
4. **是否同意"flash 与 pro 两轮均无问题"、可以向用户申请 Codex G1 终审**（yes/no）；若 yes 列 Codex 必查 3–5 项与 G1 必写残余；若 no 给最小修复。

## 文件（只给路径）
- `comp/audits/BYOK_JUDGE_V2_FIXES.md`、`comp/audits/BYOK_JUDGE_V16_FLASH_ACCEPT.md`、`comp/audits/BYOK_JUDGE_V15_PRO_ACCEPT.md`
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
verdict（PASS/CONCERN/FAIL）；skipped 逐项；误伤/假成功；是否同意申请 Codex（yes/no）；Codex 必查项；G1 必写残余。中文；引用函数/行号；不写补丁代码。
