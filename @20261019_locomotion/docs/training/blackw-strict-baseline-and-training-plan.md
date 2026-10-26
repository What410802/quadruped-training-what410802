# blackW 固定动作、严格 Part2 baseline 与训练环境计划（2026-10-24）

## 1. 固定动作（Part1）

官方 blackW `quadruped_control` 自带固定姿态轮驱行为，已复制到 `@20261024_blackw/ws/src/rl_sar_blackw/policy/blackW/behaviors/` 并在 rl_sar 的 blackW FSM 中实现通用固定姿态轮驱状态：

- `low_bar_drive`：低姿态差速轮驱过限高杆；
- `bridge_drive`：固定姿态过窄带桥；
- `car_drive`：备用固定姿态轮驱。

按键：低限杆 `Back + D-pad Down`（键盘 `5`），木桥 `Back + D-pad Right`（键盘 `6`），备用 `Back + D-pad Left`（键盘 `7`）；进入后 `RB + D-pad Up` / `1` 回 RL。策略切换改为 `Start + D-pad Left/Up/Right`（键盘 `2/3/4`），避免单键 RB/LB 与组合键同时触发。

无头测试：`@20261024_blackw/scripts/check_fixed_actions.py --case lowbar|bridge`，用 ROS `/joy` 替代手柄。2026-10-24 本机：
- lowbar：进入 `LowBarDrive`，从 y=-10.4 穿到 y=-5.66，z≈0.31；
- bridge：进入 `BridgeDrive`，从 y=-3.5 穿到 y≈+1.15。

Part2 规则仅允许 RL，固定动作只用于 Part1，不得进入能力测试。

## 2. 严格 Part2 baseline

修正了两件事：

1. Part2 出生点使用 blackW 轮底高度修正后的 `spawn`（`@20261024_blackw/.../part2_levels.json`），不再用按点足高度写的 `judge.start`；
2. `Part2JudgeV2` 的 `gap` 分支加严：`trench_bottom` 接触 → `trench_bottom_contact`；near 边跨越不在 lane 内 → `gap_bypass_outside_lane`；并补充自检。

三份官方策略（6 s 窗口，严格口径）结果归档在 `prep.d/blackw_validation/summary_strict_20261024.md`：

| policy | total |
|---|---:|
| obstacle | 500 |
| stair | 400 |
| flat | 210 |

跨策略最佳组合约 **650/1300**；主要缺口仍为 plum 200、high_platform 40cm 的 +100、slope 35/45° 的 +150、trench 30cm 的 +300（约 550 分）。

## 3. 训练环境接入计划（blackW）

当前训练仓 `prep.d/training_repo_local` 只有点足 black（12 关节、45 维单帧/270 维 6 帧、12 动作），没有 blackW。要训练 Part2 高档位，至少需要：

1. **机器人资产/常量**：16 关节（每条腿 hip/thigh/calf/wheel），默认姿态、Kp/Kd、力矩限制、轮半径、policy 关节顺序 FL/FR/RL/RR 与 MJCF actuator 顺序 FL/FR/RR/RL 的映射；
2. **动作接口**：腿为位置残差（scale 0.25），轮为速度目标（scale ±10）；MjLab 需新增轮速 action term/actuator，或自定义 action manager；
3. **观测契约**：57 维/帧 ×6 历史 = 342 维（commands 3 + ang_vel 3 + gravity 3 + joint_pos_error 16 + joint_vel 16 + last_action 16），与官方 blackW 策略一致；
4. **地形/课程**：真实 Part2 几何（高台 40、楼梯 30、斜坡 45、沟壑 30、梅花桩）或程序化等价地形；成功判据需与严格 judge 一致；
5. **策略初始化**：优先复用官方 blackW HIM 342→16 架构/权重（warm-start/teacher），而不是从零训练；
6. **评测**：训练后先用官方 Part2 场景+严格 judge，再决定是否上深度/heightmap。

**阻塞**：远程训练机 `bis-ms7e56` 当前 tailscale offline / SSH 超时，无法提交 GPU 训练；本地训练仓 venv 正在补装（无 GPU）。因此本阶段先完成代码/地形/契约接入，等远程恢复后启动训练并报告。

## 4. 优先级

1. Part1 固定动作（低限杆已通路，木桥/事件链继续标定）；
2. 训练仓 blackW 接入（最高杠杆；决定 Part2 高档位能否训练）；
3. Part2 盲训练高价值目标：high_platform 40、slope 45、trench 30、stairs 30；
4. plum/窄桥深度或 heightmap（最后）。
