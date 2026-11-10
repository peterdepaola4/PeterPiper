"""
Developer test (not shipped): V2.5 replicate averaging, cell-line colours and the
Prism look template.

    MPLBACKEND=Agg QT_QPA_PLATFORM=offscreen python dev_tests/test_compare_groups.py [--keep]

A) celllines.match: U2OS / U20S / u2-os / IHH / ihh_nls / ihhnlsmet / hepg2 /
   HEK293T / Hela ... and no false positives (anchor, helper, chopped ...);
   shades: ordered, distinct; assign_colours: same line -> shades of one family.
B) compare.group_line on synthetic dishes with hand-made numbers: dish mean over
   the included cells (NaN left out), group mean / SD (n-1) / SEM / 95% CI over
   the dish means (n = dishes), pooled cells; alignment on frame times from each
   dish's baseline: different intervals (30 s vs 60 s) -> only the common frame
   times, different lengths -> the common part, a dish without cells left out.
C) compare.save: .prism, PNG, JPEG, SVG, TIFF, PDF, CSV (+ per dish + pooled),
   XLSX (sheets) - numbers in the CSV / XLSX = B's hand-made numbers.
D) The GUI window offscreen: groups, modes, legend 'n = 3 dishes, N cells',
   colours by cell line (two U2OS groups -> two red shades, IHH green).
E) GraphPad Prism 11 (one session, only a prism.exe this test starts): the
   group .prism, a run-compare .prism and a single-run .prism open with "COMPLETE!
   No Errors."; the group graph's error bars = SEM across the dish means
   (computed here), the legend lists each group with n dishes / cells; every
   graph has the template look: 18 pt texts, the dotted line at X = 0, the
   template's symbols (circle, square, triangle ...) and plain (not bold) title.
F) V2.5 Cell line dropdown: 'Unknown' + every known line; a chosen line wins
   over the file name and re-colours the run; a typed new name: colour asked
   once, its runs get shades of it; 'Group by cell line' uses the choice; a new
   window remembers it (by .nd2 fingerprint, else run file path).
G) Sorting by a column title (numbers, natural names, dates), moving / resizing
   columns: rows keep their run (tick, group, colour, dropdown); order, sort and
   widths come back in a new window.
H) The same .nd2 twice (fingerprint / path / name + size; different fingerprints
   never): 'Same .nd2 as' + orange, the red warning for ticked twins, Save...
   asks first ('No' saves nothing, 'Yes' saves, no twins: not asked).
Exit code 0 = every check passed.
"""
from __future__ import annotations

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
OUT = REPO / "_out" / "compare_groups"
if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True)
os.environ["PETERPIPER_HOME"] = str(OUT / "home")
os.environ.setdefault("MPLCONFIGDIR", str(OUT / "home" / "mpl"))
os.environ.setdefault("MPLBACKEND", "Agg")

from peterpiper import celllines as CL                                 # noqa: E402
from peterpiper import compare as C                                    # noqa: E402
from peterpiper import graphstyle as GS                                # noqa: E402
from peterpiper import prismstyle as PS                                # noqa: E402

checks = []


def ok(name, cond, extra=""):
    checks.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra else ""), flush=True)


# ---------------------------------------------------------------- A
def part_a():
    want = {
        "u2os": "U2OS", "U2OS": "U2OS", "U20S": "U2OS", "u2-os": "U2OS", "U2_OS_dish3": "U2OS",
        "u2o5": "U2OS", "u2os_dish1_sensor_30min.nd2": "U2OS",
        "secondu2osdish.nd2": "U2OS", "IHH": "IHH", "ihh_nls": "IHH",
        "ihhnlsmetredo": "IHH", "IHH-NLS-met 500": "IHH", "1HH_nls": "IHH",
        "hepg2": "HepG2", "HEPG2_ctrl": "HepG2", "Hep G2": "HepG2", "HEK293T": "HEK293T",
        "hek293t_dish1": "HEK293T", "HEK293": "HEK293", "293T cells": "HEK293T",
        "Hela": "HeLa", "HeLa S3 run": "HeLa", "he1a": "HeLa", "MCF7": "MCF7", "mcf-7": "MCF7",
        "MCF10A": "MCF10A", "mcf 10a": "MCF10A", "A549": "A549", "a-549": "A549",
        "HCT116": "HCT116", "NIH3T3": "NIH3T3", "cos7": "COS-7", "CHO_K1": "CHO-K1",
        "cho_dish2": "CHO", "MDA-MB-231": "MDA-MB-231", "mda231": "MDA-MB-231",
        "Huh7": "Huh7", "Huh-7.5": "Huh-7.5", "SH-SY5Y": "SH-SY5Y", "jurkat": "Jurkat",
    }
    bad = {t: (CL.match(t).name if CL.match(t) else None) for t, n in want.items()
           if (CL.match(t).name if CL.match(t) else None) != n}
    ok(f"A cell-line names recognised ({len(want)} cases)", not bad, bad)
    none = ["anchor_cells", "helper", "chopped", "random_run", "nls_met_500", "dish1",
            "sample", "cytoplasm", "mitochondria", "GFP_Cy5_ratio", "20261027_run",
            "timelapse", "transfection_24h", "rhodamine", "objective_60x", "kellydata"]
    hits = {t: CL.match(t).name for t in none if CL.match(t)}
    ok("A no false positives on ordinary names", not hits, hits)
    fam = {CL.match(n).family for n in ("U2OS", "IHH", "HepG2", "HEK293", "HeLa")}
    ok("A U2OS / IHH / HepG2 / HEK293 / HeLa in five different families", len(fam) == 5, fam)
    ok("A the famous lines: red / green / blue / purple / orange",
       [CL.match(n).family for n in ("U2OS", "IHH", "HepG2", "HEK293T", "HeLa")] ==
       ["red", "green", "blue", "purple", "orange"])
    ok(f"A reference list has >= 300 cell lines ({len(CL.CELL_LINES)})", len(CL.CELL_LINES) >= 300)
    sh = CL.shades("red", 6)
    from colorsys import rgb_to_hls
    hls = [rgb_to_hls(*(int(c[i:i + 2], 16) / 255 for i in (1, 3, 5))) for c in sh]
    ok("A shades: distinct, all red, lightness differs >= 0.07 pairwise",
       len(set(sh)) == 6 and all(h[0] < 0.03 or h[0] > 0.97 for h in hls) and
       min(abs(a[1] - b[1]) for i, a in enumerate(hls) for b in hls[i + 1:]) >= 0.07, sh)
    cols = CL.assign_colours(["U2OS a", "U2OS b", "IHH c", "mystery", "U20S d"],
                             {"mystery": "#123456"})
    ok("A assign_colours: U2OS shades 1-3 in order, IHH green, remembered colour",
       cols[0] == sh[0] and cols[1] == sh[1] and cols[4] == sh[2] and
       cols[2] == CL.shades("green", 1)[0] and cols[3] == "#123456", cols)
    ok("A unknown -> None (ask)", CL.assign_colours(["mystery"])[0] is None)


# ---------------------------------------------------------------- B
def fake_run(label, sec, T, base=1):
    return C.Run(path=str(OUT / f"{label}.npz"), label=label, nd2=f"{label}.nd2", baseline=base,
                 seconds_per_frame=sec, n_timepoints=T, channels=["GFP"], meas={}, included={})


def fake_series(label, y, sec, base=1):
    y = np.asarray(y, float)
    T = y.shape[0]
    run = fake_run(label, sec, T, base)
    steps = np.arange(T, dtype=float) - (base - 1)
    x = steps * sec / 60.0 if sec > 0 else steps
    return C.Series(label=label, x=x, y=y, x_label="Time from baseline (min)" if sec > 0
                    else "Timepoints from baseline", cells=list(range(y.shape[1])), run=run)


def part_b():
    rng = np.random.default_rng(7)
    a = 1 + rng.random((6, 4))
    a[2, 1] = np.nan                                   # one missing value
    b = 2 + rng.random((6, 10))
    c = 3 + rng.random((6, 2))
    dishes = [fake_series("U2OS d1", a, 30), fake_series("U2OS d2", b, 30),
              fake_series("U2OS d3", c, 30)]
    g = C.group_line("U2OS NLS-met", dishes, "dishes")
    dm = np.stack([np.nanmean(a, 1), np.nanmean(b, 1), np.nanmean(c, 1)], 1)
    mean = dm.mean(1)
    sd = dm.std(1, ddof=1)
    sem = sd / np.sqrt(3)
    from scipy.stats import t as tdist
    ci = tdist.ppf(0.975, 2) * sem
    sm = GS.describe(g.y)
    ok("B dish means = mean of each dish's cells (NaN left out)", np.allclose(g.dish_mean, dm))
    ok("B group mean / SD / SEM / 95% CI over dish means, n = 3 dishes",
       np.allclose(sm.mean, mean) and np.allclose(sm.sd, sd) and np.allclose(sm.sem, sem) and
       np.allclose(sm.ci95, ci) and (sm.n == 3).all())
    ok("B legend: n dishes and total cells",
       C.legend_label(g) == "U2OS NLS-met (n = 3 dishes, 16 cells)", C.legend_label(g))
    p = C.group_line("U2OS NLS-met", dishes, "pooled")
    allc = np.hstack([a, b, c])
    sp = GS.describe(p.y)
    n = np.isfinite(allc).sum(1)
    ok("B pooled: mean / SEM over all cells, n = cells",
       np.allclose(sp.mean, np.nanmean(allc, 1)) and
       np.allclose(sp.sem, np.nanstd(allc, 1, ddof=1) / np.sqrt(n)) and (sp.n == n).all() and
       C.legend_label(p) == "U2OS NLS-met pooled (n = 16 cells, 3 dishes)")
    # different intervals: 30 s (T = 9, baseline T3) and 60 s (T = 5, baseline T2)
    s30 = fake_series("d30", 1 + rng.random((9, 3)), 30, base=3)    # -1, -0.5, 0, ... 3 min
    s60 = fake_series("d60", 1 + rng.random((5, 3)), 60, base=2)    # -1, 0, 1, 2, 3 min
    x, rows, note = C.align([s30, s60])
    ok("B different frame intervals: only the common frame times (-1, 0, 1, 2, 3 min)",
       np.allclose(x, [-1, 0, 1, 2, 3]) and list(rows[0]) == [0, 2, 4, 6, 8] and
       list(rows[1]) == [0, 1, 2, 3, 4] and "different frame intervals" in note, (x, note))
    gl = C.group_line("mix", [s30, s60])
    ok("B ... dish means taken at exactly those frames",
       np.allclose(gl.dish_mean[:, 0], np.nanmean(s30.y[[0, 2, 4, 6, 8]], 1)) and
       np.allclose(gl.dish_mean[:, 1], np.nanmean(s60.y, 1)))
    short = fake_series("short", 1 + rng.random((4, 2)), 30)
    x2, _r, note2 = C.align([dishes[0], short])
    ok("B different lengths: the common part only, said in the note",
       len(x2) == 4 and "left out" in note2, note2)
    empty = fake_series("empty", np.zeros((6, 0)), 30)
    g2 = C.group_line("G", dishes[:2] + [empty])
    ok("B a dish without included cells is left out and named",
       g2.n_dishes == 2 and g2.dropped == ["empty"])
    return dishes, g, p, (mean, sem, sd, dm)


# ---------------------------------------------------------------- C
def part_c(dishes, g, nums):
    mean, sem, sd, dm = nums
    rng = np.random.default_rng(3)
    ihh = [fake_series(f"IHH d{k}", 1.5 + rng.random((6, 5)), 30) for k in range(1, 4)]
    gi = C.group_line("IHH NLS-met", ihh, "dishes")
    lines = [g, gi]
    cols = CL.assign_colours([g.label, gi.label])
    folder = OUT / "saved"
    notes = C.notes_text(lines, "nucleus", "F/F0 GFP", GS.GraphStyle())
    files = C.save(folder, "avg", ["prism", "png", "jpeg", "svg", "tiff", "pdf", "csv", "xlsx"],
                   lines, cols, GS.GraphStyle(), "nucleus", "F/F0 GFP", "Average test", notes)
    exts = sorted(Path(f).name for f in files)
    ok("C all formats written", exts == sorted(["avg.prism", "avg.png", "avg.jpg", "avg.svg",
                                                "avg.tif", "avg.pdf", "avg.csv",
                                                "avg_per_dish.csv", "avg_pooled.csv",
                                                "avg.xlsx"]), exts)
    with open(folder / "avg.csv", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    mine = [r for r in rows[1:] if r[0] == g.label]
    ok("C CSV = hand-made group mean / SEM / SD, n = 3 dishes",
       len(mine) == 6 and np.allclose([float(r[6]) for r in mine], mean, rtol=1e-5) and
       np.allclose([float(r[7]) for r in mine], sem, rtol=1e-5) and
       np.allclose([float(r[8]) for r in mine], sd, rtol=1e-5) and
       all(r[10] == "3" for r in mine))
    with open(folder / "avg_per_dish.csv", encoding="utf-8") as f:
        prow = list(csv.reader(f))
    d1 = [float(r[10]) for r in prow[1:] if r[1] == "U2OS d1"]
    ok("C per-dish CSV = each dish's mean", np.allclose(d1, dm[:, 0], rtol=1e-5))
    from openpyxl import load_workbook
    wb = load_workbook(folder / "avg.xlsx")
    ok("C XLSX sheets", wb.sheetnames == ["Graph data", "Per dish", "Pooled cells", "Methods"],
       wb.sheetnames)
    ws = wb["Graph data"]
    v = [r[6] for r in ws.iter_rows(min_row=2, values_only=True) if r[0] == g.label]
    ok("C XLSX numbers are numbers = the group means", np.allclose(v, mean, rtol=1e-5))
    with zipfile.ZipFile(folder / "avg.prism") as z:
        doc = json.loads(z.read("document.json"))
        sh = json.loads(z.read(f"data/sheets/{doc['sheets']['data'][0]}/sheet.json"))
        titles = [json.loads(z.read(f"data/sets/{u}.json"))["title"] for u in sh["table"]["dataSets"]]
        tid = sh["table"]["uid"]
        data = [[float(v) if v else np.nan for v in r.split(",")]
                for r in z.read(f"data/tables/{tid}/data.csv").decode().splitlines()]
        names = [json.loads(z.read(f"data/sheets/{s}/sheet.json"))["title"]
                 for s in doc["sheets"]["data"]]
    data = np.array(data)
    ok("C .prism: one data set per group, the dish means are its replicates",
       titles == [C.legend_label(g), C.legend_label(gi)] and sh["table"]["replicatesCount"] == 3
       and np.allclose(data[:, 1:4], dm, equal_nan=True), titles)
    ok("C .prism: per-dish and pooled tables", any("each dish mean" in n for n in names) and
       any("pooled cells" in n for n in names), names)
    return files, lines, cols


# ---------------------------------------------------------------- D
def put_fake(cw, s, summary, checked=True):
    """A fake 'loaded' run in the compare window's list (no file needed)."""
    from PySide6.QtCore import Qt
    cw._insert_row(s.run.path, summary)
    cw._mark_duplicates()
    cw._runs[s.run.path] = s.run
    s.run.label = cw._labels[s.run.path]
    cw._busy = True
    cw._use(s.run.path).setCheckState(Qt.Checked if checked else Qt.Unchecked)
    cw._busy = False
    return s.run.path


def tick(cw, path, on=True):
    from PySide6.QtCore import Qt
    cw._busy = True
    cw._use(path).setCheckState(Qt.Checked if on else Qt.Unchecked)
    cw._busy = False
    cw.refresh()


def part_d():
    from PySide6.QtWidgets import QApplication, QMessageBox
    app = QApplication.instance() or QApplication(sys.argv)
    for _n in ("information", "warning", "critical"):
        setattr(QMessageBox, _n, staticmethod(lambda *a, **k: QMessageBox.Ok))
    from peterpiper.gui import comparewin
    from peterpiper.gui.comparewin import CompareWindow
    CompareWindow.ASK_UNKNOWN = False
    cw = CompareWindow(GS.GraphStyle().to_dict())
    # fake 'loaded' runs: patch current() inputs by injecting runs + series
    rng = np.random.default_rng(1)
    made = {}
    for lab in ("U2OS NLS a", "U2OS NLS b", "U2OS NLS c", "U2OS ctrl a", "U2OS ctrl b",
                "IHH NLS a", "IHH NLS b"):
        s = fake_series(lab, 1 + rng.random((5, 3)), 30)
        made[s.run.path] = s
    cw._fake = made
    orig_series = C.series
    C.series = lambda run, comp, q, base=None, minutes=True: made[run.path]
    try:
        for pth, s in made.items():
            put_fake(cw, s, dict(nd2=s.run.nd2, n_cells=3))
            cw.set_groups({pth: s.label.rsplit(" ", 1)[0]}, ask=False)
        cw.cmb_comp.addItem("Nucleus", "nucleus")
        cw.cmb_q.addItem("F/F0 GFP")
        cw.set_mode("dishes")
        lines, cols, comp, q, warn = cw.current()
        ok("D three groups (U2OS NLS, U2OS ctrl, IHH NLS)",
           [g.label for g in lines] == ["U2OS NLS", "U2OS ctrl", "IHH NLS"] and
           [g.n_dishes for g in lines] == [3, 2, 2], [g.label for g in lines])
        red = CL.shades("red", 2)
        ok("D colours: U2OS groups two red shades, IHH green",
           cols[:2] == red and cols[2] == CL.shades("green", 1)[0], cols)
        cw.refresh()
        names = [it[1].text for it in cw.legend.items]
        ok("D live legend: n dishes, cells", any("n = 3 dishes, 9 cells" in t for t in names),
           names)
        cw.set_group_colour("IHH NLS", "#00AA00")
        ok("D a chosen group colour is used and remembered",
           cw.current()[1][2] == "#00AA00" and
           comparewin.load_remembered().get("ihh nls") == "#00AA00")
        cw.set_mode("pooled")
        lines, cols, *_ = cw.current()
        ok("D pooled mode: n = cells", lines[0].kind == "pooled" and lines[0].n == 9)
        cw.set_mode("runs")
        lines, cols, *_ = cw.current()
        ok("D each-run mode: one line per run, U2OS runs in five red shades",
           len(lines) == 7 and cols[:5] == CL.shades("red", 5), cols)
        files = cw.save_to(str(OUT / "gui"), "gui", ["csv", "xlsx"], quiet=True, kinetics=[])
        ok("D window saves", len(files) == 2, files)
    finally:
        C.series = orig_series
        cw.close()
    # start window: the prominent button
    from peterpiper.gui import setup
    opened = []
    comparewin.CompareWindow.exec = lambda self: opened.append(1) or 0
    sd = setup.SetupDialog()
    ok("D start window: 'Compare / average runs...' button is prominent and opens the window",
       sd.btn_compare.text().startswith("Compare / average") and
       (sd.btn_compare.click() or True) and opened == [1])
    sd.reject()


# ------------------------------------------------- F / G / H (V2.5 list)
FAKE = {}


def fake_window():
    from peterpiper.gui.comparewin import CompareWindow
    cw = CompareWindow(GS.GraphStyle().to_dict())
    return cw


def add(cw, label, summary, checked=True, seed=0):
    s = fake_series(label, 1 + np.random.default_rng(seed).random((5, 3)), 30)
    FAKE[s.run.path] = s
    summary = dict(summary)
    summary.setdefault("nd2", f"{label}.nd2")
    return put_fake(cw, s, summary, checked)


def ready(cw):
    if cw.cmb_comp.count() == 0:
        cw.cmb_comp.addItem("Nucleus", "nucleus")
        cw.cmb_q.addItem("F/F0 GFP")
    cw.refresh()


def part_f():
    """Cell line dropdown: override, colours, typed name, group by line, remembered."""
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QColorDialog
    from peterpiper.gui import comparewin
    from peterpiper.gui.comparewin import CompareWindow, COL_LINE
    asked = []
    orig_get = QColorDialog.getColor
    QColorDialog.getColor = staticmethod(lambda *a, **k: asked.append(a[-1] if a else "") or
                                         QColor("#3366AA"))
    cw = fake_window()
    try:
        p1 = add(cw, "U2OS dish1", dict(fingerprint=dict(quick="f1", size=1000)))
        p2 = add(cw, "U2OS dish2", dict(fingerprint=dict(quick="f2", size=2000)))
        p3 = add(cw, "mystery dish3", {})
        p4 = add(cw, "U2OS dish4", {})
        ready(cw)
        cb = cw._combos[p2]
        items = [cb.itemText(i) for i in range(cb.count())]
        ok("F dropdown: 'Unknown' first, then every known cell line sorted",
           items[0] == "Unknown" and items[1:] == sorted(items[1:], key=str.lower) and
           set(CL.names()) <= set(items) and cb.isEditable(), items[:4])
        ok("F automatic match shown (U2OS / Unknown)",
           cb.currentText() == "U2OS" and cw._combos[p3].currentText() == "Unknown" and
           cw.cell_line_of(p1) == ("U2OS", CL.by_name("U2OS"), False))
        cb.setCurrentIndex(cb.findText("IHH"))
        cb.textActivated.emit("IHH")                         # the user picks IHH
        cols = dict(zip([r.path for r in cw.chosen()], cw.chosen_colours()))
        ok("F chosen IHH wins over the file name: green; dish1 stays red",
           cw.cell_line_of(p2)[:2] == ("IHH", CL.by_name("IHH")) and
           cols[p2] == CL.shades("green", 1)[0] and
           # V2.8: shades follow the list order (newest first inside a group folder)
           {cols[p1], cols[p4]} == set(CL.shades("red", 2)), cols)
        ok("F the Cell line cell text follows (for sorting)",
           cw._cells[p2][COL_LINE].text() == "IHH")
        CompareWindow.ASK_UNKNOWN = True
        c3 = cw._combos[p3]
        c3.setEditText("MyLine")
        c3.lineEdit().editingFinished.emit()                 # the user types a new name
        ok("F a new typed name: its colour asked once", len(asked) == 1 and "MyLine" in
           str(asked[0]), asked)
        c4 = cw._combos[p4]
        c4.setEditText("myline")
        c4.lineEdit().editingFinished.emit()
        cols = dict(zip([r.path for r in cw.chosen()], cw.chosen_colours()))
        ok("F ... not asked again; its runs get shades of that colour, same spelling",
           len(asked) == 1 and "#3366AA" in (cols[p3], cols[p4]) and
           {cols[p3], cols[p4]} == set(CL.shades_of("#3366AA", 2)) and
           cw.cell_line_of(p4)[0] == "MyLine" and c3.findText("MyLine") >= 0, cols)
        c4.lineEdit().editingFinished.emit()                 # leaving the field: no change
        ok("F leaving the field unchanged changes nothing", len(asked) == 1)
        cw._group_by_line()
        ok("F 'Group by cell line' uses the chosen cell lines",
           [cw._groups[p] for p in (p1, p2, p3, p4)] == ["U2OS", "IHH", "MyLine", "MyLine"] and
           cw.mode() == "dishes", [cw._groups[p] for p in (p1, p2, p3, p4)])
        gcols = dict(zip([g for g, _r in cw.groups()], cw.chosen_colours()))
        ok("F groups: IHH green, MyLine its colour",
           gcols.get("IHH") == CL.shades("green", 1)[0] and gcols.get("MyLine") == "#3366AA",
           gcols)
        prefs = comparewin.load_prefs().get("cell_lines", {})
        ok("F remembered by .nd2 fingerprint (else the run file's path)",
           prefs.get("fp:f2") == "IHH" and prefs.get(f"path:{cw._norm(p3)}") == "MyLine", prefs)
        cw.close()
        # a new window (as after closing PeterPiper): the choices come back
        cw = fake_window()
        q1 = add(cw, "U2OS dish1", dict(fingerprint=dict(quick="f1", size=1000)))
        q2 = add(cw, "U2OS dish2", dict(fingerprint=dict(quick="f2", size=2000)))
        q3 = add(cw, "mystery dish3", {})
        q5 = add(cw, "U2OS dish2 again", dict(fingerprint=dict(quick="f2", size=2000)))
        ready(cw)
        ok("F new window: chosen cell lines remembered (also for another analysis of that "
           ".nd2)", [cw.cell_line_of(p)[0] for p in (q1, q2, q3, q5)] ==
           ["U2OS", "IHH", "MyLine", "IHH"] and cw._combos[q2].currentText() == "IHH" and
           cw._combos[q3].currentText() == "MyLine" and cw.cell_line_of(q2)[2],
           [cw.cell_line_of(p)[0] for p in (q1, q2, q3, q5)])
        ok("F ... and the typed name is in every dropdown",
           cw._combos[q1].findText("MyLine") >= 0)
        cw._combos[q2].setCurrentIndex(0)
        cw._combos[q2].textActivated.emit("Unknown")
        ok("F 'Unknown' chosen on purpose: no cell line, remembered",
           cw.cell_line_of(q2) == ("Unknown", None, True) and
           comparewin.load_prefs()["cell_lines"]["fp:f2"] == "Unknown")
    finally:
        QColorDialog.getColor = orig_get
        CompareWindow.ASK_UNKNOWN = False
        cw.close()


def part_g():
    """Sort by a column, move / resize columns: remembered; rows keep their state."""
    from PySide6.QtCore import Qt
    from peterpiper.gui import comparewin
    from peterpiper.gui.comparewin import (COL_CELLS, COL_FILE, COL_GROUP, COL_LABEL, COL_LINE,
                                       COL_SAVED, COL_USE, HEADERS, PATH_ROLE)
    rows = [("dish 10", dict(n_cells=2, saved="2026-01-05T10:00:00")),
            ("dish 2", dict(n_cells=10, saved="2025-12-30T09:00:00")),
            ("dish 1", dict(n_cells=1, saved="2026-03-01T08:00:00"))]

    def fill(cw):
        ps = {lab: add(cw, lab, s, checked=(lab == "dish 10")) for lab, s in rows}
        ready(cw)
        return ps

    def labels(cw):
        return [cw._labels[p] for p in cw._paths]

    def rows_whole(cw):
        # V2.8: the list is a tree; every row's cells and dropdown belong to its run
        for p in cw._paths:
            it = cw._items[p]
            ps = {it.data(c, PATH_ROLE) for c in range(len(HEADERS))}
            if ps != {p} or cw.tree.itemWidget(it, COL_LINE) is not cw._combos[p]:
                return False
        return True
    cw = fake_window()
    try:
        ps = fill(cw)
        cw.set_mode("runs")        # V2.8: sorted inside each group folder - sort before grouping
        cw.tree.sortByColumn(COL_CELLS, Qt.AscendingOrder)
        ok("G sort by Cells: numbers as numbers (1, 2, 10)",
           labels(cw) == ["dish 1", "dish 10", "dish 2"], labels(cw))
        cw.tree.sortByColumn(COL_LABEL, Qt.AscendingOrder)
        ok("G sort by name: natural order (dish 1, dish 2, dish 10)",
           labels(cw) == ["dish 1", "dish 2", "dish 10"], labels(cw))
        cw.tree.sortByColumn(COL_SAVED, Qt.DescendingOrder)
        ok("G sort by Saved (newest first): by date, not by text",
           labels(cw) == ["dish 1", "dish 10", "dish 2"], labels(cw))
        cw.set_groups({ps["dish 2"]: "G2"}, ask=False)
        r2 = cw._paths.index(ps["dish 2"])
        ok("G rows keep their run: every cell, dropdown, group, tick and colour",
           rows_whole(cw) and cw._cells[cw._paths[r2]][COL_GROUP].text() == "G2" and
           [r.path for r in cw.chosen()] == [ps["dish 10"]] and
           cw._use(ps["dish 10"]).checkState() == Qt.Checked
           and cw._cells[ps["dish 10"]][1].text() == " " and
           cw._cells[ps["dish 2"]][1].text() == "")
        tick(cw, ps["dish 2"])
        ok("G ticking after a sort ticks that run", {r.path for r in cw.chosen()} ==
           {ps["dish 10"], ps["dish 2"]})
        hdr = cw.tree.header()
        ok("G columns can be dragged", hdr.sectionsMovable() and cw.tree.isSortingEnabled())
        hdr.moveSection(hdr.visualIndex(COL_SAVED), 0)
        cw.tree.setColumnWidth(COL_FILE, 333)
        cw.close()
        st = comparewin.load_prefs().get("table", {})
        ok("G remembered: column order, sort, widths (by column title)",
           st.get("order", [None])[0] == "Saved" and st.get("sort") == ["Saved", "desc"] and
           st.get("widths", {}).get(".nd2 file") == 333, st)
        cw = fake_window()
        ps = fill(cw)
        hdr = cw.tree.header()
        ok("G new window: column order, width and sort come back",
           hdr.visualIndex(COL_SAVED) == 0 and cw.tree.columnWidth(COL_FILE) == 333 and
           hdr.sortIndicatorSection() == COL_SAVED and
           hdr.sortIndicatorOrder() == Qt.DescendingOrder and
           labels(cw) == ["dish 2", "dish 1", "dish 10"] and rows_whole(cw),   # G2's folder first
           (hdr.visualIndex(COL_SAVED), cw.tree.columnWidth(COL_FILE), labels(cw)))
        # back to the plain list order for the next part
        hdr.moveSection(hdr.visualIndex(COL_SAVED), len(HEADERS) - 1)
        hdr.setSortIndicator(-1, Qt.AscendingOrder)
    finally:
        cw.close()


def part_h():
    """The same .nd2 twice: found, shown, warned, asked before saving."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QMessageBox
    from peterpiper.gui.comparewin import COL_FILE, COL_SAME, DUP_BG
    from peterpiper.gui import comparewin
    cw = fake_window()
    try:
        A = add(cw, "movieA", dict(fingerprint=dict(quick="aaa", size=5000),
                                   nd2_path="E:/x/movieA.nd2"), checked=False)
        B = add(cw, "movieA_renamed", dict(fingerprint=dict(quick="aaa", size=5000)),
                checked=False)
        Cc = add(cw, "movieC", dict(nd2_path="E:/x/movieC.nd2"), checked=False)
        D = add(cw, "movieC_v2", dict(nd2="movieC.nd2", nd2_path="e:\\X\\movieC.nd2"),
                checked=False)
        E = add(cw, "movieE", dict(fingerprint=dict(quick="e1", size=700)), checked=False)
        F = add(cw, "movieE_b", dict(nd2="movieE.nd2", fingerprint=dict(quick="", size=700)),
                checked=False)
        G = add(cw, "movieE_other", dict(nd2="movieE.nd2", fingerprint=dict(quick="g9",
                                                                             size=700)),
                checked=False)
        H = add(cw, "other", dict(fingerprint=dict(quick="h1", size=900)), checked=False)
        d = {p: dict(v) for p, v in cw._dups.items()}
        ok("H same fingerprint (renamed copy) found", d.get(A, {}).get(B) == "fingerprint")
        ok("H same .nd2 path found (case / slashes ignored)", d.get(Cc, {}).get(D) == "path")
        ok("H same file name + size found", d.get(E, {}).get(F) == "name_size")
        ok("H different fingerprints are never the same .nd2 (same name and size)",
           G not in d.get(E, {}) and H not in d)
        ok("H V2.8: one movie folder per .nd2 (with its colour); a single run has none",
           cw.folder_of(A) is not None and cw.folder_of(A) is cw.folder_of(B) and
           cw._cells[A][COL_FILE].background().color().name().upper() == DUP_BG and
           cw.folder_of(H) is None and
           cw._cells[H][COL_FILE].background().style() == Qt.NoBrush,
           cw._cells[A][comparewin.COL_VER].toolTip())
        tick(cw, A)
        tick(cw, H)
        ready(cw)
        ok("H one run of the .nd2 ticked: no warning",
           cw.duplicate_warning() == "" and cw.lbl_dup.isHidden())
        tick(cw, B)
        cw.set_groups({A: "grp 1", B: "grp 2"}, ask=False)
        cw.set_mode("dishes")
        w = cw.duplicate_warning()
        ok("H two ticked runs of one .nd2: prominent warning",
           "Runs 'movieA' and 'movieA_renamed' are analyses of the same .nd2 file" in w and
           "count one dish twice" in w and "different groups" in w and
           not cw.lbl_dup.isHidden() and "movieA_renamed" in cw.lbl_dup.text(), w)
        asked, paths = [], []
        cw._ask_save_path = lambda folder, name: paths.append(name) or \
            str(OUT / "dup" / "dupsave.prism")
        for k, cb in cw.chk_fmt.items():
            cb.setChecked(k == "csv")
        from PySide6.QtWidgets import QDialog
        cw._save_opts.exec = lambda: QDialog.Accepted      # V2.8: the file-types dialog: OK
        orig_q = QMessageBox.question
        try:
            QMessageBox.question = staticmethod(lambda *a, **k: asked.append(a[2]) or
                                                QMessageBox.No)
            cw._save_clicked()
            ok("H Save...: asks first; 'No' saves nothing",
               len(asked) == 1 and "same .nd2 file" in asked[0] and not paths and
               not (OUT / "dup").exists(), asked)
            QMessageBox.question = staticmethod(lambda *a, **k: asked.append(a[2]) or
                                                QMessageBox.Yes)
            (OUT / "dup").mkdir()
            cw._save_clicked()
            ok("H ... 'Yes' saves", len(asked) == 2 and paths and
               (OUT / "dup" / "dupsave.csv").exists())
            tick(cw, B, False)
            cw._save_clicked()
            ok("H no twin ticked: saved without asking", len(asked) == 2 and len(paths) == 2)
        finally:
            QMessageBox.question = orig_q
    finally:
        cw.close()


# ---------------------------------------------------------------- E
def prism_busy() -> bool:
    r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq prism.exe"], capture_output=True,
                       text=True)
    return "prism.exe" in r.stdout.lower()


def part_e(files, lines, cols):
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
    from peterpiper.prismfile import write_prism
    pdir = OUT / "prism"
    pdir.mkdir()
    shutil.copy(next(f for f in files if f.endswith(".prism")), pdir / "avg.prism")
    runs_lines = lines[0].dishes
    C.save(pdir, "runs", ["prism"], runs_lines, CL.assign_colours([s.label for s in runs_lines]),
           GS.GraphStyle(), "nucleus", "F/F0 GFP", "Runs test")
    x, y, names, _src = TPS.load_data()
    write_prism(str(pdir / "single.prism"), x, "Time from baseline (min)", "R/R0", "R/R0",
                y, names, "Single run", "t", name="single", style=GS.GraphStyle().to_dict())
    log = TPS.render(pdir, ["avg", "runs", "single"], "e")
    ok("E Prism session: COMPLETE! No Errors.", "COMPLETE! No Errors." in log, log[-200:])
    for nm in ("avg", "runs", "single"):
        if not (pdir / f"{nm}.svg").exists():
            ok(f"E {nm} rendered", False)
            continue
        svg = TPS.Svg(pdir / f"{nm}.svg")
        sizes = {round(fs) for fs, _y, _x, _t in svg.texts}
        ok(f"E {nm}: template fonts (18 pt texts)", 18 in sizes, sizes)
        ok(f"E {nm}: dotted line at X = 0 (template)", "stroke-dasharray" in svg.s)
        ok(f"E {nm}: plain title (not bold)", "font-weight=\"bold\"" not in svg.s and
           "font-weight=\"700\"" not in svg.s)
    svg = TPS.Svg(pdir / "avg.svg")
    flat = svg.alltext.replace(" ", "")
    ok("E avg: legend lists each group with n dishes / cells",
       all(C.legend_label(g).replace(" ", "") in flat for g in lines), svg.alltext[-200:])
    # error bars of each group = SD across its dish means (vertical bars; V3.0 default)
    sm = [GS.describe(g.y) for g in lines]
    exp_tot = sum(2 * np.nansum(s.sd) for s in sm)              # V3.0: SD default
    cnt, tot = TPS.vbar_sum(svg)
    ok(f"E avg: error bars = SD across dish means (V3.0 default; total {tot:.4f} vs "
       f"{exp_tot:.4f})",
       abs(tot - exp_tot) <= max(0.03 * exp_tot, cnt * 0.12 * svg.y_per_pt()), cnt)
    shapes = {TPS.shape_of(s) for s in TPS.Svg(pdir / "runs.svg").symbols()}
    ok("E runs: the template's symbols per data set (circle, square, triangle)",
       {"circle", "square", "triangle"} <= shapes, shapes)
    for g, c in zip(lines, cols):
        ok(f"E avg: colour {c} of {g.label} drawn",
           TPS.png_has_colour(pdir / "avg.png", tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)))[0])


def main() -> int:
    part_a()
    dishes, g, p, nums = part_b()
    files, lines, cols = part_c(dishes, g, nums)
    part_d()
    orig_series = C.series
    C.series = lambda run, comp, q, base=None, minutes=True: FAKE[run.path]
    try:
        part_f()
        part_g()
        part_h()
    finally:
        C.series = orig_series
    part_e(files, lines, cols)
    print(f"\n{sum(checks)} / {len(checks)} checks passed")
    if "--keep" not in sys.argv:
        shutil.rmtree(OUT / "prism", ignore_errors=True)
    return 0 if all(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
