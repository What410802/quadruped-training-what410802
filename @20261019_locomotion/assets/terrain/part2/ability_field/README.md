# Part 2 官方能力场（`terrain.zip` 本地 eval 副本）

- 来源：培训方 `terrain.zip` 的 `terrain/map.xml` + `labels/`（只读素材，2026-10-21 登记）。
- `part2_ability_field.xml` 把官方能力场与 `black_policy.xml`（Black + 12 个 motor/sensor）组合，供本地 MuJoCo/Pixi eval 使用。
- 该场包含官方六类能力地形（platform/stairs/slope/gap/high wall 的 cross_bar、plum 等），以及训练性 bridge/cross_slope/rough/low_friction；档位映射见 `../official_catalog.yaml`。
- 这是**环境/场地资产**，不是训练 task；训练 task 仍在训练仓库生成。
- 核对：`pixi run python - <<'PY' ...` 编译 `nbody=20/ngeom=955/nq=19/nu=12`。
