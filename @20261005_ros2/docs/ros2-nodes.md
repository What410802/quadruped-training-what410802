# 三个节点与消息接口：设计取舍、线程模型、实测与坑

> 入口（怎么编译、怎么跑、目录在哪）见 [`../README.md`](../README.md)；推进情况见 [`status.md`](status.md)；手柄那一半单独在 [`joystick.md`](joystick.md)。本文只写**节点与接口本身**：为什么这么设计、实测多少、踩过什么坑。
>
> 任务书：`ros2任务.pdf.md`（本机只读材料）第 1–2 项与第 4 项。

## 1 接口：三个自定义消息 + Imu

| 话题 | 类型 | 方向 | QoS（发布/订阅都是它） | 实测频率 |
|---|---|---|---|---|
| `/mit_command` | `quadruped_ros2/msg/MitCommand` | 控制器 → 仿真 | best_effort、depth 1 | 499.99 Hz |
| `/motor_state` | `quadruped_ros2/msg/MotorState` | 仿真 → 控制器 | best_effort、depth 1 | 499.98 Hz |
| `/imu` | `sensor_msgs/msg/Imu` | 仿真 → 控制器 | best_effort、depth 1 | 同上（同步发） |
| `/joy` | `sensor_msgs/msg/Joy` | 手柄 → 控制器 | reliable、depth 1 | 100 Hz |
| `/control_status` | `quadruped_ros2/msg/ControlStatus` | 控制器 → 手柄（回程） | reliable、depth 1 | 5 Hz（参数 `status_period_ms`） |
| `/sim_reset` | `std_srvs/srv/Empty`（服务） | 控制器 → 仿真 | — | 手柄按 X 时 |

复现（仓库根；两个节点起来后）：

```bash
pixi run ros2 topic hz /motor_state           # average rate: 499.978
pixi run ros2 topic info /motor_state -v      # Reliability: BEST_EFFORT（两端一致）
pixi run ros2 interface show quadruped_ros2/msg/MotorState
pixi run ros2 node info /sim_node             # 订阅/发布/服务一览
```

三条设计决策：

1. **控制器只发 MIT 五参数，不算力矩**。`MitCommand` 就是 `{kp, kd, q, w, tau}` 各 12 个数；力矩由仿真侧的电机模型算（`τ = tau + kp·(q_des − q) + kd·(w_des − q̇)`）。这与实机分工一致：驱动板里封好了 FOC 电流环，上层只发这 5 个量（讲义 §1.2/§2.3，见 [`../../@20260927_motor/docs/teaching-materials/motor.pdf.md`](../../@20260927_motor/docs/teaching-materials/motor.pdf.md)）。好处是"电机侧的非理想项"（死区 / 指令延迟 / 噪声 / 电流限幅）将来**只改仿真侧**，控制器一个字不用动。
2. **`MotorState` 除了任务书要的 5 个数组，还带一个 `sim_time`**。控制器的起身斜坡按**仿真时间**算，不是墙上时间：仿真全速跑（`realtime:=false`，回归用）时"1 s 站完"仍然是 1 s 仿真时间，量出来的轨迹与实时跑逐位一致，回归脚本也不必等真实时间。`header.stamp` 照惯例填发布时刻的 ROS 时间（做延迟分析用），两个时间各司其职。
3. **`cur`（电流）一律报 0：没有支撑模型与数据就不编**。MuJoCo 的执行器是纯力矩源（`<motor gear="1">`，`ctrl` 就是关节侧力矩），模型里既没有电流环也没有电流传感器。曾经按 `cur = tau/(减速比 × Kt)` 折算过，后来**删掉了**，理由：转矩常数 `Kt` 无出处（讲义与手册都没给 GO-M8010-6 的值，只能猜 1.0），算出来的数看着有量纲、却与实机电流没有可验证的对应关系——那属于"编数据"，比留空更糟。所以现在 `cur` 恒 0，含义明确为**未测量**（培训方口径："读不到就置 0"）；相关参数 `kt`/`publish_current` 也一并去掉（`gear` 参数停用，减速比 6.33 作为讲义给的真值留在 `motor.hpp` 的常量里备查）。将来真要做电流，需要的是**电机电气模型 + 实测标定数据**（转子侧换算见讲义 §2.3）。

### 1.1 `ddq` 与 `cur` 到底读不读得到（实测）

| 字段 | MuJoCo 里是什么 | 三阶段实测（同一次起身：趴卧 → 按 A → 站住） |
|---|---|---|
| `ddq` | **读得到**：`data.qacc`（DOF 空间加速度，`mj_step` 里由前向动力学算出），取执行器所在自由度的分量 | 起身过程 max **7.246 rad/s²**；趴卧静止 max 5.10e-06；站住静止 max 1.67e-05（即"数值零"，是约束求解的残差，不是硬编码 0） |
| `tau` | **读得到**：`data.actuator_force`（关节侧实际输出力矩，已含 `ctrlrange` 限幅） | 起身过程 max **9.2448 N·m**；站住 hold 力矩 max 5.5794 N·m；趴卧阻尼 0.0000 |
| `cur` | **读不到**：模型里没有电流环、也没有电流传感器（见上面第 3 条） | **恒 0.0000 A**（三阶段实测都是 0，含义是"未测量"） |

复现：起 `sim_node`（`-p viewer:=false -p status_period_s:=0.0`）+ `controller_node`，用一个订阅 `/motor_state` 的小脚本在 t=8 s 发一条"按 A"的 `Joy`，分三个时间窗统计 `max|ddq| / |tau| / |cur|`（做法与 [`../scripts/agent_scripts/check_joystick_device.py`](../scripts/agent_scripts/check_joystick_device.py) 里那个探头一样）。所以：**`ddq` 读真值（不用置 0），`cur` 恒 0（不推定）**。

### 1.2 参数表：人 / 外部程序与这个包的接口

三个节点一共 **34 个参数**（`ros2 param list` 的权威输出，另有框架自带的 `use_sim_time` 与 `qos_overrides.*` 未列）：仿真 18 / 控制器 9 / 手柄 7。「launch 参数」与「节点参数」是两套东西（前者只在 launch 脚本里，**必须显式桥接**才会变成后者）——机制、三个坑与优先级见 [`../../docs/learn/ros2-params-and-launch.md`](../../docs/learn/ros2-params-and-launch.md)。**"launch" 一列写的是 launch 参数名**——`ros2 launch quadruped_ros2 bringup.launch.py <名字>:=<值>` 就能改；写 `—` 的表示只在节点参数里（改法：运行时 `ros2 param set`，或单节点起时 `ros2 run … --ros-args -p 名:=值`）。

**仿真节点 `sim_node`（18 个）**

| 参数 | 类型 | 默认 | 说明 | launch |
|---|---|---|---|---|
| `scene` | string | `""` | 场景 xml；空 = 从可执行文件往上找 `scenes/flat_scene.xml` | `scene` |
| `start` | string | `raw` | 起点：`raw` = 模型原姿态（默认，与上次任务 `@20260927_motor` 的 `--start` 一致），`rest` = 场景里的趴卧 keyframe | `start` |
| `viewer` | bool | `true` | 开自建窗口（GLFW + mjv/mjr，见 §2）；无 `DISPLAY`/`WAYLAND_DISPLAY` 时自动降级为关 | `viewer` |
| `realtime` | bool | `true` | 物理按墙钟节流；`false` = 全速跑（回归用，跑得比实时快） | `realtime` |
| `viewer_shadow` | bool | `true` | 视口阴影（**运行时也有效**：窗口里按 `S` 切换） | `viewer_shadow` |
| `viewer_shadow_size` | int | `4096` | 阴影贴图边长（= 模型默认）；`0` = 用模型默认。阴影是逐片元硬比较，纹素 = `2·extent·clip/(shadowsize−2)`，所以它直接决定阴影边界的量化；4096 比 1024 只多 0.2~0.6 ms/帧、边界偏移小 4.3×。**只在建窗口时用一次**，改它要重启 | `viewer_shadow_size` |
| `viewer_shadow_clip` | double | `1.0` | 阴影正交盒半宽 = `stat.extent × 本值`（**只对平行光有效**，1.0 ⇒ 覆盖半径 ±1.33 m）。画质只取决于 `clip/shadowsize` 的比值：调小它也能让纹素变细，但覆盖同比缩小（狗走远就没阴影）。只在建窗口时用一次，改它要重启 | `viewer_shadow_clip` |
| `viewer_msaa` | int | `4` | 多重采样（抗锯齿）；`0` = 关。窗口默认 framebuffer 拿不到时自动改用离屏缓冲的 `offsamples`（本机实测窗口 MSAA 恒为 0） | `viewer_msaa` |
| `viewer_render_scale` | int | `2` | 超采样倍率：离屏按"倍率 × framebuffer"渲染再 `GL_LINEAR` 缩回窗口；`1` = 关。**与 MSAA 互斥**（同开画面全黑，节点自动关 MSAA 并提示） | `viewer_render_scale` |
| `motor_deadzone` | double | `0.0` | 电机静摩擦死区 [N·m]：`0 < \|τ\| < 死区` → 输出 0；`0` = 理想力矩源 | `motor_deadzone` |
| `motor_delay_cycles` | int | `0` | 电机指令延迟 [控制周期]：用 N 个周期之前下发的那条指令 | `motor_delay_cycles` |
| `motor_noise` | double | `0.0` | 电机力矩噪声标准差 [N·m]（加在限幅之后） | `motor_noise` |
| `motor_seed` | int | `12345` | 噪声种子：同参数 + 同 seed → 同一条噪声序列（回归可复现） | `motor_seed` |
| `publish_every` | int | `1` | 每多少物理步发一次 `/motor_state`+`/imu`（1 = 500 Hz） | — |
| `tau_max` | double | `20.0` | 关节力矩限幅 [N·m]（仿真侧电机模型里的 `ctrlrange`） | — |
| `damp_kd` | double | `0.5` | 看门狗退回阻尼模式时用的 `kd` | — |
| `command_timeout_ms` | int | `200` | 多少毫秒没收到 `/mit_command` 就退回阻尼（换算成**步数**判定，见 §3） | — |
| `status_period_s` | double | `1.0` | 每多少**仿真秒**打一行状态（`t=… z=… tilt=… ncon=…`）；`0` = 不打 | — |

**控制器节点 `controller_node`（9 个）**

| 参数 | 类型 | 默认 | 说明 | launch |
|---|---|---|---|---|
| `kp` | double | `80.0` | 站立模式位置刚度 | `kp` |
| `kd` | double | `3.0` | 站立模式速度刚度 | `kd` |
| `kd_damp` | double | `0.5` | 阻尼模式速度刚度（趴下/塌回时用，`kp` 恒 0） | `kd_damp` |
| `ramp` | double | `1.0` | 起身斜坡时长 [s]；按 `MotorState.sim_time` 计时，不是墙钟 | `ramp` |
| `button_stand` | int | `0` | 站立键索引（xpad：A=0 B=1 X=2 Y=3 LB=4 RB=5 …） | `button_stand` |
| `button_damp` | int | `1` | 阻尼键索引 | `button_damp` |
| `button_reset` | int | `2` | 复位键索引（调 `/sim_reset` 并切回阻尼） | `button_reset` |
| `tilt_warn_deg` | double | `60.0` | 倾角告警阈值 [deg]（超过就打警告，不改变控制） | `tilt_warn_deg` |
| `status_period_ms` | int | `200` | `/control_status` 的发布周期 [ms]（5 Hz） | — |

**手柄节点 `joy_node`（7 个）**

| 参数 | 类型 | 默认 | 说明 | launch |
|---|---|---|---|---|
| `device` | string | `""` | 指定设备路径（如 `/dev/input/event15`）；空 = 自动找 | `device` |
| `name` | string | `xbox,x-box,xinput` | 自动找时要求设备名含其中任一子串（逗号分隔）；空 = 任何手柄都收 | `name` |
| `deadband` | double | `0.08` | 摇杆死区（0..1）；磨损摇杆自漂时调大 | `deadband` |
| `device_dir` | string | `/dev/input` | 扫描哪个目录 | — |
| `rate_hz` | double | `100.0` | `/joy` 发布频率 | — |
| `topic` | string | `joy` | 发布的话题名 | — |
| `status_topic` | string | `control_status` | 订阅哪个话题做"回程"打印（任务书要求的消息互换） | — |

**launch 参数共 25 个**：上表"launch"列里出现的 24 个，加上 `joy`（`true`/`false`，决定起不起手柄节点——它不是节点参数，而是 launch 的条件开关）。**划分口径**：随外部世界变化或要现场整定的（场景/形态、协议口径、整定增益、手柄与按键映射、倾角阈值）都从 launch 给；模型常数（`tau_max`）与实现细节（看门狗、日志频率、话题名）留在节点参数里（`viewer_shadow*` 三个是"视口画质"，属于会随机器/显示器变化的旋钮，所以也放进 launch），因为它们有合理默认值、改它们的场合是开发调试。

### 1.3 IMU：什么时候加进模型的、本任务拿它做什么

**加的时间**：`imu_link` 本身从第二次培训（`@20260923_mujoco` 的 URDF 转换）就在模型里，但**传感器是本次任务加的**——`@20260923_mujoco` 与 `@20260927_motor` 的 `black_description.xml` 里 `<sensor>` 段计数都是 **0**，本次在 [`../models/black_description.xml`](../models/black_description.xml) 里补了：

* `<site name="imu" pos="0 0 0" size="0.005"/>`（第 68 行，挂在 `imu_link` 下）——MuJoCo 3.12 的 `gyro`/`accelerometer` 只能挂 site，`framequat` 用 `objtype="body"` 又对不上（见 §7 坑 5）；
* `<sensor>` 三项（第 197 行起）：`framequat name="imu_quat"`（世界系姿态，四元数 **w x y z**）、`gyro name="imu_gyro"`、`accelerometer name="imu_acc"`。

站点无质量、无碰撞、不参与物理：同场景同起点各跑 1000 步，`qpos`/`qvel` 最大差 **0.0**，`nsensordata` 从 0 变 10（复现见 §7 坑 4）。

**为什么加**：任务书要求仿真→控制器方向的反馈除了 `{q, dq, ddq, tau, cur}` 还有 IMU；顺带把"姿态"这条链路补全，好让上位机能知道机身歪没歪。

**本任务拿它做什么（这一点容易误解）**：控制律**不用** IMU——`controller_node` 是纯关节空间的 MIT/PD 控制，只用 `MotorState` 里的关节量。IMU 目前是**安全与监控量**：

| 用途 | 代码位置 | 说明 |
|---|---|---|
| 算倾角 | `include/quadruped_ros2/attitude.hpp` 的 `TiltDeg()` | `max(abs(roll), abs(pitch))`，从四元数取欧拉角，单位度 |
| 超阈值告警 | `src/controller_node.cpp` `OnImu()` | 超过 `tilt_warn_deg`（默认 60°）打 `WARN`，**不改变控制输出** |
| 回程显示 | 同上 + `ControlStatus.tilt_deg` | 手柄节点订阅 `/control_status` 后会打印"倾角=…"，就是这里的数 |

换句话说：现在的"狗站起来了、倾角 0.0°"是**监控**结论；将来若要做倒地检测、姿态闭环或状态估计，接的也是这条链路（`/imu` 500 Hz、best_effort、机体系原始量）。IMU 的方向约定与坑（`gyro`/`accelerometer` 是机体系、静止时加速度计 z ≈ +9.81、四元数顺序与 ROS `Imu` 相反）见 §7 坑 5、6。

## 2 控制周期与线程模型

控制周期 = 物理步长 = **0.002 s（500 Hz）**，与实机主控同量级。节点里**只有两条线程**：

| 线程 | 干什么 | 碰不碰 `mjModel`/`mjData` |
|---|---|---|
| **主线程**（= 仿真 + 渲染） | 装现场 → 建窗口 → 一个循环里"按墙钟补齐物理步（取指令 → 算力矩 → `mj_step` → 发反馈）→ 画一帧" | **只有它碰**（所以不需要任何锁） |
| **ROS 执行器线程** | 收 `/mit_command`、答 `/sim_reset` | **不碰**：只写 `SimNode` 自己的命令行槽位（一把只护 12 个 double 的小锁）与一个原子复位标志 |

两种节奏（同一个循环体）：**有窗口**时"每帧把物理补齐到当前墙钟再画"（物理仍 500 Hz、渲染跟 vsync 走，实测每帧补 8.3 步；补步数上限 `kMaxCatchupSteps=200`，防止卡一下之后一帧里追赶上千步造成画面"瞬移"）；**无窗口**时一步一节流（deadline pacing：误差不累积、落后就重新对齐不追赶），与自检/回归脚本的口径完全一致。窗口模式下 `realtime:=false` 仍按墙钟节流（要全速跑请 `viewer:=false`，节点会打一行提示）。

**为什么这样分线程更安全**：`mjData` 不是线程安全的，共享它就得上锁；现在的做法是"**谁拥有谁访问**"——仿真数据只有主线程碰，ROS 线程只通过两个明确定义的槽位（最新指令 / 复位请求）与它通信。这比"围绕共享数据加锁"更难写错，也是 2026-10-06 从"官方界面 + 三线程 + 递归锁"改过来的原因（性能见 §2.1）。

### 2.1 视口性能：为什么换掉官方界面、换了之后多少（实测，2026-10-06）

**现象**：官方 `Simulate` 窗口在仿真进行时移动鼠标会觉得卡；上一次任务的**自建窗口**（`@20260927_motor/cpp/src/viewer.h`）拖动几乎无感。

**诊断**：不是"官方界面更新率更低"——不碰鼠标时两边都是 ~57 fps。差别在架构：官方是"物理线程 + UI 线程共享一把递归锁"，UI 线程每帧要重绘两套 mjUI 面板、每个鼠标事件都要对面板做命中测试；自建窗口是单线程、完全无锁、每帧只画场景 + 两段文本。同一套鼠标负载（uinput 虚拟鼠标、~250 次/秒持续移动）下：

| 配置 | 鼠标负载 | 均值 | p50 | p95 |
|---|---|---|---|---|
| 官方 `Simulate`（UI 面板开） | 无 | 17.6 ms（56.9 fps） | 16.9 ms | 23.2 ms |
| 官方 `Simulate`（UI 面板开） | 持续移动 | 23.2 ms（**43.1 fps**） | 23.1 ms | **41.8 ms** |
| 官方 `Simulate`（UI 面板关） | 持续移动 | 21.8 ms（46.0 fps） | 21.2 ms | 26.1 ms |
| **现在的自建窗口**（`viewer.hpp`，阴影 1024） | 持续移动 | **16.7 ms（60.0 fps）** | 16.7 ms | **17.6 ms** |
| 参考探针（上次任务的窗口，阴影用模型默认 4096） | 持续移动 | 17.4 ms（57.5 fps） | 17.4 ms | 21.5 ms |

**顺带发现：自建窗口不是没有优化空间。** 关掉垂直同步量"纯渲染工作量"（1280×720 窗口，本机 framebuffer 是 2× → 2560×1440）：

| 阴影设置 | 纯工作量/帧 |
|---|---|
| 模型默认 `shadowsize=4096` | **15.5 ms（64.5 fps）——只剩 1.2 ms 余量，60 fps 下经常掉帧** |
| `shadowsize=1024` | 8.9 ms（112 fps） |
| `shadowsize=512` | 8.4 ms（119 fps） |
| 关掉阴影（`light_castshadow=0`） | 2.9 ms（349 fps） |

**⚠ 上表的绝对值口径不一致，别跨 shadowsize 对比**：这三行是透过**真实窗口**量的（含 vsync 与 blit）。同一路径的离屏对照（2560×1440、`offsamples=0`、11 次中位、开/关阴影相减）：1024 → 9.67 ms、4096 → **9.85 ms/帧**（净阴影开销 2.83 → 3.17 ms），所以默认取 4096；画质理由见 §3.0 与 [`docs/learn/graphics-stack.md` §8.3](../../docs/learn/graphics-stack.md)。

**为什么要区分两种"阴影开关"**（这也是"为什么官方面板里能实时勾掉阴影、而改 shadowsize 不生效"的答案）：

| | 是什么 | 什么时候被读 | 运行中改有没有用 |
|---|---|---|---|
| `mjvScene.flags[mjRND_SHADOW]`（面板里的 "Shadow" 勾选、我们的 `viewer_shadow` 参数 / `S` 键） | **渲染标志** | `mjr_render` **每帧**读一次 | ✅ 立刻生效（官方 `simulate.cc` 自己也在运行时改它，见 2620/3025 行） |
| `mjVisual.quality.shadowsize`（我们的 `viewer_shadow_size` 参数） | **阴影贴图的边长** | 只在 `mjr_makeContext` 建 GL 上下文、分配 shadow FBO/纹理时读一次 | ❌ 运行中改模型字段不会重建上下文；官方 `simulate/` 里 `mjr_makeContext` **全程只调一次**（`platform_ui_adapter.cc:30`，加载模型时），所以那边也同样改不动 |

实测印证（同一份代码，只差"设的时机"）：**建上下文之前**设 `shadowsize` → 512/1024/2048 分别是 8.4 / 8.9 / 10.1 ms；**建完之后**再设 → 18.0 / 18.6 / 16.0 ms（没变化，就是噪声）。

所以现在取 **`shadowsize=1024`**（`sim_node.cpp` 的 `kViewerShadowSize`：保留阴影，余量翻倍）——注意**必须在建 GL 上下文之前设**（上下文建好后改无效，第一次测就栽在这）。改完之后实测每帧：场景更新 0.02 ms + `mjr_render` 0.40 ms + HUD 0.20 ms，其余 ~15 ms 是在等 vsync——**已经是 vsync 限速，不需要再优化**；只有将来窗口/显示器更大（framebuffer 像素更多）时，才需要再把阴影贴图调小或关掉阴影。


**窗口里能做什么**（自建窗口，接口见 §2 与 `include/quadruped_ros2/viewer.hpp`）：

| 键 / 鼠标 | 作用 |
|---|---|
| 鼠标左键拖 / 右键拖（Shift 换轴）/ 中键 / 滚轮 | 转 / 平移 / 缩放（滚轮每格 5% 视野，官方是 2%） |
| **33 个显示开关快捷键**（`S` 阴影、`R` 反射、`K` 天空盒、`W` 线框、`C` 接触点、`F` 接触力、`J` 关节轴、`I` 惯性系、`M` 质心、`T` 半透明、`A` 自动连线、`,` …） | 与官方界面面板上的勾选框**同一套**（快捷键直接取自库里的 `mjVISSTRING` / `mjRNDSTRING`）；翻 bit 而已，画几何的是 libmujoco。全量表见 [`docs/learn/mujoco-viewer-keys.md`](../../docs/learn/mujoco-viewer-keys.md) |
| `F6` / `F7` / `Home` | frame 可视化循环 / label 可视化循环 / 回默认 iso 视角 |
| 画质参数 `viewer_msaa` / `viewer_render_scale` | 抗锯齿：窗口拿不到 MSAA（本机 Mesa 实测三条平台路径都是 0×）时自动走"离屏渲染 + 缩放 blit"；默认 `viewer_render_scale=2`（2× 超采样）把硬台阶像素减 **38%**、梯度 p99.9 减 **35%**（放大看部件边缘时最明显）。两者同开会黑屏，节点自动互斥。像素链路见 [`docs/learn/graphics-stack.md` §8](../../docs/learn/graphics-stack.md) |
| `Space` / `→` | 暂停·继续 / **暂停时单步前进** |
| `-` / `=` | 速度档位：`-` 更慢、`=` 更快，在官方的 **31 档**（100 → 80 → … → 0.1%）上走；只作用于窗口模式的墙钟推进 |
| `Ctrl+R` / `Ctrl+Q` / `Esc` | 复位（与手柄 X、`/sim_reset` 同一条路径）/ 退出 / 退出 |

HUD 右上角三行：`状态 + 实时倍率 + 当前速度档`、`flags: 当前开着的显示开关`、`键位提示`。HUD 两段文本**必须 ASCII**（MuJoCo 内置字体画不出中文，会变实心块——上次任务的实测教训，`viewer.hpp` 里加了自动告警）。**键位映射是数据不是 `switch`**：显示开关的键位从库表自动生成，另有 `viewer.hpp` 里的 `kRemap` 覆写表，改键 = 改一行（详见学习文档 §6）。

按键表与速度档有自检（不需要键盘，跑完即退）：

```bash
# 实测：33/33 个显示开关经按键分发确实翻动 ✓；速度档 100%/10%/1% → 0.988x / 0.100x / 0.010x 实时 ✓
```

没有了官方界面的"暂停/单步/扰动/热重载"面板（扰动、历史倒退、面板类都不建议移植，理由与代价见学习文档 §6）；要看接触点/受力就按 `C`/`F`，要改模型参数就用 `ros2 topic echo` 或临时改场景。

## 3 看门狗与复位

- **看门狗按"控制周期数"算，不按墙上时间**：默认 200 ms ÷ 2 ms = **100 步**。超过 100 步没收到 `/mit_command`（控制器挂了 / 还没起来），电机退回阻尼模式（`kp=0`、`kd=damp_kd`），并在日志里打一行。用步数而不是墙钟，是为了让 `realtime:=false` 的全速回归与实时跑行为一致（实机上驱动板也是数控制周期）。
- **复位**（手柄 X → `/sim_reset`）：回到起点姿态（`start:=rest` 就是场景里的趴卧 keyframe），控制器同时切回阻尼。**保留仿真时间轴**（`d->time` 不清零）：斜坡按 `sim_time` 算，清零会让"复位后再起身"先卡住——这个坑上一版也踩过，注释留在 [`../../@20260927_motor/cpp/essential_core/src/main.cpp`](../../@20260927_motor/cpp/essential_core/src/main.cpp)。
- **起点** `start:=raw|rest`：`raw` = 模型原姿态（**默认**，与上次任务一致：直腿、脚底刚好触地，零力矩下自己塌成趴卧，实测 0.5 s 内从 z=0.277 落到 0.145），`rest` = 场景 keyframe（趴卧）。keyframe 不会自动加载，见仓库 [`../../docs/learn/mujoco.md`](../../docs/learn/mujoco.md) §6.2。

### 3.0 两个"知道了就不影响用"的机制（2026-10-06 调查）

**`ControlStatus.tilt_deg` 目前没有任何控制用途**：它由控制器的 `OnImu()` 从 `/imu` 算出来，用途只有两个——① 控制器自己超过 `tilt_warn_deg`（默认 60°）时打一条 `WARN`（**这个判断只看传感器，不看这条消息**）；② 手柄节点收到 `/control_status` 后打印"倾角=…°"这一行状态。**站姿/起身/趴下等所有决策都只看按键**，没有任何下游消费 tilt_deg。所以这一路（msg 字段 + 回传 + 显示）属于"可删的展示信息"：如要删，改动是 `ControlStatus.msg` 去掉字段、控制器 `status.tilt_deg` 与 `joy_node.py` 那行打印各删一处；倾角告警本身**不受影响**（它算的是同一个本地量）。按你的安排，先提交当前状态再删。

**`/clock`（仿真时间）我们不用**：时序契约是**步数**（500 Hz 步进 + `/motor_state.sim_time` + 事件驱动的控制器 + 按控制周期数的看门狗），引入 `/clock`/`use_sim_time` 只会多一层耦合。机制、好处、坑与"真要用时怎么加（约 30 行）"记在 [`docs/learn/ros2-graph-and-clock.md`](../../docs/learn/ros2-graph-and-clock.md)；同一篇还解释了 `/parameter_events` 在 `rqt_graph` 里"有的节点只有去程"其实是图缓存假象（权威判断用 `ros2 topic info --verbose`）。

**窗口阴影锯齿**：MuJoCo 经典 GL 渲染器的阴影贴图是 `GL_NEAREST` + `COMPARE_R_TO_TEXTURE` 的**逐片元硬比较**（没有 PCF/双线性），阴影边界因而被量化到阴影贴图的**纹素格子**上，纹素 = `2·stat.extent·shadowclip/(shadowsize−2)`；而狗自身是按 framebuffer 分辨率 + 2× 超采样光栅化的。默认 `viewer_shadow_size=4096`（纹素 0.65 mm，比 1024 的边界偏移小 4.3×，只多 0.2~0.6 ms/帧），`viewer_shadow_clip`（默认 1.0）留作“用覆盖换分辨率”的现场旋钮；`light_bulbradius` 在经典渲染器里不被读取，做软阴影不要走那条路。机制、实测与取舍见 [`docs/learn/graphics-stack.md` §8.3](../../docs/learn/graphics-stack.md)。

### 3.1 复位"保留仿真时间轴"带来的一个坑（已修）

`/sim_reset` 与手柄 X **保留 `d->time`**（复位的是姿态与速度，不是时间轴，见 §3 的复位一节）。窗口模式下的物理步进是"补齐到当前墙钟"，如果这个"当前墙钟"写成"循环开始以来的秒数"，那么复位之后就会出现：`d->time` 仍是 25 s，而"已经过的时间"只有 0.02 s → `while (d->time < 已经过的时间)` **永远不成立 → 物理再也不步进**，画面看起来就是"狗卡在复位后的 raw 姿势不动，按什么键都没反应"（无窗口模式走的是 per-step deadline pacing，所以自检一直没暴露它）。

修法：窗口模式改用**一对锚点** `(wall_ref, sim_ref)` = "墙钟走到 `wall_ref` 时，仿真该到 `sim_ref`"，目标时刻 = `sim_ref + (now - wall_ref)`。复位后把两个锚点一起重设（`d->time` 保留，等价于"接着走"），暂停恢复时也把锚点一起前移（暂停的那段时间不算落后）；落后超过 `kMaxLagSeconds = 0.2 s` 就重新对齐而不是去追。

## 4 控制核心与上一版（`essential_core`）的移植对照

控制核心从 [`../../@20260927_motor/cpp/essential_core/src/state.h`](../../@20260927_motor/cpp/essential_core/src/state.h)（183 行）搬到 [`../ws/src/quadruped_ros2/include/quadruped_ros2/control.hpp`](../ws/src/quadruped_ros2/include/quadruped_ros2/control.hpp)，**控制律一个数没改**，只做下面几处为拆分所必需的改动：

| 项 | `essential_core` | 本任务 | 为什么 |
|---|---|---|---|
| 关节角来源 | 状态机持有 `mjModel`，启动时查 `actuator_trnid → jnt_qposadr/jnt_dofadr` | 随 `/motor_state` 消息来（**已是执行器顺序**），那张下标表整段删掉 | 控制器进程里没有 mjModel，也不该有 |
| 输出 | 直接写 `d->ctrl` | 填 5 个数组（`MitCommand`），力矩由电机侧算 | 与实机分工一致（见 §1 决策 1）；"两道限幅"里的第一道（控制程序层）随之取消，只留电机侧那一道（默认 ±20 N·m = 模型 `ctrlrange`） |
| 模式切换 | 终端按键 `tty.h`（S/D/R） | 手柄 `/joy` 的 A/B/X（只认按下沿，长按不重复触发） | 任务书第 3 项 |
| 复位 | `R` 键：`mj_resetData` + 保时间轴 | 手柄 X → `/sim_reset` 服务，仿真侧做同样的事 | 复位是**仿真侧**的动作，控制器只能请求 |
| 站姿 / 增益 / 斜坡 | 内联常量（`kStanceQ`、kp 80 / kd 3 / kd_damp 0.5 / ramp 1.0） | 逐位相同；增益与斜坡做成了 ROS 参数（默认值不变） | 为了能直接与上一版对照，也为了验收时能现场改参数 |

**对照实测**：上一版验证 F 的末态是"按下 0.2 s → z 0.3836 m、四足触地 4、末段 max|q̇| ≈ 0"（[`../../@20260927_motor/cpp/docs/essential.md`](../../@20260927_motor/cpp/docs/essential.md) §6）；本任务自检测到的稳态也是 **z = 0.3836 m、接触点 4、倾角 0.0°**，两次起身逐位一致。

## 5 实测：无头自检（一条命令跑完判定）

```bash
pixi run python @20261005_ros2/scripts/agent_scripts/check_headless.py
```

它起 `sim_node`（`viewer:=false`）+ `controller_node`，用 [`../scripts/agent_scripts/pub_joy_sequence.py`](../scripts/agent_scripts/pub_joy_sequence.py) 按 `1:A,6:B,8:X,9:A` 发 `/joy`，再读仿真节点的状态行判定（日志留在 `output/log/`，退出码 0 = 全过）：

| 检查项 | 实测 |
|---|---|
| MIT 指令一直跟得上 | 启动阶段阻尼 5 行，之后全部 `cmd=ok` |
| 看门狗没误触发 | 日志里没有「看门狗」 |
| 第一次按 A：站起来 | 峰值 z **0.3836 m**、接触点 **4**、倾角 **0.0°**、越到 0.37 m 用时约 **1.0–1.5 s**（斜坡本身 1 s，其余是状态行 0.5 s 采样间隔 + PD 收敛；多次复跑落在 1.0/1.5 s 两档） |
| 按 B：塌回趴卧 | z 回到 **0.1449 m**（场景 `rest` keyframe 的值） |
| 按 X 复位后再按 A | 又站住，末条 z **0.3836 m** |
| 两次站立一致（可复现） | 0.3836 m vs 0.3836 m |
| 实时率 | 0.999x / 1.000x / 1.000x |

原始状态行（`sim_node` 每 `status_period_s` 秒打一行，回归就 grep 它）：

```text
t=5.012 z=0.1467 tilt=0.3 ncon=4 cmd=ok      ← 按 A 之前，趴着
t=6.016 z=0.3778 tilt=0.1 ncon=4 cmd=ok      ← 1 s 斜坡把 q_des 推到站姿
t=7.020 z=0.3829 tilt=0.0 ncon=4 cmd=ok
t=11.024 z=0.1706 tilt=2.1 ncon=16 cmd=ok    ← 按 B，阻尼模式塌回去
t=11.524 z=0.1449 tilt=0.0 ncon=8 cmd=ok     ← 趴卧静止（8 个接触点，与任务 2 的判据一致）
复位：回到起点（rest），保留仿真时间轴 t=11.808 s
t=14.524 z=0.3340 tilt=0.8 ncon=4 cmd=ok     ← 复位后再按 A，又一次起身
```

## 6 ROS 2 命令速查（任务书要求"主动去熟悉"的那几条）

| 命令 | 看什么 |
|---|---|
| `ros2 node list` | `/sim_node`、`/controller_node`、`/joy_node` |
| `ros2 topic list -t` | 五条业务话题 + 类型；`/sim_reset` 是服务，不在这个话题列表里 |
| `ros2 topic echo /control_status` | 控制器视角：模式 / 斜坡进度 / 倾角 / 已发指令条数 |
| `ros2 topic echo /motor_state --once` | 12 个电机的 q/dq/ddq/tau/cur + sim_time |
| `ros2 topic echo /joy` | 8 轴 / 12 按钮（A/B/X 是 `buttons[0]/[1]/[2]`） |
| `ros2 topic hz /motor_state` | 500 Hz |
| `ros2 interface show quadruped_ros2/msg/MitCommand` | 自定义消息定义（含注释） |
| `ros2 service call /sim_reset std_srvs/srv/Empty {}` | 不开手柄也能复位 |
| `ros2 param get /controller_node kp` / `param set` | 站立模式增益；`kp` / `kd` / `kd_damp` / `ramp` / 三个按键索引都注册了参数回调，**改完下一帧就生效**（实测：`param set /controller_node ramp 8.0` 后按 A，z 从 0.1449 爬到 0.3836 用了 8 s，日志里也打「控制参数已更新…斜坡=8 s」） |

## 7 坑（都在这台机器上实测过）

1. **`ros2 topic list` 会用 daemon 的缓存**：两个节点明明在跑、`topic hz` 也有数，`ros2 topic list -t` 却只列出 `/parameter_events`、`/rosout`。加 `--no-daemon` 或先 `ros2 daemon stop` 就对了；daemon 会自己更新，只是不保证立刻。
2. **`ros2 topic echo` 的默认 QoS 是 `sensor_data`（best_effort）**，所以它能直接看 best_effort 的 `/motor_state`；反过来显式加 `--qos-reliability reliable` 会订不上（两边 QoS 不兼容时不报错，只是永远收不到）。这也是我们**不**把 500 Hz 话题做成 reliable 的原因：reliable 的流控会在订阅者变慢时把发布者顶住，而发布者是物理线程。
3. **`ros2 run` 是壳，节点是它的子进程**：只 kill 壳会留下孤儿节点继续发话题、继续写日志，下一轮自检就会读到上一轮的轨迹（我们第一版自检脚本就踩了这个，日志里出现了"上一轮还站着的狗"）。自检脚本现在把子进程`start_new_session=True` 起、按进程组 `killpg` 收，并在开头**先看有没有别人的节点在跑**（默认只提示、不动手，`--force` 才清）。**认节点要同时看 exe 和 cmdline**：C++ 节点看 `/proc/<pid>/exe`，而 `joy_node` 是 Python 脚本、`exe` 指向 `python3` ——只看 exe 会漏掉正在跑的 joy_node（实测漏掉的那个孤儿让 `ros2 node list` 里出现了两个 `/joy_node`），所以再加一条 `cmdline` 里含 `lib/quadruped_ros2/joy_node` 的判据。
4. **模型副本加了 IMU 站点与传感器，动力学一点没变**。`models/black_description.xml` 比 [`../../@20260927_motor/models/black_description.xml`](../../@20260927_motor/models/black_description.xml) 多一个 `<site name="imu">`（在 `imu_link` 上）与 `<sensor>` 三项。复现：同一场景、同一 keyframe 各跑 1000 步，`qpos`/`qvel` 最大差 **0.0**，`nsensordata` 从 0 变 10。
5. **`framequat` 传感器的 `objtype` 语义要当心**：写 `objtype="body"` 时输出与本模型的实际姿态**对不上**（实测 rest 姿态下输出 `[0.4984, 0.5019, -0.5009, 0.4989]`，而 `d->xquat[trunk]` 是 `[1, 0, 0.00001, 0.0015]`）；改成 `objtype="site"`（或 `xbody`）后与 `d->xquat` 逐位一致。本任务用的是 **site**：`<framequat name="imu_quat" objtype="site" objname="imu"/>`（`gyro`/`accelerometer` 本来就只能挂 site）。
6. **IMU 的坑只有两个数**：`gyro`/`accelerometer` 是**机体系**，静止时加速度计 z ≈ **+9.81 m/s²**、自由落体时 ≈ **0**（实测 `[-0.03, 0, 0.16]`）；`framequat` 是 `(w, x, y, z)`，ROS 的 `Imu` 是 `(x, y, z, w)`——顺序不能照抄。
7. **仿真节点在无显示服务时会自己降级**：没有 `DISPLAY` / `WAYLAND_DISPLAY` 时把 `viewer` 自动关掉并打一条警告，而不是让 GLFW 在 `glfwInit` 里把整个节点搞崩（这样"ssh 上去按脚本跑"也能用）。
8. **`launch_ros` 会把 `LaunchConfiguration` 的字符串按 YAML 规则转类型**，所以 `viewer:=false` 传进去是布尔 `false` 而不是字符串 `"false"`（参数声明成 `bool` 也能对上）；本任务的 launch 参数（bool/int/double）实测都能这样覆盖。
9. **"第一次按 A 没反应"是发现竞态，不是按键逻辑**。`/joy` 是 reliable + `keep_last(1)`：发布/订阅要先发现再通信，而控制器同时被 500 Hz 的 `/motor_state` 打着，实测发现能拖到几秒；发现完成前发的那些按键帧全丢（历史只有 1 条），于是脚本驱动的自检里第一次按 A 就没了（B 因为"本来就在阻尼"也没有日志，看起来像"只起来一次"）。实测对照：只起控制器 + 序列脚本（没有 500 Hz 负载）时 **3/3 都能收到**，带负载时第一次会丢。两条修法都进了代码：① [`../scripts/agent_scripts/pub_joy_sequence.py`](../scripts/agent_scripts/pub_joy_sequence.py) 先 `get_subscription_count()` 等到订阅者连上再开始计时；② 控制器忽略 `frame_id` 以 `joy_disconnected` 开头的帧（与主办者 gateway 的 `joy_require_connection_frame` 同一护栏）。修完 `check_headless.py` 连跑 3 次全过。
10. **`exit code -9` 不一定是节点崩了——先想想有没有别的工具在杀它**。2026-10-06 三节点联跑时 `sim_node`/`controller_node` 先后被 SIGKILL（launch 报 `exit code -9`、MuJoCo 窗口一起消失），内核日志里没有 OOM。对照时间戳才找到真凶：**自检脚本开头的"清孤儿"**——它按 `/proc/<pid>/exe` 的名字杀掉任何 `quadruped_ros2` 节点，于是把别人正在看的 demo 一起清掉了。教训：测试工具的清理要么只清自己起的进程组（`start_new_session=True` + `killpg`），要么**默认只提示、显式 `--force` 才动手**（现在是后者）。
11. **带类型的 ROS 参数不接受"整数写法"**：`-p status_period_s:=0` 会报 `parameter ... is of type {double}, setting it to {integer} is not allowed`，要写 `0.0`。这是 ROS 2 参数类型的正常行为，但第一次遇到容易以为是节点写错了。
12. **`rclpy.spin()` 收到 SIGINT 时会先 shutdown 一次 context**，收尾再调 `rclpy.shutdown()` 就抛 `RCLError: failed to shutdown: rcl_shutdown already called` —— 表现是 Ctrl-C 打一段 traceback、退出码 1（三节点联跑第一次就是这么结束的）。修法：捕获 `ExternalShutdownException`，收尾的 `destroy_node()` / `shutdown()` 都**先确认 `rclpy.ok()` 再做**（[`../ws/src/quadruped_ros2/scripts/joy_node.py`](../ws/src/quadruped_ros2/scripts/joy_node.py) 的 `main()`）。实测：发 SIGINT 后退出码 0、无 traceback。
13. **失败的自检最容易骗人：先怀疑测试工具，再怀疑被测代码**。本轮有两条教训都属这一类：① 三节点联跑时节点被 `-9` 杀掉，真凶是自检脚本开头的"清孤儿"（坑 10）；② "阴影锯齿调大贴图没用"的结论，真凶是当时那个整图梯度指标被 HUD 文字和画面别处的高对比边缘淹没（正确做法是先把阴影单独隔离出来量，见 [`docs/learn/graphics-stack.md` §8.3](../../docs/learn/graphics-stack.md)）。
