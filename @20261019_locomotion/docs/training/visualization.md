# 训练场景与训练节点视频可视化

> 2026-10-20：训练栈**自带** `play --video` / `train --video`；但默认参数会让视频“没有狗、只有调试标记、rough 看着像平地”。2026-10-21 增加固定命令序列的 `render_policy_commands.py`，用于最终模型/里程碑的可视化闭环诊断。本文记录原因、正确录制方式、图例和每轮训练的手工记录清单。视频暂不入库，有价值的再手动移到同步内容。

## 1. 现有内置代码

- `play <task> --video True --video-length N --video-height H --video-width W --checkpoint-file …`
  - 写入 checkpoint 所在 run 的 `videos/play/rl-video-step-0.mp4`。
- `train <task> --video True --video-length N --video-interval K …`
  - 写入 run 的 `videos/train/rl-video-step-*.mp4`。
- 实现：`mjlab/scripts/play.py`（`VideoRecorder`）+ `mjlab/utils/wrappers/video_recorder.py`（`media.write_video`，mp4），headless 下用 EGL 离屏渲染。

## 2. 为什么默认视频“没有狗、粗糙地面不粗糙”

### 2.1 看不到狗本身

训练仓库的 `src/alldog_mjlab/robots/black/xmls/black.xml` 是**碰撞几何模型**：躯干/腿/足的几何在 **group 3**，没有视觉 mesh（仓库不含 STL）。`ViewerConfig` 默认 `geom_group=(1,1,1,0,0,0)`，只画 group 0–2，**group 3 被隐藏**，所以默认视频里只剩调试标记和地面。

解决：录制时把 group 3 打开，例如 `geom_group=(1,1,1,1,1,1)`；视频里红色的“机器狗”就是碰撞几何，不是模型缺失。

### 2.2 默认相机不跟狗

`ViewerConfig.origin_type` 默认 `AUTO`，离屏渲染里 `AUTO` 等价于**自由相机**（看向世界 `lookat`），不会跟踪 robot；策略一跑，狗就离开画面。解决：设 `origin_type=ASSET_BODY`、`entity_name="robot"`、`body_name="trunk"`。

### 2.3 青色点/箭头/黑点是什么

| 标记 | 来源 | 含义 |
|---|---|---|
| 青色小球/射线 | `terrain_scan` 的 `debug_vis`（GridPattern 17×11=187 rays） | 每条 ray 的地形命中点；青色是默认 `hit_sphere_color=(0,1,1,1)` |
| 品红射线/点 | `foot_height_scan`（每足 4 rays，`debug_vis`） | 足端高度扫描的命中点 |
| 深蓝/深绿箭头 | `UniformVelocityCommand` 的 visualizer | 命令线速度 / 命令角速度（target） |
| 亮蓝/亮绿箭头 | 同上 | 实际线速度 / 实际角速度 |
| 紫色/橙色箭头 | 速度跟踪 reward 的 `debug_vis` | 跟踪误差辅助可视化 |
| 黑色/品红小点 | 足/接触相关 visualizer | 足端位置/接触调试点 |

这些是 mjlab 默认开着的 debug visualization（`velocity_env_cfg.py` 里 `debug_vis=True`），不是模型的一部分。Flat 任务只有速度目标，**没有位置目标点**；目标由蓝/绿速度箭头表示。默认视频把传感器 debug 也画上，所以很乱；干净录制时可以只保留 command 箭头、关掉 sensor debug。

### 2.5 蓝/暗蓝箭头重叠与红色狗

- **重叠原因**：`mjlab/tasks/velocity/mdp/velocity_command.py` 的 `UniformVelocityCommand.debug_vis()` 把 command 线速度（暗蓝）、command 角速度（深绿）、实际线速度（亮蓝）、实际角速度（亮绿）都从同一个 `from` 点、同一个 `z_offset` 画出；颜色不同但几何重叠，视频里只能看到最后一个。`--stagger-arrows true`（wrapper 默认开启）会把四类箭头按高度错开：command linear +0.18 m、command angular +0.26 m、actual linear +0.08 m、actual angular +0.16 m；实现是 monkeypatch `MujocoNativeDebugVisualizer.add_arrow`，不改进训练仓库。
- **狗为什么是红色**：训练模型 `src/alldog_mjlab/robots/black/xmls/black.xml` 的躯干/腿/足碰撞 geom 全部写死 `rgba="0.9373 0.2667 0.2667 1"`（约 `#EF4444` 红），且只存在于 group 3；运行时模型 `@20261005_ros2/models/black_description.xml` 的碰撞 geom 同样带这个 rgba。录视频打开 group 3 后，看到的就是这些红色碰撞几何；不是材质/渲染 bug，不需要改。若要换色，改碰撞 geom 的 `rgba` 或在训练 XML 补 group 1 的视觉 mesh。

### 2.6 可视化代码分布与“大改”可行性

| 层 | 文件 | 作用 |
|---|---|---|
| 训练任务 visualizer | `mjlab/tasks/velocity/mdp/velocity_command.py` | command/actual 四类箭头（本节的 z 重叠就在这里） |
| 训练任务 reward visualizer | `mjlab/tasks/velocity/mdp/rewards.py` | 速度跟踪误差的紫/橙箭头 |
| 传感器 debug | `mjlab/sensor/raycast_sensor.py`、`mjlab/sensor/sensor.py` | 青色 terrain_scan、品红 foot_height 命中点/法线 |
| debug primitive 层 | `mjlab/viewer/debug_visualizer.py`（抽象）、`mjlab/viewer/native/visualizer.py`（MuJoCo scene 实现） | `add_arrow/add_sphere/add_frame` 等底层绘制 |
| 离屏渲染/相机 | `mjlab/viewer/offscreen_renderer.py`、`mjlab/viewer/viewer_config.py` | `geom_group/site_group/origin_type/lookat/distance`、视频帧 |
| 视频封装 | `mjlab/scripts/play.py`、`mjlab/scripts/train.py`、`mjlab/utils/wrappers/video_recorder.py` | `--video`、mp4 写出 |
| 我们的诊断 wrapper | `@20261019_locomotion/scripts/agent_scripts/render_training_video.py` | 不改训练代码的“跟踪相机 + 打开 group 3 + 关 sensor debug + 箭头错开 + 全局图” |
| 训练仓库配置 | `src/alldog_mjlab/tasks/velocity/black/env_cfgs.py` | 哪些 sensor/command 开 `debug_vis`、相机 body |

**可以大改**，有三条路径：
1. **只改 wrapper（已采用）**：monkeypatch 绘制/相机，零训练仓库改动，适合诊断视频。
2. **改训练仓库的 task visualizer**：直接在 `velocity_command.py` 的 `debug_vis()` 给四组箭头不同 `z_offset`；或在 `env_cfgs.py` 调整 `debug_vis`，对 `play/train --video` 全局生效。
3. **改 mjlab 本体（fork/补丁）**：重写 `DebugVisualizer` 的 3D 标注（文字标签、图例、目标点、轨迹、接触热力图）、离屏相机轨迹（飞行动画）、多 env 全局渲染。用户已明确允许大改，但会影响所有训练/评测；建议作为单独 `viz` 分支/补丁，先不碰 baseline。



### 2.4 rough 看起来像平地

`play` 只渲染 **env 0**；rough 的 terrain generator 里 env 0 往往落在 level-0 / flat 的 patch 上（或低难度 patch），rough 的坡/台阶/碎石/离散障碍在地形的其他 patch。`play` 默认相机又是自由相机，所以看起来就是平地。**地形已经生成了**：用 `overview` 模式一次加载 7 个 env 的全局俯瞰图，可以看到 smooth slope、rough slope、离散障碍、stairs 等不同 patch（见 §4）。

## 3. 正确的录制方式：`render_training_video.py`

脚本在 [`../../scripts/agent_scripts/render_training_video.py`](../../scripts/agent_scripts/render_training_video.py)（运行时仓库里的诊断脚本；在训练仓库 venv 下执行，不改训练仓库）：

```bash
# 在训练仓库根目录
cd ~/rc_work/nwwolf_mjlab_training_release
export MUJOCO_GL=egl

# 1) 干净的单机器人跟踪视频（关闭 sensor debug，保留 command 箭头，打开碰撞组）
#    --stagger-arrows true 为默认：四类箭头按高度错开
timeout 80 .venv/bin/python ~/rc_work/render_training_video.py play \
  --task black-flat \
  --checkpoint logs/rsl_rl/black_velocity/2026-10-20_18-12-54_baseline-2000/model_1999.pt \
  --video-length 200 --video-height 480 --video-width 640 \
  --geom-group 1,1,1,1,1,1 --stagger-arrows true

# 2) 全局场景静态图（7 个 env，俯瞰；可看 rough 的多地形 patch 混合）
timeout 80 .venv/bin/python ~/rc_work/render_training_video.py overview \
  --task black-rough --num-envs 7 \
  --out ~/rc_work/videos/overview/black-rough_overview_7.png

# 3) flat 全局场景
timeout 80 .venv/bin/python ~/rc_work/render_training_video.py overview \
  --task black-flat --num-envs 7 \
  --out ~/rc_work/videos/overview/black-flat_overview_7.png
```

说明：

- `play` 模式录制完会继续开 viser（默认 8080），用 `timeout` 包一层；视频在 checkpoint 所在 run 的 `videos/play/`，再复制到 `~/rc_work/videos/`。
- `overview` 模式当前输出静态 PNG（不是飞行动画）；全局相机/初始位置由 `env.scene.env_origins` 均值决定。需要“飞入细节”的视频时，下一步在 wrapper 里按相机轨迹逐帧渲染即可（已有 `_offline_renderer._cam` 接口）。
- 训练过程中自动录像用 `train --video`；会增加 GPU/磁盘开销，按需要开短间隔。

### 3.1 固定命令序列视频：`render_policy_commands.py`（2026-10-21）

内置 `play --video` 的指令是随机的，不能保证覆盖“站立、前进、后退、横移、转向、组合”这些手动模式需求。新脚本在训练仓库 venv 下执行，自己加载 play 环境和 actor，按固定序列设置 `twist` command，逐帧渲染并写 mp4 + JSON：

```bash
cd ~/rc_work/nwwolf_mjlab_training_release
export MUJOCO_GL=egl
.venv/bin/python ~/rc_work/render_policy_commands.py \
  --task black-flat \
  --checkpoint logs/rsl_rl/black_velocity/2026-10-21_11-59-36_flat_ft_mirror01_footclear_500/model_2498.pt \
  --out ~/rc_work/videos/flat_ft_flat_commands_clean.mp4
```

先在一台能访问本仓库的机器上把脚本拷到远程（脚本本身不进训练仓库）：`scp @20261019_locomotion/scripts/agent_scripts/render_policy_commands.py bis-ms7e56.tail4413b4.ts.net:~/rc_work/render_policy_commands.py`。脚本覆盖 `stand → fwd-slow 0.3 → fwd-nominal 0.8 → fwd-fast 1.5 → bwd −0.5 → lat +0.5 → yaw +0.5 → arc-left (0.5,0,0.35) → arc-right (0.5,0,−0.35) → combined (0.8,0.3,0.4)`，每段 2–3 s，50 fps，输出同名 `.json` 记录 checkpoints/段表。相机为 `ASSET_BODY/trunk` 跟踪，关 sensor debug，保留 command 箭头。

**适用范围**：flat、`black-gravel-flat`（固定高度场）、`black-gravel-free`（自由关节碎石）。对自由关节 task 必须用小 batch（脚本固定 1 env，天然满足）；对 4096 envs 训练不要开这个脚本，避免 GPU 争用。

**闭环用法**：每个里程碑和最终候选至少录一次；先看视频再决定是否接受数值指标。数值 gate 通过但视频出现拖腿/抖动/卡边时，不得直接进入下一阶段。

## 4. 已生成样例（远程 `~/rc_work/videos/`，本地 `prep.d/videos/`，暂不入库）

| 文件 | 内容 |
|---|---|
| `flat_clean_model_1999.mp4` | flat 最终策略，跟踪相机、可见红色碰撞几何（旧版，箭头未错开） |
| `flat_clean_model_1999_stagger.mp4` | 同上，四类箭头按高度错开（2026-10-20 新版） |
| `flat_ft_flat_commands_clean.mp4`、`_v2.mp4` | **2026-10-21** flat-ft-2500 命令序列；`_v2` 含 arc-left/right 且箭头已错开 |
| `flat_ft_gravel_fixed_commands.mp4`、`_v2.mp4` | flat-ft-2500 在固定砾石高度场上的命令序列；`_v2` 含 arc-left/right、箭头错开 |
| `gravel_free_ft200_commands.mp4` | 自由关节碎石微调 200 iter 策略；可看石块被推挤/打滑/翻倒 |
| `gravel_free_v2_700_commands.mp4` | 旧稀疏自由布局（已作废）；仅历史对比 |
| `free_dense80_commands.mp4` | 旧 dense80 大石块，历史/木块参考 |
| `flat_ft_composite_zero_shot.mp4` | **最新 composite 自由砂砾**（6 cm 基座 + 120 自由 + 700 静态、3–8 cm）上用 `flat-ft-2500` zero-shot 的命令序列；不是训练后策略 |
| `part1_flat_stand.mp4` | 本地 `run_policy_scene.py` 在 Part 1 出发区的 stand；用于验证本地 policy/judge 链路 |
| `rough_clean_model_3800.mp4` | rough resume `model_3800`，跟踪相机，env0 所在 patch |
| `overview/black-flat_overview_7.png` | 7 env 全局俯瞰，flat |
| `overview/black-rough_overview_7.png` | 7 env 全局俯瞰，能看到 rough 多地形 patch |
| `overview/black-gravel-free_overview.png`、`_v2.png` | 旧自由石块场景全局俯瞰（历史） |
| `overview/black-gravel-free_composite_final_overview.png` | **最新 composite 石床**俯视图：6 cm 基座、700 静态 + 120 自由碎石、3–8 cm |
| `overview/part1_scene_robot_overview.png` | Part 1 工作场景概览（Black 替换 blackW、桥 blocks/bands、T 台阶、限高杆、砂砾坑、绕杆等） |
| `overview/part2_plum_fixed_overview.png` | Part 2 梅花桩修复中心对称后的概览（6 桩 + 两侧平台） |
| `part1_flat_stand.mp4` | 本地策略 runner 在 Part 1 出发区的 stand 视频（`flat-ft-2500`，zero-shot；不是障碍通过） |
| `part2_plum_stand.mp4` | 本地策略 runner 在 Part 2 梅花桩左平台的 stand 视频（zero-shot） |
| `flat_model_100/500/1000/1999.mp4` | 旧版 `play --video` 样例（默认相机/调试标记；保留作对比） |
| `rough_scene_flat_model_1999.mp4` | 旧版 rough 场景样例（同上） |

## 5. 每轮训练的手工记录任务

见 [`training-record-checklist.md`](training-record-checklist.md)；核心是：开跑前记配置/命令/种子/GPU，训练中看 TensorBoard 关键曲线并保留里程碑视频，结束后导出/评测/写 `experiments.md`/归档策略与视频，不在主分支堆原始日志。

## 6. 后续改进

- 已实现箭头高度错开（§2.5）；如需把错开永久化到所有 `play/train --video`，改训练仓库或 mjlab 的 `velocity_command.py`。
- `overview` 增加相机轨迹 → 生成“飞入细节”的视频（当前只有静态全局图）。
- 支持指定 terrain row/col 或 env_idx，让 rough 单机器人视频落在指定的坡/台阶/碎石 patch，而不是 env0 的 level-0 patch。
- 若要干净展示视频，可给训练仓库加一个 **visual-only XML**（复用运行仓库 `@20261005_ros2/models/black_description.xml` 的 mesh）或在训练 XML 里补 group 1 视觉几何；当前先用碰撞几何（红色）保证能看到姿态。
- 视频与原始日志都不入库；只把选中的样例复制到任务 `output/` 或 Release，并在 `experiments.md` 记录来源 checkpoint/命令。
