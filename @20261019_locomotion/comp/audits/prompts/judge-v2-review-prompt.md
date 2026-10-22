# 评审任务：RoboCon 2026 队内赛评测器 V2（Part 1 / Part 2）

角色：独立评审者。你是被测代码作者之外的第三方；只依据下面列出的文件做判断，不要相信作者的口头结论。
这是 **G1 重审前的 BYOK 预审（provisional）**，最终 G1 由不同家族的 Codex 复核；你的任务是把问题找全、给出可操作的修复清单。

## 背景（只给事实，不给结论）

- 比赛：RoboCon 2026 队内赛，仿真四足，两个赛项。
  - Part 1 障碍赛：8 个障碍（绕杆 slalom、砂砾碎木坑 gravel_pit、高墙 high_wall、限高杆 height_bar、T 形台阶 t_stairs、10° 斜坡 slope、方墩桥 bridge_blocks、窄带桥 bridge_bands），每个 100 分；越过全部障碍并返回出发区额外 +100（满分 900）；整场 3 次尝试；可手动遥控。
  - Part 2 能力测试：高台 high_platform、楼梯 stairs、斜坡 slope、高墙 high_wall、沟壑 trench、梅花桩 plum 六类；分数曲线、按成功难度计分（满分 1300）；每项 4 次；必须 RL 训练，不能用固定动作/状态机；稳定性目标 0 失败、无计时压力（优化阶段先按失败比例）。
- 规则原文：`docs/training/team-race-2026.md`。
- 主办方 2026-10-22 的补充口径：`comp/audits/JUDGE_AUDIT.md` §9 与 §9.1（含恢复不消耗尝试、最终时长取 3 次最快、T 台阶部分分上=75×3/2 下=50×3/2、10 cm 端点 0 分、小数舍去、深度相机优先等）。
- 上一版 judge（V1）在 2026-10-22 的 G1 审计里被判 FAIL（报告同上 §8），本次 V2 的目标是修复它。

## 要审的文件（只给路径，自己读）

评测器实现：
- `scripts/agent_scripts/comp_part1_judge.py`
- `scripts/agent_scripts/comp_judge_conformance.py`
- `scripts/agent_scripts/comp_part1_course.py`
- `scripts/agent_scripts/comp_part2_judge.py`
- `scripts/agent_scripts/make_part2_levels.py`
- `scripts/agent_scripts/run_part1_judged_rollout_v2.py`
- `scripts/agent_scripts/run_part2_judged_eval.py`
- `scripts/agent_scripts/comp_import_diagnostic.py`
- `scripts/agent_scripts/comp_import_part2_diag.py`

场景与配置、产物：
- `assets/terrain/part1/part1_eval_scene_v2.xml`
- `config/part2-levels.json`
- `comp/eval/flat-ft-2500-part1-diag-v2/`（manifest.json、summary.json、trials.jsonl）
- `comp/eval/flat-ft-2500-part2-diag-v2/`（manifest.json、summary.json、trials.jsonl）

规则与协议：
- `docs/training/team-race-2026.md`
- `comp/CONTRACT.md`、`comp/CONTRACT.json`
- `comp/eval/_protocol.md`
- `comp/audits/JUDGE_AUDIT.md`（§8 上轮 FAIL 报告、§9/§9.1 主办方口径）

## 评审要求

1. **成功语义/可欺骗性**：Part 1 每个障碍是否存在"没有合法进入/实际跨越/合法离开却拿到 success"的路径？特别关注：
   - 仅靠位姿区域/出口位置骗分；
   - T 台阶跨帧 history 是否真的要求每级接触、两分支/单分支部分分是否符合口径；
   - 限高杆：碰柱/碰杆是否误判失败、落杆是否可靠检测、从门洞外穿过是否得分；
   - 斜坡：方向/距离/两侧合计 1 m 是否按规则；
   - 砂砾坑：两端短边是否都强制、长边进出是否可能得分；
   - 绕杆：顺序、交替、拐角必达区、起终点圆是否缺一不可；
   - 桥：平台/桥面接触证据、瞬间 ≥2 足触地。
2. **误伤（false failure）**：合法的通过方式会不会被判失败？障碍邻接区的边界擦碰、从任意方向进入的规则（如砂砾坑两端、斜坡任意位置、高墙双向、桥双向）是否处理正确？soft-reset 语义是否会带来新的骗分漏洞？
3. **Part 2 判定与计分**：六类成功判据是否与规则一致（越过高台/楼梯/斜坡/高墙/沟壑/梅花桩分别怎么算过）；计分曲线是否 floor、低于阈值是否 0、高墙/沟壑 10 cm 端点是否 0；参数化 level 场景是否保持了官方障碍种类（允许自定义地图但不得改变种类）；水平/高度阈值是否会误判（例如站在地面 vs 真正上平台）。
4. **尝试协议**：3 次尝试、恢复不消耗、暂停时间是否真的不计入 duration、开始/重开/跳过是否消耗、最终 score 取最好一次 / time 取 3 次最快、返回奖励前置条件（8 障碍全过 + 回到出发区）是否实现正确；是否有"先成功再失败"或"重复计分"漏洞。
5. **证据链**：`comp/eval` 的 manifest/summary/trials 是否自洽、summary 的分数能否由 trials 复算、有没有信任 summary 自报的分数、diagnostic 标记是否诚实；`comp_score.py` 会不会被这些产物骗过（如需要可读 `scripts/agent_scripts/comp_score.py`）。
6. **场景 v2**：可动横杆是否静置稳定、掉落阈值是否合理；接触标签（`GEOM_TAGS`）与 judge 期望的 surface tags 是否一致；runner 是否只把真值用于判分/指令而 actor 观测不带禁止量；Part 2 参数化场景的几何是否与官方档位一致。
7. **测试缺口**：conformance 测试是否覆盖了上轮审计的全部反例、是否存在"测试通过但实现仍有洞"的地方；缺少哪些对 G1 最重要的用例。

## 输出格式

- 先给 **verdict**：`PASS` / `CONCERN` / `WARN` / `FAIL`（这是预审，不是最终 G1 verdict）。
- 再给编号问题清单：每条含 严重度（blocker/major/minor）+ 涉及文件/函数 + 为什么错/可被怎样利用 + 建议修复方向（不要写代码补丁）+ 对应 conformance 用例。
- 最后给 **G1 重审前必须修的最小集合** 与 **Codex 复核应重点看的问题**。
- 全文中文，直接引用文件中的具体行号/函数名；不要复述背景。
