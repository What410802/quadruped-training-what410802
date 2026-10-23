# C1 标签来源与限制（审计用）

日期：2026-10-23

## 谁标了什么

| 部分 | 数量 | 标注人 | 方式 |
|---|---:|---|---|
| `part1_obstacle` / `part2_level` | 56 | 用户 | 盲标（CSV 未显示 judge 结论；用户看视频后填 success/fail/reason） |
| `part1_rulecard` / `part2_rulecard` | 28 | 用户确认语义 + executor 按确认补全 | **非盲标**：用户逐卡检查后确认"除已指出 4 处外均与 judge 相同"；executor 据此把 `human_success` 设为 judge 结论、`human_judge_verdict_correct` 设为 true |
| `session_state` | 8 | 用户确认 + executor 补全 | **非盲标**：用户确认状态表看起来都没问题；executor 填 `human_protocol_ok=true` |

用户原始的部分标注已保存为 `labels_user_partial_20261023.csv`（61 行，含 56 条真实 rollout + 5 条 rulecard）。

## 用户提出并已处理的 4 处 rulecard 疑问

1. `rule_p1_gravel_pit_success`：旧卡是长边直穿的假成功 → judge 改为 L 形短边（西/北 1 m 边）后，success 卡改为合法 L 路径。
2. `rule_p1_height_bar_success`：旧卡 base z 高于 bar_z（不是从下方穿过）→ judge 增加 under-bar 检查，success 卡改为低姿态。
3. `rule_p1_slope_success`：斜坡要求沿 3 m 长边方向累计 ≥1 m，沿母线走 z 近似常数；在卡中补充说明，不要求爬升。
4. `rule_p2_plum`：旧卡路径 y=0 偏离梅花桩区 → 改为 lane_y=0.4（桩区中央）。

## 检查结果

`check_calibration.py`：92/92 条有标签，92/92 参与比较，一致率 100%，`C1 CALIBRATION: PASS`
（报告：`comp/audits/C1_CALIBRATION_REPORT.md`）。

## 限制（必须写入 G1）

- rulecard/session 标签是**语义确认**而非盲标；只有 56 条真实 rollout 是用户的盲标，因此 C1 的"judge-human 100%"主要说明用户确认了规则语义与卡片一致，不构成对 judge 成功路径的独立盲测。
- 真实成功 rollout 仍缺失（本地策略全失败）；成功侧证据目前是 rulecard + judge 实现，等训练出成功策略后必须补真实成功视频重跑 C1。
- rulecard 的 judge 结论在 2026-10-23 因砂砾坑/限高杆修复而改变；修复后由 executor 重新检查一致性，未再请用户逐卡重看（用户已确认修复解释）。
