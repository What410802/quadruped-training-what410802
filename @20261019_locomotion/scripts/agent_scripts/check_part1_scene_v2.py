#!/usr/bin/env python3
"""Scene v2 sanity check (MuJoCo): height-bar is statically supported and named geoms exist.

The 2026-10-22 stopped Codex session flagged that a slide-jointed beam might fall under
gravity before the robot touches it. This check simulates the empty scene and asserts the
beam stays within 1 cm of its initial height, plus the named surface geoms used by the
judge exist. Run under the repo pixi env (needs mujoco).

Usage (from MyMonoRepo.d):
  pixi run python @20261019_locomotion/scripts/agent_scripts/check_part1_scene_v2.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import mujoco

SCENE = Path("@20261019_locomotion/assets/terrain/part1/part1_eval_scene_v2.xml")
REQUIRED_GEOMS = [
    "height_bar_beam", "start_area", "high_wall", "gravel_pit_a", "gravel_pit_b",
    "t_stairs_y_low1", "t_stairs_y_low2", "t_stairs_y_low3", "t_stairs_top",
    "t_stairs_y_high1", "t_stairs_y_high2", "t_stairs_y_high3",
    "t_stairs_x_low1", "t_stairs_x_mid2", "t_stairs_x_high3",
    "bridge_blocks_0", "bridge_blocks_1", "bridge_blocks_2", "bridge_blocks_3",
    "bridge_blocks_4", "bridge_blocks_platform_l", "bridge_platform_r",
    "bridge_bands_0", "bridge_bands_1", "bridge_bands_2", "bridge_bands_platform_low",
    "slope_a", "slope_b",
]


def main() -> int:
    model = mujoco.MjSpec.from_file(str(SCENE)).compile()
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    missing = [n for n in REQUIRED_GEOMS
               if mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, n) < 0]
    bar = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "height_bar_beam_body")
    if bar < 0:
        print("FAIL: missing body height_bar_beam_body")
        return 1
    z0 = float(data.xpos[bar][2])
    for _ in range(1000):          # 5 s at 5 ms
        mujoco.mj_step(model, data)
    z1 = float(data.xpos[bar][2])
    drop = z0 - z1
    print(f"beam z: start={z0:.4f} after 5s={z1:.4f} drop={drop:.4f} m")
    if missing:
        print("FAIL missing geoms:", missing)
        return 1
    if drop > 0.01:
        print(f"FAIL: beam dropped {drop:.3f} m without contact")
        return 1
    print(f"scene v2 check: OK ({len(REQUIRED_GEOMS)} geoms, beam stable)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
