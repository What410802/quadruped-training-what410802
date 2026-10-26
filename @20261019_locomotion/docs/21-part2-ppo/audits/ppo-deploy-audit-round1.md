# PPO/BC 部署链路与 GPU 作业契约审计（round 1）

> 审计员：只读独立审计（未修改仓库任何文件、未在远程机写文件、未提交任何 GPU 任务）。范围：PPO/BC 线的**部署侧**（`@20261024_blackw/ws`、`scripts/`、`models/`、README）+ 远程 `~/rc_work/gpu_jobs/` 与 `~/rc_work/logs/`。HIM 线不在范围内，只在引用其 summary 格式处标注。
> 审计时间：2026-10-26。远程机 `bis-ms7e56.tail4413b4.ts.net` 以 `ssh -o BatchMode=yes` 只读访问；本机命令均在仓库根目录执行。

## 0. 结论速览

| 核心问题 | 结论 | 阻塞 |
|---|---|---|
| 1. 能不能「拿到 .pt 放进去就启动演示」 | **sim 能启动（约 5 步），但不能「保证质量」**；实机演示**缺整条硬件路径**；≤3 策略切换可行但**没有 runbook**（README 手柄键位写错） | 是 |
| 2. 0.002s/decimation10 与部署 0.005/4 是否改变策略行为 | **策略周期两端都是 50 Hz，PD/物理两端都是 500 Hz**（PD 在 `sim_node` 里按 MuJoCo 0.002s 步长算），所以策略输入输出节拍**没有变**；但 `dt` 仍是 `command_limit` 的 slew 时基，且**部署侧不可按策略覆盖**、**从无端到端频率验证** | 否（P1：F6/F7） |
| 3. 导出 drop-in 是否自足 | `policy.pt` **自足**（TorchScript 342→16，离线可跑）；**`config.yaml` 不由导出器产出**（远程 PPO 导出器 102 份模型 0 份 config），且 `contract.json` 的 `action_scale` **右腿轮符号写反**；129 个策略目录里 **83 个** `config.yaml` 顶层 key 与目录名不符 → C++ 侧进 RL 直接失败（Python judge 却能读） | 是 |
| 4. 验证覆盖 | `check_walk_blackw.py` 只覆盖「平地起身→走→转→趴下」7 项，**命令固定 1.0/1.0 m/s**，**Part2 20 关覆盖 0/20**；没有逐档部署 smoke，也没有「部署 vs judge」对拍 | 是 |
| 5. 作业脚本/队列 | resume 语义正确（650→949 有日志证据）；**出口契约有洞**：`done` 行无条件写、`ppo_*.sh` 的导出 rc 不进最终 rc、SIGTERM 退出码变成 2、`head` 级硬编码续训点与日志错标 | 否（P1） |

**VERDICT：`BLOCKED`**，阻塞项 **B1=F1、B2=F2、B3=F3**（见 §7）。

---

## 1. 核心问题 1：能否「最终 .pt 按契约放进去就启动演示」

### 1.1 sim 演示：5 步，可用；但「质量」没有被任何一步校验

工作区**已编译过**（`@20261024_blackw/ws/install/`、`ws/build/` 都在），所以从 0 到画面是 5 步：

```bash
cd /home/bis/BiS.d/Code.d/RoboCon/MyMonoRepo.d
# 0)（改过源码才需要）pixi run ros2-build
# 1) 起三节点：sim_node + joy_node + rl_sim（窗口 + 手柄）
pixi run ros2 launch rl_sar_blackw rl_sim_blackw.launch.py policy_name:=comp_bc_v5
# 2) 起身：键盘 0 / 手柄 A       （GetUp 斜坡 200 控制周期 ≈ 1.0 s 仿真时间）
# 3) 进 RL：键盘 1 / 手柄 RB + D-pad 上   → 此时才读 policy/blackW/<name>/{config.yaml,policy.pt}
# 4) 驱动：左摇杆 vx、右摇杆 yaw（joy_command_scale 默认 1.5）
# 5) 收尾：9 / B 趴下，P / LB+X 阻尼
# Part2 某一档：
pixi run ros2 launch rl_sar_blackw rl_sim_blackw.launch.py policy_name:=comp_bc_v5 part:=2 part2_level:=stairs_20cm
```

缺的东西（按严重度）：

1. **没有「这一档能不能过」的判据**：launch 只放场景和出生点（`launch/rl_sim_blackw.launch.py:37-52`），命令要人推摇杆，跑完没有任何 pass/fail。20 关里到底哪关在部署栈上能过，**目前零证据**（F2）。
2. **部署物理与 judge 不等价**：`sim_node` 把每个关节力矩统一夹到 `tau_max=20 N·m`，小腿在训练/judge 里是 59.25 N·m（F1，P0）。也就是说「judge 750 分」这套数字**不能**说明 sim 里能看到同样的行为。
3. **键位文档错误**：README 手柄行把「进 RL」写成 `LB+上`、「复位」写成 `X`，而代码是 `RB+D-pad 上` 与 `RB+Y`（`include/input_map.hpp:148-159` vs `README.md:162`）。照 README 按会进不去 RL（F5）。
4. **多策略目录 83/129 不可加载**（F4）：进场只有 `flat/stair/obstacle/comp_bc_v5/comp_high600/comp_lane300` 这批 key 与目录名一致的能进 RL。

### 1.2 实机演示：缺整条硬件路径（不是「差一点」，是从未实现）

- 工作区只有 `sim_node`（MuJoCo 本体+电机模型）、`joy_node`、`rl_sim`；`quadruped_ros2_blackw/src/` 下只有 `sim_node.cpp` 与 `controller_node.cpp`（后者是脚本姿态控制器，非 RL、也非硬件驱动），**没有任何硬件驱动节点**（无串口/CAN/EtherCAT、无电机使能/标定/错误码）。
- `rl_sim` 的时钟**由 `/motor_state.sim_time` 驱动**（`src/rl_sim.cpp:399-440`），`MotorState.msg` 明确写着 `sim_time = MuJoCo data.time`。换到实机必须先有人提供「单调递增的 sim_time」——要么扩展消息语义（把主控时间戳当 sim_time），要么改 `rl_sim` 的节拍来源；这是**代码改动**，不是配置。
- `motor.hpp` 的 `Bank` 语义（每 2 ms 算一次 MIT 力矩、`tau_max` 夹限）在实机上属于驱动板；实机侧必须**逐关节**复刻 `[23.7, 23.7, 59.25, 20]`，否则同样的策略实机行为必然不同（F1 的同一条根因）。
- 实机还需要：关节零位/方向标定（MJCF 顺序是 FL/FR/**RR/RL**，见 `scenes/blackW/blackW_description.xml:197-214`）、轮半径与轮速换向（`action_scale` 右腿 -10 的硬件依据）、看门狗（`sim_node` 200 ms → 驱动板必须有自己的掉线阻尼）、急停。
- README **完全没有「实机」章节**（`grep -n 实机 README.md` 无输出）。

结论：**实机演示当前不可 demo，缺的是驱动节点+时钟语义+逐关节限幅+标定，属于「待开发」，不是「待配置」**。

### 1.3 多策略（≤3 份）怎么切换、有没有 runbook

- **机制**：启动参数 `policy_name:=<dir>`（`launch/rl_sim_blackw.launch.py:113,137` → `rl_sim.cpp:35` → `fsm.hpp:233-237` `InitRL(robot_name + "/" + config_name)`）。**运行中**只能切到三份官方策略：键盘 `2/3/4`、手柄 `Start+D-pad 左/上/右`（`input_map.hpp:148-153`），因为 `rl_sim.cpp:340-342` 把名字**硬编码**成 `"flat"/"stair"/"obstacle"`；自训候选（`comp_bc_*`）**无法在运行中切**，只能重开 launch。
- **判据**：切换成功会打 `[policy] switched to ...`（`rl_sim.cpp:256`）；切到不存在的目录则在进 RL 时打 `InitRL() failed:`（`fsm.hpp:242-246`），**不会崩，但也不动**（届时狗保持起身姿势，没有扰动提示）。
- **runbook**：**没有**。README §「策略运行时切换」（`README.md:93-122`）只列了键位表，没有「换一份新权重需要做哪几步校验」「三份候选怎么选」「失败怎么回退」；`prep.d/` 下也没有部署 runbook（`ls prep.d/` 只有 `bc_data/results/videos`）。
- **推荐的三份候选**（目录 key 与目录名一致、`policy.pt` 齐全、config 与官方契约逐字节相同）：`comp_bc_v5`（judge v5 750/1300）、`comp_high600`、`comp_lane300`。切换流程建议「三个终端各起一份 launch，用不同 `policy_name`，ROS_DOMAIN_ID 隔离」——因为运行中切不到自训权重。

---

## 2. 核心问题 2：0.002s+decimation 10 vs 部署 0.005+decimation 4

### 2.1 先把三个周期分开看（这是本节的关键）

| 周期 | 训练/judge | 部署（rl_sar sim） | 是否一致 |
|---|---|---|---|
| 物理步长 | 0.002 s（`eval_blackw_part2.py:267,270`；`BLACKW_PHYSICS_DT=0.002`） | **0.002 s**（`scenes/blackW/blackW_description.xml:3` `<option timestep="0.002">`；`sim_node.cpp:26` 注释「控制周期 = 物理步长 = 0.002 s」） | **一致** |
| PD/力矩计算 | 每个物理子步（500 Hz，`eval_blackw_part2.py:371-390` `_apply_torque()` 每 0.002 s 一次） | **每个物理步（500 Hz）**，因为 MIT→力矩在 `sim_node` 里算（`sim_node.cpp:838-890`，`motors.Apply(...)` 后 `mj_step`） | **一致**（这是多数人以为不一致、其实一致的地方） |
| 策略推理 | 50 Hz（`policy_dt=0.02`，`substeps=10`） | **50 Hz**（`dt 0.005 × decimation 4 = 0.02`，`base.yaml:3-4`；`rl_sim.cpp:430-439`） | **一致** |
| 命令（q_des/dq_des/kp/kd）**刷新**率 | 50 Hz（每个策略步换一次，10 个子步内保持不变） | **200 Hz**（每 5 ms 重发一次同样的目标，`SetCommand` 只在变化时发+100 ms 心跳 `rl_sim.cpp:210-228`） | 名义不一致，**对动力学无影响**（目标在 20 ms 内本来就不变） |

所以「部署 base.yaml 是 dt 0.005 + decimation 4（PD 200 Hz vs 500 Hz）」这个前提**只对了一半**：`rl_sim` 自己不跑 PD，PD 在 `sim_node` 里按 0.002 s 跑。**策略看到的输入/输出节拍与训练完全一致**，这也是 `comp_bc_v5` 在 sim 里能起身走路的原因。

### 2.2 但 dt 仍然渗进了两处，且都没被验证

1. **slew 限幅被 `dt` 缩放，且作用在 200 Hz 的控制节拍上**（F6）：`command_limit.hpp:109-118` 用 `|q_des - q_des_prev| <= slew * dt`。目标每 20 ms 才变一次，而限幅器每 5 ms 判一次 → 有效上限是 `60 × 0.005 = 0.30 rad / 次推理 = 15 rad/s`，**不是文档写的 60 rad/s**（`base.yaml:17` 注释、`command_limit.hpp:50`）。改成 0.002/10 会变成 `0.12 rad/次推理 = 6 rad/s`——**越「对齐」越紧**，这条耦合没有任何测试覆盖。
2. **命令侧力矩预算用 `command_tau_limit: 33.5`（`base.yaml:13`），但真正交付的力矩被夹在 20 N·m**（F1）。这条是本次审计最严重的发现，与频率无关但同属「训练↔部署物理不等价」。

### 2.3 部署侧是否支持改成 0.002/10 —— 支持，但没有按策略覆盖的能力

- 机械上支持：`ControlStep()` 完全按 `params.dt` 与 `params.decimation` 走（`rl_sim.cpp:407-440`，含「最多补 10 步」的追赶逻辑），把 `base.yaml` 改成 `dt: 0.002 / decimation: 10` 后策略周期仍是 20 ms。
- 代价：控制回调从 200 Hz 变 500 Hz（同一执行器线程，`RunModel` 内部一次 torch 前向），全速跑的追赶上限 `10 × dt` 仍是 20 ms，但 CPU 占用与 `/motor_state` 处理频率翻 2.5 倍。
- **缺口**：`dt/decimation` 只存在于 `base.yaml`（`rl_sdk.cpp:376-377`，构造时读一次），**没有 per-policy 覆盖**，也没有「本策略按什么频率训练」的字段；`WarnIfBaseConfigMismatch()` 只比 7 个键（`knobs.hpp:143-144`），**不比频率**（因为 `config.yaml` 里根本没有频率字段）。所以一份按 100 Hz 或 500 Hz 训练的新权重，放进去不会有任何提示。

### 2.4 「有没有验证过两种控制频率」

**没有。** 证据：

- 仓库里唯一为「部署 obs vs judge obs」准备的钩子是 `RL_DEBUG_OBS=1` 时把前 60 帧 obs/action 写到 `/tmp/rl_obs_debug.csv`（`rl_sim.cpp:515-527`），但**全仓没有任何脚本读这个文件**（`grep -rn rl_obs_debug --include=*.py --include=*.md --include=*.sh` 无命中）。它是「埋了但没接」的仪器（F14）。
- judge 是**独立 Python 实现**（`eval_blackw_part2.py:338-390`），完全不经过 `rl_sar`；它自己的 `--physics-dt/--policy-dt`（`eval_blackw_part2.py:573-574`）默认就是 0.002/0.02，所以「judge 分数」从来没有检验过 rl_sar 的时钟实现。
- 本地也没有 0.005/4 与 0.002/10 的 A/B 记录（`grep -rn "0.002\|decimation" @20261024_blackw/README.md` 只有一句「0.002s 物理」讲 judge）。
- 相关文档口径已经互相矛盾：`models/comp_bc_v5/manifest.json:9-11` 写 `physics_dt_s: 0.002 / policy_rate_hz: 50`，`policy/blackW/base.yaml:3-4` 写 `0.005/4`（F7）。

---

## 3. 核心问题 3：导出 drop-in 是否自足

### 3.1 `policy.pt`：自足（可离线加载）

```bash
pixi run python -c "
import torch
m=torch.jit.load('@20261024_blackw/ws/src/rl_sar_blackw/policy/blackW/comp_bc_v5/policy.pt').eval()
print(m(torch.zeros(1,342)).shape)"      # -> torch.Size([1, 16])
```

- `comp_bc_v5` / `flat` / `dt2ms_700` 实测均 `342 → 16`，无需训练仓、无需 `alldog_mjlab`。sha256：`comp_bc_v5/policy.pt = fa68c0df…a0bf`，与 `models/comp_bc_v5/manifest.json:76` 一致；`models/comp_bc_v5/policy.pt` 与部署副本**逐字节相同**。
- 输入维度的自洽性靠 `num_observations(57) × observations_history(6) = 342`（`config.yaml:132,141-147`），与 TorchScript 输入一致；若写错，`torch::jit` 会在前向时抛异常（但见 F15：`main()` 没有 try/catch，异常会打死 `rl_sim` 进程）。

### 3.2 `config.yaml` 从哪来：**没有一份导出器产出它**（F3）

| 线 | 导出脚本 | 产物 | config.yaml |
|---|---|---|---|
| BC（本地） | `@20261024_blackw/scripts/export_bc_policy_local.py:74-101` | `policy.pt` | **从 `policy/blackW/obstacle/config.yaml` 拷贝**（`:78-79`），只改 `model_name/model_path`（`:93-94`），然后 `safe_dump` 成 `blackW/<name>:` |
| PPO（远程） | `~/rc_work/part2_team_race/scripts/agent_scripts/export_blackw_policy.py` | `policy.pt` + `contract.json` | **不产出**。`~/rc_work/models/` 实测 102 个模型目录、101 份 `contract.json`、**0 份 `config.yaml`** |

> 注：任务书里写的 `@20261024_blackw/scripts/export_blackw_policy.py` **在本仓库不存在**；同名的只有远程训练仓里的那份。本地 `training/` 快照里也没有 `blackw/actions.py`（`ls @20261024_blackw/training/blackw` → 只有 `env_cfgs/exact_terrain/guarded_ppo/__init__`），而 `env_cfgs.py:36` 依赖它（F13）。

**复制 `obstacle/config.yaml` 恰好是对的**：`obstacle`、`flat`、`comp_bc_v5`、`dt2ms_700` 四份 config 逐字段相同（仅 `model_path` 不同）：

```bash
diff <(python3 -c "import yaml;print(yaml.safe_dump(yaml.safe_load(open('@20261024_blackw/ws/src/rl_sar_blackw/policy/blackW/flat/config.yaml')),sort_keys=True))") \
     <(python3 -c "import yaml;print(yaml.safe_dump(yaml.safe_load(open('@20261024_blackw/ws/src/rl_sar_blackw/policy/blackW/comp_bc_v5/config.yaml')),sort_keys=True))")
# 只有 1/131 行不同：model_path
```

### 3.3 数值逐项核对（部署 config vs 训练契约）

| 项 | 部署 `comp_bc_v5/config.yaml` | 训练契约 | 结论 |
|---|---|---|---|
| `action_scale` | `[0.25,0.25,0.25,10]` 重复 4 组，但**第 2/4 组轮为 `-10`**（`:2-18`） | `env_cfgs.py:68-77 _wheel_leg_scale()`：`FR/RR = -10`，其余 `+10` | **一致** |
| `rl_kp / rl_kd` | `50 / 1.2`（腿）、`0 / 1.0`（轮）（`:148-181`） | 官方 blackW `SOUL`/仓库契约同值（`flat/config.yaml` 同值） | **一致** |
| `torque_limits` | `[23.7,23.7,59.25,20]`（`:182-198`） | judge `eval_blackw_part2.py:282,381` 逐关节夹 | **一致（但部署栈里是死参数，见 F1）** |
| `num_observations` / history | `57` / `[0..5]`（`:132,141-147`） | `BLACKW_ACTOR_HISTORY_LENGTH=6`，`FRAME_DIM=57`（`env_cfgs.py:57`；导出器 `FRAME_DIM=57`） | **一致** |
| 观测量比例 | `commands [2,2,0.25]`、`ang_vel 0.25`、`dof_pos 1.0`、`dof_vel 0.05`、`actions 1.0` | `BLACKW_ACTOR_OBS_SCALE`（`env_cfgs.py:58-65`） | **一致** |
| 关节顺序/映射 | `joint_mapping [0,1,2,3,4,5,6,7,12,13,14,15,8,9,10,11]`（`:112-128`） | 策略序 FL/FR/RL/RR；sim 执行器序 FL/FR/**RR/RL**（`blackW_description.xml:197-214`） | **一致**（`rl_sim.cpp:151-157` 用它做 q/dq，`:201-207` 做输出） |
| 观测历史语义 | newest first，`insert` 后 `get_obs_vec([0..5])`（`observation_buffer.cpp:31-58`），首帧回填 6+1 次（`rl_sim.cpp:493-509`） | 导出器把 native「term-major 旧→新」**置换**成「frame-major 新→旧」（`export_blackw_policy.py:40-67`） | **一致** |
| `model_path` | 写着 `policy/blackW/<name>/policy.pt` | —— | **死字段**：C++ 只拼 `CMAKE_CURRENT_SOURCE_DIR + "/policy/" + robot_path + "/" + model_name`（`rl_sdk.cpp:154`），`model_path` 从未被读 |

### 3.4 三个「静默用错 config」的坑（F3/F4）

1. **`contract.json` 的 `action_scale` 是错的**：导出器把 `[0.25,0.25,0.25,10.0]*4` 写进 `contract.json`（`export_blackw_policy.py:164-166`，实测 `~/rc_work/models/dt2ms_700/contract.json`），**右腿轮丢了负号**。谁按 `contract.json` 手搓 `config.yaml`，右前/右后轮会反向。这是唯一一份「看起来像契约」的导出产物，却是错的。
2. **`config.yaml` 顶层 key 必须等于目录名**：C++ 走 `YAML::LoadFile(cfg)[robot_path]`，`robot_path = "blackW/<dir>"`（`rl_sdk.cpp:392-402`）。实测 **129 个策略目录里 83 个 key 不符**（`eval_*`、`reg_*`、`st30_*`、`slopeB_*`、`ts_trial_*` 全写成 `blackW/comp_bc_v5`）：

```bash
cd @20261024_blackw/ws/src/rl_sar_blackw/policy/blackW
python3 -c "
import yaml,glob,os
bad=[(d,yaml.safe_load(open(d+'/config.yaml')).keys()) for d in sorted(glob.glob('*/')) if os.path.exists(d+'config.yaml')]
print(len(bad),'dirs;', sum(1 for d,k in bad if list(k)[0]!='blackW/'+d.rstrip('/')),'mismatched')"
# 129 dirs; 83 mismatched
```

   - Python judge **容忍**（`eval_blackw_part2.py:92-97`：单 key 就整份拿来用），C++ **不容忍**（`config["model_name"]` 抛 `YAML::Exception` → `fsm.hpp:242-246` 打印 `InitRL() failed` 并停在原地）。→ **judge 能评、部署打不开**，这是最典型的「评测结论与演示能力脱节」。
3. **改 key 忘改 `model_name`**：`model_name` 决定加载哪个文件（`:404,154`），`model_path` 只做展示。两者不一致时无任何告警。

### 3.5 放进一份新 .pt 之后需要的步骤（当前必须手工，没有工具保证）

```bash
# 1. 建目录 + 放权重
install -D new_policy.pt @20261024_blackw/ws/src/rl_sar_blackw/policy/blackW/<name>/policy.pt
# 2. 生成 config.yaml（照抄官方契约，只改两处）
cp @20261024_blackw/ws/src/rl_sar_blackw/policy/blackW/comp_bc_v5/config.yaml \
   @20261024_blackw/ws/src/rl_sar_blackw/policy/blackW/<name>/config.yaml
sed -i "s|^blackW/comp_bc_v5:|blackW/<name>:|; s|policy/blackW/comp_bc_v5/policy.pt|policy/blackW/<name>/policy.pt|" \
   @20261024_blackw/ws/src/rl_sar_blackw/policy/blackW/<name>/config.yaml
# 3. 静态校验（缺一不可）
python3 - <<'PY'
import yaml,torch
d='@20261024_blackw/ws/src/rl_sar_blackw/policy/blackW/<name>'
c=yaml.safe_load(open(d+'/config.yaml'))
assert list(c)==[ 'blackW/<name>' ], list(c)                       # key 必须等于目录名
e=c['blackW/<name>']
assert e['num_observations']*len(e['observations_history'])==342
assert e['action_scale'][7]==-10 and e['action_scale'][15]==-10   # 右腿轮负号
m=torch.jit.load(d+'/policy.pt').eval(); assert m(torch.zeros(1,342)).shape==(1,16)
print("ok", e['model_name'])
PY
# 4. 头号 smoke（≈30 s，全速）
pixi run python @20261024_blackw/scripts/check_walk_blackw.py --realtime false --policy <name>
# 5. judge（本地 20 关，0.002s 物理 / 50 Hz 策略）
pixi run python @20261024_blackw/scripts/eval_blackw_part2.py \
  --policy @20261024_blackw/ws/src/rl_sar_blackw/policy/blackW/<name> \
  --level stairs_20cm --attempts 4 --json prep.d/results/blackw_official/<name>_stairs20.json
#    全 20 关 + 分档 gate（推荐，写 gate_*.json）：
pixi run python @20261024_blackw/scripts/gate_stage.py \
  --policy @20261024_blackw/ws/src/rl_sar_blackw/policy/blackW/<name> --stage s2
```

第 4 步有个坑：`check_walk_blackw.py` 的基准 config 写死成 `flat`（`check_walk_blackw.py:45,252-262,260`），所以它校验的「起身终点 = default_dof_pos」「rl_kp 跳变定位」用的一直是 **flat** 的数值。当前所有候选与 flat 数值相同所以不出错，但这是**下一个候选就会中的雷**（F11）。

---

## 4. 核心问题 4：验证覆盖

### 4.1 `check_walk_blackw.py` 到底检查什么（7 项，全部是平地行为）

| # | 判据 | 代码 |
|---|---|---|
| 1 | 起身终点 = `default_dof_pos`（经 `joint_mapping` 换序），误差 < 1e-3 rad | `:252-269` |
| 2 | 起身后站住：z > 0.38 m、tilt < 10° | `:275-276` |
| 3 | 前进+转向段没摔：z > 0.3 m、tilt < 20° | `:285-286` |
| 4 | 策略周期 19–23 ms（仿真时间；全速跑放宽到均值 <30 ms） | `:297-311` |
| 5 | 转向跟得上：陀螺 z 均值 > 0.7 × 指令 | `:316-317` |
| 6 | 按 B 后回到起身前姿态并进阻尼 | `:328-329` |
| 7 | 实时率 ≥ 0.95x（全速跑则量吞吐） | `:338-340` |

场景是 `scenes/blackW/scene.xml`（**平地**，`check_walk_blackw.py:162`），命令是**常量** `VX=1.0 m/s` 前进 + `WZ=1.0 rad/s` 转向（`:53-54`），时间线固定 32 s（`:58-66`）。

### 4.2 对 Part2 20 关的覆盖：**0/20**

- 没有 `--part2-level` 之类的入参（`:149-152` 只有 `--start/--realtime/--policy/--sim-param`）。
- 判据里没有任何「障碍面高度/车轮 x·z/落地支撑」量；`STATUS_RE`（`:47`）只从 sim 状态行拿 `t,x,y,z,tilt,ncon`。
- 命令 profile 只有常量，没有 judge 的「x>1.6 m 后从 0.65 降到 0.35」「x>1.1 m 后 0.75→0.45」这类**分段 profile**（judge 侧在 `gate_stage.py:74-80` 与 `eval_blackw_part2.py:442-450`）。
- 出生点固定（不起 `spawn_x/y/z/yaw`），没有 gate 要求的 ±0.10 m / ±0.15 m / ±0.05 rad 随机化。

所以：**当前无法对任何候选 policy 做「部署仿真逐档 smoke」**（F2）。

### 4.3 建议补的脚本：`scripts/smoke_deploy_part2.py`（设计稿）

**接口**：`--policy <dir> --levels all|<key,...> --tier 0.6,1.0,1.3 --attempts 4 --realtime false --json out.json`。

**驱动方式**（不改 C++ 的最小路径）：`X`/`N` 切换 `navigation_mode`（`input_map.hpp:73`），之后 `rl_sim` 读 `/cmd_vel`（`rl_sim.cpp:448-455`），smoke 脚本按 50 Hz 发 `Twist`；起身/进 RL 仍用 `/joy`（照 `check_walk_blackw.py` 的 TIMELINE 前 6 s）。这样命令是**确定量**而不是摇杆量，且能复刻分段 profile。

**每档指标**（都要落 JSON，便于与 judge 对齐）：

| 指标 | 采集 | 判定（对齐 `part2_official_levels.json` 的 `judge` 块） |
|---|---|---|
| 前进距离 `x_end` | 状态行 `x` | 平台 x∈[2.0,3.25]；斜坡 `goal_x_min=3.9`；楼梯 `goal_x_min=3.7` 且 `descend_end_x=6.2`；墙 `goal_x_min=2.27`；沟 `far_x`（3.9/4.0/4.1） |
| 高度 `z`（分档窗口） | 状态行 `z` | 平台 `top_z±0.35` 并 hold 0.2 s；楼梯 `top_z`（0.6/0.9/1.2/1.8）；墙 `climb_z_min`（0.52…0.58）；沟 `z_cross_min=0.58` |
| 倾角 `tilt` | 状态行 | 全程 `tilt < 35°` 且末态 `< 15°`（失败判定用「翻倒」而不是「超时」） |
| 车道 | `y` | `abs(y) <= lane_half_width = 0.7`（墙/楼梯/沟都必须同车道通过） |
| 轮支撑 | **需要新增**（见下） | 四轮都在支撑面上/都在 `far_x` 之后（judge 用 `wheel_x/wheel_z`，`eval_blackw_part2.py:169-203`） |
| 时间 | `sim_time` | 每档 `seconds`：平台/墙/沟 15 s、斜坡 18 s、楼梯 30 s、梅花桩 18 s |
| 命令剖面 | 脚本自己记 | 各段实际 vx/wz，写进 JSON（judge 要求报 profile） |

**必须补的观测**：judge 的楼梯/墙/沟判据依赖**四个轮子的世界坐标**（`wheel_x/wheel_z`，`eval_blackw_part2.py:398-402,169-203`），而部署侧的状态行只有基座 `x/y/z/tilt`。两个选项：① 给 `sim_node` 的状态行/新 topic 加 4 个轮心 `x,z`（`sim_node.cpp:946-948` 已经有 `d->xpos` 的来源，改动 <20 行）；② smoke 脚本用 `/imu` + 16 关节角做正运动学反算。建议 ①，并把该 topic 定义成「judge 的输入契约」。

**与 judge 的对照方式**（这是「保证质量」的关键判据）：

1. 同一场景、同一 spawn（`part2_levels.json` 的 `spawn`）、同一命令 profile、同一 tier 集合下，部署 smoke 与 `eval_blackw_part2.py` 各跑一遍，比较**逐档 pass/fail 一致率**（目标 20/20 一致）与 `x_end/z` 的差值（目标 `|Δx| < 5 cm`、`|Δz| < 2 cm`）。
2. 现阶段预期**不一致**，且原因已知：`tau_max=20`（F1）。修完 F1 再对拍才有意义——所以 smoke 脚本应该**先**在 `tau_max:=59.25`（或修好后的默认）上跑，否则测的是部署 bug 不是策略。
3. 建议把这个对拍固化成 `scripts/comp_deploy_conformance.py`（可参照 Part1 的 `@20261019_locomotion/scripts/agent_scripts/comp_judge_conformance.py` 的写法：把判据抽成纯函数、用构造好的轨迹做单测，不需要 MuJoCo）。

---

## 5. 核心问题 5：作业脚本 / 队列契约

### 5.1 队列与清理（`common.sh` / `on_finish.sh` / `kill_test.sh`）

- **串行化**：`flock -w 600 /tmp/gpu.lock`（`common.sh:54-58`）后再等 `nvidia-smi` 空闲 <2500 MiB（`:59-63`）。这是「锁+实测」双保险，OK。
- **日志契约**：`exec > >(tee -a "$LOG")`（`:29`）+ `record()` 同时写 summary（`:47`）。注意 `tee` 是子进程，SIGTERM 时可能先死，所以 `on_exit` 只做文件写（`:32-36`），这个设计是对的。
- **SIGTERM 清理**：trap TERM/INT → `on_signal` → `exit $1`（`:37-45`）。证据 `~/rc_work/logs/ts_kill_test.log`：

```
[ts_kill_test] signal TERM 2026-10-26T08:39:12+08:00 -> cleanup
[ts_kill_test] end 2026-10-26T08:39:12+08:00 rc=TERM
```

  两个问题（F9）：① `exit "$1"` 里 `$1` 是字符串 `TERM`，bash 会报 `numeric argument required` 并以 **2** 退出（不是 143），而日志里记的是 `rc=TERM`（非数字），下游按数字解析会错；② 这个测试只验证了 `common.sh` 自己的 trap 与 summary 没有 `done` 行，**没有**验证 `on_finish.sh` 的 flag 恢复，而 `on_finish.sh` 的接入点**不在任何 shell rc 里**（`grep -rn TS_ONFINISH ~/.bashrc ~/.profile ~/.zshrc /etc/environment` 无命中；`ls ~/.ts_on_finish` 不存在），只有 `~/rc_work/logs/ts_on_finish.log` 证明它**曾经**被调用过 → 重启/换 shell 后这套保险可能静默失效。
- **flag 竞争**：`common.sh:34` 的 `on_exit` **无条件**把 `5060ti_machine_use_flag.txt` 写 0；`on_finish.sh:6-10` 才做了「还有其他 running 才不清」的判断。中断一个作业会把另一个作业的「GPU 占用」标志抹掉（F16）。
- `on_finish.sh:6` 用 `ts -l` 的**文本**判断 `other`（`awk '$1!=me && / running /'`）；`ts -l` 输出格式一变或 `ts` 不在 PATH，`other` 就算 0。证据：`ts_on_finish.log` 里 12 条记录 `other_running` **全是 0**，包括 09:35:13 同一秒结束的 job 9 与 job 10（其中一个 err=1），说明这个判断很可能一直没起作用。

### 5.2 resume / 迭代数 / 导出 / 失败传播（`ppo_*.sh`）

| 契约项 | 现状 | 证据 |
|---|---|---|
| resume 路径 | 三种写法并存：① `--agent.load-run <字面量>` + `--agent.load-checkpoint model_XXX.pt`（`ppo_st30_s075.sh:17-22`）；② 硬编码 `PREVNAME=2026-10-26_09-18-17_ppo_st30_s100` + `model_650.pt`（`ppo_m0_trench20.sh:19-20`、`ppo_m0_hardmask.sh:23-24`）；③ 动态 `ls -dt` 取最新 run（`ppo_st30_s100.sh:32`、`ppo_slope_mu12.sh:60,77`） | 见左 |
| 迭代数语义 | `--agent.max-iterations N` 在 resume 时是**增量**（650 → 949），不是绝对上限 | `ppo_m0_trench20_summary.txt` 的 `export 650/700/750/800/850/900/949` |
| 导出 | 每个 `model_*.pt` 调一次 `export_blackw_policy.py`（`ppo_m0_trench20.sh:40-46`） | 同上，7 个 export rc=0 |
| **失败传播** | **断在导出**：`record "export ... rc=$?"` 只记录，最终 `exit $RC` 用的是 **train 的 rc**（`ppo_st30_s100.sh:47,60-61`、`ppo_m0_trench20.sh:34,45,49-50`）；对比 `export_guard4.sh:12,25,32` 是正确写法（累计 `fail` 并 `exit $fail`） | `export_guard4.sh` vs 两个 `ppo_*.sh` 并排看 |
| **summary 成功标记** | `record "$JOB done ..."` **无条件**写（`ppo_st30_s100.sh:60`、`ppo_st30_s075.sh:39`、`ppo_m0_*.sh:49/56`），而 `common.sh:8` 把「最后一行 `<job> done <time>`」定义为完成标记 → **失败作业也以 done 结尾** | `ppo_m0_trench20_summary.txt` 末行 `ppo_m0_trench20 done …`，但 line 1 的日志标签写的是 `m0 slope35`（`ppo_m0_trench20.sh:21` 复制粘贴错标） |
| gate/质量 | 没有任何 `ppo_*.sh` 调 judge；只有 `check_tier_success.py` 的 **训练环境**诊断（`ppo_m0_trench20.sh:22-26`），且其 `success_rate` **不是 fail 条件** | `ppo_m0_trench20_summary.txt`：`train rc=0`、导出全 0，但 `part2_success: 0.40 → 0.28 → 0.2353`（持续下降）仍判「done」 |

### 5.3 「任务看似成功但结果无效」的 4 条实际路径

1. **train rc=0 + 导出 rc≠0** → 作业 rc=0、summary 有 `done`，但 `~/rc_work/models/<name>/` 没有可用 `.pt`（F8）。
2. **train rc=0 + 成功率下行** → 如 `ppo_m0_trench20`（0.40→0.2353），无 gate 判定（F12）。这与 `guard4` 的教训同型：800 iter 跑完、复核「无可捞档位」。
3. **硬编码续训点失效** → `PREVNAME` 指向不存在的 run 时，先跑的 env-build smoke 会失败并 `exit`，但 summary 里记的是 `env-build smoke FAILED`，**真因（checkpoint 不存在）不出现在 summary**（`ppo_m0_trench20.sh:22-27`）。
4. **gate 结果不写 summary**：`gate_stage.py` 是本地脚本，产物写 `prep.d/results/**/gate_*.json`（`gate_stage.py:274-276`），**不回流**远程 summary；HIM 线的作业（`him_model0_gate20_1026_1214_summary.txt`）已经把 `gate ... pass=False rate=0.650` 写进 summary，PPO 线应当照抄这个格式。

---

## 6. 发现清单

### P0

#### F1 —— 部署 sim 把所有关节力矩夹到 20 N·m，小腿在训练/judge 里是 59.25 N·m
- **严重度**：P0
- **文件:行**：`@20261024_blackw/ws/src/quadruped_ros2_blackw/include/quadruped_ros2_blackw/motor.hpp:41,59-63`；`@20261024_blackw/ws/src/quadruped_ros2_blackw/src/sim_node.cpp:186,803,855`；`@20261024_blackw/ws/src/rl_sar_blackw/policy/blackW/fsm.hpp:271`；`@20261024_blackw/ws/src/rl_sar_blackw/library/core/rl_sdk/rl_sdk.cpp:176`；`scenes/blackW/blackW_description.xml:197-214`
- **问题**：`motor.hpp` 的 MIT 力矩限幅是**标量** `tau_max`（默认 `kDefaultTauMax = 20.0`，注释说「取本模型 actuator 的 ctrlrange（±20）」，那是 12 关节 black 的口径）。blackW 的 MJCF 已经是**逐关节** `ctrlrange` = `23.7 / 59.25 / 20`，但 `sim_node` 仍用 `quadruped::motor::Bank(..., opt.tau_max, m->nu)` 一个数字管 16 个关节，且 launch/README/自检**从未传过 `tau_max`** → 小腿实际被夹到 20 N·m（与训练/judge 的 59.25 差 3 倍）。而 `config.yaml` 里那份 `torque_limits`（含 59.25）只在 `rl_sdk.cpp:176` 用来夹一个**随后被丢弃**的 `output_dof_tau`（`fsm.hpp:271` 把 `tau` 置 0），根本没进动力学。
- **证据/复现**：
  ```bash
  grep -n "kDefaultTauMax\|std::clamp(tau" @20261024_blackw/ws/src/quadruped_ros2_blackw/include/quadruped_ros2_blackw/motor.hpp
  # 41: inline constexpr double kDefaultTauMax = 20.0;
  # 62:     return std::clamp(tau, -tau_max, tau_max);
  grep -n "tau_max" @20261024_blackw/ws/src/quadruped_ros2_blackw/src/sim_node.cpp
  # 186/227/803：标量、launch 未覆盖
  grep -rn "tau_max" @20261024_blackw/ws/src/rl_sar_blackw/launch/ @20261024_blackw/scripts/ @20261024_blackw/README.md
  # 无输出
  grep -n "self.torque_limits" @20261024_blackw/scripts/eval_blackw_part2.py
  # 282（来自 config 的逐关节数组）、381（tau 按逐关节夹）：judge 是逐关节
  ```
  旁证（同一仓库自己写下的教训，`policy/black/base.yaml:41-46`）：「Clamping at the model's own 20 N.m was measured to bite ~2% of control cycles during a normal walk … and, because it rewrites q_des, it distorts the policy's output」。
- **影响**：① 「judge 750/1300」不能推出「sim 里同样表现」；楼梯/平台/高墙这类依赖小腿大扭矩的档位在 sim 里会**系统性变差**；`command_tau_limit: 33.5`（`base.yaml:13`）与 `torque_limits` 的「训练包络」设计被下游 20 一刀切掉；② 实机同样要逐关节复刻，否则实机行为不可预测。
- **建议修法**：把 `tau_max` 改成**逐关节数组**（从 `policy/blackW/<policy>/config.yaml` 的 `torque_limits` 读，或在 `sim_node` 增加 `tau_max_array` 参数，默认取模型 `ctrlrange` 的逐执行器值）；`Bank` 内部按关节索引取限值；`sim_node` 启动时打印 16 个限值并与 config 对账（不一致直接报错退出）；修正 `motor.hpp:39-41` 的注释（它现在描述的是 black，套到 blackW 上是错的）。修完必须重跑 §4.3 的对拍。

#### F2 —— 没有「部署仿真逐档 smoke」，Part2 20 关在部署栈上零证据
- **严重度**：P0
- **文件:行**：`@20261024_blackw/scripts/check_walk_blackw.py:47,53-54,58-66,149-152,162`；`@20261024_blackw/ws/src/rl_sar_blackw/launch/rl_sim_blackw.launch.py:37-52`；`@20261024_blackw/ws/src/rl_sar_blackw/scenes/blackW/part2_levels.json`；`@20261024_blackw/scripts/gate_stage.py:74-80`
- **问题**：唯一的无头自检只跑平地场景 + 常量 1.0 m/s / 1.0 rad/s，7 项判据全是「站住/没摔/周期/转向」，没有任何障碍判定；20 关的 judge 判据（`part2_official_levels.json` 的 `judge` 块）在部署侧没有实现，命令 profile（0.65→0.35、0.75→0.45、0.3）只在 judge 侧存在。
- **证据/复现**：
  ```bash
  grep -n "CONFIG =\|scene.xml\|VX =\|WZ =\|--policy" @20261024_blackw/scripts/check_walk_blackw.py
  # 45/162/53/54/149：平地 + 常量命令
  python3 -c "import json;d=json.load(open('@20261024_blackw/ws/src/rl_sar_blackw/scenes/blackW/part2_official_levels.json'));print(len(d['levels']),'levels,', sum(1 for e in d['levels'] if 'judge' in e),'with judge rules')"
  # 20 levels, 20 with judge rules（但部署侧无消费者）
  ```
- **影响**：无法回答「这份 .pt 在 sim 里能不能过第 N 关」；`comp_bc_v5` 的 750 分只有 Python judge 证据。
- **建议修法**：按 §4.3 落地 `smoke_deploy_part2.py` + 状态行补 4 轮世界坐标；把它接进 `ppo_*.sh`（导出后立刻跑最低档，失败则 `RC≠0`）；对拍 `eval_blackw_part2.py`。

### P1

#### F3 —— 导出 drop-in 契约不自足：导出器不产 config.yaml，`contract.json` 的 `action_scale` 右腿符号错
- **严重度**：P1
- **文件:行**：远程 `~/rc_work/part2_team_race/scripts/agent_scripts/export_blackw_policy.py:152-169`；`@20261024_blackw/scripts/export_bc_policy_local.py:78-96`；`@20261024_blackw/ws/src/rl_sar_blackw/library/core/rl_sdk/rl_sdk.cpp:154,404`；`@20261024_blackw/training/blackw/env_cfgs.py:68-77`
- **问题**：PPO 导出只写 `policy.pt + contract.json`；`contract.json` 里 `"action_scale": [0.25,0.25,0.25,10.0]*4` 与训练代码（FR/RR = **-10**）和部署 config 都矛盾。本地 BC 导出靠**拷贝官方 `obstacle/config.yaml`** 绕过这个问题，且不写 manifest/sha。`model_path` 是死字段。
- **证据/复现**：
  ```bash
  ssh bis-ms7e56 'ls ~/rc_work/models | wc -l; ls ~/rc_work/models/*/contract.json | wc -l; ls ~/rc_work/models/*/config.yaml 2>/dev/null | wc -l'
  # 102 / 101 / 0
  ssh bis-ms7e56 'python3 -c "import json;d=json.load(open(\"/home/bis/rc_work/models/dt2ms_700/contract.json\"));print(d[\"action_scale\"])"'
  # [0.25, 0.25, 0.25, 10.0, ...]  ← 右腿轮应为 -10
  ```
- **影响**：谁按 `contract.json` 手搓 config，右前/右后轮反向；没有 manifest 时也无法证明「这份 .pt 用的是哪份 config」。
- **建议修法**：导出器**同时写 `config.yaml`**（模板来自官方 `obstacle/config.yaml`，`action_scale` 用 `_wheel_leg_scale()` 的真值）+ 写 manifest（policy sha256、config sha256、训练时的 dt/decimation/命令范围/gate 结果）；`contract.json` 里的 `action_scale` 改成带符号的 16 维；把「policy.pt 与 config.yaml 必须同目录、key 必须等于目录名」做成导出后自检。

#### F4 —— 83/129 个策略目录的 `config.yaml` 顶层 key 与目录名不符：judge 能读、C++ 部署打不开
- **严重度**：P1
- **文件:行**：`@20261024_blackw/ws/src/rl_sar_blackw/library/core/rl_sdk/rl_sdk.cpp:392-402`；`@20261024_blackw/ws/src/rl_sar_blackw/policy/blackW/fsm.hpp:233-246`；对照 `@20261024_blackw/scripts/eval_blackw_part2.py:83-97`
- **问题**：C++ 用 `YAML::LoadFile(cfg)["blackW/<dir>"]` 取子节点，key 不符 → undefined → `config["model_name"].as<std::string>()` 抛异常 → `InitRL() failed`；Python 的 `load_policy_config()` 有「单 key 就整份用」的兜底，所以这些目录**能被 judge 评分但永远不能被 launch 加载**。
- **证据/复现**：见 §3.4 的 129/83 统计命令；`ls @20261024_blackw/ws/src/rl_sar_blackw/policy/blackW | wc -l` → **133 项**（131 个子目录 + `base.yaml` + …），其中有 `config.yaml` 的 129 个，`comp/` 只有 config 没有 `policy.pt`。
- **影响**：评测结论与演示能力脱节；审计/回归用的 `eval_*`、`reg_*`、`st30_*`、`ts_trial_*` 权重全是「只能评不能演」。
- **建议修法**：① C++ 侧加兜底（子节点不存在且文件只有一个顶层 key → 用它，并打 `[yaml] config key mismatch: expected blackW/<dir>, found …` 警告）；② 或者批量重写这 83 份 key（一行 `sed`，但会改动他人施工区，需所有者执行）；③ 加一个 `scripts/check_policy_dirs.py` 当 CI 断言。

#### F5 —— README 手柄键位与代码不符（进 RL / 复位两处），照文档按不出演示
- **严重度**：P1
- **文件:行**：`@20261024_blackw/README.md:162` vs `@20261024_blackw/ws/src/rl_sar_blackw/include/input_map.hpp:148-159`
- **问题**：README 写「`X` 复位、`LB+上` 进 RL」；代码是 **ResetSim = RB + Y**、**EnterRL = RB + D-pad 上**，`X` 是 `ToggleNavigation`。键盘行（`:161`）是对的。
- **证据/复现**：`grep -n "EnterRL\|ResetSim\|ToggleNavigation" @20261024_blackw/ws/src/rl_sar_blackw/include/input_map.hpp` → 148-153 行；`check_walk_blackw.py:59-60` 的 TIMELINE 用的也是 `RB`，与 README 相反。
- **影响**：人类按 README 操作会卡在 GetUp，无法进 RL（这正好解释「看起来没反应」）。
- **建议修法**：改 README 一行；顺手把「进 RL 的前置=起身斜坡走完」写成显式步骤。

#### F6 —— slew 限幅的有效上限是 15 rad/s（文档写 60），且随 `dt` 变化
- **严重度**：P1
- **文件:行**：`@20261024_blackw/ws/src/rl_sar_blackw/include/command_limit.hpp:109-118`；`@20261024_blackw/ws/src/rl_sar_blackw/src/rl_sim.cpp:407-440`（控制节拍 5 ms）；`policy/blackW/base.yaml:17`
- **问题**：限幅器每**控制周期**（5 ms）判一次 `|q_des - q_des_prev| <= 60 × 0.005 = 0.30 rad`，但 `q_des` 每**推理**（20 ms）才变一次 → 有效上限 0.30 rad/20 ms = **15 rad/s**，不是配置的 60；改成 0.002/10 后变成 6 rad/s（**更紧**）。
- **证据/复现**：读代码即可；运行时可通过 `status_period_ms:=500` 观察 `cmd_limit_events` 计数，或临时把 `command_slew` 调到 500 看是否仍在某档位卡住。
- **影响**：大跨度姿态（跨台阶的落足、从起身到行走的第一步）可能被**永久截断**（下一次控制周期目标不变，限幅器不再继续追），表现为动作迟滞/落足不到位；这与「60 rad/s 只防阶跃」的设计意图不符。
- **建议修法**：slew 的时基改成「距上次**目标变化**的仿真时间」（或用 `decimation × dt`），或在 `SetCommand` 里只在新推理的那一拍做 slew；文档改成有效值。

#### F7 —— 频率契约只存在于 base.yaml，无 per-policy 覆盖、无校验；manifest 与 base.yaml 自相矛盾
- **严重度**：P1
- **文件:行**：`@20261024_blackw/ws/src/rl_sar_blackw/policy/blackW/base.yaml:3-4`；`@20261024_blackw/ws/src/rl_sar_blackw/library/core/rl_sdk/rl_sdk.cpp:376-377`；`@20261024_blackw/ws/src/rl_sar_blackw/policy/black/knobs.hpp:143-144`；`@20261024_blackw/models/comp_bc_v5/manifest.json:9-11`；`@20261019_locomotion/docs/training/part2-ppo-handoff-2026-10-26.md:47`
- **问题**：`dt/decimation` 只在 `base.yaml`（构造时读一次），`config.yaml` 里没有频率字段，`WarnIfBaseConfigMismatch()` 只比 7 个键、不涉频率；manifest 写 `physics_dt_s 0.002 / policy_rate_hz 50`，base.yaml 写 `0.005 / 4`；交接文档又把 `BLACKW_PHYSICS_DT=0.002/BLACKW_DECIMATION=10` 称作「部署契约」。三处口径不一致，且没有任何运行期校验。
- **证据/复现**：`sed -n '3,4p' .../base.yaml`；`grep -n "PHYSICS_DT" @20261019_locomotion/docs/training/part2-ppo-handoff-2026-10-26.md`（`:47`）；`python3 -c "import json;print(json.load(open('@20261024_blackw/models/comp_bc_v5/manifest.json'))['deployment_contract'])"`。
- **影响**：换一份按别的频率训的权重，部署侧**不会有任何提示**；也就是「静默按错的频率跑」是可能的（虽然当前所有候选都是 50 Hz 策略）。
- **建议修法**：把 `control_hz/policy_hz` 写进每份 `config.yaml` 并在 `InitRL` 里与 `dt/decimation` 对账（不一致 → ERROR 日志 + 拒绝进 RL）；manifest 与 base.yaml 二选一作为真值。

#### F8 —— `ppo_*.sh` 的导出失败不进最终 rc；summary 的 `done` 行无条件写
- **严重度**：P1
- **文件:行**：`ppo_st30_s100.sh:24-28,46-47,60-61`；`ppo_m0_trench20.sh:40-46,49-50`；`ppo_st30_s075.sh:27-32,39`；对照 `export_guard4.sh:12,25,30-32`；契约定义 `common.sh:8`
- **问题**：导出循环只 `record ... rc=$?`，最终 `exit $RC` 用的是 train 的 rc；`record "$JOB done"` 无条件执行，而 `common.sh:8` 把「最后一行 done」当完成标记。
- **证据/复现**：`cat ~/rc_work/logs/ppo_m0_trench20_summary.txt`（导出 7 条 rc=0、末行 done）；`cat ~/rc_work/gpu_jobs/export_guard4.sh`（正确写法累计 `fail` 并 `exit $fail`）。反面例子：`ts_on_finish.log` 里 job 8（`ppo_st30_s100.sh`）`err=1`，其 summary 仍然以 `done` 结尾。
- **影响**：出现「作业绿色、模型目录空/不完整」；下游按 rc 或 done 行筛结果会漏。
- **建议修法**：导出累计 `fail` 并入 `RC`（照 `export_guard4.sh`）；`done` 行改成 `record "$JOB end rc=$RC ..."`，成功才写 `done`（或写 `done rc=0` / `failed rc=N`）。

#### F9 —— SIGTERM 退出码变成 2，日志记 `rc=TERM`；`on_finish` 接入点不存在于任何启动文件
- **严重度**：P1
- **文件:行**：`common.sh:37-45`（`on_signal` 里 `RC=$1; exit "$1"`）；`on_finish.sh:4-10`
- **问题**：`$1` 是字符串 `TERM`，`exit "TERM"` → bash `numeric argument required` → 退出码 **2**；summary/log 里出现非数字 `rc=TERM`。另外 `TS_ONFINISH` 只在历史日志里有痕迹，`~/.bashrc/~/.profile/~/.zshrc//etc/environment` 都没有导出，`~/.ts_on_finish` 不存在。
- **证据/复现**：`cat ~/rc_work/logs/ts_kill_test.log`（末行 `rc=TERM`）；`ssh … 'grep -rn TS_ONFINISH ~/.bashrc ~/.profile ~/.zshrc /etc/environment; echo rc=$?'`。
- **影响**：中断作业退出码与 143 不符，任何按退出码归类（killed vs failed）的统计都错；换机/重启后 `on_finish` 可能不再被调用，`5060ti_machine_use_flag.txt` 残留为 1。
- **建议修法**：`on_signal()` 用 `RC=$((128 + n))` 映射（TERM→143、INT→130）再 `exit`；把 `TS_ONFINISH`/`TS_SOCKET` 写进 `common.sh` 注释里指定的 shell 启动文件，并在 `common.sh` 启动时断言 `on_finish.sh` 可执行（不存在就 WARN）。

#### F10 —— `ppo_m0_*.sh` 硬编码续训点 + 日志/标签复制粘贴错误
- **严重度**：P1
- **文件:行**：`ppo_m0_trench20.sh:19-21`；`ppo_m0_hardmask.sh:23-25`
- **问题**：`PREVNAME=2026-10-26_09-18-17_ppo_st30_s100`、`model_650.pt` 是字面量；`ppo_m0_trench20.sh:21` 的 `record` 写成 **`m0 slope35`**，与 `ppo_m0_slope35.sh` 的 summary 首行**逐字节相同**（只差 task 名）。硬编码 run 不存在时，失败信息只会显示 `env-build smoke FAILED`。
- **证据/复现**：`diff <(head -1 ~/rc_work/logs/ppo_m0_slope35_summary.txt) <(head -1 ~/rc_work/logs/ppo_m0_trench20_summary.txt)` → 仅 task 名不同。
- **影响**：台账不可信（凭 summary 首行无法区分 slope35 与 trench20）；换 stage 时忘改续训点会**静默复用旧权重**（smoke 通过、结果作废）。
- **建议修法**：续训点改为 `ls -dt logs/rsl_rl/black_velocity/*_ppo_st30_s100 | head -1` + `ls -t …/model_*.pt | head -1`（照 `ppo_slope_mu12.sh:60,77`），并 `record "resume ck=$PREVNAME/$PREVCK"`；修掉标签。

### P2

#### F11 —— `check_walk_blackw.py` 的基准 config 写死成 `flat`
- **严重度**：P2
- **文件:行**：`@20261024_blackw/scripts/check_walk_blackw.py:45,252-262,260`；`--policy` 默认值 `:149`
- **问题**：无论 `--policy` 传什么，`expect`（`default_dof_pos` 换序）与 `rl_kp` 都取自 `policy/blackW/flat/config.yaml`；当前所有候选数值相同所以不报错，换一份 `rl_kp` 不同（如 45）的权重，第 1 项与「进 RL 定位」会误判。
- **证据/复现**：`grep -n "CONFIG =\|rl_kp = float" @20261024_blackw/scripts/check_walk_blackw.py`。
- **建议修法**：`CONFIG = POLICY_ROOT / args.policy / "config.yaml"`，并顺手断言 key == 目录名。

#### F12 —— `ppo_*.sh` 不调 judge，成功率下行不是失败条件
- **严重度**：P2
- **文件:行**：`ppo_m0_trench20.sh:47`（只 grep 训练日志）、`ppo_st30_s100.sh:51-58`（`check_tier_success.py` 只做诊断）
- **问题**：作业结束条件只有 `train rc`；`part2_success` 只打印不判定，无 gate 门槛、无 judge。
- **证据/复现**：`ppo_m0_trench20_summary.txt`：`0.4000 → 0.2800 → 0.2353` 仍 done；对照 HIM 的 `him_model0_gate20_1026_1214_summary.txt` 有 10 行 `gate ... pass=... rate=...`。
- **建议修法**：把 `gate_stage.py`（或最小版本「最低档 8/8」）接进作业，结果写 summary（`gate c=stairs s=10 pass=False rate=0.5`），并把 gate 不通过并入 `RC`。

#### F13 —— 训练快照不完整 / 文档引用不存在的脚本
- **严重度**：P2
- **文件:行**：`@20261024_blackw/training/blackw/env_cfgs.py:36`（`from …blackw.actions import WheelLegActionCfg`）；`@20261024_blackw/scripts/export_bc_policy_local.py:4-9`（docstring 引用 `export_history_policy.py`）
- **问题**：本地 `training/blackw/` 没有 `actions.py`、`him*` 等被 import 的模块（交接文档说「代码快照在 training/」，实际只能看不能跑）；`export_history_policy.py` 在两个仓库都不存在（远程叫 `export_blackw_policy.py`）。
- **证据/复现**：`ls @20261024_blackw/training/blackw`；`find . -name export_history_policy.py`（无输出）。
- **建议修法**：补齐快照并在 `training/README.md` 标「只读快照，不可执行」；改 docstring。

#### F14 —— `RL_DEBUG_OBS` 埋了钩子但没有消费者，obs 对拍从未发生
- **严重度**：P2
- **文件:行**：`@20261024_blackw/ws/src/rl_sar_blackw/src/rl_sim.cpp:515-527`
- **问题**：写 `/tmp/rl_obs_debug.csv`（前 60 帧 obs57+act16），全仓无任何脚本读取；因此「部署 obs == judge obs」从未被数值验证。
- **证据/复现**：`grep -rn "rl_obs_debug\|RL_DEBUG_OBS" --include=*.py --include=*.md --include=*.sh .`（无命中）。
- **建议修法**：写 `scripts/compare_obs_deploy_vs_judge.py`：judge 侧加同样的 dump，逐帧比 `max|Δobs|`（目标 <1e-4）；这条比任何「看起来能走」都更能证明契约一致。

#### F15 —— `rl_sim` 的 `main()` 没有 try/catch，权重维度不对会整进程退出
- **严重度**：P2
- **文件:行**：`@20261024_blackw/ws/src/rl_sar_blackw/src/rl_sim.cpp:538-543`；`Forward()` `:486-536` 无异常处理
- **问题**：`torch::jit` 输入维度不匹配时抛异常，经 `RunModel → ControlStep → MotorStateCallback` 逸出 `rclcpp::spin` → `std::terminate`；`sim_node` 还活着，看门狗 200 ms 后转阻尼（狗会突然软掉），日志只有 aborted。
- **证据/复现**：把一份 45×k 的 HIM 权重改名成 `policy.pt` 放进某目录并进 RL，观察 `rl_sim` 进程退出。
- **建议修法**：`InitRL` 里先做一次 `model.forward(torch::zeros({1, 342}))` 的 dry-run，失败则 ERROR + 拒绝进 RL；`main()` 包 try/catch 打日志后退出码 1。

#### F16 —— GPU flag 竞争 + `ts -l` 文本解析
- **严重度**：P2
- **文件:行**：`common.sh:32-36`（无条件写 0）；`on_finish.sh:6-10`
- **问题**：见 §5.1；`ts_on_finish.log` 12 条记录 `other_running` 全 0（含同一秒结束的两个作业），说明判据基本没生效。
- **证据/复现**：`tail -12 ~/rc_work/logs/ts_on_finish.log`。
- **建议修法**：flag 改成「作业 id 集合」或带 flock 的计数文件；`on_finish` 的「其他 running」改用 `ts -l` 的结构化字段（或读 `/tmp/gpu_queue.socket` 状态、或用 `pgrep -f gpu_jobs/`）。

---

## 7. VERDICT

**`BLOCKED`**

阻塞项：

- **B1 = F1**：部署 sim 的力矩限幅（20 N·m 标量）与训练/judge（逐关节 23.7/59.25/20）不等价 → 任何「部署质量」结论都不成立。
- **B2 = F2**：没有 Part2 逐档部署 smoke，20 关在部署栈上零证据 → 无法对候选策略做逐档判定。
- **B3 = F3**：drop-in 契约不自足（导出器不产 config.yaml、`contract.json` 的 `action_scale` 右腿符号错、`model_path` 死字段）→ 「按契约放进去就能启动」这句话目前依赖人工照抄 `obstacle/config.yaml` 的隐性知识。

非阻塞但必须在 demo 前修：F5（README 键位，否则人按不动）、F8/F9（作业出口契约，影响"最新权重是哪份"的可信度）。

## 附录 A：本报告用到的复现命令（全部只读）

```bash
# 部署侧关键数值
sed -n '3,4p;13p' @20261024_blackw/ws/src/rl_sar_blackw/policy/blackW/base.yaml
grep -n "kDefaultTauMax\|std::clamp(tau" @20261024_blackw/ws/src/quadruped_ros2_blackw/include/quadruped_ros2_blackw/motor.hpp
grep -n "timestep" @20261024_blackw/ws/src/rl_sar_blackw/scenes/blackW/blackW_description.xml
grep -n "dt\|decimation" @20261024_blackw/ws/src/rl_sar_blackw/library/core/rl_sdk/rl_sdk.cpp | head -4
# 策略目录自洽性
cd @20261024_blackw/ws/src/rl_sar_blackw/policy/blackW && python3 -c "
import yaml,glob,os
ds=[d for d in sorted(glob.glob('*/')) if os.path.exists(d+'config.yaml')]
print(len(ds),'dirs')
print(sum(1 for d in ds if list(yaml.safe_load(open(d+'config.yaml')))[0]!='blackW/'+d.rstrip('/')),'key mismatch')"
# TorchScript 自足性
pixi run python -c "import torch;m=torch.jit.load('@20261024_blackw/ws/src/rl_sar_blackw/policy/blackW/comp_bc_v5/policy.pt').eval();print(m(torch.zeros(1,342)).shape)"
# 远程（只读）
ssh bis-ms7e56 'cat ~/rc_work/gpu_jobs/common.sh ~/rc_work/gpu_jobs/ppo_m0_trench20.sh'
ssh bis-ms7e56 'cat ~/rc_work/logs/ppo_m0_trench20_summary.txt ~/rc_work/logs/ts_on_finish.log'
ssh bis-ms7e56 'ls ~/rc_work/models/*/config.yaml 2>/dev/null | wc -l'
```

## 附录 B：本次未能验证、需要动手才能确认的项

1. **F1 的实际影响幅度**：需要修好后重跑对拍，才能说「20 N·m 让楼梯 20 cm 从 4/4 掉到几成」。本次只做了代码级判定。
2. **`YAML::Exception` 的具体类型**：由 yaml-cpp 语义推断（undefined node 上 `.as<std::string>()` 抛异常），未实跑 `policy_name:=eval_hm650` 验证；预期表现是进 RL 时 `InitRL() failed`。
3. **slew 截断在真实轨迹上的出现频率**：需要开 `status_period_ms:=500` 看 `cmd_limit_events`，或加临时计数。
4. **`on_finish.sh` 当前是否仍被 `tsp` 调用**：`~/.local/bin/ts -> tsp`，daemon `pid 91613` 的 environ 无读权限；结论是「历史有效、接入点不可追溯」。
5. **实机驱动侧**：本仓库没有驱动节点，实机的关节顺序/零位/限幅/时钟全部未知，无法评估。
