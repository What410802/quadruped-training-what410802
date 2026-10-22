# 开发过程运维约定（DEV_OPS，非最终交付文档）

> 本文件记录开发/实验期间的运行环境约定与路径规范，不属于最终对外文档。
> 适用仓库：`RoboCon/MyMonoRepo.d`（任务仓）与本机 `RoboCon/prep.d`（工作区，仓库外）。

## 1. 远程机使用标志（5060ti）

- 路径：`~/5060ti_machine_use_flag.txt`
- 内容：`0` 或 `1`（最多一个尾随换行）；**执行者（agent）写，用户读**。
- 语义：
  - `0`：本轮已用完，**可以关机**（正常情况下保持 0）；
  - `1`：需要保留远程机（例如正在跑远程训练/长评测），**用户不会关机**；
    但执行者必须在 **0:30 前置回 0**，之后由用户关机。
- 管理规则：
  1. 默认保持 `0`；只有在确实启动需要远程机的任务时才置 `1`，并在任务结束/放弃后立即置回 `0`；
  2. 跨零点仍然需要机器时，仍按"至少 0:30 后置 0"执行；
  3. 不把该标志写进最终交付文档，只在本开发文档与 `AGENTS.md` 类开发指引中提及；
  4. 读取方（用户）若看到 `1`，会在 0:30 后等待置 0 再关机。
- 当前状态（2026-10-22）：`0`（本轮评测/实现全部在本机完成，未使用远程机）。

## 2. `prep.d` 路径规范（重要）

本机曾出现两个 `prep.d`：

| 路径 | 状态 | 说明 |
|---|---|---|
| `RoboCon/prep.d/` | **唯一规范位置** | 1.5 GB 工作区（assets/models/results/runs/scripts/logs…），在 `MyMonoRepo.d` git 仓库之外 |
| `RoboCon/MyMonoRepo.d/prep.d/` | **已删除** | 早期 cwd 混乱产生的陈旧副本（仅 2 个 result JSON，16 KB），已归档后删除 |

- 规范写法：从 `RoboCon/` 根出发引用 `prep.d/results/<name>.json`；
  从任务目录（`MyMonoRepo.d/@20261019_locomotion`）出发用 `../../prep.d/results/<name>.json`。
- `MyMonoRepo.d/.gitignore` 已忽略 `prep.d/`；**不要在 MyMonoRepo.d 下新建 prep.d**。
- 2026-10-22 处理：把陈旧副本的两个 JSON 复制到
  `RoboCon/prep.d/results/_archive_dup_20261022/` 后删除 `MyMonoRepo.d/prep.d/`。
  注意其中 `part1_zero_shot.json` 与规范位置同名文件内容不同（历史版本），归档保留以免丢失。
- 新增结果 JSON 默认写入 `RoboCon/prep.d/results/`；评测产物（comp/eval）仍入库。

## 3. 本机 vs 远程机

- 2026-10-22 起的 judge V2/V2.1、场景 v2、Part2 evaluator、course 协议与诊断评测都在本机完成
  （CPU MuJoCo + TorchScript，无需 GPU）。
- 训练/大规模评测仍按 `comp/PLAN.md` 走远程 GPU；此时按 §1 管理标志。
