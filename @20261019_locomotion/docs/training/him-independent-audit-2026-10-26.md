# HIM 独立审计结果（2026-10-26）

审计者：独立 teammate（read-only，无 GPU 训练）。

## Verdict

**READY_FOR_HIGHER_PART2**（HIM training path），前提是完成两项 pre-launch 收尾；本次已完成：

1. post-rewrite contract smoke：
   - model_0 platform，deploy physics，2/2 success；
   - 大 jitter negative，0/2；
   - train physics 0/2，说明 screen 对物理敏感，不能当 judge。
2. 文档与代码同步：judge 降级为本地 proxy，std/CCD/lane/predicate/estimator LR/deployment artifact 已记录。

## 审计确认正确

- history 顺序、canonical flip、current frame、export wrapper；
- `process_env_step` next-obs + terminal override、storage index；
- estimator/PPO optimizer 分账、checkpoint load actor 覆盖 estimator；
- std scalar fallback、estimator LR 解耦、warm-start 缺 MLP fail/guard、`sim.mujoco.ccd_iterations` 路径；
- gate screen 语义、5 类 config preflight、gate action nan/clip；
- HIM export/judge proxy 342→16、signed wheel scale。

## 已接受的剩余风险

- training geometry、local proxy judge scene、official ability_field 三者仍不完全一致；proxy 分数不是官方分数；
- 训练 5 ms/4 dec + CCD0 vs judge 2 ms/10 dec + CCD35；
- HIM deployment artifact 已放入 `@20261024_blackw/.../policy/blackW/him_row0`，但未跑 rl_sar C++/ROS `/joy`，不算 deploy-ready；
- high_wall 30/40 的 root height 可能偏紧，需 row 观察。
