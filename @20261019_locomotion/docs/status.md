# 推进情况

> 只保留**当前状态、路线位置、下一步、待决与指针**；已完成细节、历史实验和复现数据放对应文档，不在本文件重复。

## 0. 本文件记录标准（自己也要遵守）

- **用途**：跨对话对齐“现在做到哪、下一步做什么、卡在哪”；不是实验日志、提交记录或教程。
- **只写四类内容**：当前路线位置、P0/P1 里程碑状态、下一步顺序、待决/风险；其余放链接。
- **“完成”只到里程碑**：P0/P1 等 gate 才写完成；子步骤、单个脚本/场景的完成放任务 `docs/` 或 README。
- **不复述细节**：judge 语义、几何参数、训练曲线、命令输出不在本文件展开；用一句话结论 + 文档指针。
- **跨对话校准**：新对话先读本文件，再读任务 `README.md`、相关 `docs/`；发现与代码/资产不一致时先改本文件或注明“待校准”。
- **更新时机**：完成 P0/P1 gate、进入下一阶段、出现阻塞/决策、状态明显变化时更新；不因单个脚本小改而改。
- **段落单行**：遵循仓库 §2.1；每条尽量一行，便于 diff 和检索。

## 0.1 本任务授权与约定

- **Git 提交**：2026-10-22 起用户允许 AI 直接提交（直到用户明确撤销）；提交不推送 GitHub，不提交 `.vscode/settings.json`；任务级授权覆盖仓库级默认“不代为提交”。
- **可视化**：复杂、多步、需要视觉确认、结果精彩或能说明问题的过程，默认留视频/截图/contact sheet + JSON/CSV 诊断；本地放 `prep.d/videos`、`prep.d/results`，不入库，文档记路径和结论。
- **任务级覆盖**：仓库级约定是父级默认；本任务 `docs/status.md`/`docs/` 的更具体约定在任务内优先，偏离父级需在此记录理由/范围。

## 1. 当前定位

- **主目标**：2026-11-04 队内赛（障碍赛 900 + 能力测试 1300，占 70%；7 分钟答辩 30%）。真值见 [`reference/team-race-2026.md`](reference/team-race-2026.md)。
- **路线位置**：**P0 已完成（2026-10-22）**；**P1 已启动**（训练机 GPU smoke 通过）。
- **P0 范围**：场地/判定/手动状态机/评测/审计/演示链路闭环；P0 不包含训练。训练机已恢复（RTX 5060 Ti 16 GB），P1 开始使用。
- **控制仓库独立**：`quadruped_control` 是独立 C++/ROS 仓库；已创建个人 fork [`What410802/quadruped_control`](https://github.com/What410802/quadruped_control)，P0 提交 `f2b37dc` 已推送；本地 clone 的 `origin` 指个人 fork，`upstream` 指 `N-W-wolf/quadruped_control`，`local_readonly` 保留原只读副本。
- **当前策略**：`flat-ft-2500` 是唯一 baseline；足端 clearance 约 0.022 m，几乎拖地；不能把 zero-shot 障碍结果当验收。


## 2. P0 完成摘要（只列验收范围）

- **Part 1**：`part1_scene.xml` 工作副本 + `Part1Judge`/`Part1EventJudge`（足端 ground、限高杆、桥、T 台阶逐级接触、砂砾/斜坡、绕杆 checkpoint）；八障碍 zero-shot 诊断与 contact sheet 已生成。
- **Part 2**：`part2_plum.xml`（PDF 参数，几何精确检查）+ `ability_field` 官方能力场本地 eval + 六类 capability eval spec（`config/part2-ability-tasks.yaml`）。
- **手动部署**：`quadruped_control` 本地 fork 用 Pixi MuJoCo 3.12/LibTorch 2.12 构建 GUI；8 状态具名键 `F/G/J/B/T/Y/U/N` 已通，policy 仍是 `flat_ft` 占位。
- **审计/演示**：`audit_deployment.py` 通过（45 维 actor、无禁用传感器、力矩合规）；演示指南 [`demo/acceptance-demo-guide.md`](demo/acceptance-demo-guide.md) 已写。
- **可视化/文档**：Part 1 judge contact sheet、Part 2 stand 视频、AI 障碍方向自检 [`reference/agent-visual-checklist.md`](reference/agent-visual-checklist.md)、Pixi 迁移记录 [`reference/quadruped-control-pixi-migration.md`](reference/quadruped-control-pixi-migration.md)。

## 3. P1 计划（当前阶段）

1. **训练仓同步 + capability task smoke**：训练机 `~/rc_work/nwwolf_mjlab_training_release` 同步本地修改；生成/校验 Part 2 slope/stairs 等 capability terrain task，先跑 GPU smoke，不追指标。
2. **slope/stairs**：从 `flat-ft-2500` 做课程训练；先看 foot clearance、摔倒、tilt、1/2 足 ground；目标是可控低档分。
3. **Part 1 关键障碍**：limit_bar/bridge/high_wall 专项；桥窄带先低速状态机，后续再评估相机。
4. **history/camera**：专项 baseline 稳定后再加 6 帧 history；深度相机最后。
- **P1 gate**：不在本文件展开，见 [`training/eval-protocol.md`](training/eval-protocol.md) 与 [`training/training-plan.md`](training/training-plan.md)。

## 4. 最近验证（2026-10-22）

- P0 自检：`check_plum_geometry` / `check_state_machine` / `check_part2_ability_tasks` / `part1_event_judge` / `audit_deployment` / docs checker 全部通过。
- Part 1 zero-shot 诊断：八项 0 分/0 success；限高杆已改为沿 y 穿门洞，高墙已改为沿 y 跨墙，二者仍是 fail/running；这是 baseline，不是正式分。
- 桥：blocks fail、bands running；flat 策略无桥面训练，tilt 升高；需要 P1/P2 专项。
- 训练机 GPU smoke：`black-flat` 512 envs × 11 iter 约 7 s、Iteration time 0.67 s；P1 环境可用。
- 控制仓库 fork：`https://github.com/What410802/quadruped_control`，P0 分支 `main@f2b37dc` 已推送，未合并 upstream。

## 5. 待决 / 风险

- **Part 1 是否允许局部自动/固定动作**（规则允许、自动无加分）仍待用户确认；Part 2 已确认纯 RL。
- **judge 校准**：T 台阶逐级接触、限高杆位移、砂砾坑短边进出、桥面 step 还没有真实手动轨迹标定；当前是 P0 启发式。
- **正式整场分**：尚无官方多尝试计分；现有 0/8 只是独立障碍诊断。
- **P1 训练门槛**：数值安全、foot clearance、地形课程未验证；训练机已可用，先 smoke 再正式训练。
- **没有阻塞 P1 启动的决策**；若出现奖励/课程取舍或资源冲突再停下。

## 6. 关键指针

- 任务入口：[`../README.md`](../README.md)
- 比赛真值：[`reference/team-race-2026.md`](reference/team-race-2026.md)
- judge 设计：[`training/competition-judge.md`](training/competition-judge.md)
- 手动状态机：[`training/manual-fallback-state-machine.md`](training/manual-fallback-state-machine.md)
- 地形资产：[`terrain/competition-assets.md`](terrain/competition-assets.md)
- 演示指南：[`demo/acceptance-demo-guide.md`](demo/acceptance-demo-guide.md)
- AI 方向自检：[`reference/agent-visual-checklist.md`](reference/agent-visual-checklist.md)
- 控制仓库研读：[`reference/quadruped-control-study.md`](reference/quadruped-control-study.md)
- 训练计划/评测：[`training/training-plan.md`](training/training-plan.md)、[`training/eval-protocol.md`](training/eval-protocol.md)
