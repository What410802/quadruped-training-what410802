# P1 basic obstacle：slope + stairs 训练入口（2026-10-22）

> P1 第一项：在 flat 策略基础上先训练平滑坡与台阶，不把 rough/discrete/砂砾混进来。代码在训练仓库（本地 `prep.d/training_repo_local`，远程 `~/rc_work/nwwolf_mjlab_training_release`），本文件只记任务定义、启动和验收口径。

## 1. 训练任务

新增训练仓库 task：

```text
black-basic-obstacle
```

实现：

- 复用 `_build_black_env_cfg(rough=True)` 的 reward/termination/terrain-scan/actor 45 维契约；
- 只替换 terrain generator：
  - `flat` 20%；
  - `smooth_slope_up` 20%；
  - `smooth_slope_down` 20%；
  - `stairs_up` 20%；
  - `stairs_down` 20%；
- `num_rows=6`、`difficulty_range=(0.0,0.6)`：
  - 最大坡度约 `0.7×0.6 = 0.42`（约 23°）；
  - 最大台阶高约 `0.05 + 0.18×0.6 = 0.158 m`；
- 初始 terrain level = 1；
- 不包含 rough_slope、discrete_obstacles、砂砾、桥。

当前使用 `black_ppo_runner_cfg(stage="rough")`（同 actor/reward 契约），因此日志/run 名会带 rough stage；P1 的正式独立 stage 在 P2 前再拆。

## 2. 从 flat 策略启动

远程命令（2026-10-22 已执行）：

```bash
cd ~/rc_work/nwwolf_mjlab_training_release
export UV_CACHE_DIR="$HOME/rc_work/.uv-cache"
MUJOCO_GL=egl .venv/bin/train black-basic-obstacle \
  --env.scene.num-envs 4096 \
  --agent.max-iterations 1500 \
  --agent.logger tensorboard \
  --agent.resume True \
  --agent.load-run 2026-10-21_11-59-36_flat_ft_mirror01_footclear_500 \
  --agent.load-checkpoint model_2498.pt \
  --agent.run-name p1_basic_obstacle
```

- checkpoint 来源是 `flat-ft-2500` 的 `model_2498.pt`（flat/砂砾候选）；
- `--agent.resume True` 加载 actor/critic/optimizer；command curriculum 跨 stage 恢复按仓库既有逻辑处理；
- 4096 envs、1500 iter；日志在远程 `logs/p1/basic_obstacle_from_flat_ft_*.log`。

当前状态（2026-10-22）：远程 run 已启动，PID 44613；日志 `~/rc_work/nwwolf_mjlab_training_release/logs/p1/basic_obstacle_from_flat_ft_*.log`；上次检查约 iteration 2531/3998、约 2.87 s/iter，预计剩余约 70 min。训练完成或失败由后台监控任务 `bash-187` 通知；完成前不把数字当验收。

## 3. 验收口径

训练后先用 `play` 模式看：

- 摔倒率；
- slope/stairs 各 terrain level 的通过率；
- tilt/角速度；
- foot clearance；
- 是否能在 slope/stairs 上保持速度跟踪。

通过后再进 P1 的下一组：T 台阶/高台 10–20 cm 和 Part 1 关键障碍。不要用训练 reward 上升代替通过率。
