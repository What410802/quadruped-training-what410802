#!/usr/bin/env python3
"""comp_evidence_check.py — 分数/数字声明的确定性证据预检（不花 Codex 预算）。

在把任何数字写进 status/docs/答辩之前，机械校验它是否真的存在于源文件里：
路径存在吗？JSON path 能解出来吗？值对得上吗？这只能抓"幻觉证据"，
"值存在但不支持结论"仍由 Codex G4 审计判断（drive, not acquit）。

用法（从目标仓库根执行）：

    python3 comp/tools/comp_evidence_check.py --root . \
        --claims comp/CLAIMS.json --out comp/SCORE_EVIDENCE.json

claims.json 形如：

    [{"id": "p1-total", "value": 200, "source": "comp/eval/<pid>/summary.json", "path": "part1.total"}]

status ∈ verified | value_not_found | path_missing | unparseable。

    python3 comp/tools/comp_evidence_check.py --self-test
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

TOL_REL = 1e-9
TOL_ABS = 1e-6


def resolve_path(obj: Any, path: str) -> tuple[bool, Any]:
    """按 'a.b.0.c'（dict 键 / list 下标）解析；失败返回 (False, None)。"""
    cur = obj
    for token in path.split("."):
        if isinstance(cur, dict):
            if token not in cur:
                return False, None
            cur = cur[token]
        elif isinstance(cur, list):
            try:
                idx = int(token)
            except ValueError:
                return False, None
            if idx < 0 or idx >= len(cur):
                return False, None
            cur = cur[idx]
        else:
            return False, None
    return True, cur


def values_match(claim_value: Any, source_value: Any) -> bool:
    if isinstance(claim_value, bool) or isinstance(source_value, bool):
        return claim_value is source_value if isinstance(source_value, bool) else bool(claim_value) == bool(source_value)
    if isinstance(claim_value, (int, float)) and isinstance(source_value, (int, float)):
        return abs(float(claim_value) - float(source_value)) <= max(
            TOL_ABS, TOL_REL * max(abs(float(claim_value)), abs(float(source_value)))
        )
    if isinstance(claim_value, str) and isinstance(source_value, str):
        return claim_value.strip() == source_value.strip()
    # 数值字符串 vs 数值（如 "0.81" vs 0.81）
    try:
        return abs(float(claim_value) - float(source_value)) <= max(
            TOL_ABS, TOL_REL * max(abs(float(claim_value)), abs(float(source_value)))
        )
    except (TypeError, ValueError):
        return False


def check_claim(root: Path, claim: dict) -> dict:
    cid = claim.get("id", "?")
    source = claim.get("source")
    path = claim.get("path")
    out = {"id": cid, "status": "unparseable", "source": source, "path": path,
           "claimed": claim.get("value"), "actual": None, "detail": ""}
    if not source or not path:
        out["detail"] = "缺 source 或 path"
        return out
    src = (root / source).resolve() if not Path(source).is_absolute() else Path(source)
    try:
        rel = src.relative_to(root.resolve())
        out["source"] = str(rel)
    except ValueError:
        out["source"] = str(src)
    if not src.is_file():
        out["status"] = "path_missing"
        out["detail"] = f"源文件不存在: {out['source']}"
        return out
    try:
        if src.suffix.lower() == ".json":
            data = json.loads(src.read_text(encoding="utf-8"))
        else:
            data = src.read_text(encoding="utf-8")
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        out["detail"] = f"源文件不可解析: {exc}"
        return out
    if not isinstance(data, (dict, list)):
        out["detail"] = "非 JSON 容器，无法按 path 解析"
        return out
    found, actual = resolve_path(data, path)
    if not found:
        out["status"] = "value_not_found"
        out["detail"] = f"path 不存在: {path}"
        return out
    out["actual"] = actual
    if values_match(claim.get("value"), actual):
        out["status"] = "verified"
        out["detail"] = "值存在且一致（是否支持结论由 G4 Codex 审计）"
    else:
        out["status"] = "value_not_found"
        out["detail"] = f"claimed={claim.get('value')!r} != actual={actual!r}"
    return out


def run(root: Path, claims_path: Path, out_path: Path | None) -> int:
    claims = json.loads(claims_path.read_text(encoding="utf-8"))
    if not isinstance(claims, list):
        print("ERROR: claims 必须是 JSON 数组", file=sys.stderr)
        return 2
    results = [check_claim(root, c) for c in claims]
    summary: dict[str, int] = {}
    for r in results:
        summary[r["status"]] = summary.get(r["status"], 0) + 1
    payload = {"root": str(root), "claims_file": str(claims_path),
               "results": results, "summary": summary}
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text + "\n", encoding="utf-8")
        print(f"evidence report written: {out_path}")
    print(json.dumps(summary, ensure_ascii=False))
    for r in results:
        mark = "ok " if r["status"] == "verified" else "BAD"
        print(f"[{mark}] {r['id']}: {r['status']} — {r['detail']}")
    # 与 aHIL evidence_check 一致：发现幻觉证据不是工具失败，退出码保持 0，由调用方看 JSON。
    return 0


def run_self_test() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "comp" / "eval" / "p1").mkdir(parents=True)
        summary = {"policy_id": "p1", "part1": {"total": 200},
                   "part2": {"total": 60}, "grand_total": 260,
                   "nested": [{"score": 0.81}]}
        (root / "comp" / "eval" / "p1" / "summary.json").write_text(
            json.dumps(summary), encoding="utf-8")
        claims = [
            {"id": "good", "value": 260, "source": "comp/eval/p1/summary.json", "path": "grand_total"},
            {"id": "float", "value": 0.81, "source": "comp/eval/p1/summary.json", "path": "nested.0.score"},
            {"id": "wrong", "value": 999, "source": "comp/eval/p1/summary.json", "path": "grand_total"},
            {"id": "badpath", "value": 1, "source": "comp/eval/p1/summary.json", "path": "no.such"},
            {"id": "missing", "value": 1, "source": "comp/eval/p1/nope.json", "path": "x"},
        ]
        cp = root / "claims.json"
        cp.write_text(json.dumps(claims), encoding="utf-8")
        out = root / "out.json"
        assert run(root, cp, out) == 0
        payload = json.loads(out.read_text(encoding="utf-8"))
        got = {r["id"]: r["status"] for r in payload["results"]}
        assert got["good"] == "verified", got
        assert got["float"] == "verified", got
        assert got["wrong"] == "value_not_found", got
        assert got["badpath"] == "value_not_found", got
        assert got["missing"] == "path_missing", got
        assert payload["summary"]["verified"] == 2
    print("comp_evidence_check.py self-test: OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="分数/数字声明的确定性证据预检")
    ap.add_argument("--root", type=Path, default=Path("."))
    ap.add_argument("--claims", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return run_self_test()
    if not args.claims:
        ap.error("需要 --claims（或 --self-test）")
    return run(args.root, args.claims, args.out)


if __name__ == "__main__":
    sys.exit(main())
