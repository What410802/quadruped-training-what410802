# rl_sar 后备栈（P2 前保底）

> 目的：`quadruped_control` 是主部署栈；rl_sar 不并行维护，但保留可构建/可自检的 P2 前保底路径。最终学习成果优先接到主栈，只有主栈出现硬阻塞时才切后备。

## 1. 后备适用条件

只有出现以下情况才启用 rl_sar：

- `quadruped_control` 的真实后端或 ROS 2 三进程无法在队内赛前跑通；
- 实机接口只支持 rl_sar 的 `rl_real`/MIT 指令路径；
- 主栈策略切换/状态机出现短期无法修复的阻塞，且比赛需要先有可走保底。

不启用的情况：只是“想比较效果”或 P1 训练还在正常推进。

## 2. 后备资产（保留，不修改）

- 实现：`@20261007_assignment/ws/src/rl_sar/`（Apache-2.0，来自 `fan-ziqi/rl_sar e5c2f41` 的 assignment 移植）。
- 策略：`policy/black/himloco/best.pt`（HIM 270 维，45×6 history）。
- 仿真链路：`@20261005_ros2` 的 `sim_node` + `joy_node` + `rl_sim`。
- 文档：`@20261007_assignment/docs/porting.md`、`policy-model.md`、`control-stack-rates.md`。
- 自检脚本：`@20261007_assignment/scripts/agent_scripts/check_walk.py`（完整走路，需要 GUI）和两个无硬件自检（见下）。

## 3. 快速检查

```bash
# 从 MyMonoRepo.d 根运行；只跑无硬件自检
pixi run bash @20261019_locomotion/scripts/agent_scripts/check_rl_sar_fallback.sh
```

通过时应看到：

```text
result: all checks passed
result: all checks passed
rl_sar fallback self-tests: OK
```

完整仿真保底：

```bash
pixi run ros2-build
pixi run ros2 launch rl_sar rl_sim.launch.py
pixi run python @20261007_assignment/scripts/agent_scripts/check_walk.py
```

## 4. 与主栈的接口/学习差异

- rl_sar 后备跑 **HIM 270**（`best.pt`），不是当前 `flat-ft-2500` 45 维；两者观测/动作契约不同，不能混用 checkpoint。
- 主栈 `quadruped_control` 已接 45 维；后续训练优先导出主栈可加载的策略。
- 若主栈策略有突破，但后备仍需要 HIM，可把策略导出/改造成 rl_sar 的 270 契约；这是有成本的最后手段，不在 P1 做。
- 后备状态机/输入/限位是 assignment 版本；与主栈 named state 语义不一一对应，切栈时必须重新验收。

## 5. 何时决定切换

建议在 P2 入口做一次 gate：

- 主栈 Part 1 场景 + 策略切换 + 真机/三进程链路至少一项跑通；
- 若主栈仍未跑通，而 rl_sar 无硬件自检和 `check_walk` 通过，则 P2 保底启用 rl_sar；
- 切换后不删除主栈代码，保留为后续 P3 继续接续学习的路径。

## 6. 当前状态（2026-10-22）

- 两个无硬件自检已通过（2026-10-22：`check_rl_sar_fallback.sh` → input_map/command_limit 均 all checks passed）；`best.pt` 在 assignment 目录内；
- 完整 `check_walk` 未在本次重新跑（需要 GUI/仿真），上次 assignment 已 7/7 通过；
- 后备栈不修改，只作为 P2 前保险。
