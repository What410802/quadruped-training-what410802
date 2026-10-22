"""Part 1 obstacle event judge (P0 heuristic core).

Inputs are base position, per-foot ground contact flags and bar contact from a
policy rollout.  The rules are deliberately simple crossing/zone heuristics and
must be validated against teleop/golden trajectories before official use.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class ObstacleState:
    status: str = "pending"  # pending / running / success / fail
    reason: str = ""
    score: int = 0


class Part1EventJudge:
    def __init__(self) -> None:
        self.states: dict[str, ObstacleState] = {
            name: ObstacleState() for name in
            ("height_bar", "high_wall", "bridge_blocks", "bridge_bands", "gravel_pit", "t_stairs", "slope", "slalom")
        }
        self.prev = None
        # Slalom post centers from part1_scene.xml (L-shaped course).
        self.slalom_checkpoints = [(1.8, -10.5), (1.8, -11.5), (1.8, -12.5), (2.8, -12.5)]
        self.slalom_visited: set[int] = set()

    def _ground_fail(self, ground_feet: list[str]) -> str:
        return f"two_feet_ground:{','.join(ground_feet)}" if len(ground_feet) >= 2 else ""

    def update(self, base_xyz: tuple[float, float, float], ground_feet: list[str], bar_touched: bool,
               step_levels: set[int] | None = None) -> dict:
        x, y, z = map(float, base_xyz)
        prev = self.prev
        self.prev = (x, y, z)
        gfail = self._ground_fail(ground_feet)

        def setstate(name: str, success: bool, fail: bool, reason: str = "") -> None:
            st = self.states[name]
            if st.status in ("success", "fail"):
                return
            if fail:
                st.status, st.reason = "fail", reason
            elif success:
                st.status, st.reason, st.score = "success", "", 100

        # Height bar is a gate in the x-z plane at y=-9: posts at x=5.2/6.2,
        # beam spanning x=5.2..6.2.  The only valid passage is along +y/-y,
        # through x in [5.2, 6.2], NOT along +x into a side post.
        if 5.15 <= x <= 6.25 and -10.6 <= y <= -8.1:
            if self.states["height_bar"].status == "pending":
                self.states["height_bar"].status = "running"
            setstate("height_bar", success=(y > -8.95), fail=bar_touched, reason="bar_touched")
        # High wall: cross the vertical wall at x~1.8.
        if 1.2 <= x <= 2.6 and -7.7 <= y <= -6.3:
            if self.states["high_wall"].status == "pending":
                self.states["high_wall"].status = "running"
            setstate("high_wall", success=x > 2.0, fail=False)
        # 5 separated blocks: cross from left platform to right platform along +x.
        if 1.2 <= x <= 6.4 and -1.1 <= y <= 1.1:
            if self.states["bridge_blocks"].status == "pending":
                self.states["bridge_blocks"].status = "running"
            setstate("bridge_blocks", success=x > 5.4, fail=bool(gfail), reason=gfail)
        # 3 narrow bands: cross along +y from the lower platform to upper platform.
        if 5.0 <= x <= 6.4 and -4.1 <= y <= -0.7:
            if self.states["bridge_bands"].status == "pending":
                self.states["bridge_bands"].status = "running"
            setstate("bridge_bands", success=y > -1.0, fail=bool(gfail), reason=gfail)
        # Gravel pit: cross the L-shaped field along +x; any 1/2-foot ground fails.
        if 4.2 <= x <= 6.6 and -13.2 <= y <= -10.8:
            if self.states["gravel_pit"].status == "pending":
                self.states["gravel_pit"].status = "running"
            setstate("gravel_pit", success=x > 6.3, fail=bool(gfail), reason=gfail)
        # 10-degree slope: cross along +x; ground contact fails.
        if 3.7 <= x <= 6.6 and -6.8 <= y <= -3.9:
            if self.states["slope"].status == "pending":
                self.states["slope"].status = "running"
            setstate("slope", success=x > 5.7, fail=bool(gfail), reason=gfail)
        # T stairs: require at least three distinct step levels in addition to +y crossing.
        if 1.2 <= x <= 3.5 and -5.0 <= y <= -2.0:
            if self.states["t_stairs"].status == "pending":
                self.states["t_stairs"].status = "running"
            levels = step_levels or set()
            setstate("t_stairs", success=y > -2.1 and len(levels) >= 3, fail=bool(gfail), reason=gfail)
        # Slalom: visit the four posts in order (within 0.55 m); no ground-fail rule.
        for idx, (cx, cy) in enumerate(self.slalom_checkpoints):
            if idx not in self.slalom_visited and (x - cx) ** 2 + (y - cy) ** 2 <= 0.55 ** 2:
                # Require previous checkpoints first; an out-of-order post is ignored.
                if idx == 0 or (idx - 1) in self.slalom_visited:
                    self.slalom_visited.add(idx)
        if self.states["slalom"].status == "pending" and self.slalom_visited:
            self.states["slalom"].status = "running"
        setstate("slalom", success=len(self.slalom_visited) == len(self.slalom_checkpoints), fail=False)
        del prev
        return self.report()

    def report(self) -> dict:
        return {
            "score": sum(s.score for s in self.states.values()),
            "states": {k: {"status": v.status, "reason": v.reason, "score": v.score} for k, v in self.states.items()},
        }


def _synthetic() -> None:
    j = Part1EventJudge()
    # bridge_blocks path: enter left platform, cross, exit right.
    for x in (1.5, 2.2, 3.0, 4.0, 5.0, 5.5):
        j.update((x, 0.0, 0.42), [], False)
    print("bridge_blocks", j.states["bridge_blocks"])
    assert j.states["bridge_blocks"].status == "success"
    # Height bar: traverse the gate along y at x=5.7; contact fails.
    j2 = Part1EventJudge()
    for y, touch in ((-10.0, False), (-9.4, False), (-9.1, True), (-8.6, False)):
        j2.update((5.7, y, 0.8), [], touch)
    print("height_bar", j2.states["height_bar"])
    assert j2.states["height_bar"].status == "fail"
    j7 = Part1EventJudge()
    for y in (-10.0, -9.4, -8.6):
        j7.update((5.7, y, 0.8), [], False)
    print("height_bar_gate_success", j7.states["height_bar"])
    assert j7.states["height_bar"].status == "success"
    j3 = Part1EventJudge()
    for x, y in ((1.8, -10.5), (1.8, -11.5), (1.8, -12.5), (2.8, -12.5)):
        j3.update((x, y, 0.42), [], False)
    print("slalom", j3.states["slalom"])
    assert j3.states["slalom"].status == "success"
    # T stairs: crossing +y is not enough; three step levels are required.
    j4 = Part1EventJudge()
    for y, levels in ((-4.7, {5}), (-3.5, {5, 15}), (-2.0, {5, 15, 25})):
        j4.update((1.8, y, 0.42), [], False, step_levels=levels)
    print("t_stairs", j4.states["t_stairs"])
    assert j4.states["t_stairs"].status == "success"
    j5 = Part1EventJudge()
    for y in (-4.7, -3.5, -2.0):
        j5.update((1.8, y, 0.42), [], False, step_levels={5})
    print("t_stairs_missing_levels", j5.states["t_stairs"])
    assert j5.states["t_stairs"].status != "success"
    # Two feet on the floor inside a ground-fail zone must fail.
    j6 = Part1EventJudge()
    j6.update((4.5, 0.0, 0.42), ["FL", "FR"], False)
    print("bridge_ground_fail", j6.states["bridge_blocks"])
    assert j6.states["bridge_blocks"].status == "fail"
    print("synthetic OK")


if __name__ == "__main__":
    _synthetic()
