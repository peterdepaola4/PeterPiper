"""
V2.7 plot builder for 'Compare / average runs': what to plot, in words.

    Plot [R/R0] of [GFP] over [Cy5] in the [nucleus]
      vs [Time]                                  (the usual time course)
      vs [Intensity] of [GFP] in the [whole cell]  (one measure against another)
    right Y axis: [none] or another measure      (only against Time)

A MEASURE is a compartment + a quantity of compare.quantity_names ('R/R0
GFP/Cy5', 'F/F0 GFP', 'Ratio GFP/Cy5' = the ratio NOT normalised, 'Intensity
GFP' = background-subtracted). Every number comes from compare.series - the
export's own arithmetic - so a measure here is exactly the export's sheet.

Y against another measure X ('PairLine'), both measured in the SAME cells: a
cell counts only when it is included in both compartments (a cell is one
column in every compartment, PeterPiper's cell numbering). Points:

  'trajectory'  one point per timepoint, in time order: the mean of X and the
                mean of Y over the replicates (Each run: its cells; Groups -
                mean of dish means: the dish means, n = dishes; pooled: all
                cells). Error bars on both X and Y.
  'cells'       one point per cell (Each run, pooled) or per dish (mean of dish
                means), at one timepoint after the baseline or averaged over a
                window of timepoints after the baseline (nothing interpolated;
                NaN values left out of the window mean).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import compare as C
from . import graphstyle as GS

KINDS = (("R/R0", "R/R0 (ratio ÷ its baseline)"),
         ("F/F0", "F/F0 (intensity ÷ its baseline)"),
         ("ΔR/R0", "ΔR/R0 (R/R0 − 1)"),
         ("ΔF/F0", "ΔF/F0 (F/F0 − 1)"),
         ("Ratio", "Ratio (not normalised)"),
         ("Intensity", "Intensity (background-subtracted)"),
         ("Raw intensity", "Raw intensity (no background subtracted)"),
         ("Sum intensity", "Sum intensity (total signal)"),
         ("Background", "Background (of the dish)"),
         ("Comp. ratio", "Compartment ratio (e.g. nucleus / cytoplasm)"),
         ("Comp. ratio/R0", "Compartment ratio ÷ its baseline"),
         ("Area", "Area (ROI size)"))
# V2.8: what each measure is and what it tells you (the dropdown tooltips)
EXPLAIN = {
    "R/R0": "The ratio of two channels (A / B, both background-subtracted) divided by its "
            "own value at the baseline timepoint, per cell. 1 = no change. Use it for "
            "ratiometric sensors (e.g. ExRai/GFP): it cancels differences in expression level "
            "and cell thickness between cells, so you see the response itself.",
    "F/F0": "One channel's background-subtracted intensity divided by its own value at the "
            "baseline timepoint, per cell. 1 = no change, 1.5 = 50% brighter. Use it to compare "
            "how much cells change, whatever their starting brightness.",
    "ΔR/R0": "R/R0 minus 1: the change as a fraction (0 = no change, 0.2 = +20%). Same "
             "information as R/R0, a common way to report it.",
    "ΔF/F0": "F/F0 minus 1: the change as a fraction (0 = no change, 0.5 = +50%). The usual "
             "way calcium and other intensity sensors are reported.",
    "Ratio": "Channel A / channel B (both background-subtracted), NOT divided by the baseline. "
             "Use it to compare the absolute ratio between cells or conditions (e.g. a sensor "
             "that starts higher in one cell line).",
    "Intensity": "The mean brightness of the ROI minus the background, in camera counts. Use "
                 "it to see expression level or absolute changes; it depends on exposure and "
                 "laser power, so compare only images taken the same way.",
    "Raw intensity": "The mean brightness of the ROI as recorded, background NOT subtracted. "
                     "Mainly for checking: compare it with Background to see how far above "
                     "the background a cell really is.",
    "Sum intensity": "Background-subtracted mean × the ROI's area in pixels: the total signal "
                     "in the ROI. Use it when the amount (not the concentration) matters, e.g. "
                     "a protein moving into a shrinking or growing compartment.",
    "Background": "The background region's mean brightness: one value per timepoint for the "
                  "whole dish (not per cell). Use it to check bleaching, focus drift or "
                  "something floating through the background region.",
    "Comp. ratio": "A channel's intensity in one compartment divided by its intensity in "
                   "another, per cell (e.g. nucleus / cytoplasm = N/C ratio). Use it for "
                   "translocation: a protein moving into the nucleus raises N/C.",
    "Comp. ratio/R0": "The compartment ratio divided by its own value at the baseline "
                      "timepoint: how much the translocation changed in each cell (1 = no "
                      "change).",
    "Area": "The ROI's size in µm² (pixels when the pixel size is unknown). Use it to see "
            "cells or nuclei swelling, shrinking or being redrawn badly - a sudden jump often "
            "means a tracking problem.",
}
TIME = "time"
TIMEPOINT = "timepoint"
POINTS = (("trajectory", "Trajectory: one point per timepoint (mean of the cells)"),
          ("cells_at", "Each cell at one timepoint"),
          ("cells_window", "Each cell, mean over a window of timepoints"))
POINTS_EXPLAIN = {
    "trajectory": "One point per timepoint: the mean X and mean Y of the cells (or of the dish "
                  "means), joined in time order. Shows how two measures change TOGETHER over "
                  "the movie - e.g. does the nuclear signal rise before or after the cytoplasmic "
                  "one (a loop means one lags the other).",
    "cells_at": "One dot per cell at one timepoint (frames after the baseline). Shows whether "
                "cells that are high in X are also high in Y - a correlation across cells, e.g. "
                "do brighter-expressing cells respond more.",
    "cells_window": "One dot per cell, each the mean over a window of timepoints after the "
                    "baseline - the same as 'each cell at one timepoint' but less noisy.",
}
COMP_WORDS = {"nucleus": "nucleus", "cell": "whole cell", "cytoplasm": "cytoplasm",
              "mito": "mitochondria"}


# ------------------------------------------------------------------ measures
@dataclass(frozen=True)
class Measure:
    comp: str
    quantity: str            # compare.quantity_names text, e.g. 'R/R0 GFP/Cy5'

    @property
    def kind(self) -> str:
        return C.split_name(self.quantity)[0]

    def text(self) -> str:
        """'R/R0 of GFP over Cy5 in the nucleus'."""
        k, a, b, other = C.split_name(self.quantity)
        where = COMP_WORDS.get(self.comp, self.comp)
        if k == "Area":
            return f"Area of the {where}"
        if k == "Background":
            return f"Background of {a} (the dish)"
        if k.startswith("Comp. ratio"):
            what = "Compartment ratio" + (" ÷ baseline" if k.endswith("R0") else "")
            return f"{what} of {a} in the {where} over the {COMP_WORDS.get(other, other)}"
        what = f"{k} of {a}" + (f" over {b}" if b else "")
        return f"{what} in the {where}"

    def short(self) -> str:
        """'R/R0 GFP/Cy5 - Nucleus' (axis titles, table columns)."""
        return f"{self.quantity} - {C.COMP_LABELS.get(self.comp, self.comp)}"

    def to_dict(self) -> dict:
        return {"comp": self.comp, "quantity": self.quantity}

    @staticmethod
    def from_dict(d) -> Optional["Measure"]:
        if isinstance(d, dict) and d.get("comp") and d.get("quantity"):
            return Measure(str(d["comp"]), str(d["quantity"]))
        return None


RATIO_KINDS = ("R/R0", "Ratio", "ΔR/R0")             # 'A over B' (two channels)
COMP_RATIO_KINDS = ("Comp. ratio", "Comp. ratio/R0")   # 'in X over the Y' (two compartments)


def split_quantity(q: str) -> Tuple[str, str, str]:
    """'R/R0 GFP/Cy5' -> ('R/R0', 'GFP', 'Cy5'); 'F/F0 GFP' -> ('F/F0', 'GFP', '');
    'Comp. ratio GFP ÷ cytoplasm' -> ('Comp. ratio', 'GFP', 'cytoplasm')."""
    k, a, b, other = C.split_name(q)
    return k, a, (other if k in COMP_RATIO_KINDS else b)


def join_quantity(kind: str, a: str = "", b: str = "") -> str:
    if kind == "Area":
        return "Area"
    if kind in COMP_RATIO_KINDS:
        return f"{kind} {a} ÷ {b}"
    return f"{kind} {a}/{b}" if kind in RATIO_KINDS else f"{kind} {a}"


def options(runs: Sequence[C.Run]) -> Dict[str, List[str]]:
    """{compartment: quantities every run has there} (compare's order)."""
    return {c: C.common_quantities(runs, c) for c in C.common_comps(runs)}


# ------------------------------------------------------------- the plot spec
@dataclass
class Spec:
    """What the builder says. x None = Time (x_axis 'time': minutes from the
    baseline; 'timepoint': timepoints from the baseline); y2 = a second measure
    on a right Y axis (V2.8: also when X is a measure)."""
    y: Measure
    x: Optional[Measure] = None
    y2: Optional[Measure] = None
    points: str = "trajectory"
    at: int = 0                     # frames after the baseline ('cells_at')
    win: Tuple[int, int] = (0, 0)   # frames after the baseline, inclusive ('cells_window')
    x_axis: str = TIME

    def sentence(self) -> str:
        s = f"Plot {self.y.text()} vs " + (self.x.text() if self.x else (
            "timepoint" if self.x_axis == TIMEPOINT else "time"))
        if self.y2 is not None:
            s += f", and {self.y2.text()} on the right Y axis"
        if self.x is not None:
            s += {"trajectory": " - one point per timepoint",
                  "cells_at": f" - each cell at {self.at} frames after the baseline",
                  "cells_window": f" - each cell, mean over frames {self.win[0]}-{self.win[1]} "
                                  f"after the baseline"}.get(self.points, "")
        return s + "."

    def to_dict(self) -> dict:
        return dict(y=self.y.to_dict(), x=self.x.to_dict() if self.x else None,
                    y2=self.y2.to_dict() if self.y2 else None, points=self.points,
                    at=int(self.at), win=[int(self.win[0]), int(self.win[1])],
                    x_axis=self.x_axis)

    def problems(self) -> List[str]:
        """V2.8: plain warnings when the plot does not make sense as asked (the
        window shows them in red; what can still be drawn is drawn)."""
        out = []
        if self.x is not None and self.x == self.y:
            out.append("X and Y are the same measure - every point lies on a straight line.")
        if self.y2 is not None and self.y2 == self.y:
            out.append("The right Y axis shows the same measure as the left one.")
        dish = [m for m in (self.y, self.x) if m is not None and not C.per_cell(m.quantity)]
        if self.x is not None and dish and self.points != "trajectory":
            out.append("Background is one value per dish, not per cell, so it cannot be shown "
                       "per cell - shown per timepoint (trajectory) instead.")
        if self.x is not None and dish and self.points == "trajectory":
            out.append("Background is a dish measure: X and Y are each averaged over their own "
                       "values (no cell-by-cell pairing).")
        return out

    @staticmethod
    def from_dict(d) -> Optional["Spec"]:
        if not isinstance(d, dict):
            return None
        y = Measure.from_dict(d.get("y"))
        if y is None:
            return None
        w = d.get("win") or (0, 0)
        return Spec(y=y, x=Measure.from_dict(d.get("x")), y2=Measure.from_dict(d.get("y2")),
                    points=str(d.get("points") or "trajectory"), at=int(d.get("at") or 0),
                    win=(int(w[0]), int(w[1])),
                    x_axis=TIMEPOINT if d.get("x_axis") == TIMEPOINT else TIME)


# --------------------------------------------------------- one measure vs another
@dataclass
class PairLine:
    """Y against X for one run (Each run) or one group. x, y: 'trajectory' T x r
    (r replicates: cells or dish means; the point is the mean of each row),
    'cells' n x 1 (one point per cell or dish). t: the time of each row
    (trajectory) or nothing. names: the replicate / point names."""
    label: str
    points: str
    mode: str                         # 'runs' | 'dishes' | 'pooled'
    x: np.ndarray
    y: np.ndarray
    t: np.ndarray
    t_label: str
    names: List[str]
    n_dishes: int
    n_cells: int
    runs: List[C.Run] = field(repr=False, default_factory=list)
    note: str = ""

    @property
    def n(self) -> int:
        return int(self.y.shape[1]) if self.points == "trajectory" else int(self.y.shape[0])


def paired(run: C.Run, ym: Measure, xm: Measure, baseline: Optional[int],
           minutes: bool) -> Tuple[C.Series, C.Series]:
    """(Y series, X series) of the same cells: those included in both
    compartments, in the same column order. A dish-level measure (Background)
    is not paired: each keeps its own columns."""
    sy = C.series(run, ym.comp, ym.quantity, baseline, minutes)
    sx = C.series(run, xm.comp, xm.quantity, baseline, minutes)
    if not (C.per_cell(ym.quantity) and C.per_cell(xm.quantity)):
        return sy, sx
    both = [k for k in sy.cells if k in set(sx.cells)]
    iy = [sy.cells.index(k) for k in both]
    ix = [sx.cells.index(k) for k in both]
    sy = C.Series(sy.label, sy.x, sy.y[:, iy], sy.x_label, both, run)
    sx = C.Series(sx.label, sx.x, sx.y[:, ix], sx.x_label, both, run)
    return sy, sx


def _frames(s: C.Series, points: str, at: int, win: Tuple[int, int]) -> np.ndarray:
    """Rows of the series for 'cells_at' / 'cells_window' (frames after its own
    baseline; rows outside the run are dropped)."""
    b0 = int(np.argmin(np.abs(np.asarray(s.x, float))))     # the row at time 0 (baseline)
    lo, hi = (at, at) if points == "cells_at" else (min(win), max(win))
    rows = [b0 + k for k in range(int(lo), int(hi) + 1)]
    return np.asarray([r for r in rows if 0 <= r < len(s.x)], int)


def _cell_values(s: C.Series, rows: np.ndarray) -> np.ndarray:
    """Each cell's value at those rows (mean over them, NaN left out)."""
    if not len(rows) or s.y.shape[1] == 0:
        return np.full(s.y.shape[1], np.nan)
    with np.errstate(invalid="ignore"):
        return np.nanmean(s.y[rows], axis=0) if len(rows) > 1 else s.y[rows[0]].astype(float)


def pair_lines(spec: Spec, groups: Sequence[Tuple[str, Sequence[C.Run]]], mode: str,
               baseline: Optional[int], minutes: bool) -> Tuple[List[PairLine], str]:
    """The lines for spec (spec.x set) - one per run (mode 'runs': groups are
    single runs) or per group. Returns (lines, warning)."""
    warn = []
    out = []
    if not (C.per_cell(spec.y.quantity) and C.per_cell(spec.x.quantity)) and \
            spec.points != "trajectory":
        spec = Spec(spec.y, spec.x, spec.y2, "trajectory", spec.at, spec.win, spec.x_axis)
    for label, runs in groups:
        pairs = [paired(r, spec.y, spec.x, baseline, minutes) for r in runs]
        use = [(sy, sx) for sy, sx in pairs if sy.n > 0 and sx.n > 0]
        lost = [sy.label for sy, sx in pairs if sy.n == 0 or sx.n == 0]
        if lost:
            warn.append(f"{label}: no cell is included in both compartments in "
                        + ", ".join(lost) + ".")
        if not use:
            continue
        n_cells = sum(sy.n for sy, _ in use)
        if spec.points == "trajectory":
            x_al, rows, note = C.align([sy for sy, _ in use])
            if mode == "dishes":
                X = np.column_stack([GS.describe(sx.y[r]).mean for (_, sx), r in zip(use, rows)])
                Y = np.column_stack([GS.describe(sy.y[r]).mean for (sy, _), r in zip(use, rows)])
                names = [sy.label for sy, _ in use]
            else:
                X = np.hstack([sx.y[r] for (_, sx), r in zip(use, rows)])
                Y = np.hstack([sy.y[r] for (sy, _), r in zip(use, rows)])
                names = [f"{sy.label} cell {k + 1}" for sy, _ in use for k in sy.cells] \
                    if C.per_cell(spec.y.quantity) else [sy.label for sy, _ in use]
            if note:
                warn.append(f"{label}: {note}")
            out.append(PairLine(label, "trajectory", mode, X, Y, x_al, use[0][0].x_label,
                                names, len(use), n_cells, [sy.run for sy, _ in use], note))
        else:
            xs, ys, names = [], [], []
            for sy, sx in use:
                rows = _frames(sy, spec.points, spec.at, spec.win)
                vx, vy = _cell_values(sx, rows), _cell_values(sy, rows)
                if not len(rows):
                    warn.append(f"{sy.label}: has no timepoint {spec.at if spec.points == 'cells_at' else spec.win} "
                                f"frames after its baseline.")
                if mode == "dishes":
                    with np.errstate(invalid="ignore"):
                        xs.append([np.nanmean(vx) if np.isfinite(vx).any() else np.nan])
                        ys.append([np.nanmean(vy) if np.isfinite(vy).any() else np.nan])
                    names.append(sy.label)
                else:
                    xs.append(vx)
                    ys.append(vy)
                    names += [f"{sy.label} cell {k + 1}" for k in sy.cells]
            X = np.concatenate(xs)[:, None] if xs else np.zeros((0, 1))
            Y = np.concatenate(ys)[:, None] if ys else np.zeros((0, 1))
            out.append(PairLine(label, spec.points, mode, X, Y, np.zeros(0), "", names,
                                len(use), n_cells, [sy.run for sy, _ in use]))
    return out, " ".join(warn)


def legend_label(p: PairLine) -> str:
    if p.mode == "runs":
        return f"{p.label} (n = {p.n_cells} cells)"
    if p.mode == "dishes":
        return f"{p.label} (n = {p.n_dishes} dishes, {p.n_cells} cells)"
    return f"{p.label} pooled (n = {p.n_cells} cells, {p.n_dishes} dishes)"


def point_stats(p: PairLine, error: str):
    """(x mean, x lo, x hi, y mean, y lo, y hi) per point. 'cells': the values
    themselves (no error bars)."""
    if p.points == "trajectory":
        xm, xl, xh, _n = GS.stats(p.x, error)
        ym, yl, yh, _n = GS.stats(p.y, error)
        return xm, xl, xh, ym, yl, yh
    x, y = p.x[:, 0], p.y[:, 0]
    return x, x, x, y, y, y


# --------------------------------------------------------------- drawing
def draw(ax, lines: Sequence[PairLine], colours: Sequence[str], style, spec: Spec,
         title: str, right=None) -> None:
    """matplotlib: trajectory = joined points in time order with X and Y error
    bars; cells = one dot per cell / dish."""
    from .prismfile import series_symbols
    st = GS.coerce(style)
    syms = series_symbols(st.to_dict(), len(lines))
    fam, fs = GS.font_family(), float(st.font_pt)
    for p, col, sym in zip(lines, colours, syms):
        mk, filled = C._MPL_SYM.get(sym, ("o", True))
        xm, xl, xh, ym, yl, yh = point_stats(p, st.error)
        ok = np.isfinite(xm) & np.isfinite(ym)
        if p.points == "trajectory" and st.error != "none":
            ax.errorbar(xm[ok], ym[ok], xerr=np.vstack([(xm - xl)[ok], (xh - xm)[ok]]),
                        yerr=np.vstack([(ym - yl)[ok], (yh - ym)[ok]]), fmt="none",
                        ecolor=col, elinewidth=max(st.mean_width, 0.5), capsize=2)
        ax.plot(xm[ok], ym[ok], ls="-" if p.points == "trajectory" and st.mean_width > 0
                else "none", lw=st.mean_width, color=col, marker=mk or "o",
                ms=st.symbol_size if p.points == "trajectory" else max(4.0, st.symbol_size),
                mfc=col if filled else "none", mec=col, label=legend_label(p))
        if ok.any() and p.points == "trajectory":    # V2.8: start (baseline) and end
            tt = np.where(np.isfinite(p.t), np.abs(p.t), np.inf)
            i0 = int(np.argmin(tt))
            i0 = i0 if ok[i0] else int(np.nonzero(ok)[0][0])
            i1 = int(np.nonzero(ok)[0][-1])
            ax.plot([xm[i0]], [ym[i0]], "o", ms=st.symbol_size * 2.4, mfc="none", mec=col,
                    mew=1.5, zorder=5)
            ax.plot([xm[i1]], [ym[i1]], "^", ms=st.symbol_size * 2.2, mfc=col, mec="black",
                    zorder=5)
        elif ok.any():                                # V2.8: the mean of the dots as a cross
            ex = GS.stats(xm[ok][None, :], st.error)
            ey = GS.stats(ym[ok][None, :], st.error)
            mx, my = ex[0][0], ey[0][0]
            ax.errorbar([mx], [my], xerr=[[mx - ex[1][0]], [ex[2][0] - mx]] if np.isfinite(
                ex[1][0]) else None, yerr=[[my - ey[1][0]], [ey[2][0] - my]] if np.isfinite(
                ey[1][0]) else None, fmt="+", ms=st.symbol_size * 3, color=col, lw=2,
                capsize=0, zorder=5)
    xt = st.x_title.strip() or spec.x.short()
    yt = st.y_title.strip() or spec.y.short()
    ax.set_xlabel(xt, fontsize=fs, family=fam)
    ax.set_ylabel(yt, fontsize=fs, family=fam)
    ax.tick_params(labelsize=fs * GS.TICK_SCALE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    if title:
        ax.set_title(GS._wrap(title, ax.figure.get_figwidth(), fs), fontsize=fs, family=fam)
    handles, labels = ax.get_legend_handles_labels()
    if right and right[0]:                    # V2.8: a second Y measure on a right axis
        lines2, sp2 = right
        ax2 = ax.twinx()
        for p, col in zip(lines2, colours):
            xm, _xl, _xh, ym, _yl, _yh = point_stats(p, st.error)
            ok = np.isfinite(xm) & np.isfinite(ym)
            h, = ax2.plot(xm[ok], ym[ok], ls="--" if p.points == "trajectory" else "none",
                          marker=None if p.points == "trajectory" else "x", color=col,
                          lw=max(st.mean_width, 0.5))
            handles.append(h)
            labels.append(f"{legend_label(p)} - {sp2.y.quantity} (right)")
        ax2.set_ylabel(sp2.y.short(), fontsize=fs, family=fam)
        ax2.tick_params(labelsize=fs * GS.TICK_SCALE)
    if lines:
        ax.legend(handles, labels, frameon=False, loc="center left",
                  bbox_to_anchor=(1.22 if right else 1.02, 0.5),
                  prop={"family": fam, "size": fs * GS.TICK_SCALE * 0.75})


def save_figure(path, lines, colours, style, spec: Spec, title, fmt=None, dpi=300,
                right=None) -> str:
    import matplotlib
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    from pathlib import Path
    from .safety import new_output_file
    st = GS.coerce(style)
    path = Path(path)
    fmt = {"jpg": "jpeg", "tif": "tiff"}.get((fmt or path.suffix.lstrip(".")).lower(),
                                            (fmt or path.suffix.lstrip(".")).lower())
    fig = Figure(figsize=(st.width_in * 1.45, st.height_in), dpi=dpi)
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    draw(ax, lines, colours, st, spec, title, right=right)
    fig.tight_layout()
    kw = {"pil_kwargs": {"quality": 95}} if fmt == "jpeg" else \
        ({"pil_kwargs": {"compression": "tiff_lzw"}} if fmt == "tiff" else {})
    with matplotlib.rc_context({"svg.fonttype": "none", "pdf.fonttype": 42}):
        with new_output_file(path) as (used, stream):
            fig.savefig(stream, format=fmt, dpi=dpi, **kw)
    return str(used)


# ----------------------------------------------------------------- tables
def table_rows(lines: Sequence[PairLine], spec: Spec) -> List[list]:
    """One row per point: its X and Y mean, SEM, SD, n (trajectory) or its
    values (cells / dishes)."""
    f = C._f
    xs, ys = spec.x.short(), spec.y.short()
    if lines and lines[0].points == "trajectory":
        rows = [["Line", "Statistic", "Point #", lines[0].t_label,
                 f"X mean: {xs}", "X SEM", "X SD", f"Y mean: {ys}", "Y SEM", "Y SD",
                 "n (dishes)" if lines[0].mode == "dishes" else "n (cells)"]]
        for p in lines:
            dx, dy = GS.describe(p.x), GS.describe(p.y)
            what = {"runs": "mean of its cells", "dishes": "mean of dish means",
                    "pooled": "pooled cells"}[p.mode]
            for i in range(len(p.t)):
                n = int(min(dx.n[i], dy.n[i]))
                rows.append([p.label, what, i + 1, f(p.t[i]), f(dx.mean[i]), f(dx.sem[i]),
                             f(dx.sd[i]), f(dy.mean[i]), f(dy.sem[i]), f(dy.sd[i]), n])
        return rows
    rows = [["Line", "Point", f"X: {xs}", f"Y: {ys}"]]
    for p in lines:
        for nm, xv, yv in zip(p.names, p.x[:, 0], p.y[:, 0]):
            rows.append([p.label, nm, f(xv), f(yv)])
    return rows


def notes_text(lines: Sequence[PairLine], spec: Spec, style) -> str:
    e = GS.error_label(GS.coerce(style).error)
    parts = [f"PeterPiper: {spec.sentence()}",
             "X and Y were measured in the same cells: a cell was used only when it was "
             "included in both compartments. Every value is the export's own arithmetic "
             "(Intensity = background-subtracted; F/F0 and R/R0 relative to the baseline "
             "timepoint; Ratio not normalised)."]
    if spec.points == "trajectory":
        what = {"runs": "the run's cells", "dishes": "the dish means (each dish = the mean "
                "of its cells; n = dishes)", "pooled": "all cells of the group pooled"}
        parts.append("Each point is one timepoint: mean" + (f" +/- {e}" if e else "") +
                     " of X and of Y over " + what.get(lines[0].mode if lines else "runs", "") +
                     ", joined in time order. Only frame times every dish of a group has "
                     "were used (nothing interpolated).")
    else:
        parts.append("Each point is one cell" + (" (dishes: the mean of the dish's cells)"
                                                  if lines and lines[0].mode == "dishes" else "")
                     + "; NaN values were left out of window means.")
    for p in lines:
        parts.append(f"{p.label}: {p.n_dishes} run(s), {p.n_cells} cells used.")
    return "\n".join(parts)


def save(folder, name: str, formats: Sequence[str], lines: Sequence[PairLine],
         colours: Sequence[str], style, spec: Spec, title: str, notes: str = "",
         right=None) -> List[str]:
    """.prism (graph made: trajectory = X mean, Y replicates so Prism draws the
    Y error; cells = one point each), pictures, CSV / Excel. right (V2.8):
    (lines, spec) of a second Y measure against the same X - a right axis in
    the pictures, its own tables (and graphs) in the .prism, its own CSV / sheet.
    Never overwrites."""
    from pathlib import Path
    from .export import clean_prefix
    from .safety import make_dirs
    folder = Path(folder)
    make_dirs(folder)
    name = clean_prefix(name, 150) or "comparison"
    st = GS.coerce(style)
    out: List[str] = []
    xt = st.x_title.strip() or spec.x.short()
    yt = st.y_title.strip() or spec.y.short()
    if "prism" in formats and lines:
        from .prismfile import write_compare_prism
        data = []
        for p in lines:
            if p.points == "trajectory":
                data.append((legend_label(p), GS.describe(p.x).mean, p.y))
            else:
                data.append((legend_label(p), p.x[:, 0], p.y))
        pst = st.to_dict()
        if spec.points != "trajectory":
            pst.update(mean_width=0.0, error="none")
        # X is a measure: the template's automatic X axis would start at 0 (made for
        # time) - the range of the data with 5 % room, unless the style sets one
        allx = np.concatenate([np.ravel(point_stats(p, st.error)[i]) for p in lines
                               for i in (1, 2)])
        allx = allx[np.isfinite(allx)]
        if allx.size and pst.get("x_min") is None and pst.get("x_max") is None:
            lo, hi = float(allx.min()), float(allx.max())
            pad = 0.05 * (hi - lo or abs(hi) or 1.0)
            pst.update(x_min=lo - pad, x_max=hi + pad)
        out.append(write_compare_prism(
            str(folder / f"{name}.prism"), data, xt, spec.y.short(), yt, title or " ",
            list(colours), style=pst, notes=notes, sheet_title=f"{spec.y.short()} vs "
            f"{spec.x.short()}", stacked=True,
            extra=[(f"{p.label} - X {spec.x.short()} each replicate", p.t, "each", p.x,
                    p.names, xt, p.t_label) for p in lines
                   if p.points == "trajectory" and p.x.shape[1] == len(p.names)] +
            [(f"{p.label} - {right[1].y.short()} (right axis) mean, SEM, n",
              point_stats(p, st.error)[0], "sen",
              (GS.describe(p.y).mean, GS.describe(p.y).sem, GS.describe(p.y).n.astype(float)),
              None, right[1].y.short(), xt)
             for p in (right[0] if right else []) if p.points == "trajectory"]))
    for f in C.IMAGE_FORMATS:
        if f in formats or (f == "jpeg" and "jpg" in formats) or (f == "tiff" and "tif" in formats):
            out.append(save_figure(folder / f"{name}.{C.IMAGE_EXT[f]}", lines, colours, st, spec,
                                   title, fmt=f, right=right))
    rows = table_rows(lines, spec)
    rows2 = table_rows(right[0], right[1]) if right and right[0] else None
    if "csv" in formats:
        out.append(C._write_csv(folder / f"{name}.csv", rows))
        if rows2:
            out.append(C._write_csv(folder / f"{name}_right_axis.csv", rows2))
    if "xlsx" in formats:
        out.append(C._write_xlsx(folder / f"{name}.xlsx", [
            ("Graph data", rows)] + ([("Right axis data", rows2)] if rows2 else []) + [
            ("Methods", [["Methods"]] + [[t] for t in notes.split("\n")
                                                              if t.strip()])]))
    return out
