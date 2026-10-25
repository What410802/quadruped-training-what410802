#!/usr/bin/env python3
"""Aggregate blackW official-Part2 eval JSONs (several commands/policies) into a score.

Input files are the JSONs written by ``eval_blackw_part2.py``; the official
scoring for Part 2 is "highest successful difficulty per category, up to four
attempts (no time limit)".  We treat each (policy, command) run as an attempt
that the operator may choose, so per level we take the best status over all
runs, then per category the highest successful level, and map it to the contract
score curve (floor rounding, same as the frozen evaluator).

Usage (from MyMonoRepo.d):
  pixi run python @20261024_blackw/scripts/summarize_blackw_eval.py \
      --eval prep.d/results/blackw_official/final/*.json --md prep.d/results/blackw_official/final/SUMMARY.md
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

TASK = Path(__file__).resolve().parents[1]
REPO = TASK.parent
sys.path.insert(0, str(REPO / "@20261019_locomotion/scripts/agent_scripts"))
from comp_part2_judge import score_for_level  # noqa: E402

CONTRACT = REPO / "@20261019_locomotion/comp/CONTRACT.json"
ORDER = ["high_platform", "stairs", "slope", "high_wall", "trench", "plum"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval", nargs="+", required=True)
    ap.add_argument("--md", type=Path, default=None)
    ap.add_argument("--json-out", type=Path, default=None)
    ap.add_argument("--contract", type=Path, default=CONTRACT)
    args = ap.parse_args()
    files: list[Path] = []
    for pattern in args.eval:
        files.extend(Path(p) for p in glob.glob(pattern))
    files = sorted(set(files))
    if not files:
        raise SystemExit("no eval files matched")
    contract = json.loads(args.contract.read_text())["parts"]["part2"]

    # best[(category, level)] = list of (policy, command, status)
    best: dict[tuple[str, float], dict] = {}
    level_units: dict[tuple[str, float], str] = {}
    per_run = []
    for f in files:
        payload = json.loads(f.read_text())
        run = {"file": str(f), "policy": payload["policy"],
               "command": payload.get("command"), "schedule": payload.get("command_schedule")}
        n_ok = 0
        for rec in payload["results"]:
            key = (rec["category"], float(rec["level"]))
            level_units[key] = rec["unit"]
            status = rec["attempts"][-1]["judge"]["status"]
            cur = best.setdefault(key, {"status": "fail", "runs": []})
            cur["runs"].append({"policy": payload["policy"],
                                "command": payload.get("command"),
                                "status": status})
            if status == "success":
                cur["status"] = "success"
                n_ok += 1
        run["success_levels"] = n_ok
        per_run.append(run)

    categories: dict[str, dict] = {}
    total = 0
    for (category, level), info in best.items():
        c = categories.setdefault(category, {"best_level": None, "score": 0,
                                            "levels": {}})
        c["levels"][level] = info["status"]
        if info["status"] == "success":
            if c["best_level"] is None or level > c["best_level"]:
                c["best_level"] = level
    for category, c in categories.items():
        c["score"] = int(score_for_level(contract, category, c["best_level"])) \
            if c["best_level"] is not None else 0
        total += c["score"]
    payload = {"files": [str(f) for f in files], "runs": per_run,
               "categories": categories, "total_score": total,
               "best_level": {k: v["best_level"] for k, v in categories.items()}}
    lines = ["# blackW official Part 2 evaluation summary", "",
             f"runs={len(files)}  total_score={total}/1300", "",
             "| category | " + " | ".join(
                 str(lv) for lv in sorted({k[1] for k in best if k[0] == "high_platform"}))
             + " | best | score |",
             "|---|" + "---|" * (len({k[1] for k in best if k[0] == "high_platform"}) + 2)]
    for category in ORDER:
        if category not in categories:
            continue
        c = categories[category]
        levels = sorted(c["levels"])
        cells = " | ".join(("PASS " if c["levels"][lv] == "success" else "fail ")
                           for lv in levels)
        lines.append(f"| {category} | {cells} | {c['best_level']} | {c['score']} |")
    lines += ["", "## runs", "",
              "| policy | vx | schedule | levels passed |", "|---|---|---|---|"]
    for run in per_run:
        cmd = run["command"]
        vx = cmd[0] if cmd else "?"
        lines.append(f"| `{Path(run['policy']).parent.name}` | {vx} | "
                     f"{run['schedule']} | {run['success_levels']} |")
    md = "\n".join(lines) + "\n"
    if args.md:
        args.md.parent.mkdir(parents=True, exist_ok=True)
        args.md.write_text(md, encoding="utf-8")
        print(f"wrote {args.md}")
    if args.json_out:
        args.json_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        print(f"wrote {args.json_out}")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
