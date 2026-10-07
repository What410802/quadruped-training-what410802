#!/usr/bin/env python3
"""仿真手柄**端到端**自检：/dev/uinput → joy_node → /joy → 控制器 → 狗起身/趴下。

与 [`check_headless.py`](check_headless.py) 的区别：那条是"脚本直接发 /joy"，绕过了设备层；
这条**真的造一个内核输入设备**（用 [`../../sim_joy/xbox_sim_joy.py`](../../sim_joy/xbox_sim_joy.py)
的 uinput 部分，但不点 GUI——直接程序化按按钮），让 `joy_node` 从 /dev/input 里认领它。
所以它验证的是"真手柄插上也能用"的那条路径。

前提：先跑一次 `sudo scripts/setup_joy_devices.sh`（原因见 [`../../docs/joystick.md`](../../docs/joystick.md) §2）。
用法（仓库根）：

    pixi run python @20261005_ros2/scripts/agent_scripts/check_joystick_device.py

判定：joy_node 认到设备 → /joy 上看到 A/B/X 各按下过 → 仿真里两次起身、一次塌下、
末态高度与上次一致 → 没有看门狗。
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Joy

ROOT = Path(__file__).resolve().parents[2]  # @20261005_ros2/（本文件在 scripts/agent_scripts/ 下）
LOG_DIR = ROOT / "output" / "log"
SIM_JOY = ROOT / "sim_joy" / "xbox_sim_joy.py"

STAND_Z_MIN = 0.37
LIE_Z_MAX = 0.16
BUTTONS = {"A": 0, "B": 1, "X": 2}

# (时刻 s, 动作)：按下 0.3 s 就松开（控制器只认按下沿）
SEQUENCE = [(1.0, "A"), (7.0, "B"), (10.0, "X"), (11.0, "A")]
PRESS_SECONDS = 0.3
TOTAL_SECONDS = 18.0


def load_sim_joy():
    spec = importlib.util.spec_from_file_location("xbox_sim_joy", SIM_JOY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class JoyProbe(Node):
    """订 /joy，记下都收到了什么（哪一帧 buttons 哪个键被按下）。"""

    def __init__(self) -> None:
        super().__init__("check_joystick_probe")
        self.frames = 0
        self.pressed: set[int] = set()
        self.frame_ids: set[str] = set()
        self.create_subscription(Joy, "joy", self.on_joy, 1)

    def on_joy(self, msg: Joy) -> None:
        self.frames += 1
        self.frame_ids.add(msg.header.frame_id)
        for index, value in enumerate(msg.buttons):
            if value:
                self.pressed.add(index)


def start(args: list[str], log: Path) -> subprocess.Popen:
    print(f"  $ {' '.join(args)}  > {log}")
    handle = log.open("w", encoding="utf-8")
    return subprocess.Popen(args, stdout=handle, stderr=subprocess.STDOUT, start_new_session=True)


def stop(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGINT)
            proc.wait(timeout=5)
        except (subprocess.TimeoutExpired, ProcessLookupError, PermissionError):
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass


def check_no_running_nodes(force: bool) -> bool:
    """与 check_headless.py 共用同一道守卫：默认不动别人正在跑的节点。"""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from check_headless import guard_no_running_nodes

    return guard_no_running_nodes(force)


def check_uinput() -> bool:
    if not os.access("/dev/uinput", os.W_OK):
        print("[FAIL] 写不了 /dev/uinput：先跑一次\n    sudo @20261005_ros2/scripts/setup_joy_devices.sh")
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="仿真手柄端到端自检")
    parser.add_argument("--force", action="store_true",
                        help="清掉已经在跑的本任务节点再自检（默认只提示、不动它们）")
    args = parser.parse_args()

    if not check_no_running_nodes(args.force):
        return 1
    if not check_uinput():
        return 1

    sim_joy = load_sim_joy()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    sim_log = LOG_DIR / "check-joy-sim.log"
    ctl_log = LOG_DIR / "check-joy-controller.log"
    joy_log = LOG_DIR / "check-joy-node.log"

    rclpy.init()
    probe = JoyProbe()

    print("① 起 sim_node / controller_node，并先造好这个自检自己的仿真手柄")
    sim = start(
        ["ros2", "run", "quadruped_ros2", "sim_node", "--ros-args", "-p", "viewer:=false", "-p",
         "status_period_s:=0.5", "-p", "start:=rest"],
        sim_log,
    )
    time.sleep(3.0)
    ctl = start(["ros2", "run", "quadruped_ros2", "controller_node"], ctl_log)

    # **先把 uinput 设备造出来**：手柄节点要用 `-p device:=` 钉住它。
    # 不钉的话，机器上还插着实体手柄时，节点会按路径顺序认领到真手柄（实测踩过：
    # 真手柄是 event15、仿真手柄新分配 event16），于是脚本按的按钮根本没进 /joy。
    ui = sim_joy.build_uinput()
    state = sim_joy.XboxState()
    threading.Thread(target=sim_joy.uinput_loop, args=(ui, state, 100.0), daemon=True).start()
    print(f"  仿真手柄：{ui.name} → {ui.device.path}")

    print("② 起 joy_node（钉住上面那个设备）并等它认领")
    joy = start(
        ["ros2", "run", "quadruped_ros2", "joy_node", "--ros-args", "-p",
         f"device:={ui.device.path}"],
        joy_log,
    )
    time.sleep(2.0)

    connected = False
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        rclpy.spin_once(probe, timeout_sec=0.1)
        # 认领的必须是**我们造的这台**：只看到"手柄已连接"不够（那可能是真手柄）
        if any("手柄已连接" in line and ui.name in line
               for line in joy_log.read_text(encoding="utf-8", errors="replace").splitlines()):
            connected = True
            break
    print(f"  joy_node 认领：{'是' if connected else '否'}")
    dev_line = next(
        (line for line in joy_log.read_text(encoding="utf-8", errors="replace").splitlines()
         if "手柄已连接" in line and ui.name in line),
        "",
    )
    dev_line = dev_line.replace(str(joy_log), "")

    print("③ 按序列驱动：A(站立) → B(阻尼) → X(复位) → A(再站立)")
    start_time = time.monotonic()
    next_step = 0
    pressed: str | None = None
    release_at = 0.0
    while True:
        now = time.monotonic() - start_time
        if now >= TOTAL_SECONDS:
            break
        if next_step < len(SEQUENCE) and now >= SEQUENCE[next_step][0]:
            pressed = SEQUENCE[next_step][1]
            release_at = now + PRESS_SECONDS
            state.set_button(BUTTONS[pressed], 1)
            print(f"  t={now:5.2f}s 按下 {pressed}")
            next_step += 1
        if pressed is not None and now >= release_at:
            state.set_button(BUTTONS[pressed], 0)
            pressed = None
        rclpy.spin_once(probe, timeout_sec=0.0)
        time.sleep(0.01)

    state.set_button(BUTTONS["A"], 0)
    time.sleep(0.5)
    stop(joy)
    stop(ctl)
    stop(sim)
    ui.close()
    probe.destroy_node()
    rclpy.shutdown()

    # ------------------------------------------------ 判定
    sim_text = sim_log.read_text(encoding="utf-8", errors="replace")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from check_headless import TILT_MAX_DEG, find_events, parse_status  # 复用同一套轨迹判定

    rows = parse_status(sim_log)
    events = find_events(rows, LIE_Z_MAX, STAND_Z_MIN)
    stands = [e for e in events if e["kind"] == "stand"]
    lies = [e for e in events if e["kind"] == "lie"]

    rows_out: list[tuple[bool, str, str]] = []
    rows_out.append((connected, "joy_node 认到仿真手柄", dev_line.strip() or "没认到"))
    rows_out.append(
        (all(index in probe.pressed for index in BUTTONS.values()), "/joy 上看到 A/B/X 各按下过",
         f"buttons 收到 {sorted(probe.pressed)}（A=0 B=1 X=2），共 {probe.frames} 帧"),
    )
    rows_out.append(
        (any(fid.startswith("joy_connected") for fid in probe.frame_ids),
         "/joy 的 frame_id 标了已连接", "；".join(sorted(probe.frame_ids))[:60]),
    )
    rows_out.append((len(stands) >= 2 and len(lies) >= 1, "手柄按键 → 狗起身/趴下/再起身",
                     f"检出 {len(stands)} 次起身、{len(lies)} 次塌下"))
    if stands:
        rows_out.append(
            (stands[0]["peak_z"] > STAND_Z_MIN and stands[0]["ncon"] == 4,
             "站起来的高度与四足触地", f"峰值 z={stands[0]['peak_z']:.4f} m、接触点={stands[0]['ncon']}"),
        )
        rows_out.append((stands[0]["tilt"] < TILT_MAX_DEG,
                         "机身没翻", f"峰值处倾角 {stands[0]['tilt']:.1f}°"))
        if len(stands) >= 2:
            rows_out.append(
                (abs(stands[0]["peak_z"] - stands[-1]["peak_z"]) < 0.002,
                 "两次站立稳态高度一致", f"{stands[0]['peak_z']:.4f} vs {stands[-1]['peak_z']:.4f} m"),
            )
    rows_out.append(("看门狗" not in sim_text, "没有触发看门狗", "仿真日志里没有「看门狗」"))

    width = max(len(name) for _, name, _ in rows_out)
    print("\n================ 手柄端到端自检 ================")
    for ok, name, detail in rows_out:
        print(f"[{'PASS' if ok else 'FAIL'}] {name.ljust(width)}  {detail}")
    print("===============================================")
    passed = all(ok for ok, _, _ in rows_out)
    print("结论：" + ("全部通过 ✓" if passed else "有失败项 ✗"))
    print(f"日志：{LOG_DIR}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
