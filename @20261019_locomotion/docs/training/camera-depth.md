# 深度相机接入（C2 视觉主线，2026-10-24）

> 背景与决策见 [`../../comp/PLAN_C2_ARCH.md`](../../comp/PLAN_C2_ARCH.md) 的 2026-10-24 更新与 [`../../comp/CONTRACT.md`](../../comp/CONTRACT.md)（允许模拟真实相机/雷达；本队选深度相机、不用雷达；heightmap/足底力等特权量禁止进 actor）。
> 本文记：mjlab 1.6 相机 API 的实测结论、训练仓改动、正确性自检、成本/100-iter 稳定性 smoke 与尚未做的部分。远程训练仓路径：`bis-ms7e56.tail4413b4.ts.net:/home/bis/rc_work/nwwolf_mjlab_training_release`。

## 1. 结论

- mjlab 1.6（mujoco_warp 3.11 / Warp 1.17）原生支持深度相机：`CameraSensorCfg(data_types=("depth",))` + 一个 2-D observation group + rsl_rl `CNNModel`，**不需要 EGL**，渲染与现有 terrain raycast 共用同一个 GPU sense graph。
- 训练仓新增 task **`black-basic-obstacle-depth`**：与 `black-basic-obstacle` 同地形/奖励/终止，actor 输入从 45 维变 **45 proprio + 64 维深度 CNN latent**，critic 保持 259 维特权。blind task 未改动，保留 fallback。
- 深度图正确性：8 env 自检通过（相机高约 0.53 m、下俯 15°，图像下半部地面深度 0.58–0.94 m，与几何一致；上半部天空/远处按 "≥3 m 视为最远" 处理）。
- 成本 smoke（25 iter × 4 配置）+ 100-iter 稳定性 smoke：见 §5（每 iter 走时/显存/吞吐 vs blind task）。

## 2. mjlab 1.6 相机 API（读源码得到的可用结论）

| 事项 | 结论 | 出处（远程 `.venv/lib/python3.12/site-packages/`） |
|---|---|---|
| 配置 | `CameraSensorCfg(name, parent_body, pos, quat, fovy, width, height, data_types=("depth",), use_textures, use_shadows, enabled_geom_groups, clone_data)`；`parent_body` 用带 entity 前缀的名字如 `robot/d435_link` | `mjlab/sensor/camera_sensor.py` |
| 数据 | `sensor.data.depth` 形状 `[num_envs, height, width, 1]` float32；同一 sensor 还可取 `rgb`/`segmentation`，本文只开 depth | 同上 |
| 渲染路径 | `SensorContext` → `mjwarp.create_render_context(...)`；`Simulation.sense()` 把 `refit_bvh + mjwarp.render + raycast` 包进同一个 CUDA graph，每个 env step 调一次 | `mjlab/sensor/sensor_context.py`、`mjlab/sim/sim.py:522` |
| 与 raycast 共用 | 现有 `terrain_scan` / `foot_height_scan` 已是 `requires_sensor_context` sensor，所以相机只是往同一个 context 里加 rendering，没有额外图形上下文 | `mjlab/scene/scene.py:179` |
| 约束 | 一个 scene 里所有 camera 必须共享 `use_textures` / `use_shadows` / `enabled_geom_groups`；相机与 raycast 的 geom group 不一致时取并集并 warn | `mjlab/sensor/sensor_context.py:_validate_sensor_settings` |
| EGL | 不需要。`MUJOCO_GL=egl` 只影响其它渲染路径（录像/查看器），深度走 GPU RenderContext | 实测：无窗口环境训练正常 |
| 深度语义（实测） | 未命中的天空/背景像素返回 **0**；射线逃出地形时可返回几十米；有效地面像素是相机系距离（米）。进 obs 前要统一成 "0/非有限/≥cutoff 视为最远" | `depth_smoke.py` 统计 + 可视化 |
| 观测接入 | 2-D obs group（`concatenate_terms=True`，形状 `(1,H,W)`）；rsl_rl `CNNModel` 按 obs group 自动建 CNN，1-D group 直接拼到 MLP 输入 | `rsl_rl/models/cnn_model.py`、`mjlab/rl/config.py` |
| 网络 | actor `CNNModel`：CNN 输出 latent + 1-D obs → MLP `hidden_dims` → 12 维动作；本配置用 `global_pool="avg"` 得到 64 维 latent，MLP 输入 **109 = 45 + 64** | 同上 |

## 3. 训练仓改动（工作区，未 commit）

| 文件 | 改动 |
|---|---|
| `src/alldog_mjlab/tasks/velocity/black/camera_depth.py`（新增） | `depth_camera_cfg()`（相机传感器）、`camera_depth()`（深度 → `(B,1,H,W)` 归一化 obs）、`add_camera_observations()`（注册 `camera` obs group） |
| `src/alldog_mjlab/tasks/velocity/black/black_config.py` | 新增 `DepthCameraParams`（分辨率/FOV/安装位姿/深度范围/obs 噪声）与 `RunnerParams.depth`（run 名 `basic_obstacle_depth`） |
| `src/alldog_mjlab/tasks/velocity/black/env_cfgs.py` | `black_basic_obstacle_depth_env_cfg(play=False)` = P1 地形 + 相机 sensor + `camera` obs group |
| `src/alldog_mjlab/tasks/velocity/black/rl_cfg.py` | `black_depth_ppo_runner_cfg()`：actor 换 `CNNModel`、`DEPTH_CNN_CFG`、`obs_groups={"actor": ("actor","camera"), "critic": ("critic",)}` |
| `src/alldog_mjlab/tasks/velocity/black/__init__.py` | 注册 `black-basic-obstacle-depth`（train/play 两套 env cfg + depth runner cfg） |
| `scripts/agent_scripts/depth_smoke.py`（新增，调查工具） | 8 env 正确性自检 + 深度图 PGM/NPY 导出 + 步进耗时/显存；`BLACK_DEPTH_WIDTH/HEIGHT` 可临时改分辨率 |

相机安装：`robot/d435_link`（机器人模型自带的前部 RealSense 支架，trunk 前方 x≈0.225 m、z≈+0.028 m），再前移 0.01 m；fovy 70°，**下俯 15°**；深度 0.1–3.0 m；`enabled_geom_groups=(0,)` 只渲染地形/障碍（机器人 geom 是 group 3，不遮挡）。观测噪声：训练时对归一化深度图加 ±0.02 均匀噪声（play 关闭）。

观测归一化（`camera_depth()`）：

```text
d_obs = clamp(clamp(depth, min_depth, cutoff) / cutoff, 0, 1)    # 0.1..3.0 m -> 0.033..1.0
其中 depth 非有限或 <=0（无命中/天空）按 cutoff 处理
```

## 4. 正确性自检（8 env，play 模式）

```bash
cd ~/rc_work/nwwolf_mjlab_training_release
MUJOCO_GL=egl .venv/bin/python scripts/agent_scripts/depth_smoke.py --num-envs 8 --steps 20 --out ~/rc_work/depth_smoke
```

实测（2026-10-24）：

- observation groups：`actor (8,45) / critic (8,259) / camera (8,1,48,64)`，`camera` 的 term 是 `depth`；
- `sensor.data.depth` 形状 `(8,48,64,1)`；
- `camera` obs（归一化后）实测 `min=0.173 / max=1.000 / mean=0.634`：0.173×3 = 0.52 m 对应最近地面像素（相机高 0.53 m），max=1.0 对应天空/≥3 m；
- 原始深度统计：图像下半部 row median 0.58–0.94 m（与相机高 0.53 m、下俯 15° 的几何一致），上半部为 0（天空/无命中，约占 30% 像素），另有 ~11% 像素 >3 m（逃逸射线）；
- 深度图（近亮远暗）的 PGM 目视：地面梯度、远处暗带、上方天空，与“前向下俯相机”一致。

## 5. 成本 smoke（2026-10-24，25 iter/次，远程 5060 Ti 16 GB）

命令（远程训练仓，`scripts` 外的一次性批处理在 `~/rc_work/cost_smoke.sh`）：

```bash
# 每次 25 iter，前 4 iter（CUDA graph 捕获/编译）不计入均值；peak GPU 由 2 s 轮询 nvidia-smi 取
MUJOCO_GL=egl .venv/bin/train <task> --agent.max-iterations 25 --agent.save-interval 1000 \
    --agent.run-name cost_<case> --agent.logger tensorboard --env.scene.num-envs <N>
```

| case | 分辨率 | envs | 平均 iter | 峰值显存 | 相对 blind |
|---|---|---:|---:|---:|---:|
| blind（`black-basic-obstacle`） | — | 1024 | **1.39 s** | 2.0 GB | 1.00× |
| depth | 32×32 | 1024 | **2.12 s** | 4.3 GB | 1.53× |
| depth | 64×48 | 1024 | **3.53 s** | 11.1 GB | 2.54× |
| depth | 64×48 | 2048 | **6.22 s** | 14.8 GB | 4.47× |
| blind | — | 4096 | 2.84 s（同日 `fixed2` run） | 6.7 GB | 2.04× |

结论/建议：

- **分辨率主导成本**：1024 envs 下，32×32 比 blind 多 0.7 s/iter，64×48 多 2.1 s/iter；显存从 2.0 GB 分别涨到 4.3 / 11.1 GB。
- **64×48 @2048 接近 16 GB 上限（14.8 GB）**：不是安全的长跑配置（其它分配/保存会挤爆）；长跑建议 **32×32 @2048**（按 1024 的 4.3 GB 估 ~7–8 GB）或 **64×48 @1024**。
- **1000 iter 估算**（不含启动；启动约 1.5–2 min）：blind@1024 ≈ 23 min；depth32@1024 ≈ 35 min；depth64@1024 ≈ 59 min；depth64@2048 ≈ 1 h 44 min。→ 第一轮 blind vs depth 对照（500–1000 iter）在 32×32@1024 或 64×48@1024 上完全可行。
- 四次 cost run 均无 CUDA 错误、无 NaN、`Metrics/twist` 正常；25 iter 只是成本量级，不是学习效果证据。
- 日志：`~/rc_work/logs/cost_*.log`、汇总 `~/rc_work/logs/cost_smoke_summary.txt`（不入库）。

### 5.1 100-iter 训练稳定性 smoke（32×32 @1024 envs，从零）

按 handoff 的验收口径跑满 100 iteration（`--agent.max-iterations 100`，run `depth_100iter_smoke_20261024`）：

| 检查 | 结果 |
|---|---|
| 完成 iteration | **100/100** |
| CUDA 错误 / NaN | 0 / 0 |
| 每 iter 耗时 | mean **2.11 s**，max 3.47 s（首 iter 编译/capture） |
| observation shape | actor `(1024,45)`、critic `(1024,259)`、camera `(1024,1,32,32)`（同 run 日志） |
| 学习信号（从零 100 iter，不是效果结论） | `Mean value loss` 0.011；`Mean action std` 1.00→0.45；`Mean episode length` ~10→180 step（随机策略在学站/走） |

→ 相机 sensor + obs 管线 + CNN actor + PPO 全链路在 100 iter 上无崩溃；下一轮才做 blind vs depth 的对照（500–1000 iter）。

## 6. 尚未做（按优先级）

1. ~~**blind vs depth 课程对照**~~：已完成 500-iter 对照（见 §7）；结论是深度侧各项指标更好但成本 ×1.5，是否加长训练/上相机 DR 待用户确认。
2. **相机 DR**：深度噪声（已加 obs 噪声，未做渲染级噪声）、丢帧/延迟 0–2 帧、外参扰动、FOV/分辨率变化、遮挡；策略 50 Hz vs 相机 20–30 Hz 的帧保持策略。
3. **局部高度图方案 A**（备选）：如果 CNN 成本过高或学不动，改为 depth → body 系局部高度图（17×11 或 32×32）→ MLP，需要地面/平面估计或按基座系高度定义，且要和"禁止 heightmap 传感器"规则区分（这是相机算出来的，不是特权 sensor）。
4. **部署契约**：actor 输入 45 → 109（45 proprio + 64 latent），`rl_sar` 需要深度相机推理 wrapper（含同样的归一化/无命中处理）；在对照实验前不冻结、不导 ONNX。
5. **teacher-student**：现有 critic 259 特权（height_scan）已经可以当 teacher；是否做 privilege distillation 由对照结果决定。

## 7. blind vs depth 500-iter 课程对照（2026-10-24）

目的：回答"深度相机这条线目前值不值得继续"，不是判断最终质量。两个 run 除 actor 观测外完全同配置：从零训练、同 seed/地形/奖励/envs(1024)/iters(500)，远程 5060 Ti 16 GB。

| run | actor 观测 | 时长 | mean iter | Mean reward | Mean episode length | terrain level mean | illegal_contact | error_vel_xy | track_linear_velocity |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| `cmp_blind_500` | 45 维本体 | 10:35 | 1.271 s | 7.02 | 708.7 | 0.741 | 0.980 | 0.515 | 0.441 |
| `cmp_depth_500` | 45 本体 + 32×32 深度 CNN latent | 16:17 | 1.956 s | **9.77** | **842.9** | **1.010** | **0.539** | **0.479** | **0.605** |
| 差值 | — | +54% | +0.63 s | +2.75 | +134 steps | +0.27 | −45% | −0.036 | +37% |

- 两 run 全程无 CUDA/NaN/`bad_sim_state` 触发（500/500 iter，`max_abs_bad_sim_state=0`）。
- 指标取自训练日志末次迭代（`Learning iteration 499/500`）；曲线/CSV/JSON：`prep.d/results/cmp_blind_depth_metrics.csv`、`prep.d/results/cmp_blind_depth.json`，曲线图与视频见复核页 `prep.d/videos/review_20261024.html`。
- rollout 视频（play env、常速 vx=0.5 m/s、10 s；两边都跑满 500 步未摔倒）：`prep.d/videos/cmp/cmp_blind_500.mp4`、`cmp_depth_500.mp4`（后者左 RGB + 右深度面板，深度面板近亮远暗、天空黑，与 §4 自检一致）。注意 play env 起点是平地，这两段只用于确认"策略在动、深度面板正常"，不代表障碍能力。
- 解读（谨慎）：**500 iter 的早期阶段深度侧各项质量指标全面更好**（reward/episode 长度/地形课程推进/非法接触/速度跟踪），代价是每 iter 1.5×（显存见 §5：1024 envs depth32 约 4.3 GB，仍可 2048 envs）。这支持"继续深度相机线"，但 500 iter 远未到质量 gate：均值 episode 843 步（上限 1000）说明还会摔，训练 reward 也不能当通过率；结论需更长训练 + Part1/Part2 judge 才能下。
- 单 seed、只跑一次：若要把这作为选型依据，按协议至少要 3 seed 或更长预算；本轮只作为"是否继续"的信号。

### 7.1 续训到 1500 iter（2026-10-24，500 的 checkpoint 各续 1000 iter）

两 run 从各自的 `model_499.pt` 续训 +1000 iter（同 seed/地形/奖励/1024 envs；depth 30:59、blind 19:47），结果：

| run（总 1500 iter） | Mean reward | episode 长度 | terrain level mean | illegal_contact | error_vel_xy | track_lin_vel | iter 成本 | 总时长 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| blind | 11.18 | 801.0 | 1.343 | 0.622 | 0.492 | 0.586 | 1.198 s | 30.0 min |
| depth | 12.31 | 826.4 | 1.460 | 0.522 | 0.449 | 0.622 | 1.875 s | 46.9 min |
| depth − blind | +1.13 | +25.3 | +0.117 | −0.101 | −0.043 | +0.036 | ×1.56 | +56% |

- 两 run 均 1000/1000 干净（exit=0、`Warp CUDA error` 0、`bad_sim_state` 0）。
- **关键观察：depth 在 500 iter 时的明显优势到 1500 iter 大幅缩小**。500 iter 时 depth 领先 reward +2.75、episode +134、terrain +0.27、illegal −0.44；续训后 blind 追赶很快（reward 7.02→11.18、terrain 0.74→1.34、illegal 0.98→0.62），1500 iter 时差距只剩 reward +1.13（+10%）、episode +25（+3%）、terrain +0.117（+9%）、illegal −0.10（−16%），而 depth 成本是 ×1.56。中途 750–1100 iter 段 depth 因地形等级升得更快出现过 episode 长度回撤（地形变难），两条曲线都还在爬升、噪声大。
- 轨迹表（总 iter: blind/depth 的 episode 长度）：500: 709/843；600: 858/909；750: 858/717；900: 800/749；1000: 774/800；1250: 748/849；1400: 797/847；1500: 801/826。
- rollout 视频：`prep.d/videos/cmp/cmp_blind_1500.mp4`、`cmp_depth_1500.mp4`（10 s 常速，均跑满 500 步未摔）；曲线/表格在 `prep.d/videos/review_20261024.html`。

## 10. 从对照得到的 depth 改进启示（2026-10-24）

1. **depth 的价值目前集中在"早期学得快 + 更少非法接触/地形推进更快"**，而不是速度跟踪（error_vel_xy 两边都 ~0.45–0.49）；到 1500 iter 差距缩小到几个百分点——**在 16 GB / 按时限算的预算下，blind 的算力效率明显更高**。比赛如果只选一条线，blind 目前是更稳的默认。
2. **要证明 depth 值得 ×1.56 成本，需要更长预算或消融**：先把 depth 跑到 3000–5000 iter 看差距是否重新拉大（若收敛到同一水平，说明 depth 只是加速早期课程）；同时用同一预算跑 blind 对照。3k+ iter depth 约 1.5 h/次（32×32、1024 envs），可接受。
3. **优先做的 depth 改进实验（按性价比）**：
   - **分辨率 64×48 vs 32×32**：对照用的是 32×32（省成本）；64×48 每 iter 约 ×1.7（成本 smoke 3.53 vs 2.12 s），先小预算 A/B（如各 300–500 iter + 同一 checkpoint 续训对比）判断细节是否值回成本。
   - **latent/结构**：当前全局 avg pool 把空间压成 64 维，楼梯/窄障碍的"位置/高度"信息可能丢失；可试更大 latent（128）或保留 2D 特征（flatten 前几层）的小改动，单独开关对照。
   - **训练信号**：depth 侧目前 critic 仍是 259 特权（height_scan），actor 只有深度；若 actor 学得慢，可试 depth + 少量本体历史（已有 45 维）之外的辅助任务/蒸馏，而非加特权量。
   - **DR**：放在"地形课程稳定后"（见 §9），作为 fine-tune 阶段单开关加。
4. **不要现在把 depth 推到部署**：控制栈深度推理（`sim_node` 深度发布 + `rl_sim` CNN）还没做；先把训练侧跑到能明确回答"是否比 blind 强、强多少"，再投入部署工作量。

## 8. 相机观测怎么进网络：降维、是否冻结、为什么不直接输入图像

当前（`black-basic-obstacle-depth`，2026-10-24 快照）的完整链路，全部在训练仓里可查：

```text
MuJoCo 深度相机 (64x48 fovy70 下俯15°, 0.1-3.0 m, 只看 geom group 0 的地形/障碍)
  → mujoco_warp RenderContext 渲深度 (B,H,W,1) float32
  → camera_depth(): 非有限/≤0(天空/逃逸) 记为 cutoff; clamp [0.1, 3.0]; 除以 cutoff 归一 → (B,1,H,W) ∈ [0,1]
  → 训练时叠加 UniformNoise ±0.02（play/部署关闭）
  → obs group "camera"
  → rsl_rl CNNModel 的 actor CNN: Conv(1→16,k5,s2)+ELU → Conv(16→32,k3,s2)+ELU → Conv(32→64,k3,s2)+ELU
    → AdaptiveAvgPool2d(1,1) → Flatten → **64 维 latent**
  → 与 45 维本体 obs 直接拼接 = **109 维** → MLP (512, 256, 128, ELU) → 12 维动作分布
```

- **"中间降维"用的就是这 3 层卷积 + 全局平均池化**：不管输入是 64×48 还是对照实验里的 32×32，全局 avg pool 后都是 **64 维**（通道数）；concat 顺序是"1-D 组在前、CNN latent 在后"（`rsl_rl/models/cnn_model.py:112-119`）。输入 32×32 时空间尺寸 32→16→8→4，64×48 时 64×48→32×24→16×12→8×6，池化后同样 64。卷积权重 Kaiming 初始化（`rsl_rl/modules/cnn.py:init_weights`）。
- **是否冻结：不冻结，也没有预训练**。actor 和 critic 各自独立：只有 actor 有这份 CNN（相机组只映射给 actor），critic 仍是 259 维特权 MLP（并行归一化）；PPO 的梯度从动作分布一路回传到卷积核，CNN 与后面 MLP 一起**从随机初始化端到端训练**。代码里没有 `requires_grad=False`、没有单独的学习率/优化器、没有 EM 或自编码预训练。**"冻结"的只有输入规则**：深度归一化常数（0.1 m / 3.0 m）、相机内外参、`enabled_geom_groups=(0,)`——这些是契约，不是可学习参数。
- **为什么不直接把相机观测喂给网络**（四个原因，按重要性）：
  1. **维度/样本效率**：64×48 展平是 3072 维（32×32 也 1024），若直接接 MLP，第一层就是 3072×512 ≈ 157 万参数；现有 CNN 三层的参数约 2.3 万，且卷积的局部权值共享天然适合"地面/障碍边缘"这种局部几何。从零训练的样本效率差一个量级。
  2. **rsl_rl 的 actor 只吃 1-D 向量**：2-D 观测必须经过 `CNNModel` 的 encoder 变成 1-D latent 才能与 45 维本体 obs 拼接；把图像硬展平当然也能跑，但会毁掉空间结构、训练更慢（本任务没走这条）。
  3. **信息冗余**：深度图里大片平滑地面/天空是冗余的，压缩到 64 维后 MLP 只处理"与本体量相关的低维特征"，更省算力也更容易和本体观测融合；对照实验（§7）里 500 iter 的 depth 侧已全面优于 blind，说明这条降维路径是学得动的。
  4. **部署代价**：以后上控制栈/实机，推理链是"深度预处理 + 一个小 CNN + MLP"；64 维 latent 让控制侧的推理/传输量都很小，而逐像素大网络不适合 50 Hz 控制回路。
- 不用 heightmap/足底力等特权量是规则要求（`../../comp/CONTRACT.md`）；深度相机是"模拟真实传感器"的允许路径，网络自己从距离图里学地形表示，所以这里没有把相机数据替换成 heightmap。

## 9. 深度相机 DR 与地形课程：先哪个？

**结论：先继续比赛地形课程训练，DR 放到第二阶段做 fine-tune。** 理由：

1. **归因**：现在 depth 策略才 1500 iter 量级、还在摔（§7），此时叠加相机 DR（噪声/丢帧/延迟/外参）会让"学不会"无法区分是地形难还是 DR 太强，也会拖慢早期学习。
2. **DR 还没实现**：目前只有 obs 的 ±0.02 噪声，渲染级噪声、丢帧/延迟、外参扰动、分辨率变化都还没有代码（实现+验证约 1 天），先把更值钱的地形/课程跑出来。
3. **标准顺序**：nominal 任务学会 → 从强 checkpoint 续训做 DR fine-tune（降低学习率/单开关）来换泛化与实机鲁棒；DR 不是"从零学走路"的加速手段。
4. **上 DR 的判据**：episode 长度接近上限（1000 步）、非平凡地形下不频繁终止、Part1/Part2 迁移评测有可见进展；然后按单开关顺序加：深度渲染噪声/量化 → 丢帧/延迟 1–2 帧 → 外参扰动（±2–3°、±1–2 cm）→ 分辨率/FOV 变化 → 遮挡；每项单独对照并记录（延续 `comp` 的单开关协议）。
5. **并行对照**：blind 侧继续用同样预算跑，作为"深度到底贡献多少"的参照；等两边都进入稳定期，再决定是否值得把 DR 同时加到两条线，或只对 depth 线做。

## 11. 3000-iter depth 长训：包含什么（2026-10-24 启动）

目的：1500 iter 时 depth 相对 blind 的优势缩小到几个百分点（§7.1），需要更长预算判断这是"收敛到同一水平"还是"临时波动"。**只加训练预算、不加任何新机制**（单变量）。

| 项 | 内容 |
|---|---|
| 训练臂 | `cmp_depth_3000_cont`：`black-basic-obstacle-depth`，从 `cmp_depth_1500_cont/model_1498.pt` resume **+1500 iter**（总 3000）<br>`cmp_blind_3000_cont`：`black-basic-obstacle`，从 `cmp_blind_1500_cont/model_1498.pt` resume **+1500 iter**（总 3000，同预算对照） |
| 固定不变 | 同 seed=42、同 terrain generator（flat / smooth slope / stairs）、同奖励/终止/command curriculum、1024 envs、32×32 深度、obs 噪声 ±0.02、save-interval 100 |
| 唯一变量 | actor 观测：45 维本体（blind） vs 45 + 64 维深度 CNN latent（depth） |
| 预计成本 | depth ≈1500×1.88 s ≈47 min；blind ≈1500×1.20 s ≈30 min；合计约 80 min + 2 段 rollout 渲染（远程 5060 Ti） |
| 产物 | 两臂末次指标（reward / episode 长度 / terrain level / illegal_contact / error_vel_xy / track_lin_vel）、0→3000 iter 曲线、10 s ×2 段 rollout 视频（`prep.d/videos/cmp/cmp_{blind,depth}_3000.mp4`）、`prep.d/results/cmp_blind_depth_3000.json`、review 页面更新、`comp/RUN_LEDGER.md` 两行 |
| 判据 | 若 depth 在地形等级/非法接触等指标上把领先重新拉大（比如 ≥15% 且曲线持续分开）→ depth 值得继续投（warm-start/分辨率/DR）；若收敛到同水平或差距继续缩小 → **blind 作为比赛主线的默认**，depth 转向 warm-start/蒸馏/鲁棒性小实验而非堆预算 |
| 不包含（下一步） | warm-start 臂（§12）、64×48 vs 32×32 分辨率、latent/结构消融、相机 DR（§9）、Part1/Part2 judge 迁移评测（需先做控制栈深度推理）、多 seed |

注意：rsl_rl 的 resume 不恢复 RNG 状态（迭代计数与权重恢复），两个臂同语义，不影响单变量比较；仍是单 seed，结论按"信号"看，不当最终选型。

**2026-10-24 启动状态**：两臂已于 13:51:45 启动（depth 先跑、blind 后跑），预计约 80 min 训练 + 视频渲染；结束后自动复位 GPU flag。之后排队跑 §12 的 warm-start 臂（`cmp_depth_warm_1500`：同一 blind 1500 checkpoint 初始化、+1500 iter、单开关）。
**定位修订（2026-10-24）**：本组 1500/3000/warm-start 实验只作**简单地形筛选**（flat/slope/stairs 覆盖不到绕柱/桥/限高杆/高墙等结构障碍，无法裁决全场能力）；最终 blind vs depth 的裁决改为在竞争地形代理 + mirror 对称约束 + 真实 judge 下做，见 [`competition-terrain-and-symmetry-plan.md`](competition-terrain-and-symmetry-plan.md)。

## 12. depth 策略要不要用预训练/已有权重？（可行性，2026-10-24 评估）

**现状：当前 depth 策略是从头训的**（随机初始化，没有加载任何预训练权重）：500 iter 从零 → resume 到 1500 → 正在 resume 到 3000。这是为保证 blind vs depth 的单变量对照（唯一差异是 actor 观测），也是文献里的标准做法（egocentric depth + proprio 端到端 RL 从零训练即可，见 Agarwal et al., CoRL 2022；Zhuang et al., Robot Parkour Learning, CoRL 2023）。

**可行路线（按性价比排序）**：

1. **✅ 推荐：从本仓的 blind PPO checkpoint warm-start（成本最低、最可控）**。已核对 checkpoint 结构（2026-10-24，`cmp_blind_1500_cont/model_1498.pt` vs `cmp_depth_1500_cont/model_1498.pt`）：
   - blind actor：`mlp.0.weight (512, 45)`、`mlp.2 (256,512)`、`mlp.4 (128,256)`、`mlp.6 (12,128)`、`distribution.std_param (12)`；
   - depth actor：`mlp.0.weight (512, 109)`，其余 MLP 层 shape 完全一致，多出 `cnns.camera.{0,2,4}` 三组卷积权重（16/32/64 通道）。
   - 做法与仓库里**已有的 PPO→HIM warm start**（`alldog_mjlab/algorithms/him/warm_start.py`，注释明确写 "first Linear: W_him[:, :current_frame_dim] = W_ppo；W_him[:, current_frame_dim:] = 0；b_him = b_ppo；后续 Linear 逐 shape 严格复制"）完全同构：depth actor 第一层**前 45 列 = blind 权重、后 64 列（CNN latent）= 0**，bias/其余层/std 复制，CNN 保持随机初始化。由于 CNN 输出的列为 0，**初始策略严格等于 blind 策略**；随后 PPO 微调让 CNN 那 64 列从零长起来——即"先会走，再学会看"。
   - **已实现并 smoke 通过（2026-10-24）**：训练仓新增 `src/alldog_mjlab/algorithms/depth_warm_start.py`，`BlackVelocityOnPolicyRunner` 增加环境变量入口 `BLACK_DEPTH_WARM_START=<blind checkpoint 绝对路径>`（初始化语义，不允许与 `--agent.resume` 同时使用；同时把 checkpoint 的 command-curriculum `vx range` 按 range 模式恢复，避免 warm-start 跑从初始 ±1 开始而 blind@3000 已到 ±2 的不公平）。
   - smoke（32 envs、32×32、2 iter）实测日志：`actor_input 45->109 (copied 45 columns, zeroed 64 CNN-latent columns), actor keys copied 9, critic keys copied 12, CNN keys kept at init 6. optimizer / iteration / env state are NOT inherited.` → 2/2 iter 无报错，warm start 生效。
   - 排队臂：3000 基线结束后自动跑 `cmp_depth_warm_1500`（从 blind 1500 checkpoint +1500 iter、1024 envs、32×32），并渲染 10 s 深度面板视频；对照口径 = blind@3000 / depth-scratch@3000 / depth-warm@3000（同样 +1500 追加预算）。
2. **best.pt（HIMLoco，270 维 6 帧）**：不能直接加载——不同算法/框架（legged_gym → rsl_rl PPO）、不同观测契约（270 历史 vs 109 单帧；best.pt 本身就是 blind，看不到地形）；要用只能做**行为克隆/蒸馏**（先用 270 历史观测 teacher 生成动作标签，再训 depth student），中等工作量，而 best.pt 的 zero-shot 能力有限（Part1 0/8、平地 0.36 m/s），收益不确定。优先级低。
3. **其他开放权重四足策略**：基本都是不同机器人/关节/观测/动作契约（Unitree/MIT 等），只能蒸馏或 retarget，工作量大、无直接可复用性；本仓真正"契约兼容"的预训练池就是 mjlab black PPO actors（flat_ft、p1、以及本次 blind 两臂）——所以 warm-start 首选它们，而不是外部权重。
4. **论文方法论（可行、仓库已具备大半条件）**：
   - **teacher-student / 特权信息蒸馏**：本仓 critic 已经有 259 维特权观测（72 本体 + 187 height scan）、terrain/command curriculum 也齐；可以训一个"带 height scan 的 sighted teacher actor"，再蒸馏成 depth student（DAgger/KL 或动作 MSE + PPO 微调）。参考 Miki et al., *Science Robotics* 2022（perceptive locomotion 的 teacher-student 路线）。
   - **辅助自监督/跨模态目标**：用 depth 预测局部高度图/teacher latent（或 terrain 类别），作为 aux loss 帮 CNN 更快学到地形特征；或用 contrastive/自编码预训练 depth encoder 再冻结/微调。
   - **感知课程 + DR**：先平地/简单地形、再难地形，后期加深度噪声/丢帧/延迟/外参（§9 的 DR 顺序）——文献里视感知鲁棒性为 second stage（Miki 2022、Agarwal 2022 均用课程化感知设置）。
   - 这些方法都**不需要改机器人/控制栈**，只动训练仓；优先级在 warm-start 之后、按需引入，避免一次引入多个变量。
5. **为什么仍建议保留"从头训"的结论**：从头训是干净的基线；warm-start/蒸馏是"加速/更强的初始化"，必须用同预算对照证明其增益（单开关协议），不能只看最终分数。

**推荐执行顺序**：3000 基线（进行中）→ warm-start 臂（1500 iter，从 blind 1500 checkpoint 初始化，CNN 零列）→ 分辨率 64×48 A/B → teacher-student 蒸馏（若前述仍不够）→ DR fine-tune（最后）。

### 11.1 简单地形筛选结果（3000 iter + warm-start，2026-10-24 完成；只作筛选）

两臂从 1500 checkpoint 各再 +1500 iter（blind 14:37:53→15:07:08、depth 13:51:45→14:37:53；均 exit=0、无 CUDA/NaN），随后排队 warm-start 臂（从 blind@1500 初始化、+1500 iter，15:07:44→15:54:08）。最终同口径（1024 envs、32×32、同 seed）下的末次指标：

| run | Mean reward | episode 长度 | terrain level | illegal_contact | error_vel_xy | track_lin_vel | iter 成本 |
|---|---:|---:|---:|---:|---:|---:|---:|
| blind@1500 | 11.18 | 801.0 | 1.343 | 0.622 | 0.492 | 0.586 | 1.20 s |
| depth@1500 | 12.31 | 826.4 | 1.460 | 0.522 | 0.449 | 0.622 | 1.88 s |
| blind@3000 | 13.15 | 851.3 | 1.431 | 0.480 | 0.460 | 0.655 | 1.15 s |
| depth@3000 | 14.86 | 910.3 | 1.546 | 0.314 | 0.437 | 0.735 | 1.82 s |
| depth-warm@3000等效 | 12.83 | 846.3 | 1.520 | 0.543 | 0.459 | 0.601 | 1.83 s |

- depth 对 blind 的领先在 3000 iter 仍在（reward +1.71、episode +7%、terrain +8%、illegal −35%），幅度不大；成本 ×1.59。
- **warm-start（blind@1500→depth）只到 blind@3000 水平、低于 depth-from-scratch**：在简单地形上"从 blind 初始化"没有带来额外收益（可能是盲走局部最优 + CNN 列从零学习慢）；正式竞争地形批次里 warm-start 与 from-scratch 都要做对照，不能预设 warm-start 更好。
- 这些结果**只作简单地形筛选/成本曲线**，不作最终裁决；决策口径见 [`competition-terrain-and-symmetry-plan.md`](competition-terrain-and-symmetry-plan.md)。
- 视频：`prep.d/videos/cmp/cmp_{blind,depth}_3000.mp4`、`cmp_depth_warm_1500.mp4`；表格 JSON `prep.d/results/screening_simple_terrain_3000.json`；复核页 `prep.d/videos/review_20261024.html` §2.3。
