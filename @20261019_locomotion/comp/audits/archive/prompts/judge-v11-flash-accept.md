# 第十一轮 BYOK（deepseek-v4.1-flash）最终验收：第 10 轮 3 项修复后

前一轮 flash：CONCERN（无 scorer blocker），3 项必须清理：① formal Part2 `attempts_used>0` 但 trials 0 条仍短路不报错；
② official trial_id 仍全 `-a1-`；③ pause_timeout 的 operator_t 未进入 AttemptResult/manager 事件。作者已在
`BYOK_JUDGE_V2_FIXES.md` §"Flash 验收（第 10 轮）后修复"记录。

## 必须回答

1. 第 10 轮 3 项是否修好（代码依据 + 证据）：正式 Part2 attempts_used 与 trials 无条件对账；official trial_id 用真实 attempt；
   pause_timeout 事件与 operator_t 进入 attempt_result/manager events（有 `evidence/part1_course_pause_timeout_drill.json`）。
2. N1–N4/P1–P4 与所有历史 PASS 项是否仍 PASS；四份 eval 产物（含 official）与 HASHES(60 objects) 是否一致可复算。
3. 是否仍有 blocker，或"无问题"验收的必须清理项。
4. 结论：**是否满足"进入 Codex 前的 flash 验收（无问题）"**（yes/no）；若 yes 列 G1 必写残余；若 no 给最小修复。

## 文件（只给路径）

- `comp/audits/BYOK_JUDGE_V2_FIXES.md`、`comp/audits/BYOK_JUDGE_V10_FLASH_ACCEPT.md`
- `scripts/agent_scripts/comp_part1_judge.py`、`comp_part1_geom_tags.py`、`comp_judge_conformance.py`、`comp_part1_course.py`、`run_part1_course.py`、`run_part1_judged_rollout_v2.py`
- `scripts/agent_scripts/comp_part2_judge.py`、`make_part2_levels.py`、`run_part2_judged_eval.py`
- `scripts/agent_scripts/comp_import_diagnostic.py`、`comp_import_part2_diag.py`、`comp_import_course_diag.py`、`comp_score.py`、`comp_audit_hashes.py`、`check_part1_scene_v2.py`
- `assets/terrain/part1/part1_eval_scene_v2.xml`、`config/part1-route.json`、`config/part1-course-events-pause.json`、`config/part1-course-events-abort.json`、`config/part1-course-events-pause-timeout.json`、`config/part2-levels.json`
- `comp/eval/flat-ft-2500-part1-diag-v2/`、`comp/eval/flat-ft-2500-part2-diag-v2/`、`comp/eval/flat-ft-2500-part2-official-diag/`、`comp/eval/flat-ft-2500-part1-course-diag/`
- `comp/audits/evidence/*.json`、`comp/CONTRACT.md`、`comp/CONTRACT.json`、`comp/eval/_protocol.md`、`comp/audits/HASHES.json`、`comp/DEV_OPS.md`

## 已确认规则

Q2=×2/3；分数最高优先、同分取最快；稳定停表；恢复不消耗；返回奖励需全满分后重进出发区；Part2 仅 RL、每项 4 次；
Part1 手动/自动均允许（自动无加分）；砂砾坑真实几何、Part2 官方场交叉核对、soft-reset 启发式、手动 3 次演练为 G1 必写残余。

## 输出

verdict（PASS/CONCERN/FAIL）；3 项逐项 PASS/STILL-BROKEN；新问题；是否满足进入 Codex 前 flash 验收（yes/no）；G1 必写残余。
中文；引用函数/行号；不写补丁代码。
