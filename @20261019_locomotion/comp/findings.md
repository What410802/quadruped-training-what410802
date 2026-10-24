# findings：一行一条发现（异常 / 根因 / 决策）

> 只记"值得跨会话记住"的结论，每条带证据路径或复现命令；细节在 docs/。

- [2026-10-22] judge 为启发式、未用真实手动轨迹标定；限高杆方向曾有误判史（见 `docs/reference/agent-visual-checklist.md`）。→ G1 审计前，所有分数只能当 diagnostic。
- [2026-10-22] flat/rough 诊断里八障碍 zero-shot 全 0 分：可能是策略弱，也可能是 judge/起点语义问题；两者当前无法区分。→ 先审计评测，再谈策略。
- [2026-10-22] P1 `black-basic-obstacle` 第一轮：非法接触率仍高（约 0.89）、stairs_down level 0.85；桥/限高行为改善但未过 slope/stairs。→ 不能把 train reward 上升当 gate。
- [2026-10-22] 部署审计：flat-ft-2500 是 45 维 actor、effort 20 N·m；hip/thigh 23.7、calf 59.25 在 25/60 内（见 `prep.d/results/deployment_audit.json`）。→ 合规基线可用，但需每个新 policy 重跑。
- [2026-10-22] 评测产物契约落地：现有诊断 JSON 已导入为 `diagnostic` 行；正式分数需要固定协议 + 人工标定 + G1。
- [2026-10-22] **G1 judge 审计 FAIL**（codex ultra）。六类 Part1 障碍可用"空接触+出口位置"骗到 100 分（reviewer 实测 6/6）；T 台阶把当前帧接触当历史，逐级通过被漏判；斜坡方向误判；限高杆横杆固定不可掉落；Part2 低于门槛给 5 分；`summary↔trials` 无关联校验。详见 `audits/JUDGE_AUDIT.md`。
- [2026-10-22] 工具侧修复：`comp_score.py` 增加 summary↔trials 证据链/最高难度/attempts 校验（伪造 success 判 invalid）；`CONTRACT.json` 修正 Part2 最低门槛曲线；诊断导入改为诚实 provenance（seeds 空、dirty 标注、checkpoint 说明）。
- [2026-10-22] 审计同时指出：A/B 桥标注与 PDF 图 1 相反（已改为不按 A/B 断言并加歧义 Q4）；Python 端动作限幅 ±1 vs 部署 ±100（C3 WARN，待统一）。
- [2026-10-22] **主办方口径 Q1–Q6 已确认**：Part1 整场 3 次且开始/重试/恢复/跳过都消耗；T 台阶部分分 100/75/50；任何瞬间 ≥2 足触地即失败、限高杆碰柱/梁但未落杆不算失败；砂砾坑两端都需合法、斜坡两侧合计 1 m；Part2 高墙/沟壑 10 cm 端点 0 分、小数舍去、稳定 = 失效率 <1%（≥100 次）；Part1 全部按手动遥控计分（Q6）。已写入 CONTRACT/protocol。
- [2026-10-22] 新增 BYOK 评审后端：`comp_review.py` 支持 OpenAI 兼容 API（DeepSeek relay），密钥不落盘；同家族评审标 provisional，Codex 额度只用于 4 个关键 gate。
- [2026-10-22] BYOK 后端打通并完成首次真实审计：DeepSeek v4-pro 流式调用 ~11.6 min、overall WARN、13 条问题（整场 vs 单障碍协议、稳定性 <1% 定义、tiebreak/返回奖励/红线缺失、radar vs lidar 等），已修契约/协议 11 项；同家族 → provisional。
- [2026-10-22] 待主办方书面确认：恢复是否消耗尝试、T 台阶上/下↔75/50、radar 是否激光雷达、稳定性严格 0 失败还是 <1%；CONTRACT.md §5.1 已留痕。
- [2026-10-22] Part 1 judge V2 落地：纯 Python 事件式、规则语义化（合法进入→跨越证据→合法离开），10 组 conformance 覆盖 G1 审计反例（6 条 spoof、T 台阶历史、限高杆 touch/drop、斜坡距离、砂砾短边、高墙侧走、绕杆顺序、尝试规则）全部通过。待接 MuJoCo 接触分类/可掉落横杆/Part2。
- [2026-10-22] Part1 judge V2 接入 MuJoCo：场景 v2（横杆 slide joint、命名台阶/平台/坡面）+ 逐物理步接触分类 runner；8 障碍 diagnostic 全 0（flat 策略预期），边界擦碰改 soft-reset（避免相邻障碍区误占失败）。
- [2026-10-22] Part2 evaluator V2：参数化高台/楼梯/斜坡/高墙/沟壑/梅花桩 20 档 + 计分 floor/10cm 端点 0/稳定性按失败比例；flat 策略 20 档全失败（trench 20/30cm 落入），与 baseline 能力一致。
- [2026-10-22] 整场 Part1 协议类：3 次尝试、恢复不消耗（暂停时间不计入 duration）、开始/跳过消耗、返回奖励（8 障碍全过+二次进入出发区）、best score/fastest time；合成全通过 run 得 900 分自检通过。
- [2026-10-22] 整场 course 诊断 runner `run_part1_course.py` 跑通（脚本化 waypoint、1 次尝试、94 s 仿真、8 障碍 0 成功），协议类正确记录尝试/时长/失败；导入产物 `flat-ft-2500-part1-course-diag` 过 comp_score 校验（attempts_used=1 ≤ 3）。
- [2026-10-22] Q2 保守决策：T 台阶部分分暂按 75/50（转述 75*3/2=112.5 与单项满分 100 冲突），返回奖励要求单项满分（部分分不触发）；comp_score 增加部分分允许集合 + Q5 floor。
- [2026-10-22] BYOK 预审（same-model provisional）判 judge V2 FAIL：26 条（11 blocker），核心是地面判据缓冲误杀、高墙/限高杆/绕杆/T 台阶可欺骗、桥面 tag 缺失、Part2 低难度地面伪成功、整场协议未接 runner。已实现 V2.1 修复（supported gating、墙平面穿越+抬升、双向绕杆+终点最后、三臂 T 台阶、桥面 tag 补全、Part2 横向/无地面约束、恢复位姿校验、course runner/importer、floor/部分分），conformance 13 组全过；残余风险见 BYOK_JUDGE_V2_FIXES.md。
- [2026-10-22] 规则最终确认：Q2 = ×2/3（上 50、下 33.33→33）；分数最高优先、同分取最快；计时在机器人稳定停下后停止。已更新契约/protocol/judge 默认值与 course runner（stable-stop）。
- [2026-10-22] BYOK 二次预审（flash）仍 FAIL；已修复高墙抬升/限高杆持久掉杆/T 台阶 partial 升级/绕杆拐角方向/Part2 接触与绕行/整场单会话 ledger/暂停死锁/返回证据校验；第三轮改用 deepseek-v4-pro 复审。GPT/Codex 调用按用户要求先报进度待批准。
- [2026-10-24] **Warp 710 复发已插桩定位（非“resume 坏了”）**：E1 resume `model_3997`、E5 resume `model_5400` 各 100 iter 干净且 E1 与 10-22 的 `p1_cont` 前 100 iter 指标几乎逐位一致；从 `model_5496` 的 4 次 run 全部在 100 iter 内出问题。probe 在 resume 后**第一个 rollout 的 step 29** 抓到单 env 动作 13→135 几何增长、`|qvel|` 仅 ~46，obs 的 max 与 action 同步增长（含 last-action 项）→ 放大机制是动作经观测自激，不是物理先爆；NaN 是末端症状。详见 `docs/training/training-health.md` §7。
- [2026-10-24] 三项安全网（actor obs clip ±100 与部署一致 / `clip_actions=±100` 与部署一致 / `bad_sim_state` 极端状态终止）后，从 `model_5496` 的 200-iter resume smoke 无 CUDA 错误、无 NaN；动作从 ~1e5 量级被压到 ~300 饱和。→ 修复有效但只是安全网，不改 reward/课程设计；长跑仍需中程检查。
- [2026-10-24] `best.pt`（HIMLoco）zero-shot：平地 cmd 0.5 实测 vx=0.36 m/s、tilt 3.1°、tau 峰值 15.8 N·m、不摔；Part1 固定诊断 0/8（多为“没走到/被挡”）；Part2 固定 6 s 0/20（全部没走到 x≈2.5 障碍），时间放宽到 12 s 后 8/20 档成功（diag 300/1300：high_platform 10/20 cm、stairs 10/15/20/30 cm、slope 20/30°、trench 10 cm）。→ 可作 blind fallback / teacher / 对照；评测 Part2 诊断窗口需 ≥10–12 s，否则会把“没走到”当“不会”。见 `docs/training/him-best-zero-shot.md`。
- [2026-10-24] Part2 judge 观察：`high_wall` 要求墙附近 `max_z ≥ max(wall_h+0.10, 0.55)`，`best.pt` 10 cm 档实测已越过（x=3.44）但 max_z=0.478 → 判失败。是否改判属 G1/协议范围，未动。
- [2026-10-24] mjlab 1.6 深度相机走 `mujoco_warp.RenderContext`（`SensorContext` + CUDA graph `sim.sense()`），与现有 terrain_scan/foot_height_scan 的 raycast 共用同一 sense graph，**不需要 EGL**；`CameraSensorCfg(data_types=("depth",))` 的 depth 形状 `[B,H,W,1]`，no-hit/sky 像素为 0、远距离可达几十米，进 obs 前要按“≥cutoff 视为最远”处理。深度 task（64x48、forward 15° down、actor=45 proprio+CNN 64D、critic 不变 259）已注册并跑通 PPO plumbing；成本 smoke（25 iter × 4 配置，1024 envs）：blind 1.39 s/iter/2.0 GB、depth32 2.12 s/4.3 GB、depth64 3.53 s/11.1 GB、depth64@2048 6.22 s/14.8 GB；100-iter 深度训练 smoke 100/100 无 CUDA/NaN。见 `docs/training/camera-depth.md` §5。
