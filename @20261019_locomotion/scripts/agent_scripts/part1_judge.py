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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", default=DEFAULT_SCENE)
    parser.add_argument("--steps", type=int, default=20)
    parser.add_argument("--json", default="")
    args = parser.parse_args()

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
