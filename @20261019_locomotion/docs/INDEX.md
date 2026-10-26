# 文档索引与阅读顺序（2026-10-26 重组后）

> 本文件是 `@20261019_locomotion` 任务文档的唯一入口地图。仓库根 `docs/`（约定/学习笔记/踩坑）是**仓库级共享知识**，不在此树内。
> 文档角色：**INDEX（本页）→ 00 竞赛共用 → 10 Part1 → 20 Part2 共用 → 21 Part2-PPO → 22 Part2-HIM → 30 运维 → 40 参考 → 90 归档**。`comp/` 是比赛流水线（C0–C6），入口保持 [`../comp/README.md`](../comp/README.md)、状态 [`../comp/STATUS.md`](../comp/STATUS.md)。

## 一、阅读顺序（新执行者）

1. [`../README.md`](../README.md)（任务总览）与 [`../AGENTS.md`](../AGENTS.md)（工作流硬约束：C0–C6、reviewer 独立性）。
2. 本页 → [`00-competition/rules-team-race-2026.md`](00-competition/rules-team-race-2026.md)（规则/计分真值）。
3. [`30-ops/status.md`](30-ops/status.md)（当前真值：做到哪/下一步/卡在哪）。
4. 按线读：
   - **Part1**：[`10-part1/plan.md`](10-part1/plan.md) → baseline/health/experiments → terrain。
   - **Part2 共用**：[`20-part2-shared/acceptance-eval-protocol.md`](20-part2-shared/acceptance-eval-protocol.md)（验收口径，先读）→ geometry-and-levels → failure-vs-reward → deployment-contract。
   - **PPO/BC 线**：[`21-part2-ppo/handoff.md`](21-part2-ppo/handoff.md)（交接入口）→ [`execution-plan.md`](21-part2-ppo/execution-plan.md) §0 → bc-policy-report → history-bugs/history-experiments → audits。
   - **HIM 线**：[`22-part2-him/route-overview.md`](22-part2-him/route-overview.md) → gate-curriculum → gate-vs-judge-contract → 审计/导出一组。
5. 运维/复现：[`30-ops/environment.md`](30-ops/environment.md)、[`30-ops/remote-training-workflow.md`](30-ops/remote-training-workflow.md)、[`30-ops/gpu-queue.md`](30-ops/gpu-queue.md)、[`30-ops/repo-layout.md`](30-ops/repo-layout.md)。

## 二、目录树

```text
@20261019_locomotion/docs/
  INDEX.md                        # 本页
  plan.md / status.md             # 旧路径，保留为重定向页（AGENTS/引用兼容）
  00-competition/                 # 竞赛共用：规则、判定器、计分、保存底、演示、流水线指针
  10-part1/                       # Part1（black 四足障碍赛）：计划/基线/健康/实验/地形/砂砾/迁移
  20-part2-shared/                # Part2 共用：验收协议、几何档位、失败vs奖励、架构、相机深度、部署契约、方法、配方、run 记录
  21-part2-ppo/                   # Part2 PPO/BC 线：handoff、执行计划、BC 报告、盲/深度课程、history、audits
  22-part2-him/                   # Part2 HIM 线：路线、zero-shot、部署、gate、契约、导出一组、代码/路径/NaN 审计
  30-ops/                         # 环境、远程训练、GPU 队列、仓库布局、当前状态
  40-reference/                   # 文献、开源、电机/窗口、部署栈、rl_sar 迁移、视觉自检
  90-archive/                     # 过期/被取代/拆分前全文（文件头有归档横幅）
../comp/                          # 比赛流水线（独立状态目录，不移动）：CONTRACT/SCOREBOARD/RUN_LEDGER/audits/...
```

## 三、术语与命名

| 术语 | 含义 |
|---|---|
| `black` | Part1 的 12 关节四足机器人/任务基座（`tasks/velocity/black`） |
| `blackw` | Part2 的 16 关节轮足机器人（`tasks/velocity/blackw`、`robots/blackw`） |
| `him` | HIM 线（HIM estimator + actor；含 depth/HIMLoco 相关工作） |
| `part2-ppo` | PPO/BC 盲侧线（本目录 21） |
| `comp/` | 比赛流水线（C0–C6 技能、契约、记分、审计） |
| `judge v5` | 本地权威判据（`eval_blackw_part2.py`，2026-10-25 起） |
| 覆盖集 | 验收的"初始状态×指令"采样空间，见 `20-part2-shared/acceptance-eval-protocol.md` |
| 旧计数口径 | 2026-10-26 前文档里的 8/8、16/16、<1% 等自拟指标，已作废 |

## 四、历史与归档

- 拆分前全文：[`90-archive/ppo-history-full-2026-10-26.md`](90-archive/ppo-history-full-2026-10-26.md)、[`90-archive/terrain-audit-original-2026-10-26.md`](90-archive/terrain-audit-original-2026-10-26.md)。
- 旧 plan/status：[`90-archive/legacy-plan-2026-10-26.md`](90-archive/legacy-plan-2026-10-26.md)、[`90-archive/legacy-status-2026-10-26.md`](90-archive/legacy-status-2026-10-26.md)。
- 重组清点与方案：[`90-archive/reorg-inventory-2026-10-26.md`](90-archive/reorg-inventory-2026-10-26.md)；交接评审：[`90-archive/handoff-readiness-review-2026-10-26.md`](90-archive/handoff-readiness-review-2026-10-26.md)。
- `comp/audits/archive/` 保存 2026-10-22–25 的 judge 审计轮次与 prompt；终态索引见 [`../comp/audits/README.md`](../comp/audits/README.md)。

## 五、维护约定

- 新文档按编号目录放；文件名带线前缀（`part1-`、`part2-shared-`、`part2-ppo-`、`part2-him-`、`ops-`、`reference-`）。
- 事实单源：验收口径只在 `20-part2-shared/acceptance-eval-protocol.md`；GPU 队列只在 `30-ops/gpu-queue.md`；部署契约只在 `20-part2-shared/deployment-contract.md`；其他文档放指针。
- 每份 active 文档建议在标题下写一行元数据：`owner / status(active|draft|superseded) / last-verified(日期 + 关联 commit/文件)`。
