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
| 真手柄复验（验收项里"实体手柄"那一条） | ⏳ 未做：没有硬件；走的是与仿真手柄同一条路径——[`joystick.md`](joystick.md) §7，核对清单在 §8 |
| 仿真手柄 GUI 中文字号 | ⏳ 已按本机 Tk 换成 `song ti 12`（`gothic 9` → `song ti 12` 已实测解析），**字号观感待实机确认**——[`joystick.md`](joystick.md) §4 |
| `ControlStatus.tilt_deg` 回程字段 | ⏳ **已定：本轮提交后清理**（无任何控制下游，属可删的展示信息）——改动点见 [`ros2-nodes.md`](ros2-nodes.md) §3.0，排在 §3 下一步第 2 条 |
| 阴影锯齿（阴影边缘比狗的轮廓糙） | ✅ 已查明并已修（2026-10-07）：成因是 MuJoCo 经典 GL 的阴影**逐片元硬比较**（无 PCF），边界被量化到阴影贴图纹素上（2.61 mm）；默认 `viewer_shadow_size` 改为 **4096**（纹素 2.61 → 0.65 mm，边界偏移 0.728 → 0.171 px，只多 0.2~0.6 ms/帧）；新增 `viewer_shadow_clip`（默认 1.0，覆盖范围不变）。`light_bulbradius` 在经典渲染器里不被读取，做软阴影不要走那条路。证据与配方见 [`../../docs/learn/graphics-stack.md`](../../docs/learn/graphics-stack.md) §8.3，复现脚本 [`../scripts/agent_scripts/shadow_probe.py`](../scripts/agent_scripts/shadow_probe.py) |
| Agent 诊断逻辑归位 | ✅ 完成（2026-10-07）：任务 `scripts/` 下 4 个 agent 脚本移入 `scripts/agent_scripts/`（`setup_joy_devices.sh` 是人跑的一次性 sudo 工具，留在 `scripts/`）；主干里删掉调查残留（C++ 的 `kShotAfterFrames`、帧计时三件套、只写不读的 `cmd_wall_`/`Bank::cmd_`/`Binding::name`、死的 `RequestClose` 通路与无用 include；Python 的 `damping_rows`、空开关 `--keep-logs` 等）。判定与写法写进了 [`../../docs/conventions.md`](../../docs/conventions.md) §3 与 [`../../AGENTS.md`](../../AGENTS.md) |
| XML 注释里的 `--` | ✅ 已查明并已修：XML 规范禁止注释内出现双连字符；**MuJoCo（tinyxml2）能读**——实测 5 种写法（含 `--->`）都读得进去、`nq=19 ngeom=50` 不变，但 `xml.etree` 这类严格解析器一律报 `not well-formed`。本任务两个 xml 的 4 处已改成“不带双横线”的说法，改完严格解析与 MuJoCo 都通过；顺带修掉同处指向不存在脚本的过期注释。规则进 [`../../docs/conventions.md`](../../docs/conventions.md) §3；前两个任务里的同类写法按“不回改”处理 |
| `rqt_graph` 启动告警与按钮空白 | ✅ 已定位：① 告警是 `Could not find the Qt platform plugin "wayland" in ""`——rqt 用 Qt5，而环境里只装了 `qt6-wayland`；conda-forge 有 `qt-wayland 5.15.15`，**已加入 `pixi.toml`**（装后平台即 wayland、告警消失）。② 工具栏 6 个按钮**本来就是只画图标、不写字**（文字在 tooltip 里），但这个环境下所有主题图标都取不到 → 全空白。机制与两条本地兜底（把宿主的主题软链进环境）写在 [`../../docs/pitfalls/environment.md`](../../docs/pitfalls/environment.md)「2026-10-07 conda 里的 Qt 程序（rqt 等）」一节；`breeze-icons` / `gnome-icon-theme` 不在本仓库用的两个通道里，所以没进 `pixi.toml` |
| 自适应抗锯齿（随缩放改倍率） | ⏸ 论证可行、先不做（当前帧率还被合成器 present 限制）——同上 §8.2 |
| 虚拟手柄 GUI 缩放 | ⏸ 低优先级，两种改法各约 10~30 行——[`joystick.md`](joystick.md) §8 |

## 2 阻滞项

| 阻滞项 | 影响 | 现状 |
|---|---|---|
| 真手柄复验 | 验收项里"实体手柄"这一条只能用仿真手柄代替 | 没有硬件；插上后不需要改代码（[`joystick.md`](joystick.md) §7/§8） |
| 本机设备权限（一次性配置） | 没配置时仿真手柄建不出 uinput 设备、手柄节点读不了 `/dev/input` | 已解决：`sudo @20261005_ros2/scripts/setup_joy_devices.sh`；**换机器 / 重装系统后要重跑**（[`joystick.md`](joystick.md) §2） |

## 3 下一步

1. 真手柄到货后复验：与仿真手柄同一条路径、只差设备名。把设备名与 `/joy` 读数补进 [`joystick.md`](joystick.md) §7，重点核对**扳机量程、是否多一个 event 节点、`BTN_MODE` 是否存在**（清单见 §8）。
2. 清理 `ControlStatus.tilt_deg`（**已定**：本轮提交之后做；没有控制下游，改动是 msg 去掉字段 + 控制器 `status.tilt_deg` + `joy_node.py` 那行打印各删一处，倾角告警不受影响，见 [`ros2-nodes.md`](ros2-nodes.md) §3.0）。
3. 自适应抗锯齿（随缩放改倍率）：论证可行、暂不做（[`../../docs/learn/graphics-stack.md`](../../docs/learn/graphics-stack.md) §8.2）——注意它**解决不了**阴影量化（只抹软台阶边缘，台阶位置仍由纹素决定，见 §8.3）。
4. 可选：`/joint_states`（`sensor_msgs/JointState`）与 RViz 展示。`/clock` + `use_sim_time` 已论证**不用**（时序契约是步数，[`../../docs/learn/ros2-graph-and-clock.md`](../../docs/learn/ros2-graph-and-clock.md) §2）。
5. 可选：虚拟手柄 GUI 的缩放（[`joystick.md`](joystick.md) §8 给了两种改法）。

## 4 提交建议（分阶段；AI 助手不代为提交）

任务书四项与环境合并已经提交（最近五条：`54df70e` 目录骨架、`f222933` 两个节点、`6c91a02` launch、`757670b` 手柄链路与自检、`6df714b` 单环境 + 稳定通道）。**还没提交**的是这一轮"找 bug / 改代码 / 补文档"的改动，按主题分四次（每条的 `git add` 命令可直接粘贴）：

```bash
git status --short    # 先核对：ws/build|install|log、output/log|shadow 都已被 .gitignore 覆盖（这一轮补的
                      # output/shadow/），**不要** `git add -A`（会带上 .pixi/、__pycache__ 之类）

# ① 仿真侧：自建窗口（视口/画质参数、复位锚点修复）+ 阴影分辨率修复 + 电机非理想项
#    ⚠ 四项都动了 sim_node.cpp：想拆细就 `git add -p`，否则合成这一条
git add @20261005_ros2/ws/src/quadruped_ros2/include/quadruped_ros2/viewer.hpp \
        @20261005_ros2/ws/src/quadruped_ros2/include/quadruped_ros2/motor.hpp \
        @20261005_ros2/ws/src/quadruped_ros2/src/controller_node.cpp \
        @20261005_ros2/ws/src/quadruped_ros2/src/sim_node.cpp \
        @20261005_ros2/ws/src/quadruped_ros2/CMakeLists.txt \
        @20261005_ros2/ws/src/quadruped_ros2/launch/bringup.launch.py
git commit -m "feat(ros2): add the self-built viewer, shadow resolution fix and motor non-idealities"

# ② 模型与场景：XML 注释里的 -- 清掉、过期引用改对（MuJoCo 与严格解析器两边都过）
git add @20261005_ros2/models/black_description.xml @20261005_ros2/scenes/flat_scene.xml
git commit -m "fix(ros2): make the MJCF comments valid XML and drop stale references"

# ③ 脚本整理：agent 脚本收进 scripts/agent_scripts/ + 新增阴影诊断脚本；主干里的调查残留删掉
git add @20261005_ros2/scripts @20261005_ros2/ws/src/quadruped_ros2/scripts/joy_node.py \
        @20261005_ros2/.gitignore
git commit -m "refactor(ros2): group agent-run scripts and move diagnostics out of the main path"

# ④ 文档：任务 README 与 docs 五篇 + 仓库级约定/学习文档
git add @20261005_ros2/README.md @20261005_ros2/docs README.md AGENTS.md \
        docs/conventions.md docs/pitfalls/environment.md \
        docs/learn/ros2-params-and-launch.md docs/learn/ros2-graph-and-clock.md \
        docs/learn/mujoco-viewer-keys.md docs/learn/graphics-stack.md \
        docs/learn/cmake-intellisense.md docs/learn/mujoco.md .vscode/settings.json \
        @20261005_ros2_example/docs/pixi-ros2.md
git commit -m "docs(ros2): document the node interfaces, shadow pipeline and joystick chain"

# ⑤ 环境：为 rqt_graph 补 rqt-graph / Qt6 wayland / Qt5 wayland 三个依赖
git add pixi.toml pixi.lock
git commit -m "build(pixi): add rqt_graph and the Qt wayland platform plugins"
```
