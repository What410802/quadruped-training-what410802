# 合规检查（comp_compliance.py）

- 契约：`comp/CONTRACT.json`（robocon-2026-internal-v1）
- 证据：`comp/compliance_evidence.json`
- overall：**PASS**

| 检查项 | verdict | 说明 |
|---|---|---|
| actor_obs_dim | PASS | 契约 45 / 证据 45 |
| action_dim | PASS | 契约 12 / 证据 12 |
| forbidden_sensors | PASS | obs_fields 未命中禁用传感器名 |
| world_truth_scope | PASS | world_truth_in_obs=False（规则：真值仅可用于生成速度指令） |
| part2_rl_only | PASS | part2_has_fixed_action_sequence=False（规则要求仅 RL） |
| torque:hip | PASS | 证据 20.0 N·m / 上限 25.0 N·m |
| torque:thigh | PASS | 证据 20.0 N·m / 上限 25.0 N·m |
| torque:calf | PASS | 证据 20.0 N·m / 上限 60.0 N·m |

## 范围说明（2026-10-24）

- 上表的 45 维 actor 证据对应**当前部署 baseline**（blind 策略）。
- C2 视觉主线的 `black-basic-obstacle-depth` 是**实验训练任务**（actor = 45 proprio + 深度 CNN latent = 109 维），既未冻结也未部署；它使用**模拟深度相机**（规则允许、CONTRACT 选此路线、不用雷达），不含 heightmap/足底力/机身高度等禁用传感器。等该策略成为候选部署权重时，需要新做一份 `compliance_evidence`（obs dim、相机外参/噪声/延迟说明）再跑 `comp_compliance.py`。
- 训练侧新增的三项安全网（obs/action clip、`bad_sim_state` 终止）不属于合规证据；动作上限仍是 ±20 N·m（与 baseline 一致）。
