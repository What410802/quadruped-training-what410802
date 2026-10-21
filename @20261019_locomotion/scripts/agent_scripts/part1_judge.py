"""Part-1 scene contact judge skeleton.

Loads the working copy of the team-race Part 1 scene and reports:
- foot geoms and initial foot contact state;
- any robot-body contact with the height bar (the competition forbids touching it);
- per-foot contact with floor versus named obstacle geoms.

This is a P0 primitive for the official judge; obstacle progress/score state
machines are layered on top.  It is intentionally independent from training.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from dataclasses import dataclass, field

import mujoco
import numpy as np


DEFAULT_SCENE = "@20261019_locomotion/assets/terrain/part1/part1_scene.xml"


def _id(model: mujoco.MjModel, obj: mujoco.mjtObj, name: str) -> int:
    return mujoco.mj_name2id(model, obj, name)


@dataclass
class ContactState:
    foot_ground: dict[str, bool] = field(default_factory=lambda: {"FL": False, "FR": False, "RL": False, "RR": False})
    foot_unknown: dict[str, bool] = field(default_factory=lambda: {"FL": False, "FR": False, "RL": False, "RR": False})
    bar_contact: bool = False
    bar_contact_pairs: list[tuple[int, int]] = field(default_factory=list)


class Part1Judge:
    """Minimal contact/zone judge for the Part 1 scene."""

    def __init__(self, scene_path: str = DEFAULT_SCENE) -> None:
        self.spec = mujoco.MjSpec.from_file(scene_path)
        self.model = self.spec.compile()
        self.data = mujoco.MjData(self.model)
        mujoco.mj_forward(self.model, self.data)

        self.foot_geoms: dict[str, list[int]] = {}
        for leg in ("FL", "FR", "RL", "RR"):
            body = _id(self.model, mujoco.mjtObj.mjOBJ_BODY, f"{leg}_foot")
            if body < 0:
                raise RuntimeError(f"missing foot body: {leg}_foot")
            start = int(self.model.body_geomadr[body])
            num = int(self.model.body_geomnum[body])
            self.foot_geoms[leg] = list(range(start, start + num))

        self.bar_geoms = {
            int(_id(self.model, mujoco.mjtObj.mjOBJ_GEOM, name))
            for name in ("height_bar_post_a", "height_bar_post_b", "height_bar_beam")
        }
        self.named_obstacles = {
            int(_id(self.model, mujoco.mjtObj.mjOBJ_GEOM, name))
            for name in ("high_wall", "gravel_pit_a", "gravel_pit_b", "start_area")
        }
        self.bar_geom_ids = self.bar_geoms
        self.model.opt.timestep = 0.002

    def _geom_name(self, gid: int) -> str:
        name = mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_GEOM, gid)
        return name if name else f"geom_{gid}"

    def read_contacts(self) -> ContactState:
        state = ContactState()
        foot_to_leg = {gid: leg for leg, gids in self.foot_geoms.items() for gid in gids}
        for ci in range(self.data.ncon):
            c = self.data.contact[ci]
            g1, g2 = int(c.geom1), int(c.geom2)
            # bar touched by any robot body
            if g1 in self.bar_geoms or g2 in self.bar_geoms:
                other = g2 if g1 in self.bar_geoms else g1
                body = int(self.model.geom_bodyid[other])
                if body != 0:
                    state.bar_contact = True
                    state.bar_contact_pairs.append((g1, g2))
            if g1 in foot_to_leg or g2 in foot_to_leg:
                foot_g = g1 if g1 in foot_to_leg else g2
                other = g2 if foot_g == g1 else g1
                leg = foot_to_leg[foot_g]
                if other == 0 or self.model.geom_type[other] == mujoco.mjtGeom.mjGEOM_PLANE:
                    state.foot_ground[leg] = True
                elif other in self.named_obstacles:
                    state.foot_unknown[leg] = True
                else:
                    state.foot_unknown[leg] = True
        return state

    def step(self) -> ContactState:
        mujoco.mj_step(self.model, self.data)
        return self.read_contacts()

    def summary(self) -> dict:
        st = self.read_contacts()
        return {
            "foot_geoms": {k: [self._geom_name(g) for g in v] for k, v in self.foot_geoms.items()},
            "foot_ground_initial": st.foot_ground,
            "foot_unknown_initial": st.foot_unknown,
            "bar_contact_initial": st.bar_contact,
            "bar_geom_names": sorted(self._geom_name(g) for g in self.bar_geoms),
        }


class ZoneJudge:
    """Zone/contact judge core; obstacle success state machines build on this."""

    def __init__(self, scene_path: str = DEFAULT_SCENE, zones_path: str = "@20261019_locomotion/assets/terrain/part1/judge_zones.yaml") -> None:
        import yaml
        self.base = Part1Judge(scene_path)
        cfg = yaml.safe_load(Path(zones_path).read_text())
        self.zones = {k: v["bounds"] for k, v in cfg["zones"].items()}
        self.zone_geom_cache: dict[int, str | None] = {}
        self.floor_id = 0
        for g in range(self.base.model.ngeom):
            if self.base.model.geom_type[g] == mujoco.mjtGeom.mjGEOM_PLANE:
                self.floor_id = g
                break
        self.fail: dict[str, str] = {}

    def _zone_of_point(self, xyz: np.ndarray) -> str | None:
        for name, b in self.zones.items():
            if b["x"][0] <= xyz[0] <= b["x"][1] and b["y"][0] <= xyz[1] <= b["y"][1] and b["z"][0] <= xyz[2] <= b["z"][1]:
                return name
        return None

    def _geom_zone(self, gid: int) -> str | None:
        if gid not in self.zone_geom_cache:
            self.zone_geom_cache[gid] = self._zone_of_point(self.base.data.geom_xpos[gid])
        return self.zone_geom_cache[gid]

    def read(self) -> dict:
        st = self.base.read_contacts()
        trunk = _id(self.base.model, mujoco.mjtObj.mjOBJ_BODY, "trunk")
        base_pos = self.base.data.xpos[trunk].copy()
        base_zone = self._zone_of_point(base_pos)
        ground_feet = [leg for leg, hit in st.foot_ground.items() if hit]
        # Count allowed-surface contacts per zone.
        zone_contacts: dict[str, int] = {}
        for ci in range(self.base.data.ncon):
            c = self.base.data.contact[ci]
            for gid in (int(c.geom1), int(c.geom2)):
                z = self._geom_zone(gid) if gid != self.floor_id else None
                if z:
                    zone_contacts[z] = zone_contacts.get(z, 0) + 1
        if st.bar_contact:
            self.fail.setdefault("height_bar", "bar_touched")
        for zone in ("gravel_pit", "t_stairs", "slope", "bridge_blocks", "bridge_bands"):
            if base_zone == zone and len(ground_feet) >= 2:
                self.fail.setdefault(zone, f"two_feet_ground:{','.join(ground_feet)}")
        return {
            "base_zone": base_zone,
            "base_xyz": [round(float(v), 3) for v in base_pos],
            "ground_feet": ground_feet,
            "bar_touched": st.bar_contact,
            "zone_contacts": zone_contacts,
            "fail": dict(self.fail),
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", default=DEFAULT_SCENE)
    parser.add_argument("--steps", type=int, default=20)
    parser.add_argument("--json", default="")
    parser.add_argument("--zones", action="store_true", help="run zone/contact judge core")
    args = parser.parse_args()

    if args.zones:
        judge = ZoneJudge(args.scene)
        print("scene:", args.scene)
        for i in range(args.steps):
            judge.base.step()
            if i % max(1, args.steps // 5) == 0 or i == args.steps - 1:
                print(f"step {i}: " + json.dumps(judge.read(), ensure_ascii=False))
        print("final:", json.dumps(judge.read(), ensure_ascii=False))
        return

    judge = Part1Judge(args.scene)
    print("scene:", args.scene)
    print(json.dumps(judge.summary(), ensure_ascii=False, indent=2))
    bar_events = 0
    for _ in range(args.steps):
        st = judge.step()
        if st.bar_contact:
            bar_events += 1
    result = {
        "scene": args.scene,
        "steps": args.steps,
        "bar_contact_steps": bar_events,
        "bar_touched": bar_events > 0,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.json:
        with open(args.json, "w") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
