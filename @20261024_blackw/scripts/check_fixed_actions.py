#!/usr/bin/env python3
"""Headless fixed-action smoke test: publish /joy instead of using a physical gamepad.

Low-bar: spawn at the official Part1 height-bar approach, GetUp -> RL -> Back+D-pad Down,
hold forward. Asserts the deployment enters LowBarDrive and crosses the gate region.
Bridge: spawn at the narrow-band bridge approach, Back+D-pad Right; reports progress (the
bridge posture still needs calibration, so it is a smoke/progress check, not a pass gate).

Run from the repository root:
  pixi run python @20261024_blackw/scripts/check_fixed_actions.py --case lowbar
  pixi run python @20261024_blackw/scripts/check_fixed_actions.py --case bridge
"""
from __future__ import annotations

import argparse
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Joy

TASK = Path(__file__).resolve().parents[1]
SCENE_DIR = TASK / "ws/src/rl_sar_blackw/scenes/blackW"
SCENE = SCENE_DIR / "scene_terrain.xml"
LOG_DIR = TASK / "output" / "log"
STATUS_RE = re.compile(r"t=(?P<t>[\d.]+) x=(?P<x>[-\d.]+) y=(?P<y>[-\d.]+) z=(?P<z>[-\d.]+)")
CASES = {
    "lowbar": {"spawn": (5.7, -10.4, 0.676, 1.5707963), "button": 6, "axis_index": 7, "axis": -1, "name": "LowBarDrive"},
    "bridge": {"spawn": (5.7, -3.5, 0.875, 1.5707963), "button": 6, "axis_index": 6, "axis": 1, "name": "BridgeDrive"},
}


def start(args: list[str], log: Path) -> subprocess.Popen:
    handle = log.open("w", encoding="utf-8")
    return subprocess.Popen(args, stdout=handle, stderr=subprocess.STDOUT, start_new_session=True)


def stop(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGINT)
            proc.wait(timeout=5)
        except (subprocess.TimeoutExpired, ProcessLookupError, PermissionError):
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass


class Pad(Node):
    def __init__(self) -> None:
        super().__init__("blackw_fixed_action_test")
        self.pub = self.create_publisher(Joy, "joy", 10)
        self.received_command = False
        self.create_subscription(Joy, "joy", self._noop, 10)

    def _noop(self, _msg) -> None:
        pass

    def press(self, buttons: list[int], axes: list[float]) -> None:
        msg = Joy()
        msg.buttons = buttons
        msg.axes = [float(v) for v in axes]
        self.pub.publish(msg)
        rclpy.spin_once(self, timeout_sec=0.1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", choices=sorted(CASES), default="lowbar")
    args = ap.parse_args()
    case = CASES[args.case]
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    sim_log = LOG_DIR / f"fixed-{args.case}-sim.log"
    rl_log = LOG_DIR / f"fixed-{args.case}-rl.log"
    sx, sy, sz, syaw = case["spawn"]
    scene = SCENE
    sim = start(["ros2", "run", "quadruped_ros2_blackw", "sim_node", "--ros-args",
                 "-p", "viewer:=false", "-p", "realtime:=true", "-p", "status_period_s:=0.25",
                 "-p", f"scene:={scene}", "-p", "start:=raw",
                 "-p", f"spawn_x:={sx}", "-p", f"spawn_y:={sy}", "-p", f"spawn_z:={sz}",
                 "-p", f"spawn_yaw:={syaw}"], sim_log)
    rl = start(["ros2", "run", "rl_sar_blackw", "rl_sim", "--ros-args",
                "-p", "robot_name:=blackW", "-p", "policy_name:=flat"], rl_log)
    rclpy.init()
    pad = Pad()
    try:
        time.sleep(2.0)
        zero_buttons = [0] * 11
        zero_axes = [0.0] * 8
        # GetUp, then RL.
        pad.press([1] + [0] * 10, zero_axes)
        time.sleep(2.5)
        pad.press([0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 1.0])
        time.sleep(2.5)
        # Enter the fixed action.
        buttons = [0] * 11
        buttons[case["button"]] = 1
        axes = list(zero_axes)
        axes[case["axis_index"]] = case["axis"]
        pad.press(buttons, axes)
        time.sleep(1.5)
        # Hold a forward command while the fixed posture drives.
        pad.press(zero_buttons, [0.0, 0.4, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        time.sleep(9.0)
    finally:
        stop(rl)
        stop(sim)
        pad.destroy_node()
        rclpy.shutdown()
    sim_text = sim_log.read_text(encoding="utf-8", errors="replace")
    rl_text = rl_log.read_text(encoding="utf-8", errors="replace")
    frames = [dict(m.groupdict()) for m in STATUS_RE.finditer(sim_text)]
    entered = f"Entered RLFSMState{case['name']}" in rl_text
    if not frames:
        print("[FAIL] no sim status frames; see", sim_log)
        return 1
    final = frames[-1]
    print(f"frames={len(frames)} entered_behavior={entered} "
          f"final x={float(final['x']):.3f} y={float(final['y']):.3f} z={float(final['z']):.3f}")
    if args.case == "lowbar":
        ok = entered and float(final["y"]) > -8.95 and float(final["z"]) < 0.40
        print("[PASS]" if ok else "[FAIL]", "low-bar deployment crossing" if ok else "low-bar crossing not reached")
        return 0 if ok else 1
    # The narrow-band bridge ends at y=-1.0 (upper platform); require the fixed posture to
    # actually reach the far side, not merely move a little.
    crossed = (float(final["y"]) > -1.0 and 5.0 <= float(final["x"]) <= 6.4
               and float(final["z"]) >= 0.35)
    print("[PASS]" if crossed else "[FAIL]",
          "bridge fixed action crossed the narrow-band bridge" if crossed else "bridge crossing not reached")
    return 0 if crossed else 1


if __name__ == "__main__":
    raise SystemExit(main())
