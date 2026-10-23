# 评测协议（草稿，待 G1 审计后冻结）

> 版本：`protocol-draft-2026-10-22b`　状态：**draft**（未过 G1，不能作为正式分数依据；2026-10-22 已并入主办方口径 Q1–Q5）
> 目标：固定"怎么跑一次评测"，使同一 policy 在同一协议下的分数可复现、可审计。
> 正式版须由 `/comp-eval` 产出、`/comp-eval-audit` 审计后冻结（`protocol_version` 写进每个 manifest）。

## 1. 场景与 judge 版本

| 项 | 值 |
|---|---|
| Part 1 场景（V2） | `assets/terrain/part1/part1_eval_scene_v2.xml`（可动横杆 + 命名台阶/平台/坡面；sha256 由 manifest 记录） |
| Part 1 judge（V2.1） | `scripts/agent_scripts/comp_part1_judge.py`（成功语义/接触历史/全足支撑后的 1-2 足/落杆/双向绕杆/三臂台阶/失败可重试）+ `comp_part1_geom_tags.py` |
| Part 1 整场协议 | `scripts/agent_scripts/comp_part1_course.py`（3 次尝试/恢复不消耗/跳过/返回奖励/best score+fastest time） |
| Part 1 runner（诊断） | `scripts/agent_scripts/run_part1_judged_rollout_v2.py`（逐物理步接触分类） |
| Part 2 参数化档位 | `config/part2-levels.json` + `assets/terrain/part2/levels/*.xml`（20 档，官方种类不变） |
| Part 2 judge（V2） | `scripts/agent_scripts/comp_part2_judge.py`；runner `run_part2_judged_eval.py` |
| Part 2 官方场（交叉核对） | `assets/terrain/part2/ability_field/part2_ability_field.xml`、`part2_plum_eval_scene.xml` |
| 机器人模型 | 场景内 `black.xml`（与训练契约一致） |

judge 必须在策略回路外；actor 输入遵守传感器红线（IMU+编码器，可选相机/雷达）。

## 2. 机器人/策略契约（与 docs/training/eval-protocol.md §2 一致）

- obs 45（命令 3 + 角速度 3 + 重力投影 3 + 关节位置 12 + 关节速度 12 + 上一动作 12）；
- action 12，`q_target = q_default + 0.25·a`；Kp=40、Kd=1.2；策略 50 Hz（物理 5 ms × decimation 4）；
- 关节顺序 FL→FR→RL→RR（hip/thigh/calf）；`policy.pt` 为 TorchScript。

## 3. 种子

- 正式协议：`seeds = [0, 1, 2]`（策略确定性时用环境扰动种子）；
- 每个 seed 下每个障碍至少 1 次尝试；汇总报均值/最差，不报"最好一次"。

## 4. Part 1 形式：诊断单障碍 vs 正式整场（必须分开）

- **诊断模式**（当前）：每障碍独立起点/命令，只用于暴露环境与 judge 问题；**不代表整场赛程**，也不消耗正式尝试。
- **正式整场模式**（协议类已实现，操作手 runner 待接）：按规则连续跑 8 障碍 + 返回启动区；
  整场 3 次尝试；**恢复不消耗**（暂停计时、原位置原朝向继续），开始/主动重跑消耗；障碍级跳过不消耗尝试；
  同分按用时升序；每次尝试事件追加进尝试账本（禁止覆盖写）。
- 两种模式共用同一 judge 与同一份 `trials.jsonl` schema，但 `protocol.mode` 必须显式区分。
- 判定语义（V2）：合法进入 → 实际跨越/接触历史 → 合法离开；障碍邻接区**擦碰/路过**只做 soft-reset，不永久判失败。

## 4.1 起点、朝向、命令（当前为诊断脚本值，正式协议需复核进入方向/距离是否满足规则）

| 障碍 | 起点 (x,y,z) | yaw | 命令 (vx,vy,wz) | 时长 s | 备注 |
|---|---|---|---|---|---|
| height_bar | (5.7,−10.4,0.55) | π/2 | (0.4,0,0) | 4.0 | 沿 +y 穿门洞 |
| high_wall | (1.8,−7.8,0.55) | π/2 | (0.4,0,0) | 4.0 | 沿 +y 跨墙 |
| bridge_blocks | (1.8,0.0,0.65) | 0 | (0.3,0,0) | 5.0 | 左平台 → +x |
| bridge_bands | (5.7,−3.5,0.65) | π/2 | (0.3,0,0) | 5.0 | 下平台 → +y |
| gravel_pit | (3.6,−12.5,0.55) | 0 | (0.45,0,0) → (0,0,0.75) → (0.45,0,0) | 7.2 | 西 1 m 短边进 → 左转 → 北 1 m 短边出（L 形合法路径） |
| t_stairs | (1.8,−5.2,0.55) | π/2 | (0.4,0,0) | 5.0 | 主肢 → +y |
| slope | (4.6,−6.5,0.55) | π/2 | (0.5,0,0) | 6.0 | 沿 +y（3 m 长边/母线方向）走坡面 |
| slalom | (1.8,−9.25,0.55) | −π/2 | (0.45,0,0) | 4.5 | 第一根杆 → −y |

> 这些值是 `run_part1_judged_rollout_v2.py` 的 `TASKS` + `SPECIAL_ROUTES`（gravel 用脚本化三段路线；诊断用）。
> 正式协议要回答：起点是否在必达区/坑外合法、
> 命令是否允许、是否满足"从短边进入"等规则语义——在 G1 审计中作为"协议诚实性"的一部分被审查。

## 4.2 规则红线（与 CONTRACT.json constraints 同步）

- Part 2 **仅 RL**，禁止固定动作序列/状态机代打；Part 1 允许手动/固定动作但自动无额外分（Q6）。
- 力矩：大腿/髋 ≤25 N·m，小腿 ≤60 N·m。
- 传感器：仅 IMU+编码器（+模拟真实相机；**本队不采用雷达**，优先深度相机）；actor 不得含机身线速度/高程/足底力/足端高度/机身高度。
- 世界坐标/速度真值仅可用于生成速度指令，不得进网络输入。

## 5. 尝试与尝试账本

- Part 1：整场 3 次；**恢复不消耗**（暂停计时、原位置原朝向继续）、开始/主动重跑消耗；障碍级跳过不消耗尝试但该障碍不得分；最终 score 取 3 次中最好一次、最终 time 取最快一次（2026-10-22 更正）；失败原因、跳过、恢复位置都要记录；
- Part 2：每项 4 次，记录最高成功难度，不按次数扣分；分数小数**舍去**；高墙/沟壑 10 cm 端点 0 分（Q5）；稳定性目标 0 失败，无计时压力，优化阶段先按失败比例排序。
- 手动操作必须记录操作手；脚本化评测记录 `operator=scripted:<脚本名>`。

## 5.5 Part 2 计分

- 计分曲线以 `comp/CONTRACT.json` 的 `parts.part2.obstacles[*].score_curve` 为准（高台/楼梯/斜坡/高墙/沟壑/梅花桩，合计 1300）。
- 小数**舍去**（floor）；低于首个计分阈值 0 分；高墙/沟壑 10 cm 端点 0 分（Q5）。
- 最高成功难度从**全部有效尝试的 trials** 重算，不直接信任 summary（`comp_score.py` 会校验）。

## 6. 正式评测的产物

每次评测产出 `comp/eval/<policy_id>/{manifest.json,trials.jsonl,summary.json}`，字段见
比赛工作流包的 `competition/shared-references/eval-artifact-contract.md`。诊断导入（单种子、每障碍一次）
必须在 manifest 标 `protocol.diagnostic=true`，在 `SCOREBOARD` 标 `diagnostic`，不得对外引用。

## 6.1 「反复稳定」的测量口径（Q5）

- 目标：**0 失败**（主办方推荐）；优化阶段按**失败比例**排序。测量：≥100 次独立尝试；不足 100 次标 `preliminary`。
- 每次尝试独立记录 seed/起点/命令；不能用"最好一次"代表稳定通过；
- 稳定性评测单独跑，不混入正式计分尝试（避免消耗 Part 2 的 4 次机会）。

## 6.2 关键判罚口径补充（2026-10-22）

- 1/2 足触地：**任何瞬间** ≥2 足接触"不允许表面/地面"即失败（不做持续时间去抖）。
- 限高杆：只有**横杆掉落**才算失败；碰柱/碰梁但横杆未落不算失败（但仍需从门洞下穿过）。
- 砂砾坑：进入和离开两端都必须是 1 m 短边；斜坡两侧合计走 ≥1 m。
- T 台阶：两侧都过 100；单侧部分分 **Q2 已确认**：上=75×2/3=50、下=50×2/3≈33.33→33（舍去）；
  **返回奖励只认单项满分**，部分分不触发。
- 计分排序：分数最高优先，同分取最快；计时在机器人稳定停下后停止（2026-10-22 确认）。
- 软重置：障碍邻接区擦碰（路过但未真正尝试）→ 状态回 pending，不占失败；真实尝试（有接触历史/停留）才判失败。
- 限高杆掉落阈值：横杆（slide joint）相对初始高度下降 >5 cm 判掉落。

## 7. 复现性要求（正式版）

同一 policy + 同设施 + 同一操作手，两次评测的 success 序列一致；不一致项必须解释
（flaky 本身就是比赛现场风险，须修或列入兜底）。

## 8. 已知缺口（进 G1 前必须补）

1. 人工标定集为空（`eval/_calibration/`）；judge 未与人工标签比对（≥64 条，下一阶段）；
2. Part 2 evaluator 已有参数化 20 档，但未在**官方能力场**上交叉核对（当前只在自定义同种类 level 上验证）；
3. 正式整场 MuJoCo runner（操作手/键盘或控制仓接入）未接；协议类 `comp_part1_course.py` 已实现并自检；
4. 跳过/主动重跑是否消耗尝试、最终分数是否取 best 的**书面确认**仍缺（当前按恢复不消耗、开始/重跑消耗、best score 落地）；
5. T 台阶部分分 Q2 已裁决：×2/3（上=50、下=33），两侧都过=100（2026-10-22 用户确认）；
6. 砂砾坑真实几何未 recut（本地为凸起盒代理）；Part2 官方能力场交叉核对未做；
7. judge 版本以 sha256 记录，语义变更→重审流程目前人工（`audits/HASHES.json`）。
