# 2026 队内赛地形资产梳理（2026-10-21）

> 目的：把 Part 1 正式场、Part 2 能力场、培训方/开源仓库资产分清，列出**可直接用**、**需修改**、**仅参考**的部分。原始 XML/zip/PDF 均为只读材料，不入库；本文件只记路径、指纹、尺寸与使用决定。

## 1. 资产总表

| 资产 | 类型 | 指纹/规模 | 用途 | 决定 |
|---|---|---|---|---|
| `ReadOnly.d/Downloaded.d/scene_terrain (1).xml` | MuJoCo 场景 | 28,070 B，sha256 `730cce…a6d0`；151 geom；`<include file="blackW_description.xml"/>`；hfield 依赖同目录 `../../black/*.png` | **Part 1 正式场**（培训方确认） | **直接用**，先做必要修改（include/height bar/gravel pit/hfield）；正式评测前换机器人模型 |
| `ReadOnly.d/Downloaded.d/terrain.zip` | MuJoCo 能力场 + labels | 1,966,035 B，sha256 `141960…8fb0`；`terrain/map.xml` 约 920 geom/87 texture；85 个难度标签 PNG；`go1.xml`/`black.xml` 包装 | **Part 2 能力场候选**；训练/eval 可复用的地形库 | **用其几何/标签做能力场基础**，按 PDF 只取官方档位；不直接入库 |
| `ReadOnly.d/Downloaded.d/scene_terrain.xml` | MuJoCo 场景 | 15,442 B，sha256 `9da486…85ae` | 旧版单位置 playground（限高/高墙/绕杆/木桥/沟/楼梯） | 只作交叉校验/旧版参考 |
| `quadruped_control` 仓库 `assets/robots/blackW/mujoco/` | 训练方机器人/场景 | blackW_description、scene_terrain 等 | Part 1 XML include 依赖、blackW 模型 | 只读；换成我们的 Black 模型后使用 |
| `Ruixi-Cheng/26RC_Field` | 开源 CAD/几何 | MIT | 2026 场地 SolidWorks 几何 | 几何核对；保留许可 |
| `Zbszbszbssca/RC_MAP` | 开源 MuJoCo 场景 | 无许可证 | 2026 场地交叉校验 | 只参考，不复制 |
| 队内 `nav` 仓库 `scene_robocon.xml` 等 | 队内 2026 场地 | 双场 CAD/航点 | 场地/航点交叉校验 | 只读参考 |

## 2. Part 1：`scene_terrain (1).xml` 的审计

文件包含的正式障碍（按 XML 注释）：

- 30 cm 高墙（x 向，y=-7.0；与 T 楼梯中心线对齐）。
- 砂砾碎木坑（两段 box，位于 x≈4.84/5.84、y≈-12.5/-12.0）。
- 限高杆（两侧立柱 + 横杆，横杆 z≈0.325 m）。
- 1 m×1 m 出发区（仅显示，不碰撞）。
- T 字形 10 cm 级高台阶：总高 40 cm，含最高平台 + 两侧下台阶 + 向 +x 连接地面的 10 cm 级台阶。
- 木桥有两种（用户 2026-10-21 修正）：**5 个间隔方墩**（0.4×1.0×0.2 m，中心 x=2.65/3.20/3.75/4.30/4.85，y=0，缝 0.15 m）和 **3 条窄带**（0.2×1.5×0.2 m，中心 x=5.35/5.65/5.95，y=-2.25，缝 0.10 m）；后者盲策略容错低。10° 斜坡（4 m/3 m 两段）、绕杆（间距 1 m 的竖杆）。
- 额外“5 cm 台阶”“斜坡”等训练用几何（**不是 PDF 正式障碍清单的一部分**，评测时过滤）。

### 2.1 必须修改/确认的地方

| 优先级 | 问题 | 处理 |
|---|---|---|
| P0 | `include file="blackW_description.xml"` 是 blackW，不是我们的 Black | 换成我们的 Black MJCF/`black_description.xml`，核对质量/惯量/足端/碰撞体；这是最明确的一处“需要修改”候选 |
| P0 | 限高杆是**静态 cylinder**，规则要求“若杆掉落则失败” | 改成可动杆（free/hinge 或 slide + 限位），judge 检测位移/掉落；训练中也要能触发 |
| P0 | 砂砾碎木坑当前是两块**实心 box**，不是坑/碎木 | 改成 L 形坑 + 碎木/碎石表面；judge 需要区分“坑内地面”和“允许的碎木/石表面”，并实现 1 m 短边进出 |
| P1 | T 台阶为 10 cm 级高/40 cm 总高；与培训方确认是否是正式参数（PDF 图/规则未逐项标尺寸） | 以培训方口头/后续文件为准；先保留 10 cm 版本并标为待确认 |
| P1 | XML 含 5 cm 台阶/额外斜坡等非 PDF 赛事障碍 | 训练/鲁棒性可用；正式 judge 只登记 8 个正式障碍，过滤额外 geom |
| P0 | hfield 依赖 `../../black/height_field.png`、`../../black/unitree_hfield.png` | 从只读 unitree_mujoco go2w 拷贝到临时目录按相对路径放置；不修改 ReadOnly |

> 培训方说的“需要修改的一处”如果指的不是 include/height bar/gravel pit 中任一项，请把原话/位置给我；我先把上述 P0 作为确定项处理。

## 3. Part 2：能力场地形库

### 3.1 `terrain.zip` 的标签与官方档位

`terrain.zip` 是“运动能力测试场”，共 **85 个困难度标签 PNG**；按类别：

| 类别 | 标签 | 官方 Part 2 档位 | 用法 |
|---|---|---|---|
| 高台 `platform` | 5/10/15/20/25/30/40/50/60/80/100/120 cm（12 档） | 10/20/30/40 cm | 取 10/20/30/40；其余训练/鲁棒性 |
| 楼梯 `stairs` | 4/6/8/10/12/15/20/25/30/35/40 cm（11 档） | 10/15/20/30 cm | 取官方档位；其余课程 |
| 斜坡 `slope` | 5/10/15/20/25/30/35/40/45/50/60° 上坡（11 档） | 20/30/35/45° | 取官方档位 |
| 横向斜坡 `cross_slope` | 10/15/20/25/30/40/45° | 不在官方 6 项列表 | 训练多样性，不计分 |
| 沟壑 `trench` | 10/20/30/40/50/60/80/100/120/150/180 cm 净宽（11 档） | 10/20/30 cm（30=300 分） | 取 10/20/30 |
| 高墙 `cross_bar` | 8 档：4/8/12/16/20/30/40/50 cm | 10/20/30/40 cm | 20/30/40 直接对应；10 cm 需自建/改 12 cm 档 |
| 窄桥 `bridge` | 6/10/15/20/25/30/40 cm 宽；长 3 m、高 10 cm | 不在官方 Part 2 六项列表 | Part 1 木桥训练/额外能力 |
| 梅花桩 `plum` | `plum` + `plum_t2..t5`；标签显示 24 桩、顶面 20 cm、同排净距 40 cm（不是 PDF 的 200 mm 方块规格） | PDF：200×200×200 mm 方块交错，800×800×200 平台 | **按 PDF 自建**：已生成 `assets/terrain/part2/part2_plum.xml`；官方档位映射见 `assets/terrain/part2/official_catalog.yaml`；terrain.zip 的 plum 只作训练多样性 |
| 粗糙 `rough_t1..t7` | 7 档 | 不在官方能力六项 | 训练多样性/DR |
| 低摩擦 `low_friction` | 0.3/0.8/1.5/2.5/3.5/5.0（6 档） | 不在官方能力六项 | 训练多样性/DR |

- `terrain.zip` 的 `map.xml` 是单场景能力场；它**不是** Part 2 官方 XML（官方称能力场地形可自定义、只需同种类），但标签/几何足够做**能力场评测基础**。
- Part 2 正式评分只取 PDF 六项；`cross_slope`、`rough`、`low_friction`、`bridge` 只做训练/鲁棒性；`plum` 必须按 PDF 重做。
- 训练侧不直接加载 `map.xml`；在 mjlab 里按尺寸重建（见 [`materials.md`](materials.md) §4）。

### 3.2 已落地资产

- `assets/terrain/part2/part2_plum.xml`：按 PDF 推导的 6 桩（3 桩/排 × 2 排）+ 两侧 800×800×200 平台，总长 3500 mm；由 `official_catalog.yaml` 记录官方档位。
- `assets/terrain/part2/official_catalog.yaml`：把官方 6 项档位映射到 `terrain.zip` 标签；`plum` 明确使用自建 XML。
- `config/manual-state-machine.yaml`：手动保底状态机配置（flat/loose/limit_bar/bridge/stairs/high_wall/slope/slalom），由 `scripts/agent_scripts/check_state_machine.py` 校验。

### 3.3 其他仓库

- 培训方 `quadruped_control`：`assets/robots/blackW/mujoco/scene_terrain.xml` 等是机器人/场景资产，不是独立 Part 2 场；其中的 blackW 模型是 Part 1 XML 的 include 依赖。
- 开源 `26RC_Field`（MIT）：2026 场地 SolidWorks 几何，适合核对 Part 1 尺寸；不是 Part 2 能力场。
- 开源 `RC_MAP`（无许可证）：2026 场地 MuJoCo 场景，只作几何交叉校验，不复制。
- 队内 `nav` 的 `scene_robocon.xml`/航点：Part 1 场地/导航参考。

### 3.1 本地 eval 副本

- `assets/terrain/part2/ability_field/part2_ability_field.xml`：官方 `terrain.zip` 的 `map.xml` + `labels/` + Black policy 组合；编译 `nbody=20/ngeom=955/nq=19/nu=12`。
- 用途：本地 MuJoCo/Pixi zero-shot、可视化和 judge 试验；**不是训练 task**，六类 terrain 的训练 task 仍在训练仓库生成。
- 来源和许可提示：`terrain.zip` 为培训方只读素材；本地副本只服务本仓库评测，不改原始 zip。

## 4. 采集与训练使用顺序

1. **Part 1 P0**：用 `scene_terrain (1).xml` 换 Black、修 height bar/gravel pit，建 `ObstacleSpec` 与 judge；先用手动状态机跑 flat/桥/台阶/高墙。
2. **Part 2 P0**：从 `terrain.zip` 取官方 6 类档位，重建 mjlab/eval 地形；plum 按 PDF 自建；先跑现有策略 zero-shot 得分。
3. **训练地形**：按族生成（slope/stairs/platform/wall/gap/plum/bridge/loose），随机布局/难度；不在训练中直接依赖只读 `map.xml`。
4. **评测**：用 Part 1/Part 2 官方子集，judge 独立于训练 terminate；保存每障碍/每难度分数。
