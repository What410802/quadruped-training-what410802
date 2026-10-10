# TBB（oneTBB）是什么

> 这份笔记回答"TBB 是什么、为什么我们的依赖里会有它"。目前唯一的使用者是 [`@20261007_assignment`](../../@20261007_assignment/README.md) 的 rl_sar 移植：它的两条线程之间用一个 TBB 的并发队列交接动作（[`porting.md`](../../@20261007_assignment/docs/porting.md) §5、§7）。依赖声明在根 [`pixi.toml`](../../pixi.toml)；我们自己的线程与锁见 [`runtime-timing.md`](runtime-timing.md)；文档索引见 [`../../README.md`](../../README.md)。

## 1. 一句话

TBB（Intel Threading Building Blocks，现在的开源版本叫 **oneTBB**）是一个 **C++ 并行编程库**：C++ 标准库之外的三方库，把"开线程、把活分到多个核、在线程间安全地传数据"包装成现成的算法与容器。它的用法就是 `#include` 头文件 + 链接 `libtbb`。

## 2. 它提供什么（以及我们用了哪一块）

它是个工具箱，常见的有四类：

| 类别 | 例子 | 我们用了吗 |
|---|---|---|
| 任务调度与并行算法 | `parallel_for`、`parallel_reduce`、`task_group`、`flow_graph` | 没有 |
| 并发容器 | `concurrent_queue`、`concurrent_hash_map`、`concurrent_vector` | **只用了 `concurrent_queue`** |
| 内存分配器 | `scalable_allocator`、`cache_aligned_allocator` | 没有（容器内部可能用，我们没有直接调） |
| 同步原语 | `spin_mutex`、`queuing_mutex`、`rw_mutex` | 没有 |

也就是说，rl_sar 用的是这个库里最普通的一个类；库的其余部分与我们无关。（头文件有 `<tbb/...>` 与 `<oneapi/tbb/...>` 两个等价路径，前者是兼容旧写法的别名；rl_sar 用的是 `<tbb/concurrent_queue.h>`。）

## 3. `tbb::concurrent_queue`：它在 rl_sar 里干什么

三个成员在 [`rl_sdk.hpp:180`](../../@20261007_assignment/ws/src/rl_sar/library/core/rl_sdk/rl_sdk.hpp) 起：

```cpp
tbb::concurrent_queue<torch::Tensor> output_dof_pos_queue;
tbb::concurrent_queue<torch::Tensor> output_dof_vel_queue;
tbb::concurrent_queue<torch::Tensor> output_dof_tau_queue;
```

用法是生产 / 消费：**策略线程**（每 20 ms 一次 `RunModel()`）把刚算出的关节目标 `push` 进去（[`rl_sim.cpp:305`](../../@20261007_assignment/ws/src/rl_sar/src/rl_sim.cpp)），**控制线程**（每 5 ms 一次状态机 `Run()`）用 `try_pop` 取（[`fsm.hpp:216`](../../@20261007_assignment/ws/src/rl_sar/policy/black/fsm.hpp)）。三个队列里实际被消费的是 pos 与 vel 两个（`fsm.hpp` 一次取两条），`tau` 那条上游只生产不消费——**本仓的移植已经不再 push 它**（P1-b，见 [`../../@20261007_assignment/docs/status.md`](../../@20261007_assignment/docs/status.md)）——它从哪个提交引进、为什么没有消费者、无界会涨到多少、主办方怎么补的，见 [`rl-sar.md`](rl-sar.md) §5。

它保证的语义（以环境里的 oneTBB 2023.1.0 头文件为准）：

| 特性 | `tbb::concurrent_queue`（我们用的这个） | 对比：`tbb::concurrent_bounded_queue` |
|---|---|---|
| 容量 | **无界**，`push` 不因"满"而等待 | 有容量；满了 `push` 要等、`try_push` 返回 `false` |
| 取 | 只有 `try_pop`：**队列空立即返回 `false`**，不阻塞 | 有阻塞的 `pop`（等到有为止） |
| 并发 | 多生产者 / 多消费者可同时 `push` / `try_pop`，不需要外部的锁 | 同左 |
| 顺序 | FIFO | FIFO |
| 其它 | `size()` 叫 `unsafe_size()`、迭代器带 `unsafe_` 前缀：只给调试，并发时读数不可靠 | 同左 |

"控制线程 `try_pop` 拿不到就沿用上一帧目标、不等待"正是它 5 ms 控制周期的写法（`fsm.hpp:216` 的 `&&` 短路：任一队列空就整帧不动）。元素是 `torch::Tensor`：`push` / `try_pop` 传的是句柄，不搬数据。

用标准库也能做同一件事（`std::mutex` + `std::deque` + `std::condition_variable`），但要自己管锁与唤醒；上游选择 TBB 这个现成容器，移植时按"框架层逐字复制"保留（[`porting.md`](../../@20261007_assignment/docs/porting.md) §2）。

**它只管这条队列**：两条线程共享的其它数据（`robot_state`、`output_dof_pos` 成员、ROS 回调写的消息）没走队列、也不加锁，那是另一件事，分析见 [`porting.md`](../../@20261007_assignment/docs/porting.md) §7。

## 4. 怎么进到我们的构建里

- 依赖：根 `pixi.toml` 的 `tbb-devel`（conda-forge；运行时库 `tbb` 一起装上）。
- CMake：`find_package(TBB REQUIRED)`，链接目标 `TBB::tbb`（[`CMakeLists.txt:27`](../../@20261007_assignment/ws/src/rl_sar/CMakeLists.txt)、`:41`）。
- 最小用法：

```cpp
#include <tbb/concurrent_queue.h>

tbb::concurrent_queue<double> q;      // 无界
q.push(1.0);                          // 生产：不阻塞
double v = 0.0;
if (q.try_pop(v)) { /* 取到了 */ }     // 消费：空则 false，不等待
```

## 5. 来源与版本

- 官方仓库：<https://github.com/uxlfoundation/oneTBB>（原 `oneapi-src/oneTBB`，Apache-2.0）。
- 本环境版本：conda-forge 的 `tbb` / `tbb-devel` **2023.1.0**（`pixi.toml` 只写 `tbb-devel = "*"`，版本由 `pixi.lock` 锁定）。查版本：`pixi list tbb`。
