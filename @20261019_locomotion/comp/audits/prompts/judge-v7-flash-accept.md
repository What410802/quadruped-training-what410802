# 第七轮 BYOK（deepseek-v4.1-flash）验收：第 6 轮问题修复后

角色：独立评审者（验收轮）。第 6 轮 flash 验收结论：N1–N4/P1–P4 主项 PASS，但发现 4 个新 blocker：
① pause/resume 时间账本被 fake 时钟污染；② 正式 manifest 可省略 contract/scenes/judge.file_hashes 而静默通过；
③ all-skipped/abort drill 的 importer fallback 与 duration 冲突；④ Part2 `--official` 在不足 4 档时只跑 3/1 次。
作者已在 `comp/audits/BYOK_JUDGE_V2_FIXES.md` §"Flash 验收（第 6 轮）后修复"记录修复。请独立验证。

## 本轮必须回答

1. 第 6 轮 4 个 blocker 是否修好：
   - 时间账本是否完全用模拟器时钟（暂停期间物理冻结，duration=end−start；resume 不再写 fake prev_t）；
   - 正式 manifest 缺 contract/scenes/judge.file_hashes 或缺 scene file 时是否必然 invalid；
   - all-skipped/abort drill 的 trials duration 与 summary final_time 是否一致（看 evidence JSON 与 importer）；
   - Part2 official 是否每 category 恰好 4 次（trench 重复最高档、plum 4 次）。
2. N1–N4、P1–P4 是否仍 PASS。
3. 新问题：`is_ground_geom`、`validate_external_evidence` 严格化、sim-clock duration、official 重复档位是否引入新漏洞；
   演练证据（`comp/audits/evidence/*.json`）与 `HASHES.json`（53 objects）是否一致可复核。
4. 结论：**是否还有 blocker**？是否满足"进入 Codex 前的 flash 验收（无问题）"（yes/no）？若 no，给最小修复清单。

## 文件（只给路径）

- `comp/audits/BYOK_JUDGE_V2_FIXES.md`、`comp/audits/BYOK_JUDGE_V6_FLASH_ACCEPT.md`
- `scripts/agent_scripts/comp_part1_judge.py`、`comp_part1_geom_tags.py`、`comp_judge_conformance.py`、
  `comp_part1_course.py`、`run_part1_course.py`、`run_part1_judged_rollout_v2.py`
- `scripts/agent_scripts/comp_part2_judge.py`、`make_part2_levels.py`、`run_part2_judged_eval.py`
- `scripts/agent_scripts/comp_import_diagnostic.py`、`comp_import_part2_diag.py`、`comp_import_course_diag.py`、`comp_score.py`
- `scripts/agent_scripts/check_part1_scene_v2.py`
- `assets/terrain/part1/part1_eval_scene_v2.xml`、`config/part1-route.json`、`config/part1-course-events-pause.json`、
  `config/part1-course-events-abort.json`、`config/part2-levels.json`
- `comp/eval/flat-ft-2500-part1-diag-v2/`、`comp/eval/flat-ft-2500-part2-diag-v2/`、
  `comp/eval/flat-ft-2500-part1-course-diag/`（manifest/summary/trials）
- `comp/audits/evidence/part1_course_pause_resume_drill.json`、`comp/audits/evidence/part1_course_abort_drill.json`
- `comp/CONTRACT.md`、`comp/CONTRACT.json`、`comp/eval/_protocol.md`、`comp/audits/HASHES.json`、`comp/DEV_OPS.md`

## 已确认规则（2026-10-22）

Q2=×2/3（上 50、下 33.33→33）；分数最高优先、同分取最快；计时在机器人稳定停下后停止；
恢复不消耗尝试；返回奖励需全部障碍满分后重新进入出发区；Part 2 仅 RL、**每项 4 次**；
手动/自动 Part1 均允许（自动无加分）；砂砾坑真实几何等残余须在 G1 报告写明。

## 输出

- verdict：`PASS` / `CONCERN` / `FAIL`（验收建议）。
- 第 6 轮 4 项逐项 PASS/STILL-BROKEN + 代码依据。
- 新问题清单（严重度/文件/函数/利用路径/建议）。
- 是否满足"进入 Codex 前的 flash 验收"（yes/no）；仍保留、必须写进 G1 报告的已知残余风险。
- 中文；引用函数/行号；不写补丁代码。
