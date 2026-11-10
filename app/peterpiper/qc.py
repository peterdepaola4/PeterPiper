"""
Automatic quality control of every tracked cell.

After tracking, each cell is scored on purely *technical* criteria - could it
be followed, did its outline stay stable, is it bright enough above the
background noise, is it saturated, did it touch the image edge, does its trace
contain one-frame artefacts. Cells that fail are excluded automatically, with
the reason recorded, so nothing is dropped silently.

Deliberately, nothing here looks at the size or direction of the response: a
QC step that removes cells for responding "too much" or "too little" would bias
the result. Only measurement failures are rejected.

BLOCK: a new test is one more block in qc_cell(); give it a reason string.

v2.3: every channel is measured in every ROI, so the 'at or below background'
and 'too dim' tests look only at the channels the compartment's tracking rule
uses (channel A, and B for WITH / AND / IF) when the rule is given. An IF rule
excludes a cell without real signal in B (gate_reason) - even a hand-drawn one,
because that is what the rule asks for.
"""
from __future__ import annotations

import warnings
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import numpy as np

from .config import Experiment, Settings
from .measure import Measurements


@contextmanager
def _quiet_nan():
    """Silence numpy's benign 'All-NaN slice' / 'Mean of empty slice' warnings
    (a cell with no value at some timepoints); the results are unchanged (NaN)."""
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="All-NaN slice", category=RuntimeWarning)
        warnings.filterwarnings("ignore", message="Mean of empty slice", category=RuntimeWarning)
        yield


def gate_reason(name_b: str, snr: float, gate: float) -> Optional[str]:
    """IF rule: the exclusion reason when the cell's signal-to-noise in channel B
    (rules.gate_snr) is below the gate (Settings.gate_snr); None if it passes."""
    snr = float(snr) if snr is not None else float("nan")
    if np.isfinite(snr) and snr >= float(gate):
        return None
    shown = f"{snr:.1f}" if np.isfinite(snr) else "not measurable"
    return f"no {name_b} signal (IF gate: SNR {shown} < {float(gate):g})"


def rule_channels(rule, M: Measurements, exp: Optional[Experiment] = None) -> List[int]:
    """Indices into M.channels of the channels a tracking rule uses (A, and B for
    WITH / AND / IF), matched by NAME (so a channel subset of M still works).
    Empty if none can be matched."""
    names = list(getattr(exp, "channels", None) or M.channels)
    used = rule.channels_used() if hasattr(rule, "channels_used") else [int(rule.a)]
    out = []
    for i in used:
        if 0 <= int(i) < len(names) and names[int(i)] in M.channels:
            j = M.channels.index(names[int(i)])
            if j not in out:
                out.append(j)
    return out


@dataclass
class CellQC:
    index: int                                   # absolute ROI index (Cell_{index+1})
    passed: bool = True
    score: float = 1.0                           # 0-1, for ranking only
    reasons: List[str] = field(default_factory=list)
    metrics: Dict[str, float] = field(default_factory=dict)

    @property
    def summary(self) -> str:
        return "pass" if self.passed else "; ".join(self.reasons)


def _spikes(x: np.ndarray, sigma: float, rel: float = 0.2) -> np.ndarray:
    """
    Indices of one-frame artefacts: a point far from BOTH neighbours while the
    neighbours agree with each other. A real response rises and stays (or
    falls over several frames); a mis-segmented frame jumps and comes back.
    """
    x = np.asarray(x, float)
    if x.size < 5 or sigma <= 0:
        return np.zeros(0, int)
    ok = np.isfinite(x)
    if ok.sum() < 5:
        return np.zeros(0, int)
    xi = x.copy()
    xi[~ok] = np.interp(np.flatnonzero(~ok), np.flatnonzero(ok), x[ok])
    d = np.diff(xi)
    noise = 1.4826 * np.median(np.abs(d - np.median(d))) / np.sqrt(2.0)
    level = np.median(np.abs(xi))
    noise = max(noise, 1e-3 * max(level, 1e-9))
    mid = xi[1:-1]
    left, right = xi[:-2], xi[2:]
    nb = 0.5 * (left + right)
    dev = mid - nb
    agree = np.abs(left - right) < 0.5 * np.abs(dev)
    big = (np.abs(dev) > sigma * noise) & (np.abs(dev) > rel * max(level, 1e-9))
    hits = np.flatnonzero(agree & big) + 1
    # the first / last frame only have one neighbour: compare with the next two
    for t, a, b in ((0, 1, 2), (x.size - 1, x.size - 2, x.size - 3)):
        dev_e = xi[t] - xi[a]
        if (abs(dev_e) > sigma * noise and abs(dev_e) > rel * max(level, 1e-9)
                and abs(xi[a] - xi[b]) < 0.5 * abs(dev_e)):
            hits = np.append(hits, t)
    return np.unique(hits)


def response_options(channels: Sequence[str]) -> List[str]:
    """What the responder filter can look at, as shown in the dropdown."""
    out = ["any channel"] + [f"F/F0 - {c}" for c in channels]
    out += [f"R/R0 - {a}/{b}" for i, a in enumerate(channels)
            for j, b in enumerate(channels) if i != j]
    return out


def _smooth3(y: np.ndarray) -> np.ndarray:
    """3-point running median along time, so one noisy frame is not a 'response'."""
    if y.shape[0] < 3:
        return y
    p = np.concatenate([y[:1], y, y[-1:]], axis=0)
    with _quiet_nan():
        return np.nanmedian(np.stack([p[:-2], p[1:-1], p[2:]]), axis=0)


def parse_quantities(text: str, channels: Sequence[str]) -> List[str]:
    """The valid entries of a '; '-separated resp_quantity for these channels."""
    valid = set(response_options(channels)) - {"any channel"}
    return [q.strip() for q in str(text).split(";") if q.strip() in valid]


def response_size(M: Measurements, s: Settings) -> np.ndarray:
    """
    Per cell: the largest change from baseline after the baseline timepoint,
    on the quantities listed in s.resp_quantity (the largest over them, so a
    cell responding in any one of them counts). Direction: 'either' uses
    |x - 1|, 'rise' uses x - 1, 'fall' uses 1 - x. Traces are 3-point median
    smoothed first so one noisy frame is not a response.
    """
    T = M.n_timepoints
    b = int(np.clip(s.baseline_timepoint - 1, 0, T - 1))
    after = slice(b + 1, T) if T - b - 1 >= 2 else slice(0, T)
    traces = []
    k = float(getattr(s, "ratio_min_snr", 5.0))       # V3.0: too dim at baseline = blank
    for q in parse_quantities(s.resp_quantity, M.channels):
        if q.startswith("F/F0 - "):
            traces.append(M.ff0(M.channels.index(q[7:]), b, k))
        else:
            a, c = q[7:].split("/", 1)
            traces.append(M.rr0(M.channels.index(a), M.channels.index(c), b, k))
    if not traces:                                           # "any channel"
        traces = [M.ff0(c, b, k) for c in range(M.n_channels)]
    best = np.full(M.n_cells, -np.inf)
    for y in traces:
        d = _smooth3(y)[after] - 1.0
        if s.resp_direction == "rise":
            pass
        elif s.resp_direction == "fall":
            d = -d
        else:
            d = np.abs(d)
        with np.errstate(invalid="ignore"), _quiet_nan():
            dev = np.nanmax(d, axis=0) if d.shape[0] else np.zeros(M.n_cells)
        best = np.fmax(best, np.where(np.isfinite(dev), dev, -np.inf))
    return np.where(np.isfinite(best), best, 0.0)


def response_label(s: Settings, channels: Sequence[str]) -> str:
    qs = parse_quantities(s.resp_quantity, channels)
    what = " or ".join(qs) if qs else "any channel"
    sign = {"rise": "+", "fall": "-"}.get(s.resp_direction, "+/-")
    return f"{what} never changes by more than {sign}{s.resp_threshold * 100:.0f}%"


def qc_cell(k: int, M: Measurements, exp: Experiment, s: Settings,
            rois_t: Optional[Sequence[Sequence]] = None,
            manual: bool = False, field_frames: Sequence[int] = (),
            median_area: float = 0.0, response: Optional[float] = None,
            channels: Optional[Sequence[int]] = None,
            gate_fail: Optional[str] = None) -> CellQC:
    """Run every test on one cell. rois_t is TrackResult.measured ([t][cell]).
    channels: indices into M of the channels the tracking rule uses (the
    signal / background tests look only at these; the first is the 'too dim'
    channel). None = V2.2: s.ref_channel and every channel.
    gate_fail: the IF-rule reason (gate_reason) when the cell failed the gate."""
    out = CellQC(index=k)
    T = M.n_timepoints
    chans = [int(c) for c in channels if 0 <= int(c) < M.n_channels] if channels else []
    ref = chans[0] if chans else int(np.clip(s.ref_channel, 0, M.n_channels - 1))
    reasons = out.reasons
    terms: List[float] = []

    # ---- 1  could it be followed? ----------------------------------------
    q = M.quality[:, k]
    lost = float(np.mean(q < 0.4)) if T else 0.0
    out.metrics["lost_frac"] = lost
    if s.track_mode == "resegment" and not getattr(s, "cell_finder", "") \
            and lost > s.qc_max_lost_frac:
        reasons.append(f"not re-detected at {int(round(lost * T))}/{T} timepoints")
    terms.append(1.0 - lost)

    # ---- 2  did the outline stay stable? ------------------------------------
    a = M.area_px[:, k].astype(float)
    if np.any(a <= 0):
        n0 = int(np.sum(a <= 0))
        reasons.append(f"empty ROI at {n0} timepoint(s)")
        terms.append(0.0)
    elif T > 1:
        r = a[1:] / a[:-1]
        jump = float(np.max(np.maximum(r, 1.0 / r)))
        out.metrics["max_area_jump"] = jump
        if jump > s.qc_max_area_jump:
            t = int(np.argmax(np.maximum(r, 1.0 / r))) + 2
            reasons.append(f"outline jumped {jump:.1f}x in size at timepoint {t} "
                           f"(merged with / split from a neighbour)")
        terms.append(float(np.clip(1.0 / max(1.0, jump / 1.3), 0, 1)))

    # ---- 3  bright enough above the background noise? -----------------------
    bs = M.bg_subtracted()
    sig = bs[:, ref, k]
    if M.background_sd is not None and np.isfinite(M.background_sd[:, ref]).any():
        noise = float(np.nanmedian(M.background_sd[:, ref]))
        with _quiet_nan():
            snr = float(np.nanmedian(sig)) / max(noise, 1e-6)
        out.metrics["snr"] = snr
        if np.isfinite(snr) and snr < s.qc_min_snr:
            reasons.append(f"too dim (signal/noise {snr:.1f} < {s.qc_min_snr:g})")
        terms.append(float(np.clip(snr / (2.0 * max(s.qc_min_snr, 1e-6)), 0, 1))
                     if np.isfinite(snr) else 0.0)

    # every channel must sit above background, or ratios become meaningless
    # (v2.3 with a rule: only the channels the rule tracks on - every channel is
    # measured everywhere now, and a channel may rightly be dark in a compartment)
    for c in (chans or range(M.n_channels)):
        ch = M.channels[c]
        med = float(np.nanmedian(bs[:, c, k])) if np.isfinite(bs[:, c, k]).any() else np.nan
        if not np.isfinite(med) or med <= 0:
            reasons.append(f"at or below background in {ch}")
            terms.append(0.3)
            break

    # ---- 4  saturation ------------------------------------------------------
    with np.errstate(divide="ignore", invalid="ignore"):
        frac = M.n_saturated[:, :, k] / np.maximum(a, 1)[:, None]
    sat = float(np.nanmax(frac)) if frac.size else 0.0
    out.metrics["saturated_frac"] = sat
    if sat > s.qc_max_saturated_frac:
        reasons.append(f"saturated ({sat * 100:.1f}% of pixels at worst)")
    terms.append(float(np.clip(1.0 - sat / max(s.qc_max_saturated_frac * 2, 1e-6), 0, 1)))

    # ---- 5  touched the image edge while tracking ----------------------------
    if s.exclude_border and rois_t:
        H, W = exp.height, exp.width
        for t, lst in enumerate(rois_t):
            if k < len(lst):
                y0, x0, y1, x1 = lst[k].bbox
                if lst[k].area and (y0 <= 0 or x0 <= 0 or y1 >= H or x1 >= W):
                    reasons.append(f"touched the image edge at timepoint {t + 1}")
                    break

    # ---- 6  one-frame artefacts in any channel ------------------------------
    # A jump only counts when the outline also misbehaved at that frame (size
    # off by > 25% from its neighbours, or not re-detected). A genuine fast
    # transient with a steady outline is biology and is left alone.
    # Frames where the whole field jumps (focus, lamp, first frame) are listed
    # in field_frames and ignored: that is not a problem of this one cell.
    if s.qc_spike_sigma > 0 and T >= 5 and np.all(a > 0):
        hits = sorted(set(cell_spikes(k, M, s)) - set(field_frames))
        out.metrics["spikes"] = float(len(hits))
        if hits:
            shown = ", ".join(str(h + 1) for h in hits[:4]) + ("..." if len(hits) > 4 else "")
            reasons.append(f"one-frame artefact at timepoint {shown}")
        terms.append(1.0 if not hits else 0.4)

    # ---- 7  small specks ------------------------------------------------------
    seed_t = int(np.clip(s.seg_timepoint - 1, 0, T - 1))
    if s.qc_min_area_frac > 0 and median_area > 0 and a[seed_t] > 0:
        frac_a = float(a[seed_t] / median_area)
        out.metrics["area_vs_median"] = frac_a
        if frac_a < s.qc_min_area_frac:
            reasons.append(f"small speck ({frac_a * 100:.0f}% of the median cell's area)")
            terms.append(0.3)

    # ---- 8  responders only -----------------------------------------------------
    if response is not None:
        out.metrics["max_response"] = float(response)
        if s.resp_enabled and response <= s.resp_threshold:
            reasons.append(f"no response ({response_label(s, M.channels)} of baseline; "
                           f"largest {response * 100:.1f}%)")

    out.score = float(np.prod(terms)) if terms else 1.0
    out.passed = not reasons
    if gate_fail:                     # IF rule: excluded, even if drawn by hand
        reasons.insert(0, gate_fail)
        out.metrics["gate_failed"] = 1.0
        out.passed = False
    elif manual and reasons:
        reasons.append("drawn by hand, so kept")
        out.passed = True
    return out


def cell_spikes(k: int, M: Measurements, s: Settings) -> List[int]:
    """One-frame jumps in any channel that coincide with an outline glitch."""
    a = M.area_px[:, k].astype(float)
    q = M.quality[:, k]
    T = M.n_timepoints
    if T < 5 or np.any(a <= 0) or s.qc_spike_sigma <= 0:
        return []
    nb_area = np.empty(T)
    nb_area[1:-1] = 0.5 * (a[:-2] + a[2:])
    nb_area[0], nb_area[-1] = a[1], a[-2]
    glitch = (np.abs(a / nb_area - 1.0) > 0.25) | (q < 0.4)
    bs = M.bg_subtracted()
    hits = set()
    for c in range(M.n_channels):
        hits.update(int(i) for i in _spikes(bs[:, c, k], s.qc_spike_sigma) if glitch[int(i)])
    return sorted(hits)


def field_wide_frames(M: Measurements, s: Settings, cells: Sequence[int]) -> List[int]:
    """Frames where at least a quarter of the cells (and >= 3) 'spike' together."""
    cells = list(cells)
    if len(cells) < 4:
        return []
    counts = np.zeros(M.n_timepoints, int)
    for k in cells:
        for t in cell_spikes(k, M, s):
            counts[t] += 1
    return [int(t) for t in np.flatnonzero((counts >= 3) & (counts >= 0.25 * len(cells)))]


def run_qc(M: Measurements, exp: Experiment, s: Settings,
           rois_t: Optional[Sequence[Sequence]] = None,
           seed_rois: Optional[Sequence] = None, rule=None,
           channels: Optional[Sequence[int]] = None,
           gate: Optional[Dict[int, float]] = None) -> List[CellQC]:
    """QC every cell (included or not). Hand-drawn ROIs are reported, never dropped
    - except by an IF rule's gate, which is what that rule asks for.

    rule: the compartment's rules.TrackRule (v2.3) - the signal / background
          tests then look only at the channels it uses (rule_channels);
    channels: or those channel indices (into M) directly; both None = V2.2;
    gate: {cell index: signal-to-noise in channel B} from track_cells()["gate"]
          for an IF rule; cells below Settings.gate_snr fail with gate_reason().
    """
    if isinstance(rule, dict):                    # a saved rule (to_dict / track["rules"])
        from .rules import TrackRule
        rule = TrackRule.from_dict(rule, list(getattr(exp, "channels", None) or M.channels))
    if channels is None and rule is not None:
        channels = rule_channels(rule, M, exp) or None
    gate_fail: Dict[int, str] = {}
    if gate:
        thr = float(getattr(s, "gate_snr", 5.0))
        b = int(getattr(rule, "b", -1)) if rule is not None else -1
        names = list(getattr(exp, "channels", None) or M.channels)
        name_b = names[b] if 0 <= b < len(names) else "second channel"
        for k, snr in gate.items():
            why = gate_reason(name_b, snr, thr)
            if why:
                gate_fail[int(k)] = why
    seed_t = int(np.clip(s.seg_timepoint - 1, 0, M.n_timepoints - 1))
    live = [k for k in range(M.n_cells) if M.area_px[seed_t, k] > 0]
    field_frames = field_wide_frames(M, s, live)
    # median size of the cells that are actually in play (included at the start)
    pool = [k for k in live if seed_rois is None or k >= len(seed_rois)
            or getattr(seed_rois[k], "include", True)] or live
    median_area = float(np.median(M.area_px[seed_t, pool])) if pool else 0.0
    resp = response_size(M, s)
    out = []
    for k in range(M.n_cells):
        manual = bool(seed_rois is not None and k < len(seed_rois)
                      and getattr(seed_rois[k], "source", "auto") == "manual")
        c = qc_cell(k, M, exp, s, rois_t, manual, field_frames, median_area, float(resp[k]),
                    channels, gate_fail.get(k))
        if field_frames:
            c.metrics["field_wide_frames"] = float(len(field_frames))
        out.append(c)
    return out


def summarise(qc: Sequence[CellQC], considered: Sequence[int]) -> str:
    """One line for the status bar: how many failed and the commonest reasons."""
    failed = [qc[k] for k in considered if k < len(qc) and not qc[k].passed]
    if not failed:
        return f"QC: all {len(considered)} cells passed."
    counts: Dict[str, int] = {}
    for c in failed:
        for r in c.reasons:
            key = r.split(" (")[0]
            for word in ("not re-detected", "outline jumped", "too dim", "saturated",
                         "touched the image edge", "one-frame artefact", "empty ROI",
                         "at or below background", "small speck", "no response"):
                if key.startswith(word):
                    key = word
                    break
            counts[key] = counts.get(key, 0) + 1
    top = ", ".join(f"{n} {r}" for r, n in sorted(counts.items(), key=lambda kv: -kv[1]))
    return (f"QC excluded {len(failed)} of {len(considered)} cells ({top}). "
            f"Click a cell to include it again.")
