# 任务推进情况（做到哪、还差什么）

> 入口（怎么跑、文件地图）在 [`../README.md`](../README.md)；三节点的接口、实测与坑在 [`ros2-nodes.md`](ros2-nodes.md)；手柄链路在 [`joystick.md`](joystick.md)；环境与迁移在 [`environment.md`](environment.md)；电机模型在 [`motor-model.md`](motor-model.md)。约定来源：[`../../docs/conventions.md`](../../docs/conventions.md) §2、§7。

## 1 阶段状态

任务书四项（自定义消息 / 控制器 + 仿真两节点 / 手柄节点与消息互换 / launch 一键启动）都已实现并实测通过；**当前没有阻塞实现的问题**，只剩下面表里两类"要不要做"：⏳ 缺硬件或待人确认，⏸ 已论证、等拍板。每一步的取舍、数字与踩过的坑都在各自细节文档里，这里只留指针。

| 阶段 | 状态 |
|---|---|
| ① 自定义消息 `MitCommand` / `MotorState` / `ControlStatus` | ✅ 完成——[`ros2-nodes.md`](ros2-nodes.md) §1 |
| ② 控制器节点（C++：两状态机 + MIT 五参数） | ✅ 完成，控制核心逐位移植自 `@20260927_motor/cpp/essential_core/src/state.h`——[`ros2-nodes.md`](ros2-nodes.md) §3.1 |
| ② 仿真节点（C++：自建 MuJoCo 窗口 + 电机模型 + IMU + 看门狗） | ✅ 完成——[`ros2-nodes.md`](ros2-nodes.md) §2/§3、[`motor-model.md`](motor-model.md) |
| ② 闭环实测：末态 z 0.3836 m，与上一版 `essential_core` 一致 | ✅ 完成——[`ros2-nodes.md`](ros2-nodes.md) §3.1/§5 |
| ③ 手柄节点（evdev → `/joy`）+ 控制器回程 `/control_status` | ✅ 完成——[`joystick.md`](joystick.md) §3 |
| ③ 仿真手柄（uinput）+ 一次性权限脚本 | ✅ 完成——[`joystick.md`](joystick.md) §1/§2 |
| ③ 设备层端到端（uinput → `joy_node` → `/joy` → 起身/趴下/再起身） | ✅ 完成——[`joystick.md`](joystick.md) §6 |
| ③ 无头自检 `check_headless.py`（不接手柄，退出码 0/1） | ✅ 完成——[`ros2-nodes.md`](ros2-nodes.md) §5 |
| ④ launch 一键起三节点，参数可命令行覆盖 | ✅ 完成——参数全表在 [`ros2-nodes.md`](ros2-nodes.md) §1.2 |
| 参数在线修改（`kp` / `kd` / `kd_damp` / `ramp` / 三个按键索引） | ✅ 完成——[`ros2-nodes.md`](ros2-nodes.md) §6 |
| 电机非理想项（死区 / 指令延迟 / 噪声 / 噪声种子，默认全关） | ✅ 完成，做成仿真侧 ROS 参数，控制器一行不用改——[`motor-model.md`](motor-model.md) §3~§5 |
| `ddq` / `cur` 口径（培训方补充的"读不到就置 0"） | ✅ 已定口径：`ddq` 读真值、`cur` 恒 0 = 未测量——[`ros2-nodes.md`](ros2-nodes.md) §1/§1.1 |
| 环境：单环境 + `robostack-humble` 稳定通道 + 构建/激活自动发现 | ✅ 完成——[`environment.md`](environment.md) §1/§4 |
| 视口：自建窗口（阴影 / MSAA / 超采样 / 阴影正交盒参数）、复位后物理不步进的坑 | ✅ 完成——[`ros2-nodes.md`](ros2-nodes.md) §2/§2.1/§3.1 |
| 真手柄复验（验收项里"实体手柄"那一条） | ✅ **完成（2026-10-07，Zikway HID gamepad / USB）**：设备层 → `joy_node` → 控制器 → 仿真四层逐项过；`/joy` 两路摇杆与扳机到 **±1.000**、十字键 ±1，按 **A→B→X→A** 两次起身、峰值 **z = 0.3836 m**、四足触地、倾角 0.0°。实测表与换手柄的核对法见 [`joystick.md`](joystick.md) §7/§8 |
| 真手柄兼容性（第三方 HID 手柄的布局差异） | ✅ 已改（2026-10-07）：轴的角色（摇杆/扳机）与量程改成**连接时读设备自己的 `absinfo`**（不再写死 `STICK_MAX`），名字片段补 `gamepad,joystick`，预筛改成"至少一个手柄类轴"；仿真手柄（xpad 布局）回归 8/8 全过、真手柄端到端全过。新增真机探头 [`../scripts/agent_scripts/probe_gamepad.py`](../scripts/agent_scripts/probe_gamepad.py)——[`joystick.md`](joystick.md) §8 |
| 仿真手柄 GUI 中文字号 | ⏳ 已按本机 Tk 换成 `song ti 12`（`gothic 9` → `song ti 12` 已实测解析），**字号观感待实机确认**——[`joystick.md`](joystick.md) §4 |
| IMU 的用途明确化 | ✅ 完成（2026-10-07）：`/imu` 是**任务书第 2 项要求的接口**（仿真 → 控制器的反馈里要带 IMU），控制律不用它；控制器 `OnImu()` 只保留两件不影响控制输出的事——`tilt_warn_deg` 安全告警（默认 60°，设 0 关闭）与**可选的**低频打印 `imu_log_period_s`（默认 0 = 静默；验收现场 `-p imu_log_period_s:=1.0` 就能看到「IMU 回传：倾角=…」每秒一行）。见 [`ros2-nodes.md`](ros2-nodes.md) §1.3 |
| `ControlStatus.tilt_deg` 回程字段 | ✅ 已删（2026-10-07）：它没有任何控制下游（决策只看按键），改动是 msg 去字段 + 控制器 `status.tilt_deg` + `joy_node.py` 那行打印各删一处；`tilt_warn_deg` 告警**不受影响**（控制器仍从 `/imu` 本地算同一个量）。`/control_status` 现在只剩 模式 / 斜坡进度 / 指令条数——[`ros2-nodes.md`](ros2-nodes.md) §1.3 |
| 阴影锯齿（阴影边缘比狗的轮廓糙） | ✅ 已查明并已修（2026-10-07）：成因是 MuJoCo 经典 GL 的阴影**逐片元硬比较**（无 PCF），边界被量化到阴影贴图纹素上（2.61 mm）；默认 `viewer_shadow_size` 改为 **4096**（纹素 2.61 → 0.65 mm，边界偏移 0.728 → 0.171 px，只多 0.2~0.6 ms/帧）；新增 `viewer_shadow_clip`（默认 1.0，覆盖范围不变）。`light_bulbradius` 在经典渲染器里不被读取，做软阴影不要走那条路。证据与配方见 [`../../docs/learn/graphics-stack.md`](../../docs/learn/graphics-stack.md) §8.3，复现脚本 [`../scripts/agent_scripts/shadow_probe.py`](../scripts/agent_scripts/shadow_probe.py) |
| Agent 诊断逻辑归位 | ✅ 完成（2026-10-07）：任务 `scripts/` 下 4 个 agent 脚本移入 `scripts/agent_scripts/`（`setup_joy_devices.sh` 是人跑的一次性 sudo 工具，留在 `scripts/`）；主干里删掉调查残留（C++ 的 `kShotAfterFrames`、帧计时三件套、只写不读的 `cmd_wall_`/`Bank::cmd_`/`Binding::name`、死的 `RequestClose` 通路与无用 include；Python 的 `damping_rows`、空开关 `--keep-logs` 等）。判定与写法写进了 [`../../docs/conventions.md`](../../docs/conventions.md) §3 与 [`../../AGENTS.md`](../../AGENTS.md) |
| XML 注释里的 `--` | ✅ 已查明并已修：XML 规范禁止注释内出现双连字符；**MuJoCo（tinyxml2）能读**——实测 5 种写法（含 `--->`）都读得进去、`nq=19 ngeom=50` 不变，但 `xml.etree` 这类严格解析器一律报 `not well-formed`。本任务两个 xml 的 4 处已改成“不带双横线”的说法，改完严格解析与 MuJoCo 都通过；顺带修掉同处指向不存在脚本的过期注释。规则进 [`../../docs/conventions.md`](../../docs/conventions.md) §3；前两个任务里的同类写法按“不回改”处理 |
| `rqt_graph` 启动告警与按钮空白 | ✅ 已定位：① 告警是 `Could not find the Qt platform plugin "wayland" in ""`——rqt 用 Qt5，而环境里只装了 `qt6-wayland`；conda-forge 有 `qt-wayland 5.15.15`，**已加入 `pixi.toml`**（装后平台即 wayland、告警消失）。② 工具栏 6 个按钮**本来就是只画图标、不写字**（文字在 tooltip 里），但这个环境下所有主题图标都取不到 → 全空白。机制与两条本地兜底（把宿主的主题软链进环境）写在 [`../../docs/pitfalls/environment.md`](../../docs/pitfalls/environment.md)「2026-10-07 conda 里的 Qt 程序（rqt 等）」一节；`breeze-icons` / `gnome-icon-theme` 不在本仓库用的两个通道里，所以没进 `pixi.toml` |
| 自适应抗锯齿（随缩放改倍率） | ⏸ 论证可行、先不做（当前帧率还被合成器 present 限制）——同上 §8.2 |
| 虚拟手柄 GUI 缩放 | ⏸ 低优先级，两种改法各约 10~30 行——[`joystick.md`](joystick.md) §8 |
| `/joy` 正负号约定 + 仿真手柄十字键竖轴（大作业时发现） | ✅ 已改（2026-10-08）：`joy_node` 把摇杆四个轴与十字键竖轴换成主办者 `gamepads.yaml` 的约定（摇杆上 / 左为 +、十字键上 / 右为 +）；仿真手柄的十字键竖轴原先与实体手柄相反（发"上 = +1"），改成内核的"上 = −1"。`check_joystick_device.py` 加了 5 项正负号检查，13 项全过；`check_headless.py` 照旧全过（控制器只读按键，不受影响）——[`joystick.md`](joystick.md) §3 |
| 实体手柄的正负号复验 | ⏳ 待人工：插 Zikway，`ros2 topic echo /joy` 看左摇杆推上时 `axes[1]`、十字键上时 `axes[7]` 是否为 +1——[`joystick.md`](joystick.md) §7 |
| 编辑器标红（`motor.hpp` 等头文件） | ✅ 已修（2026-10-08）：换环境里的 clangd 23，本包加 `.clangd` 补头文件的 `-I` 与 `-std=c++17`；本包 6 个 C/C++ 文件 0 错——[`../../docs/pitfalls/environment.md`](../../docs/pitfalls/environment.md)「系统的 clangd 14 读不了 gcc 15 的头」 |

## 2 阻滞项

| 阻滞项 | 影响 | 现状 |
|---|---|---|
| 本机设备权限（一次性配置） | 没配置时仿真手柄建不出 uinput 设备、手柄节点读不了 `/dev/input` | 已解决：`sudo @20261005_ros2/scripts/setup_joy_devices.sh`；**换机器 / 重装系统后要重跑**（[`joystick.md`](joystick.md) §2） |

## 3 下一步

1. 自适应抗锯齿（随缩放改倍率）：论证可行、暂不做（[`../../docs/learn/graphics-stack.md`](../../docs/learn/graphics-stack.md) §8.2）——注意它**解决不了**阴影量化（只抹软台阶边缘，台阶位置仍由纹素决定，见 §8.3）。
2. 可选：`/joint_states`（`sensor_msgs/JointState`）与 RViz 展示。`/clock` + `use_sim_time` 已论证**不用**（时序契约是步数，[`../../docs/learn/ros2-graph-and-clock.md`](../../docs/learn/ros2-graph-and-clock.md) §2）。
3. 可选：虚拟手柄 GUI 的缩放（[`joystick.md`](joystick.md) §8 给了两种改法）。
