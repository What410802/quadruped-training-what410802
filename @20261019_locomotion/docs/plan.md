# Part2 / HIM 当前计划与待办

> 更新时间：2026-10-26 11:00。本文件是动态计划清单，完成项保留证据，避免“说过但漏做”。训练结果与实验细节仍放 `training/` 下的专题文档，这里只做状态与链接。

## 0. 执行约定

- 任何“成功”结论必须能指出对应的 strict term；评测配置必须 `assert` 该 term 存在，禁止把缺失 term 静默当 0。
- gate 一律用训练配置（`play=False`）+ `auto_reset=False`，在 reset 前读取 `part2_success/failure`；play 配置没有 Part2 终止项，不能用于 gate。
- 长训必须先 gate warm-start/早期 checkpoint，再决定是否续训；每 50–100 iter 有 checkpoint 与 gate 机会，禁止只 gate 最后一个 checkpoint。
- HIM 与 PPO 共用 task-spooler 单槽；job 必须写 summary、保留 checkpoint、记录 rc；失败/早停要写原因。
- 训练与评测物理参数要显式记录；HIM 当前 5 ms/4 dec 不是部署参数，最终必须用 2 ms/10 dec 复测。

## 1. 已核实的问题（2026-10-26）

### HIM gate 假测量：属实

- `him_part2_gate.py` 旧版用 `load_env_cfg(task, play=True)`；`blackw-official-him` 的 `play=True` 只有 `time_out/stuck/nonfinite_state`，没有 `part2_success/failure`。
- 旧 gate 的 `success/failure` 恒 0，job12 五类 0 不能作为 HIM 能力证据；high_wall `attempts_done=0` 还因为 play `episode_length_s=1e9` 不超时。
- 已修复：改用 `play=False`、`assert part2_success`、关闭 obs corruption、timeout 计 attempt、记录 `out_of_course`；修复后 smoke 2/2 success（platform row0）。

### job12 训练发散：属实

- iter1：`part2_success≈1.9`、`part2_clear≈0.17`、mean reward≈8.7、action std=0.30。
- iter1499：`part2_success≈0.10–0.18`、`part2_clear≈0.01–0.03`、mean reward≈75–90、episode length≈780、action std=0.49。
- `max_abs_action`：6.0 → 9.4 → 10.1 → 13.3 → 59.2 → 100.0（持续饱和）。
- 数值防护有效（无 Warp 710；一次 NanGuard 被 `nonfinite_state`/reset 吸收），但策略在“高 shaping reward、低 success、动作饱和”的坏解上发散。

### PPO 的 anti-forgetting 问题在 HIM 同样存在

- HIM 没有 `GuardedPPO` 的 base/anchor/KL 机制；只有数值 clamp，不是策略保护。
- HIM warm start 只映射官方 export 的 `actor.*` / `estimator.*` 参数，`distribution.std_param` 缺失；实际以 `init_std=0.3` 新初始化，不是官方策略的原 std。
- job12 使用 `lr=5e-4`、`entropy=3e-3`、5 epochs、1500 iter 单次长训，没有冻结/衰减 std、没有 eval-gated checkpoint、没有 BC/KL anchor。
- job12 只在末端 gate 一次（且 gate 坏），早期更好的 checkpoint 没有机会被选中；训练用 5 ms/4 dec，未做 2 ms/10 dec 对齐验证。
- PPO 侧已确认的另一类问题也需要在 HIM 检查：GuardedPPO 的 base 是“加载后的 m650”而不是显式 BC base；blend 方向容易弄反；HIM 后续若复用 GuardedPPO，必须先显式指定 teacher/BC base。

### 为什么这些问题会被引入（上升一层）

1. **play/train 配置不对称被当成同一个 config**：团队习惯“训练和评测共享 cfg”，但 Black HIM 特意把 Part2 strict term 放进 `if not play`；旧 gate 没有 contract test，smoke 只检查 JSON 能生成，不检查 term 在不在。
2. **计划写在文档、执行没有按计划**：`him-part2-gate-curriculum-plan.md` 写“先 gate warm-start，再只训练失败类别”，实际 job12 是“先 1500 iter 再 gate 最后一个”，计划与 job 脚本脱节。
3. **把 PPO 的数值安全网误当成 HIM 的策略安全网**：HIM 继承了 PPO 的 reward/return clamp，但没有继承 anti-forgetting/早停/选点；HIM 不是“换个算法的小 PPO”，它的 estimator 和 warm start 都需要单独契约。
4. **warm start 只验证 shape/mapped 数量，没有验证分布 std**：官方 TorchScript 不导出 std，fresh std 与官方 mean 不匹配，长训高 lr 会把策略带离 teacher。
5. **指标不可解释**：mean reward 随 episode length/存活时间上升，与 sparse success 反向；没有把“episode length、action saturation、success”组合成 gate 指标，导致看对数以为在进步。
6. **队列脚本只保证 FIFO/不 OOM，不保证科学流程**：没有 summary verdict、没有早停、没有对“坏 gate”做 fail-loud，运维成功被误读为实验成功。

## 2. 短期待办（P0，今天/队列内）

- [x] P0-1 修复 `him_part2_gate.py`：`play=False`、assert strict term、clean obs、timeout 计 attempt、记录 out_of_course。
- [x] P0-2 修复后 smoke：2/2 success，证明 gate 能区分成功，不再全 0。
- [x] P0-3 已提交修正后的 job12 全 checkpoint re-gate（task-spooler job 14；31 个 checkpoint × 5 类 × 10 attempts）。
- [ ] P0-4 job14 结束后读 `~/rc_work/logs/him_regate_job12_*`：找出早/中期 success 最高的 checkpoint；不要用 job12 原 gate 的 0。
- [ ] P0-5 对 job12 的 `model_0`（warm-start）与最佳 checkpoint 做 20/20；结论写入本文件 §4。
- [ ] P0-6 对 job13（PPO stairs30）不做盲目续训：等其结束/早停后，对 m650 起的 checkpoint 跑完整 judge；若 continue 无提升，记录为负结果，不占 HIM 主线。
- [x] P0-7 把“gate 假测量/job12 发散”的结论同步到 `training/him-part2-gate-curriculum-plan.md` 和 `training/nan-video-diagnosis.md`。

## 2b. 无 GPU 审查已落地（2026-10-26）

- 详见 [HIM 主链路审查](training/him-code-audit-2026-10-26.md)。
- gate：`play=False` + strict assert + `--check-config-only`，5 类配置预检全部有 `part2_success/failure`，episode_steps=1000。
- warm start：`BLACKW_HIM_INIT_STD` 默认 0.1（原 0.3），并对缺失 `distribution.std_param` 打印 warning。
- anti-forgetting：新增可选 `BLACKW_HIM_ANCHOR_ALPHA`（warm-start teacher snapshot；默认 0 不改变现状）。
- std：新增 `BLACKW_HIM_FREEZE_STD=1` 训练冻结；`precheck` 保留旧语义。
- reward A/B：新增 `BLACKW_PROGRESS_W` / `BLACKW_CLIMB_W` / `BLACKW_CLEAR_W`，默认值不变。
- 未改：5ms/4dec 默认物理、绝对 shaping reward 默认权重、judge/export；这些需要 GPU/实验验证，不能盲改。

## 3. 短期待办（P1，HIM 下一轮）

- [ ] P1-1 不再直接升 row1/扩命令；先用 warm-start teacher 做 300–500 iter 微调：
  - `lr≈1e-4`（先降 5x）、`entropy=0`、冻结/衰减 `std`；
  - 加显式 BC/teacher anchor（KL 或权重锚），base 必须固定为 warm-start 官方 actor，不是“当前 actor 的第一次快照”；
  - 每 50–100 iter gate + judge 选点；退化就回滚/best-of-N。
- [ ] P1-2 先 gate `model_0` warm-start，只训练失败类别；row0 达到 gate 标准前不升 row。
- [ ] P1-3 row0 用真实任务命令范围（vx/vy/wz），加 spawn/initial-state 抖动；每类 20/20，重复 2–3 组 seed。
- [ ] P1-4 同 checkpoint 在 5 ms/4 dec 与 2 ms/10 dec 各评一次；任何“通过”必须给出部署物理参数下的数字。
- [ ] P1-5 导出 HIM TorchScript，跑一次官方 judge 场景；训练谓词通过不等于官方 judge 通过。
- [ ] P1-6 是否继续 full PPO 长训：只有 P1-1 的 eval-gated 微调仍不涨时才考虑；备选是官方策略 + 少量残差/DAgger。

## 4. 中长期待办（P2/P3）

- [ ] P2-1 row0 五类全部 20/20 后，手动 `BLACKW_MAX_ROW=1` resume；每档重复 gate，不自动跳档。
- [ ] P2-2 逐档到 platform 40 cm、slope 45°、trench 30 cm、wall 30/40、stairs 20/30；高档只改难度参数，不改几何拓扑。
- [ ] P2-3 混合策略：先每类专项，再 mixed row0 回归；每升一档复测所有低档，防遗忘。
- [ ] P2-4 HIM 部署导出、judge 单条/批测、与 Part1 动作切换和 ROS `/joy` 联调。
- [ ] P2-5 PPO 侧：补 `gate_stage.py` + `eval_blackw_part2.py` jitter/command-set、comp placement；显式 BC base；修 `PREVDIR` glob；blend 方向先做单变量实验。
- [ ] P3-1 队列运维：job 统一 common.sh（SIGTERM/summary/verdict）、checkpoint 回传、夜间重启恢复；单 job ≤2 h。

## 5. 队列快照

| job | 内容 | 状态 |
|---|---|---|
| 11 | PPO slope μ=1.2 诊断 | finished；非交付负结果 |
| 12 | HIM row0 1500 iter + 坏 gate | finished；gate 无效，训练发散 |
| 13 | PPO stairs30 续训 | running；需早停/judge 复核 |
| 14 | HIM job12 全 checkpoint 修正 gate | queued |

## 6. 关联文档

- [HIM row0 gate/课程协议](training/him-part2-gate-curriculum-plan.md)
- [NaN/数值异常与防护](training/nan-video-diagnosis.md)
- [训练预算与配方](training/training-budget-and-recipes.md)
- [任务状态](status.md)

## 7. 用户方案评估（2026-10-26）

用户提出的路线：除 30 cm trench 和 plum 外，其他任务 row0 跑通后手动 gate 逐档提升；trench30/plum 后期再做深度视觉；过程中优化奖励/终止设计以帮助升档。

评估：**方向一致，建议加三条约束。**

1. “row0 跑通”必须按 category 分别 20/20 strict gate，不能只看 mixed 总 success；混合策略还要做低档回归。
2. trench 先只做 blind 20 cm；30 cm 作为 depth/vision 分支，不混进 blind row 课程；plum 同理。这样不会为了两个后期任务污染主线。
3. 奖励/终止优化必须单变量、可回滚、每次 gate 前后对比；不能为了让 gate 过而改判据。当前 HIM 的 `competition_progress`/`climb_height` 是绝对 progress/高度型 shaping，配合 timeout 可能奖励“停在终点附近但不满足 strict success”，这是 job12 mean reward 高而 success 低的重要候选；下一轮应优先做 potential-based/delta progress 与 success/sparse 权重的对照。

## 8. 审查策略：不是全仓无差别全审

结论：**没有必要把整个仓库所有代码无差别审一遍**；但必须在下一轮长训前完成一次 **HIM 主链路关键合同审查**。理由：最近卡住的都是 play/train config、gate、warm-start、job 脚本、指标解释这些“集成层”问题，不是 HIM 算法主体。

审查范围（P0）：

- `tasks/velocity/blackw/env_cfgs.py`：task 构造、row 选择、严格 termination/reward、play/train 差异；
- `tasks/velocity/black/him.py`：history/terminal/estimator target 合同；
- `tasks/velocity/black/him_rl_cfg.py` + `blackw/him_rl_cfg.py`：lr/entropy/std/epochs、warm-start 字段；
- `algorithms/him/{policy,ppo,estimator,storage,spec,warm_start}.py`：可微路径、finite guard、optimizer 分账、KL、terminal target；
- `blackw/him_runner.py` / `black/him_runner.py`：warm-start 映射、action guard、reward clamp、save monitor；
- `scripts/agent_scripts/him_part2_gate.py` + `him_*_job.sh`：play=False、strict assert、early-stop、summary；
- task registry / get_checkpoint_path / resume 路径：run name/checkpoint 选择、glob 碰撞。

审查方法：

- 每个 config 输出 `terms/rewards/obs dims/action dims/episode steps` 并断言关键项；
- 每个 metric 用“已知正样本 + 已知负样本”做 contract test（gate 已做 2/2 positive）；
- 每个 job 脚本先跑 `--check-config-only`/`bash -n`，再入队；
- 不在审查同时改算法超参；先记录问题，单变量修。

不审范围：read-only 官方 `.pt`、外部 PPO 交付代码、与 HIM 主链路无接口的 Part1 代码；只审接口。

## 9. Git 分批提交与推送约定（2026-10-26）

- 本地主仓 `MyMonoRepo.d`：只提交本次 HIM 相关文档/脚本/诊断视频；PPO/comp、`@20261024_blackw/ws` 构建产物、`output/`、大策略目录不入库。
- 远端训练仓 `~/rc_work/nwwolf_mjlab_training_release`：按层分批提交，先 HIM algorithm，再 HIM task/runner，再必要 shared config/robot，再 gate/job 工具；不提交 PPO 训练脚本、PPO checkpoint、`__pycache__`、policy 目录。
- 每次只用显式路径 `git add <file...>`，禁止 `git add -A` / `git add .`，避免把 PPO 工作区和未审查产物扫进去。
- 每批提交一行英文：`type(him): ...` 或 `chore(common): ...`；提交后 `git status --short` 复核，再 `git push`。
- 本地仓推 `origin master`；远端训练仓推 `origin main`（`upstream` 是 N-W-wolf，不动）。
- 远端只需提交代码与 HIM gate 脚本；训练日志、checkpoint、视频留在机器上，不进 Git。

## 10. 2026-10-26 Git 分批提交记录

本地主仓 `master` 已推送 `origin`：

- `1f16dec` `docs(him): add HIM gate, audit, NaN diagnosis and Part2 plan`
- `7314a61` `test(him): add strict Part2 gate and checkpoint re-gate tooling`
- `1051047` `docs(him): add NaN diagnostic replay videos`

远端训练仓 `main` 已推送 `origin`：

- `5b029e4` `feat(him): add HIM algorithm guards and strict Part2 gate tooling`
- `4427703` `feat(him): add blackW HIM task, exact Part2 terrain and runner`
- `d637859` `chore(common): add shared competition env dependencies required by HIM tasks`

说明：远端机 HTTPS 无凭据，推送通过本机 SSH 把远端 `git bundle` 拉回后推到 GitHub；远端工作区仍保留未提交的 PPO 改动，按“PPO无需”要求不提交。
