# Part2 验收协议（覆盖集口径；2026-10-26 用户确认）

> 本文件是 Part2 验收的唯一权威定义；其他文档只放指针。**状态：协议已确认，评测工具改造未实施**（按用户要求先写文档）。旧的"8/8、16/16、<1% 失败率"均为自拟指标，已作废。

## 1. 目标

不是刷分，而是：**任意站立初始状态 × 任意可发指令都稳；对"按合理操作路线能穿越"的指令子集必须真的穿越**；训练最后若干轮必须在 held-out 覆盖集上同样成立。

## 2. 覆盖集定义

### 2.1 指令范围 = 手柄 + 线性映射

- 代码依据：`launch/rl_sim_blackw.launch.py` 的 `joy_command_scale` 默认 **1.5**；`src/rl_sim.cpp:394-396` 把摇杆 axes（归一化 [-1,1]）映射为 `LY→v_x、LX→v_y、RX→ω_z`，乘 1.5。
- 因此指令包络：**`v_x, v_y ∈ [-1.5, 1.5] m/s`，`ω_z ∈ [-1.5, 1.5] rad/s`**，包含**倒车**与**原地转向**。
- 两个子集分开报告：
  - **稳定性集**：任意指令序列（含倒车/原地转向）→ 只要求**全程不摔倒**。
  - **可穿越集**：**以前进为主的合理指令序列**（前进 + 横向/航向修正；允许障碍前减速到停）→ 要求**实际穿越成功**。

### 2.2 初始状态 = 正态采样，90% 落在 3×对应方向尺寸内

- 以机器人自身对应方向尺寸 D 为基准：`D_x=体长、D_y=体宽、D_z=体高`（站立姿态几何包围盒；数值由模型实测定稿后写入本文件）。
- 位置偏移 `r = (r_x, r_y, r_z)` 采样：正态，**90% 质量落在 `[-1.5D, +1.5D]`**（即范围宽度 3D），对应 `σ = 1.5D / 1.6449`。
- 姿态/关节角/速度偏移用同量级正态采样（角度范围待用参考仓库惯例补定；先沿用训练 reset 的关节 offset/速度量级）。
- **穿模检查**：采样后与障碍/场景几何不得穿插；越界或穿插 → **重采样**。
- 样本必须处于可站立状态；每个 case 记录采样种子、初始位姿/关节/速度。
- held-out：覆盖集分 train/eval，评测只用 eval 集。

### 2.3 "可行穿越子集"的判定

- 对每个障碍，按"合理路线"定义参考操作剖面族（示例见 §4），判定某 case 是否可行：① 初始状态在评分车道与障碍接近段之内；② 指令序列属于该障碍的合理剖面族（前进为主、速度在包络内、允许减速到停）；③ 不存在绕障碍外侧、逆向通过、跳跃/蹭墙等非操作手行为。
- 判 success 用权威 judge 的终态谓词（`eval_blackw_part2.py` / judge v5），不用训练环境 termination 计数。

## 3. 判定

| 要求 | 通过条件 |
|---|---|
| 稳定性 | 覆盖集（eval）内**零摔倒/零失效**；任何一次失败都算待修项 |
| 可穿越性 | 可行子集内**全部成功穿越**；逐 case 报告失败清单 |
| 强鲁棒 | 训练最后若干轮在 **held-out** eval 集上同时满足以上两条 |
| 部署一致 | 部署栈（rl_sar smoke，见 `deployment-contract.md`）用同一覆盖定义对拍；逐 case 差异必须解释（物理/时序/限幅） |

**不设固定通过次数/百分比门槛。** 采样密度、初始状态范围、剖面族是实验设计，不是"分数指标"。

## 4. 参考操作剖面（用于定义可行子集，非硬编码 gate）

- platform：vx≈0.5 m/s 直行；
- high_wall：vx 0.65 m/s，x≈1.6 m 后降到 0.35；
- slope：vx≈0.3 m/s；
- stairs：vx 0.75 m/s，x≈1.1 m 后降到 0.45；
- trench：vx≈0.3 m/s；
- 允许障碍前减速到停；允许小幅横向/航向修正（不越出评分车道）。

## 5. 报告格式（建议 JSON schema）

```json
{
  "policy": "<name>",
  "policy_sha256": "...",
  "protocol": "part2-acceptance-2026-10-26",
  "level": "stairs_20cm",
  "cases": [
    {"seed": 123, "initial_state": {...}, "command_sequence": [...],
     "kind": "stability|traversal", "feasible": true,
     "judge_status": "success|fail", "judge_reason": "...",
     "detail": {"max_z": 0.0, "min_wheel_z": 0.0, "x_end": 0.0}}
  ],
  "summary": {"falls": 0, "traversal_feasible_total": 20, "traversal_success": 20,
              "failing_cases": []}
}
```

## 6. 工具状态与待办（未实施）

- 现有 `eval_blackw_part2.py` 只支持固定 `--attempts/--command/--jitter-*`；`gate_stage.py` 是旧协议。
- 待实现：覆盖集采样器（正态+穿模重采样）、稳定/穿越两个子集生成、逐 case JSON、held-out 划分、部署 smoke 对拍（`smoke_deploy_part2.py`）。
- 训练后自动评测：每个候选 checkpoint 跑 eval 覆盖集；以"零摔倒 + 可行子集全过"决定保留/晋升。

## 7. 参考实现

- mjlab `reset_root_state_uniform`（远程 `.venv` 的 `mjlab/envs/mdp/events.py`，支持 x/y/z/roll/pitch/yaw 范围，内部 `_sample_se3_range`）。
- IsaacLab / legged_gym 的 init-pose randomization 惯例；本仓库其他任务 reset 采样实现可参考。
