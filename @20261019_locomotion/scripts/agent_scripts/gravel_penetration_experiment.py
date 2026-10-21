"""Standalone foot-on-gravel penetration experiment (not used by training).

A vertical prismatic probe with the Black 2 cm foot sphere and a chosen load is
released just above a deep bed of free stones.  Sink depth is measured relative
to the bed surface; repeated seeds give a design p50/p95 depth for a pre-baked
static gravel layer.  This is a simulation proxy, not a DEM or real-gravel test;
the stone bed uses 3-5 cm ellipsoids because 3-10 cm free stones at this scale
are too expensive for a standalone CPU experiment.
"""

from __future__ import annotations

import argparse
import json

import mujoco
import numpy as np

BED_HALF = 0.20
BED_DEPTH = 0.30
GROUND_Z = -0.15
STONE_R_MIN = 0.020
STONE_R_MAX = 0.045
FOOT_RADIUS = 0.02
DT = 0.002
SETTLE_STEPS = 500
PROBE_STEPS = 500
SEED0 = 20261021


def _random_bed(seed: int) -> list[tuple[float, float, float, float, float, float, float]]:
    """Regular dense 6 x 6 x 6 bed of 3-5 cm stones with small jitter."""
    rng = np.random.default_rng(seed)
    stones: list[tuple[float, float, float, float, float, float, float]] = []
    nx = ny = 6
    nz = 6
    cell = 2.0 * BED_HALF / nx
    for iz in range(nz):
        for iy in range(ny):
            for ix in range(nx):
                rx = rng.uniform(0.015, 0.025)
                ry = rng.uniform(0.015, 0.025)
                rz = rng.uniform(0.010, 0.020)
                x = -BED_HALF + (ix + 0.5) * cell + rng.uniform(-0.004, 0.004)
                y = -BED_HALF + (iy + 0.5) * cell + rng.uniform(-0.004, 0.004)
                z = GROUND_Z + (iz + 0.5) * (BED_DEPTH / nz) + rng.uniform(-0.002, 0.002)
                stones.append((x, y, z, rx, ry, rz, rng.uniform(0.0, 2.0 * np.pi)))
    return stones


def _build(seed: int, probe_mass: float) -> tuple[mujoco.MjModel, mujoco.MjData, float]:
    rng = np.random.default_rng(seed)
    spec = mujoco.MjSpec()
    spec.option.timestep = DT
    spec.option.gravity = [0.0, 0.0, -9.81]
    spec.option.cone = mujoco.mjtCone.mjCONE_ELLIPTIC
    spec.option.impratio = 10.0

    spec.worldbody.add_geom(type=mujoco.mjtGeom.mjGEOM_PLANE, size=[2, 2, 0.1], pos=(0.0, 0.0, GROUND_Z))

    wall_t = 0.02
    wall_h = BED_DEPTH
    for x, sx in ((BED_HALF + wall_t, wall_t), (-BED_HALF - wall_t, wall_t)):
        body = spec.worldbody.add_body(pos=(x, 0.0, GROUND_Z + wall_h * 0.5))
        body.add_geom(type=mujoco.mjtGeom.mjGEOM_BOX, size=(sx, BED_HALF + 2 * wall_t, wall_h * 0.5))
    for y, sy in ((BED_HALF + wall_t, wall_t), (-BED_HALF - wall_t, wall_t)):
        body = spec.worldbody.add_body(pos=(0.0, y, GROUND_Z + wall_h * 0.5))
        body.add_geom(type=mujoco.mjtGeom.mjGEOM_BOX, size=(BED_HALF + 2 * wall_t, sy, wall_h * 0.5))

    for i, (x, y, z, rx, ry, rz, yaw) in enumerate(_random_bed(seed)):
        body = spec.worldbody.add_body(name=f"g{i:03d}", pos=(x, y, z))
        body.add_freejoint()
        body.add_geom(
            type=mujoco.mjtGeom.mjGEOM_ELLIPSOID,
            size=(rx, ry, rz),
            density=2200.0,
            friction=(1.2, 0.02, 0.001),
            solref=(0.02, 1.0),
            solimp=(0.9, 0.95, 0.001, 0.5, 2.0),
            contype=1,
            conaffinity=1,
        )
        body.quat = [float(np.cos(yaw * 0.5)), 0.0, 0.0, float(np.sin(yaw * 0.5))]

    stones = _random_bed(seed)
    center_tops = [z + rz for x, y, z, rx, ry, rz, _ in stones if abs(x) < 0.10 and abs(y) < 0.10]
    initial_surface = float(np.mean(center_tops)) if center_tops else float(BED_DEPTH)

    # Foot probe starts just above the settled surface (5 mm drop), not from the
    # top of the container: this measures a step/load, not an impact test.
    probe = spec.worldbody.add_body(name="probe", pos=(0.0, 0.0, initial_surface + FOOT_RADIUS + 0.005))
    probe.gravcomp = 1.0
    probe.add_geom(type=mujoco.mjtGeom.mjGEOM_SPHERE, size=(FOOT_RADIUS,), mass=probe_mass, friction=(1.0, 0.02, 0.001), name="probe_geom")
    joint = probe.add_joint(name="probe_z", type=mujoco.mjtJoint.mjJNT_SLIDE, axis=(0.0, 0.0, 1.0))
    joint.damping = [0.0, 0.0, 2.0]

    model = spec.compile()
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    return model, data, initial_surface


def _measure_surface(model: mujoco.MjModel, data: mujoco.MjData) -> float:
    adr = model.jnt_qposadr[model.jnt_type == mujoco.mjtJoint.mjJNT_FREE]
    # central top surface from free stones
    tops = []
    for qadr in adr:
        x, y, z = data.qpos[qadr : qadr + 3]
        if abs(x) < 0.10 and abs(y) < 0.10:
            # body has single sphere geom; use geom size via body geomadr
            pass
    # simpler: use all free-body spheres
    for i in range(model.nbody):
        jntadr = int(model.body_jntadr[i])
        if jntadr < 0 or model.jnt_type[jntadr] != mujoco.mjtJoint.mjJNT_FREE:
            continue
        qadr = int(model.jnt_qposadr[jntadr])
        x, y, z = data.qpos[qadr : qadr + 3]
        if abs(x) < 0.10 and abs(y) < 0.10:
            g = int(model.body_geomadr[i])
            tops.append(z + max(model.geom_size[g]))
    return float(np.mean(tops)) if tops else float("nan")


def run_one(seed: int, probe_mass: float) -> dict[str, float]:
    model, data, initial_surface = _build(seed, probe_mass)
    surface = initial_surface
    probe_geom = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "probe_geom")
    probe_body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "probe")
    probe_joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "probe_z")
    probe_qadr = model.jnt_qposadr[probe_joint]

    # Settle the bed with the probe held (gravcomp=1), then place the foot just
    # above the settled surface and release it. This separates compaction from
    # foot penetration.
    for _ in range(SETTLE_STEPS):
        mujoco.mj_step(model, data)
    surface = _measure_surface(model, data)
    target_center = surface + FOOT_RADIUS + 0.005
    data.qpos[probe_qadr] = target_center - model.body_pos[probe_body, 2]
    mujoco.mj_forward(model, data)
    model.body_gravcomp[probe_body] = 0.0
    for _ in range(PROBE_STEPS):
        mujoco.mj_step(model, data)
    foot_bottom = float(data.geom_xpos[probe_geom, 2]) - FOOT_RADIUS
    penetration = max(0.0, surface - foot_bottom)
    floor_hit = bool(foot_bottom <= GROUND_Z + 0.005)
    return {"seed": float(seed), "surface_z": surface, "foot_bottom": foot_bottom, "penetration_m": penetration, "floor_hit": floor_hit}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=SEED0)
    parser.add_argument("--trials", type=int, default=10)
    parser.add_argument("--probe-mass", type=float, default=13.17)
    parser.add_argument("--json", type=str, default="")
    args = parser.parse_args()
    results = [run_one(args.seed + i, args.probe_mass) for i in range(args.trials)]
    depths = np.array([r["penetration_m"] for r in results])
    summary = {
        "trials": args.trials,
        "probe_mass_kg": args.probe_mass,
        "foot_radius_m": FOOT_RADIUS,
        "penetration_m": depths.tolist(),
        "floor_hit_count": int(sum(r["floor_hit"] for r in results)),
        "p50_m": float(np.percentile(depths, 50)),
        "p95_m": float(np.percentile(depths, 95)),
        "max_m": float(depths.max()),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.json:
        with open(args.json, "w") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
