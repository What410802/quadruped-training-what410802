#!/usr/bin/env python3
"""分析 `spin_test` 的实机输出（终端会把长行折过，先压平再解析）。

用法（仓库根目录，可一次给多个日志）：
    pixi run python @20260927_motor/scripts/agent_scripts/analyse_spin_log.py <log.txt> [<log2.txt> ...]

**原则：只读程序自己算好的那几行**，不要拿"名义 5 ms/帧"去算转速——实测帧周期是 5.6~6.4 ms，
用名义步长会把转速高估 10% 以上（2026-09-29 发现并改正）。要读的行：

    cmd.kd   = 0.012479      （输出端 0.5 N·m·s/rad ÷ N² → 转子侧）       ← 增益（反推摩擦要用）
    帧数 1601（收到回复 1601、超时 0）；实测输出端转速区间 …（指令 …）；
    位置 135 → 58602 tick（转子侧；输出端 0.23° → 101.66°）；温度峰值 27 °C；最后一次 merror=0
    真实帧周期 6.388 ms（名义 5.000，即实际命令频率 156.5 Hz）
    匀速段（用**墙钟**与位置反馈算）：3.60 s 转了 1.373 圈转子 = 0.217 圈输出端 ⇒ **0.0603 圈/s**（指令 0.1000，达成 60%）

顺带按"稳态误差 = τ_fric_out / kd_out"反推库仑摩擦（输出端与转子侧两个口径都给出），
用于 S2d（把低速那个误差分成"摩擦"还是"标度"）。
"""
import pathlib
import re
import sys

# 汇总行（tick 版，2026-09-29 起）：位置 135 → 58602 tick（转子侧；输出端 0.23° → 101.66°）；温度峰值 27 °C；最后一次 merror=0
POS = re.compile(r'位置\s*([-\d]+) → ([-\d]+) tick（转子侧；输出端 ([-+\d.]+)° → ([-+\d.]+)°）；'
                 r'温度峰值 (\d+) °C；最后一次 merror=(\d+)')
# 汇总行（float 版，09-29 之前）：转子侧位置 3.6100 → 15.6257 rad（输出端 32.68° → 141.44°）；温度峰值 30 °C
POS_OLD = re.compile(r'转子侧位置 [-\d.]+ → [-\d.]+ rad（输出端 ([-+\d.]+)° → ([-+\d.]+)°）；温度峰值 (\d+) °C')
SUMM = re.compile(r'帧数 (\d+)（收到回复 (\d+)、超时 (\d+)）')
RANGE = re.compile(r'实测输出端转速区间 ([-+\d.]+)…([-+\d.]+) 圈/s（指令 ([-+\d.]+)）')
PERIOD = re.compile(r'真实帧周期 ([\d.]+) ms')
STEADY = re.compile(r'匀速段（用\*\*墙钟\*\*与位置反馈算）：([\d.]+) s 转了 ([\d.]+) 圈转子 = ([\d.]+) 圈输出端'
                    r' ⇒ \*\*([-+\d.]+) 圈/s\*\*（指令 ([-+\d.]+)，达成 ([\d.]+)%）')
KD_OUT = re.compile(r'输出端 ([\d.]+) N·m·s/rad')
GEAR_N = 19 / 3


def report(path: pathlib.Path) -> None:
    flat = re.sub(r'\s+', ' ', path.read_text(encoding='utf-8', errors='replace'))
    runs = flat.split('=== 这次会下发什么')[1:]
    print(f'=== {path.name}：{len(runs)} 次运行 ===')
    if not runs:
        print('  （没找到 "=== 这次会下发什么" 这一行：这可能不是 spin_test 的日志）')
        return
    print('%-3s %-10s %-11s %-6s %-20s %-16s %-9s %-6s %s'
          % ('#', '指令 圈/s', '匀速段实测', '达成', 'dq 反馈区间', '位置 tick', '结束角', '温度', '帧周期'))
    for i, r in enumerate(runs, 1):
        cmd = RANGE.search(r)
        steady = STEADY.search(r)
        summ = SUMM.search(r)
        period = PERIOD.search(r)
        pos = POS.search(r)
        if pos:
            ticks, deg2, temp, merr = f'{pos.group(1)}→{pos.group(2)}', pos.group(4), pos.group(5), pos.group(6)
        else:
            old = POS_OLD.search(r)
            ticks, deg2, temp, merr = ('?', old.group(2), old.group(3), '?') if old else ('?', '?', '?', '?')
        if not (steady and cmd):
            # 09-27 那批用的是更早的版本：那时还没打印"真实帧周期/匀速段"（也就没有可用的实测步长），
            # 所以这里不猜、直接说清楚去哪儿看结论。
            print('%-3d （这份日志没有"匀速段"行：2026-09-27 那批的版本还没打印它，'
                  '转速结论见 docs/real.md §3.6 的表）' % i)
            continue
        print('%-3d %-10s %-11.4f %-6s %-20s %-16s %-9s %-6s %s'
              % (i, cmd.group(3), float(steady.group(4)), steady.group(6) + '%',
                 f'{cmd.group(1)}…{cmd.group(2)}', ticks, deg2 + '°', temp + '°C',
                 (period.group(1) + ' ms') if period else '?'))
        if summ:
            print('     帧 %s（回复 %s、超时 %s）；merror=%s' % (summ.group(1), summ.group(2), summ.group(3), merr))

    print('\n按"稳态误差 = τ_fric_out / kd_out"反推库仑摩擦（用程序自己的匀速段值；kd_out 从日志头读取）')
    for i, r in enumerate(runs, 1):
        cmd, steady, kd = RANGE.search(r), STEADY.search(r), KD_OUT.search(r)
        if not (cmd and steady and kd):
            continue
        v = abs(float(steady.group(4)))
        err_rad_out = (float(cmd.group(3)) - v) * 2 * 3.14159265
        tau_out = float(kd.group(1)) * err_rad_out
        print('  第 %d 次：指令 %.4f、实测 %.4f 圈/s ⇒ 误差 %+.4f 圈/s（%+.3f rad/s）'
              ' ⇒ τ_fric ≈ %+.4f N·m（输出端）= %+.4f N·m（转子侧）'
              % (i, float(cmd.group(3)), v, float(cmd.group(3)) - v, err_rad_out, tau_out, tau_out / GEAR_N))
    print('  （判据：误差 ∝ 1/kd ⇒ 库仑摩擦；与 kd 无关 ⇒ 标度/系统性偏差，见 docs/real.md §3.6 末尾）')


def main() -> int:
    logs = [pathlib.Path(a) for a in sys.argv[1:]]
    if not logs:
        print(__doc__)
        return 2
    for path in logs:
        if not path.exists():
            print(f'{path}：文件不存在')
            continue
        report(path)
        print()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
