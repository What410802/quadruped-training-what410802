# 复审任务：RoboCon 2026 队内赛评测器 V2.1（BYOK 二次预审）

角色：独立评审者。这是你对同一评测器的**第二次预审**（第一次已判 FAIL，26 条）。
`comp/audits/BYOK_JUDGE_V2_FIXES.md` 记录了作者声称的修复；请**独立验证**这些修复是否真的成立，
并继续寻找残余的假成功/误伤/证据链漏洞。不要把"有测试"当作"实现正确"。

## 背景（事实）

- 比赛规则：`docs/reference/team-race-2026.md`；契约/判罚：`comp/CONTRACT.md`、`comp/CONTRACT.json`；
  协议：`comp/eval/_protocol.md`；首轮 G1 FAIL：`comp/audits/JUDGE_AUDIT.md`；第一次预审：`comp/audits/BYOK_JUDGE_V2_REVIEW.md`。
- 本轮目标：在进入 Codex 不同家族 G1 终审前，确认 blocker 是否清零、是否仍有可被利用的路径。

## 要审的文件（只给路径，自己读）

- `comp/audits/BYOK_JUDGE_V2_REVIEW.md`（第一次预审 26 条）
- `comp/audits/BYOK_JUDGE_V2_FIXES.md`（作者修复映射，需独立验证）
- `scripts/agent_scripts/comp_part1_judge.py`（V2.1）
- `scripts/agent_scripts/comp_part1_geom_tags.py`
- `scripts/agent_scripts/comp_judge_conformance.py`
- `scripts/agent_scripts/comp_part1_course.py`
- `scripts/agent_scripts/run_part1_judged_rollout_v2.py`
- `scripts/agent_scripts/run_part1_course.py`
- `scripts/agent_scripts/comp_part2_judge.py`
- `scripts/agent_scripts/make_part2_levels.py`
- `scripts/agent_scripts/run_part2_judged_eval.py`
- `scripts/agent_scripts/comp_import_diagnostic.py`
- `scripts/agent_scripts/comp_import_part2_diag.py`
- `scripts/agent_scripts/comp_import_course_diag.py`
- `scripts/agent_scripts/comp_score.py`
- `assets/terrain/part1/part1_eval_scene_v2.xml`
- `config/part1-route.json`、`config/part2-levels.json`
- `comp/eval/flat-ft-2500-part1-diag-v2/`、`comp/eval/flat-ft-2500-part2-diag-v2/`、
  `comp/eval/flat-ft-2500-part1-course-diag/`（manifest/summary/trials）
- `comp/SCOREBOARD.md`

## 复审要求

1. 逐条核对第一次预审的 11 个 blocker：是否真的修复？给出 PASS/STILL-BROKEN 及代码依据（行号/函数）。
   特别验证：
   - 地面 1/2 足判据是否只在"全足支撑过障碍"后生效、进场缓冲是否仍会误杀；
   - 高墙是否真的要求墙平面穿越+抬升、地面绕行/侧走是否仍可成功；
   - 桥面/T 台阶真实 geom tag 是否完整、合法通过是否一定拿到证据；
   - T 台阶三臂/逐级/部分分与"success/返回奖励"是否解耦正确；
   - 限高杆是否要求门洞内连续穿越、掉杆是否全程检测；
   - 绕杆双向、拐角时机、终点点最后、半径是否一致；
   - 失败后同 attempt 内重试、成功后锁定、返回奖励"全满分之后"；
   - Part2 低难度是否仍可用站地面/绕行成功；
   - 正式整场协议（连续 8 障碍、3 次、恢复不消耗、最快时长、best score）是否真的由 runner/importer 实现且证据链自洽。
2. **新的漏洞**：修复是否引入新的假成功/误伤？特别是 supported 门控、soft-reset、失败重试、恢复位姿校验、
   相邻 zone 重叠、共享平台 tag、逆序绕杆的侧向判定。
3. **证据链**：重新生成的三份 diagnostic 产物是否与当前代码/场景 hash 一致、summary 是否可由 trials 复算、
   诊断是否仍被如实标 diagnostic、`comp_score.py` 强校验是否覆盖部分分/floor/返回奖励。
4. **conformance 质量**：13 组测试是否覆盖本轮修复点、有没有"测试自身错误导致通过"的地方。
5. **残余风险**：列出仍会阻塞 G1 的问题（若有），以及可以接受但必须在 G1 报告里写明的风险。

## 输出格式

- verdict：`PASS` / `CONCERN` / `FAIL`（预审建议）。
- 表格：第一次预审 blocker 编号 → PASS/STILL-BROKEN → 代码依据。
- 新问题清单（严重度/文件/函数/利用路径/建议）。
- 给 Codex G1 终审的"必须重点验证项"。
- 中文；引用行号/函数名；不要写补丁代码。
