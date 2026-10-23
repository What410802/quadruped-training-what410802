# 参考轨迹（trunk-only）可视化与训练方案（C2 前，2026-10-23）

> 用户 2026-10-23 决策 **A**：接受"无 scorer blocker 的 CONCERN"作为进入轨迹训练的条件；
> G1 保持 `HASHES audited=false / verdict=pending` **不冻结**，等训练出真实成功 rollout 后补 C1/G1。

## 1. 参考轨迹定义

- **位姿 6 DoF**：`x, y, z, roll, pitch, yaw`（SE(3)）；
- **第 7 维 = 时间/速度剖面**：每段目标速度 `speed`、可选 `hold`（原地保持）；
- 视觉：半透明 trunk-only ghost（无四肢）+ 三轴方向箭头 + 参考路径轨迹；左右双视图（第三人称 + 俯视）；
- 视频/计划：`RoboCon/prep.d/videos/trunk_ref/`（不入库）、`RoboCon/prep.d/results/trunk_ref_plan.json`。

生成命令（MyMonoRepo.d 下）：

```bash
pixi run python @20261019_locomotion/scripts/agent_scripts/visualize_trunk_reference.py
```

## 2. 当前参考库（手工设计，仅用于检查，不是物理验证后的轨迹）

Part1：height_bar（低姿态穿门）、high_wall（爬 0.3 m）、bridge_blocks/bands（过桥）、gravel_pit（西短边进→L 形→北短边出）、
t_stairs（s 上→top→e 下）、slope（沿 y 母线走）、slalom（S + 拐角）。
Part2：high_platform、stairs、slope、high_wall、trench、plum（各取一个中等 level 作代表；参数化 level 后续由生成器覆盖）。

**需要用户检查**：高度/姿态是否合理、是否穿模、入口-出口方向/顺序是否正确、转向/速度是否可信、
是否需要补充/修改哪条轨迹。确认后再进入 reward 设计。

## 3. Reward 设计草案（等可视化确认后细化）

- 位姿跟踪：**3 组常数权重**——水平位置 `(x,y)`、高度 `z`、姿态 `(roll,pitch,yaw)`；
  不铺 per-axis 容差表；参考轨迹是引导，**完成判定仍由物理/judge 决定**（不能把跟踪误差小当成功）。
- 进度项：沿参考路径的进度/速度带奖励（速度剖面 ±30% 容差），避免慢爬/停滞。
- 硬约束/终止：摔倒、trunk 触地、≥2 足触地（按规则）、越过关节/力矩限制、偏离通道过大。
- 步态/风格项：早期就保留低权重足端 clearance/支撑相/滑移/动作平滑项，防止"爬行/滑行/跳"等作弊解；
  base 跟踪稳定后再加强步态与能耗项。
- 参考轨迹可行性：不直接当硬约束；训练中允许偏差，若某些轨迹不可行（如 0.6 m 高墙/大沟），回到规划/课程调整。

## 4. 阶段

1. 本可视化 → 用户检查/修改参考轨迹；
2. 定 reward 权重（3 组常数 + 少量硬约束/通道约束）与课程（flat/低障碍 → 全障碍）；
3. 远程 `h800-1` smoke → 长训（需用户确认机器开关/open）；
4. 成功 rollout 补 C1 真实成功视频 → 重跑 C1/G1 → 冻结正式评测。

## 5. v2 修订（2026-10-23 20:50，回应用户检查意见）

| 用户问题 | 处理 |
|---|---|
| 蓝色盒子是否 trunk 包围盒 / height_bar 相交 | 改为从 black MJCF trunk geoms 估的近似 bbox（半尺寸 0.225×0.075×0.08 m；不是精确网格）；height_bar 低姿态段 base z 0.24，盒顶 ≈0.32 < 杆 0.325，不再相交 |
| high_wall 顶部上倾、前腿支撑受限 | 顶部段改为 **水平姿态 pitch=0**（z≈0.66）；腿长核算：thigh≈0.25 m、calf+foot≈0.244 m，总伸长约 0.5 m，0.3 m 墙是紧但可行；最终可行性留给训练/课程微调 |
| bridge_blocks 进入/离开不自然 | 起点改到 **西侧斜坡根部**（1.8,−1.5），经斜坡→西平台→转向东→方墩→东平台；终点在 **东平台内停止**（不走出平台） |
| bridge_bands 初始/行走 z | 起点改到低平台南侧地面；z 升到 0.60 是因为平台顶面高 0.2 m（trunk base ≈0.6），不是随意抬高；去掉中段额外 bump |
| gravel_pit 转弯摆尾 | 改为**行进中平滑左转**（yaw 0→45→90，速度连续），不再原地旋转 |
| t_stairs 转弯 | 改为弧线转向（yaw 90→60→30→0），速度连续 |
| slope 走坡顶 | 改走西侧坡面中间 x≈4.7（不是 x=5.2 坡顶脊线），沿 y 长边方向 z≈0.56 常数 |
| slalom 盒方向/避让 | yaw 改为沿速度方向，杆侧偏移增大；仍建议训练时按实际足端再细调 |
| p2_slope 未停在坡顶平面 | 用场景 raycast 得到所选 level 的顶面高度，最终 waypoint 放到顶面中部（x=4.1）并保持水平 |
| 动作变化处停顿 | 去掉了所有中间 hold；速度全局 ×1.35；仅保留必要的最终平台停留（无中间停顿） |

说明：这些仍是**手工引导轨迹**，不是优化/物理验证后的可行轨迹；设计目标是给 RL 一个合理起点，细节（足端落点、姿态、速度）由训练自适应。
**评审机制**：对"参考轨迹是否合理"不值得启用 reviewer（reviewer 不是 motion planner）；用本可视化 + 简单运动学检查 + 训练 smoke 更有效。
reviewer 继续用于 judge/G1 和正式结果审计。


## 6. 全场路线顺序（2026-10-23 用户确认调整）

为缩短总路程并形成环形，Part1 参考/课程顺序改为：

> 出发区 → high_wall → T 台阶 → slope → bridge_blocks → bridge_bands → **height_bar** → gravel_pit → slalom（**短边 B 进**）→ 返回出发区

- height_bar 放在 bridge_bands 与 gravel_pit 之间，从桥带北侧下来后直接到限高杆，再南下 gravel；
- slalom 从 **L 拐角短边圆 B** 进入（短边先走）：B → post3 → post2 → corner → post1 → post0 → A，终点 A 离出发区最近；
- `config/part1-route.json` 已按此顺序更新；slalom 参考已改为 B→A 并重渲。

## 7. slalom ASCII 匹配（2026-10-23 22:45）

按用户 ASCII 示意图重建 slalom 路径；映射关系（图中坐标 → MuJoCo 场景）：
- 图中横轴 = 场地 y（三根长边杆），图中纵轴 = 场地 x（短边方向）；
- B 圆（短边）在图中底部，A 圆（长边末端）在图中右侧。

当前 waypoint 映射到同一 ASCII 网格后与目标一致（仅末尾空格差异）：

```
    #       #
   #. # . # .##
    #   #
    .#
    #
    #
```

路径：B 短边进 → 狗右手侧绕 post3 → 绕角柱/角点 → post1 东侧 → post0 西侧 → A；
用 Catmull-Rom 平滑，机身 yaw 由局部切线自动生成。用 Part1JudgeV2 对参考采样做离线判定：
**slalom = success, score 100**（单障碍，静止其他障碍）。
