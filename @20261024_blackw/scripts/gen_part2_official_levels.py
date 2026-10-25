#!/usr/bin/env python3
"""Generate isolated Part 2 capability scenes from the official ability field.

The organiser's ``terrain.zip`` contains ``map.xml``: the official Part 2 ability
field (one row per obstacle type, one column per difficulty).  The competition PDF
allows a custom map as long as the obstacle *types* match the provided field, so
local evaluation uses one isolated scene per official difficulty level: the
official geom definitions are copied verbatim from ``map.xml`` (same sizes, same
mesh vertices) and only translated so that each obstacle starts 1.8 m ahead of the
spawn point.

Outputs (relative to the repository root):
  @20261024_blackw/ws/src/rl_sar_blackw/scenes/blackW/part2_off_<key>.xml
  @20261024_blackw/ws/src/rl_sar_blackw/scenes/blackW/part2_official_levels.json

Usage (from MyMonoRepo.d):
  pixi run python @20261024_blackw/scripts/gen_part2_official_levels.py
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

import numpy as np

TASK = Path(__file__).resolve().parents[1]
REPO = TASK.parent
MAP_XML = (REPO / "@20261019_locomotion" / "assets" / "terrain" / "part2"
           / "ability_field" / "map.xml")
SCENE_DIR = TASK / "ws/src/rl_sar_blackw/scenes/blackW"
OUT_JSON = SCENE_DIR / "part2_official_levels.json"

ROBOT_INCLUDE = "blackW_description.xml"
RUNWAY_M = 1.8          # obstacle near face stays this far ahead of the spawn
SPAWN_Z = 0.500         # blackW trunk height with the deployment default pose on flat
BASE_REF_Z = 0.50       # judge: trunk height on flat ground
ROBOT = {"include": None}

_MESHES: dict[str, np.ndarray] = {}


def _parse_attrs(tag: str) -> dict[str, str]:
    return dict(re.findall(r'(\w+)="([^"]*)"', tag))


def _parse_floats(text: str) -> np.ndarray:
    return np.fromstring(text.replace(",", " "), sep=" ")


def _rot_z(angle: float) -> np.ndarray:
    c, s = math.cos(angle), math.sin(angle)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def _parse_xml() -> tuple[list[str], list[str], dict[str, np.ndarray]]:
    text = MAP_XML.read_text(encoding="utf-8")
    asset = re.search(r"<asset>(.*?)</asset>", text, re.S).group(1)
    meshes = re.findall(r"<mesh [^>]*/>", asset)
    mesh_vertices: dict[str, np.ndarray] = {}
    for m in meshes:
        attrs = _parse_attrs(m)
        if "vertex" in attrs:
            mesh_vertices[attrs["name"]] = _parse_floats(attrs["vertex"]).reshape(-1, 3)
    return meshes, re.findall(r"<geom [^>]*/>", text), mesh_vertices


def _geom_bbox(tag: str) -> tuple[np.ndarray, np.ndarray]:
    """Axis-aligned bbox of one geom in world coordinates (body translation excluded)."""
    a = _parse_attrs(tag)
    pos = _parse_floats(a["pos"]) if "pos" in a else np.zeros(3)
    if len(pos) < 3:
        pos = np.zeros(3)
    rot = np.eye(3)
    if "euler" in a:
        rot = _rot_z(float(a["euler"].split()[2]))
    if a["type"] == "mesh":
        v = _MESHES[a["mesh"]] @ rot.T + pos
        return v.min(axis=0), v.max(axis=0)
    size = _parse_floats(a["size"])
    if a["type"] == "box":
        half = size[:3]
    elif a["type"] == "cylinder":
        half = np.array([size[0], size[0], size[1]])
    elif a["type"] == "sphere":
        half = np.full(3, size[0])
    else:
        raise ValueError(f"unsupported geom type in official map: {a['type']}")
    return pos - half, pos + half


def _select_geoms(geom_lines: list[str], prefixes: tuple[str, ...]) -> list[str]:
    out = []
    for g in geom_lines:
        name = _parse_attrs(g)["name"]
        if any(name == p or name.startswith(p) for p in prefixes):
            out.append(g)
    return out


def _specs() -> list[dict]:
    """One entry per official difficulty level."""
    specs: list[dict] = []
    for h in (10, 20, 30, 40):
        specs.append({"category": "high_platform", "level": h, "unit": "cm",
                      "prefixes": (f"platform_{h:02d}cm",), "kind": "platform"})
    for h in (10, 15, 20, 30):
        specs.append({"category": "stairs", "level": h, "unit": "cm",
                      "prefixes": (f"stairs_{h:02d}cm_",), "kind": "stairs"})
    for deg in (20, 30, 35, 45):
        specs.append({"category": "slope", "level": deg, "unit": "deg",
                      "prefixes": (f"slope_{deg:02d}deg_",), "kind": "slope"})
    # cross_bar_1..8 = 4/8/12/16/20/30/40/50 cm tall, 1.4 m x 0.12 m.
    wall_field = {20: "cross_bar_5", 30: "cross_bar_6", 40: "cross_bar_7"}
    for h in (10, 20, 30, 40):
        specs.append({"category": "high_wall", "level": h, "unit": "cm",
                      "prefixes": (wall_field.get(h, "cross_bar_3"),), "kind": "wall",
                      "override_h": 0.10 if h == 10 else None})
    for w in (10, 20, 30):
        specs.append({"category": "trench", "level": w, "unit": "cm",
                      "prefixes": (f"trench_{w:02d}cm_",), "kind": "gap"})
    # Tier 1 plum: 0.8 x 0.8 m entry/exit platforms, 0.2 m cubes in two staggered rows.
    specs.append({"category": "plum", "level": 1, "unit": "bool",
                  "prefixes": ("plum_entry", "plum_r", "plum_exit"), "kind": "plum"})
    return specs


def _override_wall_height(geom_lines: list[str], height: float) -> list[str]:
    out = []
    for g in geom_lines:
        a = _parse_attrs(g)
        size = _parse_floats(a["size"])
        size[2] = height / 2.0
        pos = _parse_floats(a["pos"])
        pos[2] = height / 2.0
        g = re.sub(r'pos="[^"]*"', f'pos="{pos[0]} {pos[1]} {pos[2]:.6f}"', g)
        g = re.sub(r'size="[^"]*"', f'size="{size[0]} {size[1]} {size[2]:.6f}"', g)
        out.append(g)
    return out


def _rel(name: str, geoms: list[str]) -> np.ndarray:
    """World-frame bbox min of the first geom whose name contains ``name``."""
    for g in geoms:
        if name in _parse_attrs(g)["name"]:
            return _geom_bbox(g)[0]
    raise KeyError(name)


def _judge(kind: str, geoms: list[str], bmin: np.ndarray, bmax: np.ndarray,
           override_h: float | None) -> dict:
    lane = {"lane_half_width": 0.7, "hold_s": 0.20}
    if kind == "platform":
        return {"kind": "platform", "top_z": float(bmax[2]),
                "x_range": [round(float(bmin[0] + 0.20), 4),
                            round(float(bmax[0] - 0.05), 4)],
                "z_margin": 0.35, **lane}
    if kind == "stairs":
        # The official stairs obstacle is a full staircase: 6 up steps + 0.8 m
        # landing + 6 down steps (labels/stairs_XXcm.png covers both sides).  The
        # judge therefore needs the far end of the down flight, not just the
        # landing: "通过台阶" means climbing up AND descending back to the ground.
        return {"kind": "stairs", "top_z": float(bmax[2]),
                "goal_x_min": round(float(_rel("landing", geoms)[0] + 0.10), 4),
                "descend_end_x": round(float(bmax[0]), 4),
                "z_margin": 0.35, **lane}
    if kind == "slope":
        return {"kind": "slope", "rise_z": float(bmax[2]),
                "goal_x_min": round(float(_rel("landing", geoms)[0] + 0.10), 4),
                "z_margin": 0.35, **lane}
    if kind == "wall":
        h = float(bmax[2]) if override_h is None else override_h
        return {"kind": "wall", "wall_h": h,
                "wall_x": round(float((bmin[0] + bmax[0]) / 2.0), 4),
                "goal_x_min": round(float(bmax[0] + 0.35), 4),
                "climb_z_min": round(BASE_REF_Z + 0.20 * h, 4), **lane}
    if kind == "gap":
        nb = _rel("_near", geoms)
        fb = _rel("_far", geoms)
        # near/far are the top-right / top-left corners of the two plateau blocks.
        nb_max = None
        fb_min = None
        for g in geoms:
            n = _parse_attrs(g)["name"]
            if n.endswith("_near"):
                nb_max = _geom_bbox(g)[1]
            elif n.endswith("_far"):
                fb_min = _geom_bbox(g)[0]
        assert nb_max is not None and fb_min is not None
        plateau = float(nb_max[2])
        return {"kind": "gap",
                "gap_x": round(float((nb_max[0] + fb_min[0]) / 2.0), 4),
                "width": round(float(fb_min[0] - nb_max[0]), 4),
                "plateau_z": plateau,
                "near_x": round(float(nb_max[0]), 4),
                "far_x": round(float(fb_min[0]), 4),
                "z_cross_min": round(plateau + 0.28, 4), **lane}
    if kind == "plum":
        cubes = [g for g in geoms
                 if len(re.findall(r"plum_r[12]_\d+", _parse_attrs(g)["name"])) > 0]
        boxes = [_geom_bbox(g) for g in cubes]
        first_x = min(b[0][0] for b in boxes)
        last_x = max(b[1][0] for b in boxes)
        top = max(b[1][2] for b in boxes)
        return {"kind": "plum", "top_z": float(top),
                "cube_x_range": [round(float(first_x - 0.15), 4), round(float(last_x + 0.15), 4)],
                "goal_x_min": round(float(last_x + 0.55), 4),
                # Wheel-bottom contact threshold: a wheel touching the floor between
                # piles has its bottom at ~0.0 m; on a pile top it is at 0.2 m.  The
                # old value (0.55) was a *root-height* reference misused as a
                # wheel-bottom threshold, which made every plum attempt fail.
                "z_margin": 0.35, "z_cross_min": 0.05, **lane}
    raise ValueError(kind)


def _scene_text(geoms: list[str], meshes: list[str], dx: float, dy: float) -> str:
    used = {_parse_attrs(g).get("mesh") for g in geoms}
    mesh_block = "\n".join("    " + m for m in meshes
                           if _parse_attrs(m)["name"] in used)
    obs_block = "\n".join("      " + g for g in geoms)
    return (
        '<mujoco model="part2_official_level">\n'
        f'  <include file="{ROBOT_INCLUDE}"/>\n'
        '  <statistic center="2.0 0 0.5" extent="3.0"/>\n'
        '  <visual><global azimuth="90" elevation="-20"/></visual>\n'
        '  <asset>\n'
        f'{mesh_block}\n'
        '  </asset>\n'
        '  <worldbody>\n'
        '    <light pos="0 0 3" dir="0 0 -1" directional="true"/>\n'
        '    <geom name="level_floor" type="plane" size="0 0 0.05"'
        ' rgba="0.20 0.20 0.20 1"/>\n'
        '    <body name="obstacle" pos="{} {} 0">\n'.format(round(dx, 6), round(dy, 6))
        + obs_block + "\n"
        '    </body>\n'
        '  </worldbody>\n'
        '</mujoco>\n'
    )


def build() -> dict:
    global _MESHES
    meshes, geom_lines, _MESHES = _parse_xml()
    SCENE_DIR.mkdir(parents=True, exist_ok=True)
    levels = []
    for spec in _specs():
        geoms = _select_geoms(geom_lines, spec["prefixes"])
        if not geoms:
            raise RuntimeError(f"no official geoms matched {spec['prefixes']}")
        if spec.get("override_h") is not None:
            geoms = _override_wall_height(geoms, spec["override_h"])
        boxes = [_geom_bbox(g) for g in geoms]
        bmin = np.min([b[0] for b in boxes], axis=0)
        bmax = np.max([b[1] for b in boxes], axis=0)
        dx = RUNWAY_M - float(bmin[0])
        dy = -float(bmin[1] + bmax[1]) / 2.0
        # All judge fields are computed in the untranslated official frame and then
        # shifted by (dx, dy) to the generated scene's world frame.
        judge = _judge(spec["kind"], geoms, bmin, bmax, spec.get("override_h"))
        judge = _shift_judge(judge, dx, dy)
        key = (f"{spec['category']}_1" if spec["unit"] == "bool"
               else f"{spec['category']}_{spec['level']}{spec['unit']}")
        scene_name = f"part2_off_{key}.xml"
        (SCENE_DIR / scene_name).write_text(
            _scene_text(geoms, meshes, dx, dy), encoding="utf-8")
        levels.append({
            "key": key,
            "category": spec["category"],
            "level": spec["level"],
            "unit": spec["unit"],
            "scene": scene_name,
            "source": ("official terrain.zip map.xml: "
                       + ", ".join(_parse_attrs(g)["name"] for g in geoms[:3])
                       + ("..." if len(geoms) > 3 else "")),
            "obstacle_bbox": {"min": [round(float(v), 4) for v in bmin + [dx, dy, 0]],
                              "max": [round(float(v), 4) for v in bmax + [dx, dy, 0]]},
            "spawn": [0.0, 0.0, SPAWN_Z, 0.0],
            "command": [0.5, 0.0, 0.0],
            "seconds": 30.0 if spec["kind"] == "stairs" else (
                18.0 if spec["kind"] in ("slope", "plum") else 15.0),
            "judge": judge,
        })
    payload = {"schema_version": 2, "source_map": str(MAP_XML), "levels": levels}
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(f"wrote {len(levels)} official-geometry levels -> {OUT_JSON}")
    for lv in levels:
        print(f"  {lv['key']:22s} {lv['scene']:44s} {json.dumps(lv['judge'], ensure_ascii=False)}")
    return payload


def _shift_judge(judge: dict, dx: float, dy: float) -> dict:
    """Translate x/y-valued judge fields produced by ``_rel`` (untranslated)."""
    out = dict(judge)
    for k in ("goal_x_min", "wall_x", "near_x", "far_x", "gap_x", "descend_end_x"):
        if k in out:
            out[k] = round(float(out[k]) + dx, 4)
    if "x_range" in out:
        out["x_range"] = [round(float(out["x_range"][0]) + dx, 4),
                          round(float(out["x_range"][1]) + dx, 4)]
    if "cube_x_range" in out:
        out["cube_x_range"] = [round(float(out["cube_x_range"][0]) + dx, 4),
                               round(float(out["cube_x_range"][1]) + dx, 4)]
    return out


if __name__ == "__main__":
    build()
