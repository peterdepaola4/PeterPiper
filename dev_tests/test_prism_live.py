"""
Developer test (not shipped): the live graph's look reaches every .prism the
app writes, checked in the real GraphPad Prism 11.

    MPLBACKEND=Agg QT_QPA_PLATFORM=offscreen python dev_tests/test_prism_live.py [--keep]

GUI offscreen on the nucleus file: AUTO-DETECT, TRACK, 'As exported' view; for
several looks set in the trace panel (SD, red mean, each cell, Y range, shaded
band, hidden mean) the panel's Prism note is checked, then 'Save this graph'
(.prism) and the main export ('Prism graphs') are written. All .prism files are
opened in ONE Prism session (script: Open / ExportSVG / ExportPNG / Close) and
measured against the live graph's own numbers (graphstyle.stats of the
panel's series): error-bar lengths, colours, line widths, cell lines, axis range;
the band look must render as error bars, the hidden mean as a hairline.
Never kills a prism.exe it did not start; if Prism is already running it waits
(up to 5 min) and then skips the Prism part. Exit code 0 = every check passed.
"""
from __future__ import annotations

import labdata  # noqa: E402  (lab file names: dev_tests/lab_paths.json, never uploaded)

import os
import shutil
import subprocess
import sys
import time
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
OUT = REPO / "_out" / "prism_live"
if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True)
os.environ["PETERPIPER_HOME"] = str(OUT / "home")
os.environ.setdefault("MPLCONFIGDIR", str(OUT / "home" / "mpl"))

import test_prism_style as TPS                                     # noqa: E402  (helpers)
from PySide6.QtWidgets import QApplication, QMessageBox             # noqa: E402

app = QApplication(sys.argv)
app.setStyle("Fusion")
for _n in ("information", "warning", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: QMessageBox.Ok))
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)
QMessageBox.exec = lambda self: 0

from peterpiper import graphstyle as GS                                # noqa: E402
from peterpiper.config import Settings                                 # noqa: E402
from peterpiper.export import catalog                                  # noqa: E402
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
from peterpiper.gui.traces import VIEW_EXPORTED                        # noqa: E402
from peterpiper.nd2io import describe, open_source                     # noqa: E402

NUC = labdata.T("t02")
from labdata import need                                    # noqa: E402
need(NUC, what="test_prism_live.py")            # V3.0: lab data only
SHEET = "dRR_GFP_over_Cy5"
ClickWindow._ask_previous_run = lambda self, runs, menu=False: None
ClickWindow._ask_save_graph = lambda self, what, folder, name: (str(OUT / "saved"), name,
                                                                ["prism"])
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


LOOKS = {
    "sd": dict(error="SD"),
    "red": dict(mean_colour="#D62728", mean_width=2.0),
    "cells": dict(show_cells=True, cell_colour="#1F77B4", cell_width=0.75),
    "yrange": dict(y_min=0.0, y_max=3.0),
    "band": dict(error_style="band", symbol="none", mean_width=1.5, mean_colour="#1F6FE0"),
    "nomean": dict(show_mean=False, error="none", show_cells=True, cell_colour="#404040",
                   cell_width=0.75),
}


def prism_busy() -> bool:
    r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq prism.exe"], capture_output=True,
                       text=True)
    return "prism.exe" in r.stdout.lower()


def main() -> int:
    src = open_source(NUC)
    exp = describe(src, out_dir=str(OUT / f"OUTPUT_{Path(NUC).stem}"))
    exp.export_tiffs = False
    os.makedirs(exp.out_dir, exist_ok=True)
    w = ClickWindow(src, exp, Settings(baseline_timepoint=1))
    w.resize(1700, 1000)
    w.show()
    t = time.time()
    while not w._offered and time.time() - t < 30:
        pump(0.1)
    wait(w)
    w._auto_select()
    wait(w)
    w._track()
    wait(w)
    ok("tracked", w.track is not None)
    tr = w.traces
    tr.set_view(VIEW_EXPORTED)
    pump(0.3)
    render_dir = OUT / "render"
    render_dir.mkdir()
    expect = {}
    for name, look in LOOKS.items():
        st = GS.GraphStyle(**look)
        tr._change_style(st)                   # as the controls do: emits, settings follow
        pump(0.3)
        ok(f"{name}: Settings.graph_style = the panel's look",
           GS.coerce(w.settings.graph_style) == st)
        warn = tr.prism_warnings()
        want_warn = name in ("band", "nomean")
        ok(f"{name}: Prism note {'shown' if want_warn else 'hidden'}",
           tr.lbl_prism.isVisible() == want_warn and bool(warn) == want_warn,
           tr.lbl_prism.text())
        x, y, names, _xl, _yl = tr.current_series()
        m, lo, hi, n = GS.stats(y, st.error if st.show_mean else "none")
        expect[name] = dict(style=st, x=x, y=y, lo=lo, hi=hi, m=m)
        # 'Save this graph' (.prism only)
        tr.btn_save.click()
        wait(w)
        saved = [f for f in (getattr(w, "_graph_saved", []) or []) if f.endswith(".prism")]
        ok(f"{name}: Save this graph wrote a .prism", len(saved) == 1)
        # main export: Prism graphs of this quantity
        comps = w._export_data()
        keys = [it["key"] for it in catalog(comps, w.settings)
                if it["key"] in ("nucleus|prismgraph", "nucleus|graph|" + SHEET)]
        w._run_export(comps, keys)
        wait(w)
        prs = sorted((Path(w._exported or "") / "Nucleus" / "Prism graphs").glob("*.prism"))
        ok(f"{name}: main export wrote one .prism", len(prs) == 1)
        for tag, f in (("save", saved[:1]), ("export", prs[:1])):
            if f:
                shutil.copy(f[0], render_dir / f"{name}_{tag}.prism")
        time.sleep(1.1)                         # next export folder gets a new name
    w._dirty = False
    w.close()
    pump(0.3)

    if not TPS.PRISM.exists():
        print("SKIP: GraphPad Prism is not installed here")
        return 0 if all(checks) else 1
    t = time.time()
    while prism_busy() and time.time() - t < 300:
        time.sleep(5)
    if prism_busy():
        print("SKIP: Prism is already running (not started by this test) - not touched")
        return 0 if all(checks) else 1
    stems = sorted(p.stem for p in render_dir.glob("*.prism"))
    log = TPS.render(render_dir, stems, "live")
    ok("Prism session: COMPLETE! No Errors.", "COMPLETE! No Errors." in log, log.strip()[-200:])
    for stem in stems:
        name = stem.rsplit("_", 1)[0]
        e = expect[name]
        st, y = e["style"], e["y"]
        svgp = render_dir / f"{stem}.svg"
        if not svgp.exists():
            ok(f"{stem}: rendered", False)
            continue
        svg = TPS.Svg(svgp)
        half = e["hi"] - e["m"]
        with_bar = np.isfinite(half) & (half > 0)
        if name in ("sd", "band", "red", "cells"):
            cnt, tot = TPS.vbar_sum(svg)
            exp_tot = float(np.nansum((e["hi"] - e["lo"])[with_bar]))
            err = st.error
            # Prism's SVG coordinates come in 0.12 pt steps: on a tall axis (each cell
            # shown, outlier cells) a short bar is only known to +/- 0.12 pt per line,
            # and a bar shorter than that may not be drawn at all
            # (V2.7: both ends of every drawn segment are rounded - with the automatic
            # tick interval Prism draws a bar as one segment, not two halves, which
            # halved the old cnt-based allowance)
            tol = max(0.02 * exp_tot, 2 * cnt * 0.12 * svg.y_per_pt())
            ok(f"{stem}: error bars = live graph's {err} ({cnt} bars, total {tot:.4f} vs "
               f"{exp_tot:.4f}, tolerance {tol:.4f})",
               2 * int((2 * half[with_bar] >= 0.24 * svg.y_per_pt()).sum()) <= cnt
               <= 2 * int(with_bar.sum()) and abs(tot - exp_tot) <= tol)
        pl = svg.polylines()
        col = {p.get("stroke", "").lower() for p in pl}
        if name == "red":
            mm = [p for p in pl if p.get("stroke", "").lower() == "#d62728"]
            ok(f"{stem}: mean line #d62728, {TPS.qw(2.0)} pt",
               len(mm) == 1 and abs(float(mm[0]["stroke-width"]) - TPS.qw(2.0)) < 0.01)
            ok(f"{stem}: PNG has the red", TPS.png_has_colour(render_dir / f"{stem}.png",
                                                             (0xD6, 0x27, 0x28))[0])
        if name in ("cells", "nomean"):
            c = st.cell_colour.lower()
            # every path in the cell colour (V3.0: a cell the ratio check left with only a
            # few values is a short line - svg.polylines() keeps only lines of 10+ segments)
            cl = [p for p in svg.paths if p.get("stroke", "").lower() == c
                  and p.get("fill") == "none" and "C" not in p.get("d", "")
                  and p.get("d", "").count("L") >= 1]
            n_lines = int(np.isfinite(y).any(axis=0).sum())   # V3.0: cells the ratio check
            ok(f"{stem}: {n_lines} cell lines in {c}, {TPS.qw(st.cell_width)} pt "  # left out
               f"({y.shape[1] - n_lines} of {y.shape[1]} cells have no value)",       # draw none
               len(cl) == n_lines and all(abs(float(p["stroke-width"]) -
                                                 TPS.qw(st.cell_width)) < 0.01 for p in cl),
               f"found {len(cl)} of {sorted(col)}")
        if name == "yrange":
            ys, _ = svg.ticks()
            vals = [v for _, v in ys]
            ok(f"{stem}: Y axis {st.y_min}..{st.y_max} as the live graph",
               abs(min(vals) - st.y_min) < 1e-9 and abs(max(vals) - st.y_max) < 1e-9, str(vals))
        if name == "band":
            ok(f"{stem}: band drawn as error bars in the mean colour",
               len([a for a in svg.lines if a.get("stroke", "").lower() == "#1f6fe0"]) > 0)
            ok(f"{stem}: no symbols (as the live look)", len(svg.symbols()) == 0)
        if name == "nomean":
            ok(f"{stem}: hidden mean -> no error bars, no symbols",
               TPS.vbar_sum(svg)[0] == 0 and len(svg.symbols()) == 0)
            hl = [p for p in pl if p.get("stroke", "").lower() == st.mean_colour.lower()]
            ok(f"{stem}: ... the mean as a {TPS.qw(0.12)} pt hairline",
               len(hl) == 1 and abs(float(hl[0]["stroke-width"]) - 0.12) < 0.01,
               str([(p.get("stroke"), p.get("stroke-width")) for p in hl]))
    print(f"\n{sum(checks)} / {len(checks)} checks passed")
    if "--keep" not in sys.argv:
        shutil.rmtree(render_dir, ignore_errors=True)
    return 0 if all(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
