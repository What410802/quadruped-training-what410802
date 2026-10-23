# G1 复验前自检（第 0 步）

日期：2026-10-23；执行者：executor（DeepSeek agent）；规则：自检通过且自己找不出问题后才送 flash→pro→GLM。

## 命令与结果（在 MyMonoRepo.d 下，pixi 环境）

```text
$ pixi run python @20261019_locomotion/scripts/agent_scripts/comp_judge_conformance.py
timeout finalize: OK
scene geom tags: OK (33 named geoms checked, ground classifier OK)
comp_part1_judge V2.1 conformance: OK (13 groups)

$ pixi run python @20261019_locomotion/scripts/agent_scripts/check_part1_scene_v2.py
beam z: start=0.3250 after 5s=0.3250 drop=0.0000 m
scene v2 check: OK (28 geoms, beam stable)

$ python3 @20261019_locomotion/scripts/agent_scripts/comp_score.py --self-test
comp_score.py self-test: OK

$ python3 @20261019_locomotion/scripts/agent_scripts/comp_import_selftest.py
comp_import_selftest: OK

$ python3 @20261019_locomotion/scripts/agent_scripts/comp_part1_course.py
comp_part1_course self-test: OK {"max_attempts": 3, "recovery_consumes_attempt": false, "final_score": "best_attempt", "final_time": "min_duration_among_best_score_attempts"}

$ python3 @20261019_locomotion/scripts/agent_scripts/comp_part2_judge.py
comp_part2_judge self-test: OK

$ python3 @20261019_locomotion/scripts/agent_scripts/comp_audit_hashes.py --verdict pending
wrote comp/audits/HASHES.json (76 objects)

$ pixi run python @20261019_locomotion/scripts/agent_scripts/comp_score.py --contract @20261019_locomotion/comp/CONTRACT.json --eval @20261019_locomotion/comp/eval --task-root @20261019_locomotion --out @20261019_locomotion/comp/SCOREBOARD.md --json-out @20261019_locomotion/comp/SCOREBOARD.json
scoreboard written: @20261019_locomotion/comp/SCOREBOARD.md (+ @20261019_locomotion/comp/SCOREBOARD.json)
      ~ part1.attempts_used=8 超预算 3（diagnostic 行不据此判 invalid）
      ~ part1.attempts_used=8 超预算 3（diagnostic 行不据此判 invalid）
      ~ part1.attempts_used=8 超预算 3（diagnostic 行不据此判 invalid）
      ~ part1.attempts_used=8 超预算 3（diagnostic 行不据此判 invalid）

$ pixi run python @20261019_locomotion/scripts/agent_scripts/check_calibration.py
{"records": 92, "labeled": 92, "compared": 92, "agree": 92, "agreement": 1.0}
report -> @20261019_locomotion/comp/audits/C1_CALIBRATION_REPORT.md
C1 CALIBRATION: PASS

```

## 结论

- 上述可执行项全部通过；无已知 scorer blocker、无未解释的失败项。
- 已知残余（G1 必写）：砂砾坑真实坑体/碎木几何未 recut；Part2 官方能力场未逐档核对；限高杆 under-bar 检查用 base z 代理（全身离地间隙留 C1）；T 台阶/沟壑等保守边界；正式手动 3 次整场演练视频未补；真实成功 rollout 缺失（策略全失败）。
- 因此进入第 1 步：deepseek flash 独立复验；PASS 后 pro，再 PASS 后 GLM（Codex 不调用）。

## 2026-10-23 19:25 第 22 轮 flash CONCERN 后的自检补充

- 已修：单障碍 gravel 诊断起点/路线改为合法 L 形（`SPECIAL_ROUTES`：西 1 m 短边进→左转→北 1 m 短边出），
  `config/part1-route.json` 同步，C1 records 的 gravel rollout 带 `route` 字段。
- 已修：`comp/eval/_calibration/README_C1.md` 砂砾坑 success/fail 描述与当前 L 形一致。
- 已修：`comp/CONTRACT.md` §6 资产清单移除 V1 judge 旧条目，改为 V2.1/Part2 V2 并指向 HASHES。
- 已修：`comp/eval/_protocol.md` §4.1 诊断表 gravel/slope 行与 v2 runner 一致。
- 已重生成：四份产物、三份演练、C1 92 条记录/视频/索引、HASHES(76)；`check_calibration.py` 仍 PASS 92/92。
- 自检结论：上述 CONCERN 项已关闭；未发现新的 scorer blocker。


## 2026-10-23 19:45 第 33 轮 flash CONCERN 后的自检补充

- 已修：`run_part1_course.py` pause/resume 后继续完成当前 policy step 的剩余 physics substeps（不再跳过），保持 4 substep/policy step 时序。
- 已修：slalom 终点圆与最后一根杆重叠的假成功风险——success 额外要求离开最后一根杆半径（`last_post_cleared`），conformance 增加"停在最后一根杆圈内"反例。
- 已修：`labels_template.csv` gravel 备注改为 L 形合法路径；G1_SELFCHECK 的 HASHES 数量统一为当前 76；C1 报告纳入 HASHES objects。
- 已重生成：四份产物、三份演练、C1 记录/视频/索引、HASHES；`check_calibration.py` 仍 PASS 92/92。
- 自检结论：V33 的 CONCERN 项已关闭；未发现新的 scorer blocker。

## 2026-10-23 20:00 第 34 轮 flash CONCERN 后的自检补充

- 已修：单障碍诊断起点全部移出 judge zone（high_wall y=−8.0、bridge_blocks x=0.8、bridge_bands y=−4.2、slope y=−6.9），
  避免未来真实成功 rollout 被 `illegal_entry_side` 误杀；协议 §4.1 同步。
- 已修：gravel 单障碍改为**闭环 waypoint 导航**（目标 (4.6,−12.5)→(5.8,−12.5)→(5.8,−10.6)，只用 base 位姿生成速度指令），
  不再用开环定时转向；结果记录 `waypoints_reached`。
- 已修：`CONTRACT.md` §1/Q1 的"恢复消耗"文案与 §4/用户确认口径统一（恢复不消耗）；§6 删除不存在的 judge_zones 文件条目。
- 已修：`STATUS.md` 全面重写（原内容仍写 G1 FAIL/Part2 evaluator 缺失/calibration 为空，与现状矛盾）。
- 已修：`G1_SELFCHECK.md` 内部 HASHES 数量统一为 76；C1 报告已纳入 HASHES objects。
- 已重生成：四份产物、三份演练、C1 92 条记录/视频/索引；`check_calibration.py` PASS 92/92。
- 自检结论：V34 的 CONCERN 项已关闭；未发现新的 scorer blocker。
