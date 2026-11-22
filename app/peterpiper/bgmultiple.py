"""
PeterPiper 4.0: "N x background" for every ROI.

Each ROI shows, per channel and at the timepoint on screen, how many times
brighter it is than the background region:

    N x background = ROI mean / background mean        (raw counts, same channel)

(the user's choice: a plain ratio of the raw means, NOT background-subtracted,
so 1.0x = "as dark as the background"). Display only - nothing measured or
exported changes.

    roi_means_at(planes, rois)          -> (n, C) means (fast: bounding-box crops)
    roi_stats_at(planes, rois)          -> means, sums, areas (for the hover)
    multiples(roi_means, bg_means)      -> ROI mean / background mean (nan when unknown)
    fmt_multiple(x)                     -> "5.2x" (< 10: one decimal), "12x" (>= 10)
    level_of(x) / colour_of(x)          -> the 4-step colour scale
    badge_text(pairs) / tooltip_html(info)

Colour scale (text on the badge's own dark pill, so it reads the same on the
dark image in every theme; checked in dev_tests/test_v40_view.py: >= 4.5:1
contrast on the pill over a black or a white image, and every pair >= 12
CIEDE2000 apart with normal vision, protanopia, deuteranopia and tritanopia):
    below 1.5x   muted grey       ("hardly above background")
    1.5 - 3x     sky blue
    3 - 10x      yellow
    10x and up   orange, bold
"""
from __future__ import annotations

import html
import math
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

LEVELS = (1.5, 3.0, 10.0)                       # the 4 steps' lower edges (after the first)
LEVEL_COLOURS = ("#A7ADB4",                     # < 1.5x   muted grey
                 "#6CC6FF",                     # 1.5-3x   sky blue (Okabe-Ito, lighter)
                 "#F2E440",                     # 3-10x    yellow (Okabe-Ito)
                 "#FF8226")                     # >= 10x   orange
LEVEL_WORDS = ("hardly above background", "above background", "clearly above background",
               "far above background")
BADGE_BG = "#12161C"                            # the badge pill (drawn at BADGE_ALPHA)
# hover text + picture for a 'N x background' switch (the window's own control)
BADGE_TIP = ("Each cell shows how many times brighter it is than the background region, "
             "per channel, at the timepoint shown: cell mean / background mean. 1.0x = no "
             "brighter than the background. Hover over a cell for the exact numbers.")
BADGE_PIC = "view_nxbg"
BADGE_ALPHA = 0.88


# --------------------------------------------------------------------------
#  measuring
# --------------------------------------------------------------------------
def roi_stats_at(planes, rois: Sequence) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(means (n, C), sums (n, C), areas (n,)) of every ROI's pixels in one
    timepoint's planes (C, H, W). A missing / empty ROI gives nan / 0. Only
    each ROI's bounding box is read, so 60 ROIs on 4 x 2400 x 2400 take a few ms."""
    planes = np.asarray(planes)
    if planes.ndim == 2:
        planes = planes[np.newaxis]
    C = planes.shape[0]
    n = len(rois)
    means = np.full((n, C), np.nan)
    sums = np.full((n, C), np.nan)
    areas = np.zeros(n, np.int64)
    H, W = planes.shape[1:]
    for i, r in enumerate(rois):
        if r is None:
            continue
        y0, x0, y1, x1 = (int(v) for v in r.bbox)
        m = np.asarray(r.mask, bool)
        cy0, cx0, cy1, cx1 = max(0, y0), max(0, x0), min(H, y1), min(W, x1)
        if cy1 <= cy0 or cx1 <= cx0:
            continue
        m = m[cy0 - y0:cy1 - y0, cx0 - x0:cx1 - x0]
        a = int(m.sum())
        if not a:
            continue
        vals = planes[:, cy0:cy1, cx0:cx1][:, m]
        s = vals.sum(axis=1, dtype=np.float64)
        sums[i] = s
        means[i] = s / a
        areas[i] = a
    return means, sums, areas


def roi_means_at(planes, rois: Sequence) -> np.ndarray:
    """(n, C) mean raw counts of every ROI (nan for a missing / empty one)."""
    return roi_stats_at(planes, rois)[0]


def multiples(roi_means, bg_means) -> np.ndarray:
    """ROI mean / background mean, per channel ([C] or [n, C] against [C]).
    nan where the background is missing or not above 0."""
    r = np.asarray(roi_means, float)
    b = np.asarray(bg_means, float)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(np.isfinite(b) & (b > 0), r / np.where(b > 0, b, 1.0), np.nan)
    return out


# --------------------------------------------------------------------------
#  words and colours
# --------------------------------------------------------------------------
def fmt_multiple(x) -> str:
    """'5.2x' below 10 (one decimal), '12x' from 10 on, '-' when unknown."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "-"
    if not math.isfinite(v):
        return "-"
    if abs(v) < 9.95:
        return f"{v:.1f}x"
    return f"{v:.0f}x"


def level_of(x) -> int:
    """0 (< 1.5x), 1 (1.5 - 3x), 2 (3 - 10x), 3 (>= 10x); 0 when unknown."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0
    if not math.isfinite(v):
        return 0
    return int(sum(v >= edge for edge in LEVELS))


def colour_of(x) -> str:
    return LEVEL_COLOURS[level_of(x)]


def strongest(pairs: Sequence[Tuple[str, float]]) -> Optional[Tuple[str, float]]:
    best = None
    for name, v in pairs:
        if v is not None and math.isfinite(float(v)) and (best is None or float(v) > best[1]):
            best = (name, float(v))
    return best


def badge_pairs(pairs: Sequence[Tuple[str, float]], show: str = "all",
                main: Optional[str] = None) -> List[Tuple[str, float]]:
    """Which (channel, multiple) pairs a badge shows: 'all' = every channel;
    'main' = the channel shown in the image (main), else the strongest; 'off' = none."""
    pairs = [(str(n), float(v) if v is not None else float("nan")) for n, v in pairs]
    if show == "off" or not pairs:
        return []
    if show == "main":
        hit = [p for p in pairs if main is not None and p[0] == main]
        if hit:
            return hit[:1]
        s = strongest(pairs)
        return [s] if s else pairs[:1]
    return pairs


def badge_text(pairs: Sequence[Tuple[str, float]]) -> str:
    """'GFP 5.2x  Cy5 1.1x'."""
    return "  ".join(f"{n} {fmt_multiple(v)}" for n, v in pairs)


def _num(v, nd=0) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "-"
    if not math.isfinite(f):
        return "-"
    if abs(f) >= 1e6:
        return f"{f:.3g}"
    return f"{f:,.{nd}f}"


def tooltip_html(info: dict) -> str:
    """The hover text of one ROI. info (supplied lazily by the window):
        cell (1-based), comp (label), area_um2, t (1-based timepoint),
        baseline_t (1-based or None), channels: [ {name, mean, bg, sum,
        base_mean, base_bg} ... ] (base_* optional).
    N x background is computed here from mean / bg (and base_mean / base_bg)."""
    cell = info.get("cell")
    comp = info.get("comp") or ""
    head = f"<b>Cell {cell}</b>" + (f" &nbsp;·&nbsp; {html.escape(str(comp))}" if comp else "")
    area = info.get("area_um2")
    t = info.get("t")
    sub = []
    if area is not None and math.isfinite(float(area)):
        sub.append(f"area {float(area):.1f} µm²")
    if t is not None:
        sub.append(f"timepoint {t}")
    base_t = info.get("baseline_t")
    chans = list(info.get("channels") or [])
    has_base = base_t is not None and any("base_mean" in c for c in chans)
    rows = []
    hdr = ("<tr><th align='left'>Channel</th><th align='right'>&nbsp;Mean</th>"
           "<th align='right'>&nbsp;Background</th><th align='right'>&nbsp;N x bg</th>"
           "<th align='right'>&nbsp;Sum</th>"
           + (f"<th align='right'>&nbsp;N x bg at t{base_t}</th>" if has_base else "")
           + "</tr>")
    for c in chans:
        m = multiples(c.get("mean", np.nan), c.get("bg", np.nan))
        mv = float(m) if np.ndim(m) == 0 else float("nan")
        col = colour_of(mv)
        cells = [f"<td>{html.escape(str(c.get('name', '')))}</td>",
                 f"<td align='right'>&nbsp;{_num(c.get('mean'), 1)}</td>",
                 f"<td align='right'>&nbsp;{_num(c.get('bg'), 1)}</td>",
                 f"<td align='right'>&nbsp;<b><span style='background:{BADGE_BG};"
                 f"color:{col}'>&nbsp;{fmt_multiple(mv)}&nbsp;</span></b></td>",
                 f"<td align='right'>&nbsp;{_num(c.get('sum'))}</td>"]
        if has_base:
            bm = multiples(c.get("base_mean", np.nan), c.get("base_bg", np.nan))
            cells.append(f"<td align='right'>&nbsp;{fmt_multiple(bm)}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    note = ("<br><span style='font-size:small'>N x bg = ROI mean / background mean "
            "(raw counts) at this timepoint. Sum = all the ROI's pixel counts added.</span>")
    return (f"<div>{head}<br>{' · '.join(sub)}"
            f"<table cellspacing='0' cellpadding='1'>{hdr}{''.join(rows)}</table>{note}</div>")


def legend_items() -> List[Tuple[str, str]]:
    """[(colour, words)] for a small key: '< 1.5x hardly above background' ..."""
    edges = ("< 1.5x", "1.5 - 3x", "3 - 10x", "10x +")
    return [(LEVEL_COLOURS[i], f"{edges[i]}  {LEVEL_WORDS[i]}") for i in range(4)]
