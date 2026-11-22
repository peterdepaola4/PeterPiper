"""
Makes the graph builder's hover pictures (app/peterpiper/assets/tips/graphs_*.png,
about 320 x 160 px, light background, clear labels). Run again to remake them:

    python build/make_tips_graphs.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

OUT = Path(__file__).resolve().parents[1] / "app" / "peterpiper" / "assets" / "tips"
BINS = ("#440154", "#2A788E", "#7AD151")
RNG = np.random.default_rng(4)


def fig(n=1, w=3.2, h=1.6):
    f = Figure(figsize=(w, h), dpi=100)
    FigureCanvasAgg(f)
    f.patch.set_facecolor("#FFFFFF")
    axs = [f.add_subplot(1, n, i + 1) for i in range(n)]
    for a in axs:
        a.tick_params(labelsize=6, length=2)
        for s in ("top", "right"):
            a.spines[s].set_visible(False)
    return f, axs


def save(f, name):
    f.tight_layout(pad=0.4)
    OUT.mkdir(parents=True, exist_ok=True)
    f.savefig(OUT / f"{name}.png", facecolor="#FFFFFF")


def binned():
    f, (a,) = fig()
    x = RNG.normal(1.3, 0.15, 60)
    z = RNG.uniform(0, 1, 60)
    y = 500 + 600 * z + RNG.normal(0, 120, 60)
    b = np.digitize(z, np.quantile(z, [1 / 3, 2 / 3]))
    for i, lab in enumerate(("low Z", "middle Z", "high Z")):
        m = b == i
        a.scatter(x[m], y[m], s=8, color=BINS[i], alpha=0.6)
        a.errorbar(x[m].mean(), y[m].mean(), yerr=y[m].std(), xerr=x[m].std(), fmt="s",
                   color=BINS[i], ms=6, mec="k", lw=1.2, label=f"{lab} (n = {m.sum()})")
    a.set_xlabel("X  (e.g. F/F0 GFP)", fontsize=7)
    a.set_ylabel("Y", fontsize=7)
    a.legend(fontsize=6, frameon=False, loc="upper left")
    a.set_title("binned by Z: equal-n groups, each mean ± error", fontsize=7)
    save(f, "graphs_binned")


def colour():
    f, (a,) = fig()
    x = RNG.uniform(200, 2000, 60)
    z = RNG.uniform(0, 1, 60)
    y = 1 + 0.4 * z + RNG.normal(0, 0.05, 60)
    sc = a.scatter(x, y, s=10, c=z, cmap="viridis", vmax=1.15)
    cb = f.colorbar(sc, ax=a, pad=0.02)
    cb.ax.tick_params(labelsize=5)
    cb.set_label("Z", fontsize=7)
    a.set_xlabel("X", fontsize=7)
    a.set_ylabel("Y", fontsize=7)
    a.set_title("vs Z (colour): every cell coloured by Z", fontsize=7)
    save(f, "graphs_colour")


def times():
    f, (a,) = fig()
    t = np.arange(-5, 40)
    y = np.where(t < 0, 1.0, 1 + 0.5 * (1 - np.exp(-np.clip(t, 0, None) / 8)))
    a.plot(t, y, color="#0072B2", lw=1.6)
    a.axvline(0, color="#888888", ls="--", lw=0.8)
    a.text(0.5, 1.47, "T=0 = baseline", fontsize=6, color="#555555")
    a.plot([30], [y[t == 30][0]], "o", color="#D55E00", ms=5)
    a.text(26, y[t == 30][0] - 0.12, "at T=30", fontsize=7, color="#D55E00")
    a.axvspan(10, 20, color="#009E73", alpha=0.15)
    a.text(10.5, 1.06, "mean over\nT=10..20", fontsize=6, color="#00704F")
    a.set_xlabel("timepoints from the baseline (T)", fontsize=7)
    a.set_ylabel("F/F0", fontsize=7)
    save(f, "graphs_time")


def filt():
    f, (a,) = fig()
    x = RNG.uniform(0.5e6, 3.5e6, 70)
    y = RNG.normal(1.3, 0.12, 70)
    keep = x > 2e6
    a.scatter(x[~keep], y[~keep], s=8, color="#BBBBBB", label="left out")
    a.scatter(x[keep], y[keep], s=9, color="#0072B2", label="plotted")
    a.axvline(2e6, color="#D55E00", lw=1)
    a.text(2.05e6, 1.62, "DAPI summed at T=0 > 2e6", fontsize=6, color="#D55E00")
    a.set_xlabel("summed nuclear DAPI at T=0", fontsize=7)
    a.set_ylabel("Y", fontsize=7)
    a.legend(fontsize=6, frameon=False, loc="lower left")
    save(f, "graphs_filter")


def xbins():
    f, (a,) = fig()
    x = RNG.uniform(0, 10, 80)
    y = 1 + 0.05 * x + RNG.normal(0, 0.12, 80)
    a.scatter(x, y, s=6, color="#BBBBBB")
    e = np.linspace(0, 10, 6)
    for v in e[1:-1]:
        a.axvline(v, color="#CCCCCC", lw=0.7, ls=":")
    mx = [(x[(x >= lo) & (x < hi)]).mean() for lo, hi in zip(e, e[1:])]
    my = [(y[(x >= lo) & (x < hi)]).mean() for lo, hi in zip(e, e[1:])]
    sy = [(y[(x >= lo) & (x < hi)]).std() for lo, hi in zip(e, e[1:])]
    a.errorbar(mx, my, yerr=sy, fmt="o-", color="#0072B2", ms=4, lw=1.4)
    a.set_xlabel("X, cut into 5 bins", fontsize=7)
    a.set_ylabel("mean Y per bin", fontsize=7)
    save(f, "graphs_xbins")


def shapes():
    f, axs = fig(3, w=3.4, h=1.5)
    t = np.arange(40)
    for k in range(8):
        axs[0].plot(t, 1 + (0.3 + 0.05 * k) * (1 - np.exp(-t / 9)) + RNG.normal(0, .01, 40),
                    lw=0.7, alpha=0.6)
    axs[0].plot(t, 1 + 0.475 * (1 - np.exp(-t / 9)), color="k", lw=1.6)
    axs[0].set_title("Y vs time", fontsize=7)
    x, y = RNG.normal(0, 1, 40), RNG.normal(0, 1, 40)
    axs[1].scatter(x, 0.6 * x + y * 0.6, s=5, color="#0072B2")
    axs[1].set_title("one number each", fontsize=7)
    for k in range(6):
        xx = np.cumsum(RNG.normal(0, 0.2, 30)) + k
        yy = np.cumsum(RNG.normal(0.05, 0.1, 30))
        axs[2].scatter(xx, yy, c=np.arange(30), cmap="viridis", s=3, vmax=34)
    axs[2].set_title("two traces", fontsize=7)
    for a in axs:
        a.set_xticks([])
        a.set_yticks([])
    save(f, "graphs_shapes")


if __name__ == "__main__":
    for fn in (binned, colour, times, filt, xbins, shapes):
        fn()
    print("written to", OUT)
