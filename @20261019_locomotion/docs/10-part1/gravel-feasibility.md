# 砂砾/碎石地形可行性：自由关节刚体堆 vs 静态碎石

> 2026-10-20 用本地 MuJoCo 3.12（CPU）做的可行性原型，脚本：[`../scripts/agent_scripts/prototype_gravel.py`](../../scripts/agent_scripts/prototype_gravel.py)。目的不是给出训练地形实现，而是判断“把大量随机形状刚体（free joint）堆进预设坑”**能否用于训练**，以及另一条“起伏随机刚体地面”的代价。

## 1. 结论先行

- **自由关节刚体堆本身可行**：在单个 MuJoCo 模型里，50/100/200 块随机扁平石块带 free joint 落入带围墙的坑中，能正常稳定下来，没有逃逸；200 块时约 1.85 ms/CPU-step、最大 869 个接触。
- **直接用于 4096 envs 的训练不可行**：free joint 石块是 per-env 动态刚体，按 200 块 × 4096 env 估算约 81.9 万 body、nq≈573 万、nv≈492 万、最大接触约 356 万个，远超单张 16 GB 显存和 MJWarp 的约束/容量预算。降到 128–256 envs 做“保真微调”理论上有希望，但需要单独用 MJWarp 实测，不能当作主训练地形。
- **可落地的组合**：
  1. **训练用静态碎石/砂砾**：先用同样的随机形状生成一坑石块，动态沉降到位后把位姿**烘焙成静态 geom**（不再有 free joint），作为训练地形的一部分；形状随机性保留、动力学代价接近零，机器人足端仍会与石块表面碰撞。
  2. **评测/保真实验用动态砂砾坑**：单场景或少量 env 的 free-joint 堆，用于验证策略在“可被踩动/滚动”的碎石上的行为，以及 sim2sim/fidelity 对照。
  3. **起伏随机刚体地面**：静态随机石块/矮丘铺在平面上，作为训练地形族里的另一种 ground；成本与静态碎石同级，适合直接进 mjlab 的自定义 `SubTerrainCfg`。
- 因此：**“自由关节砂砾坑”先放在评测/保真场景，不作为第一版训练地形；训练先用“静态预沉降碎石 + 起伏随机刚体地面”**。这符合“实现有难度则先搁置”，且不阻塞 baseline。

## 2. 原型数据（本地 CPU，MuJoCo 3.12，timestep = 2 ms）

| 石块数 | 模式 | nq | nv | ngeom | 最大接触 | 逃逸 | CPU ms/step |
|---|---|---|---|---|---|---|---|
| 50 | dynamic（free joint） | 350 | 300 | 55 | 209 | 0 | 0.292 |
| 100 | dynamic | 700 | 600 | 105 | 433 | 0 | 0.736 |
| 200 | dynamic | 1400 | 1200 | 205 | 869 | 0 | 1.850 |
| 50/100/200 | static（无 joint） | 0 | 0 | 55/105/205 | 0 | 0 | 0.013 / 0.034 / 0.056 |

形状：扁平 box，半长 1.2–3.5 cm、半宽 0.8–2.5 cm、半厚 0.3–1.0 cm，随机 yaw/roll/pitch；坑内区 0.8×0.8 m、围墙高 0.25 m；重力沉降 2 s（1000 steps）。动态组用 free joint，静态组同款几何直接焊到世界。

注意：这是 **CPU MuJoCo 单模型**数据，不是 MJWarp/4096 env 的吞吐；只用来判断可行性与相对代价。

## 3. 训练规模估算（为什么不能直接上 4096 envs）

- 每个自由石块：nq=7（3 位置 + 4 四元数）、nv=6；200 块/env → nq=1400、nv=1200。
- 4096 envs：约 **573 万 nq / 492 万 nv / 82 万 body**；最大接触数量按 200 块时 ~869/env 估算约 **356 万**。这远超 16 GB 显存与 MJWarp 的约束容量；即使勉强放下，步进时间也不可接受。
- 对比：静态碎石没有 joint、没有石块间接触，只有几何与足端接触，成本接近普通静态地形（上面 static 组 200 块仅 0.056 ms/step，CPU），适合做训练地形。

## 4. 建议的实现路线

1. **静态预沉降碎石地形**（训练主线）：
   - 离线用与原型相同的随机形状/堆叠/沉降；达到稳定后记录每块石块的 `pos/quat`；
   - 在 mjlab 的自定义 `SubTerrainCfg` 里以静态 geom 形式重建，作为“砂砾/碎石”地面的一种；
   - 保留随机性：每个 terrain patch 不同种子，形状/尺寸/朝向随机；可按 difficulty 调石块大小/密度/嵌入深度。
2. **动态自由关节砂砾坑**（评测/保真，后续）：
   - 生成带坑、围墙、free-joint 石块的 MJCF 场景；
   - 单场景/少量 env 下评测策略是否能踩动/适应滚动石块；与静态近似对比，量化“保真度收益”；
   - 若要低 env 微调（如 128/256 envs），先在 MJWarp 里测显存与吞吐，再决定是否值得。
3. **起伏随机刚体地面**（训练/评测都可）：
   - 静态随机石块/低矮凸起铺在平面上；与静态碎石共用生成器，只是分布/嵌入方式不同；
   - 比“自由 joint 坑”便宜得多，适合作为粗糙地形的补充。

## 4.5 足式社区的处理办法（检索初版，2026-10-20）

| 做法 | 代表工作 | 要点 | 对我们的可操作性 |
|---|---|---|---|
| 刚性/起伏地形代理 + 地形随机化课程 | Singh 等 2024（HRP-5P，[arXiv 2504.13619](https://arxiv.org/abs/2504.13619)，[代码](https://github.com/rohanpsingh/LearningHumanoidWalking)） | 只用本体感知，在随机化地形课程上训练即可走真实软/不平地形；不显式模拟颗粒 | 最高：与我们“随机起伏刚体地面 + DR”一致，成本低 |
| 参数化颗粒介质接触模型 + 在线辨识 | Choi 等 2023（Raibo，Science Robotics，[DOI](https://doi.org/10.1126/scirobotics.ade2256)） | 用计算高效的 granular media 模型覆盖软沙到硬沥青，并从足端交互中在线辨识地形参数；软沙上 3.03 m/s | 中：需要自己实现接触力模型/辨识模块；比刚性代理真实，但工程量大 |
| 3D 阻力理论（RFT）+ MPM 验证 + teacher-student | GM-Loco 2026（[arXiv 2609.10286](https://arxiv.org/abs/2609.10286)） | 用 3D RFT 做物理落地的颗粒接触，训练时高效；用 NVIDIA Newton 的 MPM 做仿真验证；VAE 隐变量 + teacher-student 适应地形 | 中/高：RFT 思路可做轻量代理；MPM 太重，不适合我们 MJWarp 主训练 |
| 软接触/摩擦/下沉参数随机化 | 常见 sim2real 做法 | 用 MuJoCo `solref/solimp`、摩擦、接触刚度随机化近似“软”，不显式模拟颗粒 | 高：便宜，适合作为静态碎石之外的保真微调项；但要注意过度随机化掩盖真实差异 |
| MPM/DEM/颗粒引擎 | Granular Gym、NVIDIA Newton 等 | 高保真、慢；适合离线生成数据/评测，不适合 4096 envs 大规模 RL | 低（当前）：可作为后续保真实验的参照 |
| 自由关节刚体堆 / 可动碎石 | 操作/颗粒任务更多见 | 能表现“踩动/滚动/局部塌陷”，但 per-env 动态体数量大 | 中：适合评测/低 env 微调（本文 §2–§4 的原型） |

结论：社区主流仍是**刚性/参数化地形代理 + 随机化课程**，高保真颗粒模型（RFT、MPM、DEM）更多用于离线验证或小规模训练。我们的“静态随机起伏预训练 → 自由关节碎石低 env 微调”与这个趋势一致，且保留了后续升级到 RFT/软接触模型的接口。

## 5. 待做

- [ ] 把静态预沉降碎石生成器写成可复用脚本，输出 mjlab `SubTerrainCfg` 需要的几何位姿（训练仓库侧实现）。
- [ ] 动态砂砾坑 MJCF 场景（评测侧，运行仓库 `@20261019_locomotion/assets/` 或脚本生成）。
- [ ] 若需要动态训练：在 MJWarp 上测 128/256 envs + 50/100 块的显存与 step time，给出上限。
- [ ] 把“砂砾静态近似 vs 动态坑”的差异作为 fidelity 实验，纳入 S3 鲁棒性评测。

## 6. 实装：S1b 固定 + 自由关节两套砂砾（2026-10-21）

预烘焙深度来自与训练分离的踩入实验（3.3 kg 单足 p95 5.3 cm；2× 动载/13 kg 极限仍受床深限制），见 [`gravel-penetration.md`](gravel-penetration.md)。当前 composite 采用 **6 cm 基座**，在 p95 之上留约 0.7 cm 余量。


按“S1b 必须同时覆盖固定与自由关节砂砾；前者批量预训练，后者小 batch 微调”的要求，训练仓库新增两个 task：

| task | 地形 | 规模 | 用途 |
|---|---|---|---|
| `black-gravel-flat` | 50% flat + 30% 细砾石 heightfield + 20% 粗砾石 heightfield；无台阶/离散障碍 | 4096 envs 可用 | S1b 固定砂砾批量预训练 / gate |
| `black-gravel-free` | 同一 flat 场景 + `scene.spec_fn` 加 **120 块 3–8 cm 自由碎石 + 700 块静态预沉降石 + 6 cm 基座 + 6 cm 低 curb**（1.5×1.5 m，无高围栏） | **4–8 envs**（free joint/碰撞限制） | S1b 自由关节砂砾小 batch 微调 / 评测 |

实现位置（训练仓库）：

- `src/alldog_mjlab/tasks/velocity/black/terrain.py:black_gravel_flat_terrain_generator_cfg`
- `src/alldog_mjlab/tasks/velocity/black/free_gravel.py:add_free_gravel_bed / coverage_stats / _stone_geometry`
- `src/alldog_mjlab/tasks/velocity/black/env_cfgs.py:black_gravel_flat_env_cfg / black_gravel_free_env_cfg`

### 6.1 石块密度、尺寸与覆盖率（用户 2026-10-21 审查后修正）

旧版 24 个小石块（0.015–0.045 m 半长）覆盖率太低，狗实际上站在暴露的地面上；坑边缘还有 0.25 m 高围墙，出坑靠撞围栏而不是踩石块。新版改为“抬高石床 + 静态预沉降底层 + 自由碎石表层”：

- **6 cm 低 curb + 6 cm 基座**：石床整体略高于地面，狗需要迈进去；按 1/3 COM 界限 0.14 m，6 cm 属于平地；石顶最高约 14 cm（6 cm 基座 + 8 cm 石）仍在 1/3 内。
- **静态预沉降层 700 块**：3–8 cm 随机三轴椭球、随机 yaw，部分嵌入基座，形成连续的碎石表面；没有 free joint，不参与动力学。
- **自由碎石表层 120 块**：3–8 cm 随机三轴椭球，随机 yaw / 小倾斜，free joint + damping；石-石接触关闭以避免爆炸，狗踩到会推动/滚动一部分石头。
- 尺寸按实际碎石量级设置；本轮用 **3–8 cm**，与 6 cm 基座叠加后最高约 14 cm，满足 1/3 COM 平地界限。
- 覆盖率（投影，1.5×1.5 m bed）：
  - 自由层 union **11.5%**；
  - 静态层 union **58.4%**；
  - 自由+静态 union **63.2%**；
  - 再加上基座后，狗脚下始终是 stone/base 表面，不会踩穿到暴露地面。
- 当前 batch 为 **4–8 envs**；820 个石体/每 world，训练成本明显高于 80 石块版本。俯视图：`prep.d/videos/overview/black-gravel-free_composite_final_overview.png`。

### 6.2 自由 task 边界

- 120 个 free-joint 石块 + 700 个静态石块/每 world；4096 envs 不适用；4–8 envs 是实验性 batch。
- 通用 `illegal_contact` 只匹配 `terrain`，不匹配石块；训练模式额外加 `bad_orientation`（~60°）终止；play 评测保留连续 episode。
- 石-石接触关闭、静态填充层是性能与稳定性的取舍；这不是颗粒 DEM，不能替代真实砂砾物理。大块/整片石块（15–19 cm 的 dense80）只作为“木块/大障碍”的仿真思路：调密度/摩擦、改 mass 和 contact 参数后可复用到木块部分，不再当碎石尺寸基准。
- 固定 task 的 heightfield 仍是批量预训练代理；自由 task 才覆盖“踩得动/会滚动”的碎石。

### 6.3 当前评测状态

- 旧稀疏布局（24 石块 + 围墙）的 `v2_700` 32 envs pass 已**作废**，不再作为 S1b-free 证据；权重 `free-gravel-v2-700` 仅保留历史。
- 旧 dense80（80 块 15–19 cm 大石块）的 16/32 envs pass 只说明“大石块/整片石”可行，**尺寸不符合实际碎石 3–10 cm**，已降级为过渡/木块参考，不作为 S1b-free 完成。
- 新 composite（120 自由 + 700 静态、3–8 cm、6 cm 基座）尚未训练；但 `flat-ft-2500` zero-shot 在 composite **4 envs：0 摔倒、0.3/0.5 m/s MAE 0.089/0.049、p95 tilt 4.1°/3.1°**，provisional pass（4 envs/单布局，不是正式验收）；视频 `prep.d/videos/flat_ft_composite_zero_shot.mp4`。820 个石体/每 world，4–8 envs 是实验性 batch。
- 按 76% 覆盖率和无围墙布局，S1b-free 现在才是“真正踩在石层上”的测试；旧结果不能说明问题。

结论：**自由砂砾不是“必然过”的装饰项**；密度、覆盖率和出坑方式会直接改变任务难度。S1b-free 不通过时优先继续小 batch 微调/调整石块密度，而不是把它挪到其他阶段。
