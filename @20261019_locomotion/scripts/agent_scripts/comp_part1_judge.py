"""Part 1 official-style judge V2 (event-driven, rule-faithful, simulation-agnostic).

Why V2
- V1 (``part1_event_judge.py``) only checked "base reached a coordinate" and was shown in the
  2026-10-22 G1 audit to accept illegal paths (e.g. exit-side position with no crossing, six
  obstacles spoofable 6/6) and to miss legal traversals (T-stairs history, slope direction).
- V2 requires: legal entry side -> actual traversal evidence (surface contacts / step history /
  distance) -> legal exit, with per-rule failure semantics.

Inputs are pure Python values so the judge can be unit-tested without MuJoCo:
- ``base_xyz`` / ``base_yaw``
- ``foot_tags``: ``{leg: {surface_tag, ...}}`` where tags are produced by the caller from contact
  geoms (e.g. ``bridge``, ``platform_left``, ``step:main:2``, ``slope``, ``gravel``, ``wall``).
- ``ground_feet``: legs touching the floor / non-allowed ground at this instant.
- ``bar_z``: current height-bar beam z (None if unavailable -> success is blocked, see rules).

Rules encoded (organizer answers 2026-10-22, see comp/CONTRACT.md):
- 1/2-foot rule: *any instant* with >=2 feet on ground while inside a ground-fail zone -> fail
  (no debounce).
- height bar: touching posts/beam is NOT a failure; only beam drop fails; robot must pass under
  the beam through the gate opening.
- T stairs: per-step top contact history (each step at least once), both branches for full score,
  one branch only -> partial (values from the contract; Q2 value >100 is clamped and flagged).
- slope: cumulative path length on the slope surfaces along the long axis must be >= 1 m;
  both sides count together.
- gravel pit: legal entry AND exit only through the 1 m short edges; gravel surface contact
  required; any instant >=2 ground feet fails.
- bridges: platform before -> bridge surfaces -> opposite platform; >=2 ground feet fails.
- high wall: cross to the other side with climb evidence (base raised or foot on wall), not by
  walking around.
- slalom: start in a marked circle, alternate sides around posts in order, pass the corner
  checkpoint, finish in the other marked circle.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------- geometry

# Zones in world metres, from assets/terrain/part1/part1_scene.xml (2026-10-22).
ZONES: dict[str, tuple[float, float, float, float]] = {
    "start_area": (3.2, 4.2, -9.5, -8.5),
    "height_bar": (5.0, 6.4, -9.6, -8.4),
    "high_wall": (1.25, 2.35, -7.85, -6.15),
    "bridge_blocks": (1.25, 6.3, -1.0, 1.0),
    "bridge_bands": (5.0, 6.3, -4.0, -0.8),
    "gravel_pit": (4.25, 6.4, -13.0, -10.9),
    "t_stairs": (1.25, 3.35, -4.95, -2.1),
    "slope": (3.8, 6.4, -6.7, -4.0),
    "slalom": (1.3, 3.5, -13.0, -10.0),
}

# Slalom course points (scene geoms): start/end beya circles + corner checkpoint + post centres.
SLALOM_START_A = (1.8, -10.1)
SLALOM_START_B = (3.2, -12.5)
SLALOM_CORNER = (1.55, -12.75)
SLALOM_POSTS = [(1.8, -10.5), (1.8, -11.5), (1.8, -12.5), (2.8, -12.5)]
SLALOM_RADIUS_M = 0.5
SLALOM_POST_RADIUS_M = 0.35

BAR_DROP_THRESHOLD_M = 0.05
BAR_OPENING_X = (5.2, 6.2)
WALL_CROSS_Y = -7.0
WALL_TOP_Z = 0.30

# T-stairs: two branches meeting at the top platform (scene geoms, 2026-10-22).
# Each entry: (branch, level, surface_tag, approximate top-z). Caller-classified tags are
# ``step:<branch>:<level>``; the judge only needs the set.
T_STAIRS_TOP_TAG = "step:top"


# ---------------------------------------------------------------- helpers

def _side_of(zone: tuple[float, float, float, float], xy: tuple[float, float]) -> str | None:
    """Return which side of the zone the point is nearest outside, or None if inside."""
    x0, x1, y0, y1 = zone
    x, y = xy
    if x0 <= x <= x1 and y0 <= y <= y1:
        return None
    candidates = [
        (abs(x - x0), "xmin"), (abs(x - x1), "xmax"),
        (abs(y - y0), "ymin"), (abs(y - y1), "ymax"),
    ]
    return min(candidates)[1]


def _in_zone(zone: tuple[float, float, float, float], xy: tuple[float, float]) -> bool:
    x0, x1, y0, y1 = zone
    return x0 <= xy[0] <= x1 and y0 <= xy[1] <= y1


def _opposite(side: str) -> str:
    return {"xmin": "xmax", "xmax": "xmin", "ymin": "ymax", "ymax": "ymin"}[side]


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _sign(v: float) -> int:
    return 1 if v > 1e-6 else (-1 if v < -1e-6 else 0)


# ---------------------------------------------------------------- obstacle state machines

@dataclass
class ObstacleResult:
    name: str
    status: str = "pending"  # pending / running / success / fail / skipped
    reason: str = ""
    score: float = 0.0
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"status": self.status, "reason": self.reason, "score": self.score,
                "detail": self.detail}


class _Obstacle:
    """Common bookkeeping; subclasses implement the rule-specific evidence."""

    name = "abstract"
    zone: tuple[float, float, float, float] = (0, 0, 0, 0)
    ground_fail = True

    def __init__(self) -> None:
        self.result = ObstacleResult(self.name)
        self.prev_xy: tuple[float, float] | None = None
        self.prev_in_zone = False
        self.in_zone_samples = 0
        self._reset_evidence()

    # -- hooks ---------------------------------------------------------------
    def _reset_evidence(self) -> None:
        self.evidence: dict[str, Any] = {}

    def _on_first_inside(self, side_prev: str | None, xy: tuple[float, float]) -> None:
        self.evidence["entry_side_prev"] = side_prev

    def _on_sample(self, xy: tuple[float, float], tags: set[str],
                   ground_feet: set[str], bar_z: float | None, yaw: float) -> None:
        pass

    def _check_exit(self, side: str, tags: set[str], ground_feet: set[str]) -> tuple[bool, str]:
        """Return (success, reason). Called once when the base leaves the zone."""
        return False, ""

    def _check_immediate(self) -> tuple[bool, str] | None:
        """Return (success, reason) if an in-zone condition finishes the obstacle."""
        return None

    per_obstacle_score: float = 100.0

    def _score_for(self) -> float:
        """Score awarded when the obstacle ends in success (overridden by partial-score rules)."""
        return float(self.per_obstacle_score)

    # -- update --------------------------------------------------------------
    def update(self, t: float, base_xyz: tuple[float, float, float], yaw: float,
               foot_tags: dict[str, set[str]], ground_feet: set[str],
               bar_z: float | None) -> None:
        if self.result.status in ("success", "fail", "skipped"):
            return
        xy = (float(base_xyz[0]), float(base_xyz[1]))
        inside = _in_zone(self.zone, xy)
        tags = {tag for values in foot_tags.values() for tag in values}
        if inside and not self.prev_in_zone:
            self.result.status = "running"
            self._on_first_inside(_side_of(self.zone, self.prev_xy) if self.prev_xy else None, xy)
        if inside:
            self.in_zone_samples += 1
            self.result.detail["in_zone_samples"] = self.in_zone_samples
            if self.ground_fail and len(ground_feet) >= 2:
                self.result.status = "fail"
                self.result.reason = "two_feet_ground:" + ",".join(sorted(ground_feet))
                return
            self._on_sample(xy, tags, ground_feet, bar_z, yaw)
            imm = self._check_immediate()
            if imm is not None:
                ok, reason = imm
                self.result.status = "success" if ok else "fail"
                self.result.reason = reason
                if ok:
                    self.result.score = self._score_for()
                return
        elif self.prev_in_zone and self.result.status == "running":
            side = _side_of(self.zone, xy)
            ok, reason = self._check_exit(side or "unknown", tags, ground_feet)
            if ok:
                self.result.status = "success"
                self.result.reason = ""
                self.result.score = self._score_for()
            elif reason:
                self.result.status = "fail"
                self.result.reason = reason
            else:  # left the zone without legal exit: allow another try
                self.result.status = "pending"
                self.result.detail["aborted_exit"] = side
                self._reset_evidence()
        self.prev_in_zone = inside
        self.prev_xy = xy


class TraversalBridge(_Obstacle):
    """Platform -> bridge surfaces -> opposite platform; >=2 ground feet fails."""

    ground_fail = True
    axis = "x"

    def __init__(self, name: str, zone, axis: str, surface_tag: str,
                 platform_tags: tuple[str, str], opposite: bool = True) -> None:
        self.name, self.zone, self.axis = name, zone, axis
        self.surface_tag = surface_tag
        self.platform_tags = platform_tags
        self.opposite = opposite
        super().__init__()

    def _reset_evidence(self) -> None:
        self.evidence = {"bridge_hits": 0, "platforms": set()}

    def _on_sample(self, xy, tags, ground_feet, bar_z, yaw) -> None:
        if self.surface_tag in tags:
            self.evidence["bridge_hits"] += 1
        for plat in self.platform_tags:
            if plat in tags:
                self.evidence["platforms"].add(plat)

    def _check_exit(self, side: str, tags: set[str], ground_feet: set[str]) -> tuple[bool, str]:
        entry = self.evidence.get("entry_side_prev")
        if entry is None:
            return False, "illegal_entry"
        if self.opposite and side != _opposite(entry):
            return False, "wrong_exit_side"
        if self.evidence.get("bridge_hits", 0) < 3:
            return False, "missing_bridge_contact"
        if len(self.evidence.get("platforms", ())) < 2:
            return False, "missing_platform_evidence"
        return True, ""


class HeightBar(_Obstacle):
    ground_fail = False

    def __init__(self) -> None:
        self.name, self.zone = "height_bar", ZONES["height_bar"]
        super().__init__()

    def _reset_evidence(self) -> None:
        self.evidence = {"bar_z0": None, "through_opening": False, "bar_drop": False,
                         "crossed": False, "bad_opening": False}

    def _on_first_inside(self, side_prev, xy) -> None:
        super()._on_first_inside(side_prev, xy)
        self.evidence["bar_z0"] = self.evidence.get("bar_z0")

    def _on_sample(self, xy, tags, ground_feet, bar_z, yaw) -> None:
        x, y = xy
        if bar_z is not None:
            if self.evidence["bar_z0"] is None:
                self.evidence["bar_z0"] = bar_z
            elif self.evidence["bar_z0"] - bar_z > BAR_DROP_THRESHOLD_M:
                self.evidence["bar_drop"] = True
        if abs(y - (-9.0)) < 0.35:
            if BAR_OPENING_X[0] <= x <= BAR_OPENING_X[1]:
                self.evidence["through_opening"] = True
            else:
                self.evidence["bad_opening"] = True
        if self.evidence["bar_drop"]:
            self.result.status = "fail"
            self.result.reason = "bar_dropped"

    def _check_exit(self, side, tags, ground_feet) -> tuple[bool, str]:
        entry = self.evidence.get("entry_side_prev")
        if entry not in ("ymin", "ymax"):
            return False, "illegal_entry_side"   # must pass under the beam, not sideways
        if side not in ("ymin", "ymax"):
            return False, "wrong_exit_side"      # leaving through x sides is not the gate
        if side != _opposite(entry):
            return False, "wrong_exit_side"
        if self.evidence["bad_opening"] and not self.evidence["through_opening"]:
            return False, "not_through_opening"
        if self.evidence["bar_z0"] is None:
            return False, "bar_state_unknown"
        return True, ""


class HighWall(_Obstacle):
    ground_fail = False

    def __init__(self) -> None:
        self.name, self.zone = "high_wall", ZONES["high_wall"]
        super().__init__()

    def _reset_evidence(self) -> None:
        self.evidence = {"max_z": 0.0, "wall_contact": False}

    def _on_sample(self, xy, tags, ground_feet, bar_z, yaw) -> None:
        self.evidence["max_z"] = max(self.evidence["max_z"], float(self._last_z))
        if "wall" in tags:
            self.evidence["wall_contact"] = True

    def update(self, t, base_xyz, yaw, foot_tags, ground_feet, bar_z):
        self._last_z = float(base_xyz[2])
        super().update(t, base_xyz, yaw, foot_tags, ground_feet, bar_z)

    def _check_exit(self, side, tags, ground_feet) -> tuple[bool, str]:
        entry = self.evidence.get("entry_side_prev")
        if entry not in ("ymin", "ymax"):
            return False, "illegal_entry_side"   # wall is thin along y: must cross along y
        if side not in ("ymin", "ymax"):
            return False, "wrong_exit_side"      # walking along the wall is not a crossing
        if side != _opposite(entry):
            return False, "wrong_exit_side"
        if self.evidence["max_z"] < WALL_TOP_Z and not self.evidence["wall_contact"]:
            return False, "no_climb_evidence"
        return True, ""


class GravelPit(_Obstacle):
    ground_fail = True

    def __init__(self) -> None:
        self.name, self.zone = "gravel_pit", ZONES["gravel_pit"]
        super().__init__()

    def _reset_evidence(self) -> None:
        self.evidence = {"gravel_hits": 0}

    def _on_sample(self, xy, tags, ground_feet, bar_z, yaw) -> None:
        if "gravel" in tags:
            self.evidence["gravel_hits"] += 1

    def _check_exit(self, side, tags, ground_feet) -> tuple[bool, str]:
        entry = self.evidence.get("entry_side_prev")
        if entry not in ("ymin", "ymax"):
            return False, "illegal_entry_side"
        if side not in ("ymin", "ymax"):
            return False, "illegal_exit_side"
        if side == entry:
            return False, "no_crossing"
        if self.evidence["gravel_hits"] < 3:
            return False, "missing_gravel_contact"
        return True, ""


class Slope(_Obstacle):
    ground_fail = True

    def __init__(self) -> None:
        self.name, self.zone = "slope", ZONES["slope"]
        super().__init__()

    def _reset_evidence(self) -> None:
        self.evidence = {"distance": 0.0, "last": None}

    def _on_sample(self, xy, tags, ground_feet, bar_z, yaw) -> None:
        on_slope = "slope" in tags
        if on_slope:
            if self.evidence["last"] is not None:
                self.evidence["distance"] += _dist(self.evidence["last"], xy)
            self.evidence["last"] = xy
        else:
            self.evidence["last"] = None

    def _check_exit(self, side, tags, ground_feet) -> tuple[bool, str]:
        if self.evidence["distance"] < 1.0:
            return False, f"slope_distance<1m:{self.evidence['distance']:.2f}"
        return True, ""


class TStairs(_Obstacle):
    ground_fail = True

    def __init__(self, partial_up: float = 112.5, partial_down: float = 75.0,
                 max_score: float = 100.0) -> None:
        self.name, self.zone = "t_stairs", ZONES["t_stairs"]
        self.partial_up, self.partial_down, self.max_score = partial_up, partial_down, max_score
        super().__init__()

    def _reset_evidence(self) -> None:
        self.evidence = {"steps": set(), "branches": [], "top": False,
                         "entry_branch": None, "exit_branch": None}

    def _step_tags(self, tags: set[str]) -> set[str]:
        return {t for t in tags if t.startswith("step:")}

    def _on_sample(self, xy, tags, ground_feet, bar_z, yaw) -> None:
        for tag in self._step_tags(tags):
            self.evidence["steps"].add(tag)
            parts = tag.split(":")
            if len(parts) == 2:          # "step:top" = the top platform
                self.evidence["top"] = True
                continue
            _, branch, level = parts
            if branch not in self.evidence["branches"]:
                self.evidence["branches"].append(branch)
            if level == "top":
                self.evidence["top"] = True
        if self.evidence["entry_branch"] is None and self.evidence["branches"]:
            self.evidence["entry_branch"] = self.evidence["branches"][0]
        if self.evidence["top"] and len(self.evidence["branches"]) >= 1:
            self.evidence["exit_branch"] = self.evidence["branches"][-1]
        self.result.detail["branches"] = list(self.evidence["branches"])
        self.result.detail["steps"] = sorted(self.evidence["steps"])
        self.result.detail["top"] = bool(self.evidence["top"])

    def _score_for(self) -> float:
        ev = self.evidence
        if ev["top"] and len(ev["branches"]) >= 2:
            return float(self.max_score)
        if ev["top"] and len(ev["branches"]) == 1:
            raw = self.partial_up if ev["branches"][0] == "main" else self.partial_down
            return float(min(raw, self.max_score))
        return 0.0

    def _check_exit(self, side, tags, ground_feet) -> tuple[bool, str]:
        ev = self.evidence
        if not ev["top"]:
            return False, "missing_top_platform"
        if len(ev["branches"]) < 1:
            return False, "missing_step_contacts"
        if len(ev["branches"]) == 1:
            # one-branch traversal: partial but still a completed obstacle for scoring purposes
            return True, ""
        return True, ""


class Slalom(_Obstacle):
    ground_fail = False

    def __init__(self) -> None:
        self.name, self.zone = "slalom", ZONES["slalom"]
        super().__init__()

    def _reset_evidence(self) -> None:
        self.evidence = {"start_area": None, "posts": [], "sides": [], "corner": False,
                         "end_area": None}

    def _near(self, xy, point, radius=SLALOM_RADIUS_M) -> bool:
        return _dist(xy, point) <= radius

    def _on_sample(self, xy, tags, ground_feet, bar_z, yaw) -> None:
        ev = self.evidence
        if ev["start_area"] is None:
            if self._near(xy, SLALOM_START_A):
                ev["start_area"] = "A"
            elif self._near(xy, SLALOM_START_B):
                ev["start_area"] = "B"
        for idx, post in enumerate(SLALOM_POSTS):
            if idx in ev["posts"]:
                continue
            if self._near(xy, post, SLALOM_POST_RADIUS_M):
                if idx == 0 or (idx - 1) in ev["posts"]:
                    ev["posts"].append(idx)
                    # side relative to the post in the local travel frame (sign of cross product)
                    prev = ev["posts"][-2] if len(ev["posts"]) > 1 else 0
                    ref = SLALOM_POSTS[prev] if len(ev["posts"]) > 1 else (SLALOM_START_A if ev["start_area"] != "B" else SLALOM_START_B)
                    tx, ty = post[0] - ref[0], post[1] - ref[1]
                    nx, ny = -ty, tx
                    side = _sign(nx * (xy[0] - post[0]) + ny * (xy[1] - post[1]))
                    ev["sides"].append(side)
        if self._near(xy, SLALOM_CORNER) and len(ev["posts"]) >= 2:
            ev["corner"] = True
        if ev["start_area"] == "A" and self._near(xy, SLALOM_START_B):
            ev["end_area"] = "B"
        elif ev["start_area"] == "B" and self._near(xy, SLALOM_START_A):
            ev["end_area"] = "A"

    def _check_immediate(self):
        ev = self.evidence
        if ev["start_area"] and len(ev["posts"]) == len(SLALOM_POSTS):
            alternated = all(a * b < 0 for a, b in zip(ev["sides"], ev["sides"][1:]))
            complete = alternated and ev["corner"] and ev["end_area"]
            if complete:
                self.result.detail["sides"] = ev["sides"]
                return True, ""
        return None

    def _check_exit(self, side, tags, ground_feet) -> tuple[bool, str]:
        ev = self.evidence
        if not ev["start_area"]:
            return False, "no_start_area"
        if len(ev["posts"]) < len(SLALOM_POSTS):
            return False, "missing_posts"
        if not ev["corner"]:
            return False, "missing_corner_checkpoint"
        if not ev["end_area"]:
            return False, "no_end_area"
        if not all(a * b < 0 for a, b in zip(ev["sides"], ev["sides"][1:])):
            return False, "not_s_shaped_sides"
        return True, ""


# ---------------------------------------------------------------- aggregate judge

class Part1JudgeV2:
    """One instance judges one continuous course attempt (all 8 obstacles)."""

    def __init__(self, *, partial_up: float = 112.5, partial_down: float = 75.0,
                 max_obstacle_score: float = 100.0) -> None:
        self.obstacles: dict[str, _Obstacle] = {
            "height_bar": HeightBar(),
            "high_wall": HighWall(),
            "bridge_blocks": TraversalBridge("bridge_blocks", ZONES["bridge_blocks"], "x",
                                             "bridge", ("platform_left", "platform_right")),
            "bridge_bands": TraversalBridge("bridge_bands", ZONES["bridge_bands"], "y",
                                            "bridge", ("platform_low", "platform_high")),
            "gravel_pit": GravelPit(),
            "t_stairs": TStairs(partial_up, partial_down, max_obstacle_score),
            "slope": Slope(),
            "slalom": Slalom(),
        }
        self.t = 0.0
        self.returned_to_start = False
        self._all_done_once = False
        self.prev_start_inside = False
        self.start_area_hits = 0

    def update(self, t: float, base_xyz, yaw: float = 0.0, *,
               foot_tags: dict[str, set[str]] | None = None,
               ground_feet: set[str] | None = None,
               bar_z: float | None = None) -> dict:
        foot_tags = foot_tags or {}
        ground_feet = ground_feet or set()
        self.t = float(t)
        for obs in self.obstacles.values():
            obs.update(self.t, base_xyz, yaw, foot_tags, ground_feet, bar_z)
        in_start = _in_zone(ZONES["start_area"], (base_xyz[0], base_xyz[1]))
        if in_start and not self.prev_start_inside:
            self.start_area_hits += 1
        self.prev_start_inside = in_start
        statuses = [o.result.status for o in self.obstacles.values()]
        if all(s == "success" for s in statuses):
            self._all_done_once = True
        if self._all_done_once and in_start and self.start_area_hits >= 2:
            self.returned_to_start = True
        return self.report()

    def report(self) -> dict:
        obstacles = {name: o.result.to_dict() for name, o in self.obstacles.items()}
        obstacle_total = sum(o.result.score for o in self.obstacles.values())
        return_bonus = 100.0 if self.returned_to_start else 0.0
        total = obstacle_total + return_bonus
        return {
            "score": total,
            "obstacle_score": obstacle_total,
            "return_bonus": return_bonus,
            "returned_to_start": self.returned_to_start,
            "states": obstacles,
            "statuses": {name: o.result.status for name, o in self.obstacles.items()},
        }

    def finalize(self, reason: str = "timeout") -> dict:
        """End of attempt: unresolved obstacles become fail(timeout) for scoring purposes."""
        for obs in self.obstacles.values():
            if obs.result.status in ("pending", "running"):
                obs.result.status = "fail"
                obs.result.reason = reason
        return self.report()


# ---------------------------------------------------------------- attempts ledger

class AttemptManager:
    """Whole-run attempt bookkeeping per organizer answers (2026-10-22).

    - 3 attempts per run; recovery does not consume an attempt (timer paused, same attempt).
    - Starting / restarting a run consumes an attempt; skip consumes one.
    - final_score = best attempt score; final_time = fastest attempt duration (seconds).
    """

    def __init__(self, max_attempts: int = 3) -> None:
        self.max_attempts = max_attempts
        self.attempts: list[dict] = []
        self.events: list[dict] = []
        self._current: dict | None = None

    def begin(self, t: float) -> bool:
        if self._current is not None:
            raise RuntimeError("attempt already running")
        if self.attempts_used() >= self.max_attempts:
            return False
        self._current = {"attempt": len(self.attempts) + 1, "started_at": float(t),
                         "recoveries": 0, "pauses": [], "events": 0}
        self.events.append({"t": float(t), "event": "attempt_start",
                            "attempt": self._current["attempt"]})
        return True

    def attempts_used(self) -> int:
        return len(self.attempts) + (1 if self._current is not None else 0)

    def note_recovery(self, t: float) -> None:
        if self._current is None:
            raise RuntimeError("no running attempt")
        self._current["recoveries"] += 1
        self._current["pauses"].append([float(t), float(t)])  # pause window (resume extends it)
        self.events.append({"t": float(t), "event": "recovery", "consumes_attempt": False,
                            "attempt": self._current["attempt"]})

    def skip(self, t: float, reason: str = "operator_skip") -> None:
        if self._current is None:
            raise RuntimeError("no running attempt")
        cur = self._current
        self.attempts.append({**cur, "ended_at": float(t), "skipped": True,
                              "reason": reason, "score": 0.0,
                              "duration_s": max(0.0, float(t) - cur["started_at"])})
        self.events.append({"t": float(t), "event": "skip", "consumes_attempt": True,
                            "attempt": cur["attempt"]})
        self._current = None

    def end(self, t: float, report: dict, reason: str = "finished") -> None:
        if self._current is None:
            raise RuntimeError("no running attempt")
        cur = self._current
        self.attempts.append({**cur, "ended_at": float(t), "skipped": False, "reason": reason,
                              "score": float(report.get("score", 0.0)),
                              "obstacle_score": float(report.get("obstacle_score", 0.0)),
                              "return_bonus": float(report.get("return_bonus", 0.0)),
                              "duration_s": max(0.0, float(t) - cur["started_at"])})
        self.events.append({"t": float(t), "event": "attempt_end", "attempt": cur["attempt"],
                            "score": float(report.get("score", 0.0))})
        self._current = None

    def summary(self) -> dict:
        scored = [a for a in self.attempts if not a.get("skipped")]
        best_score = max((a["score"] for a in scored), default=0.0)
        fastest = min((a["duration_s"] for a in scored), default=0.0)
        return {
            "attempts_used": len(self.attempts),
            "attempts": self.attempts,
            "events": self.events,
            "final_score": best_score,
            "final_time_s": fastest,
            "skips": sum(1 for a in self.attempts if a.get("skipped")),
            "recoveries": sum(a["recoveries"] for a in self.attempts),
            "rules": {"max_attempts": self.max_attempts,
                      "recovery_consumes_attempt": False,
                      "final_score": "best_attempt",
                      "final_time": "min_over_attempts"},
        }


if __name__ == "__main__":
    print(json.dumps(Part1JudgeV2().report(), ensure_ascii=False, indent=2))
