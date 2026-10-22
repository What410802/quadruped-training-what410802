#!/usr/bin/env python3
"""comp_import_part2_diag.py — 把 `run_part2_judged_eval.py` 的 V2 诊断 JSON 导入为 comp/eval 产物。

一次性诊断导入器（不是正式评测）：每难度一次尝试、无种子/扰动，manifest 标
`protocol.diagnostic=true`，`comp_score.py` 会把该行标为 diagnostic，不能当正式分数或对外引用。

用法（从任务目录根执行，即 @20261019_locomotion）：

    pixi run python scripts/agent_scripts/comp_import_part2_diag.py \
        --result-json ../../prep.d/results/part2_v2_diag.json \
        --policy assets/policies/flat-ft-2500/policy.pt \
        --policy-id flat-ft-2500-part2-diag-v2
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import subprocess
from pathlib import Path

from comp_part2_judge import score_for_level

DEFAULT_CONTRACT = Path("comp/CONTRACT.json")
DEFAULT_LEVELS = Path("config/part2-levels.json")
DEFAULT_PART1_SCENE = Path("assets/terrain/part1/part1_eval_scene_v2.xml")
JUDGE_FILES = [Path("scripts/agent_scripts/comp_part1_judge.py"),
               Path("scripts/agent_scripts/comp_part2_judge.py")]
NOTE = ("导入自 run_part2_judged_eval.py 诊断 JSON（comp_part2_judge.Part2JudgeV2）；"
        "无种子/扰动、每难度一次尝试，非正式协议")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def head_commit(repo: Path) -> str:
    try:
        return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=30, check=True).stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return "unknown"


def main() -> int:
    ap = argparse.ArgumentParser(description="Part2 V2 诊断 JSON → comp/eval 产物（diagnostic）")
    ap.add_argument("--result-json", type=Path, required=True)
    ap.add_argument("--policy", type=Path, required=True)
    ap.add_argument("--policy-id", required=True)
    ap.add_argument("--out-dir", type=Path, default=Path("comp/eval"))
    ap.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    ap.add_argument("--levels", type=Path, default=DEFAULT_LEVELS)
    ap.add_argument("--task-root", type=Path, default=Path("."))
    ap.add_argument("--part1-scene", type=Path, default=DEFAULT_PART1_SCENE)
    args = ap.parse_args()

    result = json.loads(args.result_json.read_text(encoding="utf-8"))
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    levels_meta = json.loads(args.levels.read_text(encoding="utf-8"))
    start_map = {(e["category"], float(e["level"])): e["judge"].get("start")
                 for e in levels_meta["levels"]}
    scene_map = {(e["category"], float(e["level"])): e["scene"] for e in levels_meta["levels"]}
    p1_obstacles = [o["id"] for o in contract["parts"]["part1"]["obstacles"]]
    p2_specs = contract["parts"]["part2"]["obstacles"]

    trials: list[dict] = []
    by_category: dict[str, list[dict]] = {}
    for att in result.get("attempts") or []:
        cat = att["category"]
        level = float(att["level"])
        unit = att.get("unit", "")
        for i, run in enumerate(att.get("attempts") or [], 1):
            judge = run.get("judge") or {}
            status = judge.get("status", "fail")
            trial = {
                "trial_id": f"diag-{args.policy_id}-{cat}-{att['level']}{unit}-a{i}",
                "part": "part2",
                "obstacle": cat,
                "difficulty": att["level"],
                "value": att["level"],
                "unit": unit,
                "attempt": i,
                "seed": None,
                "start": {"pose": start_map.get((cat, level)), "note": "diagnostic level start"},
                "commands": [{"cmd": [0.5, 0.0, 0.0], "seconds": run.get("duration_s")}],
                "judge": {"status": status,
                          "failure_reason": judge.get("reason") or None,
                          "events": [],
                          "score": score_for_level(contract["parts"]["part2"], cat, att["level"])
                          if status == "success" else 0},
                "success": status == "success",
                "duration_s": run.get("duration_s"),
                "tilt_deg": run.get("tilt_deg"),
                "base": run.get("base"),
                "video": None,
            }
            trials.append(trial)
            by_category.setdefault(cat, []).append(trial)

    part2_obstacles: dict[str, dict] = {}
    total2 = 0
    for spec in p2_specs:
        oid = spec["id"]
        cat_trials = by_category.get(oid, [])
        success_levels = [float(t["difficulty"]) for t in cat_trials if t.get("success")]
        best = max(success_levels) if success_levels else None
        best_score = score_for_level(contract["parts"]["part2"], oid, best) if best is not None else 0
        total2 += best_score
        part2_obstacles[oid] = {"best_success_value": best, "best_score": best_score,
                                "attempts_used": len(cat_trials)}
    part1_obstacles = {oid: {"success": False, "score": 0, "failure_reason": "not_run",
                             "evidence": []} for oid in p1_obstacles}
    summary = {
        "schema_version": 1,
        "policy_id": args.policy_id,
        "part1": {"attempts_used": 0, "obstacles": part1_obstacles,
                  "return_to_start": False, "return_score": 0, "total": 0},
        "part2": {"obstacles": part2_obstacles, "total": total2},
        "grand_total": total2,
        "notes": NOTE,
    }

    manifest = {
        "schema_version": 1,
        "policy_id": args.policy_id,
        "created_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "repos": {
            "task": {"path": str(args.task_root), "commit": head_commit(args.task_root),
                     "dirty": True, "note": "dirty=true：HEAD 为导入时值，不是运行时的真实状态"},
            "training": {"path": "prep.d/training_repo_local（非 git 副本）", "commit": f"unknown:{args.policy_id}",
                         "dirty": True, "note": "训练仓 commit 未在运行时采集"},
            "control": {"path": "prep.d/quadruped_control_local", "commit": "unknown:not-used", "dirty": True,
                        "note": "诊断评测未经过控制仓"},
        },
        "policy": {
            "checkpoint": args.policy.name, "checkpoint_sha256": sha256_file(args.policy),
            "exported": args.policy.name, "exported_sha256": sha256_file(args.policy),
            "obs_dim": 45, "action_dim": 12, "policy_dt_ms": 20.0,
            "checkpoint_note": "原始 checkpoint 未单独保留；sha256 为导出 policy.pt",
        },
        "scenes": {
            "part1": {"file": str(args.part1_scene),
                      "sha256": sha256_file(args.part1_scene) if args.part1_scene.is_file() else ""},
            "part2": {"file": str(args.levels),
                      "sha256": sha256_file(args.levels) if args.levels.is_file() else "",
                      "levels": [
                          {"category": e["category"], "level": e["level"], "unit": e["unit"],
                           "scene": e["scene"],
                           "sha256": sha256_file(Path(e["scene"])) if Path(e["scene"]).is_file() else ""}
                          for e in levels_meta["levels"]
                      ]},
        },
        "judge": {"version": "comp_judge_v2@" + "".join(sha256_file(p)[:6] for p in JUDGE_FILES if p.is_file()),
                  "files": [str(p) for p in JUDGE_FILES]},
        "protocol": {
            "protocol_version": "diagnostic-2026-10-22-v2",
            "diagnostic": True,
            "seeds": [],
            "attempts_part1_total": 3,
            "attempts_part2_per_obstacle": 4,
            "operator": "scripted:run_part2_judged_eval.py",
            "seed_control": "none（runner 未设种子/扰动；名义 seed 不应被当作已执行）",
            "start_pose_policy": "parametric level starts (not yet protocol-frozen)",
        },
        "results": {"trials": "trials.jsonl", "summary": "summary.json"},
        "notes": NOTE,
    }

    out = args.out_dir / args.policy_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                       encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                                      encoding="utf-8")
    with (out / "trials.jsonl").open("w", encoding="utf-8") as fh:
        for t in trials:
            fh.write(json.dumps(t, ensure_ascii=False) + "\n")
    print(f"part2 diagnostic eval imported: {out} (grand_total={total2}, attempts={len(trials)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
