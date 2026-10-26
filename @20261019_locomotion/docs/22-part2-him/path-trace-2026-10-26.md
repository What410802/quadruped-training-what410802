# HIM 实际代码路径推演（2026-10-26）

> 目的：不只做 lint，而是按实际调用路径检查数据语义、控制流和契约；本文件是 2h 静态轮次的主记录。全程未占用 GPU。

## 1. 训练路径

```text
blackw/__init__.py register tasks
  -> blackw/env_cfgs.py (play=False)
     -> _apply_blackw_overrides(black_competition_env_cfg)
     -> HIM observation: actor history 6×57 / estimator_velocity / terminal recorder
  -> rsl_rl OnPolicyRunner
     -> HIMPPO.act(obs)  [current obs -> action/value/logprob/distribution]
     -> _ActionGuardWrapper.step(action)
     -> env.step -> next_obs, rewards, dones, extras
     -> HIMPPO.process_env_step(next_obs, ...)
        -> successor estimator target = next_obs frame/velocity
        -> terminal extras override for done envs
        -> storage.add_transition(transition from act)
     -> HIMPPO.update()
        -> mini-batch estimator.update(current history, next target)
        -> PPO surrogate/value/entropy
        -> optional anchor/finite guards
```

### 关键语义核对

- RSL-RL `PPO.process_env_step` 的 `obs` 是 **env.step 后的 next_obs**；HIMPPO 用它构造 successor target，方向正确。
- `PPO.act` 在 env.step 前保存 `transition.observations = current obs`；storage 的 current history 与 `next_estimator_input` 对齐。
- `HimTerminalRecorder.record_pre_reset` 在 reset 前重新 `sim.forward/sense` 并写 extras；HIMPPO 用 terminal ids 覆盖 target；路径闭合。
- `HIMPPO.load(load_cfg={"actor": True})`：RSL-RL `PPO.load` 会对整个 actor module 做 state_dict；HIM estimator 在 actor 内，因此 estimator 权重随 actor 加载；只跳过 critic/optimizer/iteration，符合 gate 推理需求。
- `HIMPolicy.get_latent`：current frame 取 `history[..., -1, :]`（MjLab oldest→newest 的 newest），source encoder 输入 `canonical_history`（newest→oldest）；与 official export contract 一致。
- `HIMPPO._successor_estimator_targets` 只在 done 环境用 terminal extras；非 done 使用 next observation，未使用 reset 后新 episode 的 obs。

## 2. gate 路径

```text
load_env_cfg(task, play=False)
  -> assert part2_success present
  -> auto_reset=False
  -> category filter + row + command/jitter/physics
  -> ManagerBasedRlEnv
  -> RslRlVecEnvWrapper
  -> load_runner_cls + runner.load(actor=True)
  -> rollout until attempts
  -> read termination_manager terms before env.reset(done_ids)
  -> JSON screen_pass / acceptance_eligible=false
```

### 核对结论

- 旧版 `play=True` 没有 Part2 term，是必现假 0；当前已修。
- `auto_reset=False` + reset before next step，能读到 terminal predicate。
- `--physics deploy` 已补 euler/elliptic/impratio/iterations/CCD/init z；但仍不是官方 PGS/judge。
- 这是 **training-predicate screen**，不是 judge；不能作为验收。见 [gate vs judge 契约](gate-vs-judge-contract.md)。

## 3. 路径推演发现的剩余语义风险

1. **gate vs judge 不同谓词**：单步 vs hold、wall climb、stairs top_seen、trench crossing；静态已确认，需要 judge adapter。
2. **estimator anchor**：`BLACKW_HIM_ANCHOR_ALPHA` 只锚 `HIMPolicy.policy_parameters()`（actor MLP + distribution），没有锚 estimator；estimator 仍可能漂移。静态上不是 bug，但 anti-forgetting 不完整。
3. **absolute shaping**：`competition_progress` 是绝对 progress，不是 delta；training termination+timeout 下可能奖励“停在终点附近”。需 A/B。
4. **job21 的 checkpoint gate** 只 10 attempts、单 seed、train physics；即使 screen 通过也不能当最终验收。
5. **gate deploy 与训练物理**：gate 用完整 deploy option，但 HIM 训练仍 5 ms/4 dec；训练策略可能对 deploy 迁移敏感。

## 4. 本轮静态检查结果

- `pyflakes`：HIM 代码原先只有 unused imports，已清理；gate 无 undefined name。
- `py_compile` / `bash -n`：通过。
- gate 5 类 `--check-config-only`：全部含 `part2_success/failure`，episode 1000 steps。
- `him_static_preflight.sh`：通过（含 pyflakes、play=True 禁止、screen_pass/acceptance_eligible 检查、旧 gate_pass 残留检查）。
- 未运行 HIM GPU 训练；不连续占用 GPU。

## 5. 2026-10-26 12:3x 新发现并修复的路径 bug

- **stairs training predicate 假阴性**：旧 predicate 要求跨完整上+下台阶到 `down_end≈6.30`，但本地 judge proxy 的 stairs 只要求到 top/landing（goal_x_min=3.3, top_z=step height）。因此 screen 报 0/20，但本地 judge proxy 对同一 `model_0` 的 stairs 10/15/20 cm 成功。
- 已改为 judge-aligned：从 exact stairs CFG 读取总高/步数，要求 `rx>=3.30`、wheel support 在 step 高度带、root height 合理；screen stairs smoke 从 0/20 变为 3/5（5 attempts 中 4 个 episode 结束）。
- 修复过程中发现 `float(difficulty)` 对标量 tensor 报错；改为 per-env tensor 广播，已 py_compile/pyflakes 通过。
- 这属于“路径语义 bug”，lint 抓不到，只有对照 judge 和实际 code path 才能发现。

## 6. 导出/judge 路径结果

- `export_him_policy.py` 已导出 model_0，TorchScript contract 通过；
- 本地本地 judge proxy 对 model_0 total_score=410（stairs 10/15/20 成功等）；
- job12 末 checkpoint judge total560，但出现 base_z=-84 等非法状态，说明 judge runner 需要 invalid-state 守卫，不能把 560 当真实提升。

## 7. 2026-10-26 13:0x 重写后 contract smoke

重写 geometry predicate 后，用 model_0 跑 gate 2 attempts：

| case | physics | attempts | success | negative? |
|---|---|---:|---:|---|
| platform, normal jitter | train | 2 | 0 | — |
| platform, normal jitter | deploy | 2 | **2** | — |
| platform, huge jitter (x2/y5/yaw1) | train | 2 | 0 | negative 成立 |

结论：
- deploy physics 下 positive 通过、故意大 jitter negative 也通过；
- train physics 相同 checkpoint platform 0/2，说明 screen 对训练/评测物理敏感，不能把 train screen 当 judge；仍保持 screen/acceptance 区分。
- 这不是正式判据，只是 contract smoke；未宣称 row0 通过。

## 8. 2026-10-26 14:0x job24 根因与修复：CCD=0 丢失轮地接触

- `2952f3b` 把错误的 `cfg.sim.ccd_iterations` 改成正确的 `cfg.sim.mujoco.ccd_iterations=0`，结果 **CCD 真正关掉**。mujoco_warp 对 cylinder-vs-terrain 凸对使用 GJK/EPA 的 `ccd_iterations`；0 次迭代等于没有支撑接触，机器人从出生点直接穿过 patch floor。
- 单变量 A/B（256 env，同 warmstart/seed/lr/std/anchor，2 iter）：

| metric iter1 | ccd=0 (job24) | ccd=50 (fix) |
|---|---:|---:|
| mean reward | -273.9 | +8.55 |
| episode length | 76.8 | 146.3 |
| bad_sim_state /step | 1.02 | 0.0000 |
| bad_orientation /step | 3.18 | 0.0000 |
| base_height | -3.83 | -0.0156 |
| lin_vel_z | -7.90 | -0.0244 |
| part2_success /step | 0.0 | 1.17 |
| max abs action | 44.90 | 5.08 |

- 修复：`BLACKW_CCD_ITERS` 默认 50；wheel-aware `bad_sim_state`（`max_wheel_vel=400`，`BLACKW_MAX_WHEEL_VEL=0` 可回退）；`max_abs_action` 每次 save 清零。
- job25（40 iter，512 env×96，`timeout 280`，同一 warmstart/std/anchor）验证：mean reward +15.8..+17.1，episode length 231–249，`part2_success` 1.94–2.34，`bad_sim_state=0`，`bad_orientation=0`，`max|a|=6.411`。

### 负 reward 是否有问题？

- **绝对 offset 本身不是问题**：GAE/优势会减 baseline，per-step 常数在理论上被 critic 吸收；scale、相对差异和 termination 才重要。
- job24 的问题不是“reward 是负的”，而是 CCD=0 让机器人掉出地形，`base_height_l2_terrain`（射线打空）≈-12/step、`lin_vel_z`（vz≈13）≈-23/step 吞掉 ~97% return；`part2_success=0` 没有正梯度，只能学“减少 |vz|”。
- `bad_sim_state` 是 terminal（无 bootstrap）；高 bad_sim 比例会强化“尽快结束”的坏局部解。
- ±50 reward clamp / return clamp 在 job24 没有触发，不能归因于 clamp。
