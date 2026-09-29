# AGENTS.md —— 面向 AI 助手的仓库规范（仓库记忆）

> 这是**给 AI 助手看的**最小必要版规范；人向的完整约定在 [`docs/conventions.md`](docs/conventions.md)，
> 两者不重复：本文只写"助手每次动手前必须知道、且容易做错"的那些。
> 仓库内容（架构说明、实现思路、实测数据、学习记录）放各处的 Markdown，不放这里。

## 每次开始时

1. 读 [`docs/conventions.md`](docs/conventions.md)（提交 / 文档 / 目录 / 环境 / 验证五节），再读**当前任务目录**的
   `README.md`（入口）、`docs/status.md`（做到哪、下一步、阻滞项）与其 `docs/` 下的细节文档。
2. 判断改动落在哪一层：仓库 `docs/`（换个任务也成立）还是任务目录（只对这份模型/这次验收成立）——
   判定标准见 conventions §7；**同一句话只写一处，其他地方放飞指针**。

## 提交（commit）

* 信息：**一行英文**，`type(scope): 一句话`（`feat`/`fix`/`docs`/`refactor`/`build`/`chore`/`test`）；不写正文。
* **AI 助手只准备信息与命令，不代为提交**（要提交时给出可直接粘贴的 `git add` + `git commit` 命令）。
* **不写 AI 署名**：提交信息里不放 `Co-authored-by: Copilot …` 之类；"AI 参与了什么"记在任务 README。
* 分阶段提交（搭环境 / 加载模型 / 加控制 / 整理结构 / 补文档分别提交），提交前确认待提交文件。
* **历史可以改写**：本仓库不额外偏好"永不改写已推送历史"（与普通 Git 仓库一致）；改写（含 `--force-with-lease`）
  前先说明原因、建一个备份分支，改完核对"内容没变、只是信息/SHA 变了"，并删掉备份分支。

## 文档

* 每段**单行**（不按宽度硬折行）；代码围栏内逐字节保持原样；图示用 Mermaid。
* 文档里出现的路径、目录树**必须与仓库实际一致**；移动/重命名文件时**全仓搜引用**并把对方改对。
* 结论必须带**可复现命令**与**实测数字**；引用外部代码给 `文件:行`。
* 文档改动后自检：`pixi run python @20260927_motor/scripts/agent_scripts/check_md_links.py <任务目录>`
  （断链 / 锚点 / 表格列数）。

## 代码与环境

* C/C++ 一律 **4 空格、不用 Tab、`.clang-format` 说了算**（`ColumnLimit: 0` = 不自动折行）。
* 环境只有仓库根 [`pixi.toml`](pixi.toml) 一个：用 `pixi run …`；**不写死绝对路径**，
  外部只读资源按"与本仓库根同级"（如 `ReadOnly.d/unitree_actuator_sdk`）推算。
* 改完代码/脚本要跑**对应的自检**并在文档里更新状态：C++ 侧用各任务的 `--self-test`（不接硬件就能跑），
  Python 侧用 `scripts/agent_scripts/` 下的分析脚本。
* 用外部代码/资料时保留来源说明（BSD-3-Clause 的宇树 SDK、Apache-2.0 的 MuJoCo 官方示例等）。

## 不要做

* 不把编译产物、缓存、大二进制提交进仓库（`.gitignore` 已覆盖 `build/`、`.cache/`、`__pycache__/`、`.pixi/`）。
* 不在没有测量/复现的情况下写"更快、更准"这类结论；不确定就写"待实机验证"并记进所在任务的清单。
* 不擅自改别人的施工区：动手前先看 `git status`，只改本次任务范围内的东西。
