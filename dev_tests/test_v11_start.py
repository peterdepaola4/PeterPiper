"""
Developer test (not shipped): PeterPiper 1.1, part "start" - the new start
screen, the movie queue on it, prepare(), recent analyses and the app loop.
No lab data needed (made-up movies: the .nd2 reader is replaced by a fake).

    MPLBACKEND=Agg QT_QPA_PLATFORM=offscreen QT_QPA_FONTDIR=C:/Windows/Fonts \\
        python dev_tests/test_v11_start.py

A) the start screen: the logo, the big choices (Analyse movies, Continue your
   queue only when there is one, Compare / average with its old text), the
   secondary links (Saved files, More with batch / templates / profiles, text
   size, theme), the theme list rebuilt from available_names() when shown;
   NO scroll bars and nothing squeezed at 1366 x 768, 1280 x 800 and 1366 x 698
   (a maximized window above the taskbar) and 1920 x 1040 (the text grows with
   the window), dark and light, with a movie that
   shows every warning, a queue and 8 recent analyses - screenshots.
B) the queue: choosing several movies fills batchqueue (in order), shows them
   with their status (to do / saved / exported / skipped), the first to do is
   shown for checking; 'Continue your queue (N left)' asks app.py to open the
   next to do; a queue that still has movies to do asks add / new; Remove, Clear.
C) prepare(): a good movie gives a usable (source, experiment, settings) -
   OUTPUT_<movie>/<user>, position 1, the file's channel names and numbers,
   saved settings made valid for the movie; a missing pixel size, frame
   interval 0, uneven gaps, several positions or unusable channel names raise
   NeedsCheck (the file closed again); a missing file raises; an unwritable
   results folder asks the same question (other place / cancel -> NeedsCheck).
   The start screen opened with such a movie shows it with the reason, and the
   run asked for is passed on.
D) the app loop (app.run_loop with a fake UI): Next movie opens the next movie
   directly, a movie that needs a look opens the start screen with it, an Open
   request from the start screen loads its run, Choose another file goes back,
   Switch user, errors; load_run uses load_run_file when there, else
   _load_roi_file, and waits until the window is not busy; the real window
   class opens through the same path; charlotte is installed guarded.
E) recent analyses: from a made-up run list, the newest 8 of this user's runs
   (one per movie; others' runs and missing files left out); Open asks for that
   movie and run; Results folder opens it; a movie that is not here cannot be
   opened; Compare's open_request is passed on the same way.
F) read-only results folders (1.0.3) still handled on the start screen, and
   the Storage & cloud link appears only when gui/storagedlg.py is there.
G) Smart auto-select (smartselect.status(), built by the lead): its one line in
   the start screen's header, the directions as the tooltip and behind (?),
   'ok' colour when unlocked; left out when the module is missing or fails.
"""
from __future__ import annotations

import os
import shutil
import sys
import time
import types
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
OUT = REPO / "_out" / "v11_start"
SHOTS = REPO / "_out" / "shots"
shutil.rmtree(OUT, ignore_errors=True)
OUT.mkdir(parents=True)
SHOTS.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("PETERPIPER_HOME", str(OUT / "home"))
os.environ["PETERPIPER_RESULTS"] = str(OUT / "PeterPiper results")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")
sys.path.insert(0, str(REPO / "app"))

from PySide6.QtCore import QTimer                                     # noqa: E402
from PySide6.QtWidgets import (QAbstractScrollArea, QApplication, QDialog,  # noqa: E402
                               QFileDialog, QMessageBox, QWidget)

APP = QApplication(sys.argv)
for _n in ("information", "warning", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: QMessageBox.Ok))

from peterpiper import batchqueue, users                              # noqa: E402
from peterpiper import history as H                                   # noqa: E402
from peterpiper.config import load_settings, save_settings            # noqa: E402
from peterpiper.gui import setup as SU                                # noqa: E402
from peterpiper.gui import theme as TH                                # noqa: E402
from peterpiper.gui import widgets as W                               # noqa: E402
from peterpiper.nd2io import ImageSource                              # noqa: E402

N = [0]
FAILS = []


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
        time.sleep(0.01)


# ------------------------------------------------------------ made-up movies
MOVIES = OUT / "movies"
MOVIES.mkdir()
SPEC = {}            # file name -> dict(um, spf, gaps, n_pos, channels, T)
OPENED = []          # FakeMovie objects made


class FakeMovie(ImageSource):
    def __init__(self, path, position=0):
        sp = SPEC[Path(path).name]
        self.path = str(path)
        self.channels = list(sp.get("channels", ["Cy5", "GFP", "mCherry"]))
        self.n_timepoints = int(sp.get("T", 12))
        self.height, self.width = 48, 64
        self.um_per_px = float(sp.get("um", 0.5))
        self.bit_depth, self.objective = 16, "Plan Apo 60x"
        self.n_positions = int(sp.get("n_pos", 1))
        self.position = int(position)
        self._spf = float(sp.get("spf", 30.0))
        self._gap = float(sp.get("gap", 0.0))
        self.closed = False
        OPENED.append(self)

    def seconds_per_frame(self):
        return self._spf

    def frame_times(self):
        if self._spf <= 0:
            return None
        t = np.arange(self.n_timepoints, dtype=float) * self._spf
        if self._gap:
            t[1:] += self._gap
        return t

    def frame(self, t):
        return np.zeros((len(self.channels), self.height, self.width), np.uint16)

    def close(self):
        self.closed = True


def movie(name, **spec):
    p = MOVIES / name
    p.write_bytes(b"not a real nd2 " * 10)
    SPEC[name] = spec
    return str(p)


SU.open_source = lambda path, position=0: (time.sleep(0.05), FakeMovie(path, position))[1]

if "Test User" not in users.all_users():
    users.add_user("Test User")
if "Other Person" not in users.all_users():
    users.add_user("Other Person")
users.activate("Test User")
ME = users._folder_of("Test User")
THEM = users._folder_of("Other Person")


def scroll_report(d, w, h):
    """[] if no visible scroll area needs a scroll bar and the window kept the
    size (nothing had to be squeezed); else what is wrong."""
    bad = []
    if (d.width(), d.height()) != (w, h):
        bad.append(f"window became {d.width()} x {d.height()}")
    for a in d.findChildren(QAbstractScrollArea):
        if a.isVisible() and (a.verticalScrollBar().maximum() > 0
                              or a.horizontalScrollBar().maximum() > 0):
            bad.append(f"{type(a).__name__} {a.objectName() or ''} scrolls "
                       f"(v {a.verticalScrollBar().maximum()}, "
                       f"h {a.horizontalScrollBar().maximum()})")
    ms = d.layout().totalMinimumSize()
    if ms.height() > h or ms.width() > w:
        bad.append(f"needs at least {ms.width()} x {ms.height()}")
    for wid in d.findChildren(QWidget):          # nothing drawn outside the window
        if wid.isVisible() and wid.isWindow() is False and wid.width() > 0:
            r = wid.rect().translated(wid.mapTo(d, wid.rect().topLeft()))
            if r.bottom() > h + 1 or r.right() > w + 1:
                bad.append(f"{type(wid).__name__} '{getattr(wid, 'text', lambda: '')()}' "
                           f"reaches {r.right()} x {r.bottom()}")
                break
    return bad


# ======================================================================== E (data)
def make_run_list():
    """10 movies of mine (one with two runs), one of another user's, one whose run
    file is gone, one whose movie is not here; written as this user's run list."""
    idx = {}
    for i in range(10):
        nd2 = movie(f"cells {i:02d}.nd2")
        folder = MOVIES / f"OUTPUT_cells {i:02d}" / ME
        folder.mkdir(parents=True, exist_ok=True)
        runs = []
        for j in range(2 if i == 9 else 1):
            rp = folder / f"cells {i:02d}_ROIs{'' if j == 0 else '_2'}.npz"
            rp.write_bytes(b"x")
            runs.append(dict(path=str(rp), saved=f"2026-11-{1 + i:02d}T10:0{j}:00",
                             kind="saved" if j == 0 else "session", tracked=True,
                             n_cells=10 + i + j))
        idx[f"key{i}"] = dict(nd2_name=Path(nd2).name, paths=[nd2], runs=runs)
    other = MOVIES / "OUTPUT_theirs" / THEM
    other.mkdir(parents=True, exist_ok=True)
    (other / "theirs_ROIs.npz").write_bytes(b"x")
    idx["their"] = dict(nd2_name="theirs.nd2", paths=[movie("theirs.nd2")],
                        runs=[dict(path=str(other / "theirs_ROIs.npz"), saved="2026-12-30T10:00:00",
                                   kind="saved", tracked=True, n_cells=5)])
    idx["gone"] = dict(nd2_name="gone run.nd2", paths=[movie("gone run.nd2")],
                       runs=[dict(path=str(MOVIES / "OUTPUT_x" / ME / "gone_ROIs.npz"),
                                  saved="2026-12-29T10:00:00", kind="saved", tracked=True,
                                  n_cells=3)])
    away = MOVIES / "OUTPUT_away" / ME
    away.mkdir(parents=True, exist_ok=True)
    (away / "away_ROIs.npz").write_bytes(b"x")
    idx["away"] = dict(nd2_name="away.nd2", paths=[str(OUT / "unplugged" / "away.nd2")],
                       runs=[dict(path=str(away / "away_ROIs.npz"), saved="2026-11-30T10:00:00",
                                  kind="session", tracked=True, n_cells=7)])
    import json
    p = H._index_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(idx, indent=1), encoding="utf-8")


# ======================================================================== A
def full_state(d):
    """The busiest start screen: a movie with every warning, a queue, recents."""
    d._load(WORST)
    d._set_check_note("The pixel size was not found in the file (1.0 \u00b5m/px is only a "
                      "stand-in) - every size and area depends on it. The gaps between "
                      "timepoints are uneven (timepoint 1 \u2192 2: 1 h 0 min).")


def part_a():
    TH.apply(APP, "midnight", 10.0)
    d = SU.SetupDialog()
    d.show()
    pump(0.4)
    ok("A the logo is on the start screen", d.findChild(W.LogoLabel) is not None)
    ok("A the big choices: Analyse movies, Compare / average (old text kept)",
       d.btn_analyse.text() == "Analyse movies" and
       d.btn_compare.text().startswith("Compare / average"))
    ok("A 'Continue your queue' is hidden without a queue", not d.btn_queue.isVisible())
    acts = {k: a.text() for k, a in d._more_actions.items()}
    ok("A More holds batch (automatic), Prism templates and the profiles",
       set(acts) == {"batch", "templates", "export_profile", "import_profile"}
       and "automatic" in acts["batch"].lower(), str(acts))
    ok("A Saved files and the theme list are there; the theme list = available_names()",
       d.btn_saved.isVisible() and
       [d.cmb_theme.itemData(i) for i in range(d.cmb_theme.count())] == TH.available_names())
    real = TH.available_names
    TH.available_names = lambda: list(real()) + ["sunset"]
    try:
        d.hide()
        d.show()
        pump(0.1)
        names = [d.cmb_theme.itemData(i) for i in range(d.cmb_theme.count())]
    finally:
        TH.available_names = real
    ok("A ... rebuilt each time it is shown (a palette found while running appears)",
       "sunset" in names, str(names))
    ok("A no movie yet: a short hint, the Open button off", d.lbl_hint.isVisible()
       and not d.movie_panel.isVisible() and not d.btn_open.isEnabled())
    d.resize(1366, 768)
    pump(0.4)
    bad = scroll_report(d, 1366, 768)
    ok("A empty start screen at 1366 x 768: no scroll bars", not bad, "; ".join(bad))
    d.grab().save(str(SHOTS / "start_empty_1366x768_dark.png"))
    d.reject()

    batchqueue.set_items([QUEUE[0], QUEUE[1], QUEUE[2], QUEUE[3], QUEUE[4]])
    batchqueue.mark(QUEUE[1], "saved")
    batchqueue.mark(QUEUE[2], "exported")
    batchqueue.mark(QUEUE[3], "skipped")
    smart = fake_smartselect(False)               # the Smart auto-select line shown too
    for theme in ("midnight", "daylight"):
        TH.apply(APP, theme, 10.0)
        for (w, h) in ((1366, 768), (1280, 800), (1366, 698), (1920, 1040)):
            d = SU.SetupDialog()
            d.show()
            d.resize(w, h)
            pump(0.2)
            full_state(d)
            pump(0.5)
            tag = f"{w}x{h}_{'dark' if theme == 'midnight' else 'light'}"
            bad = []
            for tab in (0, 1):
                d.tabs.setCurrentIndex(tab)
                pump(0.25)
                bad += scroll_report(d, w, h)
                d.grab().save(str(SHOTS / f"start_{tag}_{'recent' if tab == 0 else 'queue'}.png"))
            ok(f"A {tag}: movie with every warning, queue and 8 recent analyses - no scroll "
               f"bars, nothing squeezed", not bad, "; ".join(bad[:4]))
            if (w, h) == (1366, 768):
                ok(f"A {tag}: every warning shown, the queue choice says 2 left",
                   d.lbl_gaps.isVisible() and d.lbl_check.isVisible()
                   and d.cmb_pos.isVisible() and d.btn_queue.isVisible()
                   and "(2 left)" in d.btn_queue.text() and d.tree_recent.topLevelItemCount() == 8)
            if (w, h) == (1280, 800):
                ok(f"A {tag}: the Smart auto-select line is shown in the header",
                   d.smart_box.isVisible() and smart.TEXT in d.lbl_smart.text())
            d.reject()
    TH.apply(APP, "midnight", 10.0)
    batchqueue.clear()
    drop_smartselect()


def fake_smartselect(unlocked, text=None, how="1  Play the hidden minigame.\n2  Draw the "
                     "cells by hand in 3 queued movies and SAVE each.", fail=False):
    m = types.ModuleType("peterpiper.smartselect")
    m.TEXT = text or ("Smart auto-select: on - learns from your hand-drawn cells" if unlocked
                      else "Smart auto-select: locked - 1 of 3 hand-drawn queued movies")

    def status():
        if fail:
            raise RuntimeError("broken")
        return {"unlocked": unlocked, "text": m.TEXT, "how": how}
    m.status = status
    sys.modules["peterpiper.smartselect"] = m
    return m


def drop_smartselect():
    sys.modules.pop("peterpiper.smartselect", None)
    import peterpiper
    if hasattr(peterpiper, "smartselect"):
        delattr(peterpiper, "smartselect")


# ======================================================================== G
def part_g():
    drop_smartselect()
    d = SU.SetupDialog()
    d.show()
    pump(0.1)
    ok("G no smartselect.py: no Smart auto-select line", not d.smart_box.isVisible())
    m = fake_smartselect(False)
    d.hide()
    d.show()
    pump(0.1)
    ok("G locked: its one line is shown (refreshed when the start screen shows), the "
       "directions as the tooltip", d.smart_box.isVisible() and m.TEXT in d.lbl_smart.text()
       and "minigame" in d.lbl_smart.toolTip() and d.btn_smart_how.isVisible()
       and d.lbl_smart.property("muted") is True)
    shown = []
    real = QMessageBox.information
    QMessageBox.information = staticmethod(lambda *a, **k: shown.append(a) or QMessageBox.Ok)
    try:
        d.btn_smart_how.click()
    finally:
        QMessageBox.information = real
    ok("G ... (?) shows the directions on click", shown and "minigame" in shown[0][2]
       and m.TEXT in shown[0][2])
    d.reject()
    m = fake_smartselect(True)
    d = SU.SetupDialog()
    d.show()
    d.resize(1366, 768)
    pump(1.0)
    ok("G unlocked: said in the theme's 'ok' colour", d.smart_box.isVisible()
       and d.lbl_smart.property("role") == "ok" and m.TEXT in d.lbl_smart.text())
    d.grab().save(str(SHOTS / "start_smart_unlocked.png"))
    d.reject()
    fake_smartselect(True, fail=True)
    d = SU.SetupDialog()
    ok("G a failing status(): the line is left out, no error", not d.smart_box.isVisibleTo(d))
    d.reject()
    drop_smartselect()


# ======================================================================== B
def part_b():
    d = SU.SetupDialog()
    d.show()
    pump(0.2)
    real = QFileDialog.getOpenFileNames
    QFileDialog.getOpenFileNames = staticmethod(lambda *a, **k: (QUEUE[:4], "ND2"))
    try:
        d.btn_analyse.click()
        pump(0.3)
    finally:
        QFileDialog.getOpenFileNames = real
    its = batchqueue.items()
    ok("B choosing 4 movies at once fills the queue, in order, all to do",
       [it["nd2"] for it in its] == QUEUE[:4] and all(it["status"] == "todo" for it in its))
    ok("B ... the queue is shown with 4 rows; the first movie is shown for checking",
       d.tabs.currentIndex() == 1 and d.tree_queue.topLevelItemCount() == 4 and
       d.experiment is not None and d.experiment.nd2_path == QUEUE[0]
       and "movie 1 of 4" in d.lbl_file.text(), d.lbl_file.text())
    batchqueue.mark(QUEUE[0], "exported")
    batchqueue.mark(QUEUE[1], "saved")
    batchqueue.mark(QUEUE[2], "skipped")
    d._refresh_queue()
    st = [d.tree_queue.topLevelItem(i).text(2) for i in range(4)]
    ok("B the statuses are shown in words", st == ["exported \u2713", "saved", "skipped", "to do"],
       str(st))
    ok("B 'Continue your queue (1 left)', next: the one still to do",
       d.btn_queue.isVisible() and d.btn_queue.text() == "Continue your queue (1 left)" and
       Path(QUEUE[3]).name in d.btn_queue.sub_text() and d.tabs.tabText(1) == "Queue (1 left)",
       d.btn_queue.text())
    d.btn_queue.click()
    ok("B ... clicking it asks app.py to open that movie (no run) and closes",
       d.open_request == {"nd2": QUEUE[3], "run": None} and d.result() == QDialog.Accepted
       and d.source is None)

    d = SU.SetupDialog()
    d.show()
    pump(0.2)
    asked = []
    d._ask_queue = lambda n_todo, n_new: asked.append((n_todo, n_new)) or "add"
    d.choose_movies(QUEUE[4:6])
    ok("B choosing more while the queue has movies to do asks; 'Add' adds them",
       asked == [(1, 2)] and [it["nd2"] for it in batchqueue.items()] == QUEUE[:6]
       and d.experiment.nd2_path == QUEUE[4])
    d._ask_queue = lambda n_todo, n_new: "new"
    d.choose_movies(QUEUE[6:8])
    ok("B ... 'Start a new queue' replaces it", [it["nd2"] for it in batchqueue.items()]
       == QUEUE[6:8])
    d._ask_queue = lambda n_todo, n_new: ""
    d.choose_movies(QUEUE[0:2])
    ok("B ... Cancel changes nothing", [it["nd2"] for it in batchqueue.items()] == QUEUE[6:8])
    d.tree_queue.setCurrentItem(d.tree_queue.topLevelItem(0))
    d.btn_q_remove.click()
    ok("B Remove takes the selected movie out", [it["nd2"] for it in batchqueue.items()]
       == QUEUE[7:8] and d.tree_queue.topLevelItemCount() == 1)
    d.btn_q_clear.click()
    ok("B Clear empties the queue; the queue choice disappears",
       batchqueue.items() == [] and not d.btn_queue.isVisible()
       and not d.btn_q_open.isEnabled())
    d.choose_movies([QUEUE[2]])
    ok("B one movie only: shown for checking, the queue is not touched",
       batchqueue.items() == [] and d.experiment.nd2_path == QUEUE[2])
    d.tree_queue.clear()
    batchqueue.set_items(QUEUE[:2])
    d._refresh_queue()
    d.tree_queue.setCurrentItem(d.tree_queue.topLevelItem(1))
    d.btn_q_open.click()
    ok("B Open on a queued movie asks for that movie", d.open_request ==
       {"nd2": QUEUE[1], "run": None})
    from peterpiper.gui import batchdlg
    got = {}

    class FakeBatch:
        def __init__(self, s, parent=None, paths=()):
            got["paths"] = list(paths)

        def exec(self):
            return 0
    real_b = batchdlg.BatchDialog
    batchdlg.BatchDialog = FakeBatch
    try:
        d2 = SU.SetupDialog()
        d2._more_actions["batch"].trigger()
        d2.reject()
    finally:
        batchdlg.BatchDialog = real_b
    ok("B More > Batch analyse (automatic) starts with the queue's movies still to do",
       got.get("paths") == QUEUE[:2], str(got))
    bd = batchdlg.BatchDialog(load_settings()[0], None, paths=QUEUE[:3])
    ok("B the batch window lists the movies it was given",
       [bd.files.item(i).text() for i in range(bd.files.count())] == QUEUE[:3])
    bd.close()
    batchqueue.clear()


# ======================================================================== C
def part_c():
    s, _ = load_settings()
    s.seg_timepoint, s.baseline_timepoint, s.ref_channel = 99, 50, 7
    save_settings(s)
    src, exp, st = SU.prepare(GOOD)
    ok("C prepare(): a good movie opens - OUTPUT_<movie>/<user>, the file's numbers and "
       "channel names, position 1",
       exp.out_dir == users.output_dir(GOOD) and exp.out_dir.endswith(ME) and
       exp.um_per_px == 0.5 and exp.seconds_per_frame == 30.0 and
       exp.channels == ["Cy5", "GFP", "mCherry"] and src.position == 0
       and exp.n_timepoints == 12 and exp.export_tiffs is False, exp.out_dir)
    ok("C ... the saved settings made valid for the movie",
       st.seg_timepoint == 12 and st.baseline_timepoint == 12 and st.ref_channel == 2)
    ok("C ... the first frame is read for the analysis window, the folder remembered",
       getattr(src, "_pd4_first", None) is not None and
       load_settings()[1].get("last_out") == exp.out_dir)
    for name, path, word in (("a missing pixel size", NO_UM, "pixel size"),
                             ("frame interval 0", NO_SPF, "frame interval"),
                             ("uneven gaps", GAPS, "uneven"),
                             ("several stage positions", MULTI, "stage positions"),
                             ("a channel name that cannot be a sheet name", BADCH, "Channel name")):
        n0 = len(OPENED)
        try:
            SU.prepare(path, run="r.npz")
            res = None
        except SU.NeedsCheck as nc:
            res = nc
        ok(f"C ... {name}: NeedsCheck says why, the file is closed again",
           res is not None and word in res.text and res.nd2 == path and res.run == "r.npz"
           and len(OPENED) == n0 + 1 and OPENED[-1].closed, res.text if res else "no NeedsCheck")
    try:
        SU.prepare(str(MOVIES / "not there.nd2"))
        ok("C a missing movie raises", False)
    except FileNotFoundError as exc:
        ok("C a missing movie raises, in words", "not there" in str(exc))

    real_fp = SU.folder_problem
    fb = users.fallback_output_dir(GOOD)
    SU.folder_problem = lambda p: None if str(p).startswith(str(OUT / "PeterPiper results")) \
        else "the drive is read-only"
    try:
        asked = []
        src, exp, _ = SU.prepare(GOOD, ask=lambda f, w, a: asked.append((f, w, a)) or "alt")
        ok("C an unwritable results folder asks the start screen's question; 'Save there' "
           "uses <home>/PeterPiper results/OUTPUT_<movie>/<user>",
           len(asked) == 1 and asked[0][1] == "the drive is read-only" and exp.out_dir == fb, exp.out_dir)
        n0 = len(OPENED)
        try:
            SU.prepare(GOOD, ask=lambda f, w, a: "")
            res = None
        except SU.NeedsCheck as nc:
            res = nc
        ok("C ... Cancel: NeedsCheck (the start screen opens with it), the file closed",
           res is not None and "results folder" in res.text and OPENED[-1].closed
           and len(OPENED) == n0 + 1)
    finally:
        SU.folder_problem = real_fp

    note = "The gaps between timepoints are uneven (timepoint 1 \u2192 2: 1 h 0 min)."
    d = SU.SetupDialog(preload=GAPS, note=note, run="earlier_ROIs.npz")
    d.show()
    pump(0.4)
    ok("C the start screen opened with a movie that needs a look shows it and why",
       d.experiment is not None and d.experiment.nd2_path == GAPS and d.lbl_check.isVisible()
       and note in d.lbl_check.text() and d.lbl_gaps.isVisible())
    d.grab().save(str(SHOTS / "start_needs_check.png"))
    d.sp_int.setValue(31.0)
    d._accept()
    ok("C ... Open: the checked numbers are used and the run asked for is passed on",
       d.result() == QDialog.Accepted and d.result_tuple[1].seconds_per_frame == 31.0 and
       d.open_run == "earlier_ROIs.npz" and d.open_request is None)
    d.source.close()
    d = SU.SetupDialog(preload=GAPS, note=note, run="earlier_ROIs.npz")
    d.show()
    pump(0.4)
    d._load(GOOD)
    ok("C ... choosing another movie there forgets that run and the note",
       d.open_run is None and not d.lbl_check.isVisible())
    d.cmb_pos.clear()
    d._load(MULTI)
    ok("C a multi-position movie: the position choice is shown (2 positions)",
       d.cmb_pos.isVisible() and d.cmb_pos.count() == 2)
    d.cmb_pos.setCurrentIndex(1)
    d._accept()
    ok("C ... position 2 chosen: the source uses it, the first frame read again later",
       d.result_tuple[0].position == 1 and d.result_tuple[0]._pd4_first is None)
    d.reject()


# ======================================================================== D
class FakeDlg:
    def __init__(self, accepted=True, req=None, tup=(None, None, None), switch=False, run=None):
        self.accepted, self.open_request, self.result_tuple = accepted, req, tup
        self.switch_user, self.open_run = switch, run


class FakeWin:
    def __init__(self, nxt=None, go_back=False):
        self.next_request, self.go_back = nxt, go_back


class FakeUI:
    def __init__(self, starts, windows, prep, pick=True):
        self.starts, self.windows, self.prep, self.pick = list(starts), list(windows), prep, pick
        self.log = []

    def start(self, preload):
        self.log.append(("start", preload))
        d = self.starts.pop(0)
        return d, d.accepted

    def prepare(self, nd2):
        self.log.append(("prepare", nd2))
        r = self.prep[nd2]
        if isinstance(r, BaseException):
            raise r
        return r

    def analyse(self, src, exp, s, run):
        self.log.append(("analyse", exp, run))
        return self.windows.pop(0), 7

    def pick_user(self):
        self.log.append(("pick_user",))
        return self.pick

    def error(self, title, text):
        self.log.append(("error", title))


def part_d():
    from peterpiper import app as A
    T = ("srcA", "expA", "s")
    ui = FakeUI(starts=[FakeDlg(tup=T), FakeDlg(tup=("srcC", "expC", "s"), run=None)],
                windows=[FakeWin(nxt={"nd2": "B.nd2", "run": None}),
                         FakeWin(nxt={"nd2": "C.nd2", "run": None}), FakeWin()],
                prep={"B.nd2": ("srcB", "expB", "s"),
                      "C.nd2": SU.NeedsCheck("C.nd2", ["The pixel size was not found."])})
    code = A.run_loop(ui)
    ok("D Next movie: the next movie opens directly (no start screen); one that needs a "
       "look opens the start screen with it; closing ends with the window's code",
       ui.log == [("start", None), ("analyse", "expA", None), ("prepare", "B.nd2"),
                  ("analyse", "expB", None), ("prepare", "C.nd2"),
                  ("start", {"nd2": "C.nd2", "note": "The pixel size was not found.", "run": None}),
                  ("analyse", "expC", None)] and code == 7, str(ui.log))

    ui = FakeUI(starts=[FakeDlg(req={"nd2": "A.nd2", "run": "A_ROIs.npz"}), FakeDlg(accepted=False)],
                windows=[FakeWin(go_back=True)], prep={"A.nd2": T})
    code = A.run_loop(ui)
    ok("D Open on a recent analysis: that movie opens directly with its run; Choose "
       "another file comes back to the start screen; closing it ends (0)",
       ui.log == [("start", None), ("prepare", "A.nd2"), ("analyse", "expA", "A_ROIs.npz"),
                  ("start", None)] and code == 0, str(ui.log))

    ui = FakeUI(starts=[FakeDlg(req={"nd2": "A.nd2", "run": "A_ROIs.npz"}), FakeDlg(tup=T, run="A_ROIs.npz")],
                windows=[FakeWin()],
                prep={"A.nd2": SU.NeedsCheck("A.nd2", ["Check it."], "A_ROIs.npz")})
    A.run_loop(ui)
    ok("D ... a run asked for, whose movie needs a look: the start screen gets it, and "
       "it is loaded after Open", ui.log[2] == ("start", {"nd2": "A.nd2", "note": "Check it.",
                                                          "run": "A_ROIs.npz"})
       and ui.log[3] == ("analyse", "expA", "A_ROIs.npz"), str(ui.log))

    ui = FakeUI(starts=[FakeDlg(accepted=False, switch=True), FakeDlg(accepted=False)],
                windows=[], prep={})
    ok("D Switch user: the user is asked, then the start screen again",
       A.run_loop(ui) == 0 and [e[0] for e in ui.log] == ["start", "pick_user", "start"])
    ui = FakeUI(starts=[FakeDlg(accepted=False, switch=True)], windows=[], prep={}, pick=False)
    ok("D ... nobody chosen: the app ends", A.run_loop(ui) == 0 and
       [e[0] for e in ui.log] == ["start", "pick_user"])
    ui = FakeUI(starts=[FakeDlg(tup=T), FakeDlg(accepted=False)],
                windows=[FakeWin(nxt={"nd2": "bad.nd2", "run": None})],
                prep={"bad.nd2": OSError("cannot read")})
    A.run_loop(ui)
    ok("D a movie that cannot be read: said, then the start screen",
       [e[0] for e in ui.log] == ["start", "analyse", "prepare", "error", "start"], str(ui.log))
    ok("D request_of: next_request wins, cleaned; nothing -> None",
       A.request_of(types.SimpleNamespace(next_request={"nd2": "x", "run": ""},
                                          open_request={"nd2": "y"})) == {"nd2": "x", "run": None}
       and A.request_of(types.SimpleNamespace(next_request=None)) is None
       and A.request_of(types.SimpleNamespace(open_request={"nd2": ""})) is None)

    calls = []
    new = types.SimpleNamespace(load_run_file=lambda p: calls.append(("new", p)),
                                _load_roi_file=lambda p: calls.append(("old", p)))
    old = types.SimpleNamespace(_load_roi_file=lambda p: calls.append(("old", p)))
    ok("D load_run: load_run_file when the window has it, else _load_roi_file",
       A.load_run(new, "a.npz") == "load_run_file" and A.load_run(old, "b.npz") ==
       "_load_roi_file" and calls == [("new", "a.npz"), ("old", "b.npz")])

    class BusyWin(QWidget):
        def __init__(self):
            super().__init__()
            self.n, self.loaded = 0, []

        def _busy_now(self):
            self.n += 1
            return self.n < 3

        def load_run_file(self, p):
            self.loaded.append(p)
    bw = BusyWin()
    bw.show()
    A.load_run_when_ready(bw, "c.npz", delay_ms=20)
    pump(0.4)
    ok("D ... after the window is shown, once it is not busy any more",
       bw.loaded == ["c.npz"] and bw.n == 3, f"{bw.loaded} {bw.n}")
    bw.close()

    # the real analysis window through _QtUI.analyse (exec replaced: closes it)
    sys.path.insert(0, str(HERE))
    import synthmovie
    from peterpiper.gui import clickwin as CW
    CW.ClickWindow._ask_previous_run = lambda self, runs, menu=False: None
    src, exp = synthmovie.load(OUT / "synth_results")
    loaded = []
    real_load = CW.ClickWindow._load_roi_file
    CW.ClickWindow._load_roi_file = lambda self, p: loaded.append(p)

    class FakeApp:
        def exec(self):
            pump(1.5)
            for w in QApplication.topLevelWidgets():
                if isinstance(w, CW.ClickWindow) and w.isVisible():
                    w.next_request = {"nd2": "next.nd2", "run": None}
                    w.close()
            return 0
    try:
        win, code = A._QtUI(FakeApp(), lambda: True).analyse(src, exp, load_settings()[0],
                                                              "saved_ROIs.npz")
    finally:
        CW.ClickWindow._load_roi_file = real_load
    ok("D the real analysis window opens through the loop and the run is loaded into it "
       "(load_run_file, or _load_roi_file before part mainwin)",
       isinstance(win, CW.ClickWindow) and code == 0 and
       (loaded == ["saved_ROIs.npz"] or hasattr(win, "load_run_file")) and
       A.request_of(win) == {"nd2": "next.nd2", "run": None}, str(loaded))

    ok("D charlotte: missing -> left out, no error", A._install_charlotte(APP) in (True, False))
    fake = types.ModuleType("peterpiper.gui.charlotte")
    got = []
    fake.install = lambda app: got.append(app)
    sys.modules["peterpiper.gui.charlotte"] = fake
    try:
        r1 = A._install_charlotte(APP)
        fake.install = lambda app: 1 / 0
        r2 = A._install_charlotte(APP)
    finally:
        del sys.modules["peterpiper.gui.charlotte"]
        import peterpiper.gui as G
        if getattr(G, "charlotte", None) is fake:
            delattr(G, "charlotte")
    ok("D ... installed with the app when there; an error in it is ignored",
       r1 is True and got == [APP] and r2 is False)


# ======================================================================== E
def part_e():
    make_run_list()
    rec = SU.recent_analyses(8)
    names = [r["nd2_name"] for r in rec]
    ok("E recent analyses: the newest 8 of mine, one per movie, newest first",
       names == ["away.nd2"] + [f"cells {i:02d}.nd2" for i in (9, 8, 7, 6, 5, 4, 3)], str(names))
    r9 = rec[1]
    ok("E ... a movie with two runs shows its newest (the autosave)",
       r9["run"].endswith("_ROIs_2.npz") and r9["kind"] == "session" and r9["n_cells"] == 20
       and r9["movie_here"] and r9["nd2"] == str(MOVIES / "cells 09.nd2"))
    ok("E ... another user's run and a run whose file is gone are left out",
       "theirs.nd2" not in names and "gone run.nd2" not in names)
    ok("E ... a movie that is not here is marked", rec[0]["movie_here"] is False)

    d = SU.SetupDialog()
    d.show()
    pump(0.3)
    ok("E the start screen lists them (Recent analyses tab first)",
       d.tabs.currentIndex() == 0 and d.tree_recent.topLevelItemCount() == 8 and
       "not here" in d.tree_recent.topLevelItem(0).text(0))
    ok("E ... the newest one that can be opened is selected",
       d.tree_recent.currentItem() is d.tree_recent.topLevelItem(1)
       and d.btn_recent_open.isEnabled())
    d.tree_recent.setCurrentItem(d.tree_recent.topLevelItem(0))
    ok("E ... a movie that is not here cannot be opened", not d.btn_recent_open.isEnabled())
    opened = []
    real_open = W.open_path
    W.open_path = lambda p: opened.append(str(p)) or True
    try:
        d.tree_recent.setCurrentItem(d.tree_recent.topLevelItem(1))
        d.btn_recent_folder.click()
        d._load(GOOD)
        d.btn_open_out.click()
    finally:
        W.open_path = real_open
    ok("E 'Results folder' opens the run's folder; 'Open results folder' the movie's "
       "(or the nearest folder that exists)",
       opened[0] == r9["folder"] and Path(users.output_dir(GOOD)).is_relative_to(Path(opened[1]))
       and Path(opened[1]).is_dir(), str(opened))
    d.tree_recent.setCurrentItem(d.tree_recent.topLevelItem(1))
    d.btn_recent_open.click()
    ok("E 'Open in analysis window' asks app.py for that movie and run and closes",
       d.open_request == {"nd2": r9["nd2"], "run": r9["run"]} and d.result() == QDialog.Accepted
       and d.source is None)

    from peterpiper.gui import comparewin

    class FakeCompare(QDialog):
        def __init__(self, *a, **k):
            super().__init__()

        def exec(self):
            self.open_request = {"nd2": GOOD, "run": "cmp_ROIs.npz"}
            return 0
    real_cw = comparewin.CompareWindow
    comparewin.CompareWindow = FakeCompare
    try:
        d = SU.SetupDialog()
        d.btn_compare.click()
    finally:
        comparewin.CompareWindow = real_cw
    ok("E Compare closed with 'Open in analysis' on a run: passed on the same way",
       d.open_request == {"nd2": GOOD, "run": "cmp_ROIs.npz"} and d.result() == QDialog.Accepted)


# ======================================================================== F
def part_f():
    block = OUT / "a file, not a folder"
    block.write_text("x")
    bad = block / "OUTPUT_movie"
    alt = users.fallback_output_dir(str(block.parent / "movie 1.nd2"))
    d = SU.SetupDialog()
    d.experiment = types.SimpleNamespace(out_dir=str(bad), nd2_path=str(block.parent / "movie 1.nd2"))
    asked = []
    d._ask_results_folder = lambda folder, why, a: asked.append((folder, why, a)) or ""
    ok("F an unwritable results folder asks; Cancel keeps the start screen",
       d._results_folder_ok() is False and len(asked) == 1 and asked[0][2] == alt)
    d._ask_results_folder = lambda folder, why, a: "alt"
    ok("F ... 'Save the results there' uses the other place, made, and shows it",
       d._results_folder_ok() is True and d.experiment.out_dir == alt and Path(alt).is_dir()
       and d.lbl_out.text() == alt)
    d.close()

    ok("F no gui/storagedlg.py: no Storage & cloud link", d.btn_storage is None
       or "peterpiper.gui.storagedlg" in sys.modules)
    fake = types.ModuleType("peterpiper.gui.storagedlg")
    got = []
    fake.open_storage_dialog = lambda parent: got.append(parent)
    sys.modules["peterpiper.gui.storagedlg"] = fake
    try:
        d = SU.SetupDialog()
        d.show()
        pump(0.1)
        d.btn_storage.click()
    finally:
        del sys.modules["peterpiper.gui.storagedlg"]
    ok("F with it: the Storage & cloud link opens it", got == [d] and d.btn_storage.isVisible())
    d.reject()


GOOD = movie("good movie.nd2", um=0.5, spf=30.0)
NO_UM = movie("no pixel size.nd2", um=1.0)
NO_SPF = movie("no interval.nd2", spf=0.0)
GAPS = movie("uneven gaps.nd2", gap=3600.0)
MULTI = movie("two positions.nd2", n_pos=2)
BADCH = movie("bad channel.nd2", channels=["GFP/1", "Cy5"])
WORST = movie("a movie with a rather long name to see how it is shortened - "
              "replicate 3 dish 2 day 14.nd2", um=1.0, gap=3600.0, n_pos=3,
              channels=["Cy5", "GFP", "mCherry", "DAPI"])
QUEUE = [movie(f"queued movie {i}.nd2") for i in range(1, 9)]


def main():
    make_run_list()
    # D last: it opens the real analysis window, whose own text scaling follows
    for part in (part_a, part_b, part_c, part_e, part_f, part_g, part_d):
        try:
            part()
        except Exception as exc:                                   # noqa: BLE001
            import traceback
            traceback.print_exc()
            ok(f"{part.__name__} ran without an error", False, repr(exc))
    print(f"\n{N[0]} / {N[0] + len(FAILS)} checks passed")
    for f in FAILS:
        print("  FAILED:", f)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
