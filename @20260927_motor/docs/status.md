# 任务推进情况（做到哪、还差什么）

> 这是**本任务的推进记录**：阶段状态、下一步、阻滞项、提交与分支情况。 入口（任务书要求、怎么跑、文档地图）在 [`../README.md`](../README.md)；每个子任务项的细节在 [`../cpp/docs/`](../cpp/docs/) 与 [`../cpp_part2_remake/docs/`](../cpp_part2_remake/docs/)（子任务项二的**正式代码**是 [`../cpp_part2_remake/`](../cpp_part2_remake/)；[`../cpp_part2/`](../cpp_part2/) 是历史版本，只作对照）。 约定来源：[`../../docs/conventions.md`](../../docs/conventions.md) §2（README 只做入口，不记进度）。

## 1 阶段状态

| 阶段 | 状态 |
|---|---|
| 子任务项一：状态机仿真（窗口 / 无窗口回归 / 录像） | ✅ 完成；实测数字见 [`../cpp/docs/sim.md`](../cpp/docs/sim.md) §3 |
| 子任务项一附加：倾斜地面、可调摩擦、与第二次培训控制程序的对照 | ✅ 完成（同上 §2.5 / §2.6 / §6） |
| 子任务项一精简版：`essential` / `essential_core` | ✅ 完成（[`../cpp/docs/essential.md`](../cpp/docs/essential.md)：差别、理由与对拍验证） |
| 子任务项二 S0：端口探针（转接头能不能配 4 Mbaud、SDK 能不能开端口） | ✅ 通过（FT232H + `ftdi_sio`，4 Mbaud 整除） |
| 子任务项二 S1：让电机转起来（带斜坡与限幅） | ✅ 通过（6 次实跑：0 丢帧、温度 30–31 °C、`merror=0`） |
| **子任务项二（实体电机控制）：正式代码 [`../cpp_part2_remake/`](../cpp_part2_remake/)** | ✅ **验收通过**（2026-10-03）：任务书四条（① 官方 SDK 例程 → ② 回 0 + 键盘给角度 → ③ 标零点 + 正向偏移 30° → ④ 零点跳变）全部完成。设计与决策（D1–D20、符号表）见 [design.md](../cpp_part2_remake/docs/design.md)，实机执行卡与记录表见 [runbook.md](../cpp_part2_remake/docs/runbook.md)；自检 `ctest` 3/3（`motor_core_tests` / `motor_sim_tests` / `motor_wire_tests`），实机日志在 [`../output/terminal/`](../output/terminal/) |
| 子任务项二历史版本 [`../cpp_part2/`](../cpp_part2/) | 🗄 已被 `cpp_part2_remake/` 取代（正式化 2026-10-02，验收 2026-10-03）；保留初版实现、当时的实测记录与缩写表作对照，不再维护 |
| 工程结构对齐：`include/<项目>/**/*.hpp` + `src/*.cpp`（+ `apps/`），C++17 | 🔧 **`cpp_part2_remake/` 已按该结构组织（现行）；`cpp_part2/`（历史）2026-09-29 完成**（当时的拆分理由见 [`../cpp_part2/docs/setup.md`](../cpp_part2/docs/setup.md) §1）；`cpp/` 与 `@20260923_mujoco/` 待做，规则见 [`../../docs/learn/cpp-cmake.md`](../../docs/learn/cpp-cmake.md) 的「工程目录与文件风格」一节 |
| 文档分工与 README 瘦身：入口只做入口，细节进各自的 `docs/` | ✅ 完成（2026-09-29；`cpp_part2/`、`cpp/`、本任务 README 与 `@20260923_mujoco/` 都已按 [`../../docs/conventions.md`](../../docs/conventions.md) §2/§7 调整；`cpp_part2_remake/` 同样只做入口） |

## 2 阻滞项

| 阻滞项 | 影响 | 现状 |
|---|---|---|
| ~~没有实体电机可用~~ | ~~子任务项二的实机阶段全要上机才能推进；也是"验收当天演示"的唯一前置~~ | ✅ **已解除**（2026-10-01 起实机可用；2026-10-03 验收通过） |

## 3 下一步

子任务项二（实体电机控制）已完结并验收：[`../cpp_part2_remake/`](../cpp_part2_remake/) 覆盖任务书四条与 ④ 的断电重上电（启动检查 + 自动对齐），现场步骤与记录表见 [runbook.md](../cpp_part2_remake/docs/runbook.md) §5–§6。初版执行卡（S2 / S3–S5 那套）在 [`../cpp_part2/docs/`](../cpp_part2/docs/)，之后只作对照。

若继续推进（都不影响本次验收，按 [design.md](../cpp_part2_remake/docs/design.md) §6 的可选项）：

- **M3**：会话内的断线恢复（`reanchor` / `--recover-hold`）——做了才需要 `turn_base` 非 0；
- **M2a**：进程内确定性测试通道（虚拟时钟的 CTest）；
- **M2c**：现场探针 / 旋转工具（当前用 `motor_ctl` 的 `--no-send` 与 `move` 替代，见 runbook §9）；
- **`cpp/`（子任务项一）与 `@20260923_mujoco/` 的工程结构对齐**（规则见 [`../../docs/learn/cpp-cmake.md`](../../docs/learn/cpp-cmake.md) 的「工程目录与文件风格」一节）。

## 4 提交与分支

- 本仓库直接在 `master` 上提交（`origin` = 自己的 GitHub 仓库），**不开长期分支**；唯一的历史分支 `backup/before-conventions-rewrite` 是改写约定之前的存档，不再合入。
- 提交信息规范见 [`../../docs/conventions.md`](../../docs/conventions.md) §1（一行英文，`type(scope): …`）。
