"""
Developer test (not shipped): PeterPiper 1.1, part "mainwin" - the analysis window
(gui/clickwin.ClickWindow) made calmer, with SAVE, the movie queue, going back and
forth with Compare, and the events other parts follow.

    PYTHONIOENCODING=utf-8 MPLBACKEND=Agg QT_QPA_PLATFORM=offscreen \
        QT_QPA_FONTDIR=C:/Windows/Fonts python dev_tests/test_v11_mainwin.py

Uses the small synthetic movie shipped with the code (dev_tests/synthmovie.py); made-up
file names only. Screenshots: <repo>/_out/shots/v11_mainwin_*.png.

A) opening: the window starts maximized (an explicit resize() wins); main_window_ready
   (window) and movie_opened (nd2, window) are sent once.
B) no scroll bars: at 1366 x 768, 1280 x 800 and 1366 x 700 (a maximized window on a
   1366 x 768 screen, taskbar and title bar off), dark and light theme, every step page
   (and with AUTO-DETECT's slider, and tracked with the traces panel): no visible scroll
   area needs a scroll bar, the side panel's contents fit, the window is not wider or
   taller than asked; one page at a time, the step bar switches pages.
C) events: roi_added (manual=True for a click, False for each AUTO-DETECT cell, with
   n_cells), roi_removed (n_cells).
D) SAVE: writes the 'saved' ROI file with the tracking and the note (read_summary 'note'),
   the note does not change the content key, the feedback line says "in Compare as
   'Saved: <note>'", the 'ROIs saved' note appears, saved (nd2, path, n_cells) is sent,
   File > Save now has Ctrl+S; export sends exported (nd2, folder).
E) the movie queue: "Movie 2 of 5"; Next with changes asks to SAVE first (SAVE, then
   next_request = the next movie still to do, marked 'saved', the window closes); Skip
   marks 'skipped'; export marks 'exported'; the last movie says the queue is finished
   and stays open; a movie not in the queue shows no queue line.
F) going back and forth: load_run_file loads a saved run (with its tracking); the Compare
   window's openRequested for a run of this movie loads it here, for another movie sets
   next_request and closes this window (movie_closed sent).
G) menus: View > Theme is rebuilt each time it opens (a palette found while running
   appears); Help > Achievements... only once something is found (and calls
   eggsdlg.show_achievements); File > Back up this analysis... only with storagedlg
   (and calls backup_dialog(parent, nd2, out_dir)); File > Open results folder.
H) names the lab-data GUI tests use on the window still exist.
I) Smart auto-select (smartselect.py, guarded): hidden without the module; with it,
   status(channels=<this movie's>) is asked; shown beside AUTO-DETECT, locked (lock,
   tooltip with the status text and the directions, a click shows the directions in a
   small popup and runs nothing) or unlocked (sparkle + status label, accent gradient
   from the theme, tooltip with each bin's n; one bin: a click calls
   run(window, bin_name); several bins: a menu, one entry per bin with its n, and
   'Your bins...' -> review_dialog(window), also in step 2's More menu); asked again
   after SAVE; use_detector(None) ends a learner's busy state.
B) also: extras_bar (2 buttons put in on main_window_ready) shows itself and still fits.
"""
from __future__ import annotations

import os
import shutil
import sys
import time
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
OUT = REPO / "_out" / "v11_mainwin"
SHOTS = REPO / "_out" / "shots"
shutil.rmtree(OUT, ignore_errors=True)
OUT.mkdir(parents=True)
SHOTS.mkdir(parents=True, exist_ok=True)
os.environ["PETERPIPER_HOME"] = str(OUT / "home")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")
sys.path.insert(0, str(REPO / "app"))
# Written before smartselect.py existed: start as if it were missing (an import fails);
# the parts that need it put in their own stand-in.
sys.modules["peterpiper.smartselect"] = None
sys.modules["peterpiper.gui.storagedlg"] = None       # likewise (written before it existed)
sys.path.insert(0, str(HERE))

from PySide6.QtCore import QObject, Qt, Signal                       # noqa: E402
from PySide6.QtWidgets import (QAbstractItemView, QAbstractScrollArea,  # noqa: E402
                               QApplication, QMessageBox, QScrollArea)

APP = QApplication(sys.argv)
BOXES = []
for _n in ("information", "warning", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: (BOXES.append(a), QMessageBox.Ok)[1]))
setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.No))
QMessageBox.exec = lambda self: (BOXES.append(self.text()), 0)[1]    # never waits

import synthmovie as SM                                               # noqa: E402
from peterpiper import achievements, batchqueue, events               # noqa: E402
from peterpiper import roifile as RF                                  # noqa: E402
from peterpiper.config import Settings                                # noqa: E402
from peterpiper.gui import theme as TH                                # noqa: E402
from peterpiper.gui import widgets as W                               # noqa: E402
from peterpiper.manual import background_from_outline                 # noqa: E402

N = [0]
FAILS = []
SHOT_FILES = []


def ok(name, cond, extra=""):
    if cond:
        N[0] += 1
    else:
        FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra else ""), flush=True)


def pump(sec=0.3):
    t = time.time()
    while time.time() - t < sec:
        APP.processEvents()
        time.sleep(0.005)


def wait(w):
    pump(0.2)
    while w._busy_now():
        APP.processEvents()
        time.sleep(0.02)
    pump(0.3)


# every event the window sends, with its arguments
GOT = []
for _ev in ("main_window_ready", "movie_opened", "roi_added", "roi_removed", "saved",
            "exported", "movie_closed"):
    events.on(_ev, lambda _e=_ev, **kw: GOT.append((_e, kw)))


def got(name):
    return [kw for e, kw in GOT if e == name]


W.base_font_pt()                                       # as app.py: the default first
TH.apply(APP, "midnight", max(10.0, W.base_font_pt() + 1.0))


def movie(name: str):
    """The synthetic movie, as a (made-up) .nd2 in its own folder."""
    d = OUT / "data"
    d.mkdir(parents=True, exist_ok=True)
    src, exp = SM.load(d / f"OUTPUT_{name}" / "results")
    exp.nd2_path = str(d / f"{name}.nd2")
    Path(exp.out_dir).mkdir(parents=True, exist_ok=True)
    if not Path(exp.nd2_path).exists():
        Path(exp.nd2_path).write_bytes((f"stands in for {name} " * 40).encode())
    return src, exp


def make_window(name="movie_b", size=(1600, 960)):
    from peterpiper.gui.clickwin import ClickWindow
    ClickWindow._ask_previous_run = lambda self, runs, **k: None
    src, exp = movie(name)
    w = ClickWindow(src, exp, Settings(baseline_timepoint=2))
    w._paths_ok = lambda *a, **k: True
    if size:
        w.resize(*size)
    w.show()
    t0 = time.time()
    while not w._offered and time.time() - t0 < 30:
        pump(0.1)
    pump(0.3)
    return w


def place_background(w):
    w.background = background_from_outline([(205, 20), (250, 20), (250, 170), (205, 170)],
                                           (SM.H, SM.W))
    w._bg_auto, w._bg_kind = False, "hand"


def auto_and_track(w):
    w._goto_step(0, user=True)
    w._auto_select()
    wait(w)
    place_background(w)
    w.cmb_comp.setCurrentIndex(w.cmb_comp.findData("nucleus"))
    w._track()
    wait(w)


def scroll_report(w):
    """Visible scroll areas that need a scroll bar (lists of cells / items, which scroll
    by nature, are reported apart), whether the side panel's contents fit, and whether
    the window is bigger than asked."""
    bad, lists = [], []
    for sa in w.findChildren(QAbstractScrollArea):
        if not sa.isVisible():
            continue
        v = sa.verticalScrollBar().maximum() \
            if sa.verticalScrollBarPolicy() != Qt.ScrollBarAlwaysOff else 0
        h = sa.horizontalScrollBar().maximum() \
            if sa.horizontalScrollBarPolicy() != Qt.ScrollBarAlwaysOff else 0
        if v or h:
            (lists if isinstance(sa, QAbstractItemView) else bad).append(
                f"{sa.__class__.__name__}{'#' + sa.objectName() if sa.objectName() else ''}"
                f" v{v} h{h}")
    panel = w._side_scroll.widget()
    need = panel.minimumSizeHint().height()
    room = w._side_scroll.viewport().height()
    if need > room:
        bad.append(f"side panel needs {need} px, has {room}")
    return bad, lists


def shot(w, name):
    p = SHOTS / f"v11_mainwin_{name}.png"
    w.grab().save(str(p))
    SHOT_FILES.append(p)


# ===================================================================== A
def part_a():
    from peterpiper.gui.clickwin import ClickWindow
    ClickWindow._ask_previous_run = lambda self, runs, **k: None
    n0 = len(GOT)
    src, exp = movie("movie_a")
    w = ClickWindow(src, exp, Settings(baseline_timepoint=2))
    ok("A opens maximized by default", bool(w.windowState() & Qt.WindowMaximized))
    new = GOT[n0:]
    ok("A main_window_ready(window) then movie_opened(nd2, window), once each",
       [e for e, _ in new] == ["main_window_ready", "movie_opened"]
       and new[0][1] == {"window": w}
       and new[1][1] == {"nd2": exp.nd2_path, "window": w}, str([e for e, _ in new]))
    ok("A the menus exist when main_window_ready is sent",
       len(w.menuBar().actions()) == 3)
    w.resize(1300, 800)
    ok("A an explicit size replaces the maximized start",
       not (w.windowState() & Qt.WindowMaximized) and w.width() == 1300)
    ok("A next_request starts empty; go_back is kept", w.next_request is None
       and w.go_back is False)
    w.show()
    pump(0.5)
    ok("A one step page at a time (Rules first), traces panel hidden until tracked",
       [b.isVisible() for b in w._step_boxes] == [True, False, False, False, False]
       and not w._dock.isVisible())
    w._goto_step(2, user=True)
    pump(0.1)
    ok("A the step bar switches pages", [b.isVisible() for b in w._step_boxes]
       == [False, False, True, False, False] and w._page == 2)
    ok("A ... leaving the Rules page counts as having looked at them", w._rules_seen)
    ok("A SAVE and EXPORT always on screen (disabled until there is something)",
       w.btn_save.isVisible() and w.btn_export.isVisible() and not w.btn_save.isEnabled()
       and not w.btn_export.isEnabled())
    ok("A Open results folder, Compare, Undo, Another file in the top row",
       all(b.isVisible() for b in (w.btn_folder, w.btn_compare, w.btn_undo, w.btn_back)))
    ok("A not in a queue: no queue line", not w._queue_act.isVisible())
    ok("A extras_bar: there, empty and hidden", w.extras_bar.layout().count() == 0
       and not w.extras_bar.isVisibleTo(w))
    w._dirty = False
    w.close()
    pump(0.3)
    ok("A movie_closed(nd2) on close", got("movie_closed")[-1:] == [{"nd2": exp.nd2_path}])


# ===================================================================== B
SIZES = ((1366, 768), (1280, 800), (1366, 700))


def check_layout(w, tag, pages=range(5)):
    for theme in ("midnight", "daylight"):
        TH.switch(theme)
        w._style_next_box()
        for (sw, sh) in SIZES:
            w.resize(sw, sh)
            pump(0.5)                                     # (the text scaler waits 150 ms)
            for k in pages:
                w._show_page(k)
                pump(0.15)
                bad, lists = scroll_report(w)
                big = w.width() > sw or w.height() > sh
                if w.slider.width() < 80 or w.view.width() < 300:
                    bad.append(f"squeezed: slider {w.slider.width()} px, image {w.view.width()} px")
                ok(f"B {tag}: {theme} {sw}x{sh}, page {k + 1} {w._step_boxes[k]._title.split()[-1]}:"
                   f" no scroll bars", not bad and not big,
                   "; ".join(bad) + (f" window {w.width()}x{w.height()}" if big else "")
                   + (f" (lists: {'; '.join(lists)})" if lists else ""))
                if (sw, sh) == (1366, 768) or (sw, sh) == (1280, 800):
                    shot(w, f"{tag}_{theme}_{sw}x{sh}_step{k + 1}")
    TH.switch("midnight")
    w._style_next_box()


def part_b():
    # two extras put in on main_window_ready (as part charlotte does)
    from PySide6.QtWidgets import QPushButton
    seen = []

    def extras(window):
        seen.append(hasattr(window, "extras_bar"))
        b = QPushButton("Charlotte's Web")
        b.setStyleSheet("QPushButton { background: #f7a8d0; color: #3a0a24; }")
        window.extras_bar.layout().addWidget(b)
        window.add_extra(QPushButton("Another extra"))
    events.on("main_window_ready", extras)
    try:
        w = make_window("movie_b")
    finally:
        events.off("main_window_ready", extras)
    ok("B extras_bar exists before main_window_ready; with buttons in it, it shows itself",
       seen == [True] and w.extras_bar.isVisible() and w.extras_bar.layout().count() == 2)
    check_layout(w, "start")
    w._goto_step(0, user=True)
    w._auto_select()
    wait(w)
    ok("B AUTO-DETECT shows the ROIs page with its slider", w._page == 1
       and w.auto_row.isVisibleTo(w))
    w._set_tool("add")                                # the fullest ROIs page: a tool on too
    check_layout(w, "autodetect", pages=[1])
    w._set_tool(None)
    place_background(w)
    w.cmb_comp.setCurrentIndex(w.cmb_comp.findData("nucleus"))
    w._track()
    wait(w)
    ok("B tracked: the Check page, the traces panel appears", w.track is not None
       and w._page == 3 and w._dock.isVisible())
    check_layout(w, "tracked")
    w.cmb_comp.setCurrentIndex(w.cmb_comp.findData("background"))
    w._show_page(1)
    pump(0.2)
    ok("B Background: its instructions are shown", w.lbl_hint.isVisible()
       and "background" in w.lbl_hint.text().lower())
    w.cmb_comp.setCurrentIndex(w.cmb_comp.findData("nucleus"))
    w._dirty = False
    w.close()
    pump(0.3)


# ===================================================================== C, D
def part_cd():
    batchqueue.clear()
    w = make_window("movie_c")
    nd2 = w.exp.nd2_path
    n0 = len(GOT)
    w.cmb_comp.setCurrentIndex(w.cmb_comp.findData("nucleus"))
    w._set_tool("add")
    y, x = SM.centres(0)[5]
    w._on_point(x, y, False)
    pump(0.2)
    w._set_tool(None)
    adds = [kw for e, kw in GOT[n0:] if e == "roi_added"]
    ok("C a clicked cell: roi_added(manual=True, n_cells=1)",
       adds == [{"nd2": nd2, "manual": True, "n_cells": 1}], str(adds))
    n1 = len(GOT)
    w._auto_select()
    wait(w)
    adds = [kw for e, kw in GOT[n1:] if e == "roi_added"]
    n = sum(1 for c in w.cells if c)
    ok("C AUTO-DETECT: one roi_added(manual=False) per cell found, n_cells after",
       len(adds) == n - 1 and n == 16 and all(a["manual"] is False and a["n_cells"] == n
                                              and a["nd2"] == nd2 for a in adds),
       f"{len(adds)} events, {n} cells")
    k = next(i for i, c in enumerate(w.cells) if "nucleus" in c)
    n2 = len(GOT)
    w._remove(k, "nucleus")
    rem = [kw for e, kw in GOT[n2:] if e == "roi_removed"]
    ok("C removed: roi_removed(nd2, n_cells=15)", rem == [{"nd2": nd2, "n_cells": 15}], str(rem))
    w._undo()
    place_background(w)
    w._track()
    wait(w)
    ok("D tracked", w.track is not None)
    ok("D SAVE enabled, unsaved changes", w.btn_save.isEnabled() and w._unsaved())
    w.ed_note.setText("  dim cells   left out ")
    n3 = len(GOT)
    path = w._save_clicked()
    pump(0.3)
    s = RF.read_summary(path) if path else {}
    ok("D SAVE writes a 'saved' ROI file with the tracking", path and Path(path).exists()
       and s.get("kind") == "saved" and s.get("tracked") and s.get("n_cells") == 16,
       str(path))
    ok("D ... with the note in its summary", s.get("note") == "dim cells left out",
       repr(s.get("note")))
    sv = [kw for e, kw in GOT[n3:] if e == "saved"]
    ok("D saved(nd2, path, n_cells) sent", sv == [{"nd2": nd2, "path": str(path),
                                                   "n_cells": 16}], str(sv))
    info = w.lbl_save_info.text()
    ok("D the feedback says when and how Compare shows it",
       info.startswith("Saved ") and "in Compare as 'Saved: dim cells left out'" in info, info)
    ok("D the 'ROIs saved' note appears (no OK box)", getattr(w, "_toasts", [])[-1][0]
       == "ROIs saved" and "Saved: dim cells left out" in w._toasts[-1][1])
    ok("D nothing unsaved after SAVE; the note field is emptied", not w._unsaved()
       and w.ed_note.text() == "")
    ok("D File > Save now has Ctrl+S", w.act_save.shortcut().toString() == "Ctrl+S")
    path2 = w._save_rois(silent=True, note="")
    s2 = RF.read_summary(path2)
    ok("D the note does not change the content key (same analysis)",
       s2.get("content_key") == s.get("content_key") and s2.get("note") == "")
    # export
    comps = w._export_data()
    n4 = len(GOT)
    w._run_export(comps, ["nucleus|csv"])
    wait(w)
    ex = [kw for e, kw in GOT[n4:] if e == "exported"]
    ok("D export: exported(nd2, folder)", len(ex) == 1 and ex[0]["nd2"] == nd2
       and Path(ex[0]["folder"]).is_dir() and ex[0]["folder"] == w._exported, str(ex))
    w._dirty = False
    w.close()
    pump(0.3)
    return path


# ===================================================================== E
def part_e():
    names = ["movie_q1", "movie_q2", "movie_q3", "movie_q4", "movie_q5"]
    paths = [movie(n)[1].nd2_path for n in names]
    batchqueue.set_items(paths)
    w = make_window("movie_q2")
    ok("E 'Movie 2 of 5' and Next movie / Skip", w._queue_act.isVisible()
       and w.lbl_queue.text() == "Movie 2 of 5" and w.btn_next.isVisible()
       and w.btn_skip.isVisible(), w.lbl_queue.text())
    shot(w, "queue_line")
    asked = []
    w._ask_save_first = lambda: (asked.append(1), "save")[1]
    auto_and_track(w)
    w._next_movie()
    pump(0.5)
    st = {Path(it["nd2"]).stem: it["status"] for it in batchqueue.items()}
    ok("E Next with changes asks to SAVE first, then saves (marked 'saved')",
       asked == [1] and st["movie_q2"] == "saved", str(st))
    ok("E next_request = the next movie still to do, no run",
       w.next_request == {"nd2": paths[2], "run": None}, str(w.next_request))
    ok("E ... and the window closed", not w.isVisible())
    # Skip
    w = make_window("movie_q3")
    w._ask_save_first = lambda: (asked.append(2), None)[1]
    w._next_movie(skip=True)
    pump(0.5)
    st = {Path(it["nd2"]).stem: it["status"] for it in batchqueue.items()}
    ok("E Skip: marked 'skipped', next_request = movie 4, closed",
       st["movie_q3"] == "skipped" and w.next_request == {"nd2": paths[3], "run": None}
       and not w.isVisible() and asked == [1], str(st))
    # export marks exported; Next without changes asks nothing
    w = make_window("movie_q4")
    w._ask_save_first = lambda: (asked.append(2), None)[1]
    auto_and_track(w)
    w._run_export(w._export_data(), ["nucleus|csv"])
    wait(w)
    st = {Path(it["nd2"]).stem: it["status"] for it in batchqueue.items()}
    ok("E export: marked 'exported'", st["movie_q4"] == "exported", str(st))
    w._save_rois(silent=True)
    st = {Path(it["nd2"]).stem: it["status"] for it in batchqueue.items()}
    ok("E a SAVE after the export does not make it 'saved' again", st["movie_q4"] == "exported")
    # Next with changes, Cancel: stays
    w.ed_note.setText("x")
    w._mark_dirty()
    w._next_movie()
    pump(0.3)
    ok("E Cancel in 'Save first?': stays open, no request", w.isVisible()
       and w.next_request is None and asked == [1, 2])
    w._ask_save_first = lambda: "go"
    w._next_movie()
    pump(0.5)
    ok("E 'without saving': next_request = movie 5 (wraps past the done ones)",
       w.next_request == {"nd2": paths[4], "run": None} and not w.isVisible(),
       str(w.next_request))
    # the last movie
    batchqueue.mark(paths[0], "skipped")
    w = make_window("movie_q5")
    ok("E the last one still to do: the button says 'Finish the queue'",
       w.btn_next.text() == "Finish the queue", w.btn_next.text())
    w._next_movie()
    pump(0.3)
    st = w.lbl_status.text().replace(chr(0x200B), "")
    ok("E the last movie: the queue is finished, said kindly; the window stays",
       w.isVisible() and w.next_request is None and "last movie in your queue" in st
       and "Well done" in st and w._toasts[-1][0] == "Queue finished", st[:90])
    shot(w, "queue_finished")
    w._dirty = False
    w.close()
    pump(0.3)
    batchqueue.clear()


# ===================================================================== F
class FakeCompare(QObject):
    """Stands in for gui/comparewin.CompareWindow (part compare adds openRequested)."""
    openRequested = Signal(dict)
    made = []

    def __init__(self, *a, **k):
        super().__init__()
        self.open_request = None
        FakeCompare.made.append(self)

    def show(self):
        pass

    def close(self):
        return True

    def ask(self, req):
        self.open_request = req
        self.openRequested.emit(req)


def part_f(saved_path):
    w = make_window("movie_c")
    loaded = w.load_run_file(saved_path)
    pump(0.3)
    ok("F load_run_file loads a saved run with its tracking", loaded and w.track is not None
       and sum(1 for c in w.cells if c) == 16 and w._based_on == str(saved_path))
    ok("F ... the Check page is shown", w._page == 3)
    ok("F a missing file: False", not w.load_run_file(str(OUT / "nothing_ROIs.npz")))
    from peterpiper.gui import comparewin
    real = comparewin.CompareWindow
    comparewin.CompareWindow = FakeCompare
    try:
        w._compare_runs()
        cw = FakeCompare.made[-1]
        w.cells = []                                # (to see the run come back)
        w._refresh()
        cw.ask({"nd2": w.exp.nd2_path, "run": str(saved_path)})
        pump(0.3)
        ok("F Compare 'Open in analysis' on a run of this movie: loaded here, stays open",
           w.isVisible() and w.next_request is None and sum(1 for c in w.cells if c) == 16
           and w.track is not None)
        other = movie("movie_other")[1].nd2_path
        run2 = str(OUT / "elsewhere" / "movie_other_ROIs.npz")
        n0 = len(GOT)
        cw.ask({"nd2": other, "run": run2})
        pump(0.5)
        ok("F ... a run of another movie: next_request = that movie and run, closed",
           w.next_request == {"nd2": other, "run": run2} and not w.isVisible(),
           str(w.next_request))
        ok("F ... movie_closed sent for this movie",
           [kw for e, kw in GOT[n0:] if e == "movie_closed"] == [{"nd2": w.exp.nd2_path}])
    finally:
        comparewin.CompareWindow = real


# ===================================================================== G
def part_g():
    w = make_window("movie_g")
    names = lambda: [a.text() for a in w._theme_menu.actions()]        # noqa: E731
    w._theme_menu.aboutToShow.emit()
    before = names()
    ok("G View > Theme: the two basic themes", before == [TH.label(n) for n in TH.BASIC])
    w._help_menu.aboutToShow.emit()
    ok("G Help > Achievements... hidden while nothing is found", not w._act_eggs.isVisible())
    import dataclasses
    if len(TH.THEMES) <= len(TH.BASIC):              # (part looks adds the real palettes)
        TH.THEMES["test_palette"] = dataclasses.replace(TH.THEMES["midnight"],
                                                        name="test_palette")
    achievements.unlock("palettes")
    w._theme_menu.aboutToShow.emit()
    after = names()
    ok("G a palette found while running appears the next time the menu opens",
       len(after) > len(before) and after == [TH.label(n) for n in TH.available_names()],
       f"{len(before)} -> {len(after)}")
    ok("G ... with the current theme ticked",
       [a.text() for a in w._theme_menu.actions() if a.isChecked()] == [TH.label("midnight")])
    calls = []
    fake = types.ModuleType("peterpiper.gui.eggsdlg")
    fake.show_achievements = lambda parent: calls.append(("eggs", parent))
    sys.modules["peterpiper.gui.eggsdlg"] = fake
    import peterpiper.gui as G
    G.eggsdlg = fake
    w._help_menu.aboutToShow.emit()
    ok("G Help > Achievements... shown once something is found", w._act_eggs.isVisible())
    w._act_eggs.trigger()
    ok("G ... it calls eggsdlg.show_achievements(window)", calls == [("eggs", w)])
    w._file_menu.aboutToShow.emit()
    ok("G File > Back up this analysis... hidden without storagedlg",
       not w._act_backup.isVisible())
    sto = types.ModuleType("peterpiper.gui.storagedlg")
    sto.backup_dialog = lambda parent, nd2, out: calls.append(("backup", parent, nd2, out))
    sys.modules["peterpiper.gui.storagedlg"] = sto
    G.storagedlg = sto
    w._file_menu.aboutToShow.emit()
    ok("G ... shown with it", w._act_backup.isVisible())
    w._act_backup.trigger()
    ok("G ... backup_dialog(window, nd2, out_dir)",
       calls[-1] == ("backup", w, w.exp.nd2_path, w.exp.out_dir), str(calls[-1]))
    opened = []
    W.open_path = lambda p: (opened.append(str(p)), True)[1]
    w.btn_folder.click()
    ok("G Open results folder: one click opens the movie's results folder",
       opened == [w.exp.out_dir])
    acts = [a.text() for a in w._file_menu.actions()]
    ok("G File menu keeps Compare / average runs..., Load saved ROIs..., Earlier analyses",
       all(t in acts for t in ("Compare / average runs...", "Load saved ROIs...",
                               "Earlier analyses of this file...", "Choose another file...")))
    del sys.modules["peterpiper.gui.eggsdlg"], sys.modules["peterpiper.gui.storagedlg"]
    w._dirty = False
    w.close()
    pump(0.3)


# ===================================================================== H
USED = """_add_helper _ask_previous_run _ask_save_graph _auto_batch _auto_select _autosave
_based_on _bg_auto _bg_kind _bound_k _busy_now _choose_outputs _det_lay _detector_used _dirty
_dock _earlier_analyses _export_data _exported _extend_k _fill_detectors _fold_toggled _fp
_gate _gate_note _goto_step _last_key _live _load_roi_file _load_rois _mark_dirty _measured
_offered _on_boundary_line _on_lasso _on_point _paths_ok _place_background _prefer_sheets
_provenance _roi_state _rois _rows _rows_changed _rules_key _run_export _runner _save_log
_save_rois _save_timer _session_file _set_include _set_rules _set_tool _set_track_settings
_step_boxes _step_btns _step_now _sync_traces _tool_clicked _track _track_form _undo
_use_detector _why _writer act_ask act_autosave auto_row background boundaries btn_bound
btn_compare btn_export btn_load cells cmb_comp cmb_view comp cur_t det_box excl exp follow
go_back lbl_auto lbl_next lbl_saved lbl_seen lbl_status lbl_track q_base qc rules
session_id settings sl_auto slider sp_and sp_gate sp_move sp_tol src t0 tool traces track
view _compare_runs _saved_files _scaler _set_text_size _view_changed _cancel _on_cancelled
progress btn_auto _busy _restoring _norm""".split()


def part_h():
    w = make_window("movie_h")
    missing = [n for n in USED if not hasattr(w, n)]
    ok("H every window name the other tests use still exists", not missing, " ".join(missing))
    ok("H new: next_request, load_run_file", hasattr(w, "next_request")
       and callable(getattr(w, "load_run_file", None)))
    w._dirty = False
    w.close()
    pump(0.3)


# ===================================================================== I
def part_i():
    w = make_window("movie_i")
    ok("I Smart auto-select hidden without smartselect.py", not w.btn_smart.isVisibleTo(w)
       and w._smart_state is None and not w.act_bins.isVisible())
    w._dirty = False
    w.close()
    pump(0.2)
    how = "Draw the cells by hand on 3 movies of a queue and SAVE each."
    bins = [{"name": "gfp_cy5_nuclei", "label": "GFP/Cy5 nuclei", "n_movies": 44,
             "n_rois": 1250, "channels": ["Cy5", "GFP", "mCherry"]}]
    state = {"unlocked": False, "text": "Locked - 1 of 3 hand-drawn queued movies",
             "how": how, "label": "Smart auto-select (locked)", "bins": []}
    asked, runs, reviews = [], [], []

    def status(channels=None):
        asked.append(channels)
        return dict(state, bins=[dict(b) for b in state["bins"]])
    mod = types.ModuleType("peterpiper.smartselect")
    mod.status = status
    mod.run = lambda window, bin_name=None: runs.append((window, bin_name))
    mod.review_dialog = lambda window: (reviews.append(window), True)[1]
    sys.modules["peterpiper.smartselect"] = mod
    import peterpiper
    peterpiper.smartselect = mod
    try:
        w = make_window("movie_i")
        w._show_page(1)
        pump(0.2)
        b = w.btn_smart
        ok("I status() is asked with this movie's channel names",
           asked and asked[-1] == ["Cy5", "GFP", "mCherry"], str(asked[-1:]))
        ok("I with smartselect.py: shown beside AUTO-DETECT, locked (lock, still clickable "
           "so its directions show on hover)", b.isVisible() and b.isEnabled()
           and "\U0001F512" in b.text() and b.property("locked") is True, b.text())
        tip = b.toolTip()
        ok("I the tooltip has the status text and the directions",
           state["text"] in tip and how in tip, tip[:120])
        ok("I 'Your bins...' in step 2's More menu", w.act_bins.isVisible())
        b.click()
        pump(0.2)
        pop = w._smart_pop
        ok("I clicking it while locked shows the directions in a small popup, runs nothing",
           pop is not None and pop.isVisible() and how in w._smart_popup_text
           and runs == [], getattr(w, "_smart_popup_text", "")[:80])
        shot(w, "smart_locked")
        pop.close()
        # unlocked, one bin fits
        state.update(unlocked=True, text="Ready", bins=bins,
                     label="Smart auto-select: GFP/Cy5 nuclei (n=44)")
        n_asked = len(asked)
        auto_and_track(w)
        w._save_rois(silent=True)                    # a SAVE asks status() again
        w._show_page(1)
        pump(0.2)
        ok("I after SAVE status() is asked again: unlocked, with the sparkle and the label",
           len(asked) > n_asked and b.property("locked") is False
           and b.full_text() == "✦  Smart auto-select: GFP/Cy5 nuclei (n=44)"
           and "✦" in b.text() and b.menu() is None, b.text())
        tip = b.toolTip()
        ok("I ... the tooltip has the directions and each bin's n",
           how in tip and "GFP/Cy5 nuclei: n=44" in tip, tip[:160])
        ok("I ... its look comes from the theme (accent gradient, accent text colour)",
           TH.current().accent_text.lower() in b.styleSheet().lower()
           and "qlineargradient" in b.styleSheet())
        shot(w, "smart_unlocked")
        TH.switch("daylight")
        w._style_next_box()
        w._style_smart()
        pump(0.2)
        ok("I ... and follows a theme change", TH.THEMES["daylight"].accent.lower()
           in b.styleSheet().lower())
        shot(w, "smart_unlocked_daylight")
        TH.switch("midnight")
        w._style_next_box()
        w._style_smart()
        b.click()
        pump(0.2)
        ok("I one bin: a click calls run(window, bin_name=that bin)",
           runs == [(w, "gfp_cy5_nuclei")], str(runs))
        # two bins fit: a small menu
        state["bins"] = bins + [{"name": "cy5_only", "label": "Cy5 nuclei", "n_movies": 7,
                                 "n_rois": 210, "channels": ["Cy5"]}]
        w._refresh_smart()
        m = b.menu()
        texts = [a.text() for a in m.actions()] if m is not None else []
        ok("I two bins fit: a menu, one entry per bin with its n, and 'Your bins...'",
           texts[:2] == ["GFP/Cy5 nuclei  (n=44)", "Cy5 nuclei  (n=7)"]
           and texts[-1] == "Your bins...", str(texts))
        m.actions()[1].trigger()
        pump(0.1)
        ok("I ... choosing one runs that bin", runs[-1] == (w, "cy5_only"))
        m.actions()[-1].trigger()
        pump(0.1)
        ok("I ... 'Your bins...' opens review_dialog(window)", reviews == [w])
        w.act_bins.trigger()
        ok("I ... so does More > Smart auto-select: your bins...", reviews == [w, w])
        ok("I use_detector(None) ends a learner's busy state cleanly",
           (w.use_detector(None), not w._busy_now() and w.btn_auto.isEnabled())[1])
        w._dirty = False
        w.close()
        pump(0.2)
    finally:
        del sys.modules["peterpiper.smartselect"]
        del peterpiper.smartselect


def main():
    part_a()
    part_b()
    path = part_cd()
    part_e()
    part_f(path)
    part_g()
    part_h()
    part_i()
    print("\nscreenshots:\n  " + "\n  ".join(str(p) for p in SHOT_FILES[:6])
          + (f"\n  ... {len(SHOT_FILES)} in {SHOTS}" if len(SHOT_FILES) > 6 else ""))
    print(f"\n{N[0]} / {N[0] + len(FAILS)} checks passed")
    if FAILS:
        print("FAILED:\n  " + "\n  ".join(FAILS))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
