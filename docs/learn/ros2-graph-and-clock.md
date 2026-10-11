# ROS 2 的三件小事：`/parameter_events` 的连线、`/clock` 仿真时间，以及「名字就是路径」

三件都是本仓实际被问到过的事（前两件 2026-10-06、第三件 2026-10-11），都属于"懂了就不影响使用、不懂容易误判"的机制问题。

## 1 `/parameter_events`：为什么 `rqt_graph` 里有的节点是双向、有的只有去程

**它是什么**：每个节点启动时都会创建一个 `/parameter_events`（`rcl_interfaces/msg/ParameterEvent`）**发布者**，用来广播自己的参数变更；而**带参数服务**的节点还会订阅同一个话题（用于观察其它节点的参数变化，`ParameterEventHandler`、`ros2 param dump` 一类工具就靠它）。所以：

* 只要节点存在 → 有一条**去程**（publish）✓；
* 参数服务默认开启（`start_parameter_services=True`，rclcpp/rclpy 默认都是）→ 还应有**回程**（subscribe）✓。

**我们实测到的"不对称"是工具假象，不是真实拓扑。** 在本任务三节点运行时：

| 检查手段 | `/sim_node`（C++） | `/controller_node`（C++） | `/joy_node`（Python） |
|---|---|---|---|
| `ros2 node info` 的 Subscribers | 有 `/parameter_events` | 有 | **看不到** ✗ |
| `ros2 topic info /parameter_events --verbose`（DDS 发现层） | 在订阅者列表里 | 在订阅者列表里 | **在订阅者列表里** ✓ |

也就是说 `ros2 node info` / `rqt_graph` 读的是 **ROS 图守护进程的缓存**：节点刚起来、守护进程还没刷新，或者守护进程本身被重启过，就会少画边。**要权威判断连接，用 `ros2 topic info <话题> --verbose`（列发布/订阅节点名与 QoS）**，别只看 `rqt_graph` 的箭头。同一现象也能解释"节点已经挂了但图里还在"的幽灵节点——本次调试中我这边就出现过残留节点被误当成"当前拓扑"的情况。

## 2 `/clock` 与 `use_sim_time`：我们该不该用

**机制**：仿真器按 `rosgraph_msgs/msg/Clock` 的格式往 `/clock` 发**仿真时间**；任何把 `use_sim_time` 设为 `true` 的节点会订阅它，并让自己的 `now()`、**定时器**、消息时间戳都跟着仿真时间走（rclcpp 里由 `TimeSource` 在节点构造时挂上，rclpy 同理）。

**好处**：

* 时间可复现：同一条指令序列在任何机器上跑出同样的时间戳；
* 能和 TF、`rosbag2` 录制/回放、rviz 的时间轴对齐（它们默认按 `/clock` 走）；
* 慢放/暂停时所有节点的"时序语义"一致（我们的速度档位 `-/=` 就属于这一类）。

**代价与坑**：

* 仿真一旦卡住或退出，所有等时间的节点一起卡住（**时钟源是单点**），线程里等 sim time 的代码还可能死锁；
* 启动有先后关系：`/clock` 还没来时节点拿到的是 0，做超时判断要先"等时钟有效"；
* `create_wall_timer`（墙钟定时器）**不**受 `use_sim_time` 影响——要用仿真时间必须换成基于节点时钟的定时器，这是个容易漏的改动点；
* `/clock` 本身是额外流量：500 Hz 发一遍就是每秒 500 条消息（一般按固定频率或每 N 步发一次）。

**本任务的决定：不用 `/clock`**（[`@20261005_ros2/docs/ros2-nodes.md`](../../@20261005_ros2/docs/ros2-nodes.md) 记录了这个决策）。理由是当前的时序契约已经是**步数**而不是墙上时间：仿真节点按 500 Hz 步进、`/motor_state` 里带 `sim_time`、控制器按"收到一条反馈发一条指令"事件驱动，看门狗也按控制周期数算——引入 `/clock` 只会多一层耦合。真正需要它的场景是"要用 TF / rviz / rosbag 回放"，届时按上面三条（发 `/clock`、置 `use_sim_time`、换定时器）加，大约 30 行。

## 3 「名字就是路径」吗：ROS 2 里哪些名字会被解析，和类 Unix 路径差在哪

**一句话**：ROS 2 的名字确实是一棵**以节点为根的限定名树**，斜杠有语义（会被 rcl 展开、参与发现与匹配）；但它**不是文件系统路径**——没有 cwd、没有 `.`/`..`、没有软链与权限位，remap 里连通配符都明确"未实现"，`~` 指的是**节点自己**而不是家目录。最容易翻车的是：**"校验器说合法"和"真能建成实体"是两套判据**。

**哪些东西的名字是"真的路径"**（斜杠会被 rcl 解析）：

| 实体 | 是否解析 | 依据 / 本仓例子 |
|---|---|---|
| 节点名 + 命名空间 | ✓ | 节点名本身**不允许含 `/`**（`-r __node:=a/b` 在 rcl 词法解析期就失败）；FQN = `ns + "/" + node`，所以 `ros2 node list` 看到的是 `/robot1/rl_sim_node` |
| 话题 / 服务 / 动作名 | ✓ | 同一套校验（服务走 `validate_topic_name(name, is_service=True)`，异常前缀是 `InvalidServiceNameException` 但正文仍写 "topic name"）；相对名/绝对名/私有名三种前缀都在这里解析 |
| 参数 | ✓（作为名字） | 参数挂在节点 FQN 下：`ros2 param get /robot1/rl_sim_node:status_period_ms`；`--params-file` 的键是"节点名模式"（见下） |
| launch 的 `namespace` / `name` / `remappings` | ✓ | 最终都落成 `__ns` / `__node` / remap 规则，和命令行 `--ros-args` 同一套机制 |
| 消息字段、`header.frame_id` | ✗ | 普通字符串：TF 的层级是**约定**，ROS 不解析。本仓还拿它当状态位用——`joy_node` 发 `joy_connected:Xbox …` / `joy_disconnected`，下游据此忽略断连帧 |
| `--params-file <文件>`、`device:=/dev/input/event15` | ✗ | 那是**操作系统的真实路径**（谁去打开由节点自己决定），与 ROS 名字体系无关 |
| 名字里的 `{}` | 半解析 | 话题名里的 `{}` 是**替换语法**不是普通字符：`{node}`/`{ns}` 会被替换（实测 `{ns}/y` → `/robot1/y`），而 `foo{}` 直接报 `unknown substitution: {}` |

### 3.1 校验规则：rclpy 的"轻量校验器"只管一半

本版（`rclpy 3.3.21` / `rcl 5.3.13`）**没有** `rclpy.validate` 模块，也**没有** `validate_service_name`；实际存在的是 `validate_node_name`、`validate_namespace`、`validate_topic_name(name, *, is_service=False)`、`validate_full_topic_name`、`validate_parameter_name`、`expand_topic_name`（清单可跑出来，见 §3.7）。

| 规则 | 节点名 | 命名空间 | 话题 / 服务名 | 参数名 |
|---|---|---|---|---|
| 字符集 | `[A-Za-z0-9_]`，不得以数字开头，≤255 | 每段同左；**必须绝对**（`/` 开头），`/` 本身合法 | `[A-Za-z0-9_~{}]` 与 `/`；段不得以数字开头、不得以 `/` 结尾；`~` 必须后接 `/` | **只拒绝空串** |
| 非 ASCII | ✗（`naïve`、`机器人` 都非法） | ✗ | ✗ | ✓ |
| `.` `-` 空格 | ✗ | ✗ | ✗ | ✓ |
| `//foo`、`foo//bar` | ✗ | ✗ | **✓（校验器放行！）** | ✓ |
| `{}` | ✗ | ✗ | **✓（校验器放行）** | ✓ |
| 长度 | 校验 255 | — | **校验器完全不查长度** | — |

两个"通过校验却建不出来"的坑（都是实测）：

* `//foo` / `foo//bar` 过得了 `validate_topic_name`，但 `create_publisher` 报 `must not contain repeated '/'`；`foo{}` 过得了校验，建的时候报 `unknown substitution: {}`。
* 长度真正判的是**展开后的全限定名 ≤ 247 字符**（报错原文 `topic length should not exceed '255U - 8U'`，`ns=/` 时也照样打印 `8`）：实测 `/MMMM…`（247 字）可以、248 字失败，与命名空间长短无关。
* 节点名 255 字**通过校验器**却建不出节点（它派生的服务名超长，报 `InvalidServiceNameException`）；256 字报的是含混的 `rcl node's rmw handle is invalid`——同一个含混错误也出现在 `-r __ns:=/robot2/`（尾随斜杠）上，排障时别被它带偏。

### 3.2 三档名字怎么解析：上下文是"节点"，不是"当前目录"

| 写法 | 展开结果（`__ns:=/robot1`、`__node:=probe`） | 说明 |
|---|---|---|
| `rel_topic` | `/robot1/rel_topic` | 相对名 = `ns + "/" + name` |
| `/abs_topic` | `/abs_topic` | 绝对名原样，**忽略命名空间** |
| `~/priv_topic` | `/robot1/probe/priv_topic` | `~` = 节点自己，`~/x` 加在节点 FQN 下面；`~` 单独出现就是节点 FQN |
| `sub/child` | `/robot1/sub/child` | 多级相对名照常拼 |

* **没有 `.`/`..`/归一化**：`foo.bar`、`foo..bar`、`foo/../bar` 都因为字符集被拒（`.` 根本不在允许集里）。
* **没有 cwd**：同一个脚本在 `/tmp` 与在仓库子目录里跑，`get_namespace()` 与三个话题名完全一致；相对名的基准是**节点自己的命名空间**，不是进程工作目录。
* **相对名是"每个节点"的**：同机两个探针实例（`__ns:=/robot1`、`/robot2`）让同一个 `rel_topic` 变成两个不同话题：`/robot1/rel_topic`、`/robot2/rel_topic`。
* **名字在创建时就展开定死**：publisher 拿到手的 `topic_name` 已经是全限定串，remap 规则只在 `rclpy.init()` 时解析一次；rclpy 没有"运行期改节点名字/命名空间"的 API（这点只有间接证据，见 §3.7 的"未验证"）。

**命名空间怎么给**：只有 `-r __ns:=/abs` 这一条路。`--namespace /robot2` **不是**合法的 ros-args（rclpy 报 `UnknownROSArgsError`，rclcpp 报 `found unknown ROS arguments` 并 Aborted）；`-r __ns:=robot2`（相对值）在 rcl 解析 remap 规则时就失败（`Expected lexeme type 19, got 18 at index 6`）；`-r __ns:=/robot2/`（尾随 `/`）会一路漏到 RMW，报出与名称无关的 `rcl node's rmw handle is invalid`。

### 3.3 remap 只有"全限定名精确相等"，没有通配符

| 规则 | 实测结果 |
|---|---|
| `-r rel_topic:=other_rel` | 相对规则按**节点命名空间**展开：`rel_topic` → `/robot1/other_rel` |
| `-r /abs_topic:=/x` | 精确匹配全名，改成 `/x` |
| `-r priv_topic:=z` | **打不到** `~/priv_topic`（私有名要写 `-r '~/priv_topic:=/y'`） |
| `-r /a:=/b`（节点发 `/a/c`） | `/a/c` **不动**——父名 remap 不影响子名，要 `-r /a/c:=/b/c` |
| `-r /a/**:=/b/**` | 解析期硬错误：`Wildcard '**' is not implemented`（`rcl/arguments.c:1167`） |
| `-r /a/*:=/b/*` | 同上：`Wildcard '*' is not implemented`（`arguments.c:1164`） |
| `-r __node:=a/b` / `__node:=1bad` | rcl 词法解析期就失败（`Expected lexeme type …`），不是名称校验错误 |
| `-r __node:=good_name` | 正常：节点 FQN 与该节点的私有名一起变（`~/priv_topic` → `/robot1/good_name/priv_topic`） |

也就是说：**remap 不是"路径前缀替换"**，`__ns` / `__node` 是仅有的两条特殊规则。想要"整棵子树搬家"，靠的是给节点一个命名空间（相对名自动跟随），而不是 remap 通配符。

### 3.4 参数文件里的节点键：`/**` 是"所有节点"，`/*` 只匹配一层

| 文件里的键 | 生效范围（实测） |
|---|---|
| `/**` | **所有节点**，含根命名空间（`__ns` 未设时也命中） |
| `/robot1/**` | 该命名空间及其**任意深度**（`/robot1/sub/probe` 也命中）；在根命名空间下不命中 |
| `/robot1/*` | **只匹配一层**（`/robot1/probe` 命中，`/robot1/sub/probe` 不命中） |
| `/robot1/probe` | 精确节点名，优先级高于通配 |
| 裸 `**:`（没有前导 `/`） | 解析失败：`Couldn't parse params file … parse.c:763` |

另外三条实测：多个 `--params-file` 时**后写的覆盖先写的**；文件里的参数是"覆盖项"，节点没声明就不存在，等它将来 `declare_parameter('extra')` 时才拿到文件里的值（实测 `extra: 7` 事后声明得到 7）。

### 3.5 和类 Unix 路径的异同（一句话版）

| 维度 | 类 Unix 路径 | ROS 2 名字 |
|---|---|---|
| 分隔符 / 绝对 / 相对 | `/`；`/` 开头绝对；相对相对 **cwd** | `/`；`/` 开头绝对；相对相对**节点命名空间** |
| 上行引用 | `..` | **没有**（`.` 都不在字符集里） |
| 当前上下文 | 进程 cwd（可变，`chdir`） | 节点（创建时定死） |
| `~` | 家目录 | **节点自己**（`~` = 节点 FQN，`~/x` = 节点下） |
| 通配符 | shell 层 `*` `?` `**` | 名字里**没有**；`**`/`*` 只在**参数文件**里作为节点名模式存在，remap 里明确未实现 |
| 前缀/子树操作 | 有（目录天然是前缀） | **没有**：remap 精确匹配，"子树搬家"要用命名空间 |
| 链接 / 权限 / 大小写 | 软链、权限位、大小写敏感看文件系统 | 无软链、无权限位；**大小写敏感**（名字按字节比较） |
| 非法字符 | 只有 `/` 与 NUL | 更严：`[A-Za-z0-9_]` + `/`（话题名还多 `~{}`），非 ASCII 非法 |
| 长度 | 单段 255、全路径 4096 | 节点名 255；全限定名 **247**（校验器不查，建实体时查） |

### 3.6 父子/祖先关系（命名空间）到底改变了什么

* **相对名的解析**：祖先命名空间决定相对名落在哪；绝对名不受影响——所以**混用绝对名和相对名，是"`--namespace` 只搬走一半"的根源**。本仓正是这么发现的：`rl_sim` 原来是全仓唯一混用的节点（`/joy`、`/cmd_vel` 绝对，其余相对），2026-10-11 已全部改成相对名，于是 `ros2 run rl_sar rl_sim --ros-args -r __ns:=/robot1` 能把六个接口（含服务 `sim_reset`）一起搬到 `/robot1/…`（[`@20261007_assignment/docs/porting.md`](../../@20261007_assignment/docs/porting.md) §4）。
* **参数文件的子树匹配**：`/ns/**`、`/ns/*` 这里祖先关系**是**语义（见 §3.4）。
* **remap 不继承**：给 `/ns` 写的规则不会作用到 `/ns/topic`（§3.3）。
* **可观测性**：`ros2 node list`、`ros2 topic list`、`ros2 param get /ns/node:param` 显示的都是**全限定名**——排查"搬到哪去了"就靠它们。
* **私有名随节点名/命名空间一起变**：`~/x` 的展开同时依赖 ns 与节点名，所以 `-r __node:=` 也会改变私有名的落点（§3.3 最后一行）。

### 3.7 复现命令与"未验证"

仪器在任务目录里（conventions §3.7：调查仪器不进主干）：

```bash
# ① 校验器清单 + 逐项试（含精确错误串）
pixi run python @20261007_assignment/scripts/agent_scripts/ros2_naming/val.py

# ② 三档名字的解析：相对 / 绝对 / 私有（探针节点发三个话题并打印）
PROBE_DURATION=24 pixi run python @20261007_assignment/scripts/agent_scripts/ros2_naming/probe_node.py \
    --ros-args -r __ns:=/robot1 -r __node:=probe &
pixi run ros2 node list ; pixi run ros2 topic list

# ③ remap 精确匹配 / 无通配符（父名不动子名、`**` 直接报未实现）
pixi run python @20261007_assignment/scripts/agent_scripts/ros2_naming/ac_node.py --ros-args -r /a:=/b
pixi run python @20261007_assignment/scripts/agent_scripts/ros2_naming/probe_node.py --ros-args -r '/a/**:=/b/**'

# ④ 参数文件的节点名模式（/**、/robot1/**、/robot1/*、精确名、裸 **）
PROBE_DURATION=4 pixi run python @20261007_assignment/scripts/agent_scripts/ros2_naming/probe_node.py \
    --ros-args --params-file @20261007_assignment/scripts/agent_scripts/ros2_naming/p_robot1.yaml \
    -r __ns:=/robot1 -r __node:=probe

# ⑤ "校验通过 ≠ 建得出来"：//foo、foo{}、超长名
pixi run python @20261007_assignment/scripts/agent_scripts/ros2_naming/surprise.py --ros-args -r __ns:=/robot1
```

**没有验证的**（写文档时特意留着，别当成结论）：247 上限里那个 `8` 的确切来历（只测到边界与三条对照点）；"名字创建时一次解析"只有间接证据（没有运行期改名字的 API，也没做对照）；`{}` 只测了 `{node}`/`{ns}`；参数文件只测了上表五种键形式，`/a/*/b` 这类混合模式未测；C++ 侧 `rclcpp` 的校验器 API、多机/DDS 差异未测。这些命令当初都带 `ROS_DOMAIN_ID=42`（与当时正在跑的会话隔离）、单次观测窗口 3–24 s；照抄时不必加域号——探针只发自己的 `rel_topic`/`abs_topic`/`~/priv_topic`，不影响别的节点。`surprise.py` 想换一组名字就设 `TOPICS='["a/b", "ns//x"]'`（不设就用默认那五个）。
