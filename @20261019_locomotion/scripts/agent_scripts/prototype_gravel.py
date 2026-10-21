"""Feasibility prototype: rigid "gravel" made of many free-joint bodies in a pit.

Investigation-only script (see docs/conventions.md §3.7). Two variants:
  dynamic: free joints, pieces settle under gravity inside a pit.
  static : same pieces welded to the world (cheap ground approximation).

Reports compile size, contact counts, CPU step time, escape count and final
kinetic energy. Used to decide whether dynamic gravel is affordable as a
training terrain (per env x num_envs) or only as an evaluation/fidelity scene.
"""

from __future__ import annotations

import argparse
import time

import mujoco
import numpy as np


def quat_from_rpy(rpy: tuple[float, float, float]) -> np.ndarray:
    q = np.zeros(4)
    mujoco.mju_euler2Quat(q, np.asarray(rpy, dtype=np.float64), "xyz")
    return q


def build_model(num_pieces: int, dynamic: bool, seed: int, timestep: float) -> mujoco.MjModel:
    rng = np.random.default_rng(seed)
    spec = mujoco.MjSpec()
    spec.option.timestep = timestep
    spec.option.gravity = (0.0, 0.0, -9.81)
    spec.visual.global_.offwidth = 640
    spec.visual.global_.offheight = 480

    world = spec.worldbody
    # Pit: floor + four walls. Interior 0.8 x 0.8 m, walls 0.25 m high.
    world.add_geom(
        name="pit_floor",
        type=mujoco.mjtGeom.mjGEOM_BOX,
        size=(0.5, 0.5, 0.02),
        pos=(0.0, 0.0, -0.02),
        rgba=(0.3, 0.3, 0.3, 1.0),
    )
    wall = 0.04
    for name, pos, size in (
        ("wall_xp", (0.42, 0.0, 0.125), (wall / 2, 0.5, 0.125)),
        ("wall_xm", (-0.42, 0.0, 0.125), (wall / 2, 0.5, 0.125)),
        ("wall_yp", (0.0, 0.42, 0.125), (0.5, wall / 2, 0.125)),
        ("wall_ym", (0.0, -0.42, 0.125), (0.5, wall / 2, 0.125)),
    ):
        world.add_geom(name=name, type=mujoco.mjtGeom.mjGEOM_BOX, size=size, pos=pos,
                       rgba=(0.25, 0.25, 0.25, 1.0))

    # Pieces: flattened chips / pebbles. Sizes 1.2-4.0 cm, thickness 0.4-1.4 cm.
    for i in range(num_pieces):
        half_len = rng.uniform(0.012, 0.035)
        half_wid = rng.uniform(0.008, 0.025)
        half_thk = rng.uniform(0.003, 0.010)
        # Spawn in a loose 3-D block above the pit; solver resolves overlaps.
        pos = (
            rng.uniform(-0.32, 0.32),
            rng.uniform(-0.32, 0.32),
            0.08 + rng.uniform(0.0, 0.45),
        )
        quat = quat_from_rpy(
            (rng.uniform(-0.6, 0.6), rng.uniform(-0.6, 0.6), rng.uniform(-np.pi, np.pi))
        )
        body = world.add_body(name=f"chip_{i:04d}", pos=pos, quat=quat)
        if dynamic:
            body.add_freejoint()
        shade = rng.uniform(0.35, 0.8)
        body.add_geom(
            type=mujoco.mjtGeom.mjGEOM_BOX,
            size=(half_len, half_wid, half_thk),
            rgba=(shade, shade * 0.85, shade * 0.65, 1.0),
            friction=(1.2, 0.02, 0.001),
        )
    return spec.compile()


def run_case(num_pieces: int, dynamic: bool, steps: int, seed: int) -> dict:
    model = build_model(num_pieces, dynamic, seed, timestep=0.002)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)

    ncon_max = 0
    t0 = time.perf_counter()
    for _ in range(steps):
        mujoco.mj_step(model, data)
        ncon_max = max(ncon_max, int(data.ncon))
    elapsed = time.perf_counter() - t0

    # Free-joint qpos: 7 per chip; if static there are no free joints.
    escaped = 0
    if dynamic and model.nq >= 7 * num_pieces:
        qpos = data.qpos.reshape(num_pieces, 7)
        xyz = qpos[:, :3]
        escaped = int(
            np.sum(
                (np.abs(xyz[:, 0]) > 0.45)
                | (np.abs(xyz[:, 1]) > 0.45)
                | (xyz[:, 2] < -0.05)
                | (xyz[:, 2] > 1.0)
            )
        )
    # Total kinetic/penetration-ish diagnostics.
    ke = float(np.sum(data.qvel**2))
    return {
        "pieces": num_pieces,
        "dynamic": dynamic,
        "steps": steps,
        "nq": model.nq,
        "nv": model.nv,
        "ngeom": model.ngeom,
        "ncon_max": ncon_max,
        "escaped": escaped,
        "cpu_ms_per_step": elapsed / steps * 1e3,
        "final_qvel2": ke,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", type=int, default=1500)
    parser.add_argument("--pieces", type=int, nargs="+", default=[50, 100, 200])
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    rows = []
    for n in args.pieces:
        rows.append(run_case(n, dynamic=True, steps=args.steps, seed=args.seed))
        rows.append(run_case(n, dynamic=False, steps=10, seed=args.seed))
    print("pieces dynamic   nq    nv  ngeom  ncon_max escaped  cpu_ms/step  qvel2")
    for r in rows:
        print(
            f"{r['pieces']:>4}  {str(r['dynamic']):>5}  {r['nq']:>5} {r['nv']:>5}"
            f" {r['ngeom']:>5}  {r['ncon_max']:>7}  {r['escaped']:>6}"
            f"  {r['cpu_ms_per_step']:>8.3f}  {r['final_qvel2']:.3e}"
        )


if __name__ == "__main__":
    main()
