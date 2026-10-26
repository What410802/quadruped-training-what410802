verdict：**CONCERN**  
blocker：**未发现新的 scorer blocker**（B1/B2/B3/B5 的 judge 代码本身未再构成“合法通过被误判失败”的结构性 blocker）；但 **route 层仍有 bridge_blocks 方向/出口错配**，且 **B1/B3 的两个新 conformance 用例实际未覆盖目标路径**，属于进入 C2 前必须清理的正式链路缺口。

> artifact 未附行号，以下按 `文件::函数/代码段` 定位，不臆造行号。

---

## 1. B1：离障落地门控

### 结论：**代码层 PASS，证据层 CONCERN**

`comp_part1_judge.py::_Obstacle.update` 中，1/2 足判罚仍是：

- `ground_fail and self._ground_penalty_active(xy, tags) and len(ground_feet) >= 2`

但新增了各障碍覆盖：

| 障碍 | 覆盖函数 | 复核 |
|---|---|---|
| `bridge_blocks` / `bridge_bands` | `TraversalBridge._ground_penalty_active` | `bridge_hits>=3` 且 `platforms>=2` 后关闭判罚；中途坠落仍会失败。代码 PASS。 |
| `gravel_pit` | `GravelPit._ground_penalty_active` | `gravel_hits>=3` 且 base 距出口短边 `<=0.35 m` 才关闭；中段双足触地仍失败。代码 PASS。 |
| `t_stairs` | `TStairs._ground_penalty_active` | `top + 至少 1 条完整臂` 后关闭；未完成臂前触地仍失败。代码 PASS。 |
| `slope` | `Slope._ground_penalty_active` | 累计投影 `>=1 m` 后关闭；不足 1 m 时触地仍失败。代码 PASS。 |

`height_bar` / `high_wall` / `slalom` 的 `ground_fail=False`，不受该门控影响，符合当前语义。

### B1 证据问题

1. **bridge_bands 没有独立 landing/mid-fall 用例。**  
   `comp_judge_conformance.py::test_bridge_ground_and_success` 只测了 `bridge_
