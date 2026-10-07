#!/usr/bin/env python3
"""手柄节点（Python，任务第 3 项）：读 xbox 协议手柄，发 sensor_msgs/Joy，并订阅控制器的回程状态。

手柄从 **/dev/input/event*** 直接读内核事件（python-evdev），不经 SDL/pygame：
轴与按钮的顺序就是 xpad 驱动的原始顺序，少一层映射、也就少一层"某个手柄被 SDL 重排了"的意外。

输出对齐主办者仓库 `quadruped_control/configs/input/gamepads.yaml` 的 `xbox` profile
（8 个轴 / 12 个按钮，长度固定）：

    axes[0..7]     = 左摇杆 X、左摇杆 Y、LT、右摇杆 X、右摇杆 Y、RT、DPad X、DPad Y
    buttons[0..11] = A、B、X、Y、LB、RB、Back、Start、Guide、LS、RS、（第 12 个恒 0）

按键含义由**控制器节点**决定（A 站立 / B 阻尼 / X 复位），手柄节点只管把原始输入发出去——
这样"手柄挂了"和"控制逻辑"是两件互不影响的事。

回程：订阅控制器的 quadruped_ros2/msg/ControlStatus（模式 / 斜坡进度 / 倾角 / 指令条数）并打印。
任务书要求"手柄节点需要和控制器节点互换消息"，这就是返程那一条。

用法（在仓库根目录）：

    pixi run ros2 run quadruped_ros2 joy_node
    pixi run ros2 run quadruped_ros2 joy_node --ros-args -p device:=/dev/input/event7
    pixi run ros2 run quadruped_ros2 joy_node --ros-args -p name:=        # 任何手柄都收

读 /dev/input/* 需要权限：一次性配置见任务 README（scripts/setup_joy_devices.sh）。
"""

from __future__ import annotations

import glob
import select
import sys
from pathlib import Path

import rclpy
from evdev import InputDevice, ecodes
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import QoSProfile
from sensor_msgs.msg import Joy

from quadruped_ros2.msg import ControlStatus

# 输出长度固定成 8 轴 / 12 按钮（与主办者仓库的 gamepads.yaml 一致，方便对照）
AXIS_COUNT = 8
BUTTON_COUNT = 12

STICK_MAX = 32767.0  # ABS_X 等的量程
TRIGGER_MAX = 255.0  # ABS_Z / ABS_RZ 的量程

# 轴顺序 = xpad 原始顺序（Xbox 协议）
AXIS_CODES = ("ABS_X", "ABS_Y", "ABS_Z", "ABS_RX", "ABS_RY", "ABS_RZ", "ABS_HAT0X", "ABS_HAT0Y")
# 按钮顺序 = xpad 上报顺序；第 12 个（索引 11）没有对应键，恒 0，留给"长度固定"用
BUTTON_CODES = (
    "BTN_A",
    "BTN_B",
    "BTN_X",
    "BTN_Y",
    "BTN_TL",
    "BTN_TR",
    "BTN_SELECT",
    "BTN_START",
    "BTN_MODE",
    "BTN_THUMBL",
    "BTN_THUMBR",
)

# 名字匹配片段（小写）：内核 xpad 驱动给 360 手柄起的名字是 "Microsoft X-Box 360 pad"，
# 大写以后是 X-BOX 而不是 XBOX —— 只匹配 "xbox" 会漏掉实体手柄，所以两种写法都要。
DEFAULT_NAME_FRAGMENTS = ("xbox", "x-box", "xinput")

# 读设备权限不足时给出的补救命令（写在报错里，省得再翻文档）
PERMISSION_HINT = (
    "读 /dev/input/* 需要权限：跑一次 @20261005_ros2/scripts/setup_joy_devices.sh（需要 sudo），"
    "或把当前用户加进 input 组后重新登录"
)

def has_absolute_axes(path: str) -> bool | None:
    """sysfs 里这个 event 设备有没有"绝对轴"（**不需要任何权限**）。

    这不是手柄的完整判据（真判据在 `matches()`：A 键 + 左摇杆两个轴），只用来先把
    键盘 / 鼠标这类"一定不是手柄"的设备滤掉：它们也挂在 `/dev/input/event*` 上、往往同样
    不可读，挨个去开就会打出一串"手柄没权限"的假警报（实测：跑过 setup 脚本、手柄也认到了，
    开头却还在报 event0 没权限）。鼠标只有 REL_*，键盘连轴都没有，所以"绝对轴全为 0"就够判。
    注意内核打印的能力位是**多字**位图（空格分隔、高位字在前），所以只看"是不是全 0"，
    不去算具体位——省掉一套容易写错的位序换算（这里第一版就写错过，实测返回了 None）。

    返回 None = 读不到 sysfs（设备刚 uinput 建出来、老内核等），调用方保守地"试着开一下"。
    """
    caps = Path("/sys/class/input") / Path(path).name / "device/capabilities/abs"
    try:
        text = caps.read_text().strip()
    except OSError:
        return None
    return any(int(word, 16) for word in text.split())


# 事件码 → 输出下标（xpad 顺序）
AXIS_INDEX = {getattr(ecodes, name): i for i, name in enumerate(AXIS_CODES)}
BUTTON_INDEX = {getattr(ecodes, name): i for i, name in enumerate(BUTTON_CODES)}


def make_joy(frame_id: str, axes: list[float], buttons: list[int], stamp) -> Joy:
    msg = Joy()
    msg.header.stamp = stamp
    msg.header.frame_id = frame_id
    msg.axes = list(axes)
    msg.buttons = list(buttons)
    return msg


class JoyNode(Node):
    def __init__(self) -> None:
        super().__init__("joy_node")
        self.declare_parameter("device", "")  # 空 = 自动找；给了就只认这个路径
        self.declare_parameter("device_dir", "/dev/input")  # 自动找时扫哪个目录
        self.declare_parameter("name", ",".join(DEFAULT_NAME_FRAGMENTS))  # 空 = 任何手柄都收
        self.declare_parameter("deadband", 0.08)  # 摇杆死区（LT/RT 与 DPad 不适用）
        self.declare_parameter("rate_hz", 100.0)  # 发布频率
        self.declare_parameter("topic", "joy")
        self.declare_parameter("status_topic", "control_status")

        self.device_path = self.get_parameter("device").value
        self.device_dir = self.get_parameter("device_dir").value
        name = self.get_parameter("name").value
        self.name_fragments = tuple(part.strip().lower() for part in name.split(",") if part.strip())
        self.deadband = float(self.get_parameter("deadband").value)
        rate_hz = float(self.get_parameter("rate_hz").value)
        joy_topic = self.get_parameter("topic").value
        status_topic = self.get_parameter("status_topic").value

        # /joy 用 reliable：它是低频"命令"而不是传感器流，也让 `ros2 topic echo /joy` 开箱可用
        # （控制器节点用同样的 reliable 订阅）
        self.publisher = self.create_publisher(Joy, joy_topic, 1)
        self.status_sub = self.create_subscription(
            ControlStatus, status_topic, self.on_status, QoSProfile(depth=1)
        )

        self.device: InputDevice | None = None
        self.axes = [0.0] * AXIS_COUNT
        self.buttons = [0] * BUTTON_COUNT
        self.frame_id = "joy_disconnected"
        self.last_status_log = 0.0
        self.last_mode = ""

        self.create_timer(1.0 / rate_hz, self.poll)
        self.create_timer(1.0, self.try_connect)  # 没插 / 被拔掉时每秒重试一次
        self.try_connect()
        self.get_logger().info(
            f"手柄节点：{rate_hz:.0f} Hz 发布 /{joy_topic}；设备 = "
            + (self.device_path or "自动找（名字含 " + "/".join(self.name_fragments) + "）")
        )

    # ------------------------------------------------------------------ 设备
    def candidate_paths(self) -> list[str]:
        if self.device_path:
            return [self.device_path]
        # 用 glob 而不是 evdev.list_devices()：后者会先按"可读可写"过滤一遍，
        # 没权限时直接返回空表，于是只能报"没找到手柄"，看不出是权限问题。
        paths = sorted(glob.glob(f"{self.device_dir}/event*"))
        # 键盘 / 鼠标 / 电源键也挂在 /dev/input/event* 上，而它们跟手柄一样（在同一台机器上）
        # 往往只有 root:input 可读：直接挨个去开，会在日志里打出一串"手柄没权限"的假警报
        # （实测：跑过 setup 脚本、手柄也认到了，开头却还在报 event0 没权限）。
        # 先按 sysfs 的"有没有绝对轴"筛一遍（见 has_absolute_axes）：键盘鼠标直接跳过；
        # 判不了的（刚建的 uinput 设备等）留着"试着开一下"，不牺牲鲁棒性。
        # 一个有绝对轴的都没有 = 这台机器现在就没有手柄类设备，此时**不去开**那些设备，
        # 免得又把"键盘没权限"报成"手柄没权限"。
        verdicts = {path: has_absolute_axes(path) for path in paths}
        return [p for p, v in verdicts.items() if v is True] + [p for p, v in verdicts.items() if v is None]

    def matches(self, dev: InputDevice) -> bool:
        caps = dev.capabilities()
        keys = set(caps.get(ecodes.EV_KEY, []))
        axes = {code for code, _ in caps.get(ecodes.EV_ABS, [])}
        # 必须像手柄：有 A 键 + 左摇杆两个轴（DPad 用 hat 还是轴不强求）
        if ecodes.BTN_A not in keys or ecodes.ABS_X not in axes or ecodes.ABS_Y not in axes:
            return False
        if not self.name_fragments:
            return True
        lowered = (dev.name or "").lower()
        return any(fragment in lowered for fragment in self.name_fragments)

    def try_connect(self) -> None:
        if self.device is not None:
            return
        denied: list[str] = []
        for path in self.candidate_paths():
            try:
                dev = InputDevice(path)
            except PermissionError:
                denied.append(path)
                continue
            except OSError:
                continue
            if self.matches(dev):
                self.device = dev
                self.frame_id = f"joy_connected:{dev.name}"
                self.get_logger().info(f"手柄已连接：{dev.name}（{path}，{dev.phys}）")
                return
            dev.close()
        if denied:
            # 只有"确实像手柄、但打不开"时才提示权限（见 candidate_paths 的注释）
            self.get_logger().error(
                f"{len(denied)} 个输入设备打不开（没有权限）：{'、'.join(denied)}；{PERMISSION_HINT}",
                once=True,
            )
            return
        self.get_logger().warning(
            "还没找到手柄：插上实体手柄，或先跑仿真手柄（sim_joy/xbox_sim_joy.py）",
            throttle_duration_sec=5.0,
        )

    def disconnect(self, reason: str) -> None:
        if self.device is not None:
            self.get_logger().warning(f"手柄断开（{reason}）")
            try:
                self.device.close()
            except OSError:
                pass
        self.device = None
        self.axes = [0.0] * AXIS_COUNT
        self.buttons = [0] * BUTTON_COUNT
        self.frame_id = "joy_disconnected"

    # ------------------------------------------------------------------ 读与发
    def apply_event(self, event) -> None:
        if event.type == ecodes.EV_ABS:
            index = AXIS_INDEX.get(event.code)
            if index is None:
                return
            if index in (0, 1, 3, 4):  # 摇杆：双极性 + 死区
                self.axes[index] = self.stick(event.value)
            elif index in (2, 5):  # 扳机：0..255 单极性
                self.axes[index] = self.trigger(event.value)
            else:  # DPad hat：本来就是 -1 / 0 / 1
                self.axes[index] = float(event.value)
        elif event.type == ecodes.EV_KEY:
            index = BUTTON_INDEX.get(event.code)
            if index is not None:
                self.buttons[index] = 1 if event.value else 0

    def stick(self, raw: int) -> float:
        value = raw / STICK_MAX
        if abs(value) < self.deadband:
            return 0.0
        return max(-1.0, min(1.0, value))

    @staticmethod
    def trigger(raw: int) -> float:
        # 松开 = -1、踩到底 = +1（与摇杆同一个区间，控制器侧不必区分量纲）
        return max(-1.0, min(1.0, raw / TRIGGER_MAX * 2.0 - 1.0))

    def poll(self) -> None:
        if self.device is not None:
            try:
                ready, _, _ = select.select([self.device.fd], [], [], 0.0)
                while ready:
                    for event in self.device.read():
                        self.apply_event(event)
                    ready, _, _ = select.select([self.device.fd], [], [], 0.0)
            except OSError:
                self.disconnect("设备读失败，可能被拔掉了")
        self.publisher.publish(
            make_joy(self.frame_id, self.axes, self.buttons, self.get_clock().now().to_msg())
        )

    # ------------------------------------------------------------------ 回程
    def on_status(self, msg) -> None:
        """控制器发来的状态（回程）。模式一变就打印，其余每 2 s 打一行。"""
        now = self.get_clock().now().nanoseconds / 1e9
        changed = msg.mode != self.last_mode
        if not changed and now - self.last_status_log < 2.0:
            return
        self.last_status_log = now
        self.last_mode = msg.mode
        self.get_logger().info(
            f"控制器回程：模式={msg.mode} 斜坡={msg.ramp_progress * 100:.0f}% "
            f"倾角={msg.tilt_deg:.1f}° 已发指令={msg.command_count} 条"
        )


def main() -> int:
    """跑起来，并在 Ctrl-C 时**干净退出**。

    两处容易踩的（实测）：① `rclpy.spin()` 在 SIGINT 时抛 `ExternalShutdownException`，
      它已经把 context shutdown 过了，我们再调一次 `rclpy.shutdown()` 就会抛
      `RCLError: failed to shutdown: rcl_shutdown already called`，于是 Ctrl-C 打出一段
      traceback、退出码 1（第一次三节点联跑就是这么结束的）；② context 已经关了以后
      `destroy_node()` 也可能报错。所以这两步都要"确认还活着再做"。
    """
    rclpy.init()
    node = JoyNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node.device is not None:
            try:
                node.device.close()
            except OSError:
                pass
        try:
            node.destroy_node()
        except Exception:  # noqa: BLE001  已经 shutdown 过时 destroy 会抛，不值得我们再崩一次
            pass
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
