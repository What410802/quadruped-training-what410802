#!/usr/bin/env python3
"""自检：控制栈"没有反馈就什么都不跑"（S4 的反馈驱动时基，见 docs/porting.md §5）。

做法：起仿真 + rl_sim，按 A 让它进入起身斜坡；等斜坡真的在走（日志里出现 "Getting up x%"），
然后 `SIGSTOP` 仿真进程 1.5 s（墙钟，realtime 下约等于 1.5 s 仿真时间，足够走完半条斜坡），
看斜坡百分比有没有动：

* 反馈驱动（S4 之后）：停顿期间**没有 /motor_state**，控制一步都不跑 → 百分比不变 ✓
* 墙钟方案（S4 之前）：5 ms / 20 ms 两条墙钟循环照跑 → 百分比会涨到接近 100% ✗

停顿结束后再 `SIGCONT`，百分比必须继续走（证明不是"卡死"，只是"没时钟就不动"）。

用法（仓库根目录，先 `pixi run ros2-build`）：

    pixi run python @20261007_assignment/scripts/agent_scripts/check_feedback_clock.py
"""

from __future__ import annotations

import re
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TASK = ROOT / "@20261007_assignment"
LOG_DIR = TASK / "output" / "log"
RL_LOG = LOG_DIR / "check-feedback-clock-rl.log"
SIM_LOG = LOG_DIR / "check-feedback-clock-sim.log"
STOP_SECONDS = 1.5
PERCENT_RE = re.compile(r"Getting up ([0-9.]+)%")


def pkill(name: str) -> None:
    subprocess.run(["pkill", "-x", name], check=False)


def last_percent(text: str) -> float | None:
    found = PERCENT_RE.findall(text)
    return float(found[-1]) if found else None


def main() -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    pkill("rl_sim")
    pkill("sim_node")
    time.sleep(1.0)

    print("① 起仿真（realtime）与 rl_sim")
    sim = subprocess.Popen(
        ["ros2", "run", "quadruped_ros2", "sim_node", "--ros-args",
         "-p", "viewer:=false", "-p", "realtime:=true", "-p", "start:=rest"],
        stdout=SIM_LOG.open("w"), stderr=subprocess.STDOUT, start_new_session=True)
    time.sleep(7.0)
    rl = subprocess.Popen(["ros2", "run", "rl_sar", "rl_sim"],
                          stdout=RL_LOG.open("w"), stderr=subprocess.STDOUT, start_new_session=True)
    time.sleep(3.0)

    print("② 按 A → 等起身斜坡跑起来")
    joy = subprocess.Popen([sys.executable, "-c", """
import time, rclpy
from rclpy.node import Node
from sensor_msgs.msg import Joy
N = [0]*11; A = [1,0,0,0,0,0,0,0,0,0,0]
class P(Node):
    def __init__(self):
        super().__init__("feedback_clock_joy")
        self.pub = self.create_publisher(Joy, "/joy", 10)
        self.t0 = time.time()
        self.create_timer(0.01, self.tick)
    def tick(self):
        t = time.time() - self.t0
        if t >= 3.0:
            raise SystemExit(0)
        m = Joy(); m.axes = [0.0]*8; m.buttons = A if 0.5 <= t < 1.0 else N
        self.pub.publish(m)
rclpy.init(); rclpy.spin(P()); rclpy.shutdown()
"""], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)

    deadline = time.monotonic() + 12.0
    while time.monotonic() < deadline:
        if last_percent(RL_LOG.read_text(errors="replace")) is not None:
            break
        time.sleep(0.1)
    text = RL_LOG.read_text(errors="replace")
    if "RLFSMStatePassive to RLFSMStateGetUp" not in text:
        print("[FAIL] 12 s 内没进 GetUp（A 没生效？看 output/log/check-feedback-clock-rl.log）")
        return 1

    print(f"③ SIGSTOP 仿真 {STOP_SECONDS} s（斜坡只有 2 s，墙钟方案下会被它跑完）")
    before = last_percent(text)
    while before is None or before > 60.0:      # 等斜坡进入中段，留出"该涨"的余量
        time.sleep(0.05)
        before = last_percent(RL_LOG.read_text(errors="replace"))
        if before is None:
            break
    time.sleep(0.15)
    before = last_percent(RL_LOG.read_text(errors="replace"))
    # 注意：`ros2 run` 只是父进程，真正的节点是它的子进程 sim_node —— 信号要发给子进程，
    # 否则停的是 launcher，节点照跑（第一次就是这么测出"停顿期间斜坡还在涨"的假象）。
    if subprocess.run(["pgrep", "-x", "sim_node"], capture_output=True).returncode != 0:
        print("[FAIL] 没找到 sim_node 进程")
        return 1
    subprocess.run(["pkill", "-STOP", "-x", "sim_node"], check=False)
    time.sleep(STOP_SECONDS)
    stopped = last_percent(RL_LOG.read_text(errors="replace"))
    subprocess.run(["pkill", "-CONT", "-x", "sim_node"], check=False)

    print("④ SIGCONT → 斜坡必须继续")
    resumed = stopped
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        time.sleep(0.2)
        got = last_percent(RL_LOG.read_text(errors="replace"))
        if got is not None and got > resumed:
            resumed = got
        if resumed is not None and before is not None and resumed > before + 20.0:
            break

    # 停顿期间允许"在途/排队"的反馈带来一点点前进（实测 1.25%），但绝不该像墙钟方案那样
    # 1.5 s 就推进 ~75%（斜坡 2 s）。10 个百分点 = 200 ms 仿真时间，判别力足够。
    ok_stop = before is not None and stopped is not None and (stopped - before) < 10.0
    ok_resume = resumed is not None and before is not None and resumed > before + 20.0
    print(f"  [{'PASS' if ok_stop else 'FAIL'}] 停顿期间斜坡几乎不动（<10%）  停顿前 {before}% → 停顿 {STOP_SECONDS} s 后 {stopped}%")
    print(f"  [{'PASS' if ok_resume else 'FAIL'}] 恢复反馈后继续走   {stopped}% → SIGCONT 后 {resumed}%")

    joy.terminate()
    for proc in (rl, sim):
        proc.terminate()
    time.sleep(1.0)
    pkill("rl_sim")
    pkill("sim_node")

    if ok_stop and ok_resume:
        print("结论：全部通过 ✓（没有反馈就一步都不跑，反馈回来就接着跑）")
        return 0
    print("结论：有未通过项 ✗")
    return 1


if __name__ == "__main__":
    sys.exit(main())
