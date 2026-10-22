#!/usr/bin/env python3
"""comp_compliance.py — 部署/规则合规的确定性检查（传感器红线、力矩上限、仅 RL、actor 契约）。

输入是契约 + 一份证据 JSON（由 executor 从部署审计/模型元数据/执行器配置整理；纯数据，不靠自述结论）。
工具只做 Type-A 检查；"这个证据本身是否充分"由 Codex 审计（Prompt A 的 E 节）。

证据 JSON 形状（示例见 --self-test 与 templates/）：

    {
      "policy": {"obs_dim": 45, "action_dim": 12,
                 "obs_fields": ["command_xyz", "base_ang_vel", "projected_gravity", ...]},
      "actuators": [{"joint_type": "hip", "ctrl_max_nm": 23.7},
                    {"joint_type": "thigh", "ctrl_max_nm": 23.7},
                    {"joint_type": "calf", "ctrl_max_nm": 59.25}],
      "runtime": {"part2_has_fixed_action_sequence": false,
                  "world_truth_in_obs": false},
      "notes": "..."
    }

用法：

    python3 comp/tools/comp_compliance.py \
        --contract comp/CONTRACT.json --evidence comp/compliance_evidence.json \
        --out comp/COMPLIANCE.md --json-out comp/COMPLIANCE.json

    python3 comp/tools/comp_compliance.py --self-test

退出码：0 = 全部 PASS/WARN；1 = 存在 FAIL；2 = 用法/输入错误。
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

TOL = 1e-6


def _norm(s: str) -> str:
    return str(s).strip().lower().replace("-", "_").replace(" ", "_")


def check(contract: dict, evidence: dict) -> list[dict]:
    checks: list[dict] = []
    constraints = contract.get("constraints") or {}
    pcon = contract.get("policy_contract") or {}
    policy = evidence.get("policy") or {}
    runtime = evidence.get("runtime") or {}

    def add(cid: str, ok: bool, detail: str, severity: str = "FAIL") -> None:
        checks.append({"id": cid, "verdict": "PASS" if ok else severity,
                       "detail": detail})

    # A. actor 契约
    want_obs = pcon.get("actor_obs_dim")
    got_obs = policy.get("obs_dim")
    add("actor_obs_dim", want_obs is None or got_obs == want_obs,
        f"契约 {want_obs} / 证据 {got_obs}")
    want_act = pcon.get("action_dim")
    got_act = policy.get("action_dim")
    add("action_dim", want_act is None or got_act == want_act,
        f"契约 {want_act} / 证据 {got_act}")

    # B. 禁用传感器（按字段名子串；不做语义猜测，名字不符请补证据）
    fields = [_norm(f) for f in (policy.get("obs_fields") or [])]
    forbidden = [_norm(f) for f in (constraints.get("sensors_forbidden") or [])]
    if fields and forbidden:
        hits = sorted({f for f in forbidden for name in fields if f in name})
        add("forbidden_sensors", not hits,
            "obs_fields 命中禁用项: " + ", ".join(hits) if hits else "obs_fields 未命中禁用传感器名")
    else:
        add("forbidden_sensors", True,
            "证据缺 obs_fields 或契约缺 sensors_forbidden，跳过（WARN 级未检查）", severity="WARN")

    # C. 导航真值不得进网络
    world_in_obs = runtime.get("world_truth_in_obs")
    add("world_truth_scope", not bool(world_in_obs),
        f"world_truth_in_obs={world_in_obs}（规则：真值仅可用于生成速度指令）")

    # D. Part 2 仅 RL
    if constraints.get("part2_rl_only"):
        fixed = runtime.get("part2_has_fixed_action_sequence")
        add("part2_rl_only", not bool(fixed),
            f"part2_has_fixed_action_sequence={fixed}（规则要求仅 RL）")

    # E. 力矩上限
    limits = {_norm(k): float(v) for k, v in (constraints.get("torque_limits_nm") or {}).items()}
    actuators = evidence.get("actuators") or []
    if not actuators:
        add("torque_limits", True, "证据缺 actuators，跳过（WARN 级未检查）", severity="WARN")
    else:
        for act in actuators:
            jt = _norm(act.get("joint_type", ""))
            limit = limits.get(jt)
            got = act.get("ctrl_max_nm")
            if limit is None or got is None:
                add(f"torque:{jt}", False, f"无契约/证据力矩（limit={limit}, got={got}）")
                continue
            add(f"torque:{jt}", float(got) <= limit + TOL,
                f"证据 {got} N·m / 上限 {limit} N·m")
    return checks


def run(contract_path: Path, evidence_path: Path, out: Path | None, json_out: Path | None) -> int:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    checks = check(contract, evidence)
    fails = [c for c in checks if c["verdict"] == "FAIL"]
    overall = "FAIL" if fails else ("WARN" if any(c["verdict"] == "WARN" for c in checks) else "PASS")
    lines = ["# 合规检查（comp_compliance.py）", "",
             f"- 契约：`{contract_path}`（{contract.get('contract_version', '?')}）",
             f"- 证据：`{evidence_path}`",
             f"- overall：**{overall}**", "",
             "| 检查项 | verdict | 说明 |", "|---|---|---|"]
    for c in checks:
        lines.append(f"| {c['id']} | {c['verdict']} | {c['detail']} |")
    md = "\n".join(lines) + "\n"
    payload = {"contract_version": contract.get("contract_version"),
               "overall": overall, "checks": checks}
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(md, encoding="utf-8")
        print(f"compliance report written: {out}")
    if json_out:
        json_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"overall: {overall}")
    for c in checks:
        print(f"[{c['verdict']}] {c['id']}: {c['detail']}")
    return 1 if fails else 0


def run_self_test() -> int:
    """自检不依赖外部模板文件，便于复制到目标仓库后运行。"""
    contract = {
        "contract_version": "selftest",
        "constraints": {
            "sensors_allowed": ["imu", "joint_encoder", "camera", "lidar"],
            "sensors_forbidden": ["body_lin_vel", "heightmap", "foot_force", "foot_height", "body_height", "privileged_terrain_scan"],
            "torque_limits_nm": {"hip": 25, "thigh": 25, "calf": 60},
            "part2_rl_only": True,
        },
        "policy_contract": {"actor_obs_dim": 45, "action_dim": 12},
    }
    good = {
        "policy": {"obs_dim": 45, "action_dim": 12,
                   "obs_fields": ["command_xyz", "base_ang_vel", "projected_gravity",
                                  "joint_pos", "joint_vel", "last_action"]},
        "actuators": [{"joint_type": "hip", "ctrl_max_nm": 23.7},
                      {"joint_type": "thigh", "ctrl_max_nm": 23.7},
                      {"joint_type": "calf", "ctrl_max_nm": 59.25}],
        "runtime": {"part2_has_fixed_action_sequence": False, "world_truth_in_obs": False},
    }
    checks = check(contract, good)
    assert all(c["verdict"] == "PASS" for c in checks), checks

    bad = json.loads(json.dumps(good))
    bad["policy"]["obs_fields"].append("privileged_terrain_scan")
    bad["actuators"][2]["ctrl_max_nm"] = 99.0
    bad["runtime"]["part2_has_fixed_action_sequence"] = True
    checks = check(contract, bad)
    ids = {c["id"]: c["verdict"] for c in checks}
    assert ids["forbidden_sensors"] == "FAIL", ids
    assert ids["torque:calf"] == "FAIL", ids
    assert ids["part2_rl_only"] == "FAIL", ids
    with tempfile.TemporaryDirectory() as td:
        cp = Path(td) / "contract.json"
        ep = Path(td) / "evidence.json"
        cp.write_text(json.dumps(contract), encoding="utf-8")
        ep.write_text(json.dumps(good), encoding="utf-8")
        assert run(cp, ep, None, None) == 0
        ep.write_text(json.dumps(bad), encoding="utf-8")
        assert run(cp, ep, None, None) == 1
    print("comp_compliance.py self-test: OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="部署/规则合规检查")
    ap.add_argument("--contract", type=Path)
    ap.add_argument("--evidence", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--json-out", type=Path)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return run_self_test()
    if not args.contract or not args.evidence:
        ap.error("需要 --contract 与 --evidence（或 --self-test）")
    return run(args.contract, args.evidence, args.out, args.json_out)


if __name__ == "__main__":
    sys.exit(main())
