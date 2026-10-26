verdict：**FAIL**

## 1. 第 12 轮 blocker 逐项

### 1.1 高墙外侧抬高穿越：已关闭
- `comp_part1_judge.py` 的 `HighWall` 已固定 `WALL_X_MIN=1.30 / WALL_X_MAX=2.30`，穿越样本要求 `prev_x` 与当前 `x` 均在墙段内，且 `base z>=0.60` 才算 `cross_valid`。
- 墙段外抬高只记 `outside_x_cross`，不会成功。
- `comp_judge_conformance.test_high_wall_sideways_climb_and_bypass` 中 `outside_x` 用 `x=2.33`：该点位于 `ZONES["high_wall"]` x 区间 `(1.25, 2.35)` 内、墙段 `[1.30,2.30]` 外，会真正进入 `HighWall._on_sample` 并触发 `outside_x_cross`，最终非 success。**此项通过。**

### 1.2 T 台阶 s=50 / n/e=33：判分逻辑已修，但 n 臂 conformance 用例实际会失败，blocker 未完全关闭
- `TStairs.__init__` 默认值已是 `partial_up=50.0 / partial_down=33.0`，docstring 已更新；`Part1JudgeV2` 传入也一致。
- `_score_for` 对仅 `s` 臂完整给 50，对 `n` / `e` 臂完整给 33，逻辑正确。
- 但 `comp_judge_conformance.test_t_stairs_full_partial_and_history` 中“n 臂 only”的序列有问题：
  - 序列在 `step:top` 之后继续走了 `step:s:3`、`step:s:2`、`step:s:1`，导致 `arms["s"] = {1,2,3}`。
  - 这会令 `_complete_arms()` 返回 `["n","s"]` 两个完整臂。
  - 因此 `_score_for()` 返回 100，而测试断言 `score == 33.0`。
  - **该 conformance 用例静态可判定会失败**，即 `comp_judge_conformance.py` 当前套件不能通过。
- 结论：T 台阶代码本身按当前口径正确，但“n 臂单臂=33”没有被有效测试；e 臂用例是有效的，n 臂仍未有效覆盖。第 12 轮 blocker 的“n/e 未测”只修了一半。

### 1.3 HASHES 覆盖 Part2 ability field / plum 场景：已关闭
- `comp_audit_hashes.py` 的 `main()` 已额外写入：
  - `assets/terrain/part2/ability_field/part2_ability_field.xml`
  - `assets/terrain/part2/part2_plum_eval_scene.xml`
- `HASHES.json` 中已存在 `scene_part2_ability_field` 与 `scene_part2_plum_eval_scene` 两项。**此项通过。**

### 1.4 comp_score 的 Part1 attempts / final_time 正式校验：主链路已补，但仍有正式链路缺口
- `validate_external_evidence` 已接入 `score_one`。
- 已从 trials 按 attempt 复算 `final_score / final_time_s`，并检查 `part1.attempts_used` 与 trials 中 distinct attempt 数是否一致（formal 下为 error）。
- 也增加了“复算 best/final_time 的 attempt 必须覆盖全部 Part1 障碍”的 full 检查。
- 但存在两个正式链路边界问题：
  1. `validate_external_evidence` 复算 `final_time_s` 时，**未排除 `skipped` trial**。  
     `comp_import_course_diag.py` 对 skipped attempt 的 trial 写 `duration_s=0`，若未来正式产物同时包含 skipped attempt 与得分相同的非 skipped attempt，`min(best_durations)` 可能错误地取 0，导致合法 `final_time_s` 被误判为失败。
  2. `part1.attempts_used` distinct attempt 对账依赖 trials 中存在非 `return_to_start` 的 Part1 trial；若正式产物 `attempts_used > 0` 但 trials 为空且 summary 未声明 `final_time_s`，仍可能绕过此对账。
- 当前四份诊断产物均未触发上述边界，因此现有证据不报错；但“正式校验完整成立”还不能下结论。

## 2. 独立复核历史 PASS 项 / 证据链

### 2.1 四份 eval 产物 summary 可由 trials 复算
- `flat-ft-2500-part1-diag-v2`：8 条 trials 全 fail，score=0；summary `attempts_used=8` 与 distinct attempt 数一致；总分 0 可复算。
- `flat-ft-2500-part2-diag-v2`：20 条 trials，`attempts_used` 分别为 4/4/4/4/3/1，与 summary 一致；全部 fail，总分 0。
- `flat-ft-2500-part2-official-diag`：24 条 trials，每 category 4 条；trench 重复最高档 30cm，但 trial_id 使用 `entry_seq` 区分；全部 fail，总分 0。
- `flat-ft-2500-part1-course-diag`：3 attempts × 8 obstacles = 24 条 trials，`attempts_used=3`；全部 fail，score=0；`final_time_s=94.18` 与 trials duration 可复算。
- 结论：当前四个诊断产物的 summary 可被 trials 复算，没有发现 summary 虚报成功或分数。

### 2.2 HASHES / 重复 trial_id / Part2 合法档位
- HASHES 已覆盖新增两个 Part2 场景。
- 未发现重复 `trial_id`；Part2 official 重复最高档时使用 `attempt_index` + `trial_seq`，唯一。
- Part2 合法档位校验代码存在：`validate_external_evidence` 对 `best_success_value` 必须落在契约 `score_curve` 的 value 集合中，bool 只允许 1。当前产物无成功档位，未被触发，但机制可运行。

## 3. 误伤 / 假成功结论

- 当前四份产物没有可被利用的假成功：所有分数都是 0，没有 success 被错误声明。
- 但 T 台阶 n 臂 conformance 用例会导致测试套件失败，这属于**验证链断裂**，不是运行时判分假成功。
- `comp_score` 的 `final_time_s` 复算未排除 skipped trial，是**潜在误伤合法正式证据**；当前诊断产物未触发。

## 4. 是否同意“flash 与 pro 两轮均无问题”并申请 Codex G1 终审

**no。**

最小修复：
1. 修正 `comp_judge_conformance.test_t_stairs_full_partial_and_history` 中 n 臂 only 用例，避免同时踩完整 s 臂（例如从 top 直接向无 s:1 的方向离开，或只踩部分 s 级后出区），确保实际只完整覆盖 n 臂，断言 33。
2. 重跑 `comp_judge_conformance.py` 并确认全部通过。
3. `comp_score.validate_external_evidence` 的 `final_time_s` 复算应排除 `skipped` trial；formal 下 `attempts_used > 0` 时强制 trials 至少存在可复算 attempt。
4. 重跑 `comp_score --self-test`，刷新 `HASHES.json`，再做一次 flash/pro 复验。

## Codex 若修复后必查项（建议 3–5 项）
1. `comp_judge_conformance.py` n/e 臂单臂 33 是否真的只覆盖单一臂，且完整通过。
2. `comp_score.validate_external_evidence` 对 skipped trial、空 trials、完整障碍覆盖、返回奖励的 formal 校验是否无误伤。
3. HighWall `WALL_X_MIN/MAX` 与实际场地几何的边界一致性，以及 `z>=0.60` 是否会对合法低姿态越墙误伤。
4. 四份产物 + 三份演练证据在修复后是否重新生成，且 HASHES 与新内容一致。
5. T 台阶 partial→full 升级、失败重试、返回奖励只认满分的状态机在 course runner 中是否有回归。

## G1 必写残余
- 砂砾坑真实几何仍未 recut，当前仍为凸起盒代理。
- Part2 官方能力场逐档交叉核对未完成，本地为同种类参数化 level。
- 正式手动 / 操作手 3 次真实赛程演练未完成；当前为脚本化诊断与演练。
- soft-reset 阈值与相邻 zone 重叠仍是启发式。
- T 台阶“上/下 ↔ s/n/e”书面映射仍建议最终书面确认。
- Part2 稳定性 ≥100 次、目标 0 失败未执行；official 重复最高档统计意义有限。
- 跨 attempt 模拟器时间重置导致全局事件时间线无法排序。
- `comp/eval/_calibration/` 人工标定集仍为空。
- 协议仍为 draft，未冻结正式 `protocol_version`。
