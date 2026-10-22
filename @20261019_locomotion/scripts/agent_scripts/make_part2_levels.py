"""Generate parametric Part 2 level scenes + metadata for the V2 evaluator.

The organizer allows custom maps for ability demonstration as long as the obstacle
type matches the official one (team-race rules), so local evaluation uses exact
parametric levels; the official ability field stays for final cross-checks.

Outputs (from MyMonoRepo.d):
  assets/terrain/part2/levels/<category>_<level>.xml
  config/part2-levels.json

Usage: pixi run python @20261019_locomotion/scripts/agent_scripts/make_part2_levels.py
"""
from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # .../@20261019_locomotion
LEVEL_DIR = ROOT / "assets" / "terrain" / "part2" / "levels"
META = ROOT / "config" / "part2-levels.json"

SPECS = {
    "high_platform": {"levels": [10, 20, 30, 40], "unit": "cm", "kind": "platform"},
    "stairs": {"levels": [10, 15, 20, 30], "unit": "cm", "kind": "stairs"},
    "slope": {"levels": [20, 30, 35, 45], "unit": "deg", "kind": "slope"},
    "high_wall": {"levels": [10, 20, 30, 40], "unit": "cm", "kind": "wall"},
    "trench": {"levels": [10, 20, 30], "unit": "cm", "kind": "gap"},
    "plum": {"levels": [1], "unit": "bool", "kind": "plum"},
}

HEADER = """<mujoco model="part2_{name}">
  <include file="../black_policy.xml"/>
  <statistic center="2.0 0 0.5" extent="3.0"/>
  <visual><global azimuth="90" elevation="-20"/></visual>
  <worldbody>
    <light pos="0 0 2" dir="0 0 -1" directional="true"/>
"""

FOOTER = """  </worldbody>
</mujoco>
"""


def platform_xml(h: float) -> str:
    half = h / 2.0
    return (
        f'    <geom name="level_floor" type="plane" size="0 0 0.05" rgba="0.2 0.2 0.2 1"/>\n'
        f'    <geom name="platform" type="box" pos="2.5 0 {half:.4f}" size="0.6 0.6 {half:.4f}"\n'
        f'          rgba="0.25 0.55 0.9 1"/>\n'
    )


def stairs_xml(h: float, n: int = 6, tread: float = 0.3) -> str:
    rise = h / n
    parts = ['    <geom name="level_floor" type="plane" size="0 0 0.05" rgba="0.2 0.2 0.2 1"/>']
    x0 = 1.5
    for i in range(n):
        z0 = i * rise
        x = x0 + i * tread
        parts.append(
            f'    <geom name="stair_{i}" type="box" pos="{x + tread/2:.4f} 0 {z0 + rise/2:.4f}" '
            f'size="{tread/2:.4f} 0.6 {rise/2:.4f}" rgba="0.25 0.55 0.9 1"/>'
        )
    top_x0 = x0 + n * tread
    parts.append(
        f'    <geom name="stair_top" type="box" pos="{top_x0 + 0.7:.4f} 0 {h/2:.4f}" '
        f'size="0.7 0.6 {h/2:.4f}" rgba="0.25 0.55 0.9 1"/>'
    )
    return "\n".join(parts) + "\n"


def slope_xml(deg: float, run: float = 1.5) -> str:
    rise = run * math.tan(math.radians(deg))
    hyp = math.hypot(run, rise)
    quat = (math.cos(math.radians(deg) / 2), 0.0, -math.sin(math.radians(deg) / 2), 0.0)
    x0 = 1.5
    parts = ['    <geom name="level_floor" type="plane" size="0 0 0.05" rgba="0.2 0.2 0.2 1"/>']
    parts.append(
        f'    <geom name="slope_ramp" type="box" pos="{x0 + run/2:.4f} 0 {rise/2:.4f}" '
        f'size="{hyp/2:.4f} 0.6 0.02" quat="{quat[0]:.8f} 0 {quat[2]:.8f} 0" '
        f'rgba="0.25 0.55 0.9 1"/>'
    )
    parts.append(
        f'    <geom name="slope_top" type="box" pos="{x0 + run + 0.8:.4f} 0 {rise/2:.4f}" '
        f'size="0.8 0.6 {rise/2:.4f}" rgba="0.25 0.55 0.9 1"/>'
    )
    return "\n".join(parts) + "\n"


def wall_xml(h: float, thick: float = 0.10) -> str:
    return (
        f'    <geom name="level_floor" type="plane" size="0 0 0.05" rgba="0.2 0.2 0.2 1"/>\n'
        f'    <geom name="wall" type="box" pos="2.5 0 {h/2:.4f}" size="{thick/2:.4f} 1.0 {h/2:.4f}"\n'
        f'          rgba="0.85 0.6 0.2 1"/>\n'
    )


def gap_xml(width: float) -> str:
    x0 = 2.5
    left_end = x0 - width / 2
    right_start = x0 + width / 2
    return (
        f'    <geom name="ground_left" type="box" pos="{(-1.0 + left_end)/2:.4f} 0 -0.025" '
        f'size="{(left_end + 1.0)/2:.4f} 1.2 0.025" rgba="0.2 0.2 0.2 1"/>\n'
        f'    <geom name="ground_right" type="box" pos="{(right_start + 6.0)/2:.4f} 0 -0.025" '
        f'size="{(6.0 - right_start)/2:.4f} 1.2 0.025" rgba="0.2 0.2 0.2 1"/>\n'
        f'    <geom name="trench_bottom" type="box" pos="{x0:.4f} 0 -0.6" size="{width/2:.4f} 1.2 0.025" '
        f'rgba="0.3 0.1 0.1 1"/>\n'
    )


def build() -> dict:
    LEVEL_DIR.mkdir(parents=True, exist_ok=True)
    meta = {"schema_version": 1, "levels": []}
    for category, spec in SPECS.items():
        for level in spec["levels"]:
            if spec["kind"] == "plum":
                scene = "assets/terrain/part2/part2_plum_eval_scene.xml"
                judge = {"kind": "plum", "goal_x_min": 2.7, "goal_z_min": 0.5, "hold_s": 0.2,
                         "start": [0.4, 0.4, 0.65, 0.0], "command": [0.5, 0.0, 0.0], "seconds": 6.0}
            else:
                name = f"{category}_{level}{spec['unit']}"
                if spec["kind"] == "platform":
                    body = platform_xml(level / 100.0)
                    judge = {"kind": "platform", "top_z": level / 100.0,
                             "goal_x": [1.9, 3.1], "hold_s": 0.2}
                elif spec["kind"] == "stairs":
                    body = stairs_xml(level / 100.0)
                    n, tread = 6, 0.3
                    judge = {"kind": "stairs", "top_z": level / 100.0,
                             "goal_x_min": 1.5 + n * tread, "hold_s": 0.2}
                elif spec["kind"] == "slope":
                    body = slope_xml(level)
                    rise = 1.5 * math.tan(math.radians(level))
                    judge = {"kind": "slope", "rise_z": rise, "goal_x_min": 1.5 + 1.5,
                             "hold_s": 0.2}
                elif spec["kind"] == "wall":
                    body = wall_xml(level / 100.0)
                    judge = {"kind": "wall", "wall_x": 2.5, "wall_h": level / 100.0,
                             "goal_x_min": 2.5 + 0.5, "climb_z_margin": 0.30, "hold_s": 0.2}
                elif spec["kind"] == "gap":  # contract id: trench
                    body = gap_xml(level / 100.0)
                    judge = {"kind": "gap", "gap_x": 2.5, "width": level / 100.0,
                             "goal_x_min": 2.5 + level / 200.0 + 0.4, "min_z": 0.3, "hold_s": 0.2}
                else:  # pragma: no cover
                    raise ValueError(spec["kind"])
                scene = f"assets/terrain/part2/levels/{name}.xml"
                xml = HEADER.format(name=name) + body + FOOTER
                (LEVEL_DIR / f"{name}.xml").write_text(xml, encoding="utf-8")
                judge.update({"start": [0.0, 0.0, 0.55, 0.0], "command": [0.5, 0.0, 0.0],
                              "seconds": 6.0})
            meta["levels"].append({
                "category": category, "level": level, "unit": spec["unit"],
                "scene": scene, "judge": judge,
            })
    META.parent.mkdir(parents=True, exist_ok=True)
    META.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return meta


if __name__ == "__main__":
    m = build()
    print(f"generated {len(m['levels'])} part2 level specs -> {META}")
    for entry in m["levels"]:
        print(entry["category"], entry["level"], entry["unit"], entry["scene"])
