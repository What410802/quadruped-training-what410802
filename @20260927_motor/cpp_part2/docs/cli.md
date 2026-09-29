# `motor_ctl` 用法（离线自检与实机）

> 程序：[`../apps/motor_ctl.cpp`](../apps/motor_ctl.cpp)（构建见 [`setup.md`](setup.md) §3）。
> 本文是**参数与命令的完整清单**；现场怎么一步步做见 [`runbook.md`](runbook.md) §4 批次 4–6，
> 上机手册的"每步看什么"见 [`real.md`](real.md) §3.8。
> 设计依据（零点语义、离线重锚、验收时序）在 [`zero_semantics.md`](zero_semantics.md)。

## 1 离线自检（不接电机）

```bash
cd ..                       # 仓库根目录
B=@20260927_motor/cpp_part2/build/motor_ctl
export LD_PRELOAD=$PWD/@20260927_motor/cpp_part2/build/libpty_serial_shim.so

$B --help                                        # 全部参数与键盘命令
$B --no-send                                     # 只看配置（不发字节）

$B --self-test --script "0;30;mark;o+30;expect;30"     # 回归 0 → 30° → 记零点 → 正向偏移 30° → 再回 30°
$B --self-test --fake-datum-turns 1 --expect-deg 0 --seconds 3     # 假板子“上电认错零点”，看启动检查与自动修正
$B --self-test --fake-jump-frame 40 --fake-jump-turns 1 --script "60" --seconds 4   # 运行中注入一次跳变
$B --self-test --fake-sawtooth --script "100" --seconds 4         # 板子只报相对最近零点的角度（锯齿）
$B --self-test --fake-hand-deg 120 --fake-hand-period-s 6 --script "free;state" --seconds 8   # “手推输出端”来回 ±120°（跨 2 个零点区间）
$B --self-test --fake-off-after 200 --fake-off-frames 200 --fake-hand-deg 80 --script "free;state" --seconds 6   # 断电 + 期间手推 + 重上电
$B --self-test --fake-cycle-frame 250 --script "60" --seconds 4 --every 50                        # 单次上电复位（读数跳一个区间）
```

注入开关的语义（含"断电窗口按收到的命令帧计时""窗口结束那一帧按真上电处理"）见
[`fake_motor.md`](fake_motor.md) §3.4。

## 2 实机

```bash
sudo $B --port /dev/ttyUSB0 --id 0                       # 交互：h 看命令，先别急着给目标
sudo $B --port /dev/ttyUSB0 --id 0 --script "0"          # 回归 0 位（多圈行程会先打印预计时间）
sudo $B --port /dev/ttyUSB0 --id 0 --script "0;mark;30;o+30;expect;30"   # S3→S4：回 0 → 记零点 → 去 30° → 偏移 30° → 复查 → 再回 30°（会落回记号笔那一点）
sudo $B --port /dev/ttyUSB0 --id 0 --expect-deg 0        # 上电检查（记号笔那个点的记录值）：差 ≈1 个区间会自动修
```

要 `sudo`（或把自己加进 `dialout`）；每次都建议用行缓冲的日志包装（`sudo stdbuf -oL … | tee`，
理由见仓库 [`../../../docs/pitfalls/environment.md`](../../../docs/pitfalls/environment.md)），
现成脚本是 [`../../scripts/run_log.sh`](../../scripts/run_log.sh)。

## 3 参数

| 参数 | 默认 | 作用 |
|---|---|---|
| `--port` / `--id` / `--baud` | `/dev/ttyUSB0` / `0` / `4000000` | 串口、电机 ID、波特率 |
| `--kp-out` / `--kd-out` | 80 / 3 | **输出端**增益；下发时 `kp ÷N²`、`kd ÷N²`（转子侧） |
| `--tau-out-limit` / `--stall-s` | 1.5 N·m / 1.0 s | 力矩上限与"持续多久算卡住" |
| `--vmax-deg` / `--amax-deg` / `--tol-deg` | 90 °/s / 180 °/s² / 1.0° | 插值上限与到位判据 |
| `--offset-deg` | 0 | 软件零点偏移初值（标定结果可存档到这里） |
| `--set-zero-read` | 关 | 启动时把当前位置定义成 0（= 先执行一次 `reset here`） |
| `--expect-deg D` | 无 | 启动检查：`q` 应 ≈ D 度（上次 `mark` 的 `q`） |
| `--expect-tol-deg` / `--jump-tol-deg` | 3.0° / 8.0° | "算在容差内"与"残差算 ≈0（是跳变而不是别的事）"的判据 |
| `--max-fixes N` | 3 | 一次会话最多自动修几次零点（超过就只报警） |
| `--no-fix-startup` | 关 | 启动检查只报警、不自动修 |
| `--settle S` | 0.5 s | 到位后稳住多久才算完成 |
| `--offline-frames N` | 40 | 连续 N 帧无回复算离线（切零力矩，回来先重锚） |
| `--recover-hold` | 关 | 离线恢复后**就地重新起目标**（默认维持原目标不动） |
| `--every N` | 20 | 每 N 帧打印一行 |
| `--script "a;b;c"` / `--script-step S` | 无 / 2 s | 非交互执行命令、每条之间的间隔 |
| `--seconds S` | 0（一直跑） | 跑 S 秒后收尾退出 |
| `--no-send` | 关 | 只打印配置，不打开串口 |
| `--self-test` | 关 | PTY + 假电机（要 `LD_PRELOAD` 垫片） |
| `--fake-datum-turns N` | 0 | 假板子上电落在别的候选零点（N 个转子圈，可负） |
| `--fake-sawtooth` | 关 | 假板子只报相对最近零点的角度（0…1 个区间） |
| `--fake-jump-frame N` / `--fake-jump-turns K` | 无 / 1 | 第 N 帧注入一次"读数跳 K 个区间" |
| `--fake-off-after N` / `--fake-off-frames M` | 无 / 0 | 第 N 帧起板子断电 M 帧（不收命令、不积分、不回帧） |
| `--fake-cycle-frame N` | 无 | 第 N 帧模拟一次"上电复位"（丢圈数） |
| `--fake-hand-deg D` / `--fake-hand-period-s T` | 0 / 8 s | "手推输出端"来回 ±D 度、周期 T 秒 |
| `--fake-status-bits N` | 0 | 回帧 mode 的状态位写死（bit1 期望速度超范围、bit2 期望位置超范围） |

## 4 键盘命令

`--script` 只是"非交互地敲键盘"；真机上手时**不带 `--script`** 直接在终端敲命令更顺手（`h` 看帮助）。

| 命令 | 作用 |
|---|---|
| `0` / `<角度>` | 回软件零点 / 去相对软件零点的那个角度（度），例如 `30` / `-45` |
| `+<角度>` / `-<角度>` | 相对当前位置再挪这么多度（找记号笔位置用） |
| `state`（=`p`） | 看账本：`pos` tick / `turn_base` / `offset` / 在线状态 / 事件 |
| `reset [here\|raw]` | 把此刻定义为软件零点（不带参数时会问一句是否先回编码器真值零点） |
| `raw` | 去编码器真值零点（上电首帧 `pos = 0` 的那个候选零点） |
| `offset <度>` / `o+30` / `o-30` | 直接设 `offset` / 在现有偏移上加减 30°（S4 的"零点正向偏移 30°"；改的时候电机不会动） |
| `mark` / `goto-mark` | 记下 / 回到记号笔那个点（`mark` 会打出 `q` 与 `q_enc`，**抄下 `q_enc` 供以后上电检查**） |
| `expect` / `fix` | 与记录值对照（差 ≈ 整数个区间就是上电落在别的候选零点）/ 按建议修正 |
| `hold` / `stop`（=`free`） | 位置保持 / 立刻零力矩卸力（**手转只能在零力矩下发**：带位置环时手只能把它推开几度） |
| `h` / `q` | 帮助 / 先卸力再退出 |

## 5 几件必须知道的事

* **位置在内部是 tick**（转子侧 int64）：`q_ticks = pos_ticks + offset_ticks`、`cmd.q_ticks = q_des_ticks − offset_ticks`
  —— 就是纯加减；度只在命令输入与打印处出现（[`fixed_point.md`](fixed_point.md) §5）；
* `cmd.dq / cmd.kd` 仍是**转子侧**：程序里已经换算好（速度按 tick→rad、增益 ÷N²），别再换一遍；
* `offset` 的方向是**收到加、下发减**；`o+30` 之后，**同一个物理点（记号笔那个点）读数 +30°**，而"同一个目标角度"会落在记号笔那一点上（= 朝反方向少转 30°）。符号的唯一标准见 [`real.md`](real.md) §5.3；
* 回归 0 可能是**多圈**行程（读数从上次上电起一直累计），程序会先打印"要转多少度、直线时间多少秒"；
* 跳变判据用**整数 raw 差 ≈ k×32768**（k 个转子圈 = k×56.842° 输出端）：检测到就只把 `offset` 反向补 k 个区间 —— 这样同一个 `q_des` 仍对应同一个物理位置；**顺手挪 q_des 是错的**（会把物理目标整段挪一个区间，dry run 里实测过）；
* 上电时"认错零点"用 `--expect-deg <记号笔那点的 q>` 或 `expect` 发现（差 ≈1 个区间），`--no-fix-startup` 可以只报警不动手；
* **离线时（连续 40 帧无回复）程序自动切零力矩**，回来那一帧先重锚圈数再恢复出力——所以断链/断电再上电都不会有"追一个差一整圈的目标"的力矩冲击（离线自检里量过：52.5 N·m → 0.3 N·m）；
* 0 位最好**离候选零点边界 ≥10°**（`mark` 会提示），因为板子以"最近经过的零点"为基准，边界附近最容易认错（`--set-zero-read` 可以帮你把 0 位放到别处）。
