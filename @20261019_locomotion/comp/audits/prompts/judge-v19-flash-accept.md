# 第十九轮 BYOK（deepseek-v4.1-flash）最终验收：全 skipped importer 修复后

第 18 轮 flash：FAIL，唯一 blocker：`comp_import_course_diag.py` 全 skipped 分支的 `best_states={}` 置空在
`part1_obstacles/sum1` 计算之后（dead assignment），第一个 skipped attempt 在 abort 前已有 success 时会产出
"有 success/正分但无 evidence" 的 invalid 产物。作者已修：全 skipped 判定前移到 part1 汇总之前，best_rec/best_states
置空后再计算 summary；新增 `comp_import_selftest.py`（全 skipped + skipped judge states 含 success fixture，断言 0/0/
obstacles 全 false/evidence 空），已通过。见 FIXES §"Flash 第 18 轮后修复"。

## 必须回答
1. 全 skipped importer 路径是否闭环（代码顺序 + 自检 fixture）；skipped 语义是否再无残留。
2. conformance 13 组、comp_score self-test、importer self-test 是否通过；全部历史 PASS 项是否回归；四份产物与 HASHES 是否一致。
3. 是否仍有 blocker 或"无问题"验收必须清理项。
4. **是否满足"进入 Codex 前的 flash 验收（无问题）"**（yes/no）；若 yes 列 G1 必写残余；若 no 给最小修复。

## 文件（只给路径）
- `comp/audits/BYOK_JUDGE_V2_FIXES.md`、`comp/audits/BYOK_JUDGE_V18_FLASH_ACCEPT.md`
- `scripts/agent_scripts/comp_part1_judge.py`、`comp_part1_geom_tags.py`、`comp_judge_conformance.py`、`comp_part1_course.py`、`run_part1_course.py`、`run_part1_judged_rollout_v2.py`
- `scripts/agent_scripts/comp_part2_judge.py`、`make_part2_levels.py`、`run_part2_judged_eval.py`
- `scripts/agent_scripts/comp_import_diagnostic.py`、`comp_import_part2_diag.py`、`comp_import_course_diag.py`、`comp_import_selftest.py`、`comp_score.py`、`comp_audit_hashes.py`、`check_part1_scene_v2.py`
- `assets/terrain/part1/part1_eval_scene_v2.xml`、`assets/terrain/part2/ability_field/part2_ability_field.xml`、`assets/terrain/part2/part2_plum_eval_scene.xml`
- `config/part1-route.json`、`config/part1-course-events-pause.json`、`config/part1-course-events-abort.json`、`config/part1-course-events-pause-timeout.json`、`config/part2-levels.json`
- `comp/eval/flat-ft-2500-part1-diag-v2/`、`comp/eval/flat-ft-2500-part2-diag-v2/`、`comp/eval/flat-ft-2500-part2-official-diag/`、`comp/eval/flat-ft-2500-part1-course-diag/`
- `comp/audits/evidence/*.json`、`comp/CONTRACT.md`、`comp/CONTRACT.json`、`comp/eval/_protocol.md`、`comp/audits/HASHES.json`、`comp/DEV_OPS.md`

## 已确认规则
Q2=×2/3（上 50/下 33）；分数最高优先、同分取最快；稳定停表；恢复不消耗；返回奖励需全满分后重进出发区；Part2 仅 RL、每项 4 次；Part1 手动/自动均允许（自动无加分）；砂砾坑真实几何、Part2 官方场交叉核对、soft-reset 启发式、手动 3 次演练为 G1 必写残余。

## 输出
verdict（PASS/CONCERN/FAIL）；全 skipped 逐项；新问题；是否满足进入 Codex 前 flash 验收（yes/no）；G1 必写残余。中文；引用函数/行号；不写补丁代码。
