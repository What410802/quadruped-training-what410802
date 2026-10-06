#!/usr/bin/env python3
"""无头自检：不接手柄、不开窗口，把"控制器 ⇄ 仿真"整条链路跑一遍并判定（退出码 0/1）。

它做的事 = 人工验收那套的最小自动化版本：

    1. 起 sim_node（viewer:=false，起点默认 raw，按真实时间节流）
    2. 起 controller_node
    3. 用 scripts/pub_joy_sequence.py 按脚本发 /joy：1:A（站立）→ 6:B（阻尼）→ 8:X（复位）→ 9:A（再站立）
    4. 读仿真节点打印的状态行（`t=… z=… tilt=… ncon=… cmd=…`）判定：

       * 两条 /mit_command 都在发（cmd=ok，没有触发看门狗）；
       * A 之后 2 s 内站起来：基座 z > 0.37 m、四足触地（ncon == 4）、倾角 < 10°；
       * B 之后塌回趴卧：z < 0.16 m；
       * X 复位后又回到趴卧；
       * 第二次 A 再站起来，末态 z 与第一次一致（±2 mm）；
       * 实时率 ≥ 0.9x（控制回路没被顶住）。

用法（仓库根目录）：

    pixi run python @20261005_ros2/scripts/check_headless.py
    pixi run python @20261005_ros2/scripts/check_headless.py --keep-logs   # 保留日志
"""

from __future__ import annotations

import argparse
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # @20261005_ros2/
LOG_DIR = ROOT / "output" / "log"

STATUS_RE = re.compile(r"^t=(?P<t>[\d.]+) z=(?P<z>[\d.-]+) tilt=(?P<tilt>[\d.-]+) ncon=(?P<ncon>\d+) cmd=(?P<cmd>\w+)")
RATE_RE = re.compile(r"= (?P<rate>[\d.]+)x 实时")

# 自检脚本里的时间线（秒，从"发序列"那一刻算起）——与 pub_joy_sequence.py 的默认序列一致
SEQUENCE = "1:A,6:B,8:X,9:A"
TOTAL_SECONDS = 13.0

STAND_Z_MIN = 0.37  # 站起来后基座高度下限 [m]（上一版实测稳态 0.3836）
LIE_Z_MAX = 0.16  # 趴卧时基座高度上限 [m]（场景 rest keyframe 实测 0.1449）
TILT_MAX_DEG = 10.0  # 站着时倾角上限
RATE_MIN = 0.9  # 实时率下限


class Result:
    def __init__(self) -> None:
        self.rows: list[tuple[bool, str, str]] = []

    def check(self, ok: bool, name: str, detail: str) -> None:
        self.rows.append((ok, name, detail))

    def report(self) -> bool:
        width = max(len(name) for _, name, _ in self.rows)
        print("\n================ 自检结果 ================")
        for ok, name, detail in self.rows:
            print(f"[{'PASS' if ok else 'FAIL'}] {name.ljust(width)}  {detail}")
        passed = all(ok for ok, _, _ in self.rows)
        print("==========================================")
        print("结论：" + ("全部通过 ✓" if passed else "有失败项 ✗"))
        return passed


def start(args: list[str], log: Path) -> subprocess.Popen:
    print(f"  $ {' '.join(args)}  > {log}")
    handle = log.open("w", encoding="utf-8")
    return subprocess.Popen(args, stdout=handle, stderr=subprocess.STDOUT, start_new_session=True)


def stop(proc: subprocess.Popen) -> None:
    """停掉 proc **连同它整组**：`ros2 run` 只是壳，节点是它的子进程，
    只杀壳会留下孤儿节点继续写日志、继续发话题（下一轮自检就会读到上一轮的轨迹）。"""
    if proc.poll() is None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGINT)
            proc.wait(timeout=5)
        except (subprocess.TimeoutExpired, ProcessLookupError, PermissionError):
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass


def running_nodes() -> list[tuple[int, str]]:
    """正在跑的本任务节点（自检会跟它们抢同一批话题/服务）。

    两条都要看，缺一不可（都踩过）：
      * **exe**：C++ 节点是自己的可执行文件，`--symlink-install` 下解析到 `ws/build/...`，
        二进制被重新编译过时还会带 " (deleted)" 后缀；
      * **cmdline**：`joy_node` 是**Python 脚本**，`/proc/<pid>/exe` 指向 `python3`，
        光看 exe 名字会把正在跑的 joy_node 漏掉（实测：漏掉的那个孤儿让 `ros2 node list`
        里出现了两个 `/joy_node`，也让本函数没能拦住后一次自检）。启动命令是
        `python3 <install>/lib/quadruped_ros2/joy_node …`，按这个安装路径认。
    """
    found = []
    for entry in Path("/proc").glob("[0-9]*"):
        pid = int(entry.name)
        if pid == os.getpid():
            continue
        exe = ""
        try:
            exe = os.readlink(entry / "exe").replace(" (deleted)", "")
        except OSError:
            pass
        try:
            cmdline = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
        except OSError:
            cmdline = ""
        name = os.path.basename(exe)
        if name in ("sim_node", "controller_node", "joy_node") and "quadruped_ros2" in exe:
            found.append((pid, name))
        elif "lib/quadruped_ros2/joy_node" in cmdline:
            found.append((pid, "joy_node"))
    return found


def guard_no_running_nodes(force: bool) -> bool:
    """默认**不动**别人正在跑的节点，只提示；`--force` 才替你清掉。

    为什么改：早期版本一律 SIGKILL 掉这些节点，结果在 2026-10-06 实测中，恰好有人在
    `ros2 launch …` 看着狗跑的时候被这个脚本杀了——launch 报 `exit code -9`、MuJoCo 窗口
    一起消失（那是自检脚本干的，不是节点不稳定）。自检是**测试**工具，不该管别人的进程。
    """
    running = running_nodes()
    if not running:
        return True
    detail = "、".join(f"{name}(pid {pid})" for pid, name in running)
    if not force:
        print(f"[FAIL] 已经有本任务的节点在跑：{detail}")
        print("       自检会和它们抢同一批话题 / 服务，所以默认不动它们。")
        print("       先停掉那个 launch（Ctrl-C），或者加 --force 让自检替你清掉。")
        return False
    for pid, name in running:
        print(f"  （--force：清掉 {name} pid {pid}）")
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    time.sleep(0.5)
    return True


def parse_status(log: Path) -> list[dict]:
    rows = []
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        match = STATUS_RE.search(line)
        if match:
            rows.append(
                {
                    "t": float(match.group("t")),
                    "z": float(match.group("z")),
                    "tilt": float(match.group("tilt")),
                    "ncon": int(match.group("ncon")),
                    "cmd": match.group("cmd"),
                }
            )
    return rows


def find_events(rows: list[dict], low: float, high: float) -> list[dict]:
    """从 z 的轨迹里挑出"站起来 / 塌下去"两类事件，**不假设脚本与仿真的时间轴对齐**。

    ROS 节点启动本身要一两秒，"发序列"那一刻对应的仿真时刻没法写死，所以只看形状：
    z 从 <low 升到 >high 记一次 stand，从 >high 掉回 <low 记一次 lie。
    返回 [{kind, t, rise_s, peak_z, ncon, tilt}]：
      * stand：t = 最后一次"确实趴着"的时刻（起身起点），rise_s = 越过 low 到越过 high 的用时，
        peak_z / ncon / tilt = 这次站立期间的峰值与峰值处的读数；
      * lie：t = 掉回趴卧的时刻。
    """
    events: list[dict] = []
    standing = False
    rise_t0 = 0.0
    peak = 0.0
    peak_row: dict | None = None
    for row in rows:
        if not standing:
            if row["z"] > high:
                standing = True
                events.append(
                    {
                        "kind": "stand",
                        "t": rise_t0,
                        "rise_s": row["t"] - rise_t0,
                        "peak_z": peak,
                        "ncon": 0,
                        "tilt": 0.0,
                    }
                )
            elif row["z"] < low:
                rise_t0 = row["t"]  # 最近一次确认趴着的时刻 = 起身起点
                peak = 0.0
                peak_row = None
        else:
            if row["z"] > peak:
                peak, peak_row = row["z"], row
            if row["z"] < low:
                standing = False
                if events:
                    events[-1].update(
                        peak_z=peak,
                        ncon=peak_row["ncon"] if peak_row else 0,
                        tilt=peak_row["tilt"] if peak_row else 0.0,
                    )
                events.append({"kind": "lie", "t": row["t"], "rise_s": 0.0, "peak_z": 0.0,
                               "ncon": 0, "tilt": 0.0})
                rise_t0 = row["t"]
    if standing and events:
        events[-1].update(
            peak_z=peak, ncon=peak_row["ncon"] if peak_row else 0,
            tilt=peak_row["tilt"] if peak_row else 0.0,
        )
    return events


def main() -> int:
    parser = argparse.ArgumentParser(description="无头自检（控制器 ⇄ 仿真 + 脚本化 /joy）")
    parser.add_argument("--keep-logs", action="store_true", help="保留日志（默认也保留，打印路径）")
    parser.add_argument("--start", default="raw", help="仿真起点：raw（默认，与节点默认一致）/ rest")
    parser.add_argument("--force", action="store_true",
                        help="清掉已经在跑的本任务节点再自检（默认只提示、不动它们）")
    args = parser.parse_args()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    sim_log = LOG_DIR / "check-headless-sim.log"
    ctl_log = LOG_DIR / "check-headless-controller.log"
    joy_log = LOG_DIR / "check-headless-joy-sequence.log"

    print(f"日志目录：{LOG_DIR}")
    print("⓪ 确认没有别的节点在跑")
    if not guard_no_running_nodes(args.force):
        return 1
    print("① 起 sim_node / controller_node（无窗口）")
    sim = start(
        ["ros2", "run", "quadruped_ros2", "sim_node", "--ros-args", "-p", "viewer:=false", "-p",
         "status_period_s:=0.5", "-p", f"start:={args.start}"],
        sim_log,
    )
    time.sleep(3.0)
    ctl = start(["ros2", "run", "quadruped_ros2", "controller_node"], ctl_log)
    time.sleep(2.0)

    print("② 按脚本发 /joy：" + SEQUENCE)
    joy = start(
        ["python", str(ROOT / "scripts" / "pub_joy_sequence.py"), "--sequence", SEQUENCE,
         "--seconds", str(TOTAL_SECONDS)],
        joy_log,
    )
    joy.wait(timeout=TOTAL_SECONDS + 20)
    time.sleep(1.0)
    stop(ctl)
    stop(sim)

    rows = parse_status(sim_log)
    text = sim_log.read_text(encoding="utf-8", errors="replace")
    rates = [float(m.group("rate")) for m in RATE_RE.finditer(text)]
    events = find_events(rows, LIE_Z_MAX, STAND_Z_MIN)
    stands = [e for e in events if e["kind"] == "stand"]
    lies = [e for e in events if e["kind"] == "lie"]
    ok_rows = [r for r in rows if r["cmd"] == "ok"]
    damping_rows = [r for r in rows if r["cmd"] == "damping"]
    result = Result()

    result.check(bool(rows), "仿真节点打了状态行", f"共 {len(rows)} 行（{sim_log.name}）")
    first_ok = next((i for i, r in enumerate(rows) if r["cmd"] == "ok"), None)
    damping_after_ok = (
        [r for r in rows[first_ok:] if r["cmd"] == "damping"] if first_ok is not None else rows
    )
    result.check(
        first_ok is not None and not damping_after_ok,
        "MIT 指令一直跟得上（只有控制器起来之前是阻尼）",
        f"启动阶段阻尼 {first_ok if first_ok is not None else len(rows)} 行，之后 cmd=ok {len(ok_rows)} 行",
    )
    result.check("看门狗" not in text, "没有出现看门狗超时", "日志里没有「看门狗」字样")

    result.check(len(stands) >= 2, "①④ 两次 A 都让狗站起来了", f"检出 {len(stands)} 次起身、{len(lies)} 次塌下")
    if stands:
        first, last = stands[0], stands[-1]
        result.check(
            first["peak_z"] > STAND_Z_MIN and first["ncon"] == 4,
            "① 第一次起身：高度达标且四足触地",
            f"峰值 z={first['peak_z']:.4f} m、接触点={first['ncon']}、倾角={first['tilt']:.1f}°、"
            f"用时 {first['rise_s']:.2f} s",
        )
        result.check(abs(first["tilt"]) < TILT_MAX_DEG, "① 站起来后机身没翻",
                     f"峰值处倾角 {first['tilt']:.1f}°")
        if len(stands) >= 2:
            result.check(
                abs(first["peak_z"] - last["peak_z"]) < 0.002,
                "两次站立的稳态高度一致（可复现）",
                f"{first['peak_z']:.4f} m vs {last['peak_z']:.4f} m",
            )
    result.check(bool(lies), "② B（阻尼）：中间塌回趴卧", f"检出 {len(lies)} 次塌下")
    if rows:
        result.check(rows[-1]["z"] > STAND_Z_MIN, "③ 末态：X 复位后再按 A 又站住了",
                     f"末条 z={rows[-1]['z']:.4f} m、倾角={rows[-1]['tilt']:.1f}°")
    result.check(bool(rates) and min(rates) >= RATE_MIN, "实时率达标（控制回路没被顶住）",
                 "、".join(f"{r:.3f}x" for r in rates) or "没量到")

    passed = result.report()
    if not args.keep_logs:
        print("（日志已保留在 output/log/，--keep-logs 只影响是否额外提示）")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
