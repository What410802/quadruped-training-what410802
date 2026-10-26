#!/usr/bin/env python3
"""Manual Part-2 gate runner: stage table -> per-level x per-command-tier matrix.

Implements the gate protocol of
``@20261019_locomotion/docs/training/part2-ppo-handoff-2026-10-26.md`` section 3.4
(and the living plan section 5): official isolated scenes + the authoritative
``Part2OfficialJudge``, spawn jitter (x/y/yaw), joint offset/velocity reset
randomization consistent with the training reset, and **three command tiers** per
level built from the per-category nominal command profile.

Two modes:

* ``--stage placement``: run every official level once (16 attempts for the easy
  S0-S2 levels, 8 for the rest), report the full matrix and derive the lowest
  failing stage (blind objective = all levels except slope_45deg, trench_30cm and
  plum_1; the physically marginal slope_45deg is reported separately).
* ``--stage S0`` .. ``--stage S6`` / ``S7p`` / ``St30``: run only that stage's new
  levels plus verify all earlier stages cumulatively.

Each level is delegated to ``eval_blackw_part2.py`` as a subprocess (parallel) so
the judge code stays single-sourced; this script only builds the protocol, runs the
levels, and decides pass/fail.

Usage (from the repo root, CPU is enough):

    pixi run python @20261024_blackw/scripts/gate_stage.py \
        --policy @20261024_blackw/ws/src/rl_sar_blackw/policy/blackW/comp_bc_v5 \
        --stage placement --out-dir prep.d/results/blackw_official/stage_gates

Exit code: 0 if every requested stage passes, 1 otherwise.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import subprocess
import sys
from pathlib import Path

TASK = Path(__file__).resolve().parents[1]
REPO = TASK.parent
PY = sys.executable
EVAL = TASK / "scripts" / "eval_blackw_part2.py"
LEVELS = TASK / "ws/src/rl_sar_blackw/scenes/blackW/part2_official_levels.json"

# Official level keys (20 total, see part2_official_levels.json).
PLATFORM = ["high_platform_10cm", "high_platform_20cm", "high_platform_30cm",
            "high_platform_40cm"]
STAIRS = ["stairs_10cm", "stairs_15cm", "stairs_20cm", "stairs_30cm"]
SLOPE = ["slope_20deg", "slope_30deg", "slope_35deg", "slope_45deg"]
WALL = ["high_wall_10cm", "high_wall_20cm", "high_wall_30cm", "high_wall_40cm"]
TRENCH = ["trench_10cm", "trench_20cm", "trench_30cm"]
PLUM = ["plum_1"]

# Stage table from handoff section 3.2 (only the levels NEW at that stage).
STAGE_LEVELS: dict[str, list[str]] = {
    "S0": ["high_platform_10cm", "high_wall_10cm", "slope_20deg",
           "stairs_10cm", "trench_10cm"],
    "S1": ["stairs_15cm"],
    "S2": ["high_platform_20cm", "high_wall_20cm"],
    "S3": ["slope_30deg"],
    "S4": ["stairs_20cm", "trench_20cm"],
    "S5": ["slope_35deg"],
    "S6": ["high_platform_30cm", "high_wall_30cm"],
    # Blind-reachable high tiers that are not part of the mixed-row course (S7 in
    # the handoff also contains blind-unreachable trench30 and marginal slope45).
    "S7p": ["high_platform_40cm", "high_wall_40cm"],
    "St30": ["stairs_30cm"],
}
STAGE_ORDER = ["S0", "S1", "S2", "S3", "S4", "S5", "S6", "S7p", "St30"]

# Per-category nominal command profile (same as the judge reference profile).
CATEGORY_PROFILE: dict[str, dict] = {
    "high_platform": {"command": (0.5, 0.0, 0.0)},
    "high_wall": {"command": (0.65, 0.0, 0.0), "slow_from_x": 1.6, "cmd_slow": 0.35},
    "slope": {"command": (0.3, 0.0, 0.0)},
    "stairs": {"command": (0.75, 0.0, 0.0), "slow_from_x": 1.1, "cmd_slow": 0.45},
    "trench": {"command": (0.3, 0.0, 0.0)},
    "plum": {"command": (0.5, 0.0, 0.0)},
}
TIER_SCALES = (0.6, 1.0, 1.3)
VX_BOUNDS = (0.2, 1.1)  # handoff section 3.4 command tier clamp

# Blind objective of the current phase: everything except these three levels.
PHYSICS_PENDING = ["slope_45deg"]
DEPTH_ONLY = ["trench_30cm", "plum_1"]
EXCLUDED = set(PHYSICS_PENDING) | set(DEPTH_ONLY)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def level_command_tiers(level: dict) -> list[tuple[float, float, float]]:
    """Three command tiers for one level from its category nominal profile."""
    profile = CATEGORY_PROFILE[level["category"]]
    base = profile["command"]
    tiers = []
    for scale in TIER_SCALES:
        vx = _clamp(base[0] * scale, *VX_BOUNDS)
        tiers.append((round(vx, 4), round(base[1] * scale, 4), round(base[2] * scale, 4)))
    return tiers


def attempts_for_level(stage: str, level_key: str, override: int) -> int:
    if override > 0:
        return override
    # Handoff: easy stages S0-S2 need 16/16, harder stages 8/8.
    easy = set(STAGE_LEVELS["S0"]) | set(STAGE_LEVELS["S1"]) | set(STAGE_LEVELS["S2"])
    return 16 if level_key in easy else 8


def run_level(level: dict, policy: Path, attempts: int, protocol: dict,
              out_dir: Path) -> dict:
    """Run one level with all its attempts through eval_blackw_part2.py."""
    profile = CATEGORY_PROFILE[level["category"]]
    scale_spec = ",".join(str(scale) for scale in protocol["tier_scales"])
    out_json = out_dir / f"level_{level['key']}.json"
    cmd = [
        str(PY), str(EVAL),
        "--policy", str(policy),
        "--only", level["key"],
        "--attempts", str(attempts),
        "--command", *[str(v) for v in profile["command"]],
        "--command-set", scale_spec,
        "--cmd-jitter-y", str(protocol["cmd_jitter_y"]),
        "--cmd-jitter-wz", str(protocol["cmd_jitter_wz"]),
        "--jitter-x", str(protocol["jitter_x"]),
        "--jitter-y", str(protocol["jitter_y"]),
        "--jitter-yaw", str(protocol["jitter_yaw"]),
        "--joint-offset", str(protocol["joint_offset"]),
        "--joint-vel", str(protocol["joint_vel"]),
        "--json", str(out_json),
    ]
    if "slow_from_x" in profile:
        cmd[cmd.index("--json"):cmd.index("--json")] = [
            "--slow-from-x", str(profile["slow_from_x"]),
            "--cmd-slow", str(profile["cmd_slow"])]
    completed = subprocess.run(cmd, capture_output=True, text=True)
    if completed.returncode != 0:
        return {"key": level["key"], "category": level["category"],
                "error": completed.stderr.strip()[-500:] or completed.stdout[-500:],
                "pass": False, "attempt_count": attempts}
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    record = payload["results"][0]
    tier_stats = {str(k): v for k, v in record.get("tiers", {}).items()}
    passed = (record["success_count"] == record["attempt_count"]
              and all(v["success"] == v["attempts"] for v in tier_stats.values()))
    return {"key": level["key"], "category": level["category"],
            "level": record["level"], "unit": record["unit"],
            "success_count": record["success_count"],
            "attempt_count": record["attempt_count"],
            "tiers": tier_stats, "pass": bool(passed),
            "level_json": str(out_json)}


def stage_verdict(stage: str, level_results: dict[str, dict]) -> dict:
    required: list[str] = []
    for name in STAGE_ORDER:
        required.extend(STAGE_LEVELS[name])
        if name == stage:
            break
    failing = [key for key in required
               if not level_results.get(key, {}).get("pass", False)]
    tested = [key for key in required if key in level_results]
    return {"stage": stage, "required_levels": required, "tested": tested,
            "failing": failing, "pass": bool(required) and not failing}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", type=Path, required=True,
                    help="policy dir containing policy.pt + config.yaml")
    ap.add_argument("--stage", default="placement",
                    choices=["placement", *STAGE_ORDER],
                    help="'placement' = all levels + lowest failing stage")
    ap.add_argument("--attempts", type=int, default=0,
                    help="override attempts per hard level (0 = protocol default 16/8)")
    ap.add_argument("--out-dir", type=Path,
                    default=REPO / "prep.d/results/blackw_official/stage_gates")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--jitter-x", type=float, default=0.10)
    ap.add_argument("--jitter-y", type=float, default=0.15)
    ap.add_argument("--jitter-yaw", type=float, default=0.05)
    ap.add_argument("--joint-offset", type=float, default=0.03)
    ap.add_argument("--joint-vel", type=float, default=1.0)
    ap.add_argument("--tier-scales", type=str, default="0.6,1.0,1.3",
                    help="comma-separated vx scales of the nominal per-category command")
    ap.add_argument("--cmd-jitter-y", type=float, default=0.2)
    ap.add_argument("--cmd-jitter-wz", type=float, default=0.3)
    args = ap.parse_args()

    if not (args.policy / "policy.pt").is_file():
        raise SystemExit(f"policy not found under {args.policy}")
    all_levels = json.loads(LEVELS.read_text(encoding="utf-8"))["levels"]
    by_key = {level["key"]: level for level in all_levels}
    protocol = {"jitter_x": args.jitter_x, "jitter_y": args.jitter_y,
                "jitter_yaw": args.jitter_yaw, "joint_offset": args.joint_offset,
                "joint_vel": args.joint_vel, "cmd_jitter_y": args.cmd_jitter_y,
                "cmd_jitter_wz": args.cmd_jitter_wz,
                "tier_scales": [float(x) for x in args.tier_scales.split(",")],
                "vx_bounds": list(VX_BOUNDS)}
    args.out_dir.mkdir(parents=True, exist_ok=True)

    if args.stage == "placement":
        selected_keys = [level["key"] for level in all_levels]
    else:
        required: list[str] = []
        for name in STAGE_ORDER:
            required.extend(STAGE_LEVELS[name])
            if name == args.stage:
                break
        selected_keys = required
    jobs = [(by_key[key], attempts_for_level(args.stage, key, args.attempts))
            for key in selected_keys]

    print(f"policy={args.policy} sha256={_sha256(args.policy / 'policy.pt')[:16]} "
          f"stage={args.stage} levels={len(jobs)} workers={args.workers}")
    print(f"protocol: spawn +-({args.jitter_x},{args.jitter_y}) m yaw +-{args.jitter_yaw} rad, "
          f"joint +-{args.joint_offset} rad / +-{args.joint_vel} rad/s, "
          f"tiers {protocol['tier_scales']} vx clamp {VX_BOUNDS}, "
          f"cmd jitter vy+-{args.cmd_jitter_y} wz+-{args.cmd_jitter_wz}")
    results: dict[str, dict] = {}
    with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_level, level, args.policy, attempts, protocol,
                               args.out_dir): level["key"]
                   for level, attempts in jobs}
        for future in cf.as_completed(futures):
            result = future.result()
            results[result["key"]] = result
            mark = "PASS" if result["pass"] else "FAIL"
            detail = (f'{result.get("success_count")}/{result.get("attempt_count")}'
                      if "success_count" in result else result.get("error", "error"))
            print(f"  {result['key']:24s} {mark}  {detail}")

    stages = {}
    if args.stage == "placement":
        for name in STAGE_ORDER:
            stages[name] = stage_verdict(name, results)
        blind_keys = [level["key"] for level in all_levels if level["key"] not in EXCLUDED]
        blind_failing = [key for key in blind_keys
                         if not results.get(key, {}).get("pass", False)]
        stage_failing = [name for name in STAGE_ORDER if not stages[name]["pass"]]
        summary = {"mode": "placement", "blind_objective_levels": blind_keys,
                   "blind_objective_failing": blind_failing,
                   "blind_objective_pass": not blind_failing,
                   "lowest_failing_stage": stage_failing[0] if stage_failing else None,
                   "physics_pending": PHYSICS_PENDING, "depth_only": DEPTH_ONLY}
        for key in PHYSICS_PENDING + DEPTH_ONLY:
            if key in results:
                summary.setdefault("excluded_results", {})[key] = {
                    "pass": results[key]["pass"],
                    "success": f'{results[key].get("success_count")}/'
                               f'{results[key].get("attempt_count")}'}
    else:
        stages[args.stage] = stage_verdict(args.stage, results)
        summary = {"mode": "stage", "stage": args.stage}

    verdict = {"policy": str(args.policy),
               "policy_sha256": _sha256(args.policy / "policy.pt"),
               "date": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
               "protocol": protocol, "level_results": results,
               "stages": stages, "summary": summary}
    out_json = args.out_dir / f"gate_{args.stage}_{verdict['policy_sha256'][:12]}.json"
    out_json.write_text(json.dumps(verdict, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")

    print("\nstages:")
    for name, stage in stages.items():
        state = "PASS" if stage["pass"] else "FAIL"
        print(f"  {name:4s} {state}  required={len(stage['required_levels'])} "
              f"failing={stage['failing']}")
    if args.stage == "placement":
        print(f"blind objective (excl. {sorted(EXCLUDED)}) pass="
              f"{summary['blind_objective_pass']} "
              f"failing={summary['blind_objective_failing']}")
        print(f"lowest failing stage: {summary['lowest_failing_stage']}")
        for key, res in summary.get("excluded_results", {}).items():
            print(f"  excluded {key:14s} pass={res['pass']} ({res['success']})")
    print(f"\nwrote {out_json}")
    if args.stage == "placement":
        return 0 if summary["blind_objective_pass"] else 1
    return 0 if stages[args.stage]["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
