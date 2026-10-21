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
            ("height_bar", "high_wall", "bridge_blocks", "bridge_bands", "gravel_pit", "t_stairs", "slope")
        }
        self.prev = None

    def _ground_fail(self, ground_feet: list[str]) -> str:
        return f"two_feet_ground:{','.join(ground_feet)}" if len(ground_feet) >= 2 else ""

    def update(self, base_xyz: tuple[float, float, float], ground_feet: list[str], bar_touched: bool) -> dict:
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

        # Height bar: cross the bar line at y~-9 without touching it.
        if 5.0 <= x <= 6.4 and -9.6 <= y <= -8.4:
            if self.states["height_bar"].status == "pending":
                self.states["height_bar"].status = "running"
            setstate("height_bar", success=x > 6.2, fail=bar_touched, reason="bar_touched")
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
        # T stairs: cross along +y (main limb); ground contact fails.
        if 1.2 <= x <= 3.5 and -5.0 <= y <= -2.0:
            if self.states["t_stairs"].status == "pending":
                self.states["t_stairs"].status = "running"
            setstate("t_stairs", success=y > -2.1, fail=bool(gfail), reason=gfail)
        # 10-degree slope: cross along +x; ground contact fails.
        if 3.7 <= x <= 6.6 and -6.8 <= y <= -3.9:
            if self.states["slope"].status == "pending":
                self.states["slope"].status = "running"
            setstate("slope", success=x > 5.7, fail=bool(gfail), reason=gfail)
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
    # height bar with contact fails.
    j2 = Part1EventJudge()
    for x, touch in ((5.0, False), (5.5, False), (5.8, True), (6.3, False)):
        j2.update((x, -9.0, 0.8), [], touch)
    print("height_bar", j2.states["height_bar"])
    assert j2.states["height_bar"].status == "fail"
    print("synthetic OK")


if __name__ == "__main__":
    _synthetic()
