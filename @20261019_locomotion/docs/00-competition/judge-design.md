# 队内赛合格判定器设计（P0）

## 1. 结论

- **先建“官方判定器”，不是只建 training terminate**。判定器要输出“障碍是否成功、拿多少分、第几次尝试、失败原因、是否跳过”，并能在手动操作/多次尝试/摔倒恢复下持续记录；training terminate 只是它的简化子集。
- **没有找到可直接复用的整场比赛 judge**。IsaacLab 的 [`TerminationManager`](https://github.com/isaac-sim/IsaacLab/blob/main/source/isaaclab/isaaclab/managers/termination_manager.py) 可借“终止项管理器”的结构，MuJoCo contact sensor / MjLab event manager 可借接触/事件机制；但本比赛的障碍成功判据、足接触比例、尝试/计分规则必须自己实现并在自建场上标定。
- 判定器必须在**正式场/能力场几何**上工作；不能拿 flat/rough 的速度跟踪 gate 当合格判定。
- Part 1 的“背地形路径”只能通过**导航速度指令/状态机**影响机器人；世界坐标/速度真值不能直接进网络。Part 2 不能写固定动作/背路径，只能 RL 策略。

## 2. 判定器架构

| 模块 | 职责 | 输入 | 输出 |
|---|---|---|---|
| `ObstacleSpec` | 每个障碍的几何区域、允许表面、地面、起点/终点、难度档位 | 场地 MJCF/XML 元数据 | 区域/表面标签 |
| `FootContactClassifier` | 每只脚是否接触“允许表面”或“地面”；1/2 规则；去抖 | 足端 geom 与 obstacle/ground geom 的 contact、法向力、持续时间 | `feet_on_ground`、`feet_on_obstacle`、接触次数 |
| `ObstacleJudge` | 逐障碍状态机/事件：进入、通过、失败、成功 | 足接触、base/trunk 位姿、bar 位移、checkpoint 顺序 | `status: pending/running/success/fail/skipped` |
| `AttemptManager` | 3 次（Part 1）/每项 4 次（Part 2）、摔倒暂停、原位置恢复、跳过 | reset/operator 事件、judge 状态 | attempt index、resume pose |
| `ScoreBoard` | 逐项/总分、返回启动区奖励、最高难度 | ObstacleJudge | JSON/终端/可视化 |
| `TrainingTerminationAdapter` | 给训练环境用的简化终止：fall/stuck/success；可配置近似 | judge 事件或近似信号 | `terminated`、`time_out`、diagnostic |

## 3. 足接触语义（最关键的规则）

- 本比赛中的“1/2 以上足端与地面接触”按**4 足中 ≥2 足**处理；接触需要连续/去抖，避免单帧碰撞噪声。
- “地面”不是所有 geom：正式障碍的**允许表面**（台阶顶面、桥面、坡面、高台顶面、石块/碎木表面）不算 ground；floor/场外地面/障碍内部的坑底算 ground。
- 用接触法向力阈值 + 持续时间（例如 >5 N 且 >0.05 s，最终以实测标定）定义“有接触”，避免轻擦。
- T 台阶的“每一级顶面至少一次足底接触”要按**台阶层级**记录接触历史，而不是只看脚是否碰到任意石面。
- 限高杆需要 movable bar 的位移/角度检测；bar 位移超过阈值或掉落即失败，不能只看机器人是否穿过。
- 判定器只读仿真状态，不读策略内部；官方 evaluator 与训练 reward 解耦。

## 4. 逐障碍判据（摘要）

### 4.1 赛项一

| 障碍 | 成功 | 失败/重试 |
|---|---|---|
| 直角绕杆 | 按顺序通过每个 checkpoint/必达区，S 形且每个竖杆都过 | 漏杆/顺序错误；离开场地 |
| 砂砾碎木坑 | 从 1 m 短边进入和离开；跨越期间不触发 1/2 足 ground | 1/2 足 ground 持续超阈值；从长边进出不算 |
| 高墙 | 越/爬到高墙另一侧，base/foot 过顶/过墙 | 未过墙；卡住 |
| 限高杆 | 从门柱之间沿垂直门平面方向穿过且杆不接触 | 杆位移/掉落；撞侧柱/横梁；从门洞外侧绕行不算 |
| T 字形台阶 | 任一侧上、另一侧下；每级顶面至少一次足接触；不触发 1/2 足 ground | 漏级；1/2 足 ground；只上不下只得部分分 |
| 高墙 | 沿墙的薄方向（世界 ±y）跨到另一侧 | 撞墙/卡住；沿墙长方向走不算 |
| 斜坡 | 在坡面沿 3 m 长边方向累计 ≥1 m；不触发 1/2 足 ground | 距离不足；ground contact |
| 木桥 A/B | 一侧平台经桥到另一侧平台；不触发 1/2 足 ground。两种桥面要分开：`bridge_blocks` 5 个 0.4×1.0 m 方墩（缝 0.15 m），`bridge_bands` 3 条 0.2×1.5 m 窄带（缝 0.10 m） | 掉桥；脚到缝底/ground；ground contact |

### 4.2 赛项二

| 障碍 | 成功判据 | 难度档 |
|---|---|---|
| 高台 | 上到高台上平面 | 10/20/30/40 cm |
| 楼梯 | 通过台阶（上/下） | 10/15/20/30 cm |
| 斜坡 | 迎坡通过 | 20/30/35/45° |
| 高墙 | 越过/攀爬到另一侧 | 20/30/40 cm |
| 沟壑 | 跨过沟壑到对侧 | 10–30 cm，30 cm=300 |
| 梅花桩 | 从平台经桩阵到另一侧平台 | 200 分；按 PDF 尺寸自建 |

- 能力测试按“最高成功难度”计分，不按尝试次数扣分；每项 4 次，失败/重试不改变已得最高分。
- 赛项二仅 RL：判定器只判成功，不提供固定动作；策略选择/模式切换不能被实现成“固定动作序列”。

## 5. 训练 terminate 与官方 judge 的关系

- 训练环境可以先用简化 `fall / stuck / illegal_contact / success` 作为 terminate；但它们只是 training signal，不能直接当比赛分数。
- 官方 judge 的 `success` 事件可以作为训练 success reward/termination 的来源之一，但要防止 reward hacking：例如策略在障碍入口附近反复触发 judge、或利用 ground 接触阈值。
- 每个障碍的 judge 先在**固定种子/手工轨迹**上验证，再用于训练；训练时用同一几何但不同难度/布局。

## 6. 验证计划（P0）

当前已落地 Part 1 working scene 与接触判定骨架：`assets/terrain/part1/part1_scene.xml`、`scripts/agent_scripts/part1_judge.py`（足端 ground/限高杆 contact），下一步补逐障碍 success state machine 与 Part 2 能力档位。

1. 用场地 XML 生成 8 个障碍/6 类能力障碍的 `ObstacleSpec`（区域、允许表面、ground、checkpoint、bar）。
2. 用 MuJoCo 直接设置机器人姿态/脚接触，做**单元测试**：成功、失败、边界、1/2 足、漏级、bar 掉落、attempt reset。
3. 用手动/脚本化 rollout 录 3–5 个成功和失败样例，judge 结果与人工标注一致。
4. 在正式场跑 `flat-ft-2500` zero-shot，输出真实基线得分；这个分数才是“比赛进度”的起点。
5. judge 输出 JSON（每障碍成功/得分/尝试/失败原因），与计分板/答辩材料共用。

## 6.1 P0 本地 zero-shot 基线（2026-10-22）

`scripts/agent_scripts/run_part1_judged_rollout.py` 用本地 45 维 `flat-ft-2500` 独立尝试 8 个 Part 1 障碍，并读取 `Part1Judge` / `Part1EventJudge`（judge 在策略回路外）：

| 障碍 | 结果 | 说明 |
|---|---|---|
| bridge_blocks | fail | 两足 ground fail，tilt≈25.9° |
| bridge_bands | running | 到 y≈−3.08 后未完成，tilt≈14.9° |
| gravel_pit | pending | 从坑外半个宽度起步，4 s 内未进入区域 |
| height_bar | fail | 从 y=-10.4 沿 +y 穿门洞，碰横梁；tilt≈1.6° |
| high_wall | running | 沿 ±y 跨墙方向进入，未越过墙；tilt≈2.1° |
| slalom | running | 只接近第一个 checkpoint |
| slope | fail | 两足 ground fail，tilt≈6.6° |
| t_stairs | pending | 未进入台阶区，未见台阶层接触 |

这是**脚本起点/命令下的诊断**，不是官方整场得分；T 台阶逐级接触、限高杆位移、桥面 step 等判据仍需用真实手动轨迹校准。结果 JSON：`prep.d/results/part1_zero_shot.json`。

## 7. 与路线的对应

- **P0 先 judge + 场地**：judge 不依赖策略训练；没有 judge 就不做“比赛训练”。
- **Part 1**：macro 路线/状态机只输出导航速度指令；micro 逐地形训练；固定动作/局部自动只在 Part 1 允许且无额外分；由 attempt manager 管理 3 次尝试和恢复。
- **Part 2**：不背路径、不写固定动作；逐品类 RL，优先一个共享 terrain generalist，再考虑按品类微调/专家；judge 负责最高难度/得分。
- **答辩**：judge 的 JSON/得分曲线/失败原因直接作为答辩证据。
