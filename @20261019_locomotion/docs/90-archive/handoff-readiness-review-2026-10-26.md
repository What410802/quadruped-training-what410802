# 交接就绪度评审（2026-10-26）

> 目的：回答"如果现在把仓库交给一位不熟悉对话历史的新执行者，他能否在 1 天内找到入口、理解目标、复现评测并开始干活"。本文件只做评审与建议，不代表已完成；具体修复按文末优先级排期。评审对象：`@20261019_locomotion/docs/`（57 份 md）+ `@20261024_blackw/README.md` / `training/README.md` + 关联脚本名与关卡文件。

## 0. 结论速览

- **入口存在但不可靠**：新执行者能找到 `part2-ppo-handoff-2026-10-26.md`，但会同时读到 3 份"计划/协议"文档（handoff、执行计划、blind-depth 课程计划）中互相重叠的 gate/随机化描述；这些描述在 2026-10-26 口径变更前已经漂移过至少两轮（8/8 → 覆盖集），只改一处就会留下旧协议。
- **最严重的问题不是"文档少"，而是"单一事实源缺失 + 状态/所有者未标注 + 评测协议还不可执行"**。这三条会让新执行者照着旧命令/旧口径跑出无效结论，重复我们今天踩过的坑。
- 建议优先做 4 件事（合计约 4–6 h，见 §4）：① 把新验收口径落成一份**可实现的评测协议 spec**（含采样伪代码/报告 schema）；② **单源化** gate/队列/部署契约，其余文档只放指针；③ 修掉**脚本名/关卡文件名/命令路径**的不一致；④ 给 active 文档加统一**元数据头 + INDEX**。

## 1. 事实盘点（本次实测）

| 项 | 实测结果 | 影响 |
|---|---|---|
| docs 数量 | `@20261019_locomotion/docs/` 下 57 份 md | 无索引，新人不知道读哪份 |
| 任务线混杂 | PPO/BC 线（`part2-*`、`blackw-*`）、HIM 线（`him-*`、`camera-depth.md`）、共享（`status.md`、`plan.md`、`comp/*`）在同一目录 | 边界只写在 handoff 一处；新人易改错线 |
| 重复事实 | "GPU 队列/task-spooler" 出现在 8 份文档；"gate 协议"至少 4 处；"部署契约"3 处 | 改一处必漏，口径漂移 |
| 机器相关路径 | 11 份文档含 `/home/bis` 或 `bis-ms7e56` 绝对路径/主机名 | 换人/换机直接失效 |
| 命令与脚本名漂移 | `competition-terrain-and-symmetry-plan.md` 引用不存在的 `export_history_policy.py`（远程现名 `export_blackw_policy.py`）；另有两套关卡 JSON：场景侧 `scenes/blackW/part2_levels.json`、judge 侧 `part2_official_levels.json`（键名/出生高度不同） | 照文档跑会找不到文件或跑错关卡集 |
| 过期协议文档 | `eval-protocol.md`（2026-10-20）写的还是 Part1 时代契约（45 维、12 关节、5 ms/4 dec），与当前 57 维/16 关节/2 ms/10 dec 不符 | 新人会按错契约做评测/部署 |
| 历史归档 | `part2-ppo-training-history.md` 已 500+ 行、按时间追加，旧结论未标失效（部分已在 2026-10-26 加"作废"标注） | 新人无法区分"当前真值"与"已推翻结论" |
| 文档头元数据 | 抽样 active 文档均无"owner / status(active 或 superseded) / last-verified / 关联代码 commit" | 无法判断新鲜度 |
| markdown 质量 | 仓库自带 checker 在 `comp/*` 有历史断链/表格问题（非本次新增）；active PPO 文档本次已自检 | 低优先 |
| 任务入口链 | handoff（入口）→ 执行计划（当前计划）→ history（归档）→ remote-training-workflow（队列）→ 各 task README；链条事实上存在但未在单一 INDEX 声明 | 新人需自行猜测顺序 |

## 2. 分级问题与建议

### P0（会让新人执行错误，必须先修）

1. **验收口径缺可执行 spec**：`执行计划 §0.3` 已写"覆盖集"原则与用户确认的边界（手柄范围、3D/90% 正态、穿模、前进为主、减速到停允许），但还缺：D（体长/宽/高）的实测数值、姿态/关节/速度偏移的具体分布、指令序列生成规则（如何从"前进为主"生成序列）、"可行穿越子集"逐障碍的形式化判定、held-out 划分、报告 JSON schema、部署侧同覆盖对拍流程。**建议新增 `part2-acceptance-eval-protocol.md`（纯 spec，含伪代码 + 示例 JSON），并让 §0.3 只保留原则与指针。**
2. **单源化**：gate/评测口径只在 spec 里写一次；handoff §3.4、执行计划 §5、blind-depth §3、`eval-protocol.md` 全部改成"见 spec §X"；`eval-protocol.md` 顶部加"已部分被 Part2 spec 取代"标记。**队列协议单源到 `remote-training-workflow.md`；部署契约单源到 `@20261024_blackw/README.md` 的部署章节。**
3. **命令/脚本/文件一致性**：全仓 grep 不存在的脚本名、两套关卡 JSON、旧参数（`--jitter-*` 旧 gate、`--command-set` 三档）；每份含命令的文档末尾附"本次验证日期 + 执行机器 + 实测输出一行"。
4. **文档元数据 + INDEX**：每份 active 文档头部 4 行——`作用 / owner（PPO|HIM|共享）/ status（active|superseded|draft）/ last-verified（日期 + 关联代码 commit）`；`docs/training/INDEX.md` 声明阅读顺序、每份文档角色、边界（哪条线负责哪些文件）。

### P1（明显降低交接效率）

1. **"当前真值"一页纸**：从 history 抽出 8–10 条仍然有效的结论（judge 750 的组成、楼梯/斜坡/壕沟状态、已作废结论清单、当前最优 checkpoint、下一步 A6 实验），单独成页；history 只做归档。
2. **快速开始（quickstart）**：环境（pixi/ros2-build）、本机 judge 跑一关、远程 GPU 队列加入（含 `TS_ONFINISH` 设置）、导出 policy 并安装到部署目录、跑 headless 自检——5 条命令以内；路径用 `<REPO>`/`$HOME` 变量而非绝对路径。
3. **失败案例/坑清单**：把本次审计的 P0（DR 丢失、lr 1.5e-5 覆盖、谓词覆盖、sim 力矩 20 N·m、contract 右轮符号、config key 不符）写成"已知坑 + 检查命令"一页，新人上手先跑一遍。
4. **代码-文档版本锚**：文档里引用代码/脚本时写"文件:行 + 对应 commit 短 hash"；对远程训练仓写 fork commit；快照目录 `training/` 标注"只读快照，不可执行"（审计 F13）。
5. **产物登记表**：`prep.d/results/**`、`models/**`、视频/JSON 的"产生命令 + 日期 + 输入策略 sha256"统一登记（现有 `models/comp_bc_v5/manifest.json` 是好的样板）。

### P2（体验/长期）

1. `docs/training/` 按线分子目录（`ppo/`、`him/`、`shared/`），文件名保留日期后缀；迁移时全仓搜引用。
2. 术语表：judge v5、覆盖集、gate、可行子集、canonical、held-out、warm start、spec/plan/history 的角色。
3. `comp/*` 历史 markdown 问题要么修要么归档到 `comp/archive/` 并加 index。
4. CI：`check_md_links.py` + 新增两个 grep 门——active 文档禁用绝对路径/主机名；active 文档禁用已作废数值指标（`8/8`、`16/16`、`<1%` 只允许出现在"已作废"横幅里）。

## 3. 推荐的阅读顺序（应写入 INDEX）

1. `part2-ppo-handoff-2026-10-26.md`（入口：目标、边界、当前状态）→ 2. `part2-ppo-execution-plan-2026-10-26.md` §0（结论/口径/TODO）→ 3. `part2-acceptance-eval-protocol.md`（验收 spec）→ 4. `remote-training-workflow.md`（队列/机器）→ 5. `@20261024_blackw/README.md` 部署章节 → 6. `part2-ppo-training-history.md` 的"当前有效结论"页（历史细节按需查）→ 7. `part2-blind-depth-curriculum-plan.md`（深度侧）。

## 4. 建议排期（文档改动，不含实现）

| 优先级 | 动作 | 预计 | 产出 |
|---|---|---|---|
| P0 | 写 `part2-acceptance-eval-protocol.md`（含采样伪代码、可行子集判定、报告 schema、held-out） | 2 h | 新文档 + §0.3 改为指针 |
| P0 | 单源化 gate/队列/部署契约（4 处改指针） | 1 h | 4 份文档 diff |
| P0 | 修命令/脚本/关卡文件名不一致 + 每份命令文档加"验证日期/机器" | 1 h | grep 清零 |
| P0 | 文档元数据头 + `INDEX.md`（含线归属/角色/阅读顺序） | 1 h | 每份 active md + INDEX |
| P1 | "当前真值"页 + quickstart + 已知坑清单 + 产物登记 | 2–3 h | 3 份新文档 |
| P2 | 目录分流/术语表/CI 门 | 1–2 天 | 结构改造 |

## 5. 本次已顺带完成的样板

- 新验收口径已单点写入执行计划 §0.3；handoff §3.4 重写为指针 + 执行要点；blind-depth 与 history 加作废横幅；旧 8/8/16/16/<1% 从 active 文档移除（横幅只保留作废说明）。
- 新增部署工具时同步了 README/文档：`import_blackw_policy.py`、`check_policy_dirs.py`、canonical config 模板。
- 审计闭环产出的两份报告放在 `prep.d/audits/`，是"文档-代码一致性"检查的实际样例（新执行者可先读它们了解已知坑）。

## 6. 明确的残余风险（交给新人前必须知道）

- `docs/status.md` / `docs/plan.md` 是共享状态文件，当前由另一条线（HIM）更新；PPO 线的最新状态以 `part2-ppo-execution-plan §0.2` 为准，两边可能短暂不同步。
- 远程训练仓（`~/rc_work/part2_team_race`）与本地快照（`@20261024_blackw/training/`）不是逐字节镜像；文档引用代码时必须写"本地快照/远程仓"二选一。
- 本轮审计后仍存在未修项（部署 F2 smoke、导出 config、job 出口契约、judge fail-open 等，见历史 §19.5）；交接文档应把"未修项"与"已修项"分开列，避免新人把未修项当已修。
