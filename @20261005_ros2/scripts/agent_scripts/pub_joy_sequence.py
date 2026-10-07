#!/usr/bin/env python3
"""按脚本发 /joy 的无头测试工具（不接手柄，直接把按键序列打进 ROS 2）。

用途：没有手柄 / 没有 /dev/input 权限时，也能把"手柄 → 控制器 → 仿真"这条链路整条跑一遍。
做法与主办者仓库的 quadruped_control/scripts/test/ros2_headless_test.py 一致：它也是在测试里
直接 publish_joy(buttons=...)，而不是去伪造一个设备——本任务把它固化成一个小工具。

    pixi run python @20261005_ros2/scripts/agent_scripts/pub_joy_sequence.py --seconds 12
    pixi run python @20261005_ros2/scripts/agent_scripts/pub_joy_sequence.py --sequence "1:A,6:B,8:X,9:A"

序列写法：`时刻:动作`（时刻是启动后的秒数，动作 = A/B/X 单键，或 `none` 表示松开）。
默认序列 1:A,6:B,8:X,9:A 正好是"起身 → 趴下 → 复位 → 再起身"。
按下的键只持续 `--press-seconds`（默认 0.2 s），因为控制器认的是**按下沿**（长按不会重复触发）。

注意：真手柄请用 joy_node；本工具是**测试替身**，不检查"谁在用设备"。
"""

from __future__ import annotations

import time

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Joy

# A/B/X/Y/LB/RB/Back/Start/Guide/LS/RS → buttons[0..10]（与 joy_node 一致），第 12 个恒 0
BUTTONS = ["A", "B", "X", "Y", "LB", "RB", "Back", "Start", "Guide", "LS", "RS"]
BUTTON_INDEX = {name: index for index, name in enumerate(BUTTONS)}
AXIS_COUNT = 8
BUTTON_COUNT = 12

DEFAULT_SEQUENCE = "1:A,6:B,8:X,9:A"


def parse_sequence(text: str) -> list[tuple[float, str]]:
    steps = []
    for item in text.split(","):
        item = item.strip()
        if not item:
            continue
        when, _, action = item.partition(":")
        steps.append((float(when), action.strip().upper()))
    steps.sort()
    return steps


class SequencePublisher(Node):
    def __init__(self, topic: str) -> None:
        super().__init__("pub_joy_sequence")
        # reliable：与控制器节点的 /joy 订阅一致（它把 /joy 当"命令"而不是传感器流）
        self.publisher = self.create_publisher(Joy, topic, 1)

    def send(self, pressed: str | None) -> None:
        msg = Joy()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "joy_connected:pub_joy_sequence"
        msg.axes = [0.0] * AXIS_COUNT
        msg.buttons = [0] * BUTTON_COUNT
        if pressed and pressed in BUTTON_INDEX:
            msg.buttons[BUTTON_INDEX[pressed]] = 1
        self.publisher.publish(msg)

    def wait_for_subscriber(self, timeout_s: float) -> bool:
        """等到有人订阅 /joy 再开始计时。

        为什么必须等：ROS 2 的发布/订阅要**先发现再通信**，而 `/joy` 是 reliable + keep_last(1)。
        控制器那边同时被 500 Hz 的 /motor_state 打着，实测发现能拖到几秒；发现还没完成时发出的
        那些"按键帧"直接丢光（发布者的历史只有 1 条），于是"第一次按 A"就丢了——自检里表现为
        "狗只起来一次"。这个坑实测过：不加载时 3/3 都能收到，带 500 Hz 负载时第一次会丢。
        """
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self.publisher.get_subscription_count() > 0:
                self.get_logger().info(
                    f"/{self.publisher.topic_name.split('/')[-1]} 已有 {self.publisher.get_subscription_count()} 个订阅者，开始计时"
                )
                return True
            rclpy.spin_once(self, timeout_sec=0.05)
        self.get_logger().warning(f"等了 {timeout_s:.1f} s 也没人订阅，仍然开始发（可能白按）")
        return False


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="按脚本发 /joy（无头测试用）")
    parser.add_argument("--sequence", default=DEFAULT_SEQUENCE, help="形如 1:A,6:B,8:X,9:A")
    parser.add_argument("--topic", default="joy")
    parser.add_argument("--press-seconds", type=float, default=0.2, help="每次按下持续多久")
    parser.add_argument("--seconds", type=float, default=None, help="总共发多久；默认到最后一个动作 + 2 s")
    parser.add_argument("--rate-hz", type=float, default=50.0, help="按住期间的发送频率")
    parser.add_argument("--wait-subscriber", type=float, default=10.0,
                        help="开始计时前最多等多少秒让订阅者连上（0 = 不等）；见下面 wait_for_subscriber 的注释")
    args = parser.parse_args()

    steps = parse_sequence(args.sequence)
    total = args.seconds if args.seconds is not None else (steps[-1][0] if steps else 0.0) + 2.0

    rclpy.init()
    node = SequencePublisher(args.topic)
    if args.wait_subscriber > 0.0:
        node.wait_for_subscriber(args.wait_subscriber)
    node.get_logger().info(f"按脚本发 /{args.topic}：{args.sequence}（共 {total:.1f} s）")

    start = time.monotonic()
    period = 1.0 / args.rate_hz
    next_step = 0
    pressed: str | None = None
    release_at = 0.0
    while True:
        now = time.monotonic() - start
        if now >= total:
            break
        if next_step < len(steps) and now >= steps[next_step][0]:
            pressed = steps[next_step][1]
            release_at = now + args.press_seconds
            node.get_logger().info(f"t={now:5.2f}s 按下 {pressed}")
            next_step += 1
        if pressed is not None and now >= release_at:
            pressed = None
        node.send(pressed)
        rclpy.spin_once(node, timeout_sec=0.0)
        time.sleep(period)

    node.send(None)
    node.get_logger().info("序列发完，最后一条全部松开")
    node.destroy_node()
    rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
