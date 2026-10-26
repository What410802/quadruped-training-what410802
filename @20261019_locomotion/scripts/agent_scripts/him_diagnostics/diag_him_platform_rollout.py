"""Inspect one HIM platform rollout: root x/z, progress, terminations."""
from __future__ import annotations

import argparse
from dataclasses import asdict

import torch

from mjlab.envs import ManagerBasedRlEnv
from mjlab.rl import RslRlVecEnvWrapper
from mjlab.tasks.registry import load_env_cfg, load_rl_cfg, load_runner_cls


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", default="blackw-platform-micro-him")
    ap.add_argument("--checkpoint", required=True)
    args = ap.parse_args()
    env_cfg = load_env_cfg(args.task, play=True)
    env_cfg.scene.num_envs = 1
    if env_cfg.scene.terrain is not None:
        env_cfg.scene.terrain.max_init_terrain_level = 0
    env = ManagerBasedRlEnv(cfg=env_cfg, device="cuda:0", render_mode=None)
    vec = RslRlVecEnvWrapper(env, clip_actions=load_rl_cfg(args.task).clip_actions)
    agent_cfg = load_rl_cfg(args.task)
    runner_cls = load_runner_cls(args.task)
    runner = runner_cls(vec, asdict(agent_cfg), device="cuda:0")
    runner.load(args.checkpoint, load_cfg={"actor": True}, strict=True, map_location="cuda:0")
    policy = runner.get_inference_policy(device="cuda:0")
    obs, _ = vec.reset()
    max_z = -99.0
    with torch.no_grad():
        for step in range(300):
            obs, reward, dones, _ = vec.step(policy(obs))
            robot = env.scene["robot"]
            p = robot.data.root_link_pos_w[0].detach().cpu().numpy()
            z = float(p[2])
            max_z = max(max_z, z)
            if step % 20 == 0 or (z > 0.70):
                print(f"step={step:3d} x={p[0]:.3f} y={p[1]:.3f} z={z:.3f} "
                      f"max_z={max_z:.3f} reward={float(reward[0]):.2f} done={bool(dones[0])}")
            if bool(dones[0]):
                print("  terminations:", {k: float(v[0]) for k, v in env.termination_manager.compute().items()})
                obs, _ = vec.reset()
    print("final max_root_z", max_z)


if __name__ == "__main__":
    main()
