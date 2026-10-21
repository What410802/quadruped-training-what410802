# Part 2 plum and catalog

- `part2_plum.xml`: MJCF for the official Part 2 plum obstacle, built from PDF page 4 because the provided map's plum parameters are wrong.
- `black.xml`: copy of the training repo Black model (primitive geoms), used for local scene compile.
- `official_catalog.yaml`: official Part 2 levels mapped to `terrain.zip` labels; extra training-only categories separated.
- `ability_field/part2_ability_field.xml`: local eval wrapper combining the official `terrain.zip` map + labels with `black_policy.xml`; compiled `nbody=20/ngeom=955/nq=19/nu=12`. It is an evaluation/visualization asset, not a training task.

## Plum parameters (from PDF)

- Cubes: 200 × 200 × 200 mm; platforms: 800 × 800 × 200 mm on both sides; overall length 3500 mm.
- Two rows; first cube to platform gaps 100 mm / 400 mm; row spacing 200 mm; same-row cube gaps 400 mm; overall center symmetric.
- Implementation: 3 cubes per row × 2 rows = 6 cubes; coordinates left platform 0–800 mm, right platform 2700–3500 mm; row y ranges 100–300 / 500–700 mm.
- This is a derivation from the PDF figure; if the provider has a numerically different drawing, update `part2_plum.xml` and record the source.
- Correct centers: top row x=1.0/1.6/2.2, y=0.2; bottom row x=1.3/1.9/2.5, y=0.6; platform x=0.0–0.8 / 2.7–3.5, y=0.0–0.8. `check_plum_geometry.py` verifies exact corners, gaps and center symmetry.

## Check

```bash
pixi run python @20261019_locomotion/scripts/agent_scripts/check_plum_geometry.py
```
