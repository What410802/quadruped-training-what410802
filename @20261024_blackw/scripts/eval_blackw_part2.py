#!/usr/bin/env python3
"""Headless MuJoCo evaluation of one blackW TorchScript policy on official Part 2 levels.

The evaluation contract mirrors the rl_sar deployment stack (see
``ws/src/rl_sar_blackw``):

* observation = ``commands, base_ang_vel, projected_gravity, joint_pos_rel,
  joint_vel, last_action`` with the deployment scales (57 values), six frames
  newest -> oldest (342 values);
* action = 3 leg position residuals (scale from the policy config, default 0.25)
  + 1 wheel velocity target (default 10) per leg;
* torque = ``kp*(q_des - q) - kd*dq`` for legs and ``kd*(dq_des - dq)`` for
  wheels, clipped to the per-joint torque limits;
* physics dt and policy period are command-line options; the deployment MJCF
  runs at 2 ms physics with 50 Hz policy inference.

Scenes and judge metadata come from ``gen_part2_official_levels.py`` (official
terrain.zip geometry, isolated per level).  A longer runway and a two-stage
velocity command (fast approach, slow near the obstacle) can be requested; the
rules allow a custom map and the operator drives the velocity command, so report
the command profile with the score.

Usage (from MyMonoRepo.d):
  pixi run python @20261024_blackw/scripts/eval_blackw_part2.py \
      --policy @20261024_blackw/ws/src/rl_sar_blackw/policy/blackW/obstacle \
      --json ../prep.d/results/blackw_official/obstacle.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import mujoco
import numpy as np
import torch
import yaml

TASK = Path(__file__).resolve().parents[1]
REPO = TASK.parent
POLICY_ROOT = TASK / "ws/src/rl_sar_blackw/policy/blackW"
SCENE_DIR = TASK / "ws/src/rl_sar_blackw/scenes/blackW"
LEVELS = SCENE_DIR / "part2_official_levels.json"
CONTRACT = REPO / "@20261019_locomotion/comp/CONTRACT.json"

sys.path.insert(0, str(REPO / "@20261019_locomotion/scripts/agent_scripts"))
from comp_part2_judge import score_for_level  # noqa: E402

FALL_TILT_DEG = 75.0
FALL_Z_M = 0.15
# Judge contract version for score traceability (bumped whenever a predicate
# changes; old result JSONs keep their own version string).
JUDGE_VERSION = "v5-wheel-terminal-bands-2026-10-25"
# Wheel geometry / terminal-state tolerances (blackW wheel radius 0.103 m).
WHEEL_RADIUS_M = 0.103
# A wheel counts as "on a support surface" when its bottom is within this
# distance of that surface (the default pose has ~2 cm static penetration).
WHEEL_ON_SURFACE_TOL_M = 0.06
# Wall crossing: all wheels must be past the wall and back on the ground.
WALL_BACK_CLEARANCE_M = 0.16
GROUND_WHEEL_TOL_M = 0.08
# Stairs: all four wheels must be past the end of the down flight and back on
# the ground (the official staircase is up + 0.8 m landing + down).
STEP_DESCEND_CLEARANCE_M = 0.10
# Extra hold beyond the rule's 0.2 s so the terminal state is genuinely stable.
TERMINAL_HOLD_EXTRA_S = 0.1


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_policy_config(policy: Path) -> dict:
    """Return the blackW policy config (``blackW/<name>:`` mapping) plus base.yaml."""
    root = policy if policy.is_dir() else policy.parent
    name = root.name
    base = yaml.safe_load((POLICY_ROOT / "base.yaml").read_text(encoding="utf-8"))["blackW"]
    cfg = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))
    for key in (name, f"blackW/{name}"):
        if key in cfg:
            merged = dict(base)
            merged.update(cfg[key])
            return merged
    if len(cfg) == 1:
        merged = dict(base)
        merged.update(next(iter(cfg.values())))
        return merged
    raise KeyError(f"policy config key for {name!r} not found in {root / 'config.yaml'}")


class Part2OfficialJudge:
    """Rule-faithful Part 2 capability judge on official-geometry levels.

    Success is a **terminal-state predicate on the robot's support points**: the
    attempt only counts once all four wheels have reached the target support
    surface and stay there (``hold_s``), not when the trunk merely crosses a
    line.  Failure is a rule violation (fall, lane bypass, wheel inside a trench
    slot) or timeout; it is a termination, never a reward term.

    Per obstacle:
      * platform: all four wheels on the platform top, base inside the platform
        x-range, stable ``hold_s``;
      * stairs / slope: all four wheels on the top landing, past the goal x;
      * wall: crossed the wall plane, all four wheels back on the ground past
        the wall, stable;
      * gap (trench): all four wheels on the far plateau past the far slot edge;
        a wheel dipping into the slot deeper than ``min(0.5*depth, radius)``
        invalidates the attempt (official trench depth = 0.30 m, wheel radius
        0.103 m -> 0.103 m allowed drop);
      * plum: all four wheels on the exit platform; any wheel touching the
        ground while over the pile field invalidates the attempt.
    """

    def __init__(self, level: dict) -> None:
        self.level = level
        self.j = level["judge"]
        self.kind = self.j["kind"]
        self.t = 0.0
        self.last_t = None
        self.held = 0.0
        self.status = "running"
        self.reason = ""
        self.detail: dict = {"max_z": 0.0, "max_x": 0.0, "min_z_gap": 9.9,
                             "min_wheel_z": 9.9, "min_wheel_z_slot": 9.9}
        self.crossed = False
        self.max_z_near = 0.0
        self.gap_near_crossed = False
        self.gap_far_crossed = False
        self.top_seen = False
        self.prev = None

    def _lateral_ok(self, y: float) -> bool:
        return abs(y) <= float(self.j.get("lane_half_width", 0.7))

    def update(self, t: float, base: np.ndarray, tilt_deg: float,
               wheel_x: np.ndarray | None = None,
               wheel_z: np.ndarray | None = None) -> str:
        if self.status != "running":
            return self.status
        self.t = float(t)
        x, y, z = (float(base[0]), float(base[1]), float(base[2]))
        self.detail["max_z"] = round(max(self.detail["max_z"], z), 3)
        self.detail["max_x"] = round(max(self.detail["max_x"], x), 3)
        lateral_ok = self._lateral_ok(y)
        if wheel_z is not None and len(wheel_z):
            self.detail["min_wheel_z"] = round(min(self.detail["min_wheel_z"],
                                                   float(np.min(wheel_z))), 3)

        if tilt_deg > FALL_TILT_DEG or z < FALL_Z_M:
            self.status, self.reason = "fail", (
                f"fell:tilt={tilt_deg:.1f}" if tilt_deg > FALL_TILT_DEG else f"fell:z={z:.2f}")
            return self.status

        cond = False
        kind = self.kind
        if kind == "platform":
            lo, hi = self.j["x_range"]
            top = float(self.j["top_z"])
            cond = (lo <= x <= hi and lateral_ok
                    and wheel_z is not None
                    and np.all((wheel_z >= top - WHEEL_ON_SURFACE_TOL_M)
                               & (wheel_z <= top + 0.20)))
        elif kind == "stairs":
            top = float(self.j["top_z"])
            end_x = float(self.j.get("descend_end_x", self.j["goal_x_min"]))
            # Climb evidence: all four wheels on the top landing at some point.
            if (wheel_z is not None and np.all(wheel_z >= top - WHEEL_ON_SURFACE_TOL_M)
                    and x >= float(self.j["goal_x_min"])):
                self.top_seen = True
            # Terminal state: descended the far flight, all wheels on the ground.
            cond = (self.top_seen and lateral_ok and wheel_z is not None
                    and wheel_x is not None
                    and np.all(wheel_x >= end_x + STEP_DESCEND_CLEARANCE_M)
                    and np.all((wheel_z >= -0.06) & (wheel_z <= 0.20))
                    and x >= end_x + STEP_DESCEND_CLEARANCE_M)
        elif kind == "slope":
            rise = float(self.j["rise_z"])
            cond = (x >= float(self.j["goal_x_min"]) and lateral_ok
                    and wheel_z is not None
                    and np.all((wheel_z >= rise - WHEEL_ON_SURFACE_TOL_M)
                               & (wheel_z <= rise + 0.20)))
        elif kind == "wall":
            wx_wall = float(self.j["wall_x"])
            if self.prev is not None and (self.prev - wx_wall) * (x - wx_wall) <= 0 \
                    and abs(x - self.prev) < 1.0 and lateral_ok:
                self.crossed = True
            if abs(x - wx_wall) <= 0.8:
                self.max_z_near = max(self.max_z_near, z)
            cond = (self.crossed and x >= float(self.j["goal_x_min"]) and lateral_ok
                    and self.max_z_near >= float(self.j["climb_z_min"])
                    and wheel_z is not None
                    and wheel_x is not None
                    and np.all(wheel_x >= wx_wall + WALL_BACK_CLEARANCE_M)
                    and np.all(wheel_z <= GROUND_WHEEL_TOL_M))
        elif kind == "gap":
            nx, fx = float(self.j["near_x"]), float(self.j["far_x"])
            depth = float(self.j["plateau_z"])
            allowed = min(0.5 * depth, WHEEL_RADIUS_M)
            floor_z = depth - allowed
            if self.prev is not None and abs(x - self.prev) < 1.0:
                if (self.prev - nx) * (x - nx) <= 0 and lateral_ok:
                    self.gap_near_crossed = True
                if (self.prev - fx) * (x - fx) <= 0 and lateral_ok:
                    self.gap_far_crossed = True
            if wheel_x is not None and wheel_z is not None:
                in_slot = (wheel_x >= nx - 0.06) & (wheel_x <= fx + 0.06)
                if np.any(in_slot):
                    slot_z = float(np.min(wheel_z[in_slot]))
                    self.detail["min_wheel_z_slot"] = round(
                        min(self.detail["min_wheel_z_slot"], slot_z), 3)
                    if slot_z < floor_z - 0.01:
                        self.status, self.reason = "fail", f"gap:wheel_in_slot:z={slot_z:.2f}"
                        return self.status
            cond = (self.gap_near_crossed and self.gap_far_crossed
                    and x >= fx + 0.15 and lateral_ok
                    and wheel_z is not None
                    and np.all((wheel_z >= depth - WHEEL_ON_SURFACE_TOL_M)
                               & (wheel_z <= depth + 0.20)))
        elif kind == "plum":
            lo, hi = self.j["cube_x_range"]
            if lo <= x <= hi and wheel_z is not None:
                if np.any(wheel_z < self.j["z_cross_min"]):
                    self.status, self.reason = "fail", (
                        f"dropped:z={float(np.min(wheel_z)):.2f}@x={x:.2f}")
                    return self.status
                self.top_seen = True
            cond = (self.top_seen and x >= float(self.j["goal_x_min"]) and lateral_ok
                    and wheel_z is not None
                    and np.all((wheel_z >= float(self.j["top_z"]) - WHEEL_ON_SURFACE_TOL_M)
                               & (wheel_z <= float(self.j["top_z"]) + 0.20)))
        else:
            raise ValueError(kind)

        dt = 0.02 if self.last_t is None else max(0.0, self.t - self.last_t)
        self.last_t = self.t
        self.prev = x
        if cond:
            self.held += dt
            if self.held >= float(self.j.get("hold_s", 0.2)) + TERMINAL_HOLD_EXTRA_S:
                self.status = "success"
        else:
            self.held = 0.0
        return self.status

    def finalize(self, reason: str = "timeout") -> dict:
        if self.status == "running":
            self.status = "fail"
            if not self.reason:
                self.reason = reason
        return {"status": self.status, "reason": self.reason,
                "detail": {k: v for k, v in self.detail.items() if not k.startswith("_")}}


class PolicyRunner:
    """MuJoCo + TorchScript deployment-contract runner for blackW."""

    def __init__(self, scene: Path, policy_pt: Path, cfg: dict,
                 physics_dt: float = 0.002, policy_dt: float = 0.02,
                 torque_limit_scale: float = 1.0) -> None:
        self.model = mujoco.MjModel.from_xml_path(str(scene))
        self.model.opt.timestep = physics_dt
        self.data = mujoco.MjData(self.model)
        self.cfg = cfg
        self.policy = torch.jit.load(str(policy_pt))
        self.policy.eval()
        self.policy_dt = policy_dt
        self.substeps = max(1, int(round(policy_dt / physics_dt)))
        self.joint_names = list(cfg["joint_names"])
        self.default_pos = np.asarray(cfg["default_dof_pos"], dtype=np.float64)
        self.action_scale = np.asarray(cfg["action_scale"], dtype=np.float64)
        self.kp = np.asarray(cfg["rl_kp"], dtype=np.float64) * torque_limit_scale
        self.kd = np.asarray(cfg["rl_kd"], dtype=np.float64) * torque_limit_scale
        self.torque_limits = np.asarray(cfg["torque_limits"], dtype=np.float64)
        self.obs_scale = {
            "commands": np.asarray(cfg.get("commands_scale", [2.0, 2.0, 0.25])),
            "ang_vel": float(cfg.get("ang_vel_scale", 0.25)),
            "dof_pos": float(cfg.get("dof_pos_scale", 1.0)),
            "dof_vel": float(cfg.get("dof_vel_scale", 0.05)),
        }
        self.clip_obs = float(cfg.get("clip_obs", 100.0))
        self.clip_actions = 100.0
        self.history_len = len(cfg.get("observations_history", [0, 1, 2, 3, 4, 5]))
        self.wheel = np.asarray(cfg.get("wheel_indices", [3, 7, 11, 15]))
        self.action = np.zeros(16)
        self.hist: list[np.ndarray] = []
        self.qadr = np.array([self.model.jnt_qposadr[
            mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, n)]
            for n in self.joint_names])
        self.vadr = np.array([self.model.jnt_dofadr[
            mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, n)]
            for n in self.joint_names])
        joint_ids = [mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, n)
                     for n in self.joint_names]
        self.act_ids = []
        for jid in joint_ids:
            hits = [a for a in range(self.model.nu) if self.model.actuator_trnid[a, 0] == jid]
            if not hits:
                raise RuntimeError(f"no actuator for joint id {jid}")
            self.act_ids.append(hits[0])
        self.trunk_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, "trunk")
        # Wheel bodies ("<LEG>_foot") carry the wheel cylinder (radius 0.103).
        self.wheel_bodies = []
        for leg in ("FL", "FR", "RL", "RR"):
            bid = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, f"{leg}_foot")
            if bid >= 0:
                self.wheel_bodies.append(bid)
        self.wheel_radius = float(cfg.get("wheel_radius", 0.103))
        self.reset_pose()

    def reset_pose(self, spawn: np.ndarray | None = None, yaw: float = 0.0) -> None:
        if spawn is None:
            spawn = np.array([0.0, 0.0, 0.5, 0.0])
        self.data.qpos[:] = self.model.qpos0
        for adr, val in zip(self.qadr, self.default_pos):
            self.data.qpos[adr] = val
        self.data.qpos[0:3] = spawn[:3]
        self.data.qpos[3:7] = [np.cos(yaw / 2.0), 0.0, 0.0, np.sin(yaw / 2.0)]
        self.data.qvel[:] = 0.0
        mujoco.mj_forward(self.model, self.data)
        self.action[:] = 0.0
        self.hist = []

    def _obs(self, command: np.ndarray) -> np.ndarray:
        d, m = self.data, self.model
        q = np.array([d.qpos[a] for a in self.qadr])
        qd = np.array([d.qvel[a] for a in self.vadr])
        res = np.zeros(6)
        mujoco.mj_objectVelocity(m, d, mujoco.mjtObj.mjOBJ_BODY, self.trunk_id, res, 1)
        w_body = res[3:6]
        mat = d.xmat[self.trunk_id].reshape(3, 3)
        grav = mat.T @ np.array([0.0, 0.0, -1.0])
        dof_pos_rel = q - self.default_pos
        dof_pos_rel[self.wheel] = 0.0
        obs = np.concatenate([
            command * self.obs_scale["commands"],
            w_body * self.obs_scale["ang_vel"],
            grav,
            dof_pos_rel * self.obs_scale["dof_pos"],
            qd * self.obs_scale["dof_vel"],
            self.action,
        ])
        return np.clip(obs, -self.clip_obs, self.clip_obs).astype(np.float32)

    def infer(self, command: np.ndarray) -> None:
        obs = self._obs(command)
        if not self.hist:
            self.hist = [obs.copy() for _ in range(self.history_len)]
        else:
            self.hist = self.hist[1:] + [obs.copy()]
        inp = np.concatenate(self.hist[::-1], axis=0).astype(np.float32)
        with torch.no_grad():
            out = self.policy(torch.from_numpy(inp).unsqueeze(0))
        self.action[:] = np.clip(out.numpy().reshape(-1).astype(np.float64),
                                 -self.clip_actions, self.clip_actions)

    def _apply_torque(self) -> None:
        d = self.data
        q = np.array([d.qpos[a] for a in self.qadr])
        qd = np.array([d.qvel[a] for a in self.vadr])
        act = self.action * self.action_scale
        is_wheel = np.zeros(16, dtype=bool)
        is_wheel[self.wheel] = True
        q_des = self.default_pos + np.where(is_wheel, 0.0, act)
        dq_des = np.where(is_wheel, act, 0.0)
        tau = self.kp * (q_des - q) - self.kd * (qd - dq_des)
        tau = np.clip(tau, -self.torque_limits, self.torque_limits)
        for aid, val in zip(self.act_ids, tau):
            d.ctrl[aid] = val

    def step(self) -> None:
        for _ in range(self.substeps):
            self._apply_torque()
            mujoco.mj_step(self.model, self.data)

    def base(self) -> tuple[np.ndarray, float]:
        pos = self.data.qpos[0:3].copy()
        mat = np.zeros(9)
        mujoco.mju_quat2Mat(mat, self.data.qpos[3:7])
        mat = mat.reshape(3, 3)
        tilt = np.degrees(np.arccos(np.clip(mat[2, 2], -1.0, 1.0)))
        return pos, float(tilt)

    def wheel_states(self) -> tuple[np.ndarray, np.ndarray]:
        """Return ``(x, z_bottom)`` arrays for the four wheels (world frame)."""
        xs = np.array([float(self.data.xpos[bid][0]) for bid in self.wheel_bodies])
        zs = np.array([float(self.data.xpos[bid][2]) for bid in self.wheel_bodies])
        return xs, zs - self.wheel_radius

    def warmup(self, command: np.ndarray, seconds: float = 0.4) -> None:
        for _ in range(int(round(seconds / self.policy_dt))):
            self.infer(command)
            self.step()


class _VideoWriter:
    """Render a follow camera to H.264 via ffmpeg (EGL offscreen)."""

    def __init__(self, path: Path, runner: PolicyRunner, width: int = 640,
                 height: int = 400, fps: int = 25) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.renderer = mujoco.Renderer(runner.model, height, width)
        self.cam = mujoco.MjvCamera()
        self.cam.distance = 2.6
        self.cam.azimuth = 120.0
        self.cam.elevation = -22.0
        self.proc = subprocess.Popen(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
             "-s", f"{width}x{height}", "-r", str(fps), "-i", "-",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", str(self.path)],
            stdin=subprocess.PIPE)

    def write(self, runner: PolicyRunner, pos: np.ndarray) -> None:
        self.cam.lookat[:] = [float(pos[0]) + 0.7, float(pos[1]),
                              max(0.4, float(pos[2]) + 0.1)]
        self.renderer.update_scene(runner.data, self.cam)
        frame = self.renderer.render()
        self.proc.stdin.write(frame.astype(np.uint8).tobytes())

    def close(self) -> None:
        if self.proc.stdin:
            self.proc.stdin.close()
        self.proc.wait(timeout=120)
        self.renderer.close()


def _command_at(schedule: dict | None, x: float, base_command: np.ndarray) -> np.ndarray:
    cmd = base_command.copy()
    if not schedule:
        return cmd
    if "slow_from_x" in schedule and x >= float(schedule["slow_from_x"]):
        cmd[0] = float(schedule["cmd_slow"])
    return cmd


def run_attempt(scene: Path, level: dict, policy_pt: Path, cfg: dict,
                command: np.ndarray, seconds: float, physics_dt: float,
                policy_dt: float, jitter_y: float, seed: int, record: bool,
                runway_extra: float, schedule: dict | None,
                video: Path | None, video_every: int) -> dict:
    runner = PolicyRunner(scene, policy_pt, cfg, physics_dt=physics_dt,
                          policy_dt=policy_dt)
    spawn = np.asarray(level["spawn"], dtype=np.float64).copy()
    spawn[0] -= runway_extra
    spawn[1] += float(jitter_y)
    runner.reset_pose(spawn=spawn[:3], yaw=float(spawn[3]))
    judge = Part2OfficialJudge(level)
    runner.warmup(command, seconds=0.4)
    n = int(round(seconds / policy_dt))
    traj = []
    sim_t = 0.0
    renderer = _VideoWriter(video, runner) if video is not None else None
    try:
        for i in range(n):
            cmd = _command_at(schedule, float(runner.data.qpos[0]), command)
            runner.infer(cmd)
            runner.step()
            sim_t += policy_dt
            pos, tilt = runner.base()
            wxs, wzs = runner.wheel_states()
            judge.update(sim_t, pos, tilt, wheel_x=wxs, wheel_z=wzs)
            if renderer is not None and i % video_every == 0:
                renderer.write(runner, pos)
            if record and i % 5 == 0:
                traj.append([round(sim_t, 3), round(float(pos[0]), 3),
                             round(float(pos[1]), 3), round(float(pos[2]), 3),
                             round(tilt, 2)])
            if judge.status != "running":
                break
    finally:
        if renderer is not None:
            renderer.close()
    report = judge.finalize("timeout")
    pos, tilt = runner.base()
    return {"judge": report, "base": [round(float(v), 3) for v in pos],
            "tilt_deg": round(tilt, 2), "sim_time": round(sim_t, 2), "traj": traj}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", type=Path, default=POLICY_ROOT / "obstacle",
                    help="policy dir containing policy.pt + config.yaml, or .pt path")
    ap.add_argument("--levels", type=Path, default=LEVELS)
    ap.add_argument("--only", action="append", default=[])
    ap.add_argument("--attempts", type=int, default=1)
    ap.add_argument("--seconds", type=float, default=None)
    ap.add_argument("--command", type=float, nargs=3, default=None,
                    metavar=("VX", "VY", "WZ"))
    ap.add_argument("--slow-from-x", type=float, default=None,
                    help="switch vx to --cmd-slow once base x reaches this value")
    ap.add_argument("--cmd-slow", type=float, default=0.3)
    ap.add_argument("--runway-extra", type=float, default=0.0,
                    help="move the spawn further back (longer approach)")
    ap.add_argument("--jitter-y", type=float, default=0.0)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--physics-dt", type=float, default=0.002)
    ap.add_argument("--policy-dt", type=float, default=0.02)
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--video-dir", type=Path, default=None,
                    help="write one mp4 per level into this directory")
    ap.add_argument("--video-every", type=int, default=4)
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--contract", type=Path, default=CONTRACT)
    args = ap.parse_args()

    if args.video_dir is not None and os.environ.get("MUJOCO_GL") is None:
        raise SystemExit("rendering needs MUJOCO_GL=egl (or osmesa) in the environment")

    policy_pt = args.policy if args.policy.is_file() else args.policy / "policy.pt"
    if not policy_pt.exists():
        raise SystemExit(f"policy not found: {policy_pt}")
    cfg = load_policy_config(args.policy)
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    part2 = contract["parts"]["part2"]
    levels = json.loads(args.levels.read_text(encoding="utf-8"))["levels"]
    selected = levels
    if args.only:
        wanted = set(args.only)
        selected = [e for e in levels if e["category"] in wanted or e["key"] in wanted]
    if not selected:
        raise SystemExit(f"no level matched {args.only}")

    schedule = None
    if args.slow_from_x is not None:
        schedule = {"slow_from_x": args.slow_from_x, "cmd_slow": args.cmd_slow}
    t0 = time.time()
    results = []
    for entry in selected:
        scene = SCENE_DIR / entry["scene"]
        command = np.asarray(args.command if args.command is not None
                             else entry["command"], dtype=np.float64)
        seconds = args.seconds if args.seconds is not None else float(entry["seconds"])
        attempts = []
        for k in range(max(1, args.attempts)):
            seed = args.seed + 1000 * k + len(results)
            jitter = float(np.random.default_rng(seed).uniform(-args.jitter_y, args.jitter_y)) \
                if args.jitter_y > 0 else 0.0
            video = (args.video_dir / f"{entry['key']}_a{k}.mp4") \
                if args.video_dir is not None else None
            attempts.append(run_attempt(scene, entry, policy_pt, cfg, command, seconds,
                                       args.physics_dt, args.policy_dt, jitter, seed,
                                       args.record, args.runway_extra, schedule,
                                       video, args.video_every))
        successes = sum(1 for a in attempts if a["judge"]["status"] == "success")
        record = {"key": entry["key"], "category": entry["category"],
                  "level": entry["level"], "unit": entry["unit"],
                  "success_count": successes, "attempt_count": len(attempts),
                  "best_success": successes > 0, "attempts": attempts}
        results.append(record)
        a = attempts[-1]
        print(f"{entry['key']:22s} {'SUCCESS' if record['best_success'] else 'fail':7s} "
              f"({successes}/{len(attempts)}) judge={a['judge']['status']:7s} "
              f"{a['judge']['reason']:26s} base={a['base']} tilt={a['tilt_deg']}")

    categories: dict[str, dict] = {}
    for rec in results:
        cat = rec["category"]
        c = categories.setdefault(cat, {"levels": [], "best_level": None, "score": 0})
        c["levels"].append({"level": rec["level"], "unit": rec["unit"],
                            "success_count": rec["success_count"],
                            "attempt_count": rec["attempt_count"],
                            "best_success": rec["best_success"]})
        if rec["best_success"] and (c["best_level"] is None or rec["level"] > c["best_level"]):
            c["best_level"] = rec["level"]
    total = 0
    for cat, c in categories.items():
        c["score"] = int(score_for_level(part2, cat, c["best_level"])) \
            if c["best_level"] is not None else 0
        total += c["score"]
    payload = {
        "judge": "blackw_part2_eval.Part2OfficialJudge",
        "policy": str(policy_pt),
        "policy_sha256": sha256_file(policy_pt),
        "levels_file": str(args.levels),
        "levels_sha256": sha256_file(args.levels),
        "physics_dt": args.physics_dt,
        "policy_dt": args.policy_dt,
        "judge_version": JUDGE_VERSION,
        "wheel_radius_m": WHEEL_RADIUS_M,
        "terminal_hold_extra_s": TERMINAL_HOLD_EXTRA_S,
        "attempts": max(1, args.attempts),
        "jitter_y": args.jitter_y,
        "runway_extra": args.runway_extra,
        "command": args.command,
        "command_schedule": schedule,
        "categories": categories,
        "total_score": total,
        "results": results,
        "wall_time_s": round(time.time() - t0, 1),
        "notes": ("official terrain.zip geometry, isolated custom map (allowed by the "
                  "team-race rules); diagnostic until a frozen protocol is defined"),
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.json}")
    print(f"total_score={total} (categories={len(categories)}) wall={payload['wall_time_s']}s")


if __name__ == "__main__":
    main()
