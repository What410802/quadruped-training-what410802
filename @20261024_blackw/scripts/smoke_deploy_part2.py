#!/usr/bin/env python3
"""Headless per-level Part2 deploy smoke: sim_node + rl_sim, joystick/nav commands, judge v5.

This is the missing F2 tool from the deploy audit: the only previous self-check
(check_walk_blackw.py) exercised flat-ground behaviour on 7 items and had zero
coverage of the 20 Part2 ability levels.  This script:

1. launches the deploy stack headless for one Part2 level at a time
   (scene + spawn from scenes/blackW/part2_levels.json);
2. presses GetUp (A) and Enter-RL (RB+D-pad up), toggles navigation mode (X),
   then publishes the level's official command on /cmd_vel for its `seconds`;
3. parses the sim_node status lines (base x/y/z/tilt + 4 wheel x/z world coords)
   and feeds them into the authoritative judge predicate (eval_blackw_part2.py);
4. prints one PASS/FAIL per level and writes JSON.  Exit code 0 only if every
   selected level passes.

Usage (from repo root, after `pixi run ros2-build`):
    pixi run python @20261024_blackw/scripts/smoke_deploy_part2.py \
        --policy comp_bc_v5 --only high_platform_10cm --realtime false
    pixi run python @20261024_blackw/scripts/smoke_deploy_part2.py --policy comp_bc_v5
"""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import rclpy
import yaml
from quadruped_ros2_blackw.msg import MotorState
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Joy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_blackw_part2 import Part2OfficialJudge  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
TASK = ROOT / "@20261024_blackw"
SCENE_DIR = TASK / "ws/src/rl_sar_blackw/scenes/blackW"
POLICY_ROOT = TASK / "ws/src/rl_sar_blackw/policy/blackW"
LOG_DIR = TASK / "output" / "smoke-deploy"
WHEEL_RADIUS = 0.103
JOY_SCALE = 1.5
STATUS_RE = re.compile(
    r"t=(?P<t>[\d.]+) x=(?P<x>[\d.-]+) y=(?P<y>[\d.-]+) z=(?P<z>[\d.-]+) "
    r"tilt=(?P<tilt>[\d.-]+) ncon=\d+ cmd=(?P<cmd>\w+)"
    r"(?: wx=(?P<wx>[\d.,-]+) wz=(?P<wz>[\d.,-]+))?")
BUTTONS = ["A", "B", "X", "Y", "LB", "RB", "Back", "Start", "Guide", "LS", "RS"]


def _popen(args: list[str], log: Path) -> subprocess.Popen:
    print("  $ " + " ".join(args))
    fh = log.open("w", encoding="utf-8")
    return subprocess.Popen(args, stdout=fh, stderr=subprocess.STDOUT, start_new_session=True)


def _stop(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGINT)
            proc.wait(timeout=8)
        except (subprocess.TimeoutExpired, ProcessLookupError, PermissionError):
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass


def running_nodes() -> list[str]:
    found = []
    for entry in Path("/proc").glob("[0-9]*"):
        try:
            exe = os.readlink(entry / "exe").replace(" (deleted)", "")
        except OSError:
            continue
        name = os.path.basename(exe)
        if (name == "sim_node" and "quadruped_ros2" in exe) or (name == "rl_sim" and "rl_sar" in exe):
            found.append(f"{name}(pid {entry.name})")
    return found


class Recorder(Node):
    def __init__(self) -> None:
        super().__init__("smoke_deploy_part2")
        self.joy_pub = self.create_publisher(Joy, "joy", 1)
        self.create_subscription(MotorState, "motor_state", self._on_state, qos_profile_sensor_data)
        self.sim_time: float | None = None

    def _on_state(self, msg: MotorState) -> None:
        self.sim_time = float(msg.sim_time)

    def send_joy(self, buttons: list[str], axes: dict[int, float]) -> None:
        msg = Joy()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.axes = [0.0] * 8
        msg.axes[2] = msg.axes[5] = -1.0  # triggers released (joy_node convention)
        for i, v in axes.items():
            msg.axes[i] = v
        msg.buttons = [1 if b in buttons else 0 for b in BUTTONS] + [0]
        self.joy_pub.publish(msg)


def parse_status(log: Path) -> list[dict]:
    rows = []
    if not log.is_file():
        return rows
    for raw in log.read_text(encoding="utf-8", errors="replace").splitlines():
        m = STATUS_RE.search(raw)
        if not m:
            continue
        row = {k: float(m.group(k)) for k in ("t", "x", "y", "z", "tilt")}
        row["cmd"] = m.group("cmd")
        if m.group("wx") and m.group("wz"):
            row["wx"] = np.array([float(v) for v in m.group("wx").split(",")])
            row["wz"] = np.array([float(v) for v in m.group("wz").split(",")])
        else:
            row["wx"] = row["wz"] = None
        rows.append(row)
    return rows


def run_level(level: dict, judge_level: dict, policy: str, realtime: bool) -> dict:
    key = level["key"]
    scene = SCENE_DIR / level["scene"]
    spawn = level.get("spawn", level.get("start", [0.0, 0.0, 0.5, 0.0]))
    seconds = float(level.get("seconds", 8.0))
    command = list(level.get("command", [0.5, 0.0, 0.0]))
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    sim_log = LOG_DIR / f"{key}-{policy}-sim.log"
    rl_log = LOG_DIR / f"{key}-{policy}-rl.log"
    if not scene.is_file():
        return {"level": key, "status": "fail", "reason": f"scene missing: {scene}"}

    sim_args = ["ros2", "run", "quadruped_ros2_blackw", "sim_node", "--ros-args",
                "-p", "viewer:=false", "-p", f"realtime:={'true' if realtime else 'false'}",
                "-p", "status_period_s:=0.02", "-p", "start:=raw",
                "-p", f"scene:={scene}",
                "-p", f"spawn_x:={spawn[0]}", "-p", f"spawn_y:={spawn[1]}",
                "-p", f"spawn_z:={spawn[2]}", "-p", f"spawn_yaw:={spawn[3]}"]
    rl_args = ["ros2", "run", "rl_sar_blackw", "rl_sim", "--ros-args",
               "-p", "robot_name:=blackW", "-p", f"policy_name:={policy}"]
    sim = _popen(sim_args, sim_log)
    rl = _popen(rl_args, rl_log)
    rclpy.init()
    node = Recorder()
    nav_on = False
    rl_start_sim: float | None = None
    result = {"level": key, "policy": policy, "status": "fail", "reason": "incomplete"}
    try:
        deadline = time.monotonic() + 60.0
        while node.sim_time is None and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.05)
        if node.sim_time is None:
            return {"level": key, "status": "fail",
                    "reason": f"no /motor_state within 60 s (see {rl_log})"}
        t0 = node.sim_time
        # sim-time timeline: GetUp, Enter-RL, then the level's official command via
        # joystick axes (same path as a human operator; JOY_SCALE=1.5 at full stick).
        getup = (0.5, 0.9)
        enter = (2.0, 2.4)
        cmd_start = 3.0
        cmd_end = cmd_start + seconds
        axes_cmd = {0: command[1] / JOY_SCALE, 1: command[0] / JOY_SCALE,
                    3: command[2] / JOY_SCALE}
        t_cmd_sim: float | None = None
        wall_deadline = time.monotonic() + 300.0
        while True:
            if time.monotonic() > wall_deadline:
                result["reason"] = "wall-clock guard hit"
                break
            rclpy.spin_once(node, timeout_sec=0.002)
            now = node.sim_time - t0
            buttons, axes = [], {}
            if getup[0] <= now < getup[1]:
                buttons = ["A"]
            elif enter[0] <= now < enter[1]:
                buttons, axes = ["RB"], {7: 1.0}
            elif now >= cmd_start:
                axes = dict(axes_cmd)
            node.send_joy(buttons, axes)
            if rl_start_sim is None and now >= cmd_start:
                rl_start_sim = node.sim_time
                t_cmd_sim = node.sim_time
            if rl_start_sim is not None and now >= cmd_end + 1.5:
                break
        # stop sending the command; the judge uses the recorded interval only.
        try:
            for _ in range(10):
                node.send_joy([], {})
                rclpy.spin_once(node, timeout_sec=0.005)
        except Exception:
            pass
    finally:
        node.destroy_node()
        try:
            rclpy.shutdown()
        except Exception:
            pass
        _stop(rl)
        _stop(sim)

    rows = parse_status(sim_log)
    ok_rows = [r for r in rows if r["cmd"] == "ok"]
    if not ok_rows:
        result["reason"] = f"no status rows with cmd=ok (see {sim_log})"
        return result
    # Attempt starts when the level command starts, not when RL was entered
    # (GetUp/Enter-RL happen in place).
    if t_cmd_sim is not None:
        ok_rows = [r for r in ok_rows if r["t"] >= t_cmd_sim]
    if not ok_rows:
        result["reason"] = f"no status rows after command start (see {sim_log})"
        return result
    t_rl = ok_rows[0]["t"]
    judge = Part2OfficialJudge(judge_level)
    fed = 0
    for r in ok_rows:
        if r["wx"] is None or r["wz"] is None:
            continue
        judge.update(r["t"] - t_rl, np.array([r["x"], r["y"], r["z"]]), r["tilt"],
                     wheel_x=r["wx"], wheel_z=r["wz"] - WHEEL_RADIUS)
        fed += 1
    verdict = judge.finalize("timeout" if fed else "no_feed")
    last = ok_rows[-1]
    out = {"level": key, "category": level.get("category"), "policy": policy,
           "status": verdict["status"], "reason": verdict.get("reason", ""),
           "fed_rows": fed, "last_base": [round(last["x"], 3), round(last["y"], 3),
                                          round(last["z"], 3)],
           "judge_detail": verdict.get("detail", {}),
           "sim_log": str(sim_log), "rl_log": str(rl_log)}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--policy", default="comp_bc_v5",
                    help="policy dir under policy/blackW (e.g. comp_bc_v5)")
    ap.add_argument("--levels", type=Path, default=SCENE_DIR / "part2_levels.json")
    ap.add_argument("--judge-levels", type=Path, default=SCENE_DIR / "part2_official_levels.json")
    ap.add_argument("--only", action="append", default=[], help="level key(s); default = all")
    ap.add_argument("--realtime", choices=["true", "false"], default="false")
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args()

    cfg_path = POLICY_ROOT / args.policy / "config.yaml"
    if not cfg_path.is_file():
        print(f"[FAIL] missing policy config: {cfg_path}")
        return 1
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    if list(cfg) != [f"blackW/{args.policy}"]:
        print(f"[FAIL] top-level key {list(cfg)} != ['blackW/{args.policy}']")
        return 1
    if not (POLICY_ROOT / args.policy / "policy.pt").is_file():
        print(f"[FAIL] missing policy.pt in {cfg_path.parent}")
        return 1
    busy = running_nodes()
    if busy:
        print(f"[FAIL] nodes already running: {', '.join(busy)}; stop them first")
        return 1

    deploy = json.loads(args.levels.read_text(encoding="utf-8"))
    official = json.loads(args.judge_levels.read_text(encoding="utf-8"))
    official = official["levels"] if isinstance(official, dict) and "levels" in official else official
    by_key = {e["key"]: e for e in official}
    selected = [e for e in deploy if not args.only or e["key"] in args.only]
    if not selected:
        print(f"[FAIL] no matching level; available: {[e['key'] for e in deploy]}")
        return 1
    results = []
    realtime = args.realtime == "true"
    for level in selected:
        print(f"\n== {level['key']} ({level.get('category')}) ==")
        try:
            res = run_level(level, by_key[level["key"]], args.policy, realtime)
        except Exception as exc:  # keep the remaining levels running
            res = {"level": level["key"], "status": "fail", "reason": f"exception: {exc}"}
        results.append(res)
        print(f"  -> {res['status'].upper()} {res.get('reason', '')}")
    passed = sum(1 for r in results if r["status"] == "success")
    payload = {"policy": args.policy, "realtime": args.realtime,
               "levels_total": len(results), "levels_passed": passed,
               "levels_failed": len(results) - passed, "results": results}
    print(f"\n{passed}/{len(results)} levels passed")
    if args.json:
        args.json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
        print(f"wrote {args.json}")
    return 0 if results and passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
