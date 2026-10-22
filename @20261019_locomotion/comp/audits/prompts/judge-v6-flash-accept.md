# 第六轮 BYOK（deepseek-v4.1-flash）验收：第 5 轮问题修复后

角色：独立评审者（验收轮）。第 5 轮 flash 验收结论：N1–N4 PASS、P1/P2 PASS，但 P3/P4/暂停内 abort 仍 broken。
作者已在 `comp/audits/BYOK_JUDGE_V2_FIXES.md` §"Flash 验收（第 5 轮）后修复"记录修复。请独立验证，不要以测试通过代替实现正确。

## 本轮必须回答

1. 第 5 轮遗留问题是否修好：
   - P3：`comp_score.validate_external_evidence` 是否被 `score_one` 实际调用（传 trials/task_root）；`scene` 键的 level hash 是否复核；缺 sha256 是否报错；篡改 hash / 非法 Part2 档位 / 错误 final_time 是否真的报 invalid（看自检与代码路径）；
   - P4：`ramp_blocks_l/r` 等非 plane 接近面是否进入 ground 分类（共享 `is_ground_geom`），且桥/坡/台阶不被误判为 ground；
   - 暂停内 abort 的终止信号是否外传（不再出现 inactive course 继续；3 次 pause→resume→abort 演练是否合理）。
2. N1–N4、P1–P2 是否仍 PASS。
3. 新问题：`is_ground_geom`、`score_one` 接线、course 状态复位是否引入新漏洞；三份重新导入的 diagnostic 与当前 `HASHES.json`（51 objects）是否一致。
4. 结论：**是否还有 blocker**？是否满足"进入 Codex 前深 flash 验收"（yes/no）？若仍 no，给最小修复清单。

## 文件（只给路径）

- `comp/audits/BYOK_JUDGE_V2_FIXES.md`、`comp/audits/BYOK_JUDGE_V5_FLASH_ACCEPT.md`
- `scripts/agent_scripts/comp_part1_judge.py`、`comp_part1_geom_tags.py`、`comp_judge_conformance.py`、
  `comp_part1_course.py`、`run_part1_course.py`、`run_part1_judged_rollout_v2.py`
- `scripts/agent_scripts/comp_part2_judge.py`、`make_part2_levels.py`、`run_part2_judged_eval.py`
- `scripts/agent_scripts/comp_import_diagnostic.py`、`comp_import_part2_diag.py`、`comp_import_course_diag.py`、`comp_score.py`
- `scripts/agent_scripts/check_part1_scene_v2.py`
- `assets/terrain/part1/part1_eval_scene_v2.xml`、`config/part1-route.json`、`config/part1-course-events-pause.json`、
  `config/part1-course-events-abort.json`、`config/part2-levels.json`
- `comp/eval/flat-ft-2500-part1-diag-v2/`、`comp/eval/flat-ft-2500-part2-diag-v2/`、
  `comp/eval/flat-ft-2500-part1-course-diag/`（manifest/summary/trials；course 为 3 次 pause/resume 演练）
- `comp/CONTRACT.md`、`comp/CONTRACT.json`、`comp/eval/_protocol.md`、`comp/audits/HASHES.json`、`comp/DEV_OPS.md`
- 运行证据：`comp/audits/JUDGE_AUDIT.md`（首轮 FAIL）、`comp/eval/_calibration/README.md`（标定集阶段）

## 已确认规则（2026-10-22）

Q2=×2/3（上 50、下 33.33→33）；分数最高优先、同分取最快；计时在机器人稳定停下后停止；
恢复不消耗尝试；返回奖励需全部障碍满分后重新进入出发区；Part 2 仅 RL、每项 4 次。

## 输出

- verdict：`PASS` / `CONCERN` / `FAIL`（验收建议）。
- 5 轮遗留项逐项 PASS/STILL-BROKEN + 代码依据。
- 新问题清单（严重度/文件/函数/利用路径/建议）。
- 是否满足"进入 Codex 前的 flash 验收"（yes/no）；仍保留、必须写进 G1 报告的已知残余风险。
- 中文；引用函数/行号；不写补丁代码。
