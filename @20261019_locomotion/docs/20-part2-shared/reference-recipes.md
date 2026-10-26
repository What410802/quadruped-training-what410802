# 可复用训练配方盘点：N-W-wolf / HYNova / 官方权重

## 结论

- N-W-wolf `super-dog` 就是 **blackW 的 HIMLoco/Isaac Gym 训练配方**：16 关节、57 维单步观测 ×6 历史 = 342、16 动作、轮速控制、HIMOnPolicyRunner + HIMPPO + HIMActorCritic；这与官方 blackW `.pt` 的 HIM 结构和 342/16 部署契约一致，是**最接近“直接换地形再训练”的仓库**。
- N-W-wolf `nwwolf_mjlab_training_release` 是 **Black 点足**的 MjLab HIM 训练工程，不含 blackW 任务/地形；可复用的是 `algorithms/him`、`black/him_runner.py`、`black/him_rl_cfg.py`、`export_policy.py` 这套 MjLab HIM 训练/导出代码。
- HYNova `zeitvex/RC_WheelLeg` 是 **MjLab 的 16DOF 轮足 HIM 训练配方**（53D actor、16 动作、HIMPPO、地形/奖励/课程），架构同源但机器人契约不同；MIT 许可，代码可直接读/改，**不能只换地形**，还要换机器人常量、观测/动作 contract。
- 官方 blackW `.pt` 是部署用 TorchScript（`PolicyExporterHIM`），不是训练 checkpoint；可以作为教师/权重提取/行为克隆来源，**不能假设能直接 `--resume`**。
- 两个队伍都是 HIM 族架构，但模拟器/观测维度/动作 scale/奖励实现不同；不存在一个“改 terrain 行就完全兼容”的跨仓库 magic switch。

## N-W-wolf super-dog（blackW 直接配方）

仓库：<https://github.com/N-W-wolf/super-dog>（CC BY-NC-SA 4.0，注意许可）

可直接复用：

- `legged_gym/envs/blackW/blackW_config.py`：blackW URDF、默认关节角、PD（腿 Kp50/Kd1.2、轮 Kp0/Kd1.0）、action scale（腿 0.25、轮速度 10）、关节顺序、地形/命令/奖励/DR/噪声/观测缩放；
- `blackW_env.py`：blackW 专用接触、轮速、越障奖励逻辑；
- `projects/himloco` + `rsl_rl`：`HIMOnPolicyRunner`、`HIMPPO`、`HIMActorCritic`、`HIMEstimator`；
- `日志/blackW/*.md`：2026-05-24 到 07-15 的奖励/课程/地形/高墙/楼梯/续训实验记录（非常有价值）；
- 训练入口：`python legged_gym/legged_gym/scripts/train.py --task=blackW`。

关键配置：

- `BlackWCfgPPO`: `HIMOnPolicyRunner`、`HIMActorCritic`、`HIMPPO`；
- `4096` envs、`num_steps_per_env=64`、`max_iterations=1000`、`save_interval=50`、`resume=True`，示例 `load_run="Jun26_12-30-56_"`；
- 官方部署策略名 `Obstacle_Jun26_12-30-56_.pt` 与这个 run 命名对应，说明官方模型极可能来自这套配方（1000 iter 级别 + 续训/分叉，而不是单纯 15000 iter）。

限制：

- 依赖 Isaac Gym、Python 3.8、PyTorch 1.13/cu117；当前远程 MjLab 环境不能直接跑；
- 仓库只有训练代码/log，没有训练 checkpoint；官方 `.pt` 是 TorchScript，不能直接当 legged_gym 的 `model_*.pt` 续训；
- 地形比例只有 flat/slope/stairs/gravel/high_wall，没有 Part2 的 high_platform/trench/plum，需要补官方 `map.xml` 几何。

## N-W-wolf nwwolf_mjlab_training_release（MjLab HIM 基础）

仓库：<https://github.com/N-W-wolf/nwwolf_mjlab_training_release>

可直接复用：

- `src/alldog_mjlab/algorithms/him/`：estimator/policy/ppo/storage/warm_start；
- `src/alldog_mjlab/tasks/velocity/black/him_runner.py`、`him_rl_cfg.py`、`him.py`；
- `src/alldog_mjlab/utils/export_policy.py`。

不能直接复用：

- 这个仓库是 **Black 点足**任务；没有 blackW 机器人/地形/动作接口，地形也不能直接换。

用途：把它的 HIM 训练/导出代码接到我们已建的 blackW MjLab 任务上，是当前 GPU 环境下最省事的接入点。

## HYNova RC_WheelLeg（MjLab 16DOF HIM）

仓库：<https://github.com/zeitvex/RC_WheelLeg>（MIT）

可直接复用：

- `05_software/train/rc_mjlab/src/robot/rsl_rl/`：`HIMActorCritic`、`HIMPPO`、`HIMEstimator`、runner；
- `src/robot/config/rl_cfg.py`：Rough `max_iterations=20_000`、`num_steps_per_env=24`、2048 envs、PPO 超参；
- `src/robot/config/env_cfgs.py` + `src/robot/mdp/`：命令课程、分轴速度奖励、地形课程、轮腿奖励/低通/扰动；
- `src/robot/terrains/`：高墙/低杆/楼梯等 MjLab 地形实现；
- 最终部署模型 `model_6800.onnx`（约 6800 iter）可作质量参照。

不能直接复用：

- actor 单步 53D（3+3+3+12+12+4+16），我们是 57D（16 关节，轮位置也占位）；动作 scale/机器人参数/URDF 不同；只换地形不够，必须换 robot/obs/action contract。

## 官方 blackW `.pt`

位置：`ReadOnly.d/quadruped_control/assets/policies/blackW/{flat,obstacle,stair}/*.pt`

- TorchScript 内含 `PolicyExporterHIM` 的 estimator + actor；
- 342 输入、16 输出，与 super-dog blackW 的 57×6/16 契约一致；
- 可尝试：提取 estimator/actor 权重映射到 HIMActorCritic 做 warm-start/教师，或行为克隆；不可直接作为 Isaacs legged_gym `model_*.pt` 训练 checkpoint。

## 推荐路线

1. 若 Isaac Gym 环境可用：用 N-W-wolf super-dog blackW 配方，替换地形为官方 Part2 `map.xml` 几何，先 1000 iter 级 pilot；尝试从官方 `.pt` 提取 HIM 权重 warm-start。
2. 若继续用当前远程 MjLab/RTX5060：用 N-W-wolf `nwwolf_mjlab_training_release` 的 HIM 代码或 HYNova 的 MjLab HIM 代码，接到我们的 blackW 任务/官方地形上；训练超参向 N-W-wolf blackW（4096 envs、64 steps、1000 iter）或 HYNova（2048/24/20k）靠拢。
3. 先做一件事：把官方 `.pt` 的 HIM 权重能否映射到目标 HIMActorCritic 做可行验证；成功则优先热启动，失败则从 HIM 从零 + 官方地形课程。
