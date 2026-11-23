"""
Developer test (not shipped): PeterPiper 1.2, part "progress" - every loading window
shows a bar with the percent, the time left (or the time so far), and a detail line
naming what is being looked at.

    PYTHONIOENCODING=utf-8 MPLBACKEND=Agg QT_QPA_PLATFORM=offscreen \
        QT_QPA_FONTDIR=C:/Windows/Fonts python dev_tests/test_v12_progress.py

Uses the small synthetic movie shipped with the code (dev_tests/synthmovie.py) and
made-up folders only. Screenshots: <repo>/_out/shots/v12_progress_*.png.

A) the time-left estimate (widgets.TimeLeft, a fake clock): nothing in the first
   second, "x s so far" when no fraction is known, "estimating time left..." until
   there is enough progress, then "about ... left" that counts down between reports,
   does not jump on uneven progress, and restarts when the fraction goes back.
B) the 'working' window (BusyPanel): the percent on the bar, the time left after some
   progress, the text and the detail line (third argument, or after a line break), a
   long path shortened in the middle (drive and file name kept, the whole path in the
   tooltip) without the window growing or passing the screen; a drive root's title is
   not empty (place_name); an empty title says "Working..."; the old two-argument
   progress(fraction, text) and busy.step(i, n, text) still work; a call with only a
   fraction keeps the text.
C) the analysis window's strip (ProgressStrip): percent, detail, time, a moving bar
   for an unknown fraction (None or -1), reset / finish; workers.Job.progress sends
   None as -1 and the detail after a line break.
D) real callers send fractions and details: history.find_runs_in_folder on a made-up
   folder tree (fractions from 0 to 1, never going back, each folder and file named);
   Compare's "Find my runs in a folder" (title with the folder, never empty for a drive
   root; fractions; details); the analysis window's AUTO-DETECT, TRACK and export on the
   synthetic movie (captured at ProgressStrip.update: fractions, "timepoint i of n",
   each file written); a saved run read back through the bar (_load_roi_file);
   history.find_previous_runs and the start screen's recent analyses with progress;
   save_graph_files names each file; compare.save names each file.
E) screenshots of the working window and the analysis window's strip mid-progress.
"""
from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
OUT = REPO / "_out" / "v12_progress"
SHOTS = REPO / "_out" / "shots"
shutil.rmtree(OUT, ignore_errors=True)
OUT.mkdir(parents=True)
SHOTS.mkdir(parents=True, exist_ok=True)
os.environ["PETERPIPER_HOME"] = str(OUT / "home")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault("MPLCONFIGDIR", str(OUT / "home" / "mpl"))
sys.path.insert(0, str(REPO / "app"))
sys.path.insert(0, str(HERE))

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox  # noqa: E402

APP = QApplication(sys.argv)
BOXES = []
for _n in ("information", "warning", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: (BOXES.append(a), QMessageBox.Ok)[1]))
setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.No))
QMessageBox.exec = lambda self: (BOXES.append(self.text()), 0)[1]    # never waits

import numpy as np                                                    # noqa: E402

import synthmovie as SM                                               # noqa: E402
from peterpiper import history                                        # noqa: E402
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
    while (w._busy_now() or w.bg_busy() or w.retracking()):
        APP.processEvents()
        time.sleep(0.02)
    pump(0.3)


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def shot(widget, name):
    p = SHOTS / f"v12_progress_{name}.png"
    widget.grab().save(str(p))
    SHOT_FILES.append(str(p))
    return p


W.base_font_pt()
TH.apply(APP, "midnight", max(10.0, W.base_font_pt() + 1.0))
LONG = ("C:/" + "/".join(f"a rather long folder name {i}" for i in range(12))
        + "/the_movie_of_the_day_ROIs.npz")


# ===================================================================== A
def part_a():
    c = Clock()
    e = W.TimeLeft(clock=c)
    ok("A nothing said in the first second", e.text() == "")
    c.t += 12
    e.feed(None)
    ok("A no fraction known: the time so far", e.text() == "12 s so far", e.text())
    e.restart()
    c.t += 0.5
    e.feed(0.01)
    ok("A too little progress: estimating", e.text() == "estimating time left...", e.text())
    c.t += 9.5
    e.feed(0.25)                                    # 10 s for a quarter: 30 s left
    ok("A after some progress: about 30 s left", e.text() == "about 30 s left", e.text())
    c.t += 5
    ok("A it counts down between reports", e.text() == "about 25 s left", e.text())
    lefts, f = [], 0.25
    for i in range(1, 21):                          # uneven progress: steady estimate
        c.t += 1
        f += 0.03 if i % 2 else 0.0                 # bursts, then nothing
        e.feed(f)
        lefts.append(e.seconds_left())
    jumps = max(abs(a - b) for a, b in zip(lefts, lefts[1:]))
    ok("A uneven progress does not make it jump (steps under 4 s)", jumps < 4.0,
       f"{jumps:.1f} s")
    ok("A minutes are written out", W.fmt_duration(80) == "1 min 20 s"
       and W.fmt_duration(3900) == "1 h 5 min" and W.fmt_duration(120) == "2 min")
    e2 = W.TimeLeft(clock=c)
    c.t += 30
    e2.feed(0.5)
    c.t += 30
    e2.feed(0.9)
    e2.feed(0.1)                                    # a new part of the work
    ok("A a fraction going back restarts the estimate",
       e2.text() == "estimating time left...", e2.text())
    e2.feed(1.0)
    ok("A at the end: almost done", e2.text() == "almost done", e2.text())


# ===================================================================== B
def part_b():
    p = W.BusyPanel(None, f"Looking for your runs in {W.place_name('D:' + chr(92))}")
    ok("B a drive root's name is never empty", W.place_name("D:\\") == "D:\\"
       and W.place_name("E:/") == "E:/" and W.place_name("C:/data/runs") == "runs")
    ok("B ... so the title ends with the drive",
       p.lbl_title.text() == "Looking for your runs in D:\\", p.lbl_title.text())
    p_empty = W.BusyPanel(None, "  ")
    ok("B an empty title says Working...", p_empty.lbl_title.text() == "Working...")
    p_empty.deleteLater()
    c = Clock()
    p.eta = W.TimeLeft(clock=c)
    p.appear()
    pump(0.1)
    w0 = p.width()
    scr = APP.primaryScreen().availableGeometry().width()
    p.update_progress(None, "Checking folders")
    ok("B no fraction yet: a moving bar", p.bar.maximum() == 0 and not p.bar.isTextVisible())
    c.t += 3
    p.update_progress(None, "Checking folders")
    ok("B ... and the time so far", p.lbl_time.text() == "3 s so far", p.lbl_time.text())
    c.t += 1
    p.update_progress(0.0, "Reading your saved runs", detail="run 1 of 80 - C:/x/a.npz")
    c.t += 8
    p.update_progress(0.2, "Reading your saved runs", detail="run 17 of 80 - " + LONG)
    ok("B a fraction: the bar shows the percent", p.bar.maximum() == 1000 and
       p.bar.isTextVisible() and p.bar.text() == "20%", p.bar.text())
    ok("B the time left after some progress", p.lbl_time.text().startswith("about ")
       and p.lbl_time.text().endswith(" left"), p.lbl_time.text())
    ok("B the text and the detail line", p.lbl.text() == "Reading your saved runs"
       and p.lbl_detail.text().startswith("run 17 of 80 - C:/"))
    pump(0.1)
    shown = p.lbl_detail.shown_text()
    ok("B a long path is shortened in the middle", p.lbl_detail.is_elided()
       and "…" in shown and shown.startswith("run 17 of 80 - C:/")
       and shown.endswith("ROIs.npz"), shown)
    ok("B ... the whole path in the tooltip", LONG in p.lbl_detail.toolTip())
    ok("B the window does not grow, and fits the screen", p.width() == w0 and
       p.width() <= scr and p.lbl_detail.width() <= p.width(), f"{w0} -> {p.width()}, {scr}")
    p.update_progress(0.3, "Adding your runs\nrun 2 of 5 - C:/x/b.npz")
    ok("B the detail may follow a line break", p.lbl.text() == "Adding your runs"
       and p.lbl_detail.text() == "run 2 of 5 - C:/x/b.npz")
    p.update_progress(0.35, "Next step")
    ok("B a new text without a detail clears the old detail", p.lbl_detail.text() == "")
    p.close()
    # the old two-argument form, through the real background runner
    seen, args = [], []
    orig = W.BusyPanel.update_progress

    def cap(self, fraction, text="", detail=None):
        args.append((fraction, text, detail))
        return orig(self, fraction, text, detail)
    W.BusyPanel.update_progress = cap
    try:
        def slow(progress):
            progress(0.5, "half way")
            time.sleep(0.5)
            progress(0.6)                         # only a fraction: the text stays
            time.sleep(0.5)
            seen.extend(w for w in APP.topLevelWidgets()
                        if isinstance(w, W.BusyPanel) and w.isVisible())
            return 42
        got = W.run_with_progress(None, "Testing", slow)
    finally:
        W.BusyPanel.update_progress = orig
    ok("B the old progress(fraction, text) still works", got == 42 and seen and
       seen[0].lbl.text() == "half way" and seen[0].bar.value() == 600,
       f"{[s.lbl.text() for s in seen]} {seen[0].bar.value() if seen else None}")
    ok("B ... passed on as (fraction, text, no detail)", (0.5, "half way", None) in args,
       str(args[:3]))
    with W.busy(None, "Steps") as b:
        b.step(1, 4, "one of four")
        v1 = b.panel.bar.value() == 250 and b.panel.lbl.text() == "one of four"
        b.step(2, 4, "two of four", "file 2 of 4 - C:/x/two.nd2")
        v2 = b.panel.lbl_detail.text() == "file 2 of 4 - C:/x/two.nd2"
    ok("B busy.step: old and new forms", v1 and v2)


# ===================================================================== C
def part_c():
    s = W.ProgressStrip()
    s.resize(900, 60)
    s.show()
    c = Clock()
    s.eta = W.TimeLeft(clock=c)
    s.reset("Tracking...")
    s.update(0.0, "Following and redrawing 16 cells\ntimepoint 1 of 12 (0 done)")
    c.t += 6
    s.update(0.25, "Following and redrawing 16 cells\ntimepoint 3 of 12 (3 done)")
    ok("C strip: percent, text, detail", s.bar.text() == "25%" and
       s.msg.text() == "Following and redrawing 16 cells" and
       s.detail.text() == "timepoint 3 of 12 (3 done)", f"{s.bar.text()} {s.msg.text()}")
    ok("C strip: the time left", s.lbl_time.text() == "about 20 s left", s.lbl_time.text())
    s.update(-1.0, "Looking", "folder C:/x")
    ok("C strip: -1 = unknown: a moving bar", s.bar.maximum() == 0)
    s.busy("Finding an empty background area...", detail="12 timepoints")
    ok("C strip: busy() with a detail", s.bar.maximum() == 0 and s.detail.text() == "12 timepoints")
    s.reset("Ready.")
    ok("C strip: reset clears the detail and the time", s.bar.maximum() == 1000
       and s.detail.text() == "" and s.lbl_time.text() == "" and s.msg.text() == "Ready.")
    c.t += 65
    s.finish("Done: 3 file(s)")
    ok("C strip: finish says how long it took", s.bar.value() == 1000
       and s.lbl_time.text() == "took 1 min 5 s", s.lbl_time.text())
    s.close()
    from peterpiper.gui.workers import Job
    j = Job()
    em = []
    j.progressed.connect(lambda f, m: em.append((f, m)))
    j.progress(None, "Looking", detail="C:/x")
    j.progress(0.5, "Half")
    ok("C Job.progress: None as -1, the detail after a line break, old form",
       em == [(-1.0, "Looking\nC:/x"), (0.5, "Half")], str(em))


# ===================================================================== D
def make_tree() -> Path:
    root = OUT / "tree"
    for a in ("alpha", "beta", "gamma"):
        for b in ("one", "two"):
            d = root / a / b / "deep"
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{a}_{b}_ROIs.npz").write_bytes(b"not a real run")
    (root / "$RECYCLE.BIN").mkdir(exist_ok=True)
    return root


def mono(fr):
    fr = [f for f in fr if f is not None and f >= 0]
    return all(b >= a - 1e-9 for a, b in zip(fr, fr[1:]))


def part_d_history():
    root = make_tree()
    cap = []
    got = history.find_runs_in_folder(root, lambda f, t: cap.append((f, t)) or True)
    fr = [f for f, _t in cap]
    ok("D folder search: fractions from 0, never going back, below 1",
       fr and fr[0] == 0.0 and mono(fr) and max(fr) < 1.0 and max(fr) > 0.5,
       f"{fr[:3]} ... {fr[-3:]}")
    dets = [W.split_progress(t)[1] or "" for _f, t in cap]
    ok("D folder search: each folder named in the detail",
       any(str(root / "beta" / "two" / "deep") in d for d in dets)
       and all(d for d in dets), dets[-1])
    ok("D folder search: each file named", any("gamma_one_ROIs.npz" in d for d in dets))
    ok("D folder search: the result is unchanged", got == dict(mine=[], others=0, untracked=0),
       str(got))
    # Compare's "Find my runs in a folder": the real caller, through a recording runner
    from peterpiper.gui.comparewin import CompareWindow
    import peterpiper.gui.comparewin as CWm
    CompareWindow.ASK_UNKNOWN = False
    cw = CompareWindow()
    rec = []
    orig_rwp = W.run_with_progress

    def fake_rwp(parent, title, fn, delay_ms=350):
        calls = []

        def progress(fraction=None, text="", detail=None):
            calls.append((fraction, text, detail))
            return True
        rec.append((title, calls))
        return fn(progress)
    W.run_with_progress = fake_rwp
    orig_dir = QFileDialog.getExistingDirectory
    try:
        QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: str(root))
        cw._find_in_folder()
        title, calls = rec[-1]
        ok("D Compare 'Find my runs': the title names the folder",
           title == f"Looking for your runs in {root.name}", title)
        fr = [c[0] for c in calls]
        ok("D Compare 'Find my runs': fractions, never going back",
           fr and all(f is not None for f in fr) and mono(fr), str(fr[:4]))
        ok("D Compare 'Find my runs': details name the folders",
           any(str(root / "alpha") in (W.split_progress(t, d)[1] or "") for _f, t, d in calls))
        # a drive root: never an empty title (the work itself not run here)
        W.run_with_progress = lambda parent, title, fn, delay_ms=350: (
            rec.append((title, [])), dict(mine=[], others=0, untracked=0))[1]
        QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: "D:\\")
        cw._find_in_folder()
        ok("D Compare 'Find my runs' on a drive root: the title ends with the drive",
           rec[-1][0] == "Looking for your runs in D:\\", rec[-1][0])
    finally:
        W.run_with_progress = orig_rwp
        QFileDialog.getExistingDirectory = orig_dir
        cw.close()
    ok("D comparewin uses the shared helper", CWm.W is W)


def place_background(w):
    w.background = background_from_outline([(205, 20), (250, 20), (250, 170), (205, 170)],
                                           (SM.H, SM.W))
    w._bg_auto, w._bg_kind = False, "hand"


def part_d_window():
    from peterpiper.gui.clickwin import ClickWindow
    ClickWindow._ask_previous_run = lambda self, runs, **k: None
    d = OUT / "data"
    d.mkdir(parents=True, exist_ok=True)
    src, exp = SM.load(d / "OUTPUT_made_up_movie" / "results")
    exp.nd2_path = str(d / "made_up_movie.nd2")
    Path(exp.out_dir).mkdir(parents=True, exist_ok=True)
    Path(exp.nd2_path).write_bytes(b"stands in for a movie " * 40)
    cap = []
    orig = W.ProgressStrip.update

    def rec(self, fraction, message="", detail=None):
        cap.append((fraction, message, detail))
        return orig(self, fraction, message, detail)
    W.ProgressStrip.update = rec
    try:
        w = ClickWindow(src, exp, Settings(baseline_timepoint=2))
        w._paths_ok = lambda *a, **k: True
        w.resize(1600, 960)
        w.show()
        t0 = time.time()
        while not w._offered and time.time() - t0 < 30:
            pump(0.1)
        pump(0.3)
        w._goto_step(0, user=True)
        n0 = len(cap)
        w._auto_select()
        wait(w)
        auto = cap[n0:]
        ok("D AUTO-DETECT: fractions and a detail (blob / cell i of n)",
           auto and mono([a[0] for a in auto]) and
           any(" of " in (W.split_progress(m, dd)[1] or "") for _f, m, dd in auto),
           str(auto[-2:]))
        place_background(w)
        w.cmb_comp.setCurrentIndex(w.cmb_comp.findData("nucleus"))
        n1 = len(cap)
        w._track()
        wait(w)
        trk = cap[n1:]
        dets = [W.split_progress(m, dd) for _f, m, dd in trk]
        ok("D TRACK: a fraction per timepoint, going up to 1",
           len(trk) >= SM.T and mono([t[0] for t in trk]) and trk[-1][0] == 1.0,
           str([t[0] for t in trk][-3:]))
        ok("D TRACK: 'timepoint i of n' in the detail, no inline estimate",
           any(dt == f"timepoint {SM.T} of {SM.T} ({SM.T} done)" for _h, dt in dets)
           and not any("s left" in h for h, _d in dets), str(dets[-1]))
        path = w._save_rois(silent=True)
        pump(0.3)
        comps = w._export_data()
        n2 = len(cap)
        # 4.0: an export normally runs in the background (task list); as in Batch
        # analysis it can run in the window, where its bar is checked here
        w.export_in_background = False
        w._run_export(comps, ["nucleus|csv", "nucleus|excel"])
        wait(w)
        exp_cap = cap[n2:]
        dets = [W.split_progress(m, dd)[1] or "" for _f, m, dd in exp_cap]
        ok("D export: fractions, never going back", exp_cap and
           mono([e[0] for e in exp_cap]), str([round(e[0], 2) for e in exp_cap][:8]))
        ok("D export: the workbook is named while it is written",
           any(d.endswith(".xlsx") and "sheet step" in d for d in dets), dets[:2])
        ok("D export: each step names the file written",
           any(".csv" in d and "step " in d for d in dets), dets[-1])
        # a saved run read back through the bar
        n_cells = len(w.cells)
        w._dirty = False
        w.close()
        pump(0.3)
        src2, exp2 = SM.load(d / "OUTPUT_made_up_movie" / "results")
        exp2.nd2_path = exp.nd2_path
        w2 = ClickWindow(src2, exp2, Settings(baseline_timepoint=2))
        w2._paths_ok = lambda *a, **k: True
        w2.show()
        t0 = time.time()
        while not w2._offered and time.time() - t0 < 30:
            pump(0.1)
        w2._load_roi_file(path)
        pump(0.3)
        ok("D a saved run is read back through the bar (ROIs and tracking)",
           w2.track is not None and len(w2.cells) == n_cells, f"{len(w2.cells)} {n_cells}")
        # the strip mid-progress (as during tracking), for the screenshot
        c = Clock()
        w2.progress.eta = W.TimeLeft(clock=c)
        w2.progress.reset("Following...")
        w2.progress.update(0.0, "Following and redrawing 16 cells")
        c.t += 9
        w2.progress.update(0.42, f"Following and redrawing 16 cells\ntimepoint 5 of 12 "
                                 f"(5 done) - {exp2.nd2_path}")
        pump(0.2)
        ok("D the strip mid-progress: percent, time left, detail",
           w2.progress.bar.text() == "42%" and w2.progress.lbl_time.text().startswith("about")
           and "timepoint 5 of 12" in w2.progress.detail.text(), w2.progress.lbl_time.text())
        ok("D the strip does not widen the window", w2.width() <= 1600 + 1, str(w2.width()))
        shot(w2, "analysis_window_strip")
        w2.progress.reset("Ready.")
        w2._dirty = False
        w2.close()
        pump(0.2)
    finally:
        W.ProgressStrip.update = orig
    # earlier analyses with progress (the start screen / analysis window caller)
    cap2 = []
    runs = history.find_previous_runs(exp.nd2_path, exp.out_dir, (SM.H, SM.W), SM.T,
                                      progress=lambda f, t: cap2.append((f, t)) or True)
    ok("D earlier analyses: found as before", any(Path(r.path) == Path(path) for r in runs))
    dets = [W.split_progress(t)[1] or "" for _f, t in cap2]
    ok("D earlier analyses: fractions and details (the movie, each folder, each file)",
       mono([f for f, _t in cap2]) and dets and exp.nd2_path in dets[0]
       and any(d.startswith("file ") and ".npz" in d for d in dets), str(dets[:3]))
    from peterpiper.gui import setup as SU
    cap3 = []

    def p3(fraction=None, text="", detail=None):
        cap3.append((fraction, text, detail))
        return True
    rec_list = SU.recent_analyses(8, progress=p3)
    ok("D recent analyses: the same list, with fractions and the runs named",
       rec_list == SU.recent_analyses(8) and cap3 and all(c[2] for c in cap3)
       and mono([c[0] for c in cap3]), str(cap3[:2]))
    return path


def part_d_add(path):
    """Compare's 'Add run file...' with several files: read in the background."""
    from peterpiper.gui.comparewin import CompareWindow
    CompareWindow.ASK_UNKNOWN = False
    cw = CompareWindow()
    junk = OUT / "tree" / "alpha" / "one" / "deep" / "alpha_one_ROIs.npz"
    rec = []
    orig_rwp, orig_open = W.run_with_progress, QFileDialog.getOpenFileNames

    def fake_rwp(parent, title, fn, delay_ms=350):
        calls = []
        rec.append((title, calls))
        return fn(lambda fraction=None, text="", detail=None: calls.append(
            (fraction, text, detail)) or True)
    W.run_with_progress = fake_rwp
    QFileDialog.getOpenFileNames = staticmethod(lambda *a, **k: ([str(path), str(junk)], ""))
    try:
        cw._add_clicked()
    finally:
        W.run_with_progress, QFileDialog.getOpenFileNames = orig_rwp, orig_open
    title, calls = rec[0] if rec else ("", [])
    ok("D Compare 'Add run file' with 2 files: a bar, each run named",
       title == "Adding 2 runs" and [c[0] for c in calls] == [0.0, 0.5]
       and calls[1][2] == f"run 2 of 2 - {junk}", f"{title} {calls}")
    ok("D ... the good run is added and read (ticked), nothing left over",
       any(Path(p) == Path(path) for p in cw._runs) and not cw._preloaded,
       f"{list(cw._runs)} {list(cw._preloaded)}")
    cw.close()


def part_d_saving():
    from peterpiper.export import save_graph_files
    cap = []
    x = np.arange(5, dtype=float)
    y = np.random.default_rng(1).random((5, 3))
    files = save_graph_files(OUT / "graphs", "made_up_graph", ["png", "svg"], x, y,
                             ["Cell_1", "Cell_2", "Cell_3"], {}, "Time (s)", "F/F0", "t",
                             "F/F0", progress=lambda f, m: cap.append((f, m)) or True)
    dets = [W.split_progress(m)[1] or "" for _f, m in cap]
    ok("D save this graph: each file named", len(files) == 2 and
       dets == [f"file 1 of 2 - {OUT / 'graphs' / 'made_up_graph'}.png",
                f"file 2 of 2 - {OUT / 'graphs' / 'made_up_graph'}.svg"], str(dets))
    from peterpiper import compare as C
    said = []
    say = C._steps(lambda f, m: said.append((f, m)), 3)
    for n in ("a.prism", "a.png", "a.xlsx"):
        say(n)
    ok("D compare.save's steps: file i of n, fractions below 1",
       [m.split("\n")[1] for _f, m in said] == ["file 1 of 3 - a.prism", "file 2 of 3 - a.png",
                                                 "file 3 of 3 - a.xlsx"]
       and [round(f, 2) for f, _m in said] == [0.0, 0.33, 0.67], str(said))


# ===================================================================== E
def part_e():
    p = W.BusyPanel(None, f"Looking for your runs in {W.place_name('D:' + chr(92))}")
    c = Clock()
    p.eta = W.TimeLeft(clock=c)
    p.update_progress(0.0, "Looking for your runs")
    c.t += 25
    p.update_progress(0.37, "2 of your runs found, 118 file(s) checked",
                      detail="folder " + LONG.rsplit("/", 1)[0])
    p.appear()
    pump(0.3)
    shot(p, "working_window")
    p.close()


def main():
    part_a()
    part_b()
    part_c()
    part_d_history()
    path = part_d_window()
    part_d_add(path)
    part_d_saving()
    part_e()
    print("screenshots:", *SHOT_FILES, sep="\n  ")
    print(f"\n{N[0]} / {N[0] + len(FAILS)} checks passed")
    if FAILS:
        print("FAILED:", *FAILS, sep="\n  ")
        sys.exit(1)


if __name__ == "__main__":
    main()
