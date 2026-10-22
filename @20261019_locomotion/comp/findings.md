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
