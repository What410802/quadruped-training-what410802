#!/usr/bin/env python3
"""Generate an rl_sar-compatible copy of a task scene.

The task scenes (`@20261019_locomotion/assets/terrain/part1|part2`) use the mjlab
actuator order FL / FR / RL / RR, while the rl_sar control stack
(`@20261007_assignment`) maps policy joints to the simulated joint order
FL / FR / RR / RL (the order of `@20261005_ros2`'s `black_description.xml`, see
`policy/black/base.yaml` `joint_mapping`).  `sim_node` indexes actuators, so the
scene copy only needs its `<actuator>` block reordered; joint qpos order and every
other XML element stay byte-identical.

Usage (repository root, any Python with mujoco is fine - `pixi run python` works):

    pixi run python @20261019_locomotion/scripts/agent_scripts/make_rlsar_scene.py \
        --scene @20261019_locomotion/assets/terrain/part1/part1_eval_scene.xml \
        --out ../prep.d/scenes/part1_rlsar.xml

The generated scene includes a rewritten robot XML in the same output directory, so
`ros2 run quadruped_ros2 sim_node --ros-args -p scene:=<absolute out path>` works.
Generated files live under `prep.d/` (not committed).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

LEGS = ("FL", "FR", "RR", "RL")
JOINTS = ("hip", "thigh", "calf")
EXPECTED_MOTOR_ORDER = [f"motor_{leg}_{joint}_joint" for leg in LEGS for joint in JOINTS]
MOTOR_RE = re.compile(r"<motor\b[^>]*?name=\"(?P<name>[^\"]+)\"[^>]*?/>", re.S)
INCLUDE_RE = re.compile(r"(<include\b[^>]*?file=\")(?P<file>[^\"]+)(\"[^>]*?/>)")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def make_visuals_visible(robot_xml: str) -> tuple[str, int]:
    """Move mjlab's robot visual geoms (group 3) to group 1.

    mjlab scenes put robot visual geoms in group 3 to separate them from terrain (group
    0) in the depth camera.  ``quadruped_ros2``'s viewer starts from
    ``mjv_defaultOption`` (groups 0-2 visible), so the robot would be invisible there.
    Group affects visualization only; collision pairs (contype/conaffinity) are untouched.
    """
    count = robot_xml.count('group="3"')
    return robot_xml.replace('group="3"', 'group="1"'), count


def reorder_actuators(robot_xml: str, robot_path: Path) -> tuple[str, list[str]]:
    actuator_match = re.search(r"(?P<open><actuator>)(?P<body>.*?)(?P<close></actuator>)",
                               robot_xml, re.S)
    if actuator_match is None:
        raise SystemExit(f"{robot_path}: no <actuator> block found")
    body = actuator_match.group("body")
    motors = list(MOTOR_RE.finditer(body))
    if not motors:
        raise SystemExit(f"{robot_path}: no <motor> elements inside <actuator>")
    names = [m.group("name") for m in motors]
    if sorted(names) != sorted(EXPECTED_MOTOR_ORDER):
        raise SystemExit(f"{robot_path}: unexpected motor set {names}")
    by_name = {m.group("name"): m.group(0) for m in motors}
    # Deterministic reorder; keep the original line indentation of the first motor.
    first_line_start = body.rfind("\n", 0, motors[0].start()) + 1
    indent = body[first_line_start:motors[0].start()]
    ordered = [by_name[name] for name in EXPECTED_MOTOR_ORDER]
    new_body = "\n" + "\n".join(indent + motor for motor in ordered) + "\n"
    new_xml = (robot_xml[:actuator_match.start("body")] + new_body
               + robot_xml[actuator_match.end("body"):])
    return new_xml, names


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--scene", type=Path, required=True, help="task scene XML to convert")
    ap.add_argument("--out", type=Path, required=True, help="output scene XML (under prep.d/)")
    args = ap.parse_args()

    scene_path = args.scene.resolve()
    scene_xml = read_text(scene_path)

    out_scene = args.out.resolve()
    out_scene.parent.mkdir(parents=True, exist_ok=True)
    out_robot = out_scene.with_name(out_scene.stem + "_robot.xml")

    # A scene may include several files (terrain map + robot). Rewrite the robot
    # include to a local copy with the rl_sar actuator order; keep every other include
    # as an absolute path so its own relative asset files (labels/*.png) still work.
    robot_includes = []
    other_includes = []
    for include in INCLUDE_RE.finditer(scene_xml):
        candidate = (scene_path.parent / include.group("file")).resolve()
        if candidate.is_file() and "<actuator" in read_text(candidate):
            robot_includes.append((include, candidate))
        else:
            other_includes.append((include, candidate))
    if len(robot_includes) != 1:
        raise SystemExit(
            f"{scene_path}: expected exactly one include with an <actuator> block, "
            f"found {[str(candidate) for _, candidate in robot_includes]}")
    include, robot_path = robot_includes[0]
    robot_xml = read_text(robot_path)
    robot_xml, moved_visuals = make_visuals_visible(robot_xml)
    new_robot_xml, old_order = reorder_actuators(robot_xml, robot_path)

    # Rewrite from the last include to the first so the recorded offsets stay valid.
    new_scene_xml = scene_xml
    replacements = []
    for other_include, candidate in other_includes:
        replacements.append((other_include, str(candidate)))
    replacements.append((include, None))  # robot: local copy next to the scene
    replacements.sort(key=lambda item: item[0].start("file"), reverse=True)
    asset_dirs = set()
    for target_include, replacement in replacements:
        if replacement is None:
            replacement = out_robot.name
        else:
            if 'file="' in read_text(Path(replacement)):
                asset_dirs.add(Path(replacement).parent)
        new_scene_xml = (new_scene_xml[:target_include.start("file")] + replacement
                         + new_scene_xml[target_include.end("file"):])
    if asset_dirs:
        if len(asset_dirs) > 1:
            raise SystemExit(f"{scene_path}: included assets from multiple dirs: {asset_dirs}")
        asset_dir = next(iter(asset_dirs))
        new_scene_xml = new_scene_xml.replace(
            "</mujoco>", f"  <compiler texturedir=\"{asset_dir}\"/>\n</mujoco>", 1)

    out_robot.write_text(new_robot_xml, encoding="utf-8")
    out_scene.write_text(new_scene_xml, encoding="utf-8")

    # Fail fast if the generated scene is not loadable or not in rl_sar order.
    try:
        import mujoco
    except ImportError:  # mujoco is available in the repository pixi env
        print("warning: mujoco not importable, skipped load check", file=sys.stderr)
    else:
        model = mujoco.MjModel.from_xml_path(str(out_scene))
        motors = [model.actuator(i).name for i in range(model.nu)]
        assert motors == EXPECTED_MOTOR_ORDER, motors
        assert model.nu == 12 and model.nq == 19 and model.nv == 18, (
            model.nu, model.nq, model.nv)
        sensors = {model.sensor(i).name for i in range(model.nsensor)}
        missing = {"imu_quat", "imu_gyro", "imu_acc"} - sensors
        assert not missing, f"missing IMU sensors for sim_node: {missing}"

    print(f"scene : {scene_path}")
    print(f"robot : {robot_path}")
    print(f"out   : {out_scene}")
    print(f"robot : {out_robot}")
    print(f"motor order before: {old_order}")
    print(f"motor order after : {EXPECTED_MOTOR_ORDER}")
    print(f"visual geoms group 3 -> 1: {moved_visuals}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
