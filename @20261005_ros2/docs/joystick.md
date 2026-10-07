# 手柄链路：设备、权限、映射与三级测试路线

> 入口（怎么编译、怎么跑）见 [`../README.md`](../README.md)；节点与消息接口见 [`ros2-nodes.md`](ros2-nodes.md)。本文只写**手柄这一条链路**：谁扮演什么角色、设备与权限、映射表、怎么在没有实体手柄时测、以及与主办者仓库那套的对照。

## 1 三个角色

| 角色 | 是什么 | 在哪 |
|---|---|---|
| **实体手柄** | xbox 协议的游戏手柄，插上就是 `/dev/input/eventN` | 硬件 |
| **仿真手柄** | 鼠标操作的 GUI，通过 `/dev/uinput` 造一个**内核输入设备**，名字/VID:PID/轴序/按钮序都对齐 xpad 下的 Xbox 360 手柄 | [`../sim_joy/xbox_sim_joy.py`](../sim_joy/xbox_sim_joy.py)（**外部独立进程，不是 ROS 节点**） |
| **手柄节点** | ROS 2 节点：读那个设备 → 发 `sensor_msgs/Joy`；同时订阅控制器的回程状态 | [`../ws/src/quadruped_ros2/scripts/joy_node.py`](../ws/src/quadruped_ros2/scripts/joy_node.py) |

仿真手柄**刻意不纳入 ROS 2 管理**：它只往内核里造设备，和真手柄走完全同一条路（`/dev/input` → `joy_node` → `/joy`）。于是"仿真手柄能跑通"就意味着"真手柄插上就能用"——除了设备名字不同（`joy_node` 按名字片段自动认，见 §3），代码一行都不用改。反之，若让仿真手柄直接发 `/joy`，就绕过了要测的那一层。

```text
实体手柄 ─┐
          ├─► /dev/input/eventN ─► joy_node ─► /joy ─► controller_node ─► /mit_command ─► sim_node
仿真手柄 ─┘   (uinput 造的真设备)   (Python)            (A 站立 / B 阻尼 / X 复位)
```

## 2 设备与权限（本机实测，一次性配置）

实测（2026-10-05，本机 Ubuntu 22.04）：

| 对象 | 权限 | 结果 |
|---|---|---|
| `/dev/uinput` | `crw------- root root`（0600） | `bis` 写不了 → 仿真手柄建不出设备 |
| `/dev/input/event0` | `crw-rw---- root input`（0660，**无 ACL**） | `bis` `open()` 报 `Permission denied` |
| `bis` 的组 | `adm cdrom sudo dip plugdev lpadmin lxd sambashare docker fuse` | **不在 `input` 组** |
| 会话 | `loginctl show-session 3` → `Active=yes`、`Seat=seat0` | 有活动会话，可用 systemd 的 uaccess 机制 |
| 本机 udev 规则 | `/usr/lib/udev/rules.d/70-joystick.rules` 只 import hwdb，**没有 uaccess** | 所以**真手柄插上也读不了**（这条不是仿真手柄特有的问题） |

一次性配置（本仓库唯一的特权操作，只写一条 udev 规则）：

```bash
sudo @20261005_ros2/scripts/setup_joy_devices.sh          # 需要 sudo 密码
```

它做四件事：`modprobe uinput` → 写 `/etc/udev/rules.d/60-quadruped-joy.rules`（给 `/dev/uinput` 与"手柄类"输入设备打 `uaccess` 标签）→ `udevadm control --reload-rules` + `trigger` → 顺手 `setfacl` 给 `/dev/uinput` 补一次权限（保证"现在就能用"）。

**为什么用 uaccess 而不是 `usermod -aG input`**：uaccess 是 logind 给"当前活动会话的用户"发一个设备 ACL，**立刻生效、不需要重新登录**；加组要重新登录（而且要连 `/dev/uinput` 一起改组权限）。撤销：删掉那个规则文件 + `udevadm control --reload-rules`。

没跑这条脚本时的表现（都是明确报错、不会静默失败；两条都实测过）：

- `xbox_sim_joy.py`：`[xbox_sim_joy] 造不出 uinput 设备："/dev/uinput" cannot be opened for writing`，紧跟上面那条 sudo 命令（evdev 这里抛的是 `UInputError` 而不是 `PermissionError`，所以捕获放宽了）；
- `joy_node`：`N 个输入设备打不开（没有权限）：…`，并继续以 `joy_disconnected` 状态每秒重试（此时它照发全 0 的 `/joy`，控制器收不到按键）。注意 `evdev.list_devices()` 会先按"可读可写"过滤，没权限时直接返回空表——那样只能报"没找到手柄"，看不出是权限问题，所以手柄节点自己 `glob` `/dev/input/event*`。
- **这条提示曾经误报过**：键盘 / 鼠标也挂在 `/dev/input/event*` 上、同样只有 `root:input` 可读，早期版本挨个去开，于是在"权限已配好、手柄也认到了"的情况下，开头仍先打一条 `没有权限打开 /dev/input/event0`（实测：2026-10-06 三节点联跑，用户以为 `sudo` 脚本没生效，其实紧跟其后就是"手柄已连接"）。现在先按 sysfs 的 `/sys/class/input/eventN/device/capabilities/abs` 判断"有没有绝对轴"（**不需要权限**）：键盘鼠标直接跳过，只有"确实像手柄却打不开"才提示权限。顺带一个坑：内核打印的能力位是**多字**位图（空格分隔、高位字在前），算具体位很容易写错（第一版按单整数读，对刚建的 uinput 手柄返回了 `None`）——所以只看"是不是全 0"，不算位序。

## 3 映射：8 轴 / 12 按钮

输出长度与顺序**对齐主办者仓库**的 `configs/input/gamepads.yaml`（只读材料 `ReadOnly.d/quadruped_control/` 下）里的 `xbox` profile，方便两边对照：

| 输出 | 来源（evdev 码，xpad 顺序） | 归一化 |
|---|---|---|
| `axes[0]` `axes[1]` | `ABS_X` `ABS_Y`（左摇杆） | ÷32767，死区 0.08（参数 `deadband`） |
| `axes[2]` `axes[5]` | `ABS_Z` `ABS_RZ`（LT / RT） | 0..255 → −1..1 |
| `axes[3]` `axes[4]` | `ABS_RX` `ABS_RY`（右摇杆） | ÷32767，死区 0.08 |
| `axes[6]` `axes[7]` | `ABS_HAT0X` `ABS_HAT0Y`（DPad） | 本来就是 −1/0/1 |
| `buttons[0..10]` | `BTN_A` `BTN_B` `BTN_X` `BTN_Y` `BTN_TL` `BTN_TR` `BTN_SELECT` `BTN_START` `BTN_MODE` `BTN_THUMBL` `BTN_THUMBR` | 0/1 |
| `buttons[11]` | —（没有对应键） | 恒 0，只为"长度固定" |

按键语义由**控制器节点**决定（不是手柄节点）：`button_stand=0`（A）站立、`button_damp=1`（B）阻尼、`button_reset=2`（X）复位，都只认**按下沿**（长按不重复触发，与上一版键盘的 S/D/R 一致）。回程：手柄节点订阅 `/control_status` 并打印"模式 / 斜坡进度 / 倾角 / 已发指令条数"——这就是任务书"手柄节点需要和控制器节点互换消息"的返程那一条。

还有一条护栏：控制器**忽略 `frame_id` 以 `joy_disconnected` 开头的帧**（手柄没找到设备时手柄节点发的就是它，"全 0"不会被当成"松手"或"按了什么"）。这与主办者仓库 gateway 的 `joy_require_connection_frame` 是同一个设计，理由也一样：动作要建立在"输入源确实是活的"之上。

**设备认领规则**（`joy_node` 的参数）：`device` 给了就只认这个路径；没给就扫 `/dev/input/event*`，要求"有 `BTN_A` + 左摇杆两个轴"，并且名字里含 `name` 参数里的某个片段（默认 `xbox,x-box,xinput,gamepad,joystick`，`name:=` 空表示任何手柄都收）。名字片段有两种写法是必须的：内核 xpad 驱动给 360 手柄起的名是 `Microsoft X-Box 360 pad`，大写后是 **X-BOX** 而不是 XBOX——只匹配 `xbox` 会漏掉实体手柄（调研笔记 `xbox_sim_joy.py` 里记过这个坑，本机只读材料）。**2026-10-07 真机复验**又补了一类：第三方 HID 手柄常常只报 `… gamepad` / `… joystick`（实测那台是 `Zikway HID gamepad`），所以默认片段加了 `gamepad,joystick`。

### 3.1 为什么 `/joy` 按频率发（快照），而不是事件触发

实现是这样的（[`../ws/src/quadruped_ros2/scripts/joy_node.py`](../ws/src/quadruped_ros2/scripts/joy_node.py) 的 `poll()`）：每 10 ms（`rate_hz=100`）先用 `select` + `read` 把设备里**积压的 evdev 事件全部读出来**更新 axes/buttons，然后**无条件发一帧完整快照**。也就是"事件读取 + 定频快照发布"。

为什么订阅侧更想要快照而不是事件：

1. **`sensor_msgs/Joy` 本来就是快照语义**：只有 `axes[]`/`buttons[]` 两个数组，没有"哪个键变了、什么时候变的"这种字段；同类话题（`/joint_states`、`/imu`）也都是定频快照。
2. **"静止"必须与"失联"可区分**：只发变化帧的话，手柄不动时话题会彻底安静，订阅方无法判断是"手柄静止"还是"手柄（或节点）死了"。主办者仓库 gateway 的 `joy_timeout_ns = 250 ms`（超时即认为失联）成立的前提就是发布方持续发帧。
3. **延迟有上界、诊断直观**：最坏 10 ms；`ros2 topic hz /joy` 直接反映手柄节点是否活着——和 `/motor_state` 的 500 Hz 用同一套观测手段。
4. **丢帧无害**：快照是幂等的（下一帧 10 ms 后又带一整套状态），不需要为"逐事件可靠投递"设计队列/重传；控制器只认按下沿，按 A 的 0.2 s 里能收到 ~20 帧，丢一两帧不影响。

代价是静止时也在发，但量很小：Joy 约 100 B/帧 × 100 Hz ≈ **10 KB/s**，相对 `/motor_state`（约 500 B × 500 Hz ≈ 250 KB/s）可忽略。

对照**官方 `joy` 包**：它默认是**事件驱动**（`autorepeat_rate` 默认 0 = 只在事件时发），需要"保底同步"时把 `autorepeat_rate` 设成 10~20 Hz——即"事件触发 + 定频保底"。那套更省流量，但要在订阅侧接受"静止时可能长时间没有帧"；我们选了更简单、更确定的定频快照。要改成混合也容易：在 `poll()` 里加一个"值变了才发、否则每 100 ms 保底发一帧"的条件即可。

## 4 三级测试路线（实体稀缺时的替代方案）

| 级别 | 测什么 | 命令 | 需要权限？ | 实测 |
|---|---|---|---|---|
| ① 链路自检 | "手柄 → 控制器 → 仿真"整条链路**不需要手柄**也能跑：脚本按 `1:A,6:B,8:X,9:A` 直接发 `/joy` | `pixi run python @20261005_ros2/scripts/agent_scripts/check_headless.py` | 否 | ✅ 全过（[`ros2-nodes.md`](ros2-nodes.md) §5） |
| ② 设备层端到端 | **真造一个内核输入设备**（uinput）→ `joy_node` 从 `/dev/input` 认领 → `/joy` 上看到 A/B/X → 狗起身/趴下/再起身 | `pixi run python @20261005_ros2/scripts/agent_scripts/check_joystick_device.py` | **要**（§2） | ✅ 全过，见 §6 |
| ③ 手动操作仿真手柄 | 鼠标点 GUI，看狗听不听使唤（GUI 中文字体已从 Tk 默认的日文 `gothic` 9 号换成 `song ti` 12 号：本机 Tk 是非 Xft 构建，fontconfig 里的 `Noto Sans CJK SC` 它看不见，核心字族里只有 `song ti`/`fangsong ti` 是中文正体） | 终端 A：`pixi run python @20261005_ros2/sim_joy/xbox_sim_joy.py`；终端 B：`pixi run ros2 launch quadruped_ros2 bringup.launch.py` | **要** | ✅ GUI 能起（窗口在桌面出现），按键路径与 ② 是同一条 |
| ④ 实体手柄复验 | 同一套代码换真设备 | 插手柄 → 同 ③ 的终端 B（`joy_node` 按名字自动认） | **要**（同一条规则） | ⏳ 没实体手柄，未跑 |

①的脚本 [`../scripts/agent_scripts/pub_joy_sequence.py`](../scripts/agent_scripts/pub_joy_sequence.py) 是**测试替身**：它不碰设备，直接把按键序打进 `/joy`。这不是偷懒——主办者仓库也是这么做的（见 §5）。②的脚本 [`../scripts/agent_scripts/check_joystick_device.py`](../scripts/agent_scripts/check_joystick_device.py) 直接 `import` 仿真手柄的 uinput 部分并程序化按按钮，所以不必有人守着鼠标点。

## 5 与主办者（n-w-wolf）仓库的对照

`ReadOnly.d` 里与本任务相关的是 `quadruped_control`（`rl_sar-black-W` 只有 thirdparty 的宇树手柄头文件）。逐项对照：

| 主办者仓库 | 做什么 | 本任务 |
|---|---|---|
| `adapters/ros2/quadruped_gateway/scripts/controller_input.py` | **pygame/SDL** 读手柄，按 `configs/input/gamepads.yaml` 的 profile（按名字猜型号）映射成**固定 8 轴 / 12 按钮**，100 Hz 发 `sensor_msgs/Joy`；`frame_id` 写成 `joy_connected:<profile>` / `joy_disconnected`；没设备时发全 0 | 同样是"固定 8/12 + 死区 0.08 + `joy_connected:/joy_disconnected`"。差别：我们**直接读 evdev**（不引 pygame/SDL），因为仿真手柄本来就要用 evdev 造设备、且少一层 SDL 自己重排轴的风险；profile 机制简化成一个 `name` 参数（本任务只要求 xbox 协议） |
| 同上：`configs/input/gamepads.yaml` | 各型号手柄的轴/按钮索引表 | 输出顺序与它的 `xbox` profile 一致（§3），但没做多 profile |
| `adapters/ros2/quadruped_gateway/src/ros2_gateway.cpp` | 订阅 `/joy`（best effort、depth 1）与 `/cmd_vel`，`joy_timeout_ns` 250 ms，要求"连接确认帧" | 同样 best_effort/depth 1、同样有超时（我们的看门狗 200 ms，但在**仿真侧**按控制周期数算）；"连接确认帧"这一条我们也抄了：控制器忽略 `frame_id` 为 `joy_disconnected` 的帧 |
| `scripts/test/ros2_headless_test.py` | 无头测试：进程组起停 + **直接 `publish_joy(buttons=…)`** 造按键序列，验证整条链路 | [`../scripts/agent_scripts/pub_joy_sequence.py`](../scripts/agent_scripts/pub_joy_sequence.py) 就是这一招的固化版（支持 `--sequence "1:A,6:B"`） |
| `apps/replay/main.cpp` | **回放状态日志**（CSV）驱动运动运行时，输出诊断对比 | 不是一回事（那是"回放机器人状态"，不是"回放输入序列"），本任务没做 |

**调研结论（回答"要不要给仿真手柄加'只发预定序列'的功能"）**：主办者仓库的**手柄节点本身没有**"读预录制/预编写操作序列"的功能；"按序列驱动"出现在**测试脚本**里（`ros2_headless_test.py`）。所以按约定：**仿真手柄只做设备主路径**（鼠标 → uinput），序列驱动单独做成测试脚本 `pub_joy_sequence.py`——两者分工与主办者仓库一致。

## 6 端到端实测（2026-10-06，跑过 `setup_joy_devices.sh` 之后）

```bash
pixi run python @20261005_ros2/scripts/agent_scripts/check_joystick_device.py
```

它起 `sim_node`（无窗口）+ `controller_node` + `joy_node`，再造一个 uinput 手柄并程序化按 `A(1s) → B(7s) → X(10s) → A(11s)`，日志在 `output/log/check-joy-*.log`：

| 检查项 | 实测 |
|---|---|
| 权限 | 配置前 `/dev/uinput` 是 `root:root 0600`、`bis` 写不了；配置后带 ACL `user:bis:rw-`，`test -w` 通过 |
| 仿真手柄造出的设备 | `Xbox 360 Wireless Controller (Sim)` → **`/dev/input/event14`**（uinput 退出后设备自动消失） |
| `joy_node` 认领 | `手柄已连接：Xbox 360 Wireless Controller (Sim)（/dev/input/event14，py-evdev-uinput）` |
| `/joy` 内容 | 885 帧，`frame_id = joy_connected:Xbox 360 Wireless Controller (Sim)`；`buttons` 上确实看到 **0(A) / 1(B) / 2(X)** 各按下过 |
| 按键 → 动作 | 仿真日志里 **2 次起身 + 1 次塌下**（A 站起、B 趴下、X 复位、再 A 站起） |
| 起身质量 | 峰值 **z = 0.3836 m**、四足触地（ncon=4）、倾角 **0.0°**；两次站立稳态一致（0.3836 vs 0.3836 m） |
| 看门狗 | 没触发 |

也就是说：**设备层（uinput → evdev → `/joy`）到控制层（按键 → 状态机 → 狗）整条链路都通了**，与"脚本直接发 `/joy`"那条自检得到的数字完全一致。唯一没跑的是真手柄（没有硬件），而它与仿真手柄走的是同一条路，只差设备名。

## 7 未验证 / 下一步

- **④ 实体手柄复验**：✅ **已做（2026-10-07，Zikway HID gamepad，USB）**——设备层、`joy_node`、控制器、仿真四层逐项实测通过：
  * 认领：名字是 `Zikway HID gamepad`（不含 `xbox`），加 `gamepad` 片段后**自动认领**；也可以 `-p device:=/dev/input/event15` 钉住（两者都实测过）；
  * 摇杆：`/joy` 的 `axes[0]/[1]`（左）与 `axes[3]/[4]`（右）都到 **±1.000**；
  * 扳机：LT/RT → `axes[2]/[5]` 到 **±1.000**（这台同时上报 `BTN_TL2/TR2` 数字键）；
  * 十字键：`axes[6]/[7]` 到 **±1**（`ABS_HAT0X/Y`）；
  * 按键：**A→B→X→A** 依次被控制器认到（日志四条"手柄 A/B/X → …"），狗**两次起身**、峰值 **z = 0.3836 m**、四足触地、倾角 0.0°——与仿真手柄、与上一版数字完全一致。
  复现用的探头是 [`../scripts/agent_scripts/probe_gamepad.py`](../scripts/agent_scripts/probe_gamepad.py)（设备层，`--watch` 引导采集）+ `--ros-args -p device:=` 起 `joy_node`，整套核对表见 §8。
- **非 xbox 布局的手柄**：已有一台第三方 HID 手柄实测通过（轴量程与槽位由 `absinfo` 自适应，不再写死量程）；再换别的牌子，先跑 `probe_gamepad.py` 看它的轴/键码位，必要时只改 `name` 片段或 `-p device:=`，一般不必改代码。
- **未做**：震动/LED 回馈（`sensor_msgs/JoyFeedback`）、`/joy` 的轴语义（当前控制器只用按钮；左右摇杆已经在 `/joy` 里，将来做"走两步"时直接用 `axes[1]`）。

## 8 虚拟手柄 vs 真实 Xbox 手柄：接口对照与真机核对清单

**虚拟手柄是本任务自己写的**（`sim_joy/xbox_sim_joy.py`，Tk 图形界面 + `evdev.UInput`，391 行），没有套用现成方案；思路是"**造一个内核级的真手柄**"，所以对 `joy_node` 而言它与实体手柄没有区别（SDL / pygame / `jstest` 同样分不出来）。界面的窗口缩放不友好（画布坐标是建窗时算的），优先级低，两种改法：把画布改成 `<Configure>` 回调里按当前尺寸重算坐标（约 30 行），或干脆固定宽高比、只允许等比缩放（约 10 行）。

**对 `joy_node` 的接口对照**（我们在 `sim_joy/xbox_sim_joy.py::build_uinput()` 里声明的，对照 Linux `xpad` 驱动下的 360 手柄）：

| 项目 | 我们的虚拟手柄 | 真实 Xbox（xpad/xpadneo/xone） | 影响 |
|---|---|---|---|
| 按钮码 | `BTN_A/B/X/Y`、`BTN_TL/TR`、`BTN_SELECT/START/MODE`、`BTN_THUMBL/R` | 同名同码（Xbox One 起内核别名 `BTN_SOUTH/EAST/NORTH/WEST`，**码值相同**） | ✓ 无 |
| 轴码与顺序 | `ABS_X, ABS_Y, ABS_Z, ABS_RX, ABS_RY, ABS_RZ, ABS_HAT0X, ABS_HAT0Y` | 同序（左摇杆 X/Y、扳机 Z/RZ、右摇杆 RX/RY、十字键 HAT0） | ✓ 无 |
| 量程 | 摇杆 -32768..32767、扳机 0..255、十字键 -1..1 | 多数 xpad 手柄相同；**第三方差别很大**：实测那台是摇杆 0..255（静止在中点 128）、扳机 0..255、十字键 -1..1 | ✓ 已改成**读设备自己的 `absinfo`**：连接时按“双极性 / 单极性”判每个轴是摇杆还是扳机、用内核给的量程归一化（见 §8 的真机表）|
| `EV_FF`（震动） | **没有声明** | 有（rumble） | ⚠️ 只影响"发震动"的程序；`joy_node` 不用，故无害 |
| 设备名 | `Xbox 360 Wireless Controller (Sim)` | USB 线：`Microsoft X-Box 360 pad`；蓝牙：`Xbox Wireless Controller` 等；**第三方：`Zikway HID gamepad`（实测）** | ✓ `joy_node` 按片段匹配（`xbox`/`x-box`/`xinput`/`gamepad`/`joystick`，大小写不敏感），都收 |
| VID:PID | `045E:028E`（360 无线接收器） | 有线 360 是 `045E:028F`，Xbox One 系列另有其值 | ✓ 我们只按名字+能力挑，不按 PID |
| event 节点数 | 1 | 实体手柄常暴露**多个** event 节点（手柄本体 + 媒体键 + 键盘接口）：实测那台 3 个（`event15` 手柄、`event16` Consumer Control、`event17` Keyboard） | ✓ 预筛改成“**有手柄类轴（`ABS_X/Y/Z/RX/RY/RZ/GAS/BRAKE/HAT*`）且有游戏按键（`BTN_A/B/X/Y/TL/TR/…`）**”：只判“绝对轴非 0”会让 `event17` 那种带 `ABS_VOLUME` 的键盘接口混进来；只判“有手柄类轴”又会让**触摸板**（`ABS_X/Y` + `BTN_LEFT`）混进来，两者都会被报成“手柄没权限” |
| 通信方式 | `uinput` 写入 → 内核 input 子系统 → 任何读 `/dev/input/event*` 的程序 | HID 驱动（USB/蓝牙）→ 同一个 input 子系统 | ✓ 对上层完全同构（这正是"造真设备"而非"发假消息"的价值） |

**真机实测（2026-10-07，`Zikway HID gamepad`，USB 有线）**：

| 项 | 实测 | 结论 |
|---|---|---|
| 设备名 / ID | `Zikway HID gamepad` | 不含 `xbox` → 默认片段加了 `gamepad,joystick`；仍可 `-p device:=` 钉住 |
| USB id | vendor `0x3537` / product `0x1041` | 只按名字 + 能力挑设备，不看 PID |
| event 节点 | **3 个**：`event15`（手柄，有 ACL）、`event16`（Consumer Control）、`event17`（Keyboard，带一个 `ABS_VOLUME` 位） | 预筛必须要求"至少一个**手柄类**轴"，否则 `event17` 会被当成候选、再报成"手柄没权限" |
| 轴 | `ABS_X/Y/Z/RZ`：0..255、静止 **128**（两个摇杆）；`ABS_GAS/BRAKE`：0..255、静止 **0**（LT/RT）；`ABS_HAT0X/Y`：−1..1 | 与 xpad **不同**：它没有 `ABS_RX/RY`，右摇杆在 `Z/RZ` 上、扳机在 `GAS/BRAKE` 上 |
| 轴→槽位（实测日志） | `X→axes[0]`、`Y→axes[1]`、`BRAKE→axes[2]`(LT)、`Z→axes[3]`、`RZ→axes[4]`、`GAS→axes[5]`(RT)、`HAT0X/Y→axes[6]/[7]` | 与 xbox 布局**语义一致**（右摇杆在 3/4、扳机在 2/5） |
| 按键 | 19 个：`BTN_A/B/C/X/Y/Z`、`BTN_TL/TR`、`BTN_TL2/TR2`、`BTN_SELECT/START`、**`BTN_MODE`**、`BTN_THUMBL/R` + 3 个音量/电源键 | 我们需要的 11 个码位齐全（含 `BTN_MODE`）；扳机同时上报 `TL2/TR2` 数字键（节点不读，无害） |
| `EV_FF`（震动） | 无 | 我们用不到 |
| 端到端 | A→B→X→A：两次起身、峰值 **z = 0.3836 m**、`ncon=4`、倾角 0.0° | ✅ 与仿真手柄 / 上一版逐位一致 |

**换手柄时怎么核**（`probe_gamepad.py` 就是为它写的）：

```bash
# ① 静态：列设备 + 对照 joy_node 的预期（名字片段、轴码位、量程、槽位），结论直接给 OK/注意/不兼容
pixi run python @20261005_ros2/scripts/agent_scripts/probe_gamepad.py

# ② 动态：按提示把摇杆/扳机/按键/十字键各动一遍，打印"哪个轴/键对应哪个控件"与实测极值
pixi run python @20261005_ros2/scripts/agent_scripts/probe_gamepad.py --watch 60

# ③ 整条链路（狗真的动起来）：起三个节点，按 A/B/X；想钉设备就加 -p device:=/dev/input/eventN
pixi run ros2 launch quadruped_ros2 bringup.launch.py
```

重点核对三件事：**轴量程与槽位**（`absinfo` 是不是双极性/单极性、有没有 `ABS_RX/RY`）、**扳机是轴还是数字键**、**`BTN_MODE` 是否存在**（部分驱动把它单独放在另一个接口上）。
