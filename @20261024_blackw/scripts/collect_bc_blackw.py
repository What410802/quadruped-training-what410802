#!/usr/bin/env python3
"""Collect behaviour-cloning data from the official blackW policies (local MuJoCo).

The organiser's official blackW TorchScript policies already clear several
official Part 2 tiers (platform 40 cm, wall 40 cm, slope 35 deg, trench 20 cm at
slow command).  This script rolls them out on the official-geometry scenes from
``gen_part2_official_levels.py`` and records

    (single-frame proprioceptive observation, raw 16-D action)

for every control step.  Observations follow the deployment contract used both by
rl_sar and by the MjLab blackW task (see ``eval_blackw_part2.PolicyRunner``), so
the records can initialise the MjLab PPO actor with behaviour cloning.

Output: ``prep.d/bc_data/blackw_bc_<tag>.npz`` with obs float32 [N,57], act
float32 [N,16], episode index [N], episode success flag [N], weight [N].

Usage (from MyMonoRepo.d):
  pixi run python @20261024_blackw/scripts/collect_bc_blackw.py --tag v1
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys_path = str(HERE)
import sys

sys.path.insert(0, sys_path)
from eval_blackw_part2 import (  # noqa: E402
    LEVELS, POLICY_ROOT, Part2OfficialJudge, PolicyRunner, SCENE_DIR,
    load_policy_config,
)

TASK = HERE.parent
OUT_DIR = TASK.parent / "prep.d" / "bc_data"


def collect_episode(runner: PolicyRunner, level: dict, teacher: str,
                    command: np.ndarray, seconds: float, slow_x: float | None,
                    slow_vx: float) -> dict:
    policy_dt = runner.policy_dt
    spawn = np.asarray(level["spawn"], dtype=np.float64)
    runner.reset_pose(spawn=spawn[:3], yaw=float(spawn[3]))
    judge = Part2OfficialJudge(level)
    # No warm-up: the MjLab training env also lets the policy act from the reset
    # state, so the behaviour-cloned student must see that same initial condition.
    n = int(round(seconds / policy_dt))
    obs_list, act_list = [], []
    sim_t = 0.0
    for _ in range(n):
        cmd = command.copy()
        x = float(runner.data.qpos[0])
        if slow_x is not None and x >= slow_x:
            cmd[0] = slow_vx
        obs = runner._obs(cmd)
        runner.infer(cmd)
        runner.step()
        sim_t += policy_dt
        pos, tilt = runner.base()
        judge.update(sim_t, pos, tilt)
        obs_list.append(obs)
        act_list.append(runner.action.copy())
        if judge.status != "running":
            break
    report = judge.finalize("timeout")
    return {"obs": np.asarray(obs_list, dtype=np.float32),
            "act": np.asarray(act_list, dtype=np.float32),
            "success": report["status"] == "success",
            "category": level["category"], "level": level["level"],
            "teacher": teacher, "command": [float(v) for v in command],
            "slow_x": slow_x}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="v1")
    ap.add_argument("--teachers", default="obstacle,stair")
    ap.add_argument("--seconds", type=float, default=14.0)
    ap.add_argument("--physics-dt", type=float, default=0.002)
    ap.add_argument("--policy-dt", type=float, default=0.02)
    ap.add_argument("--only", action="append", default=[])
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    levels = json.loads((SCENE_DIR / "part2_official_levels.json").read_text())["levels"]
    if args.only:
        levels = [lv for lv in levels if lv["key"] in args.only]
    teachers = [t.strip() for t in args.teachers.split(",") if t.strip()]
    cfgs = {t: load_policy_config(POLICY_ROOT / t) for t in teachers}

    commands = [(0.25, 0.0, 0.0), (0.35, 0.0, 0.0), (0.5, 0.0, 0.0),
                (0.7, 0.0, 0.0), (0.9, 0.0, 0.0),
                (0.5, 0.10, 0.0), (0.5, -0.10, 0.0),
                (0.5, 0.0, 0.20), (0.5, 0.0, -0.20)]
    schedules = [(None, 0.3), (1.2, 0.25)]  # (slow_from_x, slow_vx)

    episodes = []
    runner_cache: dict[tuple[str, str], PolicyRunner] = {}
    for teacher in teachers:
        # The flat policy only contributes basic locomotion: run it on the flat
        # approach stretch (no obstacle) so the student keeps velocity tracking.
        flat_teacher = teacher == "flat"
        for level in levels:
            scene = SCENE_DIR / level["scene"]
            cmds = commands if not flat_teacher else commands + [
                (0.3, 0.0, 0.3), (0.3, 0.0, -0.3), (0.6, 0.2, 0.0), (0.6, -0.2, 0.0)]
            schs = schedules if not flat_teacher else [(None, 0.3)]
            secs = 2.5 if flat_teacher else args.seconds
            key = (teacher, str(scene))
            if key not in runner_cache:
                runner_cache[key] = PolicyRunner(
                    scene, POLICY_ROOT / teacher / "policy.pt", cfgs[teacher],
                    physics_dt=args.physics_dt, policy_dt=args.policy_dt)
            for cmd in cmds:
                for slow_x, slow_vx in schs:
                    episodes.append(collect_episode(
                        runner_cache[key], level, teacher, np.asarray(cmd),
                        secs, slow_x, slow_vx))
    all_obs, all_act, ep_idx, ep_success, ep_weight = [], [], [], [], []
    for i, ep in enumerate(episodes):
        if ep["obs"].size == 0:
            continue
        all_obs.append(ep["obs"])
        all_act.append(ep["act"])
        ep_idx.append(np.full(len(ep["obs"]), i, dtype=np.int32))
        w = 1.0 if ep["success"] else 0.15
        ep_weight.append(np.full(len(ep["obs"]), w, dtype=np.float32))
        ep_success.append(ep["success"])
    obs = np.concatenate(all_obs)
    act = np.concatenate(all_act)
    idx = np.concatenate(ep_idx)
    weight = np.concatenate(ep_weight)
    meta = [{k: v for k, v in ep.items() if k not in ("obs", "act")} for ep in episodes]
    out = OUT_DIR / f"blackw_bc_{args.tag}.npz"
    np.savez_compressed(out, obs=obs, act=act, episode=idx, weight=weight,
                        meta=json.dumps(meta))
    n_ok = sum(1 for ep in episodes if ep["success"])
    print(f"saved {out}: samples={len(obs)} episodes={len(episodes)} "
          f"successful_episodes={n_ok}")
    by_cat: dict[str, int] = {}
    for ep in episodes:
        key = f"{ep['teacher']}/{ep['category']}/{ep['level']}"
        by_cat[key] = by_cat.get(key, 0) + (1 if ep["success"] else 0)
    print(json.dumps(by_cat, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
