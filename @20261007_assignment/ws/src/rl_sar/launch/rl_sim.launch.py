"""一键启动大作业的三个节点：仿真节点 + 手柄节点（都来自 @20261005_ros2）+ rl_sim（本包）。

与 @20261005_ros2 的 bringup.launch.py 相比，只是把 controller_node 换成了 rl_sim——
仿真节点与手柄节点原样复用，话题接口不变（数据流见任务 README）。

用法（仓库根目录）：

    pixi run ros2 launch rl_sar rl_sim.launch.py                     # 开窗口（默认）
    pixi run ros2 launch rl_sar rl_sim.launch.py viewer:=false       # 无窗口
    pixi run ros2 launch rl_sar rl_sim.launch.py rl:=false           # 不起 rl_sim，另开终端
                                                                     # `pixi run ros2 run rl_sar rl_sim` 用键盘操作

注：**rl_sim 的键盘操作只在它自己独占终端时有效**（它直接读 stdin 而 launch 不把终端交给子进程），
所以要用键盘就按上面第三行分开起。手柄（或仿真手柄）在 launch 里就能用。

`realtime` 默认 true 且**不要改成 false**：rl_sim 按墙钟每 20 ms 推理一次，仿真必须按真实时间走，
两边的"20 ms"才是同一个 20 ms（实验与结论见 docs/experiments.md）。
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    rl = LaunchConfiguration("rl")
    joy = LaunchConfiguration("joy")
    scene = LaunchConfiguration("scene")
    start = LaunchConfiguration("start")
    viewer = LaunchConfiguration("viewer")
    realtime = LaunchConfiguration("realtime")
    device = LaunchConfiguration("device")
    joy_command_scale = LaunchConfiguration("joy_command_scale")

    return LaunchDescription(
        [
            DeclareLaunchArgument("rl", default_value="true", description="是否起 rl_sim（键盘操作时设 false，另开终端单独起）"),
            DeclareLaunchArgument("joy", default_value="true", description="是否起手柄节点"),
            DeclareLaunchArgument("scene", default_value="", description="场景 xml；空 = 仿真节点默认（@20261005_ros2/scenes/flat_scene.xml）"),
            DeclareLaunchArgument("start", default_value="raw", description="仿真起点：raw / rest"),
            DeclareLaunchArgument("viewer", default_value="true", description="是否开 MuJoCo 窗口"),
            DeclareLaunchArgument("realtime", default_value="true", description="仿真按真实时间走（rl_sim 依赖它，保持 true）"),
            DeclareLaunchArgument("device", default_value="", description="手柄设备路径；空 = 自动获取"),
            DeclareLaunchArgument("joy_command_scale", default_value="1.5", description="摇杆满偏对应的速度指令 [m/s、rad/s]"),
            Node(
                package="quadruped_ros2",
                executable="sim_node",
                name="sim_node",
                output="screen",
                parameters=[{"scene": scene, "start": start, "viewer": viewer, "realtime": realtime}],
            ),
            Node(
                package="quadruped_ros2",
                executable="joy_node",
                name="joy_node",
                output="screen",
                condition=IfCondition(joy),
                parameters=[{"device": device}],
            ),
            Node(
                package="rl_sar",
                executable="rl_sim",
                name="rl_sim_node",
                output="screen",
                emulate_tty=True,
                condition=IfCondition(rl),
                parameters=[{"robot_name": "black", "joy_command_scale": joy_command_scale}],
            ),
        ]
    )
