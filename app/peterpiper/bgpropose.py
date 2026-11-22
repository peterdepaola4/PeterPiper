"""
PeterPiper 4.0: background FIRST - proposed background regions.

Before any cell is drawn, the analysis window shows a handful of places that
would make a good background region: dark, flat, free of cells and bright
specks in every channel, a sensible size, and spread over the image (so the
user sees choices from different parts of the field, not six boxes side by
side). Each comes with its mean and SD per channel (measured exactly, at full
resolution) and a short plain reason ("dark and even in every channel").

    propose(planes, um_per_px, occupied=None, n=6, channels=None)  -> [Candidate]
    measure_region(planes, roi, um_per_px, channels=None)          -> Candidate
                     (a region the user drew: the same numbers and reason)
    region_stats(planes, roi)                                      -> (mean[C], sd[C])

planes: one timepoint, (C, H, W). The SEARCH runs on a block-averaged copy
(about 600 px across: well under a second for 4 x 2400 x 2400); the numbers
are always taken from the full-resolution pixels. Nothing here changes how the
background is measured later (manual.BackgroundMeter) - a candidate is only
a suggestion until the user accepts it; its .roi is an ordinary segment.Roi
(kind "background", source "proposed").

Older placement helpers (segment.auto_background, segment.auto_background_large
and manual.auto_background) are unchanged; this module reuses their ideas:
a block-averaged working copy, bright = above median + k robust SD, a clear
zone around anything bright or drawn, and box sums with ndi.uniform_filter.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import numpy as np
from scipy import ndimage as ndi

from .segment import Roi

WORK_PX = 600              # the search runs on a copy about this many px across
BRIGHT_K = 3.0             # bright (a cell, a speck): smoothed > median + 3 robust SD
CLEAR_UM = 3.0             # ... and this far around it is not background either
EDGE_UM = 5.0              # never closer to the image edge than this
MAX_UM = 40.0              # the biggest square tried ...
MIN_UM = 12.0              # ... the smallest
FREE_MIN = 0.995           # a candidate is (almost) entirely free of bright / drawn pixels
DARK_Z = 1.0               # 'dark' in a channel: at most 1 robust SD above its typical level
EVEN_SD = 1.6              # 'even': local SD within 1.6 x the channel's own noise


@dataclass
class Candidate:
    """One proposed (or user-drawn) background region."""
    roi: Roi
    mean: np.ndarray                     # per channel, raw counts (full resolution)
    sd: np.ndarray                       # per channel
    reason: str = ""                     # short plain words
    score: float = 0.0                   # lower = better (ranking only)
    size_um: float = 0.0                 # side of the square (or sqrt of the area)
    rank: int = 0                        # 1-based; 0 = the user's own region
    channels: List[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"BG {self.rank}" if self.rank else "Your region"

    def area_um2(self, um_per_px: float) -> float:
        return float(self.roi.area) * float(um_per_px) ** 2


# --------------------------------------------------------------------------
#  helpers
# --------------------------------------------------------------------------
def _um(exp_or_um) -> float:
    v = getattr(exp_or_um, "um_per_px", exp_or_um)
    try:
        v = float(v)
    except (TypeError, ValueError):
        v = 1.0
    return v if v > 0 else 1.0


def _names(planes, channels, exp_or_um) -> List[str]:
    if channels:
        return [str(c) for c in channels]
    got = getattr(exp_or_um, "channels", None)
    if got and len(got) == len(planes):
        return [str(c) for c in got]
    return [f"Ch{i + 1}" for i in range(len(planes))]


def _block(plane: np.ndarray, f: int) -> np.ndarray:
    """f x f block mean (float32) - the alias-free shrink of segment._block_mean,
    done on the integer data without a full-size float copy."""
    if f <= 1:
        return np.asarray(plane, np.float32)
    h, w = plane.shape
    h2, w2 = h - h % f, w - w % f
    return plane[:h2, :w2].reshape(h2 // f, f, w2 // f, f).mean(axis=(1, 3), dtype=np.float32)


def _block_any(mask: np.ndarray, f: int, shape) -> np.ndarray:
    m = np.asarray(mask, bool)
    if f > 1:
        h, w = shape
        m = m[:h * f, :w * f].reshape(h, f, w, f).any(axis=(1, 3))
    return m[:shape[0], :shape[1]]


def _robust(v: np.ndarray) -> Tuple[float, float]:
    med = float(np.median(v))
    noise = 1.4826 * float(np.median(np.abs(v - med)))
    return med, (noise if noise > 0 else max(1.0, abs(med) * 0.01))


def region_stats(planes: np.ndarray, roi: Roi) -> Tuple[np.ndarray, np.ndarray]:
    """Mean and SD per channel of the region's raw pixels (full resolution,
    float64) - the same pixels BackgroundMeter will use."""
    y0, x0, y1, x1 = (int(v) for v in roi.bbox)
    crop = np.asarray(planes)[:, y0:y1, x0:x1]
    m = np.asarray(roi.mask, bool)
    if not m.any():
        n = len(planes)
        return np.full(n, np.nan), np.full(n, np.nan)
    vals = crop[:, m].astype(np.float64)
    return vals.mean(axis=1), vals.std(axis=1)


class _Work:
    """The block-averaged working copy and its per-channel statistics."""

    def __init__(self, planes: np.ndarray, um: float, occupied: Optional[np.ndarray]) -> None:
        C, H, W = planes.shape
        self.f = f = int(max(1, round(min(H, W) / WORK_PX)))
        self.small = np.stack([_block(planes[c], f) for c in range(C)])
        _, self.h, self.w = self.small.shape
        self.um_s = um * f                                  # um per working pixel
        self.med = np.zeros(C)
        self.noise = np.zeros(C)
        self.z = np.empty_like(self.small)                  # robust z per channel
        bright = np.zeros((self.h, self.w), bool)
        sub = (slice(None, None, 2), slice(None, None, 2))
        for c in range(C):
            med, noise = _robust(self.small[c][sub])
            self.med[c], self.noise[c] = med, noise
            self.z[c] = (self.small[c] - med) / noise
            sm = ndi.gaussian_filter(self.small[c], 1.0)
            bright |= sm > med + BRIGHT_K * noise
        if occupied is not None and np.asarray(occupied).any():
            bright |= _block_any(occupied, f, (self.h, self.w))
        clear = max(1, int(round(CLEAR_UM / max(self.um_s, 1e-6))))
        self.forbidden = ndi.binary_dilation(bright, iterations=clear)
        self.sorted = [np.sort(self.small[c][sub].ravel()) for c in range(C)]

    def percentile_of(self, c: int, value: float) -> float:
        """Share of the channel's (working) pixels darker than value."""
        s = self.sorted[c]
        return float(np.searchsorted(s, value)) / max(1, s.size)

    def z_of(self, c: int, value: float) -> float:
        """value in robust SD units above the channel's typical (median) level."""
        return (float(value) - self.med[c]) / self.noise[c]


def _reason(work: _Work, names: Sequence[str], mean: np.ndarray, local_sd: np.ndarray,
            size_um: float, free: float = 1.0) -> str:
    """Short plain words: dark? even? in every channel or which not."""
    dark = [work.z_of(c, float(mean[c])) <= DARK_Z for c in range(len(names))]
    even = [float(local_sd[c]) <= EVEN_SD for c in range(len(names))]
    not_dark = [n for n, d in zip(names, dark) if not d]
    uneven = [n for n, e in zip(names, even) if not e]
    if not not_dark and not uneven:
        txt = "dark and even in every channel"
    elif not not_dark:
        txt = "dark in every channel; a little uneven in " + ", ".join(uneven)
    elif not uneven:
        txt = "even, but a little brighter in " + ", ".join(not_dark)
    else:
        txt = "brighter in " + ", ".join(not_dark) + "; uneven in " + ", ".join(uneven)
    if free < 0.98:
        txt += "; something bright is inside"
    if size_um >= 30:
        txt = "large, " + txt
    elif size_um < 16:
        txt = "small gap between cells, " + txt
    return txt


# --------------------------------------------------------------------------
#  the proposals
# --------------------------------------------------------------------------
def propose(planes, exp_or_um, occupied: Optional[np.ndarray] = None, n: int = 6,
            channels: Optional[Sequence[str]] = None, max_um: float = MAX_UM,
            min_um: float = MIN_UM) -> List[Candidate]:
    """
    Up to n ranked background candidates for one timepoint.

    planes: (C, H, W) raw counts (one timepoint, e.g. the drawing timepoint);
    exp_or_um: the Experiment (its um_per_px and channel names) or um per px;
    occupied: (H, W) bool of pixels already taken by ROIs (or None).
    Squares of max_um are tried first, then smaller ones (x 0.8, down to
    min_um) to fill up to n. Ranked best first: darkest + evenest (in robust
    SD units of each channel, averaged over the channels), a little bonus for
    a bigger square. Candidates keep apart (at least a sixth of the image, or
    their own size) so they are spread over the field.
    """
    planes = np.asarray(planes)
    if planes.ndim == 2:
        planes = planes[np.newaxis]
    C, H, W = planes.shape
    um = _um(exp_or_um)
    names = _names(planes, channels, exp_or_um)
    work = _Work(planes, um, occupied)
    h, w = work.h, work.w
    free = (~work.forbidden).astype(np.float32)
    # per-channel z clipped (one very bright channel must not decide everything)
    zc = np.clip(work.z, -6.0, 12.0)
    dark_map = zc.mean(axis=0)
    margin = max(1, int(math.ceil(EDGE_UM / max(work.um_s, 1e-6))))
    picked: List[Tuple[float, int, int, int, float, np.ndarray]] = []
    spread = max(h, w) / 6.0
    size = float(max_um)
    min_box = max(3, int(round(min_um / work.um_s)))
    tries = 0
    while size >= min_um - 1e-6 and len(picked) < n and tries < 12:
        tries += 1
        box = max(3, int(round(size / work.um_s)))
        size *= 0.8
        if box + 2 * margin >= min(h, w):
            continue
        frac = ndi.uniform_filter(free, box, mode="constant", cval=0.0)
        dark = ndi.uniform_filter(dark_map, box, mode="nearest")
        # evenness: local SD of each channel's z inside the box, averaged
        sd = np.zeros((C, h, w), np.float32)
        for c in range(C):
            m1 = ndi.uniform_filter(zc[c], box, mode="nearest")
            m2 = ndi.uniform_filter(zc[c] * zc[c], box, mode="nearest")
            sd[c] = np.sqrt(np.clip(m2 - m1 * m1, 0.0, None))
        flat = sd.mean(axis=0)
        score = dark + 0.5 * flat - 0.6 * math.log2(box / min_box + 1e-9)
        e = margin + box // 2 + 1
        ok = frac >= FREE_MIN
        ok[:e, :] = ok[-e:, :] = False
        ok[:, :e] = ok[:, -e:] = False
        score = np.where(ok, score, np.inf)
        # positions too close to an earlier pick are out
        yy, xx = np.ogrid[0:h, 0:w]
        for (_s, cy, cx, b, _sz, _l) in picked:
            r = max(spread, 0.5 * (b + box) * 1.2)
            score[(yy - cy) ** 2 + (xx - cx) ** 2 < r * r] = np.inf
        while len(picked) < n:
            i = int(np.argmin(score))
            best = float(score.flat[i])
            if not np.isfinite(best):
                break
            cy, cx = divmod(i, w)
            picked.append((best, cy, cx, box, box * work.um_s, sd[:, cy, cx].copy()))
            r = max(spread, box * 1.2)
            y0, y1 = max(0, int(cy - r)), min(h, int(cy + r) + 1)
            x0, x1 = max(0, int(cx - r)), min(w, int(cx + r) + 1)
            sub_y, sub_x = np.ogrid[y0:y1, x0:x1]
            score[y0:y1, x0:x1][(sub_y - cy) ** 2 + (sub_x - cx) ** 2 < r * r] = np.inf
    picked.sort(key=lambda p: p[0])
    out: List[Candidate] = []
    f = work.f
    for rank, (sc, cy, cx, box, size_um, lsd) in enumerate(picked, start=1):
        y0 = int(np.clip(cy - box // 2, 0, h - box)) * f
        x0 = int(np.clip(cx - box // 2, 0, w - box)) * f
        bb = box * f
        y1, x1 = min(H, y0 + bb), min(W, x0 + bb)
        roi = Roi((y0, x0, y1, x1), np.ones((y1 - y0, x1 - x0), bool), "background")
        roi.source = "proposed"
        mean, sdv = region_stats(planes, roi)
        cand = Candidate(roi=roi, mean=mean, sd=sdv, score=float(sc),
                         size_um=float((x1 - x0) * um), rank=rank, channels=list(names))
        cand.reason = _reason(work, names, mean, lsd, cand.size_um)
        roi.score = float(sc)
        roi.why = cand.reason
        out.append(cand)
    return out


def measure_region(planes, roi: Roi, exp_or_um, channels: Optional[Sequence[str]] = None
                   ) -> Candidate:
    """A region the user drew (or placed), described like a proposal: exact
    mean / SD per channel and the same kind of plain reason (rank 0)."""
    planes = np.asarray(planes)
    if planes.ndim == 2:
        planes = planes[np.newaxis]
    um = _um(exp_or_um)
    names = _names(planes, channels, exp_or_um)
    mean, sd = region_stats(planes, roi)
    work = _Work(planes, um, None)
    f = work.f
    y0, x0, y1, x1 = (int(v) for v in roi.bbox)
    sy = slice(y0 // f, max(y0 // f + 1, y1 // f))
    sx = slice(x0 // f, max(x0 // f + 1, x1 // f))
    lsd = np.array([float(np.std(work.z[c][sy, sx])) for c in range(len(names))])
    freed = 1.0 - float(work.forbidden[sy, sx].mean()) if work.forbidden[sy, sx].size else 1.0
    size_um = math.sqrt(max(roi.area, 1)) * um
    cand = Candidate(roi=roi, mean=mean, sd=sd, score=float("nan"), size_um=size_um,
                     rank=0, channels=list(names))
    cand.reason = _reason(work, names, mean, lsd, size_um, free=freed)
    return cand
