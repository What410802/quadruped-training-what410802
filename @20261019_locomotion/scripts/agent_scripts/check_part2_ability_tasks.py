"""Validate the local six-category Part 2 ability eval spec against terrain.zip labels."""

from __future__ import annotations

import argparse
from pathlib import Path

import mujoco
import yaml


DEFAULT = "@20261019_locomotion/config/part2-ability-tasks.yaml"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=DEFAULT)
    args = parser.parse_args()
    cfg_path = Path(args.config)
    root = cfg_path.parent.parent
    cfg = yaml.safe_load(cfg_path.read_text())
    model = mujoco.MjSpec.from_file(str(root / cfg["field"])).compile()
    materials = {
        mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_MATERIAL, int(model.geom_matid[i]))
        for i in range(model.ngeom)
        if int(model.geom_matid[i]) >= 0
    }
    categories = cfg["categories"]
    expected = {"high_platform", "stairs", "slope", "gap", "high_wall", "plum"}
    missing = expected - set(categories)
    if missing:
        raise SystemExit(f"missing categories: {sorted(missing)}")
    checked = 0
    for name in sorted(expected - {"plum"}):
        labels = categories[name].get("labels", {})
        if not labels:
            raise SystemExit(f"{name}: no labels")
        for level, label in labels.items():
            if f"terrain_label_{label}" not in materials:
                raise SystemExit(f"{name}: label {label} not in field")
            checked += 1
    if categories["plum"].get("scene") != "assets/terrain/part2/part2_plum_eval_scene.xml":
        raise SystemExit("plum must use the custom part2_plum_eval_scene.xml")
    print(f"config: {args.config}")
    print(f"categories: {len(categories)}; checked labels: {checked}")
    for name in sorted(expected - {"plum"}):
        levels = categories[name].get("levels_cm", categories[name].get("levels_deg", []))
        print(f"  {name:14s} levels={levels}")
    print("OK")


if __name__ == "__main__":
    main()
