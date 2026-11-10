"""
Developer test for the graph style (graphstyle.py), the live trace panel's
'As exported' view (gui/traces.py) and the PNG / CSV export (export.py).

    python dev_tests/test_graph.py [output folder]

Run offscreen (no window appears):
    set PETERPIPER_HOME=<scratch>\\_home  MPLBACKEND=Agg  QT_QPA_PLATFORM=offscreen
    (QT_QPA_FONTDIR=C:/Windows/Fonts makes the offscreen screenshots show text)

It writes screenshots / PNGs into the output folder (default
$PETERPIPER_HOME/out/graph_test) and exits with 1 if any check fails.
Not shipped: the app is in app/, this folder is for developers.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
os.environ.setdefault("MPLBACKEND", "Agg")
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    os.environ.get("PETERPIPER_HOME", tempfile.gettempdir())) / "out" / "graph_test"
OUT.mkdir(parents=True, exist_ok=True)

errors: list = []
sys.excepthook = lambda k, v, tb: errors.append("".join(traceback.format_exception(k, v, tb)))
checks: list = []


def ok(name: str, cond, extra: str = "") -> None:
    checks.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra else ""), flush=True)


def same(a, b) -> bool:
    """Bit-identical arrays (NaN == NaN)."""
    a, b = np.asarray(a), np.asarray(b)
    return a.shape == b.shape and np.array_equal(a, b, equal_nan=True)


def close(a, b, tol=1e-12) -> bool:
    a, b = np.asarray(a, float), np.asarray(b, float)
    if a.shape != b.shape or not np.array_equal(np.isnan(a), np.isnan(b)):
        return False
    m = ~np.isnan(a)
    return bool(np.all(np.abs(a[m] - b[m]) <= tol * np.maximum(1.0, np.abs(b[m]))))


from peterpiper import graphstyle as GS                         # noqa: E402
from peterpiper.config import Experiment, Settings              # noqa: E402
from peterpiper.measure import Measurements                     # noqa: E402


# ==========================================================================
#  synthetic data: T=40, C=2 (GFP rises, Cy5 flat), N=8 cells, a few NaNs
# ==========================================================================
def synthetic(T=40, C=2, N=8, seed=1) -> Measurements:
    rng = np.random.default_rng(seed)
    t = np.arange(T)
    resp = 1 + 0.8 / (1 + np.exp(-(t - 15) / 3))
    mean = np.empty((T, C, N))
    for k in range(N):
        mean[:, 0, k] = 1000 * (1 + 0.1 * k) * resp * (1 + 0.03 * rng.normal(size=T)) + 100
        mean[:, 1, k] = 800 * (1 + 0.05 * k) * (1 + 0.02 * rng.normal(size=T)) + 100
    mean[5, 0, 2] = np.nan            # one missing value
    mean[20, :, 4] = np.nan           # a lost cell at one timepoint
    mean[30:, :, 6] = np.nan          # a cell that leaves the field
    bg = 100.0 + rng.normal(size=(T, C))
    return Measurements(mean=mean, background=bg, area_px=np.full((T, N), 50.0),
                        n_saturated=np.zeros((T, C, N)), quality=np.ones((T, N)),
                        channels=["GFP", "Cy5"])


# ==========================================================================
#  a) statistics
# ==========================================================================
def hand_stats(y):
    """Per timepoint, the textbook way (loop over rows; finite values only)."""
    from scipy import stats as sst
    T = y.shape[0]
    m, sd, sem, ci, n = (np.full(T, np.nan) for _ in range(5))
    for i in range(T):
        v = y[i][np.isfinite(y[i])]
        n[i] = v.size
        if v.size:
            m[i] = v.sum() / v.size
        if v.size >= 2:
            sd[i] = np.sqrt(((v - v.mean()) ** 2).sum() / (v.size - 1))
            sem[i] = sd[i] / np.sqrt(v.size)
            ci[i] = sst.t.ppf(0.975, v.size - 1) * sem[i]
            # scipy's own SEM agrees
            assert abs(sst.sem(v) - sem[i]) < 1e-12 * max(1, abs(sem[i]))
    return m, sd, sem, ci, n


def test_stats() -> None:
    rng = np.random.default_rng(7)
    y = rng.normal(2.0, 0.7, size=(30, 6))
    y[rng.random(y.shape) < 0.15] = np.nan
    y[3, :] = np.nan                     # nobody
    y[4, 1:] = np.nan                    # one cell only
    y[5, 2:] = np.nan                    # two cells
    s = GS.describe(y)
    m, sd, sem, ci, n = hand_stats(y)
    ok("stats: mean = hand-computed", close(s.mean, m))
    ok("stats: SD (n-1) = hand-computed", close(s.sd, sd))
    ok("stats: SEM = SD/sqrt(n) = hand-computed (and scipy.stats.sem)", close(s.sem, sem))
    ok("stats: 95% CI = t(0.975,n-1) x SEM", close(s.ci95, ci))
    ok("stats: n per timepoint", same(s.n, n.astype(int)), str(s.n[:8]))
    ok("stats: n<2 -> SD/SEM/CI empty", np.isnan(s.sem[[3, 4]]).all() and np.isnan(s.ci95[4])
       and np.isfinite(s.sem[5]))
    for e, err in (("SEM", sem), ("SD", sd), ("95% CI", ci)):
        mm, lo, hi, nn = GS.stats(y, e)
        ok(f"stats('{e}'): low/high = mean -/+ {e}", close(lo, m - err) and close(hi, m + err)
           and same(nn, n.astype(int)))
    mm, lo, hi, nn = GS.stats(y, "none")
    ok("stats('none'): low = high = mean", same(lo, mm) and same(hi, mm))
    mm, lo, hi, nn = GS.stats(np.zeros((5, 0)), "SEM")
    ok("stats: no cells -> NaN mean, n = 0", np.isnan(mm).all() and (nn == 0).all())
    # 95% CI for n = 2 uses t = 12.706
    two = np.array([[1.0, 3.0]])
    ok("stats: 95% CI n=2 uses t=12.706", abs(GS.describe(two).ci95[0] - 12.7062047 * 1.0) < 1e-6)
    # float32 input keeps its own precision (V2.2 arithmetic)
    y32 = y.astype(np.float32)
    with np.errstate(invalid="ignore"):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            ref = np.nanmean(y32, axis=1)
    ok("stats: float32 data handled like V2.2 (no silent up-cast)", same(GS.describe(y32).mean, ref))


def v22_csv_stats(y, on):
    """V2.2's CSV formula, verbatim (export.py before V2.3)."""
    T = y.shape[0]
    with np.errstate(invalid="ignore"):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            n = np.sum(np.isfinite(y), axis=1)
            m = np.nanmean(y, axis=1) if on else np.full(T, np.nan)
            sem = (np.nanstd(y, axis=1, ddof=1) / np.sqrt(np.maximum(n, 1))
                   if len(on) > 1 else np.full(T, np.nan))
    return m, sem, n


def test_csv_unchanged() -> None:
    from peterpiper.plots import _panels
    M = synthetic()
    s = Settings()
    s.baseline_timepoint = 5
    for on in ([0, 1, 2, 3, 4, 5, 6, 7], [0, 2, 4, 6], [3], []):
        bad = []
        for name, data, *_ in _panels(M, s):
            y = data[:, on] if on else np.zeros((M.n_timepoints, 0))
            m0, sem0, n0 = v22_csv_stats(y, on)
            d = GS.describe(y)
            if not (same(d.mean, m0) and same(d.sem, sem0) and same(d.n, n0)):
                bad.append(name)
        ok(f"CSV mean/SEM/n bit-identical to V2.2 formula (included = {on})", not bad, str(bad))


def run_export_csv(module, out_root: Path, M: Measurements, style=None):
    exp = Experiment(nd2_path=str(out_root / "synthetic.nd2"), channels=list(M.channels),
                     n_timepoints=M.n_timepoints, seconds_per_frame=30.0)
    s = Settings()
    s.baseline_timepoint = 5
    s.resp_quantity = "R/R0 - GFP/Cy5"
    s.ratio_min_snr = 0.0           # V3.0: the ratio check off - V2.2 had none
    if style is not None:
        s.graph_style = style
    inc = {k: (0 if k in (5, 7) else 1) for k in range(M.n_cells)}
    comps = {"nucleus": dict(label="Nucleus", name="nucleus", M=M, cells=list(range(M.n_cells)),
                             include=inc, why={}, qc=None, seeds=None, channel=0, rois=None)}
    keys = ["nucleus|csv", "nucleus|graph|dRR_GFP_over_Cy5", "nucleus|graph|dFF_GFP"]
    return module.run_export(str(out_root), exp, s, comps, keys)


def test_csv_files_vs_v22() -> None:
    """Run the V2.2 export.py (from git) and this one on the same data: every
    CSV file must be byte-identical."""
    M = synthetic()
    try:
        import pd4nav_history                       # PD4nav's history (PeterPiper's earlier name)
        src = pd4nav_history.show("8e31298", "export.py")
    except Exception as e:                                  # noqa: BLE001
        ok("CSV files vs V2.2 export.py", False, f"could not read V2.2 from git: {e}")
        return
    p = OUT / "export_v22.py"
    p.write_bytes(src)
    spec = importlib.util.spec_from_file_location("peterpiper._export_v22", p)
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    from peterpiper import export as new
    r_old = run_export_csv(old, OUT / "v22", M)
    time.sleep(1.1)                                        # a different Export_<time> folder
    r_new = run_export_csv(new, OUT / "v23", M)
    a = sorted(f for f in r_old["files"] if f.endswith(".csv"))
    b = sorted(f for f in r_new["files"] if f.endswith(".csv"))
    ok("CSV: same number of CSV files as V2.2", len(a) == len(b) and len(a) > 0, f"{len(a)}")
    def no_sd(path):                # V3.0 adds an SD column at the end of every row
        rows_ = Path(path).read_bytes().decode("utf-8").split(chr(10))
        return chr(10).join(r.rsplit(",", 1)[0] if r else r for r in rows_).encode("utf-8")
    diff = [Path(x).name for x, y in zip(a, b) if Path(x).read_bytes() != no_sd(y)]
    ok("CSV: every CSV byte-identical to V2.2 (ratio check off, without the V3.0 SD column)",
       not diff, str(diff[:3]))
    with open(b[0], newline="") as fh:
        rows = list(csv.reader(fh))
    ok("CSV: header ends Mean, SEM, n, SD (V3.0)", rows[0][-4:] == ["Mean", "SEM", "n", "SD"],
       str(rows[0][-4:]))
    sd_ok = True
    for r in rows[1:]:
        vals = [float(v) for v in r[2:-4] if v != ""]
        if len(vals) >= 2 and r[-1] != "":
            sd_ok &= abs(float(r[-1]) - float(np.std(vals, ddof=1))) <= 1e-5 * max(1, abs(float(r[-1])))
    ok("CSV: SD = the sample SD (n - 1) of the cells written", sd_ok)
    pngs = [f for f in r_new["files"] if f.endswith(".png")]
    ok("PNG export: 2 graphs written", len(pngs) == 2 and all(Path(f).stat().st_size > 20000
                                                             for f in pngs), str(pngs))
    from PIL import Image
    im = Image.open(pngs[0])
    ok("PNG export: 300 dpi, 6 x 4.5 in (1800 x 1350 px)",
       im.size == (1800, 1350) and round(im.info.get("dpi", (0, 0))[0]) == 300,
       f"{im.size} {im.info.get('dpi')}")
    (OUT / "export_png_default.png").write_bytes(Path(pngs[0]).read_bytes())
    # a style from the settings reaches the PNG
    r_sty = run_export_csv(new, OUT / "v23_style", M,
                           style=GS.apply_preset({}, "Shaded SEM band + each cell").to_dict())
    p2 = [f for f in r_sty["files"] if f.endswith(".png")][0]
    a1 = np.asarray(Image.open(pngs[0]).convert("RGB"), float)
    a2 = np.asarray(Image.open(p2).convert("RGB"), float)
    ok("PNG export: Settings.graph_style changes the PNG", np.abs(a1 - a2).mean() > 1.0,
       f"mean abs diff {np.abs(a1 - a2).mean():.2f}")
    (OUT / "export_png_band_cells.png").write_bytes(Path(p2).read_bytes())


def test_style_dict() -> None:
    st = GS.GraphStyle(error="SD", show_cells=True, mean_colour="#FF0000", y_min=0.5)
    d = st.to_dict()
    ok("GraphStyle: to_dict is JSON-safe and round-trips",
       GS.GraphStyle.from_dict(json.loads(json.dumps(d))) == st)
    weird = {"error": "sd", "error_style": "BAND", "mean_colour": "#abc", "mean_width": "2",
             "symbol_size": -5, "show_cells": "yes", "x_min": "auto", "y_max": "3.5",
             "font_pt": 500, "title": None, "baseline_line": 1, "nonsense": 42,
             "symbol": "hexagon", "cell_colour": "red"}
    w = GS.GraphStyle.from_dict(weird)
    ok("GraphStyle.from_dict: coerces types, ignores unknown keys, rejects bad values",
       w.error == "SD" and w.error_style == "band" and w.mean_colour == "#AABBCC"
       and w.mean_width == 2.0 and w.symbol_size == 0.0 and w.show_cells is True
       and w.x_min is None and w.y_max == 3.5 and w.font_pt == 72.0 and w.baseline_line is True
       and w.symbol == "circle" and w.cell_colour == "#C0C0C0"
       and w.title == GS.GraphStyle().title,
       str(w))
    ok("GraphStyle.from_dict(None / {} / junk) = defaults",
       GS.GraphStyle.from_dict(None) == GS.GraphStyle() == GS.GraphStyle.from_dict([1, 2]))
    names = list(GS.PRESETS)
    need = ["Prism default - mean ± SD", "Prism default - mean ± SEM", "Mean ± SEM + each cell",
            "Mean ± SD + each cell", "Mean ± 95% CI", "Shaded SEM band + each cell",
            "Each cell only"]                 # V3.0: SD default; every preset names its error
    ok("PRESETS: the required looks exist, each naming its error",
       all(n in names for n in need) and all(
           ("SEM" in n) == (GS.PRESETS[n].error == "SEM") for n in names), str(names))
    ok("PRESETS: the default look is mean ± SD", GS.DEFAULT_PRESET == "Prism default - mean ± SD"
       and GS.PRESETS[GS.DEFAULT_PRESET] == GS.GraphStyle())
    ok("PRESETS: default preset = GraphStyle()", GS.PRESETS[GS.DEFAULT_PRESET] == GS.GraphStyle())
    ok("PRESETS: every preset recognised by preset_name",
       all(GS.preset_name(GS.PRESETS[n]) == n for n in names))
    mine = GS.GraphStyle(title="My {n}", y_min=0.0, font_pt=16)
    ap = GS.apply_preset(mine, "Mean ± SD")
    ok("apply_preset keeps your titles / ranges / font", ap.title == "My {n}" and ap.y_min == 0.0
       and ap.font_pt == 16 and ap.error == "SD")
    fields = [f.name for f in GS.dataclasses.fields(GS.GraphStyle)]
    ok("PRISM_SUPPORT: one entry per field (+ data), values yes/template/no",
       set(fields) <= set(GS.PRISM_SUPPORT) and set(GS.PRISM_SUPPORT.values()) <= {"yes", "template", "no"})
    from peterpiper import prismstyle as PS
    ok("PRISM_SUPPORT = prismstyle.SUPPORT (+ data yes; legend / size no)",
       all(GS.PRISM_SUPPORT[k] == v for k, v in PS.SUPPORT.items())
       and GS.PRISM_SUPPORT["data"] == "yes" and GS.PRISM_SUPPORT["legend"] == "no")
    d, wn = GS.prism_look(GS.GraphStyle(error="SD", error_style="band"))
    ok("prism_look: band -> SD error bars + plain warning",
       d["error_style"] == "bars" and d["error"] == "SD" and len(wn) == 1 and "band" in wn[0])
    d, wn = GS.prism_look(GS.GraphStyle(show_mean=False, show_cells=True))
    ok("prism_look: hidden mean -> hairline, no symbol, no error",
       d["mean_width"] == 0.12 and d["symbol"] == "none" and d["error"] == "none" and wn)
    d, wn = GS.prism_look(GS.GraphStyle(baseline_line=True))
    ok("prism_look: dashed line at 0 -> warning only", wn and d["baseline_line"])
    ok("prism_look: default look -> no warning", GS.prism_look(GS.GraphStyle())[1] == [])
    t = GS.title_text(GS.GraphStyle(title="{file} - {comp} (n = {n}) {quantity} {other} {"),
                      "exp1", "Nucleus", "R/R0 GFP/Cy5", 7)
    ok("title_text: fills {file} {comp} {n} {quantity}, leaves other text alone",
       t == "exp1 - Nucleus (n = 7) R/R0 GFP/Cy5 {other} {", t)
    ok("title_text: empty template = no title", GS.title_text(GS.GraphStyle(title=""), "a", "b", "c", 1) == "")


# ==========================================================================
#  c) matplotlib renderer: one PNG per preset (+ SVG / PDF)
# ==========================================================================
def test_matplotlib() -> None:
    from PIL import Image
    from peterpiper.plots import _panels
    M = synthetic()
    s = Settings()
    s.baseline_timepoint = 5
    panels = {p[0]: p for p in _panels(M, s)}
    on = [0, 1, 2, 3, 4, 6]
    y = panels["dRR_GFP_over_Cy5"][1][:, on]
    exp = Experiment(channels=["GFP", "Cy5"], n_timepoints=40, seconds_per_frame=30.0)
    x, xl = exp.time_axis(40, 4)
    arrs = {}
    pdir = OUT / "presets_png"
    pdir.mkdir(exist_ok=True)
    for name, st in GS.PRESETS.items():
        st = st.copy(baseline_line=True)
        fn = pdir / ("".join(ch if ch.isalnum() else "_" for ch in name) + ".png")
        if fn.exists():
            fn.unlink()
        used = GS.save_figure(fn, x, y, [f"Cell_{k + 1}" for k in on], st, xl, "R/R0 GFP/Cy5",
                              GS.title_text(st, "synthetic", "Nucleus", "R/R0 GFP/Cy5", len(on)))
        a = np.asarray(Image.open(used).convert("L"), float)
        arrs[name] = a
        ok(f"matplotlib '{name}': not blank", a.std() > 5 and (a < 128).mean() > 0.003,
           f"std {a.std():.1f}, dark {100 * (a < 128).mean():.2f}%")
    keys = list(arrs)
    diffs = [np.abs(arrs[a] - arrs[b]).mean() for i, a in enumerate(keys) for b in keys[i + 1:]]
    ok("matplotlib: every preset looks different", min(diffs) > 0.05, f"min diff {min(diffs):.3f}")
    for ext in ("svg", "pdf"):
        fn = OUT / f"graph_default.{ext}"
        if fn.exists():
            fn.unlink()
        used = GS.save_figure(fn, x, y, [], GS.GraphStyle(legend=True), xl, "R/R0 GFP/Cy5", "t")
        head = Path(used).read_bytes()[:400]
        ok(f"save_figure: {ext.upper()} written", (b"<svg" in head) if ext == "svg"
           else head.startswith(b"%PDF"))
    used2 = GS.save_figure(OUT / "graph_default.svg", x, y, [], GS.GraphStyle(), xl, "q", "t")
    ok("save_figure: never overwrites (adds _2)", used2.endswith("graph_default_2.svg"), used2)
    Path(used2).unlink()
    # fixed axis ranges reach matplotlib
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    fig = Figure()
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    GS.draw_matplotlib(ax, x, y, [], GS.GraphStyle(x_min=-1, x_max=10, y_min=0.5, y_max=2.5),
                       xl, "q", "title")
    ok("draw_matplotlib: fixed axis ranges", ax.get_xlim() == (-1, 10) and ax.get_ylim() == (0.5, 2.5),
       f"{ax.get_xlim()} {ax.get_ylim()}")
    # the plotted mean / error bars are stats()
    fig = Figure()
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    GS.draw_matplotlib(ax, x, y, [], GS.GraphStyle(), xl, "q", "")
    m, lo, hi, n = GS.stats(y, "SD")                  # V3.0: the default error is SD
    line = [ln for ln in ax.get_lines() if ln.get_label().startswith("Mean")][0]
    ok("draw_matplotlib: mean line = stats() mean", close(line.get_ydata(), m))
    segs = [c for c in ax.collections if c.__class__.__name__ == "LineCollection"][0].get_segments()
    ok_t = np.isfinite(lo) & np.isfinite(hi)
    lo_s = np.array([sg[0][1] for sg in segs])
    hi_s = np.array([sg[1][1] for sg in segs])
    ok("draw_matplotlib: error bars = mean ± SD (the default)",
       close(lo_s, lo[ok_t]) and close(hi_s, hi[ok_t]))


# ==========================================================================
#  b) the live trace panel, driven as ClickWindow._sync_traces does
# ==========================================================================
def test_panel() -> None:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtWidgets import QApplication, QMessageBox
    app = QApplication.instance() or QApplication([])
    for n in ("information", "warning", "critical"):
        setattr(QMessageBox, n, staticmethod(lambda *a, **k: QMessageBox.Ok))
    from peterpiper.gui.traces import TracePanel, VIEW_CHECK, VIEW_EXPORTED
    from peterpiper.manual import LABELS

    def pump(sec=0.15):
        t = time.time()
        while time.time() - t < sec:
            app.processEvents()
            time.sleep(0.005)

    M = synthetic()
    exp = Experiment(nd2_path=str(OUT / "synthetic.nd2"), channels=["GFP", "Cy5"],
                     n_timepoints=40, seconds_per_frame=30.0, out_dir=str(OUT))
    w = TracePanel(exp)
    w.resize(560, 900)
    w.show()
    pump()
    live = list(range(8))
    excl = {5, 7}
    why = {k: ("excluded by you" if k in excl else "included") for k in live}
    state = {"inc": [k for k in live if k not in excl]}
    sig = {"sel": [], "time": [], "style": [], "view": [], "export": []}

    def set_include(k, on):          # what ClickWindow._set_include + _sync_traces do
        if on:
            excl.discard(k)
        else:
            excl.add(k)
        state["inc"] = [c for c in live if c not in excl]
        why2 = {c: ("excluded by you" if c in excl else "included") for c in live}
        w.set_included(state["inc"], why2)

    w.include_set.connect(set_include)
    w.cell_selected.connect(lambda k: sig["sel"].append(k))
    w.time_clicked.connect(lambda t: sig["time"].append(t))
    w.style_changed.connect(lambda d: sig["style"].append(d))
    w.view_changed.connect(lambda v: sig["view"].append(v))
    # ClickWindow._sync_traces(full=True):
    w.set_data(M, live, state["inc"], why, LABELS["nucleus"], 4, 0, ["R/R0 - GFP/Cy5", "F/F0 - GFP"])
    w.set_time(10)
    pump()
    ok("panel: opens on the preferred quantity", w.current_quantity() == "R/R0 - GFP/Cy5",
       w.current_quantity())
    from peterpiper.plots import _panels
    s = Settings()
    s.baseline_timepoint = 5
    ref = {p[0]: p[1] for p in _panels(M, s)}["dRR_GFP_over_Cy5"]
    x, y, names, xl, yl = w.current_series()
    ok("current_series: the included cells' values = the export's numbers",
       same(y, ref[:, state["inc"]]) and names == [f"Cell_{k + 1}" for k in state["inc"]]
       and xl == "Time from baseline (min)" and yl == "R/R0 GFP/Cy5", f"{y.shape} {yl}")

    def grab(name):
        pump(0.1)
        p = OUT / f"panel_{name}.png"
        w.grab().save(str(p))
        from PIL import Image
        return np.asarray(Image.open(p).convert("RGB"), float)

    def plot_area(a):
        g = w.plot.geometry()
        top = w.plot.mapTo(w, w.plot.rect().topLeft())
        return a[top.y():top.y() + g.height(), top.x():top.x() + g.width()]

    def common_diff(a, b):           # mean pixel difference over the common area
        h, wd = min(a.shape[0], b.shape[0]), min(a.shape[1], b.shape[1])
        return np.abs(a[:h, :wd] - b[:h, :wd]).mean()

    check0 = grab("check_default")
    ok("Check cells: not blank", plot_area(check0).std() > 10)
    ok("Check cells: style row hidden, Hide excluded shown",
       not w.style_box.isVisible() and w.chk_hide.isVisible())
    m_chk = w._mean.getData()[1]
    m_ref, lo_ref, hi_ref, _n = GS.stats(ref[:, state["inc"]], GS.coerce(w.style()).error)
    ok("Check cells: blue mean = stats() of the included", close(m_chk, m_ref))
    ok("Check cells: band = mean ± the graph look's error (V3.0; SD by default)", close(w._lo.getData()[1], lo_ref)
       and close(w._hi.getData()[1], hi_ref))

    # ---- view switch by clicking the button
    w.btn_view[VIEW_EXPORTED].click()
    pump()
    ok("view switch: view_changed('exported') emitted", sig["view"] == [VIEW_EXPORTED], str(sig["view"]))
    ok("As exported: style row shown, Hide excluded / Mean only hidden",
       w.style_box.isVisible() and not w.chk_hide.isVisible() and not w.chk_mean.isVisible())
    w.set_export_context("synthetic", "Nucleus", str(OUT))
    pump()

    shots = {}
    for name in GS.PRESETS:
        w.set_style(GS.apply_preset(w.style(), name).to_dict())
        pump()
        st = GS.GraphStyle.from_dict(w.style())
        tag = "".join(ch if ch.isalnum() else "_" for ch in name)
        a = grab("exported_" + tag)
        shots[name] = plot_area(a)
        ok(f"As exported '{name}': not blank", shots[name].std() > 8,
           f"std {shots[name].std():.1f}")
        ok(f"As exported '{name}': Look dropdown shows it", w.cmb_look.currentText() == name,
           w.cmb_look.currentText())
        inc = state["inc"]
        m, lo, hi, n = GS.stats(ref[:, inc], st.error)
        if st.show_mean:
            ok(f"As exported '{name}': mean line = stats() of the included only",
               close(w._mean.getData()[1], m))
            if st.error != "none" and st.error_style == "bars":
                o = w._errbar.opts
                fin = np.isfinite(m) & np.isfinite(lo) & np.isfinite(hi)
                ok(f"As exported '{name}': error bars = {st.error}",
                   close(o["top"], (hi - m)[fin]) and close(o["bottom"], (m - lo)[fin])
                   and close(o["y"], m[fin]))
            if st.error_style == "band" and st.error != "none":
                ok(f"As exported '{name}': band = mean ± {st.error}",
                   close(w._lo.getData()[1], lo) and close(w._hi.getData()[1], hi))
        else:
            ok(f"As exported '{name}': no mean drawn", w._mean is None and w._errbar is None)
        shown = sorted(k for _it, k in w._curves)
        ok(f"As exported '{name}': cell lines = included cells only" if st.show_cells
           else f"As exported '{name}': no cell lines",
           shown == (sorted(inc) if st.show_cells else []), str(shown))
        ok(f"As exported '{name}': title shows n", w._title.endswith(f"(n = {len(inc)})"), w._title)
    keys = list(shots)
    # the header above the plot wraps differently per style, so the plot heights
    # can differ by a line: compare the common (top-left) part
    hh = min(v.shape[0] for v in shots.values())
    ww = min(v.shape[1] for v in shots.values())
    shots = {k: v[:hh, :ww] for k, v in shots.items()}
    diffs = {(a, b): np.abs(shots[a] - shots[b]).mean() for i, a in enumerate(keys) for b in keys[i + 1:]}
    worst = min(diffs, key=diffs.get)
    ok("As exported: every preset looks different on screen", diffs[worst] > 0.05,
       f"least different: {worst} {diffs[worst]:.3f}")

    # ---- include / exclude through the list updates the As-exported mean
    w.set_style(GS.GraphStyle().to_dict())
    pump()
    before = w._mean.getData()[1].copy()
    row = live.index(1)
    w.table.item(row, 0).setCheckState(Qt.Unchecked)            # untick cell 2
    pump(0.3)
    inc2 = [k for k in live if k not in excl]
    ok("list: unticking a cell emits include_set and excludes it", 1 not in inc2, str(inc2))
    m2, *_ = GS.stats(ref[:, inc2], "SEM")
    after = w._mean.getData()[1]
    ok("As exported: mean follows the include list", close(after, m2) and not close(after, before))
    ok("As exported: title n follows the include list", w._title.endswith(f"(n = {len(inc2)})"),
       w._title)
    w.table.item(row, 0).setCheckState(Qt.Checked)
    pump(0.3)
    ok("list: ticking it again includes it", 1 in [k for k in live if k not in excl])

    # ---- compact controls emit style_changed
    sig["style"].clear()
    w.cmb_err.setCurrentIndex(w.cmb_err.findData("SEM"))     # V3.0: SD is the default now
    pump()
    ok("Error dropdown: style_changed with error = SEM",
       sig["style"] and sig["style"][-1]["error"] == "SEM")
    ok("Error dropdown: Look shows 'Prism default - mean ± SEM'",
       w.cmb_look.currentText() == "Prism default - mean ± SEM", w.cmb_look.currentText())
    w.cmb_errstyle.setCurrentIndex(w.cmb_errstyle.findData("band"))
    pump()
    ok("bars/band dropdown: band drawn", w._band is not None and w._errbar is None)
    ok("custom look: Look shows Custom", w.cmb_look.currentText().startswith("Custom"),
       w.cmb_look.currentText())
    w.chk_cells.setChecked(True)
    pump()
    ok("Each cell checkbox: cell lines drawn", len(w._curves) == len(state["inc"]))
    w._set_field("mean_colour", "#ff0000")
    pump()
    ok("mean colour: applied to the mean line",
       w._mean.opts["pen"].color().name().lower() == "#ff0000" and sig["style"][-1]["mean_colour"] == "#FF0000")
    a_red = grab("exported_custom_red_band_cells")
    ok("custom style differs from the default on screen",
       common_diff(plot_area(a_red), shots[GS.DEFAULT_PRESET]) > 0.05)

    # ---- fixed axis ranges, font size, title template, baseline line
    st = GS.GraphStyle(x_min=-2, x_max=12, y_min=0.8, y_max=2.0, font_pt=16,
                       title="{quantity} in {comp}: n = {n}", y_title="Norm. ratio",
                       baseline_line=True)
    w.set_style(st.to_dict())
    pump()
    xr, yr = w.vb.viewRange()
    ok("axis ranges: As exported shows your fixed ranges",
       close(xr, [-2, 12], 1e-9) and close(yr, [0.8, 2.0], 1e-9), f"{xr} {yr}")
    w.vb.scaleBy((0.5, 0.5))
    pump()
    w.reset_zoom()
    pump()
    xr, yr = w.vb.viewRange()
    ok("Reset zoom: back to the fixed ranges", close(xr, [-2, 12], 1e-9) and close(yr, [0.8, 2.0], 1e-9))
    ok("title template: {quantity} {comp} {n}",
       w._title == f"R/R0 GFP/Cy5 in Nucleus: n = {len(state['inc'])}", w._title)
    ok("axis title: yours replaces the automatic one",
       "Norm. ratio" in w.plot.getAxis("left").labelString()
       and "16pt" in w.plot.getAxis("left").labelString())
    ok("baseline line drawn at 0", w._baseline_line is not None and w._baseline_line.value() == 0.0)
    grab("exported_ranges_font16_baseline")

    # ---- hover and click still work (both views)
    def scene_pt(xv, yv):
        return w.vb.mapViewToScene(QPointF(xv, yv))

    w.set_style(GS.PRESETS["Mean ± SEM + each cell"].to_dict())
    pump()
    m, lo, hi, n = w._exp_stats
    i = 20
    (vy0, vy1) = w.vb.viewRange()[1]
    w._hover((scene_pt(float(w._x[i]), float(m[i]) + 0.2 * (vy1 - vy0)),))
    ok("hover (As exported): mean ± SEM and n at that time",
       w.lbl_hover.text().startswith("Mean ") and f"timepoint {i + 1}" in w.lbl_hover.text()
       and "SEM" in w.lbl_hover.text(), w.lbl_hover.text())
    k = state["inc"][2]
    w._hover((scene_pt(float(w._x[i]), float(ref[i, k])),))
    ok("hover (As exported): a cell line's value", w.lbl_hover.text().startswith("Cell "),
       w.lbl_hover.text())

    class Ev:
        def __init__(self, pos, dbl=False):
            self._p, self._d = pos, dbl

        def button(self):
            return Qt.LeftButton

        def double(self):
            return self._d

        def scenePos(self):
            return self._p

    sig["time"].clear()
    w._scene_click(Ev(scene_pt(float(w._x[13]) + 0.05, float(m[13]))))
    pump()
    ok("click (As exported): jumps to the clicked time", sig["time"] == [13], str(sig["time"]))
    sig["sel"].clear()
    w._pick(k, Ev(scene_pt(0, 0)))
    w._scene_click(Ev(scene_pt(float(w._x[13]), float(m[13]))))
    pump()
    ok("click a cell line (As exported): selects that cell, no time jump",
       sig["sel"] and sig["sel"][-1] == k and sig["time"] == [13], f"{sig['sel']} {sig['time']}")
    pen = [it for it, kk in w._curves if kk == k][0].opts["pen"]
    ok("selected cell drawn orange", pen.color().name() == "#ff8c00", pen.color().name())
    sig["time"].clear()
    w._pick(k, Ev(scene_pt(0, 0), dbl=True))                   # double-click = exclude
    w._scene_click(Ev(scene_pt(float(w._x[13]), float(m[13]))))  # (the same click)
    pump(0.3)
    ok("double-click a cell line (As exported): excludes it", k in excl, str(sorted(excl)))
    set_include(k, True)
    pump(0.3)

    # Save graph...: emits export_requested when connected; else saves itself
    w.export_requested.connect(lambda q: sig["export"].append(q))
    w.btn_save.click()
    pump()
    ok("Save graph...: export_requested(quantity) emitted", sig["export"] == ["R/R0 - GFP/Cy5"],
       str(sig["export"]))
    fn = OUT / "panel_save_graph.png"
    if fn.exists():
        fn.unlink()
    used = w.save_graph(fn)
    x, y, names, xl, yl = w.current_series()
    fn2 = OUT / "panel_save_graph_direct.png"
    if fn2.exists():
        fn2.unlink()
    GS.save_figure(fn2, x, y, names, w.style(), xl, yl, w.current_title())
    ok("save_graph(): the PNG = draw_matplotlib of current_series (same file bytes)",
       Path(used).read_bytes() == fn2.read_bytes())

    # ---- back to Check cells: exactly as before
    w.set_style({})
    w.btn_view[VIEW_CHECK].click()
    pump()
    ok("view switch back: view_changed('check')", sig["view"][-1] == VIEW_CHECK)
    w.select(None)
    check1 = grab("check_after_roundtrip")
    d = np.abs(plot_area(check1) - plot_area(check0))
    ok("Check cells: identical after visiting As exported (fonts / axes restored)",
       d.max() == 0, f"max diff {d.max():.0f}, mean {d.mean():.4f}")
    for name in ("Each cell only", "Mean ± 95% CI"):
        w.set_style(GS.PRESETS[name].to_dict())
        pump()
        dd = np.abs(plot_area(grab("check_style_" + name[:8].replace(" ", "_")))
                    - plot_area(check0))
        ok(f"Check cells: unaffected by the graph style ('{name}')", dd.max() == 0,
           f"max diff {dd.max():.0f}")
    i = 25
    k = state["inc"][0]
    w._hover((scene_pt(float(w._x[i]), float(ref[i, k])),))
    ok("hover (Check cells): cell value", w.lbl_hover.text().startswith(f"Cell "), w.lbl_hover.text())
    sig["time"].clear()
    w._scene_click(Ev(scene_pt(float(w._x[7]), 1.0)))
    pump()
    ok("click (Check cells): jumps to the time", sig["time"] == [7], str(sig["time"]))
    w.select(3)
    pen = [it for it, kk in w._curves if kk == 3][0].opts["pen"]
    ok("select(k) (Check cells): orange", pen.color().name() == "#ff8c00")
    w.set_baseline(10)
    pump()
    ok("set_baseline: x axis moves (0 at timepoint 11)", w._x[10] == 0.0)

    # ---- the 'More style...' dialog: build it, change a value, OK / Cancel
    from peterpiper.gui.traces import StyleDialog
    w.set_view(VIEW_EXPORTED)
    w.set_style({})
    pump()
    dlg = StyleDialog(GS.GraphStyle.from_dict(w.style()), "Time from baseline (min)", "R/R0 GFP/Cy5", w)
    seen = []
    dlg.changed.connect(lambda dd: seen.append(dd))
    dlg.w["symbol"].setCurrentIndex(dlg.w["symbol"].findData("square"))
    dlg.w["y_min"].setText("0.5")
    dlg.w["x_max"].setText("abc")                      # not a number: red, treated as auto
    dlg.w["font_pt"].setValue(14)
    r = dlg.result_style()
    ok("More style: every field has a control",
       set(dlg.w) == {f.name for f in GS.dataclasses.fields(GS.GraphStyle)}, str(sorted(dlg.w)))
    ok("More style: edits give the right style (bad number = auto)",
       r.symbol == "square" and r.y_min == 0.5 and r.x_max is None and r.font_pt == 14
       and len(seen) >= 3)
    dlg.show()
    pump()
    dlg.grab().save(str(OUT / "style_dialog.png"))
    dlg.close()
    # live preview through the panel, then Cancel = back
    old = w.style()
    import peterpiper.gui.traces as TR
    orig_exec = TR.StyleDialog.exec

    def fake_exec(self, accept=False):
        self.w["symbol"].setCurrentIndex(self.w["symbol"].findData("diamond"))
        pump()
        fake_exec.preview = w.style()["symbol"]
        return 1 if accept else 0

    TR.StyleDialog.exec = lambda self: fake_exec(self, False)
    sig["style"].clear()
    w._more_style()
    pump()
    ok("More style: live preview while open", fake_exec.preview == "diamond")
    ok("More style: Cancel restores the style, no style_changed", w.style() == old and not sig["style"])
    TR.StyleDialog.exec = lambda self: fake_exec(self, True)
    w._more_style()
    pump()
    ok("More style: OK keeps it and emits style_changed",
       w.style()["symbol"] == "diamond" and sig["style"] and sig["style"][-1]["symbol"] == "diamond")
    TR.StyleDialog.exec = orig_exec

    # ---- clear() and set_data again (as after re-tracking)
    w.clear("cleared")
    pump()
    ok("clear(): empty panel, no crash", w._full is None and w.current_series()[1].size == 0)
    w.set_data(M, live, state["inc"], why, LABELS["nucleus"], 4, 0, [])
    pump()
    ok("set_data after clear (As exported): drawn again", w._mean is not None)
    # no cells included at all
    w.set_included([], {k: "excluded by you" for k in live})
    pump(0.3)
    ok("no cells included (As exported): no mean, title n = 0, no crash",
       w._mean is None and w._title.endswith("(n = 0)"), w._title)
    w.set_included(state["inc"], why)
    pump(0.3)
    # a Prism note is shown only while the look has something Prism cannot draw
    w.set_style({})
    pump(0.2)
    quiet = not w.lbl_prism.isVisible() and "*" not in w.chk_cells.text()
    w.set_style(GS.GraphStyle(error_style="band").to_dict())
    pump(0.2)
    ok("Prism honesty: note only for a band (shows error bars instead)",
       quiet and w.lbl_prism.isVisible() and "error bars instead" in w.lbl_prism.text()
       and "*" in w.cmb_errstyle.itemText(1), w.lbl_prism.text())
    w.set_style({})
    w.close()


def main() -> int:
    print(f"output: {OUT}")
    for fn in (test_stats, test_csv_unchanged, test_style_dict, test_matplotlib,
               test_csv_files_vs_v22, test_panel):
        try:
            fn()
        except Exception:                                    # noqa: BLE001
            ok(f"{fn.__name__} ran without an exception", False, traceback.format_exc())
    if errors:
        ok("no exceptions inside Qt slots", False, "\n".join(errors)[:3000])
    else:
        ok("no exceptions inside Qt slots", True)
    bad = [n for n, c in checks if not c]
    print(f"\n{len(checks) - len(bad)} / {len(checks)} checks passed")
    for n in bad:
        print("  FAILED:", n)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
