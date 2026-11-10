"""
Developer test (not shipped): V2.6 Compare / average - kinetics, remembered
groups and the versions of one .nd2.

    MPLBACKEND=Agg QT_QPA_PLATFORM=offscreen python dev_tests/test_v26_kinetics.py [--keep]

A) kinetics.curve_kinetics on a hand-made curve (every number worked out by
   hand: baseline, peak, amplitude, t10 / t½ / t90 by linear interpolation,
   10-90% rise time, least-squares initial slope, maximum rate), on an exact
   exponential rise (t½ = tau ln 2 within the frame spacing), a fall, the flags
   (peak at the last timepoint, no clear response, no baseline frame).
B) Groups: each dish's values from its own dish mean curve; mean / SD / SEM /
   95% CI over the dishes = numpy / scipy by hand; the group mean curve's
   kinetics listed for reference.
C) compare.save with kinetics: t½ and slope graphs in PNG / SVG / .prism, the
   kinetics CSVs and .xlsx sheets hold the numbers of B; nothing overwritten.
D) The window: Graph = a kinetics parameter draws the dot plot (ticks = groups,
   n dishes); Save writes the ticked kinetics graphs; groups, graph names,
   ticked runs and view come back in a new window (groups also by .nd2
   fingerprint for a new analysis of the same dish).
E) Versions of one .nd2: each set its own colour, 'newest (3 of 3)' / 'older
   (2 of 3)' / 'oldest (1 of 3)' by the saved date, sorted newest on top with
   the older analyses of that .nd2 right under it.
F) GraphPad Prism 11 (only a prism.exe this test starts): the kinetics .prism
   opens with "COMPLETE! No Errors.", the legend names the groups, the error
   bars = SEM across the dishes, the group colours are drawn.
Exit code 0 = every check passed.
"""
from __future__ import annotations

import csv
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
OUT = REPO / "_out" / "v26_kinetics"
if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True)
os.environ["PETERPIPER_HOME"] = str(OUT / "home")
os.environ.setdefault("MPLCONFIGDIR", str(OUT / "home" / "mpl"))
os.environ.setdefault("MPLBACKEND", "Agg")

from peterpiper import compare as C                                    # noqa: E402
from peterpiper import graphstyle as GS                                # noqa: E402
from peterpiper import kinetics as K                                   # noqa: E402

checks = []
FAKE = {}


def ok(name, cond, extra=""):
    checks.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if not isinstance(extra, str) or extra else ""), flush=True)


def close(a, b, tol=1e-9):
    return np.isfinite(a) and abs(a - b) <= tol


# ---------------------------------------------------------------- A
def part_a():
    x = np.array([-1, 0, 1, 2, 3, 4], float)
    y = np.array([1, 1, 1.2, 1.8, 2.0, 1.9])
    k = K.curve_kinetics(x, y)
    ok("A baseline = mean at time <= 0 (2 frames)", close(k.base, 1.0) and k.base_n == 2)
    ok("A peak 2.0 at time 3, amplitude 1.0, rise", close(k.peak, 2.0) and close(k.t_max, 3)
       and close(k.amp, 1.0) and k.direction == "rise")
    ok("A t½ = 1 + (1.5 - 1.2) / 0.6 = 1.5", close(k.t_half, 1.5), k.t_half)
    ok("A t10 = 0.5, t90 = 2.5, 10-90% rise time 2.0",
       close(k.t10, 0.5) and close(k.t90, 2.5) and close(k.rise, 2.0), (k.t10, k.t90))
    exp_slope = np.polyfit([0, 1, 2], [1, 1.2, 1.8], 1)[0]
    ok(f"A initial slope = least squares through t 0, 1, 2 ({exp_slope:.4f})",
       close(k.slope, exp_slope) and k.slope_n == 3, k.slope)
    ok("A maximum rate = 0.6 (step 1 -> 2)", close(k.max_rate, 0.6), k.max_rate)
    ok("A no flags", not k.flags, k.flags)

    tau = 5.0
    xe = np.arange(-3, 61) * 0.25
    ye = np.where(xe <= 0, 1.0, 1 + (1 - np.exp(-xe / tau)))
    ke = K.curve_kinetics(xe, ye)
    th = -tau * np.log(1 - 0.5 * ke.amp)           # exact for the reached amplitude
    ok(f"A exponential: t½ = {th:.4f} within a quarter frame", abs(ke.t_half - th) < 0.06,
       ke.t_half)
    ok("A exponential still rising at the end: flagged", any("end of the window" in f
                                                              for f in ke.flags), ke.flags)
    xd = np.array([-3, -2, -1, 0, 1, 2, 3, 4], float)
    yd = np.array([1.3, 1.15, 1.05, 1.0, 1.4, 1.8, 2.0, 2.0])
    kd = K.curve_kinetics(xd, yd)
    ok("A baseline = the value AT the baseline timepoint, not the drifting frames before",
       close(kd.base, 1.0) and close(kd.amp, 1.0) and close(kd.t_half, 1.25), kd)
    kw = K.curve_kinetics(xd, yd, t_end=2.0)
    ok("A window end 2: peak 1.8 at 2, t½ = 1 + (1.4 - 1.4) / 0.4 = 1.0, flagged at the end",
       close(kw.peak, 1.8) and close(kw.t_max, 2.0) and close(kw.t_half, 1.0) and
       close(kw.t_end, 2.0) and any("end of the window" in f for f in kw.flags), kw)
    kf = K.curve_kinetics(x, 2 - y)
    ok("A a fall: direction 'fall', same t½ and |amplitude|",
       kf.direction == "fall" and close(kf.t_half, 1.5) and close(kf.amp, -1.0), kf)
    rng = np.random.default_rng(3)
    xn = np.arange(-4, 10, dtype=float)
    yn = 1 + np.where(xn <= 0, rng.normal(0, 0.1, xn.size), 0.0)
    yn[xn > 0] = 1.05
    kn = K.curve_kinetics(xn, yn)
    ok("A change < 3 SD of the baseline frames: 'no clear response'",
       any("no clear response" in f for f in kn.flags), kn.flags)
    k0 = K.curve_kinetics([1, 2, 3], [1, 2, 3])
    ok("A no baseline frame: NaN + flag", not np.isfinite(k0.t_half) and k0.flags)


# ---------------------------------------------------------------- helpers
def fake_series(label, y, sec=60, base=1, path=None):
    y = np.asarray(y, float)
    T = y.shape[0]
    run = C.Run(path=path or str(OUT / f"{label}.npz"), label=label, nd2=f"{label}.nd2",
                baseline=base, seconds_per_frame=sec, n_timepoints=T, channels=["GFP"],
                meas={}, included={})
    steps = np.arange(T, dtype=float) - (base - 1)
    return C.Series(label=label, x=steps * sec / 60.0, y=y, x_label="Time from baseline (min)",
                    cells=list(range(y.shape[1])), run=run)


def rise(tau, T=20, base=3, cells=3, seed=0, amp=1.0):
    """T x cells: flat until the baseline timepoint, then 1 + amp (1 - exp(-t/tau))."""
    t = np.arange(T, dtype=float) - (base - 1)
    c = np.where(t <= 0, 1.0, 1 + amp * (1 - np.exp(-np.maximum(t, 0) / tau)))
    rng = np.random.default_rng(seed)
    return c[:, None] * (1 + rng.normal(0, 0.002, (T, cells)))


def dishes():
    a = [fake_series(f"U2OS d{i + 1}", rise(t, seed=i), base=3) for i, t in enumerate((2, 3, 4))]
    b = [fake_series(f"IHH d{i + 1}", rise(t, seed=10 + i, amp=0.5), base=3)
         for i, t in enumerate((6, 8))]
    return a, b


# ---------------------------------------------------------------- B
def part_b():
    a, b = dishes()
    ga, gb = C.group_line("U2OS", a), C.group_line("IHH", b)
    items = K.items_for([ga, gb])
    ok("B one value per dish, from the dish mean curve",
       [len(it.kin) for it in items] == [3, 2] and
       close(items[0].kin[1].t_half,
             K.curve_kinetics(a[1].x, np.nanmean(a[1].y, axis=1)).t_half))
    from scipy.stats import t as student_t
    for it in items:
        v = it.values("t_half")
        sm = K.summary(it, "t_half")
        sd = np.std(v, ddof=1)
        sem = sd / np.sqrt(len(v))
        ok(f"B {it.label}: t½ mean / SD / SEM / 95% CI over {len(v)} dishes",
           close(sm.mean[0], v.mean()) and close(sm.sd[0], sd) and close(sm.sem[0], sem) and
           close(sm.ci95[0], student_t.ppf(0.975, len(v) - 1) * sem) and sm.n[0] == len(v),
           (v, sm.mean[0], sm.sem[0]))
    ok("B faster dishes (smaller tau) have smaller t½ and steeper slopes",
       np.all(np.diff(items[0].values("t_half")) > 0) and
       np.all(np.diff(items[0].values("slope")) < 0), items[0].values("t_half"))
    ok("B group mean curve's kinetics listed for reference",
       items[0].mean_kin is not None and np.isfinite(items[0].mean_kin.t_half))
    return [ga, gb], items


# ---------------------------------------------------------------- C
def part_c(lines, items):
    folder = OUT / "save"
    cols = ["#D55E00", "#009E73"]
    files = C.save(folder, "kin", ["prism", "png", "svg", "csv", "xlsx"], lines, cols,
                   GS.GraphStyle(), "nucleus", "F/F0 GFP", "t", "notes",
                   kinetics=["t_half", "slope"])
    names = sorted(Path(f).name for f in files)
    want = {"kin_t-half-max.prism", "kin_t-half-max.png", "kin_t-half-max.svg",
            "kin_initial-slope.prism", "kin_initial-slope.png", "kin_initial-slope.svg",
            "kin_kinetics_per_dish.csv", "kin_kinetics_groups.csv", "kin.xlsx"}
    ok("C kinetics graphs (PNG / SVG / .prism) and tables written", want <= set(names), names)
    with open(folder / "kin_kinetics_per_dish.csv", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    col = rows[0].index("t½ max (min)")
    got = [float(r[col]) for r in rows[1:]]
    exp = list(items[0].values("t_half")) + list(items[1].values("t_half"))
    ok("C per-dish CSV: t½ of every dish", np.allclose(got, exp, rtol=1e-5), got)
    with open(folder / "kin_kinetics_groups.csv", encoding="utf-8") as fh:
        g = [r for r in csv.reader(fh) if r[0] == "U2OS" and r[3] == "t½ max"]
    ok("C group CSV: U2OS t½ mean and SEM", g and np.isclose(float(g[0][5]), np.mean(exp[:3])) and
       np.isclose(float(g[0][7]), np.std(exp[:3], ddof=1) / np.sqrt(3), rtol=1e-5), g)
    from openpyxl import load_workbook
    wb = load_workbook(folder / "kin.xlsx", read_only=True)
    ok("C .xlsx: kinetics sheets + methods text",
       {"Kinetics per dish", "Kinetics groups", "Methods"} <= set(wb.sheetnames) and
       any("t½ max" in str(r[0]) for r in wb["Methods"].iter_rows(values_only=True) if r[0]),
       wb.sheetnames)
    with zipfile.ZipFile(folder / "kin_t-half-max.prism") as z:
        import json
        txt = " ".join(json.dumps(json.loads(z.read(n)), ensure_ascii=False)
                       for n in z.namelist() if n.endswith(".json"))
    ok("C .prism: graph data + column table (one column per group)",
       "t½ max - graph data" in txt and "each dish (column table)" in txt and
       '"U2OS"' in txt and '"IHH"' in txt)
    again = C.save(folder, "kin", ["png"], lines, cols, GS.GraphStyle(), "nucleus",
                   "F/F0 GFP", "t", "notes", kinetics=["t_half"])
    ok("C nothing overwritten (a second save gets new names)",
       all(Path(f).name not in names for f in again), again)
    return files


# ---------------------------------------------------------------- D / E
def put_fake(cw, s, summary, checked=True):
    from PySide6.QtCore import Qt
    FAKE[s.run.path] = s
    cw._insert_row(s.run.path, summary)
    cw._mark_duplicates()
    cw._runs[s.run.path] = s.run
    s.run.label = cw._labels[s.run.path]
    cw._busy = True
    cw._use(s.run.path).setCheckState(Qt.Checked if checked else Qt.Unchecked)
    cw._busy = False
    return s.run.path


def ready(cw):
    if cw.cmb_comp.count() == 0:
        cw.cmb_comp.addItem("Nucleus", "nucleus")
        cw.cmb_q.addItem("F/F0 GFP")
    cw.refresh()


def part_d():
    from PySide6.QtWidgets import QApplication, QMessageBox
    from peterpiper.gui.comparewin import CompareWindow
    app = QApplication.instance() or QApplication(sys.argv)
    for _n in ("information", "warning", "critical"):
        setattr(QMessageBox, _n, staticmethod(lambda *a, **k: QMessageBox.Ok))
    CompareWindow.ASK_UNKNOWN = False
    a, b = dishes()
    cw = CompareWindow(GS.GraphStyle().to_dict())
    paths = [put_fake(cw, s, dict(nd2=f"{s.label}.nd2", fingerprint=dict(quick=f"q{i}",
                                                                             size=100 + i)))
             for i, s in enumerate(a + b)]
    cw.set_groups({p: ("U2OS NLS" if i < 3 else "IHH NLS") for i, p in enumerate(paths)},
                  ask=False)
    cw.set_mode("dishes")
    ready(cw)
    cw.set_graph("t_half")
    ticks = cw.plot.getAxis("bottom")._tickLevels
    labels = [t for _p, t in (ticks[0] if ticks else [])]
    ok("D kinetics view: dot plot with one tick per group, n dishes",
       labels == ["U2OS NLS (n = 3)", "IHH NLS (n = 2)"], labels)
    ok("D kinetics view: values in the info text", "t½ max: U2OS NLS:" in cw.lbl_info.text()
       and "n = 3 dishes" in cw.lbl_info.text(), cw.lbl_info.text())
    cw.set_graph("time")
    ok("D back to the time course: time ticks again", cw.plot.getAxis("bottom")._tickLevels
       is None)
    for k, cb in cw.chk_kin.items():
        cb.setChecked(k in ("t_half", "max_rate"))
    files = cw.save_to(str(OUT / "gui"), "gui", ["png", "csv"], quiet=True)
    names = {Path(f).name for f in files}
    ok("D Save writes the ticked kinetics graphs",
       {"gui.png", "gui_t-half-max.png", "gui_max-rate.png", "gui_kinetics_per_dish.csv"} <=
       names and "gui_initial-slope.png" not in names, sorted(names))
    cw.set_label(paths[0], "U2OS first dish")
    cw.set_graph("slope")
    cw.close()

    cw2 = CompareWindow(GS.GraphStyle().to_dict())
    p2 = [put_fake(cw2, s, dict(nd2=f"{s.label}.nd2", fingerprint=dict(quick=f"q{i}",
                                                                            size=100 + i)),
                   checked=False) for i, s in enumerate(a + b)]
    ok("D a new window: every group remembered",
       [cw2._groups[p] for p in p2] == ["U2OS NLS"] * 3 + ["IHH NLS"] * 2,
       [cw2._groups[p] for p in p2])
    ok("D a new window: the graph name remembered", cw2._labels[p2[0]] == "U2OS first dish",
       cw2._labels[p2[0]])
    orig = C.load_run
    C.load_run = lambda p: FAKE[p].run
    try:
        cw2._restore_view()
    finally:
        C.load_run = orig
    ok("D a new window: ticked runs, mode and graph remembered",
       all(cw2._is_on(p) for p in p2) and cw2.mode() == "dishes" and cw2.graph() == "slope" and
       cw2.chk_kin["max_rate"].isChecked() and not cw2.chk_kin["slope"].isChecked(),
       (cw2.mode(), cw2.graph()))
    new = fake_series("U2OS d2 reanalysed", rise(3), path=str(OUT / "re.npz"))
    pn = put_fake(cw2, new, dict(nd2="U2OS d2.nd2", fingerprint=dict(quick="q1", size=101)),
                  checked=False)
    ok("D a new analysis of a grouped dish (same .nd2 fingerprint) joins its group",
       cw2._groups[pn] == "U2OS NLS", cw2._groups[pn])
    cw2.close()
    return app


def part_e():
    from PySide6.QtCore import Qt
    from peterpiper.gui.comparewin import (COL_FILE, COL_LABEL, COL_VER, DUP_COLOURS,
                                       CompareWindow, HEADERS)
    cw = CompareWindow(GS.GraphStyle().to_dict())
    rows = [("A old", "fa", "2026-10-01T10:00:00"), ("A newest", "fa", "2026-11-01T10:00:00"),
            ("A middle", "fa", "2026-10-15T10:00:00"), ("B old", "fb", "2026-09-01T10:00:00"),
            ("B new", "fb", "2026-10-20T10:00:00"), ("solo", "fc", "2026-10-25T10:00:00")]
    P = {}
    for lab, fp, saved in rows:
        s = fake_series(lab, rise(3), path=str(OUT / f"{lab}.npz"))
        P[lab] = put_fake(cw, s, dict(nd2=f"{fp}.nd2", saved=saved,
                                      fingerprint=dict(quick=fp, size=7)), checked=False)
    ver = {lab: cw.version_of(p) for lab, p in P.items()}
    ok("E versions by saved date (V2.8 wording; + the PeterPiper version when the file has it)", ver == {
        "A old": "oldest of 3", "A newest": "newest of 3", "A middle": "older of 3",
        "B old": "oldest of 2", "B new": "newest of 2", "solo": ""}, ver)
    col = {lab: cw._cells[p][COL_FILE].background().color().name().upper()
           for lab, p in P.items()}
    ok("E each .nd2 set its own colour (same inside a set, none for a single run)",
       col["A old"] == col["A newest"] == col["A middle"] == DUP_COLOURS[0] and
       col["B old"] == col["B new"] == DUP_COLOURS[1] and
       cw._cells[P["solo"]][COL_FILE].background().style() == Qt.NoBrush, col)
    ok("E older analyses in italics", cw._cells[P["A old"]][COL_LABEL].font().italic() and
       not cw._cells[P["A newest"]][COL_LABEL].font().italic())
    hdr = cw.tree.header()
    ok("E sorted by Version, newest first (the default)",
       hdr.sortIndicatorSection() == HEADERS.index("Version") and
       hdr.sortIndicatorOrder() == Qt.DescendingOrder)
    cw.tree.sortItems(COL_VER, Qt.DescendingOrder)
    lab_of = {p: lab for lab, p in P.items()}
    order = [lab_of[p] for p in cw._paths]
    ok("E newest on top, each .nd2's older analyses right under it",
       order == ["A newest", "A middle", "A old", "solo", "B new", "B old"], order)
    cw.close()


# ---------------------------------------------------------------- F
def prism_busy() -> bool:
    r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq prism.exe"], capture_output=True,
                       text=True)
    return "prism.exe" in r.stdout.lower()


def part_f(files, items):
    import test_prism_style as TPS
    if not TPS.PRISM.exists():
        print("SKIP: GraphPad Prism is not installed here")
        return
    t = time.time()
    while prism_busy() and time.time() - t < 300:
        time.sleep(5)
    if prism_busy():
        print("SKIP: Prism is already running (not started by this test) - not touched")
        return
    pdir = OUT / "prism"
    pdir.mkdir()
    shutil.copy(next(f for f in files if f.endswith("t-half-max.prism")), pdir / "th.prism")
    shutil.copy(next(f for f in files if f.endswith("initial-slope.prism")), pdir / "sl.prism")
    log = TPS.render(pdir, ["th", "sl"], "k")
    ok("F Prism session: COMPLETE! No Errors.", "COMPLETE! No Errors." in log, log[-200:])
    if not (pdir / "th.svg").exists():
        ok("F t½ graph rendered", False)
        return
    svg = TPS.Svg(pdir / "th.svg")
    flat = svg.alltext.replace(" ", "")
    ok("F legend names both groups with n dishes",
       "U2OS(n=3dishes)" in flat and "IHH(n=2dishes)" in flat, svg.alltext[-200:])
    ok("F the Y title is the parameter with its unit", "t½max(min)" in flat)
    exp = sum(2 * K.summary(it, "t_half").sd[0] for it in items)   # V3.0: SD default
    cnt, tot = TPS.vbar_sum(svg)
    ok(f"F error bars = SD across the dishes (V3.0 default; total {tot:.4f} vs {exp:.4f})",
       abs(tot - exp) <= max(0.05 * exp, cnt * 0.12 * svg.y_per_pt()), cnt)
    for c in ("#D55E00", "#009E73"):
        ok(f"F colour {c} drawn", TPS.png_has_colour(
            pdir / "th.png", tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)))[0])


def part_g():
    """Same time window; one row per analysis; column order; visible ticks."""
    long_ = fake_series("long", rise(12, T=60), path=str(OUT / "long.npz"))
    short = fake_series("short", rise(12, T=20), path=str(OUT / "short.npz"))
    ga = C.group_line("A", [long_])
    gb = C.group_line("B", [short])
    same = K.items_for([ga, gb], True)
    own = K.items_for([ga, gb], False)
    ok("G same window: both dishes end at the shortest dish's end (19 min)",
       all(close(it.kin[0].t_end, 19.0) for it in same), [it.kin[0].t_end for it in same])
    ok("G same window: identical curves -> identical t½, whatever the movie length",
       close(same[0].kin[0].t_half, same[1].kin[0].t_half, 1e-6), [it.kin[0].t_half for it in same])
    ok("G own windows: the longer movie gets a bigger amplitude and a later t½ (why the "
       "same window is the default)", own[0].kin[0].amp > own[1].kin[0].amp and
       own[0].kin[0].t_half > own[1].kin[0].t_half + 1)
    ok("G window text", "0 - 19 min for every dish" in K.window_text(same, ga.x_label, True))

    from PySide6.QtCore import Qt
    import peterpiper.roifile as RF
    from peterpiper.gui.comparewin import (COL_LABEL, COL_SAVED, COL_USE, COL_VER, CompareWindow,
                                       _TickDelegate, update_prefs)
    S = {}

    def summ(path, nd2, fp, ck, saved, kind):
        S[path] = dict(path=path, tracked=True, nd2=nd2, content_key=ck, saved=saved,
                       kind=kind, n_cells=5, fingerprint=dict(quick=fp, size=9))
        return path
    e1 = summ(str(OUT / "m1_export.npz"), "m1.nd2", "f1", "K1", "2026-11-01T10:00:30", "export")
    s1 = summ(str(OUT / "m1_session.npz"), "m1.nd2", "f1", "K1", "2026-11-01T10:00:10", "session")
    s2 = summ(str(OUT / "m1_later.npz"), "m1.nd2", "f1", "K2", "2026-11-02T09:00:00", "session")
    orig = RF.read_summary
    RF.read_summary = lambda p: S.get(str(p))
    update_prefs(table={"order": ["Use", "Colour", "Name in the graph", "Group (replicate "
                                  "dishes)", "Cell line", ".nd2 file", "Same .nd2 as", "Cells",
                                  "Baseline", "Frame interval", "Saved", "Version"]},
                 order_v26=False)
    try:
        cw = CompareWindow(GS.GraphStyle().to_dict())
        for p in (e1, s1, s2):
            cw.add_run_file(p, quiet=True, check=False)
        ok("G export + session with the same contents: ONE row, the copy kept with it",
           len(cw._paths) == 2 and cw._copies.get(e1) == [s1] and s1 not in cw._cells,
           (len(cw._paths), cw._copies))
        ok("G a changed later analysis is its own row: newest (2 of 2) / oldest (1 of 2)",
           cw.version_of(s2).endswith("newest of 2") and cw.version_of(e1).endswith("oldest of 2"),
           (cw.version_of(s2), cw.version_of(e1)))
        ok("G V2.8: the Version tooltip says which other analysis (its save time), both "
           "in one movie folder",
           "saved 1 Nov 2026 10:00" in cw._cells[s2][COL_VER].toolTip() and
           cw.folder_of(s2) is cw.folder_of(e1) is not None, cw._cells[s2][COL_VER].toolTip())
        ok("G the copy's file is named in the tooltip", "m1_session.npz" in
           cw._cells[e1][7].toolTip())
        ok("G adding the copy again ticks the existing row",
           cw.add_run_file(s1, quiet=True, check=False) and len(cw._paths) == 2)
        hdr = cw.tree.header()
        ok("G an older saved column order: Version and Saved moved right after the name",
           [hdr.visualIndex(c) for c in (COL_LABEL, COL_VER, COL_SAVED)] == [2, 3, 4],
           [hdr.visualIndex(c) for c in (COL_LABEL, COL_VER, COL_SAVED)])
        ok("G the Use column draws light tick boxes (seen on a dark list)",
           isinstance(cw.tree.itemDelegateForColumn(COL_USE), _TickDelegate) and
           cw.tree.styleSheet() == "")
        cw.close()
    finally:
        RF.read_summary = orig


def main() -> int:
    part_a()
    lines, items = part_b()
    files = part_c(lines, items)
    orig = C.series
    C.series = lambda run, comp, q, base=None, minutes=True: FAKE[run.path]
    try:
        part_d()
        part_e()
        part_g()
    finally:
        C.series = orig
    part_f(files, items)
    print(f"\n{sum(checks)} / {len(checks)} checks passed")
    if "--keep" not in sys.argv:
        shutil.rmtree(OUT / "prism", ignore_errors=True)
    return 0 if all(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
