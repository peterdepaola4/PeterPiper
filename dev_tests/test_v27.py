"""
Developer test (not shipped): V2.7.

    MPLBACKEND=Agg QT_QPA_PLATFORM=offscreen python dev_tests/test_v27.py [--no-prism]

A) xyplot: measures as words, paired cells (only cells included in BOTH
   compartments), trajectory (mean X / mean Y per timepoint, n = cells or dishes)
   and each cell (at a timepoint, window mean) against hand-computed numbers.
B) The Compare window's builder: the rows offer what the runs have, Y vs Time is
   the V2.6 graph, Y vs a measure draws points, the right Y axis, the sentence,
   remembered spec; save writes .prism / PNG / CSV / XLSX (never overwriting).
C) The .prism files open in GraphPad Prism 11 (script) COMPLETE.
"""
from __future__ import annotations

import csv
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
OUT = REPO / "_out" / "v27"
if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True)
os.environ["PETERPIPER_HOME"] = str(OUT / "home")
os.environ.setdefault("MPLCONFIGDIR", str(OUT / "home" / "mpl"))

from PySide6.QtWidgets import QApplication, QMessageBox             # noqa: E402

app = QApplication(sys.argv)
for _n in ("information", "warning", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: QMessageBox.Ok))

from peterpiper import compare as C                                     # noqa: E402
from peterpiper import xyplot as XP                                     # noqa: E402
from peterpiper.measure import Measurements                             # noqa: E402

FAILS: list = []
N_OK = [0]


def ok(name, cond, extra=""):
    good = bool(cond)
    N_OK[0] += good
    if not good:
        FAILS.append(name)
    print(("PASS " if good else "FAIL ") + name + (f"  [{extra}]" if extra else ""), flush=True)


def make_run(label, seed, T=12, n=6, spf=60.0, base=3, excl_cyto=(), excl_nuc=()):
    """A run with nucleus + cytoplasm, channels GFP, Cy5 (background 10)."""
    rng = np.random.default_rng(seed)
    meas = {}
    for comp, scale in (("nucleus", 1.0), ("cytoplasm", 0.5)):
        mean = 10 + scale * (100 + rng.uniform(0, 50, (T, 2, n)) +
                             np.linspace(0, 60, T)[:, None, None])
        meas[comp] = Measurements(mean=mean, background=np.full((T, 2), 10.0),
                                  area_px=np.full((T, n), 50.0),
                                  n_saturated=np.zeros((T, 2, n)), quality=np.ones((T, n)),
                                  channels=["GFP", "Cy5"], roi_mode=comp)
    inc = {"nucleus": [k for k in range(n) if k not in excl_nuc],
           "cytoplasm": [k for k in range(n) if k not in excl_cyto]}
    return C.Run(path=str(OUT / f"{label}.npz"), label=label, nd2=f"{label}.nd2", baseline=base,
                 seconds_per_frame=spf, n_timepoints=T, channels=["GFP", "Cy5"], meas=meas,
                 included=inc)


def part_a():
    print("\n=== A) xyplot data ===", flush=True)
    m = XP.Measure("nucleus", "R/R0 GFP/Cy5")
    ok("A measure in words", m.text() == "R/R0 of GFP over Cy5 in the nucleus", m.text())
    ok("A Ratio / Intensity split and join",
       XP.split_quantity("Ratio GFP/Cy5") == ("Ratio", "GFP", "Cy5")
       and XP.split_quantity("Intensity GFP") == ("Intensity", "GFP", "")
       and XP.join_quantity("F/F0", "GFP") == "F/F0 GFP")
    r1 = make_run("dishA", 1, excl_cyto=(1,), excl_nuc=(4,))
    r2 = make_run("dishB", 2)
    sp = XP.Spec(y=XP.Measure("nucleus", "F/F0 GFP"), x=XP.Measure("cytoplasm", "Intensity Cy5"))
    sy, sx = XP.paired(r1, sp.y, sp.x, None, True)
    ok("A paired: only cells included in both compartments", sy.cells == [0, 2, 3, 5]
       and sx.cells == sy.cells, f"{sy.cells}")
    M = r1.meas["nucleus"]
    bs = M.mean[:, 0, :] - 10.0
    ff0 = bs / bs[2]
    ok("A paired Y = the export's F/F0 of those cells (baseline T3)",
       np.allclose(sy.y, ff0[:, [0, 2, 3, 5]]))
    cy = r1.meas["cytoplasm"].mean[:, 1, :] - 10.0
    ok("A paired X = background-subtracted Cy5 intensity of the same cells",
       np.allclose(sx.y, cy[:, [0, 2, 3, 5]]))
    lines, warn = XP.pair_lines(sp, [("dishA", [r1])], "runs", None, True)
    p = lines[0]
    xm, _xl, _xh, ym, yl, yh = XP.point_stats(p, "SEM")
    ok("A trajectory: one point per timepoint, mean X / mean Y of the paired cells",
       len(xm) == 12 and np.allclose(xm, cy[:, [0, 2, 3, 5]].mean(1))
       and np.allclose(ym, ff0[:, [0, 2, 3, 5]].mean(1)))
    sem = ff0[:, [0, 2, 3, 5]].std(1, ddof=1) / 2.0
    ok("A trajectory Y SEM = SD (n-1) / sqrt(n)", np.allclose(yh - ym, sem))
    ok("A trajectory time = minutes from the baseline", np.allclose(p.t, (np.arange(12) - 2.0)))
    sp_at = XP.Spec(y=sp.y, x=sp.x, points="cells_at", at=4)
    p2 = XP.pair_lines(sp_at, [("dishA", [r1])], "runs", None, True)[0][0]
    ok("A each cell at 4 frames after the baseline (row 7)",
       np.allclose(p2.x[:, 0], cy[6, [0, 2, 3, 5]]) and np.allclose(p2.y[:, 0], ff0[6, [0, 2, 3, 5]])
       and p2.names[0] == "dishA cell 1")
    sp_w = XP.Spec(y=sp.y, x=sp.x, points="cells_window", win=(2, 5))
    p3 = XP.pair_lines(sp_w, [("dishA", [r1])], "runs", None, True)[0][0]
    ok("A each cell, mean over frames 2-5 after the baseline (rows 5-8)",
       np.allclose(p3.y[:, 0], ff0[4:8, [0, 2, 3, 5]].mean(0)))
    g, _w = XP.pair_lines(sp, [("U2OS", [r1, r2])], "dishes", None, True)
    d2y = C.series(r2, "nucleus", "F/F0 GFP").y.mean(1)
    ok("A groups - mean of dish means: replicates = the 2 dish means",
       g[0].x.shape == (12, 2) and np.allclose(g[0].y[:, 0], ff0[:, [0, 2, 3, 5]].mean(1))
       and np.allclose(g[0].y[:, 1], d2y) and g[0].n_dishes == 2 and g[0].n_cells == 10)
    gp, _w = XP.pair_lines(sp, [("U2OS", [r1, r2])], "pooled", None, True)
    ok("A groups - pooled: all 10 paired cells", gp[0].y.shape == (12, 10))
    ok("A sentence", sp.sentence() == "Plot F/F0 of GFP in the nucleus vs Intensity of Cy5 in "
       "the cytoplasm - one point per timepoint.", sp.sentence())
    ok("A spec round trip", XP.Spec.from_dict(sp_w.to_dict()) == sp_w)
    return r1, r2


def part_b(r1, r2):
    print("\n=== B) the Compare window builder ===", flush=True)
    from peterpiper.gui.comparewin import CompareWindow
    CompareWindow.ASK_UNKNOWN = False
    cw = CompareWindow()
    for r in (r1, r2):
        cw._runs[r.path] = r
        cw._insert_row(r.path, {"nd2": r.nd2, "n_cells": 6, "baseline": r.baseline,
                                "seconds_per_frame": 60.0, "saved": "2026-11-02T10:00:00"})
    cw.chosen = lambda: [r1, r2]
    cw._recompute()
    kinds = [cw.row_y.cmb_kind.itemData(i) for i in range(cw.row_y.cmb_kind.count())]
    ok("B Plot row offers R/R0, F/F0, Ratio, Intensity (V2.8: and every other measure)",
       kinds[:2] == ["R/R0", "F/F0"] and {"Ratio", "Intensity"} <= set(kinds), f"{kinds}")
    xk = [cw.row_x.cmb_kind.itemText(i) for i in range(cw.row_x.cmb_kind.count())]
    ok("B vs row starts with Time", xk[0] == "Time")
    cw.row_y.set_measure(XP.Measure("cytoplasm", "Ratio GFP/Cy5"))
    ok("B choosing in the Plot row sets the plotted quantity",
       cw.cmb_comp.currentData() == "cytoplasm" and cw.cmb_q.currentText() == "Ratio GFP/Cy5",
       f"{cw.cmb_comp.currentData()} {cw.cmb_q.currentText()}")
    ok("B 'over' shown for a ratio", not cw.row_y.cmb_b.isHidden())
    cw.row_y.set_measure(XP.Measure("nucleus", "F/F0 GFP"))
    ok("B 'over' hidden for F/F0", cw.row_y.cmb_b.isHidden())
    lines, *_ = cw.current()
    ok("B vs Time = the time course (one line per run)", len(lines) == 2
       and isinstance(lines[0], C.Series))
    ok("B sentence shown", "F/F0 of GFP in the nucleus vs time" in cw.lbl_sentence.text(),
       cw.lbl_sentence.text())
    cw.row_y2.set_measure(XP.Measure("cytoplasm", "Intensity Cy5"))
    ok("B right Y axis shown with a measure", cw.plot.getAxis("right").isVisible()
       and "right Y axis" in cw.lbl_sentence.text())
    files = cw.save_to(str(OUT / "saved"), "timecourse_y2", formats=["prism", "png", "csv"],
                       quiet=True, kinetics=[])
    ok("B save with a right axis: .prism, .png, .csv + right-axis csv", sorted(
        Path(f).name for f in files) == ["timecourse_y2.csv", "timecourse_y2.png",
                                         "timecourse_y2.prism", "timecourse_y2_right_axis.csv"],
       f"{[Path(f).name for f in files]}")
    cw.row_y2.set_measure(None)
    cw.row_x.set_measure(XP.Measure("cytoplasm", "Intensity Cy5"))
    sp = cw.spec()
    ok("B vs a measure: spec, Points shown (V2.8: the right axis stays available)",
       sp.x == XP.Measure("cytoplasm", "Intensity Cy5") and sp.y2 is None
       and not cw.wid_points.isHidden())
    ok("B the kinetics graph is off when X is a measure", not cw.cmb_graph.isEnabled())
    pl = cw.pair_lines()
    ok("B pair lines: one per run, paired cells", len(pl[0]) == 2 and pl[0][0].y.shape == (12, 4))
    files = cw.save_to(str(OUT / "saved"), "pairs", formats=["prism", "png", "csv", "xlsx"],
                       quiet=True)
    ok("B save Y vs X: .prism .png .csv .xlsx", sorted(Path(f).suffix for f in files) ==
       [".csv", ".png", ".prism", ".xlsx"], f"{files}")
    rows = list(csv.reader(open(OUT / "saved" / "pairs.csv", encoding="utf-8")))
    ok("B pairs.csv: 24 points with X / Y mean, SEM",
       len(rows) == 25 and rows[0][4].startswith("X mean") and rows[0][7].startswith("Y mean"))
    files2 = cw.save_to(str(OUT / "saved"), "pairs", formats=["csv"], quiet=True)
    ok("B never overwrites", Path(files2[0]).name == "pairs_2.csv", files2)
    cw.cmb_points.setCurrentIndex(cw.cmb_points.findData("cells_at"))
    cw.sp_at.setValue(3)
    files = cw.save_to(str(OUT / "saved"), "cells", formats=["prism", "png", "csv"], quiet=True)
    rows = list(csv.reader(open(OUT / "saved" / "cells.csv", encoding="utf-8")))
    ok("B each cell: one row per paired cell (4 + 6)", len(rows) == 11, f"{len(rows)}")
    cw._save_view_prefs()
    from peterpiper.gui.comparewin import load_prefs
    ok("B the plot is remembered", XP.Spec.from_dict(load_prefs()["view"]["spec"]) == cw.spec())
    cw.close()
    return [OUT / "saved" / "timecourse_y2.prism", OUT / "saved" / "pairs.prism",
            OUT / "saved" / "cells.prism"]


def part_c(prisms):
    print("\n=== C) Prism 11 ===", flush=True)
    import test_prism_style as TPS
    if not TPS.have_prism():
        print("     (no GraphPad Prism for Windows here - opening the files in Prism skipped)")
        return
    d = OUT / "prism"
    d.mkdir(exist_ok=True)
    for p in prisms:
        shutil.copy2(p, d / p.name)
    names = [p.stem for p in prisms]
    log = TPS.render(d, names, "v27")
    ok("C Prism opens every V2.7 .prism COMPLETE", "COMPLETE" in log and "PROBLEM" not in log,
       log.strip()[:200])
    for n in names:
        ok(f"C {n}.png drawn by Prism", (d / f"{n}.png").exists())


def main() -> int:
    r1, r2 = part_a()
    prisms = part_b(r1, r2)
    if "--no-prism" not in sys.argv:
        part_c(prisms)
    print(f"\n{N_OK[0]} / {N_OK[0] + len(FAILS)} checks passed")
    for f in FAILS:
        print("  FAILED:", f)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
