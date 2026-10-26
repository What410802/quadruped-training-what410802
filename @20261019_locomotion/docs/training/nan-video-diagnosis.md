# HIM platform NaN 崩溃录像与诊断

> 2026-10-25。按要求先不修复，只录制 NanGuard dump 回放和文本诊断。录像位于 `prep.d/videos/nan_debug/`。

## 1. 事故概览

| run | envs | 崩溃 iter | NanGuard env | detection step | 录像 |
|---|---:|---:|---:|---:|---|
| `blackw_him_platform_1024_pilot_v0` | 1024 | 12/300 | 339 | 3399 | `nan_1024env_env339.mp4` |
| `blackw_him_platform_512_pilot_v0` | 512 | 14/300 | 298 | 3960 | `nan_512env_env298.mp4` |
| `blackw_him_platform_256_pilot_v0` | 256 | 22/300 | 15 | 5965 | `nan_256env_env15.mp4` |
| `blackw_him_platform_128_pilot_v0` | 128 | 225/300 | 103 | 58065 | `nan_128env_env103.mp4` |

每个 dump 都是 NanGuard 在检测到 NaN 前保存的 **100 个 finite state**；视频为最后 100 帧逐帧回放，最后一帧标注 `LAST FINITE SAMPLE (NaN next step)`。视频不是完整训练实时录屏，而是从 NanGuard state dump 还原的最近 100 个物理状态。

## 2. 录像里看到的物理瞬间

四个规模下的最后一帧都停在同一种姿态附近：

- 机器人已经到高台边缘；
- 前轮接近/压在 10 cm 平台顶面，后轮仍在地面附近；
- 128 env 的最后一帧 root 速度最大：约 `vx=1.0 m/s, vy=-0.49 m/s, vz=-0.1 m/s`，是明显的冲台/接触瞬间；
- 1024/512/256 的最后一帧 root 高度约 `0.52–0.58 m`，轮底在平台顶部附近。

最后一帧的状态数据本身全部 finite：

```text
qpos finite = True
qvel finite = True
qacc finite = True
sensordata finite = True
```

说明 NaN 不是在 dump 的最后一个 state 里，而是发生在其后的一个 `mjwarp.step`/更新路径。

## 3. 日志上的故障链

四个 run 都有相同的早期签名：

```text
/__w/pytorch/pytorch/aten/src/ATen/native/cuda/TensorCompare.cu:121:
_assert_async_cuda_kernel: Assertion `normal expects all elements of std >= 0.0` failed.
```

随后是：

```text
[NanGuard] Detected NaN/Inf at step ...
[NanGuard] NaN/Inf found in envs: [...]
Traceback ...
File ".../alldog_mjlab/algorithms/him/ppo.py", line 170, in update
    if kl_mean > self.desired_kl * 2.0:
torch.AcceleratorError: CUDA error: device-side assert triggered
Warp CUDA error 710 ...
```

因此“末端故障链和之前类似”**成立**：`normal` 的 std 断言 → CUDA device-side assert → CUDA context 污染 → Warp 710；traceback 落在 HIMPPO KL 同步点。

但需要注意日志顺序：

- 128 run 中 `normal expects std >= 0.0` 出现在 `Learning iteration 223` 输出之前；
- NanGuard 的 `step 58065` 出现在其后；
- CUDA 错误是异步上报的，不能仅凭打印顺序断言“sim NaN 一定先于 std NaN”。

所以更准确的说法是：

> 日志同时证明出现了 policy `std` 非有限/为负和 sim state NaN；但谁是第一因，当前日志不能严格排序，需要用 `CUDA_LAUNCH_BLOCKING=1` + 逐项 finite probe 才能钉死。

## 4. 对现有防护的判断

- `nonfinite_actions=0`、`max|action|` 约 8.5–9.2（远小于 clip 100），说明未出现动作自激/非有限动作进入 sim；
- `nefc_max` 32–36、`overflow_nonzero=0`，没有看到接触/约束容量溢出；
- `Episode_Termination/nonfinite_state` 在所有 run 中都是 0；
- NanGuard 的检测列表包含 `sensordata`，而 `_nonfinite_state` 只检查 qpos/qvel/qacc/qacc_warmstart，不含 `sensordata`；这与“nonfinite_state 没抓到但 NanGuard 抓到”一致；
- HIM 侧确实没有像 PPO 路径那样的 reward/return clamp、非有限 loss guard、terminal target 清洗；termination 前的终态观测记录器也手工绕过了 ObservationManager 的 nan policy；
- 这些都属于“可以补的防护”，不是本次录像要修的 bug；本次按要求没有改这些。

## 5. 结论

- 你的“同一故障签名、不是新数值类型”判断**基本正确**；
- “触发源是接触密集爬台时的单 env sim NaN”与录像和 NanGuard 现象**一致**；
- 但“sim NaN 先于 policy std NaN”目前**无法仅凭日志/CDP 证明**，因为 `normal` 断言先打印、NanGuard 后打印，而 CUDA 错误是异步的；
- 可以确认的是：最后一帧是**高台边缘、前轮接触/冲台**，其后的 step 或 HIM 更新路径出现了非有限状态；
- 下一步若要定位“第一个坏 tensor”，需要按你的建议做 lr=0 teacher-only + `CUDA_LAUNCH_BLOCKING=1` + 逐数组 finite probe；本次先只交付录像和现有证据。

## 6. 1 mm 圆角 A/B 实验结果（2026-10-25）

按用户要求，把高台暴露棱改为 1 mm 圆角凸包网格（Minkowski box+sphere，`ExactHighPlatformTerrainCfg.edge_radius=0.001`），其余配置与旧 pilot 相同：HIM official warm start、fixed 命令、`lr=5e-4`、`entropy=3e-3`、`ccd_iterations=0`、NaN guard。

| 配置 | 旧结果 | 1 mm 圆角结果 |
|---|---|---|
| 128 env | iter225 / step58065 崩 | **完整跑完 300 iter，无 NaN，part2_success 持续非零** |
| 256 env | iter22 / step5965 崩 | **完整跑完 50 iter，无 NaN** |
| 512 env（并发） | iter14 / step3960 崩 | iter26 / step7104 仍崩 |
| 512 env（solo） | — | **iter0 / step453 仍崩**（env184） |
| 1024 env（solo） | iter12 / step3399 崩 | iter19 / step5164 仍崩（env190） |

结论：1 mm 圆角对 128/256 env 明显有帮助，但 **512/1024 仍会出 NaN**，且 512 solo 这次甚至更早；因此“1 mm 圆角消除压强奇点”不是充分修复。可能是：

- 1 mm 对当前接触尺度太小；
- 平台网格凸包与轮子 cylinder 的接触仍存在异常；
- 或 NaN 还来自其它接触/求解器路径，不只是 8 条外棱。

新录像：

- [1mm 圆角 512 env solo NaN 前 100 帧](../../assets/videos/nan_debug/nan_round1mm_512env_solo.mp4)
- [1mm 圆角 1024 env solo NaN 前 100 帧](../../assets/videos/nan_debug/nan_round1mm_1024env_solo.mp4)
- [1mm 圆角 512 最后帧](../../assets/videos/nan_debug/nan_round512_solo_last.png)

按用户规则，如果仍异常且没有更强候选原因，下一步先采用防护形式；当前尚未改防护代码，先交付 A/B 结果和录像。


## 7. 圆角撤销与库侧 issue 核对

- 按用户要求，`exact_terrain.py` 已恢复为官方原始地形，不再使用 1 mm 圆角网格；实验视频保留在 `assets/videos/nan_debug/`。
- 代码审查：HIM policy/estimator/PPO 都是纯 PyTorch 可微算子；`source encoder` 在 `no_grad` 下是 HIM 原设计，`torch.normal`/`log_softmax`/`F.normalize` 没有手写不可微 kernel。没有发现我们这层引入的“不可微”错误。
- 但发现三类相关库侧已知问题：
  - [mjlab #870](https://github.com/mujocolab/mjlab/issues/870) 完全相同的 `normal expects all elements of std >= 0.0`；讨论提到 rsl_rl surrogate log-ratio 溢出和 obs normalization；修复 commit 启用 Go1 actor/critic obs normalization。
  - [mjlab #912](https://github.com/mujocolab/mjlab/issues/912) 轮足复杂地形 NaN；修复 commit `3cf17ee` 还加固了 `fit_terrain_normal`，说明库自身承认 NaN/Inf 可来自单个坏 env。
  - [mjlab #918](https://github.com/mujocolab/mjlab/issues/918) 把 “NaN hunting” 列为 v1.5 主题，关联 #912/#870。
  - [mujoco_warp #930](https://github.com/google-deepmind/mujoco_warp/issues/930) warp 物理 NaN；[Newton #3702](https://github.com/newton-physics/newton/issues/3702) 指出 nconmax 溢出可能静默变 NaN（我们 overflow=0 但值得监控）。
- 结论：不能简单归因“全是 MuJoCo”，也不能保证“我们代码全对所以只能是 sim”；已知库侧 NaN 问题存在，同时我们的 HIM 缺 finite guard/obs normalization/terminal sanitize，会放大问题。需要 lr=0 probe 才能定位第一因。

## 8. 8GB/进程显存协议预判

- HIM 128 env 实测约 1.7GB，256 env 约 3.2GB；512 env 预计 5–6GB，1024 env 预计 9GB+，因此 **HIM 512 env 在 8GB 限制内可行，1024 不可行**。
- 用 `512 env × 96 steps` 可把 batch 补到约 49k（相当于 1024×48 的 batch），总预算 512×96×3000≈147M steps，接近 N-W 262M 的一半；相对 1024×64 的宽度损失可通过 step/iter 部分补偿，预计不是数量级损失，但比 1024 宽 batch 略慢/样本相关性略高。
- PPO 侧由另一 Agent 自己控制在 ≤8GB；两边同时跑满足用户新协议。
- 明天若按 8GB 协议启动，建议 HIM 用 512 env × 96 step × ≥3000 iter，先 300 iter 看 strict success/NaN，再续训。

## 9. 2026-10-26 HIM row0 job12 复盘

job12（`him_row0_mixed_gate_1026_0959`）证明 10-25 的数值防护有效：1500 iter 没有 Warp 710，NanGuard 事件被 `nonfinite_state`/reset 吸收。但训练策略本身发散：`part2_success` 从 iter1≈1.9 降到 iter1499≈0.1–0.18，mean reward 8.7→75–90，action std 0.30→0.49，`max_abs_action` 6→100。也就是说，**数值安全 ≠ 策略安全**；HIM 还缺 teacher anchor/冻结 std/eval-gated checkpoint。job12 的旧 gate 因 `play=True` 无 Part2 term 而全 0，不能作为能力证据；修正 gate 后由 job14 重测 checkpoint。
