#!/usr/bin/env python3
"""把一份导出的 TorchScript 权重安装成 rl_sar 可加载的部署策略目录。

部署契约（审计 ppo-deploy-audit-round1 F3/F4）：
  * 目录 ``policy/blackW/<name>/`` 下必须有 ``policy.pt`` + ``config.yaml``；
  * ``config.yaml`` 顶层 key 必须等于 ``blackW/<name>``（C++ 按目录名取子节点），
    ``model_name`` 必须等于 ``<name>``（决定加载哪个 .pt），``model_path`` 只是展示字段；
  * 观测 = 57 × 6 帧（frame-major 新→旧）、动作 16、右腿轮 action_scale 为 -10；
  * 权重必须能 ``torch.jit.load`` 且 ``forward(1×342) -> 1×16``。

用法（仓库根目录）：

    pixi run python @20261024_blackw/scripts/import_blackw_policy.py \
        --policy-pt prep.d/results/ppo_st30/exports/ppo_m0_hardmask_950/policy.pt \
        --name hardmask_950 \
        --source-contract prep.d/results/ppo_st30/exports/ppo_m0_hardmask_950/contract.json \
        --force

    # 只校验、不安装
    pixi run python @20261024_blackw/scripts/import_blackw_policy.py --check policy/blackW/comp_bc_v5

退出码：0 = 通过；1 = 校验失败。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

import torch
import yaml

TASK = Path(__file__).resolve().parents[1]
POLICY_ROOT = TASK / "ws/src/rl_sar_blackw/policy/blackW"
TEMPLATE = TASK / "scripts/templates/blackw_deploy_config.yaml"
FRAME_DIM = 57
ACTION_DIM = 16
HISTORY = 6
# policy joint order FL, FR, RL, RR; wheel action scale must be +10, -10, +10, -10.
WHEEL_ACTION_SIGN = {3: 10.0, 7: -10.0, 11: 10.0, 15: -10.0}
LEG_SCALE = 0.25


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_policy(path: Path) -> torch.jit.ScriptModule:
    module = torch.jit.load(str(path), map_location="cpu").eval()
    with torch.no_grad():
        out = module(torch.zeros(1, FRAME_DIM * HISTORY))
    if tuple(out.shape) != (1, ACTION_DIM):
        raise SystemExit(f"{path}: forward shape {tuple(out.shape)} != (1, {ACTION_DIM})")
    return module


def load_config(path: Path, name: str) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or len(data) != 1:
        raise SystemExit(f"{path}: config.yaml must have exactly one top-level key")
    key = list(data)[0]
    expected = f"blackW/{name}"
    if key != expected:
        raise SystemExit(f"{path}: top-level key {key!r} != directory name {expected!r}"
                         " (C++ loads config[key] and would fail)")
    entry = data[key]
    model_name = str(entry.get("model_name", ""))
    if not model_name or (path.parent / model_name).resolve() != (path.parent / "policy.pt").resolve():
        raise SystemExit(f"{path}: model_name {model_name!r} does not point at policy.pt in the "
                         "same dir (the loader uses dir + model_name; model_path is display-only)")
    if int(entry["num_observations"]) * len(entry["observations_history"]) != FRAME_DIM * HISTORY:
        raise SystemExit(f"{path}: num_observations x history != {FRAME_DIM}x{HISTORY}")
    scale = [float(value) for value in entry["action_scale"]]
    if len(scale) != ACTION_DIM:
        raise SystemExit(f"{path}: action_scale length {len(scale)} != {ACTION_DIM}")
    for index, expected_sign in WHEEL_ACTION_SIGN.items():
        if scale[index] != expected_sign:
            raise SystemExit(f"{path}: action_scale[{index}]={scale[index]} != {expected_sign} "
                             "(right leg wheels must be negative)")
    for index in range(ACTION_DIM):
        if index not in WHEEL_ACTION_SIGN and scale[index] != LEG_SCALE:
            raise SystemExit(f"{path}: action_scale[{index}]={scale[index]} != {LEG_SCALE}")
    return entry


def check_dir(path: Path) -> dict:
    name = path.name
    policy_path = path / "policy.pt"
    config_path = path / "config.yaml"
    if not policy_path.is_file() or not config_path.is_file():
        raise SystemExit(f"{path}: need both policy.pt and config.yaml")
    load_policy(policy_path)
    entry = load_config(config_path, name)
    manifest_path = path / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {}
    return {"name": name, "policy_sha256": sha256(policy_path),
            "config_sha256": sha256(config_path), "manifest": manifest,
            "model_name": entry["model_name"]}


def write_config(out_dir: Path, name: str) -> dict:
    template = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
    template_key = list(template)[0]
    entry = dict(template[template_key])
    entry["model_name"] = "policy.pt"
    entry["model_path"] = f"policy/blackW/{name}/policy.pt"
    data = {f"blackW/{name}": entry}
    (out_dir / "config.yaml").write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return load_config(out_dir / "config.yaml", name)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy-pt", type=Path, help="exported policy.pt")
    ap.add_argument("--name", help="target policy dir name under policy/blackW/")
    ap.add_argument("--source-contract", type=Path, default=None,
                    help="optional contract.json from the exporter (sha/action_scale cross-check)")
    ap.add_argument("--source-checkpoint", default="",
                    help="optional training checkpoint path for the manifest")
    ap.add_argument("--prune-old", action="store_true",
                    help="delete old candidate dirs listed in the manifest policy_root? (unused)")
    ap.add_argument("--check", type=Path, default=None,
                    help="only validate an existing policy dir, do not install")
    ap.add_argument("--force", action="store_true", help="overwrite an existing policy dir")
    args = ap.parse_args()

    if args.check is not None:
        info = check_dir(args.check)
        print(json.dumps({k: v for k, v in info.items() if k != "manifest"},
                         ensure_ascii=False, indent=2))
        print("OK")
        return 0

    if args.policy_pt is None or not args.name:
        raise SystemExit("--policy-pt and --name are required unless --check is used")
    if not args.policy_pt.is_file():
        raise SystemExit(f"missing {args.policy_pt}")
    out_dir = POLICY_ROOT / args.name
    if out_dir.exists() and not args.force:
        raise SystemExit(f"{out_dir} already exists; pass --force to overwrite")
    out_dir.mkdir(parents=True, exist_ok=True)

    # contract.json cross-check (the old exporter wrote +10 for all wheels: audit F3).
    if args.source_contract is not None and args.source_contract.is_file():
        contract = json.loads(args.source_contract.read_text(encoding="utf-8"))
        scale = [float(value) for value in contract.get("action_scale", [])]
        if len(scale) == ACTION_DIM:
            for index, expected_sign in WHEEL_ACTION_SIGN.items():
                if scale[index] != expected_sign:
                    print(f"[warn] contract.json action_scale[{index}]={scale[index]} != "
                          f"{expected_sign} (known old-exporter bug; config.yaml is authoritative)")

    shutil.copy2(args.policy_pt, out_dir / "policy.pt")
    entry = write_config(out_dir, args.name)
    load_policy(out_dir / "policy.pt")  # re-validate copied file
    manifest = {
        "name": args.name,
        "policy": str(out_dir / "policy.pt"),
        "policy_sha256": sha256(out_dir / "policy.pt"),
        "config": str(out_dir / "config.yaml"),
        "config_sha256": sha256(out_dir / "config.yaml"),
        "source_policy_pt": str(args.policy_pt),
        "source_checkpoint": args.source_checkpoint,
        "num_observations": entry["num_observations"],
        "history": entry["observations_history"],
        "action_scale": entry["action_scale"],
        "note": "deployment contract: 342 = 57x6 frame-major newest->oldest; 16 actions",
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                           encoding="utf-8")
    info = check_dir(out_dir)
    print(json.dumps({"installed": str(out_dir), "policy_sha256": info["policy_sha256"],
                      "config_sha256": info["config_sha256"]}, ensure_ascii=False, indent=2))
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
