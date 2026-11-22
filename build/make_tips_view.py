"""
PeterPiper 4.0: the hover pictures of the 'view' part (background first,
N x background, baseline, the 4-page flow). Remake them with

    python build/make_tips_view.py

They go to app/peterpiper/assets/tips/view_*.png (640 x 320 px, shown at
320 x 160 in the hover; light background, clear labels). Synthetic drawings
only - no real data.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt                                    # noqa: E402
import numpy as np                                                 # noqa: E402
from matplotlib.patches import FancyBboxPatch, Rectangle          # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "app" / "peterpiper" / "assets" / "tips"
sys.path.insert(0, str(ROOT / "app"))

W_IN, H_IN, DPI = 6.4, 3.2, 100           # 640 x 320 px
BG = "#F7F8FA"
INK = "#1E2328"
MUTED = "#5F6670"
GREEN = "#2E9E3E"


def _fig():
    fig = plt.figure(figsize=(W_IN, H_IN), dpi=DPI, facecolor=BG)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 64)
    ax.set_ylim(0, 32)
    ax.axis("off")
    return fig, ax


def _save(fig, name: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"{name}.png"
    fig.savefig(p, dpi=DPI, facecolor=BG)
    plt.close(fig)
    return p


def _field(ax, x0, y0, w, h, seed=3):
    """A small dark 'microscope field' with a few cells."""
    rng = np.random.default_rng(seed)
    n = 120
    img = np.full((n, n), 0.12) + rng.normal(0, 0.015, (n, n))
    yy, xx = np.mgrid[0:n, 0:n]
    for cy, cx, r, b in ((40, 38, 13, 0.85), (85, 30, 10, 0.35), (78, 88, 12, 0.55),
                         (28, 95, 8, 0.3)):
        img += b * np.exp(-((yy - cy) ** 2 + (xx - cx) ** 2) / (2 * r * r))
    ax.imshow(np.clip(img, 0, 1), cmap="Greens_r" if False else "gray",
              extent=(x0, x0 + w, y0, y0 + h), vmin=0, vmax=1, zorder=1)
    return n


def bg_why() -> Path:
    fig, ax = _fig()
    _field(ax, 2, 3, 26, 26)
    # the cell's outline and the background box (dashed, green)
    th = np.linspace(0, 2 * np.pi, 80)
    ax.plot(2 + 26 * 38 / 120 + 3.0 * np.cos(th), 3 + 26 * (1 - 40 / 120) + 3.0 * np.sin(th),
            color="#FFD400", lw=2, zorder=3)
    ax.add_patch(Rectangle((12.6, 3.8), 5.6, 4.4, fill=False, ls="--", lw=2.2, ec="#3CFF3C",
                           zorder=3))
    ax.text(15.4, 9.0, "Background", color="#3CFF3C", fontsize=9, ha="center",
            fontweight="bold", zorder=4)
    ax.text(10.2, 25.8, "Cell", color="#FFD400", fontsize=9, ha="center", fontweight="bold",
            zorder=4)
    # the sum on the right
    ax.text(31, 26, "How bright is the cell?", fontsize=12, fontweight="bold", color=INK)
    ax.text(31, 21.2, "Cell mean", fontsize=11, color=INK)
    ax.text(50, 21.2, "1040", fontsize=11, color=INK, ha="right", fontweight="bold")
    ax.text(31, 17.4, "Background mean", fontsize=11, color=INK)
    ax.text(50, 17.4, "200", fontsize=11, color=GREEN, ha="right", fontweight="bold")
    ax.plot([31, 51], [16.2, 16.2], color=INK, lw=1)
    ax.add_patch(FancyBboxPatch((31, 10.6), 24, 4.2, boxstyle="round,pad=0.3",
                                fc="#12161C", ec="none"))
    ax.text(32, 11.9, "GFP", color="#E1E4E8", fontsize=12)
    ax.text(38.5, 11.9, "5.2x", color="#F0E442", fontsize=13, fontweight="bold")
    ax.text(45, 11.9, "background", color="#E1E4E8", fontsize=9)
    ax.text(31, 6.4, "1.0x = no brighter than the background.", fontsize=9.5, color=MUTED)
    ax.text(31, 3.4, "Pick a dark, empty place: no cells, no specks.", fontsize=9.5,
            color=MUTED)
    return _save(fig, "view_bg_why")


def nxbg() -> Path:
    from peterpiper import bgmultiple as BM
    fig, ax = _fig()
    ax.text(2, 28, "N x background on every cell", fontsize=12, fontweight="bold", color=INK)
    ax.text(2, 24.6, "= cell mean / background mean, per channel, at the timepoint shown",
            fontsize=9.5, color=MUTED)
    edges = ("below 1.5x", "1.5 - 3x", "3 - 10x", "10x and more")
    words = ("hardly above background", "above background", "clearly above",
             "far above background")
    vals = (1.1, 2.4, 5.2, 14)
    for i in range(4):
        y = 19 - i * 4.6
        ax.add_patch(FancyBboxPatch((2.5, y - 1.2), 12.5, 3.4, boxstyle="round,pad=0.25",
                                    fc="#12161C", ec="none"))
        ax.text(3.4, y - 0.1, "GFP", color="#E1E4E8", fontsize=11)
        ax.text(8.6, y - 0.1, BM.fmt_multiple(vals[i]), color=BM.LEVEL_COLOURS[i], fontsize=12,
                fontweight="bold")
        ax.text(17.5, y - 0.1, edges[i], color=INK, fontsize=10.5, fontweight="bold")
        ax.text(33, y - 0.1, words[i], color=MUTED, fontsize=10)
    return _save(fig, "view_nxbg")


def baseline() -> Path:
    fig, ax = _fig()
    ax.text(2, 28, "The baseline (F0)", fontsize=12, fontweight="bold", color=INK)
    ax.text(2, 24.8, "Each timepoint is divided by the value at the baseline:",
            fontsize=9.5, color=MUTED)
    ax.text(42, 24.8, "F/F0 = F(t) / F(baseline)", fontsize=10, color=INK, fontweight="bold")
    x = np.linspace(4, 60, 60)
    t_add = 26.0
    y = 7 + 0.15 * np.sin(x) + np.where(x > t_add, 9 * (1 - np.exp(-(x - t_add) / 6)), 0)
    ax.plot([4, 60], [5, 5], color=MUTED, lw=1)
    ax.plot([4, 4], [5, 22], color=MUTED, lw=1)
    ax.plot(x, y, color="#2299CC", lw=2.4)
    xb = 20.0
    ax.plot([xb, xb], [5, 21], color="#0073E6", lw=1.6, ls="--")
    ax.plot([xb], [7 + 0.15 * np.sin(xb)], "o", color="#0073E6", ms=7)
    ax.text(xb - 0.6, 18.5, "baseline\n= time 0", color="#0073E6", fontsize=9.5, ha="right",
            fontweight="bold")
    ax.annotate("drug added", xy=(t_add, 7.4), xytext=(32, 12.5), fontsize=9.5, color=INK,
                arrowprops=dict(arrowstyle="->", color=INK, lw=1))
    ax.text(5, 2.2, "Pick a timepoint just BEFORE you add anything.", fontsize=9.5, color=MUTED)
    return _save(fig, "view_baseline")


def pages() -> Path:
    fig, ax = _fig()
    ax.text(2, 28, "Four pages, left to right", fontsize=12, fontweight="bold", color=INK)
    names = ("1 Start", "2 Draw", "3 Track & check", "4 Graphs & export")
    words = ("movie, queue,\nserver, backup", "background first,\nthen the cells",
             "follow the cells,\ninclude / exclude", "graphs, Excel,\nPrism, CSV")
    xs = (1.2, 15.4, 28.8, 46.6)
    ws = (12, 11, 15.2, 16.2)
    for i, (x, w) in enumerate(zip(xs, ws)):
        cur = i == 1
        ax.add_patch(FancyBboxPatch((x, 17.5), w, 4.5, boxstyle="round,pad=0.3",
                                    fc="#3D7FD6" if cur else "#E4E8EE", ec="none"))
        ax.text(x + w / 2, 19.6, names[i], ha="center", va="center", fontsize=9.5,
                fontweight="bold", color="white" if cur else INK)
        ax.text(x + w / 2, 12.5, words[i], ha="center", va="center", fontsize=9, color=MUTED)
        if i < 3:
            ax.text(x + w + 0.75, 19.6, "›", fontsize=14, color=MUTED, va="center")
    ax.text(2, 4.5, "◀ Back always goes one page back.   Next ▶ says what it will do.",
            fontsize=9.5, color=INK)
    return _save(fig, "view_pages")


def main() -> list:
    return [bg_why(), nxbg(), baseline(), pages()]


if __name__ == "__main__":
    for p in main():
        print(p)
