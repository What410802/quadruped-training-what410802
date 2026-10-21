# Part 2 plum and catalog

- `part2_plum.xml`: MJCF for the official Part 2 plum obstacle, built from PDF page 4 because the provided map's plum parameters are wrong.
- `black.xml`: copy of the training repo Black model (primitive geoms), used for local scene compile.
- `official_catalog.yaml`: official Part 2 levels mapped to `terrain.zip` labels; extra training-only categories separated.

## Plum parameters (from PDF)

- Cubes: 200 × 200 × 200 mm; platforms: 800 × 800 × 200 mm on both sides; overall length 3500 mm.
- Two rows; first cube to platform gaps 100 mm / 400 mm; row spacing 200 mm; same-row cube gaps 400 mm; overall center symmetric.
- Implementation: 3 cubes per row × 2 rows = 6 cubes; coordinates left platform 0–800 mm, right platform 2700–3500 mm; row y ranges 100–300 / 500–700 mm.
- This is a derivation from the PDF figure; if the provider has a numerically different drawing, update `part2_plum.xml` and record the source.

## Check

```bash
pixi run python - <<'PY'
import mujoco
m = mujoco.MjSpec.from_file('@20261019_locomotion/assets/terrain/part2/part2_plum.xml').compile()
print(m.nbody, m.ngeom, m.nq)
PY
```
