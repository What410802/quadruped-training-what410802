# 子任务项一（仿真部分）：关节电机 + 状态机

> 任务书第一条：仿真里加控制程序模拟关节电机的特性，控制程序写成状态机，含两个状态—— ① 阻尼模式（所有关节电机都是阻尼状态）；② 站立模式（阻尼模式下按键就能从任意初始位置连续地站起来， 另一个键切回阻尼）。讲义与任务书在 [`../docs/teaching-materials/`](../docs/teaching-materials/)。
>
> 目录（TOC）：[做了什么](#做了什么) · [怎么跑](#怎么跑) · [关键参数](#关键参数) · [实测摘要](#实测摘要) · [目录](#目录)

**实现细节、实测数字与踩坑**：见 [`docs/sim.md`](docs/sim.md)（其中 §6 专门对照了 [**与第二次培训那套站立控制的区别**](docs/sim.md#6-与第二次培训站立控制的区别)：控制律的完整度、 谁决定"模式"、斜坡怎么定、增益从哪来、限幅在哪一层）。

## 做了什么

可执行文件 `motor_sim`：把关节电机当 **MIT 混合控制器**自己算（讲义 §1.2），控制程序写成**两状态的状态机**——

1. **阻尼模式**（上电默认）：12 个关节都是阻尼状态，$\tau = -k_d\dot q$（`kp=0`）；
2. **站立模式**：阻尼模式下按 **`S`**，从**任意初始位置**连续地站起来（位置项目标从按下那一刻的姿态用 smoothstep 推到站姿，控制器不变）；按 **`D`** 切回阻尼，狗在重力下自己塌回去。

窗口是自己写的（GLFW + `mjv/mjr`），因为要用键盘切模式——官方 `Simulate` 界面的按键挂不上自定义回调。 另有两种无窗口模式：`--mode sim`（回归：`--script "1:stand,5:damp,6:reset"` 按仿真时刻切状态，`reset` = 回到 `--start` 起点并回阻尼模式，跑完打印指标与判定，退出码 0/2/1）与 `--mode record`（**录像**：隐藏窗口离屏渲染 → ffmpeg，配合 `--script` 能直接做出固定脚本的演示视频，不需要人按键；产物在 `../output/cpp/`）。

电机不是"理想力矩源"一句话带过：限幅 / 死区 / 指令延迟 / 噪声四个开关都有，默认全关 = 理想； 并按讲义 §2.3 把"关节侧参数 ↔ 电机**转子侧**命令"的换算写在代码里（`motor::ToRotor`，默认减速比 6.33）—— 这是给子任务项二准备的：实机对同一组输出侧参数。

地面也可调（从第二次培训的斜面 demo 移植进来，默认不生效）：`--pitch/--roll` 把平面地面转个角度 （狗跟着转、**重力不动**，所以越陡越站不住；高度/倾斜/漂移都改成相对地面法向算）， `--floor-friction "S [SPIN ROLL]"` / `--floor-condim N` 改摩擦（会连足底一起设：MuJoCo 的接触摩擦取 两 geom 逐元素最大，只改地面不生效）。默认 0° / 不改参数时，结果与加这个功能之前**逐位相同**。

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

## 关键参数

`--start raw|stance|rest|side`（起点）、`--kp/--kd`（站立模式，默认 80/3 = 讲义 §1.4 的实机配置）、 `--kd-damp`（阻尼模式，默认 0.5）、`--ramp auto|SEC`（起身斜坡）、`--deadzone/--delay-cycles/--noise/--tau-max` （非理想项；`--deadzone N` 会分别报"落死区 N 电机·步（占比）"与"进出死区 M 次"两个数，原因见 [`docs/sim.md`](docs/sim.md) §4 踩坑 15）、`--script`（sim/record 模式的脚本，动作 `stand` / `damp` / `reset`；`reset` = 回到 `--start` 起点并回阻尼模式，与窗口里的 `R` 键一致，保留仿真时间轴）、 `--out/--fps`（录像）、`--pitch/--roll/--floor-friction/--floor-condim`（倾斜地面与摩擦，默认全不生效； 量测自动改成相对地面法向，见 [`docs/sim.md`](docs/sim.md) §2.5）、`--dump-stance FILE`（把搜出来的站姿 写进文件后退出；**但仓库里的 `../models/stance.txt` 现在不是它写的** —— 那份是重搜出来的低站姿（理由与实测见 [`docs/essential.md`](docs/essential.md) §4），本条命令（只扫膝 0.9/1.1/1.3）会写回旧的高站姿；格式与指纹见 [`src/stance_file.h`](src/stance_file.h)）。

## 实测摘要

本机 i5-1035G1 + MuJoCo 3.12.0。**完整表格（含可复现命令、对照实验与踩坑）在 [`docs/sim.md`](docs/sim.md) §3**， 这里只留三条一眼要记住的：阻尼模式 5 s 软瘫成趴卧（z 0.1450 m、四足触地）、站立模式在 0.05 s 与 3 s 按下都能 站住（自动选 0.1 s / 1.5 s 斜坡，起身 0.07 / 1.40 s）、**侧躺 90° 起不来**是已知边界（纯 PD 不会翻身）； 无窗口 46.5x 实时，倾斜地面 15° 站得住、18° 翻倒，摩擦 μ ≤ 0.15 沿坡滑走。

## 目录

```
@20260927_motor/
├── cpp/
│   ├── CMakeLists.txt   # 只链 mujoco + glfw（不链官方界面库：窗口是我们自己写的）
│   ├── README.md        # 本文件：怎么建、怎么跑、参数、实测摘要
│   ├── docs/sim.md      # 实现细节、全部实测数字、踩坑；§6 与第二次培训控制程序对照
│   ├── docs/essential.md# 两个精简版的差别、理由与验证（低站姿的来历、踩坑、对拍方法）
│   ├── src/             # 完整版：三种模式（view/sim/record）+ 倾斜地面/摩擦 + 电机非理想项
│   │   ├── main.cpp        # 只做编排：解析参数 → 装配现场 → 三种模式与判定
│   │   ├── cli.h           # 命令行面：用法文本、选项表、取值与全部校验
│   │   ├── scene_setup.h   # 现场装配：场景 XML → 地面/脚 → 站姿搜索 → 地面倾角 → 摆到起点
│   │   │                   #   （setup::Scene 持有 model/data，失败时自动释放）
│   │   ├── motor.h         # 关节电机：MIT 公式（含量纲说明）、转子侧换算、限幅/死区/延迟/噪声、统计
│   │   ├── stance.h        # 站姿搜索与量测口径（四足触地、高度、竖直度、漂移）
│   │   ├── state.h         # 状态机：阻尼 / 站立 + 自动斜坡
│   │   ├── observation.h   # 观测：Snapshot/Sample + “算不算起身完成”
│   │   ├── start.h         # 起点：摆位（raw/stance/rest/side）与“回到起点”（R / reset）
│   │   ├── viewer.h        # 自己写的窗口（键盘、鼠标相机、HUD）
│   │   ├── recorder.h      # 无窗口录像（隐藏窗口 + 离屏 framebuffer → ffmpeg）
│   │   ├── ground.h        # 倾斜地面与摩擦（默认 0° / 不生效）
│   │   ├── stance_file.h   # 站姿文件：格式/指纹 + 写（把搜出来的站姿存给最简版用）
│   │   └── args.h          # 命令行语法（从 @20260923_mujoco/cpp_task2 复制，让本任务自包含）
│   ├── essential/       # 最简版：窗口用 MuJoCo **官方** Simulate 界面，按键从**终端**读（src/tty.h），
│   │   ├── README.md    #   一次读懂用（怎么跑、按键、目录）
│   │   └── src/         #   按需精简的同名头文件（无 Search/无倾斜/无录像）+ stance_file.h（只读那一半）+ main.cpp
│   ├── essential_core/  # 核心版（无 README：说明在 main.cpp 文件头与 docs/essential.md）：两个状态
│   │   └── src/         #   + 一条 MIT 公式 + 一个站姿（内联在 state.h）；state.h / main.cpp / tty.h
│   └── agent_scripts/   # 一次性/诊断工具（不进 CMake，用法写在各自文件头）：search_stance.cpp（重新搜站姿）
├── models/ + scenes/    # 模型与场景（从 @20260923_mujoco 复制）；另有搜好存下的 models/stance.txt
└── ../output/cpp/       # 录像产物（damp_stand_damp.mp4、stand_up_from_rest.mp4）
```

与第二次培训那套站立控制的逐条对照（控制律完整度、谁决定"模式"、斜坡怎么定、增益从哪来、限幅在哪一层）， 以及"两边用手同一组增益收敛到同一个末态（z 0.4864 m、竖直度 0.24°）"的实测，见 [`docs/sim.md`](docs/sim.md) §6。
