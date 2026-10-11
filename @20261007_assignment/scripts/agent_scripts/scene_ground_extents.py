"""量一量场景里"三块地面"各到哪里：① 碰撞面（plane）② 可见地面（画出来的方块）③ 阴影覆盖区。

背景：这三样在画面里都像"地面"，但由完全不同的设置支配，实测数字见
[`../../../../docs/learn/mujoco.md`](../../../../docs/learn/mujoco.md) §6.10：

* ① 碰撞面 = `type="plane"` 的**无限半空间**，`size` 不参与物理；
* ② 可见地面 = 绘制方块的半宽 `size[0]`/`size[1]`（外观另由 `rgba`/`material` 决定）；
* ③ 阴影覆盖区 = `vis.map.shadowclip × stat.extent`（只对**方向光**；聚光灯用 `shadowscale × cutoff`）。

跑法（仓库根目录）：

```bash
pixi run python @20261007_assignment/scripts/agent_scripts/scene_ground_extents.py
```

判定都用"开/关对照"：阴影靠 `light_castshadow` 1↔0 的差分（conventions §5.2：先做开/关对照，
别拿整图指标下结论），可见范围靠"地板色 vs 背景色"分块。渲染走 `MUJOCO_GL=egl`（pixi 激活时已设）。
"""
from __future__ import annotations

import math
from pathlib import Path

import mujoco
import numpy as np

REPO = Path(__file__).resolve().parents[3]
SCENE = REPO / "@20261005_ros2" / "scenes" / "flat_scene.xml"

H, W = 480, 640
CAM_DIST = 20.0  # 俯视相机高度：20·tan(22.5°) → 画面覆盖 ±11.05 m(横) × ±8.28 m(纵)
SHADOW_THRESHOLD = 200  # 开/关阴影差多少像素才算"这里还有影子"


def top_down(model: mujoco.MjModel, data: mujoco.MjData) -> np.ndarray:
    """正上方俯视一张图（y 轴向上，行号随 y 减小）。"""
    cam = mujoco.MjvCamera()
    cam.type = mujoco.mjtCamera.mjCAMERA_FREE
    cam.lookat[:] = [0.0, 0.0, 0.0]
    cam.distance = CAM_DIST
    cam.azimuth = 90.0
    cam.elevation = -90.0
    mujoco.mj_resetData(model, data)
    mujoco.mj_forward(model, data)
    renderer = mujoco.Renderer(model, H, W)
    renderer.update_scene(data, cam)
    image = renderer.render().astype(int)
    renderer.close()
    return image


def shadow_pixels(model: mujoco.MjModel, data: mujoco.MjData, x: float) -> int:
    """把机器人放到 x 处，同一机位渲染两次（投影开/关）→ 差异像素数 = 影子的面积。"""
    cam = mujoco.MjvCamera()
    cam.type = mujoco.mjtCamera.mjCAMERA_FREE
    cam.lookat[:] = [x, 0.0, 0.15]
    cam.distance = 4.0
    cam.azimuth = 90.0
    cam.elevation = -70.0
    mujoco.mj_resetData(model, data)
    data.qpos[0] = x
    mujoco.mj_forward(model, data)
    renderer = mujoco.Renderer(model, 400, 400)
    model.light_castshadow[0] = 1
    renderer.update_scene(data, cam)
    on = renderer.render().astype(int)
    model.light_castshadow[0] = 0
    renderer.update_scene(data, cam)
    off = renderer.render().astype(int)
    model.light_castshadow[0] = 1
    renderer.close()
    return int((np.abs(on - off).sum(axis=2) > 12).sum())


def main() -> int:
    model = mujoco.MjModel.from_xml_path(str(SCENE))
    data = mujoco.MjData(model)
    floor = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "floor")
    print(f"MuJoCo {mujoco.__version__}｜场景 {SCENE.relative_to(REPO)}")
    print(f"  floor：type={mujoco.mjtGeom(model.geom_type[floor]).name} "
          f"size={np.round(model.geom_size[floor], 3)} rbound={model.geom_rbound[floor]:.3f}")
    print(f"  stat.extent = {model.stat.extent:.4f} m｜vis.map.shadowclip = {model.vis.map.shadowclip}"
          f"｜vis.map.shadowscale = {model.vis.map.shadowscale:.2f}（只对聚光灯）"
          f"｜vis.quality.shadowsize = {model.vis.quality.shadowsize}")
    print(f"  light[0]：type={mujoco.mjtLightType(model.light_type[0]).name} "
          f"castshadow={bool(model.light_castshadow[0])} dir={np.round(model.light_dir[0], 2)}")

    print("\n① 碰撞面：落到不同 x，看地面还在不在（plane 应当是无限半空间）")
    for x in (0.0, 6.0, 50.0, 500.0):
        mujoco.mj_resetData(model, data)
        data.qpos[0], data.qpos[1], data.qpos[2] = x, 0.0, 0.5
        for _ in range(1500):
            mujoco.mj_step(model, data)
        print(f"   x = {x:6.1f} m → 静止 z = {data.qpos[2]:.4f} m，接触点 ncon = {data.ncon}"
              f"{'（地面仍在这里托着它）' if data.ncon else '（没有接触：地面到头了）'}")

    print("\n② 可见地面：俯视图里地板色块到哪里结束（期望 = 2·size[0] × 2·size[1]）")
    image = top_down(model, data)
    half_y = CAM_DIST * math.tan(math.radians(model.vis.global_.fovy) / 2)
    half_x = half_y * W / H
    floor_rgb = image[H // 2, W // 2]
    mask = np.abs(image - floor_rgb).sum(axis=2) < 24
    cols = np.where(mask.any(axis=0))[0]
    rows = np.where(mask.any(axis=1))[0]
    to_m = lambda px, total, half: (px - (total - 1) / 2) / ((total - 1) / 2) * half  # noqa: E731
    print(f"   相机：正上方 {CAM_DIST:.0f} m、fovy={model.vis.global_.fovy}° → "
          f"画面覆盖 ±{half_x:.2f} m(横) × ±{half_y:.2f} m(纵)；地板色 = {tuple(int(v) for v in floor_rgb)}")
    print(f"   地板色块：x ∈ [{to_m(cols.min(), W, half_x):+.2f}, {to_m(cols.max(), W, half_x):+.2f}] m  "
          f"y ∈ [{to_m(rows.max(), H, half_y):+.2f}, {to_m(rows.min(), H, half_y):+.2f}] m")

    print("\n③ 阴影覆盖区：castshadow 开/关差分，看机器人在哪些 x 还有影子")
    for x in (0.0, 0.5, 1.0, 1.3, 1.5, 2.0, 3.0, 6.0):
        n = shadow_pixels(model, data, x)
        print(f"   x = {x:4.1f} m → 阴影像素 {n:6d} → {'有影' if n > SHADOW_THRESHOLD else '无影'}")
    print(f"   参照：shadowclip × stat.extent = {model.vis.map.shadowclip} × "
          f"{model.stat.extent:.4f} = {model.vis.map.shadowclip * model.stat.extent:.3f} m")

    print("\n④ 换 shadowclip（覆盖变大→同一位置影子回来；贴图仍是 shadowsize² → 会变糊）")
    for clip in (1.0, 3.0, 6.0):
        model.vis.map.shadowclip = clip
        print(f"   shadowclip = {clip:.1f} → 覆盖 ≈ ±{clip * model.stat.extent:.2f} m，"
              f"x=2 m 处阴影像素 = {shadow_pixels(model, data, 2.0)}")
    model.vis.map.shadowclip = 1.0

    print("\n⑤ 场景里换了别的东西 → stat.extent 变 → 阴影覆盖跟着变（分辨率不变，于是更糊）")
    base_extent = model.stat.extent
    for extent in (base_extent, 2.5, 4.0):
        model.stat.extent = extent
        print(f"   stat.extent = {extent:5.3f} m（×shadowclip 1.0 → 覆盖 ≈ ±{extent:.2f} m）→ "
              f"x=2 m 处阴影像素 = {shadow_pixels(model, data, 2.0)}")
    model.stat.extent = base_extent
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
