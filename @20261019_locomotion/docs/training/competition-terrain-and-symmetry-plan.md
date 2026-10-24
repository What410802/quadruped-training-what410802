# 比赛地形覆盖、步态对称性与 blind vs depth 最终裁决（2026-10-24 修订）

> 触发：用户指出两个方法论问题——① 当前训练地形只有 flat / smooth slope / stairs，不能反映 Part1 的绕柱、桥、限高杆、高墙、砂砾等和 Part2 的高台/沟壑/梅花桩，而这些恰是深度视觉最可能有用的地方，用它裁决 blind vs depth 不成立；② 奖励里没有对称性约束，后腿"始终一前一后"（symmetry breaking）仍在；③ 是否应在"方法论拉满（接近最终模型）"后再比较两条线，以及这样会不会就已经是最终策略。
> 本文给修订后的训练地形、对称性修复和最终实验设计。当前在跑的 3000/warm-start 只作为**简单地形筛选**，不作为最终裁决依据。

## 1. 为什么现在的地形不足以裁决

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

**判据**：以 judge 总分为主（Part1 8 项 + Part2 20 档），辅以 0 摔倒/失效 <1%、对称性指标达标、推理成本；若两条线分数接近（<5%），选 blind（成本低、风险小）。不再用训练 reward 或"简单地形曲线"直接裁决。

## 5. DR 的位置

仍在**地形课程稳定之后**做（原 `camera-depth.md` §9）：先把 `black-competition` 上的策略训到能走/少摔，再用强 checkpoint 做 DR fine-tune（深度渲染噪声/量化 → 丢帧/延迟 → 外参 → 分辨率/FOV → 遮挡，单开关逐项），避免早期学习被 DR 拖慢、归因不清。

## 6. 需要补的评测/工程项

1. **`black-competition` + `black-competition-depth` 任务**：terrain generator（§2）、depth 相机沿用 `camera_depth.py`、runner 复用；
2. **本地深度推理评测**：把训练好的 CNN actor 导出（rsl_rl `CNNModel` 两输入 obs group），在本任务 MuJoCo 场景里渲染 32×32 深度（MuJoCo Python `Renderer` 的深度渲染）+ 同一归一化/无命中规则，再跑现有 Part1/Part2 judge；blind 评测链路已通；
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
| 竞争地形代理 | `src/alldog_mjlab/tasks/velocity/black/competition_terrain.py`（8 个自定义 SubTerrainCfg + 复用 flat/slope/stairs/gravel，共 14 列 × 6 行、难度 0..1） | CPU 几何检查通过（634 geoms、goal patch 48/84 = 8 障碍列 × 6 行）；GPU 3-iter smoke 通过 |
| 任务 | `black-competition` / `black-competition-depth`（+ `-hist` 6 帧历史变体）注册在 `__init__.py` | smoke：blind 3 iter、depth 3 iter、history/depth-hist + mirror 0.1 各 2 iter 均 rc=0、无 NaN/CUDA |
| 任务成功奖励 | `competition_rewards.py`：goal flat patch（8 个障碍列）→ 稀疏 `competition_goal` 奖励（权重 3.0）+ `competition_goal_reached` 终止；非障碍列用 spawn origin 填充并按最小距离 0.8 m 屏蔽 | smoke 的 `Episode_Reward/competition_goal`/`Episode_Termination/competition_goal_reached` 项存在（迭代太短，成功数 0，符合预期） |
| 历史帧 | `black-competition-hist`（270 维 actor）、`black-competition-depth-hist`（270+64 CNN） | smoke 通过；`symmetry.py` 已扩展为支持 45×k 历史布局的 mirror loss |
| mirror 0.1 | 环境变量 `BLACK_MIRROR_LOSS_COEFF=0.1` 作用于所有新 run | smoke 日志 `[INFO] mirror-loss symmetry enabled: coefficient=0.1` |
| 预览视频 | `prep.d/videos/competition/` 12 段（blind/depth zero-shot × 障碍列）+ `contact_competition_preview.jpg`；review 页 §2.4 | 已生成；仅用于地形几何/基线行为检查 |
| 历史帧 A/B | `cmp_comp_blind_800`（45-D）vs `cmp_comp_hist_800`（270-D），800 iter × 1024 envs，mirror 0.1 + goal 奖励 | **RUNNING**（2026-10-24 16:10 起，约 40 min） |

备注：地形代理与官方场景仍有几何/材质/接触差异，最终裁决仍以 Part1/Part2 真实场景 judge 为准；接下来的实现顺序是 "历史帧结论 → blind-final 长训 → depth-final（warm-start/from-scratch）→ judge 对比"。
