# 比赛工作流状态

> 只记：当前阶段、下一步、阻塞、最近一次审计结论。进展事实在 `../docs/status.md`，本文件只服务工作流门禁。
> 更新时机：阶段切换、门禁结论变化、出现阻塞。最后更新：2026-10-23。

## 0. 当前

- **stage**：**C1 完成（PASS）**；G1 评测器复验进行中（BYOK flash→pro→GLM；Codex 未调用）。
- **deadline**：2026-11-04 晚。
- **next**：G1 reviewer 链 PASS 后冻结 judge → C2 基线评测 + 参考轨迹策略训练（先本地躯干可视化，用户确认后开训）。
- **blockers**：无已确认 scorer blocker。G1 残余：砂砾坑真实坑体/碎木未 recut；Part2 官方能力场未逐档核对；
  限高杆 under-bar 用 base z 代理；真实成功 rollout 缺失（本地策略全失败）；正式手动 3 次整场演练视频未补；
  course runner 为脚本化诊断链路；slalom 终点圆与最后一根杆在场景显示上重叠（judge 已要求离开最后一杆半径后才算终点）。

## 1. 门禁状态

| 门禁 | 状态 | 说明 |
|---|---|---|
| G0 规则契约 | **PASS** | Q1–Q6 已由用户确认并写入 `CONTRACT.*`（Q1 恢复不消耗、Q2 ×2/3、Q4 砂砾短边/斜坡合计 1 m） |
| G1 评测器可信 | **IN PROGRESS（BYOK）** | judge V2.1 + 场景 v2 + course/Part2 evaluator；C1 人工标定 PASS；BYOK flash/pro/GLM 复验进行中，Codex 待用户批准 |
| G2 基线可复现 | pending | 待正式协议评测（当前只有 diagnostic 产物） |
| G3 单轮评测有效 | pending | 诊断行为 `diagnostic`，不计正式分 |
| G4 里程碑审计 | pending | — |
| G5 冻结 | pending | G1 PASS 后冻结 |

## 2. 当前评测产物

| policy_id | 性质 | 分数 | 备注 |
|---|---|---:|---|
| `flat-ft-2500-part1-diag-v2` | diagnostic | 0 | 8 障碍逐项，V2.1 judge；不可用于对外分数 |
| `flat-ft-2500-part2-diag-v2` | diagnostic | 0 | 20 个参数化 level |
| `flat-ft-2500-part2-official-diag` | diagnostic | 0 | 6 类 × 4 次 official-style |
| `flat-ft-2500-part1-course-diag` | diagnostic | 0 | 3 attempts 整场协议链路 |
| V1 旧产物（`-diag-v1`） | diagnostic | 0 | 仅存档，已被 v2 取代 |

`SCOREBOARD.md` 由 `comp_score.py` 生成；诊断行不得用于选型或对外引用。

## 3. 最近审计

- 2026-10-23：**C1 人工标定 PASS**（92/92 标签、一致率 100%；56 条真实 rollout 为用户盲标，rulecard/session 为语义确认，见 `eval/_calibration/LABELS_PROVENANCE.md`）。
- C1 发现并修复 2 个 judge 语义错误：砂砾坑 L 形短边（原 ymin/ymax 假成功）、限高杆未校验"从下方通过"；
  另修复 slalom 终点与最后一杆重叠的潜在假成功、course pause/resume 跳 substep、诊断起点在 zone 内等。
- 2026-10-23：GLM-5.3 第 31 轮曾判 PASS；上述语义修复后重新走 BYOK 复验（V32–V34 flash 均为 CONCERN：
  无 scorer blocker，但文档/诊断起点/证据链问题已逐项关闭；当前复验进行中）。
- Codex 仍不可用/未调用；恢复后仍需用户二次确认才调用。

## 4. P0 进度

| P0 项 | 状态 | 产物 |
|---|---|---|
| Part 1 V2.1 judge（合法进入/跨越证据/离开、三臂 T 台阶、限高杆 under-bar、双向绕杆、失败可重试、返回奖励） | 已实现 + 13 组 conformance | `scripts/agent_scripts/comp_part1_judge.py`、`comp_judge_conformance.py` |
| AttemptManager（3 次、恢复不消耗、账本、best/fastest） | 已实现 | `comp_part1_course.py` + `run_part1_course.py` |
| 场景 v2（可掉落横杆 + 命名台阶/平台/坡面） | 已实现 | `assets/terrain/part1/part1_eval_scene_v2.xml` |
| Part 2 evaluator（六类、参数化 level、4 attempts official） | 已实现 | `comp_part2_judge.py`、`run_part2_judged_eval.py` |
| 评测产物导入/计分/证据链校验 | 已实现 | `comp_import_*.py`、`comp_score.py` |
| C1 人工标定包 | **PASS** | `eval/_calibration/`（92 条记录 + 56 视频 + 28 rulecards） |
| G1 BYOK 复验 | 进行中 | `audits/BYOK_JUDGE_V3*_ACCEPT.*`、`G1_SELFCHECK.md` |

## 5. 下一步

1. 完成 G1 BYOK 复验（flash→pro→GLM）并记录 verdict；Codex 恢复后按用户确认补最终 acquittal。
2. G1 PASS 后冻结 judge（HASHES `audited=true`），进入 C2 基线评测。
3. 参考轨迹策略训练：先本地生成"仅躯干"ghost 可视化供用户检查，再定 reward/容差并训练。
