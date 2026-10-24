# 主控制栈迁移到 rl_sar（评估与计划，2026-10-24）

> 背景：用户实机试操作后认为**基于 rl_sar 的控制层手感更好**（上个大作业 `@20261007_assignment` 已用同一份 `best.pt` 跑通），要求把手动/演示主栈从 `quadruped_control` 迁到 rl_sar（原计划 P2 保底/参考，提前启动），后续深度相机也基于这条线。
> 本文回答：是否可行、会不会重复造轮子、两侧技术栈差异、要改哪些东西、分几期做、怎么验收。证据全部在本机复现过（2026-10-24）。
> 相关：旧的栈选择记录 [`deployment-stack-comparison.md`](deployment-stack-comparison.md)（本次决策已更新它）、`@20261007_assignment/docs/porting.md`、`@20261005_ros2/docs/ros2-nodes.md`。

## 1. 结论

- **可行，且不重复造轮子**：迁移 = 复用现有 `rl_sar` 控制器包（`@20261007_assignment/ws/src/rl_sar`）+ 仿真节点 `quadruped_ros2`（`@20261005_ros2`），**不重写控制层/仿真后端**；唯一必须新增的是**场景数据适配层**（把本任务 Part1/Part2 的 MJCF 转成 rl_sar 侧能直接加载的副本）和演示启动/文档。
- **改数据不改代码**：两侧机器人模型关节数/顺序/执行器力矩限幅一致（都是 12 个 hinge + 1 freejoint、`<motor>` ±20 N·m、IMU 传感器名 `imu_quat/imu_gyro/imu_acc`）。差异只有两处，都可以由一次性的场景转换脚本处理：① 执行器顺序（本任务 FL/FR/RL/RR vs rl_sar 侧假设的 FL/FR/RR/RL）；② 机器人可视化 geom group（本任务 mjlab 约定 group 3，`quadruped_ros2` 的 viewer 默认只显示 0–2）。
- **已验证**（§4）：rl_sar 栈本机今天仍全绿（`check_walk --realtime false` 7/7、24x 全速）；用本任务机器人模型（flat 瞬态场景）也 7/7；Part1 场景转换副本能进入 `GetUp → RL`（getup 判定通过），GUI 能正常渲染本任务场景与红色机器人。
- **迁移后主栈**：`rl_sar`（控制器）+ `quadruped_ros2/sim_node`（MuJoCo 仿真 + 自建窗口）+ `joy_node`（真实/虚拟手柄或键盘）；评测/judge 仍是本任务的 Python 管线（策略层，不受控制栈影响）。`quadruped_control` 降为备选/参考，不删除。
- **深度相机**：迁到 rl_sar 线后，需在 `sim_node` 里加"深度相机渲染 + 发布"，在 `rl_sim` 里加 CNN 推理与观测拼接；工作量和在 `quadruped_control` 里做相当，但**只做一次**（控制层、状态机、限位、时基都复用），且与"以后上实机"的路径一致（rl_sar 上游有 `rl_real`）。
- **风险**：ROS 2 进程模型/多终端操作比单进程 `quadruped_control` 重；键盘控制要单独占一个终端；`policy switching`（P0 的 8 个具名状态键）rl_sar 侧没有，需要用配置扩展补（本轮不需要，见 §5.W4）。

## 2. 两侧技术栈差异

| 维度 | rl_sar（`@20261007_assignment` + `@20261005_ros2`） | quadruped_control（当前演示栈） |
|---|---|---|
| 架构 | ROS 2 三节点：`joy_node` → `rl_sim`（控制器）→ `sim_node`（仿真）；话题 `mit_command`/`motor_state`/`imu`，500 Hz 仿真反馈 | 单进程 C++（`quadruped_mujoco_sim`）：core + motion runtime + torch policy + MuJoCo backend + 自建窗口；另有未用的三进程 ROS 2 路径 |
| 时基/频率 | **仿真时间驱动**：控制每 5 ms、推理每 20 ms 仿真时间；暂停/慢放/快放不影响策略周期（全速 25x 仍 7/7） | 控制周期固定 5 ms（`control_period_ms`），仿真按 `real_time_factor` 墙钟节流；无"暂停时策略周期"概念 |
| 策略契约 | HIM 270 维（45×6 历史）硬编码在 `himloco/config.yaml`；当前单策略，`config_name` 写死 | 配置化 TorchScript：45/270、history_frames、action scale、默认姿态、关节映射都可配；8 个具名策略位 |
| 状态机 | Passive → GetUp → RL_Locomotion → GetDown，斜坡按仿真时间；`kd_passive`/两段起身/趴下周期可配 | 同状态族 + policy switch/Retry/Event chain（blackW），P0 加了 8 个具名状态键（当前全是占位策略） |
| 输入 | 真实/虚拟手柄（`/joy`）+ 键盘（rl_sim 直接读终端）；`/cmd_vel` 导航模式 | 终端键盘（W/S/A/D/Q/E、Space、F/G/J/B/T/Y/U/N 等）+ 未来手柄/ROS |
| 仿真后端 | `sim_node`：自建 GLFW + mjv/mjr 渲染，**电机非理想模型**（死区/指令延迟/力矩噪声/种子），MIT 五参数由电机模型算力矩，`/sim_reset` 复位 | `MujocoRobotIO` + 官方 Simulate 界面；MIT 指令直接 `data.ctrl`，无电机非理想项；`focus_on_robot` 视角 |
| 策略/观测实现 | `library/core` 逐字复用上游 rl_sar，270 维 obs buffer/历史/推理/动作换算都在控制层，C++ libtorch | 自写 `RlController`：obs/动作/历史/限位，C++ libtorch |
| 安全/限位 | 控制器侧 `command_limit.hpp`（隐含力矩预算 33.5 N·m、q_des 变化率、kp/kd 上限）+ 仿真侧 ±20 N·m | 配置 `max_position_jump`/`action_clip`/`observation_clip`，仿真侧 ±20 N·m |
| 依赖/环境 | 仓库根同一 pixi 环境（RoboStack Humble + mujoco 3.12 + libtorch），ROS 2 话题/launch | 同一 pixi 环境（无 ROS 依赖），CMake + 自有 YAML 配置 |
| 测试 | `check_walk.py` 7 项（时间线脚本发 /joy）、`check_headless.py`、`check_feedback_clock.py`、`input_map_selftest`、`command_limit_selftest`、colcon test | MuJoCo 集成测试、`audit_deployment.py`、若干离线 checker |
| 实机路径 | 上游 `rl_real`（MIT 指令），我们已补限位；最接近比赛真实接口 | 有三进程/真实后端迁移计划，未实施 |
| 维护 | 上游 `fan-ziqi/rl_sar` Apache-2.0，本地 fork 小改；两个仓都是本仓库历史任务产物 | 团队主仓库 + 个人 fork，落后上游 17 commits |

**"手感差异"的来源（推测，供以后确认）**：rl_sar 侧有电机非理想模型（死区/延迟/噪声）、仿真时间驱动的 5 ms/20 ms 节拍、控制器侧指令限位，而 `quadruped_control` 是理想力矩 + 墙钟节拍；另外 `quadruped_control` 的 `obstacle.yaml` 用 kp45/hip±0.05，与作业 `config.yaml`（kp40/hip0）不同。迁移到 rl_sar 后这三项都按已验证的作业配置走。

## 3. 迁移要改什么（不重写现有代码）

| # | 项 | 需要做什么 | 规模 | 状态 |
|---|---|---|---|---|
| W1 | **场景适配** | 写一个纯数据转换脚本：把本任务 Part1/Part2 MJCF 复制成 rl_sar 侧场景副本——执行器顺序改成 FL/FR/RR/RL（适配 `joint_mapping`）、机器人可视化 geom group 3→1（适配 `sim_node` viewer）、被 include 的地形文件用绝对路径 + `texturedir` 保留相对资源；输出到 `prep.d/scenes/`，任务仓库的原始场景一行不改 | 小（已完成，`scripts/agent_scripts/make_rlsar_scene.py`） | ✅ 2026-10-24 |
| W2 | **演示启动/操作** | rl_sar launch 已支持 `scene:=`；写 Part1/Part2 场景的启动命令、键盘/手柄两套操作说明、常见坑（键盘需独立终端、`start:=rest` 需要场景 keyframe 本任务没有所以用 `raw`） | 小（文档+脚本，零代码） | 本轮出文档 |
| W3 | **起跑位姿/课程变体** | Part1 整场演示要从出发区（x≈3.7, y≈-9）起跑：转换脚本加可选 keyframe（把机器人 qpos 摆到出发区、朝向赛道），或生成演示专用场景副本；评测用的 per-obstacle 起点保持由 Python eval 控制，不受影响 | 小（半天） | 待做 |
| W4 | **手动保底的状态/策略扩展** | rl_sar 当前单策略、`config_name` 写死。若以后有按障碍切换策略/限速的需求：把 `config_name` 改成 base.yaml/ROS 参数，加多个 `himloco_*` 配置目录，键盘/手柄加切换键（`input_map.hpp` 一处）；命令限位已有 | 小-中（0.5 天） | 待做（本轮不需要：现在只有 best.pt 一个可用策略） |
| W5 | **深度相机（后续）** | `sim_node`：加深度相机渲染（MuJoCo 3.12 离屏 + 读深度缓冲）→ 发布深度图 topic；`rl_sim`：actor 观测变 45 + CNN latent 64，加载训练仓导出的 CNN+actor TorchScript，观测拼接/归一化与训练侧一致（深度/cutoff 归一、无命中按最远）；配置加相机内参/帧率；验证用训练地形上的 play 对照 | 中（2–3 天，深度渲染 API 有不确定性） | 待做 |
| W6 | **实机路径** | 复用上游 `rl_real` + 我们的 `command_limit`；迁移后与实机的接口语义（MIT 五参数）一致，比继续在 quadruped_control 上补真实后端更顺 | 中 | 待做 |

**"重复造轮子"清单**：

- **不重复**：控制器（rl_sar 现成、已验证）、仿真后端（`sim_node` 现成，含电机非理想模型）、状态机/时基/限位（rl_sar 已实现并测过）、场景资产（复用本任务 MJCF，只做数据转换）、评测/judge（Python 管线不动）、训练仓（完全无关）。
- **会变成"沉没成本"的**：`quadruped_control` 里 P0 自写的 motion runtime/policy adapter/config loader（功能与 rl_sar 重叠）——迁移后它们从主路径降为备选/参考；其 8 个具名状态键的演示能力若以后确需保留，再按 W4 在 rl_sar 侧加，不两套并行维护。
- **避免新增重复**：不 fork rl_sar 到任务目录、不重写 ROS 话题层、不为演示另写一套仿真后端；W1 只做数据转换脚本（可复用、可重复生成）。

## 4. 本机验证证据（2026-10-24）

| 检查 | 结果 | 证据 |
|---|---|---|
| rl_sar 栈自身回归（作业 flat 场景，`check_walk.py --realtime false`） | **7/7 PASS**，全速 24.44x，策略周期均值 21.74 ms（作业侧判据 <30 ms） | 控制台输出（2026-10-24） |
| 本任务机器人模型 + rl_sar（`prep.d/scenes/task_flat_rlsar.xml`，flat 瞬态场景 + 本任务 `black_policy.xml`） | **7/7 PASS**：起身终点误差 4.96e-08 rad、z=0.415/倾角 2.3°、RL 段 z≥0.409/倾角≤7.1°、转向 0.978 rad/s、22.17x 全速 | `prep.d/results/rlsar_migration/check_walk_task_robot_flat.txt` |
| Part1 转换场景（`prep.d/scenes/part1_rlsar.xml`） | 场景成功加载（含全部障碍/7 个传感器）；**起身/站立/RL 不摔全部 PASS**（z=0.417 倾角 1.4°；RL 段 z≥0.398、倾角≤12.8°）；只有"转向"项 FAIL——机器人沿 +x 直行 1.8 m 后撞上桥面块（0.2 m 高）被挡，属场景障碍而非控制失效 | `prep.d/results/rlsar_migration/check_walk_part1_scene.txt` |
| Part1 原始场景 + 把两份 yaml `joint_mapping` 临时改成恒等 | 同样 `GetUp` PASS（反向验证"执行器顺序差异"就是唯一的映射问题；实验后已还原 assignment 配置） | 实验记录 |
| GUI 渲染 | `quadruped_ros2` 窗口加载 Part1 转换场景，地面/砂砾/障碍可见，机器人红色可动部件可见；无需改动 `sim_node`/`viewer` 代码 | `prep.d/videos/rlsar_migration/gui_part1_robot_visible.png`（before/after 各一张） |
| Part2 场景转换 | `part2_plum_eval_scene`、`part2_ability_field`（含 `map.xml` + `labels/*.png` 外部资源）都已生成并通过 MuJoCo 加载自检 | `prep.d/scenes/part2_plum_rlsar.xml`、`part2_ability_rlsar.xml` |

## 5. 建议路线与验收

1. **立刻可用于"试操作对比"（W1+W2，已完成/本轮出文档）**：用转换后的 Part1 场景跑 rl_sar GUI，键盘或手柄操作 best.pt，和 `quadruped_control` 手感对比；两边同一份权重、同一评测口径，只有控制层不同。
2. **演示流程迁移（W3+W4，约 1 天）**：Part1 起跑位姿/整场演示脚本 + 需要的状态切换/限速扩展；更新 `docs/demo/acceptance-demo-guide.md` 为 rl_sar 版本（保留 quadruped_control 备选命令）。
3. **深度相机（W5，2–3 天）**：训练侧先把 depth 策略练到可用（当前 1500-iter 对照进行中）；控制侧并行做 `sim_node` 深度发布 + `rl_sim` CNN 推理，与训练侧同一归一化/无命中规则。
4. **实机（W6）**：比赛前若上真机，走 rl_sar `rl_real` + command_limit；quadruped_control 只作备用。

**验收**：`check_walk` 式时间线在 Part1/Part2 转换场景上通过（起身/行走/转向/趴下、无 NaN/无摔）；Part1 整场手动演示能走完并出 judge 记录（judge 仍是外部 Python）；GUI 画面正常；文档更新 `docs/status.md`、`docs/demo/acceptance-demo-guide.md`、`deployment-stack-comparison.md`。

## 6. 现有可用命令（本轮就能试）

```bash
cd RoboCon/MyMonoRepo.d
# ① 生成 rl_sar 场景副本（一次性；改场景后重跑）
pixi run python @20261019_locomotion/scripts/agent_scripts/make_rlsar_scene.py \
  --scene @20261019_locomotion/assets/terrain/part1/part1_eval_scene.xml \
  --out ../prep.d/scenes/part1_rlsar.xml
# ② 终端 A：仿真窗口（不启动 rl_sim，把键盘留给终端 B）
pixi run ros2 launch rl_sar rl_sim.launch.py \
  scene:=$PWD/../prep.d/scenes/part1_rlsar.xml start:=raw rl:=false joy:=false
# ③ 终端 B：键盘控制（0 起身 / 1 进 RL / W S A D Q E / Space / 9 趴下 / P 阻尼 / R 复位 / N 导航模式）
pixi run ros2 run rl_sar rl_sim
```

手柄路径（真实手柄或 `pixi run python @20261005_ros2/sim_joy/xbox_sim_joy.py` 造的虚拟手柄）：把 ② 改成不带 `rl:=false joy:=false` 的原版 launch 即可（A 起身、RB+十字键上 进 RL、左摇杆走/右摇杆转、B 趴下），见 `@20261007_assignment/README.md`。
