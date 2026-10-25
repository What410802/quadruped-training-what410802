#!/usr/bin/env python3
"""Merge behaviour-cloned actor weights into a converted blackW PPO checkpoint.

Keeps the (already action-convention-converted) critic, critic observation
normaliser and iteration counter from an existing checkpoint, and replaces the
actor MLP with the behaviour-cloned weights, so the MjLab PPO runner can resume
from it.

Usage (from MyMonoRepo.d):
  pixi run python @20261024_blackw/scripts/make_bc_checkpoint.py \
      --base prep.d/bc_data/comp_high600_mirror.pt \
      --bc prep.d/bc_data/bc_actor_v1.pt \
      --out prep.d/bc_data/model_600_bc_v1.pt --std 0.8
"""
from __future__ import annotations

import argparse
from pathlib import Path

import torch


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--bc", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--std", type=float, default=0.8, help="initial Gaussian std")
    args = ap.parse_args()

    base = torch.load(args.base, map_location="cpu", weights_only=False)
    bc = torch.load(args.bc, map_location="cpu", weights_only=False)
    bc_actor = dict(bc["actor_state_dict"])
    base_actor = dict(base["actor_state_dict"])
    for key, value in bc_actor.items():
        if key not in base_actor:
            raise KeyError(f"BC actor key {key} not in base actor")
        if tuple(base_actor[key].shape) != tuple(value.shape):
            raise ValueError(f"shape mismatch for {key}: "
                             f"{tuple(base_actor[key].shape)} vs {tuple(value.shape)}")
        base_actor[key] = value.clone()
    base_actor["distribution.std_param"] = torch.full((16,), float(args.std))
    base["actor_state_dict"] = base_actor
    base["bc_source"] = str(args.bc)
    base["bc_val_loss"] = float(bc.get("val_loss", -1.0))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    torch.save(base, args.out)
    print(f"saved {args.out}: base iter={base.get('iter')} "
          f"bc_val_loss={base['bc_val_loss']:.5f} std={args.std}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
