> **2026-10-21 用户审查后已作废（仅历史）**：该权重对应旧稀疏布局（24 小块 + 矮围墙），石块覆盖率不足，狗实际站在地面、出坑靠围栏挡住。不要把它当作 S1b-free 证据；dense 80 石块布局的权重另行导出。

# free-gravel-v2-700

2026-10-21 的 S1b-free（自由关节砂砾）候选：从 `flat-ft-2500` 出发，在 `black-gravel-free` 上做 32 envs 小 batch 微调；最终 `model_3896`（v2_700 段）。**不是最终验收策略**。

| 项 | 值 |
|---|---|
| 训练 task | `black-gravel-free`（24 个 free-joint 石块，中心 0.65 m 清空，矮围墙；石-石接触关闭） |
| 训练仓库 | `nwwolf_mjlab_training_release` 基线 `24c7f16` + 2026-10-21 工作区改动（free task / foot_clearance / mirror loss / reward safety；未 commit） |
| run 目录（远程） | `logs/rsl_rl/black_velocity/2026-10-21_13-23-29_gravel_free_v2_700/` |
| checkpoint | `model_3896.pt` |
| 初始化 | `flat-ft-2500` → 稳定化 free 微调链（stable100 → stable400 → v2_200 → v2_700）；command curriculum 从 ±1 重新开始 |
| 导出 | `.venv/bin/export --task-id black-gravel-free --load-run 2026-10-21_13-23-29_gravel_free_v2_700 --checkpoint model_3896.pt --output-dir ~/rc_work/baseline/exported_free_gravel_v2_700` |
| `policy.pt` | 770,774 B，sha256 `9b5dc867efe6b62155b3aa8734890b8d1dbd791526fd67d39d262239e73fb178` |
| 契约 | TorchScript actor-only；输入 `[1,45]`；输出 `[1,12]` raw action；`q_target = q_default + 0.25·raw`；Kp=40/Kd=1.2；50 Hz |

## S1b-free 评测（play 模式，固定命令序列）

| envs | 摔倒率 | 0.3 m/s vx MAE | 0.5 m/s vx MAE | p95 tilt（0.3/0.5） | 结论 |
|---|---|---|---|---|---|
| 16 | 0 | 0.166 | 0.154 | 9.4° / 5.3° | 0 摔倒；0.3 m/s 略高于 0.15 |
| **32** | **0** | **0.129** | **0.084** | **3.1° / 2.8°** | provisional pass（按 eval-protocol §6.2 固定口径） |

补充：v2_900（再 200 iter）反而在 16 envs 出现 6.25% 摔倒和 0.3/0.5 MAE 0.128/0.196；说明自由石块任务对最后一次更新/随机布局仍有方差。当前保留 **v2_700** 作为 free 候选，不追最后一次 checkpoint。

## 可视诊断

视频 `gravel_free_v2_700_commands.mp4`（本地 `prep.d/videos/`，不入库）覆盖 stand/fwd 0.3/0.8/1.5/bwd/lat/yaw/combined；可看石块被推挤、足端接触和转向。另有 `overview/black-gravel-free_overview_v2.png` 展示 24 石块 + 围墙布局。

## 限制

- 自由石块不是颗粒介质；只是“踩得动/会滚动”的近似，不能代替真实砂砾坑。
- `black-gravel-free` 只适合 16–64 envs；4096 会因 free joint 数量/接触容量失败。
- 只在 32 envs、seed/布局固定的 screening 下 provisional pass；需要多 seed、随机石块布局和固定地形/命令复测后才能谈验收。
- 权重入库策略见 [`../../../docs/training/experiments.md`](../../../docs/training/experiments.md) §5。
