# stage4 blind 策略迁移诊断（2026-10-24 20:00）

> 被测策略：`prep.d/models/competition_blind_stage4/policy.pt`（45-D 单帧 actor，竞争地形代理上累计训练约 8.3k iter：A/B 800 + final 1700 + resume 600 + stage3 900 + stage3b 2500 + stage4 1800；stage4 前修正了趴地步态）。
> 对应 checkpoint：`logs/rsl_rl/black_velocity/2026-10-24_19-01-52_cmp_comp_blind_stage4/model_4298.pt`。

## 1. 速度指令输入：训练与真实场景都有，不是缺失通道

- **训练环境**（`black-competition` / `black-competition-depth`）：actor 45 维观测 = `commands(3) + ang_vel(3) + projected_gravity(3) + joint_pos(12) + joint_vel(12) + last_action(12)`，commands 的 scale 为 `[2.0, 2.0, 0.25]`（`env_cfgs.py` 的 `BLACK_ACTOR_OBS_TERM_ORDER` 与 `_configure_observations`）。
- 但竞争任务为了对齐 goal 方向，训练时**只给固定前进指令**：`vx ∈ (0.4, 1.0)`、`vy = 0`、`wz = 0`，且关闭 command curriculum（见 `competition-terrain-and-symmetry-plan.md` §10）。
- **真实场景评测**（`run_policy_scene.py` 的 `obs()`）：同样是 45 维，命令项为 `command * [2.0, 2.0, 0.25]`；Part1 judge 每条任务给 `(0.3–0.5, 0, 0)`，Part2 judge 给 `(0.5, 0, 0)`。
- **结论**：训练和真实场景**都有速度指令输入**；差别是训练中 `vy/wz` 恒为 0，所以策略**不会响应 yaw**（见 §3 的 rl_sar 实测：转向指令完全无输出）。depth 任务的 obs 合约继承同一套，同样含 commands；但 **depth-final 从未在竞争地形上真正训练**（64×48×1024 启动即 Warp OOM，只跑了 1 iter），现有 depth 只在简单地形筛选过，因此"depth 迁移失败"目前没有可诊断的竞争地形 depth 策略。

## 2. 代理地形逐任务成功率与失败原因（stage4 策略，play env，12 s/attempt）

评测：`prep.d/results/competition_eval_stage4_levels01.json` / `..._levels23.json`（每个障碍列 2 个 env；0/1 与 2/3 两档难度）。

| 障碍列 | level 0/1 成功率 | level 2/3 成功率 | 失败原因（levels 0/1） |
|---|---:|---:|---|
| 6 bridge_blocks | 0% | 0% | 1 timeout + 1 stuck |
| 7 bridge_bands | 0% | 0% | timeout |
| 8 height_bar | **100%**（2/2） | 0% | — |
| 9 high_wall | 0% | 0% | timeout |
| 10 slalom | **50%**（1/2） | 0% | 1 timeout |
| 11 trench | 0% | 0% | timeout |
| 12 platform | 0% | 0% | timeout |
| 13 stepping_stones | 0% | 0% | stuck |
| **总体** | **18.75%**（3/16） | **0%**（0/16） | timeout 10 / stuck 3 / success 3 |

**代理地形上能过的只有"低头穿限高杆"和"简单绕柱"两类**；桥、墙、沟、高台、梅花桩全部不会过（无摔倒，只是 timeout/stuck）。说明训练没有学出"爬/跨"类技能，而不是控制不稳。

## 3. 真实场景失败原因与占比

**Part2**（`part2_stage4_final_{6s,12s}.json`，24 次/窗口，6 类 × 4 档）：

| 窗口 | 成功率 | 失败原因 |
|---|---:|---|
| 6 s | 0/24 | **timeout 24/24（100%）** |
| 12 s | 0/24 | **timeout 24/24（100%）** |

无 fall、无 lateral bypass，全部是"在窗口内没有到达成功区域/没有完成越障"——机器人会走会动（12 s 内前进 ~0.5–1.5 m），但不会爬台/跨沟/上墙。

**Part1**（`part1_stage4_final.json`，8 个脚本化起点）：

| 原因 | 次数 |
|---|---:|
| 未完成（judge running/pending，窗口内未过） | 6/8（75%） |
| `two_feet_ground`（≥2 足触地失败语义） | 2/8（25%，bridge_blocks、slope） |

## 4. 可部署 .pt 与 rl_sar 实测

- 交付包：`prep.d/models/rlsar_stage4/`（`policy.pt` + `config.yaml` + `README.md` + `check_walk_flat.log`）。
  - `policy.pt`：actor-only TorchScript，`[1,45] -> [1,12]`；`config.yaml` 与 assignment `black/himloco` 一致，仅改 `model_name` 和 `observations_history: [0]`（单帧）。
  - 用法：拷到 `@20261007_assignment/ws/src/rl_sar/policy/black/himloco/` 覆盖 config 后跑 `pixi run python @20261007_assignment/scripts/agent_scripts/check_walk.py --realtime false`；诊断后 `git checkout -- .../himloco/config.yaml` 恢复（测试后已恢复，assignment repo 干净）。
- **rl_sar check_walk（flat scene）结果**：起身/站立/策略周期/趴下/全速节拍通过；**转向指令 1.0 rad/s 完全不跟随**（陀螺 z ≈ 0），另有一次运行因 z 最低 0.314 m / 倾角 24.4° 未过"RL 段没摔"阈值 → 前进能走、转向不会。
- 该失败与训练时 `wz=0` 一致，不是 rl_sar 集成问题。

## 5. 可视化（诊断视频）

目录：`prep.d/videos/diagnosis_stage4/`（16 段 mp4 + `contact_diagnosis_stage4.jpg` + `index.html`）：

- 代理地形 4 段：bridge_blocks / height_bar / high_wall / stepping_stones（难度 0.8，`stage4_blind_*`）；
- 真实 Part1 7 段：bridge_blocks、bridge_bands、height_bar、high_wall、slope、t_stairs、slalom（脚本化起点/命令，`p1_*`）；
- 真实 Part2 5 段：high_platform 10 cm、stairs 10 cm、slope 20°、high_wall 20 cm、trench 20 cm（`p2_*`）。

## 6. 迁移失败的根因判断（按证据强度）

1. **技能缺口（最强）**：代理上只有 height_bar/slalom 能过，桥/墙/沟/台/桩 0% → 策略没有"爬/跨"能力；真实 Part2 需要爬 10–40 cm 台/墙/沟，所以 100% timeout。
2. **命令域不匹配**：训练 yaw=0，rl_sar 手动转向指令无响应 → Part1 人工遥控无法转向（若继续用这个策略，Part1 只能直行，不满足赛项）。
3. **场景分布差**：真实 Part2 起点在 0.55–0.79 m 高的平台上，代理地形从地面出发；平台高度/起始相对高度不一致，进一步削弱迁移（证据：本地 judge 里 base 高度稳定但不会上台阶/台面）。
4. **depth 未验证**：depth-final OOM，未在竞争地形训练 → 尚不能下"depth 不行"的结论；需先定 32×32/512 env 配置。

## 7. 建议（与 route A/B/C 对应）

- **A（推荐）**：真实 Part1/Part2 场景几何训练 + **恢复 vy/wz 命令**（至少给 yaw ±0.5 rad/s、vy ±0.3）以便人工遥控；Part2 用 judge 同款 success 判定做奖励。
- 若先走 B：给代理任务补"爬台/跨沟/上墙"的优先课程（当前 8 类同时均匀采样导致爬类技能没学出来），并加 yaw 命令；但此前 8.3k iter 的证据不支持乐观。
- 部署侧：rl_sar 集成本身已验证可用（`policy.pt` 前进正常），恢复 yaw 训练后即可用于 Part1 手动遥控诊断。
