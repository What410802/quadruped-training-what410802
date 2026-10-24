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
