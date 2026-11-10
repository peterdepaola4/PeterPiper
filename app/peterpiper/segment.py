"""
The ROI object, image helpers and the background ROI.

An ROI is stored as a bounding box plus a boolean mask, so rings (which are not
simple polygons) and hand-drawn polygons are the same kind of object downstream.
ROIs are drawn where you click by manual.py (nothing is detected automatically);
this module holds what that and the rest of the app share: Roi, small
version-stable morphology helpers, flatten / auto_threshold and the automatic
background region.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy import ndimage as ndi
from skimage import measure
from skimage.filters import threshold_triangle


# ==========================================================================
#  Small, version-stable morphology helpers
#  (scikit-image has changed the signatures of remove_small_objects and
#   binary_erosion between releases; these do the same jobs with SciPy only.)
# ==========================================================================
_DISK_CACHE: Dict[int, np.ndarray] = {}


def _disk(radius: int) -> np.ndarray:
    r = max(0, int(radius))
    if r not in _DISK_CACHE:
        if r == 0:
            _DISK_CACHE[r] = np.ones((1, 1), bool)
        else:
            y, x = np.ogrid[-r:r + 1, -r:r + 1]
            _DISK_CACHE[r] = (x * x + y * y) <= r * r + 1e-9
    return _DISK_CACHE[r]


def _dilate(mask: np.ndarray, radius: int) -> np.ndarray:
    if radius <= 0:
        return mask
    return ndi.binary_dilation(mask, structure=_disk(radius))


def _remove_small(mask: np.ndarray, min_size: int) -> np.ndarray:
    if min_size <= 1 or not mask.any():
        return mask
    lab, n = ndi.label(mask)
    if n == 0:
        return mask
    counts = np.bincount(lab.ravel())
    counts[0] = 0
    return counts[lab] >= min_size


def _block_mean(a: np.ndarray, f: int) -> np.ndarray:
    """Average over f x f blocks - an alias-free way to shrink an image."""
    if f <= 1:
        return a
    h, w = a.shape
    h2, w2 = h - h % f, w - w % f
    if h2 < f or w2 < f:
        return a
    return a[:h2, :w2].reshape(h2 // f, f, w2 // f, f).mean(axis=(1, 3))


def _upsample_to(small: np.ndarray, shape: Tuple[int, int]) -> np.ndarray:
    zy = shape[0] / small.shape[0]
    zx = shape[1] / small.shape[1]
    out = ndi.zoom(small, (zy, zx), order=1, mode="nearest")
    if out.shape != shape:                       # guard against rounding
        pad = np.zeros(shape, out.dtype)
        h = min(shape[0], out.shape[0])
        w = min(shape[1], out.shape[1])
        pad[:h, :w] = out[:h, :w]
        if h < shape[0]:
            pad[h:, :w] = out[h - 1:h, :w]
        if w < shape[1]:
            pad[:, w:] = pad[:, w - 1:w]
        out = pad
    return out


def _solidity(region) -> float:
    """
    Solidity (area / convex-hull area), computed on a half-size copy.

    The exact convex hull of every object is one of the most expensive parts of
    the filtering step, and nuclei are tens of pixels across, so halving the
    resolution changes the number in the third decimal while costing a quarter
    as much.
    """
    im = region.image
    if im.shape[0] >= 16 and im.shape[1] >= 16:
        small = im[::2, ::2]
        if small.sum() >= 8:
            try:
                from skimage.morphology import convex_hull_image
                hull = convex_hull_image(small)
                if hull.sum():
                    return float(small.sum()) / float(hull.sum())
            except Exception:
                pass
    try:
        return float(region.solidity)
    except Exception:
        return 1.0


def _coarse_factor(shape: Tuple[int, int], target: int = 800) -> int:
    """Downsample factor that keeps the working image near `target` px."""
    return int(max(1, round(min(shape) / target)))


# ==========================================================================
#  ROI
# ==========================================================================
@dataclass
class Roi:
    """A region of interest: boolean mask inside a bounding box (y0, x0, y1, x1)."""

    bbox: Tuple[int, int, int, int]
    mask: np.ndarray
    kind: str = "nucleus"
    include: bool = True
    source: str = "auto"          # "auto" | "manual"
    quality: float = 1.0          # tracking match quality for this timepoint
    score: float = float("nan")   # ranking for the 'Cells included' slider (naturalness)
    expressing: bool = True       # False: below the expression floor
    why: str = ""                 # why it starts excluded (shown when clicked)
    outline: Optional[np.ndarray] = None   # shown / clicked region (mito: the network's
                                           # envelope); measured pixels are still `mask`

    # ------------------------------------------------------------- geometry
    @property
    def area(self) -> int:
        return int(self.mask.sum())

    @property
    def centroid(self) -> Tuple[float, float]:
        y0, x0, _, _ = self.bbox
        if not self.mask.any():
            return float(y0), float(x0)
        ys, xs = np.nonzero(self.mask)
        return float(ys.mean() + y0), float(xs.mean() + x0)

    def shifted(self, dy: int, dx: int, shape: Tuple[int, int]) -> "Roi":
        """Translate the ROI, clipping it to the image."""
        h, w = shape
        y0, x0, y1, x1 = self.bbox
        ny0, nx0, ny1, nx1 = y0 + dy, x0 + dx, y1 + dy, x1 + dx
        cy0, cx0 = max(0, ny0), max(0, nx0)
        cy1, cx1 = min(h, ny1), min(w, nx1)
        if cy1 <= cy0 or cx1 <= cx0:
            return Roi((y0, x0, y1, x1), self.mask.copy(), self.kind,
                       self.include, self.source, 0.0)
        sub = self.mask[cy0 - ny0: cy1 - ny0, cx0 - nx0: cx1 - nx0]
        return Roi((cy0, cx0, cy1, cx1), sub.copy(), self.kind,
                   self.include, self.source, self.quality)

    def full_mask(self, shape: Tuple[int, int]) -> np.ndarray:
        out = np.zeros(shape, bool)
        y0, x0, y1, x1 = self.bbox
        out[y0:y1, x0:x1] = self.mask
        return out

    def contours(self) -> List[np.ndarray]:
        """Outlines as (N, 2) arrays of (x, y) image coordinates, for drawing.
        Cached on the ROI (its mask never changes once made), so redrawing the
        image while scrubbing through time costs nothing."""
        key = (id(self.mask), id(self.outline), self.bbox,
               bool(self.__dict__.get("show_kept")))
        cached = self.__dict__.get("_contour_cache")
        if cached is not None and cached[0] == key:
            return cached[1]
        out = self._contours_now()
        self.__dict__["_contour_cache"] = (key, out)
        return out

    def _contours_now(self) -> List[np.ndarray]:
        y0, x0, _, _ = self.bbox
        shown = [self.outline if self.outline is not None else self.mask]
        # mitochondria (and AND-rule ROIs, flagged show_kept by the window): the
        # measured pixels too, inside the outline that is followed
        if (self.kind == "mito" or self.__dict__.get("show_kept")) \
                and self.outline is not None and self.mask.any():
            shown.append(self.mask)
        out = []
        for m in shown:
            pad = np.pad(m, 1, mode="constant")
            for c in measure.find_contours(pad.astype(float), 0.5):
                pts = np.column_stack([c[:, 1] - 1 + x0, c[:, 0] - 1 + y0])
                if len(pts) >= 3:
                    out.append(pts)
        return out

    def measure(self, img: np.ndarray, sat_level: int = 65535) -> Dict[str, float]:
        y0, x0, y1, x1 = self.bbox
        vals = img[y0:y1, x0:x1][self.mask]
        if vals.size == 0:
            return {"mean": np.nan, "median": np.nan, "max": np.nan, "std": np.nan,
                    "area": 0, "n_sat": 0}
        return {
            "mean": float(vals.mean()),
            "std": float(vals.std()),
            "median": float(np.median(vals)),
            "max": float(vals.max()),
            "area": int(vals.size),
            "n_sat": int((vals >= sat_level).sum()),
        }

    # ------------------------------------------------------------ factories
    @staticmethod
    def from_polygon(points: Sequence[Sequence[float]],
                     shape: Tuple[int, int],
                     kind: str = "manual") -> Optional["Roi"]:
        """points: sequence of (x, y) in image coordinates."""
        pts = np.asarray(points, float)
        if pts.ndim != 2 or len(pts) < 3:
            return None
        h, w = shape
        x0 = int(max(0, np.floor(pts[:, 0].min())))
        x1 = int(min(w, np.ceil(pts[:, 0].max()) + 1))
        y0 = int(max(0, np.floor(pts[:, 1].min())))
        y1 = int(min(h, np.ceil(pts[:, 1].max()) + 1))
        if x1 - x0 < 1 or y1 - y0 < 1:
            return None
        local = np.column_stack([pts[:, 1] - y0, pts[:, 0] - x0])
        mask = measure.grid_points_in_poly((y1 - y0, x1 - x0), local)
        if not mask.any():
            return None
        return Roi((y0, x0, y1, x1), mask, kind, source="manual")

    @staticmethod
    def from_rect(x: float, y: float, w: float, h: float,
                  shape: Tuple[int, int], kind: str = "background") -> Optional["Roi"]:
        H, W = shape
        x0 = int(max(0, round(min(x, x + w))))
        y0 = int(max(0, round(min(y, y + h))))
        x1 = int(min(W, round(max(x, x + w))))
        y1 = int(min(H, round(max(y, y + h))))
        if x1 - x0 < 2 or y1 - y0 < 2:
            return None
        return Roi((y0, x0, y1, x1), np.ones((y1 - y0, x1 - x0), bool), kind)


# ==========================================================================
#  Image preparation
# ==========================================================================
def local_background(img: np.ndarray, radius_px: float) -> np.ndarray:
    """
    Smooth estimate of the local background.

    A large-sigma Gaussian is the right shape for this, but running it at full
    resolution on a 2400 x 2400 frame costs seconds. Block-averaging first,
    blurring the small image, then interpolating back gives the same surface to
    within a few counts for a fraction of the time.
    """
    f = img.astype(np.float32)
    if radius_px <= 1:
        return np.zeros_like(f)
    ds = min(_coarse_factor(img.shape, 800), max(1, int(radius_px // 8)))
    small = _block_mean(f, ds)
    sigma = max(0.5, radius_px / 2.0 / max(1, ds))
    blurred = ndi.gaussian_filter(small, sigma, mode="nearest")
    if ds <= 1:
        return blurred
    return _upsample_to(blurred, img.shape)


def flatten(img: np.ndarray, smooth_sigma: float, background_radius: float
            ) -> np.ndarray:
    """Smoothed, background-subtracted image in float32 counts."""
    f = img.astype(np.float32)
    if smooth_sigma > 0:
        f = ndi.gaussian_filter(f, smooth_sigma, mode="nearest")
    f = f - local_background(img, background_radius)
    return f


def auto_threshold(signal: np.ndarray) -> float:
    """
    Threshold in counts above local background.

    Fluorescence frames are mostly empty, so a noise-based floor (robust median
    + 4 sigma) is combined with the triangle threshold, which handles a histogram
    dominated by one background peak better than Otsu does. The larger of the two
    is used so that noise is never called signal.
    """
    sub = signal[::4, ::4].ravel()
    med = float(np.median(sub))
    mad = float(np.median(np.abs(sub - med)))
    noise = med + 4.0 * 1.4826 * max(mad, 1e-6)
    try:
        tri = float(threshold_triangle(sub))
    except Exception:
        tri = noise
    thr = max(noise, tri)
    if not np.isfinite(thr):
        thr = noise
    return float(thr)


# ==========================================================================
#  Background ROI
# ==========================================================================
def auto_background(planes: Sequence[np.ndarray], occupied: np.ndarray,
                    box_px: int, margin: int = 8) -> Tuple[Optional[Roi], str]:
    """
    Place a square ROI in the emptiest, flattest part of the field.

    Scores every candidate position by how much ROI / bright material it
    contains and how uniform it is, then returns the best one.
    """
    box = max(4, int(box_px))
    H, W = occupied.shape
    if H <= box + 2 * margin or W <= box + 2 * margin:
        return None, "The image is too small for a background box of that size."

    stack = np.maximum.reduce([p.astype(np.float32) for p in planes]).astype(np.float64)
    bright = stack > np.percentile(stack[::4, ::4], 97.0)
    busy = (occupied | bright).astype(np.float64)

    # Mean "busyness" and local contrast inside every possible box position.
    # Border pixels count as fully busy so the box is never placed half outside.
    occ = ndi.uniform_filter(busy, box, mode="constant", cval=1.0)
    mean = ndi.uniform_filter(stack, box, mode="nearest")
    sq = ndi.uniform_filter(stack * stack, box, mode="nearest")
    var = np.clip(sq - mean * mean, 0.0, None)

    # An empty box is the first priority; among equally empty boxes, prefer the
    # flattest one (no debris, no gradient).
    score = occ * 1000.0 + np.sqrt(var) / (np.abs(mean) + 1.0)
    edge = margin + box // 2
    score[:edge, :] = np.inf
    score[-edge:, :] = np.inf
    score[:, :edge] = np.inf
    score[:, -edge:] = np.inf
    if not np.isfinite(score).any():
        return None, "No cell-free area was found - draw the background ROI by hand."

    cy, cx = np.unravel_index(int(np.argmin(score)), score.shape)
    y0 = int(np.clip(cy - box // 2, 0, H - box))
    x0 = int(np.clip(cx - box // 2, 0, W - box))
    roi = Roi((y0, x0, y0 + box, x0 + box), np.ones((box, box), bool), "background")
    frac = float(busy[y0:y0 + box, x0:x0 + box].mean())
    msg = (f"Background box {box}x{box} px placed at ({x0}, {y0}); "
           f"{frac * 100:.1f}% of it contains detected material.")
    return roi, msg


def naturalness(rois: Sequence[Roi]) -> Tuple[np.ndarray, List[str]]:
    """
    How 'natural' each ROI looks compared with the others in the same image.

    For every cell: log area, solidity (convexity), circularity (4 pi A / P^2)
    and elongation are turned into robust z-scores against the median cell
    (median / MAD, so a few odd ones cannot shift the reference). Only the
    unnatural direction counts: smaller than the others, less convex, less
    round, more elongated. Very large (clumps) counts a little too.
    Returns (score, short reason) per ROI: 0 is a typical cell, more negative
    is odder; around -3 and below are the clear outliers.
    """
    n = len(rois)
    if n == 0:
        return np.zeros(0), []
    feats = np.zeros((n, 4))
    for i, r in enumerate(rois):
        m = r.mask
        a = max(1, int(m.sum()))
        props = measure.regionprops(m.astype(np.uint8))
        if not props:
            feats[i] = (np.log(a), 0.5, 0.5, 3.0)
            continue
        p = props[0]
        per = max(float(p.perimeter), 1.0)
        circ = float(np.clip(4 * np.pi * a / (per * per), 0, 1.2))
        maj = float(getattr(p, "axis_major_length", None) or p.major_axis_length)
        mnr = max(float(getattr(p, "axis_minor_length", None) or p.minor_axis_length), 1.0)
        feats[i] = (np.log(a), _solidity(p), circ, maj / mnr)

    def rz(x):
        med = np.median(x)
        mad = 1.4826 * np.median(np.abs(x - med))
        return (x - med) / max(mad, 1e-6 if mad else 0.05 * max(abs(med), 1e-3))

    if n < 4:                                    # too few to compare
        return np.zeros(n), [""] * n
    z_size, z_sol, z_circ, z_elong = (rz(feats[:, j]) for j in range(4))
    small = np.minimum(0.0, z_size)
    big = -0.5 * np.maximum(0.0, z_size - 3.0)
    shape = 0.5 * (np.minimum(0.0, z_sol) + np.minimum(0.0, z_circ) +
                   np.minimum(0.0, -z_elong))
    score = small + big + shape
    why = []
    for i in range(n):
        bits = []
        if z_size[i] < -2:
            bits.append(f"{np.exp(feats[i, 0] - np.median(feats[:, 0])) * 100:.0f}% of "
                        f"the typical size")
        if z_size[i] > 5:
            bits.append("much bigger than the others")
        if min(z_sol[i], z_circ[i]) < -2:
            bits.append("irregular outline")
        if z_elong[i] > 2:
            bits.append("unusually elongated")
        why.append(", ".join(bits))
    return score, why


def auto_background_large(stacks: Sequence[np.ndarray], occupied: np.ndarray,
                          um_per_px: float, max_um: float = 120.0, min_um: float = 25.0,
                          clear_um: float = 8.0) -> Tuple[Optional[Roi], str]:
    """
    A LARGE background region, placed automatically.

    `stacks` are (C, Y, X) frames sampled across the whole time series. Any
    pixel that is ever bright in any channel (cells, cytoplasm, debris, cells
    drifting in later) or lies within `clear_um` of a detected cell is
    forbidden. Then the largest square (from `max_um` down to `min_um`) that is
    almost entirely free is chosen, and whatever forbidden pixels remain inside
    it are masked out - so the region is big (a stable, low-noise reading) and
    still contains background only.
    """
    H, W = occupied.shape
    f = int(max(1, min(H, W) // 600))              # work on a ~600 px copy
    bright = np.zeros((H // f, W // f), bool) if f > 1 else np.zeros((H, W), bool)
    for st in stacks:
        for plane in st:
            p = _block_mean(plane.astype(np.float32), f)[:bright.shape[0], :bright.shape[1]]
            sm = ndi.gaussian_filter(p, 1.0)
            sub = sm[::2, ::2].ravel()
            med = float(np.median(sub))
            noise = 1.4826 * float(np.median(np.abs(sub - med))) or 1.0
            bright |= sm > med + 4.0 * noise
    occ = occupied[::f, ::f][:bright.shape[0], :bright.shape[1]] if f > 1 else occupied
    clear = max(1, int(round(clear_um / max(um_per_px * f, 1e-6))))
    forbidden = _dilate(bright | occ, clear)
    free = (~forbidden).astype(np.float64)
    h, w = free.shape
    margin = max(2, int(round(5.0 / max(um_per_px * f, 1e-6))))
    size_um = max_um
    while size_um >= min_um:
        box = int(round(size_um / max(um_per_px * f, 1e-6)))
        if box + 2 * margin < min(h, w):
            frac = ndi.uniform_filter(free, box, mode="constant", cval=0.0)
            e = margin + box // 2
            frac[:e, :] = frac[-e:, :] = 0
            frac[:, :e] = frac[:, -e:] = 0
            cy, cx = np.unravel_index(int(np.argmax(frac)), frac.shape)
            if frac[cy, cx] >= 0.9:
                y0 = int(np.clip(cy - box // 2, 0, h - box)) * f
                x0 = int(np.clip(cx - box // 2, 0, w - box)) * f
                bb = box * f
                y1, x1 = min(H, y0 + bb), min(W, x0 + bb)
                ok = ~forbidden[y0 // f:(y1 + f - 1) // f, x0 // f:(x1 + f - 1) // f]
                mask = np.repeat(np.repeat(ok, f, 0), f, 1)[:y1 - y0, :x1 - x0] if f > 1 else ok
                roi = Roi((y0, x0, y1, x1), mask.copy(), "background")
                return roi, (f"Large background region {size_um:.0f} x {size_um:.0f} um "
                             f"({x1 - x0} x {y1 - y0} px) at ({x0}, {y0}); "
                             f"{(1 - mask.mean()) * 100:.1f}% of it masked out because "
                             f"something bright passes through at some timepoint.")
        size_um *= 0.85
    return None, "No cell-free area was found - draw the background box by hand."

