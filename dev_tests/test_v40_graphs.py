"""
Developer test (not shipped): PeterPiper 4.0 graph builder - graphbuilder.py (engine),
graphparse.py (typed sentences), gui/graphbuilder.py (widget) and Compare's
'Graphs across runs' page. Synthetic data only (a 4-channel run: Cy5, mCherry, GFP,
DAPI; 60 cells x 121 timepoints x 3 compartments) - no lab movie is opened.

    PYTHONIOENCODING=utf-8 MPLBACKEND=Agg QT_QPA_PLATFORM=offscreen \
        PETERPIPER_HOME=_out/home_v40g python dev_tests/test_v40_graphs.py

A) quantities = the export's own numbers (plots._panels: BgSub / dFF / R / dRR;
   compare.measure_data: Sum intensity, Area, Comp. ratio (/R0)); x background; every
   time choice (at T / min / frame, end, mean, max, min, AUC, slope) against numpy.
B) RunData.from_track (live cells, excluded cells, baseline, condition from the name)
   and RunData.from_run (a compare.Run as Compare loads it).
C) shape rules: traces (vs Time), scatter, X bins, trace vs trace (points / trajectories),
   time inheritance ('at T=30 vs F/F0' -> both at T=30), Z of a trace at the baseline,
   group means / SD / SEM, correlation (Pearson / Spearman) against scipy.
D) bins: equal count, equal width, own cut-offs; labels, colours, empty bins.
E) conditions: >, between, outside, a trace taken at T=0, condition / run, included only;
   the drift add-on (off by default; on removes a linear drift).
F) parser: the user's three sentences, 20+ variations, errors with suggestions,
   spec -> sentence -> spec round trip (many specs), autocomplete, highlighting.
G) recipes (favourites, recent) in the user's folder; table export (CSV / Excel with the
   sentence on top, never overwriting).
H) widget: rows <-> sentence, swap, chips, star / recent, hover / click -> cell_clicked,
   export PNG / SVG, auto-fit after changes and resizes, redraw time, screenshots of the
   user's three example graphs.
I) Compare: the builder is the main page, gets the ticked runs, split by run / condition,
   the averages page still works (its settings box shows only there), Close under both.
"""
from __future__ import annotations

import os
import shutil
import sys
import time
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
OUT = REPO / "_out" / "v40_graphs"
SHOTS = REPO / "_out" / "shots"
shutil.rmtree(OUT, ignore_errors=True)
OUT.mkdir(parents=True)
SHOTS.mkdir(parents=True, exist_ok=True)
os.environ["PETERPIPER_HOME"] = str(OUT / "home")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")
sys.path.insert(0, str(REPO / "app"))

import numpy as np                                                    # noqa: E402

from peterpiper import compare as C                                   # noqa: E402
from peterpiper import graphbuilder as G                              # noqa: E402
from peterpiper import graphparse as P                                # noqa: E402
from peterpiper.config import Experiment, Settings                    # noqa: E402
from peterpiper.measure import Measurements, min_snr                  # noqa: E402
from peterpiper.plots import _panels, drift_slopes                    # noqa: E402

N_OK = [0]
FAILS = []


def ok(name, cond, extra=""):
    if cond:
        N_OK[0] += 1
    else:
        FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + ("" if isinstance(extra, str) and extra == "" else f"  [{extra}]"),
          flush=True)


def same(a, b, tol=1e-9) -> bool:
    a, b = np.asarray(a, float), np.asarray(b, float)
    if a.shape != b.shape:
        return False
    fa, fb = np.isfinite(a), np.isfinite(b)
    return bool((fa == fb).all() and np.allclose(a[fa], b[fb], rtol=tol, atol=tol))


CH = ["Cy5", "mCherry", "GFP", "DAPI"]
T, N = 121, 60
COMPS3 = ("nucleus", "cytoplasm", "cell")


def synth_meas(seed=1, n=N, t=T, drift=0.0):
    """{comp: Measurements}: Cy5 rises after timepoint 11 (the baseline), GFP flat,
    mCherry per-cell level, DAPI per-cell DNA content; a few dim cells (GFP below the
    noise at baseline -> blank F/F0, as the export does); drift: counts per frame."""
    rng = np.random.default_rng(seed)
    tt = np.arange(t, dtype=float)
    resp = 1 + 0.5 * (1 - np.exp(-np.clip(tt - 10, 0, None) / 15.0))
    level = rng.uniform(300, 2500, (4, n))
    level[2, :3] = -50.0                                # three GFP-dim cells
    meas = {}
    for ci, comp in enumerate(COMPS3):
        bg = np.full((t, 4), 100.0) + rng.normal(0, 1, (t, 4))
        sig = level[None] * np.where(np.arange(4) == 0, resp[:, None], 1.0)[:, :, None]
        mean = bg[:, :, None] + sig * (1 - 0.3 * ci) + rng.normal(0, 4, (t, 4, n)) + \
            drift * tt[:, None, None]
        area = np.full((t, n), 300.0 + 150 * ci) + rng.normal(0, 3, (t, n))
        meas[comp] = Measurements(mean=mean, background=bg, area_px=area,
                                  n_saturated=np.zeros((t, 4, n), int), quality=np.ones((t, n)),
                                  channels=list(CH), background_sd=np.full((t, 4), 8.0))
    return meas


def synth_run(name="U2OS dish1", seed=1, baseline=11, spf=30.0, excl=(0, 1), **kw) -> G.RunData:
    meas = synth_meas(seed, **kw)
    n = next(iter(meas.values())).n_cells
    live = {c: np.ones(n, bool) for c in meas}
    inc = {c: np.ones(n, bool) for c in meas}
    for c in inc:
        inc[c][list(excl)] = False
    return G.RunData(name=name, meas=meas, included=inc, live=live, baseline=baseline,
                     seconds_per_frame=spf, um_per_px=0.5, condition=G._condition(name),
                     key=f"key:{name}")


def as_compare_run(rd: G.RunData, path: str) -> C.Run:
    return C.Run(path=path, label=rd.name, nd2=rd.name + ".nd2", baseline=rd.baseline,
                 seconds_per_frame=rd.seconds_per_frame, n_timepoints=rd.n_t,
                 channels=list(CH), meas=rd.meas,
                 included={c: [int(k) for k in np.flatnonzero(rd.included[c])]
                           for c in rd.meas}, um_per_px=rd.um_per_px)


Q = G.Quantity


# ---------------------------------------------------------------- A
def part_a():
    run = synth_run()
    M = run.meas["nucleus"]
    s = Settings(baseline_timepoint=run.baseline, write_ratio_sheets=True,
                 ratio_min_snr=min_snr())
    pan = {name: d for name, d, *_r in _panels(M, s)}
    ok("A mean intensity = export BgSub_Cy5", same(G.values(run, Q("nucleus", "Cy5", "mean")),
                                                  pan["BgSub_Cy5"]))
    ff = G.values(run, Q("nucleus", "GFP", "ff0"))
    ok("A F/F0 = export dFF_GFP (dim cells blank as in the export)",
       same(ff, pan["dFF_GFP"]) and np.isnan(ff[:, :3]).all(), np.isnan(ff[:, :3]).all())
    ok("A ratio = export R_Cy5_over_GFP", same(G.values(run, Q("nucleus", "Cy5/GFP", "ratio")),
                                              pan["R_Cy5_over_GFP"]))
    ok("A R/R0 = export dRR_Cy5_over_GFP", same(G.values(run, Q("nucleus", "Cy5/GFP", "rr0")),
                                               pan["dRR_Cy5_over_GFP"]))
    ok("A R/R0 in the other order (GFP/Cy5) = dRR_GFP_over_Cy5",
       same(G.values(run, Q("nucleus", "GFP/Cy5", "rr0")), pan["dRR_GFP_over_Cy5"]))
    crun = as_compare_run(run, str(OUT / "a.npz"))
    sumi, _c = C.measure_data(crun, "nucleus", "Sum intensity DAPI", run.baseline)
    ok("A summed total intensity = Compare's 'Sum intensity' ((mean - bg) x area)",
       same(G.values(run, Q("nucleus", "DAPI", "total")), sumi))
    ok("A RunData.total() is the same (T x C x N)",
       same(run.total("nucleus")[:, 3, :], sumi))
    area, _c = C.measure_data(crun, "cytoplasm", "Area", run.baseline)
    ok("A area = Compare's Area (um2 with the pixel size)",
       same(G.values(run, Q("cytoplasm", "", "area")), area) and
       abs(float(area[0, 0]) - float(run.meas["cytoplasm"].area_px[0, 0]) * 0.25) < 1e-9)
    cr, _c = C.measure_data(crun, "nucleus", "Comp. ratio GFP ÷ cytoplasm", run.baseline)
    ok("A nuclear/cytoplasmic GFP = Compare's 'Comp. ratio'",
       same(G.values(run, Q("nucleus", "GFP", "mean", comp2="cytoplasm")), cr))
    cr0, _c = C.measure_data(crun, "nucleus", "Comp. ratio/R0 GFP ÷ cytoplasm", run.baseline)
    ok("A nuclear/cytoplasmic GFP F/F0 = Compare's 'Comp. ratio/R0'",
       same(G.values(run, Q("nucleus", "GFP", "ff0", comp2="cytoplasm")), cr0))
    xb = G.values(run, Q("nucleus", "mCherry", "xbg"))
    ok("A x background = raw ROI mean / background mean",
       same(xb, M.mean[:, 1, :] / M.background[:, 1][:, None]))
    ok("A raw = the ROI's raw mean", same(G.values(run, Q("nucleus", "GFP", "raw")),
                                         M.mean[:, 2, :]))
    tr = pan["BgSub_Cy5"]
    b0 = run.baseline - 1
    ok("A at T=30 = 30 timepoints after the baseline",
       same(G.values(run, Q("nucleus", "Cy5", "mean", "at", 30.0)), tr[b0 + 30]))
    ok("A at T=0 = the baseline; T=-5 before it",
       same(G.values(run, Q("nucleus", "Cy5", "mean", "at", 0.0)), tr[b0]) and
       same(G.values(run, Q("nucleus", "Cy5", "mean", "at", -5.0)), tr[b0 - 5]))
    ok("A at 5 min = 10 frames (30 s per frame) after the baseline",
       same(G.values(run, Q("nucleus", "Cy5", "mean", "at", 5.0, unit="min")), tr[b0 + 10]))
    ok("A at frame 12 = the movie's own 12th frame",
       same(G.values(run, Q("nucleus", "Cy5", "mean", "at", 12.0, unit="frame")), tr[11]))
    ok("A at a time outside the movie = no value (NaN)",
       np.isnan(G.values(run, Q("nucleus", "Cy5", "mean", "at", 500.0))).all())
    ok("A at the end = the last timepoint", same(G.values(run, Q("nucleus", "Cy5", "mean",
                                                                  "end")), tr[-1]))
    ok("A mean over T=0..10", same(G.values(run, Q("nucleus", "Cy5", "mean", "mean", 0.0, 10.0)),
                                   tr[b0:b0 + 11].mean(0)))
    ok("A max / min over the whole movie",
       same(G.values(run, Q("nucleus", "Cy5", "mean", "max")), tr.max(0)) and
       same(G.values(run, Q("nucleus", "Cy5", "mean", "min")), tr.min(0)))
    x = run.time
    auc = np.array([np.trapezoid(tr[b0:b0 + 21, k], x[b0:b0 + 21]) if hasattr(np, "trapezoid")
                    else np.trapz(tr[b0:b0 + 21, k], x[b0:b0 + 21]) for k in range(N)])
    ok("A AUC over T=0..20 (trapezoids, x in minutes)",
       same(G.values(run, Q("nucleus", "Cy5", "mean", "auc", 0.0, 20.0)), auc, 1e-7))
    ok("A slope over frames 2-9 = plots.drift_slopes (the export's drift slope)",
       same(G.values(run, Q("nucleus", "Cy5", "mean", "slope", 2.0, 9.0, "frame")),
            drift_slopes(tr, x, 2, 9)))
    ok("A slope with no window = frames 2-9 (the drift default)",
       same(G.values(run, Q("nucleus", "Cy5", "mean", "slope")), drift_slopes(tr, x, 2, 9)))
    try:
        G.values(run, Q("nucleus", "JF646", "mean"))
        ok("A an unknown channel says so in words", False)
    except G.QuantityError as e:
        ok("A an unknown channel says so in words", "no channel 'JF646'" in str(e), str(e))
    try:
        G.values(run, Q("mito", "GFP", "mean"))
        ok("A a missing compartment says so in words", False)
    except G.QuantityError as e:
        ok("A a missing compartment says so in words", "no mitochondrial ROIs" in str(e), str(e))


# ---------------------------------------------------------------- B
def part_b():
    meas = synth_meas(2, n=8, t=20)
    exp = Experiment(nd2_path="C:/x/HeLa_dish3.nd2", channels=list(CH), n_timepoints=20,
                     seconds_per_frame=60.0, um_per_px=0.65)
    cells = [{"nucleus": 1, "cell": 1} for _ in range(8)]
    cells[5] = {"cell": 1}                           # no nucleus drawn for cell 6
    rd = G.RunData.from_track({"meas": meas}, exp, {"nucleus": {2}, "cell": [7]}, baseline_t=4,
                              cells=cells)
    ok("B from_track: included = drawn and not excluded",
       list(np.flatnonzero(rd.included["nucleus"])) == [0, 1, 3, 4, 6, 7] and
       list(np.flatnonzero(rd.included["cell"])) == [0, 1, 2, 3, 4, 5, 6],
       (np.flatnonzero(rd.included["nucleus"]), np.flatnonzero(rd.included["cell"])))
    ok("B from_track: all cells (live) keeps the excluded ones, not the undrawn",
       list(np.flatnonzero(rd.mask("nucleus", False))) == [0, 1, 2, 3, 4, 6, 7])
    ok("B from_track: name, baseline, interval, pixel size, condition from the name",
       rd.name == "HeLa_dish3" and rd.baseline == 4 and rd.minutes and rd.um_per_px == 0.65
       and rd.condition == "HeLa" and rd.time[3] == 0 and rd.time[5] == 2.0,
       (rd.name, rd.condition, rd.time[:6]))
    ok("B from_track: channels and compartments", rd.channels == CH and
       rd.comps == ["nucleus", "cytoplasm", "cell"])
    rd2 = G.RunData.from_track({"meas": meas}, Experiment(), None, 1)
    ok("B from_track with nothing else: every column live and included",
       rd2.included["nucleus"].all() and not rd2.minutes and rd2.time_label.startswith("Timep"))
    crun = as_compare_run(synth_run("IHH d2", seed=3), str(OUT / "ihh.npz"))
    r3 = G.RunData.from_run(crun)
    ok("B from_run: included from the run's saved lists, key = its path",
       list(np.flatnonzero(r3.included["nucleus"])) == crun.included["nucleus"] and
       r3.key == crun.path and r3.condition == "IHH")
    ok("B from_run numbers = from_track numbers (same arithmetic)",
       same(G.values(r3, Q("nucleus", "Cy5/GFP", "rr0")),
            C.measure_data(crun, "nucleus", "R/R0 Cy5/GFP", crun.baseline)[0]))


# ---------------------------------------------------------------- C
def part_c():
    G.warm_up()
    run = synth_run()
    sp = G.GraphSpec(y=Q("nucleus", "Cy5", "ff0"))
    r = G.compute([run], sp)
    inc = 58
    ok("C vs Time -> traces: one trace per included cell, a mean line",
       r.shape == "traces" and r.n_cells == inc and len(r.groups) == 1 and
       len(r.groups[0].x) == T and r.x_label == "Time from baseline (min)",
       (r.shape, r.n_cells))
    tr = G.values(run, sp.y)[:, 2:]
    ok("C the mean line = mean of the included cells, error = SD (n - 1)",
       same(r.groups[0].y, np.nanmean(tr, 1)) and
       same(r.groups[0].yerr, np.nan_to_num(np.nanstd(tr, 1, ddof=1))))
    r2 = G.compute([run], replace(sp, error="SEM"))
    n = np.isfinite(tr).sum(1)
    ok("C SEM = SD / sqrt(n)", same(r2.groups[0].yerr, np.nan_to_num(np.nanstd(tr, 1, ddof=1)
                                                                      / np.sqrt(n))))
    ok("C one run, no Z: each cell in its fixed cell colour",
       r.cells[0].colour == G._cell_colour_fn()(2) and r.cells[5].colour ==
       G._cell_colour_fn()(7))
    r = G.compute([run], replace(sp, y=Q("nucleus", "Cy5", "ff0", "at", 30.0)))
    ok("C a one-number Y against Time: shown as its full trace, with a note",
       r.shape == "traces" and any("full trace" in n_ for n_ in r.notes), r.notes)
    sc = G.GraphSpec(y=Q("cell", "mCherry", "mean", "at", 30.0), x=Q("nucleus", "GFP", "ff0"))
    r = G.compute([run], sc)
    xv = G.values(run, Q("nucleus", "GFP", "ff0", "at", 30.0))
    ok("C trace next to a one-number quantity takes its time (X at T=30 like Y)",
       r.shape == "scatter" and same([c.x[0] for c in r.cells], xv[2:]) and
       any("like Y" in n_ for n_ in r.notes), r.notes)
    ys = np.array([c.y[0] for c in r.cells])
    xs = np.array([c.x[0] for c in r.cells])
    from scipy import stats
    okm = np.isfinite(xs) & np.isfinite(ys)
    pr = stats.pearsonr(xs[okm], ys[okm])
    ok("C Pearson r and p = scipy's (n = cells with both values)",
       r.corr and abs(r.corr[0][2] - pr[0]) < 1e-12 and abs(r.corr[0][3] - pr[1]) < 1e-9 and
       r.corr[0][4] == okm.sum(), r.corr)
    r = G.compute([run], replace(sc, corr="spearman"))
    sr = stats.spearmanr(xs[okm], ys[okm])
    ok("C Spearman rho = scipy's", abs(r.corr[0][2] - sr[0]) < 1e-12)
    ok("C scatter: one point per cell, group mean marker with X and Y error",
       len(r.cells) == inc and r.groups[0].kind == "marker" and len(r.groups[0].xerr) == 1)
    r = G.compute([run], replace(sc, x_bins=G.BinSpec("count", 4)))
    ok("C X in 4 equal-n bins -> mean Y per bin (a line of 4 points)",
       r.shape == "binned" and len(r.groups[0].x) == 4 and
       sum(int(v) for v in r.groups[0].n) == okm.sum(), r.groups[0].n)
    pr_ = G.GraphSpec(y=Q("nucleus", "Cy5/GFP", "rr0"), x=Q("cytoplasm", "mCherry", "mean"))
    r = G.compute([run], pr_)
    ok("C trace vs trace -> every (cell, timepoint) point, coloured by time",
       r.shape == "pairs" and sum(len(c.x) for c in r.cells) == inc * T and
       r.cells[0].colours is not None and r.colour_range == (float(run.time.min()),
                                                               float(run.time.max())),
       r.colour_range)
    r = G.compute([run], replace(pr_, pairs="trajectories"))
    ok("C trajectories: one line per cell, the mean trajectory", r.shape == "pairs" and
       len(r.groups[0].x) == T)
    r = G.compute([run], replace(pr_, z=Q("nucleus", "DAPI", "mean")))
    ok("C three traces: points coloured by Z at each timepoint (Z per point)",
       r.cells[0].colours is not None and len(r.cells[0].z) == T and r.colour_range is not None
       and r.z_label.startswith("Mean intensity DAPI"))
    r = G.compute([run], G.GraphSpec(y=Q("nucleus", "Cy5", "ff0"), z=Q("nucleus", "DAPI",
                                                                       "total")))
    ok("C Z a trace with traces vs Time: taken at the baseline (T=0), a note",
       r.z is not None and r.z.time == "at" and r.z.t1 == 0 and
       any("baseline" in n_ for n_ in r.notes), r.notes)
    two = [run, synth_run("HeLa dish2", seed=5, spf=60.0)]
    r = G.compute(two, replace(sc, split="run"))
    ok("C two runs, colour by run: two groups, two colours",
       [g.label.split(" (")[0] for g in r.groups] == ["U2OS dish1", "HeLa dish2"] and
       len({g.colour for g in r.groups}) == 2)
    r = G.compute(two, replace(sc, split="condition"))
    ok("C colour by condition (cell line from the name)",
       [g.label.split(" (")[0] for g in r.groups] == ["U2OS", "HeLa"], [g.label for g in r.groups])
    r = G.compute(two, sp)
    ok("C pooled runs with different frame intervals: means over the union of times, a note",
       r.n_runs == 2 and any("different times" in n_ for n_ in r.notes))
    r = G.compute([run], G.GraphSpec(y=Q("nucleus", "JF646", "ff0")))
    ok("C a bad choice gives an error in words, no exception", r.error and "JF646" in r.error,
       r.error)
    r = G.compute([], sp)
    ok("C no run: 'No run to plot yet.'", r.error == "No run to plot yet.")
    ok("C shape_of", G.shape_of(sp) == "traces" and G.shape_of(sc) == "scatter" and
       G.shape_of(pr_) == "pairs" and G.shape_of(replace(sc, x_bins=G.BinSpec())) == "binned")


# ---------------------------------------------------------------- D
def part_d():
    run = synth_run()
    zq = Q("nucleus", "DAPI", "total", "at", 0.0)
    sp = G.GraphSpec(y=Q("nucleus", "Cy5", "ff0"), z=zq, z_mode="bins",
                     z_bins=G.BinSpec("count", 3))
    r = G.compute([run], sp)
    sizes = [len([c for c in r.cells if c.group == g.label.rsplit(" (n = ", 1)[0]])
             for g in r.groups]
    ok("D equal-count bins: 3 groups of the same size (58 cells -> 19/20)",
       len(r.groups) == 3 and max(sizes) - min(sizes) <= 1 and sum(sizes) == 58, sizes)
    zv = G.values(run, zq)[2:]
    lows = [float(g.label.split(" ")[2]) for g in r.groups]
    ok("D bins in order low -> high, labels say the range and n",
       lows == sorted(lows) and all("(n = " in g.label for g in r.groups) and
       r.groups[0].label.startswith("summed DAPI"), [g.label for g in r.groups])
    ok("D bin colours differ and are not the pale end of the scale",
       len({g.colour for g in r.groups}) == 3 and all(g.colour != "#FDE725" for g in r.groups))
    e = G.bin_edges(zv, G.BinSpec("width", 4))
    ok("D equal-width edges: 4 equal steps from min to max",
       len(e) == 5 and np.allclose(np.diff(np.r_[zv.min(), e[1:-1], zv.max()]),
                                   (zv.max() - zv.min()) / 4))
    cuts = (float(np.percentile(zv, 25)), float(np.percentile(zv, 75)))
    r = G.compute([run], replace(sp, z_bins=G.BinSpec("custom", 3, cuts)))
    b = G.assign_bins(zv, G.bin_edges(zv, G.BinSpec("custom", 3, cuts)))
    ok("D my cut-offs: below / between / above",
       len(r.groups) == 3 and (b == 0).sum() == (zv < cuts[0]).sum() and
       (b == 2).sum() == (zv >= cuts[1]).sum())
    ok("D assign_bins: no value -> -1", list(G.assign_bins(np.array([np.nan, 1.0]),
                                                           np.array([-np.inf, 0, np.inf]))) ==
       [-1, 1])
    r = G.compute([run], replace(sp, z_bins=G.BinSpec("custom", 2, (1e12,))))
    ok("D a cut-off above every value: one bin left (no crash)", len(r.groups) == 1)
    r = G.compute([run, synth_run("HeLa dish2", seed=5)], replace(sp, split="run"))
    ok("D bins x runs: run - bin groups in shades of each run's colour",
       len(r.groups) == 6 and r.groups[0].label.startswith("U2OS dish1 - "), len(r.groups))


# ---------------------------------------------------------------- E
def part_e():
    run = synth_run()
    sp = G.GraphSpec(y=Q("cell", "mCherry", "mean", "at", 30.0), x=Q("nucleus", "GFP", "ff0",
                                                                     "at", 30.0))
    dq = Q("nucleus", "DAPI", "total", "at", 0.0)
    dv = G.values(run, dq)
    thr = float(np.median(dv[2:]))
    r = G.compute([run], replace(sp, filters=(G.Filter(q=dq, op=">", a=thr),)))
    want = [k for k in range(2, N) if dv[k] > thr]
    ok("E condition '>': only those cells", sorted(c.k for c in r.cells) == want,
       (len(r.cells), len(want)))
    lo, hi = np.percentile(dv[2:], [30, 70])
    r = G.compute([run], replace(sp, filters=(G.Filter(q=dq, op="between", a=hi, b=lo),)))
    ok("E 'between' (either order)", sorted(c.k for c in r.cells) ==
       [k for k in range(2, N) if lo <= dv[k] <= hi])
    r = G.compute([run], replace(sp, filters=(G.Filter(q=dq, op="outside", a=lo, b=hi),)))
    ok("E 'not between'", sorted(c.k for c in r.cells) ==
       [k for k in range(2, N) if dv[k] < lo or dv[k] > hi])
    r = G.compute([run], replace(sp, filters=(G.Filter(q=dq, op=">", a=thr, on=False),)))
    ok("E a condition switched off changes nothing", r.n_cells == 58)
    fq = Q("nucleus", "DAPI", "total")                       # a trace -> at T=0
    r2 = G.compute([run], replace(sp, filters=(G.Filter(q=fq, op=">", a=thr),)))
    ok("E a condition on a trace is taken at T=0 (the baseline)",
       sorted(c.k for c in r2.cells) == want)
    xb = G.values(run, Q("nucleus", "GFP", "xbg", "at", 0.0))
    r = G.compute([run], replace(sp, filters=(G.Filter(q=Q("nucleus", "GFP", "xbg", "at", 0.0),
                                                       op=">", a=3.0),)))
    ok("E 'GFP x background at T=0 > 3' leaves out the dim cells",
       sorted(c.k for c in r.cells) == [k for k in range(2, N) if xb[k] > 3] and
       not {0, 1, 2} & {c.k for c in r.cells})
    two = [run, synth_run("HeLa dish2", seed=5)]
    r = G.compute(two, replace(sp, filters=(G.Filter(kind="condition", text="hela"),)))
    ok("E condition = HeLa (any case): only that run's cells",
       {c.run_name for c in r.cells} == {"HeLa dish2"})
    r = G.compute(two, replace(sp, filters=(G.Filter(kind="run", text="U2OS dish1"),)))
    ok("E run = U2OS dish1", {c.run_name for c in r.cells} == {"U2OS dish1"})
    r = G.compute([run], replace(sp, included_only=False))
    ok("E all cells: the excluded ones too", r.n_cells == 60)
    r = G.compute([run], replace(sp, filters=(G.Filter(q=dq, op=">", a=1e20),)))
    ok("E nothing left: a plain message", r.error.startswith("No cell is left"), r.error)
    # the drift add-on
    dr = synth_run("drifting", seed=9, drift=2.0)
    q = Q("nucleus", "GFP", "mean")
    off = G.compute([dr], G.GraphSpec(y=q))
    on = G.compute([dr], G.GraphSpec(y=q, drift=(2, 9)))
    s_off = G.values(dr, Q("nucleus", "GFP", "mean", "slope", 2.0, 9.0, "frame"))
    s_on = G.values(dr, Q("nucleus", "GFP", "mean", "slope", 2.0, 9.0, "frame"), drift=(2, 9))
    ok("E drift add-on off by default: the numbers are the export's",
       G.GraphSpec(y=q).drift is None and same(off.cells[0].y, G.values(dr, q)[:, 2]))
    ok("E drift add-on on: each cell's straight-line drift (frames 2-9) taken out",
       np.nanmean(np.abs(s_off)) > 3.0 and np.nanmax(np.abs(s_on)) < 1e-9 and
       any("Drift correction on" in n_ for n_ in on.notes), (np.nanmean(s_off), np.nanmax(s_on)))
    ok("E drift: the baseline value itself is unchanged",
       same(on.cells[0].y[dr.b0], off.cells[0].y[dr.b0]))


# ---------------------------------------------------------------- F
EX1 = "R/R0 of nuclear Cy5/GFP vs. Intensity of cytoplasmic mCherry"
EX2 = ("Intensity of whole cell mCherry at T=30 vs. F/F0 of GFP binned by Summed Total "
       "Intensity of nuclear DAPI at T=0")
EX3 = ("R/R0 nuclear Cy5/GFP vs. Intensity of cytoplasmic mCherry vs. Intensity of nuclear "
       "DAPI")


def part_f():
    cp = list(COMPS3)
    p = P.parse(EX1, CH, cp)
    ok("F example 1: R/R0 nuclear Cy5/GFP vs cytoplasmic mCherry intensity",
       p.ok and p.spec.y == Q("nucleus", "Cy5/GFP", "rr0") and
       p.spec.x == Q("cytoplasm", "mCherry", "mean") and p.spec.z is None,
       [i.message for i in p.issues])
    p = P.parse(EX2, CH, cp)
    ok("F example 2: whole cell mCherry at T=30 vs F/F0 GFP binned by summed nuclear DAPI "
       "at T=0",
       p.ok and p.spec.y == Q("cell", "mCherry", "mean", "at", 30.0) and
       p.spec.x == Q("nucleus", "GFP", "ff0") and
       p.spec.z == Q("nucleus", "DAPI", "total", "at", 0.0) and p.spec.z_mode == "bins",
       (p.spec, [i.message for i in p.issues]))
    p = P.parse(EX3, CH, cp)
    ok("F example 3: three things, the third as colour",
       p.ok and p.spec.z == Q("nucleus", "DAPI", "mean") and p.spec.z_mode == "colour")
    V = [  # (sentence, check)
        ("F/F0 GFP vs time", lambda s: s.x is None and s.y == Q("nucleus", "GFP", "ff0")),
        ("ff0 gfp vs t", lambda s: s.x is None and s.y.measure == "ff0"),
        ("r/r0 nuc cy5/gfp versus cyto mcherry",
         lambda s: s.y == Q("nucleus", "Cy5/GFP", "rr0") and s.x.comp == "cytoplasm"),
        ("ratio of GFP over Cy5 in the nucleus vs time",
         lambda s: s.y == Q("nucleus", "GFP/Cy5", "ratio")),
        ("Cy5/GFP vs time", lambda s: s.y.measure == "ratio" and s.y.chan == "Cy5/GFP"),
        ("summed nuclear DAPI vs area of the nucleus",
         lambda s: s.y.measure == "total" and s.x == Q("nucleus", "", "area")),
        ("total DAPI at baseline vs integrated mCherry at the end",
         lambda s: s.y == Q("nucleus", "DAPI", "total", "at", 0.0) and
         s.x.time == "end" and s.x.measure == "total"),
        ("whole cell mCherry t30 vs gfp at 30 min",
         lambda s: s.y.t1 == 30 and s.y.unit == "tp" and s.x.t1 == 30 and s.x.unit == "min"),
        ("mean intensity cytoplasmic GFP at frame 12 vs nuclear GFP",
         lambda s: s.y == Q("cytoplasm", "GFP", "mean", "at", 12.0, unit="frame")),
        ("max F/F0 GFP vs summed DAPI at T=0",
         lambda s: s.y.time == "max" and s.y.t1 is None),
        ("F/F0 GFP mean over T=0..10 vs DAPI",
         lambda s: s.y.time == "mean" and (s.y.t1, s.y.t2) == (0.0, 10.0)),
        ("GFP slope over frames 2-9 vs DAPI total at T=0",
         lambda s: s.y == Q("nucleus", "GFP", "mean", "slope", 2.0, 9.0, "frame")),
        ("AUC of F/F0 GFP over 0-20 min vs mCherry at baseline",
         lambda s: s.y.time == "auc" and s.y.unit == "min" and s.y.t2 == 20.0),
        ("nuclear/cytoplasmic GFP vs time",
         lambda s: s.y.comp == "nucleus" and s.y.comp2 == "cytoplasm"),
        ("N/C GFP vs time", lambda s: s.y.comp2 == "cytoplasm"),
        ("GFP x background at T=0 vs mCherry x bg at T=0",
         lambda s: s.y.measure == "xbg" and s.x.measure == "xbg"),
        ("F/F0 GFP vs time coloured by summed DAPI at T=0",
         lambda s: s.z is not None and s.z_mode == "colour" and s.z.measure == "total"),
        ("F/F0 GFP vs time binned by DAPI in 4 equal-width bins",
         lambda s: s.z_mode == "bins" and s.z_bins == G.BinSpec("width", 4)),
        ("F/F0 GFP vs time binned by DAPI quartiles", lambda s: s.z_bins.n == 4),
        ("F/F0 GFP vs time split by DAPI at T=0 bins at 1e6, 2e6",
         lambda s: s.z_bins == G.BinSpec("custom", 3, (1e6, 2e6))),
        ("R/R0 Cy5/GFP at the end vs mCherry at T=0 in 5 bins",
         lambda s: s.x_bins == G.BinSpec("count", 5) and s.z is None),
        ("F/F0 GFP vs time, per run, SEM, log y",
         lambda s: s.split == "run" and s.error == "SEM" and s.log_y and not s.log_x),
        ("R/R0 Cy5/GFP vs mCherry, trajectories, spearman, all cells",
         lambda s: s.pairs == "trajectories" and s.corr == "spearman" and not s.included_only),
        ("F/F0 GFP vs time where summed nuclear DAPI at T=0 > 2e6",
         lambda s: len(s.filters) == 1 and s.filters[0].op == ">" and s.filters[0].a == 2e6 and
         s.filters[0].q == Q("nucleus", "DAPI", "total", "at", 0.0)),
        ("F/F0 GFP vs time where GFP x background at T=0 > 3 and condition = U2OS",
         lambda s: len(s.filters) == 2 and s.filters[0].q.measure == "xbg" and
         s.filters[1].kind == "condition" and s.filters[1].text == "U2OS"),
        ("F/F0 GFP vs time if max F/F0 GFP between 1.2 and 5",
         lambda s: s.filters[0].op == "between" and (s.filters[0].a, s.filters[0].b) == (1.2, 5)),
        ("F/F0 GFP vs time where DAPI max over 0-30 min > 5",
         lambda s: s.filters[0].op == ">" and s.filters[0].a == 5 and
         s.filters[0].q.t2 == 30.0),
        ("F/F0 GFP vs time, drift corrected frames 2-9", lambda s: s.drift == (2, 9)),
        ("whole-cell mCherry average vs nucleus Cy5 peak",
         lambda s: s.y.comp == "cell" and s.y.measure == "mean" and s.x.time == "max"),
        ("F/F0 GFP vs time, per condition, 95% CI, no points",
         lambda s: s.split == "condition" and s.error == "95% CI" and not s.show_cells),
    ]
    bad = []
    for text, check in V:
        p = P.parse(text, CH, cp)
        try:
            good = p.spec is not None and not p.errors and check(p.spec)
        except Exception as e:                                 # noqa: BLE001
            good = False
            print("   ", text, e)
        if not good:
            bad.append((text, [i.message for i in p.issues], p.spec))
    ok(f"F {len(V)} variations understood", not bad, bad[:3])
    p = P.parse("jf646 nuc vs time", CH, cp)
    ok("F a dye name: 'jf646' read as Cy5, said in a note (not an error)",
       p.ok and p.spec.y.chan == "Cy5" and any("Cy5" in i.message and i.level == "note"
                                               for i in p.issues))
    p = P.parse("F/F0 of GPF vs time", CH, cp)
    e = p.errors
    ok("F a typo: underlined with a suggestion (GPF -> GFP)",
       e and e[0].word == "GPF" and "GFP" in e[0].suggestions and
       P.parse("F/F0 of GPF vs time", CH, cp).spec is None, [(i.word, i.suggestions) for i in e])
    p = P.parse("F/F0 nuclear GFP vs time banana", CH, cp)
    ok("F an unknown word: an error at its place, the graph still made",
       p.spec is not None and p.errors and p.errors[0].word == "banana" and
       "F/F0 nuclear GFP vs time banana"[p.errors[0].start:p.errors[0].end] == "banana")
    p = P.parse("R/R0 GFP vs time", CH, cp)
    ok("F R/R0 with one channel: says it needs two", any("needs two channels" in i.message
                                                        for i in p.issues))
    p = P.parse("GFP vs mCherry vs DAPI vs Cy5", CH, cp)
    ok("F four things: 'At most three'", any("At most three" in i.message for i in p.issues))
    p = P.parse("", CH, cp)
    ok("F empty: a hint, no spec", p.spec is None and p.issues and p.issues[0].level == "note")
    p = P.parse("F/F0 GFP vs time where DAPI is big", CH, cp)
    ok("F a condition without a comparison: says how",
       any("needs a comparison" in i.message for i in p.issues))
    p = P.parse("mito GFP vs time", CH, cp)
    ok("F a compartment the run lacks: says which it has", any("no mitochondrial" in i.message
                                                               for i in p.issues))
    # spec -> sentence -> spec
    rng = np.random.default_rng(3)
    meas = list(G.MEASURES)
    times = [("trace", None, None, "tp"), ("at", 30.0, None, "tp"), ("at", 0.0, None, "tp"),
             ("at", 5.0, None, "min"), ("at", 12.0, None, "frame"), ("end", None, None, "tp"),
             ("max", None, None, "tp"), ("min", 0.0, 30.0, "tp"), ("mean", 0.0, 10.0, "tp"),
             ("auc", 0.0, 20.0, "min"), ("slope", 2.0, 9.0, "frame"), ("mean", -5.0, 5.0, "tp")]

    def rq(trace_ok=True):
        m = meas[rng.integers(len(meas))]
        need = G.MEASURES[m][1]
        a, b = rng.choice(CH, 2, replace=False)
        chan = "" if need == 0 else (f"{a}/{b}" if need == 2 else str(a))
        t = times[rng.integers(len(times))]
        comp = str(rng.choice(COMPS3))
        comp2 = ""
        if need == 1 and m in ("mean", "total", "ff0") and rng.random() < 0.15:
            comp2 = "cytoplasm" if comp != "cytoplasm" else "nucleus"
        return Q(comp, chan, m, t[0], t[1], t[2], t[3], comp2)
    trips = 0
    fails = []
    for i in range(300):
        y = rq()
        x = rq() if rng.random() < 0.8 else None
        z = rq() if rng.random() < 0.5 else None
        spec = G.GraphSpec(
            y=y, x=x, z=z, z_mode="bins" if (z is not None and rng.random() < 0.5) else "colour",
            z_bins=G.BinSpec(*[("count", 3, ()), ("width", 4, ()),
                               ("custom", 3, (1e6, 2.5e6))][rng.integers(3)]),
            x_bins=(G.BinSpec("count", 5) if x is not None and z is None and rng.random() < 0.3
                    else None),
            filters=tuple([G.Filter(q=rq(), op=str(rng.choice([">", "<", ">=", "<="])), a=2e6)]
                          if rng.random() < 0.3 else []) +
            tuple([G.Filter(q=rq(), op="between", a=1.5, b=3.0)] if rng.random() < 0.2 else []) +
            tuple([G.Filter(kind="condition", text="U2OS")] if rng.random() < 0.1 else []),
            error=str(rng.choice(G.ERRORS)), split=str(rng.choice(G.SPLITS)),
            log_x=bool(rng.random() < 0.2), log_y=bool(rng.random() < 0.2),
            corr=str(rng.choice(["pearson", "spearman", "none"])),
            pairs=str(rng.choice(["points", "trajectories"])),
            show_cells=bool(rng.random() < 0.8), show_mean=bool(rng.random() < 0.9),
            included_only=bool(rng.random() < 0.8),
            drift=(2, 9) if rng.random() < 0.1 else None)
        if spec.z is None:
            spec = replace(spec, z_mode="colour", z_bins=G.BinSpec())
        elif spec.z_mode == "colour":
            spec = replace(spec, z_bins=G.BinSpec())
        sen = P.sentence(spec)
        back = P.parse(sen, CH, cp)
        if back.spec == spec and not back.errors:
            trips += 1
        elif len(fails) < 3:
            fails.append((sen, [i.message for i in back.errors],
                          {k: (getattr(spec, k), getattr(back.spec, k, None))
                           for k in ("y", "x", "z", "filters") if back.spec is not None and
                           getattr(spec, k) != getattr(back.spec, k)}))
    ok(f"F spec -> sentence -> spec gives the same spec ({trips} / 300 random graphs)",
       trips == 300, fails)
    s1 = P.sentence(P.parse(EX2, CH, cp).spec)
    ok("F the canonical sentence of example 2 reads well", s1 ==
       "intensity whole cell mCherry at T=30 vs F/F0 nuclear GFP binned by summed nuclear "
       "DAPI at T=0 in 3 equal-count bins", s1)
    c1 = P.complete("R/R0 nuc", CH, cp)
    c2 = P.complete("R/R0 nuclear Cy5/", CH, cp)
    c3 = P.complete("R/R0 nuclear Cy5/GFP ", CH, cp)
    c4 = P.complete("F/F0 nuclear mch", CH, cp)
    ok("F autocomplete: the word being typed, channel B of a ratio, the next words",
       "R/R0 nuclear" in c1 and "R/R0 nuclear Cy5/GFP" in c2 and
       "R/R0 nuclear Cy5/GFP vs" in c3 and "R/R0 nuclear Cy5/GFP binned by" in c3 and
       "F/F0 nuclear mCherry" in c4, (c1, c2[:3], c3[:4], c4))
    h = P.highlight_html("F/F0 of GPF vs time", P.parse("F/F0 of GPF vs time", CH, cp).issues)
    ok("F highlighting: the unknown word underlined in red",
       "<span style='color:#C00000;text-decoration:underline'>GPF</span>" in h, h)
    t0 = time.perf_counter()
    for _ in range(50):
        P.parse(EX2, CH, cp)
    ms = (time.perf_counter() - t0) / 50 * 1000
    ok(f"F parsing is fast ({ms:.1f} ms per sentence)", ms < 30)


# ---------------------------------------------------------------- G
def part_g():
    sp = P.parse(EX2, CH, list(COMPS3)).spec
    G.add_recent("a", sp)
    G.add_recent("b", sp)
    d = G.add_recent("a", sp)
    ok("G recent: newest first, no duplicates", [r["sentence"] for r in d["recent"]] == ["a", "b"])
    for i in range(20):
        G.add_recent(f"s{i}", sp)
    ok("G recent: at most 12 kept", len(G.load_recipes()["recent"]) == G.RECENT_MAX)
    G.save_favourite("DAPI bins", P.sentence(sp), sp)
    d = G.load_recipes()
    ok("G favourite saved with its spec; read back equal",
       d["favourites"][0]["name"] == "DAPI bins" and
       G.GraphSpec.from_dict(d["favourites"][0]["spec"]) == sp and G.is_favourite(P.sentence(sp)))
    ok("G recipes live in the user's settings folder (PETERPIPER_HOME)",
       G._recipes_file().is_file() and str(OUT / "home") in str(G._recipes_file()))
    G.remove_favourite("DAPI bins")
    ok("G favourite removed", not G.load_recipes()["favourites"])
    G._recipes_file().write_text("{not json", encoding="utf-8")
    ok("G a damaged recipes file: empty lists, no crash",
       G.load_recipes() == {"favourites": [], "recent": []})
    run = synth_run()
    res = G.compute([run], sp)
    p1 = G.save_table(OUT / "tab.csv", P.sentence(sp), sp, res)
    p2 = G.save_table(OUT / "tab.csv", P.sentence(sp), sp, res)
    txt = Path(p1).read_text(encoding="utf-8")
    ok("G CSV: the sentence and the conditions on top, one row per cell, never overwritten",
       txt.startswith("Graph: " + P.sentence(sp)) and "Conditions: included cells only" in txt
       and Path(p2).name == "tab_2.csv" and txt.count("\nU2OS dish1,") >= 58, Path(p2).name)
    px = G.save_table(OUT / "tab.xlsx", P.sentence(sp), sp, res)
    from openpyxl import load_workbook
    wb = load_workbook(px)
    ok("G Excel: Cells, Means and Methods sheets; numbers as numbers",
       wb.sheetnames == ["Cells", "Means", "Methods"] and
       any(isinstance(wb["Cells"].cell(r, 5).value, float) for r in range(2, 9)) and
       str(wb["Methods"].cell(2, 1).value).startswith("Graph: "), wb.sheetnames)


# ---------------------------------------------------------------- H
def part_h(app):
    from PySide6.QtCore import QPointF, Qt
    from peterpiper.gui.graphbuilder import GraphBuilder
    G.warm_up()

    def pump(n=4):
        for _ in range(n):
            app.processEvents()
    run = synth_run()
    w = GraphBuilder()
    w.resize(1100, 720)
    w.show()
    w.set_runs([run])
    pump()
    ok("H opens with a sensible graph: F/F0 of the first channel vs time",
       w.spec().y == Q("nucleus", "Cy5", "ff0") and w.spec().x is None and
       w.ed.text() == "F/F0 nuclear Cy5 vs time")
    shots = []
    for i, (text, nm) in enumerate(((EX1, "ex1_rr0_vs_mcherry"), (EX2, "ex2_binned_by_dapi"),
                                    (EX3, "ex3_three_traces"))):
        p = w.set_sentence(text)
        w.redraw()
        pump()
        res = w.result()
        path = SHOTS / f"v40_graphs_{nm}.png"
        w.grab().save(str(path))
        shots.append(path)
        ok(f"H example {i + 1} drawn ({res.shape}, {res.n_cells} cells) - {path.name}",
           p.ok and not res.error and res.n_cells == 58 and path.stat().st_size > 20000,
           res.error)
    ok("H the rows follow the sentence (example 3: Z = nuclear DAPI as colour)",
       w.row_z.quantity() == Q("nucleus", "DAPI", "mean") and
       w.cmb_zmode.currentData() == "colour" and w.row_y.cmb_b.isVisible())
    w.row_x.cmb_m.setCurrentIndex(w.row_x.cmb_m.findData("total"))
    pump()
    ok("H the sentence follows the rows", w.ed.text().startswith(
        "R/R0 nuclear Cy5/GFP vs summed cytoplasmic mCherry"), w.ed.text())
    w.swap("xy")
    ok("H swap X and Y", w.spec().x == Q("nucleus", "Cy5/GFP", "rr0") and
       w.ed.text().startswith("summed cytoplasmic mCherry vs R/R0"))
    w.swap("xz")
    ok("H swap X and Z", w.spec().z == Q("nucleus", "Cy5/GFP", "rr0"))
    # timings: 60 cells x 121 t x 4 ch x 3 comps
    times = {}
    for text in ("F/F0 GFP vs time binned by summed nuclear DAPI at T=0", EX1, EX2, EX3,
                 "R/R0 nuclear Cy5/GFP vs cytoplasmic mCherry, trajectories"):
        w.set_sentence(text)
        w.redraw()
        w.redraw()
        times[text[:30]] = round(w.last_draw_ms, 1)
    ok(f"H redraw under 150 ms for 60 cells x 121 t x 4 ch x 3 comps {times}",
       max(times.values()) < 150, times)
    # chips
    w.set_sentence("F/F0 GFP vs time")
    w.ed_cond.setText("summed nuclear DAPI at T=0 > 3e5")
    w._add_condition_typed()
    pump()
    chips = [c.text() for c in w._chip_widgets]
    ok("H '+ condition' adds a chip; the sentence gets 'where ...'",
       len(w.spec().filters) == 1 and any("summed nuclear DAPI at T=0 > 300000" in c
                                          for c in chips) and " where " in w.ed.text(), chips)
    n_before = w.result().n_cells
    w._chip_widgets[1].click()
    pump()
    w.redraw()
    ok("H clicking a chip removes the condition", not w.spec().filters and
       w.result().n_cells >= n_before)
    w._chip_widgets[0].click()
    pump()
    w.redraw()
    ok("H the 'included cells only' chip switches to all cells",
       not w.spec().included_only and w.result().n_cells == 60 and
       "all cells" in w._chip_widgets[0].text())
    w.ed_cond.setText("DAPI is big")
    w._add_condition_typed()
    ok("H a condition that is not understood is refused (red), nothing added",
       not w.spec().filters and "needs a comparison" in w.ed_cond.toolTip())
    # star / recent
    w.set_sentence(EX1)
    w._remember_recent()
    w.set_sentence("F/F0 GFP vs time")
    w._remember_recent()
    w._star()
    ok("H star: the graph becomes a favourite; the recent strip lists the others",
       w.btn_star.isChecked() and G.is_favourite(w.sentence()) and
       any(b.text().startswith("★") for b in w._recent_btns) and
       any("R/R0 nuclear Cy5/GFP" in b.text() for b in w._recent_btns),
       [b.text() for b in w._recent_btns])
    rb = next(b for b in w._recent_btns if "R/R0 nuclear Cy5/GFP" in b.text())
    rb.click()
    pump()
    ok("H one click on a recent graph shows it again", w.spec().y == Q("nucleus", "Cy5/GFP",
                                                                         "rr0"))
    # hover / click
    w.set_sentence(EX2)
    w.redraw()
    pump()
    got = []
    w.cell_clicked.connect(lambda key, k: got.append((key, k)))
    vb = w.plot.getPlotItem().getViewBox()
    xs, ys, meta = w._pts
    i = int(np.flatnonzero(np.isfinite(xs) & np.isfinite(ys))[0])
    sp = vb.mapViewToScene(QPointF(float(xs[i]), float(ys[i])))
    w._hover(sp)

    class Ev:
        def scenePos(self):
            return sp
    w._clicked(Ev())
    ok("H hover a point: cell number and its values; click: cell_clicked(run, k)",
       w.lbl_read.text().startswith(f"Cell {meta[i][2] + 1}") and got == [(run.key, meta[i][2])],
       (w.lbl_read.text(), got))
    # auto-fit
    vb.setRange(xRange=(100, 200), yRange=(100, 200), padding=0)
    w.resize(900, 600)
    pump(6)
    (x0, x1), (y0, y1) = vb.viewRange()
    fx = np.isfinite(xs) & np.isfinite(ys)
    ok("H after a resize the plot fits all points again",
       x0 <= xs[fx].min() and x1 >= xs[fx].max() and y0 <= ys[fx].min() and y1 >= ys[fx].max(),
       ((x0, x1), (xs[fx].min(), xs[fx].max())))
    vb.setRange(xRange=(100, 200), yRange=(100, 200), padding=0)
    w.set_sentence(EX1)
    w.redraw()
    pump()
    (x0, x1), _ = vb.viewRange()
    xs2 = w._pts[0]
    ok("H after a graph change the plot fits again", x0 <= np.nanmin(xs2) and
       x1 >= np.nanmax(xs2))
    # options
    w._set_opt("log_y", True)
    w.redraw()
    ok("H log Y: the drawn values are log10", np.nanmax(w._pts[1]) < 1 and
       w._opt_actions["log_y"].isChecked() and "log y" in w.ed.text())
    w._set_opt("drift", (2, 9))
    ok("H the drift add-on from Options: in the spec and the sentence",
       w.spec().drift == (2, 9) and "drift corrected frames 2-9" in w.ed.text())
    ok("H 'Runs' split menu hidden for one run", not w.menu_split.menuAction().isVisible())
    # export
    pn = w.export_image(OUT / "plot.png")
    ps = w.export_image(OUT / "plot.svg")
    pt = w.export_table(OUT / "plot.csv")
    ok("H export PNG / SVG / CSV", Path(pn).stat().st_size > 5000 and
       "<svg" in Path(ps).read_text(encoding="utf-8", errors="ignore")[:2000] and
       Path(pt).read_text(encoding="utf-8").lstrip('"').startswith("Graph: ") and
       Path(ps).stat().st_size < 3e6, (pn, ps, Path(ps).stat().st_size))
    # 1366 x 768: the builder at the size of the analysis window's graph area
    w.resize(1000, 560)
    pump(4)
    ok("H at a small size the plot keeps a usable height (>= 180 px)", w.plot.height() >= 180,
       w.plot.height())
    # typing: partial sentence -> autocomplete model
    w._typed("F/F0 nuclear GF")
    ok("H typing fills the autocomplete list", "F/F0 nuclear GFP" in w._model.stringList())
    w.close()
    return shots


# ---------------------------------------------------------------- I
def part_i(app):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QMessageBox
    from peterpiper.gui.comparewin import CompareWindow
    for _n in ("information", "warning", "critical"):
        setattr(QMessageBox, _n, staticmethod(lambda *a, **k: QMessageBox.Ok))
    CompareWindow.ASK_UNKNOWN = False

    def pump(n=4):
        for _ in range(n):
            app.processEvents()
    cw = CompareWindow()
    runs = [as_compare_run(synth_run("U2OS dish1", seed=1), str(OUT / "u1.npz")),
            as_compare_run(synth_run("U2OS dish2", seed=2), str(OUT / "u2.npz")),
            as_compare_run(synth_run("HeLa dish1", seed=3), str(OUT / "h1.npz"))]
    for i, r in enumerate(runs):
        cw._insert_row(r.path, dict(nd2=r.nd2, fingerprint=dict(quick=f"q{i}", size=100 + i)))
        cw._runs[r.path] = r
        cw._busy = True
        cw._use(r.path).setCheckState(Qt.Checked)
        cw._busy = False
    cw._mark_duplicates()
    cw.setWindowState(Qt.WindowNoState)
    cw.resize(1366, 768)
    cw.show()
    cw.refresh()
    pump(6)
    b = cw.builder
    ok("I Compare opens on 'Graphs across runs' (the builder); the averages box is hidden",
       cw.page() == "graphs" and cw.tabs.tabText(0) == "Graphs across runs" and
       not cw._settings_scroll.isVisible() and b.isVisible())
    ok("I the builder has the three ticked runs, conditions from the cell lines",
       sorted((r.name, r.condition) for r in b.runs()) ==
       [("HeLa dish1", "HeLa"), ("U2OS dish1", "U2OS"), ("U2OS dish2", "U2OS")],
       [(r.name, r.condition) for r in b.runs()])
    b.set_sentence(EX2.replace("T=30", "T=30") + ", per condition")
    b.redraw()
    pump()
    res = b.result()
    ok("I colour by condition across runs: U2OS (2 dishes) and HeLa",
       not res.error and len(res.groups) == 6 and res.n_runs == 3 and
       b.menu_split.menuAction().isVisible(), (res.error, [g.label for g in res.groups]))
    b.set_sentence("F/F0 GFP vs time, per run")
    b.redraw()
    pump()
    ok("I colour by run: one mean per run in the list's colours",
       sorted(g.label.split(" (")[0] for g in b.result().groups) ==
       ["HeLa dish1", "U2OS dish1", "U2OS dish2"] and
       len({g.colour for g in b.result().groups}) == 3)
    path = SHOTS / "v40_graphs_compare_1366x768.png"
    cw.grab().save(str(path))
    ok(f"I screenshot {path.name}", path.stat().st_size > 20000)
    cw._use(runs[2].path).setCheckState(Qt.Unchecked)
    pump()
    ok("I unticking a run updates the builder", sorted(r.name for r in b.runs()) ==
       ["U2OS dish1", "U2OS dish2"], [r.name for r in b.runs()])
    got = []
    cw._builder_cell(runs[0].path, 4)
    ok("I a clicked cell selects its run in the list",
       cw.current_run() == runs[0].path and "Cell 5" in b.lbl_read.text(), cw.current_run())
    cw.show_page("average")
    pump()
    ok("I the averages page still draws (time course of the run means) and shows its box",
       cw.page() == "average" and cw._settings_scroll.isVisible() and cw.btn_close.isVisible()
       and cw.btn_save.isVisible())
    from peterpiper import kinetics as K
    ok("I kinetics are an add-on: none ticked for saving by default",
       K.DEFAULT_SAVE == () and not any(c.isChecked() for c in cw.chk_kin.values()))
    cw.close()
    cw2 = CompareWindow()
    ok("I the page and the builder's graph are remembered",
       cw2.page() == "average" and cw2.builder.sentence().startswith("F/F0 nuclear GFP vs time"),
       (cw2.page(), cw2.builder.sentence()))
    cw2.show_page("graphs")
    cw2.close()
    del got


def main():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    part_a()
    part_b()
    part_c()
    part_d()
    part_e()
    part_f()
    part_g()
    shots = part_h(app)
    part_i(app)
    print("Screenshots:", ", ".join(str(s) for s in shots))
    total = N_OK[0] + len(FAILS)
    print(f"{N_OK[0]} / {total} checks passed")
    if FAILS:
        print("FAILED:", FAILS)
        sys.exit(1)


if __name__ == "__main__":
    main()
