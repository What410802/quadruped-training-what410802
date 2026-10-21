# 评测协议与 baseline gate（2026-10-20 初版）

> 目的：在改任何 reward/curriculum 之前，先把“基线是否可用”变成可重复、可比较的数字。当前 flat baseline 已完成、rough 质量不足（见 [`status.md`](../status.md)）。本协议先用于 flat/rough 基线，后续台阶/梅花桩与优化实验都复用它。

## 0. 2026 队内赛真值 vs 本协议

本文件 §3–§6 的 flat/rough/砂砾 gate 是**训练内部 gate**，不是比赛验收口径。2026-10-21 收到的培训方 `队内赛.pdf` 才是当前真值，完整成功定义/计分见 [`../reference/team-race-2026.md`](../reference/team-race-2026.md)。

判定器框架/足接触语义/验证计划见 [`competition-judge.md`](competition-judge.md)。必须新增两类官方 evaluator（P0，优先于继续调参）：

| evaluator | 判据（摘要） | 输出 |
|---|---|---|
| 赛项一 障碍赛 | 逐个障碍成功定义：绕杆 S 形/必达区；砂砾碎木坑从 1 m 短边进出且 1/2 以上足不触地；高墙越/爬；限高杆穿过且杆不掉；T 台阶每级至少一次足底接触且 1/2 足不触地；斜坡沿 3 m 长边至少走 1 m 且 1/2 足不触地；木桥 A/B 通过且 1/2 足不触地 | 每障碍 100、返回 100、总 900；用时/尝试次数 |
| 赛项二 能力测试 | 高台/楼梯/斜坡/高墙/沟壑/梅花桩，按最高难度；每障碍 4 次；仅 RL；力矩 hip/thigh ≤25 N·m、calf ≤60 N·m | 每障碍得分、总分 1300 |

- 官方 evaluator 必须记录：足接触比例、成功/失败原因、尝试次数、是否跳过、摔倒/恢复位置、得分。
- 旧 §3 命令 suite 只用于 flat/rough 训练诊断；不能作为比赛 gate。
- 旧 §4 的“2026 V2.0/2027”地形条目仅历史参考；正式场/能力场以 PDF 图 1–4 和培训方文件为准（当前尚未建 MJCF）。
- **部署传感器红线**：官方 evaluator/最终 actor 只允许 IMU+编码器（+可选相机/雷达）；height scan、foot force、foot height、body height、body lin vel 等不能进 actor。

## 1. 产物与记账

每个被评测的策略必须带一份元数据（运行仓库 `assets/policies/<version>/README.md` 或等价记录）：

- 训练仓库 commit（fork 后是 fork commit）、`uv.lock` hash；
- 训练命令、task id、`num_envs`、`max_iterations`、种子、TensorBoard run 目录；
- checkpoint 文件与导出 `policy.pt` 的 sha256；
- 本协议版本（本文）、评测脚本 commit/参数、评测日期与机器。

没有元数据的策略不进入 `main` 的“已验收策略”集合。

## 2. 契约

| 项 | 训练/评测契约 |
|---|---|
| actor obs | PPO 45 维单帧（命令 3 + base ang vel 3 + projected gravity 3 + joint pos 12 + joint vel 12 + last action 12）；HIM 为 6×45 = 270（oldest→newest） |
| action | 12 维 raw action，`q_target = q_default + 0.25 × raw`；policy order FL→FR→RL→RR（hip/thigh/calf） |
| PD | Kp=40、Kd=1.2 |
| 控制周期 | 策略 50 Hz（20 ms）；训练/评测主线用 physics dt 5 ms × decimation 4；部署参考 runner 另有 2 ms 物理 + 20 ms 策略的对照 |
| 力矩上限 | 评测时用训练模型的 actuator ctrlrange（模型默认 clamp ±20 N·m；真机包络 33.5，后续单独做 A/B） |
| 场景 | 本地 MuJoCo：flat 用 `@20261005_ros2/scenes/flat_scene.xml`；地形评测后续用 `terrain.zip` 能力场与自建场地 |

评测脚本必须显式打印以上契约的校验值（obs/action shape、joint mapping、policy dt），不匹配直接失败。

## 3. 命令 suite（固定、可重复）

每个 episode 从 `z=0.45 m`、指定 yaw 的静止状态开始，先固定 PD 稳定 1 s、零指令暖机 1 s，再进入命令段。命令段建议初版：

| 段 | 命令 (vx, vy, wz) | 时长 | 用途 |
|---|---|---|---|
| stand | (0, 0, 0) | 5 s | 静止漂移/抖动 |
| fwd-slow | (0.3, 0, 0) | 4 s | 低速跟踪 |
| fwd-nominal | (0.8, 0, 0) | 6 s | 常规速度 |
| fwd-fast | (1.5, 0, 0) | 6 s | 高速（若课程已扩到） |
| bwd | (-0.5, 0, 0) | 4 s | 后退 |
| lat | (0, ±0.5, 0) | 4 s | 横移 |
| yaw | (0, 0, ±0.5) | 4 s | 转向 |
| combined | (0.8, 0.3, 0.4) | 6 s | 组合指令 |
| arc-left | (0.5, 0, 0.35) | 4 s | 前进+转向（圆弧）|
| arc-right | (0.5, 0, −0.35) | 4 s | 反向圆弧 |
| step 0→0.8→1.5→0 | 阶跃 | 各 3 s | 平滑切换/超调 |
| push-free | (0.6, 0, 0) | 6 s | 无外扰基线 |

同一套命令序列用于 baseline 与后续实验；每段重复至少 3 个种子（策略确定性则用环境扰动种子），报告均值与最差 episode。

## 4. 地形 suite（与训练阶段对应）

| 阶段 | 地形 | 来源 |
|---|---|---|
| flat baseline | plane、small slope（11.3°/14° 近似）、rough t1–t7、低摩擦 | 本地自建/`terrain.zip` 车道 |
| 砂砾近似 | 静态预沉降碎石、起伏随机刚体地面 | `gravel-feasibility.md` 的静态路线 |
| 台阶/梅花桩/能力场 | 2026 队内赛 T 台阶、高台、高墙、沟壑、梅花桩 | 按 PDF 图/尺寸自建 mjlab task + evaluator（P0，后续） |
| 正式场 | 2026 队内赛障碍赛 + 能力测试 | 后续自建 MJCF/evaluator（P0；PDF 为当前真值） |

## 5. 指标

| 指标 | 定义 | 用途 |
|---|---|---|
| 线速度跟踪 | 命令段内 `mean(||v_body,xy − v_cmd,xy||)` 与 RMSE | 主任务指标 |
| 角速度跟踪 | 命令段内 `mean(|wz − wz_cmd|)` | 主任务指标 |
| 摔倒率 | tilt > 60° 或非法接触持续 0.2 s 的 episode 比例 | 安全 gate |
| 卡死率 | 有移动指令时 progress speed <0.05 m/s 持续 >3 s | 安全 gate |
| 基座高度/姿态 | 均值与最大偏差（目标 0.43 m、tilt） | 稳定性 |
| 力矩/功率 | `sum|τ|`、`sum|q̇ τ|`、`sum|q̇||τ|` 的 RMS/max | 能量/电机负载 |
| 动作平滑 | `sum(a_t−a_{t−1})²`、`sum(a_t−2a_{t−1}+a_{t−2})²` | sim2real |
| 足端滑移 | 接触期足端水平速度均值（后续加） | 打滑/效率 |
| CoT（可选） | 正机械功率积分 / (mg·距离) | 与第一性原理实验对照 |

## 6. Baseline gate（初版，可按实测调整）

baseline 必须在**不改 reward/curriculum 设计**的前提下满足：

- **G1 flat 基本可用**：stand 5 s 无摔倒、水平漂移 ≤0.30 m（初版 0.15 m，2026-10-20 baseline 实测后校准：baseline 实测 0.273 m，且训练没有位置保持奖励、零指令速度误差仅 0.0049 m/s，0.15 m 阈值过严；若后续加 standing 训练再收紧）；fwd-nominal 6 s 无摔倒，线速度跟踪 MAE ≤0.25 m/s，yaw MAE ≤0.20 rad/s。
- **G2 课程推进**：command curriculum 的 `vx_max` 在 2000 iteration 内至少推进到 ≥1.5（记录曲线；若未推进，允许按“不改变设计”的少量调参，见 §7）。
- **G3 rough 可跑**：从 flat checkpoint 续训后，在 rough 评估中 terrain level 均值有推进、无 NaN/数值崩溃；逐地形通过率达到记录值（阈值先记录，不在 baseline 阶段强行调高）。
- **G4 导出/回放**：`policy.pt` 可被本地评估脚本加载；obs/action shape 与契约一致；用同一命令 suite 复跑结果可重复（同种子差异在噪声内）。
- **G5 无异常**：训练日志无 NaN、无频繁容量溢出；评测时无 segfault/崩溃。

如果 G1/G2 不达标：先查环境和配置问题（地形、DR、观测、action 映射），再允许**少量调参**（见 §7）。如果 G3 不达标：记录失败模式，作为台阶/梅花桩阶段与优化实验的输入，不阻塞后续。

### 6.1 台阶/梅花桩：诊断测试与正式训练分开（2026-10-21）

结论：**不需要“当前策略在 flat/rough 上满意”才允许测试，但正式训练必须先过最低门槛。** 两种活动的目的和失败代价不同：

- 诊断性集成测试只花几分钟，用来暴露地形、height scan、碰撞、终止、导出/回放的问题；如果连这个都不做，就无法判断后面的失败来自环境还是策略。
- 没有门槛就开正式训练，会把环境 bug、契约错误和策略能力混在一起，浪费 GPU，还可能学出拖腿/卡边等坏习惯。

| 层级 | 允许做的事 | 门槛 |
|---|---|---|
| 诊断性集成测试 | 用现有策略在自定义 T 台阶/梅花桩跑 1–3 episode，检查地形/高度扫描/碰撞/终止/回放 | 导出策略可加载、契约校验通过；不训练、不调参；结果标为 `diagnostic`，不计入台阶阶段成绩 |
| 正式台阶/梅花桩训练 | 建课程、训练、按通过率评测 | H1–H4 全部通过；H5 有记录（不阻塞） |

正式训练硬门槛：

- **H1 flat 基本可用**：G1/G2/G4/G5 通过（G1 的 stand 阈值按当前校准值 0.30 m；后续若收紧，按收紧值）。
- **H2 数值安全**：`Loss/value` 与平方类 reward 有限；连续 200 iteration 内无 NaN、无 `normal expects std >= 0` 断言、无 Warp CUDA 710；已加 clamp 与 stop-on-nonfinite（见 [`training-health.md`](training-health.md) §3）。
- **H3 地形管线**：自定义台阶/梅花桩在训练仓库注册；本地场景可加载；height scan/critic 与地形尺寸一致；`nconmax/njmax` 足够；出生点与相机安全。
- **H4 步态硬故障排除**：不能有已确认的动作/观测顺序错误；不能有单腿全程拖地/从不离地。当前 flat 的 RL/RR 不对称（RR 接触比例 1.00 vs RL 0.84）按“必须定位、但不必等完全对称”处理：若最终确认只是 PPO symmetry breaking，且台阶诊断中没有单腿拖行/卡边，可带风险进入正式训练并并行修；若台阶诊断显示拖腿导致卡边，则升为硬阻塞。
- **H5 rough 定义正确**：legacy rough 的 G3 **不阻塞**台阶正式训练（它含 50% stairs/discrete obstacles，是鲁棒性配置，不是 target）；rough-flat 拆分后的短基线应至少做到“无崩溃、terrain curriculum 有推进、通过率可复现”。若一时没做，正式训练前要在记录里明确这是已知风险，不能把台阶失败归因于 rough 基线。

**不构成门槛的项**：flat 动作“好看”、完全对称步态、CoT/能量、legacy rough 的台阶通过率、台阶/梅花桩上现有策略的原始通过率（训练前必然差）。这些是优化/验收目标，不是启动训练的前置条件。

**当前判断（2026-10-21）**：flat 基本通过；rough 有数值不稳定与地形课程卡死，rough-flat 尚未拆分。因此**暂不启动台阶/梅花桩正式训练**；可先做诊断性集成测试、导出 rough 模型做 G3，并按 [`training-health.md`](training-health.md) 加数值安全网、拆 rough-flat。

### 6.2 S1b：平地（含砂砾）gate（2026-10-21，2 天时间盒）

目标：在 `black-gravel-flat`（50% flat + 30% 细砾石 + 20% 粗砾石代理，无台阶/离散障碍）上确认“基本行走可用”。这是当前 2 天时间盒的 gate；**不通过就转实验性思路，不把时间继续花在同一个 baseline 配方上**。

评测口径（初版，第一次正式评测后按实测校准）：

- 32 envs，play/nominal physics，命令段 `stand / 0.3 / 0.5 m/s 前进 / 后退 / 横移 / 转向 / 组合`，每段 4 s；固定种子。
- **通过线**：摔倒率 ≤5%；0.3 和 0.5 m/s 的 `MAE vx` 分别 ≤0.15 / 0.20 m/s；最大 tilt 的 p95 ≤25°；无持续 stuck；0.8 m/s 只记录不作为硬门槛。
- 不要求后腿完全对称、不要求 foot clearance 达到 0.09 m；这些是步态质量目标，单列。
- 若 2 天内（至 2026-10-23）仍不通过：按 [`training-plan.md`](training-plan.md) §2 的实验性路线走（history/HIM、非对称 actor-critic、接触/足端奖励、动态砂砾代理），不再只调现有 10/11 项权重。

当前证据（2026-10-21，32 envs、play 模式、随机 terrain level 0–2；不是最终固定地形 gate）：flat `model_1999` 全段 0 摔倒，0.3/0.5 m/s 的 vx MAE 0.127/0.128、p95 tilt 9.4°/7.9°；mirror+footclear 500 全段 0 摔倒，0.3/0.5 m/s 的 vx MAE 0.089/0.162、p95 tilt 9.5°/7.8°；砾石训练 `model_2100` 全段 0 摔倒，0.3/0.5 m/s 的 vx MAE 0.147/0.092、p95 tilt 5.3°/5.9°；flat fine-tune `flat-ft-2500` 全段 0 摔倒，0.3/0.5 m/s 的 vx MAE 0.134/0.178、p95 tilt 8.8°/8.6°。**四版都通过初版 S1b**；`flat-ft-2500` 的 flat gate 也通过；这些仍是 screening，不是正式固定地形评测。

**S1b 的两个地面都要覆盖（2026-10-21 明确）**：

- **S1b-fixed**：`black-gravel-flat`，4096 envs 批量预训练；`flat-ft-2500` 在 64 envs 已 provisional pass。
- **S1b-free**：`black-gravel-free` 改为**抬高石床 + 6 cm 基座 + 6 cm 低 curb + 700 静态预沉降石 + 120 自由碎石子**（碎石 3–8 cm，随机椭球；1.5×1.5 m，无高围栏）。6 cm 来自独立踩入实验 3.3 kg 单足 p95 5.3 cm + 0.7 cm 余量；覆盖：自由层 union 11.5%、静态层 58.4%、合计 63.2%。820 石体/每 world，训练/评测成本高。旧 24 石块/带围墙和 dense80 大石块结果都只作历史/木块参考，不再作为 S1b-free 证据；composite 训练尚未完成；但 `flat-ft-2500` zero-shot 在 composite **4 envs：0 摔倒、0.3/0.5 m/s MAE 0.089/0.049、p95 4.1°/3.1°**，provisional pass（4 envs/单布局，不是正式验收）。

**2026-10-21 结论**：S1b-fixed 初版通过（`flat-ft-2500`）；S1b-free 已按“抬高石床 + 3–8 cm 实际碎石尺寸 + 6 cm 预烘焙基座”重做，但 composite 训练/评测尚未完成；旧大石块结果不再作为证据。下一步先测吞吐/优化静态层，再评测与多 seed。

### 6.3 “平地”的宏观边界（2026-10-21 提案，待实例校准）

用户提出：不能只按“有没有围栏/石块”分类，应按**高度尺度**判断是否属于平地：

- **宏观平地定义（2026-10-21 先取 1/3）**：障碍/围栏/地形起伏的最高点 < 狗质心离地高度的 **1/3** 时，算平地；Black 站立质心约 0.43 m，对应上限约 **0.14 m**。1/2 只作为后续敏感性对照，不用于当前分类。
- 例如：为了围住石块而造的低矮围栏、5–40 mm 的台阶沿、3–8 cm 碎石层、6 cm 基座，都属于“平地”的宏观起伏；0.25 m 以上的围栏/台阶则不再是平地。
- 这个定义是**宏观分类**，不是接触质量/摩擦/脚步稳定性的替代；碎石层虽然宏观是平地，仍会因滚动/踩穿影响策略。
- 当前 `black-gravel-free` 采用：6 cm 基座 + 6 cm 低 curb + 3–8 cm 碎石，石顶最高约 14 cm；按 1/3（0.14 m）边界仍属于平地任务。低 curb/石床不是高围栏，S1b 分类不变；后续用实例继续校准。

## 7. 允许的“少量调参”边界（不改变原设计）

仅允许调现有参数、一次只动一项、记录原因与结果：

- command curriculum 的阈值/步长/初始范围（不改算法结构）；
- reward 权重幅度（例如 ±50% 内、单项），不新增 reward term；
- DR 范围（摩擦/payload/push 等）在现有项内微调；
- 训练时长/种子；
- 不得改：actor/critic 结构、obs/action 契约、终止类型、课程类型。

每次调参都写进训练仓库 `docs/` 或本任务 `status.md`，baseline 的对照集保留原始版本。

## 8. 当前 baseline 运行记录

| 项 | 值 |
|---|---|
| 训练命令 | `MUJOCO_GL=egl .venv/bin/train black-flat --env.scene.num-envs 4096 --agent.max-iterations 2000 --agent.logger tensorboard --agent.run-name baseline-2000` |
| 机器 | `bis-ms7e56`（RTX 5060 Ti 16 GB） |
| 启动时间 / 日志 | 2026-10-20 18:13 左右；`~/rc_work/baseline/flat_baseline_2000.log` |
| 初始吞吐 | 约 1.55–1.57 s/iteration（4096 envs），ETA 约 50 min |
| 状态 | ✅ flat 训练完成（47:19，2026-10-20 19:00 左右）；导出的 `policy.pt` 与 flat gate 评测见 [`experiments.md`](experiments.md) §3；G1 conditional、G2/G4/G5 通过；rough 的 G3 初判未通过（[`experiments.md`](experiments.md) §3.4） |
