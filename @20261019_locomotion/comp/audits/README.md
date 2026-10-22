# audits/ —— 独立审计结论

> 本目录只放**跨模型 verdict**（Codex）；executor 只收集路径与跑确定性预检。
> 每次审计的元信息必须含 reviewer/model/effort/threadId/date；被审对象哈希写 `HASHES.json`。
> 哈希变化 → 对应门禁失效，需重审（见 比赛工作流包的 `competition/shared-references/competition-gates.md` §3）。

| 文件 | 门禁 | 内容 | 状态 |
|---|---|---|---|
| `JUDGE_AUDIT.md/.json` | G1 | judge 规则忠实性/漏洞/协议诚实/证据链/合规/范围 | **FAIL（2026-10-22）**，修复 P0 后重审 |
| `JUDGE_CROSSCHECK.md` | G1 | 盲写第二实现与现有 judge 的逐条比对 | 未做（与 P0 修复一起做） |
| `SCORE_AUDIT.md` | G4 | 记分板数字 → 证据路径核对与白名单 | 未做 |
| `TRAIN_SYSTEM_AUDIT.md` | — | reward/课程/终止/观测契约系统性问题 | 未做 |
| `REDTEAM.md` | G5 | 冻结前"决赛为什么失败"红队 | 未做 |
| `BYOK_CONTRACT_REVIEW.md/.json` | G0 辅助 | BYOK（DeepSeek v4-pro，provisional）对契约/协议的独立初筛：WARN，13 条问题 | 已做；问题已按需修正 |
| `prompts/` | — | 审计 prompt 存档（可复用于 Codex/BYOK/manual 后端） | — |
| `BYOK_JUDGE_V2_REVIEW.md/.json` | G1 预审 1 | DeepSeek flash（same-model-provisional）对 judge V2：FAIL/26 条 | 已修复，见 FIXES |
| `BYOK_JUDGE_V2_VERIFY.md/.json` | G1 预审 2 | DeepSeek flash 复审：FAIL（7 blocker 未清） | 已修复，见 FIXES §二次预审 |
| `BYOK_JUDGE_V3_PRO_REVIEW.md/.json` | G1 预审 3 | DeepSeek **pro** 第三轮复审：FAIL（N1–N4），已修复 | 见 FIXES §Pro 预审后修复 |
| `CODEX_G1_REAUDIT_STOPPED_20261023.md` | G1 尝试 | Codex `gpt-6.1-sol`/xhigh 会话 00:08 被中止（非 verdict）；用户要求 GPT 调用先审批 | 见 `DEV_OPS.md` §4 |
| `BYOK_JUDGE_V4_PRO_VERIFY.md/.json` | G1 预审 4 | DeepSeek **pro**：N1–N4 PASS，提出 P1–P4 | 已修复 |
| `BYOK_JUDGE_V5_FLASH_ACCEPT.md/.json` | G1 预审 5 | DeepSeek **flash** 验收：N1–N4/P1/P2 PASS，P3/P4/abort 仍 broken | 已修复，见 FIXES §Flash 验收后修复 |
| `BYOK_JUDGE_V6_FLASH_ACCEPT.md/.json` | G1 预审 6 | DeepSeek **flash**：第 5 轮 P3/P4/abort PASS，又提出时间账本/证据缺失/official 次数 | 已修复，见 FIXES §Flash 第 6 轮后修复 |
| `BYOK_JUDGE_V7_FLASH_ACCEPT.md/.json` | G1 预审 7 | DeepSeek **flash**：主项 PASS，提出空条目/重复 trial_id/fake 账本 | 已修复，见 FIXES §Flash 第 7 轮后修复 |
| `BYOK_JUDGE_V8_FLASH_ACCEPT.md/.json` | G1 预审 8 | DeepSeek **flash**：CONCERN（无 scorer blocker，4 项审计清理） | 已修复，见 FIXES §Flash 第 8 轮 |
| `BYOK_JUDGE_V9_FLASH_ACCEPT.md/.json` | G1 预审 9 | DeepSeek **flash**：PASS 技术项，minor 快照/hash/对账残留 | 已修复，见 FIXES §Flash 第 8 轮（补） |
| `BYOK_JUDGE_V10_FLASH_ACCEPT.md/.json` | G1 预审 10 | DeepSeek **flash** 最终验收（待运行） | — |
| `evidence/part1_course_*_drill.json` | 协议演练证据 | 3 次 pause/resume 与 pause→resume→abort 的 runner 证据（纳入 HASHES） | — |
| `BYOK_JUDGE_V2_FIXES.md` | — | 预审→修复/残余风险逐条映射 | — |

## HASHES.json

记录被审对象的哈希（judge 源码、场景 XML、protocol、CONTRACT.json、manifest）。
由 `/comp-eval-audit` 在审计完成后写入；当前含 2026-10-22 G1 审计元信息（verdict=FAIL）。
