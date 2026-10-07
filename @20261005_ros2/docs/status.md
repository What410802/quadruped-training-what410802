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

## 2 阻滞项

| 阻滞项 | 影响 | 现状 |
|---|---|---|
| 本机设备权限（一次性配置） | 没配置时仿真手柄建不出 uinput 设备、手柄节点读不了 `/dev/input` | 已解决：`sudo @20261005_ros2/scripts/setup_joy_devices.sh`；**换机器 / 重装系统后要重跑**（[`joystick.md`](joystick.md) §2） |

## 3 下一步

1. 自适应抗锯齿（随缩放改倍率）：论证可行、暂不做（[`../../docs/learn/graphics-stack.md`](../../docs/learn/graphics-stack.md) §8.2）——注意它**解决不了**阴影量化（只抹软台阶边缘，台阶位置仍由纹素决定，见 §8.3）。
2. 可选：`/joint_states`（`sensor_msgs/JointState`）与 RViz 展示。`/clock` + `use_sim_time` 已论证**不用**（时序契约是步数，[`../../docs/learn/ros2-graph-and-clock.md`](../../docs/learn/ros2-graph-and-clock.md) §2）。
3. 可选：虚拟手柄 GUI 的缩放（[`joystick.md`](joystick.md) §8 给了两种改法）。

## 4 提交建议（分阶段；AI 助手不代为提交）

已经提交的（任务书四项 + 环境合并 + 上一轮"找 bug / 改代码 / 补文档"）：

```text
54df70e 目录骨架            f222933 两个节点         6c91a02 launch
757670b 手柄链路与自检      6df714b 单环境 + 稳定通道
38bdd26 自建窗口 + 阴影修复 + 电机非理想项
1ef8128 MJCF 注释合法化 + 过期引用
b634bc4 agent 脚本归位 + 主干调查残留清理
3f4a29b 文档（节点接口 / 阴影链路 / 手柄）
543a43b rqt_graph + Qt wayland 平台插件
```

**还没提交**的是这三件事（去掉没有下游的 `tilt_deg`、把 IMU 用途写清、真手柄兼容性与复验），按主题分五次；每条的 `git add` 可直接粘贴：

```bash
git status --short    # 先核对：ws/build|install|log 与 output/log|shadow 都已被 .gitignore 覆盖，别 `git add -A`

# ① 手柄：第三方 HID 手柄的轴布局自适应（按 AbsInfo 判角色/量程）+ 名字片段与设备预筛加固
#    + 自检钉住自己造的 uinput 设备 + 真机探头
git add @20261005_ros2/ws/src/quadruped_ros2/scripts/joy_node.py \
        @20261005_ros2/ws/src/quadruped_ros2/launch/bringup.launch.py \
        @20261005_ros2/scripts/agent_scripts/check_joystick_device.py \
        @20261005_ros2/scripts/agent_scripts/probe_gamepad.py
git commit -m "fix(ros2): adapt the joy node to third-party HID gamepad layouts"

# ② 回程消息：去掉没有控制下游的 tilt_deg，并把 IMU 的用途说清（告警 + 可选打印）
#    注意 joy_node.py 在第 ① 条已经 add 过了，所以这里只需带上消息、控制器与文档
git add @20261005_ros2/ws/src/quadruped_ros2/msg/ControlStatus.msg \
        @20261005_ros2/ws/src/quadruped_ros2/src/controller_node.cpp \
        @20261005_ros2/README.md @20261005_ros2/docs/ros2-nodes.md
git commit -m "refactor(ros2): drop the unused tilt_deg field and make the IMU use explicit"

# ③ 文档：真手柄实测表与换手柄的核对法
git add @20261005_ros2/docs/joystick.md @20261005_ros2/docs/status.md
git commit -m "docs(ros2): record the real gamepad verification and third-party axis layout"

# ④ 学习文档：两个抗锯齿旋钮的分工、阴影贴图为什么越大越清晰、雾不是阴影
git add docs/learn/graphics-stack.md
git commit -m "docs: explain the AA knob duties and separate the shadow map from fog"

# ⑤ 环境：无（这一轮没动 pixi.toml）
```

`joy_node.py` 这一轮有两种改动（轴映射 + 去掉回程打印里的倾角）：整文件 `git add` 会一起提交，所以上面的顺序把两件事合进 ①，②里只留消息/控制器/文档——如果想拆细，就在 ① 之前先 `git add -p @20261005_ros2/ws/src/quadruped_ros2/scripts/joy_node.py` 把"回程打印"那段留给 ②。
