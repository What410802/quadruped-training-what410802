#!/usr/bin/env python3
"""comp_freeze.py — 生成 C5 冻结清单：多仓 provenance + 产物 sha256 + 评测口径。

用法（从目标仓库根执行）：

    python3 comp/tools/comp_freeze.py \
        --contract comp/CONTRACT.json \
        --manifest comp/eval/<policy_id>/manifest.json \
        --repo task=@20261019_locomotion \
        --repo training=<训练仓库路径> \
        --repo control=<控制仓库路径> \
        --artifact exported=assets/policies/<ver>/policy.pt \
        --artifact scene=assets/terrain/part1/part1_eval_scene.xml \
        --out comp/freeze/FREEZE_MANIFEST.md \
        --json-out comp/freeze/FREEZE_MANIFEST.json

仓库 dirty（有未提交改动）时默认拒绝冻结（退出码 1）；确认要在 dirty 状态下冻结时加 --allow-dirty
（清单会显式记录 dirty=true，这是给现场兜底用的，不是常规路径）。

    python3 comp/tools/comp_freeze.py --self-test
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_info(path: Path) -> dict:
    info: dict = {"path": str(path), "git": False, "commit": None, "dirty": None}
    try:
        head = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=30, check=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "-C", str(path), "status", "--porcelain", "--untracked-files=no"],
            capture_output=True, text=True, timeout=30, check=True,
        ).stdout.strip()
        info.update({"git": True, "commit": head, "dirty": bool(status)})
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        pass
    lock = path / "uv.lock"
    if lock.is_file():
        info["uv_lock_sha256"] = sha256_file(lock)
    return info


def build(contract_path: Path, manifest_path: Path, repos: list[str],
          artifacts: list[str], allow_dirty: bool) -> tuple[dict, int]:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    repo_entries = []
    for spec in repos:
        if "=" not in spec:
            raise SystemExit(f"--repo 需要 name=path，收到: {spec}")
        name, path = spec.split("=", 1)
        entry = git_info(Path(path))
        entry["name"] = name
        repo_entries.append(entry)
    art_entries = []
    for spec in artifacts:
        if "=" not in spec:
            raise SystemExit(f"--artifact 需要 name=path，收到: {spec}")
        name, path = spec.split("=", 1)
        p = Path(path)
        art_entries.append({"name": name, "path": path,
                            "exists": p.is_file(),
                            "sha256": sha256_file(p) if p.is_file() else None})
    dirty = [r for r in repo_entries if r.get("dirty")]
    not_git = [r for r in repo_entries if not r.get("git")]
    blocked = bool(dirty or not_git) and not allow_dirty
    payload = {
        "freeze_version": "freeze-v1",
        "generated_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "contract_version": contract.get("contract_version"),
        "competition": contract.get("competition"),
        "policy_id": manifest.get("policy_id"),
        "protocol_version": (manifest.get("protocol") or {}).get("protocol_version"),
        "judge_version": (manifest.get("judge") or {}).get("version"),
        "repos": repo_entries,
        "artifacts": art_entries,
        "manifest": {
            "policy": manifest.get("policy"),
            "scenes": manifest.get("scenes"),
            "protocol": manifest.get("protocol"),
            "judge": manifest.get("judge"),
        },
        "allow_dirty": allow_dirty,
        "status": "BLOCKED" if blocked else ("DIRTY_ALLOWED" if dirty else "OK"),
        "blockers": [f"{r['name']}: dirty=true" for r in dirty]
                    + [f"{r['name']}: 不是 git 仓库（无法冻结 provenance）" for r in not_git],
    }
    return payload, (1 if blocked else 0)


def write_manifest(payload: dict, out_md: Path, out_json: Path) -> None:
    rows = "\n".join(
        f"| {r['name']} | `{r.get('path')}` | `{r.get('commit') or '-'}` | "
        f"{str(r.get('dirty')).lower()} | `{r.get('uv_lock_sha256') or '-'}` |"
        for r in payload["repos"]
    )
    arts = "\n".join(
        f"| {a['name']} | `{a['path']}` | `{a.get('sha256') or '-'}` | {a['exists']} |"
        for a in payload["artifacts"]
    )
    blockers = "\n".join(f"- {b}" for b in payload["blockers"]) or "- （无）"
    md = f"""# Freeze Manifest（C5，comp_freeze.py 生成）

- freeze_version：`{payload['freeze_version']}`
- 生成时间：{payload['generated_at']}
- 比赛 / 契约：{payload.get('competition')} / `{payload.get('contract_version')}`
- 候选 policy：`{payload.get('policy_id')}`
- 协议 / judge 版本：`{payload.get('protocol_version')}` / `{payload.get('judge_version')}`
- 状态：**{payload['status']}**

## 1. Provenance（多仓）

| 仓库 | 路径 | commit | dirty | uv.lock sha256 |
|---|---|---|---|---|
{rows}

## 2. 冻结产物

| 产物 | 路径 | sha256 | 存在 |
|---|---|---|---|
{arts}

## 3. 评测口径（来自 eval manifest）

- protocol：`{json.dumps(payload['manifest'].get('protocol'), ensure_ascii=False)}`
- policy：`{json.dumps(payload['manifest'].get('policy'), ensure_ascii=False)}`
- scenes：`{json.dumps(payload['manifest'].get('scenes'), ensure_ascii=False)}`
- judge：`{json.dumps(payload['manifest'].get('judge'), ensure_ascii=False)}`

## 4. 阻塞项

{blockers}

## 5. 冻结后规则

1. 只允许关键 bug 修复，修复后重跑回归并 `freeze_version` +1；
2. 不再开新训练线；对外数字只来自 `SCOREBOARD` 白名单；
3. 答辩前夜不改数字，只改讲法。
"""
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(md, encoding="utf-8")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_self_test() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "eval").mkdir()
        (root / "art.bin").write_bytes(b"hello-freeze")
        contract = {"contract_version": "t", "competition": "test"}
        manifest = {"policy_id": "p1", "protocol": {"protocol_version": "proto"},
                    "judge": {"version": "j"}, "policy": {"exported_sha256": "x"},
                    "scenes": {}}
        cp = root / "contract.json"; cp.write_text(json.dumps(contract), encoding="utf-8")
        mp = root / "manifest.json"; mp.write_text(json.dumps(manifest), encoding="utf-8")
        payload, code = build(cp, mp, [f"task={root}"], [f"art={root / 'art.bin'}"], allow_dirty=True)
        assert payload["policy_id"] == "p1"
        assert payload["artifacts"][0]["sha256"] == sha256_file(root / "art.bin")
        assert payload["artifacts"][0]["exists"] is True
        assert code == 0
        assert payload["status"] in ("OK", "DIRTY_ALLOWED")
        out_md, out_json = root / "freeze" / "F.md", root / "freeze" / "F.json"
        write_manifest(payload, out_md, out_json)
        assert out_md.is_file() and out_json.is_file()
        # 非 git 路径 + 不允许 dirty → BLOCKED
        payload2, code2 = build(cp, mp, ["task=/nonexistent-path-xyz"], [], allow_dirty=False)
        assert payload2["status"] == "BLOCKED" and code2 == 1
    print("comp_freeze.py self-test: OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="生成比赛冻结清单")
    ap.add_argument("--contract", type=Path)
    ap.add_argument("--manifest", type=Path)
    ap.add_argument("--repo", action="append", default=[], help="name=path，可重复")
    ap.add_argument("--artifact", action="append", default=[], help="name=path，可重复")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--json-out", type=Path)
    ap.add_argument("--allow-dirty", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return run_self_test()
    if not (args.contract and args.manifest and args.repo and args.out and args.json_out):
        ap.error("需要 --contract --manifest --repo --out --json-out（或 --self-test）")
    payload, code = build(args.contract, args.manifest, args.repo, args.artifact, args.allow_dirty)
    write_manifest(payload, args.out, args.json_out)
    print(f"freeze manifest written: {args.out} (+ {args.json_out})")
    print(f"status: {payload['status']}")
    for b in payload["blockers"]:
        print(f"  BLOCKER: {b}")
    return code


if __name__ == "__main__":
    sys.exit(main())
