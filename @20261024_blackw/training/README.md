# blackW Part2 训练侧代码快照（2026-10-25 审计修复后）

这里保存的是**远程训练仓**（`bis-ms7e56:~/rc_work/part2_team_race/src/`，源于 MjLab + mujoco_warp 的 blackW 任务）中
本次审计修复涉及的文件快照，便于入库追溯；远程训练仓仍是运行时真值，修改时两边需同步。

| 文件 | 说明 |
|---|---|
| `blackw/env_cfgs.py` | 官方 Part2 任务组装：judge-aligned `part2_success/failure` 谓词（含 hold/爬上证据）、exact 任务 sub-terrain key、anti-farm 奖励、`BLACKW_MAX_ROW`、部署物理对齐 |
| `blackw/exact_terrain.py` | 官方几何地形生成（坡道改为实心楔形，修正 y 偏移） |
| `blackw/guarded_ppo.py` | 权重信赖域 PPO（微调 BC 权重时防止灾难性漂移） |
| `black/black_config.py` | PPO/策略超参数 env 覆盖（entropy/std/epochs/mini-batches/normalize-advantage） |
| `black/rl_cfg.py` | 上述超参数到 rsl_rl 配置的映射 + `BLACKW_ALGORITHM` 算法类选择 |

修复背景、证据与仍然存在的问题见 [`../docs/training/part2-bc-policy-report.md`](../../@20261019_locomotion/docs/training/part2-bc-policy-report.md) §11。
