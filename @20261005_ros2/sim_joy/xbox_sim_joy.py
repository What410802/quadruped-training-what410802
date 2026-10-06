#!/usr/bin/env python3
"""仿真手柄（外部独立进程）：鼠标造一个**真的** xbox 协议手柄，供 joy_node 原样读取。

不是 ROS 节点，也不发布话题——它只做一件事：通过 /dev/uinput 造一个内核输入设备，
名字 / VID / PID / 轴序 / 按钮序都对齐 Linux xpad 驱动下的 Xbox 360 手柄。
于是 `joy_node`（以及任何 SDL / pygame / jstest 程序）都分不出它是真是假：

    实体手柄稀缺 → 先用它把"手柄 → 控制器 → 仿真"整条链路测通 → 再插真手柄复验。

用法：

    pixi run python @20261005_ros2/sim_joy/xbox_sim_joy.py

需要一次性权限（写 /dev/uinput 与读 /dev/input/event*），见脚本 scripts/setup_joy_devices.sh。
没权限时本程序会直接把要跑的命令打出来。

界面：左/右摇杆拖动、LT/RT 滑条、按钮按住、DPad 九宫格；勾"保持"可锁定某个输入，
方便一边操作一边看别的窗口。设备位置由内核决定，打印里的 `/dev/input/eventN` 就是它。
"""

from __future__ import annotations

import argparse
import math
import threading
import time

AXIS_MAX = 32767  # 摇杆量程（xpad：-32768..32767，取对称的正半当分子）
TRIGGER_MAX = 255  # 扳机量程
AXIS_MIN = -32768

BUTTON_NAMES = ["A", "B", "X", "Y", "LB", "RB", "Back", "Start", "Guide", "LS", "RS"]

SETUP_HINT = """\
[sudo] 需要一次性权限配置（写 /dev/uinput + 读 /dev/input/event*）：

    sudo <仓库根>/@20261005_ros2/scripts/setup_joy_devices.sh

它只写一条 udev 规则（给 uinput 与手柄设备打 uaccess 标签），不装任何软件。
"""


def build_uinput():
    """创建虚拟 Xbox 360 手柄（uinput）。轴/按钮顺序必须与 xpad 一致。"""
    from evdev import AbsInfo, UInput, ecodes as e

    def stick():
        return AbsInfo(value=0, min=AXIS_MIN, max=AXIS_MAX, fuzz=0, flat=0, resolution=0)

    def trigger():
        return AbsInfo(value=0, min=0, max=TRIGGER_MAX, fuzz=0, flat=0, resolution=0)

    def hat():
        return AbsInfo(value=0, min=-1, max=1, fuzz=0, flat=0, resolution=0)

    keys = [
        e.BTN_A,
        e.BTN_B,
        e.BTN_X,
        e.BTN_Y,
        e.BTN_TL,
        e.BTN_TR,
        e.BTN_SELECT,
        e.BTN_START,
        e.BTN_MODE,
        e.BTN_THUMBL,
        e.BTN_THUMBR,
    ]
    axes = [
        (e.ABS_X, stick()),
        (e.ABS_Y, stick()),
        (e.ABS_Z, trigger()),
        (e.ABS_RX, stick()),
        (e.ABS_RY, stick()),
        (e.ABS_RZ, trigger()),
        (e.ABS_HAT0X, hat()),
        (e.ABS_HAT0Y, hat()),
    ]
    return UInput(
        events={e.EV_KEY: keys, e.EV_ABS: axes},
        # 名字里要有 "Xbox"：joy_node 按名字片段挑设备（xbox / x-box / xinput）
        name="Xbox 360 Wireless Controller (Sim)",
        vendor=0x045E,
        product=0x028E,
        version=0x0100,
        bustype=e.BUS_USB,
    )


class XboxState:
    """一份手柄状态（GUI 写、uinput 线程读）。角度/扳机都归一化到 -1..1 或 0..1。"""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.lx = 0.0
        self.ly = 0.0  # GUI 约定：右 / 上为正
        self.rx = 0.0
        self.ry = 0.0
        self.lt = 0.0  # 0..1
        self.rt = 0.0
        self.dpad = (0, 0)  # (x, y)，下为正（GUI 坐标）
        self.buttons = [0] * len(BUTTON_NAMES)

    def set_stick(self, side: str, x: float, y: float) -> None:
        with self.lock:
            if side == "L":
                self.lx, self.ly = x, y
            else:
                self.rx, self.ry = x, y

    def set_trigger(self, side: str, value: float) -> None:
        with self.lock:
            if side == "L":
                self.lt = value
            else:
                self.rt = value

    def set_dpad(self, x: int, y: int) -> None:
        with self.lock:
            self.dpad = (x, y)

    def set_button(self, index: int, value: int) -> None:
        with self.lock:
            self.buttons[index] = 1 if value else 0

    def reset(self) -> None:
        with self.lock:
            self.lx = self.ly = self.rx = self.ry = 0.0
            self.lt = self.rt = 0.0
            self.dpad = (0, 0)
            self.buttons = [0] * len(BUTTON_NAMES)

    def snapshot(self):
        with self.lock:
            return (
                self.lx,
                self.ly,
                self.rx,
                self.ry,
                self.lt,
                self.rt,
                self.dpad,
                list(self.buttons),
            )


def uinput_loop(ui, state: XboxState, hz: float) -> None:
    """按固定频率把状态写进 uinput（只在变化时写，但每秒至少 syn 一次）。"""
    from evdev import ecodes as e

    period = 1.0 / hz
    last = None
    while True:
        lx, ly, rx, ry, lt, rt, (dx, dy), buttons = state.snapshot()
        raw = (
            int(max(-1.0, min(1.0, lx)) * AXIS_MAX),
            int(max(-1.0, min(1.0, -ly)) * AXIS_MAX),  # evdev：上 = 负
            int(max(0.0, min(1.0, lt)) * TRIGGER_MAX),
            int(max(-1.0, min(1.0, rx)) * AXIS_MAX),
            int(max(-1.0, min(1.0, -ry)) * AXIS_MAX),
            int(max(0.0, min(1.0, rt)) * TRIGGER_MAX),
            int(dx),
            int(-dy),  # evdev hat：上 = 正，GUI 的 y 向下为正
        )
        current = (raw, tuple(buttons))
        if current != last:
            for code, value in zip(
                (e.ABS_X, e.ABS_Y, e.ABS_Z, e.ABS_RX, e.ABS_RY, e.ABS_RZ, e.ABS_HAT0X, e.ABS_HAT0Y),
                raw,
            ):
                ui.write(e.EV_ABS, code, value)
            for index, code in enumerate(
                (
                    e.BTN_A,
                    e.BTN_B,
                    e.BTN_X,
                    e.BTN_Y,
                    e.BTN_TL,
                    e.BTN_TR,
                    e.BTN_SELECT,
                    e.BTN_START,
                    e.BTN_MODE,
                    e.BTN_THUMBL,
                    e.BTN_THUMBR,
                )
            ):
                ui.write(e.EV_KEY, code, buttons[index])
            ui.syn()
            last = current
        time.sleep(period)


def apply_cjk_font(root) -> str:
    """把 Tk 的默认字体换成中文字体，返回用上的字族名（一个都没找到就返回空串）。

    实测（本机）：`TkDefaultFont` 是 `gothic`（**日文**字体）**9 号**——中文既小又"连笔"，
    因为日文字形与中文字形本就不同（如"直/角/单"的写法），9 号也太小。
    这台机器的 Tk 是**非 Xft** 构建（`font.families()` 只列出 20 个 X11 核心字族），
    所以 fontconfig 里的 `Noto Sans CJK SC` 在这里找不到、任何名字都会掉回 `fixed`；
    能用的是核心字族里的 **`song ti`（宋体）/`fangsong ti`（仿宋）**，它们才是中文正体。
    两套名字都试：Xft 构建的 Tk 用前面的，核心字体的 Tk 用后面的。
    `TkFixedFont` 不动（保持等宽）。
    """
    import tkinter.font as tkfont

    available = set(tkfont.families(root))
    candidates = (
        "Noto Sans CJK SC",
        "Source Han Sans SC",
        "WenQuanYi Micro Hei",
        "Droid Sans Fallback",
        "Microsoft YaHei",
        "song ti",
        "fangsong ti",
    )
    for family in candidates:
        if family not in available:
            continue
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkTooltipFont"):
            try:
                tkfont.nametofont(name).configure(family=family, size=12)
            except Exception:  # noqa: BLE001  某个命名字体不存在时不影响其它
                pass
        return family
    return ""


def build_gui(state: XboxState, status) -> None:
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    apply_cjk_font(root)
    root.title("仿真 Xbox 360 手柄 —— xbox_sim_joy（外部进程，不经过 ROS）")

    def make_pad(parent, label: str, side: str) -> None:
        frame = ttk.LabelFrame(parent, text=label)
        frame.pack(side=tk.LEFT, padx=8, pady=4)
        size = 170
        canvas = tk.Canvas(frame, width=size, height=size, bg="#1e1e1e", highlightthickness=0)
        canvas.pack(padx=6, pady=6)
        center = size / 2
        radius = size / 2 - 12
        canvas.create_oval(
            center - radius, center - radius, center + radius, center + radius, outline="#555", width=2
        )
        knob = canvas.create_oval(
            center - 13, center - 13, center + 13, center + 13, fill="#e0603a", outline=""
        )
        hold = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text="松手保持", variable=hold).pack(anchor="w")

        def move(event):
            dx, dy = event.x - center, event.y - center
            dist = math.hypot(dx, dy)
            if dist > radius:
                dx, dy = dx * radius / dist, dy * radius / dist
            canvas.coords(
                knob, center + dx - 13, center + dy - 13, center + dx + 13, center + dy + 13
            )
            state.set_stick(side, dx / radius, -dy / radius)  # 屏幕上为正 → 归一化后上为正

        def release(_event=None):
            if not hold.get():
                canvas.coords(knob, center - 13, center - 13, center + 13, center + 13)
                state.set_stick(side, 0.0, 0.0)

        canvas.bind("<B1-Motion>", move)
        canvas.bind("<Button-1>", move)
        canvas.bind("<ButtonRelease-1>", release)

    top = ttk.Frame(root)
    top.pack()
    make_pad(top, "左摇杆 LS", "L")
    make_pad(top, "右摇杆 RS", "R")

    def make_trigger(parent, label: str, side: str) -> None:
        frame = ttk.LabelFrame(parent, text=label)
        frame.pack(fill=tk.X, padx=8, pady=2)
        value = tk.DoubleVar(value=0.0)
        keep = tk.BooleanVar(value=False)
        scale = ttk.Scale(
            frame,
            from_=0,
            to=100,
            orient=tk.HORIZONTAL,
            variable=value,
            command=lambda _v: state.set_trigger(side, value.get() / 100.0),
        )
        scale.pack(fill=tk.X, padx=6)

        def release(_event=None):
            if not keep.get():
                value.set(0.0)
                state.set_trigger(side, 0.0)

        scale.bind("<ButtonRelease-1>", release)
        ttk.Checkbutton(frame, text="保持", variable=keep).pack(anchor="w")

    make_trigger(root, "LT（左扳机）", "L")
    make_trigger(root, "RT（右扳机）", "R")

    buttons = ttk.LabelFrame(root, text="按钮（按住 = 按下；勾选 = 锁定按下）")
    buttons.pack(fill=tk.X, padx=8, pady=4)
    grid = ttk.Frame(buttons)
    grid.pack()
    for column, name in enumerate(BUTTON_NAMES):
        index = column
        locked = tk.BooleanVar(value=False)
        cell = ttk.Frame(grid)
        cell.grid(row=0, column=column, padx=2)
        button = tk.Button(cell, text=name, width=5)
        button.pack()
        button.bind("<ButtonPress-1>", lambda _e, i=index: state.set_button(i, 1))
        button.bind(
            "<ButtonRelease-1>", lambda _e, i=index, v=locked: state.set_button(i, 1 if v.get() else 0)
        )
        ttk.Checkbutton(
            cell, variable=locked, command=lambda i=index, v=locked: state.set_button(i, int(v.get()))
        ).pack()

    dpad = ttk.LabelFrame(root, text="DPad（axes[6] / axes[7]）")
    dpad.pack(padx=8, pady=4)
    dpad_grid = ttk.Frame(dpad)
    dpad_grid.pack()
    directions = [
        ("↖", -1, -1),
        ("↑", 0, -1),
        ("↗", 1, -1),
        ("←", -1, 0),
        ("●", 0, 0),
        ("→", 1, 0),
        ("↙", -1, 1),
        ("↓", 0, 1),
        ("↘", 1, 1),
    ]
    for index, (text, dx, dy) in enumerate(directions):
        tk.Button(dpad_grid, text=text, width=4, command=lambda x=dx, y=dy: state.set_dpad(x, y)).grid(
            row=index // 3, column=index % 3, padx=2, pady=2
        )

    bottom = ttk.Frame(root)
    bottom.pack(fill=tk.X, padx=8, pady=6)
    ttk.Button(bottom, text="全部归中 / 松开", command=state.reset).pack(side=tk.LEFT)
    ttk.Button(bottom, text="退出", command=root.destroy).pack(side=tk.RIGHT)

    info = tk.StringVar()
    ttk.Label(root, textvariable=info, justify=tk.LEFT, foreground="#444").pack(padx=8, pady=4)

    def refresh():
        lx, ly, rx, ry, lt, rt, (dx, dy), keys = state.snapshot()
        info.set(
            status
            + f"\nLS=({lx:+.2f},{ly:+.2f}) RS=({rx:+.2f},{ry:+.2f}) LT={lt:.2f} RT={rt:.2f} DPad=({dx},{dy})"
            + "\n按钮: " + "".join(str(k) for k in keys) + "  (" + " ".join(BUTTON_NAMES) + ")"
        )
        root.after(120, refresh)

    refresh()
    root.mainloop()


def main() -> int:
    parser = argparse.ArgumentParser(description="鼠标驱动的仿真 Xbox 360 手柄（uinput）")
    parser.add_argument("--hz", type=float, default=100.0, help="写 uinput 的频率")
    args = parser.parse_args()

    try:
        ui = build_uinput()
    except ImportError as exc:
        print(f"[xbox_sim_joy] 缺 python-evdev：{exc}（`pixi run …` 里有）")
        return 1
    except Exception as exc:  # noqa: BLE001
        # evdev 打不开 /dev/uinput 时抛的是 UInputError（不是 PermissionError），所以这里宽一点
        print(f"[xbox_sim_joy] 造不出 uinput 设备：{exc}\n{SETUP_HINT}")
        return 1

    state = XboxState()
    threading.Thread(target=uinput_loop, args=(ui, state, args.hz), daemon=True).start()
    status = (
        f"设备：{ui.name}  VID:PID = 045E:028E  节点 = {ui.device.path}\n"
        f"joy_node 会自动认出它（名字含 Xbox）；也可以 `jstest {ui.device.path.replace('event', 'js')}` 看原始值"
    )
    print("[xbox_sim_joy] " + status.replace("\n", " | "))
    build_gui(state, status)
    ui.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
