# 第四轮 BYOK（DeepSeek pro）复验：N1–N4 是否清零、能否送 Codex G1

角色：独立评审者。上一轮（pro）verdict=FAIL，指出正式整场链路 N1–N4：
N1 course runner 未逐物理步采样；N2 course importer 的 best-attempt/duration 口径错；
N3 同分最快时间口径未落到"最高分尝试内取最快"；N4 bool 曲线仍非 `==1`。
作者已在 `comp/audits/BYOK_JUDGE_V2_FIXES.md` §"Pro 预审后修复"声明修复。请独立验证，不要以测试通过代替实现正确。

## 本轮目标

1. 逐项验证 N1–N4 是否真的修好（给出代码依据/仍存在的利用路径）。
2. 检查新引入的问题（逐物理步采样是否引入事件/时序问题；per-attempt 记录是否与 importer、comp_score 一致；
   同分最快时间是否只在最高分尝试内取；bool 是否只认 1）。
3. 检查三份重新生成的 diagnostic 是否与当前代码/场景 hash 一致、summary 可由 trials 复算。
4. 给结论：是否仍有 blocker？**是否可以送 Codex G1 终审（1 次，需用户批准）**？若不可，列出最小修复集合。

## 文件（只给路径）

- `comp/audits/BYOK_JUDGE_V2_FIXES.md`（第一/二/Pro 三轮修复映射）
- `comp/audits/BYOK_JUDGE_V3_PRO_REVIEW.md`（上一轮原始报告）
- `scripts/agent_scripts/comp_part1_judge.py`、`comp_part1_geom_tags.py`、`comp_judge_conformance.py`、
  `comp_part1_course.py`、`run_part1_course.py`
- `scripts/agent_scripts/comp_part2_judge.py`、`make_part2_levels.py`、`run_part2_judged_eval.py`
- `scripts/agent_scripts/comp_import_diagnostic.py`、`comp_import_part2_diag.py`、`comp_import_course_diag.py`、`comp_score.py`
- `scripts/agent_scripts/check_part1_scene_v2.py`
- `assets/terrain/part1/part1_eval_scene_v2.xml`、`config/part1-route.json`、`config/part2-levels.json`
- `comp/eval/flat-ft-2500-part1-diag-v2/`、`comp/eval/flat-ft-2500-part2-diag-v2/`、
  `comp/eval/flat-ft-2500-part1-course-diag/`（manifest/summary/trials）
- `comp/CONTRACT.md`、`comp/CONTRACT.json`、`comp/eval/_protocol.md`、`comp/audits/HASHES.json`

## 已确认规则（2026-10-22）

Q2=×2/3（上 50、下 33.33→33）；分数最高优先、同分取最快；Part 1 计时在机器人稳定停下后停止；
恢复不消耗尝试；返回奖励需全部障碍满分后重新进入出发区；Part 2 仅 RL、每项 4 次。

## 输出

- verdict：`PASS` / `CONCERN` / `FAIL`（预审建议）。
- N1–N4 逐项 PASS/STILL-BROKEN + 代码依据。
- 新问题清单（严重度/文件/函数/利用路径/建议）。
- **是否可送 Codex**：给 yes/no + 送审前必须做的事 + Codex 应重点检查的 3–5 项。
- 中文；引用函数/行号；不写补丁代码。
