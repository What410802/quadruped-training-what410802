# Part 2：失败/终止条件与奖励/惩罚的分工

> 日期：2026-10-25 ｜ 来源：用户提问 + 本次调研 ｜ 适用：2026 队内赛 Part 2「越障能力测试」（纯仿真、仅 RL、每障碍 4 次、取最高难度、不计时间）

## 0. 结论速览

1. **分界线不是"难不难"，而是两问：judge 会不会判负？这个状态还可不可能成功？** judge 判负或不可恢复 → 只能做成 termination；judge 不度量、可折衷的质量指标 → 才做 reward shaping；中间没有第三种归属。
2. **success 是吸收态（一旦成立就锁存），所以 success 谓词必须"强到之后任何状态都无法推翻它"**：四轮落在目标支撑面上 + 连续 hold + 姿态合格。"基座越过某条 x 线""基座高度越过某个阈值"都只是事件，不是终态。
3. **硬规则不能只靠惩罚**：惩罚只是把约束折成价格，策略在 `r_task > λ·c` 时直接买过去；Skalse et al. 证明任何非常数代理在一般策略集上都不可能"不可 hack"。反过来，**可恢复且 judge 不判负的问题不要用终止**，否则人为制造 false negative，还教出"不敢冒险"的策略。
4. **训练环境的 success/fail 谓词必须和 judge 是同一个函数、同一份 spec**，否则就是 train/eval mismatch。我们 2026-10-25 的 `competition_goal_reached=76%` 与 `official_platform_success=0` 正是这种 mismatch 的标本（[`blackw-training-runs.md`](blackw-training-runs.md) §HIM 段）。
5. **沟壑的 `max 轮子下降深度 > min(1/2·沟壑深度, 轮子半径)` 合理**，对官方几何它退化成 `τ = r = 0.103 m`；要补的只有两点：20 cm 档余量只有 2.5 cm；success 必须等**四轮都越过 far 边**，而不是 base 过线。

## 1. 问题与现状

### 1.1 用户的两条纠正

- (a) 高墙/高台/楼梯的成功终态应是"四轮都落到目标支撑面 / 越过障碍后的地面"，不是"基座刚越过某条线就判成功"。
- (b) 沟壑里轮子掉进槽（前后轮触地）没有被判失败，说明"穿过 x 就成功"的判据错了。

这两条是同一个 bug 的两面：**把"事件"（某一帧 base x 过线、base z 过阈）当成了"状态"（四轮落在目标面上并保持）**。事件判据有三个结构性缺陷：(i) 对采样率与抖动敏感，可能恰好在不安全的那一帧成立；(ii) 一旦成立就锁存，之后掉下去不再计；(iii) 与"机器人真的上去了"没有因果关系 —— 一次腾空、一次前轮搭台、一次侧倾都能满足。三者叠加的结果就是"判成功了但视频里没过去"，或"轮子掉进槽里却已经算过"。

### 1.2 当前代码到底怎么判

| 判据 | 位置 | 现状 | 问题 |
|---|---|---|---|
| 高台 success | [`comp_part2_judge.py`](../../../@20261019_locomotion/scripts/agent_scripts/comp_part2_judge.py):109 | `x∈goal_x` 且 `base_z ≥ top_z+0.38` 且 `not ground_feet` 且任一轮触 `platform` | 只有"至少一轮上台 + 基座够高"；把"前轮搭台、后轮悬空、机身抬高"也算过 |
| 楼梯 success | 同上:112 | `x ≥ goal_x_min` 且 `base_z ≥ top_z+0.38` 且任一轮触 `stairs` | 同上；`top_z` 是 6×档位，`+0.38` 比真实站立低 14 cm |
| 斜坡 success | 同上:115 | `x ≥ goal_x_min` 且 `base_z ≥ rise_z+0.38` | 同上 |
| 高墙 success | 同上:118-120 | `wall_crossed`（base x 穿墙平面）+ `wall_contact` + `max_z_near ≥ max(wall_h+0.10, 0.55)` | 穿墙用 base 位置判定；"爬升证据"只是"靠近墙时基座抬高过 10 cm"，一次后腿蹬地就能满足 |
| 沟壑 success | 同上:122-123 | `gap_crossed`（base x 穿近边和远边）+ `x ≥ goal_x_min` + `z ≥ min_z` | base 过 far 边即成功；此刻后轮还在槽上方，之后掉进去已经锁存成功 |
| 沟壑 fail | 同上:139-140、180-183 | 接触 `trench_bottom` geom 即 fail | 只在轮子真正触到槽底（深 0.3 m）才触发；10 cm 槽根本触不到底 |
| hold | 同上:189-199 | `hold_s=0.2 s`，中断即清零 | success 侧语义是对的（连续 hold），但 0.2 s 偏短；fail 侧没有等价的去抖（单帧接触/倾角即判负） |
| 失败总类 | 同上:172-179 | `tilt > 75°` 或 `base_z < 0.15` | `0.15` 是**绝对**高度：站在 0.3 m 平台上"趴窝"（base_z≈0.45）不触发 |
| 第二套 judge | [`eval_blackw_part2.py`](../../../@20261024_blackw/scripts/eval_blackw_part2.py):87-215 | 与上面的 V2 各写一套，阈值不同（`z_margin=0.35` vs `+0.38`） | 两份实现必然漂移；同一段视频两个分数 |
| 轮子只传最低那只 | 同上:347-355、427-429 | `lowest_wheel()` 只返回最低轮，judge 只看它 | 判 fail 够用，判"四轮都在目标面"不可能 |
| 沟壑阈值 | 同上:54-58、170-181 | `allowed_drop = min(0.05, 0.5·w)` | 常数 5 cm：10/20/30 cm 三档同一阈值，且**没有**换算成"轮子浸入比例" |
| 评价 JSON 收尾 | 同上:547 | 引用了未定义的 `GAP_Z_TOL_M` | **NameError**：`--json` 的写入在:563，跑完整场评测后崩在写盘前，结构化结果全丢（控制台行还在） |

结论：现在的问题不是"阈值调得不准"，而是**判据类型错了**（事件 vs 状态），加上**两套 judge + 两套阈值**。

## 2. 理论：三条边界

### 2.1 termination 的标准语义：terminated / truncated / 吸收态

Sutton & Barto 把 episode 的结束定义为进入**终止状态**：此后不再有回报，价值为 0（episodic 任务的 return 只累加到 T，即 `G_t = R_{t+1} + … + R_T`）[2]。Gymnasium 0.26 起把单一 `done` 拆成 `terminated`（任务自然结束：成功、失败、死亡）与 `truncated`（外部原因：时间上限、步数上限），并要求**只有 terminated 才把 bootstrap 置 0，truncated 必须 bootstrap**（`target = reward + (1-terminated)·γ·V(s')`）[3]。

这个区分不是 API 洁癖。Pardo et al. 证明：把时间上限当成终止会引入**状态别名**（相同的观测在不同剩余时间下价值不同）并破坏经验回放的有效性，正确做法是情形 (i) 把剩余时间放进观测、情形 (ii) 在截断处 bootstrap [4]。我们的 Part 2 属于情形 (i) 的变体：**超时在记分上是 fail，在 RL 语义上是 truncation**，两者必须分开实现 —— 记分用 judge 的 `finalize("timeout")→fail`，训练用 `truncated=True` + 一个小固定惩罚。

legged_gym 是这套惯例的教科书实现：`check_termination()` 里 `reset_buf = 任一 termination body 接触力 > 1 N`，`time_out_buf = episode_length_buf > max_episode_length`，`reset_buf |= time_out_buf`；训练侧把 `extras["time_outs"]` 单独送给算法用于 bootstrap，并且终端奖励写成 `reset_buf * ~time_out_buf`（超时不给终端奖励）[12]。MjLab（我们远程训练栈）沿用同一结构：`TerminationTermCfg.time_out` 标记某个 term 进 `_truncated_buf` 还是 `_terminated_buf`，`dones = truncated | terminated`，并把 `time_outs` 单独暴露 [16]。

对设计的直接约束有三条：
1. 任何 judge 判负的状态都必须是 `terminated`（不能是 truncated），否则 critic 会以为"失败之后还有未来"，价值被系统性高估。
2. 超时必须是 `truncated`，且**终值要与 fail 接近**（见 §3.4 的"拖延"陷阱）。
3. 不要在终止之后继续用同一个 episode 的数据训练（我们的 judge 一旦 `success/fail` 就 `return`，这是对的，见 [`comp_part2_judge.py`](../../../@20261019_locomotion/scripts/agent_scripts/comp_part2_judge.py):133）。

### 2.2 reward shaping 的安全区：potential-based shaping

Ng, Harada & Russell 1999 的定理：对任意势函数 `Φ: S → ℝ`，形如 `F(s,a,s') = γΦ(s') − Φ(s)` 的 shaping 项**不改变最优策略集合**，也不改变策略按回报的排序（policy invariance）[1]。这条定理的含义常被误读：它保证"不会把最优策略带偏"，**不保证**学得更快、也**不保证**你选的 Φ 是对的 —— 它只保证"你加的这项在数学上是可回收的"。

对我们最有用的其实是它的推导。把 shaping 从 t=0 累到 T−1：

```text
Σ_{t=0}^{T-1} γ^t · F_t = Σ γ^{t+1}Φ(s_{t+1}) − Σ γ^t Φ(s_t) = γ^T Φ(s_T) − Φ(s_0)
```

也就是说，**shaping 的总回报只取决于"起点势"和"终点势"**。这带来两个必须遵守的工程约束：
1. **Φ 必须在所有终止状态取 0**（Ng et al. 原文的要求）。若 Φ = x（前向进度），一次"在 x=1.5 m 处摔倒"的失败终止会额外拿到 `γ^T·1.5` 的正回报 —— 策略会学会"往前冲、摔得越远越好"。实践中不需要特判，只需做到**在终止的那一步不加 shaping 项**，等价于把终态势置 0。
2. **Φ 必须定义在任务相关的投影上，并且单调**。若 Φ = x 而不管 y 与是否在障碍上，等价于奖励"绕过去"——我们 `blackw_comp_blind_v0` 后期"策略出现绕过障碍退化"就是这类 reward 的典型产物（[`blackw-training-runs.md`](blackw-training-runs.md) 结果段）。正确的 Φ 是"沿赛道的投影进度 + 目标面高度"这类在障碍上仍然单调的量，且 lateral 越界要用终止（硬约束）而不是靠 Φ 的形状去"引导"。

若课程里 Φ 随难度变化（同一个 env 里第 3 档和第 4 档的目标不同），固定 Φ 的定理不再适用，要用动态势函数版本（Devlin & Kudenko 2012，让 Φ 也依赖时间/回合阶段，仍保持 invariance）[8]，或者给每档单独建 task。

### 2.3 为什么"硬规则只靠惩罚"不成立：reward hacking

Amodei et al. 把 reward hacking 列为五类具体安全问题之一："agent 找到最大化代理目标、但设计者并不想要的方式" [5]。Krakovna et al. 收集了大量 specification gaming 实例（含"利用物理漏洞""在评测指标上做局部最优"）[7]。

Skalse et al. 2022 给出了第一个形式化定义，并证明了关键结论：把 proxy 定义为"提高 proxy 期望回报永远不会降低 true 期望回报"即 unhackable；**在全体随机策略集合上，两个回报函数只可能在一个为常数时 unhackable**；对确定性策略和有限策略集虽然存在非平凡的 unhackable 对，但条件很窄 [6]。翻成工程语言：**任何"窄化"的代理目标（你的 reward）在足够强的优化器面前都会被找到漏洞；把硬规则放进 reward 就等于邀请策略来 hack 它**。

对我们的场景，这条定理的实用推论是"**惩罚不能替代判负**"：Part 2 的分数差很大（沟壑 30 cm = 300 分，高台 40 cm = 200 分），只要 `success_bonus` 的量级远大于"违规惩罚"，策略就会在 `r_task > λ·c` 时选择违规；把 λ 提到足够大，又会压死探索（策略干脆不靠近障碍）。这是**一个自由参数（λ）要同时承担两件互相矛盾的事**，必然有一头是错的。相反，把违规做成 termination，λ 就不存在了：违规那一步之后没有未来，价值函数自己会学会"不要进去"。

反过来也要警惕：**"能用惩罚解决的绝不要只靠惩罚"这句流行话是反的**，它原本说的是"能不用惩罚就不用"，而不是"硬规则也可以用惩罚"。准确版本是：**能用终止表达的硬规则，不要用惩罚表达；能用 shaping 表达的质量指标，不要用终止表达。** 两边都错在"用错了机制"，而不是"用了惩罚/终止"。

### 2.4 constrained RL / CMDP 视角：什么时候必须终止或屏蔽

CMDP（Altman 1999）把问题写成"最大化回报 + 约束 `J_c(π) ≤ d`" [10]。CPO 的动机陈述非常贴合我们的处境："很多应用里**同时指定回报和约束**比试图用回报函数去设计行为更方便" [9]。求解 CMDP 有三条路，对应三种实现：

| 处理方式 | 数学形式 | 什么时候用 | 我们的对应实现 |
|---|---|---|---|
| 拉格朗日/固定惩罚 | `max r − λc` | 约束是**软**的（可偶尔违反、代价可度量、允许折衷） | 姿态、平滑、力矩、速度跟踪 |
| 约束优化（CPO/PID-Lagrangian） | 显式对偶变量、按违反量调 λ | 约束是硬的但**可度量且可恢复**、且你愿意实现两套 critic | 暂不需要（复杂度/收益不划算） |
| 屏蔽/投影/终止（shielding） | 从可行集里选动作，或直接结束 | 约束是**硬**的、**违反即无效**、或不可恢复 | 摔倒、越界、轮子进槽、底盘触地 |

Dalal et al. 的"安全层"是第三类的连续版本：把动作投影回安全集，而不是靠惩罚把策略推离 [11]；Alshiekh et al. 的 shielding 则是离散版本 [17]。它们的共同前提是"**你有一个能判定安全集的模型**"——我们有（几何 + 接触），所以对"进槽""越界""摔倒"这类**状态可判定**的约束，正确做法是终止（离散、一次性），而不是惩罚（连续、可折衷）。

同时要注意 CMDP 的适用边界：**约束必须是"可度量的期望"**。像"四轮都落在目标面上"这种谓词，违反一次就作废整个 attempt，它不是"期望违反率 ≤ d"的问题，用 CMDP 建模反而绕远。判据分类的第一刀应该切在"这是谓词还是度量"上，第二刀才切在"谓词是否可恢复"。

### 2.5 腿足 RL 的工程惯例

| 系统 | termination 里放什么 | success 怎么处理 | 对我们的启示 |
|---|---|---|---|
| legged_gym / Rudin et al. 2022 [12] | 指定 body 接触力 > 1 N；超时单列（`time_out_buf`） | 没有显式 success，用 terrain curriculum 的"走够远就升级" | 摔倒/触地是终止，超时是截断，两者永不混用 |
| MuJoCo Playground [13] | `terminations` 配置项（接触、姿态、越界）+ `episode_length` | 任务是 tracking，success 用 reward 度量 | 终止项是**声明式配置**，不是散落在代码里的 if |
| Robot Parkour Learning [14] | 摔倒、出界 | 技能级目标是"越过某类障碍"，技能用课程分阶段训练，评测按到达目标区域的成功率统计 | "到目标区域"用区域判据，不用"过某条线" |
| BeamDojo [15] | 摔倒终止 | 稀疏 foothold 奖励 + 双 critic + 两阶段课程（先平地后实地形） | 稀疏成功信号必须配 dense 的"过程"信号，但不能把过程当成功 |
| MjLab（我们的训练栈）[16] | `bad_orientation`、`root_height_below_minimum`、`nan_detection`、`time_out` | 由 task 自己加 | 我们的 `official_platform_success` 是**自造的 reward 项**，不是 term —— 这是"success 只存在于 reward 里"的典型错误 |

共同的工程形状很稳定：**termination 是一组"状态谓词"，每条一个函数、一个布尔张量；成功与失败都是终止，但超时被单独标记；success 的"到没到"用区域/接触判据，进度用 reward 或课程**。我们没有理由发明第五种。

### 2.6 训练/评测一致性：judge 谓词就是 reward 谓词

"代理目标和真实目标不一致"在 RL 里有一个更一般的名字：objective mismatch —— 优化 A 却用 B 评价 [18]。放到比赛里，B 就是 judge。任何"训练里叫 success、评测里叫 fail"的状态，都是**给策略发了一张空头支票**：
- 训练 success 太松（x 过线、base_z 过阈）→ 策略学会"过线姿势"，评测 0 分（我们的 76% → 0%）。
- 训练 fail 太松（可恢复也终止）→ 策略学会"不敢靠近"，评测也 0 分，但你连"它其实能做到"都看不到。

唯一稳的做法：**judge 与训练共用同一份谓词实现**。具体到我们：`gen_part2_official_levels.py` 已经把每档的 `judge` 元数据写进 `part2_official_levels.json`（[`gen_part2_official_levels.py`](../../../@20261024_blackw/scripts/gen_part2_official_levels.py):151-205、:258-273），训练 task 只要在启动时读同一个 JSON、用同一组谓词函数构造 termination 与 reward，漂移就被结构性地消掉了。

## 3. 判定规则（可直接照做）

### 3.1 六问决策

按顺序问，第一个"是"就是归属：

| # | 问题 | 是 → 归属 |
|---|---|---|
| Q1 | rules/judge 会不会把它记成 fail？ | **termination（fail）**，且必须同时是 judge 的 fail 事件，同一个函数 |
| Q2 | 它是不是不可恢复（吸收态：翻倒、掉进槽、底盘落地、出界无法回来）？ | **termination（fail）**；即使 judge 不判负也要终止（否则 critic 在学"死局里的未来"） |
| Q3 | 它可恢复，但恢复之后 judge 仍然判这次 attempt 无效（越过线又走回、单轮短暂离面）？ | **termination（fail）** + 阈值带滞回/去抖；不要指望策略"自己改回来" |
| Q4 | judge 用它算分（难度、成功）？ | 它是 **success 谓词**的一部分：终态 + hold，不是 shaping |
| Q5 | 它是连续可度量的质量指标（姿态、平滑、力矩、速度跟踪、进度）？ | **reward shaping**；进度类用 PBRS（§2.2），风格类用有界惩罚 |
| Q6 | 它是机构/物理本身的限制（力矩上限、关节限位、轮速上限）？ | **用 clamp/saturation 建模**，既不终止也不惩罚（惩罚会让策略"怕用力"或"贴着上限"） |

两个常见错误各对应一条：
- **假终止**：Q2/Q3 都不成立却终止（例如"3 s 没进展就判 fail"）→ 人为 false negative，策略学会保守。正确做法是 `stuck` 只作为 **truncation**（bootstrap + 小惩罚），或者干脆不终止、让超时兜底。
- **假成功**：把 Q5 的量当成 Q4（`x > goal_x`、`base_z > 阈值`）→ specification gaming。正确做法是把"到没到"写成接触/区域谓词。

### 3.2 谓词形式化：状态、而非事件

把每个障碍写成四元组，全部是**状态谓词**（对当前帧的 `s` 求值），不是"跨过某个坐标"：

```text
P_support(i, S) : 第 i 个轮子与支撑面集合 S 有接触（或轮底 z ∈ [z_S−0.01, z_S+0.01] 作为几何回退）
P_clear(i, S')  : 第 i 个轮子不与任何更低的面 S'（地面、槽底、上一级台阶）接触
P_region(i, R)  : 轮心 xy 落在区域 R 内（含 0.05 m 内缩）
P_pose          : |roll|,|pitch| ≤ θ_max，|ż_base| ≤ v_z_max
SUCCESS         : ∀ i∈{FL,FR,RL,RR}: P_support(i,S) ∧ P_clear(i,S') ∧ P_region(i,R) ∧ P_pose，连续 hold T_h
```

关键在 `∀ i`（四轮）与 `T_h`（连续 hold）：只要有一个轮子不满足，谓词为假，计时清零。这就自动排除了"前轮搭台、后轮悬空"的瞬态，也正是用户 (a) 要求的东西。现有的 `_cond` 用的是 `∃ i`（`"platform" in tags` 只要任一轮），这是判据类型错误的最小可修点（[`comp_part2_judge.py`](../../../@20261019_locomotion/scripts/agent_scripts/comp_part2_judge.py):110）。

### 3.3 hold、滞回与灰区

- **hold 时长取 0.30 s（50 Hz 下 15 步）**。理由：单帧接触在 5 ms 物理步长下可能只是一次擦碰；0.30 s 足够滤掉"跳过去擦一下台边"和"被撞一下弹到台面上"，又不至于要求"站定"（1.5 m 平台上以 0.5 m/s 走完要 3 s，0.30 s 只占 1/10 行程，不会误杀"滚过去"）。现有 `hold_s=0.2` 建议提到 0.30，并在标定集上对比 0.2/0.3/0.5 的判定差异后再冻结。
- **滞回（hysteresis）**：进入成功判据用**收紧**的阈值（lateral |y| ≤ 0.65、区域内缩 0.05 m），判负用**放宽**的阈值（|y| > 0.75、轮底低于面 0.10 m）。中间 10 cm / 5 cm 是死区：既不算成功也不算失败，状态保持原样。没有死区，机器人正卡在边界上时会每帧翻转，hold 永远攒不满，判负也会误触发。
- **灰区（既不能判成功也不能判负）**：行为是"继续跑"，不是"猜一个"。灰区里训练环境既不给 success bonus 也不终止，让 timeout 兜底。这一点必须写进协议：灰区占比是 judge 质量的直接指标，占比高说明阈值没标定好。
- **吸收态的两个方向不对称**：success 一旦成立就锁存（规则就是"上到平面即得分"，之后掉下来不改变已得分），所以 success 谓词必须"充分"；fail 一旦成立也锁存（4 次机会里这次已经废了）。**锁存意味着谓词的召回率比精确率更重要**：宁晚判 success，不可早判。

### 3.4 两个必须避开的数值陷阱

**陷阱一：fail 与 timeout 的终值差**。若 fail 给 −10、超时给 0，策略会学会"在障碍前磨蹭到超时"（拖延是一种典型的 specification gaming，且完全合法地规避了惩罚）。做法：超时用小固定惩罚（≤ 0.1×`success_bonus`）+ `truncated=True`（保留 bootstrap），并且**在 judge 里超时也记 fail**，让记分口径一致。

**陷阱二：shaping 在终止步的支付**。按 §2.2 的推导，进度势在失败终止时会**倒付奖励**。实现上统一处理：`if terminated: shaping = 0`，不要靠"Φ 恰好为 0"。

## 4. 参考来源

| # | 来源 | 用途 |
|---|---|---|
| [1] | Ng, Harada, Russell, *Policy Invariance Under Reward Transformations*, ICML 1999 — [PDF](https://people.eecs.berkeley.edu/~pabbeel/cs287-fa09/readings/NgHaradaRussell-shaping-ICML1999.pdf) | PBRS 定理与 `Φ(终态)=0` 的要求 |
| [2] | Sutton & Barto, *Reinforcement Learning: An Introduction*, 2nd ed. — [书页](http://incompleteideas.net/book/the-book-2nd.html) | episodic 任务的终止状态定义 |
| [3] | Gymnasium, *Migration Guide*（`terminated` / `truncated` 与 bootstrap）— [链接](https://gymnasium.farama.org/introduction/migration_guide/) | 终止语义的现行标准 |
| [4] | Pardo et al., *Time Limits in Reinforcement Learning*, ICML 2018 — [arXiv:1712.00378](https://arxiv.org/abs/1712.00378) | 时间上限必须 bootstrap，否则状态别名 |
| [5] | Amodei et al., *Concrete Problems in AI Safety*, 2016 — [arXiv:1606.06565](https://arxiv.org/abs/1606.06565) | reward hacking 的问题分类 |
| [6] | Skalse et al., *Defining and Characterizing Reward Hacking*, 2022 — [arXiv:2209.13085](https://arxiv.org/abs/2209.13085) | 任何非常数代理在一般策略集上都不可能 unhackable |
| [7] | Krakovna et al., *Specification gaming: the flip side of AI ingenuity*, DeepMind 2020 — [链接](https://deepmind.google/blog/specification-gaming-the-flip-side-of-ai-ingenuity/) | 真实 gaming 案例集 |
| [8] | Devlin & Kudenko, *Dynamic Potential-Based Reward Shaping*, AAMAS 2012 — [ACM](https://dl.acm.org/doi/abs/10.5555/2343576.2343638) | 课程里势函数随时间变化时的 invariance |
| [9] | Achiam et al., *Constrained Policy Optimization*, ICML 2017 — [arXiv:1705.10528](https://arxiv.org/abs/1705.10528) | "同时指定回报与约束"胜过"用回报设计行为" |
| [10] | Altman, *Constrained Markov Decision Processes*, 1999（ISBN 9780849303821）— [Google Books](https://www.google.com/books/edition/Constrained_Markov_Decision_Processes/3X9S1NM2iOgC) | CMDP 形式化 |
| [11] | Dalal et al., *Safe Exploration in Continuous Action Spaces*, 2018 — [arXiv:1801.08757](https://arxiv.org/abs/1801.08757) | 约束用投影/安全层实现，而非只靠惩罚 |
| [12] | Rudin et al., *Learning to Walk in Minutes*, CoRL 2021 — [arXiv:2109.11978](https://arxiv.org/abs/2109.11978)；代码 [legged_robot.py](https://github.com/leggedrobotics/legged_gym/blob/master/legged_gym/envs/base/legged_robot.py) | `check_termination` / `time_out_buf` / `_reward_termination` |
| [13] | Zakka et al., *MuJoCo Playground*, 2025 — [arXiv:2502.08844](https://arxiv.org/abs/2502.08844) | 终止项声明式配置 |
| [14] | Zhuang et al., *Robot Parkour Learning*, CoRL 2023 — [arXiv:2309.05665](https://arxiv.org/abs/2309.05665) | 目标区域式 success + 课程 |
| [15] | Wang et al., *BeamDojo*, RSS 2025 — [arXiv:2502.10363](https://arxiv.org/abs/2502.10363) | 稀疏成功 + dense 过程信号 + 两阶段课程 |
| [16] | MjLab — [terminations.py](https://github.com/mujocolab/mjlab/blob/main/src/mjlab/envs/mdp/terminations.py)、[termination_manager.py](https://github.com/mujocolab/mjlab/blob/main/src/mjlab/managers/termination_manager.py) | 我们训练栈的 `time_out` 标志与 terminated/truncated 分离 |
| [17] | Alshiekh et al., *Safe RL via Shielding*, AAAI 2018 — [arXiv:1708.08611](https://arxiv.org/abs/1708.08611) | 屏蔽/终止作为硬约束实现 |
| [18] | Lambert et al., *Objective Mismatch in Model-based RL*, 2020 — [arXiv:2002.04523](https://arxiv.org/abs/2002.04523) | "优化的目标 ≠ 评价的目标"的一般化 |

## 5. Part 2 六障碍设计表

几何基线（官方 `map.xml` + [`part2-terrain-audit.md`](part2-terrain-audit.md)）：高台 1.5×1.6 m 单块；楼梯 6 级上（踏面 0.30 m）+ 0.8 m landing + 6 级下；斜坡 2 m 水平 × 1.4 m 宽，升高 2·tanθ，顶部 0.8 m 平台；高墙 1.4 m 宽 × 0.12 m 厚；沟壑净宽 0.10/0.20/0.30 m、深 0.30 m、通道 1.4 m、进/出各 1 m 楔形坡；梅花桩 0.2 m 方块 + 0.8 m 平台。机器人：轮半径 `r = 0.103 m`、轴距 0.425 m、轮距 0.399 m、名义站立基座高 ≈ 0.524 m（默认位姿实测：轮心 z=0.0794 @ trunk 0.5）。

| 障碍 | 成功谓词（终态 + hold 0.30 s） | 失败/终止（judge fail ⟺ training terminated） | 只做 reward shaping | 训练落地（MjLab term） |
|---|---|---|---|---|
| 高台 10/20/30/40 | 四轮 `P_support(platform_<h>cm)` ∧ 四轮 `P_clear(地面/低面)` ∧ 横滚与俯仰 ≤ 15°；不再用 base z | 翻倒（tilt>75° 或 `base_z − min轮底 < 0.25`）；从侧面掉下（四轮全部离开台面且 base 下落 > 0.15）；lateral 越界 > 0.75；超时 | 进度势 `Φ = −dist(x, 平台中心)`（终止步置 0）；轮-台接触的 dense 小奖励；`lin_vel_z`、`orientation`、`action_rate`、`torque` 惩罚 | term `platform_four_wheels_on_top`；rew `success_bonus`（边沿触发一次）+ `progress_x`(PBRS) + `wheel_on_target` |
| 楼梯 10/15/20/30 | 主判据：四轮落到远端地面（`x > 末级 + 0.20`、轮底 ≤ 0.03）且**曾有两轮同时接触 landing/最高级**（爬升证据）；备选宽口径：四轮在 landing 上（须在冻结协议前定，见 §7.2 第 1 条） | 翻倒；lateral 越界；从侧面跌下台阶（base 下落 > 0.15）；超时 | 逐级高度势 `Φ = 负(剩余级数)`；`stumble`（轮撞竖面）惩罚；`feet_air_time` 类步态项 | term `stairs_far_ground` + `stairs_landing_seen`；rew `success_bonus` + `height_progress`(PBRS) |
| 斜坡 20/30/35/45 | 四轮 `P_support(顶部平台)` ∧ 轮底 ≥ `rise_z − 0.02` ∧ lateral 在坡宽内 | 翻倒（45° 常见后翻）；侧滑出坡宽 > 0.75；超时 | 高度势 `Φ = z_base`（仅在坡面上单调）；`orientation`（pitch 期望值随坡度）；`lin_vel_z`；轮滑惩罚 | term `slope_on_top_platform`；rew `success_bonus` + `height_progress`(PBRS) + `slope_pitch_tracking` |
| 高墙 10/20/30/40 | 四轮落到墙后地面（`x > wall_x + 0.35 + 半轴距`、轮底 ≤ 0.03）∧ **至少一轮曾踩到墙顶**（`轮底 z ≥ wall_h − 0.01` 且距墙面 x 偏差 ≤ 0.30 m）∧ lateral 在 1.4 m 内 | 翻倒；撞墙后横向跌落；lateral 越界；超时（**不把"机身碰墙"判负**：Part 2 没有 Part 1 的 1/2 足接触规则） | 爬升势 `Φ = min(z_base, wall_h+0.10)`；`stumble`；`collision`（仅机身重碰，小权重） | term `wall_wheels_past` + `wall_top_touched`；rew `success_bonus` + `climb_progress`(PBRS) |
| 沟壑 10/20/30 | **四轮** `x_i > far_x + 0.05` ∧ 轮底 ≥ `plateau_z − 0.02` ∧ lateral ≤ 0.65，连续 0.30 s（§6 详述） | 任一轮底 < `plateau_z − τ(w)` 在槽窗内（τ 见 §6）；接触 `trench_bottom`；`base_z < plateau_z − 0.15`；lateral > 0.75；超时 | 跨越势 `Φ = −dist(x, far_x)`（终止置 0）；轮速/滑移；`lin_vel_z` | term `gap_wheels_past` + `gap_wheel_drop` + `gap_bottom_contact`；rew `success_bonus` + `cross_progress`(PBRS) |
| 梅花桩（200 分） | 四轮落在出口平台（`x ≥ goal_x_min`、轮底 ≥ `top_z − 0.02`）并 hold；过程中不允许轮底落到桩间地面 | 掉到桩间（`cube_x_range` 内任一轮底 < `top_z − 0.15` 即 0.05）；`base_z < 0.55`；翻倒；超时 | 桩面接触计数（稀疏 foothold 的 dense 代理）；`Φ = −dist(下一个桩)`；步态平滑 | term `plum_on_exit_platform` + `plum_dropped`；rew `success_bonus` + `foothold_bonus` + `progress`(PBRS) |

逐条备注：

- 高台的"四轮上台"在 1.5×1.6 m 的台面上是宽松的（机器人占地 0.425×0.399 m），不会误杀贴边站稳的姿态；这正是"四轮判据"在本场地上好用的原因 —— 平台远大于足迹。
- 楼梯是六个障碍里唯一**必须先定口径**的：规则只写"通过台阶"，官方几何是"上 6 级 + landing + 下 6 级"。按字面"通过"应当穿过到远端；按"最弱可辩护读法"只需上到 landing。两种读法给分完全相同（分数只看档位），所以**判据选哪个只影响可辩护性与训练难度**，不影响得分期望；建议 judge 用"到 landing"（宽松、不易被判不诚实），训练 success 与之相同，另把"下到远端"做成 progress 奖励而不是第二个 success。
- 高墙的"踩到墙顶"证据对 10 cm 档冗余（墙高 < 轮半径，轮子本来就滚过去了），对 30/40 cm 档是必要的：没有它，"贴着墙根绕过去"也会满足"四轮落到墙后地面"。判据里要同时用"几何过线"和"接触证据"，缺一不可。
- 梅花桩的"掉下去"必须在 `cube_x_range` 内判，否则出口平台到地面的正常下坡会被误判。
- **不要把 Part 1 的"1/2 足接触地面即失败"搬进 Part 2**：Part 2 规则只写"越过/攀爬通过/成功上到平面"，没有任何足接触比例约束（[`team-race-2026.md`](../reference/team-race-2026.md) §3.2）。搬过来就是纯 false negative。

### 5.1 训练环境怎么落地（MjLab）

| 项 | 做法 |
|---|---|
| term 声明 | 每个谓词一个函数（`(env) -> Bool[T_env]`），成功与失败都进 `terminations`，`time_out=True` 只给超时项；MjLab 的 `TerminationTermCfg.time_out` 决定进 `_truncated_buf` 还是 `_terminated_buf` [16] |
| success bonus | 同一个谓词在 reward 里做**边沿触发**（`succ & ~succ_prev`），一次只发一次；不要在终止后继续发 |
| 进度 | 用 PBRS：`r += γΦ(s') − Φ(s)`，`terminated` 步不加；Φ 必须是"沿赛道投影的单调量"，否则会奖励绕行（§2.2） |
| 课程 | 按**成功率门控**升档（连续 N 次成功或成功率 ≥ 95% 再升），不要用"走够远"的距离课程（legged_gym 的 terrain curriculum 是给 rough 用的，不是给"必须越过"的任务用的）[12] |
| 记分 | 训练日志里的 `success` 必须由 judge 的同一份 spec 产出；`docs`/答辩里的分数只能来自 evaluator |
| 观测 | 不要把 `base_z` 之类判据量塞进 actor（合规红线：actor 只允许 IMU+编码器，见 [`team-race-2026.md`](../reference/team-race-2026.md) §2.2）；判据量只进 critic/日志 |

## 6. 沟壑判据：`max 轮子下降深度 > min(1/2·沟壑深度, 轮子半径)` 是否合理

### 6.1 结论

**合理，方向对，可以直接用；但有三个必须补的限定**，否则会在 20 cm 档误判或漏判。

1. **基准必须是「槽口两侧的台面高度」**，不是基座高度、不是全局地面高度：`drop_i = plateau_z − (wheel_hub_z_i − r)`。用 `hub_z − r` 作轮底是保守的：轮子倾斜 θ 时真实最低点是 `hub_z − r·√(1−u_z²)`，θ=10° 时误差 1.5 mm，可忽略。
2. **窗口必须覆盖整个槽区并持续监测到 success 之后**：`x_i ∈ [near_x − 0.06, far_x + 0.06]`（现有实现就是这个窗口，保留）；且 success 一旦判出就锁存，所以 success 只能等**四轮都过 far 边**才发（§6.3）。现在的问题是 success 由 base 过线触发（[`comp_part2_judge.py`](../../../@20261019_locomotion/scripts/agent_scripts/comp_part2_judge.py):122），锁存后掉进去不再计 —— 这正是用户 (b) 看到的现象。
3. **阈值要带宽度项**：用户公式里的 `1/2·沟壑深度` 在官方几何下**恒被 `r` 压住**（深度恒 0.30 m ⇒ 0.15 > r=0.103），三档都退化成 τ=0.103。真正决定"轮子是否只是被两个槽沿架住"的是**净宽**，见下表。

### 6.2 几何推导

轮子（半径 r）横跨净宽 w 的槽、被两侧槽沿架住时，轮底最多下降：

```text
d_sup(w) = r − sqrt(max(r² − (w/2)², 0))
```

| 档位 w | w/2 | `d_sup(w)` | 用户阈值 `min(0.5h, r)` | 余量 `τ − d_sup` | 判定含义 |
|---|---|---|---|---|---|
| 0.10 m | 0.05 | **0.0130 m** | 0.103 m | 0.090 m | 轮子跨得过去；只有明显陷进去（>10 cm）才判负 |
| 0.20 m | 0.10 | **0.0783 m** | 0.103 m | 0.025 m | w≈2r，轮子"刚好一轮直径"；被架住时已下沉 7.8 cm，余量只有 2.5 cm |
| 0.30 m | 0.15 > r | 无（架不住） | 0.103 m | — | 轮子必然掉下去；任一明显下降都该判负 |

三点解读：
- **公式的物理含义是"两个独立充分条件的较紧者"**：(i) 下降超过槽深一半 ⇒ 已到槽底一半；(ii) 下降超过一个轮半径 ⇒ 轮子半浸。取 min 即"任一条成立就算掉进去"。这个取法是保守的（对判负有利），方向正确。
- **官方深度恒为 0.30 m，所以 (i) 永远不生效**，实际阈值就是 `τ = r`。要写进文档/代码注释，否则后人以为在做"半深"判定。
- **20 cm 档是唯一需要小心的一档**：0.0783/0.103 只差 2.5 cm，接触柔度、轮子压扁、`hub_z − r` 的近似都可能吃掉 1 cm 量级。这不是"阈值取错了"，而是"这一档的几何本来就贴着极限"——w=0.2 ≈ 2r 意味着**滚过去在物理上几乎不可能，必须跳/跨**。

### 6.3 建议的判定与实现

- **fail（任一成立）**：① 槽窗内任一轮 `drop_i > τ`，`τ = min(0.45·h, r) = 0.103`；② 任一 geom 接触 `trench_bottom`（精确信号，不需标定）；③ `base_z < plateau_z − 0.15`（真的塌下去了）；④ lateral > 0.75；⑤ 超时。
- **success**：`∀ i: x_i > far_x + 0.05 ∧ wheel_bottom_i ≥ plateau_z − 0.02 ∧ |y_i| ≤ 0.65`，连续 hold 0.30 s；且此前未触发任何 fail。**"四轮全过 far 边"是这条判据的核心**：它同时覆盖了"前轮过去了但后轮掉进槽"的情况（用户 (b) 的 bug）。
- **更严格的可选版本**（若担心"轮子明显陷进槽但没到 `r`"）：`τ(w) = min(r, d_sup(w) + 0.02)`，即 0.033 / 0.098 / 0.103。10 cm 档从 0.103 收紧到 0.033（该档 0 分，只作课程，收紧无害），20/30 cm 基本不变。
- **实现位置**：`eval_blackw_part2.py:170-181` 已是这个形状（`floor_z = plateau_z − allowed_drop`、`min_wheel_z`、窗口 ±0.06），只需把 `allowed_drop` 从常数 0.05 换成 `min(0.45*h, r)`、并**改成逐轮**而不是只喂最低那一只（`lowest_wheel()` 在:347-355）。`comp_part2_judge.py` 侧要把 `trench_bottom` 之外再加"轮底阈值"这条（现在只有接触判据，10 cm 档永远不触发）。
- **阈值不是拍脑袋**：`τ` 的真实标定数据是"成功穿越时的 `max_i drop_i` 分布"。跑 20 次成功穿越（含人工/脚本轨迹），看 p95；若 p95 已接近 0.08（20 cm 档），说明当前策略是"擦着过去"的，应把 τ 提到 0.10 并接受更严的判负，而不是反过来放宽。

### 6.4 "四轮离开障碍区域后落到目标面"怎么定义（含 hysteresis）

```text
enter(i)  = P_support(i, S_target) ∧ P_clear(i, S_lower) ∧ |y_i − y_lane| ≤ 0.65
SUCCESS   = ∀i enter(i) 连续 0.30 s
violate   = |y_base − y_lane| > 0.75 ∨ (出现过 enter 后，四轮全部 P_clear(S_target) 且 base 下落 > 0.15)
```

- **进入用严阈值（0.65/0.05 内缩），判负用宽阈值（0.75/0.10）**，中间是死区；死区内不改变状态、不重置 hold。没有死区时，机器人卡在边界会让 hold 每帧清零、success 永远到不了，或者判负反复抖动。
- **hold 语义是"连续"**：中断即清零（现有实现已如此，[`comp_part2_judge.py`](../../../@20261019_locomotion/scripts/agent_scripts/comp_part2_judge.py):199），不是累计。累计会在"反复上上下下"时给出成功。
- **接触 vs 几何的双通道**：接触是主判据（MuJoCo 接触列表可靠），几何 `|wheel_bottom − z_S| ≤ 0.01` 是回退（接触在单帧可能缺失）。两个通道在标定集上必须给出相同判定，否则先修接触分类（`run_part2_judged_eval.py:74-101` 的 `foot_tags` 已经把每腿接触的 geom 打上 `platform/stair/slope/plum/trench_bottom` 标签，可直接复用）。
- **锁存与"回退"**：`enter` 成立满 0.30 s 后 success 锁存；锁存之前任何一帧不满足就清零。不要把"离开目标面"建成 fail —— 那是合法的"没站稳又退回去"，judge 应该继续等（灰区），而不是判负。

## 7. 对我们当前实现的具体改动建议

按优先级排序，全部只改判据/训练信号，不改地形与策略。

| # | 文件:行 | 现状 | 改成 | 优先级 |
|---|---|---|---|---|
| 1 | [`eval_blackw_part2.py`](../../../@20261024_blackw/scripts/eval_blackw_part2.py):547 | `GAP_Z_TOL_M` 未定义 | 删掉该字段，或改成 `GAP_MAX_WHEEL_DROP_M` 并在 payload 里同时给 `detail["gap_allowed_drop"]` | P0（现在每次评测的 JSON 都丢） |
| 2 | [`comp_part2_judge.py`](../../../@20261019_locomotion/scripts/agent_scripts/comp_part2_judge.py):105-127 | platform/stairs/slope 用 `base_z ≥ top_z+0.38` + `∃轮触目标面` | 改成 `∀ 四轮 P_support(target) ∧ P_clear(lower) ∧ P_pose`，`hold_s` 0.30 | P0（用户 (a)） |
| 3 | 同上:121-123 | gap success 用 `gap_crossed`（base 穿 far 边） | 改成 `∀ 四轮 x_i > far_x+0.05 且轮底 ≥ plateau_z−0.02`，hold 0.30 | P0（用户 (b)） |
| 4 | 同上:139-140、180-183 | gap fail 只有 `trench_bottom` 接触 | 增加逐轮 `drop_i > min(0.45h, r)` 与 `base_z < plateau_z−0.15` | P0（10 cm 档现在永不触发） |
| 5 | 同上:172-179 | 摔倒用绝对 `base_z < 0.15` | 增加相对判据 `base_z − min_i(wheel_bottom_i) < 0.25`，`0.15` 保留为全局兜底 | P1（站在 0.3 m 平台上趴窝现在不算失败） |
| 6 | 同上:189-199 | `hold_s` 默认 0.2 | 提到 0.30，并在标定集上对比 0.2/0.3/0.5 | P1 |
| 7 | [`eval_blackw_part2.py`](../../../@20261024_blackw/scripts/eval_blackw_part2.py):87-215 | 与 V2 重复实现，阈值不同（`z_margin=0.35` vs `+0.38`） | 删掉 `Part2OfficialJudge`，改为 `from comp_part2_judge import Part2JudgeV2`（已在:52 引入 `score_for_level`） | P1（两套 judge = 两个分数） |
| 8 | 同上:347-355、427-429 | 只把最低轮的 `(x,z)` 传给 judge | 传四轮的 `(x,y,z)`（`list[tuple]`），judge 侧用 `∀`/`∃` 两种量化 | P1（"四轮"判据的前置条件） |
| 9 | [`gen_part2_official_levels.py`](../../../@20261024_blackw/scripts/gen_part2_official_levels.py):151-205 | `z_margin=0.35`、`climb_z_min=0.5+0.2h`、`z_cross_min=plateau+0.28` | 换成上面表里的谓词参数（`support_z`、`τ(w)`、`hold_s`、`lane`），并把 `base_ref_z` 从 0.5 校正为 0.524（默认位姿下轮底在 −0.024 m，spawn 0.5 会陷地 2.4 cm） | P2 |
| 10 | 训练 task（远程 MjLab） | `official_platform_success = x∈[1.9,3.1] 且 root_z≥0.72` 是 **reward 项**，不是 termination（[`blackw-training-runs.md`](blackw-training-runs.md) §HIM） | 删掉该 reward 项；把同一谓词做成 `terminations` 里的 `platform_four_wheels_on_top`，reward 只留边沿触发的 `success_bonus` | P0（这是"success 只活在 reward 里"的根因） |
| 11 | 训练 task | `competition_progress` / `competition_goal` 等 x-进度项 | 保留为 PBRS 但改成 `γΦ(s')−Φ(s)`、`terminated` 步清零；lateral 用终止（已有 `lane termination`） | P1 |

### 7.1 验证计划（改完必须过的四关）

1. **单元测试**：构造合成轨迹（四轮全上台 / 两轮上台悬空 / 前轮过 far 边后后轮进槽 / 轮子擦槽沿 1 cm / 轮子陷 5 cm / 轮子触底），断言 judge 的 `status` 与 `reason` 符合上表；`comp_part2_judge.py` 已有 `run_self_test()`（:224-341），把上面六条加进去。
2. **实跑回放**：用已有 rollout 视频逐帧对判据打点，要求"判 success 的那一帧"与"人眼认定的上到平面"一致，误差 ≤ 0.3 s；判 fail 的帧必须能看到对应的几何事实。
3. **双实现交叉**：新判据与独立第二实现（盲写）在同一批轨迹上给出一致结论（G1 审计要求，见 [`competition-judge.md`](competition-judge.md) §6）。
4. **训练/评测同源**：拿 judge 的 spec 在训练环境里跑 100 episode，逐 episode 比对 `env` 记录的 success/fail 与离线 judge 的结论，必须 100% 一致；不一致就是漂移，先修漂移再训练。

### 7.2 需要用户确认

1. **楼梯口径**：`通过台阶` = 上到 landing（宽松）还是穿过到远端地面（严格）？两者给分相同，但影响"可辩护性"与训练难度；建议前者 + 把"下到远端"做成 progress。
2. **沟壑判据的严格度**：用 `τ = min(0.45h, r) = 0.103`（"轮子半浸才判负"，与你的公式一致）还是 `τ(w) = min(r, d_sup(w)+0.02)`（"明显陷进槽沿就判负"，20 cm 档不变、10 cm 档更严）？建议先用前者跑标定集、把逐轮 `max drop` 记进 `detail`，再据此决定是否收紧。
3. **高台"四轮"是否要求同时接触**：瞬时四轮同时接触在高速滚下会偶发缺帧，`hold 0.30 s` 已经覆盖；若标定发现缺帧严重，再放宽成"任意 0.30 s 窗口内 ≥90% 的帧满足"（这会引入新的调参面，非必要不做）。
