# HIM row0 model0 deployment artifact

Source: nwwolf_mjlab_training_release job12 `model_0` (official warm start).
Exported by `@20261019_locomotion/scripts/agent_scripts/export_him_policy.py`.

- Input: canonical 6x57 history, frame-major newest->oldest, 342 floats.
- Output: 16 raw actions, official HIM signed wheel scale (FL/RL +10, FR/RR -10).
- Local judge proxy on team scenes: total_score=410; **not** official ability_field score.
- Status: deployment config/policy copied for HIM path, but **not yet tested through rl_sar C++/ROS `/joy`**; do not claim deploy-ready.
