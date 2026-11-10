"""
Developer test (not shipped): V2.8 Compare window.

    MPLBACKEND=Agg QT_QPA_PLATFORM=offscreen python dev_tests/test_v28.py [--no-prism]

A) measures: raw intensity, background, dF/F0, dR/R0, sum intensity, area (um2),
   compartment ratio and ratio/R0 against hand-computed numbers; plain warnings
   for plots that make no sense; background (a dish measure) never paired per cell.
B) the run tree: analyses of one .nd2 in a movie folder (newest first), one tick
   per movie, the folder's own tick, rows keep their state; the Groups panel:
   new group, put selected runs in, drop, rename, delete, take out.
C) the graph: Y error bars on / X off by default and both toggles, Each cell,
   legend click hides a line with its bars, the hover readout, Timepoint axis,
   right axis against a measure, explanations on every dropdown entry; saving.
D) Prism opens the saved files.
"""
from __future__ import annotations

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
OUT = REPO / "_out" / "v28"
if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True)
os.environ["PETERPIPER_HOME"] = str(OUT / "home")
os.environ.setdefault("MPLCONFIGDIR", str(OUT / "home" / "mpl"))

from PySide6.QtCore import QPointF, Qt                              # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox             # noqa: E402

app = QApplication(sys.argv)
for _n in ("information", "warning", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: QMessageBox.Ok))

from peterpiper import compare as C                                     # noqa: E402
from peterpiper import xyplot as XP                                     # noqa: E402
from peterpiper.measure import Measurements                             # noqa: E402

FAILS: list = []
N = [0]


def ok(name, cond, extra=""):
    N[0] += bool(cond)
    if not cond:
        FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra else ""), flush=True)


def make_run(label, seed, T=10, n=5, base=3, um=0.5, excl_cyto=(), nd2=None, saved=""):
    rng = np.random.default_rng(seed)
    meas = {}
    for comp, scale in (("nucleus", 1.0), ("cytoplasm", 0.5)):
        mean = 20 + scale * (100 + rng.uniform(0, 50, (T, 2, n)) +
                             np.linspace(0, 40, T)[:, None, None])
        meas[comp] = Measurements(mean=mean, background=np.full((T, 2), 20.0) +
                                  np.arange(T)[:, None] * 0.5,
                                  area_px=rng.uniform(80, 120, (T, n)),
                                  n_saturated=np.zeros((T, 2, n)), quality=np.ones((T, n)),
                                  channels=["GFP", "Cy5"], roi_mode=comp)
    inc = {"nucleus": list(range(n)), "cytoplasm": [k for k in range(n) if k not in excl_cyto]}
    return C.Run(path=str(OUT / f"{label}.npz"), label=label, nd2=nd2 or f"{label}.nd2",
                 baseline=base, seconds_per_frame=30.0, n_timepoints=T,
                 channels=["GFP", "Cy5"], meas=meas, included=inc, saved=saved, um_per_px=um)


def part_a():
    print("\n=== A) measures ===", flush=True)
    r = make_run("d1", 1, excl_cyto=(2,))
    N_, Cy = r.meas["nucleus"], r.meas["cytoplasm"]
    bsn = N_.mean[:, 0, :] - N_.background[:, 0][:, None]
    bsc = Cy.mean[:, 0, :] - Cy.background[:, 0][:, None]

    def get(comp, q):
        return C.measure_data(r, comp, q, 3)
    d, c = get("nucleus", "Raw intensity GFP")
    ok("A raw intensity = the ROI mean", np.allclose(d, N_.mean[:, 0, :]))
    d, c = get("nucleus", "Background GFP")
    ok("A background = the region mean, one column (a dish measure)",
       d.shape == (10, 1) and np.allclose(d[:, 0], N_.background[:, 0]) and c == [0])
    d, c = get("nucleus", "ΔF/F0 GFP")
    ok("A ΔF/F0 = F/F0 - 1 (baseline T3)", np.allclose(d, bsn / bsn[2] - 1))
    rr = (N_.mean[:, 0, :] - N_.background[:, 0][:, None]) / \
         (N_.mean[:, 1, :] - N_.background[:, 1][:, None])
    d, c = get("nucleus", "ΔR/R0 GFP/Cy5")
    ok("A ΔR/R0 = R/R0 - 1", np.allclose(d, rr / rr[2] - 1))
    d, c = get("nucleus", "Sum intensity GFP")
    ok("A sum intensity = (mean - background) x area px", np.allclose(d, bsn * N_.area_px))
    d, c = get("nucleus", "Area")
    ok("A area in um2 = px x 0.5²", np.allclose(d, N_.area_px * 0.25))
    d, c = get("nucleus", "Comp. ratio GFP ÷ cytoplasm")
    ok("A nucleus / cytoplasm ratio per cell, cells in both compartments",
       np.allclose(d, bsn / bsc) and c == [0, 1, 3, 4], f"{c}")
    d, c = get("nucleus", "Comp. ratio/R0 GFP ÷ cytoplasm")
    ok("A compartment ratio ÷ baseline", np.allclose(d, (bsn / bsc) / (bsn / bsc)[2]))
    ok("A every V2.4 quantity is unchanged",
       np.allclose(get("nucleus", "F/F0 GFP")[0], bsn / bsn[2]) and
       np.allclose(get("nucleus", "R/R0 GFP/Cy5")[0], rr / rr[2]))
    qs = C.common_quantities([r], "nucleus")
    ok("A on offer: R/R0 first, compartment ratios included",
       qs[0].startswith("R/R0") and "Comp. ratio GFP ÷ cytoplasm" in qs and "Area" in qs)
    m = XP.Measure("nucleus", "Comp. ratio GFP ÷ cytoplasm")
    ok("A in words", m.text() == "Compartment ratio of GFP in the nucleus over the cytoplasm"
       and XP.Measure("nucleus", "Area").text() == "Area of the nucleus", m.text())
    sp = XP.Spec(y=m, x=m)
    ok("A warning: X = Y", any("same measure" in t for t in sp.problems()))
    bg = XP.Measure("nucleus", "Background GFP")
    sp = XP.Spec(y=XP.Measure("nucleus", "F/F0 GFP"), x=bg, points="cells_at")
    ok("A warning: background per cell", any("not per cell" in t for t in sp.problems()))
    lines, _w = XP.pair_lines(sp, [("d1", [r])], "runs", None, True)
    ok("A background vs F/F0 is drawn per timepoint, not paired per cell",
       len(lines) == 1 and lines[0].points == "trajectory" and lines[0].x.shape == (10, 1)
       and lines[0].y.shape == (10, 5))
    return r


def part_bc(r1):
    print("\n=== B) run tree and groups ===", flush=True)
    from peterpiper.gui import comparewin as CW
    CW.CompareWindow.ASK_UNKNOWN = False
    cw = CW.CompareWindow()
    runs = {
        "A old": make_run("A_old", 2, nd2="movieA.nd2", saved="2026-11-01T10:00:00"),
        "A new": make_run("A_new", 3, nd2="movieA.nd2", saved="2026-11-02T10:00:00"),
        "B": make_run("B", 4, nd2="movieB.nd2", saved="2026-11-01T12:00:00"),
        "C": make_run("C", 5, nd2="movieC.nd2", saved="2026-11-01T13:00:00"),
    }
    for lab, r in runs.items():
        cw._runs[r.path] = r
        r.label = lab
        cw._insert_row(r.path, {"nd2": r.nd2, "n_cells": 5, "baseline": r.baseline,
                                "saved": r.saved, "nd2_path": f"D:/data/{r.nd2}",
                                "fingerprint": {"quick": r.nd2, "size": 100}})
        cw._labels[r.path] = lab
    cw._mark_duplicates()
    P = {k: r.path for k, r in runs.items()}
    fo = cw.folder_of(P["A new"])
    ok("B two analyses of movieA are one movie folder, newest first",
       fo is not None and fo is cw.folder_of(P["A old"]) and fo.childCount() == 2 and
       fo.child(0).data(0, CW.PATH_ROLE) == P["A new"] and cw.folder_of(P["B"]) is None,
       fo.text(CW.COL_LABEL) if fo else "")
    ok("B the folder says what it is", fo is not None and "2 analyses" in fo.text(CW.COL_LABEL))
    ok("B every run still listed, Cell line dropdowns attached",
       set(cw._paths) == set(P.values()) and
       all(cw.tree.itemWidget(cw._items[q], CW.COL_LINE) is cw._combos[q] for q in P.values()))
    cw._use(P["A old"]).setCheckState(Qt.Checked)
    cw._use(P["A new"]).setCheckState(Qt.Checked)
    ok("B Each run: two analyses of one movie may be compared (with the red note)",
       cw._is_on(P["A new"]) and cw._is_on(P["A old"]) and "same .nd2" in cw.duplicate_warning())
    cw._use(P["A new"]).setCheckState(Qt.Unchecked)
    cw.set_mode("dishes")
    cw._use(P["A new"]).setCheckState(Qt.Checked)
    ok("B Groups: one analysis per movie - ticking the newest unticks the older one",
       cw._is_on(P["A new"]) and not cw._is_on(P["A old"]) and
       fo.checkState(CW.COL_USE) == Qt.Checked)
    fo.setCheckState(CW.COL_USE, Qt.Unchecked)
    ok("B unticking the folder unticks its analysis", not cw._is_on(P["A new"]))
    fo.setCheckState(CW.COL_USE, Qt.Checked)
    ok("B ticking the folder ticks its newest analysis", cw._is_on(P["A new"]))
    for k in ("B", "C"):
        cw._use(P[k]).setCheckState(Qt.Checked)
    ok("B ticked rows bold, others dimmed",
       cw._items[P["B"]].font(CW.COL_LABEL).bold() and
       not cw._items[P["A old"]].font(CW.COL_LABEL).bold())
    # groups panel
    cw.tree.clearSelection()
    cw._items[P["A new"]].setSelected(True)
    cw._items[P["B"]].setSelected(True)
    cw.put_selected_in("U2OS")
    cw.tree.clearSelection()
    cw._items[P["C"]].setSelected(True)
    cw.put_selected_in("IHH")
    gnames = [cw.tree.topLevelItem(i).text(CW.COL_LABEL)
              for i in range(cw.tree.topLevelItemCount())]
    ok("B put selected runs in a group: the groups, the mode, the Group column",
       [g for g, _r in cw.groups()] == ["U2OS", "IHH"] and cw.mode() == "dishes" and
       cw._cells[P["B"]][CW.COL_GROUP].text() == "U2OS" and gnames == ["U2OS", "IHH"],
       f"{cw.groups()} {gnames}")
    u = cw._gfolders["U2OS"]
    ok("B the list is folders by group: U2OS holds its 2 dishes, both plotted",
       u.text(CW.COL_VER) == "2 of 2 dishes plotted" and u.childCount() == 2 and
       u.checkState(CW.COL_USE) == Qt.Checked and cw._items[P["B"]].parent() is u,
       (u.text(CW.COL_VER), u.childCount()))
    ok("B the movie folder sits inside its group folder (A's two analyses)",
       cw.folder_of(P["A new"]) is not None and cw.folder_of(P["A new"]).parent() is u and
       cw.folder_of(P["A old"]) is cw.folder_of(P["A new"]))
    lines, *_ = cw.current()
    ok("B the graph shows the groups (mean of dish means)",
       [g.label for g in lines] == ["U2OS", "IHH"] and lines[0].n_dishes == 2)
    cw.tree.setCurrentItem(cw._gfolders["IHH"])
    from PySide6.QtWidgets import QInputDialog
    QInputDialog.getText = staticmethod(lambda *a, **k: ("IHH renamed", True))
    cw._rename_group()
    ok("B rename a group: its runs follow", cw._groups[P["C"]] == "IHH renamed")
    cw.tree.setCurrentItem(cw._gfolders["IHH renamed"])
    cw._delete_group()
    ok("B delete a group: its runs stay, ungrouped (in 'No group')",
       cw._groups[P["C"]] == "" and P["C"] in cw._paths and
       cw._items[P["C"]].parent() is cw._gfolders[""])
    cw._gfolders["U2OS"].setCheckState(CW.COL_USE, Qt.Unchecked)
    ok("B unticking a group folder unticks its dishes",
       not cw._is_on(P["B"]) and not any(cw._is_on(P[k]) for k in ("A new", "A old")))
    cw._gfolders["U2OS"].setCheckState(CW.COL_USE, Qt.Checked)
    ok("B ticking a group folder ticks its dishes (the newest analysis of a movie)",
       cw._is_on(P["B"]) and cw._is_on(P["A new"]) and not cw._is_on(P["A old"]))
    ok("B Version column says which analysis", "newest" in
       cw._cells[P["A new"]][CW.COL_VER].text(), cw._cells[P["A new"]][CW.COL_VER].text())
    cw.tree.clearSelection()
    cw._items[P["B"]].setSelected(True)
    cw._ungroup_selected()
    ok("B take out of group", cw._groups[P["B"]] == "")
    QInputDialog.getText = staticmethod(lambda *a, **k: ("Empty one", True))
    cw._new_group()
    ok("B a new empty group is listed (and remembered)", "Empty one" in cw._all_groups() and
       "Empty one" in (CW.load_prefs().get("group_names") or []))

    ok("B resizing: dividers cannot collapse a part; minimum window size; settings scroll",
       not cw.hsplit.childrenCollapsible() and not cw.vsplit.childrenCollapsible() and
       cw.minimumWidth() >= 900 and cw.vsplit.widget(1).__class__.__name__ == "QScrollArea")
    print("\n=== C) graph ===", flush=True)
    cw.set_groups({P["A new"]: "U2OS", P["B"]: "U2OS", P["C"]: "IHH"}, ask=False)
    cw.set_mode("runs")
    cw._recompute()
    cw.row_y.set_measure(XP.Measure("nucleus", "F/F0 GFP"))
    ok("C defaults: Y error bars on, X error bars off, each cell off",
       cw.chk_yerr.isChecked() and not cw.chk_xerr.isChecked() and not cw.chk_cells.isChecked())
    cw.refresh()
    import pyqtgraph as pg
    bars = [i for i in cw.plot.items() if isinstance(i, pg.ErrorBarItem)]
    ok("C time course: one set of Y error bars per line", len(bars) == 3, f"{len(bars)}")
    cw.chk_yerr.setChecked(False)
    bars = [i for i in cw.plot.items() if isinstance(i, pg.ErrorBarItem)]
    ok("C Y error bars off", len(bars) == 0)
    cw.chk_yerr.setChecked(True)
    cw.chk_cells.setChecked(True)
    n_items = len([i for i in cw.plot.items() if isinstance(i, pg.PlotDataItem)])
    ok("C each cell: 5 faint cell lines behind each of 3 means", n_items == 3 * 5 + 3, f"{n_items}")
    cw.chk_cells.setChecked(False)
    main = cw._hover_pts[0][-1]
    main.setVisible(False)
    app.processEvents()
    shown = [i.isVisible() for i in cw.plot.items() if isinstance(i, pg.ErrorBarItem)]
    ok("C hiding a line (legend click) hides its error bars, not the others'",
       shown.count(False) == 1 and shown.count(True) == 2, f"{shown}")
    main.setVisible(True)
    vb = cw.plot.getViewBox()
    cw.plot.resize(800, 600)
    app.processEvents()
    vb.autoRange()
    app.processEvents()
    _n, x, m, *_r = cw._hover_pts[0]
    pos = vb.mapViewToScene(QPointF(float(x[5]), float(m[5])))
    cw._hover(pos)
    ok("C hover readout: the point's values with its error (SD by default)",
       "F/F0 GFP = " in cw.lbl_hover.text() and "±" in cw.lbl_hover.text() and
       "(SD)" in cw.lbl_hover.text(), cw.lbl_hover.text())
    ok("C the default error is SD (V2.8), remembered", cw.style.error == "SD" and
       CW.load_prefs()["view"].get("error") in (None, "SD"))
    cw.row_x.set_measure(None, first=XP.TIMEPOINT)
    lines, *_ = cw.current()
    ok("C X = Timepoint: timepoints from the baseline",
       lines[0].x_label == "Timepoints from baseline" and lines[0].x[2] == 0,
       lines[0].x_label)
    cw.row_x.set_measure(XP.Measure("cytoplasm", "Intensity GFP"))
    cw.row_y2.set_measure(XP.Measure("nucleus", "Area"))
    cw.refresh()
    ok("C right axis against a measure", cw.plot.getAxis("right").isVisible() and
       "right Y axis" in cw.lbl_sentence.text())
    bars = [i for i in cw.plot.items() if isinstance(i, pg.ErrorBarItem)]
    ok("C X error bars off by default with X = a measure", len(bars) == 3, f"{len(bars)}")
    cw.chk_xerr.setChecked(True)
    bars = [i for i in cw.plot.items() if isinstance(i, pg.ErrorBarItem)]
    ok("C X error bars on", len(bars) == 6, f"{len(bars)}")
    cw.row_x.set_measure(XP.Measure("nucleus", "F/F0 GFP"))
    ok("C red warning for X = Y", not cw.lbl_problem.isHidden() and "same measure" in
       cw.lbl_problem.text())
    cw.row_x.set_measure(XP.Measure("cytoplasm", "Intensity GFP"))
    ok("C explanations on hover for every entry",
       all(cw.row_y.cmb_kind.itemData(i, Qt.ToolTipRole) for i in range(cw.row_y.cmb_kind.count()))
       and all(cw.cmb_mode.itemData(i, Qt.ToolTipRole) for i in range(cw.cmb_mode.count()))
       and all(cw.cmb_graph.itemData(i, Qt.ToolTipRole) for i in range(cw.cmb_graph.count()))
       and all(cw.cmb_points.itemData(i, Qt.ToolTipRole) for i in range(cw.cmb_points.count()))
       and all(cw.cmb_err.itemData(i, Qt.ToolTipRole) for i in range(cw.cmb_err.count())))
    scat = [i for i in cw.plot.items() if isinstance(i, pg.ScatterPlotItem)]
    ok("C trajectory: a start and an end marker per line (3 lines)", len(scat) >= 6, f"{len(scat)}")
    files = cw.save_to(str(OUT / "saved"), "pairs", formats=["prism", "png", "csv"], quiet=True)
    from peterpiper import outlog
    e = outlog.entries()
    ok("C every save is in the saved-files log (newest first, all its files)",
       bool(e) and e[0]["kind"] == "compare" and e[0]["name"] == "pairs" and
       sorted(Path(f).name for f in e[0]["files"]) == sorted(Path(f).name for f in files),
       e[0] if e else None)
    from peterpiper.gui.outlogdlg import OutputsDialog
    dlg = OutputsDialog()
    ok("C 'Saved files...' lists it, with its files", dlg.table.rowCount() >= 1 and
       dlg.files.count() == len(files), (dlg.table.rowCount(), dlg.files.count()))
    dlg.close()
    ok("C save Y vs X with a right axis: .prism, .png, .csv + right-axis .csv",
       sorted(Path(f).name for f in files) == ["pairs.csv", "pairs.png", "pairs.prism",
                                              "pairs_right_axis.csv"], f"{files}")
    cw.row_y2.set_measure(None)
    cw.cmb_points.setCurrentIndex(cw.cmb_points.findData("cells_at"))
    crosses = [i for i in cw.plot.items() if isinstance(i, pg.ErrorBarItem)]
    ok("C dot plot: a mean ± error cross per line", len(crosses) >= 3, f"{len(crosses)}")
    cw.cmb_points.setCurrentIndex(cw.cmb_points.findData("trajectory"))
    cw.row_x.set_measure(None, first=XP.TIME)
    cw.row_y.set_measure(XP.Measure("nucleus", "Comp. ratio GFP ÷ cytoplasm"))
    cw.set_mode("dishes")
    files2 = cw.save_to(str(OUT / "saved"), "ncratio", formats=["prism", "png", "csv"],
                        quiet=True, kinetics=[])
    ok("C save an N/C ratio time course of groups", len(files2) >= 3, f"{files2}")
    cw.close()
    return [f for f in files + files2 if f.endswith(".prism")]


def part_d(prisms):
    print("\n=== D) Prism 11 ===", flush=True)
    import test_prism_style as TPS
    d = OUT / "prism"
    d.mkdir(exist_ok=True)
    for f in prisms:
        shutil.copy2(f, d / Path(f).name)
    log = TPS.render(d, [Path(f).stem for f in prisms], "v28")
    ok("D Prism opens the V2.8 .prism files COMPLETE", "COMPLETE" in log and "PROBLEM" not in log,
       log.strip()[:200])


def main() -> int:
    r = part_a()
    prisms = part_bc(r)
    if "--no-prism" not in sys.argv:
        part_d(prisms)
    print(f"\n{N[0]} / {N[0] + len(FAILS)} checks passed")
    for f in FAILS:
        print("  FAILED:", f)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
