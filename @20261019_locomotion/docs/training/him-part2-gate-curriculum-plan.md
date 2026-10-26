# HIM Part2 最低档 100% gate 与课程推进

> 2026-10-25 讨论稿；远程机已关，明天用 task-spooler 串行全显存执行。

## 1. 当前课程实现（重要）

- `black_competition_env_cfg` 显式 `cfg.curriculum.pop("terrain_levels")`，**没有启用 MjLab 自带 terrain curriculum**；原因是 native `terrain_levels_vel` 按“走过的距离”升降，而 Part2 障碍成功后 episode 会提前终止，距离不够会被误降级/停级。
- `blackw_official_mixed_env_cfg` 只设置 `max_init_terrain_level`（当前 0），训练难度是**固定起始行**，不是自动逐级升档。
- 所以现在的“更高档位长训”不是自动基于上一档位策略；实际做法只能是**resume 上一 checkpoint + 手动提高起始行/任务难度**，没有“前一档已鲁棒”的强制门。
- 结论：不能把 MjLab 自带课程当成 success-gated 课程；需要显式 gate 或自定义 CurriculumTerm。

## 2. 最低档 100% gate 协议

目标：除梅花桩外的所有 Part2 地形，在最低官方档位达到经验上的 100% 成功，并且高档只调难度参数、不改变几何拓扑。

类别与最低档：

| category | 最低档 |
|---|---|
| high_platform | 10 cm |
| slope | 20° |
| stairs | 10 cm/级 |
| high_wall | 10 cm |
| trench | 10 cm gap |

测试要求：

- 每个类别至少 **20/20 次严格成功**；建议重复 2–3 组 seed，报告 20/20、40/40 或 60/60。
- 初始状态随机化：spawn 位置/朝向/初始速度抖动，范围按部署起点和 judge 容差设定。
- 指令随机化：使用真实手柄/线性映射后的 `vx, vy, wz` 范围，包含 stop 和组合指令；不能只测试固定 `vx=0.5`。
- 对每个 attempt 同时记录：`part2_success`/`part2_failure`、wheel drop、lane、final pose、速度跟踪误差。
- 成功判据用 strict judge/训练谓词 v5；不能用 root-x goal。

100% 只能是经验 gate：报告 20/20、40/40 等，不声称数学证明。

## 3. 高档“无质变”检查

- platform：同 1.5×1.6m box，只改高度 0.10→0.40；
- slope：同 2m horizontal run，只改 20→45°；
- stairs：同 6 上 + landing + 6 下，只改总高；
- high_wall：同 1.4m 宽/0.12m 厚，只改高度；
- trench：同 plateau+ramp+1.4m channel，只改 gap 0.10→0.30。

当前 `exact_terrain.py` 已恢复培训方原始几何；平台圆角实验已撤销。高档检查用同一 task/同一谓词/同一动作 contract，只允许 `max_init_terrain_level` 和难度参数变化。

## 4. 课程推进方式

推荐先手动 gate，不要马上写自动课程：

1. **Row0 专项**：每个 category 单独训练/eval，row0 达到 20/20；
2. **Row0 混合**：把已通过专项的策略在 mixed row0 上微调，确保 5 类都仍 20/20；
3. **逐档 resume**：只把 `max_init_terrain_level` 提到下一行，resume 上一 best checkpoint；每个新行先 eval 20 次，未过就回退/继续 row；
4. **命令阶段**：每行先 fixed 或 narrow 三轴，过 gate 后扩到真实手柄完整范围；命令范围变化也算 gate 条件；
5. **自动课程**：如果手动 gate 稳定，再实现 success-gated CurriculumTerm（按 `part2_success` 的滚动成功率和 attempts 升降 `terrain_levels`），不要用距离型 `terrain_levels_vel`。

## 5. 明天执行顺序

1. task-spooler 单 slot 启动；
2. 先跑 row0 五类 HIM/现有 best policy 的 20 次 gate，输出 per-category JSON；
3. 只对未过 gate 的类别改训练信号/课程；
4. gate 通过后再升行；
5. 每个 job 全 GPU，另一个 Agent 的任务在队列中串行等待。

## 6. 已落地的 gate 工具与 row 参数

- gate 脚本：[him_part2_gate.py](../../scripts/agent_scripts/him_part2_gate.py)
  - 必须用 `play=False` 的训练配置；`play=True` 没有 Part2 终止项，会假测出 0；
  - 显式 `assert "part2_success" in term_mgr.active_terms`；
  - `auto_reset=False`，reset 前读取 strict `part2_success/failure/out_of_course`；
  - 关闭 obs corruption，timeout 计 attempt，按 category 过滤，输出 JSON。
- 新增 `BLACKW_MAX_ROW`：`blackw-platform-exact-him` 和 `blackw-official-him` 都可通过它选择 manual row。
- 示例：

```bash
python @20261019_locomotion/scripts/agent_scripts/him_part2_gate.py \
  --task blackw-official-him \
  --checkpoint /path/model_XXX.pt \
  --category platform --row 0 --attempts 20 \
  --vx-min 0 --vx-max 1 --vy 0.3 --wz 1.0 \
  --out gate_platform_r0.json
```

修正后的 gate smoke：platform row0，2 attempts 得到 2/2 success，证明它不是“缺 term 恒 0”的假测量。旧版 play=True 的 smoke 只验证了 JSON 能生成，不能区分“没这项”和“没成功”，已废弃。

## 7. 已落地的数值防护

- HIM runner 安装 reward clamp（默认 ±50）和 return/advantage clamp（±1000/±100）；
- HIMPPO 对非有限 loss/梯度跳过 update 并打印 `[GUARD]`；
- HIMEstimator 对非有限 loss/grad 跳过 update；
- HIM policy 对 non-finite `log_std_param` 做最后一次 sanitize；
- terminal observation target 明确 `nan_to_num`；
- `estimator_velocity` observation group 改为 `sanitize`；
- `_nonfinite_state` 增加 `sensordata` 检查。
