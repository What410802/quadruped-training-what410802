# 当前状态（2026-10-26，跨线）

> 本页只写"当前真值 + 下一步 + 阻塞"；细节在各自线文档，旧长版归档在 [`../90-archive/legacy-status-2026-10-26.md`](../90-archive/legacy-status-2026-10-26.md)。

## 进展（事实）

- **比赛**：2026-11-04 队内赛；两赛项（障碍赛 900 + 越障能力 1300）占 70%，答辩 30%；D-3（11-01）起不再开新训练线。
- **Part2 交付现状**：`comp_bc_v5` 的 judge v5 750/743 为**未审计 executor 证据**；2026-10-26 两份 BYOK+RFR 独立评审（GLM different-family）G1/G4 均 **FAIL/REJECT**：judge v5 无标定/与 V2 漂移/高度带谓词、comp_bc_v5 无 comp/eval 三件套、部署 smoke 5/20 与分数矛盾且 smoke 本身无效（旧 proxy 场景 + 官方权重对照也 5/20 + 数值爆炸；场景已修为官方 `part2_off_*`，待重跑）。详见 [`../../comp/audits/2026-10-26-BYOK-RFR-SUMMARY.md`](../../comp/audits/2026-10-26-BYOK-RFR-SUMMARY.md)。能力上限约 850（s100 m650，同样未审计）；trench30/plum 属深度项。
- **验收口径**：2026-10-26 已改为覆盖集协议（零摔倒 + 可行穿越子集全过 + held-out），旧的 8/8、16/16、<1% 指标全部作废；协议见 [`../20-part2-shared/acceptance-eval-protocol.md`](../20-part2-shared/acceptance-eval-protocol.md)。
- **代码审计闭环**：round-1 两份独立审计（PPO 核心、部署/作业）均 BLOCKED；已修第一批（sim 逐关节力矩、部署策略导入/校验工具、DR 恢复、resume lr/继承控制、plum 奖励、README 键位等）；round-2 未 PASS，剩余阻塞逐项见 [`../21-part2-ppo/audit-blockers.md`](../21-part2-ppo/audit-blockers.md)。
- **HIM 线**：HIM agent 已停止；其本地/远程改动已原样分批提交（nwwolf 仓 `pre-reorg-him-2026-10-26` tag）；HIM gate 假测量与发散问题记录在其文档（22 目录），当前不作为交付主线。
- **文档重组**：2026-10-26 完成（本目录树 + INDEX）；仓库目录不合并/不改名，命名规范见 [`../INDEX.md`](../INDEX.md) §三。

## 下一步（按优先级）

1. 第二轮修复已完成（P1 语义项、F3/F6/F7/F14/F15、job 契约、F2 smoke 工具；见 [`../21-part2-ppo/audit-blockers.md`](../21-part2-ppo/audit-blockers.md) §0）；下一步：build 后跑 F2 smoke（逐档 PASS/FAIL + F1 验证）、补 P2 清单、开 round-2 独立审计至 PASS。
2. 按新验收协议实现覆盖集评测（judge 侧 + 部署侧 smoke 对拍），替换旧 gate/固定次数工具。
3. Part2 归因实验（A6：resume 契约、guard 锚点、低档回放、课程、model soup），每个实验按覆盖集评估。
4. BC 数据/教师能力审计 → 大范围鲁棒转向的 BC/DAgger 计划。
5. 多策略切换 runbook + 演示验收（Part2 场景 headless 冒烟）。

## 阻塞

- 审计未 PASS 前不恢复大规模训练（用户 2026-10-26 指示）。
- `@20261024_blackw/ws` 生成策略目录（约 128 个）与官方 mesh 资产不入库（gitignore），演示前需按 [`../20-part2-shared/deployment-contract.md`](../20-part2-shared/deployment-contract.md) 恢复。
- 实机驱动链路未实现（详见部署契约文档）。
