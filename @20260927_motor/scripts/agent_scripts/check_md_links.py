#!/usr/bin/env python3
"""检查任务目录里 Markdown 的：相对链接是否有断链、锚点是否存在、表格列数是否一致。

用法（仓库根目录）：pixi run python @20260927_motor/scripts/agent_scripts/check_md_links.py @20260927_motor

目录参数给 `.` 就是全仓：会自动跳过 `.pixi` / `ReadOnly.d` / `build` / `install` / `log` / `.git` 等
非本仓内容的目录（这样仓库根的 `README.md`、`AGENTS.md` 也能被查到——它们不在任何任务目录里，
此前只有"被别人链接进来"时才会按需解析标题）。

统计表格列数时会去掉行内代码 ``...`` 与转义的 \\|，避免把 `(status<<4) | id` 之类
当成新的一列（这是手写检查容易漏、也容易误报的地方）。

另外查"**按 GitHub Flavored Markdown 渲染出来跟写的不一样**"的结构问题。注意 GFM 对这些写法
基本都是**照字面渲染**而不是报错，所以本检查器的价值是"抓手误"，不是"复刻一个 CommonMark 解析器"：

* **引用块标题**：`> ### 标题` 也是标题，锚点扫描要认它（此前指向这种标题的链接会误报"锚点找不到"）；
* **引用块以「：」结尾、紧接着的代码围栏却没写 `>`**：引用块在这里提前结束，代码块被渲染到引用块外面；
* **未闭合的 `~~`**：GFM 的删除线要成对，落单的 `~~` 会原样显示（本仓踩过：勾选表格里漏了个 `~~`）；
* **未闭合的行内代码**：落单的反引号会把后面一大段吞成代码，渲染出来完全不是写的那个样子；
* **未闭合的代码围栏**：GFM 把未闭合的围栏一直吃到文件末尾，后面所有内容都变成代码块；
* **链接目标里有裸空格**：GFM 只认 `%20` 或 `<my file.md>` 这种写法，裸空格会链接失效（本文件之外的
  工具（含本检查器）用文件系统路径能解析，所以这里单独报）；
* **`#` 后面没有空格 / 超过 6 个 `#`**：GFM 不把它们当标题（没有锚点、也没有标题样式）；
* **表格缺少分隔行**（`|---|---|`，必须是第二行）：GFM 不把它当表格，整块会渲染成段落。

已知**不查**的（刻意的）：引用式链接 `[x][ref]` + `[ref]: url`、setext 标题（`标题` 下面跟 `===`）、
重复标题的 `-1` 后缀锚点、HTML 块内部。写文档时请避开这些写法。
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
SEP_RE = re.compile(r"^\s*\|[\s:|-]+\|\s*$")

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


def split_fenced(text: str) -> tuple[list[tuple[int, str]], int | None]:
    """按 GFM 规则把围栏代码块切出去，返回（未被围栏包住的行, 未闭合围栏的起始行号）。

    围栏 = 行首（≤3 空格缩进）连续 ≥3 个 ` 或 ~；闭合围栏必须是同一种字符、长度不短于开围栏、
    且后面只有空白。未闭合的围栏会一直吃到文件末尾（GFM 行为），所以那种情况返回起始行号。
    """
    keep: list[tuple[int, str]] = []
    opened: tuple[str, int, int] | None = None    # (字符, 长度, 行号)
    for i, line in enumerate(text.splitlines(), 1):
        # `> ``` ` 这种引用块里的围栏也要认（本仓 README 与 conventions 里就有，早期版本会把它
        # 当成普通行、把围栏内容当正文，于是里面的 ```` 之类被误报）
        bare = re.sub(r"^\s*(?:>\s?)+", "", line)
        m = re.match(r"^\s*(`{3,}|~{3,})(.*)$", bare)   # 缩进也认：缩进代码块里的 ``` 同样是"内容"
        if opened is None:
            if m:
                opened = (m.group(1)[0], len(m.group(1)), i)
                continue
            keep.append((i, line))
        elif m and m.group(1)[0] == opened[0] and len(m.group(1)) >= opened[1] and not m.group(2).strip():
            opened = None
    return keep, (opened[2] if opened else None)


def inline_code_issues(line: str) -> list[str]:
    """一行里未闭合的行内代码。

    GFM 的规则是"**同长度的下一个**反引号串"配对（不是相邻配对）：`` `a` `` 是对的，
    ```` `` `a` `` ```` 也是对的（外层 2 个反引号包住内层 1 个）。所以这里对每个串去找
    后面第一个等长的串；找不到才算未闭合。行内代码不跨行，逐行判即可。
    """
    runs = [(m.start(), len(m.group(0))) for m in re.finditer(r"`+", line)]
    i = 0
    while i < len(runs):
        start, length = runs[i]
        close = next((j for j in range(i + 1, len(runs)) if runs[j][1] == length), None)
        if close is None:
            return [f"第 {start + 1} 列起有未闭合的 `{'`' * length}"]
        i = close + 1
    return []


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
    tabular: list[str] = []
    probs = 0

    for p in files:
        text = p.read_text(encoding="utf-8")
        for line_no in unquoted_fence_after_colon(text):
            struct.append(f"{p}:{line_no} 引用块以「：」结尾，但后面的代码围栏没有 '>'")
        # 围栏之外的正文行：行内代码 / 删除线 / 标题写法都在这一层查（围栏里的 `~~`、`#` 是字面量，
        # 本仓 docs/learn/runtime-timing.md 的 ASCII 图就是 `~~~` 串，早期版本在这里误报过）
        body, unclosed = split_fenced(text)
        if unclosed is not None:
            struct.append(f"{p}:{unclosed} 代码围栏没有闭合（GFM 会把它吃到文件末尾）")
        for i, line in body:
            for why in inline_code_issues(line):
                struct.append(f"{p}:{i} {why}")
            plain = re.sub(r"`+[^`]*`+", "CODE", line)
            if plain.count("~~") % 2:
                struct.append(f"{p}:{i} 删除线 `~~` 没有成对闭合")
            if re.match(r"^\s{0,3}#{1,6}[^\s#]", line) or re.match(r"^\s{0,3}#{7,}", line):
                struct.append(f"{p}:{i} `#` 后缺空格或超过 6 个 `#`，GFM 不当标题")
        # 连续的 | 开头行算一个表；每个表单独比较列数（不同表列数本来就可以不同）
        # 连续的 | 开头行算一个表。分隔行也算块的一部分（早先的版本让它"中断"块，于是列数只在数据
        # 行之间比、从没跟表头比过——这里一并修好：列数以表头为准，分隔行必须在第二行）。
        blocks: list[list[tuple[int, int, bool]]] = []
        block: list[tuple[int, int, bool]] = []
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
            tgt_space = re.search(r"\]\(([^)]*\s[^)]*)\)", line)
            if tgt_space and not tgt_space.group(1).strip().startswith(("http", "mailto:")):
                struct.append(f"{p}:{i} 链接目标里有裸空格（GFM 只认 %20 或 <...>）")
            if line.strip().startswith("|"):
                # 缩进 ≥4 空格在 GFM 里是"缩进代码块"，里面的 | 是内容不是表格（ASCII 图常见）
                indented_code = len(line) - len(line.lstrip()) >= 4
                block.append((i, strip_cells(line), bool(SEP_RE.match(line)) or indented_code))
            elif block:
                blocks.append(block)
                block = []
        if block:
            blocks.append(block)

        for rows in blocks:
            # GFM：表格的第二行必须是分隔行，否则整块渲染成段落
            # 第一行本身是缩进代码块（≥4 空格）时，整块根本不是表格，不报
            if not rows[0][2] and (len(rows) < 2 or not rows[1][2]):
                struct.append(f"{p}:{rows[0][0]} 表格缺少分隔行（`|---|---|` 必须在第二行）")
            # 列数以表头为准：GFM 渲染时多出来的格子被丢掉、少的补空，写错就是"内容错位"
            cells = [(i, c) for i, c, sep in rows if not sep]
            if cells:
                head_cols = cells[0][1]
                for i, c in cells[1:]:
                    if c != head_cols:
                        probs += 1
                        tabular.append(f"{p}:{i} 竖线 {c} ≠ 表头 {head_cols}")

    print(f"文件: {len(files)}  断链: {len(bad)}  锚点找不到: {len(anchors)}  表格列数异常: {probs}"
          f"  结构（引用块/围栏/行内代码/删除线…）: {len(struct)}")
    for x in sorted(bad):
        print("  断链 ", x)
    for x in sorted(anchors):
        print("  锚点 ", x)
    for x in sorted(tabular):
        print("  表格 ", x)
    for x in struct:
        print("  结构 ", x)
    return 1 if (bad or anchors or probs or struct) else 0


if __name__ == "__main__":
    raise SystemExit(main())
