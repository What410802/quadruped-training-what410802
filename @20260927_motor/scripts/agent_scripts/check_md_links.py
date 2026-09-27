#!/usr/bin/env python3
"""检查任务目录里 Markdown 的：相对链接是否有断链、锚点是否存在、表格列数是否一致。

用法（仓库根目录）：pixi run python @20260927_motor/scripts/agent_scripts/check_md_links.py @20260927_motor

统计表格列数时会去掉行内代码 ``...`` 与转义的 \\|，避免把 `(status<<4) | id` 之类
当成新的一列（这是手写检查容易漏、也容易误报的地方）。
"""
import re
import sys
from pathlib import Path


def slug(heading: str) -> str:
    s = heading.strip().lower()
    s = re.sub(r"[^\w\u4e00-\u9fff\- ]", "", s)
    return s.replace(" ", "-")


def headings_of(text: str) -> set[str]:
    return {slug(m.group(1)) for m in re.finditer(r"^#{1,6}\s+(.*)$", text, re.M)}


def strip_cells(line: str) -> int:
    s = re.sub(r"`[^`]*`", "CODE", line)     # 行内代码里的 | 不算
    s = s.replace("\\|", "PIPE")             # 转义的 \| 不算
    return s.count("|")


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    root = Path(sys.argv[1])
    files = sorted(p for p in root.rglob("*.md") if "/build/" not in str(p))
    heads = {p: headings_of(p.read_text(encoding="utf-8")) for p in files}

    bad: list[str] = []
    anchors: list[str] = []
    probs = 0

    for p in files:
        text = p.read_text(encoding="utf-8")
        # 连续的 | 开头行算一个表；每个表单独比较列数（不同表列数本来就可以不同）
        blocks: list[list[tuple[int, int]]] = []
        block: list[tuple[int, int]] = []
        for i, line in enumerate(text.splitlines(), 1):
            for m in re.finditer(r"\]\(([^)]+)\)", line):
                tgt = m.group(1).strip()
                if tgt.startswith(("http://", "https://", "mailto:")):
                    continue
                path, _, frag = tgt.partition("#")
                dest = p
                if path:
                    dest = p.parent / path          # 不 resolve：要和 heads 的键（相对路径）对得上
                    if not dest.exists():
                        bad.append(f"{p}:{i} -> {tgt}")
                        continue
                if frag and frag not in heads.get(dest, set()):
                    anchors.append(f"{p}:{i} -> {tgt}")
            is_row = line.strip().startswith("|")
            is_sep = bool(re.match(r"^\s*\|[\s:|-]+\|\s*$", line))
            if is_row and not is_sep:
                block.append((i, strip_cells(line)))
            elif block:
                blocks.append(block)
                block = []
        if block:
            blocks.append(block)

        for rows in blocks:
            counts = {c for _, c in rows}
            if len(counts) > 1:
                main = max(counts, key=lambda c: sum(1 for _, x in rows if x == c))
                for i, c in rows:
                    if c != main:
                        probs += 1
                        print(f"  表格列数异常: {p}:{i} 竖线 {c} ≠ {main}")

    print(f"文件: {len(files)}  断链: {len(bad)}  锚点找不到: {len(anchors)}  表格列数异常: {probs}")
    for x in bad:
        print("  断链 ", x)
    for x in anchors:
        print("  锚点 ", x)
    return 1 if (bad or anchors or probs) else 0


if __name__ == "__main__":
    raise SystemExit(main())
