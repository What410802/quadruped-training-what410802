# HIM 主链路代码审查（2026-10-26，无 GPU 部分）

> 范围：只审 HIM 训练/评测实际用到的代码；不做全仓无差别审查。远程机只跑 CPU 配置检查，不占 GPU。

## 1. 审查范围

- `tasks/velocity/blackw/env_cfgs.py`
- `tasks/velocity/black/him.py`
- `tasks/velocity/black/him_rl_cfg.py`
- `tasks/velocity/blackw/him_rl_cfg.py`
- `algorithms/him/{policy,ppo,estimator,storage,spec,warm_start}.py`
- `tasks/velocity/blackw/him_runner.py`
- `scripts/agent_scripts/him_part2_gate.py` / HIM job 脚本

## 2. 发现与处理

| 问题 | 状态 |
|---|---|
| gate 用 `play=True`，play 配置无 strict part2 term，success 恒 0 | 已修；`play=False` + assert + `--check-config-only` |
| warm start 不恢复 `distribution.std_param`，实际 fresh std=0.3 | 已修：`BLACKW_HIM_INIT_STD` 默认 0.1，并打印 warning |
| HIM 没有 teacher anchor | 已加可选 `BLACKW_HIM_ANCHOR_ALPHA`；0 表示关闭，warm start 时 snapshot teacher |
| HIM 没有冻结 std 的训练模式 | 已加 `BLACKW_HIM_FREEZE_STD=1` 冻结 warm-start/init std；`precheck` 保留旧语义 |
| reward 权重只能在代码里改，无法做 gate A/B | 已加 `BLACKW_PROGRESS_W` / `BLACKW_CLIMB_W` / `BLACKW_CLEAR_W`，默认值不变 |
| job 无 SIGTERM/verdict/预检 | job14 已加 trap/verdict；gate 增 `--check-config-only`；后续 job 统一先预检 |
| HIM 5 ms/4 dec 与部署 2 ms/10 dec 未对齐 | **未修**；下一轮必须显式评测，不改默认训练物理 |
| 绝对 progress/高度 shaping 可能奖励“终点附近停留” | **未改默认**；记录为 A/B 假设，先做权重/potential-based 对照 |
| HIM 没有官方 judge/export | **未修**；列 P1，训练谓词通过后再做 |

## 3. 无 GPU 验证

### gate 配置预检（5 类）

```bash
for c in platform slope stairs high_wall trench; do
  .venv/bin/python him_part2_gate.py --task blackw-official-him \
    --category "$c" --row 0 --check-config-only
done
```

结果全部包含：

```text
terms=[... part2_success, part2_failure, nonfinite_state]
episode_steps=1000
```

### init std 配置

```bash
BLACKW_HIM_INIT_STD=0.05 python -c 'load_rl_cfg("blackw-official-him")...'
# init_std = 0.05
```

### 静态检查

- `python -m py_compile` 通过：gate 脚本、HIMPPO、HIMPolicy、HIMEstimator、env_cfgs、him_runner；
- `bash -n` 通过：job14 重测脚本；
- 文档链接检查通过。

## 4. 仍待 GPU/真实环境验证

- anchor alpha 的实际效果（0 / 0.01 / 0.05）；
- init std 0.1 是否足够探索；
- reward 权重 A/B（progress/climb/clear）；
- gate 20/20 与官方 judge；
- 2 ms/10 dec 部署物理复测；
- HIM 导出 TorchScript。

## 5. 2026-10-26 12:05 回归修复

- `him_part2_gate.py` 的 JSON 输出引用了未定义 `wheel_drop`，导致 job14 的 155 次 gate 全部 rc=1、无 JSON；这是修复 `out_of_course` 字段时引入的回归。
- 已修：`out_of_course` 用真实计数；`wheel_drop` 显式 0（strict `part2_failure` 已覆盖落沟）；增加 `gate_pass`、`success_rate`、`physics`、`jitter`。
- 修复后 smoke：model_0 platform，1 attempt，train physics，1/1 success，JSON 正常，`gate_pass=true`。
- 旧 job14 结果作废；新 job20 用 model_0 ×5 类 ×20 attempts ×2 seeds ×train/deploy 重建基线。
- 所有 HIM job 现在必须 fail-loud：gate rc!=0 或无 JSON 时 job 退出非零。

## 6. 2026-10-26 12:10 补充

- gate 新增 `--command-scale`（0.6/1.0/1.3× 包络）、`--jitter-x/y/yaw`、`--physics deploy`（2 ms/10 dec）。
- 当前 job20 先跑 1.0× 基线；包络扫描作为下一组 gate，避免一次 job 过长。
