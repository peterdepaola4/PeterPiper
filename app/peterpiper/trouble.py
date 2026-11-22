"""
PeterPiper 4.0: the ROI troubleshooter (engine; the window is gui/troubledlg.py).

For ONE problem cell and compartment it tries the logical alternatives to the
current tracking rule / settings, runs each for that cell only (retrack.py:
the cell's neighbourhood is read once, every other cell is replayed as it
was), and scores how steady each result is - so the user can pick the best by
eye, and the program can say which looks best.

    alternatives(k, comp, current_rule, exp, cells, frame_t0, settings)
        -> [Candidate]   ("now" first, then up to ~8 first-ring ideas,
                          then the "Try more" ring)
    run_candidates(src, exp, cells, background, t0, previous_out, k, comp,
                   candidates, track_kw, ...)
        -> yields CandidateResult as each one finishes (cancellable)
    choice_overrides(overrides, k, comp, candidate)
        -> the overrides to track with (manual.track_cells / retrack_cells)

Which ideas: only channels that show this cell at t0 (signal-to-noise at
least the IF bar, the same test as rules.gate_snr) are used as the main
channel; each alone ("GFP only"), helped by another such channel ("GFP with
DAPI helping"), trimmed by one (AND / WITH); and the size / move limits
(size within 15 / 25 / 40 %, moves up to 2 / 3 / 5 um per timepoint).
"""
from __future__ import annotations

import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

import numpy as np

from . import manual as MN
from . import retrack as RT
from .rules import HELP, TrackRule, _name
from .segment import Roi

SIZE_TOLS = (0.15, 0.25, 0.40)
MAX_MOVES = (2.0, 3.0, 5.0)
FIRST_RING = 8                  # ideas in the first ring (plus "now": 9 tiles)
GOOD, OK = 75.0, 50.0           # score bars for the "good" / "ok" badge


@dataclass
class Candidate:
    label: str                              # plain words, e.g. "GFP only"
    rule: Optional[TrackRule]               # None: the compartment's own rule
    settings: Dict[str, float] = field(default_factory=dict)
    why: str = ""                           # one sentence (hover)
    prior: float = 0.0                      # a-priori plausibility (higher first)
    ring: int = 1                           # 1 first ring, 2 "Try more"
    current: bool = False                   # the tracking as it is now

    def key(self, channels: Sequence[str]) -> tuple:
        r = self.rule.to_dict(list(channels)) if self.rule is not None else None
        return (repr(sorted(r.items())) if r else None, tuple(sorted(self.settings.items())))


@dataclass
class CandidateResult:
    candidate: Candidate
    rois: List[Roi]                         # [t] the cell's ROI of this compartment
    mean: np.ndarray                        # (T, C) its mean per channel
    quality: np.ndarray                     # (T,) 1 redrawn, 0.9 kept as drawn, 0.3 moved only
    area: np.ndarray                        # (T,) pixels
    score: float = 0.0
    grade: str = "ok"                       # "good" | "ok" | "poor"
    reasons: List[str] = field(default_factory=list)
    out: Optional[dict] = None              # the whole result (cell spliced in)
    seconds: float = 0.0
    error: str = ""


# ==========================================================================
#  Which ideas
# ==========================================================================
def channel_snr(frame_t0: np.ndarray, roi: Roi, um: float) -> List[float]:
    """Signal-to-noise of each channel in the ROI at t0 (manual._snr: inside mean
    minus the 25th percentile of a 3 um ring, over the image's pixel noise)."""
    st = np.asarray(frame_t0)
    return [float(MN._snr(st[c], roi, um)) for c in range(st.shape[0])]


def _mv_txt(v: float) -> str:
    return f"{v:g} µm"


def alternatives(k: int, comp: str, current_rule: Optional[TrackRule], exp, cells,
                 frame_t0: np.ndarray, settings: Optional[dict] = None, gate_snr: float = 5.0,
                 first_ring: int = FIRST_RING, snr: Optional[Sequence[float]] = None
                 ) -> List[Candidate]:
    """
    The ideas to try for cell k's compartment, ranked by how likely they are to
    help (a-priori): "now" first; then the first ring (about first_ring ideas);
    the rest are ring 2 ("Try more"). settings: the current size_tol /
    max_move_um (and the cell's own override settings if it has any).
    """
    ch = list(exp.channels)
    C = len(ch)
    um = float(exp.um_per_px)
    s = dict(settings or {})
    tol = float(s.get("size_tol", 0.25))
    mv = float(s.get("max_move_um", 3.0))
    roi = cells[k][comp]
    snr = list(snr) if snr is not None else channel_snr(frame_t0, roi, um)
    cur = current_rule if current_rule is not None else TrackRule(
        comp, int(min(max(getattr(roi, "channel", 0), 0), C - 1)))
    now = Candidate("now", None, {}, "The tracking as it is now.", 1e9, 0, True)
    sig = [c for c in sorted(range(C), key=lambda c: -snr[c]) if snr[c] >= gate_snr]
    lg = [math.log(max(v, 1.0)) for v in snr]
    out: List[Candidate] = []

    def add(label, rule, st, why, prior, ring=1):
        out.append(Candidate(label, rule, dict(st), why, prior, ring))

    for a in sig:
        A = _name(ch, a)
        add(f"{A} only", TrackRule(comp, a), {},
            f"Follow it on {A} alone ({A} shows this cell {snr[a]:.0f}× above the noise).",
            lg[a])
        for h in sig:
            if h == a:
                continue
            H = _name(ch, h)
            add(f"{A} with {H} helping", TrackRule(comp, a, HELP, -1, (h,)), {},
                f"Follow it on {A}, with {H} helping where {A} is weak (the outline stays "
                f"within 1 µm of the {A} outline).", lg[a] + 0.3 * lg[h] - 0.15)
            add(f"{A} AND {H}", TrackRule(comp, a, "and", h), {},
                f"Follow it on {A}; measure only the pixels also bright in {H}.",
                lg[a] + 0.2 * lg[h] - 0.6, 2)
            add(f"{A} WITH {H}", TrackRule(comp, a, "with", h), {},
                f"Follow it on {A}; keep the pixels where {A} and {H} together are bright.",
                lg[a] + 0.2 * lg[h] - 0.5, 2)
    # size / move limits, on the current rule if its channel shows the cell, else the best
    a_cur = int(cur.a)
    base = None if (a_cur in sig or not sig) else TrackRule(comp, sig[0])
    base_txt = "" if base is None else f"{_name(ch, sig[0])} only, "
    bprior = (lg[a_cur] if base is None else lg[sig[0]]) - 0.4
    for t in SIZE_TOLS:
        if abs(t - tol) < 1e-9:
            continue
        word = "tighter" if t < tol else "looser"
        add(f"{base_txt}{word} size (±{t:.0%})", base, {"size_tol": t},
            f"Keep its size within {t:.0%} of what you drew (now {tol:.0%}).",
            bprior - (0.1 if t > tol else 0.0), 1 if t != SIZE_TOLS[-1] or tol < 0.3 else 2)
    for m in MAX_MOVES:
        if abs(m - mv) < 1e-9:
            continue
        word = "allow bigger moves" if m > mv else "smaller moves only"
        add(f"{base_txt}{word} ({_mv_txt(m)})", base, {"max_move_um": m},
            f"Let it move up to {_mv_txt(m)} per timepoint (now {_mv_txt(mv)}).",
            bprior - (0.05 if m > mv else 0.2), 1 if m > mv else 2)
    # no duplicates of the current tracking or of each other
    cur_key = Candidate("", cur, {}).key(ch)
    seen = {cur_key, Candidate("", None, {}).key(ch)}
    uniq = []
    for c in sorted(out, key=lambda c: (c.ring, -c.prior)):
        kk = c.key(ch)
        eff = Candidate("", c.rule if c.rule is not None else cur, c.settings).key(ch)
        if kk in seen or eff in seen:
            continue
        seen.update({kk, eff})
        uniq.append(c)
    first = [c for c in uniq if c.ring == 1][:first_ring]
    rest = [c for c in uniq if c not in first]
    for c in rest:
        c.ring = 2
    return [now] + first + rest


# ==========================================================================
#  Running them
# ==========================================================================
def stability(rois: Sequence[Roi], quality: np.ndarray, mean_main: np.ndarray, seed: Roi,
              t0: int, um: float, max_move_um: float) -> Tuple[float, str, List[str]]:
    """(score 0-100, grade, plain reasons) of one cell's tracking: how often the
    outline was redrawn (not only moved), how steady its size is, jumps bigger
    than the allowed move, how well t0 matches what was drawn, timepoints with
    nothing measured."""
    T = len(rois)
    area = np.array([float(MN._shape(r).sum()) for r in rois])
    q = np.asarray(quality, float)
    redrawn = float(np.mean(q >= 0.9)) if T else 0.0
    ok = area > 0
    cv = float(np.std(area[ok]) / max(np.mean(area[ok]), 1.0)) if ok.any() else 1.0
    cen = np.array([_centroid(r) for r in rois])
    step = np.hypot(*np.diff(cen, axis=0).T) * um if T > 1 else np.zeros(0)
    jumps = int(np.sum(step > max_move_um + 1e-6))
    nan = int(np.sum(~np.isfinite(np.asarray(mean_main, float))))
    iou = _iou(rois[t0], MN._region(seed)) if 0 <= t0 < T else 0.0
    score = 100.0
    score -= 45.0 * (1.0 - redrawn)
    score -= min(25.0, 100.0 * cv)
    score -= min(20.0, 40.0 * jumps / max(T - 1, 1))
    score -= 25.0 * (1.0 - iou)
    score -= min(30.0, 60.0 * nan / max(T, 1))
    score = float(max(0.0, min(100.0, score)))
    grade = "good" if score >= GOOD else "ok" if score >= OK else "poor"
    why = [f"outline redrawn at {redrawn:.0%} of timepoints"
           + ("" if redrawn >= 0.95 else " (the rest: only moved along)"),
           f"size varies {cv:.0%}" + (" (steady)" if cv < 0.08 else ""),
           ("no jumps" if not jumps else
            f"jumps more than {max_move_um:g} µm at {jumps} timepoint{'s' if jumps != 1 else ''}"),
           f"matches what you drew {iou:.0%}"]
    if nan:
        why.append(f"nothing measured at {nan} timepoint{'s' if nan != 1 else ''}")
    return score, grade, why


def _centroid(r: Roi) -> Tuple[float, float]:
    m = MN._shape(r)
    if not m.any():
        return (float("nan"), float("nan"))
    ys, xs = np.nonzero(m)
    return float(ys.mean() + r.bbox[0]), float(xs.mean() + r.bbox[1])


def _iou(a: Roi, b: Roi) -> float:
    A, B = MN._shape(a), MN._shape(b)
    inter = MN._overlap_px(Roi(a.bbox, A, "x"), Roi(b.bbox, B, "x"))
    union = int(A.sum()) + int(B.sum()) - inter
    return float(inter) / union if union else 0.0


def choice_overrides(overrides: Optional[dict], k: int, comp: str, cand: Candidate) -> dict:
    """The per-cell overrides with this candidate chosen for cell k's compartment
    ("now": unchanged). Pass them to retrack_cells / track_cells."""
    ov = dict(overrides or {})
    if cand.current:
        return ov
    entry = {"rule": cand.rule, "settings": dict(cand.settings),
             "why": "chosen in the ROI troubleshooter"}
    old = ov.get((comp, int(k)))
    if cand.rule is None and old and old.get("rule") is not None:
        entry["rule"] = old["rule"]               # a settings idea on its own rule
    ov[(comp, int(k))] = entry
    return ov


def neighbourhood(previous_out: dict, k: int, comp: str, cells, um: float, H: int, W: int,
                  max_move_um: float = max(MAX_MOVES), extra_um: float = 12.0) -> tuple:
    """The box (y0, x0, y1, x1) around cell k over the whole movie that the
    candidates can need (read once into a CropCache)."""
    boxes = [cells[k][c].bbox for c in cells[k]]
    for c, g in (previous_out.get("rois") or {}).items():
        if c in cells[k] and k < len(g[0]):
            boxes += [g[t][k].bbox for t in range(len(g)) if g[t][k].area]
    b = np.array(boxes)
    margin = int(max(MN.MARGIN_MIN_PX, round(MN._px(max_move_um, um))))
    big = max(float(MN._region(r).area) for r in cells[k].values())
    pad = MN.pair_pad(margin, big, um, "mito", True) + int(MN._px(extra_um, um))
    return (max(0, int(b[:, 0].min()) - pad), max(0, int(b[:, 1].min()) - pad),
            min(H, int(b[:, 2].max()) + pad), min(W, int(b[:, 3].max()) + pad))


def result_of(out: dict, cand: Candidate, k: int, comp: str, seed: Roi, t0: int, um: float,
              main: int, max_move_um: float) -> CandidateResult:
    M = out["meas"][comp]
    rois = [out["rois"][comp][t][k] for t in range(M.mean.shape[0])]
    q = np.asarray(out.get("track_q", {}).get(comp, M.quality))[:, k] \
        if out.get("track_q") else np.asarray(M.quality)[:, k]
    sc, gr, why = stability(rois, q, M.mean[:, main, k], seed, t0, um, max_move_um)
    return CandidateResult(cand, rois, np.asarray(M.mean[:, :, k]), q,
                           np.asarray(M.area_px[:, k]), sc, gr, why, out)


def run_candidates(src, exp, cells, background, t0: int, previous_out: dict, k: int, comp: str,
                   candidates: Sequence[Candidate], track_kw: dict,
                   overrides: Optional[dict] = None, progress=None,
                   cancel: Optional[threading.Event] = None, workers: int = 3,
                   cache: Optional[RT.CropCache] = None) -> Iterator[CandidateResult]:
    """
    Run every candidate for cell k's compartment only (the other cells replayed
    as they were) and yield each result AS IT FINISHES ("now" first, at once:
    it is previous_out). track_kw: the track_cells settings (max_move_um,
    mito_k, sat_level, lead, size_tol, rules, gate_snr, overlap_k, boundaries).
    cancel: set it to stop (results already yielded stay). progress(f, msg)
    -> False also stops. The cell's neighbourhood is read once (CropCache).
    """
    cancel = cancel or threading.Event()
    um = float(exp.um_per_px)
    seed = cells[k][comp]
    mv0 = float(track_kw.get("max_move_um", 3.0))
    rule0 = (track_kw.get("rules") or {}).get(comp)
    main = int(getattr(rule0, "a", getattr(seed, "channel", 0)) or 0)
    for cand in candidates:
        if cand.current:
            r = result_of(previous_out, cand, k, comp, seed, t0, um, main, mv0)
            yield r
    todo = [c for c in candidates if not c.current]
    if not todo:
        return
    if cache is None:
        box = neighbourhood(previous_out, k, comp, cells, um, exp.height, exp.width)
        cache = RT.CropCache(src, box, exp.n_timepoints)

        def pr(f, m):
            if cancel.is_set():
                return False
            return progress(0.25 * f, m) if progress else True
        cache.fill(pr)
    done = [0]
    lock = threading.Lock()
    per = {}
    norm = RT._norm_from(previous_out, list(exp.channels))
    if norm is None and any(c.rule is not None and c.rule.effective_mode() != "only"
                            for c in todo):
        from .rules import make_norm
        norm = make_norm(np.asarray(src.frame(int(t0))))   # once, for every idea

    def one(cand: Candidate) -> CandidateResult:
        t_s = time.time()
        ov = choice_overrides(overrides, k, comp, cand)

        def pr(f, m, key=id(cand)):
            if cancel.is_set():
                return False
            with lock:
                per[key] = f
                tot = sum(per.values()) / len(todo)
            if progress:
                return progress(0.25 + 0.75 * tot, f"Trying {len(todo)} ways for cell {k + 1}"
                                                    f"\n{done[0]} of {len(todo)} done")
            return True
        kw = dict(track_kw)
        kw["overrides"] = ov
        out = RT.retrack_cells(src, exp, cells, background, t0, previous_out, {comp: [k]},
                               progress=pr, propagate=False, cache=cache, norm=norm, **kw)
        r = result_of(out, cand, k, comp, seed, t0, um,
                      int(cand.rule.a) if cand.rule is not None else main,
                      float(cand.settings.get("max_move_um", mv0)))
        r.seconds = round(time.time() - t_s, 2)
        return r

    pool = ThreadPoolExecutor(max_workers=max(1, int(workers)))
    try:
        futs = {pool.submit(one, c): c for c in todo}
        for f in as_completed(futs):
            if cancel.is_set():
                break
            try:
                r = f.result()
            except MN.Cancelled:
                break
            except Exception as exc:                       # noqa: BLE001
                c = futs[f]
                r = CandidateResult(c, [], np.zeros((0, 0)), np.zeros(0), np.zeros(0),
                                    0.0, "poor", ["it could not be tracked this way"],
                                    error=str(exc))
            with lock:
                done[0] += 1
            yield r
    finally:
        cancel.set() if cancel.is_set() else None
        pool.shutdown(wait=True, cancel_futures=True)


def ranked(results: Sequence[CandidateResult]) -> List[CandidateResult]:
    """Best first (score; on a tie the tracking as it is now first)."""
    return sorted(results, key=lambda r: (-r.score, not r.candidate.current))
