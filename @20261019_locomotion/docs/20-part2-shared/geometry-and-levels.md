# 比赛地形覆盖、步态对称性与 blind vs depth 最终裁决（2026-10-24 修订）

> 触发：用户指出两个方法论问题——① 当前训练地形只有 flat / smooth slope / stairs，不能反映 Part1 的绕柱、桥、限高杆、高墙、砂砾等和 Part2 的高台/沟壑/梅花桩，而这些恰是深度视觉最可能有用的地方，用它裁决 blind vs depth 不成立；② 奖励里没有对称性约束，后腿"始终一前一后"（symmetry breaking）仍在；③ 是否应在"方法论拉满（接近最终模型）"后再比较两条线，以及这样会不会就已经是最终策略。
> 本文给修订后的训练地形、对称性修复和最终实验设计。当前在跑的 3000/warm-start 只作为**简单地形筛选**，不作为最终裁决依据。

## 1. 为什么现在的地形不足以裁决

> **验收口径（2026-10-26 更新，用户明确）**：此前文档中的 `8/8`、`16/16`、`<1%` 等通过次数/百分比均为自拟指标，已作废。现行验收 = 覆盖的初始状态×指令集内"零摔倒 + 可行子集全部穿越 + held-out 同样成立"，逐 case 报告，不设固定次数门槛；详见 `part2-ppo-execution-plan-2026-10-26.md` §0.3。



| 比赛地形 | 当前训练地形覆盖 | blind 是否本来就能过 | depth 的信息优势 |
|---|---|---|---|
| flat / 斜坡 / 台阶 | ✅（flat + smooth slopes + stairs） | 主要靠本体历史/自适应即可 | 有限（几何简单、可预测） |
| 绕柱 slalom | ❌ | 需要感知柱位、贴边走 | **高**（柱在视野内，可提前转向） |
| 方墩桥/窄带桥 | ❌ | 靠盲走、容错低 | **高**（桥面宽度/缝隙/对岸可测） |
| 限高杆 | ❌ | 只能靠高度估计/记忆 | **高**（横杆/门洞在正前方） |
| 高墙 | ❌ | 靠冲击/试错 | **高**（墙面距离、高度可测） |
| 砂砾/碎木坑 | ⚠️ 有 gravel 任务但不在 P1 | 部分 | 中（坑深/边界） |
| T 台阶 | ⚠️ 有 stairs（非 T 形） | 部分 | 中 |
| Part2 高台/沟壑/梅花桩 | ❌ | 差 | **高**（落差、桩距） |

结论：slopes/stairs 是"本体可自适应"的地形，用它比较会系统性低估 depth 的价值；**最终裁决必须在含结构障碍的竞争地形上做**。

## 2. 竞争地形代理（`black-competition` 任务）

在 mjlab 现有 terrain primitive 上尽量复用，仅补 4 个自定义 primitive；尺寸按 `comp/CONTRACT.md` 与 Part1/Part2 MJCF 的本任务参数。

| 比赛障碍 | 训练地形实现 | 关键参数（来自 CONTRACT/场景） |
|---|---|---|
| 方墩桥 bridge_blocks | **自定义 `BridgeBlocksCfg`**（5 个 box） | 0.4×1.0 m 方墩、缝 0.15 m、顶面高 0.20 m |
| 窄带桥 bridge_bands | **自定义 `BridgeBandsCfg`**（3 条窄带） | 0.2×1.5 m、缝 0.10 m、高 0.20 m（或复用 `BoxNarrowBeamsTerrainCfg`） |
| 限高杆 height_bar | **自定义 `HeightBarCfg`**（两柱 + 横梁） | 门洞宽约 1.0 m、横杆底边 0.20–0.30 m（难度插值） |
| 高墙 high_wall | **自定义 `HighWallCfg`**（横跨路径的竖板） | 高 0.10–0.40 m（Part1 0.2–0.3、Part2 10–40 cm），厚 0.05 m |
| 绕柱 slalom | **自定义 `SlalomPolesCfg`**（交错圆柱） | 柱半径 0.03–0.05 m、纵向间距 0.8–1.2 m、S 形 |
| 砂砾碎木坑 gravel_pit | 复用已有 `black-gravel-flat`（settled proxy）/ `HfDiscreteObstaclesTerrainCfg`（坑+凸起） | 1 m 短边进出、坑深 0.05–0.15 m |
| T 台阶 t_stairs | `BoxOpenStairsTerrainCfg` / `BoxRandomStairsTerrainCfg`（可双向） | 台阶 0.10–0.30 m（Part1 表 3 难度） |
| Part2 梅花桩 | `BoxSteppingStonesTerrainCfg` | 桩 0.2×0.2×0.2 m、排距 0.2 m、间距 0.4 m（按 PDF/场景参数缩放） |
| Part2 高台/沟壑 | `BoxPyramidStairsTerrainCfg` + `HfDiscreteObstaclesTerrainCfg`（pits） | 高台 10–40 cm；沟壑 10–30 cm |
| 斜坡 20–45° | 现有 `HfPyramidSlopedTerrainCfg`（难度范围扩到 45°） | 3 m 长边、≥1 m 行走距离 |

- 难度课程：每类按比赛档位映射到 `difficulty ∈ [0,1]`（例如高墙 0.10→0.40 m、限高 0.30→0.20 m 门洞、桥缝 0.05→0.15 m），与 Part1/Part2 的 10/20/30/40 cm 档位对齐。
- 比例建议（初值，可调）：flat 10%、slope 10%、stairs 10%、gravel 10%、bridge 15%、height_bar 10%、high_wall 15%、slalom 10%、stepping_stones 10%。**先保证每类都有足够梯度**，不追求与比赛精确同比例。
- 与真实场景的偏差：训练代理是程序化地形，尺寸/材质/光照与 Part1/Part2 MJCF 不完全一致；**最终以本地 judge 在真实场景上的评测为准**（见 §4），代理只用于训练分布覆盖。
- 验证：新 task 能构建、能跑 play rollout、几何尺寸与 CONTRACT/场景文件逐项对齐（可写一个 `check_comp_terrain_geometry.py` 对照参数）；训练 100–200 iter 看无 NaN/无 CUDA，replay 视频确认能走。

## 3. 步态对称性：现状与修复

**现状（已确认）**：当前 P1/depth 训练只启用了 `foot_clearance`（权重 −0.01），**mirror loss 默认 0**（`BLACK_MIRROR_LOSS_COEFF=0`），所以后腿不对称（RL−RR 平均前后差 0.15–0.25 m、RR 拖地）是预期的 symmetry breaking；用户观察到的"后腿始终一前一后"与此一致。旧 A/B（`docs/training/experiments.md` §3.9，2026-10-21，flat 从零 2048 envs）结论：

| 设置 | RL−RR 平均 x 差 | 后腿接触 | 后腿足端最高 |
|---|---:|---:|---:|
| 无 mirror（baseline） | 0.255 m | 0.953 / 1.000 | 4.1 / 2.1 cm |
| mirror 0.1 | 0.047 m | 1.000 / 1.000 | 2.4 / 2.9 cm（两条后腿都拖地） |
| mirror 0.1 + foot_clearance | **0.006 m** | 0.937 / 0.987 | 4.5 / 5.1 cm |

→ **修复 = mirror loss 0.1 + foot_clearance（已有）**，并用同一套指标回归，防止"对称但拖腿"退化解。后续所有竞争地形训练（blind 和 depth 两条线）默认开启 `BLACK_MIRROR_LOSS_COEFF=0.1`；先做 0 vs 0.1（可选再加 0.03）的单开关 A/B，确认地形能力/通过率不下降。若 mirror loss 明显拖慢结构障碍学习，再考虑 0.03 或 mirror data augmentation（需要给 critic 的 height scan 实现镜像，当前只做 loss）。
另外在 rollout 诊断里固定输出四个对称性指标：RL−RR 平均前后差、后腿接触率、后腿足端最高点、左右相位相关（hip/thigh 角度互相关峰），作为 gate。

## 4. 最终实验设计：方法论拉满后再裁决（并且这次比较就是最终模型）

用户的直觉正确：**在"简单地形 + 无对称约束"下裁决不成立**；但也不应该为每个问题各跑一个完整 pipeline。建议如下"一次成型"的最终选择协议：

1. **阶段 0（已在做，只作筛选，不作裁决）**：简单地形 500/1500/3000 iter + warm-start 臂，得到成本曲线和"深度是否学得动"的粗信号；当前队列跑完即结束，不再加预算。
2. **阶段 1：把两条线的"方法论"补齐**：
   - 训练地形换成 `black-competition`（§2）；
   - 奖励/约束：mirror 0.1（§3）+ 现有 foot_clearance + 现有 P1 奖励；
   - 课程/终止/命令范围沿用已验证配置；DR 放到最后（见 §5）。
3. **阶段 2：先训一条"最终候选主线"（blind，便宜）**：`black-competition` 从 P1 权重 resume（或从零 3000–5000 iter），产出 blind-final；用本地 Part1/Part2 judge 诊断（现有 `run_part1_judged_rollout.py` 等，blind 链路已通）。
4. **阶段 3：depth 最终候选 = blind-final warm-start + 同地形同预算**：用已在训练仓实现的 `BLACK_DEPTH_WARM_START`（从 blind-final 初始化、CNN latent 列置零）+ `black-competition-depth`（深度相机）训 1500–3000 iter；这样 depth 只花"增量成本"（约盲线的 1.5–1.6×/iter），不需要从零重训。
5. **阶段 4：裁决 = 同协议 judge 分数**：两个最终候选在 Part1/Part2 真实场景上按现有 judge 跑同一组起点/命令（深度候选需要先补"本地深度推理"评测链路，见 §6），比较总分/单项通过/稳定性/耗时；**赢的那条就是最终策略**（所以"会不会已经是最终模型"——是的，这正是目的：把比较和最终训练合并，不重复烧算力）；输的一条留作 fallback 与消融证据。
6. **阶段 5：冻结与收尾**：winner 按需 DR fine-tune（单开关、从强 checkpoint 续训）→ 重跑 judge/演示/合规检查 → G5 冻结（若时间不够，冻结阶段 4 的 winner，并记录未做 DR）。

**成本估算**（5060 Ti，1024 envs）：blind-final 3000–5000 iter ≈ 1–2 h；depth-final warm-start 1500–3000 iter ≈ 0.8–1.6 h；judge 评测（CPU）≈ 0.5–1 h/轮；合计约 4–6 h GPU，10 天窗口足够。时间线建议：10/24–25 地形生成器 + mirror A/B（GPU 排队间隙）；10/26–27 blind-final + judge 迭代；10/28 depth-final + 深度评测链路；10/29 裁决/冻结；10/30–11/03 DR（可选）/演示/审计/答辩准备。

**判据**：以 judge 总分为主（Part1 8 项 + Part2 20 档），辅以 0 摔倒/失效（用户口径：任何一次失败都算待修，见执行计划 §0.3）、对称性指标达标、推理成本；若两条线分数接近（<5%），选 blind（成本低、风险小）。不再用训练 reward 或"简单地形曲线"直接裁决。

## 5. DR 的位置

仍在**地形课程稳定之后**做（原 `camera-depth.md` §9）：先把 `black-competition` 上的策略训到能走/少摔，再用强 checkpoint 做 DR fine-tune（深度渲染噪声/量化 → 丢帧/延迟 → 外参 → 分辨率/FOV → 遮挡，单开关逐项），避免早期学习被 DR 拖慢、归因不清。

## 6. 需要补的评测/工程项

1. **`black-competition` + `black-competition-depth` 任务**：terrain generator（§2）、depth 相机沿用 `camera_depth.py`、runner 复用；
2. **本地深度推理评测**：**已实现（2026-10-24，待真实 checkpoint 验证）**：训练仓 `scripts/agent_scripts/export_depth_policy.py` 用 rsl_rl `_TorchCNNModel` JIT 导出（`forward(obs_1d, [depth])`，输出 12 维 action，写 `contract.json`/sha256）；本地 `run_policy_scene.py` 的 `ScenePolicyRunner` 增加 `depth_config`（在 `d435_link` 上按训练参数加相机：70° fovy、0.1–3.0 m、64×48，隐藏机器人 geoms、归一化 /3.0），`run_part1_judged_rollout.py` / `run_part2_judged_eval.py` 增加 `--depth/--depth-width/--depth-height`；已用 dummy depth policy 端到端跑通 Part1 judge（无错误、JSON 记录 `depth: true`）。真实 depth checkpoint 的导出于 blind-final/depth-final 产出后补；blind 评测链路早已通。
3. **几何对照检查**：新地形参数 vs CONTRACT/Part1/Part2 场景参数；
4. **对称性指标脚本**：从 rollout 里算 §3 的四个指标，作为每次训练后的固定输出；
5. 文档/账本：新增 run 行、实验结论进 `experiments.md`/`camera-depth.md`。

## 7. 对当前在跑任务的处理

- 当前 3000-iter（blind/depth）与排队中的 warm-start 臂**继续跑完**（成本已花），结果只写进"简单地形筛选/成本曲线"，**不进入最终选型判据**；
- warm-start 代码保留，作为阶段 3 的工具；
- 阶段 1 的 `black-competition` 地形与 mirror A/B 在 GPU 空出来后开始（预计 2026-10-24 傍晚），先各跑 500–800 iter 筛选，再进长训。

## 8. 实现状态（2026-10-24）

已落地（训练仓 worktree，未提交上游）：

| 项 | 落点 | 状态/证据 |
|---|---|---|
| 竞争地形代理 | `src/alldog_mjlab/tasks/velocity/black/competition_terrain.py`（8 个自定义 SubTerrainCfg + 复用 flat/slope/stairs/gravel，共 14 列 × 6 行、难度 0..1） | CPU 几何检查通过（634 geoms、goal patch 4覆盖集零失败（§0.3）4 = 8 障碍列 × 6 行）；GPU 3-iter smoke 通过 |
| 任务 | `black-competition` / `black-competition-depth`（+ `-hist` 6 帧历史变体）注册在 `__init__.py` | smoke：blind 3 iter、depth 3 iter、history/depth-hist + mirror 0.1 各 2 iter 均 rc=0、无 NaN/CUDA |
| 任务成功奖励 | `competition_rewards.py`：goal flat patch（8 个障碍列）→ 稀疏 `competition_goal` 奖励（权重 3.0）+ `competition_goal_reached` 终止；非障碍列用 spawn origin 填充并按最小距离 0.8 m 屏蔽 | smoke 的 `Episode_Reward/competition_goal`/`Episode_Termination/competition_goal_reached` 项存在（迭代太短，成功数 0，符合预期） |
| 历史帧 | `black-competition-hist`（270 维 actor）、`black-competition-depth-hist`（270+64 CNN） | smoke 通过；`symmetry.py` 已扩展为支持 45×k 历史布局的 mirror loss（**2026-10-24 修正：MjLab native history 是 term-major 布局**——每个 term 的 6 帧连续排列，不是 6×45 帧块——mirror 已按 term-major 实现并验证 involutive；A/B 的 hist 臂在修正后启动） |
| mirror 0.1 | 环境变量 `BLACK_MIRROR_LOSS_COEFF=0.1` 作用于所有新 run | smoke 日志 `[INFO] mirror-loss symmetry enabled: coefficient=0.1` |
| 预览视频 | `prep.d/videos/competition/` 12 段（blind/depth zero-shot × 障碍列）+ `contact_competition_preview.jpg`；review 页 §2.4 | 已生成；仅用于地形几何/基线行为检查 |
| 历史帧 A/B | `cmp_comp_blind_800`（45-D）vs `cmp_comp_hist_800`（270-D），800 iter × 1024 envs，mirror 0.1 + goal 奖励 | **RUNNING**（2026-10-24 16:10 起，约 40 min） |

备注：地形代理与官方场景仍有几何/材质/接触差异，最终裁决仍以 Part1/Part2 真实场景 judge 为准；接下来的实现顺序是 "历史帧结论 → blind-final 长训 → depth-final（warm-start/from-scratch）→ judge 对比"。

**部署/评测注意（270 维历史策略）**：mjlab native history 的 270 维布局是 term-major、oldest→newest（`[command×6, ang_vel×6, gravity×6, joint_pos×6, joint_vel×6, actions×6]`，每个 term 内部按时间旧→新），与 `rl_sar`/`best.pt` 的 HIM 270 维约定（frame-major、newest→oldest）不同。若历史帧 A/B 胜出，导出 TorchScript 时需要把第一层 Linear 的列置换为部署约定（离线重排权重即可，不需要重训），本地 judge 的 `ScenePolicyRunner` 也需要按部署/评测约定做历史栈；否则只能用于训练侧评测。此工作在 A/B 结论后按需执行。

### 8.1 历史帧 A/B 结果（800 iter，2026-10-24）

两臂同地形/同奖励/同预算（1024 envs、800 iter、mirror 0.1、goal 奖励、从零；单 seed）：

| arm | Mean reward | episode | terrain level | illegal_contact | goal_reached | vx_max | iter 成本 |
|---|---:|---:|---:|---:|---:|---:|---:|
| single-frame 45-D (`cmp_comp_blind_800`) | **9.72** | **730.2** | 0.310 | **0.761** | **8.7%** | 1.0 | 1.39 s |
| 6-frame 270-D (`cmp_comp_hist_800`) | 8.08 | 639.5 | **0.347** | 0.954 | 4.7% | 1.2 | 1.44 s |

结论：**单帧 45-D 在 800 iter 内明显更好**（reward +20%、episode +14%、非法接触低 20%、goal 成功率高 87%），历史帧臂只在地形等级/命令范围略高，但摔倒/触地多、任务成功少。考虑：
- 历史帧需要额外部署/评测转换（native term-major → HIM frame-major 第一层列重排；已实现 `export_history_policy.py` 与本地 history runner，但增加链路风险）；
- 单帧与已有 Part1/Part2 judge 链路、导出、rl_sar/quadruped_control 契约完全兼容；
- 800 iter 不是历史帧的"完全体"（可能更长训练/更多历史帧会改善），但当前比赛窗口下不优先赌它。

→ **blind-final / depth-final 都采用单帧 45-D actor**；历史帧保留为研究记录（`-hist` 任务与导出脚本仍在仓库），不进入最终选型。

**补充定量记录（2026-10-24）**：步态对称性（flat、0.8 m/s、6 s）单帧 RL−RR 前后差 0.062 m、后腿足端最高 0.038 m；历史帧 −0.114 m、0.025 m（两臂 z<0.04 接触率均 1.0，该阈值是近似，真实接触判据以 judge 为准）。难度 0.8/0.6 障碍列 12 s 评测在 800 iter 两臂均 0 成功率，平均前进 0.80 m（单帧）/0.89 m（历史帧），不具区分度；A/B 判定以训练指标（reward/episode/illegal/goal）+ 部署成本为准。A/B 视频与拼图见 `prep.d/videos/competition/comp_ab_*.mp4`、`contact_competition_ab.jpg`，review 页 §2.5。

## 9. 首次盲策略评测暴露的问题与修正（2026-10-24 17:20）

1. **本地评测动作裁剪 bug**：`run_policy_scene.py` / `run_part2_judged_eval.py` 把 policy raw action 裁剪到 ±1，而训练/部署契约是 `clip_actions=±100`（动作再乘 0.25 的 action scale）。竞争地形策略的动作常超过 ±1，旧本地 judge 因此严重低估策略能力（机器人几乎不动）。**已改为 ±100**；此前所有本地 judge 结果（含 P1 zero-shot）都受此影响，最终裁决必须用修正后的链路重跑。
2. **非法接触/卡死终止阻止障碍学习**：`illegal_contact`（trunk/thigh vs terrain）和 `stuck` 在障碍任务里会终止"爬墙/穿限高杆/上高台"所需的合法身体接触，且障碍列课程长期停在低难度（level ≈0.1）。竞争任务已改为：移除 `illegal_contact` 与 `stuck`，新增 `bad_orientation`（1.05 rad）摔倒终止；保留 time_out/bad_sim_state/out_of_terrain_bounds。深度任务继承同一环境。
3. **任务奖励与命令改造**：竞争地形任务从"随机速度跟踪"改为"固定前进命令 (vx 0.4–1.0, vy=wz=0) + 关闭 command curriculum"，并加入 dense `competition_progress`（权重 1.5，沿 +x 到 far-end goal 的归一化进度）+ sparse `competition_goal`（权重 5.0）；地形课程保留，初始 level 上限从 1 提到 2（障碍列更快见到中难度）。
4. **NaN 崩溃与防护**：blind-final 在总迭代 ~1930 时因 critic obs 出现 NaN 中止（`check_nan`）。已扩展 `bad_sim_state` 同时检查 joint/root **位置**非有限（此前只查速度），并给竞争任务 actor/critic 观测组加 `nan_policy="warn"`（打印 term 后 sanitize，单 env NaN 不再杀死 1024-env 长跑）；从 model_1900 resume 的 600 iter 运行中 NaN 警告为 0。
5. 以上修正意味着 **stage3（从 model_2500 resume +2500 iter）用新的任务定义重训**，之后重新评测；之前所有比赛地形 run 只作过程记录。

**结论（截至 2026-10-24 17:25）**：竞争地形代理训练本身还不足以让策略在真实 Part1/Part2 场景得分（首个 1900-iter 策略本地 judge Part1 0/8、Part2 0/27），主要原因是上述终止/命令/奖励设计问题（已于本小节修正）和训练预算不足；stage3 与后续 depth-final 的 judge 结果将决定是否继续在代理地形上加预算，或改为直接以真实场景为训练分布。

## 10. 第二次训练设计修正（2026-10-24 18:00，stage3 中途发现）

stage3 训练到 ~900 iter 时发现：地形课程（native `terrain_levels_vel`，按"走够距离"升级）与 **goal 终止**冲突——成功穿越障碍后 episode 提前结束，走过的距离达不到距离阈值，导致 8 个障碍列里 `slalom / height_bar / trench / platform` 长期停在 level 0，`bridge/bands/stones/high_wall` 靠"走得多"升到 2.7–3.4。结果就是 policy 根本没训练到这四类障碍，真实 judge 自然 0 分。

修正（stage3b 起生效）：
- 竞争任务**关闭 terrain curriculum**（`cfg.curriculum.pop("terrain_levels")`），改为固定难度分布 `max_init_terrain_level=4`（训练时行 0–4 随机 = 难度 0–0.8；play 仍全 0–5）；
- 保留固定前进命令、progress/goal 奖励、去 illegal/stuck 终止、startup NaN guard。
- stage3 在 ~900 iter 手动停止（checkpoint `cmp_comp_blind_stage3/model_3400.pt`），stage3b 从该 checkpoint resume +2500 iter。

同时记录：stage3 中途策略（900 iter）本地 judge 仍为 Part1 0/8、Part2 0/27，但 Part1 多个障碍状态从"pending"变为"running/fail"（有位移/接触），说明动作裁剪修正后评测链路能反映行为；真实场景得分仍依赖四类障碍的补齐训练。

## 11. 评测窗口敏感性 & 首次出现的能力信号（2026-10-24 18:30）

- 本地 Part2 judge 的每档尝试窗口默认 6 s（冻结自早期诊断；官方规则未写每档时限）。stage3b 中途 checkpoint（总 ~4300 iter）在 6 s 窗口 Part2 0/27；把窗口放宽到 12 s 后出现 **trench 10cm SUCCESS**（机器人跨过 10 cm 沟壑；按 contract 曲线 10cm 是 0 分，但证明能力信号和 judge 灵敏度都正常）。
- 同一 12 s 窗口下 flat_ft-2500（无越障能力）仍 0 成功，说明不是"窗口放宽后随便什么都能过"。
- Part1 的本地 judge 是按"脚本化起点/命令 + 自动通过判据"做的诊断，**Part1 正式比赛是人工遥控**（自动无额外分），所以 Part1 的 0/8 不应当作最终否决依据；Part1 需要的是速度跟踪/鲁棒性（blind 已够用），Part2（仅 RL）才是最终 blind vs depth 能力裁决的主战场。
- 目前 blind 训练汇总（竞争地形代理、新任务定义、stage3b 进行中）：总 ~4300 iter 时 Part2 12s 窗口只有 trench 10cm 一个 0 分项；其余评分档（platform 10cm、stairs 10cm、slope 20°、high wall 20cm、trench 20cm、plum）尚未通过，需要更多训练/更好的 sim2sim 对齐。
- 结论：**评测必须同时报告 6 s / 12 s 两种窗口，并注明官方窗口未定**；最终裁决以 Part2 的"评分档通过数/得分"为主，Part1 用速度跟踪+人工演示质量作辅。

## 12. 阻塞点：代理地形训练→真实场景的迁移失败（2026-10-24 19:00，需要用户决策）

### 12.1 证据

blind（竞争地形代理，从 800-iter A/B 臂一路续训到 stage3b 结束，总 ~6800 iter）的本地 judge 结果（动作裁剪已修正、命令按 contract 固定）：

| checkpoint / 阶段 | Part1（8 障碍自动诊断） | Part2（6 s 窗口） | Part2（12 s 窗口） | 训练侧指标 |
|---|---:|---:|---:|---|
| model_1900（旧任务定义） | 0/8 | 0/27 | — | reward ~9.7, terrain 0.37 |
| model_2499（旧任务定义，resume 完） | 0/8 | 0/27 | — | reward 10.45, goal 12.2% |
| stage3 中途（新任务定义，~900 iter） | 0/8 | 0/27 | 0/27 | goal 79%, progress 0.22 |
| stage3b 最终（总 ~6800 iter） | **0/8** | **0/27** | **0/27** | reward 11.9, goal 47%, progress 0.21 |
| flat_ft-2500（对照） | 0/2（slope/t_stairs） | 0/27 | 0/27 | — |
| P1 basic（对照） | 0/2 | 0/27 | — | — |

- 关键异常：stage3b 最终策略在本地 Part2 场景里 base z≈0.238 m、tilt≈22°，几乎**趴地/蹲行**（训练里为了钻限高杆/低姿态，学会了低姿态 gait），本地 judge 里基本原地不动 → 全部失败。
- 训练侧 goal_reached 很高（47–79%）、progress 0.21，说明策略在**训练代理地形**上会走会过部分障碍；但真实场景分布（平台高度 0.6–0.8 m 起点、障碍尺寸/接触语义、机器人质量/摩擦）与代理差异大，出现"proxy 上高分、real 上趴地"的退化。
- Part2 judge 12 s 窗口在 stage3b 中途 checkpoint 上出现过 trench 10cm SUCCESS（按 contract 是 0 分档），说明 judge 灵敏度正常；但评分档（platform 10cm=10、stairs 10cm=10、slope 20°=10、high wall 20cm=50、trench 20cm≈150、plum=200）均未通过。
- **Part1 是人工遥控赛项**（自动无额外分），其自动 judge 只作诊断；Part1 需要的是速度跟踪/抗扰动，blind 基础策略是够的。**Part2 才是 blind vs depth 能力裁决主战场**。

### 12.2 深度线现状

depth-final warm start（从 stage3b blind checkpoint、64×48、1024 envs）启动即触发 **Warp CUDA OOM（16 GB）**：64×48 深度渲染 ×1024 env 超过显存；已停止。可行配置：32×32×1024（筛选用的分辨率）或 64×48×512。depth 的最终训练也要在"真实场景训练/代理地形"路线确定后进行。

### 12.3 备选路线（需要用户拍板）

- **A（推荐，针对 Part2 RL-only 1300 分）：直接用真实场景几何训练**。用 `SceneCfg.spec_fn` 把 Part1/Part2 的实际障碍 geometry 注入 mjlab training scene（或按 `config/part2-levels.json` 参数化重建），在真实起点/平台高度/尺寸上训练，奖励用 judge 同款的 region/height 成功条件；随机化起点、障碍档位与速度。代价：工程 ~1–2 天（场景注入/成功判定/课程），GPU 数小时；这是唯一有希望把 Part2 得分从 0 拉起来的路线，也能直接用于 depth 对比（相机看到真实障碍）。
- **B（低成本、收益不确定）**：保留代理地形但修正退化：去掉 height_bar 的"钻"激励/强化 base height 与直立终止、把平台高度/尺寸对齐真实场景、提高 foot clearance；再训 5–10k iter 后重新 judge。可能仍 0 分，但工程小（~半天）。
- **C（保守）**：Part1 维持 blind（人工遥控可用），Part2 用现有 best-effort 策略/回退（大概率 0–低分），把剩余时间投入 Part1 人工演示、答辩与部署稳定性。风险：Part2 1300 分基本放弃。

**建议**：选 A，并把 Part2 作为 RL 主战场；Part1 用现有 blind 基础策略（flat_ft/p1）做人工遥控，不追求自动 judge 分。请用户确认路线（A/B/C）以及是否接受"A 需要 1–2 天额外工程 + GPU 时间"。

### 12.4 抗退化修复后的复查（2026-10-24 19:45，stage4）

针对 stage3b 的"趴地/蹲行"退化（base z≈0.24 m、tilt≈22°）做了修复：限高杆净空提高到 0.55–0.60 m（不再需要爬行）、`base_height` 权重 −1→−4、`foot_clearance` −0.01→−0.03、训练难度分布 rows 0–3；从健康走姿 checkpoint（model_2499）resume 1800 iter。结果：

- 平地步态恢复：本地 flat 场景 5 s 前进 1.24 m、base z=0.421 m、tilt=6.1°（stage3b 为 z=0.235、tilt=21.6°）；
- 竞争地形训练指标：reward 14.33（历次最高）、base_height 惩罚 −0.009、goal_reached 51%、NaN 0；
- **真实场景 judge 仍为 0**：Part1 0/8；Part2 6 s 0/27、12 s 0/27（机器人会动、会碰撞，但没有通过任何成功档）。
- 结论：抗退化修复解决了"趴地"问题，但**代理地形训练仍不足以让策略通过真实 Part1/Part2 的成功判据**；路线 A（直接用真实场景几何训练）仍是推荐路径，需要用户确认后执行。

## 13. 步态诊断与"借用开源基座"建议（2026-10-24 20:35）

- **后腿拖地实测**：自训 stage4 / blind_yaw 的 RL/RR foot lift 只有 3–4 mm（FL 80–96 mm、FR 38–76 mm），HIM `best.pt` 为 97/93/28/62 mm；自训步态退化为"前腿拉、后腿拖"。
- **限高杆已失真**：抗退化补丁把净空提到 0.55–0.60 m（高于站立高度），视频里杆在狗身上方，和真实 Part1 的低限高不一致；恢复低净空时需要用 terrain_type 掩码限制低姿态只出现在限高杆列，或把低头拆成单独技能。
- **yaw/vy 命令实验**：800 iter 后代理成功率 18.75%→31.25%，但 yaw 跟踪仍只有 ~0.05 rad/s，且后腿拖地未改善 → 先修基座步态，再谈转向/高层大脑。
- **depth 显存**：32×32×1024 已可训练（300 iter smoke 通过），warm-start 45→109 维机制工作；64×48 需 512 envs。
- **开源调研**：见 `docs/reference/open-source-locomotion-survey.md`。核心结论：优先借用**同机器人同契约的 `best.pt`（HIM）**做基座/教师，其次移植 **MuJoCo Playground / mjlab / legbot_lab（TS recipe）**；IsaacGym 系仓库（legged_gym/unitree_rl_gym/parkour 等）在 RTX 5060 Ti 上不建议尝试；导航"大脑"可用 Navigation Model Zoo（ONNX `[v,ω]`）或 Nav2，但对本次比赛优先级最低。

## 14. best.pt 基座审查（P0，2026-10-24 21:00）

- **best.pt 结构**（TorchScript）：输入 270-D 历史（frame-major，最新帧在前）；内部 `estimator`(270→128→64→19，输出 vel3 + latent16) + `actor`(64→512→256→128→12；输入 = 最新 45-D 观测 + vel3 + normalize(latent16)）。**与我们 hist 任务 270-D actor 的普通 MLP 不同**，不能直接 state-dict 热启动；需要"复刻 HIM 结构（可微）+ 我们的 term-major→HIM frame-major 排列"或做教师蒸馏。
- **零样本审查（我们的新奖励环境 `black-competition-hist`，270-D play env，12 s，16 env）**：
  | 难度 | 成功率 | 摔倒率 | 平均前进 | 平均每步奖励 |
  |---|---:|---:|---:|---:|
  | level 0/1 | 12.5%（2/16；height_bar 50%、platform 50%） | 0% | 1.16 m | 0.0136 |
  | level 2/3 | 0% | 0% | 0.86 m | 0.0084 |
  - 说明：best.pt 在我们的新奖励环境里**没有摔倒/发散**（无退化迹象），但也和自训策略一样过不了桥/墙/沟/桩；它的优势在步态质量（四足 lift 97/93/28/62 mm vs 自训 96/38/3/4 mm）与真实 Part2 扩展窗口 8/20。
  - 审查脚本：`nwwolf_mjlab_training_release/scripts/agent_scripts/audit_history_policy.py`（可对任意 HIM 270 策略做零样本 competition 评测；含 perm 转换）。
- **热启动方案（待实施）**：在训练仓实现 `HimActor`（estimator+actor，加载 best.pt state_dict，内部把 mjlab term-major 270 转 HIM frame-major），用 rsl_rl PPO 在我们的奖励上 fine-tune；训练中持续监控：摔倒率、四足 lift（后腿 >20 mm）、每列成功率、reward 分项（base_height/termination/progress 是否被 hack）、最终 judge。退化即回滚。

---

## 附：Part2 训练地形审计（proxy vs 官方能力场）

结论：**当前 `black_competition_terrain_generator_cfg` 不是竞赛地形的复制品，而是简化/近似版；不能再把 proxy reward 当作真实通过信号。** 本轮暂停训练，先做逐地形、逐难度核对。

## 权威来源

官方地形来自 `ReadOnly.d/Downloaded.d/terrain.zip`，本地展开在 `@20261019_locomotion/assets/terrain/part2/ability_field/`：

- `map.xml`：实际场景 geom（尺寸、mesh、位置）。
- `labels/*.png`：官方能力档位标注卡。
- `official_catalog.yaml`：档位映射。

`assets/terrain/part2/levels/*.xml` 是此前自建的**简化关卡**，不是官方地形；`blackW` 训练里的 proxy terrain 又是另一套简化参数。三者不一致。

## 逐地形差异

### high_platform

| 来源 | 10/20/30/40cm 实际几何 |
|---|---|
| 官方 `map.xml` | 单块 box，`size=(0.75,0.8,h/2)`，顶面 1.5×1.6m，中心在 lane 前 2.5m 附近；无辅助台阶 |
| 当前 proxy | 先放 0.35×0.7m 半高辅助台阶，再放 0.7×0.7m 平台；高度 0.10+0.30×difficulty |
| 本地 level XML | 单块 1.2×1.2m，低于官方 1.5×1.6m |

官方 40cm 卡明确写“平台 150×160cm”；proxy 的平台只有 70×70cm，并且多了一个真实场地没有的半高台阶，会直接教出错误的踩台阶策略。

### high_wall

| 来源 | 几何 |
|---|---|
| 官方 | `cross_bar_*`：宽 1.4m、厚 0.12m、高 0.10/0.20/0.30/0.40m 的窄墙 |
| 当前 proxy | 厚 0.06m、横贯整个 8m 地形块、高度只到 0.30m |
| 本地 level XML | 厚 0.10m、宽 2.0m、位置 x=2.5 |

proxy **根本没有 40cm 档**；厚度/宽度也不同，不能用来训练高墙。

### slope

| 来源 | 20/30/35/45° 几何 |
|---|---|
| 官方 | mesh 楔形，水平长 2m、宽 1.4m，升高 = 2×tan(angle)：0.728 / 1.155 / 1.400 / 2.000m，后面接 0.8m 平台 |
| 当前 proxy | `HfPyramidSlopedTerrainCfg` 的高程场金字塔，diff 0→1 扫到 45°，不是带平台的直斜坡 |
| 本地 level XML | 水平长 1.5m、宽 1.2m，升高 0.546 / 0.866 / 1.050 / 1.500m |

官方 45° 是水平 2m、升高 **2m**，本地只有 1.5m；proxy 是另一种坡度形状。此前“slope 35 能过、45 不能过”的结论不能直接迁移到官方 45°。

### stairs

| 来源 | 10/15/20/30cm 实际几何 |
|---|---|
| 官方 | 6 级，单级高度 = 档位，踏面 0.30m，总高 = 6×档位：0.60 / 0.90 / 1.20 / 1.80m |
| 当前 proxy | `BoxPyramidStairsTerrainCfg`，台阶高度约 0.05+0.18×difficulty，和官方 6 级结构不一致 |
| 本地 level XML | 6 级但总高只有 0.10/0.15/0.20/0.30m，约是官方总高的 1/6 |

这是本轮最严重的差异之一：本地“stairs_30cm”只有 30cm 总高，官方是单级 30cm、总高 180cm。此前 stairs 的 success 完全不能说明能过官方 30cm 楼梯。

### trench

| 来源 | 10/20/30cm 实际几何 |
|---|---|
| 官方 | 净宽 0.10/0.20/0.30m，深 0.30m，通道宽 1.4m；entry/exit 各有 1m 楔形坡 |
| 当前 proxy | gap 0.15–0.35m（10cm 档起点就不对）、深 0.30m、中心在 lane 前 1.4m |
| 本地 level XML | gap 0.10/0.20/0.30m、深 **0.60m**、通道宽 2.4m、无 entry/exit 坡 |

### Part 1 height_bar（顺带核对）

| 来源 | 数值 |
|---|---|
| 官方 `part1_scene.xml` | 横杆中心 z=0.325m，半径 0.015m，杆底约 **0.31m**，门柱高 0.31m |
| 当前 proxy `HeightBarTerrainCfg` | clearance 0.60→0.55m，杆底约 0.55–0.60m |

proxy 限高杆比真实高约 0.25–0.29m；此前的“限高杆过高”问题也确认存在。

## 训练/评测现状

- 训练 reward 和 success 用的是 proxy 的 `x>goal_x` 稀疏规则，不是 judge 的 platform/wall/slope/gap 条件；reward 上升不等于真实通过。
- 课程没有按用户要求做“简化档 100% 成功后再升档”：`TerrainGeneratorCfg(curriculum=True)` 是距离/地形级课程，我们另外设置的 `max_init_terrain_level` 只是初始行，不是成功率门控。
- 之前的失败档位（用 proxy/本地 XML 评测，结论仅对错误几何有效）：
  - proxy `comp_high600`：high_platform 10/20/30 过，**40 未过**；slope 20/30/35 过，**45 未过**；trench 10/20 过，**30 未过**；高墙和楼梯均未过。
  - `comp_lane300`：stairs 10/15/20/30 过（但本地 stairs 几何错误，无效）；slope 20/30 过。
  - exact 任务（此前用本地 XML 尺寸建）：platform/slope 的 `competition_goal_reached` 长期 0；现在看是几何本身就不对，不能作为官方结论。

## 下一步（需确认后执行）

1. 以 `map.xml` + `labels` 为唯一权威，重建训练 terrain 和本地评测关卡：
   - high_platform：1.5×1.6m 单块，无辅助台阶，10/20/30/40cm；
   - high_wall：1.4m×0.12m，10/20/30/40cm；
   - slope：2m 水平长、1.4m 宽，20/30/35/45°，升高 2×tan；
   - stairs：6 级 × 单级档位、踏面0.3m，总高6×档位；
   - trench：0.1/0.2/0.3m 净宽、0.3m 深，入口/出口楔形坡，通道1.4m；
   - Part 1 height_bar：杆底 0.31m。
2. 每一档单独做 success-gated 课程：先低档、成功率达标（例如连续100次/≥99%）才进入下一档；不再用混合 proxy 的稀疏 x 奖励。
3. 训练前先逐档渲染训练 terrain 截图给你确认，确认后才用远程 GPU。
