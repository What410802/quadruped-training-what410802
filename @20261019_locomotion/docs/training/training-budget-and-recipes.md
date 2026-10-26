# 训练预算、env/step/iter 与已成功配方

> 2026-10-25 调研结论。目的：决定 blackW HIM 正式训练的 env / step / iter、学习率和 GPU 排队方式。

## 1. 外部参考

- N-W-wolf `super-dog` blackW HIMLoco：<https://github.com/N-W-wolf/super-dog>，`BlackWCfgPPO` 的 `num_envs=4096`、`num_steps_per_env=64`、`max_iterations=1000`，约 **262M env steps**；官方 `Obstacle_Jun26_12-30-56_.pt` 命名与该 run 对应。
- HYNova `RC_WheelLeg`：<https://github.com/zeitvex/RC_WheelLeg>，MjLab 16DOF 轮足，RC2026 全国一等奖/第7/1050 分；当前 Rough 配置 `2048 envs`、`num_steps_per_env=24`、`max_iterations=20000`，最终部署 `model_6800.onnx`；约 334M–983M env steps。
- HYNova 控制：`0.005s × decimation4`（50Hz）；动作延迟 0–2 步，腿低通 5Hz、轮低通 15Hz；`lr=8e-4` adaptive，entropy 分阶段 0.003→0.001→0.0008。
- BeamDojo：<https://arxiv.org/abs/2502.10363>，人形稀疏落脚点；核心是 foothold 采样奖励 + double critic + 两阶段（平地感知预训练→任务地形 fine-tune），不是 blackW 现成配方；当前外部 Agent 仓库也没有实际 BeamDojo 代码。

## 2. env / step / iter 的含义（据参考问答）

- `batch = env × step`；`total steps = env × step × iter`。
- env 是数据宽度，step 是单条轨迹深度，iter 是采样-更新轮数。
- 总步数相同不等于效果相同：固定总预算时，GPU 物理仿真通常**优先加 env**；step 至少要覆盖任务决策 horizon；iter 决定更新次数，按 batch 反向校准学习率。
- 显存约 `常数 + α·env + β·(env×step)`，与 iter 无关。显存不足时优先 **降 env、提高 step 保 batch**，或增加 `num_mini_batches`；不要靠减 iter 省显存。
- mjlab 没有把 nworld 分块串行执行的内置开关；CPU 模式可跑但官方不建议训练。低显存优先降 env / 降观测 history / 调 nconmax/njmax。

## 3. 我们之前的偏差

| run | env | step | iter | 约 env steps |
|---|---:|---:|---:|---:|
| HIM strict platform 200 | 64 | 64 | 200 | 0.82M |
| HIM platform 600 | 64 | 64 | 600 | 2.5M |
| HIM mixed 128 | 128 | 64 | 300 | 2.6M |
| N-W blackW | 4096 | 64 | 1000 | 262M |
| HYNova final | 2048 | 24 | ~6800 | 334M |

我们的几百 iter 只到成功配方的 **1%–2%** sample budget，这是当前“平台 success=0”最可能的主因之一，而不是 HIM 路线本身。

## 4. 正式 pilot 取值（已与用户确认）

- 任务：`blackw-platform-exact-him`，strict 四轮 `part2_success/failure/clear`。
- envs：**1024**（GPU 空闲时；先安全窗口，后续可评估 2048）。
- `num_steps_per_env`：**64**（与 N-W/MjLab HIM 默认一致，覆盖 20s episode 的决策 horizon）。
- iterations：**3000**；total ≈ **196M env steps**，位于 N-W 262M 同一量级。
- batch：1024×64=65,536；lr=**5e-4** adaptive，entropy=**0.003**；init_std 保持 0.3（先稳定，后续 A/B 0.5/1.0）。
- OCR/command：阶段 1 `BLACKW_COMMAND_STAGE=narrow`（vx0.25–1、vy±0.15、wz±0.2，仍是三轴），阶段 2 再扩到 wide vx0–1、vy±0.3、wz±1。
- save interval=50；从 `model_50/100/...` 每 100–200 iter 做 strict 分项检查；若 500–800 iter 仍 `part2_success=0`，先停，不要盲跑 3000。
- 物理/控制：保持 0.005s × decimation4，与 HYNova/N-W 当前代码一致；2ms/10dec 只是外部实验，不作为默认。

## 5. GPU 排队

远程机没有 Slurm/PBS/runai 等正式队列（只有 `screen`）。已在训练机放置轻量排队脚本：

```text
~/rc_work/queue_blackw_platform_1024.sh
/tmp/blackw_queue.log
```

逻辑：

1. 等待所有其他 `.venv/bin/train` 进程退出；
2. 等待 GPU 显存 < 2500 MiB；
3. 置 `~/5060ti_machine_use_flag.txt=1`；
4. 启动上面 1024×64×3000 的 HIM strict platform 训练；
5. 训练结束自动置 flag=0 并写日志。

用户会通知另一 Agent 在完成后停掉任务；队列会在 GPU 空闲时自动开始。当前外部仍有多个训练进程，队列处于等待状态。

## 6. 低占用并行

- 外部 5 个训练进程占用约 11.6GB/99%，HIM 1024 无法安全并发；当前队列不启动。
- 如果之后只能并行，最多跑 **128–256 envs 的 smoke/A-B**，不作为正式训练预算结论。
- 1024 env 正式训练需要等外部任务退出或用户协调窗口。

## 7. 单卡串行队列选择（2026-10-25 更新）

结论：16GB 单卡不应把 HIM/PPO 各切一半并行；环境的“宽度”收益大于并发收益，应改为 **一次只跑一个全显存训练，另一个排队**。

远程机没有 sudo 权限安装 system 包，因此没有用 Slurm/PBS；已把 **task-spooler v1.0.3** 用户级安装到：

```text
~/.local/bin/tsp
~/.local/bin/ts -> tsp
TS_SOCKET=/tmp/gpu_queue.socket
```

用法：

```bash
export PATH="$HOME/.local/bin:$PATH"
export TS_SOCKET=/tmp/gpu_queue.socket
ts -S 1                 # 单 GPU：一个 slot
ts ~/rc_work/gpu_jobs/him_1024.sh
ts -l                   # 查看队列/日志
ts -c                   # 清理已完成
```

每个 job 脚本内部再做 `flock /tmp/gpu.lock` + 等待 `nvidia-smi` 显存 < 1GB + flag 1/0，避免 ts 本身不感知 GPU 造成两个 job 重叠。

不推荐 Slurm：单机单卡安装 slurmctld/slurmd、配置 GRES GPU 和维护成本远大于收益，只有多节点/多用户资源调度才值得。
