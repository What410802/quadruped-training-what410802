# Part 1 working scene

Working copy of the training provider's Part 1 scene, copied from the read-only file `scene_terrain (1).xml` (28,070 B, sha256 `730cce…a6d0`). The source is not committed in this repo; this copy is for local judge/visualization work.

## Changes from source

- `<include file="blackW_description.xml"/>` -> `<include file="black.xml"/>`; `black.xml` is copied from the training repo `src/alldog_mjlab/robots/black/xmls/black.xml` (primitive Black model, no STL assets).
- Removed the two training-only hfield assets/geoms (`perlin_hfield`, `image_hfield`): they are extra terrain, not part of the official Part 1 obstacle list. Extra 5 cm stairs/slope geoms are kept but ignored by the official judge.
- Added stable names for judge anchors: `high_wall`, `gravel_pit_a`, `gravel_pit_b`, `height_bar_post_a`, `height_bar_post_b`, `height_bar_beam`, `start_area`.
- Height bar remains **static** per user decision; official judge/termination will detect robot-bar contact instead of modifying the geometry.
- Gravel pit and stairs remain the source configuration (user confirmed current forms are acceptable).

## Check

```bash
pixi run python - <<'PY'
import mujoco
m = mujoco.MjSpec.from_file('@20261019_locomotion/assets/terrain/part1/part1_scene.xml').compile()
print(m.nbody, m.ngeom, m.nq)
PY
pixi run python @20261019_locomotion/scripts/agent_scripts/part1_judge.py --steps 5
```
