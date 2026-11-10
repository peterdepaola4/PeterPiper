"""
Developer test (not shipped): the live graph in the main window (pass C of
V2.3) and long Windows paths, driven directly on REAL .nd2 data, offscreen.

    MPLBACKEND=Agg QT_QPA_PLATFORM=offscreen \\
        python dev_tests/test_gui_graph.py [--parts 12] [--out <folder>]

  1  nucleus file (T=48): AUTO-DETECT, TRACK; the trace panel inside the real
     dock: 'As exported' does not make the dock wider (nor does a long hover
     readout), 'Check cells' comes back at the same width; change the Look
     preset, error, mean colour (colour dialog), axis range, title and X title
     (More style...) -> Settings.graph_style updated, saved to settings.json,
     session marked dirty and autosaved with it; the plotted mean / error bars
     = graphstyle.stats of the included cells (also after excluding a cell);
     'Save this graph...' writes .prism (a valid zip whose data table holds the
     included cells' numbers and whose graph carries the title), PNG (= the
     panel's own drawing, byte for byte) and SVG; never overwrites; the main
     export's PNG = the same drawing, its .prism has the same title; a changed
     export file name (export dialog) marks the session dirty, autosaves it and
     renames the graph title; closing + reopening (load the session) restores
     the graph look and the name
  2  LONG PATHS: an output folder > 200 characters (plain form, as a user's):
     autosave, Save ROIs now, a full export of every item type (Raw TIFFs and
     viewing copies on a 2-timepoint copy, to keep it small), 'Save this
     graph', the 'analysed before' scan and Load saved ROIs all work; paths
     shown to the user and kept in the run index are in the normal form
  Screenshots (offscreen grab, text drawn as boxes) go to <repo>/_out/shots.

Test data are read-only (D:\\); everything is written under --out.
Exit code 0 = every check passed.
"""
from __future__ import annotations

import labdata  # noqa: E402  (lab file names: dev_tests/lab_paths.json, never uploaded)

import argparse
import copy
import csv
import io
import json
import os
import shutil
import sys
import time
import traceback
import zipfile
from pathlib import Path

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                                  # noqa: BLE001
    pass
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "app"))

NUC = labdata.T("t02")
from labdata import need                                    # noqa: E402
need(NUC, what="test_gui_graph.py")            # V3.0: lab data only

ap = argparse.ArgumentParser()
ap.add_argument("--parts", default="12")
ap.add_argument("--out", default=str(REPO / "_out" / "gui_graph"))
args = ap.parse_args()

from peterpiper.safety import long_path, plain_path                    # noqa: E402

OUT = Path(plain_path(str(Path(args.out).resolve())))             # plain, like a user's
SHOTS = REPO / "_out" / "shots"
if os.path.exists(long_path(OUT)):
    shutil.rmtree(long_path(OUT))
os.makedirs(long_path(OUT), exist_ok=True)
os.makedirs(SHOTS, exist_ok=True)
os.environ["PETERPIPER_HOME"] = str(OUT / "home")                    # fresh settings + run index
os.environ.setdefault("MPLCONFIGDIR", str(OUT / "home" / "mpl"))

errors, dialogs, questions = [], [], []
sys.excepthook = lambda k, v, tb: errors.append("".join(traceback.format_exception(k, v, tb)))
from PySide6.QtGui import QColor                                   # noqa: E402
from PySide6.QtWidgets import (QApplication, QColorDialog, QDialog, QFileDialog,  # noqa: E402
                               QMessageBox)

app = QApplication(sys.argv)
app.setStyle("Fusion")
for _n in ("information", "warning", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: dialogs.append(a[1:3]) or QMessageBox.Ok))
QMessageBox.question = staticmethod(lambda *a, **k: questions.append(a[1:3]) or QMessageBox.No)
QMessageBox.exec = lambda self: dialogs.append((self.windowTitle(), self.text())) or 0

from peterpiper import graphstyle as GS                                # noqa: E402
from peterpiper import history as H                                    # noqa: E402
from peterpiper.config import Settings, load_settings                  # noqa: E402
from peterpiper.export import catalog, run_export                      # noqa: E402
from peterpiper.gui import clickwin as CW                              # noqa: E402
from peterpiper.gui import traces as TR                                # noqa: E402
from peterpiper.gui.clickwin import ClickWindow                        # noqa: E402

# V3.0: the main window no longer places the background region by itself (you
# pick a spot); this test was written for the automatic one - placed as before
def _v29_auto_bg(cls):
    orig = cls.__init__

    def init(self, *a, **k):
        orig(self, *a, **k)
        from PySide6.QtCore import QTimer as _QT
        _QT.singleShot(150, self._auto_background)
    cls.__init__ = init


_v29_auto_bg(ClickWindow)
from peterpiper.gui.exportdlg import ExportDialog                      # noqa: E402
from peterpiper.gui.traces import VIEW_CHECK, VIEW_EXPORTED            # noqa: E402
from peterpiper.nd2io import describe, open_source                     # noqa: E402
from peterpiper.plots import _panels                                   # noqa: E402
from peterpiper.roifile import load_roi_state, read_summary            # noqa: E402

ASK = {"answer": None, "calls": []}


def _fake_ask(self, runs, menu=False):                # never a modal dialog in a test
    ASK["calls"].append(dict(runs=list(runs), menu=menu))
    a = ASK["answer"]
    return a(runs) if callable(a) else a


ClickWindow._ask_previous_run = _fake_ask
SAVE = {"calls": [], "formats": ["prism", "png", "svg"]}


def _fake_save(self, what, folder, name):            # the 'Save this graph' dialog
    SAVE["calls"].append(dict(what=what, folder=folder, name=name))
    return folder, name, list(SAVE["formats"])


ClickWindow._ask_save_graph = _fake_save
checks = []


def ok(name, cond, extra=""):
    checks.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra else ""), flush=True)


def pump(sec=0.3):
    t = time.time()
    while time.time() - t < sec:
        app.processEvents()
        time.sleep(0.005)


def wait(w):
    pump(0.3)
    while w._busy_now():
        app.processEvents()
        time.sleep(0.02)
    pump(0.3)


def flushed(w):
    w._writer.flush()
    pump(0.2)


def L(p) -> str:                                      # the test reads long paths too
    return long_path(str(p))


def exists(p) -> bool:
    return os.path.exists(L(p))


def rbytes(p) -> bytes:
    with open(L(p), "rb") as f:
        return f.read()


def close(a, b, tol=1e-9):
    a, b = np.asarray(a, float), np.asarray(b, float)
    return a.shape == b.shape and np.allclose(a, b, rtol=tol, atol=tol, equal_nan=True)


def sessions(out_dir):
    d = H.session_dir(out_dir)
    if not exists(d):
        return []
    return sorted(Path(plain_path(e.path)) for e in os.scandir(L(d))
                  if "_session_" in e.name and e.name.endswith(".npz"))


def open_window(nd2, out_dir, settings=None, answer=None):
    ASK["answer"] = answer
    ASK["calls"].clear()
    src = open_source(nd2)
    exp = describe(src, out_dir=str(out_dir))
    exp.export_tiffs = False
    os.makedirs(L(exp.out_dir), exist_ok=True)
    w = ClickWindow(src, exp, settings or Settings())
    w.resize(1700, 1000)
    w.show()
    t = time.time()
    while not w._offered and time.time() - t < 30:
        pump(0.1)
    pump(0.5)
    wait(w)
    return w


def shot(w, name):
    pump(0.3)
    w.grab().save(str(SHOTS / f"{name}.png"))


def prism_table(path):
    """(x, y (T x n), graph title bytes) of a .prism: the graph's own data table."""
    with zipfile.ZipFile(L(path)) as z:
        doc = json.loads(z.read("document.json"))
        gsid = doc["sheets"]["data"][0]
        sheet = json.loads(z.read(f"data/sheets/{gsid}/sheet.json"))
        tid = sheet["table"]["uid"]
        rows = list(csv.reader(io.StringIO(z.read(f"data/tables/{tid}/data.csv").decode())))
        gid = doc["sheets"]["graphs"][0]
        gb = z.read(f"graphs/{gid}/data.bin")
        bad = z.testzip()
    num = np.array([[float(v) if v else np.nan for v in r] for r in rows if r])
    return num[:, 0], num[:, 1:], gb, bad


QUANT = "R/R0 - GFP/Cy5"
SHEET = "dRR_GFP_over_Cy5"
OUT_A = OUT / "a" / f"OUTPUT_{Path(NUC).stem}"
STATE = {}
AUTOSAVE_S = CW.AUTOSAVE_MS / 1000.0


# =============================================================================
def part_1():
    print("\n--- 1: the live graph in the window")
    w = open_window(NUC, OUT_A, Settings(baseline_timepoint=1))
    tr = w.traces
    ok("start: the panel uses Settings.graph_style (defaults)",
       tr.style() == GS.coerce(w.settings.graph_style).to_dict())
    w._auto_select()
    wait(w)
    live = w._live("nucleus")
    ok("AUTO-DETECT", len(live) >= 20, f"{len(live)} nuclei")
    t = time.time()
    w._track()
    wait(w)
    flushed(w)
    ok("tracked", w.track is not None, f"{len(live)} cells x {w.exp.n_timepoints} in "
                                        f"{time.time() - t:.0f} s")
    ok("trace opens on R/R0 GFP/Cy5", tr.current_quantity() == QUANT, tr.current_quantity())
    stem = Path(NUC).stem[:40]
    ok("export context: title {file} = the export name, {comp} = Nucleus",
       tr.current_title().startswith(f"{stem} - Nucleus (n = "), tr.current_title())

    # ---- width: inside the real dock
    pump(0.5)
    d0, p0 = w._dock.width(), tr.width()
    shot(w, "1_window_check_cells")
    tr.btn_view[VIEW_EXPORTED].click()
    pump(0.6)
    d1 = w._dock.width()
    ok("As exported: the dock does not get wider", d1 <= d0 + 1, f"{d0} -> {d1} px")
    tr.lbl_hover.setText("Mean 1.2345 ± 0.0678 SEM (n = 41)  at  12.5 min " * 4)
    pump(0.4)
    d1b = w._dock.width()
    ok("a long hover readout does not widen the dock", d1b <= d0 + 1, f"{d0} -> {d1b} px")
    tr.lbl_hover.setText("")
    tr.btn_view[VIEW_CHECK].click()
    pump(0.6)
    d2, p2 = w._dock.width(), tr.width()
    ok("back to Check cells: the same width as before", d2 == d0 and p2 == p0,
       f"dock {d0} -> {d2}, panel {p0} -> {p2}")
    tr.btn_view[VIEW_EXPORTED].click()
    pump(0.5)
    shot(w, "2_window_as_exported_default")

    # ---- change the look: preset, error, colour, More style...
    w._dirty = False
    w._save_timer.stop()
    tr.cmb_look.setCurrentIndex(tr.cmb_look.findText("Mean ± SEM + each cell"))
    pump(0.2)
    ok("Look preset -> Settings.graph_style (each cell)",
       w.settings.graph_style.get("show_cells") is True, str(w.settings.graph_style)[:80])
    s_disk, _x = load_settings()
    ok("... and saved to settings.json", (s_disk.graph_style or {}).get("show_cells") is True)
    ok("... and the session is marked dirty (autosave timer running)",
       w._dirty and w._save_timer.isActive())
    tr.cmb_err.setCurrentIndex(tr.cmb_err.findData("SD"))
    pump(0.2)
    ok("Error -> SD", w.settings.graph_style.get("error") == "SD")
    orig_col = QColorDialog.getColor
    QColorDialog.getColor = staticmethod(lambda *a, **k: QColor("#D62728"))
    tr.btn_colour.click()
    QColorDialog.getColor = orig_col
    pump(0.2)
    ok("mean colour (colour dialog)", w.settings.graph_style.get("mean_colour") == "#D62728",
       w.settings.graph_style.get("mean_colour"))
    orig_exec = TR.StyleDialog.exec

    def style_exec(dlg):
        dlg.w["y_min"].setText("0.5")
        dlg.w["y_max"].setText("2.5")
        dlg.w["title"].setText("{file} | {comp} | {quantity} | n={n}")
        dlg.w["x_title"].setText("Minutes after drug")
        return QDialog.Accepted
    TR.StyleDialog.exec = style_exec
    tr.btn_more.click()
    TR.StyleDialog.exec = orig_exec
    pump(0.3)
    gs = dict(w.settings.graph_style)
    ok("More style...: axis range, title and X title -> Settings.graph_style",
       gs.get("y_min") == 0.5 and gs.get("y_max") == 2.5 and gs.get("title", "").startswith("{file} |")
       and gs.get("x_title") == "Minutes after drug" and gs.get("error") == "SD"
       and gs.get("show_cells") is True, str({k: gs.get(k) for k in ("y_min", "y_max", "title")}))
    ok("the panel shows the fixed Y range", close(tr.vb.viewRange()[1], [0.5, 2.5], 1e-6),
       str(tr.vb.viewRange()[1]))
    ok("the panel title uses the template", tr.current_title() ==
       f"{stem} | Nucleus | R/R0 GFP/Cy5 | n={len(w._live('nucleus')) - len(w.excl['nucleus'])}",
       tr.current_title())
    pump(AUTOSAVE_S + 0.8)
    flushed(w)
    ss = sessions(OUT_A)
    st, _c = load_roi_state(ss[0]) if ss else ({}, {})
    ok("autosaved: the session file holds the new graph look",
       len(ss) == 1 and st.get("graph_style") == gs, str(st.get("graph_style"))[:100])
    shot(w, "3_window_as_exported_custom")

    # ---- the plotted mean / error = graphstyle.stats of the included cells
    M = w.track["meas"]["nucleus"]
    ref = {p[0]: p[1] for p in _panels(M, w.settings)}[SHEET]
    live = w._live("nucleus")

    def check_stats(tag):
        inc = [k for k in live if k not in w.excl["nucleus"]]
        x, y, names, xl, yl = tr.current_series()
        ok(f"{tag}: the panel's data = the export's numbers (included cells)",
           close(y, ref[:, inc]) and names == [f"Cell_{k + 1}" for k in inc], f"n = {len(inc)}")
        m, lo, hi, n = GS.stats(ref[:, inc], "SD")
        o = tr._errbar.opts if tr._errbar is not None else {}
        fin = np.isfinite(m) & np.isfinite(lo) & np.isfinite(hi)
        ok(f"{tag}: mean line and SD bars = graphstyle.stats of the included cells",
           close(tr._mean.getData()[1], m) and close(o.get("top"), (hi - m)[fin])
           and close(o.get("bottom"), (m - lo)[fin]))
        ok(f"{tag}: one thin line per included cell", sorted(k for _i, k in tr._curves) == inc)
        return inc
    inc = check_stats("As exported")
    k0 = inc[0]
    w._set_include("nucleus", k0, False)
    pump(0.3)
    inc2 = check_stats(f"after excluding cell {k0 + 1}")
    ok("... n in the title follows", tr.current_title().endswith(f"n={len(inc2)}"))
    w._set_include("nucleus", k0, True)
    pump(0.3)

    # ---- Save this graph...
    SAVE["calls"].clear()
    tr.btn_save.click()
    wait(w)
    files = list(getattr(w, "_graph_saved", []) or [])
    c = SAVE["calls"][0] if SAVE["calls"] else {}
    ok("Save this graph: the dialog's defaults (out_dir/Graphs, <name>_nucleus_<quantity>)",
       c.get("folder") == str(Path(OUT_A) / "Graphs")
       and c.get("name") == f"{stem}_nucleus_R-R0_GFP-Cy5", str(c))
    ok("Save this graph: .prism, .png, .svg written",
       [Path(f).suffix for f in files] == [".prism", ".png", ".svg"] and all(exists(f) for f in files),
       str([Path(f).name for f in files]))
    x, y, names, xl, yl = tr.current_series()
    title = tr.current_title()
    if len(files) == 3:
        px, py, gb, bad = prism_table(files[0])
        ok(".prism: a valid zip (CRC ok)", bad is None)
        ok(".prism: its graph's data table = the included cells' numbers (7 digits)",
           py.shape == y.shape and close(px, x, 1e-6) and close(py, y, 2e-6),
           f"{py.shape} vs {y.shape}")
        ok(".prism: the graph carries your title and X title",
           title.encode("cp1252") in gb and b"Minutes after drug" in gb)
        ref_png = OUT / "ref_panel.png"
        GS.save_figure(ref_png, x, y, names, tr.style(), xl, yl, title)
        ok("PNG = graphstyle.save_figure of the panel's series and style (bytes)",
           rbytes(files[1]) == rbytes(ref_png))
        svg = rbytes(files[2]).decode("utf-8", "replace")
        ok("SVG: a drawing with the text kept as text", svg.lstrip().startswith("<?xml")
           and "<svg" in svg and "Minutes after drug" in svg)
        STATE["panel_png"] = files[1]
    tr.btn_save.click()
    wait(w)
    files2 = list(getattr(w, "_graph_saved", []) or [])
    ok("saving again never replaces: _2 files",
       [Path(f).stem.endswith("_2") for f in files2] == [True, True, True]
       and all(exists(f) for f in files), str([Path(f).name for f in files2]))
    dl = [d for d in getattr(w, "_toasts", []) if d and d[0] == "Graph saved"]   # V2.9 note
    ok("the 'Graph saved' message lists the files (normal path form)",
       dl and "\\\\?\\" not in str(dl[-1][1]) and Path(files2[0]).name in str(dl[-1][1]))

    # ---- main export: PNG = the same drawing; .prism the same title
    comps = w._export_data()
    cat = catalog(comps, w.settings)
    keys = [it["key"] for it in cat if it["key"] in ("nucleus|graph|" + SHEET,
                                                      "nucleus|prismgraph")]
    w._run_export(comps, keys)
    wait(w)
    folder = Path(w._exported or "")
    pngs = sorted((folder / "Nucleus" / "Graphs").glob("*.png")) if w._exported else []
    prs = sorted((folder / "Nucleus" / "Prism graphs").glob("*.prism")) if w._exported else []
    ok("main export: one PNG and one .prism", len(pngs) == 1 and len(prs) == 1,
       f"{[p.name for p in pngs + prs]}")
    if pngs and STATE.get("panel_png"):
        ok("main export PNG = 'Save this graph' PNG = save_figure(Settings.graph_style), bytes",
           rbytes(pngs[0]) == rbytes(STATE["panel_png"]))
        ref2 = OUT / "ref_export.png"
        GS.save_figure(ref2, x, y, names, w.settings.graph_style, xl, yl, title)
        ok("... and = save_figure with Settings.graph_style", rbytes(pngs[0]) == rbytes(ref2))
    if prs:
        px, py, gb, bad = prism_table(prs[0])
        ok("main export .prism: same data, your title and X title (Prism keeps its own look)",
           bad is None and close(py, y, 2e-6) and title.encode("cp1252") in gb
           and b"Minutes after drug" in gb)

    # ---- a changed export file name marks the session dirty and autosaves (pass B)
    orig = ExportDialog.exec
    seen = {}

    def dlg_exec(dlg):
        seen["look"] = dlg.lbl_look.text()
        dlg.ed_prefix.setText("MyRun 1")
        dlg.chk_remember.setChecked(False)
        return QDialog.Accepted
    ExportDialog.exec = dlg_exec
    ran = []
    w._run_export = lambda comps, keys: ran.append(keys)
    flushed(w)
    w._dirty = False
    w._save_timer.stop()
    w._choose_outputs()
    ExportDialog.exec = orig
    del w._run_export
    ok("export dialog shows the graph look in words",
       "each cell" in seen.get("look", "") and "SD" in seen.get("look", ""), seen.get("look"))
    ok("new file name: session dirty, autosave timer running",
       w.prefix == "MyRun 1" and w._dirty and w._save_timer.isActive() and ran)
    ok("... the graph title uses the new name", tr.current_title().startswith("MyRun 1 |"),
       tr.current_title())
    pump(AUTOSAVE_S + 0.8)
    flushed(w)
    ss = sessions(OUT_A)
    st, _c = load_roi_state(ss[0]) if ss else ({}, {})
    ok("... autosaved with the new name", st.get("prefix") == "MyRun 1", str(st.get("prefix")))
    STATE["session"] = ss[0] if ss else None
    STATE["gs"] = gs
    w.close()
    pump(0.3)

    # ---- reopen: load that session -> the look and the name come back
    w2 = open_window(NUC, OUT_A, Settings(baseline_timepoint=1),
                     answer=lambda runs: str(STATE["session"]))
    n_before = len(sessions(OUT_A))
    ok("reopened: the session offered and loaded with its tracking",
       ASK["calls"] and w2.track is not None)
    ok("... the graph look restored (settings and panel)",
       w2.settings.graph_style == STATE["gs"] and w2.traces.style() == GS.coerce(STATE["gs"]).to_dict())
    ok("... the file name restored (graph title)", w2.traces.current_title().startswith("MyRun 1 |"),
       w2.traces.current_title())
    pump(AUTOSAVE_S + 0.8)
    flushed(w2)
    ok("... just looking makes no new session file", len(sessions(OUT_A)) == n_before)
    w2.traces.set_view(VIEW_EXPORTED)
    pump(0.5)
    shot(w2, "4_window_reloaded_as_exported")
    w2.close()
    pump(0.3)


# =============================================================================
def part_2():
    print("\n--- 2: long paths (output folder > 200 characters)")
    if not STATE.get("session"):
        ok("(part 1 made a session)", False)
        return
    deep = OUT / "deep"
    i = 0
    while len(str(deep)) < 190:
        deep = deep / f"Experiment folder {i} with a long descriptive name"
        i += 1
    deep = deep / f"OUTPUT_{Path(NUC).stem}"
    ok("the output folder is long (plain form)", len(str(deep)) > 200, f"{len(str(deep))} chars")
    w = open_window(NUC, deep, Settings(baseline_timepoint=1), answer=None)
    w._load_roi_file(STATE["session"])
    pump(0.3)
    ok("loaded the part-1 session (tracking)", w.track is not None)
    # V2.5 does not re-save an unchanged loaded session; forget its key so this
    # part still tests a save into the deep folder
    w._last_key = None
    w._mark_dirty()
    pump(AUTOSAVE_S + 0.8)
    flushed(w)
    ss = sessions(deep)
    sp = ss[0] if ss else None
    ok("autosave into the deep folder", sp is not None and exists(sp) and len(str(sp)) > 260
       and "Could not" not in w.lbl_saved.text(),
       f"{len(str(sp)) if sp else 0} chars; {w.lbl_saved.text()[:60]}")
    sm = read_summary(sp) if sp else None
    ok("... its summary reads back (tracked)", bool(sm) and sm["tracked"])
    rp = w._save_rois(silent=True)
    ok("Save ROIs now in the deep folder", rp is not None and exists(rp), str(rp)[-60:])
    # full export of every item type (TIFFs / viewing copies below, on a short copy)
    comps = w._export_data()
    cat = catalog(comps, w.settings)
    keys = [it["key"] for it in cat if it["key"] not in ("*|tiffs", "*|views")]
    n0 = len(dialogs)
    t = time.time()
    # V3.0: with Windows' long paths off, a too-long export asks first - answered
    # 'Export anyway' here (this part tests that long paths are written correctly)
    from peterpiper.syscheck import long_paths_enabled
    asked = []
    real_ok = ClickWindow._paths_ok

    def paths_ok(self, stem, comps_):           # called = the check ran; 'Export anyway'
        asked.append(stem)
        return True
    ClickWindow._paths_ok = paths_ok
    from peterpiper.export import longest_path
    est = longest_path(w.exp.out_dir, w.exp.nd2_path, "", [(d["label"], d["name"])
                                                          for d in comps.values()])
    ok("the long-path estimate sees this export is over 250 characters", est > 250, str(est))
    w._run_export(comps, keys)
    wait(w)
    ClickWindow._paths_ok = real_ok
    ok("the long-path check was asked before writing", bool(asked)
       or long_paths_enabled() is not False)
    folder = w._exported
    bad = [d for d in dialogs[n0:] if d and "wrong" in str(d[0]).lower()]
    ok("full export (every item type) in the deep folder", folder is not None and not bad,
       f"{len(keys)} items in {time.time() - t:.0f} s; {str(bad)[:300]}")
    found = []
    if folder:
        for root, _dirs, fs in os.walk(L(folder)):
            found += [plain_path(os.path.join(root, f)) for f in fs]
    longest = max((len(p) for p in found), default=0)
    kinds = sorted({Path(p).suffix for p in found})
    ok("... files of every kind written, the deepest over 260 characters",
       longest > 260 and {".xlsx", ".pzfx", ".prism", ".png", ".csv", ".npz", ".txt"} <= set(kinds),
       f"{len(found)} files, longest {longest} chars, {kinds}")
    prs = [p for p in found if p.endswith(".prism")]
    ok("... a deep .prism opens as a valid zip", prs and prism_table(prs[0])[3] is None,
       f"{len(prs[0]) if prs else 0} chars")
    from openpyxl import load_workbook
    xl = [p for p in found if p.endswith(".xlsx")]
    try:
        wb = load_workbook(L(xl[0]), read_only=True)
        good = len(wb.sheetnames) > 3
        wb.close()
    except Exception as exc:                                       # noqa: BLE001
        good = False
        print("   ", exc)
    ok("... a deep workbook opens", good)
    msg = [d for d in getattr(w, "_toasts", []) if d and d[0] == "Exported"]    # V2.9 note
    ok("the 'Exported' message shows the normal path form",
       msg and "\\\\?\\" not in str(msg[-1][1]) and str(deep) in str(msg[-1][1]))
    # Raw TIFFs + viewing copies (the same writers), 2 timepoints
    e2 = copy.copy(w.exp)
    e2.n_timepoints = 2
    out = run_export(str(deep), e2, w.settings, {}, ["*|tiffs", "*|views"], src=w.src)
    tifs, views = [], []
    for root, _d, fs in os.walk(L(out["folder"])):
        tifs += [f for f in fs if f.endswith(".tif")]
        views += [f for f in fs if f.endswith("_VIEW-ONLY.png")]
    C = w.exp.n_channels
    ok("Raw TIFFs and viewing copies in the deep folder", len(tifs) == 2 * C and len(views) == 2 * C,
       f"{len(tifs)} TIFFs, {len(views)} PNGs")
    import tifffile
    tf = [os.path.join(r, f) for r, _d, fs in os.walk(L(out["folder"])) for f in fs
          if f.endswith(".tif")]
    ok("... a deep TIFF reads back", tf and tifffile.imread(tf[0]).shape == (w.exp.height, w.exp.width))
    # Save this graph in the deep folder
    w.traces.set_view(VIEW_EXPORTED)
    pump(0.3)
    SAVE["calls"].clear()
    w.traces.btn_save.click()
    wait(w)
    files = list(getattr(w, "_graph_saved", []) or [])
    ok("Save this graph in the deep folder", len(files) == 3 and all(exists(f) for f in files)
       and all("\\\\?\\" not in f for f in files), f"{max((len(f) for f in files), default=0)} chars")
    # the 'analysed before' scan and Load saved ROIs
    runs = H.find_previous_runs(NUC, str(deep), (w.exp.height, w.exp.width), w.exp.n_timepoints)
    paths = [os.path.normcase(r.path) for r in runs]
    ok("the 'analysed before' scan finds the deep session (normal path form)",
       sp is not None and os.path.normcase(str(sp)) in paths
       and all("\\\\?\\" not in r.path for r in runs), f"{len(runs)} runs")
    idx = json.loads(Path(os.environ["PETERPIPER_HOME"], "run_history.json").read_text(encoding="utf-8"))
    ent = idx.get(H.nd2_fingerprint(NUC)["quick"], {})
    ok("the run index keeps the deep paths in the normal form",
       any(r["path"] == str(sp) for r in ent.get("runs", []))
       and all("\\\\?\\" not in r["path"] for r in ent.get("runs", [])))
    orig = QFileDialog.getOpenFileName
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (str(rp), ""))
    w.track = None
    n0 = len(dialogs)
    w._load_rois()
    QFileDialog.getOpenFileName = orig
    pump(0.3)
    ok("Load saved ROIs... from the deep folder (with its tracking)",
       w.track is not None and not [d for d in dialogs[n0:] if "Could not" in str(d[0])])
    w.close()
    pump(0.3)


t_all = time.time()
for key, fn in (("1", part_1), ("2", part_2)):
    if key in args.parts:
        try:
            fn()
        except Exception:                                          # noqa: BLE001
            errors.append(traceback.format_exc())
            ok(f"part {key} ran to the end", False)
print()
n_pass = sum(c for _n, c in checks)
print(f"{n_pass} of {len(checks)} checks passed; errors: {len(errors)}; "
      f"{time.time() - t_all:.0f} s")
for e in errors[:5]:
    print(str(e)[-2500:])
crit = [d for d in dialogs if d and "wrong" in str(d[0]).lower()]
for d in crit[:3]:
    print("ERROR DIALOG:", str(d)[:1500])
sys.exit(0 if n_pass == len(checks) and not errors and not crit else 1)
