"""Launch the three nodes of the assignment: sim_node + joy_node (both from @20261005_ros2) + rl_sim.

Same topic interface as @20261005_ros2's bringup.launch.py, with rl_sim in place of controller_node
(data flow in the task README).

Usage (from the repository root):

    pixi run ros2 launch rl_sar rl_sim.launch.py                    # with the MuJoCo window (default)
    pixi run ros2 launch rl_sar rl_sim.launch.py viewer:=false      # headless
    pixi run ros2 launch rl_sar rl_sim.launch.py rl:=false          # no rl_sim; start it yourself to use
                                                                    # the keyboard: `pixi run ros2 run rl_sar rl_sim`

rl_sim reads stdin directly, so its keyboard controls only work when it owns a terminal - that is why
the keyboard needs the third form above. A gamepad (or the virtual pad) works through this launch file.

`realtime:=false` (full speed) also works: since S4 the control stack is paced by the sim_time carried
in /motor_state (control every 5 ms, inference every 20 ms of sim time), so the policy period does not
depend on how fast the sim runs - measured 7/7 at 25x. Rate table: @20261007_assignment/docs/control-stack-rates.md.
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
            DeclareLaunchArgument("rl", default_value="true", description="start rl_sim? set false to run it in its own terminal (keyboard)"),
            DeclareLaunchArgument("joy", default_value="true", description="start the joy node?"),
            DeclareLaunchArgument("scene", default_value="", description="scene xml; empty = sim_node default (@20261005_ros2/scenes/flat_scene.xml)"),
            DeclareLaunchArgument("start", default_value="raw", description="sim start pose: raw / rest"),
            DeclareLaunchArgument("viewer", default_value="true", description="open the MuJoCo window?"),
            DeclareLaunchArgument("realtime", default_value="true", description="run the sim in real time (false = full speed; the control stack handles both)"),
            DeclareLaunchArgument("device", default_value="", description="gamepad device path; empty = auto"),
            DeclareLaunchArgument("joy_command_scale", default_value="1.5", description="stick full deflection maps to this command [m/s, rad/s]"),
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
