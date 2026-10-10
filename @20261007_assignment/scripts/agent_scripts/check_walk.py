#!/usr/bin/env python3
"""无头自检：仿真节点 + rl_sim，按脚本发 /joy，让狗"起身 → 进 RL → 前进 → 转向 → 趴下"，跑完判定。

和 @20261005_ros2 的 check_headless.py 是同一个套路（起节点、发 /joy、读仿真状态行判定，退出码 0/1），
差别是这里要发**摇杆**，而且多量两样东西：

* **策略周期（仿真时间）**：rl_sim 按墙钟每 20 ms 推理一次；/mit_command 里的关节目标每推理一次才变，
  用"变的那一刻最新一条 /motor_state 的 sim_time"量出它在仿真时间里的真实周期——这是
  docs/experiments.md 里"墙钟够不够用"的那组输入；
* **转向角速度**：/imu 的陀螺 z，与参考实现（policy_reference.py）同一个指令下的结果对照。

/joy 按 @20261005_ros2 的 joy_node 的规范化输出发（xpad 顺序；摇杆上 / 左为正、十字键上 / 右为正，
即主办者 gamepads.yaml 的口径，接口见 @20261005_ros2/docs/joystick.md §3）。

用法（仓库根目录，先 `pixi run ros2-build`）：

    pixi run python @20261007_assignment/scripts/agent_scripts/check_walk.py
"""

from __future__ import annotations

import argparse
import os
import re
import signal
import statistics
import subprocess
import time
from pathlib import Path

import rclpy
import yaml
from quadruped_ros2.msg import MitCommand, MotorState
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Imu, Joy

TASK = Path(__file__).resolve().parents[2]  # @20261007_assignment/
LOG_DIR = TASK / "output" / "log"
CONFIG = TASK / "ws/src/rl_sar/policy/black/himloco/config.yaml"

STATUS_RE = re.compile(r"^t=(?P<t>[\d.]+) z=(?P<z>[\d.-]+) tilt=(?P<tilt>[\d.-]+) ncon=(?P<ncon>\d+)")
RATE_RE = re.compile(r"= (?P<rate>[\d.]+)x 实时")

JOY_SCALE = 1.5  # rl_sim 的 joy_command_scale 默认值：摇杆满偏 = 1.5 m/s（或 rad/s）
VX = 1.0  # 前进段的速度指令 [m/s]
WZ = 1.0  # 转向段的角速度指令 [rad/s]

# 时间线（秒，从 rl_sim 开始发 /mit_command 算起）：(起, 止, 段名, 按键, 轴)
# 轴按 joy_node 的规范化正负号写：左摇杆上推 = axes[1] 为正；右摇杆左推（左转）= axes[3] 为正；十字键上 = axes[7] = +1。
TIMELINE = [
    (1.0, 1.3, "press A", ["A"], {}),
    (5.0, 5.3, "press RB+up", ["RB"], {7: 1.0}),
    (7.0, 17.0, "forward", [], {1: VX / JOY_SCALE}),
    (17.0, 19.0, "stop", [], {}),
    (19.0, 25.0, "turn", [], {3: WZ / JOY_SCALE}),
    (25.0, 27.0, "stop2", [], {}),
    (27.0, 27.3, "press B", ["B"], {}),
]
TOTAL_SECONDS = 32.0
BUTTONS = ["A", "B", "X", "Y", "LB", "RB", "Back", "Start", "Guide", "LS", "RS"]


class Recorder(Node):
    def __init__(self) -> None:
        super().__init__("check_walk")
        self.joy_pub = self.create_publisher(Joy, "joy", 1)
        self.create_subscription(MotorState, "motor_state", self.on_state, qos_profile_sensor_data)
        self.create_subscription(MitCommand, "mit_command", self.on_command, qos_profile_sensor_data)
        self.create_subscription(Imu, "imu", self.on_imu, qos_profile_sensor_data)
        self.sim_time = None
        self.states: list[tuple[float, list[float]]] = []  # (sim_time, q)
        self.commands: list[tuple[float, list[float], list[float]]] = []  # (sim_time, q, kp)
        self.gyro_z: list[tuple[float, float]] = []

    def on_state(self, msg: MotorState) -> None:
        self.sim_time = msg.sim_time
        self.states.append((msg.sim_time, list(msg.q)))

    def on_command(self, msg: MitCommand) -> None:
        if self.sim_time is not None:
            self.commands.append((self.sim_time, list(msg.q), list(msg.kp)))

    def on_imu(self, msg: Imu) -> None:
        if self.sim_time is not None:
            self.gyro_z.append((self.sim_time, msg.angular_velocity.z))

    def send_joy(self, buttons: list[str], axes: dict[int, float]) -> None:
        msg = Joy()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.axes = [0.0] * 8
        msg.axes[2] = msg.axes[5] = -1.0  # 扳机松开 = -1（与 joy_node 一致）
        for index, value in axes.items():
            msg.axes[index] = value
        msg.buttons = [1 if name in buttons else 0 for name in BUTTONS] + [0]
        self.joy_pub.publish(msg)


def start(args: list[str], log: Path) -> subprocess.Popen:
    print(f"  $ {' '.join(args)}  > {log.relative_to(TASK)}")
    handle = log.open("w", encoding="utf-8")
    return subprocess.Popen(args, stdout=handle, stderr=subprocess.STDOUT, start_new_session=True)


def stop(proc: subprocess.Popen) -> None:
    """连同进程组一起停（`ros2 run` 只是壳，节点是它的子进程）。"""
    if proc.poll() is None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGINT)
            proc.wait(timeout=5)
        except (subprocess.TimeoutExpired, ProcessLookupError, PermissionError):
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass


def running_nodes() -> list[str]:
    """已经在跑的同名节点会和自检抢话题，先查出来（不替人杀）。"""
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


def percentile(values: list[float], p: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, int(round(p / 100.0 * (len(s) - 1))))]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--start", default="rest", help="仿真起点：rest（趴卧 keyframe，默认）/ raw（模型原姿态落下）")
    args = ap.parse_args()
    busy = running_nodes()
    if busy:
        print(f"[FAIL] 已经有节点在跑：{'、'.join(busy)}——先停掉那个 launch 再自检")
        return 1

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    sim_log, rl_log = LOG_DIR / "check-walk-sim.log", LOG_DIR / "check-walk-rl.log"
    print("① 起仿真节点（无窗口、按真实时间）与 rl_sim")
    sim = start(["ros2", "run", "quadruped_ros2", "sim_node", "--ros-args", "-p", "viewer:=false",
                 "-p", "realtime:=true", "-p", "status_period_s:=0.25", "-p", f"start:={args.start}"], sim_log)
    rl = start(["ros2", "run", "rl_sar", "rl_sim"], rl_log)

    rclpy.init()
    node = Recorder()
    phases: dict[str, tuple[float, float]] = {}  # 段名 → (起, 止) 仿真时间
    try:
        deadline = time.monotonic() + 30.0
        while not node.commands and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.05)
        if not node.commands:
            print("[FAIL] 30 s 内没收到 rl_sim 的 /mit_command（看 output/log/check-walk-rl.log）")
            return 1
        print("② 按时间线发 /joy：" + " → ".join(name for _, _, name, _, _ in TIMELINE))
        t0 = time.monotonic()
        next_send = t0
        while (now := time.monotonic() - t0) < TOTAL_SECONDS:
            rclpy.spin_once(node, timeout_sec=0.002)
            if time.monotonic() < next_send:
                continue
            next_send += 0.02  # 50 Hz
            buttons, axes = [], {}
            for begin, end, name, b, a in TIMELINE:
                if begin <= now < end:
                    buttons, axes = b, a
                    sim_now = node.sim_time or 0.0
                    first, _ = phases.get(name, (sim_now, sim_now))
                    phases[name] = (first, sim_now)
            node.send_joy(buttons, axes)
    finally:
        node.destroy_node()
        rclpy.shutdown()
        stop(rl)
        stop(sim)

    rows = []
    rate = None
    for line in sim_log.read_text(encoding="utf-8", errors="replace").splitlines():
        if m := STATUS_RE.match(line.strip()):
            rows.append({k: float(v) for k, v in m.groupdict().items()})
        if m := RATE_RE.search(line):
            rate = float(m.group("rate"))

    def window(name: str, skip: float = 0.0) -> list[dict]:
        begin, end = phases[name]
        return [r for r in rows if begin + skip <= r["t"] <= end]

    results: list[tuple[bool, str, str]] = []

    def check(ok: bool, name: str, detail: str) -> None:
        results.append((ok, name, detail))

    # 站姿：进 RL 之前、起身走完时，下发的 q 应该正好是 default_dof_pos（经 joint_mapping 换到仿真顺序）
    cfg = yaml.safe_load(CONFIG.read_text())["black/himloco"]
    expect = [0.0] * 12
    for i, sim_index in enumerate(cfg["joint_mapping"]):
        expect[sim_index] = cfg["default_dof_pos"][i]
    stand_begin, _ = phases["press RB+up"]
    before = [c for c in node.commands if c[0] <= stand_begin]
    err = max(abs(a - b) for a, b in zip(before[-1][1], expect)) if before else float("inf")
    check(err < 1e-3, "起身终点 = default_dof_pos（关节映射对）", f"最大偏差 {err:.2e} rad")
    stand = window("press RB+up")
    if stand:
        check(stand[-1]["z"] > 0.38 and stand[-1]["tilt"] < 10, "起身后站住了",
              f"z={stand[-1]['z']:.3f} m、倾角 {stand[-1]['tilt']:.1f}°、触地 {int(stand[-1]['ncon'])}")

    walk = window("forward") + window("stop") + window("turn") + window("stop2")
    if walk:
        z_min, tilt_max = min(r["z"] for r in walk), max(r["tilt"] for r in walk)
        check(z_min > 0.3 and tilt_max < 20, "RL 段没摔（前进 + 转向）",
              f"z 最低 {z_min:.3f} m、倾角最大 {tilt_max:.1f}°")

    # 策略周期：RL 段里关节目标每变一次 = 推理一次
    rl_begin, rl_end = phases["forward"][0], phases["stop2"][1]
    changes = []
    last_q = None
    for t, q, kp in node.commands:
        if rl_begin <= t <= rl_end:
            if last_q is not None and q != last_q:
                changes.append(t)
            last_q = q
    periods = [1000.0 * (b - a) for a, b in zip(changes, changes[1:])]
    if periods:
        mean = statistics.fmean(periods)
        check(19.0 < mean < 23.0, "策略周期（仿真时间）接近 20 ms",
              f"均值 {mean:.2f} ms、p5 {percentile(periods, 5):.1f}、p95 {percentile(periods, 95):.1f}、"
              f"最大 {max(periods):.1f}、超过 30 ms 的 {sum(p > 30.0 for p in periods)} 次（共 {len(periods)} 次）")

    begin, end = phases["turn"]
    wz = [g for t, g in node.gyro_z if end - 3.0 <= t <= end]
    if wz:
        mean_wz = statistics.fmean(wz)
        check(mean_wz > 0.7 * WZ, f"转向跟得上指令 {WZ} rad/s", f"最后 3 s 陀螺 z 均值 {mean_wz:.3f} rad/s")

    # B：rl_sar 的 GetDown 是"把关节目标推回到**进 GetUp 那一刻**的关节角"（上游 go2 的语义），
    # 推完转阻尼（Passive，kp = 0，q 不再改）。所以比关节角，不比高度：raw 起点按 A 时狗还在往下掉，
    # 那一刻的高度是瞬态，复不了（实测两次 0.325 / 0.290 m），关节角才是 GetDown 真正的目标。
    up = next((c for c in node.commands if c[2][0] > 0.0), None)  # 第一条 kp > 0 = 进了 GetUp
    passive = "Switch from RLFSMStateGetDown to RLFSMStatePassive" in rl_log.read_text(errors="replace")
    if up and node.commands:
        q_up = [s for s in node.states if s[0] <= up[0]][-1][1]
        q_final = node.commands[-1][1]
        err = max(abs(a - b) for a, b in zip(q_final, q_up))
        check(err < 0.02 and passive, "B 之后回到起身前的姿态并转阻尼",
              f"最终关节目标与进 GetUp 时的关节角最大差 {err:.4f} rad、{'已' if passive else '未'}进 Passive")
    check(rate is not None and rate >= 0.95, "实时率达标", f"{rate}x" if rate else "日志里没有实时率")

    print("\n================ 自检结果 ================")
    for ok, name, detail in results:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}  {detail}")
    passed = all(ok for ok, _, _ in results) and len(results) >= 7
    print("==========================================")
    print("结论：" + ("全部通过 ✓" if passed else "有未通过项 ✗"))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
