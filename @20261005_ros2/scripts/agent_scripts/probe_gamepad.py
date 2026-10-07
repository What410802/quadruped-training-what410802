#!/usr/bin/env python3
"""真手柄探头：列设备 → 对照 `joy_node.py` 的预期 → 引导式采集真实布局。

**为什么需要它**：[`check_joystick_device.py`](check_joystick_device.py) 造的是**仿真**手柄（我们自己的
uinput 设备，布局必然与 xpad 一致）；实体手柄是"内核给它什么就是什么"，设备名、轴量程、轴/键的
码位都可能与 xpad 不同。这个脚本只**读**设备（不发任何事件），把"实际布局"和
`joy_node.py` 里那份写死的 xpad 预期逐项对照，并给出结论。

用法（仓库根）：

    # ① 静态核对：列出所有带绝对轴的设备，并对照 joy_node 的预期
    pixi run python @20261005_ros2/scripts/agent_scripts/probe_gamepad.py

    # ② 引导式采集：按提示依次动各个控件（左右摇杆、扳机、按键、方向键），
    #    结束后打印"哪个轴/键对应哪个控件"的实测布局表
    pixi run python @20261005_ros2/scripts/agent_scripts/probe_gamepad.py --watch 45

    # 指定设备（默认自动挑"有绝对轴且能打开"的那个）
    pixi run python @20261005_ros2/scripts/agent_scripts/probe_gamepad.py --device /dev/input/event15 --watch 45

读不到设备的权限问题见 `scripts/setup_joy_devices.sh` 与 docs/joystick.md §2。
"""

from __future__ import annotations

import argparse
import select
import sys
import time
from pathlib import Path

import evdev
from evdev import ecodes

# 与 joy_node.py 保持同一份预期（改那边时这里要跟着改；两边都引同一常量最理想，但
# joy_node 是被 colcon 安装的节点脚本，直接 import 会把 rclpy 也拖进来）
EXPECTED_AXIS_CODES = ("ABS_X", "ABS_Y", "ABS_Z", "ABS_RX", "ABS_RY", "ABS_RZ", "ABS_HAT0X", "ABS_HAT0Y")
EXPECTED_BUTTON_CODES = (
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
EXPECTED_NAME_FRAGMENTS = ("xbox", "x-box", "xinput", "gamepad", "joystick")
STICK_SLOTS = (0, 1, 3, 4)     # xbox 布局：左摇杆 0/1、右摇杆 3/4
TRIGGER_SLOTS = (2, 5)         # LT 2、RT 5
HAT_SLOTS = {"ABS_HAT0X": 6, "ABS_HAT0Y": 7}
BRAKE_IS_LT = True             # HID 里 brake = 左扳机、gas = 右扳机


def code_name(table, code: int) -> str:
    """evdev 的码表里既有 int→str 也有 int→tuple（别名），统一取字符串。"""
    value = table.get(code)
    if isinstance(value, tuple):
        return value[0]
    return value if isinstance(value, str) else f"0x{code:x}"


def candidates() -> list[tuple[str, evdev.InputDevice | None, str]]:
    """枚举 /dev/input/event*：能打开的给设备对象，打不开的给原因（权限/占用）。"""
    out = []
    for path in sorted(evdev.list_devices()):
        try:
            dev = evdev.InputDevice(path)
        except (OSError, PermissionError) as exc:
            out.append((path, None, type(exc).__name__))
            continue
        out.append((path, dev, ""))
    return out


def abs_axes(dev: evdev.InputDevice) -> dict[int, evdev.AbsInfo]:
    """`{事件码: AbsInfo}`——按**事件码**存、按码位顺序遍历，与 joy_node 分配槽位的顺序一致
    （按名字排序会把 ABS_RZ 排到 ABS_X 前面，预测出来的映射就错了）。"""
    caps = dev.capabilities(absinfo=True)
    return {code: info for code, info in sorted(caps.get(ecodes.EV_ABS, []))}


def axis_label(code: int) -> str:
    return code_name(ecodes.ABS, code)


def buttons(dev: evdev.InputDevice) -> list[str]:
    caps = dev.capabilities(absinfo=False)
    return [code_name(ecodes.BTN, code) for code in sorted(caps.get(ecodes.EV_KEY, []))]


def describe(dev: evdev.InputDevice) -> None:
    absinfos = abs_axes(dev)
    keys = buttons(dev)
    print(f"  设备名 : {dev.name!r}")
    print(f"  路径   : {dev.path} | phys={dev.phys} | uniq={dev.uniq!r}")
    print(f"  USB id : vendor=0x{dev.info.vendor:04x} product=0x{dev.info.product:04x} "
          f"bus=0x{dev.info.bustype:02x} ver=0x{dev.info.version:x}")
    print("  绝对轴（按事件码顺序）:")
    for code, info in absinfos.items():
        center = (info.min + info.max) / 2.0
        span = info.max - info.min
        bipolar = info.min < 0 or (span > 0 and abs(info.value - center) <= 0.25 * span)
        kind = "摇杆（双极性）" if bipolar else "扳机（单极性）"
        print(f"    {axis_label(code):12s} code={code:3d} value={info.value:6d} min={info.min:6d} "
              f"max={info.max:6d} 中点={center:7.1f} flat={info.flat}  ({kind})")
    print(f"  按键({len(keys)}) : " + " ".join(keys))
    print(f"  力反馈 : {dev.capabilities().get(ecodes.EV_FF, '无')}")


def classify(absinfos: dict[str, evdev.AbsInfo]) -> tuple[list, list, list[str]]:
    """复刻 `joy_node.py::build_axis_roles` 的判定：双极性 → 摇杆槽位、单极性 → 扳机槽位。

    规则改在节点里时这里也要改（探头是"核对手册"，不是第二份实现；两边不一致就说明工具过时了）。
    """
    sticks, triggers, ignored = [], [], []
    for code, info in absinfos.items():  # 已按事件码升序
        name = axis_label(code)
        if name in HAT_SLOTS:
            continue
        span = info.max - info.min
        if span <= 0:
            ignored.append(name)
            continue
        center = (info.min + info.max) / 2.0
        if info.min < 0 or abs(info.value - center) <= 0.25 * span:
            sticks.append((name, info))
        else:
            triggers.append((name, info))
    preferred = {"ABS_BRAKE": 0, "ABS_GAS": 1} if BRAKE_IS_LT else {"ABS_GAS": 0, "ABS_BRAKE": 1}
    triggers.sort(key=lambda ni: (preferred.get(ni[0], 2), ni[0]))
    return sticks, triggers, ignored


def verdict(dev: evdev.InputDevice) -> bool:
    """逐项对照 joy_node.py 的预期，返回 True = 不需要改代码就能用。"""
    ok = True
    absinfos = abs_axes(dev)
    keys = set(buttons(dev))
    lowered = (dev.name or "").lower()

    print("  —— 对照 joy_node.py 的预期 ——")
    matched = [f for f in EXPECTED_NAME_FRAGMENTS if f in lowered]
    if matched:
        print(f"  [OK]   设备名命中 name 过滤片段 {matched}")
    else:
        ok = False
        print(f"  [注意] 设备名不含 {EXPECTED_NAME_FRAGMENTS} 中任何一个 → 默认不会认领它。"
              f" 起节点时加 -p name:= 或 -p device:={dev.path}（docs/joystick.md §2）")

    sticks, triggers, ignored = classify(absinfos)
    print("  [OK]   轴角色由设备自己的 absinfo 判定（joy_node.build_axis_roles 的规则）→ 预期映射：")
    for (name, info), slot in zip(sticks, STICK_SLOTS):
        center = (info.min + info.max) / 2
        print(f"           {name}→axes[{slot}]/stick（中心 {center:.0f}，半量程 {(info.max - info.min) / 2:.0f}）")
    for (name, info), slot in zip(triggers, TRIGGER_SLOTS):
        print(f"           {name}→axes[{slot}]/trigger（0..{info.max}）")
    present = {axis_label(code) for code in absinfos}
    for name, slot in HAT_SLOTS.items():
        if name in present:
            print(f"           {name}→axes[{slot}]/hat")
    if len(sticks) > len(STICK_SLOTS):
        ok = False
        print(f"  [注意] 双极性轴有 {len(sticks)} 个，多于 {len(STICK_SLOTS)} 个摇杆槽位 → 多出来的会被忽略："
              f"{[n for n, _ in sticks[len(STICK_SLOTS):]]}")
    if ignored:
        print(f"  [提示] 忽略的轴（量程为 0 或不是摇杆/扳机/hat）：{ignored}")

    names = {axis_label(code) for code in absinfos}
    missing = [c for c in ("ABS_X", "ABS_Y") if c not in names]
    if missing or "BTN_A" not in keys:
        ok = False
        print(f"  [不兼容] 缺 {missing or ''}{' BTN_A' if 'BTN_A' not in keys else ''} → 过不了 joy_node 的 "
              f"matches()（要求 A 键 + 左摇杆两轴），认不到这台")
    only_digital = [c for c in ("BTN_TL", "BTN_TR", "BTN_TL2", "BTN_TR2") if c in keys]
    if only_digital:
        print(f"  [提示] 这台还有数字扳机键 {only_digital}：若同时有轴（上面那行），轴优先；"
              f"只有数字键时控制器侧看到的是 buttons[] 而不是 axes[]")

    missing_btn = [c for c in EXPECTED_BUTTON_CODES if c not in keys]
    if missing_btn:
        ok = False
        print(f"  [注意] 缺按钮 {missing_btn} → Joy.buttons 里对应下标恒 0（本节点只用 A/B/X）")
    else:
        print(f"  [OK]   12 个按钮里的 {len(EXPECTED_BUTTON_CODES)} 个码位齐全"
              f"（含 BTN_MODE={'BTN_MODE' in keys}）")
    return ok


def watch(dev: evdev.InputDevice, seconds: float) -> None:
    """引导式采集：按提示动各个控件，最后打印实测布局。"""
    print(f"\n=== 引导式采集（{seconds:.0f} s）===")
    print("请依次做（不用掐时间，每个动作动一下就回中/松开）：")
    for step in (
        "1) 左摇杆：左右扳到底、再上下扳到底",
        "2) 右摇杆：左右扳到底、再上下扳到底",
        "3) 左、右扳机/肩键：按到底再松开",
        "4) A / B / X / Y 各按一次",
        "5) Start / Select / 中间大键（若有）各按一次",
        "6) 方向键（十字键）四个方向各按一次",
    ):
        print("   " + step)
    print("（结束会打印实测表；随时 Ctrl-C 也能拿到已采到的部分）\n")

    ax_min: dict[str, int] = {}
    ax_max: dict[str, int] = {}
    ax_rest: dict[str, int] = {}
    ax_changed: dict[str, int] = {}
    btn_hits: dict[str, int] = {}
    for name, info in abs_axes(dev).items():
        ax_min[name] = ax_max[name] = ax_rest[name] = info.value
        ax_changed[name] = 0
    deadline = time.monotonic() + seconds
    try:
        while time.monotonic() < deadline:
            ready, _, _ = select.select([dev.fd], [], [], 0.2)
            if not ready:
                continue
            for event in dev.read():
                if event.type == ecodes.EV_ABS:
                    name = code_name(ecodes.ABS, event.code)
                    if name in ax_min:
                        ax_min[name] = min(ax_min[name], event.value)
                        ax_max[name] = max(ax_max[name], event.value)
                        if event.value != ax_rest[name]:
                            ax_changed[name] += 1
                elif event.type == ecodes.EV_KEY and event.value == 1:
                    name = code_name(ecodes.BTN, event.code)
                    btn_hits[name] = btn_hits.get(name, 0) + 1
    except KeyboardInterrupt:
        print("\n（提前结束，用已采到的数据）")

    print("=== 实测布局 ===")
    print(f"{'轴':14s} {'静止':>6s} {'最小':>6s} {'最大':>6s} {'变化次数':>8s}")
    for name in ax_min:
        print(f"{name:14s} {ax_rest[name]:6d} {ax_min[name]:6d} {ax_max[name]:6d} {ax_changed[name]:8d}")
    print("按下的键：", " ".join(f"{k}×{v}" for k, v in sorted(btn_hits.items())) or "（一个都没按到）")
    moving = [n for n, c in ax_changed.items() if c]
    still = [n for n, c in ax_changed.items() if not c]
    if still:
        print("没动过的轴：", " ".join(still), "（可能是 HID 描述里存在但物理上没有的控件）")
    if moving:
        print("动过的轴：", " ".join(moving))
        print("提示：若某个轴静止值在中点、且被 2) 右摇杆 或 3) 扳机 动到，它的语义就定了——"
              "拿这张表去核 joy_node.py 的 AXIS_CODES 与量程换算。")


def main() -> int:
    ap = argparse.ArgumentParser(description="实体手柄探头（只读，不注入任何事件）")
    ap.add_argument("--device", help="指定设备路径（默认：第一个有绝对轴且打得开的）")
    ap.add_argument("--watch", type=float, default=0.0, help="引导式采集秒数（0 = 只做静态核对）")
    args = ap.parse_args()

    devices = candidates()
    print("=== /dev/input 下的设备 ===")
    picked: evdev.InputDevice | None = None
    for path, dev, err in devices:
        if dev is None:
            print(f"  {path:22s} （打不开：{err}——多半是权限，见 scripts/setup_joy_devices.sh）")
            continue
        has_abs = bool(dev.capabilities().get(ecodes.EV_ABS))
        print(f"  {path:22s} abs={has_abs!s:5s} {dev.name!r}")
        if has_abs and picked is None and (args.device is None or path == args.device):
            picked = dev
        elif dev.path != (picked.path if picked else None):
            dev.close()

    if args.device:
        try:
            picked = evdev.InputDevice(args.device)
        except OSError as exc:
            print(f"\n打不开 {args.device}：{exc}")
            return 1
    if picked is None:
        print("\n没有找到可用的手柄设备（要有绝对轴、且当前用户能读）。")
        return 1

    print(f"\n=== 选中：{picked.path} ===")
    describe(picked)
    ok = verdict(picked)
    print(f"\n结论：{'joy_node 能直接用这台（映射见上面的预期表）' if ok else '与 joy_node 的预期有差异，见上面标了 [注意]/[不兼容] 的行'}")

    if args.watch > 0:
        watch(picked, args.watch)
    picked.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
