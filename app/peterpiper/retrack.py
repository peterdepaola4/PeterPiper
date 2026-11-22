"""
PeterPiper 4.0: re-track only what changed.

Tracking a whole movie (every cell, every timepoint, every compartment, every
channel) is slow on big files. After a small change - one ROI moved, redrawn,
added or removed, one cell's boundary line, one compartment's rule, the
background - only part of the result is out of date. This module finds that
part and recomputes it, so the answer is EXACTLY (bit for bit) what a full
TRACK & MEASURE with the same inputs gives.

    snapshot(...)        what the tracking depends on, kept with a result
    plan(old, new)       what a change between two snapshots needs:
                         {"retrack": {comp: [cells]}, "background": bool,
                          "drop": [cells], "drop_pairs": {comp: [cells]},
                          "full": bool, "why": text}
    retrack_cells(...)   a new result with only those columns recomputed
    remeasure_background(...)   a new background (no re-tracking)

Why it is exact. Cells are NOT independent in the tracker: a cell's outline
may not take pixels nearer a neighbour (same compartment), never takes another
cell's nucleus (other compartments), two cells' regions never share a pixel
(the lower cell number keeps them), and a cytoplasm is its cell minus its own
nucleus; each cell's move is measured on its first ('Follow') compartment. So
the re-track runs the tracker itself for the chosen (compartment, cell) pairs
while every other pair is REPLAYED from the earlier result frame by frame (its
outline, its move, its quality) - the re-tracked cells see their neighbours
exactly as a full run would. Afterwards every pair whose outline / move /
quality came out different is compared with the replayed pairs near it (at
that timepoint, within the distance the tracker looks); any replayed pair a
change could have reached is re-tracked too, and so on until nothing new is
reached (usually one or two passes). The background is not affected by the
cells (every pixel of its region is used); only its "ROIs cover x %" note is
recounted.

Speed. Only the pixels the re-tracked cells need are read: each frame is an
empty (zero) image with those parts filled in from the file (nd2io crop(),
memory-mapped) - a part the tracker turns out to need that was not read yet is
read on the spot before it is used (SparseFrames.ensure), so a guess that was
too small costs time, never correctness.
"""
from __future__ import annotations

import hashlib
import time
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import numpy as np

from . import manual as MN
from .measure import Measurements
from .segment import Roi

COMPS = MN.COMPS
Pair = Tuple[str, int]
TRACK_SETTINGS = ("max_move_um", "mito_k", "size_tol", "overlap_k", "sat_level")
SLACK_UM = 4.0               # the first guess of what to read: + this around the parts needed
MAX_PASSES = 6               # after this many passes the rest is simply re-tracked in full


# ==========================================================================
#  Snapshots and the plan
# ==========================================================================
def roi_fp(r: Optional[Roi]) -> Optional[str]:
    """A fingerprint of an ROI (where it is, its pixels, its outline, its channel)."""
    if r is None:
        return None
    h = hashlib.sha1()
    h.update(np.asarray(r.bbox, np.int64).tobytes())
    h.update(np.packbits(np.asarray(r.mask, bool)).tobytes())
    h.update(str(np.asarray(r.mask).shape).encode())
    o = getattr(r, "outline", None)
    if o is not None:
        h.update(b"o" + np.packbits(np.asarray(o, bool)).tobytes())
    h.update(str(getattr(r, "channel", 0)).encode())
    return h.hexdigest()


def _rule_fp(r, channels: Sequence[str]):
    if r is None:
        return None
    if hasattr(r, "to_dict"):
        return tuple(sorted((k, tuple(v) if isinstance(v, list) else v)
                            for k, v in r.to_dict(channels).items()))
    if isinstance(r, dict):
        return tuple(sorted((k, tuple(v) if isinstance(v, list) else v) for k, v in r.items()))
    return str(r)


def snapshot(cells: Sequence[Dict[str, Roi]], rules, background: Optional[Roi], t0: int,
             channels: Sequence[str], settings: Optional[dict] = None,
             boundaries: Optional[dict] = None, overrides: Optional[dict] = None,
             lead: Sequence[str] = COMPS, n_timepoints: Optional[int] = None) -> dict:
    """What a tracking result depends on, as small fingerprints (no image data):
    keep it next to the result (clickwin: when tracking finishes) and compare it
    with the current one (plan) after a change. settings: max_move_um, mito_k,
    size_tol, overlap_k, sat_level (gate_snr only decides IF exclusions)."""
    from . import rules as RL
    ch = list(channels)
    ovs = RL.complete_overrides(overrides, ch) if overrides else {}
    return dict(
        cells=[{c: roi_fp(r) for c, r in (cell or {}).items()} for cell in cells],
        rules=None if rules is None else {c: _rule_fp(r, ch) for c, r in dict(rules).items()},
        background=roi_fp(background), t0=int(t0), channels=tuple(ch),
        settings={k: float(v) for k, v in (settings or {}).items() if k in TRACK_SETTINGS},
        gate_snr=float((settings or {}).get("gate_snr", 5.0)),
        boundaries={int(k): repr([[tuple(map(float, p)) for p in ln] for ln in v])
                    for k, v in (boundaries or {}).items() if v},
        overrides={f"{c}:{k}": (_rule_fp(o.get("rule"), ch), tuple(sorted(o["settings"].items())))
                   for (c, k), o in ovs.items()},
        lead=tuple(lead), n_timepoints=n_timepoints)


def _anchor(cell: dict, lead: Sequence[str]) -> Optional[str]:
    return next((c for c in list(lead) + list(COMPS) if c in cell), None)


def plan(old: Optional[dict], new: dict) -> dict:
    """
    What has to be recomputed to bring a result tracked with snapshot `old` up
    to snapshot `new`:
      full        t0, a tracking setting, the channels or the 'Follow' order
                  changed (or there is no earlier result): track everything;
      retrack     {comp: [cell indices]} - ROI moved / redrawn / added, a cell's
                  boundary lines or its own override changed: that cell (all its
                  compartments when its first 'Follow' compartment - the one its
                  move is measured on - changed; its cytoplasm when its nucleus
                  changed); a compartment's rule changed: that compartment of
                  every cell (and every compartment of cells it moves);
      drop        cells that lost every ROI; drop_pairs {comp: [cells]} every
                  compartment ROI removed (their columns become empty);
      background  the background region changed: re-measure it only;
      regate      the IF threshold changed: only the IF exclusions are redone.
    Neighbours a change can reach are found while re-tracking (retrack_cells).
    """
    res = dict(retrack={}, background=False, drop=[], drop_pairs={}, full=False, why="",
               regate=False)
    if old is None:
        res.update(full=True, why="not tracked yet")
        return res
    for key, why in (("t0", "the drawn timepoint changed"),
                     ("settings", "a tracking setting changed"),
                     ("channels", "the channels changed"),
                     ("lead", "the order of the compartments followed changed"),
                     ("n_timepoints", "the number of timepoints changed")):
        if old.get(key) != new.get(key):
            res.update(full=True, why=why)
            return res
    if (old.get("rules") is None) != (new.get("rules") is None):
        res.update(full=True, why="tracking rules were switched on / off")
        return res
    res["regate"] = old.get("gate_snr") != new.get("gate_snr")
    res["background"] = old.get("background") != new.get("background")
    lead = list(new.get("lead") or COMPS)
    oc, nc = list(old.get("cells") or []), list(new.get("cells") or [])
    todo: Set[Pair] = set()
    drop_pairs: Set[Pair] = set()

    def whole(k: int) -> None:
        for c in nc[k]:
            todo.add((c, k))

    for k in range(max(len(oc), len(nc))):
        a = oc[k] if k < len(oc) else {}
        b = nc[k] if k < len(nc) else {}
        for c in set(a) - set(b):
            drop_pairs.add((c, k))
        if not b:
            continue
        changed = {c for c in b if a.get(c) != b.get(c)}
        if _anchor(a, lead) != _anchor(b, lead) or _anchor(b, lead) in changed:
            whole(k)                          # its move is measured on another / a new ROI
        todo.update((c, k) for c in changed)
        if ("nucleus" in changed or ("nucleus" in a) != ("nucleus" in b)) and "cytoplasm" in b:
            todo.add(("cytoplasm", k))        # the cytoplasm is its cell minus its nucleus
        ob = (old.get("boundaries") or {}).get(k)
        if ob != (new.get("boundaries") or {}).get(k):
            whole(k)
    orules, nrules = old.get("rules") or {}, new.get("rules") or {}
    for c in set(orules) | set(nrules):
        if orules.get(c) != nrules.get(c):
            for k, b in enumerate(nc):
                if c in b:
                    todo.add((c, k))
                    if _anchor(b, lead) == c:
                        whole(k)
    oo, no = old.get("overrides") or {}, new.get("overrides") or {}
    for key in set(oo) | set(no):
        if oo.get(key) != no.get(key):
            c, k = key.split(":")
            k = int(k)
            if k < len(nc) and c in nc[k]:
                todo.add((c, k))
                if _anchor(nc[k], lead) == c:
                    whole(k)
    rt: Dict[str, List[int]] = {}
    for c, k in sorted(todo, key=lambda p: (p[1], COMPS.index(p[0]))):
        rt.setdefault(c, []).append(k)
    dp: Dict[str, List[int]] = {}
    for c, k in sorted(drop_pairs, key=lambda p: (p[1], COMPS.index(p[0]))):
        dp.setdefault(c, []).append(k)
    res["retrack"], res["drop_pairs"] = rt, dp
    res["drop"] = sorted({k for _c, k in drop_pairs if k >= len(nc) or not nc[k]})
    bits = []
    if rt:
        bits.append(f"re-track {sum(len(v) for v in rt.values())} ROI(s)")
    if dp:
        bits.append(f"remove {sum(len(v) for v in dp.values())} ROI(s)")
    if res["background"]:
        bits.append("re-measure the background")
    res["why"] = ", ".join(bits) or "nothing changed"
    return res


def nothing_to_do(p: dict) -> bool:
    return not (p.get("full") or p.get("retrack") or p.get("drop_pairs") or p.get("background"))


# ==========================================================================
#  Reading only what is needed
# ==========================================================================
class SparseFrames:
    """
    Frames for a re-track: full-size images that are zero except the parts read
    from the file (src.crop). guess(t) gives the parts to read first (a list of
    (y0, x0, y1, x1)); ensure() reads any further part the tracker needs before
    it uses it. Counts what was read (px_read, reads).
    """
    sparse = True

    def __init__(self, src, exp, guess=None, cache=None) -> None:
        self.src, self.exp = src, exp
        self.H, self.W, self.C = int(exp.height), int(exp.width), int(exp.n_channels)
        self.guess = guess or (lambda t: [])
        self.cache = cache                       # CropCache (shared by troubleshooter runs)
        self.dtype = None
        self._cov: Dict[int, List[tuple]] = {}
        self._ver: Dict[int, int] = {}
        self._t: Dict[int, int] = {}
        self.px_read = 0
        self.reads = 0
        self.misses = 0
        import threading
        self._lock = threading.Lock()

    def _read(self, t: int, box) -> np.ndarray:
        y0, x0, y1, x1 = box
        if self.cache is not None:
            a = self.cache.crop(t, y0, y1, x0, x1)
        else:
            a = np.asarray(self.src.crop(t, y0, y1, x0, x1))
        with self._lock:
            self.px_read += int(a.size)
            self.reads += 1
        return a

    def _clip(self, box):
        y0, x0, y1, x1 = (int(v) for v in box)
        return max(0, y0), max(0, x0), min(self.H, y1), min(self.W, x1)

    def get(self, t: int) -> np.ndarray:
        t = int(t)
        boxes = merge_boxes([self._clip(b) for b in self.guess(t)])
        parts = [(b, self._read(t, b)) for b in boxes if b[2] > b[0] and b[3] > b[1]]
        dt = parts[0][1].dtype if parts else (self.dtype or np.uint16)
        if self.dtype is None:
            self.dtype = dt
        arr = np.zeros((self.C, self.H, self.W), dt)
        for (y0, x0, y1, x1), a in parts:
            arr[:, y0:y1, x0:x1] = a
        with self._lock:
            self._cov[id(arr)] = [b for b, _a in parts]
            self._ver[id(arr)] = 0
            self._t[id(arr)] = t
        return arr

    def ensure(self, arr: np.ndarray, box) -> None:
        b = self._clip(box)
        if b[2] <= b[0] or b[3] <= b[1]:
            return
        cov = self._cov.get(id(arr))
        if cov is None:                           # not one of ours: a whole frame
            return
        if any(c[0] <= b[0] and c[1] <= b[1] and c[2] >= b[2] and c[3] >= b[3] for c in cov):
            return
        a = self._read(self._t[id(arr)], b)
        arr[:, b[0]:b[2], b[1]:b[3]] = a
        cov.append(b)
        self._ver[id(arr)] += 1
        self.misses += 1

    def version(self, arr: np.ndarray) -> int:
        return self._ver.get(id(arr), 0)


def merge_boxes(boxes: Iterable[tuple]) -> List[tuple]:
    """Overlapping (or nearly touching) boxes joined into their bounding boxes."""
    out = [tuple(int(v) for v in b) for b in boxes if b[2] > b[0] and b[3] > b[1]]
    changed = True
    while changed and len(out) > 1:
        changed = False
        res: List[tuple] = []
        for b in out:
            for i, r in enumerate(res):
                if b[0] <= r[2] + 8 and r[0] <= b[2] + 8 and b[1] <= r[3] + 8 and r[1] <= b[3] + 8:
                    res[i] = (min(b[0], r[0]), min(b[1], r[1]), max(b[2], r[2]), max(b[3], r[3]))
                    changed = True
                    break
            else:
                res.append(b)
        out = res
    return out


class CropCache:
    """Parts of frames kept in memory (the troubleshooter runs one cell many
    ways: its neighbourhood is read from the file once). crop() answers from
    memory when the part is inside what is kept, else reads the file."""

    def __init__(self, src, box, T: int) -> None:
        self.src, self.box, self.T = src, tuple(int(v) for v in box), int(T)
        self.frames: Dict[int, np.ndarray] = {}
        import threading
        self._lock = threading.Lock()

    def fill(self, progress=None) -> None:
        y0, x0, y1, x1 = self.box
        for t in range(self.T):
            if t not in self.frames:
                self.frames[t] = np.asarray(_crop(self.src, t, y0, y1, x0, x1))
            if progress and not progress((t + 1) / self.T, "Reading the cell's neighbourhood"):
                raise MN.Cancelled()

    def crop(self, t: int, y0: int, y1: int, x0: int, x1: int) -> np.ndarray:
        by0, bx0, by1, bx1 = self.box
        if by0 <= y0 and bx0 <= x0 and y1 <= by1 and x1 <= bx1:
            with self._lock:
                a = self.frames.get(int(t))
            if a is None:
                a = np.asarray(_crop(self.src, t, by0, by1, bx0, bx1))
                with self._lock:
                    self.frames[int(t)] = a
            return a[:, y0 - by0:y1 - by0, x0 - bx0:x1 - bx0]
        return np.asarray(_crop(self.src, t, y0, y1, x0, x1))


def _crop(src, t, y0, y1, x0, x1) -> np.ndarray:
    if hasattr(src, "crop"):
        return src.crop(int(t), int(y0), int(y1), int(x0), int(x1))
    return np.ascontiguousarray(np.asarray(src.frame(int(t)))[:, y0:y1, x0:x1])


# ==========================================================================
#  Replaying an earlier result
# ==========================================================================
def replayable(out: Optional[dict], T: int) -> bool:
    """Can `out` be replayed (made by the 4.0 tracker, same number of timepoints)?"""
    if not out or "shifts" not in out or "track_q" not in out:
        return False
    sh = np.asarray(out["shifts"])
    return sh.ndim == 3 and sh.shape[0] == T and all(
        len(g) == T for g in (out.get("rois") or {}).values())


def live_pairs(out: dict) -> Set[Pair]:
    """The (compartment, cell) pairs tracked in a result."""
    res = set()
    for c, q in (out.get("track_q") or {}).items():
        q = np.asarray(q)
        for k in np.nonzero((q > 0).any(axis=0))[0]:
            res.add((c, int(k)))
    return res


class _Replay:
    """What the tracker needs to replay the pairs it does not re-track."""

    def __init__(self, prev: dict, active: Set[Pair], frames, norm, n_pass: int) -> None:
        self.prev, self.active, self.frames, self.norm = prev, active, frames, norm
        self.n_pass = n_pass
        self._reg: Dict[tuple, Roi] = {}

    def region(self, c: str, t: int, k: int) -> Roi:
        key = (c, t, k)
        r = self._reg.get(key)
        if r is None:
            s = self.prev["rois"][c][t][k]
            r = Roi(tuple(int(v) for v in s.bbox), MN._shape(s), c, True, "manual")
            r.channel = getattr(s, "channel", 0)
            self._reg[key] = r
        return r

    def followed(self, c: str, t: int, k: int) -> Roi:
        return self.region(c, t, k)

    def quality(self, c: str, t: int, k: int) -> float:
        return float(self.prev["track_q"][c][t, k])

    def shift(self, t: int, k: int) -> Tuple[int, int]:
        s = self.prev["shifts"][t, k]
        return int(s[0]), int(s[1])

    def message(self, done: int, T: int) -> str:
        n = len({k for _c, k in self.active})
        return (f"Re-tracking {n} cell{'s' if n != 1 else ''} (only what changed)"
                f"\ntimepoint {done} of {T}" + (f" - check {self.n_pass}" if self.n_pass > 1
                                                 else ""))


def _norm_from(prev: Optional[dict], channels: Sequence[str]):
    """The channel scaling (rules.GuideNorm) recorded in an earlier result, or None."""
    from .rules import GuideNorm
    d = ((prev or {}).get("params") or {}).get("norm")
    if not isinstance(d, dict) or list(d) != list(channels):
        return None
    try:
        return GuideNorm(bg=np.array([float(d[c]["bg"]) for c in channels]),
                         top=np.array([float(d[c]["top"]) for c in channels]),
                         noise=np.array([float(d[c]["noise"]) for c in channels]))
    except (KeyError, TypeError, ValueError):
        return None


def _boxes(out: dict, c: str, T: int, N: int, live: Set[Pair]) -> np.ndarray:
    """(T, N, 4) bbox of every tracked ROI of compartment c (-1 where none)."""
    b = np.full((T, N, 4), -1, np.int64)
    g = (out.get("rois") or {}).get(c)
    if g is None:
        return b
    for k in range(min(N, len(g[0]) if g else 0)):
        if (c, k) not in live:
            continue
        for t in range(T):
            b[t, k] = g[t][k].bbox
    return b


# ==========================================================================
#  Re-tracking
# ==========================================================================
def retrack_cells(src, exp, cells: Sequence[Dict[str, Roi]], background: Roi, t0: int,
                  previous_out: dict, which: Optional[Dict[str, Sequence[int]]] = None,
                  max_move_um: float = 3.0, mito_k: float = 3.0, sat_level: int = 65535,
                  lead: Sequence[str] = COMPS, progress=None, size_tol: float = 0.25,
                  rules=None, gate_snr: float = 5.0, overlap_k: float = 3.0,
                  boundaries: Optional[dict] = None, overrides: Optional[dict] = None,
                  background_changed: bool = False, propagate: bool = True,
                  cache: Optional[CropCache] = None, norm=None) -> dict:
    """
    The tracking result for these inputs (the same arguments as
    manual.track_cells), recomputing only the (compartment, cell) pairs in
    `which` ({comp: [cell indices]}, from plan()["retrack"]) plus every pair
    that is new, removed, or reached by a change (propagate=True; False: the
    chosen pairs only, replaying everything else - the troubleshooter's
    previews). Everything else is copied from previous_out, which must be the
    result of the same inputs before the change (made by the 4.0 tracker - else
    the whole movie is tracked, which gives the same numbers).
    background_changed: also re-measure the background region (remeasure_background).
    cache: a CropCache to read from (troubleshooter); norm: the channel scaling of
    the drawn frame (rules.make_norm) if already known.
    Returns the new result dict (as track_cells), with out["retrack"] = {passes,
    pairs (re-tracked), seconds, px_read (pixels read), full (bool)}.
    """
    t_start = time.time()
    T, C, N = exp.n_timepoints, exp.n_channels, len(cells)
    um = exp.um_per_px
    kw = dict(max_move_um=max_move_um, mito_k=mito_k, sat_level=sat_level, lead=lead,
              size_tol=size_tol, rules=rules, gate_snr=gate_snr, overlap_k=overlap_k,
              boundaries=boundaries, overrides=overrides)
    if not replayable(previous_out, T):
        out = MN.track_cells(src, exp, cells, background, t0, progress=progress, **kw)
        out["retrack"] = dict(passes=1, pairs=None, seconds=round(time.time() - t_start, 3),
                              px_read=None, full=True,
                              why="the earlier result cannot be replayed - tracked in full")
        return out
    prev = previous_out
    prev_live = live_pairs(prev)
    new_pairs = {(c, k) for k, cell in enumerate(cells) for c in cell}
    dropped = {p for p in prev_live if p not in new_pairs}
    active: Set[Pair] = {(c, int(k)) for c, ks in (which or {}).items() for k in ks
                         if 0 <= int(k) < N and c in cells[int(k)]}
    active |= {p for p in new_pairs if p not in prev_live}
    comps = [c for c in COMPS if any(c in cell for cell in cells)]
    # channel scaling for WITH / AND / IF / helper rules (frozen at the drawn frame)
    norm_given = norm
    norm = None
    from . import rules as RL
    need_norm = False
    if rules is not None or overrides:
        ro = RL.complete_rules(rules, cells, comps, list(exp.channels)) if rules is not None else {}
        ov = RL.complete_overrides(overrides, list(exp.channels), N) if overrides else {}
        need_norm = any(r.effective_mode() != "only" for r in list(ro.values())
                        + [o["rule"] for o in ov.values() if o.get("rule") is not None])
    if need_norm:
        norm = norm_given if norm_given is not None else _norm_from(prev, list(exp.channels))
        if norm is None:
            norm = RL.make_norm(np.asarray(src.frame(int(t0))))
    passes, res, frames_list = 0, None, []
    ctx_extra: Set[int] = set()
    drift = _drift(prev, T, N)
    if propagate and dropped:                     # a removed ROI frees pixels for its neighbours
        active |= _reached(prev, None, set(), dropped, prev_live, cells, T, N, um,
                           kw, lead)
    while True:
        passes += 1
        if not active:
            res = None
            break
        frames = SparseFrames(src, exp, _guess(prev, cells, active, res, drift, um, max_move_um,
                                               size_tol, T), cache) \
            if (hasattr(src, "crop") or cache is not None) else MN._FullFrames(src)
        frames_list.append(frames)
        rp = _Replay(prev, set(active), frames, norm, passes)
        rp.skip = _far(prev, cells, active, None, T, N, um, kw, extra=ctx_extra)
        res = MN.track_cells(src, exp, cells, background, t0, progress=progress, _replay=rp, **kw)
        near = rp.skip - _far(prev, cells, active, res, T, N, um, kw)
        if near:                                  # a re-tracked ROI went near a cell left
            ctx_extra |= near                     # out: track again with it as context
            continue
        if not propagate:
            break
        more = _reached(prev, res, active, dropped, prev_live, cells, T, N, um,
                        kw, lead) | set(res["disturbed"])
        more -= active
        if not more:
            break
        active |= more
        if passes >= MAX_PASSES:                  # (never seen) - simply re-track it all
            active |= new_pairs
    out = _merge(prev, res, cells, active if res is not None else set(), dropped, exp,
                 background, t0, kw, norm, comps)
    if background_changed:
        out = remeasure_background(src, exp, out, background, progress=progress)
    out["retrack"] = dict(passes=passes, pairs=sorted(active, key=lambda p: (p[1], p[0])),
                          seconds=round(time.time() - t_start, 3),
                          px_read=int(sum(getattr(f, "px_read", 0) for f in frames_list)),
                          reads=int(sum(getattr(f, "reads", 0) for f in frames_list)),
                          misses=int(sum(getattr(f, "misses", 0) for f in frames_list)),
                          full=False)
    return out


def _drift(prev: dict, T: int, N: int) -> np.ndarray:
    """(T, 2) the typical (median) whole-pixel position of a cell relative to t0."""
    sh = np.asarray(prev["shifts"], float)
    t0 = int((prev.get("params") or {}).get("t0", 0))
    pos = np.zeros((T, max(N, 1), 2))
    n = min(N, sh.shape[1])
    if n:
        pos[t0 + 1:, :n] = np.cumsum(sh[t0 + 1:, :n], axis=0)
        if t0 > 0:
            pos[:t0, :n] = np.cumsum(sh[:t0, :n][::-1], axis=0)[::-1]
    return np.median(pos[:, :n], axis=1) if n else np.zeros((T, 2))


def _guess(prev: dict, cells, active: Set[Pair], res: Optional[dict], drift: np.ndarray,
           um: float, max_move_um: float, size_tol: float, T: int):
    """guess(t) -> boxes to read first at timepoint t: around where each re-tracked
    ROI was (earlier result / last pass) and where its seed would have drifted."""
    per_t: List[List[tuple]] = [[] for _ in range(T)]
    margin = int(max(MN.MARGIN_MIN_PX, round(MN._px(max_move_um, um))))
    slack = int(MN._px(SLACK_UM, um))
    t0 = int((prev.get("params") or {}).get("t0", 0))
    for c, k in active:
        seed = cells[k].get(c)
        if seed is None:
            continue
        pad = MN.pair_pad(margin, float(MN._region(seed).area), um, c, True) + slack
        y0, x0, y1, x1 = seed.bbox
        for t in range(T):
            dy, dx = drift[t] - drift[t0]
            bxs = [(y0 + dy, x0 + dx, y1 + dy, x1 + dx)]
            for src_out in (prev, res):
                if src_out is None:
                    continue
                g = (src_out.get("rois") or {}).get(c)
                if g is None or k >= len(g[t]) or g[t][k] is None:
                    continue
                for tt in (t - 1, t):
                    if 0 <= tt < T and g[tt][k] is not None and g[tt][k].area:
                        bxs.append(g[tt][k].bbox)
            for b in bxs:
                per_t[t].append((int(b[0]) - pad, int(b[1]) - pad, int(b[2]) + pad, int(b[3]) + pad))
    merged = [merge_boxes(b) for b in per_t]
    return lambda t: merged[int(t)]


def _far(prev: dict, cells, active: Set[Pair], res: Optional[dict], T: int, N: int, um: float,
         kw: dict, extra: Iterable[int] = ()) -> Set[int]:
    """The cells with nothing re-tracked that are too far from every re-tracked ROI
    to matter to it at any timepoint (the tracker can leave them out). res None:
    judged from where the re-tracked ROIs were (earlier result, seeds) with room
    to spare; with res: from where they are now (exact check, no spare room)."""
    act_cells = {k for _c, k in active}
    m = int(max(MN.MARGIN_MIN_PX, round(MN._px(_max_move(kw, N), um))))
    big = max([float(MN._region(r).area) for cell in cells for r in cell.values()] or [100.0])
    ring_px = int(max(2, MN._px(MN.RING_UM, um)))
    D = 3 * (m + 1) + max(ring_px, int(np.ceil(np.sqrt(big / np.pi))) + m + 2) + 2
    if res is None:
        D += int(MN._px(3 * SLACK_UM, um)) + 3 * (m + 1)
    live = live_pairs(prev)
    # (T, 4) per re-tracked pair: where it is / was
    mine = []
    for c, k in active:
        rows = []
        for src_out in ((prev,) if res is None else (prev, res)):
            if src_out is res or (c, k) in live:
                b = _boxes(src_out, c, T, N, {(c, k)})[:, k]
                rows.append(b)
        seed = cells[k].get(c)
        if seed is not None and res is None:
            rows.append(np.tile(np.asarray(seed.bbox, np.int64), (T, 1)))
        mine.extend(rows)
    if not mine:
        return set()
    A = np.stack(mine)                                  # (P, T, 4)
    okA = A[..., 0] >= 0
    if res is None:                                     # where they were: also any time
        allb = A[okA]
        if allb.size:
            A = np.concatenate([A, np.tile(np.array([allb[:, 0].min(), allb[:, 1].min(),
                                                     allb[:, 2].max(), allb[:, 3].max()]),
                                           (1, T, 1))])
            okA = A[..., 0] >= 0
    out = set()
    extra = set(extra)
    for j, cell in enumerate(cells):
        if j in act_cells or j in extra or not cell:
            continue
        near = False
        for c in cell:
            if (c, j) not in live:
                near = True
                break
            B = _boxes(prev, c, T, N, {(c, j)})[:, j]   # (T, 4)
            Bs = np.stack([B, np.roll(B, 1, 0), np.roll(B, -1, 0)])
            for b in Bs:
                okB = b[:, 0] >= 0
                hit = okA & okB[None] & (A[..., 0] - D < b[None, :, 2]) & \
                    (b[None, :, 0] < A[..., 2] + D) & (A[..., 1] - D < b[None, :, 3]) & \
                    (b[None, :, 1] < A[..., 3] + D)
                if hit.any():
                    near = True
                    break
            if near:
                break
        if not near:
            out.add(j)
    return out


def _max_move(kw: dict, N: int) -> float:
    from . import rules as RL
    mv = [float(kw["max_move_um"])]
    if kw.get("overrides"):
        mv += [float(o["settings"].get("max_move_um", 0.0)) for o in
               RL.complete_overrides(kw.get("overrides"), (), N).values()]
    return max(mv)


def _same(a: Optional[Roi], b: Optional[Roi]) -> bool:
    if a is None or b is None:
        return a is b
    if tuple(a.bbox) != tuple(b.bbox) or a.mask.shape != b.mask.shape:
        return False
    if not np.array_equal(a.mask, b.mask):
        return False
    oa, ob = getattr(a, "outline", None), getattr(b, "outline", None)
    if (oa is None) != (ob is None):
        return False
    return oa is None or np.array_equal(oa, ob)


def _reached(prev: dict, res: dict, active: Set[Pair], dropped: Set[Pair], prev_live: Set[Pair],
             cells, T: int, N: int, um: float, kw: dict, lead) -> Set[Pair]:
    """The replayed pairs a change could have reached (see the module text)."""
    changed: Dict[Pair, np.ndarray] = {}           # pair -> (T,) bool: differs at t
    shift_changed: Set[int] = set()
    for c, k in (active if res is not None else ()):
        d = np.zeros(T, bool)
        if (c, k) not in prev_live:
            d[:] = True
        else:
            for t in range(T):
                if not _same(res["rois"][c][t][k], prev["rois"][c][t][k]) or \
                        float(res["track_q"][c][t, k]) != float(prev["track_q"][c][t, k]):
                    d[t] = True
        if d.any():
            changed[(c, k)] = d
        anc = _anchor(cells[k], lead)
        if anc == c and k < prev["shifts"].shape[1] and \
                not np.array_equal(res["shifts"][:, k], prev["shifts"][:, k]):
            shift_changed.add(k)
    for p in dropped:
        changed[p] = np.ones(T, bool)
    if not changed and not shift_changed:
        return set()
    out: Set[Pair] = set()
    for k in shift_changed:                         # its other compartments move with it
        out |= {(c, k) for c in cells[k]}
    frozen = [(c, j) for j, cell in enumerate(cells) for c in cell if (c, j) not in active]
    if not frozen:
        return out
    # how far a change can reach in one frame (the tracker's windows, see the module text)
    from . import rules as RL
    moves = [float(kw["max_move_um"])] + [float(o["settings"].get("max_move_um", 0.0)) for o in
                                          RL.complete_overrides(kw.get("overrides"), (), N)
                                          .values()] if kw.get("overrides") else         [float(kw["max_move_um"])]
    m = int(max(MN.MARGIN_MIN_PX, round(MN._px(max(moves), um))))
    big = max([float(MN._region(r).area) for cell in cells for r in cell.values()] or [100.0])
    ring_px = int(max(2, MN._px(MN.RING_UM, um)))
    D = 3 * (m + 1) + ring_px + 2                   # its redraw window
    D_trim = 3 * (m + 1) + max(ring_px, int(np.ceil(np.sqrt(big / np.pi))) + m + 2) + 2
    trimmed = prev.get("trimmed") or {}             # ... and its regrow window, where it
                                                    # gave pixels to a neighbour
    comps_all = sorted({c for c, _j in frozen} | {c for c, _k in changed})
    old_b = {c: _boxes(prev, c, T, N, prev_live) for c in comps_all}
    new_b = {c: _boxes(res, c, T, N, active) for c in comps_all} if res is not None else {}

    def spread(b: np.ndarray) -> np.ndarray:
        """(T, 4) union of the boxes at t-1, t, t+1 (rows of -1 = none)."""
        out_b = np.full_like(b, -1)
        for t in range(T):
            rows = [b[tt] for tt in (t - 1, t, t + 1) if 0 <= tt < T and b[tt][0] >= 0]
            if rows:
                r = np.array(rows)
                out_b[t] = (r[:, 0].min(), r[:, 1].min(), r[:, 2].max(), r[:, 3].max())
        return out_b

    fz_spread = {(c, j): spread(old_b[c][:, j]) for c, j in frozen}

    def reach(c2: str, j: int) -> np.ndarray:
        """(T,) how far a change can reach pair (c2, j) at each timepoint."""
        tr = trimmed.get(c2)
        if tr is None or j >= np.asarray(tr).shape[1]:
            return np.full(T, D_trim)
        tr = np.asarray(tr, bool)[:, j]
        sp = tr.copy()
        sp[1:] |= tr[:-1]
        sp[:-1] |= tr[1:]
        return np.where(sp, D_trim, D)

    for (c, k), d in changed.items():
        dd = d.copy()
        dd[1:] |= d[:-1]
        dd[:-1] |= d[1:]
        mine = []
        for bsrc in (old_b, new_b):
            if c in bsrc:
                mine.append(spread(bsrc[c][:, k]))
        for (c2, j) in frozen:
            if (c2, j) in out:
                continue
            if j == k:
                if c == "nucleus" and c2 == "cytoplasm":
                    out.add((c2, j))
                continue
            if not (c2 == c or (c == "nucleus" and c2 != "nucleus")):
                continue
            fb = fz_spread[(c2, j)]
            Dj = reach(c2, j)
            for mb in mine:
                ok = dd & (mb[:, 0] >= 0) & (fb[:, 0] >= 0)
                if not ok.any():
                    continue
                hit = ok & (mb[:, 0] - Dj < fb[:, 2]) & (fb[:, 0] < mb[:, 2] + Dj) & \
                    (mb[:, 1] - Dj < fb[:, 3]) & (fb[:, 1] < mb[:, 3] + Dj)
                if hit.any():
                    out.add((c2, j))
                    break
    return out


def _blank_roi(c: str) -> Roi:
    e = Roi((0, 0, 1, 1), np.zeros((1, 1), bool), c)
    e.include = False
    return e


def _merge(prev: dict, res: Optional[dict], cells, active: Set[Pair], dropped: Set[Pair],
           exp, background: Roi, t0: int, kw: dict, norm, comps: List[str]) -> dict:
    """The new result: earlier columns, re-tracked pairs replaced, removed ones emptied."""
    T, C, N = exp.n_timepoints, exp.n_channels, len(cells)
    um = exp.um_per_px
    Np = int(np.asarray(prev["shifts"]).shape[1])
    n = min(N, Np)
    any_meas = next(iter(prev["meas"].values()), None)
    meas, rois, redrawn, tq_all, trim_all = {}, {}, {}, {}, {}
    for c in comps:
        M = prev["meas"].get(c)
        mean = np.full((T, C, N), np.nan)
        total = np.full((T, C, N), np.nan)
        area = np.zeros((T, N), int)
        nsat = np.zeros((T, C, N), int)
        quality = np.ones((T, N))
        tq = np.zeros((T, N))
        trm = np.zeros((T, N), bool)
        grid = [[None] * N for _ in range(T)]
        if M is not None:
            mean[:, :, :n] = M.mean[:, :, :n]
            if M.sum is not None:
                total[:, :, :n] = M.sum[:, :, :n]
            area[:, :n] = M.area_px[:, :n]
            nsat[:, :, :n] = M.n_saturated[:, :, :n]
            quality[:, :n] = M.quality[:, :n]
            tq[:, :n] = np.asarray(prev["track_q"][c])[:, :n]
            if (prev.get("trimmed") or {}).get(c) is not None:
                trm[:, :n] = np.asarray(prev["trimmed"][c])[:, :n]
            else:
                trm[:, :n] = True                   # not recorded: assume the worst
            for t in range(T):
                grid[t][:n] = prev["rois"][c][t][:n]
        for k in range(N):
            p = (c, k)
            if p in active and res is not None:
                mean[:, :, k] = res["mean"][c][:, :, k]
                total[:, :, k] = res["total"][c][:, :, k]
                area[:, k] = res["area"][c][:, k]
                nsat[:, :, k] = res["nsat"][c][:, :, k]
                q = res["qual"][c][:, k]
                quality[:, k] = np.where(q > 0, q, 1.0)
                tq[:, k] = res["track_q"][c][:, k]
                trm[:, k] = res["trimmed"][c][:, k]
                for t in range(T):
                    grid[t][k] = res["rois"][c][t][k]
            elif p in dropped or c not in cells[k] or k >= n or M is None:
                mean[:, :, k] = np.nan
                total[:, :, k] = np.nan
                area[:, k] = 0
                nsat[:, :, k] = 0
                quality[:, k] = 1.0
                tq[:, k] = 0.0
                trm[:, k] = False
                for t in range(T):
                    grid[t][k] = _blank_roi(c)
        live = [k for k in range(N) if c in cells[k]]
        q = quality[:, live] if live else np.ones((T, 0))
        redrawn[c] = float(np.mean(q >= 0.9)) if q.size else 1.0
        src_m = M if M is not None else any_meas
        meas[c] = Measurements(
            mean=mean, background=src_m.background.copy(), area_px=area, n_saturated=nsat,
            quality=quality, channels=list(exp.channels),
            background_sd=None if src_m.background_sd is None else src_m.background_sd.copy(),
            roi_mode=MN.FILE_NAMES[c], sum=total,
            background_sum=None if src_m.background_sum is None else src_m.background_sum.copy(),
            background_npx=None if src_m.background_npx is None else src_m.background_npx.copy())
        rois[c] = grid
        tq_all[c] = tq
        trim_all[c] = trm
    out = dict(meas=meas, rois=rois, redrawn=redrawn)
    # the tracker's record (as a full run writes it)
    rules = kw.get("rules")
    margin = int(max(MN.MARGIN_MIN_PX, round(MN._px(kw["max_move_um"], um))))
    lines_used = res["lines_used"] if res is not None else _lines_used(kw, exp, cells)
    out["params"] = MN.track_params(comps, um, kw["max_move_um"], margin, kw["size_tol"],
                                    kw["mito_k"], kw["gate_snr"], kw["overlap_k"], t0, norm,
                                    list(exp.channels), rules is not None, lines_used)
    out["background"] = _bg_summary(prev, background, rois, T, C, um)
    out["bg_excluded"] = dict(prev.get("bg_excluded") or {})
    from . import rules as RL
    rule_of = RL.complete_rules(rules, cells, comps, list(exp.channels)) if rules is not None else {}
    ov = RL.complete_overrides(kw.get("overrides"), list(exp.channels), N) \
        if kw.get("overrides") else {}

    def rule_ck(c, k):
        o = ov.get((c, k))
        return o["rule"] if o is not None and o.get("rule") is not None else rule_of.get(c)

    def mode(c, k):
        r = rule_ck(c, k)
        return RL._ab(r, C)[1] if r is not None else None

    if rules is not None:
        out["rules"] = [rule_of[c].to_dict(list(exp.channels)) for c in comps]
    help_comps = [c for c in comps if any(mode(c, k) == "help" for k in range(N) if c in cells[k])
                  or (c in rule_of and RL._ab(rule_of[c], C)[1] == "help")]
    if_comps = [c for c in comps if any(mode(c, k) == "if" for k in range(N) if c in cells[k])
                or (c in rule_of and RL._ab(rule_of[c], C)[1] == "if")]
    # keep the full tracker's order of the IF / helper compartments (COMPS order then extras)
    for key, lst, nm in (("gate", if_comps, "if"), ("helper_snr", help_comps, "help")):
        if not lst:
            continue
        d = {}
        for c in lst:
            d[c] = {}
            for k in range(N):
                if c not in cells[k] or mode(c, k) != nm:
                    continue
                if (c, k) in active and res is not None:
                    v = res[key].get(c, {}).get(k)
                else:
                    v = ((prev.get(key) or {}).get(c) or {}).get(k)
                if v is not None:
                    d[c][k] = v
        out[key] = d
    if help_comps:
        out["params"]["help_weight"] = float(RL.HELP_WEIGHT)
        out["params"]["help_guard_um"] = float(RL.HELP_GUARD_UM)
    shifts = np.zeros((T, N, 2), np.int32)
    shifts[:, :n] = np.asarray(prev["shifts"])[:, :n]
    if res is not None:                           # the re-tracked cells' own moves
        for k in {k for _c, k in active}:
            shifts[:, k] = res["shifts"][:, k]
    for k in range(N):
        if not cells[k]:
            shifts[:, k] = 0
    out["shifts"] = shifts
    out["track_q"] = tq_all
    out["trimmed"] = trim_all
    ov_list = [MN._override_record(o, c, k, list(exp.channels))
               for (c, k), o in sorted(ov.items(), key=lambda kv: (kv[0][1], COMPS.index(kv[0][0])))
               if c in cells[k]]
    if ov_list:
        out["overrides"] = ov_list
        out["params"]["overrides"] = ov_list
    return out


def _lines_used(kw: dict, exp, cells) -> dict:
    """The boundary lines record when nothing was re-tracked (as track_cells writes it)."""
    out = {}
    N = len(cells)
    for k, lines in (kw.get("boundaries") or {}).items():
        try:
            k = int(k)
        except (TypeError, ValueError):
            continue
        if 0 <= k < N and lines and _anchor(cells[k], kw.get("lead") or COMPS) is not None \
            and MN.wall_mask(lines, (exp.height, exp.width)).any():
            out[k] = [[[float(p[0]), float(p[1])] for p in ln] for ln in lines]
    return out


def _bg_summary(prev: dict, background: Roi, rois: dict, T: int, C: int, um: float) -> dict:
    """The earlier background record with the 'measured ROIs cover x %' part recounted."""
    s = dict(prev.get("background") or {})
    meter = MN.BackgroundMeter(background, T, C, um)
    m = meter.mask
    n_reg = int(m.sum())
    fr = []
    for t in range(T):
        mask = meter.roi_mask([g[t][k] for g in rois.values() for k in range(len(g[t]))
                               if g[t][k] is not None])
        fr.append(round(float(int((mask & m).sum())) / max(n_reg, 1), 5))
    s["roi_frac"] = fr
    s["roi_frames"] = [t + 1 for t, f in enumerate(fr) if f > 0]
    s["max_roi_frac"] = round(max(fr, default=0.0), 5)
    return s


def _real(r: Optional[Roi]) -> bool:
    return r is not None and tuple(r.bbox) != (0, 0, 1, 1)


# ==========================================================================
#  The background alone
# ==========================================================================
def remeasure_background(src, exp, previous_out: dict, background: Roi, progress=None) -> dict:
    """
    A result with the background region (re)measured at every timepoint from the
    file - every channel's background mean / SD / sum / pixels in each
    compartment's Measurements (so every background-subtracted value, ratio,
    F/F0 follows) and the background record (overlap note, fluctuation and
    object checks) - with the cells' tracking unchanged. Reads only the
    region's box of each frame. Bit-identical to a full TRACK & MEASURE.
    """
    T, C = exp.n_timepoints, exp.n_channels
    um = exp.um_per_px
    meter = MN.BackgroundMeter(background, T, C, um)
    frames = SparseFrames(src, exp, lambda t: [meter.box])
    rois = previous_out.get("rois") or {}
    for i, t in enumerate(range(T)):
        arr = frames.get(t)
        cur = [g[t][k] for g in rois.values() for k in range(len(g[t])) if g[t][k] is not None]
        meter.add(t, arr, meter.roi_mask(cur))
        del arr
        if progress and not progress((i + 1) / T, f"Measuring the background\ntimepoint "
                                                  f"{t + 1} of {T}"):
            raise MN.Cancelled()
    meter.finish()
    out = dict(previous_out)
    meas = {}
    for c, M in (previous_out.get("meas") or {}).items():
        meas[c] = Measurements(mean=M.mean, background=meter.mean.copy(), area_px=M.area_px,
                               n_saturated=M.n_saturated, quality=M.quality,
                               channels=list(M.channels), background_sd=meter.sd.copy(),
                               roi_mode=M.roi_mode, sum=M.sum,
                               background_sum=meter.sum.copy(),
                               background_npx=meter.npx.copy())
    out["meas"] = meas
    out["background"] = meter.summary()
    out["bg_excluded"] = dict(meter.excluded)
    params = dict(previous_out.get("params") or {})
    if params:
        params["background"] = MN.background_params(um)
        out["params"] = params
    out["bg_read_px"] = int(frames.px_read)
    return out


# ==========================================================================
#  Splicing a single-cell result in (troubleshooter)
# ==========================================================================
def pairs_of(which: Dict[str, Sequence[int]]) -> Set[Pair]:
    return {(c, int(k)) for c, ks in (which or {}).items() for k in ks}


# ==========================================================================
#  One call for the window
# ==========================================================================
def update(src, exp, cells, background, t0: int, previous_out: Optional[dict],
           old_snap: Optional[dict], new_snap: dict, progress=None, **track_kw) -> dict:
    """
    Bring previous_out (tracked with old_snap) up to date with new_snap, the
    cheapest exact way: nothing (returns previous_out), the background only,
    the changed ROIs (and whatever they reach), or everything. track_kw: the
    track_cells settings (max_move_um, mito_k, sat_level, lead, size_tol, rules,
    gate_snr, overlap_k, boundaries, overrides). out["retrack"]["plan"] says
    what was done.
    """
    p = plan(old_snap, new_snap)
    if previous_out is not None and not p["full"] and nothing_to_do(p):
        out = dict(previous_out)
    elif p["full"] or previous_out is None or not replayable(previous_out, exp.n_timepoints):
        out = MN.track_cells(src, exp, cells, background, t0, progress=progress, **track_kw)
        out["retrack"] = dict(full=True, passes=1, pairs=None, seconds=None, px_read=None)
    elif not p["retrack"] and not p["drop_pairs"]:
        out = remeasure_background(src, exp, previous_out, background, progress=progress)
        out["retrack"] = dict(full=False, passes=0, pairs=[], seconds=None, px_read=None)
    else:
        out = retrack_cells(src, exp, cells, background, t0, previous_out, p["retrack"],
                            progress=progress, background_changed=p["background"], **track_kw)
    out["retrack"] = dict(out.get("retrack") or {}, plan=p)
    return out
