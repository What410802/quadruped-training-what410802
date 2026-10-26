# 第九轮 BYOK（deepseek-v4.1-flash）最终验收：第 8 轮 CONCERN 修复后

角色：独立评审者（最终 flash 验收轮）。第 8 轮 flash 结论：无 scorer blocker，但有 4 项必须清理：
① Part2 official attempt 字段非 category 内 1–4、缺 official 4 次落盘产物；② abort/pause/resume/skip 事件仍有 fake 时钟；
③ comp_score 不拒绝重复 trial_id、`_check_hash` 无非 dict 防护、Part1-only 正式 manifest 可能被误判；
④ 缺空条目/level hash 篡改/重复 trial_id 自检。作者已修复并在 `comp/audits/BYOK_JUDGE_V2_FIXES.md` §"Flash 验收（第 8 轮）后修复"记录。

## 本轮必须回答

1. 第 8 轮 4 项是否修好（official attempt 1–4 与 24 条落盘证据、事件账本用 last_sim_t、重复 trial_id 校验、Part1-only 正式 manifest 不误判、4 个自检用例）。
2. N1–N4、P1–P4、前几轮所有 PASS 项是否仍 PASS。
3. 是否存在新的 blocker/回归（尤其：event/trial 唯一性、HASHES 55 objects、official artifact 的 attempts 对账）。
4. 结论：**是否满足"进入 Codex 前的 flash 验收（无问题）"**（yes/no）；若 no 列最小修复；yes 则说明仍必须写进 G1 报告的残余风险。

## 文件（只给路径）

- `comp/audits/BYOK_JUDGE_V2_FIXES.md`、`comp/audits/BYOK_JUDGE_V8_FLASH_ACCEPT.md`
- `scripts/agent_scripts/comp_part1_judge.py`、`comp_part1_geom_tags.py`、`comp_judge_conformance.py`、
  `comp_part1_course.py`、`run_part1_course.py`、`run_part1_judged_rollout_v2.py`
- `scripts/agent_scripts/comp_part2_judge.py`、`make_part2_levels.py`、`run_part2_judged_eval.py`
- `scripts/agent_scripts/comp_import_diagnostic.py`、`comp_import_part2_diag.py`、`comp_import_course_diag.py`、`comp_score.py`
- `scripts/agent_scripts/check_part1_scene_v2.py`、`comp_audit_hashes.py`
- `assets/terrain/part1/part1_eval_scene_v2.xml`、`config/part1-route.json`、`config/part1-course-events-pause.json`、
  `config/part1-course-events-abort.json`、`config/part2-levels.json`
- `comp/eval/flat-ft-2500-part1-diag-v2/`、`comp/eval/flat-ft-2500-part2-diag-v2/`、
  `comp/eval/flat-ft-2500-part2-official-diag/`、`comp/eval/flat-ft-2500-part1-course-diag/`
- `comp/audits/evidence/part1_course_pause_resume_drill.json`、`comp/audits/evidence/part1_course_abort_drill.json`
- `comp/CONTRACT.md`、`comp/CONTRACT.json`、`comp/eval/_protocol.md`、`comp/audits/HASHES.json`、`comp/DEV_OPS.md`

## 已确认规则

Q2=×2/3；分数最高优先、同分取最快；稳定停表；恢复不消耗；返回奖励需全满分后重进出发区；Part2 仅 RL、每项 4 次；
Part1 手动/自动均允许（自动无加分）；砂砾坑真实几何、Part2 官方场交叉核对、soft-reset 启发式、手动 3 次演练为 G1 必写残余。

## 输出

- verdict：PASS / CONCERN / FAIL（验收建议）。
- 第 8 轮 4 项逐项 PASS/STILL-BROKEN + 代码依据。
- 新问题清单；是否满足"进入 Codex 前的 flash 验收"（yes/no）；G1 必写残余。
- 中文；引用函数/行号；不写补丁代码。
