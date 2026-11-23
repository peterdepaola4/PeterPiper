"""
Developer test (not shipped): PeterPiper 4.0 - the analysis window's 4-page flow
(gui/clickwin.ClickWindow, integration of the view / server / trackx / graphs parts).
Synthetic movie only (dev_tests/synthmovie.py); made-up file names.

Checks
  A  pages: the window opens on 2 Draw; 1 Start is done; Back on Draw asks for the
     start window (go_back); Track & check / Graphs & export cannot be reached before
     there is something to track / a tracking; Next says 'Track 16 cells'; the old
     _goto_step(k) still shows the matching new page
  B  background first: background places are proposed (on the image and in the
     picker, in ~0.1 s, never in the window's thread); the cell tools are folded and
     locked until a background is chosen; '+' on the image takes one (kind
     'proposed'), the picker folds to one line, the proposals leave the image;
     Change opens it again; Undo takes the choice back (the picker returns)
  C  N x background: one badge per ROI; the badges follow the timepoint (GFP of a
     sensor cell rises); the hover numbers (mean, background, sum, baseline); 'off'
     hides them; the graph's channel becomes the 'main' channel
  D  Undo: ROI added, include / exclude, the compartment chosen, the background;
     the Undo beside the cell list follows; Ctrl+Z
  E  Next runs TRACK & MEASURE and shows Track & check with the traces; the baseline
     chosen beside the cell list is the window's baseline; page 4 shows the graph
     builder (one run plotted); the drift add-on window reaches it
  F  re-track by itself: removing one cell after tracking updates the tracking
     without TRACK & MEASURE (only that change), the result equals a full tracking
  G  background tasks: EXPORT runs in the task center (the window's own job stays
     free); Next movie in a 2-movie queue opens the next movie while the export is
     still running; the export finishes afterwards with its files
  H  the File menu has no 'Back up this analysis...'; the status bar has the task
     button
  I  no scroll bars at 1366 x 768 on any page (dark and light theme), screenshots
"""
from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
OUT = REPO / "_out" / "v40_flow"
SHOTS = REPO / "_out" / "shots"
shutil.rmtree(OUT, ignore_errors=True)
OUT.mkdir(parents=True)
SHOTS.mkdir(parents=True, exist_ok=True)
os.environ["PETERPIPER_HOME"] = str(OUT / "home")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")
sys.path.insert(0, str(REPO / "app"))
sys.path.insert(0, str(HERE))

from PySide6.QtWidgets import QApplication, QMessageBox, QScrollBar   # noqa: E402

APP = QApplication.instance() or QApplication([])

import numpy as np                                                     # noqa: E402
import synthmovie as SM                                                # noqa: E402
from peterpiper import batchqueue                                      # noqa: E402
from peterpiper import tasks as TK                                     # noqa: E402
from peterpiper.config import Settings                                 # noqa: E402
from peterpiper.gui import theme as TH                                 # noqa: E402
from peterpiper.gui import widgets as W                                # noqa: E402

RESULTS = []


def ok(name, cond, extra=""):
    RESULTS.append((name, bool(cond)))
    print(f"{'PASS' if cond else 'FAIL'} {name}" + (f"  [{extra}]" if extra != "" else ""),
          flush=True)


def pump(sec=0.2):
    t = time.time()
    while time.time() - t < sec:
        APP.processEvents()
        time.sleep(0.005)


def wait(w, limit=120):
    t = time.time()
    pump(0.2)
    while (w._busy_now() or w.bg_busy() or w.retracking() or w._retrack_timer.isActive()) \
            and time.time() - t < limit:
        pump(0.05)
    pump(0.3)


BOXES = []
QMessageBox.exec = lambda self: (BOXES.append(self.text()), 0)[1]
for _n in ("information", "warning", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: (BOXES.append(str(a[2:3])), QMessageBox.Ok)[1]))
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)
W.base_font_pt()
TH.apply(APP, "midnight", max(10.0, W.base_font_pt() + 1.0))


def movie(name):
    d = OUT / "data"
    d.mkdir(parents=True, exist_ok=True)
    src, exp = SM.load(d / f"OUTPUT_{name}" / "results")
    exp.nd2_path = str(d / f"{name}.nd2")
    Path(exp.out_dir).mkdir(parents=True, exist_ok=True)
    if not Path(exp.nd2_path).exists():
        Path(exp.nd2_path).write_bytes((f"stands in for {name} " * 40).encode())
    return src, exp


def make_window(name="flow_a", size=(1366, 728)):
    from peterpiper.gui.clickwin import ClickWindow
    ClickWindow._ask_previous_run = lambda self, runs, **k: None
    src, exp = movie(name)
    w = ClickWindow(src, exp, Settings(baseline_timepoint=1))
    w._paths_ok = lambda *a, **k: True
    w.resize(*size)
    w.show()
    t0 = time.time()
    while (not w._offered or not w._bg_cands) and time.time() - t0 < 30:
        pump(0.1)
    pump(0.3)
    return w


def scroll_bars(w) -> list:
    """Scroll bars shown anywhere in the side panel / window (the trace table and the
    graph builder's own lists may scroll)."""
    out = []
    for sb in w.findChildren(QScrollBar):
        if not sb.isVisible():
            continue
        p, inside = sb.parent(), False
        while p is not None:
            if p is getattr(w, "_dock", None):
                inside = True
                break
            p = p.parent()
        if not inside:
            out.append(sb)
    return out


def part_a_b_c_d_e(w):
    from peterpiper.gui.clickwin import P_DRAW, P_GRAPHS, P_TRACK
    f = w.flow
    ok("A opens on 2 Draw, 1 Start done", w._page == P_DRAW and f.page() == P_DRAW
       and f.is_done(0))
    ok("A Track & check / Graphs & export not reachable yet",
       not f.is_enabled(P_TRACK) and not f.is_enabled(P_GRAPHS))
    ok("A Next is 'Track cells' and off (no background, no cells)",
       "Track" in f.btn_next.text() and not f.btn_next.isEnabled(), f.btn_next.text())
    ok("A the hint says: pick the background first", "background first" in f.hint(), f.hint())
    # ---- B background first
    ok("B background places proposed (picker + image)",
       len(w._bg_cands) >= 1 and len(w.view.bg_candidates()) == len(w._bg_cands)
       and w.picker.isVisible(), len(w._bg_cands))
    ok("B proposing took < 1 s (in a job)", getattr(w, "_bg_ms", 9e9) < 1000,
       f"{getattr(w, '_bg_ms', 0):.0f} ms")
    ok("B the cell tools are folded and locked until a background",
       not w.cells_box.isEnabled() and bool(w.cells_box.property("folded")))
    w.picker.slider.setValue(2 if len(w._bg_cands) > 1 else 1)
    pump(0.1)
    ok("B browsing emphasises that place on the image",
       w.view.bg_current() == w.picker.current())
    w.view.bg_plus_clicked.emit(0)
    pump(0.3)
    ok("B '+' takes it: kind 'proposed', proposals gone, picker folded to one line",
       w.background is not None and w._bg_kind == "proposed" and not w.view.bg_candidates()
       and not w.picker.isVisible() and w.bg_line.isVisible() and "BG 1" in w.lbl_bg.text(),
       w.lbl_bg.text())
    ok("B the cell tools open", w.cells_box.isEnabled() and not w.cells_box.property("folded"))
    w.btn_bg_change.click()
    pump(0.5)
    ok("B Change opens the picker again (proposals on the image)",
       w.picker.isVisible() and len(w.view.bg_candidates()) >= 1)
    w.btn_bg_change.click()
    pump(0.2)
    ok("B 'Keep it' closes it", not w.picker.isVisible() and not w.view.bg_candidates())
    w._undo()
    pump(0.5)
    ok("B Undo takes the background back: the picker returns",
       w.background is None and w.picker.isVisible() and not w.cells_box.isEnabled())
    w._accept_background(0)
    pump(0.2)
    # ---- D undo across actions (first an ROI)
    n_undo = len(w._undo_stack)
    w._auto_select()
    wait(w)
    n = w._n_cells()
    ok("D auto-detect: 16 cells; Undo and the list's Undo are on",
       n == 16 and w.btn_undo.isEnabled() and w.traces.btn_undo.isEnabled(), n)
    ok("A Next is 'Track 16 cells' and on", f.btn_next.text().startswith("Track 16 cells")
       and f.btn_next.isEnabled(), f.btn_next.text())
    # ---- C badges
    rects = w.view.badge_rects()
    ok("C one N x background badge per ROI", len(w.view._badges.entries) == 16, len(rects))
    w.slider.setValue(1)
    pump(0.3)
    e1 = {k: dict(p) for k, _b, p, _m, _s in w.view._badges.entries}
    w.slider.setValue(10)
    while w.store.get(9) is None:
        pump(0.05)
    pump(0.3)
    e2 = {k: dict(p) for k, _b, p, _m, _s in w.view._badges.entries}
    # the sensor cells' GFP doubles after t4 (the others stay at 1.0x)
    k0 = max(e2, key=lambda k: e2[k]["GFP"] / max(1e-9, e1.get(k, {}).get("GFP", 1e9)))
    ok("C the badges follow the timepoint (a sensor cell's GFP x bg rises after t4)",
       k0 in e1 and e2[k0]["GFP"] > e1[k0]["GFP"] * 1.3
       and sum(1 for k in e2 if e2[k]["GFP"] > 1.3 * e1.get(k, {}).get("GFP", 9e9)) == 8,
       f"{e1.get(k0, {}).get('GFP', 0):.2f} -> {e2.get(k0, {}).get('GFP', 0):.2f}")
    info = w._roi_info("nucleus", 0)
    html = w.view.roi_tooltip("nucleus", 0)
    ok("C hover: exact mean, background and sum per channel",
       info and len(info["channels"]) == 3 and all(c["bg"] > 0 and c["sum"] > c["mean"]
                                                   for c in info["channels"])
       and "Cell 1" in html and "Background" in html)
    w.cmb_badges.setCurrentIndex(w.cmb_badges.findData("off"))
    pump(0.1)
    ok("C 'off' hides the badges", not w.view._badges.entries)
    w.cmb_badges.setCurrentIndex(w.cmb_badges.findData("all"))
    pump(0.2)
    w.view.vb.scaleBy((12, 12))                    # zoomed far out
    pump(0.3)
    lay_ = w.view._badges.layout()
    ok("C zoomed far out the badges still show, compact ('22×': number only)",
       len(lay_) >= 4 and all(s[0][0] == "" and s[0][1].endswith("×") for _k, _r, s in lay_),
       f"{len(lay_)} shown, e.g. {lay_[0][2][0][1] if lay_ else ''}")
    w.view.fit()
    pump(0.2)
    w.cmb_badges.setCurrentIndex(w.cmb_badges.findData("numbers"))
    pump(0.2)
    lay_ = w.view._badges.layout()
    ok("C 'numbers only': the compact badge at any zoom",
       lay_ and all(s[0][0] == "" for _k, _r, s in lay_))
    w.act_tint.setChecked(True)
    pump(0.2)
    tinted = sum(1 for c in getattr(w.view, "_tint_curves", []) if c.isVisible())
    ok("C 'Colour outlines by level': halos in the level colours", tinted >= 1, tinted)
    w.act_tint.setChecked(False)
    pump(0.1)
    ok("C ... and off again", not any(c.isVisible() for c in w.view._tint_curves))
    # cost with 100 ROIs: badges + tint + layout + paint
    from peterpiper.segment import Roi
    base = [r for r in w._rois("nucleus") if r is not None]
    many, pairs = {}, {}
    for j in range(100):
        r0 = base[j % len(base)]
        dy, dx = 3 * (j // len(base)), 2 * (j // len(base))
        y0, x0, y1, x1 = r0.bbox
        r = Roi((y0 + dy, x0 + dx, y1 + dy, x1 + dx), r0.mask.copy(), "nucleus")
        many[("nucleus", j)] = r
        pairs[("nucleus", j)] = [("Cy5", 5.0 + j % 7), ("GFP", 1.2 + j % 3), ("mCherry", 2.0)]
    from PySide6.QtGui import QImage, QPainter
    img = QImage(800, 600, QImage.Format_ARGB32)
    ts = []
    for _ in range(5):
        t = time.perf_counter()
        w.view.set_roi_badges(pairs, "all", rois=many, main="Cy5", tint=True)
        p_ = QPainter(img)
        w.view._badges.paint(p_)
        p_.end()
        ts.append((time.perf_counter() - t) * 1000)
    ok("C 100 ROIs: badges + tint + layout + paint < 20 ms", sorted(ts)[2] < 20,
       f"{sorted(ts)[2]:.1f} ms (median of 5)")
    w.cmb_badges.setCurrentIndex(w.cmb_badges.findData("all"))
    w.cmb_badges.setCurrentIndex(w.cmb_badges.findData("all"))
    w.slider.setValue(1)
    pump(0.3)
    # ---- D undo: include / exclude, compartment chosen
    n0 = len(w._undo_stack)
    w._set_include("nucleus", 2, False)
    ok("D exclude cell 3 -> one undo step", len(w._undo_stack) == n0 + 1 and 2 in w.excl["nucleus"])
    w.traces.undo_requested.emit()
    pump(0.1)
    ok("D the Undo beside the cell list takes it back", 2 not in w.excl["nucleus"])
    w._add_row("cytoplasm", 0)
    pump(0.2)
    i = w.cmb_comp.findData("cytoplasm")
    w.cmb_comp.setCurrentIndex(i)
    w.cmb_comp.activated.emit(i)
    pump(0.1)
    ok("D choosing a compartment is an undo step", w.comp == "cytoplasm")
    acts = [a for a in w._view_menu.actions() if a.text() == "Undo"]  # Ctrl+Z
    ok("D Undo has the Ctrl+Z shortcut", acts and acts[0].shortcut().toString() in
       ("Ctrl+Z", "Meta+Z"), acts[0].shortcut().toString() if acts else "")
    acts[0].trigger()
    pump(0.2)
    ok("D Ctrl+Z (Undo) takes the compartment choice back", w.comp == "nucleus", w.comp)
    rm = [r for r in w._rows if r["cmb"].currentData() == "cytoplasm"]
    if rm:
        w._remove_row(rm[0])
    pump(0.2)
    ok("D ... the cells stay", w._n_cells() == 16)
    # ---- E Next = track
    t = time.perf_counter()
    f.next.emit()
    wait(w)
    ok("E Next tracks and shows Track & check with the traces",
       w.track is not None and w._page == P_TRACK and w._dock.isVisible()
       and w._dock_stack.currentWidget() is w.traces,
       f"{time.perf_counter() - t:.1f} s")
    ok("E Graphs & export reachable; Next 'Graphs & export'",
       f.is_enabled(P_GRAPHS) and "Graphs" in f.btn_next.text())
    w.traces.sp_base.setValue(3)
    pump(0.2)
    ok("E the baseline beside the cell list is the window's baseline (q_base 3)",
       w.q_base.value() == 3 and w.settings.baseline_timepoint == 3)
    w.traces.sp_base.setValue(1)
    pump(0.1)
    f.next.emit()
    pump(0.8)
    g = w.graphs
    ok("E page 4: the graph builder in the right panel with this run",
       w._page == P_GRAPHS and g is not None and w._dock_stack.currentWidget() is g
       and len(g.runs()) == 1 and g.result() is not None and not g.result().error,
       getattr(g.result(), "error", ""))
    w.sp_dfrom.setValue(3)
    w.sp_dto.setValue(8)
    ok("E the drift add-on window reaches the graph builder",
       g._drift_window == (3, 8) and (w.settings.drift_from, w.settings.drift_to) == (3, 8))
    for name in ("v40_flow_draw.png", "v40_flow_track.png", "v40_flow_graphs.png"):
        pass
    return w


def part_f(w):
    from peterpiper import retrack as RT
    from peterpiper.gui.clickwin import P_TRACK
    w._show_page(P_TRACK)
    pump(0.2)
    full = w.track
    w._remove(5, "nucleus")
    ok("F removing a cell after tracking: the tracking waits for its update",
       w.track is None and w._prev_track is not None)
    from PySide6.QtCore import Qt as _Qt
    w.traces.set_pending([1])                      # (what the update does for its cells)
    pens = {k: it.opts["pen"] for it, k in w.traces._curves}
    ok("F cells being updated: their old traces grey and dashed",
       1 in pens and pens[1].style() == _Qt.DashLine and pens[1].color().red() == 150)
    t = time.perf_counter()
    wait(w)
    dt = time.perf_counter() - t
    p = (w.track or {}).get("retrack", {}).get("plan", {})
    ok("F updated by itself (no TRACK & MEASURE), only that change",
       w.track is not None and not p.get("full"), f"{dt:.1f} s, {p.get('why')}")
    cells = w._followed_cells()
    ref = __import__("peterpiper.manual", fromlist=["x"]).track_cells(
        w.src, w.exp, cells, w.background, int(w.t0 or 0), **w._track_kw(cells))
    Ma, Mb = w.track["meas"]["nucleus"], ref["meas"]["nucleus"]
    ok("F the update equals a full tracking (means, background)",
       np.array_equal(np.nan_to_num(Ma.mean), np.nan_to_num(Mb.mean))
       and np.array_equal(np.nan_to_num(Ma.background), np.nan_to_num(Mb.background)))
    w._undo()
    wait(w)
    ok("F Undo brings the cell (and its tracking) back",
       5 < len(w.cells) and "nucleus" in w.cells[5] and w.track is not None)
    del full, RT


def part_g(w):
    """Export in the background; Next movie while it runs."""
    from peterpiper.gui import clickwin as CW
    real = CW.run_export

    def slow(*a, **k):
        time.sleep(3.0)
        return real(*a, **k)
    CW.run_export = slow
    from peterpiper import nd2io
    real_open = nd2io.open_source
    opened = []                                  # the export's OWN reader (a made-up .nd2:
    nd2io.open_source = lambda p, position=0: (opened.append(str(p)),   # the synthetic one)
                                               SM.load(OUT / "own_reader")[0])[1]
    paths = [str(w.exp.nd2_path), str(OUT / "data" / "flow_b.nd2")]
    movie("flow_b")
    batchqueue.set_items(paths)
    w._update_queue()
    comps = w._export_data()
    keys = ["nucleus|excel", "nucleus|csv", "*|methods", "*|views"]
    w._run_export(comps, keys)
    pump(0.2)
    tasks = [t for t in TK.center().active() if t.kind == "export"]
    ok("G EXPORT runs as a background task; the window's own job is free",
       tasks and not w._busy_now() and w.bg_busy(), [t.title for t in tasks])
    w._ask_save_first = lambda: "go"
    t = time.perf_counter()
    w._next_movie(skip=False)
    while w.isVisible() and time.perf_counter() - t < 5:
        pump(0.02)
    dt = time.perf_counter() - t
    still = [t_ for t_ in tasks if not t_.finished]
    ok("G Next movie opens the next one at once, the export still running",
       w.next_request == {"nd2": paths[1], "run": None} and not w.isVisible() and still,
       f"{dt * 1000:.0f} ms, export running: {bool(still)}")
    t = time.time()
    while any(not t_.finished for t_ in tasks) and time.time() - t < 120:
        pump(0.1)
    done = tasks[0] if tasks else None
    files = (done.result or {}).get("files", []) if done is not None else []
    ok("G ... and finishes afterwards with its files (viewing copies with its own reader)",
       done is not None and done.state == TK.DONE and any(f.endswith(".xlsx") for f in files)
       and any("Viewing copies" in f for f in files), done.error if done else "")
    nd2io.open_source = real_open
    st = {Path(it["nd2"]).stem: it["status"] for it in batchqueue.items()}
    ok("G the queue marks it 'exported' (from the task)", st.get("flow_a") == "exported", st)
    CW.run_export = real
    batchqueue.clear()


def part_h(w):
    texts = [a.text() for a in w._file_menu.actions()]
    ok("H no 'Back up this analysis...' in the File menu",
       not any("Back up" in t for t in texts) and not hasattr(w, "_act_backup"), texts)
    from peterpiper.gui.taskstatus import TaskStatusButton
    ok("H the task button at the right of the status bar",
       isinstance(getattr(w, "task_status", None), TaskStatusButton)
       and w.task_status.isVisible())


def part_i():
    from peterpiper.gui.clickwin import P_DRAW, P_GRAPHS, P_TRACK
    for theme in ("midnight", "daylight"):
        try:
            TH.apply(APP, theme, max(10.0, W.base_font_pt() + 1.0))
        except Exception:                                          # noqa: BLE001
            TH.apply(APP, TH.DEFAULT, 11.0)
        w = make_window(f"flow_i_{theme}", (1366, 728))
        w.grab().save(str(SHOTS / f"v40_flow_{theme}_1_draw_bg.png"))
        bars = scroll_bars(w)
        w._accept_background(0)
        w._auto_select()
        wait(w)
        pump(0.3)
        w.grab().save(str(SHOTS / f"v40_flow_{theme}_2_draw_cells.png"))
        bars += scroll_bars(w)
        sizes = [w.width()]
        w.flow.next.emit()
        wait(w)
        w._select(0)
        pump(0.3)
        w.grab().save(str(SHOTS / f"v40_flow_{theme}_3_track.png"))
        bars += scroll_bars(w)
        sizes.append(w.width())
        w._show_page(P_GRAPHS)
        pump(0.8)
        w.grab().save(str(SHOTS / f"v40_flow_{theme}_4_graphs.png"))
        bars += scroll_bars(w)
        sizes.append(w.width())
        ok(f"I {theme}: no scroll bars on any page at 1366 x 768, the window stays 1366 wide",
           not bars and max(sizes) <= 1366,
           f"{[type(b.parent()).__name__ for b in bars]} widths {sizes}")
        w._show_page(P_DRAW)
        w._dirty = False
        w.close()
        pump(0.3)


def main():
    t0 = time.time()
    w = make_window()
    part_a_b_c_d_e(w)
    part_f(w)
    part_h(w)
    part_g(w)
    from peterpiper.gui.clickwin import ClickWindow, P_DRAW
    w2 = make_window("flow_back")
    w2.flow.back.emit()
    pump(0.3)
    ok("A Back on Draw = the start window (go_back, closed)",
       w2.go_back and not w2.isVisible())
    w3 = make_window("flow_steps")
    w3._goto_step(0, user=True)
    ok("A the old _goto_step(0) shows Draw with the rules open",
       w3._page == P_DRAW and not w3.rules_box.property("folded"))
    w3._dirty = False
    w3.close()
    part_i()
    TK.center().wait_all(30)
    failed = [n for n, c in RESULTS if not c]
    print(f"\n{len(RESULTS) - len(failed)} / {len(RESULTS)} checks passed "
          f"({time.time() - t0:.0f} s)", flush=True)
    del ClickWindow
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
