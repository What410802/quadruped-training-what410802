# 环境与踩坑记录（本机）

在本机（Linux + Optimus 双显卡：Intel UHD 核显 + NVIDIA MX350）搭建和运行本仓库环境时踩到的坑。 这里既是"踩坑备查"，也是仓库里各项配置的**依据**——改配置前先读对应小节。

相关文档：MuJoCo 本体知识点与坑点见 [`../learn/mujoco.md`](../learn/mujoco.md)（第 7 节讲 `MUJOCO_GL` 与渲染开销，[§7.6](../learn/mujoco.md#76-这些结论驱动了哪些配置决策) 是"结论 → 配置"的反向索引）； 图形栈背景见 [`../learn/graphics-stack.md`](../learn/graphics-stack.md)；编辑器提示的完整方案见 [`../learn/cmake-intellisense.md`](../learn/cmake-intellisense.md)；项目约定见 [`../conventions.md`](../conventions.md)；文档索引见 [`../../README.md`](../../README.md)。

## 环境怎么搭出来（从零复现）

**安装步骤（装 pixi → `pixi install` → 验证）在仓库根 [`README.md`](../../README.md) 的「快速开始」里，不在这里重复。** 本节只记“为什么 / 谁提供”的部分：

- `[dependencies]` 只声明了 5 项：`python=3.12.*`、`mujoco>=3.12.0,<4`、`cxx-compiler`、`cmake`、`ninja`；其余全是它们的依赖自动带进来的。**MuJoCo 的 C++ 头文件、库与 CMake 配置不是我们单独装的**，而是 `mujoco` 这个**元包**（它自己 0 个文件）依赖的 `libmujoco` 提供：`include/mujoco/*.h`、`include/simulate/*.h`、`lib/libmujoco.so`、`lib/libmujoco_simulate.so`、`lib/cmake/mujoco/`；`glfw`、`libgl-devel`、`mujoco-simulate`、`mujoco-samples` 也都是随它进来的。

```bash
# 各项依赖是谁装的（mujoco 是元包，libmujoco 才真正带头文件）
python3 - <<'PY'
import glob, json
for f in sorted(glob.glob('.pixi/envs/default/conda-meta/*mujoco*.json')):
    d = json.load(open(f))
    n = len([x for x in d['files']
             if x.startswith(('include/mujoco', 'lib/libmujoco', 'lib/cmake/mujoco'))])
    print(f"{d['name']:16s} {d['version']:8s} 相关文件 {n:3d} 个")
PY

```

搭环境时踩过的坑（清华镜像 403、镜像不支持 sharded repodata、PyPI 上游达不到 1 MiB/s 所以要保留回退链）见下面各节；任务目录只引用本文，不重复。

**能不能真的从零装全**（2026-09-26 实测）：把仓库 clone 到一个干净目录（新克隆里没有 `.pixi`），只跑 `pixi install`——2 s 就装完（包都在 pixi 本地缓存里，所以没走网络；换一台全新机器会重新下载，耗时见后面镜像一节），随后 `import mujoco` 得到 3.12.0、`include/mujoco/mujoco.h` 与 `lib/libmujoco.so` 都在，Python 侧 `scripts/agent_scripts/rest_check.py` 与 C++ 侧 `cpp_task2`（cmake + ninja 编译后运行）都直接跑通且结论一致（8 s 后末 1 s 漂移 4.440e-10 m、判“静止趴住”）。

## 工具链选择： Pixi = Conda + uv

好处：**Python、MuJoCo（C 库 + Python 绑定）与 C++ 工具链都装在同一个 pixi 环境里**，不用系统 apt 包，也不用单独的 venv。

- **跨语言共用同一份 MuJoCo**：C++ 侧（`cpp_task2/`、`cpp_stand/`、`cpp_slope/`）需要的是 `libmujoco`（头文件 + 库 + CMake 配置）；conda-forge 的 `mujoco` 包同时提供 C 库与 Python 绑定，两边**就是同一个 3.12.0**，行为一致、数字可比（C++/Python 逐项对照就是 C++ 侧的验收方式）。pip/venv 只能拿到 Python 轮子，拿不到配套头文件与 CMake 配置。
- **一次装齐 C++ 工具链**：`cxx-compiler` / `cmake` / `ninja` 都在 conda-forge，与 `libmujoco` 出自同一条工具链，避免“系统 gcc 编、conda 库链接”的 ABI / libstdc++ 错配。
- **可复现**：`pixi.lock` 锁死确切版本与哈希，别人 clone 后 `pixi install` 得到同一个环境，“在我机器上能跑”这件事有据可查。
- **不污染系统**：一切装在仓库内的 `.pixi/`（已 gitignore），不需要 sudo，删掉目录即回滚；系统只负责显卡驱动这类必须由系统管的东西。
- **能承载“必须提前生效”的环境变量**：`MUJOCO_GL` 必须在 `import mujoco` 之前生效（见下面“图形后端”一节），`[activation.env]` 正好解决这件事。
- **两种包源都可用**：conda 侧走 conda-forge（实测直连 conda.anaconda.org 最快，见下一小节），PyPI 侧由内置的 uv 负责，并可用 `extra-index-urls` 配国内回退源。
- 代价：多一层工具（要习惯用 `pixi run` 而不是直接 `python`），且 conda-forge 的 `mujoco` 版本略落后于 PyPI（当前 3.12.0 vs 3.14.0）——对本项目不构成问题。

## 2026-09-24 pixi / conda / PyPI 镜像

本工作区用 `pixi` 统一管理 Python 与 MuJoCo（`pixi.toml` 在仓库根目录）。初始化时遇到下面几个坑，均已处理，记录备查。

**1）清华 TUNA 镜像对本机整体 403（conda 与 pypi 都是）**

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge/linux-64/repodata.json   # 403
curl -s -o /dev/null -w '%{http_code}\n' \
  https://pypi.tuna.tsinghua.edu.cn/simple/mujoco/                                          # 403
```

现象：`pixi search` / `pixi install` 直接失败（`HTTP status client error (403 Forbidden)`）； 只有 `pixi search --no-config ...` 才能绕过配置拿到数据。

- 配置位置是 `~/.pixi/config.toml`（**不是** `~/.config/pixi/config.toml`），原内容把 `conda-forge` / `pytorch` 映射到 TUNA，并把 pypi `index-url` 也指向 TUNA。
- 处理：**删除 `[mirrors]` 段**，pypi `index-url` 改成 USTC。原因见第 2 条。

**2）国内镜像都不支持 sharded repodata，走镜像反而更慢**

conda 的完整 `repodata.json` 是几十 MB；conda.anaconda.org 额外提供 `repodata_shards.msgpack.zst`（linux-64 约 **570 KB**），pixi 会优先用它。实测：

| 源 | `repodata_shards.msgpack.zst` |
|---|---|
| conda.anaconda.org（官方） | **200**，570 KB / 2.3 s |
| USTC | 302（跳 NJU） |
| NJU / aliyun / TUNA | 404 |

所以结论是反直觉的：**conda 侧不用镜像，直连 conda.anaconda.org 最快**。这也顺便解释了 第 1 条里为什么「删掉 mirrors」是正确解法。

**3）PyPI 上游本身达不到 1 MiB/s，所以仍然需要镜像**

同一文件（`mujoco-3.14.0-cp312-...whl`）8~20 s 限时下载实测：

| 源 | 实测速度 |
|---|---|
| files.pythonhosted.org（上游） | 4～21 KB/s |
| USTC | 31～356 KB/s（最快） |
| NJU | 157 KB/s |
| aliyun | 索引 200，但文件路径 404（布局不同） |
| pypi.org | 索引可访问，但 20 s 超时 |

结论：**没有任何一端达到 1 MiB/s**，因此保留镜像；`pixi.toml` 用多索引回退链：

```toml
[pypi-options]
extra-index-urls = [
    "https://mirrors.ustc.edu.cn/pypi/simple",
    "https://mirrors.aliyun.com/pypi/simple",
    "https://mirror.nju.edu.cn/pypi/web/simple",
]
```

- pixi 底层是 uv，**采用 first-index 策略**（不是 pip 的「所有索引一起选最优版本」）： 按顺序取**第一个命中该包**的索引，且 `extra-index-urls` **优先于** `index-url`。 上面 `index-url` 留空 ⇒ 默认 `https://pypi.org/simple` 作为最后兜底。
- 因此 `extra-index-urls` 的顺序 = 优先级顺序，**第一个应该写最快的源**（此处 USTC）。
- 注意 pip/uv 需要的是 PEP 503 的 `.../simple` 路径；`https://mirrors.ustc.edu.cn/pypi/` 会 301，不能直接当 index 用。

**4）其它小坑**

| 问题 | 说明 |
|---|---|
| `pixi add --dry-run` | pixi 0.77.0 **没有**这个参数 |
| `pixi --no-config search ...` | 报 `unexpected argument`；`--no-config` 必须放在**子命令之后**：`pixi search --no-config ...` |
| conda-forge 的 `mujoco` 版本落后 | conda-forge 最高 **3.12.0**，PyPI 已到 **3.14.0**；本项目选 conda-forge 以统一 C++/Python |
| `raw.githubusercontent.com` | 一度超时（curl exit 28）；稍后恢复。URDF 来源用 sha256 校验确认 |
| pixi 识别到 `__cuda=13.0` | 来自驱动 580；但本机 MX350 是 sm_61，**不支持 CUDA 13**，后续装 CUDA 相关包时要注意 |

**测速/验源可复用的命令：**

```bash
# conda 镜像是否支持 sharded repodata（200 才值得用）
curl -s -o /dev/null -w '%{http_code}\n' \
  "$MIRROR/conda-forge/linux-64/repodata_shards.msgpack.zst"

# 真实吞吐（B/s；>= 1048576 才算 1 MiB/s）
curl -s -o /dev/null -m 10 -w '%{http_code} %{speed_download}\n' "$FILE_URL"
```

## 2026-09-24 URDF → MJCF 转换与 git 索引

详见 [`../../@20260923_mujoco/README.md`](../../@20260923_mujoco/README.md)，这里只记最容易再踩的几条：

1. **MuJoCo 自带转换会把根 link 并进 `worldbody`**：没有 `<freejoint/>`，基座的质量惯量也整块丢失（本模型 13.2472 → 7.47 kg），而且只导 `<collision>`、visual mesh 全丢。
2. **urdf.enkeebot.com 的「Include Skeleton」版没有碰撞体**（全部 geom `contype=0 conaffinity=0`），拿它做“趴在地上”会直接穿过地面。
   上面两条的症状、数字与选项组合见 [`../../@20260923_mujoco/docs/model.md`](../../@20260923_mujoco/docs/model.md)（本任务文档），这里只留结论。
3. **同一份 mesh 被复制了 3 份**（原始 URDF、网站导出、旧导出），每份 34 MB 且 md5 完全相同。处理：模型用 `meshdir` 指向 `assets/urdf/meshes` 这一份，其余在 `.gitignore` 里排除。
4. **`.gitignore` 对已经 `git add` 过的文件无效**。重复的 meshes 与已删除的旧 skeleton 仍然留在索引里，必须 `git rm -r --cached <path>` 才能真正排除（磁盘文件不受影响）。
5. **导出模型的默认位形穿模**。urdf.enkeebot.com 把根 body 放在原点，而零位形下脚底在基座下方约 0.58 m ⇒ 任何“建完 `MjData` 直接 `mj_step`”的脚本都会看到求解器把狗弹到空中（场景里的 `<keyframe>` 不会被自动加载）。两条修法：把模型基座默认高度抬到“脚底刚好触地”（推荐，模型自洽），或在脚本里`mj_resetDataKeyframe(model, data, 0)` / 显式设 `data.qpos[2]`。
6. **`<include>` 之后 `meshdir` 是相对顶层文件解析的**。scene 与模型分目录时，模型里的`meshdir="meshes/"` 会去 scene 所在目录找 `meshes/`（删掉软链接后的报错原文：`Error opening file 'meshes/@20260927_motor/models/trunk.STL'`），而同一模型单独加载却正常。做法：**顶层场景**自己在 `<include>` 之后写一行 `<compiler meshdir="../models/meshes"/>`（多个 `<compiler>` 里后写的覆盖先写的，所以写在 include 之前会被模型那份盖回去）；被直接当顶层加载的模型目录（`models/`、`assets/black_description/`）仍各留一个 `meshes` 目录软链接。`scenes/meshes` 两个软链接已按此删除（2026-09-27），复现与规则见 [`../learn/mujoco.md`](../learn/mujoco.md) §6.1。

> MuJoCo 知识点（`geom` 的 `type` 取值、`friction` / `condim` 语法与默认值、接触参数速查） 见 [`../learn/mujoco.md`](../learn/mujoco.md)。

## 2026-09-25 图形后端 / GPU / 渲染性能（本机实测）

> 数据与复现方式见 [`../learn/mujoco.md`](../learn/mujoco.md) 第 6、7 节， 图形栈背景见 [`../learn/graphics-stack.md`](../learn/graphics-stack.md)。

- 本机是 **Optimus 双显卡**（Intel UHD 核显负责显示 + NVIDIA MX350 2 GB 独显），实测 **`MUJOCO_GL` 会决定用哪块卡**：
  * `egl` → 离屏 context 落在 **NVIDIA MX350**（GL 4.6，max texture 32768）；
  * `glfw` → 走“显示的 GL”，即 **Intel 核显**（Mesa 23.2.1，max texture 16384）。

  所以两侧的性能差异**首先是 GPU 差异**，不是后端本身的开销。
- 渲染成本（960×540，同一套代码）：MX350 出一帧 ~5.5 ms、整条录像链路 ~7.1 ms； 核显则分别是 ~21 ms / ~22 ms（50 fps 录像要 ~111% CPU，跟不上）。
- 仓库把 `MUJOCO_GL=egl` 写进 `pixi.toml` 的 `[activation.env]`，对所有脚本生效； 临时换后端要 `pixi run env MUJOCO_GL=glfw python …`（命令行前缀会被激活环境覆盖）。
- 本机显卡算力（Pascal sm_61 + 驱动 580）**不够跑 MJX / MJWarp**，所以只用 CPU 仿真。
- 本机特有的小现象：开窗口的进程退出时偶发 `segmentation fault` 或 `GLFWError: EGL: Failed to clear current context`（MP4 在崩溃前已写完，产物不受影响）； Wayland/XWayland 会把 GLFW 的窗口位置警告打到 stderr。
- **离屏渲染的帧尺寸由模型的 `<visual><global offwidth/offheight>` 决定，不是请求尺寸，也不是窗口尺寸**（默认 640×480；本任务场景声明的是 1280×720）。以前 `cpp_task2/src/record.h` 没动这两个字段，于是离屏 buffer 一直是场景声明的 1280×720，再把 1280×720 的帧按请求的 960×540 喂给 ffmpeg，帧就错位（现象：写进 191 帧的 raw 流被 ffmpeg 读成 339 帧、时长 6.78 s）。现在 recorder 在 `mjr_makeContext` **之前**把 `offwidth/offheight` 设成输出尺寸（Python 侧 `VideoRecorder` 一直这么做），实测 960×540 / 1920×1080 / 3840×2160 三档的视口与输出尺寸逐项一致、ffprobe 实测分辨率也对得上，`vflip` 后面不再需要 `scale`；只有驱动把视口夹小时才回退到"按实际视口读 + scale 到输出"（`mjr_maxViewport` 仍是每帧字节数的唯一依据）。
- **录像链路的开销量级**（`cpp_slope --mode record --pitch 15 --seconds 5`，251 帧 / 5 仿真秒，`egl`→MX350）：960×540 → 9.8–13.3 s（39–53 ms/帧）、1920×1080 → 17.8–19.8 s（71–79 ms/帧）、3840×2160 → 50.8 s（202 ms/帧）。三个数都受**机器负载**影响（测时负载均值 ~8，同一命令重复跑能差 30%），量级参考就行。录像**不是实时的**，但这不影响产物：MP4 的时间轴按**仿真时间**走，与机器快慢无关，分辨率越高只是录得越慢。
- 这些结论**驱动了哪些配置**（反向索引）：见 [`../learn/mujoco.md` 第 7.6 节](../learn/mujoco.md#76-这些结论驱动了哪些配置决策)。

## 2026-09-25 C++ 工具链（pixi 提供）与编辑器提示

> 用途与任务背景见 [`../../@20260923_mujoco/README.md`](../../@20260923_mujoco/README.md) 的「C++ 程序」一节。

- **用 pixi 的编译器，不用系统 gcc**：conda-forge 的 `libmujoco` 是 conda 工具链编出来的，混搭系统 gcc 容易踩 ABI / libstdc++ 版本问题，所以 `cxx-compiler` / `cmake` / `ninja` 都装进同一个 env（本机实测 gcc 15.3.0 / cmake 4.4.3 / ninja 1.13.2）。
- conda 的 `mujoco` 包**已经带齐 C++ 需要的东西**：`include/mujoco/*.h`、`libmujoco.so`、`lib/cmake/mujoco/mujocoConfig.cmake`（目标 `mujoco::mujoco` 与 `mujoco::libmujoco_simulate`），所以既不用自带 MuJoCo 源码，也不用宇树 readme 里那套“下载官方包解压到 `~/.mujoco` 再 `ln -s`”。
- 配置时把 `-DCMAKE_PREFIX_PATH="$CONDA_PREFIX"` 传进去即可，`find_package(mujoco)` 就能找到上面的 CMake 配置。
- **换 C++ 不会更快**：`mj_step` 两边调的是同一份 C 库，本机实测 C++ 循环 0.0394 ms/步、Python 0.04 ms/步；渲染依旧是 5.5 ms/帧（由 GPU 决定）。
- **编辑器（clangd）要配 `--query-driver`**：CMake 把 `$CONDA_PREFIX/include` 当作“隐式包含目录”而**不写进** `compile_commands.json`，clangd 于是找不到 `mujoco/mujoco.h`、也拿不到 conda 的 libstdc++ 头，满屏标红（一次自检可报出 21 条错误）。让 clangd 去问 pixi 的编译器即可消除：`--query-driver=**/.pixi/envs/*/bin/*`（glob 必须 `**/` 开头，实测不带就匹配不上）。排查工具：`clangd --check=<file>`，它打印的就是编辑器同源的诊断。
- **上面这个参数要写到哪个文件，取决于 VSCode 本身是怎么打开的**：VSCode clangd 扩展把 `clangd.arguments` / `clangd.path` 声明为 **window scope**。用**多根工作区**（本机同级的 `RoboCon.code-workspace`，不入库）打开时，window 级设置只认工作区文件 / 用户设置，写在文件夹级 `.vscode/settings.json` 里不生效；**单独打开仓库文件夹**时，`.vscode/settings.json` 本身就是工作区设置，写在这里才生效。Agent 要测试的话，如果 `ps -eo args | grep clangd` 只看到 `/usr/bin/clangd`，clangd 进程参数为空，那么是单独打开仓库文件夹。单独打开仓库文件夹时，读取 [`../../.vscode/settings.json`](../../.vscode/settings.json)；多根工作区时要把同样两项抄进工作区文件。
- 改完要重启语言服务器（命令面板 → `clangd: Restart language server`），否则跑的还是旧进程；想确认可以直接看进程参数：`ps -eo args | grep clangd`。
- clangd 把索引缓存写在 `<project>/.cache/clangd/`（它把含 `compile_commands.json` 的上级目录当作 project），已加进 `.gitignore`。

### 2026-10-08 系统的 clangd 14 读不了 gcc 15 的头：改用环境里的 clangd 23

**现象**：`@20261007_assignment` 的 `rl_sim.hpp`、`rl_sdk.cpp` 打开就标红（`'torch/script.h' file not found`、`no member named 'value' in 'std::is_same<…>'` 等），命令行编译却是好的。

**原因**：编辑器跑的是系统 apt 的 `/usr/bin/clangd`（14.0.0），有两层问题：

1. 没有 `--query-driver`（参数没生效，见上一条）：clangd 用系统 gcc 11 的 libstdc++ 头去解析为 gcc 15 写的头，模板一路报错；`$CONDA_PREFIX/include`（`torch/script.h` 就在这里）也不在搜索路径里。
2. 加上 `--query-driver` 也不行：clangd 14 读 gcc 15 的 `ia32intrin.h` 时直接报 `definition of builtin function '__rdtsc'`，然后 `too many errors` 停掉。clangd 的版本必须新到能读懂这套工具链的头。

**做法**：根 `pixi.toml` 加 `clang-tools = "23.*"`（clangd、clang-format 等）与 `clang-23 = "23.*"`（只为它带的 `lib/clang/23/include`，即 clangd 的内建头目录；没有它，clangd 报 `Failed to auto-detect resource directory`）。`.vscode/settings.json` 里用 `"clangd.path": "${workspaceFolder}/.pixi/envs/default/bin/clangd"` 指过去，并保留 `--query-driver`。改完执行 `clangd: Restart language server`；VSCode 若提示"工作区要设置 clangd.path"，选允许。clangd 没有单独的 conda 包，`clang-tools` 又固定依赖同版本的 `clang-format`，所以环境里的 clang-format 也随之变成 23（见本节最后一条）。

**头文件借错命令**：头文件不在 `compile_commands.json` 里，clangd 要"借"一个源文件的命令来解析。`@20261005_ros2` 的包的编译库里混着二十多条 rosidl 生成文件，`motor.hpp` 按名字相似度借到了 `motor_state__type_support.cpp`，那条命令既没有本包的 `include/`，标准也是 `gnu++14`。修法是在包目录放一份 `.clangd` 补上 `-I` 与 `-std=c++17`，见 [`../../@20261005_ros2/ws/src/quadruped_ros2/.clangd`](../../@20261005_ros2/ws/src/quadruped_ros2/.clangd)。`clangd --check` 不建后台索引，对头文件的判断比编辑器更悲观；要看编辑器里的真实结果，得像编辑器一样用 LSP 打开文件。

**实测**（以 LSP 方式打开文件、等后台索引稳定后数 error 级诊断；clangd 14 那一列与 VSCode「问题」面板里的数一致，例如 `rl_sim.hpp` 都是 8 条）：

| 文件 | 系统 clangd 14（无参数，原状） | 环境 clangd 23 + `--query-driver` + `.clangd` |
|---|---|---|
| `rl_sar/include/rl_sim.hpp` | 8 | 0 |
| `rl_sar/library/core/rl_sdk/rl_sdk.cpp` | 20 | 0 |
| `rl_sar/library/core/rl_sdk/rl_sdk.hpp` | 20 | 0 |
| `rl_sar/src/rl_sim.cpp` | 17 | 0 |
| `rl_sar/policy/black/fsm.hpp` | 6 | 0 |
| `quadruped_ros2/include/quadruped_ros2/motor.hpp` | 17 | 0（不加 `.clangd` 是 13） |
| `quadruped_ros2/include/quadruped_ros2/viewer.hpp` | 18 | 0 |
| 两个 ROS 包的全部 16 个 C/C++ 文件 | — | 全部 0 |
| 早先任务抽查 8 个文件（`@20260927_motor/cpp`、`@20260923_mujoco/cpp_*`、`@20261005_ros2_example` 等） | 6 个有错 | 7 个为 0；剩下的 `mini_robot/src/robot.cpp` 是它的 `build/compile_commands.json` 过期（还指向改名前的 `@20260923_robot_cpp_training/`），与 clangd 版本无关，重新 configure 那个工程即可 |

**clang-format 也跟着变成 23**：环境里的 clang-format 23 与系统 `/usr/bin/clang-format` 14 对同一份 `.clang-format` 的结果不完全一样。对 100 个已入库的 C/C++ 文件，14 会改动 56 个，23 会改动 60 个；两者结果不同的有 14 个（4 个只有 23 会改，10 个两者都改但改法不同），主要差在行尾注释的对齐（23 会把相邻几行的 `///<` 注释对齐到同一列）。编辑器里的"格式化文档"走的是 clangd 内置的同版本格式化，所以现在是 23；命令行要与它一致，就用环境里的那份（`pixi run clang-format -i <file>`，或激活环境后直接 `clang-format`）。

## 2026-09-25 复现上游 unitree_mujoco（C++ 与 Python 两条路线）

> 用途与任务背景见 [`../../@20260923_mujoco/README.md`](../../@20260923_mujoco/README.md) 的「复现上游参考实现」一节；复现解决的那个疑问（`LowCmd` 回调归属）见 [`../learn/runtime-timing.md`](../learn/runtime-timing.md) §10。两个自建环境都不入库，放在工作区同级目录 `Replicate.d/`：`unitree_mujoco/{python,cpp}/` 各一个 pixi 环境，与环境、版本无关的 SDK 放顶层 `Replicate.d/unitree_sdk2/` 共用。

- **两条路线各自单独建环境，不动任务主环境**。Python 侧必须 `python=3.10`：`unitree_sdk2_python/setup.py` 钉死 `cyclonedds==0.10.2`，而该版本只发布了 **cp310** 轮子，cp311/cp312 都是 0 个（`curl -s https://mirrors.ustc.edu.cn/pypi/simple/cyclonedds/ | grep -c 'cyclonedds-0.10.2.*cp312'` → `0`），在 3.12 上只能源码编 Cyclone DDS。C++ 侧不能复用主环境：官方包里的 `libmujoco.so` 会和 conda 的 `mujoco` 撞车。
- **旧 `opencv-python` 与 numpy 2 不兼容**：pip 那份 `opencv-python 4.5.5` 是按 numpy 1.x ABI 编的，在 numpy 2.2.6 下 `import cv2` 报 `numpy.core.multiarray failed to import`；把 numpy 钉到 `1.26` 即可（也符合该 SDK 的年代）。
- **C++ 路线必须另下官方 MuJoCo 发布包**：conda 的 `mujoco` 只有头文件，而 `simulate/CMakeLists.txt:25` 的 `file(GLOB …)` 要**编 `mujoco/simulate/{glfw_*,platform_*,simulate}.cc`** 这些示例源码，所以 `Replicate.d/mujoco-3.12.0/`（与 conda 同版本）免不了。
- **`unitree_sdk2` 不用自己编 Cyclone DDS、也不用 sudo**：仓库自带预编译 `lib/x86_64/libunitree_sdk2.a` 与 `thirdparty/{include,lib}` 里的 ddsc/ddscxx，`cmake --install` 到 `Replicate.d/unitree_sdk2` 即可；上游硬编码的 `/opt/unitree_robotics/lib/cmake` 是用 `list(APPEND …)` 加的（`simulate/CMakeLists.txt:12`），命令行传 `-DCMAKE_PREFIX_PATH=<install>/lib/cmake` 就能盖过它。
- **编上游 `simulate` 还差两个 conda 依赖**：glfw 的头文件 `#include <GL/gl.h>` → 需要 `libgl-devel`（conda 编译器不搜系统 `/usr/include`，即使系统装了 `libgl-dev` 也没用）；SDK 的 `include/unitree/dds_wrapper/robots/go2/go2_sub.h:7` 有 `#include <eigen3/Eigen/Dense>` → 需要 `eigen`。
- **上游按可执行文件位置找配置与场景**：`simulate/src/main.cc:683` 是 `proj_dir = getExecutableDir().parent_path()`，即要求可执行文件正好在 `simulate/` 下一层，然后读 `proj_dir/config.yaml`、场景取 `proj_dir.parent_path()/unitree_robots/<robot>/<scene.xml>`（`:684`、`:687`）。把构建目录放到 `Replicate.d` 后，用软链接补齐这套相对位置即可，参考克隆里只加一个 `simulate/mujoco → Replicate.d/mujoco-3.12.0`。
- **回环网卡上的 DDS 会打印 `selected interface "lo" is not multicast-capable: disabling multicast`**：`lo` 没有多播，属正常，单机通信仍走单播。
- **Python 侧启动前要改两个运行时条件**（不改参考源码，用启动器覆盖）：`USE_JOYSTICK = 1` 在本机没有手柄（无 `/dev/input/js*`）时会失败；`ROBOT_SCENE` 是相对路径、依赖 cwd。两者都在 `Replicate.d/unitree_mujoco/python/run_sim.py` 里改，该脚本同时负责打印线程清单与回调线程。
- **被动 viewer 需要真实窗口**：Python 侧得 `MUJOCO_GL=glfw`（主环境默认是 `egl`，无窗口）；本机 Wayland 会话下会有一条 `GLFWError: (65548) Wayland: The platform does not provide the window position` 警告，不影响显示。
- **退出阶段会段错误**：Python 侧两次复现，`viewer.close()` 之后进程以 `segmentation fault (core dumped)` 收场——上游退出路径本身缺同步，不影响前面的运行。

复现时要敲的关键命令（在 `Replicate.d/unitree_mujoco/{python,cpp}` 下执行，两个环境各自 `pixi install` 一次）。下面是**本机实际敲过的命令**，只把两处仓库之外的只读资源换成了变量（`REF` = 只读材料里的 `unitree_mujoco`，`SDK`/`MJ` = 复现环境里的 SDK 与官方 MuJoCo 包），具体路径按自己的机器填，仓库里不写：

三样东西**都不在仓库里，要自己准备**（别指望哪来的现成副本）：

| 变量 | 是什么 | 怎么拿 |
|---|---|---|
| `REF` | 上游仿真器源码 | `git clone https://github.com/unitreerobotics/unitree_mujoco`（BSD-3-Clause；本轮用 commit `1eb6642`） |
| `SDK` | `unitree_sdk2`（DDS 通信库） | `git clone https://github.com/unitreerobotics/unitree_sdk2`（自带上游预编译 `lib/x86_64/libunitree_sdk2.a`，**不用**自己编 Cyclone DDS） |
| `MJ` | 官方 MuJoCo **3.12.0** 发布包 | 到 <https://github.com/google-deepmind/mujoco/releases> 下 `mujoco-3.12.0-linux-x86_64.tar.gz` 解开即可（conda 的 `mujoco` 只有头文件，编不了上游 `simulate/`） |

```bash
REF=<unitree_mujoco 的路径>
# Python：仿真器（探针在启动器里，会打印线程清单与 LowCmd 回调所在线程）
pixi run python run_sim.py                 # 加 --seconds 10 可自动关窗退出
# 控制器另开终端（回车开始，无限循环）
printf '\n' | pixi run python "$REF/example/python/stand_go2.py"

# C++：编上游仿真器与控制器（SDK 安装前缀与官方 MuJoCo 包按上面两条准备）
SDK=<unitree_sdk2 的路径> ; MJ=<官方 MuJoCo 3.12.0 发布包的路径>
cmake -S "$REF/simulate" -B build -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_PREFIX_PATH="$SDK/lib/cmake;$CONDA_PREFIX" \
  -DCMAKE_EXE_LINKER_FLAGS="-L$CONDA_PREFIX/lib -L$MJ/lib -L$SDK/lib -Wl,-rpath,$CONDA_PREFIX/lib -Wl,-rpath,$MJ/lib -Wl,-rpath,$SDK/lib"
cmake --build build --target unitree_mujoco -j8
cmake -S "$REF/example/cpp" -B build-stand -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH="$SDK/lib/cmake;$CONDA_PREFIX"
cmake --build build-stand -j8
# 跑：仿真器（带官方 Simulate 界面）+ 控制器（另开终端，回车开始）
LD_LIBRARY_PATH="$CONDA_PREFIX/lib:$SDK/lib:$MJ/lib" ./build/unitree_mujoco
LD_LIBRARY_PATH="$CONDA_PREFIX/lib:$SDK/lib" ./build-stand/stand_go2
```

两边的运行结果（基座高度采样）见 [`../../@20260923_mujoco/README.md`](../../@20260923_mujoco/README.md) 的「复现上游参考实现」一节。

## 2026-10-07 conda 里的 Qt 程序（rqt 等）：平台插件缺 wayland、图标主题取不到

**两条现象**（都在 rqt_graph 上复现，KDE/Wayland 本机）：

1. 启动打一行 `Could not find the Qt platform plugin "wayland" in ""`，然后照常起来（退回 XWayland）；
2. 界面里**所有工具栏按钮都是空白**（鼠标悬浮有 tooltip），dock 标题栏退化成 `D` / `R` / `X` 这类字母兜底。

**① 平台插件**：rqt 是 **Qt5**（PyQt5），而环境里原先只装了 `qt6-wayland`；conda 的 qt5 编译默认平台是 wayland，找不到插件就退回 xcb 并告警。修法是补 Qt5 的那份：`pixi add qt-wayland`（conda-forge，5.15.15，约 1 MB）——实测装完 `QApplication.platformName()` 就是 `wayland`，告警消失（[`pixi.toml`](../../pixi.toml) 已加）。

**② 图标取不到**：不是"Wayland 的锅"，是**搜索路径被 rqt 自己冻结**。`qt_gui/main.py` 的 `_set_theme_if_necessary()` 在 `QApplication` **创建之前**就调 `QIcon.setThemeSearchPaths()`，而那时 Qt 的默认列表只有 `[':/icons']` —— 宿主（`XDG_DATA_DIRS` / `~/.local/share/icons`）的目录**永远进不来**。冻结后的列表是：

```text
['<env>/share/tango_icons_vendor/resource/icons', ':/icons', '<env>/share/icons/']
```

而这两个能进去的目录都不给力：`adwaita-icon-theme 51` 只带 `*-symbolic.svg`（rqt 找的是 `view-refresh`、`document-open` 这类老名字），`ros-humble-tango-icons-vendor` 那个路径**根本不存在**（实测该 conda 包只装了 ament/cmake 元数据共 15 个文件，**一个图标文件都没有**，属打包缺口）。于是 `QIcon.fromTheme(...)` 全部返回空图标 → 按钮空白。

**怎么量**（不需要截屏工具）：在真实进程里把窗口抓成图并遍历按钮，注意 rqt 的工具栏按钮**本来就只画图标、不写字**（文字在 tooltip）：

```python
# 让 rqt 的 QApplication.exec_ 在启动 N 秒后执行这段，再 QApplication.quit()
for b in window.findChildren(QAbstractButton):
    print(b.toolTip(), b.icon().isNull(), b.icon().availableSizes()[:1])
```

**兜底（本地有效、不入库）**：把宿主的完整图标主题软链进环境的搜索路径，`fromTheme` 立刻能取到：

```bash
ln -s /usr/share/icons/Tango "$CONDA_PREFIX/share/icons/Tango"    # 实测 6/6 图标都出来（含 image）
ln -s /usr/share/icons/breeze "$CONDA_PREFIX/share/icons/breeze"  # 5/6：image 仍缺
```

`image` 这个空按钮是**上游**的问题：rqt_graph 要的是 `QIcon.fromTheme('image')`，而 Adwaita / breeze / hicolor 里都没有这个名字（正确写法应是 `image-x-generic`）。另外 `breeze-icons` / `gnome-icon-theme` 在本仓库用的两个通道（`robostack-humble` + `conda-forge`）里都没有候选，所以没写进 `pixi.toml`；**重建环境后软链会被清掉，需要重做**。

## 2026-09-29 管道（`| tee`）让程序输出变"卡顿"：`stdbuf -oL`

**症状**：给命令接了 `2>&1 | tee log.txt`（实机日志留档）之后，终端不再逐行刷新——要攒一大段才出现一次， 而且经常从半行中间断开；不接 `tee` 时一切正常。实机调零/手转那些"看着读数变化"的操作因此很难受。

**原因**：stdio 的缓冲策略跟着"stdout 是不是终端"变。接了管道/重定向之后，C 库把 stdout 从**按行缓冲** （`\n` 就刷）改成**按块缓冲**（4 KB 才刷一次）⇒ 输出要么攒满一块、要么等进程退出才出来。 `tee` 本身**没有**解缓冲的选项（GNU coreutils 的 tee 只有 `-a/-i/-p/--output-error`；`grep --line-buffered` 那类是每个程序自己的开关，不能通用）。

**修法**：把**生产端**改成行缓冲——`stdbuf` 通过 `LD_PRELOAD` 改 libc 的缓冲模式：

```bash
stdbuf -oL <程序> | tee log            # ✅ 每行立刻刷
sudo stdbuf -oL <程序> | tee log       # ✅ sudo 要放在 stdbuf 前面（反过来 sudo 会清掉 LD_PRELOAD）
stdbuf -oL sudo <程序> | tee log       # ❌ 无效
```

**实测**（本机，一个每 0.4 s 打一行、不调用 `fflush` 的小程序）：

| 场景 | 4 行到达时刻 |
|---|---|
| `./slow \| while read …`（管道，无 stdbuf） | 全部挤在进程结束时（11 ms 内 4 行一起到） |
| `stdbuf -oL ./slow \| while read …` | 0.4 s 均匀间隔（56.878 / 57.279 / 57.680 / 58.080 s） |

**要记住的两点**：① 这是"程序的 stdout 不是终端"造成的，跟 `tee` 关系不大——任何重定向/管道都一样； ② 交互式程序（读 stdin 的那种）用 `stdbuf -oL` 只改 stdout/stderr，**stdin 仍是终端**，键盘输入不受影响。

**落到本仓库**：实机命令统一走 `@20260927_motor/scripts/run_log.sh`（用法与理由见 `@20260927_motor/cpp_part2_remake/docs/runbook.md` §4；初版说明在历史版本 `@20260927_motor/cpp_part2/docs/runbook.md` §2） （`sudo stdbuf -oL … | tee`，按时间戳自动命名日志；`sudo` 写在脚本外面）。

## 2026-10-08 libtorch / pytorch：锁 CPU 的 generic 构建

**现象**：在 `pixi.toml` 里直接写 `libtorch = "*"`，pixi 会解析到 **CUDA 构建**（`libtorch-2.13.0-cuda129_mkl_…`，单包 779.61 MiB，另拉一整套 `cuda-*` 运行库）。原因是本机有 NVIDIA 显卡，pixi 探测到虚拟包 `__cuda=13.0`（`pixi info` 的 Virtual packages 一栏），带 CUDA 的构建就优先了。本机那块 MX350 是 `__cuda_arch=6.1`，新版 CUDA 构建未必还支持它；而且我们只在 CPU 上跑小网络，根本用不到。

**做法**：用 build 字符串锁 CPU 构建，并且挑 **generic**（不是 `cpu_mkl`）：

```toml
libtorch = { version = "*", build = "cpu_generic*" }
pytorch = { version = "*", build = "cpu_generic*" }   # Python 侧要用 torch 时再加，同一份底层库
```

`cpu_mkl` 构建要求 `libblas * *mkl`，会把**整个环境**的 BLAS（numpy 等都在用）从 openblas 换成 MKL；generic 构建只要求 `libblas >=3.9`，沿用环境里已有的 openblas。查可选构建的命令：`pixi search 'libtorch[build=cpu_generic*]' -p linux-64 -l 12`。

**解出来的结果与副作用**（`pixi lock` 的输出，2026-10-08）：

| 包 | 变化 | 说明 |
|---|---|---|
| `libtorch` | + 2.12.0 `cpu_generic` | 最新是 2.13.0，但它要 `libabseil 20260526`，环境里被锁在 20260107，求解器退到 2.12.0 |
| `_openmp_mutex` | `20_gnu` → `8_kmp_llvm` | libtorch 要 LLVM 的 OpenMP 运行库；全环境的 OpenMP 从 libgomp 换成 llvm-openmp |
| `libopenblas` | `pthreads` → `openmp` 变体 | 跟着 OpenMP 换 |
| `pytorch` | + 2.12.0 `cpu_generic_py312` | 24.49 MiB，与 libtorch 共用底层库 |

OpenMP 换了运行库之后，回归过 `@20261005_ros2` 的无头自检（`check_headless.py` 全部通过，末态 z 仍是 0.3836 m、实时率 1.000x）。

**一处源码兼容**：libtorch 2.x 的 `torch/script.h` 不再顺带包含 `torch::set_num_threads` 的声明，老代码（如 rl_sar）要补一行 `#include <torch/utils.h>`，否则报 `'set_num_threads' is not a member of 'torch'`。

**验证**：

```bash
pixi run bash -c 'ls $CONDA_PREFIX/share/cmake/Torch/TorchConfig.cmake'   # CMake 找得到 Torch
pixi run python -c "import torch; print(torch.__version__, torch.cuda.is_available())"   # 2.12.0 False
```

用到它的任务：[`../../@20261007_assignment/`](../../@20261007_assignment/README.md)（rl_sar 用 libtorch 跑策略；参考实现用 Python 的 torch）。
