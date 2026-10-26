"""Guarded PPO variant for fine-tuning a distilled (BC) blackW policy.

The plain PPO update drifts a behaviour-cloned actor far enough to lose the
previously solved Part 2 tiers (report: 750 -> 10-50 after 100-200 iterations
with lr 1e-4).  This subclass keeps the actor inside a trust region around its
initial (BC) weights:

    theta <- theta_base + lam * (theta - theta_base)      (after every update step)

with ``lam`` < 1 (default 0.9) applied to every optimizer step, plus optional
per-parameter freezing.  The trust region is a proximal anchor to the base
policy (similar in spirit to KL-anchored fine-tuning, but in weight space, so it
needs no extra forward pass / reference network).

Environment variables:
    BLACKW_GUARD_BLEND       lam, 0 = frozen at base, 1 = no anchoring (default 0.9).
                             NOTE: larger lam means MORE plasticity (it keeps a larger
                             fraction of the accumulated drift per optimizer step).
    BLACKW_GUARD_MAX_DRIFT   per-parameter L2 trust radius (default 0.0 = off)
    BLACKW_GUARD_FREEZE      comma-separated parameter-name substrings to freeze
    BLACKW_GUARD_LOG         "1" prints actor drift each iteration
    BLACKW_GUARD_BASE_CKPT   optional .pt checkpoint whose actor_state_dict becomes the
                             trust-region centre (e.g. the BC v5 checkpoint).  Unset =
                             the weights loaded with this run are the centre.
"""

from __future__ import annotations

import hashlib
import os

import torch
from rsl_rl.algorithms import PPO


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


class GuardedPPO(PPO):
    """PPO with a weight-space trust region around the loaded base actor."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._guard_blend = _env_float("BLACKW_GUARD_BLEND", 0.9)
        self._guard_max_drift = _env_float("BLACKW_GUARD_MAX_DRIFT", 0.0)
        self._guard_freeze = tuple(
            part.strip() for part in os.environ.get("BLACKW_GUARD_FREEZE", "").split(",")
            if part.strip())
        self._guard_log = os.environ.get("BLACKW_GUARD_LOG", "0") in ("1", "true", "yes")
        self._guard_base: dict[str, torch.Tensor] | None = None
        self._guard_drift = float("nan")
        self.optimizer.register_step_post_hook(self._guard_after_step)

    # -- rollout vs update -------------------------------------------------
    def update(self):  # type: ignore[override]
        if self._guard_base is None:
            self._capture_guard_base()
        out = super().update()
        if self._guard_log:
            print(f"[guarded-ppo] actor_drift={self._guard_drift:.3e} "
                  f"blend={self._guard_blend}", flush=True)
        return out

    def set_base_actor(self) -> None:
        """Re-snapshot the guard centre: current actor, or BLACKW_GUARD_BASE_CKPT."""
        self._guard_base = None

    def _capture_guard_base(self) -> None:
        base_ckpt = os.environ.get("BLACKW_GUARD_BASE_CKPT", "").strip()
        if base_ckpt:
            self._guard_base = self._load_base_checkpoint(base_ckpt)
            print(f"[guarded-ppo] guard base = checkpoint {base_ckpt} "
                  f"sha256={_sha256(base_ckpt)[:16]}", flush=True)
        else:
            # First update() happens after the checkpoint has been loaded, so the
            # current actor weights ARE the base policy.
            self._guard_base = {
                name: param.detach().clone()
                for name, param in self._raw_actor.named_parameters()
                if param.requires_grad
            }
            print("[guarded-ppo] guard base = weights loaded with this run (self)",
                  flush=True)
        if self._guard_freeze:
            for name, param in self._raw_actor.named_parameters():
                if any(token in name for token in self._guard_freeze):
                    param.requires_grad_(False)

    def _load_base_checkpoint(self, path: str) -> dict[str, torch.Tensor]:
        """Load ``actor_state_dict`` from a checkpoint and map it onto the actor."""
        payload = torch.load(path, map_location="cpu", weights_only=False)
        state = payload.get("actor_state_dict", payload)
        base: dict[str, torch.Tensor] = {}
        missing: list[str] = []
        for name, param in self._raw_actor.named_parameters():
            if not param.requires_grad:
                continue
            value = state.get(name)
            if value is None:
                value = state.get(f"actor.{name}")
            if value is None:
                missing.append(name)
                continue
            if tuple(value.shape) != tuple(param.shape):
                raise ValueError(
                    f"guarded base checkpoint {path}: shape mismatch for {name}: "
                    f"{tuple(value.shape)} vs actor {tuple(param.shape)}")
            base[name] = value.detach().clone().to(param.device)
        if missing:
            raise KeyError(
                f"guarded base checkpoint {path}: missing actor parameters {missing}")
        return base

    # -- weight-space anchoring -------------------------------------------
    @torch.no_grad()
    def _guard_after_step(self, *args, **kwargs) -> None:
        if self._guard_base is None:
            return
        drift_sq = 0.0
        count = 0
        for name, param in self._raw_actor.named_parameters():
            base = self._guard_base.get(name)
            if base is None or not param.requires_grad:
                continue
            delta = param - base
            if self._guard_max_drift > 0.0:
                norm = delta.norm()
                if norm > self._guard_max_drift:
                    delta = delta * (self._guard_max_drift / (norm + 1e-12))
            param.copy_(base + self._guard_blend * delta)
            d = (param - base).float()
            drift_sq += float((d * d).sum())
            count += d.numel()
        if count:
            self._guard_drift = (drift_sq / count) ** 0.5
