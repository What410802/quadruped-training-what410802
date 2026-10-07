# ROS 2 的两件小事：`/parameter_events` 的连线、以及 `/clock` 仿真时间

两件都在这次任务里被问到过（2026-10-06），都属于"懂了就不影响使用、不懂容易误判"的机制问题。

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
