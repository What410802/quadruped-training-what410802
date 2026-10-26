# 远程 GPU 训练工作流：停止即通知、失败即诊断（2026-10-24）

> 背景：训练跑在远程机 `bis-ms7e56.tail4413b4.ts.net`，一次 run 20 min–2 h。之前靠人肉轮询 `ssh + grep`，容易错过失败或结果；本工作流让"训练停止/失败"自动产生一次可被本 agent 会话收到的通知，并自动拉回日志/视频。

## 1. 远端 run 脚本契约

每个训练/渲染批次写一个远端脚本（放在 `~/rc_work/<name>.sh`），遵守：

1. `chmod +x`、`nohup` 启动，日志进 `~/rc_work/logs/<name>.log`；
2. `trap 'printf "0" > ~/5060ti_machine_use_flag.txt' EXIT`，进入时先 `printf "1"` —— 只要脚本退出（成功/失败/Ctrl-C）都会释放 GPU 占用标志；
3. 写**完成标记文件** `~/rc_work/logs/<name>_summary.txt`：每条 run 记录 `rc=`、迭代数、时间；最后一行固定 `"<name> done <time>"`；失败时写 `ABORT` 或 `rc=<非0>`；
4. 视频/评测产物固定落到 `~/rc_work/videos|results/...`，本地 watcher 按前缀拉取。

示例（节选）：

```bash
OUT="$HOME/rc_work/logs/competition_ab_summary.txt"; : > "$OUT"
trap 'printf "0" > "$HOME/5060ti_machine_use_flag.txt"' EXIT
printf "1" > "$HOME/5060ti_machine_use_flag.txt"
env BLACK_MIRROR_LOSS_COEFF=0.1 MUJOCO_GL=egl .venv/bin/train black-competition \
  --agent.max-iterations 800 --agent.run-name cmp_comp_blind_800 \
  --env.scene.num-envs 1024 > "$HOME/rc_work/logs/cmp_comp_blind_800.log" 2>&1
echo "cmp_comp_blind_800 rc=$? iters=$(grep -c 'Learning iteration' ...) $(date +%H:%M:%S)" >> "$OUT"
...
echo "competition ab history done $(date +%H:%M:%S)" >> "$OUT"
```

## 2. 本地 watcher（后台任务 = 通知机制）

本地用 `bash` 后台任务（本 agent 的 `run_in_background`）跑一个 watcher 脚本：

1. 每 10–20 s `ssh` 轮询 summary：出现 `"<name> done"` → DONE；出现 `ABORT`/`rc=[1-9]`/`cuda_err` → FAIL；否则 RUNNING；
2. 退出条件触发后，打印 summary + `pgrep`（确认没有残留 train/render 进程）+ flag 值；
3. `scp` 拉回 logs/videos/results 到 `prep.d/`；
4. 后台任务结束时，本 agent 会话会收到一条 job 完成通知（无需轮询），随后立刻能读 `job_output` 并给出诊断/下一步。

模式与已有脚本：

- 通用 watcher 模板：`/tmp/rcwork/watch_*.sh`（本轮用于筛选/竞争地形 A/B）；
- 远端脚本命名：`~/rc_work/{smoke_*,render_*,competition_*}.sh`；
- 注意：`pgrep -f` 的 pattern 会匹配 ssh 命令行自身，等待时用标记文件而不是 `pgrep`；监控进程时用 `[.]` 括号写法或 `pkill` 时先确认 PID。

## 3. 失败即诊断的最小检查清单

- `rc!=0`：先看 `grep -E "Error|Traceback|CUDA|Warp|bad_sim_state" log`，再看 `tail -30`；
- 训练 NaN：`grep -i "nan\|inf" log`，对照 reward/return clamp 与 `bad_sim_state` 终止；
- GPU 卡死/残留：`ps -eo pid,cmd | grep "\.venv/bin/train" | grep -v grep`，`nvidia-smi` 显存/利用率，必要时 kill 后把 flag 置 0；
- 训练结束但没产物：检查 `ls -d logs/rsl_rl/black_velocity/*<run-name>` 与 `save_interval`，确认 `ls -t <run>/model_*.pt | head`。

## 4. 可视化节点

按用户要求只在**主要节点**录 rollout 视频（smoke 验证地形/接口、A/B 得到结论、blind-final/depth-final 完成、judge 前后）：

- 训练地形：`scripts/agent_scripts/render_policy_video.py --task ... --checkpoint ... [--terrain-level/--terrain-type]`；
- 真实 Part1/Part2 场景：本地 `run_part1_judged_rollout.py` / `run_part2_judged_eval.py`（blind 链路已通；depth 链路见后续 work item）；
- 结果统一放 `prep.d/videos/`，review 页 `prep.d/videos/review_20261024.html` 按节点追加 section。

## 5. task-spooler 单卡 GPU 队列（2026-10-26 实测，取代手工 nohup 抢卡）

算力机已装 task-spooler v1.0.3（`~/.local/bin/ts -> tsp`），用**单槽队列**把训练/导出/评测任务串行化；两条训练线（PPO/BC 与 HIM）共用 `TS_SOCKET=/tmp/gpu_queue.socket`，一次只跑一个全显存 job。

- 初始化（机器重启后执行一次）：`export PATH="$HOME/.local/bin:$PATH"; export TS_SOCKET=/tmp/gpu_queue.socket; ts -S 1`；
- job 目录契约：`~/rc_work/gpu_jobs/common.sh`（统一 PATH/TS_SOCKET/`MUJOCO_GL=egl`、`cd ~/rc_work/part2_team_race`、`PYTHONPATH=$PWD/src`、`/tmp/gpu.lock` flock + 等显存 <2.5 GB、flag 文件、SIGTERM/EXIT trap 清理、`~/rc_work/logs/<job>.log` 与 `<job>_summary.txt`）；
- 每个计算任务一个 `~/rc_work/gpu_jobs/<job>.sh`（`JOB_NAME=<job>; . common.sh` 之后直接写命令），提交：
  `TS_ONFINISH=~/rc_work/gpu_jobs/on_finish.sh ts -L <label> ~/rc_work/gpu_jobs/<job>.sh`；
- 常用命令：`ts -l`（队列，`run=N/1` 为占用槽数）、`ts -s <id>`、`ts -t <id>`（跟踪输出）、`ts -c <id>`（完整输出）、`ts -i <id>`（开始/结束/耗时/退出码）、`ts -o <id>`（输出临时文件）、`ts -k <id>`（SIGTERM 任务进程组）、`ts -w <id>`（阻塞等待）、`ts -C`（清空已完成列表）。

2026-10-26 08:37–08:41 实测（RTX 5060 Ti 16 GB，队列空闲 → 单槽串行）：

| job | 内容 | 调度行为 | 结果 |
|---|---|---|---|
| `kill_test` | `sleep 240` + trap 清理 | `ts -k` 后 4 s 结束 | state=finished、E-Level=-1；SIGTERM trap 生效，flag 1→0 |
| `smoke_train` | `blackw-slope-exact` 16 env × 3 iter（部署对齐物理） | 立即开始 | 11 s 跑完，rc=0，生成 run 目录 |
| `export_guard4` | 3 个 guard4 run × 5 个 checkpoint 导出 TorchScript | 在 smoke 后排队 9 s 才启动 | 85.6 s，15/15 rc=0，单 checkpoint 约 5–6 s，policy.pt 1.38 MB |

注意：

- **队列状态在 `/tmp`（socket + 任务列表）**，机器重启即丢失；持久记录看 `~/rc_work/logs/*.log` 与 `*_summary.txt`，收尾后 `scp` 回本地 `prep.d/`。
- **flag 文件只是辅助信号**：`~/5060ti_machine_use_flag.txt=1` 表示某 job 持有 GPU；正常结束/`ts -k`（SIGTERM）由 trap 复位，SIGKILL 或直接 kill 外部进程不会复位，此时以 `ts -l` + `nvidia-smi` 为准并手工 `printf 0 > ~/5060ti_machine_use_flag.txt`。
- `TS_ONFINISH` 在任务结束时被调用（参数 `jobid err outfile command`），此时该 job 在 `ts -l` 里仍显示 running，判"是否还有别的 job 在跑"要排除自己；不要用它做关键状态迁移。
- **不要绕开队列直接 `nohup .venv/bin/train`**：单槽的意义就是两条线串行，绕开会撞显存/吞吐；提交前先 `ts -l` + `nvidia-smi`，每条线最多排 2–3 个 job，长训按 ≤2 h 切分（夜间关机），配合 `--agent.save-interval 50` 续训。
- 建议 job 标签：`ppo_*` / `him_*` / `diag_*`，便于两条线协同与清理。
