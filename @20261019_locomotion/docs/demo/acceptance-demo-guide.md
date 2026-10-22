# 验收演示指南（P0，面向最终演示者）

> 这是 2026-11-04 队内赛/验收的演示脚本说明，不是“已经训练完成的竞赛策略”。当前状态是 P0 场地/判定/手动部署/评测闭环。

## 1. 演示前准备

- 在仓库根执行，环境只用根 `pixi.toml`：`pixi run …`。
- 本地演示资产在仓库父目录 `RoboCon/prep.d/`：`videos/`、`results/`；不入库。
- `quadruped_control` 本地 fork：`RoboCon/prep.d/quadruped_control_local`；已用 Pixi 依赖构建。

离线自检（约 10 s）：

```bash
cd RoboCon/MyMonoRepo.d
pixi run python @20261019_locomotion/scripts/agent_scripts/check_md_links.py @20261019_locomotion
pixi run python @20261019_locomotion/scripts/agent_scripts/check_plum_geometry.py
pixi run python @20261019_locomotion/scripts/agent_scripts/check_state_machine.py
pixi run python @20261019_locomotion/scripts/agent_scripts/check_part2_ability_tasks.py
pixi run python @20261019_locomotion/scripts/agent_scripts/part1_event_judge.py
pixi run python @20261019_locomotion/scripts/agent_scripts/audit_deployment.py
```

## 2. 现场顺序（12–15 分钟）

### 2.1 先讲边界（1 分钟）

- Part 1：障碍赛，手动状态机 + 外部 judge；当前是 `flat-ft-2500` 基线，未训练障碍专项策略。
- Part 2：能力测试，只能 RL；已有官方能力场 eval 场景和六类 spec，训练尚未开始。
- P0 目标是“场地/判定/部署/演示链路”，不是竞赛分数。

### 2.2 Part 1 仿真与手动状态机（3–4 分钟）

```bash
cd RoboCon/prep.d/quadruped_control_local
P=../../MyMonoRepo.d/.pixi/envs/default
cmake -S . -B .build-pixi \
  -DQUADRUPED_ENABLE_MUJOCO=ON -DQUADRUPED_ENABLE_TORCH=ON \
  -DQUADRUPED_BUILD_APPS=ON \
  -DQUADRUPED_MUJOCO_SIMULATE_DIR="$PWD/third_party/mujoco_simulate" \
  -DBUILD_TESTING=OFF -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_CXX_COMPILER="$P/x86_64-conda-linux-gnu-c++" \
  -DPNG_LIBRARY="$P/lib/libpng.so" -DPNG_PNG_INCLUDE_DIR="$P/include" \
  -DZLIB_LIBRARY=/usr/lib/x86_64-linux-gnu/libz.so -DZLIB_INCLUDE_DIR=/usr/include
cmake --build .build-pixi --target quadruped_mujoco_sim -j4
LD_PRELOAD=$P/lib/libstdc++.so.6 LD_LIBRARY_PATH=$P/lib \
  .build-pixi/apps/mujoco_sim/quadruped_mujoco_sim \
  --scene ../../MyMonoRepo.d/@20261019_locomotion/assets/terrain/part1/part1_eval_scene.xml
```

按键：

```text
0  GetUp
1  Start/Return RL
F/G/J/B/T/Y/U/N  flat / loose / limit_bar / bridge / stairs / high_wall / slope / slalom
W/S/A/D/Q/E 速度；Space 归零；X 退出
```

讲解：

- 看到 `GetUp → Stand → Running`，说明 Passive/GetUp/RL 已接通；
- 按 `T`/`B` 看 `policy switched`，说明状态选择链路已通；
- 8 个 policy 目前共用 `flat_ft`，只演示接口，不演示专项通过；
- 桥/限高杆不要强行走；当前 zero-shot 是 fail，这是诊断结果。

### 2.3 Part 1 judge + zero-shot 诊断（2 分钟）

```bash
MUJOCO_GL=egl pixi run python @20261019_locomotion/scripts/agent_scripts/run_part1_judged_rollout.py \
  --json ../prep.d/results/part1_zero_shot.json \
  --render-dir ../prep.d/videos/judge_frames_demo
```

展示：

```text
RoboCon/prep.d/videos/part1_judged_zero_shot_contact.png
```

讲解：

- 每个障碍独立起点/命令；judge 在策略回路外；
- 限高杆门柱 x=5.2/6.2，正确通过方向沿 y；错误沿 +x 会撞侧柱；
- bridge blocks/bands 当前 fail/running、tilt 升高；flat 策略没有桥面训练；
- 文本 `part1_zero_shot.json` 中有 base/tilt/judge 状态/原因。

### 2.4 Part 2 能力场/梅花桩（2 分钟）

```bash
# 能力场 stand
MUJOCO_GL=egl pixi run python @20261019_locomotion/scripts/agent_scripts/run_policy_scene.py \
  --scene @20261019_locomotion/assets/terrain/part2/ability_field/part2_ability_field.xml \
  --start 0 0 0.55 0.0 --seconds 2 \
  --render --out ../prep.d/videos/part2_ability_field_stand.mp4

# 梅花桩 stand
MUJOCO_GL=egl pixi run python @20261019_locomotion/scripts/agent_scripts/run_policy_scene.py \
  --scene @20261019_locomotion/assets/terrain/part2/part2_plum_eval_scene.xml \
  --start 0.4 0.4 0.65 0.0 --seconds 2 \
  --render --out ../prep.d/videos/part2_plum_stand.mp4
```

讲解：

- 能力场来自官方 `terrain.zip`，本地包装为 Black + 12 轴；
- 六类 spec 在 `config/part2-ability-tasks.yaml`；
- 梅花桩是自建 XML（PDF 参数），`check_plum_geometry.py` 精确验证；
- 只演示 stand/局部行走，不是能力测试通过。

### 2.5 部署合规（1 分钟）

```bash
pixi run python @20261019_locomotion/scripts/agent_scripts/audit_deployment.py \
  --control-repo ../prep.d/quadruped_control_local
```

讲解：45 维 actor、无禁用传感器；policy effort 20；控制仓库 hip/thigh 23.7、calf 59.25，在 25/60 内；`ok: true` 即 P0 部署合同通过。

## 3. 脚本总表

| 脚本 | 作用 | 输出 |
|---|---|---|
| `run_policy_scene.py` | 本地 45 维策略 stand/walk、箭头视频 | mp4、base/tilt 行 |
| `run_part1_judged_rollout.py` | 八障碍 zero-shot + judge | JSON、contact sheet |
| `part1_judge.py` | 足端/限高杆接触、区域 | JSON/终端 |
| `part1_event_judge.py` | 逐障碍 success/fail 状态机 + 自检 | `synthetic OK` |
| `check_state_machine.py` | 8 状态/限速/runtime policy 校验 | 状态表 |
| `check_plum_geometry.py` | 梅花桩角点/缝隙/中心对称 | `OK: 3+3 cubes...` |
| `check_part2_ability_tasks.py` | 六类 spec 与官方 label 交叉检查 | `categories: 6; ... OK` |
| `audit_deployment.py` | 传感器/力矩/输入输出合规 | `"ok": true` |

## 4. 降级与禁止

- 无显示器：播放 `prep.d/videos/` 预录视频 + JSON。
- GUI 构建失败：只演示本地策略 runner + judge，说明 Pixi 构建已验证过。
- 不要说已经拿到正式分数；当前 Part 1 八项 0 分/待完成，只有诊断分。
- 不要用已废弃的 `part1_heightbar_zero_shot_8s.mp4` 演示正确方向；正确视频是 `part1_heightbar_gate_pass.mp4`。
