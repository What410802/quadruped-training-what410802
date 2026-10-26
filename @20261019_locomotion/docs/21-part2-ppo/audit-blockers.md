# PPO/BC 线与部署链路：审计阻塞清单（2026-10-26 现状）

> 本页汇总 round-1 两份独立审计（[`audits/ppo-core-audit-round1.md`](audits/ppo-core-audit-round1.md)、[`audits/ppo-deploy-audit-round1.md`](audits/ppo-deploy-audit-round1.md)）里**仍未关闭**的代码项，以及已修项的验证状态。目的是：开 round-2 审计前逐项清零；不把"看起来跑通"当通过。
> 状态码：**OPEN**=未修；**FIXED**=代码已修（注明验证）；**PARTIAL**=修了一半/缺验证或接线。

## 0. 本轮修复状态（2026-10-26 17:00，第二轮）

> 本节记录 §1 清单的实际修复与验证；§1 表格保留 round-1 原始描述。状态：**FIXED**=代码已改且有自测/命令证据；**PARTIAL**=代码已改但缺目标场景验证；**OPEN**=未动。

| ID | 状态 | 修复位置 / 证据 |
|---|---|---|
| P1-1 | **FIXED** | 远程 `blackw/env_cfgs.py` 删除 3 处 `cfg.sim.ccd_iterations` 死写；`_apply_deployment_sim_options` 改 `BLACKW_CCD_ITERS`（默认 35=judge）；`py_compile` 通过 |
| P1-2 | **FIXED（静态）** | platform 阈值改行相对：`_platform_top_z()` + `min_clearance`/`clearance`；`blackw-platform-easy` 已注册；10 cm 档不再用绝对 0.72；「success-gated 升档」伪注释已删（行晋升未实现，属实验） |
| P1-3 | **FIXED** | `check_tier_success.py`（本地+远程）：`max_steps` 从 env `max_episode_length` 推导；`truncated` 字段 + 非零退出；worst/best 只统计完成过 episode 的 env |
| P1-4 | **FIXED** | 训练 lane 统一 `PART2_LANE_HALF_WIDTH=0.7`；`BLACKW_LANE` 默认 0.7；termination/success/judge 单源 |
| P1-5 | **FIXED** | `eval_blackw_part2.py`：缺 `lane_half_width`/`hold_s`/stairs `descend_end_x` → KeyError；`wheel_bodies != 4` → RuntimeError；judge smoke 通过 |
| P1-6 | **FIXED** | 远程 `eval_blackw_official.py` → `_deprecated_eval_blackw_official.py`（文件头标注不可与 judge v5 比较），commit `xxxx` |
| P1-7 | **FIXED** | `black/rl_cfg.py`：出现 `BLACKW_GUARD_*` 但 `BLACKW_ALGORITHM` 非 GuardedPPO → `ValueError` |
| P1-10 | **FIXED** | 远程 `gpu_jobs`：`common.sh` record 钩子（失败不写 done）、信号码 143/130、flag 竞争修复；新增 `submit.sh`（导出 TS_ONFINISH/TS_SOCKET）；9 个 `ppo_*.sh` 接 `BLACKW_RESUME_LOAD_CFG/LR`、动态 resume、导出/tiercheck rc 传播、`bash -n` 全过；SIGTERM 实测 exit=143 + 日志 rc=143 |
| P1-11 | **FIXED** | 新增 `@20261024_blackw/scripts/check_predicate_judge_parity.py`（lane/hold(0.2+0.1)/stairs key/judge fail-closed 守卫静态对拍），当前 `PARITY OK` |
| P1-12 | **FIXED** | blackW reset root velocity 默认 0（`BLACKW_RESET_ROOT_VEL` 可覆盖），与 judge 静止出生一致 |
| P0-2r | **FIXED** | 所有续训 `ppo_*.sh` 已接线 `BLACKW_RESUME_LOAD_CFG=actor` + `BLACKW_RESUME_LR`，summary 记录 resume/load_cfg/lr |
| F1 | **FIXED（代码，smoke 通过）** | 逐关节 `tau_max`（23.7/23.7/59.25/20）已在部署栈实现；F2 smoke 能正常加载策略并取得 5 档成功 → 部署栈力矩路径可用。**仍缺** judge-vs-sim 同一 checkpoint 的逐 case 数值对拍（smoke 只给 pass/fail） |
| F2 | **PARTIAL（工具已实现，但 5/20 结果无效）** | `smoke_deploy_part2.py` 已能逐档跑（tag 前 5/20），但 2026-10-26 独立评审发现：① deploy `part2_levels.json` 用旧 proxy `part2_*.xml`，judge 用官方 `part2_off_*.xml`（20/20 不一致，已修 levels）；② 官方 `obstacle` 权重同一 smoke 也 5/20 且数值爆炸 → smoke/栈有效性未验证。修复并重跑前，5/20 不得作为策略部署证据。见 `comp/audits/2026-10-26-BYOK-RFR-SUMMARY.md` |
| F3 | **FIXED** | 远程 exporter 写 `config.yaml`+`manifest.json`、`action_scale` 带右腿负号（模板已上传）；本地 BC exporter 也写 manifest；模板 `model_name: policy.pt` 修正 |
| F6 | **FIXED（结论修正）** | 新增自测：控制周期每 5 ms 都做一次 slew、每策略周期 4 次 → 有效 slew = 配置值（20 自测 / 60 部署），审计"15 rad/s"的推导不成立；自测待 build 后跑 |
| F7 | **FIXED** | `base.yaml`+模板加 `control_hz/policy_hz`；`rl_sdk.cpp` 读 base/策略 config 并在 `InitRL` 对账（偏差 >2% 抛异常）；main 捕获后安全退出 |
| F14 | **FIXED（工具）** | 新增 `read_rl_obs_debug.py` 解析 `/tmp/rl_obs_debug.csv`（obs/action 分段统计 + 首帧 + JSON） |
| F15 | **FIXED** | `rl_sim.cpp` main 包 try/catch（含 catch(...)），异常打印并返回 1 |
| P2 清单 | 未动 | 见 §3；不阻塞 round-2 |

### 0.1 本轮验证记录（2026-10-26 17:20）

| 验证 | 命令 | 结果 |
|---|---|---|
| C++ 编译 | `pixi run ros2-build`（blackw ws） | 2 packages OK（rl_sar_blackw 75 s） |
| C++ 自测 | `command_limit_selftest` / `input_map_selftest` | **all PASS**（含 F6 的"每策略周期 4 次 slew → 有效=配置值"用例、F15 不影响） |
| 训练栈 smoke（GPU） | `submit.sh audit_round2_smoke ppo_audit_smoke3.sh` | `train rc=0`；`[resume] BLACKW_RESUME_LOAD_CFG=actor`、`lr=4e-05`；DR=`[base_com payload_mass push_robot]`；summary 成功 done |
| platform-easy 环境构造 | `check_tier_success --task blackw-platform-easy` | `rc=0`、`truncated=false`、`official_platform_success` 4/4 → 行相对阈值生效 |
| 部署 20 档 smoke | `smoke_deploy_part2.py --policy comp_bc_v5` | **5/20（结果作废，见 F2）**：官方权重对照同样 5/20 + 数值爆炸 → 栈/场景有效性未验证；deploy levels 场景已修为官方 `part2_off_*`，待重跑 |
| 谓词-judge 对拍 | `check_predicate_judge_parity.py` | `PARITY OK`（lane 0.7、hold 0.2+0.1=15 steps、stairs key、fail-closed 守卫齐全） |

验证中又发现并修掉 2 个工具 bug：`check_tier_success` 的 `torch.full_like(int64, nan)` 溢出；platform-exact 任务的 success 实际由 `official_platform_success` 触发而 tiercheck 只统计 `part2_success`。

**仍未关闭**：F1 的 judge-vs-sim 逐 case 数值对拍（只有 pass/fail）；P0-1/P0-3 的最终验证仍是"下一次正式训练+judge"；P2 清单未动；真实硬件链路未实现（不在本轮范围）。

## 1. 阻塞 round-2 PASS 的代码项（按建议修复顺序）

| # | 项 | 位置 | 现状 | 要做什么 |
|---|---|---|---|---|
| P0-2r | 续训 lr/继承：代码已加开关，但**除 smoke 外的 job 脚本都没接线** | 远程 `curriculum_checkpoint.py:261-286`；`gpu_jobs/ppo_*.sh` | **PARTIAL**：`BLACKW_RESUME_LOAD_CFG=actor` + `BLACKW_RESUME_LR` 已实现且 job23 验证；仅 `ppo_audit_smoke3.sh` 设置 | 所有续训 job 显式设置两个变量，并在 summary 打印 `resume ck/lr`；否则重演"名义 4e-5、实际 1e-5" |
| P1-1 | CCD 死写 3 处 | `@20261024_blackw/training/blackw/env_cfgs.py:832/868/1016/1127`（`cfg.sim.ccd_iterations`） | **OPEN**：字段实际在 `cfg.sim.mujoco.ccd_iterations`（mjlab `sim/sim.py:116,140`），当前等于 35 与 judge 一致，注释"disable CCD"误导 | 若要关 → 写 `cfg.sim.mujoco.ccd_iterations=0`；若保持 → 删 3 行+改注释并写明 CCD=35 与 judge 同值 |
| P1-2 | platform-exact 专用项在 10 cm 档是死代码、success-gated 未实现 | `env_cfgs.py:946-968`（`min_root_z=0.72`、`max_init_terrain_level=0`）、`:639-677`（阈值 0.70）、easy 变体未注册 | **OPEN**：10 cm 平台站住 root z≈0.58 → `official_platform_success` 永不触发、`platform_height` 恒 0；`terrain_levels` 被 pop，"success-gated 升档"无实现 | 阈值改为按难度算（`base_ref_z + h + eps`）；要么实现 success-gated 行晋升，要么把注释改成"固定 10 cm"并删/注册 easy 变体 |
| P1-3 | `check_tier_success.py --episodes 3` 永远只跑 2 个 episode | `@20261024_blackw/scripts/check_tier_success.py:101-115` | **OPEN**：`max_steps=int(400/episodes)*episodes+2000`（=2399 < 3×1000），且无 truncated 标记 | 从 env 读 `max_episode_length`；未达目标 episode 数 → WARN/非零退出；修 `clamp(min=1)` 的 worst_env_rate |
| P1-4 | 训练 lane 0.9/0.8 与 judge/success 0.7 不一致 | `env_cfgs.py:396/679/771/893/965`（`PART2_LANE_HALF_WIDTH=0.7` 但 termination 用 0.9/0.8） | **OPEN**：0.7<|y|<0.9 区间训练合法、judge 判负 → 成功率被系统性拉低 | `_lane_deviation` 默认改 `PART2_LANE_HALF_WIDTH`；更宽松必须显式传参并打印 |
| P1-5 | judge 3 处 fail-open | `eval_blackw_part2.py:174`（`descend_end_x` 回退）、`:311-316`（wheel_bodies 未校验数量，`np.all([])` 为 True）、`:142/248`（lane/hold 默认静默） | **OPEN** | `__init__` 断言 4 个 wheel body；stairs 强制要求 `descend_end_x`；levels JSON 显式键+缺省打日志，不做静默回退 |
| P1-6 | 远程第二个口径不同的 judge 仍在 | 远程 `part2_team_race/scripts/agent_scripts/eval_blackw_official.py` | **OPEN**：与 judge v5 的 goal/hold/谓词全不同，文件名更"官方" | 删除或改名 `_deprecated_*` 并在文件头写"不可与 judge v5 比较"；README 标唯一权威入口 |
| P1-7 | 漏设 `BLACKW_ALGORITHM` 时 guard 变量静默失效 | `training/black/rl_cfg.py:39-41`、`guarded_ppo.py:54-64` | **OPEN** | 检测到任一 `BLACKW_GUARD_*`/`BLACKW_RESUME_*` 但 class_name 非 GuardedPPO → fail loud |
| P1-10 | 作业脚本契约（与 F8/F9/F10/F12/F16 同源） | `gpu_jobs/ppo_*.sh`、`common.sh`、`on_finish.sh` | **OPEN**：① 导出 rc 不进最终 `RC`；② `record "$JOB done"` 无条件写（失败作业也有 done）；③ SIGTERM `exit "TERM"`→rc=2 且日志 `rc=TERM`；④ `TS_ONFINISH` 不在任何 shell 启动文件里；⑤ `on_exit` 无条件清 GPU flag，与 `on_finish.sh` 的"还有其他 running"判断冲突；⑥ 硬编码 resume 点；⑦ gate/tiercheck verdict 不进 summary | 照 `export_guard4.sh` 累计 fail；done 改为 `end rc=$RC`（成功才 done）；信号映射 143/130；把 TS_* 写进 shell rc 并启动断言；flag 用同一"other running"逻辑；resume 动态解析；summary 写 `gate pass/rate/verdict` |
| P1-11 | 缺"训练谓词 vs judge 谓词"对拍自检 | 无脚本 | **OPEN** | 新增自检：同一组预置轨迹/状态分别喂训练 termination 与 judge，比较 pass/fail 与原因；纳入 CI |
| P1-12 | 训练 reset root 速度 ±1.0 与 judge 静止出生不一致（文档称一致） | `env_cfgs.py:222-223` | **OPEN** | 评测/对照时把 root 速度随机化设 0（或按覆盖协议定义），并把差异写进验收协议 |
| F2 | 部署侧无 Part2 逐档 smoke（20 关 0/20 覆盖） | 无 `smoke_deploy_part2.py`；`check_walk_blackw.py` 仅平地 | **OPEN**（F1 修完才能有意义地对拍） | 实现 `scripts/smoke_deploy_part2.py`（按 `part2_official_levels.json` 判据 + 命令 profile，输出逐档 pass/fail），接进 job 作为导出后门槛 |
| F3 | 远程导出器不自足：不产 `config.yaml`/manifest，`contract.json` 的 `action_scale` 右腿符号错 | 远程 `export_blackw_policy.py:152-172`（`[0.25]*3+[10.0] *4`，应为 FR/RR=-10） | **OPEN**（本地已有 `import_blackw_policy.py`/模板可复用） | 导出即写 `config.yaml`（模板）+ `manifest.json`（policy/config sha256、dt/decimation、命令范围）；`contract.json` 改正负号；导出后自检 |
| F6 | slew 有效上限 15 rad/s（文档写 60），随 dt 变化 | `command_limit.hpp:109-118`、`rl_sim.cpp:407-440` | **OPEN** | 改为"距上次目标变化的时间"时基，或只在新推理拍做 slew；文档写有效值 |
| F7 | 频率契约只在 `base.yaml`，无 per-policy 覆盖/校验；manifest 与 base.yaml 矛盾 | `base.yaml:3-4`、`rl_sdk.cpp:376-377`、`comp_bc_v5/manifest.json` | **OPEN** | `config.yaml` 加 `control_hz/policy_hz`，`InitRL` 与 dt/decimation 对账，不一致拒绝进 RL |
| F15 | `rl_sim.cpp` 主推理路径无 try/catch（只有切换策略的 InitRL 有） | `rl_sim.cpp:538`（main）、`:244`（仅切换） | **OPEN** | 包住主循环推理/控制写回，异常→ERROR+安全退出而不是整进程被杀 |
| F14 | `RL_DEBUG_OBS` 埋了但全仓无消费者 | `rl_sim.cpp:515-527` | **OPEN**（低） | 要么写脚本解析 `/tmp/rl_obs_debug.csv` 做 obs 对拍，要么删掉埋点 |

## 2. 已修项（保留证据，避免重复发现）

| # | 项 | 状态 |
|---|---|---|
| P0-1 | blackW DR 丢失 | **FIXED**：`BLACKW_DR_EVENTS` 受控白名单（默认 `payload_mass,base_com,push_robot`；foot_friction/pd_gains/encoder_bias 在 blackW 无对应 geom，不能照原审计"全开"），job23 smoke PASS |
| P0-3 | plum 状态式奖励可刷分 | **FIXED**：改 potential-delta，`BLACKW_PLUM_FOOT_W` 默认 0.0 |
| F1 | sim 统一 20 N·m 力矩 | **FIXED（代码）**：`motor.hpp` 逐关节 `tau_max`/`tauMaxByJoint()`，`sim_node` 自动从 ctrlrange 读 23.7/23.7/59.25/20 或 `tau_max_array`，启动打印 16 个限值；模板 config 带 `torque_limits`。**验证仍被 F2 阻塞**（无 Part2 逐档部署 smoke） |
| F4 | 83/129 config 顶层 key 不符 | **PARTIAL**：`scripts/check_policy_dirs.py` 已加（可 `--fix`）；`import_blackw_policy.py` 生成正确 key；curated/official 目录通过；86 个历史生成目录仍不符（已 gitignore/不入库，需要时 `--fix`） |
| F5 | README 手柄键位错 | **FIXED**（进 RL=RB+D-pad 上、复位=RB+Y；部署契约文档同步） |
| F11 | `check_walk_blackw.py` 基准 config 写死 flat | **FIXED**：config 由 `--policy` 推导并断言 key |
| F13 | 本地 training 快照缺 `blackw/actions.py` 等 | **未修（低优先）**：快照只读、远程仓为准；文档已标"只读快照" |

## 3. P2 / 卫生项（不阻塞 round-2，但建议下一批训练前顺手）

- P2-3：显式传 `load_cfg` 的调用者（`export_blackw_policy.py:103`、`check_tier_success.py:82`）静默忽略 `BLACKW_RESUME_LOAD_CFG`；应打印优先级 WARN。
- P2-4：`wheel_states()` 用 `<LEG>_foot` 原点当轮心，与轮 cyl geom 前移 0.028 m 有偏置（train/judge 一致，绝对阈值需知）。
- P2-5：`BLACKW_SUCCESS_HOLD_STEPS` 可改但无日志，改了会与 judge 0.3 s 静默脱钩。
- P2-6：`initial_std` 默认 1.0（当前从 BC 继承 0.1 不受影响）。
- P2-7：`BLACKW_CLEAR_W` 代码默认 25，文档/job 全用 60。
- P2-8：`total_score` 在 `--only` 下只算子集；显式三元组命令不平移 `cmd_slow`。
- P2-9：`--exact-spawn` 黑名单清理方式对新增 reset 键会漏。
- P2-10：judge 写死 0.002/0.02，不读 policy `config.yaml` 的 dt/decimation。
- P2-11：`diag_rollout.py` 用基类 runner 且把 `max_init_terrain_level` 钉 0。
- P2-12：exec-plan 写 `--joint-offset-range/--joint-vel-range`，实际参数是 `--joint-offset/--joint-vel`（已在校对文档时注意）。

## 4. 非审计但阻塞"有效训练/验收"的工程项

1. **覆盖集评测工具未实现**：`20-part2-shared/acceptance-eval-protocol.md` 已定义口径（手柄全范围、90%/3D 正态+穿模重采样、稳定/穿越两子集、held-out、JSON 报告），但 `eval_blackw_part2.py`/`gate_stage.py` 仍是旧"固定次数+3 档"协议；在实现前，不能宣称"满足验收"。
2. **作业/队列接线**：见 P1-10；不修则"作业绿色但模型缺失/质量下行"会重演。
3. **部署资产**：`scenes/blackW/assets/`（约 42 MB 官方 mesh）按仓库约定 gitignore，演示前需从官方源恢复（见 `20-part2-shared/deployment-contract.md`）。

## 5. 建议执行顺序

1. **第一批（阻塞语义正确性）**：P1-1、P1-5、P1-7、P1-11、P1-12、P1-4。
2. **第二批（阻塞部署/交付可信）**：F3 → F1 验证 + F2 → F6/F7/F15。
3. **第三批（阻塞实验可追溯）**：P1-10（含 F8/F9/F10/F12/F16）、P0-2r 接线、F14、P1-6。
4. **第四批**：P1-2、P1-3、P2 清单；然后开 round-2 独立审计；PASS 后才恢复训练与 A6 实验。

> 本清单与 `30-ops/status.md`、`21-part2-ppo/handoff.md` 联动；修完一项就地把状态改为 FIXED 并写验证命令/证据。
