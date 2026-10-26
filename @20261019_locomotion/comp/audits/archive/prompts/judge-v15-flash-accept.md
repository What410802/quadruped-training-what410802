# 第十五轮 BYOK（deepseek-v4.1-flash）最终验收：第 13 轮 CONCERN 修复后

第 13 轮 flash：CONCERN（无 scorer blocker），4 项必须清理：① HighWall 墙外抬升 conformance 用例 x=2.7 在 zone 外未打到
`outside_x_cross` 分支；② HASHES 缺 `part2_ability_field.xml` 与 `part2_plum_eval_scene.xml`；③ comp_score 缺 Part1
`attempts_used` 与 distinct attempt 对账、final_time 复算未要求 attempt 覆盖全部 Part1 障碍；④ TStairs 默认值/docstring 75/50
与 Part1JudgeV2 的 50/33 不一致。作者已修复：用例改 x=2.33（zone 内、墙段外）、HASHES 62 objects、comp_score 两项正式校验、
TStairs 默认 50/33；四份产物已按修复后 judge 重新导入。见 `BYOK_JUDGE_V2_FIXES.md` §"Flash 第 13 轮后修复"。

## 必须回答

1. 4 项是否修好（代码/证据）；HighWall/T 台阶行为是否正确、conformance 用例是否真正打到修复分支。
2. 全部历史 PASS 项（N1–N4/P1–P4、judge 语义、证据链）是否回归；四份产物与 HASHES(62) 是否一致可复算。
3. 是否仍有 blocker 或"无问题"验收必须清理项。
4. **是否满足"进入 Codex 前的 flash 验收（无问题）"**（yes/no）；若 yes 列 G1 必写残余；若 no 给最小修复。

## 文件（只给路径）
- `comp/audits/BYOK_JUDGE_V2_FIXES.md`、`comp/audits/BYOK_JUDGE_V13_FLASH_ACCEPT.md`
- `scripts/agent_scripts/comp_part1_judge.py`、`comp_part1_geom_tags.py`、`comp_judge_conformance.py`、`comp_part1_course.py`、`run_part1_course.py`、`run_part1_judged_rollout_v2.py`
- `scripts/agent_scripts/comp_part2_judge.py`、`make_part2_levels.py`、`run_part2_judged_eval.py`
- `scripts/agent_scripts/comp_import_diagnostic.py`、`comp_import_part2_diag.py`、`comp_import_course_diag.py`、`comp_score.py`、`comp_audit_hashes.py`、`check_part1_scene_v2.py`
- `assets/terrain/part1/part1_eval_scene_v2.xml`、`assets/terrain/part2/ability_field/part2_ability_field.xml`、`assets/terrain/part2/part2_plum_eval_scene.xml`
- `config/part1-route.json`、`config/part1-course-events-pause.json`、`config/part1-course-events-abort.json`、`config/part1-course-events-pause-timeout.json`、`config/part2-levels.json`
- `comp/eval/flat-ft-2500-part1-diag-v2/`、`comp/eval/flat-ft-2500-part2-diag-v2/`、`comp/eval/flat-ft-2500-part2-official-diag/`、`comp/eval/flat-ft-2500-part1-course-diag/`
- `comp/audits/evidence/*.json`、`comp/CONTRACT.md`、`comp/CONTRACT.json`、`comp/eval/_protocol.md`、`comp/audits/HASHES.json`、`comp/DEV_OPS.md`

## 已确认规则
Q2=×2/3（上 50/下 33）；分数最高优先、同分取最快；稳定停表；恢复不消耗；返回奖励需全满分后重进出发区；Part2 仅 RL、每项 4 次；Part1 手动/自动均允许（自动无加分）；砂砾坑真实几何、Part2 官方场交叉核对、soft-reset 启发式、手动 3 次演练为 G1 必写残余。

## 输出
verdict（PASS/CONCERN/FAIL）；4 项逐项 PASS/STILL-BROKEN；新问题；是否满足进入 Codex 前 flash 验收（yes/no）；G1 必写残余。中文；引用函数/行号；不写补丁代码。
