# 第三次培训 · 第一部分（仿真）：关节电机 + 状态机

> 任务书：[`../../../ReadOnly.d/Downloaded.d/第三次培训任务.pdf.md`](../../../ReadOnly.d/Downloaded.d/第三次培训任务.pdf.md)；讲义：[`../../../ReadOnly.d/Downloaded.d/motor.pdf.md`](../../../ReadOnly.d/Downloaded.d/motor.pdf.md)（§1 控制方式与仿真模拟、§2 零点与减速比）。
> 本文只写**只对本任务成立**的东西（这份模型、这组数）；通用的 MuJoCo 知识与坑点在仓库 [`../../docs/`](../../docs/) 下，这里只放指针。

## 1 任务要求 → 实现

| 任务书要求 | 实现 | 证据 |
|---|---|---|
| 仿真里加控制程序，模拟关节电机的特性 | `cpp/src/motor.h`：把讲义 §1.2 的 MIT 公式自己算（仿真里没有转子，写成关节侧），另带限幅 / 死区 / 指令延迟 / 噪声四个开关 | 启动打印的「电机模型 / 非理想项」两行；§3 的实测表 |
| 控制程序写成状态机、含两个状态 | `cpp/src/state.h` 的 `ctrl::StateMachine`：`Damping` / `Standing`，切换只改**指令**，电机与公式不变 | `--help` 与启动打印的「状态机」行 |
| ① 阻尼模式：所有关节电机均是阻尼状态 | 阻尼模式 = 12 个关节都下 `kp=0、kd=--kd-damp、pos=0` ⇒ τ = −kd·q̇（讲义 §1.3 的"阻尼模式"） | §3.1：从原姿态起 5 s 塌成趴卧（z 0.5786 → 0.1450 m、四足触地 4） |
| ② 站立模式：阻尼模式下按某个键站起来（从任意初始位置、连续地） | 按 `S`：位置项目标 q_des 从"按下那一刻的关节角"用 smoothstep 推到站姿，控制器不变 ⇒ 连续起身；斜坡时长按姿态自动选 | §3.2 各起点实测；窗口里按 `S`/`D` 实时切换 |
| 另一个键切回阻尼 | 按 `D`：位置项目标撤掉，只剩 −kd·q̇，狗在重力下自己塌回去 | §3.3（`--script "0.05:stand,5:damp"`） |

窗口按键：`S` 站立、`D` 阻尼、`R` 回到起点、`Q`/`Esc` 退出；鼠标左键转（+Shift 水平转）、右键平移（+Shift 水平平移）、中键/滚轮缩放。

`R` = 把基座、关节角、速度都恢复成 `--start` 指定的**起点**（不是固定的趴卧），同时把状态切回上电默认的**阻尼模式**、并保留仿真时间轴；所以按 `R` 之后会看到狗从起点姿态自然塌下（阻尼模式的正常行为），紧接着按 `S` 就能再从起点起身。`--start rest` 时按 `R` 回到趴卧（起点本来就是趴卧），`--start stance` / `raw` / `side` 则分别回到站姿 / 模型原姿态 / 侧躺。

## 2 怎么实现

### 2.1 电机：MIT 公式写在关节侧

讲义 §1.2 的公式在**电机转子侧**：$\tau_{rotor} = T_{ff} + K_P(Pos_{des}-p) + K_W(W_{des}-\omega)$；
我们的执行器是 `<motor>`（`gear=1`，`data.ctrl` 直接就是**关节侧**力矩），所以照讲义 §2.3 的映射
（位置/速度 ×N、力矩 ÷N、刚度/阻尼 ÷N²）把同一条公式写在关节侧：

$$\tau = \tau_{ff} + k_p(q_{des}-q) + k_d(\dot q_{des}-\dot q)$$

**量纲（全量纲说明）** —— 两侧（转子/关节）的量纲完全一样，减速比 $N$ 只是**无量纲**的圈数比，
换算只改数值、不改量纲（讲义 §2.3 的 `×N / ÷N / ÷N²`）：

| 量 | 符号 | 量纲 | 单位（本任务） | 典型值 |
|---|---|---|---|---|
| 输出力矩 / 前馈力矩 | $\tau$, $\tau_{ff}$ | $\mathrm{M L^2 T^{-2}}$ | N·m | 站立时 \|τ\| 峰值 4.5 N·m |
| 位置刚度 | $k_p$（转子侧 $K_P$） | $\mathrm{M L^2 T^{-2}}$（每弧度） | N·m/rad | 80（实机配置） |
| 速度刚度（阻尼） | $k_d$（转子侧 $K_W$） | $\mathrm{M L^2 T^{-2} T}$（每 rad/s） | N·m·s/rad | 3（站立）/ 0.5（阻尼模式） |
| 角度 / 目标角度 | $q$, $q_{des}$（转子侧 $p$, $Pos$） | 无量纲（弧度） | rad | 站姿膝 1.10 rad |
| 角速度 / 目标角速度 | $\dot q$, $\dot q_{des}$（转子侧 $\omega$, $W$） | $\mathrm{T^{-1}}$ | rad/s | 起身段 \|q̇\| 峰值 ~10 rad/s |
| 减速比 | $N$ | 无量纲（圈数比） | – | 6.33（GO-8010-6，$N^2 \approx 40.07$） |
| 转子侧力矩 | $\tau_{rotor}$ | 同 $\tau$ | N·m | $\tau_{out}/N$，例：33.5 N·m → 5.29 N·m |

代进公式就能看出为什么只有这一种写法：$k_p(q_{des}-q)$ 是 $\mathrm{N\,m/rad}\times\mathrm{rad}=\mathrm{N\,m}$，
$k_d(\dot q_{des}-\dot q)$ 是 $\mathrm{N\,m\,s/rad}\times\mathrm{rad/s}=\mathrm{N\,m}$，两项与 $\tau_{ff}$ 同量纲、可以相加；
`data.ctrl`（我们写的）/ 实机的 `cmd.tau`（转子侧）也都是 N·m。**数值直觉**：$k_p=80$ 时 10°（0.1745 rad）偏差
产生 **14.0 N·m**；$k_d=3$ 时 1 rad/s 产生 **3 N·m**；$k_d$ 的量纲里带一个“秒”，所以换单位（deg、rpm）必须先换算。

三个容易踩的单位点：

1. MuJoCo 的 `qpos/qvel` 是 **rad / rad/s**，日志/HUD 里的 `deg` 只是给人看的；
2. 限幅是**输出端**的：本模型 `ctrlrange` 是 ±20 N·m、讲义说实机 black 配置是 33.5 N·m —— 这两个都是关节侧，
   换成转子侧要 **÷N**（20/6.33 = 3.16 N·m）；反之实机 `data.tau` 是转子侧，换成关节侧要 **×N**；
3. `--gravity-comp` 叠加的 `qfrc_bias` 也是 N·m，所以能直接加到 τ 上。

**与官方 SDK 对得上**：Unitree 官方电机 SDK（[`../../../ReadOnly.d/unitree_actuator_sdk`](../../../ReadOnly.d/unitree_actuator_sdk)，
`unitreerobotics/unitree_actuator_sdk`，commit `5b79a42`）的 `MotorCmd{tau, dq, q, kp, kd}` / `MotorData{tau, dq, q}`
就是同一套量（全部**转子侧**），README 还专门写了 $kp_{rotor}=kp_{output}/r^2$、$kd_{rotor}=kd_{output}/r^2$
（`unitree_actuator_sdk/README.md` 第 53–57 行），与讲义 §2.3 一字不差；减速比用 `queryGearRatio(MotorType)` 查（`unitreeMotor.h:73`）。

代码里两条都留了：`motor::Cmd`（关节侧，仿真真正算的）与 `motor::RotorCmd`（转子侧 SDK 字段），
`motor::ToRotor(cmd, gear)` 做换算。启动时会打印一次换算结果作为对照（默认 `N = 6.33`，$N^2 \approx 40.07$）：

| 关节侧（我们思考用的） | 转子侧（下发给电机的） | 本任务默认值下 |
|---|---|---|
| `kp = 80` N·m/rad | `K_P = kp/N²` | 1.997 N·m/rad |
| `kd = 3` N·m·s/rad | `K_W = kd/N²` | 0.07487 N·m·s/rad |
| `q_des` | `Pos = N·q_des` | 目标 0.5 rad → 3.165 |

反馈方向同理：`q = data.Pos/N + offset`（`offset` 就是第二部分的标定值，讲义 §2.5）。

**非理想项**（讲义 §1.1 的三类非线性）都做成了开关，默认全关 = 理想力矩源：

| 开关 | 模拟什么 | 默认 |
|---|---|---|
| `ctrlrange`（模型里 ±20 N·m）/ `--tau-max N` | 恒力矩区的天花板（电流限幅）；讲义说实机 black 配置是 33.5 N·m | 用模型值 |
| `--deadzone N` | 小力矩时的静摩擦死区（\|τ\| < N 就当 0） | 0 |
| `--delay-cycles N` | 指令延迟 N 个控制周期（上层算完到电机执行之间的滞后） | 0 |
| `--noise N` | 编码器/电流环噪声 [N·m]（固定种子，可复现） | 0 |

**不建"高速段力矩随转速下降"**：那是电压/反电动势限制（讲义 §1.1 的 (b)）。本模型关节转速
（起身段 |q̇| 峰值 ~10 rad/s）远低于电机基速，且它不改变"给定力矩输出多少力矩"这条结论；
真要建，就在 `Apply()` 里把 τ 上限乘一条转速曲线。

### 2.2 状态机与"自动斜坡"

两个状态只差**指令**：阻尼模式 `kp=0, kd>0, pos=0`；站立模式 `kp/kd=80/3`（讲义 §1.4 提到的实机输出侧
那一组）、`pos` 随时间从起点推到站姿。切换是幂等的（重复按同一个键不会重启斜坡），上电默认在阻尼模式
（任务书第 1 条）。

斜坡时长按**按下那一刻的姿态**自动选（`--ramp auto`，默认），依据是两条实测（§3.2）：

| 按下时的姿态 | 选用的斜坡 | 为什么 |
|---|---|---|
| 还在站姿附近（基座 z ≥ 0.9×站姿、竖直度 ≤ 30°） | 0.1 s | 它正在往下倒，腿得在倒下之前收进去；1.5 s 来不及（实测 ✗） |
| 已经趴下/躺着 | 1.5 s | 拿力顶会把自己掀翻；0.1 s 会翻过去（实测 ✗） |

`--ramp 1.5` 可以改成固定值（这时两个分支都用它）。

### 2.3 站姿（控制目标）
沿用第二次培训额外 demo（[`@20260923_mujoco/cpp_stand/`](../../@20260923_mujoco/cpp_stand/)）的**搜索**：
膝取 `{0.9, 1.1, 1.3}`、大腿按膝的 `0.1…1.0` 倍扫，每次把基座平移到"最低那只脚刚好贴地"，取
"质心水平投影离四足中心最近"的一组。本模型搜到：膝 **1.10 rad**、大腿 **0.55×膝**、基座 z **0.4973 m**、
质心离四足中心 **0.0009 m**、四足触地 4。为什么不拿模型默认位形当目标见
[`@20260923_mujoco/docs/stand.md`](../../@20260923_mujoco/docs/stand.md)（膝越界 0.85 rad + 质心在足后 0.18 m）。

### 2.4 录像（`--mode record`）：给别人看的备用视频

窗口需要人按键、还得有显示服务；演示给别人看更省事的是**固定脚本 + 录像**：无窗口、全速跑，
每次得到同一段片子（与机器快慢无关）。

```bash
pixi run @20260927_motor/cpp/build/motor_sim --mode record \
    --script "0.05:stand,5:damp" --seconds 8 \
    --out @20260927_motor/output/cpp/damp_stand_damp.mp4
```

- 渲染走**隐藏窗口 + 离屏 framebuffer**（[`../cpp/src/recorder.h`](../cpp/src/recorder.h)）→ ffmpeg 管道 `libx264`；
  做法与 [`@20260923_mujoco/cpp_task2/src/record.h`](../../@20260923_mujoco/cpp_task2/src/record.h) 相同，那边的坑都带上了：
  离屏尺寸按 `--width/--height` 改（必须在 `mjr_makeContext` **之前**）、出帧按**仿真时间的严格网格** $k/fps$
  （帧数 ≈ 时长×fps）、行序自下而上交给 `-vf vflip`、**不调 `glfwTerminate()`**、HUD 只用 ASCII。
- 视频里也画 HUD（ASCII）：左边是当前状态 + 本次脚本，右边是 t / 四足触地 / 基座高度 / 竖直度 / \|τ\| 峰值 ——
  看视频的人不用猜“这是在演什么”。
- 仍需要能连上显示服务/EGL（隐藏窗口也要 GL 上下文），与 Python 侧的 `MUJOCO_GL` 无关。
- **录像不是实时的**：1280×720 下每帧 ~27–38 ms，8 仿真秒的片子录了 ~11 s；不影响产物（时间轴按仿真时间）。

| 产物 | 产出命令 | 实测 |
|---|---|---|
| `output/cpp/damp_stand_damp.mp4` | `pixi run @20260927_motor/cpp/build/motor_sim --mode record --script "0.05:stand,5:damp" --seconds 8 --out @20260927_motor/output/cpp/damp_stand_damp.mp4` | 1280×720 @50 fps、**401 帧 / 8.020 s**、724 KiB，录制 wall 10.9 s |
| `output/cpp/stand_up_from_rest.mp4` | `pixi run @20260927_motor/cpp/build/motor_sim --mode record --start rest --script "1:stand" --seconds 6 --out @20260927_motor/output/cpp/stand_up_from_rest.mp4` | 1280×720 @50 fps、**301 帧 / 6.020 s**、668 KiB，录制 wall 11.5 s |

两段片子演的是任务书要求的那两件事：① 阻尼模式（软瘫趴在）→ 按 S 起身 → 按 D 切回阻尼（又塌回去）；
② 从趴卧 keyframe 起身（自动选 1.5 s 斜坡，起身 1.39 s）。HUD 里能直接看到 `state: DAMPING / STANDING`
与 `feet on ground`、`base z` 的变化。

## 3 实测（本机 i5-1035G1，MuJoCo 3.12.0）

默认参数：`kp=80 kd=3 kd_damp=0.5 ramp=auto`、起点 = 模型原姿态、无窗口（`--mode sim`，全速跑）。
2500 步 / 5 仿真秒 wall 107.6 ms（**单步 0.0431 ms、46.5x 实时**）；窗口模式按墙钟节流。

### 3.1 阻尼模式：kd 决定"软瘫"落在什么姿势（从原姿态起 5 s）

| `--kd-damp` | 末态基座 z | 竖直度 | 四足触地 | 水平位移 | 结论 |
|---|---|---|---|---|---|
| 0 | 0.1449 m | 0.00° | 4 | 0.0707 m | 趴平（与 `rest` keyframe 同高） |
| 0.3 | 0.1450 m | 0.00° | 4 | 0.0340 m | 趴平 |
| **0.5（默认）** | 0.1450 m | 0.00° | 4 | 0.0551 m | 趴平 ✓ |
| 1 | 0.2296 m | 3.81° | 0 | 0.3684 m | 撑在腿上（没趴下去） |
| 3 | 0.2043 m | 26.21° | 0 | 0.4523 m | 侧翻 |

读法：kd 越大，关节越"黏"、越撑得住，狗就不再是软瘫下去、而是架在腿上甚至侧翻。这也解释了为什么
右侧两行在这种姿势下再按站立键会失败（没有足底接触，纯 PD 顶不回来）。默认取 0.5。

### 3.2 站立模式：从任意初始位置连续起身（自动斜坡）

| 起点（`--start`） | 按键时刻 | 选出的斜坡 | 末态 z（站姿 0.4973） | 竖直度 | 四足触地 | 起身用时 | 判定 |
|---|---|---|---|---|---|---|---|
| `raw`（原姿态，直腿） | 0.05 s（还在往下倒） | 0.10 s | 0.4864 m | 0.25° | 4 | 0.07 s | ✓ |
| `raw` | 3.0 s（已经趴平） | 1.50 s | 0.4862 m | 0.25° | 4 | 1.40 s | ✓ |
| `rest`（趴卧 keyframe） | 1.0 s | 1.50 s | 0.4864 m | 0.24° | 4 | 1.41 s | ✓ |
| `stance`（已在站姿上） | 0.05 s | 0.10 s | 0.4864 m | 0.24° | 4 | 0.00 s | ✓ |
| `side`（侧躺，绕 x 转 90°） | 1.0 s | 1.50 s | 0.1709 m | 89.53° | 0 | — | ✗ |

对照组（固定斜坡，说明"按姿态选"不是多余的）：

| 组合 | 结果 |
|---|---|
| `--ramp 1.5` + 0.05 s 按键（还在原姿态上倒） | ✗ 倒（斜坡太长，来不及收腿） |
| `--ramp 0.1` + 3 s 按键（已经趴平） | ✗ 翻过去（猛拉） |
| `--ramp 0.3` + 0.3 s 按键 | ✗ 2 足触地、竖直度 41° |

**已知边界**：趴卧、原姿态、半站、站姿上都能起来；**侧躺 90° 起不来**——纯 PD 到站姿没有"翻身"这一步
（起身段把力矩打满 52 次也没翻过来）。要做这个得加一段翻身轨迹，第一部分不做，实测数字留在这里。

### 3.3 切回阻尼 + 非理想项

`--script "0.05:stand,5:damp"`：站立段 ✓（z 0.4864、四足触地 4），5 s 切阻尼后 ✓ 塌回趴卧（z 0.1450、末段 max\|q̇\| 0.000）。

| 配置 | 站立段 | 切回阻尼后 | 电机统计 |
|---|---|---|---|
| 理想（默认） | ✓ z=0.4864、max\|q̇\| 0.001 | ✓ z=0.1450 | 撞限幅 **0** 次 / 48000 电机·步，\|τ\| 峰值 4.47、均值 ~2.5 N·m |
| `--deadzone 0.5 --delay-cycles 2 --noise 0.2` | ✓ z=0.4864、max\|q̇\| 0.049 | ✓ z=0.1450（末段 max\|τ\| 0.52，死区在起作用） | 撞限幅 0 次，\|τ\| 峰值 4.66 |
| `--tau-max 33.5`（讲义说的实机限幅） | ✓ 同上 | ✓ | 与默认（±20）逐渐位相同 |

结论：这组任务（软瘫 / 起身 / 站住）**用不到限幅**——|τ| 峰值 4.5 N·m 离 ±20 还远；限幅只在侧躺那种
"顶不回来"的场景里出现（52 次打满）。死区 0.5 N·m 会削掉阻尼模式下的小力矩（末段 max|τ| 0.52），
但不足以改变结果。

## 4 踩坑

1. **阻尼模式的 kd 决定它最后趴成什么样**（§3.1）。一开始默认取 3（= 站立模式的 kd，图省事），结果狗
   在阻尼模式下侧翻，接着"按 S 站起来"必然失败。修法是按"软瘫"的物理去选：小 kd（0.5）才像真狗那样
   收腿趴平。
2. **斜坡时长不能写死**（§3.2 的对照表）。同一段"推到站姿"的代码，在"还在原姿态上往下倒"时要用 0.1 s，
   在"已经趴平"时要用 1.5 s——反了都会摔。所以做成"按下那一刻按姿态自动选"。
3. **"起身完成"不能只看基座高度**。原姿态的基座（0.5786）比站姿（0.4973）**还高**，只看高度会立刻
   判"0.00 s 就起来了"。改成"四足触地 + 高度到位 + 竖直度 ≤ 10°"才靠谱。
4. **搜索出来的站姿是"刚好相切"**：几何上按"最低脚的球面刚好切地面"算，切点相切时 MuJoCo 可能不生成
   接触点（实测刚搜完的站姿打印"四足触地 0"）。修法：按 1 mm 步长往下压，直到数出 4 个足底接触
   （现在基座 z=0.4973 = 相切高度 − 1 mm）。这件事在第二次培训的斜面 demo 里也踩过（那里是按步长往下压
   直到四足进接触）。
5. **窗口为什么自己写**：任务要用键盘切模式，而官方 `Simulate` 界面（`mj::GlfwAdapter`）的按键属于它自己
   的 UI，挂不上自定义回调。所以这次用 GLFW 自己开窗口：渲染仍是 `mjv_updateScene` + `mjr_render`，
   相机用 `mjv_moveCamera`（调用惯例照官方 `sample/basic.cc`：像素位移除以窗口高度、y 取负，滚轮 5% 高度）。
6. **不要调 `glfwTerminate()`**：本机驱动上收尾会崩（与 [`@20260923_mujoco/cpp_task2/src/record.h`](../../@20260923_mujoco/cpp_task2/src/record.h)
   同一条结论），只销毁窗口，进程退出时由系统回收。
7. **日志要设成行缓冲**：窗口模式是长时间运行的交互程序，stdout 被重定向时是块缓冲，中途被 `Ctrl-C`/信号
   打断会丢掉全部日志（第一次冒烟测试就什么都没看到）。`main()` 开头 `setvbuf(stdout, nullptr, _IOLBF, 0)`。
8. **Wayland 下"窗口尺寸" ≠ "framebuffer 尺寸"**：本机缩放是 2×，`glfwCreateWindow(1280, 720)` 拿到的
   **window size 是 1280×720、framebuffer 是 2560×1440**（启动日志实测：`窗口：window 1280x720、framebuffer 1280x720（缩放 1.00x）` → `window 1280x720、framebuffer 2560x1440（缩放 2.00x）`，compositor 在首帧之后才把缩放报上来）。渲染视口只在构造时取一次（`mjr_maxViewport`）的话，画面就永远画在左下角那一小块 —— 就是"不跟着窗口变、固定在左下角"。
   修法：**每帧**用 `glfwGetFramebufferSize` 重取视口，并处理最小化时的 0×0（直接不画）；尺寸/缩放变化时打一行日志，便于在任何桌面上核对。
   为什么这样就跟桌面/缩放无关了：`mjr_render(viewport, …)` 的坐标就是**当前 framebuffer 的像素**，所以唯一正确的视口就是它的像素尺寸；不同桌面/缩放只是让这个尺寸不同而已。实测（独立探针，程序化改窗口尺寸，Wayland 2×）：`window 800x400 ↔ framebuffer 1600x800`、`1600x900 ↔ 3200x1800`、`1280x720 ↔ 2560x1440`，即 framebuffer 永远 = window × 2，改窗口后**同一帧内就跟着变**——而我们是每帧重取，所以拖拽/最大化/跨屏移动都能跟上。X11 1× 时两者相等（修复前也能跑，无回归）；X11 HiDPI、Wayland 整数/分数缩放（GLFW 3.5.1，≥ 3.4 才支持分数缩放）同理。
9. **鼠标方向与灵敏度都“两次取负/两个比例”的坑**。官方链路是：
   `platform_ui_adapter.cc:236-241` 先把光标 y 翻成 y-up 再算 `dy`，`simulate.cc:2096` 传给
   `mjv_moveCamera` 时又写 `-state->dy` —— 两次取负抵消，效果等于"GLFW 的 y-down 位移直接传正值"（与最简示例
   `sample/basic.cc:92` 一致）。只看了 `simulate.cc` 那一处、照着写 `-dy`，方向就反了。
   同一个地方还有第二个比例：`platform_ui_adapter.cc:233-234` 先把光标位移乘 `buffer/window` 比例换成
   framebuffer 像素，然后才除以 `rect[3].height`（framebuffer 高度）——两个比例相消，等价于
   **直接除以窗口（逻辑）高度**。上一版除以的是 framebuffer 高度，于是 2× 缩放下相机转速只有官方的一半。
   现在按"不取负 + 除以窗口高度"写，转动灵敏度与缩放比例无关，和官方一致；另带 Shift = 水平面、
   中键/滚轮 = 缩放（同官方）。
10. **窗口里 HUD 的文字只能用 ASCII**。`mjr_overlay` 用的是 MuJoCo 内置的**位图字体，只覆盖 ASCII**：
   非 ASCII 字节会被当成未知字形、画成一个**实心块**，所以中文（3 字节）看上去就是三个粗方块 —— 就是
   "加粗乱码"的来源。离屏探针实测（`mjr_overlay` 后数“墨迹”像素，每字节平均）：

   | 文本 | ink/byte |
   |---|---|
   | `state: STANDING  feet on ground: 4  base z = 0.4862 m` | 41.7 |
   | `S = stand   D = damp   R = reset   Q/Esc = quit` | 33.1 |
   | `S = 站立模式   D = 阻尼模式   R = 回到起点   Q/Esc = 退出` | 72.9 |
   | `四足触地 4` | **121.9** |
   | `基座 z = 0.1450 m` | 52.9 |
   | `\|τ\| 峰值 6.6 N·m` | 94.7 |
   | `竖直度 0.25°` | 118.1 |

   这也解释了用户一眼看到的那几处：“S = / D = / R = / Q-Esc = 后面”“4 前面”“z = … 前面”“\|τ\| 里面”
   “N 与 m 之间（`·`）”“0.25 后面（`°`）”全是非 ASCII。现在 HUD 全部改成 ASCII（`state: STANDING`、
   `feet on ground`、`base z`、`tilt ... deg`、`\|tau\| peak ... N*m`），**终端日志照旧用中文**（终端字体没问题）；
   另外在 `viewer::Window::Draw()` 里加了一道检查：HUD 里一旦出现非 ASCII 字节就在终端报一次警告。
   窗口标题是桌面（compositor）画的，不受这个字体限制，可以继续用中文。
11. **`R`（复位）不能只调 `mj_resetData`**。`mj_resetData` 会把 `d->time` 一起清零，而站立模式的
   斜坡与 `--script` 都是按**仿真时间**排的：复位后时间轴跳回 0，已经算好的斜坡目标（或脚本剩余时刻）
   就永远等不到，现象是"按 R 后狗塌下去再也起不来"（早期版本还顺手固定切回阻尼模式，看起来就像
   "R 永远 reset 到趴卧"）。修法：复位时记下 `t_keep = d->time`，`mj_resetData` + 重设起点姿态 +
   `mj_forward` 之后再写回 `d->time = t_keep`；同时让 `R` 复用状态机的 `Request(Damping)`，保证"复位 =
   回到 `--start` 起点 + 回阻尼模式"。复现：

   ```bash
   pixi run @20260927_motor/cpp/build/motor_sim --mode sim --seconds 8 --start raw \
       --script "0.05:stand,3:reset,4:stand"     # 站住 → t=3 复位（日志里 z 0.4865 → 0.5786，t 保留）→ 再站住 ✓
   ```

   四个起点都验过：`raw` 回模型原姿态（z 0.5786）、`rest` 回趴卧（z 0.1449）、`stance` 回站姿
   （z 0.4973）、`side` 回侧躺（竖直度 90°）。

## 5 复现命令

```bash
cd ..                                                     # 仓库根目录（有 pixi.toml）
pixi run cmake -S @20260927_motor/cpp -B @20260927_motor/cpp/build -G Ninja -DCMAKE_PREFIX_PATH="$CONDA_PREFIX"
pixi run cmake --build @20260927_motor/cpp/build

# 窗口（交付形态）：按 S 站立、D 阻尼、R 回到起点、Q/Esc 退出
pixi run @20260927_motor/cpp/build/motor_sim

# 无窗口回归（退出码：0 = 判定通过、2 = 不通过、1 = 参数错误）
pixi run @20260927_motor/cpp/build/motor_sim --mode sim --seconds 5                        # ①阻尼模式：松手塌回趴卧
pixi run @20260927_motor/cpp/build/motor_sim --mode sim --seconds 6 --script "0.05:stand"  # ②按 S 起身
pixi run @20260927_motor/cpp/build/motor_sim --mode sim --seconds 8 --script "3:stand"     # ②已经趴平时再按 S
pixi run @20260927_motor/cpp/build/motor_sim --mode sim --seconds 10 --script "0.05:stand,5:damp"  # ③切回阻尼
pixi run @20260927_motor/cpp/build/motor_sim --mode sim --seconds 8 --start rest --script "1:stand"
pixi run @20260927_motor/cpp/build/motor_sim --mode sim --seconds 8 --start side --script "1:stand"  # 已知边界：起不来（退出码 2）
pixi run @20260927_motor/cpp/build/motor_sim --mode sim --seconds 10 --deadzone 0.5 --delay-cycles 2 --noise 0.2 --script "0.05:stand,5:damp"
pixi run @20260927_motor/cpp/build/motor_sim --mode sim --seconds 5 --kd-damp 3            # 对比：kd 太大 → 侧翻

# 录像（别人看不了实时时的备用视频，§2.4）
pixi run @20260927_motor/cpp/build/motor_sim --mode record --script "0.05:stand,5:damp" --seconds 8 --out @20260927_motor/output/cpp/damp_stand_damp.mp4
pixi run @20260927_motor/cpp/build/motor_sim --mode record --start rest --script "1:stand" --seconds 6 --out @20260927_motor/output/cpp/stand_up_from_rest.mp4
```
