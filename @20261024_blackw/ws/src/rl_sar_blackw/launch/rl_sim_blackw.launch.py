"""Launch the three nodes of the assignment: sim_node + joy_node (both from @20261005_ros2) + rl_sim.

Same topic interface as @20261005_ros2's bringup.launch.py, with rl_sim in place of controller_node
(data flow in the task README).

Usage (from the repository root):

    pixi run ros2 launch rl_sar_blackw rl_sim.launch.py                    # with the MuJoCo window (default)
    pixi run ros2 launch rl_sar_blackw rl_sim.launch.py viewer:=false      # headless
    pixi run ros2 launch rl_sar_blackw rl_sim.launch.py rl:=false          # no rl_sim; start it yourself to use
                                                                    # the keyboard: `pixi run ros2 run rl_sar_blackw rl_sim`

rl_sim reads stdin directly, so its keyboard controls only work when it owns a terminal - that is why
the keyboard needs the third form above. A gamepad (or the virtual pad) works through this launch file.

`realtime:=false` (full speed) also works: since S4 the control stack is paced by the sim_time carried
in /motor_state (control every 5 ms, inference every 20 ms of sim time), so the policy period does not
depend on how fast the sim runs - measured 7/7 at 25x. Rate table: @20261007_assignment/docs/control-stack-rates.md.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
import json
from pathlib import Path
from launch_ros.parameter_descriptions import ParameterValue


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SCENE_ROOT = PACKAGE_ROOT / "scenes" / "blackW"
PART2 = {e["key"]: e for e in json.loads((SCENE_ROOT / "part2_levels.json").read_text())}
PART1_SPAWN = (3.7, -9.0, 0.676, 0.0)  # support 0.001 + blackW wheel offset 0.670 + clearance


def _resolve_scene(part, level, explicit):
    if explicit:
        # An explicitly selected scene still gets the matching Part1/Part2 spawn, so
        # `scene:=part2_plum_eval_scene.xml` cannot silently spawn at the model origin.
        name = Path(explicit).name
        for e in PART2.values():
            if Path(e["scene"]).name == name:
                return explicit, tuple(e.get("spawn", e["start"]))
        if name == "scene_terrain.xml":
            return explicit, PART1_SPAWN
        return explicit, (None, None, None, None)
    if str(part) == "2":
        e = PART2[str(level)]
        start = e.get("spawn", e["start"])  # spawn is height-corrected for blackW; start is the original judge pose
        return str(SCENE_ROOT / e["scene"]), tuple(start)
    return str(SCENE_ROOT / "scene_terrain.xml"), PART1_SPAWN


def generate_launch_description() -> LaunchDescription:
    rl = LaunchConfiguration("rl")
    joy = LaunchConfiguration("joy")
    scene = LaunchConfiguration("scene")
    part = LaunchConfiguration("part")
    part2_level = LaunchConfiguration("part2_level")
    spawn_x = LaunchConfiguration("spawn_x")
    spawn_y = LaunchConfiguration("spawn_y")
    spawn_z = LaunchConfiguration("spawn_z")
    spawn_yaw = LaunchConfiguration("spawn_yaw")
    start = LaunchConfiguration("start")
    viewer = LaunchConfiguration("viewer")
    realtime = LaunchConfiguration("realtime")
    device = LaunchConfiguration("device")
    joy_command_scale = LaunchConfiguration("joy_command_scale")
    policy_name = LaunchConfiguration("policy_name")

    def _sim_params(context):
        part = context.perform_substitution(LaunchConfiguration("part"))
        level = context.perform_substitution(LaunchConfiguration("part2_level"))
        explicit = context.perform_substitution(LaunchConfiguration("scene"))
        scene_path, start_xyz_yaw = _resolve_scene(part, level, explicit)
        sx = context.perform_substitution(LaunchConfiguration("spawn_x"))
        sy = context.perform_substitution(LaunchConfiguration("spawn_y"))
        sz = context.perform_substitution(LaunchConfiguration("spawn_z"))
        syaw = context.perform_substitution(LaunchConfiguration("spawn_yaw"))
        params = {"scene": ParameterValue(scene_path, value_type=str),
                  "viewer": ParameterValue(LaunchConfiguration("viewer"), value_type=bool),
                  "realtime": ParameterValue(LaunchConfiguration("realtime"), value_type=bool),
                  "start": ParameterValue(LaunchConfiguration("start"), value_type=str)}
        # Defaults come from the selected Part1/Part2 spawn; explicit launch args override component-wise.
        defaults = dict(zip(("spawn_x", "spawn_y", "spawn_z", "spawn_yaw"), start_xyz_yaw))
        for key, val in (("spawn_x", sx), ("spawn_y", sy), ("spawn_z", sz), ("spawn_yaw", syaw)):
            if str(val) not in ("", "nan", "None"):
                params[key] = ParameterValue(val, value_type=float)
            elif defaults.get(key) is not None:
                params[key] = float(defaults[key])
        return params

    def _launch_sim_node(context):
        params = _sim_params(context)
        return [Node(
            package="quadruped_ros2_blackw",
            executable="sim_node",
            name="sim_node",
            output="screen",
            parameters=[params],
        )]

    return LaunchDescription(
        [
            DeclareLaunchArgument("rl", default_value="true", description="start rl_sim? set false to run it in its own terminal (keyboard)"),
            DeclareLaunchArgument("joy", default_value="true", description="start the joy node?"),
            DeclareLaunchArgument("scene", default_value="", description="explicit scene xml; empty = use part/part2_level defaults"),
            DeclareLaunchArgument("start", default_value="raw", description="sim start pose: raw / rest"),
            DeclareLaunchArgument("viewer", default_value="true", description="open the MuJoCo window?"),
            DeclareLaunchArgument("realtime", default_value="true", description="run the sim in real time (false = full speed; the control stack handles both)"),
            DeclareLaunchArgument("device", default_value="", description="gamepad device path; empty = auto"),
            DeclareLaunchArgument("policy_name", default_value="flat", description="blackW policy dir: flat / stair / obstacle"),
            DeclareLaunchArgument("part", default_value="1", description="1 = official Part1 terrain, 2 = Part2 level (set part2_level)"),
            DeclareLaunchArgument("part2_level", default_value="high_platform_10cm", description="Part2 level key, see scenes/blackW/part2_levels.json"),
            DeclareLaunchArgument("spawn_x", default_value="nan", description="optional spawn x override"),
            DeclareLaunchArgument("spawn_y", default_value="nan", description="optional spawn y override"),
            DeclareLaunchArgument("spawn_z", default_value="nan", description="optional spawn z override"),
            DeclareLaunchArgument("spawn_yaw", default_value="nan", description="optional spawn yaw override"),
            DeclareLaunchArgument("joy_command_scale", default_value="1.5", description="stick full deflection maps to this command [m/s, rad/s]"),
            OpaqueFunction(function=_launch_sim_node),
            Node(
                package="quadruped_ros2_blackw",
                executable="joy_node",
                name="joy_node",
                output="screen",
                condition=IfCondition(joy),
                parameters=[{"device": device}],
            ),
            Node(
                package="rl_sar_blackw",
                executable="rl_sim",
                name="rl_sim_node",
                output="screen",
                emulate_tty=True,
                condition=IfCondition(rl),
                parameters=[{"robot_name": "blackW", "policy_name": policy_name, "joy_command_scale": joy_command_scale}],
            ),
        ]
    )
