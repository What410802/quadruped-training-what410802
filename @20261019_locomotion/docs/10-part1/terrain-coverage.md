# Part1 地形覆盖（摘要，指针）

> 本页只保留 Part1 相关的结论；Part2 几何/档位/对称性/blind-vs-depth 的完整分析见 [`../20-part2-shared/geometry-and-levels.md`](../20-part2-shared/geometry-and-levels.md)。

- Part1 障碍赛地形：8 障碍 + 返回启动区；训练代理地形与官方场地的差异、砂砾/碎石/限高杆等可行性结论见 [`terrain-assets.md`](terrain-assets.md)、[`terrain-materials.md`](terrain-materials.md)、[`gravel-feasibility.md`](gravel-feasibility.md)、[`gravel-penetration.md`](gravel-penetration.md)。
- Part1 训练入口：`black-flat` / `black-rough` / `black-competition`（见 [`plan.md`](plan.md)）；赛事判分口径见 [`../00-competition/rules-team-race-2026.md`](../00-competition/rules-team-race-2026.md)。
- 历史背景（2026-10-24 之前的地形覆盖分析）已合并进 geometry-and-levels 的 §1–§2，避免两份文档重复。
