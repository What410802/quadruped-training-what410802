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

## 4. 第一轮结果（2026-10-22，训练完成）

- run：`logs/rsl_rl/black_velocity/2026-10-22_15-25-59_p1_basic_obstacle`
- 最终 checkpoint：`model_3997.pt`
- 训练：4096 envs，约 **1 h 11 min**（约 2.86 s/iter），无进程崩溃；后台监控 `bash-187` 已完成。
- 训练末期 terrain level：mean≈1.54，stairs_up≈1.84，stairs_down≈0.85，smooth_slope_up≈1.78，smooth_slope_down≈1.53；非法接触率仍高（约 0.89），不能当通过。
- 导出策略：远程 `~/models/p1_basic_obstacle/policy.pt`（45 维，actor-only，导出校验通过；本地副本在 `prep.d/models/p1_basic_obstacle/policy.pt`）。

### 本地 Part 1 迁移诊断

用 P1 policy 跑原来的八障碍脚本，和 flat-ft 对照：

| 障碍 | flat-ft | P1 basic-obstacle |
|---|---|---|
| bridge_blocks | fail, tilt≈25.9° | running, tilt≈10.7° |
| bridge_bands | running, tilt≈14.9° | running, tilt≈4.6° |
| height_bar | fail(bar), tilt≈1.6° | running, tilt≈1.1° |
| slope | fail, tilt≈6.6° | fail, tilt≈9.3° |
| T stairs | pending | pending |
| 其他 | 0 success | 0 success |

结论：桥面/限高杆行为有改善，但 **P1 还没有通过 slope/stairs**；不能把本轮当 P1 验收。contact sheet：`prep.d/videos/part1_p1_basic_obstacle_contact.png`。

### 第二轮续训（2026-10-22）

- run：`logs/rsl_rl/black_velocity/2026-10-22_16-44-17_p1_basic_obstacle_cont`；checkpoint `model_5496.pt`；
- 4096 envs × 1500 iter，约 1 h 11 min；
- 训练末期 terrain level：mean≈1.62（第一轮 1.54），smooth_slope_up≈1.92，stairs_up≈1.68，stairs_down≈1.09；非法接触率约 0.875，仍高；
- 本地 Part 1 迁移诊断反而变差：bridge_bands tilt≈38.7°、height_bar 重新碰杆、t_stairs fail；说明不能只靠连续训练，Part 1 迁移与训练地形不一致，需要先做训练环境评估/调课程；
- 结果 JSON：`prep.d/results/part1_p1_cont.json`；contact sheet：`prep.d/videos/part1_p1_cont_contact.png`。

### 下一步（当前暂停）

- **用户已明确暂不继续下一轮训练**；先做训练环境 play/eval（terrain level、slope/stairs 通过率、摔倒率），再决定课程/奖励调整；
- 下次训练再优先 T 台阶/高台 10–20 cm，不混 rough/discrete；
- 恢复/桥面专项放 P2。

## 3. 验收口径

训练后先用 `play` 模式看：

- 摔倒率；
- slope/stairs 各 terrain level 的通过率；
- tilt/角速度；
- foot clearance；
- 是否能在 slope/stairs 上保持速度跟踪。

通过后再进 P1 的下一组：T 台阶/高台 10–20 cm 和 Part 1 关键障碍。不要用训练 reward 上升代替通过率。
