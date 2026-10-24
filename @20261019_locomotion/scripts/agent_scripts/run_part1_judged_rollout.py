"""Run zero-shot flat policy on Part 1 obstacles through the local judge.

This is a P0 baseline harness, not an official score: starts/commands are
scripted, and each obstacle is attempted independently.  The judge is external
to the policy (no ground-truth in the control loop).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import mujoco
import numpy as np

from part1_event_judge import Part1EventJudge
from part1_judge import Part1Judge
from run_policy_scene import ScenePolicyRunner

SCENE = "@20261019_locomotion/assets/terrain/part1/part1_eval_scene.xml"
POLICY = "@20261019_locomotion/assets/policies/flat-ft-2500/policy.pt"

# name: (start xyz, yaw, command, seconds, note)
TASKS = {
    "height_bar": ((5.7, -10.4, 0.55), np.pi / 2, (0.4, 0.0, 0.0), 4.0, "through gate opening along +y"),
    "high_wall": ((1.8, -7.8, 0.55), np.pi / 2, (0.4, 0.0, 0.0), 4.0, "cross wall along +y"),
    "bridge_blocks": ((1.8, 0.0, 0.65), 0.0, (0.3, 0.0, 0.0), 5.0, "left platform -> +x"),
    "bridge_bands": ((5.7, -3.5, 0.65), np.pi / 2, (0.3, 0.0, 0.0), 5.0, "lower platform -> +y"),
    "gravel_pit": ((3.5, -12.0, 0.55), 0.0, (0.45, 0.0, 0.0), 6.0, "approach pit from half-width outside along +x"),
    "t_stairs": ((1.8, -5.2, 0.55), np.pi / 2, (0.4, 0.0, 0.0), 5.0, "main limb -> +y"),
    "slope": ((3.6, -5.5, 0.55), 0.0, (0.5, 0.0, 0.0), 5.0, "slope -> +x"),
    "slalom": ((1.8, -9.25, 0.55), -np.pi / 2, (0.45, 0.0, 0.0), 4.5, "first post -> -y"),
}


def _bind_judge(judge: Part1Judge, runner: ScenePolicyRunner) -> None:
    judge.model = runner.model
    judge.data = runner.data


def _step_levels(runner: ScenePolicyRunner, judge: Part1Judge) -> set[int]:
    levels: set[int] = set()
    foot_geoms = {g for gids in judge.foot_geoms.values() for g in gids}
    for ci in range(runner.data.ncon):
        c = runner.data.contact[ci]
        g1, g2 = int(c.geom1), int(c.geom2)
        foot = g1 if g1 in foot_geoms else g2 if g2 in foot_geoms else None
        if foot is None:
            continue
        other = g2 if foot == g1 else g1
        p = runner.model.geom_pos[other]
        if 1.2 <= p[0] <= 3.5 and -5.0 <= p[1] <= -2.0:
            levels.add(round(float(p[2]) * 100))
    return levels


def _render_final(runner: ScenePolicyRunner, name: str, status: str, out_dir: Path) -> None:
    import mujoco
    out_dir.mkdir(parents=True, exist_ok=True)
    renderer = mujoco.Renderer(runner.model, height=360, width=480)
    opt = mujoco.MjvOption(); opt.geomgroup[:] = 1
    base, _ = runner.base()
    cam = mujoco.MjvCamera(); cam.distance = 2.8; cam.elevation = -22; cam.azimuth = 135
    cam.lookat[:] = (base[0], base[1], max(0.18, base[2] - 0.15))
    renderer.update_scene(runner.data, camera=cam, scene_option=opt)
    img = renderer.render().copy()
    renderer.close()
    path = out_dir / f"{name}__{status}.ppm"
    with open(path, "wb") as f:
        f.write(f"P6\n{img.shape[1]} {img.shape[0]}\n255\n".encode())
        f.write(img.tobytes())


def run_task(name: str, policy_path: str, scene_path: str, render_dir: Path | None = None,
             depth_config: dict | None = None) -> dict:
    (xyz, yaw, command, seconds, note) = TASKS[name]
    runner = ScenePolicyRunner(scene_path, policy_path, (xyz[0], xyz[1], xyz[2], yaw),
                               depth_config=depth_config)
    judge = Part1Judge(scene_path)
    _bind_judge(judge, runner)
    events = Part1EventJudge()

    for _ in range(25):
        runner.step(np.zeros(3))
    states = None
    for _ in range(int(seconds / 0.02)):
        runner.step(np.asarray(command, dtype=np.float64))
        judge_data = judge.read_contacts()
        ground_feet = [leg for leg, hit in judge_data.foot_ground.items() if hit]
        states = events.update(
            tuple(float(v) for v in runner.data.xpos[runner.trunk]),
            ground_feet,
            judge_data.bar_contact,
            step_levels=_step_levels(runner, judge),
        )
    base, tilt = runner.base()
    if render_dir is not None:
        status = states["states"][name]["status"]
        _render_final(runner, name, status, render_dir)
    return {
        "task": name,
        "note": note,
        "start": [round(float(v), 2) for v in xyz] + [round(float(yaw), 2)],
        "command": [float(v) for v in command],
        "seconds": seconds,
        "base": [round(float(v), 3) for v in base],
        "tilt_deg": round(float(tilt), 2),
        "judge": states,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", choices=sorted(TASKS), action="append")
    parser.add_argument("--scene", default=SCENE)
    parser.add_argument("--policy", default=POLICY)
    parser.add_argument("--json", default="prep.d/results/part1_zero_shot.json")
    parser.add_argument("--render-dir", default="")
    parser.add_argument("--depth", action="store_true",
                        help="policy is a depth CNN actor: input (45, [1,1,H,W])")
    parser.add_argument("--depth-width", type=int, default=64)
    parser.add_argument("--depth-height", type=int, default=48)
    args = parser.parse_args()
    names = args.task or sorted(TASKS)
    depth_config = ({"width": args.depth_width, "height": args.depth_height}
                    if args.depth else None)
    results = []
    for name in names:
        render_dir = Path(args.render_dir) if args.render_dir else None
        result = run_task(name, args.policy, args.scene, render_dir, depth_config=depth_config)
        results.append(result)
        st = result["judge"]["states"][name]
        print(f"{name:14s} status={st['status']:8s} score={st['score']:3d} "
              f"base={result['base']} tilt={result['tilt_deg']} reason={st['reason']}")
    out = Path(args.json)
    out.parent.mkdir(parents=True, exist_ok=True)
    total = sum(r["judge"]["score"] for r in results)
    success = sum(1 for r in results if r["judge"]["states"][r["task"]]["status"] == "success")
    out.write_text(json.dumps({
        "scene": args.scene,
        "policy": args.policy,
        "depth": bool(args.depth),
        "total_score": total,
        "success_count": success,
        "attempts": results,
    }, indent=2))
    print(f"total_score={total} success={success}/{len(results)}")
    print("wrote", out)


if __name__ == "__main__":
    main()
