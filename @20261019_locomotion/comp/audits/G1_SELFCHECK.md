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
wrote comp/audits/HASHES.json (80 objects)

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
  `config/part1-route.json` 同步，C1 records 的 gravel rollout 带 `waypoints` / `waypoints_reached` 字段（当前策略全 false）。
- 已修：`comp/eval/_calibration/README_C1.md` 砂砾坑 success/fail 描述与当前 L 形一致。
- 已修：`comp/CONTRACT.md` §6 资产清单移除 V1 judge 旧条目，改为 V2.1/Part2 V2 并指向 HASHES。
- 已修：`comp/eval/_protocol.md` §4.1 诊断表 gravel/slope 行与 v2 runner 一致。
- 已重生成：四份产物、三份演练、C1 92 条记录/视频/索引、HASHES(80)；`check_calibration.py` 仍 PASS 92/92。
- 自检结论：上述 CONCERN 项已关闭；未发现新的 scorer blocker。


## 2026-10-23 19:45 第 33 轮 flash CONCERN 后的自检补充

- 已修：`run_part1_course.py` pause/resume 后继续完成当前 policy step 的剩余 physics substeps（不再跳过），保持 4 substep/policy step 时序。
- 已修：slalom 终点圆与最后一根杆重叠的假成功风险——success 额外要求离开最后一根杆半径（`last_post_cleared`），conformance 增加"停在最后一根杆圈内"反例。
- 已修：`labels_template.csv` gravel 备注改为 L 形合法路径；G1_SELFCHECK 的 HASHES 数量统一为当前 80；C1 报告纳入 HASHES objects。
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


## 2026-10-23 20:10 第 35 轮 flash CONCERN 后的自检补充

- 已修：C1 records 的 gravel rollout 现在持久化 `waypoints` / `waypoints_reached`（与视频渲染一致；当前 flat 策略全 false，故只是失败样本）。
- 已修：`README_C1.md` / `G1_SELFCHECK.md` 不再声称真实 rollout 已执行合法 L 路径；成功侧仍明确由 rulecard 覆盖。
- 已确认：course pause 期间物理冻结（暂停循环不推进 physics，只推进 operator 事件时钟），resume 后补完当前 policy step 的剩余 substep。
- 已加入 G1 残余：限高杆要求 entry/exit 对边，穿越后折返同侧是否算通过仍待主办方口径；场景 slalom 终点圆显示重叠（judge 已用 last_post_cleared 防护）。
- 自检结论：V35 的 CONCERN 项已关闭；未发现新的 scorer blocker。

## 2026-10-23 20:15 第 36 轮 flash CONCERN 后的自检补充

- 已修：`check_calibration.py` 现在校验 `human_judge_verdict_correct`（rulecard）与 failure_reason 词表；
  C1 报告会显式列出 judge-verdict 错标/未知 reason。
- 已修：原始盲标 `labels_user_partial_20261023.csv` 与 `check_calibration.py` 纳入 HASHES（77 objects）。
- 已修：course route `cross_slope` 终点移到 zone 外（5.2,−3.8），避免"未真正出 slope zone"。
- V36 reviewer 结论：无 scorer/judge 语义 blocker；剩余 CONCERN 均为已知 G1 残余（真实成功 rollout、正式手动整场、
  base-footprint/base-z 代理、场景显示重叠等），其中"真实成功 rollout"必须先有可用策略。
- 自检结论：无 blocker；继续追 PASS 需要先训练/补正式链路，因此向用户提出下一步选择。

## 2026-10-23 20:25 用户决策 A + 轨迹可视化

- 用户选择 **A**：接受"无 scorer blocker 的 CONCERN"进入轨迹训练；**G1 保持未冻结**（HASHES `audited=false/pending`），
  等训练出真实成功 rollout 后补 C1 真实成功视频、再跑 flash→pro→GLM 拿 PASS/冻结。
- 已生成 trunk-only 参考轨迹可视化：Part1 8 + Part2 6 = 14 个 mp4（`RoboCon/prep.d/videos/trunk_ref/`，不入库），
  plan 在 `comp/eval/trunk_ref_plan.json`，说明 `comp/PLAN_TRUNK_REFERENCE.md`；等用户检查后再定 reward/开训。
- 复验记录：flash V32–V36 均 CONCERN、无 scorer/judge 语义 blocker；pro/GLM 在最终 A 决策下暂缓，待真实成功证据齐备后一并复跑。

## 2026-10-23 22:12 参考轨迹 v5 / 全场顺序调整

- 按用户确认调整 Part1 课程环序：出发区 → high_wall → T 台阶 → slope → bridge_blocks → bridge_bands → height_bar → gravel_pit → slalom(B 短边进) → 出发区；
  `config/part1-route.json` 已更新，course diag/三份演练重生成并重新导入。
- slalom 参考改为短边 B 进：B → post3 → post2 → corner → post1 → post0 → A；重渲 trunk_ref。
- P2 高台/楼梯/斜坡/梅花桩改为 world-only raycast 表面跟随；沟壑平地；位置线性插值（消除 waypoint 停顿）。
- 这些属于 C2 训练参考/诊断链路，不改变 judge 语义；G1 仍按 A 决策未冻结。
