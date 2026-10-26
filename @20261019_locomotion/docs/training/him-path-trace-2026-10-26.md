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
- 这是 **training-predicate screen**，不是 judge；不能作为验收。见 [gate vs judge 契约](him-gate-vs-judge-contract.md)。

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
