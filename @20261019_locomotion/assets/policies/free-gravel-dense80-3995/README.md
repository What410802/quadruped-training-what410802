> **2026-10-21 用户审查后降级（过渡/木块参考）**：该权重使用 80 块 15–19 cm 大石块，尺寸不符合实际碎石 3–10 cm，不再作为 S1b-free 证据；只保留作“大块/整片石/木块”仿真参考。新 composite 见 `black-gravel-free`（120 自由 + 700 静态、3–8 cm、6 cm 抬高石床）。

# free-gravel-dense80-3995

2026-10-21 的“大块/整片石”过渡策略：80 块 15–19 cm 大石块、无围墙、16 envs 小 batch 微调；最终 `model_3995`。**不是 S1b-free 证据，只作木块/大障碍参考**。

| 项 | 值 |
|---|---|
| 训练 task | `black-gravel-free`：80 块 free-joint 石块（full 15–19 cm × 13–17 cm），1.6×1.6 m 方阵，无围墙；石-石接触关闭，中心不额外清空 |
| 覆盖率 | 投影面积和 **79.0%**，栅格化 union **76.4%**（`free_gravel.py:coverage_stats` + 独立采样） |
| 训练仓库 | `nwwolf_mjlab_training_release` 基线 `24c7f16` + 2026-10-21 工作区改动（free task / foot_clearance / mirror loss / reward safety；未 commit） |
| run 目录（远程） | `logs/rsl_rl/black_velocity/2026-10-21_13-58-28_free_dense80_ft100b/` |
| checkpoint | `model_3995.pt` |
| 初始化 | 旧 `free-gravel-v2-700` resume；16 envs × 100 iter，`--agent.command-curriculum-restore none` |
| 导出 | `.venv/bin/export --task-id black-gravel-free --load-run 2026-10-21_13-58-28_free_dense80_ft100b --checkpoint model_3995.pt --output-dir ~/rc_work/baseline/exported_free_dense80` |
| `policy.pt` | 770,774 B，sha256 `b27c62bfb7bedb39bb8e3191c8098a65ede04d2ee876527c50aecb15aa3f54a1` |
| 契约 | TorchScript actor-only；输入 `[1,45]`；输出 `[1,12]` raw action；`q_target = q_default + 0.25·raw`；Kp=40/Kd=1.2；50 Hz |

## S1b-free 评测（play 模式，固定命令序列含 arc-left/right）

| envs | 摔倒率 | 0.3 m/s vx MAE | 0.5 m/s vx MAE | p95 tilt 0.3/0.5 | 结论 |
|---|---|---|---|---|---|
| **16** | **0%** | **0.077** | **0.124** | **3.1° / 2.9°** | provisional pass；arc-left/right 也是 0 摔倒、MAE 0.123/0.138 |
| 32 | 0% | 0.079 | 0.128 | 3.3° / 3.0° | 主 gate 也过；arc-left/right 0 摔倒、MAE 0.119/0.135（提高 nconmax/njmax 后不再出现 NaN） |

旧的 24 石块/带围墙 `free-gravel-v2-700` 已被用户审查判定为“石块太稀、狗站在地面、出坑靠围栏”，对应权重仅作历史保留。

## 可视诊断

- `prep.d/videos/free_dense80_commands.mp4`：固定命令序列，含 arc-left/right；可看狗从石层上走到平面。
- `prep.d/videos/overview/black-gravel-free_dense80_overview.png`：俯视图，石块铺满 1.6 m 方阵，无围墙。

## 限制

- 自由石块不是颗粒介质；只是“踩得动/会滚动”的近似。
- 16–32 envs 才能跑；4096 envs 不适用。
- 32 envs 需要 `nconmax=2048 / njmax=4096`；低容量会出现 `nefc overflow`/arc 段 NaN。正式复测仍要做 multi-seed/固定布局。
- 权重入库策略见 [`../../../docs/training/experiments.md`](../../../docs/training/experiments.md) §5。
