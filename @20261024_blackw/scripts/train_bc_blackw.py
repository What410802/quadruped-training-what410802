#!/usr/bin/env python3
"""Behaviour-clone the official blackW policies into the MjLab PPO actor MLP.

Reads the ``blackw_bc_*.npz`` records produced by ``collect_bc_blackw.py`` and
trains the exact actor architecture used by the MjLab blackW PPO task
(MLP 342 -> 512 -> 256 -> 128 -> 16, ELU) to predict the official policies' raw
actions from the native term-major 6-frame history (oldest -> newest), i.e. the
layout the training environment feeds the actor.  The exported deployment policy
is produced by re-permuting this layout (``export_history_policy.py``).

Usage (from MyMonoRepo.d):
  pixi run python @20261024_blackw/scripts/train_bc_blackw.py \
      --data prep.d/bc_data/blackw_bc_v1.npz --out prep.d/bc_data/bc_actor_v1.pt
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

TERM_DIMS = (3, 3, 3, 16, 16, 16)  # command, ang_vel, gravity, qpos, qvel, actions
FRAME_DIM = sum(TERM_DIMS)          # 57
HISTORY = 6


def build_native_history(obs: np.ndarray, episode: np.ndarray) -> np.ndarray:
    """(N,57) single frames -> (N,342) native term-major, oldest -> newest."""
    n = len(obs)
    out = np.zeros((n, FRAME_DIM * HISTORY), dtype=np.float32)
    term_offsets = np.cumsum((0,) + TERM_DIMS)  # boundaries in a 57 frame
    for ep in np.unique(episode):
        idx = np.where(episode == ep)[0]
        if len(idx) == 0:
            continue
        frames = np.zeros((len(idx), HISTORY, FRAME_DIM), dtype=np.float32)
        # CircularBuffer semantics: the first appended frame backfills all slots.
        frames[:] = obs[idx[0]][None, None, :]
        for t, row in enumerate(idx):
            frames[t, :-1] = frames[t - 1, 1:] if t > 0 else obs[row][None, :].repeat(HISTORY - 1, 0)
            frames[t, -1] = obs[row]
        # MjLab native history flatten: term-major across observation terms, and
        # frame-major inside a term (oldest -> newest).  See
        # mjlab/managers/observation_manager.py: compute_group() -> circular
        # buffer.buffer.reshape(num_envs, -1).  This is also the layout
        # export_history_policy.py assumes when permuting to deployment order.
        cols = []
        for k, dim in enumerate(TERM_DIMS):
            lo, hi = term_offsets[k], term_offsets[k + 1]
            block = frames[:, :, lo:hi]                 # (T, HISTORY, dim)
            cols.append(block.reshape(len(idx), dim * HISTORY))
        out[idx] = np.concatenate(cols, axis=1)
    return out


def build_mlp() -> nn.Sequential:
    return nn.Sequential(
        nn.Linear(FRAME_DIM * HISTORY, 512), nn.ELU(),
        nn.Linear(512, 256), nn.ELU(),
        nn.Linear(256, 128), nn.ELU(),
        nn.Linear(128, 16),
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--batch", type=int, default=4096)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--val-frac", type=float, default=0.1)
    ap.add_argument("--device", default="cpu")
    args = ap.parse_args()

    d = np.load(args.data, allow_pickle=True)
    obs, act, episode, weight = d["obs"], d["act"], d["episode"], d["weight"]
    meta = json.loads(str(d["meta"]))
    print(f"loaded {args.data}: samples={len(obs)} episodes={len(np.unique(episode))}")
    x_np = build_native_history(obs, episode)
    x = torch.from_numpy(x_np)
    y = torch.from_numpy(act.astype(np.float32))
    w = torch.from_numpy(weight.astype(np.float32))

    # split by episode to avoid leakage between adjacent frames
    eps = np.unique(episode)
    rng = np.random.default_rng(0)
    rng.shuffle(eps)
    n_val = max(1, int(len(eps) * args.val_frac))
    val_eps = set(eps[:n_val].tolist())
    val_mask = np.isin(episode, list(val_eps))
    tr = torch.from_numpy(~val_mask)
    va = torch.from_numpy(val_mask)
    print(f"train={int(tr.sum())} val={int(va.sum())}")

    model = build_mlp().to(args.device)
    opt = torch.optim.Adam(model.parameters(), lr=args.lr)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs)
    loss_fn = nn.HuberLoss(delta=1.0, reduction="none")

    best_state = {k: v.clone() for k, v in model.state_dict().items()}
    best_val = float("inf")
    for epoch in range(args.epochs):
        model.train()
        idx = torch.where(tr)[0]
        perm = idx[torch.randperm(len(idx))]
        total, count = 0.0, 0
        for i in range(0, len(perm), args.batch):
            b = perm[i:i + args.batch]
            pred = model(x[b].to(args.device))
            loss = (loss_fn(pred, y[b].to(args.device)) * w[b].to(args.device)[:, None]).mean()
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            total += float(loss) * len(b)
            count += len(b)
        sched.step()
        model.eval()
        with torch.no_grad():
            vmask = torch.where(va)[0]
            preds = []
            for i in range(0, len(vmask), args.batch):
                b = vmask[i:i + args.batch]
                preds.append(model(x[b].to(args.device)).cpu())
            pred = torch.cat(preds)
            val = float((loss_fn(pred, y[vmask]) * w[vmask][:, None]).mean())
        if val < best_val:
            best_val = val
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
        print(f"epoch {epoch:03d} train={total / max(count, 1):.5f} val={val:.5f} "
              f"best={best_val:.5f}")
    model.load_state_dict(best_state)
    payload = {
        "mlp.0.weight": model[0].weight.detach().cpu(),
        "mlp.0.bias": model[0].bias.detach().cpu(),
        "mlp.2.weight": model[2].weight.detach().cpu(),
        "mlp.2.bias": model[2].bias.detach().cpu(),
        "mlp.4.weight": model[4].weight.detach().cpu(),
        "mlp.4.bias": model[4].bias.detach().cpu(),
        "mlp.6.weight": model[6].weight.detach().cpu(),
        "mlp.6.bias": model[6].bias.detach().cpu(),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"actor_state_dict": payload, "val_loss": best_val,
                "data": str(args.data), "epochs": args.epochs}, args.out)
    print(f"saved {args.out} (best val {best_val:.5f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
