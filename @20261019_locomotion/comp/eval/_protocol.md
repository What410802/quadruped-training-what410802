# 评测协议（草稿，待 G1 审计后冻结）

> 版本：`protocol-draft-2026-10-22`　状态：**draft**（未过 G1，不能作为正式分数依据）
> 目标：固定"怎么跑一次评测"，使同一 policy 在同一协议下的分数可复现、可审计。
> 正式版须由 `/comp-eval` 产出、`/comp-eval-audit` 审计后冻结（`protocol_version` 写进每个 manifest）。

## 1. 场景与 judge 版本

| 项 | 值 |
|---|---|
| Part 1 场景 | `assets/terrain/part1/part1_eval_scene.xml`，sha256 `e7b654ad1bcf4638…` |
| Part 1 judge zones | `assets/terrain/part1/judge_zones.yaml` |
| judge（事件级） | `scripts/agent_scripts/part1_event_judge.py`，sha256 `546dbacd29465cb6…` |
| judge（接触级） | `scripts/agent_scripts/part1_judge.py`，sha256 `b398a39d25a21542…` |
| Part 2 场景 | `assets/terrain/part2/ability_field/part2_ability_field.xml`、`assets/terrain/part2/part2_plum_eval_scene.xml`（sha256 待补） |
| 机器人模型 | 场景内 `black.xml`（与训练契约一致） |

judge 必须在策略回路外；actor 输入遵守传感器红线（IMU+编码器，可选相机/雷达）。

## 2. 机器人/策略契约（与 docs/training/eval-protocol.md §2 一致）

- obs 45（命令 3 + 角速度 3 + 重力投影 3 + 关节位置 12 + 关节速度 12 + 上一动作 12）；
- action 12，`q_target = q_default + 0.25·a`；Kp=40、Kd=1.2；策略 50 Hz（物理 5 ms × decimation 4）；
- 关节顺序 FL→FR→RL→RR（hip/thigh/calf）；`policy.pt` 为 TorchScript。

## 3. 种子

- 正式协议：`seeds = [0, 1, 2]`（策略确定性时用环境扰动种子）；
- 每个 seed 下每个障碍至少 1 次尝试；汇总报均值/最差，不报"最好一次"。

## 4. 起点、朝向、命令（当前为诊断脚本值，正式协议需复核进入方向/距离是否满足规则）

| 障碍 | 起点 (x,y,z) | yaw | 命令 (vx,vy,wz) | 时长 s | 备注 |
|---|---|---|---|---|---|
| height_bar | (5.7,−10.4,0.55) | π/2 | (0.4,0,0) | 4.0 | 沿 +y 穿门洞 |
| high_wall | (1.8,−7.8,0.55) | π/2 | (0.4,0,0) | 4.0 | 沿 +y 跨墙 |
| bridge_blocks | (1.8,0.0,0.65) | 0 | (0.3,0,0) | 5.0 | 左平台 → +x |
| bridge_bands | (5.7,−3.5,0.65) | π/2 | (0.3,0,0) | 5.0 | 下平台 → +y |
| gravel_pit | (3.5,−12.0,0.55) | 0 | (0.45,0,0) | 6.0 | 从短边外侧进坑（需按规则复核） |
| t_stairs | (1.8,−5.2,0.55) | π/2 | (0.4,0,0) | 5.0 | 主肢 → +y |
| slope | (3.6,−5.5,0.55) | 0 | (0.5,0,0) | 5.0 | 沿 +x 上坡 |
| slalom | (1.8,−9.25,0.55) | −π/2 | (0.45,0,0) | 4.5 | 第一根杆 → −y |

> 这些值是 `run_part1_judged_rollout.py` 的 `TASKS`（诊断用）。正式协议要回答：起点是否在必达区/坑外合法、
> 命令是否允许、是否满足"从短边进入"等规则语义——在 G1 审计中作为"协议诚实性"的一部分被审查。

## 5. 尝试与尝试账本

- Part 1：整场 3 次（**Q1 待确认**）；失败原因、是否跳过、恢复位置都要记录；
- Part 2：每项 4 次，记录最高成功难度，不按次数扣分；
- 手动操作必须记录操作手；脚本化评测记录 `operator=scripted:<脚本名>`。

## 6. 正式评测的产物

每次评测产出 `comp/eval/<policy_id>/{manifest.json,trials.jsonl,summary.json}`，字段见
比赛工作流包的 `competition/shared-references/eval-artifact-contract.md`。诊断导入（单种子、每障碍一次）
必须在 manifest 标 `protocol.diagnostic=true`，在 `SCOREBOARD` 标 `diagnostic`，不得对外引用。

## 7. 复现性要求（正式版）

同一 policy + 同设施 + 同一操作手，两次评测的 success 序列一致；不一致项必须解释
（flaky 本身就是比赛现场风险，须修或列入兜底）。

## 8. 已知缺口（进 G1 前必须补）

1. 人工标定集为空（`eval/_calibration/`）；judge 未与人工标签比对；
2. Part 2 起点/难度档位/evaluator 未定义；
3. 尝试账本尚未由评测脚本自动写（当前诊断导入按一次/障碍）；
4. judge 版本以 sha256 记录，但尚无"语义变更→重审"的自动触发（人工按 `audits/HASHES.json` 检查）。
