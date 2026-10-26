from __future__ import annotations

import os
from dataclasses import asdict

import torch

from mjlab.envs import ManagerBasedRlEnv
from mjlab.rl import RslRlVecEnvWrapper
from mjlab.tasks.registry import load_env_cfg, load_rl_cfg, load_runner_cls


def main() -> None:
    task = "blackw-platform-micro-him"
    os.environ["BLACKW_OFFICIAL_WARMSTART"] = "/tmp/official_blackw_obstacle.pt"
    env_cfg = load_env_cfg(task, play=True)
    env_cfg.scene.num_envs = 1
    if env_cfg.scene.terrain:
        env_cfg.scene.terrain.max_init_terrain_level = 0
    env = ManagerBasedRlEnv(cfg=env_cfg, device="cuda:0", render_mode=None)
    vec = RslRlVecEnvWrapper(env, clip_actions=load_rl_cfg(task).clip_actions)
    runner_cls = load_runner_cls(task)
    runner = runner_cls(vec, asdict(load_rl_cfg(task)), device="cuda:0")
    policy = runner.get_inference_policy(device="cuda:0")
    obs, _ = vec.reset()
    max_z = -99.0
    with torch.no_grad():
        for step in range(300):
            obs, reward, dones, _ = vec.step(policy(obs))
            robot = env.scene["robot"]
            p = robot.data.root_link_pos_w[0].detach().cpu().numpy()
            z = float(p[2]); max_z = max(max_z, z)
            if step % 20 == 0:
                print(f"step={step:3d} x={p[0]:.3f} y={p[1]:.3f} z={z:.3f} max_z={max_z:.3f}")
    print("final max_root_z", max_z)


if __name__ == "__main__":
    main()
