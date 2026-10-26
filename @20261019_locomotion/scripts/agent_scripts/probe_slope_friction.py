"""Probe whether slope_45deg is traction-limited in the official judge physics.

The official scenes use geom friction 1.0; a 45 deg slope needs tan(45)=1.0, i.e.
zero margin.  Re-run the same BC policy on the same scene with wheel/terrain
friction raised (test-only, NOT the official judge) to separate "policy cannot"
from "physics does not allow".
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path("/home/bis/BiS.d/Code.d/RoboCon/MyMonoRepo.d")
TASK = ROOT / "@20261024_blackw"
sys.path.insert(0, str(TASK / "scripts"))
sys.path.insert(0, str(ROOT / "@20261019_locomotion/scripts/agent_scripts"))
import eval_blackw_part2 as ev  # noqa: E402

POLICY = TASK / "ws/src/rl_sar_blackw/policy/blackW/comp_bc_v5"
LEVELS = json.loads((ev.LEVELS).read_text(encoding="utf-8"))["levels"]
level = next(e for e in LEVELS if e["key"] == "slope_45deg")
scene = ev.SCENE_DIR / level["scene"]
cfg = ev.load_policy_config(POLICY)
command = np.array([0.3, 0.0, 0.0])
seconds = float(level["seconds"])

print(f"scene={scene.name} command={command} wheel_radius={ev.WHEEL_RADIUS_M}")
for mu in (1.0, 1.2, 1.5, 2.0):
    runner = ev.PolicyRunner(scene, POLICY / "policy.pt", cfg,
                             physics_dt=0.002, policy_dt=0.02)
    runner.model.geom_friction[:, 0] = mu
    spawn = np.asarray(level["spawn"], dtype=np.float64).copy()
    runner.reset_pose(spawn=spawn[:3], yaw=float(spawn[3]))
    judge = ev.Part2OfficialJudge(level)
    runner.warmup(command, seconds=0.4)
    max_z = 0.0
    for _ in range(int(round(seconds / 0.02))):
        runner.infer(command)
        runner.step()
        pos, tilt = runner.base()
        wxs, wzs = runner.wheel_states()
        judge.update(0.0, pos, tilt, wheel_x=wxs, wheel_z=wzs)
        max_z = max(max_z, float(pos[2]))
    res = judge.finalize("timeout")
    print(f"mu={mu:3.1f} -> judge={res['status']:7s} reason={res['reason']:20s} "
          f"max_root_z={max_z:.2f} detail={ {k: round(v,2) for k,v in res['detail'].items()} }")
