# Run Ledger（训练/评测 run 账本，只追加）

> 现有 run 的细节仍在 `docs/training/experiments.md`；本表只做"一行一个 run + 可追溯字段"。
> 新 run 由 `/comp-train-loop` 追加；评测结果由 `comp_score.py` 写 `SCOREBOARD.md`。

| run_id | 日期 | task | 初始化 | envs | iters | 时长 | 训练仓 commit | 导出 sha256 | eval policy_id | 总分 | 状态 |
|---|---|---|---:|---:|---|---|---|---|---|---:|---|
| `baseline-2000` | 2026-10-20 | `black-flat` | 从零 | 4096 | 2000 | 47:19 | 训练仓 `24c7f16`（未改） | `ac4652b8c5bc…` | — | — | EVAL_DONE（flat gate 通过） |
| `baseline-rough-3999` | 2026-10-20 | `black-rough` | flat `model_1999` | 4096 | 3999 | 1:17 + 恢复 | 训练仓 `24c7f16` | `b34b03e5ae71…` | — | — | EVAL_DONE（G3 未通过） |
| `flat_ft_mirror01_footclear_500` | 2026-10-21 | `black-flat` | baseline `model_1999` resume | 2048 | 500 | 13:00 | 训练仓 `24c7f16` + mirror/footclear 改动 | `332737933d75…` | `flat-ft-2500-part1-diag-v1` | 0 | EVAL_DONE（诊断） |
| `p1_basic_obstacle` | 2026-10-22 | `black-basic-obstacle` | flat-ft `model_2498` | 4096 | 1500 | 1:11 | 训练仓 fork（`model_3997`） | `8deb41a6ab3b…` | `p1-basic-obstacle-part1-diag-v1` | 0 | EVAL_DONE（诊断；slope/stairs 未过） |
| `p1_basic_obstacle_cont` | 2026-10-22 | `black-basic-obstacle` | `model_3997` resume → `model_5496` | 4096 | 1500 | 1:11 | 训练仓 fork | `035749ffab32…` | `p1-cont-part1-diag-v1` | 0 | EVAL_DONE（诊断） |
| `eval-only:part1-v2` | 2026-10-22 | — | 复用 flat-ft-2500 | — | — | — | 训练仓 `24c7f16`（同 v1） | 同 `332737933d75…` | `flat-ft-2500-part1-diag-v2` | 0 | EVAL_DONE（V2 judge 诊断） |
| `eval-only:part2-v2` | 2026-10-22 | — | 复用 flat-ft-2500 | — | — | — | 训练仓 `24c7f16`（同 v1） | 同 `332737933d75…` | `flat-ft-2500-part2-diag-v2` | 0 | EVAL_DONE（V2 evaluator 诊断；20 档全失败） |
| `eval-only:course-v2` | 2026-10-22 | — | 复用 flat-ft-2500 | — | — | 94 s | 训练仓 `24c7f16`（同 v1） | 同 `332737933d75…` | `flat-ft-2500-part1-course-diag` | 0 | EVAL_DONE（整场协议诊断；1 次尝试） |
| `e1_ctrl_3997_20261024` | 2026-10-24 | `black-basic-obstacle` | resume p1 run1 `model_3997` | 4096 | 100 | 4:18 | 训练仓 `ab66f9c` + worktree diff（10-22 快照同） | — | — | — | CLEAN（对照：复现 p1_cont 前 100 iter） |
| `e5_5400_20261024` | 2026-10-24 | `black-basic-obstacle` | resume `p1_cont model_5400` | 4096 | 100 | 5:00 | 同上 | — | — | — | CLEAN（action_rate 峰值 0.088） |
| `probe2_5496_20261024` | 2026-10-24 | `black-basic-obstacle` | resume `model_5496` + `BLACK_ANOMALY_PROBE=1` | 4096 | 1（首个 rollout 内 step 29 停训） | — | 同上 + `utils/anomaly_probe.py` | — | — | — | ANOMALY CAUGHT（动作自激证据，见 training-health §7.3） |
| `fixed2_5496_200_20261024` | 2026-10-24 | `black-basic-obstacle` | resume `model_5496` + 三项安全网 | 4096 | 200 | ~12:00（含启动） | 同上 + obs/action clip + `bad_sim_state` | — | — | — | FIXED SMOKE（无 CUDA/NaN；动作饱和 ~300） |
| `eval-only:him-best-v2` | 2026-10-24 | — | 外部 HIMLoco `best.pt` zero-shot（frozen-start + time-extended） | — | — | ~6 min（CPU） | `@20261007_assignment` 权重 md5 `7af7bab2…` | — | — | — | EVAL_DONE（诊断；Part2 ext 300/1300） |
| `depth_plumbing_test_20261024` | 2026-10-24 | `black-basic-obstacle-depth` | 从零（10 iter 内） | 64 | 3 | — | 训练仓 + depth task 改动 | — | — | — | PLUMBING OK（CNNModel actor、obs 45+camera、3 次 PPO update） |
| `cost_smoke_20261024` | 2026-10-24 | `black-basic-obstacle` / `-depth` | 从零（成本测量，各 25 iter） | 1024 / 2048 | 25×4 | 1–3 min/case | 训练仓 + depth task 改动 | — | — | — | COST：blind 1.39 s/iter、depth32 2.12 s、depth64 3.53 s、depth64@2048 6.22 s（15 GB） |
| `depth_100iter_smoke_20261024` | 2026-10-24 | `black-basic-obstacle-depth` | 从零 | 1024 | 100 | 3:19 | 训练仓 + depth task 改动 | — | — | — | SMOKE PASS（100/100、无 CUDA/NaN、mean 2.11 s/iter、32×32） |
| `cmp_blind_500_20261024` | 2026-10-24 | `black-basic-obstacle` | 从零 | 1024 | 500 | 10:35（1.27 s/iter） | 训练仓 + depth/safety 改动 | — | — | — | TRAIN DONE（对照 blind，同 seed/地形/奖励；rollout 视频见 `prep.d/videos/cmp/`） |
| `cmp_depth_500_20261024` | 2026-10-24 | `black-basic-obstacle-depth` | 从零 | 1024 | 500 | 16:17（1.96 s/iter） | 训练仓 + depth task 改动 | — | — | — | TRAIN DONE（对照 depth 32×32；rollout 视频见 `prep.d/videos/cmp/`） |
| `cmp_blind_1500_cont_20261024` | 2026-10-24 | `black-basic-obstacle` | resume `cmp_blind_500 model_499` | 1024 | +1000 | 19:47（1.20 s/iter） | 训练仓 + depth/safety 改动 | — | — | — | TRAIN DONE（总 1500 iter；reward 11.18/ep 801/terrain 1.34/illegal 0.62） |
| `cmp_depth_1500_cont_20261024` | 2026-10-24 | `black-basic-obstacle-depth` | resume `cmp_depth_500 model_499` | 1024 | +1000 | 30:59（1.88 s/iter） | 训练仓 + depth task 改动 | — | — | — | TRAIN DONE（总 1500 iter；reward 12.31/ep 826/terrain 1.46/illegal 0.52；500→1500 的领先缩小） |
| `cmp_depth_3000_cont_20261024` | 2026-10-24 | `black-basic-obstacle-depth` | resume `cmp_depth_1500_cont model_1498` | 1024 | +1500 | 46:08（1.82 s/iter） | 训练仓 + depth task 改动 | — | — | — | TRAIN DONE（总 3000 iter；reward 14.86/ep 910/terrain 1.55/illegal 0.31；简单地形筛选） |
| `cmp_blind_3000_cont_20261024` | 2026-10-24 | `black-basic-obstacle` | resume `cmp_blind_1500_cont model_1498` | 1024 | +1500 | 29:15（1.17 s/iter） | 同上 | — | — | — | TRAIN DONE（总 3000 iter；reward 13.15/ep 851/terrain 1.43/illegal 0.48；简单地形筛选） |
| `cmp_comp_blind_800_20261024` | 2026-10-24 | `black-competition` | 从零（竞争地形 + goal 奖励 + mirror 0.1） | 1024 | 800 | 19:01（1.39 s/iter） | 训练仓 competition_terrain/competition_rewards + env 注册 | — | — | — | TRAIN DONE：reward 9.72/ep 730/terrain 0.310/illegal 0.761/goal 8.7%；**A/B 胜出，作为 final actor 配置** |
| `cmp_comp_hist_800_20261024` | 2026-10-24 | `black-competition-hist` | 从零（竞争地形 + goal 奖励 + mirror 0.1 + 6 帧历史） | 1024 | 800 | 18:41（1.44 s/iter） | 训练仓 competition_terrain/competition_rewards/history task | — | — | — | TRAIN DONE：reward 8.08/ep 640/terrain 0.347/illegal 0.954/goal 4.7%；A/B 落败，不进入最终选型 |
| `cmp_comp_blind_final_20261024` | 2026-10-24 | `black-competition` | resume `cmp_comp_blind_800 model_799` +1700 | 1024 | +1700 | 25:05 后崩（iter 1129） | 竞争地形/奖励/termination 首版 | — | — | — | CRASH：critic obs NaN（~总 1930 iter）；已加位置检查+obs guard |
| `cmp_comp_blind_final2_20261024` | 2026-10-24 | `black-competition` | resume `cmp_comp_blind_final model_1900` +600 | 1024 | +600 | 13:56（1.39 s/iter） | 同上 + NaN guard | — | — | — | DONE：总 2500 iter；reward 10.45/goal 12.2%/illegal 0.65；NaN 警告 0；本地 judge Part1 0/8、Part2 0/27（动作裁剪修正后） |
| `cmp_comp_blind_stage3_20261024` | 2026-10-24 | `black-competition`（新任务定义） | resume `cmp_comp_blind_final2 model_2499` +2500 | 1024 | +2500 | ~58 min 预计 | 新：固定前进命令+progress/goal 奖励+去 illegal/stuck 终止+init level 2 | — | — | — | RUNNING（17:35 起） |
| `cmp_comp_blind_stage3b_20261024` | 2026-10-24 | `black-competition`（固定难度分布 rows 0–4，无 terrain curriculum） | resume `cmp_comp_blind_stage3 model_3400` +2500 | 1024 | +2500 | ~58 min 预计 | 同上 + curriculum 修正 | — | — | — | RUNNING（18:00 起；stage3 在 ~900 iter 手动停止以修 curricula） |
| `cmp_comp_blind_stage4_20261024` | 2026-10-24 | `black-competition`（抗退化：限高杆 0.55–0.6、base_height −4、foot_clearance −0.03、rows 0–3） | resume model_2499 +1800 | 1024 | 1800 | 40:55（1.36 s/iter） | 同上 + 抗退化修正 | — | — | — | TRAIN DONE：reward 14.33/base_height −0.009/goal 51%；平地步态恢复（z 0.42/tilt 6°），真实 judge 仍 0 |
| `cmp_depth_final_warm_20261024` | 2026-10-24 | `black-competition-depth` | blind stage3b warm start，64×48 | 1024 | 1500 计划 | — | depth task（新任务定义） | — | — | — | STOPPED：Warp CUDA OOM（64×48×1024），需 32×32 或 512 envs |
| `cmp_depth_warm_1500_20261024` | 2026-10-24 | `black-basic-obstacle-depth` | warm start from `cmp_blind_1500_cont model_1498`（CNN latent 列置零） | 1024 | 1500 | 46:24（1.83 s/iter） | 训练仓 + `depth_warm_start.py` + runner env-var 入口 | — | — | — | TRAIN DONE（3000等效 reward 12.83/ep 846；≈blind@3000、< depth-from-scratch；简单地形筛选） |

## 单开关说明

| run_id | 相对上一版改了什么（只许一项） | 预期 | 实际 |
|---|---|---|---|
| `flat_ft_mirror01_footclear_500` | 加 mirror loss 0.1 + foot_clearance | 步态对称性/离地高度改善 | 见 docs/training/experiments.md |
| `p1_basic_obstacle` | 混合 terrain generator（flat+smooth slope+stairs，无 rough/discrete） | 坡度/台阶通过 | 部分改善，未过 gate |
| `eval-only:part1-v2` / `part2-v2` / `course-v2` | 只替换评测器（judge V2 + 参数化 Part2 档位 + 整场协议），策略未变 | 得到可审计的 0 分诊断，验证评测链路 | 与 v1 一致（flat 策略 0 分），链路跑通 |
| `fixed2_5496_200_20261024` | 相对 `probe2` 只加三项安全网（obs clip / action clip / bad_sim_state 终止） | 同一崩点不再 NaN/CUDA 710 | 见 training-health §7.5 |
| `cmp_blind_500` / `cmp_depth_500` | 唯一差异是 actor 观测（45 维本体 vs 45 本体 + 32×32 深度 CNN latent）；同 seed/地形/奖励/envs/iters，从零 | 量化深度相机在短训练预算下的代价/收益 | 500 iter：depth 全面更好但 1500 iter 后领先缩小（见 camera-depth §7/§7.1） |
| `cmp_*_1500_cont` | 从各自 500 checkpoint 各 +1000 iter（不换地形/奖励/seed） | 看 depth 优势是否随训练保持 | 领先缩小到 +3%~+16%，成本 ×1.56；blind 算力效率更高（§7.1/§10） |
| `eval-only:him-best-videos` | 只加录像（不改评测口径/起点/时间尺度） | 让用户能二次检查 zero-shot 评测过程 | 28 段视频 + `index.html`；分数与无录像时一致（Part1 0/8、Part2 ext 300/1300） |
| `deploy-him-best` | 控制仓库只加 1 个策略循环配置 + 窗口 geom group 可见性 | 能在演示 GUI 手动试操作 best.pt | 契约核对通过、GUI GetUp→Running→行走验证，见 `docs/training/deploy-him-best.md` |

| `blackw_comp_blind_v0` | 新增 blackW 16 关节机器人/混合轮腿 action/57×6 actor observation，任务换为 blackW competition | 首次验证训练链路+学习信号 | 训练到 ~700 iter；外部严格 judge 出现零散成功，后期出现绕障退化 |
| `blackw_comp_lane_v0` | 只加 lateral lane termination（|y|>0.9 终止），从 `blackw_comp_blind_v0/model_200` resume | 阻止绕过障碍、提升真实 Part2 | model_300 strict 300 分、model_500 strict 200 分 |
| `blackw_comp_high_v0` | 只把 `max_init_terrain_level` 提到 5（高台/高坡/深沟行），从 lane model_500 resume | 攻高价值高档位 | model_600 strict 350 分；组合最优约 750/1300，40cm/45°/30cm/plum 仍缺 |

| `terrain_audit_20261025` | 对照官方 `terrain.zip/map.xml` 与训练 proxy/本地 level XML | 决定是否继续训练 | **暂停**：proxy 与官方地形不一致（platform 尺寸/台阶、wall 40cm、slope 长度、stairs 总高、trench 深度、height_bar 杆底）；详见 `docs/training/part2-terrain-audit.md` |

| `blackw_official_platform_pilot_v0` | 官方 `map.xml` 高台几何（1.5×1.6，无辅助台阶），从自训 high model_600 warm-start | 验证官方真实几何可直接训练 | 300 iter 后 goal=0，未爬上 10–16cm；rollout 视频已录；需低档 success-gated/更长训练，视频 `prep.d/videos/blackw_official_pilot/official_platform_pilot.mp4` |

## 失败 run

| run_id | 现象 | 根因 | 处理 |
|---|---|---|---|
| `baseline-rough-2000` | `normal expects std >= 0` + Warp 710 崩溃 | 数值不稳定（见 training-health §3） | 从 checkpoint 恢复；后续加 reward/return 安全网 |
| `rough_from_p1_20261023` / `basobstacle_from_p1_20261023` / `smoke100_resume_20261024` | resume `model_5496` 后 100 iter 内 Warp 710；action_rate 离群 | 动作经 last-action 观测自激（training-health §7.3） | 加 obs/action clip + `bad_sim_state`；`fixed2` 200 iter 通过 |
