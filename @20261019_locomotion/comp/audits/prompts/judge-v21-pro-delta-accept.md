# 第二十一轮 BYOK pro 复验（delta 验收）：GLM 发现的 B1/B2/B3/B5/route 修复后

背景：第 20 轮智谱 GLM-5.3 独立复核判定 FAIL，指出 8 项问题，其中 B1（离障落地 1/2 足误判失败）为 scorer blocker。
作者已修复 B1/B2/B3/B5 与 route 错配，并重新生成四份 eval 产物与三份演练证据；修复映射见
`comp/audits/BYOK_JUDGE_V2_FIXES.md` §"GLM 最终验收（第 20 轮）发现的问题与修复"。
请独立验证修复是否真正生效、是否引入回归，不要因为作者/前几轮结论而放行。

## 必须回答

1. **B1**：`_Obstacle._ground_penalty_active` 门控是否让"完成跨越后下障碍/落到地面"合法，同时"中途真坠落（桥面中段/台阶未完成/砂砾坑中段双足触地）"仍判失败；
   四个 ground_fail 障碍（bridge_blocks/bridge_bands/gravel_pit/t_stairs/slope）覆盖是否完整。
2. **B2**：绕杆拐角改为记录所有访问时序 + 半径 0.30 后，提前扫过拐角是否不再误杀合法路径，乱序/缺拐角是否仍拒绝。
3. **B3/B5**：T 台阶"另一臂缺级"是否仍能得分；Part2 hold 是否真正连续（中断清零）。
4. **route**：slope 段是否沿判分轴（y 投影）、slalom 是否经过拐角必达区；其余 bridge 方向在 B1 修复后是否可通过。
5. **回归与证据链**：conformance 13 组、各 self-test、四份产物 summary↔trials、HASHES(66 objects) 是否一致；
   是否有新的假成功/误判失败/正式链路缺口。
6. **结论**：verdict = PASS / CONCERN / FAIL；是否有 blocker；是否建议进入下一阶段（C1 人工标定 / C2 基线评测）（yes/no）。

## 文件（只给路径）
- `comp/audits/BYOK_JUDGE_V2_FIXES.md`、`comp/audits/BYOK_JUDGE_V20_GLM_ACCEPT.md`、`comp/audits/BYOK_JUDGE_V19_FLASH_ACCEPT.md`、`comp/audits/BYOK_JUDGE_V19_PRO_ACCEPT.md`
- `scripts/agent_scripts/comp_part1_judge.py`、`comp_part1_geom_tags.py`、`comp_judge_conformance.py`、`comp_part1_course.py`、`run_part1_course.py`、`run_part1_judged_rollout_v2.py`
- `scripts/agent_scripts/comp_part2_judge.py`、`make_part2_levels.py`、`run_part2_judged_eval.py`
- `scripts/agent_scripts/comp_import_diagnostic.py`、`comp_import_part2_diag.py`、`comp_import_course_diag.py`、`comp_import_selftest.py`、`comp_score.py`、`comp_audit_hashes.py`、`comp_review.py`、`check_part1_scene_v2.py`
- `assets/terrain/part1/part1_eval_scene_v2.xml`、`assets/terrain/part2/ability_field/part2_ability_field.xml`、`assets/terrain/part2/part2_plum_eval_scene.xml`
- `config/part1-route.json`、`config/part1-course-events-pause.json`、`config/part1-course-events-abort.json`、`config/part1-course-events-pause-timeout.json`、`config/part2-levels.json`
- `comp/eval/flat-ft-2500-part1-diag-v2/`、`comp/eval/flat-ft-2500-part2-diag-v2/`、`comp/eval/flat-ft-2500-part2-official-diag/`、`comp/eval/flat-ft-2500-part1-course-diag/`（manifest/summary/trials）
- `comp/audits/evidence/*.json`、`comp/CONTRACT.md`、`comp/CONTRACT.json`、`comp/eval/_protocol.md`、`comp/audits/HASHES.json`、`comp/DEV_OPS.md`、`comp/STATUS.md`、`docs/reference/team-race-2026.md`

## 已确认规则
Q2=×2/3（上 50/下 33/两侧 100，舍去）；分数最高优先、同分取最快；稳定停表；恢复不消耗；返回奖励需全 8 障碍满分后重进出发区；Part2 仅 RL、每项 4 次；Part1 手动/自动均允许（自动无加分）；砂砾坑真实几何未 recut、Part2 官方场未逐档核对、soft-reset 启发式为 G1 必写残余。

## 输出
verdict（PASS/CONCERN/FAIL）；B1/B2/B3/B5/route 逐项；新问题；是否建议进入下一阶段（yes/no）；G1 必写残余。中文；引用函数/行号；不写补丁代码。
