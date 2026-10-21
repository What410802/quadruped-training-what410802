"""Validate the manual fallback state-machine config."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml


DEFAULT = "@20261019_locomotion/config/manual-state-machine.yaml"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=DEFAULT)
    args = parser.parse_args()
    cfg = yaml.safe_load(Path(args.config).read_text())
    states = cfg.get("states", {})
    if not states:
        raise SystemExit("no states")
    default = cfg.get("default_state")
    if default not in states:
        raise SystemExit(f"default_state {default!r} not in states")
    for name, spec in states.items():
        for key in ("purpose", "policy", "runtime_policy", "max_vx", "max_vy", "max_wz"):
            if key not in spec:
                raise SystemExit(f"{name}: missing {key}")
        for key in ("max_vx", "max_vy", "max_wz"):
            if float(spec[key]) < 0:
                raise SystemExit(f"{name}: {key} must be non-negative")
    print(f"config: {args.config}")
    print(f"default: {default}; states: {len(states)}")
    for name, spec in states.items():
        print(f"{name:12s} policy={spec['policy']:15s} runtime={spec['runtime_policy']:12s} vx<={spec['max_vx']} vy<={spec['max_vy']} wz<={spec['max_wz']}")
    print("OK")


if __name__ == "__main__":
    main()
