#!/usr/bin/env python3
"""阴影锯齿诊断（**任务外的诊断工具**，不参与运行链路）：证明"阴影边缘为什么比狗的轮廓更糙"。

背景：视口里狗的**投影阴影**看起来比狗自身的轮廓更"低分辨率/锯齿"，
[`docs/learn/graphics-stack.md`](../../../docs/learn/graphics-stack.md) §8.3 与
[`docs/status.md`](../../docs/status.md) 之前的归因是"调大 `shadowsize` 没用、软阴影要靠 `light_bulbradius`"，
本脚本用**离屏渲染 + 同一相机**逐项复核这两条，并把"糙多少"量化成像素。

机制（MuJoCo 3.12 classic GL，引用的是上游 `src/render/classic/` 的源文件与行号，源码不在本仓库里）：
`src/render/classic/render_context.c:1146` 建的是 `GL_DEPTH24_STENCIL8` 阴影贴图，
`MIN/MAG_FILTER = GL_NEAREST`、`COMPARE_MODE = GL_COMPARE_R_TO_TEXTURE`、`COMPARE_FUNC = GL_GEQUAL`
→ **逐片元硬比较、没有 PCF**；`shadowClip`/`shadowSize` 只在 `mjr_makeContext` 里读一次
（同文件 1708/1722 行）→ **改这两个值必须在建 GL 上下文之前**，这正是本脚本每个配置都重建
`Renderer` 的原因。平行光的阴影投影是正交的：`glOrtho(-shadowClip, +shadowClip, …)` +
`glViewport(1, 1, shadowSize-2, shadowSize-2)`（`render_gl3.c:1272/1292`），于是

    世界空间纹素 = 2 · stat.extent · vis.map.shadowclip / (shadowsize - 2)

即**画质只取决于 `shadowclip / shadowsize` 的比值**，而不是 `shadowsize` 单独多大——
这就是"1024→4096 看不出差别"的真正原因（在同比例下确实没差别）。

指标口径（都只用 numpy）：

* `阴影掩膜` = 同一帧"阴影开/关"两图的逐像素最大通道差 > `--threshold`（默认 8）的像素，
  再与**分割渲染**得到的地板像素求交（排除狗身上的自遮蔽，它占了差值像素的四成）。
* `自由边界` = 掩膜每列最上/最下的那个像素，且它的外侧邻域必须是"**被照亮**的地板"
  （被狗挡住的那一段不算，否则量的是狗的轮廓而不是阴影）。
* `平缓列段` = 参考图（`4096/clip 0.25`，纹素 ≈0.28 px，视为准精确）上 |Δy| ≤ 1 的连续列段里最长的一段。
  相邻列 |Δy| 这个统计量量的是**斜率**，只有平缓段才能把"纹素台阶"从斜线里分出来，
  所以扫参表里所有配置都在**同一组列**上比。
* `位移` = 该配置的边界曲线与参考曲线的逐列之差（均值 / p99 / 最大）——这是不依赖斜率的量化误差，
  也是"阴影比狗轮廓糙多少"那句话的量化；狗的轮廓用**同一相机的 4× 超采样**（5120×2880 分割图）当参考。
* `texel_px` 按屏幕横向投影算（俯仰会把沿视线方向的位移压到 sin20°≈0.34 倍，横向不压）。

用法（仓库根执行）：

    pixi run python @20261005_ros2/scripts/agent_scripts/shadow_probe.py --quick   # 约 20 s
    pixi run python @20261005_ros2/scripts/agent_scripts/shadow_probe.py           # 全量，约 40 s

产物：`@20261005_ros2/output/shadow/` 下的 PNG（裁剪放大对比 + 整帧）、
`shadow_probe_summary.json` 与 `shadow_probe_summary.csv`（全部原始数字）。
阴影指标是确定性的（重跑逐位相同）；`cost_ms` 是墙钟时间，重跑会有几个百分点的波动。
"""

from __future__ import annotations

import argparse
import csv
import json
import struct
import sys
import time
import zlib
from pathlib import Path

import mujoco
import numpy as np

# ---------------------------------------------------------------- 路径与常量

ROOT = Path(__file__).resolve().parents[2]  # @20261005_ros2/（本文件在 scripts/agent_scripts/ 下）
SCENE = ROOT / "scenes" / "flat_scene.xml"
OUT_DIR = ROOT / "output" / "shadow"

# 与 viewer.hpp `ResetCamera()` / 场景 `<visual>` 保持一致
CAM_AZIMUTH = 135.0
CAM_ELEVATION = -20.0
CAM_LOOKAT = (0.0, 0.0, 0.15)
CAM_FOVY = 45.0  # 场景未改，mjVisual.Global.fovy 默认 45°

FLOOR_GEOM = 0  # 场景里地面 geom 的 id（`floor`）
BASE_SHADOWSIZE = 1024  # sim_node.cpp `viewer_shadow_size` 默认
BASE_SHADOWCLIP = 1.0  # 场景未设 `<map shadowclip>`，MuJoCo 默认 1.0
REF_SHADOWSIZE = 4096  # 参考（准精确）配置
REF_SHADOWCLIP = 0.25
THRESHOLD = 8  # 阴影掩膜阈值（逐像素最大通道差）
HARD_STEP = 120  # 复刻 viewer_snapshot.py 的"硬台阶"口径（|∇| > 120）

MUJOCO_SPOT = int(mujoco.mjtLightType.mjLIGHT_SPOT)
MUJOCO_DIRECTIONAL = int(mujoco.mjtLightType.mjLIGHT_DIRECTIONAL)


# ---------------------------------------------------------------- PNG 读写

def _png_writer():
    """优先复用 `viewer_snapshot.write_png`（该文件可能被移动到 agent_scripts/），失败就用内置兜底。"""
    for rel in ("scripts/agent_scripts", "scripts"):
        path = ROOT / rel
        if (path / "viewer_snapshot.py").exists():
            sys.path.insert(0, str(path))
            try:
                from viewer_snapshot import write_png  # type: ignore

                return write_png
            except Exception:  # noqa: BLE001 —— 对方文件被改动/移动都不该拖垮本脚本
                pass
    return _write_png_fallback


def _write_png_fallback(path: Path, rgb: np.ndarray) -> None:
    """兜底 PNG 写入（8bit RGB、非隔行）；与 `scripts/agent_scripts/viewer_snapshot.py` 的实现一致。"""
    h, w, _ = rgb.shape
    raw = b"".join(b"\x00" + rgb[y].tobytes() for y in range(h))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )


WRITE_PNG = _png_writer()


def save_png(path: Path, rgb: np.ndarray) -> None:
    WRITE_PNG(path, np.ascontiguousarray(rgb.astype(np.uint8)))


def upscale(img: np.ndarray, factor: int) -> np.ndarray:
    """最近邻放大（看纹素台阶用）。"""
    return np.repeat(np.repeat(img, factor, axis=0), factor, axis=1)


def hstack_panels(panels: list[np.ndarray], sep: int = 8, color: int = 255) -> np.ndarray:
    h = max(p.shape[0] for p in panels)
    bar = np.full((h, sep, 3), color, np.uint8)
    out = []
    for i, p in enumerate(panels):
        if p.shape[0] < h:  # 高度补齐（白/黑）：下方补分隔色
            pad = np.full((h - p.shape[0], p.shape[1], 3), color, np.uint8)
            p = np.concatenate([p, pad], axis=0)
        out.append(p)
        if i != len(panels) - 1:
            out.append(bar)
    return np.concatenate(out, axis=1)


# ---------------------------------------------------------------- 渲染

def load_model(shadowsize: int, clip: float, width: int, height: int, light: str = "directional",
               cutoff: float | None = None, bulbradius: float | None = None) -> tuple[mujoco.MjModel, mujoco.MjData]:
    """装载场景并设好**必须在建 GL 上下文之前**生效的字段（shadowsize / shadowclip / offsamples / 离屏尺寸）。"""
    m = mujoco.MjModel.from_xml_path(str(SCENE))
    m.vis.global_.offwidth = max(width, m.vis.global_.offwidth)
    m.vis.global_.offheight = max(height, m.vis.global_.offheight)
    m.vis.quality.offsamples = 0  # 关 MSAA/超采样，看的是"裸"渲染（成本测量也要求这样）
    m.vis.quality.shadowsize = shadowsize
    m.vis.map.shadowclip = clip
    if light == "spot":
        m.light_type[0] = MUJOCO_SPOT
        m.light_cutoff[0] = 45.0 if cutoff is None else cutoff
    else:
        m.light_type[0] = MUJOCO_DIRECTIONAL
    if bulbradius is not None:
        m.light_bulbradius[0] = bulbradius
    d = mujoco.MjData(m)
    mujoco.mj_resetData(m, d)  # 与 sim_node 默认 `start:=raw` 一致（XML 默认 qpos）
    mujoco.mj_forward(m, d)
    return m, d


def make_camera(dist: float) -> mujoco.MjvCamera:
    cam = mujoco.MjvCamera()
    cam.type = mujoco.mjtCamera.mjCAMERA_FREE
    cam.azimuth = CAM_AZIMUTH
    cam.elevation = CAM_ELEVATION
    cam.distance = dist
    cam.lookat[:] = CAM_LOOKAT
    return cam


def render_triple(m: mujoco.MjModel, d: mujoco.MjData, dist: float, width: int, height: int,
                  segmentation: bool = True,
                  renderer: mujoco.Renderer | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray | None, tuple[int, float]]:
    """同一相机、同一帧渲染三次：阴影开 / 阴影关 / 分割。

    注意（踩过的坑）：`mjRND_SHADOW` 是**渲染标志**，必须在**每次 `render()` 之前**设到
    `r.scene.flags` 上；`mjv_updateScene` 不动 scene flags，所以设一次能一直有效，
    但这里每次都显式设置，避免被 `enable_segmentation_rendering()` 之类的路径影响。
    `renderer` 传进来时复用它（省掉每次新建 GL 上下文），并不关闭它。
    """
    r = renderer if renderer is not None else mujoco.Renderer(m, height=height, width=width)
    cam = make_camera(dist)
    r.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = 1
    r.update_scene(d, camera=cam)
    on = r.render().copy()
    r.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = 0
    r.update_scene(d, camera=cam)
    off = r.render().copy()
    seg = None
    if segmentation:
        r.enable_segmentation_rendering()
        r.update_scene(d, camera=cam)
        seg = r.render().copy()
        r.disable_segmentation_rendering()
    ctx = getattr(r, "_mjr_context", None)
    latched = (int(ctx.shadowSize), float(ctx.shadowClip)) if ctx is not None else (0, 0.0)
    if renderer is None:
        r.close()
    return on, off, seg, latched


def displacement_hotspot(edge_a: np.ndarray, edge_b: np.ndarray, win_w: int) -> tuple[int, int]:
    """边界"抖动"最大的一段（细节放大图开在这儿才拍得到台阶；只看位移的**波动**，
    因为纯位移可能只是一条平直边界整体平移了半格，那样看起来并不锯齿）。返回 (x0, y_center)。"""
    ok = (edge_a >= 0) & (edge_b >= 0)
    if ok.sum() < 10:
        return -1, -1
    dd = np.where(ok, (edge_a - edge_b).astype(np.float64), 0.0)
    span = max(3, win_w * 3) | 1
    kern = np.ones(span) / span
    num = np.convolve(dd, kern, mode="same")
    den = np.convolve(ok.astype(np.float64), kern, mode="same")
    smooth = num / np.maximum(den, 1e-9)
    res = np.where(ok, np.abs(dd - smooth), 0.0)
    if len(res) <= win_w:
        return 0, int(np.median(edge_b[ok]))
    cum = np.cumsum(np.concatenate(([0.0], res)))
    s = cum[win_w:] - cum[:-win_w]
    x0 = int(np.argmax(s))
    cols = np.arange(x0, x0 + win_w)
    cols = cols[ok[cols]]
    yc = int(np.median(edge_b[cols])) if len(cols) else int(np.median(edge_b[ok]))
    return x0, yc


def masks_from_seg(seg: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """分割图 → (地板掩膜, 狗掩膜)。分割值 = (geom id, object type)。"""
    objid, objtype = seg[..., 0], seg[..., 1]
    geom = objtype == int(mujoco.mjtObj.mjOBJ_GEOM)
    return geom & (objid == FLOOR_GEOM), geom & (objid != FLOOR_GEOM)


def shadow_mask(on: np.ndarray, off: np.ndarray, floor: np.ndarray, thr: int = THRESHOLD) -> np.ndarray:
    diff = np.abs(on.astype(np.int16) - off.astype(np.int16)).max(axis=2)
    return (diff > thr) & floor


def pixel_delta(a: np.ndarray, b: np.ndarray) -> int:
    """两图逐像素最大通道差的最大值（用于"逐位相同"的判定）。"""
    return int(np.abs(a.astype(np.int16) - b.astype(np.int16)).max())


# ---------------------------------------------------------------- 边界与统计

def column_edge(mask: np.ndarray, side: str) -> tuple[np.ndarray, np.ndarray]:
    """每列最上（top）或最下（bot）的掩膜行号；无掩膜的列返回 -1（附"该列是否有掩膜"）。"""
    h = mask.shape[0]
    has = mask.any(axis=0)
    if side == "top":
        y = np.argmax(mask, axis=0).astype(np.int64)
    else:
        y = (h - 1 - np.argmax(mask[::-1], axis=0)).astype(np.int64)
    return np.where(has, y, -1), has


def free_edge(mask: np.ndarray, outside_ok: np.ndarray, side: str) -> np.ndarray:
    """掩膜的自由边界曲线：外侧邻域必须落在 `outside_ok`（阴影用"被照亮的地板"，狗用"非狗"）。

    被狗挡住的阴影边界（外侧邻域是狗像素）会被剔除，否则量到的是狗的轮廓而不是阴影的分辨率。
    """
    h, w = mask.shape
    y, has = column_edge(mask, side)
    nb = y - 1 if side == "top" else y + 1
    ok = has & (nb >= 0) & (nb < h)
    cols = np.nonzero(ok)[0]
    ok[cols] &= outside_ok[nb[cols], cols]
    return np.where(ok, y, -1)


def longest_smooth(y: np.ndarray, min_len: int, max_step: int = 1) -> np.ndarray:
    """曲线上 |Δy| ≤ max_step 的最长连续列段（量化台阶只在平缓处才和斜率分得开）。"""
    xs = np.nonzero(y >= 0)[0]
    if len(xs) < min_len:
        return np.zeros(0, np.int64)
    brk = np.nonzero(np.diff(xs) != 1)[0]
    starts = np.concatenate(([0], brk + 1))
    ends = np.concatenate((brk + 1, [len(xs)]))
    best: np.ndarray = np.zeros(0, np.int64)
    for a, b in zip(starts, ends):
        seg_x, seg_y = xs[a:b], y[xs[a:b]]
        good = np.nonzero(np.abs(np.diff(seg_y)) <= max_step)[0]
        if len(good) == 0:
            continue
        brk2 = np.nonzero(np.diff(good) != 1)[0]
        s2 = np.concatenate(([0], brk2 + 1))
        e2 = np.concatenate((brk2 + 1, [len(good)]))
        for c, e in zip(s2, e2):
            cand = seg_x[good[c]:good[e - 1] + 2]
            if len(cand) > len(best):
                best = cand
    return best


def staircase_stats(y: np.ndarray, cols: np.ndarray) -> dict:
    """一列一段的"台阶"统计：相邻列 |Δy| 均值/最大、不同 y 层数、常数 y 的游程中位数/最大。"""
    seq = y[cols].astype(np.int64)
    if len(seq) < 2:
        return {}
    d = np.abs(np.diff(seq))
    brk = np.nonzero(np.diff(seq) != 0)[0]
    runs = np.diff(np.concatenate(([0], brk + 1, [len(seq)])))
    return {
        "cols": int(len(seq)),
        "mean_dy": round(float(d.mean()), 3),
        "max_dy": int(d.max()),
        "levels": int(len(np.unique(seq))),
        "median_run": float(np.median(runs)),
        "max_run": int(runs.max()),
    }


def displacement(y: np.ndarray, y_ref: np.ndarray, cols: np.ndarray) -> dict:
    """与准精确参考的逐列位移（px）：均值 / p99 / 最大——不依赖斜率的量化误差。"""
    use = cols[(y[cols] >= 0) & (y_ref[cols] >= 0)]
    if len(use) < 30:
        return {"cols": int(len(use))}
    dd = (y[use] - y_ref[use]).astype(np.float64)
    return {
        "cols": int(len(use)),
        "mean": round(float(np.abs(dd).mean()), 3),
        "rms": round(float(np.sqrt((dd ** 2).mean())), 3),
        "p99": round(float(np.percentile(np.abs(dd), 99)), 2),
        "max": round(float(np.abs(dd).max()), 2),
    }


def boundary_pixels(mask: np.ndarray) -> np.ndarray:
    """4-邻域边界像素。"""
    e = np.zeros_like(mask)
    e[1:, :] |= ~mask[:-1, :]
    e[:-1, :] |= ~mask[1:, :]
    e[:, 1:] |= ~mask[:, :-1]
    e[:, :-1] |= ~mask[:, 1:]
    return mask & e


def xor_offset(mask: np.ndarray, ref: np.ndarray) -> dict:
    """与参考掩膜不一致的面积 / 参考边界长度 ≈ 边界的平均偏移（px）。"""
    xor = int((mask ^ ref).sum())
    bnd = int(boundary_pixels(ref).sum())
    return {"xor_px": xor, "ref_boundary_px": bnd, "offset_px": round(xor / max(1, bnd), 3)}


def hard_steps(img: np.ndarray, region: np.ndarray | None = None) -> int:
    """复刻 `viewer_snapshot.py` 的"硬台阶"口径（|∇| > 120 的像素数，越多越锯齿）。"""
    g = img.astype(np.int16)
    dx = np.abs(np.diff(g, axis=1)).max(axis=2)
    dy = np.abs(np.diff(g, axis=0)).max(axis=2)
    grad = np.zeros(img.shape[:2], np.int16)
    grad[:, :-1] = np.maximum(grad[:, :-1], dx)
    grad[:-1, :] = np.maximum(grad[:-1, :], dy)
    hit = grad > HARD_STEP
    return int((hit & region).sum()) if region is not None else int(hit.sum())


# ---------------------------------------------------------------- 参考（准精确）

class Reference:
    """某个相机距离 + 某种光源下的参考：准精确阴影掩膜/边界曲线 + 固定"平缓列段" + 4× 超采样狗轮廓。

    "准精确"= 4096 贴图 + clip 0.25（纹素 0.163 mm，在 0.5 m 处也只有 0.28 px）。
    """

    def __init__(self, dist: float, width: int, height: int, min_len: int, light: str = "directional",
                 cutoff: float | None = None, bulbradius: float | None = None, dog_ss: int = 4):
        m, d = load_model(REF_SHADOWSIZE, REF_SHADOWCLIP, width, height, light=light, cutoff=cutoff,
                          bulbradius=bulbradius)
        on, off, seg, latched = render_triple(m, d, dist, width, height)
        self.latched = latched
        self.floor, self.dog = masks_from_seg(seg)
        self.shadow = shadow_mask(on, off, self.floor)
        lit = self.floor & ~self.shadow
        self.top = free_edge(self.shadow, lit, "top")
        self.bot = free_edge(self.shadow, lit, "bot")
        cols_top = longest_smooth(self.top, min_len)
        cols_bot = longest_smooth(self.bot, min_len)
        self.side = "bot" if len(cols_bot) >= len(cols_top) else "top"
        self.cols = cols_bot if self.side == "bot" else cols_top
        # 狗的轮廓参考：同相机 4× 超采样（列 c ↔ 4c），列 0 视为被画幅上沿截断
        m4, d4 = load_model(REF_SHADOWSIZE, REF_SHADOWCLIP, width * dog_ss, height * dog_ss,
                            light=light, cutoff=cutoff, bulbradius=bulbradius)
        _, _, seg4, _ = render_triple(m4, d4, dist, width * dog_ss, height * dog_ss)
        _, dog4 = masks_from_seg(seg4)
        # 4×4 多数表决降采样 = "理想 1× 掩膜"，与真实 1× 二值掩膜之差即屏幕光栅化误差
        blocks = dog4.reshape(height, dog_ss, width, dog_ss).transpose(0, 2, 1, 3).reshape(height, width, -1)
        self.dog_ref = blocks.mean(axis=2) >= 0.5
        # 狗轮廓取"上沿"还是"下沿"：近距离时上沿早就出画幅，下沿（脚底/腹部）还在
        self.dog_side, self.dog_cols, self.dog_ref_y = "top", np.zeros(0, np.int64), np.zeros(width)
        best = -1
        for side in ("top", "bot"):
            y4, has4 = column_edge(dog4, side)
            y4 = np.where(has4 & (y4 > 0) & (y4 < dog_ss * height - 1), y4, -1)
            ref_y = np.full(width, -1.0)
            for c in range(width):
                block = y4[c * dog_ss:(c + 1) * dog_ss]
                block = block[block >= 0]
                if len(block) == dog_ss:  # 4 列都有效才用
                    ref_y[c] = float(block.mean()) / dog_ss
            cols = longest_smooth(ref_y, min_len)
            if len(cols) > best:
                best, self.dog_side, self.dog_cols, self.dog_ref_y = len(cols), side, cols, ref_y
        self.dog_edge_side = self.dog_side
        self.dog_y = free_edge(self.dog, ~self.dog, self.dog_side)
        self.dog_y = np.where(self.dog_y > 0, self.dog_y, -1)

    def edge(self) -> np.ndarray:
        return self.bot if self.side == "bot" else self.top


# ---------------------------------------------------------------- 单配置测量

def measure(shot: tuple, ref: Reference, m: mujoco.MjModel, dist: float, tag: str, **extra) -> dict:
    """把一个配置的阴影/狗轮廓边界统计成一条记录（所有配置都在参考给出的**同一组列**上比）。"""
    on, off, seg, latched = shot
    floor, dog = masks_from_seg(seg)
    sh = shadow_mask(on, off, floor)
    lit = floor & ~sh
    edge_cfg = free_edge(sh, lit, ref.side)
    dog_edge = free_edge(dog, ~dog, ref.dog_side)
    dog_edge = np.where(dog_edge > 0, dog_edge, -1)
    ref_edge = ref.edge()
    use = ref.cols[(edge_cfg[ref.cols] >= 0) & (ref_edge[ref.cols] >= 0)]
    dog_use = ref.dog_cols[(dog_edge[ref.dog_cols] >= 0) & (ref.dog_ref_y[ref.dog_cols] >= 0)]
    texel_mm = 2 * m.stat.extent * float(m.vis.map.shadowclip) / (int(m.vis.quality.shadowsize) - 2) * 1e3
    ppm = m.vis.global_.offheight / (2 * dist * np.tan(np.deg2rad(CAM_FOVY) / 2))
    rec = {
        "tag": tag,
        "dist": dist,
        "px_per_m": round(ppm, 1),
        "shadowsize": int(m.vis.quality.shadowsize),
        "shadowclip": round(float(m.vis.map.shadowclip), 4),
        "ctx_latched": [latched[0], round(latched[1], 4)],
        "light_type": int(m.light_type[0]),
        "cutoff": round(float(m.light_cutoff[0]), 2),
        "bulbradius": round(float(m.light_bulbradius[0]), 4),
        "texel_mm": round(texel_mm, 4),
        "texel_px": round(texel_mm * ppm / 1000, 3),
        "shadow_px": int(sh.sum()),
        "selfshadow_px": int((shadow_mask(on, off, ~floor) & dog).sum()),
        "floor_px": int(floor.sum()),
        "edge_side": ref.side,
        "dog_edge_side": ref.dog_side,
        "stair": staircase_stats(edge_cfg, use),
        "disp_vs_ref": displacement(edge_cfg, ref_edge, use),
        "offset_vs_ref": xor_offset(sh, ref.shadow),
        "dog_stair": staircase_stats(dog_edge, dog_use),
        "dog_disp_vs_4x": displacement(dog_edge, ref.dog_ref_y, dog_use),
        "dog_offset_vs_4x": xor_offset(dog, ref.dog_ref),
        "hard_px": hard_steps(on),
        "hard_px_floor": hard_steps(on, floor),
    }
    rec.update(extra)
    return rec


# ---------------------------------------------------------------- 表格输出

def print_table(title: str, header: list[str], rows: list[list[str]]) -> None:
    widths = [max([len(h)] + [len(r[i]) if i < len(r) else 0 for r in rows]) for i, h in enumerate(header)]
    line = "  ".join(h.ljust(w) for h, w in zip(header, widths))
    print(f"\n{title}")
    print(line)
    print("-" * len(line))
    for r in rows:
        print("  ".join(str(c).ljust(w) for c, w in zip(r, widths)))


def fnum(x, fmt: str = "{:.2f}", dash: str = "-") -> str:
    return dash if x is None else fmt.format(x)


# ---------------------------------------------------------------- 主流程

def main() -> int:
    ap = argparse.ArgumentParser(description="阴影锯齿诊断：阴影贴图纹素 vs 狗轮廓（离屏渲染，同一相机）")
    ap.add_argument("--quick", action="store_true", help="快速模式（少扫几档、少跑几次成本）")
    ap.add_argument("--width", type=int, default=1280, help="离屏宽（默认 1280，场景 offwidth）")
    ap.add_argument("--height", type=int, default=720, help="离屏高（默认 720，场景 offheight）")
    ap.add_argument("--out", type=Path, default=OUT_DIR, help="产物目录（默认 @20261005_ros2/output/shadow）")
    ap.add_argument("--distances", default="2.0,1.0,0.5", help="相机距离目录（逗号分隔）")
    ap.add_argument("--sweep-dist", type=float, default=0.5, help="扫参用的相机距离（默认 0.5，最能看出纹素）")
    ap.add_argument("--cost-reps", type=int, default=11, help="成本测量重复次数（取中位数，默认 11）")
    ap.add_argument("--min-smooth", type=int, default=40, help="平缓列段最短长度（默认 40 列）")
    ap.add_argument("--no-png", action="store_true", help="不写 PNG（只出表与 JSON/CSV）")
    ap.add_argument("--scale", type=int, default=5, help="裁剪放大倍数（4~8，默认 5）")
    args = ap.parse_args()

    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    # 只清自己上一次跑出来的产物（避免快捷模式留下的旧图与全量结果混在一起）
    for stale in sorted(out_dir.glob("shadow_*.png")) + sorted(out_dir.glob("shadow_probe_summary.*")):
        if stale.is_file():
            stale.unlink()
            print(f"清理旧产物：{stale.name}")
    distances = [float(v) for v in args.distances.split(",")]
    sweep_sizes = [1024, 4096] if args.quick else [1024, 2048, 4096]
    clips = [1.0, 0.25] if args.quick else [1.0, 0.5, 0.25]
    degrade = [] if args.quick else [256, 64]
    reps = 5 if args.quick else args.cost_reps
    cost_big = not args.quick
    images: list[dict] = []

    print(f"场景：{SCENE.relative_to(ROOT.parent)}  离屏：{args.width}x{args.height}  outsamples=0")
    print(f"相机：azimuth {CAM_AZIMUTH}、elevation {CAM_ELEVATION}、lookat {CAM_LOOKAT}、fovy {CAM_FOVY}°"
          f"（与 viewer.hpp ResetCamera 一致）")

    # ---- 0) 各距离的参考（准精确）
    refs: dict[float, Reference] = {}
    records: list[dict] = []
    dist_rows: list[list[str]] = []
    frames: dict[float, dict] = {}
    t0 = time.perf_counter()
    for dist in distances:
        refs[dist] = Reference(dist, args.width, args.height, args.min_smooth)
        print(f"参考 @ {dist:.2f} m：4096/clip{REF_SHADOWCLIP}（纹素 {2 * refs[dist].latched[1] / (REF_SHADOWSIZE - 2) * 1e3:.3f} mm）"
              f" → {refs[dist].side} 边平缓段 {len(refs[dist].cols)} 列、狗轮廓平缓段 {len(refs[dist].dog_cols)} 列")
    ref_ms = (time.perf_counter() - t0) * 1e3
    print(f"参考耗时 {ref_ms:.0f} ms")

    # ---- 1) 距离目录：当前默认 1024/clip1.0
    for dist in distances:
        m, d = load_model(BASE_SHADOWSIZE, BASE_SHADOWCLIP, args.width, args.height)
        shot = render_triple(m, d, dist, args.width, args.height)
        rec = measure(shot, refs[dist], m, dist, f"viewer默认 {BASE_SHADOWSIZE}/clip{BASE_SHADOWCLIP}")
        records.append(rec)
        frames[dist] = {"on": shot[0], "off": shot[1], "shadowsize": BASE_SHADOWSIZE, "clip": BASE_SHADOWCLIP}
        dist_rows.append([
            f"{dist:.1f}", f"{rec['px_per_m']:.0f}", f"{rec['texel_mm']:.2f}", f"{rec['texel_px']:.2f}",
            str(rec["shadow_px"]), fnum(rec["stair"].get("mean_dy")), str(rec["stair"].get("max_dy", "-")),
            str(rec["stair"].get("levels", "-")), fnum(rec["stair"].get("median_run"), "{:.0f}"),
            fnum(rec["disp_vs_ref"].get("mean")), fnum(rec["disp_vs_ref"].get("p99")),
            str(rec["offset_vs_ref"]["offset_px"]),
            fnum(rec["dog_stair"].get("mean_dy")), fnum(rec["dog_stair"].get("median_run"), "{:.0f}"),
            fnum(rec["dog_disp_vs_4x"].get("mean")), str(rec["dog_offset_vs_4x"]["offset_px"]),
            fnum(rec["offset_vs_ref"]["offset_px"] / max(1e-9, rec["dog_offset_vs_4x"]["offset_px"]), "{:.1f}x"),
        ])

    # ---- 2) 扫参：shadowsize × shadowclip（默认在 --sweep-dist 上）
    sweep_rows: list[list[str]] = []
    sweep_cache: dict[tuple[int, float], tuple] = {}
    combos = [(ss, c) for ss in sweep_sizes for c in clips] + [(ss, 1.0) for ss in degrade]
    for ss, clip in combos:
        m, d = load_model(ss, clip, args.width, args.height)
        shot = render_triple(m, d, args.sweep_dist, args.width, args.height)
        sweep_cache[(ss, clip)] = (shot, m)
        rec = measure(shot, refs[args.sweep_dist], m, args.sweep_dist, f"{ss}/clip{clip}")
        records.append(rec)
        sweep_rows.append([
            str(ss), f"{clip:g}", f"{rec['texel_mm']:.3f}", f"{rec['texel_px']:.2f}",
            str(rec["shadow_px"]), fnum(rec["stair"].get("mean_dy")), str(rec["stair"].get("max_dy", "-")),
            str(rec["stair"].get("levels", "-")), fnum(rec["stair"].get("median_run"), "{:.0f}"),
            str(rec["stair"].get("max_run", "-")),
            fnum(rec["disp_vs_ref"].get("mean")), fnum(rec["disp_vs_ref"].get("p99")),
            str(rec["offset_vs_ref"]["offset_px"]),
        ])
    sweep_rows.sort(key=lambda r: (float(r[2]), int(r[0])))

    # ---- 3) 光照对照：方向光 vs 聚光灯、bulbradius 是否真的无效
    #  注意：聚光灯改的是**光照**（地面变暗、阴影形状也随投影变化），
    #  所以每种光型都要有**自己的**准精确参考，否则"位移"量的是两种光的差异而不是分辨率。
    light_cfgs = [("directional", None, 0.02, "方向光（现状）"), ("directional", None, 0.3, "方向光 + bulb0.3")]
    if args.quick:
        light_cfgs.append(("spot", 45.0, 0.02, "聚光 cutoff45"))
    else:
        light_cfgs += [
            ("spot", 45.0, 0.02, "聚光 cutoff45（场景 cutoff）"),
            ("spot", 90.0, 0.3, "聚光 cutoff90 + bulb0.3（旧配方）"),
            ("directional", None, 0.3, "方向光 + bulb0.3"),
            ("spot", 45.0, 0.3, "聚光 cutoff45 + bulb0.3"),
        ]
    light_rows: list[list[str]] = []
    light_frames: dict[str, np.ndarray] = {}
    bulb_pairs: list[dict] = []
    base_img: dict[str, np.ndarray] = {}
    light_refs: dict[tuple, Reference] = {}
    for kind, cutoff, bulb, label in light_cfgs:
        key = (kind, cutoff)
        if key not in light_refs:
            light_refs[key] = Reference(args.sweep_dist, args.width, args.height, args.min_smooth,
                                        light=kind, cutoff=cutoff, bulbradius=0.02)
        ref = light_refs[key]
        m, d = load_model(BASE_SHADOWSIZE, BASE_SHADOWCLIP, args.width, args.height,
                          light=kind, cutoff=cutoff, bulbradius=bulb)
        shot = render_triple(m, d, args.sweep_dist, args.width, args.height)
        rec = measure(shot, ref, m, args.sweep_dist, label, light=kind, cutoff_val=cutoff, bulb=bulb)
        # 聚光灯的纹素按"灯下 3 m 处"的透视范围估：fovy = min(2·cutoff·shadowScale, 160)°
        if kind == "spot":
            fovy = min(2 * float(m.light_cutoff[0]) * float(m.vis.map.shadowscale), 160.0)
            est = 2 * 3.0 * np.tan(np.deg2rad(fovy) / 2) / (BASE_SHADOWSIZE - 2) * 1e3
            rec["texel_mm"] = round(est, 4)
            rec["texel_px"] = round(est * rec["px_per_m"] / 1000, 3)
            rec["texel_note"] = f"透视投影 fovy={fovy:.0f}°，按灯下 3 m 处估"
        records.append(rec)
        key_img = f"{kind}|cutoff={cutoff}|bulb={bulb}"
        base_img[key_img] = shot[0]
        light_frames[label] = shot[0]
        light_rows.append([
            label, str(rec["light_type"]), fnum(rec["cutoff"], "{:.0f}"), f"{rec['bulbradius']:.2f}",
            str(rec["shadow_px"]), fnum(rec["stair"].get("mean_dy")),
            str(rec["offset_vs_ref"]["offset_px"]), str(rec["hard_px"]), str(rec["hard_px_floor"]),
            fnum(rec["texel_mm"], "{:.3f}"),
        ])
    # bulbradius 成对比较：同一光型、只换灯泡半径 → 必须逐位相同
    for kind, cutoff in (("directional", None), ("spot", 45.0), ("spot", 90.0)):
        a = base_img.get(f"{kind}|cutoff={cutoff}|bulb=0.02")
        b = base_img.get(f"{kind}|cutoff={cutoff}|bulb=0.3")
        if a is not None and b is not None:
            bulb_pairs.append({"light": kind, "cutoff": cutoff, "max_pixel_diff": pixel_delta(a, b),
                               "identical": bool(np.array_equal(a, b))})

    # ---- 4) 成本：mjr_render + readback 墙钟（中位数）
    cost_rows: list[list[str]] = []
    cost_records: list[dict] = []
    for ss in (1024, 2048, 4096):
        row = [str(ss)]
        entry = {"shadowsize": ss}
        for (w, h, label) in [(args.width, args.height, "small")] + (
                [(2560, 1440, "viewer2x")] if cost_big else []):
            m, d = load_model(ss, BASE_SHADOWCLIP, w, h)
            cam = make_camera(2.0)  # 视口默认距离
            t = time.perf_counter()
            r = mujoco.Renderer(m, height=h, width=w)
            ctx_ms = (time.perf_counter() - t) * 1e3
            r.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = 1
            for _ in range(2):  # 预热
                r.update_scene(d, camera=cam)
                r.render()
            on_ms, upd_ms = [], []
            for _ in range(reps):
                t = time.perf_counter()
                r.update_scene(d, camera=cam)
                upd_ms.append((time.perf_counter() - t) * 1e3)
                t = time.perf_counter()
                r.render()
                on_ms.append((time.perf_counter() - t) * 1e3)
            r.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = 0
            off_ms = []
            for _ in range(reps):
                r.update_scene(d, camera=cam)
                t = time.perf_counter()
                r.render()
                off_ms.append((time.perf_counter() - t) * 1e3)
            r.close()
            entry[label] = {
                "size": f"{w}x{h}", "shadow_on_ms": round(float(np.median(on_ms)), 2),
                "shadow_off_ms": round(float(np.median(off_ms)), 2),
                "shadow_cost_ms": round(float(np.median(on_ms) - np.median(off_ms)), 2),
                "update_scene_ms": round(float(np.median(upd_ms)), 2),
                "context_ms": round(ctx_ms, 1),
                "reps": reps,
            }
            row += [f"{entry[label]['shadow_on_ms']:.2f}", f"{entry[label]['shadow_off_ms']:.2f}",
                    f"{entry[label]['shadow_cost_ms']:+.2f}", f"{entry[label]['context_ms']:.0f}"]
        cost_rows.append(row)
        cost_records.append(entry)

    # ---- 5) PNG
    reach_records: list[dict] = []
    if not args.no_png:
        d0 = args.sweep_dist
        cand_keys = [(BASE_SHADOWSIZE, BASE_SHADOWCLIP)] + [
            (ss, c) for ss, c in ((4096, 0.25), (2048, 0.5), (4096, 1.0)) if (ss, c) in sweep_cache]
        # 裁剪窗口开在"默认配置边界抖动最大"的地方（否则可能裁到看不出差别的直线段上）
        ref_mask = refs[d0].shadow
        masks_by_key = {}
        for key in cand_keys:
            shot, _ = sweep_cache[key]
            fl, _ = masks_from_seg(shot[2])
            masks_by_key[key] = (shadow_mask(shot[0], shot[1], fl), fl)
        edge_ref = refs[d0].edge()
        _m0, _f0 = masks_by_key[cand_keys[0]]
        edge_def = free_edge(_m0, _f0 & ~_m0, refs[d0].side)
        hx, hy = displacement_hotspot(edge_def, edge_ref, 280 if not args.quick else 240)
        cw, ch = (280, 175) if not args.quick else (240, 170)
        x0 = min(max(0, hx - cw // 2), args.width - cw)
        y0 = min(max(0, hy - ch // 2), args.height - ch)
        def crop(img: np.ndarray) -> np.ndarray:
            return img[y0:y0 + ch, x0:x0 + cw]

        panels, labels = [], []
        for key in cand_keys:
            panels.append(upscale(crop(sweep_cache[key][0][0]), args.scale))
            labels.append(f"{key[0]}/clip{key[1]:g}")
        # 最后一块：与准精确参考的分歧（红 = 默认配置多出来的阴影，蓝 = 参考里才有的阴影）
        base = crop(sweep_cache[cand_keys[0]][0][0]).copy() // 2 + 100
        diff_a, diff_b = masks_by_key[cand_keys[0]][0], ref_mask
        only_a, only_b = crop(diff_a) & ~crop(diff_b), crop(diff_b) & ~crop(diff_a)
        base[only_a] = (255, 40, 40)
        base[only_b] = (40, 80, 255)
        panels.append(upscale(base, args.scale))
        labels.append("红=默认多、蓝=参考多（与准精确参考的分歧）")
        name = "shadow_crop_" + "_vs_".join(f"{k[0]}_clip{k[1]:g}" for k in cand_keys) + ".png"
        save_png(out_dir / name, hstack_panels(panels))
        images.append({"file": name, "panels": labels, "crop_xywh": [int(x0), int(y0), int(cw), int(ch)],
                       "scale": args.scale, "note": "裁剪窗口取'默认配置 vs 准精确参考'分歧最多处"})

        # 同一热点的小窗口 8× 放大（3 块：默认 / 4096·clip1 / 4096·clip0.25），专门拍"台阶"落在哪儿
        dw, dh, dscale = 120, 90, 8
        hx, hy = displacement_hotspot(edge_def, edge_ref, dw)
        dx0 = min(max(0, hx - dw // 4), args.width - dw)
        dy0 = min(max(0, hy - dh // 2), args.height - dh)
        detail_keys = [k for k in cand_keys[:1] + [(4096, 1.0), (4096, 0.25)] if k in sweep_cache]
        detail = [upscale(sweep_cache[k][0][0][dy0:dy0 + dh, dx0:dx0 + dw], dscale) for k in detail_keys]
        # 再补一块：把两条边界曲线叠在暗化后的画面上（红 = 默认 1024/clip1 的边界，蓝 = 准精确参考）
        overlay = (sweep_cache[cand_keys[0]][0][0][dy0:dy0 + dh, dx0:dx0 + dw] // 3 + 80).astype(np.uint8)
        for x in range(dx0, dx0 + dw):
            for y, col in ((edge_def[x], (255, 40, 40)), (edge_ref[x], (40, 80, 255))):
                if 0 <= y < args.height and dy0 <= y < dy0 + dh:
                    overlay[int(y) - dy0, x - dx0] = col
        detail.append(upscale(overlay, dscale))
        save_png(out_dir / "shadow_crop_detail_8x.png", hstack_panels(detail, sep=4))
        images.append({"file": "shadow_crop_detail_8x.png",
                       "panels": [f"{k[0]}/clip{k[1]:g}" for k in detail_keys]
                                 + ["红=1024/clip1 的阴影边界、蓝=准精确参考的边界（同一段）"],
                       "crop_xywh": [int(dx0), int(dy0), dw, dh], "scale": dscale,
                       "note": "窗口取边界抖动最大处"})

        # 整帧对：默认 vs 最优候选（+ 阴影关）
        best_key = (4096, 1.0) if (4096, 1.0) in sweep_cache else cand_keys[-1]
        full = [sweep_cache[(BASE_SHADOWSIZE, BASE_SHADOWCLIP)][0][0],
                sweep_cache[best_key][0][0],
                frames[d0]["off"]]
        save_png(out_dir / "shadow_full_default_vs_best.png", hstack_panels(full, sep=6))
        images.append({"file": "shadow_full_default_vs_best.png",
                       "panels": [f"{BASE_SHADOWSIZE}/clip{BASE_SHADOWCLIP}",
                                  f"{best_key[0]}/clip{best_key[1]:g}", "阴影关"]})
        save_png(out_dir / f"shadow_full_{BASE_SHADOWSIZE}_clip{BASE_SHADOWCLIP:g}.png", full[0])
        save_png(out_dir / f"shadow_full_{best_key[0]}_clip{best_key[1]:g}.png", full[1])
        images += [{"file": f"shadow_full_{BASE_SHADOWSIZE}_clip{BASE_SHADOWCLIP:g}.png"},
                   {"file": f"shadow_full_{best_key[0]}_clip{best_key[1]:g}.png"}]

        # 光照对照（整帧，方向光 vs 旧配方的聚光）
        ll = [light_frames.get("方向光（现状）"), light_frames.get("聚光 cutoff90 + bulb0.3（旧配方）")]
        if all(v is not None for v in ll):
            save_png(out_dir / "shadow_light_directional_vs_spot.png", hstack_panels(ll, sep=6))
            images.append({"file": "shadow_light_directional_vs_spot.png",
                           "panels": ["方向光（现状）", "聚光 cutoff90 + bulb0.3（旧配方）"]})

        # shadowclip 的"覆盖范围"：把狗挪开再看（阴影盒以世界原点为中心，clip 决定半径）
        reach_panels, reach_labels = [], []
        for clip in (BASE_SHADOWCLIP, 0.5, 0.25):
            mm, dd = load_model(BASE_SHADOWSIZE, clip, args.width, args.height)
            rr = mujoco.Renderer(mm, height=args.height, width=args.width)
            for x in (0.0, 0.5, 1.5):
                dd.qpos[0] = x  # 沿 x 挪（阴影盒中心在世界原点，不在狗身上）
                mujoco.mj_forward(mm, dd)
                s = render_triple(mm, dd, 1.0, args.width, args.height, renderer=rr)
                fl, _ = masks_from_seg(s[2])
                reach_records.append({"shadowsize": BASE_SHADOWSIZE, "clip": clip, "dog_x_m": x,
                                      "shadow_px": int(shadow_mask(s[0], s[1], fl).sum())})
                if x == 0.5:
                    reach_panels.append(s[0])
                    reach_labels.append(f"clip{clip:g}（阴影 {reach_records[-1]['shadow_px']} px）")
            rr.close()
        save_png(out_dir / "shadow_clip_reach_dog_moved_0p5m.png", hstack_panels(reach_panels, sep=6))
        images.append({"file": "shadow_clip_reach_dog_moved_0p5m.png", "panels": reach_labels,
                       "note": "狗沿 +x 挪 0.5 m（相机 1.0 m）：clip 决定阴影盒覆盖半径，太小就整块没有阴影"})

        # 距离三连（同一阴影在哪一档在屏幕上更明显）
        if all(dist in frames for dist in distances):
            panels = []
            for dist in distances:
                img = frames[dist]["on"]
                hh, ww = img.shape[:2]
                cx, cy = ww // 2, int(hh * 0.62)
                panels.append(upscale(img[max(0, cy - 90):cy + 90, max(0, cx - 150):cx + 150], 3))
            save_png(out_dir / "shadow_distances_2_1_0p5.png", hstack_panels(panels, sep=6))
            images.append({"file": "shadow_distances_2_1_0p5.png",
                           "panels": [f"{d:.1f} m" for d in distances], "scale": 3})

    # ---- 6) 表与机器可读结果
    print_table("① 距离目录（当前默认 1024/clip1.0，与视口相机一致；"
                "'偏移' = 边界与准精确参考的平均距离，px；'倍数' = 阴影偏移 / 狗轮廓偏移）",
                ["距离m", "px/m", "纹素mm", "纹素px", "阴影px", "mean|Δy|", "max|Δy|", "层数", "游程中位",
                 "位移mean", "位移p99", "阴影偏移", "狗mean|Δy|", "狗游程", "狗位移mean", "狗偏移", "倍数"],
                dist_rows)
    print_table(f"② 扫参 shadowsize × shadowclip（距离 {args.sweep_dist} m，同一组平缓列；"
                f"纹素 = 2·extent·clip/(shadowsize-2)）",
                ["shadowsize", "clip", "纹素mm", "纹素px", "阴影px", "mean|Δy|", "max|Δy|", "层数", "游程中位",
                 "最长游程", "位移mean", "位移p99", "不一致px/边界px"],
                sweep_rows)
    print_table("③ 光照对照（均 1024/clip1.0；每种光型各自与**同光型的准精确参考**比，"
                "硬台阶 = 整图 |∇|>120，复刻 viewer_snapshot 口径）",
                ["配置", "type", "cutoff", "bulb", "阴影px", "mean|Δy|", "边界偏移px", "整图硬台阶", "地面硬台阶",
                 "纹素mm"],
                light_rows)
    cost_header = ["shadowsize"]
    if cost_records:
        for k in [k for k in ("small", "viewer2x") if k in cost_records[0]]:
            cost_header += [f"{cost_records[0][k]['size']} 开", f"{cost_records[0][k]['size']} 关",
                            f"{cost_records[0][k]['size']} 净增", f"{cost_records[0][k]['size']} 建上下文"]
    print_table(f"④ 成本：mjr_render + readback 中位数（offsamples=0、无 vsync，{reps} 次；"
                f"'净增'= 阴影开 − 阴影关；'建上下文'= Renderer 构造，改 shadowsize 要重启就是它；"
                f"视口实际是 1280x720 逻辑 ×2 超采样 = 2560x1440）", cost_header, cost_rows)

    if reach_records:
        print("\n⑦ shadowclip 的覆盖半径（狗沿 +x 挪开，相机 1.0 m，1024 贴图）")
        for clip in (BASE_SHADOWCLIP, 0.5, 0.25):
            cells = [r for r in reach_records if r["clip"] == clip]
            print(f"  clip {clip:g}（±{clip * mujoco.MjModel.from_xml_path(str(SCENE)).stat.extent:.2f} m）："
                  + "，".join(f"狗在 x={r['dog_x_m']:.1f} → 阴影 {r['shadow_px']} px" for r in cells))

    print("\n⑤ bulbradius 成对比较（同光型、只改灯泡半径）")
    for p in bulb_pairs:
        print(f"  {p['light']:12s} cutoff={p['cutoff']} 0.02 vs 0.3：最大像素差 {p['max_pixel_diff']}"
              f" → {'逐位相同 ✓' if p['identical'] else '有差异 ✗'}")

    # 同画质组：纹素相同 → 由 2·extent·clip/(size-2) 决定，可用 clip 换 size
    cost_by_size = {c["shadowsize"]: c for c in cost_records}
    groups: dict[float, list[dict]] = {}
    for rec in records:
        if rec["tag"].startswith(("1024/", "2048/", "4096/", "256/", "64/")):
            groups.setdefault(round(rec["texel_mm"], 3), []).append(rec)
    print("\n⑥ 同纹素组（画质等价、成本不同，用来选默认；成本 = 1280x720 阴影开的中位帧时间）")
    for texel in sorted(groups):
        members = []
        for r in sorted(groups[texel], key=lambda r: r["shadowsize"]):
            c = cost_by_size.get(r["shadowsize"], {}).get("small", {})
            ms = f"{c['shadow_on_ms']:.2f} ms" if c else "-"
            members.append(f"{r['shadowsize']}/clip{r['shadowclip']:g}（偏移 {r['offset_vs_ref']['offset_px']} px、"
                           f"覆盖 ±{r['shadowclip'] * mujoco.MjModel.from_xml_path(str(SCENE)).stat.extent:.2f} m、{ms}）")
        print(f"  纹素 {texel:.3f} mm：" + "；".join(members))

    summary = {
        "meta": {
            "scene": str(SCENE.relative_to(ROOT.parent)),
            "renderer": f"MuJoCo {mujoco.__version__} classic GL，offsamples=0，{args.width}x{args.height}",
            "camera": {"azimuth": CAM_AZIMUTH, "elevation": CAM_ELEVATION, "lookat": list(CAM_LOOKAT),
                       "fovy": CAM_FOVY, "upstream": "viewer.hpp ResetCamera()"},
            "stat_extent_m": round(mujoco.MjModel.from_xml_path(str(SCENE)).stat.extent, 6),
            "threshold": THRESHOLD,
            "reference": {"shadowsize": REF_SHADOWSIZE, "shadowclip": REF_SHADOWCLIP,
                          "texel_mm": round(2 * mujoco.MjModel.from_xml_path(str(SCENE)).stat.extent
                                            * REF_SHADOWCLIP / (REF_SHADOWSIZE - 2) * 1e3, 4)},
            "smooth_cols": {f"{d:.1f}": int(len(refs[d].cols)) for d in distances},
            "dog_smooth_cols": {f"{d:.1f}": int(len(refs[d].dog_cols)) for d in distances},
            "edge_side": {f"{d:.1f}": refs[d].side for d in distances},
            "quick": args.quick,
            "determinism": "图像类指标确定性；cost_ms 为墙钟中位数，重跑有波动",
        },
        "records": records,
        "cost": cost_records,
        "bulbradius_pairs": bulb_pairs,
        "clip_reach": reach_records,
        "images": images,
    }
    (out_dir / "shadow_probe_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    flat_keys = ["tag", "dist", "px_per_m", "shadowsize", "shadowclip", "light_type", "cutoff", "bulbradius",
                 "texel_mm", "texel_px", "shadow_px", "selfshadow_px", "floor_px", "edge_side",
                 "hard_px", "hard_px_floor"]
    with (out_dir / "shadow_probe_summary.csv").open("w", newline="", encoding="utf-8") as fp:
        writer = csv.writer(fp)
        writer.writerow(flat_keys + ["stair_cols", "mean_dy", "max_dy", "levels", "median_run",
                                     "disp_mean", "disp_p99", "disp_max", "xor_px", "offset_px",
                                     "dog_mean_dy", "dog_disp_mean"])
        for rec in records:
            writer.writerow([rec.get(k) for k in flat_keys]
                            + [rec["stair"].get("cols"), rec["stair"].get("mean_dy"), rec["stair"].get("max_dy"),
                               rec["stair"].get("levels"), rec["stair"].get("median_run"),
                               rec["disp_vs_ref"].get("mean"), rec["disp_vs_ref"].get("p99"),
                               rec["disp_vs_ref"].get("max"), rec["offset_vs_ref"]["xor_px"],
                               rec["offset_vs_ref"]["offset_px"],
                               rec["dog_stair"].get("mean_dy"), rec["dog_disp_vs_4x"].get("mean")])
    print(f"\n产物目录：{out_dir}")
    for img in images:
        print(f"  PNG  {img['file']}")
    print(f"  JSON shadow_probe_summary.json（{len(records)} 条记录）")
    print("  CSV  shadow_probe_summary.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
