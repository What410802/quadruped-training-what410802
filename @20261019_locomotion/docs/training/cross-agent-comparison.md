# 与另一 Agent 的 Part 2 训练路线对比

> 只读观察，2026-10-25。另一 Agent 的工作目录是远程训练机 `~/rc_work/part2_team_race`；本文不修改其代码、不停止其任务。用户提到的 BeamDojo 路线在当前仓库里尚未看到 `BeamDojo`/`beam` 代码/配置；当前实际在跑的是 **PPO + BC 初始化 + official Part2 mixed terrain**（run `ppo_bc_v4*`、`smoke_judge*`）。

## 1. 对方实际在跑什么

- 任务：`blackw-official`，参数来自环境变量，例如 `BLACKW_CLIMB_W`、`BLACKW_GOAL_W`、`BLACKW_PROGRESS_W`、`BLACKW_CLEAR_W`、`BLACKW_MAX_ROW`；最新进程用 `BLACKW_PHYSICS_DT=0.002`、`BLACKW_DECIMATION=10`、`BLACKW_LR=2e-4`、`1024 envs`。
- 初始化：`model_600_bc_v4_s03.pt` / BC mirror，即先用官方 blackW 策略做 behavior cloning/DAgger，再 PPO 微调。
- 地形：`blackw/official mixed`，16 m patch，五个 category（platform/high_wall/slope/stairs/trench）；另有 plum 任务。
- 训练成功项：不是 root-x goal，而是 `_part2_terrain_state` 用四轮 body 位置算 `part2_success` / `part2_failure` / `part2_clear`；trench 还有 wheel drop penalty。目标是对齐严格 Part2 judge。
- 日志：`/tmp/train_ppo_bc_v4.log` 中 `competition_goal_reached` 约 0.22–0.35，mean reward≈34；这是 PPO/BC 旧任务口径，不能直接当 strict judge 分项。

## 2. 关键差异

| 维度 | 我的 blackW HIM 路线 | 对方当前路线 |
|---|---|---|
| 策略 | HIM actor（57×6 history + estimator latent），官方 `.pt` warm-start；blind | PPO/BC MLP，先从官方策略 BC，再 PPO；另有 depth 任务 |
| 成功判据 | 平台用 root x/z，mixed 用 goal-x；不是严格 judge | `part2_success/failure` 用四轮 body 高度/位置，trench 还检查 wheel drop |
| 地形 | platform/wall/slope 基本 official；trench 仍是简化平底 gap；stairs 只有上行；无 plum | official trench（0.3m plateau + 1m entry/exit ramps + 0.1–0.3m slot）、stairs up+down、plum 24 cubes |
| 控制/物理 | 默认 MjLab sim dt/decimation；HIM 训练频繁 Warp assert | `sim dt=0.002`、`decimation=10`、LR=2e-4、1024 envs；显式稳定化 |
| 命令 | 已改三轴 wide command（vx0–1、vy±0.3、wz±1） | 前向主导窄命令（vx0.25–1、vy±0.15、wz±0.2） |
| 课程 | 单类别 easy/平台；mixed 从 row0 | `BLACKW_MAX_ROW` 手动行课程 + 五类混合 |
| 计算 | 64–512 envs，NaN/Warp assert 限制 | 1024 envs 长跑，GPU 占用高 |

## 3. 应该借鉴的部分

1. **严格 Part2 success/failure/clear 项**：直接移植 `_part2_terrain_state` 的思路，用四轮支撑面/沟槽 drop 判据替代 root-x goal；这是当前 HIM 训练 false success 和平台学不动的核心缺口。
2. **official exact terrain 补全**：trench 的 plateau+ramp、stairs 的 up+down、plum 的 24 cubes；我们现在的简化版不能作为高台/沟壑/梅花桩的训练/评测依据。
3. **把 judge 规则写进训练**：`part2_failure` 终止 + `part2_clear` 成功奖励，比只给 x-progress 更接近评分。
4. **物理/控制一致性**：对方用 2 ms sim + 10 decimation；需要与部署控制频率、延迟、kp/kd 做 A/B，而不是只在默认 dt 上追 iter。
5. **BC/DAgger 初始化**：对方从官方策略 BC 后再 PPO，能快速获得基本越障行为；HIM 可以把官方 actor/teacher 的 action 蒸馏进 HIM actor（不是直接加载，因为结构不同）。
6. **分项日志**：按 terrain column/row 统计 success/failure，而不是只看 mixed goal 占比；这样能定位 platform vs trench vs stairs。

## 4. 不建议直接照搬的部分

- 对方是 PPO/BC MLP，我是 HIM actor；checkpoint 不能直接互换。HIM 的 342 观测/16 动作 contract 与 57 维 MLP 不同，只能做 **distillation / teacher action 标签**。
- 对方当前运行是 forward-dominant 窄命令；用户明确要求最终 `vx/vy/wz` 组合都跟随，不能把 `vy=0, wz=0` 固定住。
- 对方仓库与我的训练仓并行占用 GPU；直接在其目录改代码会干扰，必须只读借鉴或另开分支。
- 对方日志里的 `competition_goal_reached` 是旧 goal-x 口径，不是 strict judge 分；引用时必须区分。

## 5. 建议的下一步

1. 在我的 HIM official mixed task 里加入 `part2_success/part2_failure/part2_clear`（四轮判据）和 trench drop penalty；
2. 补 official trench/stairs/plum 几何；先做平台/沟壑单类别 smoke；
3. 用 BC/DAgger teacher action 做 HIM 蒸馏初始化，对比“官方 `.pt` HIM warm-start”与“BC 蒸馏”两条路线；
4. 控制频率/延迟 DR 与 kp/kd 一致性检查纳入 smoke；
5. 最后再扩到高台 40 / 斜坡 45 / 沟壑 30 和 plum。


## 6. 已实际借鉴的改动（2026-10-25）

- 已把 `_part2_terrain_state` 的 strict 四轮 success/failure 逻辑移植到我们的 `blackw/official mixed`：`part2_success`、`part2_failure`、`part2_clear`，并移除 x-only `competition_goal`。
- 已同步 official trench（plateau + entry/exit ramps + slot）、stairs（up+down+landing）和 plum 几何到 `exact_terrain.py`；`ExactPlumTerrainCfg` 尚未接 task。
- 32 envs、20 iter strict smoke 通过；下一步再用 64/128 envs 做 platform/trench 分项 success 验证。
