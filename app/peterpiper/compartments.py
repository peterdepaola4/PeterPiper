"""
Image helpers for the compartments beyond the nucleus, used when you click to
add an ROI (manual.py) and by the tracking rules (rules.py):

    mito_mask()           mitochondria: fine bright structures (puncta / tubules)
                          well above the local background noise
    cells_from_channel()  whole cells from a channel WITHOUT a nuclear stain
                          (mitochondria, or a whole-cell fill such as mRuby),
                          split at their nuclei
    split_roi()           cut an ROI in two along a line (the Split tool)
    _robust_noise()       the MAD-based noise level used throughout
"""
from __future__ import annotations

from typing import List, Optional

import numpy as np
from scipy import ndimage as ndi
from skimage import measure, segmentation

from .segment import Roi, _block_mean, _remove_small


def _px(um: float, um_per_px: float) -> float:
    return um / max(um_per_px, 1e-6)


def _robust_noise(x: np.ndarray) -> float:
    x = x[np.isfinite(x)]
    if x.size < 10:
        return 1.0
    med = float(np.median(x))
    return float(1.4826 * np.median(np.abs(x - med))) or 1.0


# ==========================================================================
#  Mitochondria
# ==========================================================================
def mito_mask(plane: np.ndarray, um_per_px: float, k: float = 3.0) -> np.ndarray:
    """
    Mitochondria: fine bright structures. A difference of Gaussians keeps
    puncta / tubules and removes the diffuse cytosolic haze and the large-scale
    background; pixels more than k robust noise SDs above zero are kept.
    """
    im = plane.astype(np.float32)
    s1 = max(0.7, _px(0.12, um_per_px))
    s2 = max(3.0, _px(1.0, um_per_px))
    dog = ndi.gaussian_filter(im, s1) - ndi.gaussian_filter(im, s2)
    noise = _robust_noise(dog[::4, ::4])
    m = dog > k * noise
    m = _remove_small(m, max(3, int(_px(0.25, um_per_px) ** 2)))
    return m


# ==========================================================================
#  Whole cells without a nuclear stain
# ==========================================================================
def cells_from_channel(plane: np.ndarray, um_per_px: float, role: str = "mito",
                       exclude_border: bool = True, min_um2: float = 60.0) -> np.ndarray:
    """
    Whole cells from a channel WITHOUT a nuclear stain (mitochondria, or a
    whole-cell fill such as mRuby). Label image, one label per cell.

    1  Brightness-independent: background subtracted, divided by its noise and
       LOG-scaled, so a dim cell and one ten times brighter count the same.
    2  Lightly blurred (fills the gaps between mitochondria), thresholded
       (Otsu), closed and hole-filled -> where there is cell.
    3  Touching cells are split at their nuclei: with mitochondria the nucleus
       is the dark hole ringed by mitochondria; in a whole-cell fill it is the
       brighter core. Each cell = the part of the cloud closest to its nucleus.
       A cell with no visible nucleus gets one seed at its thickest point.
    """
    from skimage import filters, morphology
    f = int(max(1, round(0.5 / max(um_per_px, 1e-6))))       # work at ~0.5 um/px
    im = _block_mean(plane.astype(np.float32), f) if f > 1 else plane.astype(np.float32)
    u = um_per_px * f
    bg = ndi.gaussian_filter(ndi.minimum_filter(ndi.gaussian_filter(im, 2),
                                                size=max(3, int(_px(30, u)))), _px(15, u))
    sig = im - bg
    lo = sig[::3, ::3].ravel()
    noise = float(1.4826 * np.median(np.abs(lo - np.median(lo)))) or 1.0
    L = np.log1p(np.clip(sig / noise, 0, None))
    Ls = ndi.gaussian_filter(L, _px(1.5, u))
    try:
        thr = float(filters.threshold_otsu(Ls[::2, ::2]))
    except ValueError:
        return np.zeros(plane.shape, np.int32)
    m = ndi.binary_closing(Ls > thr, iterations=max(1, int(_px(1.5, u))))
    m = _remove_small(ndi.binary_fill_holes(m), int(min_um2 / (u * u)))
    if not m.any():
        return np.zeros(plane.shape, np.int32)
    # nuclei as seeds
    Lf = ndi.gaussian_filter(L, _px(1.0, u))
    inner = ndi.binary_erosion(m, iterations=max(1, int(_px(2.0, u))))
    fp = morphology.disk(max(2, int(_px(9.0, u))))
    if role == "mito":
        cand = (ndi.grey_closing(Lf, footprint=fp) - Lf) > 0.6       # dark hole in the network
    else:
        cand = (Lf - ndi.grey_opening(Lf, footprint=fp)) > 0.4       # brighter core of a fill
    cand = ndi.binary_opening(inner & cand, structure=morphology.disk(max(1, int(_px(2.0, u)))))
    lab_c, _ = ndi.label(cand)
    seeds = np.zeros(m.shape, np.int32)
    n = 0
    for r in measure.regionprops(lab_c):
        if 25 <= r.area * u * u <= 600 and r.solidity >= 0.8:
            n += 1
            seeds[lab_c == r.label] = n
    dist = ndi.distance_transform_edt(m)
    comp, nc = ndi.label(m)
    has = np.zeros(nc + 1, bool)
    has[np.unique(comp[seeds > 0])] = True
    for c, sl in enumerate(ndi.find_objects(comp), start=1):
        if not has[c] and sl is not None:
            d = np.where(comp[sl] == c, dist[sl], 0)
            yy, xx = np.unravel_index(int(np.argmax(d)), d.shape)
            n += 1
            seeds[sl[0].start + yy, sl[1].start + xx] = n
    lab = segmentation.watershed(ndi.distance_transform_edt(seeds == 0), seeds, mask=m)
    if exclude_border:
        edge = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
        lab[np.isin(lab, edge[edge > 0])] = 0
    keep = np.unique(lab[lab > 0])
    lut = np.zeros(int(lab.max()) + 1, np.int32)
    lut[keep] = np.arange(1, keep.size + 1, dtype=np.int32)
    lab = lut[lab]
    if f > 1:
        lab = np.repeat(np.repeat(lab, f, 0), f, 1)[:plane.shape[0], :plane.shape[1]]
        if lab.shape != plane.shape:
            full = np.zeros(plane.shape, np.int32)
            full[:lab.shape[0], :lab.shape[1]] = lab
            lab = full
    return lab.astype(np.int32)


# ==========================================================================
#  Editing
# ==========================================================================
def split_roi(r: Roi, p0, p1) -> Optional[List[Roi]]:
    """Cut an ROI in two along the line p0-p1 ((x, y) points). None if it does not cut."""
    y0, x0, y1, x1 = r.bbox
    (ax, ay), (bx, by) = p0, p1
    yy, xx = np.mgrid[y0:y1, x0:x1]
    side = (bx - ax) * (yy - ay) - (by - ay) * (xx - ax) > 0
    # a 2-pixel cut along the line so the halves do not touch
    d = np.abs((bx - ax) * (yy - ay) - (by - ay) * (xx - ax)) / max(np.hypot(bx - ax, by - ay), 1e-6)
    keep = r.mask & (d > 1.0)
    parts = []
    for half in (keep & side, keep & ~side):
        lab, n = ndi.label(half)
        if n == 0:
            continue
        sizes = np.bincount(lab.ravel())[1:]
        big = lab == (int(np.argmax(sizes)) + 1)
        if big.sum() < 0.05 * r.area:
            continue
        ys, xs = np.nonzero(big)
        a0, a1, b0, b1 = int(ys.min()), int(ys.max()) + 1, int(xs.min()), int(xs.max()) + 1
        parts.append(Roi((y0 + a0, x0 + b0, y0 + a1, x0 + b1), big[a0:a1, b0:b1].copy(),
                         "nucleus", True, "manual"))
    return parts if len(parts) == 2 else None

