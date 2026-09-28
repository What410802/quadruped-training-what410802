# essential：最简版（官方窗口 + 终端按键 + 站姿预存）

> 这是 [`../`](../README.md)（完整版）的精简副本，目标是**一次读懂**这次培训的控制程序：MIT 关节电机 + 两状态机 + 站姿。
> 与完整版的三处不同：① 窗口用 MuJoCo **官方**的 Simulate 界面、按键从**终端**读；② **站姿预先搜好存在文件里**，启动时加载而不是搜索；③ 只留一个模式（没有 `--mode sim/record`）。
> 完整版的实测数字与踩坑在 [`../docs/sim.md`](../docs/sim.md)。

## 与完整版的差别

| 去掉了 | 为什么可以去掉 |
|---|---|
| **自写窗口**（`../src/viewer.h`，200 行 GLFW/mjr 代码） | 换成官方 Simulate 界面：相机、暂停/单步/调速、关节与执行器面板都是现成的；它的键挂不上自定义回调，于是我们的 4 个键改从终端读（`src/tty.h`） |
| **站姿搜索**（`stance::Search`，70 行扫描） | 站姿只由**模型**决定，每次搜出来都一样 ⇒ 预先算好存进 [`../../models/stance.txt`](../../models/stance.txt)，启动时加载（`src/stance_file.h` 只留"读"这一半） |
| `--mode sim/record` 与 `--script`、`recorder.h` | 回归与录像是"交作业"的工程手段，与控制程序本身无关 |
| 倾斜地面 `--pitch/--roll`、摩擦 `--floor-*`、`ground.h` | 量测要跟着地面法向走（`stance::Plane`），是这次任务之外的一个 demo |
| 电机非理想项 `--tau-max/--deadzone/--delay-cycles/--noise`、`--gravity-comp`、`--gear` | 只留"MIT 公式 + 模型自带的 `ctrlrange` 限幅"；那三类非线性的实测见完整版与 `docs/sim.md` |
| `--width/--height` | 窗口归官方界面管，尺寸不归我们 |
| 只给完整版用的死代码 | `ctrl::NameAscii` / `ParseState` / `last_event_ascii` / `Ramping` / `q_des()`、构造时查一遍却没人读的 `qadr_`、`motor::command()` / `ResetStats()` —— 都是自写窗口 HUD 与脚本模式留下的，最简版没有它们 |

保留下来的控制程序一个字没变：状态机与自动斜坡（`ctrl::StateMachine`）、四足触地/高度/竖直度/漂移的口径、`--start raw|stance|rest|side`、`--kp/--kd/--kd-damp/--ramp`。

## 怎么跑

```bash
cd ..   # 仓库根目录（有 pixi.toml）
pixi run cmake -S @20260927_motor/cpp/essential -B @20260927_motor/cpp/essential/build -G Ninja -DCMAKE_PREFIX_PATH="$CONDA_PREFIX"
pixi run cmake --build @20260927_motor/cpp/essential/build

pixi run @20260927_motor/cpp/essential/build/essential_sim                # 开官方窗口；在**这个终端**里按键
pixi run @20260927_motor/cpp/essential/build/essential_sim --start rest   # 从场景自带的趴卧姿态起，按 S 起身
pixi run @20260927_motor/cpp/essential/build/essential_sim --help         # 比完整版少一半的选项
```

在**运行它的那个终端**里按键（不用回车、不回显）：

| 键 | 作用 |
|---|---|
| `S` | 站立模式：`q_des` 从按下那一刻的关节角在斜坡时长里推到站姿（`--ramp auto` 按按下时的姿态选 0.1 s / 1.5 s） |
| `D` | 阻尼模式：松开位置项，只剩 τ = −kd·q̇，狗在重力下自己塌回去 |
| `R` | 回到起点（`--start` 指定的位姿），并切回阻尼模式 |
| `Q` / `Ctrl-C` | 收工：打印摘要、关掉窗口、正常退出（退出码 0） |

窗口里是官方界面：**空格 = 暂停/继续**（暂停时控制循环也不推进，时间轴重新对齐）、鼠标操作相机、面板能改 `qpos`/`ctrl` 看实时数值；直接关掉窗口同样正常收工。

## 目录（都在 `src/` 下，与完整版的 `cpp/src/` 对齐）

| 文件 | 与 [`../src/`](../src/) 的关系 |
|---|---|
| `main.cpp` | 编排：建官方窗口（主线程 `RenderLoop()`）+ 控制线程（装配 → `Load` → 一步一循环）；**`R` 的"回起点"就写在这里**（详见下面「四个改进」） |
| `tty.h` | **新增**：终端按键（raw 模式 + 非阻塞轮询 + 析构复原），替掉了 `viewer.h` 的键盘回调 |
| `stance_file.h` | **新增**：站姿文件的读取与指纹校验（格式定义在完整版那份 `../../src/stance_file.h`）；只读 `version`/`model`/`feet`/`z`/`q` 五行 |
| `stance.h` | 精简：删掉 `Search`（站姿改从文件来）与 `Plane`（地面恒水平），只留查脚、量测、`TiltDeg` 与 `Target`；`Target` 只留 `q`/`z`/`ok` |
| `state.h` | 精简：`Config` 去掉 `ground`/`gravity_comp`，"还在站姿附近"改用世界 z 与竖直度；HUD/脚本相关的死代码已删；另收留了原来在 `stance.h` 里、只有它用的 `Smoothstep` / `JointAngles` |
| `scene_setup.h` | 精简：没有 floor geom / 摩擦覆盖 / 倾斜地面；站姿改成读文件；`Scene::Release()` 把 `m/d` 所有权交给官方界面 |
| `motor.h` | 精简：只留 MIT 公式 + 模型自带限幅 + 统计 |
| `observation.h` | 精简：`Sample` 不需要 `stance::Plane` 参数 |
| `start.h` | 精简：只剩 "摆到 `--start`" 的 `Pose`（删掉倾斜那一支，所以少 3 个参数）；完整版那个 `Reset` 胶水没搬过来（只有一个调用点，内联在 `main.cpp` 里） |
| `cli.h` / `args.h` | 命令行的语义/语法两半；`args.h` 是逐字复制 |
| `CMakeLists.txt`（上一级） | 单独的工程与 target `essential_sim`；链 `mujoco::mujoco` + `mujoco::libmujoco_simulate` + glfw + `Threads::Threads` |

**没有 `hud.h`**，仓库里从来没有过：当初决定"HUD 片段先不拆头文件、只在 `../src/main.cpp` 里合并去重"，所以它一直是那两三个匿名命名空间里的小函数。最简版换成官方窗口之后，连那段也不需要了——日志（状态切换、起点/收工摘要、统计）直接打在这个终端上。

## 四个改进（解耦 vs demo 简洁性）

这四条都是"去掉只有完整版才需要的抽象"，改完两边行为仍然逐字相同（下面「验证」的 B 组）：

1. **"回起点"不再是一个函数**：完整版的 `start::Reset` = 摆位 + 前后各量一次 + 切回阻尼，因为那边**窗口按键**和**录像脚本**两个地方都要用；最简版只有 `R` 一个入口，于是直接写在 `main.cpp` 按 `R` 的分支里 —— `start.h` 就只剩 `Pose` 这一件事（"改状态"）。
2. **`Smoothstep` / `JointAngles` 从 `stance.h` 搬到 `state.h`**：它们只有状态机用（斜坡插值、"按下那一刻的关节角"），住在"站姿（控制目标）与量测"这个概念里会让 `stance.h` 不纯；`stance.h` 里 `TiltDeg` 仍被状态机用，所以那条依赖留着。
3. **`stance::Target` 只留 `q` / `z` / `ok`**：`bend` / `frac` / `com_err` / `feet` 是完整版**搜索的内部量**（搜完顺手记下来打日志），最简版不搜也不报。它们仍然留在**文件的 `search` 行**里（对拍和复现要用），只是加载器不读了——顺带把读它们的 `Field()` 小工具也删了，`ParseNumbers` 改用 `std::istringstream`（少一个手写指针循环）。
4. **启动日志收敛**：删掉 `电机模型：理想力矩源（τ = …）` 一行 —— 公式就写在 `motor.h` 的注释里，而紧跟的 `状态机：阻尼模式：kp=0 kd=0.5；站立模式：kp=80 kd=3` 已经把两个模式的参数全说了；`站姿` 那行也从"膝 X rad、大腿 Y×膝、质心离…、四足触地…"收成"基座 z=…"（站姿文件里本来就写着，不必每次启动重念）。完整版那边一个字没动（那是对拍基线）。

## 站姿为什么可以预存

站姿只由**模型**决定——关节限位、几何、质量；跟场景、摩擦、控制增益都无关，所以同一份模型搜出来的结果每次都一样。那就没有理由每次启动都再扫一遍（也省得最简版背着整套搜索代码）。于是：

- **写**：完整版 `motor_sim --dump-stance <文件>` 把 `stance::Search` 的结果按固定格式写出来（仓库里那份 = `models/stance.txt`，与模型放在一起）；
- **读**：本版本启动时只做"打开 → 对指纹 → 装进 `stance::Target`"，`--stance FILE` 可以换一份（默认按"从可执行文件往上找带 `scenes/` 的目录"定位）；
- **指纹**：`model`（nq/nv/nu/nbody/ngeom/总质量）与 `feet`（足底球个数/半径）两行**逐字比对**，不符就报错退出——宁可报错，也不要偷偷用一个不属于当前模型的站姿。报错里直接给出重新生成的命令。
- **数值精度**：数字按 `%.17g` 写，读回来与搜出来的 double **逐位相同**，所以两边的物理结果能直接对拍（下面"验证"里的 B 组就是这么做的）。

## 三个踩坑（都是这次实测出来的）

1. **`Simulate::Load()` 会阻塞等渲染线程来接模型**，所以顺序必须是"主线程先进 `RenderLoop()`，控制线程里再 `Load()`"；反了就是开一个空白窗口然后死等（`Simulate::Load` 里有个条件变量，官方 `main.cc` 也是这个顺序）。
2. **官方窗口的程序化退出**：`sim.exitrequest` 只是通知物理线程，`RenderLoop()` 不看它；`GlfwAdapter` 把 `GLFWwindow*` 藏在私有成员里（拿不到它去 `glfwSetWindowShouldClose`），但 `ShouldCloseWindow()` 是**虚函数**——子类里加一个自己的标志位就够（`main.cpp` 的 `ClosableAdapter`）。没有这一手，终端的 `q` 就只能 `exit()` 硬退（不跑析构、恢复不了终端）。
3. **站姿文件的默认路径靠"从可执行文件往上找 `scenes/`"**：正常构建（`essential/build/essential_sim`）能找到任务目录；但如果把可执行文件放到别处（比如把对拍脚手架编到 `/tmp` 里跑），就得用 `--stance` 显式指路——否则报错里那句"打不开"会看着莫名其妙。

## 验证

- **A 完整版没被改坏**：加了 `--dump-stance` 之后，与改动前（HEAD）编出来的二进制对拍 14 组 sim 命令，**逐字相同、退出码相同**（CLI 用例只多了新选项那两行用法文字）。
- **B 站姿文件 = 搜索结果**：essential（**加载文件**）与完整版（**搜索**）跑同一组命令 **12 组逐字相同、退出码相同**（`0` 与 `2` 都出现过）——只要站姿有一个比特不同，所有轨迹数字都会漂。上面的「四个改进」改完又重跑了一遍这 12 组（`--start raw|stance|rest|side` × 起身/切回阻尼/回起点再起身 × 改 `kp`/`kd`/`ramp`），结论不变；比对时只排除"完整版 `main.cpp` 独有"的行（`电机模型：…`、脚本预览）与两处措辞本来就不同的日志（`站姿…`），物理数字、状态切换、判定与退出码一个不落。
- **C 终端按键**：在真终端里跑 `essential_sim` 自动喂键（`S` → `R` → `Q`）：起身 1.39 s（与 `docs/sim.md` 的 1.39–1.40 s 一致）、按 `R` 那行措辞与完整版 `start::Reset` **逐字相同**、退出码 0；`13575 步 / 27.150 仿真秒` = 1.00x 实时。
- **D 报错路径**：文件不存在 / 模型指纹不符 / 版本不符 / `q` 个数不对，四条都给出"原因 + 重新生成的命令"，退出码 1。
- **E 生成可复现**：`--dump-stance` 连跑两次逐字节相同，且与入库的 `models/stance.txt` 逐字节相同。

（用管道喂输入测按键是没用的：stdin 不是终端时 raw 模式不启动，程序会明确提示"按不了键"。）
