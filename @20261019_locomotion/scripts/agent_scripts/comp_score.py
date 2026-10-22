#!/usr/bin/env python3
"""comp_score.py — 比赛评测记分板：校验 manifest/trials/summary 并重算官方分。

纯 stdlib；不读网络；不改评测产物。用法（从目标仓库根执行）：

    python3 comp/tools/comp_score.py \
        --contract comp/CONTRACT.json \
        --eval comp/eval \
        --out comp/SCOREBOARD.md \
        --json-out comp/SCOREBOARD.json

    # 只校验，不写记分板
    python3 comp/tools/comp_score.py --contract ... --eval ... --validate-only

    # 工具自检（无需真实数据）
    python3 comp/tools/comp_score.py --self-test

退出码：0 = 全部 valid 或仅 self-test 通过；1 = 存在 invalid 行；2 = 用法/输入错误。

校验内容（对应 shared-references/eval-artifact-contract.md）：
1. manifest 必填字段 / 三仓 commit / 协议版本 / 种子 / judge 版本；
2. summary 与 manifest 的 policy_id 一致，障碍集合与契约一致；
3. Part 1 分数 = 成功障碍分之和 + 返回奖励（全通过才给）；attempts ≤ 预算；
4. Part 2 best_score = score_curve 对 best_success_value 插值；attempts ≤ 预算；
5. grand_total = part1.total + part2.total；
6. trials（若存在）：每行 JSON、seed 在协议内、part/obstacle 已知。

设计说明：本工具只做 Type-A（机器可判）检查。分数是否"支持你的结论"由 Codex G4 审计，不由本工具决定。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import math
import sys
import tempfile
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

REQUIRED_MANIFEST = (
    "schema_version", "policy_id", "created_at", "repos", "policy",
    "scenes", "judge", "protocol", "results",
)
REQUIRED_REPOS = ("task", "training", "control")


# ---------------------------------------------------------------- helpers

def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def curve_points(curve: list[dict], value: float | None, unit: str | None = None) -> int:
    """按契约 score_curve 分段线性插值；低于首点 = 0，高于末点 = 末点分；小数按 Q5 舍去。"""
    if value is None:
        return 0
    if unit == "bool":
        return int(math.floor(curve[-1]["points"])) if float(value) == 1.0 else 0
    pts = sorted((float(p["value"]), float(p["points"])) for p in curve)
    if not pts:
        return 0
    v = float(value)
    if v <= pts[0][0]:
        return int(math.floor(pts[0][1])) if v == pts[0][0] else 0
    if v >= pts[-1][0]:
        return int(math.floor(pts[-1][1]))
    for (v0, p0), (v1, p1) in zip(pts, pts[1:]):
        if v0 <= v <= v1:
            if v1 == v0:
                return int(math.floor(p1))
            return int(math.floor(p0 + (p1 - p0) * (v - v0) / (v1 - v0)))
    return 0


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _err(errors: list[str], msg: str) -> None:
    errors.append(msg)


def _warn(warnings: list[str], msg: str) -> None:
    warnings.append(msg)


def validate_external_evidence(manifest: dict, summary: dict, contract: dict,
                               task_root: Path, diagnostic: bool) -> tuple[list[str], list[str]]:
    """Machine-check the evidence chain that summary alone cannot prove.

    - recompute scene/judge/contract sha256 recorded in the manifest;
    - Part 2 best difficulty must be a legal contract level (bool => exactly 1);
    - Part 1 final_time must be the fastest among the best-score attempts (confirmed rule).
    """
    errors: list[str] = []
    warnings: list[str] = []

    def _check_hash(entry: dict, label: str) -> None:
        rel = entry.get("file") or entry.get("path")
        recorded = entry.get("sha256") or ""
        if not rel:
            return
        path = Path(rel)
        if not path.is_absolute():
            path = task_root / path
        if not path.is_file():
            (_warn if diagnostic else _err)(warnings if diagnostic else errors,
                                            f"{label} 文件不存在，无法复核 hash: {rel}")
            return
        actual = _sha256(path)
        if recorded and actual != recorded:
            _err(errors, f"{label} sha256 不匹配: {rel}（manifest={recorded[:12]} actual={actual[:12]}）")

    scenes = manifest.get("scenes") or {}
    for key, entry in scenes.items():
        if isinstance(entry, dict):
            _check_hash(entry, f"scenes.{key}")
            for lvl in entry.get("levels") or []:
                _check_hash(lvl, f"scenes.{key}.levels")
    contract_meta = manifest.get("contract") or {}
    if isinstance(contract_meta, dict):
        _check_hash(contract_meta, "contract")
    judge = manifest.get("judge") or {}
    for fh in judge.get("file_hashes") or []:
        _check_hash(fh, "judge.file")
    for f in judge.get("files") or []:
        p = Path(f)
        if not p.is_absolute():
            p = task_root / p
        if not p.is_file():
            _warn(warnings, f"judge.files 路径不存在: {f}")

    # Part 2 legal difficulty levels
    p2_specs = {o["id"]: o for o in (contract.get("parts", {}).get("part2", {}) or {}).get("obstacles", [])}
    for oid, rec in ((summary.get("part2") or {}).get("obstacles") or {}).items():
        spec = p2_specs.get(oid)
        if spec is None:
            continue
        value = rec.get("best_success_value")
        if value is None:
            continue
        allowed = {float(p["value"]) for p in spec.get("score_curve", [])}
        if spec.get("unit") == "bool":
            if float(value) != 1.0:
                _err(errors, f"part2.{oid}.best_success_value={value} 非法（bool 只允许 1）")
        elif float(value) not in allowed:
            _err(errors, f"part2.{oid}.best_success_value={value} 不是契约合法档位 {sorted(allowed)}")

    # Part 1 final time: fastest among best-score attempts, computed from trials
    s1 = summary.get("part1") or {}
    if "final_time_s" in s1:
        trials = []
        # trials are not passed in here; caller adds them under the private key
        trials = manifest.get("__trials__") or []
        p1_obs = {o["id"]: o for o in (contract.get("parts", {}).get("part1", {}) or {}).get("obstacles", [])}
        by_attempt: dict[int, dict] = {}
        for t in trials:
            if t.get("part") != "part1":
                continue
            attempt = int(t.get("attempt") or 0)
            rec = by_attempt.setdefault(attempt, {"score": 0.0, "duration": float(t.get("duration_s") or 0.0),
                                                  "full": True, "return": False})
            oid = t.get("obstacle")
            j = t.get("judge") or {}
            if oid == "return_to_start":
                if "return_to_start_after_full" in (j.get("events") or []):
                    rec["return"] = True
                continue
            score = float(j.get("score") or 0.0)
            rec["score"] += score
            spec = p1_obs.get(oid)
            if spec is not None and score < float(spec.get("per_obstacle_score", 0)):
                rec["full"] = False
        if not by_attempt:
            (_warn if diagnostic else _err)(warnings if diagnostic else errors,
                                            "summary 声明 final_time_s 但 trials 中没有可复算的 attempt")
        else:
            for rec in by_attempt.values():
                if rec["return"] and rec["full"]:
                    rec["score"] += float(((contract.get("parts", {}).get("part1", {}) or {})
                                           .get("return_bonus") or {}).get("score", 100))
            best = max(r["score"] for r in by_attempt.values())
            best_durations = [r["duration"] for r in by_attempt.values() if r["score"] == best]
            expected = min(best_durations)
            got = float(s1.get("final_time_s") or 0.0)
            if abs(got - expected) > 1e-6:
                _err(errors, f"part1.final_time_s={got} 应为最高分尝试中最快 {expected}")
            if "final_score" in s1 and abs(float(s1["final_score"]) - best) > 1e-6:
                _err(errors, f"part1.final_score={s1['final_score']} 应为 {best}")
    return errors, warnings


# ---------------------------------------------------------------- validation

def validate_manifest(manifest: dict, policy_dir: Path) -> list[str]:
    errors: list[str] = []
    diagnostic = bool((manifest.get("protocol") or {}).get("diagnostic"))
    for key in REQUIRED_MANIFEST:
        if key not in manifest:
            _err(errors, f"manifest 缺字段: {key}")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        _err(errors, f"manifest.schema_version != {SCHEMA_VERSION}")
    for repo in REQUIRED_REPOS:
        entry = (manifest.get("repos") or {}).get(repo)
        if not isinstance(entry, dict):
            _err(errors, f"manifest.repos.{repo} 缺失")
            continue
        if not entry.get("commit"):
            _err(errors, f"manifest.repos.{repo}.commit 为空")
        elif diagnostic and str(entry["commit"]).startswith("unknown"):
            pass  # diagnostic 允许 unknown commit（不计入正式分数）
        if "dirty" not in entry:
            _err(errors, f"manifest.repos.{repo}.dirty 缺失")
        elif entry.get("dirty") and not diagnostic:
            _err(errors, f"manifest.repos.{repo}.dirty=true（评测应在干净 commit 上）")
    policy = manifest.get("policy") or {}
    for key in ("checkpoint_sha256", "exported_sha256", "obs_dim", "action_dim"):
        if key not in policy:
            _err(errors, f"manifest.policy.{key} 缺失")
    protocol = manifest.get("protocol") or {}
    if not protocol.get("protocol_version"):
        _err(errors, "manifest.protocol.protocol_version 缺失")
    seeds = protocol.get("seeds")
    if not isinstance(seeds, list):
        _err(errors, "manifest.protocol.seeds 不是数组")
    elif not seeds and not diagnostic:
        _err(errors, "manifest.protocol.seeds 为空（正式评测必须有种子）")
    if not (manifest.get("judge") or {}).get("version"):
        _err(errors, "manifest.judge.version 缺失")
    results = manifest.get("results") or {}
    for key in ("trials", "summary"):
        rel = results.get(key)
        if not rel:
            _err(errors, f"manifest.results.{key} 缺失")
        elif not (policy_dir / rel).is_file():
            _err(errors, f"manifest.results.{key} 指向的文件不存在: {rel}")
    return errors


def validate_summary(summary: dict, manifest: dict, contract: dict,
                     trials: list[dict] | None = None) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    trials = trials or []
    by_id = {t.get("trial_id"): t for t in trials if t.get("trial_id")}
    by_obstacle: dict[tuple[str, str], list[dict]] = {}
    for t in trials:
        by_obstacle.setdefault((str(t.get("part")), str(t.get("obstacle"))), []).append(t)
    if summary.get("schema_version") != SCHEMA_VERSION:
        _err(errors, "summary.schema_version 不匹配")
    if summary.get("policy_id") != manifest.get("policy_id"):
        _err(errors, "summary.policy_id 与 manifest 不一致")

    parts = contract.get("parts") or {}
    part1 = parts.get("part1") or {}
    part2 = parts.get("part2") or {}
    p1_obs = {o["id"]: o for o in part1.get("obstacles", [])}
    p2_obs = {o["id"]: o for o in part2.get("obstacles", [])}
    proto = manifest.get("protocol") or {}
    diagnostic = bool(proto.get("diagnostic"))

    # ---- Part 1
    s1 = summary.get("part1") or {}
    sum1 = 0
    seen1 = s1.get("obstacles") or {}
    for oid, spec in p1_obs.items():
        rec = seen1.get(oid)
        if rec is None:
            _err(errors, f"part1 缺障碍记录: {oid}")
            continue
        success = bool(rec.get("success"))
        score = rec.get("score")
        per = int(spec.get("per_obstacle_score", 0))
        allowed = {per}
        for raw in (spec.get("partial_scores") or {}).values():
            if isinstance(raw, (int, float)) and not isinstance(raw, bool):
                allowed.add(int(min(float(raw), per)))
        if success:
            if score not in allowed:
                _err(errors, f"part1.{oid}.score={score} 应为 {per} 或部分分 {sorted(allowed)}")
        elif score != 0:
            _err(errors, f"part1.{oid}.score={score} 应为 0（未成功）")
        sum1 += int(score or 0)
    for oid in seen1:
        if oid not in p1_obs:
            _err(errors, f"part1 出现契约外障碍: {oid}")
    for oid, rec in seen1.items():
        ev = list(rec.get("evidence") or [])
        obs_trials = by_obstacle.get(("part1", oid), [])
        succ_trials = [t for t in obs_trials if (t.get("judge") or {}).get("status") == "success"]
        if rec.get("success"):
            if not ev:
                _err(errors, f"part1.{oid} success 缺 evidence trial id")
            for eid in ev:
                t = by_id.get(eid)
                if t is None:
                    _err(errors, f"part1.{oid} evidence 指向不存在的 trial: {eid}")
                elif (t.get("judge") or {}).get("status") != "success":
                    _err(errors, f"part1.{oid} evidence {eid} 的 judge 状态不是 success")
        else:
            for eid in ev:
                t = by_id.get(eid)
                if t and (t.get("judge") or {}).get("status") == "success":
                    _err(errors, f"part1.{oid} 标 fail 但 evidence {eid} 是 success")
            if succ_trials:
                _err(errors, f"part1.{oid} 标 fail 但 trials 中存在 success 记录")
        if obs_trials and int(rec.get("attempts_used") or len(obs_trials)) != len(obs_trials):
            _warn(warnings, f"part1.{oid} attempts 与 trials 条数不一致（diagnostic 常见）")
    def _full_success(oid: str) -> bool:
        rec = seen1.get(oid) or {}
        return bool(rec.get("success")) and int(rec.get("score") or 0) >= int(p1_obs[oid].get("per_obstacle_score", 0))
    all_ok = bool(p1_obs) and all(_full_success(o) for o in p1_obs)
    bonus = part1.get("return_bonus") or {}
    return_expected = int(bonus.get("score", 0)) if (all_ok and bool(s1.get("return_to_start"))) else 0
    if int(s1.get("return_score") or 0) != return_expected:
        _err(errors, f"part1.return_score={s1.get('return_score')} 应为 {return_expected}")
    if return_expected > 0:
        ev_id = s1.get("return_evidence")
        t = by_id.get(ev_id) if ev_id else None
        if t is None:
            _err(errors, "part1 有返回奖励但缺 return_evidence trial")
        elif (t.get("part1") if False else t.get("part")) != "part1" or \
                t.get("obstacle") != "return_to_start" or \
                (t.get("judge") or {}).get("status") != "success" or \
                "return_to_start_after_full" not in ((t.get("judge") or {}).get("events") or []):
            _err(errors, "part1 return_evidence trial 未证明全满分后返回出发区")
    p1_total = sum1 + return_expected
    if int(s1.get("total") or 0) != p1_total:
        _err(errors, f"part1.total={s1.get('total')} 重算为 {p1_total}")
    budget1 = int((part1.get("attempts") or {}).get("count", 10 ** 9))
    if int(s1.get("attempts_used") or 0) > budget1:
        msg = f"part1.attempts_used={s1.get('attempts_used')} 超预算 {budget1}"
        (_warn(warnings, msg + "（diagnostic 行不据此判 invalid）") if diagnostic else _err(errors, msg))
    if proto.get("attempts_part1_total") not in (None, budget1) and not diagnostic:
        _err(errors, "manifest.protocol.attempts_part1_total 与契约不一致")

    # ---- Part 2
    s2 = summary.get("part2") or {}
    sum2 = 0
    seen2 = s2.get("obstacles") or {}
    budget2 = int(part2.get("attempts_per_obstacle", 10 ** 9))
    for oid, spec in p2_obs.items():
        rec = seen2.get(oid)
        if rec is None:
            _err(errors, f"part2 缺障碍记录: {oid}")
            continue
        best_raw = rec.get("best_success_value")
        expected = curve_points(spec.get("score_curve", []), best_raw, spec.get("unit"))
        expected = min(expected, int(spec.get("max_score", 10 ** 9)))
        got = int(rec.get("best_score") or 0)
        if got != expected:
            _err(errors, f"part2.{oid}.best_score={got} 按曲线应为 {expected}（value={best_raw}）")
        if int(rec.get("attempts_used") or 0) > budget2:
            msg = f"part2.{oid}.attempts_used 超预算 {budget2}"
            (_warn(warnings, msg + "（diagnostic 行不据此判 invalid）") if diagnostic else _err(errors, msg))
        sum2 += got
    for oid in seen2:
        if oid not in p2_obs:
            _err(errors, f"part2 出现契约外障碍: {oid}")
    for oid, rec in seen2.items():
        obs_trials = by_obstacle.get(("part2", oid), [])
        succ_trials = [t for t in obs_trials
                       if t.get("success") is True or (t.get("judge") or {}).get("status") == "success"]
        value = rec.get("best_success_value")
        if value is None:
            if succ_trials:
                _err(errors, f"part2.{oid} best_success_value 为空但 trials 中存在成功记录")
        else:
            matched = [t for t in succ_trials
                       if t.get("difficulty") == value or t.get("value") == value]
            if not matched:
                _err(errors, f"part2.{oid} best_success_value={value} 无对应成功 trial")
        if obs_trials and int(rec.get("attempts_used") or 0) != len(obs_trials):
            _warn(warnings, f"part2.{oid} attempts 与 trials 条数不一致（diagnostic 常见）")
    if int(s2.get("total") or 0) != sum2:
        _err(errors, f"part2.total={s2.get('total')} 重算为 {sum2}")
    if proto.get("attempts_part2_per_obstacle") not in (None, budget2) and not diagnostic:
        _err(errors, "manifest.protocol.attempts_part2_per_obstacle 与契约不一致")

    grand = p1_total + sum2
    if int(summary.get("grand_total") or 0) != grand:
        _err(errors, f"grand_total={summary.get('grand_total')} 重算为 {grand}")
    if p1_total > int(part1.get("max_score", 10 ** 9)):
        _err(errors, "part1 超过契约满分")
    if sum2 > int(part2.get("max_score", 10 ** 9)):
        _err(errors, "part2 超过契约满分")
    return errors, warnings


def validate_trials(policy_dir: Path, manifest: dict) -> list[str]:
    errors: list[str] = []
    rel = (manifest.get("results") or {}).get("trials")
    if not rel or not (policy_dir / rel).is_file():
        return errors
    seeds = set((manifest.get("protocol") or {}).get("seeds") or [])
    with (policy_dir / rel).open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as exc:
                _err(errors, f"trials 第 {lineno} 行不是 JSON: {exc}")
                continue
            if seeds and rec.get("seed") is not None and rec["seed"] not in seeds:
                _err(errors, f"trials 第 {lineno} 行 seed={rec['seed']} 不在协议种子里")
            if not rec.get("trial_id"):
                _err(errors, f"trials 第 {lineno} 行缺 trial_id")
    return errors


# ---------------------------------------------------------------- scoreboard

def load_trials(policy_dir: Path, manifest: dict) -> tuple[list[dict], list[str]]:
    errors: list[str] = []
    rel = (manifest.get("results") or {}).get("trials")
    if not rel or not (policy_dir / rel).is_file():
        return [], errors
    trials: list[dict] = []
    with (policy_dir / rel).open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                trials.append(json.loads(line))
            except json.JSONDecodeError as exc:
                _err(errors, f"trials 第 {lineno} 行不是 JSON: {exc}")
    return trials, errors


def score_one(policy_dir: Path, contract: dict) -> dict:
    row: dict[str, Any] = {"policy_dir": str(policy_dir), "errors": [], "warnings": []}
    manifest_path = policy_dir / "manifest.json"
    summary_path = policy_dir / "summary.json"
    if not manifest_path.is_file() or not summary_path.is_file():
        row["errors"].append("缺 manifest.json 或 summary.json")
        row["status"] = "invalid"
        return row
    try:
        manifest = load_json(manifest_path)
        summary = load_json(summary_path)
    except json.JSONDecodeError as exc:
        row["errors"].append(f"JSON 解析失败: {exc}")
        row["status"] = "invalid"
        return row
    row["policy_id"] = manifest.get("policy_id") or summary.get("policy_id") or policy_dir.name
    row["date"] = str(manifest.get("created_at"))[:10]
    row["errors"] += validate_manifest(manifest, policy_dir)
    trials, trial_errors = load_trials(policy_dir, manifest)
    row["errors"] += trial_errors
    errs, warns = validate_summary(summary, manifest, contract, trials)
    row["errors"] += errs
    row["warnings"] += warns
    row["errors"] += validate_trials(policy_dir, manifest)
    row["part1_total"] = int((summary.get("part1") or {}).get("total") or 0)
    row["part2_total"] = int((summary.get("part2") or {}).get("total") or 0)
    row["grand_total"] = int(summary.get("grand_total") or 0)
    row["summary_path"] = str(summary_path)
    row["diagnostic"] = bool((manifest.get("protocol") or {}).get("diagnostic"))
    row["status"] = "valid" if not row["errors"] else "invalid"
    if row["status"] == "valid" and row["diagnostic"]:
        row["status"] = "diagnostic"
    return row


def write_scoreboard(rows: list[dict], contract: dict, out_md: Path, out_json: Path) -> None:
    now = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# 记分板（由 comp_score.py 生成，不要手改数字）",
        "",
        f"> 生成时间：{now}　契约：{contract.get('contract_version', '?')}",
        "> 对外引用规则：只有 `valid` 且通过 G4 的行可以被引用，且必须带 policy_id + 证据路径。",
        "",
        "| policy_id | 日期 | Part1 | Part2 | 总分 | 状态 | 证据 |",
        "|---|---|---:|---:|---:|---|---|",
    ]
    for r in rows:
        status = r["status"]
        if r.get("errors"):
            status += ":" + "; ".join(r["errors"][:2])
        lines.append(
            f"| `{r.get('policy_id', '?')}` | {r.get('date', '')} | "
            f"{r.get('part1_total', 0)} | {r.get('part2_total', 0)} | {r.get('grand_total', 0)} | "
            f"{status} | `{r.get('summary_path', '')}` |"
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    payload = {
        "generated_at": now,
        "contract_version": contract.get("contract_version"),
        "rows": rows,
    }
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- self-test

def _synthetic() -> tuple[dict, dict, dict, dict]:
    """自检用的最小契约/三件套（不依赖外部模板文件，便于复制到目标仓库后仍可自检）。"""
    contract = {
        "contract_version": "selftest",
        "parts": {
            "part1": {
                "max_score": 200, "attempts": {"scope": "run", "count": 3},
                "obstacles": [{"id": "a", "per_obstacle_score": 100},
                              {"id": "b", "per_obstacle_score": 100}],
                "return_bonus": {"id": "return", "score": 100, "requires": "all_obstacles_success"},
            },
            "part2": {
                "max_score": 300, "attempts_per_obstacle": 4,
                "obstacles": [
                    {"id": "p", "name": "p", "max_score": 200, "unit": "cm",
                     "score_curve": [{"value": 10, "points": 10}, {"value": 20, "points": 50}]},
                    {"id": "q", "name": "q", "max_score": 100, "unit": "bool",
                     "score_curve": [{"value": 1, "points": 100}]},
                ],
            },
        },
    }
    manifest = {
        "schema_version": 1, "policy_id": "selftest-run-v1",
        "created_at": "2026-10-22T20:00:00+08:00",
        "repos": {k: {"path": k, "commit": "abc123", "dirty": False}
                  for k in ("task", "training", "control")},
        "policy": {"checkpoint_sha256": "x", "exported_sha256": "y", "obs_dim": 45, "action_dim": 12},
        "scenes": {}, "judge": {"version": "j"},
        "protocol": {"protocol_version": "proto", "seeds": [0, 1, 2],
                     "attempts_part1_total": 3, "attempts_part2_per_obstacle": 4,
                     "operator": "scripted"},
        "results": {"trials": "trials.jsonl", "summary": "summary.json"},
    }
    summary = {
        "schema_version": 1, "policy_id": "selftest-run-v1",
        "part1": {"attempts_used": 1,
                  "obstacles": {"a": {"success": True, "score": 100},
                                "b": {"success": False, "score": 0}},
                  "return_to_start": False, "return_score": 0, "total": 100},
        "part2": {"obstacles": {"p": {"best_success_value": 20, "best_score": 50, "attempts_used": 1},
                                "q": {"best_success_value": 1, "best_score": 100, "attempts_used": 1}},
                  "total": 150},
        "grand_total": 250,
    }
    return contract, manifest, summary, {}


def run_self_test() -> int:
    contract, manifest, summary, _ = _synthetic()
    trials = [
        {"trial_id": "t-a", "part": "part1", "obstacle": "a", "seed": 0,
         "judge": {"status": "success"}},
        {"trial_id": "t-b", "part": "part1", "obstacle": "b", "seed": 0,
         "judge": {"status": "fail"}},
        {"trial_id": "t-p", "part": "part2", "obstacle": "p", "seed": 0,
         "difficulty": 20, "success": True},
        {"trial_id": "t-q", "part": "part2", "obstacle": "q", "seed": 0,
         "difficulty": 1, "success": True},
    ]
    summary["part1"]["obstacles"]["a"]["evidence"] = ["t-a"]
    summary["part1"]["obstacles"]["b"]["evidence"] = ["t-b"]
    assert curve_points([{"value": 10, "points": 10}, {"value": 20, "points": 50}], 5, "cm") == 0
    assert curve_points([{"value": 10, "points": 10}, {"value": 20, "points": 50}], 20, "cm") == 50
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "comp" / "eval" / "selftest-run-v1"
        root.mkdir(parents=True)
        (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        (root / "trials.jsonl").write_text("".join(json.dumps(t) + "\n" for t in trials), encoding="utf-8")
        (root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False), encoding="utf-8")
        row = score_one(root, contract)
        assert row["status"] == "valid", row["errors"]
        assert row["grand_total"] == 250, row
        assert row["part1_total"] == 100 and row["part2_total"] == 150, row

        # 违规 1：尝试次数超预算
        bad = json.loads(json.dumps(summary))
        bad["part1"]["attempts_used"] = 99
        (root / "summary.json").write_text(json.dumps(bad), encoding="utf-8")
        row = score_one(root, contract)
        assert row["status"] == "invalid" and any("attempts_used" in e for e in row["errors"]), row

        # 违规 2：手改总分
        bad2 = json.loads(json.dumps(summary))
        bad2["grand_total"] = 999
        (root / "summary.json").write_text(json.dumps(bad2), encoding="utf-8")
        row = score_one(root, contract)
        assert any("grand_total" in e for e in row["errors"]), row

        # 违规 3：Part2 best_score 与曲线不符
        bad3 = json.loads(json.dumps(summary))
        bad3["part2"]["obstacles"]["p"]["best_score"] = 200
        (root / "summary.json").write_text(json.dumps(bad3), encoding="utf-8")
        row = score_one(root, contract)
        assert any("best_score" in e for e in row["errors"]), row

        # 违规 4：summary 报 success 但 trials 里没有 success（证据链断裂）
        (root / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
        broken = json.loads(json.dumps(trials))
        broken[0]["judge"]["status"] = "fail"
        (root / "trials.jsonl").write_text("".join(json.dumps(t) + "\n" for t in broken), encoding="utf-8")
        row = score_one(root, contract)
        assert any("part1.a" in e for e in row["errors"]), row

        # 违规 5：Part2 best_success_value 无对应成功 trial
        (root / "trials.jsonl").write_text("".join(json.dumps(t) + "\n" for t in trials), encoding="utf-8")
        bad5 = json.loads(json.dumps(trials))
        bad5[2]["difficulty"] = 15
        (root / "trials.jsonl").write_text("".join(json.dumps(t) + "\n" for t in bad5), encoding="utf-8")
        row = score_one(root, contract)
        assert any("best_success_value" in e for e in row["errors"]), row
    print("comp_score.py self-test: OK")
    return 0


# ---------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="比赛评测记分板校验与重算")
    ap.add_argument("--contract", type=Path)
    ap.add_argument("--eval", type=Path, dest="eval_dir", help="包含 <policy_id>/ 子目录的评测根目录")
    ap.add_argument("--out", type=Path, help="写 SCOREBOARD.md")
    ap.add_argument("--json-out", type=Path, help="写 SCOREBOARD.json")
    ap.add_argument("--task-root", type=Path, default=Path("."),
                    help="任务目录根（用于复核 manifest 中场景/judge/契约的相对路径 hash）")
    ap.add_argument("--validate-only", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return run_self_test()
    if not args.contract or not args.eval_dir:
        ap.error("需要 --contract 与 --eval（或 --self-test）")
    if not args.contract.is_file():
        print(f"ERROR: contract not found: {args.contract}", file=sys.stderr)
        return 2
    contract = load_json(args.contract)
    policy_dirs = (sorted(p for p in args.eval_dir.iterdir()
                         if p.is_dir() and not p.name.startswith(("_", ".")))
                   if args.eval_dir.is_dir() else [])
    if not policy_dirs:
        print(f"ERROR: no policy dirs under {args.eval_dir}", file=sys.stderr)
        return 2

    rows = [score_one(p, contract) for p in policy_dirs]
    bad = [r for r in rows if r["status"] == "invalid"]
    if not args.validate_only and args.out and args.json_out:
        write_scoreboard(rows, contract, args.out, args.json_out)
        print(f"scoreboard written: {args.out} (+ {args.json_out})")
    for r in rows:
        flag = {"valid": "ok  ", "diagnostic": "diag", "invalid": "BAD "}.get(r["status"], "BAD ")
        print(f"[{flag}] {r.get('policy_id')}: part1={r.get('part1_total')} part2={r.get('part2_total')} total={r.get('grand_total')}")
        for e in r["errors"]:
            print(f"      - {e}")
        for w in r["warnings"]:
            print(f"      ~ {w}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
