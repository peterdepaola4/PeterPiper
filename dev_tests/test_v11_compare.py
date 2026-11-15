"""
Developer test (not shipped): PeterPiper 1.1 - the 'Compare / average runs'
window made calm and clear, 'Open in analysis', output files, which save is
which, colours readable on the graph.

    MPLBACKEND=Agg QT_QPA_PLATFORM=offscreen python dev_tests/test_v11_compare.py

Runs are made like dev_tests/test_compare_groups.py does (fake runs put into the
list; roifile.read_summary replaced where a run file's summary is read).

A) the window opens maximized; far fewer top-level buttons than 1.0 (20 then -
   counted on the 1.0 window), and every 1.0 action is still in a menu (Add runs,
   Groups, the List menu, Output files, Save's More); every attribute and
   method the older tests drive is still there.
B) no scroll bars: at 1366 x 768 and 1280 x 800 (and 1366 x 700, a maximized
   window under a title bar and the taskbar), dark and light theme, with 14 runs
   in the list: every visible scroll area (the plot settings) needs no scroll
   bar, the window's minimum size fits, the run list keeps a usable height; also
   with the 'Points' row and a problem note shown. Screenshots in _out/shots.
C) the list: 'Save' column says 'Saved: <note>' / 'Saved' / 'Autosave' /
   'Export' (+ the note in the tooltip), 'User' column, taller rows, the rare
   columns hidden by default, a column shown again is remembered.
D) 'Open in analysis' (button and double-click): open_request = {"nd2", "run"},
   openRequested(dict) emitted with the same, the window closes (accepted); a
   moved movie is found by its fingerprint in the run index or next to the run's
   OUTPUT_ folder; not found: the user is asked (the chosen file used; Cancel =
   nothing happens; a file with other contents: asked first, No = nothing).
E) 'Open results folder' opens the run's results folder (W.open_path); the output
   files list shows its exports (date, file count, this run's export marked),
   autosaves and comparisons, and Open opens the chosen one.
F) colours: the fallback palette is Okabe-Ito without its pale yellow (every
   colour >= 2:1 on the white graph) and stays distinguishable for colour-blind
   eyes (deutan / protan / tritan simulation); pale colours get a darker symbol
   edge in the live graph; the famous cell lines' first colours stay apart.
Exit code 0 = every check passed.
"""
from __future__ import annotations

import itertools
import os
import shutil
import sys
from pathlib import Path

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                                  # noqa: BLE001
    pass
HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "app"))
sys.path.insert(0, str(HERE))
OUT = REPO / "_out" / "v11_compare"
SHOTS = REPO / "_out" / "shots"
if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True)
SHOTS.mkdir(parents=True, exist_ok=True)
os.environ["PETERPIPER_HOME"] = str(OUT / "home")
os.environ.setdefault("MPLCONFIGDIR", str(OUT / "home" / "mpl"))
os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")

from peterpiper import celllines as CL                                 # noqa: E402
from peterpiper import compare as C                                    # noqa: E402
from peterpiper import graphstyle as GS                                # noqa: E402
from peterpiper import history                                         # noqa: E402
from peterpiper import roifile as RF                                   # noqa: E402

BUTTONS_V10 = 20          # visible top-level buttons of the 1.0 window (counted before 1.1)
checks = []


def ok(name, cond, extra=""):
    checks.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra else ""), flush=True)


# ------------------------------------------------------------------ helpers
FAKE = {}
SUMMARY = {}


def fake_series(label, y, sec=30, base=1, path=None):
    y = np.asarray(y, float)
    T = y.shape[0]
    run = C.Run(path=path or str(OUT / "runs" / f"{label}.npz"), label=label, nd2=f"{label}.nd2",
                baseline=base, seconds_per_frame=sec, n_timepoints=T, channels=["GFP"],
                meas={}, included={})
    steps = np.arange(T, dtype=float) - (base - 1)
    return C.Series(label=label, x=steps * sec / 60.0, y=y, x_label="Time from baseline (min)",
                    cells=list(range(y.shape[1])), run=run)


def put_fake(cw, s, summary, checked=True):
    from PySide6.QtCore import Qt
    summary = dict(summary)
    summary.setdefault("nd2", s.run.nd2)
    SUMMARY[str(s.run.path)] = dict(summary, path=str(s.run.path), tracked=True)
    cw._insert_row(s.run.path, summary)
    cw._mark_duplicates()
    cw._runs[s.run.path] = s.run
    s.run.label = cw._labels[s.run.path]
    cw._busy = True
    cw._use(s.run.path).setCheckState(Qt.Checked if checked else Qt.Unchecked)
    cw._busy = False
    FAKE[s.run.path] = s
    return s.run.path


def add(cw, label, summary=None, checked=True, seed=0, path=None):
    s = fake_series(label, 1 + np.random.default_rng(seed).random((6, 4)), path=path)
    return put_fake(cw, s, summary or {}, checked)


def ready(cw):
    if cw.cmb_comp.count() == 0:
        cw.cmb_comp.addItem("Nucleus", "nucleus")
        cw.cmb_q.addItem("F/F0 GFP")
    cw.refresh()


def pump(app, n=3):
    for _ in range(n):
        app.processEvents()


def buttons(cw):
    from PySide6.QtWidgets import QPushButton, QToolButton
    return [b for b in cw.findChildren(QPushButton) + cw.findChildren(QToolButton)
            if b.isVisible() and b.window() is cw and b.text()]


def scroll_problems(cw):
    """Every visible scroll area of the window that would need a scroll bar
    (the run list may scroll inside itself; the graph never shows bars)."""
    from PySide6.QtWidgets import QAbstractScrollArea, QGraphicsView
    bad = []
    for s in cw.findChildren(QAbstractScrollArea):
        if not s.isVisible() or s.window() is not cw or s is cw.tree or \
                isinstance(s, QGraphicsView) or s.parent() is cw.tree:
            continue
        v, h = s.verticalScrollBar().maximum(), s.horizontalScrollBar().maximum()
        if v or h:
            bad.append(f"{type(s).__name__} v={v} h={h}")
    return bad


def make_window():
    from peterpiper.gui.comparewin import CompareWindow
    CompareWindow.ASK_UNKNOWN = False
    return CompareWindow(GS.GraphStyle().to_dict())


def fill_list(cw, n=14):
    kinds = [dict(kind="saved", note="final, after drift fix"), dict(kind="session"),
             dict(kind="export"), dict(kind="saved")]
    lines = ["U2OS", "IHH", "HepG2", "HeLa", "mystery"]
    out = []
    for i in range(n):
        lab = f"{lines[i % len(lines)]} dish {i + 1}"
        s = dict(kinds[i % len(kinds)], n_cells=5 + i, user="Ana" if i % 3 else "Ben",
                 saved=f"2026-11-{1 + i % 28:02d}T10:{i:02d}:00",
                 fingerprint=dict(quick=f"fp{i // 2}", size=100 + i // 2),
                 nd2=f"movie{i // 2}.nd2")
        out.append(add(cw, lab, s, checked=i < 6, seed=i))
    cw.set_groups({p: ("U2OS ctrl" if i < 4 else "") for i, p in enumerate(out)}, ask=False)
    ready(cw)
    return out


# ---------------------------------------------------------------- A
def part_a(app):
    from PySide6.QtCore import Qt
    cw = make_window()
    try:
        ok("A opens maximized", bool(cw.windowState() & Qt.WindowMaximized))
        cw.setWindowState(Qt.WindowNoState)
        cw.resize(1366, 768)
        cw.show()
        pump(app)
        bs = buttons(cw)
        print(f"   top-level buttons: 1.0 = {BUTTONS_V10}, 1.1 = {len(bs)}: "
              f"{[b.text() for b in bs]}")
        ok(f"A fewer top-level buttons ({len(bs)} instead of {BUTTONS_V10})",
           len(bs) <= 9 and len(bs) < BUTTONS_V10, [b.text() for b in bs])

        def texts(menu):
            menu.aboutToShow.emit()
            out = []
            for a in menu.actions():
                out.append(a.text())
                if a.menu() is not None:
                    out += texts(a.menu())
            return out
        want = {
            cw.menu_add: ["Add run file...", "Find my runs in a folder...", "My data is in..."],
            cw.menu_groups: ["New group...", "Put selected runs in",
                             "Take selected runs out of their group", "Group by cell line"],
            cw.menu_list: ["Remove selected runs from the list", "Untick all",
                           "Open all folders", "Close all folders", "Columns shown"],
            cw.menu_results: ["Open results folder", "This run's output files...",
                              "Every saved file..."],
            cw.menu_save: ["Save plot settings...", "Load plot settings...", "Batch save...",
                           "Prism style templates..."],
        }
        miss = {k.title() or str(i): [t for t in v if t not in texts(k)]
                for i, (k, v) in enumerate(want.items())}
        miss = {k: v for k, v in miss.items() if v}
        g = texts(cw.menu_groups)
        ok("A every 1.0 action is in a menu (add, groups, list, outputs, save)",
           not miss and any(t.startswith("Rename group") for t in g) and
           any(t.startswith("Delete group") for t in g), miss)
        ok("A Save... stays a button of its own (the main action)",
           cw.btn_save.text() == "Save..." and cw.btn_save in bs)
        used = ["_all_groups", "_ask_save_path", "_busy", "_cells", "_combos", "_copies",
                "_delete_group", "_dups", "_gfolders", "_group_by_line", "_groups", "_hover",
                "_hover_pts", "_insert_row", "_is_on", "_items", "_labels", "_mark_duplicates",
                "_new_group", "_norm", "_paths", "_recompute", "_rename_group", "_runs",
                "_save_clicked", "_save_opts", "_save_view_prefs", "_ungroup_selected", "_use",
                "add_run_file", "cell_line_of", "chk_cells", "chk_fmt", "chk_kin",
                "chk_own_base", "chk_xerr", "chk_yerr", "chosen", "chosen_colours", "cmb_comp",
                "cmb_err", "cmb_graph", "cmb_mode", "cmb_points", "cmb_q", "current",
                "duplicate_warning", "folder_of", "groups", "hsplit", "lbl_dup", "lbl_hover",
                "lbl_info", "lbl_problem", "lbl_sentence", "legend", "mode", "pair_lines",
                "plot", "put_selected_in", "refresh", "row_x", "row_y", "row_y2", "save_to",
                "set_checked", "set_graph", "set_group_colour", "set_groups", "set_label",
                "set_mode", "sp_at", "sp_base", "spec", "style", "tree", "version_of", "vsplit",
                "wid_points", "_restore_view", "graph", "btn_put", "btn_save", "_put_menu",
                "_add_clicked", "_my_data_is_in", "_find_in_folder", "_remove_clicked",
                "_saved_files", "_templates", "_save_plot_settings", "_load_plot_settings",
                "_batch_save", "_rename_group", "lbl_missing", "lbl_warn", "btn_reset",
                "open_request", "openRequested", "open_in_analysis", "open_results_folder",
                "show_output_files", "find_movie"]
        gone = [n for n in used if not hasattr(cw, n)]
        ok("A every attribute / method the tests drive is still there (+ the 1.1 ones)",
           not gone, gone)
        ok("A the settings still sit in a scroll area under the list (test_v28's check)",
           cw.vsplit.widget(1).__class__.__name__ == "QScrollArea")
    finally:
        cw.close()


# ---------------------------------------------------------------- B
def part_b(app):
    from PySide6.QtCore import Qt
    from peterpiper.gui import theme as TH
    for theme in ("midnight", "daylight"):
        TH.apply(app, theme, 10.0)
        for w, h in ((1366, 768), (1280, 800), (1366, 700)):
            cw = make_window()
            try:
                fill_list(cw)
                cw.setWindowState(Qt.WindowNoState)
                cw.resize(w, h)
                cw.show()
                pump(app, 5)
                bad = scroll_problems(cw)
                ms = cw.minimumSizeHint()
                ok(f"B {theme} {w}x{h}: no scroll bar needed, the window's minimum fits, "
                   f"the list is usable",
                   not bad and ms.width() <= w and ms.height() <= h and
                   cw.size().width() == w and cw.size().height() == h and
                   cw.tree.viewport().height() >= 150 and
                   cw._settings_scroll.viewport().height() >=
                   cw._settings_scroll.widget().minimumSizeHint().height(),
                   (bad, ms, cw.tree.viewport().height()))
                if h != 700:
                    path = SHOTS / f"compare_{theme}_{w}x{h}.png"
                    cw.grab().save(str(path))
                    ok(f"B screenshot {path.name}", path.exists() and path.stat().st_size > 10000)
                if (w, h) == (1366, 768):
                    # the rows that appear with other choices: Points (X = a measure)
                    # and a problem note - still nothing to scroll
                    cw.lbl_points.setVisible(True)
                    cw.wid_points.setVisible(True)
                    cw.lbl_problem.setText("A long note about a plot that makes no sense, "
                                           "long enough to take two lines in the box. " * 2)
                    cw.lbl_problem.setVisible(True)
                    cw._fit_settings()
                    pump(app, 5)
                    bad = scroll_problems(cw)
                    ok(f"B {theme} 1366x768 with Points and a problem note: still no scroll "
                       f"bar", not bad and cw.tree.viewport().height() >= 120,
                       (bad, cw.tree.viewport().height()))
            finally:
                cw.close()
    TH.apply(app, "midnight", 10.0)


# ---------------------------------------------------------------- C
def part_c(app):
    from PySide6.QtCore import Qt
    from peterpiper.gui import comparewin as CW
    cw = make_window()
    try:
        P = {
            "saved": add(cw, "dish A", dict(kind="saved", note="final, after drift fix",
                                            user="Ana")),
            "saved_plain": add(cw, "dish B", dict(kind="saved", user="Ana")),
            "auto": add(cw, "dish C", dict(kind="session", user="Ben")),
            "export": add(cw, "dish D", dict(kind="export")),
        }
        ready(cw)
        got = {k: cw._cells[p][CW.COL_KIND].text() for k, p in P.items()}
        ok("C 'Save' column: Saved: note / Saved / Autosave / Export", got == {
            "saved": "Saved: final, after drift fix", "saved_plain": "Saved",
            "auto": "Autosave", "export": "Export"}, got)
        ok("C the note and what the kind means in the tooltip",
           "Your note: final, after drift fix" in cw._cells[P["saved"]][CW.COL_KIND].toolTip()
           and "Autosaved" in cw._cells[P["auto"]][CW.COL_KIND].toolTip())
        ok("C 'User' column", cw._cells[P["saved"]][CW.COL_USER].text() == "Ana" and
           cw._cells[P["auto"]][CW.COL_USER].text() == "Ben" and
           cw._cells[P["export"]][CW.COL_USER].text() == "")
        # note read from the file itself when the summary has no 'note' key
        import json
        import zipfile
        f = OUT / "runs" / "noted_ROIs.npz"
        f.parent.mkdir(parents=True, exist_ok=True)
        import io
        buf = io.BytesIO()
        np.save(buf, np.array(json.dumps({"note": "  from the file  ", "kind": "saved"})))
        with zipfile.ZipFile(f, "w") as z:
            z.writestr("state_json.npy", buf.getvalue())
        ok("C a note not in the summary is read from the file",
           CW.note_of(str(f), {"kind": "saved"}) == "from the file" and
           CW.note_of(str(f), {"kind": "session"}) == "" and
           CW.note_of(str(f), {"kind": "saved", "note": "x"}) == "x")
        hdr = cw.tree.header()
        shown = [CW.HEADERS[hdr.logicalIndex(v)] for v in range(hdr.count())
                 if not hdr.isSectionHidden(hdr.logicalIndex(v))]
        ok("C clear columns first: movie, which save, date, cells, user, cell line",
           shown[:8] == ["Use", "Colour", "Name in the graph", "Kind of save", "Saved", "Cells",
                         "User", "Cell line"], shown)
        ok("C rarely needed columns hidden by default",
           all(hdr.isSectionHidden(CW.HEADERS.index(n)) for n in CW.DEFAULT_HIDDEN))
        ok("C plain column titles", cw.tree.headerItem().text(CW.COL_SAVED) == "Date saved" and
           cw.tree.headerItem().text(CW.COL_KIND) == "Save")
        cw.show()
        pump(app)
        fm = cw.tree.fontMetrics()
        rh = cw.tree.visualItemRect(cw._items[P["auto"]]).height()
        ok(f"C taller rows ({rh} px for {fm.height()} px text)", rh >= fm.height() + 12, rh)
        cw.set_column_shown(CW.COL_BASE, True)
        cw.close()
        cw = make_window()
        ok("C a column shown again is remembered",
           not cw.tree.header().isSectionHidden(CW.COL_BASE) and
           cw.tree.header().isSectionHidden(CW.COL_INT))
        cw.set_column_shown(CW.COL_BASE, False)
    finally:
        cw.close()


# ---------------------------------------------------------------- D
def part_d(app):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox
    from peterpiper.gui import comparewin as CW
    data = OUT / "data"
    data.mkdir(parents=True, exist_ok=True)

    def movie(path, content):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content * 1000)
        return path

    def run_file(path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"run")
        return str(path)
    a_nd2 = movie(data / "movieA.nd2", b"AAAA")
    fpa = history.nd2_fingerprint(a_nd2)
    a_run = run_file(data / "OUTPUT_movieA" / "Ana" / "movieA_ROIs.npz")
    b_new = movie(OUT / "moved" / "movieB copy.nd2", b"BBBB")
    fpb = history.nd2_fingerprint(b_new)
    b_run = run_file(OUT / "elsewhere" / "movieB_session_1.npz")
    c_nd2 = movie(OUT / "data2" / "movieC.nd2", b"CCCC")
    fpc = history.nd2_fingerprint(c_nd2)
    c_run = run_file(OUT / "data2" / "OUTPUT_movieC" / "Ana" / "PeterPiper_sessions" /
                     "movieC_session_2.npz")
    d_real = movie(OUT / "somewhere" / "movieD.nd2", b"DDDD")
    fpd = history.nd2_fingerprint(d_real)
    d_run = run_file(OUT / "runsD" / "movieD_ROIs.npz")
    wrong = movie(OUT / "somewhere" / "other.nd2", b"XXXX")
    S = {
        a_run: dict(nd2="movieA.nd2", nd2_path=str(a_nd2), fingerprint=fpa, kind="saved"),
        b_run: dict(nd2="movieB.nd2", nd2_path="Z:/gone/movieB.nd2", fingerprint=fpb,
                    kind="session"),
        c_run: dict(nd2="movieC.nd2", nd2_path="Z:/gone/movieC.nd2", fingerprint=fpc,
                    kind="session"),
        d_run: dict(nd2="movieD.nd2", nd2_path="Z:/gone/movieD.nd2", fingerprint=fpd,
                    kind="saved"),
    }
    # the run index knows where movie B was last opened (made with history's own API)
    history.record_run(str(b_new), b_run, dict(S[b_run], tracked=True,
                                               saved="2026-11-01T10:00:00"))
    orig_rs = RF.read_summary
    RF.read_summary = lambda p: (dict(S[str(p)], path=str(p)) if str(p) in S
                                 else orig_rs(p))
    orig_open = QFileDialog.getOpenFileName
    orig_q = QMessageBox.question
    asked = []
    try:
        cw = make_window()
        P = {k: add(cw, k, S[p], checked=False, path=p) for k, p in
             (("A", a_run), ("B", b_run), ("C", c_run), ("D", d_run))}
        ready(cw)
        got = []
        cw.openRequested.connect(lambda d: got.append(d))
        cw.show()
        cw.tree.setCurrentItem(cw._items[P["A"]])
        ok("D 'Open in analysis' enabled when one run is selected",
           cw.btn_open.isEnabled() and cw.current_run() == a_run)
        cw.btn_open.click()
        want = {"nd2": str(a_nd2), "run": a_run}
        ok("D 'Open in analysis': open_request = the run's movie and file",
           cw.open_request == want, cw.open_request)
        ok("D ... openRequested emitted with the same dict, the window closed (accepted)",
           got == [want] and cw.result() == QDialog.Accepted and not cw.isVisible(), got)
        cw.close()
        cw = make_window()
        P = {k: add(cw, k, S[p], checked=False, path=p) for k, p in
             (("A", a_run), ("B", b_run), ("C", c_run), ("D", d_run))}
        ready(cw)
        cw.show()
        cw._cell_double(cw._items[P["B"]], CW.COL_SAVED)
        ok("D double-click a run (not its name / colour): opens it; a moved movie is found "
           "by its fingerprint (run index)",
           cw.open_request == {"nd2": str(b_new), "run": b_run}, cw.open_request)
        cw.close()
        cw = make_window()
        P = {k: add(cw, k, S[p], checked=False, path=p) for k, p in
             (("A", a_run), ("B", b_run), ("C", c_run), ("D", d_run))}
        ok("D a moved data folder: the movie found next to the run's OUTPUT_ folder",
           cw.find_movie(c_run, ask=False) == str(c_nd2), cw.find_movie(c_run, ask=False))
        ok("D a double-click on the name still renames (no opening)",
           (cw._cell_double(cw._items[P["A"]], CW.COL_LABEL) or True) and
           cw.open_request is None)
        QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: asked.append(a[1]) or ("", ""))
        cw.show()
        ok("D not found: the user is asked; Cancel = nothing happens",
           cw.open_in_analysis(d_run) is False and len(asked) == 1 and
           "movieD.nd2" in asked[0] and cw.open_request is None and cw.isVisible(), asked)
        QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: asked.append(a[1]) or
                                                   (str(wrong), ""))
        QMessageBox.question = staticmethod(lambda *a, **k: asked.append("q") or QMessageBox.No)
        ok("D a file with other contents: asked first, No = nothing happens",
           cw.open_in_analysis(d_run) is False and asked[-1] == "q" and
           cw.open_request is None)
        QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: asked.append(a[1]) or
                                                   (str(d_real), ""))
        n = len(asked)
        ok("D the movie the user shows is used",
           cw.open_in_analysis(d_run) is True and cw.open_request == {"nd2": str(d_real),
                                                                       "run": d_run}
           and len(asked) == n + 1, cw.open_request)
        cw.close()
        ok("D the run index was only read (record_run made in this test only)",
           len(history.indexed_runs()) == 1)
    finally:
        RF.read_summary = orig_rs
        QFileDialog.getOpenFileName = orig_open
        QMessageBox.question = orig_q


# ---------------------------------------------------------------- E
def part_e(app):
    from peterpiper.gui import comparewin as CW
    from peterpiper.gui import widgets as W
    res = OUT / "data" / "OUTPUT_movieE" / "Ana"
    ex1 = res / "Export_2026-11-01_10-00-30"
    ex2 = res / "Export_2026-11-03_09-15-00"
    for d, n in ((ex1, 2), (ex2, 3)):
        d.mkdir(parents=True, exist_ok=True)
        for k in range(n):
            (d / f"file{k}.csv").write_text("x")
    (res / "PeterPiper_sessions").mkdir()
    (res / "Comparisons").mkdir()
    run = str(ex1 / "movieE_ROIs.npz")
    Path(run).write_bytes(b"run")
    opened = []
    orig = W.open_path
    W.open_path = lambda p: opened.append(str(p)) or True
    cw = make_window()
    try:
        p = add(cw, "movieE", dict(kind="export"), checked=False, path=run)
        ready(cw)
        ok("E results folder of an export / an autosave / a saved run",
           CW.results_folder(run) == res and
           CW.results_folder(str(res / "PeterPiper_sessions" / "x_session_1.npz")) == res and
           CW.results_folder(str(res / "x_ROIs.npz")) == res)
        cw.tree.setCurrentItem(cw._items[p])
        cw.act_open_folder.trigger()
        ok("E 'Open results folder' opens the run's results folder",
           opened == [str(res)], opened)
        dlg = cw.show_output_files(p, exec_=False)
        items = [dlg.list.item(i).text() for i in range(dlg.list.count())]
        ok("E output files: exports newest first with date and file count, this run's export "
           "marked, autosaves, comparisons, the run's own file",
           items[0] == "Export 3 Nov 2026 09:15:00 - 3 files" and
           items[1] == "Export 1 Nov 2026 10:00:30 - 3 files   (this run's export)" and
           "Autosaves (sessions)" in items and
           "Comparisons (saved from this window)" in items and
           items[-1] == "This run's file: movieE_ROIs.npz", items)
        dlg.list.setCurrentRow(1)
        from PySide6.QtWidgets import QPushButton
        btn = next(b for b in dlg.findChildren(QPushButton) if b.text() == "Open")
        btn.click()
        ok("E Open opens the chosen export folder", opened[-1] == str(ex1), opened)
        dlg.reject()
    finally:
        W.open_path = orig
        cw.close()


# ---------------------------------------------------------------- F
_CVD = {"deutan": np.array([[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413],
                            [-0.011820, 0.042940, 0.968881]]),
        "protan": np.array([[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216],
                            [-0.003882, -0.048116, 1.051998]]),
        "tritan": np.array([[1.255528, -0.076749, -0.178779], [-0.078411, 0.930809, 0.147602],
                            [0.004733, 0.691367, 0.303900]])}


def _lab(hexc, kind=None):
    """CIE Lab of a colour, as seen with a colour-vision deficiency (Machado 2009)."""
    rgb = np.array([int(hexc[i:i + 2], 16) / 255 for i in (1, 3, 5)])
    lin = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    if kind:
        lin = np.clip(_CVD[kind] @ lin, 0, 1)
    xyz = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722],
                    [0.0193, 0.1192, 0.9505]]) @ lin / np.array([0.95047, 1, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.array([116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])])


def _worst(cols):
    return min(np.linalg.norm(_lab(a, k) - _lab(b, k)) for k in _CVD
               for a, b in itertools.combinations(cols, 2))


def part_f(app):
    ok("F fallback palette = Okabe-Ito without the pale yellow, every colour >= 2:1 on white",
       C.PLOT_PALETTE == tuple(c for c in C.PALETTE if c != "#F0E442") and
       all(C.contrast_on_white(c) >= 2.0 for c in C.PLOT_PALETTE),
       {c: round(C.contrast_on_white(c), 2) for c in C.PALETTE})
    w = _worst(C.PLOT_PALETTE)
    ok(f"F ... and colour-blind safe (worst pair under deutan / protan / tritan: dE {w:.1f})",
       w >= 10, w)
    famous = [CL.shades(f, 1)[0] for f in ("red", "green", "blue", "purple", "orange")]
    w2 = _worst(famous)
    ok(f"F the famous cell lines' colours stay apart for colour-blind eyes (dE {w2:.1f})",
       w2 >= 8, famous)
    ok("F a pale colour gets a darker edge, a strong one none",
       C.edge_colour("#F0E442") is not None and
       C.contrast_on_white(C.edge_colour("#F0E442")) > C.contrast_on_white("#F0E442") and
       C.edge_colour("#0072B2") is None)
    cw = make_window()
    try:
        p = add(cw, "pale run")
        ready(cw)
        cw.set_colour(p, "#F0E442")
        main = cw._hover_pts[0][-1] if cw._hover_pts else None
        pen = main.opts.get("symbolPen") if main is not None else None
        ok("F the live graph: a pale line's dots have a darker edge",
           pen is not None and pen.color().name().upper() == C.edge_colour("#F0E442"),
           pen.color().name() if pen is not None else None)
    finally:
        cw.close()


def main() -> int:
    from PySide6.QtWidgets import QApplication, QMessageBox
    app = QApplication.instance() or QApplication(sys.argv)
    for _n in ("information", "warning", "critical"):
        setattr(QMessageBox, _n, staticmethod(lambda *a, **k: QMessageBox.Ok))
    from peterpiper.gui import theme as TH
    TH.apply(app, "midnight", 10.0)
    orig = C.series
    C.series = lambda run, comp, q, base=None, minutes=True: FAKE[run.path]
    try:
        part_a(app)
        part_b(app)
        part_c(app)
        part_d(app)
        part_e(app)
        part_f(app)
    finally:
        C.series = orig
    print(f"\n{sum(checks)} / {len(checks)} checks passed")
    return 0 if all(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
