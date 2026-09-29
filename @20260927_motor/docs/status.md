# 任务推进情况（做到哪、还差什么）

> 这是**本任务的推进记录**：阶段状态、下一步、阻滞项、提交与分支情况。
> 入口（任务书要求、怎么跑、文档地图）在 [`../README.md`](../README.md)；每个子任务项的细节在
> [`../cpp/docs/`](../cpp/docs/) 与 [`../cpp_part2/docs/`](../cpp_part2/docs/)。
> 约定来源：[`../../docs/conventions.md`](../../docs/conventions.md) §2（README 只做入口，不记进度）。

## 1 阶段状态

| 阶段 | 状态 |
|---|---|
| 子任务项一：状态机仿真（窗口 / 无窗口回归 / 录像） | ✅ 完成；实测数字见 [`../cpp/docs/sim.md`](../cpp/docs/sim.md) §3 |
| 子任务项一附加：倾斜地面、可调摩擦、与第二次培训控制程序的对照 | ✅ 完成（同上 §2.5 / §2.6 / §6） |
| 子任务项一精简版：`essential` / `essential_core` | ✅ 完成（[`../cpp/docs/essential.md`](../cpp/docs/essential.md)：差别、理由与对拍验证） |
| 子任务项二 S0：端口探针（转接头能不能配 4 Mbaud、SDK 能不能开端口） | ✅ 通过（FT232H + `ftdi_sio`，4 Mbaud 整除） |
| 子任务项二 S1：让电机转起来（带斜坡与限幅） | ✅ 通过（6 次实跑：0 丢帧、温度 30–31 °C、`merror=0`） |
| 子任务项二 S2：零力矩手转找零点 + 定"里程计/锯齿" + kd 扫描 + 量断链行为 + 上电基准 | 🔧 **工具与手册已就绪**（[`../cpp_part2/docs/real.md`](../cpp_part2/docs/real.md) §3.7 的 S2a–S2f），待实机执行（执行卡：[`../cpp_part2/docs/runbook.md`](../cpp_part2/docs/runbook.md) §4 批次 3） |
| 子任务项二 S1b：官方 SDK 例程（任务书第 1 条的字面要求） | 🔧 **命令与安全注意事项已就绪**（[`../cpp_part2/docs/runbook.md`](../cpp_part2/docs/runbook.md) §4 批次 2），待实机执行 |
| 子任务项二 S3–S5：回归 0 + 键盘给角度 / 标零点 + 偏移 30° / 零点跳变 | 🔧 **程序已就绪**（[`../cpp_part2/apps/motor_ctl.cpp`](../cpp_part2/apps/motor_ctl.cpp)；离线自检八种情形都跑通，见 [`../cpp_part2/docs/cli.md`](../cpp_part2/docs/cli.md) §1 与 [`real.md`](../cpp_part2/docs/real.md) §3.8），待实机执行（执行卡：runbook §4 批次 4–6） |
| 子任务项二收尾：实机记录表 → 填回文档 → 提交 → 当面验收演示 | ⏳ 记录表与演示脚本已备好（[`../cpp_part2/docs/runbook.md`](../cpp_part2/docs/runbook.md) §5 / §7），等实机数据 |
| 工程结构对齐：`include/<项目>/**/*.hpp` + `src/*.cpp`（+ `apps/`），C++17 | 🔧 **`cpp_part2/` 已完成**（2026-09-29：5 个头文件 + 4 个实现 + 4 个入口，Allman/C++17；理由见 [`../cpp_part2/docs/setup.md`](../cpp_part2/docs/setup.md) §1）；`cpp/` 与 `@20260923_mujoco/` 待做，规则见 [`../../docs/learn/cpp-cmake.md`](../../docs/learn/cpp-cmake.md) 的「工程目录与文件风格」一节 |
| 文档分工与 README 瘦身：入口只做入口，细节进各自的 `docs/` | ✅ 完成（2026-09-29；`cpp_part2/`、`cpp/`、本任务 README 与 `@20260923_mujoco/` 都已按 [`../../docs/conventions.md`](../../docs/conventions.md) §2/§7 调整） |

## 2 阻滞项

| 阻滞项 | 影响 | 现状 |
|---|---|---|
| **没有实体电机可用** | 子任务项二的 S1b / S2 / S3–S5 与收尾全部要上机才能推进；也是"验收当天演示"的唯一前置 | 唯一的硬阻滞；离线段（协议、控制律、零点账本、仿真电机、文档与执行卡）已全部做完 |

## 3 下一步

实机到手后的顺序：先 **S2**（[`../cpp_part2/docs/real.md`](../cpp_part2/docs/real.md) §3.7：手转找零点 +
定"里程计/锯齿" + 量断链行为 + 查上电基准），再用 `motor_ctl` 做 **S3–S5**（§3.8；标定与跳变的符号约定见 §5）。
现场照着 [`../cpp_part2/docs/runbook.md`](../cpp_part2/docs/runbook.md) 的批次 3–6 走，跑完把数字填回 §5 记录表。

## 4 提交与分支

- 本仓库直接在 `master` 上提交（`origin` = 自己的 GitHub 仓库），**不开长期分支**；唯一的历史分支
  `backup/before-conventions-rewrite` 是改写约定之前的存档，不再合入。
- 提交信息规范见 [`../../docs/conventions.md`](../../docs/conventions.md) §1（一行英文，`type(scope): …`）。
