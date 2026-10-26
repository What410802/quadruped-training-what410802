# HIM 导出与本地 judge proxy 基线（2026-10-26）

## 1. 导出链路

新增 [export_him_policy.py](../../scripts/agent_scripts/export_him_policy.py)：

- 加载 HIM checkpoint 的 actor + source estimator；
- 通过 `HIMPolicy.as_jit()` 导出 TorchScript；
- 输入是 canonical 6×57 history，frame-major newest→oldest，flatten 342；
- 输出 16 raw actions；官方 HIM wheel action scale 为 FL/RL +10、FR/RR -10（`BlackWRunner` 默认 scale 正好一致，不能传 `--trained-blackw` 的 unsigned +10）。

导出 `job12/model_0.pt`（warm-start）为 `him_model0_policy.pt`，TorchScript dummy forward 通过。

## 2. 本地官方 judge 基线

使用 `prep.d/blackw_validation/run_blackw_part2_judge.py`（CPU MuJoCo、团队自定义 scene/判据、`hold_s`）测导出的 HIM policy。**这些 scene 不是官方 ability_field/map.xml 的几何复刻；total_score 只能当本地 proxy，不能当官方得分。**

- `model_0`（warm-start）：**total_score=410**
  - platform 10/20/30 success，40 fail；
  - stairs 10/15/20 success，30 fail；
  - slope 20 success，30/35/45 fail；
  - high_wall 10/20 success，30/40 fail；
  - trench 10/20 success，30 fail；
  - plum fail。

- `model_1499`（job12 末 checkpoint）：未加 invalid-state guard 前 proxy 输出 total560，但多个“success”出现 `base_z=-84` 等非物理状态（trench），invalid-state guard 已加入 judge runner 后重测为 total260；此前 560 作废，不能当真实分数。

结论：**本地 proxy judge 路径已经能跑 HIM policy**，但 scene 几何与官方 ability_field 仍有已知差异（stairs/slope/trench），不能作为官方通过证据；job12 末模型明显发散；gate screen 与 judge 不可互换。

## 3. 与 screen gate 对照

job20 的不完整 screen（model_0）与 judge 对比：

| category | screen (train) | judge |
|---|---:|---:|
| platform | 17/20 | 10/20/30 成功 |
| slope | 13/20 | 20° 成功 |
| stairs | 0/20 | 10/15/20 成功 |
| high_wall | 20/20 | 10/20 成功 |
| trench | 13/20 | 10/20 成功 |

**关键发现：stairs screen 0/20 是 false negative**。训练 predicate 的 stairs 逻辑要求穿越下台阶到 far end（旧硬编码 down_end 6.20，且要求 root height），而本地 proxy judge 的 stairs 只要求到达 top/landing；这不是“模型不会 stairs”的证据。

## 4. 当前判断

- 导出链路可用；
- judge 链路可用，但本地 judge runner 需要 invalid-state/out-of-bounds 守卫；
- 训练 predicate 的 stairs 与 judge 语义不一致，需对齐后再用于 reward/termination/screen；
- 在这些修复前，HIM 不恢复长训。


## 5. 2026-10-26 12:3x 修正

- 已修 stairs training predicate：旧逻辑要求穿越下台阶到 far end（约6.30 m），官方 judge 只要求到 top/landing（goal_x_min=3.3、top_z=step height）；screen stairs 从 0/20 变为 smoke 3/5。
- 修复时发现 `difficulty` 是 tensor，不能 `float()`，已改为逐 env 广播。
- 该 bug 属于路径语义错误，静态 lint 无法发现；已记录到 path trace。
