# audits/ —— 独立审计结论

> 本目录只放**跨模型 verdict**（Codex）；executor 只收集路径与跑确定性预检。
> 每次审计的元信息必须含 reviewer/model/effort/threadId/date；被审对象哈希写 `HASHES.json`。
> 哈希变化 → 对应门禁失效，需重审（见 比赛工作流包的 `competition/shared-references/competition-gates.md` §3）。

| 文件 | 门禁 | 内容 | 状态 |
|---|---|---|---|
| `JUDGE_AUDIT.md/.json` | G1 | judge 规则忠实性/漏洞/协议诚实/证据链/合规/范围 | 未做 |
| `JUDGE_CROSSCHECK.md` | G1 | 盲写第二实现与现有 judge 的逐条比对 | 未做 |
| `SCORE_AUDIT.md` | G4 | 记分板数字 → 证据路径核对与白名单 | 未做 |
| `TRAIN_SYSTEM_AUDIT.md` | — | reward/课程/终止/观测契约系统性问题 | 未做 |
| `REDTEAM.md` | G5 | 冻结前"决赛为什么失败"红队 | 未做 |

## HASHES.json

记录被审对象的哈希（judge 源码、场景 XML、protocol、CONTRACT.json、manifest）。
由 `/comp-eval-audit` 在审计完成后写入；当前为空模板。
