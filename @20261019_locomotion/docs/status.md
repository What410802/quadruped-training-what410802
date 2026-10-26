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
- **路线位置**：**P0 已完成（2026-10-22）**；**P1 数值稳定性已修（2026-10-24，见 training-health §7），P1 质量 gate 仍未过**；**C2 视觉主线已开工**：深度相机 task 已进训练仓、obs/CNN 管线、成本/100-iter smoke 见 [`training/camera-depth.md`](training/camera-depth.md)，**blind vs depth 500-iter 对照已完成**（depth 指标更好、成本 ×1.54，见同文 §7）；`best.pt` 已可进演示 GUI 手动试操作（[`training/deploy-him-best.md`](training/deploy-him-best.md)）。当前没有训练进程。
- **P0 范围**：场地/判定/手动状态机/评测/审计/演示链路闭环；P0 不包含训练。训练机已恢复（RTX 5060 Ti 16 GB），P1 开始使用。
- **主栈迁移（2026-10-24）**：用户试操作后决定把手动/演示主栈从 `quadruped_control` 迁到 **rl_sar**（已完成评估+场景适配脚本+本机验证；后续 W3–W6 见计划文档）（作业 `@20261007_assignment` 控制器 + `@20261005_ros2/sim_node`），后续深度相机也基于该线；`quadruped_control` 降为备选。迁移**不重写控制层**：已实现本任务场景的纯数据转换（`scripts/agent_scripts/make_rlsar_scene.py`，执行器顺序 FL/FR/RR/RL + 机器人可视化 group 3→1），本机验证 rl_sar 栈 7/7、本任务机器人 flat 场景 7/7、Part1 场景 `GetUp` 通过且 GUI 正常渲染。评估/改动清单/试用命令见 [`reference/rl-sar-migration-plan.md`](reference/rl-sar-migration-plan.md)。
- **控制仓库独立**：`quadruped_control` 是独立 C++/ROS 仓库；个人 fork [`What410802/quadruped_control`](https://github.com/What410802/quadruped_control) 已推送 `f2b37dc`；本地 `origin`=个人 fork、`upstream`=`N-W-wolf/quadruped_control`、`local_readonly`=原只读副本。**暂不切 coverMoon**：它比团队 fork 超前 17 个提交/190 文件，但 P1 训练不依赖控制仓库；P1 baseline 稳定后再在独立分支 rebase 到 `coverMoon/quadruped_control` 并重跑 Pixi 构建/测试。
- **当前策略**：本地训练 baseline 仍是 `flat-ft-2500`（足端 clearance 约 0.022 m，几乎拖地）；新增外部 blind baseline `best.pt`（HIMLoco，平地 cmd 0.5 实测 vx=0.36 m/s、稳定不摔；Part2 低/中档在时间放宽后 8/20 档成功，见 [`training/him-best-zero-shot.md`](training/him-best-zero-shot.md)）。两者都**不能**把 zero-shot 障碍结果当验收。


## 2. P0 完成摘要（只列验收范围）

- **Part 1**：`part1_scene.xml` 工作副本 + `Part1Judge`/`Part1EventJudge`（足端 ground、限高杆、桥、T 台阶逐级接触、砂砾/斜坡、绕杆 checkpoint）；八障碍 zero-shot 诊断与 contact sheet 已生成。
- **Part 2**：`part2_plum.xml`（PDF 参数，几何精确检查）+ `ability_field` 官方能力场本地 eval + 六类 capability eval spec（`config/part2-ability-tasks.yaml`）。
- **手动部署**：`quadruped_control` 本地 fork 用 Pixi MuJoCo 3.12/LibTorch 2.12 构建 GUI；8 状态具名键 `F/G/J/B/T/Y/U/N` 已通，policy 仍是 `flat_ft` 占位。**2026-10-24 起可试操作 `best.pt`**：控制仓库里 `assets/policies/black/obstacle/best.pt` 与作业 `best.pt` 逐字节相同，新增 `configs/policies/black/policy_switch_best.yaml` 把它设为启动策略（`--policy-switch-config` 绝对路径），顺手修了 MuJoCo 窗口不显示 group 3 机器人 geom 的问题；契约核对/构建/按键/证据见 [`training/deploy-him-best.md`](training/deploy-him-best.md)。深度策略不部署（控制栈无深度相机/CNN 推理，500-iter 质量也不够，见同文 §6）。
- **审计/演示**：`audit_deployment.py` 通过（45 维 actor、无禁用传感器、力矩合规）；演示指南 [`demo/acceptance-demo-guide.md`](demo/acceptance-demo-guide.md) 已写。
- **可视化/文档**：Part 1 judge contact sheet、Part 2 stand 视频、AI 障碍方向自检 [`reference/agent-visual-checklist.md`](reference/agent-visual-checklist.md)、Pixi 迁移记录 [`reference/quadruped-control-pixi-migration.md`](reference/quadruped-control-pixi-migration.md)。

## 3. P1 当前阶段

- **已完成**：训练仓 `black-basic-obstacle` task（flat + smooth slopes + stairs）；两轮 4096-env 训练（resume from flat-ft），各约 1 h 11 min；P1 policy 导出并做 Part 1 迁移诊断。**当前没有训练进程**。
- **2026-10-24 数值稳定性修复**：从 `model_5496` resume 的 4 次 run 在 100 iter 内崩 Warp CUDA 710；插桩定位为“坠落状态 -> 动作经 last-action 观测自激 -> 超大动作 -> NaN”，已装三项安全网（actor obs clip ±100 与部署一致、`clip_actions=±100` 与部署一致、`bad_sim_state` 极端状态终止），200-iter resume smoke 无 CUDA/NaN；详见 [`training/training-health.md`](training/training-health.md) §7。**P1 质量 gate 仍为未通过**（训练 reward 不等于通过率）。
- **当前结论**：第一轮桥/限高杆有改善，第二轮训练地形 level 略升但 Part 1 迁移退化；不能只靠续训，也不能把训练 reward 当通过率。详见 [`training/p1-basic-obstacle.md`](training/p1-basic-obstacle.md)。
- **下一步（等用户指示）**：先做训练环境评估和课程/奖励调整；再决定 P1 第三轮训练或转向 Part 1 专项。
- **2026-10-24 21:00（P0/P1 调研）**：best.pt 结构已拆（estimator 270→19 + actor 64→12）；零样本在我们的新 competition 环境 level0/1 成功率 12.5%、0 摔倒、level2/3 0%，无退化迹象但过不了桥/墙/沟/桩；热启动需复刻 HIM 结构。MuJoCo Playground 核查：代码 Apache-2.0、资产 Menagerie 许可、**不附带预训练权重**、Go1 joystick 观测 48 维/动作 12 维/action_scale 0.5/Kp35 Kd0.5；已启动本机安装与后续 Go1 训练→TorchScript 桥接。
**2026-10-24 20:35（步态/开源调研）**：实测自训策略后腿 lift 仅 3–4 mm（HIM best.pt 为 28/62 mm）→ 步态退化是核心问题，建议以 best.pt 为基座/教师；代理限高杆被抗退化补丁抬高到 0.55–0.6 m，已失真，需 terrain_type 掩码恢复；yaw/vy 800 iter 实验成功率 31.25% 但转向仍不跟随；depth 32×32×1024 训练 smoke 通过（OOM 解除）。开源调研见 `docs/reference/open-source-locomotion-survey.md`。
**2026-10-24 20:00（stage4 迁移诊断）**：已补齐诊断三问——① 训练与真实场景都有速度指令输入，但训练固定 vy=wz=0，rl_sar 实测转向不响应；② 代理 level 0/1 成功率 18.75%（仅 height_bar/slalom 会过），真实 Part2 失败 100% 为 timeout（无 fall）；③ 已生成 16 段真实/代理诊断视频并通过 rl_sar check_walk（前进可用、转向失败），部署包 `prep.d/models/rlsar_stage4/`。详见 `docs/training/stage4-migration-diagnosis.md`；这进一步确认技能缺口（桥/墙/沟/台/桩都不会爬）是迁移失败主因。
**2026-10-24 19:45（抗退化复查）**：stage4（base_height/限高杆/难度修正 + 1800 iter）平地步态恢复正常（z 0.42/tilt 6°），训练 reward 14.33，但真实 judge 仍 Part1 0/8、Part2 6s/12s 0/27 → 代理路线不足，仍建议路线 A（真实场景训练），待用户确认。
**2026-10-24 19:00（阻塞点，待用户决策）**：代理地形→真实场景迁移失败（stage3b 总 ~6800 iter 后 Part1 0/8、Part2 6s/12s 均 0/27；策略在真实场景里趴地/蹲行），depth-final 64×48×1024 触发 CUDA OOM 已停止；建议改为"用真实 Part1/Part2 场景几何训练（A）"，Part1 维持人工遥控 blind 基础策略。详见 `training/competition-terrain-and-symmetry-plan.md` §12。
**2026-10-24 18:35（能力信号+窗口敏感性）**：stage3b 中途 checkpoint 在 Part2 12 s 窗口首次出现 trench 10cm SUCCESS（6 s 窗口仍 0）；flat_ft 同窗口仍 0 → judge 灵敏度正常，但官方 Part2 每档时限未定，最终裁决需同时报 6 s/12 s。Part1 为人工遥控，其自动 judge 只作诊断。
**2026-10-24 18:00（课程修正）**：stage3 中途发现 distance-based terrain curriculum 与 goal 终止冲突，slalom/height_bar/trench/platform 停在 level 0；改为固定难度分布 rows 0–4、关闭 terrain curriculum，stage3b 从 model_3400 resume +2500 iter 重训。
**2026-10-24 17:25（竞争地形首次评测修正）**：发现本地 judge 动作裁剪 ±1 vs 训练 ±100 的 bug（已修）；竞争任务移除 illegal_contact/stuck 终止（它们阻止爬墙/穿杆等合法接触）、改为固定前进命令+goal progress 奖励、初始难度提到 2；blind-final 在 ~1930 iter 因 critic NaN 中止，已加位置检查 + obs nan guard 并 resume 完成 2500。stage3（从 2500 ckpt +2500 iter）重训进行中。
**2026-10-24 16:50（历史帧 A/B 结果）**：竞争地形 800 iter A/B 完成——单帧 45-D（reward 9.72/ep 730/illegal 0.761/goal 8.7%）优于 6 帧 270-D（8.08/640/0.954/4.7%），且部署/评测链路更简单；**决定 final 用单帧 45-D**，历史帧保留研究记录。下一步：blind-final（竞争地形 2500 iter）→ depth-final（warm-start）→ Part1/Part2 judge 裁决。
**2026-10-24 16:18（历史帧布局修正）**：发现 MjLab native history 为 term-major（非 6×45 帧块）；`symmetry.py` 的 mirror 已按 term-major 重写并验证 involutive；A/B hist 臂将在修正后启动；若 hist 胜出需在导出时重排第一层列以匹配 HIM 270 部署约定（见竞争地形计划 §8 部署注意）。
**2026-10-24 16:15（深度评测链路）**：本地 depth 评测链路已实现并 dummy-policy 端到端验证（训练仓 JIT 导出 + `ScenePolicyRunner` 深度相机 + Part1/Part2 judge `--depth`），待 blind-final/depth-final checkpoint 产出后跑真实 judge。
**2026-10-24 下午（竞争地形批次）**：已实现竞争地形代理 + 任务成功奖励 + 历史帧任务 + mirror loss 历史支持（smoke 全通过，预览视频 `prep.d/videos/competition/`、review §2.4）；历史帧 A/B（single-frame vs 6-frame，800 iter）17:10 左右出结果；后续按"历史帧结论 → blind-final 长训 → depth-final（warm-start/from-scratch）→ Part1/Part2 judge 裁决"推进。
**2026-10-24 方法论修订（用户指出）**：① 当前 flat/smooth slope/stairs 训练地形覆盖不到绕柱、桥、限高杆、高墙、砂砾、梅花桩等"深度视觉最有价值"的障碍，不能据此裁决 blind vs depth；② 当前 run 只开 foot_clearance、mirror loss=0，后腿不对称（symmetry breaking）仍在；③ 最终裁决改为"方法论拉满后的 judge 对比"，且该对比即最终模型选择（blind-final 先训、depth 用 warm-start 增量训练，避免 2× 从零）。方案与时间线见 [`training/competition-terrain-and-symmetry-plan.md`](training/competition-terrain-and-symmetry-plan.md)。当前在跑的 3000/warm-start 只作简单地形筛选。**2026-10-24 16:00 筛选收尾**：depth@3000 reward 14.86/ep 910/terrain 1.55/illegal 0.31 vs blind@3000 13.15/851/1.43/0.48（成本 ×1.59）；warm-start@3000等效 12.83/846 ≈ blind@3000、低于 depth-from-scratch（warm-start 不保证更好，竞争地形批次需对照）；结果归档 `prep.d/results/screening_simple_terrain_3000.json` 与 review §2.3。方法论弹药库（已用/已验证、仓库已实现未启用、需引入的论文方法、以及"完成时间奖励"分析）见 [`training/methodology-inventory.md`](training/methodology-inventory.md)。另做小修：DR 的 push 从固定 16 s 改为 per-env 随机 6–20 s（避免策略学到扰动日程、且 16 s 固定间隔在 20 s episode 内只有同相位一次）。
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
- **2026-10-26 无GPU修复/审查决策**：gate 增加 `--check-config-only` 预检与 `gate_pass/success_rate`，修正文档假 smoke；job14 trap/verdict 加固。确定不做全仓无差别审查，改为下一轮长训前完成 HIM 主链路关键合同审查（范围见 plan.md §8）。用户方案“row0逐档 + trench30/plum后期depth”方向批准，但要求 per-category gate 与奖励单变量。
- **2026-10-26 计划看板**：新增 [`plan.md`](plan.md)，记录 P0/P1/P2 待办、HIM gate 假测量修复、job12 发散结论与队列 job13/14。后续进度先更新该文件。
- **2026-10-26 row0 队列已提交**：HIM row0 mixed train+gate job `him_row0_mixed_gate_20261026_...` 已提交 task-spooler，位于队列 ID12（当前 PPO job11 运行中，完成后自动执行）；训练 512env×96step×1500iter，随后对 platform/slope/stairs/high_wall/trench 各跑20次 gate。
- **2026-10-26 防护+gate 落地**：HIM 加 reward/return clamp、HIMPPO/estimator 非有限 loss 跳过、policy log_std sanitize、terminal target nan_to_num、estimator_velocity sanitize、nonfinite_state 加 sensordata；新增 `him_part2_gate.py` 和 `BLACKW_MAX_ROW` 手动 row gate。guard/gate smoke 通过；未改原始地形。
- **2026-10-25 最低档 gate/课程计划**：当前 competition/mixed 已 pop 掉 native `terrain_levels`，不是 success-gated curriculum；高档只能 resume + 手动 max_init row。已写 `training/him-part2-gate-curriculum-plan.md`：除plum外每类最低档20/20并对真实三轴指令/初始随机化测试，高档只改参数，gate通过再升档。明天优先 row0 五类 gate，再决定训练。
- **2026-10-25 单卡队列**：确认分半并行不如串行全显存；已用户级安装 task-spooler (`~/.local/bin/ts`, `TS_SOCKET=/tmp/gpu_queue.socket`)，计划 slot=1 + job 内 flock/VRAM 等待，一次只跑 HIM 或 PPO。Slurm 单机不必要。明天按串行全显存启动。
- **2026-10-25 圆角撤销/issue核对/8GB协议**：圆角已撤销恢复官方地形；HIM 代码审计未发现不可微自定义算子，但 mjlab #870/#912/#918、mujoco_warp #930、Newton #3702 均报告过 NaN/device assert，不能只归因 MuJoCo。HIM 512 env 预计5–6GB（8GB内可行），1024 rm约9GB+不可行；计划 512×96×3000≈147M steps，明天按8GB协议启动。
- **2026-10-25 1mm圆角 A/B**：高台8条外棱改1mm圆角后，128 env 完整300 iter无NaN、256 env50 iter无NaN；但512 env（solo step453）和1024 env（solo step5164）仍NaN。说明1mm圆角有帮助但不足以消除；新录像在 prep.d/videos/nan_debug/。按用户规则下一步考虑防护。详见 [`training/nan-video-diagnosis.md`](training/nan-video-diagnosis.md)。
- **2026-10-25 NaN 录像诊断**：已从 NanGuard dump 还原 1024/512/256/128 四个配置最后100个finite state的视频，位于 `prep.d/videos/nan_debug/`；四者都停在平台边缘/前轮接触瞬间，下一 step/更新出现 NaN。确认 `normal std>=0`→CUDA assert→Warp710 签名一致；`nonfinite_state` 未含 sensordata，HIM 缺 reward/loss/terminal guard。日志顺序不能证明 sim NaN 先于 std NaN，需 CUDA_LAUNCH_BLOCKING probe。按要求本次未修复。详见 [`training/nan-video-diagnosis.md`](training/nan-video-diagnosis.md)。
- **2026-10-25 HIM 死代码修正（重要）**：确认并修复 (1) exact sub-terrain key 为 "exact" 导致 part2_success/failure/clear 恒 False；(2) BlackWHimOfficialRunner warm-start 被放在 save return 后，strict platform 实际从零训练；(3) low_base_height=0.55 误杀 z≈0.51 的 teacher；(4) part2_clear 25→200。修正后 teacher no-update precheck 出现 non-zero part2_success/part2_clear，128 env pilot 也保持 success 信号。此前“HIM strict=0=学不会”的结论作废；但 256/512/1024 仍 Warp assert，1024 队列已禁用，需先修 contact/NaN reset。
- **2026-10-25 训练预算/排队**：调研 N-W(4096×64×1000≈262M)、HYNova(2048×24×6800≈334M) 与 env/step/iter 关系；此前 HIM 只有0.8–2.6M步，差100倍。已决定正式 pilot 为 platform exact strict、1024 env×64 step×3000 iter≈196M，lr5e-4/entropy3e-3，先前向窄命令后扩wide。远程无正式队列，已部署 `~/rc_work/queue_blackw_platform_1024.sh` 等外部训练退出且显存<2.5GB后自动启动。详见 [`training/training-budget-and-recipes.md`](training/training-budget-and-recipes.md)。
- **2026-10-25 strict platform-only**：`blackw-platform-exact-him` 改用四轮 part2_success/failure/clear 后，64 envs 200 iter 完整跑完，但 part2_success=0、platform_height≈0，说明平台不是判据假成功，而是确实没学会四轮上台；nefc43/overflow0/nonfinite0，无 Warp assert。下一步平台课程/contact reward 或 teacher 蒸馏。
- **2026-10-25 strict Part2 移植**：已把对方只读 recipe 中的 `part2_success/failure/clear`（四轮支撑面 + trench wheel-drop）移植到 HIM official mixed，替换 x-only goal；同时补 official trench/stairs/plum 几何。32 envs×20 iter strict smoke 通过，`part2_*` 项正常出现、nefc32/overflow0/nonfinite0、无 Warp assert；strict success 仍0（预期）。下一步 64/128 envs 分项训练验证。
- **2026-10-25 跨 Agent 对比**：只读查看 `~/rc_work/part2_team_race`：对方实际是 PPO+BC 初始化 + official mixed terrain + `part2_success/failure/clear` 四轮判据 + 2ms/10decimation，已有 goal 信号；BeamDojo 代码尚未出现。关键可借鉴：judge-aligned 四轮成功/失败项、official trench(plateau/ramp)/stairs(up+down)/plum 几何、BC/DAgger 蒸馏、分项日志。详见 [`training/cross-agent-comparison.md`](training/cross-agent-comparison.md)。
- **2026-10-25 HIM mixed resume64**：从 model_200 以64 envs resume 到319 iter，`competition_goal_reached`≈0.33–0.50，progress最高0.97，climb≈0.01–0.03；信号可重复但仍非严格 judge，且仍 Warp assert（nan dump 17:55:24）。checkpoint model_300。下一步修 invalid-state reset 后再长训。
- **2026-10-25 HIM official mixed goal 信号**：官方五类 exact 地形 + goal/progress/climb 奖励，128 envs 跑到229 iter（随后 Warp assert），`competition_goal_reached` 终止占比约0.19–0.33，mean reward≈15；climb_height仅0.01。nan_guard 在 step58881 抓到 env8 NaN。checkpoint model_200 已保存；这是 HIM 首次 mixed goal 信号，但不能直接当高台/斜坡/沟壑 judge 通过。
- **2026-10-25 HIM 诊断归档**：三个 HIM 平台诊断脚本已归档到 `scripts/agent_scripts/him_diagnostics/` 并写入复现命令；`check_him_policy_equiv` 的 env-history 对拍为 `max_abs_diff=0.0`，官方 warm-start platform rollout 仍 crouch（z≈0.69→0.51），说明权重映射正确但平台技能/执行层还有问题。
- **2026-10-25 climb pilot**：平台 HIM 加 `climb_height`（root_z-0.55）后 128 envs 600 iter，reward≈26、climb≈0.4–0.5，但 official_platform_success仍0、platform_height≈0；climb 奖励数值不能当成功。外部 Agent 的 PPO/BC official mixed 有 goal success .22–.35，可作为奖励/地形参照。训练已停、flag=0。
- **2026-10-25 guardrail smoke**：三轴命令 + nan_guard + wrapper action guard + CCD-off，128 envs 300 iter 完整跑完，nefc峰值~38、overflow=0、nonfinite=0、max|action|~5.0；无 CUDA assert。但 easy platform 的 official success 仍为0；2000 iter 到413仍0，已停。数值稳定性和平台技能仍是两件事。
- **2026-10-25 指令/数值防护**：平台 HIM 命令已改为 vx0–1、vy±0.3、wz±1、4–6s 重采样，stop/turn/组合都采样；启用 `sim.nan_guard`，wrapper 层动作 `nan_to_num+clamp`，save 时打印 nefc/overflow/nonfinite/max|action|。同时修 blackW base_height target 0.43→0.69。30 iter smoke 全部有限，overflow=0。
- **2026-10-25 平台诊断**：修复 blackW `base_height_target` 0.43→0.69（此前策略被奖励成蹲伏）；给平台任务加直线 command、low-base 终止、platform_jump 奖励。HIM 权重映射在 env obs 上 `max_abs_diff=0.0`，但官方 warm-start rollout 仍蹲伏/后移，`official_platform_success=0`；说明 action/部署语义仍有差异。训练已停、flag=0，下一步核对 forward/yaw 与 wheel/leg 符号。
- **2026-10-25 HIM NaN guard/小批次**：给 wheel-leg action 加 `nan_to_num` 后，CCD-on 64 envs HIM platform 300 iter 稳定完成；之前 residual Warp assert 至少部分来自非有限动作。微平台 1–3cm、5–10cm easy 均无 `official_platform_success`，progress 到平台附近但 root 不抬升；下一步是平台接触/高度判据与课程，不是继续加 iter。外部 depth-vision Agent 仍占用 GPU，本训练已停、flag=0。
- **2026-10-25 速度指令澄清**：当前训练用 body-frame `[vx,vy,wz]` 3 维速度指令（competition HIM 固定 vx0.4–1.0、vy±0.3、wz±1、10s 重采样），无 `vz`；官方/HYNova/N-W-wolf 也没有 vz 指令，垂直抬升应由地形/奖励/height skill mode 隐式学。加 vz 会改观测/动作/热启动/部署 contract，暂不做。
- **2026-10-25 HIM pilot 继续**：补上 exact task 的 `flat_patch_sampling` 后出现 76% x-goal，但 CCD-off 下 x-only 会把穿模/绕行误判成功；已改为 official success（x 在平台范围且 base z≥0.72），并去掉 x-only goal。512 envs + warm-start 在 official success 下跑 100 iter 稳定，继续 resume 到 321/599 再次 Warp assert；真实平台成功仍 0。已新增官方 slope/trench/wall/stairs exact 类和 `blackw-official-him` task smoke。下一步仍是 residual assert + 平台爬升奖励/课程。
- **2026-10-25 HIM 接入 pilot**：blackW HIM task 已注册；官方 `.pt` actor/source estimator warm-start 已验证 1-iter smoke 可加载。发现 Mujoco-Warp cylinder-box CCD assert；`cfg.sim.ccd_iterations=0` 后 256 envs 平台 HIM 150 iter 稳定。512 envs + official warm-start 跑到 294/300 才再次 assert，reward ~15 但 platform goal/height 仍为 0（未爬上 10–16cm）。当前先停 GPU、flag=0；下一步用 residual assert 定位 + 平台奖励/课程，不直接长训。
- **2026-10-25 官方 .pt 热启动验证 PASS**：官方 `Obstacle_Jun26_12-30-56_.pt` 的 14 个 actor/source-estimator tensor 与 MjLab `HIMPolicy`（57×6、76 actor input、19 estimator output）shape 完全匹配；仅 target encoder/prototypes（训练专用）缺失；随机 1×342 canonical history 输出 `max_abs_diff=0.0`。结论：可从官方 HIM actor/estimator 热启动，critic/target encoder 随机初始化后续训。详见 [`training/blackw-architecture-decision.md`](training/blackw-architecture-decision.md)。
- **2026-10-25 参考配方盘点**：找到 N-W-wolf `super-dog` 的 **blackW HIMLoco/Isaac Gym 完整训练配方**（4096 envs、64 steps、1000 iter、HIMOnPolicyRunner/HIMPPO/HIMActorCritic、16 关节/342 观测/16 动作）和 HYNova `RC_WheelLeg` 的 MjLab HIM 配方；官方 blackW `.pt` 正是 HIM exporter。N-W-wolf super-dog 最接近“换地形再训”，但其中没有 Part2 的 platform/trench/plum 地形且需 Isaac Gym；MjLab 路线可复用 HYNova/N-W-wolf 的 HIM 代码。详见 [`training/reference-recipes.md`](training/reference-recipes.md)。
- **2026-10-25 架构决策**：确认当前 `PPO+342-D MLP` 只是继承自 Black/MjLab 的初步 baseline；官方 blackW 是 HIM（estimator+actor），HYNova 16DOF 比赛版也用 HIM + 20k iter，我们的训练规模/结构/地形均不对标。决定移植 HIM（优先参考 MIT 的 `zeitvex/RC_WheelLeg`）+ 官方逐档 geometry + success-gated 课程；同时去掉训练地形中官方不存在的蓝色物理侧墙，只保留 lane 判罚。详见 [`training/blackw-architecture-decision.md`](training/blackw-architecture-decision.md)。
- **2026-10-25 official platform pilot**：按官方 `map.xml` 几何重做 single-block 1.5×1.6 m 高台，从我们自己的 high model_600 warm-start 300 iter，`competition_goal_reached=0`、平台高度奖励 0，未爬上 10–16cm；rollout 视频 `prep.d/videos/blackw_official_pilot/official_platform_pilot.mp4`。结论：300 iter warm-start 不足以适配官方几何，不能据此判不可训练；下一步先做低档 success-gated 课程/更长 pilot，不再刷 proxy。训练后 GPU flag=0、GPU idle。
- **2026-10-25 terrain 审计：暂停训练**：确认 proxy/本地 level XML 不是官方能力场复制品；high_platform 平台尺寸/无辅助台阶、high_wall 40cm 缺失、slope 水平长与升高、stairs 总高、trench 深度/通道、height_bar 杆底高度均有实质差异，详见 [`training/part2-terrain-audit.md`](training/part2-terrain-audit.md)。此前 proxy 训练 success 不能作为官方通过证据；待按官方 `map.xml`+`labels` 重建训练/评测地形并加 success-gated 课程后再开 GPU。
- **2026-10-25 blackW 训练链路打通**：远程训练仓接入 blackW（16 关节、混合轮腿 action、57×6=342 actor observation、16 action），完成 `blackw-flat`/`blackw-competition` smoke 与两次 competition 训练；严格 Part2 judge 下按类别选最优约 **750/1300**（high_platform 30cm/100、stairs 30cm/200、slope 35°/100、high_wall 40cm/200、trench 20cm/150），高台 40cm / 斜坡 45° / 沟壑 30cm / 梅花桩仍缺。新策略已放入 `@20261024_blackw`（`comp_high600`/`comp_lane300`）；训练结束 GPU flag 已置 0、GPU idle。追加的 platform-only specialist 仍是 proxy success / 外部 0；随后又接入 actual Part2 几何的 exact platform/slope 任务（无 helper step，nconmax/njmax 已调大），训练 400 iter 仍 goal=0；再降初始地形行到 easy 重训也仍为 0，说明需要先改训练信号（高度/平台接触奖励）或做官方策略蒸馏，而不是继续加 iter。remote GPU 已停、flag=0、GPU idle。详见 [`training/blackw-training-runs.md`](training/blackw-training-runs.md) 与 [`training/blackw-strict-baseline-and-training-plan.md`](training/blackw-strict-baseline-and-training-plan.md)。
- **2026-10-24（夜间）blackW 部署/评测新进展**：`@20261024_blackw` 独立工作区完成 blackW 16 关节 rl_sar 适配、Part1/Part2 场景接入、运行时策略切换、Part1 出生点修正（21/21 无初始穿透）；为 Part1 接入官方 `low_bar_drive`/`bridge_drive`/`car_drive` 固定动作并用 ROS `/joy` 无头测试（lowbar 穿过、bridge 到对侧）。Part2 出生点改用 blackW `spawn`、gap judge 加严（沟底接触/绕过 lane 判负）后重跑三份官方策略：strict baseline obstacle 500/stair 400/flat 210，跨策略最佳约 **650/1300**；详细结果见 [`training/blackw-strict-baseline-and-training-plan.md`](training/blackw-strict-baseline-and-training-plan.md)。远程训练机当前离线，blackW 训练仓接入/训练待远程恢复。
- **2026-10-24 Warp 710 根因 + 修复**：对照实验（E1 resume `model_3997`、E5 resume `model_5400` 各 100 iter 干净；probe 在 resume `model_5496` 的第一个 rollout 抓到动作在单 env 内 13→135 几何增长而 `|qvel|` 仍正常）→ 判定为动作反馈自激而非物理先爆；三项安全网后 200 iter 无 CUDA/NaN。见 [`training/training-health.md`](training/training-health.md) §7。
- **2026-10-24 `best.pt` zero-shot 评测**：契约自检通过；平地可用；Part1 0/8（诊断口径）、Part2 时间放宽后 8/20 档成功（diag 300/1300）。→ 可作 blind fallback / teacher / 对照，不可直接 fine-tune。见 [`training/him-best-zero-shot.md`](training/him-best-zero-shot.md)。
- **2026-10-24 深度相机 task**：`black-basic-obstacle-depth`（64x48 depth、forward 15° down、obs group `camera`、actor = 45 proprio + CNN latent 64、critic 不变 259）已在训练仓注册并跑通 PPO plumbing；成本 smoke 数字见 [`training/camera-depth.md`](training/camera-depth.md)。blind task 未改动，保留 fallback。
- **2026-10-24 可视化**：`best.pt` zero-shot 评测过程已录 28 段视频（Part1 8 障碍独立起点 + Part2 20 档），索引 `prep.d/videos/him_best/index.html`；blind vs depth 对照已续训到 **1500 iter**（500 后各 +1000）：depth 仍全面略好（reward +10%、episode +3%、terrain +9%、非法接触 −16%）但优势比 500 iter 时大幅缩小，成本 ×1.56、blind 算力效率更高（结论与后续改进建议见 [`training/camera-depth.md`](training/camera-depth.md) §7.1/§10）；策略 rollout 视频、曲线与指标在 `prep.d/videos/review_20261024.html`。**3000-iter 长训已启动**（两臂 resume +1500，预计约 80 min，见 §11），**depth warm-start 已实现并 smoke 通过**（从 blind 1500 checkpoint 初始化、CNN latent 列置零、command curriculum range 恢复；`BLACK_DEPTH_WARM_START` 环境变量入口），3000 跑完自动续跑 warm-start 臂（§12）。
- **2026-10-24 best.pt 进 GUI**：手动演示环境已验证 `GetUp → Running → 行走`（Part1 场地），试操作命令与截图见 [`training/deploy-him-best.md`](training/deploy-him-best.md)；截图 `prep.d/videos/demo_himloco/`。
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
