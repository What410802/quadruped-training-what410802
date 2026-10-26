# best.pt 部署到手动演示环境（quadruped_control，2026-10-24）

> 目的：把步骤 2 的 zero-shot 策略（`best.pt`，HIMLoco）接进本机最终演示用的 `quadruped_control` MuJoCo GUI，让用户手动试操作；步骤 3 的深度策略本轮**不部署**（原因见 §6）。
> 前置：zero-shot 评测结论见 [`him-best-zero-shot.md`](best-pt-zero-shot.md)；控制仓库本地 fork 与构建见 [`../reference/deployment-stack-comparison.md`](../40-reference/deployment-stack-comparison.md) 与 [`../demo/acceptance-demo-guide.md`](../00-competition/demo-guide.md)。

## 1. 结论

- **可试操作**：`best.pt` 已经在控制仓库里（`assets/policies/black/obstacle/best.pt`，md5 `7af7bab2cc1cb559000551f2637e0649`，sha256 `a5979a6b…`，与 `@20261007_assignment/ws/src/rl_sar/policy/black/himloco/best.pt` **逐字节相同**，来源 `rl_sar@4abccaa` 的 `himloco_obstacle`），不存在模型搬运/转换风险。
- **只改配置**：控制仓库的 `motion/src/rl_controller.cpp` 本来就支持 `history_frames=[0..5]` + `inference_input_dimension=270` 的 HIM 契约，`configs/policies/black/obstacle.yaml` 就是这份策略的部署配置；新增 `configs/policies/black/policy_switch_best.yaml` 把它放到策略循环首位即可启动即用，默认 `policy_switch.yaml`（8 个 `flat_ft` 占位）保持不动。
- **GUI 已验证**：`GetUp → Running` 正常，`W` 命令生效、机器人行走、`9` 趴下、`x` 退出；观测/动作契约核对与命令行证据见 §4。唯一代码改动是 MuJoCo 窗口显示 geom group 3（否则 Part1 场地里机器人不可见，见 §3.2）。
- **深度策略暂不部署**：控制栈只有 12 关节 MLP 策略路径，没有深度相机/CNN 推理；且 500-iter 对照策略质量还不足以进演示（§6）。

## 2. 契约核对（为什么不用改 C++ RL 路径）

`obstacle.yaml` 的字段与 `rl_controller.cpp` 的实现逐项对上（行号为本控制仓库 worktree）：

| 契约 | 训练/评测侧 | 控制仓库实现 | 结论 |
|---|---|---|---|
| 输入维度 | 270 = 45×6（最新帧在前） | `insert_observation()` 把新帧 memcpy 到 `history_` 起址、旧帧后移（`motion/src/rl_controller.cpp:307-313`）；`inference_input()` 按 `history_frames` 顺序拼接到 270（`:391-404`） | 一致 |
| 单帧布局 | `[cmd*scale(3), gyro*0.25(3), gravity(3), (q-q0)(12), dq*0.05(12), previous_action(12)]` | `:230-282` 同序；观测最后按 `observation_clip=100` 截断（`:284-289`） | 一致 |
| 命令 | `[vx,vy,wz]`，`command_scale [2,2,0.25]`、`limits [3,1,3]` | `obstacle.yaml` 同值；运行 `vx=0.3` 命令被接受 | 一致 |
| 动作 | `default + a*0.25`，`a` 先裁到 `±100`，`previous_action` 用裁剪后的原始输出 | `convert_actions()`：`clamp(action_clip)` → `default + action*action_scale` → 位置限位/`max_position_jump`（`:337-388`）；`previous_actions_` 存裁剪后值（`:361`） | 一致 |
| 关节顺序 | FL/FR/RL/RR × hip/thigh/calf | `configs/robots/black.yaml` 同序，`policy_dof_indices` 恒等 | 一致 |
| PD/限幅 | kp 45 / kd 1.2（`rl_sar` 参考配置） | `obstacle.yaml` 的 kp=45、kd=1.2，力矩上限由 `black.yaml` 的 `max_effort` 约束 | 一致 |

`obstacle.yaml` 与 `@20261007_assignment` 的 `config.yaml` 有两处小差异：kp 45 vs 40、默认 hip 姿态 ±0.05 vs 0；本部署采用控制仓库里与这份权重同源的 `obstacle.yaml`（`rl_sar` 的 `himloco_obstacle/config.yaml`）。若要换成作业配置，只要复制 `obstacle.yaml` 改这两组数并改名加入循环即可，无需改代码。

## 3. 改动清单（控制仓库本地 worktree，未提交）

1. **新增 `configs/policies/black/policy_switch_best.yaml`**：策略循环 `[obstacle, flat_ft, loose_ft, limit_bar_ft, bridge_ft, stairs_ft, high_wall_ft, slope_ft]`，启动即 `obstacle`（=best.pt）；`2` 键切换循环、`F/G/J/B/T/Y` 仍可选占位策略（`N`/slalom 未入循环）。默认 `policy_switch.yaml` 不动。
2. **`apps/mujoco_sim/sim_window.cpp` +7 行**：`Simulate::Load()` 之后把所有 geom group 打开。原因：比赛场地（`part1_eval_scene.xml` 等来自 mjlab 约定）把机器人可视化 geom 放在 **group 3**，而 MuJoCo Simulate 默认只显示 group 0–2，原样跑窗口里只能看到地面和黑色足端碰撞球。
3. 构建产物 `.build-pixi/`（未跟踪，不入库）；改动 diff 存档 `RoboCon/prep.d/diffs/20261024_quadruped_control_demo_best.diff`，新增配置副本在 `RoboCon/prep.d/control_worktree/`。

## 4. 构建与运行（本机实测命令）

控制仓库当前 pixi 环境里没有 `x86_64-conda-linux-gnu-c++`（旧演示指南里的编译器名已失效），用 pixi 的 `c++`（gcc 15.3）+ `Ninja` 构建，并补 pthread/rt/dl 链接项（conda 链接器默认 `--as-needed`，缺了会报 `DSO missing from command line`）：

```bash
cd RoboCon/prep.d/quadruped_control_local
P=$PWD/../../MyMonoRepo.d/.pixi/envs/default
export PATH="$P/bin:$PATH" LD_LIBRARY_PATH="$P/lib"
cmake -S . -B .build-pixi -G Ninja \
  -DQUADRUPED_ENABLE_MUJOCO=ON -DQUADRUPED_ENABLE_TORCH=ON -DQUADRUPED_BUILD_APPS=ON \
  -DQUADRUPED_MUJOCO_SIMULATE_DIR="$PWD/third_party/mujoco_simulate" \
  -DBUILD_TESTING=ON -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_CXX_COMPILER="$P/bin/c++" \
  -DPNG_LIBRARY="$P/lib/libpng.so" -DPNG_PNG_INCLUDE_DIR="$P/include" \
  -DZLIB_LIBRARY=/usr/lib/x86_64-linux-gnu/libz.so -DZLIB_INCLUDE_DIR=/usr/include \
  -DCMAKE_EXE_LINKER_FLAGS="-lpthread -lrt -ldl"
cmake --build .build-pixi -j6
```

试操作（Part1 场地；`--policy-switch-config` 必须是**绝对路径**：

```bash
cd RoboCon/prep.d/quadruped_control_local
P=../../MyMonoRepo.d/.pixi/envs/default
LD_PRELOAD=$P/lib/libstdc++.so.6 LD_LIBRARY_PATH=$P/lib \
  .build-pixi/apps/mujoco_sim/quadruped_mujoco_sim \
  --scene ../../MyMonoRepo.d/@20261019_locomotion/assets/terrain/part1/part1_eval_scene.xml \
  --policy-switch-config "$PWD/configs/policies/black/policy_switch_best.yaml"
```

终端按键（在启动程序的终端里按）：`0` 起立 → `1` 启动 RL（此时跑 best.pt）→ `W/S/A/D/Q/E` 调速度（每按一次 ±0.1 m/s）→ `Space` 速度归零 → `2` 切下一个策略（`flat_ft` 占位，可再切回）→ `9` 趴下 → `r` 重置并重新对准机器人视角 → `k` 暂停/继续 → `x` 退出。
MuJoCo 窗口相机：滚轮缩放、左键拖动旋转、`Ctrl`+右键双击切 tracking camera、`Esc` 回到自由相机；默认取景距离约 1.9 m，走起来后机器人容易出画面，先滚轮拉远一点再走。

## 5. 验证证据（2026-10-24）

| 检查 | 结果 | 证据 |
|---|---|---|
| MuJoCo 集成测试（45/270 全链路，flat HIM 策略） | 全部通过；`RL 闭环：4 秒位移=1.52545 m`、`RL 横移：4 秒侧向位移=3.08816 m` | `LD_PRELOAD=… .build-pixi/tests/mujoco/quadruped_mujoco_tests` |
| GUI 手动链路 | `GetUp` t≈6.0 s → `Running` t≈8.7 s，`vx=0.3` 命令接受/归零正常，退出码 0 | pty 驱动脚本输出（见下） |
| 机器人可见 + 行走 | Part1 场景红色机器人在起点站立、RL 启动后前进（截图 `03_rl_start_win.png`、`04_walk0_win.png`…） | `RoboCon/prep.d/videos/demo_himloco/`（11 张窗口裁图 + `terminal.log`） |
| 策略加载 | 8 个策略配置全部通过启动校验（无 `加载 RL 策略失败`/`策略配置警告`） | GUI 启动日志 |

全部试操作证据（截图 + contact sheet + 终端日志）在 `RoboCon/prep.d/videos/demo_himloco/`；与其余可视化（`best.pt` zero-shot 28 段、blind vs depth 对照）汇总在 `RoboCon/prep.d/videos/review_20261024.html`。

## 6. 深度策略为什么暂不部署

1. **控制栈没有对应输入通道**：`quadruped_control` 的 RL 路径是 `TorchScript(state frame) → 动作`，观测只有 45/270 维本体量；深度策略需要 32×32（或 64×48）深度图 + 冻结/在线 CNN 编码器，控制仓库没有相机传感器、CNN 模块或图像预处理，接进来等于新写一条推理链。
2. **策略本身还不够好**：本轮 blind vs depth 对照只训 500 iter（约 18 min），深度策略是从头训，500 iter 远未收敛；对照结果见 [`../../comp/RUN_LEDGER.md`](../../comp/RUN_LEDGER.md) 与 `prep.d/results/cmp_blind_depth.json`，视频在 `prep.d/videos/cmp/`。按用户条件“效果还可以的话才部署”，本轮不满足。
3. **训练侧下一步才是正路**：深度相机 DR（噪声/丢帧/延迟/外参）与更长训练在 [`camera-depth.md`](../20-part2-shared/camera-depth.md) §6；等深度策略在训练地形上稳定后再评估部署，届时需要先给控制栈加“深度相机输入 + CNN”支持。

## 7. 仍未做 / 风险

- 控制仓库改动未提交（团队仓库，按约定留 worktree）；若要固化，先 `git add configs/policies/black/policy_switch_best.yaml apps/mujoco_sim/sim_window.cpp` 再提交。
- `obstacle` 策略的观测/动作按 `rl_sar` 参考配置（kp45/hip±0.05）跑；与作业 `config.yaml`（kp40/hip0）不同，若手动试操作步态异常，优先换这两组参数对比，见 §2 末。
- 手动试操作是“平地 + 场地起点”验证，不等于障碍通过；Part1 障碍通过率仍以 judge 诊断为准（`best.pt` zero-shot 0/8）。
