## verdict：FAIL

不是 CONCERN。当前仍有一个可被利用的 Part1 假成功，属于 scorer blocker；因此**不同意**“flash 与 pro 两轮均无问题”，也不能在修复并重新通过两轮前申请 Codex G1。

---

## 1. 独立核验：Part1 仍有可被利用的假成功

### 1.1 Blocker：高墙 `HighWall` 未把穿越约束在墙体 x 段内

**证据链：**

- `scripts/agent_scripts/comp_part1_judge.py` 的 `HighWall._on_sample` 记录了 `prev_x`，但后续逻辑没有使用 `prev_x`：
  - 只判断 `prev_y -> y` 是否跨过 `WALL_CROSS_Y = -7.0`
  - 只要求 `self._last_z >= 0.60`
  - 然后 `cross_valid += 1`
- `HighWall._check_exit` 只检查：
  - entry 是否为 `ymin/ymax`
  - exit side 是否 opposite
  - `cross_valid >= 1`
  - **完全没有检查穿越点的 x 是否在墙体真实范围内**
- 场景 `assets/terrain/part1/part1_eval_scene_v2.xml` 的高墙：
  - `pos="1.8 -7.0 0.15"`
  - `size="0.025 0.5 0.15"`
  - `quat="0.7071068 0.0 0.0 0.7071068"`
  - 绕 z 旋转 90° 后，墙在 x 方向的大概范围是 `[1.3, 2.3]`
- 但 `ZONES["high_wall"] = (1.25, 2.35, -7.85, -6.15)` 比墙段宽。

**可利用路径示例（judge 直接输入，不依赖实际物理碰墙）：**

```text
x=1.25, y=-8.00, z=0.45   # 从 ymin 外进入 zone 外
x=1.25, y=-7.60, z=0.65   # 进入 zone，抬升 base z
x=1.25, y=-7.00, z=0.65   # 跨过 WALL_CROSS_Y，raised=true
x=1.25, y=-6.60, z=0.45
x=1.25, y=-6.00, z=0.45   # 从 ymax 离开
```

`HighWall._check_exit` 会返回 `(True, "")`，即使这条路径在墙 x 段外、没有 `wall` 触碰、也没有真正越墙。

`comp_judge_conformance.py` 当前的 `test_high_wall_sideways_climb_and_bypass` 只覆盖了：
- 沿墙走
- x=1.8 地面高度穿墙
- x=1.8 碰墙但地面高度
- x=1.8 抬升穿越成功

**没有覆盖“x 在墙段外、抬升穿越”的假成功用例。**

因此这是 `HighWall` 语义未闭合，属于可利用的假成功。

---

## 2. 其他 Part1 障碍：未发现新的明确 blocker

### 2.1 限高杆 / 落杆

- `HeightBar._pre_sample` 全程跟踪 `bar_base_seen`，只要首次观测后下降超过 `BAR_DROP_THRESHOLD_M = 0.05`，即持久标记 `bar_dropped_seen`。
- `HeightBar._on_sample` 要求门洞 x `[5.2,6.2]` 内连续跨过 y=-9。
- 未发现“预掉落洗掉”“门外穿越后横移”类假成功。

### 2.2 桥 / 砂砾坑 / 斜坡 / 绕杆

- `TraversalBridge` 需要 bridge hits、两个 platform tag，并要求入口/出口 opposite。
- `GravelPit` 需要 y 侧短边进、对侧 y 出，且至少 3 次 `gravel` 接触。
- `Slope` 只累计 slope tag 期间的 y 投影距离，横移不计，`distance >=1.0` 才成功。
- `Slalom` 有起点圆、顺序、corner checkpoint、end area、alternating sides。

当前 conformance 没有暴露这些障碍的明确假成功。

### 2.3 T 台阶部分分

- `TStairs._check_exit` 在 `_complete_arms()` 非空时可成功，`_score_for()` 对一条完整臂给部分分：
  - `s` 臂：`partial_up`
  - 其他臂：`partial_down`
- 默认 `Part1JudgeV2(partial_up=50.0, partial_down=33.0)`，符合 Q2 ×2/3。
- 但 conformance 只测了一条 `s` 臂升级为满分，没有测仅 `n` 臂或仅 `e` 臂是否按 33 判分。
- 这不是当前 blocker，但 Codex 应复核“上/下”与 `s/n/e` 臂的映射是否正确。

---

## 3. Part2 六类：暂未发现明显 lane 绕过假成功

- `Part2JudgeV2._lateral_ok` 限制了 lane ±0.7。
- `wall` 要求 `wall_crossed` + `wall_contact` + 高 z；且 lane width 小于墙宽，绕行风险较低。
- `gap` 要求跨 near/far 边，`plum/platform/stairs/slope` 都要求对应 foot tag + `not ground_feet`。

未发现新的 Part2 blocker。但“官方能力场逐档交叉核对”仍然是残余风险。

---

## 4. 尝试协议与账本：整体通过

- 整场 runner `run_part1_course.py::run_policy_step` 每个 policy action 拆成 4 个物理步，每个物理步都 `feed()`，确认逐物理步采样。
- 暂停循环只推进 operator fake 时钟和事件，不调用 `course.update`，没有继续喂 judge。
- `StableStopTracker` 使用 `model.opt.timestep`，不是 policy dt。
- `Part1Course.update/abort_attempt` 用 `last_sim_t` 作为账本时钟，暂停期间物理冻结，duration 天然排除暂停。
- `AttemptManager.note_recovery` 不消耗 attempt；`skip` 消耗 attempt。
- `Part1Course.summary` 与 `AttemptManager.summary` 的 `final_time` 为最高分尝试内最快。
- 证据目录中有：
  - `part1_course_pause_resume_drill.json`
  - `part1_course_abort_drill.json`
  - `part1_course_pause_timeout_drill.json`

账本结论：**当前诊断链路可用**。

---

## 5. 证据链

### 5.1 四份 eval 产物 summary 能否由 trials 复算

当前四份产物：

- `flat-ft-2500-part1-diag-v2`
- `flat-ft-2500-part2-diag-v2`
- `flat-ft-2500-part2-official-diag`
- `flat-ft-2500-part1-course-diag`

在当前数据下：

- Part2 `best_success_value` 全为 `null`，trials 全 fail，attempts_used 与 trials 条数一致。
- course diag 的 part1 `final_score=0`、`final_time_s=94.18` 可由 trials 中三个 attempt 的 duration 重新算得。
- Part1 diag 每个障碍一条 fail trial，summary success=false，可与 trial 对应。

**当前诊断产物可复算，没有发现现有分数被手改。**

### 5.2 HASHES 覆盖

`comp/audits/HASHES.json` 名义上 60 objects，覆盖了：

- judge / contract / protocol
- level XML
- 四份 eval 的 manifest/trials/summary
- 三份 pause/abort/timeout evidence

但仍缺：

- `assets/terrain/part2/ability_field/part2_ability_field.xml`
- `assets/terrain/part2/part2_plum_eval_scene.xml`

这些场景在 manifest 中有引用，尤其 `flat-ft-2500-part1-diag-v2` 的 `scenes.part2` 指向 ability field。

因此 HASHES 覆盖不完整。虽然当前不是正式分数依据，但 G1 前应补齐。

### 5.3 comp_score 机器复核

`comp_score.py` 已接入：

- `validate_external_evidence` 并被 `score_one` 调用
- scenes / judge.file_hashes / contract sha256 重算
- Part2 合法档位检查，bool 只认 `1.0`
- Part2 formal attempts_used vs trials 无条件 error
- 重复 trial_id 检查
- Part1 final_time 从 trials 按 attempt 复算

仍存在两个正式链路上的缺陷：

1. **Part1 attempts_used 没有全局按 distinct attempt 对账**
   - `validate_summary` 对 Part1 障碍级 attempts 仍主要是 warning。
   - 没有正式错误检查 `summary.part1.attempts_used` 是否等于 trials 中实际出现的不同 attempt 数。

2. **`validate_external_evidence` 复算 Part1 final_time 时，`full` 初始为 True，只在与分数不足时置 False，不会检查该 attempt 是否覆盖全部 Part1 障碍。**
   - 极端情况下，缺失障碍的 attempt 仍可能被当作 full attempt 参与 return bonus 复算。

这两个不是当前诊断产物的 blocker，但正式 scoring 前应补严。

---

## 6. 是否同意申请 Codex：no

原因：独立 pro 复验发现 Part1 `HighWall` 仍存在可被利用的假成功，不满足“pro 无问题”。

最小修复：

1. `HighWall` 增加墙段 x 约束：
   - 穿越 `WALL_CROSS_Y` 时，`x` 必须落在真实高墙 x 范围内；否则不产生 `cross_valid`。
   - 可以从 scene 固定墙段，或用现有 `prev_x`/`prev_y` 直接校验。
2. 增加 conformance 反例：
   - `x` 在墙段外但 z≥0.60 的 y 向穿越不得成功。
3. 补 HASHES 对象：
   - `part2_ability_field.xml`
   - `part2_plum_eval_scene.xml`

修复后，需要重新跑 conformance / 重新生成 HASHES，然后再由 flash 与 pro 两轮复验无问题后，才可申请 Codex。

---

## 7. 若修复后送 Codex，重点复核项

1. **Part1 高墙墙段 x 约束**：修复是否真正阻断侧边抬升假成功，且合法攀爬不被误判失败。
2. **T 台阶 `s/n/e` 部分分与 Q2 上/下对应**：当前只测 s 臂，未测 n/e 臂。
3. **Part2 官方能力场交叉核对**：当前只有参数化 level，官方场校验仍缺。
4. **comp_score 论证链**：Part1 attempts_used 与 distinct attempt 对账，final_time 复算的“完整尝试”定义。
5. **HASHES 场景覆盖**：是否已包含 Part2 ability field 与 plum 场景。

---

## 8. G1 报告必须写明的残余风险

1. 砂砾坑真实几何仍未 recut，本地是凸起盒代理。
2. Part2 官方能力场逐档交叉核对仍未完成。
3. 正式手动 3 次尝试演练仍未在真实赛程上做，目前主要是脚本化诊断。
4. soft-reset 阈值与相邻 zone 重叠仍为启发式。
5. 跨 attempt 模拟器时间从 0.5 重置，事件时间线不可全局排序。
6. Part2 official 重复最高档时，确定性策略下重复结果统计意义有限。
7. T 台阶“上/下”与三臂映射的书面确认仍建议留痕。
