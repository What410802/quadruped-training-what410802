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
- **路线位置**：**P0 已完成（2026-10-22）**；**P1 数值稳定性已修（2026-10-24，见 training-health §7），P1 质量 gate 仍未过**；**C2 视觉主线已开工**：深度相机 task 已进训练仓、obs/CNN 管线与成本/100-iter 稳定性 smoke 见 [`training/camera-depth.md`](training/camera-depth.md)。当前没有训练进程。
- **P0 范围**：场地/判定/手动状态机/评测/审计/演示链路闭环；P0 不包含训练。训练机已恢复（RTX 5060 Ti 16 GB），P1 开始使用。
- **控制仓库独立**：`quadruped_control` 是独立 C++/ROS 仓库；个人 fork [`What410802/quadruped_control`](https://github.com/What410802/quadruped_control) 已推送 `f2b37dc`；本地 `origin`=个人 fork、`upstream`=`N-W-wolf/quadruped_control`、`local_readonly`=原只读副本。**暂不切 coverMoon**：它比团队 fork 超前 17 个提交/190 文件，但 P1 训练不依赖控制仓库；P1 baseline 稳定后再在独立分支 rebase 到 `coverMoon/quadruped_control` 并重跑 Pixi 构建/测试。
- **当前策略**：本地训练 baseline 仍是 `flat-ft-2500`（足端 clearance 约 0.022 m，几乎拖地）；新增外部 blind baseline `best.pt`（HIMLoco，平地 cmd 0.5 实测 vx=0.36 m/s、稳定不摔；Part2 低/中档在时间放宽后 8/20 档成功，见 [`training/him-best-zero-shot.md`](training/him-best-zero-shot.md)）。两者都**不能**把 zero-shot 障碍结果当验收。


## 2. P0 完成摘要（只列验收范围）

- **Part 1**：`part1_scene.xml` 工作副本 + `Part1Judge`/`Part1EventJudge`（足端 ground、限高杆、桥、T 台阶逐级接触、砂砾/斜坡、绕杆 checkpoint）；八障碍 zero-shot 诊断与 contact sheet 已生成。
- **Part 2**：`part2_plum.xml`（PDF 参数，几何精确检查）+ `ability_field` 官方能力场本地 eval + 六类 capability eval spec（`config/part2-ability-tasks.yaml`）。
- **手动部署**：`quadruped_control` 本地 fork 用 Pixi MuJoCo 3.12/LibTorch 2.12 构建 GUI；8 状态具名键 `F/G/J/B/T/Y/U/N` 已通，policy 仍是 `flat_ft` 占位。
- **审计/演示**：`audit_deployment.py` 通过（45 维 actor、无禁用传感器、力矩合规）；演示指南 [`demo/acceptance-demo-guide.md`](demo/acceptance-demo-guide.md) 已写。
- **可视化/文档**：Part 1 judge contact sheet、Part 2 stand 视频、AI 障碍方向自检 [`reference/agent-visual-checklist.md`](reference/agent-visual-checklist.md)、Pixi 迁移记录 [`reference/quadruped-control-pixi-migration.md`](reference/quadruped-control-pixi-migration.md)。

## 3. P1 当前阶段

- **已完成**：训练仓 `black-basic-obstacle` task（flat + smooth slopes + stairs）；两轮 4096-env 训练（resume from flat-ft），各约 1 h 11 min；P1 policy 导出并做 Part 1 迁移诊断。**当前没有训练进程**。
- **2026-10-24 数值稳定性修复**：从 `model_5496` resume 的 4 次 run 在 100 iter 内崩 Warp CUDA 710；插桩定位为“坠落状态 -> 动作经 last-action 观测自激 -> 超大动作 -> NaN”，已装三项安全网（actor obs clip ±100 与部署一致、`clip_actions=±100` 与部署一致、`bad_sim_state` 极端状态终止），200-iter resume smoke 无 CUDA/NaN；详见 [`training/training-health.md`](training/training-health.md) §7。**P1 质量 gate 仍为未通过**（训练 reward 不等于通过率）。
- **当前结论**：第一轮桥/限高杆有改善，第二轮训练地形 level 略升但 Part 1 迁移退化；不能只靠续训，也不能把训练 reward 当通过率。详见 [`training/p1-basic-obstacle.md`](training/p1-basic-obstacle.md)。
- **下一步（等用户指示）**：先做训练环境评估和课程/奖励调整；再决定 P1 第三轮训练或转向 Part 1 专项。
- **后续顺序**：slope/stairs 稳定 → T 台阶/高台 10–20 cm → Part 1 limit_bar/bridge/high_wall 专项 → history/camera。
- **P1 gate**：不在本文件展开，见 [`training/eval-protocol.md`](training/eval-protocol.md) 与 [`training/training-plan.md`](training/training-plan.md)。

## 4. 最近验证（2026-10-22 ~ 2026-10-24）

- P0 自检：`check_plum_geometry` / `check_state_machine` / `check_part2_ability_tasks` / `part1_event_judge` / `audit_deployment` / docs checker 全部通过。
- **比赛迭代工作流落地（comp/）**：`comp/` 契约（CONTRACT.json，8+6 障碍）、评测协议草稿、诊断评测导入（3 个 `diagnostic` 行、均 0 分）、记分板 dry-run（`comp/SCOREBOARD.md`）、合规检查 PASS（45 维 actor / ±20 N·m 在 25/60 内）、审计哈希登记（`comp/audits/HASHES.json`）。**G1 judge 独立审计已完成：FAIL**（见下条）；工具在 `scripts/agent_scripts/comp_*.py`（`--self-test` 通过）。见 [`comp/STATUS.md`](../comp/STATUS.md)。
- **G1 judge 独立审计（Codex gpt-6-astra ultra，2026-10-22，新线程/只给路径）**：overall **FAIL**。头号问题：① 未验证真实跨越即成功（六类 Part1 障碍可被"空接触+出口位置"骗过，reviewer 实测 6/6 各 100）；② T 台阶把当前帧接触当历史，逐级通过被漏判；③ 斜坡方向/距离/判罚阶段错误；另有 Part1 计分不完整、Part2 低于门槛给分、attempts/暂停恢复缺失、summary↔trials 无关联、provenance 不完整。修复 P0 后重审；结论与逐项证据见 [`comp/audits/JUDGE_AUDIT.md`](../comp/audits/JUDGE_AUDIT.md)。执行者已实施工具侧修复：`comp_score` 增加 summary↔trials 证据链校验、Part2 最低门槛曲线修正、诊断导入 provenance 诚实化。
- Part 1 zero-shot 诊断：八项 0 分/0 success；限高杆已改为沿 y 穿门洞，高墙已改为沿 y 跨墙，二者仍是 fail/running；这是 baseline，不是正式分。
- 桥：blocks fail、bands running；flat 策略无桥面训练，tilt 升高；需要 P1/P2 专项。
- 训练机 GPU smoke：`black-flat`/`black-rough` 512 envs × 11 iter 分别约 7/12 s；`black-rough` 已加载 stairs/slope 地形，P1 环境可用。
- **P1 第一轮训练完成**：`black-basic-obstacle`（flat + smooth slopes + stairs，4096 envs × 1500 iter，resume from flat-ft）耗时 **1 h 11 min**，checkpoint `model_3997.pt`；terrain level 有推进但非法接触率仍高。导出 P1 policy 在 Part 1 迁移诊断：桥/限高杆改善，slope/T stairs 仍未通过，**P1 未完成**。详见 [`training/p1-basic-obstacle.md`](training/p1-basic-obstacle.md) 与 `prep.d/videos/part1_p1_basic_obstacle_contact.png`。
- **P1 第二轮续训完成**：`model_5496.pt`，1 h 11 min；训练地形 level 略升（mean≈1.62）但非法接触仍高；本地 Part 1 迁移变差（bands tilt≈38.7°、height 碰杆、T fail）。P1 **未完成**；不再盲目续训，下一步先做训练环境评估与课程/奖励调整。两轮训练共约 2 h 22 min；P1 总估 3–4 h。contact sheet：`prep.d/videos/part1_p1_cont_contact.png`。
- rl_sar 后备自检：`check_rl_sar_fallback.sh` 的 input_map/command_limit 两项均 `all checks passed`；完整 `check_walk` 未重跑（需 GUI）。
- **2026-10-24 Warp 710 根因 + 修复**：对照实验（E1 resume `model_3997`、E5 resume `model_5400` 各 100 iter 干净；probe 在 resume `model_5496` 的第一个 rollout 抓到动作在单 env 内 13→135 几何增长而 `|qvel|` 仍正常）→ 判定为动作反馈自激而非物理先爆；三项安全网后 200 iter 无 CUDA/NaN。见 [`training/training-health.md`](training/training-health.md) §7。
- **2026-10-24 `best.pt` zero-shot 评测**：契约自检通过；平地可用；Part1 0/8（诊断口径）、Part2 时间放宽后 8/20 档成功（diag 300/1300）。→ 可作 blind fallback / teacher / 对照，不可直接 fine-tune。见 [`training/him-best-zero-shot.md`](training/him-best-zero-shot.md)。
- **2026-10-24 深度相机 task**：`black-basic-obstacle-depth`（64x48 depth、forward 15° down、obs group `camera`、actor = 45 proprio + CNN latent 64、critic 不变 259）已在训练仓注册并跑通 PPO plumbing；成本 smoke 数字见 [`training/camera-depth.md`](training/camera-depth.md)。blind task 未改动，保留 fallback。
- 控制仓库 fork：`https://github.com/What410802/quadruped_control`，P0 分支 `main@f2b37dc` 已推送，未合并 upstream；部署栈取舍（rl_sar vs quadruped_control）见 [`reference/deployment-stack-comparison.md`](reference/deployment-stack-comparison.md)。

## 5. 待决 / 风险

- **Part 1 是否允许局部自动/固定动作**（规则允许、自动无加分）仍待用户确认；Part 2 已确认纯 RL。
- **judge 校准**：T 台阶逐级接触、限高杆位移、砂砾坑短边进出、桥面 step 还没有真实手动轨迹标定；当前是 P0 启发式。**G1 审计已做：FAIL（2026-10-22）**；修复 P0 并重审前，所有评测分数只是 `diagnostic`，不得用于选型或对外引用，见 [`comp/audits/JUDGE_AUDIT.md`](../comp/audits/JUDGE_AUDIT.md)、[`comp/STATUS.md`](../comp/STATUS.md) 与 [`comp/eval/_protocol.md`](../comp/eval/_protocol.md)。
- **正式整场分**：尚无官方多尝试计分；现有 0/8 只是独立障碍诊断。
- **P1 训练门槛**：数值安全、foot clearance、地形课程未验证；训练机已可用，GPU smoke 通过，进入 capability task smoke。
- **部署栈**：主栈 `quadruped_control`；`rl_sar` 保留为 P2 前保底/参考，不在 P1 并行维护；后备 runbook 见 [`reference/rl-sar-fallback.md`](reference/rl-sar-fallback.md)。
- **模型/窗口对齐**：理想 MIT 公式一致，但 control 无死区/延迟/噪声且 Black 模型默认参数/限幅不同；P2 前做 legacy-black 对齐 profile。旧自建窗口 `viewer.hpp` 可复用但需适配，P1 暂用官方 Simulate。详见 [`reference/motor-model-and-viewer.md`](reference/motor-model-and-viewer.md)。
- **控制仓库升级**：`coverMoon/quadruped_control` 是团队 fork 的上游，领先 17 commits，含 target-expiry 修复、RL 布局、测试、地图/实机计划；当前 P0 fork 可用，P1 期间不切，P2/部署前做一次受控 rebase。
- **2026-10-24 决策/风险**：C2 视觉主线先按「原始深度 -> CNN（方案 B）」做最小可用管线（直接用 mjlab 1.6 原生 2-D obs group + rsl_rl CNNModel，不引入地面平面假设；局部高度图方案 A 留作成本/学习不稳定时的备选）；相机 DR（噪声/丢帧/延迟/外参）、blind vs depth A/B、部署侧 depth 推理 wrapper 都未做，见 [`training/camera-depth.md`](training/camera-depth.md) §6。
- **数值稳定性是“已修症状”不是“已根治”**：安全网没有改 reward/课程设计，长跑前仍需 run card + 中程检查（training-health §7.6）。
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
