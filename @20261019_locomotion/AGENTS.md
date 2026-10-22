# AGENTS.md —— @20261019_locomotion 比赛迭代工作流（任务级）

> 本文件是该任务新增的 AI 协作协议；父级 `../../AGENTS.md` 与 `../../docs/conventions.md` 仍是默认，
> 本任务偏离父级的地方在此写明。工作流定义在独立仓库 `What410802/academic-human-in-the-loop`
> 的 `competition/` 目录（本机 clone 路径不入库，见 `comp/README.md` 的"工作流来源"）。

## 0. 先读什么（顺序固定）

1. 本文件；
2. `comp/STATUS.md`（阶段 / 下一步 / 阻塞 / 最近审计结论）；
3. `docs/status.md`（任务进展；与 comp/STATUS 冲突时以 docs/status 的进展事实为准）；
4. 按需：`comp/CONTRACT.md`、`comp/PLAN.md`、`comp/SCOREBOARD.md`、`comp/audits/`。

## 1. 工作流（C0–C6，技能手动执行）

```text
C0 规则契约 → C1 评测器 + 独立审计(G1) → C2 基线记分
→ C3 每日：triage → train-loop → score（异常时 diagnose）
→ C4 整合 → C5 冻结 → C6 答辩
```

- 技能定义：`<aHIL-competition-fork>/competition/skills/<name>/SKILL.md`（comp-pipeline / comp-contract /
  comp-eval / comp-eval-audit / comp-score / comp-train-loop / comp-diagnose / comp-triage / comp-freeze / comp-defense）；
  本会话没有 slash 层，**手动读 SKILL.md 执行**。
- 共享契约：同仓库 `competition/shared-references/{competition-gates,eval-artifact-contract,reviewer-cadence,audit-prompts}.md`。
- 工具：`scripts/agent_scripts/comp_*.py`（纯 stdlib，带 `--self-test`）。

## 2. 角色与评审独立性（硬约束）

- executor = 本 agent；reviewer = Codex `gpt-6-astra`（aHIL codex MCP bridge：`mcp__codex__codex` / `mcp__codex__codex-reply`）。
- **executor 不自判 Type-B**：judge 忠实度、分数诚实、泛化性、决赛风险必须由 Codex verdict 落文件。
- prompt 只给**文件路径 + 评审任务**，不给摘要/结论/改动列表/上一轮反馈（唯一例外：同线程引用 reviewer 自己上一轮结论）。
- G1（评测器审计）与冻结红队用 `ultra`；里程碑审计 `xhigh`。新线程；复核可同线程。
- 每次调用落 trace 到 `comp/traces/`，被审对象哈希写 `comp/audits/HASHES.json`。

## 3. 硬约定

1. **分数只来自 evaluator**；Codex 不产出分数。对外数字必须过 `comp_evidence_check.py` 且在 `SCOREBOARD` 白名单。
2. 每轮评测用**冻结协议**（种子/起点/命令/尝试/操作手/judge 版本写进 manifest）；协议改动 bump 版本并重审 G1。
3. **单开关**：一个 run 只改 reward/课程/终止/地形/观测中的一项；混合改动拆开归因。
4. **先提交再启动训练**；manifest 记录多仓 commit/dirty/`uv.lock` hash/权重 sha256。
5. 不挑种子：报均值/最差/尝试次数；重跑同一权重 = 新 `policy_id`。
6. D-3（距 2026-11-04 ≤3 天）起不再开新训练线，只做冻结、兜底、答辩。
7. reviewer 不可用时 fail closed：写 `REVIEW_UNAVAILABLE`，不得用"自己检查过"代替。
8. 训练等待可用定时器/监控；**审计不能按定时器轮询**（milestone/改动/异常触发）。

## 4. 提交与文档

- 提交信息一行英文 `type(scope): ...`。AI 代为提交的授权见 `docs/status.md` §0.1（2026-10-22 起允许，任务级授权）。
- 文档遵循 `../../docs/conventions.md`：单行段落、路径与仓库实际一致、结论带可复现命令与实测数字、
  不写仓库外本机路径。
- 入库：`comp/CONTRACT.*`、`comp/eval/<policy>/{manifest,summary}.json`、`comp/audits/*`、`comp/SCOREBOARD.*`、
  `comp/RUN_LEDGER.md`、`comp/findings.md`、`comp/freeze/*`、`comp/defense/*.md`；
  不入库：`comp/traces/`、`*.mp4`、`*.pt`（`comp/.gitignore` 已覆盖）。

## 5. 快速命令

```bash
# 记分板校验/重算（每次评测后）
pixi run python @20261019_locomotion/scripts/agent_scripts/comp_score.py \
  --contract @20261019_locomotion/comp/CONTRACT.json --eval @20261019_locomotion/comp/eval \
  --out @20261019_locomotion/comp/SCOREBOARD.md --json-out @20261019_locomotion/comp/SCOREBOARD.json

# 数字证据预检 / 合规检查 / 冻结清单（见各脚本 --help）
pixi run python @20261019_locomotion/scripts/agent_scripts/comp_evidence_check.py --help
pixi run python @20261019_locomotion/scripts/agent_scripts/comp_compliance.py --help
pixi run python @20261019_locomotion/scripts/agent_scripts/comp_freeze.py --help
```

## 6. 当前状态（2026-10-22）

- C1 进行中：诊断导入已落地（3 个 `diagnostic` 行，均为 0 分）；**G1 judge 审计未做**；
  人工标定集为空；正式协议（种子/尝试/Part2 起点）仍缺。
- 下一步：G1 审计（Prompt A）＋盲写第二实现（Prompt B）→ 标定集 → 正式协议 → 基线记分。
- 详见 `comp/STATUS.md`。
