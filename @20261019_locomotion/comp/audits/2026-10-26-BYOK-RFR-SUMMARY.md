# 2026-10-26 竞赛向独立评审（BYOK + RFR，无 Codex）

> 触发：G1 judge v5 的 Codex 审计此前 `REVIEW_UNAVAILABLE`（401）；用户 2026-10-26 指示不要调用 Codex，改用 aHIL `competition` 分支的 BYOK 评审链，并把该分支对齐 main 分支的 Rejection-First Review (RFR) 实践。
> 执行：`/home/bis/ahil` 的 `competition` 分支（worktree `RoboCon/aHIL-comp`）已 merge `main`（commit `2c74019`，包含 RFR chain：`skills/shared-references/reject-first-chain.md`、`tools/reject_first_gate.py`、6 个单测全过）；评审使用本仓库 `comp/audit-prompts/judge_audit_rfr.md`、`score_evidence_rfr.md`（在 RFR S1/S2 与 G1/G4 prompt 基础上做竞赛口径适配），后端 `comp_review.py` BYOK，均**不同 family**（executor=deepseek-v4.1-flash）。

## 结论（两份独立评审，均 FAIL/REJECT）

| 审计 | reviewer | 元信息 | verdict | 未解决 FATAL |
|---|---|---|---|---|
| G1 评测器（judge v5） | GLM-5.3（zhipu） | different-family；133K tokens；356 s；payload 302 KB / 57 files；trace `comp/traces/comp-eval-audit/` | **FAIL / REJECT** | ① v5 无标定/对照（全部 A 类成功条件 NOT_RUN）；② v5 与 Part2JudgeV2 语义漂移，且唯一存档产物由 V2 生成 |
| G4 分数与证据链 | GLM-5.3-Flash（zhipu-flash） | different-family；53K tokens；trace `comp/traces/comp-score-audit/` | **FAIL / REJECT** | ① comp_bc_v5 的 750/743/4-of-4 无 comp/eval 三件套支撑、judge v5 未审计；② 部署栈 5/20（≈300/1300）与 750 宣称直接矛盾且未披露 |

原始 verdict 文件：`comp/audits/2026-10-26-judge-v5-G1-BYOK-GLM.{md,json}`、`comp/audits/2026-10-26-score-evidence-G4-BYOK-GLMFLASH.{md,json}`。

## 评审指出的主要问题（executor 已核对）

1. **judge v5 自拟阈值**：hold 0.3 s（0.2+0.1）、WHEEL_ON_SURFACE_TOL 0.06 m、gap 允许下沉 min(0.5*depth, wheel_r)=0.103 m、wall climb_z_min 等均不在规则原文（`docs/00-competition/rules-team-race-2026.md` §3 只写"越过即得分"）；需主办方书面口径或补规则依据。
2. **成功谓词是"高度带"而非接触**：platform/slope 仅验四轮 z 带 + 基座 x/y，存在"后两轮上台、前两轮抬高保持 0.3 s"的骗分路径；若用于训练 termination 有 reward hacking 风险。建议改"高度带 AND 轮心投影落在支撑面内"或接触几何。
3. **两套 judge 语义漂移**：v5（eval_blackw_part2.py）与 V2（comp_part2_judge.py）对同一条件实现不同；唯一存档 comp/eval 产物由 V2 生成，历史分数无法映射到 v5。
4. **v5 输出不符合 comp/eval 三件套契约**（无 seed/operator/manifest/trials/summary），无法进入 comp_score 证据链。
5. **comp_bc_v5 分数全部是 executor 证据**：无 comp/eval 三件套、无 judge v5 file hash/HASHES 登记；报告内部数字矛盾（期望 743 vs 706；高墙 3/4 vs 1/4；高台 4/4 vs 3/4@vx0.9）。
6. **部署证据问题**：smoke 5/20 与 judge 750 差 450 分未披露；smoke 出现数值爆炸（trench z≈-1118）、plum 初始即倒（tilt=180）。
7. **合规风险（最高优先）**：轮腿构型（4 个主动轮/轮电机）是否属于规则允许的"足式"及力矩表覆盖范围，材料里没有任何授权依据；若现场按 literal 足式执行，judge 再准也是 0 分 → 需主办方书面确认。

## executor 侧跟进（本轮已做/待做）

- 已核出部署 smoke 的更根本问题：**部署 `part2_levels.json` 用的是旧 proxy 场景 `part2_*.xml`，judge 用的是官方几何 `part2_off_*.xml`**（20/20 全不一致）——部署演示/冒烟一直跑在错的关卡几何上。已把 deploy levels 全部改为官方 `part2_off_*`（`part2_levels.json`），待重跑 smoke。
- 官方权重对照（missing control #4）：官方 `obstacle` 权重过同一 smoke 也是 **5/20**（与 comp_bc_v5 同为 5/20，且同样出现 trench 数值爆炸/plum 失败）→ **5/20 不能归因于策略，smoke/栈本身有效性存疑**；在修复并重跑前，删除一切"部署栈能力"引用。
- 待做：comp_bc_v5 的 judge v5 结果导入 comp/eval 三件套（manifest 带 v5 hash + 训练仓 commit），`comp_score.py` 重算；报告 750/743 降级为"未审计 executor 证据"；judge v5 阈值取得规则依据/主办方确认；4 次尝试语义在 runner 层实现；接触式成功谓词改造（冻结前）；覆盖集验收工具实现。

> 评审纪律：两份 verdict 都是 different-family；按本仓库 `comp/reviewer.json` 规则，GLM 可作为 Type-B 独立评审（不再依赖 Codex）。执行者不得自行把 FAIL 改写成 PASS；修复后需重跑 reviewer 复验。
