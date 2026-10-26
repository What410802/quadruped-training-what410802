> 归档：本文件内容已并入 [`../20-part2-shared/geometry-and-levels.md`](../20-part2-shared/geometry-and-levels.md)。

# Part 2 训练地形审计：proxy vs 官方能力场

结论：**当前 `black_competition_terrain_generator_cfg` 不是竞赛地形的复制品，而是简化/近似版；不能再把 proxy reward 当作真实通过信号。** 本轮暂停训练，先做逐地形、逐难度核对。

## 权威来源

官方地形来自 `ReadOnly.d/Downloaded.d/terrain.zip`，本地展开在 `@20261019_locomotion/assets/terrain/part2/ability_field/`：

- `map.xml`：实际场景 geom（尺寸、mesh、位置）。
- `labels/*.png`：官方能力档位标注卡。
- `official_catalog.yaml`：档位映射。

`assets/terrain/part2/levels/*.xml` 是此前自建的**简化关卡**，不是官方地形；`blackW` 训练里的 proxy terrain 又是另一套简化参数。三者不一致。

## 逐地形差异

### high_platform

| 来源 | 10/20/30/40cm 实际几何 |
|---|---|
| 官方 `map.xml` | 单块 box，`size=(0.75,0.8,h/2)`，顶面 1.5×1.6m，中心在 lane 前 2.5m 附近；无辅助台阶 |
| 当前 proxy | 先放 0.35×0.7m 半高辅助台阶，再放 0.7×0.7m 平台；高度 0.10+0.30×difficulty |
| 本地 level XML | 单块 1.2×1.2m，低于官方 1.5×1.6m |

官方 40cm 卡明确写“平台 150×160cm”；proxy 的平台只有 70×70cm，并且多了一个真实场地没有的半高台阶，会直接教出错误的踩台阶策略。

### high_wall

| 来源 | 几何 |
|---|---|
| 官方 | `cross_bar_*`：宽 1.4m、厚 0.12m、高 0.10/0.20/0.30/0.40m 的窄墙 |
| 当前 proxy | 厚 0.06m、横贯整个 8m 地形块、高度只到 0.30m |
| 本地 level XML | 厚 0.10m、宽 2.0m、位置 x=2.5 |

proxy **根本没有 40cm 档**；厚度/宽度也不同，不能用来训练高墙。

### slope

| 来源 | 20/30/35/45° 几何 |
|---|---|
| 官方 | mesh 楔形，水平长 2m、宽 1.4m，升高 = 2×tan(angle)：0.728 / 1.155 / 1.400 / 2.000m，后面接 0.8m 平台 |
| 当前 proxy | `HfPyramidSlopedTerrainCfg` 的高程场金字塔，diff 0→1 扫到 45°，不是带平台的直斜坡 |
| 本地 level XML | 水平长 1.5m、宽 1.2m，升高 0.546 / 0.866 / 1.050 / 1.500m |

官方 45° 是水平 2m、升高 **2m**，本地只有 1.5m；proxy 是另一种坡度形状。此前“slope 35 能过、45 不能过”的结论不能直接迁移到官方 45°。

### stairs

| 来源 | 10/15/20/30cm 实际几何 |
|---|---|
| 官方 | 6 级，单级高度 = 档位，踏面 0.30m，总高 = 6×档位：0.60 / 0.90 / 1.20 / 1.80m |
| 当前 proxy | `BoxPyramidStairsTerrainCfg`，台阶高度约 0.05+0.18×difficulty，和官方 6 级结构不一致 |
| 本地 level XML | 6 级但总高只有 0.10/0.15/0.20/0.30m，约是官方总高的 1/6 |

这是本轮最严重的差异之一：本地“stairs_30cm”只有 30cm 总高，官方是单级 30cm、总高 180cm。此前 stairs 的 success 完全不能说明能过官方 30cm 楼梯。

### trench

| 来源 | 10/20/30cm 实际几何 |
|---|---|
| 官方 | 净宽 0.10/0.20/0.30m，深 0.30m，通道宽 1.4m；entry/exit 各有 1m 楔形坡 |
| 当前 proxy | gap 0.15–0.35m（10cm 档起点就不对）、深 0.30m、中心在 lane 前 1.4m |
| 本地 level XML | gap 0.10/0.20/0.30m、深 **0.60m**、通道宽 2.4m、无 entry/exit 坡 |

### Part 1 height_bar（顺带核对）

| 来源 | 数值 |
|---|---|
| 官方 `part1_scene.xml` | 横杆中心 z=0.325m，半径 0.015m，杆底约 **0.31m**，门柱高 0.31m |
| 当前 proxy `HeightBarTerrainCfg` | clearance 0.60→0.55m，杆底约 0.55–0.60m |

proxy 限高杆比真实高约 0.25–0.29m；此前的“限高杆过高”问题也确认存在。

## 训练/评测现状

- 训练 reward 和 success 用的是 proxy 的 `x>goal_x` 稀疏规则，不是 judge 的 platform/wall/slope/gap 条件；reward 上升不等于真实通过。
- 课程没有按用户要求做“简化档 100% 成功后再升档”：`TerrainGeneratorCfg(curriculum=True)` 是距离/地形级课程，我们另外设置的 `max_init_terrain_level` 只是初始行，不是成功率门控。
- 之前的失败档位（用 proxy/本地 XML 评测，结论仅对错误几何有效）：
  - proxy `comp_high600`：high_platform 10/20/30 过，**40 未过**；slope 20/30/35 过，**45 未过**；trench 10/20 过，**30 未过**；高墙和楼梯均未过。
  - `comp_lane300`：stairs 10/15/20/30 过（但本地 stairs 几何错误，无效）；slope 20/30 过。
  - exact 任务（此前用本地 XML 尺寸建）：platform/slope 的 `competition_goal_reached` 长期 0；现在看是几何本身就不对，不能作为官方结论。

## 下一步（需确认后执行）

1. 以 `map.xml` + `labels` 为唯一权威，重建训练 terrain 和本地评测关卡：
   - high_platform：1.5×1.6m 单块，无辅助台阶，10/20/30/40cm；
   - high_wall：1.4m×0.12m，10/20/30/40cm；
   - slope：2m 水平长、1.4m 宽，20/30/35/45°，升高 2×tan；
   - stairs：6 级 × 单级档位、踏面0.3m，总高6×档位；
   - trench：0.1/0.2/0.3m 净宽、0.3m 深，入口/出口楔形坡，通道1.4m；
   - Part 1 height_bar：杆底 0.31m。
2. 每一档单独做 success-gated 课程：先低档、成功率达标（例如连续100次/≥99%）才进入下一档；不再用混合 proxy 的稀疏 x 奖励。
3. 训练前先逐档渲染训练 terrain 截图给你确认，确认后才用远程 GPU。
