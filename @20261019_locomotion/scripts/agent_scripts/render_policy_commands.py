"""Render a policy through a fixed command suite with a tracking offscreen camera.

Run on the training-machine venv (mjlab + alldog_mjlab):

    cd ~/rc_work/nwwolf_mjlab_training_release
    MUJOCO_GL=egl .venv/bin/python /path/to/render_policy_commands.py \
        --task black-flat --checkpoint logs/.../model_2498.pt \
        --out ~/rc_work/videos/flat_ft_flat_commands.mp4

This is an investigation/diagnostic script; it is not part of the training loop.
The command suite covers the manual-mode needs: stand, forward slow/nominal/fast,
backward, lateral, yaw and a combined command.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import imageio.v3 as iio
import numpy as np
import torch

import alldog_mjlab.tasks  # noqa: F401
import mjlab.tasks  # noqa: F401
from mjlab.viewer.native.visualizer import MujocoNativeDebugVisualizer
from mjlab.envs import ManagerBasedRlEnv
from mjlab.rl import MjlabOnPolicyRunner, RslRlVecEnvWrapper
from mjlab.tasks.registry import load_env_cfg, load_rl_cfg, load_runner_cls
from mjlab.viewer import ViewerConfig

SEGMENTS = [
    ("stand", (0.0, 0.0, 0.0), 2.0),
    ("fwd-slow", (0.3, 0.0, 0.0), 2.0),
    ("fwd-nominal", (0.8, 0.0, 0.0), 3.0),
    ("fwd-fast", (1.5, 0.0, 0.0), 3.0),
    ("bwd", (-0.5, 0.0, 0.0), 2.0),
    ("lat-pos", (0.0, 0.5, 0.0), 2.0),
    ("yaw-pos", (0.0, 0.0, 0.5), 2.0),
    ("arc-left", (0.5, 0.0, 0.35), 4.0),
    ("arc-right", (0.5, 0.0, -0.35), 4.0),
    ("combined", (0.8, 0.3, 0.4), 3.0),
]


def _stagger_command_arrows() -> None:
    """Offset command/actual arrows vertically so they do not overlap in video."""
    orig_add_arrow = MujocoNativeDebugVisualizer.add_arrow

    def patched_add_arrow(self, start, end, color, width=0.015, label=None):
        start = np.asarray(start, dtype=np.float64).copy()
        end = np.asarray(end, dtype=np.float64).copy()
        rgb = tuple(float(c) for c in color[:3])
        if rgb == (0.2, 0.2, 0.6):
            dz = 0.18
        elif rgb == (0.2, 0.6, 0.2):
            dz = 0.26
        elif rgb == (0.0, 0.6, 1.0):
            dz = 0.08
        elif rgb == (0.0, 1.0, 0.4):
            dz = 0.16
        else:
            dz = 0.0
        if dz:
            start[2] += dz
            end[2] += dz
        return orig_add_arrow(self, start, end, color, width=width, label=label)

    MujocoNativeDebugVisualizer.add_arrow = patched_add_arrow


def _clean_update_visualizers(self, visualizer) -> None:
    """Draw command/reward overlays, but skip sensor debug point clouds."""
    for mod in self.manager_visualizers.values():
        mod.debug_vis(visualizer)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", default="black-flat")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--fps", type=int, default=50)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--warmup", type=float, default=1.0)
    parser.add_argument("--camera-distance", type=float, default=2.2)
    parser.add_argument("--camera-elevation", type=float, default=-20.0)
    parser.add_argument("--camera-azimuth", type=float, default=135.0)
    args = parser.parse_args()

    torch.set_grad_enabled(False)
    cfg = load_env_cfg(args.task, play=True)
    cfg.scene.num_envs = 1
    cfg.viewer.width = args.width
    cfg.viewer.height = args.height
    cfg.viewer.origin_type = ViewerConfig.OriginType.ASSET_BODY
    cfg.viewer.entity_name = "robot"
    cfg.viewer.body_name = "trunk"
    cfg.viewer.distance = args.camera_distance
    cfg.viewer.elevation = args.camera_elevation
    cfg.viewer.azimuth = args.camera_azimuth
    cfg.viewer.max_extra_envs = 0
    cfg.viewer.site_group = (0, 0, 0, 0, 0, 0)
    cfg.viewer.geom_group = (1, 1, 1, 1, 1, 1)
    # The training scene's raycast/foot sensor debug markers are useful in an
    # interactive viewer but dominate a policy video.
    ManagerBasedRlEnv.update_visualizers = _clean_update_visualizers
    _stagger_command_arrows()
    env = ManagerBasedRlEnv(cfg=cfg, device=args.device, render_mode="rgb_array")
    agent_cfg = load_rl_cfg(args.task)
    env = RslRlVecEnvWrapper(env, clip_actions=agent_cfg.clip_actions)
    runner = (load_runner_cls(args.task) or MjlabOnPolicyRunner)(env, asdict(agent_cfg), device=args.device)
    runner.load(args.checkpoint, load_cfg={"actor": True}, strict=True, map_location=args.device)
    policy = runner.get_inference_policy(device=args.device)
    term = env.unwrapped.command_manager.get_term("twist")
    term.is_standing_env[:] = False

    obs, _ = env.reset()
    term.is_standing_env[:] = False
    for _ in range(int(args.warmup / 0.02)):
        term.is_standing_env[:] = False
        term.command[:] = 0.0
        obs, *_ = env.step(policy(obs))

    frames: list[np.ndarray] = []
    metadata = []
    for name, cmd, seconds in SEGMENTS:
        term.is_standing_env[:] = False
        term.command[:] = torch.tensor(cmd, device=env.unwrapped.device, dtype=torch.float32)
        steps = int(round(seconds / 0.02))
        for _ in range(steps):
            obs, *_ = env.step(policy(obs))
            frame = env.unwrapped.render()
            if frame is None:
                raise RuntimeError("env.render() returned None")
            frames.append(np.asarray(frame))
        metadata.append({"segment": name, "cmd": list(cmd), "seconds": seconds, "steps": steps})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    iio.imwrite(str(args.out), np.stack(frames), fps=args.fps, plugin="FFMPEG")
    meta_path = args.out.with_suffix(".json")
    meta_path.write_text(json.dumps({
        "task": args.task,
        "checkpoint": str(args.checkpoint),
        "fps": args.fps,
        "frames": len(frames),
        "segments": metadata,
    }, ensure_ascii=False, indent=2) + "\n")
    print(f"WROTE {args.out} frames={len(frames)} meta={meta_path}")
    env.close()


if __name__ == "__main__":
    main()
