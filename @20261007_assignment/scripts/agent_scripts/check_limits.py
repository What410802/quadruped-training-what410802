#!/usr/bin/env python3
"""量"限位余量"：跑狗的时候另开一个终端，看我们离三层限位各有多远。

三层限位（详见 docs/safety-limits.md）：

* `library/core` 的 `ComputeOutput()`：`output_dof_tau` 被夹到 `torque_limits`（±33.5 N·m）——但它只进 CSV/队列，**不下发**；
* `@20261005_ros2` 的电机模型 `motor.hpp: Torque()`：`clamp(τ, ±tau_max)`，`tau_max` 默认 **20 N·m**（`sim_node` 的 `tau_max` 参数）；
* MJCF：`<motor ctrllimited="true" ctrlrange="-20 20">`（MuJoCo 再夹一次 `d->ctrl`）+ 关节 `limited="true" range=...`（**软**约束）。

这个脚本订阅 `/motor_state`（关节角、实测力矩）与 `/imu`，在退出时打印：
① 实测力矩 |τ| 的峰值与"贴着 ±20"的采样比例（= 限幅被打满的程度）；
② 每个关节的 q 相对 MJCF `range` 的余量（最坏一个 + 是哪个关节）；
③ 关节角速度 |dq| 的峰值（MuJoCo 不限制速度，只有限位软约束）。

用法（仓库根目录，**先让狗跑起来**：仿真节点 + rl_sim，再发 /joy）：

    pixi run python @20261007_assignment/scripts/agent_scripts/check_limits.py --seconds 20
"""

from __future__ import annotations

import argparse
import re
import statistics
import sys
from pathlib import Path

import rclpy
from quadruped_ros2.msg import MitCommand, MotorState
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data

ROOT = Path(__file__).resolve().parents[3]
MODEL = ROOT / "@20261005_ros2" / "models" / "black_description.xml"
CLAMP = 20.0   # motor.hpp 的 kDefaultTauMax / MJCF 的 ctrlrange


def joint_ranges() -> list[tuple[str, float, float]]:
    """从 MJCF 里读 12 个关节的 range（顺序 = 模型里的声明顺序 = 执行器顺序）。"""
    text = MODEL.read_text(encoding="utf-8")
    out = []
    for m in re.finditer(r'<joint name="([A-Za-z0-9_]+)"[^>]*range="([-0-9. ]+)"', text):
        lo, hi = (float(x) for x in m.group(2).split())
        out.append((m.group(1), lo, hi))
    return out


class Limits(Node):
    def __init__(self) -> None:
        super().__init__("check_limits")
        self.tau_abs: list[float] = []
        self.dq_abs: list[float] = []
        self.q: list[list[float]] = []
        self.tau: list[list[float]] = []
        self.dq: list[list[float]] = []
        self.kp: list[float] = []      # 每个采样当时的 kp：80 = 起身/趴下斜坡，40 = RL
        self.last_kp = 0.0
        # /motor_state 是 best_effort 发的（500 Hz、只要最新）：默认 reliable 订阅者收不到，
        # 必须用 sensor 数据 QoS（porting.md §4 的 QoS 坑，实测会打印 incompatible QoS）。
        self.create_subscription(MotorState, "motor_state", self.on_state, qos_profile_sensor_data)
        self.create_subscription(MitCommand, "mit_command", self.on_cmd, qos_profile_sensor_data)

    def on_cmd(self, msg: MitCommand) -> None:
        self.last_kp = float(msg.kp[0]) if len(msg.kp) else 0.0

    def on_state(self, msg: MotorState) -> None:
        self.tau.append(list(msg.tau))
        self.q.append(list(msg.q))
        self.dq.append(list(msg.dq))
        self.tau_abs.extend(abs(t) for t in msg.tau)
        self.dq_abs.extend(abs(w) for w in msg.dq)
        self.kp.append(self.last_kp)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=20.0)
    args = ap.parse_args()

    rclpy.init()
    node = Limits()
    print(f"采样 {args.seconds:.0f} s（跑狗的时候看）……")
    end = node.get_clock().now().nanoseconds + int(args.seconds * 1e9)
    while node.get_clock().now().nanoseconds < end:
        rclpy.spin_once(node, timeout_sec=0.1)
    node.destroy_node()
    rclpy.shutdown()

    if not node.tau:
        print("[FAIL] 没收到 /motor_state（仿真节点起来了吗？）")
        return 1

    print(f"\n样本 {len(node.tau)} 条（{len(node.tau_abs)} 个电机采样）")
    peak = max(node.tau_abs)
    sat = sum(1 for t in node.tau_abs if t >= CLAMP - 0.01) / len(node.tau_abs)
    print(f"① 实测力矩 |τ| 峰值 {peak:.2f} N·m（限幅 ±{CLAMP:.0f}）；贴着限幅的采样 {sat * 100:.2f}%")
    print(f"   均值 {statistics.fmean(node.tau_abs):.2f}、p95 {sorted(node.tau_abs)[int(0.95 * len(node.tau_abs))]:.2f} N·m")

    ranges = joint_ranges()
    worst = None
    for j, (name, lo, hi) in enumerate(ranges):
        qs = [row[j] for row in node.q]
        margin = min(min(q - lo for q in qs), min(hi - q for q in qs))
        inside = lo - 0.02 <= min(qs) and max(qs) <= hi + 0.02
        if worst is None or margin < worst[1]:
            worst = (name, margin, min(qs), max(qs), inside)
    print(f"② 关节角余量最小的是 {worst[0]}：{worst[1] * 1000:.1f} mrad（q ∈ [{worst[2]:.3f}, {worst[3]:.3f}]，"
          f"{'全程在 range 内' if worst[4] else '⚠ 越界'}）")
    for j, (name, lo, hi) in enumerate(ranges):
        qs = [row[j] for row in node.q]
        out = [k for k, q in enumerate(qs) if q < lo or q > hi]
        if out:
            rl = sum(1 for k in out if 39.0 < node.kp[k] < 41.0)
            print(f"   ⚠ {name} 越界：{len(out)}/{len(qs)} 采样（{100.0 * len(out) / len(qs):.1f}%），"
                  f"越界时 {rl} 条在 RL（kp=40）、{len(out) - rl} 条在斜坡（kp=80），"
                  f"最大超出 {max(max(lo - min(qs), 0.0), max(max(qs) - hi, 0.0)) * 1000:.0f} mrad")
    print(f"③ 关节角速度 |dq| 峰值 {max(node.dq_abs):.2f} rad/s（MuJoCo 不限速度，只靠限位软约束与电机力矩）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
