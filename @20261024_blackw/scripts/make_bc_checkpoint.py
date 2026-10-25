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
    ap.add_argument("--reset-trainer", action="store_true",
                    help="reset critic weights, optimizer momentum, iteration and env "
                         "curriculum state (required for a clean warm start)")
    ap.add_argument("--lr", type=float, default=5e-5,
                    help="optimizer lr stored in the reset checkpoint")
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
    if args.reset_trainer:
        import torch.nn as nn
        critic = dict(base["critic_state_dict"])
        # Re-initialise the critic MLP with the same default ``nn.Linear`` init a
        # fresh rsl_rl run would use (the base critic was trained on a different
        # task/reward scale, so its value estimates are noise after a warm start).
        for key, value in list(critic.items()):
            if not key.startswith("mlp.") or not key.endswith(".weight"):
                continue
            layer = nn.Linear(value.shape[1], value.shape[0])
            critic[key] = layer.weight.detach().clone()
            bias_key = key[: -len("weight")] + "bias"
            if bias_key in critic:
                critic[bias_key] = layer.bias.detach().clone()
        base["critic_state_dict"] = critic
        groups = []
        for group in base["optimizer_state_dict"]["param_groups"]:
            group = dict(group)
            group["lr"] = float(args.lr)
            groups.append(group)
        base["optimizer_state_dict"] = {"state": {}, "param_groups": groups}
        base["iter"] = 0
        base["infos"] = {}
    base["bc_source"] = str(args.bc)
    base["bc_val_loss"] = float(bc.get("val_loss", -1.0))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    torch.save(base, args.out)
    print(f"saved {args.out}: base iter={base.get('iter')} "
          f"bc_val_loss={base['bc_val_loss']:.5f} std={args.std}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
