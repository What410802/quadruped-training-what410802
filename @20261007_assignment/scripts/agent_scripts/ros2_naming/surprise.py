#!/usr/bin/env python3
"""实验 5：那些"看着合法"的名字，真的能建进图里吗？

默认试一组固定名字（`//foo`、`foo//bar`、`foo{}`、`_`、300 个 `L`）；要换一组就设
`TOPICS='["a/b", "ns//x"]'`。跑法（仓库根）：

```bash
pixi run python @20261007_assignment/scripts/agent_scripts/ros2_naming/surprise.py --ros-args -r __ns:=/robot1
```

结论见 docs/learn/ros2-graph-and-clock.md §3.1/§3.7。
"""
import os
import json
import rclpy
from rclpy.node import Node
from std_msgs.msg import String

_DEFAULT_NAMES = ["//foo", "foo//bar", "foo{}", "_", "L" * 300]
NAMES = json.loads(os.environ["TOPICS"]) if "TOPICS" in os.environ else _DEFAULT_NAMES

rclpy.init()
node = Node('surprise_probe')
node.declare_parameter('who', 'unset')
print(f'node fqn = {node.get_fully_qualified_name()!r}', flush=True)
for n in NAMES:
    disp = n if len(n) <= 20 else f'{n[:8]}...({len(n)} chars)'
    try:
        p = node.create_publisher(String, n, 10)
        print(f'  create_publisher({disp!r}) OK -> topic_name={p.topic_name!r} '
              f'(len={len(p.topic_name)})', flush=True)
    except Exception as e:
        print(f'  create_publisher({disp!r}) FAILED -> '
              f'{type(e).__name__}: {str(e).splitlines()[0]}', flush=True)

def quit_():
    raise SystemExit(0)
node.create_timer(float(os.environ.get('SURPRISE_DURATION', '4')), quit_)
try:
    rclpy.spin(node)
except SystemExit:
    pass
finally:
    node.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()
