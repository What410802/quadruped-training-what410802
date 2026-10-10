#!/usr/bin/env python3
"""参考实现：不经 ROS、按**仿真时间锁步**跑 best.pt，给 rl_sar 移植版当对照基准。

它和 rl_sar 读同一份配置（ws/src/rl_sar/policy/black/{base.yaml,himloco/config.yaml}）、
跑同一个场景（@20261005_ros2/scenes/flat_scene.xml，即仿真节点默认加载的那份），
但观测 / 动作的拼法是**按大作业说明独立写的**——两边对得上，才说明 rl_sar 那边没拼错。

与 ROS 链路相比它多了一样东西：**真值**（基座速度、位置都直接读 mjData），所以能量化
"走得怎么样"；再用 --period-ms / --delay-ms 把 rl_sar 墙钟线程带来的时序误差注入进来，
就能单独看"时钟"这一项的影响（docs/experiments.md）。

物理与电机：仿真步长 2 ms，每步按 MIT 公式算力矩（tau = kp·(q_des − q) − kd·dq，再限幅），
与 @20261005_ros2 的仿真节点同一个式子；--tau-max 同时改写模型的 ctrlrange（否则 MuJoCo
会在 ±20 N·m 再截一次）。

用法（仓库根目录）：

    pixi run python @20261007_assignment/scripts/agent_scripts/policy_reference.py --cmd 0.5,0,0
    pixi run python @20261007_assignment/scripts/agent_scripts/policy_reference.py --cmd 0.5,0,0 --tau-max 20
    pixi run python @20261007_assignment/scripts/agent_scripts/policy_reference.py --cmd 0.5,0,0 \\
        --period-ms 20.6 --period-jitter-ms 0.6 --delay-ms 5
    pixi run python @20261007_assignment/scripts/agent_scripts/policy_reference.py --cmd 1.0,0,0 \
        --pause-at 3 --pause-seconds 2

时钟：循环里另记一个"墙钟" wall（每圈 +2 ms），策略按 wall 排程——不暂停时 wall 与仿真时间同步走，
等价于锁步；--pause-at 时物理不步进、wall 照走，就是 rl_sar 墙钟线程遇到"仿真暂停"的样子。
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import mujoco
import numpy as np
import torch
import yaml

TASK = Path(__file__).resolve().parents[2]  # @20261007_assignment/
REPO = TASK.parent
POLICY_DIR = TASK / "ws/src/rl_sar/policy/black"
DEFAULT_SCENE = REPO / "@20261005_ros2/scenes/flat_scene.xml"


def quat_rotate_inverse(q_wxyz: np.ndarray, v: np.ndarray) -> np.ndarray:
    """把世界系向量 v 转到机体系（q 是机体在世界系的姿态，w x y z）。"""
    w, xyz = q_wxyz[0], q_wxyz[1:]
    return v * (2.0 * w * w - 1.0) - np.cross(xyz, v) * w * 2.0 + xyz * np.dot(xyz, v) * 2.0


def tilt_deg(q_wxyz: np.ndarray) -> float:
    """机体 z 轴与世界 z 轴的夹角。"""
    g = quat_rotate_inverse(q_wxyz, np.array([0.0, 0.0, -1.0]))
    return math.degrees(math.acos(max(-1.0, min(1.0, -g[2]))))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--scene", type=Path, default=DEFAULT_SCENE)
    ap.add_argument("--cmd", default="0.5,0,0", help="vx,vy,wz（m/s、m/s、rad/s），站稳后施加")
    ap.add_argument("--settle", type=float, default=1.5, help="先用固定 PD 站多久 [s]")
    ap.add_argument("--warmup", type=float, default=2.0, help="进 RL 后先给零指令多久 [s]")
    ap.add_argument("--seconds", type=float, default=10.0, help="施加指令的时长 [s]")
    ap.add_argument("--window", type=float, default=5.0, help="统计用最后多少秒 [s]")
    ap.add_argument("--tau-max", type=float, default=33.5, help="电机力矩上限，同时改写 ctrlrange [N·m]")
    ap.add_argument("--period-ms", type=float, default=20.0, help="策略周期均值 [ms]（锁步 = 20）")
    ap.add_argument("--period-jitter-ms", type=float, default=0.0, help="策略周期均匀抖动 ±[ms]")
    ap.add_argument("--delay-ms", type=float, default=0.0, help="推理出的目标晚多久才生效 [ms]")
    ap.add_argument("--pause-at", type=float, default=None,
                    help="指令开始后多少秒把物理冻住（模拟在仿真窗口里按暂停；策略照墙钟继续推理）[s]")
    ap.add_argument("--pause-seconds", type=float, default=0.0, help="冻住多久 [s]")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    base = yaml.safe_load((POLICY_DIR / "base.yaml").read_text())["black"]
    cfg = yaml.safe_load((POLICY_DIR / "himloco/config.yaml").read_text())["black/himloco"]
    policy = torch.jit.load(str(POLICY_DIR / "himloco" / cfg["model_name"]))
    policy.eval()

    n = cfg["num_of_dofs"]
    mapping = cfg["joint_mapping"]  # 策略下标 → 仿真执行器下标
    default = np.array(cfg["default_dof_pos"])
    action_scale = np.array(cfg["action_scale"])
    rl_kp, rl_kd = np.array(cfg["rl_kp"]), np.array(cfg["rl_kd"])
    fixed_kp, fixed_kd = np.array(base["fixed_kp"]), np.array(base["fixed_kd"])
    cmd_scale = np.array(cfg["commands_scale"])
    history_len = len(cfg["observations_history"])
    num_obs = cfg["num_observations"]
    clip_obs = cfg["clip_obs"]
    clip_lo, clip_hi = np.array(cfg["clip_actions_lower"]), np.array(cfg["clip_actions_upper"])

    m = mujoco.MjModel.from_xml_path(str(args.scene))
    d = mujoco.MjData(m)
    m.actuator_ctrlrange[:] = [-args.tau_max, args.tau_max]
    dt = m.opt.timestep
    # 策略关节 i → 执行器 mapping[i] → 关节 qpos / qvel 地址
    jnt = [m.actuator_trnid[mapping[i], 0] for i in range(n)]
    qadr = np.array([m.jnt_qposadr[j] for j in jnt])
    vadr = np.array([m.jnt_dofadr[j] for j in jnt])
    act = np.array(mapping)
    quat_adr = m.sensor_adr[m.sensor("imu_quat").id]
    gyro_adr = m.sensor_adr[m.sensor("imu_gyro").id]

    rng = np.random.default_rng(args.seed)
    cmd = np.array([float(x) for x in args.cmd.split(",")])

    # 初始：关节摆到站姿、基座抬高一点，让它落下去由固定 PD 接住
    mujoco.mj_resetData(m, d)
    d.qpos[2] = 0.45
    d.qpos[qadr] = default
    mujoco.mj_forward(m, d)

    q_des = default.copy()
    kp, kd = fixed_kp, fixed_kd
    actions = np.zeros(n)
    hist = np.zeros((history_len, num_obs))  # hist[0] = 最新一帧
    pending: list[tuple[float, np.ndarray]] = []  # (生效时刻, q_des)
    t_rl = args.settle
    t_cmd = args.settle + args.warmup
    t_end = t_cmd + args.seconds
    next_policy = t_rl
    wall = 0.0
    pause = None
    if args.pause_at is not None:
        pause = (t_cmd + args.pause_at, t_cmd + args.pause_at + args.pause_seconds)
        t_end += args.pause_seconds

    rows = []  # (t, vx, vy, wz, z, tilt, |tau|max, n_over_20)
    fell = None
    while wall < t_end:
        t = wall
        frozen = pause is not None and pause[0] <= wall < pause[1]
        if t >= t_rl and t + 1e-9 >= next_policy:
            kp, kd = rl_kp, rl_kd
            q = d.qpos[qadr]
            dq = d.qvel[vadr]
            quat = d.sensordata[quat_adr:quat_adr + 4]
            gyro = d.sensordata[gyro_adr:gyro_adr + 3]
            c = cmd if t >= t_cmd else np.zeros(3)
            obs = np.concatenate([
                c * cmd_scale,
                gyro * cfg["ang_vel_scale"],
                quat_rotate_inverse(quat, np.array([0.0, 0.0, -1.0])),
                (q - default) * cfg["dof_pos_scale"],
                dq * cfg["dof_vel_scale"],
                actions,
            ])
            obs = np.clip(obs, -clip_obs, clip_obs)
            hist = np.roll(hist, 1, axis=0)
            hist[0] = obs
            with torch.no_grad():
                out = policy(torch.tensor(hist.reshape(1, -1), dtype=torch.float32)).numpy()[0]
            actions = np.clip(out.astype(np.float64), clip_lo, clip_hi)
            pending.append((t + args.delay_ms * 1e-3, default + actions * action_scale))
            period = args.period_ms + (rng.uniform(-1, 1) * args.period_jitter_ms if args.period_jitter_ms else 0)
            next_policy += period * 1e-3
        while pending and pending[0][0] <= t + 1e-9:
            q_des = pending.pop(0)[1]

        q = d.qpos[qadr]
        dq = d.qvel[vadr]
        tau = np.clip(kp * (q_des - q) - kd * dq, -args.tau_max, args.tau_max)
        d.ctrl[act] = tau
        wall += dt
        if frozen:
            continue
        mujoco.mj_step(m, d)

        quat = d.qpos[3:7]
        v_body = quat_rotate_inverse(quat, d.qvel[0:3])
        raw = kp * (q_des - d.qpos[qadr]) - kd * d.qvel[vadr]
        rows.append((d.time, v_body[0], v_body[1], d.qvel[5], d.qpos[2], tilt_deg(quat),
                     np.abs(raw).max(), int((np.abs(raw) > 20.0).sum())))
        if fell is None and (d.qpos[2] < 0.2 or rows[-1][5] > 60.0):
            fell = d.time

    a = np.array(rows)
    w = a[a[:, 0] >= a[-1, 0] - args.window]  # 按仿真时间取最后 window 秒（暂停过的话仿真时间比墙钟短）
    walk = a[a[:, 0] >= t_cmd]
    pause_txt = f" pause={args.pause_seconds}s@+{args.pause_at}s" if pause else ""
    print(f"cmd={args.cmd} tau_max={args.tau_max} period={args.period_ms}±{args.period_jitter_ms}ms "
          f"delay={args.delay_ms}ms{pause_txt} seed={args.seed}")
    print(f"  last {args.window:.0f}s: vx={w[:, 1].mean():.3f} vy={w[:, 2].mean():.3f} wz={w[:, 3].mean():.3f} "
          f"z={w[:, 4].mean():.3f} (min {w[:, 4].min():.3f}) tilt max={w[:, 5].max():.1f}deg")
    print(f"  walking: |tau| peak={walk[:, 6].max():.1f} N·m, steps with any |tau|>20: "
          f"{100.0 * (walk[:, 7] > 0).mean():.1f}%  fell={'no' if fell is None else f'at t={fell:.2f}s'}")
    return 0 if fell is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
