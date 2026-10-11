#!/usr/bin/env python3
"""检查任务目录里 Markdown 的：相对链接是否有断链、锚点是否存在、表格列数是否一致。

用法（仓库根目录）：pixi run python @20260927_motor/scripts/agent_scripts/check_md_links.py @20260927_motor

目录参数给 `.` 就是全仓：会自动跳过 `.pixi` / `ReadOnly.d` / `build` / `install` / `log` / `.git` 等
非本仓内容的目录（这样仓库根的 `README.md`、`AGENTS.md` 也能被查到——它们不在任何任务目录里，
此前只有"被别人链接进来"时才会按需解析标题）。

统计表格列数时会去掉行内代码 ``...`` 与转义的 \\|，避免把 `(status<<4) | id` 之类
当成新的一列（这是手写检查容易漏、也容易误报的地方）。

另外查两类"渲染出来跟写的不一样"的结构问题（2026-10-11 加，理由见
`@20261007_assignment/docs/status.md` 的 P2-b）：

* **引用块标题**：`> ### 标题` 也是标题，锚点扫描要认它（此前指向这种标题的链接会误报"锚点找不到"）；
* **引用块以「：」结尾、紧接着的代码围栏却没写 `>`**：引用块在这里提前结束，代码块被渲染到引用块
  外面（本仓实测踩过：`@20261005_ros2/README.md` 的历史版本）。
"""
import re
import sys
import os
from pathlib import Path


def slug(heading: str) -> str:
    s = re.sub(r"^\s*>?\s*#+\s*", "", heading.strip())   # 去掉 '> ' 与 '### ' 这类标记
    s = s.lower()
    s = re.sub(r"[^\w\u4e00-\u9fff\- ]", "", s)
    return s.replace(" ", "-").strip("-")


def headings_of(text: str) -> set[str]:
    # `> ### 标题` 也是标题：引用块里的标题渲染后同样是锚点，之前不认它会把指向它的链接误报成断锚点。
    lines = (re.sub(r"^\s*>\s?", "", line) for line in text.splitlines())
    return {slug(m.group(1)) for line in lines for m in re.finditer(r"^#{1,6}\s+(.*)$", line)}


FENCE = re.compile(r"^\s*(```|~~~)")

# 扫 `.` 时要跳过的目录：第三方环境、只读材料、构建产物、日志
SKIP_DIRS = {".pixi", "ReadOnly.d", "build", "install", "log", ".git", ".cache", "node_modules",
             "__pycache__", "site-packages"}


def unquoted_fence_after_colon(text: str) -> list[int]:
    """引用块以「：」结尾、紧随其后的代码围栏却没写 `>` → 返回那种行的行号（1 基）。

    `> 见下：` 空行后面直接写 ``` 时，Markdown 会在这里结束引用块（空行断掉引用），
    代码块就渲染到引用块外面了。规则故意只认「以冒号结尾」——它才是"下面还有内容"的承诺，
    指向别处的注记（以句号结尾）后面跟代码块是正常的，不该报。
    """
    lines = text.splitlines()
    hits: list[int] = []
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if not stripped.startswith(">") or not line.rstrip().endswith(("：", ":")):
            continue
        j = i + 1
        while j < len(lines) and (not lines[j].strip() or lines[j].lstrip().startswith(">")):
            j += 1
        if j < len(lines) and FENCE.match(lines[j]):
            hits.append(i + 1)
    return hits


def strip_cells(line: str) -> int:
    s = re.sub(r"`[^`]*`", "CODE", line)     # 行内代码里的 | 不算
    s = s.replace("\\|", "PIPE")             # 转义的 \| 不算
    return s.count("|")


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    root = Path(sys.argv[1])
    files = sorted(p for p in root.rglob("*.md") if not SKIP_DIRS.intersection(p.parts))
    heads = {p: headings_of(p.read_text(encoding="utf-8")) for p in files}

    bad: list[str] = []
    anchors: list[str] = []
    struct: list[str] = []
    probs = 0

    for p in files:
        text = p.read_text(encoding="utf-8")
        for line_no in unquoted_fence_after_colon(text):
            struct.append(f"{p}:{line_no} 引用块以「：」结尾，但后面的代码围栏没有 '>'")
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
                    # 归一化（去掉 ../ 而不是 resolve）：heads 的键是 rglob 给出的规整路径，
                    # 不归一化的话 "docs/pitfalls/../learn/x.md" 这种键永远匹配不上，会误报"锚点找不到"
                    dest = Path(os.path.normpath(p.parent / path))
                    if not dest.exists():
                        bad.append(f"{p}:{i} -> {tgt}")
                        continue
                # 锚点只对 Markdown 目标有意义：链接指向目录、图片、PDF 时带 # 是合法的，
                # 别去读它们的标题（读二进制会 UnicodeDecodeError，实测踩过）。
                if frag and dest.suffix.lower() in (".md", ".markdown"):
                    # 目标在扫描范围之外（例如任务目录里的链接指向仓库根 README.md）：按需补算它的
                    # 标题，否则锚点永远查不到——这正是 P2-b 里那两条误报的真正原因（2026-10-11 查清）。
                    if dest not in heads and dest.is_file():
                        try:
                            heads[dest] = headings_of(dest.read_text(encoding="utf-8"))
                        except (OSError, UnicodeDecodeError):
                            heads[dest] = set()
                    if frag not in heads.get(dest, set()):
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

    print(f"文件: {len(files)}  断链: {len(bad)}  锚点找不到: {len(anchors)}  表格列数异常: {probs}"
          f"  引用块/围栏: {len(struct)}")
    for x in bad:
        print("  断链 ", x)
    for x in anchors:
        print("  锚点 ", x)
    for x in struct:
        print("  结构 ", x)
    return 1 if (bad or anchors or probs or struct) else 0


if __name__ == "__main__":
    raise SystemExit(main())
