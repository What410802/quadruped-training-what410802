# 实验：策略在我们的模型上走不走得动、rl_sar 的时钟与线程问题严不严重

做实验的原因：rl_sar **当时**用两条墙钟线程跑控制与推理（[`porting.md`](porting.md) §5），和仿真时间没有关系；线程之间共享数据也不加锁——§3~§6 是那套方案下的实测记录，§9 是 S4 改成反馈驱动之后的结果（结论变了的地方都在 §9 里重新量过）。

所有命令都在仓库根执行，先 `pixi install` 与 `pixi run ros2-build`。数字是 2026-10-08 在本机（Ubuntu 22.04、Intel i5-1035G1 4 核 8 线程、libtorch 2.12.0 CPU 版）上测的。

## 1. 两条链路与指标

| 链路 | 脚本 | 时钟 | 能量什么 |
|---|---|---|---|
| **ROS 链路**（真正要交的东西） | [`check_walk.py`](../scripts/agent_scripts/check_walk.py)：起 sim_node（无窗口、实时）+ rl_sim，按脚本发 `/joy` | rl_sim 的墙钟线程 | 基座高度 / 倾角（仿真节点的状态行）、转向角速度（`/imu`）、策略周期在仿真时间里的分布（`/mit_command` 的关节目标每变一次 = 推理一次） |
| **参考实现** | [`policy_reference.py`](../scripts/agent_scripts/policy_reference.py)：Python 里直接跑 MuJoCo + torch，不经 ROS | 仿真时间锁步（可注入误差） | 以上全部，外加**真值速度**（vx、vy 直接读 mjData） |

两边用同一个场景（`@20261005_ros2/scenes/flat_scene.xml`）、同一份配置（`policy/black/*.yaml`）、同一个 `best.pt`、同一个 MIT 力矩式子。参考实现的观测 / 动作是按大作业说明**独立重写**的，两边结果对得上，也就同时验证了 rl_sar 那边的拼法。

ROS 链路量不到前进速度：仿真节点只发关节、IMU 和状态行（含高度），不发基座位置（那是上次任务的接口，本任务不改）。所以分两步：先在 ROS 链路上量出时序误差（§3），再把它注入参考实现，看它对速度的影响（§4）。

## 2. 策略能在我们的模型上走；±20 N·m 的限幅够用

参考实现，锁步（策略周期正好 20 ms、无延迟），每个指令跑 10 s，统计最后 5 s：

```bash
S=@20261007_assignment/scripts/agent_scripts/policy_reference.py
for c in 0,0,0 0.5,0,0 1.0,0,0 1.5,0,0 0,0.3,0 0,0,1.0; do pixi run python -I $S --cmd $c; done
pixi run python -I $S --cmd 1.5,0,0 --tau-max 20
```

| 指令 (vx, vy, wz) | 实际 vx | 实际 vy | 实际 wz | 高度 z [m] | 最大倾角 | 力矩峰值 [N·m] |
|---|---|---|---|---|---|---|
| (0, 0, 0) | 0.002 | 0.001 | 0.001 | 0.427 | 2.0° | 10.2 |
| (0.5, 0, 0) | 0.361 | −0.004 | −0.005 | 0.414 | 3.1° | 15.8 |
| (1.0, 0, 0) | 0.957 | 0.000 | 0.021 | 0.417 | 3.2° | 19.1 |
| (1.5, 0, 0) | 1.474 | −0.019 | 0.071 | 0.419 | 4.6° | 20.0 |
| (0, 0.3, 0) | 0.010 | 0.268 | −0.003 | 0.417 | 2.9° | 15.1 |
| (0, 0, 1.0) | 0.025 | 0.030 | 0.934 | 0.432 | 1.9° | 16.3 |

* 策略在我们的模型上能走，跟踪误差在几个百分点内（0.5 m/s 那一档偏低到 0.36，原因未查，不影响结论）。
* **力矩上限**：策略按 33.5 N·m 训练，而我们的电机模型限幅 `tau_max` 默认 20、模型 `ctrlrange` 也是 ±20。1.5 m/s 以内峰值不超过 20.0 N·m；把参考实现的上限改成 20 再跑 1.5 m/s，结果逐位相同（vx 1.474）。所以**模型不用改**，仿真节点按默认参数就能用。

## 3. ROS 链路：能走，策略周期在仿真时间里是 20.8 ms

```bash
pixi run python @20261007_assignment/scripts/agent_scripts/check_walk.py              # 从趴卧起（默认）
pixi run python @20261007_assignment/scripts/agent_scripts/check_walk.py --start raw  # 从模型原姿态落下
```

时间线：A（起身）→ RB + 十字键上（进 RL）→ 前进 1.0 m/s 10 s → 停 2 s → 转向 1.0 rad/s 6 s → 停 2 s → B（趴下）。两种起点下 7 项都通过；从趴卧起的一次输出：

| 检查 | 结果 |
|---|---|
| 起身终点 = `default_dof_pos`（经 `joint_mapping` 换到仿真顺序） | 最大偏差 4.96e-08 rad |
| 起身后站住 | z = 0.428 m、倾角 0.7°、四足触地 |
| RL 段（前进 + 转向）没摔 | z 最低 0.410 m、倾角最大 3.1° |
| 策略周期（仿真时间） | 均值 20.76 ms、p5 20.0、p95 22.0、最大 26.0（961 次） |
| 转向 1.0 rad/s，最后 3 s 的陀螺 z 均值 | 0.962 rad/s |
| B 之后关节回到按 A 时的角度，并转阻尼 | 最大差 0.0000 rad |
| 实时率 | 1.0x |

两种起点、连同检查脚本改版前的几次和一次干净 clone 上的运行，共 7 次：策略周期均值 20.74～20.80 ms，转向 0.961～0.970 rad/s。周期只取 20 ms 或 22 ms 这类值：仿真步长是 2 ms，推理结果要等到下一步才被用上。均值比 20 ms 长 0.8 ms 左右，原因是 `LoopFunc` 每圈"先干活再睡（周期 − 已用时间）"，而已用时间按整毫秒截断（`library/core/loop/loop.hpp:76`），所以周期只会变长、不会变短。

## 4. 把实测的时序误差注入参考实现：速度 −4.5%，不摔

用 §3 的分布近似：周期 20.77 ms ± 1.0 ms（均匀分布，落到 2 ms 步长上就是 20 或 22 ms），外加 5 ms 延迟（控制线程每 5 ms 才把新动作取走发出）。三个随机种子：

```bash
S=@20261007_assignment/scripts/agent_scripts/policy_reference.py
for seed in 0 1 2; do for c in 1.0,0,0 0,0,1.0; do
  pixi run python -I $S --tau-max 20 --cmd $c --seed $seed
  pixi run python -I $S --tau-max 20 --cmd $c --seed $seed --period-ms 20.77 --period-jitter-ms 1.0 --delay-ms 5
done; done
```

| 指令 | 锁步 | 注入 ROS 实测时序（3 个种子） | ROS 链路实测 |
|---|---|---|---|
| 前进 1.0 m/s：vx | 0.957 | 0.911～0.915（−4.5%） | 量不到 |
| 转向 1.0 rad/s：wz | 0.934 | 0.957～0.962（+3%） | **0.961～0.970** |

转向这一列可以三方对照：注入实测时序后，参考实现的预测（0.957～0.962）与 ROS 链路的实测（0.961～0.970）只差约 0.01 rad/s（ROS 略高）。锁步与实测之间差了 0.03 左右，其中大部分被这个时序模型解释了。说明这个时序模型抓住了主要因素，前进速度那一列的 −4.5% 也可以采信。

误差再放大也只是慢慢变差（锁步之外都是 1.0 m/s 前进、`--tau-max 20`、种子 0）：

| 周期 / 延迟 | vx | 摔了吗 |
|---|---|---|
| 20.6 ± 0.6 ms / 5 ms | 0.915 | 否 |
| 21 ± 1 ms / 10 ms | 0.891 | 否 |
| 24 ± 4 ms / 20 ms | 0.825 | 否 |

## 5. 墙钟方案的边界：暂停、慢放都没事，快放到 3 倍会摔（**S4 之前的记录**，结论见 §9）

rl_sim 只认墙钟，不管仿真走了多少，所以仿真一旦不按真实时间走，"每 20 ms 推理一次"在仿真时间里就不再是 20 ms。三种情形在参考实现里模拟（前进 1.0 m/s）：

```bash
S=@20261007_assignment/scripts/agent_scripts/policy_reference.py
for p in 0.5 2 5; do pixi run python -I $S --tau-max 20 --cmd 1.0,0,0 --pause-at 3 --pause-seconds $p; done
for per in 2 6.3 10 12.6 16 30 40 60 100; do pixi run python -I $S --tau-max 20 --cmd 1.0,0,0 --period-ms $per; done
```

| 情形 | 对应操作 | 仿真时间里的策略周期 | vx | 摔了吗 |
|---|---|---|---|---|
| 暂停 0.5 / 2 / 5 s（物理冻住，策略照墙钟对着冻住的状态继续推理） | 仿真窗口里按空格 | — | 0.958 / 0.956 / 0.957 | 否 |
| 慢放 80% / 50% / 10% | 窗口里 `-` 键降速 | 16 / 10 / 2 ms | 1.049 / 1.226 / 1.711 | 否（走得比指令快） |
| 快放 1.5x / 2x | — | 30 / 40 ms | 0.800 / 0.706 | 否 |
| 快放 3x / 5x | `realtime:=false`（无窗口全速） | 60 / 100 ms | — | **摔**（10.5 s / 6.5 s 时） |

所以墙钟方案唯一会出事的用法是"仿真跑得比真实时间快很多"，也就是 `realtime:=false`。launch 文件把 `realtime` 默认设成 true，并在说明里写明不要改；代价是 `check_walk.py` 只能按真实时间跑（约 35 s），不能像上次的 `check_headless.py` 那样全速回归。

## 6. 线程间不加锁：5 分钟连续行走无异常

[`porting.md`](porting.md) §7 列了三处不加锁的共享数据，分析的结论是最坏只会混入相邻两帧的数据。实测：把 `check_walk.py` 的前进段拉长到 300 s（从趴卧起，其余时间线不变），一次连续跑完：

| 检查 | 结果 |
|---|---|
| RL 段（300 s 前进 + 6 s 转向）没摔 | z 最低 0.409 m、倾角最大 3.4° |
| 推理次数 / 策略周期 | 14909 次；均值 20.79 ms、p5 20.0、p95 22.0、**最大 114.0 ms** |
| 转向 1.0 rad/s | 0.965 rad/s |
| 进程 | rl_sim 与 sim_node 都正常退出，7 项全部通过 |

没有崩溃，也看不到线程问题的痕迹。有一个意外：最长的一次策略周期是 114 ms（在仿真时间里），而 p95 只有 22 ms，说明有一次推理线程被操作系统晚调度了约 0.1 s（浸泡期间本机同时在做别的事）。狗没受影响，这与 §5 的结论一致：周期偶尔变长不会让它摔。这类长周期出现了几次，这次没有记录，`check_walk.py` 之后补了"超过 30 ms 的次数"这一项。

（这次浸泡用的是一次性脚本，没有入库：它只是导入 `check_walk.py`，把时间线里的前进段改成 `(7.0, 307.0)`、总时长改成 322 s。）

## 7. 键位逐项验证与"非理想电机"回归（2026-10-10）

**背景**：S1 把原来每 5 ms 一行的 `RL Controller …` 状态行改成 `status_period_ms`（默认 0 = 关），于是进 RL 之后**终端上不再有任何新输出**——最后留在屏幕上的还是 GetUp 状态用 `\r` 打的 `Getting up 100.00%`，看起来像"卡在起身、进不了 RL"。不是状态机的问题（日志里 `[FSM] Switch from RLFSMStateGetUp to RLFSMStateRL_Locomotion` 一直在打），是**状态可见性**丢了。修法：`RLFSMStateRL_Locomotion::Enter()` 打一行 `Entered RL_Locomotion; … status_period_ms …`（与 Passive 的进状态提示同一风格），要连续看指令就用 `-p status_period_ms:=500`。

**键位表逐项验证**（`porting.md` §6.2 的手柄 6 项 + 键盘 8 项；手柄用 `/joy` 时间线脚本，键盘用 `script` 给它一个 pty 后逐键送）：

| 操作 | 手柄证据 | 键盘证据 |
|---|---|---|
| 起身 `A` / `0` | `Passive → GetUp` | 同左（pty 送 `0`） |
| 进 RL `RB+十字键上` / `1` | `GetUp → RL_Locomotion`（**在斜坡走完前按下**，走的是手动分支） | 同左（送 `1`） |
| 趴下 `B` / `9` | `RL_Locomotion → GetDown` | 同左（送 `9`） |
| 阻尼 `LB+X` / `P` | `GetUp → Passive`；⚠ `LB+X` 里含原始 `X`，所以同时会**翻转一次**导航模式（不是"一定切回 OFF"，按当时状态而定） | 同左（送 `p`；键盘 `P` 不含 X，不会动导航模式） |
| 复位 `RB+Y` / `R` | 姿态被复位（z 0.414 → 0.196 后重新爬起）；`/sim_reset` **保留仿真时间轴**，别拿 `sim_time` 当判据 | 同左（同一条分支） |
| 导航模式 `X` / `N` | 一次按键一次 `Navigation mode` 翻转（按 3 s 也只翻 1 次） | 同一分支 |

**"RB+十字键上没反应"的诊断**（2026-10-11，现场）：根因是**虚拟手柄窗口跑的是旧修订**，不是 rl_sim 也不是键位表。三段证据：

1. 仓库里的脚本（`89539fc` 之后）设备层是对的：在隔离 ROS 域里造一个同款 uinput 手柄并模拟 GUI 回调（`set_button(5,1)` = 勾选 RB 的"锁定按下"，再 `set_dpad(0,-1)` = 点 ↑），`/joy` 读到的正是 `buttons[5]=1`、`axes[7]=+1.00` —— 组合键确实发出去了。
2. 旧修订（`89539fc` 之前）对 ↑ 写的是 `ABS_HAT0Y = -dy = +1`，而 `joy_node.py:63` 的 `SLOT_SIGN` 对第 7 槽是 **−1**（evdev 十字键"上为负"→ 规范化 /joy"上为正"）→ 旧手柄的 ↑ 在 `/joy` 里是 **`axes[7] = −1`**，rl_sim 按约定读成 **十字键下** → `Gamepad::RB_DPadDown`，而 `RLFSMStateGetUp::CheckChange()` 只认 `RB_DPadUp`/`Num1` → 于是"按了没反应"。（同一修订里摇杆的符号本来就是对 evdev 的，所以旧窗口还能用摇杆走路，只有十字键失灵——与现象完全一致。）
3. 在用户正在跑的会话上直接往 `/joy` 注入 `RB+十字键上`（绕过设备层）→ `/mit_command` 增益从 `fixed_kp=80/fixed_kd=3`（GetUp）变成 `rl_kp=40/rl_kd=1.2`（RL）→ 状态机、键位表、`/joy` 约定都没问题。

**处置**：重启虚拟手柄（`pixi run python @20261005_ros2/sim_joy/xbox_sim_joy.py`）即可；验证办法是点着 ↑ 看 `ros2 topic echo /joy --once` 的 `axes[7]` 应为 **+1.0**（`-1.0` 说明还是旧实例）。补充：手柄 GUI 的按钮带"锁定按下"勾选框（勾上 = `set_button(i,1)` 常按），所以"锁定 RB + 点一次 ↑"这一只鼠标的操作就能拼出组合键，不必同时按住两个控件。

**输入层重构后的验证（S3.5，2026-10-11）**：新增的 [`input_map_selftest`](../ws/src/rl_sar/test/input_map_selftest.cpp)（`pixi run ros2 run rl_sar input_map_selftest`，或走 CTest：`colcon test --packages-select rl_sar`；**不需要 ROS 图 / 仿真 / 手柄**）覆盖 8 组：边沿一次性、锁存十字键不吞按键、组合键补位即触发、按住 RB 时 A 仍生效、复位组合、键盘单值锁存的「变化即按下」、手柄+键盘同时、轴到 bit 的映射。端到端四组回归：**锁存 hat + A 两组都 ✓**（修前 `hat=down` ✗）；**手柄键位扫描 5 段切换 + 导航模式 2 次** ✓；**键盘 pty 路径 `0→1→9→p` 四段** ✓；**混合输入弹回复现用例**（手柄 A + 键盘 `1`）→ 只进 1 次 RL 并停住 ✓（P1-g 的 bug 从结构上消失）；`check_walk.py` 7/7 ✓。重构里踩到一个自己造的坑：第一版把**摇杆电平**也一起删了（新层只管边沿），`check_walk` 的「转向」项立刻失败（陀螺 z 0.000 rad/s）——连续量要留在 `JoyCallback` 里按帧赋值，边沿与电平两条路必须分开看。

**运行侧的两个隐患（与代码无关，但会让"看起来没反应"）**：① `install/` 里的 `joy_node` 是**源码的副本**（不是符号链接）——改完 `joy_node.py` 不重新 `pixi run ros2-build` 就还是旧行为；`rl_sim` 是指向 `build/` 的符号链接、手柄脚本从源码跑，都不会陈旧。② 判状态别只看画面：站着不动的狗在 GetUp 与 RL 里长得一样，用 `ros2 topic echo /mit_command --field kp` 看增益（80/3 = GetUp，40/1.2 = RL）最稳；组合键是否到位则看 `ros2 topic echo /joy`（`buttons[5]=1` + `axes[7]=1.0`）。

**"锁存的十字键吞掉按键"**（2026-10-11 复现 + 修复）：虚拟手柄的十字键**点一下就锁存**（`axes[7]` 一直发 ±1，点 `●` 或「全部归中 / 松开」才回中），而 `JoyCallback()` 的映射是最后写入者赢、十字键规则又写在按键规则之后——于是锁存着"下"时按 A，`control.current_gamepad` 每帧都被写成 `DPadDown`，状态机读不到 `Gamepad::A`。两组独立对照（同一脚本，只差十字键是否锁存）：

```
hat=down   → A 被吞掉：没有任何切换 ✗      # 复现
hat=clear  → A 生效：Passive → GetUp ✓
```

修法：先按 P1-h 把四条十字键规则收进 `if (!any_gamepad_button)`；**S3.5 之后由输入层彻底解决**——十字键只是普通 bit，组合就是多个 bit，不再有「最后写入者赢」。修后同一对照 **两组都 ✓**；并且"十字键锁存着**上** + 按 RB"（原来的进 RL 手势）仍然给出 `Passive → GetUp → RL_Locomotion` ✓。

**非理想电机回归**（`check_walk.py` 新加的 `--sim-param` 透传）：

```bash
# ① 文档里"完整版实测用的那组"（motor-model.md §2）：7/7 全过
pixi run python @20261007_assignment/scripts/agent_scripts/check_walk.py \
    --sim-param motor_deadzone:=0.5 --sim-param motor_delay_cycles:=2 \
    --sim-param motor_noise:=0.2 --sim-param motor_seed:=12345
# ② 2 倍严苛（死区 1.0 N·m / 延迟 4 周期 / 噪声 0.4 N·m）：仍然 7/7
pixi run python @20261007_assignment/scripts/agent_scripts/check_walk.py \
    --sim-param motor_deadzone:=1.0 --sim-param motor_delay_cycles:=4 \
    --sim-param motor_noise:=0.4 --sim-param motor_seed:=12345
```

| 判据 | 理想（默认全关） | ① 0.5 / 2 / 0.2 | ② 1.0 / 4 / 0.4 |
|---|---|---|---|
| 起身终点偏差 | 4.96e-08 rad | 4.96e-08 rad | 4.96e-08 rad |
| 起身后 z / 倾角 | 0.429 m / 0.8° | 0.429 m / 0.8° | 0.429 m / 0.9° |
| RL 段最低 z / 最大倾角 | 0.411 m / 2.9° | 0.410 m / 3.3° | 0.409 m / 3.5° |
| 策略周期均值（p95） | 20.65 ms（22.0） | 20.67 ms（22.0） | 20.65 ms（22.0） |
| 转向陀螺 z 均值 | 0.968 rad/s | 0.982 rad/s | 0.975 rad/s |
| 实时率 | 0.995x | 1.000x | 0.999x |

② 那次的仿真节点退出统计证明这些非理想项**确实在咬**：`累计 193572 电机·步，撞限幅 3 次（0.002%），落死区 67589 电机·步（34.917%，进出死区 10228 次）`。也就是说：这套策略对本模型里的静摩擦、8 ms 指令延迟与 0.4 N·m 力矩噪声**不敏感**（差异都在抖动范围内），验收结论不受非理想项影响。

## 8. 结论

| 问题 | 严重程度（依据） | 处理 |
|---|---|---|
| 墙钟线程：实时运行时策略周期 20.8 ms（训练 20 ms） | 轻：速度 −4.5%、转向 +3%，不摔（§3、§4） | 保留原样 |
| 墙钟线程：仿真暂停 / 慢放 | 无影响（§5） | 保留原样 |
| 墙钟线程：仿真快放 ≥ 3 倍（`realtime:=false`） | 严重：摔（§5） | 不改代码，launch 固定 `realtime:=true` 并写明 |
| 线程间不加锁 | 未观察到影响（§6，约 15000 次推理），理论上最坏只混入相邻两帧（porting §7） | 前两处保留原样；第 3 处按 [`status.md`](status.md) P2-c 改成读局部副本（一行） |
| 推理线程偶尔被晚调度（浸泡中最长 114 ms） | 轻：不摔（§6；与 §5 的"周期变长只慢慢变差"一致） | 保留原样 |
| 力矩上限 20 N·m（训练 33.5） | 无影响：1.5 m/s 以内峰值 ≤ 20.0（§2） | 不改模型 |

所以原计划的第二阶段（把 rl_sim 改成跟着 `/motor_state` 的仿真时间走）**不是必须的**。只有将来需要全速回归（`realtime:=false`）时才值得做——届时的改法、代价与验收见 [`status.md`](status.md) 的 P1-c 与实施顺序 S4，时基机制本身见 [`../../docs/learn/rl-sar.md`](../../docs/learn/rl-sar.md) §6。

## 9. S4：改成反馈驱动之后（2026-10-11）

做法见 [`porting.md`](porting.md) §2 第 18 条与 §5，频率总表在 [`control-stack-rates.md`](control-stack-rates.md)。三个场景都是同一条命令跑出来的：

| 场景 | S4 之前（§3/§5 的数字） | S4 之后 |
|---|---|---|
| 1x 实时 | 策略周期均值 20.65~20.80 ms | **20.00 ms**（p5/p95 都是 20.0；998 次里 0~1 次超 30 ms，偶发一次 32 ms） |
| 全速 `realtime:=false` | 3x 就摔 | **22~25x**（带检查脚本，多次实测）7/7 全过；栈自身 **39.3~41.6x**（无 Python 负载，见频率总表 §6） |
| 暂停 | 墙钟循环照跑，斜坡继续推进 | SIGSTOP 仿真 1.5 s：斜坡只前进 3.5%（在途反馈），`SIGCONT` 后继续 |

```bash
pixi run python @20261007_assignment/scripts/agent_scripts/check_walk.py                    # 1x：20.00 ms、7/7
pixi run python @20261007_assignment/scripts/agent_scripts/check_walk.py --realtime false    # 全速：~25x、7/7
pixi run python @20261007_assignment/scripts/agent_scripts/check_feedback_clock.py           # 暂停：斜坡不动/恢复即走
```

**中途踩的坑（值得记）**：第一版写成"每收到一条 `/motor_state` 就跑一次控制"。1x 下没问题（策略周期 20.00 ms），但全速时反馈到 4~5 kHz、`/mit_command` 也跟着 4~5 kHz，两端直接被打爆：

```
[FAIL] 策略周期 均值 28.54 ms、p95 50.0、最大 154.0、超过 30 ms 的 171 次（共 571 次）
[FAIL] 起身终点 最大偏差 3.45e-01 rad（斜坡没走完）
```

改成"控制锚在仿真时间每 5 ms 一步"（并把 `/mit_command` 改成目标变了才发 + 心跳）之后全速 7/7。教训：**反馈是时钟，不是工作量**——节拍要按仿真时间定，别按消息条数定。
