"""Diagnostic: deterministic rollout of a PPO actor inside the training env.

Prints per-step traces so a train-vs-judge mismatch can be localized (where does
the policy stall / which success sub-condition fails).
"""
from __future__ import annotations

import argparse
from dataclasses import asdict

import torch

from mjlab.envs import ManagerBasedRlEnv
from mjlab.rl import MjlabOnPolicyRunner, RslRlVecEnvWrapper
from mjlab.tasks.registry import load_env_cfg, load_rl_cfg
from mjlab.utils.torch import configure_torch_backends


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", default="blackw-slope-exact")
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--num-envs", type=int, default=8)
    ap.add_argument("--steps", type=int, default=900)
    ap.add_argument("--command", type=float, default=0.3)
    args = ap.parse_args()
    configure_torch_backends()
    env_cfg = load_env_cfg(args.task, play=False)
    env_cfg.scene.num_envs = args.num_envs
    if env_cfg.scene.terrain is not None:
        env_cfg.scene.terrain.max_init_terrain_level = 0
    env = ManagerBasedRlEnv(cfg=env_cfg, device="cuda:0", render_mode=None)
    env = RslRlVecEnvWrapper(env, clip_actions=None)
    runner = MjlabOnPolicyRunner(env, asdict(load_rl_cfg(args.task)), device="cuda:0")
    runner.load(args.checkpoint, load_cfg={"actor": True})
    policy = runner.get_inference_policy(device="cuda:0")
    obs = env.get_observations()
    unwrapped = env.unwrapped
    asset = unwrapped.scene["robot"]
    terrain = unwrapped.scene.terrain
    tm = unwrapped.termination_manager
    origins = terrain.env_origins
    print("spawn origins:", origins[:3].tolist())
    for step in range(args.steps):
        with torch.no_grad():
            actions = policy(obs)
        obs, _rew, dones, extras = env.step(actions)
        if step % 50 == 0 or bool(dones.any()):
            rx = (asset.data.root_link_pos_w[:, 0] - origins[:, 0]).detach().cpu()
            ry = (asset.data.root_link_pos_w[:, 1] - origins[:, 1]).detach().cpu()
            rz = asset.data.root_link_pos_w[:, 2].detach().cpu()
            lane = tm.get_term("lane_deviation").cpu()
            succ = tm.get_term("part2_success").cpu()
            print(f"step {step:4d} x={rx[:4].tolist()} y={ry[:4].tolist()} z={rz[:4].tolist()} "
                  f"lane={lane.int().tolist()} succ={succ.int().tolist()} dones={dones.int().tolist()}")
        if bool(dones.all()):
            break
    env.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
