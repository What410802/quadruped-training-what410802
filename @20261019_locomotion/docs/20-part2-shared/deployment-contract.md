# Part2 部署契约（rl_sar blackW）

> 本文件抽取并统一 `@20261024_blackw/README.md` 的部署契约与操作要点；工作区 README 仍是环境说明入口。**代码位置**：`@20261024_blackw/ws/src/rl_sar_blackw`（部署栈）、`@20261024_blackw/ws/src/quadruped_ros2_blackw`（仿真节点/电机模型）。

## 1. 策略目录 drop-in 契约

- 路径：`policy/blackW/<name>/{policy.pt, config.yaml}`；可选 `manifest.json`（推荐，由 `scripts/import_blackw_policy.py` 生成）。
- `config.yaml`：**顶层 key 必须等于 `blackW/<name>`**（C++ 按目录名取子节点，Python judge 有兜底）；`model_name` 必须是同目录真实文件名（通常 `policy.pt`）；`model_path` 仅展示。
- 观测：57 × 6 历史（frame-major，新→旧）= 342；动作 16（`FL,FR,RL,RR × hip,thigh,calf,wheel`）。
- `action_scale`：腿 ±0.25，轮 **FL+10 / FR−10 / RL+10 / RR−10**（右腿负号，训练同约定）。
- 力矩上限（逐关节）：`[23.7, 23.7, 59.25, 20] × 4`；sim_node 默认从 MJCF `<motor ctrlrange>` 读取，`tau_max_array` 参数可覆盖。
- 频率字段：`base.yaml` 与每份 `config.yaml` 都必须声明 `control_hz: 200` / `policy_hz: 50`；`rl_sdk.cpp` 在 `InitRL` 与 `dt/decimation` 对账（偏差 >2% 抛异常，rl_sim 捕获后安全退出）。
- 验证命令：`pixi run python @20261024_blackw/scripts/import_blackw_policy.py --check policy/blackW/<name>`；批量：`check_policy_dirs.py`；谓词-judge 对拍：`check_predicate_judge_parity.py`。

## 2. 控制栈事实

- 场景物理：MJCF `<option timestep="0.002" ... cone="elliptic" impratio="100">`；PD/力矩在 `sim_node` 每物理步（500 Hz）计算。
- `policy/blackW/base.yaml`：`dt: 0.005`、`decimation: 4` → **策略 50 Hz**、命令刷新 200 Hz；策略输入输出节拍与训练一致（训练 0.002 s × 10 dec、50 Hz）。
- `command_limit.hpp` 的 slew 每个控制周期（5 ms）执行一次、每策略周期（4 个控制周期）共 4 次 → 有效 slew = 配置值（60 rad/s）。审计 F6 曾按"每策略周期只夹一次"推成 15 rad/s，但 `Command_limit_selftest.cpp` 的重复周期用例（build 后跑）会证明是 60；改 dt/decimation 时仍需跑该自测。
- `src/rl_sim.cpp` 在每次进 RL 前对 history buffer 做 backfill（与训练一致），否则 6 帧历史首帧全 0。

## 3. 运行（sim）

```bash
pixi run ros2-build
pixi run ros2 launch rl_sar_blackw rl_sim_blackw.launch.py policy_name:=comp_bc_v5
# Part2 某档：
pixi run ros2 launch rl_sar_blackw rl_sim_blackw.launch.py policy_name:=comp_bc_v5 part:=2 part2_level:=stairs_20cm
```

- 操作（键位以 `include/input_map.hpp` 为准）：键盘 `0` 起身、`1` 进 RL、`W/S/A/D/Q/E` 移动、`9` 趴下、`P` 阻尼、`R` 复位、`N` 导航模式、`2/3/4` 切官方策略；手柄 `A` 起身、`B` 趴下、`RB+D-pad 上` 进 RL、`RB+Y` 复位、`X` 导航模式、`LB+X` 阻尼、`Start+D-pad 左/上/右` 切官方策略。
- `joy_command_scale` 默认 1.5（摇杆满偏 = 1.5 m/s 或 rad/s）；也可用 `/cmd_vel`（导航模式）给确定指令。
- **运行中只能切官方 flat/stair/obstacle**；自训策略（comp_bc_*）需重开 launch 改 `policy_name:=<name>`。

## 4. 多策略与交付

- 交付 ≤3 份策略时可每个障碍/一组障碍启动一次 launch（用不同 `policy_name`），runbook 待写（见 `status.md` 待办）。
- 现有候选：`comp_bc_v5`（judge 750）、`comp_high600`、`comp_lane300`；`models/comp_bc_v5` 是带 manifest/sha 的交付包样板。

## 5. 已知缺口（2026-10-26）

1. **Part2 逐档部署 smoke**：工具已实现（`scripts/smoke_deploy_part2.py`），但 **5/20 结果作废**：deploy levels 曾用旧 proxy 场景 `part2_*.xml` 而 judge 用官方 `part2_off_*.xml`（20/20 不一致，2026-10-26 已修 `part2_levels.json`）；官方 `obstacle` 权重同一 smoke 也 5/20 且数值爆炸（trench z≈-1118）→ 栈有效性未验证。以官方权重对照 + 官方场景重跑后，才能谈"judge 750 vs 部署能力"。另：项目文档中的 750/743 已被独立评审判为未审计 executor 证据。
2. 官方 mesh 资产 `scenes/blackW/assets/` 未入库（gitignore，约 42 MB）；演示前需从官方 ReadOnly 源复制（README 有来源说明）。
3. 转向能力：`comp_bc_v5` 在 sim 里 1.0 rad/s 转向实测不达标（训练指令 yaw 覆盖有限）；验收口径要求覆盖手柄全范围，需训练侧补。
4. 实机路径：无硬件驱动节点、`rl_sim` 时钟依赖 `/motor_state.sim_time`、无逐关节限幅/标定/急停——实机演示不可用。
5. `RL_DEBUG_OBS=1` 的 obs/action dump 已接读取工具：`scripts/read_rl_obs_debug.py --csv /tmp/rl_obs_debug.csv`（obs 57 分段/首帧 JSON），用于与 judge 侧 replay 对拍。
5. 生成策略目录（约 128 个 `policy/blackW/*`）不入库，只保留 curated/official；恢复用 `import_blackw_policy.py`。
