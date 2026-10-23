"""Build the C1 human-calibration bundle (videos + records + label sheet).

C1 calibration dataset (comp/eval/_calibration/README.md):
  - Part 1: 8 obstacles x 4 policies = 32 records
  - Part 2: 6 categories x 4 (level, policy) = 24 records
  - session state: 8 ledger/protocol records (state tables, no robot video)

For each robot-rollout record this script writes:
  - an mp4 video (tracking camera, 20 fps, prep.d/videos/calibration/)
  - a JSON record with the judge verdict, evidence summary, policy/start/command
    and an empty ``human`` label field.

Usage (from MyMonoRepo.d):
  pixi run python @20261019_locomotion/scripts/agent_scripts/build_calibration_bundle.py \
      --out-dir ../prep.d/videos/calibration \
      --labels @20261019_locomotion/comp/eval/_calibration/records.jsonl
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import mujoco
import numpy as np

ROOT = Path("@20261019_locomotion")
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from comp_part2_judge import Part2JudgeV2  # noqa: E402
from run_part1_judged_rollout_v2 import TASKS, V2Runner  # noqa: E402
from run_part2_judged_eval import LevelRunner  # noqa: E402

SCENE_P1 = str(ROOT / "assets/terrain/part1/part1_eval_scene_v2.xml")
LEVELS_JSON = ROOT / "config/part2-levels.json"
DEFAULT_POLICIES = ["flat-ft-2500", "baseline-2000", "baseline-rough-3999", "gravel-flat-2100"]
LEGS = ("FL", "FR", "RL", "RR")


# ---------------------------------------------------------------- rendering
def _render_frames(frames: list[np.ndarray], out_mp4: Path, fps: int = 20) -> None:
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="cal_frames_"))
    try:
        for i, frame in enumerate(frames):
            with open(tmp / f"f{i:05d}.ppm", "wb") as fh:
                fh.write(f"P6\n{frame.shape[1]} {frame.shape[0]}\n255\n".encode())
                fh.write(frame.tobytes())
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                        "-framerate", str(fps), "-i", str(tmp / "f%05d.ppm"),
                        "-pix_fmt", "yuv420p", str(out_mp4)], check=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _make_renderer(model, width: int = 640, height: int = 480):
    renderer = mujoco.Renderer(model, height=height, width=width)
    opt = mujoco.MjvOption()
    opt.geomgroup[:] = 1
    cam = mujoco.MjvCamera()
    cam.distance = 3.0
    cam.elevation = -25.0
    cam.azimuth = 135.0
    return renderer, opt, cam


def _track(cam, data, body: int, ahead: float = 0.9) -> None:
    pos = np.asarray(data.xpos[body], dtype=float)
    rot = np.asarray(data.xmat[body], dtype=float).reshape(3, 3)
    fwd = rot[:, 0]
    cam.lookat[:] = (pos[0] + fwd[0] * ahead, pos[1] + fwd[1] * ahead,
                    max(0.25, pos[2] - 0.05))


# ---------------------------------------------------------------- Part 1
def render_part1(task: str, policy: str, out_mp4: Path) -> dict:
    xyz, yaw, cmd, seconds, note = TASKS[task]
    vr = V2Runner(SCENE_P1, str(ROOT / "assets/policies" / policy / "policy.pt"),
                  (xyz[0], xyz[1], xyz[2], yaw))
    renderer, opt, cam = _make_renderer(vr.model)
    frames: list[np.ndarray] = []
    n = int(0.5 / 0.02)
    for _ in range(n):
        vr._policy_step(np.zeros(3))
    for _ in range(int(seconds / 0.02)):
        vr._policy_step(np.asarray(cmd, dtype=float))
        _track(cam, vr.data, vr.trunk)
        renderer.update_scene(vr.data, camera=cam, scene_option=opt)
        frames.append(renderer.render().copy())
    renderer.close()
    report = vr.judge.finalize("timeout")
    _render_frames(frames, out_mp4, fps=50)
    st = report["states"][task]
    base, tilt = vr.runner.base()
    return {
        "judge": {"status": st["status"], "score": float(st["score"]),
                  "reason": st.get("reason") or "", "detail": st.get("detail") or {}},
        "base_final": [round(float(v), 3) for v in base],
        "tilt_deg": round(float(tilt), 2),
        "start": [float(v) for v in xyz] + [float(yaw)],
        "command": [float(v) for v in cmd],
        "seconds": float(seconds),
        "note": note,
        "frames": len(frames),
    }


# ---------------------------------------------------------------- Part 2
def _levels() -> list[dict]:
    return json.loads(LEVELS_JSON.read_text(encoding="utf-8"))["levels"]


def render_part2(entry: dict, policy: str, out_mp4: Path) -> dict:
    j = entry["judge"]
    start = j.get("start", [0.0, 0.0, 0.55, 0.0])
    lr = LevelRunner(str(ROOT / entry["scene"]), str(ROOT / "assets/policies" / policy / "policy.pt"),
                     (start[0], start[1], start[2], start[3]))
    renderer, opt, cam = _make_renderer(lr.model)
    frames: list[np.ndarray] = []
    lr.warmup(0.5)
    judge = Part2JudgeV2(entry)
    command = np.asarray(j.get("command", [0.5, 0.0, 0.0]), dtype=float)
    duration = float(j.get("seconds", 6.0))
    for _ in range(int(duration / 0.02)):
        lr._policy_step(command, judge=judge)
        _track(cam, lr.data, lr.runner.trunk)
        renderer.update_scene(lr.data, camera=cam, scene_option=opt)
        frames.append(renderer.render().copy())
    renderer.close()
    report = judge.finalize("timeout")
    _render_frames(frames, out_mp4, fps=50)
    base, tilt = lr.runner.base()
    return {
        "judge": {"status": report.get("status"), "score": float(report.get("score") or 0.0),
                  "reason": report.get("reason") or "", "detail": report.get("detail") or {}},
        "base_final": [round(float(v), 3) for v in base],
        "tilt_deg": round(float(tilt), 2),
        "start": [float(v) for v in start],
        "command": [float(v) for v in command],
        "seconds": duration,
        "note": f"{entry['category']} {entry['level']}{entry.get('unit','')}",
        "frames": len(frames),
    }


# ---------------------------------------------------------------- session records
def _course_records(course_json: Path) -> list[dict]:
    data = json.loads(course_json.read_text(encoding="utf-8"))
    attempts = data.get("attempts") or []
    summary = data.get("session_summary") or {}
    rows = []
    for i, att in enumerate(attempts, 1):
        rec = att.get("attempt_result") or {}
        rows.append({
            "kind": "session_attempt",
            "attempt": i,
            "score": rec.get("score"),
            "duration_s": round(float(rec.get("duration_s") or 0.0), 3),
            "skipped": bool(rec.get("skipped")),
            "reason": rec.get("reason"),
            "events": rec.get("events"),
        })
    return [{
        "kind": "session_state",
        "title": "整场 3 次尝试账本（best score / fastest tie-break）",
        "state_table": {
            "attempts_used": summary.get("attempts_used"),
            "recoveries": summary.get("recoveries"),
            "pauses": summary.get("pauses"),
            "final_score": summary.get("final_score"),
            "final_time_s": summary.get("final_time_s"),
            "final_time_scope": summary.get("final_time_scope")
                                   or "min_duration_among_best_score_attempts",
            "attempts": rows,
        },
        "judge": {"status": "n/a", "score": summary.get("final_score") or 0.0,
                  "reason": "protocol_ledger", "detail": {}},
        "human": {"success": None, "failure_reason": None, "protocol_ok": None},
        "video": None,
        "note": "只审协议/账本：best score、同分取最快、恢复不消耗、最终计时口径",
    }]


def _drill_record(path: Path, title: str, human_hint: str) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    summary = data.get("session_summary") or {}
    attempts = data.get("attempts") or []
    events = []
    for att in attempts:
        rec = att.get("attempt_result") or {}
        events.append({
            "attempt": rec.get("attempt"),
            "score": rec.get("score"),
            "duration_s": rec.get("duration_s"),
            "skipped": rec.get("skipped"),
            "reason": rec.get("reason"),
            "events": rec.get("events"),
        })
    return {
        "kind": "session_state",
        "title": title,
        "state_table": {
            "attempts_used": summary.get("attempts_used"),
            "recoveries": summary.get("recoveries"),
            "skips": summary.get("skips"),
            "pauses": summary.get("pauses"),
            "events": summary.get("events"),
            "attempts": events,
        },
        "judge": {"status": "n/a", "score": 0.0, "reason": "protocol_ledger", "detail": {}},
        "human": {"success": None, "failure_reason": None, "protocol_ok": None},
        "video": None,
        "note": human_hint,
    }


SESSION_SOURCES = [
    ("part1_course_diag.json", "course", "整场 3 次尝试账本（best/fastest）", "账本是否正确：best score + 同分最快、恢复不消耗"),
    ("part1_course_pause_resume_drill.json", "pause", "暂停/恢复演练（3 attempts，每 attempt 暂停 1 s 后原位恢复）",
     "暂停期间物理冻结、恢复原位且不消耗尝试、时长不含暂停"),
    ("part1_course_abort_drill.json", "abort", "主动 abort 演练（3 attempts，每 attempt 暂停→恢复→abort）",
     "abort 消耗尝试、skip 记录、duration 用模拟器时钟"),
    ("part1_course_pause_timeout_drill.json", "timeout", "暂停超时演练（pause 后不恢复，120 s 超时）",
     "120 s 超时 abort、事件与 operator_t 记录"),
]


def _session_records(results_dir: Path) -> list[dict]:
    """Exactly 8 session-state records (protocol/ledger semantics)."""
    recs: list[dict] = []
    course = results_dir / "part1_course_diag.json"
    course_data = json.loads(course.read_text(encoding="utf-8")) if course.is_file() else {}
    if course_data:
        recs.extend(_course_records(course))
    # pause/resume timeline from the course pause drill (same JSON as the course run)
    if course_data:
        atts = course_data.get("attempts") or []
        rows = []
        for att in atts:
            rec = att.get("attempt_result") or {}
            rows.append({"attempt": rec.get("attempt"), "duration_s": rec.get("duration_s"),
                         "events": rec.get("events"), "recoveries": (att.get("judge") or {})
                         .get("summary", {}).get("recoveries")})
        recs.append({
            "kind": "session_state",
            "title": "暂停/恢复演练时间账本（3 attempts，每 attempt 暂停约 1 s 后原位恢复）",
            "state_table": {"attempts": rows,
                            "session_summary": course_data.get("session_summary")},
            "judge": {"status": "n/a", "score": 0.0, "reason": "protocol_ledger", "detail": {}},
            "human": {"success": None, "failure_reason": None, "protocol_ok": None},
            "video": None,
            "note": "暂停期间物理冻结、恢复后不消耗尝试；duration 不含暂停（模拟器时钟）",
        })
    for fname, kind, title, hint in SESSION_SOURCES:
        p = results_dir / fname
        if p.is_file() and kind in ("abort", "timeout"):
            recs.append(_drill_record(p, title, hint))
    abort = results_dir / "part1_course_abort_drill.json"
    if abort.is_file():
        data = json.loads(abort.read_text(encoding="utf-8"))
        recs.append({
            "kind": "session_state",
            "title": "skipped attempt 语义（abort drill）",
            "state_table": {"session_summary": data.get("session_summary"),
                            "attempts": data.get("attempts")},
            "judge": {"status": "n/a", "score": 0.0, "reason": "protocol_ledger", "detail": {}},
            "human": {"success": None, "failure_reason": None, "protocol_ok": None},
            "video": None,
            "note": "skipped 不计分/不计时长/不作 evidence",
        })
    # timing/tie-break worked example
    summary = course_data.get("session_summary") or {}
    attempts = course_data.get("attempts") or []
    recs.append({
        "kind": "session_state",
        "title": "best score / 同分取最快 计算示例",
        "state_table": {
            "attempts": [{"attempt": (a.get("attempt_result") or {}).get("attempt"),
                          "score": (a.get("attempt_result") or {}).get("score"),
                          "duration_s": (a.get("attempt_result") or {}).get("duration_s")}
                         for a in attempts],
            "final_score": summary.get("final_score"),
            "final_time_s": summary.get("final_time_s"),
            "rule": "best score first; tie -> fastest among best-score attempts only",
        },
        "judge": {"status": "n/a", "score": float(summary.get("final_score") or 0.0),
                  "reason": "protocol_ledger", "detail": {}},
        "human": {"success": None, "failure_reason": None, "protocol_ok": None},
        "video": None,
        "note": "分数最高优先；同分只在最高分尝试内取最快（不是全局最快）",
    })
    # return-bonus semantics card
    recs.append({
        "kind": "session_state",
        "title": "返回奖励语义（全 8 项满分后才生效）",
        "state_table": {
            "rule": "return bonus only if all 8 obstacles full score, then re-enter start area",
            "course_final_score": summary.get("final_score"),
            "course_return_evidence": summary.get("return_evidence") if "return_evidence" in summary else None,
            "note": "部分分/缺项不得触发返回奖励；返回奖励只认单项满分",
        },
        "judge": {"status": "n/a", "score": 0.0, "reason": "protocol_ledger", "detail": {}},
        "human": {"success": None, "failure_reason": None, "protocol_ok": None},
        "video": None,
        "note": "返回奖励必须全部障碍满分后重新进入出发区",
    })
    # attempt cap / recovery semantics card from course evidence
    recs.append({
        "kind": "session_state",
        "title": "3 次尝试上限与恢复不消耗",
        "state_table": {
            "attempts_used": summary.get("attempts_used"),
            "recoveries": summary.get("recoveries"),
            "max_attempts": 3,
            "rule": "recovery/pause does not consume an attempt; abort/skip does",
        },
        "judge": {"status": "n/a", "score": 0.0, "reason": "protocol_ledger", "detail": {}},
        "human": {"success": None, "failure_reason": None, "protocol_ok": None},
        "video": None,
        "note": "整场最多 3 次尝试；恢复不消耗；abort/主动重跑消耗",
    })
    return recs[:8]



# ---------------------------------------------------------------- rulecards (SVG)
RULE_P1 = {
    "height_bar": {
        "success": [
            {"x": 5.7, "y": -10.4, "bar_z": 0.325}, {"x": 5.7, "y": -9.0, "bar_z": 0.325},
            {"x": 5.7, "y": -8.4, "bar_z": 0.325}, {"x": 5.7, "y": -8.2, "bar_z": 0.325},
        ],
        "fail": [
            {"x": 5.7, "y": -10.4, "bar_z": 0.325}, {"x": 5.7, "y": -9.0, "bar_z": 0.20},
            {"x": 5.7, "y": -8.4, "bar_z": 0.20}, {"x": 5.7, "y": -8.2, "bar_z": 0.20},
        ],
    },
    "high_wall": {
        "success": [
            {"x": 1.8, "y": -7.9}, {"x": 1.8, "y": -7.4, "z": 0.75, "tags": ["wall"]},
            {"x": 1.8, "y": -7.0, "z": 0.85, "tags": ["wall"]}, {"x": 1.8, "y": -6.6, "z": 0.75, "tags": ["wall"]},
            {"x": 1.8, "y": -6.0},
        ],
        "fail": [
            {"x": 1.8, "y": -7.9}, {"x": 1.8, "y": -7.4}, {"x": 1.8, "y": -7.0},
            {"x": 1.8, "y": -6.6}, {"x": 1.8, "y": -6.0},
        ],
    },
    "bridge_blocks": {
        "success": [
            {"x": 0.5, "y": 0.0}, {"x": 1.35, "y": 0.0, "tags": ["platform_left"]},
            {"x": 2.2, "y": 0.0, "tags": ["bridge"]}, {"x": 3.2, "y": 0.0, "tags": ["bridge"]},
            {"x": 4.2, "y": 0.0, "tags": ["bridge"]}, {"x": 5.2, "y": 0.0, "tags": ["bridge"]},
            {"x": 5.6, "y": 0.0, "tags": ["platform_right"]}, {"x": 6.5, "y": 0.0},
        ],
        "fail": [
            {"x": 0.5, "y": 0.0}, {"x": 1.35, "y": 0.0, "tags": ["platform_left"]},
            {"x": 3.2, "y": 0.0, "tags": ["bridge"], "ground": ["FL", "FR"]}, {"x": 4.0, "y": 0.0},
        ],
    },
    "bridge_bands": {
        "success": [
            {"x": 5.7, "y": -4.2}, {"x": 5.7, "y": -3.6, "tags": ["platform_low"]},
            {"x": 5.7, "y": -2.8, "tags": ["bridge"]}, {"x": 5.7, "y": -2.4, "tags": ["bridge"]},
            {"x": 5.7, "y": -2.0, "tags": ["bridge"]}, {"x": 5.7, "y": -1.3, "tags": ["platform_high"]},
            {"x": 5.7, "y": -0.6},
        ],
        "fail": [
            {"x": 5.7, "y": -4.2}, {"x": 5.7, "y": -3.6, "tags": ["platform_low"]},
            {"x": 5.7, "y": -2.25, "tags": ["bridge"], "ground": ["FL", "FR"]}, {"x": 5.7, "y": -1.6},
        ],
    },
    "gravel_pit": {
        "success": [
            {"x": 5.0, "y": -13.4}, {"x": 5.0, "y": -12.9, "tags": ["gravel"]},
            {"x": 5.5, "y": -12.0, "tags": ["gravel"]}, {"x": 5.8, "y": -11.5, "tags": ["gravel"]},
            {"x": 6.0, "y": -11.0, "tags": ["gravel"]}, {"x": 6.0, "y": -10.8},
        ],
        "fail": [
            {"x": 4.0, "y": -12.0}, {"x": 4.4, "y": -12.0, "tags": ["gravel"]},
            {"x": 5.2, "y": -12.0, "tags": ["gravel"]}, {"x": 6.0, "y": -12.0, "tags": ["gravel"]},
            {"x": 6.5, "y": -12.0},
        ],
    },
    "t_stairs": {
        "success": [
            {"x": 1.8, "y": -5.4}, {"x": 1.8, "y": -4.9, "tags": ["step:s:1"]},
            {"x": 1.8, "y": -4.6, "tags": ["step:s:2"]}, {"x": 1.8, "y": -4.3, "tags": ["step:s:3"]},
            {"x": 1.8, "y": -3.8, "tags": ["step:top"]}, {"x": 2.2, "y": -3.5, "tags": ["step:e:3"]},
            {"x": 2.6, "y": -3.5, "tags": ["step:e:2"]}, {"x": 3.05, "y": -3.5, "tags": ["step:e:1"]},
            {"x": 3.6, "y": -3.5},
        ],
        "fail": [
            {"x": 1.8, "y": -5.4}, {"x": 1.8, "y": -4.9, "tags": ["step:s:1"]},
            {"x": 1.8, "y": -4.6, "tags": ["step:s:2"]}, {"x": 1.8, "y": -4.3, "tags": ["step:s:3"]},
            {"x": 1.8, "y": -3.8, "tags": ["step:top"]}, {"x": 1.8, "y": -4.3, "tags": ["step:e:3"]},
            {"x": 1.8, "y": -4.9, "tags": ["step:e:1"]}, {"x": 1.8, "y": -5.6},
        ],
    },
    "slope": {
        "success": [
            {"x": 5.2, "y": -6.9}, {"x": 5.2, "y": -6.5, "tags": ["slope"]},
            {"x": 5.2, "y": -6.1, "tags": ["slope"]}, {"x": 5.2, "y": -5.7, "tags": ["slope"]},
            {"x": 5.2, "y": -5.3, "tags": ["slope"]}, {"x": 5.2, "y": -3.9},
        ],
        "fail": [
            {"x": 5.2, "y": -6.9}, {"x": 5.2, "y": -6.5, "tags": ["slope"]},
            {"x": 5.2, "y": -6.1, "tags": ["slope"]}, {"x": 5.2, "y": -3.9},
        ],
    },
    "slalom": {
        "success": [
            {"x": 1.8, "y": -10.1}, {"x": 1.9, "y": -10.5}, {"x": 1.7, "y": -11.0},
            {"x": 1.7, "y": -11.5}, {"x": 1.9, "y": -12.0}, {"x": 1.9, "y": -12.5},
            {"x": 1.55, "y": -12.75}, {"x": 2.4, "y": -12.6}, {"x": 2.8, "y": -12.6},
            {"x": 3.2, "y": -12.5},
        ],
        "fail": [
            {"x": 1.8, "y": -10.1}, {"x": 3.2, "y": -12.5}, {"x": 1.9, "y": -10.5},
            {"x": 1.7, "y": -11.5}, {"x": 1.9, "y": -12.5}, {"x": 1.55, "y": -12.75},
            {"x": 2.8, "y": -12.6}, {"x": 3.6, "y": -11.8},
        ],
    },
}


def _svg_path_card(path: Path, title: str, subtitle: str, samples: list[dict],
                   verdict: str, detail_lines: list[str], zones: list[tuple] = ()) -> None:
    xs = [s.get("x", 0.0) for s in samples]
    ys = [s.get("y", 0.0) for s in samples]
    x0, x1 = min(xs) - 0.5, max(xs) + 0.5
    y0, y1 = min(ys) - 0.5, max(ys) + 0.5
    W, H = 900, 640
    def sx(x): return 60 + (x - x0) / max(1e-6, x1 - x0) * (W - 120)
    def sy(y): return H - 60 - (y - y0) / max(1e-6, y1 - y0) * (H - 180)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
             '<rect width="100%" height="100%" fill="white"/>',
             f'<text x="30" y="32" font-size="20" font-family="sans-serif" font-weight="bold">{title}</text>',
             f'<text x="30" y="56" font-size="14" font-family="sans-serif" fill="#444">{subtitle}</text>',
             f'<text x="30" y="80" font-size="16" font-family="sans-serif" fill="{"#0a7" if verdict=="success" else "#c22"}">judge verdict: {verdict}</text>']
    for (zx0, zx1, zy0, zy1, name) in zones:
        parts.append(f'<rect x="{sx(zx0):.1f}" y="{sy(zy1):.1f}" width="{sx(zx1)-sx(zx0):.1f}" height="{sy(zy0)-sy(zy1):.1f}" fill="none" stroke="#888" stroke-dasharray="6,4"/>')
        parts.append(f'<text x="{sx(zx0)+4:.1f}" y="{sy(zy1)-4:.1f}" font-size="12" font-family="sans-serif" fill="#888">{name}</text>')
    pts = " ".join(f"{sx(s.get('x',0)):.1f},{sy(s.get('y',0)):.1f}" for s in samples)
    parts.append(f'<polyline points="{pts}" fill="none" stroke="#2463eb" stroke-width="3"/>')
    for i, s in enumerate(samples):
        color = "#c22" if s.get("ground") else "#2463eb"
        parts.append(f'<circle cx="{sx(s.get("x",0)):.1f}" cy="{sy(s.get("y",0)):.1f}" r="6" fill="{color}"/>')
        label = str(i + 1)
        tags = s.get("tags") or []
        if tags:
            label += ":" + ",".join(tags)
        if s.get("ground"):
            label += " G:" + ",".join(s["ground"])
        parts.append(f'<text x="{sx(s.get("x",0))+8:.1f}" y="{sy(s.get("y",0))-8:.1f}" font-size="11" font-family="monospace" fill="#333">{label}</text>')
    for i, line in enumerate(detail_lines[:6]):
        parts.append(f'<text x="30" y="{H-120+i*18}" font-size="12" font-family="monospace" fill="#333">{line}</text>')
    parts.append('</svg>')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts), encoding="utf-8")


def _part1_rulecards(out_dir: Path) -> list[dict]:
    from comp_part1_judge import Part1JudgeV2, ZONES
    records = []
    for task in sorted(RULE_P1):
        for expect, key in ((True, "success"), (False, "fail")):
            samples = RULE_P1[task][key]
            judge = Part1JudgeV2()
            rep = None
            for i, smp in enumerate(samples):
                tags = {leg: set(smp.get("tags") or []) for leg in LEGS}
                rep = judge.update(i * 0.02, (smp["x"], smp["y"], smp.get("z", 0.45)), 0.0,
                                   foot_tags=tags, ground_feet=set(smp.get("ground") or []),
                                   bar_z=smp.get("bar_z"))
            rep = rep or judge.finalize("timeout")
            st = rep["states"][task]
            ok = st["status"] == "success"
            verdict = "success" if ok else "fail"
            want = "canonical success path" if expect else "rule-violating path"
            svg = out_dir / f"rule_p1_{task}_{key}.svg"
            _svg_path_card(svg, f"Part1 rulecard: {task} ({want})",
                           "top-down x-y path; labels = foot surface tags / ground contacts",
                           samples, verdict,
                           [f"judge score={st['score']} reason={st.get('reason') or '-'}",
                            "请判断：该轨迹按比赛规则应 success 还是 fail？judge 判对了吗？"],
                           zones=[(ZONES[task][0], ZONES[task][1], ZONES[task][2], ZONES[task][3],
                                   f"ZONES[{task}]")])
            records.append({
                "trial_id": None, "kind": "part1_rulecard", "obstacle": task, "media_type": "svg",
                "video": str(svg), "judge": {"status": verdict, "score": float(st["score"]),
                                             "reason": st.get("reason") or "", "detail": {}},
                "human": {"success": None, "failure_reason": None, "judge_verdict_correct": None},
                "note": f"rulecard: {want}；请按规则标注 success/fail 与 judge 是否正确",
            })
    return records


def _part2_rulecards(out_dir: Path) -> list[dict]:
    from comp_part2_judge import Part2JudgeV2, score_for_level
    contract = json.loads((ROOT / "comp/CONTRACT.json").read_text(encoding="utf-8"))
    levels = _levels()
    by_cat: dict[str, list[dict]] = {}
    for e in levels:
        by_cat.setdefault(e["category"], []).append(e)
    records: list[dict] = []

    def _samples(kind: str, j: dict, success: bool) -> list[dict]:
        if kind == "platform":
            lo, hi = j.get("goal_x", [2.0, 3.0])
            gx = (float(lo) + float(hi)) / 2.0
            z = float(j["top_z"]) + 0.45
            seq = [{"x": 0.0, "z": 0.5, "tags": ["platform"]},
                   {"x": lo - 0.2, "z": 0.55, "tags": ["platform"]},
                   {"x": gx, "z": z, "tags": ["platform"]},
                   {"x": gx, "z": z, "tags": ["platform"]},
                   {"x": gx, "z": z, "tags": ["platform"]}]
            if not success:
                seq = [{"x": 0.0, "z": 0.5, "tags": ["platform"]},
                       {"x": lo - 0.5, "z": 0.5, "tags": ["platform"]},
                       {"x": lo - 0.5, "z": 0.5, "tags": ["platform"]}]
        elif kind == "stairs":
            gx = float(j["goal_x_min"]) + 0.3
            z = float(j["top_z"]) + 0.45
            seq = [{"x": 0.0, "z": 0.5, "tags": ["stairs"]},
                   {"x": 2.0, "z": 0.7, "tags": ["stairs"]},
                   {"x": gx, "z": z, "tags": ["stairs"]},
                   {"x": gx, "z": z, "tags": ["stairs"]},
                   {"x": gx, "z": z, "tags": ["stairs"]}]
            if not success:
                seq = [{"x": 0.0, "z": 0.5, "tags": ["stairs"]},
                       {"x": 2.0, "z": 0.55, "tags": ["stairs"]}]
        elif kind == "slope":
            gx = float(j["goal_x_min"]) + 0.3
            z = float(j["rise_z"]) + 0.45
            seq = [{"x": 0.0, "z": 0.8, "tags": ["slope"]},
                   {"x": 2.0, "z": 0.9, "tags": ["slope"]},
                   {"x": gx, "z": z, "tags": ["slope"]},
                   {"x": gx, "z": z, "tags": ["slope"]},
                   {"x": gx, "z": z, "tags": ["slope"]}]
            if not success:
                seq = [{"x": 0.0, "z": 0.8, "tags": ["slope"]},
                       {"x": 2.0, "z": 0.85, "tags": ["slope"]}]
        elif kind == "wall":
            wx = float(j["wall_x"])
            gx = float(j["goal_x_min"]) + 0.2
            zc = max(float(j["wall_h"]) + 0.15, 0.60)
            seq = [{"x": wx - 0.6, "z": zc, "tags": ["wall"]},
                   {"x": wx, "z": zc + 0.05, "tags": ["wall"]},
                   {"x": gx, "z": 0.5, "tags": []},
                   {"x": gx, "z": 0.5, "tags": []},
                   {"x": gx, "z": 0.5, "tags": []}]
            if not success:
                seq = [{"x": wx - 0.6, "z": 0.45, "tags": []},
                       {"x": wx, "z": 0.45, "tags": []},
                       {"x": gx, "z": 0.45, "tags": []}]
        elif kind == "gap":
            gx = float(j["gap_x"])
            half = float(j.get("width", 0.1)) / 2.0
            gmin = float(j["goal_x_min"]) + 0.2
            seq = [{"x": gx - half - 0.5, "z": 0.5, "tags": []},
                   {"x": gx - 0.1, "z": 0.5, "tags": []},      # crosses near edge
                   {"x": gx + 0.4, "z": 0.5, "tags": []},      # crosses far edge
                   {"x": gmin, "z": 0.5, "tags": []},
                   {"x": gmin, "z": 0.5, "tags": []},
                   {"x": gmin, "z": 0.5, "tags": []}]
            if not success:
                seq = [{"x": gx - half - 0.5, "z": 0.5, "tags": []},
                       {"x": gx, "z": 0.1, "tags": []}]
        elif kind == "plum":
            gx = float(j["goal_x_min"]) + 0.2
            z = float(j["goal_z_min"]) + 0.1
            seq = [{"x": 0.4, "z": 0.6, "tags": []},
                   {"x": 2.0, "z": z, "tags": ["plum"]},
                   {"x": gx, "z": z, "tags": ["plum"]},
                   {"x": gx, "z": z, "tags": ["plum"]},
                   {"x": gx, "z": z, "tags": ["plum"]}]
            if not success:
                seq = [{"x": 0.4, "z": 0.6, "tags": []},
                       {"x": 2.8, "z": 0.42, "tags": ["plum"]},
                       {"x": 2.8, "z": 0.42, "tags": ["plum"]}]
        else:
            seq = []
        return seq

    for cat in sorted(by_cat):
        entries = sorted(by_cat[cat], key=lambda x: float(x["level"]))
        entry = entries[-1]
        for want_success in (True, False):
            samples = _samples(entry["judge"]["kind"], entry["judge"], want_success)
            if not samples:
                continue
            judge = Part2JudgeV2(entry)
            rep = None
            for i, smp in enumerate(samples):
                legs = {leg: set(smp.get("tags") or []) for leg in LEGS}
                rep = judge.update(i * 0.1, (smp["x"], 0.0, smp["z"]), 5.0,
                                   foot_tags=legs, ground_feet=set())
            rep = rep or judge.finalize("timeout")
            ok = rep.get("status") == "success"
            if ok != want_success:
                print(f"  !! rulecard mismatch {cat} want_success={want_success} got={rep.get('status')}", flush=True)
                continue
            score = score_for_level(contract["parts"]["part2"], cat, entry["level"]) if ok else 0
            pts = [{"x": smp["x"], "y": 0.0, "z": smp["z"]} for smp in samples]
            svg = out_dir / f"rule_p2_{cat}_{'success' if want_success else 'fail'}.svg"
            _svg_path_card(svg, f"Part2 rulecard: {cat} level {entry['level']}{entry.get('unit','')}",
                           "top-down x-y path; labels = surface tags at each sample",
                           pts, "success" if ok else "fail",
                           [f"judge score={score} reason={rep.get('reason') or '-'}",
                            f"judge spec: {json.dumps(entry['judge'], ensure_ascii=False)[:120]}",
                            "请判断：该轨迹按规则应 success 还是 fail？judge 判对了吗？"])
            records.append({
                "trial_id": None, "kind": "part2_rulecard", "category": cat,
                "level": entry["level"], "unit": entry.get("unit"), "media_type": "svg",
                "video": str(svg), "judge": {"status": "success" if ok else "fail",
                                             "score": float(score),
                                             "reason": rep.get("reason") or "", "detail": {}},
                "human": {"success": None, "failure_reason": None, "judge_verdict_correct": None},
                "note": "rulecard：请按规则标注 success/fail 与 judge 是否正确",
            })
    return records


# ---------------------------------------------------------------- main
def _choose_policies(prescan: Path | None) -> list[str]:
    if not prescan or not prescan.is_file():
        return DEFAULT_POLICIES
    rows = json.loads(prescan.read_text(encoding="utf-8"))
    rank: dict[str, tuple[int, float]] = {}
    for r in rows:
        pol = r.get("policy")
        if not pol:
            continue
        st = str(r.get("status"))
        score = float(r.get("score") or 0.0)
        succ = 1 if st == "success" else 0
        old = rank.get(pol, (0, 0.0))
        rank[pol] = (old[0] + succ, old[1] + score)
    ordered = sorted(rank, key=lambda p: rank[p], reverse=True)
    chosen = [p for p in ordered if (ROOT / "assets/policies" / p / "policy.pt").is_file()][:4]
    return chosen or DEFAULT_POLICIES


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=Path, default=Path("../prep.d/videos/calibration"))
    ap.add_argument("--records", type=Path,
                    default=Path("@20261019_locomotion/comp/eval/_calibration/records.jsonl"))
    ap.add_argument("--labels-csv", type=Path,
                    default=Path("@20261019_locomotion/comp/eval/_calibration/labels_template.csv"))
    ap.add_argument("--prescan", type=Path, default=Path("../prep.d/results/c1_prescan_part1.json"))
    ap.add_argument("--results-dir", type=Path, default=Path("../prep.d/results"))
    ap.add_argument("--policies", nargs="*", default=None)
    ap.add_argument("--only", choices=["part1", "part2", "session", "rulecards"], default=None)
    ap.add_argument("--no-rulecards", action="store_true")
    ap.add_argument("--limit-part1", type=int, default=None)
    ap.add_argument("--limit-part2", type=int, default=None)
    ap.add_argument("--skip-existing", action="store_true")
    args = ap.parse_args()

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    policies = args.policies or _choose_policies(args.prescan)
    print(f"policies: {policies}", flush=True)
    records: list[dict] = []
    seq = 0

    def next_id() -> str:
        nonlocal seq
        seq += 1
        return f"cal-{seq:03d}"

    if args.only in (None, "part1"):
        tasks = sorted(TASKS)
        combos = [(t, p) for p in policies for t in tasks]
        if args.limit_part1:
            combos = combos[: args.limit_part1]
        for task, pol in combos:
            rid = next_id()
            video = out_dir / f"{rid}_p1_{task}_{pol}.mp4"
            if not (args.skip_existing and video.is_file()):
                print(f"[part1] {rid} {task} {pol}", flush=True)
                try:
                    info = render_part1(task, pol, video)
                except Exception as exc:  # noqa: BLE001
                    print(f"  !! failed: {type(exc).__name__}: {exc}", flush=True)
                    continue
            else:
                info = {"judge": {"status": "unknown", "score": 0.0, "reason": "existing", "detail": {}}}
            records.append({
                "trial_id": rid, "kind": "part1_obstacle", "obstacle": task, "policy": pol,
                "video": str(video.relative_to(Path("../prep.d").resolve())) if video.is_absolute()
                         else str(video),
                "judge": info["judge"], "note": info.get("note"),
                "start": info.get("start"), "command": info.get("command"),
                "seconds": info.get("seconds"), "frames": info.get("frames"),
                "human": {"success": None, "failure_reason": None},
            })

    if args.only in (None, "part2"):
        levels = _levels()
        by_cat: dict[str, list[dict]] = {}
        for e in levels:
            by_cat.setdefault(e["category"], []).append(e)
        combos = []
        for cat, entries in by_cat.items():
            ordered = sorted(entries, key=lambda x: float(x["level"]))
            for i in range(4):
                e = ordered[min(i, len(ordered) - 1)]
                pol = policies[i % len(policies)]
                combos.append((e, pol))
        if args.limit_part2:
            combos = combos[: args.limit_part2]
        for entry, pol in combos:
            rid = next_id()
            key = f"{entry['category']}_{entry['level']}{entry.get('unit','')}"
            video = out_dir / f"{rid}_p2_{key}_{pol}.mp4"
            if not (args.skip_existing and video.is_file()):
                print(f"[part2] {rid} {key} {pol}", flush=True)
                try:
                    info = render_part2(entry, pol, video)
                except Exception as exc:  # noqa: BLE001
                    print(f"  !! failed: {type(exc).__name__}: {exc}", flush=True)
                    continue
            else:
                info = {"judge": {"status": "unknown", "score": 0.0, "reason": "existing", "detail": {}}}
            records.append({
                "trial_id": rid, "kind": "part2_level", "category": entry["category"],
                "level": entry["level"], "unit": entry.get("unit"), "policy": pol,
                "scene": entry.get("scene"),
                "video": str(video),
                "judge": info["judge"], "note": info.get("note"),
                "start": info.get("start"), "command": info.get("command"),
                "seconds": info.get("seconds"), "frames": info.get("frames"),
                "human": {"success": None, "failure_reason": None},
            })

    if (not args.no_rulecards) and args.only in (None, "rulecards"):
        rule_out = out_dir / "rulecards"
        rule_records = _part1_rulecards(rule_out) + _part2_rulecards(rule_out)
        for r in rule_records:
            r["trial_id"] = next_id()
        records.extend(rule_records)

    if args.only in (None, "session"):
        sessions = _session_records(args.results_dir)
        for s in sessions:
            s["trial_id"] = next_id()
            records.append(s)

    # write records + label sheet
    args.records.parent.mkdir(parents=True, exist_ok=True)
    with args.records.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    header = ["trial_id", "kind", "obstacle_or_category", "level", "policy", "video",
              "judge_status", "judge_score", "human_success", "human_failure_reason",
              "human_protocol_ok", "human_judge_verdict_correct", "notes"]
    with args.labels_csv.open("w", encoding="utf-8") as fh:
        fh.write(",".join(header) + "\n")
        for r in records:
            row = [r["trial_id"], r["kind"],
                   r.get("obstacle") or r.get("category") or r.get("title", ""),
                   r.get("level", ""), r.get("policy", ""), r.get("video") or "",
                   (r.get("judge") or {}).get("status", ""),
                   str((r.get("judge") or {}).get("score", "")),
                   "", "", "", "", r.get("note", "") or ""]
            fh.write(",".join('"' + str(x).replace('"', '""') + '"' for x in row) + "\n")
    print(f"records: {len(records)} -> {args.records}")
    print(f"labels template -> {args.labels_csv}")
    print(json.dumps({"part1": sum(1 for r in records if r['kind'] == 'part1_obstacle'),
                      "part2": sum(1 for r in records if r['kind'] == 'part2_level'),
                      "session": sum(1 for r in records if r['kind'] == 'session_state')},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
