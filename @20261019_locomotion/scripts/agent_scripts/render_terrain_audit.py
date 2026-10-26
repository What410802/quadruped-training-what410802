"""Render official Part2 ability-field obstacles for a geometry audit.

Investigation helper only: renders the actual `terrain.zip` ability field (read-only)
so proxy/course differences can be inspected by a human before training.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import mujoco
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SCENE = ROOT / "assets/terrain/part2/ability_field/part2_ability_field.xml"
# Look-at points for representative official obstacles in map.xml.
OBSTACLES = {
    "high_platform_40cm": (21.75, 0.0, 0.25),
    "high_wall_40cm": (10.2, 21.0, 0.30),
    "slope_45deg": (51.0 + 2.0, 6.0, 1.0),
    "stairs_30cm": (63.0 + 1.5, 3.0, 0.90),
    "trench_30cm": (15.0 + 4.3, 9.0, 0.15),
    "plum": (7.5, 12.0, 0.20),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT.parent / "prep.d/results/terrain_audit")
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=400)
    ap.add_argument("--distance", type=float, default=3.2)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    model = mujoco.MjModel.from_xml_path(str(SCENE))
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    renderer = mujoco.Renderer(model, height=args.height, width=args.width)
    cam = mujoco.MjvCamera()
    mujoco.mjv_defaultCamera(cam)
    cam.distance = args.distance
    cam.elevation = -18.0
    cam.azimuth = 90.0
    for name, lookat in OBSTACLES.items():
        cam.lookat[:] = lookat
        renderer.update_scene(data, camera=cam)
        img = renderer.render()
        path = args.out / f"official_{name}.png"
        import imageio.v3 as iio
        iio.imwrite(path, img)
        print(f"wrote {path}")
    renderer.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
