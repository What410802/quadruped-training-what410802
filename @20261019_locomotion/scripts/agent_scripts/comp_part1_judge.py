"""Part 1 official-style judge V2.1 (event-driven, rule-faithful, simulation-agnostic).

V2.1 fixes the blockers found by the 2026-10-22 BYOK pre-audit:
- ground-fail only after the robot actually touched the obstacle surface (approach
  ground no longer kills legal attempts);
- high wall needs a real crossing of the wall plane with climb evidence, not just a
  y-side entry/exit;
- T stairs tracks explicit arms (south / north / east) and every step level, with
  partial score separated from full success;
- height bar needs a continuous crossing through the gate opening, and bar drop is
  tracked from the very first observed beam state;
- slalom supports both directions, requires the corner checkpoint at the turn and the
  end area only after all posts + corner, and uses the 1 m diameter beya circles;
- a failed obstacle can be retried inside the same attempt (failure is recorded as an
  event, the obstacle re-arms after leaving the zone); a success is final.
- slope distance is the cumulative projection along the slope long axis (y), not the
  Euclidean path length.

Inputs are pure Python values so the judge can be unit-tested without MuJoCo; the
runner classifies contacts into surface tags and passes them in.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------- geometry

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

# Slalom course (1 m diameter beya circles per rules; display geoms in scene v2 match).
SLALOM_START_A = (1.8, -10.1)
SLALOM_START_B = (3.2, -12.5)
SLALOM_CORNER = (1.55, -12.75)
SLALOM_POSTS = [(1.8, -10.5), (1.8, -11.5), (1.8, -12.5), (2.8, -12.5)]
SLALOM_RADIUS_M = 0.5
SLALOM_POST_RADIUS_M = 0.35
SLALOM_CORNER_RADIUS_M = 0.30   # keep the corner checkpoint distinct from post 2 (0.43 m away)

BAR_DROP_THRESHOLD_M = 0.05
BAR_OPENING_X = (5.2, 6.2)
WALL_CROSS_Y = -7.0
# High wall geom: pos x=1.8, size x=0.5 rotated 90 deg about z -> actual x span [1.30, 2.30].
# A raised base crossing y=-7 outside this span is walking around the wall, not surmounting.
WALL_X_MIN = 1.30
WALL_X_MAX = 2.30
# climb evidence: base raised this high above standing height during the wall crossing
WALL_CLIMB_Z = 0.60   # minimum base height at the wall crossing sample
# Exit/landing grace: once an obstacle traversal's evidence is complete (or the base is
# within this distance of the exit boundary), ground contact is landing, not failure.
EXIT_GRACE_M = 0.35

PART1_OBSTACLES = ("height_bar", "high_wall", "bridge_blocks", "bridge_bands",
                   "gravel_pit", "t_stairs", "slope", "slalom")


# ---------------------------------------------------------------- helpers

def _in_zone(zone: tuple[float, float, float, float], xy: tuple[float, float]) -> bool:
    x0, x1, y0, y1 = zone
    return x0 <= xy[0] <= x1 and y0 <= xy[1] <= y1


def _crossing_side(zone: tuple[float, float, float, float],
                   prev: tuple[float, float], curr: tuple[float, float]) -> str | None:
    """Which zone boundary the segment prev->curr crosses (entry or exit)."""
    x0, x1, y0, y1 = zone
    px, py = prev
    cx, cy = curr
    crossings: list[tuple[float, str]] = []

    def _x_at(y: float) -> float:
        if abs(cy - py) < 1e-9:
            return (px + cx) / 2.0
        return px + (cx - px) * (y - py) / (cy - py)

    def _y_at(x: float) -> float:
        if abs(cx - px) < 1e-9:
            return (py + cy) / 2.0
        return py + (cy - py) * (x - px) / (cx - px)

    if (py - y0) * (cy - y0) <= 0 and min(py, cy) <= y0 <= max(py, cy):
        if x0 <= _x_at(y0) <= x1 and py != cy:
            crossings.append((abs(cy - py), "ymin"))
    if (py - y1) * (cy - y1) <= 0 and min(py, cy) <= y1 <= max(py, cy):
        if x0 <= _x_at(y1) <= x1 and py != cy:
            crossings.append((abs(cy - py), "ymax"))
    if (px - x0) * (cx - x0) <= 0 and min(px, cx) <= x0 <= max(px, cx):
        if y0 <= _y_at(x0) <= y1 and px != cx:
            crossings.append((abs(cx - px), "xmin"))
    if (px - x1) * (cx - x1) <= 0 and min(px, cx) <= x1 <= max(px, cx):
        if y0 <= _y_at(x1) <= y1 and px != cx:
            crossings.append((abs(cx - px), "xmax"))
    if crossings:
        return max(crossings)[1]
    return _side_of(zone, curr)


def _side_of(zone: tuple[float, float, float, float], xy: tuple[float, float]) -> str | None:
    x0, x1, y0, y1 = zone
    x, y = xy
    if _in_zone(zone, xy):
        return None
    return min([(abs(x - x0), "xmin"), (abs(x - x1), "xmax"),
                (abs(y - y0), "ymin"), (abs(y - y1), "ymax")])[1]


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
    failures: list[str] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"status": self.status, "reason": self.reason, "score": self.score,
                "failures": list(self.failures), "detail": self.detail}


class _Obstacle:
    """Common bookkeeping; subclasses implement the rule-specific evidence."""

    name = "abstract"
    zone: tuple[float, float, float, float] = (0, 0, 0, 0)
    ground_fail = False
    # surface tag prefixes/names proving the robot is actually on the obstacle
    surface_tags: tuple[str, ...] = ()
    per_obstacle_score = 100.0

    def __init__(self) -> None:
        self.result = ObstacleResult(self.name)
        self.prev_xy: tuple[float, float] | None = None
        self.prev_in_zone = False
        self.prev_touched = False
        self.supported = False
        self.in_zone_samples = 0
        self.armed = True
        self._reset_evidence()

    # -- hooks ---------------------------------------------------------------
    def _reset_evidence(self) -> None:
        self.evidence: dict[str, Any] = {}

    def _on_first_inside(self, side_prev: str | None, xy: tuple[float, float]) -> None:
        self.evidence["entry_side_prev"] = side_prev

    def _pre_sample(self, bar_z: float | None) -> None:
        """Called every update before zone logic; subclasses may track global state."""
        pass

    def _on_sample(self, xy: tuple[float, float], tags: set[str], ground_feet: set[str],
                   bar_z: float | None, yaw: float) -> None:
        pass

    def _check_exit(self, side: str, tags: set[str], ground_feet: set[str]) -> tuple[bool, str]:
        """Return (success, fail_reason). Empty fail_reason = soft reset (not a failure)."""
        return False, ""

    def _check_immediate(self) -> tuple[bool, str] | None:
        return None

    def _score_for(self) -> float:
        return float(self.per_obstacle_score)

    def _ground_penalty_active(self, xy: tuple[float, float], tags: set[str]) -> bool:
        """Whether 2+ ground feet at this sample count as a traversal failure.

        Default: active after the robot has been fully supported on the obstacle until the
        subclass reports its traversal evidence complete. Landing on the ground after a
        completed/partial traversal must NOT be penalised (GLM review 2026-10-23, B1).
        """
        return self.supported

    def _mark_partial(self) -> None:
        partial = self.result.score < self.per_obstacle_score
        self.result.detail["partial"] = bool(partial)

    def _touched(self, tags: set[str]) -> bool:
        if not self.surface_tags:
            return False
        return any(tag == prefix or tag.startswith(prefix)
                   for tag in tags for prefix in self.surface_tags)

    # -- failure/attempt handling -------------------------------------------
    def _fail(self, reason: str) -> None:
        """Record a failed obstacle attempt; the obstacle can be retried this attempt."""
        self.result.failures.append(reason)
        self.result.status = "pending"
        self.result.reason = ""
        self.result.score = 0.0
        self.result.detail["last_failure"] = reason
        self._reset_evidence()
        self.prev_touched = False
        self.supported = False
        self.armed = False

    # -- update --------------------------------------------------------------
    def update(self, t: float, base_xyz: tuple[float, float, float], yaw: float,
               foot_tags: dict[str, set[str]], ground_feet: set[str],
               bar_z: float | None) -> None:
        if self.result.status in ("success", "skipped"):
            if not (self.result.status == "success"
                    and self.result.score < self.per_obstacle_score
                    and not self.result.detail.get("upgrade_unavailable")):
                return
        self._pre_sample(bar_z)
        xy = (float(base_xyz[0]), float(base_xyz[1]))
        inside = _in_zone(self.zone, xy)
        tags = {tag for values in foot_tags.values() for tag in values}
        if not inside:
            self.armed = True
        if inside and not self.prev_in_zone:
            self.result.status = "running"   # also reopens partial success for upgrade
            entry = _crossing_side(self.zone, self.prev_xy, xy) if self.prev_xy else None
            self._on_first_inside(entry, xy)
        if inside:
            self.in_zone_samples += 1
            self.result.detail["in_zone_samples"] = self.in_zone_samples
            if self.armed:
                touched = self.prev_touched or self._touched(tags)
                self.prev_touched = touched
                if touched and not ground_feet:
                    self.supported = True
                self.result.detail["touched"] = touched
                if (self.ground_fail and self._ground_penalty_active(xy, tags)
                        and len(ground_feet) >= 2):
                    self._fail("two_feet_ground:" + ",".join(sorted(ground_feet)))
                    self.prev_in_zone = inside
                    self.prev_xy = xy
                    return
                self.evidence["touched"] = touched
                self._on_sample(xy, tags, ground_feet, bar_z, yaw)
                imm = self._check_immediate()
                if imm is not None:
                    ok, reason = imm
                    if ok and self.ground_fail and not self.supported:
                        # GLM/flash 2026-10-23: never fully supported on the obstacle means
                        # the robot merely grazed a surface tag while walking on the ground;
                        # such a run must not be accepted as a traversal success.
                        self._fail("insufficient_obstacle_support")
                    elif ok:
                        self.result.status = "success"
                        self.result.reason = ""
                        self.result.score = self._score_for()
                        self._mark_partial()
                    else:
                        self._fail(reason or "failed")
                    self.prev_in_zone = inside
                    self.prev_xy = xy
                    return
        elif self.prev_in_zone and self.result.status == "running":
            side = _crossing_side(self.zone, self.prev_xy, xy) if self.prev_xy else _side_of(self.zone, xy)
            if self.armed:
                ok, reason = self._check_exit(side or "unknown", tags, ground_feet)
                if ok:
                    self.result.status = "success"
                    self.result.reason = ""
                    self.result.score = self._score_for()
                    self._mark_partial()
                elif reason:
                    self._fail(reason)
                elif self.result.detail.get("partial"):
                    self.result.status = "success"   # keep the partial score
                else:
                    self.result.status = "pending"
                    self.result.detail["aborted_exit"] = side
                    self._reset_evidence()
                    self.armed = True
        self.prev_in_zone = inside
        self.prev_xy = xy


class TraversalBridge(_Obstacle):
    """Platform -> bridge surfaces -> opposite platform."""

    ground_fail = True

    def __init__(self, name: str, zone, axis: str, surface_tag: str,
                 platform_tags: tuple[str, str]) -> None:
        self.name, self.zone, self.axis = name, zone, axis
        self.surface_tag = surface_tag
        self.platform_tags = platform_tags
        self.surface_tags = (surface_tag, platform_tags[0], platform_tags[1])
        super().__init__()

    def _reset_evidence(self) -> None:
        self.evidence = {"bridge_hits": 0, "platforms": set()}

    def _on_sample(self, xy, tags, ground_feet, bar_z, yaw) -> None:
        if self.surface_tag in tags:
            self.evidence["bridge_hits"] += 1
        for plat in self.platform_tags:
            if plat in tags:
                self.evidence["platforms"].add(plat)

    def _ground_penalty_active(self, xy, tags) -> bool:
        # reaching the far platform with bridge contact completes the traversal evidence;
        # stepping down onto the ground afterwards is landing, not a failure.
        if not self.supported:
            return False
        return not (self.evidence.get("bridge_hits", 0) >= 3
                    and len(self.evidence.get("platforms", ())) >= 2)

    def _check_exit(self, side: str, tags: set[str], ground_feet: set[str]) -> tuple[bool, str]:
        entry = self.evidence.get("entry_side_prev")
        if entry is None:
            return False, "illegal_entry" if self.in_zone_samples >= 5 else ""
        if side != _opposite(entry):
            return False, "wrong_exit_side"
        if self.evidence.get("bridge_hits", 0) < 3:
            return False, "missing_bridge_contact"
        if len(self.evidence.get("platforms", ())) < 2:
            return False, "missing_platform_evidence"
        return True, ""


class HeightBar(_Obstacle):
    def __init__(self) -> None:
        self.name, self.zone = "height_bar", ZONES["height_bar"]
        self.bar_base_seen: float | None = None
        self.bar_dropped_seen = False
        super().__init__()

    def _pre_sample(self, bar_z: float | None) -> None:
        if bar_z is None:
            return
        if self.bar_base_seen is None:
            self.bar_base_seen = float(bar_z)
        elif self.bar_base_seen - float(bar_z) > BAR_DROP_THRESHOLD_M:
            self.bar_dropped_seen = True

    def _reset_evidence(self) -> None:
        self.evidence = {"cross_valid": 0, "prev_y": None}

    def _on_sample(self, xy, tags, ground_feet, bar_z, yaw) -> None:
        x, y = xy
        if self.bar_dropped_seen:
            self._fail("bar_dropped")
            return
        prev_y = self.evidence.get("prev_y")
        if prev_y is not None and (prev_y - (-9.0)) * (y - (-9.0)) <= 0 and abs(prev_y - y) < 1.0:
            if BAR_OPENING_X[0] <= x <= BAR_OPENING_X[1]:
                self.evidence["cross_valid"] += 1
        self.evidence["prev_y"] = y

    def _check_exit(self, side: str, tags: set[str], ground_feet: set[str]) -> tuple[bool, str]:
        entry = self.evidence.get("entry_side_prev")
        if entry not in ("ymin", "ymax"):
            return False, "illegal_entry_side" if self.in_zone_samples >= 5 else ""
        if side not in ("ymin", "ymax") or side != _opposite(entry):
            return False, "wrong_exit_side"
        if self.evidence["cross_valid"] < 1:
            return False, "no_valid_gate_crossing"
        if self.bar_base_seen is None:
            return False, "bar_state_unknown"
        if self.bar_dropped_seen:
            return False, "bar_dropped"
        return True, ""


class HighWall(_Obstacle):
    def __init__(self) -> None:
        self.name, self.zone = "high_wall", ZONES["high_wall"]
        super().__init__()

    def _reset_evidence(self) -> None:
        self.evidence = {"max_z": 0.0, "wall_contact": False, "cross_valid": 0,
                         "outside_x_cross": 0, "prev_y": None, "prev_x": None}

    def _on_sample(self, xy, tags, ground_feet, bar_z, yaw) -> None:
        x, y = xy
        self.evidence["max_z"] = max(self.evidence["max_z"], self._last_z)
        if "wall" in tags:
            self.evidence["wall_contact"] = True
        prev_y = self.evidence.get("prev_y")
        prev_x = self.evidence.get("prev_x")
        if prev_y is not None and (prev_y - WALL_CROSS_Y) * (y - WALL_CROSS_Y) <= 0:
            if abs(prev_y - y) < 1.0:
                # real climb: base raised well above standing height at the crossing;
                # a sideways wall touch at ground height is not evidence of surmounting.
                raised = self._last_z >= WALL_CLIMB_Z
                within_x = (WALL_X_MIN <= float(prev_x) <= WALL_X_MAX
                            and WALL_X_MIN <= float(x) <= WALL_X_MAX)
                if raised and within_x:
                    self.evidence["cross_valid"] += 1
                elif raised:
                    self.evidence["outside_x_cross"] += 1
                else:
                    self.evidence["ground_cross"] = self.evidence.get("ground_cross", 0) + 1
        self.evidence["prev_y"] = y
        self.evidence["prev_x"] = x

    def update(self, t, base_xyz, yaw, foot_tags, ground_feet, bar_z):
        self._last_z = float(base_xyz[2])
        super().update(t, base_xyz, yaw, foot_tags, ground_feet, bar_z)

    def _check_exit(self, side: str, tags: set[str], ground_feet: set[str]) -> tuple[bool, str]:
        entry = self.evidence.get("entry_side_prev")
        if entry not in ("ymin", "ymax"):
            return False, "illegal_entry_side" if self.in_zone_samples >= 5 else ""
        if side not in ("ymin", "ymax") or side != _opposite(entry):
            return False, "wrong_exit_side"
        if self.evidence["cross_valid"] < 1:
            return False, "no_climb_crossing"
        return True, ""


class GravelPit(_Obstacle):
    surface_tags = ("gravel",)
    ground_fail = True

    def __init__(self) -> None:
        self.name, self.zone = "gravel_pit", ZONES["gravel_pit"]
        super().__init__()

    def _reset_evidence(self) -> None:
        self.evidence = {"gravel_hits": 0}

    def _on_sample(self, xy, tags, ground_feet, bar_z, yaw) -> None:
        if "gravel" in tags:
            self.evidence["gravel_hits"] += 1

    def _ground_penalty_active(self, xy, tags) -> bool:
        if not self.supported or self.evidence.get("gravel_hits", 0) < 3:
            return bool(self.supported)
        entry = self.evidence.get("entry_side_prev")
        zx0, zx1, zy0, zy1 = self.zone
        if entry == "ymin":
            return not (xy[1] >= zy1 - EXIT_GRACE_M)
        if entry == "ymax":
            return not (xy[1] <= zy0 + EXIT_GRACE_M)
        return True

    def _check_exit(self, side: str, tags: set[str], ground_feet: set[str]) -> tuple[bool, str]:
        entry = self.evidence.get("entry_side_prev")
        if entry not in ("ymin", "ymax"):
            return False, "illegal_entry_side" if self.in_zone_samples >= 5 else ""
        if side not in ("ymin", "ymax"):
            return False, "illegal_exit_side" if self.in_zone_samples >= 5 else ""
        if side == entry:
            return False, "no_crossing"
        if self.evidence["gravel_hits"] < 3:
            return False, "missing_gravel_contact"
        return True, ""


class Slope(_Obstacle):
    surface_tags = ("slope",)
    ground_fail = True

    def __init__(self) -> None:
        self.name, self.zone = "slope", ZONES["slope"]
        super().__init__()

    def _reset_evidence(self) -> None:
        self.evidence = {"distance": 0.0, "last_y": None}

    def _on_sample(self, xy, tags, ground_feet, bar_z, yaw) -> None:
        x, y = xy
        if "slope" in tags:
            last_y = self.evidence.get("last_y")
            if last_y is not None:
                self.evidence["distance"] += abs(y - last_y)   # projection on long axis
            self.evidence["last_y"] = y
        else:
            self.evidence["last_y"] = None

    def _ground_penalty_active(self, xy, tags) -> bool:
        if not self.supported:
            return False
        return self.evidence.get("distance", 0.0) < 1.0

    def _check_exit(self, side: str, tags: set[str], ground_feet: set[str]) -> tuple[bool, str]:
        if self.evidence["distance"] < 1.0:
            return False, ""
        return True, ""


class TStairs(_Obstacle):
    """T-shaped stairs: three arms (south / north / east) meet at the top platform.

    Tags: ``step:s:1..3``, ``step:n:1..3``, ``step:e:1..3``, ``step:top``.
    Full success = two different arms each with levels 1,2,3 visited + top + returned
    to the ground. One complete arm + top = partial score (Q2 x2/3: up/s = 50, down/n,e = 33).
    """

    surface_tags = ("step:",)
    ground_fail = True

    def __init__(self, partial_up: float = 50.0, partial_down: float = 33.0,
                 max_score: float = 100.0) -> None:
        self.name, self.zone = "t_stairs", ZONES["t_stairs"]
        self.partial_up, self.partial_down, self.max_score = partial_up, partial_down, max_score
        super().__init__()

    def _reset_evidence(self) -> None:
        self.evidence = {"arms": {}, "top": False, "entry_arm": None, "exit_arm": None}

    def _step_tags(self, tags: set[str]) -> list[str]:
        return [t for t in tags if t.startswith("step:")]

    def _on_sample(self, xy, tags, ground_feet, bar_z, yaw) -> None:
        for tag in self._step_tags(tags):
            parts = tag.split(":")
            if len(parts) == 2:  # step:top
                self.evidence["top"] = True
                continue
            _, arm, level = parts
            self.evidence["arms"].setdefault(arm, set()).add(int(level))
            if self.evidence["entry_arm"] is None:
                self.evidence["entry_arm"] = arm
            self.evidence["exit_arm"] = arm
        self.result.detail["arms"] = {k: sorted(v) for k, v in self.evidence["arms"].items()}

    def _complete_arms(self) -> list[str]:
        return [arm for arm, levels in self.evidence["arms"].items() if levels >= {1, 2, 3}]

    def _has_incomplete_arm(self) -> bool:
        return any(levels and levels < {1, 2, 3} for levels in self.evidence["arms"].values())

    def _ground_penalty_active(self, xy, tags) -> bool:
        if not self.supported:
            return False
        return not (self.evidence.get("top") and len(self._complete_arms()) >= 1)

    def _score_for(self) -> float:
        complete = self._complete_arms()
        if len(complete) >= 2:
            return float(min(self.max_score, self.per_obstacle_score))
        if len(complete) == 1:
            arm = complete[0]
            raw = self.partial_up if arm == "s" else self.partial_down
            return float(min(raw, self.max_score))
        return 0.0

    def _check_exit(self, side: str, tags: set[str], ground_feet: set[str]) -> tuple[bool, str]:
        ev = self.evidence
        if not ev["top"]:
            return False, "" if self.in_zone_samples < 5 else "missing_top_platform"
        if not self._complete_arms():
            return False, "incomplete_step_history"
        if self._has_incomplete_arm():
            # a skipped level on any arm is not a legal partial/full traversal
            return False, "incomplete_step_history"
        return True, ""


class Slalom(_Obstacle):
    """Slalom: start in one beya circle, alternate sides around the poles in order,
    pass the corner checkpoint at the turn, finish in the other beya circle.

    Direction is inferred from the start circle: A -> posts 0,1,2,3; B -> 3,2,1,0.
    """

    def __init__(self) -> None:
        self.name, self.zone = "slalom", ZONES["slalom"]
        super().__init__()

    def _reset_evidence(self) -> None:
        self.evidence = {"start_area": None, "order": [], "order_expected": [],
                         "sides": [], "corner": False, "end_area": None,
                         "corner_after": None, "corner_visits": []}

    def _near(self, xy, point, radius=SLALOM_RADIUS_M) -> bool:
        return _dist(xy, point) <= radius

    def _on_sample(self, xy, tags, ground_feet, bar_z, yaw) -> None:
        ev = self.evidence
        done_before = len(ev["order"])
        if ev["start_area"] is None:
            if self._near(xy, SLALOM_START_A):
                ev["start_area"] = "A"
                ev["order_expected"] = [0, 1, 2, 3]
            elif self._near(xy, SLALOM_START_B):
                ev["start_area"] = "B"
                ev["order_expected"] = [3, 2, 1, 0]
        expected = ev["order_expected"]
        idx = len(ev["order"])
        if idx < len(expected):
            target = expected[idx]
            post = SLALOM_POSTS[target]
            if self._near(xy, post, SLALOM_POST_RADIUS_M):
                ev["order"].append(target)
                ref = SLALOM_START_A if ev["start_area"] == "A" else SLALOM_START_B
                if idx >= 1:
                    ref = SLALOM_POSTS[expected[idx - 1]]
                tx, ty = post[0] - ref[0], post[1] - ref[1]
                nx, ny = -ty, tx
                ev["sides"].append(_sign(nx * (xy[0] - post[0]) + ny * (xy[1] - post[1])))
        expected_corner_after = 3 if ev["start_area"] == "A" else 2
        if (self._near(xy, SLALOM_CORNER, SLALOM_CORNER_RADIUS_M)
                and ev["start_area"] is not None and len(ev["order"]) >= 2):
            # the rules only require passing the corner checkpoint, not a single fixed
            # moment; keep every visit so an early sweep cannot lock out the legal pass.
            if len(ev["order"]) not in ev["corner_visits"]:
                ev["corner_visits"].append(len(ev["order"]))
            ev["corner"] = True
            if len(ev["order"]) == expected_corner_after:
                ev["corner_after"] = len(ev["order"])
        # the end circle is only a valid finish if all four posts were already
        # registered before this sample (not in the same sample as the last post,
        # which can be geometrically inside the end circle)
        if done_before == 4 and ev["corner"]:
            if ev["start_area"] == "A" and self._near(xy, SLALOM_START_B):
                ev["end_area"] = "B"
            elif ev["start_area"] == "B" and self._near(xy, SLALOM_START_A):
                ev["end_area"] = "A"

    def _check_immediate(self):
        ev = self.evidence
        expected_corner_after = 3 if ev["start_area"] == "A" else 2
        if (ev["start_area"] and ev["end_area"] and len(ev["order"]) == 4
                and expected_corner_after in ev["corner_visits"]
                and all(a * b < 0 for a, b in zip(ev["sides"], ev["sides"][1:]))):
            return True, ""
        return None

    def _check_exit(self, side: str, tags: set[str], ground_feet: set[str]) -> tuple[bool, str]:
        ev = self.evidence
        if not ev["start_area"]:
            return False, "" if self.in_zone_samples < 5 else "no_start_area"
        if len(ev["order"]) < 4:
            return False, "missing_posts"
        if not ev["corner"]:
            return False, "missing_corner_checkpoint"
        if not ev["end_area"]:
            return False, "no_end_area"
        expected_corner_after = 3 if ev["start_area"] == "A" else 2
        if expected_corner_after not in ev["corner_visits"]:
            return False, "corner_out_of_order"
        if not all(a * b < 0 for a, b in zip(ev["sides"], ev["sides"][1:])):
            return False, "not_s_shaped_sides"
        return True, ""


# ---------------------------------------------------------------- aggregate judge

class Part1JudgeV2:
    """One instance judges one continuous course attempt."""

    def __init__(self, *, partial_up: float = 50.0, partial_down: float = 33.0,
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
        self.bar_base: float | None = None
        self.bar_dropped = False
        self.all_full_done = False
        self.start_area_entries: list[float] = []
        self.return_after_full = False
        self.prev_start_inside = False

    def update(self, t: float, base_xyz, yaw: float = 0.0, *,
               foot_tags: dict[str, set[str]] | None = None,
               ground_feet: set[str] | None = None,
               bar_z: float | None = None) -> dict:
        foot_tags = foot_tags or {}
        ground_feet = ground_feet or set()
        self.t = float(t)
        if bar_z is not None:
            if self.bar_base is None:
                self.bar_base = float(bar_z)
            elif self.bar_base - float(bar_z) > BAR_DROP_THRESHOLD_M:
                self.bar_dropped = True
        for obs in self.obstacles.values():
            obs.update(self.t, base_xyz, yaw, foot_tags, ground_feet, bar_z)
        in_start = _in_zone(ZONES["start_area"], (float(base_xyz[0]), float(base_xyz[1])))
        if in_start and not self.prev_start_inside:
            self.start_area_entries.append(self.t)
            if self.all_full_done:
                self.return_after_full = True
        self.prev_start_inside = in_start
        if not self.all_full_done and all(
                o.result.status == "success" and o.result.score >= o.per_obstacle_score
                for o in self.obstacles.values()):
            self.all_full_done = True
        return self.report()

    def report(self) -> dict:
        obstacles = {name: o.result.to_dict() for name, o in self.obstacles.items()}
        obstacle_total = sum(o.result.score for o in self.obstacles.values())
        return_bonus = 100.0 if self.return_after_full else 0.0
        return {
            "score": obstacle_total + return_bonus,
            "obstacle_score": obstacle_total,
            "return_bonus": return_bonus,
            "returned_to_start": self.return_after_full,
            "all_full_success": self.all_full_done,
            "bar_dropped": self.bar_dropped,
            "states": obstacles,
            "statuses": {name: o.result.status for name, o in self.obstacles.items()},
        }

    def finalize(self, reason: str = "timeout") -> dict:
        for obs in self.obstacles.values():
            if obs.result.status in ("pending", "running"):
                obs.result.status = "fail"
                obs.result.reason = obs.result.detail.get("last_failure") or reason
        return self.report()


# ---------------------------------------------------------------- attempts ledger

class AttemptManager:
    """Whole-run attempt bookkeeping per organizer answers (2026-10-22)."""

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
        self._current["pauses"].append([float(t), float(t)])
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
        best_candidates = [a for a in scored if a["score"] == best_score]
        fastest = min((a["duration_s"] for a in best_candidates), default=0.0)
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
                      "final_time": "min_duration_among_best_score_attempts"},
        }


if __name__ == "__main__":
    print(json.dumps(Part1JudgeV2().report(), ensure_ascii=False, indent=2))
