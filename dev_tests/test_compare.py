"""
Developer test (not shipped): V2.4 'Load look from a Prism file' and 'Compare runs'.

    MPLBACKEND=Agg QT_QPA_PLATFORM=offscreen python dev_tests/test_compare.py [--keep]

A) prismstyle.read_style: for several GraphStyles write_prism(style) -> read_style
   gives the style back (within Prism's 0.12 pt steps); the trace panel's and
   More style's 'Load look from a Prism file' set the live look (settings follow);
   unusable files give a plain message. In GraphPad Prism 11 (by script) a written
   .prism is re-saved unchanged and with SetAxisLimits / SetAxisTitle /
   SetGraphTitle; read_style must give the same look / the changes.
B) Three tracked runs (the nucleus file twice with other exclusions, its
   sibling with baseline T3) saved with 'Save ROIs now', each with its own single-
   run CSV export. The Compare window (offscreen) lists them, the per-run mean /
   SEM / n / time equal the export's numbers, saves .prism / PNG / SVG / CSV (never
   overwriting); the .prism opens in Prism 11 COMPLETE with one line per run in
   distinct colours and a legend. The main window's and the start window's
   buttons open it. All Prism work is ONE Prism session; a prism.exe this test
   did not start is never touched. Exit code 0 = every check passed.
"""
from __future__ import annotations

import labdata  # noqa: E402  (lab file names: dev_tests/lab_paths.json, never uploaded)

import csv
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
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
OUT = REPO / "_out" / "compare"
if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True)
os.environ["PETERPIPER_HOME"] = str(OUT / "home")
os.environ.setdefault("MPLCONFIGDIR", str(OUT / "home" / "mpl"))

import test_prism_style as TPS                                     # noqa: E402  (helpers)
from PySide6.QtWidgets import QApplication, QMessageBox             # noqa: E402

app = QApplication(sys.argv)
app.setStyle("Fusion")
MSG = []
for _n in ("information", "warning", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: (MSG.append(a[2] if len(a) > 2
                                                                      else ""), QMessageBox.Ok)[1]))
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)
QMessageBox.exec = lambda self: 0

from peterpiper import compare as C                                    # noqa: E402
from peterpiper import graphstyle as GS                                # noqa: E402
from peterpiper import prismstyle as PS                                # noqa: E402
from peterpiper.config import Settings                                 # noqa: E402
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
from peterpiper.gui.comparewin import CompareWindow                    # noqa: E402
from peterpiper.gui.traces import StyleDialog, VIEW_EXPORTED           # noqa: E402
from peterpiper.nd2io import describe, open_source                     # noqa: E402
from peterpiper.prismfile import write_prism                           # noqa: E402

NUC = labdata.T("t02")
NUC2 = labdata.T("t03")
from labdata import need                                    # noqa: E402
need(NUC, NUC2, what="test_compare.py")            # V3.0: lab data only
ClickWindow._ask_previous_run = lambda self, runs, menu=False: None
checks = []


def ok(name, cond, extra=""):
    checks.append(bool(cond))
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


def same_style(want: dict, got: dict, fields=PS.READ_FIELDS):
    """Fields that differ (floats within Prism's steps: 0.12 pt lines, symbol
    sizes to 0.01 pt, font sizes to 0.001 pt)."""
    bad = {}
    for f in fields:
        if f in ("cell_colour", "cell_width") and not want.get("show_cells"):
            continue                              # no cell lines: nothing to read
        if f not in got:
            bad[f] = (want.get(f), "missing")
            continue
        a, b = want.get(f), got[f]
        if isinstance(a, float) and isinstance(b, (int, float)) and b is not None:
            tol = 0.061 if f.endswith("width") else 0.01
            if abs(a - b) > tol:
                bad[f] = (a, b)
        elif a != b:
            bad[f] = (a, b)
    return bad


def prism_session(folder: Path, lines, name: str, timeout=900) -> str:
    """One Prism script run (TPS.render's loop with our own commands)."""
    pzc, log = folder / f"{name}.pzc", folder / f"{name}.log"
    pzc.write_text("\r\n".join([f'SetPath "{folder}"'] + lines + ["Exit"]) + "\r\n",
                   encoding="cp1252")
    for _attempt in range(2):
        p = subprocess.Popen([str(TPS.PRISM), str(pzc)])          # only this PID is ever killed
        t0 = time.time()
        while p.poll() is None:
            txt = log.read_text(errors="replace") if log.exists() else ""
            if "PROBLEM" in txt or time.time() - t0 > timeout:
                time.sleep(1)
                p.kill()
                p.wait()
                break
            time.sleep(0.5)
        if log.exists():
            return log.read_text(errors="replace")
        time.sleep(5)
    return "(no log)"


def prism_busy() -> bool:
    r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq prism.exe"], capture_output=True,
                       text=True)
    return "prism.exe" in r.stdout.lower()


def read_export_csv(folder: Path, pattern: str):
    fs = sorted((folder / "Nucleus" / "CSV").glob(pattern))
    if not fs:
        return None
    with open(fs[0], encoding="utf-8") as f:
        rows = list(csv.reader(f))
    h = rows[0]
    im, isem, i_n = h.index("Mean"), h.index("SEM"), h.index("n")
    num = lambda v: float(v) if v != "" else np.nan                # noqa: E731
    return dict(x=np.array([num(r[0]) for r in rows[1:]]),
                mean=np.array([num(r[im]) for r in rows[1:]]),
                sem=np.array([num(r[isem]) for r in rows[1:]]),
                n=np.array([int(r[i_n]) for r in rows[1:]]))


# ------------------------------------------------------------------ A: offline
STYLES = {
    "rt_default": GS.GraphStyle(),
    "rt_red_sd": GS.GraphStyle(error="SD", mean_colour="#D62728", mean_width=2.0,
                               symbol="square", symbol_size=5.0, font_pt=14.0),
    "rt_cells_ci": GS.GraphStyle(error="95% CI", show_cells=True, cell_colour="#1F77B4",
                                 cell_width=0.75, x_min=-2.0, x_max=8.0, y_min=0.5, y_max=1.5,
                                 symbol="triangle", title="My cells (n = {n})",
                                 x_title="Minutes", y_title="Ratio"),
    "rt_none": GS.GraphStyle(error="none", symbol="diamond", mean_width=0.36, symbol_size=4.32,
                             font_pt=9.0, mean_colour="#2CA02C"),
}


def write_styled(folder: Path, name: str, st: GS.GraphStyle) -> str:
    rng = np.random.default_rng(len(name))
    x = np.arange(12.0) - 2
    y = rng.normal(1.0, 0.1, (12, 6))
    q = "R/R0 GFP/Cy5"
    xt, yt = GS.axis_titles(st, "Time from baseline (min)", q)
    return write_prism(str(folder / f"{name}.prism"), x, xt, q, yt, y,
                       [f"Cell_{k + 1}" for k in range(6)],
                       GS.title_text(st, "cells", "Nucleus", q, 6), style=st.to_dict(),
                       name="cells")


def part_a_offline(folder: Path) -> dict:
    files = {}
    for name, st in STYLES.items():
        p = write_styled(folder, name, st)
        files[name] = p
        got, notes = PS.read_style(p)
        bad = same_style(st.to_dict(), got)
        ok(f"A {name}: write_prism -> read_style gives the style back", not bad,
           f"{bad} {notes}")
    # graph block alone (bytes): same numbers, texts as written
    with zipfile.ZipFile(files["rt_red_sd"]) as z:
        gid = json.loads(z.read("document.json"))["sheets"]["graphs"][0]
        gb = z.read(f"graphs/{gid}/data.bin")
    got, _n = PS.read_style(gb)
    ok("A read_style(bytes): colour / error / symbol / width",
       got.get("mean_colour") == "#D62728" and got.get("error") == "SD" and
       got.get("symbol") == "square" and abs(got.get("mean_width", 0) - 2.0) <= 0.061)
    # unusable files: plain messages
    bad = folder / "not_prism.prism"
    bad.write_bytes(b"hello")
    try:
        PS.read_style(bad)
        ok("A not a .prism: ValueError", False)
    except ValueError as e:
        ok("A not a .prism: plain message", "could not be read as a Prism project" in str(e),
           str(e))
    nog = folder / "no_graph.prism"
    with zipfile.ZipFile(files["rt_default"]) as zi, zipfile.ZipFile(nog, "w") as zo:
        for it in zi.infolist():
            data = zi.read(it.filename)
            if it.filename == "document.json":
                d = json.loads(data)
                d["sheets"]["graphs"] = []
                data = json.dumps(d).encode()
            zo.writestr(it.filename, data)
    try:
        PS.read_style(nog)
        ok("A no graph: ValueError", False)
    except ValueError as e:
        ok("A no graph: plain message", "has no graph" in str(e), str(e))
    return files


# --------------------------------------------------------------- B: the runs
def track_run(nd2: str, tag: str, base: int, saves):
    """Track nd2, then for each (exclude cells) in saves: exclude, Save ROIs now,
    export the CSV tables. Returns [(roi path, export folder, excluded)]."""
    src = open_source(nd2)
    exp = describe(src, out_dir=str(OUT / f"OUTPUT_{tag}"))
    exp.export_tiffs = False
    os.makedirs(exp.out_dir, exist_ok=True)
    w = ClickWindow(src, exp, Settings(baseline_timepoint=1))
    w.resize(1500, 950)
    w.show()
    t = time.time()
    while not w._offered and time.time() - t < 30:
        pump(0.1)
    wait(w)
    w._auto_select()
    wait(w)
    w._track()
    wait(w)
    ok(f"B {tag}: tracked", w.track is not None and "nucleus" in w.track["meas"])
    w.q_base.setValue(base)
    pump(0.2)
    out = []
    live = w._live("nucleus")
    for excl in saves:
        for k in live:
            w._set_include("nucleus", k, k not in excl)
        pump(0.2)
        p = w._save_rois(silent=True)
        comps = w._export_data()
        w._run_export(comps, ["nucleus|csv"])
        wait(w)
        out.append((str(p), Path(w._exported), list(excl)))
        time.sleep(1.1)                          # next export folder gets a new name
    return w, out


def main() -> int:
    a_dir = OUT / "prism"
    a_dir.mkdir()
    a_files = part_a_offline(a_dir)

    w1, runs1 = track_run(NUC, "nuc", 1, [[]])
    live1 = w1._live("nucleus")
    # second save of the same file: two cells excluded (another run of the same .nd2)
    for k in live1:
        w1._set_include("nucleus", k, k not in live1[:2])
    pump(0.2)
    p = w1._save_rois(silent=True)
    w1._run_export(w1._export_data(), ["nucleus|csv"])
    wait(w1)
    runs1.append((str(p), Path(w1._exported), live1[:2]))

    # ---- A in the GUI: the trace panel takes the look of a .prism
    tr = w1.traces
    tr.set_view(VIEW_EXPORTED)
    pump(0.2)
    want = PS.read_style(a_files["rt_red_sd"])[0]
    okk = tr.load_prism_look(a_files["rt_red_sd"], quiet=True)
    pump(0.2)
    st = GS.coerce(w1.settings.graph_style)
    ok("A panel: Load look -> live look + Settings.graph_style follow",
       okk and not same_style(want, st.to_dict(), [f for f in want]) and
       GS.coerce(tr.style()) == st, f"{same_style(want, st.to_dict(), list(want))}")
    ok("A panel: a bad file -> False, look unchanged",
       not tr.load_prism_look(str(a_dir / "not_prism.prism"), quiet=True) and
       GS.coerce(tr.style()) == st)
    MSG.clear()
    tr.load_prism_look(str(a_dir / "no_graph.prism"))
    ok("A panel: plain message for a file without a graph", MSG and "has no graph" in MSG[-1],
       MSG[-1:] and MSG[-1][:80])
    dlg = StyleDialog(GS.GraphStyle(), "x", "y", tr)
    dlg.load_prism_file(a_files["rt_cells_ci"], quiet=True)
    got = dlg.result_style()
    ok("A More style...: Load look fills the dialog",
       got.show_cells and got.cell_colour == "#1F77B4" and got.error == "95% CI"
       and got.y_max == 1.5)
    dlg.reject()
    # the Look list's last entry 'Load look from a Prism file...' (file dialog stubbed)
    import peterpiper.gui.traces as TRM
    TRM.ask_prism_file = lambda parent, folder="": a_files["rt_none"]
    tr._change_style(GS.GraphStyle())
    pump(0.1)
    tr.cmb_look.setCurrentIndex(tr.cmb_look.findText(TRM.PRISM_ITEM))
    pump(0.3)
    st3 = GS.coerce(w1.settings.graph_style)
    ok("A Look list: 'Load look from a Prism file...' loads it; the list shows the look",
       st3.mean_colour == "#2CA02C" and st3.error == "none" and st3.symbol == "diamond"
       and tr.cmb_look.currentText() != TRM.PRISM_ITEM, tr.cmb_look.currentText())
    tr._change_style(GS.GraphStyle())                       # back to the default look
    pump(0.2)

    # ---- main window button + menu
    w1.btn_compare.click()
    pump(0.5)
    cw0 = getattr(w1, "_compare", None)
    ok("B main window: 'Compare / average runs...' opens the window with this file's runs",
       cw0 is not None and cw0.isVisible() and len(cw0._paths) >= 2, cw0 and len(cw0._paths))
    acts = [a.text() for a in w1.menuBar().actions()[0].menu().actions()]
    ok("B File menu has 'Compare / average runs...'", "Compare / average runs..." in acts)
    cw0.close()
    w1._dirty = False
    w1.close()
    pump(0.3)

    w2, runs2 = track_run(NUC2, "nuc2", 3, [[]])
    w2._dirty = False
    w2.close()
    pump(0.3)
    runs = [runs1[0], runs2[0], runs1[1]]
    ok("B three runs saved", all(r and Path(r[0]).exists() for r in runs), [r[0] for r in runs])

    # ---- the Compare window (default list from the index + next to the .nd2)
    cw = CompareWindow(GS.GraphStyle().to_dict(), NUC, str(OUT / "OUTPUT_nuc"))
    cw.show()
    pump(0.3)
    paths = [r[0] for r in runs]
    norm = {cw._norm(p) for p in cw._paths}
    ok("B default list has the three saved runs", all(cw._norm(p) in norm for p in paths),
       len(cw._paths))
    cw.set_checked(paths)
    pump(0.3)
    order = [cw._norm(p) for p in cw._paths]
    rows = [order.index(cw._norm(p)) for p in paths]
    cw.set_label(cw._paths[rows[2]], "nuc - 2 excluded")      # V2.8: by run, not row
    pump(0.2)
    comps = [cw.cmb_comp.itemData(i) for i in range(cw.cmb_comp.count())]
    qs = [cw.cmb_q.itemText(i) for i in range(cw.cmb_q.count())]
    ok("B compartment / quantities in common", comps == ["nucleus"] and
       qs and qs[0].startswith("R/R0") and any(q.startswith("F/F0") for q in qs), f"{comps} {qs}")
    q = next((q for q in qs if q.startswith("R/R0")), qs[0] if qs else "")
    cw.cmb_q.setCurrentIndex(qs.index(q))
    pump(0.3)
    lines, colours, comp, qq, warn = cw.current()
    # in the order of `runs` (the window lists them in its own order)
    pos = {cw._norm(s.run.path): i for i, s in enumerate(lines)}
    idx = [pos.get(cw._norm(p), 0) for p in paths]
    lines, colours = [lines[i] for i in idx], [colours[i] for i in idx]
    ok("B three lines, distinct colours", len(lines) == 3 and len(set(colours)) == 3,
       str(colours))
    ok("B no interval warning for equal frame intervals", warn == "", warn)
    ok("B edited label used", [s.label for s in lines][2] == "nuc - 2 excluded")
    # numbers = each run's own single-run CSV export
    a, b = q.split(" ", 1)[1].split("/")
    for s, (rp, folder, excl) in zip(lines, [runs[i] for i in range(3)]):
        ref = read_export_csv(folder, f"*R-R0*{a}-{b}*.csv")
        sm = GS.describe(s.y)
        good = ref is not None and len(ref["x"]) == len(s.x) and \
            np.allclose(ref["x"], np.round(s.x, 6), rtol=1e-5, atol=1e-6, equal_nan=True) and \
            np.allclose(ref["mean"], sm.mean, rtol=1e-5, atol=1e-9, equal_nan=True) and \
            np.allclose(ref["sem"], sm.sem, rtol=1e-5, atol=1e-9, equal_nan=True) and \
            np.array_equal(ref["n"], sm.n)
        ok(f"B {s.label}: x, mean, SEM, n = its own export's CSV (n = {s.n}, "
           f"baseline T{s.run.baseline})", good)
    n_live = [len(C.load_run(r[0]).included["nucleus"]) for r in runs]
    ok("B n = included cells (excluded cells left out)", n_live[2] == n_live[0] - 2 and
       [s.n for s in lines] == n_live, str(n_live))
    ok("B each run's own baseline (T1, T3, T1): x = 0 there",
       [s.run.baseline for s in lines] == [1, 3, 1] and
       all(abs(s.x[s.run.baseline - 1]) < 1e-12 for s in lines))
    # one baseline for all
    cw.chk_own_base.setChecked(False)
    cw.sp_base.setValue(2)
    pump(0.2)
    l2 = cw.current()[0]
    ok("B 'same baseline for all' = T2 everywhere", all(abs(s.x[1]) < 1e-12 for s in l2))
    cw.chk_own_base.setChecked(True)
    pump(0.2)
    # different intervals: a plain warning
    r0 = lines[0].run
    old = r0.seconds_per_frame
    r0.seconds_per_frame = old * 2 if old > 0 else 30.0
    _m, w_txt = C.time_units([s.run for s in lines])
    r0.seconds_per_frame = old
    ok("B different frame intervals -> plain warning", "different frame intervals" in w_txt,
       w_txt[:90])
    # live preview: one curve with a legend entry per run
    names = [it[1].text for it in cw.legend.items]
    ok("B live graph legend: one entry per run", sorted(names) == sorted(
        C.legend_label(s) for s in lines), str(names))

    # ---- save
    sdir = OUT / "saved"
    files = cw.save_to(str(sdir), "cmp", ["prism", "png", "svg", "csv"], quiet=True,
                      kinetics=[])
    ok("B saved .prism, .png, .svg, .csv", sorted(Path(f).suffix for f in files) ==
       [".csv", ".png", ".prism", ".svg"], str(files))
    again = cw.save_to(str(sdir), "cmp", ["csv"], quiet=True)
    ok("B never overwrites (cmp_2.csv)", again and Path(again[0]).name == "cmp_2.csv", again)
    with open(next(f for f in files if f.endswith(".csv")), encoding="utf-8") as f:
        rows_ = list(csv.reader(f))
    good = True
    for s in lines:
        sm = GS.describe(s.y)
        mine = [r for r in rows_[1:] if r[0] == s.label]
        good &= len(mine) == len(s.x) and all(
            (r[7] == "" and not np.isfinite(sm.mean[t])) or abs(float(r[7]) - sm.mean[t]) <=
            1e-5 * max(1, abs(sm.mean[t])) for t, r in enumerate(mine)) and \
            [int(r[11]) for r in mine] == list(sm.n)
    ok("B CSV: mean and n per run per timepoint", good)
    pz = next(f for f in files if f.endswith(".prism"))
    with zipfile.ZipFile(pz) as z:
        doc = json.loads(z.read("document.json"))
        sh = json.loads(z.read(f"data/sheets/{doc['sheets']['data'][0]}/sheet.json"))
        titles = [json.loads(z.read(f"data/sets/{u}.json"))["title"]
                  for u in sh["table"]["dataSets"]]
    ok("B .prism: one data set per run, replicates = largest n",
       sorted(titles) == sorted(C.legend_label(s) for s in lines) and
       sh["table"]["replicatesCount"] == max(s.n for s in lines), str(titles))

    # ---- start window button
    from peterpiper.gui import comparewin, setup
    opened = []
    comparewin.CompareWindow.exec = lambda self: opened.append(len(self._paths)) or 0
    sd = setup.SetupDialog()
    sd.btn_compare.click()
    ok("B start window: 'Compare saved runs...' opens the window (indexed runs listed)",
       opened and opened[0] >= 3, opened)
    sd.reject()
    cw.close()

    # ---------------------------------------------------- Prism 11: one session
    if not TPS.PRISM.exists():
        print("SKIP: GraphPad Prism is not installed here")
        return finish()
    t = time.time()
    while prism_busy() and time.time() - t < 300:
        time.sleep(5)
    if prism_busy():
        print("SKIP: Prism is already running (not started by this test) - not touched")
        return finish()
    pdir = OUT / "prism_run"
    pdir.mkdir()
    shutil.copy(pz, pdir / "cmp.prism")
    for n in ("rt_red_sd", "rt_cells_ci"):
        shutil.copy(a_files[n], pdir / f"{n}.prism")
    lines_ = ['Open "rt_red_sd.prism"', "GoTo G 1", 'Save "rt_red_sd_resaved.prism"', "Close",
              'Open "rt_cells_ci.prism"', "GoTo G 1", 'Save "rt_cells_ci_resaved.prism"',
              "Close",
              'Open "rt_red_sd.prism"', "GoTo G 1", "SetAxisLimits Y Bottom 0",
              "SetAxisLimits Y Top 3", "SetAxisLimits X Bottom -5", "SetAxisLimits X Top 60", 'SetAxisTitle Y "Fold change"',
              'SetGraphTitle "Edited in Prism"', 'Save "rt_red_sd_edited.prism"', "Close",
              'Open "cmp.prism"', "GoTo G 1", 'ExportSVG "cmp.svg"', 'ExportPNG "cmp.png"',
              "Close"]
    log = prism_session(pdir, lines_, "session")
    ok("Prism session: COMPLETE! No Errors.", "COMPLETE! No Errors." in log, log.strip()[-200:])
    for n in ("rt_red_sd", "rt_cells_ci"):
        f = pdir / f"{n}_resaved.prism"
        if f.exists():
            got, notes = PS.read_style(f)
            bad = same_style(STYLES[n].to_dict(), got)
            ok(f"A {n} saved by Prism: read_style = the style written", not bad,
               f"{bad} {notes}")
        else:
            ok(f"A {n} saved by Prism", False)
    f = pdir / "rt_red_sd_edited.prism"
    if f.exists():
        got, notes = PS.read_style(f)
        exp_ = dict(STYLES["rt_red_sd"].to_dict(), y_min=0.0, y_max=3.0, x_min=-5.0,
                    x_max=60.0, y_title="Fold change", title="Edited in Prism")
        bad = same_style(exp_, got)
        ok("A edited in Prism (SetAxisLimits X/Y, axis title, graph title): read_style "
           "reflects the changes", not bad, f"{bad} {notes}")
        # and the live graph takes it
        st2 = GS.GraphStyle.from_dict({**GS.GraphStyle().to_dict(), **got})
        ok("A edited look is a valid GraphStyle", st2.y_max == 3.0 and st2.x_min == -5.0)
    else:
        ok("A edited in Prism: saved", False)
    svgp = pdir / "cmp.svg"
    if svgp.exists():
        s = svgp.read_text(encoding="utf-8")
        cols = [c.lower() for c in colours]
        counts = {c: s.lower().count(f'stroke="{c}"') for c in cols}
        svg = TPS.Svg(svgp)
        ok("Prism: the comparison shows one line per run in its own colour",
           all(v >= len(ln.x) - 1 for v, ln in zip(counts.values(), lines)), str(counts))
        flat = svg.alltext.replace(" ", "")
        ok("Prism: legend lists every run", all(C.legend_label(ln).replace(" ", "") in flat
                                                for ln in lines), svg.alltext[-200:])
        ok("Prism: PNG has each run's colour", all(
            TPS.png_has_colour(pdir / "cmp.png", tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)))[0]
            for c in colours))
    else:
        ok("Prism: comparison rendered", False)
    return finish()


def finish() -> int:
    print(f"\n{sum(checks)} / {len(checks)} checks passed")
    if "--keep" not in sys.argv:
        shutil.rmtree(OUT / "prism_run", ignore_errors=True)
    return 0 if all(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
