#!/usr/bin/env python3
"""实验 2/3/4 的探针节点：发一个相对名、一个绝对名、一个私有名话题，声明参数 who，打印解析结果。

跑法见 docs/learn/ros2-graph-and-clock.md §3（要带 --ros-args -r __ns:=… -r __node:=…）。

Publishes one relative, one absolute and one private topic, declares parameter
'who', prints resolved names, then spins for --duration seconds.

Usage: ros2 run-less direct: pixi run python @20261007_assignment/scripts/agent_scripts/ros2_naming/probe_node.py
       plus normal --ros-args ... remapping arguments.
"""
import sys
import rclpy
from rclpy.node import Node
from std_msgs.msg import String

import os
DURATION = float(os.environ.get('PROBE_DURATION', '18'))


class Probe(Node):
    def __init__(self):
        super().__init__('probe')
        self.declare_parameter('who', 'unset')
        if os.environ.get('DECLARE_EXTRA') == '1':
            self.declare_parameter('extra', -1)
            print(f'post-hoc declared "extra"      = '
                  f'{self.get_parameter("extra").value!r}', flush=True)
        self.p_rel = self.create_publisher(String, 'rel_topic', 10)
        self.p_abs = self.create_publisher(String, '/abs_topic', 10)
        self.p_priv = self.create_publisher(String, '~/priv_topic', 10)

        print('=== PROBE RESOLVED NAMES ===', flush=True)
        print(f'node.get_name()                = {self.get_name()!r}', flush=True)
        print(f'node.get_namespace()           = {self.get_namespace()!r}', flush=True)
        print(f'node.get_fully_qualified_name()= {self.get_fully_qualified_name()!r}', flush=True)
        print(f'pub("rel_topic").topic_name    = {self.p_rel.topic_name!r}', flush=True)
        print(f'pub("/abs_topic").topic_name   = {self.p_abs.topic_name!r}', flush=True)
        print(f'pub("~/priv_topic").topic_name = {self.p_priv.topic_name!r}', flush=True)
        print(f'param "who" value              = '
              f'{self.get_parameter("who").value!r}', flush=True)
        print(f'all declared params            = '
              f'{ {k: v.value for k, v in sorted(self._parameters.items())} }', flush=True)
        print('=== END PROBE ===', flush=True)

        self.create_timer(DURATION, self._quit)

    def _quit(self):
        print(f'[probe] duration {DURATION}s reached, shutting down', flush=True)
        raise SystemExit(0)


def main():
    rclpy.init()
    try:
        node = Probe()
    except Exception as e:
        print(f'!!! NODE CREATION FAILED: {type(e).__name__}: {e}', flush=True)
        raise
    try:
        rclpy.spin(node)
    except SystemExit:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
