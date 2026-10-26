# 第十二轮 BYOK（deepseek-v4-pro）最终验收：flash 已 PASS 后的独立复核

角色：独立评审者（用户指定的"Codex 前 deepseek-pro 验收"轮）。第 11 轮 deepseek-v4.1-flash 对当前状态给出 PASS
（无 scorer blocker、无"无问题"验收必须清理项）。用户要求：flash 与 pro 两轮均无问题后，才可向用户申请 Codex G1 终审。
请独立复核，不要因 flash 说 PASS 就放行。

## 本轮必须回答

1. 独立核验当前评测器 V2.1 是否仍存在**可被利用的假成功**或**合法通过被误判失败**：
   Part1 八障碍（限高杆/高墙/方墩桥/窄带桥/砂砾坑/T 台阶/斜坡/绕杆）成功语义、任意瞬间 1/2 足、落杆、双向绕杆、
   三臂台阶与 Q2=×2/3 部分分、返回奖励（全满分后重进出发区）；Part2 六类成功判据/触碰证据/lane 约束/墙体跨越/沟壑跨越/梅花桩。
2. 尝试协议与账本：3 次尝试、恢复不消耗、暂停不喂 judge、稳定停表用物理 dt、best score/fastest（同分最快只在最高分内）、
   abort/skip 事件用模拟器时钟；完整整场 runner 是否逐物理步采样；pause/resume/abort/pause_timeout 演练证据。
3. 证据链：四份 eval 产物（part1-diag-v2、part2-diag-v2、part2-official-diag、part1-course-diag）summary 能否由 trials 复算；
   HASHES(60 objects) 是否覆盖 scenes/judge/contract/levels/official/course 证据；comp_score 是否机器复核 hash、Part2 合法档位、
   attempts_used 与 trials 对账、重复 trial_id、Part1 final_time。
4. 是否仍有 blocker；**是否同意"flash 与 pro 两轮均无问题"、可以向用户申请 Codex G1 终审（yes/no）**。
   若 no，给最小修复；若 yes，列 Codex 应重点复核的 3–5 项与 G1 报告必须写明的残余风险。

## 文件（只给路径）

- `comp/audits/BYOK_JUDGE_V2_FIXES.md`（11 轮修复映射）、`comp/audits/BYOK_JUDGE_V11_FLASH_ACCEPT.md`（flash PASS）
- `scripts/agent_scripts/comp_part1_judge.py`、`comp_part1_geom_tags.py`、`comp_judge_conformance.py`、`comp_part1_course.py`、`run_part1_course.py`、`run_part1_judged_rollout_v2.py`
- `scripts/agent_scripts/comp_part2_judge.py`、`make_part2_levels.py`、`run_part2_judged_eval.py`
- `scripts/agent_scripts/comp_import_diagnostic.py`、`comp_import_part2_diag.py`、`comp_import_course_diag.py`、`comp_score.py`、`comp_audit_hashes.py`、`check_part1_scene_v2.py`
- `assets/terrain/part1/part1_eval_scene_v2.xml`、`config/part1-route.json`、`config/part1-course-events-pause.json`、`config/part1-course-events-abort.json`、`config/part1-course-events-pause-timeout.json`、`config/part2-levels.json`
- `comp/eval/flat-ft-2500-part1-diag-v2/`、`comp/eval/flat-ft-2500-part2-diag-v2/`、`comp/eval/flat-ft-2500-part2-official-diag/`、`comp/eval/flat-ft-2500-part1-course-diag/`
- `comp/audits/evidence/*.json`、`comp/CONTRACT.md`、`comp/CONTRACT.json`、`comp/eval/_protocol.md`、`comp/audits/HASHES.json`、`comp/DEV_OPS.md`
- `docs/reference/team-race-2026.md`、`comp/audits/JUDGE_AUDIT.md`（首轮 FAIL）

## 已确认规则

Q2=×2/3（上 50/下 33）；分数最高优先、同分取最快；稳定停表；恢复不消耗；返回奖励需全满分后重进出发区；
Part2 仅 RL、每项 4 次；Part1 手动/自动均允许（自动无加分）；砂砾坑真实几何、Part2 官方场交叉核对、soft-reset 启发式、
手动 3 次演练为 G1 必写残余。

## 输出

verdict（PASS/CONCERN/FAIL）；blocker/误伤/证据链结论；是否同意申请 Codex（yes/no）；Codex 必查项；G1 必写残余。
中文；引用函数/行号；不写补丁代码。
