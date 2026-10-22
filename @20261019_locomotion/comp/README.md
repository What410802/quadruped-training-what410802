# comp/ —— 比赛迭代工作流状态目录

> 本目录由 aHIL 的比赛工作流增量包落地而来：`What410802/academic-human-in-the-loop` 仓库的
> `competition/` 目录（分支 `competition-workflow`；本机 clone 路径不入库）。
> 目的：让「训练 → 固定协议评测 → 分数证据链 → 独立审计 → 决策 → 冻结 → 答辩」可复盘，
> 且**评测器与分数不是自证的**：Codex 审计评测器/证据，分数只来自 evaluator。

## 先读什么

1. 本文件；
2. `STATUS.md`（阶段 / 下一步 / 阻塞 / 最近审计结论）；
3. `../docs/status.md`（任务进展；两者冲突时以后者的进展事实为准）；
4. 按需：`CONTRACT.md`、`PLAN.md`、`SCOREBOARD.md`、`audits/`。

## 目录

```text
comp/
├── README.md            # 本文件
├── STATUS.md            # 阶段/下一步/阻塞
├── PLAN.md              # 冲刺计划（triage）
├── CONTRACT.md          # 人读契约（规则→分数表/成功定义/约束/歧义）
├── CONTRACT.json        # 机读契约（工具输入）
├── SCOREBOARD.md        # 权威记分板（comp_score.py 生成，不手改数字）
├── SCOREBOARD.json
├── RUN_LEDGER.md        # 训练/评测 run 账本
├── findings.md          # 一行一条发现
├── compliance_evidence.json  # 部署合规证据（传感器/力矩/仅RL）
├── eval/
│   ├── _protocol.md     # 评测协议（版本化）
│   ├── _calibration/    # 人工标定集（≥30 条，视频在外）
│   └── <policy_id>/     # manifest.json / trials.jsonl / summary.json
├── audits/              # JUDGE_AUDIT / SCORE_AUDIT / TRAIN_SYSTEM_AUDIT / REDTEAM
├── freeze/              # FREEZE_MANIFEST / REPLAY / FALLBACK
├── defense/             # 7 分钟答辩 + 演示
└── traces/              # Codex 调用 trace（gitignore；结论摘要另存 audits/）
```

## 工具（`../scripts/agent_scripts/comp_*.py`，纯 stdlib，带 `--self-test`）

```bash
# 1) 记分板校验/重算（每次评测后）
pixi run python @20261019_locomotion/scripts/agent_scripts/comp_score.py \
  --contract @20261019_locomotion/comp/CONTRACT.json \
  --eval @20261019_locomotion/comp/eval \
  --out @20261019_locomotion/comp/SCOREBOARD.md \
  --json-out @20261019_locomotion/comp/SCOREBOARD.json

# 2) 数字证据预检（把数字写进 status/答辩前）
pixi run python @20261019_locomotion/scripts/agent_scripts/comp_evidence_check.py \
  --root @20261019_locomotion --claims @20261019_locomotion/comp/CLAIMS.json \
  --out @20261019_locomotion/comp/SCORE_EVIDENCE.json

# 3) 合规检查（传感器红线/力矩/仅 RL）
pixi run python @20261019_locomotion/scripts/agent_scripts/comp_compliance.py \
  --contract @20261019_locomotion/comp/CONTRACT.json \
  --evidence @20261019_locomotion/comp/compliance_evidence.json

# 4) 冻结清单（C5）
pixi run python @20261019_locomotion/scripts/agent_scripts/comp_freeze.py ...（见 --help）
```

工具只做 Type-A 检查；"评测器是否忠实规则 / 分数是否支持结论"必须由 Codex 审计
（见该仓库 `competition/shared-references/audit-prompts.md`）。

## 与现有文档的关系（单一事实源）

| 现有文档 | comp/ 对应 | 说明 |
|---|---|---|
| `docs/status.md` | `comp/STATUS.md` | 进展权威仍是 docs/status；comp/STATUS 只记工作流阶段与门禁结论 |
| `docs/reference/team-race-2026.md` | `comp/CONTRACT.md` | 规则真值以 team-race 为准，契约只做机读化与逐条引用 |
| `docs/training/competition-judge.md` | `comp/audits/JUDGE_AUDIT.md` | judge 设计保留；独立审计结论落 audits |
| `docs/training/eval-protocol.md` | `comp/eval/_protocol.md` | 训练内部 gate（G1–G5/H1–H4）与比赛官方评测分开 |
| `docs/training/experiments.md` | `comp/RUN_LEDGER.md` | 现有 run 表继续维护；新 run 同时写 ledger |
| `assets/policies/<ver>/README.md` | `comp/eval/<pid>/manifest.json` | README 记来源与 sha256；manifest 是机读版本 |

## 当前阶段

见 `STATUS.md`。当前是 **C1（评测器 + 待 G1 独立审计）**：
已有诊断性评测导入（单种子、每障碍一次，标 `diagnostic`），尚无正式协议评测与人工标定集。
**G1 未过之前，0/8 等诊断数字不能作为策略能力结论，也不能对外引用。**
