# 比赛工作流状态

> 只记：当前阶段、下一步、阻塞、最近一次审计结论。进展事实在 `../docs/status.md`，本文件只服务工作流门禁。
> 更新时机：阶段切换、门禁结论变化、出现阻塞。最后更新：2026-10-24。

## 0. 当前

- **stage**：**C1 完成（PASS）**；G1 评测器仍**未冻结**（用户决策 A）；**C2 训练线重开（2026-10-24）**：Warp 710 已修（见 `../docs/training/training-health.md` §7），视觉主线的 depth task 已进训练仓，blind baseline `best.pt` 已 zero-shot 评测。
- **deadline**：2026-11-04 晚。
- **2026-10-24 主栈决策**：手动/演示主栈迁移到 **rl_sar**（控制层复用，`quadruped_control` 降为备选）；场景适配脚本已落地并本机验证，深度相机后续也走 rl_sar 线。见 `../docs/reference/rl-sar-migration-plan.md`。
- **next**：① **视觉主线 blind vs depth 已续训到 1500 iter**：depth 仍全面略好（reward +10%/episode +3%/terrain +9%/非法接触 −16%）但 500 iter 时的优势大幅缩小、成本 ×1.56，blind 算力效率更高（`../docs/training/camera-depth.md` §7.1/§10）；下一步建议 depth 跑 3000–5000 iter 或做分辨率/latent 消融后再定是否值得部署（3000 长训已启动；warm-start from blind 已实现并 smoke 通过、排队跑，见 `../docs/training/camera-depth.md` §11/§12），DR 放到地形课程稳定后（§9）；`best.pt` 已可进演示 GUI（quadruped_control 路径，`../docs/training/deploy-him-best.md`）；② **主栈迁移 rl_sar**：评估+场景适配已验证（`../docs/reference/rl-sar-migration-plan.md`），下一步起跑位姿/演示脚本/策略切换扩展；③ P1 数字虽已稳，但质量 gate 未过，需要课程/奖励评估而不是盲目续训；④ G1 待训练出真实成功 rollout 后补 PASS/冻结。
  **2026-10-24 方法论修订**：简单地形 3000/warm-start 只作筛选；最终 blind vs depth 裁决改为竞争地形代理（绕柱/桥/限高杆/高墙/砂砾/梅花桩）+ mirror 0.1 对称约束 + 真实 Part1/Part2 judge 的一次性对比（winner 即最终策略，depth 用 warm-start 增量），见 `../docs/training/competition-terrain-and-symmetry-plan.md`；方法论弹药库（已用/未启用/需引入、时间奖励分析）见 `../docs/training/methodology-inventory.md`。
  3000-iter 筛选 + warm-start 臂已于 2026-10-24 15:54 结束（flag=0、远程机空闲）：depth@3000 仍略好于 blind（×1.59 成本），warm-start@3000等效≈blind、低于 depth-from-scratch；仅作简单地形筛选。
- **blockers**：无已确认 scorer blocker。G1 残余同前（砂砾坑真实坑体/碎木未 recut；Part2 官方能力场未逐档核对；限高杆 under-bar 用 base z 代理；真实成功 rollout 缺失；正式手动 3 次整场演练视频未补；course runner 为脚本化诊断链路；slalom 终点与最后一杆显示重叠）。
  **新增观察（不阻塞）**：Part2 `high_wall` 的 `max_z ≥ max(wall_h+0.1, 0.55)` 对“跨过而非爬上墙”的通过方式偏保守（`best.pt` 10 cm 档实测越墙仍判失败）；是否改判属 G1/协议范围，需审计后再动。

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

- 2026-10-24：**训练数值稳定性插桩审计（executor 侧，非 Type-B）**：Warp 710 根因定位为动作反馈自激（`training-health.md` §7）；修复后 200 iter smoke 无 CUDA/NaN。**这不是 G1 审计**，judge/评测器未变。
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
| G1 BYOK 复验 | 暂停（用户决策 A，G1 暂不冻结） | `audits/BYOK_JUDGE_V3*_ACCEPT.*`、`G1_SELFCHECK.md` |
| C2 blind baseline（`best.pt` zero-shot） | 诊断完成 | `prep.d/results/him_best_part{1,2}_v2[_extended].json`；结论见 `../docs/training/him-best-zero-shot.md` |
| C2 训练数值稳定性（Warp 710） | **已修（200 iter smoke）** | 远程训练仓 `utils/anomaly_probe.py`、`terminations.bad_sim_state`；`../docs/training/training-health.md` §7 |
| C2 深度相机 task + 成本 smoke | 管线跑通；成本 smoke（25 iter × 4 配置）与 100-iter 稳定性 smoke 见 `../docs/training/camera-depth.md` §5 | 远程训练仓 `camera_depth.py`、`black-basic-obstacle-depth`；`../docs/training/camera-depth.md` |

## 5. 下一步

1. 完成 G1 BYOK 复验（flash→pro→GLM）并记录 verdict；Codex 恢复后按用户确认补最终 acquittal。
2. G1 PASS 后冻结 judge（HASHES `audited=true`），进入 C2 基线评测。
3. 参考轨迹策略训练：先本地生成"仅躯干"ghost 可视化供用户检查，再定 reward/容差并训练。
