# 地形与资源：盘点、尺寸依据、mjlab 映射

> **2026-10-21 校准**：培训方 `队内赛.pdf` 是当前任务真值（2026-11-04 队内赛：障碍赛 + 越障能力测试），见 [`../reference/team-race-2026.md`](../reference/team-race-2026.md)。本文件下面的 2026 V2.0 / 2027 条目仅作尺寸/素材参考，不再作为官方验收入口；正式障碍场/能力场要以 PDF 图 1–4 和培训方后续文件为准。

## 1. 手头材料（只读材料，按名称引用）

| 材料 | 内容 | 指纹 / 规模 | 本任务的用途 |
|---|---|---|---|
| `terrain.zip` | 单位置“运动能力测试场”：`terrain/map.xml` + 85 张难度标签 + `go1.xml`/`black.xml` 两个包装场景；unitree 场景布局（`robot/<robot>/xmls` + `scene/terrain/`） | 1,966,035 B，sha256 `1419607a4458b889602a1d6b692ed97af72179c28f95ff141f0e5738f1b98fb0`；map.xml 约 920 个 geom、87 个纹理，含沙地/坡/台阶/沟/碎石/桥/低摩擦等车道 | 能力评测套件（逐车道扫）；训练地形在 mjlab 中**重建**，不直接把 map.xml 塞进训练环境 |
| `scene_terrain.xml` | unitree go2w 模板改出的组合地形 playground：限高杆、高墙、绕杆、木桥、沟/桥墩、10×30 楼梯，外加 unitree 生成的斜坡/台阶/随机石块/两块 hfield | 15,442 B，sha256 `9da48640d354ba8b360fcf57e4e26d66f19a58bca19bc4d57bee4aaa1085ae29`；补齐 black 模型与两张 hfield 后 179 geom、nq=19 | 单障碍逐项评测（playground）；尺寸与 2026 规则做对照 |
| `scene_terrain (1).xml`（2026-10-20 培训方更新） | 新版 `blackW RC_MAP scene`：30cm 高墙、砂砾碎木坑、限高杆、1m×1m 出发区、T 字形 10cm 级高台阶（含最高平台/下台阶/连地台阶）、斜坡木桥 A/B、10° 斜坡（4m/3m 两段）、绕杆、5cm 台阶、其他障碍；共 151 个 geom | 28,070 B，sha256 `730ccebd2c400720ca50eb000afc7cd0791f7484957c25ca18b9eb3816a4a6d0`；`<include file="blackW_description.xml"/>`；hfield 依赖 `../../black/height_field.png`、`../../black/unitree_hfield.png` | 2026 正式场地的更新版几何/布局参考；`blackW_description.xml` 在只读 `quadruped_control/assets/robots/blackW/mujoco/`，两个 hfield PNG 可从只读 `unitree_mujoco/unitree_robots/go2w/` 取；需拷到临时目录按原相对路径摆放，暂不复制入库 |
| 2026 官方规则 V2.0 + 场地图册 | 障碍赛 14×6 m、210 s、8 障碍；手动列 100 分/障碍、返回启动区 +100（满分 900）；各障碍的结构/尺寸 | 规则与图册为官方 PDF（本机只读材料；官网与 LocoWiki 均有） | 正式场地建模与手动计分的**权威依据**；V2.0 相对 V1.0 的差异见 §2 |
| 2027 规则 V1.0 | 下一届障碍集：绕桩、限高框架、高墙、沟壑组合、砖木坑、轮胎阵、梅花桩、单木桥 | 官方 PDF（本机只读材料） | 台阶/梅花桩目标的尺寸依据（§3） |
| `Ruixi-Cheng/26RC_Field` | 2026 场地三维 SolidWorks：单场地 + 双场地镜像拼图，零件含 坑、斜坡、木桥 A/B、竖杆、限高杆、高墙、T 字形台阶（README 注明砂砾碎木坑与材料标定待补） | MIT 许可；GitHub 公开仓库 | 建 2026 正式场地的几何参考（转 MJCF/提取轮廓） |
| `Zbszbszbssca/RC_MAP` | 一份 2026 仿生足式场地的 MuJoCo `scene_terrain.xml`（高墙/砂砾坑/限高杆/出发区/T 楼梯/斜坡/木桥/绕杆 + 训练附加地形） | **无许可证**；GitHub 公开仓库 | 只做几何/布局交叉校验，不复制资产、不入库 |
| 队内 `nav` 仓库的 2026 场地资产 | `scene_robocon.xml`（双场地 CAD，212 geom）、`scene_obstacle_rule.xml`、俯视地图、左右场航点 | 队内仓库（N-W-wolf），可访问但按只读材料对待 | 2026 实际赛场的第二份交叉校验；航点可用于评测命令层 |
| 训练仓库 | 队内 `nwwolf_mjlab_training_release`（mjlab 1.6.0，`black-flat`/`black-rough` 任务） | 公开 GitHub；训练侧代码来源 | 训练地形与课程改在这里（不在本任务重写） |

## 2. 2026 官方场地（V2.0）要点（建模依据）

- 场地 14,000 × 6,000 mm；8 个障碍：直角绕杆、砂砾碎木坑、高墙、限高杆、大斜坡、木桥 A、木桥 B、T 字形台阶；具体排列与安装位置赛前公布；两个启动区（地面、T 字形台阶顶）。
- 关键尺寸（V1.0 表 1 + V2.0 修订）：高墙 1000 × 300 × 50 mm；限高杆横杆长 1000 mm、底部离地 300 mm；T 字形台阶总长 2800、宽 1900、高 400 mm，台阶深 320 mm/高 120 mm（顶部平台为可选启动区）；大斜坡总宽 2000、长 3000、角度 **11.3°**（V2.0 由 10° 修订），两侧小斜坡高 200 mm/14°；直角绕杆竖杆高 ≥500 mm、间距 1000 mm、必达区 φ350 mm（V2.0 改红色虚线圆）；砂砾碎木坑 L 形、宽 1000 mm、护栏/木槛高 150 mm、深约 100 mm；木桥 A/B 详见场地图册。
- 手动列计分：8 × 100 + 返回启动区 100 = **900 满分**；越障成功判定按规则表 2（例如 T 字形台阶要求每级台阶顶面与足底至少接触一次、木桥要求从一侧平台经桥到另一侧平台、大斜坡要求两侧各沿 3 m 长边行走 ≥1 m）。
- 建模流程建议：先用规则/图册尺寸在中国 MJCF 里搭简化场（box/cylinder 为主）→ 用 `26RC_Field` 的 SolidWorks 轮廓核对关键位置 → 用队内 `scene_robocon.xml` 与 `RC_MAP` 交叉校验 → 最后把判定区域/启动区/返回区写成评测器配置。

## 3. 台阶与梅花桩的尺寸依据

- 台阶：2026 的 T 字形台阶（总高 400、级高 120/级深 320、宽 1900、长 2800）是首选目标；2027 的沟壑组合还包含 **级高 120/级深 320/宽 800** 的台阶段、平台高 360、沟壑宽 360、20° 斜坡。
- 梅花桩（2027 规则）：**200 × 200 × 200 mm** 方块交错布置；两侧为 800 × 800 × 200 mm 平台；两排首个方块与平台的距离分别为 100 mm、400 mm；上下两排方块间距 200 mm；同一排两方块间距 400 mm；整体中心对称。若任务书用的是 2026 之外的变体，以任务书为准并在评测器里参数化。
- 单木桥（2027）：3000 × 400 × 100 mm，可作为后续窄桥/高级地形扩展。

## 4. mjlab 地形映射（训练侧）

mjlab 1.6.0 原生地形类（`src/mjlab/terrains/{primitive,heightfield}_terrains.py`）与本任务目标的对应关系：

| 目标地形 | 现成类 | 需要自写/组合的部分 |
|---|---|---|
| 平地 | `BoxFlatTerrainCfg` | 无 |
| 光滑/缓坡 | `HfPyramidSlopedTerrainCfg` | 无 |
| 粗糙地 | `HfRandomUniformTerrainCfg`、`HfPerlinNoiseTerrainCfg` | 无 |
| 碎石/砂砾 | `HfRandomUniformTerrainCfg`（粗尺度）或 `BoxRandomSpreadTerrainCfg` | 更贴近碎石的 box 混合地形（自定义 `SubTerrainCfg`，可按训练仓库 `terrain.py` 的写法照葫芦画瓢） |
| 台阶（T 字形/直台阶） | `BoxPyramidStairsTerrainCfg`、`BoxInvertedPyramidStairsTerrainCfg`、`BoxRandomStairsTerrainCfg`、`BoxOpenStairsTerrainCfg` | 按 2026 T 字形尺寸定制的 box 台阶（含顶部平台与下行段） |
| 梅花桩 | `BoxSteppingStonesTerrainCfg`、`BoxRandomSpreadTerrainCfg`、`BoxRandomGridTerrainCfg` | 按 2027 尺寸（200³、间距 200/400、两侧 800×800×200 平台）定制的交错桩阵 |
| 沟壑组合（2027 扩展） | `BoxOpenStairsTerrainCfg` 可参考 | L 形两平台 + 120/320 台阶 + 360 缺口 + 20° 斜坡的自定义地形 |
| 窄桥/单木桥 | `BoxNarrowBeamsTerrainCfg` | 按 2027 尺寸（3000×400×100）改参数即可 |
| 低矮限高/低摩擦等 | 无现成；RC_WheelLeg 的 `RCLowBarTerrainCfg`（MIT）可参考实现 | 低姿态通过训练；低摩擦可用材质/摩擦随机化实现 |

接入位置（训练仓库侧，不复制到本任务）：地形数学写在 `src/alldog_mjlab/tasks/velocity/black/terrain.py`（现有 `BlackRoughSlopeTerrainCfg` 就是“slope + noise 的 int16 高度场相加”的写法）；难度/比例在 `black_config.py` 的 `TerrainParams`；装配在 `env_cfgs.py` 的 terrain generator 处；验证用 mjlab 的地形可视化/`play` 先在单帧里看尺寸。训练地形不要直接引用只读材料里的 map.xml，而是按尺寸在 mjlab 里重建，便于随机化、课程和并行生成。

## 5. 评测场景（本任务侧）

| 场景 | 用途 | 来源 |
|---|---|---|
| `scene_terrain.xml` playground | 单障碍逐项检查（限高、高墙、绕杆、木桥、沟、楼梯） | 只读材料 `scene_terrain.xml`；补齐 black 模型与 hfield 后使用 |
| `scene_terrain (1).xml` 新版场地 | 2026 正式场地更新版：T 台阶、砂砾碎木坑、高墙、限高杆、斜坡木桥 A/B、10° 斜坡、绕杆等 | 只读 `ReadOnly.d/Downloaded.d/scene_terrain (1).xml`；include 的是 `blackW_description.xml`（不是本任务的 black 模型；文件在只读 `quadruped_control/assets/robots/blackW/mujoco/`）；hfield PNG 需从 `unitree_mujoco/unitree_robots/go2w/` 取并放到 `../../black/` 相对位置；使用前拷到临时目录/建软链，不修改 ReadOnly；正式评测需把 include 换成我们的 black 模型并复核碰撞/尺寸 |
| `terrain.zip` 能力场 | 平滑/坡/台阶/沟/碎石/桥/低摩擦逐车道能力 | 只读材料 `terrain.zip`；其包装布局要求 `robot/black/xmls` + `terrain/` |
| 2026 正式场地（自建 MJCF） | 手动计分、整场流程、后期 sim2sim | 规则 V2.0 + 图册 + `26RC_Field`（MIT）几何 |
| 2027 扩展地形 | 台阶/梅花桩/单木桥的远期目标 | 2027 规则 V1.0（本机只读材料） |

## 6. 入库与许可约束

- 只读材料与官方 PDF **不直接入库**（体积 + 许可）；仓库里只写名称、尺寸表与来源说明，命令需要时由本机只读材料或官方下载页准备（[`../../docs/conventions.md`](../../../docs/conventions.md) §4.7、§4.10）。
- 可入库的第三方几何/代码：`26RC_Field`（MIT，保留版权/许可说明）；`Zbszbszbssca/RC_MAP` 无许可证，**只参考、不复制**；开源代码的许可见 [`open-source.md`](../reference/open-source.md)。
- 地形与场景资产若后续要入库，优先存“参数化配置 + 生成脚本”，而不是大 mesh；确需 mesh 时用软链接共用一份真实文件（§3.8）。

## 7. 平地阶段素材清单（2026-10-20 核对）

“平地阶段”这里指 flat 基础策略的地形族：平面、光滑坡、粗糙地、刚性碎石/石块、低摩擦。**训练侧**与**评测侧**分开看：

| 地形 | 训练侧是否可用 | 评测侧素材 | 结论 |
|---|---|---|---|
| 平面 flat | ✅ mjlab `BoxFlatTerrainCfg` / plane | 自建 plane 即可 | 齐 |
| 光滑坡 | ✅ mjlab `HfPyramidSlopedTerrainCfg`（2026 大/小斜坡 11.3°/14° 已知） | `terrain.zip` slope 车道（5–60°）；`scene_terrain.xml` unitree 斜坡组 | 尺寸/实现方式齐 |
| 粗糙地 | ✅ mjlab `HfRandomUniform` / `HfPerlinNoise`；训练仓库已有 `BlackRoughSlopeTerrainCfg` | `terrain.zip` rough t1–t7（5×5 石块、0.3 m 间距、高 1–6 cm）；`scene_terrain.xml` 随机石块组 | 齐 |
| 碎石/砂砾 | ⚠️ 只能用**刚性近似**：`BoxRandomSpread` / 自定义石块 + 粗糙高度场 + 摩擦随机；MuJoCo 没有现成可变形颗粒模型（自由关节堆的可行性原型见 [`gravel-feasibility.md`](gravel-feasibility.md)） | `terrain.zip` 只有刚性石块 lane，没有可变形砂砾；2026 官方砂砾碎木坑只有规则尺寸/图册，`26RC_Field` README 也标注砂砾碎木坑与材料标定待补 | **半成品**：几何与近似方案有，真实变形/颗粒物理没有 |
| 低摩擦 | ✅ 材质/摩擦随机化即可 | `terrain.zip` 低摩擦车道 0.50→0.03；可在本地评测脚本里复用 | 齐 |
| 2026 正式场地整体 | 训练不需要直接建正式场；正式场只做评测 | 已有规则 V2.0 尺寸、图册、`26RC_Field`（MIT CAD）、队内 `nav` 的 `scene_robocon.xml`；正式 MJCF 尚未搭建 | 评测场地未建（不影响 flat 基线） |

结论：

- **flat 基线训练**：素材够用。flat/坡/粗糙/低摩擦都可以直接在 mjlab 生成，不需要把手头的地形文件导入训练；`terrain.zip` / `scene_terrain.xml` 作为**评测套件**已齐。
- **砂砾**是唯一明显的保真缺口：如果只要求“刚性碎石 + 摩擦/粗糙度随机”，现在就能做；如果要求“可踩陷、颗粒流动”那种砂砾，MuJoCo 原生没有现成方案，需要单独做近似（比如软接触/高度场下沉/附加阻力模型）并标成 fidelity 实验，不能假装它等于真实砂砾。
- **台阶/梅花桩**：尺寸依据齐（2026 T 台阶、2027 沟壑/梅花桩），但训练地形配置和正式评测场景都要新建；台阶的“直台阶/金字塔台阶”已有 native 类可复用，T 字形/梅花桩需要自定义。

## 8. 2026-10-20 培训方补充资料

2026-10-20 21:37 在只读 `ReadOnly.d/Downloaded.d/` 新增 7 个 PDF（5 篇论文，其中两篇带中文翻译）与更新版 `scene_terrain (1).xml`；均只读、不入库。指纹（sha256）见下表。

| 文件 | 论文/内容 | 指纹 | 与训练计划的关系 |
|---|---|---|---|
| `2107.04034v1.pdf` | RMA: Rapid Motor Adaptation for Legged Robots（arXiv 2107.04034） | `d8660da8…` | 自适应/teacher-student 类，S2/S3 参考 |
| `2107.04034_zh-Hans.pdf` | RMA 中文翻译 | `8ba68542…` | 同上 |
| `2405.10830v2.pdf` | CTS: Concurrent Teacher-Student RL for Legged Locomotion（RA-L 2024） | `babc1afa…` | 训练计划中 teacher-student 对照 |
| `dreamwaq.pdf` | DreamWaQ（ICRA 2023） | `0ec52fa5…` | 历史隐式地形估计，S1/S2 对照 |
| `2312.11460v3.pdf` | HIMLoco（ICLR 2024） | `966785d9…` | `best.pt` 来源；HIM 主线 |
| `2312.11460_zh-Hans.pdf` | HIMLoco 中文翻译 | `a0ae67f2…` | 同上 |
| `Cheng 等 - 2023 - Extreme Parkour with Legged Robots.pdf` | Extreme Parkour（ICRA 2024） | `50f1cf2b…` | 台阶/跳沟课程参考；非商用许可，只参考 |

按标题看覆盖了训练计划里的 **RMA、CTS、DreamWaQ** 三篇，另加 HIMLoco 与 Extreme Parkour 两篇；中文翻译两篇。新版 `scene_terrain (1).xml` 的摘要见 §1，具体障碍注释含 30cm 高墙、砂砾碎木坑、限高杆、出发区、T 字台阶、木桥、10° 斜坡、绕杆等。

## 9. 下一步清单

1. 用规则尺寸在 MJCF 里搭 2026 正式场地（先 8 障碍简化版），与 `26RC_Field`/队内 CAD 核对；写下评测器的障碍判定区域配置。
2. 在训练仓库里新加/改地形配置：先 flat/rough/碎石，再三档台阶、梅花桩；每类都先用单帧可视化核对尺寸。
3. 用 `scene_terrain.xml` + `terrain.zip` 建评测脚本，先跑出 `best.pt` 的基线（已有一轮结果，可重复）。
4. 任务书进一步明确后回填 §3 的尺寸与 §5 的场地版本。
