"""
Developer test (not shipped): PeterPiper 1.2, part "merge" - the Merge tool (two ROIs
next to each other that are really one cell become one ROI; peterpiper.roimerge and the
analysis window's ROI step).

    PYTHONIOENCODING=utf-8 MPLBACKEND=Agg QT_QPA_PLATFORM=offscreen \
        QT_QPA_FONTDIR=C:/Windows/Fonts python dev_tests/test_v12_merge.py

A built synthetic movie (made-up names only): one elongated nucleus that was outlined as
two ROIs (a 2 px gap between them), a third cell just below it, a far cell, an empty
corner for the background. Screenshots: <repo>/_out/shots/v12_merge_*.png.

A) roimerge on its own: touching ROIs and gaps of 1 - 6 px (3 um at 0.5 um/px) join into
   ONE 4-connected ROI holding both and a small bridge only between them; 7 px apart is
   refused ('far'); the limit scales with the pixel size; a third cell partly in the gap
   is never taken (the bridge goes beside it), one filling the gap blocks the merge;
   holes the join closes are filled, an ROI's own hole (cytoplasm's nucleus) stays out of
   the measured pixels but inside the outline; mitochondria keep only their pieces as
   measured pixels; ROIs at the image edge merge; merge_cells joins every compartment
   both cells have, refuses when the other compartment (two nuclei) is not next to each
   other, brings along one only the second cell has, keeps the first cell's channel, and
   never changes the cells passed in.
B) the window: a Merge button (tooltip, mode style as Split / Add to cell, in the row with
   Split; tools in two rows, 4 + 3, every label whole), no scroll bars at 1366 x 768,
   1280 x 800 and 1366 x 700 with Merge on (before and after a merge, screenshots); background compartment: no Merge; an empty spot or the same ROI
   twice: a gentle message and Merge stays on; a far pair: 'These two ROIs are not next
   to each other', nothing changes; Esc picks again, Esc again turns Merge off.
C) the merge: one connected ROI with both areas + the bridge, the first cell's number
   kept, the second cell gone, Cells: drops by one, no pixel of the third cell taken,
   tracking cleared (the next-step box says track again), roi_removed(merged=True) sent
   and no roi_added (not a hand-drawn ROI); Undo gives both back.
D) tracking again: the merged cell is followed (one piece on every timepoint, on the
   moving nucleus), the removed cell has no trace, the other cells' numbers are exactly
   those before the merge.
E) SAVE and load: the merged ROI is in the saved file (roifile.load_roi_state) and a new
   window loading it has the same ROI, cell count and tracking; the methods text names
   merging.
"""
from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
OUT = REPO / "_out" / "v12_merge"
SHOTS = REPO / "_out" / "shots"
shutil.rmtree(OUT, ignore_errors=True)
OUT.mkdir(parents=True)
SHOTS.mkdir(parents=True, exist_ok=True)
os.environ["PETERPIPER_HOME"] = str(OUT / "home")
os.environ.setdefault("MPLCONFIGDIR", str(OUT / "home" / "mpl"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")
sys.path.insert(0, str(REPO / "app"))
sys.path.insert(0, str(HERE))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                                  # noqa: BLE001
    pass

from PySide6.QtCore import Qt                                       # noqa: E402
from PySide6.QtGui import QFont                                     # noqa: E402
from PySide6.QtWidgets import (QAbstractItemView, QAbstractScrollArea,  # noqa: E402
                               QApplication, QMessageBox)
from skimage.measure import label                                   # noqa: E402

APP = QApplication(sys.argv)
BOXES = []
for _n in ("information", "warning", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: (BOXES.append(a), QMessageBox.Ok)[1]))
setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.No))
QMessageBox.exec = lambda self: (BOXES.append(self.text()), 0)[1]    # never waits

from peterpiper import events                                       # noqa: E402
from peterpiper import roifile as RF                                # noqa: E402
from peterpiper import roimerge as RM                               # noqa: E402
from peterpiper.config import Experiment, Settings                  # noqa: E402
from peterpiper.gui import theme as TH                              # noqa: E402
from peterpiper.gui import widgets as W                             # noqa: E402
from peterpiper.manual import background_from_outline               # noqa: E402
from peterpiper.nd2io import ImageSource                            # noqa: E402
from peterpiper.segment import Roi                                  # noqa: E402

N = [0]
FAILS: list = []
SHOT_FILES: list = []


def ok(name, cond, extra=""):
    N[0] += bool(cond)
    if not cond:
        FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra else ""), flush=True)


def pump(sec=0.3):
    t = time.time()
    while time.time() - t < sec:
        APP.processEvents()
        time.sleep(0.005)


def wait(w):
    pump(0.2)
    while (w._busy_now() or w.bg_busy() or w.retracking()):
        APP.processEvents()
        time.sleep(0.02)
    pump(0.3)


GOT = []
for _ev in ("roi_added", "roi_removed"):
    events.on(_ev, lambda _e=_ev, **kw: GOT.append((_e, kw)))

W.base_font_pt()
TH.apply(APP, "midnight", max(10.0, W.base_font_pt() + 1.0))

# --------------------------------------------------------------------- helpers
H, WD = 100, 120
YY, XX = np.mgrid[:H, :WD]


def roi(m, kind="nucleus", outline=None):
    shown = m if outline is None else (m | outline)
    ys, xs = np.nonzero(shown)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    r = Roi((int(y0), int(x0), int(y1), int(x1)), m[y0:y1, x0:x1].copy(), kind, True, "manual")
    if outline is not None:
        r.outline = outline[y0:y1, x0:x1].copy()
    r.channel = 0
    return r


def disc(cy, cx, rad, shape=(H, WD)):
    yy, xx = np.mgrid[:shape[0], :shape[1]]
    return (yy - cy) ** 2 + (xx - cx) ** 2 <= rad * rad


def pieces(m):
    return int(label(m, connectivity=1).max())


def full(r, shape=(H, WD)):
    return r.full_mask(shape)


def shape_of(r, shape=(H, WD)):
    o = getattr(r, "outline", None)
    return Roi(r.bbox, o if o is not None else r.mask, r.kind).full_mask(shape)


# ===================================================================== A
def part_a():
    for gap in (0, 1, 2, 4, 6):
        a = disc(50, 40, 10)
        b = disc(50, 40 + 20 + gap + 1, 10) & ~a
        r, why = RM.merge_rois(roi(a), roi(b), 0.5, (H, WD))
        if r is None:
            ok(f"A gap {gap} px: merged", False, why)
            continue
        f = full(r)
        added = f & ~(a | b)
        ys, xs = np.nonzero(added)
        between = added.any() and xs.min() >= 40 + 10 - 3 and xs.max() <= 40 + 21 + gap + 3 \
            and ys.min() >= 50 - 10 and ys.max() <= 50 + 10
        ok(f"A gap {gap} px: one 4-connected ROI with both, the bridge only between them",
           why == "" and pieces(f) == 1 and f[a].all() and f[b].all() and between
           and added.sum() < 0.1 * (a.sum() + b.sum()),
           f"added {int(added.sum())} px, cols {xs.min() if added.any() else '-'}-"
           f"{xs.max() if added.any() else '-'}")
    a = disc(50, 40, 10)
    b = disc(50, 40 + 20 + 7 + 1, 10)
    r, why = RM.merge_rois(roi(a), roi(b), 0.5, (H, WD))
    ok("A 7 px apart (more than 3 um at 0.5 um/px): refused as not next to each other",
       r is None and why == RM.FAR and RM.gap_px(roi(a), roi(b)) == 7.0)
    r, why = RM.merge_rois(roi(a), roi(b), 0.25, (H, WD))
    ok("A ... at 0.25 um/px the same 7 px are 1.75 um: merged", r is not None
       and pieces(full(r)) == 1)
    b4 = disc(50, 40 + 20 + 4 + 1, 10)
    r, why = RM.merge_rois(roi(a), roi(b4), 1.0, (H, WD))
    ok("A ... at 1 um/px 4 px are 4 um: refused", r is None and why == RM.FAR)
    # a third cell partly in the gap: never taken, the bridge goes beside it
    b = disc(50, 40 + 20 + 4 + 1, 10)
    c = disc(42, 52.5, 3.2)
    c &= ~(a | b)
    r, why = RM.merge_rois(roi(a), roi(b), 0.5, (H, WD), others=[roi(c)])
    ok("A a third cell partly in the gap: joined beside it, none of its pixels taken",
       r is not None and pieces(full(r)) == 1 and not (full(r) & c).any(), why)
    wall = (np.abs(XX - 52.5) <= 1.6) & (np.abs(YY - 50) <= 30) & ~(a | b)
    r, why = RM.merge_rois(roi(a), roi(b), 0.5, (H, WD), others=[roi(wall)])
    ok("A a third cell filling the gap: refused (blocked), nothing taken",
       r is None and why == RM.BLOCKED)
    # holes the join closes are filled: two C shapes facing each other
    ring = disc(50, 60, 16) & ~disc(50, 60, 8)
    left = ring & (XX < 59)
    right = ring & (XX > 61)
    r, why = RM.merge_rois(roi(left), roi(right), 0.5, (H, WD))
    f = full(r) if r is not None else np.zeros((H, WD), bool)
    ok("A two C shapes: the ring's middle is filled (a hole the join closed)",
       r is not None and f[50, 60] and pieces(f) == 1 and not (~f & disc(50, 60, 13)).any())
    # cytoplasm: whole-cell outlines, measured without the nucleus hole
    c1 = disc(50, 42, 14)
    c2 = disc(50, 42 + 28 + 2 + 1, 14)
    n1 = disc(50, 42, 5)
    cy1, cy2 = roi(c1 & ~n1, "cytoplasm", c1), roi(c2, "cytoplasm", c2)
    nuc = roi(n1, "nucleus")
    r, why = RM.merge_rois(cy1, cy2, 0.5, (H, WD), avoid=[nuc])
    ok("A cytoplasm: the outline is joined (one piece, gap filled), its nucleus stays out of "
       "the measured pixels and in the outline",
       r is not None and r.outline is not None and pieces(shape_of(r)) == 1
       and not (full(r) & n1).any() and shape_of(r)[n1].all()
       and full(r)[c2].all() and full(r).sum() > (c1 & ~n1).sum() + c2.sum())
    # mitochondria: outlines joined, measured = only the pieces
    o1, o2 = disc(50, 40, 10), disc(50, 61, 10)
    p1 = o1 & (XX % 4 == 0)
    p2 = o2 & (XX % 4 == 1)
    r, why = RM.merge_rois(roi(p1, "mito", o1), roi(p2, "mito", o2), 0.5, (H, WD))
    ok("A mitochondria: the region is joined, the measured pixels are only the pieces",
       r is not None and pieces(shape_of(r)) == 1 and np.array_equal(full(r), p1 | p2))
    # at the image edge
    e1 = disc(0, 30, 8) & (YY >= 0)
    e2 = disc(0, 48, 8) & ~e1
    r, why = RM.merge_rois(roi(e1), roi(e2), 0.5, (H, WD))
    ok("A ROIs at the image edge merge (inside the image)", r is not None
       and pieces(full(r)) == 1 and r.bbox[0] == 0)
    # merge_cells
    na, nb = disc(50, 40, 6), disc(50, 53, 6)
    ca, cb = disc(50, 40, 12), disc(50, 63, 12) & ~disc(50, 40, 12)
    A = {"nucleus": roi(na), "cytoplasm": roi(ca & ~na, "cytoplasm", ca)}
    B = {"nucleus": roi(nb), "cytoplasm": roi(cb & ~nb, "cytoplasm", cb)}
    A["nucleus"].channel, A["cytoplasm"].channel = 2, 1
    keep = {k: (v.bbox, v.mask.copy()) for k, v in A.items()}
    new, why, info = RM.merge_cells(A, B, "cytoplasm", 0.5, (H, WD))
    ok("A merge_cells: nucleus and cytoplasm both joined, cytoplasm leaves the joined "
       "nucleus out",
       new is not None and sorted(info["merged"]) == ["cytoplasm", "nucleus"]
       and pieces(full(new["nucleus"])) == 1
       and not (full(new["cytoplasm"]) & full(new["nucleus"])).any(), str(why))
    ok("A ... the first cell's channel is kept; the cells passed in are unchanged",
       new is not None and new["nucleus"].channel == 2 and new["cytoplasm"].channel == 1
       and all(A[k].bbox == keep[k][0] and np.array_equal(A[k].mask, keep[k][1]) for k in A))
    nfar = disc(50, 70, 4)
    B2 = {"nucleus": roi(nfar), "cytoplasm": roi(cb & ~nfar, "cytoplasm", cb)}
    new, why, info = RM.merge_cells(A, B2, "cytoplasm", 0.5, (H, WD))
    ok("A merge_cells: cytoplasms touch but the two nuclei are far apart: refused, naming "
       "the nucleus", new is None and why == (RM.FAR, "nucleus"), str(why))
    B3 = {"nucleus": roi(nb), "cytoplasm": roi(cb & ~nb, "cytoplasm", cb)}
    A3 = {"nucleus": roi(na)}
    new, why, info = RM.merge_cells(A3, B3, "nucleus", 0.5, (H, WD))
    ok("A merge_cells: a compartment only the second cell has comes along",
       new is not None and info["moved"] == ["cytoplasm"] and new["cytoplasm"] is B3["cytoplasm"]
       is not None and info["merged"] == ["nucleus"])
    new, why, info = RM.merge_cells(A3, {"cytoplasm": B3["cytoplasm"]}, "nucleus", 0.5, (H, WD))
    ok("A merge_cells: the clicked compartment missing in one cell: refused",
       new is None and why[0] == RM.EMPTY)


# ===================================================================== movie
class Movie(ImageSource):
    """One elongated nucleus (drawn as two ROIs), a cell below it, a far cell; it drifts."""
    T, HH, WW = 6, 160, 160

    def __init__(self):
        self.channels = ["Cy5", "GFP"]
        self.n_timepoints, self.height, self.width = self.T, self.HH, self.WW
        rng = np.random.default_rng(12)
        yy, xx = np.mgrid[:self.HH, :self.WW]
        self.frames = []
        for t in range(self.T):
            dy, dx = 0.4 * t, 0.3 * t
            st = np.full((2, self.HH, self.WW), 200.0)
            pean = ((yy - 50 - dy) / 9.5) ** 2 + ((xx - 50 - dx) / 19.0) ** 2 <= 1
            below = (yy - 78 - dy) ** 2 + (xx - 50 - dx) ** 2 <= 81
            far = (yy - 50 - dy) ** 2 + (xx - 120 - dx) ** 2 <= 81
            for m, v in ((pean, 1500), (below, 1800), (far, 2100)):
                st[0][m] += v
                st[1][m] += 500 if t < 3 else 900
            st += rng.normal(0, 8, st.shape)
            self.frames.append(np.clip(np.round(st), 0, 65535).astype(np.uint16))

    def frame(self, t):
        return self.frames[int(t)]

    @staticmethod
    def truth(t, which="pean"):
        yy, xx = np.mgrid[:Movie.HH, :Movie.WW]
        dy, dx = 0.4 * t, 0.3 * t
        if which == "pean":
            return ((yy - 50 - dy) / 9.5) ** 2 + ((xx - 50 - dx) / 19.0) ** 2 <= 1
        return (yy - 78 - dy) ** 2 + (xx - 50 - dx) ** 2 <= 81


SHAPE = (Movie.HH, Movie.WW)


def groi(m):
    ys, xs = np.nonzero(m)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    r = Roi((int(y0), int(x0), int(y1), int(x1)), m[y0:y1, x0:x1].copy(), "nucleus", True,
            "manual")
    r.channel = 0
    return r


def make_window(name):
    from peterpiper.gui.clickwin import ClickWindow
    ClickWindow._ask_previous_run = lambda self, runs, **k: None
    d = OUT / "data"
    d.mkdir(parents=True, exist_ok=True)
    src = Movie()
    exp = Experiment(nd2_path=str(d / f"{name}.nd2"), out_dir=str(d / f"OUTPUT_{name}"),
                     channels=list(src.channels), n_timepoints=src.T, width=src.WW,
                     height=src.HH, um_per_px=0.5, seconds_per_frame=30.0)
    exp.export_tiffs = False
    Path(exp.out_dir).mkdir(parents=True, exist_ok=True)
    if not Path(exp.nd2_path).exists():
        Path(exp.nd2_path).write_bytes((f"stands in for {name} " * 40).encode())
    w = ClickWindow(src, exp, Settings(baseline_timepoint=1))
    w._paths_ok = lambda *a, **k: True
    w.resize(1366, 768)
    w.show()
    t0 = time.time()
    while not w._offered and time.time() - t0 < 30:
        pump(0.1)
    pump(0.3)
    return w


def scroll_report(w):
    bad = []
    for sa in w.findChildren(QAbstractScrollArea):
        if not sa.isVisible() or isinstance(sa, QAbstractItemView):
            continue
        v = sa.verticalScrollBar().maximum() \
            if sa.verticalScrollBarPolicy() != Qt.ScrollBarAlwaysOff else 0
        h = sa.horizontalScrollBar().maximum() \
            if sa.horizontalScrollBarPolicy() != Qt.ScrollBarAlwaysOff else 0
        if v or h:
            bad.append(f"{sa.__class__.__name__} v{v} h{h}")
    need = w._side_scroll.widget().minimumSizeHint().height()
    room = w._side_scroll.viewport().height()
    if need > room:
        bad.append(f"side panel needs {need} px, has {room}")
    return bad


def text_fits(w, key):
    from PySide6.QtGui import QFontMetrics
    from peterpiper.gui.clickwin import TOOLS
    b = w._tool_btn[key]
    label, _col, active = TOOLS[key]
    f = QFont(b.font())
    bold = QFont(f)
    bold.setWeight(QFont.Weight.ExtraBold)
    return (QFontMetrics(f).horizontalAdvance(label) + 6 <= b.width()
            and QFontMetrics(bold).horizontalAdvance(active) + 6 <= b.width())


def check_fits(w, tag):
    for sw, sh in ((1366, 768), (1280, 800), (1366, 700)):
        w.resize(sw, sh)
        pump(0.5)
        w._show_page(1)
        pump(0.2)
        bad = scroll_report(w)
        big = w.width() > sw or w.height() > sh
        b = w._tool_btn["merge"]
        fit = all(text_fits(w, k) for k in w._tool_btn)
        ok(f"B {tag} {sw}x{sh}: no scroll bars, every tool button's text (plain and the "
           f"bold '● ...ING') fits whole",
           not bad and not big and b.isVisible() and fit,
           "; ".join(bad) + str([(x.text(), x.width()) for x in w._tool_btn.values()]))
        p = SHOTS / f"v12_merge_{tag}_{sw}x{sh}.png"
        w.grab().save(str(p))
        SHOT_FILES.append(p)
    w.resize(1366, 768)
    pump(0.3)


def status(w):
    return w.lbl_status.text().replace(chr(0x200B), "")


# ===================================================================== B - E
def part_bcde():
    from peterpiper.gui.clickwin import ClickWindow, TOOL_ROWS
    from peterpiper.provenance import methods_text
    w = make_window("pair_movie")
    pean = Movie.truth(0)
    left = pean & (XXg < 49)
    right = pean & (XXg > 50)
    below = Movie.truth(0, "below")
    far = (YYg - 50) ** 2 + (XXg - 120) ** 2 <= 81
    for m in (left, right, below, far):
        w._add_roi(groi(m), "nucleus", "drawn by hand")
    pump(0.2)
    w.background = background_from_outline([(105, 110), (155, 110), (155, 155), (105, 155)],
                                           SHAPE)
    w._bg_auto, w._bg_kind = False, "hand"
    ok("B four cells outlined (the nucleus as two ROIs, 2 px apart)", w._n_cells() == 4
       and all("nucleus" in c for c in w.cells))
    b = w._tool_btn.get("merge")
    ok("B a Merge button with a hover tip, beside Split; two rows of tools (4 + 3)",
       b is not None and b.text() == "Merge" and "one" in b.toolTip()
       and TOOL_ROWS == (("add", "remove", "draw", "resize"), ("split", "merge", "extend"))
       and b.isCheckable() and sorted(k for r in TOOL_ROWS for k in r) == sorted(w._tool_btn))
    w._set_tool("merge")
    pump(0.2)
    ok("B Merge on: the mode style of the other tools (coloured, '● MERGING', its line)",
       w.tool == "merge" and b.isChecked() and b.text() == "● MERGING"
       and "#4a63b8" in b.styleSheet() and w.lbl_tool.isVisible()
       and "MERGING" in w.lbl_tool.text() and w.view.mode == "view")
    check_fits(w, "before")
    w._set_tool("merge")
    # track first: the numbers of the other cells to compare with later
    w._track()
    wait(w)
    ok("D tracked before the merge", w.track is not None)
    M0 = w.track["meas"]["nucleus"]
    before = {k: (M0.mean[:, :, k].copy(), M0.area_px[:, k].copy()) for k in (2, 3)}
    w._set_tool("merge")
    pump(0.1)
    ok("B Merge goes to the drawn timepoint's ROI page", w._page == 1 and w.cur_t == w.t0)
    # the background compartment has no Merge
    w.cmb_comp.setCurrentIndex(w.cmb_comp.findData("background"))
    w._set_tool("merge")
    ok("B background compartment: no Merge", w.tool is None)
    w.cmb_comp.setCurrentIndex(w.cmb_comp.findData("nucleus"))
    w._set_tool("merge")
    snap = [dict(c) for c in w.cells]
    ev0 = len(GOT)
    # an empty spot
    w._on_point(20.0, 140.0, False)
    ok("B an empty spot: a gentle message, Merge stays on, nothing picked",
       "No nucleus ROI there" in status(w) and w.tool == "merge" and w._merge_k is None,
       status(w))
    w._on_point(42.0, 50.0, False)                       # the left half: cell 1
    ok("B first click picks cell 1 (selected), asks for the one next to it",
       w._merge_k == 0 and w.selected == 0 and "picked" in status(w), status(w))
    w._on_point(43.0, 51.0, False)                       # the same ROI again
    ok("B the same ROI twice: a gentle message, still picked, Merge stays on",
       "itself" in status(w) and w._merge_k == 0 and w.tool == "merge", status(w))
    w._on_point(120.0, 50.0, False)                      # the far cell
    ok("B a far pair: 'These two ROIs are not next to each other', nothing changed",
       "These two ROIs are not next to each other" in status(w) and w._n_cells() == 4
       and all(a is b for c0, c1 in zip(snap, w.cells) for a, b in zip(c0.values(),
                                                                       c1.values()))
       and w._merge_k == 0 and w.tool == "merge" and w.track is not None, status(w))
    w._on_escape()
    ok("B Esc: pick again (Merge stays on)", w._merge_k is None and w.tool == "merge")
    w._on_escape()
    ok("B Esc again: Merge off", w.tool is None and not b.isChecked() and b.text() == "Merge")
    w._set_tool("merge")
    # ------------------------------------------------------------------ C
    n_undo = len(w._undo_stack)
    w._on_point(42.0, 50.0, False)
    w._on_point(58.0, 50.0, False)
    pump(0.2)
    c0 = w.cells[0].get("nucleus")
    f = c0.full_mask(SHAPE) if c0 is not None else np.zeros(SHAPE, bool)
    added = f & ~(left | right)
    ok("C merged: one 4-connected ROI with both areas and the bridge",
       c0 is not None and pieces(f) == 1 and f[left].all() and f[right].all()
       and added.sum() >= 2 * 15, f"added {int(added.sum())} px; {status(w)}")
    ok("C ... the bridge lies in the gap between them (no spill around the outside)",
       added.any() and np.nonzero(added)[1].min() >= 44 and np.nonzero(added)[1].max() <= 55
       and (added & pean).sum() >= 0.6 * added.sum(), f"{int((added & pean).sum())} of "
                                                      f"{int(added.sum())} on the nucleus")
    ok("C it keeps the first cell's number; the second cell is gone; Cells: 3",
       w.cells[1] == {} and w._n_cells() == 3 and "Cells: 3" in w.lbl_counts.text()
       and w.selected == 0, w.lbl_counts.text())
    ok("C no pixel of the third cell (or the far cell) taken",
       not (f & below).any() and not (f & far).any()
       and np.array_equal(w.cells[2]["nucleus"].full_mask(SHAPE), snap[2]["nucleus"]
                          .full_mask(SHAPE)))
    ok("C tracking cleared: the next-step box says track again",
       w.track is None and "TRACK & MEASURE again" in w.lbl_next.text().replace(chr(0x200B), ""),
       w.lbl_next.text()[:120])
    new_ev = GOT[ev0:]
    ok("C roi_removed(merged=True, n_cells=3) sent, no roi_added (not a hand-drawn ROI)",
       [e for e, _ in new_ev] == ["roi_removed"] and new_ev[0][1].get("merged") is True
       and new_ev[0][1].get("n_cells") == 3, str(new_ev))
    ok("C one Undo step; Merge stays on, ready for the next pair",
       len(w._undo_stack) == n_undo + 1 and w.tool == "merge" and w._merge_k is None)
    ok("C the status line says what happened", "joined to cell 1" in status(w)
       and "TRACK & MEASURE" in status(w), status(w))
    check_fits(w, "after")
    merged_mask = f.copy()
    w._undo()
    pump(0.2)
    ok("C Undo gives both ROIs back (and the tracking)",
       w._n_cells() == 4 and np.array_equal(w.cells[0]["nucleus"].full_mask(SHAPE), left)
       and np.array_equal(w.cells[1]["nucleus"].full_mask(SHAPE), right)
       and w.track is not None)
    # ------------------------------------------------------------------ D
    w._set_tool("merge")
    w._on_point(42.0, 50.0, False)
    w._on_point(58.0, 50.0, False)
    ok("D merged again (the same ROI)", w._n_cells() == 3 and np.array_equal(
        w.cells[0]["nucleus"].full_mask(SHAPE), merged_mask))
    w._set_tool(None)
    w._track()
    wait(w)
    ok("D tracked again", w.track is not None)
    T = Movie.T
    follow = []
    for t in range(T):
        r = w.track["rois"]["nucleus"][t][0]
        m = r.full_mask(SHAPE) if r is not None else np.zeros(SHAPE, bool)
        tr = Movie.truth(t)
        iou = (m & tr).sum() / max(1, (m | tr).sum())
        follow.append((pieces(m), round(float(iou), 2)))
    ok("D the merged cell is followed: one piece on the moving nucleus at every timepoint",
       all(p == 1 and iou >= 0.7 for p, iou in follow), str(follow))
    M1 = w.track["meas"]["nucleus"]
    gone = w.track["rois"]["nucleus"][0][1]
    ok("D the removed cell has no ROI / trace", (gone is None or not gone.area)
       and np.all(~np.isfinite(M1.mean[:, :, 1]) | (M1.area_px[:, 1] == 0)[:, None]))
    same = all(np.array_equal(M1.mean[:, :, k], before[k][0], equal_nan=True)
               and np.array_equal(M1.area_px[:, k], before[k][1]) for k in (2, 3))
    ok("D the other cells' numbers are exactly those before the merge", same,
       str([(float(np.nanmax(np.abs(M1.mean[:, :, k] - before[k][0]))),
             int(np.abs(M1.area_px[:, k] - before[k][1]).max())) for k in (2, 3)]))
    # ------------------------------------------------------------------ E
    path = w._save_rois(silent=True)
    ok("E SAVE wrote a file", path is not None and Path(path).exists(), str(path))
    state, comps = RF.load_roi_state(path)
    saved = comps.get("nucleus") or []
    ok("E the saved file holds the merged ROI as cell 1, nothing as cell 2",
       len(saved) == 4 and np.array_equal(saved[0].full_mask(SHAPE), merged_mask)
       and not saved[1].area and state.get("cells", [None, None])[1] == {})
    w2 = make_window("pair_movie")
    ok("E a new window loads the run", w2.load_run_file(path))
    pump(0.5)
    ok("E ... with the merged ROI, 3 cells and the tracking",
       w2._n_cells() == 3 and np.array_equal(w2.cells[0]["nucleus"].full_mask(SHAPE),
                                             merged_mask)
       and "nucleus" not in w2.cells[1] and w2.track is not None
       and np.array_equal(w2.track["rois"]["nucleus"][3][0].full_mask(SHAPE),
                          w.track["rois"]["nucleus"][3][0].full_mask(SHAPE)))
    txt = methods_text(w.settings, w.exp, comps=["nucleus"])
    ok("E the methods text names merging among the edits", "split, merged, extended" in txt)
    for x in (w, w2):
        x._dirty = False
        x.close()
    pump(0.3)


YYg, XXg = np.mgrid[:Movie.HH, :Movie.WW]

if __name__ == "__main__":
    part_a()
    part_bcde()
    print("Screenshots:\n  " + "\n  ".join(str(p) for p in SHOT_FILES))
    print(f"\n{N[0]} / {N[0] + len(FAILS)} checks passed")
    if FAILS:
        print("FAILED:\n  " + "\n  ".join(FAILS))
        sys.exit(1)
