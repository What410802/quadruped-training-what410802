# 第八轮 BYOK（deepseek-v4.1-flash）最终验收：第 7 轮问题修复后

角色：独立评审者（最终 flash 验收轮）。第 7 轮 flash 结论：第 6 轮 4 项主路径 PASS，但提出空证据条目、
Part2 official 重复档 trial_id 冲突、abort/pause 仍写 fake 时钟、skipped 标注、ground 前缀过宽。作者已在
`comp/audits/BYOK_JUDGE_V2_FIXES.md` §"Flash 验收（第 7 轮）后修复"记录修复。请独立验证。

## 本轮必须回答

1. 第 7 轮 5 个问题是否修好（空条目必报错、trial_id 唯一、abort/pause 用模拟器时钟、skipped 标注、ground 白名单）。
2. N1–N4、P1–P4、第 6 轮 4 项是否仍 PASS。
3. 新问题：唯一 trial_id 与 attempts_used 对账、`last_sim_t` 账本、严格 evidence 校验是否引入回归。
4. 结论：**是否还有 blocker**？是否满足"进入 Codex 前的 flash 验收（无问题）"（yes/no）？若 no 给最小修复清单。

## 文件（只给路径）

- `comp/audits/BYOK_JUDGE_V2_FIXES.md`、`comp/audits/BYOK_JUDGE_V7_FLASH_ACCEPT.md`
- `scripts/agent_scripts/comp_part1_judge.py`、`comp_part1_geom_tags.py`、`comp_judge_conformance.py`、
  `comp_part1_course.py`、`run_part1_course.py`、`run_part1_judged_rollout_v2.py`
- `scripts/agent_scripts/comp_part2_judge.py`、`make_part2_levels.py`、`run_part2_judged_eval.py`
- `scripts/agent_scripts/comp_import_diagnostic.py`、`comp_import_part2_diag.py`、`comp_import_course_diag.py`、`comp_score.py`
- `scripts/agent_scripts/check_part1_scene_v2.py`
- `assets/terrain/part1/part1_eval_scene_v2.xml`、`config/part1-route.json`、`config/part1-course-events-pause.json`、
  `config/part1-course-events-abort.json`、`config/part2-levels.json`
- `comp/eval/flat-ft-2500-part1-diag-v2/`、`comp/eval/flat-ft-2500-part2-diag-v2/`、
  `comp/eval/flat-ft-2500-part1-course-diag/`
- `comp/audits/evidence/part1_course_pause_resume_drill.json`、`comp/audits/evidence/part1_course_abort_drill.json`
- `comp/CONTRACT.md`、`comp/CONTRACT.json`、`comp/eval/_protocol.md`、`comp/audits/HASHES.json`、`comp/DEV_OPS.md`

## 已确认规则

Q2=×2/3；分数最高优先、同分取最快；稳定停表；恢复不消耗；返回奖励需全满分后重进出发区；
Part2 仅 RL、每项 4 次；Part1 手动/自动均允许（自动无加分）；已知残余（砂砾坑真实几何、Part2 官方场交叉核对、
soft-reset 启发式、手动 3 次演练）须在 G1 报告写明。

## 输出

- verdict：PASS / CONCERN / FAIL（验收建议）。
- 第 7 轮 5 项逐项 PASS/STILL-BROKEN + 代码依据。
- 新问题清单（严重度/文件/函数/利用路径/建议）。
- 是否满足"进入 Codex 前的 flash 验收"（yes/no）；仍保留的 G1 必写残余。
- 中文；引用函数/行号；不写补丁代码。
