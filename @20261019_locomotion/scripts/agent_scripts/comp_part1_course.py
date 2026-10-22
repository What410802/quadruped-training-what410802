"""Formal Part 1 whole-course attempt protocol (attempts + timer + return bonus).

The course itself is driven externally (scripted diagnostic route or a human operator
through the control stack); this module owns the *rule bookkeeping*:

- one attempt = one continuous run over the Part 1 field; judge states are fed in
  continuously through ``Part1JudgeV2``;
- 3 attempts per run; a fall with pause+recovery does NOT consume an attempt and the
  paused wall time is excluded from the attempt duration;
- starting/restarting and operator skip consume an attempt (current organizer reading);
- obstacle-level skip (the course offers skip for unpassable obstacles) marks that
  obstacle failed/skipped but the attempt continues;
- attempt score = sum of obstacle scores + 100 return bonus iff all 8 obstacles
  succeeded AND the robot re-entered the start area after the last success;
- final score = best attempt score; final time = fastest attempt duration.

This module is pure Python and conformance-tested in ``comp_course_conformance.py``;
the MuJoCo runner only has to stream ``update`` calls and operator events.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from comp_part1_judge import ZONES, AttemptManager, Part1JudgeV2

MAX_ATTEMPTS = 3
RETURN_BONUS = 100.0


@dataclass
class AttemptResult:
    attempt: int
    score: float = 0.0
    obstacle_score: float = 0.0
    return_bonus: float = 0.0
    duration_s: float = 0.0
    skipped: bool = False
    reason: str = ""
    events: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"attempt": self.attempt, "score": self.score,
                "obstacle_score": self.obstacle_score, "return_bonus": self.return_bonus,
                "duration_s": self.duration_s, "skipped": self.skipped,
                "reason": self.reason, "events": self.events}


class Part1Course:
    """One whole-run session (up to 3 attempts) with pause/recovery/skip events."""

    def __init__(self, max_attempts: int = MAX_ATTEMPTS,
                 partial_up: float = 75.0, partial_down: float = 50.0) -> None:
        self.manager = AttemptManager(max_attempts=max_attempts)
        self.judge = Part1JudgeV2(partial_up=partial_up, partial_down=partial_down)
        self.partial_up = partial_up
        self.partial_down = partial_down
        self.active = False
        self.attempt_no = 0
        self.active_time = 0.0
        self.paused = False
        self.prev_t: float | None = None
        self.results: list[AttemptResult] = []
        self._current_events: list[dict] = []
        self._start_area_hits = 0
        self._prev_in_start = False

    # ---------------------------------------------------------------- lifecycle
    def begin_attempt(self, t: float) -> bool:
        if self.active:
            raise RuntimeError("attempt already running")
        if not self.manager.begin(t):
            return False
        self.judge = Part1JudgeV2(partial_up=self.partial_up, partial_down=self.partial_down)
        self.active = True
        self.attempt_no += 1
        self.active_time = 0.0
        self.paused = False
        self.prev_t = float(t)
        self._start_area_hits = 0
        self._prev_in_start = False
        self._current_events = []
        return True

    def update(self, t: float, base_xyz, yaw: float = 0.0, **kwargs) -> dict:
        if not self.active:
            raise RuntimeError("no active attempt; call begin_attempt() first")
        t = float(t)
        if not self.paused and self.prev_t is not None:
            dt = max(0.0, t - self.prev_t)
            self.active_time += dt
        self.prev_t = t
        report = self.judge.update(t, base_xyz, yaw, **kwargs)
        in_start = (ZONES["start_area"][0] <= base_xyz[0] <= ZONES["start_area"][1]
                    and ZONES["start_area"][2] <= base_xyz[1] <= ZONES["start_area"][3])
        if in_start and not self._prev_in_start:
            self._start_area_hits += 1
        self._prev_in_start = in_start
        return report

    def pause(self, t: float) -> None:
        """Fall detected -> timer paused (does not consume an attempt by itself)."""
        if not self.active or self.paused:
            return
        self.paused = True
        self._current_events.append({"t": float(t), "event": "pause"})
        self.manager.note_recovery(t)

    def resume(self, t: float, base_xyz=None, yaw: float = 0.0) -> None:
        if not self.active or not self.paused:
            return
        self.paused = False
        self.prev_t = float(t)
        self._current_events.append({"t": float(t), "event": "resume",
                                     "pose": list(base_xyz) if base_xyz is not None else None})

    def skip_obstacle(self, t: float, name: str) -> None:
        if not self.active:
            raise RuntimeError("no active attempt")
        obs = self.judge.obstacles.get(name)
        if obs is None:
            raise KeyError(name)
        if obs.result.status in ("success", "fail"):
            return
        obs.result.status = "skipped"
        obs.result.reason = "operator_skip"
        self._current_events.append({"t": float(t), "event": "skip_obstacle", "obstacle": name})

    def end_attempt(self, t: float, reason: str = "finished") -> AttemptResult:
        if not self.active:
            raise RuntimeError("no active attempt")
        self.judge.finalize(reason)
        report = self.judge.report()
        obstacle_score = float(report["obstacle_score"])
        # return bonus requires *full* obstacle scores: a partial (e.g. T-stairs one side)
        # does not count as "越过全部障碍"
        all_full = all(s["status"] == "success" and float(s["score"]) >= 100.0
                       for s in report["states"].values())
        returned = all_full and self._start_area_hits >= 2
        return_bonus = RETURN_BONUS if returned else 0.0
        score = obstacle_score + return_bonus
        result = AttemptResult(attempt=self.attempt_no, score=score, obstacle_score=obstacle_score,
                               return_bonus=return_bonus, duration_s=self.active_time,
                               skipped=False, reason=reason, events=list(self._current_events))
        attempt_report = {"score": score, "obstacle_score": obstacle_score,
                          "return_bonus": return_bonus}
        self.results.append(result)
        self.manager.end(t, attempt_report, reason=reason)
        # attempt duration in the ledger must be the *active* time (pause excluded)
        self.manager.attempts[-1]["duration_s"] = result.duration_s
        self.manager.attempts[-1]["duration_note"] = "active_time_pause_excluded"
        self.active = False
        self.paused = False
        return result

    def abort_attempt(self, t: float, reason: str = "operator_abort") -> AttemptResult:
        """Operator abort/restart: consumes the attempt, score 0."""
        if not self.active:
            raise RuntimeError("no active attempt")
        result = AttemptResult(attempt=self.attempt_no, score=0.0, duration_s=self.active_time,
                               skipped=True, reason=reason, events=list(self._current_events))
        self.manager.skip(t, reason=reason)
        self.manager.attempts[-1]["duration_s"] = result.duration_s
        self.manager.attempts[-1]["duration_note"] = "active_time_pause_excluded"
        self.results.append(result)
        self.active = False
        self.paused = False
        return result

    # ---------------------------------------------------------------- results
    def summary(self) -> dict:
        summary = self.manager.summary()
        summary["attempt_results"] = [r.to_dict() for r in self.results]
        summary["final_score"] = max((r.score for r in self.results if not r.skipped), default=0.0)
        summary["final_time_s"] = min((r.duration_s for r in self.results if not r.skipped),
                                      default=0.0)
        summary["attempts_allowed"] = self.manager.max_attempts
        return summary

    def export_report(self) -> dict:
        return {"summary": self.summary(),
                "rules": {"return_bonus": RETURN_BONUS,
                          "recovery_consumes_attempt": False,
                          "skip_obstacle_consumes_attempt": False,
                          "final_score": "best_attempt",
                          "final_time": "min_over_attempts"}}


# ---------------------------------------------------------------- self-test
def _mk_update(course: Part1Course, t: float, x: float, y: float, z: float = 0.45,
               tags: dict | None = None, ground: set | None = None, bar_z: float = 0.325) -> dict:
    return course.update(t, (x, y, z), 0.0, foot_tags=tags or {}, ground_feet=ground or set(),
                         bar_z=bar_z)


def run_self_test() -> None:
    # One successful attempt: feed legal traversals for all 8 obstacles, then return.
    c = Part1Course()
    assert c.begin_attempt(0.0)
    t = 0.0

    def step(x, y, tags=None, ground=None, z=0.45, dt=0.05):
        nonlocal t
        t += dt
        return _mk_update(c, t, x, y, z, tags=tags or {}, ground=ground or set())

    # bridge_blocks (x axis)
    for x, tag in [(0.5, None), (1.3, "platform_left"), (2.2, "bridge"), (3.2, "bridge"),
                   (4.2, "bridge"), (5.2, "bridge"), (5.6, "platform_right"), (6.4, None)]:
        step(x, 0.0, tags={tag: {tag}} if tag else {}, z=0.65)
    # bridge_bands (y axis)
    for y, tag in [(-4.2, None), (-3.5, "platform_low"), (-2.5, "bridge"), (-2.0, "bridge"),
                   (-1.6, "bridge"), (-1.2, "bridge"), (-0.9, "platform_high"), (-0.7, None)]:
        step(5.7, y, tags={tag: {tag}} if tag else {}, z=0.65)
    # height_bar (y axis, through opening)
    for y in (-10.4, -10.0, -9.5, -9.0, -8.5, -8.2):
        step(5.7, y)
    # high_wall (y axis with climb evidence)
    for y, z in [(-7.9, 0.45), (-7.4, 0.75), (-7.0, 0.85), (-6.6, 0.75), (-6.0, 0.45)]:
        step(1.8, y, tags={"wall": {"wall"}} if 0.6 <= z else {}, z=z)
    # gravel (short edges y)
    for y, tag in [(-13.4, None), (-12.9, "gravel"), (-12.0, "gravel"), (-11.5, "gravel"),
                   (-11.0, "gravel"), (-10.8, None)]:
        step(5.5, y, tags={tag: {tag}} if tag else {})
    # t_stairs (y arm up -> top -> x arm down)
    for y, tag in [(-5.4, None), (-4.9, "step:y:1"), (-4.6, "step:y:2"), (-4.3, "step:y:3"),
                   (-3.8, "step:top"), (-3.5, None)]:
        step(1.8, y, tags={tag: {tag}} if tag else {}, z=0.65)
    for x, tag in [(2.2, "step:x:3"), (2.6, "step:x:2"), (2.9, "step:x:1"), (3.4, None)]:
        step(x, -3.5, tags={tag: {tag}} if tag else {}, z=0.65)
    # slope (y travel on slope with >=1 m distance)
    step(3.6, -5.0)  # approach outside the slope zone
    for i in range(1, 16):
        step(5.2, -6.5 + 0.1 * i, tags={"slope": {"slope"}}, z=0.55)
    step(3.6, -5.0)
    # slalom
    for x, y in [(1.8, -10.1), (1.9, -10.5), (1.7, -11.0), (1.7, -11.5), (1.9, -12.0),
                 (1.9, -12.5), (1.55, -12.75), (2.4, -12.6), (2.8, -12.6), (3.2, -12.5)]:
        step(x, y)
    # return to start area: first entry, leave, then re-enter (second entry)
    step(3.7, -9.0)
    step(2.8, -9.0)   # outside start area
    step(3.7, -9.0)
    result = c.end_attempt(t)
    assert result.score == 900.0, result.to_dict()
    summary = c.summary()
    assert summary["final_score"] == 900.0, summary
    assert summary["attempts_used"] == 1, summary
    assert summary["final_time_s"] == result.duration_s, summary
    assert abs(c.manager.attempts[0]["duration_s"] - result.duration_s) < 1e-9, c.manager.attempts[0]

    # Attempt 2: pause/recovery not consuming; then abort consumes; attempt 3 unused after.
    assert c.begin_attempt(t)
    step(3.7, -9.0)
    c.pause(t)
    t += 5.0                      # paused wall time must not count
    c.resume(t, (3.5, -9.0))
    t += 0.1
    result2 = c.abort_attempt(t, "restart")
    assert result2.skipped and result2.score == 0.0
    summary = c.summary()
    assert summary["attempts_used"] == 2, summary
    assert summary["recoveries"] == 1, summary
    assert abs(summary["attempt_results"][1]["duration_s"] - result2.duration_s) < 1e-9
    assert summary["attempt_results"][1]["duration_s"] < 1.0, \
        "paused wall time must be excluded from the attempt duration"
    assert c.begin_attempt(t + 1.0), "attempt 3 must be available"
    t += 1.2
    step(3.7, -9.0)
    c.abort_attempt(t, "operator_abort")
    summary = c.summary()
    assert summary["attempts_used"] == 3, summary
    assert not c.begin_attempt(t + 2.0), "4th attempt must be rejected"
    assert summary["final_score"] == 900.0, summary

    # Partial obstacle (T-stairs one side) must NOT trigger the return bonus.
    c2 = Part1Course()
    assert c2.begin_attempt(0.0)
    for name, obs in c2.judge.obstacles.items():
        obs.result.status = "success"
        obs.result.score = 50.0 if name == "t_stairs" else 100.0
    c2.update(0.0, (3.7, -9.0, 0.45), 0.0)   # first entry into start area
    c2.update(0.1, (2.8, -9.0, 0.45), 0.0)   # leave
    c2.update(0.2, (3.7, -9.0, 0.45), 0.0)   # re-enter
    r2 = c2.end_attempt(0.3)
    assert r2.return_bonus == 0.0, r2.to_dict()
    assert r2.score == 750.0, r2.to_dict()
    print("comp_part1_course self-test: OK", json.dumps(summary["rules"], ensure_ascii=False))


if __name__ == "__main__":
    run_self_test()
