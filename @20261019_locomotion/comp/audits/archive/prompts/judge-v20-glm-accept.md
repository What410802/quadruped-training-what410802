# 第二十轮 BYOK（Zhipu GLM-5.3）最终验收：Codex 暂不可用时的 independent-family 复核

角色：独立评审者。背景：该评测器已经 deepseek-v4.1-flash 第 19 轮 PASS、deepseek-v4-pro 第 19 轮 PASS；但用户规定
**不得私自调用 Codex**，且 Codex 额度预计一周内不可用。因此按用户 2026-10-23 指示，用智谱 GLM-5.3 做第三轮
different-family 复核；若 GLM 也判 PASS，则进入下一阶段（C1 人工标定 / 基线评测），Codex 恢复后补最终 acquittal。
请独立复核，不要因为前两轮 PASS 就放行。

## 必须回答

1. **Part 1 评测器 V2.1 是否仍有可利用的假成功或误判失败**：8 障碍（限高杆/高墙/方墩桥/窄带桥/砂砾坑/T 台阶/斜坡/绕杆）
   的成功语义、任意瞬间 ≥2 足触地、落杆、双向绕杆、T 台阶三臂与 Q2=×2/3（上 50/下 33/两侧 100）部分分、返回奖励
   （全部障碍满分后重进出发区）；整场 course runner 是否逐物理步采样、3 次尝试/恢复不消耗/暂停不喂 judge/稳定停表
   用物理 dt/同分取最快只在最高分尝试内/abort、skip、pause_timeout 事件用模拟器时钟。
2. **Part 2 评测器**：六类（高台/台阶/斜坡/高墙/沟壑/梅花桩）成功判据、分数曲线 floor、10 cm 端点 0、lane 约束、
   墙体跨越、沟壑 near/far 跨越、触碰证据、任意瞬间规则、每项 4 次（official 不足 4 档重复最高档）语义。
3. **证据链**：四份 eval 产物（part1-diag-v2、part2-diag-v2、part2-official-diag、part1-course-diag）的 summary 能否
   由 trials 复算；HASHES(62 objects) 是否覆盖场景/judge/contract/levels/official/course/演练证据；comp_score 是否机器复核
   外部 hash、Part2 合法档位、attempts_used 与 trials 对账、重复 trial_id、Part1 final_time（含 skipped 语义）。
   演练证据 `comp/audits/evidence/*.json`（pause/resume、abort、pause_timeout）是否成立。
4. **结论**：verdict = PASS / CONCERN / FAIL；是否有 blocker；**是否同意"可以进入下一阶段（C1 人工标定 / C2 基线评测）"**（yes/no）；
   若 yes，列 G1 报告必须写明的残余风险与建议下一步；若 no，给最小修复清单。

## 已确认规则（2026-10-22 用户转述主办方）

Q2=×2/3（上 50、下 33、两侧 100，小数舍去）；分数最高优先、得分相同取最快；计时在机器人稳定停下后停止；
恢复不消耗尝试；返回奖励需全部 8 障碍满分后重新进入出发区；Part 2 仅 RL、每项最多 4 次；Part 1 手动/自动均允许
（自动无加分）；已知缺口：砂砾坑真实几何未 recut、Part2 官方能力场未逐档核对、soft-reset 启发式、正式手动 3 次
整场演练未在真实赛程完成、`_protocol.md` 仍 draft。

## 文件（只给路径）

- `comp/audits/BYOK_JUDGE_V2_FIXES.md`（19 轮修复映射）、`comp/audits/BYOK_JUDGE_V19_FLASH_ACCEPT.md`、`comp/audits/BYOK_JUDGE_V19_PRO_ACCEPT.md`
- `comp/audits/JUDGE_AUDIT.md`（首轮 FAIL 与 §9/10）
- `scripts/agent_scripts/comp_part1_judge.py`、`comp_part1_geom_tags.py`、`comp_judge_conformance.py`、`comp_part1_course.py`、`run_part1_course.py`、`run_part1_judged_rollout_v2.py`
- `scripts/agent_scripts/comp_part2_judge.py`、`make_part2_levels.py`、`run_part2_judged_eval.py`
- `scripts/agent_scripts/comp_import_diagnostic.py`、`comp_import_part2_diag.py`、`comp_import_course_diag.py`、`comp_import_selftest.py`、`comp_score.py`、`comp_audit_hashes.py`、`comp_review.py`、`check_part1_scene_v2.py`
- `assets/terrain/part1/part1_eval_scene_v2.xml`、`assets/terrain/part2/ability_field/part2_ability_field.xml`、`assets/terrain/part2/part2_plum_eval_scene.xml`
- `config/part1-route.json`、`config/part1-course-events-pause.json`、`config/part1-course-events-abort.json`、`config/part1-course-events-pause-timeout.json`、`config/part2-levels.json`
- `comp/eval/flat-ft-2500-part1-diag-v2/`（manifest/summary/trials）、`comp/eval/flat-ft-2500-part2-diag-v2/`、`comp/eval/flat-ft-2500-part2-official-diag/`、`comp/eval/flat-ft-2500-part1-course-diag/`
- `comp/audits/evidence/part1_course_pause_resume_drill.json`、`part1_course_abort_drill.json`、`part1_course_pause_timeout_drill.json`
- `comp/CONTRACT.md`、`comp/CONTRACT.json`、`comp/eval/_protocol.md`、`comp/audits/HASHES.json`、`comp/DEV_OPS.md`、`comp/STATUS.md`
- `docs/reference/team-race-2026.md`、`comp/SCOREBOARD.md`、`comp/SCOREBOARD.json`

## 输出

- verdict：PASS / CONCERN / FAIL（给依据）。
- 是否有 scorer blocker / 合法通过被误判失败。
- 证据链结论（HASHES、summary↔trials、comp_score）。
- **是否同意进入下一阶段（yes/no）**；G1 必写残余；建议下一步。
- 中文；引用函数/行号；不要写补丁代码。
