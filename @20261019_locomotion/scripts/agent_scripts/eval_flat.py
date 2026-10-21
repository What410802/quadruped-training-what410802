"""Flat-ground gate evaluation for an exported Black PPO policy (45-dim obs).

Investigation / gate script for @20261019_locomotion. Mirrors the training
contract: policy obs 45, action 12, q_target = q_default + 0.25*raw,
Kp=40/Kd=1.2, policy period 20 ms (physics 5 ms x decimation 4).

Usage (from repo root):
    pixi run python @20261019_locomotion/scripts/agent_scripts/eval_flat.py \
        --policy @20261019_locomotion/assets/policies/baseline-2000/policy.pt

The scene is the existing flat playground scene (robot + plane). Metrics are
printed as a JSON summary; this is the G1/G2 gate tool, not a deployment runner.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import time

import mujoco
import numpy as np
import torch

LEGS = ("FL", "FR", "RL", "RR")
JOINTS = tuple(f"{leg}_{part}_joint" for leg in LEGS for part in ("hip", "thigh", "calf"))
# Policy order FL -> FR -> RL -> RR (same as the exported policy contract).
DEFAULT_Q = np.array(
    [
        0.0, 0.8014, -1.527,
        0.0, -0.8014, 1.527,
        0.0, 0.8014, -1.527,
        0.0, -0.8014, 1.527,
    ],
    dtype=np.float64,
)
ACTION_SCALE = 0.25
KP, KD = 40.0, 1.2
POLICY_DT = 0.02
PHYSICS_DT = 0.005
CMD_SCALE = np.array([2.0, 2.0, 0.25])
ANG_SCALE = 0.25
DOF_VEL_SCALE = 0.05
SETTLE_S = 1.0
WARMUP_S = 1.0


def quat_rotate_inv(quat: np.ndarray, vec: np.ndarray) -> np.ndarray:
    """Rotate world vector into body frame (inverse of quat's active rotation)."""
    w, x, y, z = quat
    # conjugate quaternion then active rotation
    q = np.array([w, -x, -y, -z], dtype=np.float64)
    t = 2.0 * np.cross(q[1:], vec)
    return vec + q[0] * t + np.cross(q[1:], t)


def tilt_deg(quat: np.ndarray) -> float:
    w, x, y, z = quat
    r22 = 1.0 - 2.0 * (x * x + y * y)
    return math.degrees(math.acos(max(-1.0, min(1.0, r22))))


class FlatEval:
    def __init__(self, scene: pathlib.Path, policy_path: pathlib.Path) -> None:
        self.m = mujoco.MjModel.from_xml_path(str(scene))
        self.m.opt.timestep = PHYSICS_DT
        self.m.opt.integrator = mujoco.mjtIntegrator.mjINT_IMPLICITFAST
        self.d = mujoco.MjData(self.m)

        self.policy = torch.jit.load(str(policy_path), map_location="cpu")
        self.policy.eval()

        # Policy-order joint/actuator mapping, resolved by names (model order is FL,FR,RR,RL).
        self.qadr = np.array(
            [self.m.jnt_qposadr[self.m.joint(name).id] for name in JOINTS], dtype=np.int64
        )
        self.vadr = np.array(
            [self.m.jnt_dofadr[self.m.joint(name).id] for name in JOINTS], dtype=np.int64
        )
        self.act_ids = np.array(
            [self.m.actuator(f"{name}_motor").id for name in JOINTS], dtype=np.int64
        )
        self.quat_adr = int(self.m.sensor("imu_quat").adr[0])
        self.gyro_adr = int(self.m.sensor("imu_gyro").adr[0])
        self.ctrl_lo = self.m.actuator_ctrlrange[self.act_ids, 0].copy()
        self.ctrl_hi = self.m.actuator_ctrlrange[self.act_ids, 1].copy()

    def reset(self) -> None:
        mujoco.mj_resetData(self.m, self.d)
        self.d.qpos[0:3] = (0.0, 0.0, 0.45)
        self.d.qpos[3:7] = (1.0, 0.0, 0.0, 0.0)
        self.d.qpos[self.qadr] = DEFAULT_Q
        self.d.qvel[:] = 0.0
        self.d.ctrl[:] = 0.0
        mujoco.mj_forward(self.m, self.d)
        self.last_action = np.zeros(12, dtype=np.float64)

    def _obs(self, cmd: np.ndarray) -> np.ndarray:
        q = self.d.qpos[self.qadr]
        dq = self.d.qvel[self.vadr]
        quat = self.d.sensordata[self.quat_adr : self.quat_adr + 4].copy()
        gyro = self.d.sensordata[self.gyro_adr : self.gyro_adr + 3].copy()
        w = quat[0]
        xyz = quat[1:]
        g = np.array([0.0, 0.0, -1.0])
        grav = g * (2.0 * w * w - 1.0) - np.cross(xyz, g) * w * 2.0 + xyz * np.dot(xyz, g) * 2.0
        return np.concatenate(
            [
                cmd * CMD_SCALE,
                gyro * ANG_SCALE,
                grav,
                (q - DEFAULT_Q) * 1.0,
                dq * DOF_VEL_SCALE,
                self.last_action,
            ]
        )

    def _pd_step(self, q_des: np.ndarray, kp: float, kd: float) -> None:
        q = self.d.qpos[self.qadr]
        dq = self.d.qvel[self.vadr]
        tau = np.clip(kp * (q_des - q) - kd * dq, self.ctrl_lo, self.ctrl_hi)
        self.d.ctrl[self.act_ids] = tau
        mujoco.mj_step(self.m, self.d)

    def settle(self) -> None:
        n = int(round(SETTLE_S / PHYSICS_DT))
        for _ in range(n):
            self._pd_step(DEFAULT_Q, 80.0, 3.0)
        mujoco.mj_forward(self.m, self.d)

    def _policy_step(self, cmd: np.ndarray) -> None:
        obs = self._obs(cmd)
        with torch.no_grad():
            raw = self.policy(torch.from_numpy(obs[None, :]).float()).numpy()[0].astype(np.float64)
        self.last_action = raw
        q_des = DEFAULT_Q + ACTION_SCALE * raw
        for _ in range(int(round(POLICY_DT / PHYSICS_DT))):
            self._pd_step(q_des, KP, KD)

    def run_segment(self, name: str, cmd: tuple[float, float, float], seconds: float) -> dict:
        self.reset()
        self.settle()
        warm_steps = int(round(WARMUP_S / POLICY_DT))
        for _ in range(warm_steps):
            self._policy_step(np.zeros(3))
        cmd_arr = np.asarray(cmd, dtype=np.float64)
        steps = int(round(seconds / POLICY_DT))
        vx_err, vy_err, wz_err = [], [], []
        torque_sq, action_rate_sq = [], []
        max_tilt = 0.0
        min_z = 99.0
        fell = False
        t0 = time.perf_counter()
        prev_action = self.last_action.copy()
        for _ in range(steps):
            self._policy_step(cmd_arr)
            quat = self.d.qpos[3:7].copy()
            tilt = tilt_deg(quat)
            max_tilt = max(max_tilt, tilt)
            min_z = min(min_z, float(self.d.qpos[2]))
            if tilt > 60.0 or self.d.qpos[2] < 0.20:
                fell = True
                break
            # skip first 0.3 s for tracking stats (transition)
            if self.d.time > 0.3:
                v_world = self.d.qvel[0:3].copy()
                v_body = quat_rotate_inv(quat, v_world)
                vx_err.append(abs(v_body[0] - cmd_arr[0]))
                vy_err.append(abs(v_body[1] - cmd_arr[1]))
                wz = float(self.d.sensordata[self.gyro_adr + 2])
                wz_err.append(abs(wz - cmd_arr[2]))
            torque = self.d.actuator_force[self.act_ids].copy()
            torque_sq.append(float(np.sum(torque * torque)))
            action_rate_sq.append(float(np.sum((self.last_action - prev_action) ** 2)))
            prev_action = self.last_action.copy()
        wall = time.perf_counter() - t0
        return {
            "segment": name,
            "cmd": list(cmd),
            "seconds": seconds,
            "fell": fell,
            "max_tilt_deg": max_tilt,
            "min_z": min_z,
            "final_xy": [float(self.d.qpos[0]), float(self.d.qpos[1])],
            "mae_vx": float(np.mean(vx_err)) if vx_err else None,
            "mae_vy": float(np.mean(vy_err)) if vy_err else None,
            "mae_wz": float(np.mean(wz_err)) if wz_err else None,
            "rms_torque_sum": float(np.sqrt(np.mean(torque_sq))) if torque_sq else None,
            "action_rate_mean": float(np.mean(action_rate_sq)) if action_rate_sq else None,
            "wall_s": wall,
        }


DEFAULT_SUITE = [
    ("stand", (0.0, 0.0, 0.0), 5.0),
    ("fwd-slow", (0.3, 0.0, 0.0), 4.0),
    ("fwd-nominal", (0.8, 0.0, 0.0), 6.0),
    ("fwd-fast", (1.5, 0.0, 0.0), 6.0),
    ("bwd", (-0.5, 0.0, 0.0), 4.0),
    ("lat-pos", (0.0, 0.5, 0.0), 4.0),
    ("yaw-pos", (0.0, 0.0, 0.5), 4.0),
    ("combined", (0.8, 0.3, 0.4), 6.0),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--policy",
        type=pathlib.Path,
        default=pathlib.Path("@20261019_locomotion/assets/policies/baseline-2000/policy.pt"),
    )
    parser.add_argument(
        "--scene",
        type=pathlib.Path,
        default=pathlib.Path("@20261005_ros2/scenes/flat_scene.xml"),
    )
    parser.add_argument("--json", type=pathlib.Path, default=None)
    args = parser.parse_args()
    ev = FlatEval(args.scene, args.policy)
    rows = []
    print(f"policy: {args.policy}")
    print(f"scene : {args.scene}")
    for name, cmd, seconds in DEFAULT_SUITE:
        r = ev.run_segment(name, cmd, seconds)
        rows.append(r)
        print(json.dumps(r, ensure_ascii=False))
    summary = {
        "policy": str(args.policy),
        "policy_sha256": __import__("hashlib").sha256(args.policy.read_bytes()).hexdigest(),
        "scene": str(args.scene),
        "contract": {
            "obs": 45,
            "action_scale": ACTION_SCALE,
            "kp": KP,
            "kd": KD,
            "policy_dt": POLICY_DT,
            "physics_dt": PHYSICS_DT,
            "cmd_scale": CMD_SCALE.tolist(),
        },
        "segments": rows,
        "g1_stand_no_fall": not rows[0]["fell"],
        "g1_fwd_nominal_no_fall": not rows[2]["fell"],
    }
    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    print("SUMMARY", json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
