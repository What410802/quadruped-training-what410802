<!-- BYOK 后端审计（provisional） -->
# BYOK Contract Review（DeepSeek v4-pro，同家族 → provisional）

> **后端**：`comp_review.py` / OpenAI 兼容 relay / `deepseek-v4-pro`
> **独立性**：executor=deepseek-v4.1-flash、reviewer=deepseek-v4-pro → **same-family-provisional**
> （可驱动改进，不能单独作为 G1/G4 的 acquittal；G1/红队仍需 1 次 Codex 不同家族评审）
> **prompt**：`comp/audits/prompts/contract-review-prompt.md`；**meta**：`BYOK_CONTRACT_REVIEW.json`
> **内容**：reviewer 原始输出如下（executor 未改写），overall=WARN，13 条问题 + 6 条待人工确认。

overall: **WARN**

本次为只读审计，未修改任何文件。以 `docs/reference/team-race-2026.md` 为规则真值，对照 `comp/CONTRACT.md`、`comp/CONTRACT.json`、`comp/eval/_protocol.md`。主要口径大多已落地，但协议草案仍有结构性缺口，且存在 1 个稳定性计算矛盾、若干加分/约束字段未机读化或措辞不一致。

---

## 问题清单

| # | 文件:行/段落 | 问题 | 最小修复 |
|---|---|---|---|
| 1 | `comp/eval/_protocol.md:§4/§5`（TASKS 表） | Part 1 协议仍按“每障碍独立 TASKS/单独起点”组织，而规则是“整场 3 次尝试、跨越全部障碍并返回启动区”。当前协议无法表达完整赛程、跳过扣分、返回奖励、单次 attempt 的连续失败/恢复。 | 将“诊断用单障碍 rollout”和“正式 Part 1 整场赛程”分离；正式协议必须定义完整赛程顺序、起点/goal、各障碍 checkpoint、返回启动区判罚、attempt 账本如何随整场 attempt 递增。 |
| 2 | `comp/CONTRACT.json:parts.part2.stability.definition`；`comp/eval/_protocol.md:§6.1` | `<1%（≥100 次尝试）` 与“即 0 次失败才达标”不等价。101 次尝试中失败 1 次约 0.99% `< 1%`，仍达标；只有恰好 100 次时 1 次失败才是 1% 不达标。 | 机读定义改为 `fail_count / attempts < 0.01`；或明确 “attempts=100 时 0 失败；>100 时按比例判定”；若主板方真实意图是“0 失败”，应写 `failure_ratio_max = 0`。 |
| 3 | `comp/eval/_protocol.md:§2/§5` | 协议草案未重复 Part 2 红线：仅允许 RL、不能写固定动作；未写力矩上限（大腿/髋 ≤25 N·m，小腿 ≤60 N·m）。 | 在 §2 或 §5 增加“规则红线”块：Part 2 RL-only、无固定动作；力矩限制与 `CONTRACT.json:constraints.torque_limits_nm` 一致。 |
| 4 | `comp/eval/_protocol.md:§4/§5` | 协议未定义“返回启动区 +100”任务及其前置条件；也未落地 Q6：Part 1 全部按手动遥控计分、自动/固定动作无额外分、计时口径不变；未写 Part 1 同分用时排序。 | 增加 return-to-start 任务/判罚；增加 Part 1 计分口径：手动遥控计分、自动无额外分；增加排序：Part 1 得分相同按用时升序。 |
| 5 | `comp/CONTRACT.json:scoring.parts.part1` | JSON 缺少 Part 1 同分用时排序字段；`CONTRACT.md:§4` 已写“同分排序：用时（Part 1）”，机读契约未覆盖。 | 在 `parts.part1` 或 `scoring` 增加 `"tiebreak": {"part1": "time_asc"}`。 |
| 6 | `comp/CONTRACT.json:parts.part1.obstacles[*].fail_conditions` 中 `feet_on_ground>=2`；`comp/CONTRACT.md:§2` 表 | “任何瞬间 ≥2 足触地即失败”仅在 `_protocol.md:§6.2` 和 CONTRACT.md 歧义清单 Q3 出现；Part 1 机读障碍 `fail_conditions` 没有 `any_instant`/零去抖语义，机器消费方可能误解为持续接触才失败。 | 在 JSON schema 增补 `"feet_on_ground_semantics": "any_instant_ge_2"`；CONTRACT.md 表下加脚注“≥2 足触地按任何瞬间计”。 |
| 7 | `comp/CONTRACT.md:§1`（“返回启动区 100”） | 未写出返回奖励的前置条件；规则原文为“越过全部障碍并回到启动区额外 100 分”。JSON 已有 `requires: all_obstacles_success`，但人读契约没有写清。 | 改为“越过全部障碍并回到启动区额外 +100”。 |
| 8 | `comp/CONTRACT.md:§2 height_bar`；`comp/CONTRACT.json:parts.part1.obstacles.height_bar.success_criteria` | 两份契约都加了“垂直于门平面穿过”，但 `team-race-2026.md` 只写“任何运动姿态从限高杆下方穿过”，未出现“垂直于门平面”。若 PDF 原文没有，这是新增限制。 | 删除“垂直于门平面”；或由主办方书面确认后补入 `team-race-2026.md` 真值。 |
| 9 | `comp/CONTRACT.json:parts.part1.obstacles.gravel_pit.success_criteria`；`slope.success_criteria` | gravel 写成“从 1 m 短边进入/离开”，虽有 `entry_exit_required: both_legal_short_edges`，但文本本身有歧义；slope 的 `success_criteria` 未写“两侧合计”，只靠 `distance_scope` 补救。 | gravel 文本改为“从 1 m 短边进入且从 1 m 短边离开”；slope 文本改为“两侧合计沿 3 m 长边方向累计行走 ≥ 1 m”。 |
| 10 | `comp/CONTRACT.json:constraints.sensors_allowed` | JSON 允许 `"lidar"`，但 `CONTRACT.md` 与规则真值写的是“雷达”。LiDAR 通常指激光雷达，与“雷达”不一定等价。 | 对齐为 `"radar"`，或若主办方口径就是“激光雷达”，显式写 `"lidar"` 并更新真值文档。 |
| 11 | `comp/eval/_protocol.md:§3` | “汇总报均值/最差，不报‘最好一次’”可能被理解为正式计分规则，与 Part 2 “取最高成功难度”矛盾。 | 限定该句仅用于“跨 seed 复现性/稳定性报告”；正式计分仍按 Part 2 每障碍 4 次取最高难度、Part 1 按成功/失败与返回计分。 |
| 12 | `comp/eval/_protocol.md:§5` | 协议未列出 Part 2 各项得分曲线/满分（高台、楼梯、斜坡一、高墙、沟壑、梅花桩共 1300），仅写了部分 Q5 端点与舍去规则；已知缺口也承认 Part 2 evaluator 未定义。 | 协议显式引用 `CONTRACT.json:parts.part2.obstacles[*].score_curve` 或复制曲线；冻结前必须补齐 Part 2 难度档位和 evaluator。 |
| 13 | `comp/CONTRACT.json:parts.part2.obstacles[*]` | 对高台/楼梯/斜坡一等，规则写“阈值以下不得分”，JSON 只有正分点，没有显式 `below_min_points: 0`；不如高墙/沟壑的 0 分端点明确。 | 给每项 Part 2 曲线增补 `"below_min_points": 0` 或 `"no_score_below_min": true`。 |

---

## 需要人工最终确认的点

1. **Q1 的“摔倒恢复消耗一次尝试”**：规则原文写“摔倒后可暂停计时并恢复”，存在“同一次 attempt 内恢复”的解释空间；当前三份文件均按 2026-10-22 口径写成“恢复也消耗次数”。建议书面确认。
2. **Q2 的“仅上 = 75 / 仅下 = 50”对应关系**：`CONTRACT.md`/`CONTRACT.json` 都仍标记“按表顺序，仍需最终书面确认”。应拿到最终书面口径。
3. **限高杆“垂直于门平面”**：两份契约出现该限制，但规则真值文档没有；需确认是否来自 `队内赛.pdf` 原文。
4. **“雷达” vs “lidar”**：需确认允许的传感器是传统雷达、激光雷达，还是两者均可。
5. **稳定性“0 失败”与“<1%”**：需确认正式判定是“严格 0 失败”，还是“失败比例 <1%”。若是后者，1/101 这种情形是否算达标。
6. **`docs/training/competition-judge.md` 未在本次审计材料中**：完整成功/失败语义被契约引用到该文件；本次无法核对 judge 级是否完全落实“任何瞬间 1/2 足触地”等口径。
