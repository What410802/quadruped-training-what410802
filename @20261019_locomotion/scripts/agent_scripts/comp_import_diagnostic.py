#!/usr/bin/env python3
"""comp_import_diagnostic.py — 把 `run_part1_judged_rollout.py` 的诊断 JSON 导入为 comp/eval 产物。

这是一次性诊断导入器（不是正式评测）：单种子、每障碍一次尝试、起点/命令取自诊断脚本。
因此 manifest 标 `protocol.diagnostic=true`，`comp_score.py` 会把该行标为 `diagnostic`，
不能当正式分数或对外引用。

用法（从任务目录根执行）：

    pixi run python @20261019_locomotion/scripts/agent_scripts/comp_import_diagnostic.py \
        --result-json ../prep.d/results/part1_zero_shot.json \
        --policy @20261019_locomotion/assets/policies/flat-ft-2500/policy.pt \
        --policy-id flat-ft-2500-part1-diag-v1

输出：<out-dir>/<policy_id>/{manifest.json,trials.jsonl,summary.json}
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import subprocess
from pathlib import Path

DEFAULT_CONTRACT = "comp/CONTRACT.json"
DEFAULT_SCENE = "assets/terrain/part1/part1_eval_scene.xml"
DEFAULT_JUDGE = "scripts/agent_scripts/part1_event_judge.py"
NOTE = "导入自 run_part1_judged_rollout.py 诊断 JSON；runner 未设种子/扰动，每障碍一次，非正式协议"


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
    return {"running": "timeout", "pending": "not_started"}.get(status, "other:diagnostic")


def main() -> int:
    ap = argparse.ArgumentParser(description="诊断 JSON → comp/eval 产物（diagnostic）")
    ap.add_argument("--result-json", type=Path, required=True)
    ap.add_argument("--policy", type=Path, required=True)
    ap.add_argument("--policy-id", required=True)
    ap.add_argument("--out-dir", type=Path, default=Path("comp/eval"))
    ap.add_argument("--contract", type=Path, default=Path(DEFAULT_CONTRACT))
    ap.add_argument("--scene", type=Path, default=Path(DEFAULT_SCENE))
    ap.add_argument("--judge", type=Path, default=Path(DEFAULT_JUDGE))
    ap.add_argument("--judge-extra", action="append", default=[], type=Path,
                    help="额外的 judge/映射文件（如 comp_part1_judge.py、comp_part1_geom_tags.py）")
    ap.add_argument("--task-root", type=Path, default=Path("."))
    ap.add_argument("--part2-scene", type=Path,
                    default=Path("assets/terrain/part2/ability_field/part2_ability_field.xml"))
    args = ap.parse_args()

    result = json.loads(args.result_json.read_text(encoding="utf-8"))
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    p1_obstacles = {o["id"]: o for o in contract["parts"]["part1"]["obstacles"]}
    p2_obstacles = {o["id"]: o for o in contract["parts"]["part2"]["obstacles"]}

    attempts = result.get("attempts") or []
    trials: list[dict] = []
    per_task: dict[str, dict] = {}
    for idx, att in enumerate(attempts, 1):
        task = att["task"]
        states = (att.get("judge") or {}).get("states") or {}
        st = states.get(task) or {}
        status = st.get("status", "pending")
        reason = st.get("reason", "") or ""
        trial = {
            "trial_id": f"diag-{args.policy_id}-{task}-a{idx}",
            "part": "part1",
            "obstacle": task,
            "attempt": idx,
            "seed": None,
            "start": {"pose": att.get("start"), "note": att.get("note")},
            "commands": [{"cmd": att.get("command"), "seconds": att.get("seconds")}],
            "judge": {"status": status, "failure_reason": failure_reason(status, reason),
                      "events": [], "score": int(st.get("score") or 0)},
            "duration_s": att.get("seconds"),
            "tilt_deg": att.get("tilt_deg"),
            "base": att.get("base"),
            "video": None,
        }
        trials.append(trial)
        per_task.setdefault(task, trial)

    part1_obstacles: dict[str, dict] = {}
    total = 0
    for oid in p1_obstacles:
        t = per_task.get(oid)
        success = bool(t and t["judge"]["status"] == "success")
        # partial-score obstacles (T stairs partial) carry their judge score; full success = max
        if success and t is not None:
            score = int(t["judge"].get("score") or p1_obstacles[oid].get("per_obstacle_score", 100))
        else:
            score = 0
        total += score
        part1_obstacles[oid] = {
            "success": success,
            "score": score,
            "failure_reason": None if success else (t["judge"]["failure_reason"] if t else "no_attempt"),
            "evidence": [t["trial_id"]] if t else [],
        }
    part2_obstacles = {oid: {"best_success_value": None, "best_score": 0, "attempts_used": 0}
                       for oid in p2_obstacles}
    summary = {
        "schema_version": 1,
        "policy_id": args.policy_id,
        "part1": {"attempts_used": len(attempts), "obstacles": part1_obstacles,
                  "return_to_start": False, "return_score": 0, "total": total},
        "part2": {"obstacles": part2_obstacles, "total": 0},
        "grand_total": total,
        "notes": NOTE,
    }

    p2_scene = args.part2_scene
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
            "part1": {"file": str(args.scene), "sha256": sha256_file(args.scene)},
            "part2": {"file": str(p2_scene), "sha256": sha256_file(p2_scene) if p2_scene.is_file() else ""},
        },
        "judge": {"version": "comp_part1_judge_v2_1@"
                  + "".join(sha256_file(p)[:6] for p in [args.judge] + list(args.judge_extra) if p.is_file()),
                  "files": [str(p) for p in [args.judge] + list(args.judge_extra)]},
        "protocol": {
            "protocol_version": "diagnostic-2026-10-22",
            "diagnostic": True,
            "seeds": [],
            "attempts_part1_total": 3,
            "attempts_part2_per_obstacle": 4,
            "operator": "scripted:run_part1_judged_rollout.py",
            "seed_control": "none（runner 未设种子/扰动；名义 seed 不应被当作已执行）",
            "start_pose_policy": "per-task diagnostic starts (not yet protocol-frozen)",
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
    print(f"diagnostic eval imported: {out} (grand_total={total}, attempts={len(attempts)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
