# HIMLoco `best.pt` zero-shot 评测（2026-10-24）

> 目的：验证主办方/大作业给的 HIMLoco `best.pt` 能不能当 **blind baseline / fallback / teacher**，再决定 C2 视觉主线的起点。
> 模型内部结构、270 维输入契约、部署拼法见 [`policy-model.md`](../../../@20261007_assignment/docs/policy-model.md) 与 [`porting.md`](../../../@20261007_assignment/docs/porting.md) §5；本文只记评测方法与实测结果。
> 评测器是 C2 诊断链路（Part1 V2 judge、Part2 V2 evaluator，**G1 未冻结**），所以下面所有分数只能当 diagnostic，不能对外引用。

## 1. 结论

- **模型本身健康**：`best.pt`（991679 B，md5 `7af7bab2cc1cb559000551f2637e0649`，sha256 `a5979a6b…`）加载后 `[1,270] → [1,12]`、batch 3 正常、确定性输出，与 `policy-model.md` 的契约一致。
- **平地行走可用**：`@20261007_assignment` 的参考实现（`policy_reference.py`，同一份 config + 同一套 PD/kp/kd）在 flat scene 上 `cmd=0.5` 实测 vx=0.360 m/s、tilt max 3.1°、`|tau|` 峰值 15.8 N·m（<20）、10 s 内不摔。→ 可以当 flat/粗糙地形的 **blind fallback**（比 `flat-ft-2500` 的 0.022 m 拖地足端干净得多）。
- **Part 1 八障碍 0/8（诊断）**：固定诊断起点/时长下全部失败，原因分两类——(a) 走得慢，时间窗内没到障碍（height_bar/high_wall/slalom 的 `touched=false`）；(b) 真卡住/规则失败（slalom 被第一根杆挡住、bridge 上不去、gravel/slope 触发 `two_feet_ground` 判罚）。**T 台阶有真实进展**：延伸到 2× 时间后爬上南臂 1–3 级（北臂到 3 级），只是没完成"两臂 + 顶部"拿不到部分分。
- **Part 2 低/中档可用（时间放宽后）**：固定 6 s 窗口 0/20（**全部是"没走到障碍"**，不是能力失败）；把窗口放到 12 s 后 **8/20 档成功**，diag 总分 300/1300：high_platform 10/20 cm、stairs 10/15/20/30 cm、slope 20°/30°、trench 10 cm（10 cm 端点按 Q5 记 0 分）；high_wall 全档、slope 35°/45°、trench 20/30 cm、plum 失败。
- **不能用它直接 fine-tune**：训练侧（mjlab）与部署侧（HIMLoco：6 帧历史 + `estimator`）obs/action 契约不同；它适合当 **fallback / teacher / 对照**，不是 C2 主训练起点（除非先做契约对齐）。

## 2. 方法

新增脚本 [`eval_him_best.py`](../../scripts/agent_scripts/eval_him_best.py)：复用本地 Part1 V2 judge runner 与 Part2 level runner，只把"策略步"换成 HIMLoco 契约：

- 观测：每 20 ms 一帧 45 维（commands×[2,2,0.25]、ang_vel×0.25、gravity、dof_pos−default、dof_vel×0.05、上一帧 action），整体 clamp ±100，压入 6 帧历史（最新在前），拼成 270 维；
- 动作：`[1,270] → [1,12]`，clip ±100，`q_target = default_dof_pos + 0.25 × action`，kp=40 / kd=1.2，力矩限 `torque_limits=33.5`（模型自己的训练包络；不等于本地 20 N·m 场景限幅，见 §4 局限）；
- 场景 / judge / 采样节拍与 `run_part1_judged_rollout_v2.py`、`run_part2_judged_eval.py` 完全一致，因此结果和 `flat-ft-2500` 诊断可直接对比。

两种诊断变体：

| 变体 | Part 1 时长 | Part 2 时长 | 用途 |
|---|---|---|---|
| frozen-start（默认） | 与既有诊断相同（4.0–7.2 s） | 6 s | 与既有 `flat-ft-2500` 诊断同口径 |
| time-extended（`--time-scale 2 --p2-seconds 12`） | ×2 | 12 s | 区分"没走到"和"真不会" |

## 3. 契约自检（脚本每次先跑）

| 检查 | 结果 |
|---|---|
| TorchScript 加载 | ok |
| `[1,270] →` | `[1,12]` |
| `[3,270] →` | `[3,12]` |
| `out_abs_max`（seed 0 随机输入） | 2.052（与 `policy-model.md` 记录的 2.05 一致） |
| 确定性（同一输入两次） | True |
| md5 / sha256 | `7af7bab2cc1cb559000551f2637e0649` / `a5979a6b56a820642ab5f33c6e885de51c5747099777c678c3a0897e71e8afa1` |

## 4. 平坦地面基准（`policy_reference.py`，非本文脚本）

```bash
pixi run python @20261007_assignment/scripts/agent_scripts/policy_reference.py --cmd 0.5,0,0 --seconds 8 --window 4
```

实测（2026-10-24）：`last 4s: vx=0.360 vy=-0.009 wz=-0.003 z=0.414 (min 0.403) tilt max=3.1deg`；`|tau| peak=15.8 N·m，>20 N·m 的步数 0.0%`，`fell=no`。→ 平地稳态跟 0.5 m/s 指令只到 0.36 m/s（有稳态误差），但稳定、力矩不顶限。

## 5. Part 1 结果（1 次尝试/障碍，诊断）

### 5.1 frozen-start（与既有诊断同口径）

| 障碍 | status | reason | 证据 | 结束 base (x,y,z) | tilt |
|---|---|---|---:|---|---:|
| height_bar | fail | timeout | in_zone=119, touched=False | [5.687, -9.46, 0.411] | 2.88 |
| high_wall | fail | timeout | in_zone=659, touched=False | [1.786, -7.327, 0.403] | 1.34 |
| bridge_blocks | fail | timeout | — | [1.063, 0.032, 0.41] | 3.37 |
| bridge_bands | fail | timeout | in_zone=732, touched=True | [5.593, -3.688, 0.608] | 3.95 |
| gravel_pit | fail | two_feet_ground:RL,RR | in_zone=1617, touched=True | [5.413, -11.805, 0.57] | 3.29 |
| t_stairs | fail | timeout | 南臂 s 到 1–3 级 | [1.623, -4.041, 0.761] | 10.09 |
| slope | fail | two_feet_ground:FL,FR,RL | in_zone=1010, touched=True | [3.807, -5.08, 0.413] | 1.82 |
| slalom | fail | timeout | in_zone=368, touched=False | [1.775, -10.183, 0.412] | 2.75 |

`total_score=0 success=0/8`。

### 5.2 time-extended（2× 时长）

`total_score=0 success=0/8`，但证据更清楚：

- **t_stairs**：`arms={'s':[1,2,3], 'n':[3]}` —— 南臂 1–3 级走完、北臂到 3 级，但没到 `top`，按 judge 拿不到部分分（部分分要求 top）。
- **bridge_bands**：`in_zone=1732`（8.66 s 都在桥区）、touched=True，但没完成跨越；`bridge_blocks` 仍卡在左平台起点（x≈1.06）。
- **height_bar / high_wall / slalom**：`touched` 仍为 false，结束位置与 frozen 变体几乎逐位相同（如 high_wall y=-7.327、slalom y=-10.183）→ 不是时间不够，而是被挡在障碍前（slalom 第一根杆、限高杆门洞前）。
- **gravel_pit / slope**：都因"任何瞬间 ≥2 足触地"判罚失败（Q1 口径），说明策略在砂砾/坡面上是"正常行走"而不是能力型通过。

### 5.3 与 `flat-ft-2500` 对比

同一套 frozen-start 诊断下两者都是 0/8，但轨迹不同：`flat-ft-2500` 在 slope 直接翻倒（tilt 178.6°），`best.pt` 在 slope 保持直立（tilt 1.8°）但被地面判罚；T 台阶 `best.pt` 上到 z=0.76、`flat-ft-2500` 停在 z=0.41。→ 同样的 0 分，`best.pt` 的物理能力明显更强。

## 6. Part 2 结果（20 档，1 次尝试/档，诊断）

### 6.1 frozen-start（6 s）

`diag_total_score=0`，20/20 fail，**全部 reason=timeout**；high_wall/trench 各档结束位置逐位相同（x=2.039、z=0.424）→ 7 s（含 1 s warmup）只走了约 2.0 m，压根没到 x≈2.5 的障碍。**这组数字不能当能力结论**。

### 6.2 time-extended（12 s）

`diag_total_score=300`（按 CONTRACT 的 Q5 曲线），8/20 档成功：

| 类别 | 成功档 | 失败档 | 关键数字 |
|---|---|---|---|
| high_platform | 10 cm、20 cm | 30/40 cm | 成功时平台顶 z=0.519/0.594；30 cm 起卡在平台边（x≈1.66、z≈0.42） |
| stairs | 10/15/20/30 cm（全过） | — | 台阶顶 z=0.516→0.704；30 cm 档 6 级每级 5 cm |
| slope | 20°、30° | 35°、45° | 30° 到坡顶 z=1.29；35° 卡在坡中（tilt 27.6°）、45° 起步即 tilt 33.7° |
| high_wall | 无 | 10/20/30/40 cm | 10 cm 档越过了墙（x=3.436）但 judge 要求墙附近 `max_z≥0.55`，实测 0.478 → 判失败；见 §7 局限 |
| trench | 10 cm | 20/30 cm | 10 cm 档跨过（x=3.028）；20/30 cm 掉进沟里（z=0.209/0.179、tilt 17.6°/8.8°） |
| plum | 无 | 1 级 | 上过桩面（max_z=0.628）但偏离通道（y=1.26 > lane 0.7） |

## 7. 局限与注意事项

- **诊断窗口对慢策略偏短**：frozen-start 的 Part2 6 s 窗口不足以让这个 0.29–0.36 m/s 的策略走到 x≈2.5 的障碍；后续 Part2 诊断/协议要么给 ≥10–12 s，要么按"到达障碍"触发计时，否则会把"没走到"当"不会"。
- **judge 口径观察（不是本次改动的对象）**：Part2 high_wall 的 `max_z ≥ max(wall_h+0.10, 0.55)` 对"跨过而不是爬上墙"的通过方式偏保守；10 cm 档实测越墙仍判失败。是否要改属 G1/协议范围，需审计后再动。
- **力矩包络**：本文按模型自己的 `torque_limits=33.5 N·m` 评测；本地 Part1/Part2 场景 ctrlrange 是 ±20 N·m（`flat-ft-2500` 诊断也用 20）。实测平地 `|tau|` 峰值 15.8，未触发两者差异，但高难度地形上 33.5 vs 20 可能影响结果，跨策略比较时口径要写清楚。
- **G1 未冻结**：Part1/Part2 分数仍是 diagnostic；本文所有数字不进 SCOREBOARD。
- **训练契约不一致**：`best.pt` 是 6 帧 270 维 HIMLoco，mjlab 训练仓的 PPO actor 是 45 维单帧；不要把它直接塞进 mjlab resume/fine-tune，除非先做 obs/action/estimator 的契约对齐（或 distill 成 45 维 student）。

## 8. 复现

```bash
# 仓库根目录；CPU 即可，不需要 GPU/远程机
pixi run python @20261019_locomotion/scripts/agent_scripts/eval_him_best.py --part all --out-dir ../prep.d/results
pixi run python @20261019_locomotion/scripts/agent_scripts/eval_him_best.py --part all \
    --time-scale 2.0 --p2-seconds 12 --tag _extended --out-dir ../prep.d/results
```

产物（不入库）：`../prep.d/results/him_best_part1_v2[_extended].json`、`him_best_part2_v2[_extended].json`、`him_best_eval_summary[_extended].md`。

录像（让用户能二次检查评测过程；只加渲染，不改 judge/起点/时长，数字与不录像时一致）：

```bash
MUJOCO_GL=egl pixi run python @20261019_locomotion/scripts/agent_scripts/eval_him_best.py \
    --part all --time-scale 2.0 --p2-seconds 12 --tag _extended \
    --video --video-dir ../prep.d/videos/him_best --out-dir ../prep.d/results
```

产物：`../prep.d/videos/him_best/part1/*.mp4`（8 段，每个障碍独立起点/命令）、`part2/*.mp4`（20 档），索引 `../prep.d/videos/him_best/index.html`；全部可视化（含 blind vs depth 对照与演示 GUI 截图）汇总在 `../prep.d/videos/review_20261024.html`。
