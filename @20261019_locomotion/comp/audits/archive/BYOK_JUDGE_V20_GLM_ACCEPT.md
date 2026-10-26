# 第二十轮 BYOK 独立复核（GLM-5.3，different-family）

```text
reviewer:   glm-5.3 / BYOK zhipu backend / 2026-10-23
scope:      第 19 轮 flash/pro PASS 后的同一批工件（judge V2.1 / course 协议 / Part2 V2 /
            四份 eval 产物 / HASHES / 演练证据），静态复核 + 几何推演
独立性:     executor=deepseek-v4.1-flash vs reviewer=glm-5.3 → different-family
verdict:    FAIL（新发现结构性"合法通过被误判失败"，构成 scorer blocker）
```

> 说明：artifact 未附行号，以下按"文件::函数/代码段"定位，不臆造行号。本轮不复述前 19 轮已闭环项的细节，只给结论；重点放在前两轮 PASS 未覆盖的方向——**出口/落地阶段的几何语义**。

---

## 1. Part 1 评测器 V2.1

### 1.1 已确认闭环的项（不因前两轮 PASS 而免检，本轮重查仍成立）

| 项 | 结论 | 依据 |
|---|---|---|
| 假成功（spoof 类） | **未发现新通道** | 8 障碍出口位欺骗（`test_spoof_exit_positions`）、高墙墙段 x∈[1.30,2.30]（`HighWall._on_sample`，conformance 2.33 反例）、限高杆门洞连续穿越 + 预掉落持久化（`HeightBar._pre_sample/_on_sample`）、桥/坑/台阶地面带内行走无接触证据即拒（`_check_exit` 证据缺失分支）、绕杆乱序/早终点/同侧 S（`Slalom._check_exit`）均复核通过；接触法向过滤（`run_part1_judged_rollout_v2._sample_judge`，顶面 \|normal_z\|≥0.5）阻止了台阶侧面蹭分 |
| 任意瞬间 ≥2 足 | 采样正确 | 两个 runner 均**每物理步（5 ms）**采样（`V2Runner._policy_step` 内 4×`mj_step`+`_sample_judge`；`run_part1_course.run_policy_step` 内 4×`feed()`），N1 修复无回归 |
| 落杆 | 正确 | `bar_base_seen/bar_dropped_seen` 为障碍对象持久状态，预掉落不可被重试洗掉；`check_part1_scene_v2.py` 保证静置不掉 |
| 双向绕杆 | 正确（有一个次级问题，见 1.3-B2） | 起点圆决定杆序、终点圆要求 done_before==4、半径 0.5 m |
| 返回奖励 | 语义正确 | `Part1JudgeV2.update` 只在 `all_full_done`（全部 8 项且 score≥100）后把出发区进入记 return；T 部分分不触发；`comp_score.validate_summary` 强制 return evidence trial |
| course 账本 | 正确 | 逐物理步喂 judge；暂停期间不调 `course.update`（P2 无回归）；`StableStopTracker` 用 `model.opt.timestep`；`final_time` = 最高分尝试内最快（`AttemptManager.summary` + `comp_score.validate_external_evidence` 双侧同口径）；abort/skip/pause_timeout 事件 t 用模拟器时钟、operator_t 另记（三份 drill 证据核实一致）；skipped trial 不计分/不计时长/不作 evidence（第 16 轮修复无回归） |

### 1.2 新发现 blocker（B1）：**离障落地阶段的 1/2 足误判失败**

`_Obstacle.update` 的判罚条件是：`ground_fail and self.supported and len(ground_feet) >= 2`，且 `supported` 一旦置 True 在本次尝试内不回落。也就是说：**只要机器人曾被障碍面全足支撑，此后它在障碍 zone 内的任何瞬间有 ≥2 足接触地面，即判失败——包括"已完成跨越、正在走下障碍落到目的地地面"的落地阶段**。

问题在于 zone 边界与障碍表面边缘的几何关系。逐障碍核对（`ZONES` vs `part1_eval_scene_v2.xml` geom 尺寸）：

| 障碍 | 表面边缘 vs zone 边界 | 落地后果 |
|---|---|---|
| **gravel_pit** | 砂砾盒南缘 y=−13.0 **正好等于** zone ymin；北缘 −11.0，zone ymax=−10.9（0.1 m 地面带） | 机器人前足先落到带内/边界外的地面上时，base 仍在 zone 内（四足 base 落后前足约 0.2–0.3 m）→ 两个前足 = 2 ground feet → `two_feet_ground` **失败**。**两个短边出口均触发 → 该障碍对正常行走步态结构性 0 分** |
| **t_stairs** | ymin=−4.95 vs s:1 南缘 −4.9（0.05 m 带）；ymax=−2.1 **正好等于** n:1 北缘；xmax=3.35 vs e:1 东缘 3.2（0.15 m 带）；xmin=1.25 vs 臂西缘 1.3 | **四条边出口均触发**。而契约成功定义本身是"通过另一个台阶**回到地面**"（team-race §2.1）——若落地即失败则该障碍按定义永不可成功，矛盾 → 实现错误。100/50/33 全部不可得 |
| **bridge_blocks** | platform_r（x∈[5.2,6.2]）y 延伸到 −1.5，越过 zone ymin=−1.0 → **南出口干净**（在平台上出 zone）；但东出口：platform_r 东缘 6.2 vs zone xmax 6.3（0.1 m 地面带）→ 触发 | 西→东（**正是 `config/part1-route.json` 的方向**）不可过；仅"北进（爬 platform_l 北面）→ 东跨 → 南出"一条路可过 |
| **bridge_bands** | platform_high 覆盖 ymax=−0.8 → **北出口干净**；platform_low 南缘 −4.0 **正好等于** zone ymin → 南出口触发 | 北→南（路线方向）不可过；仅南进北出可过 |
| slope / height_bar / high_wall / slalom | slope 两侧板 y 向延伸超出 zone（沿板面出 zone，干净）；后三者 `ground_fail=False` | 不受影响 |

**为什么规则上这是误判**：
- 木桥规则明文"**到达/离开平台方式不限**"——走下平台落到地面是完成动作的一部分；
- T 台阶成功定义以"回到地面"结束；砂砾坑成功定义以"从短边离开"结束——如果落地接触地面即失败，这些障碍按定义不可通过，与"每项 100 分"的规则矛盾；
- `BYOK_JUDGE_V2_FIXES.md` #1 只修了**进场**地面不判罚（approach），**离场**落地从未被审视。

**为什么 19 轮评审都没抓到**：conformance 的 `feed()` 是合成数据，"legal traversal"用例从未在出口样本里注入 ground feet；MuJoCo 诊断里 flat 策略 0/8、从未走到任何一个障碍的落地阶段。这是静态几何推演（zone 边、表面边、base 滞后于前足）才能暴露的问题。

**量化影响**：即使策略完美，当前 judge + 当前 route 下 Part 1 上限 ≈ **300/900**（仅限高杆/高墙/绕杆可过：route 的 bridge_blocks 西→东、bridge_bands 北→南均为被封方向，t_stairs/gravel 结构性 0，见 1.4 的 slope 路线问题）；换最优通过方向也 ≈ **600/900**，且返回奖励（需 8 项全满分）不可得。C2 基线如果现在跑，测的是 judge 的落地 bug 而不是策略能力。

### 1.3 次级问题

**B2（major，误判失败）：绕杆拐角首次邻近即锁存。** `Slalom._on_sample` 中 corner 用 `not ev["corner"]` 锁存首次进入拐角圆（r=0.5）的时刻，`corner_after` 记录当时的杆数；若机器人在"错误时序"扫过拐角圆（例如 A 方向走西侧重心的 S 形，在 (1.5,−12.3) 附近——距拐角 0.45 m、尚未进入 post 2 的 0.35 m 圈——拐角被锁存为 corner_after=2≠3），之后即使按正确路线再过拐角也不重锁，最终 `corner_out_of_order` 失败。规则只要求"中间必须经过拐角必达区"，未规定时刻；镜像 S 形（两侧交替合法）存在被误杀的路径。conformance 只覆盖了 canonical 路径。

**B3（minor，假成功）：T 台阶"缺级上+完整下"得 33。** 机器人在 s 臂漏触某级（漏级按规则应失败）或直接从顶台侧面爬上（不经过任何臂），只要另一臂 {1,2,3}+top 完整，`_score_for` 给 33（`one_side_down`）。无作弊动机（完整上+top 即 50），属欠严格边界。另：s=上/n,e=下的方向映射仍是硬编码假设（已列残余，需书面确认）。

**B4（minor，理论性）：限高杆未校验"从下方"。** `HeightBar._on_sample` 只查穿越平面时 x∈[5.2,6.2]，不查 base z 低于横杆——理论上跳跃越过横杆也会被判成功（当前行走策略跳不过 0.34 m，不构成现实风险，但应记入标定集）。

### 1.4 路线与判分轴错配（route 层，非 judge 层）

`slope` 判分轴是**沿屋脊方向（y）在两块坡面上累计 |Δy|≥1 m**——这与"两侧斜坡、不分开计分"的屋顶式几何解释一致（slope_a/slope_b 共享高缘 x≈5.2，judge 语义本身正确）。但 `config/part1-route.json` 的 `cross_slope` 是沿 **x 方向翻越屋脊**，|Δy|≈0 → 该段即使策略完美也得 0 分。route 同时还使用了 1.2 中被封的两个 bridge 方向。route 是 P0 诊断 harness（已自我声明非正式赛程），但 **C2 基线若复用此 route，会叠加 judge bug 与 route 错配双重失真**，必须先修。

---

## 2. Part 2 评测器

| 检查 | 结论 |
|---|---|
| 六类成功判据 | 平台/楼梯/斜坡/梅花桩均要求目标位姿 + lane 内 + **无地面足 + 对应表面 tag**（`_cond`），"站地面伪成功"已封；高墙要求 lane 内跨 wall_x + 墙接触 + 近墙 max_z≥max(wall_h+0.10, 0.55)；沟壑要求 near/far 边先后跨越（或一次跃过）+ z 恢复 |
| floor / 10 cm 端点 0 | `curve_points_floor` 与 `comp_score.curve_points` 双实现一致：wall/trench 10 cm=0（conformance 断言在案）、bool 只认 1.0、trench 25 cm=225（floor 验证） |
| 每项 4 次（official） | `--official` 高→低取前 4 档、不足补最高档（trench=[30,20,10,30]、plum×4），trials a1–a4 与 summary attempts_used=4 对账一致；重复档在确定性策略下统计意义有限（已记录） |
| 证据链 | manifest 逐 level scene sha256、`validate_external_evidence` 校验合法档位/成功 trial 对应 |

**新发现问题：**

- **B5（minor–moderate，假成功）：hold 时间只累加不重置。** `Part2JudgeV2.update` 中 `if cond: self.held += dt` ——**没有 else 清零**（定义了带重置的 `_hold_ok` 但从未调用，是死代码）。0.2 s 的"稳定站立"实际是**跨时段累计**：断续满足条件（如跳上台面 0.1 s、跌落、再上台 0.1 s）也会 success。与修复声明"持续 hold"不符。
- **B6（minor，误判失败，保守向）：高墙成功必须发生墙接触。** 干净跳过（越过的合法形态之一）无 wall tag → fail。当前行走策略不构成现实风险，但标定集应覆盖。
- **B7（minor，误判失败，保守向）：沟壑 lane ±0.7 m 比沟本身（y 半宽 1.2 m）窄**，在 \|y\|∈(0.7,1.2] 处跨越同一沟壑被拒。
- **B8（note）：official 档位表是固定梯子**（trench 会重试最高档，platform/wall/stairs/slope 不会重试失败的高档）——规则允许 4 次任选难度，固定梯子是合法但非最优的测法，可能低估边界能力。

---

## 3. 证据链

这部分**干净**，与前两轮结论一致，本轮独立复核仍成立：

- **HASHES（62 objects）**：覆盖 contract（md/json）、protocol、5 个 judge/协议文件、3 个 runner、3 个 importer、score 工具、场景 v2、levels 19 个 xml + levels json + 2 个 Part2 场景、四份产物的 manifest/trials/summary（含 official）、route、3 份演练证据。与 payload 中文件实际 sha256 逐项相符。缺口（非阻塞，前两轮已提）：`comp_import_selftest.py`、`config/part1-course-events-*.json` 不在 OBJECTS。
- **summary↔trials 复算**：四份产物全部抽查通过——part1-diag 8 条全 fail 与 summary 一致；part2-diag 20 条、attempts_used 4/4/4/4/3/1 与 trials 计数一致；official 24 条、每类 4 条、attempt 1–4 编号正确；course 3×8=24 条全 fail、final_time 94.18（summary 94.17999999998638 与 trial 94.18 差 1.4e-11 < 1e-6 容差）。skipped/0 分/重复 trial_id 校验路径均在。
- **comp_score**：`validate_external_evidence` 已接入 `score_one`；外部 hash、Part2 合法档位、attempts 对账（formal 不一致即 error）、Part1 final_score/final_time 从 trials 按最高分尝试复算（含 skipped 排除）——自检 fixture（篡改 hash/非法档位/错误 final_time/skipped 正分）覆盖到位。
- **演练证据**：pause_resume（3 attempts、recoveries=3、pauses=[[1.0,1.0]] 模拟器时钟闭合、时长不含暂停）、abort（3×skip、duration=2.505=end−start 模拟器时钟、operator_t 记录）、pause_timeout（121.02 s 触发、事件先 append 再 abort、duration 0.5）——与 `Part1Course` 代码路径逐一吻合，无 fake 时钟污染。

---

## 4. 结论

### verdict：**FAIL**

- **scorer blocker：有。** B1（离障落地 1/2 足误判失败）是结构性"合法通过被误判失败"：t_stairs 与 gravel_pit 对正常步态**完全不可通过**，两个桥各封一个方向（含 route 所用方向），返回奖励因此不可得。按用户自己的门禁标准（blocker = 合法通过被误判失败），必须先修。B2（绕杆拐角锁存）为 path-dependent 的同向问题。
- 假成功侧：spoof 类通道已封死，本轮无新增重大项；新增的是 B3（T 台阶缺级得 33）与 B5（Part2 hold 累计），均为 minor–moderate。
- 证据链（HASHES / summary↔trials / comp_score / 演练）：通过，无需返工。

### 是否同意进入下一阶段（C1 人工标定 / C2 基线评测）：**no**

C2 现在跑会把落地 bug 和 route 错配烧进基线数字；C1 的 64 条标注很贵，对着一个已知要改判罚语义的 judge 去标，标签会作废。B1/B2/B5 的修复面很小，先修再进。

### 最小修复清单（按优先级）

1. **B1**：把 1/2 足判罚限定在"跨越进行中"——例如当退出侧证据已集齐（桥：双平台+桥面命中且已到达远端平台；T 台阶：臂+top 完整；砂砾：gravel 命中且已越过远短边）时立即锁定成功/停用地面判罚；或把判罚区域从 zone 收缩到障碍表面足迹、且以"足越过远侧表面边"而非"base 越过 zone 边"作为检查终点。修完后**必须保留**中途真坠落（桥面中段双足触地）仍判失败。conformance 需补"合法完整穿越 + 落地时前足触地、base 仍在 zone 内"的合成用例（当前 `feed()` 从未在出口样本注入 ground feet，这正是 19 轮漏检的原因）。
2. **B2**：拐角改为"在期望时序窗口内的到访才计数"（或取终点区到访前最后一次拐角到访判定），并补镜像 S/提前扫过拐角圆的 conformance 反例。
3. **B5**：`held` 在 cond 为假时清零（落实"持续 hold"），同步 self-test。
4. **route**：修正 `part1-route.json` 的 bridge 方向（blocks 改北进南出、bands 改南进北出）与 slope 段（改为沿屋脊 y 向走 ≥1 m），或至少在产物 notes 里声明该 route 不用于计分。
5. **B3/B4/B6/B7**：记入标定集待裁决项；B3 建议改为"使用的上坡臂缺级即整体失败"。

### G1 报告必写残余（修复后仍需携带）

- 砂砾坑真实"坑+碎木"几何未 recut（凸起盒代理）——**注意：recut 后 B1 的出口几何会变，修复必须以真实几何复核**；
- Part2 官方能力场逐档交叉核对未做；official 重复最高档统计意义有限；固定梯子策略可能低估边界难度；
- soft-reset 阈值与相邻 zone 重叠仍是启发式；
- T 台阶 s/n/e ↔ 上/下映射、障碍级跳过是否消耗整场尝试、pause_timeout 120 s（自定协议常量）需书面确认；
- 正式手动 3 次整场演练未在真实赛程完成；
- B4/B6/B7 三个保守向判罚（限高杆跳跃、Part2 墙接触、沟壑 lane 宽）留待 C1 标定裁决；
- 跨 attempt 模拟器时钟重置、`_protocol.md` draft、HASHES verdict=pending、`comp_import_selftest.py`/事件配置 JSON 未入 HASHES。

### 建议下一步

修 1–4（预计改动集中在 `_Obstacle.update` 的判罚门控、`Slalom._on_sample`、`Part2JudgeV2.update`、route json）→ 补齐 1 中新 conformance 用例并全量重跑（conformance 13 组 + course/Part2 自检 + 四份诊断产物 + 三份演练）→ 刷新 `HASHES.json` → 用 flash（或直接 GLM）做一次**只针对该 delta 的复验** → 再进 C1/C2。Codex 恢复后补最终 acquittal 的计划不变。
