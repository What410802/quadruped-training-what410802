# 共享 GPU 队列协议（单源）

> 本页是队列口径的唯一来源；其他文档只放指针。机器：`bis-ms7e56.tail4413b4.ts.net`（RTX 5060 Ti 16 GB）。详细实测记录见 [`remote-training-workflow.md`](remote-training-workflow.md)。

## 约定

- 单卡队列：task-spooler，`TS_SOCKET=/tmp/gpu_queue.socket`；`ts -l` 看队列（`run=1/1` 表示正在跑）。
- 提交：`TS_ONFINISH=$HOME/rc_work/gpu_jobs/on_finish.sh ts -L <label> <job.sh>`；label 与 run 名一致（见 INDEX 命名规范）。
- 作业脚本契约：`source ~/rc_work/gpu_jobs/common.sh`（日志/summary/GPU lock/flag/trap）；summary 最后一行 `<job> done <time>` 只在成功时写；失败/中断要非零退出并把 verdict 写 summary。
- 单 job ≤ 2 h；夜间关机约 00:00–09:00（可等到 00:30）；关机/重启会丢队列，长任务必须 checkpoint（save-interval ≤ 50）。
- 清理：`ts -k <id>` 只是请求取消；标志位以 `ts -l` + `nvidia-smi` 为准，必要时手工 `printf 0 > ~/5060ti_machine_use_flag.txt`。
- 不绕过队列直接起训练；调试用 2-iter × 16-env 的小 job。日志：`~/rc_work/logs/<job>_summary.txt`、`~/rc_work/logs/<job>.log`。

## 目录（建议，逐步迁移）

- `gpu_jobs/ppo/`（PPO/BC 线）、`gpu_jobs/him/`（HIM 线，历史）、`gpu_jobs/common.sh`、`on_finish.sh`、`kill_test.sh`、`probe/`。
- 产物：`~/rc_work/models/<line>/<part>/<name>/`（新产物），旧目录不动；run 名 `<line>_<part>_<family>_<purpose>_<MMDD>`。
- 队列/tag 与 run 记录的映射写 `comp/RUN_LEDGER.md` 与各线 run 记录。
