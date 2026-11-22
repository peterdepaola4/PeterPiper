"""
PeterPiper 4.0 graph builder - the engine (no Qt): "Y vs X (vs Z)" of any per-cell
quantity, per run and across runs.

RunData
    One tracked movie, light: its Measurements per compartment (the export's own
    numbers), which cells are drawn (live) and included per compartment, the
    baseline timepoint, the frame interval, the pixel size, the condition (cell
    line, celllines.py). Made from a live tracking result (from_track) or from a
    saved run that Compare loads (from_run / load_rundata).

Quantity  = compartment (or two: 'nucleus' / 'cytoplasm' = their ratio, per cell)
          + channel (or a channel ratio 'A/B')
          + measure:
              mean     mean intensity, background-subtracted (= the export's
                       BgSub_ / 'Intensity' numbers)
              total    summed total intensity = (ROI mean - background) x ROI
                       area in px (= Compare's 'Sum intensity'; the Excel Sum_
                       sheet is the RAW pixel sum, before background)
              raw      raw ROI mean (no background subtracted)
              ff0      F/F0 (the export's dFF_; dim-at-baseline cells blank)
              ratio    A/B of background-subtracted means (the export's R_)
              rr0      R/R0 (the export's dRR_)
              xbg      'x background' = raw ROI mean / background mean
              area     ROI area in um2 (px when the pixel size is not known)
          + time:
              trace    the full trace (one value per timepoint)
              at       at one time (t1)
              end      at the last timepoint
              mean / max / min / auc / slope   over t1..t2 (whole movie when not
                       given; slope = least-squares line, plots.drift_slopes - the
                       kinetics / drift add-on)
          Times: unit 'tp' = timepoints FROM THE BASELINE (T=0 is the baseline,
          as on the graphs' time axis; T=-3 is three frames before it), 'min' =
          minutes from the baseline, 'frame' = the movie's own 1-based frame
          number (as the app's 'T5' labels and the drift window).

GraphSpec = Y vs X (None = Time) with an optional Z (colour, or bins: equal
count / equal width / your own cut-offs), X bins (mean Y per X bin), filters
(removable conditions), included cells only (default), error (SD / SEM / 95% CI),
per-cell points, log axes, correlation, how runs are split (pool / run /
condition / group), and the drift-correction add-on (off by default).

Shape rules (compute()):
    X = Time                 'traces'   each cell's trace; mean +/- error per group
                                        (group = run / condition / Z bin ...)
    scalar vs scalar         'scatter'  one point per cell; Z colours or bins;
                                        X bins -> mean Y per bin; Pearson / Spearman
    trace vs trace           'pairs'    every (cell, timepoint) point coloured by
                                        time (or by Z), or per-cell trajectories;
                                        group means as a trajectory
    trace next to a scalar   the trace takes the scalar's time ('mCherry at T=30
                             vs F/F0 GFP' -> both at T=30); with no time given it
                             is taken at the last timepoint (the notes say so)
    Z a trace (colour/bins of whole cells) -> taken at Y's / X's time, else at the
                             baseline (T=0)

Every number comes from compare / plots (the export's own arithmetic), so a value
here equals the export's value for the same cell.
"""
from __future__ import annotations

import csv
import io
import json
import math
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from .measure import Measurements, min_snr

COMPS = ("nucleus", "cytoplasm", "cell", "mito")
COMP_ADJ = {"nucleus": "nuclear", "cytoplasm": "cytoplasmic", "cell": "whole cell",
            "mito": "mitochondrial"}
COMP_NOUN = {"nucleus": "Nucleus", "cytoplasm": "Cytoplasm", "cell": "Whole cell",
             "mito": "Mitochondria"}
# measure key: (label for menus, channels it needs: 0 / 1 / 2)
MEASURES = {"mean": ("Mean intensity", 1), "total": ("Summed total intensity", 1),
            "ff0": ("F/F0", 1), "rr0": ("R/R0", 2), "ratio": ("Ratio", 2),
            "xbg": ("x background", 1), "raw": ("Raw mean (no bg)", 1), "area": ("Area", 0)}
MEASURE_TIPS = {
    "mean": "The ROI's mean brightness minus the background (camera counts) - the export's "
            "'Intensity' / BgSub numbers. Shows how much of the protein is there per pixel.",
    "total": "Summed total intensity: (ROI mean - background) x the ROI's area in pixels - the "
             "whole amount of signal in the ROI (e.g. DNA content with DAPI).",
    "ff0": "F/F0: the background-subtracted intensity divided by its value at the baseline "
           "timepoint, per cell (1 = no change).",
    "rr0": "R/R0: the ratio of two channels divided by its value at the baseline timepoint, "
           "per cell (1 = no change). For ratiometric sensors.",
    "ratio": "Channel A / channel B (both background-subtracted), not normalised.",
    "xbg": "x background: the ROI's raw mean divided by the background's mean (2 = twice as "
           "bright as the background). Tells you how far above the background a cell is.",
    "raw": "The ROI's mean as recorded, background NOT subtracted (for checking).",
    "area": "The ROI's area in um2 (pixels when the pixel size is not known).",
}
TIMES = {"trace": "full trace", "at": "at a time", "end": "at the last timepoint",
         "mean": "mean over", "max": "max over", "min": "min over",
         "auc": "area under curve", "slope": "slope over"}
TIME_TIPS = {
    "trace": "Every timepoint (a trace). Against Time: the usual time course.",
    "at": "One number per cell at one time. T=0 is the baseline, T=5 five timepoints after it; "
          "'min' = minutes from the baseline; 'frame' = the movie's own frame number.",
    "end": "One number per cell: its value at the last timepoint.",
    "mean": "One number per cell: the mean over a window of time (the whole movie if no "
            "window is set).",
    "max": "One number per cell: its highest value (in the window).",
    "min": "One number per cell: its lowest value (in the window).",
    "auc": "One number per cell: the area under its curve (trapezoids, x in minutes when the "
           "frame interval is known, else in timepoints).",
    "slope": "One number per cell: the slope of a straight line fitted through the window "
             "(per minute, or per timepoint) - the kinetics / drift add-on.",
}
UNITS = ("tp", "min", "frame")
WINDOW_TIMES = ("mean", "max", "min", "auc", "slope")
ERRORS = ("SD", "SEM", "95% CI", "none")
SPLITS = ("pool", "run", "condition", "group")
DEFAULT_SLOPE = (2, 9)            # frames: Settings.drift_from / drift_to defaults
GROUP_PALETTE = ("#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#000000")
# viridis, cut before its palest yellow (dots must be seen on the white plot)
_RAMP = ((0.0, (68, 1, 84)), (0.15, (71, 44, 122)), (0.3, (59, 81, 139)),
         (0.45, (44, 113, 142)), (0.6, (33, 144, 141)), (0.75, (39, 173, 129)),
         (0.88, (92, 200, 99)), (1.0, (170, 220, 50)))


class QuantityError(ValueError):
    """A quantity this run cannot make (plain words)."""


# ===================================================================== quantities
@dataclass(frozen=True)
class Quantity:
    comp: str = "nucleus"
    chan: str = ""                 # 'GFP' or 'Cy5/GFP' (ratio / R/R0)
    measure: str = "mean"
    time: str = "trace"
    t1: Optional[float] = None
    t2: Optional[float] = None
    unit: str = "tp"               # 'tp' (from the baseline) | 'min' | 'frame'
    comp2: str = ""                # '' or a second compartment: comp / comp2 per cell

    @property
    def is_trace(self) -> bool:
        return self.time == "trace"

    def channels(self) -> List[str]:
        return [c for c in str(self.chan).split("/") if c] if self.chan else []

    def comps(self) -> List[str]:
        return [self.comp] + ([self.comp2] if self.comp2 else [])

    def base(self) -> "Quantity":
        """The same quantity as a full trace (the cache key)."""
        return replace(self, time="trace", t1=None, t2=None, unit="tp")

    def with_time_of(self, other: "Quantity") -> "Quantity":
        return replace(self, time=other.time, t1=other.t1, t2=other.t2, unit=other.unit)

    def what(self) -> str:
        """'R/R0 Cy5/GFP' / 'Summed total intensity DAPI' / 'Area'."""
        m = MEASURES.get(self.measure, (self.measure, 1))[0]
        if self.measure == "area":
            return "Area"
        if self.measure == "xbg":
            return f"{self.chan} x background"
        return f"{m} {self.chan}".strip()

    def short(self) -> str:
        """'summed DAPI', 'R/R0 Cy5/GFP', 'area' - legends."""
        if self.measure == "area":
            return "area"
        m = {"mean": "", "total": "summed ", "ff0": "F/F0 ", "rr0": "R/R0 ",
             "ratio": "ratio ", "xbg": "x bg ", "raw": "raw "}.get(self.measure, "")
        return (f"{m}{self.chan}" if self.measure != "xbg" else f"{self.chan} x bg").strip()

    def where(self) -> str:
        if self.comp2:
            return f"{COMP_NOUN.get(self.comp, self.comp)} / {COMP_ADJ.get(self.comp2, self.comp2)}"
        return COMP_NOUN.get(self.comp, self.comp)

    def label(self) -> str:
        """Axis title: 'R/R0 Cy5/GFP - Nucleus, at T=30'."""
        t = time_text(self)
        return f"{self.what()} - {self.where()}" + (f", {t}" if t else "")

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in ("comp", "chan", "measure", "time", "t1", "t2",
                                              "unit", "comp2")}

    @staticmethod
    def from_dict(d) -> Optional["Quantity"]:
        if not isinstance(d, dict) or not d.get("comp"):
            return None
        f = lambda v: None if v is None else float(v)          # noqa: E731
        return Quantity(comp=str(d["comp"]), chan=str(d.get("chan") or ""),
                        measure=str(d.get("measure") or "mean"),
                        time=str(d.get("time") or "trace"), t1=f(d.get("t1")),
                        t2=f(d.get("t2")), unit=str(d.get("unit") or "tp"),
                        comp2=str(d.get("comp2") or ""))


def _num(v: float) -> str:
    return f"{float(v):g}"


def t_text(v: float, unit: str) -> str:
    if unit == "min":
        return f"{_num(v)} min"
    if unit == "frame":
        return f"frame {_num(v)}"
    return f"T={_num(v)}"


def range_text(a: Optional[float], b: Optional[float], unit: str) -> str:
    if a is None and b is None:
        return ""
    if unit == "min":
        return f"{_num(a if a is not None else 0)}-{_num(b) if b is not None else 'end'} min"
    if unit == "frame":
        return f"frames {_num(a if a is not None else 1)}-{_num(b) if b is not None else 'end'}"
    return f"T={_num(a if a is not None else 0)}..{_num(b) if b is not None else 'end'}"


def time_text(q: Quantity) -> str:
    """'at T=30', 'at the end', 'max over T=0..30', 'slope over frames 2-9', '' (trace)."""
    if q.time == "trace":
        return ""
    if q.time == "end":
        return "at the end"
    if q.time == "at":
        if q.t1 is None or (q.unit == "tp" and q.t1 == 0):
            return "at baseline" if q.t1 is None or q.unit == "tp" else ""
        return "at " + t_text(q.t1, q.unit)
    word = {"mean": "mean", "max": "max", "min": "min", "auc": "AUC", "slope": "slope"}[q.time]
    r = range_text(q.t1, q.t2, q.unit)
    return f"{word} over {r}" if r else word


# ======================================================================== runs
@dataclass
class RunData:
    """One tracked movie (see the module text). Arrays are indexed by cell
    column k (PeterPiper's cell numbering: the same k in every compartment)."""
    name: str
    meas: Dict[str, Measurements]
    included: Dict[str, np.ndarray]
    live: Dict[str, np.ndarray]
    baseline: int = 1                       # 1-based
    seconds_per_frame: float = 0.0
    um_per_px: float = 0.0
    condition: str = ""
    group: str = ""
    key: str = ""
    path: str = ""
    nd2: str = ""
    _cache: dict = field(default_factory=dict, repr=False)

    # ---------------------------------------------------------------- shape
    @property
    def comps(self) -> List[str]:
        return [c for c in COMPS if c in self.meas] + [c for c in self.meas if c not in COMPS]

    @property
    def channels(self) -> List[str]:
        out: List[str] = []
        for c in self.comps:
            out += [ch for ch in self.meas[c].channels if ch not in out]
        return out

    @property
    def n_t(self) -> int:
        return max((M.n_timepoints for M in self.meas.values()), default=0)

    @property
    def n_cells(self) -> int:
        return max((M.n_cells for M in self.meas.values()), default=0)

    @property
    def b0(self) -> int:
        return int(np.clip(int(self.baseline) - 1, 0, max(0, self.n_t - 1)))

    @property
    def minutes(self) -> bool:
        return self.seconds_per_frame > 0

    @property
    def time(self) -> np.ndarray:
        """Time from the baseline: minutes when the frame interval is known, else timepoints."""
        steps = np.arange(self.n_t, dtype=float) - self.b0
        return steps * self.seconds_per_frame / 60.0 if self.minutes else steps

    @property
    def time_label(self) -> str:
        return "Time from baseline (min)" if self.minutes else "Timepoints from baseline"

    # the brief's light arrays (views of the export's Measurements)
    def mean(self, comp: str) -> np.ndarray:            # (T, C, N) raw ROI means
        return self.meas[comp].mean

    def total(self, comp: str) -> np.ndarray:           # (T, C, N) background-subtracted sums
        M = self.meas[comp]
        return M.bg_subtracted() * np.asarray(M.area_px, float)[:, None, :]

    def area(self, comp: str) -> np.ndarray:            # (T, N)
        return np.asarray(self.meas[comp].area_px, float)

    def background(self, comp: str) -> np.ndarray:      # (T, C)
        return self.meas[comp].background

    def mask(self, comp: str, included_only: bool = True) -> np.ndarray:
        N = self.n_cells
        src = self.included if included_only else self.live
        m = np.zeros(N, bool)
        v = np.asarray(src.get(comp, np.zeros(0, bool)), bool)
        m[:min(N, len(v))] = v[:N]
        return m

    # ---------------------------------------------------------------- times
    def index(self, v: Optional[float], unit: str) -> Optional[int]:
        """0-based timepoint for a time (see the module text); None when outside the movie."""
        if v is None:
            return None
        if unit == "frame":
            i = int(round(v)) - 1
        elif unit == "min" and self.minutes:
            i = self.b0 + int(round(v * 60.0 / self.seconds_per_frame))
        else:
            i = self.b0 + int(round(v))
        return i if 0 <= i < self.n_t else None

    def window(self, q: Quantity) -> Tuple[int, int]:
        T = self.n_t
        if q.time == "slope" and q.t1 is None and q.t2 is None:
            a, b = DEFAULT_SLOPE
            return max(0, min(a, T) - 1), max(0, min(b, T) - 1)

        def clip(v, default):
            if v is None:
                return default
            if q.unit == "frame":
                i = int(round(v)) - 1
            elif q.unit == "min" and self.minutes:
                i = self.b0 + int(round(v * 60.0 / self.seconds_per_frame))
            else:
                i = self.b0 + int(round(v))
            return int(np.clip(i, 0, T - 1))
        i1, i2 = clip(q.t1, 0), clip(q.t2, T - 1)
        return (i1, i2) if i1 <= i2 else (i2, i1)

    # ---------------------------------------------------------------- makers
    @staticmethod
    def from_track(track: dict, exp, excl: Optional[Dict[str, Iterable[int]]] = None,
                   baseline_t: int = 1, cells: Optional[Sequence[dict]] = None,
                   name: str = "", condition: Optional[str] = None, key: str = "",
                   group: str = "") -> "RunData":
        """From the analysis window's live result: track = manual.track_cells' dict
        (track['meas'] = {comp: Measurements}), exp = the Experiment (channels,
        seconds_per_frame, um_per_px, nd2_path), excl = {comp: excluded cell
        indices}, baseline_t = the 1-based baseline, cells = the window's cell
        list (cell k has comp c when c in cells[k]; None = every column)."""
        meas = {c: M for c, M in (track.get("meas") or {}).items() if M is not None}
        excl = excl or {}
        live, inc = {}, {}
        for c, M in meas.items():
            N = M.n_cells
            if cells is not None:
                lv = np.array([k < len(cells) and isinstance(cells[k], dict) and c in cells[k]
                               for k in range(N)], bool)
            else:
                lv = np.ones(N, bool)
            out = np.zeros(N, bool)
            for k in excl.get(c, ()) or ():
                if 0 <= int(k) < N:
                    out[int(k)] = True
            live[c], inc[c] = lv, lv & ~out
        nd2 = str(getattr(exp, "nd2_path", "") or "")
        nm = name or (Path(nd2).stem if nd2 else "this movie")
        return RunData(name=nm, meas=meas, included=inc, live=live,
                       baseline=int(baseline_t or 1),
                       seconds_per_frame=float(getattr(exp, "seconds_per_frame", 0) or 0),
                       um_per_px=float(getattr(exp, "um_per_px", 0) or 0),
                       condition=_condition(nm) if condition is None else str(condition),
                       group=group, key=key or nd2 or nm, path="", nd2=Path(nd2).name)

    @staticmethod
    def from_run(run, condition: Optional[str] = None, group: str = "",
                 label: str = "") -> "RunData":
        """From a compare.Run (a saved run file, as Compare loads it)."""
        live, inc = {}, {}
        for c, M in run.meas.items():
            N = M.n_cells
            a = np.asarray(M.area_px, float)
            lv = np.isfinite(a).any(axis=0) & (np.nan_to_num(a) > 0).any(axis=0) \
                if a.size else np.zeros(N, bool)
            m = np.zeros(N, bool)
            for k in run.included.get(c, []) or []:
                if 0 <= int(k) < N:
                    m[int(k)] = True
            live[c], inc[c] = lv | m, m
        nm = label or run.label
        return RunData(name=nm, meas=dict(run.meas), included=inc, live=live,
                       baseline=int(run.baseline), seconds_per_frame=float(run.seconds_per_frame),
                       um_per_px=float(getattr(run, "um_per_px", 0) or 0),
                       condition=_condition(run.nd2 or nm) if condition is None else condition,
                       group=group, key=str(run.path), path=str(run.path), nd2=run.nd2)


def load_rundata(path, condition: Optional[str] = None) -> RunData:
    """A saved run file (.npz) -> RunData (compare.load_run; ValueError in plain words).
    File I/O: call it in a background job."""
    from .compare import load_run
    return RunData.from_run(load_run(path), condition=condition)


def _condition(name: str) -> str:
    try:
        from .celllines import match
        cl = match(name)
        return cl.name if cl else ""
    except Exception:                                          # noqa: BLE001
        return ""


# ================================================================= arithmetic
def _pad(a: np.ndarray, T: int, N: int) -> np.ndarray:
    a = np.asarray(a, float)
    if a.shape == (T, N):
        return a
    out = np.full((T, N), np.nan)
    out[:min(T, a.shape[0]), :min(N, a.shape[1])] = a[:T, :N]
    return out


def _chan(M: Measurements, name: str, comp: str) -> int:
    low = [c.lower() for c in M.channels]
    if name.lower() in low:
        return low.index(name.lower())
    raise QuantityError(f"The {COMP_ADJ.get(comp, comp)} ROIs have no channel '{name}' "
                        f"(they have {', '.join(M.channels)}).")


def _one_comp(run: RunData, comp: str, chan: str, measure: str) -> np.ndarray:
    """(T, N) of one compartment, the export's arithmetic (see the module text)."""
    if comp not in run.meas:
        raise QuantityError(f"This run has no {COMP_ADJ.get(comp, comp)} ROIs "
                            f"(it has {', '.join(COMP_ADJ.get(c, c) for c in run.comps)}).")
    M = run.meas[comp]
    b0 = int(np.clip(run.b0, 0, M.n_timepoints - 1))
    k = min_snr()
    with np.errstate(divide="ignore", invalid="ignore"):
        if measure == "area":
            um = float(run.um_per_px or 0)
            return np.asarray(M.area_px, float) * (um * um if um > 0 else 1.0)
        chs = [c for c in chan.split("/") if c]
        if measure in ("ratio", "rr0"):
            if len(chs) != 2:
                raise QuantityError(f"{MEASURES[measure][0]} needs two channels, e.g. "
                                    f"{'/'.join(M.channels[:2])}.")
            a, b = _chan(M, chs[0], comp), _chan(M, chs[1], comp)
            if a == b:
                raise QuantityError("A ratio needs two different channels.")
            return M.ratio_checked(a, b, b0, k) if measure == "ratio" else M.rr0(a, b, b0, k)
        if len(chs) != 1:
            raise QuantityError(f"{MEASURES.get(measure, (measure,))[0]} is of one channel "
                                f"(not '{chan}').")
        c = _chan(M, chs[0], comp)
        if measure == "mean":
            return M.bg_subtracted()[:, c, :]
        if measure == "raw":
            return np.asarray(M.mean[:, c, :], float)
        if measure == "total":
            return M.bg_subtracted()[:, c, :] * np.asarray(M.area_px, float)
        if measure == "ff0":
            return M.ff0(c, b0, k)
        if measure == "xbg":
            r = np.asarray(M.mean[:, c, :], float) / np.asarray(M.background[:, c], float)[:, None]
            return np.where(np.isfinite(r), r, np.nan)
    raise QuantityError(f"Unknown measure '{measure}'.")


def trace(run: RunData, q: Quantity, drift: Optional[Tuple[int, int]] = None) -> np.ndarray:
    """(T, N) full trace of q's measure (cached per run). drift = (frame a, frame b):
    the drift-correction add-on - each cell's straight-line slope through frames
    a..b is taken out: y - slope x (t - t_baseline). Area is never corrected."""
    key = (q.base(), drift if q.measure != "area" else None)
    hit = run._cache.get(key)
    if hit is not None:
        return hit
    T, N = run.n_t, run.n_cells
    if q.comp2:
        if q.measure in ("ratio", "rr0"):
            raise QuantityError("A compartment ratio (e.g. nuclear/cytoplasmic) is of one "
                                "channel - not of a channel ratio.")
        base = "mean" if q.measure == "ff0" else q.measure
        with np.errstate(divide="ignore", invalid="ignore"):
            r = _pad(_one_comp(run, q.comp, q.chan, base), T, N) / \
                _pad(_one_comp(run, q.comp2, q.chan, base), T, N)
        r = np.where(np.isfinite(r), r, np.nan)
        out = Measurements.fold_change(r, run.b0) if q.measure == "ff0" else r
    else:
        out = _pad(_one_comp(run, q.comp, q.chan, q.measure), T, N)
    if drift and q.measure != "area":
        from .plots import drift_slopes
        a, b = int(drift[0]), int(drift[1])
        a, b = max(1, min(a, T)), max(1, min(b, T))
        x = run.time
        sl = drift_slopes(out, x, min(a, b), max(a, b))
        out = out - np.nan_to_num(sl)[None, :] * (x - x[run.b0])[:, None]
    out.setflags(write=False)
    run._cache[key] = out
    if len(run._cache) > 64:                       # keep it light
        run._cache.pop(next(iter(run._cache)))
    return out


def reduce(run: RunData, q: Quantity, tr: np.ndarray) -> np.ndarray:
    """(N,) one number per cell for q's time choice (NaN where there is none)."""
    T, N = tr.shape
    if q.time == "trace":
        raise ValueError("a trace has no single value")
    if q.time in ("at", "end"):
        i = T - 1 if q.time == "end" else (run.b0 if q.t1 is None else run.index(q.t1, q.unit))
        return np.full(N, np.nan) if i is None else np.array(tr[i], float)
    i1, i2 = run.window(q)
    w = np.asarray(tr[i1:i2 + 1], float)
    if q.time == "slope":
        from .plots import drift_slopes
        return drift_slopes(tr, run.time, i1 + 1, i2 + 1)
    with np.errstate(invalid="ignore", divide="ignore"):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            if q.time == "mean":
                return np.nanmean(w, axis=0) if len(w) else np.full(N, np.nan)
            if q.time == "max":
                return np.nanmax(w, axis=0) if len(w) else np.full(N, np.nan)
            if q.time == "min":
                return np.nanmin(w, axis=0) if len(w) else np.full(N, np.nan)
    if q.time == "auc":
        x = run.time[i1:i2 + 1]
        out = np.full(N, np.nan)
        for k in range(N):
            ok = np.isfinite(w[:, k])
            if ok.sum() >= 2:
                xs, ys = x[ok], w[ok, k]
                out[k] = float(np.sum((xs[1:] - xs[:-1]) * (ys[1:] + ys[:-1]) / 2.0))
        return out
    raise ValueError(f"unknown time '{q.time}'")


def values(run: RunData, q: Quantity, drift=None) -> np.ndarray:
    """(T, N) for a trace quantity, (N,) for a one-number-per-cell quantity."""
    tr = trace(run, q, drift)
    return tr if q.is_trace else reduce(run, q, tr)


# ===================================================================== spec
@dataclass(frozen=True)
class BinSpec:
    kind: str = "count"            # 'count' (equal number of cells) | 'width' | 'custom'
    n: int = 3
    cuts: Tuple[float, ...] = ()   # 'custom': the cut-offs between bins

    def to_dict(self) -> dict:
        return {"kind": self.kind, "n": int(self.n), "cuts": [float(c) for c in self.cuts]}

    @staticmethod
    def from_dict(d) -> "BinSpec":
        if not isinstance(d, dict):
            return BinSpec()
        return BinSpec(kind=str(d.get("kind") or "count"), n=max(1, int(d.get("n") or 3)),
                       cuts=tuple(float(c) for c in (d.get("cuts") or ())))


@dataclass(frozen=True)
class Filter:
    """A removable condition. kind 'value': q (one number per cell) op a [b];
    'condition' / 'run' / 'group': text must equal (case-insensitive) the run's."""
    kind: str = "value"
    q: Optional[Quantity] = None
    op: str = ">"                   # > >= < <= between outside
    a: float = 0.0
    b: float = 0.0
    text: str = ""
    on: bool = True

    def scalar_q(self) -> Optional[Quantity]:
        if self.q is None:
            return None
        return replace(self.q, time="at", t1=0.0, unit="tp") if self.q.is_trace else self.q

    def keep(self, v: np.ndarray) -> np.ndarray:
        with np.errstate(invalid="ignore"):
            if self.op == ">":
                return v > self.a
            if self.op == ">=":
                return v >= self.a
            if self.op == "<":
                return v < self.a
            if self.op == "<=":
                return v <= self.a
            lo, hi = min(self.a, self.b), max(self.a, self.b)
            if self.op == "between":
                return (v >= lo) & (v <= hi)
            if self.op == "outside":
                return (v < lo) | (v > hi)
        return np.isfinite(v)

    def to_dict(self) -> dict:
        return {"kind": self.kind, "q": self.q.to_dict() if self.q else None, "op": self.op,
                "a": float(self.a), "b": float(self.b), "text": self.text, "on": bool(self.on)}

    @staticmethod
    def from_dict(d) -> Optional["Filter"]:
        if not isinstance(d, dict):
            return None
        return Filter(kind=str(d.get("kind") or "value"), q=Quantity.from_dict(d.get("q")),
                      op=str(d.get("op") or ">"), a=float(d.get("a") or 0),
                      b=float(d.get("b") or 0), text=str(d.get("text") or ""),
                      on=bool(d.get("on", True)))


@dataclass(frozen=True)
class GraphSpec:
    y: Quantity
    x: Optional[Quantity] = None          # None = Time
    z: Optional[Quantity] = None
    z_mode: str = "colour"                # 'colour' | 'bins'
    z_bins: BinSpec = BinSpec()
    x_bins: Optional[BinSpec] = None      # X scalar: mean Y per X bin
    filters: Tuple[Filter, ...] = ()
    included_only: bool = True
    error: str = "SD"
    show_cells: bool = True               # per-cell traces / points
    show_mean: bool = True                # group means (traces, bins, trajectories)
    log_x: bool = False
    log_y: bool = False
    corr: str = "pearson"                 # 'pearson' | 'spearman' | 'none'
    pairs: str = "points"                 # trace vs trace: 'points' | 'trajectories'
    split: str = "pool"                   # 'pool' | 'run' | 'condition' | 'group'
    drift: Optional[Tuple[int, int]] = None   # add-on: drift correction, frames a..b

    def to_dict(self) -> dict:
        return {"y": self.y.to_dict(), "x": self.x.to_dict() if self.x else None,
                "z": self.z.to_dict() if self.z else None, "z_mode": self.z_mode,
                "z_bins": self.z_bins.to_dict(),
                "x_bins": self.x_bins.to_dict() if self.x_bins else None,
                "filters": [f.to_dict() for f in self.filters],
                "included_only": self.included_only, "error": self.error,
                "show_cells": self.show_cells, "show_mean": self.show_mean,
                "log_x": self.log_x, "log_y": self.log_y, "corr": self.corr,
                "pairs": self.pairs, "split": self.split,
                "drift": list(self.drift) if self.drift else None}

    @staticmethod
    def from_dict(d) -> Optional["GraphSpec"]:
        if not isinstance(d, dict):
            return None
        y = Quantity.from_dict(d.get("y"))
        if y is None:
            return None
        dr = d.get("drift")
        return GraphSpec(
            y=y, x=Quantity.from_dict(d.get("x")), z=Quantity.from_dict(d.get("z")),
            z_mode="bins" if d.get("z_mode") == "bins" else "colour",
            z_bins=BinSpec.from_dict(d.get("z_bins")),
            x_bins=BinSpec.from_dict(d["x_bins"]) if isinstance(d.get("x_bins"), dict) else None,
            filters=tuple(f for f in (Filter.from_dict(v) for v in d.get("filters") or ())
                          if f is not None),
            included_only=bool(d.get("included_only", True)),
            error=str(d.get("error") or "SD") if d.get("error") in ERRORS else "SD",
            show_cells=bool(d.get("show_cells", True)), show_mean=bool(d.get("show_mean", True)),
            log_x=bool(d.get("log_x")), log_y=bool(d.get("log_y")),
            corr=str(d.get("corr") or "pearson"), pairs=str(d.get("pairs") or "points"),
            split=str(d.get("split") or "pool") if d.get("split") in SPLITS else "pool",
            drift=(int(dr[0]), int(dr[1])) if isinstance(dr, (list, tuple)) and len(dr) == 2
            else None)


def effective(spec: GraphSpec) -> Tuple[Quantity, Optional[Quantity], Optional[Quantity], List[str]]:
    """(Y, X, Z, notes) after the shape rules (module text)."""
    y, x, z, notes = spec.y, spec.x, spec.z, []
    if x is None:
        if not y.is_trace:
            notes.append(f"Against Time, Y is its full trace ('{time_text(y)}' left out).")
            y = y.base()
    elif y.is_trace != x.is_trace:
        if y.is_trace:
            if spec.x.time != "trace":
                y = y.with_time_of(x)
                notes.append(f"Y has no time: it is taken {time_text(y)}, like X.")
        else:
            x = x.with_time_of(y)
            notes.append(f"X has no time: it is taken {time_text(x)}, like Y.")
    if z is not None and z.is_trace:
        pairs = x is not None and y.is_trace and x.is_trace
        if not pairs:
            ref = y if not y.is_trace else None
            z = z.with_time_of(ref) if ref is not None else replace(z, time="at", t1=0.0,
                                                                     unit="tp")
            notes.append(f"Z (colour / bins) needs one number per cell: taken {time_text(z)}.")
    return y, x, z, notes


def shape_of(spec: GraphSpec) -> str:
    y, x, _z, _n = effective(spec)
    if x is None:
        return "traces"
    if y.is_trace and x.is_trace:
        return "pairs"
    return "binned" if spec.x_bins is not None else "scatter"


# ===================================================================== bins
def bin_edges(v: np.ndarray, b: BinSpec) -> np.ndarray:
    """Edges (len n + 1) of the bins over the finite values v."""
    f = np.asarray(v, float)
    f = f[np.isfinite(f)]
    if b.kind == "custom" and b.cuts:
        return np.array([-np.inf] + sorted(float(c) for c in b.cuts) + [np.inf])
    n = max(1, int(b.n))
    if not len(f):
        return np.array([-np.inf, np.inf])
    lo, hi = float(f.min()), float(f.max())
    if b.kind == "width":
        e = np.linspace(lo, hi, n + 1)
    else:
        e = np.quantile(f, np.linspace(0, 1, n + 1))
    e[0], e[-1] = -np.inf, np.inf
    return e


def assign_bins(v: np.ndarray, edges: np.ndarray) -> np.ndarray:
    """Bin index per value (-1 = no value). Each bin is [lower, upper), the last [lower, inf]."""
    v = np.asarray(v, float)
    out = np.full(v.shape, -1, int)
    ok = np.isfinite(v)
    if ok.any():
        idx = np.searchsorted(edges[1:-1], v[ok], side="right")
        out[ok] = idx
    return out


def bin_labels(edges: np.ndarray, vals: np.ndarray, counts: Sequence[int]) -> List[str]:
    f = np.asarray(vals, float)
    f = f[np.isfinite(f)]
    lo_all = float(f.min()) if len(f) else 0.0
    hi_all = float(f.max()) if len(f) else 0.0
    out = []
    for i in range(len(edges) - 1):
        a = lo_all if not np.isfinite(edges[i]) else float(edges[i])
        b = hi_all if not np.isfinite(edges[i + 1]) else float(edges[i + 1])
        out.append(f"{_short(a)} - {_short(b)} (n = {counts[i]})")
    return out


def _short(v: float) -> str:
    if v == 0 or not np.isfinite(v):
        return f"{v:g}"
    a = abs(v)
    return f"{v:.3g}" if 1e-3 <= a < 1e5 else f"{v:.2e}"


# ================================================================ colours
def ramp(t: float) -> str:
    """Continuous colour (viridis without its pale end) for t in 0..1."""
    t = round(float(np.clip(t if np.isfinite(t) else 0.0, 0, 1)) * 128) / 128.0  # 129 shades
    return _ramp_q(t)


@lru_cache(maxsize=256)
def _ramp_q(t: float) -> str:
    for (a, ca), (b, cb) in zip(_RAMP, _RAMP[1:]):
        if t <= b:
            f = (t - a) / (b - a) if b > a else 0.0
            c = [int(round(x + (y - x) * f)) for x, y in zip(ca, cb)]
            return "#%02X%02X%02X" % tuple(c)
    return "#%02X%02X%02X" % _RAMP[-1][1]


def ramp_many(v: np.ndarray, lo: float, hi: float, log: bool = False) -> List[str]:
    v = np.asarray(v, float)
    if log:
        with np.errstate(divide="ignore", invalid="ignore"):
            v, lo, hi = np.log10(v), math.log10(lo) if lo > 0 else lo, \
                math.log10(hi) if hi > 0 else hi
    span = (hi - lo) if hi > lo else 1.0
    return [ramp((x - lo) / span) for x in v]


def bin_colours(n: int) -> List[str]:
    if n <= 1:
        return ["#0072B2"]
    return [ramp(0.05 + 0.85 * i / (n - 1)) for i in range(n)]


def _cell_colour_fn() -> Callable[[int], str]:
    try:
        from .gui.widgets import cell_colour
        return cell_colour
    except Exception:                                          # noqa: BLE001
        return lambda k: GROUP_PALETTE[int(k) % len(GROUP_PALETTE)]


# ================================================================= results
@dataclass
class CellSeries:
    """One cell: a point (x, y scalars), a trace (x = time) or a trajectory."""
    run: str
    run_name: str
    k: int
    x: np.ndarray
    y: np.ndarray
    z: np.ndarray
    t: np.ndarray                     # time of each point ('' for one point)
    colour: str
    group: str
    colours: Optional[List[str]] = None   # per point (coloured by time / Z per point)


@dataclass
class GroupSeries:
    label: str
    colour: str
    x: np.ndarray
    y: np.ndarray
    yerr: np.ndarray
    xerr: np.ndarray
    n: np.ndarray
    kind: str = "line"                # 'line' | 'marker'


@dataclass
class Result:
    shape: str
    cells: List[CellSeries] = field(default_factory=list)
    groups: List[GroupSeries] = field(default_factory=list)
    x_label: str = ""
    y_label: str = ""
    z_label: str = ""
    colour_range: Optional[Tuple[float, float]] = None
    corr: List[Tuple[str, str, float, float, int]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    error: str = ""
    n_cells: int = 0
    n_runs: int = 0
    y: Optional[Quantity] = None
    x: Optional[Quantity] = None
    z: Optional[Quantity] = None

    def points(self) -> Tuple[np.ndarray, np.ndarray, List[Tuple[str, str, int, float]]]:
        """Every drawn per-cell point (x, y, [(run key, run name, k, t)]) - for hover / click."""
        xs, ys, meta = [], [], []
        for c in self.cells:
            xs.append(np.asarray(c.x, float))
            ys.append(np.asarray(c.y, float))
            tt = c.t if len(c.t) == len(c.x) else np.full(len(c.x), np.nan)
            meta += [(c.run, c.run_name, c.k, float(t)) for t in tt]
        if not xs:
            return np.zeros(0), np.zeros(0), []
        return np.concatenate(xs), np.concatenate(ys), meta

    def table(self) -> List[list]:
        """The plotted numbers, one row per point (cells) - the CSV / Excel table."""
        zl = self.z_label or "Z"
        head = ["Run", "Condition / group", "Cell", "Time" if self.shape in ("traces", "pairs")
                else "", self.x_label or "X", self.y_label or "Y"] + ([zl] if self.z else [])
        head = [h for h in head if h != ""]
        rows = [head]
        timed = self.shape in ("traces", "pairs")
        for c in self.cells:
            for i in range(len(c.y)):
                r = [c.run_name, c.group, c.k + 1]
                if timed:
                    r.append(_f(c.t[i]) if i < len(c.t) else "")
                r += [_f(c.x[i]), _f(c.y[i])]
                if self.z is not None:
                    zv = c.z[i] if len(c.z) == len(c.y) else (c.z[0] if len(c.z) else np.nan)
                    r.append(_f(zv))
                rows.append(r)
        return rows

    def summary_table(self) -> List[list]:
        rows = [["Group", self.x_label or "X", "X error", self.y_label or "Y", "Y error", "n"]]
        for g in self.groups:
            for i in range(len(g.x)):
                rows.append([g.label, _f(g.x[i]), _f(g.xerr[i]) if len(g.xerr) else "",
                             _f(g.y[i]), _f(g.yerr[i]) if len(g.yerr) else "",
                             int(g.n[i]) if len(g.n) else ""])
        return rows


def _f(v) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return ""
    return "" if not np.isfinite(v) else f"{v:.6g}"


def _stats(m: np.ndarray, error: str) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(mean, error half-width, n) over axis 1 of m (rows = x positions)."""
    from . import graphstyle as GS
    if m.size == 0:
        z = np.zeros(m.shape[0])
        return np.full(m.shape[0], np.nan), z, z.astype(int)
    s = GS.describe(m)
    err = {"SD": s.sd, "SEM": s.sem, "95% CI": s.ci95}.get(error, np.zeros_like(s.mean))
    return s.mean, np.nan_to_num(np.asarray(err, float)), np.asarray(s.n, int)


def warm_up() -> None:
    """Import the statistics library (about 0.5 s the first time) - call it in a
    background thread when the builder opens, so the first graph is fast."""
    try:
        import scipy.stats                                     # noqa: F401
    except Exception:                                          # noqa: BLE001
        pass


def _corr(x: np.ndarray, y: np.ndarray, method: str) -> Tuple[float, float, int]:
    ok = np.isfinite(x) & np.isfinite(y)
    n = int(ok.sum())
    if n < 3 or np.ptp(x[ok]) == 0 or np.ptp(y[ok]) == 0:
        return float("nan"), float("nan"), n
    try:
        import sys
        if "scipy.stats" not in sys.modules:      # still loading (warm_up): r now, p next time
            raise ImportError
        from scipy import stats
        r = stats.spearmanr(x[ok], y[ok]) if method == "spearman" else stats.pearsonr(x[ok], y[ok])
        return float(r[0]), float(r[1]), n
    except Exception:                                          # noqa: BLE001
        if method == "spearman":
            xr = np.argsort(np.argsort(x[ok])).astype(float)
            yr = np.argsort(np.argsort(y[ok])).astype(float)
            return float(np.corrcoef(xr, yr)[0, 1]), float("nan"), n
        return float(np.corrcoef(x[ok], y[ok])[0, 1]), float("nan"), n


def _group_name(run: RunData, split: str) -> str:
    if split == "run":
        return run.name
    if split == "condition":
        return run.condition or "no condition"
    if split == "group":
        return run.group or run.name
    return "All cells"


# ================================================================= compute
def compute(runs: Sequence[RunData], spec: GraphSpec,
            cell_colour: Optional[Callable[[int], str]] = None,
            run_colours: Optional[Dict[str, str]] = None) -> Result:
    """Everything the plot shows (see the module text). Never raises for a bad
    choice: Result.error says what is wrong in plain words."""
    y, x, z, notes = effective(spec)
    shape = shape_of(spec)
    res = Result(shape=shape, notes=list(notes), y=y, x=x, z=z)
    res.y_label = y.label()
    res.z_label = z.label() if z is not None else ""
    runs = [r for r in runs if r is not None]
    if not runs:
        res.error = "No run to plot yet."
        return res
    res.x_label = x.label() if x is not None else runs[0].time_label
    if x is None and len({r.minutes for r in runs}) > 1:
        res.notes.append("Some runs have no frame interval: their time axis is in timepoints.")
    cc = cell_colour or _cell_colour_fn()
    drift = spec.drift
    if drift:
        res.notes.append(f"Drift correction on: each cell's straight-line slope through frames "
                         f"{drift[0]}-{drift[1]} was taken out of its trace.")
    # ---- per run: the values and which cells count
    per_run = []
    errors = []
    for run in runs:
        try:
            qs = [q for q in (y, x, z) if q is not None]
            comps = sorted({c for q in qs for c in q.comps()})
            m = np.ones(run.n_cells, bool)
            for c in comps:
                if c not in run.meas:
                    raise QuantityError(f"{run.name} has no {COMP_ADJ.get(c, c)} ROIs.")
                m &= run.mask(c, spec.included_only)
            for f in spec.filters:
                if not f.on:
                    continue
                if f.kind == "value" and f.scalar_q() is not None:
                    fq = f.scalar_q()
                    for c in fq.comps():
                        if c in run.meas:
                            m &= run.mask(c, spec.included_only)
                    m &= f.keep(values(run, fq, drift))
                elif f.kind in ("condition", "run", "group"):
                    have = {"condition": run.condition, "run": run.name, "group": run.group}[f.kind]
                    if str(have).strip().lower() != f.text.strip().lower():
                        m[:] = False
            yv = values(run, y, drift)
            xv = values(run, x, drift) if x is not None else None
            zv = values(run, z, drift) if z is not None else None
            per_run.append((run, np.flatnonzero(m), yv, xv, zv))
        except QuantityError as e:
            errors.append(str(e))
    if errors and not per_run:
        res.error = errors[0]
        return res
    for e in dict.fromkeys(errors):
        res.notes.append("Left out: " + e)
    res.n_runs = len(per_run)
    # ---- Z: continuous colour range or bins (over every cell / point drawn)
    zall = []
    for _run, ks, _yv, _xv, zv in per_run:
        if zv is not None and len(ks):
            zall.append(np.ravel(zv[..., ks] if zv.ndim == 2 else zv[ks]))
    zcat = np.concatenate(zall) if zall else np.zeros(0)
    edges = None
    if z is not None and spec.z_mode == "bins":
        edges = bin_edges(zcat, spec.z_bins)
        if spec.z_bins.kind == "count" and len(np.unique(zcat[np.isfinite(zcat)])) < len(edges) - 1:
            res.notes.append("Fewer different Z values than bins: some bins are empty.")
    zlo = zhi = None
    if z is not None and spec.z_mode == "colour" and np.isfinite(zcat).any():
        zlo, zhi = float(np.nanmin(zcat)), float(np.nanmax(zcat))
        res.colour_range = (zlo, zhi)
    nb = len(edges) - 1 if edges is not None else 0
    # ---- group keys: split (pool / run / condition / group) x Z bin
    split_names = list(dict.fromkeys(_group_name(r, spec.split) for r, *_ in per_run))
    base_col = {}
    for i, g in enumerate(split_names):
        rc = (run_colours or {}).get(g)
        base_col[g] = rc or (GROUP_PALETTE[i % len(GROUP_PALETTE)] if len(split_names) > 1
                             or nb == 0 else "#000000")
    bcols = bin_colours(nb) if nb else []
    if nb:
        counts = [0] * nb
        zb_all = assign_bins(zcat, edges)
        for b in zb_all[zb_all >= 0]:
            counts[b] += 1
        blabels = [s.rsplit(" (n = ", 1)[0] for s in bin_labels(edges, zcat, counts)]
    else:
        blabels = []
    gsort: Dict[str, tuple] = {}

    def gkey(run: RunData, b: int) -> Tuple[str, str]:
        g = _group_name(run, spec.split)
        lab0 = g if (b < 0 or not nb) else (
            f"{z.short()} {blabels[b]}" if len(split_names) == 1 else f"{g} - {blabels[b]}")
        gsort.setdefault(lab0, (split_names.index(g), b))
        if b < 0 or not nb:
            return g, base_col[g]
        lab = lab0
        if len(split_names) == 1:
            return lab, bcols[b]
        from .celllines import shades_of
        try:
            return lab, shades_of(base_col[g], nb)[b]
        except Exception:                                      # noqa: BLE001
            return lab, bcols[b]

    single = len(per_run) == 1 and spec.split == "pool"
    order: List[str] = []
    gcols: Dict[str, str] = {}
    # ---- build the per-cell series
    if shape == "traces":
        for run, ks, yv, _xv, zv in per_run:
            t = run.time
            for k in ks:
                zval = float(zv[k]) if zv is not None else np.nan
                b = int(assign_bins(np.array([zval]), edges)[0]) if nb else -1
                if nb and b < 0:
                    continue
                g, gc = gkey(run, b)
                col = (ramp_many([zval], zlo, zhi)[0] if zlo is not None else
                       gc if (nb or not single) else cc(int(k)))
                res.cells.append(CellSeries(run.key, run.name, int(k), t, yv[:, k],
                                            np.array([zval]), t, col, g))
                if g not in gcols:
                    order.append(g)
                    gcols[g] = gc
        # group means over aligned times (union; n varies where runs differ)
        for g in sorted(order, key=lambda g: gsort.get(g, (0, 0))):
            mem = [c for c in res.cells if c.group == g]
            tt = np.unique(np.round(np.concatenate([c.t for c in mem]), 9))
            M = np.full((len(tt), len(mem)), np.nan)
            for j, c in enumerate(mem):
                M[np.searchsorted(tt, np.round(c.t, 9)), j] = c.y
            mu, er, n = _stats(M, spec.error)
            res.groups.append(GroupSeries(f"{g} (n = {len(mem)})", gcols[g], tt, mu, er,
                                          np.zeros(0), n))
        if len({len(r.time) for r, *_ in per_run}) > 1 or \
                len({r.seconds_per_frame for r, *_ in per_run}) > 1:
            res.notes.append("The runs have different times: each mean uses the cells that have "
                             "a value at that time (nothing interpolated).")
    elif shape in ("scatter", "binned"):
        for run, ks, yv, xv, zv in per_run:
            for k in ks:
                zval = float(zv[k]) if zv is not None else np.nan
                b = int(assign_bins(np.array([zval]), edges)[0]) if nb else -1
                if nb and b < 0:
                    continue
                g, gc = gkey(run, b)
                col = (ramp_many([zval], zlo, zhi)[0] if zlo is not None else
                       gc if (nb or not single) else cc(int(k)))
                res.cells.append(CellSeries(run.key, run.name, int(k), np.array([xv[k]]),
                                            np.array([yv[k]]), np.array([zval]), np.zeros(0),
                                            col, g))
                if g not in gcols:
                    order.append(g)
                    gcols[g] = gc
        for g in sorted(order, key=lambda g: gsort.get(g, (0, 0))):
            mem = [c for c in res.cells if c.group == g]
            xs = np.array([c.x[0] for c in mem], float)
            ys = np.array([c.y[0] for c in mem], float)
            ok = np.isfinite(xs) & np.isfinite(ys)
            if shape == "binned":
                xe = bin_edges(np.concatenate([c.x for c in res.cells]), spec.x_bins)
                xb = assign_bins(xs, xe)
                gx, gy, gxe, gye, gn = [], [], [], [], []
                for b in range(len(xe) - 1):
                    sel = ok & (xb == b)
                    if not sel.any():
                        continue
                    mx, ex, _n = _stats(xs[sel][None, :], spec.error)
                    my, ey, ny = _stats(ys[sel][None, :], spec.error)
                    gx.append(mx[0]), gy.append(my[0]), gxe.append(ex[0]), gye.append(ey[0])
                    gn.append(ny[0])
                res.groups.append(GroupSeries(f"{g} (n = {int(ok.sum())})", gcols[g],
                                              np.array(gx), np.array(gy), np.array(gye),
                                              np.array(gxe), np.array(gn, int), "line"))
            else:
                mx, ex, _n = _stats(xs[ok][None, :], spec.error)
                my, ey, ny = _stats(ys[ok][None, :], spec.error)
                res.groups.append(GroupSeries(f"{g} (n = {int(ok.sum())})", gcols[g], mx, my, ey,
                                              ex, ny, "marker"))
            if spec.corr != "none":
                r, p, n = _corr(xs, ys, spec.corr)
                res.corr.append((g, spec.corr, r, p, n))
        if spec.corr != "none" and len(order) > 1:
            xs = np.array([c.x[0] for c in res.cells], float)
            ys = np.array([c.y[0] for c in res.cells], float)
            r, p, n = _corr(xs, ys, spec.corr)
            res.corr.insert(0, ("all", spec.corr, r, p, n))
    else:                                                   # pairs: trace vs trace
        tl = runs[0].time_label
        tall = np.concatenate([r.time for r, *_ in per_run]) if per_run else np.zeros(0)
        z_per_point = zv_is_trace = z is not None and z.is_trace
        if z is None and spec.pairs == "points":
            res.colour_range = (float(np.nanmin(tall)), float(np.nanmax(tall))) if len(tall) \
                else None
            res.z_label = tl
        for run, ks, yv, xv, zv in per_run:
            t = run.time
            for k in ks:
                zz = zv[:, k] if zv_is_trace else (np.array([float(zv[k])]) if zv is not None
                                                     else np.zeros(0))
                b = -1
                if nb and not z_per_point:
                    b = int(assign_bins(zz[:1], edges)[0])
                    if b < 0:
                        continue
                g, gc = gkey(run, b)
                cols = None
                if z is None and spec.pairs == "points" and res.colour_range:
                    cols = ramp_many(t, *res.colour_range)
                elif zlo is not None and z_per_point:
                    cols = ramp_many(zz, zlo, zhi)
                elif nb and z_per_point:
                    bb = assign_bins(zz, edges)
                    cols = [bcols[i] if i >= 0 else "#999999" for i in bb]
                col = (ramp_many(zz[:1], zlo, zhi)[0] if zlo is not None and not z_per_point
                       else gc if (nb or not single) else cc(int(k)))
                res.cells.append(CellSeries(run.key, run.name, int(k), xv[:, k], yv[:, k], zz, t,
                                            col, g, cols))
                if g not in gcols:
                    order.append(g)
                    gcols[g] = gc
        for g in sorted(order, key=lambda g: gsort.get(g, (0, 0))):
            mem = [c for c in res.cells if c.group == g]
            tt = np.unique(np.round(np.concatenate([c.t for c in mem]), 9))
            MX = np.full((len(tt), len(mem)), np.nan)
            MY = np.full((len(tt), len(mem)), np.nan)
            for j, c in enumerate(mem):
                i = np.searchsorted(tt, np.round(c.t, 9))
                MX[i, j], MY[i, j] = c.x, c.y
            mx, ex, _n = _stats(MX, spec.error)
            my, ey, ny = _stats(MY, spec.error)
            res.groups.append(GroupSeries(f"{g} (n = {len(mem)})", gcols[g], mx, my, ey, ex, ny))
            if spec.corr != "none":
                xs = np.concatenate([c.x for c in mem])
                ys = np.concatenate([c.y for c in mem])
                r, p, n = _corr(xs, ys, spec.corr)
                res.corr.append((g, spec.corr, r, p, n))
        if spec.corr != "none" and res.corr:
            res.notes.append("r over every (cell, timepoint) point: points of one cell are not "
                             "independent, so read p with care.")
    res.n_cells = len(res.cells)
    if not res.cells:
        res.error = ("No cell is left to plot - check the conditions"
                     + (" or tick 'all cells' (some are excluded)" if spec.included_only else "")
                     + ".")
    return res


# ================================================================= exports
def save_figure(path, res: Result, spec: GraphSpec, title: str = "", dpi: int = 300) -> str:
    """The graph drawn by matplotlib (.svg / .pdf keep the text as text, .png at dpi):
    the same cells, means, errors and colours as the live plot. Never overwrites."""
    import matplotlib
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.colors import LinearSegmentedColormap, Normalize
    from matplotlib.figure import Figure
    from .safety import new_output_file
    p = Path(path)
    fmt = (p.suffix.lstrip(".") or "svg").lower()
    fig = Figure(figsize=(7.0, 4.4), dpi=dpi)
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    for s_ in ("top", "right"):
        ax.spines[s_].set_visible(False)
    shape = res.shape
    if spec.show_cells and res.cells:
        if shape == "traces" or (shape == "pairs" and spec.pairs == "trajectories"):
            alpha = 0.45 if spec.show_mean and res.groups else 0.9
            for c in res.cells:
                ax.plot(c.x, c.y, color=c.colour, lw=0.6, alpha=alpha)
        else:
            xs = np.concatenate([c.x for c in res.cells])
            ys = np.concatenate([c.y for c in res.cells])
            cols: List[str] = []
            for c in res.cells:
                cols += c.colours if c.colours is not None else [c.colour] * len(c.x)
            ax.scatter(xs, ys, s=4 if shape == "pairs" else 12, c=cols, linewidths=0)
    if spec.show_mean or not spec.show_cells:
        for g in res.groups:
            err = g.yerr if spec.error != "none" else None
            if shape == "traces":
                ax.plot(g.x, g.y, color=g.colour, lw=2.2, label=g.label)
                if err is not None:
                    ax.fill_between(g.x, g.y - err, g.y + err, color=g.colour, alpha=0.2, lw=0)
            elif shape == "pairs":
                ax.plot(g.x, g.y, color=g.colour, lw=2.2, marker="o", ms=2.5, label=g.label)
            else:
                xe = g.xerr if (spec.error != "none" and len(g.xerr) == len(g.x)) else None
                ax.errorbar(g.x, g.y, yerr=err, xerr=xe, color=g.colour,
                            fmt="s-" if g.kind == "line" else "s", ms=6, mec="k", lw=1.4,
                            label=g.label)
    if res.colour_range is not None:
        cmap = LinearSegmentedColormap.from_list(
            "pp", [(pos, tuple(v / 255 for v in c)) for pos, c in _RAMP])
        sm = matplotlib.cm.ScalarMappable(norm=Normalize(*res.colour_range), cmap=cmap)
        fig.colorbar(sm, ax=ax, pad=0.02).set_label(res.z_label, fontsize=8)
    if spec.log_x:
        ax.set_xscale("log")
    if spec.log_y:
        ax.set_yscale("log")
    ax.set_xlabel(res.x_label, fontsize=9)
    ax.set_ylabel(res.y_label, fontsize=9)
    ax.tick_params(labelsize=8)
    if title:
        ax.set_title(title, fontsize=9)
    if res.groups and (len(res.groups) > 1 or res.groups[0].label != "All cells"):
        ax.legend(fontsize=7, frameon=False)
    fig.tight_layout()
    with matplotlib.rc_context({"svg.fonttype": "none", "pdf.fonttype": 42}):
        with new_output_file(p) as (used, stream):
            fig.savefig(stream, format=fmt, dpi=dpi)
    return str(used)


def header_lines(sentence: str, spec: GraphSpec, res: Result) -> List[str]:
    from . import graphparse as GP
    out = [f"Graph: {sentence}"]
    on = [GP.filter_text(f) for f in spec.filters if f.on]
    out.append("Conditions: " + ("; ".join((["included cells only"] if spec.included_only else
                                           ["all cells (also excluded ones)"]) + on)))
    out.append(f"Error: {spec.error}; split: {spec.split}; cells: {res.n_cells}; runs: "
               f"{res.n_runs}")
    for g, m, r, p, n in res.corr:
        out.append(f"{'Spearman rho' if m == 'spearman' else 'Pearson r'} ({g}): {_f(r)}, "
                   f"p = {_f(p)}, n = {n}")
    out += [f"Note: {n}" for n in res.notes]
    return out


def save_table(path, sentence: str, spec: GraphSpec, res: Result) -> str:
    """The plotted table as .csv or .xlsx (by the suffix), the sentence and conditions
    on top; group means below (.csv) / on a second sheet (.xlsx). Never overwrites."""
    from .compare import _write_csv, _write_xlsx
    p = Path(path)
    head = [[h] for h in header_lines(sentence, spec, res)]
    if p.suffix.lower() == ".xlsx":
        return _write_xlsx(p, [("Cells", res.table()), ("Means", res.summary_table()),
                               ("Methods", [["Methods"]] + head)])
    rows = head + [[]] + res.table() + [[]] + res.summary_table()
    return _write_csv(p.with_suffix(".csv"), rows)


# ================================================================= recipes
RECENT_MAX = 12


def _recipes_file() -> Path:
    from .history import home_dir
    return home_dir() / "graph_recipes.json"


def load_recipes() -> dict:
    """{'favourites': [{name, sentence, spec}], 'recent': [{sentence, spec}]} of this user."""
    try:
        d = json.loads(_recipes_file().read_text(encoding="utf-8"))
        if isinstance(d, dict):
            return {"favourites": [r for r in d.get("favourites") or [] if isinstance(r, dict)],
                    "recent": [r for r in d.get("recent") or [] if isinstance(r, dict)]}
    except (OSError, ValueError):
        pass
    return {"favourites": [], "recent": []}


def _save_recipes(d: dict) -> None:
    p = _recipes_file()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, indent=1), encoding="utf-8")
        tmp.replace(p)
    except OSError:
        pass


def add_recent(sentence: str, spec: GraphSpec) -> dict:
    d = load_recipes()
    d["recent"] = [r for r in d["recent"] if r.get("sentence") != sentence]
    d["recent"].insert(0, {"sentence": sentence, "spec": spec.to_dict()})
    d["recent"] = d["recent"][:RECENT_MAX]
    _save_recipes(d)
    return d


def save_favourite(name: str, sentence: str, spec: GraphSpec) -> dict:
    d = load_recipes()
    name = str(name).strip() or sentence[:40]
    d["favourites"] = [r for r in d["favourites"] if r.get("name") != name]
    d["favourites"].append({"name": name, "sentence": sentence, "spec": spec.to_dict()})
    _save_recipes(d)
    return d


def remove_favourite(name: str) -> dict:
    d = load_recipes()
    d["favourites"] = [r for r in d["favourites"] if r.get("name") != name]
    _save_recipes(d)
    return d


def is_favourite(sentence: str) -> bool:
    return any(r.get("sentence") == sentence for r in load_recipes()["favourites"])
