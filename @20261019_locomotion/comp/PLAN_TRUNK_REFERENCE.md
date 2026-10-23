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
