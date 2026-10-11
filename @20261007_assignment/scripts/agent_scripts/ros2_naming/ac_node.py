#!/usr/bin/env python3
"""Experiment 3c: publisher on /a/c, to test whether -r /a:=/b moves children."""
import sys
import rclpy
from rclpy.node import Node
from std_msgs.msg import String

import os
DURATION = float(os.environ.get('AC_DURATION', '5'))


class AC(Node):
    def __init__(self):
        super().__init__('ac_probe')
        self.p = self.create_publisher(String, '/a/c', 10)
        print('=== AC PROBE ===', flush=True)
        print(f'pub("/a/c").topic_name = {self.p.topic_name!r}', flush=True)
        print('=== END ===', flush=True)
        self.create_timer(DURATION, self._quit)

    def _quit(self):
        raise SystemExit(0)


rclpy.init()
n = AC()
try:
    rclpy.spin(n)
except SystemExit:
    pass
finally:
    n.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()
