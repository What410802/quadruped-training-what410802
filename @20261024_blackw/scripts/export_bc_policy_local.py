#!/usr/bin/env python3
"""Export a behaviour-cloned blackW actor (native history layout) for deployment.

The BC actor trained by ``train_bc_blackw.py`` consumes the MjLab native history
layout (term-major, oldest -> newest).  Deployment (rl_sar / the local judge) uses
frame-major newest -> oldest, so the first Linear input columns are permuted
exactly like ``export_history_policy.py`` does for PPO checkpoints.  The resulting
TorchScript policy plus a mirrored-wheel ``config.yaml`` can be dropped into
``ws/src/rl_sar_blackw/policy/blackW/<name>/`` and evaluated with
``eval_blackw_part2.py`` or the rl_sar launch files.

Usage (from MyMonoRepo.d):
  pixi run python @20261024_blackw/scripts/export_bc_policy_local.py \
      --bc prep.d/bc_data/bc_actor_v1.pt --name comp_bc_v1
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import numpy as np
import torch
import yaml

TASK = Path(__file__).resolve().parents[1]
POLICY_ROOT = TASK / "ws/src/rl_sar_blackw/policy/blackW"
FRAME_DIM = 57
HISTORY = 6
TERM_LAYOUT = (
    (3, 0),    # command
    (3, 3),    # base_ang_vel
    (3, 6),    # projected_gravity
    (16, 9),   # joint_pos (wheel positions zeroed)
    (16, 25),  # joint_vel
    (16, 41),  # previous actions
)


def build_permutation(history_length: int = HISTORY) -> np.ndarray:
    p = np.zeros(FRAME_DIM * history_length, dtype=np.int64)
    native_block_offset = 0
    for term_dim, frame_offset in TERM_LAYOUT:
        for frame in range(history_length):        # target frame 0 = newest
            native_frame = history_length - 1 - frame
            for d in range(term_dim):
                target_index = frame * FRAME_DIM + frame_offset + d
                native_index = native_block_offset + native_frame * term_dim + d
                p[target_index] = native_index
        native_block_offset += term_dim * history_length
    return p


class BCPolicy(torch.nn.Module):
    def __init__(self, state: dict[str, torch.Tensor]) -> None:
        super().__init__()
        self.mlp = torch.nn.Sequential(
            torch.nn.Linear(FRAME_DIM * HISTORY, 512), torch.nn.ELU(),
            torch.nn.Linear(512, 256), torch.nn.ELU(),
            torch.nn.Linear(256, 128), torch.nn.ELU(),
            torch.nn.Linear(128, 16),
        )
        # native -> deployment permutation on the first layer columns
        perm = torch.from_numpy(build_permutation())
        weight = state["mlp.0.weight"].clone()
        state = dict(state)
        state["mlp.0.weight"] = weight[:, perm].contiguous()
        self.mlp.load_state_dict({k.replace("mlp.", ""): v for k, v in state.items()})

    def forward(self, obs: torch.Tensor) -> torch.Tensor:
        return self.mlp(obs)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bc", type=Path, required=True)
    ap.add_argument("--name", default="comp_bc_v1")
    ap.add_argument("--base-config", type=Path,
                    default=POLICY_ROOT / "obstacle/config.yaml")
    args = ap.parse_args()
    bc = torch.load(args.bc, map_location="cpu", weights_only=False)
    actor = {k: v for k, v in bc["actor_state_dict"].items() if k.startswith("mlp.")}
    policy = BCPolicy(actor).eval()
    out_dir = POLICY_ROOT / args.name
    out_dir.mkdir(parents=True, exist_ok=True)
    scripted = torch.jit.script(policy)
    scripted.save(str(out_dir / "policy.pt"))
    # Deployment config: official blackW contract (57 x 6 history, mirrored wheel
    # action scale on the right legs, kp/kd and torque limits).
    cfg = yaml.safe_load(args.base_config.read_text(encoding="utf-8"))
    key = next(iter(cfg))
    entry = cfg[key]
    entry["model_name"] = "policy.pt"
    entry["model_path"] = f"policy/blackW/{args.name}/policy.pt"
    yaml.safe_dump({f"blackW/{args.name}": entry},
                   (out_dir / "config.yaml").open("w", encoding="utf-8"))
    # quick shape check
    with torch.no_grad():
        out = scripted(torch.zeros(1, FRAME_DIM * HISTORY))
    # Self-contained drop-in (audit F3): manifest binds policy.pt to config.yaml.
    import hashlib, json
    def _sha(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    manifest = {
        "policy_name": args.name,
        "source_bc": str(args.bc),
        "policy_sha256": _sha(out_dir / "policy.pt"),
        "config_sha256": _sha(out_dir / "config.yaml"),
        "model_name": "policy.pt",
        "layout": "frame-major newest->oldest",
        "history_length": HISTORY,
        "action_scale": [0.25, 0.25, 0.25, 10.0, 0.25, 0.25, 0.25, -10.0,
                         0.25, 0.25, 0.25, 10.0, 0.25, 0.25, 0.25, -10.0],
        "deployment_note": "check with @20261024_blackw/scripts/import_blackw_policy.py --check",
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"exported -> {out_dir/'policy.pt'} forward={tuple(out.shape)} "
          f"config={out_dir/'config.yaml'} manifest={out_dir/'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
