"""
Response kinetics (V2.6): how fast each dish responds after its baseline.

Used by the Compare / average window. Every number is read from ONE curve per
dish - the dish mean (the mean of its included cells at every timepoint, the
same curve the group average is made of; compare.group_line), on the dish's own
time axis from its own baseline (time 0 = the baseline timepoint). Nothing is
smoothed or fitted to a model.

  window           from time 0 to the window end. Default: the SAME end for
                   every dish shown (the end of the shortest dish), so dishes
                   imaged for different lengths are measured over the same
                   time - otherwise a still-changing curve gets a larger
                   maximum, and a later t½, just because its movie is longer.
                   Optional: each dish to its own last frame.
  baseline level   the curve's value at the baseline timepoint (time 0) - the
                   same reference F/F0 and R/R0 are normalised to. (Frames
                   before it are not averaged in: they often still drift.)
  baseline SD      SD of the last BASE_SD_FRAMES frames up to and including time
                   0 (noise check only)
  response         the time in the window where the curve is furthest from the
                   baseline level (rise or fall: the larger change wins);
                   peak = its value
  amplitude        peak - baseline level (signed)
  t10 / t½ / t90   first time after 0 the curve reaches baseline + 10 / 50 / 90 %
                   of the amplitude, linearly interpolated between the two
                   frames on either side of the crossing (the frame times
                   themselves are not changed). Searched from time 0 up to the
                   peak.
  10-90% rise time t90 - t10
  initial slope    least-squares straight line through the curve from time 0 up
                   to and including the first frame at or past half-maximum (at
                   least 2 frames): the initial rate of the response (quantity
                   per minute, or per timepoint when the frame interval is not
                   known)
  maximum rate     the steepest step between two consecutive frames from time 0
                   up to the peak (in the direction of the response)

Flags (written next to the numbers, never hidden): peak at the end of the
window (may still be changing), change smaller than 3 SD of the baseline frames
(no clear response; only with >= 3 such frames), no frame at / before time 0,
no frame after it.

Per group (replicate dishes): each parameter's mean, SD (n - 1), SEM, 95% CI =
t(0.975, n - 1) x SEM and n = dishes with a value (graphstyle.describe, the
same arithmetic as everywhere else). The kinetics of the group's mean curve is
written too, for reference - it is not the mean of the dish values.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import numpy as np

from . import graphstyle as GS

# key, name, what the unit is ("time" | "rate" | "value")
PARAMS = (("t_half", "t½ max", "time"),
          ("slope", "Initial rise slope", "rate"),
          ("max_rate", "Maximum rate", "rate"),
          ("t_max", "Time to max", "time"),
          ("amp", "Amplitude (max - baseline)", "value"),
          ("rise", "10-90% rise time", "time"))
PARAM_NAMES = {k: n for k, n, _u in PARAMS}
FILE_TAGS = {"t_half": "t-half-max", "slope": "initial-slope", "max_rate": "max-rate",
             "t_max": "time-to-max", "amp": "amplitude", "rise": "rise-10-90"}
DEFAULT_SAVE = ("t_half", "slope")
NOISE_K = 3.0                    # 'no clear response': |amplitude| < 3 SD of the baseline
BASE_SD_FRAMES = 5               # frames up to time 0 used for the baseline SD


@dataclass
class Kin:
    """The kinetics of one curve (NaN = not defined; flags say why)."""
    base: float = np.nan
    base_n: int = 0              # frames used for the baseline SD
    base_sd: float = np.nan
    direction: str = ""          # "rise" | "fall" | ""
    peak: float = np.nan
    t_max: float = np.nan
    amp: float = np.nan
    t10: float = np.nan
    t_half: float = np.nan
    t90: float = np.nan
    rise: float = np.nan
    slope: float = np.nan
    slope_n: int = 0
    max_rate: float = np.nan
    n_frames: int = 0            # frames after time 0 inside the window
    t_end: float = np.nan        # the window end used
    flags: List[str] = field(default_factory=list)

    def value(self, key: str) -> float:
        return float(getattr(self, key))


def _crossing(xs: np.ndarray, ys: np.ndarray, target: float, s: float) -> Tuple[float, int]:
    """(time, index of the first frame at / past target) - s = +1 rise, -1 fall;
    linear between the frame before and that frame. (NaN, -1) = never."""
    for j in range(len(ys)):
        if s * (ys[j] - target) >= 0:
            if j == 0:
                return float(xs[0]), 0
            x0, x1, y0, y1 = xs[j - 1], xs[j], ys[j - 1], ys[j]
            if y1 == y0:
                return float(x1), j
            return float(x0 + (target - y0) * (x1 - x0) / (y1 - y0)), j
    return np.nan, -1


def curve_end(x, y) -> float:
    """The last time with a value (NaN if none)."""
    x = np.asarray(x, float).ravel()
    y = np.asarray(y, float).ravel()
    ok = np.isfinite(x) & np.isfinite(y)
    return float(x[ok].max()) if ok.any() else np.nan


def curve_kinetics(x, y, t_end: Optional[float] = None, tol: float = 1e-9) -> Kin:
    """The kinetics of one curve (x: time from the baseline, y: its values;
    NaN values are left out; t_end: the window end, None = the last frame).
    See the module text."""
    x = np.asarray(x, float).ravel()
    y = np.asarray(y, float).ravel()
    ok = np.isfinite(x) & np.isfinite(y)
    if t_end is not None and np.isfinite(t_end):
        ok &= x <= t_end + max(tol, 1e-6 * abs(t_end))
    x, y = x[ok], y[ok]
    o = np.argsort(x, kind="stable")
    x, y = x[o], y[o]
    k = Kin(t_end=float(x.max()) if x.size else np.nan)
    pre = x <= tol
    k.n_frames = int((~pre).sum())
    if not pre.any():
        k.flags.append("no frame at or before the baseline")
        return k
    if not (~pre).any():
        k.flags.append("no frame after the baseline")
        return k
    j0 = int(np.flatnonzero(pre)[-1])                 # the baseline frame (time 0)
    k.base = float(y[j0])
    sd_y = y[pre][-BASE_SD_FRAMES:]
    k.base_n = int(sd_y.size)
    if k.base_n >= 2:
        k.base_sd = float(np.std(sd_y, ddof=1))
    xp, yp = x[~pre], y[~pre]
    dev = yp - k.base
    i = int(np.argmax(np.abs(dev)))
    s = 1.0 if dev[i] >= 0 else -1.0
    k.direction = "rise" if s > 0 else "fall"
    k.peak, k.t_max = float(yp[i]), float(xp[i])
    k.amp = k.peak - k.base
    if i == len(xp) - 1:
        k.flags.append(("max" if s > 0 else "min") + " at the end of the window - may still be "
                       + ("rising" if s > 0 else "falling"))
    if k.base_n >= 3 and np.isfinite(k.base_sd) and abs(k.amp) < NOISE_K * k.base_sd:
        k.flags.append(f"change smaller than {NOISE_K:g} SD of the baseline frames - "
                       f"no clear response")
    if k.amp == 0:
        k.flags.append("no change from the baseline")
        return k
    seq_x = x[j0:j0 + 1 + i + 1]                      # time 0 ... the peak
    seq_y = y[j0:j0 + 1 + i + 1]
    k.t10, _ = _crossing(seq_x, seq_y, k.base + 0.1 * k.amp, s)
    k.t_half, jh = _crossing(seq_x, seq_y, k.base + 0.5 * k.amp, s)
    k.t90, _ = _crossing(seq_x, seq_y, k.base + 0.9 * k.amp, s)
    if np.isfinite(k.t10) and np.isfinite(k.t90):
        k.rise = k.t90 - k.t10
    if jh >= 0:
        m = max(2, jh + 1)
        fx, fy = seq_x[:m], seq_y[:m]
        if len(fx) >= 2 and np.ptp(fx) > 0:
            k.slope = float(np.polyfit(fx, fy, 1)[0])
            k.slope_n = int(len(fx))
    if len(seq_x) >= 2:
        r = np.diff(seq_y) / np.diff(seq_x)
        r = r[np.isfinite(r)]
        if r.size:
            k.max_rate = float(r[np.argmax(s * r)])
    return k


def units(key: str, x_label: str, quantity: str) -> str:
    """'min', 'per min' ... for a parameter (x_label: the time axis title)."""
    t = "min" if str(x_label).endswith("(min)") else "timepoints"
    u = next(u for kk, _n, u in PARAMS if kk == key)
    if u == "time":
        return t
    if u == "rate":
        return f"{quantity} per {'min' if t == 'min' else 'timepoint'}"
    return quantity


def axis_title(key: str, x_label: str, quantity: str) -> str:
    return f"{PARAM_NAMES[key]} ({units(key, x_label, quantity)})"


# ------------------------------------------------------------- items
@dataclass
class Item:
    """One point of a kinetics graph: a run (its cells' mean curve) or a
    group (its dishes' values)."""
    label: str
    kin: List[Kin]               # one per dish (a run: one)
    names: List[str]             # dish names
    dishes: list = field(repr=False, default_factory=list)   # compare.Series per dish
    mean_kin: Optional[Kin] = None                           # the group mean curve

    def values(self, key: str) -> np.ndarray:
        return np.array([k.value(key) for k in self.kin], float)


def dish_curve(s) -> Tuple[np.ndarray, np.ndarray]:
    """(x, the dish mean at every timepoint) of a compare.Series."""
    return np.asarray(s.x, float), GS.describe(s.y).mean


def common_end(lines: Sequence) -> float:
    """The end of the shortest dish among these lines (NaN if none)."""
    from .compare import GroupLine
    ends = []
    for ln in lines:
        for s in (ln.dishes if isinstance(ln, GroupLine) else [ln]):
            e = curve_end(*dish_curve(s))
            if np.isfinite(e):
                ends.append(e)
    return float(min(ends)) if ends else np.nan


def items_for(lines: Sequence, same_window: bool = True) -> List[Item]:
    """Kinetics items for what the compare window shows: compare.Series (each
    run) or compare.GroupLine (groups: every dish's own curve). same_window:
    every dish up to common_end(lines); else each to its own last frame."""
    from .compare import GroupLine
    t_end = common_end(lines) if same_window else None
    out = []
    for ln in lines:
        if isinstance(ln, GroupLine):
            kins = [curve_kinetics(*dish_curve(s), t_end=t_end) for s in ln.dishes]
            mk = curve_kinetics(ln.x, GS.describe(ln.dish_mean).mean, t_end=t_end)
            out.append(Item(ln.label, kins, [s.label for s in ln.dishes], list(ln.dishes), mk))
        else:
            out.append(Item(ln.label, [curve_kinetics(*dish_curve(ln), t_end=t_end)],
                            [ln.label], [ln]))
    return out


def window_text(items: Sequence[Item], x_label: str, same_window: bool) -> str:
    t = "min" if str(x_label).endswith("(min)") else "timepoints"
    ends = sorted({round(k.t_end, 6) for it in items for k in it.kin if np.isfinite(k.t_end)})
    if not ends:
        return ""
    if same_window:
        return f"Kinetics window: 0 - {ends[0]:g} {t} for every dish (the shortest dish)."
    return (f"Kinetics window: each dish to its own end ({ends[0]:g} - {ends[-1]:g} {t})."
            if len(ends) > 1 else f"Kinetics window: 0 - {ends[0]:g} {t}.")


def summary(item: Item, key: str) -> GS.Summary:
    """mean, SD, SEM, 95% CI, n over the item's dishes for one parameter."""
    return GS.describe(item.values(key)[None, :])


def _f(v) -> str:
    return "" if v is None or not np.isfinite(v) else f"{float(v):.6g}"


def dish_table(items: Sequence[Item], x_label: str, quantity: str, comp: str) -> List[list]:
    from .compare import COMP_LABELS
    t = "min" if str(x_label).endswith("(min)") else "timepoints"
    rate = f"per {'min' if t == 'min' else 'timepoint'}"
    rows = [["Group", "Dish (run)", ".nd2 file", "Run file", "Compartment", "Quantity",
             "Included cells", f"Window end ({t})", "Frames after time 0",
             "Baseline level (value at time 0)", "Baseline SD", "Baseline SD frames",
             "Response", "Peak", f"Time to max ({t})", "Amplitude (peak - baseline)",
             f"t10 ({t})", f"t½ max ({t})", f"t90 ({t})", f"10-90% rise time ({t})",
             f"Initial rise slope ({rate})", "Slope frames", f"Maximum rate ({rate})", "Flags"]]
    for it in items:
        for nm, k, s in zip(it.names, it.kin, it.dishes or [None] * len(it.kin)):
            run = getattr(s, "run", None)
            rows.append([it.label, nm, run.nd2 if run else "",
                         Path(run.path).name if run else "", COMP_LABELS.get(comp, comp),
                         quantity, getattr(s, "n", ""), _f(k.t_end), k.n_frames, _f(k.base),
                         _f(k.base_sd), k.base_n, k.direction, _f(k.peak), _f(k.t_max),
                         _f(k.amp), _f(k.t10), _f(k.t_half), _f(k.t90), _f(k.rise),
                         _f(k.slope), k.slope_n, _f(k.max_rate), "; ".join(k.flags)])
    return rows


def group_table(items: Sequence[Item], x_label: str, quantity: str, comp: str) -> List[list]:
    from .compare import COMP_LABELS
    rows = [["Group", "Compartment", "Quantity", "Parameter", "Unit", "Mean of dishes", "SD",
             "SEM", "95% CI (half-width)", "n (dishes with a value)", "Dishes",
             "Of the group mean curve (reference)", "Each dish"]]
    for it in items:
        for key, name, _u in PARAMS:
            sm = summary(it, key)
            mk = it.mean_kin.value(key) if it.mean_kin is not None else np.nan
            rows.append([it.label, COMP_LABELS.get(comp, comp), quantity, name,
                         units(key, x_label, quantity), _f(sm.mean[0]), _f(sm.sd[0]),
                         _f(sm.sem[0]), _f(sm.ci95[0]), int(sm.n[0]), len(it.kin), _f(mk),
                         "; ".join(f"{n}: {_f(v) or '-'}" for n, v in
                                   zip(it.names, it.values(key)))])
    return rows


def methods(same_window: bool = True) -> str:
    return (
        "Kinetics (per dish, from the dish mean curve = mean of its included cells at every "
        "timepoint, time from its own baseline; nothing smoothed or fitted): " +
        ("every dish was measured over the same window, from time 0 to the end of the "
         "shortest dish shown; " if same_window else
         "each dish was measured from time 0 to its own last frame; ") +
        "baseline level = the curve's value at the baseline timepoint (time 0, the F0 / R0 "
        "reference); peak = the time in the window where the curve is furthest from the "
        "baseline level (rise or fall); amplitude = peak - baseline level; t10 / t½ max / "
        "t90 = first time after 0 the curve reaches baseline + 10 / 50 / 90 % of the "
        "amplitude, linearly interpolated between the two frames around the crossing "
        "(searched from time 0 up to the peak); 10-90% rise time = t90 - t10; initial rise "
        "slope = least-squares straight line through the curve from time 0 up to and "
        "including the first frame at or past half-maximum; maximum rate = steepest step "
        "between consecutive frames up to the peak. Groups: mean, SD (n - 1), SEM = SD / "
        "sqrt(n), 95% CI = t(0.975, n - 1) x SEM over the dishes (n = dishes with a value); "
        "the kinetics of the group mean curve is listed for reference. Flagged: peak at the "
        f"end of the window (may still be changing); change smaller than {NOISE_K:g} SD of "
        f"the last {BASE_SD_FRAMES} frames up to time 0 (>= 3 frames).")


METHODS = methods(True)


# ------------------------------------------------------------- drawing
def _offsets(n: int, width: float = 0.24) -> np.ndarray:
    """Fixed, symmetric horizontal offsets for n dish dots (no randomness)."""
    if n <= 1:
        return np.zeros(max(n, 0))
    return np.linspace(-width / 2, width / 2, n)


def draw(ax, items: Sequence[Item], key: str, colours: Sequence[str], style, x_label: str,
         quantity: str, title: str) -> None:
    """matplotlib dot plot: each dish a dot, the group mean as a bar with the
    style's error (SEM / SD / 95% CI / none) across the dishes."""
    st = GS.coerce(style)
    fs = float(st.font_pt)
    fam = GS.font_family()
    e = st.error if st.error in ("SEM", "SD", "95% CI") else None
    for i, (it, col) in enumerate(zip(items, colours)):
        v = it.values(key)
        pos = i + 1
        fin = np.isfinite(v)
        ax.plot(pos + _offsets(len(v))[fin], v[fin], "o", color=col, markersize=max(
            3.0, st.symbol_size * 1.2), markerfacecolor=col, markeredgewidth=0, zorder=3)
        sm = summary(it, key)
        m = sm.mean[0]
        if np.isfinite(m):
            ax.plot([pos - 0.28, pos + 0.28], [m, m], color=col, lw=max(1.0, st.mean_width * 2),
                    zorder=2)
            err = {"SEM": sm.sem, "SD": sm.sd, "95% CI": sm.ci95}.get(e) if e else None
            if err is not None and np.isfinite(err[0]):
                ax.errorbar([pos], [m], yerr=[err[0]], color=col, capsize=6,
                            lw=max(0.8, st.mean_width * 1.5), zorder=2)
    ax.set_xticks(range(1, len(items) + 1))
    ax.set_xticklabels([f"{it.label}\n(n = {int(summary(it, key).n[0])})" for it in items],
                       rotation=30 if len(items) > 3 else 0,
                       ha="right" if len(items) > 3 else "center", family=fam,
                       fontsize=fs * GS.TICK_SCALE * 0.8)
    ax.set_xlim(0.4, len(items) + 0.6)
    ax.set_ylabel(axis_title(key, x_label, quantity), fontsize=fs, family=fam)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.tick_params(axis="y", labelsize=fs * GS.TICK_SCALE)
    if title:
        ax.set_title(GS._wrap(title, ax.figure.get_figwidth(), fs), fontsize=fs, family=fam)


def save_figure(path, items, key, colours, style, x_label, quantity, title, fmt=None,
                dpi=300) -> str:
    import matplotlib
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    from .compare import IMAGE_FORMATS
    from .safety import new_output_file
    st = GS.coerce(style)
    path = Path(path)
    fmt = (fmt or path.suffix.lstrip(".") or "png").lower()
    fmt = {"jpg": "jpeg", "tif": "tiff"}.get(fmt, fmt)
    if fmt not in IMAGE_FORMATS:
        raise ValueError(f"Graphs can be saved as {', '.join(IMAGE_FORMATS)}, not '{fmt}'.")
    fig = Figure(figsize=(max(st.width_in, 1.2 + 1.1 * len(items)), st.height_in), dpi=dpi)
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    draw(ax, items, key, colours, st, x_label, quantity, title)
    fig.tight_layout()
    kw = {"pil_kwargs": {"quality": 95}} if fmt == "jpeg" else \
        ({"pil_kwargs": {"compression": "tiff_lzw"}} if fmt == "tiff" else {})
    with matplotlib.rc_context({"svg.fonttype": "none", "pdf.fonttype": 42}):
        with new_output_file(path) as (used, stream):
            fig.savefig(stream, format=fmt, dpi=dpi, **kw)
    return str(used)


def write_prism(path, items: Sequence[Item], key: str, colours: Sequence[str], style,
                x_label: str, quantity: str, title: str, notes: str = "") -> str:
    """A .prism with the graph made (the PeterPiper template): one data set per run /
    group at X = its position (1, 2, 3 ...; the legend names them), the dishes'
    values as its replicates - Prism draws mean +/- error across the dishes.
    Plus a column table (one column per group, one row per dish) for a scatter
    dot plot and a 'mean, SEM, n' table."""
    from .prismfile import write_compare_prism
    yt = axis_title(key, x_label, quantity)
    runs = []
    for i, it in enumerate(items):
        v = it.values(key)
        n = int(np.isfinite(v).sum())
        lab = (f"{i + 1}: {it.label} (n = {n} dish{'es' if n != 1 else ''})"
               if len(it.kin) > 1 or it.mean_kin is not None else f"{i + 1}: {it.label}")
        runs.append((lab, np.array([float(i + 1)]), v[None, :]))
    cols = [(it.label, it.values(key), it.names) for it in items]
    return write_compare_prism(
        str(path), runs, "Group (see the legend)" if any(it.mean_kin is not None
                                                          for it in items) else
        "Run (see the legend)", PARAM_NAMES[key], yt, title or " ", list(colours),
        style=dict(GS.coerce(style).to_dict(), baseline_line=False, x_min=0.5,
                   x_max=len(items) + 0.5), notes=notes,
        sheet_title=f"{PARAM_NAMES[key]} - graph data", columns_extra=[
            (f"{PARAM_NAMES[key]} - each dish (column table)", yt, cols)])
