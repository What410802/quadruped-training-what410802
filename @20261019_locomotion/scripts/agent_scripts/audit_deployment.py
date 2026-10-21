"""Audit the P0 deployment policy/scene against competition sensor/effort rules."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import mujoco
import numpy as np
import torch
import yaml


def _joint_kind(name: str) -> str:
    if "hip" in name:
        return "hip"
    if "thigh" in name:
        return "thigh"
    if "calf" in name:
        return "calf"
    raise ValueError(f"unknown joint: {name}")


def audit_scene(path: str, rules: dict) -> dict:
    model = mujoco.MjSpec.from_file(path).compile()
    act_names = [mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_ACTUATOR, i) or "" for i in range(model.nu)]
    ctrlranges = {}
    for i, name in enumerate(act_names):
        ctrlranges[name] = [float(v) for v in model.actuator_ctrlrange[i]]
    violations: list[str] = []
    for name, ctrl in ctrlranges.items():
        if not name.startswith("motor_"):
            continue
        joint = name[len("motor_"):]
        kind = _joint_kind(joint)
        max_allowed = float(rules["joints"][f"{kind}_max_effort_nm"])
        if max(abs(ctrl[0]), abs(ctrl[1])) > max_allowed:
            violations.append(f"{joint}: actuator ctrlrange {ctrl} > {max_allowed}")
    return {"scene": path, "nu": model.nu, "actuators": ctrlranges, "violations": violations}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="@20261019_locomotion/config/deployment-audit.yaml")
    parser.add_argument("--control-repo", default="")
    parser.add_argument("--json", default="prep.d/results/deployment_audit.json")
    args = parser.parse_args()
    config_path = Path(args.config)
    task_root = config_path.parent.parent
    cfg = yaml.safe_load(config_path.read_text())
    rules = cfg
    report = {"config": args.config, "policy": {}, "scenes": [], "violations": []}

    policy_path = task_root / cfg["policy"]["path"]
    policy = torch.jit.load(str(policy_path), map_location="cpu").eval()
    dummy = torch.zeros(1, int(cfg["policy"]["actor_obs_dimension"]))
    with torch.no_grad():
        out = policy(dummy)
    report["policy"] = {
        "path": str(policy_path),
        "input_shape": list(dummy.shape),
        "output_shape": list(out.shape),
        "actor_obs_dimension": int(cfg["policy"]["actor_obs_dimension"]),
        "effort_limit_nm": float(cfg["policy"]["effort_limit_nm"]),
    }
    if int(out.shape[-1]) != 12:
        report["violations"].append(f"policy action dimension {out.shape[-1]} != 12")
    for source in cfg["policy"]["banned_actor_sources"]:
        if source in cfg["policy"]["actor_obs_terms"]:
            report["violations"].append(f"banned actor source present: {source}")
    for scene in cfg["scenes"]:
        result = audit_scene(str(task_root / scene), rules)
        report["scenes"].append(result)
        report["violations"].extend(result["violations"])

    if args.control_repo:
        ctrl_cfg = Path(args.control_repo) / "configs/robots/black.yaml"
        if ctrl_cfg.exists():
            raw = yaml.safe_load(ctrl_cfg.read_text())
            for j in raw.get("joints", []):
                kind = _joint_kind(j["name"])
                max_effort = float(j.get("max_effort", 0.0))
                limit = float(rules["joints"]["control_repo_max_effort"][kind])
                if max_effort > limit:
                    report["violations"].append(f"{j['name']}: control max_effort {max_effort} > {limit}")
    report["ok"] = not report["violations"]
    print(json.dumps(report, indent=2))
    out = Path(args.json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
