#!/usr/bin/env python3
"""分析 `motor_ctl` 的一次或多次运行日志（终端里 `... | tee <log>` 得到的文本，或是 dry run 的留档）。

用法（仓库根目录）：pixi run python @20260927_motor/scripts/agent_scripts/analyse_ctl_log.py <log.txt> [...]

它回答"实机记录表要填的那几栏"（表在 cpp_part2/docs/runbook.md §5）：

1. 每次运行的配置（增益、插值上限、offset 初值）与启动读数（q_enc / 区间 / pos raw）；
2. 每条命令与它对应的**到位结果**（末位置、与目标的差、到位 / 未到位）；
3. **零点跳变**修正了几次、每次的方向与时刻、offset 首末值；
4. 保护有没有触发（力矩卡住 / 掉线 / merror / 温度）、以及收尾是怎么退的；
5. 每个运行的**一行摘要**（可直接抄进记录表）+ 需要人工确认的疑点清单。

日志格式（`motor_ctl` 的标准输出，见 cpp_part2/README.md §6）：
    === S3–S5：... ===             ← 每个运行由此开始
    启动读数：pos 0 tick（= +0.000°，第 0 区、区内 +0.000°）、offset +0 tick（+0.000°） → q +0.000°
    命令#1："30"
       目标 +30.000°（现在 +0.000°）：要转 +30.00° ...
      ⇒ 到位（|差| ≤ 1.00°），保持中
      **零点跳变：Δpos +32768 tick = +1 个转子圈 ≈ +56.842° 输出端（残差 +0 tick）** 帧 39 t=0.200 s
        修正（运行中检测到）：offset +0 → -32768 tick（-1 个区间 = -56.842°）
    帧  100 t= 0.515：pos ... tick（...°、第 0 区） offset ...° → q ...°；目标 ... 差 ...；dq ...、tau ...、temp 30、merror 0
    === 汇总 ===
    帧 2284（回复 2284、超时 0）；q ...（首帧 ...、末帧 ...）；offset 末值 ...（... tick）；力矩峰值 ...；温度峰值 ...；末次 merror=0
    零点跳变修正 0 次；记号笔那个点 已记录；本次计划行程合计 90.0°；真实帧周期 5.309 ms（名义 5.0 ms）

退出码：0 = 每个运行都拿到了汇总（正常分析完）；2 = 没解析到任何运行；3 = 有的运行缺汇总/需要人工确认。
"""
import re
import sys
from pathlib import Path


RE_RUN_HEAD = re.compile(r"===\s*S3[–-]S5")
# 启动读数（tick 化之后的写法）：pos +17299 tick（= +30.008°，第 0 区、区内 +30.008°）、offset +0 tick（+0.000°） → q +30.008°
RE_START = re.compile(
    r"启动读数：pos\s*([+-]?\d+) tick（=\s*([+-][\d.]+)°，第\s*(-?\d+)\s*区、区内\s*([+-][\d.]+)°）、"
    r"offset\s*([+-]?\d+) tick（([+-][\d.]+)°）\s*→\s*q\s*([+-][\d.]+)°")
RE_CMD = re.compile(r"命令#(\d+)：\"(.*)\"")
RE_TARGET = re.compile(r"目标\s*([+-][\d.]+)°（现在\s*([+-][\d.]+)°）")
RE_ARRIVE = re.compile(r"⇒ 到位（\|差\| ≤ ([\d.]+)°）")
# 段 = 一条"目标"行到下一次"目标"行之间；段内的"⇒ 到位"就记在这条命令名下
RE_JUMP = re.compile(r"\*\*零点跳变：Δpos\s*([+-]?\d+) tick =\s*([+-]?\d+(?:\.\d+)?)\s*个转子圈 ≈\s*"
                     r"([+-][\d.]+)° 输出端（残差\s*([+-]?\d+) tick）\*\* 帧\s*(\d+) t=([\d.]+)\s*s")
RE_FIX = re.compile(r"修正（(.*?)）：offset\s*([+-]?\d+) →\s*([+-]?\d+) tick")
RE_STAT = re.compile(
    r"帧\s*(\d+)\s*t=\s*([\d.]+)：pos\s*([+-]?\d+) tick（\s*([+-][\d.]+)°、第\s*(-?\d+)\s*区）\s*"
    r"offset\s*([+-][\d.]+)°\s*→\s*q\s*([+-][\d.]+)°；目标\s*([+-][\d.]+)°\s*差\s*([+-][\d.]+)°；"
    r"dq\s*([+-][\d.]+)°/s、tau\s*([+-][\d.]+)\s*N·m[^、]*、temp\s*(\d+)、merror\s*(\d+)")
RE_SUM = re.compile(
    r"帧\s*(\d+)（回复\s*(\d+)、超时\s*(\d+)）；q\s*([+-][\d.]+)°…([+-][\d.]+)°（首帧\s*([+-][\d.]+)°、"
    r"末帧\s*([+-][\d.]+)°）；offset 末值\s*([+-][\d.]+)°（([+-]\d+) tick）；力矩峰值\s*([\d.-]+)\s*N·m（"
    r"保持时\s*([\d.-]+)）；温度峰值\s*(-?\d+)\s*°C；末次 merror=(\d+)")
RE_SUM2 = re.compile(r"零点跳变修正\s*(\d+)\s*次；记号笔那个点\s*(已记录|未记录[^；]*?)；本次计划行程合计\s*([\d.]+)°；真实帧周期\s*([\d.]+)\s*ms")
RE_GAIN = re.compile(r"增益：输出端 kp=(\S+)\s*kd=(\S+)\s*→\s*转子侧 K_P=(\S+)\s*K_W=(\S+)；力矩上限\s*(\S+)\s*N·m")
RE_CFG = re.compile(r"插值 vmax=(\d+)°/s、amax=(\d+)°/s²、到位判据 ([\d.]+)°")
RE_PROTECT = [
    ("力矩卡住", re.compile(r"\*\*力矩连续.*超过上限")),
    ("掉线（连续无回复）", re.compile(r"\*\*连续 \d+ 帧无回复")),
    ("电机报错 merror", re.compile(r"\*\*电机报错 merror=")),
    ("温度偏高", re.compile(r"\*\*温度 \d+ °C 偏高\*\*")),
    ("跳变次数用尽", re.compile(r"\*\*跳变次数超过")),
    ("启动检查报认错零点", re.compile(r"疑似上电认错零点")),
    ("启动检查：不是整数个区间", re.compile(r"先别动电机")),
    ("力矩接近上限（单帧）", re.compile(r"← 力矩接近上限")),
]
RE_TAIL = [
    ("正常收尾", re.compile(r"收尾：已发 \d+ 帧零力矩")),
    ("脚本跑完收尾", re.compile(r"脚本跑完.*⇒ 收尾退出")),
    ("--seconds 到点收尾", re.compile(r"--seconds [\d.]+ 到 ⇒ 收尾退出")),
    ("用户 q 退出", re.compile(r"退出：先发零力矩")),
]


def split_runs(text):
    """按 '=== S3–S5' 把日志切成一串运行；每段带上它前面的命令注释行。"""
    lines = text.splitlines()
    starts = [i for i, ln in enumerate(lines) if RE_RUN_HEAD.search(ln)]
    if not starts:
        return []
    runs = []
    for idx, s in enumerate(starts):
        e = starts[idx + 1] if idx + 1 < len(starts) else len(lines)
        head = lines[s]
        # 往上看：最近的以 '$' 开头的行 = 这次运行的命令行（可能没有）
        cmd = ""
        for j in range(s - 1, max(-1, s - 6), -1):
            if lines[j].startswith("$"):
                cmd = lines[j].lstrip("$ ").strip()
                break
        runs.append({"head": head, "cmd": cmd, "lines": lines[s:e]})
    return runs


def parse_run(run):
    r = {
        "命令": [], "跳变": [], "修正": [], "保护": [], "收尾": [],
        "状态行": 0, "首次状态": None, "末次状态": None, "到位次数": 0,
        "启动": None, "汇总": None, "汇总2": None, "增益": None, "cfg": None,
        "命令_目标": [],
        "段": [],
    }
    for ln in run["lines"]:
        if m := RE_START.search(ln):
            r["启动"] = {
                "pos_tick": int(m.group(1)), "pos_deg": float(m.group(2)), "区": int(m.group(3)),
                "区内": float(m.group(4)), "offset_tick": int(m.group(5)),
                "offset_deg": float(m.group(6)), "q_deg": float(m.group(7)),
            }
        if m := RE_GAIN.search(ln):
            r["增益"] = {"kp": m.group(1), "kd": m.group(2), "tau_limit": m.group(5)}
        if m := RE_CFG.search(ln):
            r["cfg"] = {"vmax": m.group(1), "amax": m.group(2), "tol": m.group(3)}
        if m := RE_CMD.search(ln):
            r["命令"].append(m.group(2))
        if m := RE_TARGET.search(ln):
            # 每条"目标"行开一个新段；段内的"到位"记在这条命令名下
            r["段"].append({"目标": float(m.group(1)), "起点": float(m.group(2)), "到位": False,
                            "到位次数": 0, "末差": None})
        if (m := RE_ARRIVE.search(ln)) and r["段"]:
            r["段"][-1]["到位"] = True
            r["段"][-1]["到位次数"] += 1
            r["到位次数"] += 1
        if m := RE_JUMP.search(ln):
            r["跳变"].append({"raw": int(m.group(1)), "圈": float(m.group(2)), "deg": float(m.group(3)),
                              "残差tick": int(m.group(4)), "帧": int(m.group(5)), "t": float(m.group(6))})
        if m := RE_FIX.search(ln):
            r["修正"].append({"why": m.group(1), "from_tick": int(m.group(2)), "to_tick": int(m.group(3))})
        if m := RE_STAT.search(ln):
            r["状态行"] += 1
            st = {"帧": int(m.group(1)), "t": float(m.group(2)), "pos_tick": int(m.group(3)),
                  "pos_deg": float(m.group(4)), "区": int(m.group(5)), "offset": float(m.group(6)),
                  "q": float(m.group(7)), "目标": float(m.group(8)), "差": float(m.group(9)),
                  "dq": float(m.group(10)), "tau": float(m.group(11)), "temp": int(m.group(12)),
                  "merror": int(m.group(13))}
            if r["首次状态"] is None:
                r["首次状态"] = st
            r["末次状态"] = st
        if m := RE_SUM.search(ln):
            r["汇总"] = {"帧": int(m.group(1)), "回复": int(m.group(2)), "超时": int(m.group(3)),
                         "q_min": float(m.group(4)), "q_max": float(m.group(5)),
                         "首帧": float(m.group(6)), "末帧": float(m.group(7)),
                         "offset末": float(m.group(8)), "offset末tick": int(m.group(9)),
                         "tau峰": float(m.group(10)), "tau保持": float(m.group(11)),
                         "temp峰": int(m.group(12)), "merror": int(m.group(13))}
        if m := RE_SUM2.search(ln):
            r["汇总2"] = {"修正次数": int(m.group(1)), "记号笔": m.group(2),
                          "行程": float(m.group(3)), "帧周期ms": float(m.group(4))}
        for name, rx in RE_PROTECT:
            if rx.search(ln) and name not in r["保护"]:
                r["保护"].append(name)
        for name, rx in RE_TAIL:
            if rx.search(ln) and name not in r["收尾"]:
                r["收尾"].append(name)
    return r


def fmt(v, w=8, p=3):
    return f"{v:+{w}.{p}f}"


def report(path, runs):
    print(f"文件 {path}：{len(runs)} 个运行")
    need_check = []
    for i, run in enumerate(runs, 1):
        r = parse_run(run)
        print()
        print(f"—— 运行 #{i} ——")
        if run["cmd"]:
            print(f"  命令：{run['cmd']}")
        if r["增益"]:
            g = r["增益"]
            print(f"  配置：kp={g['kp']} kd={g['kd']}（输出端）、力矩上限 {g['tau_limit']} N·m"
                  + (f"、vmax={r['cfg']['vmax']}°/s、amax={r['cfg']['amax']}°/s²、到位判据 {r['cfg']['tol']}°" if r["cfg"] else ""))
        if r["启动"]:
            s = r["启动"]
            print(f"  启动：pos {s['pos_tick']:+d} tick（{fmt(s['pos_deg'])}°，第 {s['区']} 区、"
                  f"区内 {s['区内']:+.3f}°）、offset {s['offset_tick']:+d} tick（{fmt(s['offset_deg'])}°）"
                  f" → q {fmt(s['q_deg'])}°")
        if r["命令"]:
            print(f"  命令 {len(r['命令'])} 条：{' / '.join(r['命令'])}")
        if r["命令_目标"]:
            print(f"  目标角度：{' / '.join(f'{t:+.2f}°' for t, _ in r['命令_目标'])}")

        # 每条命令的到位情况（段 = 一条"目标"行到下一次"目标"行之间）
        if r["段"]:
            print(f"  各段（共 {len(r['段'])} 条目标、{r['到位次数']} 次「到位」）：")
            for k, row in enumerate(r["段"], 1):
                flag = "到位" if row["到位"] else "**未见到位**"
                if row["到位次数"] > 1:
                    flag += f"（{row['到位次数']} 次）"
                print(f"    {k}. 目标 {row['目标']:+.3f}°（从 {row['起点']:+.3f}° 出发）→ {flag}")

        if r["跳变"]:
            print(f"  零点跳变 {len(r['跳变'])} 次：")
            for j in r["跳变"]:
                print(f"    Δpos {j['raw']:+d} tick（{j['圈']:+.0f} 个转子圈 ≈ {j['deg']:+.3f}°，残差 "
                      f"{j['残差tick']:+d} tick）帧 {j['帧']} t={j['t']:.3f} s")
        if r["修正"]:
            for f in r["修正"]:
                print(f"    修正（{f['why']}）：offset {f['from_tick']:+d} → {f['to_tick']:+d} tick"
                      f"（{f['to_tick'] / 32768 * 360 / (19 / 3):+.3f}°）")
        if r["保护"]:
            print(f"  ⚠ 触发/出现过：{'、'.join(r['保护'])}")
        if r["收尾"]:
            print(f"  收尾：{'、'.join(r['收尾'])}")
        if r["汇总"]:
            s = r["汇总"]
            print(f"  汇总：帧 {s['帧']}（回复 {s['回复']}、超时 {s['超时']}）、"
                  f"q {fmt(s['q_min'])}°…{fmt(s['q_max'])}°（末帧 {fmt(s['末帧'])}°）、"
                  f"offset 末值 {fmt(s['offset末'])}°（{s['offset末tick']:+d} tick）、"
                  f"力矩峰 {s['tau峰']:.3f} N·m（保持 {s['tau保持']:.3f}）、"
                  f"温度峰 {s['temp峰']} °C、merror {s['merror']}")
        if r["汇总2"]:
            s2 = r["汇总2"]
            print(f"        跳变修正 {s2['修正次数']} 次、记号笔 {s2['记号笔']}、行程合计 {s2['行程']}°、"
                  f"帧周期 {s2['帧周期ms']} ms")
        if not r["汇总"] or not r["汇总2"]:
            need_check.append(f"运行 #{i} 缺「汇总」行（进程被 Ctrl-C？日志被截断？）")
        if r["汇总"] and r["汇总"]["超时"] > 0:
            need_check.append(f"运行 #{i} 有 {r['汇总']['超时']} 帧超时")
        if r["汇总"] and r["汇总"]["merror"] != 0:
            need_check.append(f"运行 #{i} 末次 merror={r['汇总']['merror']}")
        if r["保护"]:
            need_check.append(f"运行 #{i} 触发了保护：{'、'.join(r['保护'])}")
        missing = [row for row in r["段"] if not row["到位"]]
        if missing:
            need_check.append("运行 #%d 有 %d 条目标没记到「到位」：%s" % (
                i, len(missing), "、".join(f"{row['目标']:+.2f}°" for row in missing)))

        # 一行摘要（抄进 runbook §5 的记录表）
        if r["汇总"]:
            s = r["汇总"]
            print("  ⇩ 记录表可用的一行：")
            fix_n = r["汇总2"]["修正次数"] if r["汇总2"] else len(r["修正"])
            print(f"    {'/'.join(r['命令']) or '（无命令）'} | 末位置 {s['末帧']:+.3f}° | "
                  f"offset {s['offset末']:+.3f}° | 跳变修正 {fix_n} 次（运行中 {len(r['跳变'])} 次） | "
                  f"力矩峰 {s['tau峰']:.3f} N·m | temp {s['temp峰']} °C | 超时 {s['超时']} | "
                  f"帧周期 {r['汇总2']['帧周期ms'] if r['汇总2'] else '?'} ms")

    print()
    if need_check:
        print("需要人工确认：")
        for c in need_check:
            print(f"  - {c}")
        return 3
    print("结论：每个运行都拿到了汇总、没有超时/保护/merror ⇒ 可以按上面的摘要填记录表。")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    rc = 0
    for arg in sys.argv[1:]:
        path = Path(arg)
        if not path.exists():
            print(f"{path}：文件不存在")
            rc = 3
            continue
        runs = split_runs(path.read_text(encoding="utf-8", errors="replace"))
        if not runs:
            print(f"{path}：没解析到任何运行（日志里没有「=== S3–S5」这一行？）")
            rc = 3
            continue
        rc = max(rc, report(path, runs))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
