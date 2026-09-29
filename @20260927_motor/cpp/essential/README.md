# essential：最简版（官方窗口 + 终端按键 + 站姿预存）

> 这是 [`../`](../README.md)（完整版）的精简副本，目标是**一次读懂**这次培训的控制程序：MIT 关节电机 + 两状态机 + 站姿。
> 完整版的实测数字与踩坑在 [`../docs/sim.md`](../docs/sim.md)。

## 与完整版、核心版的差别

与完整版（[`../`](../README.md)）的三处不同：① 窗口用 MuJoCo **官方** Simulate 界面、按键从**终端**读；
② **站姿预先搜好存在文件里**，启动时加载而不是搜索；③ 只留一个模式（没有 `--mode sim/record`）。

**逐项差别表、`essential_core` 那一刀砍了什么、"低站姿"的来历、三个踩坑与"两边行为逐字相同"的验证方法**：
[`../docs/essential.md`](../docs/essential.md)（完整版的实现与全部实测数字在 [`../docs/sim.md`](../docs/sim.md)）。

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

**关于阻尼**：阻尼模式是**我们在控制器里加的**（指令 `kp = 0, kd = kd_damp` ⇒ τ = −kd·q̇），不是靠摩擦或关节自身的被动阻尼。
从模型原姿态起不按 S，基座 z（起步 0.5786 m）实测：`kd_damp = 0` 时 0.5 s 已落到 0.197 m、1.0 s 就趴定（0.1449 m）；
默认 `kd_damp = 0.5` 在 0.5 s 还有 0.277 m、约 2 s 才趴定；`kd_damp = 1.0` 到 4 s 还撑在 0.23 m（腿还有"刚度感"，趴不下去）。

窗口里是官方界面：**空格 = 暂停/继续**（暂停时控制循环也不推进，时间轴重新对齐）、鼠标操作相机、面板能改 `qpos`/`ctrl` 看实时数值；直接关掉窗口同样正常收工。

## 目录（都在 `src/` 下，与完整版的 `cpp/src/` 对齐）

| 文件 | 与 [`../src/`](../src/) 的关系 |
|---|---|
| `main.cpp` | 编排：建官方窗口（主线程 `RenderLoop()`）+ 控制线程（装配 → `Load` → 一步一循环）；**`R` 的"回起点"就写在这里**（那段胶水的理由见 [`../docs/essential.md`](../docs/essential.md) §3） |
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

