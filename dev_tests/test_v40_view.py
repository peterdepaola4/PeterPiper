"""
Developer test (not shipped): PeterPiper 4.0 "view" part - background first,
N x background badges, the traces panel's baseline / Undo / auto-fit, the page
header and several background jobs at once.

    PYTHONIOENCODING=utf-8 MPLBACKEND=Agg QT_QPA_PLATFORM=offscreen \
    QT_QPA_FONTDIR=C:/Windows/Fonts python dev_tests/test_v40_view.py

A) bgpropose on synthetic images: finds the empty areas, never a cell (nor a
   region marked occupied), the darker / evener area ranks first, candidates are
   spread over the image, mean / SD exact at full resolution, plain reasons,
   a user-drawn region measured the same way; < 1 s on 4 x 2400 x 2400.
B) the lab's 4-channel movie (ONE timepoint read; skipped without lab data):
   6 candidates, none on a bright object, < 1 s; screenshot of the candidates
   on the image + the picker + the page header (the Draw page's first step).
C) bgmultiple: ROI means by bounding-box crops (= full-mask means), N x
   background maths, "5.2x" / "12x", the 4-step colour scale (boundaries,
   >= 4.5:1 contrast on the badge over a black or white image, colour-blind safe).
D) badges on the image: no two overlap (also when crowded), hidden when zoomed
   far out / 'off', 'main' shows one channel, a 60-ROI update < 20 ms.
E) hover tooltip text (cell, compartment, area, every channel's mean /
   background / N x bg / sum, baseline) asked lazily from the window's callback.
F) the picker (signals, chips, own region, empty state) and the image's
   candidates ('+' click, click inside, show all / current only, chosen
   background drawn dashed and named).
G) traces panel: baseline selector beside the cell list (baseline_changed
   0-based, set_baseline silent), Undo button (undo_requested, enabled state),
   the graph always fits (quantity, mean only, hide excluded, baseline, resize)
   but keeps the user's own zoom until the graph changes; no drift controls.
H) page header: current / done / enabled pages, Back / Next / page_requested,
   Next text and hint, tips on every page; both basic themes.
I) workers: several non-exclusive jobs at once beside an exclusive one.
"""
from __future__ import annotations

import os
import shutil
import sys
import time
import traceback
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
OUT = REPO / "_out" / "v40_view"
SHOTS = REPO / "_out" / "shots"
shutil.rmtree(OUT, ignore_errors=True)
OUT.mkdir(parents=True)
SHOTS.mkdir(parents=True, exist_ok=True)
os.environ["PETERPIPER_HOME"] = str(OUT / "home")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")
sys.path.insert(0, str(REPO / "app"))
sys.path.insert(0, str(HERE))

from PySide6.QtCore import QPointF, Qt                                 # noqa: E402
from PySide6.QtGui import QImage, QPainter                             # noqa: E402
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QVBoxLayout,  # noqa: E402
                               QWidget)

APP = QApplication(sys.argv)
from peterpiper import bgmultiple as BM                                 # noqa: E402
from peterpiper import bgpropose as BP                                  # noqa: E402
from peterpiper.gui import theme as TH                                  # noqa: E402
from peterpiper.segment import Roi                                      # noqa: E402

TH.apply(APP, "midnight", 10.0)

N = [0]
FAILS = []
errors: list = []
sys.excepthook = lambda k, v, tb: errors.append("".join(traceback.format_exception(k, v, tb)))
TIMES = {}


def ok(name, cond, extra=""):
    if cond:
        N[0] += 1
    else:
        FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra else ""), flush=True)


def pump(sec=0.1):
    t = time.time()
    while time.time() - t < sec:
        APP.processEvents()
        time.sleep(0.005)


def shot(w, name):
    p = SHOTS / f"v40_view_{name}.png"
    w.grab().save(str(p))
    return p


def disk(H, W, cy, cx, r):
    yy, xx = np.ogrid[0:H, 0:W]
    return (yy - cy) ** 2 + (xx - cx) ** 2 <= r * r


def circle_roi(cy, cx, r, shape, kind="nucleus"):
    H, W = shape
    y0, x0 = max(0, cy - r), max(0, cx - r)
    y1, x1 = min(H, cy + r + 1), min(W, cx + r + 1)
    yy, xx = np.ogrid[y0:y1, x0:x1]
    m = (yy - cy) ** 2 + (xx - cx) ** 2 <= r * r
    return Roi((y0, x0, y1, x1), m, kind)


def overlaps(a, b):
    ay0, ax0, ay1, ax1 = a
    by0, bx0, by1, bx1 = b
    return not (ay1 <= by0 or by1 <= ay0 or ax1 <= bx0 or bx1 <= ax0)


# ==========================================================================
#  A) proposals on synthetic images
# ==========================================================================
def synthetic_field(H=900, W=1200, C=3, seed=4):
    """Cells everywhere except three empty areas: left (bg 200), centre-bottom
    (bg 150, the darkest) and top-right (bg 200 with bright specks: uneven)."""
    rng = np.random.default_rng(seed)
    img = np.full((C, H, W), 200.0)
    cells = np.zeros((H, W), bool)
    empty = [(80, 40, 380, 300), (560, 480, 860, 760), (60, 860, 330, 1160)]
    for cy in range(40, H, 70):
        for cx in range(40, W, 70):
            if any(y0 - 30 <= cy < y1 + 30 and x0 - 30 <= cx < x1 + 30
                   for y0, x0, y1, x1 in empty):
                continue
            m = disk(H, W, cy, cx, 22)
            cells |= m
            for c in range(C):
                img[c][m] += 900 + 300 * c
    y0, x0, y1, x1 = empty[1]
    img[:, y0:y1, x0:x1] -= 50                                    # the darkest place
    y0, x0, y1, x1 = empty[2]
    for _ in range(60):                                           # specks: uneven
        sy, sx = rng.integers(y0 + 5, y1 - 5), rng.integers(x0 + 5, x1 - 5)
        img[1, sy - 1:sy + 2, sx - 1:sx + 2] += 160
    img += rng.normal(0, 8, img.shape)
    return np.clip(np.round(img), 0, 65535).astype(np.uint16), cells, empty


def part_a():
    print("--- A) proposals on synthetic images")
    planes, cells, empty = synthetic_field()
    um = 0.5
    t0 = time.perf_counter()
    cands = BP.propose(planes, um, None, n=6, channels=["Cy5", "GFP", "DAPI"])
    TIMES["propose 3 x 900 x 1200"] = time.perf_counter() - t0
    ok("A1 candidates found", len(cands) >= 3, f"{len(cands)}")
    near_cell = ndi_dilate(cells, 4)
    ok("A2 no candidate touches a cell",
       all(not near_cell[c.roi.bbox[0]:c.roi.bbox[2], c.roi.bbox[1]:c.roi.bbox[3]].any()
           for c in cands), str([c.roi.bbox for c in cands]))
    grown = [(y0 - 30, x0 - 30, y1 + 30, x1 + 30) for y0, x0, y1, x1 in empty]  # no cells there
    clear = ndi_dilate(cells, int(BP.CLEAR_UM / um) - 1)
    ok("A3 every candidate keeps the clear zone (3 um) from every cell",
       all(not clear[c.roi.bbox[0]:c.roi.bbox[2], c.roi.bbox[1]:c.roi.bbox[3]].any()
           for c in cands))
    y0, x0, y1, x1 = empty[1]
    b = cands[0].roi.bbox
    ok("A4 BG 1 is in the darkest area", y0 <= b[0] and b[2] <= y1 and x0 <= b[1] and b[3] <= x1,
       str(b))
    ok("A5 ranked best first (score ascending, rank 1..n, labels)",
       [c.rank for c in cands] == list(range(1, len(cands) + 1))
       and all(cands[i].score <= cands[i + 1].score for i in range(len(cands) - 1))
       and cands[0].label == "BG 1")
    m, s = BP.region_stats(planes, cands[0].roi)
    y0, x0, y1, x1 = cands[0].roi.bbox
    direct = planes[:, y0:y1, x0:x1].reshape(3, -1).astype(np.float64)
    ok("A6 mean / SD exact at full resolution",
       np.allclose(cands[0].mean, direct.mean(1), rtol=0, atol=1e-9)
       and np.allclose(cands[0].sd, direct.std(1), rtol=0, atol=1e-9)
       and np.allclose(m, cands[0].mean))
    ok("A7 reasons are short plain words",
       all(isinstance(c.reason, str) and 5 < len(c.reason) < 120 for c in cands),
       cands[0].reason)
    ok("A8 the best place is 'dark and even in every channel'",
       "dark and even in every channel" in cands[0].reason, cands[0].reason)
    # the uneven area (specks) never outranks the flat ones
    yU0, xU0, yU1, xU1 = empty[2]

    def in_area(c, a):
        return a[0] <= c.roi.bbox[0] and c.roi.bbox[2] <= a[2] and a[1] <= c.roi.bbox[1] \
            and c.roi.bbox[3] <= a[3]
    ranks_uneven = [c.rank for c in cands if in_area(c, grown[2])]
    ranks_flat = [c.rank for c in cands if in_area(c, grown[0])]
    ok("A9 the speckled area ranks below the flat ones",
       ranks_flat and (not ranks_uneven or min(ranks_uneven) > min(ranks_flat)),
       f"uneven {ranks_uneven} flat {ranks_flat}")
    cents = [((c.roi.bbox[0] + c.roi.bbox[2]) / 2, (c.roi.bbox[1] + c.roi.bbox[3]) / 2)
             for c in cands]
    dmin = min(np.hypot(a[0] - b_[0], a[1] - b_[1]) for i, a in enumerate(cents)
               for b_ in cents[i + 1:]) if len(cents) > 1 else 1e9
    ok("A10 spread over the image (no two candidates closer than 1/7 of it)",
       dmin >= max(planes.shape[1:]) / 7.0, f"{dmin:.0f} px")
    ok("A11 candidates are background ROIs, sensible size",
       all(c.roi.kind == "background" and c.roi.source == "proposed"
           and 12 <= c.size_um <= 41 for c in cands), str([round(c.size_um) for c in cands]))
    occ = np.zeros(planes.shape[1:], bool)
    occ[y0 - 20:y1 + 20, x0 - 20:x1 + 20] = True          # 'BG 1' area now holds ROIs
    c2 = BP.propose(planes, um, occ, n=6)
    ok("A12 occupied pixels (drawn ROIs) are avoided",
       c2 and all(not occ[c.roi.bbox[0]:c.roi.bbox[2], c.roi.bbox[1]:c.roi.bbox[3]].any()
                  for c in c2))
    own = Roi.from_polygon([(60, 100), (250, 100), (250, 330), (60, 330)], planes.shape[1:],
                           "background")
    mc = BP.measure_region(planes, own, um, ["Cy5", "GFP", "DAPI"])
    vals = planes[:, own.bbox[0]:own.bbox[2], own.bbox[1]:own.bbox[3]][:, own.mask]
    ok("A13 a drawn region: rank 0, exact numbers, a reason",
       mc.rank == 0 and mc.label == "Your region"
       and np.allclose(mc.mean, vals.astype(float).mean(1)) and bool(mc.reason), mc.reason)
    over_cells = Roi.from_rect(380, 380, 160, 160, planes.shape[1:])
    mo = BP.measure_region(planes, over_cells, um, ["Cy5", "GFP", "DAPI"])
    ok("A14 a drawn region over cells is described as not dark / bright inside",
       "dark and even in every channel" not in mo.reason, mo.reason)
    # timing on 4 x 2400 x 2400
    rng = np.random.default_rng(1)
    big = (rng.normal(300, 10, (4, 2400, 2400))).astype(np.uint16)
    for cy in range(60, 2400, 150):
        for cx in range(60, 2400, 150):
            if (cy // 150 + cx // 150) % 5:
                big[:, cy - 30:cy + 30, cx - 30:cx + 30] += 2000
    ts = []
    for _ in range(2):
        t0 = time.perf_counter()
        cb = BP.propose(big, 0.325, None, n=6)
        ts.append(time.perf_counter() - t0)
    TIMES["propose 4 x 2400 x 2400 (first, second)"] = tuple(round(x, 3) for x in ts)
    ok("A15 < 1 s on 4 x 2400 x 2400", max(ts) < 1.0 and len(cb) == 6, f"{ts}")
    return planes, cands


def ndi_dilate(m, r):
    from scipy import ndimage as ndi
    return ndi.binary_dilation(m, iterations=r)


# ==========================================================================
#  B) the lab movie, one timepoint
# ==========================================================================
def lab_frame():
    from labdata import T, missing
    from peterpiper.nd2io import open_source
    for key in ("t51", "t52"):
        p = T(key)
        if missing(p):
            continue
        src = open_source(p)
        try:
            if src.n_channels == 4:
                t0 = time.perf_counter()
                f = src.frame(0)
                TIMES[f"read one timepoint ({key})"] = round(time.perf_counter() - t0, 2)
                return key, f, list(src.channels), float(src.um_per_px)
        finally:
            src.close()
    return None


def draw_page(planes, channels, um, cands, name, bg=None, badges=None, rois=None):
    """A mock of the Draw page: page header, image with the candidates, picker."""
    from peterpiper.gui.bgpicker import BgPicker
    from peterpiper.gui.imageview import ImageView
    from peterpiper.gui.pageflow import PageFlow
    win = QWidget()
    v = QVBoxLayout(win)
    v.setContentsMargins(0, 0, 0, 0)
    flow = PageFlow()
    flow.set_page(1)
    flow.set_done(0, True)
    flow.set_enabled(2, False)
    flow.set_enabled(3, False)
    flow.set_next("Pick a background first", False)
    flow.set_hint("Step 1: pick the background - browse the green squares, then press +.")
    v.addWidget(flow)
    row = QHBoxLayout()
    view = ImageView()
    row.addWidget(view, 3)
    side = QWidget()
    side.setFixedWidth(380)
    sl = QVBoxLayout(side)
    picker = BgPicker()
    picker.set_candidates(cands, channels, um)
    sl.addWidget(picker)
    sl.addStretch(1)
    row.addWidget(side)
    v.addLayout(row, 1)
    win.resize(1366, 740)
    win.show()
    di = channels.index("DAPI") if "DAPI" in channels else 0
    view.show_planes([planes[di]], key="x", autorange=True)
    view.set_rois(rois or [], bg, None, None, comp="nucleus")
    view.set_bg_candidates(cands, 0)
    picker.candidate_changed.connect(view.set_bg_current)
    view.bg_region_clicked.connect(picker.set_current)
    if badges:
        view.set_roi_badges(badges, "all")
    pump(0.3)
    p = shot(win, name)
    return win, view, picker, flow, p


def part_b():
    print("--- B) the lab's 4-channel movie, one timepoint")
    got = lab_frame()
    if got is None:
        print("SKIPPED (lab data only): part B")
        return None
    key, f, chans, um = got
    ts = []
    for _ in range(2):
        t0 = time.perf_counter()
        cands = BP.propose(f, um, None, n=6, channels=chans)
        ts.append(time.perf_counter() - t0)
    TIMES[f"propose on the lab movie ({key}, 4 x {f.shape[1]} x {f.shape[2]})"] = \
        tuple(round(x, 3) for x in ts)
    ok("B1 lab movie: 6 candidates in < 1 s", len(cands) == 6 and max(ts) < 1.0,
       f"{ts} {key} {chans}")
    # no candidate holds a bright object in any channel (well above its own level)
    bright_free = True
    for c in cands:
        y0, x0, y1, x1 = c.roi.bbox
        for ci in range(f.shape[0]):
            plane = f[ci]
            med = float(np.median(plane[::8, ::8]))
            box = plane[y0:y1, x0:x1].astype(float)
            from scipy import ndimage as ndi
            if ndi.uniform_filter(box, 5).max() > 2.0 * med + 50:
                bright_free = False
    ok("B2 lab movie: no candidate holds a bright object (any channel)", bright_free)
    ok("B3 lab movie: every mean below the channel's median + its noise",
       all(c.mean[ci] <= np.median(f[ci, ::8, ::8]) * 1.15 for c in cands
           for ci in range(f.shape[0])),
       str([np.round(c.mean).tolist() for c in cands[:2]]))
    for c in cands:
        print(f"    {c.label}: {c.roi.bbox} {c.size_um:.0f} um  mean "
              f"{np.round(c.mean).astype(int).tolist()}  - {c.reason}")
    win, view, picker, flow, p = draw_page(f, chans, um, cands, "lab_candidates_picker")
    ok("B4 screenshot: Draw page with candidates + picker", p.exists(), str(p))
    view.set_bg_current(2)
    picker.set_current(2)
    view.show_region(cands[2].roi, 4.0)
    pump(0.2)
    shot(win, "lab_candidate3_zoomed")
    # chosen: dashed 'Background'; badges on some lab cells (DAPI nuclei)
    from scipy import ndimage as ndi
    di = chans.index("DAPI")
    sm = ndi.uniform_filter(f[di, ::2, ::2].astype(np.float32), 3)
    lab_, n = ndi.label(sm > np.median(sm) * 3)
    objs = ndi.find_objects(lab_)
    rois = []
    for i, sl in enumerate(objs[:400]):
        if sl is None:
            continue
        m = lab_[sl] == i + 1
        if m.sum() < 60:
            continue
        m2 = np.repeat(np.repeat(m, 2, 0), 2, 1)
        y0, x0 = sl[0].start * 2, sl[1].start * 2
        rois.append(Roi((y0, x0, y0 + m2.shape[0], x0 + m2.shape[1]), m2, "nucleus"))
        if len(rois) >= 60:
            break
    bg = cands[0].roi
    means = BM.roi_means_at(f, rois)
    mult = BM.multiples(means, cands[0].mean)
    badges = {("nucleus", k): list(zip(chans, mult[k])) for k in range(len(rois))}
    win.close()
    win2, view2, picker2, _flow2, _p = draw_page(f, chans, um, cands, "lab_badges_chosen",
                                                 bg=bg, badges=badges, rois=rois)
    picker2.set_chosen("Background: BG 1")
    view2.set_bg_candidates([], 0)
    r0 = rois[0]
    view2.show_region(Roi((max(0, r0.bbox[0] - 200), max(0, r0.bbox[1] - 200),
                           r0.bbox[2] + 200, r0.bbox[3] + 200), np.ones((1, 1), bool)), 1.6)
    pump(0.3)
    shot(win2, "lab_badges_zoomed")
    ok("B5 lab badges: some shown, none overlapping",
       0 < len(view2.badge_rects()) and no_overlap(view2.badge_rects()),
       f"{len(view2.badge_rects())} shown")
    win2.close()
    return f, chans, um, cands


# ==========================================================================
#  C) the N x background numbers
# ==========================================================================
def part_c():
    print("--- C) N x background maths, words, colours")
    rng = np.random.default_rng(3)
    planes = rng.integers(100, 4000, (4, 2400, 2400)).astype(np.uint16)
    rois = [circle_roi(150 + 280 * (i // 8), 150 + 280 * (i % 8), 30, (2400, 2400))
            for i in range(60)]
    t0 = time.perf_counter()
    means, sums, areas = BM.roi_stats_at(planes, rois)
    TIMES["roi_stats_at 60 ROIs, 4 x 2400 x 2400 (ms)"] = round(
        (time.perf_counter() - t0) * 1000, 1)
    full = rois[7].full_mask((2400, 2400))
    ok("C1 bounding-box means = full-mask means",
       np.allclose(means[7], planes[:, full].astype(float).mean(1))
       and np.allclose(sums[7], planes[:, full].astype(float).sum(1))
       and areas[7] == full.sum())
    ok("C2 60 ROIs measured in < 50 ms",
       TIMES["roi_stats_at 60 ROIs, 4 x 2400 x 2400 (ms)"] < 50,
       f"{TIMES['roi_stats_at 60 ROIs, 4 x 2400 x 2400 (ms)']} ms")
    m2 = BM.roi_means_at(planes, [None, rois[0]])
    ok("C3 a missing ROI gives nan", np.isnan(m2[0]).all() and np.isfinite(m2[1]).all())
    mult = BM.multiples([1040.0, 220.0, 50.0], [200.0, 200.0, 0.0])
    ok("C4 multiples = ROI mean / background mean (nan for a 0 background)",
       np.isclose(mult[0], 5.2) and np.isclose(mult[1], 1.1) and np.isnan(mult[2]))
    mm = BM.multiples(np.array([[400.0, 300.0], [100.0, 900.0]]), [100.0, 300.0])
    ok("C5 multiples for many ROIs at once", np.allclose(mm, [[4.0, 1.0], [1.0, 3.0]]))
    cases = {5.24: "5.2x", 1.04: "1.0x", 9.94: "9.9x", 9.96: "10x", 12.4: "12x",
             12.6: "13x", 150.2: "150x", float("nan"): "-", None: "-"}
    got = {k: BM.fmt_multiple(k) for k in cases}
    ok("C6 '5.2x' below 10, whole numbers from 10", all(got[k] == v for k, v in cases.items()),
       str(got))
    lv = [BM.level_of(v) for v in (0.5, 1.49, 1.5, 2.99, 3.0, 9.99, 10.0, 99, float("nan"))]
    ok("C7 colour steps at 1.5 / 3 / 10", lv == [0, 0, 1, 1, 2, 2, 3, 3, 0], str(lv))
    from peterpiper.gui import colourvision as CV
    r, g, b_ = (int(BM.BADGE_BG[i:i + 2], 16) for i in (1, 3, 5))
    pill_on_black = CV.composite(f"rgba({r},{g},{b_},{BM.BADGE_ALPHA})", "#000000")
    pill_on_white = CV.composite(f"rgba({r},{g},{b_},{BM.BADGE_ALPHA})", "#FFFFFF")
    worst = min(CV.contrast(c, under) for c in BM.LEVEL_COLOURS
                for under in (pill_on_black, pill_on_white))
    ok("C8 every step >= 4.5:1 on the badge (image black or white behind)", worst >= 4.5,
       f"{worst:.2f}")
    dmin = CV.min_distance(list(BM.LEVEL_COLOURS))[0]
    ok("C9 the 4 steps stay distinct with colour-blindness (CIEDE2000 >= 12)",
       dmin >= 12, f"{dmin:.1f}")
    ok("C10 badge text", BM.badge_text([("GFP", 5.24), ("Cy5", 1.1)]) == "GFP 5.2x  Cy5 1.1x")
    ok("C11 'main' = the channel shown, else the strongest",
       BM.badge_pairs([("GFP", 5.2), ("Cy5", 1.1)], "main", "Cy5") == [("Cy5", 1.1)]
       and BM.badge_pairs([("GFP", 5.2), ("Cy5", 11.0)], "main", None) == [("Cy5", 11.0)]
       and BM.badge_pairs([("GFP", 5.2)], "off") == [])


# ==========================================================================
#  D) badges on the image
# ==========================================================================
def no_overlap(rects):
    rs = [r for _k, r in rects]
    return all(not rs[i].intersects(rs[j]) for i in range(len(rs)) for j in range(i + 1, len(rs)))


def covers_roi(view, rects):
    """Badges lying on an ROI that is not their own (screen boxes)."""
    o = view.vb.mapFromView(QPointF(0, 0))
    e = view.vb.mapFromView(QPointF(1, 1))
    sx, sy = e.x() - o.x(), e.y() - o.y()
    bad = []
    for key, r in rects:
        for k, roi in enumerate(view._rois):
            if ("nucleus", k) == key:
                continue
            y0, x0, y1, x1 = roi.bbox
            L, T = o.x() + x0 * sx, o.y() + y0 * sy
            R, B = o.x() + x1 * sx, o.y() + y1 * sy
            if r.left() < R and L < r.right() and r.top() < B and T < r.bottom():
                bad.append((key, k))
    return bad


def part_d():
    print("--- D) badges")
    from peterpiper.gui.imageview import ImageView
    view = ImageView()
    view.resize(1100, 820)
    view.show()
    H = W = 2400
    rng = np.random.default_rng(5)
    img = rng.normal(200, 10, (H, W)).astype(np.float32)
    rois = []
    for i in range(60):
        cy, cx = 200 + 290 * (i // 8), 200 + 280 * (i % 8)
        r = circle_roi(cy, cx, 45, (H, W))
        img[r.bbox[0]:r.bbox[2], r.bbox[1]:r.bbox[3]][r.mask] += 300 + 60 * i
        rois.append(r)
    view.show_planes([img], key="g", autorange=True)
    view.set_rois(rois, None, None, None, comp="nucleus")
    chans = ["Cy5", "mCherry", "GFP", "DAPI"]
    vals = [(1.1, 2.0, 5.24, 12.0), (0.9, 1.6, 3.3, 1.2)]

    def badges(shift=0.0):
        return {("nucleus", k): [(c, v + shift + 0.01 * k) for c, v in zip(chans, vals[k % 2])]
                for k in range(60)}
    pump(0.2)
    b = badges()
    ts = []
    for i in range(6):
        t0 = time.perf_counter()
        view.set_roi_badges(badges(0.1 * i), "all", main="GFP")
        lay = view._badges.layout()
        im = QImage(view.glw.size(), QImage.Format_ARGB32)
        im.fill(0)
        p = QPainter(im)
        view._badges.paint(p)
        p.end()
        ts.append((time.perf_counter() - t0) * 1000)
    TIMES["badges: 60-ROI update + layout + paint (ms, median of 6)"] = round(
        float(np.median(ts)), 2)
    ok("D1 60-ROI badge update + layout + paint < 20 ms", float(np.median(ts)) < 20,
       f"{np.round(ts, 1).tolist()}")
    rects = view.badge_rects()
    ok("D2 whole image: badges shown and none overlap", len(rects) > 0 and no_overlap(rects),
       f"{len(rects)} of 60")
    p1 = shot(view, "badges_whole")
    # zoom in: full text with every channel
    r0 = rois[9]
    view.show_region(Roi((r0.bbox[0] - 150, r0.bbox[1] - 150, r0.bbox[2] + 150,
                          r0.bbox[3] + 400), np.ones((1, 1), bool)), 1.0)
    pump(0.2)
    lay = view._badges.layout()
    full_txt = ["".join(s[0] + s[1] for s in segs) for _k, _r, segs in lay]
    ok("D3 zoomed in: every channel in the badge",
       any(t.count("x") >= 4 and "GFP" in t and "Cy5" in t for t in full_txt), str(full_txt[:2]))
    shot(view, "badges_zoomed")
    # 'main': one channel only
    view.set_roi_badges(b, "main", main="GFP")
    lay = view._badges.layout()
    ok("D4 'main': only the channel shown", lay and all(
        len(segs) == 1 and segs[0][0].startswith("GFP") for _k, _r, segs in lay))
    view.set_roi_badges(b, "off")
    ok("D5 'off': no badges", view.badge_rects() == [])
    # zoomed far out (4.0 integration, changed on purpose: badges ALWAYS show): the
    # compact form - the main channel's number only, e.g. '22×'
    view.set_roi_badges(b, "all", main="GFP")
    view.vb.setRange(xRange=(-20000, 22400), yRange=(-20000, 22400), padding=0)
    pump(0.1)
    lay = view._badges.layout()
    ok("D6 zoomed far out: compact badges ('22×', main channel only), never all hidden",
       lay and all(len(s) == 1 and s[0][0] == "" and s[0][1].endswith("×") for _k, _r, s in lay))
    view.fit()
    # crowded: ROIs touching each other
    crowd = [circle_roi(300 + 34 * (i // 10), 300 + 34 * (i % 10), 15, (H, W)) for i in range(60)]
    view.set_rois(crowd, None, None, None, comp="nucleus")
    view.show_region(Roi((280, 280, 520, 660), np.ones((1, 1), bool)), 1.1)
    view.set_roi_badges({("nucleus", k): [("GFP", 2.0 + k), ("Cy5", 1.0)] for k in range(60)},
                        "all", main="GFP")
    pump(0.2)
    rects = view.badge_rects()
    ok("D7 crowded: no overlaps, some badges left out", no_overlap(rects) and len(rects) < 60,
       f"{len(rects)} of 60 shown")
    ok("D7b no badge covers another ROI", not covers_roi(view, rects))
    ok("D8 crowded: the strongest win a place",
       ("nucleus", 59) in [k for k, _r in rects])
    shot(view, "badges_crowded")
    view.set_rois(rois, None, None, None, comp="nucleus")
    view.set_roi_badges(b, "all", main="GFP")
    view.fit()
    return view, rois, img


# ==========================================================================
#  E) hover tooltip
# ==========================================================================
def part_e(view, rois):
    print("--- E) hover tooltip")
    calls = []

    def info(comp, k):
        calls.append((comp, k))
        return {"cell": k + 1, "comp": "Nucleus", "area_um2": rois[k].area * 0.325 ** 2,
                "t": 12, "baseline_t": 5,
                "channels": [{"name": "GFP", "mean": 1040.0, "bg": 200.0, "sum": 1040.0 * 400,
                              "base_mean": 400.0, "base_bg": 200.0},
                             {"name": "Cy5", "mean": 220.0, "bg": 200.0, "sum": 88000.0,
                              "base_mean": 210.0, "base_bg": 200.0}]}
    view.set_roi_info(info)
    cy, cx = rois[2].centroid
    key = view.hover_key_at(cx, cy)
    ok("E1 the ROI under the mouse is found", key == ("nucleus", 2), str(key))
    txt = view.roi_tooltip(*key)
    for word in ("Cell 3", "Nucleus", "µm²", "timepoint 12", "GFP", "Cy5", "1,040.0", "200.0",
                 "5.2x", "1.1x", "416,000", "t5", "2.0x"):
        if word not in txt:
            ok(f"E2 tooltip has '{word}'", False, txt[:300])
            break
    else:
        ok("E2 tooltip: cell, compartment, area, every channel's mean / bg / N x / sum, "
           "baseline", True)
    calls.clear()
    pos = view.vb.mapViewToScene(QPointF(cx, cy))
    view._hover(pos)
    view._hover(pos)
    view._hover(view.vb.mapViewToScene(QPointF(cx + 1, cy)))
    ok("E3 the window is asked once per ROI entered (lazy)", calls == [("nucleus", 2)], str(calls))
    view._hover(view.vb.mapViewToScene(QPointF(5, 5)))
    ok("E4 leaving the ROI forgets it", view._hover_key is None)
    html_ = BM.tooltip_html({"cell": 1, "comp": "Cytoplasm", "channels": [
        {"name": "GFP", "mean": float("nan"), "bg": 100.0}]})
    ok("E5 unknown values shown as '-'", "Cytoplasm" in html_ and ">&nbsp;-&nbsp;<" in html_)
    view.set_roi_info(None)


# ==========================================================================
#  F) the picker and the image's candidates
# ==========================================================================
class FakeClick:
    def __init__(self, scene, button=Qt.LeftButton, double=False):
        self._p, self._b, self._d = scene, button, double
        self.accepted = False

    def scenePos(self):                                               # noqa: N802
        return self._p

    def button(self):
        return self._b

    def double(self):
        return self._d

    def modifiers(self):
        return Qt.NoModifier

    def accept(self):
        self.accepted = True


def part_f(planes, cands):
    print("--- F) picker + candidates on the image")
    from peterpiper.gui.bgpicker import BgPicker
    from peterpiper.gui.imageview import ImageView
    chans = ["Cy5", "GFP", "DAPI"]
    pk = BgPicker()
    pk.resize(380, 300)
    pk.show()
    sig = {"chg": [], "acc": [], "draw": 0, "all": []}
    pk.candidate_changed.connect(sig["chg"].append)
    pk.accepted.connect(sig["acc"].append)
    pk.draw_own.connect(lambda: sig.__setitem__("draw", sig["draw"] + 1))
    pk.show_all_changed.connect(sig["all"].append)
    pk.set_candidates(cands, chans, 0.5)
    pump()
    ok("F1 picker: BG 1 shown with a chip per channel",
       pk.lbl_name.text() == "BG 1" and [c.text().split()[0] for c in pk.chips[:3]] == chans
       and pk.lbl_count.text() == f"1 of {len(cands)}")
    ok("F2 chips carry the means", pk.chips[1].text().endswith(f"{cands[0].mean[1]:,.0f}"),
       pk.chips[1].text())
    pk.btn_next.click()
    pk.slider.setValue(3)
    pk.btn_prev.click()
    ok("F3 > / slider / < browse: candidate_changed", sig["chg"] == [1, 2, 1], str(sig["chg"]))
    pk.set_current(0)
    ok("F4 set_current from the window: no signal", sig["chg"] == [1, 2, 1]
       and pk.current() == 0)
    pk.btn_use.click()
    pk.btn_draw.click()
    pk.chk_all.setChecked(False)
    ok("F5 Use -> accepted(0); Draw my own; Show all",
       sig["acc"] == [0] and sig["draw"] == 1 and sig["all"] == [False])
    pump()
    shot(pk, "picker")
    own = BP.measure_region(planes, Roi.from_rect(60, 100, 150, 150, planes.shape[1:]),
                            0.5, chans)
    pk.set_own(own)
    pk.btn_use.click()
    ok("F6 the user's own region: accepted(Roi)", isinstance(sig["acc"][-1], Roi)
       and pk.lbl_name.text() == "Your region")
    pk.set_chosen("Background: your region")
    pump()
    shot(pk, "picker_own")
    pk.set_candidates([], chans, 0.5)
    ok("F7 nothing found: says so, Use disabled",
       not pk.btn_use.isEnabled() and "No empty place" in pk.lbl_name.text())
    shot(pk, "picker_empty")
    pk.close()
    # the image
    view = ImageView()
    view.resize(900, 700)
    view.show()
    view.show_planes([planes[2]], key="d", autorange=True)
    view.set_rois([], None)
    view.set_bg_candidates(cands, 0)
    pump(0.2)
    hit = {"plus": [], "reg": [], "empty": []}
    view.bg_plus_clicked.connect(hit["plus"].append)
    view.bg_region_clicked.connect(hit["reg"].append)
    view.empty_clicked.connect(lambda x, y: hit["empty"].append((x, y)))
    plus = view._bg_items[1][2]
    view._on_click(FakeClick(plus.centre_scene()))
    y0, x0, y1, x1 = cands[2].roi.bbox
    view._on_click(FakeClick(view.vb.mapViewToScene(QPointF((x0 + x1) / 2, (y0 + y1) / 2))))
    view._on_click(FakeClick(view.vb.mapViewToScene(QPointF(600, 450))))
    ok("F8 '+' -> bg_plus_clicked(1); inside BG 3 -> bg_region_clicked(2); elsewhere: as before",
       hit["plus"] == [1] and hit["reg"] == [2] and len(hit["empty"]) == 1, str(hit))
    view.set_bg_show_all(False)
    vis = [it[0].isVisible() for it in view._bg_items]
    ok("F9 show all off: only the current candidate", vis == [True] + [False] * (len(vis) - 1))
    view.set_bg_show_all(True)
    view.set_bg_current(1)
    ok("F10 the current one is emphasised",
       view._bg_items[1][0].brush().color().alpha() > view._bg_items[0][0].brush().color().alpha()
       and view._bg_items[1][2].current)
    shot(view, "candidates_synthetic")
    view.set_bg_candidates([], 0)
    view.set_rois([], cands[0].roi)
    pump()
    ok("F11 chosen background: dashed outline named 'Background'",
       view._c_bak.opts["pen"].style() == Qt.DashLine and view._bak_label.isVisible()
       and view._bak_label.textItem.toPlainText() == "Background" and not view._bg_items)
    shot(view, "background_chosen")
    view.set_rois([], None)
    ok("F12 no background: outline and name gone", not view._bak_label.isVisible())
    view.close()


# ==========================================================================
#  G) traces panel
# ==========================================================================
def synthetic_M(T=40, C=2, N=8, seed=1):
    from peterpiper.measure import Measurements
    rng = np.random.default_rng(seed)
    t = np.arange(T)
    resp = 1 + 0.8 / (1 + np.exp(-(t - 15) / 3))
    mean = np.empty((T, C, N))
    for k in range(N):
        mean[:, 0, k] = 1000 * (1 + 0.1 * k) * resp * (1 + 0.03 * rng.normal(size=T)) + 100
        mean[:, 1, k] = 800 * (1 + 0.05 * k) * (1 + 0.02 * rng.normal(size=T)) + 100
    bg = 100.0 + rng.normal(size=(T, C))
    return Measurements(mean=mean, background=bg, area_px=np.full((T, N), 50.0),
                        n_saturated=np.zeros((T, C, N)), quality=np.ones((T, N)),
                        channels=["GFP", "Cy5"])


def fits(w, tol=1e-6):
    a = w.vb.viewRange()
    was = w._user_zoom
    w.reset_zoom()
    b = w.vb.viewRange()
    w._user_zoom = was
    return np.allclose(a, b, atol=tol * max(1.0, float(np.abs(b).max())))


def part_g():
    print("--- G) traces panel")
    from PySide6.QtWidgets import QMessageBox
    for n in ("information", "warning", "critical"):
        setattr(QMessageBox, n, staticmethod(lambda *a, **k: QMessageBox.Ok))
    from peterpiper.config import Experiment
    from peterpiper.gui.traces import TracePanel
    exp = Experiment(nd2_path=str(OUT / "synthetic.nd2"), channels=["GFP", "Cy5"],
                     n_timepoints=40, seconds_per_frame=30.0, out_dir=str(OUT))
    w = TracePanel(exp)
    w.resize(560, 760)
    w.show()
    pump()
    sig = {"base": [], "undo": 0, "inc": []}
    w.baseline_changed.connect(sig["base"].append)
    w.undo_requested.connect(lambda: sig.__setitem__("undo", sig["undo"] + 1))
    live = list(range(8))
    inc = [0, 1, 2, 3, 4, 6]
    why = {k: ("included" if k in inc else "excluded by you") for k in live}
    M = synthetic_M()
    w.set_data(M, live, inc, why, "Nucleus", 4, 0, ["F/F0 - GFP"])
    pump()
    ok("G1 baseline selector shows the baseline (1-based) and the number of timepoints",
       w.sp_base.value() == 5 and w.sp_base.maximum() == 40 and "40" in w.lbl_base.text())
    # beside the cell list: the baseline row sits directly above the table
    ok("G2 the selector sits right by the include / exclude list",
       w.sp_base.parentWidget().parentWidget() is w.table.parentWidget())
    w.sp_base.setValue(10)
    pump()
    ok("G3 changing it: baseline_changed(9) (0-based), x axis 0 at timepoint 10",
       sig["base"] == [9] and w._x[9] == 0.0 and w.baseline() == 9, str(sig["base"]))
    w.set_baseline(2)
    pump()
    ok("G4 set_baseline from the window: selector follows, no signal",
       sig["base"] == [9] and w.sp_base.value() == 3 and w._x[2] == 0.0)
    ok("G5 Undo starts disabled", not w.btn_undo.isEnabled())
    w.set_undo_enabled(True)
    w.btn_undo.click()
    ok("G6 Undo -> undo_requested; enabled state settable", sig["undo"] == 1
       and w.btn_undo.isEnabled())
    ok("G7 fits after set_data", fits(w))
    # the user zooms: kept while the graph stays the same ...
    w.vb.scaleBy((0.4, 0.4))
    w.vb.sigRangeChangedManually.emit([True, True])
    zoom = w.vb.viewRange()
    w.set_time(20)
    w.set_included([0, 1, 2, 3], {k: "included" for k in live})
    pump()
    ok("G8 your zoom is kept while the graph stays (time, include / exclude)",
       w.user_zoomed() and np.allclose(w.vb.viewRange(), zoom))
    shot(w, "traces_zoomed_by_user")
    # ... and the graph fits again as soon as it changes
    i = w.cmb_what.findText("F/F0 - Cy5")
    w.cmb_what.setCurrentIndex(i)
    pump()
    ok("G9 quantity changed: fits again", not w.user_zoomed() and fits(w))
    for name, act in (("mean only", lambda: w.chk_mean.setChecked(True)),
                      ("hide excluded", lambda: w.chk_hide.setChecked(True)),
                      ("baseline", lambda: w.sp_base.setValue(15)),
                      ("compartment (set_data)", lambda: w.set_data(
                          synthetic_M(seed=3), live, inc, why, "Cytoplasm", 4, 0, [])),
                      ("include / exclude", lambda: w.set_included([0, 1], why))):
        w.vb.scaleBy((0.5, 0.5))
        w.vb.sigRangeChangedManually.emit([True, True])
        if name == "include / exclude":
            w._user_zoom = False                  # not zoomed: an include change refits
        act()
        pump(0.15)
        ok(f"G10 {name}: fits", fits(w), str(w.vb.viewRange()))
    w.chk_mean.setChecked(False)
    w.resize(700, 900)
    pump(0.3)
    ok("G11 resized: still fits", fits(w))
    w.vb.scaleBy((0.5, 0.5))
    w.vb.sigRangeChangedManually.emit([True, True])
    zoom = w.vb.viewRange()
    w.resize(640, 820)
    pump(0.3)
    ok("G12 resized while zoomed by you: your zoom kept", w.user_zoomed())
    w.reset_zoom()
    ok("G13 Reset zoom: fits, your zoom forgotten", not w.user_zoomed() and fits(w))
    ok("G14 no drift-slope controls in the traces panel",
       not [a for a in vars(w) if "drift" in a.lower()])
    ok("G15 old signals still there",
       all(hasattr(w, s) for s in ("cell_selected", "include_set", "include_all",
                                   "time_clicked", "style_changed", "export_requested")))
    from peterpiper.gui.tips import pic_path
    ok("G16 baseline hover has its picture", pic_path("view_baseline") is not None
       and "view_baseline" in w.sp_base.toolTip())
    shot(w, "traces_baseline_undo")
    w.close()


# ==========================================================================
#  H) page header
# ==========================================================================
def part_h():
    print("--- H) page header")
    from peterpiper.gui.pageflow import PageFlow
    f = PageFlow()
    f.resize(1366, 60)
    f.show()
    sig = {"page": [], "back": 0, "next": 0}
    f.page_requested.connect(sig["page"].append)
    f.back.connect(lambda: sig.__setitem__("back", sig["back"] + 1))
    f.next.connect(lambda: sig.__setitem__("next", sig["next"] + 1))
    ok("H1 four pages, starts on 2 Draw", f.pages() == ["Start", "Draw", "Track & check",
                                                        "Graphs & export"] and f.page() == 1)
    ok("H2 later pages not reachable yet", not f.crumbs[2].isEnabled()
       and not f.crumbs[3].isEnabled() and f.crumbs[0].isEnabled())
    f.set_done(0, True)
    f.set_next("Track 18 cells", True)
    f.set_hint("Draw the cells: click a nucleus, or AUTO-DETECT.")
    ok("H3 done page ticked, Next text, hint",
       f.crumb_text(0).startswith("✓") and f.btn_next.text().startswith("Track 18 cells")
       and "AUTO-DETECT" in f.hint())
    f.crumbs[2].click()
    ok("H4 a page not reachable: clicking does nothing", sig["page"] == [])
    f.set_enabled(2, True)
    f.crumbs[2].click()
    f.crumbs[1].click()                      # the current page: nothing
    f.crumbs[0].click()
    ok("H5 page_requested for reachable pages", sig["page"] == [2, 0], str(sig["page"]))
    f.btn_back.click()
    f.btn_next.click()
    ok("H6 Back / Next signals", sig["back"] == 1 and sig["next"] == 1)
    ok("H7 on page 2, Back means the start window",
       "start window" in f.btn_back.toolTip())
    f.set_next("Pick a background first", False)
    ok("H8 Next can be disabled", not f.btn_next.isEnabled())
    ok("H9 every page name has a hover explanation",
       all(len(b.toolTip()) > 60 for b in f.crumbs))
    shot(f, "pageflow_draw_midnight")
    f.set_page(2)
    f.set_done(1, True)
    f.set_next("Graphs & export", True)
    f.set_hint("Check the traces: untick cells to exclude them, set the baseline.")
    ok("H10 page 3: Back goes to page 2", "page 2" in f.btn_back.toolTip())
    shot(f, "pageflow_track_midnight")
    TH.apply(APP, "daylight", 10.0)
    pump()
    f._update()
    shot(f, "pageflow_track_daylight")
    TH.apply(APP, "midnight", 10.0)
    f.close()


# ==========================================================================
#  I) several jobs at once
# ==========================================================================
def part_i():
    print("--- I) background jobs")
    from peterpiper.gui import workers as WK

    def slow(x, progress=None):
        for i in range(5):
            time.sleep(0.04)
            progress(i / 5, "working")
        return x * 2

    results = []
    excl = WK.JobRunner(WK.FuncJob(slow, 1), on_done=results.append)
    pool = WK.JobPool()
    excl.start()
    rs = [pool.start(WK.FuncJob(slow, k), on_done=results.append, name=f"job {k}")
          for k in (10, 20, 30)]
    pump(0.05)
    ok("I1 three background jobs and one exclusive job run at once",
       pool.count() == 3 and WK.exclusive_running()
       and len(WK.running(exclusive=False)) == 3, f"{pool.count()}")
    t0 = time.time()
    while (pool.count() or excl.is_running()) and time.time() - t0 < 10:
        pump(0.05)
    pump(0.1)
    ok("I2 all finished with their results", sorted(results) == [2, 20, 40, 60], str(results))
    ok("I3 nothing left running", WK.running() == [] and not WK.exclusive_running()
       and all(r.is_finished() for r in rs))
    r2 = pool.start(WK.FuncJob(slow, 5), name="stop me")
    ok("I4 stop_all waits for every job", pool.stop_all(5.0, APP.processEvents)
       and not r2.thread.isRunning() and pool.count() == 0)


def main():
    planes, cands = part_a()
    part_b()
    part_c()
    view, rois, _img = part_d()
    part_e(view, rois)
    view.close()
    part_f(planes, cands)
    part_g()
    part_h()
    part_i()
    pump(0.2)
    ok("no uncaught errors", not errors, "\n".join(errors)[-1500:])
    print("\nTimings:")
    for k, v in TIMES.items():
        print(f"    {k}: {v}")
    print(f"\nScreenshots: {SHOTS}")
    total = N[0] + len(FAILS)
    print(f"\n{N[0]} / {total} checks passed")
    if FAILS:
        print("FAILED: " + "; ".join(FAILS))
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:                                              # noqa: BLE001
        traceback.print_exc()
        print(f"\n{N[0]} / {N[0] + len(FAILS) + 1} checks passed (the test stopped)")
        sys.exit(1)
