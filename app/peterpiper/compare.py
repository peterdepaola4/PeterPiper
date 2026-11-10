"""
Compare runs (V2.4): the mean of several saved, tracked runs in one graph.

A run is an ROI / session file (.npz) that holds the tracking (every ROI at
every timepoint and the measurements). For each run the numbers are made
EXACTLY as that run's own export makes them: the same Measurements arithmetic
(plots._panels: background-subtracted F/F0, ratio, R/R0 ...), the run's own
baseline timepoint and frame interval, and only the cells it includes (its
saved include / exclude). Mean, SEM / SD / 95% CI and n per timepoint come
from graphstyle.stats / describe, as everywhere else.

Quantities are matched by channel NAME, so runs whose channels are in another
order still compare the same thing. Saved: one .prism (one data set per line,
legend, the template look with one colour per line), PNG / JPEG / SVG / TIFF /
PDF (same drawing, with a key), CSV and XLSX tables. Nothing is ever overwritten.

V2.5 - replicate averaging (groups of dishes). Each saved run is one dish (one
coverslip / well imaged as one .nd2 movie: many cells, one biosensor). Runs are
put into groups (e.g. 'U2OS NLS-met': three dishes). Two group statistics, on
the same aligned time axis:

  dish means (the replicate statistic; n = dishes)
      1. per dish and timepoint: the dish mean = arithmetic mean of that dish's
         INCLUDED cells that have a value there (the run's own export numbers:
         background-subtracted, its own baseline);
      2. per group and timepoint: mean of the dish means, SD (n - 1) across the
         dishes, SEM = SD / sqrt(n dishes), 95% CI = t(0.975, n - 1) x SEM;
         n = dishes with a value at that time. Every dish counts once, however
         many cells it has (the dish is the experimental unit).
  pooled cells (written too, for reference)
      every included cell of every dish of the group as one sample: mean, SD,
      SEM = SD / sqrt(n cells), n = cells. Cells of one dish are not independent
      replicates, so the dish-mean version is the one to report.

Time alignment (align()): every run's time counts from ITS OWN baseline (time 0
= its baseline timepoint), in minutes when every run knows its frame interval,
otherwise in timepoints. Only times that EVERY dish of the group has are
averaged (a time matches when it is within 0.1 % of the shortest frame interval,
i.e. the same frame time); nothing is interpolated. Dishes imaged at different
frame intervals or for different lengths keep only their common frame times; the
window and the methods text say how many were left out. Dishes without included
cells are left out of the group (and named).

same_nd2() (V2.5): which runs are analyses of the same .nd2 movie (same content
fingerprint, else the same .nd2 path, else the same file name and size), so the
window can warn before one dish is averaged as two.
"""
from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import graphstyle as GS
from .config import Settings
from .measure import Measurements
from .roifile import COMPS, COMP_WORDS, MEAS_FIELDS
from .safety import long_path, make_dirs, new_output_file

# one colour per run (colour-blind friendly order); the user can change each
PALETTE = ("#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#000000",
           "#F0E442")
KINDS = ("R/R0", "F/F0", "Ratio", "Intensity")       # list order of the quantities
COMP_LABELS = {"nucleus": "Nucleus", "cell": "Whole cell", "cytoplasm": "Cytoplasm",
               "mito": "Mitochondria"}


@dataclass
class Run:
    path: str
    label: str                       # what the graph calls it (the .nd2 name; editable)
    nd2: str                         # .nd2 file name it was saved for
    baseline: int                    # 1-based, as saved
    seconds_per_frame: float         # 0 = not known
    n_timepoints: int
    channels: List[str]
    meas: Dict[str, Measurements] = field(repr=False)
    included: Dict[str, List[int]] = field(repr=False)
    saved: str = ""
    um_per_px: float = 0.0           # V2.8: for areas in um2 (0 = not known: px)

    def comps(self) -> List[str]:
        return [c for c in COMPS if c in self.meas and self.included.get(c) is not None]

    def interval_text(self) -> str:
        s = self.seconds_per_frame
        return f"{s:g} s per frame" if s > 0 else "frame interval not known"


@dataclass
class Series:
    """One run's line: x (T) from ITS baseline, y (T x n) its included cells."""
    label: str
    x: np.ndarray
    y: np.ndarray
    x_label: str
    cells: List[int]
    run: Run = field(repr=False)

    @property
    def n(self) -> int:
        return int(self.y.shape[1])


# ------------------------------------------------------------------ loading
def load_run(path) -> Run:
    """A saved run with its tracking. ValueError (plain words) when the file
    cannot be used."""
    p = Path(path)
    try:
        with np.load(long_path(p), allow_pickle=False) as z:
            if "track_json" not in z:
                raise ValueError(f"{p.name} has no tracking saved - open its .nd2, load this "
                                 f"file and press TRACK, then save (File > Save ROIs now).")
            meta = json.loads(str(z["track_json"]))
            state = json.loads(str(z["state_json"])) if "state_json" in z else {}
            meas = {}
            for c in meta.get("comps", []):
                kw = {f: z[f"trk_{c}_m_{f}"] for f in MEAS_FIELDS if f"trk_{c}_m_{f}" in z}
                if "mean" not in kw:
                    continue
                meas[c] = Measurements(channels=list(meta.get(f"chan_{c}", [])),
                                       roi_mode=meta.get(f"mode_{c}", c), **kw)
    except (OSError, ValueError, KeyError) as e:
        if isinstance(e, ValueError) and "tracking" in str(e):
            raise
        raise ValueError(f"{p.name} could not be read as a PeterPiper ROI / session file.") from None
    if not isinstance(state, dict) or not state.get("v2"):
        raise ValueError(f"{p.name} was saved by a PD4nav older than 2.0 - it does not say "
                         f"which cells were included. Load it in the main window and save it "
                         f"again.")
    cells = state.get("cells") or []
    if isinstance(cells, str):
        cells = json.loads(cells)
    excl = state.get("excl") or {}
    included = {}
    for c, M in meas.items():
        live = [k for k, cell in enumerate(cells) if isinstance(cell, dict) and c in cell
                and k < M.n_cells]
        out = {int(k) for k in excl.get(c, [])}
        included[c] = [k for k in live if k not in out]
    exp = state.get("exp") if isinstance(state.get("exp"), dict) else {}
    T = max((M.n_timepoints for M in meas.values()), default=0)
    try:
        base = int(state.get("baseline") or 1)
    except (TypeError, ValueError):
        base = 1
    nd2 = str(state.get("nd2") or Path(str(state.get("nd2_path") or "")).name or p.stem)
    try:
        um = float(exp.get("um_per_px") or 0.0)
    except (TypeError, ValueError):
        um = 0.0
    return Run(path=str(p), label=Path(nd2).stem or p.stem, nd2=nd2,
               baseline=max(1, min(base, max(1, T))),
               seconds_per_frame=float(exp.get("seconds_per_frame") or 0.0),
               n_timepoints=T, channels=list(state.get("channels") or []), meas=meas,
               included=included, saved=str(state.get("saved") or ""), um_per_px=um)


# --------------------------------------------------------------- quantities
def _panels_named(M: Measurements, baseline: int) -> List[Tuple[str, np.ndarray, str]]:
    """(name by channel NAMES, T x N data, y label) - plots._panels (the export's
    own arithmetic), named 'R/R0 GFP/Cy5', 'F/F0 GFP', 'Ratio GFP/Cy5', 'Intensity GFP'."""
    from .plots import _panels
    from .measure import min_snr
    s = Settings(baseline_timepoint=int(baseline), write_ratio_sheets=True,
                 ratio_min_snr=min_snr())
    panels = _panels(M, s)
    ch = list(M.channels)
    names = [f"Intensity {c}" for c in ch] + [f"F/F0 {c}" for c in ch]
    for a, b in M.channel_pairs():
        names += [f"Ratio {ch[a]}/{ch[b]}", f"R/R0 {ch[a]}/{ch[b]}"]
    if len(names) != len(panels):
        raise RuntimeError("quantity list out of step with plots._panels")
    return [(nm, p[1], p[2]) for nm, p in zip(names, panels)]


def quantity_names(M: Measurements) -> List[str]:
    """The export's quantities of one compartment (V2.4 names, unchanged) and,
    since V2.8, every further measure (MEASURE_KINDS) except the compartment
    ratios, which need two compartments (quantity_names_run)."""
    ch = list(M.channels)
    out = [f"Intensity {c}" for c in ch] + [f"F/F0 {c}" for c in ch]
    for a, b in M.channel_pairs():
        out += [f"Ratio {ch[a]}/{ch[b]}", f"R/R0 {ch[a]}/{ch[b]}"]
    out += [f"{k} {c}" for k in ("ΔF/F0", "Raw intensity", "Background", "Sum intensity")
            for c in ch]
    out += [f"ΔR/R0 {ch[a]}/{ch[b]}" for a, b in M.channel_pairs()]
    out.append("Area")
    return out


def quantity_names_run(run: "Run", comp: str) -> List[str]:
    """quantity_names of the compartment plus its compartment ratios against
    every other compartment of the run (same channel names)."""
    out = quantity_names(run.meas[comp])
    for other in run.comps():
        if other != comp:
            for c in run.meas[comp].channels:
                if c in run.meas[other].channels:
                    out += [f"Comp. ratio {c} ÷ {other}", f"Comp. ratio/R0 {c} ÷ {other}"]
    return out


# ---------------------------------------------------------- V2.8 measures
# Every measure is one number per cell and timepoint (T x N), from the run's own
# saved measurements - the same arithmetic as the export:
#   Intensity       ROI mean - background mean (same channel, same timepoint)
#   Raw intensity   ROI mean (no background subtracted)
#   Background      the background region's mean (one value per timepoint, the
#                   same for every cell - a dish-level measure)
#   F/F0, R/R0      Intensity / Ratio divided by its value at the baseline timepoint
#   dF/F0, dR/R0    F/F0 - 1, R/R0 - 1
#   Ratio           Intensity A / Intensity B (not normalised)
#   Sum intensity   (ROI mean - background) x ROI area in px: the total signal
#   Area            ROI area in um2 (px when the pixel size is not known)
#   Comp. ratio     Intensity of the channel in this compartment / in another
#                   (e.g. nucleus / cytoplasm), per cell; /R0: divided by its
#                   value at the baseline timepoint
MEASURE_KINDS = ("R/R0", "F/F0", "ΔR/R0", "ΔF/F0", "Ratio", "Intensity", "Raw intensity",
                 "Sum intensity", "Background", "Comp. ratio", "Comp. ratio/R0", "Area")


def split_name(q: str) -> Tuple[str, str, str, str]:
    """(kind, channel A, channel B or '', other compartment or '')."""
    q = str(q)
    if q == "Area":
        return "Area", "", "", ""
    for k in sorted(MEASURE_KINDS, key=len, reverse=True):
        if q.startswith(k + " "):
            rest = q[len(k) + 1:]
            if k.startswith("Comp. ratio") and " ÷ " in rest:
                a, other = rest.split(" ÷ ", 1)
                return k, a, "", other
            if k in ("R/R0", "Ratio", "ΔR/R0") and "/" in rest:
                a, b = rest.split("/", 1)
                return k, a, b, ""
            return k, rest, "", ""
    return q, "", "", ""


def measure_data(run: "Run", comp: str, quantity: str, b1: int) -> Tuple[np.ndarray, List[int]]:
    """(T x N data of every cell column, the columns this measure has: the
    cells included in comp - and, for a compartment ratio, also in the other
    compartment). b1: the 1-based baseline timepoint. KeyError if the run does
    not have it. 'Background' is a dish measure: T x 1, columns [0]."""
    M = run.meas[comp]
    k, a, b, other = split_name(quantity)
    ch = list(M.channels)
    cells = list(run.included.get(comp, []))
    b0 = int(np.clip(b1 - 1, 0, M.n_timepoints - 1))
    if k in ("Intensity", "F/F0", "Ratio", "R/R0"):
        for nm, data, _yl in _panels_named(M, b1):
            if nm == quantity:
                return data, cells
        raise KeyError(quantity)
    with np.errstate(divide="ignore", invalid="ignore"):
        if k == "Area":
            um = float(run.um_per_px or 0.0)
            return np.asarray(M.area_px, float) * (um * um if um > 0 else 1.0), cells
        if a not in ch:
            raise KeyError(quantity)
        ia = ch.index(a)
        bs = M.bg_subtracted()
        if k == "Raw intensity":
            return np.asarray(M.mean[:, ia, :], float), cells
        if k == "Background":
            return np.asarray(M.background[:, ia], float)[:, None], [0]
        if k == "ΔF/F0":
            return M.ff0(ia, b0) - 1.0, cells
        if k == "Sum intensity":
            return bs[:, ia, :] * np.asarray(M.area_px, float), cells
        if k == "ΔR/R0":
            if b not in ch:
                raise KeyError(quantity)
            return M.rr0(ia, ch.index(b), b0) - 1.0, cells
        if k.startswith("Comp. ratio"):
            if other not in run.meas or a not in run.meas[other].channels:
                raise KeyError(quantity)
            O = run.meas[other]
            num = bs[:, ia, :]
            den = O.bg_subtracted()[:, list(O.channels).index(a), :]
            n = min(num.shape[1], den.shape[1])
            r = np.full(num.shape, np.nan)
            r[:, :n] = num[:, :n] / den[:, :n]
            r = np.where(np.isfinite(r), r, np.nan)
            both = [c for c in cells if c in set(run.included.get(other, [])) and c < n]
            return (M.fold_change(r, b0) if k == "Comp. ratio/R0" else r), both
    raise KeyError(quantity)


def measure_unit(run: Optional["Run"], quantity: str) -> str:
    """The axis unit words for a measure ('' when it has no unit)."""
    k = split_name(quantity)[0]
    if k == "Area":
        return "µm²" if run is not None and run.um_per_px > 0 else "px"
    if k in ("Intensity", "Raw intensity", "Background"):
        return "counts"
    if k == "Sum intensity":
        return "counts × px"
    return ""


def per_cell(quantity: str) -> bool:
    """False for dish-level measures (one value per timepoint for the dish)."""
    return split_name(quantity)[0] != "Background"


def _rank(name: str) -> int:
    k = split_name(name)[0]
    return MEASURE_KINDS.index(k) if k in MEASURE_KINDS else len(MEASURE_KINDS)


def common_comps(runs: Sequence[Run]) -> List[str]:
    return [c for c in COMPS if runs and all(c in r.comps() for r in runs)]


def common_quantities(runs: Sequence[Run], comp: str) -> List[str]:
    """Quantities every run has for this compartment (channels matched by
    name), in MEASURE_KINDS order (R/R0 first)."""
    sets = [quantity_names_run(r, comp) for r in runs if comp in r.meas]
    if not sets or len(sets) != len(runs):
        return []
    keep = [q for q in sets[0] if all(q in s for s in sets[1:])]
    return sorted(keep, key=lambda q: (_rank(q), sets[0].index(q)))


def time_units(runs: Sequence[Run]) -> Tuple[bool, str]:
    """(minutes?, plain warning or ''). Minutes only when every run knows its
    frame interval; a warning when the intervals differ."""
    sp = [r.seconds_per_frame for r in runs]
    if not runs:
        return True, ""
    if any(s <= 0 for s in sp):
        unknown = [r.label for r in runs if r.seconds_per_frame <= 0]
        return False, ("The frame interval of " + ", ".join(unknown) + " is not known, so the "
                       "time axis is in timepoints from each run's baseline.")
    if max(sp) - min(sp) > 1e-3 * max(sp):
        return True, ("The runs were imaged at different frame intervals (" +
                      ", ".join(f"{r.label}: {r.seconds_per_frame:g} s" for r in runs) +
                      "). Each line uses its own interval, so the time points do not line up.")
    return True, ""


# --------------------------------------------------- the same .nd2 twice (V2.5)
SAME_REASONS = {"fingerprint": "same file contents (fingerprint)",
                "path": "same .nd2 path",
                "name_size": "same file name and size"}


def same_nd2(items: Sequence[dict]) -> Dict[str, List[Tuple[str, str]]]:
    """
    Which runs are analyses of the same .nd2 movie (= the same dish).

    items: [{key, quick, size, nd2_path, nd2_name}] - quick / size: the .nd2's
    content fingerprint (history.nd2_fingerprint; '' / 0 = not known), nd2_path:
    its normalised full path ('' = not known), nd2_name: its file name lower case
    ('' = not known). Two runs come from the same .nd2 when
      1. their fingerprints are equal (same contents, even renamed / moved), or
      2. (no fingerprint contradicts it) the same .nd2 path, or
      3. (no fingerprint contradicts it) the same file name and the same size.
    Two runs whose fingerprints are both known and differ are never the same.
    Returns {key: [(other key, reason)]} for every run that has a twin
    (reason: a SAME_REASONS key); keys without a twin are left out.
    """
    out: Dict[str, Dict[str, str]] = {}
    rank = {"fingerprint": 0, "path": 1, "name_size": 2}
    buckets: Dict[Tuple[str, str], List[dict]] = {}
    for it in items:
        q, size = str(it.get("quick") or ""), int(it.get("size") or 0)
        if q:
            buckets.setdefault(("fingerprint", q + f":{size}"), []).append(it)
        if it.get("nd2_path"):
            buckets.setdefault(("path", str(it["nd2_path"])), []).append(it)
        if it.get("nd2_name") and size > 0:
            buckets.setdefault(("name_size", f"{str(it['nd2_name']).lower()}:{size}"),
                               []).append(it)
    for (why, _v), group in buckets.items():
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                ka, kb = str(a["key"]), str(b["key"])
                if ka == kb:
                    continue
                qa, qb = str(a.get("quick") or ""), str(b.get("quick") or "")
                if why != "fingerprint" and qa and qb and qa != qb:
                    continue                    # two different movies with one name / path
                for x, y in ((ka, kb), (kb, ka)):
                    old = out.setdefault(x, {}).get(y)
                    if old is None or rank[why] < rank[old]:
                        out[x][y] = why
    return {k: sorted(v.items()) for k, v in out.items()}


def series(run: Run, comp: str, quantity: str, baseline: Optional[int] = None,
           minutes: bool = True) -> Series:
    """One run's included cells for this quantity, with time from its baseline
    (baseline: 1-based; None = the run's saved baseline)."""
    M = run.meas[comp]
    b1 = int(baseline or run.baseline)
    b1 = max(1, min(b1, M.n_timepoints))
    data, cells = measure_data(run, comp, quantity, b1)       # V2.8: every measure
    y = data[:, cells] if cells else np.zeros((M.n_timepoints, 0))
    steps = np.arange(M.n_timepoints, dtype=float) - (b1 - 1)
    if minutes and run.seconds_per_frame > 0:
        x, xl = steps * run.seconds_per_frame / 60.0, "Time from baseline (min)"
    else:
        x, xl = steps, "Timepoints from baseline"
    return Series(label=run.label, x=x, y=np.asarray(y, float), x_label=xl, cells=cells,
                  run=run)


# ---------------------------------------------------------- groups (V2.5)
@dataclass
class GroupLine:
    """One group line. kind 'dishes': y = T x D dish means (each dish one
    replicate - the graph's mean +/- error is across dishes); kind 'pooled':
    y = T x all included cells of all dishes. x = the common times."""
    label: str                     # group name
    kind: str                      # "dishes" | "pooled"
    x: np.ndarray
    y: np.ndarray
    x_label: str
    dishes: List[Series] = field(repr=False)
    rows: List[np.ndarray] = field(repr=False)       # per dish: its rows at x
    dish_mean: np.ndarray = field(repr=False)        # T x D
    dish_n: np.ndarray = field(repr=False)           # T x D cells with a value
    dropped: List[str] = field(default_factory=list)  # dishes left out (no cells)
    note: str = ""                                   # alignment note ('' = all times)

    @property
    def n(self) -> int:
        return int(self.y.shape[1])

    @property
    def n_dishes(self) -> int:
        return len(self.dishes)

    @property
    def n_cells(self) -> int:
        return int(sum(s.n for s in self.dishes))

    @property
    def cells(self) -> List[int]:
        return list(range(self.y.shape[1]))

    @property
    def run(self):
        return self.dishes[0].run if self.dishes else None


def align(lines: Sequence[Series]) -> Tuple[np.ndarray, List[np.ndarray], str]:
    """(common x, per line: its row index at each common x, note). Times are
    each run's own time from its baseline (Series.x). A time is common when
    every line has a time within 0.1 % of the shortest frame interval of it
    (minutes) - or exactly the same timepoint step (timepoints). The note says
    what was left out ('' = nothing)."""
    if not lines:
        return np.zeros(0), [], ""
    minutes = lines[0].x_label.endswith("(min)")
    if minutes:
        ivs = [s.run.seconds_per_frame / 60.0 for s in lines if s.run and
               s.run.seconds_per_frame > 0]
        tol = 1e-3 * (min(ivs) if ivs else 1.0)
    else:
        tol = 1e-9
    base = np.asarray(lines[0].x, float)
    keep_x, rows = [], [[] for _ in lines]
    for xv in base:
        if not np.isfinite(xv):
            continue
        idx = []
        for s in lines:
            d = np.abs(np.asarray(s.x, float) - xv)
            j = int(np.nanargmin(d)) if np.isfinite(d).any() else -1
            if j < 0 or d[j] > tol:
                break
            idx.append(j)
        else:
            keep_x.append(xv)
            for k, j in enumerate(idx):
                rows[k].append(j)
    x = np.asarray(keep_x, float)
    rows_a = [np.asarray(r, int) for r in rows]
    lost = [(s.label, len(s.x) - len(x)) for s in lines if len(s.x) != len(x)]
    note = ""
    if lost:
        ivs = sorted({round(s.run.seconds_per_frame, 6) for s in lines if s.run})
        why = ("the dishes were imaged at different frame intervals (" +
               ", ".join(f"{v:g} s" for v in ivs) + ")") if minutes and len(ivs) > 1 else \
            "the dishes cover different times"
        note = (f"Only the {len(x)} frame times that every dish has were averaged, because "
                f"{why}; left out: " + ", ".join(f"{lab} {k}" for lab, k in lost) +
                " timepoints. Nothing was interpolated.")
        if len(x) == 0:
            note = f"These dishes have no frame time in common ({why}) - nothing to average."
    return x, rows_a, note


def group_line(name: str, lines: Sequence[Series], kind: str = "dishes") -> GroupLine:
    """Average the dishes (runs) of one group - see the module text."""
    use = [s for s in lines if s.n > 0]
    dropped = [s.label for s in lines if s.n == 0]
    x, rows, note = align(use)
    T, D = len(x), len(use)
    dm = np.full((T, D), np.nan)
    dn = np.zeros((T, D), int)
    for k, (s, r) in enumerate(zip(use, rows)):
        if T:
            sm = GS.describe(s.y[r])
            dm[:, k] = sm.mean
            dn[:, k] = sm.n
    if kind == "pooled":
        y = np.hstack([s.y[r] for s, r in zip(use, rows)]) if use and T else np.zeros((T, 0))
    else:
        y = dm
    xl = lines[0].x_label if lines else "Time"
    return GroupLine(label=name, kind=kind, x=x, y=np.asarray(y, float), x_label=xl,
                     dishes=list(use), rows=rows, dish_mean=dm, dish_n=dn, dropped=dropped,
                     note=note)


def legend_label(s) -> str:
    if isinstance(s, GroupLine):
        if s.kind == "pooled":
            return f"{s.label} pooled (n = {s.n_cells} cells, {s.n_dishes} dishes)"
        return f"{s.label} (n = {s.n_dishes} dishes, {s.n_cells} cells)"
    return f"{s.label} (n = {s.n})"


# ------------------------------------------------------------------ drawing
_MPL_SYM = {"circle": ("o", True), "square": ("s", True), "triangle": ("^", True),
            "triangle_down": ("v", True), "diamond": ("D", True), "none": (None, True),
            "open_circle": ("o", False), "open_square": ("s", False),
            "open_triangle": ("^", False), "open_triangle_down": ("v", False),
            "open_diamond": ("D", False)}


def draw(ax, lines: Sequence, colours: Sequence[str], style, y_label: str,
         title: str, right=None) -> None:
    """matplotlib: each line drawn by graphstyle.draw_matplotlib (the export's own
    drawing: mean +/- error of the line's replicate columns) in its colour, with
    the template's symbol per line (prismfile.series_symbols) and a key right of
    the plot. The title is plain (not bold), as in the Prism template."""
    from .prismfile import series_symbols
    st = GS.coerce(style)
    syms = series_symbols(st.to_dict(), len(lines))
    handles = []
    for i, (s, col) in enumerate(zip(lines, colours)):
        one = st.copy(mean_colour=col, show_cells=False, show_mean=True, legend=False,
                      baseline_line=i == 0)             # time 0 = every run's baseline
        before = len(ax.lines)
        GS.draw_matplotlib(ax, s.x, s.y, [f"c{k + 1}" for k in range(s.y.shape[1])], one,
                           lines[0].x_label, y_label, "")
        mine = [ln for ln in ax.lines[before:] if ln.get_label() and
                not ln.get_label().startswith("_")]
        if mine:
            mk, filled = _MPL_SYM.get(syms[i], ("o", True))
            mine[-1].set_marker(mk)
            mine[-1].set_markerfacecolor(col if filled else "none")
            mine[-1].set_markeredgecolor(col)
            mine[-1].set_markeredgewidth(0 if filled else max(0.5, st.mean_width))
            mine[-1].set_label(legend_label(s))
            handles.append(mine[-1])
    fs = float(st.font_pt)
    if right and right[0]:                     # V2.7: (lines, comp, quantity) on a right Y axis
        ax2 = ax.twinx()
        for s, col in zip(right[0], colours):
            m, _lo, _hi, _n = GS.stats(s.y, st.error)
            h, = ax2.plot(s.x, m, ls="--", color=col, lw=max(st.mean_width, 0.5),
                          label=f"{legend_label(s)} - {right[2]} (right)")
            handles.append(h)
        ax2.set_ylabel(f"{right[2]} - {COMP_LABELS.get(right[1], right[1])}", fontsize=fs,
                       family=GS.font_family())
        ax2.tick_params(labelsize=fs * GS.TICK_SCALE)
        ax2.spines["top"].set_visible(False)
    if title:
        ax.set_title(GS._wrap(title, ax.figure.get_figwidth(), fs), fontsize=fs,
                     family=GS.font_family())
    if handles:
        ax.legend(handles=handles, frameon=False, loc="center left",
                  bbox_to_anchor=(1.22 if right and right[0] else 1.02, 0.5),
                  prop={"family": GS.font_family(), "size": fs * GS.TICK_SCALE * 0.75})


IMAGE_FORMATS = ("png", "jpeg", "svg", "tiff", "pdf")
IMAGE_EXT = {"png": "png", "jpeg": "jpg", "svg": "svg", "tiff": "tif", "pdf": "pdf"}


def save_figure(path, lines, colours, style, y_label, title, fmt=None, dpi=300,
                right=None) -> str:
    """PNG / JPEG / TIFF at dpi, SVG / PDF with the text kept as text. The key
    sits right of the plot (as in the Prism template), so the figure is wider."""
    import matplotlib
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    st = GS.coerce(style)
    path = Path(path)
    fmt = (fmt or path.suffix.lstrip(".") or "png").lower()
    fmt = {"jpg": "jpeg", "tif": "tiff"}.get(fmt, fmt)
    if fmt not in IMAGE_FORMATS:
        raise ValueError(f"Graphs can be saved as {', '.join(IMAGE_FORMATS)}, not '{fmt}'.")
    fig = Figure(figsize=(st.width_in * 1.45, st.height_in), dpi=dpi)
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    draw(ax, lines, colours, st, y_label, title, right=right)
    fig.tight_layout()
    kw = {"pil_kwargs": {"quality": 95}} if fmt == "jpeg" else \
        ({"pil_kwargs": {"compression": "tiff_lzw"}} if fmt == "tiff" else {})
    with matplotlib.rc_context({"svg.fonttype": "none", "pdf.fonttype": 42}):
        with new_output_file(path) as (used, stream):
            fig.savefig(stream, format=fmt, dpi=dpi, **kw)
    return str(used)


# ------------------------------------------------------------------- tables
def _f(v) -> str:
    return "" if v is None or not np.isfinite(v) else f"{float(v):.6g}"


def table_rows(lines: Sequence, quantity: str, comp: str) -> List[list]:
    """Runs: one row per run per timepoint - mean, SEM, SD, 95% CI half-width, n.
    Groups: one row per group per common time - the line's group statistic
    (dish means: n = dishes; pooled: n = cells)."""
    if lines and isinstance(lines[0], GroupLine):
        rows = [["Group", "Statistic", "Compartment", "Quantity", "Common time #",
                 lines[0].x_label, "Mean", "SEM", "SD", "95% CI (half-width)",
                 "n (dishes with a value)" if lines[0].kind == "dishes" else
                 "n (cells with a value)", "Dishes", "Cells (included)"]]
        for g in lines:
            sm = GS.describe(g.y)
            what = ("mean of dish means (n = dishes)" if g.kind == "dishes" else
                    "pooled cells (n = cells)")
            for t in range(len(g.x)):
                rows.append([g.label, what, COMP_LABELS.get(comp, comp), quantity, t + 1,
                             _f(g.x[t]), _f(sm.mean[t]), _f(sm.sem[t]), _f(sm.sd[t]),
                             _f(sm.ci95[t]), int(sm.n[t]), g.n_dishes, g.n_cells])
        return rows
    rows = [["Run", "File", "Compartment", "Quantity", "Baseline timepoint", "Timepoint",
             lines[0].x_label if lines else "Time", "Mean", "SEM", "SD", "95% CI (half-width)",
             "n (cells with a value)", "Included cells"]]
    for s in lines:
        sm = GS.describe(s.y)
        for t in range(len(s.x)):
            rows.append([s.label, s.run.nd2, COMP_LABELS.get(comp, comp), quantity,
                         s.run.baseline if s.run else "", t + 1, f"{s.x[t]:.6g}"] +
                        ["" if not np.isfinite(v) else f"{v:.6g}"
                         for v in (sm.mean[t], sm.sem[t], sm.sd[t], sm.ci95[t])] +
                        [int(sm.n[t]), s.n])
    return rows


def dish_rows(groups: Sequence[GroupLine], quantity: str, comp: str) -> List[list]:
    """Per-dish table: one row per dish per common time - the dish mean, its SEM
    over its own cells and its n cells (the numbers the group mean is made of)."""
    rows = [["Group", "Dish (run)", ".nd2 file", "Run file", "Baseline timepoint",
             "Frame interval (s)", "Compartment", "Quantity", "Timepoint in the run",
             groups[0].x_label if groups else "Time", "Dish mean", "SEM over its cells",
             "SD over its cells", "n (cells with a value)", "Included cells"]]
    for g in groups:
        for s, r in zip(g.dishes, g.rows):
            sm = GS.describe(s.y[r])
            for t in range(len(g.x)):
                rows.append([g.label, s.label, s.run.nd2, Path(s.run.path).name, s.run.baseline,
                             _f(s.run.seconds_per_frame) or "unknown",
                             COMP_LABELS.get(comp, comp), quantity, int(r[t]) + 1, _f(g.x[t]),
                             _f(sm.mean[t]), _f(sm.sem[t]), _f(sm.sd[t]), int(sm.n[t]), s.n])
    return rows


def other_rows(groups: Sequence[GroupLine], quantity: str, comp: str) -> List[list]:
    """The group statistic NOT plotted (pooled cells when the dish means are
    plotted and the other way round)."""
    kind = "pooled" if groups and groups[0].kind == "dishes" else "dishes"
    return table_rows([group_line(g.label, g.dishes, kind) for g in groups], quantity, comp)


def _write_csv(path: Path, rows) -> str:
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    with new_output_file(path) as (used, stream):
        stream.write(buf.getvalue().encode("utf-8"))
    return str(used)


def _write_xlsx(path: Path, sheets: Sequence[Tuple[str, List[list]]]) -> str:
    """Numbers as numbers (the CSV text '1.234' -> 1.234; '' -> empty)."""
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook()
    wb.remove(wb.active)
    for title, rows in sheets:
        ws = wb.create_sheet(title[:31])
        for i, r in enumerate(rows):
            vals = []
            for v in r:
                if isinstance(v, str) and i > 0 and title != "Methods":
                    if v == "":
                        v = None
                    else:
                        try:
                            v = float(v)
                        except ValueError:
                            pass
                vals.append(v)
            ws.append(vals)
        if len(rows) > 1 and title != "Methods":
            for c in ws[1]:
                c.font = Font(bold=True)
            ws.freeze_panes = "A2"
    buf = io.BytesIO()
    wb.save(buf)
    with new_output_file(path) as (used, stream):
        stream.write(buf.getvalue())
    return str(used)


def save(folder, name: str, formats: Sequence[str], lines: Sequence,
         colours: Sequence[str], style, comp: str, quantity: str, title: str,
         notes: str = "", kinetics: Sequence[str] = (),
         kinetics_same_window: bool = True, right=None) -> List[str]:
    """Write the comparison: .prism, .png / .jpg / .svg / .tif / .pdf, .csv and
    .xlsx (formats: 'prism', 'png', 'jpeg', 'svg', 'tiff', 'pdf', 'csv', 'xlsx')
    into folder as name.<ext>. Never overwrites (adds _2, _3 ...).
    Groups: name.csv = the plotted group statistic, plus name_per_dish.csv and
    name_pooled.csv (or name_dish_means.csv when the pooled cells are plotted);
    the .xlsx holds them all and the methods text.
    kinetics (V2.6; peterpiper.kinetics parameter keys, e.g. 't_half', 'slope'): for
    each, name_<parameter>.<image / prism> (each dish a dot, mean +/- error across
    the dishes); the kinetics tables (name_kinetics_per_dish.csv,
    name_kinetics_groups.csv and two .xlsx sheets) whenever one is asked for;
    kinetics_same_window: every dish over the same window (kinetics.items_for).
    right (V2.7): (lines, compartment, quantity) of a second measure on a right Y
    axis - drawn dashed in the pictures, its 'mean, SEM, n' tables (and a graph of
    its own) in the .prism, a 'Right axis data' table.
    Returns the paths."""
    from .export import clean_prefix
    folder = Path(folder)
    make_dirs(folder)
    name = clean_prefix(name, 150) or "comparison"
    st = GS.coerce(style)
    out: List[str] = []
    groups = [g for g in lines if isinstance(g, GroupLine)]
    xt, yt = GS.axis_titles(st, lines[0].x_label if lines else "", quantity)
    if "prism" in formats:
        from .prismfile import write_compare_prism
        extra, sen_titles = [], None
        if groups:
            what = "dish means, n = dishes" if groups[0].kind == "dishes" else \
                "pooled cells, n = cells"
            sen_titles = [f"{g.label} - {quantity} group mean, SEM, n ({what})" for g in groups]
            for g in groups:
                extra.append((f"{g.label} - {quantity} each dish mean", g.x, "each", g.dish_mean,
                              [s.label for s in g.dishes], quantity))
                kind = "pooled" if g.kind == "dishes" else "dishes"
                sm = GS.describe(group_line(g.label, g.dishes, kind).y)
                extra.append((f"{g.label} - {quantity} "
                              f"{'pooled cells' if kind == 'pooled' else 'mean of dish means'}"
                              f" mean, SEM, n", g.x, "sen", (sm.mean, sm.sem, sm.n.astype(float)),
                              None, quantity))
        if right and right[0]:
            for s in right[0]:
                sm = GS.describe(s.y)
                extra.append((f"{s.label} - {right[2]} ({COMP_LABELS.get(right[1], right[1])}, "
                              f"right axis) mean, SEM, n", s.x, "sen",
                              (sm.mean, sm.sem, sm.n.astype(float)), None, right[2]))
        out.append(write_compare_prism(
            str(folder / f"{name}.prism"), [(legend_label(s), s.x, s.y) for s in lines],
            xt, quantity, yt, title or " ", list(colours), style=st.to_dict(), notes=notes,
            sheet_title=(f"Average - {quantity}" if groups else None), sen_titles=sen_titles,
            extra=extra))
    for f in IMAGE_FORMATS:
        if f in formats or (f == "jpeg" and "jpg" in formats) or (f == "tiff" and "tif" in formats):
            out.append(save_figure(folder / f"{name}.{IMAGE_EXT[f]}", lines, colours, st,
                                   quantity, title, fmt=f, right=right))
    main = table_rows(lines, quantity, comp)
    sheets = [("Graph data", main)]
    if right and right[0]:
        sheets.append(("Right axis data", table_rows(right[0], right[2], right[1])))
    if groups:
        kind = "pooled" if groups[0].kind == "dishes" else "dishes"
        sheets += [("Per dish", dish_rows(groups, quantity, comp)),
                   ("Pooled cells" if kind == "pooled" else "Mean of dish means",
                    other_rows(groups, quantity, comp))]
    kin_rows = None
    if kinetics and lines:
        from . import kinetics as K
        items = K.items_for(lines, kinetics_same_window)
        xl = lines[0].x_label
        knotes = (notes + "\n" + K.methods(kinetics_same_window) + " " +
                  K.window_text(items, xl, kinetics_same_window))
        for key in kinetics:
            tag = K.FILE_TAGS[key]
            kt = f"{K.PARAM_NAMES[key]} - {quantity} - {COMP_LABELS.get(comp, comp)}"
            if "prism" in formats:
                out.append(K.write_prism(folder / f"{name}_{tag}.prism", items, key, colours, st,
                                         xl, quantity, kt, knotes))
            for f in IMAGE_FORMATS:
                if f in formats or (f == "jpeg" and "jpg" in formats) or \
                        (f == "tiff" and "tif" in formats):
                    out.append(K.save_figure(folder / f"{name}_{tag}.{IMAGE_EXT[f]}", items, key,
                                             colours, st, xl, quantity, kt, fmt=f))
        kin_rows = (K.dish_table(items, xl, quantity, comp),
                    K.group_table(items, xl, quantity, comp))
        sheets += [("Kinetics per dish", kin_rows[0]), ("Kinetics groups", kin_rows[1])]
        notes = knotes
    sheets.append(("Methods", [["Methods"]] + [[t] for t in notes.split("\n") if t.strip()]))
    if "csv" in formats:
        out.append(_write_csv(folder / f"{name}.csv", main))
        if right and right[0]:
            out.append(_write_csv(folder / f"{name}_right_axis.csv",
                                  table_rows(right[0], right[2], right[1])))
        if groups:
            sh = dict(sheets)
            out.append(_write_csv(folder / f"{name}_per_dish.csv", sh["Per dish"]))
            out.append(_write_csv(folder / (f"{name}_pooled.csv" if kind == "pooled"
                                            else f"{name}_dish_means.csv"),
                                  sh["Pooled cells" if kind == "pooled" else
                                     "Mean of dish means"]))
        if kin_rows:
            out.append(_write_csv(folder / f"{name}_kinetics_per_dish.csv", kin_rows[0]))
            out.append(_write_csv(folder / f"{name}_kinetics_groups.csv", kin_rows[1]))
    if "xlsx" in formats:
        out.append(_write_xlsx(folder / f"{name}.xlsx", sheets))
    return out


def notes_text(lines: Sequence, comp: str, quantity: str, style) -> str:
    st = GS.coerce(style)
    e = GS.error_label(st.error)
    if lines and isinstance(lines[0], GroupLine):
        kind = lines[0].kind
        parts = [f"PeterPiper replicate average of {sum(g.n_dishes for g in lines)} dishes in "
                 f"{len(lines)} group(s): {quantity}, {COMP_WORDS.get(comp, comp)}."]
        if kind == "dishes":
            parts.append("For each dish (one saved run) the mean of its included cells was "
                         "taken at every timepoint; each line is the mean" +
                         (f" +/- {e}" if e else "") + " of those dish means (n = number of "
                         "dishes; SD with n - 1, SEM = SD / sqrt(n), 95% CI = t(0.975, n - 1) x "
                         "SEM). Each dish counts once, whatever its number of cells. The "
                         "pooled-cells version (all cells of the group as one sample) is in "
                         "the tables for reference.")
        else:
            parts.append("Each line pools every included cell of every dish of the group "
                         "(mean" + (f" +/- {e}" if e else "") + ", n = cells; SD with n - 1, "
                         "SEM = SD / sqrt(n)). Cells of one dish are not independent "
                         "replicates: the mean of dish means (n = dishes, in the tables) is "
                         "the replicate statistic.")
        parts.append("X = time from each dish's own baseline; only frame times that every "
                     "dish of a group has were used (nothing interpolated).")
        for g in lines:
            parts.append(f"Group {g.label}: {g.n_dishes} dishes, {g.n_cells} included cells, "
                         f"{len(g.x)} common times.")
            if g.note:
                parts.append(g.note)
            if g.dropped:
                parts.append("Left out (no included cells): " + ", ".join(g.dropped) + ".")
            for s in g.dishes:
                parts.append(f"  {s.label}: {s.run.nd2}, {s.n} included cells, baseline "
                             f"timepoint {s.run.baseline}, {s.run.interval_text()}, file "
                             f"{Path(s.run.path).name}.")
        return "\n".join(parts)
    parts = [f"PeterPiper comparison of {len(lines)} runs: {quantity}, "
             f"{COMP_WORDS.get(comp, comp)}. Each line is the mean"
             + (f" +/- {e}" if e else "") + " of that run's included cells "
             "(SEM = SD / sqrt(n), SD with n - 1). X = time from each run's own baseline."]
    for s in lines:
        parts.append(f"{s.label}: {s.run.nd2}, {s.n} included cells, baseline timepoint "
                     f"{s.run.baseline}, {s.run.interval_text()}, file {Path(s.run.path).name}.")
    return " ".join(parts)
