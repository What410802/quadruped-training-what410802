#!/usr/bin/env python3
"""分析 S2 的 `serial_probe --watch --log` 日志：手转输出端时读数到底长什么样。

用法（仓库根目录）：pixi run python @20260927_motor/scripts/agent_scripts/analyse_watch_log.py <log.csv>

日志格式（`--log` 写出来的，每帧一行 CSV，另加 `MARK,...` 行）：
    # frame,t,q_raw,q_rotor_rad,out_deg,zone,in_zone_deg,dq,tau,temp,merror
    MARK,t,label,out_deg,q_raw

脚本回答四个问题（对应 docs/real.md §3.7 的验收标准）：

1. **读数是里程计还是锯齿？** 把相邻采样的 Δ 按方向投影，看"单向转一段时间后，
   总位移"是否与"首末读数之差"一致：
   - 里程计（odometer，S1 实测就是）：读数单调累计、`zone` 连续变化、跨零点无跳变；
   - 锯齿（只报"相对最近零点"，讲义 §2.4）：`in_zone_deg` 一直在 0…56.87° 里循环，
     `out_deg` 每个区间都回 0 —— 这种必须在软件里自己补区间。
2. **反向转是否对称**（里程计的正负计数对不对）。
3. **有没有 ≈1 个零点区间的跳变**（讲义 §2.6 的"认错零点"）：把相邻 Δ 换算成
   "零点区间"的倍数，统计落在 1±10% 的个数，并列出它们的位置。
4. **记号笔那个点在读数上是多少**（`MARK` 行），以及手转的速度量级。

退出码：0 = 没发现整间隔跳变（或没转够），3 = 发现整间隔跳变（需要按讲义 §2.6 补偏移）。
"""
import math
import re
import sys
from pathlib import Path


GEAR_CANDIDATES = (19 / 3, 6.33, 6.3, 6.333)   # 真实的 19:3 优先（程序内部用它）；SDK 的 6.33 只作对照


def load(path: Path):
    rows, marks = [], []
    header = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = re.sub(r"\s+", "", line)
        if not line or line.startswith("#"):
            header = header or line
            continue
        f = line.split(",")
        if f[0] == "MARK" and len(f) >= 4:
            marks.append({"t": float(f[1]), "label": f[2], "out_deg": float(f[3]),
                          "q_raw": float(f[4]) if len(f) > 4 else float("nan")})
        elif len(f) >= 11:
            rows.append({
                "frame": int(f[0]), "t": float(f[1]), "q_raw": float(f[2]),
                "q_rad": float(f[3]), "out_deg": float(f[4]), "zone": int(f[5]),
                "in_zone": float(f[6]), "dq": float(f[7]), "tau": float(f[8]),
                "temp": int(f[9]), "merror": int(f[10]),
            })
    return header, rows, marks


def fmt(v, w=9, p=3):
    return f"{v:+{w}.{p}f}"


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    path = Path(sys.argv[1])
    header, rows, marks = load(path)
    if not rows:
        print(f"{path}：没解析到任何帧（格式不对？）")
        return 2

    # 零点区间 = 360/N；N 从 zone 与角度反推最稳（zone = floor(out_deg/interval)）
    n_gear, zi = GEAR_CANDIDATES[0], 360.0 / GEAR_CANDIDATES[0]
    for n in GEAR_CANDIDATES:
        cand = 360.0 / n
        if all(abs(math.floor(r["out_deg"] / cand) - r["zone"]) <= 1 for r in rows[:50]):
            n_gear, zi = n, cand
            break

    t0, t1 = rows[0]["t"], rows[-1]["t"]
    span = rows[-1]["out_deg"] - rows[0]["out_deg"]
    print(f"文件 {path.name}：{len(rows)} 帧、{t1 - t0:.3f} s（{len(rows) / max(t1 - t0, 1e-9):.1f} Hz）、"
          f"减速比 N = {n_gear:.4f}、零点区间 = {zi:.4f}°")
    zones = [r["zone"] for r in rows]
    print(f"输出端读数 {rows[0]['out_deg']:+.3f}° → {rows[-1]['out_deg']:+.3f}°（净位移 {span:+.3f}°"
          f" = {span / zi:+.3f} 个零点区间）；区号 {min(zones)}…{max(zones)}（{max(zones) - min(zones) + 1} 个）")
    print(f"温度峰值 {max(r['temp'] for r in rows)} °C、出现过的 merror 值 "
          f"{sorted({r['merror'] for r in rows})}、dq 区间 "
          f"{min(r['dq'] for r in rows):+.3f}…{max(r['dq'] for r in rows):+.3f} rad/s（转子）")

    # —— 1. 里程计 vs 锯齿 ——
    steps = []
    for a, b in zip(rows, rows[1:]):
        d = b["out_deg"] - a["out_deg"]
        steps.append((a["frame"], a["t"], d, b["zone"] - a["zone"]))
    abs_sum = sum(abs(s[2]) for s in steps)          # 走过的路（不抵消）
    net = sum(s[2] for s in steps)                   # 净位移
    fwd = sum(s[2] for s in steps if abs(s[2]) > 0.05 and s[2] > 0)
    bwd = sum(s[2] for s in steps if abs(s[2]) > 0.05 and s[2] < 0)
    reversals = sum(1 for s in steps if abs(s[2]) > 0.05)
    big = [s for s in steps if abs(s[2]) >= 2.0]
    print()
    print(f"手转量：正方向 {fwd:+.2f}°、反方向 {bwd:+.2f}°、|Δ| 总和 {abs_sum:.2f}°（净 {net:+.2f}°）、"
          f"有位移的采样 {reversals} 个")
    print(f"每帧步进：max |Δ| = {max(abs(s[2]) for s in steps):.3f}°、"
          f"≥2° 的 {len(big)} 次")
    print("读数形态判定：", end="")
    span_deg = max(r["out_deg"] for r in rows) - min(r["out_deg"] for r in rows)
    if span_deg > zi * 1.1:
        print(f"**里程计**（读数跨越了 {span_deg / zi:.2f} 个区间，是累计的）"
              " ⇒ 跨零点由驱动板自己维护，我们的软件不用补区间；"
              "但上电时落在哪个零点仍然不确定（讲义 §2.6）。")
        print("            注意：这个结论不排除“中途认错零点”（下面单独看整间隔步进）。")
    elif abs_sum > zi * 2:
        print(f"**锯齿 / 只报“相对最近零点”**（一共转了 {abs_sum / zi:.2f} 个区间的路，"
              f"读数却一直待在 {span_deg:.2f}° < 1 个区间里）= 讲义 §2.4 那种"
              " ⇒ 我们的软件必须自己数跨过了几个零点、补上 ±1 个区间。")
    else:
        print(f"还不能定：读数跨度 {span_deg:.2f}°、走过的路 {abs_sum:.2f}°（{abs_sum / zi:.2f} 个区间）。"
              "建议单向慢慢转**超过 2 个零点区间**再跑一次。")

    # —— 2. 反向对称性 ——
    seg = [(a, b) for a, b in zip(rows, rows[1:]) if abs(b["out_deg"] - a["out_deg"]) > 0.05]
    print(f"换向：有位移的采样 {len(seg)} 个、正方向 {fwd:+.2f}°、反方向 {bwd:+.2f}°；"
          "里程计可逆的话，反向段的每周步进应与正向同一量级（不出现整间隔跳变）。")

    # —— 3. 整间隔跳变（认错零点）——
    wrap_like = [s for s in steps if abs(abs(s[2] / zi) - 1.0) < 0.10]
    print()
    print(f"≈±1 个零点区间（{zi:.2f}°，容差 10%）的步进：{len(wrap_like)} 次")
    for frame, t, d, dz in wrap_like[:20]:
        print(f"    帧 {frame:6d} t={t:7.3f} s：Δ {d:+8.3f}°（{d / zi:+.3f} 个区间，转子 {d * n_gear:+.1f}°）")
    if len(wrap_like) > 20:
        print(f"    …共 {len(wrap_like)} 次")
    other_big = [s for s in big if s not in wrap_like]
    if other_big:
        print(f"其它 ≥2° 的步进 {len(other_big)} 次（前 5 个）：")
        for frame, t, d, dz in other_big[:5]:
            print(f"    帧 {frame:6d} t={t:7.3f} s：Δ {d:+8.3f}°（{d / zi:+.3f} 个区间）")
        print("    ⇒ 若不是整间隔，先排除'手转太快/采样间隔太长'（把阈值 --jump-deg 调大重跑）")

    # —— 4. 标记 ——
    print()
    if marks:
        print(f"MARK（记号笔那个点）{len(marks)} 个：")
        for i, m in enumerate(marks, 1):
            zone = math.floor(m["out_deg"] / zi)
            print(f"    #{i} t={m['t']:7.3f} s：输出端 {m['out_deg']:+.3f}°"
                  f"（第 {zone} 区、区内 {m['out_deg'] - zone * zi:+.3f}°，raw≈{m['q_raw']:.0f}）"
                  f"{'  名字：' + m['label'] if m['label'] else ''}")
        if len(marks) >= 2:
            print(f"    相邻标记之间的距离：" +
                  "、".join(f"{b['out_deg'] - a['out_deg']:+.3f}°"
                            for a, b in zip(marks, marks[1:])))
    else:
        print("没有 MARK：手转时按回车就能记一个（S4 标定要用它）")

    print()
    if wrap_like:
        print(f"结论：发现 {len(wrap_like)} 次整间隔跳变 ⇒ 像讲义 §2.6 的'认错零点'，"
              f"处理办法是把 offset 加/减一个区间（{zi:.4f}° 输出端 = {360.0:.0f}° 转子）。")
        return 3
    print("结论：这段数据里没有整间隔跳变；跨零点的处理见上面的'读数形态判定'。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
