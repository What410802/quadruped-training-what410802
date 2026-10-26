#!/usr/bin/env python3
"""Summarise the RL_DEBUG_OBS dump from rl_sim (`/tmp/rl_obs_debug.csv`).

rl_sim writes 60 frames when started with RL_DEBUG_OBS=1, one line per inference:
    obs_0,...,obs_56;act_0,...,act_15
The first frame (frame 0) is the freshest observation, i.e. the one the policy sees;
comparing its obs/action against the Python judge (same MuJoCo scene + policy) is the
intended use (audit F14: the probe existed but nothing read it).

Usage:
    RL_DEBUG_OBS=1 pixi run ros2 launch rl_sar_blackw rl_sim_blackw.launch.py ...
    pixi run python @20261024_blackw/scripts/read_rl_obs_debug.py --csv /tmp/rl_obs_debug.csv
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

OBS_DIM = 57
ACT_DIM = 16
TERMS = ("commands", "ang_vel", "gravity", "dof_pos", "dof_vel", "actions")
TERM_SLICES = {"commands": (0, 3), "ang_vel": (3, 6), "gravity": (6, 9),
               "dof_pos": (9, 25), "dof_vel": (25, 41), "actions": (41, 57)}


def parse(path: Path) -> list[tuple[list[float], list[float]]]:
    rows: list[tuple[list[float], list[float]]] = []
    for ln, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        raw = raw.strip()
        if not raw or raw.startswith("#"):
            continue
        if ";" not in raw:
            raise SystemExit(f"{path}:{ln}: expected 'obs;act', got {raw[:40]!r}")
        obs_s, act_s = raw.split(";", 1)
        obs = [float(v) for v in obs_s.split(",") if v != ""]
        act = [float(v) for v in act_s.split(",") if v != ""]
        if len(obs) != OBS_DIM or len(act) != ACT_DIM:
            raise SystemExit(
                f"{path}:{ln}: dims obs={len(obs)} act={len(act)} "
                f"(expected {OBS_DIM}/{ACT_DIM})")
        rows.append((obs, act))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--csv", type=Path, default=Path("/tmp/rl_obs_debug.csv"))
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args()
    if not args.csv.is_file():
        raise SystemExit(f"{args.csv} missing; start rl_sim with RL_DEBUG_OBS=1 first")
    rows = parse(args.csv)
    if not rows:
        raise SystemExit(f"{args.csv}: no data rows")
    import numpy as np
    obs = np.asarray([r[0] for r in rows])
    act = np.asarray([r[1] for r in rows])
    out = {
        "csv": str(args.csv),
        "frames": int(len(rows)),
        "obs_dim": OBS_DIM,
        "act_dim": ACT_DIM,
        "obs_abs_max": {k: round(float(np.abs(obs[:, a:b]).max()), 4)
                        for k, (a, b) in TERM_SLICES.items()},
        "act_abs_max": round(float(np.abs(act).max()), 4),
        "first_frame": {
            "obs": {k: [round(float(v), 4) for v in obs[0, a:b]]
                    for k, (a, b) in TERM_SLICES.items()},
            "act": [round(float(v), 4) for v in act[0]],
        },
        "frame_delta_obs_max": round(
            float(np.abs(np.diff(obs, axis=0)).max()), 4) if len(rows) > 1 else 0.0,
        "note": "frame 0 = freshest obs; compare against Python judge replay "
                "with the same scene/checkpoint (docs/20-part2-shared/deployment-contract.md)",
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if args.json:
        args.json.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
