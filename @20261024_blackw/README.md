# blackW 轮足 rl_sar 部署工作区（独立副本）

这个目录是从 `@20261005_ros2`（`quadruped_ros2` 仿真/消息包）与 `@20261007_assignment`（`rl_sar` 策略栈）复制出来、
专门给 **blackW 16 关节轮足** 做部署适配的**隔离副本**；原目录保持原样，点足 black 的 `check_walk` 已回归通过。

## 已实现

- `ws/src/quadruped_ros2_blackw`：16 关节消息（`float64[]` 动态数组）、MuJoCo sim_node（按模型 `nu` 驱动，12/16 都能跑）、joy/controller 节点。
- `ws/src/rl_sar_blackw`：
  - `policy/blackW/`：官方 blackW `flat` / `stair` / `obstacle` 三份 TorchScript 策略（从 `ReadOnly.d/quadruped_control/assets/policies/blackW/` 复制，Apache-2.0，来源见其 `SOURCE.md`）；
  - `policy/blackW/base.yaml` + `policy/blackW/{flat,stair,obstacle}/config.yaml`：57 维观测 ×6 历史 = 342 输入、16 动作、轮速度控制、Kp/Kd/action_scale/关节顺序/`joint_mapping` 已按 blackW 契约配置；
  - `policy/blackW/fsm.hpp`：blackW 单段起身 FSM（16 关节），注册 robot type `blackW`；
  - `launch/rl_sim_blackw.launch.py`：sim_node + joy_node + rl_sim，`robot_name=blackW`，支持 `policy_name:=flat|stair|obstacle` 和 `scene:=...`；
  - `scenes/blackW/`：官方 blackW MJCF + 平地/官方 Part1 地形场景。
- `policy/blackW/behaviors/`：官方 blackW `low_bar_drive` / `bridge_drive` / `car_drive` 固定姿态轮驱配置（从 `ReadOnly.d/quadruped_control/configs/behaviors/blackW/` 复制；Part1 固定动作）。
- `scripts/check_walk_blackw.py`：7 项无头自检（复制并适配自 assignment），支持 `--policy flat|stair|obstacle`。
- `scripts/check_fixed_actions.py`：用 ROS 发布 `/joy` 代替手柄的固定动作无头自检（lowbar/bridge），见下方命令。
- `policy/blackW/behaviors/`：官方 blackW `low_bar_drive` / `bridge_drive` / `car_drive` 固定姿态轮驱配置（从 `ReadOnly.d/quadruped_control/configs/behaviors/blackW/` 复制；Part1 固定动作；Part2 规则不允许固定动作）。
- `@20261024_blackw` 不修改原 `@20261005_ros2` / `@20261007_assignment`；点足 black 的原有 `check_walk.py` 已通过。

## 场景接入（Part 1 / Part 2）

- `part:=1`（默认）：官方 Part1 障碍场 `scenes/blackW/scene_terrain.xml`，出生点固定为出发区颜色块 `(3.7, -9.0, 0.676)`、yaw=0（高度按 blackW 轮底高度修正）。
- `part:=2 part2_level:=<key>`：Part2 某一档能力场景（场景来自 `scenes/blackW/part2_levels.json`，共 20 档；里面的 `spawn` 字段是给 blackW 修正过高度的出生位姿，`start` 仍保留原始 judge 位姿）。
- `spawn_x/spawn_y/spawn_z/spawn_yaw:=...` 可按分量覆盖出生点（未给的分量用当前 Part/档位的修正默认值；全部给 `nan` 等价于不覆盖、但 launch 仍会填默认）。
- `scene:=<xml>` 也可以显式指定场景；如果是 Part1 场景或 20 个 Part2 场景之一，launch 会自动套用对应修正出生点，不会回到模型原点穿模。

可用 Part2 key：
`high_platform_10cm/20cm/30cm/40cm`、`stairs_10cm/15cm/20cm/30cm`、`slope_20deg/30deg/35deg/45deg`、`high_wall_10cm/20cm/30cm/40cm`、`trench_10cm/20cm/30cm`、`plum_1bool`。

## Part2 策略与官方几何评测（2026-10-26 更新，judge v5）

- **当前最佳权重**：`policy/blackW/comp_bc_v5/`（342→512→256→128→16 ELU MLP，官方 obstacle/stair/flat 三份权重 BC + 两轮 DAgger 蒸馏，部署契约与 `config.yaml` 齐全）。已入库备份：`@20261024_blackw/models/comp_bc_v5/`（policy.pt + checkpoint + config + manifest，含 sha256/评测数据/命令 profile）。
- **严格 judge v5（官方几何隔离场景，0.002s 物理）**：逐障碍选命令的参考 profile = **750/1300**（最好情况；4 次挑战期望 ≈743）；同 judge 官方三份权重基线 = **660/1300**。
- 最低档（平台 10/wall 10/slope 20/stairs 10/trench 10）judge 各 8 次尝试全部通过；档位之间只有尺寸缩放、无几何质变（验证记录见归档）。

| Part2 障碍 | 权重 | 推荐指令 | 最高档 | 4 次尝试通过率 | 得分 |
|---|---|---|---|---|---:|
| high_platform | `comp_bc_v5` | vx=0.5 | 40cm | 4/4 | 200 |
| high_wall | `comp_bc_v5` | vx=0.65 → x=1.6m → 0.35 | 40cm | 3/4 | 200 |
| slope | `comp_bc_v5` | vx=0.3 | 35° | 4/4 | 100 |
| stairs | `comp_bc_v5` | vx=0.75 → x=1.1m → 0.45 | 20cm（完整上+下） | 2/4 | 100 |
| trench | `comp_bc_v5` | vx=0.3 | 20cm（洁净跨越） | 4/4 | 150 |
| plum | 暂无 | — | — | 0/4 | 0 |
| **合计** | | | | | **750** |

未过档位：楼梯 30cm（**盲可训练**，盲侧 850 的天花板只差这一项 +100）、斜坡 45°（**judge 物理摩擦上限不可达**：官方场景 μ=1.0、tan45°=1.0 零余量，2026-10-26 判定，见历史归档 §14.2）、壕沟 30cm、梅花桩（**盲不可达**：trench30 gap > 前后轮触地跨距一半 0.213 m，梅花桩需落足感知；深度依赖相对盲侧增量 350 = trench30 +150、梅花桩 +200）。2026-10-25/26 训练侧审计修复（success 谓词死代码、可刷分奖励、训练地形/物理与 judge 不一致、critic 继承等）与后续计划见交接文档与执行计划；深度部署必须开始做（D0 + rl_sar 渲染/CNN 最小链路）。

复现命令（仓库根目录）：

```bash
# 重新生成官方几何场景
pixi run python @20261024_blackw/scripts/gen_part2_official_levels.py
# 单策略全 20 关评测（按障碍选命令）
pixi run python @20261024_blackw/scripts/eval_blackw_part2.py \
  --policy @20261024_blackw/ws/src/rl_sar_blackw/policy/blackW/comp_bc_v5 --command 0.8 0 0
# 多命令/多策略汇总
pixi run python @20261024_blackw/scripts/summarize_blackw_eval.py --eval 'prep.d/results/.../*.json'
```

无头部署自检（rl_sar + sim_node）：

```bash
pixi run python @20261024_blackw/scripts/check_walk_blackw.py --realtime false --policy comp_bc_v5
```

前进段通过（基座 z 0.517、倾角 1.3°）；转向指令尚未覆盖（BC 数据里 yaw 只在 flat 教师片段出现）。部署契约修复：轮速 `action_scale` 必须是官方镜像符号（FL+10/FR−10/RL+10/RR−10）；`src/rl_sim.cpp` 在每次进 RL 前对 history buffer 做 backfill（与 MjLab/rsl_rl 训练时一致），否则 6 帧历史首帧全 0 会让策略（尤其蒸馏权重）在部署时发散。

## 文档与交接（PPO/BC 线）

| 文档 | 用途 |
|---|---|
| [`@20261019_locomotion/docs/training/part2-ppo-handoff-2026-10-26.md`](../@20261019_locomotion/docs/training/part2-ppo-handoff-2026-10-26.md) | **新会话入口**：课程规则（单谱系逐档 gate、禁止多难度并行）、原明天清单/命令、远程/GPU 队列状态、边界、开放问题 |
| [`@20261019_locomotion/docs/training/part2-ppo-execution-plan-2026-10-26.md`](../@20261019_locomotion/docs/training/part2-ppo-execution-plan-2026-10-26.md) | **当前执行计划（2026-10-26 起）**：修正后的分数账、分阶段排期、task-spooler GPU 队列使用协议、待确认项 |
| [`part2-bc-policy-report.md`](../@20261019_locomotion/docs/training/part2-bc-policy-report.md) | 主报告：judge v5、BC/DAgger、评测结果、参考文献、局限 |
| [`part2-ppo-training-history.md`](../@20261019_locomotion/docs/training/part2-ppo-training-history.md) | 归档：训练侧 bug 审计与修复证据、最低档/档位结构验证、显存实测、早期记录 |
| [`part2-blind-depth-curriculum-plan.md`](../@20261019_locomotion/docs/training/part2-blind-depth-curriculum-plan.md) | 模型分工（主线 M0 + T30/S45/St30/P）、盲课段 B0–B4、深度 BeamDojo 课程 D0–D5 |
| [`part2-failure-vs-reward-design.md`](../@20261019_locomotion/docs/training/part2-failure-vs-reward-design.md) | termination vs reward shaping 原则与文献 |
| `@20261024_blackw/training/README.md` | 训练侧代码快照与远程仓对应关系 |

## 出生点检查

`scripts/check_spawns.py` 用 MuJoCo 对 21 个出生位姿（Part1 + 20 个 Part2 档位）做支撑面射线和初始接触检查：

```bash
pixi run python @20261024_blackw/scripts/check_spawns.py
```

结果：原始 Part2 `judge.start` 的 z 是按点足高度给的，blackW 轮底比点足低约 0.12 m，直接用会全部穿模（最严重 plum 约 -0.186 m）；改用 `part2_levels.json` 的 `spawn` 后 **21/21 初始穿透为 0**，Part1 出生点同步修正为 z=0.676。

Part2 judge v5 口径下，官方三份策略按障碍选命令的基线是 **660/1300**（楼梯只到 10cm 是最大短板），自训 `comp_bc_v5` 为 **750/1300**；评测方法、逐档结果与复现命令见主报告（文档地图见上）。

## 策略运行时切换（已实现）

在 RL 状态下可随时切换三份官方策略，切换时自动重新加载 342 维观测/16 动作策略、清空命令与历史：

| 动作 | 键盘 | 手柄 |
|---|---|---|
| flat 策略 | `2` | `Start + D-pad Left` |
| stair 策略 | `3` | `Start + D-pad Up` |
| obstacle 策略 | `4` | `Start + D-pad Right` |
| comp_bc_v5（自训可部署，**Part2 推荐**） | 启动参数 `policy_name:=comp_bc_v5` | 见上方 Part2 表（judge v5 750/1300 profile） |
| 早期自训权重（对照） | `policy_name:=comp_high600` 或 `comp_lane300` | 旧口径，保留作对照 |

固定动作（**仅 Part1**；Part2 规则只允许 RL，禁止固定动作）：

| 动作 | 键盘 | 手柄 | 说明 |
|---|---|---|---|
| low_bar_drive | `5` | `Back + D-pad Down` | 低姿态差速轮驱过限高杆 |
| bridge_drive | `6` | `Back + D-pad Right` | 固定姿态过木桥 |
| car_drive | `7` | `Back + D-pad Left` | 固定姿态轮驱备用 |

固定动作进入后在 RL 状态下按 `1` / `RB + D-pad Up` 可回到 RL；按 `9`/`B` 趴下、`P` 阻尼。

固定动作覆盖范围（重要）：

- `low_bar_drive`：Part1 **限高杆**；ROS `/joy` 无头测试已过（final y≈-5.62，z≈0.31）。
- `bridge_drive`：Part1 **窄带桥桥面（bridge_bands）**；无头测试已过（final y≈1.07，z≈0.38）。
- `bridge_blocks`（宽木桥）没有专用固定动作；`car_drive` 是备用固定姿态，不是 bridge_blocks 的已验证方案。
- Part1 其余障碍（高墙、T 台阶、斜坡、砂砾、绕杆）仍需 RL/手动；**目前没有整场 Part1 全障碍连通的证据**，现有证据只是两个固定动作各自通过对应障碍。

按键表已避开组合键冲突（策略/固定动作都使用 Start/Back + D-pad，不再用单键 RB/LB/Y）。

（原有 `A/B/X/LB+X/RB+上/RB+Y` 的起身/趴下/阻尼/进 RL/复位没有被占用冲突；切换事件会打印 `[policy] switched to ...`。）

## 运行

```bash
cd /home/bis/BiS.d/Code.d/RoboCon/MyMonoRepo.d

# 0) 编译（本目录已编译过；改过源码后跑一次）
pixi run ros2-build

# 1) GUI 运行（默认 flat 策略，窗口 + 手柄/键盘）
pixi run ros2 launch rl_sar_blackw rl_sim_blackw.launch.py

# 2) 切换策略
pixi run ros2 launch rl_sar_blackw rl_sim_blackw.launch.py policy_name:=obstacle
pixi run ros2 launch rl_sar_blackw rl_sim_blackw.launch.py policy_name:=stair

# 3) Part1 官方障碍场（默认 part:=1，出生点已设在出发区）
pixi run ros2 launch rl_sar_blackw rl_sim_blackw.launch.py part:=1
# 4) Part2 某一档（例：high_platform_10cm / stairs_30cm / plum_1bool ...）
pixi run ros2 launch rl_sar_blackw rl_sim_blackw.launch.py part:=2 part2_level:=high_platform_10cm
# 5) 直接指定场景 + 自定义出生点
pixi run ros2 launch rl_sar_blackw rl_sim_blackw.launch.py \
  scene:=$PWD/@20261024_blackw/ws/src/rl_sar_blackw/scenes/blackW/scene_terrain.xml \
  spawn_x:=3.7 spawn_y:=-9.0 spawn_z:=0.55 spawn_yaw:=0.0

# 6) 无头自检（全速，约 30 s/次）
pixi run python @20261024_blackw/scripts/check_walk_blackw.py --realtime false --policy flat

# 7) 固定动作无头自检（ROS 发布 /joy，相当于代替手柄操作）
pixi run python @20261024_blackw/scripts/check_fixed_actions.py --case lowbar
pixi run python @20261024_blackw/scripts/check_fixed_actions.py --case bridge
pixi run python @20261024_blackw/scripts/check_walk_blackw.py --realtime false --policy obstacle
```

## 按键（与 assignment 的 black 相同；没有改键位）

键盘：`0` 起身、`1` 进 RL、`W/S` 前后、`A/D` 左右、`Q/E` 转向、空格停止、`9` 趴下、`P` 阻尼、`R` 复位、`N` 导航模式。
手柄：`A` 起身、`B` 趴下、`X` 复位、`LB+上` 进 RL、`RB+方向` 策略/行为切换（与 assignment 文档一致）。

> 如果 `pixi run ros2 launch ...` 启动时提示找不到包，确认已执行 `pixi run ros2-build`；本目录 `ws/` 会被仓库根
> `scripts/activate_ros2_workspaces.sh` 自动 source。
