# MuJoCo 官方窗口：全量按键与显示开关（含移植到自建窗口的代价）

**一句话结论**：官方 `Simulate` 窗口的交互分三层——**框架按键**（12 个，硬编码在 `simulate/simulate.cc` 的按键分支里）、**显示开关快捷键**（42 个，来自 `mjVISSTRING` / `mjRNDSTRING` 两张常量表，由 mjUI 的快捷键机制自动绑定）、**只在面板里有的**（暂停/单步/扰动/热重载/噪声/历史刮擦等，没有键）。前两层搬到我们的自建窗口里**一共约 55 行**（一次性，每帧零成本），第三层不建议搬。

本文是**上游知识的全量索引**；我们窗口现在实际支持哪些键，写在任务侧 [`@20261005_ros2/docs/ros2-nodes.md` §2.1](../../@20261005_ros2/docs/ros2-nodes.md)。

## 1 怎么拿到全量映射（可复现）

两张快捷键表是 MuJoCo 的**导出常量**，Python 绑定里就有，不需要读源码：

```bash
pixi run python -c "
import mujoco
for table in (mujoco.mjVISSTRING, mujoco.mjRNDSTRING):
    for i, row in enumerate(table):
        print(i, row[0], '| 默认', row[1], '| 快捷键', row[2] or '(无)')"
```

三列表的含义：`[0]` = 面板里显示的名字、`[1]` = **默认是否开启**（`"0"` / `"1"`）、`[2]` = 快捷键（空 = 没有键，只能点面板）。框架按键的权威出处是官方 `simulate/simulate.cc` 的按键分支（本文第 2 节每行都给了行号，版本为本机 MuJoCo 3.12.0）。

## 2 框架按键（12 个，出处 `simulate/simulate.cc`）

| 键 | 作用 | 出处 |
|---|---|---|
| `Space` | 运行 / 暂停（`sim->run` 取反，并清掉扰动） | `simulate.cc:1887` |
| `→` | **暂停时单步前进**（走一步并把状态压进历史缓冲） | `simulate.cc:1899` |
| `←` | 暂停 + **历史回退一步**（走历史刮擦器） | `simulate.cc:1920` |
| `PageUp` | 扰动选择上移到父 body | `simulate.cc:1935` |
| `]` / `[` | 下一台 / 上一台**固定相机**（模型 `ncam>0` 才有意义） | `simulate.cc:1949` / `:1963` |
| `F6` | 循环 frame 可视化（None→Body→Geom→Site→Camera→Light→Contact→World） | `simulate.cc:1977` |
| `F7` | 循环 label 可视化（17 种） | `simulate.cc:1984` |
| `Esc` | **回到 free 相机**（注意：不是退出程序） | `simulate.cc:1991` |
| `-` / `=` | 降速 / 提速，在 `percentRealTime` 的 **31 档**上走：100 → 80 → 63 → 50 → … → 0.2 → 0.1（`%`）；带 Shift 时不生效 | `simulate.cc:1997` / `:2007`，档位表见 `simulate.h:241` |
| `Tab` / `Shift+Tab` | 收起 / 放下**左面板** / **右面板** | `simulate.cc:2014` |

**没有退出快捷键**（要点窗口关闭按钮）；全屏、垂直同步、字体、配色都是面板项而不是键（`simulate.cc:1694`-`1699`）。

## 3 显示开关快捷键（42 个，来自两张常量表）

按快捷键排序，`组` 说明它改的是哪个数组：`mjvOption.flags[]`（可视化项，影响"画什么"）与 `mjvScene.flags[]`（渲染项，影响"怎么画"）。`默认` 一列对应上面的 `[1]`。

| 键 | 项 | 组 | 索引 | 默认 |
|---|---|---|---|---|
| `'` | Scale Inertia | `mjvOption.flags` | 11 | 关 |
| `,` | Activation | `mjvOption.flags` | 5 | 关 |
| `,` | Segment | `mjvScene.flags` | 8 | 关 |
| `/` | Haze | `mjvScene.flags` | 6 | **开** |
| `;` | Skin | `mjvOption.flags` | 23 | **开** |
| 反引号键 | Body Tree | `mjvOption.flags` | 28 | 关 |
| `\` | Mesh Tree | `mjvOption.flags` | 29 | 关 |
| `A` | Auto Connect | `mjvOption.flags` | 19 | 关 |
| `B` | Perturb Force | `mjvOption.flags` | 12 | 关 |
| `C` | Contact Point | `mjvOption.flags` | 14 | 关 |
| `D` | Static Body | `mjvOption.flags` | 22 | **开** |
| `E` | Equality | `mjvOption.flags` | 9 | 关 |
| `F` | Contact Force | `mjvOption.flags` | 16 | 关 |
| `G` | Fog | `mjvScene.flags` | 5 | 关 |
| `H` | Convex Hull | `mjvOption.flags` | 0 | 关 |
| `I` | Inertia | `mjvOption.flags` | 10 | 关 |
| `J` | Joint | `mjvOption.flags` | 2 | 关 |
| `K` | Skybox | `mjvScene.flags` | 4 | **开** |
| `L` | Additive | `mjvScene.flags` | 3 | 关 |
| `M` | Center of Mass | `mjvOption.flags` | 20 | 关 |
| `N` | Island | `mjvOption.flags` | 15 | 关 |
| `O` | Perturb Object | `mjvOption.flags` | 13 | **开** |
| `P` | Contact Split | `mjvOption.flags` | 17 | 关 |
| `Q` | Camera | `mjvOption.flags` | 3 | 关 |
| `R` | Reflection | `mjvScene.flags` | 2 | **开** |
| `S` | Shadow | `mjvScene.flags` | 0 | **开** |
| `T` | Transparent | `mjvOption.flags` | 18 | 关 |
| `U` | Actuator | `mjvOption.flags` | 4 | 关 |
| `V` | Tendon | `mjvOption.flags` | 7 | **开** |
| `W` | Wireframe | `mjvScene.flags` | 1 | 关 |
| `X` | Texture | `mjvOption.flags` | 1 | **开** |
| `Y` | Range Finder | `mjvOption.flags` | 8 | **开** |
| `Z` | Light | `mjvOption.flags` | 6 | 关 |

没有快捷键、只能点面板的 9 项：`Select Point`(21)、`Flex Vert`(24)、`Flex Edge`(25)、`Flex Face`(26)、`Flex Skin`(27)、`SDF iters`(30)（以上在 `mjvOption.flags`），以及 `Depth`(7)、`Id Color`(9)、`Cull Face`(10)（在 `mjvScene.flags`）。

两个细节：`C` 同时是 `Camera`(Q) 的邻居 `Contact Point` 与 `Cull Face`(无键) 中的前者，`P` 是 `Contact Split` 而不是"点"；**`,` 被 `Activation` 与 `Segment` 共用**（按一下就同时翻两个，因为 mjUI 是"按键匹配字符串就翻"）；`S`/`R`/`K`/`/` 这些默认开的项，按一下就是关掉——**阴影性能开关就在 `S` 上**，与我们 `viewer_shadow` 参数是同一件事（见 [`ros2-nodes.md` §2.1](../../@20261005_ros2/docs/ros2-nodes.md)）。

## 4 鼠标（官方 `simulate.cc:2035`-`2100` + `platform_ui_adapter.cc`）

| 操作 | 作用 |
|---|---|
| 左键拖动（3D 区域） | 旋转 |
| 右键拖动 | 平移（Shift 换轴） |
| 中键拖动 | 缩放 |
| 滚轮 | 缩放，**每格 = 垂直视野的 2%**（`simulate.cc:97` 的 `zoom_increment`） |
| 左键单击 body | 选中该 body（`mjv_select`，`simulate.cc:2058`），供扰动与 `PageUp` 用 |
| **Ctrl + 左/右键拖动** | **施加扰动**：Shift 决定平移 / 旋转（`simulate.cc:2042`-`2080`） |
| 双击面板标题 | 折叠 / 展开面板（mjUI 行为） |
| 右键点面板 | 关闭该面板（mjUI 行为） |

## 5 只有面板里才有的能力（如果要，用官方 UI）

`Simulation` 面板：暂停/复位/对齐、**Reload（热重载模型）**、Copy state、Key 加载/保存、**`Noise scale` / `Noise rate`（给 ctrl 加噪声）**、**History 刮擦器**；`Watch` 面板按字段名+下标盯任意 `d->` 变量；`Info` / `Profiler` / `Sensor` 三张实时表；`Rendering` / `Visualization` / `Group` / `Override` 等面板改的是前面两张表对应的字段；`Joint` / `Control` / `Equality` 面板直接拖动关节与执行器。

这些是**整个 mjUI 框架**（上千行）承载的，搬不过来；需要时用官方 UI 打开同一个场景即可（本机 MuJoCo 是二进制发布包，**没有 `simulate` 可执行文件**，用 Python 入口）：

```bash
pixi run python -m mujoco.viewer @20261005_ros2/scenes/flat_scene.xml
```

注意这是 `launch_passive` 通道（Python 侧），实测只有 ~0.93x 实时，**只适合看模型/场景，不适合实时验证控制**；实时验证仍走我们的 `ros2 launch quadruped_ros2 bringup.launch.py`。

## 6 移植到自建窗口的代价（结论：显示那组不显著）

我们自建窗口（[`viewer.hpp`](../../@20261005_ros2/ws/src/quadruped_ros2/include/quadruped_ros2/viewer.hpp)）自己拥有 `mjvOption` / `mjvScene`，所以第 3 节那 42 个开关都是"改一个 bit"，难点只在**键位冲突**与**HUD 怎么显示**：

| 分组 | 内容 | 估计行数 | 每帧成本 | 建议 |
|---|---|---|---|---|
| **A 显示开关** | 33 个有键的项（遍历两张表的快捷键字符串，命中就翻对应 bit）+ HUD 上列出已开启的项 | **~30 行** | 0（标志只在渲染时被读） | ✅ **已实施**（2026-10-06） |
| **B 小功能** | `F6`/`F7` 循环 frame/label、`-`/`=` 速度档位（窗口 pacing 乘倍率）、`→` 暂停时单步、`Home` 回默认视角 | **~25 行** | 0 | ✅ **已实施**（2026-10-06） |
| **C 扰动** | body 拾取（`mjv_select`）+ `Ctrl+拖动` 施力 + **在 `mj_step` 之前 `mjv_applyPerturbForce`**（要动物理循环）+ HUD 提示 | ~100 行 | 每步一次 `mjv_applyPerturbForce` | ⚠️ 可选：想"推狗"验证抗扰时再做 |
| **C 历史倒退** | 官方是 `mj_getState` 环形缓冲（上限 **100 MB**，`simulate.cc:2590`）+ 刮擦滑块 + `←` 回退 | ~100 行 | 每步一次状态拷贝 | ❌ 不建议（回归有脚本、看历史有录屏） |
| **C 面板类** | watch / info / profiler / sensor / 物理参数热改 / 模型热重载 / 相机选择 / 图像传感器 | 上千行（等于重写界面） | — | ❌ 用官方 UI 代替（第 5 节） |

**键位冲突必须先解决**（这是 A 组唯一真正的设计工作）：官方把 `R`（反射）、`S`（阴影）、`Q`（相机）、`Esc`（free 相机）都用掉了，而我们现在的 `R` = 复位、`S` = 阴影（恰好一致）、`Q`/`Esc` = 退出。可选的干净方案是：**节点动作加 Ctrl**（`Ctrl+R` 复位、`Ctrl+Q` 退出）、`Space` 暂停（与官方一致）、`Esc` 保留退出（与官方"Esc = free 相机"不同，但符合多数人预期），其余字母全部让给显示开关。

## 7 这些开关的功能是谁实现的？（只翻 bit 还是自己画？）

**只翻 bit，功能在 libmujoco 里。** `mjvOption.flags[]` / `mjvScene.flags[]` / `mjvOption.frame` / `mjvOption.label` 都只是 `mjv_updateScene`（把开关变成 `mjvScene` 里的几何）和 `mjr_render`（把 `mjvScene` 画出来）的入参——这两个函数是库的公开 API，我们每帧已经在调（官方界面调的也是它们），**"画关节轴/标签/接触力箭头"的代码在库里**（`engine_vis_*`），既不在官方 `simulate.cc`，也不在我们窗口里。

| 开关 | ngeom | 开关 | ngeom |
|---|---|---|---|
| 基线 | 21 | `A` 自动连线 | 21 → **51** |
| `J` 关节轴 | 21 → **34** | `I` 惯性系 | 21 → **40** |
| `U` 执行器 | 21 → **33** | Body Tree / Mesh Tree | 21 → 44 / 49 |
| `C` 接触点 / `F` 接触力 | 21 → **25** | `Z` 灯光 / `M` 质心 | 21 → 22 |
| `D` 静态体（默认开） | 关掉 21 → **20** | `S`/`R`/`K`/`W`/`G`/`/`/`L`/`,`（渲染项） | 不变（只改画法） |

`Q` / `V` / `Y` / `E` / `N` / `P` / `B` / `O` / `H` / `'` / `;` / `T` / `,`（可视化侧）在本模型上 ngeom 不变，因为**模型里没有对应对象**（0 台相机、0 腱、0 测距、0 等式约束、无激活动态、无 flex/skin/透明几何），开关翻了但没东西可画——这解释了"为什么有些键按下去没反应"。

## 8 官方的按键能改吗？

三层，各不一样：

| 层 | 存在形式 | 能不能改 |
|---|---|---|
| **33 个显示开关的快捷键** | 库里的导出表 `extern const char* mjVISSTRING[][3]` / `mjRNDSTRING[][3]`（字符串本身在 `.rodata`，但**指针数组可写**） | 可以：给指针槽赋新字符串即可（`mjVISSTRING[i][2] = "F9"`），但那是**进程级**的——连官方界面会一起变，属于 hack |
| **12 个框架按键** | 官方 `simulate.cc` 里硬编码的 `case`（本文第 2 节） | 只能改官方源码重编 `libmujoco_simulate`；我们不用它，所以与我们无关 |
| **我们自己窗口的键位** | `viewer.hpp`：绑定表由库表自动生成 + 一张 `kRemap` 覆写表（`{官方快捷键, 换成哪个 GLFW 键}`） | 改一行即可（例如把"反射"从 `R` 挪到 `F9`：`{'R', GLFW_KEY_F9}`），渲染与节点代码都不用动；节点动作键（`Space`/`→`/`-`/`=`/`Ctrl+R`/`Ctrl+Q`）在 `sim_node.cpp` 的按键分发里，也在一个地方 |

**为什么官方界面自己也用不了"改键"**：它的按键处理是写死的 `switch`，而面板项与快捷键的对应关系藏在库表里，两者只能通过"重编"或"改库表的指针槽"来动——这也是我们把映射做成**数据表**的原因（见上一节）。

## 9 我们自建窗口现在支持的键（对照用）

`Space` 暂停/继续、`→` 暂停时单步、`-`/`=` 速度（31 档）、`Ctrl+R` 复位、`Ctrl+Q`/`Esc` 退出、33 个显示开关快捷键（第 3 节全表）、`F6`/`F7`/`Home`；鼠标左键转、右键平移（Shift 换轴）、中键/滚轮缩放（每格 5%，官方是 2%）。HUD 右上角显示状态/实时倍率/速度档、当前开着的开关、键位提示。完整接口与实测数据见 [`ros2-nodes.md` §2.1](../../@20261005_ros2/docs/ros2-nodes.md)；"官方界面为什么鼠标一动就掉帧"的诊断也在那一节。
