# cpp/：任务 4 的结论与落点

任务 2 的 C++ 版在 [`../cpp_task2/`](../cpp_task2/)（平地场景 + 零力矩静止趴卧、静止判定、与 Python 侧逐项对照的数字）。

任务 4 原计划在这里把 [`../python/`](../python/) 的双缓冲结构用 C++ 复刻一遍（物理线程独占 `mjData`、渲染只读快照副本、锁只罩 memcpy）。**实测结论：不必复刻**——`cpp_task2 --mode view` 用的是 MuJoCo 官方 `Simulate` 界面（`mj::Simulate` + `mj::GlfwAdapter`），官方 `RenderLoop` 在 `Render()` 之前就放锁（源码注释 `// MutexLock (unblocks simulation thread)`），渲染不在锁里、物理照常推进，实测 **1.00x 实时** 且画面流畅；Python 侧那 0.14x 的缺口来自 GIL，C++ 不存在这个问题。逐帧对比见 [`../../docs/learn/runtime-timing.md`](../../docs/learn/runtime-timing.md) §11 的方案 ③，线程与通道结构的研读见 [`../../docs/learn/unitree-mujoco.md`](../../docs/learn/unitree-mujoco.md)。

如果要走的**是“不依赖官方 UI、自带渲染循环”那条路**，就在这里落 `CMakeLists.txt` 与 `src/`，构建目录用 `cpp/build/`（已被 `.gitignore` 忽略）；那时才有必要照 [`../python/simulator.py`](../python/simulator.py) 的写法自己搬快照。
