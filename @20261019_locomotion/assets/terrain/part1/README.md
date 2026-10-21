# Part 1 working scene

Working copy of the training provider's Part 1 scene, copied from the read-only file `scene_terrain (1).xml` (28,070 B, sha256 `730cce…a6d0`). The source is not committed in this repo; this copy is for local judge/visualization work.

## Changes from source

- `<include file="blackW_description.xml"/>` -> `<include file="black.xml"/>`; `black.xml` is copied from the training repo `src/alldog_mjlab/robots/black/xmls/black.xml` (primitive Black model, no STL assets).
- Removed the two training-only hfield assets/geoms (`perlin_hfield`, `image_hfield`): they are extra terrain, not part of the official Part 1 obstacle list. Extra 5 cm stairs/slope geoms are kept but ignored by the official judge.
- Added stable names for judge anchors: `high_wall`, `gravel_pit_a`, `gravel_pit_b`, `height_bar_post_a`, `height_bar_post_b`, `height_bar_beam`, `start_area`.
- Height bar remains **static** per user decision; official judge/termination will detect robot-bar contact instead of modifying the geometry.
- Gravel pit and stairs remain the source configuration (user confirmed current forms are acceptable).

## Bridge geometry (user correction)

- **5 separated square blocks** (`bridge_blocks_0..4`): full size 0.4 m × 1.0 m × 0.2 m, center x=2.65/3.20/3.75/4.30/4.85 m, y=0, gap 0.15 m between blocks; a foot in a gap can reach the floor.
- **3 narrow bands** (`bridge_bands_0..2`): full size 0.2 m × 1.5 m × 0.2 m, center x=5.35/5.65/5.95 m, y=-2.25, gap 0.10 m between bands; this is the harder bridge: a blind policy must place feet on 0.2 m strips and recover from a missed step.
- The state machine should treat these as `bridge_blocks` and `bridge_bands` sub-profiles under one `bridge` state; the judge must know which surfaces are allowed.

## Check

```bash
pixi run python - <<'PY'
import mujoco
m = mujoco.MjSpec.from_file('@20261019_locomotion/assets/terrain/part1/part1_scene.xml').compile()
print(m.nbody, m.ngeom, m.nq)
PY
pixi run python @20261019_locomotion/scripts/agent_scripts/part1_judge.py --steps 5
```
