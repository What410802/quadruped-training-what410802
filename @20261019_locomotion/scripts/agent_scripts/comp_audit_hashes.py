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
    "judge_part1_v2_1": "scripts/agent_scripts/comp_part1_judge.py",
    "judge_conformance": "scripts/agent_scripts/comp_judge_conformance.py",
    "judge_course_protocol": "scripts/agent_scripts/comp_part1_course.py",
    "judge_part2_v2": "scripts/agent_scripts/comp_part2_judge.py",
    "geom_tags": "scripts/agent_scripts/comp_part1_geom_tags.py",
    "part2_levels_maker": "scripts/agent_scripts/make_part2_levels.py",
    "runner_part1_v2": "scripts/agent_scripts/run_part1_judged_rollout_v2.py",
    "runner_course": "scripts/agent_scripts/run_part1_course.py",
    "runner_part2_v2": "scripts/agent_scripts/run_part2_judged_eval.py",
    "importer_part1": "scripts/agent_scripts/comp_import_diagnostic.py",
    "importer_part2": "scripts/agent_scripts/comp_import_part2_diag.py",
    "importer_course": "scripts/agent_scripts/comp_import_course_diag.py",
    "score_tool": "scripts/agent_scripts/comp_score.py",
    "scene_part1_v2": "assets/terrain/part1/part1_eval_scene_v2.xml",
    "scene_check": "scripts/agent_scripts/check_part1_scene_v2.py",
    "part1_route": "config/part1-route.json",
    "part2_levels_json": "config/part2-levels.json",
    "eval_part1_diag": "comp/eval/flat-ft-2500-part1-diag-v2/summary.json",
    "eval_part2_diag": "comp/eval/flat-ft-2500-part2-diag-v2/summary.json",
    "eval_course_diag": "comp/eval/flat-ft-2500-part1-course-diag/summary.json",
    "rules_pdf_md": "docs/reference/team-race-2026.md",
    "byok_pre_audit": "comp/audits/BYOK_JUDGE_V2_REVIEW.md",
    "byok_fix_map": "comp/audits/BYOK_JUDGE_V2_FIXES.md",
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


LEVEL_DIR = ROOT / "assets/terrain/part2/levels"


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
    for lvl in sorted(LEVEL_DIR.glob("*.xml")):
        rel = lvl.relative_to(ROOT).as_posix()
        out["objects"][f"level_{lvl.stem}"] = {"path": rel, "sha256": sha256(lvl)}
    for pid in ("flat-ft-2500-part1-diag-v2", "flat-ft-2500-part2-diag-v2",
                "flat-ft-2500-part2-official-diag", "flat-ft-2500-part1-course-diag"):
        for fname in ("manifest.json", "trials.jsonl", "summary.json"):
            rel = f"comp/eval/{pid}/{fname}"
            p = ROOT / rel
            if p.is_file():
                out["objects"][f"eval_{pid}_{fname.split('.')[0]}"] = {"path": rel, "sha256": sha256(p)}
    for extra in ("assets/terrain/part2/ability_field/part2_ability_field.xml",
                  "assets/terrain/part2/part2_plum_eval_scene.xml",
                  "scripts/agent_scripts/comp_import_selftest.py",
                  "config/part1-course-events-pause.json",
                  "config/part1-course-events-abort.json",
                  "config/part1-course-events-pause-timeout.json",
                  "scripts/agent_scripts/build_calibration_bundle.py",
                  "scripts/agent_scripts/make_calibration_label_sheet.py",
                  "scripts/agent_scripts/check_calibration.py",
                  "comp/eval/_calibration/records.jsonl",
                  "comp/eval/_calibration/README_C1.md",
                  "comp/eval/_calibration/index.html",
                  "comp/eval/_calibration/labels_template.csv",
                  "comp/eval/_calibration/LABELS_PROVENANCE.md",
                  "comp/audits/G1_SELFCHECK.md",
                  "comp/audits/C1_CALIBRATION_REPORT.md"):
        if not (ROOT / extra).is_file():
            continue
        out["objects"]["extra_" + (ROOT / extra).stem] = {"path": extra, "sha256": sha256(ROOT / extra)}
    for extra in ():
        p = ROOT / extra
        if p.is_file():
            out["objects"]["scene_" + p.stem] = {"path": extra, "sha256": sha256(p)}
    evidence_dir = ROOT / "comp/audits/evidence"
    for ev in sorted(evidence_dir.glob("*.json")):
        rel = ev.relative_to(ROOT).as_posix()
        out["objects"][f"evidence_{ev.stem}"] = {"path": rel, "sha256": sha256(ev)}
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
