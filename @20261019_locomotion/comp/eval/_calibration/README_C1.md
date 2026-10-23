# C1 人工标定包使用说明（2026-10-23 生成）

## 这是什么

C1 = 评测器标定阶段：用**人工标签**给规则 judge 做 ground truth，检查 judge 是否误判、
并在 judge 语义变更后做回归。不是训练数据，也不会训练学习型 judge（规则 judge 需可复现、可审计）。

本包在现有诊断链路上生成，产物在：

| 文件 | 说明 |
|---|---|
| `records.jsonl` | 92 条记录（含 judge verdict/evidence；**标注时不要先看**，CSV 已隐藏 judge 结论） |
| `labels_template.csv` | 盲标表：填 `human_success` / `human_failure_reason` / `human_protocol_ok` / `human_judge_verdict_correct` |
| `index.html` | 浏览全部记录（视频/SVG 链接 + session 状态表），建议直接用它逐个打开 |
| `../../../prep.d/videos/calibration/` | 56 个机器人 rollout 视频（mp4，不入库） |
| `../../../prep.d/videos/calibration/rulecards/` | 28 张 SVG 规则卡（浏览器打开） |

## 记录组成（92 条）

| kind | 数量 | 说明 |
|---|---|---|
| `part1_obstacle` | 32 | Part1 8 障碍 × 4 策略的真实策略 rollout（当前本地策略全部失败，用于验"误判失败"） |
| `part2_level` | 24 | Part2 6 类 × 4（不同 policy/level）真实策略 rollout（同上） |
| `part1_rulecard` | 16 | Part1 每障碍 1 条 canonical 成功路径 + 1 条规则违反路径（SVG 俯视图，含足端 tag/触地接触） |
| `part2_rulecard` | 12 | Part2 每类 1 条成功 + 1 条失败语义卡（SVG 俯视图） |
| `session_state` | 8 | 整场账本 / pause-resume / abort / pause_timeout / skipped / best-fastest 等协议状态表 |

> 为什么有 rulecard：本地没有训练好的障碍/能力策略（现有 flat/gravel 策略在正式障碍上 0/8、Part2 0/6），
> 真实 rollout 只能覆盖"失败侧"。rulecard 用规则 judge 自己接受的 canonical 样本路径覆盖"成功侧"，
> 让你能同时校准 judge 的 false-fail 与 false-success；它们不替代真实机器人视频，C2 基线训练出可成功策略后会补真实成功视频。

## 怎么标（盲标，约 1.5–2.5 小时）

1. 打开 `index.html`；CSV 里按 `trial_id` 顺序逐条。
2. **不要打开 `records.jsonl`**（含 judge 结论，会破坏盲标）。
3. 对 `part1_obstacle` / `part2_level`（56 条 mp4）：
   - 看视频，按比赛规则判断机器人是否真正完成该障碍/能力项；
   - `human_success` 填 `true`/`false`；
   - 失败时填 `human_failure_reason`（建议代码：`no_crossing`、`two_feet_ground`、`fell`、`bar_drop`、
     `wrong_side`、`incomplete`、`timeout`、`other:<说明>`）。
4. 对 `part1_rulecard` / `part2_rulecard`（28 张 SVG）：
   - 俯视图：折线是基座 x-y 轨迹，点上的 label 是足端接触到的表面 tag / `G:` 地面足；
   - 判断"按规则这条轨迹应 success 还是 fail"→ 填 `human_success`；
   - 再判断"judge 的结论是否正确"→ `human_judge_verdict_correct` 填 `true`/`false`（judge 结论见 SVG 标题）。
5. 对 `session_state`（8 条，无视频）：
   - 看状态表，检查协议语义是否正确（best score、同分取最快、恢复不消耗尝试、暂停冻结/原位恢复、
     abort 消耗尝试、pause_timeout、skipped 不计分/不计时长）；
   - `human_protocol_ok` 填 `true`/`false`，有问题在 `human_failure_reason` 写说明。
6. 保存 CSV（保持 UTF-8），然后运行：

```bash
cd /home/bis/BiS.d/Code.d/RoboCon/MyMonoRepo.d
pixi run python @20261019_locomotion/scripts/agent_scripts/check_calibration.py \
  --labels @20261019_locomotion/comp/eval/_calibration/labels_template.csv
```

会写出 `comp/audits/C1_CALIBRATION_REPORT.{md,json}`：覆盖率、judge-human 分项一致率、逐条不一致清单。
若有不一致，我会逐条核规则（可能改 judge 或记录为标定例外），然后重跑受影响的少量视频。

## 判定口径速查（2026-10-22 已确认）

- Part1 八障碍各自 success = 合法进入 → 实际跨越/接触证据 → 完整离开；**任何瞬间 ≥2 足触地失败**（落地阶段除外，
  完成跨越后的下障碍触地属于落地）；限高杆只看横杆是否掉落，碰杆不算失败；T 台阶部分分 ×2/3（上 50、下 33、两侧 100），
  漏级/异臂乱序失败；砂砾坑短边进出；斜坡两侧合计 ≥1 m；方墩桥/窄带桥到另一侧平台。
- 整场：3 次尝试、恢复不消耗、best score、同分取最快、计时在稳定停下后停止；返回奖励只认全部 8 项满分后重进出发区。
- Part2：六类各最多 4 次，取最高成功难度，分数 floor，10 cm 端点 0 分，允许任意成功姿态（不要求固定步态）。
- rulecard 标注以“规则应判什么”为准，而不是“视频里跑得多漂亮”。

## 完成后

把填好的 CSV 路径告诉我（或直接保存在原位置）；我跑一致性检查、把结果写入 C1 报告与 G1 材料；
不一致项逐条讨论后决定改 judge 还是记录为例外。确认无误后你再恢复 goal，我进入 C2 基线评测/日常循环。
