"""一键启动 cpp_hello 的 talker 与 listener（教程 §3）。

参数写在这里，等价于命令行 `--ros-args -p message:=... -p period_ms:=...`；
`--symlink-install` 下改本文件内容立即生效，增删/改名 launch 文件要重新 colcon build。
"""

from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            package='cpp_hello',
            executable='talker',
            name='talker',
            output='screen',
            parameters=[{
                'message': '你好，ros2',
                'period_ms': 500,
            }],
        ),
        Node(
            package='cpp_hello',
            executable='listener',
            name='listener',
            output='screen',
        ),
    ])
