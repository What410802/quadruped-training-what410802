# PPO/BC 盲侧训练-评测线核心代码审计（round 1）

> 审计员：只读独立审计（未修改仓库任何文件、未在远程机写文件、未提交任何 GPU 任务）。范围：PPO/BC 盲侧线的**训练与评测核心**（judge/评测协议、gate 协议、训练 reward/termination/reset/命令/地形/物理对齐、resume 继承、GuardedPPO、导出契约的训练侧）、远程训练仓对应模块与 `~/rc_work/gpu_jobs/*.sh` 契约。HIM 线不在范围内；部署栈（C++ / sim_node / config.yaml 消费侧）由另一审计员负责，本文只在接口处标注并指向 [`ppo-deploy-audit-round1.md`](ppo-deploy-audit-round1.md)。
> 审计时间：2026-10-26。工作目录 `/home/bis/BiS.d/Code.d/RoboCon/MyMonoRepo.d`；远程机 `bis-ms7e56.tail4413b4.ts.net` 以 `ssh -o BatchMode=yes` 只读访问。

## 0. 结论速览

| # | 结论 | 严重度 |
|---|---|---|
| 1 | **blackW 全部任务的 domain randomization 被静默删除**（`_override_events` 整字典替换），与文档"已有 DR 保持不变"相反，`check_tier_success --no-dr` 与"随机化 gate"已是同一条命令 | P0 |
| 2 | **续训时学习率被 checkpoint 里的 optimizer 静默覆盖**（`BLACKW_LR=4e-5` 实际是 1e-5），"lr 4e-5 + 小步长"的方法学叙述与 A6a 单变量 A/B 都不成立 | P0 |
| 3 | `blackw-plum` 的 `plum_foothold` 仍是**状态式每步奖励**（可站着刷），违反团队自己的"不要状态式 shaping"硬规则 | P0 |
| 4 | 训练侧 `cfg.sim.ccd_iterations = 0` 是**死写**（字段在 `sim.mujoco`），注释声称的"关闭 CCD"不存在 | P1 |
| 5 | `blackw-platform-exact/-easy` 的专用成功终止（root z≥0.72）与 50 权重 height 奖励在 10 cm 起点**永不触发**，且"success-gated 升档"从未实现（terrain 行被 pop 后固定为 0） | P1 |
| 6 | `check_tier_success --episodes 3`（文档推荐命令）**永远只能跑 2 个 episode**（`max_steps` 公式被 20 s episode 卡死），输出无 truncated 标记 | P1 |
| 7 | 训练 `lane_deviation` 用 0.90/0.80，judge 与 success 谓词用 0.70 → 0.7<\|y\|<0.9 区间在训练里白跑 | P1 |
| 8 | judge 存在 3 处 fail-open 默认值（`descend_end_x` 回退、`wheel_bodies` 少于 4 个时 `np.all([])==True`、`hold_s`/`lane` 默认） | P1 |
| 9 | 远程还有**第二个口径完全不同的 judge**（`eval_blackw_official.py`：墙在 2.5 m、楼梯不要求下台阶、只看 root 高度），无弃用标记 | P1 |
| 10 | 权威 judge 本体与训练谓词**逐条对齐**（20 关几何、hold、四条轮支撑带、trench/plum 判负），导出 342 布局与 mjlab 原生历史顺序一致，resume 迭代语义正确 —— 这些不用再查 | 已核实 |

**VERDICT：`BLOCKED`**（阻塞项 = P0-1、P0-2、P0-3）。

## 1. 审计范围、方法与证据来源

- 本地逐行通读：`@20261024_blackw/scripts/{eval_blackw_part2.py,gate_stage.py,check_tier_success.py}`、`@20261024_blackw/training/blackw/{env_cfgs.py,exact_terrain.py,guarded_ppo.py,__init__.py}`、`@20261024_blackw/training/black/{black_config.py,rl_cfg.py}`。远程侧 `export_blackw_policy.py` 不在本地快照里，按远程副本审阅（`@20261024_blackw/scripts/export_bc_policy_local.py` 是 BC 导出，不是这条线）。
- 远程只读抓取到 `/tmp/ppo_audit/` 后比对：`diff -q` 显示 `blackw/{env_cfgs.py,exact_terrain.py,guarded_ppo.py,__init__.py}` 与 `black/{black_config.py,rl_cfg.py}` **与远程训练仓逐字节相同**（全部无输出）→ 快照 = 运行时真值，本报告的 `文件:行` 两边通用。
- 远程额外只读审阅：`src/alldog_mjlab/tasks/velocity/black/{curriculum_checkpoint.py,env_cfgs.py,rewards.py}`、`scripts/agent_scripts/*.py`、`~/rc_work/gpu_jobs/*.sh`、三个已跑 run 的 `params/{agent,env}.yaml` 与 checkpoint 内容、`.venv` 里 `rsl_rl` / `mjlab` 的相关实现。
- 本地 CPU 小实验（只读，无产物落库）：用 `pixi run python` 加载 `scenes/blackW/part2_off_high_platform_10cm.xml` 核对自由关节/执行器类型/几何/质量；用 `eval_blackw_part2.py --only high_platform_10cm --seconds 3` 实跑一次 judge（base z=0.582 的关键证据）。
- 未做（超出只读/算力边界）：真实 GPU 训练、20 关全量 judge、μ 探针重跑、部署 C++ 行为验证。

## 2. P0（会静默产生错误训练信号/错误结论）

### P0-1 blackW 全部任务丢失 domain randomization（6 个 DR event 被整体丢弃）

- **严重度**：P0
- **文件:行**：`@20261024_blackw/training/blackw/env_cfgs.py:199-226`，关键是 `:215` 的 `cfg.events = {` 整体赋值；对照基线 `~/rc_work/part2_team_race/src/alldog_mjlab/tasks/velocity/black/env_cfgs.py:284-410`。
- **问题**：基类 `_configure_events()` 建的是 `reset_base / reset_hip_joints / reset_thigh_joints / reset_calf_joints / foot_friction / payload_mass / base_com / pd_gains / encoder_bias / push_robot`（10 个，DR 开关全部 `enabled=True`）。blackW 的 `_override_events()` 用 **`cfg.events = {...}` 整字典替换**，只留下 `reset_base` 与 `reset_robot_joints` 两项 → 摩擦、负载、质心、PD 增益、编码器偏置、周期推力**全部消失**。注释只说要"加 gate 对齐的 spawn 随机化"，没有任何删除 DR 的意图。
- **证据**：
  - 代码：`env_cfgs.py:215-226` 整字典替换；基线 dict 见上引。
  - 实测（已跑 run 的真实训练配置，非推断）：
    ```bash
    ssh -o BatchMode=yes bis-ms7e56.tail4413b4.ts.net 'D=$(ls -dt ~/rc_work/part2_team_race/logs/rsl_rl/black_velocity/*ppo_st30_s100 | head -1); grep -n "^events:" -A 3 $D/params/env.yaml'
    ```
    输出里 `events:` 下只有 `reset_base` 与 `reset_robot_joints` 两个键。
  - 反向对照（说明不是"序列化丢字段"）：同一 run 的 `pose_range` 三个轴（hardmask run `:1216-1225` 显示 `x±0.10 / y±0.15 / yaw±0.05`）说明 spawn 随机化确实生效，被丢掉的只有 DR 那一组。
- **影响**：① 所有"训练配置含 DR"的叙述失效（`part2-ppo-training-history.md:99`"已有 DR（摩擦/负载/质心/编码器偏置/PD/推力）保持不变"、`:305`"稳健化训练必须把 spawn 随机化装进训练 reset"两条都默认 DR 在）；② `check_tier_success.py --no-dr` 与"去掉 `--no-dr` 的随机化 gate"（`part2-ppo-handoff-2026-10-26.md:279`）变成**同一条命令**，历史与将来的"with DR 成功率"其实是同一分布；③ 当前 8/8 稳健化目标里最直接的接触鲁棒性工具（摩擦/推力/负载 DR）在研究计划中"存在"、在代码中"不存在"。
- **建议修法**：改为就地补充而非替换 —— `cfg.events["reset_base"] = reset_base`、`cfg.events["reset_robot_joints"] = ...`，并把 `reset_{hip,thigh,calf}_joints` 三个分项删掉（或保留，二者等价）；在 `_apply_blackw_overrides()` 末尾加断言：训练模式（`not play`）下 `set(cfg.events)` 必须包含 `foot_friction/payload_mass/base_com/pd_gains/encoder_bias/push_robot`，除非显式 `BLACKW_NO_DR=1`（并把该标志写进 `params/env.yaml` 可查）。修完用上面那条 `grep -n "^events:"` 复验。

### P0-2 续训（full resume）静默覆盖学习率，`BLACKW_LR` 名不副实

- **严重度**：P0
- **文件:行**：远程 `src/alldog_mjlab/tasks/velocity/black/curriculum_checkpoint.py:259-272`（`load()` 覆盖，仅 `load_cfg is None` 时才读 `BLACKW_RESUME_LOAD_CFG`）；`rsl_rl/algorithms/ppo.py:389-391`（`if load_cfg.get("optimizer"): ... self.learning_rate = self.optimizer.param_groups[0]["lr"]`）；`@20261024_blackw/training/black/black_config.py:530-533`（`learning_rate` 默认 1e-3、`schedule="adaptive"`、`desired_kl=0.01`）。
- **问题**：所有 `ppo_*.sh` 都用 `--agent.resume True` 全量 resume（没有一个设 `BLACKW_RESUME_LOAD_CFG`），`mjlab/scripts/train.py:173` 调 `runner.load(str(path))` 不传 `load_cfg` → 默认加载 actor+critic+**optimizer**+iteration；`PPO.load` 随后把 `self.learning_rate` 改写成 checkpoint 里的 lr。job 里写的 `BLACKW_LR=4e-5` 只对新起 run 有效。
- **证据**：
  - `ppo_st30_s100` 的 `params/agent.yaml` 写 `learning_rate: 4.0e-05`；同一个 run 的 checkpoint 里实际值：
    ```bash
    ssh ... '.venv/bin/python -c "
    import torch,glob
    for p in [glob.glob(\"logs/rsl_rl/black_velocity/*ppo_st30_s100/model_300.pt\")[0],
              glob.glob(\"logs/rsl_rl/black_velocity/*ppo_st30_s100b/model_650.pt\")[0]]:
        d=torch.load(p,map_location=\"cpu\",weights_only=False)
        print(p, d[\"iter\"], d[\"optimizer_state_dict\"][\"param_groups\"][0][\"lr\"])"'
    ```
    输出：`model_300.pt 300 1.0000000000000003e-05`、`model_650.pt 650 1.0000000000000003e-05`（BC 起点 checkpoint 的 optimizer lr 是 5e-05，s075 从它继承）。
- **影响**：① 文档/归档里的"guarded lr 4e-5"（`part2-ppo-training-history.md:163,172`、handoff `:51`、所有 job 注释）与实际执行的 1e-5 差 4 倍，并受 `adaptive`（`desired_kl=0.01`，无上界）继续漂移 —— "小步长保住 BC"的结论实际是在另一个步长上得到的；② 计划中的 A6a（`BLACKW_RESUME_LOAD_CFG=actor` vs 全量 resume）**不是单变量对照**：actor-only 会同时把 lr 从 1e-5 抬回 4e-5、并把 Adam 一/二阶矩清零，结果无法归因到"critic/optimizer 继承"。
- **建议修法**：① 在 `BlackVelocityOnPolicyRunner.load()` 末尾打印并落盘 effective lr（`[resume] lr=<old>-><new>`），A/B 与文档一律引用它；② 显式选择语义：提供 `BLACKW_FORCE_LR=1`（load 后把 `self.learning_rate` 与 `optimizer.param_groups[*]["lr"]` 都改写成配置值），或在 `BLACKW_RESUME_LOAD_CFG=actor` 成为默认时同步说明"lr 用 CLI 值"；③ A6a 开跑前先把这条固化，否则该实验没有解释力。

### P0-3 `blackw-plum` 的 `plum_foothold` 仍是状态式每步奖励（可原地刷分）

- **严重度**：P0（仅 `blackw-plum` 任务，当前不在盲侧关键路径）
- **文件:行**：`@20261024_blackw/training/blackw/env_cfgs.py:297-326`（`_plum_foothold_reward`）、`:1126-1132`（默认 `BLACKW_PLUM_FOOT_W=3.0`）。
- **问题**：该项每一步返回 `frac(轮底在[0.14,0.34] m 的轮子比例) * 在场区内`，与"是否在推进/是否接近成功"无关；`part2_failure` 只在轮底 <0.05 时判负，所以"爬上桩顶站着不动"是零风险高收益策略：默认权重 3.0 × 1000 步（20 s episode）≈ 3000 量级，而成功一次性奖励只有 25（代码默认）/60（job 常用）。这与团队自己的硬规则（handoff `:218`"不要状态式 shaping"、归档 §11.2/§13）直接冲突，且与 `_course_progress_delta` / `part2_clear` 的抗刷分改造不一致。
- **证据**：代码（`in_field` 只看 x∈[3.75,11.15]、`on_pile` 只看轮底高度，均不含 root 位置/时间掩膜）；旁证：`part2-ppo-training-history.md:137` 记录 plum 在 15 个 checkpoint 上 0/60，与"停在桩上不会被终止"的形状一致（超时结束、success 恒 0）。
- **建议修法**：与 progress 同口径加 mask（只在 `root_x <= goal_x` 时计分，直接复用 `_course_progress_reward` 的写法），或改 potential 差分；短期至少把默认权重降到 0（`BLACKW_PLUM_FOOT_W=0`），先用 `part2_clear + competition_progress` 验证"能否走过去"。

## 3. P1（会浪费时间/误判，但不至于直接产出错误分数）

### P1-1 `cfg.sim.ccd_iterations = 0` 是死写；注释声称的"关闭 CCD"不存在

- **文件:行**：`env_cfgs.py:837`（exact）、`:985`（mixed official）、`:1096`（plum）。
- **问题**：mjlab 的 CCD 迭代数在 `sim.mujoco.ccd_iterations`（`mjlab/sim/sim.py:116` 定义、`:140` 写入 `model.opt.ccd_iterations`），`SimCfg` 上没有 `ccd_iterations` 字段 → 这三行只是给 dataclass 实例挂了一个不会被序列化/使用的属性。而 `_apply_deployment_sim_options()` 已经把 `sim.mujoco.ccd_iterations = 35`（`:801`）。
- **证据**：`ppo_st30_s100/params/env.yaml` 里 `sim.mujoco.ccd_iterations: 35`，且整份 yaml 没有 `sim.ccd_iterations`；对照 `mjlab/tasks/velocity/config/go1/env_cfgs.py:38` 的写法是 `cfg.sim.mujoco.ccd_iterations = 500`。
- **影响**：注释说"Wheel cylinders vs box edges hit a Mujoco-Warp CCD assert … so disable CCD"，实际没关（=35，与 judge 一致）。若那个 assert 真的会复现，保护并不存在；若不复现，注释是误导（会让人以为训练侧 CCD 与 judge 不同而被"解释"掉）。
- **建议修法**：若确实要关 → `cfg.sim.mujoco.ccd_iterations = 0`；若要与 judge 一致 → 删掉这三行与相应注释，并在 `_apply_deployment_sim_options()` 的 docstring 里写明 CCD=35 与 judge 同值。

### P1-2 `blackw-platform-exact` 的两个专用项在 10 cm 起点为死代码；"success-gated 升档"未实现

- **文件:行**：`env_cfgs.py:920-933`（`platform_height` weight 50 + `official_platform_success(min_root_z=0.72)` + `max_init_terrain_level=0`）、`:639-645`（`_platform_height_reward` 阈值 0.70）、`:658-677`（`_platform_top_success`）、`:1157-1178`（easy 变体，`min_root_z=0.71`）；`~/rc_work/.../black/env_cfgs.py:1003`（`cfg.curriculum.pop("terrain_levels")`）。
- **问题**：`black_competition_env_cfg` 在训练模式 pop 掉 `terrain_levels`，而 `blackw_platform_exact_env_cfg` 又把 `max_init_terrain_level` 钉成 0 → 整条 run 都在 10 cm 平台（row 0 = difficulty 0）。此时 root z ≈ 0.5+0.10 = 0.60：`official_platform_success` 要 ≥0.72（永不触发）、`_platform_height_reward` 的 `clamp(root_z-0.70)` 恒 0（50 权重白挂）。docstring 的"Pilot only 10 cm elevated platform first; increase later with the success-gated curriculum"没有任何实现（`terrain_levels` 被 pop，没有 success-gated 晋升 term）。
- **证据**：本地 CPU 实跑 `pixi run python @20261024_blackw/scripts/eval_blackw_part2.py --policy .../comp_bc_v5 --only high_platform_10cm --seconds 3 --attempts 2` → `SUCCESS (2/2) ... base=[2.325, 0.053, 0.582]`，即在 10 cm 平台上站住时 root z=0.582 < 0.70/0.72。
- **影响**：该任务的"防假成功"修复（`_platform_top_success`，注释里说的 70% 假成功问题）实际不生效，真正的成功判据只剩通用的 `part2_success`（这个是对的）；调参时看到 `platform_height` 恒 0 会误判"奖励没生效"。`blackw-platform-easy`（5–10 cm + `min_root_z=0.71`）更极端：阈值高于平台顶 6–21 cm，且该任务**根本没注册**（`training/blackw/__init__.py:70-83` 不含它，只有 HIM 变体存在）。
- **建议修法**：`min_root_z` 改成按难度算（`PART2_BASE_REF_Z + h + 0.02`，且 `_platform_top_success` 增加 `top_z` 参数）；`platform_height` 同理用相对高度；要么实现 success-gated 行晋升（`curriculum` term），要么把注释改成"固定 10 cm 平台"，并把 `blackw_platform_easy_env_cfg` 删掉或注册。

### P1-3 `check_tier_success.py --episodes 3` 永远跑不到 3 个 episode（文档推荐命令）

- **文件:行**：`@20261024_blackw/scripts/check_tier_success.py:101-102`（`max_steps = int(400/episodes)*episodes + 2000`）、`:115-133`（统计与输出）。
- **问题**：`episodes=3` → `max_steps = 133*3+2000 = 2399` 步；而 `episode_length_s=20`、`step_dt=0.002*10=0.02` → 每个 episode 1000 步，3 个 episode 需要 3000 步 → 循环必然在"per-env 只跑完 ≤2 个 episode"时退出。输出里没有任何 truncated 标记，`success_rate` 直接按已完成 episode 计算。
- **证据**：`episode_length_s: 20.0` 见 `ppo_st30_s100/params/env.yaml:1336`；公式见上；`--episodes 3` 的命令出现在 `part2-ppo-handoff-2026-10-26.md:279`、`part2-ppo-execution-plan-2026-10-26.md:291`。
- **影响**：文档口径的"128 env × 3 episodes"实际是 2 episodes（且不含未完成 episode），成功率是子样本；`--episodes 2` 恰好在 2000/2400 内、勉强安全，所以 job 脚本里的 `--episodes 2` 没出事，但换成 3（或 4）就静默降级。
- **建议修法**：`max_steps = episodes * env.unwrapped.max_episode_length + 200`（从 env 读，不猜）；输出加 `truncated: bool`、`episodes_per_env_min/max`；若未达 `--episodes` 就非零退出（或至少 `[WARN]` 到 stderr）。顺带修 `:115` 的 `episodes.clamp(min=1)`：完全没跑完 episode 的 env 会得到 rate=0，让 `worst_env_rate` 变 0（误导）。

### P1-4 训练 `lane_deviation`（0.90/0.80）与 judge/success 的车道（0.70）不一致

- **文件:行**：`env_cfgs.py:648-655`（默认 `max_abs_y=0.9`）、`:741`（mixed 0.9）、`:863`（official mixed 0.9）、`:934`（platform exact 0.80）、`:1001/:1101`（`BLACKW_LANE` 默认 0.90）；对照 success 谓词 `:456` 用 `PART2_LANE_HALF_WIDTH=0.7`（`:365`），judge 用 `lane_half_width=0.7`（levels JSON）。
- **问题**：训练在 0.7<|y|<0.9（platform exact 是 0.8）区间不终止，但 success 谓词与 judge 都要求 ≤0.7 → 这些 episode 在训练里"合法地跑到超时"，成功率被系统性拉低，且失败归因（lane vs 能力）变模糊。
- **证据**：以上行号；judge 侧 `eval_blackw_part2.py:141-142` + `part2_official_levels.json` 的 `"lane_half_width": 0.7`。
- **建议修法**：`_lane_deviation` 默认值改为 `PART2_LANE_HALF_WIDTH`（单一来源），需要更宽松时显式传参并打印。

### P1-5 judge（`eval_blackw_part2.py`）的 3 处 fail-open 默认值

- **文件:行**：`:174`（`end_x = self.j.get("descend_end_x", self.j["goal_x_min"])`）、`:311-316`（`wheel_bodies` 收集，未校验数量）、`:142`/`:248`（`lane_half_width`/`hold_s` 默认）。
- **问题**：
  1. `descend_end_x` 缺失时回退到 `goal_x_min` → stairs 判据从"四轮下到 6.3 m"静默退化成"过 3.7 m"（假成功）。当前 4 个 stairs 关都带该字段，属潜伏风险。
  2. `wheel_bodies` 只收集名字存在的 `<LEG>_foot`；若场景改名则列表变短甚至为空，而 `np.all(空数组)==True` → platform/slope/gap/plum 的"四轮在支撑带内"自动成立（**假成功**）。本机核对 `part2_off_high_platform_10cm.xml` 四个 body 都在，所以现在不会触发。
  3. `hold_s`/`lane_half_width` 缺失时静默用 0.2/0.7（与官方值一致，但不可见）。
- **证据**：本地 `mujoco` 检查四个 `<LEG>_foot` 存在；`np.all([])` 语义见 numpy 文档；`:170-171`/`:189-190`/`:226-227`/`:238-239` 都是 `np.all(...)` 直接当条件。
- **建议修法**：`__init__` 里断言 `len(self.wheel_bodies)==4` 且 `torch.jit` 输入维 = `57*history_len`；levels JSON 用显式键访问（或者加一份 schema 校验脚本）；`descend_end_x` 在 `kind=="stairs"` 时强制要求存在。

### P1-6 远程存在第二个口径完全不同的 judge，且没有弃用标记

- **文件:行**：远程 `scripts/agent_scripts/eval_blackw_official.py:110-171`（`OfficialJudge`）、`:61`（`load_env_cfg(task, play=True)`）。
- **问题**：这套判据与权威 judge 不是同一协议：平台 `x_range [1.95,3.20]`（权威 `[2.0,3.25]`）、stairs `goal_x 3.55` 且**不要求下台阶**（权威 goal 3.7 + descend_end 6.2 + clearance 0.10）、slope `goal_x 3.60`（权威 3.9）、wall `wall_x 2.5`（权威 1.86）、trench `near_x 3.5`（权威 3.8）、hold 0.20 s（权威 0.3 s）、全部只看 root 高度与 x（权威看四轮支撑带 + evidence + 槽内轮沉判负）。它还走 `play=True`（没有 `part2_*` term），自带另一套成功语义。
- **证据**：上述行号逐条对照 `part2_official_levels.json` 的 `judge` 块（`eval_blackw_part2.py` 用的就是它）。
- **影响**：这是一份会给出**更好看但不可比**数字的脚本，留在原目录里且文件名比权威 judge 更"官方"；任何新会话误用它都会污染 750/850 口径。
- **建议修法**：删除，或改名 `_deprecated_eval_blackw_official.py` 并在文件头写"数值不可与 judge v5 比较"，同时在 `scripts/agent_scripts/README`（若有）标注唯一权威入口。

### P1-7 `BLACKW_GUARD_*` 在漏设 `BLACKW_ALGORITHM` 时静默降级为普通 PPO

- **文件:行**：`@20261024_blackw/training/black/rl_cfg.py:39-41`（`"class_name": os.environ.get("BLACKW_ALGORITHM", "PPO")`）、`training/blackw/guarded_ppo.py:54-64`（6 个 guard env var 只在 GuardedPPO 构造时读）。
- **问题**：一个忘了 `BLACKW_ALGORITHM` 的 job 会安静地跑 vanilla PPO，`BLACKW_GUARD_BLEND/BASE_CKPT/FREEZE/LOG` 全部无效；只有事后翻 `params/agent.yaml` 的 `algorithm.class_name` 才能发现。
- **证据**：`ppo_audit_smoke2/ppo_st30_*` 的 `agent.yaml` 里 `class_name: ...guarded_ppo:GuardedPPO`（正常路径）；`rl_cfg.py:40` 的默认值是裸 `"PPO"`。
- **建议修法**：在 `black_ppo_algorithm_kwargs()` 里加 fail-loud：若 `os.environ` 里出现任一 `BLACKW_GUARD_*`（或 `BLACKW_RESUME_LOAD_CFG`）而 `class_name` 不以 `GuardedPPO` 结尾 → `raise ValueError`。附带修 `guarded_ppo.py:76-78` 的 `set_base_actor()`：注释说"重快照当前 actor"，实际是置空 `_guard_base`，下次 update 会**重新从 `BLACKW_GUARD_BASE_CKPT` 加载**（若设了）——语义与注释不符且目前无人调用，建议改名 `reset_guard_base()` 并写清语义。

### P1-8 `gate_stage.py` 的协议默认值与训练分布不匹配（外加一处死代码）

- **文件:行**：`@20261024_blackw/scripts/gate_stage.py:199-200`（`--cmd-jitter-y 0.2 / --cmd-jitter-wz 0.3` 默认）、`:123-148`（`run_level` 不传 `--seconds`）、`:104-112`（`level_command_tiers()` 无人调用）。
- **问题**：① gate 的指令抖动（vy±0.2、wz±0.3）是训练（`BLACKW_LATERAL_CMD=0.1`、`BLACKW_YAW_CMD=0.1`）的 2–3 倍 —— `part2-ppo-execution-plan-2026-10-26.md:32` 已经承认"strict gate 下 ±0.2/±0.3 对当前策略过严，需与用户确认"，但代码默认仍是 strict；② 每关时长沿用 levels JSON 的固定值，0.6× 慢档不延时 → 慢档更容易 timeout，gate 对慢档系统性偏严；③ `level_command_tiers()`（含 `VX_BOUNDS` clamp）是死代码，真正的 clamp 在 eval 的 `_build_command_tiers` 里，两处语义重复。
- **证据**：上述行号；`run_level` 的 cmd 列表里没有 `--seconds`。
- **建议修法**：cmd jitter 默认取训练值（或从 env 读，缺省失败）、慢档按 `1/scale` 放大 `--seconds`、删掉死函数并把 clamp 收到一处。

### P1-9 levels JSON 的 per-level 命令与文档 judge profile 不一致

- **文件:行**：`@20261024_blackw/ws/src/rl_sar_blackw/scenes/blackW/part2_official_levels.json`（20 关的 `"command": [0.5,0,0]`）、`gate_stage.py:74-82`（`CATEGORY_PROFILE`：platform 0.5 / wall 0.65→0.35 / slope 0.3 / stairs 0.75→0.45 / trench 0.3）、`eval_blackw_part2.py:607-611`（不吃 `--command` 时用 JSON 值）。
- **问题**：不加 `--command` 直接跑单关（README 与 handoff `:293` 的简写用法）时，slope 按 0.5 而不是 0.3、wall 按 0.5 而不是 0.65→0.35、stairs 按 0.5 而不是 0.75→0.45 跑 —— 与 gate/历史分数口径不同，分数不可比。
- **证据**：JSON 里 20 关的 command 全为 `[0.5, 0.0, 0.0]`；profile 见 `gate_stage.py:74-82` 与 handoff `:116`。
- **建议修法**：把 profile（含 `slow_from_x/cmd_slow`）写进 levels JSON，让 eval 与 gate 共用一个来源；或让 eval 默认读 `CATEGORY_PROFILE`。

### P1-10 job 脚本契约漏洞（远程 `~/rc_work/gpu_jobs/`）

- **文件:行**：`ppo_audit_smoke2.sh:27`（`exit 0`）；`ppo_st30_s075.sh:27-38`（写死 `model_100/200/300` 与 `[ -f "$RUNDIR/model_300.pt" ]`）；`common.sh:10,31-43`（`set -uo pipefail` 无 `-e`，`RC` 只在显式赋值时为真）。
- **问题**：
  1. `ppo_audit_smoke2.sh` 无论 smoke rc 都 `exit 0` → 失败在 `ts -i` / `on_finish` 里看起来是成功（本机 `sed -n '1,40p'` 可见 `RC=$?` 之后未使用）。
  2. `ppo_st30_s075.sh` 仍假设最后存档是 `model_300.pt`，实际该 run 只有 `model_299.pt`（已核对 run 目录）→ 阶段 A 的导出与 tiercheck 静默跳过（`part2-ppo-execution-plan-2026-10-26.md:193` 记过这次事故，但脚本没修）。
  3. `common.sh` 的 summary 末行永远是 `<job> done <time>`，与 `remote-training-workflow.md:11` 的契约（"失败时写 ABORT 或 rc=<非0>"）不符；`RC` 只有脚本显式赋值时才是真值。
  4. 早停仍未实现（`part2-ppo-execution-plan-2026-10-26.md:61` 的 TODO B）：没有"连续 2 个 100-iter judge 无提升即停"，job13 就是靠人事后判死的。
- **证据**：上述行号；`ls ~/rc_work/part2_team_race/logs/rsl_rl/black_velocity/*ppo_st30_s075/` 只有 `model_299.pt`。
- **建议修法**：`set -euo pipefail` 或每步 `|| { RC=$?; record "step failed"; exit $RC; }`；smoke 失败即 `exit $RC`；取真实最后存档 `ls -t "$RUNDIR"/model_*.pt | head -1`；summary 末行带 verdict（`done|aborted rc=N`）。注：导出 rc 不进最终 rc、`done` 行无条件写这两条与部署审计 §5.2 重复，此处不另计。

### P1-11 本轮修复本身缺一个"谓词 vs judge"的对拍自检

- **文件:行**：`env_cfgs.py:363-367`（judge 常量在训练侧硬编码一份）、`eval_blackw_part2.py:54-71`（judge 侧硬编码另一份）。
- **问题**：两套常量（wheel radius、surface tol、wall_x、back clearance、ground tol、descend clearance、hold steps、lane）各自硬编码；本次审计逐条对照"全部一致"，但没有任何自动检查 —— 下一次任一侧改一个常数（或 levels JSON 改一档几何）就会重新静默分叉，这正是 §11.1/§16.1 两次事故的根因。
- **证据**：本次逐条对照结果见附录 A.2（20 关 judge 元数据 vs `_part2_terrain_state` 常量）。
- **建议修法**：在 `check_tier_success.py`（或独立 `check_predicate_parity.py`）里加一个纯 CPU 的"常量对拍"：从 levels JSON 读出 20 关的几何/hold/lane，与 `env_cfgs` 的公式逐项比较（`assert` 到 1e-6），进 job 的 smoke 步骤；这样 judge 侧改档位会立刻在训练侧报错。

### P1-12 训练 reset 的 root 速度随机化与 judge 静止出生不一致（文档声称"一致"）

- **文件:行**：`env_cfgs.py:202-214`（保留 `reset_base` 的原 `params`，即 `velocity_range` 六轴 ±0.5）；`black/black_config.py:229-238`（`root_velocity` ±0.5）；judge 侧 `run_attempt` 的 `reset_pose` 只写姿态、`qvel[:]=0`（`eval_blackw_part2.py:319-336`）；gate 协议只随机位姿（`gate_stage.py:192-196`）。
- **问题**：训练 reset 让 root 带 ±0.5 m/s / ±0.5 rad/s 初速度，judge 永远静止出生；handoff `:114` 写"关节 offset/速度与现有 reset 随机化一致"，但 gate 并不随机速度，`check_tier_success --exact-spawn` 又会把速度清零 → "训练 reset = gate reset = judge reset" 只在位姿维度成立。
- **证据**：三个 run 的 `params/env.yaml` 的 `reset_base.params.velocity_range` 均为 ±0.5。
- **建议修法**：要么把 judge/gate 的出生速度也随机（需要 levels JSON 支持，且要重新取证），要么在训练侧增加 `BLACKW_RESET_VEL=0` 开关并在 gate 文档里明确"速度维度不覆盖"。

## 4. P2（文档-代码/默认值对齐）

- **P2-1**：`black/black_config.py:629` `command_curriculum_restore: ... = "range"`，而 `black/rl_cfg.py:69-77` 的 docstring 写"auto（默认）：同 stage resume -> full"。实际默认永远不是 `auto`，"同 stage 精确续训"不是默认行为（`curriculum_checkpoint.resolve_restore_mode` 的表格也没写这个默认）。
- **P2-2**：远程 `curriculum_checkpoint.py:89-93` 的 docstring 表格写"source stage 未知 → range（保守：范围保留）"，代码 `if source_stage is None: return "none"`（丢弃已恢复的 vx range）。注释与实现相反，且方向上更危险。
- **P2-3**：`curriculum_checkpoint.py:267-272`：`BLACKW_RESUME_LOAD_CFG` 只在 `load_cfg is None` 时生效；任何显式传 `load_cfg` 的调用者（`export_blackw_policy.py:103`、`check_tier_success.py:82` 都传 `{"actor": True}`）会静默忽略该变量。建议改成"显式 load_cfg 优先但打印 WARN"，并在 docstring 写明优先级。
- **P2-4**：`eval_blackw_part2.py` 的 `wheel_states()`（`:398-402`）用 `<LEG>_foot` body 原点当轮心，而轮子 cyl geom 在 body 系 `x=+0.028`（本机 `part2_off_high_platform_10cm.xml` 实测）→ 所有 wheel_x 判据有 2.8 cm 前向偏置。训练谓词用同一约定，所以 train/judge 一致、不会误判，但绝对阈值（trench 槽边 ±0.06、stairs/wall clearance）对应的实际接触点比标称偏 2.8 cm。
- **P2-5**：`env_cfgs.py:367` 的 `BLACKW_SUCCESS_HOLD_STEPS` 允许把训练 hold 改成任意值；handoff `:55` 把它当旋钮记录。一旦被设成非 15，训练谓词与 judge 的 0.3 s hold 静默脱钩，且没有任何日志。
- **P2-6**：`black/black_config.py:514` `initial_std` 默认 **1.0**，而 docs 通篇说 σ=0.1–0.3。当前 guarded 路线从 BC checkpoint 继承 `distribution.std_param=0.1`（已核对 `model_300/650` 的 `actor_state_dict`，`actor` 以 `strict=True` 加载），所以不受影响；但从零 PPO 或 std 键缺失时会用 1.0（leg 0.25 rad / wheel 10 rad/s 的探索噪声）。
- **P2-7**：`env_cfgs.py:896-901/1065/1148-1151` 的 `BLACKW_CLEAR_W` 默认 **25**，而 handoff `:54`、所有 job 与归档都用 **60**。文档里的"默认值"和代码默认值不同。
- **P2-8**：`eval_blackw_part2.py` 的 `total_score`（`:668-672`）在 `--only` 子集下只统计子集（实测 `total_score=10`），字段名有歧义；`_build_command_tiers`（`:531-540`）的显式三元组形式（`"0.3,0,0;..."`）**不**平移 `cmd_slow`，与 docstring"慢段同比例缩放"只对 scale 形式成立。
- **P2-9**：`check_tier_success.py:55-68` 的 `--exact-spawn` 只清 `pose_range/position_range/velocity_range` 三类键（黑名单写法）；将来 reset event 新增参数（如 `yaw_range`）会静默漏掉，让"exact spawn"名不副实。
- **P2-10**：`eval_blackw_part2.py:13-15` 的 docstring、handoff `:114` 写"部署 MJCF 2 ms 物理"，而 `policy/blackW/base.yaml:2-3` 是 `dt: 0.005 / decimation: 4`。部署审计 §2 已澄清两端策略周期都是 50 Hz、PD 都是 500 Hz（`sim_node` 按 MuJoCo 2 ms 步长算 PD），**行为无差异**；这里只记录"eval 完全忽略 `config.yaml` 的 dt/decimation（写死 0.002/0.02）"这一维护性缺口 —— 若将来出现 0.005 物理的策略，judge 会静默用 0.002 评它。
- **P2-11**：`diag_rollout.py:34` 用基类 `MjlabOnPolicyRunner`（而非任务注册的 runner），`:30-31` 把 `max_init_terrain_level` 钉 0；在没设 `BLACKW_DIFF_MIN/MAX` 时它滚的是难度 0 的关，容易与"训练难度"混淆（`get_term` 直取、缺项会 KeyError，这点是好的）。
- **P2-12**：exec-plan `:230` 写 `--joint-offset-range/--joint-vel-range`，实际参数是 `--joint-offset/--joint-vel`（`eval_blackw_part2.py:562-565`）—— 照文档敲会直接报错（可控，但属描述错位）。

## 5. 已核实正确 / 已修好的项（避免重复发现）

1. **快照一致性**：本地 `@20261024_blackw/training/{blackw,black}/*.py` 与远程 `src/alldog_mjlab/tasks/velocity/{blackw,black}/` **逐字节相同**（`diff -q` 全绿），"快照即真值"成立。
2. **训练谓词 vs 权威 judge 逐条对齐**（`env_cfgs.py:396-542` ↔ `part2_official_levels.json` 的 `judge` 块）：platform `top=0.10+0.30d`、`x∈[2.0,3.25]`；stairs `top=0.60+1.20d`、`goal 3.7`、`descend_end 6.2`、clearance `0.10`、下坡后 `wheel_z∈[-0.06,0.20]`；slope `rise=2·tan(20+25d)`、`goal 3.9`；wall `wall_x 1.86`、`goal 2.27`、`climb_z 0.5+0.2h`、back clearance `0.16`、ground tol `0.08`；trench `near 3.8`、`far=3.8+w`、`plateau 0.3`、允许下沉 `min(0.15,0.103)`；plum field `[3.75,11.15]`、drop `<0.05`、`top 0.2`、`goal 11.55`。**没有一个常数分叉**。
3. **训练地形几何自洽**：`exact_terrain.py` 的实心楔形坡（rise=2·tanθ）与槽几何（槽实为 rel `[3.8, 3.8+w]`）与上述公式一致；`_ramp()` 已修掉"薄板 2 cm 台阶 + y 偏移"两个老 bug。
4. **hold 语义**：judge `held >= hold_s(0.2)+0.1 = 0.3 s @50 Hz = 15 步` == `PART2_HOLD_STEPS=15`；`episode_length_buf` 在 `step()` 里先 `+1` 再算 termination（mjlab `manager_based_rl_env.py:446-456`），所以 `<=1` 的复位只在 episode 第 1 步生效，**没有 off-by-one**。
5. **`part2_clear` 只付一次**：mjlab `step()` 里 termination 先算、reward 后算、reset 最后（同上），两者共用 `common_step_counter` 缓存（`env_cfgs.py:426-429` 与 `:549-552`），streak==15 与 `>=15` 同步成立 → 一次性 +60 不会重复也不会漏。
6. **resume 语义正确**（与部署审计结论一致）：`rsl_rl/runners/on_policy_runner.py:77-78` 是 `total_it = start_it + num_learning_iterations` → `--agent.max-iterations 400` 就是"新增 400"；实测 s100 = `model_300..698`（399 次学习迭代 + 末次保存）、s100b = `650..1449`。`mjlab/scripts/train.py:173` 调 `runner.load(path)` 不传 `load_cfg`，所以 `BLACKW_RESUME_LOAD_CFG` 在训练路径上**确实生效**（但见 P0-2 / P2-3）。
7. **观测/动作契约**：actor 57×6 的 term 顺序、wheel 位置置零、`last_action` 为 raw action、右轮 `action_scale=-10`、kp/kd=50/1.2/1.0、torque limits、policy 关节序 FL/FR/RL/RR、MJCF actuator 为 general(gain 1,bias 0)=纯力矩、free joint 在 `qpos[0:7]` —— 本机逐项核对通过（`comp_bc_v5/config.yaml` 与训练 `_wheel_leg_scale` 一致）。
8. **342 布局与导出置换自洽**：mjlab 原生历史是"term-major、oldest→newest"（`CircularBuffer.buffer` 文档 + 每 term `reshape` 后 concat，`observation_manager.py:372-382`），`export_blackw_policy.py:51-67` 的置换假设正确，eval 的 `hist[::-1]`（frame-major newest→oldest）与置换后的权重配套 —— 这条链**没有**静默错位。
9. **已修项复核**：`_part2_success/_part2_clear_reward` 只保留一份 hold 版（`env_cfgs.py:579-586`，注释也留了禁止再定义）；`check_tier_success.py:87-93` 的 `part2_success` fail-closed 断言在；`guarded_ppo` 的 `BLACKW_GUARD_BASE_CKPT` 实现可加载并打印 sha（job19 的 `agent.yaml`/日志）。

## 6. 未覆盖 / 移交给另一审计员

- 部署栈真值（`sim_node` PD/力矩限幅、`joint_mapping`、`observations_history` 实测顺序、`fixed_kp 80/3` vs `rl_kp 50/1.2` 谁生效、`config.yaml` 顶层 key 与目录名不符）→ [`ppo-deploy-audit-round1.md`](ppo-deploy-audit-round1.md)（含导出器不产 config.yaml、`contract.json` 右轮符号写反两条，本文不重复计分，但训练侧确认：`env_cfgs.py:68-77` 与 `comp_bc_v5/config.yaml` 都是 FR/RR=-10）。
- HIM 线（`him*.py`、HIM runner、`blackw-platform-exact-him`）未审。
- 未做实测：20 关全量 judge、真实 GPU 训练、μ=1.2/1.5 探针复跑。

## 7. VERDICT

**`BLOCKED`**

阻塞项（按修复顺序）：

1. **P0-1** 全部 blackW 任务丢失 domain randomization（`env_cfgs.py:215`）—— 与文档相反，且让"随机化 gate"失去意义。
2. **P0-2** 续训静默继承 optimizer 的 lr（实际 1e-5 vs 名义 4e-5），并使计划的 A6a A/B 不是单变量。
3. **P0-3** `blackw-plum` 的 `plum_foothold` 状态式奖励可原地刷分。

其余 P1（1–12）都不阻塞"继续做更高层优化"，但建议在下一批训练前至少先修 **P1-1（CCD 死写）、P1-2（platform 死项/假课程）、P1-3（tiercheck episode 数）、P1-5（judge fail-open 三处）、P1-10（job 出口契约）**：这五条都会让"看起来跑通了"的实验结果不可用。

修复顺序建议：P0-1 → P0-2 → P1-1/P1-2/P1-3 → P0-3（plum 不在关键路径，可与深度线一起排）→ P1-10/P1-5/P1-11（对拍自检）→ 其余 P2。

## 附录 A：本报告用到的复现命令（全部只读）

```bash
# 1) 本地快照 == 远程训练仓（应无输出；只读 scp 到临时目录比对）
cd /home/bis/BiS.d/Code.d/RoboCon/MyMonoRepo.d
T=$(mktemp -d)
for f in env_cfgs.py exact_terrain.py guarded_ppo.py __init__.py; do
  timeout 120 scp -q -o BatchMode=yes bis-ms7e56.tail4413b4.ts.net:"~/rc_work/part2_team_race/src/alldog_mjlab/tasks/velocity/blackw/$f" "$T/$f"
  diff -q "@20261024_blackw/training/blackw/$f" "$T/$f" || echo "DIFF: $f"
done

# 2) DR 是否在真实训练配置里（只看 events 下的键）
ssh -o BatchMode=yes bis-ms7e56.tail4413b4.ts.net \
 'D=$(ls -dt ~/rc_work/part2_team_race/logs/rsl_rl/black_velocity/*ppo_st30_s100 | head -1); grep -n "^events:" -A 3 $D/params/env.yaml'

# 3) resume 的实际学习率（对比 params/agent.yaml 里的 learning_rate: 4.0e-05）
ssh -o BatchMode=yes bis-ms7e56.tail4413b4.ts.net \
 'cd ~/rc_work/part2_team_race && .venv/bin/python -c "
import torch,glob
paths=[glob.glob(\"logs/rsl_rl/black_velocity/*ppo_st30_s100/model_300.pt\")[0],
       glob.glob(\"logs/rsl_rl/black_velocity/*ppo_st30_s100b/model_650.pt\")[0]]
for p in paths:
    d=torch.load(p,map_location=\"cpu\",weights_only=False)
    print(p, d[\"iter\"], d[\"optimizer_state_dict\"][\"param_groups\"][0][\"lr\"],
          float(d[\"actor_state_dict\"][\"distribution.std_param\"][0]))"'
# -> model_300.pt 300 1.0000000000000003e-05 0.1
# -> model_650.pt 650 1.0000000000000003e-05 0.1

# 4) CCD 字段的真实位置（mjlab 侧）
ssh -o BatchMode=yes bis-ms7e56.tail4413b4.ts.net \
 'grep -n "ccd_iterations" /home/bis/rc_work/nwwolf_mjlab_training_release/.venv/lib/python3.12/site-packages/mjlab/sim/sim.py'

# 5) 10 cm 平台上站住时的 root 高度（< 0.70/0.72 阈值）
pixi run python @20261024_blackw/scripts/eval_blackw_part2.py \
  --policy @20261024_blackw/ws/src/rl_sar_blackw/policy/blackW/comp_bc_v5 \
  --only high_platform_10cm --seconds 3 --attempts 2

# 6) tiercheck 的 max_steps（episodes=3 时 2399 < 3*1000）
pixi run python -c "e=3; print(int(400/e)*e+2000, 3*int(20/0.02))"

# 7) 官方场景的关节/执行器/轮几何（自由关节在前、general 力矩执行器、轮半径 0.103、geom 前移 0.028）
pixi run python -c "
import mujoco
m=mujoco.MjModel.from_xml_path('@20261024_blackw/ws/src/rl_sar_blackw/scenes/blackW/part2_off_high_platform_10cm.xml')
print(m.nq,m.nv,m.nu,m.jnt_type[0],set(int(t) for t in m.actuator_trntype),
      [mujoco.mj_id2name(m,mujoco.mjtObj.mjOBJ_BODY,i) for i in range(m.nbody) if '_foot' in (mujoco.mj_id2name(m,mujoco.mjtObj.mjOBJ_BODY,i) or '')])"
```
