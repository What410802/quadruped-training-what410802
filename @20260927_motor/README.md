# 第三次培训：关节电机（第一部分：仿真）

> 任务书 [`../../ReadOnly.d/Downloaded.d/第三次培训任务.pdf.md`](../../ReadOnly.d/Downloaded.d/第三次培训任务.pdf.md) 分两部分：**① 仿真**加控制程序（状态机、两个状态）、**② 实体电机控制**（SDK 转起来 → 回归零点 → 偏移零点 → 处理零点跳变）。讲义 [`../../ReadOnly.d/Downloaded.d/motor.pdf.md`](../../ReadOnly.d/Downloaded.d/motor.pdf.md) 讲 MIT 混合控制与零点/减速比。
> 本目录现在只做**第一部分**，用 C++。

## 做了什么

`cpp/`（C++ 工程，可执行文件 `motor_sim`）：把关节电机当 **MIT 混合控制器**自己算（讲义 §1.2），控制程序写成**两状态的状态机**——

1. **阻尼模式**（上电默认）：12 个关节都是阻尼状态，$\tau = -k_d\dot q$（`kp=0`）；
2. **站立模式**：阻尼模式下按 **`S`**，从**任意初始位置**连续地站起来（位置项目标从按下那一刻的姿态用
   smoothstep 推到站姿，控制器不变）；按 **`D`** 切回阻尼，狗在重力下自己塌回去。

窗口是自己写的（GLFW + `mjv/mjr`），因为要用键盘切模式——官方 `Simulate` 界面的按键挂不上自定义回调。
另有 `--mode sim` 无窗口回归模式：`--script "1:stand,5:damp"` 按仿真时刻切状态，跑完打印指标与判定（退出码 0/2）。

电机不是"理想力矩源"一句话带过：限幅 / 死区 / 指令延迟 / 噪声四个开关都有，默认全关 = 理想；
并按讲义 §2.3 把"关节侧参数 ↔ 电机**转子侧**命令"的换算写在代码里（`motor::ToRotor`，默认减速比 6.33），
**第二部分对实机直接用同一组输出侧参数**。

**实现细节、实测数字与踩坑**：见 [`docs/sim.md`](docs/sim.md)。

## 环境与依赖

用仓库根 `pixi.toml` 的那一个环境（MuJoCo 3.12.0 的 C++ 库 + glfw），不需要新装东西。
C++ 侧不依赖 `MUJOCO_GL`（那是 Python 绑定选渲染后端用的）。

模型与场景：`models/black_description.xml` + `scenes/flat_scene.xml` 从 [`@20260923_mujoco/`](../@20260923_mujoco/)
**复制**过来（同一只狗、同一个场景，本任务自包含）；34 MB 的 mesh **只有一份**，两处 `meshes` 软链接都指向
[`../@20260923_mujoco/assets/urdf/meshes`](../@20260923_mujoco/assets/urdf/meshes)。

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
```

关键参数：`--start raw|stance|rest|side`（起点）、`--kp/--kd`（站立模式，默认 80/3 = 讲义 §1.4 的实机配置）、
`--kd-damp`（阻尼模式，默认 0.5）、`--ramp auto|SEC`（起身斜坡）、`--deadzone/--delay-cycles/--noise/--tau-max`
（非理想项）、`--script`（sim 模式的切状态脚本）。

## 实测摘要（本机，详见 [`docs/sim.md`](docs/sim.md)）

| 场景 | 结果 |
|---|---|
| 阻尼模式，从原姿态起 5 s | 软瘫成趴卧：基座 z 0.5786 → **0.1450 m**、四足触地 4、末段 max\|q̇\| 0.000 → ✓ |
| 阻尼模式，`--kd-damp 3`（对照） | 侧翻：z 0.2043 m、竖直度 26.21°、**0 足触地** → 这种姿势再按站立键必然失败 |
| 站立模式，按下时**还在倒**（原姿态 0.05 s） | 自动选 0.1 s 斜坡 → 站住（z 0.4864、竖直度 0.25°、四足触地 4），**起身 0.07 s** ✓ |
| 站立模式，按下时**已经趴平**（3 s） | 自动选 1.5 s 斜坡 → 站住（z 0.4862），**起身 1.40 s** ✓ |
| 从趴卧 keyframe 起 | ✓ 起身 1.41 s；从站姿上起 ✓ 0.00 s |
| **侧躺（绕 x 转 90°）起** | ✗ 起不来（竖直度 89.53°、0 足触地）——纯 PD 到站姿没有"翻身"这一步，是已知边界 |
| 非理想项（死区 0.5 N·m + 延迟 2 周期 + 噪声 0.2 N·m） | 站立 ✓ / 切回阻尼 ✓，结论不变；撞限幅 **0** 次，\|τ\| 峰值 4.66 N·m（限幅 ±20 用不到） |
| 无窗口速度 | 2500 步 / 5 仿真秒 wall 107.6 ms（单步 0.0431 ms、**46.5x 实时**） |

## 目录

```
@20260927_motor/
├── README.md            # 本文件：入口
├── docs/sim.md          # 第一部分的实现与实测（只对本任务成立的内容）
├── models/              # black_description.xml（从 @20260923_mujoco 复制）+ meshes 软链接
├── scenes/              # flat_scene.xml（同源复制）+ meshes 软链接
└── cpp/
    ├── CMakeLists.txt   # 只链 mujoco + glfw（不链官方界面库：窗口是我们自己写的）
    └── src/
        ├── motor.h      # 关节电机：MIT 公式、转子侧换算、限幅/死区/延迟/噪声
        ├── stance.h     # 站姿搜索与量测（四足触地、高度、竖直度）
        ├── state.h      # 状态机：阻尼 / 站立 + 自动斜坡
        ├── viewer.h     # 自己写的窗口（键盘、鼠标相机、HUD）
        ├── args.h       # 命令行解析（从 @20260923_mujoco/cpp_task2 复制，让本任务自包含）
        └── main.cpp     # 组装：两种模式（view / sim）与判定
```

**下一步（第二部分）**：实机 SDK 侧要用的换算（`N`、`offset`）已经在 `motor.h` 里备好；
本任务目前只有仿真，第二部分（实体电机）待做。
