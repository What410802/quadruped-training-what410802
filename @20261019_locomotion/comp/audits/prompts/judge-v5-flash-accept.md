# 第五轮 BYOK（deepseek-v4.1-flash）验收：P1–P4 修复后是否还有 blocker

角色：独立评审者（验收轮）。前四轮：flash FAIL×2、pro FAIL×2。第四轮 pro 确认 N1–N4 已修，但提出 P1–P4；
作者已在 `comp/audits/BYOK_JUDGE_V2_FIXES.md` §"第四轮 Pro 复验后修复"记录修复。请独立验证，**不要以测试通过代替实现正确**。

## 本轮必须回答

1. N1–N4（逐物理步采样、per-attempt best、同分最快只在最高分尝试、bool==1）现在是否仍 PASS？
2. P1–P4 是否真的修好：
   - P1 稳定停表使用真实物理 dt（5 ms）且需 0.5 s stable；
   - P2 暂停期间不向 judge 喂冻结位姿，只推进事件/超时时钟；
   - P3 `comp_score` 机器复核 scenes/judge/contract sha256、Part2 合法档位（bool==1）、Part1 final_score/final_time（最高分尝试内最快）；
   - P4 course runner 的 ground 分类覆盖非 plane 地面（命名 ground/level_floor/trench_bottom 等）。
3. 新引入问题：暂停/恢复事件时钟、stable-stop tracker、comp_score 外部证据校验是否可靠；三份重新导入的 diagnostic 与当前代码/HASHES 是否一致。
4. 结论：**是否存在 blocker**？是否满足"进入 Codex 前置条件之一（flash 验收无问题）"？若仍有问题，给最小修复清单。

## 文件（只给路径）

- `comp/audits/BYOK_JUDGE_V2_FIXES.md`（四轮修复映射）
- `comp/audits/BYOK_JUDGE_V4_PRO_VERIFY.md`（上一轮 P1–P4 报告）
- `scripts/agent_scripts/comp_part1_judge.py`、`comp_part1_geom_tags.py`、`comp_judge_conformance.py`、
  `comp_part1_course.py`、`run_part1_course.py`
- `scripts/agent_scripts/comp_part2_judge.py`、`make_part2_levels.py`、`run_part2_judged_eval.py`
- `scripts/agent_scripts/comp_import_diagnostic.py`、`comp_import_part2_diag.py`、`comp_import_course_diag.py`、`comp_score.py`
- `scripts/agent_scripts/check_part1_scene_v2.py`
- `assets/terrain/part1/part1_eval_scene_v2.xml`、`config/part1-route.json`、`config/part1-course-events-pause.json`、
  `config/part2-levels.json`
- `comp/eval/flat-ft-2500-part1-diag-v2/`、`comp/eval/flat-ft-2500-part2-diag-v2/`、
  `comp/eval/flat-ft-2500-part1-course-diag/`（manifest/summary/trials；course 为 3 次 pause/resume 演练）
- `comp/CONTRACT.md`、`comp/CONTRACT.json`、`comp/eval/_protocol.md`、`comp/audits/HASHES.json`、`comp/DEV_OPS.md`

## 已确认规则（2026-10-22）

Q2=×2/3（上 50、下 33.33→33）；分数最高优先、同分取最快；计时在机器人稳定停下后停止；
恢复不消耗尝试；返回奖励需全部障碍满分后重新进入出发区；Part 2 仅 RL、每项 4 次；手动/自动 Part1 均允许（自动无加分）。

## 输出

- verdict：`PASS` / `CONCERN` / `FAIL`（验收建议）。
- N1–N4、P1–P4 逐项 PASS/STILL-BROKEN + 代码依据。
- 新问题清单（严重度/文件/函数/利用路径/建议）。
- 是否满足"进入 Codex 前的 flash 验收"（yes/no），以及仍保留的已知残余风险（须在 G1 报告写明）。
- 中文；引用函数/行号；不写补丁代码。
