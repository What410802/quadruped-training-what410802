# C++ 工程：`cpp_task2/` / `cpp_stand/` / `cpp_slope/`

> 三个工程都用**同一个 pixi 环境**与**同一份 MJCF**，所以数字能与 Python 侧直接对照；每个工程都是独立的
> `CMakeLists.txt`（工具链取自 pixi 环境）。
> 入口（怎么跑、结果在哪）见 [`../README.md`](../README.md)；任务 2 的结论与产物见 [`task2.md`](task2.md)，
> 倾斜地面 demo 的实测与踩坑见 [`stand.md`](stand.md)，上游复现见 [`replication.md`](replication.md)。

## 1 任务 2 的 C++ 版（`cpp_task2/`）

与 Python 侧**共用同一个 pixi 环境**和**同一份 MJCF**（`models/` + `scenes/`），所以两边算出的数字可以直接对照。两个可执行文件，分别对标两个 Python 脚本：

| 可执行文件 | 对标 | 干什么 |
|---|---|---|
| `rest_check` | `scripts/agent_scripts/rest_check.py` | 读场景自带的 `rest` keyframe、零力矩跑 N 秒，打印基座漂移/末段 max\|qvel\|/接触点数；退出码：0 = 静止趴住、2 = 判“未静止”、1 = 参数写错 |
| `dog_sim` | `scripts/simulate.py` / `simulate_record.py` | 不加载 keyframe（默认位形自然塌成趴卧）、零力矩跑 N 秒（默认 4 s）；三种模式：`--mode sim` 只仿真（无窗口无录像，全速）、`--mode record` 离屏录像、`--mode view`（**默认**）开 MuJoCo 官方 Simulate 窗口（时长不限，关窗结束） |

```bash
pixi run cmake -S @20260923_mujoco/cpp_task2 -B @20260923_mujoco/cpp_task2/build -G Ninja -DCMAKE_PREFIX_PATH="$CONDA_PREFIX"
pixi run cmake --build @20260923_mujoco/cpp_task2/build
pixi run @20260923_mujoco/cpp_task2/build/rest_check                                                 # 静止判定（默认 8 s），退出码 0 = 静止
pixi run @20260923_mujoco/cpp_task2/build/rest_check @20260923_mujoco/scenes/flat_scene_raw.xml 2   # 反例：穿模被弹飞，判“未静止”
pixi run @20260923_mujoco/cpp_task2/build/dog_sim                                                    # 默认：开官方 Simulate 窗口（关窗结束）
pixi run @20260923_mujoco/cpp_task2/build/dog_sim --mode record                                      # 离屏录像，录到 output/cpp/rest_down.mp4
pixi run @20260923_mujoco/cpp_task2/build/dog_sim @20260923_mujoco/scenes/flat_scene.xml 3 --mode sim # 只仿真（无窗口无录像）
```

两个程序的命令行都**不接受认不出的选项**：写错就直接报错退出（退出码 1）并打印用法，不会把 `--p` 这种未知选项默默当成场景路径；数值参数（`seconds`、`--fps/--width/--height`）不是数字、`--out` 这类缺值、`--mode` 不是 sim/record/view、位置参数超过两个也都同样报错。两个程序的解析逻辑都集中在 `cpp_task2/src/args.h`（`OptionDef` + `Args` + `ParseArgs`），主程序只声明自己认哪些选项、再取值。

实测（8 s、`ctrl=0`）：末 1 s xy 漂移 4.440e-10 m、末态 max|qvel| 6.06e-09、接触点数 8，与 Python 侧 `rest_check.py` **同一判据**（漂移 4.440e-10 m、ncon=8）。产物清单见 [`docs/task2.md`](task2.md)。

**录像**（`--mode record`，对应 Python 侧的 `VideoRecorder`）：离屏渲染（隐藏窗口拿 GL 上下文）→ `mjr_readPixels` → ffmpeg 管道，代码在 `cpp_task2/src/record.h`；出帧按 **仿真时间的严格网格**（第 k 帧对应 `k/fps` 仿真秒）决定，所以帧数 ≈ 时长×fps、MP4 的时间轴 = 仿真时间、与机器快慢无关（旧写法“距上次出帧过了 1/fps 就出”会被 dt=0.002 s 量化：5 仿真秒 @50 fps 只出 236 帧 / 4.72 s、@120 fps 只出 500 帧，视频比仿真快 6%–20%，见 [`docs/stand.md`](stand.md) 踩坑 10）；`--out/--fps/--width/--height/--camera` 可调——**`--out` 给了就按你写的路径解析（相对当前目录），不给才用默认（相对可执行文件的固定位置）**，终端里打印的是绝对路径。离屏缓冲会按 `--width/--height` 分配（建 context 前改 `vis.global.off*`），所以 1080p / 4K 是原生渲染而不是放大。实测 4 仿真秒 @50 fps @960×540 → `output/cpp/rest_down.mp4`：**201 帧 / 4.02 s**；5 仿真秒 @50 fps @960×540 → `output/cpp/slope_stand.mp4`：**251 帧 / 5.02 s**；三档分辨率的录像开销（251 帧：960×540 → 9.8–13.3 s、1920×1080 → 17.8–19.8 s、3840×2160 → 50.8 s）见 [`../docs/pitfalls/environment.md`](../../docs/pitfalls/environment.md) 的图形后端一节。

**窗口模式**（`--mode view`，默认）：链的是 conda 包里 MuJoCo 自带的官方界面库（`mujoco::libmujoco_simulate`，即 `mj::Simulate` + `mj::GlfwAdapter`），所以窗口与 Python 的默认窗口、`unitree_mujoco` 的 C++ 窗口**是同一个界面**：能暂停/单步/调速/换相机/拖动物体。起点与另两种模式一致（不加载 keyframe，零力矩从默认位形塌成趴卧）；物理线程把仿真时间轴钉在墙钟上（速度取界面上的下拉框，**上限 100%、不会比实时快**），实测倍率按官方语义（`measured_slowdown` = 墙钟/仿真，界面显示 `100/它` 并与目标速度比对、偏差超 10% 告警）写回界面，主线程跑 `RenderLoop()`（官方要求它在主线程），关窗后通知物理线程收工。时长**默认不限**，关窗才结束；给了 `seconds` 就到那个仿真时刻停止推进物理，窗口继续开着方便观察。实时率与暂停细节见 [`docs/stand.md`](stand.md) 踩坑 6/9。

一个坑：`Simulate::Load` 内部会**阻塞等渲染线程来接模型**（条件变量 `cond_loadrequest`），所以顺序必须是「主线程先跑 `RenderLoop()`，再由物理线程 `Load`」（官方 `main.cc` 就是把加载放在 `PhysicsThread` 里）；在 `RenderLoop` 之前调 `Load`，结果是开了一个窗口却一帧不画（任务栏有条目、Alt+Tab 里没有、内容空白）外加永久等待。

## 2 额外 demo：平地站稳与可调倾斜地面（`cpp_stand/` + `cpp_slope/`）

两个跟验收点无关、用来把「控制器 + 场景参数」跑通的小程序，共用一个头文件 `cpp_stand/src/control.h`（关节 PD：$\tau = k_p(q_{des}-q) - k_d\dot q$，可叠加 `qfrc_bias` 前馈）；`cpp_slope/` 在其基础上多 `--pitch/--roll`，把**地面**绕 y/x 轴转过去（**重力不动**），狗跟着转同一角度摆到斜面上。控制目标不是模型的默认位形（那一位形膝越界 0.85 rad、且质心在足后 0.18 m），而是初始化时**搜**出来的屈膝站姿（不读 keyframe、不改 XML）；**起点**用 `--start raw|stance|rest` 三选一（`raw` = 模型原姿态、`stance` = 直接站在站姿上、`rest` = 场景自带的趴卧 keyframe），`raw`/`rest` 由同一个 `RampFrom()` 在 `--ramp` 秒内把目标从起点推到站姿（**控制律不变**）。默认：`stand` 用 `raw`（从原姿态开始）、`slope` 用 `stance`（原姿态在斜坡上更容易摔），`slope` 会把起点自己摆到斜面上。默认场景：`stand` 用 `scenes/flat_scene.xml`，`slope` 用 `scenes/slope_scene.xml`（就是 flat_scene + 一张 MuJoCo 自带的棋盘格地面纹理，物理逐位不变；纯色地面看不出坡度，原因见 [`docs/stand.md`](stand.md) 踩坑 4/5）。

```bash
pixi run cmake -S @20260923_mujoco/cpp_stand -B @20260923_mujoco/cpp_stand/build -G Ninja -DCMAKE_PREFIX_PATH="$CONDA_PREFIX"
pixi run cmake --build @20260923_mujoco/cpp_stand/build
pixi run @20260923_mujoco/cpp_stand/build/stand                                  # 默认：原姿态起步（--start raw）→ 收腿 → 站住
pixi run @20260923_mujoco/cpp_stand/build/stand --mode sim --seconds 30          # 只仿真 30 s，打印指标与判定
pixi run @20260923_mujoco/cpp_stand/build/stand --mode sim --start stance        # 起点直接摆在站姿上（无起步过程）
pixi run @20260923_mujoco/cpp_stand/build/stand --mode sim --start rest --seconds 5   # 从趴卧（rest keyframe）起身，同一个 PD
pixi run @20260923_mujoco/cpp_stand/build/stand --mode sim --kp 300 --kd 6       # 增益扫（会判"未站稳"）
pixi run cmake -S @20260923_mujoco/cpp_slope -B @20260923_mujoco/cpp_slope/build -G Ninja -DCMAKE_PREFIX_PATH="$CONDA_PREFIX"
pixi run cmake --build @20260923_mujoco/cpp_slope/build
pixi run @20260923_mujoco/cpp_slope/build/slope --mode sim --pitch 15            # 15° 斜面，判"有没有离地/翻倒"
pixi run @20260923_mujoco/cpp_slope/build/slope --mode sim --start rest --pitch 10   # 斜面上从趴卧起身（同样是 --ramp 秒斜坡）
pixi run @20260923_mujoco/cpp_slope/build/slope --mode sim --start raw --pitch 10    # 斜面上从原姿态开始（实测只到 10°，对照表见 docs/stand.md）
```

实测（`--mode sim`）：默认起点（`stand` = 原姿态 `raw`，0.1 s 斜坡）下 5 s / 30 s 都是「四足站稳 ✓」（起始 z=0.5786 的直腿原姿态 → 末态 z=0.4928、竖直度 0.02°、四足触地 4、末 1 s 位移 0.0135 m，退出码 0）；`--start stance` / `--start rest`（趴卧）也都能站住（末 1 s 位移 0.0045 / 0.0022 m）；增益窗口窄且与起点无关（kp 150–200 ✓、kp 300–500 会滑走 ✗）；斜面默认起点 `stance`：≤15° 能撑住（15° 时 5 s 滑 0.1524 m 且四足不离地），≥20° 滑走翻倒（退出码 2）；斜面上也能从趴卧起身（≤15° ✓、≥20° 起不来）。站姿是初始化时**搜**出来的（不读 keyframe），增益窗口、限位/穿模、「原姿态必须快收腿」、「地面一直没真的转」与「触地计数只认足底球」那些坑都写在 [`docs/stand.md`](stand.md)。

## 3 任务 4 的结论（实测目前不必再复现 C++ 版 Unitree 官方实现）

任务 4 原计划是把 [`python/`](../python/) 的双缓冲结构用 C++ 复刻一遍（物理线程独占 `mjData`、渲染只读快照副本、锁只罩 memcpy）。实测结论是“不必复刻”：我们自己的物理线程 + MuJoCo 官方 `Simulate` 界面（`cpp_task2 --mode view`）本来就是非阻塞的——官方 `RenderLoop` 在 `Render()` 之前就放锁（源码注释 `// MutexLock (unblocks simulation thread)`），渲染在锁外、物理照常推进，实测 **1.00x 实时**（1 仿真秒 = wall 1.00 s）而且画面流畅；Python 侧那 0.14x 的缺口来自 GIL，C++ 里不存在这个问题。逐帧对比见 [`../docs/learn/runtime-timing.md`](../../docs/learn/runtime-timing.md) §11 的方案 ③，线程与通道结构的研读见 [`../docs/learn/unitree-mujoco.md`](../../docs/learn/unitree-mujoco.md)。

另外发现 `mj_step` 两边调用的是同一份 C 库，单步耗时几乎一样（实测数据见 [`../docs/pitfalls/environment.md`](../../docs/pitfalls/environment.md) 的「C++ 工具链」一节），渲染开销也只由 GPU 决定。

