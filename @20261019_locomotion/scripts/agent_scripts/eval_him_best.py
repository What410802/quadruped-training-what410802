#!/usr/bin/env python3
"""Zero-shot evaluation of the assignment HIMLoco ``best.pt`` on Part 1 / Part 2.

The assignment policy is *not* the same observation/action contract as the local
45-D single-frame mjlab actor:

- input is ``[B, 270]`` = 6 frames x 45, the newest frame first;
- the 45-D frame is commands / ang_vel / gravity / dof_pos / dof_vel / actions with
  the assignment's own scales (see ``config.yaml``);
- output is a 12-D unscaled action clipped to +/-100, then
  ``q_target = default_dof_pos + action_scale * action``; PD gains are ``rl_kp`` /
  ``rl_kd`` (40 / 1.2) and the torque envelope is ``torque_limits`` (33.5 N.m).

This script reuses the local Part 1 V2 judge runner and the Part 2 level runner by
swapping in a scene runner that keeps the 6-frame history and applies the assignment
clipping/gains.  Everything else (scene, judge, sampling cadence) is unchanged, so
the results are directly comparable with the flat-ft diagnostics.

Usage (from MyMonoRepo.d):

    pixi run python @20261019_locomotion/scripts/agent_scripts/eval_him_best.py --part all
    pixi run python @20261019_locomotion/scripts/agent_scripts/eval_him_best.py --part part1 --tasks slalom --tasks slope
    pixi run python @20261019_locomotion/scripts/agent_scripts/eval_him_best.py --part part2 --only high_platform --only trench

Outputs go to ``../prep.d/results/`` (outside the repo) plus a Markdown summary;
the JSON payloads keep the upstream judge schema and add the policy contract.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import mujoco
import numpy as np
import torch
import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
POLICY_DIR = REPO_ROOT / "@20261007_assignment/ws/src/rl_sar/policy/black"
BEST_PT = POLICY_DIR / "himloco/best.pt"
POLICY_CFG = POLICY_DIR / "himloco/config.yaml"

sys.path.insert(0, str(SCRIPT_DIR))

import run_part1_judged_rollout_v2 as p1mod  # noqa: E402
import run_part2_judged_eval as p2mod  # noqa: E402
from run_policy_scene import ScenePolicyRunner  # noqa: E402

WARMUP_S = 1.0


def file_hashes(path: Path) -> dict[str, str]:
    return {
        "md5": hashlib.md5(path.read_bytes()).hexdigest(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": str(path.stat().st_size),
    }


def load_cfg() -> dict:
    return yaml.safe_load(POLICY_CFG.read_text())["black/himloco"]


class VideoSink:
    """Render one policy run to an mp4 (CPU MuJoCo renderer + ffmpeg, no display)."""

    def __init__(self, path: Path, fps: int, width: int, height: int, every: int,
                 azimuth: float = 135.0) -> None:
        self.path = path
        self.fps = fps
        self.every = max(1, every)
        self.width = width
        self.height = height
        self.azimuth = azimuth
        self.frames_dir = path.parent / "frames" / path.stem
        self.frames_dir.mkdir(parents=True, exist_ok=True)
        self._renderer = None
        self._camera = None
        self._option = None
        self._counter = 0
        self._n = 0

    def _ensure(self, model) -> None:
        if self._renderer is not None:
            return
        self._renderer = mujoco.Renderer(model, height=self.height, width=self.width)
        self._camera = mujoco.MjvCamera()
        self._camera.distance = 2.4
        self._camera.elevation = -20.0
        self._camera.azimuth = self.azimuth
        self._option = mujoco.MjvOption()
        self._option.geomgroup[:] = 1

    def maybe_capture(self, model, data, base_x: float, base_y: float, base_z: float) -> None:
        self._counter += 1
        if (self._counter - 1) % self.every != 0:
            return
        self._ensure(model)
        self._camera.lookat[:] = (base_x, base_y, max(0.15, base_z - 0.15))
        self._renderer.update_scene(data, camera=self._camera, scene_option=self._option)
        frame = self._renderer.render()
        tmp = self.frames_dir / f"f{self._n:05d}.ppm"
        with tmp.open("wb") as fh:
            fh.write(f"P6\n{frame.shape[1]} {frame.shape[0]}\n255\n".encode())
            fh.write(frame.tobytes())
        self._n += 1

    def close(self) -> None:
        if self._renderer is None:
            return
        self._renderer.close()
        if self._n == 0:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
             "-framerate", str(self.fps), "-i", str(self.frames_dir / "f%05d.ppm"),
             "-pix_fmt", "yuv420p", str(self.path)],
            check=True,
        )
        for p in self.frames_dir.glob("*.ppm"):
            p.unlink()
        self.frames_dir.rmdir()
        try:
            self.frames_dir.parent.rmdir()
        except OSError:
            pass


class VideoConfig:
    """Process-wide video output settings (CLI-driven)."""

    def __init__(self, root: Path, fps: int, width: int, height: int, every: int) -> None:
        self.enabled = False
        self.root = root
        self.fps = fps
        self.width = width
        self.height = height
        self.every = every

    def sink(self, group: str, name: str) -> VideoSink | None:
        if not self.enabled:
            return None
        return VideoSink(self.root / group / f"{name}.mp4", self.fps, self.width,
                         self.height, self.every)


VIDEO = VideoConfig(Path("../prep.d/videos/him_best"), 25, 512, 384, 2)


class HimBestRunner(ScenePolicyRunner):
    """Single-env scene runner with the HIMLoco 6-frame observation contract."""

    def __init__(self, scene: str, policy_path: str, start: tuple[float, float, float, float]) -> None:
        super().__init__(scene, policy_path, start)
        cfg = load_cfg()
        self.cfg = cfg
        self.history_len = len(cfg["observations_history"])
        self.num_obs = int(cfg["num_observations"])
        self.obs_clip = float(cfg["clip_obs"])
        self.cmd_scale = np.array(cfg["commands_scale"], dtype=np.float64)
        self.ang_vel_scale = float(cfg["ang_vel_scale"])
        self.dof_pos_scale = float(cfg["dof_pos_scale"])
        self.dof_vel_scale = float(cfg["dof_vel_scale"])
        self.action_scale = np.array(cfg["action_scale"], dtype=np.float64)
        self.clip_lo = np.array(cfg["clip_actions_lower"], dtype=np.float64)
        self.clip_hi = np.array(cfg["clip_actions_upper"], dtype=np.float64)
        self.kp = np.array(cfg["rl_kp"], dtype=np.float64)
        self.kd = np.array(cfg["rl_kd"], dtype=np.float64)
        self.tau_max = float(cfg["torque_limits"][0])
        # The policy is evaluated under its own trained torque envelope, not the
        # local mjlab scene's 20 N.m ctrlrange (same choice as policy_reference.py).
        self.model.actuator_ctrlrange[:] = [-self.tau_max, self.tau_max]
        self.history = np.zeros((self.history_len, self.num_obs), dtype=np.float64)

    def obs(self, command: np.ndarray) -> np.ndarray:
        """Build one 45-D frame, push it into the history, return the 270-D input."""
        gyro = np.array(self.data.sensor("imu_ang_vel").data, dtype=np.float64)
        quat = np.array(self.data.qpos[3:7], dtype=np.float64)
        w, x, y, z = quat
        R = np.array([
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ])
        gravity = R.T @ np.array([0.0, 0.0, -1.0])
        q_rel = np.array(self.data.qpos[self.qpos_adr]) - self.q_default
        qvel = np.array(self.data.qvel[self.qvel_adr])
        frame = np.concatenate([
            command * self.cmd_scale,
            gyro * self.ang_vel_scale,
            gravity,
            q_rel * self.dof_pos_scale,
            qvel * self.dof_vel_scale,
            self.last_action,
        ])
        frame = np.clip(frame, -self.obs_clip, self.obs_clip)
        self.history = np.roll(self.history, 1, axis=0)
        self.history[0] = frame
        return self.history.reshape(-1)

    def policy_action(self, command: np.ndarray) -> np.ndarray:
        """One inference: history -> 12-D action clipped to the assignment bounds."""
        obs = torch.from_numpy(self.obs(command)).unsqueeze(0).to(torch.float32)
        with torch.no_grad():
            raw = self.policy(obs).numpy().reshape(-1).astype(np.float64)
        action = np.clip(raw, self.clip_lo, self.clip_hi)
        self.last_action[:] = action
        return action

    def drive(self, action: np.ndarray) -> None:
        """PD torque command for one policy step (4 x 5 ms physics substeps)."""
        q_target = self.q_default + self.action_scale * action
        q = np.array(self.data.qpos[self.qpos_adr])
        qd = np.array(self.data.qvel[self.qvel_adr])
        tau = np.clip(self.kp * (q_target - q) - self.kd * qd, -self.tau_max, self.tau_max)
        self.data.ctrl[self.motor_ids] = tau


class HimBestPart1Runner(p1mod.V2Runner):
    """V2 judge runner driven by the HIMLoco policy step."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._video: VideoSink | None = None

    def run_task(self, name: str, warmup_s: float) -> dict:
        self._video = VIDEO.sink("part1", name)
        try:
            return super().run_task(name, warmup_s)
        finally:
            if self._video is not None:
                self._video.close()
                self._video = None

    def _policy_step(self, command: np.ndarray) -> None:
        action = self.runner.policy_action(command)
        self.runner.drive(action)
        for _ in range(4):
            mujoco.mj_step(self.model, self.data)
            self._sample_judge()
        if self._video is not None:
            base = np.asarray(self.data.xpos[self.runner.trunk], dtype=float)
            self._video.maybe_capture(self.model, self.data, base[0], base[1], base[2])


class HimBestLevelRunner(p2mod.LevelRunner):
    """Part 2 level runner driven by the HIMLoco policy step."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._video: VideoSink | None = None

    def warmup(self, seconds: float = 0.5) -> None:
        for _ in range(int(WARMUP_S / 0.02)):
            self._policy_step(np.zeros(3), judge=None)

    def run_attempt(self, entry: dict, seconds: float | None = None) -> dict:
        key = f"{entry['category']}_{entry['level']}{entry['unit']}"
        self._video = VIDEO.sink("part2", key)
        try:
            return super().run_attempt(entry, seconds)
        finally:
            if self._video is not None:
                self._video.close()
                self._video = None

    def _policy_step(self, command: np.ndarray, judge) -> None:
        action = self.runner.policy_action(command)
        self.runner.drive(action)
        for _ in range(4):
            mujoco.mj_step(self.model, self.data)
            if judge is not None:
                self._sample(judge)
        if self._video is not None:
            base = np.asarray(self.data.xpos[self.runner.trunk], dtype=float)
            self._video.maybe_capture(self.model, self.data, base[0], base[1], base[2])


def contract_test(policy_path: Path) -> dict:
    """Verify the TorchScript input/output contract before touching the scenes."""
    policy = torch.jit.load(str(policy_path)).eval()
    torch.manual_seed(0)
    with torch.no_grad():
        single = policy(torch.randn(1, 270))
        batch = policy(torch.randn(3, 270))
    out = {
        "torchscript_load": "ok",
        "in_shape": [1, 270],
        "out_shape": list(single.shape),
        "batch3_out_shape": list(batch.shape),
        "out_abs_max_seed0": float(single.abs().max()),
        "out_dim": int(single.shape[-1]),
        "out_dim_is_12": int(single.shape[-1]) == 12,
        "deterministic": bool(torch.equal(policy(torch.zeros(1, 270)), policy(torch.zeros(1, 270)))),
    }
    if not out["out_dim_is_12"]:
        raise RuntimeError(f"unexpected output dim: {out['out_shape']}")
    return out


def annotate(payload_path: Path, contract: dict, extra: dict) -> None:
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload["policy_contract"] = contract
    payload["eval_contract"] = extra
    payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_summary(out_dir: Path, contract: dict, hashes: dict, part1: dict | None,
                  part2: dict | None, title_suffix: str = "", tag: str = "") -> Path:
    lines = [
        f"# HIMLoco `best.pt` zero-shot evaluation (Part 1 + Part 2){title_suffix}",
        "",
        f"- policy: `{BEST_PT}` ({hashes['bytes']} B, md5 `{hashes['md5']}`, sha256 `{hashes['sha256']}`)",
        f"- config: `{POLICY_CFG}`",
        f"- contract test: in `[1,270]` → out `{contract['out_shape']}`; batch 3 → `{contract['batch3_out_shape']}`; deterministic={contract['deterministic']}",
        "- gains/limits: rl_kp=40, rl_kd=1.2, torque 33.5 N.m, action_scale=0.25, obs clip ±100",
        "- these are **diagnostic** runs (G1 not frozen); do not use as official score",
        "",
    ]
    if part1 is not None:
        lines += [
            "## Part 1 (V2 judge)",
            "",
            "| task | status | score | reason | base | tilt_deg |",
            "|---|---|---:|---|---|---:|",
        ]
        per_task = {a["task"]: a for a in part1["attempts"]}
        for name in sorted(per_task):
            a = per_task[name]
            st = a["judge"]["states"][name]
            lines.append(f"| {name} | {st['status']} | {st['score']} | {st['reason']} | {a['base']} | {a['tilt_deg']} |")
        lines += ["", f"total_score={part1['total_score']} success={part1['success_count']}/{len(part1['attempts'])}", ""]
    if part2 is not None:
        lines += [
            "## Part 2 (V2 evaluator, 1 attempt per level)",
            "",
            "| category | level | success | reason | base | tilt_deg |",
            "|---|---:|---|---|---|---:|",
        ]
        for rec in part2["attempts"]:
            a = rec["attempts"][-1]
            j = a["judge"]
            status = j.get("status", "?")
            reason = j.get("reason", "")
            lines.append(
                f"| {rec['category']} | {rec['level']}{rec['unit']} | "
                f"{'SUCCESS' if rec['best_success'] else 'fail'} ({rec['success_count']}/{rec['attempt_count']}) | "
                f"{status}:{reason} | {a['base']} | {a['tilt_deg']} |"
            )
        lines += ["", f"diag_total_score={part2['total_score']}", ""]
    path = out_dir / f"him_best_eval_summary{tag}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_video_index(root: Path, part1: dict | None, part2: dict | None,
                      hashes: dict, extra: dict) -> Path:
    """Minimal index.html linking the rendered mp4s to the judge results."""
    rows_p1 = []
    if part1 is not None:
        per_task = {a["task"]: a for a in part1["attempts"]}
        for name in sorted(per_task):
            a = per_task[name]
            st = a["judge"]["states"][name]
            rows_p1.append(
                f'<tr><td>{name}</td><td>{st["status"]}</td><td>{st["reason"]}</td>'
                f'<td><a href="part1/{name}.mp4">part1/{name}.mp4</a></td></tr>'
            )
    rows_p2 = []
    if part2 is not None:
        for rec in part2["attempts"]:
            a = rec["attempts"][-1]
            j = a["judge"]
            key = f"{rec['category']}_{rec['level']}{rec['unit']}"
            rows_p2.append(
                f'<tr><td>{rec["category"]}</td><td>{rec["level"]}{rec["unit"]}</td>'
                f'<td>{"SUCCESS" if rec["best_success"] else "fail"}</td>'
                f'<td>{j.get("reason", "")}</td>'
                f'<td><a href="part2/{key}.mp4">part2/{key}.mp4</a></td></tr>'
            )
    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>HIMLoco best.pt zero-shot videos</title>
<style>body{{font-family:sans-serif;margin:24px}}table{{border-collapse:collapse;margin:12px 0}}
td,th{{border:1px solid #999;padding:4px 8px;font-size:13px}}th{{background:#eee}}</style></head><body>
<h2>HIMLoco best.pt zero-shot evaluation videos</h2>
<p>policy md5 <code>{hashes['md5']}</code>, sha256 <code>{hashes['sha256']}</code>,
variant <b>{extra['diagnostic_variant']}</b>; diagnostic only (G1 not frozen).</p>
<h3>Part 1 (V2 judge)</h3><table><tr><th>task</th><th>status</th><th>reason</th><th>video</th></tr>
{''.join(rows_p1)}</table>
<h3>Part 2 (V2 evaluator)</h3><table><tr><th>category</th><th>level</th><th>success</th><th>reason</th><th>video</th></tr>
{''.join(rows_p2)}</table>
<p>Rendered with the CPU MuJoCo renderer (512x384, 25 fps); camera follows the trunk.</p>
</body></html>
"""
    path = root / "index.html"
    path.write_text(html, encoding="utf-8")
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--policy", type=Path, default=BEST_PT)
    ap.add_argument("--part", choices=["part1", "part2", "all"], default="all")
    ap.add_argument("--out-dir", type=Path, default=Path("../prep.d/results"))
    ap.add_argument("--tasks", action="append", default=[], help="Part 1 task names (default: all)")
    ap.add_argument("--only", action="append", default=[], help="Part 2 category or category_level")
    ap.add_argument("--warmup", type=float, default=WARMUP_S, help="Part 1 warmup before the task [s]")
    ap.add_argument("--time-scale", type=float, default=1.0,
                    help="Part 1 diagnostic duration multiplier (for time-extended diagnostics only)")
    ap.add_argument("--p2-seconds", type=float, default=None,
                    help="Part 2 duration override [s] (for time-extended diagnostics only)")
    ap.add_argument("--tag", default="", help="suffix for output file names, e.g. _extended")
    ap.add_argument("--video", action="store_true", help="render one mp4 per task/level (CPU renderer)")
    ap.add_argument("--video-dir", type=Path, default=Path("../prep.d/videos/him_best"))
    ap.add_argument("--video-fps", type=int, default=25)
    ap.add_argument("--video-width", type=int, default=512)
    ap.add_argument("--video-height", type=int, default=384)
    ap.add_argument("--video-every", type=int, default=2,
                    help="render one frame every N policy steps (2 -> 25 fps at 50 Hz)")
    args = ap.parse_args()

    policy = args.policy
    if not policy.is_absolute():
        policy = (Path.cwd() / policy).resolve()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    VIDEO.enabled = args.video
    VIDEO.root = args.video_dir
    VIDEO.fps = args.video_fps
    VIDEO.width = args.video_width
    VIDEO.height = args.video_height
    VIDEO.every = args.video_every
    if args.video:
        VIDEO.root.mkdir(parents=True, exist_ok=True)
        print(f"[video] rendering to {VIDEO.root} ({VIDEO.width}x{VIDEO.height} @ 25 fps)")

    hashes = file_hashes(policy)
    contract = contract_test(policy)
    cfg = load_cfg()
    extra = {
        "warmup_s": args.warmup,
        "history_len": len(cfg["observations_history"]),
        "history_order": "newest_first",
        "action_scale": float(cfg["action_scale"][0]),
        "rl_kp": float(cfg["rl_kp"][0]),
        "rl_kd": float(cfg["rl_kd"][0]),
        "torque_limit": float(cfg["torque_limits"][0]),
        "obs_clip": float(cfg["clip_obs"]),
        "clips_actions": [float(cfg["clip_actions_lower"][0]), float(cfg["clip_actions_upper"][0])],
        "part1_time_scale": args.time_scale,
        "part2_seconds": args.p2_seconds,
        "diagnostic_variant": "time-extended" if (args.time_scale != 1.0 or args.p2_seconds) else "frozen-start",
    }
    print(f"policy {policy}")
    print(f"  {hashes}")
    print(f"  contract: {contract}")
    print(f"  eval contract: {extra}")

    part1 = part2 = None
    part1_json = args.out_dir / f"him_best_part1_v2{args.tag}.json"
    part2_json = args.out_dir / f"him_best_part2_v2{args.tag}.json"

    if args.part in ("part1", "all"):
        p1mod.ScenePolicyRunner = HimBestRunner
        p1mod.V2Runner = HimBestPart1Runner
        if args.time_scale != 1.0:
            p1mod.TASKS = {
                name: (xyz, yaw, cmd, seconds * args.time_scale, note)
                for name, (xyz, yaw, cmd, seconds, note) in p1mod.TASKS.items()
            }
        argv = [
            "run_part1_judged_rollout_v2.py",
            "--policy", str(policy),
            "--json", str(part1_json),
            "--warmup", str(args.warmup),
        ]
        for task in args.tasks:
            argv += ["--task", task]
        old_argv, sys.argv = sys.argv, argv
        try:
            p1mod.main()
        finally:
            sys.argv = old_argv
        annotate(part1_json, contract, extra)
        part1 = json.loads(part1_json.read_text(encoding="utf-8"))

    if args.part in ("part2", "all"):
        p2mod.ScenePolicyRunner = HimBestRunner
        p2mod.LevelRunner = HimBestLevelRunner
        argv = [
            "run_part2_judged_eval.py",
            "--policy", str(policy),
            "--json", str(part2_json),
        ]
        if args.p2_seconds is not None:
            argv += ["--seconds", str(args.p2_seconds)]
        for only in args.only:
            argv += ["--only", only]
        old_argv, sys.argv = sys.argv, argv
        try:
            p2mod.main()
        finally:
            sys.argv = old_argv
        annotate(part2_json, contract, extra)
        part2 = json.loads(part2_json.read_text(encoding="utf-8"))

    summary = write_summary(args.out_dir, contract, hashes, part1, part2,
                            "" if not args.tag else f" — {extra['diagnostic_variant']}",
                            tag=args.tag)
    print("summary:", summary)
    if args.video:
        index = write_video_index(VIDEO.root, part1, part2, hashes, extra)
        print("video index:", index)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
