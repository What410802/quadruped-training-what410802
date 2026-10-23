"""Render deterministic trunk-only reference trajectories (C2 training guidance).

For each Part 1 obstacle and Part 2 category this script:
  - loads the MuJoCo scene (robot geoms hidden; terrain/obstacles visible);
  - animates a semi-transparent trunk-only ghost (box + orientation axes + trail)
    along a hand-designed reference path with a speed/timing profile (6 DoF pose + speed);
  - renders two views side-by-side: third-person tracking view + top-down view;
  - writes an mp4 per task plus a JSON plan (waypoints, speed, durations).

The references are *guidance/targets*, not physically validated trajectories; they exist so
the user can inspect the intended trunk motion before we define the training reward and
before any training run.  No training is started by this script.

Usage (from MyMonoRepo.d):
  pixi run python @20261019_locomotion/scripts/agent_scripts/visualize_trunk_reference.py
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

import mujoco
import numpy as np

ROOT = Path("@20261019_locomotion")
SCENE_P1 = ROOT / "assets/terrain/part1/part1_eval_scene_v2.xml"
LEVELS_JSON = ROOT / "config/part2-levels.json"
TRUNK_SIZE = (0.225, 0.075, 0.080)   # approximate trunk bbox half-sizes from black MJCF


def _wrap(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


def _rot_yaw_pitch_roll(yaw_deg: float, pitch_deg: float, roll_deg: float) -> np.ndarray:
    y, p, r = np.radians([yaw_deg, pitch_deg, roll_deg])
    Rz = np.array([[math.cos(y), -math.sin(y), 0], [math.sin(y), math.cos(y), 0], [0, 0, 1]])
    Ry = np.array([[math.cos(p), 0, math.sin(p)], [0, 1, 0], [-math.sin(p), 0, math.cos(p)]])
    Rx = np.array([[1, 0, 0], [0, math.cos(r), -math.sin(r)], [0, math.sin(r), math.cos(r)]])
    return Rz @ Ry @ Rx


def _smooth(t: float) -> float:
    """smoothstep interpolation parameter in [0,1]."""
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def build_samples(waypoints: list[dict]) -> list[dict]:
    """Interpolate a waypoint list into 50 Hz pose/speed samples.

    waypoint keys: x,y,z, yaw, pitch, roll (deg), speed (m/s), hold (s, optional)
    """
    out: list[dict] = []
    t = 0.0
    dt = 0.02
    for i, wp in enumerate(waypoints):
        hold = float(wp.get("hold", 0.0))
        if hold > 0:
            for _ in range(int(round(hold / dt))):
                out.append({"t": t, "x": wp["x"], "y": wp["y"], "z": wp["z"],
                            "yaw": wp.get("yaw", 0.0), "pitch": wp.get("pitch", 0.0),
                            "roll": wp.get("roll", 0.0), "speed": 0.0})
                t += dt
        if i == len(waypoints) - 1:
            break
        nxt = waypoints[i + 1]
        speed = float(wp.get("speed", 0.4))
        dist = math.dist((wp["x"], wp["y"], wp["z"]), (nxt["x"], nxt["y"], nxt["z"]))
        dur = max(0.2, dist / max(0.05, speed)) if wp.get("speed", 0.4) is not None else 0.5
        n = max(1, int(round(dur / dt)))
        for k in range(n):
            u = _smooth(k / n)
            out.append({
                "t": t,
                "x": wp["x"] + (nxt["x"] - wp["x"]) * u,
                "y": wp["y"] + (nxt["y"] - wp["y"]) * u,
                "z": wp["z"] + (nxt["z"] - wp["z"]) * u,
                "yaw": wp.get("yaw", 0.0) + _wrap(math.radians((nxt.get("yaw", 0.0) - wp.get("yaw", 0.0)))) * 180.0 / math.pi * u,
                "pitch": wp.get("pitch", 0.0) + (nxt.get("pitch", 0.0) - wp.get("pitch", 0.0)) * u,
                "roll": wp.get("roll", 0.0) + (nxt.get("roll", 0.0) - wp.get("roll", 0.0)) * u,
                "speed": speed if k < n - 1 else float(nxt.get("speed", 0.0)),
            })
            t += dt
    return out


# ---------------------------------------------------------------- reference bank
def _wp(x, y, z, yaw=0.0, pitch=0.0, roll=0.0, speed=0.4, hold=0.0) -> dict:
    return {"x": x, "y": y, "z": z, "yaw": yaw, "pitch": pitch, "roll": roll,
            "speed": speed, "hold": hold}


P1_REFERENCES: dict[str, list[dict]] = {
    "height_bar": [
        _wp(5.7, -10.6, 0.42, yaw=90, speed=0.40),
        _wp(5.7, -9.7, 0.30, yaw=90, speed=0.30),
        _wp(5.7, -9.2, 0.24, yaw=90, speed=0.25),   # crouch: trunk top ~0.32 < bar 0.325
        _wp(5.7, -8.8, 0.24, yaw=90, speed=0.25),
        _wp(5.7, -8.2, 0.32, yaw=90, speed=0.30),
        _wp(5.7, -7.9, 0.42, yaw=90, speed=0.20),
    ],
    "high_wall": [
        _wp(1.8, -8.0, 0.42, yaw=90, speed=0.40),
        _wp(1.8, -7.55, 0.45, yaw=90, speed=0.35),
        _wp(1.8, -7.2, 0.60, yaw=90, pitch=-10, speed=0.30),
        _wp(1.8, -7.0, 0.66, yaw=90, pitch=0, speed=0.25),
        _wp(1.8, -6.8, 0.66, yaw=90, pitch=0, speed=0.25),   # level body over the wall top
        _wp(1.8, -6.55, 0.55, yaw=90, pitch=6, speed=0.30),
        _wp(1.8, -6.0, 0.42, yaw=90, speed=0.20),
    ],
    "bridge_blocks": [
        _wp(1.8, -1.5, 0.42, yaw=90, speed=0.35),   # start at the ramp root (south of platform)
        _wp(1.8, -1.0, 0.48, yaw=90, speed=0.30),
        _wp(1.8, -0.4, 0.58, yaw=90, speed=0.25),
        _wp(1.8, 0.0, 0.60, yaw=90, speed=0.20),    # west platform
        _wp(2.05, 0.0, 0.60, yaw=45, speed=0.20),   # turn east on the platform
        _wp(2.4, 0.0, 0.60, yaw=0, speed=0.25),
        _wp(3.3, 0.0, 0.60, yaw=0, speed=0.30),
        _wp(4.5, 0.0, 0.60, yaw=0, speed=0.30),
        _wp(5.4, -0.4, 0.60, yaw=-20, speed=0.25),
        _wp(5.7, -0.5, 0.60, yaw=0, speed=0.15),    # stop on the east platform
    ],
    "bridge_bands": [
        _wp(5.7, -4.2, 0.42, yaw=90, speed=0.35),   # ground south of the low platform
        _wp(5.7, -3.75, 0.52, yaw=90, speed=0.30),
        _wp(5.7, -3.5, 0.60, yaw=90, speed=0.22),   # low platform (top 0.2)
        _wp(5.7, -2.9, 0.60, yaw=90, speed=0.30),
        _wp(5.7, -2.25, 0.60, yaw=90, speed=0.30),
        _wp(5.7, -1.6, 0.60, yaw=90, speed=0.30),
        _wp(5.7, -1.0, 0.60, yaw=90, speed=0.20),   # end of the band section (no higher z bump)
    ],
    "gravel_pit": [
        _wp(3.6, -12.5, 0.42, yaw=0, speed=0.35),
        _wp(4.3, -12.5, 0.55, yaw=0, speed=0.30),
        _wp(4.8, -12.5, 0.55, yaw=0, speed=0.25),
        _wp(5.25, -12.5, 0.55, yaw=0, speed=0.22),
        # smooth vehicle-like left turn inside the pit (no in-place yaw)
        _wp(5.6, -12.4, 0.55, yaw=45, speed=0.20),
        _wp(5.8, -12.1, 0.55, yaw=90, speed=0.22),
        _wp(5.8, -11.4, 0.55, yaw=90, speed=0.30),
        _wp(5.8, -10.7, 0.42, yaw=90, speed=0.20),
    ],
    "t_stairs": [
        _wp(1.8, -5.4, 0.42, yaw=90, speed=0.30),
        _wp(1.8, -4.95, 0.52, yaw=90, speed=0.25),
        _wp(1.8, -4.6, 0.62, yaw=90, speed=0.22),
        _wp(1.8, -4.2, 0.76, yaw=90, speed=0.22),
        _wp(1.8, -3.85, 0.84, yaw=90, speed=0.18),
        _wp(1.8, -3.5, 0.84, yaw=90, speed=0.15),
        # smooth right turn on the top platform, then descend the east arm
        _wp(1.9, -3.25, 0.84, yaw=60, speed=0.15),
        _wp(2.1, -3.3, 0.82, yaw=30, speed=0.15),
        _wp(2.35, -3.5, 0.76, yaw=0, speed=0.18),
        _wp(2.8, -3.5, 0.60, yaw=0, speed=0.25),
        _wp(3.3, -3.5, 0.42, yaw=0, speed=0.20),
    ],
    "slope": [
        # walk in the middle of the west slope panel (x≈4.7), along the 3 m long edge (y)
        _wp(4.7, -6.9, 0.42, yaw=90, speed=0.40),
        _wp(4.7, -6.5, 0.56, yaw=90, speed=0.40),
        _wp(4.7, -5.7, 0.56, yaw=90, speed=0.40),
        _wp(4.7, -4.9, 0.56, yaw=90, speed=0.40),
        _wp(4.7, -4.2, 0.56, yaw=90, speed=0.35),
        _wp(4.7, -3.8, 0.56, yaw=90, speed=0.20),
    ],
    "slalom": [
        _wp(1.8, -10.0, 0.42, yaw=-75, speed=0.35),
        _wp(2.25, -10.5, 0.42, yaw=-100, speed=0.35),  # right of post 0
        _wp(1.35, -11.5, 0.42, yaw=-110, speed=0.35),  # left of post 1
        _wp(2.25, -12.5, 0.42, yaw=-60, speed=0.35),   # right of post 2
        _wp(1.55, -12.75, 0.42, yaw=-160, speed=0.30),  # corner checkpoint
        _wp(2.25, -12.95, 0.42, yaw=-10, speed=0.30),  # around the south side of post 3
        _wp(2.95, -12.85, 0.42, yaw=15, speed=0.30),
        _wp(3.2, -12.5, 0.42, yaw=50, speed=0.20),     # end circle
    ],
}

P2_REFERENCES: dict[str, list[dict]] = {
    "high_platform": [
        _wp(0.0, 0.0, 0.42, speed=0.40),
        _wp(1.9, 0.0, 0.48, speed=0.35),
        _wp(2.4, 0.0, 0.95, pitch=-12, speed=0.25),
        _wp(2.7, 0.0, 0.95, pitch=0, speed=0.15),   # level body on the platform top
    ],
    "stairs": [
        _wp(0.0, 0.0, 0.42, speed=0.40),
        _wp(1.7, 0.0, 0.52, speed=0.30),
        _wp(2.2, 0.0, 0.65, pitch=-12, speed=0.25),
        _wp(2.6, 0.0, 0.78, pitch=-8, speed=0.22),
        _wp(3.9, 0.0, 0.78, pitch=0, speed=0.20),   # on the top platform
    ],
    "slope": [
        _wp(0.0, 0.0, 0.42, speed=0.40),
        _wp(1.6, 0.0, 0.52, speed=0.35),
        _wp(2.2, 0.0, 1.05, pitch=-18, speed=0.25),
        _wp(2.9, 0.0, 1.35, pitch=-10, speed=0.22),
        _wp(4.1, 0.0, 1.50, pitch=0, speed=0.15),   # middle of the top plane
    ],
    "high_wall": [
        _wp(0.0, 0.0, 0.42, speed=0.40),
        _wp(2.0, 0.0, 0.48, speed=0.35),
        _wp(2.5, 0.0, 0.68, pitch=-15, speed=0.28),
        _wp(2.9, 0.0, 0.68, pitch=0, speed=0.25),
        _wp(3.3, 0.0, 0.48, speed=0.20),
    ],
    "trench": [
        _wp(0.0, 0.0, 0.42, speed=0.45),
        _wp(2.1, 0.0, 0.50, speed=0.50),
        _wp(2.5, 0.0, 0.62, pitch=-8, speed=0.55),  # hop/gap crossing
        _wp(2.9, 0.0, 0.50, pitch=0, speed=0.45),
        _wp(3.3, 0.0, 0.42, speed=0.20),
    ],
    "plum": [
        _wp(0.4, 0.4, 0.42, speed=0.35),
        _wp(1.0, 0.4, 0.60, pitch=-6, speed=0.25),
        _wp(1.6, 0.4, 0.65, speed=0.25),
        _wp(2.2, 0.4, 0.65, speed=0.25),
        _wp(2.8, 0.4, 0.65, speed=0.15),
    ],
}


def _scene_top_z(scene_path: Path, x: float, y: float) -> float | None:
    model = mujoco.MjModel.from_xml_path(str(scene_path))
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    p = np.array([x, y, 3.0], dtype=np.float64)
    v = np.array([0.0, 0.0, -1.0], dtype=np.float64)
    g = np.array([-1], dtype=np.int32)
    n = np.zeros(3)
    dist = mujoco.mj_ray(model, data, p, v, None, 1, -1, g, n)
    if dist < 0:
        return None
    return float(3.0 - dist)


def _adjust_p2_reference(cat: str, entry: dict, wps: list[dict]) -> list[dict]:
    """Follow the level surface with the trunk (no artificial triangular bumps).

    - high_platform / stairs / slope / plum: raycast the level scene at each waypoint and
      set the trunk base to surface_top + 0.42 m; pitch is derived from the local slope.
    - trench: keep flat (ground level) across the gap; no hop.
    - high_wall: keep the hand-designed climb profile (raycast top would be the wall top).
    """
    scene = ROOT / entry["scene"]
    if cat == "trench":
        for w in wps:
            w["z"] = 0.42
            w["pitch"] = 0.0
        return wps
    if cat == "high_wall":
        return wps
    for w in wps:
        top = _scene_top_z(scene, w["x"], w["y"])
        if top is not None and top > 0.03:
            w["z"] = round(top + 0.42, 3)
    # smooth orientation from local height gradient along the path
    for i, w in enumerate(wps):
        if i + 1 >= len(wps):
            w["pitch"] = 0.0
            continue
        nxt = wps[i + 1]
        dh = math.hypot(nxt["x"] - w["x"], nxt["y"] - w["y"])
        if dh > 1e-6:
            w["pitch"] = round(max(-25.0, min(25.0,
                              -math.degrees(math.atan2(nxt["z"] - w["z"], dh)))), 1)
        else:
            w["pitch"] = 0.0
    return wps


def _renderer(model, width=560, height=420):
    r = mujoco.Renderer(model, height=height, width=width)
    opt = mujoco.MjvOption()
    opt.geomgroup[:] = 0
    opt.geomgroup[0] = 1   # world/terrain only; robot geoms are group 3
    return r, opt


def _add_ghost(scene, pos, R, rgba=(0.15, 0.5, 1.0, 0.45)):
    if scene.ngeom >= len(scene.geoms):
        return
    g = scene.geoms[scene.ngeom]
    mujoco.mjv_initGeom(g, mujoco.mjtGeom.mjGEOM_BOX,
                        np.array(TRUNK_SIZE, dtype=np.float64), np.asarray(pos, dtype=np.float64),
                        np.asarray(R, dtype=np.float64).reshape(-1), np.asarray(rgba, dtype=np.float32))
    scene.ngeom += 1


def _add_line(scene, a, b, rgba=(0.1, 0.8, 0.9, 0.25), width=0.008):
    if scene.ngeom >= len(scene.geoms):
        return
    g = scene.geoms[scene.ngeom]
    mujoco.mjv_initGeom(g, mujoco.mjtGeom.mjGEOM_CAPSULE,
                        np.array([width, width, 0.0]), np.zeros(3), np.eye(3).reshape(-1),
                        np.asarray(rgba, dtype=np.float32))
    mujoco.mjv_connector(g, mujoco.mjtGeom.mjGEOM_CAPSULE, width,
                         np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64))
    scene.ngeom += 1


def _add_arrow(scene, start, vec, rgba, width=0.01):
    if scene.ngeom >= len(scene.geoms):
        return
    if np.linalg.norm(vec) < 1e-4:
        return
    g = scene.geoms[scene.ngeom]
    mujoco.mjv_initGeom(g, mujoco.mjtGeom.mjGEOM_ARROW,
                        np.array([width, width, 0.0]), np.zeros(3), np.eye(3).reshape(-1),
                        np.asarray(rgba, dtype=np.float32))
    mujoco.mjv_connector(g, mujoco.mjtGeom.mjGEOM_ARROW, width,
                         np.asarray(start, dtype=np.float64),
                         np.asarray(start, dtype=np.float64) + np.asarray(vec, dtype=np.float64))
    scene.ngeom += 1


def _render_task(scene_path: Path, samples: list[dict], out_mp4: Path,
                 title: str, width=560, height=420) -> dict:
    model = mujoco.MjModel.from_xml_path(str(scene_path))
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    renderer, opt = _renderer(model, width, height)
    side_cam = mujoco.MjvCamera()
    side_cam.distance = 2.8
    side_cam.elevation = -25.0
    side_cam.azimuth = 135.0
    top_cam = mujoco.MjvCamera()
    top_cam.elevation = -90.0
    top_cam.azimuth = 90.0
    # path bounds
    xs = [s["x"] for s in samples]
    ys = [s["y"] for s in samples]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    span = max(max(xs) - min(xs), max(ys) - min(ys), 1.0)
    top_cam.lookat[:] = (cx, cy, 0.1)
    top_cam.distance = span * 1.25 + 1.0
    step = max(1, len(samples) // 120)
    trail_pts = [(s["x"], s["y"], s["z"]) for s in samples[::step]]
    tmp = Path(tempfile.mkdtemp(prefix="trunk_ref_"))
    try:
        for i, smp in enumerate(samples):
            R = _rot_yaw_pitch_roll(smp["yaw"], smp["pitch"], smp["roll"])
            pos = np.array([smp["x"], smp["y"], smp["z"]])
            # third-person view
            side_cam.lookat[:] = (pos[0] + 0.4 * R[0, 0], pos[1] + 0.4 * R[1, 0], max(0.2, pos[2] - 0.05))
            renderer.update_scene(data, camera=side_cam, scene_option=opt)
            for j in range(0, min(i, len(trail_pts) - 1), 3):
                _add_line(renderer.scene, trail_pts[j], trail_pts[j + 1])
            _add_ghost(renderer.scene, pos, R)
            _add_arrow(renderer.scene, pos, R[:, 0] * 0.28, (0.9, 0.1, 0.1, 0.9))
            _add_arrow(renderer.scene, pos, np.array([0, 0, 0.28]), (0.1, 0.2, 0.9, 0.9))
            f_side = renderer.render().copy()
            # top-down view
            renderer.update_scene(data, camera=top_cam, scene_option=opt)
            for j in range(0, min(i, len(trail_pts) - 1), 3):
                _add_line(renderer.scene, trail_pts[j], trail_pts[j + 1])
            _add_ghost(renderer.scene, pos, R)
            _add_arrow(renderer.scene, pos, R[:, 0] * 0.28, (0.9, 0.1, 0.1, 0.9))
            f_top = renderer.render().copy()
            frame = np.concatenate([f_side, f_top], axis=1)
            Path(tmp / f"f{i:05d}.ppm").write_bytes(
                f"P6\n{frame.shape[1]} {frame.shape[0]}\n255\n".encode() + frame.tobytes())
        renderer.close()
        out_mp4.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                        "-framerate", "50", "-i", str(tmp / "f%05d.ppm"),
                        "-pix_fmt", "yuv420p", str(out_mp4)], check=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return {"title": title, "frames": len(samples),
            "duration_s": round(samples[-1]["t"] if samples else 0.0, 2),
            "video": str(out_mp4)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=Path, default=Path("../prep.d/videos/trunk_ref"))
    ap.add_argument("--plan", type=Path, default=Path("../prep.d/results/trunk_ref_plan.json"))
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--speed-scale", type=float, default=1.35,
                    help="scale all reference speeds (reduces wasted reference time)")
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    plan: dict = {"part1": {}, "part2": {}, "speed_scale": args.speed_scale}
    def _scaled(wps):
        out = []
        for w in wps:
            w = dict(w)
            w["speed"] = round(float(w.get("speed", 0.4)) * args.speed_scale, 3)
            out.append(w)
        return out
    for name, wps in P1_REFERENCES.items():
        if args.only and name not in args.only:
            continue
        wps = _scaled(wps)
        samples = build_samples(wps)
        out = args.out_dir / f"p1_{name}.mp4"
        info = _render_task(SCENE_P1, samples, out, f"Part1 {name}")
        plan["part1"][name] = {"waypoints": wps, **info}
        print("wrote", out, f"({info['duration_s']}s)", flush=True)
    levels = json.loads(LEVELS_JSON.read_text(encoding="utf-8"))["levels"]
    by_cat: dict[str, list[dict]] = {}
    for e in levels:
        by_cat.setdefault(e["category"], []).append(e)
    for cat, wps in P2_REFERENCES.items():
        if args.only and cat not in args.only:
            continue
        entry = sorted(by_cat[cat], key=lambda x: float(x["level"]))[min(1, len(by_cat[cat]) - 1)]
        scene = ROOT / entry["scene"]
        wps = _adjust_p2_reference(cat, entry, _scaled(wps))
        samples = build_samples(wps)
        out = args.out_dir / f"p2_{cat}.mp4"
        info = _render_task(scene, samples, out, f"Part2 {cat}")
        plan["part2"][cat] = {"level": entry["level"], "unit": entry.get("unit"),
                              "scene": entry["scene"], "waypoints": wps, **info}
        print("wrote", out, f"({info['duration_s']}s)", flush=True)
    args.plan.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("plan ->", args.plan)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
