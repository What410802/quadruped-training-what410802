# 第 22 轮 BYOK 独立复验：C1 标定后的 judge 终态（砂砾坑短边 + 限高杆 under-pass）

你是独立 reviewer（different-family）。只依据给定文件路径自行阅读、独立推导；不要因为作者说明、
C1 报告或前几轮结论而放行。请检查当前终态的**规则语义、实现、证据链**是否一致。

## 必须回答

1. **砂砾碎木坑**：场景 XML 的 L 形几何与 `comp_part1_judge.py::GravelPit` 的进出判定是否满足契约
   "从 1 m 短边进入且从 1 m 短边离开、long-edge 进出失败"？合法 L 路径能否 success；长边进入/退出是否失败；
   坑中段 2 足触地是否失败；合法离开后落地是否不判罚。
2. **限高杆**：`HeightBar` 是否真正要求从杆下方穿过（不是只看杆掉落）；低姿态通过是否 success、
   站立高度通过是否 not_under_bar、杆掉落是否 fail；是否有新的误判。
3. **route**：`config/part1-route.json` 的 gravel 段是否为合法 L 路径；course/诊断路线与 judge 语义是否一致。
4. **C1 标定**：`comp/eval/_calibration/` 的 92 条记录、labels、`C1_CALIBRATION_REPORT.md`、
   `LABELS_PROVENANCE.md` 是否一致；标签来源限制是否被诚实记录；是否还有 judge-human 不一致。
5. **回归与证据链**：conformance 13 组、各 self-test、四份产物 summary↔trials、三份演练、`HASHES.json`、
   `G1_SELFCHECK.md` 是否一致；有无新的 scorer 假成功/误判失败/正式链路缺口。
6. **结论**：verdict = PASS / CONCERN / FAIL；是否有 blocker；是否建议进入下一阶段（C2/轨迹训练）（yes/no）；
   G1 必写残余。

## 文件（只给路径，不提供结论）

- `scripts/agent_scripts/comp_part1_judge.py`、`comp_part1_geom_tags.py`、`comp_judge_conformance.py`、`comp_part1_course.py`、`run_part1_course.py`、`run_part1_judged_rollout_v2.py`
- `scripts/agent_scripts/comp_part2_judge.py`、`make_part2_levels.py`、`run_part2_judged_eval.py`
- `scripts/agent_scripts/comp_import_diagnostic.py`、`comp_import_part2_diag.py`、`comp_import_course_diag.py`、`comp_import_selftest.py`、`comp_score.py`、`comp_audit_hashes.py`、`comp_review.py`、`check_part1_scene_v2.py`
- `assets/terrain/part1/part1_eval_scene_v2.xml`、`assets/terrain/part2/ability_field/part2_ability_field.xml`、`assets/terrain/part2/part2_plum_eval_scene.xml`
- `config/part1-route.json`、`config/part1-course-events-pause.json`、`config/part1-course-events-abort.json`、`config/part1-course-events-pause-timeout.json`、`config/part2-levels.json`
- `comp/eval/flat-ft-2500-part1-diag-v2/`、`comp/eval/flat-ft-2500-part2-diag-v2/`、`comp/eval/flat-ft-2500-part2-official-diag/`、`comp/eval/flat-ft-2500-part1-course-diag/`
- `comp/audits/evidence/part1_course_pause_resume_drill.json`、`part1_course_abort_drill.json`、`part1_course_pause_timeout_drill.json`
- `comp/eval/_calibration/records.jsonl`、`labels_template.csv`、`LABELS_PROVENANCE.md`、`README_C1.md`
- `comp/audits/C1_CALIBRATION_REPORT.md`、`G1_SELFCHECK.md`、`HASHES.json`
- `comp/CONTRACT.md`、`comp/CONTRACT.json`、`comp/eval/_protocol.md`、`comp/DEV_OPS.md`、`comp/STATUS.md`、`docs/reference/team-race-2026.md`

## 已确认规则

Q2=×2/3（上 50/下 33/两侧 100，舍去）；分数最高优先、同分取最快；稳定停表；恢复不消耗；
返回奖励需全 8 项满分后重进出发区；Part2 仅 RL、每项 4 次；Part1 手动/自动均允许（自动无加分）；
砂砾坑真实坑体/碎木未 recut、Part2 官方场未逐档核对、soft-reset 启发式为 G1 必写残余。

## 输出

verdict（PASS/CONCERN/FAIL）；逐项回答 1–5；新问题；是否建议进入下一阶段（yes/no）；G1 必写残余。
中文；引用文件/函数/行号；不写补丁代码。
