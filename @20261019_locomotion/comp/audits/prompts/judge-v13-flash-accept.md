# 第十三轮 BYOK（deepseek-v4.1-flash）验收：Pro 发现的 HighWall blocker 修复后

角色：独立评审者（最终 flash 验收轮）。第 12 轮 deepseek-v4-pro 判定 FAIL：高墙 `HighWall` 未把穿越约束在
真实墙段 x∈[1.30,2.30] 内，墙外侧抬高绕过可假成功（scorer blocker）；并要求补 T 台阶 n/e 臂部分分测试。
作者已修复：`WALL_X_MIN/WALL_X_MAX` 约束穿越样本、conformance 新增"墙外侧抬高穿越必须失败"与 n/e 臂 partial=33 用例，
并重新生成四份 eval 产物与三份演练证据、HASHES(60 objects)。见 `BYOK_JUDGE_V2_FIXES.md` §"Pro 最终验收（第 12 轮）blocker 修复"。

## 必须回答

1. HighWall x 段约束是否真正关闭"墙外侧抬高穿越"假成功，且墙内合法攀爬不被误判；T 台阶 n/e 臂 partial=33、s=50 是否正确。
2. N1–N4/P1–P4 与所有历史 PASS 项是否仍 PASS；四份 eval 产物（含 official 24 条）与 HASHES(60) 是否一致可复算。
3. 是否仍有 blocker 或"无问题"验收必须清理项。
4. **是否满足"进入 Codex 前的 flash 验收（无问题）"**（yes/no）；若 yes 列 G1 必写残余；若 no 给最小修复。

## 文件（只给路径）

- `comp/audits/BYOK_JUDGE_V2_FIXES.md`、`comp/audits/BYOK_JUDGE_V12_PRO_ACCEPT.md`
- `scripts/agent_scripts/comp_part1_judge.py`、`comp_part1_geom_tags.py`、`comp_judge_conformance.py`、`comp_part1_course.py`、`run_part1_course.py`、`run_part1_judged_rollout_v2.py`
- `scripts/agent_scripts/comp_part2_judge.py`、`make_part2_levels.py`、`run_part2_judged_eval.py`
- `scripts/agent_scripts/comp_import_diagnostic.py`、`comp_import_part2_diag.py`、`comp_import_course_diag.py`、`comp_score.py`、`comp_audit_hashes.py`、`check_part1_scene_v2.py`
- `assets/terrain/part1/part1_eval_scene_v2.xml`、`config/part1-route.json`、`config/part1-course-events-pause.json`、`config/part1-course-events-abort.json`、`config/part1-course-events-pause-timeout.json`、`config/part2-levels.json`
- `comp/eval/flat-ft-2500-part1-diag-v2/`、`comp/eval/flat-ft-2500-part2-diag-v2/`、`comp/eval/flat-ft-2500-part2-official-diag/`、`comp/eval/flat-ft-2500-part1-course-diag/`
- `comp/audits/evidence/*.json`、`comp/CONTRACT.md`、`comp/CONTRACT.json`、`comp/eval/_protocol.md`、`comp/audits/HASHES.json`、`comp/DEV_OPS.md`

## 已确认规则

Q2=×2/3（上 50/下 33）；分数最高优先、同分取最快；稳定停表；恢复不消耗；返回奖励需全满分后重进出发区；Part2 仅 RL、每项 4 次；Part1 手动/自动均允许（自动无加分）；砂砾坑真实几何、Part2 官方场交叉核对、soft-reset 启发式、手动 3 次演练为 G1 必写残余。

## 输出

verdict（PASS/CONCERN/FAIL）；HighWall/T 台阶逐项 PASS/STILL-BROKEN；新问题；是否满足进入 Codex 前 flash 验收（yes/no）；G1 必写残余。中文；引用函数/行号；不写补丁代码。
