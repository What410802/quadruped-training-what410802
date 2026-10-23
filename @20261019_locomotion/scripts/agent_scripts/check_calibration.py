"""Validate the completed C1 human labels and compute judge-human agreement.

Usage (from MyMonoRepo.d):
  pixi run python @20261019_locomotion/scripts/agent_scripts/check_calibration.py \
      --labels @20261019_locomotion/comp/eval/_calibration/labels_template.csv

Writes comp/audits/C1_CALIBRATION_REPORT.md (+ .json). Exit code 0 when all labels are
present and there are no disagreements; 1 otherwise (so it can gate C1).
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path("@20261019_locomotion")
DEFAULT_RECORDS = ROOT / "comp/eval/_calibration/records.jsonl"
DEFAULT_LABELS = ROOT / "comp/eval/_calibration/labels_template.csv"
OUT_MD = ROOT / "comp/audits/C1_CALIBRATION_REPORT.md"
OUT_JSON = ROOT / "comp/audits/C1_CALIBRATION_REPORT.json"

TRUE = {"1", "true", "yes", "y", "t", "success", "pass", "ok", "对", "是"}
FALSE = {"0", "false", "no", "n", "f", "fail", "不", "否"}


def _bool(value: str) -> bool | None:
    v = (value or "").strip().lower()
    if v in TRUE:
        return True
    if v in FALSE:
        return False
    return None


def _load_records(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _load_labels(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            tid = (row.get("trial_id") or "").strip()
            if tid:
                out[tid] = row
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", type=Path, default=DEFAULT_RECORDS)
    ap.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    ap.add_argument("--out-md", type=Path, default=OUT_MD)
    ap.add_argument("--out-json", type=Path, default=OUT_JSON)
    ap.add_argument("--print", action="store_true", help="additionally print the markdown")
    args = ap.parse_args()

    records = _load_records(args.records)
    labels = _load_labels(args.labels)
    errors: list[str] = []
    missing: list[str] = []
    mismatches: list[dict] = []
    stats: dict[str, dict[str, int]] = defaultdict(lambda: {"compared": 0, "agree": 0})
    labeled = 0

    for rec in records:
        tid = rec["trial_id"]
        row = labels.get(tid)
        if row is None:
            missing.append(tid)
            continue
        labeled += 1
        kind = rec["kind"]
        judge = rec.get("judge") or {}
        judge_success = judge.get("status") == "success"
        if kind in ("part1_obstacle", "part2_level", "part1_rulecard", "part2_rulecard"):
            human = _bool(row.get("human_success", ""))
            if human is None:
                missing.append(f"{tid}:human_success")
                continue
            key = rec.get("obstacle") or rec.get("category") or "unknown"
            key = f"{kind}:{key}"
            stats[key]["compared"] += 1
            if human == judge_success:
                stats[key]["agree"] += 1
            else:
                mismatches.append({
                    "trial_id": tid, "kind": kind,
                    "target": rec.get("obstacle") or rec.get("category"),
                    "level": rec.get("level"), "policy": rec.get("policy"),
                    "human_success": human, "judge_status": judge.get("status"),
                    "judge_score": judge.get("score"), "judge_reason": judge.get("reason"),
                    "human_failure_reason": row.get("human_failure_reason", ""),
                    "video": rec.get("video"),
                })
        elif kind == "session_state":
            human_ok = _bool(row.get("human_protocol_ok", ""))
            if human_ok is None:
                missing.append(f"{tid}:human_protocol_ok")
                continue
            stats["session_state"]["compared"] += 1
            if human_ok:
                stats["session_state"]["agree"] += 1
            else:
                mismatches.append({"trial_id": tid, "kind": kind,
                                   "title": rec.get("title"),
                                   "human_protocol_ok": False,
                                   "judge_reason": "protocol_ledger"})
        if (row.get("human_failure_reason") or "").strip() and _bool(row.get("human_success", "")):
            errors.append(f"{tid}: human_success=true 但填了 failure_reason")

    compared = sum(v["compared"] for v in stats.values())
    agree = sum(v["agree"] for v in stats.values())
    coverage = labeled / len(records) if records else 0.0
    lines = ["# C1 人工标定报告", "",
             f"- records: {len(records)}，已加载标签: {labeled}，覆盖率: {coverage:.1%}",
             f"- 参与一致性比较: {compared}，一致: {agree}，一致率: {(agree / compared if compared else 0):.1%}",
             f"- 缺失标签: {len(missing)}，标注错误: {len(errors)}，judge-human 不一致: {len(mismatches)}", ""]
    lines.append("## 分项一致率")
    lines.append("")
    lines.append("| 项 | compared | agree | 一致率 |")
    lines.append("|---|---|---|---|")
    for key in sorted(stats):
        v = stats[key]
        rate = v["agree"] / v["compared"] if v["compared"] else 0.0
        lines.append(f"| {key} | {v['compared']} | {v['agree']} | {rate:.1%} |")
    lines.append("")
    if mismatches:
        lines.append("## judge-human 不一致（需逐条规则依据或修 judge）")
        lines.append("")
        lines.append("| trial_id | target | human | judge | reason | video |")
        lines.append("|---|---|---|---|---|---|")
        for m in mismatches:
            lines.append(f"| {m['trial_id']} | {m.get('target') or m.get('title','')} | "
                         f"{m.get('human_success')} | {m.get('judge_status')} | {m.get('judge_reason') or ''} | "
                         f"{m.get('video') or ''} |")
        lines.append("")
    if missing:
        lines.append("## 缺失标签（trial_id 或字段）")
        lines.append("")
        lines.extend(f"- {m}" for m in missing)
    if errors:
        lines.append("## 标注格式错误")
        lines.extend(f"- {e}" for e in errors)

    report = {"records": len(records), "labeled": labeled, "coverage": coverage,
              "compared": compared, "agree": agree,
              "agreement": (agree / compared if compared else None),
              "by_kind": stats, "mismatches": mismatches,
              "missing": missing, "format_errors": errors}
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if args.print:
        print("\n".join(lines))
    else:
        print(json.dumps({k: report[k] for k in ("records", "labeled", "compared", "agree", "agreement")},
                         ensure_ascii=False))
        print(f"report -> {args.out_md}")
    ok = not missing and not errors and not mismatches
    print("C1 CALIBRATION: " + ("PASS" if ok else "NOT_READY"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
