# 比赛工作流状态

> 只记：当前阶段、下一步、阻塞、最近一次审计结论。进展事实在 `../docs/status.md`，本文件只服务工作流门禁。
> 更新时机：阶段切换、门禁结论变化、出现阻塞。

## 0. 当前

- **stage**：C1（评测器已建诊断导入，**G1 独立审计未做**）
- **deadline**：2026-11-04 晚（截至 2026-10-22 约 12.5 天）
- **next**：G1 judge 审计（Codex ultra，新线程，只给路径）→ 人工标定集 → 正式协议评测 → 基线记分
- **blockers**：
  1. judge 为启发式、未用真实手动轨迹标定；`qa` 与几何方向曾有误判史（见 `docs/reference/agent-visual-checklist.md`）；
  2. 无人工标定集（`eval/_calibration/` 空）；
  3. 现有评测只有**单种子、每障碍一次**的诊断导入（`diagnostic`），不满足正式协议；
  4. P1 `black-basic-obstacle` 未过 slope/stairs gate（见 docs/status）。

## 1. 门禁状态

| 门禁 | 状态 | 说明 |
|---|---|---|
| G0 规则契约 | WARN | `CONTRACT.md/json` 初版；Q1–Q3 歧义 pending（需主办方确认） |
| G1 评测器可信 | **pending** | 未审计；`audits/` 为空 |
| G2 基线可复现 | pending | 待正式协议评测 |
| G3 单轮评测有效 | pending | 诊断导入为 `diagnostic`，不计正式分 |
| G4 里程碑审计 | pending | 尚无里程碑策略 |
| G5 冻结 | pending | — |

## 2. 当前评测产物

| policy_id | 来源 | 性质 | 分数 | 备注 |
|---|---|---|---:|---|
| `flat-ft-2500-part1-diag-v1` | `prep.d/results/part1_zero_shot.json` | diagnostic（单种子/每障碍一次） | 0 | 只作起点记录 |
| `p1-basic-obstacle-part1-diag-v1` | `prep.d/results/part1_p1_basic_obstacle.json` | diagnostic | 0 | 桥/限高杆行为改善但未通过 |
| `p1-cont-part1-diag-v1` | `prep.d/results/part1_p1_cont.json` | diagnostic | 0 | 续训后诊断 |

## 3. 最近审计

- 无。第一次 G1 审计的物料清单见 `../docs/...` 与 比赛工作流包的 `competition/docs/ROBOCON_2026.md` §4。

## 4. 下一步顺序

1. 跑 `/comp-eval-audit` 的 G1（Prompt A）＋盲写第二实现（Prompt B），产出 `audits/JUDGE_AUDIT.{md,json}`；
2. 建人工标定集（≥30 条，覆盖成功/失败/边界），judge 与人工标签一致率 ≥ 目标；
3. 写正式 `eval/_protocol.md`（种子/起点/命令/尝试/操作手/judge 版本），重跑基线；
4. 基线分进 `SCOREBOARD.md`（`valid` 行），再进 C3 训练循环。
