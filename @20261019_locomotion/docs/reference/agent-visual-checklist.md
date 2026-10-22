# AI 动手前自检：障碍方向与门洞（2026-10-22）

> 触发场景：写脚本/改 judge/选起点和速度方向/录视频/解释障碍通过方式之前。一次错误案例：限高杆被当成沿 +x 通过，实际门洞在 y 方向。

## 1. 先读几何，不按名字猜方向

- 在 MJCF/MuJoCo 里取 `geom_pos`、`geom_size`、`geom_quat`、`geom_type`，必要时读 body/关节；不要只靠 geom 名字或俯视图的直觉。
- 门/栏/墙要区分：
  - **门柱**：两根柱子的连线定义门宽；机器人应从两柱之间、垂直于门平面前进；
  - **横梁**：横梁的轴向不是通过方向；横梁下方是净空，门洞方向是门平面的法向；
  - **墙**：墙的厚方向是跨越方向；墙的高度决定是否需要爬/跳，不是“绕过去”。
- 对每个障碍在任务配置/judge 里显式写：`axis`（通过方向）、`entry`/`exit`（进入/离开边界）、`opening_bounds`（门洞横向范围）、`fail_conditions`。

## 2. 限高杆案例（必须记住）

`part1_scene.xml` 中：

- 柱：`height_bar_post_b` 在 `(5.2, -9.0)`，`height_bar_post_a` 在 `(6.2, -9.0)`；
- 梁：`height_bar_beam` 在 `(5.7, -9.0, 0.325)`，长度沿 x；
- 因此门洞是 **x ∈ [5.2, 6.2]、y = -9 附近** 的平面，正确通过方向是 **沿 y**，不是沿 +x。
- 错误示例（已废弃）：从 `(4.9, -9)` 沿 +x 接近，撞在侧柱/梁上；这是“看见横梁就以为沿横梁走”的典型误判。
- 正确起点：`(5.7, -10.4)`，yaw=+π/2，沿机体 +x（世界 +y）低速通过；judge 在 y 跨越 -9 且 x 落在门洞内时 success，任一机器人 body 接触柱/梁则 fail。

## 3. 视觉复核流程（至少做一步）

1. 生成一次 top-down 渲染，标出障碍 geom/边界和拟定起点/方向箭头；确认箭头穿过门洞中心而不是柱子。
2. 生成一次第一视角或斜视短片段，确认机器人正对开口、无侧柱遮挡。
3. 跑 judge 前先跑 `Part1Judge` 的接触/区域自检；若 status 与几何不符，先修 judge，不继续调策略。
4. 把复核图/短视频留到 `prep.d/videos/`，并在任务 status 记一行；算法结论必须能和图对上。

## 4. 其他 Part 1 方向的快速核对

| 障碍 | 通过方向 | 依据 |
|---|---|---|
| high_wall | 沿 ±y 跨墙 | `high_wall` quat=yaw 90°，薄方向是世界 y；跨度为 x=1.3…2.3 |
| bridge_blocks | 沿 ±x | 方墩沿 x 排列 |
| bridge_bands | 沿 ±y | 三条带沿 y 长、沿 x 排列 |
| T stairs | 沿 ±y 走主肢，或从侧肢绕 | 主阶 geom 在 x=1.8、y=-4.75…-2.25 |
| slope | 沿 ±x 上/下坡 | 坡面在 x=4.6/5.8、y=-5 |
| gravel_pit | 从 1 m 短边进/出 | L 形两箱；进入前用尺寸/PDF 再确认短边 |
| slalom | 依次绕 4 个柱 | 柱位 (1.8,-10.5)(1.8,-11.5)(1.8,-12.5)(2.8,-12.5) |

## 5. 代码/配置落点

- `scripts/agent_scripts/run_part1_judged_rollout.py` 的 `TASKS` 必须带 `note`，写清通过方向；
- `scripts/agent_scripts/part1_event_judge.py` 的 success 条件必须与 `TASKS` 的 axis 一致；
- 每次新增/修改障碍，同步 `docs/training/competition-judge.md` 的判据表和本文件的方向表。
