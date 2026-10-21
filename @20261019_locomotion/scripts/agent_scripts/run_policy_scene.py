"""Run an exported Black policy in a standalone MuJoCo scene.

This is the local P0 evaluation/visualization path: no mjlab dependency, one
environment, direct motor torque from the 45-D actor.  It is not the training env.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import mujoco
import numpy as np
import torch

POLICY_JOINT_ORDER = tuple(
    f"{leg}_{j}_joint" for leg in ("FL", "FR", "RL", "RR") for j in ("hip", "thigh", "calf")
)
Q_DEFAULT = {
    "FL_hip_joint": 0.0, "FL_thigh_joint": 0.8014, "FL_calf_joint": -1.527,
    "FR_hip_joint": 0.0, "FR_thigh_joint": -0.8014, "FR_calf_joint": 1.527,
    "RL_hip_joint": 0.0, "RL_thigh_joint": 0.8014, "RL_calf_joint": -1.527,
    "RR_hip_joint": 0.0, "RR_thigh_joint": -0.8014, "RR_calf_joint": 1.527,
}
KP, KD = 40.0, 1.2
ACTION_SCALE = 0.25
EFFORT_LIMIT = 20.0


def _id(model: mujoco.MjModel, obj: mujoco.mjtObj, name: str) -> int:
    return mujoco.mj_name2id(model, obj, name)


class ScenePolicyRunner:
    def __init__(self, scene: str, policy_path: str, start: tuple[float, float, float, float]) -> None:
        self.model = mujoco.MjSpec.from_file(scene).compile()
        self.model.opt.timestep = 0.005
        self.data = mujoco.MjData(self.model)
        self.policy = torch.jit.load(policy_path, map_location="cpu").eval()
        self.qpos_adr = np.array([self.model.jnt_qposadr[_id(self.model, mujoco.mjtObj.mjOBJ_JOINT, j)] for j in POLICY_JOINT_ORDER])
        self.qvel_adr = np.array([self.model.jnt_dofadr[_id(self.model, mujoco.mjtObj.mjOBJ_JOINT, j)] for j in POLICY_JOINT_ORDER])
        self.motor_ids = np.array([_id(self.model, mujoco.mjtObj.mjOBJ_ACTUATOR, f"motor_{j}") for j in POLICY_JOINT_ORDER])
        self.trunk = _id(self.model, mujoco.mjtObj.mjOBJ_BODY, "trunk")
        self.q_default = np.array([Q_DEFAULT[j] for j in POLICY_JOINT_ORDER], dtype=np.float64)
        self.start = start
        self.last_action = np.zeros(12, dtype=np.float64)
        self._reset()

    def _reset(self) -> None:
        self.data.qpos[:] = 0.0
        self.data.qvel[:] = 0.0
        x, y, z, yaw = self.start
        self.data.qpos[0:3] = (x, y, z)
        self.data.qpos[3:7] = (np.cos(yaw / 2), 0.0, 0.0, np.sin(yaw / 2))
        self.data.qpos[self.qpos_adr] = self.q_default
        self.last_action[:] = 0.0
        mujoco.mj_forward(self.model, self.data)

    def obs(self, command: np.ndarray) -> np.ndarray:
        gyro = np.array(self.data.sensor("imu_ang_vel").data, dtype=np.float64)
        quat = np.array(self.data.qpos[3:7], dtype=np.float64)  # wxyz
        # Body-frame gravity vector from root quaternion.
        w, x, y, z = quat
        R = np.array([
            [1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
            [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
            [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)],
        ])
        gravity = R.T @ np.array([0.0, 0.0, -1.0])
        qpos = np.array(self.data.qpos[self.qpos_adr]) - self.q_default
        qvel = np.array(self.data.qvel[self.qvel_adr]) * 0.05
        return np.concatenate([
            command * np.array([2.0, 2.0, 0.25]),
            gyro * 0.25,
            gravity,
            qpos,
            qvel,
            self.last_action,
        ]).astype(np.float32)

    def step(self, command: np.ndarray) -> None:
        obs = torch.from_numpy(self.obs(command)).unsqueeze(0)
        with torch.no_grad():
            raw = self.policy(obs).numpy().reshape(-1).astype(np.float64)
        raw = np.clip(raw, -1.0, 1.0)
        self.last_action[:] = raw
        q_target = self.q_default + ACTION_SCALE * raw
        q = np.array(self.data.qpos[self.qpos_adr])
        qd = np.array(self.data.qvel[self.qvel_adr])
        tau = np.clip(KP * (q_target - q) - KD * qd, -EFFORT_LIMIT, EFFORT_LIMIT)
        self.data.ctrl[self.motor_ids] = tau
        for _ in range(4):
            mujoco.mj_step(self.model, self.data)

    def base(self) -> tuple[np.ndarray, float]:
        pos = np.array(self.data.xpos[self.trunk])
        quat = np.array(self.data.xquat[self.trunk])
        w, x, y, z = quat
        R = np.array([
            [1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
            [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
            [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)],
        ])
        tilt = np.degrees(np.arccos(np.clip(R[2, 2], -1.0, 1.0)))
        return pos, float(tilt)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", default="@20261019_locomotion/assets/terrain/part1/part1_eval_scene.xml")
    parser.add_argument("--policy", default="@20261019_locomotion/assets/policies/flat-ft-2500/policy.pt")
    parser.add_argument("--start", type=float, nargs=4, default=(3.7, -9.0, 0.55, 0.0))
    parser.add_argument("--command", type=float, nargs=3, default=(0.0, 0.0, 0.0))
    parser.add_argument("--warmup", type=float, default=1.0)
    parser.add_argument("--seconds", type=float, default=4.0)
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    runner = ScenePolicyRunner(args.scene, args.policy, tuple(args.start))
    cmd = np.array(args.command, dtype=np.float64)
    for _ in range(int(args.warmup / 0.02)):
        runner.step(np.zeros(3))
    if args.render:
        frames = []
        renderer = mujoco.Renderer(runner.model, height=480, width=640)
        opt = mujoco.MjvOption(); opt.geomgroup[:] = 1
        cam = mujoco.MjvCamera(); cam.distance = 2.2; cam.elevation = -20; cam.azimuth = 135
        steps = int(args.seconds / 0.02)
        for i in range(steps):
            runner.step(cmd)
            pos, _ = runner.base()
            cam.lookat[:] = (pos[0], pos[1], max(0.2, pos[2] - 0.15))
            renderer.update_scene(runner.data, camera=cam, scene_option=opt)
            frames.append(renderer.render().copy())
        renderer.close()
        if args.out:
            out = Path(args.out)
            out.parent.mkdir(parents=True, exist_ok=True)
            tmp = out.parent / "frames"
            tmp.mkdir(parents=True, exist_ok=True)
            for i, frame in enumerate(frames):
                with open(tmp / f"f{i:04d}.ppm", "wb") as f:
                    f.write(f"P6\n{frame.shape[1]} {frame.shape[0]}\n255\n".encode())
                    f.write(frame.tobytes())
            subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-framerate", "50", "-i", str(tmp / "f%04d.ppm"), str(out)], check=True)
            for p in tmp.glob("*.ppm"):
                p.unlink()
            print("wrote", out)
    else:
        for _ in range(int(args.seconds / 0.02)):
            runner.step(cmd)
    pos, tilt = runner.base()
    print("base", np.round(pos, 3), "tilt_deg", round(tilt, 2))


if __name__ == "__main__":
    main()
