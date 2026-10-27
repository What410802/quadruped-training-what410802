# Phase 2（deployment）迁移状态（2026-10-27，追加记录）

本文件是旧仓对 Phase 2 迁移的追加说明：Phase 2 的代码与证据已迁到新 umbrella/deployment 仓，旧仓只保留这份状态与指针，不再维护第二阶段实现。

## 已完成

- P2-00 环境自包含：umbrella `pixi` 的 deploy env（ROS 2 Humble + colcon + MuJoCo 3.11 + CPU torch），无主机 ROS 依赖；`pixi install -e deploy`/`colcon build` 实测通过。
- P2-01/P2-02：上游 `fan-ziqi/rl_sar@e5c2f41` 基线 + 源码 delta；`rl_sar`/`quadruped_ros2` 包结构、`robots/*/robot.yaml` manifest、fail-loud 契约校验。
- P2-03~P2-06：策略加载/观测历史/动作限幅、反馈驱动时钟（control 5 ms / inference 20 ms）、统一 FSM、NaN 输入侧防护（sim_node 拒绝非有限 `/mit_command`，rl_sim 观测/动作 sanitize）；MuJoCo 压力证据见新仓 `deployment/docs/migration/p2-04-p2-06-smoke.md`。
- P2-07：Part1 官方场景规范化（两机型 `robots/*/scene_part1.xml`）、Part2 官方生成（`map.xml`）与 interim 场景逐文件对比：20/20 XML 字节一致，B3 结论为保留 interim 运行副本。
- P2-08：130 个策略权重全量入库（177,814,494 bytes）+ `policy-manifest.json`；curated 6 个策略 manifest 校验 6/6、0 problems。
- P2-09：统一 part/level/policy launch；headless 自检、策略加载、频率/反馈验证。
- P2-10：delta 归档脚本与状态：旧 delta 196/196 文件在新仓落位、0 missing；quadruped_ros2 13 文件对照。
- P2-11 L2：supported 组合 blackW×Part1、black×Part1、blackW×Part2 三组 headless 矩阵 PASS；trace 全 finite、反馈 dt=2 ms、12/16 dof。
- P2-11 验收按 Phase 2 口径完成：包独立 build/launch + 契约 + smoke/matrix/NaN/spawn 证据通过；旧 ws↔新仓 `/motor_state` 的 L1 逐元素比较不是 Phase 2 gate（属于 P3-13 迁移证据）。

## 未完成 / 明确风险

- P2-11 L1 **已移出 Phase 2 验收**：旧 ws↔新仓 trace 对照是 P3-13 旧/新迁移证据，不是 deployment 功能稳定性判据；同 binary 两次运行已不一致，逐元素 bitwise 不可达。历史尝试与归因保留在新仓 `deployment/docs/migration/p2-11-acceptance.md`、`deployment/artifacts/phase2/equiv/`，Phase 3 文档记录该局限即可。
- `check_walk_blackw.py`：旧包平地 fixed-command regression，可选、非 Phase 2 gate（旧审计也指出其覆盖有限和 flat 写死问题）。
- black×Part2（B4）延后，最终"两机型×两赛项"还差该组合。
- Phase 3 eval runner/回放、高墙训练侧 rollout 探针与 parity、P3-12 矩阵/QA/spec 冻结仍在进行。

## 新仓指针

- umbrella：`What410802/robocon-intrasquad`（spec `docs/contracts/evaluation-spec.md`、eval `eval/robocon_eval/`）
- deployment：`What410802/robocon-intrasquad-deploy`（证据目录 `deployment/docs/migration/`、`deployment/artifacts/phase2/`）
- training：`What410802/robocon-intrasquad-training`（高墙 P3-14 提交 `1665fe6`）
- 关键 deployment 提交：`ded276f`（P2-11 L1 归因）、`0df8555`（L2 矩阵）、`9ab5ec0`（P2-10）、`17e52b7`（P2-08）、`74152b4`（Part1 场景）
