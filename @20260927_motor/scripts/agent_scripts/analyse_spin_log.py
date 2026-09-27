#!/usr/bin/env python3
"""分析 spin_test 的实机输出（终端把长行折过，先压平再解析）。

用法：pixi run python @20260927_motor/scripts/agent_scripts/analyse_spin_log.py <log.txt>
"""
import re
import sys
import pathlib

LOG = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else
                   '@20260927_motor/output/terminal/motor-real-2026092719.txt')
flat = re.sub(r'\s+', ' ', LOG.read_text(encoding='utf-8', errors='replace'))
runs = flat.split('=== 这次会下发什么')[1:]

FRAME = re.compile(r'帧 (\d+)：转子 实测 ([-+\d.]+) rad/s[^；]*；输出端 [-\d.]+ 圈/s、累计转角 ([-+\d.]+)°')
PHASE = re.compile(r'\[t= ?([\d.]+) s\] 阶段 → ([^：]+)：')
SUMM = re.compile(r'帧数 (\d+)（收到回复 (\d+)、超时 (\d+)）')
RANGE = re.compile(r'实测输出端转速区间 ([-+\d.]+)…([-+\d.]+) 圈/s（指令 ([-+\d.]+)）')
POS = re.compile(r'转子侧位置 [-\d.]+ → [-\d.]+ rad（输出端 ([-+\d.]+)° → ([-+\d.]+)°）；温度峰值 (\d+) °C')

print('%d 次运行（终端折行已压平）\n' % len(runs))
hdr = ('#', '指令 圈/s', '匀速段实测', '达成', 'dq 反馈均值', 'dq 反馈区间', '结束角', '温度')
print('%-3s %-10s %-11s %-6s %-11s %-16s %-9s %s' % hdr)
for i, r in enumerate(runs, 1):
    cmdrev = RANGE.search(r)
    frames = [(int(m.group(1)), float(m.group(2)), float(m.group(3))) for m in FRAME.finditer(r)]
    phases = [(float(m.group(1)), m.group(2).strip()) for m in PHASE.finditer(r)]
    summ = SUMM.search(r)
    pos = POS.search(r)
    hold = [p[0] for p in phases if '保持' in p[1]]
    down = [p[0] for p in phases if '降速' in p[1]]
    t1, t2 = (hold[0] if hold else 2.0), (down[0] if down else 5.0)
    seg = [f for f in frames if t1 <= f[0] * 0.005 <= t2]
    if len(seg) > 1 and cmdrev:
        v = (seg[-1][2] - seg[0][2]) / 360.0 / ((seg[-1][0] - seg[0][0]) * 0.005)
        dq = [f[1] for f in seg]
        print('%-3d %-10s %-11.4f %-6s %-11.3f %-16s %-9s %s' % (
            i, cmdrev.group(3), v, '%.0f%%' % (100 * abs(v) / float(cmdrev.group(3))),
            sum(dq) / len(dq), '%.2f…%.2f' % (min(dq), max(dq)),
            pos.group(2) + '°' if pos else '?', pos.group(3) + '°C' if pos else '?'))
        if summ:
            print('     帧 %s（回复 %s、超时 %s）' % (summ.group(1), summ.group(2), summ.group(3)))
    else:
        print('%-3d （帧行没解析出来：%d 条）' % (i, len(frames)))

# 速度环稳态误差 → 反推库仑摩擦：误差[输出端 rev/s] = τ_fric_out / (kd_out·2π)？推导：
#   τ = kd_out·(ω_des − ω)（输出端），稳态时 τ 正好抵消摩擦 τ_fric_out ⇒ 误差 = τ_fric_out / kd_out
print('\n反推摩擦：稳态误差 = τ_fric_out / kd_out（kd_out = 0.5 N·m·s/rad，输出端）')
for i, r in enumerate(runs, 1):
    cmdrev = RANGE.search(r)
    frames = [(int(m.group(1)), float(m.group(2)), float(m.group(3))) for m in FRAME.finditer(r)]
    phases = [(float(m.group(1)), m.group(2).strip()) for m in PHASE.finditer(r)]
    hold = [p[0] for p in phases if '保持' in p[1]]
    down = [p[0] for p in phases if '降速' in p[1]]
    seg = [f for f in frames if (hold[0] if hold else 2.0) <= f[0] * 0.005 <= (down[0] if down else 5.0)]
    if len(seg) > 1 and cmdrev:
        v = (seg[-1][2] - seg[0][2]) / 360.0 / ((seg[-1][0] - seg[0][0]) * 0.005)
        err_rad_out = (float(cmdrev.group(3)) - abs(v)) * 2 * 3.14159265
        tau_fric_out = 0.5 * err_rad_out
        print('  第 %d 次：误差 %+.4f 圈/s = %+.3f rad/s（输出端）⇒ τ_fric ≈ %.4f N·m（输出端）'
              '= %.4f N·m（转子侧，÷N）' % (i, float(cmdrev.group(3)) - abs(v), err_rad_out,
                                             tau_fric_out, tau_fric_out / 6.33))
