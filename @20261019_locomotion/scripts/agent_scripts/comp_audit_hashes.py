#!/usr/bin/env python3
"""comp_audit_hashes.py — 重算 G1 审计对象的 sha256 并写 `comp/audits/HASHES.json`。

用途：每次 judge/协议/场景语义变化后，在送审（或重审）前刷新哈希，使审计对象固定；
hash 变化即旧门禁失效（见 acceptance-gate）。

用法（从任务目录根执行）：
    pixi run python scripts/agent_scripts/comp_audit_hashes.py [--verdict pending]
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

OBJECTS = {
    "contract_json": "comp/CONTRACT.json",
    "contract_md": "comp/CONTRACT.md",
    "protocol_md": "comp/eval/_protocol.md",
    "judge_part1_v2": "scripts/agent_scripts/comp_part1_judge.py",
    "judge_conformance": "scripts/agent_scripts/comp_judge_conformance.py",
    "judge_course": "scripts/agent_scripts/comp_part1_course.py",
    "judge_part2_v2": "scripts/agent_scripts/comp_part2_judge.py",
    "part2_levels_maker": "scripts/agent_scripts/make_part2_levels.py",
    "scene_part1_v2": "assets/terrain/part1/part1_eval_scene_v2.xml",
    "part1_route": "config/part1-route.json",
    "part2_levels_json": "config/part2-levels.json",
    "eval_part1_diag": "comp/eval/flat-ft-2500-part1-diag-v2/summary.json",
    "eval_part2_diag": "comp/eval/flat-ft-2500-part2-diag-v2/summary.json",
    "eval_course_diag": "comp/eval/flat-ft-2500-part1-course-diag/summary.json",
    "rules_pdf_md": "docs/reference/team-race-2026.md",
}

SUPERSEDED = {
    "judge_event_v1": "scripts/agent_scripts/part1_event_judge.py",
    "judge_contact_v1": "scripts/agent_scripts/part1_judge.py",
    "scene_part1_v1": "assets/terrain/part1/part1_eval_scene.xml",
    "judge_zones_v1": "assets/terrain/part1/judge_zones.yaml",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verdict", default="pending", help="pending / PASS / CONCERN / FAIL")
    ap.add_argument("--report", default="comp/audits/JUDGE_AUDIT.md")
    ap.add_argument("--out", type=Path, default=Path("comp/audits/HASHES.json"))
    args = ap.parse_args()
    out = {"audited": args.verdict != "pending",
           "note": f"G1 重审对象（judge V2）；verdict={args.verdict}；hash 变化即门禁失效",
           "generated_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
           "objects": {}, "superseded": {}, "audit": {}}
    for key, rel in OBJECTS.items():
        p = ROOT / rel
        out["objects"][key] = {"path": rel, "sha256": sha256(p) if p.is_file() else ""}
    for key, rel in SUPERSEDED.items():
        p = ROOT / rel
        out["superseded"][key] = {"path": rel, "sha256": sha256(p) if p.is_file() else "",
                                  "note": "G1 首轮对象，已被 V2 取代"}
    out["audit"] = {"skill": "comp-eval-audit", "gate": "G1", "reviewer": "pending",
                    "date": "", "verdict": args.verdict, "report": args.report}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.out} ({len(out['objects'])} objects)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
