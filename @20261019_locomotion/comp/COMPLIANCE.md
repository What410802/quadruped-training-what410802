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
