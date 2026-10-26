from __future__ import annotations

import os
from dataclasses import asdict

import torch

from mjlab.envs import ManagerBasedRlEnv
from mjlab.rl import RslRlVecEnvWrapper
from mjlab.tasks.registry import load_env_cfg, load_rl_cfg, load_runner_cls


def main() -> None:
    os.environ.setdefault("BLACKW_OFFICIAL_WARMSTART", "/tmp/official_blackw_obstacle.pt")
    task = "blackw-platform-micro-him"
    env_cfg = load_env_cfg(task, play=True)
    env_cfg.scene.num_envs = 1
    if env_cfg.scene.terrain:
        env_cfg.scene.terrain.max_init_terrain_level = 0
    env = ManagerBasedRlEnv(cfg=env_cfg, device="cuda:0", render_mode=None)
    vec = RslRlVecEnvWrapper(env, clip_actions=load_rl_cfg(task).clip_actions)
    runner_cls = load_runner_cls(task)
    runner = runner_cls(vec, asdict(load_rl_cfg(task)), device="cuda:0")
    actor = runner.alg.actor
    from alldog_mjlab.algorithms.him.spec import canonical_history

    obs, _ = vec.reset()
    history = obs["actor"]
    can = canonical_history(history)
    with torch.no_grad():
        ours = actor.as_jit()(can)
        official = torch.jit.load("/tmp/official_blackw_obstacle.pt", map_location="cuda:0")
        # Official obstacle policy contract: flattened canonical history [B,342] -> mean action.
        # Try direct input; if it expects something else, report shape/error.
        try:
            ref = official(can)
        except Exception as exc:  # noqa: BLE001
            print("official call failed:", type(exc).__name__, exc)
            return
    print("history", tuple(history.shape), "canonical", tuple(can.shape))
    print("ours", ours[0, :8].detach().cpu().numpy())
    print("ref ", ref[0, :8].detach().cpu().numpy())
    print("max_abs_diff", float((ours - ref).abs().max()))
    print("shapes", tuple(ours.shape), tuple(ref.shape))


if __name__ == "__main__":
    main()
