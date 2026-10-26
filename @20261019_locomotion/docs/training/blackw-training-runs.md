# blackW 训练 run 记录


## 初始化方式（重要）

- `blackw_comp_blind_v0` 是**从零训练**：启动命令没有 `--agent.resume`，日志中 `Loading model checkpoint` 次数为 0。
- `blackw_comp_lane_v0` 从 `blackw_comp_blind_v0/model_200.pt` resume；`blackw_comp_high_v0` 从 `blackw_comp_lane_v0/model_500.pt` resume；exact/specialist 从 `blackw_comp_high_v0/model_600.pt` resume。
- **没有从官方 blackW 权重续训**：官方 blackW 是 HIM estimator+actor 结构，本仓 PPO actor 是 342→512→256→128→16 的 MLP，架构不兼容；如果要热启动，需要先做蒸馏/结构适配，不能直接 load 官方 `.pt`。

## 训练仓接入（2026-10-25）

远程仓 `bis-ms7e56:~/rc_work/nwwolf_mjlab_training_release` 新增：

- `src/alldog_mjlab/robots/blackw/`：blackW MJCF/STL + 16 关节 `EntityCfg`；剥离 XML 自带 `<motor>`/keyframe，由 MjLab `IdealPdActuator` 管理 16 个 actuator。
- `src/alldog_mjlab/tasks/velocity/blackw/`：
  - `actions.py`：每腿 4 维混合 action（3 位置残差 scale 0.25 + 1 轮速 target scale 10），4 条腿共 16 维，顺序 FL/FR/RL/RR；
  - `env_cfgs.py`：从 black 的 competition 任务复用奖励/command/termination/terrain，替换机器人、feet contact sensor、reset events、actor/critic observation；
  - actor：57 维单帧 × 6 历史（342 维，term-major flatten，训练）/ 部署导出为 frame-major newest→oldest；动作 16 维；
  - task：`blackw-flat`、`blackw-competition`。
- `scripts/agent_scripts/export_blackw_policy.py`：导出 actor 为 TorchScript，按 57 维 frame-major history 重排第一层 Linear 输入；已用 `model_0.pt` 验证 `[1,342] -> [1,16]` 与 SHA256 写入 contract。

## Run: blackw_comp_blind_v0

| 项 | 值 |
|---|---|
| 日期 | 2026-10-25 09:08 CST 启动 |
| 任务 | `blackw-competition` |
| envs | 2048 |
| iterations | 2000 |
| run-name | `blackw_comp_blind_v0` |
| 远程 run 目录 | `logs/rsl_rl/black_velocity/2026-10-25_09-08-44_blackw_comp_blind_v0` |
| 日志 | `logs/blackw/blackw_comp_blind_v0.out` |
| GPU flag | 启动前置 1；训练进程结束后 watcher 置 0 |
| 监控 | `bash-2093` 每 120 s 检查；进程结束自动 `echo 0` 到 `~/5060ti_machine_use_flag.txt` |

备注：terrain 的 hfield 在高接触密度时会打印 `height field collision overflow`，当前不致命（进程/GPU 正常、reward/课程在更新）；若影响接触质量，后续降低 hfield 分辨率或按 black 的 nconmax 策略处理后再训。


## Official-geometry platform pilot（2026-10-25）

- 目标：验证“直接把官方 `map.xml` 几何放进训练”是否可行，而不是继续造 proxy。
- 地形：`ExactHighPlatformTerrainCfg` 按官方 `map.xml` 改为单块 1.5×1.6 m 竖直台、无辅助台阶、lane ±0.70 m；先只做 platform 一个类别。
- 训练：从我们自己的 `blackw_comp_high_v0/model_600.pt` warm-start，2048 envs，300 iter（600→900），run `blackw_official_platform_pilot_v0`。
- 结果：`competition_goal_reached=0`、`platform_height` reward 始终 0，策略没有爬上 10–16 cm 的官方平台；6 s rollout 视频在 `prep.d/videos/blackw_official_pilot/official_platform_pilot.mp4`（默认相机被平台遮挡）；跟随狗 root 的俯视跟踪相机版：`prep.d/videos/blackw_official_pilot/official_platform_pilot_overhead.mp4`。
- 结论：这只能说明**300 iter warm-start 不足以适配官方几何**，不能说明官方几何不可训练；下一步应按用户要求先做低档 success-gated 课程和更长 pilot，同时保留从零/从官方策略蒸馏两种选项。继续用旧 proxy 训练没有意义。

## 速度指令训练现状

当前 blackW competition task 是**命令条件策略**，不是自主策略：

- command 观测：`[vx, vy, yaw_rate]`，归一化 `(2,2,0.25)`；
- `blackw_competition` 训练范围：`vx∈[0.4,1.0]`、`vy∈[-0.3,0.3]`、`yaw∈[-1,1]`，所有 env 为 forward-only（`rel_forward_envs=1.0`）；
- reward 含 `track_linear_velocity_xy` / `track_angular_velocity_z`，同时叠加 proxy 的 `competition_progress` / `competition_goal`；command curriculum 在 competition task 中被移除；
- 部署：rl_sar `/joy` / `/cmd_vel` 连续速度命令进策略；固定动作只用 joystick 前后/转向驱动轮速。

因此，若要“不同地形下遵从速度指令”，不能只加地形，必须把 command 分布和 success 条件一起重做：

1. 官方地形逐档、success-gated；
2. command 范围覆盖部署实际会用到的低速/停止/转向，而不是固定 0.4–1.0；
3. reward 以 body-frame 速度 tracking 为基础，地形 success 作为额外信号；避免用“x 超过 goal”的 proxy 奖励替代 tracking；
4. 如果高档障碍需要瞬时减速/抬轮，允许策略短时偏离 command，但用 tracking 的折扣/分段权重，不要直接取消 command 观测；必要时用 RL skill 模式（仍非固定动作）作为高档位子策略。

## HIM MjLab 接入与 warm-start pilot（2026-10-25）

- 新增 `blackw/him.py`、`him_rl_cfg.py`、`him_runner.py`，注册 `blackw-competition-him`、`blackw-platform-exact-him`；使用 N-W-wolf MjLab HIM 算法（HIMPolicy/HIMPPO/HIMOnPolicyRunner），观测为 actor `[B,6,57]` + estimator velocity，动作16。
- `BLACKW_OFFICIAL_WARMSTART=/path/policy.pt` 可把官方 TorchScript 的 actor/source-estimator 权重直接载入（验证 14 tensor 全匹配，输出 diff 0）。
- Pilot：`blackw-platform-exact-him`，512/2048 envs、官方 platform 几何；512 envs 无 warm-start 50 iter 可跑完；2048 envs 在迭代 24 左右触发 Warp CUDA assert；512 envs + official warm-start 在 ~78 iter 触发同样 assert。无 warm-start 2048 也在 ~24 iter 崩溃。
- 现象：CUDA error 710 `device-side assert`；栈在 HIMPPO update 的 KL 计算，无显式 NaN 日志。已加 `clip_actions=100`；提高 `nconmax=1024/njmax=4096` 无效。
- **CCD 修复**：blackW 轮子 cylinder 与平台 box 的 Mujoco-Warp CCD 在 HIM 探索下触发 assert。`cfg.sim.ccd_iterations=0` 后，256 envs 的 HIM platform 150 iter 可稳定跑完；继续验证 512 envs + official warm-start 跑到 294/300 才再次 assert，说明 CCD 不是唯一来源。
- 修正了一个关键成功判据 bug：exact task 没有注册 `flat_patch_sampling`，`competition_goal` 永远拿不到 goal；补上后训练出现 76% `competition_goal_reached`，但 CCD-off 可能穿模，x-only goal 会误判成功；因此平台 pilot 改成 `official_platform_success = x∈[1.9,3.1] 且 root_z≥0.72`，并移除 x-only goal 奖励/终止。
- 在 CCD-off + official success 条件下：512 envs 从 warm-start 跑 100 iter 稳定；继续 resume 到 321/599 iter 时再次 Warp assert；`official_platform_success=0`、`platform_height≈0`，说明还没有真正爬上 10cm 官方平台。
- 结论：HIM 接入、warm-start、goal/成功判据修复已验证；残余 Warp assert 和平台爬升仍是阻塞，不能把之前 76% 的 x-goal 当成通过率。

## 后续

1. 训练结束后导出最新 checkpoint，用 `prep.d/blackw_validation/run_blackw_part2_judge.py` 在真实 Part2 场景 + 严格 judge 上评测；
2. 若 high_platform/slope/trench 高档位仍不足，继续同任务续训或加难度课程；
3. 训练/导出结果更新本文件与 `status.md`。

## 结果（2026-10-25）

- `blackw_comp_blind_v0`：从零 2048 envs，训练到 ~700 iter 时外部严格 judge 最佳已出现 high_platform 20 / stairs 20-30 / slope 30 等零散成功；后期策略出现绕过障碍退化。
- `blackw_comp_lane_v0`：加 lateral lane termination 后从 model_200 resume，外部严格 judge：model_300 = 300 分（high_platform 20=50、stairs 30=200、slope 30=50），model_500 = 200 分（high_platform 30=100、slope 35=100）。
- `blackw_comp_high_v0`：从 lane model_500 resume，max_init_terrain_level=5（高台/高坡/深沟行）训练 800 iter；model_600 = 350 分（high_platform 30=100、slope 35=100、trench 20=150），model_800 = 200 分，model_900 = 150 分。
- 组合选择（不同策略逐类别）：high_platform comp_high600 30cm/100、stairs comp_lane300 30cm/200、slope comp_high600 35°/100、high_wall 官方 obstacle 40cm/200、trench comp_high600 20cm/150，strict 合计 **约 750/1300**。
- 仍缺：high_platform 40cm、slope 45°、trench 30cm、plum；训练奖励在 proxy 上继续上升但外部严格 judge 不稳定，需继续课程/真实几何训练，不能只用 proxy reward 选型。
- GPU：训练结束已把 `~/5060ti_machine_use_flag.txt` 置 0，`nvidia-smi` 179 MiB/0%，无训练进程。
- 追加 specialist 尝试：`blackw-platform`（只 platform 子地形，max level 5，从 high model_600 resume 400 iter），model_999 外部 strict judge 仍 0/4 档，说明”proxy reward 上升“不等于真实 Part2 成功；不值得继续在同 proxy 上加算力。下一步应先补真实 Part2 几何/成功判据进训练环境，或对官方策略做面向真实场景的蒸馏/微调。
- 又追加 exact Part2 几何任务：`blackw-platform-exact` / `blackw-slope-exact`（从 actual level XML 参数构造，无 helper step；`nconmax=256 njmax=2048`），从 high model_600 resume 约 400 iter：训练 log 的 `competition_goal_reached` 长期为 0，说明 40cm 竖直台 / 45° 实尺坡对当前 blind PPO 仍然学不会；先停止继续烧 GPU，下一步需要 **课程/高度过渡奖励** 或 **官方策略蒸馏/真实场景微调**，而不是继续同配置加 iter。
- 随后把 exact 任务的初始地形行降到 `max_init_terrain_level=1`，并给 exact slope 加 20°→45° difficulty sweep；`blackw-platform-exact` 从 easy 行重训 400 iter，`competition_goal_reached` 仍为 0。当前证据足以说明：继续用同一 PPO/奖励配置加算力没有收益，必须先改训练信号（高度/平台接触奖励）或做 official-policy 蒸馏。

## 速度指令设计（2026-10-25）

当前 blackW HIM/competition 训练使用 **body-frame 3 维速度指令** `[vx, vy, wz]`，不是自主策略：

- flat HIM：继承 base Black 指令范围，`vx` 有 command curriculum；`resampling_time=10 s`；
- competition/platform HIM：固定 `vx∈[0.4,1.0]`、`vy∈[-0.3,0.3]`、`wz∈[-1,1]`，`rel_forward_envs=1.0`，command curriculum 被移除；
- actor 第一帧前 3 维是 `command * (2.0,2.0,0.25)`；
- 例：`cmd=[0.8,0,0]` → actor 看到 `[1.6,0,0]`；杆/固定动作不走这个 policy command。

**没有 `vz` 指令**。理由：

- 官方 blackW / HYNova / N-W-wolf 的轮足策略都是 3 维速度命令，垂直运动由地形、接触和奖励隐式学习；
- `vz` 在腾空/台阶阶段物理上不连续，操作手也没有自然的 z 轴摇杆；
- 加 `vz` 会把 actor command 从 3→4、57→58、estimator target 和部署 contract 全部改掉，官方 `.pt` warm-start 首层形状也会失配；
- 对高端台阶/高台，更合适的是 **height/skill mode**（目标 base 高度或相位）或 terrain-conditioned 自主越障，而不是连续 `vz` 指令。

当前 platform pilot 仍卡在 Warp CUDA assert + 爬升成功信号 0；先修稳定性/奖励，不先加 `vz`。


## HIM 动作 contract 发现（2026-10-25）

官方 blackW / N-W-wolf 的轮速 action scale 是 **有符号**：FL +10、FR -10、RL +10、RR -10（`wheel_forward_sign`）；此前我们的 blackW HIM task 仍沿用自训 comp policy 的 +10/+10/+10/+10，和官方 warm-start 权重不匹配。已在 HIM task 改为官方 signed scale（leg 仍 0.25），部署 HIM 导出也必须用 signed config。

在该修正下，platform easy（平台形状 5–10cm）warm-start 512 envs 300 iter 仍稳定但 `official_platform_success=0`、`platform_height≈0`，说明仅修 action sign 不足以产生平台爬升；还需要平台接触/高度奖励和更明确的越障技能课程。

## 当前阻塞

- HIM 训练在 exact platform 上仍会 residual Warp assert（CCD-on 约 50 iter；CCD-off + std0.3 可稳定数百 iter，但 std0.3 仍非最终配置）；
- 官方 platform 高度 5–10cm 的 success 仍为 0；
- 需要先把平台爬升信号做出来，再谈 40cm/45°/30cm 档位；
- 当前 GPU 已停、flag=0、GPU idle。


## 2026-10-25 15:xx 备注

本地/远程训练状态检查发现另有一个外部进程 `cwd=~/rc_work/part2_team_race`、task `blackw-official`、run `ppo_comp600_official_v0` 正在占用 GPU；它不是本任务启动的，未终止。我们自己启动的 HIM 训练均已停止；远程 `~/5060ti_machine_use_flag.txt` 当前仍为 0，GPU 约 6 GB/85% 被该外部进程占用。


## 2026-10-25 并发 GPU 小批次实验

- 另一个 Agent 的 depth-vision 任务占用 GPU（`~/rc_work/part2_team_race`，约 6GB）。
- 在剩余显存下用 `blackw-platform-easy-him`、256 envs 从 easy signs model_250 resume，
  峰值约 8.6GB / 16GB，显存足够；但 267 iter 时仍触发同一 Warp CUDA assert，不是 OOM。
- 结论：**小批次并发训练显存可行，但 residual Warp assert 仍阻塞长训**；不能靠减 envs 绕过。
- 该次训练已停止；外部 depth-vision 进程未被终止。


## 2026-10-25 HIM 小批次诊断（并发外部 GPU）

- 外部 depth-vision Agent 持续占用 GPU（约 6GB）；我们把 blackW HIM 降到 64 envs 并发，峰值约 7GB，显存可行。
- 给 `WheelLegAction.apply_actions` 加 `nan_to_num` guard 后：
  - CCD-on、64 envs、300 iter 可稳定跑完；
  - CCD-off、64 envs、300 iter 同样稳定；
  - 说明此前 residual Warp assert 与 NaN/Inf action 有关，guard 是必要修复。
- 新增微平台（1–3cm）验证：lane 从 0.8 缩到 0.6、CCD-on、64 envs、200 iter；
  - `competition_progress` 约 1.2（到达平台 region 附近），但 `official_platform_success=0`、`platform_height=0`；
  - 说明当前 HIM 策略/几何没有真实抬升平台，或 root z 阈值/接触仍不对；不能把 x-progress 当成平台通过。
- 平台 5–10cm 的 easy 阶段同样 300 iter 无 success；需要接触/高度奖励或更明确的爬升技能，而不是只加迭代。


## 2026-10-25 平台诊断：base height contract bug

- 发现 blackW 训练一直沿用 Black 点足任务的 `base_height_target=0.43 m`；blackW 正常站立 root 约 0.69 m，导致策略被奖励成蹲伏/爬行。已把 blackW 的 base_height target 改为 **0.69 m**，并给平台任务加 `low_base_height` 终止、直线指令（vx=0.5, vy=0, yaw=0）。
- HIM 权重映射再次用 env 实际观测核对：`HIMPolicy.as_jit()` 与官方 TorchScript 在同一个 `[1,6,57]` history 上输出 `max_abs_diff=0.0`，说明映射/观测拼接本身是对的。
- 但官方 warm-start 在 micro platform 的 rollout 仍从 z≈0.69 蹲到 ≈0.51，并向后/侧向漂移；说明 action 执行语义或训练环境/官方部署 contract 仍有差异，不是权重映射问题。
- 加 `platform_jump`（平台附近向上的 base 速度）奖励后，easy 平台 256 envs 训练到约 400 iter 仍 `official_platform_success=0`、`platform_height≈0`；rollout 仍蹲伏/后移。暂不把 progress 当成功。
- 训练已停止；GPU flag=0。下一步应先核对 action yaw/forward 符号与官方部署的 wheel/leg 符号，再做平台奖励。

## 2026-10-25 指令覆盖与数值防护修正

按部署契约修正：最终策略输入是 `[v_x, v_y, omega_z]`，训练不能只覆盖 v_x。平台 HIM task 的命令范围改为 `vx∈[0,1]`、`vy∈[-0.3,0.3]`、`wz∈[-1,1]`，`resampling_time_range=(4,6)s`，`rel_forward_envs=0`、`rel_standing_envs=0.1`；保留 stop/turn/组合指令，确保任意本体状态下都有三轴跟随压力。

数值防护：

- `sim.nan_guard.enabled=True`，输出 `/tmp/mjlab/nan_dumps`；
- `BlackWHimOfficialRunner` 在 wrapper 层对动作做 `nan_to_num + clamp`，不再只依赖 action term；
- action term 仍保留 finite guard；
- 每次 save 打印 `nefc_max`、`overflow_nonzero`、`nonfinite_actions`、`max_abs_action`，作为常规稳定性指标；
- 30 iter smoke：`nefc_max=16`、`overflow_nonzero=0`、`nonfinite_actions=0`、`max_abs_action=1.571`，无 NaN。
- 另修复 blackW `base_height_target` 从 Black 点足的 0.43 改为 0.69；之前策略会被奖励成蹲伏。
- 尚未做：per-term reward clamp / only_positive_rewards、action low-pass、延迟 DR、kp/kd/力矩一致性检查；这些列入下一步。


## 2026-10-25 300-iter 指令/guardrail smoke + 平台结果

- 配置：`blackw-platform-easy-him`，128 envs，official warm-start，三轴命令 `vx∈[0,1]`、`vy±0.3`、`wz±1`，4–6s 重采样，CCD-off + NaN guard + wrapper action guard。
- 300 iter 完整跑完：`nefc_max≈38`、`overflow_nonzero=0`、`nonfinite_actions=0`、`max_abs_action≈5.03`；无 CUDA assert，无 NaN dump。
- 但 `official_platform_success` 全程为 0，`platform_height` 约 0，`platform_jump` 仅约 0.03–0.09；结论是数值稳定性已有改善，**平台爬升仍未学会/未发生**。
- 随后跑 2000 iter 长跑，到 413 iter 仍 success=0，mean reward≈18，low_base_height≈0；已停止，避免无信号烧 GPU。
- 下一步必须先把平台抬升信号做出来（接触/足端/高度课程或 skill mode），而不是继续加 iter；同时外部 PPO/BC Agent 仍占用 GPU。


## 2026-10-25 climb-height reward pilot

- 参考同机另一 Agent 的 official-obstacle recipe，给平台 HIM 增加 `climb_height = clamp(root_z - 0.55, 0, 0.60)`（weight 8）；easy 平台 128 envs、三轴命令、NaN guard，跑到 600 iter。
- 结果：mean reward≈26，`climb_height` 奖励≈0.4–0.5，`platform_jump`≈0.03–0.09，但 `official_platform_success` 仍为 **0**、`platform_height`≈0。
- 说明 climb-height 常量奖励不足以产生平台抬升；不能把 climb_height 的数值当成成功。
- 另一个 Agent 的 PPO/BC 在 official mixed task 上已出现 `competition_goal_reached≈0.22–0.35`，其 recipe 使用更大 goal/progress 权重和 16m terrain；可作为下一轮 HIM 的奖励/地形参照，但仍需独立验证 HIM 是否能学。

## 2026-10-25 下一步

- 对 HIM official mixed task 应用 `climb_height` + goal/progress 权重、16m patch，并做 300 iter smoke；重点是 success 信号而不是累计 iter。
- 增加 per-term reward clamp / only_positive、action low-pass/delay DR、kp/kd/力矩一致性检查。
- 外部 PPO/BC Agent 的 GPU 工作仍优先；非必要不与它同时长训。

## HIM 诊断脚本复现（2026-10-25）

本地归档了三个远程诊断脚本，位于 `@20261019_locomotion/scripts/agent_scripts/him_diagnostics/`。它们只读，不修改训练仓：

- `check_him_policy_equiv.py`：验证加载后的 `HIMPolicy.as_jit()` 与官方 TorchScript 在同一 `[1,6,57]` history 上的输出是否一致。
- `diag_him_platform_rollout.py`：加载某个 HIM checkpoint，打印 platform rollout 的 root x/y/z 和最大 z。
- `diag_him_official_warmstart_rollout.py`：不加载 checkpoint，直接用 `BLACKW_OFFICIAL_WARMSTART` 权重跑 rollout。

准备：先确认远程训练仓、`.venv`、`MUJOCO_GL=egl` 和 `/tmp/official_blackw_obstacle.pt` 存在；脚本按远程路径写死 `cuda:0`，只在训练仓目录下运行。

复现命令：

```bash
scp @20261019_locomotion/scripts/agent_scripts/him_diagnostics/*.py bis-ms7e56.tail4413b4.ts.net:/tmp/him_diagnostics/
ssh bis-ms7e56.tail4413b4.ts.net
cd ~/rc_work/nwwolf_mjlab_training_release
export MUJOCO_GL=egl
.venv/bin/python /tmp/him_diagnostics/check_him_policy_equiv.py
.venv/bin/python /tmp/him_diagnostics/diag_him_official_warmstart_rollout.py
.venv/bin/python /tmp/him_diagnostics/diag_him_platform_rollout.py \
  --task blackw-platform-easy-him \
  --checkpoint logs/rsl_rl/blackw_velocity_him/<run>/model_XXX.pt
```

已知结果：`check_him_policy_equiv.py` 输出 `max_abs_diff=0.0`；官方 warm-start rollout 在 micro/easy platform 上 root z 从约 0.69 降到约 0.51，未抬升，与 `official_platform_success=0` 一致。

## 2026-10-25 HIM official mixed：首次出现 goal 信号

- 更新 `blackw-official-him` recipe：官方 platform/high_wall/slope/stairs/trench exact 地形，16 m patch，命令 `vx∈[0.25,1]`、`vy±0.15`、`wz±0.2`，goal/progress/climb_height 奖励，CCD-off，NaN guard + wrapper action guard。
- 128 envs、229 iter（随后仍触发 Warp assert）：
  - `competition_goal_reached` 终止占比约 **0.19–0.33**；
  - mean reward≈15，`competition_progress≈0.58`；
  - `climb_height` 仍只有约 0.01；
  - 说明 HIM official mixed **开始有 goal 信号**，但不足以证明高台/斜坡/沟壑单项成功。
- nan_guard 在 `detection_step=58881` 抓到 env8 的 NaN（dump 在 `/tmp/mjlab/nan_dumps`），CPU/仿真状态在后续 iter 触发 Warp assert；checkpoint 保存到 model_200。
- 下一步：先在 64 envs 从 model_200 resume，确认 goal 信号可保持并定位 NaN env 的接触/地形，再开长训；不能把 mixed goal 占比直接当 Part2 judge 通过。

## 2026-10-25 HIM official mixed resume64

- 从 `blackw_him_official_mixed_v0/model_200` 以 64 envs resume 到 319 iter（仍触发 Warp assert）：
  - `competition_goal_reached` 终止占比约 0.33–0.50；
  - `competition_progress` 0.24–0.97（最后一步 0.97）；
  - `climb_height` 0.01–0.03；
  - mean reward≈12；
  - checkpoint 有 model_300。
- 说明 mixed goal 信号可重复，但仍不是严格 Part2 单项 judge 结果；`climb_height` 很低，平台/高墙仍需单独验证。
- 64 envs 仍会 Warp assert；nan dump 最新在 `/tmp/mjlab/nan_dumps/nan_dump_20261025_175524.npz`，需要先修 invalid-state reset/接触，再谈长训。

## 2026-10-25 strict Part2 训练项移植

- 只读借鉴同机 Part2 Agent 的 `_part2_terrain_state`，已把 `part2_success` / `part2_failure` / `part2_clear` 移植到我们的 HIM official mixed task：
  - success 要求四个轮子到达目标支撑面（platform/stairs/slope/trench），不是 root-x 线；
  - trench 轮子下陷超过 `min(0.5*gap, wheel_radius)` 判 `part2_failure`；
  - `part2_clear` 成功奖励 weight=25；
  - 移除了 x-only `competition_goal` 和 `competition_goal_reached`。
- 同时把 official trench（0.3m plateau + 1m entry/exit ramps + 0.1–0.3m slot）、stairs（6 上 + 0.8m landing + 6 下）和 plum 几何从对方只读代码同步到 `exact_terrain.py`；新增的 `ExactPlumTerrainCfg` 尚未接 task。
- 32 envs、20 iter smoke：`part2_success`/`part2_failure`/`part2_clear` 均出现在日志中，`nefc_max=32`、`overflow=0`、`nonfinite_actions=0`、`max|action|≈1.56`，无 Warp assert/NaN dump。20 iter 内 strict success 仍为 0，符合预期（只是链路 smoke）。
- 下一步：用 64/128 envs 从 model_300 resume 做 strict success 300 iter，先看 platform/trench 分项是否有 success，再决定是否长训。

## 2026-10-25 strict platform-only HIM

- `blackw-platform-exact-him` 现在使用 strict 四轮 `part2_success` / `part2_failure` / `part2_clear`，不再是 root-x/root-z 代理成功。
- 64 envs、official platform 10 cm、warm-start、三轴命令、NaN guard，跑完 200 iter：
  - `part2_success=0`，`part2_failure=0`，`part2_clear=0`；
  - `platform_height` 仅 0.001–0.002，`climb_height` 有信号但未形成真正上台；
  - mean reward≈23；
  - `nefc_max=43`、`overflow=0`、`nonfinite_actions=0`、`max|action|≈5.03`；无 Warp assert。
- 结论：strict 判据链路已验证；平台技能仍未出现，且不是 root-x 假成功掩盖的问题了，是真正没有四轮上台。下一步需要平台课程/接触奖励或 BC/teacher 蒸馏，不能只加 iter。

## 2026-10-25 HIM 严重 bug 修正（重要）

收到另一 Agent 的审查后逐条核对，以下均属实，并已修复：

1. **exact 任务 success/failure 是死代码**：`_exact_env_cfg` 把唯一 sub-terrain 命名为 `"exact"`，但 `_part2_terrain_state` 按 `platform/slope/stairs/trench/high_wall` 列名分支；`columns=["exact"]` 时所有分支都不命中，`part2_success`/`part2_failure`/`part2_clear` 永远 False/0。已改为按 terrain class 命名为 `platform`/`slope`/`trench`/`high_wall`/`stairs`，并把训练谓词同步到 v5（轮底支撑带 + 上界 + `root_z` + `|vz|`）。
2. **HIM warm-start 是死代码**：`BlackWHimOfficialRunner.__init__` 的 warm-start 代码被之前 patch 放到了 `save()` 的 `return` 之后，永远不会执行。`blackw_him_platform_strict_v0` 实际是**从零训练**，不能拿来证明“HIM 学不会平台”。已把 warm-start 移回 `__init__`，并验证日志出现 `[INFO] official warm start ... mapped=14`。
3. **低姿态终止误杀 teacher**：平台任务的 `low_base_height` 阈值原为 `0.55`，但官方 teacher 在接近平台时 root z≈0.51，会在到平台前被 reset，导致 teacher no-update precheck 也为 0。已降到 `0.40`。
4. **success 奖励量级不足**：platform 的 `part2_clear` 原为 25，低于平台附近 shaping 的 horizon 总量；已提高到 **200**，使成功严格优于拖延。
5. **1024 排队已停用**：脚本已改名为 `.disabled`，训练前不会再自动开 1024。

修正后的 teacher no-update precheck（64 env、fixed 命令、lr=0、冻结 std）：`part2_success` 出现非零，`part2_clear≈0.2`，说明 warm-start/谓词/低姿态门已接通。

1024/512/256 env 仍会立即 Warp assert；**128 env** 可跑，128 pilot 在 `part2_clear≈0.1–0.2`、success 非零的情况下跑到约 100 iter 后仍遇到 Warp assert（nan dump `20261025_205752`），checkpoint 到 model_75。因此还不能用 196M 预算长训；先修 128 以上的 contact/NaN reset。

结论：之前文档里“HIM strict platform success=0 = 学不会”的结论**作废**，这是死代码/从零训练造成的假零；当前已能看到 teacher 的真实 strict success，但 1024 长训仍被 Warp assert 阻塞。
