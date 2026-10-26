# HIM gate 与本地 judge proxy 契约差异（2026-10-26）

> 结论：当前 HIM gate 只是 **training-predicate screen**；本地 judge proxy 的 scene 也不是官方 ability_field 几何，不能当官方验收。job20/21 的 `screen_pass` 不能作为 Part2 得分/通过证据。

## 1. 为什么最初没用 judge

- HIM 线最初没有 HIM checkpoint 的 TorchScript 导出，也没有把 HIM policy 接进本地 judge；gate 只是训练环境的快速 screening。
- 训练 predicate 的注释写“matching strict judge”，但这是**手写的近似**，没有做 predicate contract diff；它考虑了四轮支撑、base height、lane 等，但没有 hold。
- 后来出现 gate 假测量、NameError 等工程问题，修复都集中在“gate 能否读到 term/生成 JSON”，没有回到“gate 是否等价 judge”这一层。
- 5 ms/4 dec 训练与 2 ms/10 dec judge 的差异，最初只用 `--physics deploy` 改 dt/dec，没有复制 solver 选项；后来才发现不完整。

## 2. Predicate 差异

| 类别 | HIM training predicate `_part2_terrain_state` | 本地 judge proxy |
|---|---|---|
| 所有类别 | 单步 bool；termination 命中即成功 | 需要 `hold_s` 连续保持（0.05–0.2 s） |
| high_wall | wall-relative `wx_min>=2.44 & rx>=3.0 & root_z>=clamp(wall_h+0.10,0.55)` | 还要求跨墙平面/爬升证据 `max_z_near >= wall_h+0.10` |
| stairs | 终点 wheel ground + root height | 还要求 `top_seen`（先到顶部平台） |
| trench | far-side plateau + root height | 还要求 near/far crossing + gap_entered/lane 证据 |
| plum | 平台 wheel band/root height | judge 走独立 plum 逻辑 |
| wheel drop | 无独立输出，`part2_failure` 近似 | judge 显式事件/落沟逻辑 |
| lane/out_of_course | training term 有 lane 终止 | judge 有 lateral/gap bypass 判负 |

因此甚至可能出现“training predicate 单步为真，但 judge 因未 hold/未 crossing 判失败”。

## 3. 物理差异

当前 gate `--physics deploy` 已复制官方 `<option>` 的大部分：

```text
euler / elliptic / sparse / newton
iterations=100 / ls_iterations=50 / ls_tolerance=0.01
impratio=100 / ccd_iterations=35
timestep=0.002 / decimation=10
robot init z=0.52
```

mujoco_warp 不支持 PGS，因此仍是 newton 近似；这本身也不能等价 judge。

## 4. 决策

1. gate 输出字段改为 `screen_pass`，并显式写 `acceptance_eligible=false`、`predicate=training_part2_v5_single_step`；
2. job20/21 已撤回，不再用 screen 结果当验收；
3. HIM TorchScript export + 本地 judge proxy adapter 已跑通；proxy 场景仍是团队参数化场景，不是官方 ability_field 几何；
4. gate 只用于低档粗筛，不写“通过”；官方分数仍需用官方 ability_field 场景重测。

## 5. job20/21 处置（2026-10-26 12:5x）

- job20（model0 screen）在运行中被 kill；已产生的 JSON 不完整，不能使用。
- job21（microfine）从 task-spooler 队列移除。
- 原因：screen predicate 不等价 judge，deploy physics 当时不完整；继续跑会得到“gate 过但 judge 不过”的误导数据。
- 重新入队前必须先完成：静态 preflight、judge adapter/export、predicate contract diff、完整 deploy physics。


## 6. 撤回时已产生的不完整 screen 数据（仅诊断，不验收）

job20 在 kill 前只完成 seed0 部分类别；结果为 training-predicate screen，不是 judge：

| category | train | deploy |
|---|---:|---:|
| platform | 17/20 | 17/20 |
| slope | 13/20 | 14/20 |
| stairs | 0/20 | 0/19 |
| high_wall | 20/20 | 20/20 |
| trench | 13/20 | 13/20 |

这组数据只说明 warm-start model_0 在 screen 下并不 row0 全过；不能写进验收，也不能证明本地 judge proxy 分数。job21 已从队列移除，未执行。
