"""Conformance tests for comp_part1_judge.py V2.1 (no MuJoCo needed).

Covers the G1 audit counterexamples and the 2026-10-22 BYOK pre-audit blockers:
- six exit-side spoof paths must not score;
- approach ground (before touching the obstacle) must not trigger the 1/2-foot rule;
- the 1/2-foot rule fires only after the robot has been fully supported by the obstacle,
  and a failed obstacle can be retried within the same attempt;
- T-stairs explicit arms and per-level history, partial score separated from full;
- height bar: post/beam touch is not failure, beam drop is, gate must be crossed through
  the opening (no "outside then lateral" trick);
- slope: projection on the long axis, boundary graze soft-resets, no lateral-wiggle spoof;
- gravel pit: both short edges legal, long-edge genuine attempt fails, ground rule gated;
- bridges: real surface tags, platform evidence, instant ground failure after support;
- high wall: real wall-plane crossing with climb evidence, no ground bypass;
- slalom: both directions, corner at the turn, end area last, alternation;
- scene v2 real geom names are all mapped to judge surface tags (no silent missing tags).

Run: python3 scripts/agent_scripts/comp_judge_conformance.py
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from comp_part1_judge import AttemptManager, Part1JudgeV2  # noqa: E402
from comp_part1_geom_tags import GEOM_TAGS, is_ground_geom  # noqa: E402

LEGS = ("FL", "FR", "RL", "RR")


def feed(judge: Part1JudgeV2, samples, *, dt: float = 0.02) -> dict:
    report = None
    for i, s in enumerate(samples):
        tags = {leg: set(s.get("tags", [])) for leg in LEGS}
        report = judge.update(i * dt, (s["x"], s["y"], s.get("z", 0.45)), s.get("yaw", 0.0),
                              foot_tags=tags, ground_feet=set(s.get("ground", [])),
                              bar_z=s.get("bar_z"))
    return report


def st(report: dict, name: str) -> dict:
    return report["states"][name]


def assert_status(report, name, status, why=""):
    s = st(report, name)
    assert s["status"] == status, f"{name}: expected {status}, got {s['status']} ({s['reason']}) [{why}]"


def assert_not_success(report, name, why=""):
    assert st(report, name)["status"] != "success", f"{name}: must not succeed [{why}]"


def assert_failed(report, name, why=""):
    s = st(report, name)
    assert s["failures"] or s["status"] == "fail", f"{name}: expected a recorded failure, got {s} [{why}]"


# ---------------------------------------------------------------- spoof / approach

def test_spoof_exit_positions():
    cases = [
        ("bridge_blocks", [(6.0, 0.0), (6.4, 0.0)]),
        ("bridge_bands", [(5.7, -0.9), (5.7, -0.7)]),
        ("height_bar", [(5.7, -8.5), (5.7, -8.3)]),
        ("high_wall", [(1.8, -6.2), (1.8, -6.0)]),
        ("gravel_pit", [(5.5, -11.0), (5.5, -10.85)]),
        ("t_stairs", [(1.8, -2.2), (1.8, -2.05)]),
        ("slope", [(6.0, -5.0), (6.45, -5.0)]),
        ("slalom", [(3.2, -12.5), (3.6, -12.5)]),
    ]
    for name, path in cases:
        rep = feed(Part1JudgeV2(), [{"x": x, "y": y} for x, y in path])
        assert_not_success(rep, name, f"spoof path {path}")
    print("spoof exit positions: OK -> all non-success")


def test_approach_ground_is_not_failure():
    """Walking on the floor before touching the obstacle must not trigger the 1/2 rule."""
    cases = [
        ("bridge_blocks", [(0.8, 0.0), (1.3, 0.0)]),
        ("gravel_pit", [(5.0, -13.6), (5.0, -13.2)]),
        ("t_stairs", [(1.8, -5.4), (1.8, -4.9)]),
        ("slope", [(3.6, -5.0), (4.5, -5.0)]),
    ]
    for name, path in cases:
        rep = feed(Part1JudgeV2(),
                   [{"x": x, "y": y, "ground": ["FL", "FR", "RL", "RR"]} for x, y in path])
        failures = st(rep, name)["failures"]
        assert not failures, f"{name}: approach ground must not fail: {failures}"
        assert_not_success(rep, name, "approach only")
    print("approach ground: OK -> no false failure")


def test_failure_can_be_retried_and_success_is_final():
    judge = Part1JudgeV2()
    rep = feed(judge, [
        {"x": 0.5, "y": 0.0},
        {"x": 1.35, "y": 0.0, "tags": ["platform_left"]},
        {"x": 1.6, "y": 0.0, "tags": ["platform_left"]},
        {"x": 2.0, "y": 0.0, "tags": ["bridge"]},
        {"x": 2.3, "y": 0.0, "tags": ["bridge"], "ground": ["FL", "FR"]},
    ])
    assert_failed(rep, "bridge_blocks", "ground rule after support")
    legal = [
        {"x": 0.5, "y": 0.0},
        {"x": 1.35, "y": 0.0, "tags": ["platform_left"]},
        {"x": 2.2, "y": 0.0, "tags": ["bridge"]},
        {"x": 3.2, "y": 0.0, "tags": ["bridge"]},
        {"x": 4.2, "y": 0.0, "tags": ["bridge"]},
        {"x": 5.2, "y": 0.0, "tags": ["bridge"]},
        {"x": 5.6, "y": 0.0, "tags": ["platform_right"]},
        {"x": 6.4, "y": 0.0, "tags": ["platform_right"]},
    ]
    rep = feed(judge, legal)
    assert_status(rep, "bridge_blocks", "success", "retry after failure")
    print("retry-after-failure: OK")


# ---------------------------------------------------------------- bridges / bar / wall

def test_bridge_ground_and_success():
    judge = Part1JudgeV2()
    rep = feed(judge, [
        {"x": 0.5, "y": 0.0},
        {"x": 1.35, "y": 0.0, "tags": ["platform_left"]},
        {"x": 2.2, "y": 0.0, "tags": ["bridge"]},
        {"x": 3.2, "y": 0.0, "tags": ["bridge"]},
        {"x": 4.2, "y": 0.0, "tags": ["bridge"]},
        {"x": 5.2, "y": 0.0, "tags": ["bridge"]},
        {"x": 5.6, "y": 0.0, "tags": ["platform_right"]},
        {"x": 6.4, "y": 0.0, "tags": ["platform_right"]},
    ])
    assert_status(rep, "bridge_blocks", "success", "legal traversal")
    assert st(rep, "bridge_blocks")["score"] == 100
    print("bridge_blocks: OK legal traversal")


def test_height_bar_touch_drop_and_gate():
    base = [
        {"x": 5.7, "y": -10.4, "bar_z": 0.325},
        {"x": 5.7, "y": -9.5, "bar_z": 0.325},
        {"x": 5.7, "y": -9.0, "bar_z": 0.325},
        {"x": 5.7, "y": -8.5, "bar_z": 0.325},
        {"x": 5.7, "y": -8.2, "bar_z": 0.325},
    ]
    assert_status(feed(Part1JudgeV2(), base), "height_bar", "success", "gate crossing, bar stable")

    dropped = [dict(s, bar_z=(0.20 if i >= 2 else 0.325)) for i, s in enumerate(base)]
    assert_failed(feed(Part1JudgeV2(), dropped), "height_bar", "beam drop")

    # beam already dropped before entering the zone -> cannot succeed on a retry
    pre_drop = [
        {"x": 5.7, "y": -10.8, "bar_z": 0.325},
        {"x": 5.7, "y": -10.2, "bar_z": 0.20},
        {"x": 5.7, "y": -9.5, "bar_z": 0.20},
        {"x": 5.7, "y": -9.0, "bar_z": 0.20},
        {"x": 5.7, "y": -8.5, "bar_z": 0.20},
        {"x": 5.7, "y": -8.2, "bar_z": 0.20},
    ]
    assert_not_success(feed(Part1JudgeV2(), pre_drop), "height_bar", "pre-entry beam drop")

    outside = [
        {"x": 4.6, "y": -10.4, "bar_z": 0.325},
        {"x": 4.6, "y": -9.5, "bar_z": 0.325},
        {"x": 5.7, "y": -9.0, "bar_z": 0.325},
        {"x": 5.7, "y": -8.5, "bar_z": 0.325},
        {"x": 5.7, "y": -8.2, "bar_z": 0.325},
    ]
    assert_not_success(feed(Part1JudgeV2(), outside), "height_bar", "outside-then-lateral")
    print("height_bar: OK touch!=fail / drop=fail / gate crossing required")


def test_high_wall_sideways_climb_and_bypass():
    sideways = [
        {"x": 1.2, "y": -7.0}, {"x": 1.5, "y": -7.0}, {"x": 2.0, "y": -7.0},
        {"x": 2.4, "y": -7.0}, {"x": 2.6, "y": -7.0},
    ]
    assert_not_success(feed(Part1JudgeV2(), sideways), "high_wall", "walked along the wall")

    climb = [
        {"x": 1.8, "y": -7.9},
        {"x": 1.8, "y": -7.4, "z": 0.75, "tags": ["wall"]},
        {"x": 1.8, "y": -7.0, "z": 0.85, "tags": ["wall"]},
        {"x": 1.8, "y": -6.6, "z": 0.75, "tags": ["wall"]},
        {"x": 1.8, "y": -6.0},
    ]
    assert_status(feed(Part1JudgeV2(), climb), "high_wall", "success", "raised crossing")

    bypass = [
        {"x": 1.8, "y": -7.9}, {"x": 1.8, "y": -7.4}, {"x": 1.8, "y": -7.0},
        {"x": 1.8, "y": -6.6}, {"x": 1.8, "y": -6.0},
    ]
    rep = feed(Part1JudgeV2(), bypass)
    assert_not_success(rep, "high_wall", "ground-height crossing")

    # wall-touching at ground height is still not a climb
    wall_touch_ground = [
        {"x": 1.8, "y": -7.9},
        {"x": 1.8, "y": -7.4, "z": 0.45, "tags": ["wall"]},
        {"x": 1.8, "y": -7.0, "z": 0.45, "tags": ["wall"]},
        {"x": 1.8, "y": -6.6, "z": 0.45, "tags": ["wall"]},
        {"x": 1.8, "y": -6.0},
    ]
    assert_not_success(feed(Part1JudgeV2(), wall_touch_ground), "high_wall",
                       "sideways wall touch at ground height")

    # raised crossing outside the actual wall x span [1.30, 2.30] must not count
    outside_x = [
        {"x": 2.7, "y": -7.9},
        {"x": 2.7, "y": -7.4, "z": 0.75},
        {"x": 2.7, "y": -7.0, "z": 0.85},
        {"x": 2.7, "y": -6.6, "z": 0.75},
        {"x": 2.7, "y": -6.0},
    ]
    assert_not_success(feed(Part1JudgeV2(), outside_x), "high_wall",
                       "raised crossing outside wall x span")
    print("high_wall: OK sideways/no-climb/wall-touch/outside-span useless / real crossing succeeds")


# ---------------------------------------------------------------- stairs / slope / gravel

def test_t_stairs_full_partial_and_history():
    full = [
        {"x": 1.8, "y": -5.4},
        {"x": 1.8, "y": -4.9, "tags": ["step:s:1"]},
        {"x": 1.8, "y": -4.6, "tags": ["step:s:2"]},
        {"x": 1.8, "y": -4.3, "tags": ["step:s:3"]},
        {"x": 1.8, "y": -3.8, "tags": ["step:top"]},
        {"x": 2.2, "y": -3.5, "tags": ["step:e:3"]},
        {"x": 2.6, "y": -3.5, "tags": ["step:e:2"]},
        {"x": 2.9, "y": -3.5, "tags": ["step:e:1"]},
        {"x": 3.4, "y": -3.5},
    ]
    rep = feed(Part1JudgeV2(), full)
    assert_status(rep, "t_stairs", "success", "two complete arms")
    assert st(rep, "t_stairs")["score"] == 100
    assert set(st(rep, "t_stairs")["detail"]["arms"]) == {"s", "e"}

    partial = [
        {"x": 1.8, "y": -5.4},
        {"x": 1.8, "y": -4.9, "tags": ["step:s:1"]},
        {"x": 1.8, "y": -4.6, "tags": ["step:s:2"]},
        {"x": 1.8, "y": -4.3, "tags": ["step:s:3"]},
        {"x": 1.8, "y": -3.8, "tags": ["step:top"]},
        {"x": 1.8, "y": -4.3, "tags": ["step:s:3"]},
        {"x": 1.8, "y": -4.9, "tags": ["step:s:1"]},
        {"x": 1.8, "y": -5.4},
    ]
    rep = feed(Part1JudgeV2(), partial)
    assert_status(rep, "t_stairs", "success", "one complete arm = partial")
    assert st(rep, "t_stairs")["score"] == 50.0, "up partial = 50 (Q2 confirmed x2/3)"

    missing_level = [
        {"x": 1.8, "y": -5.4},
        {"x": 1.8, "y": -4.9, "tags": ["step:s:1"]},
        {"x": 1.8, "y": -3.8, "tags": ["step:top"]},
        {"x": 1.8, "y": -3.0},
    ]
    rep = feed(Part1JudgeV2(), missing_level)
    assert_not_success(rep, "t_stairs", "missing step levels must not score")

    # a partial result can be upgraded to full if the second arm is completed later
    # in the same attempt (partial success must not be permanently locked)
    j2 = Part1JudgeV2()
    feed(j2, partial)
    upgrade = [
        {"x": 1.8, "y": -3.8, "tags": ["step:top"]},
        {"x": 2.2, "y": -3.5, "tags": ["step:e:3"]},
        {"x": 2.6, "y": -3.5, "tags": ["step:e:2"]},
        {"x": 3.3, "y": -3.5, "tags": ["step:e:1"]},
        {"x": 3.5, "y": -3.5},
    ]
    rep = feed(j2, upgrade)
    assert_status(rep, "t_stairs", "success", "partial upgraded to full")
    assert st(rep, "t_stairs")["score"] == 100.0, st(rep, "t_stairs")
    # north arm only (downward direction) = 33 (Q2 x2/3); east arm only = 33 as well
    for arm, y0 in (("n", -1.9), ("e", None)):
        if arm == "n":
            seq = [
                {"x": 1.8, "y": -2.9},
                {"x": 1.8, "y": -3.3, "tags": ["step:n:1"]},
                {"x": 1.8, "y": -3.6, "tags": ["step:n:2"]},
                {"x": 1.8, "y": -3.9, "tags": ["step:n:3"]},
                {"x": 1.8, "y": -4.3, "tags": ["step:top"]},
                {"x": 1.8, "y": -4.6, "tags": ["step:s:3"]},
                {"x": 1.8, "y": -4.9, "tags": ["step:s:2"]},
                {"x": 1.8, "y": -5.3, "tags": ["step:s:1"]},
                {"x": 1.8, "y": -5.8},
            ]
        else:
            seq = [
                {"x": 3.4, "y": -3.5},
                {"x": 3.0, "y": -3.5, "tags": ["step:e:1"]},
                {"x": 2.6, "y": -3.5, "tags": ["step:e:2"]},
                {"x": 2.2, "y": -3.5, "tags": ["step:e:3"]},
                {"x": 1.8, "y": -3.8, "tags": ["step:top"]},
                {"x": 1.8, "y": -4.3, "tags": ["step:s:3"]},
                {"x": 1.8, "y": -4.9, "tags": ["step:s:1"]},
                {"x": 1.8, "y": -5.6},
            ]
        rep = feed(Part1JudgeV2(), seq)
        assert_status(rep, "t_stairs", "success", f"one-arm {arm} partial")
        assert st(rep, "t_stairs")["score"] == 33.0, (arm, st(rep, "t_stairs"))
    print("t_stairs: OK two-arm full / s=50 / n,e=33 / missing levels fail")


def test_slope_projection_and_graze_reset():
    spoof = [
        {"x": 3.6, "y": -5.0}, {"x": 4.5, "y": -5.0}, {"x": 5.5, "y": -5.0}, {"x": 6.5, "y": -5.0},
    ]
    assert_not_success(feed(Part1JudgeV2(), spoof), "slope", "x-position spoof")

    legal = [{"x": 4.6, "y": -6.6}]
    for i in range(1, 16):
        legal.append({"x": 4.6, "y": -6.6 + 0.1 * i, "tags": ["slope"]})
    legal.append({"x": 4.6, "y": -5.0, "tags": ["slope"]})
    legal.append({"x": 4.6, "y": -3.8})   # leave the slope zone
    rep = feed(Part1JudgeV2(), legal)
    assert_status(rep, "slope", "success", "long-axis projection >= 1 m")

    graze = [{"x": 5.7, "y": -4.2}, {"x": 5.7, "y": -3.5}] + legal
    rep = feed(Part1JudgeV2(), graze)
    assert_status(rep, "slope", "success", "soft-reset graze then legal traversal")

    lateral = [{"x": 5.0, "y": -6.6}]
    for i in range(1, 12):
        lateral.append({"x": 5.0 + (0.1 if i % 2 else -0.1), "y": -6.6, "tags": ["slope"]})
    lateral.append({"x": 5.0, "y": -3.8})
    assert_not_success(feed(Part1JudgeV2(), lateral), "slope", "lateral wiggle must not count")
    print("slope: OK projection, graze reset, lateral wiggle rejected")


def test_gravel_short_edges_and_long_edge():
    legal = [
        {"x": 5.0, "y": -13.4},
        {"x": 5.0, "y": -12.9, "tags": ["gravel"]},
        {"x": 5.5, "y": -12.0, "tags": ["gravel"]},
        {"x": 5.8, "y": -11.5, "tags": ["gravel"]},
        {"x": 6.0, "y": -11.0, "tags": ["gravel"]},
        {"x": 6.0, "y": -10.8},
    ]
    assert_status(feed(Part1JudgeV2(), legal), "gravel_pit", "success", "short-edge entry+exit")

    long_side = [
        {"x": 4.0, "y": -12.0},
        {"x": 4.4, "y": -12.0, "tags": ["gravel"]},
        {"x": 4.8, "y": -12.0, "tags": ["gravel"]},
        {"x": 5.2, "y": -12.0, "tags": ["gravel"]},
        {"x": 5.6, "y": -12.0, "tags": ["gravel"]},
        {"x": 6.0, "y": -12.0, "tags": ["gravel"]},
        {"x": 6.5, "y": -12.0},
    ]
    rep = feed(Part1JudgeV2(), long_side)
    assert_not_success(rep, "gravel_pit", "long-edge entry")
    assert_failed(rep, "gravel_pit", "genuine long-edge attempt")
    print("gravel_pit: OK short edges / long edge rejected")


def test_slalom_forward_reverse_and_spoof():
    forward = [
        {"x": 1.8, "y": -10.1},
        {"x": 1.9, "y": -10.5},
        {"x": 1.7, "y": -11.0},
        {"x": 1.7, "y": -11.5},
        {"x": 1.9, "y": -12.0},
        {"x": 1.9, "y": -12.5},
        {"x": 1.55, "y": -12.75},
        {"x": 2.4, "y": -12.6},
        {"x": 2.8, "y": -12.6},
        {"x": 3.2, "y": -12.5},
    ]
    rep = feed(Part1JudgeV2(), forward)
    assert_status(rep, "slalom", "success", "forward S")

    reverse = [
        {"x": 3.2, "y": -12.5},
        {"x": 2.8, "y": -12.4},
        {"x": 1.9, "y": -12.6},
        {"x": 1.55, "y": -12.75},
        {"x": 1.9, "y": -11.6},
        {"x": 1.7, "y": -10.6},
        {"x": 1.8, "y": -10.1},
    ]
    rep = feed(Part1JudgeV2(), reverse)
    assert_status(rep, "slalom", "success", "reverse S")

    early_end = [
        {"x": 1.8, "y": -10.1},
        {"x": 3.2, "y": -12.5},       # visit the end circle early
        {"x": 1.9, "y": -10.5},
        {"x": 1.7, "y": -11.5},
        {"x": 1.9, "y": -12.5},
        {"x": 1.55, "y": -12.75},
        {"x": 2.8, "y": -12.6},       # post 3
        {"x": 2.5, "y": -11.8},       # leave without re-entering the end circle
        {"x": 3.6, "y": -11.8},
    ]
    assert_not_success(feed(Part1JudgeV2(), early_end), "slalom", "early end area")

    out_of_order = [
        {"x": 1.8, "y": -10.1},
        {"x": 1.7, "y": -11.5},
        {"x": 1.9, "y": -12.5},
        {"x": 2.8, "y": -12.6},
    ]
    assert_not_success(feed(Part1JudgeV2(), out_of_order), "slalom", "out-of-order posts")

    # corner checkpoint too early (A direction requires it after post 2)
    early_corner = [
        {"x": 1.8, "y": -10.1},
        {"x": 1.9, "y": -10.5},   # post 0
        {"x": 1.7, "y": -11.5},   # post 1
        {"x": 1.55, "y": -12.75},  # corner after only two posts (A expects three)
        {"x": 1.9, "y": -12.5},   # post 2
        {"x": 2.8, "y": -12.6},   # post 3
        {"x": 3.2, "y": -12.5},   # end
    ]
    assert_not_success(feed(Part1JudgeV2(), early_corner), "slalom", "corner too early")
    print("slalom: OK forward/reverse / early-end and out-of-order rejected")


# ---------------------------------------------------------------- ledger / timeout / scene

def test_attempt_manager_rules():
    am = AttemptManager(max_attempts=3)
    assert am.begin(0.0)
    am.note_recovery(10.0)
    am.end(40.0, {"score": 60.0, "obstacle_score": 60.0, "return_bonus": 0.0})
    assert am.begin(50.0)
    am.end(100.0, {"score": 90.0, "obstacle_score": 90.0, "return_bonus": 0.0})
    assert am.begin(110.0)
    am.skip(115.0)
    summary = am.summary()
    assert summary["attempts_used"] == 3 and summary["final_score"] == 90.0
    assert summary["final_time_s"] == 50.0 and summary["recoveries"] == 1
    assert am.begin(120.0) is False
    print("attempt manager: OK recovery-free / best score / fastest time / 3-attempt cap")


def test_timeout_finalize():
    rep = Part1JudgeV2().finalize("timeout")
    assert all(s["status"] == "fail" for s in rep["states"].values())
    print("timeout finalize: OK")


def test_scene_geom_tags_complete():
    scene = Path(__file__).resolve().parents[2] / "assets/terrain/part1/part1_eval_scene_v2.xml"
    tree = ET.parse(scene)
    names = {e.get("name") for e in tree.iter("geom") if e.get("name")}
    required_prefixes = ("bridge_blocks_", "bridge_bands_", "t_stairs_", "slope_",
                         "gravel_pit_")
    missing = [n for n in names if n.startswith(required_prefixes) and n not in GEOM_TAGS]
    assert not missing, f"scene geoms missing from GEOM_TAGS: {missing}"
    assert GEOM_TAGS["bridge_platform_r"] >= {"platform_right", "platform_high"}
    # ground classifier (2026-10-23 flash acceptance): approach ramps are ground, while
    # obstacle surfaces (bridge/slope/steps) must never be classified as ground.
    assert is_ground_geom("ramp_blocks_l") and is_ground_geom("ramp_blocks_r")
    assert is_ground_geom("floor", is_plane=True) and is_ground_geom("ground_left")
    assert is_ground_geom("trench_bottom") and is_ground_geom("level_floor")
    assert not is_ground_geom("bridge_blocks_0")
    assert not is_ground_geom("slope_a")
    assert not is_ground_geom("t_stairs_y_low1")
    print(f"scene geom tags: OK ({len(names)} named geoms checked, ground classifier OK)")


def main() -> None:
    tests = [
        test_spoof_exit_positions,
        test_approach_ground_is_not_failure,
        test_failure_can_be_retried_and_success_is_final,
        test_bridge_ground_and_success,
        test_height_bar_touch_drop_and_gate,
        test_high_wall_sideways_climb_and_bypass,
        test_t_stairs_full_partial_and_history,
        test_slope_projection_and_graze_reset,
        test_gravel_short_edges_and_long_edge,
        test_slalom_forward_reverse_and_spoof,
        test_attempt_manager_rules,
        test_timeout_finalize,
        test_scene_geom_tags_complete,
    ]
    for fn in tests:
        fn()
    print(f"comp_part1_judge V2.1 conformance: OK ({len(tests)} groups)")


if __name__ == "__main__":
    main()
