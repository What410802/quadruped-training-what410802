#!/usr/bin/env python3
"""Evaluate a blackW policy on the official 45 deg slope scene at chosen terrain friction.

Why: the official judge scene uses MuJoCo's default geom friction 1.0; a 45 deg
slope needs tan(45 deg) = 1.0, i.e. **zero static margin** for a steady powered
climb.  This probe re-runs the same judge geometry/predicate with the terrain
friction overridden (test-only) so a policy trained with raised training friction
can be evaluated both at mu=1.2 and at the official mu=1.0, and the run-up effect
can be measured (entry speed, reached height, joint speed peaks).

Deployment limits referenced by the report come from
``@20261007_assignment/docs/safety-limits.md`` section 3 and
``@20261024_blackw/ws/src/rl_sar_blackw/include/command_limit.hpp``:
controller-side ``dq_des`` cap 20 rad/s and implied-torque budget 33.5 N*m; the
MuJoCo model itself has no joint velocity limit.

Usage (from repo root, CPU is enough):
  pixi run python @20261019_locomotion/scripts/agent_scripts/probe_slope_friction.py \
      --policy @20261024_blackw/ws/src/rl_sar_blackw/policy/blackW/comp_bc_v5 \
      --mu 1.0 --mu 1.2 --command 0.3
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import mujoco
import numpy as np

ROOT = Path("/home/bis/BiS.d/Code.d/RoboCon/MyMonoRepo.d")
TASK = ROOT / "@20261024_blackw"
sys.path.insert(0, str(TASK / "scripts"))
sys.path.insert(0, str(ROOT / "@20261019_locomotion/scripts/agent_scripts"))
import eval_blackw_part2 as ev  # noqa: E402

DQ_DES_CAP = 20.0  # deployment command limiter (rad/s), command_limit.hpp default
LEVEL_KEY = "slope_45deg"
RISE_M = 2.0
GRAVITY = 9.81


def energy_table(mass: float, radius: float) -> None:
    print(f"robot_mass={mass:.2f} kg  slope_rise={RISE_M:.2f} m  delta_PE={mass*GRAVITY*RISE_M:.1f} J")
    print(f"pure ballistic needs v=sqrt(2gh)={np.sqrt(2*GRAVITY*RISE_M):.2f} m/s "
          f"-> wheel {np.sqrt(2*GRAVITY*RISE_M)/radius:.1f} rad/s "
          f"(dq_des cap {DQ_DES_CAP:.0f} rad/s)")
    print("run-up reduces the required average friction (mu_eff = tan45 * (1 - v^2/(2gh))):")
    for v in (0.5, 1.0, 1.5, 2.0, DQ_DES_CAP * radius):
        gain = v * v / (2 * GRAVITY * RISE_M)
        print(f"  entry {v:4.2f} m/s: KE {0.5*mass*v*v:5.1f} J = {gain*100:4.1f}% of delta_PE, "
              f"wheel {v/radius:5.1f} rad/s, mu_eff={1-gain:.3f}")


def robot_mass(scene: Path) -> float:
    model = mujoco.MjModel.from_xml_path(str(scene))
    total = 0.0
    for i in range(model.nbody):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, i) or ""
        if name in ("world", "obstacle"):
            continue
        total += float(model.body_mass[i])
    return total


def rollout(policy_dir: Path, level: dict, scene: Path, cfg: dict, mu: float,
            command: np.ndarray, runway_extra: float, seconds: float, device: str) -> dict:
    runner = ev.PolicyRunner(scene, policy_dir / "policy.pt", cfg)
    runner.model.geom_friction[:, 0] = mu
    spawn = np.asarray(level["spawn"], dtype=np.float64).copy()
    spawn[0] -= runway_extra
    runner.reset_pose(spawn=spawn[:3], yaw=float(spawn[3]))
    judge = ev.Part2OfficialJudge(level)
    names = list(cfg["joint_names"])
    wheel_slots = [i for i, n in enumerate(names) if "wheel" in n]
    leg_slots = [i for i, n in enumerate(names) if "wheel" not in n]
    runner.warmup(command, seconds=0.4)
    base_x = float(level["obstacle_bbox"]["min"][0])
    max_z = -1.0
    max_wheel = max_leg = 0.0
    entry_speed = None
    for _ in range(int(round(seconds / 0.02))):
        runner.infer(command)
        runner.step()
        pos, tilt = runner.base()
        wxs, wzs = runner.wheel_states()
        judge.update(0.0, pos, tilt, wheel_x=wxs, wheel_z=wzs)
        max_z = max(max_z, float(pos[2]))
        qd = np.abs(runner.data.qvel[runner.vadr])
        max_wheel = max(max_wheel, float(qd[wheel_slots].max()))
        max_leg = max(max_leg, float(qd[leg_slots].max()))
        if entry_speed is None and float(pos[0]) >= base_x:
            entry_speed = float(np.linalg.norm(runner.data.qvel[0:2]))
    verdict = judge.finalize("timeout")
    return dict(mu=mu, verdict=verdict["status"], reason=verdict["reason"],
                max_root_z=max_z, entry_speed=entry_speed,
                max_wheel_qvel_rad_s=max_wheel, max_leg_qvel_rad_s=max_leg,
                wheel_over_dq_cap=max_wheel > DQ_DES_CAP)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", type=Path,
                    default=TASK / "ws/src/rl_sar_blackw/policy/blackW/comp_bc_v5")
    ap.add_argument("--mu", type=float, action="append", default=None,
                    help="terrain friction override(s), default: 1.0 and 1.2")
    ap.add_argument("--command", type=float, nargs=3, default=[0.3, 0.0, 0.0])
    ap.add_argument("--runway-extra", type=float, default=0.0)
    ap.add_argument("--seconds", type=float, default=18.0)
    ap.add_argument("--device", default="cpu")
    args = ap.parse_args()

    levels = json.loads(ev.LEVELS.read_text(encoding="utf-8"))["levels"]
    level = next(e for e in levels if e["key"] == LEVEL_KEY)
    scene = ev.SCENE_DIR / level["scene"]
    cfg = ev.load_policy_config(args.policy)
    radius = float(cfg.get("wheel_radius", 0.103))
    print(f"policy={args.policy}")
    energy_table(robot_mass(scene), radius)
    mus = args.mu or [1.0, 1.2]
    print(f"\nscene={scene.name} command={args.command} runway_extra={args.runway_extra} "
          f"seconds={args.seconds}")
    print(f"{'mu':>5s} {'verdict':>9s} {'max_root_z':>10s} {'entry_v':>8s} "
          f"{'max_wheel':>10s} {'max_leg':>8s}  over_dq_cap")
    for mu in mus:
        out = rollout(args.policy, level, scene, cfg, mu,
                      np.asarray(args.command, dtype=np.float64),
                      args.runway_extra, args.seconds, args.device)
        print(f"{out['mu']:5.2f} {out['verdict']:>9s} {out['max_root_z']:10.2f} "
              f"{(out['entry_speed'] or 0):8.2f} {out['max_wheel_qvel_rad_s']:10.1f} "
              f"{out['max_leg_qvel_rad_s']:8.1f}  {out['wheel_over_dq_cap']}")
        print(f"      reason={out['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
