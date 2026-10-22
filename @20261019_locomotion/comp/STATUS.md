# 比赛工作流状态

> 只记：当前阶段、下一步、阻塞、最近一次审计结论。进展事实在 `../docs/status.md`，本文件只服务工作流门禁。
> 更新时机：阶段切换、门禁结论变化、出现阻塞。

## 0. 当前

- **stage**：C1（**G1 judge 审计已完成：FAIL**，2026-10-22）
- **deadline**：2026-11-04 晚（截至 2026-10-22 约 12.5 天）
- **next**：按 `audits/JUDGE_AUDIT.md` 的 P0 清单修 judge/evaluator（成功语义、T 台阶部分分、斜坡、限高杆落杆、Part2 门槛/舍去/稳定性）
  → 补人工标定集（≥64 条）→ 重跑 G1（含盲写第二实现）→ 正式协议评测 → 基线记分
- **blockers**：
  1. **G1 FAIL**：judge 存在可直接触发的错误成功路径与漏判（详见 `audits/JUDGE_AUDIT.md` §3/§4）；规则口径已补齐（Q1–Q6），P0 重写按已确认口径执行；
  0. **评审后端已就绪**：Codex（≤4 次/14 天）+ BYOK DeepSeek（provisional）+ manual 协调者；首次 BYOK 契约审计 completed（WARN，13 条已合入契约/协议修正），见 `audits/BYOK_CONTRACT_REVIEW.md`。
  2. Part 2 六类 evaluator/起点/难度判定缺失（当前只有测试/几何，无完整 evaluator）；
  3. 人工标定集为空（`eval/_calibration/` 只有 README）；
  4. 尝试账本/暂停恢复（AttemptManager）未实现，现有 runner 覆盖写结果；
  5. provenance 不完整：训练/控制仓 commit、uv.lock、完整 judge hash 未在运行时采集（诊断导入只能标 diagnostic）。

## 1. 门禁状态

| 门禁 | 状态 | 说明 |
|---|---|---|
| G0 规则契约 | **PASS** | Q1–Q6 已于 2026-10-22 由用户转述主办方口径并写入 `CONTRACT.*`（Q2 的上/下↔75/50 建议书面确认） |
| G1 评测器可信 | **FAIL** | 2026-10-22 Codex ultra 审计：overall FAIL；修复 P0 后重审；见 `audits/JUDGE_AUDIT.{md,json}` |
| G2 基线可复现 | pending | 待正式协议评测（当前只有诊断导入） |
| G3 单轮评测有效 | pending | 诊断行为 `diagnostic`，不计正式分 |
| G4 里程碑审计 | pending | 尚无里程碑策略 |
| G5 冻结 | pending | — |

## 2. 当前评测产物

| policy_id | 来源 | 性质 | 分数 | 备注 |
|---|---|---|---:|---|
| `flat-ft-2500-part1-diag-v1` | `prep.d/results/part1_zero_shot.json` | diagnostic（未控种子/每障碍一次） | 0 | 仅起点记录 |
| `p1-basic-obstacle-part1-diag-v1` | `prep.d/results/part1_p1_basic_obstacle.json` | diagnostic | 0 | `model_3997` 导出 `8deb41a6…` |
| `p1-cont-part1-diag-v1` | `prep.d/results/part1_p1_cont.json` | diagnostic | 0 | `model_5496` 导出 `035749ff…` |

`SCOREBOARD.md` 由 `comp_score.py` 生成；这些行**不得**用于选型或对外引用（G1 FAIL + 仅诊断）。

## 3. 最近审计（G1，2026-10-22）

- reviewer：codex / gpt-6-astra / **ultra** / 新线程 / read-only / 只给路径；threadId 未由 bridge 回传。
- **overall：FAIL**。逐项：A1–A4 FAIL、B1–B3 FAIL、B4 WARN、C1/C2 FAIL、C3 WARN、C4 PASS、
  D1–D3 FAIL、E1 WARN、E2 PASS、E3 WARN、E4 PASS、F1/F2 WARN。
- 头号问题：① 未验证真实跨越就成功（六类障碍可被空接触+出口位置骗过，reviewer 实测 6/6 各 100）；
  ② T 台阶把当前帧接触当历史（逐级通过被漏判）；③ 斜坡方向/距离/判罚阶段错误。
- 执行者已实施的工具侧修复：`comp_score` 增加 summary↔trials 证据链强校验（伪造 success 现在会被判 invalid）；
  `CONTRACT.json` 修正 Part2 最低门槛曲线（高台/楼梯 <10 cm、坡 <20° 为 0）；诊断导入诚实化（seeds 为空、dirty 标注、
  checkpoint 说明）。
- 未做：盲写第二实现交叉比对（`JUDGE_CROSSCHECK.md`）——与 P0 judge 修复一起做，才能对比"新 judge vs 独立实现"。
- **评审后端（2026-10-22 新增）**：Codex 额度 ≤4 次/14 天，留给 G1/红队/最终分数/争议各 1 次；日常审计用 BYOK（`competition/tools/comp_review.py` + `reviewer.json`，DeepSeek relay，同家族 → verdict 标 provisional），或由用户作为协调者在 DSH 另开会话执行（manual backend）。

## 4.1 P0 进度（2026-10-22 起）

| P0 项 | 状态 | 产物 |
|---|---|---|
| Part 1 V2.1 judge（合法进入/跨越证据/离开、三臂 T 台阶、限高杆连续穿越、双向绕杆、失败可重试、返回奖励只认全满分） | **已实现 + 13 组 conformance 全过** | `scripts/agent_scripts/comp_part1_judge.py`、`comp_judge_conformance.py` |
| AttemptManager（3 次、恢复不消耗、账本、best score/fastest time） | 已实现 | 同文件 + `comp_part1_course.py` |
| 场景 v2（可掉落横杆 + 命名台阶/平台/坡面） | **已实现**（横杆静置稳定，掉落可检测） | `assets/terrain/part1/part1_eval_scene_v2.xml` |
| runner 接入 V2（每物理步接触分类/bar 位移） | **已实现**，8 障碍 diagnostic 已跑 | `run_part1_judged_rollout_v2.py`、`comp/eval/flat-ft-2500-part1-diag-v2/` |
| 正式 Part 1 整场赛程协议 | **协议类 + MuJoCo 整场诊断 runner 已实现**；操作手事件接口已留（`--events`），正式手动跑法待 C4 排练 | `comp_part1_course.py`、`run_part1_course.py`、`comp/eval/flat-ft-2500-part1-course-diag/` |
| Part 2 六类 evaluator | **已实现**（参数化 20 档 + 计分 floor/端点 0） | `comp_part2_judge.py`、`make_part2_levels.py`、`run_part2_judged_eval.py`、`comp/eval/flat-ft-2500-part2-diag-v2/` |
| 边界擦碰语义（路过相邻障碍区不得永久判失败） | 已修：soft-reset | `comp_part1_judge.py` + conformance/course 自检 |
| 证据链：整场 course 诊断导入 + 重算校验 | 已完成（attempts_used=1 ≤ 3，score 由 trials 复算） | `comp_import_course_diag.py`、`comp/SCOREBOARD.md` |
| T 台阶 Q2 | ✅ 已确认（2026-10-22）：×2/3 → 上=50、下=50×2/3≈33.33→33；返回奖励只认满分 | `CONTRACT.*`、`_protocol.md`、judge 默认值 |
| 计时/排序口径 | ✅ 已确认：分数最高优先、同分取最快；**计时在机器人稳定停下后停止**（runner 已实现 stable-stop） | `CONTRACT.*`、`run_part1_course.py` |
| BYOK 评审升级顺序 | flash 两轮 FAIL → **pro 第三轮 FAIL（N1–N4）→ 已修复** → Codex（需用户二次确认，因外部额度） | `comp/audits/BYOK_JUDGE_V3_PRO_REVIEW.md`、`BYOK_JUDGE_V2_FIXES.md` |
| GPT/Codex 调用规则 | 任何 GPT 系调用须先报进度并二次确认；DeepSeek 调用无需告知；已写入 `comp/DEV_OPS.md` §4 | `comp/DEV_OPS.md` |
| Pro 复验 P1–P4 | 稳定停表 dt、暂停误喂 judge、comp_score 外部证据校验、ground 分类已修；3-attempt pause 演练进行中 | `comp_part1_course.py`、`run_part1_course.py`、`comp_score.py` |
| BYOK 预审（same-model，provisional） | 已执行：FAIL/26 条（11 blocker），已逐条修复或记录残余风险 | `audits/BYOK_JUDGE_V2_REVIEW.md`、`audits/BYOK_JUDGE_V2_FIXES.md` |
| G1 重审（Codex，不同家族） | **待用户批准后执行**：gpt-6-astra 403 无权限；gpt-6.1-sol/xhigh 会话被中止（见 `CODEX_G1_REAUDIT_STOPPED_20261023.md`，非 verdict）；N1–N4 修复后待重新批准 1 次 | 第 2 版 `JUDGE_AUDIT` |

**V2 评测链路（2026-10-22 晚）**：Part1 judge V2 `comp_part1_judge.py`（10 组 conformance 全过，含 G1 反例：6 条出口骗分、T 台阶跨帧历史、限高杆 touch/drop、斜坡距离、砂砾短边、高墙侧走、绕杆顺序、尝试规则）+ 场景 v2 + 逐物理步 runner + 整场协议 `comp_part1_course.py`（3 次、恢复不消耗、最快用时、返回奖励）+ Part2 六类 judge/参数化 20 档 evaluator；两条 diagnostic 产物已进 `comp/SCOREBOARD.md`（`flat-ft-2500-part1-diag-v2`/`-part2-diag-v2`，均 0 分，符合 flat 策略预期）。

## 4. 下一步顺序

1. P0-1：重写 judge 成功语义（合法进入→实际跨越/接触历史→完整离开；六障碍逐条）+ Part2 evaluator；
2. P0-2：AttemptManager（整场/障碍/暂停/恢复/跳过/重跑，追加写不覆盖）；
3. P0-3：运行时 provenance 采集（多仓 commit/dirty/uv.lock、完整 judge 依赖 hash）；
4. P0-4：conformance 用例（reviewer 给的非法得分反例进单元测试）；
5. 然后：64 条人工标定 + 盲写第二实现 → **重跑 G1**；通过后才做正式协议基线与 C3 训练循环。
