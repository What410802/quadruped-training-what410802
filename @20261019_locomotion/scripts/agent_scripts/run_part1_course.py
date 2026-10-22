"""Run the formal Part 1 whole-course protocol on the V2 judge (diagnostic harness).

This is the *integration harness* for `comp_part1_course.py`:
- spawns the policy in the start area of `part1_eval_scene_v2.xml`;
- follows a scripted waypoint route (`config/part1-route.json`) using only navigation
  truth to generate velocity commands (allowed by the rules);
- streams every physics step into the V2 judge + course protocol (attempts, pause,
  recovery, skip, return bonus, best score / fastest active time);
- optionally consumes operator events (pause/resume/skip_obstacle/abort) from a JSON
  file, so the same protocol can be driven by a human at the real run.

The scripted route is a P0 diagnostic, NOT the approved competition course: the real
run is manual. It exists to prove that the protocol and judge integrate end-to-end.

Usage (from MyMonoRepo.d):
  pixi run python @20261019_locomotion/scripts/agent_scripts/run_part1_course.py \
      --policy @20261019_locomotion/assets/policies/flat-ft-2500/policy.pt \
      --attempts 1 --json ../prep.d/results/part1_course_diag.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import mujoco
import numpy as np
import torch

from comp_part1_course import Part1Course
from run_part1_judged_rollout_v2 import GEOM_TAGS
from run_policy_scene import ACTION_SCALE, EFFORT_LIMIT, KD, KP, ScenePolicyRunner

ROOT = Path("@20261019_locomotion")
SCENE = ROOT / "assets/terrain/part1/part1_eval_scene_v2.xml"
ROUTE = ROOT / "config/part1-route.json"
POLICY = ROOT / "assets/policies/flat-ft-2500/policy.pt"
BAR_BODY = "height_bar_beam_body"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _yaw_of(xquat) -> float:
    w, x, y, z = (float(v) for v in xquat)
    return float(np.arctan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z)))


def _wrap(a: float) -> float:
    return float((a + np.pi) % (2 * np.pi) - np.pi)


class CoursePolicyRunner:
    def __init__(self, scene: Path, policy: Path, start: tuple[float, float, float, float]) -> None:
        self.runner = ScenePolicyRunner(str(scene), str(policy), start)
        self.model = self.runner.model
        self.data = self.runner.data
        self.bar_body = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, BAR_BODY)
        if self.bar_body < 0:
            raise RuntimeError("missing height bar body: use part1_eval_scene_v2.xml")
        self.floor_geoms = {g for g in range(self.model.ngeom)
                            if self.model.geom_type[g] == mujoco.mjtGeom.mjGEOM_PLANE}
        self.geom_names = {g: (mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_GEOM, g) or "")
                           for g in range(self.model.ngeom)}
        self.leg_geoms: dict[str, set[int]] = {}
        for leg in ("FL", "FR", "RL", "RR"):
            body = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, f"{leg}_foot")
            start_i = int(self.model.body_geomadr[body])
            self.leg_geoms[leg] = set(range(start_i, start_i + int(self.model.body_geomnum[body])))
        self.trunk = self.runner.trunk

    def base(self) -> tuple[np.ndarray, float]:
        return self.runner.base()

    def sample(self) -> dict:
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
        return {"t": float(self.data.time),
                "base_xyz": (float(base[0]), float(base[1]), float(base[2])),
                "yaw": _yaw_of(self.data.xquat[self.trunk]),
                "foot_tags": foot_tags, "ground_feet": ground_feet,
                "bar_z": float(self.data.xpos[self.bar_body][2])}

    def step_policy(self, command: np.ndarray) -> None:
        obs = self.runner.obs(command)
        with torch.no_grad():
            action = self.runner.policy(torch.from_numpy(obs).unsqueeze(0)).numpy().reshape(-1)
        action = np.clip(action.astype(np.float64), -1.0, 1.0)
        self.runner.last_action[:] = action
        q_target = self.runner.q_default + ACTION_SCALE * action
        q = np.array(self.data.qpos[self.runner.qpos_adr])
        qd = np.array(self.data.qvel[self.runner.qvel_adr])
        tau = np.clip(KP * (q_target - q) - KD * qd, -EFFORT_LIMIT, EFFORT_LIMIT)
        self.data.ctrl[self.runner.motor_ids] = tau
        for _ in range(4):
            mujoco.mj_step(self.model, self.data)


def waypoint_command(cpr: CoursePolicyRunner, target: tuple[float, float], speed: float) -> tuple[np.ndarray, bool]:
    base, _tilt = cpr.base()
    dx, dy = target[0] - float(base[0]), target[1] - float(base[1])
    dist = float(np.hypot(dx, dy))
    if dist < 0.30:
        return np.zeros(3), True
    yaw = _yaw_of(cpr.data.xquat[cpr.trunk])
    err = _wrap(float(np.arctan2(dy, dx)) - yaw)
    if abs(err) > 1.2:
        return np.array([0.0, 0.0, float(np.clip(1.5 * err, -0.8, 0.8))]), False
    vx = speed * max(0.0, float(np.cos(err)))
    return np.array([vx, 0.0, float(np.clip(1.2 * err, -0.6, 0.6))]), False


def apply_events(course: Part1Course, events: list[dict], idx: int, t: float) -> int:
    while idx < len(events) and float(events[idx]["t"]) <= t:
        ev = events[idx]
        kind = ev["event"]
        if kind == "pause":
            course.pause(t)
        elif kind == "resume":
            course.resume(t)
        elif kind == "skip_obstacle":
            course.skip_obstacle(t, ev["obstacle"])
        elif kind == "abort":
            course.abort_attempt(t, "operator_abort")
            return idx + 1
        idx += 1
    return idx


def run_attempt(cpr: CoursePolicyRunner, route: dict, events: list[dict], attempt: int,
                warmup_s: float = 0.5) -> dict:
    course = Part1Course()
    for _ in range(int(warmup_s / 0.02)):
        cpr.step_policy(np.zeros(3))
    ok = course.begin_attempt(float(cpr.data.time))
    if not ok:
        raise RuntimeError("course rejected attempt (budget exhausted)")
    ev_idx = 0
    aborted = False
    for seg in route["segments"]:
        target = tuple(seg["target"])
        speed = float(seg.get("speed", 0.5))
        t_end = float(cpr.data.time) + float(seg.get("max_s", 4.0))
        while cpr.data.time < t_end:
            cmd, reached = waypoint_command(cpr, target, speed)
            cpr.step_policy(cmd)
            s = cpr.sample()
            course.update(s["t"], s["base_xyz"], s["yaw"], foot_tags=s["foot_tags"],
                          ground_feet=s["ground_feet"], bar_z=s["bar_z"])
            ev_idx = apply_events(course, events, ev_idx, s["t"])
            if not course.active:
                aborted = True
                break
            if reached:
                break
        if aborted:
            break
    if course.active:
        course.end_attempt(float(cpr.data.time), "route_complete")
    return {"attempt": attempt, "aborted": aborted, "report": course.export_report(),
            "judge": course.judge.report() if not course.active else None}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", type=Path, default=POLICY)
    ap.add_argument("--scene", type=Path, default=SCENE)
    ap.add_argument("--route", type=Path, default=ROUTE)
    ap.add_argument("--attempts", type=int, default=1)
    ap.add_argument("--events", type=Path, default=None, help="操作手事件 JSON（可选）")
    ap.add_argument("--json", type=Path, default=Path("../prep.d/results/part1_course_diag.json"))
    args = ap.parse_args()

    route = json.loads(args.route.read_text(encoding="utf-8"))
    events = json.loads(args.events.read_text(encoding="utf-8")) if args.events else []
    events = sorted(events, key=lambda e: float(e["t"]))
    start = tuple(route["start"])
    attempts = []
    session_courses = []
    for attempt in range(1, args.attempts + 1):
        cpr = CoursePolicyRunner(args.scene, args.policy, start)
        result = run_attempt(cpr, route, events, attempt)
        attempts.append(result)
        session_courses.append(result["judge"])
        st = result["judge"]["states"] if result["judge"] else {}
        n_success = sum(1 for x in st.values() if x["status"] == "success")
        print(f"attempt {attempt}: score={result['report']['summary']['final_score']} "
              f"obstacles_success={n_success} aborted={result['aborted']}")
        if result["aborted"]:
            break
    total_success = sum(1 for x in (attempts[-1]["judge"]["states"] if attempts[-1]["judge"] else {}).values()
                        if x["status"] == "success")
    payload = {
        "kind": "part1_course_diagnostic",
        "protocol": "comp_part1_course.Part1Course",
        "judge": "comp_part1_judge.Part1JudgeV2",
        "scene": str(args.scene), "scene_sha256": sha256_file(args.scene),
        "route": str(args.route), "route_sha256": sha256_file(args.route),
        "policy": str(args.policy), "policy_sha256": sha256_file(args.policy),
        "attempts": attempts,
        "last_attempt_success_count": total_success,
        "notes": "scripted route is a P0 diagnostic harness; real run is manual, not approved protocol",
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("wrote", args.json)


if __name__ == "__main__":
    main()
