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
from run_part1_judged_rollout_v2 import SPECIAL_WAYPOINTS, TASKS, V2Runner  # noqa: E402
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
    def _render_frame(vr_):
        _track(cam, vr_.data, vr_.trunk)
        renderer.update_scene(vr_.data, camera=cam, scene_option=opt)
        frames.append(renderer.render().copy())

    waypoints = SPECIAL_WAYPOINTS.get(task)
    reached: list[bool] = []
    if waypoints:
        reached = vr.run_waypoints(waypoints, on_step=_render_frame)
    else:
        for _ in range(int(seconds / 0.02)):
            vr._policy_step(np.asarray(cmd, dtype=float))
            _render_frame(vr)
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
        "waypoints": [list(w) for w in (waypoints or [])],
        "waypoints_reached": reached,
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
            {"x": 5.7, "y": -10.4, "z": 0.25, "bar_z": 0.325},
            {"x": 5.7, "y": -9.5, "z": 0.25, "bar_z": 0.325},
            {"x": 5.7, "y": -9.0, "z": 0.25, "bar_z": 0.325},
            {"x": 5.7, "y": -8.5, "z": 0.25, "bar_z": 0.325},
            {"x": 5.7, "y": -8.2, "z": 0.25, "bar_z": 0.325},
        ],
        "fail": [
            {"x": 5.7, "y": -10.4, "z": 0.45, "bar_z": 0.325},
            {"x": 5.7, "y": -9.5, "z": 0.45, "bar_z": 0.325},
            {"x": 5.7, "y": -9.0, "z": 0.45, "bar_z": 0.325},
            {"x": 5.7, "y": -8.5, "z": 0.45, "bar_z": 0.325},
            {"x": 5.7, "y": -8.2, "z": 0.45, "bar_z": 0.325},
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
            {"x": 0.5, "y": 0.0, "z": 0.45}, {"x": 1.35, "y": 0.0, "z": 0.55, "tags": ["platform_left"]},
            {"x": 2.2, "y": 0.0, "z": 0.55, "tags": ["bridge"]}, {"x": 3.2, "y": 0.0, "z": 0.55, "tags": ["bridge"]},
            {"x": 4.2, "y": 0.0, "z": 0.55, "tags": ["bridge"]}, {"x": 5.2, "y": 0.0, "z": 0.55, "tags": ["bridge"]},
            {"x": 5.6, "y": 0.0, "z": 0.55, "tags": ["platform_right"]}, {"x": 6.5, "y": 0.0, "z": 0.45},
        ],
        "fail": [
            {"x": 0.5, "y": 0.0}, {"x": 1.35, "y": 0.0, "tags": ["platform_left"]},
            {"x": 3.2, "y": 0.0, "tags": ["bridge"], "ground": ["FL", "FR"]}, {"x": 4.0, "y": 0.0},
        ],
    },
    "bridge_bands": {
        "success": [
            {"x": 5.7, "y": -4.2, "z": 0.45}, {"x": 5.7, "y": -3.6, "z": 0.55, "tags": ["platform_low"]},
            {"x": 5.7, "y": -2.8, "z": 0.55, "tags": ["bridge"]}, {"x": 5.7, "y": -2.4, "z": 0.55, "tags": ["bridge"]},
            {"x": 5.7, "y": -2.0, "z": 0.55, "tags": ["bridge"]}, {"x": 5.7, "y": -1.3, "z": 0.55, "tags": ["platform_high"]},
            {"x": 5.7, "y": -0.6, "z": 0.45},
        ],
        "fail": [
            {"x": 5.7, "y": -4.2}, {"x": 5.7, "y": -3.6, "tags": ["platform_low"]},
            {"x": 5.7, "y": -2.25, "tags": ["bridge"], "ground": ["FL", "FR"]}, {"x": 5.7, "y": -1.6},
        ],
    },
    "gravel_pit": {
        "success": [
            {"x": 3.5, "y": -12.5, "z": 0.45}, {"x": 4.1, "y": -12.5, "z": 0.45},
            {"x": 4.5, "y": -12.5, "z": 0.57, "tags": ["gravel"]},
            {"x": 5.0, "y": -12.5, "z": 0.57, "tags": ["gravel"]},
            {"x": 5.6, "y": -12.5, "z": 0.57, "tags": ["gravel"]},
            {"x": 5.8, "y": -12.0, "z": 0.57, "tags": ["gravel"]},
            {"x": 5.8, "y": -11.5, "z": 0.57, "tags": ["gravel"]},
            {"x": 5.8, "y": -10.8, "z": 0.45},
        ],
        "fail": [
            {"x": 5.0, "y": -13.4, "z": 0.45}, {"x": 5.0, "y": -12.9, "z": 0.57, "tags": ["gravel"]},
            {"x": 5.5, "y": -12.0, "z": 0.57, "tags": ["gravel"]},
            {"x": 5.8, "y": -11.5, "z": 0.57, "tags": ["gravel"]},
            {"x": 6.0, "y": -11.0, "z": 0.57, "tags": ["gravel"]},
            {"x": 6.0, "y": -10.8, "z": 0.45},
        ],
    },
    "t_stairs": {
        "success": [
            {"x": 1.8, "y": -5.4, "z": 0.45}, {"x": 1.8, "y": -4.9, "z": 0.55, "tags": ["step:s:1"]},
            {"x": 1.8, "y": -4.6, "z": 0.65, "tags": ["step:s:2"]},
            {"x": 1.8, "y": -4.3, "z": 0.75, "tags": ["step:s:3"]},
            {"x": 1.8, "y": -3.8, "z": 0.85, "tags": ["step:top"]},
            {"x": 2.2, "y": -3.5, "z": 0.75, "tags": ["step:e:3"]},
            {"x": 2.6, "y": -3.5, "z": 0.65, "tags": ["step:e:2"]},
            {"x": 3.05, "y": -3.5, "z": 0.55, "tags": ["step:e:1"]},
            {"x": 3.6, "y": -3.5, "z": 0.45},
        ],
        "fail": [
            {"x": 1.8, "y": -5.4, "z": 0.45}, {"x": 1.8, "y": -4.9, "z": 0.55, "tags": ["step:s:1"]},
            {"x": 1.8, "y": -4.6, "z": 0.65, "tags": ["step:s:2"]},
            {"x": 1.8, "y": -4.3, "z": 0.75, "tags": ["step:s:3"]},
            {"x": 1.8, "y": -3.8, "z": 0.85, "tags": ["step:top"]},
            {"x": 1.8, "y": -4.3, "z": 0.75, "tags": ["step:e:3"]},
            {"x": 1.8, "y": -4.9, "z": 0.55, "tags": ["step:e:1"]},
            {"x": 1.8, "y": -5.6, "z": 0.45},
        ],
    },
    "slope": {
        "success": [
            {"x": 5.2, "y": -6.9, "z": 0.45}, {"x": 5.2, "y": -6.5, "z": 0.62, "tags": ["slope"]},
            {"x": 5.2, "y": -6.1, "z": 0.62, "tags": ["slope"]}, {"x": 5.2, "y": -5.7, "z": 0.62, "tags": ["slope"]},
            {"x": 5.2, "y": -5.3, "z": 0.62, "tags": ["slope"]}, {"x": 5.2, "y": -3.9, "z": 0.62},
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


def _world_footprints(scene_path, prefixes=None, exclude=("level_floor", "floor", "plum_floor")):
    """Project world-body geoms to x-y footprints for the SVG rulecards."""
    m = mujoco.MjModel.from_xml_path(str(scene_path))
    out = []
    for g in range(m.ngeom):
        if int(m.geom_bodyid[g]) != 0:
            continue
        name = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, g) or ""
        if name in exclude:
            continue
        if prefixes is not None and not any(name.startswith(p) for p in prefixes):
            continue
        if int(m.geom_type[g]) == int(mujoco.mjtGeom.mjGEOM_PLANE):
            continue
        pos = np.asarray(m.geom_pos[g], dtype=float)
        size = np.asarray(m.geom_size[g], dtype=float)
        typ = int(m.geom_type[g])
        if typ == int(mujoco.mjtGeom.mjGEOM_BOX):
            R = np.zeros(9)
            mujoco.mju_quat2Mat(R, np.asarray(m.geom_quat[g], dtype=float))
            R = R.reshape(3, 3)
            pts = []
            for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                q = pos + R @ np.array([sx * size[0], sy * size[1], 0.0])
                pts.append((float(q[0]), float(q[1])))
            out.append({"kind": "poly", "pts": pts, "name": name, "z": float(pos[2]),
                        "top": float(pos[2] + abs(R[2, 2]) * size[2] if abs(R[2, 2]) < 1 else size[2])})
        elif typ in (int(mujoco.mjtGeom.mjGEOM_CYLINDER), int(mujoco.mjtGeom.mjGEOM_CAPSULE),
                     int(mujoco.mjtGeom.mjGEOM_SPHERE)):
            radius = float(size[0]) if typ != int(mujoco.mjtGeom.mjGEOM_CAPSULE) else float(size[0]) + float(size[1])
            out.append({"kind": "circle", "c": (float(pos[0]), float(pos[1])),
                        "r": max(0.04, radius), "name": name, "z": float(pos[2])})
    return out


def _bounds(samples, geoms, zones, goals):
    xs = [s.get("x", 0.0) for s in samples]
    ys = [s.get("y", 0.0) for s in samples]
    for g in geoms:
        if g["kind"] == "poly":
            xs.extend(p[0] for p in g["pts"])
            ys.extend(p[1] for p in g["pts"])
        else:
            xs.extend([g["c"][0] - g["r"], g["c"][0] + g["r"]])
            ys.extend([g["c"][1] - g["r"], g["c"][1] + g["r"]])
    for z in zones:
        xs.extend([z[0], z[1]])
        ys.extend([z[2], z[3]])
    for goal in goals:
        xs.extend([goal[0], goal[1]])
        ys.extend([goal[2], goal[3]])
    return min(xs) - 0.4, max(xs) + 0.4, min(ys) - 0.4, max(ys) + 0.4


def _svg_path_card(path: Path, title: str, subtitle: str, samples: list[dict],
                   verdict: str, detail_lines: list[str], zones: list[tuple] = (),
                   geoms: list[dict] = (), key_lines: list[str] = (),
                   z_lines: list[tuple] = (), goals: list[tuple] = ()) -> None:
    x0, x1, y0, y1 = _bounds(samples, geoms, zones, goals)
    W, H = 1000, 780
    PX0, PX1, PY0, PY1 = 70, 930, 110, 470
    def sx(x): return PX0 + (x - x0) / max(1e-6, x1 - x0) * (PX1 - PX0)
    def sy(y): return PY1 - (y - y0) / max(1e-6, y1 - y0) * (PY1 - PY0)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
             '<rect width="100%" height="100%" fill="white"/>',
             f'<text x="30" y="34" font-size="20" font-family="sans-serif" font-weight="bold">{title}</text>',
             f'<text x="30" y="58" font-size="13" font-family="sans-serif" fill="#444">{subtitle}</text>',
             f'<text x="30" y="84" font-size="17" font-family="sans-serif" font-weight="bold" fill="{"#0a7" if verdict=="success" else "#c22"}">judge verdict: {verdict}</text>',
             f'<rect x="{PX0}" y="{PY0}" width="{PX1-PX0}" height="{PY1-PY0}" fill="#fafafa" stroke="#ccc"/>']
    for z in zones:
        parts.append(f'<rect x="{sx(z[0]):.1f}" y="{sy(z[3]):.1f}" width="{sx(z[1])-sx(z[0]):.1f}" height="{sy(z[2])-sy(z[3]):.1f}" fill="none" stroke="#999" stroke-dasharray="6,4"/>')
        parts.append(f'<text x="{sx(z[0])+4:.1f}" y="{sy(z[3])-4:.1f}" font-size="11" font-family="sans-serif" fill="#999">{z[4] if len(z)>4 else "zone"}</text>')
    for goal in goals:
        parts.append(f'<rect x="{sx(goal[0]):.1f}" y="{sy(goal[3]):.1f}" width="{sx(goal[1])-sx(goal[0]):.1f}" height="{sy(goal[2])-sy(goal[3]):.1f}" fill="#2a7a2a" fill-opacity="0.07" stroke="#2a7a2a" stroke-dasharray="4,3"/>')
        parts.append(f'<text x="{sx(goal[0])+4:.1f}" y="{sy(goal[3])+14:.1f}" font-size="11" font-family="sans-serif" fill="#2a7a2a">{goal[4] if len(goal)>4 else "goal"}</text>')
    for g in geoms:
        if g["kind"] == "poly":
            pts = " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y in g["pts"])
            parts.append(f'<polygon points="{pts}" fill="#d9d0b8" fill-opacity="0.85" stroke="#8a7f66" stroke-width="1"/>')
        else:
            parts.append(f'<circle cx="{sx(g["c"][0]):.1f}" cy="{sy(g["c"][1]):.1f}" r="{max(3.0, (sx(g["c"][0]+g["r"])-sx(g["c"][0]))):.1f}" fill="#b58b5a" fill-opacity="0.8" stroke="#7a5a35"/>')
    pts = " ".join(f"{sx(s.get('x',0)):.1f},{sy(s.get('y',0)):.1f}" for s in samples)
    parts.append(f'<polyline points="{pts}" fill="none" stroke="#2463eb" stroke-width="3"/>')
    for i, smp in enumerate(samples):
        color = "#c22" if smp.get("ground") else "#2463eb"
        parts.append(f'<circle cx="{sx(smp.get("x",0)):.1f}" cy="{sy(smp.get("y",0)):.1f}" r="6" fill="{color}"/>')
        label = str(i + 1)
        tags = smp.get("tags") or []
        if tags:
            label += ":" + ",".join(tags)
        if smp.get("ground"):
            label += " G:" + ",".join(smp["ground"])
        parts.append(f'<text x="{sx(smp.get("x",0))+8:.1f}" y="{sy(smp.get("y",0))-8:.1f}" font-size="11" font-family="monospace" fill="#333">{label}</text>')
    parts.append(f'<text x="{sx(samples[0].get("x",0))-6:.1f}" y="{sy(samples[0].get("y",0))+18:.1f}" font-size="12" font-family="sans-serif" fill="#0a7">IN</text>')
    parts.append(f'<text x="{sx(samples[-1].get("x",0))-8:.1f}" y="{sy(samples[-1].get("y",0))-14:.1f}" font-size="12" font-family="sans-serif" fill="#c22">OUT</text>')
    # z profile subplot
    ZY0, ZY1 = 500, 585
    zs = [float(s.get("z", 0.45)) for s in samples]
    bars = [s.get("bar_z") for s in samples]
    zmin = min(zs + [b for b in bars if b is not None] + [v for v, _ in z_lines] or [0.0])
    zmax = max(zs + [b for b in bars if b is not None] + [v for v, _ in z_lines] or [1.0])
    zmin, zmax = zmin - 0.05, zmax + 0.05
    def zy(z): return ZY1 - (z - zmin) / max(1e-6, zmax - zmin) * (ZY1 - ZY0)
    def zx(i): return PX0 + (i / max(1, len(samples) - 1)) * (PX1 - PX0)
    parts.append(f'<text x="30" y="{ZY0-6}" font-size="12" font-family="sans-serif" fill="#444">base height z (blue) / bar z (orange) vs sample index; dashed = judge threshold</text>')
    parts.append(f'<rect x="{PX0}" y="{ZY0}" width="{PX1-PX0}" height="{ZY1-ZY0}" fill="#fafafa" stroke="#ccc"/>')
    for v, lab in z_lines:
        parts.append(f'<line x1="{PX0}" y1="{zy(v):.1f}" x2="{PX1}" y2="{zy(v):.1f}" stroke="#c22" stroke-dasharray="5,3"/>')
        parts.append(f'<text x="{PX0+4}" y="{zy(v)-3:.1f}" font-size="10" font-family="monospace" fill="#c22">{lab} {v:.2f}</text>')
    zpts = " ".join(f"{zx(i):.1f},{zy(z):.1f}" for i, z in enumerate(zs))
    parts.append(f'<polyline points="{zpts}" fill="none" stroke="#2463eb" stroke-width="2"/>')
    bpts = [(i, b) for i, b in enumerate(bars) if b is not None]
    if bpts:
        bstr = " ".join(f"{zx(i):.1f},{zy(b):.1f}" for i, b in bpts)
        parts.append(f'<polyline points="{bstr}" fill="none" stroke="#d9822b" stroke-width="2" stroke-dasharray="4,2"/>')
    # bottom text blocks
    ty = 615
    parts.append(f'<text x="30" y="{ty}" font-size="12" font-family="sans-serif" font-weight="bold" fill="#333">judge evidence（规则程序实际用到的证据）</text>')
    for i, line in enumerate(detail_lines[:4]):
        parts.append(f'<text x="30" y="{ty+20+i*18}" font-size="11" font-family="monospace" fill="#333">{_esc(line[:150])}</text>')
    ty2 = ty + 100
    parts.append(f'<text x="30" y="{ty2}" font-size="12" font-family="sans-serif" font-weight="bold" fill="#333">KEY RULE / 差异点（判 success/fail 的依据）</text>')
    for i, line in enumerate(key_lines[:5]):
        parts.append(f'<text x="30" y="{ty2+20+i*18}" font-size="11" font-family="sans-serif" fill="#333">{_esc(line[:120])}</text>')
    parts.append(f'<text x="30" y="{H-14}" font-size="11" font-family="sans-serif" fill="#777">足端 tag 只表示"接触了哪个表面"；完成判定还看 base 轨迹/高度/时序/入口-出口方向，见上方证据与规则。</text>')
    parts.append('</svg>')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts), encoding="utf-8")


def _esc(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


P1_GEOM_PREFIXES = {
    "height_bar": ("height_bar_post",),
    "high_wall": ("high_wall",),
    "bridge_blocks": ("bridge_blocks", "bridge_platform_r", "ramp_blocks"),
    "bridge_bands": ("bridge_bands", "bridge_"),
    "gravel_pit": ("gravel_pit",),
    "t_stairs": ("t_stairs",),
    "slope": ("slope_",),
    "slalom": (),
}

P1_KEY = {
    "height_bar": {
        "success": ["成功：低姿态从门洞下方穿过（base z < bar_z），横杆保持未掉落（bar_z≈0.325）；碰杆/擦杆但杆不掉不算失败。",
                    "失败例 A：站立高度（base z 0.45 > bar_z 0.325）从门洞位置通过 = 没有从下方穿过。",
                    "失败例 B：横杆掉落到低位（bar_z 掉到 0.20）。",
                    "本卡差异：base z 与 bar_z 的高度关系 + 是否穿过门洞；不是靠足端接触判定。"],
        "fail": ["失败例：站立高度（base z 0.45 > bar_z 0.325）从门洞位置通过 = 没有从下方穿过；或横杆掉落到 0.20。",
                 "对照 success 卡：路径相同，但 base z 高于/等于 bar_z（未从下方通过）。",
                 "本卡差异：base z 与 bar_z 的高度关系 + 是否穿过门洞；不是靠足端接触判定。"],
    },
    "high_wall": {
        "success": ["成功：爬墙时有墙 tag 接触、max_z_near≥max(wall_h+0.10,0.55)，越过 x≥2.30 后合法退出。",
                    "失败例：从地面高度直接穿墙（无墙接触、无爬高）。",
                    "本卡差异：墙接触 + 近墙最大高度；不是只看 xy 路径。"],
        "fail": ["失败例：从地面高度直接穿墙（无墙接触、无爬高）。",
                 "对照 success 卡：路径相同，但 z/墙接触证据不同。",
                 "本卡差异：墙接触 + 近墙最大高度；不是只看 xy 路径。"],
    },
    "bridge_blocks": {
        "success": ["成功：西平台→方墩→东平台，足在 bridge/platform 上，全程无 ≥2 足触地，从东侧合法退出。",
                    "失败例：中途落坑（某采样 ≥2 足触地）。",
                    "本卡差异：平台/桥面接触 + 无触地 + 东侧出口。"],
        "fail": ["失败例：中途落坑（某采样 ≥2 足触地）。",
                 "对照 success 卡：路径相同，但轨迹中段出现地面足。",
                 "本卡差异：平台/桥面接触 + 无触地 + 东侧出口。"],
    },
    "bridge_bands": {
        "success": ["成功：南低平台→窄带→北高平台，足在 band/platform 上，从北侧退出。",
                    "失败例：中途落带下（≥2 足地面）。",
                    "本卡差异：窄带接触 + 无触地 + 南进北出。"],
        "fail": ["失败例：中途落带下（≥2 足地面）。",
                 "对照 success 卡：路径相同，但轨迹中段出现地面足。",
                 "本卡差异：窄带接触 + 无触地 + 南进北出。"],
    },
    "gravel_pit": {
        "success": ["成功：从西侧 1 m 短边进入、经 L 形坑体、从北侧 1 m 短边离开；坑内≥3 次 gravel 接触。",
                    "长边（南侧/东侧 2 m 边）进出非法；出坑后落到地面不判罚。",
                    "本卡差异：入口/出口必须是两条 1 m 短边（西 + 北），不能直穿长边/缺口。"],
        "fail": ["失败例：从南侧 2 m 长边进入（wrong side），即使穿过坑体也不成立。",
                 "对照 success 卡：路径相似，但入口是长边而不是 1 m 短边。",
                 "本卡差异：入口/出口必须是两条 1 m 短边（西 + 北），不能直穿长边/缺口。"],
    },
    "t_stairs": {
        "success": ["成功：单次连续跨越：s 上→top→e 下（两条完整臂），无漏级、无反向乱序，任意臂无缺级。",
                    "失败例：只走一条臂（partial 50）、缺级、或同一次尝试里分两段完成两臂（合并 partial）。",
                    "本卡差异：完整臂数 + 连续性；不是只看是否碰到台阶。"],
        "fail": ["失败例：只走一条臂（partial 50）、缺级、或同一次尝试里分两段完成两臂（合并 partial）。",
                 "对照 success 卡：同样接触台阶，但臂证据不完整/不连续。",
                 "本卡差异：完整臂数 + 连续性；不是只看是否碰到台阶。"],
    },
    "slope": {
        "success": ["成功：在两侧坡面上沿 3 m 长边方向（本场地为 y 方向）累计行走 ≥1.0 m，并合法退出。",
                    "沿母线方向走时 base 高度 z 近似常数（不要求爬升到坡顶）；两侧斜坡合计距离。",
                    "失败例：坡面接触距离不足 1.0 m，或途中 ≥2 足触地。"],
        "fail": ["失败例：坡面接触距离不足 1.0 m（沿 3 m 长边方向累计），或途中 ≥2 足触地。",
                 "对照 success 卡：路径更长/沿长边方向位移 ≥1 m；z 不需要上升。",
                 "本卡差异：沿 3 m 长边方向的累计位移量，不是高度上升量。"],
    },
    "slalom": {
        "success": ["成功：A/B 入口 → 4 根杆按顺序 → 指定拐角 → 出口；不提前进入未来杆圆、不提前出区。",
                    "失败例：漏杆/乱序/提前碰未来杆/未到拐角。",
                    "本卡差异：杆的先后顺序与拐角，不是有没有碰到杆。"],
        "fail": ["失败例：漏杆/乱序/提前碰未来杆/未到拐角。",
                 "对照 success 卡：轨迹相同但顺序不同（或提前碰未来杆）。",
                 "本卡差异：杆的先后顺序与拐角，不是有没有碰到杆。"],
    },
}


def _part1_rulecards(out_dir: Path) -> list[dict]:
    from comp_part1_judge import Part1JudgeV2, SLALOM_CORNER, SLALOM_POSTS, ZONES
    records = []
    for task in sorted(RULE_P1):
        geoms = _world_footprints(SCENE_P1, P1_GEOM_PREFIXES[task])
        if task == "slalom":
            geoms = [{"kind": "circle", "c": p, "r": 0.12, "name": "post", "z": 0.0}
                     for p in SLALOM_POSTS]
            geoms.append({"kind": "circle", "c": SLALOM_CORNER, "r": 0.12, "name": "corner", "z": 0.0})
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
            detail = st.get("detail") or {}
            detail_lines = [f"score={st['score']} reason={st.get('reason') or '-'}",
                            "detail=" + json.dumps(detail, ensure_ascii=False),
                            "samples=" + json.dumps([{k: v for k, v in smp.items() if k != "tags"} for smp in samples], ensure_ascii=False)]
            want = "canonical success path" if expect else "rule-violating path"
            svg = out_dir / f"rule_p1_{task}_{key}.svg"
            _svg_path_card(svg, f"Part1 rulecard: {task} ({want})",
                           "top-down x-y path (geometry footprints) + base/bar height profile; labels = foot surface tags",
                           samples, verdict, detail_lines,
                           zones=[(ZONES[task][0], ZONES[task][1], ZONES[task][2], ZONES[task][3],
                                   f"ZONES[{task}]")],
                           geoms=geoms, key_lines=P1_KEY[task][key])
            records.append({
                "trial_id": None, "kind": "part1_rulecard", "obstacle": task, "media_type": "svg",
                "video": str(svg), "judge": {"status": verdict, "score": float(st["score"]),
                                             "reason": st.get("reason") or "", "detail": detail},
                "human": {"success": None, "failure_reason": None, "judge_verdict_correct": None},
                "note": f"rulecard：{want}；看图/高度曲线判断应 success/fail，再判 judge 是否正确（差异点见卡片 KEY RULE）",
            })
    return records


P2_PREFIXES = ("platform", "stair", "slope", "wall", "trench", "plum", "ground_left", "ground_right")
P2_KEY = {
    "high_platform": ["成功：踩上平台（platform tag）、x∈goal_x、z≥top_z+0.38、无地面足、保持 hold_s。",
                      "失败：在地面高度通过、未进入 goal_x 或 z 不足。"],
    "stairs": ["成功：踩台阶（stairs tag）、x≥goal_x_min、z≥top_z+0.38、无地面足、保持 hold_s。",
               "失败：z 不足/未到 goal_x/仍在地面。"],
    "slope": ["成功：坡面 tag、x≥goal_x_min、z≥rise_z+0.38、无地面足、保持 hold_s。",
              "失败：高度不足或未越过 goal_x。"],
    "high_wall": ["成功：墙接触 + 越过 wall_x + x≥goal_x_min + 近墙最大 z≥max(wall_h+0.10,0.55)。",
                  "失败：无墙接触/未爬高/未越过 goal_x。"],
    "trench": ["成功：跨过沟（近/远边都跨越）、x≥goal_x_min、z≥min_z、lane 内。",
               "失败：掉进沟（z 过低）或未跨过。"],
    "plum": ["成功：踩梅花桩 tag、x≥goal_x_min、z≥goal_z_min、无地面足、保持 hold_s。",
             "失败：z 不足/未到 goal_x/仍在地面。"],
}


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
                   {"x": gx - 0.1, "z": 0.5, "tags": []},
                   {"x": gx + 0.4, "z": 0.5, "tags": []},
                   {"x": gmin, "z": 0.5, "tags": []},
                   {"x": gmin, "z": 0.5, "tags": []},
                   {"x": gmin, "z": 0.5, "tags": []}]
            if not success:
                seq = [{"x": gx - half - 0.5, "z": 0.5, "tags": []},
                       {"x": gx, "z": 0.1, "tags": []}]
        elif kind == "plum":
            gx = float(j["goal_x_min"]) + 0.2
            z = float(j["goal_z_min"]) + 0.1
            y = float(j.get("lane_y", 0.4))
            seq = [{"x": 0.4, "z": 0.6, "tags": []},
                   {"x": 2.0, "z": z, "tags": ["plum"]},
                   {"x": gx, "z": z, "tags": ["plum"]},
                   {"x": gx, "z": z, "tags": ["plum"]},
                   {"x": gx, "z": z, "tags": ["plum"]}]
            for smp in seq: smp["y"] = y
            if not success:
                seq = [{"x": 0.4, "z": 0.6, "tags": []},
                       {"x": 2.8, "z": 0.42, "tags": ["plum"]},
                       {"x": 2.8, "z": 0.42, "tags": ["plum"]}]
                for smp in seq: smp["y"] = y
        else:
            seq = []
        return seq

    def _z_lines(kind: str, j: dict) -> list[tuple]:
        if kind == "platform":
            return [(float(j["top_z"]) + 0.38, "top_z+0.38")]
        if kind == "stairs":
            return [(float(j["top_z"]) + 0.38, "top_z+0.38")]
        if kind == "slope":
            return [(float(j["rise_z"]) + 0.38, "rise_z+0.38")]
        if kind == "wall":
            return [(max(float(j["wall_h"]) + 0.10, 0.55), "max(wall_h+0.10,0.55)")]
        if kind == "gap":
            return [(float(j.get("min_z", 0.3)), "min_z")]
        if kind == "plum":
            return [(float(j["goal_z_min"]), "goal_z_min")]
        return []

    def _goals(kind: str, j: dict, lane: float) -> list[tuple]:
        lo = float(j.get("lane_y", 0.0)) - lane
        hi = float(j.get("lane_y", 0.0)) + lane
        if kind == "platform":
            gx = j.get("goal_x", [2.0, 3.0])
            return [(float(gx[0]), float(gx[1]), lo, hi, "goal_x")] 
        if kind in ("stairs", "slope", "plum", "wall", "gap"):
            gmin = float(j.get("goal_x_min", 0.0))
            return [(gmin, gmin + 1.5, lo, hi, "x>=goal_x_min")]
        return []

    for cat in sorted(by_cat):
        entries = sorted(by_cat[cat], key=lambda x: float(x["level"]))
        entry = entries[-1]
        geoms = _world_footprints(ROOT / entry["scene"], P2_PREFIXES)
        for want_success in (True, False):
            samples = _samples(entry["judge"]["kind"], entry["judge"], want_success)
            if not samples:
                continue
            judge = Part2JudgeV2(entry)
            rep = None
            for i, smp in enumerate(samples):
                legs = {leg: set(smp.get("tags") or []) for leg in LEGS}
                rep = judge.update(i * 0.1, (smp["x"], smp.get("y", 0.0), smp["z"]), 5.0,
                                   foot_tags=legs, ground_feet=set())
            rep = rep or judge.finalize("timeout")
            ok = rep.get("status") == "success"
            if ok != want_success:
                print(f"  !! rulecard mismatch {cat} want_success={want_success} got={rep.get('status')}", flush=True)
                continue
            score = score_for_level(contract["parts"]["part2"], cat, entry["level"]) if ok else 0
            zl = _z_lines(entry["judge"]["kind"], entry["judge"])
            goals = _goals(entry["judge"]["kind"], entry["judge"], float(entry["judge"].get("lane_half_width", 0.7)))
            detail_lines = [f"score={score} status={rep.get('status')} reason={rep.get('reason') or '-'}",
                            "detail=" + json.dumps(rep.get("detail") or {}, ensure_ascii=False),
                            "judge_spec=" + json.dumps(entry["judge"], ensure_ascii=False)]
            svg = out_dir / f"rule_p2_{cat}_{'success' if want_success else 'fail'}.svg"
            _svg_path_card(svg, f"Part2 rulecard: {cat} level {entry['level']}{entry.get('unit','')}",
                           "top-down x-y path with level geometry + base height profile; labels = surface tags",
                           samples, "success" if ok else "fail", detail_lines,
                           geoms=geoms, key_lines=P2_KEY[cat], z_lines=zl, goals=goals)
            records.append({
                "trial_id": None, "kind": "part2_rulecard", "category": cat,
                "level": entry["level"], "unit": entry.get("unit"), "media_type": "svg",
                "video": str(svg), "judge": {"status": "success" if ok else "fail",
                                             "score": float(score),
                                             "reason": rep.get("reason") or "", "detail": rep.get("detail") or {}},
                "human": {"success": None, "failure_reason": None, "judge_verdict_correct": None},
                "note": "rulecard：看图/高度曲线判断应 success/fail，再判 judge 是否正确（差异点见卡片 KEY RULE）",
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
                "route": info.get("route") or None,
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
