# C1 人工标定包使用说明（2026-10-23 更新：失败原因字典 + rulecard 可解释性增强）

## 这是什么

C1 = 评测器标定阶段：用**人工标签**给规则 judge 做 ground truth，检查 judge 是否误判、并在 judge 语义变更后做回归。
不是训练数据，也不会训练学习型 judge（规则 judge 需可复现、可审计）。

产物在 `comp/eval/_calibration/`：

| 文件 | 说明 |
|---|---|
| `records.jsonl` | 92 条记录（含 judge verdict/evidence；**标注时不要先看**，CSV 已隐藏 judge 结论） |
| `labels_template.csv` | 盲标表：填 `human_success` / `human_failure_reason` / `human_protocol_ok` / `human_judge_verdict_correct` |
| `index.html` | 浏览全部记录（视频/SVG 链接 + session 状态表），建议直接用它逐个打开 |
| `../../../prep.d/videos/calibration/` | 56 个机器人 rollout 视频（mp4，不入库） |
| `../../../prep.d/videos/calibration/rulecards/` | 28 张 SVG 规则卡（**已升级**：含障碍几何脚印、base/bar 高度曲线、judge 实际证据、KEY RULE 差异点） |

## 记录组成（92 条）

| kind | 数量 | 说明 |
|---|---|---|
| `part1_obstacle` | 32 | Part1 8 障碍 × 4 策略真实 rollout（当前本地策略全失败，用于验"误判失败"） |
| `part2_level` | 24 | Part2 6 类 × 4（不同 policy/level）真实 rollout（同上） |
| `part1_rulecard` | 16 | Part1 每障碍：1 条 canonical 成功路径 + 1 条规则违反路径 |
| `part2_rulecard` | 12 | Part2 每类：1 条成功 + 1 条失败语义卡 |
| `session_state` | 8 | 整场账本 / pause-resume / abort / pause_timeout / skipped / best-fastest / 返回奖励 / 3 次上限 |

## 失败原因字典（`human_failure_reason`，2026-10-23 明确）

按**优先级从上到下**取第一个成立的（不要重复纠结）：

| 取值 | 定义 | 说明 |
|---|---|---|
| `fell` | 视频中机器人翻倒/侧翻/明显失稳，已无法继续 | 最高优先级 |
| `bar_drop` | 限高杆被顶落到低位（横杆掉落） | 仅 height_bar |
| `two_feet_ground` | 明显 ≥2 足同时触地而仍在障碍上（非完成跨越后的落地阶段） | 按比赛规则失败 |
| `wrong_side` | 从错误一侧进入/退出（如砂砾坑应从短边进、本视频从长边进） | 方向性失败 |
| `incomplete` | 明显只完成了一部分（T 台阶单臂、桥走到一半、台阶缺级等），视频中已停止/结束 | 与 no_crossing 区别：已经做对一部分 |
| `no_crossing` | 机器人保持站立但没完成障碍：停住/卡住/走偏/方向错误/最终没越过 | 你目前主要用的"没完成任务" |
| `timeout` | **视频在完成前结束（4–6 s 截断）**，无法判断后续；不是官方 120 s 超时 | 若视频内已停住/摔倒，优先 fell/no_crossing |
| `other:<说明>` | 以上都不合适 | 写清楚现象 |

> 你之前的用法（摔倒=fell、没完成且停下=no_crossing、视频没给结果=timeout）**基本正确**，只是建议再细分：
> 已经做对一部分的用 `incomplete`，方向错的用 `wrong_side`，杆掉了用 `bar_drop`。已标的部分不用返工；
> 如果后面发现某条更符合细分类，改一下即可，检查器只看 success/fail 与 judge 是否一致，reason 只做统计。

## rulecard 怎么看（回应"足部接触不能完全反映正确性"）

旧版卡确实只画了足端 tag；**v2 已升级**，每张卡包含：

1. **俯视图**：障碍几何脚印（从场景 XML 投影的真实 box/cylinder）、zone 边界、goal 区域、路径点
   （点上的 label 是足端接触的表面 tag / `G:` 地面足），以及 IN/OUT；
2. **高度曲线子图**：base z（和 height_bar 的 bar_z）随采样序号变化，虚线是 judge 阈值
   （Part2 的 `top_z+0.38`、`rise_z+0.38`、`max(wall_h+0.10,0.55)`、`min_z`、`goal_z_min`）；
3. **judge evidence**：judge 实际用的证据（`in_zone_samples`、`touched`、`partial`、`arms`、`bar_z` 等）；
4. **KEY RULE / 差异点**：这条轨迹与对照卡的**唯一关键差异**（如砂砾坑短边进 vs 长边进、T 台阶完整臂 vs 缺级）；
5. 页脚提示：足端 tag 只表示"接触了哪个表面"，完成判定还看 base 轨迹/高度/时序/入口-出口方向。

所以你判 rulecard 时：**先看 KEY RULE 的判据，再看几何/高度曲线/证据是否真的满足它**，不要只看点上的 tag。
砂砾坑 success/fail 现在一眼能区分：success 从南短边进、北短边出（`aborted_exit: ymax` 不会出现）；
fail 从西侧长边横穿（judge evidence 里 `aborted_exit: xmax`）。

## 关于"整体账本有没有视频"（明确回答）

**没有。** 8 条 `session_state` 是协议/账本语义记录，用状态表（attempt 列表、score、duration、events、pause/abort/skip）
表达，不是机器人视频；这一轮 course runner 没有录像。你根据 JSON 状态表判断"大致没问题"是符合设计用途的
（验 best score/同分最快/恢复不消耗/暂停冻结/abort/skip 语义）。
真实"3 次整场手动/操作手演练"的视频仍是 G1 残余，会在正式链路补齐；如果你希望现在补课程尝试视频，
需要改 course runner 加录像（约 1–2 h），我可以做，但优先级低于训练策略。

## 关于"样本丰富度低"（同意，已在计划中处理）

- 当前真实 rollout 全失败（预扫描 6 策略 × 8 障碍 48/48 fail），rulecard 只能覆盖语义边界，不能替代真实成功视频；
  **C1 本轮的定位是"失败侧 + 规则语义"的初步锚点**，不是完整标定。
- 等训练出能成功的策略后，补真实成功 rollout（每障碍/每类 2–4 条）重跑 C1 一致性；judge 语义若变，再回归。
- 在此之前，策略训练不依赖"judge 完全正确"：训练 reward 用仿真物理量（base 轨迹/姿态/足接触/速度），
  judge 只在评测/评分时用；C2 baseline 分数在 judge 冻结并通过 C1 后才对外正式报告。

## 怎么标（继续标注的顺序）

1. 打开 `index.html`；CSV 按 `trial_id` 顺序。
2. `part1_obstacle` / `part2_level`（56 条 mp4）：看视频，`human_success` true/false；失败按上面字典填 reason。
3. `part1_rulecard` / `part2_rulecard`（28 张 SVG，**建议在你已标的 56 条之后继续**）：
   - 按 KEY RULE 判断"应 success/fail"→ `human_success`；
   - 判断"judge 判对了吗"→ `human_judge_verdict_correct` = true/false。
4. `session_state`（8 条）：按状态表判断协议语义 → `human_protocol_ok` = true/false。
5. 保存 CSV 后运行：

```bash
cd /home/bis/BiS.d/Code.d/RoboCon/MyMonoRepo.d
pixi run python @20261019_locomotion/scripts/agent_scripts/check_calibration.py \
  --labels @20261019_locomotion/comp/eval/_calibration/labels_template.csv
```

检查器会给出覆盖率、按障碍/类别/session 的 judge-human 一致率、逐条不一致清单；
你已标的部分随时可以跑（会显示 NOT_READY + 覆盖率），不用等全部标完。

## 判定口径速查（2026-10-22 已确认）

- Part1 八障碍各自 success = 合法进入 → 实际跨越/接触证据 → 完整离开；**任何瞬间 ≥2 足触地失败**（完成跨越后的落地除外）；
  限高杆只看横杆是否掉落，碰杆不算失败；T 台阶部分分 ×2/3（上 50、下 33、两侧 100），漏级/异臂乱序失败；
  砂砾坑短边进出；斜坡两侧合计 ≥1 m；方墩桥/窄带桥到另一侧平台；绕杆按顺序 + 拐角。
- 整场：3 次尝试、恢复不消耗、best score、同分取最快、计时在稳定停下后停止；返回奖励只认全部 8 项满分后重进出发区。
- Part2：六类各最多 4 次，取最高成功难度，分数 floor，10 cm 端点 0 分，允许任意成功姿态（不要求固定步态）。
