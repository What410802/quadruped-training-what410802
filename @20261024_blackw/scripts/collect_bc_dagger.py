#!/usr/bin/env python3
"""DAgger data collection: teacher labels on the behaviour-cloned student's states.

Runs the exported student policy (TorchScript, deployment frame-major layout) in
the official-geometry scenes, queries the official teacher policy on the same
history observation at every control step, and records
``(single-frame observation, teacher action)``.  Merging this with the initial
teacher demonstrations closes the covariate-shift gap of plain behaviour cloning.

Usage (from MyMonoRepo.d):
  pixi run python @20261024_blackw/scripts/collect_bc_dagger.py \
      --student @20261024_blackw/ws/src/rl_sar_blackw/policy/blackW/comp_bc_v2 \
      --tag dagger1 --teachers obstacle,stair
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from eval_blackw_part2 import (  # noqa: E402
    POLICY_ROOT, PolicyRunner, load_policy_config, SCENE_DIR,
)

TASK = HERE.parent
OUT_DIR = TASK.parent / "prep.d" / "bc_data"


def student_teacher_episode(scene: Path, level: dict, student_cfg: dict,
                           student_pt: Path, teacher_pt: Path, teacher_cfg: dict,
                           command: np.ndarray, seconds: float,
                           slow_x: float | None, slow_vx: float,
                           physics_dt: float, policy_dt: float,
                           jitter_y: float = 0.0) -> dict:
    student = PolicyRunner(scene, student_pt, student_cfg, physics_dt=physics_dt,
                           policy_dt=policy_dt)
    teacher = torch.jit.load(str(teacher_pt)).eval()
    spawn = np.asarray(level["spawn"], dtype=np.float64).copy()
    if jitter_y:
        spawn[1] += float(np.random.default_rng(abs(hash((str(scene), level["key"], command[0], slow_x))) % 2**32).uniform(-jitter_y, jitter_y))
    student.reset_pose(spawn=spawn[:3], yaw=float(spawn[3]))
    hist: list[np.ndarray] = []
    obs_list, act_list = [], []
    n = int(round(seconds / policy_dt))
    for _ in range(n):
        cmd = command.copy()
        x = float(student.data.qpos[0])
        if slow_x is not None and x >= slow_x:
            cmd[0] = slow_vx
        frame = student._obs(cmd)
        if not hist:
            hist = [frame.copy() for _ in range(6)]
        else:
            hist = hist[1:] + [frame.copy()]
        inp = np.concatenate(hist[::-1]).astype(np.float32)[None]
        with torch.no_grad():
            t_act = teacher(torch.from_numpy(inp)).numpy().reshape(-1)
        student.infer(cmd)
        student.step()
        obs_list.append(frame)
        act_list.append(np.clip(t_act, -100.0, 100.0).astype(np.float32))
    return {"obs": np.asarray(obs_list, dtype=np.float32),
            "act": np.asarray(act_list, dtype=np.float32),
            "teacher": str(teacher_pt), "category": level["category"],
            "level": level["level"], "success": False,
            "command": [float(v) for v in command], "slow_x": slow_x,
            "student": str(student_pt)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--student", type=Path, required=True)
    ap.add_argument("--tag", default="dagger1")
    ap.add_argument("--teachers", default="obstacle,stair")
    ap.add_argument("--seconds", type=float, default=14.0)
    ap.add_argument("--physics-dt", type=float, default=0.002)
    ap.add_argument("--policy-dt", type=float, default=0.02)
    ap.add_argument("--commands", default="0.25,0.35,0.5,0.7,0.9")
    ap.add_argument("--only", action="append", default=[],
                    help="level key filter (default: all official levels)")
    ap.add_argument("--slow-from", type=float, default=1.2)
    ap.add_argument("--jitter-y", type=float, default=0.0,
                    help="random lateral spawn offset (robustness augmentation)")
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    levels = json.loads((SCENE_DIR / "part2_official_levels.json").read_text())["levels"]
    if args.only:
        wanted = set(args.only)
        levels = [lv for lv in levels if lv["key"] in wanted]
    student_pt = args.student / "policy.pt"
    student_cfg = load_policy_config(args.student)
    teachers = [t.strip() for t in args.teachers.split(",") if t.strip()]
    commands = [float(v) for v in args.commands.split(",")]
    episodes = []
    for teacher in teachers:
        teacher_pt = POLICY_ROOT / teacher / "policy.pt"
        teacher_cfg = load_policy_config(POLICY_ROOT / teacher)
        for level in levels:
            scene = SCENE_DIR / level["scene"]
            for vx in commands:
                for slow_x, slow_vx in ((None, vx), (args.slow_from, 0.3)):
                    episodes.append(student_teacher_episode(
                        scene, level, student_cfg, student_pt, teacher_pt,
                        teacher_cfg, np.array([vx, 0.0, 0.0]), args.seconds,
                        slow_x, slow_vx, args.physics_dt, args.policy_dt,
                        jitter_y=args.jitter_y))
    obs = np.concatenate([e["obs"] for e in episodes])
    act = np.concatenate([e["act"] for e in episodes])
    ep = np.concatenate([np.full(len(e["obs"]), i, dtype=np.int32)
                         for i, e in enumerate(episodes)])
    weight = np.ones(len(obs), dtype=np.float32)
    meta = [{k: v for k, v in e.items() if k not in ("obs", "act")} for e in episodes]
    out = OUT_DIR / f"blackw_bc_{args.tag}.npz"
    np.savez_compressed(out, obs=obs, act=act, episode=ep, weight=weight,
                        meta=json.dumps(meta))
    print(f"saved {out}: samples={len(obs)} episodes={len(episodes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
