#!/usr/bin/env python3
"""校验 policy/blackW/*/config.yaml 与目录名/权重文件是否自洽（部署侧 CI 断言）。

C++ 加载逻辑（rl_sdk.cpp）：``config = YAML::LoadFile(policy/<dir>/config.yaml)[<dir>]``
→ 顶层 key 必须等于目录名（如 ``blackW/comp_bc_v5``）；``model_name`` 必须是同目录下
真实存在的文件名（通常是 ``policy.pt``）。Python judge 有"只有一个 key 就用它"的兜底，
C++ 没有 → key 不符的目录能评测但不能部署（审计 ppo-deploy-audit-round1 F4）。

用法：
    pixi run python @20261024_blackw/scripts/check_policy_dirs.py            # 报告
    pixi run python @20261024_blackw/scripts/check_policy_dirs.py --names comp_bc_v5,...  # 只查指定
    pixi run python @20261024_blackw/scripts/check_policy_dirs.py --fix      # 修 key（只改 key 行）

退出码：0 = 全部通过；1 = 有非法目录。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import torch
import yaml

TASK = Path(__file__).resolve().parents[1]
POLICY_ROOT = TASK / "ws/src/rl_sar_blackw/policy/blackW"
FRAME_DIM = 57
HISTORY = 6


def check_dir(path: Path) -> list[str]:
    name = path.name
    issues: list[str] = []
    policy = path / "policy.pt"
    cfg_path = path / "config.yaml"
    if not policy.is_file():
        return [f"{name}: missing policy.pt"]
    if not cfg_path.is_file():
        return [f"{name}: missing config.yaml"]
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or len(data) != 1:
        return [f"{name}: config.yaml must have exactly one top-level key"]
    key = list(data)[0]
    if key != f"blackW/{name}":
        issues.append(f"{name}: top-level key {key!r} != 'blackW/{name}'")
    entry = data[key] if isinstance(data[key], dict) else {}
    model_name = entry.get("model_name")
    if not isinstance(model_name, str) or not (path / model_name).is_file():
        issues.append(f"{name}: model_name {model_name!r} not a file in this dir")
    try:
        obs = int(entry["num_observations"])
        hist = len(entry["observations_history"])
    except (KeyError, TypeError, ValueError):
        obs, hist = 0, 0
    if obs * hist != FRAME_DIM * HISTORY:
        issues.append(f"{name}: num_observations*history = {obs}*{hist} != 342")
    scale = entry.get("action_scale")
    if not isinstance(scale, list) or len(scale) != 16:
        issues.append(f"{name}: action_scale length != 16")
    else:
        expected = {3: 10.0, 7: -10.0, 11: 10.0, 15: -10.0}
        for index, want in expected.items():
            if float(scale[index]) != want:
                issues.append(f"{name}: action_scale[{index}]={scale[index]} != {want}")
    try:
        module = torch.jit.load(str(policy), map_location="cpu").eval()
        with torch.no_grad():
            shape = tuple(module(torch.zeros(1, FRAME_DIM * HISTORY)).shape)
        if shape != (1, 16):
            issues.append(f"{name}: forward shape {shape} != (1,16)")
    except Exception as error:  # noqa: BLE001 - report whatever torch says
        issues.append(f"{name}: torch.jit load/forward failed: {type(error).__name__}: {error}")
    return issues


def fix_key(path: Path) -> None:
    cfg_path = path / "config.yaml"
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or len(data) != 1:
        raise SystemExit(f"{cfg_path}: cannot fix, not a single-key mapping")
    old_key = list(data)[0]
    new_key = f"blackW/{path.name}"
    if old_key == new_key:
        return
    data = {new_key: data[old_key]}
    cfg_path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
                        encoding="utf-8")
    print(f"[fix] {path.name}: {old_key} -> {new_key}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--names", default="", help="comma-separated dir names (default: all)")
    ap.add_argument("--fix", action="store_true", help="rewrite the top-level key when mismatched")
    args = ap.parse_args()
    names = [name.strip() for name in args.names.split(",") if name.strip()]
    dirs = sorted([path for path in POLICY_ROOT.iterdir()
                   if path.is_dir() and (path / "config.yaml").is_file()])
    if names:
        wanted = set(names)
        dirs = [path for path in dirs if path.name in wanted]
        missing = wanted - {path.name for path in dirs}
        if missing:
            raise SystemExit(f"unknown policy dirs: {sorted(missing)}")
    bad = 0
    for path in dirs:
        issues = check_dir(path)
        if issues:
            bad += 1
            for issue in issues:
                print(f"[FAIL] {issue}")
            if args.fix:
                fix_key(path)
                after = check_dir(path)
                if after:
                    for issue in after:
                        print(f"[FAIL after fix] {issue}")
                else:
                    print(f"[fixed] {path.name}")
    print(f"\nchecked {len(dirs)} dirs, {bad} with issues")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
