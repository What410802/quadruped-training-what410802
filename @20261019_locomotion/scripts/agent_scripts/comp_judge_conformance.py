"""Conformance tests for comp_part1_judge.py V2 (no MuJoCo needed).

Cases are taken from the 2026-10-22 G1 audit counterexamples:
- exit-side position without legal entry must NOT score (6 spoof paths);
- T-stairs per-step contact history across frames, both branches vs one branch;
- height bar: touching posts/beam without drop is NOT a failure, beam drop fails,
  crossing outside the gate opening fails;
- slope: crossing by x-position without slope-surface distance fails;
- gravel pit: long-side entry/exit illegal, both short edges legal, ground rule instant;
- bridges: ground fail is instantaneous, platforms + bridge contacts required;
- high wall: sideways walk / no climb evidence fails, real crossing succeeds;
- slalom: order, side alternation, corner checkpoint and end area all required.

Run: python3 scripts/agent_scripts/comp_judge_conformance.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from comp_part1_judge import AttemptManager, Part1JudgeV2  # noqa: E402


def feed(judge: Part1JudgeV2, samples, *, t0: float = 0.0, dt: float = 0.02) -> dict:
    """samples: list of dict(x=,y=,z=,tags=[...],ground=[...],bar_z=)"""
    report = None
    for i, s in enumerate(samples):
        tags = {leg: set(s.get("tags", [])) for leg in ("FL", "FR", "RL", "RR")}
        ground = set(s.get("ground", []))
        xy = (s["x"], s["y"])
        report = judge.update(t0 + i * dt, (xy[0], xy[1], s.get("z", 0.45)),
                              s.get("yaw", 0.0), foot_tags=tags, ground_feet=ground,
                              bar_z=s.get("bar_z"))
    return report


def state(report: dict, name: str) -> dict:
    return report["states"][name]


def assert_status(report, name, status, why=""):
    st = state(report, name)
    assert st["status"] == status, f"{name}: expected {status}, got {st['status']} ({st['reason']}) [{why}]"


def assert_not_success(report, name, why=""):
    st = state(report, name)
    assert st["status"] != "success", f"{name}: must not succeed, got {st['status']} [{why}]"


# ---------------------------------------------------------------- illegal spoof paths

def test_spoof_exit_positions():
    """A base teleported to the exit side with no legal entry must not score."""
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
        judge = Part1JudgeV2()
        report = feed(judge, [{"x": x, "y": y} for x, y in path])
        assert_not_success(report, name, f"spoof path {path}")
    print("spoof exit positions: OK -> all non-success")


def test_bridge_blocks_success_and_ground_fail():
    judge = Part1JudgeV2()
    path = [
        dict(x=0.5, y=0.0),
        dict(x=1.3, y=0.0, tags=["platform_left"]),
        dict(x=2.2, y=0.0, tags=["bridge"]),
        dict(x=3.2, y=0.0, tags=["bridge"]),
        dict(x=4.2, y=0.0, tags=["bridge"]),
        dict(x=5.2, y=0.0, tags=["bridge"]),
        dict(x=5.6, y=0.0, tags=["platform_right"]),
        dict(x=6.4, y=0.0, tags=["platform_right"]),
    ]
    report = feed(judge, path)
    assert_status(report, "bridge_blocks", "success", "legal traversal")
    assert state(report, "bridge_blocks")["score"] == 100

    judge2 = Part1JudgeV2()
    report2 = feed(judge2, [
        dict(x=0.5, y=0.0),
        dict(x=1.3, y=0.0, tags=["platform_left"]),
        dict(x=2.2, y=0.0, tags=["bridge"]),
        dict(x=2.6, y=0.0, ground=["FL", "FR"]),  # any instant >=2 ground feet fails
    ])
    assert_status(report2, "bridge_blocks", "fail", "instant ground fail")
    assert "two_feet_ground" in state(report2, "bridge_blocks")["reason"]
    print("bridge_blocks: OK success + instant ground fail")


def test_height_bar_touch_vs_drop():
    base = [
        dict(x=5.7, y=-10.0, bar_z=0.325),
        dict(x=5.7, y=-9.5, bar_z=0.325),
        dict(x=5.7, y=-9.0, bar_z=0.325),  # touching posts/beam is NOT a failure
        dict(x=5.7, y=-8.5, bar_z=0.325),
        dict(x=5.7, y=-8.2, bar_z=0.325),
    ]
    judge = Part1JudgeV2()
    report = feed(judge, base)
    assert_status(report, "height_bar", "success", "pass through gate, bar stable")

    judge2 = Part1JudgeV2()
    dropped = [dict(s, bar_z=(0.20 if i >= 2 else 0.325)) for i, s in enumerate(base)]
    report2 = feed(judge2, dropped)
    assert_status(report2, "height_bar", "fail", "beam dropped")
    assert "bar_dropped" in state(report2, "height_bar")["reason"]

    judge3 = Part1JudgeV2()
    outside = [
        dict(x=4.6, y=-10.0, bar_z=0.325),
        dict(x=4.6, y=-9.5, bar_z=0.325),
        dict(x=4.6, y=-9.0, bar_z=0.325),
        dict(x=4.6, y=-8.5, bar_z=0.325),
        dict(x=4.6, y=-8.2, bar_z=0.325),
    ]
    report3 = feed(judge3, outside)
    assert_not_success(report3, "height_bar", "crossed outside the gate opening")
    print("height_bar: OK touch!=fail / drop=fail / outside-opening!=success")


def test_t_stairs_history_and_partial():
    # Sequential contacts across frames: main branch 1,2,3 -> top -> side branch 3,2,1 -> exit.
    path = [
        dict(x=1.8, y=-5.4),
        dict(x=1.8, y=-4.9, tags=["step:main:1"]),
        dict(x=1.8, y=-4.6, tags=["step:main:2"]),
        dict(x=1.8, y=-4.3, tags=["step:main:3"]),
        dict(x=1.8, y=-3.8, tags=["step:top"]),
        dict(x=2.2, y=-3.5, tags=["step:side:3"]),
        dict(x=2.6, y=-3.5, tags=["step:side:2"]),
        dict(x=2.9, y=-3.5, tags=["step:side:1"]),
        dict(x=3.4, y=-3.5),
        dict(x=3.6, y=-3.5),
    ]
    judge = Part1JudgeV2()
    report = feed(judge, path)
    assert_status(report, "t_stairs", "success", "full two-branch traversal")
    assert state(report, "t_stairs")["score"] == 100
    assert len(state(report, "t_stairs")["detail"]["branches"]) == 2

    # Same branch up and back down = partial (one branch), must still count as completed.
    judge2 = Part1JudgeV2()
    partial = [
        dict(x=1.8, y=-5.4),
        dict(x=1.8, y=-4.9, tags=["step:main:1"]),
        dict(x=1.8, y=-4.6, tags=["step:main:2"]),
        dict(x=1.8, y=-4.3, tags=["step:main:3"]),
        dict(x=1.8, y=-3.8, tags=["step:top"]),
        dict(x=1.8, y=-4.3, tags=["step:main:3"]),
        dict(x=1.8, y=-4.9, tags=["step:main:1"]),
        dict(x=1.8, y=-5.4),
        dict(x=1.8, y=-5.6),
    ]
    report2 = feed(judge2, partial)
    assert_status(report2, "t_stairs", "success", "one-branch traversal is partial")
    assert len(state(report2, "t_stairs")["detail"]["branches"]) == 1
    assert state(report2, "t_stairs")["score"] == 75.0, "partial up = 75 (Q2 conservative)"
    print("t_stairs: OK sequential history + full/partial")


def test_slope_distance_and_direction():
    # Crossing by x-position with no slope contacts: distance stays 0 -> not success.
    judge = Part1JudgeV2()
    report = feed(judge, [
        dict(x=3.6, y=-5.0),
        dict(x=4.5, y=-5.0),
        dict(x=5.5, y=-5.0),
        dict(x=6.5, y=-5.0),
    ])
    assert_not_success(report, "slope", "no slope surface distance")

    # Legal: stay on slope surfaces and travel >=1 m along the long (y) axis.
    judge2 = Part1JudgeV2()
    path = [dict(x=3.6, y=-6.5)]
    for step in range(1, 16):
        path.append(dict(x=5.2, y=-6.5 + 0.1 * step, tags=["slope"]))
    path.append(dict(x=5.2, y=-5.0, tags=["slope"]))
    path.append(dict(x=3.6, y=-5.0))  # exit zone
    report2 = feed(judge2, path)
    assert_status(report2, "slope", "success", "two sides distance sum >= 1 m")

    # Boundary graze (enter the zone and leave after 2 frames, no slope contact) must
    # soft-reset and not poison a later legal traversal.
    judge3 = Part1JudgeV2()
    graze_then_legal = [
        dict(x=5.7, y=-4.2),        # inside slope zone (adjacent to bridge_bands approach)
        dict(x=5.7, y=-3.5),        # left without slope distance -> pending
    ] + path
    report3 = feed(judge3, graze_then_legal)
    assert_status(report3, "slope", "success", "soft-reset graze then legal traversal")
    print("slope: OK position-spoof fails, real distance succeeds")


def test_gravel_entry_exit_sides():
    judge = Part1JudgeV2()
    legal = [
        dict(x=5.0, y=-13.4),
        dict(x=5.0, y=-12.9, tags=["gravel"]),
        dict(x=5.5, y=-12.0, tags=["gravel"]),
        dict(x=5.8, y=-11.5, tags=["gravel"]),
        dict(x=6.0, y=-11.0, tags=["gravel"]),
        dict(x=6.0, y=-10.8),
    ]
    report = feed(judge, legal)
    assert_status(report, "gravel_pit", "success", "short-edge entry+exit")

    judge2 = Part1JudgeV2()
    long_side = [
        dict(x=4.0, y=-12.0),
        dict(x=4.4, y=-12.0, tags=["gravel"]),
        dict(x=4.8, y=-12.0, tags=["gravel"]),
        dict(x=5.2, y=-12.0, tags=["gravel"]),
        dict(x=5.6, y=-12.0, tags=["gravel"]),
        dict(x=6.0, y=-12.0, tags=["gravel"]),
        dict(x=6.4, y=-12.0),
        dict(x=6.6, y=-12.0),
    ]
    report2 = feed(judge2, long_side)
    assert_status(report2, "gravel_pit", "fail", "genuine long-edge attempt")
    assert "illegal_entry_side" in state(report2, "gravel_pit")["reason"]
    print("gravel_pit: OK short-edge legal / long-edge illegal")


def test_high_wall_sideways_and_climb():
    judge = Part1JudgeV2()
    sideways = [
        dict(x=1.2, y=-7.0),
        dict(x=1.5, y=-7.0, z=0.45),
        dict(x=2.0, y=-7.0, z=0.45),
        dict(x=2.4, y=-7.0, z=0.45),
        dict(x=2.6, y=-7.0, z=0.45),
    ]
    report = feed(judge, sideways)
    assert_not_success(report, "high_wall", "walked along the wall instead of crossing")

    judge2 = Part1JudgeV2()
    climb = [
        dict(x=1.8, y=-7.9),
        dict(x=1.8, y=-7.4, z=0.55, tags=["wall"]),
        dict(x=1.8, y=-7.0, z=0.65, tags=["wall"]),
        dict(x=1.8, y=-6.6, z=0.55, tags=["wall"]),
        dict(x=1.8, y=-6.0),
    ]
    report2 = feed(judge2, climb)
    assert_status(report2, "high_wall", "success", "raised crossing with wall contact")

    judge3 = Part1JudgeV2()
    no_climb = [
        dict(x=1.8, y=-7.9),
        dict(x=1.8, y=-7.4),   # standing height, no wall contact, no raise
        dict(x=1.8, y=-7.0),
        dict(x=1.8, y=-6.6),
        dict(x=1.8, y=-6.0),
    ]
    report3 = feed(judge3, no_climb)
    assert_not_success(report3, "high_wall", "crossed without climb evidence")
    print("high_wall: OK sideways fails / real crossing succeeds / no-climb fails")


def test_slalom_sequence():
    judge = Part1JudgeV2()
    path = [
        dict(x=1.8, y=-10.1),      # start area A
        dict(x=1.9, y=-10.5),      # post 0, side +1
        dict(x=1.7, y=-11.0),
        dict(x=1.7, y=-11.5),      # post 1, side -1
        dict(x=1.9, y=-12.0),
        dict(x=1.9, y=-12.5),      # post 2, side +1
        dict(x=1.55, y=-12.75),    # corner checkpoint
        dict(x=2.4, y=-12.6),
        dict(x=2.8, y=-12.6),      # post 3, side -1
        dict(x=3.2, y=-12.5),      # end area B
    ]
    report = feed(judge, path)
    assert_status(report, "slalom", "success", "S-shaped sequence")
    assert state(report, "slalom")["detail"]["sides"] == [1, -1, 1, -1]

    judge2 = Part1JudgeV2()
    bad_order = [
        dict(x=1.8, y=-10.1),
        dict(x=1.7, y=-11.5),   # post 1 before post 0 -> ignored
        dict(x=1.8, y=-12.5),
        dict(x=2.8, y=-12.5),
    ]
    report2 = feed(judge2, bad_order)
    assert_not_success(report2, "slalom", "out-of-order posts")
    print("slalom: OK ordered S succeeds / out-of-order fails")


def test_attempt_manager_rules():
    am = AttemptManager(max_attempts=3)
    assert am.begin(0.0)
    am.note_recovery(10.0)          # recovery does NOT consume an attempt
    am.end(40.0, {"score": 60.0, "obstacle_score": 60.0, "return_bonus": 0.0})
    assert am.begin(50.0)
    am.end(100.0, {"score": 90.0, "obstacle_score": 90.0, "return_bonus": 0.0})
    assert am.begin(110.0)
    am.skip(115.0)
    summary = am.summary()
    assert summary["attempts_used"] == 3, summary
    assert summary["final_score"] == 90.0, summary
    assert summary["final_time_s"] == 40.0, summary
    assert summary["recoveries"] == 1, summary
    assert summary["skips"] == 1, summary
    assert am.begin(120.0) is False, "4th attempt must be rejected"
    print("attempt manager: OK recovery-free / best score / fastest time / 3-attempt cap")


def test_timeout_finalize():
    judge = Part1JudgeV2()
    report = judge.finalize("timeout")
    assert all(s["status"] == "fail" for s in report["states"].values())
    print("timeout finalize: OK")


def main() -> None:
    tests = [
        test_spoof_exit_positions,
        test_bridge_blocks_success_and_ground_fail,
        test_height_bar_touch_vs_drop,
        test_t_stairs_history_and_partial,
        test_slope_distance_and_direction,
        test_gravel_entry_exit_sides,
        test_high_wall_sideways_and_climb,
        test_slalom_sequence,
        test_attempt_manager_rules,
        test_timeout_finalize,
    ]
    for fn in tests:
        fn()
    print(f"comp_part1_judge V2 conformance: OK ({len(tests)} groups)")


if __name__ == "__main__":
    main()
