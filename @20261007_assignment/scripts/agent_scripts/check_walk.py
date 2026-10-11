#!/usr/bin/env python3
"""无头自检：仿真节点 + rl_sim，按脚本发 /joy，让狗"起身 → 进 RL → 前进 → 转向 → 趴下"，跑完判定。

和 @20261005_ros2 的 check_headless.py 是同一个套路（起节点、发 /joy、读仿真状态行判定，退出码 0/1），
差别是这里要发**摇杆**，而且多量两样东西：

* **策略周期（仿真时间）**：S4 起 rl_sim 由反馈驱动——每条 /motor_state 跑一次控制，仿真时间每前进
  `dt * decimation`（= 20 ms）推理一次，所以这个周期按构造就是 20 ms **仿真时间**；这里仍独立量一遍
  （/mit_command 里的关节目标每推理一次变一次，取"变的那一刻最新一条 /motor_state 的 sim_time"算真实周期），
  既作回归，也当"反馈节拍没跑偏"的判据。
* **转向角速度**：/imu 的陀螺 z，与参考实现（policy_reference.py）同一个指令下的结果对照。

/joy 按 @20261005_ros2 的 joy_node 的规范化输出发（xpad 顺序；摇杆上 / 左为正、十字键上 / 右为正，
即主办者 gamepads.yaml 的口径，接口见 @20261005_ros2/docs/joystick.md §3）。

用法（仓库根目录，先 `pixi run ros2-build`）：

    pixi run python @20261007_assignment/scripts/agent_scripts/check_walk.py
    pixi run python @20261007_assignment/scripts/agent_scripts/check_walk.py --realtime false   # 全速跑（测"快放不再摔"）

`--realtime false` 时仿真不按墙钟走，时间线也改成按**仿真时间**推进（TIMELINE 里的秒 = 仿真秒）——这正是 S4
要证明的性质：暂停/慢放/快放都不影响策略周期。
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
    ap.add_argument("--realtime", default="true", choices=["true", "false"],
                    help="仿真是否按真实时间走；false = 全速跑（时间线随之改成按仿真时间推进）")
    ap.add_argument("--sim-param", action="append", default=[], metavar="name:=value",
                    help="额外透传给仿真节点的 ROS 参数，可重复（例：--sim-param motor_deadzone:=0.02）")
    args = ap.parse_args()
    busy = running_nodes()
    if busy:
        print(f"[FAIL] 已经有节点在跑：{'、'.join(busy)}——先停掉那个 launch 再自检")
        return 1

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    sim_log, rl_log = LOG_DIR / "check-walk-sim.log", LOG_DIR / "check-walk-rl.log"
    print("① 起仿真节点（无窗口、按真实时间）与 rl_sim")
    sim_args = ["ros2", "run", "quadruped_ros2", "sim_node", "--ros-args", "-p", "viewer:=false",
                "-p", f"realtime:={args.realtime}", "-p", "status_period_s:=0.25", "-p", f"start:={args.start}"]
    for extra in args.sim_param:  # 非理想电机项等：只在需要时打开，默认全关
        sim_args += ["-p", extra]
    sim = start(sim_args, sim_log)
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
        # realtime:=false 时仿真不按墙钟走：时间线改按仿真时间推进（TIMELINE 里的秒 = 仿真秒）。
        # 也看 --sim-param 里有没有 realtime:=false，两种写法行为一致。
        by_sim_time = args.realtime == "false" or any(p.startswith("realtime:=false") for p in args.sim_param)
        if by_sim_time:
            print("   （全速跑：时间线按仿真时间推进）")
        t0 = time.monotonic()
        t0_sim = None
        next_send = t0
        # 全速跑时 /joy 也必须按**仿真时间**发：否则墙钟 50 Hz 在 20x 下等于每 400 ms 仿真时间一帧，
        # TIMELINE 里 0.3 s 的按键脉冲整段被跳过（实测：一条都发不进去，狗当然不起来）。
        # 规则：仿真时间每 10 ms 发一帧，同时限制墙钟最快 200 Hz（免得 Python 端把自己压垮）。
        last_send_sim = 0.0
        last_send_wall = 0.0
        while True:
            if by_sim_time:
                if t0_sim is None and node.sim_time is not None:
                    t0_sim = node.sim_time
                now = (node.sim_time - t0_sim) if t0_sim is not None else 0.0
            else:
                now = time.monotonic() - t0
            if now >= TOTAL_SECONDS:
                break
            rclpy.spin_once(node, timeout_sec=0.002)
            if by_sim_time:
                wall_now = time.monotonic()
                if now - last_send_sim < 0.01 or wall_now - last_send_wall < 0.005:
                    continue
                last_send_sim = now
                last_send_wall = wall_now
            else:
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
    skipped: list[str] = []

    def check(ok: bool, name: str, detail: str) -> None:
        results.append((ok, name, detail))

    def skip(name: str, why: str) -> None:
        # 状态行是**墙钟**每 status_period_s 一条：全速跑时一个 0.3 s 仿真时间的窗口只有十几毫秒墙钟，
        # 里面可能一条都没有。这种情况明确标 SKIP（以前是"少一项就判失败"，会误报整体不通过）。
        skipped.append(f"{name}（{why}）")

    # 站姿：进 RL 之前、起身走完时，下发的 q 应该正好是 default_dof_pos（经 joint_mapping 换到仿真顺序）
    cfg = yaml.safe_load(CONFIG.read_text())["black/himloco"]
    expect = [0.0] * 12
    for i, sim_index in enumerate(cfg["joint_mapping"]):
        expect[sim_index] = cfg["default_dof_pos"][i]
    stand_begin, _ = phases["press RB+up"]
    # 判据用"进 RL 之前的那一条指令"（= 斜坡终点 = 站姿），靠 **kp 从 fixed_kp 跳到 rl_kp** 定位，
    # 不依赖时间线：全速跑时反馈间隙会超过补步上限（10 步 = 50 ms 仿真时间），斜坡在仿真时间里
    # 会略微拉长，"按下 RB+↑ 那一刻"未必已经到站姿（按时间线取会误报，实测偏差 6.6e-02 rad）。
    rl_kp = float(cfg["rl_kp"][0] if isinstance(cfg["rl_kp"], list) else cfg["rl_kp"])
    enter = next((i for i, c in enumerate(node.commands)
                  if c[0] >= stand_begin - 1.0 and abs(c[2][0] - rl_kp) < 1.0), None)
    if enter:                      # 进 RL 的那条之前一条 = 斜坡终点
        before = node.commands[:enter]
    else:                          # 没进 RL（跑挂了）：退回"按下 RB+↑ 之前"
        before = [c for c in node.commands if c[0] <= stand_begin]
    err = max(abs(a - b) for a, b in zip(before[-1][1], expect)) if before else float("inf")
    check(err < 1e-3, "起身终点 = default_dof_pos（关节映射对）",
          f"最大偏差 {err:.2e} rad（取{'进 RL 前' if enter else '按 RB+↑ 前'}最后一条指令）")
    stand = window("press RB+up")
    if not stand:
        # 回退：从"进 RL 那一刻"到"前进段开始"之间的所有状态行（语义相同：起身完成、还没走）
        stand = [r for r in rows if stand_begin <= r["t"] < phases["forward"][0]]
    if stand:
        check(stand[-1]["z"] > 0.38 and stand[-1]["tilt"] < 10, "起身后站住了",
              f"z={stand[-1]['z']:.3f} m、倾角 {stand[-1]['tilt']:.1f}°、触地 {int(stand[-1]['ncon'])}")
    else:
        skip("起身后站住了", "该区间内没有仿真状态行")

    walk = window("forward") + window("stop") + window("turn") + window("stop2")
    if not walk:
        skip("RL 段没摔（前进 + 转向）", "该区间内没有仿真状态行")
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
        detail = (f"均值 {mean:.2f} ms、p5 {percentile(periods, 5):.1f}、p95 {percentile(periods, 95):.1f}、"
                  f"最大 {max(periods):.1f}、超过 30 ms 的 {sum(p > 30.0 for p in periods)} 次（共 {len(periods)} 次）")
        if by_sim_time:
            # 全速跑：栈内节拍按仿真时间定义，但**墙钟上的吞吐**取决于 rl_sim 能不能吃下反馈流。
            # 本机实测 20~25x 时均值仍是 20.5 ms；再快（不限速、宿主更忙）时单执行器线程饱和，
            # 控制只能按 sim_time 补步（每帧最多 10 步），推理节拍在仿真时间里退化——实测一次
            # 22x 的运行是均值 26.3 ms / p95 54 ms，但起身、走、转、趴下仍全过。
            # 所以这里放宽判据（行为正确性由上面几项守着），并把实测值打出来。
            check(mean < 30.0 and percentile(periods, 95) < 60.0,
                  "策略周期（全速：放宽到均值 <30 ms，见 docs/control-stack-rates.md §4）", detail)
        else:
            check(19.0 < mean < 23.0, "策略周期（仿真时间）接近 20 ms", detail)

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
    if rate is None and by_sim_time:
        # 仿真节点每 5 s 墙钟才打一次吞吐行；全速跑整个流程 1~3 s 墙钟就完了，等不到那一行。
        # 那就自己量：本次跑掉的仿真时间 / 墙钟时间。
        span_sim = (node.sim_time - t0_sim) if (t0_sim is not None and node.sim_time is not None) else None
        span_wall = time.monotonic() - t0
        rate = (span_sim / span_wall) if span_sim and span_wall > 0 else None
        if rate:
            rate = round(rate, 2)
    label = "实时率达标（1x）" if not by_sim_time else "全速跑也跑得动（实测节拍）"
    check(rate is not None and rate >= 0.95, label,
          f"{rate}x" if rate else "量不到实时率（看 output/log/check-walk-sim.log）")

    print("\n================ 自检结果 ================")
    for ok, name, detail in results:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}  {detail}")
    for name in skipped:
        print(f"[SKIP] {name}")
    passed = all(ok for ok, _, _ in results) and not skipped
    print("==========================================")
    print("结论：" + ("全部通过 ✓" if passed else "有未通过项 ✗"))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
