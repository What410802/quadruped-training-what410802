"""Self-test for course importer edge cases (stdlib only).

Covers 2026-10-23 flash finding: an all-skipped session whose first skipped attempt had
already touched successful obstacles before abort must still import as an all-zero summary
(no success evidence, no positive score, final 0/0).
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IMPORTER = Path(__file__).with_name("comp_import_course_diag.py")
POLICY = ROOT / "assets/policies/flat-ft-2500/policy.pt"


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        result = {
            "policy_id": "selftest-allskip",
            "attempts": [
                {"attempt": 1, "attempt_result": {"attempt": 1, "score": 0.0, "obstacle_score": 0.0,
                                                 "return_bonus": 0.0, "duration_s": 5.0, "skipped": True,
                                                 "reason": "operator_abort", "events": []},
                 "judge": {"states": {"height_bar": {"status": "success", "score": 100},
                                      "high_wall": {"status": "fail", "score": 0}}}},
                {"attempt": 2, "attempt_result": {"attempt": 2, "score": 0.0, "obstacle_score": 0.0,
                                                 "return_bonus": 0.0, "duration_s": 3.0, "skipped": True,
                                                 "reason": "operator_abort", "events": []},
                 "judge": {"states": {"high_wall": {"status": "success", "score": 100}}}},
            ],
            "session_summary": {"attempts_used": 2, "final_score": 999.0, "final_time_s": 3.0},
        }
        (tmp / "result.json").write_text(json.dumps(result), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(IMPORTER), "--result-json", str(tmp / "result.json"),
             "--policy", str(POLICY), "--policy-id", "selftest-allskip"],
            cwd=str(ROOT), capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
        out = ROOT / "comp/eval/selftest-allskip"
        summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
        p1 = summary["part1"]
        assert p1["attempts_used"] == 2
        assert p1["final_score"] == 0 and p1["final_time_s"] == 0, p1
        assert p1["total"] == 0 and p1["return_score"] == 0, p1
        for oid, rec in p1["obstacles"].items():
            assert rec["success"] is False and rec["score"] == 0 and not rec["evidence"], (oid, rec)
        # every trial is skipped/zero
        trials = [json.loads(x) for x in (out / "trials.jsonl").read_text(encoding="utf-8").splitlines() if x]
        assert all(t["skipped"] and t["judge"]["status"] == "skipped" and t["judge"]["score"] == 0 for t in trials)
        for f in out.iterdir():
            f.unlink()
        out.rmdir()
    print("comp_import_selftest: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
