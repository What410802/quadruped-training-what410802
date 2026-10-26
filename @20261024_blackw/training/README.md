# blackW Part2 训练侧代码快照（2026-10-26，审计修复后）

这里保存的是**远程训练仓**（`bis-ms7e56:~/rc_work/part2_team_race/src/`，MjLab v1.6.0 + mujoco_warp 的 blackW 任务）中
PPO/BC 线涉及的文件快照，便于入库追溯；远程训练仓仍是运行时真值（`/tmp/part2_train/src` 只是本机中转副本，可能随重启丢失），修改时以本快照为准拷回远程。

| 文件 | 说明 |
|---|---|
| `blackw/env_cfgs.py` | Part2 任务组装：judge v5 对齐的 `part2_success/failure` 谓词（hold/爬上证据/支撑带）、exact 任务 sub-terrain key、anti-farm 奖励、`BLACKW_MAX_ROW`、部署物理对齐、`BLACKW_NCONMAX/NJMAX` 容量覆盖、wall/plum 任务 |
| `blackw/__init__.py` | 任务注册（`blackw-{platform,wall,slope,stairs,trench}-exact`、`blackw-plum`、`blackw-official`、`blackw-flat`） |
| `blackw/exact_terrain.py` | 官方几何地形生成（坡道实心楔形、修正 y 偏移、全部坡道统一 `_ramp()`） |
| `blackw/guarded_ppo.py` | 权重信赖域 PPO（`GuardedPPO`，微调 BC 权重时防灾难性漂移） |
| `black/black_config.py` | PPO/策略超参数 env 覆盖（entropy/std/epochs/mini-batches/normalize-advantage） |
| `black/rl_cfg.py` | 上述超参数到 rsl_rl 配置的映射 + `BLACKW_ALGORITHM` 算法类选择 |

修复背景、证据与当前状态见主报告 [`part2-bc-policy-report.md`](../../@20261019_locomotion/docs/21-part2-ppo/bc-policy-report.md) 与归档 [`part2-ppo-training-history.md`](../../@20261019_locomotion/docs/21-part2-ppo/history-experiments.md) §11；明天上机步骤见交接 [`part2-ppo-handoff-2026-10-26.md`](../../@20261019_locomotion/docs/21-part2-ppo/handoff.md)。
