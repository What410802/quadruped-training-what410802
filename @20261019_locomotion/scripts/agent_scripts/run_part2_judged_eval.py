"""Run a policy on the Part 2 capability levels through the V2 evaluator (diagnostic).

For each category x level in ``config/part2-levels.json``:
- spawn the policy at the level start pose, warm up to a stand, then command forward;
- sample the V2 evaluator every physics step (5 ms);
- record success/fail, base pose, tilt and judge reason.

Official scoring is "highest successful difficulty per category, 4 attempts"; the
diagnostic default is 1 attempt per level (use ``--attempts 4`` for protocol-like runs
and stability ratios). Output goes to prep.d and is converted to comp/eval artifacts
separately (do not hand-edit scores).

Usage (from MyMonoRepo.d):
  pixi run python @20261019_locomotion/scripts/agent_scripts/run_part2_judged_eval.py \
      --policy @20261019_locomotion/assets/policies/flat-ft-2500/policy.pt \
      --only high_platform --only trench_10cm --attempts 1 --json ../prep.d/results/part2_v2_smoke.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import mujoco
import numpy as np
import torch

from comp_part2_judge import Part2JudgeV2, score_for_level
from run_policy_scene import (
    ACTION_SCALE, EFFORT_LIMIT, KD, KP, ScenePolicyRunner,
)

ROOT = Path("@20261019_locomotion")
LEVELS_JSON = ROOT / "config" / "part2-levels.json"
CONTRACT = ROOT / "comp" / "CONTRACT.json"
POLICY = ROOT / "assets" / "policies" / "flat-ft-2500" / "policy.pt"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class LevelRunner:
    """Policy + judge loop for one attempt at one Part 2 level."""

    def __init__(self, scene: str, policy: str, start: tuple[float, float, float, float],
                 depth_config: dict | None = None) -> None:
        self.runner = ScenePolicyRunner(scene, policy, start, depth_config=depth_config)
        self.depth_config = depth_config
        self.model = self.runner.model
        self.data = self.runner.data
        self.policy = self.runner.policy
        self.judge: Part2JudgeV2 | None = None
        self.floor_geoms = {g for g in range(self.model.ngeom)
                            if self.model.geom_type[g] == mujoco.mjtGeom.mjGEOM_PLANE}
        self.geom_names = {g: (mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_GEOM, g) or "")
                           for g in range(self.model.ngeom)}
        self.leg_geoms: dict[str, set[int]] = {}
        for leg in ("FL", "FR", "RL", "RR"):
            body = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, f"{leg}_foot")
            start_i = int(self.model.body_geomadr[body])
            self.leg_geoms[leg] = set(range(start_i, start_i + int(self.model.body_geomnum[body])))

    def warmup(self, seconds: float = 0.5) -> None:
        for _ in range(int(seconds / 0.02)):
            self._policy_step(np.zeros(3), judge=None)

    def _sample(self, judge: Part2JudgeV2) -> None:
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
                name = self.geom_names.get(other, "")
                if other in self.floor_geoms or name in {"ground_left", "ground_right", "trench_bottom"}:
                    ground_feet.add(leg)
                elif name.startswith("platform"):
                    foot_tags[leg].add("platform")
                elif name.startswith("stair"):
                    foot_tags[leg].add("stairs")
                elif name.startswith("slope"):
                    foot_tags[leg].add("slope")
                elif name == "wall":
                    foot_tags[leg].add("wall")
                elif name.startswith("plum"):
                    foot_tags[leg].add("plum")
        base, tilt = self.runner.base()
        judge.update(float(self.data.time),
                     (float(base[0]), float(base[1]), float(base[2])), tilt,
                     foot_tags=foot_tags, ground_feet=ground_feet)

    def _policy_step(self, command: np.ndarray, judge: Part2JudgeV2 | None) -> None:
        obs = self.runner.obs(command)
        obs_t = torch.from_numpy(obs).unsqueeze(0)
        if self.depth_config is not None:
            depth = torch.from_numpy(self.runner.render_depth())
            with torch.no_grad():
                action = self.policy(obs_t, [depth]).numpy().reshape(-1).astype(np.float64)
        else:
            with torch.no_grad():
                action = self.policy(obs_t).numpy().reshape(-1).astype(np.float64)
        action = np.clip(action, -1.0, 1.0)
        self.runner.last_action[:] = action
        q_target = self.runner.q_default + ACTION_SCALE * action
        q = np.array(self.data.qpos[self.runner.qpos_adr])
        qd = np.array(self.data.qvel[self.runner.qvel_adr])
        tau = np.clip(KP * (q_target - q) - KD * qd, -EFFORT_LIMIT, EFFORT_LIMIT)
        self.data.ctrl[self.runner.motor_ids] = tau
        for _ in range(4):
            mujoco.mj_step(self.model, self.data)
            if judge is not None:
                self._sample(judge)

    def run_attempt(self, entry: dict, seconds: float | None = None) -> dict:
        j = entry["judge"]
        self.judge = Part2JudgeV2(entry)
        self.warmup(0.5)
        command = np.asarray(j.get("command", [0.5, 0.0, 0.0]), dtype=np.float64)
        duration = float(seconds if seconds is not None else j.get("seconds", 6.0))
        for _ in range(int(duration / 0.02)):
            self._policy_step(command, judge=self.judge)
        report = self.judge.finalize("timeout")
        base, tilt = self.runner.base()
        return {"judge": report,
                "base": [round(float(v), 3) for v in base],
                "tilt_deg": round(float(tilt), 2),
                "duration_s": duration}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", type=Path, default=POLICY)
    ap.add_argument("--depth", action="store_true",
                    help="policy is a depth CNN actor: input (45, [1,1,H,W])")
    ap.add_argument("--depth-width", type=int, default=64)
    ap.add_argument("--depth-height", type=int, default=48)
    ap.add_argument("--levels", type=Path, default=LEVELS_JSON)
    ap.add_argument("--contract", type=Path, default=CONTRACT)
    ap.add_argument("--only", action="append", default=[], help="category or category_level e.g. trench_10cm")
    ap.add_argument("--attempts", type=int, default=1)
    ap.add_argument("--official", action="store_true",
                    help="official Part2 mode: at most 4 attempts per category (levels high->low)")
    ap.add_argument("--seconds", type=float, default=None)
    ap.add_argument("--json", type=Path, default=Path("../prep.d/results/part2_v2_eval.json"))
    args = ap.parse_args()

    levels = json.loads(args.levels.read_text(encoding="utf-8"))["levels"]
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    p2 = contract["parts"]["part2"]
    selected = levels
    if args.only:
        wanted = set(args.only)
        selected = []
        for e in levels:
            key = e["category"] if e["unit"] == "bool" else f"{e['category']}_{e['level']}{e['unit']}"
            if e["category"] in wanted or key in wanted:
                selected.append(e)
    if args.official:
        by_cat: dict[str, list[dict]] = {}
        for e in levels:
            by_cat.setdefault(e["category"], []).append(e)
        allowed_cats = {e["category"] for e in selected} if args.only else set(by_cat)
        official = []
        for cat in sorted(allowed_cats):
            ordered = sorted(by_cat.get(cat, []), key=lambda x: -float(x["level"]))
            if not ordered:
                continue
            for e in ordered[:4]:
                official.append(e)
            # official rule: 4 attempts per category; repeat the highest level if the
            # category defines fewer than 4 levels (trench=3, plum=1)
            for _ in range(4 - min(4, len(ordered))):
                official.append(ordered[0])
        selected = official
    results = []
    official_counter: dict[str, int] = {}
    for entry in selected:
        scene = str(ROOT / entry["scene"])
        start = tuple(entry["judge"]["start"])
        attempts = []
        n_attempts = 1 if args.official else max(1, args.attempts)
        for _ in range(n_attempts):
            depth_config = ({"width": args.depth_width, "height": args.depth_height}
                            if args.depth else None)
            lr = LevelRunner(scene, str(args.policy), start, depth_config=depth_config)
            attempts.append(lr.run_attempt(entry, args.seconds))
        successes = sum(1 for a in attempts if a["judge"]["status"] == "success")
        cat = entry["category"]
        if args.official:
            official_counter[cat] = official_counter.get(cat, 0) + 1
            attempt_index = official_counter[cat]
        else:
            attempt_index = None
        record = {"category": cat, "level": entry["level"], "unit": entry["unit"],
                  "scene": entry["scene"], "attempt_index": attempt_index,
                  "attempts": attempts,
                  "success_count": successes, "attempt_count": len(attempts),
                  "best_success": successes > 0}
        results.append(record)
        mark = "SUCCESS" if record["best_success"] else "fail"
        print(f"{entry['category']:14s} {entry['level']:>4}{entry['unit']:3s} {mark} "
              f"({successes}/{len(attempts)}) base={attempts[-1]['base']} tilt={attempts[-1]['tilt_deg']}")

    categories: dict[str, dict] = {}
    for rec in results:
        cat = rec["category"]
        c = categories.setdefault(cat, {"levels": [], "best_level": None, "best_success": False, "score": 0})
        c["levels"].append({"level": rec["level"], "unit": rec["unit"],
                            "success_count": rec["success_count"], "attempt_count": rec["attempt_count"],
                            "best_success": rec["best_success"]})
        if rec["best_success"] and (c["best_level"] is None or rec["level"] > c["best_level"]):
            c["best_level"] = rec["level"]
            c["best_success"] = True
    total = 0
    for cat, c in categories.items():
        c["score"] = score_for_level(p2, cat, c["best_level"]) if c["best_success"] else 0
        total += c["score"]
    payload = {
        "judge": "comp_part2_judge.Part2JudgeV2",
        "policy": str(args.policy),
        "policy_sha256": sha256_file(args.policy),
        "levels_file": str(args.levels),
        "contract_version": contract.get("contract_version"),
        "categories": categories,
        "total_score": total,
        "attempts": results,
        "notes": "diagnostic run; official score requires frozen protocol and G1-audited evaluator",
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"total_score={total} (categories={len(categories)})")
    print("wrote", args.json)


if __name__ == "__main__":
    main()
