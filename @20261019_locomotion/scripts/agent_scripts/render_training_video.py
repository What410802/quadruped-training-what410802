"""Clean diagnostic video / scene overview for the training stack.

Runs on the training-machine venv (mjlab + alldog_mjlab installed):

    cd ~/rc_work/nwwolf_mjlab_training_release
    .venv/bin/python <this script> play --task black-flat \
        --checkpoint logs/.../model_1999.pt --video-length 200

Compared with the built-in `play --video`, this wrapper:
  - tracks the robot with the offscreen camera (ASSET_BODY/trunk), and
  - hides the raycast/foot sensor debug markers (keeps command arrows).
It is intentionally kept out of the training repo for now; videos are diagnostics.

`overview` mode renders a static free-camera scene image (whole terrain view).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

import alldog_mjlab.tasks  # noqa: F401  (register black tasks)
import mjlab.tasks.registry as registry
from mjlab.envs import ManagerBasedRlEnv
from mjlab.scripts import play as play_mod
from mjlab.viewer import ViewerConfig
from mjlab.viewer.native.visualizer import MujocoNativeDebugVisualizer


def _make_env_cfg_patch(mode: str, geom_group: tuple[int, ...]):
    orig = registry.load_env_cfg

    def patched(task_id: str, play: bool = False):
        cfg = orig(task_id, play=play)
        cfg.viewer.site_group = (0, 0, 0, 0, 0, 0)  # hide sensor debug sites
        cfg.viewer.geom_group = geom_group  # training model: collision geoms live in group 3
        cfg.viewer.max_extra_envs = 0
        if mode == "overview":
            cfg.viewer.origin_type = ViewerConfig.OriginType.WORLD
            cfg.viewer.lookat = (0.0, 0.0, 0.3)
            cfg.viewer.distance = 9.0
            cfg.viewer.elevation = -65.0
            cfg.viewer.azimuth = 135.0
            cfg.viewer.height = 720
            cfg.viewer.width = 1280
        else:
            cfg.viewer.origin_type = ViewerConfig.OriginType.ASSET_BODY
            cfg.viewer.entity_name = "robot"
            cfg.viewer.body_name = "trunk"
            cfg.viewer.distance = 2.2
            cfg.viewer.elevation = -20.0
            cfg.viewer.azimuth = 135.0
        return cfg

    return patched


def _stagger_command_arrows() -> None:
    """Stagger command/actual velocity arrows vertically so they do not overlap.

    The task visualizer draws command/actual arrows at the same z offset; in video
    they overlap and only the last color is readable. This monkeypatch keeps the
    original colors/lengths and only raises/lowers the arrow start/end points.
    """
    orig_add_arrow = MujocoNativeDebugVisualizer.add_arrow

    def patched_add_arrow(self, start, end, color, width=0.015, label=None):
        start = np.asarray(start, dtype=np.float64).copy()
        end = np.asarray(end, dtype=np.float64).copy()
        rgb = tuple(float(c) for c in color[:3])
        # Task visualizer colors (mjlab/tasks/velocity/mdp/velocity_command.py)
        if rgb == (0.2, 0.2, 0.6):       # command linear (dark blue): higher
            dz = 0.18
        elif rgb == (0.2, 0.6, 0.2):     # command angular (dark green)
            dz = 0.26
        elif rgb == (0.0, 0.6, 1.0):     # actual linear (cyan): lower
            dz = 0.08
        elif rgb == (0.0, 1.0, 0.4):     # actual angular (light green)
            dz = 0.16
        else:
            dz = 0.0
        if dz:
            start[2] += dz
            end[2] += dz
        return orig_add_arrow(self, start, end, color, width=width, label=label)

    MujocoNativeDebugVisualizer.add_arrow = patched_add_arrow


def _clean_update_visualizers(self, visualizer) -> None:
    """Keep command arrows (target/actual velocity); skip sensor debug markers."""
    for mod in self.manager_visualizers.values():
        mod.debug_vis(visualizer)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("play", "overview"))
    parser.add_argument("--task", default="black-flat")
    parser.add_argument("--checkpoint", type=Path, default=None)
    parser.add_argument("--video-length", type=int, default=200)
    parser.add_argument("--video-height", type=int, default=480)
    parser.add_argument("--video-width", type=int, default=640)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--log-root", default="logs/rsl_rl")
    parser.add_argument("--geom-group", default="1,1,1,1,1,1")
    parser.add_argument("--num-envs", type=int, default=1)
    parser.add_argument("--stagger-arrows", default="true")
    args = parser.parse_args()

    geom_group = tuple(int(x) for x in args.geom_group.split(","))
    assert len(geom_group) == 6, geom_group
    patched = _make_env_cfg_patch(args.mode, geom_group)
    registry.load_env_cfg = patched
    play_mod.load_env_cfg = patched

    if args.mode == "play":
        if args.checkpoint is None:
            raise SystemExit("--checkpoint is required for play mode")
        ManagerBasedRlEnv.update_visualizers = _clean_update_visualizers
        if args.stagger_arrows.lower() == "true":
            _stagger_command_arrows()
        sys.argv = [
            "play",
            args.task,
            "--checkpoint-file",
            str(args.checkpoint),
            "--num-envs",
            "1",
            "--device",
            args.device,
            "--video",
            "True",
            "--video-length",
            str(args.video_length),
            "--video-height",
            str(args.video_height),
            "--video-width",
            str(args.video_width),
            "--viewer",
            "viser",
            "--log-root",
            args.log_root,
        ]
        play_mod.main()
        return

    # Overview: static global screenshot of the generated scene.
    cfg = patched(args.task, play=True)
    cfg.scene.num_envs = args.num_envs
    if args.mode == "overview":
        cfg.viewer.max_extra_envs = max(0, args.num_envs - 1)
    ManagerBasedRlEnv.update_visualizers = _clean_update_visualizers
    env = ManagerBasedRlEnv(cfg=cfg, device=args.device, render_mode="rgb_array")
    try:
        env.reset()
        # Frame all env origins: the free camera is created at __init__ from
        # ViewerConfig, so adjust the renderer's camera after reset.
        renderer = getattr(env, "_offline_renderer", None)
        origins = env.scene.env_origins.detach().cpu().numpy()
        center = origins.mean(axis=0)
        center[2] = 0.2
        if renderer is not None and getattr(renderer, "_cam", None) is not None:
            renderer._cam.lookat[:] = center
            span = float(np.ptp(origins[:, 0]) + np.ptp(origins[:, 1]))
            renderer._cam.distance = max(6.0, 0.6 * span + 4.0)
            renderer._cam.elevation = -60.0
            renderer._cam.azimuth = 135.0
        frame = env.render()
        if frame is None:
            raise RuntimeError("env.render() returned None")
        out = args.out or Path("overview.png")
        out.parent.mkdir(parents=True, exist_ok=True)
        import imageio.v3 as iio

        iio.imwrite(str(out), frame)
        print(f"OVERVIEW_SAVED {out} {frame.shape}")
    finally:
        env.close()


if __name__ == "__main__":
    main()
