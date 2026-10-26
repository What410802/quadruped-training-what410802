# 复审任务（DeepSeek pro，第三轮 BYOK）：RoboCon 2026 评测器 V3 候选

角色：独立评审者。前两轮 flash 预审均为 FAIL；本轮升级到 pro，只判断"是否仍有 blocker 级假成功/误伤/证据链问题"。
`comp/audits/BYOK_JUDGE_V2_FIXES.md` 记录作者修复映射（含"二次预审后修复"），请独立验证，不要以测试通过代替实现正确。

## 已确认规则更新（2026-10-22，需按此审）

- **Q2 已确认**：T 台阶部分分 = 原值 ×2/3：仅上=50、仅下=50×2/3≈33.33→按舍去=33；两侧都过=100。
- **排序**：分数最高优先，同分取最快；Part 1 计时在机器人**稳定停下后**停止（不是首次进入出发区即停）。
- 恢复不消耗尝试；开始/主动重跑消耗；返回奖励要求全部障碍**满分**之后重新进入出发区。
- Part 1 允许手动/固定动作（自动无加分）；Part 2 仅 RL。

## 要审的文件（只给路径）

- `comp/audits/BYOK_JUDGE_V2_FIXES.md`（第一/二轮修复映射，需验证）
- `scripts/agent_scripts/comp_part1_judge.py`、`comp_part1_geom_tags.py`、`comp_judge_conformance.py`
- `scripts/agent_scripts/comp_part1_course.py`、`run_part1_course.py`
- `scripts/agent_scripts/comp_part2_judge.py`、`make_part2_levels.py`、`run_part2_judged_eval.py`
- `scripts/agent_scripts/comp_import_diagnostic.py`、`comp_import_part2_diag.py`、`comp_import_course_diag.py`、`comp_score.py`
- `assets/terrain/part1/part1_eval_scene_v2.xml`、`config/part1-route.json`、`config/part2-levels.json`
- `comp/eval/flat-ft-2500-part1-diag-v2/`、`comp/eval/flat-ft-2500-part2-diag-v2/`、
  `comp/eval/flat-ft-2500-part1-course-diag/`（manifest/summary/trials，注意可能是修复前生成的，若与代码 hash 不一致请指出）
- `comp/CONTRACT.md`、`comp/CONTRACT.json`、`comp/eval/_protocol.md`
- `docs/reference/team-race-2026.md`、`comp/audits/JUDGE_AUDIT.md`

## 评审要求

1. 逐条判断前两轮 blocker 是否真正清零（高墙、限高杆、T 台阶、绕杆、桥面 tag、地面判据、失败重试、返回奖励、Part2 低难度/绕行、正式整场协议、恢复/暂停）。
2. 用新的 Q2=×2/3、稳定停表、同分取最快口径检查实现与测试是否一致。
3. 寻找仍然可被利用的假成功（给出具体轨迹/位姿序列或代码路径）与合法通过的误伤。
4. 检查证据链：三份 diagnostic summary 是否可由 trials 复算、是否与当前代码/场景 hash 一致、comp_score 是否覆盖返回奖励/部分分/场景/判据 hash。
5. 检查正式整场 runner 是否同一个 `Part1Course` 会话跑 3 次尝试、暂停不死锁、稳定停表生效、importer best attempt/return evidence 正确。

## 输出

- verdict：`PASS` / `CONCERN` / `FAIL`（预审建议；最终 G1 由 Codex 出）。
- 前两轮 blocker 的 PASS/STILL-BROKEN 表。
- 新问题清单（严重度/文件/函数/利用路径/建议）。
- 给 Codex G1 终审的必查项与"是否可以送 Codex"建议。
- 中文；引用函数/行号；不写补丁代码。
