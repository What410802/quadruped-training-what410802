"""Create the blind C1 label sheet + HTML gallery from records.jsonl.

The label sheet must NOT show the judge verdict (labeling is blind). The judge verdict
stays in records.jsonl for the post-label agreement check.

Usage (from MyMonoRepo.d):
  pixi run python @20261019_locomotion/scripts/agent_scripts/make_calibration_label_sheet.py
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path

ROOT = Path("@20261019_locomotion")
DEFAULT_RECORDS = ROOT / "comp/eval/_calibration/records.jsonl"
DEFAULT_CSV = ROOT / "comp/eval/_calibration/labels_template.csv"
DEFAULT_INDEX = ROOT / "comp/eval/_calibration/index.html"
VIDEO_ROOT = Path("../prep.d")


def _rel_video(video: str, base: Path) -> str:
    p = Path(video)
    if p.is_absolute():
        try:
            p = p.relative_to(VIDEO_ROOT.resolve())
        except ValueError:
            pass
    return str((base / ".." / ".." / ".." / "prep.d" / p).resolve()) if not p.is_absolute() else str(p)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", type=Path, default=DEFAULT_RECORDS)
    ap.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    ap.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    args = ap.parse_args()

    records = [json.loads(line) for line in args.records.read_text(encoding="utf-8").splitlines() if line.strip()]
    header = ["trial_id", "kind", "obstacle_or_category", "level", "policy_or_title",
              "video_or_svg", "human_success", "human_failure_reason",
              "human_protocol_ok", "human_judge_verdict_correct", "notes"]
    with args.csv.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for r in records:
            w.writerow([
                r["trial_id"], r["kind"],
                r.get("obstacle") or r.get("category") or r.get("title", ""),
                r.get("level", ""),
                r.get("policy") or "",
                r.get("video") or "",
                "", "", "", "",
                r.get("note", "") or "",
            ])
    print(f"blind label sheet -> {args.csv} ({len(records)} rows)")

    # HTML gallery (blind: judge verdict not shown)
    rows_html = []
    index_dir = args.index.parent.resolve()
    for r in records:
        media = r.get("video") or ""
        media_href = ""
        if media:
            try:
                media_href = os.path.relpath(Path(media).resolve(), start=index_dir)
            except OSError:
                media_href = media
        media_cell = f'<a href="{media_href}">open</a>' if media_href else "—"
        kind = r["kind"]
        if kind == "session_state":
            media_cell = f'<a href="#{r["trial_id"]}">state table</a>'
        target = r.get("obstacle") or r.get("category") or r.get("title", "")
        rows_html.append(
            f"<tr><td>{r['trial_id']}</td><td>{kind}</td><td>{target}</td>"
            f"<td>{r.get('level','')}</td><td>{r.get('policy','')}</td><td>{media_cell}</td>"
            f"<td>{r.get('note','') or ''}</td></tr>")
    sessions_html = []
    for r in records:
        if r["kind"] != "session_state":
            continue
        table = json.dumps(r.get("state_table"), ensure_ascii=False, indent=2)
        sessions_html.append(f'<h3 id="{r["trial_id"]}">{r["trial_id"]} — {r.get("title","")}</h3>'
                             f'<p>{r.get("note","")}</p><pre style="background:#f6f6f6;padding:8px">{table}</pre>')
    html = f"""<!doctype html><meta charset="utf-8"><title>C1 calibration bundle</title>
<style>body{{font-family:sans-serif;margin:24px}}table{{border-collapse:collapse}}
td,th{{border:1px solid #ccc;padding:4px 8px;font-size:13px}}th{{background:#eee}}</style>
<h1>C1 评测器人工标定包（盲标）</h1>
<p>按 <code>{args.csv.name}</code> 逐条标注；视频/图在 <code>../prep.d/videos/calibration/</code>。
judge verdict 未显示（盲标）。标注完成后运行
<code>pixi run python @20261019_locomotion/scripts/agent_scripts/check_calibration.py</code>。</p>
<table><tr><th>trial_id</th><th>kind</th><th>目标</th><th>level</th><th>policy</th><th>media</th><th>notes</th></tr>
{''.join(rows_html)}
</table>
<h2>session-state 状态表</h2>
{''.join(sessions_html)}
"""
    args.index.write_text(html, encoding="utf-8")
    print(f"gallery -> {args.index}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
