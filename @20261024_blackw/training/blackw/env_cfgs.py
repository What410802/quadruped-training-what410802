"""blackW wheel-legged task assembly (first milestone: flat velocity tracking).

This module starts from the validated Black flat task and replaces exactly the
robot / wheels' action interface / observation contract / reset events. The
reward, command and termination wiring stay on the Black baseline so the first
blackW policy can be trained and evaluated end-to-end before adding competition
terrain.
"""

from __future__ import annotations

from dataclasses import replace

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.envs import mdp as envs_mdp
from mjlab.envs.mdp.events import reset_joints_by_offset
from mjlab.managers import EventTermCfg, ObservationTermCfg, RewardTermCfg, TerminationTermCfg
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.sensor import ContactMatch, ContactSensorCfg

from alldog_mjlab.robots.blackw import (
    BLACKW_FOOT_NAMES,
    BLACKW_JOINT_NAMES,
    BLACKW_WHEEL_JOINTS,
    get_blackw_robot_cfg,
)
from alldog_mjlab.tasks.velocity.black.env_cfgs import (
    _build_black_env_cfg,
    black_competition_env_cfg,
)
from alldog_mjlab.tasks.velocity.black.competition_rewards import (
    _goal_positions,
    competition_goal_progress,
    competition_goal_reward,
)
from alldog_mjlab.tasks.velocity.blackw.actions import WheelLegActionCfg
from mjlab.terrains.terrain_generator import FlatPatchSamplingCfg

from alldog_mjlab.tasks.velocity.blackw.exact_terrain import (
    ExactHighPlatformTerrainCfg,
    ExactHighWallTerrainCfg,
    ExactPlumTerrainCfg,
    ExactSlopeTerrainCfg,
    ExactStairsTerrainCfg,
    ExactTrenchTerrainCfg,
)

BLACKW_ACTION_TERM_ORDER = tuple(f"wheel_leg_{leg.lower()}" for leg in BLACKW_FOOT_NAMES)
BLACKW_ACTOR_OBS_TERM_ORDER = (
    "command",
    "base_ang_vel",
    "projected_gravity",
    "joint_pos",
    "joint_vel",
    "actions",
)
BLACKW_ACTOR_HISTORY_LENGTH = 6
BLACKW_ACTOR_OBS_SCALE = {
    "command": (2.0, 2.0, 0.25),
    "base_ang_vel": 0.25,
    "projected_gravity": 1.0,
    "joint_pos": 1.0,
    "joint_vel": 0.05,
    "actions": 1.0,
}


def _wheel_leg_scale(leg: str) -> dict[str, float]:
    # The official blackW deployment contract mirrors the wheel action sign on the
    # right legs (rl_sar action_scale = -10 for FR/RR); training must use the same
    # convention or the official HIM warm start drives the right wheels backwards.
    return {
        f"{leg}_hip_joint": 0.25,
        f"{leg}_thigh_joint": 0.25,
        f"{leg}_calf_joint": 0.25,
        f"{leg}_wheel_joint": -10.0 if leg in ("FR", "RR") else 10.0,
    }


def _blackw_joint_pos_rel(env, asset_cfg: SceneEntityCfg, biased: bool = False):
    """Joint position error, with wheel positions forced to zero (official contract)."""
    obs = envs_mdp.joint_pos_rel(env, asset_cfg=asset_cfg, biased=biased)
    names = asset_cfg.joint_names
    wheel_cols = [i for i, name in enumerate(names) if name in BLACKW_WHEEL_JOINTS]
    if wheel_cols:
        obs = obs.clone()
        obs[:, wheel_cols] = 0.0
    return obs


def _override_robot(cfg: ManagerBasedRlEnvCfg) -> None:
    cfg.scene.entities = {"robot": get_blackw_robot_cfg()}


def _override_sensors(cfg: ManagerBasedRlEnvCfg) -> None:
    sensors = []
    for sensor in cfg.scene.sensors or ():
        if sensor.name == "foot_height_scan":
            continue  # blackW has no foot sites; clearance reward is removed below
        if sensor.name == "feet_ground_contact" and isinstance(sensor, ContactSensorCfg):
            sensor.primary = ContactMatch(
                mode="body",
                pattern=tuple(f"{leg}_foot" for leg in BLACKW_FOOT_NAMES),
                entity="robot",
            )
        sensors.append(sensor)
    cfg.scene.sensors = tuple(sensors)


def _override_actions(cfg: ManagerBasedRlEnvCfg) -> None:
    cfg.actions = {
        f"wheel_leg_{leg.lower()}": WheelLegActionCfg(
            entity_name="robot",
            actuator_names=tuple(
                f"{leg}_{joint}_joint" for joint in ("hip", "thigh", "calf", "wheel")
            ),
            scale=_wheel_leg_scale(leg),
            preserve_order=True,
        )
        for leg in BLACKW_FOOT_NAMES
    }


def _override_observations(cfg: ManagerBasedRlEnvCfg) -> None:
    actor = cfg.observations["actor"]
    actor.history_length = BLACKW_ACTOR_HISTORY_LENGTH
    actor.flatten_history_dim = True
    terms = actor.terms
    terms["joint_pos"] = replace(
        terms["joint_pos"],
        func=_blackw_joint_pos_rel,
        params={
            **terms["joint_pos"].params,
            "asset_cfg": SceneEntityCfg(
                "robot", joint_names=BLACKW_JOINT_NAMES, preserve_order=True
            ),
        },
    )
    terms["joint_vel"] = replace(
        terms["joint_vel"],
        func=envs_mdp.joint_vel_rel,
        params={
            **terms["joint_vel"].params,
            "asset_cfg": SceneEntityCfg(
                "robot", joint_names=BLACKW_JOINT_NAMES, preserve_order=True
            ),
        },
    )
    # blackW's IMU sensor is named imu_gyro, not the black XML's imu_ang_vel; use the
    # entity-state observations instead of the base config's builtin-sensor terms.
    terms["base_ang_vel"] = replace(
        terms["base_ang_vel"], func=envs_mdp.base_ang_vel, params={}
    )
    terms["projected_gravity"] = replace(
        terms["projected_gravity"], func=envs_mdp.projected_gravity, params={}
    )
    actor.terms = {name: terms[name] for name in BLACKW_ACTOR_OBS_TERM_ORDER}
    for name, scale in BLACKW_ACTOR_OBS_SCALE.items():
        actor.terms[name] = replace(actor.terms[name], scale=scale)

    joint_obs = ObservationTermCfg(
        func=envs_mdp.joint_pos_rel,
        params={
            "asset_cfg": SceneEntityCfg(
                "robot", joint_names=BLACKW_JOINT_NAMES, preserve_order=True
            )
        },
    )
    joint_vel_obs = ObservationTermCfg(
        func=envs_mdp.joint_vel_rel,
        params={
            "asset_cfg": SceneEntityCfg(
                "robot", joint_names=BLACKW_JOINT_NAMES, preserve_order=True
            )
        },
    )
    cfg.observations["critic"] = replace(
        cfg.observations["critic"],
        terms={
            "base_lin_vel": ObservationTermCfg(func=envs_mdp.base_lin_vel),
            "base_ang_vel": ObservationTermCfg(func=envs_mdp.base_ang_vel),
            "projected_gravity": ObservationTermCfg(func=envs_mdp.projected_gravity),
            "joint_pos": joint_obs,
            "joint_vel": joint_vel_obs,
            "actions": ObservationTermCfg(func=envs_mdp.last_action),
            "command": ObservationTermCfg(
                func=envs_mdp.generated_commands,
                params={"command_name": "twist"},
            ),
            "height_scan": ObservationTermCfg(
                func=envs_mdp.height_scan,
                params={"sensor_name": "terrain_scan"},
                scale=0.2,
            ),
        },
    )


def _override_events(cfg: ManagerBasedRlEnvCfg) -> None:
    reset_base = cfg.events["reset_base"]
    cfg.events = {
        "reset_base": reset_base,
        "reset_robot_joints": EventTermCfg(
            func=reset_joints_by_offset,
            mode="reset",
            params={
                "position_range": (-0.03, 0.03),
                "velocity_range": (-1.0, 1.0),
                "asset_cfg": SceneEntityCfg("robot", joint_names=BLACKW_JOINT_NAMES),
            },
        ),
    }





def _course_progress_reward(
    env,
    goal_name: str = "goal",
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
):
    """Progress reward that stops paying once the goal x line is crossed.

    ``competition_goal_progress`` saturates at 1.0 after crossing the goal line,
    so a policy can farm it (and ``climb_height``) by camping past the obstacle
    instead of finishing it.  Masking keeps the dense signal strictly pre-goal.
    """
    import torch

    base = competition_goal_progress(env, goal_name=goal_name, asset_cfg=asset_cfg)
    goal_data = _goal_positions(env, goal_name)
    if goal_data is None:
        return base
    goal, valid = goal_data
    root_x = env.scene[asset_cfg.name].data.root_link_pos_w[:, 0]
    mask = (root_x <= goal[:, 0]) & valid
    return base * mask.to(base.dtype)


def _course_climb_reward(
    env,
    goal_name: str = "goal",
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
):
    """Climb-height shaping that only pays before the goal line is crossed."""
    import torch

    base = _climb_height_reward(env, asset_cfg=asset_cfg)
    goal_data = _goal_positions(env, goal_name)
    if goal_data is None:
        return base
    goal, valid = goal_data
    root_x = env.scene[asset_cfg.name].data.root_link_pos_w[:, 0]
    mask = (root_x <= goal[:, 0]) & valid
    return base * mask.to(base.dtype)


def _out_of_course(
    env,
    goal_name: str = "goal",
    margin: float = 0.8,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
):
    """Termination: robot ran past the obstacle without satisfying success.

    Prevents post-goal reward farming (goal/progress terms saturate) and keeps
    the robot on the obstacle patch instead of wandering over the flat border.
    """
    import torch

    asset = env.scene[asset_cfg.name]
    reward = torch.zeros(env.num_envs, dtype=torch.bool, device=env.device)
    goal_data = _goal_positions(env, goal_name)
    if goal_data is None:
        return reward
    goal, valid = goal_data
    root_x = asset.data.root_link_pos_w[:, 0]
    return valid & (root_x > goal[:, 0] + margin)



def _plum_foothold_reward(
    env,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    wheel_radius: float = 0.103,
    cube_x_lo: float = 3.90,
    cube_x_hi: float = 11.00,
):
    """Dense foothold shaping for the plum field: reward wheels standing on piles.

    Blind policies cannot see the gaps; a fixed periodic pile field still lets a
    timed gait work.  This term pays in proportion to how many wheels are on a
    pile top (wheel bottom in [0.14, 0.34] m) while the robot is over the field.
    """
    import torch

    asset = env.scene[asset_cfg.name]
    terrain = env.scene.terrain
    origins = terrain.env_origins
    origins = origins if isinstance(origins, torch.Tensor) else torch.as_tensor(
        origins, device=env.device)
    origins = origins.to(env.device)
    body_names = asset.body_names
    wheel_ids = [body_names.index(f"{leg}_foot") for leg in ("FL", "FR", "RL", "RR")]
    wpos = asset.data.body_link_pos_w[:, wheel_ids, :]
    wx = wpos[..., 0] - origins[:, 0:1]
    wz = wpos[..., 2] - wheel_radius
    in_field = (wx >= cube_x_lo) & (wx <= cube_x_hi)
    on_pile = in_field & (wz >= 0.14) & (wz <= 0.34)
    frac = on_pile.to(torch.float32).mean(dim=1)
    return frac * in_field.any(dim=1).to(torch.float32)



def _course_progress_delta(
    env,
    goal_name: str = "goal",
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    scale: float = 1.0,
):
    """Potential-based progress shaping: pay only the *increase* of goal progress.

    State-based progress (``competition_goal_progress``) pays every step while a
    policy stands still anywhere ahead of spawn, which is farmable; the delta
    form is a potential (Ng et al. 1999) and pays only actual advancement.
    """
    import torch

    progress = competition_goal_progress(env, goal_name=goal_name, asset_cfg=asset_cfg)
    goal_data = _goal_positions(env, goal_name)
    if goal_data is not None:
        goal, valid = goal_data
        root_x = env.scene[asset_cfg.name].data.root_link_pos_w[:, 0]
        progress = progress * ((root_x <= goal[:, 0]) & valid).to(progress.dtype)
    prev = getattr(env, "_course_prev_progress", None)
    if prev is None or prev.shape[0] != env.num_envs:
        prev = torch.zeros_like(progress)
    delta = torch.clamp(progress - prev, min=0.0)
    env._course_prev_progress = progress.detach()
    return delta * scale


PART2_WHEEL_RADIUS_M = 0.103
PART2_WHEEL_SURFACE_TOL_M = 0.06
PART2_WALL_X = 1.86
PART2_WALL_BACK_CLEARANCE_M = 0.16
PART2_GROUND_WHEEL_TOL_M = 0.08
PART2_STEP_DESCEND_CLEARANCE_M = 0.10
PART2_BASE_REF_Z = 0.5
PART2_LANE_HALF_WIDTH = 0.7
# Judge hold: hold_s=0.2 + TERMINAL_HOLD_EXTRA_S=0.1 at 50 Hz = 15 steps.
PART2_HOLD_STEPS = int(__import__("os").environ.get("BLACKW_SUCCESS_HOLD_STEPS", "15"))


def _part2_state_buffers(env, n: int, device):
    """Create or reset the per-env evidence buffers used by the Part2 predicate.

    The strict judge requires *evidence* (climbed onto the top landing / crossed
    the wall plane and reached climb height / was not dropped in the pile field)
    in addition to the terminal wheel state.  Buffers reset on every episode
    start (``episode_length_buf <= 1``).
    """
    import torch

    prev = getattr(env, "_part2_prev_rx", None)
    fresh = prev is None or prev.shape[0] != n
    if fresh:
        prev = torch.zeros(n, device=device)
        env._part2_max_z_near = torch.zeros(n, device=device)
        env._part2_top_seen = torch.zeros(n, dtype=torch.bool, device=device)
        env._part2_wall_crossed = torch.zeros(n, dtype=torch.bool, device=device)
    reset = env.episode_length_buf <= 1
    prev[reset] = 0.0
    env._part2_max_z_near[reset] = 0.0
    env._part2_top_seen[reset] = False
    env._part2_wall_crossed[reset] = False
    env._part2_prev_rx = prev
    return env


def _part2_terrain_state(
    env,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    wheel_radius: float = PART2_WHEEL_RADIUS_M,
    terrain_kind: str | None = None,
):
    """Per-env official Part2 success / rule-violation state from wheel poses.

    Mirrors ``@20261024_blackw/scripts/eval_blackw_part2.py``
    (``JUDGE_VERSION = v5-wheel-terminal-bands-2026-10-25``):

    * success is a terminal-state predicate on the four wheel bottoms
      (``wheel_z`` in ``[surface - 0.06, surface + 0.20]``, i.e. support band);
    * evidence is required where the judge requires it (stairs: all wheels on the
      top landing at some point; wall: base crossed the wall plane and reached
      ``climb_z_min`` near the wall; plum: no wheel below the pile-top line in
      the field);
    * violations are rules the judge treats as an invalid attempt (a wheel
      sinking into the trench slot deeper than ``min(0.5 * depth, radius)``; a
      wheel dropped below the pile-top line inside the plum field; falls are
      handled by the generic fall terminations).

    The result is cached per env step so reward / termination terms can call it
    without double-updating the evidence buffers.

    ``terrain_kind`` selects the predicate for single-terrain specialist tasks;
    when omitted the kind is taken from the sub-terrain column name (mixed task).
    """
    import torch

    step = int(getattr(env, "common_step_counter", -1))
    cache = getattr(env, "_part2_state_cache", None)
    if cache is not None and cache[0] == step:
        return cache[1], cache[2]

    asset = env.scene[asset_cfg.name]
    terrain = env.scene.terrain
    origins = terrain.env_origins
    origins = origins.to(env.device) if isinstance(origins, torch.Tensor) else torch.as_tensor(
        origins, device=env.device)
    types = torch.as_tensor(terrain.terrain_types, device=env.device)
    levels = torch.as_tensor(terrain.terrain_levels, device=env.device)
    num_rows = int(terrain.cfg.terrain_generator.num_rows)
    # The generator maps rows to ``lower + (upper-lower) * row/(rows-1)``; the
    # default range is (0, 1) but specialist runs may pin a fixed difficulty, so
    # read the actual range instead of assuming row/(rows-1).
    diff_lo, diff_hi = terrain.cfg.terrain_generator.difficulty_range
    row_t = levels.to(torch.float32) / max(1.0, float(num_rows - 1))
    difficulty = (float(diff_lo) + (float(diff_hi) - float(diff_lo)) * row_t).clamp(0.0, 1.0)
    body_names = asset.body_names
    wheel_ids = [body_names.index(f"{leg}_foot") for leg in ("FL", "FR", "RL", "RR")]
    wpos = asset.data.body_link_pos_w[:, wheel_ids, :]            # (N, 4, 3)
    wx = wpos[..., 0] - origins[:, 0:1]
    wz = wpos[..., 2] - wheel_radius
    rx = asset.data.root_link_pos_w[:, 0] - origins[:, 0]
    ry = asset.data.root_link_pos_w[:, 1] - origins[:, 1]
    root_z = asset.data.root_link_pos_w[:, 2]
    root_vz = asset.data.root_link_lin_vel_w[:, 2]
    n = env.num_envs
    d = difficulty
    lane = ry.abs() <= PART2_LANE_HALF_WIDTH
    wz_min = wz.min(dim=1).values
    wx_min = wx.min(dim=1).values
    wx_max = wx.max(dim=1).values

    success = torch.zeros(n, dtype=torch.bool, device=env.device)
    violation = torch.zeros(n, dtype=torch.bool, device=env.device)
    columns = list(terrain.cfg.terrain_generator.sub_terrains.keys())

    def branch(name):
        if terrain_kind is not None:
            return (torch.ones(n, dtype=torch.bool, device=env.device)
                    if name == terrain_kind
                    else torch.zeros(n, dtype=torch.bool, device=env.device))
        return (types == columns.index(name)) if name in columns else torch.zeros(
            n, dtype=torch.bool, device=env.device)

    def on_surface(level, tol=PART2_WHEEL_SURFACE_TOL_M, band=0.20):
        return ((wz >= (level - tol).unsqueeze(1))
                & (wz <= (level + band).unsqueeze(1))).all(dim=1)

    if "platform" in columns or terrain_kind == "platform":
        m = branch("platform")
        top = 0.10 + 0.30 * d
        success |= m & (on_surface(top) & lane
                        & (rx >= 2.0) & (rx <= 3.25))
    if "stairs" in columns or terrain_kind == "stairs":
        m = branch("stairs")
        top = 0.60 + 1.20 * d
        goal_x = 3.70
        end_x = 6.20
        _part2_state_buffers(env, n, env.device)
        env._part2_top_seen |= ((wz >= (top - PART2_WHEEL_SURFACE_TOL_M).unsqueeze(1)).all(dim=1)
                                & (rx >= goal_x))
        on_ground = ((wz >= -PART2_WHEEL_SURFACE_TOL_M)
                     & (wz <= 0.20)).all(dim=1)
        success |= m & env._part2_top_seen & lane & on_ground & (
            wx_min >= end_x + PART2_STEP_DESCEND_CLEARANCE_M) & (
            rx >= end_x + PART2_STEP_DESCEND_CLEARANCE_M)
    if "slope" in columns or terrain_kind == "slope":
        m = branch("slope")
        rise = torch.tan(torch.deg2rad(20.0 + 25.0 * d)) * 2.0
        success |= m & on_surface(rise) & lane & (rx >= 3.90)
    if "high_wall" in columns or terrain_kind == "high_wall":
        m = branch("high_wall")
        h = 0.10 + 0.30 * d
        goal_x = 2.27
        _part2_state_buffers(env, n, env.device)
        prev = env._part2_prev_rx
        env._part2_wall_crossed |= ((prev - PART2_WALL_X) * (rx - PART2_WALL_X) <= 0.0) & (
            (rx - prev).abs() < 1.0)
        near = (rx - PART2_WALL_X).abs() <= 0.8
        env._part2_max_z_near = torch.maximum(
            env._part2_max_z_near, torch.where(near, root_z, torch.zeros_like(root_z)))
        env._part2_prev_rx = rx.detach().clone()
        climb_z_min = PART2_BASE_REF_Z + 0.20 * h
        success |= m & env._part2_wall_crossed & (rx >= goal_x) & lane & (
            env._part2_max_z_near >= climb_z_min) & (
            wx_min >= PART2_WALL_X + PART2_WALL_BACK_CLEARANCE_M) & (
            wz.max(dim=1).values <= PART2_GROUND_WHEEL_TOL_M)
    if "trench" in columns or terrain_kind == "trench":
        m = branch("trench")
        gap_w = 0.10 + 0.20 * d
        near_x = 3.80
        far_x = near_x + gap_w
        allowed_drop = min(0.5 * 0.30, float(wheel_radius))
        floor_z = 0.30 - allowed_drop
        in_slot = ((wx >= (near_x - 0.06)) & (wx <= (far_x + 0.06).unsqueeze(1)))
        violation |= m & (in_slot & (wz < floor_z - 0.01)).any(dim=1)
        success |= m & on_surface(torch.full_like(d, 0.30)) & lane & (
            wx_min >= far_x + 0.15) & (rx >= far_x + 0.15)
    if "plum" in columns or terrain_kind == "plum":
        m = branch("plum")
        in_field = (wx >= 3.75) & (wx <= 11.15)
        dropped = in_field & (wz < 0.05)
        violation |= m & dropped.any(dim=1)
        _part2_state_buffers(env, n, env.device)
        in_field_root = (rx >= 3.75) & (rx <= 11.15)
        env._part2_top_seen |= in_field_root & (~dropped.any(dim=1))
        success |= m & env._part2_top_seen & lane & (on_surface(torch.full_like(d, 0.20))) & (
            wx_min >= 11.55) & (rx >= 11.55)
    if terrain_kind is not None:
        # Single-terrain specialist task: the kind is decided by the caller, so
        # zero out the other branches' (always-false) masks for clarity.
        pass
    env._part2_state_cache = (step, success, violation)
    return success, violation


def _part2_success_streak(env, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")):
    """Consecutive success-predicate steps (cached once per env step)."""
    import torch

    step = int(getattr(env, "common_step_counter", -1))
    cache = getattr(env, "_part2_streak_cache", None)
    if cache is not None and cache[0] == step:
        return cache[1]
    success, _ = _part2_terrain_state(env, asset_cfg)
    streak = getattr(env, "_part2_success_streak", None)
    if streak is None or streak.shape[0] != env.num_envs:
        streak = torch.zeros(env.num_envs, dtype=torch.long, device=env.device)
    reset = env.episode_length_buf <= 1
    streak[reset] = 0
    streak = torch.where(success, streak + 1, torch.zeros_like(streak))
    env._part2_success_streak = streak
    env._part2_streak_cache = (step, streak)
    return streak


def _part2_clear_reward(env, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")):
    """One-step success bonus: paid exactly when the held success predicate fires."""
    import torch

    streak = _part2_success_streak(env, asset_cfg)
    return (streak == PART2_HOLD_STEPS).to(torch.float32)


def _part2_failure(env, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")):
    """Termination: attempt became invalid per the strict Part2 judge."""
    _, violation = _part2_terrain_state(env, asset_cfg)
    return violation


def _part2_success(env, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")):
    """Termination: four wheels held the target support terminal state."""
    streak = _part2_success_streak(env, asset_cfg)
    return streak >= PART2_HOLD_STEPS


def _part2_clear_reward(env, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")):
    """One-step success bonus for the official Part2 success predicate."""
    import torch

    success, _ = _part2_terrain_state(env, asset_cfg)
    return success.to(torch.float32)


def _part2_failure(env, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")):
    """Termination: attempt became invalid per the strict Part2 judge."""
    _, violation = _part2_terrain_state(env, asset_cfg)
    return violation


def _part2_success(env, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")):
    """Termination: all four wheels reached the target support surface."""
    success, _ = _part2_terrain_state(env, asset_cfg)
    return success


def _trench_wheel_drop_penalty(
    env,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    trench_column: int = -1,
    max_drop_m: float = 0.05,
    plateau_z: float = 0.30,
    gap_start_x: float = 3.5,
    wheel_radius: float = 0.103,
):
    """Penalize wheels sinking into the trench slot by more than the judge allows.

    The official Part 2 judge (``@20261024_blackw/scripts/eval_blackw_part2.py``)
    rejects a crossing when any wheel dips more than ``min(5 cm, 0.5 * gap)``
    below the 0.30 m plateau top while its x is inside the slot, which catches
    the "fall into the trench and climb out" cheat that plain goal rewards miss.
    This term mirrors that rule as a dense training penalty, active only for
    trench-column envs.
    """
    import torch

    if trench_column < 0:
        return torch.zeros(env.num_envs, device=env.device)
    asset = env.scene[asset_cfg.name]
    terrain = env.scene.terrain
    origins = terrain.env_origins
    if isinstance(origins, torch.Tensor):
        origins = origins.to(env.device)
    else:
        origins = torch.as_tensor(origins, device=env.device)
    terrain_types = torch.as_tensor(terrain.terrain_types, device=env.device)
    terrain_levels = torch.as_tensor(terrain.terrain_levels, device=env.device)
    num_rows = int(terrain.cfg.terrain_generator.num_rows)
    body_names = asset.body_names
    wheel_ids = [body_names.index(f"{leg}_foot") for leg in ("FL", "FR", "RL", "RR")]
    pos = asset.data.body_link_pos_w[:, wheel_ids, :]           # (N, 4, 3)
    x_local = pos[..., 0] - origins[:, 0:1]
    z_bottom = pos[..., 2] - wheel_radius
    difficulty = terrain_levels.to(torch.float32) / max(1.0, float(num_rows - 1))
    gap_w = 0.10 + 0.20 * difficulty                             # official 10..30 cm
    gap_lo = torch.full_like(gap_w, gap_start_x - 0.10)
    gap_hi = gap_start_x + gap_w + 0.30
    in_slot = (x_local >= gap_lo.unsqueeze(1)) & (x_local <= gap_hi.unsqueeze(1))
    allowed_drop = torch.clamp(0.5 * gap_w, max=max_drop_m)       # min(5 cm, 0.5*gap)
    allowed_floor = plateau_z - allowed_drop
    over = torch.clamp(allowed_floor.unsqueeze(1) - z_bottom, min=0.0)
    penalty = (over * in_slot.to(over.dtype)).sum(dim=1) / 4.0
    mask = (terrain_types == trench_column).to(penalty.dtype)
    return penalty * mask


def _platform_height_reward(env, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")):
    """Small dense signal for lifting the root toward a platform top."""
    import torch

    asset = env.scene[asset_cfg.name]
    root_z = asset.data.root_link_pos_w[:, 2]
    return torch.clamp(root_z - 0.70, min=0.0, max=0.5)


def _lane_deviation(env, max_abs_y: float = 0.9, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")):
    """Terminate lateral bypass: the Part2 judge scores only inside the lane."""
    import torch

    asset = env.scene[asset_cfg.name]
    origins = env.scene.terrain.env_origins
    lateral = asset.data.root_link_pos_w[:, 1] - origins[:, 1]
    return torch.abs(lateral) > max_abs_y


def _platform_top_success(
    env,
    min_root_z: float = 0.72,
    goal_x_min: float = 1.9,
    goal_x_max: float = 3.1,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
):
    """Official-platform success proxy: root over the platform AND raised onto it.

    The previous goal-x-only reward let a CCD-disabled/penetrating robot reach x
    without climbing (false 70% success).  Require the base to be raised to the
    10 cm platform height as well.
    """
    import torch

    asset = env.scene[asset_cfg.name]
    origins = env.scene.terrain.env_origins
    x = asset.data.root_link_pos_w[:, 0] - origins[:, 0]
    z = asset.data.root_link_pos_w[:, 2]
    return (x >= goal_x_min) & (x <= goal_x_max) & (z >= min_root_z)


def _climb_height_reward(env, asset_cfg: SceneEntityCfg = SceneEntityCfg("robot")):
    """Dense reward for lifting the trunk above flat standing height.

    Applies to every official Part2 obstacle (platform, stairs, slope, trench
    plateau, wall): the robot starts on a flat patch, so any trunk height above
    the flat stance is evidence that it is climbing the obstacle.
    """
    import torch

    asset = env.scene[asset_cfg.name]
    root_z = asset.data.root_link_pos_w[:, 2]
    return torch.clamp(root_z - 0.55, min=0.0, max=0.60)


def _override_rewards(cfg: ManagerBasedRlEnvCfg) -> None:
    # Foot clearance uses Black foot sites, which do not exist on blackW; the rest of
    # the frozen Black reward set is robot-agnostic.
    cfg.rewards.pop("foot_clearance", None)


def _apply_blackw_overrides(cfg: ManagerBasedRlEnvCfg) -> ManagerBasedRlEnvCfg:
    _override_robot(cfg)
    _override_sensors(cfg)
    _override_actions(cfg)
    _override_observations(cfg)
    _override_events(cfg)
    _override_rewards(cfg)
    return cfg


def blackw_flat_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    return _apply_blackw_overrides(_build_black_env_cfg(play=play, rough=False))


def blackw_competition_env_cfg(
    play: bool = False, subterrains: tuple[str, ...] | None = None
) -> ManagerBasedRlEnvCfg:
    """Competition-proxy terrain (Part1/Part2 obstacles) with the blackW contract.

    ``subterrains`` restricts the generator to a subset (specialist policies), e.g.
    only the high-platform, slope or trench columns for the high Part2 tiers.
    """
    cfg = _apply_blackw_overrides(black_competition_env_cfg(play=play))
    if subterrains and cfg.scene.terrain is not None:
        generator = cfg.scene.terrain.terrain_generator
        assert generator is not None
        for name in subterrains:
            if name not in generator.sub_terrains:
                raise ValueError(f"unknown blackW sub-terrain: {name}")
        generator.sub_terrains = {
            name: generator.sub_terrains[name] for name in subterrains
        }
    if cfg.scene.terrain is not None and not play:
        # Stage 2 targets the high-value Part2 tiers: initialise on rows 0..5
        # (high platform 30/40, slope 35/45, trench 20/30), not only the easy rows.
        cfg.scene.terrain.max_init_terrain_level = 5
    if not play:
        # A goal-x-only reward lets the policy walk around obstacle patches (y up to
        # several metres on real Part2 scenes). The judges score inside a narrow lane;
        # terminate lateral bypass so the policy must interact with the obstacle.
        cfg.terminations["lane_deviation"] = TerminationTermCfg(
            func=_lane_deviation, params={"max_abs_y": 0.9}
        )
    return cfg


def blackw_platform_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    return blackw_competition_env_cfg(play=play, subterrains=("platform",))


def blackw_slope_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    return blackw_competition_env_cfg(
        play=play, subterrains=("smooth_slope_up", "smooth_slope_down")
    )


def blackw_trench_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    return blackw_competition_env_cfg(play=play, subterrains=("trench",))


# Exact specialist terrain class -> official Part2 judge kind.  The sub-terrain
# key IS the judge kind: ``_part2_terrain_state`` branches on the column name, so
# naming the single column ``"exact"`` made every part2_* term dead code.
_EXACT_TERRAIN_KIND: dict[str, str] = {
    "ExactHighPlatformTerrainCfg": "platform",
    "ExactHighWallTerrainCfg": "high_wall",
    "ExactSlopeTerrainCfg": "slope",
    "ExactStairsTerrainCfg": "stairs",
    "ExactTrenchTerrainCfg": "trench",
    "ExactPlumTerrainCfg": "plum",
}



def _apply_deployment_sim_options(cfg) -> None:
    """Match the official Part2 scene ``<option>`` block used by the judge.

    The official ``ability_field/map.xml`` scenes run MuJoCo with elliptic cone,
    PGS solver, ``impratio=100``, Euler integrator, 100 solver iterations and 35
    CCD iterations.  MjLab defaults (newton / pyramidal / impratio=1 /
    implicitfast / 10 iterations) give a visibly different wheel-friction
    response on steeper slopes: a BC policy that cleared the 35 deg judge scene
    could not climb the same 35 deg slope in the training env, so PPO gradients
    pushed it away from the (already correct) deployment behaviour.
    """
    import os

    if os.environ.get("BLACKW_DEPLOY_SIM", "0") not in ("1", "true", "yes"):
        return
    sim = cfg.sim.mujoco
    sim.integrator = "euler"
    sim.cone = "elliptic"
    sim.jacobian = "sparse"
    # mujoco_warp does not implement mjSOL_PGS (the official scene uses PGS); keep
    # Newton but raise the iteration count / friction settings to match as closely
    # as the backend allows.
    sim.solver = "newton"
    sim.iterations = 100
    sim.ls_iterations = 50
    sim.ls_tolerance = 0.01
    sim.impratio = 100.0
    sim.ccd_iterations = 35
    # The deployment scenes spawn the robot at the judge spawn height (0.5 m base),
    # not at the training init height (0.69 m).
    robot = cfg.scene.entities.get("robot")
    if robot is not None and getattr(robot, "init_state", None) is not None:
        robot.init_state.pos = (0.0, 0.0, 0.52)


def _exact_env_cfg(terrain_cfg, play: bool) -> ManagerBasedRlEnvCfg:
    import os

    cfg = _apply_blackw_overrides(black_competition_env_cfg(play=play))
    assert cfg.scene.terrain is not None and cfg.scene.terrain.terrain_generator
    generator = cfg.scene.terrain.terrain_generator
    terrain_cfg.flat_patch_sampling = {
        "goal": FlatPatchSamplingCfg(num_patches=1, patch_radius=0.3)
    }
    kind = _EXACT_TERRAIN_KIND.get(type(terrain_cfg).__name__)
    if kind is None:
        raise ValueError(f"unknown exact terrain cfg: {type(terrain_cfg).__name__}")
    generator.sub_terrains = {kind: terrain_cfg}
    _apply_deployment_sim_options(cfg)
    # Specialist runs fix a difficulty row so the whole batch trains one tier
    # (e.g. slope 45 deg, stairs 30 cm); default keeps the full 0..1 sweep.
    dmin = float(os.environ.get("BLACKW_DIFF_MIN", "0.0"))
    dmax = float(os.environ.get("BLACKW_DIFF_MAX", "1.0"))
    if (dmin, dmax) != (0.0, 1.0):
        generator.difficulty_range = (dmin, dmax)
    # Exact ramps/platforms create many wheel/edge contacts; blackW smoke hit
    # nconmax=172 on the 45-degree ramp.  Default is generous for single-line
    # experiments; when two training lines share one GPU, cap the warp capacity
    # (e.g. BLACKW_NCONMAX=256, BLACKW_NJMAX=1024) to fit a half-GPU memory budget.
    cfg.sim.nconmax = int(os.environ.get("BLACKW_NCONMAX", "1024"))
    cfg.sim.njmax = int(os.environ.get("BLACKW_NJMAX", "4096"))
    # Wheel cylinders vs platform box hit a Mujoco-Warp CCD assert in HIM
    # exploration; these tasks are low-speed, so disable CCD.
    cfg.sim.ccd_iterations = 0
    if not play:
        dmin = float(os.environ.get("BLACKW_DIFF_MIN", "0.0"))
        # Command profile for specialist runs (obstacle traversal is straight-lane).
        command = cfg.commands["twist"]
        command.ranges.lin_vel_x = (
            float(os.environ.get("BLACKW_VX_MIN", "0.40")),
            float(os.environ.get("BLACKW_VX_MAX", "1.00")),
        )
        lateral = float(os.environ.get("BLACKW_LATERAL_CMD", "0.10"))
        yaw = float(os.environ.get("BLACKW_YAW_CMD", "0.20"))
        command.ranges.lin_vel_y = (-lateral, lateral)
        command.ranges.ang_vel_z = (-yaw, yaw)
        command.rel_forward_envs = 1.0
        command.rel_standing_envs = 0.0
        # Start exact tasks on the easy rows unless a fixed hard tier or an
        # explicit curriculum row is requested (BLACKW_MAX_ROW=0..num_rows-1).
        max_row = int(os.environ.get("BLACKW_MAX_ROW", "-1"))
        if max_row >= 0:
            num_rows = int(generator.num_rows)
            cfg.scene.terrain.max_init_terrain_level = min(
                max_row, max(0, num_rows - 1))
        else:
            cfg.scene.terrain.max_init_terrain_level = (
                0 if dmin > 0.0 else 1)
        cfg.terminations["lane_deviation"] = TerminationTermCfg(
            func=_lane_deviation, params={"max_abs_y": 0.9}
        )
        cfg.terminations.pop("competition_goal_reached", None)
        # The base competition cfg ships competition_goal (weight 5.0, pays every
        # step the root is past the goal line) and a state-based
        # competition_progress (weight 1.5).  They must be removed here, not just
        # shadowed: a policy could farm them by camping past the obstacle line.
        cfg.rewards.pop("competition_goal", None)
        cfg.rewards.pop("climb_height", None)
        cfg.terminations["part2_success"] = TerminationTermCfg(
            func=_part2_success, params={"asset_cfg": SceneEntityCfg("robot")})
        cfg.terminations["part2_failure"] = TerminationTermCfg(
            func=_part2_failure, params={"asset_cfg": SceneEntityCfg("robot")})
        cfg.rewards["competition_progress"] = RewardTermCfg(
            func=_course_progress_delta,
            weight=float(os.environ.get("BLACKW_PROGRESS_W", "8.0")),
            params={"goal_name": "goal", "asset_cfg": SceneEntityCfg("robot")},
        )
        goal_w = float(os.environ.get("BLACKW_GOAL_W", "0.0"))
        if goal_w > 0.0:
            cfg.rewards["competition_goal"] = RewardTermCfg(
                func=competition_goal_reward,
                weight=goal_w,
                params={"goal_name": "goal", "asset_cfg": SceneEntityCfg("robot")},
            )
        climb_w = float(os.environ.get("BLACKW_CLIMB_W", "0.0"))
        if climb_w > 0.0:
            cfg.rewards["climb_height"] = RewardTermCfg(
                func=_course_climb_reward,
                weight=climb_w,
            )
        cfg.terminations["part2_out_of_course"] = TerminationTermCfg(
            func=_out_of_course, params={"goal_name": "goal", "margin": 0.8})
        if float(os.environ.get("BLACKW_CLEAR_W", "25.0")) > 0.0:
            cfg.rewards["part2_clear"] = RewardTermCfg(
                func=_part2_clear_reward,
                weight=float(os.environ.get("BLACKW_CLEAR_W", "25.0")),
                params={"asset_cfg": SceneEntityCfg("robot")},
            )
    return cfg


def blackw_stairs_exact_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    """Exact official stairs task (full up + landing + down staircase)."""
    return _exact_env_cfg(ExactStairsTerrainCfg(), play)


def blackw_wall_exact_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    """Exact official high-wall task (cross_bar 10..40 cm)."""
    return _exact_env_cfg(ExactHighWallTerrainCfg(), play)


def blackw_platform_exact_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    cfg = _exact_env_cfg(
        ExactHighPlatformTerrainCfg(side_walls=False, lane_half_width=0.70), play
    )
    if not play:
        cfg.rewards["platform_height"] = RewardTermCfg(
            func=_platform_height_reward, weight=50.0
        )
        # Goal-x alone is gameable (CCD-off penetration / walking around). Replace
        # the sparse x-goal with a real platform-top condition for the pilot.
        cfg.rewards.pop("competition_goal", None)
        cfg.terminations.pop("competition_goal_reached", None)
        cfg.terminations["official_platform_success"] = TerminationTermCfg(
            func=_platform_top_success, params={"min_root_z": 0.72}
        )
        # Pilot only 10 cm elevated platform first; increase later with the
        # success-gated curriculum.
        if cfg.scene.terrain is not None:
            cfg.scene.terrain.max_init_terrain_level = 0
        cfg.terminations["lane_deviation"].params["max_abs_y"] = 0.80
    return cfg


def blackw_slope_exact_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    return _exact_env_cfg(ExactSlopeTerrainCfg(), play)


def blackw_trench_exact_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    return _exact_env_cfg(ExactTrenchTerrainCfg(), play)


def blackw_official_mixed_env_cfg(
    play: bool = False, subterrains: tuple[str, ...] | None = None
) -> ManagerBasedRlEnvCfg:
    """Official Part2 geometry mixed terrain (5 categories, no proxy shapes).

    Each column is one official obstacle type and each row is a difficulty step;
    ``BLACKW_MAX_ROW`` (default: hardest row) sets the initial difficulty row so a
    manual success-gated curriculum can start easy and promote.  The command range
    covers the slow deployment speeds (0.25-1.0 m/s) at which the official blackW
    policy clears the platform / wall tiers.
    """
    import os

    cfg = _apply_blackw_overrides(black_competition_env_cfg(play=play))
    assert cfg.scene.terrain is not None and cfg.scene.terrain.terrain_generator
    sampling = {"goal": FlatPatchSamplingCfg(num_patches=1, patch_radius=0.3)}
    terrains = {
        "platform": ExactHighPlatformTerrainCfg(flat_patch_sampling=sampling),
        "high_wall": ExactHighWallTerrainCfg(flat_patch_sampling=sampling),
        "slope": ExactSlopeTerrainCfg(flat_patch_sampling=sampling),
        "stairs": ExactStairsTerrainCfg(flat_patch_sampling=sampling),
        "trench": ExactTrenchTerrainCfg(flat_patch_sampling=sampling),
    }
    if subterrains:
        terrains = {k: v for k, v in terrains.items() if k in subterrains}
    # The official trench (ramp + plateau + gap + ramp) is ~5.8 m long from the
    # spawn; the default 8 m patch would let it overflow into the next difficulty
    # row, so lengthen every patch to 16 m.  Obstacle offsets are spawn-relative
    # and unchanged.
    cfg.scene.terrain.terrain_generator.size = (16.0, 8.0)
    cfg.scene.terrain.terrain_generator.sub_terrains = terrains
    cfg.sim.nconmax = int(os.environ.get("BLACKW_NCONMAX", "256"))
    cfg.sim.njmax = int(os.environ.get("BLACKW_NJMAX", "1024"))
    # Wheel cylinders vs box edges triggered a Mujoco-Warp CCD assert in HIM runs.
    cfg.sim.ccd_iterations = 0
    if not play:
        num_rows = cfg.scene.terrain.terrain_generator.num_rows
        cfg.scene.terrain.max_init_terrain_level = int(
            os.environ.get("BLACKW_MAX_ROW", str(max(0, num_rows - 1)))
        )
        cfg.terminations["lane_deviation"] = TerminationTermCfg(
            func=_lane_deviation,
            params={"max_abs_y": float(os.environ.get("BLACKW_LANE", "0.90"))},
        )
        command = cfg.commands["twist"]
        command.ranges.lin_vel_x = (
            float(os.environ.get("BLACKW_VX_MIN", "0.25")),
            float(os.environ.get("BLACKW_VX_MAX", "1.0")),
        )
        # Obstacle traversal is a straight-lane task; keep small lateral/heading
        # commands so most episodes interact with the obstacle instead of leaving
        # the 1.4-1.6 m scoring lane (the operator drives straight at obstacles).
        lateral = float(os.environ.get("BLACKW_LATERAL_CMD", "0.15"))
        yaw = float(os.environ.get("BLACKW_YAW_CMD", "0.2"))
        command.ranges.lin_vel_y = (-lateral, lateral)
        command.ranges.ang_vel_z = (-yaw, yaw)
        command.rel_forward_envs = 1.0
        command.rel_standing_envs = 0.0
        # Obstacle traversal matters more than exact velocity tracking on a single
        # flat patch; keep tracking but add a dense climb signal and a bigger
        # sparse success bonus (the goal patch sits past every official obstacle).
        # The base cfg ships a state-based competition_progress (1.5) and a
        # per-step competition_goal (5.0); both pay while camping past an
        # obstacle line.  Drop them and re-add only potential-based variants.
        cfg.rewards.pop("competition_goal", None)
        cfg.rewards.pop("climb_height", None)
        cfg.rewards["competition_progress"] = RewardTermCfg(
            func=_course_progress_delta,
            weight=float(os.environ.get("BLACKW_PROGRESS_W", "8.0")),
            params={"goal_name": "goal", "asset_cfg": SceneEntityCfg("robot")},
        )
        goal_w = float(os.environ.get("BLACKW_GOAL_W", "0.0"))
        if goal_w > 0.0:
            cfg.rewards["competition_goal"] = RewardTermCfg(
                func=competition_goal_reward,
                weight=goal_w,
                params={"goal_name": "goal", "asset_cfg": SceneEntityCfg("robot")},
            )
        climb_w = float(os.environ.get("BLACKW_CLIMB_W", "0.0"))
        if climb_w > 0.0:
            cfg.rewards["climb_height"] = RewardTermCfg(
                func=_course_climb_reward,
                weight=climb_w,
            )
        cfg.terminations["part2_out_of_course"] = TerminationTermCfg(
            func=_out_of_course, params={"goal_name": "goal", "margin": 0.8})
        # Trench cleanup: the goal/progress rewards alone let a policy cross by
        # dropping into the slot and climbing out; the strict judge rejects that.
        trench_pen_w = float(os.environ.get("BLACKW_TRENCH_PEN_W", "0.0"))
        if trench_pen_w > 0.0 and "trench" in terrains:
            cfg.rewards["trench_wheel_drop"] = RewardTermCfg(
                func=_trench_wheel_drop_penalty,
                weight=-trench_pen_w,
                params={"trench_column": list(terrains).index("trench")},
            )
        # Judge-aligned terminal conditions: the old ``competition_goal_reached``
        # term ended the episode when the *trunk* crossed a line, which allowed
        # "wheels still on the obstacle" completions and trench cheating.  The
        # success term now requires all four wheels on the target support
        # surface, and a trench slot violation terminates the attempt as a
        # failure (rules: attempt invalid, same as the strict judge).
        cfg.terminations.pop("competition_goal_reached", None)
        cfg.terminations["part2_success"] = TerminationTermCfg(
            func=_part2_success, params={"asset_cfg": SceneEntityCfg("robot")})
        cfg.terminations["part2_failure"] = TerminationTermCfg(
            func=_part2_failure, params={"asset_cfg": SceneEntityCfg("robot")})
        clear_w = float(os.environ.get("BLACKW_CLEAR_W", "25.0"))
        if clear_w > 0.0:
            cfg.rewards["part2_clear"] = RewardTermCfg(
                func=_part2_clear_reward,
                weight=clear_w,
                params={"asset_cfg": SceneEntityCfg("robot")},
            )
    return cfg


def blackw_plum_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    """Part2 tier-1 plum pile field: 24 piles + entry/exit platforms (200 pts).

    Uses the strict wheel-contact success/failure predicates: any wheel touching
    the ground between piles ends the attempt (judge rule), and success needs all
    four wheels on the exit platform.  The dense progress/goal rewards plus the
    success bonus shape the crossing; the task has no difficulty levels (the
    official tier-1 field is fixed).
    """
    import os

    cfg = _apply_blackw_overrides(black_competition_env_cfg(play=play))
    assert cfg.scene.terrain is not None and cfg.scene.terrain.terrain_generator
    terrain = ExactPlumTerrainCfg()
    terrain.flat_patch_sampling = {
        "goal": FlatPatchSamplingCfg(num_patches=1, patch_radius=0.3)
    }
    cfg.scene.terrain.terrain_generator.size = (16.0, 8.0)
    cfg.scene.terrain.terrain_generator.sub_terrains = {"plum": terrain}
    cfg.sim.nconmax = int(os.environ.get("BLACKW_NCONMAX", "512"))
    cfg.sim.njmax = int(os.environ.get("BLACKW_NJMAX", "2048"))
    cfg.sim.ccd_iterations = 0
    if not play:
        cfg.scene.terrain.max_init_terrain_level = 0
        cfg.terminations.pop("competition_goal_reached", None)
        cfg.terminations["lane_deviation"] = TerminationTermCfg(
            func=_lane_deviation,
            params={"max_abs_y": float(os.environ.get("BLACKW_LANE", "0.90"))},
        )
        cfg.terminations["part2_success"] = TerminationTermCfg(
            func=_part2_success, params={"asset_cfg": SceneEntityCfg("robot")})
        cfg.terminations["part2_failure"] = TerminationTermCfg(
            func=_part2_failure, params={"asset_cfg": SceneEntityCfg("robot")})
        command = cfg.commands["twist"]
        command.ranges.lin_vel_x = (
            float(os.environ.get("BLACKW_VX_MIN", "0.25")),
            float(os.environ.get("BLACKW_VX_MAX", "0.65")),
        )
        lateral = float(os.environ.get("BLACKW_LATERAL_CMD", "0.05"))
        yaw = float(os.environ.get("BLACKW_YAW_CMD", "0.08"))
        command.ranges.lin_vel_y = (-lateral, lateral)
        command.ranges.ang_vel_z = (-yaw, yaw)
        command.rel_forward_envs = 1.0
        command.rel_standing_envs = 0.0
        cfg.rewards.pop("competition_goal", None)
        cfg.rewards.pop("climb_height", None)
        cfg.rewards["competition_progress"] = RewardTermCfg(
            func=_course_progress_delta,
            weight=float(os.environ.get("BLACKW_PROGRESS_W", "8.0")),
            params={"goal_name": "goal", "asset_cfg": SceneEntityCfg("robot")},
        )
        foot_w = float(os.environ.get("BLACKW_PLUM_FOOT_W", "3.0"))
        if foot_w > 0.0:
            cfg.rewards["plum_foothold"] = RewardTermCfg(
                func=_plum_foothold_reward,
                weight=foot_w,
                params={"asset_cfg": SceneEntityCfg("robot")},
            )
        goal_w = float(os.environ.get("BLACKW_GOAL_W", "0.0"))
        if goal_w > 0.0:
            cfg.rewards["competition_goal"] = RewardTermCfg(
                func=competition_goal_reward,
                weight=goal_w,
                params={"goal_name": "goal", "asset_cfg": SceneEntityCfg("robot")},
            )
        climb_w = float(os.environ.get("BLACKW_CLIMB_W", "0.0"))
        if climb_w > 0.0:
            cfg.rewards["climb_height"] = RewardTermCfg(
                func=_course_climb_reward,
                weight=climb_w,
            )
        cfg.terminations["part2_out_of_course"] = TerminationTermCfg(
            func=_out_of_course, params={"goal_name": "goal", "margin": 0.8})
        if float(os.environ.get("BLACKW_CLEAR_W", "25.0")) > 0.0:
            cfg.rewards["part2_clear"] = RewardTermCfg(
                func=_part2_clear_reward,
                weight=float(os.environ.get("BLACKW_CLEAR_W", "25.0")),
                params={"asset_cfg": SceneEntityCfg("robot")},
            )
    return cfg


def blackw_platform_easy_env_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    """Platform-shape curriculum stage: 5->10 cm before the official 10 cm tier."""
    cfg = _exact_env_cfg(
        ExactHighPlatformTerrainCfg(
            platform_height_range=(0.05, 0.10),
            side_walls=False,
            lane_half_width=0.70,
        ),
        play,
    )
    if not play:
        cfg.rewards["platform_height"] = RewardTermCfg(
            func=_platform_height_reward, weight=50.0
        )
        cfg.rewards.pop("competition_goal", None)
        cfg.terminations.pop("competition_goal_reached", None)
        cfg.terminations["official_platform_success"] = TerminationTermCfg(
            func=_platform_top_success, params={"min_root_z": 0.71}
        )
        if cfg.scene.terrain is not None:
            cfg.scene.terrain.max_init_terrain_level = 0
        cfg.terminations["lane_deviation"].params["max_abs_y"] = 0.80
    return cfg
