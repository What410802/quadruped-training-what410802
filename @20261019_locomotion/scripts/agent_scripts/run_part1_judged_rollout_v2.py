"""Run one policy over Part 1 obstacles through the V2 judge (diagnostic path).

V2 differs from the P0 diagnostic runner:
- judge is `comp_part1_judge.Part1JudgeV2`: legal entry -> traversal evidence ->
  legal exit, per-step surface tags, any-instant 1/2-foot rule, bar-drop detection;
- every physics step is sampled (the V1 runner sampled once per 20 ms policy step and
  rebuilt step levels per frame, which lost contact history);
- scene is `part1_eval_scene_v2.xml` (movable beam on a slide joint, named platforms,
  steps and slope panels).

This runner is for diagnostics/validation only. Official scoring must use the frozen
protocol (`comp/eval/_protocol.md`) and the whole-course attempt protocol.

Usage (from MyMonoRepo.d):
  pixi run python @20261019_locomotion/scripts/agent_scripts/run_part1_judged_rollout_v2.py \
      --policy @20261019_locomotion/assets/policies/flat-ft-2500/policy.pt \
      --json ../prep.d/results/part1_v2_diag.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import mujoco
import numpy as np
import torch

from comp_part1_judge import Part1JudgeV2
from run_policy_scene import (
    ACTION_SCALE, EFFORT_LIMIT, KD, KP, POLICY_JOINT_ORDER, Q_DEFAULT, ScenePolicyRunner,
)

SCENE = "@20261019_locomotion/assets/terrain/part1/part1_eval_scene_v2.xml"
POLICY = "@20261019_locomotion/assets/policies/flat-ft-2500/policy.pt"
BAR_BODY = "height_bar_beam_body"

# name: (start xyz, yaw, command, seconds, note)  -- same diagnostic starts as V1
TASKS = {
    "height_bar": ((5.7, -10.4, 0.55), np.pi / 2, (0.4, 0.0, 0.0), 4.0, "through gate along +y"),
    "high_wall": ((1.8, -7.8, 0.55), np.pi / 2, (0.4, 0.0, 0.0), 4.0, "cross wall along +y"),
    "bridge_blocks": ((1.8, 0.0, 0.65), 0.0, (0.3, 0.0, 0.0), 5.0, "left platform -> +x"),
    "bridge_bands": ((5.7, -3.5, 0.65), np.pi / 2, (0.3, 0.0, 0.0), 5.0, "lower platform -> +y"),
    "gravel_pit": ((3.5, -12.0, 0.55), 0.0, (0.45, 0.0, 0.0), 6.0, "approach pit along +x"),
    "t_stairs": ((1.8, -5.2, 0.55), np.pi / 2, (0.4, 0.0, 0.0), 5.0, "main limb -> +y"),
    "slope": ((3.6, -5.5, 0.55), 0.0, (0.5, 0.0, 0.0), 5.0, "slope -> +x"),
    "slalom": ((1.8, -9.25, 0.55), -np.pi / 2, (0.45, 0.0, 0.0), 4.5, "first post -> -y"),
}

# Geo name -> surface tags used by the judge (see comp_part1_judge.py).
GEOM_TAGS: dict[str, set[str]] = {
    "bridge_blocks_platform_l": {"platform_left"},
    "bridge_platform_r": {"platform_right", "platform_high"},
    "bridge_bands_platform_low": {"platform_low"},
    "slope_a": {"slope"},
    "slope_b": {"slope"},
    "gravel_pit_a": {"gravel"},
    "gravel_pit_b": {"gravel"},
    "high_wall": {"wall"},
    "ramp_blocks_l": {"ramp"},
    "ramp_blocks_r": {"ramp"},
    # T stairs: same level tag on both y sides; x arm is the second branch.
    "t_stairs_y_low1": {"step:y:1"},
    "t_stairs_y_low2": {"step:y:2"},
    "t_stairs_y_low3": {"step:y:3"},
    "t_stairs_y_high1": {"step:y:1"},
    "t_stairs_y_high2": {"step:y:2"},
    "t_stairs_y_high3": {"step:y:3"},
    "t_stairs_x_low1": {"step:x:1"},
    "t_stairs_x_mid2": {"step:x:2"},
    "t_stairs_x_high3": {"step:x:3"},
    "t_stairs_top": {"step:top"},
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _yaw_of(data, body: int) -> float:
    q = np.asarray(data.xquat[body], dtype=float)  # wxyz
    w, x, y, z = q
    return float(np.arctan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z)))


class V2Runner:
    def __init__(self, scene: str, policy: str, start: tuple[float, float, float, float]) -> None:
        self.runner = ScenePolicyRunner(scene, policy, start)
        self.model = self.runner.model
        self.data = self.runner.data
        self.bar_body = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, BAR_BODY)
        if self.bar_body < 0:
            raise RuntimeError(f"missing body {BAR_BODY}: use part1_eval_scene_v2.xml")
        self.floor_geoms = {
            g for g in range(self.model.ngeom)
            if self.model.geom_type[g] == mujoco.mjtGeom.mjGEOM_PLANE
        }
        self.geom_names = {
            g: (mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_GEOM, g) or "")
            for g in range(self.model.ngeom)
        }
        self.leg_geoms: dict[str, set[int]] = {}
        for leg in ("FL", "FR", "RL", "RR"):
            body = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, f"{leg}_foot")
            if body < 0:
                raise RuntimeError(f"missing foot body {leg}_foot")
            start_i = int(self.model.body_geomadr[body])
            n = int(self.model.body_geomnum[body])
            self.leg_geoms[leg] = set(range(start_i, start_i + n))
        self.trunk = self.runner.trunk
        self.policy = self.runner.policy
        self.qpos_adr = self.runner.qpos_adr
        self.qvel_adr = self.runner.qvel_adr
        self.motor_ids = self.runner.motor_ids
        self.q_default = self.runner.q_default
        self.last_action = self.runner.last_action
        self.judge = Part1JudgeV2()

    def _policy_step(self, command: np.ndarray) -> None:
        obs = self.runner.obs(command)
        raw = torch.from_numpy(obs).unsqueeze(0)
        with torch.no_grad():
            action = self.policy(raw).numpy().reshape(-1).astype(np.float64)
        action = np.clip(action, -1.0, 1.0)
        self.last_action[:] = action
        q_target = self.q_default + ACTION_SCALE * action
        q = np.array(self.data.qpos[self.qpos_adr])
        qd = np.array(self.data.qvel[self.qvel_adr])
        tau = np.clip(KP * (q_target - q) - KD * qd, -EFFORT_LIMIT, EFFORT_LIMIT)
        self.data.ctrl[self.motor_ids] = tau
        for _ in range(4):
            mujoco.mj_step(self.model, self.data)
            self._sample_judge()

    def _sample_judge(self) -> None:
        foot_tags: dict[str, set[str]] = {leg: set() for leg in self.leg_geoms}
        ground_feet: set[str] = set()
        for ci in range(self.data.ncon):
            c = self.data.contact[ci]
            g1, g2 = int(c.geom1), int(c.geom2)
            for leg, geoms in self.leg_geoms.items():
                if g1 in geoms:
                    other = g2
                elif g2 in geoms:
                    other = g1
                else:
                    continue
                if other in self.floor_geoms:
                    ground_feet.add(leg)
                tags = GEOM_TAGS.get(self.geom_names.get(other, ""))
                if tags:
                    foot_tags[leg].update(tags)
        base = np.asarray(self.data.xpos[self.trunk], dtype=float)
        bar_z = float(self.data.xpos[self.bar_body][2])
        self.judge.update(float(self.data.time), (float(base[0]), float(base[1]), float(base[2])),
                          _yaw_of(self.data, self.trunk), foot_tags=foot_tags,
                          ground_feet=ground_feet, bar_z=bar_z)

    def run_task(self, name: str, warmup_s: float) -> dict:
        xyz, yaw, cmd, seconds, note = TASKS[name]
        command = np.asarray(cmd, dtype=np.float64)
        self.judge = Part1JudgeV2()
        for _ in range(int(warmup_s / 0.02)):
            self._policy_step(np.zeros(3))
        for _ in range(int(seconds / 0.02)):
            self._policy_step(command)
        report = self.judge.finalize("timeout")
        base, tilt = self.runner.base()
        return {
            "task": name,
            "note": note,
            "start": [round(float(v), 2) for v in xyz] + [round(float(yaw), 2)],
            "command": [float(v) for v in command],
            "seconds": seconds,
            "base": [round(float(v), 3) for v in base],
            "tilt_deg": round(float(tilt), 2),
            "judge": report,
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", choices=sorted(TASKS), action="append")
    parser.add_argument("--scene", default=SCENE)
    parser.add_argument("--policy", default=POLICY)
    parser.add_argument("--json", default="../prep.d/results/part1_v2_diag.json")
    parser.add_argument("--warmup", type=float, default=0.5)
    args = parser.parse_args()
    names = args.task or sorted(TASKS)
    results = []
    for name in names:
        xyz, yaw = TASKS[name][0], TASKS[name][1]
        vr = V2Runner(args.scene, args.policy, (xyz[0], xyz[1], xyz[2], yaw))
        result = vr.run_task(name, args.warmup)
        results.append(result)
        st = result["judge"]["states"][name]
        print(f"{name:14s} status={st['status']:8s} score={st['score']:5.1f} reason={st['reason']}")
    total = sum(r["judge"]["score"] for r in results)
    success = sum(1 for r in results if r["judge"]["states"][r["task"]]["status"] == "success")
    payload = {
        "judge": "comp_part1_judge.Part1JudgeV2",
        "scene": args.scene,
        "scene_sha256": sha256_file(Path(args.scene)),
        "policy": args.policy,
        "policy_sha256": sha256_file(Path(args.policy)),
        "total_score": total,
        "success_count": success,
        "attempts": results,
    }
    out = Path(args.json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(f"total_score={total} success={success}/{len(results)}")
    print("wrote", out)


if __name__ == "__main__":
    main()
