# blackW Part2 训练架构决策

结论：**纯 PPO + 342-D MLP 只是从 Black/MjLab 基座继承来的初步 baseline，不是针对 Part2 高档位验证过的方案。要继续冲官方/HYNova 水平，需要换成 HIM 类结构，并重新做官方地形 + 速度指令课程。**

## 事实依据

- 当前训练：`blackw` 任务用 `black_ppo_runner_cfg(stage="rough")`，actor/critic 都是 512-256-128 MLP，actor 输入 342（57×6 历史扁平），没有 estimator，没有 privileged critic 的在线估计。
- 官方 blackW `.pt`：TorchScript 里是 `legged_gym.utils.helpers.PolicyExporterHIM`，即 HIM 结构（estimator + actor/critic），不能用我们的 MLP 直接续训。
- HYNova 开源 16DOF 轮足（`zeitvex/RC_WheelLeg`，MIT）比赛最终版：
  - 训练也用 mjlab + PPO，但 `src/robot/rsl_rl/modules/him_actor_critic.py` 是 HIM actor-critic；
  - actor 输入 = one-step obs + estimator 的 vel3 + latent16；
  - `num_steps_per_env=24`、`max_iterations=20_000`（Flat 10k、Rough 20k），2048 envs；
  - 最终比赛 Rough 策略为 `model_6800.onnx`（6800 iter 左右）。
- 官方 HIMLoco 训练默认 `max_iterations=15000`；官方 blackW 目录有约 95 个日期版本 checkpoint（6/25–7/15）。
- 我们目前从零/短程训练 1000–1400 iter，且只用 proxy terrain，规模、结构、地形都不对标，**不能据此判断达到官方水平**。

## 官方 .pt → MjLab HIM 热启动验证（2026-10-25，PASS）

目标：`alldog_mjlab.algorithms.him.policy:HIMPolicy`（N-W-wolf MjLab HIM），
spec 为 `single_frame=57, history=6, command=3, velocity=3, action=16, latent=16`，
encoder `(128,64)`、actor `(512,256,128)`。

- 官方 `Obstacle_Jun26_12-30-56_.pt` 参数：actor `(512,76)/(256,512)/(128,256)/(16,128)`，estimator `(128,342)/(64,128)/(19,64)`；
- 映射后 **14 个 actor + source-estimator tensor 全部 shape 完全匹配**；
- 仅缺训练专用的 `estimator.target.*` 与 `estimator.proto.weight`（官方部署模型不含）；
- 输入 `1×342` canonical history（newest→oldest）对比：`max_abs_diff = 0.0`。

结论：**官方 HIM actor/source estimator 可以直接 warm-start 到 MjLab HIMPolicy**；target encoder/prototypes/critic 随机初始化后继续 HIM 训练。验证脚本：`prep.d/blackw_validation/him_warmstart_validate.py`。

## 为什么纯 MLP 不够

Part2 高档位（高台40、坡45、沟壑30、高墙40）需要：

- 从历史观测推断接触/地形/外力（HIM estimator 正是为此）；
- privileged critic 提供训练期特权信息，部署 actor 只用可观测历史；
- 更长的训练与 success-gated 课程；
- 正确的速度指令分布和 terrain-specific reward。

没有 estimator/privileged critic，盲策略在复杂接触地形上的样本效率和稳定性都差；这不是 PPO 本身的问题，而是**网络结构与训练信息瓶颈**。

## 建议方案（不预设方法偏好）

1. 移植 HIM 结构到我们的 mjlab blackW 任务：342 actor history、57 one-step、16 actions，actor 输入 57+3+16=76；critic 使用现有 247 维 privileged obs。
2. 直接参考 HYNova（MIT）的 `HIMActorCritic`/`HIMPPO`/runner 和 reward/curriculum；只替换机器人常量、观测/动作契约和地形。
3. 训练配置向参考靠拢：2048 envs、20k iter、`num_steps_per_env` 24–100、save interval 100；先用官方最低档 success-gated，再升档。
4. 地形按官方 `map.xml` 逐档重建；不再用 proxy；物理侧墙去掉，只保留判罚 lane 约束。
5. 官方 `.pt` 可作为教师/参考：若 HIM 结构匹配，尝试 warm-start actor 或行为克隆；否则从零 HIM + 长训练。

## 蓝色墙说明

pilot 视频里的蓝色侧墙是**我们训练地形里加的物理墙**（`ExactHighPlatformTerrainCfg.side_walls=True`），用来防止策略绕过平台；官方 `map.xml` 没有这两堵墙，只有裁判 lane 约束。它会影响策略与地形的接触学习，现已默认关闭（`side_walls=False`），改回 lane termination/惩罚。

