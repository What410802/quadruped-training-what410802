# 第三次培训：关节电机（第一部分：仿真）

> 任务书 [`docs/teaching-materials/第三次培训任务.pdf.md`](docs/teaching-materials/第三次培训任务.pdf.md) 分两部分：**① 仿真**加控制程序（状态机、两个状态）、**② 实体电机控制**（SDK 转起来 → 回归零点 → 偏移零点 → 处理零点跳变）。讲义 [`docs/teaching-materials/motor.pdf.md`](docs/teaching-materials/motor.pdf.md) 讲 MIT 混合控制与零点/减速比（随 git 同步；原来放在 `ReadOnly.d/Downloaded.d/`）。
> 本目录现在只做**第一部分**，用 C++。

## 做了什么

`cpp/`（C++ 工程，可执行文件 `motor_sim`）：把关节电机当 **MIT 混合控制器**自己算（讲义 §1.2），控制程序写成**两状态的状态机**——

1. **阻尼模式**（上电默认）：12 个关节都是阻尼状态，$\tau = -k_d\dot q$（`kp=0`）；
2. **站立模式**：阻尼模式下按 **`S`**，从**任意初始位置**连续地站起来（位置项目标从按下那一刻的姿态用
   smoothstep 推到站姿，控制器不变）；按 **`D`** 切回阻尼，狗在重力下自己塌回去。

窗口是自己写的（GLFW + `mjv/mjr`），因为要用键盘切模式——官方 `Simulate` 界面的按键挂不上自定义回调。
另有两种无窗口模式：`--mode sim`（回归：`--script "1:stand,5:damp,6:reset"` 按仿真时刻切状态，`reset` = 回到
`--start` 起点并回阻尼模式，跑完打印指标与判定，退出码 0/2/1）与 `--mode record`（**录像**：隐藏窗口离屏渲染 → ffmpeg，配合 `--script` 能直接做出
固定脚本的演示视频，不需要人按键；产物在 `output/cpp/`）。

电机不是"理想力矩源"一句话带过：限幅 / 死区 / 指令延迟 / 噪声四个开关都有，默认全关 = 理想；
并按讲义 §2.3 把"关节侧参数 ↔ 电机**转子侧**命令"的换算写在代码里（`motor::ToRotor`，默认减速比 6.33），
**第二部分对实机直接用同一组输出侧参数**。

地面也可调（从第二次培训的斜面 demo 移植进来，默认不生效）：`--pitch/--roll` 把平面地面转个角度
（狗跟着转、**重力不动**，所以越陡越站不住；高度/倾斜/漂移都改成相对地面法向算），
`--floor-friction "S [SPIN ROLL]"` / `--floor-condim N` 改摩擦（会连足底一起设：MuJoCo 的接触摩擦取
两 geom 逐元素最大，只改地面不生效）。默认 0° / 不改参数时，结果与加这个功能之前**逐位相同**。

**实现细节、实测数字与踩坑**：见 [`docs/sim.md`](docs/sim.md)。

## 环境与依赖

用仓库根 `pixi.toml` 的那一个环境（MuJoCo 3.12.0 的 C++ 库 + glfw），不需要新装东西。
C++ 侧不依赖 `MUJOCO_GL`（那是 Python 绑定选渲染后端用的）。

模型与场景：`models/black_description.xml` + `scenes/flat_scene.xml` 从 [`@20260923_mujoco/`](../@20260923_mujoco/)
**复制**过来（同一只狗、同一个场景，本任务自包含）；34 MB 的 mesh **只有一份**，`models/meshes` 软链接指向
[`../@20260923_mujoco/assets/urdf/meshes`](../@20260923_mujoco/assets/urdf/meshes)（场景里的 `meshdir` 由
`<compiler meshdir="../models/meshes"/>` 显式给出，所以 `scenes/` 下不再需要软链接，见
[`../docs/learn/mujoco.md`](../docs/learn/mujoco.md) §6.1）。

## 怎么跑

```bash
cd ..                                    # 仓库根目录（有 pixi.toml）
pixi run cmake -S @20260927_motor/cpp -B @20260927_motor/cpp/build -G Ninja -DCMAKE_PREFIX_PATH="$CONDA_PREFIX"
pixi run cmake --build @20260927_motor/cpp/build

pixi run @20260927_motor/cpp/build/motor_sim                       # 窗口：S 站立、D 阻尼、R 回到起点、Q/Esc 退出
pixi run @20260927_motor/cpp/build/motor_sim --help                # 全部参数

# 无窗口回归（退出码 0 = 判定通过、2 = 不通过、1 = 参数错误）
pixi run @20260927_motor/cpp/build/motor_sim --mode sim --seconds 5                        # ①阻尼模式：松手塌回趴卧
pixi run @20260927_motor/cpp/build/motor_sim --mode sim --seconds 6 --script "0.05:stand"  # ②按 S 起身
pixi run @20260927_motor/cpp/build/motor_sim --mode sim --seconds 10 --script "0.05:stand,5:damp"  # ③切回阻尼
pixi run @20260927_motor/cpp/build/motor_sim --mode sim --seconds 8 --start raw --script "0.05:stand,3:reset,4:stand"  # ④复位后再起身（= 窗口里按 R）
pixi run @20260927_motor/cpp/build/motor_sim --mode sim --seconds 6 --pitch 10 --start stance --script "0.05:stand"          # ⑤10° 斜面上站住
pixi run @20260927_motor/cpp/build/motor_sim --mode sim --seconds 6 --pitch 18 --start stance --script "0.05:stand"          # ⑤18°：翻倒（退出码 2）
pixi run @20260927_motor/cpp/build/motor_sim --mode sim --seconds 6 --pitch 15 --floor-friction 0.1 --start stance --script "0.05:stand"  # ⑤摩擦小 → 沿坡滑走（退出码 2）

# 录像（无窗口 + 脚本切换，给别人看的备用视频）
pixi run @20260927_motor/cpp/build/motor_sim --mode record --script "0.05:stand,5:damp" --seconds 8 --out @20260927_motor/output/cpp/damp_stand_damp.mp4
pixi run @20260927_motor/cpp/build/motor_sim --mode record --start rest --script "1:stand" --seconds 6 --out @20260927_motor/output/cpp/stand_up_from_rest.mp4
```

关键参数：`--start raw|stance|rest|side`（起点）、`--kp/--kd`（站立模式，默认 80/3 = 讲义 §1.4 的实机配置）、
`--kd-damp`（阻尼模式，默认 0.5）、`--ramp auto|SEC`（起身斜坡）、`--deadzone/--delay-cycles/--noise/--tau-max`
（非理想项）、`--script`（sim/record 模式的脚本，动作 `stand` / `damp` / `reset`；`reset` = 回到 `--start` 起点并回阻尼模式，
与窗口里的 `R` 键一致，保留仿真时间轴）、`--out/--fps`（录像）、
`--pitch/--roll/--floor-friction/--floor-condim`（倾斜地面与摩擦，默认全不生效；
量测自动改成相对地面法向，见 [`docs/sim.md`](docs/sim.md) §2.5）。

## 实测摘要（本机，详见 [`docs/sim.md`](docs/sim.md)）

| 场景 | 结果 |
|---|---|
| 阻尼模式，从原姿态起 5 s | 软瘫成趴卧：基座 z 0.5786 → **0.1450 m**、四足触地 4、末段 max\|q̇\| 0.000 → ✓ |
| 阻尼模式，`--kd-damp 3`（对照） | 侧翻：z 0.2043 m、竖直度 26.21°、**0 足触地** → 这种姿势再按站立键必然失败 |
| 站立模式，按下时**还在倒**（原姿态 0.05 s） | 自动选 0.1 s 斜坡 → 站住（z 0.4864、竖直度 0.25°、四足触地 4），**起身 0.07 s** ✓ |
| 站立模式，按下时**已经趴平**（3 s） | 自动选 1.5 s 斜坡 → 站住（z 0.4862），**起身 1.40 s** ✓ |
| 从趴卧 keyframe 起 | ✓ 起身 1.41 s；从站姿上起 ✓ 0.00 s |
| **侧躺（绕 x 转 90°）起** | ✗ 起不来（竖直度 89.53°、0 足触地）——纯 PD 到站姿没有"翻身"这一步，是已知边界 |
| 非理想项（死区 0.5 N·m + 延迟 2 周期 + 噪声 0.2 N·m） | 站立 ✓ / 切回阻尼 ✓，结论不变（死区削掉 32246 个电机·步的小力矩） |
| 倾斜地面（`--pitch`，摩擦默认 1） | 5° / 10° / 15° 均 ✓（漂移 0.06 / 0.12 / 0.23 m），**18° 翻倒** ✗ |
| 摩擦可调（`--pitch 15`） | μ ≥ 0.3 ✓（μ=0.3 时一路在滑，漂移 0.65 m）；μ ≤ 0.15 ✗ 滑走（6 s 漂 20.6 m） |
| 无窗口速度 | 2500 步 / 5 仿真秒 wall 107.6 ms（单步 0.0431 ms、**46.5x 实时**） |
| 录像（`--mode record`，1280×720 @50 fps） | 8 仿真秒 → **401 帧 / 8.020 s / 724 KiB**（录制 wall 10.9 s）；6 仿真秒 → **301 帧 / 6.020 s**（`output/cpp/` 两段片子，见 [`docs/sim.md`](docs/sim.md) §2.4） |

## 目录

```
@20260927_motor/
├── README.md            # 本文件：入口
├── docs/sim.md          # 第一部分的实现与实测（只对本任务成立的内容）
├── models/              # black_description.xml（从 @20260923_mujoco 复制）+ meshes 软链接
├── scenes/              # flat_scene.xml（同源复制；里面显式写 meshdir，不需要 meshes 软链接）
├── output/cpp/          # 产物：录像（`--mode record`）
└── cpp/
    ├── CMakeLists.txt   # 只链 mujoco + glfw（不链官方界面库：窗口是我们自己写的）
    └── src/
        ├── motor.h      # 关节电机：MIT 公式（含量纲说明）、转子侧换算、限幅/死区/延迟/噪声
        ├── stance.h     # 站姿搜索与量测（四足触地、高度、竖直度）
        ├── state.h      # 状态机：阻尼 / 站立 + 自动斜坡
        ├── viewer.h     # 自己写的窗口（键盘、鼠标相机、HUD）
        ├── recorder.h   # 无窗口录像（隐藏窗口 + 离屏 framebuffer → ffmpeg）
        ├── args.h       # 命令行解析（从 @20260923_mujoco/cpp_task2 复制，让本任务自包含）
        └── main.cpp     # 组装：三种模式（view / sim / record）与判定
```

## 目录（第三部分预备）

```
@20260927_motor/
└── cpp_part2/           # 第三部分（实机）预备：不接电机也能跑的 dry run
    ├── README.md        # 官方例程现状、PTY 为什么不行、报文/标度实测表、下一步
    └── src/
        ├── pty_serial_shim.c        # LD_PRELOAD：把 TIOCGSERIAL/TIOCSSERIAL 拦下来
        └── fake_motor_dryrun.cpp    # PTY + 假电机线程：跑通"上位机 → SDK → 报文 → 反馈"
```

## 第二部分（实机）预备：官方 SDK

任务书第二部分（实体电机）要用的就是宇树官方电机 SDK：
[`../../ReadOnly.d/unitree_actuator_sdk`](../../ReadOnly.d/unitree_actuator_sdk)
（`unitreerobotics/unitree_actuator_sdk`，clone 到本机的是 commit `5b79a42`）。核对结果：

| 讲义/任务书里的说法 | SDK 里的对应物 |
|---|---|
| 电机型号 GO-8010-6，减速比 6.33 | `MotorType::GO_M8010_6`（`include/unitreeMotor/unitreeMotor.h:9-13`）+ `queryGearRatio(MotorType)`（同文件 `:73`，减速比从 SDK 查，不用自己写 6.33） |
| 5 个命令 $T_{ff}, p_{des}, \omega_{des}, K_P, K_W$ | `MotorCmd{ tau, q, dq, kp, kd }`（`unitreeMotor.h:21-41`，**全部是转子侧**） |
| 反馈 `data.Pos/W` | `MotorData{ tau, dq, q, temp, merror, correct }`（`unitreeMotor.h:43-66`） |
| `mode = 0` 刹车、`mode = 1` FOC | `MotorMode{BRAKE, FOC, CALIBRATE}` + `queryMotorMode(type, mode)`（`unitreeMotor.h:15-19`、`:72`） |
| 官方例程让电机先转起来 | `example/example_goM8010_6_motor.cpp`（`SerialPort "/dev/ttyUSB0"`、`cmd.mode = queryMotorMode(GO_M8010_6, FOC)`、`serial.sendRecv(&cmd,&data)`、循环里打 `data.q/dq/temp/merror`）；A1 例子里用 `cmd.dq = -6.28*queryGearRatio(...)` 让它空转 |
| 零点标定/偏移（第二部分 3、4） | `MotorMode::CALIBRATE`；另有官方 GUI 工具 `motor_tools/Unitree_MotorTools_v1.2.4_x86_64_Linux` |

两个实际注意点：

1. **用例程的 C++ 版**。仓库里预编译的 Python 绑定是 `lib/unitree_actuator_sdk.cpython-38-x86_64-linux-gnu.so`
   （**Python 3.8**），而本仓库 pixi 环境的 Python 是 **3.12**，直接 `import` 会失败；要跑 Python 例程得自己重编 wrapper
   （仓库带 `thirdparty/python_wrapper`）。
2. 例程要 `sudo` 且要先确认串口设备（`/dev/ttyUSB0`，看实际枚举）与电机 ID；开环转动请像任务书说的那样
   用插值缓慢变化，先小角度试。

### SDK 侧明确写出来的"限幅"（与仿真侧对齐）

讲义/任务书里唯一写死的数值限制是**输出侧力矩 33.5 N·m**（讲义 §1.4），SDK 侧则有一层**报文定点标度**带来的
硬边界——这一层是我们这次 dry run 实测出来的（详见 [`cpp_part2/README.md`](cpp_part2/README.md)）：

| 量 | 报文类型 | 量程 | 分辨率 | 换算到关节侧（N=6.33） |
|---|---|---|---|---|
| `tor_des` / `torque` | `int16` q8 | ±127.996 N·m | 1/256 N·m | 关节侧 ±810 N·m（远大于 33.5，不是瓶颈） |
| `spd_des` / `speed` | `int16`（q7 ×π，实测） | ±804 rad/s（转子侧） | π/128 = 0.0245 rad/s | 关节侧 ±127 rad/s |
| `pos_des` / `pos` | `int32` q15 **圈** | ±65536 圈（转子侧） | 1/32768 圈 = 1.92e-4 rad | 关节侧分辨率 3.0e-5 rad |
| `k_pos` / `k_spd` | `uint16` q15 **归一化** | 0…32766（≈ K_P 0…25.6） | 1/1280 | `K_P = kp/N² = 1.997`（占量程 7.8%）；**超量程会被静默截到 32766**（实测：K_P = 49.9 与 99.8 都变 32766）——关节侧 kp 上限 ≈ 1026 |
| `temp` | `int8` | −128…127 °C | 1 °C | **90 °C 触发温度保护**（驱动板行为） |
| `MError` | 3 bit | 0 正常 / 1 过热 / 2 过流 / 3 过压 / 4 编码器故障 | — | 上层可以据此降额/停机 |

我们的仿真里保留的限幅与之一一对应：力矩限幅（`ctrlrange` ±20 / `--tau-max 33.5`，主文档 §2.6 有对照表）、
死区、指令延迟、噪声、位置限位、期望位置的斜率（`--ramp`）；**唯一没建**的是"高速段力矩随转速下降"，
理由见 [`docs/sim.md`](docs/sim.md) §2.6。

### dry run（不接电机）：已经跑通

官方例程**不接电机直接跑会崩**（`SerialPort` 构造抛 `IOException`，例程没接异常 → `terminate` +
core dumped）；想把串口换成 PTY 也不行（`SerialPort` 会对串口做 `TIOCGSERIAL`/`TIOCSSERIAL`，PTY 回
`ENOTTY`，与波特率无关）。做法是加一层 `LD_PRELOAD` 把这两个 ioctl 拦下来，再在 PTY 另一头起一个"假电机"
按报文格式回帧 —— 位置/速度/力矩/刚度四组标度与 CRC 都已实测对拍：

```bash
cd .. && S=../ReadOnly.d/unitree_actuator_sdk
gcc -O2 -fPIC -shared -o /tmp/pty_serial_shim.so @20260927_motor/cpp_part2/src/pty_serial_shim.c -ldl
g++ -O2 -std=c++14 -I$S/include -I$S/include/unitreeMotor \
    @20260927_motor/cpp_part2/src/fake_motor_dryrun.cpp \
    -L$S/lib -lUnitreeMotorSDK_Linux64 -Wl,-rpath,"$PWD/$S/lib" -pthread -o /tmp/fake_motor_dryrun
LD_PRELOAD=/tmp/pty_serial_shim.so /tmp/fake_motor_dryrun
```

仿真与实机的对齐方式已经在 `motor.h` 里备好：仿真算关节侧“$\tau = \tau_{ff} + k_p(q_{des}-q) + k_d(\dot q_{des}-\dot q)$”，
在实机上下发前用 `motor::ToRotor()` 换成转子侧（$\times N$ / $\div N$ / $\div N^2$），反馈用 $q = data.q/N + offset$。

**下一步（第二部分）**：dry run 已通（见上），接着把"假电机"从固定回帧换成一阶惯性 + 摩擦 + 限幅的小模型，
先在 dry run 上把「休息零点 → 插值到指定角 → 标记零点 → 偏移 +30° → 处理零点跳变」整套流程跑通，再接实机。
