#!/usr/bin/env python3
"""Static parity check: Part2 training predicates vs the authoritative judge v5.

Catches the audit P1-11 class of drift without a GPU run:
  * lane half width: training constant vs every level's judge rule;
  * success hold time: training hold steps (= 0.3 s * 50 Hz) vs judge hold_s;
  * required judge keys: stairs must carry descend_end_x (audit P1-5);
  * fail-closed guards still present in eval_blackw_part2.py.

Usage (from repo root):
    pixi run python @20261024_blackw/scripts/check_predicate_judge_parity.py
Exit code 0 = parity, 1 = drift found.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV = DEFAULT_ROOT / "@20261024_blackw/training/blackw/env_cfgs.py"
DEFAULT_LEVELS = (DEFAULT_ROOT / "@20261024_blackw/ws/src/rl_sar_blackw/scenes/blackW"
                  / "part2_official_levels.json")
DEFAULT_JUDGE = DEFAULT_ROOT / "@20261024_blackw/scripts/eval_blackw_part2.py"
JUDGE_HZ = 50.0


def _read_consts(env_path: Path) -> dict:
    text = env_path.read_text(encoding="utf-8")
    out: dict = {}
    m = re.search(r"^PART2_LANE_HALF_WIDTH\s*=\s*([0-9.]+)", text, re.M)
    if not m:
        raise SystemExit(f"{env_path}: PART2_LANE_HALF_WIDTH not found")
    out["lane_half_width"] = float(m.group(1))
    m = re.search(r'PART2_HOLD_STEPS\s*=\s*int\(__import__\("os"\)\.environ\.get\(\s*'
                  r'"BLACKW_SUCCESS_HOLD_STEPS",\s*"(\d+)"\)\)', text)
    if not m:
        m = re.search(r'BLACKW_SUCCESS_HOLD_STEPS",\s*"(\d+)"', text)
    if not m:
        raise SystemExit(f"{env_path}: PART2_HOLD_STEPS not found")
    out["hold_steps"] = int(m.group(1))
    out["hold_steps_used"] = "PART2_HOLD_STEPS" in text
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--env-cfg", type=Path, default=DEFAULT_ENV)
    ap.add_argument("--levels", type=Path, default=DEFAULT_LEVELS)
    ap.add_argument("--judge", type=Path, default=DEFAULT_JUDGE)
    args = ap.parse_args()

    consts = _read_consts(args.env_cfg)
    payload = json.loads(args.levels.read_text(encoding="utf-8"))
    levels = payload["levels"] if isinstance(payload, dict) else payload
    judge_src = args.judge.read_text(encoding="utf-8")
    # Judge terminal hold = level hold_s + a shared post-terminal confirmation time;
    # training counts PART2_HOLD_STEPS at 50 Hz (audit/handoff: 0.3 s = 15 steps).
    m = re.search(r"^TERMINAL_HOLD_EXTRA_S\s*=\s*([0-9.]+)", judge_src, re.M)
    hold_extra = float(m.group(1)) if m else 0.0
    consts["hold_extra_s"] = hold_extra

    failures: list[str] = []

    # 1) lane width must be single-source in both places
    for e in levels:
        j = e["judge"]
        if "lane_half_width" not in j:
            failures.append(f"{e.get('key')}: judge missing lane_half_width")
        elif abs(float(j["lane_half_width"]) - consts["lane_half_width"]) > 1e-9:
            failures.append(
                f"{e.get('key')}: judge lane {j['lane_half_width']} != training "
                f"{consts['lane_half_width']}")

    # 2) hold: judge hold_s * 50 Hz must match training success hold steps
    for e in levels:
        j = e["judge"]
        if "hold_s" not in j:
            failures.append(f"{e.get('key')}: judge missing hold_s")
            continue
        steps = (float(j["hold_s"]) + hold_extra) * JUDGE_HZ
        if abs(steps - consts["hold_steps"]) > 0.51:
            failures.append(
                f"{e.get('key')}: hold_s={j['hold_s']}+extra={hold_extra} "
                f"({steps:g} steps) != training PART2_HOLD_STEPS={consts['hold_steps']}")

    # 3) stairs must carry descend_end_x (fallback would be a false success)
    for e in levels:
        j = e["judge"]
        if j.get("kind") == "stairs" and "descend_end_x" not in j:
            failures.append(f"{e.get('key')}: stairs missing descend_end_x")

    # 4) fail-closed guards must still be in the judge source
    guard_checks = {
        "wheel body count guard": "len(self.wheel_bodies) != 4",
        "explicit lane key": 'float(self.j["lane_half_width"])',
        "explicit hold key": 'float(self.j["hold_s"])',
        "stairs explicit descend_end_x": 'self.j["descend_end_x"]',
    }
    for name, needle in guard_checks.items():
        if needle not in judge_src:
            failures.append(f"judge lost fail-closed guard: {name} ({needle!r})")

    # 5) training predicate must actually use the shared hold constant
    if not consts["hold_steps_used"]:
        failures.append("env_cfgs: PART2_HOLD_STEPS defined but not referenced")

    print(f"env={args.env_cfg}")
    print(f"levels={len(levels)}  lane={consts['lane_half_width']}  "
          f"hold_steps={consts['hold_steps']} ({consts['hold_steps'] / JUDGE_HZ:.2f} s, "
          f"judge hold_s={0.2}+{hold_extra})")
    if failures:
        print(f"PARITY FAIL ({len(failures)} issue(s)):")
        for f in failures:
            print(" -", f)
        return 1
    print("PARITY OK: training predicates and judge v5 knobs agree")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
