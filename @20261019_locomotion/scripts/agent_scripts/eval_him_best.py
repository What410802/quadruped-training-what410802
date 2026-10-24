#!/usr/bin/env python3
"""Zero-shot evaluation of the assignment HIMLoco ``best.pt`` on Part 1 / Part 2.

The assignment policy is *not* the same observation/action contract as the local
45-D single-frame mjlab actor:

- input is ``[B, 270]`` = 6 frames x 45, the newest frame first;
- the 45-D frame is commands / ang_vel / gravity / dof_pos / dof_vel / actions with
  the assignment's own scales (see ``config.yaml``);
- output is a 12-D unscaled action clipped to +/-100, then
  ``q_target = default_dof_pos + action_scale * action``; PD gains are ``rl_kp`` /
  ``rl_kd`` (40 / 1.2) and the torque envelope is ``torque_limits`` (33.5 N.m).

This script reuses the local Part 1 V2 judge runner and the Part 2 level runner by
swapping in a scene runner that keeps the 6-frame history and applies the assignment
clipping/gains.  Everything else (scene, judge, sampling cadence) is unchanged, so
the results are directly comparable with the flat-ft diagnostics.

Usage (from MyMonoRepo.d):

    pixi run python @20261019_locomotion/scripts/agent_scripts/eval_him_best.py --part all
    pixi run python @20261019_locomotion/scripts/agent_scripts/eval_him_best.py --part part1 --tasks slalom --tasks slope
    pixi run python @20261019_locomotion/scripts/agent_scripts/eval_him_best.py --part part2 --only high_platform --only trench

Outputs go to ``../prep.d/results/`` (outside the repo) plus a Markdown summary;
the JSON payloads keep the upstream judge schema and add the policy contract.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import mujoco
import numpy as np
import torch
import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
POLICY_DIR = REPO_ROOT / "@20261007_assignment/ws/src/rl_sar/policy/black"
BEST_PT = POLICY_DIR / "himloco/best.pt"
POLICY_CFG = POLICY_DIR / "himloco/config.yaml"

sys.path.insert(0, str(SCRIPT_DIR))

import run_part1_judged_rollout_v2 as p1mod  # noqa: E402
import run_part2_judged_eval as p2mod  # noqa: E402
from run_policy_scene import ScenePolicyRunner  # noqa: E402

WARMUP_S = 1.0


def file_hashes(path: Path) -> dict[str, str]:
    return {
        "md5": hashlib.md5(path.read_bytes()).hexdigest(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": str(path.stat().st_size),
    }


def load_cfg() -> dict:
    return yaml.safe_load(POLICY_CFG.read_text())["black/himloco"]


class HimBestRunner(ScenePolicyRunner):
    """Single-env scene runner with the HIMLoco 6-frame observation contract."""

    def __init__(self, scene: str, policy_path: str, start: tuple[float, float, float, float]) -> None:
        super().__init__(scene, policy_path, start)
        cfg = load_cfg()
        self.cfg = cfg
        self.history_len = len(cfg["observations_history"])
        self.num_obs = int(cfg["num_observations"])
        self.obs_clip = float(cfg["clip_obs"])
        self.cmd_scale = np.array(cfg["commands_scale"], dtype=np.float64)
        self.ang_vel_scale = float(cfg["ang_vel_scale"])
        self.dof_pos_scale = float(cfg["dof_pos_scale"])
        self.dof_vel_scale = float(cfg["dof_vel_scale"])
        self.action_scale = np.array(cfg["action_scale"], dtype=np.float64)
        self.clip_lo = np.array(cfg["clip_actions_lower"], dtype=np.float64)
        self.clip_hi = np.array(cfg["clip_actions_upper"], dtype=np.float64)
        self.kp = np.array(cfg["rl_kp"], dtype=np.float64)
        self.kd = np.array(cfg["rl_kd"], dtype=np.float64)
        self.tau_max = float(cfg["torque_limits"][0])
        # The policy is evaluated under its own trained torque envelope, not the
        # local mjlab scene's 20 N.m ctrlrange (same choice as policy_reference.py).
        self.model.actuator_ctrlrange[:] = [-self.tau_max, self.tau_max]
        self.history = np.zeros((self.history_len, self.num_obs), dtype=np.float64)

    def obs(self, command: np.ndarray) -> np.ndarray:
        """Build one 45-D frame, push it into the history, return the 270-D input."""
        gyro = np.array(self.data.sensor("imu_ang_vel").data, dtype=np.float64)
        quat = np.array(self.data.qpos[3:7], dtype=np.float64)
        w, x, y, z = quat
        R = np.array([
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ])
        gravity = R.T @ np.array([0.0, 0.0, -1.0])
        q_rel = np.array(self.data.qpos[self.qpos_adr]) - self.q_default
        qvel = np.array(self.data.qvel[self.qvel_adr])
        frame = np.concatenate([
            command * self.cmd_scale,
            gyro * self.ang_vel_scale,
            gravity,
            q_rel * self.dof_pos_scale,
            qvel * self.dof_vel_scale,
            self.last_action,
        ])
        frame = np.clip(frame, -self.obs_clip, self.obs_clip)
        self.history = np.roll(self.history, 1, axis=0)
        self.history[0] = frame
        return self.history.reshape(-1)

    def policy_action(self, command: np.ndarray) -> np.ndarray:
        """One inference: history -> 12-D action clipped to the assignment bounds."""
        obs = torch.from_numpy(self.obs(command)).unsqueeze(0).to(torch.float32)
        with torch.no_grad():
            raw = self.policy(obs).numpy().reshape(-1).astype(np.float64)
        action = np.clip(raw, self.clip_lo, self.clip_hi)
        self.last_action[:] = action
        return action

    def drive(self, action: np.ndarray) -> None:
        """PD torque command for one policy step (4 x 5 ms physics substeps)."""
        q_target = self.q_default + self.action_scale * action
        q = np.array(self.data.qpos[self.qpos_adr])
        qd = np.array(self.data.qvel[self.qvel_adr])
        tau = np.clip(self.kp * (q_target - q) - self.kd * qd, -self.tau_max, self.tau_max)
        self.data.ctrl[self.motor_ids] = tau


class HimBestPart1Runner(p1mod.V2Runner):
    """V2 judge runner driven by the HIMLoco policy step."""

    def _policy_step(self, command: np.ndarray) -> None:
        action = self.runner.policy_action(command)
        self.runner.drive(action)
        for _ in range(4):
            mujoco.mj_step(self.model, self.data)
            self._sample_judge()


class HimBestLevelRunner(p2mod.LevelRunner):
    """Part 2 level runner driven by the HIMLoco policy step."""

    def warmup(self, seconds: float = 0.5) -> None:
        for _ in range(int(WARMUP_S / 0.02)):
            self._policy_step(np.zeros(3), judge=None)

    def _policy_step(self, command: np.ndarray, judge) -> None:
        action = self.runner.policy_action(command)
        self.runner.drive(action)
        for _ in range(4):
            mujoco.mj_step(self.model, self.data)
            if judge is not None:
                self._sample(judge)


def contract_test(policy_path: Path) -> dict:
    """Verify the TorchScript input/output contract before touching the scenes."""
    policy = torch.jit.load(str(policy_path)).eval()
    torch.manual_seed(0)
    with torch.no_grad():
        single = policy(torch.randn(1, 270))
        batch = policy(torch.randn(3, 270))
    out = {
        "torchscript_load": "ok",
        "in_shape": [1, 270],
        "out_shape": list(single.shape),
        "batch3_out_shape": list(batch.shape),
        "out_abs_max_seed0": float(single.abs().max()),
        "out_dim": int(single.shape[-1]),
        "out_dim_is_12": int(single.shape[-1]) == 12,
        "deterministic": bool(torch.equal(policy(torch.zeros(1, 270)), policy(torch.zeros(1, 270)))),
    }
    if not out["out_dim_is_12"]:
        raise RuntimeError(f"unexpected output dim: {out['out_shape']}")
    return out


def annotate(payload_path: Path, contract: dict, extra: dict) -> None:
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload["policy_contract"] = contract
    payload["eval_contract"] = extra
    payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_summary(out_dir: Path, contract: dict, hashes: dict, part1: dict | None,
                  part2: dict | None, title_suffix: str = "", tag: str = "") -> Path:
    lines = [
        f"# HIMLoco `best.pt` zero-shot evaluation (Part 1 + Part 2){title_suffix}",
        "",
        f"- policy: `{BEST_PT}` ({hashes['bytes']} B, md5 `{hashes['md5']}`, sha256 `{hashes['sha256']}`)",
        f"- config: `{POLICY_CFG}`",
        f"- contract test: in `[1,270]` → out `{contract['out_shape']}`; batch 3 → `{contract['batch3_out_shape']}`; deterministic={contract['deterministic']}",
        "- gains/limits: rl_kp=40, rl_kd=1.2, torque 33.5 N.m, action_scale=0.25, obs clip ±100",
        "- these are **diagnostic** runs (G1 not frozen); do not use as official score",
        "",
    ]
    if part1 is not None:
        lines += [
            "## Part 1 (V2 judge)",
            "",
            "| task | status | score | reason | base | tilt_deg |",
            "|---|---|---:|---|---|---:|",
        ]
        per_task = {a["task"]: a for a in part1["attempts"]}
        for name in sorted(per_task):
            a = per_task[name]
            st = a["judge"]["states"][name]
            lines.append(f"| {name} | {st['status']} | {st['score']} | {st['reason']} | {a['base']} | {a['tilt_deg']} |")
        lines += ["", f"total_score={part1['total_score']} success={part1['success_count']}/{len(part1['attempts'])}", ""]
    if part2 is not None:
        lines += [
            "## Part 2 (V2 evaluator, 1 attempt per level)",
            "",
            "| category | level | success | reason | base | tilt_deg |",
            "|---|---:|---|---|---|---:|",
        ]
        for rec in part2["attempts"]:
            a = rec["attempts"][-1]
            j = a["judge"]
            status = j.get("status", "?")
            reason = j.get("reason", "")
            lines.append(
                f"| {rec['category']} | {rec['level']}{rec['unit']} | "
                f"{'SUCCESS' if rec['best_success'] else 'fail'} ({rec['success_count']}/{rec['attempt_count']}) | "
                f"{status}:{reason} | {a['base']} | {a['tilt_deg']} |"
            )
        lines += ["", f"diag_total_score={part2['total_score']}", ""]
    path = out_dir / f"him_best_eval_summary{tag}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--policy", type=Path, default=BEST_PT)
    ap.add_argument("--part", choices=["part1", "part2", "all"], default="all")
    ap.add_argument("--out-dir", type=Path, default=Path("../prep.d/results"))
    ap.add_argument("--tasks", action="append", default=[], help="Part 1 task names (default: all)")
    ap.add_argument("--only", action="append", default=[], help="Part 2 category or category_level")
    ap.add_argument("--warmup", type=float, default=WARMUP_S, help="Part 1 warmup before the task [s]")
    ap.add_argument("--time-scale", type=float, default=1.0,
                    help="Part 1 diagnostic duration multiplier (for time-extended diagnostics only)")
    ap.add_argument("--p2-seconds", type=float, default=None,
                    help="Part 2 duration override [s] (for time-extended diagnostics only)")
    ap.add_argument("--tag", default="", help="suffix for output file names, e.g. _extended")
    args = ap.parse_args()

    policy = args.policy
    if not policy.is_absolute():
        policy = (Path.cwd() / policy).resolve()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    hashes = file_hashes(policy)
    contract = contract_test(policy)
    cfg = load_cfg()
    extra = {
        "warmup_s": args.warmup,
        "history_len": len(cfg["observations_history"]),
        "history_order": "newest_first",
        "action_scale": float(cfg["action_scale"][0]),
        "rl_kp": float(cfg["rl_kp"][0]),
        "rl_kd": float(cfg["rl_kd"][0]),
        "torque_limit": float(cfg["torque_limits"][0]),
        "obs_clip": float(cfg["clip_obs"]),
        "clips_actions": [float(cfg["clip_actions_lower"][0]), float(cfg["clip_actions_upper"][0])],
        "part1_time_scale": args.time_scale,
        "part2_seconds": args.p2_seconds,
        "diagnostic_variant": "time-extended" if (args.time_scale != 1.0 or args.p2_seconds) else "frozen-start",
    }
    print(f"policy {policy}")
    print(f"  {hashes}")
    print(f"  contract: {contract}")
    print(f"  eval contract: {extra}")

    part1 = part2 = None
    part1_json = args.out_dir / f"him_best_part1_v2{args.tag}.json"
    part2_json = args.out_dir / f"him_best_part2_v2{args.tag}.json"

    if args.part in ("part1", "all"):
        p1mod.ScenePolicyRunner = HimBestRunner
        p1mod.V2Runner = HimBestPart1Runner
        if args.time_scale != 1.0:
            p1mod.TASKS = {
                name: (xyz, yaw, cmd, seconds * args.time_scale, note)
                for name, (xyz, yaw, cmd, seconds, note) in p1mod.TASKS.items()
            }
        argv = [
            "run_part1_judged_rollout_v2.py",
            "--policy", str(policy),
            "--json", str(part1_json),
            "--warmup", str(args.warmup),
        ]
        for task in args.tasks:
            argv += ["--task", task]
        old_argv, sys.argv = sys.argv, argv
        try:
            p1mod.main()
        finally:
            sys.argv = old_argv
        annotate(part1_json, contract, extra)
        part1 = json.loads(part1_json.read_text(encoding="utf-8"))

    if args.part in ("part2", "all"):
        p2mod.ScenePolicyRunner = HimBestRunner
        p2mod.LevelRunner = HimBestLevelRunner
        argv = [
            "run_part2_judged_eval.py",
            "--policy", str(policy),
            "--json", str(part2_json),
        ]
        if args.p2_seconds is not None:
            argv += ["--seconds", str(args.p2_seconds)]
        for only in args.only:
            argv += ["--only", only]
        old_argv, sys.argv = sys.argv, argv
        try:
            p2mod.main()
        finally:
            sys.argv = old_argv
        annotate(part2_json, contract, extra)
        part2 = json.loads(part2_json.read_text(encoding="utf-8"))

    summary = write_summary(args.out_dir, contract, hashes, part1, part2,
                            "" if not args.tag else f" — {extra['diagnostic_variant']}",
                            tag=args.tag)
    print("summary:", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
