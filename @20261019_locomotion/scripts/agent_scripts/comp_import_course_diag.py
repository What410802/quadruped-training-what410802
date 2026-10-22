#!/usr/bin/env python3
"""comp_import_course_diag.py — 把 `run_part1_course.py` 的整场诊断 JSON 导入为 comp/eval 产物。

这是**协议链路诊断**（脚本化 waypoint 路线，非操作手正式赛程）：manifest 标
`protocol.diagnostic=true`、`protocol.mode=course_diagnostic`，`comp_score.py` 标 diagnostic。
正式比赛整场由操作手手动跑；此导入器用于验证"整场协议 + judge + 证据链"能闭环。

summary 口径：per-obstacle 取**最好一次尝试**的结果；attempts_used = 实际尝试次数；
返回奖励只在该尝试"全部障碍满分 + 二次进入出发区"时计入（与 comp_score 校验一致）。

用法（从任务目录根执行）：
    pixi run python scripts/agent_scripts/comp_import_course_diag.py \
        --result-json ../../prep.d/results/part1_course_diag.json \
        --policy assets/policies/flat-ft-2500/policy.pt \
        --policy-id flat-ft-2500-part1-course-diag
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import subprocess
from pathlib import Path

DEFAULT_CONTRACT = Path("comp/CONTRACT.json")
DEFAULT_ROUTE = Path("config/part1-route.json")
DEFAULT_PART1_SCENE = Path("assets/terrain/part1/part1_eval_scene_v2.xml")
JUDGE_FILES = [Path("scripts/agent_scripts/comp_part1_judge.py"),
               Path("scripts/agent_scripts/comp_part1_geom_tags.py"),
               Path("scripts/agent_scripts/comp_part1_course.py")]
NOTE = ("导入自 run_part1_course.py 整场诊断（脚本化 waypoint、单次尝试、无种子/扰动）；"
        "不是操作手正式赛程，不能当正式分数")


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


def failure_reason(status: str, reason: str) -> str | None:
    if status == "success":
        return None
    if reason:
        return reason
    return {"running": "timeout", "pending": "not_attempted"}.get(status, "other:diagnostic")


def main() -> int:
    ap = argparse.ArgumentParser(description="整场 course 诊断 JSON → comp/eval 产物（diagnostic）")
    ap.add_argument("--result-json", type=Path, required=True)
    ap.add_argument("--policy", type=Path, required=True)
    ap.add_argument("--policy-id", required=True)
    ap.add_argument("--out-dir", type=Path, default=Path("comp/eval"))
    ap.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    ap.add_argument("--route", type=Path, default=DEFAULT_ROUTE)
    ap.add_argument("--part1-scene", type=Path, default=DEFAULT_PART1_SCENE)
    ap.add_argument("--task-root", type=Path, default=Path("."))
    args = ap.parse_args()

    result = json.loads(args.result_json.read_text(encoding="utf-8"))
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    p1_specs = {o["id"]: o for o in contract["parts"]["part1"]["obstacles"]}
    attempts = result.get("attempts") or []

    # Each attempt JSON carries its own AttemptResult (score/duration/return bonus); pick
    # the best attempt by score, then fastest duration (confirmed tie rule).
    def _att_rec(att: dict) -> dict:
        return dict(att.get("attempt_result") or {})

    best_idx = 0
    best_key = (-1.0, -0.0)
    for i, att in enumerate(attempts):
        rec = _att_rec(att)
        if rec.get("skipped"):
            continue
        key = (float(rec.get("score", 0.0)), -float(rec.get("duration_s", 0.0)))
        if key > best_key:
            best_key, best_idx = key, i
    if best_key[0] < 0.0 and attempts:      # all attempts skipped: still keep a record
        best_idx = 0
    best = attempts[best_idx] if attempts else {"report": {"summary": {}}, "judge": {"states": {}}}
    best_rec = _att_rec(best)
    best_attempt_no = int(best_rec.get("attempt") or best.get("attempt") or (best_idx + 1))
    best_states = (best.get("judge") or {}).get("states") or {}

    trials: list[dict] = []
    for i, att in enumerate(attempts, 1):
        states = (att.get("judge") or {}).get("states") or {}
        duration = float(_att_rec(att).get("duration_s", 0.0))
        for oid in p1_specs:
            st = states.get(oid) or {}
            status = st.get("status", "pending")
            trials.append({
                "trial_id": f"diag-{args.policy_id}-{oid}-a{i}",
                "part": "part1", "obstacle": oid, "attempt": i, "seed": None,
                "start": {"pose": None, "note": "whole-course attempt (scripted route)"},
                "commands": [{"cmd": "waypoint_route", "seconds": round(duration, 3)}],
                "judge": {"status": status,
                          "failure_reason": failure_reason(status, st.get("reason", "")),
                          "events": [], "score": int(st.get("score") or 0)},
                "duration_s": round(duration, 3), "video": None,
            })

    part1_obstacles: dict[str, dict] = {}
    sum1 = 0
    for oid in p1_specs:
        st = best_states.get(oid) or {}
        status = st.get("status", "pending")
        success = status == "success"
        score = int(st.get("score") or 0) if success else 0
        sum1 += score
        evidence = [t["trial_id"] for t in trials
                    if t["obstacle"] == oid and t["attempt"] == best_attempt_no
                    and t["judge"]["status"] == "success"]
        part1_obstacles[oid] = {"success": success, "score": score,
                                "failure_reason": None if success else failure_reason(status, st.get("reason", "")),
                                "evidence": evidence}
    all_full = bool(part1_obstacles) and all(r["success"] and r["score"] >= int(p1_specs[o].get("per_obstacle_score", 100))
                                              for o, r in part1_obstacles.items())
    return_bonus = float(best_rec.get("return_bonus", 0.0)) if all_full else 0.0
    return_trial_id = f"diag-{args.policy_id}-return_to_start-a{best_attempt_no}"
    if return_bonus > 0:
        trials.append({
            "trial_id": return_trial_id, "part": "part1", "obstacle": "return_to_start",
            "attempt": best_attempt_no, "seed": None,
            "start": {"pose": None, "note": "after all obstacles full, re-entered start area"},
            "commands": [{"cmd": "return_to_start", "seconds": 0.0}],
            "judge": {"status": "success", "failure_reason": None,
                      "events": ["return_to_start_after_full"], "score": 0},
            "duration_s": 0.0, "video": None,
        })
    session = result.get("session_summary") or {}
    summary = {
        "schema_version": 1,
        "policy_id": args.policy_id,
        "part1": {"attempts_used": len(attempts), "obstacles": part1_obstacles,
                  "return_to_start": bool(return_bonus > 0), "return_score": int(return_bonus),
                  "return_evidence": return_trial_id if return_bonus > 0 else None,
                  "final_score": session.get("final_score"),
                  "final_time_s": session.get("final_time_s"),
                  "total": int(sum1 + return_bonus)},
        "part2": {"obstacles": {oid: {"best_success_value": None, "best_score": 0, "attempts_used": 0}
                                for oid in [o["id"] for o in contract["parts"]["part2"]["obstacles"]]},
                  "total": 0},
        "grand_total": int(sum1 + return_bonus),
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
                        "note": "脚本化整场诊断未经过控制仓"},
        },
        "policy": {"checkpoint": args.policy.name, "checkpoint_sha256": sha256_file(args.policy),
                   "exported": args.policy.name, "exported_sha256": sha256_file(args.policy),
                   "obs_dim": 45, "action_dim": 12, "policy_dt_ms": 20.0,
                   "checkpoint_note": "原始 checkpoint 未单独保留；sha256 为导出 policy.pt"},
        "scenes": {"part1": {"file": str(args.part1_scene),
                             "sha256": sha256_file(args.part1_scene) if args.part1_scene.is_file() else ""},
                   "part2": {"file": "config/part2-levels.json",
                             "sha256": sha256_file(Path("config/part2-levels.json"))
                             if Path("config/part2-levels.json").is_file() else ""}},
        "judge": {"version": "comp_judge_v2@" + "".join(sha256_file(p)[:6] for p in JUDGE_FILES if p.is_file()),
                  "files": [str(p) for p in JUDGE_FILES],
                  "file_hashes": [{"path": str(p), "sha256": sha256_file(p)}
                                  for p in JUDGE_FILES if p.is_file()]},
        "contract": {"file": str(args.contract), "sha256": sha256_file(args.contract)},
        "protocol": {
            "protocol_version": "course-diagnostic-2026-10-22",
            "mode": "course_diagnostic",
            "diagnostic": True,
            "seeds": [],
            "attempts_part1_total": 3,
            "attempts_part2_per_obstacle": 4,
            "operator": "scripted:run_part1_course.py",
            "route": {"file": str(args.route),
                      "sha256": sha256_file(args.route) if args.route.is_file() else ""},
            "seed_control": "none（脚本化 waypoint 路线，无扰动；result 里的 seed 均未执行）",
            "start_pose_policy": "route start in start_area (3.7,-9.0)",
        },
        "results": {"trials": "trials.jsonl", "summary": "summary.json"},
        "notes": NOTE,
    }

    out = args.out_dir / args.policy_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (out / "trials.jsonl").open("w", encoding="utf-8") as fh:
        for t in trials:
            fh.write(json.dumps(t, ensure_ascii=False) + "\n")
    print(f"course diagnostic imported: {out} (grand_total={summary['grand_total']}, attempts={len(attempts)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
