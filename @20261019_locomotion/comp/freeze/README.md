# freeze/ —— C5 冻结清单

由 `/comp-freeze` + `scripts/agent_scripts/comp_freeze.py` 生成：

- `FREEZE_MANIFEST.{md,json}`：多仓 commit/dirty、uv.lock hash、权重/导出/场景/judge/protocol 的 sha256；
- `REPLAY.md`：固定协议回归回放（≥2 次，success 序列一致）；
- `FALLBACK.md`：兜底策略与切换命令；
- `FREEZE_NOTES.md`：候选选择理由。

规则：dirty repo 不允许冻结；冻结后只允许关键 bug 修复且 `freeze_version` +1。
当前状态：未开始（需先过 G1，并完成 C3 训练与 C4 整合）。
