"""Check Part 2 plum dimensions, gaps and central symmetry from the MJCF."""

from __future__ import annotations

import argparse
from pathlib import Path

import mujoco
import numpy as np

DEFAULT = "@20261019_locomotion/assets/terrain/part2/part2_plum.xml"


def aabb(model: mujoco.MjModel, gid: int) -> tuple[np.ndarray, np.ndarray]:
    center = np.array(model.geom_pos[gid], dtype=float)
    half = np.array(model.geom_size[gid], dtype=float)
    return center - half, center + half


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", default=DEFAULT)
    args = parser.parse_args()
    model = mujoco.MjSpec.from_file(args.scene).compile()
    ids = {}
    for name in ("plum_platform_left", "plum_platform_right"):
        ids[name] = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, name)
    cubes = []
    for i in range(6):
        g = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, f"plum_cube_{i}")
        lo, hi = aabb(model, g)
        cubes.append((i, lo, hi))
        print(f"cube_{i}: corners ({lo[0]:.3f},{lo[1]:.3f},{lo[2]:.3f})..({hi[0]:.3f},{hi[1]:.3f},{hi[2]:.3f})")
    llo, lhi = aabb(model, ids["plum_platform_left"])
    rlo, rhi = aabb(model, ids["plum_platform_right"])
    print(f"left platform: {llo}..{lhi}")
    print(f"right platform: {rlo}..{rhi}")
    assert np.allclose(lhi[0], 0.8) and np.allclose(rlo[0], 2.7), "platform x bounds wrong"
    assert np.allclose(lhi[2], 0.2) and np.allclose(rhi[2], 0.2), "platform height wrong"
    top = [c for c in cubes if abs(c[1][1] - 0.1) < 1e-6]
    bottom = [c for c in cubes if abs(c[1][1] - 0.5) < 1e-6]
    assert len(top) == 3 and len(bottom) == 3, "expected 3 cubes per row"
    # Left/right first gaps 100 / 400 mm, same-row gaps 400 mm.
    top_x = sorted(c[1][0] for c in top)
    bottom_x = sorted(c[1][0] for c in bottom)
    assert np.allclose(top_x[0] - lhi[0], 0.1), f"top-left gap {top_x[0]-lhi[0]}"
    assert np.allclose(bottom_x[0] - lhi[0], 0.4), f"bottom-left gap {bottom_x[0]-lhi[0]}"
    assert np.allclose(rlo[0] - max(c[2][0] for c in top), 0.4), "top-right gap"
    assert np.allclose(rlo[0] - max(c[2][0] for c in bottom), 0.1), "bottom-right gap"
    assert all(np.allclose(top[i+1][1][0] - top[i][2][0], 0.4) for i in range(2)), "top row gap"
    assert all(np.allclose(bottom[i+1][1][0] - bottom[i][2][0], 0.4) for i in range(2)), "bottom row gap"
    # Central symmetry: reflect across x=1.75 and y=0.4, swapping rows.
    center = np.array([1.75, 0.4, 0.0])
    for i, lo, hi in cubes:
        mirrored_lo = np.array([2*center[0]-hi[0], 2*center[1]-hi[1], lo[2]])
        mirrored_hi = np.array([2*center[0]-lo[0], 2*center[1]-lo[1], hi[2]])
        found = any(np.allclose(mirrored_lo, lo2, atol=1e-6) and np.allclose(mirrored_hi, hi2, atol=1e-6)
                    for _, lo2, hi2 in cubes)
        assert found, f"cube_{i} has no central mirror"
    assert np.allclose(rhi[0] - llo[0], 3.5), "overall length should be 3.5 m"
    print("OK: 3+3 cubes, gaps and central symmetry valid")


if __name__ == "__main__":
    main()
