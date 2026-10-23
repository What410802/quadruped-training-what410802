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
wrote comp/audits/HASHES.json (72 objects)

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
