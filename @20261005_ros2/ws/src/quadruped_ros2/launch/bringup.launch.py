"""一键启动本次任务的三个节点（任务第 4 项）：仿真节点 + 控制器节点 + 手柄节点。

用法（在仓库根目录；仓库只用一个 pixi 环境，不必再带 `-e`）：

    pixi run ros2 launch quadruped_ros2 bringup.launch.py                    # 开窗口（默认）
    pixi run ros2 launch quadruped_ros2 bringup.launch.py viewer:=false      # 无窗口
    pixi run ros2 launch quadruped_ros2 bringup.launch.py joy:=false         # 不起手柄节点
    pixi run ros2 launch quadruped_ros2 bringup.launch.py start:=rest        # 该从趴卧 keyframe 起
    pixi run ros2 launch quadruped_ros2 bringup.launch.py device:=/dev/input/event7

三个节点之间的关系见任务 README 的那张数据流图；本文件只做"谁来起、参数怎么传"。
`viewer` 在没有 DISPLAY / WAYLAND_DISPLAY 时由仿真节点自己降级成无窗口，不会崩。

**暴露哪些参数**：凡"随外部世界变化"或"要现场整定"的都从这里给——仿真的场景/形态与视口
（scene、start、viewer、realtime、viewer_shadow、viewer_shadow_size、viewer_shadow_clip、
viewer_msaa、viewer_render_scale）、控制整定（kp/kd/kd_damp/ramp）、电机非理想项（motor_deadzone、
motor_delay_cycles、motor_noise、motor_seed）、手柄与真机映射（joy、device、name、deadband、
按键索引）、倾角告警阈值（tilt_warn_deg）；
其余是模型常数（tau_max/damp_kd）与实现细节（看门狗、发布/日志频率、话题名），它们有合理默认值，
要改就 `ros2 param set`（运行时）或 `ros2 run … --ros-args -p`（单节点）——完整参数表见
`docs/ros2-nodes.md` §1.2。
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    joy = LaunchConfiguration("joy")
    scene = LaunchConfiguration("scene")
    start = LaunchConfiguration("start")
    viewer = LaunchConfiguration("viewer")
    viewer_shadow = LaunchConfiguration("viewer_shadow")
    viewer_shadow_size = LaunchConfiguration("viewer_shadow_size")
    viewer_shadow_clip = LaunchConfiguration("viewer_shadow_clip")
    viewer_msaa = LaunchConfiguration("viewer_msaa")
    viewer_render_scale = LaunchConfiguration("viewer_render_scale")
    realtime = LaunchConfiguration("realtime")
    motor_deadzone = LaunchConfiguration("motor_deadzone")
    motor_delay_cycles = LaunchConfiguration("motor_delay_cycles")
    motor_noise = LaunchConfiguration("motor_noise")
    motor_seed = LaunchConfiguration("motor_seed")
    device = LaunchConfiguration("device")
    joy_name = LaunchConfiguration("name")
    deadband = LaunchConfiguration("deadband")
    kp = LaunchConfiguration("kp")
    kd = LaunchConfiguration("kd")
    kd_damp = LaunchConfiguration("kd_damp")
    ramp = LaunchConfiguration("ramp")
    button_stand = LaunchConfiguration("button_stand")
    button_damp = LaunchConfiguration("button_damp")
    button_reset = LaunchConfiguration("button_reset")
    tilt_warn_deg = LaunchConfiguration("tilt_warn_deg")

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "joy",
                default_value="true",
                description="是否启动手柄节点（没有手柄 / 没有权限时可关掉，控制器照常收 /joy）",
            ),
            DeclareLaunchArgument(
                "scene",
                default_value="",
                description="场景 xml；空 = 从可执行文件往上找 scenes/flat_scene.xml",
            ),
            DeclareLaunchArgument(
                "start",
                default_value="raw",
                description="起点：raw = 模型原姿态（默认，与上次任务一致），rest = 场景里的趴卧 keyframe",
            ),
            DeclareLaunchArgument(
                "viewer",
                default_value="true",
                description="仿真节点开不开 MuJoCo 官方窗口（无显示服务时自动关）",
            ),
            DeclareLaunchArgument(
                "viewer_shadow",
                default_value="true",
                description="视口阴影开关（运行中按 S 也能切；关掉最省，实测见 docs/ros2-nodes.md §2.1）",
            ),
            DeclareLaunchArgument(
                "viewer_shadow_size",
                default_value="4096",
                description="阴影贴图边长；0 = 用模型默认（4096）。4096 比 1024 只多 0.2~0.6 ms/帧、阴影边界偏移却小 4.3×（见 docs/learn/graphics-stack.md §8.3）。改它要重启节点",
            ),
            DeclareLaunchArgument(
                "viewer_shadow_clip",
                default_value="1.0",
                description="阴影正交盒半宽 = stat.extent×该值（只对平行光有效）；越小阴影越精细、覆盖越小，改它要重启节点（成因见 docs/learn/graphics-stack.md §8.3）",
            ),
            DeclareLaunchArgument(
                "viewer_msaa",
                default_value="4",
                description="窗口/离屏多重采样（抗锯齿）；0 = 关。窗口拿不到时自动走离屏 MSAA",
            ),
            DeclareLaunchArgument(
                "viewer_render_scale",
                default_value="2",
                description="超采样倍率：离屏按 倍率×framebuffer 渲染再缩回窗口；1 = 关（放大看细节时最明显）",
            ),
            DeclareLaunchArgument(
                "realtime",
                default_value="true",
                description="物理按墙钟节流；false = 全速跑（回归脚本用）",
            ),
            DeclareLaunchArgument(
                "motor_deadzone",
                default_value="0.0",
                description="电机静摩擦死区 [N·m]；0 = 理想力矩源（典型真实值 0.5，见 docs/motor-model.md）",
            ),
            DeclareLaunchArgument(
                "motor_delay_cycles",
                default_value="0",
                description="电机指令延迟 [控制周期]；0 = 无延迟（典型真实值 2）",
            ),
            DeclareLaunchArgument(
                "motor_noise",
                default_value="0.0",
                description="电机力矩噪声标准差 [N·m]；0 = 无噪声（典型真实值 0.2）",
            ),
            DeclareLaunchArgument(
                "motor_seed",
                default_value="12345",
                description="噪声种子：同一组参数 + 同一 seed → 同一条噪声序列，便于复现",
            ),
            DeclareLaunchArgument(
                "device",
                default_value="",
                description="手柄设备路径；空 = 按名字自动找",
            ),
            DeclareLaunchArgument(
                "name",
                default_value="xbox,x-box,xinput",
                description="手柄名字里要含的片段（逗号分隔）；空 = 任何手柄都收",
            ),
            DeclareLaunchArgument(
                "deadband",
                default_value="0.08",
                description="摇杆死区（0..1）；磨损摇杆自漂时调大",
            ),
            DeclareLaunchArgument("kp", default_value="80.0", description="站立模式位置刚度"),
            DeclareLaunchArgument("kd", default_value="3.0", description="站立模式速度刚度"),
            DeclareLaunchArgument("kd_damp", default_value="0.5", description="阻尼模式速度刚度（趴下时用）"),
            DeclareLaunchArgument("ramp", default_value="1.0", description="起身斜坡时长 [s]"),
            DeclareLaunchArgument("button_stand", default_value="0", description="站立键索引（xpad：A=0 B=1 X=2 Y=3…）"),
            DeclareLaunchArgument("button_damp", default_value="1", description="阻尼键索引"),
            DeclareLaunchArgument("button_reset", default_value="2", description="复位键索引"),
            DeclareLaunchArgument("tilt_warn_deg", default_value="60.0", description="倾角告警阈值 [deg]"),
            # ② 仿真节点（C++，MuJoCo + 电机模型）
            Node(
                package="quadruped_ros2",
                executable="sim_node",
                name="sim_node",
                output="screen",
                parameters=[
                    {
                        "scene": scene,
                        "start": start,
                        "viewer": viewer,
                        "realtime": realtime,
                        "viewer_shadow": viewer_shadow,
                        "viewer_shadow_size": viewer_shadow_size,
                        "viewer_shadow_clip": viewer_shadow_clip,
                        "viewer_msaa": viewer_msaa,
                        "viewer_render_scale": viewer_render_scale,
                        "motor_deadzone": motor_deadzone,
                        "motor_delay_cycles": motor_delay_cycles,
                        "motor_noise": motor_noise,
                        "motor_seed": motor_seed,
                    }
                ],
            ),
            # ① 控制器节点（C++，状态机 + MIT 五参数）
            Node(
                package="quadruped_ros2",
                executable="controller_node",
                name="controller_node",
                output="screen",
                parameters=[
                    {
                        "kp": kp,
                        "kd": kd,
                        "kd_damp": kd_damp,
                        "ramp": ramp,
                        "button_stand": button_stand,
                        "button_damp": button_damp,
                        "button_reset": button_reset,
                        "tilt_warn_deg": tilt_warn_deg,
                    }
                ],
            ),
            # ③ 手柄节点（Python，读 /dev/input → /joy）
            Node(
                package="quadruped_ros2",
                executable="joy_node",
                name="joy_node",
                output="screen",
                condition=IfCondition(joy),
                parameters=[{"device": device, "name": joy_name, "deadband": deadband}],
            ),
        ]
    )
