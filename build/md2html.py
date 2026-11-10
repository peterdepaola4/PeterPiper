"""
Build README.html (one self-contained page) from README.md.

    python build/md2html.py [README.md] [README.html]

No extra packages: a small converter for the Markdown subset the manual uses -
headings, paragraphs, bullet and numbered lists (nested by indentation, with
code blocks inside items), pipe tables, fenced code blocks, block quotes,
`code`, **bold**, *italic*, [links](url) and bare https:// links. HTML
comments are dropped; the block between <!-- toc --> and <!-- /toc --> is
replaced by a table of contents made from the ## and ### headings. Heading
anchors follow GitHub's rule, so the same #links work on GitHub and here.

The output is deterministic (no dates), so rebuilding an unchanged README.md
gives a byte-identical README.html. Not shipped (build/ is left out of the zip).
"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

REPO = Path(__file__).resolve().parents[1]

LIST_RE = re.compile(r"^(\s*)([-*]|\d+\.)\s+(.*)$")
HEAD_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
SEP_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")
FENCE_RE = re.compile(r"^(\s*)```")


# ---------------------------------------------------------------- inline
def _plain(text: str) -> str:
    """Heading text without inline markup (for anchors and the contents)."""
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    return text.replace("**", "").replace("*", "")


def slug(text: str, seen: Dict[str, int]) -> str:
    """GitHub-style anchor: lower case, punctuation removed, spaces -> '-'."""
    s = re.sub(r"[^\w\- ]", "", _plain(text).strip().lower()).replace(" ", "-")
    n = seen.get(s, 0)
    seen[s] = n + 1
    return s if n == 0 else f"{s}-{n}"


def inline(text: str) -> str:
    """Markdown inline markup -> HTML (everything else escaped)."""
    keep: List[str] = []

    def hold(fragment: str) -> str:
        keep.append(fragment)
        return f"\x00{len(keep) - 1}\x00"

    # code spans first: their content is literal
    text = re.sub(r"(`+)(.+?)\1", lambda m: hold(f"<code>{html.escape(m.group(2).strip())}</code>"),
                  text)
    # [text](url)
    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)",
                  lambda m: hold(f'<a href="{html.escape(m.group(2), quote=True)}">'
                                 f"{inline(m.group(1))}</a>"), text)

    def bare(m: re.Match) -> str:
        url = m.group(0)
        tail = ""
        while url and url[-1] in ".,;:)":
            tail = url[-1] + tail
            url = url[:-1]
        return hold(f'<a href="{html.escape(url, quote=True)}">{html.escape(url)}</a>') + tail

    text = re.sub(r"https?://[^\s<>\"]+", bare, text)
    text = html.escape(text, quote=False)
    text = re.sub(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])\*(?=\S)(.+?)(?<=\S)\*(?![\w*])", r"<em>\1</em>", text)
    while "\x00" in text:
        text = re.sub(r"\x00(\d+)\x00", lambda m: keep[int(m.group(1))], text)
    return text


# ---------------------------------------------------------------- blocks
def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _cells(row: str) -> List[str]:
    """Split a table row on | outside `code` spans."""
    row = row.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|") and not row.endswith("\\|"):
        row = row[:-1]
    out, cur, in_code = [], "", False
    for ch in row:
        if ch == "`":
            in_code = not in_code
        if ch == "|" and not in_code:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    out.append(cur.strip())
    return out


def _starts_block(lines: List[str], i: int) -> bool:
    line = lines[i]
    if not line.strip():
        return True
    if HEAD_RE.match(line) or FENCE_RE.match(line) or LIST_RE.match(line):
        return True
    if line.lstrip().startswith(">") or line.lstrip().startswith("<!--"):
        return True
    return line.lstrip().startswith("|") and i + 1 < len(lines) and bool(SEP_RE.match(lines[i + 1]))


class Doc:
    def __init__(self) -> None:
        self.seen: Dict[str, int] = {}
        self.heads: List[Tuple[int, str, str]] = []      # (level, anchor, html text)

    def render(self, lines: List[str]) -> str:
        out: List[str] = []
        i, n = 0, len(lines)
        while i < n:
            line = lines[i]
            s = line.strip()
            if not s:
                i += 1
                continue
            if s == "<!-- toc -->":                       # replaced by the contents
                while i < n and lines[i].strip() != "<!-- /toc -->":
                    i += 1
                out.append("\x01TOC\x01")
                i += 1
                continue
            if s.startswith("<!--"):                       # other comments: dropped
                while i < n and "-->" not in lines[i]:
                    i += 1
                i += 1
                continue
            m = FENCE_RE.match(line)
            if m:
                ind = len(m.group(1))
                i += 1
                code = []
                while i < n and not lines[i].strip().startswith("```"):
                    code.append(lines[i][min(ind, _indent(lines[i])):])
                    i += 1
                i += 1
                out.append("<pre><code>" + html.escape("\n".join(code)) + "</code></pre>")
                continue
            m = HEAD_RE.match(line)
            if m:
                level, text = len(m.group(1)), m.group(2)
                anchor = slug(text, self.seen)
                body = inline(text)
                self.heads.append((level, anchor, body))
                link = "" if level == 1 else f' <a class="anchor" href="#{anchor}">#</a>'
                out.append(f'<h{level} id="{anchor}">{body}{link}</h{level}>')
                i += 1
                continue
            if s.startswith("|") and i + 1 < n and SEP_RE.match(lines[i + 1]):
                head = _cells(line)
                i += 2
                rows = []
                while i < n and lines[i].strip().startswith("|"):
                    rows.append(_cells(lines[i]))
                    i += 1
                t = ["<div class=\"table-wrap\"><table>", "<thead><tr>"]
                t += [f"<th>{inline(c)}</th>" for c in head]
                t.append("</tr></thead><tbody>")
                for r in rows:
                    r = (r + [""] * len(head))[:len(head)]
                    t.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
                t.append("</tbody></table></div>")
                out.append("".join(t))
                continue
            if s.startswith(">"):
                quote = []
                while i < n and lines[i].strip().startswith(">"):
                    q = lines[i].strip()[1:]
                    quote.append(q[1:] if q.startswith(" ") else q)
                    i += 1
                out.append("<blockquote>" + self.render(quote) + "</blockquote>")
                continue
            if LIST_RE.match(line):
                html_list, i = self._list(lines, i)
                out.append(html_list)
                continue
            para = []
            while i < n and (not para or not _starts_block(lines, i)):
                para.append(lines[i].strip())
                i += 1
            out.append("<p>" + inline(" ".join(para)) + "</p>")
        return "\n".join(out)

    def _list(self, lines: List[str], i: int) -> Tuple[str, int]:
        n = len(lines)
        first = LIST_RE.match(lines[i])
        base = len(first.group(1))
        ordered = first.group(2)[0].isdigit()
        items = []
        while i < n:
            m = LIST_RE.match(lines[i])
            if not m or len(m.group(1)) != base or m.group(2)[0].isdigit() != ordered:
                break
            content = base + len(m.group(2)) + 1
            body = [m.group(3)]
            loose = False
            i += 1
            while i < n:
                line = lines[i]
                if not line.strip():
                    j = i
                    while j < n and not lines[j].strip():
                        j += 1
                    if j < n and _indent(lines[j]) > base:
                        body += [""] * (j - i)
                        loose = True
                        i = j
                        continue
                    break
                if _indent(line) <= base:
                    break
                body.append(line[min(content, _indent(line)):])
                i += 1
            inner = self.render(body)
            if not loose and inner.startswith("<p>"):          # tight item: no <p>
                end = inner.find("</p>")
                inner = inner[3:end] + inner[end + 4:]
            items.append((m.group(2), inner))
        tag = "ol" if ordered else "ul"
        start = ""
        if ordered:
            k = int(items[0][0][:-1])
            start = f' start="{k}"' if k != 1 else ""
        return (f"<{tag}{start}>" + "".join(f"<li>{body}</li>" for _m, body in items)
                + f"</{tag}>"), i


# ---------------------------------------------------------------- page
CSS = """
:root { --bg: #ffffff; --fg: #1d2330; --muted: #5b6475; --line: #d9dee7; --soft: #f4f6fa;
        --head: #eef2f8; --accent: #24507a; --link: #1f5fa8; --code: #f1f3f7; --quote: #f6f8fb; }
@media (prefers-color-scheme: dark) {
  :root { --bg: #15181e; --fg: #e3e6ec; --muted: #9aa3b2; --line: #343a46; --soft: #1c2028;
          --head: #222834; --accent: #8fb8e6; --link: #8fc0ff; --code: #232833; --quote: #1b2029; }
}
* { box-sizing: border-box; }
html { scroll-padding-top: 12px; }
body { margin: 0; background: var(--bg); color: var(--fg);
       font: 16px/1.6 "Segoe UI", system-ui, -apple-system, Roboto, Arial, sans-serif; }
.layout { display: grid; grid-template-columns: 300px minmax(0, 1fr); max-width: 1320px;
          margin: 0 auto; }
nav.toc { position: sticky; top: 0; align-self: start; height: 100vh; overflow-y: auto;
          padding: 20px 14px 40px 20px; border-right: 1px solid var(--line);
          font-size: 13.5px; line-height: 1.45; background: var(--soft); }
nav.toc .title { font-weight: 700; color: var(--accent); margin: 0 0 10px; font-size: 15px; }
nav.toc ol { list-style: none; margin: 0; padding: 0; }
nav.toc ol ol { padding-left: 14px; margin: 2px 0 6px; }
nav.toc li { margin: 3px 0; }
nav.toc a { color: var(--fg); text-decoration: none; }
nav.toc a:hover { color: var(--link); text-decoration: underline; }
nav.toc > ol > li > a { font-weight: 600; }
main { padding: 28px 48px 80px; min-width: 0; max-width: 980px; }
h1 { font-size: 2.0em; line-height: 1.2; margin: 0.2em 0 0.4em; color: var(--accent); }
h2 { font-size: 1.5em; margin: 2.2em 0 0.6em; padding-bottom: 0.25em;
     border-bottom: 2px solid var(--line); color: var(--accent); }
h3 { font-size: 1.18em; margin: 1.8em 0 0.5em; }
h4 { font-size: 1.0em; margin: 1.4em 0 0.4em; }
h2 .anchor, h3 .anchor, h4 .anchor { visibility: hidden; text-decoration: none;
     color: var(--muted); font-weight: 400; margin-left: 6px; }
h2:hover .anchor, h3:hover .anchor, h4:hover .anchor { visibility: visible; }
p, ul, ol { margin: 0.6em 0; }
li { margin: 0.25em 0; }
li > ul, li > ol { margin: 0.25em 0; }
a { color: var(--link); }
code { font-family: Consolas, "Cascadia Mono", "Courier New", monospace; font-size: 0.9em;
       background: var(--code); padding: 0.08em 0.32em; border-radius: 4px; }
pre { background: var(--code); border: 1px solid var(--line); border-radius: 6px;
      padding: 12px 14px; overflow-x: auto; line-height: 1.4; }
pre code { background: none; padding: 0; font-size: 0.86em; }
blockquote { margin: 0.9em 0; padding: 0.4em 1em; background: var(--quote);
             border-left: 4px solid var(--accent); border-radius: 0 6px 6px 0; }
.table-wrap { overflow-x: auto; margin: 0.8em 0 1em; }
table { border-collapse: collapse; width: 100%; font-size: 0.92em; }
th, td { border: 1px solid var(--line); padding: 6px 9px; text-align: left; vertical-align: top; }
th { background: var(--head); font-weight: 600; }
tbody tr:nth-child(even) td { background: var(--soft); }
footer { margin-top: 3em; padding-top: 1em; border-top: 1px solid var(--line);
         color: var(--muted); font-size: 0.85em; }
@media (max-width: 1000px) {
  .layout { display: block; }
  nav.toc { position: static; height: auto; border-right: none;
            border-bottom: 1px solid var(--line); padding: 16px; }
  main { padding: 16px 16px 60px; }
}
@media print {
  :root { --bg: #fff; --fg: #000; --muted: #444; --line: #bbb; --soft: #fff; --head: #eee;
          --accent: #000; --link: #000; --code: #f3f3f3; --quote: #f6f6f6; }
  body { font-size: 10.5pt; }
  .layout { display: block; max-width: none; }
  nav.toc { position: static; height: auto; overflow: visible; border: none; padding: 0;
            background: none; page-break-after: always; font-size: 10pt; }
  main { padding: 0; max-width: none; }
  a { text-decoration: none; }
  h2 .anchor, h3 .anchor, h4 .anchor { display: none; }
  h1, h2, h3, h4 { break-after: avoid; page-break-after: avoid; }
  pre, blockquote, tr { break-inside: avoid; page-break-inside: avoid; }
  .table-wrap { overflow: visible; }
  pre { white-space: pre-wrap; }
  footer { display: none; }
}
"""


def toc(heads: List[Tuple[int, str, str]]) -> str:
    out = ['<nav class="toc" aria-label="Contents"><p class="title">Contents</p><ol>']
    open_sub = False
    for level, anchor, body in heads:
        if level == 2:
            if open_sub:
                out.append("</ol></li>")
                open_sub = False
            elif len(out) > 1:
                out.append("</li>")
            out.append(f'<li><a href="#{anchor}">{body}</a>')
        elif level == 3 and len(out) > 1:
            if not open_sub:
                out.append("<ol>")
                open_sub = True
            out.append(f'<li><a href="#{anchor}">{body}</a></li>')
    if open_sub:
        out.append("</ol></li>")
    elif len(out) > 1:
        out.append("</li>")
    out.append("</ol></nav>")
    return "".join(out)


def build(src: Path, dst: Path) -> None:
    text = src.read_text(encoding="utf-8")
    doc = Doc()
    body = doc.render(text.splitlines())
    nav = toc(doc.heads)
    body = body.replace("\x01TOC\x01", "")
    title = next((re.sub(r"\s+-\s+.*$", "", _plain(t)) for lv, _a, t in doc.heads if lv == 1),
                 "Manual")
    page = (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        f"<title>{html.escape(title)} manual</title>\n<style>{CSS}</style>\n</head>\n<body>\n"
        f"<div class=\"layout\">\n{nav}\n<main>\n{body}\n"
        f"<footer>This page is made from README.md by build/md2html.py - the same text.</footer>\n"
        "</main>\n</div>\n</body>\n</html>\n")
    dst.write_text(page, encoding="utf-8", newline="\n")
    print(f"{dst}: {len(page.encode('utf-8')):,} bytes, {sum(1 for h in doc.heads if h[0] == 2)} "
          f"sections, {sum(1 for h in doc.heads if h[0] == 3)} subsections")


if __name__ == "__main__":
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "README.md"
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else REPO / "README.html"
    build(src, dst)
