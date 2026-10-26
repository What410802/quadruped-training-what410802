#!/usr/bin/env python3
"""Optional manual GPU budget check (historical helper).

The compute machine now uses a GPU queue for training jobs, so launching through
the queue is the normal path and the old "half GPU / 8 GB per line" protocol is
retired.  This script is kept only as a manual sanity check for memory/process
counts when running something outside the queue.

Recommended per-line launch flags (exact Part2 tasks):
  BLACKW_NCONMAX=256 BLACKW_NJMAX=1024   # ~1.5 GB for a 512-env run

Usage:
  pixi run python @20261024_blackw/scripts/gpu_budget_check.py \
      --need-gb 2 --max-line-gb 8 --max-processes 2
"""
from __future__ import annotations

import argparse
import subprocess
import sys


def query_gpu() -> tuple[int, int]:
    out = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
        text=True,
    ).strip().splitlines()[0]
    used, total = (int(v) for v in out.split(","))
    return used, total


def query_training_processes() -> int:
    out = subprocess.check_output(["ps", "-eo", "args"], text=True)
    return sum(
        1 for line in out.splitlines()
        if line.strip().startswith("/") and ".venv/bin/train" in line
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--need-gb", type=float, default=2.0,
                    help="estimated memory of the new run (512-env + capped warp)")
    ap.add_argument("--max-line-gb", type=float, default=8.0,
                    help="memory budget of this training line (half GPU)")
    ap.add_argument("--max-processes", type=int, default=2,
                    help="max concurrent training processes of this line")
    ap.add_argument("--line-processes", type=int, default=0,
                    help="currently running processes of this line (override auto count)")
    args = ap.parse_args()
    used_mib, total_mib = query_gpu()
    used_gb, total_gb = used_mib / 1024.0, total_mib / 1024.0
    procs = args.line_processes or query_training_processes()
    free_gb = total_gb - used_gb
    print(f"GPU memory: used {used_gb:.2f} / {total_gb:.2f} GB, free {free_gb:.2f} GB")
    print(f"training processes on GPU: {procs} (line cap {args.max_processes})")
    ok = True
    if procs >= args.max_processes:
        print(f"REFUSE: {procs} training processes already running "
              f"(line cap {args.max_processes})")
        ok = False
    if used_gb + args.need_gb > args.max_line_gb:
        print(f"WARN: used {used_gb:.2f} + new {args.need_gb:.2f} > "
              f"line budget {args.max_line_gb:.2f} GB; consider a smaller run "
              f"or wait for a slot")
        ok = False
    if not ok:
        return 1
    print("PASS: memory/process budget available")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
