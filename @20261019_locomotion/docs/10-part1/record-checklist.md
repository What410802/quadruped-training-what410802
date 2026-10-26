# 每轮训练要手动完成的记录性任务

> 配套：[`experiments.md`](experiments.md)（记录表）、[`eval-protocol.md`](eval-protocol.md)（gate）、[`visualization.md`](visualization.md)（视频）。目的是让每轮训练都可追溯、可比较，不依赖“我记得当时跑过”。

## 1. 开跑前（5 分钟）

- [ ] 确认目标 run 要回答的问题（例如“flat baseline 复现”“rough 续训”“实验组 B 对照”），写进 `experiments.md` 占位行。
- [ ] 记录训练仓库 commit、`uv.lock` hash、task id、环境（远程原生 uv）、GPU；代码/配置若有改动，先确认在哪个分支、是否会影响 baseline。
- [ ] 记录训练命令：`num_envs`、`max_iterations`（注意 resume 语义）、seed、`run-name`、日志/checkpoint 路径。
- [ ] 确认没有并发重 GPU 任务（训练期间不要同时跑 `play --video`；视频放训练后或单独串行）。
- [ ] 确认 TensorBoard 路径可写：`logs/rsl_rl/black_velocity`；用训练仓库的 `.venv/bin/tensorboard` 启动（远程 PATH 没有 `tensorboard`）。
- [ ] 记下预期 ETA 与峰值显存（可参考 [`environment.md`](../30-ops/environment.md) §3 的 512–8192 envs 基准）。

## 2. 训练中（每个里程碑）

- [ ] 开跑后看前几条日志：无 `NaN`、无 CUDA error、无 `normal expects std >= 0` 等断言；`Mean reward`/`Mean episode length` 在正常范围。
- [ ] 每 50–100 iteration 看 TensorBoard 关键曲线（读法见 [`training-health.md`](health.md) §6）：
  - `Mean reward`、`Mean episode length`（是否满 1000 steps）；
  - `Curriculum/command/{vx_min,vx_max,ema_low,ema_high,pass_streak}`（课程是否推进）；
  - `Curriculum/terrain_levels/*` **分地形看**（重点 `stairs_down`、`discrete_obstacles` 是否掉级）；
  - `Metrics/twist/error_vel_xy`、`error_vel_yaw`；
  - `Episode_Termination/{illegal_contact,stuck,time_out}`；
  - **数值预警**：`Loss/value` >100 或 inf、`action_rate_l2`/`smoothness` 出现 >1 的绝对值、`mean_reward` 出现负的离群值、`Loss/learning_rate` 频繁 <1e-4；
  - `Mean action std` 与 `Loss/entropy`（fine-tune 正常应收敛；rough 曾从 2.3 升到 6.8）。
- [ ] 在里程碑 checkpoint（100/500/1000/…/最终）录一次视频，并做**可视化闭环诊断**：
  - 单机器人 tracking 视频：`render_training_video.py play`（见 [`visualization.md`](visualization.md) §3）；
  - **固定命令序列视频**：`render_policy_commands.py`，覆盖 stand / fwd / bwd / lat / yaw / arc-left / arc-right / combined（见 [`visualization.md`](visualization.md) §3.1）；flat、fixed gravel、free-joint gravel 各至少一条；
  - 全局静态图：`render_training_video.py overview`（flat 与对应地形各一张）；
  - 先看视频再看数字：出现拖腿、抖动、卡边、原地摆尾时，即使 gate 数字通过也不能直接进入下一阶段。
- [ ] 如果崩溃：保存日志尾部、最后 checkpoint、复现命令/时间；在 `experiments.md` 写清报错与恢复方式（例：rough 3388/3999 的 PPO `std >= 0` 断言 → resume from `model_3350`）；注意 `std >= 0` 只是末端症状，先看 `Loss/value` 与平方类 reward 的预警。
- [ ] 如果继续训练/重训：确认是否真的要继承上一阶段的 command range；resume 会重置 terrain level 与 command EMA/buffer，曲线跳变不是退化。
- [ ] 不在训练进程运行期间改训练代码/配置；要改就另起 run。

## 3. 训练结束（30–60 分钟）

- [ ] 从日志抄最终指标（iteration、wall time、Mean reward、episode length、curriculum、error_vel、terminations、action std）到 `experiments.md`。
- [ ] 导出 TorchScript（在训练仓库）：`.venv/bin/export --task-id … --load-run … --checkpoint … --output-dir …`；记录 `policy.pt` sha256、大小、输入/输出维度。
- [ ] 本地 gate 评测：`pixi run python @20261019_locomotion/scripts/agent_scripts/eval_flat.py --json …`（rough 评测脚本后续补）；把 JSON 与策略放入 `assets/policies/<version>/`，写 `README.md`（来源、命令、契约、gate）。
- [ ] 更新 `experiments.md` 的 run 表、gate 结论、视频记录；更新 `status.md` 的阶段状态与下一步。
- [ ] 归档：
  - 选中的 `policy.pt` + 评测 JSON 进运行仓库任务 `assets/policies/<version>/`；
  - 把本轮发现的问题/健康检查结论补到 [`training-health.md`](health.md) 或 [`experiments.md`](experiments.md)；
  - 精选 `policy.pt` / `model_*.pt` 可入库（见 [`experiments.md`](experiments.md) §5）；每 50 iter 的原始 checkpoint、TensorBoard 事件与日志留在远程或 Release；
  - 有价值的视频复制到任务 `output/` 或 Release，并记录来源；`videos/`、`logs/` 不入库。
- [ ] 写一句结论：这轮是否达到 gate、下一步是继续/调参/换实验；如果需要少量调参，记录“只调了哪个现有参数、为什么”（参见 [`eval-protocol.md`](eval-protocol.md) §7）。

## 4. 每轮结束前的检查（一条命令思路）

```bash
# 训练仓库（示例）
cd ~/rc_work/nwwolf_mjlab_training_release
.venv/bin/tensorboard --logdir logs/rsl_rl/black_velocity --port 6006   # 看曲线
.venv/bin/export --task-id black-flat --load-run '<run>' --checkpoint model_XXXX.pt

# 运行仓库（示例）
cd <运行仓库根目录>
pixi run python @20261019_locomotion/scripts/agent_scripts/eval_flat.py \
  --policy @20261019_locomotion/assets/policies/<version>/policy.pt \
  --json @20261019_locomotion/assets/policies/<version>/eval-flat.json
pixi run python @20260927_motor/scripts/agent_scripts/check_md_links.py @20261019_locomotion
```

## 5. 记录不通过时

- 不要只写“效果不好”；记录：哪个 gate 项不达标、数值、与 baseline 的差值、怀疑的原因、试过什么（以及是否属于“只调现有参数”）。
- 如果必须改设计（新增 reward/终止/课程类型），先回到 `experiments.md` 记一条“设计变更提案”，跑 A/B 后再决定是否进入主线。
