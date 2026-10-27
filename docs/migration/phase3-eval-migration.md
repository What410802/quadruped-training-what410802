# Phase 3（eval）迁移状态（2026-10-27，追加记录）

第三阶段评测实现已迁到 umbrella 仓 `eval/`，本文件只记录状态与指针。

## 已完成（有测试/证据）

- 合同/计分：`eval/robocon_eval/data/contract.json`（v2，T 台阶 50/50）、`contract.py`/`scoring.py` 与 20+ 单测。
- Part1 judge V2.1：zones/7 障碍/整场协议/conformance（14 组）；T 台阶方向 50/50；高墙支撑点投影 + `wall_side_bypass`。
- Part2 judge：V2（黑足式）迁移 + self-test；v5（blackW 轮式）迁移并因高墙 spec 变更 bump 到
  `v6-wall-support-projection-2026-10-27`，含支撑点投影/侧向失败测试。
- 官方场景：Part1 规范化（两机型 `robots/*/scene_part1.xml`）；Part2 官方 map.xml 生成与 interim 场景
  20/20 byte-identical（B3 结论保留 interim）。
- Trace/回放：JSONL 契约；deploy `/eval_state`（base/feet/contact/bar_z/cmd/cmd_step/q/dq/tau）；
  `robocon-eval replay-part1/part2-v2/part2-v5`；deploy→eval 端到端已验证。
- P3-01：`eval/CONTRACT-DECISIONS.md`、`eval/artifacts/HASHES.json`/`FREEZE.json`；
- P3-10 基础：`robocon-eval audit-hashes`/`freeze`；P3-12：`robocon-eval matrix` 4 组合；
- P3-13 部分：`robocon-eval consistency` 跨仓判据审计 11 项全 PASS（contract ↔ judges ↔ training ↔ levels）。
- P3-14：训练侧高墙 parity `PARITY OK`，wall crossing helper 单测 3/3，env-level `wall_env_probe.py` PASS（training `7aae13b`）；完整 trained-policy rollout 作为可选（task-specific spawn/command 未配）。

## 未完成

- P3-05/06/07 真实轨迹 golden replay（旧 diagnostics 无 `traj`，需新录制）；
- P3-09 确定性 MuJoCo runner、P3-10 trials/summary/SCOREBOARD、P3-11 calibration；
- P3-13 冻结/QA、旧仓最终验收证据；
- P2-11 L1 旧/新 trace 比较已按范围纠正：它是 P3-13 旧/新迁移证据，不是 Phase 2 deployment 验收 gate；same-binary 两次已不同，逐元素 bitwise 不可达，Phase 3 文档记录该局限即可（不阻塞 deployment 验收）。

## 新仓指针

- umbrella `What410802/robocon-intrasquad`：`eval/`、`docs/contracts/evaluation-spec.md`；
- deployment `What410802/robocon-intrasquad-deploy`：`docs/migration/`、`artifacts/phase2/`；
- training `What410802/robocon-intrasquad-training`：`5ecc329`（P3-14）。
- 关键 commit：umbrella `63e4185`（consistency）、`7614301`（v5 golden metadata）、`ab54331`（matrix）；
  deployment `a524395`（repeatability）、`b13c02a`（L1 attribution）。

## 冻结记录（2026-10-27）

- 规范/决策已冻结：`docs/contracts/evaluation-spec.md` 标 `frozen-v1.0`，`eval/CONTRACT-DECISIONS.md` 标 `frozen-v2`；`eval/artifacts/FREEZE.json`（schema 2）含 spec/docs sha256、git heads、QA 指针。
- 最终预检：`robocon-eval qa` → 9 项 PASS（contract/consistency 15/15/hash gate/calibration 92/92/matrix 4/golden part1+part2v5/self-test 29）；umbrella head `5f22151`（FREEZE 记录）、部署 `e17cf57`、训练 `5ecc329`，dirty=false。
- 仍属已知限制/可选：旧 diagnostics 无轨迹故旧/新完整 golden replay 不做；blackW 轮式 runner 为可选；正式 policy trial campaign 未跑（SCOREBOARD 标 not_run）；black×Part2 B4 延后。

- 最终 QA/FREEZE 刷新：training head `7aae13b`、umbrella head 见 `eval/artifacts/FREEZE.json`；`robocon-eval qa` 仍全 PASS。
