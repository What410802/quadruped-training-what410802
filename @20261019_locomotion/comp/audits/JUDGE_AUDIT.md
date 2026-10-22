# Judge Audit（G1：评测器独立审计）—— 2026-10-22

```text
reviewer:   codex / gpt-6-astra / ultra / threadId=未由 bridge 回传（记录于会话日志）/ date=2026-10-22
scope:      规则原文（队内赛.pdf 全 4 页）+ docs/reference/team-race-2026.md + comp/CONTRACT.*
            + comp/eval/_protocol.md + docs/training/eval-protocol.md + judge 源码（事件级/接触级）
            + 场地 XML/judge zones + Part2 场地 + 样板 eval 三件套 + 标定集目录（空）
            + deployment_audit.py + agent 视觉自检清单
audit_mode: fresh thread, read-only, 路径 only（未给执行者摘要/结论）
overall:    FAIL
```

> 本文件是执行者对 reviewer 响应的结构化整理；判定与证据均来自 reviewer，执行者只做录入。
> 原始响应较长，按 reviewer 输出顺序整理如下（逐项 verdict 与证据行号保留原样）。

## 1. 被审对象哈希（`HASHES.json`）

| 对象 | sha256（前 16） |
|---|---|
| CONTRACT.json | `d58ad1af44043566` |
| eval/_protocol.md | `e477ab0dd3def6fd` |
| part1_event_judge.py | `546dbacd29465cb6` |
| part1_judge.py | `b398a39d25a21542` |
| part1_eval_scene.xml | `e7b654ad1bcf4638` |
| judge_zones.yaml | `53b1f6c0a9bae0cb` |

## 2. 确定性预检（executor 跑，Type-A，供审计参考）

- 工具 `--self-test`：全部通过；`comp_score --validate-only`：3 行 `diagnostic` 通过。
- `comp_compliance`：PASS（45 维 actor、20 N·m ≤ 25/60、无禁用传感器名）；**注意** reviewer 指出该证据是
  import 时整理的自报 data，不能替代运行时观测（见 D1/E1）。
- 标定集：`comp/eval/_calibration/` 只有 README，无标签。

## 3. 逐项审计结论（来自 reviewer）

### A. 规则忠实性：FAIL

| 障碍 | verdict | 关键证据 | 最小修复 |
|---|---|---|---|
| 直角绕杆 | FAIL | `part1_event_judge.py:91` 只要求依次接近杆心，无 S 形/交替绕侧/起终点圆/拐角必达区；两点采样即可收齐 4 checkpoint 得 100 | 记录起点、每杆有向绕侧、拐角与终点完整序列，支持两个合法方向 |
| 砂砾碎木坑 | FAIL | `part1_event_judge.py:76` 只查矩形内 `x>6.3`，无短边进入/离开证据；`part1_eval_scene.xml:27` 实际只有两个固定平顶箱体，无碎石/坑底 | 补实际障碍几何、合法短边线段与进入-跨越-离开状态 |
| 高墙 | FAIL | `part1_event_judge.py:61` 不检查越/爬；绕到另一侧再横向进入判定区即 100 | 记录墙前进入、有效墙段上方穿越、另一侧完整离开，排除绕行 |
| 限高杆 | FAIL | 规则（PDF 表 2）只规定"从下方穿过、杆掉落失败"；`part1_judge.py:78` 却把碰柱/碰梁都判失败；`part1_eval_scene.xml:43` 横杆是固定 world geom，根本不会掉落；`part1_event_judge.py:58` 不检查下穿与整机通过 | 实现可掉落横杆与落杆检测；完整通过后再确认成功；轻触/碰柱先向主办方确认 |
| T 字形台阶 | FAIL | `run_part1_judged_rollout.py:42` 每帧重建高度集合、按 geom 中心高度分类，不看顶面；`part1_event_judge.py:89` 要求当前帧同时出现三种高度 → 逐级接触历史丢失、上下同高台阶被合并 | 为每级顶面建独立 `step_id`，按所走支路累计接触历史，验证上下 + 回地面 |
| 斜坡 | FAIL | 坡面长边沿世界 y（`part1_eval_scene.xml:113`），judge 却以 `x>5.7` 判成功（`part1_event_judge.py:80`），无坡面接触与长边距离 | 按坡面局部坐标累计有效行走距离，落实两侧斜坡计分口径 |
| 方墩木桥 | FAIL | `part1_event_judge.py:66` 只查出口坐标，无起点平台/经桥/对侧平台证据 | 为平台和桥面建标签，记录完整跨越与持续 ground 失败 |
| 窄带木桥 | FAIL | `part1_event_judge.py:71` 同上，只有位置阈值 | 同上，并支持反向合法通过 |
| Part 2 六项 | FAIL | 高台/楼梯/斜坡/高墙/沟壑/梅花桩均无完整 evaluator、起点、成功判定；`_protocol.md:67` 自认缺失 | 补六类规则判定、难度测量与稳定重复要求 |

- Part 2 梅花桩**几何单项 PASS**：`part2_plum_eval_scene.xml:8` 的 6 块 200 mm 方块、800 mm 平台、间隙、总长 3500 mm 与 PDF 第 4 页图相符（但这不构成能力证据）。
- A2 方向/顺序 FAIL：墙/门洞 y 法向、方墩 x、窄带 y 主轴判断正确，但无有向跨越历史；T 台阶只接受 `y>-2.1`，漏掉 +x 合法侧支路；斜坡把上坡方向误当长边方向。`CONTRACT.md:29` 把方墩称 A、窄带称 B，与 PDF 第 1 页图 1 标注相反。
- A3 计分 FAIL：`part1_event_judge.py:50` 只有整项 100，`:105` 最多 800，无返回启动区 100 与 T 台阶部分分（表 3 的 75/50 对应需先确认）；**Part 2 门槛错误**：`CONTRACT.json:127,155,183` 把 `(0,0)` 接到首个计分阈值，`comp_score.py:57` 实测高台 5 cm=5 分、楼梯 5 cm=5 分、斜坡 10°=5 分，而 PDF 第 3 页应为 0 分；`run_part1_judged_rollout.py:130` 每轮汇总八项状态，区域重叠时可能混分/重复累计。
- A4 尝试/跳过/重复挑战 FAIL：`part1_event_judge.py:43` 成功/失败永久锁定，无重试/跳过/暂停/恢复接口；`run_part1_judged_rollout.py:75` 每障碍重建仿真；`comp_score.py:191` 直接相信 summary 最高难度，未从全部挑战推导，也未落实"反复稳定越过"。

### B. 漏洞与可被利用面：FAIL

| 检查 | verdict | 证据与判断 |
|---|---|---|
| B1 不合法路径得分 | FAIL | `part1_event_judge.py:55` 起六个分支均无需入口历史；reviewer 实测**六类障碍各提交一个出口侧位置、空地面接触 → 6/6 立即成功各 100 分**；绕墙、同侧接近绕杆也被接受 |
| B2 接触/时间/位移阈值 | FAIL | `part1_judge.py:74` 不判断受力/顶面法向/持续时间；`run_policy_scene.py:93` judge 只读最后状态，短接触可能漏掉；坡判区从 x=3.7 开始而实物约 x=4.066，接近阶段四足落地即可提前失败；非 plane 地面被归为 unknown |
| B3 摔倒/恢复/暂停 | FAIL | `part1_event_judge.py:36` 无暂停/恢复/朝向输入；实测失败后合法重试仍失败；限高杆提前成功后碰杆仍保留 100 分；无 PDF 第 2 页要求的原位置/原朝向恢复验证 |
| B4 训练 reward/termination | WARN | 训练代码（`prep.d/training_repo_local/.../env_cfgs.py:413`）当前未发现直接调用该 judge；但 `competition-judge.md:62` 计划允许接入 → 接入后会奖励错误成功、漏奖正常 T 台阶 |

### C. 评测协议诚实性：FAIL / WARN

| 检查 | verdict | 证据与判断 |
|---|---|---|
| C1 协议字段是否实际执行 | FAIL | `comp_import_diagnostic.py:90` 固定补写 seed=0，原 runner 无种子/扰动入口；`run_part1_judged_rollout.py:82` 0.5 s 暖机未进命令记录且期间不判接触；起点 yaw 被舍入；manifest 只登记事件 judge |
| C2 尝试是否完整记录 | FAIL | summary `attempts_used=8` 而 manifest 声明整场预算 3；8 个独立障碍被编号为 attempt 1–8；`run_part1_judged_rollout.py:128` 覆盖写结果，无法排除此前失败重跑未留存 |
| C3 训练/评测/标定场版本 | WARN | 顶层 XML 哈希匹配但不覆盖 include；能力场 `map.xml:499` 仍是 24 桩，与独立六桩场不同；`run_policy_scene.py:86` 限动作 ±1 而部署 `flat_ft.yaml:44` 为 ±100 |
| C4 trials 与 summary | PASS | 抽查 3 条（bridge_bands/timeout、height_bar/fail、slope/two_feet_ground）状态、原因、分数、evidence ID 一致；八条均 0 分合计一致 |

### D. 证据链：FAIL

| 检查 | verdict | 证据与判断 |
|---|---|---|
| D1 commit/sha256/uv.lock | FAIL | `manifest.json:11` training/control commit 为 unknown、缺 uv.lock；`comp_import_diagnostic.py:134` 将 task.dirty 硬编码 false、取导入时 HEAD、checkpoint/export 都写成 `policy.pt` |
| D2 success 对应 trial | **FAIL（校验机制）** | 当前样例无 success，但 `comp_score.py:219` 不关联 summary↔trials；reviewer 只读试验：保持 8 条失败 trial 不变、把 summary 高墙改 success/100，两个验证函数仍 `errors=[]` |
| D3 分数能否复现 | FAIL | `manifest.json:41` 缺完整 judge 版本、`:56` 起点协议未冻结；Part 2 零分实际表示"未评测"而非"已尝试失败" |

### E. 合规红线：WARN / PASS

| 检查 | verdict | 证据与判断 |
|---|---|---|
| E1 actor 输入 | WARN | `run_policy_scene.py:60` 拼接字段未包含题列禁止量，但重力投影直接来自 root qpos 四元数、未走 IMU 接口；模型声明了未被 actor 读取的线速度传感器；`audit_deployment.py:69` 只检查自报 YAML |
| E2 瞬时力矩 | PASS（已核执行路径） | `black_policy.xml:160` gear=1、±20；`run_policy_scene.py:91` 再限 ±20；控制仓 23.7/23.7/59.25 有总限幅 |
| E3 Part 2 仅 RL | WARN | Python 路径是网络输出接 PD，但 `summary.json:76` 六项 0 次尝试，无 Part 2 实际执行链证据 |
| E4 世界真值流向 | PASS（已核执行路径） | `run_policy_scene.py:73` actor 输入不含世界位置/机身线速度；位置只交外部 judge，线速度仅可视化 |

### F. 范围与泛化：WARN

- F1：所审样例覆盖 **1 个布局、8 个固定起点、每项 1 次**，名义 seed 无扰动执行，Part 2 为 **0 次**；标定集为空。
  manifest/协议正确标了 `diagnostic`；任何正式通过率/排名/得分结论都超出证据。
- F2：`part1_event_judge.py:30` 及后续硬编码世界坐标，不能随场景平移/旋转/难度变化；PDF 规则允许同类自定义地图，目前无布局变体证据。

## 4. 最可能导致正式比赛丢分的三个 judge 问题

1. **未验证真实跨越就成功**（A1/B1）：出口坐标/接近杆心即得分，会把绕行、漏必达区、未完成动作误认为能力。
2. **T 台阶把当前接触当历史**（A1/A3）：正常逐级通过被漏判、合法侧支路不被接受、部分分缺失，直接误导训练取舍。
3. **斜坡方向/距离/判罚阶段错误**（A2/B2）：目标变成沿 x 越坐标阈值；规则要求沿坡面长边行走，且接近阶段可能先被错误判失败。

## 5. 规则歧义（待主办方确认）

1. Part 1 三次机会是整场还是每障碍？重新越障、摔倒恢复是否消耗机会？
2. T 台阶表 3 的"各 75/50 分"是否分别对应自动/遥控半程分？遥控仅上、仅下分别计多少？
3. "≥1/2 足触地"是否任何瞬时接触都失败？跨越期从何时到何时？限高杆轻触未落、碰柱是否另判失败？
4. 砂砾坑"短边进入或离开"要求两端都合法还是满足一端？两侧斜坡的 1 m 分别计算还是合计？
5. Part 2 高墙/沟壑在 10 cm 端点的分数、比例分小数处理、"反复稳定越过"的最低重复要求？

## 6. 人工标定集最小方案（reviewer 建议）

- **≥64 条轨迹/会话记录** + 计分边界表（不是用来估计成功率，只做功能标定）：
  - Part 1 八障碍 × 4 条（合法通过、另一合法方向、明确失败、边界反例）= 32；
  - Part 2 六类 × 4 条（同难度三次独立稳定成功 + 一条失败/绕行反例）= 24；
  - 会话状态 8 条（重复进入、失败重试、跳过、暂停恢复、错误位姿恢复、Part1 次数限制、Part2 跨难度四次挑战与最高分保留、返回奖励前置条件）。
- 计分边界表覆盖每个阈值的下方/等值/上方/区间插值，必须包含高台/楼梯 <10 cm、坡 <20° 均 0 分，以及高台 35 cm=150 分。
- 每条至少记：`trial_id/run_id/attempt_id`、障碍与难度、实际 seed/扰动、完整起点、命令时间线、策略/场景/judge 依赖哈希、同步视频或状态轨迹；人工标签含成功/失败、预期分数、失败条款、进入/离开时刻、关键足接触/台阶 ID、落杆事件、恢复位姿。
- 两名标注者先独立盲标再处理分歧；通过标准：成功状态、分数、尝试账本与人工标签 **100% 一致**，关键非法得分反例零假阳性；同记录重复回放一致。

## 7. 当前分数的使用结论（reviewer）

| 用途 | 结论 | 理由 |
|---|---|---|
| (a) 内部诊断 | **WARN：可有条件使用** | 可定位起点/命令/接触/卡住问题（保留原轨迹与 diagnostic 标签）；0/8 只代表此脚本+此 judge 的输出 |
| (b) 策略选型 | **FAIL：不可据分数排名** | 假成功、漏成功、动作执行差异、覆盖不足同时存在，比较结果可能反向 |
| (c) 对外引用/答辩能力分数 | **FAIL：不可使用** | 正式协议、标定、完整证据链、Part2 evaluator 均不齐全；答辩可展示诊断过程与本次发现，能力分数须修复+标定+重跑 |

## 8. 修复清单（执行者按 reviewer 建议整理，按优先级）

### P0（G1 重审前必须修）

1. judge 成功语义：所有 Part 1 障碍改为"合法进入 → 实际跨越/接触历史 → 完整离开"状态机；补齐 part2 evaluator。
   - 绕杆：S 形序列 + 起终点/拐角必达区；
   - 砂砾坑：短边进入/离开 + 坑/碎木几何；
   - 高墙：墙上方穿越或攀爬 + 排除绕行；
   - 限高杆：可掉落横杆 + 整机下穿通过；
   - T 台阶：逐级 `step_id` 接触历史 + 侧支路；
   - 斜坡：坡面局部坐标、沿长边累计距离；
   - 木桥：平台/桥面标签 + 完整跨越。
2. `comp_score`：summary↔trials 强校验（evidence ID、success 与 trial 一致、Part2 最高难度从 trials 重算）。
3. `CONTRACT.json`：Part 2 分数曲线最低门槛（高台/楼梯 <10 cm、坡 <20° 为 0）；修正 A/B 命名歧义。
4. 尝试账本：AttemptManager（整场/障碍/暂停/恢复/跳过/重跑），禁止覆盖写。
5. 收窄 `diagnostic` 语义：未控种子/未控起点必须写进 manifest，不得冒充 seed=0。

### P1（G1 重审时一并看）

6. 接触判定：逐物理步累计、法向/受力/持续时间阈值、地面与允许表面区分。
7. 证据链：运行时采集真实多仓 commit/dirty/uv.lock/完整 judge hash + 依赖 hash。
8. 标定集 64 条 + 计分边界表；judge 与人工标签 100% 一致。
9. `E1`：actor 姿态改从 IMU 接口取；移除未使用禁止传感器；审计真实观测来源。
10. C3：统一动作限幅契约（Python ±1 vs 部署 ±100）、冻结 train/eval/cal 场景角色与完整依赖。

### P2

11. 布局变体（平移/旋转/合法起点/难度）与 held-out 布局；
12. Part 2 专用运行入口 + RL-only 证据（策略哈希/控制模式/切换事件）。

## 9. 2026-10-22 主办方口径补充（Q1–Q6，用户转述）及对 P0 的影响

> 本节是审计后补入的规则口径，不改变 reviewer 的判定；P0 修复按"已确认口径"执行。

| id | 已确认口径 | 对 judge/P0 的直接影响 |
|---|---|---|
| Q1 | 整场 3 次；开始/重试/恢复/跳过都消耗 | AttemptManager 语义：每次启动即计数；恢复/跳过也要记账 |
| Q2 | T 台阶按 100 分缩放：两侧都过=100、仅上=75、仅下=50 | judge 增加部分分状态；不再要求"必须两侧"才给分 |
| Q3 | 任何瞬间 ≥2 足触地即失败；碰柱/碰梁但横杆未落**不算失败** | 接触判定去掉持续时间去抖（改为瞬时）；**删除**"bar_contact=fail"，改为只判横杆掉落 + 完整下穿 |
| Q4 | 砂砾坑进入与离开两端都需合法（1 m 短边）；斜坡两侧合计 ≥1 m | 砂砾坑状态机需两端短边证据；斜坡按两侧累加距离判定 |
| Q5 | 高墙/沟壑 10 cm 端点 0 分；小数舍去；稳定 = 失效率 <1%（≥100 次） | 计分用 floor；新增稳定性测量协议（≥100 次独立尝试）；高墙/沟壑曲线端点 0 |
| Q6 | Part 1 全部按手动遥控计分，自动/固定动作无额外分、计时口径不变 | Part 1 评测按遥控口径；自动只影响可靠性/用时，不影响分值 |

**P0 修复清单据此更新**：原第 1、3、4、5 条保留并细化；原"限高杆轻触/碰柱待确认"改为"碰柱/梁不算失败、必须实现落杆检测"；
新增"稳定性测量（≥100 次）"与"部分分/舍去"两条。

### 9.1 2026-10-22 二次确认（对 §9 的更正）

| id | 更正口径 | 影响 |
|---|---|---|
| Q1 | 恢复**不消耗**尝试；最终时长取 3 次中最快者 | AttemptManager：恢复=同 attempt 内事件；计时暂停；final_time=min；分数取 best（假设待确认） |
| Q2 | 上=75×3/2=112.5、下=50×3/2=75 | **与单项 100 分冲突**（112.5>100）：待确认封顶/150 分制；实现前需裁决，暂不写死计分 |
| Q3 | 雷达不采用，优先深度相机 | 合规证据改为 depth camera；actor 仍不得含禁止量；盲策略 fallback |
| Q4 | 稳定性目标 0 失败；无计时压力，先按失败比例优化 | 稳定性评测：target_failures=0、metric=failure_ratio、≥100 次 |

