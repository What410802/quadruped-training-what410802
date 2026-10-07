#!/usr/bin/env python3
"""视口截图与画质对比（**任务外的诊断工具**，不参与运行链路）。

为什么在脚本里而不是写进 `viewer.hpp`：截图/分段计时这类东西只服务于"调画质"这一次性活动，
放进主代码会污染主思路；而渲染结果最终要**人眼确认**（HITL）才可靠。所以这里做成：
用系统截图工具抓我们窗口所在的屏幕 → 裁切 → 存 PNG（给你看）→ 顺带算两个客观指标（给自己比）。

用法（窗口先跑起来，见 README「快速开始」）：

    # 抓全屏存 PNG（默认用 spectacle，KDE 自带；别的桌面用 --shot-cmd 换）
    pixi run python @20261005_ros2/scripts/agent_scripts/viewer_snapshot.py --out /tmp/shot.png

    # 只关心狗的腿部/阴影那一块，并和上一次对比（左旧右新 + 指标）
    pixi run python @20261005_ros2/scripts/agent_scripts/viewer_snapshot.py --out /tmp/new.png \
        --crop 1150,880,1750,1120 --compare /tmp/old.png --compare-out /tmp/diff.png

指标说明（同一相机的两张图才有可比性）：`硬台阶` = 相邻像素通道差 > 120 的像素数（越多越"锯齿"）、
`过渡` = 差值在 20~120 之间的像素数（抗锯齿/软阴影会把它抬高）、`p99.9` = 梯度幅值的 99.9 分位
（越小越平滑）。它们只用来**辅助**判断，最终请以 PNG 为准。
"""

from __future__ import annotations

import argparse
import shutil
import struct
import subprocess
import sys
import zlib
from pathlib import Path

import numpy as np


def shoot(cmd: str, out: Path) -> None:
    """调用外部截图工具抓全屏（默认 spectacle：KDE 自带，Wayland 下也能抓）。"""
    if not shutil.which(cmd.split()[0]):
        sys.exit(f"找不到截图工具 {cmd.split()[0]}；用 --shot-cmd 指定（或自己截图后 --input 传进来）")
    out.parent.mkdir(parents=True, exist_ok=True)
    # 截图工具会偶发失败（KWin 的 D-Bus 请求超时），重试几次；仍失败就给出手动兜底
    for attempt in range(1, 4):
        if out.exists():
            out.unlink()
        try:
            subprocess.run([*cmd.split(), str(out)], check=True)
        except subprocess.CalledProcessError:
            pass
        if out.exists() and out.stat().st_size > 0:
            print(f"截图：{out}（第 {attempt} 次成功）")
            return
        print(f"第 {attempt} 次截图失败（{cmd} 没产出文件），重试…")
    sys.exit(
        f"截图失败：{cmd} 三次都没产出文件。可以① 手动截图后用 --input 传路径；"
        "② 换工具：--shot-cmd 'gnome-screenshot -f' / 'grim' / 'import -window root'"
    )


def read_png(path: Path) -> np.ndarray:
    """读 PNG（只支持 8bit RGB/RGBA 非隔行，够用；避免引入 Pillow 依赖）。"""
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "不是 PNG"
    pos, idat, w, h, ch = 8, b"", 0, 0, 0
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        tag = data[pos + 4 : pos + 8]
        body = data[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if tag == b"IHDR":
            w, h, depth, color, _, _, interlace = struct.unpack(">IIBBBBB", body)
            assert depth == 8 and interlace == 0, "只支持 8bit 非隔行"
            ch = {2: 3, 6: 4, 0: 1}[color]
        elif tag == b"IDAT":
            idat += body
        elif tag == b"IEND":
            break
    raw = zlib.decompress(idat)
    stride = w * ch
    out = np.zeros((h, stride), dtype=np.uint8)
    prev = np.zeros(stride, dtype=np.uint8)
    p = 0
    for y in range(h):
        f = raw[p]
        line = np.frombuffer(raw[p + 1 : p + 1 + stride], dtype=np.uint8).copy()
        p += 1 + stride
        if f == 1:  # Sub
            for i in range(ch, stride):
                line[i] = (int(line[i]) + int(line[i - ch])) & 0xFF
        elif f == 2:  # Up
            line = (line.astype(int) + prev.astype(int)).astype(np.uint8)
        elif f == 3:  # Average
            for i in range(stride):
                left = int(line[i - ch]) if i >= ch else 0
                line[i] = (int(line[i]) + (left + int(prev[i])) // 2) & 0xFF
        elif f == 4:  # Paeth
            for i in range(stride):
                a = int(line[i - ch]) if i >= ch else 0
                b = int(prev[i])
                c = int(prev[i - ch]) if i >= ch else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (int(line[i]) + pr) & 0xFF
        out[y] = line
        prev = line
    img = out.reshape(h, w, ch)
    return img[:, :, :3] if ch >= 3 else np.repeat(img, 3, axis=2)


def write_png(path: Path, rgb: np.ndarray) -> None:
    h, w, _ = rgb.shape
    raw = b"".join(b"\x00" + rgb[y].tobytes() for y in range(h))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )


def metrics(img: np.ndarray) -> tuple[int, int, float]:
    g = img.astype(np.int16)
    dx = np.abs(np.diff(g, axis=1)).max(axis=2)
    dy = np.abs(np.diff(g, axis=0)).max(axis=2)
    grad = np.zeros(img.shape[:2], np.int16)
    grad[:, :-1] = np.maximum(grad[:, :-1], dx)
    grad[:-1, :] = np.maximum(grad[:-1, :], dy)
    return int((grad > 120).sum()), int(((grad > 20) & (grad <= 120)).sum()), float(np.percentile(grad, 99.9))


def main() -> int:
    ap = argparse.ArgumentParser(description="视口截图 + 画质对比（HITL 辅助）")
    ap.add_argument("--input", type=Path, help="已有截图（不自己抓）")
    ap.add_argument("--out", type=Path, help="截图输出 PNG 路径")
    ap.add_argument("--shot-cmd", default="spectacle -b -n -f", help="外部截图命令（默认 spectacle）")
    ap.add_argument("--crop", help="裁切区域 x0,y0,x1,y1（像素）")
    ap.add_argument("--compare", type=Path, help="对比图（同相机的另一张 PNG）")
    ap.add_argument("--compare-out", type=Path, help="并排结果输出 PNG")
    ap.add_argument("--scale", type=int, default=1, help="放大倍数（看细节用，默认 1）")
    args = ap.parse_args()

    src = args.input
    if src is None:
        if args.out is None:
            sys.exit("要么给 --input，要么给 --out（会自己去抓屏）")
        src = args.out.with_suffix(".full.png")
        shoot(args.shot_cmd, src)

    img = read_png(src)
    if args.crop:
        x0, y0, x1, y1 = (int(v) for v in args.crop.split(","))
        img = img[y0:y1, x0:x1]
    if args.scale > 1:
        img = np.repeat(np.repeat(img, args.scale, axis=0), args.scale, axis=1)
    if args.out is not None:
        write_png(args.out, img)
        print(f"已存：{args.out}（{img.shape[1]}x{img.shape[0]}）")

    hard, mid, p999 = metrics(img)
    print(f"指标：硬台阶 {hard}、过渡 {mid}、梯度 p99.9 {p999:.1f}")

    if args.compare is not None:
        other = read_png(args.compare)
        if args.crop:
            x0, y0, x1, y1 = (int(v) for v in args.crop.split(","))
            other = other[y0:y1, x0:x1]
        if args.scale > 1:
            other = np.repeat(np.repeat(other, args.scale, axis=0), args.scale, axis=1)
        h = min(img.shape[0], other.shape[0])
        w = min(img.shape[1], other.shape[1])
        sep = np.full((h, 8, 3), 255, np.uint8)
        both = np.concatenate([other[:h, :w], sep, img[:h, :w]], axis=1)
        dst = args.compare_out or args.out.with_name(args.out.stem + "_diff.png")
        write_png(dst, both)
        oh, om, op = metrics(other[:h, :w])
        print(f"对比（左 = {args.compare.name}，右 = 本次）：")
        print(f"  硬台阶 {oh} → {hard}（{(hard - oh) / max(1, oh) * 100:+.0f}%）")
        print(f"  过渡   {om} → {mid}")
        print(f"  p99.9  {op:.1f} → {p999:.1f}（{(p999 - op) / max(1e-9, op) * 100:+.0f}%）")
        print(f"  并排图：{dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
