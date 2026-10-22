# 第十轮 BYOK（deepseek-v4.1-flash）最终验收：第 9 轮 minor 修复后

角色：独立评审者（最终 flash 验收轮）。第 9 轮 flash 结论：CONCERN（无 scorer blocker），提出 5 项 minor：
① attempt/event 快照被后续 attempt 污染；② official Part2 summary 未纳入 HASHES；③ formal Part2 attempts_used 与 trials 不一致未报错；
④ fixes 文档缺第 8 轮记录；⑤ official trial_id 命名/pause_timeout operator_t。作者已修复并在 `BYOK_JUDGE_V2_FIXES.md` §"Flash 验收（第 9 轮）后修复"记录。

## 必须回答

1. 第 9 轮 5 项是否修好（快照深拷贝并重生成证据、HASHES 含 official manifest/trials/summary、formal 对账 error、文档记录、operator_t）。
2. N1–N4/P1–P4 与所有历史 PASS 项是否仍 PASS；三份/四份产物与 HASHES 是否一致可复算。
3. 是否仍有 blocker 或"无问题"标准的必须清理项。
4. **是否满足"进入 Codex 前的 flash 验收（无问题）"**（yes/no）；若 yes 列出 G1 必写残余风险；若 no 给最小修复。

## 文件（只给路径）

- `comp/audits/BYOK_JUDGE_V2_FIXES.md`、`comp/audits/BYOK_JUDGE_V9_FLASH_ACCEPT.md`
- `scripts/agent_scripts/comp_part1_judge.py`、`comp_part1_geom_tags.py`、`comp_judge_conformance.py`、`comp_part1_course.py`、`run_part1_course.py`、`run_part1_judged_rollout_v2.py`
- `scripts/agent_scripts/comp_part2_judge.py`、`make_part2_levels.py`、`run_part2_judged_eval.py`
- `scripts/agent_scripts/comp_import_diagnostic.py`、`comp_import_part2_diag.py`、`comp_import_course_diag.py`、`comp_score.py`、`comp_audit_hashes.py`、`check_part1_scene_v2.py`
- `assets/terrain/part1/part1_eval_scene_v2.xml`、`config/part1-route.json`、`config/part1-course-events-pause.json`、`config/part1-course-events-abort.json`、`config/part2-levels.json`
- `comp/eval/flat-ft-2500-part1-diag-v2/`、`comp/eval/flat-ft-2500-part2-diag-v2/`、`comp/eval/flat-ft-2500-part2-official-diag/`、`comp/eval/flat-ft-2500-part1-course-diag/`
- `comp/audits/evidence/*.json`、`comp/CONTRACT.md`、`comp/CONTRACT.json`、`comp/eval/_protocol.md`、`comp/audits/HASHES.json`、`comp/DEV_OPS.md`

## 已确认规则

Q2=×2/3；分数最高优先、同分取最快；稳定停表；恢复不消耗；返回奖励需全满分后重进出发区；Part2 仅 RL、每项 4 次；Part1 手动/自动均允许（自动无加分）；砂砾坑真实几何、Part2 官方场交叉核对、soft-reset 启发式、手动 3 次演练为 G1 必写残余。

## 输出

- verdict：PASS / CONCERN / FAIL。
- 第 9 轮 5 项逐项 PASS/STILL-BROKEN + 代码依据。
- 新问题；是否满足"进入 Codex 前的 flash 验收"（yes/no）；G1 必写残余。
- 中文；引用函数/行号；不写补丁代码。
