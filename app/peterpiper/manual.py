"""
v2.0: ROIs are made by clicking - nothing is detected automatically.

You pick a compartment and a channel and click where you can see it; the ROI is
drawn around the click from that channel's pixels only (a small window, so it
is instant on any image size):

    nucleus       the bright blob under the click, out to half its brightness
                  above the local background (holes filled)
    cell          the whole cell in that channel, split from touching neighbours
                  at their nuclei / bright cores, holes (the nucleus) filled
    cytoplasm     the same cell minus its nucleus (your nucleus ROI of that cell
                  if there is one, otherwise the dark hole in the cell)
    mito          the cell's mitochondria region, and inside it the mitochondria
                  themselves as many small pieces (strands / puncta) - only those
                  pixels are measured, never the empty space between them

Clicked ROIs that sit on the same cell share one cell number (by overlap or by
being close together - no cell outline needed); the Link tool fixes a wrong guess.

Tracking: every ROI is REDRAWN at every timepoint - moved by the cell's
sub-pixel image shift, then re-outlined from that frame's pixels at the edge
level it had when you clicked (see track_cells).
"""
from __future__ import annotations

from dataclasses import dataclass

import time
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy import ndimage as ndi

from .compartments import _robust_noise, cells_from_channel, mito_mask  # noqa: F401
from .measure import Measurements
from .segment import Roi

COMPS = ("nucleus", "cell", "cytoplasm", "mito")
LABELS = {"nucleus": "Nucleus", "cell": "Whole cell", "cytoplasm": "Cytoplasm",
          "mito": "Mitochondria", "background": "Background"}
FILE_NAMES = {"nucleus": "nucleus", "cell": "whole_cell", "cytoplasm": "cytoplasm",
              "mito": "mito"}
ProgressFn = Optional[Callable[[float, str], bool]]


class Cancelled(Exception):
    pass


def _px(um: float, um_per_px: float) -> float:
    return um / max(um_per_px, 1e-9)


def _crop(plane: np.ndarray, y: float, x: float, half: int):
    H, W = plane.shape
    yi, xi = int(round(y)), int(round(x))
    y0, y1 = max(0, yi - half), min(H, yi + half)
    x0, x1 = max(0, xi - half), min(W, xi + half)
    return plane[y0:y1, x0:x1].astype(np.float32), y0, x0, yi - y0, xi - x0


def _to_roi(m: np.ndarray, y0: int, x0: int, outline: Optional[np.ndarray] = None) -> Optional[Roi]:
    shown = m if outline is None else (m | outline)
    if not shown.any():
        return None
    ys, xs = np.nonzero(shown)
    a0, a1, b0, b1 = int(ys.min()), int(ys.max()) + 1, int(xs.min()), int(xs.max()) + 1
    r = Roi((y0 + a0, x0 + b0, y0 + a1, x0 + b1), m[a0:a1, b0:b1].copy(), "nucleus",
            True, "manual")
    if outline is not None:
        r.outline = outline[a0:a1, b0:b1].copy()
    return r


def _keep_component(m: np.ndarray, cy: int, cx: int) -> np.ndarray:
    lab, n = ndi.label(m)
    if n == 0:
        return m
    k = lab[cy, cx]
    if k == 0:                                   # nearest piece to the click
        d, (iy, ix) = ndi.distance_transform_edt(lab == 0, return_indices=True)
        k = lab[iy[cy, cx], ix[cy, cx]]
    return lab == k


# ==========================================================================
#  Drawing at a click
# ==========================================================================
def _nucleus_at(sm: np.ndarray, raw: np.ndarray, cy: int, cx: int, um: float,
                inner_um: float = 2.5, edge: float = 0.35) -> Optional[dict]:
    """
    The nucleus around (cy, cx) in a smoothed crop `sm` (raw = same crop, unsmoothed):
    its edge sits 35 % of the way from the local background up to the nucleus's
    typical inside brightness (the median of a small disc at its centre) - so
    bright specks inside a nucleus can neither shrink it to the speck nor split it,
    and a nucleus with a brighter core is still outlined whole.
    Returns dict(mask, bg, inner, noise, touches_edge) or None.
    """
    H, W = sm.shape
    if not (0 <= cy < H and 0 <= cx < W):
        return None
    r = int(max(2, _px(inner_um, um)))
    yy, xx = np.ogrid[-cy:H - cy, -cx:W - cx]
    disc = yy * yy + xx * xx <= r * r
    inner = float(np.median(sm[disc]))
    bg = float(np.percentile(sm, 15))
    low = raw[sm <= np.percentile(sm, 40)]
    noise = _robust_noise((low - np.median(low)).ravel()) if low.size > 20 else 1.0
    if inner - bg <= 3 * noise:
        return None
    m = ndi.binary_fill_holes(_keep_component(sm > bg + edge * (inner - bg), cy, cx))
    if not m[cy, cx]:
        return None
    whole = float(np.median(sm[m]))           # the centre may have been a bright speck:
    if whole < inner:                         # judge by the whole nucleus once more
        inner = whole
        m2 = ndi.binary_fill_holes(_keep_component(sm > bg + edge * (inner - bg), cy, cx))
        if m2[cy, cx]:
            m = m2
    m = ndi.binary_opening(m, iterations=1) & m
    if not m.any() or not m[cy, cx]:
        return None
    m = _keep_component(m, cy, cx)
    touches = bool(m[0].any() or m[-1].any() or m[:, 0].any() or m[:, -1].any())
    return dict(mask=m, bg=bg, inner=inner, noise=noise, touches_edge=touches)


def draw_nucleus(plane: np.ndarray, y: float, x: float, um: float,
                 expect_um2: Optional[float] = None) -> Optional[Roi]:
    """The nucleus under the click (see _nucleus_at); a circle if nothing is there."""
    half = int(_px(25.0, um))
    if expect_um2:
        half = int(np.clip(2.5 * np.sqrt(expect_um2 / np.pi) / um, _px(15, um), _px(60, um)))
    for _grow in range(3):
        crop, y0, x0, cy, cx = _crop(plane, y, x, half)
        if crop.size < 16 or not (0 <= cy < crop.shape[0] and 0 <= cx < crop.shape[1]):
            return None
        sm = ndi.gaussian_filter(crop, max(1.0, _px(0.8, um)))
        r = int(max(2, _px(2.0, um)))          # the click may be a little off-centre
        wy0, wx0 = max(0, cy - r), max(0, cx - r)
        win = sm[wy0:cy + r + 1, wx0:cx + r + 1]
        py, px = np.unravel_index(int(np.argmax(win)), win.shape)
        res = _nucleus_at(sm, crop, py + wy0, px + wx0, um)
        if res is None:
            break
        if not res["touches_edge"]:
            if res["mask"].sum() >= _px(2.0, um) ** 2:
                return _to_roi(res["mask"], y0, x0)
            break
        if half >= _px(60, um):
            return _to_roi(res["mask"], y0, x0)
        half = int(half * 1.6)                            # big nucleus: look wider
    rr = _px(np.sqrt(expect_um2 / np.pi), um) if expect_um2 else _px(5.0, um)
    crop, y0, x0, cy, cx = _crop(plane, y, x, int(rr) + 2)
    yy, xx = np.ogrid[:crop.shape[0], :crop.shape[1]]
    return _to_roi((yy - cy) ** 2 + (xx - cx) ** 2 <= rr * rr, y0, x0)


def _split_on_valleys(crop: np.ndarray, lab: np.ndarray, um: float,
                      nuclei: Sequence[Roi], y0: int, x0: int, cy: int, cx: int) -> np.ndarray:
    """
    Re-split the cells found in the window along the DIM lines between them
    (watershed on the image), seeded by your nucleus ROIs where there are any,
    otherwise by each cell's core - so touching cells get natural, not straight,
    borders.
    """
    from skimage.segmentation import watershed
    fg = lab > 0
    markers = np.zeros(lab.shape, np.int32)
    n = 0
    for r in nuclei or ():
        ry0, rx0, ry1, rx1 = r.bbox
        ys, xs = np.nonzero(r.mask)
        ys, xs = ys + ry0 - y0, xs + rx0 - x0
        ok = (ys >= 0) & (ys < lab.shape[0]) & (xs >= 0) & (xs < lab.shape[1])
        if ok.sum() < 5:
            continue
        n += 1
        markers[ys[ok], xs[ok]] = n
    if n == 0:                                   # no nuclei drawn here: each cell's core
        edt = ndi.distance_transform_edt(fg)
        for i in range(1, int(lab.max()) + 1):
            m = lab == i
            if m.any():
                n += 1
                markers[m & (edt >= 0.6 * edt[m].max())] = n
    elif not markers[cy, cx] and fg[cy, cx] and not any(
            markers[lab == lab[cy, cx]]):        # the clicked cell has no nucleus drawn
        n += 1
        markers[max(0, cy - 2):cy + 3, max(0, cx - 2):cx + 3] = n
    sm = ndi.gaussian_filter(crop, max(1.0, _px(1.0, um)))
    hole_filled = ndi.binary_fill_holes(fg)
    ws = watershed(-sm, markers, mask=hole_filled)
    return np.where(fg, ws, 0)


def _cell_region(plane: np.ndarray, y: float, x: float, um: float, role: str,
                 nuclei: Sequence[Roi] = ()) -> Tuple[Optional[np.ndarray], int, int]:
    """(mask of the cell under the click, NOT hole-filled, y0, x0) in a local window."""
    for half_um in (45.0, 80.0):
        crop, y0, x0, cy, cx = _crop(plane, y, x, int(_px(half_um, um)))
        if crop.size < 64:
            return None, 0, 0
        lab = cells_from_channel(crop, um, role, False, 20.0)
        if lab.max() == 0:
            return None, 0, 0
        lab = _split_on_valleys(crop, lab, um, nuclei, y0, x0, cy, cx)
        if lab.max() == 0:
            return None, 0, 0
        k = int(lab[cy, cx])
        if k == 0:
            d, (iy, ix) = ndi.distance_transform_edt(lab == 0, return_indices=True)
            if d[cy, cx] > _px(6.0, um):
                return None, 0, 0
            k = int(lab[iy[cy, cx], ix[cy, cx]])
        m = lab == k
        if half_um < 80 and (m[0].any() or m[-1].any() or m[:, 0].any() or m[:, -1].any()):
            continue                                      # cut off by the window: wider
        return m, y0, x0
    return m, y0, x0


def _paint(rois: Sequence[Roi], shape, y0: int, x0: int) -> np.ndarray:
    out = np.zeros(shape, bool)
    for r in rois:
        ry0, rx0, _, _ = r.bbox
        ys, xs = np.nonzero(r.mask)
        ys, xs = ys + ry0 - y0, xs + rx0 - x0
        ok = (ys >= 0) & (ys < shape[0]) & (xs >= 0) & (xs < shape[1])
        out[ys[ok], xs[ok]] = True
    return out


def draw_cell(plane: np.ndarray, y: float, x: float, um: float,
              nuclei: Sequence[Roi] = ()) -> Optional[Roi]:
    m, y0, x0 = _cell_region(plane, y, x, um, "cell", nuclei)
    if m is None:
        return None
    return _to_roi(ndi.binary_fill_holes(m), y0, x0)


def draw_cytoplasm(plane: np.ndarray, y: float, x: float, um: float,
                   nuclei: Sequence[Roi] = ()) -> Optional[Roi]:
    """The cell minus its nucleus; the outline shown is the whole cell."""
    m, y0, x0 = _cell_region(plane, y, x, um, "cell", nuclei)
    if m is None:
        return None
    full = ndi.binary_fill_holes(m)
    gap = int(round(_px(0.5, um)))
    nuc = _paint(nuclei, full.shape, y0, x0) & full       # your nucleus ROIs in this cell
    if nuc.sum() >= 0.03 * full.sum():
        lab, n = ndi.label(_paint(nuclei, full.shape, y0, x0))
        keep = np.unique(lab[nuc])
        nuc = np.isin(lab, keep[keep > 0])                # those nuclei, whole
    else:
        nuc = full & ~m                                   # the dark hole the region skipped
        if nuc.sum() < 0.03 * full.sum():                 # no hole: the dark core instead
            sub = plane[y0:y0 + full.shape[0], x0:x0 + full.shape[1]].astype(np.float32)
            sm = ndi.gaussian_filter(sub, max(1.0, _px(1.0, um)))
            inside = sm[full]
            if inside.size:
                dark = full & (sm < np.percentile(inside, 25))
                edt = ndi.distance_transform_edt(full)
                lab, n = ndi.label(dark)
                if n:
                    best = max(range(1, n + 1), key=lambda i: edt[lab == i].mean())
                    cand = ndi.binary_fill_holes(lab == best)
                    if 0.05 * full.sum() < cand.sum() < 0.6 * full.sum():
                        nuc = cand
    if gap and nuc.any():
        nuc = ndi.binary_dilation(nuc, iterations=gap)
    cyto = full & ~nuc
    if cyto.sum() < 0.1 * full.sum():
        cyto = full
    return _to_roi(cyto, y0, x0, outline=full)


def mito_pieces(crop: np.ndarray, region: np.ndarray, um: float, k: float = 3.0) -> np.ndarray:
    """
    The mitochondria themselves inside one cell's region: many small ROIs (strands
    and puncta), NOT the empty space between them.
      1  fine strands / puncta: a white top-hat (structures thinner than ~1.6 um)
         removes the diffuse cytosolic haze; kept where it is above BOTH k x the
         background noise and the cell's own split between haze and mitochondria
         (Otsu threshold of the top-hat inside the region);
      2  dense clusters (e.g. the packed network beside the nucleus, too wide for
         the top-hat): brighter than the cell's own split between its glow and
         its bright parts (Otsu of log intensity) AND still textured;
      3  specks under 0.1 um2 are dropped.
    Found again at every timepoint, so moving / fusing / splitting mitochondria
    are followed. Empty if the region holds no clear mitochondria.
    """
    from skimage.filters import threshold_otsu
    from skimage.morphology import disk
    sm = ndi.gaussian_filter(crop.astype(np.float32), max(0.6, _px(0.08, um)))
    r = int(max(2, round(_px(0.8, um))))
    th = ndi.white_tophat(sm, footprint=disk(r))
    region = region.astype(bool)
    if region.sum() < 20:
        return np.zeros_like(region)
    outside = ~ndi.binary_dilation(region, iterations=2)
    if outside.sum() > 200:
        pool, bgo = th[outside], float(np.percentile(sm[outside], 50))
        bnoise = _robust_noise((sm[outside] - bgo).ravel())
    else:
        pool, bgo = th[th <= np.percentile(th, 50)], float(np.percentile(sm, 10))
        bnoise = _robust_noise((sm - bgo).ravel())
    noise = _robust_noise((pool - np.median(pool)).ravel()) if pool.size > 20 else 1.0

    def otsu(v: np.ndarray) -> float:
        try:
            return float(threshold_otsu(v)) if v.size > 20 and np.ptp(v) > 0 else float("inf")
        except ValueError:
            return float("inf")
    fine = (th > max(float(k) * noise, otsu(th[region]))) & region
    inside = sm[region]
    cellpx = inside[inside > bgo + 5 * bnoise]
    m = fine
    if cellpx.size > 20:
        t = bgo + float(np.exp(otsu(np.log(np.maximum(cellpx - bgo, 1.0)))))
        m = fine | ((sm > t) & (th > 2 * noise) & region)
    if not m.any():                               # a dim cell: the noise floor alone
        m = (th > float(k) * noise) & region
    lab, n = ndi.label(m)
    if n:
        sizes = np.bincount(lab.ravel())
        keep = sizes >= max(3, int(round(0.1 / (um * um))))
        keep[0] = False
        m = keep[lab]
    return m


def mito_envelope(pieces: np.ndarray, region: np.ndarray, um: float) -> np.ndarray:
    """The part of the cell that holds its mitochondria: everything within 1 um of
    a piece, small gaps closed, holes filled (shown as the outline and followed
    when tracking; only the pieces are measured)."""
    if not pieces.any():
        return region
    env = ndi.distance_transform_edt(~pieces) <= _px(1.0, um)
    from skimage.morphology import disk
    env = ndi.binary_closing(env, structure=disk(int(max(1, _px(1.0, um)))))
    env = ndi.binary_fill_holes(env) & region
    return env if env.any() else region


def draw_mito(plane: np.ndarray, y: float, x: float, um: float, k: float = 3.0) -> Optional[Roi]:
    """The cell's mitochondria region (outline) and, measured, only the
    mitochondria pieces inside it (see mito_pieces)."""
    m, y0, x0 = _cell_region(plane, y, x, um, "mito")
    if m is None:
        return None
    region = ndi.binary_fill_holes(m)
    sub = plane[y0:y0 + region.shape[0], x0:x0 + region.shape[1]]
    mito = mito_pieces(sub, region, um, k)
    if not mito.any():
        return None
    return _to_roi(mito, y0, x0, outline=mito_envelope(mito, region, um))


def draw_at(comp: str, plane: np.ndarray, y: float, x: float, um: float, s,
            nuclei: Sequence[Roi] = (), expect_um2: Optional[float] = None) -> Optional[Roi]:
    """`nuclei`: the nucleus ROIs you have drawn - they anchor whole cells and
    are cut out of cytoplasm."""
    if comp == "nucleus":
        r = draw_nucleus(plane, y, x, um, expect_um2)
    elif comp == "cell":
        r = draw_cell(plane, y, x, um, nuclei)
    elif comp == "cytoplasm":
        r = draw_cytoplasm(plane, y, x, um, nuclei)
    elif comp == "mito":
        r = draw_mito(plane, y, x, um, float(getattr(s, "mito_k", 3.0)))
    else:
        r = None
    if r is not None:
        r.kind = comp
    return r


# ==========================================================================
#  Auto-select: only the OBVIOUS ones
# ==========================================================================
def _solidity(m: np.ndarray) -> float:
    from skimage.morphology import convex_hull_image
    a = float(m.sum())
    if a < 9:
        return 0.0
    return a / max(1.0, float(convex_hull_image(m).sum()))


def _peaks(plane: np.ndarray, um: float, smooth_um: float, spacing_um: float,
           k_noise: float) -> List[Tuple[int, int]]:
    """Bright spots: local maxima of the smoothed channel, well above its noise."""
    sm = ndi.gaussian_filter(plane.astype(np.float32), max(1.0, _px(smooth_um, um)))
    sub = sm[::4, ::4]
    bg = float(np.median(sub))
    noise = _robust_noise((sub - bg).ravel())
    size = int(max(3, round(_px(spacing_um, um))))
    peak = (sm == ndi.maximum_filter(sm, size=size)) & (sm > bg + k_noise * noise)
    ys, xs = np.nonzero(peak)
    order = np.argsort(-sm[ys, xs])
    return [(int(ys[i]), int(xs[i])) for i in order]


def _plane_noise(plane: np.ndarray) -> float:
    """Pixel noise of the image background (robust: the cells do not count)."""
    sub = plane[::4, ::4].astype(np.float32)
    lo = sub[sub <= np.percentile(sub, 50)]
    return _robust_noise((lo - np.median(lo)).ravel())


def _snr(plane: np.ndarray, r: Roi, um: float, noise: Optional[float] = None) -> float:
    """How far the ROI's inside is above its surroundings, in units of the image
    background's pixel noise."""
    H, W = plane.shape
    pad = int(_px(6.0, um))
    y0, x0, y1, x1 = r.bbox
    a0, b0, a1, b1 = max(0, y0 - pad), max(0, x0 - pad), min(H, y1 + pad), min(W, x1 + pad)
    crop = plane[a0:a1, b0:b1].astype(np.float32)
    m = np.zeros(crop.shape, bool)
    m[y0 - a0:y1 - a0, x0 - b0:x1 - b0] = _shape(r)
    ring = ndi.binary_dilation(m, iterations=int(max(2, _px(3.0, um)))) & ~m
    if not ring.any() or not m.any():
        return 0.0
    bg = float(np.percentile(crop[ring], 25))
    if noise is None:
        noise = _plane_noise(plane)
    return (float(np.mean(crop[m])) - bg) / max(noise, 1e-6)


@dataclass
class DetectParams:
    """V2.9: what AUTO-DETECT keeps as an 'obvious' nucleus (see _auto_nuclei) -
    the fixed limits of every version, gathered in one place."""
    min_area_um2: float = 30.0
    max_area_um2: float = 1000.0
    min_solidity: float = 0.80
    min_lift_noise: float = 3.0       # lift above its surroundings, x the noise SD
    min_lift_top: float = 0.015       # ... and x the 90th-percentile lift (a bright nucleus)
    dim_frac: float = 0.08            # under this x the bright lift = 'dim'
    circ_bright: float = 0.60         # circularity a bright nucleus needs
    circ_dim: float = 0.70            # ... a dim one
    dim_solidity: float = 0.88        # ... and the solidity a dim one needs
    frag_frac: float = 0.30           # smaller than this x the median kept area = fragment

    def to_dict(self) -> dict:
        return {f: float(getattr(self, f)) for f in self.__dataclass_fields__}

    @staticmethod
    def from_dict(d) -> "DetectParams":
        p = DetectParams()
        for k, v in (d or {}).items():
            if k in p.__dataclass_fields__:
                try:
                    setattr(p, k, float(v))
                except (TypeError, ValueError):
                    pass
        return p


def nucleus_candidates(plane: np.ndarray, um: float, taken: Sequence[Roi] = (),
                       tick=None, ok_edge=None) -> List[dict]:
    """V2.9: every nucleus-sized blob AUTO-DETECT looks at, outlined, with what
    it is judged on: area_um2, solidity, circ (4 pi A / P^2), lift and noise.
    (Permissive: 10-3000 um2, solidity >= 0.5 - the limits are applied by
    filter_candidates.)"""
    return _auto_nuclei(plane, um, taken, tick or (lambda f, m: None),
                        ok_edge or (lambda r: True), cands_only=True)


def filter_candidates(cand: List[dict], prm: "DetectParams") -> List[dict]:
    """The candidates AUTO-DETECT keeps with these limits (in order)."""
    use = [c for c in cand if prm.min_area_um2 <= c["area_um2"] <= prm.max_area_um2
           and c["solidity"] >= prm.min_solidity]
    if not use:
        return []
    top = float(np.percentile([c["lift"] for c in use], 90))
    out = [c for c in use if c["lift"] >= max(prm.min_lift_noise * c["noise"],
                                              prm.min_lift_top * top)
           and c["circ"] >= (prm.circ_bright if c["lift"] >= prm.dim_frac * top else prm.circ_dim)
           and (c["lift"] >= prm.dim_frac * top or c["solidity"] >= prm.dim_solidity)]
    if out:                                        # drop odd fragments of the rest
        med = float(np.median([c["roi"].area for c in out]))
        out = [c for c in out if c["roi"].area >= prm.frag_frac * med]
    for c in use:
        c["top"] = top
    return out


def _auto_nuclei(plane: np.ndarray, um: float, taken: Sequence[Roi], tick, ok_edge,
                 params: Optional["DetectParams"] = None, cands_only: bool = False):
    """
    The obvious nuclei of a channel:
      1  candidates = NUCLEUS-SIZED blobs (difference of Gaussians, 1.5 / 5 um):
         specks and fine texture do not respond, bright and dim nuclei do;
      2  each outlined like a click (edge 35 % of the way from the local background
         up to the nucleus's typical inside brightness - specks inside cannot
         shrink it);
      3  touching nuclei split along the dim line between them (one per blob centre);
      4  kept only if obvious: 30-1000 um2, compact (solidity >= 0.80), not at the
         edge, and lifted above its own surroundings by at least 3 noise SDs AND
         1.5 % of the 90th-percentile lift of all candidates (a typical bright
         nucleus); round enough (circularity 4 pi area / perimeter^2 >= 0.6, or
         >= 0.7 for a dim one - lift under 8 % of that bright lift - which must
         also have solidity >= 0.88); fragments under 30 % of the median kept
         area are dropped.
    """
    from skimage.segmentation import watershed
    H, W = plane.shape
    f = plane.astype(np.float32)
    tick(0.05, "Finding nucleus-sized blobs...")
    dog = ndi.gaussian_filter(f, max(1.0, _px(1.5, um))) - ndi.gaussian_filter(f, max(2.0, _px(5.0, um)))
    sub = dog[::4, ::4]
    dnoise = _robust_noise((sub - np.median(sub)).ravel())
    peak = (dog == ndi.maximum_filter(dog, size=int(max(3, round(_px(6.0, um)))))) & (dog > 6 * dnoise)
    ys, xs = np.nonzero(peak)
    order = np.argsort(-dog[ys, xs])[:3000]
    seeds = list(zip(ys[order].tolist(), xs[order].tolist()))
    seed_img = np.zeros((H, W), bool)
    seed_img[ys, xs] = True
    tick(0.2, f"Checking {len(seeds)} nucleus-sized blobs...")
    sm = ndi.gaussian_filter(f, max(1.0, _px(0.8, um)))            # as for a click
    claimed = _paint(list(taken), (H, W), 0, 0)
    cand: list = []
    for i, (y, x) in enumerate(seeds):
        if i % 40 == 0:
            tick(0.2 + 0.75 * i / max(1, len(seeds)), f"Checking blob {i + 1} of {len(seeds)}...")
        if claimed[y, x]:
            continue
        res = None
        for half_um in (25.0, 45.0):
            half = int(_px(half_um, um))
            y0, y1, x0, x1 = max(0, y - half), min(H, y + half), max(0, x - half), min(W, x + half)
            res = _nucleus_at(sm[y0:y1, x0:x1], plane[y0:y1, x0:x1], y - y0, x - x0, um)
            if res is None or not res["touches_edge"]:
                break
        if res is None or res["touches_edge"]:
            continue
        m = res["mask"] & ~claimed[y0:y1, x0:x1]
        if not m[y - y0, x - x0]:
            continue
        inside = seed_img[y0:y1, x0:x1] & m
        if inside.sum() >= 2 and _solidity(m) < 0.85:     # two nuclei touching: split
            markers, n = ndi.label(ndi.binary_dilation(inside, iterations=int(_px(1.5, um))) & m)
            if n >= 2:
                ws = watershed(-sm[y0:y1, x0:x1], markers, mask=m)
                parts = [ws == j for j in range(1, n + 1)]
                # only a real split: every part nucleus-sized and rounder than the whole
                if all(p.sum() * um * um >= 30.0 and _solidity(p) >= 0.85 for p in parts):
                    m = ws == ws[y - y0, x - x0]
        m = _keep_component(m, y - y0, x - x0)
        claimed[y0:y1, x0:x1] |= m                 # this blob is decided either way
        r = _to_roi(m, y0, x0)
        if r is None or not ok_edge(r):
            continue
        a = r.area * um * um
        sol = _solidity(r.mask)
        if not (10.0 <= a <= 3000.0) or sol < 0.5:      # V2.9: permissive here, the limits
            continue                                    # are applied below (params)
        cand.append(dict(roi=r, lift=float(res["inner"] - res["bg"]),
                         noise=float(res["noise"]), area_um2=float(a), solidity=float(sol)))
    if not cand:
        return []
    # OBVIOUS = clearly visible next to the bright nuclei of this image: lifted
    # above the background by >= 1.5 % of a typical bright nucleus (90th
    # percentile) and >= 3 noise SDs; round (circularity >= 0.6); the dimmer ones
    # (under 8 %) must be rounder (circularity >= 0.7, solidity >= 0.88)
    from skimage.measure import perimeter

    def smooth(m: np.ndarray) -> float:            # 1 = circle; ragged blobs score low
        p = perimeter(np.pad(m, 1))
        return float(4 * np.pi * m.sum() / max(p * p, 1e-6))
    for c in cand:
        c["circ"] = smooth(c["roi"].mask)
    if cands_only:
        return cand
    out = filter_candidates(cand, params or DetectParams())
    return [c["roi"] for c in out]


def auto_select(plane: np.ndarray, comp: str, um: float, s, nuclei: Sequence[Roi] = (),
                taken: Sequence[Roi] = (), seed_nuclei: Optional[Sequence[Roi]] = None,
                progress: ProgressFn = None) -> List[Roi]:
    """
    The OBVIOUS ones of this compartment on this channel - clearly above the
    background, a sensible size and shape, not cut off by the image edge.
    Conservative on purpose: add the rest by clicking.

    nucleus           bright spots of the channel, outlined like a click
    cell / cytoplasm  one per nucleus you already have (else bright cell cores)
    / mito
    taken: ROIs of this compartment that already exist (never duplicated).
    """
    H, W = plane.shape
    edge = int(_px(2.0, um))
    out: List[Roi] = []
    noise = _plane_noise(plane)

    def tick(f: float, msg: str) -> None:
        if progress and not progress(f, msg):
            raise Cancelled()

    def ok_edge(r: Roi) -> bool:
        y0, x0, y1, x1 = r.bbox
        return y0 > edge and x0 > edge and y1 < H - edge and x1 < W - edge

    def is_taken(y: int, x: int) -> bool:
        for t in list(taken) + out:
            ty0, tx0, ty1, tx1 = t.bbox
            if ty0 <= y < ty1 and tx0 <= x < tx1 and _shape(t)[y - ty0, x - tx0]:
                return True
        return False

    if comp == "nucleus":
        prm = DetectParams()
        out = _auto_nuclei(plane, um, taken, tick, ok_edge, params=prm)
    else:
        seeds: List[Tuple[int, int]] = []
        if nuclei:
            for n in (nuclei if seed_nuclei is None else seed_nuclei):  # beside each nucleus
                cy, cx = n.centroid
                rad = _eq_diam(n) / 2
                best = None
                for a in np.linspace(0, 2 * np.pi, 16, endpoint=False):
                    py, px = int(cy + 1.5 * rad * np.sin(a)), int(cx + 1.5 * rad * np.cos(a))
                    if 0 <= py < H and 0 <= px < W and (best is None or plane[py, px] > best[0]):
                        best = (plane[py, px], py, px)
                if best is not None:
                    seeds.append((best[1], best[2]))
        else:
            seeds = _peaks(plane, um, 4.0, 12.0, 8.0)[:600]
        for i, (y, x) in enumerate(seeds):
            if i % 10 == 0:
                tick(0.1 + 0.8 * i / max(1, len(seeds)), f"Checking cell {i + 1} of {len(seeds)}...")
            if is_taken(y, x):
                continue
            r = draw_at(comp, plane, y, x, um, s, nuclei)
            if r is None or not ok_edge(r):
                continue
            a = _shape(r).sum() * um * um
            if not (60.0 <= a <= 8000.0) or _snr(plane, r, um, noise) < 5.0:
                continue
            r2, frac = cut_overlaps(r, list(taken) + out)
            if r2 is None or frac < 0.7:
                continue
            out.append(r2)
    for r in out:
        r.kind, r.source = comp, "auto"
    tick(1.0, f"Detected {len(out)} {LABELS[comp].lower()} ROIs.")
    return out


def cut_overlaps(roi: Roi, others: Sequence[Roi]) -> Tuple[Optional[Roi], float]:
    """
    The new ROI minus the same-compartment ROIs of other cells (two cells never
    share pixels). Returns (trimmed ROI or None if nothing is left, kept fraction).
    """
    y0, x0, y1, x1 = roi.bbox
    shown = _shape(roi)
    before = float(shown.sum())
    if before == 0:
        return None, 0.0
    taken = _paint([Roi(o.bbox, _shape(o), o.kind) for o in others if o is not None],
                   shown.shape, y0, x0)
    if not taken.any():
        return roi, 1.0
    keep = shown & ~taken
    frac = float(keep.sum()) / before
    if not keep.any():
        return None, 0.0
    keep = _keep_component(keep, *np.unravel_index(int(np.argmax(
        ndi.distance_transform_edt(keep))), keep.shape))
    mask = roi.mask & keep
    if getattr(roi, "outline", None) is not None:
        out = _to_roi(mask if mask.any() else keep, y0, x0, outline=keep)
    else:
        out = _to_roi(keep, y0, x0)
    if out is None:
        return None, 0.0
    out.kind = roi.kind
    out.channel = getattr(roi, "channel", 0)
    return out, frac


def from_outline(comp: str, points, shape, plane: np.ndarray, um: float,
                 nuclei: Sequence[Roi] = (), mito_k: float = 3.0) -> Optional[Roi]:
    """An ROI drawn by hand (polygon), made into the chosen compartment."""
    poly = Roi.from_polygon(points, shape, comp)
    if poly is None or not poly.area:
        return None
    y0, x0, y1, x1 = poly.bbox
    full = poly.mask
    if comp == "cytoplasm":
        nuc = _paint(nuclei, full.shape, y0, x0) & full
        if nuc.any():
            nuc = ndi.binary_dilation(nuc, iterations=int(max(1, round(_px(0.5, um)))))
        cyto = full & ~nuc
        r = _to_roi(cyto if cyto.sum() > 0.1 * full.sum() else full, y0, x0, outline=full)
    elif comp == "mito":
        m = mito_pieces(plane[y0:y1, x0:x1], full, um, mito_k)
        r = _to_roi(m if m.any() else full, y0, x0, outline=full)
    else:
        r = _to_roi(full, y0, x0)
    if r is not None:
        r.kind = comp
    return r


# ==========================================================================
#  Background (V2.5)
# ==========================================================================
# The background region INCLUDES cells: what is subtracted is the light of the
# dish, the medium AND the autofluorescence of non-transfected cells. EVERY
# pixel of the region is used at every timepoint - nothing is left out
# (BackgroundMeter): background = sum of the region's raw pixels / their
# number, per channel and timepoint. Afterwards the background trace of every
# channel is checked (background_fluctuation): a timepoint whose background
# jumps away from its neighbours (more than BG_FLUCT_K robust SD of those
# jumps AND more than BG_FLUCT_REL of the background level), or a background
# that drifts by more than BG_DRIFT_REL over the movie, is recorded - the
# numbers are never changed. V2.7: the user is WARNED only for an object in the
# region (BG_OBJ_REL, below) or measured cells covering > BG_ROI_WARN of it.
# BG_SMOOTH_PX, BG_BRIGHT_*, BG_HALO_UM and BG_AUTO_* are used only to PLACE
# the automatic region (away from very bright objects), never to measure.
BG_SMOOTH_PX = 1.0         # Gaussian sigma (px) before the bright / moving tests
BG_BRIGHT_K = 10.0         # bright: > region median + 10 robust SD (that timepoint) ...
BG_BRIGHT_REL = 1.0        # ... and > (1 + 1.0) x region median (twice the median)
BG_HALO_UM = 1.0           # bright / moving objects widened by this
BG_ROI_MARGIN_UM = 2.0     # measured ROIs (and the automatic region's placement) keep this gap
BG_AUTO_MIN_UM = 25.0      # the automatic square never shrinks below this
BG_AUTO_FREE = 0.9         # ... at least 90 % free of bright objects (ROIs: not at all)
BG_HAND_UM = 60.0          # a clicked background region: a square this size
BG_FLUCT_K = 5.0           # a jump: > 5 robust SD of the background's own jumps ...
BG_FLUCT_REL = 0.05        # ... AND > 5 % of the background level
BG_DRIFT_REL = 0.20        # a drift: the running median changes > 20 % of the level
BG_FLUCT_WIN = 5           # running-median window (timepoints) for both tests
# V2.7: the user is warned only when an OBJECT comes into the region: per channel
# and timepoint, the share of the background value that comes from very bright
# pixels (above bright_level() of that timepoint's region pixels) - the sum of
# (pixel - region median) over those pixels / (pixels x median). A timepoint is
# flagged when that share is more than BG_OBJ_REL above its median over the
# movie (a bright cell floating in raises the background by that much). Jumps
# and drift alone (lamp flicker, focus, bleaching) are recorded, not warned
# about, and so are measured cells covering <= BG_ROI_WARN of the region.
BG_OBJ_REL = 0.03          # an object: raises the background by > 3 % of its level
BG_ROI_WARN = 0.05         # measured cells inside the region: warned above 5 %
BG_METHOD = "all pixels, object check v2.7"


def _bright_objects(stack: np.ndarray, um: float, f: int) -> np.ndarray:
    """Placement only (not a measurement): very bright objects (dead cells,
    debris) on an f x f block-averaged copy - any channel, smoothed, above
    bright_level() of the frame."""
    from .segment import _block_mean
    out = None
    for plane in stack:
        p = _block_mean(plane.astype(np.float32), f) if f > 1 else plane.astype(np.float32)
        sm = ndi.gaussian_filter(p, BG_SMOOTH_PX)
        b = sm > bright_level(p.ravel())
        out = b if out is None else (out | b[:out.shape[0], :out.shape[1]])
    return out


def bright_level(v: np.ndarray) -> float:
    """The 'very bright' level of a set of raw pixel values: above BOTH
    median + BG_BRIGHT_K robust SD and (1 + BG_BRIGHT_REL) x median."""
    med = float(np.median(v))
    noise = _robust_noise(np.asarray(v, np.float64) - med)
    return max(med + BG_BRIGHT_K * noise, (1.0 + BG_BRIGHT_REL) * med)


def auto_background(stacks: Sequence[np.ndarray], um: float, max_um: float = 150.0,
                    avoid: Sequence[Roi] = ()) -> Tuple[Optional[Roi], str]:
    """
    The automatic background region (V2.5): a LARGE square (max_um, default
    150 um) that may hold non-transfected cells. It avoids only the measured
    ROIs (`avoid`, widened by BG_ROI_MARGIN_UM) and very bright objects (dead
    cells, debris) in any of the given frames (e.g. the first, middle and last
    timepoints), widened by BG_HALO_UM. It shrinks (15 % per step, down to
    BG_AUTO_MIN_UM) only if it does not fit - it must hold no ROI pixel and be at
    least BG_AUTO_FREE free of bright objects, 5 um from the image edge. Among the places that fit, the
    freest is used (ties: nearest the image centre). The region is the whole
    square: what is left out at each timepoint is decided from that timepoint's
    pixels when it is measured (BackgroundMeter).
    """
    H, W = stacks[0].shape[1:]
    f = int(max(1, min(H, W) // 600))              # placement on a ~600 px copy
    h, w = H // f, W // f
    forbidden = np.zeros((h, w), bool)
    for st in stacks:
        b = _bright_objects(np.asarray(st), um, f)
        forbidden |= b[:h, :w]
    halo = max(1, int(round(BG_HALO_UM / max(um * f, 1e-6))))
    forbidden = ndi.binary_dilation(forbidden, iterations=halo)
    taken = np.zeros((h, w), bool)
    if avoid:
        full = _paint([Roi(r.bbox, _shape(r), r.kind) for r in avoid if r is not None and r.area],
                      (H, W), 0, 0)
        if full.any():
            small = full[:h * f, :w * f].reshape(h, f, w, f).any(axis=(1, 3)) if f > 1 else full
            gap = max(1, int(round(BG_ROI_MARGIN_UM / max(um * f, 1e-6))))
            taken = ndi.binary_dilation(small, iterations=gap)
    free = (~forbidden).astype(np.float64)
    roi = taken.astype(np.float64)
    margin = max(2, int(round(5.0 / max(um * f, 1e-6))))
    yy, xx = np.mgrid[0:h, 0:w]
    centre = np.hypot(yy - h / 2.0, xx - w / 2.0) / max(h, w)
    size_um = float(max_um)
    while size_um >= BG_AUTO_MIN_UM:
        box = int(round(size_um / max(um * f, 1e-6)))
        if box + 2 * margin < min(h, w):
            frac = ndi.uniform_filter(free, box, mode="constant", cval=0.0)
            if taken.any():                          # no ROI pixel at all inside
                frac[ndi.uniform_filter(roi, box, mode="constant", cval=0.0) > 1e-7] = 0
            e = margin + box // 2
            frac[:e, :] = frac[-e:, :] = 0
            frac[:, :e] = frac[:, -e:] = 0
            best = float(frac.max())
            if best >= BG_AUTO_FREE:
                score = np.where(frac >= best - 1e-6, -centre, -np.inf)
                cy, cx = np.unravel_index(int(np.argmax(score)), score.shape)
                y0 = int(np.clip(cy - box // 2, 0, h - box)) * f
                x0 = int(np.clip(cx - box // 2, 0, w - box)) * f
                bb = box * f
                y1, x1 = min(H, y0 + bb), min(W, x0 + bb)
                roi = Roi((y0, x0, y1, x1), np.ones((y1 - y0, x1 - x0), bool), "background")
                roi.source = "auto"
                return roi, (f"Automatic background region {size_um:.0f} x {size_um:.0f} um "
                             f"({x1 - x0} x {y1 - y0} px) at ({x0}, {y0}); it may hold "
                             f"non-transfected cells. It was placed away from very bright objects "
                             f"and the measured ROIs; every pixel of it is measured.")
        size_um *= 0.85
    return None, "No place for a background region was found - draw it by hand."


def background_at(stack: np.ndarray, y: float, x: float, um: float,
                  size_um: float = BG_HAND_UM) -> Optional[Roi]:
    """A square background region (BG_HAND_UM) centred on a click - cells
    included; what is left out is decided at every timepoint (BackgroundMeter)."""
    H, W = stack.shape[1:]
    half = int(_px(size_um / 2, um))
    yi, xi = int(round(y)), int(round(x))
    y0, y1, x0, x1 = max(0, yi - half), min(H, yi + half), max(0, xi - half), min(W, xi + half)
    if y1 - y0 < 4 or x1 - x0 < 4:
        return None
    r = Roi((y0, x0, y1, x1), np.ones((y1 - y0, x1 - x0), bool), "background")
    r.source = "click"
    return r


def background_from_outline(points, shape) -> Optional[Roi]:
    """A background region drawn by hand (freehand outline, image (x, y) points)."""
    r = Roi.from_polygon(points, shape, "background")
    if r is None or r.area < 16:
        return None
    r.source = "hand"
    return r


class BackgroundMeter:
    """
    Measures the background region at every timepoint from ALL of its raw
    pixels (see the notes above BG_SMOOTH_PX). Frames may arrive in any order
    (the tracker goes forwards from the drawn timepoint, then backwards). The
    measured ROIs of each timepoint are only COUNTED (how much of the region
    they cover, for the note) - they are not left out.
    """

    def __init__(self, region: Roi, T: int, C: int, um: float) -> None:
        self.region = region
        self.box = tuple(int(v) for v in region.bbox)
        self.mask = np.asarray(region.mask, bool)
        self.T, self.C, self.um = int(T), int(C), float(um)
        self.done = np.zeros(self.T, bool)
        self.mean = np.full((self.T, self.C), np.nan)
        self.sd = np.full((self.T, self.C), np.nan)
        self.sum = np.full((self.T, self.C), np.nan)
        self.npx = np.zeros(self.T, np.int64)
        self.obj = np.full((self.T, self.C), np.nan)    # V2.7: share from very bright pixels
        self.n_rois = np.zeros(self.T, np.int64)
        self.excluded: Dict[int, np.ndarray] = {}     # always empty: nothing is left out

    def roi_mask(self, rois: Sequence[Roi]) -> np.ndarray:
        """The measured ROIs of one timepoint (their followed regions) inside the
        region's box - counted for the overlap note, not left out."""
        return _paint_box([Roi(r.bbox, _shape(r), r.kind) for r in rois if r is not None],
                          self.box)

    def add(self, t: int, stack: np.ndarray, roi_mask: Optional[np.ndarray] = None) -> None:
        t = int(t)
        if self.done[t]:
            return
        y0, x0, y1, x1 = self.box
        m = self.mask
        raw = np.asarray(stack[:, y0:y1, x0:x1])
        n = int(m.sum())
        self.npx[t] = n
        if roi_mask is not None:
            self.n_rois[t] = int((roi_mask & m).sum())
        if n:
            vals = raw[:, m].astype(np.float64)                # every raw pixel of the region
            sm = vals.sum(axis=1)
            self.sum[t] = sm
            self.mean[t] = sm / n
            self.sd[t] = vals.std(axis=1)
            for c in range(vals.shape[0]):
                self.obj[t, c] = bright_share(vals[c])
        self.done[t] = True

    def finish(self) -> None:
        """Nothing is buffered (kept for the tracker's call)."""

    def summary(self) -> dict:
        """The region, the ROI overlap and the fluctuation check (JSON-ready,
        1-based timepoints)."""
        n_reg = int(self.mask.sum())
        roi = [round(float(x) / max(n_reg, 1), 5) for x in self.n_rois]
        out = dict(method=BG_METHOD, region_px=n_reg,
                   region_um2=round(n_reg * self.um * self.um, 3),
                   kept_px=[int(x) for x in self.npx], roi_frac=roi,
                   roi_frames=[t + 1 for t, f in enumerate(roi) if f > 0],
                   max_roi_frac=round(max(roi, default=0.0), 5),
                   frames_with_objects=[], max_object_frac=0.0)
        out.update(background_fluctuation(self.mean))
        out.update(background_objects(self.obj))
        return out


def bright_share(v: np.ndarray) -> float:
    """V2.7: the share of the mean of raw pixel values v that comes from very
    bright pixels (above bright_level(v)): sum(v - median) over them /
    (len(v) x median). 0 when nothing is very bright."""
    v = np.asarray(v, np.float64)
    if v.size == 0:
        return float("nan")
    med = float(np.median(v))
    if med <= 0:
        return 0.0
    b = v[v > bright_level(v)]
    return float((b - med).sum() / (v.size * med)) if b.size else 0.0


def background_objects(obj: np.ndarray) -> dict:
    """V2.7: objects in the background region. obj: (T, C) bright_share per
    channel and timepoint. A timepoint is flagged when, in any channel, the
    share is more than BG_OBJ_REL above that channel's median share over the
    movie. Returns obj_frames (1-based), obj_rel_max per channel (largest rise
    above the median share) and the limit."""
    obj = np.asarray(obj, float)
    frames, rel = set(), []
    for c in range(obj.shape[1] if obj.ndim == 2 else 0):
        s = obj[:, c]
        ok = np.isfinite(s)
        if not ok.any():
            rel.append(0.0)
            continue
        rise = np.where(ok, s - float(np.median(s[ok])), np.nan)
        rel.append(round(float(np.nanmax(rise)), 5))
        frames.update(int(t) + 1 for t in np.nonzero(np.nan_to_num(rise) > BG_OBJ_REL)[0])
    return dict(obj_frames=sorted(frames), obj_rel_max=rel, obj_rel=BG_OBJ_REL,
                roi_warn=BG_ROI_WARN)


def background_fluctuation(mean: np.ndarray) -> dict:
    """
    The fluctuation check of a (T, C) background trace (it never changes it).
    Per channel: trend = running median over BG_FLUCT_WIN timepoints;
    jump = background - trend; a timepoint is flagged when |jump| is more than
    BG_FLUCT_K x the robust SD of all jumps (1.4826 x median absolute
    deviation) AND more than BG_FLUCT_REL x the background level (median of
    the trace). Drift = (largest - smallest trend) / level.
    """
    mean = np.asarray(mean, float)
    T, C = mean.shape if mean.ndim == 2 else (0, 0)
    chans = []
    for c in range(C):
        b = mean[:, c]
        ok = np.isfinite(b)
        if ok.sum() < max(3, BG_FLUCT_WIN):
            chans.append(dict(level=None, jump_frames=[], max_jump_rel=0.0, drift_rel=0.0))
            continue
        h = BG_FLUCT_WIN // 2
        trend = np.array([np.nanmedian(b[max(0, t - h):t + h + 1])
                          if np.isfinite(b[max(0, t - h):t + h + 1]).any() else np.nan
                          for t in range(T)])
        level = float(np.nanmedian(b))
        jump = b - trend
        jv = jump[ok & np.isfinite(jump)]
        noise = 1.4826 * float(np.median(np.abs(jv - np.median(jv))))
        lim = max(BG_FLUCT_K * noise, BG_FLUCT_REL * abs(level))
        big = np.isfinite(jump) & (np.abs(np.nan_to_num(jump)) > lim)
        flag = [int(t) + 1 for t in np.nonzero(big)[0]]
        rel = np.abs(jv) / max(abs(level), 1e-9)
        tr = trend[np.isfinite(trend)]
        drift = float((tr.max() - tr.min()) / max(abs(level), 1e-9)) if tr.size else 0.0
        chans.append(dict(level=round(level, 4), jump_frames=flag,
                          max_jump_rel=round(float(rel.max()) if rel.size else 0.0, 5),
                          drift_rel=round(drift, 5)))
    return dict(fluct=chans, fluct_k=BG_FLUCT_K, fluct_rel=BG_FLUCT_REL,
                drift_rel_limit=BG_DRIFT_REL, fluct_win=BG_FLUCT_WIN)


def background_params(um: float) -> dict:
    """The background constants (JSON-ready, for the methods record)."""
    return dict(method=BG_METHOD, all_pixels=True,
                obj_rel=float(BG_OBJ_REL), roi_warn=float(BG_ROI_WARN),
                fluct_k=float(BG_FLUCT_K), fluct_rel=float(BG_FLUCT_REL),
                drift_rel=float(BG_DRIFT_REL), fluct_win=int(BG_FLUCT_WIN),
                smooth_px=float(BG_SMOOTH_PX), bright_k=float(BG_BRIGHT_K),
                bright_rel=float(BG_BRIGHT_REL), halo_um=float(BG_HALO_UM),
                roi_margin_um=float(BG_ROI_MARGIN_UM), auto_min_um=float(BG_AUTO_MIN_UM),
                auto_free=float(BG_AUTO_FREE), hand_square_um=float(BG_HAND_UM),
                roi_margin_px=int(max(1, round(_px(BG_ROI_MARGIN_UM, um)))))


def _ranges(ts) -> str:
    """[1, 2, 3, 7] -> '1-3, 7'."""
    out, start, prev = [], None, None
    for t in ts:
        if start is None:
            start = prev = t
        elif t == prev + 1:
            prev = t
        else:
            out.append(f"{start}" if start == prev else f"{start}-{prev}")
            start = prev = t
    if start is not None:
        out.append(f"{start}" if start == prev else f"{start}-{prev}")
    return ", ".join(out)


def background_warning(info: dict, hand: bool = True,
                       channels: Optional[Sequence[str]] = None) -> str:
    """Plain-language note ('' when there is nothing to fix). V2.7: only when a
    bright object came into the region (background_objects) or measured cells
    cover more than BG_ROI_WARN of it. Jumps and drift alone (lamp flicker,
    focus, bleaching) are recorded in the methods but not warned about - they
    affect the cells as much as the background. Nothing is left out either way.
    Records made before V2.7 (no object check) give no note."""
    if not info or "obj_frames" not in info:
        return ""
    names = list(channels or [])
    bits = []
    fr = list(info.get("obj_frames") or [])
    if fr:
        rel = list(info.get("obj_rel_max") or [])
        worst = max(range(len(rel)), key=lambda c: rel[c]) if rel else None
        who = (f" (most in {names[worst] if worst < len(names) else f'channel {worst + 1}'}: "
               f"+{rel[worst]:.0%} of its level)") if worst is not None else ""
        bits.append(f"a bright object is in it at timepoint(s) {_ranges(fr)}{who}")
    limit = float(info.get("roi_warn", BG_ROI_WARN))
    roi = list(info.get("roi_frac") or [])
    rf = [t + 1 for t, f in enumerate(roi) if f > limit]
    if rf:
        bits.append(f"measured cells cover up to {float(info.get('max_roi_frac') or 0):.1%} "
                    f"of it (timepoint(s) {_ranges(rf)})")
    if not bits:
        return ""
    return ("Background region: " + "; ".join(bits) + ". Every pixel of the region was used "
            "as it is - redraw the background if you want a region without it.")


# ==========================================================================
#  Which cell does a new ROI belong to?
# ==========================================================================
def _shape(r: Roi) -> np.ndarray:
    return r.outline if getattr(r, "outline", None) is not None else r.mask


def _eq_diam(r: Roi) -> float:
    return 2.0 * np.sqrt(max(1.0, float(_shape(r).sum())) / np.pi)


def _overlap(a: Roi, b: Roi, grow: int) -> bool:
    ay0, ax0, ay1, ax1 = a.bbox
    by0, bx0, by1, bx1 = b.bbox
    y0, x0 = min(ay0, by0) - grow, min(ax0, bx0) - grow
    y1, x1 = max(ay1, by1) + grow, max(ax1, bx1) + grow
    if max(ay0, by0) - grow > min(ay1, by1) + grow or max(ax0, bx0) - grow > min(ax1, bx1) + grow:
        return False
    A = np.zeros((y1 - y0, x1 - x0), bool)
    B = np.zeros_like(A)
    A[ay0 - y0:ay1 - y0, ax0 - x0:ax1 - x0] = _shape(a)
    B[by0 - y0:by1 - y0, bx0 - x0:bx1 - x0] = _shape(b)
    if grow:
        A = ndi.binary_dilation(A, iterations=grow)
    return bool((A & B).any())


def link_cell(cells: Sequence[Dict[str, Roi]], roi: Roi, comp: str, um: float,
              skip: Sequence[int] = ()) -> int:
    """
    Index of the cell this new ROI belongs to, or -1 for a new cell. A cell
    that already has this compartment is never chosen. Touching (within 1 um)
    wins; otherwise the nearest cell whose ROIs are within about half a cell
    diameter of each other.
    """
    grow = int(max(1, round(_px(1.0, um))))
    cy, cx = roi.centroid
    best, best_d = -1, np.inf
    for k, cell in enumerate(cells):
        if k in skip or not cell or comp in cell:
            continue
        for other in cell.values():
            if other is None or not other.area:
                continue
            if _overlap(roi, other, grow):
                d = 0.0
            else:
                oy, ox = other.centroid
                d = float(np.hypot(cy - oy, cx - ox))
                if d > 0.5 * (_eq_diam(roi) + _eq_diam(other)) + _px(3.0, um):
                    continue
            if d < best_d:
                best, best_d = k, d
    return best


# ==========================================================================
#  Tracking: every ROI is REDRAWN at every timepoint
# ==========================================================================
# Each frame, for each cell:
#   1  movement: sub-pixel image shift around the cell's first ROI between this
#      frame and the previous one (kept as a running sub-pixel total, so slow
#      drift is never rounded away);
#   2  redraw: around the moved outline, the ROI is re-thresholded in this frame
#      at the SAME relative edge level it had when you clicked (where its edge
#      sat between the local background and its inside) - so it follows shape
#      changes and brightening / dimming alike;
#   3  neighbours: pixels nearer another tracked cell belong to that cell, and
#      other cells' nuclei are never taken - two cells never share pixels;
#   4  size guard: the area may differ from the size you drew by at most
#      +/- size_tol (25 %) and from the frame before by at most 1.5x - a redraw
#      outside that (e.g. a nucleus spilling into its cytoplasm or a neighbour)
#      is RE-FITTED to the nearest allowed size around where the cell is; if
#      even that fails, or it no longer overlaps where the cell was, the moved
#      outline is used and that frame is flagged (quality 0.3, QC notes it);
#   5  V2.5 hard limits: the followed region never has more than
#      (1 + size_tol) x or fewer than (1 - size_tol) x the pixels you drew
#      (_exact_area trims to the brightest connected pixels of the redrawn
#      outline / grows by the brightest neighbouring pixels, never into another
#      cell or across a boundary line); size_tol = 0 = EXACTLY the drawn count;
#      two cells' ROIs never overlap in the same frame (_resolve_overlaps) and an
#      ROI never crosses its cell's boundary lines (boundary_side).
# V2.5 rule lock: every rule follows the cell exactly as ONLY does, on channel
# A's raw pixels. The second channel can only TRIM the measured pixels inside
# that outline (AND: where B is bright; WITH: where the combined A+B image is
# above the outline's own edge level) or exclude cells (IF) - never make the
# ROI larger than the ONLY outline.
# The clicked frame itself is outlined the same way (from your click's shape),
# so every timepoint is outlined by one method - no step between frame 1 and 2.
# Measurements are always read from the raw pixels under the final mask:
# mean = sum of the pixels / number of pixels.

SIGMA_UM = {"nucleus": 0.6, "cell": 1.0, "cytoplasm": 1.0, "mito": 2.0}
# Tracker constants (named so the methods record, track_cells()["params"], can
# quote them; the values are those of V2.2):
SIGMA_MIN_PX = 0.8            # smoothing never below 0.8 px (Gaussian sigma)
RING_UM = 4.0                 # local background: a ring this wide around the region
RING_BG_PCT = 20              # ... its 20th percentile is the background level
EDGE_PAD_UM = 10.0            # window around the region for the edge level
EDGE_LEVEL_CLIP = (0.12, 0.8)  # edge level (0 = background, 1 = inside) kept in this range
AREA_STEP = (0.67, 1.5)       # size guard: area vs the frame before, at most this change
FIRST_FRAME_TOL = 0.10        # the clicked frame: within 10 % of the size you drew
REFIT_ACCEPT = (0.95, 1.05)   # a re-fitted outline must land within this slack of the range
MIN_OVERLAP_PREV = 0.5        # >= half of a redrawn outline must lie where the cell was
MIN_HIT_FRAC = 0.05           # pieces kept if they hold >= 5 % (and >= 3 px) of the region
MARGIN_MIN_PX = 3             # search margin = max(3 px, max_move_um)
SHIFT_PAD_PX = 8              # phase correlation window = ROI box + margin + 8 px
PHASE_UPSAMPLE = 10           # phase correlation upsampling (1/10 px precision)
TRACKER = "redraw-every-frame v2.5 (rules locked to ONLY, hard size limits)"
WALL_HALF_PX = 1              # boundary lines: drawn 1 + 2 x 1 = 3 px thick (no 8-connected leak)


# ---- V2.5: tracker boundary lines (per cell, fixed in the image) ----------
def wall_mask(lines, shape) -> np.ndarray:
    """Boundary lines (each a list of image (x, y) points, a polyline) as pixels
    of the whole image, 3 px thick (WALL_HALF_PX): a region on one side cannot
    reach the other through a diagonal gap."""
    H, W = shape
    m = np.zeros((H, W), bool)
    for line in lines or ():
        pts = [(float(p[1]), float(p[0])) for p in line]
        if len(pts) == 1:
            pts = pts * 2
        for (ya, xa), (yb, xb) in zip(pts[:-1], pts[1:]):
            n = int(np.ceil(max(abs(ya - yb), abs(xa - xb)) * 4)) + 2
            yy = np.linspace(ya, yb, n).round().astype(int)
            xx = np.linspace(xa, xb, n).round().astype(int)
            ok = (yy >= 0) & (yy < H) & (xx >= 0) & (xx < W)
            m[yy[ok], xx[ok]] = True
    if m.any() and WALL_HALF_PX > 0:
        m = ndi.binary_dilation(m, structure=np.ones((3, 3), bool), iterations=WALL_HALF_PX)
    return m


def boundary_side(lines, shape, region: Roi) -> Optional[np.ndarray]:
    """The pixels a cell may use (whole image, bool): the connected part of the
    image outside its boundary lines that holds most of its region. None when
    the cell has no lines."""
    wall = wall_mask(lines, shape)
    if not wall.any():
        return None
    lab, n = ndi.label(~wall)                       # 4-connected parts between the lines
    y0, x0, y1, x1 = region.bbox
    hits = np.bincount(lab[y0:y1, x0:x1][_shape(region)].ravel(), minlength=n + 1)
    hits[0] = 0
    if hits.max() > 0:
        k = int(np.argmax(hits))
    else:                                           # the region sits on the line itself
        cy, cx = (int(round(v)) for v in region.centroid)
        _d, (iy, ix) = ndi.distance_transform_edt(lab == 0, return_indices=True)
        k = int(lab[iy[cy, cx], ix[cy, cx]])
    return lab == k


def _grow_bright(m: np.ndarray, sm: np.ndarray, allowed: np.ndarray, n: int) -> np.ndarray:
    """m grown to n pixels by repeatedly adding the brightest (sm) pixels that
    touch it, never into allowed=False pixels (other cells, boundary lines) -
    always connected. Fewer than n if there is no more room."""
    cur = m.copy()
    cross = ndi.generate_binary_structure(2, 1)
    while True:
        need = int(n) - int(cur.sum())
        if need <= 0:
            return cur
        front = ndi.binary_dilation(cur, structure=cross) & allowed & ~cur
        if not front.any():
            return cur
        ys, xs = np.nonzero(front)
        if ys.size > need:
            pick = np.argsort(-sm[ys, xs], kind="stable")[:need]
            ys, xs = ys[pick], xs[pick]
        cur[ys, xs] = True


def _exact_area(m: np.ndarray, sm: np.ndarray, allowed: np.ndarray, n: int) -> np.ndarray:
    """
    Exactly n pixels from a redrawn outline m (V2.5 hard size limit; size 0 %):
      too big    the n brightest CONNECTED pixels of m around its middle (its
                 deepest point): the highest guide level whose piece holding the
                 middle still has >= n pixels is found, and the piece of the next
                 level up is grown inside it by the brightest touching pixels;
      too small  m grown by the brightest neighbouring pixels (_grow_bright),
                 never into other cells or across boundary lines.
    """
    n = int(max(1, n))
    a = int(m.sum())
    if a == n or a == 0:
        return m
    if a < n:
        return _grow_bright(m, sm, allowed | m, n)
    edt = ndi.distance_transform_edt(m)
    cy, cx = np.unravel_index(int(np.argmax(edt)), m.shape)
    vals = np.unique(sm[m])
    vals = vals[vals <= sm[cy, cx]]

    def piece(level: float) -> np.ndarray:
        return _keep_component(m & (sm >= level), cy, cx)
    whole = piece(vals[0])
    if whole.sum() < n:                         # m is in pieces: keep the middle one whole
        rest = m & ~whole                       # and add the brightest pixels of the others
        ys, xs = np.nonzero(rest)
        pick = np.argsort(-sm[ys, xs], kind="stable")[:n - int(whole.sum())]
        out = whole.copy()
        out[ys[pick], xs[pick]] = True
        return out
    lo, hi = 0, len(vals) - 1                   # piece(vals[lo]) >= n; find the highest such
    if piece(vals[hi]).sum() >= n:
        lo = hi
    else:
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if piece(vals[mid]).sum() >= n:
                lo = mid
            else:
                hi = mid
    big = piece(vals[lo])
    small = piece(vals[lo + 1]) if lo + 1 < len(vals) else np.zeros_like(m)
    if not small.any():
        small = np.zeros_like(m)
        small[cy, cx] = True
    return _grow_bright(small, sm, big, n)


def _box(bbox, pad: int, H: int, W: int):
    y0, x0, y1, x1 = bbox
    return max(0, y0 - pad), max(0, x0 - pad), min(H, y1 + pad), min(W, x1 + pad)


def _paint_box(rois: Sequence[Roi], box, shape_fn=None) -> np.ndarray:
    by0, bx0, by1, bx1 = box
    out = np.zeros((by1 - by0, bx1 - bx0), bool)
    for r in rois:
        if r is None or not r.area:
            continue
        m = shape_fn(r) if shape_fn else r.mask
        y0, x0, y1, x1 = r.bbox
        a0, b0 = max(y0, by0), max(x0, bx0)
        a1, b1 = min(y1, by1), min(x1, bx1)
        if a1 <= a0 or b1 <= b0:
            continue
        out[a0 - by0:a1 - by0, b0 - bx0:b1 - bx0] |= m[a0 - y0:a1 - y0, b0 - x0:b1 - x0]
    return out


def _region(r: Roi) -> Roi:
    """The filled shape that is followed (outline for cytoplasm / mito)."""
    if getattr(r, "outline", None) is not None:
        return Roi(r.bbox, r.outline, r.kind)
    return r


def _edge_level(plane: np.ndarray, region: Roi, comp: str, um: float) -> float:
    """Where the outline sits between local background (0) and the ROI's inside (1)."""
    H, W = plane.shape
    pad = int(_px(EDGE_PAD_UM, um))
    box = _box(region.bbox, pad, H, W)
    by0, bx0, by1, bx1 = box
    sm = ndi.gaussian_filter(plane[by0:by1, bx0:bx1].astype(np.float32),
                             max(SIGMA_MIN_PX, _px(SIGMA_UM[comp], um)))
    P = _paint_box([region], box)
    if P.sum() < 9:
        return 0.5
    ring = ndi.binary_dilation(P, iterations=int(max(2, _px(RING_UM, um)))) & ~P
    bg = float(np.percentile(sm[ring], RING_BG_PCT)) if ring.any() else float(np.percentile(sm, 10))
    inner = float(np.median(sm[P]))
    edge = P & ~ndi.binary_erosion(P)
    e = float(np.median(sm[edge])) if edge.any() else bg + 0.5 * (inner - bg)
    if inner - bg <= 1e-6:
        return 0.5
    return float(np.clip((e - bg) / (inner - bg), *EDGE_LEVEL_CLIP))


def _redraw(plane: np.ndarray, pred: Roi, comp: str, level: float, um: float,
            margin: int, rivals: Sequence[Roi], walls: Sequence[Roi],
            ref_area: Optional[float] = None, tol: float = 0.25,
            side: Optional[np.ndarray] = None) -> Optional[Roi]:
    """
    Re-outline one ROI in this frame around its predicted (moved) region.
    rivals: other cells' regions of the same compartment (pixels nearer them are
    theirs); walls: pixels never taken (other cells' nuclei); side: the pixels
    this cell may use (boundary_side, whole image) or None. None = rejected.
    """
    H, W = plane.shape
    pad = margin + int(_px(RING_UM, um))
    box = _box(pred.bbox, pad, H, W)
    by0, bx0, by1, bx1 = box
    if by1 - by0 < 4 or bx1 - bx0 < 4:
        return None
    sm = ndi.gaussian_filter(plane[by0:by1, bx0:bx1].astype(np.float32),
                             max(SIGMA_MIN_PX, _px(SIGMA_UM[comp], um)))
    P = _paint_box([pred], box)
    a_prev = int(P.sum())
    if a_prev < 9:
        return None
    allowed = ndi.binary_dilation(P, iterations=margin)
    near = [r for r in rivals if r is not None and r.area and
            r.bbox[0] < by1 and r.bbox[2] > by0 and r.bbox[1] < bx1 and r.bbox[3] > bx0]
    R = _paint_box(near, box) if near else np.zeros_like(P)
    if R.any():                                   # pixels nearer a neighbour are its own
        d_own = ndi.distance_transform_edt(~P)
        d_riv = ndi.distance_transform_edt(~R)
        allowed &= (d_own < d_riv) & ~R
    wall = _paint_box(walls, box)
    if wall.any():
        allowed &= ~wall
    if side is not None:                          # V2.5: never across a boundary line
        allowed &= side[by0:by1, bx0:bx1]
    # local background: the same 4 um ring as on the clicked frame, minus neighbours
    ring = ndi.binary_dilation(P, iterations=int(max(2, _px(RING_UM, um)))) & ~P & ~R & ~wall
    bg = float(np.percentile(sm[ring], RING_BG_PCT)) if ring.sum() >= 20 else float(np.percentile(sm, 10))
    inner = float(np.median(sm[P]))
    if inner - bg <= 1e-6:
        return None
    cand = (sm > bg + level * (inner - bg)) & allowed
    lab, n = ndi.label(cand)
    new = None
    if n:
        hits = np.bincount(lab[P].ravel(), minlength=n + 1)
        hits[0] = 0
        keep = np.nonzero(hits >= max(3, MIN_HIT_FRAC * a_prev))[0]
        if keep.size:
            new = ndi.binary_fill_holes(np.isin(lab, keep)) & allowed
    # size guard: the area may differ from the size you drew by at most `tol`
    # (and from the frame before by at most 1.5x); outside that the outline is
    # re-fitted to the nearest allowed size around where the cell is
    lo_a, hi_a = AREA_STEP[0] * a_prev, AREA_STEP[1] * a_prev
    if ref_area:
        lo_a, hi_a = max(lo_a, (1 - tol) * ref_area), min(hi_a, (1 + tol) * ref_area)
        if lo_a > hi_a:                          # frame before was off: back towards ref
            lo_a = hi_a = float(np.clip(a_prev, (1 - tol) * ref_area, (1 + tol) * ref_area))
    a_new = int(new.sum()) if new is not None else 0
    fitted = None
    if new is None or not (lo_a <= a_new <= hi_a):
        target = float(np.clip(a_new, lo_a, hi_a)) if a_new else 0.5 * (lo_a + hi_a)
        core = ndi.binary_erosion(P, iterations=int(max(1, _px(1.0, um)))) if a_prev > 50 else P
        new, fitted = fit_area(sm, allowed, core if core.any() else P, bg, inner, target)
        a_new = int(new.sum())
        if not (REFIT_ACCEPT[0] * lo_a <= a_new <= REFIT_ACCEPT[1] * hi_a):
            return None
    if not a_new or (new & P).sum() < MIN_OVERLAP_PREV * a_new:
        return None                              # it left where the cell was
    if ref_area:                                 # V2.5: hard limits, no slack
        n_lo, n_hi = size_limits(ref_area, tol)
        if not (n_lo <= a_new <= n_hi):
            new = _exact_area(new, sm, allowed, n_hi if a_new > n_hi else n_lo)
            if not new.any():
                return None
    ys, xs = np.nonzero(new)
    a0, a1, b0, b1 = int(ys.min()), int(ys.max()) + 1, int(xs.min()), int(xs.max()) + 1
    out = Roi((by0 + a0, bx0 + b0, by0 + a1, bx0 + b1), new[a0:a1, b0:b1].copy(), comp)
    out.fit_level = fitted                       # the level that gave the allowed size
    return out


def size_limits(ref_area: float, tol: float) -> Tuple[int, int]:
    """(fewest, most) pixels a followed region may have: (1 -/+ tol) x the drawn
    area, rounded inwards; tol = 0 gives exactly the drawn pixel count."""
    ref = float(ref_area)
    lo = int(np.ceil((1.0 - tol) * ref - 1e-6))
    hi = int(np.floor((1.0 + tol) * ref + 1e-6))
    lo = max(1, lo)
    return lo, max(lo, hi)


RESIZE_STEP = 1.12        # one wheel notch = 12 % more / less area


def _at_level(sm: np.ndarray, allowed: np.ndarray, core: np.ndarray, bg: float, inner: float,
              level: float) -> np.ndarray:
    """The thresholded region (edge at `level` between bg and inner) that holds
    most of `core`, holes filled; empty if none."""
    cand = (sm > bg + float(level) * (inner - bg)) & allowed
    lab, n = ndi.label(cand)
    if n == 0:
        return np.zeros_like(cand)
    hits = np.bincount(lab[core].ravel(), minlength=n + 1)
    hits[0] = 0
    if hits.max() == 0:
        return np.zeros_like(cand)
    return ndi.binary_fill_holes(lab == int(np.argmax(hits))) & allowed


def _grow_to(m: np.ndarray, allowed: np.ndarray, target: float) -> np.ndarray:
    """m grown evenly outwards (never into allowed=False pixels) to `target` pixels
    (ties at the same distance: hollows are filled first, so the edge stays smooth)."""
    need = int(round(target - m.sum()))
    free = allowed & ~m
    if need <= 0 or not free.any():
        return m
    key = ndi.distance_transform_edt(~m) - 0.5 * ndi.gaussian_filter(m.astype(np.float32), 2.0)
    ys, xs = np.nonzero(free)
    kv = key[ys, xs]
    pick = np.argsort(kv, kind="stable")[:min(need, kv.size)]
    grown = m.copy()
    grown[ys[pick], xs[pick]] = True
    return _keep_component(grown, *np.unravel_index(int(np.argmax(ndi.distance_transform_edt(m))),
                                                    m.shape))


def _shrink_to(m: np.ndarray, target: float) -> np.ndarray:
    """m shrunk evenly inwards (its middle kept) to `target` pixels."""
    n = int(round(target))
    if m.sum() <= n or n < 1:
        return m
    key = ndi.distance_transform_edt(m) + 0.5 * ndi.gaussian_filter(m.astype(np.float32), 2.0)
    ys, xs = np.nonzero(m)
    pick = np.argsort(-key[ys, xs], kind="stable")[:n]
    out = np.zeros_like(m)
    out[ys[pick], xs[pick]] = True
    out = _keep_component(out, *np.unravel_index(int(np.argmax(np.where(m, key, -1))), m.shape))
    if out.sum() < 0.98 * n:                    # a lobe was cut off: refill inside m
        out = _grow_to(out, m, n)
    return out


def fit_area(sm: np.ndarray, allowed: np.ndarray, core: np.ndarray, bg: float, inner: float,
             target: float, lo: float = 0.02, hi: float = 0.98) -> Tuple[np.ndarray, Optional[float]]:
    """
    The region around `core` whose area is `target` pixels:
      * inside the image's own range: the threshold level (edge between the local
        background and the ROI's inside) that gives that area - the outline
        follows the image;
      * where the image jumps (two blobs merging at one level) or beyond its
        range (bigger than the lowest level / smaller than the highest): the
        nearest such outline grown / shrunk evenly to exactly that area (never
        into allowed=False pixels, i.e. other cells).
    Returns (mask, level used - None when it had to be grown / shrunk a lot).
    """
    target = max(4.0, float(target))
    big = _at_level(sm, allowed, core, bg, inner, lo)
    a_big = float(big.sum())
    if a_big == 0:
        return big, None
    if a_big <= target:                                   # bigger than the image allows
        return _grow_to(big, allowed, target), None
    small = _at_level(sm, allowed, core, bg, inner, hi)
    if small.any() and small.sum() >= target:             # smaller than the image allows
        return _shrink_to(small, target), None
    a, b = lo, hi                                         # area falls as the level rises
    best, best_l, best_err = big, lo, abs(a_big - target)
    for _ in range(16):
        mid = 0.5 * (a + b)
        m = _at_level(sm, allowed, core, bg, inner, mid)
        am = float(m.sum())
        if am and abs(am - target) < best_err:
            best, best_l, best_err = m, mid, abs(am - target)
        if am > target:
            a = mid
        else:
            b = mid
        if best_err <= max(2.0, 0.01 * target):
            break
    if best_err > 0.03 * target:                          # a jump in the image: even out
        best = _grow_to(best, allowed, target) if best.sum() < target else _shrink_to(best, target)
    return best, best_l


def _local(plane: np.ndarray, reg: Roi, comp: str, um: float, pad: int, others: Sequence[Roi]):
    """Smoothed crop around reg with its background / inside levels."""
    H, W = plane.shape
    box = _box(reg.bbox, pad, H, W)
    by0, bx0, by1, bx1 = box
    sm = ndi.gaussian_filter(plane[by0:by1, bx0:bx1].astype(np.float32),
                             max(0.8, _px(SIGMA_UM.get(comp, 1.0), um)))
    P = _paint_box([reg], box)
    taken = _paint_box([_region(o) for o in others if o is not None], box) & ~P
    ring = ndi.binary_dilation(P, iterations=int(max(2, _px(4.0, um)))) & ~P & ~taken
    bg = float(np.percentile(sm[ring], 20)) if ring.sum() >= 20 else float(np.percentile(sm, 10))
    inner = float(np.median(sm[P])) if P.any() else bg
    return box, sm, P, taken, bg, inner


def resize_roi(plane: np.ndarray, base: Roi, comp: str, steps: int, um: float,
               others: Sequence[Roi] = (), nucleus: Optional[Roi] = None,
               mito_k: float = 3.0) -> Optional[Roi]:
    """
    Scroll-to-resize: `base` (the ROI as it was when you started scrolling)
    redrawn with RESIZE_STEP ** steps times its area - each notch up 12 % bigger,
    each notch down 12 % smaller, with no limit either way. Within the image's
    own brightness range the outline follows the image (threshold level); past
    it the outline grows / shrinks evenly. Other cells' pixels are never taken.
    """
    reg0 = _region(base)
    a0 = float(reg0.area)
    if a0 < 4:
        return None
    target = max(6.0, a0 * RESIZE_STEP ** int(steps))
    grow_px = max(0.0, np.sqrt(target / np.pi) - np.sqrt(a0 / np.pi))
    pad = int(grow_px + _px(6.0, um)) + 2
    box, sm, P, taken, bg, inner = _local(plane, reg0, comp, um, pad, others)
    by0, bx0, by1, bx1 = box
    if P.sum() < 4:
        return None
    if inner - bg <= 1e-6:
        inner = bg + 1.0
    allowed = ~taken
    allowed[0, :] = allowed[-1, :] = allowed[:, 0] = allowed[:, -1] = False
    core = ndi.binary_erosion(P, iterations=int(max(1, _px(1.0, um)))) if P.sum() > 50 else P
    new, _lvl = fit_area(sm, allowed, core if core.any() else P, bg, inner, target)
    if not new.any():
        return None
    ys, xs = np.nonzero(new)
    a0_, a1, b0, b1 = int(ys.min()), int(ys.max()) + 1, int(xs.min()), int(xs.max()) + 1
    region = Roi((by0 + a0_, bx0 + b0, by0 + a1, bx0 + b1), new[a0_:a1, b0:b1].copy(), comp)
    hole = None
    if comp == "cytoplasm" and nucleus is None and getattr(base, "outline", None) is not None:
        hole = Roi(base.bbox, base.outline & ~base.mask, "hole")
    return _finish(comp, region, plane, um, mito_k, nucleus, hole, int(getattr(base, "channel", 0)))


# ==========================================================================
#  Editing: split one ROI in two, add a missed part to an ROI
# ==========================================================================
def _stroke_mask(points, box, width: int) -> np.ndarray:
    """A freehand line (image x, y points) as pixels of `box`, `width` thick,
    its two ends extended straight on so it crosses the whole box."""
    by0, bx0, by1, bx1 = box
    h, w = by1 - by0, bx1 - bx0
    pts = [(float(y) - by0, float(x) - bx0) for x, y in points]
    if len(pts) >= 2:
        far = float(h + w)
        for end, nxt in ((0, 1), (-1, -2)):
            (ya, xa), (yb, xb) = pts[end], pts[nxt]
            # direction from a few points in, so a wobbly end does not matter
            j = min(len(pts) - 1, 4) if end == 0 else max(0, len(pts) - 5)
            yb, xb = pts[j] if (pts[j][0], pts[j][1]) != (ya, xa) else (yb, xb)
            d = np.hypot(ya - yb, xa - xb)
            if d > 1e-6:
                ext = (ya + (ya - yb) / d * far, xa + (xa - xb) / d * far)
                pts = [ext] + pts if end == 0 else pts + [ext]
    m = np.zeros((h, w), bool)
    for (ya, xa), (yb, xb) in zip(pts[:-1], pts[1:]):
        n = int(max(abs(ya - yb), abs(xa - xb))) * 2 + 2
        yy = np.linspace(ya, yb, n).round().astype(int)
        xx = np.linspace(xa, xb, n).round().astype(int)
        ok = (yy >= 0) & (yy < h) & (xx >= 0) & (xx < w)
        m[yy[ok], xx[ok]] = True
    return ndi.binary_dilation(m, iterations=max(1, width // 2)) if width > 1 else m


def split_roi(roi: Roi, points, um: float) -> Optional[Tuple[Roi, Roi]]:
    """
    Cut one ROI in two along a freehand line drawn through it (the ends of the
    line are continued straight, so it only has to cross the ROI roughly).
    Returns the two parts (bigger first) or None if the line does not divide it
    into two real pieces (each at least 5 % of it).
    """
    shown = _shape(roi)
    y0, x0, y1, x1 = roi.bbox
    cut = _stroke_mask(points, (y0, x0, y1, x1), 2)
    rest = shown & ~cut
    lab, n = ndi.label(rest)
    if n < 2:
        return None
    sizes = np.bincount(lab.ravel())
    sizes[0] = 0
    order = np.argsort(-sizes)
    a, b = int(order[0]), int(order[1])
    if sizes[b] < max(9, 0.05 * shown.sum()):
        return None
    # every pixel (the cut line, small slivers) goes to the nearer of the two
    d_a = ndi.distance_transform_edt(lab != a)
    d_b = ndi.distance_transform_edt(lab != b)
    part_a = shown & (d_a <= d_b)
    part_b = shown & ~part_a
    out = []
    for part in (part_a, part_b):
        if getattr(roi, "outline", None) is not None:
            r = _to_roi(roi.mask & part if (roi.mask & part).any() else part, y0, x0, outline=part)
        else:
            r = _to_roi(part, y0, x0)
        if r is None:
            return None
        r.kind, r.channel, r.source = roi.kind, getattr(roi, "channel", 0), "manual"
        out.append(r)
    return out[0], out[1]


def extend_roi(plane: np.ndarray, roi: Roi, comp: str, y: float, x: float, um: float,
               others: Sequence[Roi] = (), nucleus: Optional[Roi] = None,
               mito_k: float = 3.0, reach_um: float = 6.0) -> Optional[Roi]:
    """
    Add the part of the cell at (x, y) to an existing ROI that is too small /
    missed something: around the click (within reach_um) the image is outlined
    at the ROI's own edge level - or a little below the clicked pixel's
    brightness if that is dimmer - and the piece holding the click is joined to
    the ROI. Other cells' pixels are never taken.
    """
    reg = _region(roi)
    H, W = plane.shape
    reach = int(_px(reach_um, um))
    yi, xi = int(round(y)), int(round(x))
    if not (0 <= yi < H and 0 <= xi < W):
        return None
    y0, x0, y1, x1 = reg.bbox
    big = (min(y0, yi - reach), min(x0, xi - reach), max(y1, yi + reach + 1), max(x1, xi + reach + 1))
    pseudo = Roi(big, np.ones((big[2] - big[0], big[3] - big[1]), bool), comp)
    box, sm, P, taken, bg, inner = _local(plane, reg, comp, um, 2, others)
    box = _box(pseudo.bbox, int(_px(4.0, um)), H, W)
    by0, bx0, by1, bx1 = box
    sm = ndi.gaussian_filter(plane[by0:by1, bx0:bx1].astype(np.float32),
                             max(0.8, _px(SIGMA_UM.get(comp, 1.0), um)))
    P = _paint_box([reg], box)
    taken = _paint_box([_region(o) for o in others if o is not None], box) & ~P
    cy, cx = yi - by0, xi - bx0
    if P[cy, cx]:
        return None                                      # already inside
    if inner - bg <= 1e-6:
        inner = bg + 1.0
    level = _edge_level(plane, reg, comp, um)
    here = (float(sm[cy, cx]) - bg) / (inner - bg)
    level = min(level, 0.85 * here) if here > 0 else level
    yy, xx = np.ogrid[:sm.shape[0], :sm.shape[1]]
    near = (yy - cy) ** 2 + (xx - cx) ** 2 <= reach * reach
    cand = (sm > bg + level * (inner - bg)) & near & ~taken
    if not cand[cy, cx]:                                 # a dark spot: a small disc there
        r0 = int(max(2, _px(1.0, um)))
        cand = ((yy - cy) ** 2 + (xx - cx) ** 2 <= r0 * r0) & ~taken
    piece = _keep_component(cand, cy, cx)
    new = P | piece
    if not (piece & ndi.binary_dilation(P, iterations=2)).any():
        # not touching: join them with a band as wide as the piece is thick
        d_p = ndi.distance_transform_edt(~P)
        py, px = np.unravel_index(int(np.argmin(np.where(piece, d_p, np.inf))), P.shape)
        d_q = ndi.distance_transform_edt(~piece)
        qy, qx = np.unravel_index(int(np.argmin(np.where(P, d_q, np.inf))), P.shape)
        band = _stroke_mask([(px + bx0, py + by0), (qx + bx0, qy + by0)], box,
                            int(max(2, _px(1.5, um))))
        seg = np.zeros_like(band)
        lo_y, hi_y = sorted((py, qy))
        lo_x, hi_x = sorted((px, qx))
        seg[max(0, lo_y - 3):hi_y + 4, max(0, lo_x - 3):hi_x + 4] = True
        new |= band & seg & ~taken
    new = ndi.binary_fill_holes(new) & ~taken
    ys, xs = np.nonzero(new)
    a0, a1, b0, b1 = int(ys.min()), int(ys.max()) + 1, int(xs.min()), int(xs.max()) + 1
    region = Roi((by0 + a0, bx0 + b0, by0 + a1, bx0 + b1), new[a0:a1, b0:b1].copy(), comp)
    hole = None
    if comp == "cytoplasm" and nucleus is None and getattr(roi, "outline", None) is not None:
        hole = Roi(roi.bbox, roi.outline & ~roi.mask, "hole")
    return _finish(comp, region, plane, um, mito_k, nucleus, hole, int(getattr(roi, "channel", 0)))


def _sub_shift(prev: np.ndarray, cur: np.ndarray, bbox, max_shift: int) -> Tuple[float, float]:
    """Sub-pixel displacement (dy, dx) of the neighbourhood of bbox from prev to cur."""
    from skimage.registration import phase_cross_correlation
    H, W = cur.shape
    a0, b0, a1, b1 = _box(bbox, max_shift + SHIFT_PAD_PX, H, W)
    a = prev[a0:a1, b0:b1].astype(np.float32)
    b = cur[a0:a1, b0:b1].astype(np.float32)
    if a.size < 64 or a.shape != b.shape or not np.ptp(a) or not np.ptp(b):
        return 0.0, 0.0
    try:
        sh, _, _ = phase_cross_correlation(a - a.mean(), b - b.mean(),
                                           upsample_factor=PHASE_UPSAMPLE, normalization=None)
    except Exception:                                      # noqa: BLE001
        return 0.0, 0.0
    return (float(np.clip(-sh[0], -max_shift, max_shift)),
            float(np.clip(-sh[1], -max_shift, max_shift)))


def _moved(r: Roi, dy: int, dx: int, shape) -> Roi:
    n = r.shifted(dy, dx, shape)
    n.kind = r.kind
    n.channel = getattr(r, "channel", 0)
    if getattr(r, "outline", None) is not None:
        o = Roi(r.bbox, r.outline, r.kind).shifted(dy, dx, shape)
        if o.mask.shape == n.mask.shape:
            n.outline = o.mask
    return n


def _measure(stack: np.ndarray, r: Roi, sat: int):
    """(mean, area px, saturated px, sum) per channel over the ROI's mask in this
    frame: sum = every raw pixel added up (float64: exact for integer counts),
    mean = sum / area - the same numbers the Excel Sum / Area sheets show."""
    y0, x0, y1, x1 = r.bbox
    m = r.mask
    C = stack.shape[0]
    if not m.any():
        return np.full(C, np.nan), 0, np.zeros(C, int), np.full(C, np.nan)
    vals = stack[:, y0:y1, x0:x1][:, m]                    # raw pixels, full resolution
    n = int(m.sum())
    s = vals.astype(np.float64).sum(axis=1)
    return s / n, n, (vals >= sat).sum(axis=1), s


def _finish(comp: str, region: Roi, plane: np.ndarray, um: float, mito_k: float,
            nucleus: Optional[Roi], hole: Optional[Roi], channel: int) -> Roi:
    """The measured ROI from a followed region: cytoplasm = region minus nucleus,
    mito = mitochondria pixels inside the region (found in this frame)."""
    y0, x0, y1, x1 = region.bbox
    full = region.mask
    if comp == "cytoplasm":
        box = (y0, x0, y1, x1)
        cut = _paint_box([nucleus], box) if nucleus is not None else \
            _paint_box([hole], box) if hole is not None else np.zeros_like(full)
        if cut.any():
            cut = ndi.binary_dilation(cut, iterations=int(max(1, round(_px(0.5, um)))))
        m = full & ~cut
        if m.sum() < 0.1 * full.sum():
            m = full
        r = Roi(region.bbox, m, comp)
        r.outline = full
    elif comp == "mito":
        sub = plane[y0:y1, x0:x1]
        m = mito_pieces(sub, full, um, mito_k) if sub.shape == full.shape else full
        if not m.any():                          # none clear in this frame: keep the region
            m = full                             # (the frame is flagged by QC as a jump)
        r = Roi(region.bbox, m, comp)
        r.outline = full
    else:
        r = Roi(region.bbox, full, comp)
    r.channel, r.source = channel, "manual"
    return r


def _resolve_overlaps(comp: str, regs: List[Optional[Roi]], q: List[float],
                      sides: Sequence[Optional[np.ndarray]],
                      before: Sequence[Optional[Roi]],
                      planes: Optional[Sequence[Optional[np.ndarray]]] = None,
                      fewest: Optional[Sequence[Optional[int]]] = None,
                      um: float = 1.0, pad: int = 3) -> List[Optional[Roi]]:
    """
    V2.5: in one frame, two cells' regions of a compartment never share a pixel
    and no region crosses its cell's boundary lines. Regions redrawn in this
    frame (q = 1) are disjoint already (pixels nearer a neighbour are its own);
    a region that fell back to its moved outline gives up the pixels another
    cell holds (ties: the lower cell number keeps them) and keeps its biggest
    piece; if nothing is left, its region of the frame before (trimmed the same
    way) is used. A trimmed region with fewer pixels than its hard limit
    (fewest[k]) is grown back by the brightest neighbouring pixels of its
    image (planes[k], smoothed as for redrawing), never into another cell or
    across its lines (_grow_bright). Untouched regions are returned as they are.
    """
    out = list(regs)
    order = sorted([k for k, r in enumerate(regs) if r is not None],
                   key=lambda k: (q[k] < 1.0, k))
    kept: List[int] = []

    def trimmed(r: Roi, k: int) -> Tuple[np.ndarray, bool]:
        y0, x0, y1, x1 = r.bbox
        m = r.mask.copy()
        if sides[k] is not None:
            m &= sides[k][y0:y1, x0:x1]
        for j in kept:
            o = out[j]
            if o is None or not o.area:
                continue
            oy0, ox0, oy1, ox1 = o.bbox
            a0, b0, a1, b1 = max(y0, oy0), max(x0, ox0), min(y1, oy1), min(x1, ox1)
            if a1 <= a0 or b1 <= b0:
                continue
            m[a0 - y0:a1 - y0, b0 - x0:b1 - x0] &= ~o.mask[a0 - oy0:a1 - oy0, b0 - ox0:b1 - ox0]
        return m, bool((m != r.mask).any())

    for k in order:
        r = regs[k]
        m, changed = trimmed(r, k)
        if changed:
            if not m.any() and before[k] is not None:
                r = before[k]
                m, _c = trimmed(r, k)
            if m.any():
                m = _keep_component(m, *np.unravel_index(
                    int(np.argmax(ndi.distance_transform_edt(m))), m.shape))
                nr = _to_roi(m, r.bbox[0], r.bbox[1])
                nr.kind = comp
                lo = fewest[k] if fewest is not None else None
                if lo and planes is not None and planes[k] is not None and nr.area < lo:
                    nr = _regrow(nr, comp, planes[k], lo, sides[k],
                                 [out[j] for j in kept if out[j] is not None], um, pad)
                out[k] = nr
            else:
                out[k] = Roi((r.bbox[0], r.bbox[1], r.bbox[0] + 1, r.bbox[1] + 1),
                             np.zeros((1, 1), bool), comp)
        kept.append(k)
    return out


def _regrow(r: Roi, comp: str, plane: np.ndarray, n: int, side: Optional[np.ndarray],
            others: Sequence[Roi], um: float, pad: int) -> Roi:
    """A trimmed region grown back to n pixels by the brightest neighbouring
    pixels (never into `others`, never across the cell's lines)."""
    H, W = plane.shape
    grow = int(np.ceil(np.sqrt(max(n - r.area, 0) / np.pi))) + pad + 2
    box = _box(r.bbox, grow, H, W)
    by0, bx0, by1, bx1 = box
    M = _paint_box([r], box)
    allowed = ~_paint_box(list(others), box)
    if side is not None:
        allowed &= side[by0:by1, bx0:bx1]
    sm = ndi.gaussian_filter(plane[by0:by1, bx0:bx1].astype(np.float32),
                             max(SIGMA_MIN_PX, _px(SIGMA_UM.get(comp, 1.0), um)))
    g = _grow_bright(M, sm, allowed | M, int(n))
    out = _to_roi(g, by0, bx0)
    if out is None:
        return r
    out.kind = comp
    return out


def track_cells(src, exp, cells: Sequence[Dict[str, Roi]], background: Roi, t0: int,
                max_move_um: float = 3.0, mito_k: float = 3.0, sat_level: int = 65535,
                lead: Sequence[str] = COMPS, progress: ProgressFn = None,
                size_tol: float = 0.25, rules: Optional[Dict[str, "TrackRule"]] = None,
                gate_snr: float = 5.0, overlap_k: float = 3.0,
                boundaries: Optional[Dict[int, list]] = None) -> dict:
    """
    Follow every cell from timepoint t0 forwards and backwards, REDRAWING every
    ROI at every timepoint, and measure every compartment on every channel.

    rules: {comp: rules.TrackRule}. V2.5: every rule follows the cell exactly as
    ONLY does, on channel A's raw pixels; the second channel only trims the
    measured pixels inside that outline:
      AND   pixels also bright in B (rules.overlap_mask, k = overlap_k);
      WITH  pixels where the combined A+B image (rules.guide_plane) is above the
            outline's own edge level on it (rules.with_mask);
      IF    nothing is trimmed; the signal-to-noise of B in each cell at t0 is
            returned (out["gate"]) and the caller excludes cells below gate_snr.
    A frame where no pixel is left measures NaN (quality 0.3).
    None = V2.2: each ROI is followed on the channel it was drawn on.
    V3.0 'help' rules (main channel A + helper channels): the ROI is followed and
    redrawn on rules.guide_plane (A + HELP_WEIGHT x each helper, each scaled to its
    own levels at t0), and each frame's outline is kept within HELP_GUARD_UM of the
    outline A alone gives (rules.help_guard); nothing is trimmed afterwards.
    boundaries: {cell index: [polyline, ...]} - lines (image (x, y) points)
    that cell's ROIs never cross (boundary_side).
    size_tol: the followed region keeps between (1 - size_tol) and
    (1 + size_tol) x the pixels drawn (hard); 0 = exactly the drawn count.
    The background region is measured at every timepoint by BackgroundMeter
    (cells included; very bright and fast-moving objects and the measured ROIs
    left out, from that timepoint's pixels).

    Returns dict(meas={comp: Measurements}, rois={comp: [t][cell] Roi},
                 redrawn={comp: fraction of ROI-frames redrawn (rest: moved only)},
                 rules=[rule dicts] (with rules only), params={every tracking
                 constant, for the methods}, gate={comp: {cell: SNR}} (IF only),
                 background={the region, its ROI overlap and the fluctuation
                 check}, bg_excluded={} (nothing is left out of the background))).
    """
    from concurrent.futures import ThreadPoolExecutor
    T, C, N = exp.n_timepoints, exp.n_channels, len(cells)
    H, W = exp.height, exp.width
    comps = [c for c in COMPS if any(c in cell for cell in cells)]
    um = exp.um_per_px
    margin = int(max(MARGIN_MIN_PX, round(_px(max_move_um, um))))
    mean = {c: np.full((T, C, N), np.nan) for c in comps}
    total = {c: np.full((T, C, N), np.nan) for c in comps}
    area = {c: np.zeros((T, N), int) for c in comps}
    nsat = {c: np.zeros((T, C, N), int) for c in comps}
    qual = {c: np.zeros((T, N)) for c in comps}
    rois = {c: [[None] * N for _ in range(T)] for c in comps}
    meter = BackgroundMeter(background, T, C, um)
    # the background is measured in its own thread, in the order the frames come
    # (one worker: the meter sees every frame exactly as the tracker does)
    bg_pool = ThreadPoolExecutor(max_workers=1)
    bg_jobs: list = []
    # each cell's movement is measured around its ROI of the first 'Follow' row
    anchor = [next((c for c in list(lead) + list(COMPS) if c in cell), None) for cell in cells]
    order_c = [c for c in COMPS if c in comps]            # nucleus first: others need it
    pool = ThreadPoolExecutor(max_workers=3)              # frames are read ahead
    first = np.asarray(src.frame(int(t0)))
    # tracking rules (None = V2.2): every rule follows on channel A (the ONLY outline)
    RL, rule_of, norm = None, {}, None
    if rules is not None:
        from . import rules as RL
        rule_of = RL.complete_rules(rules, cells, comps, list(exp.channels))
        if any(r.effective_mode() != "only" for r in rule_of.values()):
            norm = RL.make_norm(first)                    # frozen at the drawn frame
    and_comps = [c for c in comps if RL and RL._ab(rule_of[c], C)[1] == "and"]
    if_comps = [c for c in comps if RL and RL._ab(rule_of[c], C)[1] == "if"]
    with_comps = [c for c in comps if RL and RL._ab(rule_of[c], C)[1] == "with"]
    help_comps = [c for c in comps if RL and RL._ab(rule_of[c], C)[1] == "help"]
    gate: Dict[str, Dict[int, float]] = {c: {} for c in if_comps}
    gcache: list = []                                     # [(frame, key, helper image)]
    hsnr: Dict[str, Dict[int, dict]] = {c: {} for c in help_comps}

    def plane(stack: np.ndarray, _cache: dict, c: str, r: Roi) -> Tuple[np.ndarray, int]:
        """(image compartment c is followed on in this frame, channel recorded on
        the ROI): channel A's raw plane for every older rule (V2.5 lock); V3.0
        helpers: the main channel + HELP_WEIGHT x each helper (rules.guide_plane)."""
        if RL is None:
            ch = min(int(getattr(r, "channel", 0)), C - 1)
            return stack[ch], ch
        a = RL._ab(rule_of[c], C)[0]
        if c not in help_comps:
            return stack[a], a
        key = RL.guide_key(rule_of[c], C)
        for st, k, g in gcache:
            if st is stack and k == key:
                return g, a
        g = RL.guide_plane(stack, rule_of[c], norm)
        gcache.append((stack, key, g))
        del gcache[:-4]                                   # a few frames are enough
        return g, a

    # boundary lines: the part of the image each cell may use (fixed in the image)
    sides: List[Optional[np.ndarray]] = [None] * N
    lines_used: Dict[int, list] = {}
    for k, lines in (boundaries or {}).items():
        try:
            k = int(k)
        except (TypeError, ValueError):
            continue
        if 0 <= k < N and lines and anchor[k] is not None:
            sides[k] = boundary_side(lines, (H, W), _region(cells[k][anchor[k]]))
            if sides[k] is not None:
                lines_used[k] = [[[float(p[0]), float(p[1])] for p in ln] for ln in lines]

    # the edge level of every ROI, from the frame you clicked on (channel A)
    level = [{c: _edge_level(plane(first, {}, c, r)[0], _region(r), c, um)
              for c, r in cell.items()} for cell in cells]
    # V3.0 helpers: the main channel's own edge level too (the 1 um guard)
    level_main = [{c: _edge_level(first[RL._ab(rule_of[c], C)[0]], _region(r), c, um)
                   for c, r in cell.items() if c in help_comps} for cell in cells]
    # WITH: the outline's own edge level on the combined image, frozen at t0
    lev_with: List[Dict[str, float]] = [dict() for _ in cells]
    for c in with_comps:
        g_with = RL.guide_plane(first, rule_of[c], norm)
        for k, cell in enumerate(cells):
            if c in cell:
                lev_with[k][c] = _edge_level(g_with, _region(cell[c]), c, um)
        del g_with
    holes = []
    for cell in cells:                                    # cytoplasm without a nucleus ROI
        r = cell.get("cytoplasm")
        if r is not None and "nucleus" not in cell and getattr(r, "outline", None) is not None:
            holes.append(Roi(r.bbox, r.outline & ~r.mask, "hole"))
        else:
            holes.append(None)
    ref_area = [{c: float(_region(r).area) for c, r in cell.items()} for cell in cells]
    t_start = time.time()
    done = [0]

    def record(t: int, stack: np.ndarray, cur, q) -> None:
        for k, cell in enumerate(cur):
            for c, r in cell.items():
                mu, a, ns, s = _measure(stack, r, sat_level)
                mean[c][t, :, k], area[c][t, k], nsat[c][t, :, k] = mu, a, ns
                total[c][t, :, k] = s
                qual[c][t, k] = q[k].get(c, 1.0)
                r.contours()                              # ready for smooth display
                rois[c][t][k] = r
        # the background of this timepoint (measured once its neighbours are in)
        bg_jobs.append(bg_pool.submit(meter.add, t, stack,
                                      meter.roi_mask([r for cell in cur for r in cell.values()])))
        done[0] += 1
        if progress:
            el = time.time() - t_start
            left = el / done[0] * (T - done[0])
            if not progress(done[0] / T, f"Following and redrawing {N} cells: timepoint "
                                         f"{t + 1} of {T}  ({done[0]} done, about "
                                         f"{int(left) + 1} s left)"):
                raise Cancelled()

    def measured(stack: np.ndarray, cur, q):
        """AND / WITH rules: the measured ROIs keep only the pixels the second
        channel allows, inside the followed outline (the followed ROIs in `cur`
        stay whole, for the next frame and the neighbours)."""
        if not and_comps and not with_comps:
            return cur
        out = []
        for k, cell in enumerate(cur):
            d = dict(cell)
            for c in and_comps + with_comps:
                if c not in d:
                    continue
                if c in and_comps:
                    d[c] = RL.apply_and(d[c], stack, rule_of[c], norm, um, overlap_k)
                else:
                    d[c] = RL.apply_with(d[c], stack, rule_of[c], norm, um,
                                         lev_with[k].get(c, 0.5), c)
                if not d[c].mask.any():
                    q[k][c] = 0.3                         # nothing left: NaN
            out.append(d)
        return out

    def outline_all(stack: np.ndarray, cur, q, pred, first_frame: bool, hole):
        """Redraw every ROI of every cell in this frame (nucleus first)."""
        new = [dict() for _ in cells]
        for c in order_c:
            regions = [(_region(p[c]) if c in p else None) for p in pred]
            before = [(_region(cell[c]) if c in cell else None) for cell in cur]
            nuclei_now = [n.get("nucleus") for n in new]
            regs: List[Optional[Roi]] = [None] * N
            chans, planes = [0] * N, [None] * N
            for k, p in enumerate(pred):
                if c not in p:
                    continue
                g, ch = plane(stack, {}, c, p[c])
                walls = [] if c == "nucleus" else \
                    [nuclei_now[j] for j in range(N) if j != k and nuclei_now[j] is not None]
                tol = min(FIRST_FRAME_TOL, size_tol) if first_frame else size_tol
                reg = _redraw(g, regions[k], c, lev[k][c],
                              um, margin, regions[:k] + regions[k + 1:], walls,
                              ref_area[k].get(c), tol, sides[k])
                # the clicked frame keeps your shape if its redraw fails (0.9)
                q[k][c] = 1.0 if reg is not None else (0.9 if first_frame else 0.3)
                if reg is None:
                    reg = regions[k]
                elif getattr(reg, "fit_level", None) is not None:
                    lev[k][c] = float(reg.fit_level)
                if c in help_comps:                       # V3.0: stay near the main outline
                    a_ch = RL._ab(rule_of[c], C)[0]
                    regm = _redraw(stack[a_ch], regions[k], c, levm[k][c],
                                   um, margin, regions[:k] + regions[k + 1:], walls,
                                   ref_area[k].get(c), tol, sides[k])
                    if regm is not None and getattr(regm, "fit_level", None) is not None:
                        levm[k][c] = float(regm.fit_level)
                    reg = RL.help_guard(reg, regm if regm is not None else regions[k], um)
                regs[k], chans[k], planes[k] = reg, ch, g
            tl = min(FIRST_FRAME_TOL, size_tol) if first_frame else size_tol
            fewest = [size_limits(ref_area[k][c], tl)[0] if c in ref_area[k] else None
                      for k in range(N)]
            regs = _resolve_overlaps(c, regs, [q[k].get(c, 1.0) for k in range(N)], sides,
                                     before, planes, fewest, um, margin)
            for k in range(N):
                if regs[k] is not None:
                    new[k][c] = _finish(c, regs[k], planes[k], um, mito_k,
                                        new[k].get("nucleus"), hole[k], chans[k])
        return new

    lev: List[Dict[str, float]] = []
    levm: List[Dict[str, float]] = []

    def run(order: Sequence[int], skip_first: bool) -> None:
        nonlocal lev, levm
        cur = [dict(cell) for cell in cells]
        lev = [dict(lv) for lv in level]                  # may adapt as the cell changes
        levm = [dict(lv) for lv in level_main]
        hole = list(holes)
        acc = [[0.0, 0.0] for _ in cells]
        futures = {t: pool.submit(lambda tt=t: np.asarray(src.frame(int(tt)))) for t in order[:4]}
        prev = None
        for i, t in enumerate(order):
            if i + 4 < len(order):
                futures[order[i + 4]] = pool.submit(lambda tt=order[i + 4]: np.asarray(src.frame(int(tt))))
            stack = futures.pop(t).result()
            q = [dict() for _ in cells]
            if prev is not None:
                # 1  movement -> predicted position of every ROI
                pred = []
                for k, cell in enumerate(cur):
                    key = anchor[k]
                    if key is None:
                        pred.append({})
                        continue
                    g_prev = plane(prev, {}, key, cell[key])[0]
                    g_now = plane(stack, {}, key, cell[key])[0]
                    dy, dx = _sub_shift(g_prev, g_now, cell[key].bbox, margin)
                    acc[k][0] += dy
                    acc[k][1] += dx
                    iy, ix = int(round(acc[k][0])), int(round(acc[k][1]))
                    acc[k][0] -= iy
                    acc[k][1] -= ix
                    pred.append({c: _moved(r, iy, ix, (H, W)) for c, r in cell.items()})
                    if hole[k] is not None and (iy or ix):
                        hole[k] = hole[k].shifted(iy, ix, (H, W))
                # 2-5  redraw, nucleus first
                cur = outline_all(stack, cur, q, pred, False, hole)
            else:
                # the clicked frame: your ROIs, outlined by the same method as every
                # other frame (so there is no step between the first two timepoints),
                # within 10 % of the size you drew (the guard refers to that size)
                cur = outline_all(stack, cur, q, cur, True, hole)
                if not skip_first:                        # IF rules: signal in B at t0
                    for c in if_comps:
                        for k, cell in enumerate(cur):
                            if c in cell:
                                gate[c][k] = RL.gate_snr(stack, cell[c], rule_of[c], um, norm)
                    for c in help_comps:                  # V3.0: helper signal at t0
                        for k, cell in enumerate(cur):
                            if c in cell:
                                hsnr[c][k] = {exp.channels[h]: v for h, v in RL.helper_snr(
                                    stack, cell[c], rule_of[c], um, norm).items()}
            if not (skip_first and i == 0):
                record(t, stack, measured(stack, cur, q), q)
            prev = stack

    try:
        run(list(range(t0, T)), False)               # the clicked timepoint, then forwards
        if t0 > 0:
            run(list(range(t0, -1, -1)), True)        # and backwards to the start
        for j in bg_jobs:
            j.result()                                # an error in the meter surfaces here
        meter.finish()
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
        bg_pool.shutdown(wait=True, cancel_futures=True)
    for c in comps:
        for t in range(T):
            for k in range(N):
                if rois[c][t][k] is None:
                    e = Roi((0, 0, 1, 1), np.zeros((1, 1), bool), c)
                    e.include = False
                    rois[c][t][k] = e
    meas, redrawn = {}, {}
    for c in comps:
        live = [k for k in range(N) if c in cells[k]]
        q = qual[c][:, live] if live else np.ones((T, 0))
        redrawn[c] = float(np.mean(q >= 0.9)) if q.size else 1.0
        meas[c] = Measurements(mean=mean[c], background=meter.mean.copy(), area_px=area[c],
                               n_saturated=nsat[c], quality=np.where(qual[c] > 0, qual[c], 1.0),
                               channels=list(exp.channels), background_sd=meter.sd.copy(),
                               roi_mode=FILE_NAMES[c], sum=total[c],
                               background_sum=meter.sum.copy(),
                               background_npx=meter.npx.copy())
    out = dict(meas=meas, rois=rois, redrawn=redrawn)
    out["params"] = track_params(comps, um, max_move_um, margin, size_tol, mito_k, gate_snr,
                                 overlap_k, t0, norm, list(exp.channels), rules is not None,
                                 lines_used)
    out["background"] = meter.summary()
    out["bg_excluded"] = dict(meter.excluded)
    if RL is not None:
        out["rules"] = [rule_of[c].to_dict(list(exp.channels)) for c in comps]
    if help_comps:                                        # V3.0: for the methods
        out["params"]["help_weight"] = float(RL.HELP_WEIGHT)
        out["params"]["help_guard_um"] = float(RL.HELP_GUARD_UM)
        out["helper_snr"] = hsnr
    if if_comps:
        out["gate"] = gate
    return out


def track_params(comps: Sequence[str], um: float, max_move_um: float, margin: int,
                 size_tol: float, mito_k: float, gate_snr: float, overlap_k: float,
                 t0: int, norm=None, channels: Sequence[str] = (),
                 with_rules: bool = True, boundaries: Optional[Dict[int, list]] = None) -> dict:
    """Every number the tracker used (JSON-ready), for the methods / provenance record."""
    from . import rules as RL
    lo, hi = (1.0 - float(size_tol), 1.0 + float(size_tol))
    p = {
        "tracker": TRACKER,
        "max_move_um": float(max_move_um),
        "margin_px": int(margin),
        "size_tol": float(size_tol),
        "first_frame_tol": float(min(FIRST_FRAME_TOL, size_tol)),
        "area_step": [float(v) for v in AREA_STEP],
        "sigma_um": {c: float(SIGMA_UM[c]) for c in comps},
        "ring_um": float(RING_UM),
        "edge_level_clip": [float(v) for v in EDGE_LEVEL_CLIP],
        "phase_upsample": int(PHASE_UPSAMPLE),
        "mito_k": float(mito_k),
        "gate_snr": float(gate_snr),
        "overlap_k": float(overlap_k),
        "t0": int(t0),
        # extra keys, explained in _note
        "um_per_px": float(um),
        "sigma_min_px": float(SIGMA_MIN_PX),
        "ring_bg_pct": float(RING_BG_PCT),
        "refit_accept": [float(v) for v in REFIT_ACCEPT],
        "min_overlap_prev": float(MIN_OVERLAP_PREV),
        "shift_pad_px": int(SHIFT_PAD_PX),
        "and_sigma_um": float(RL.AND_SIGMA_UM),
        "norm_stride": int(RL.NORM_STRIDE),
        "norm_pct": [float(RL.NORM_BG_PCT), float(RL.NORM_TOP_PCT)],
        # V2.5
        "size_limits": [lo, hi],
        "rule_lock": "ONLY outline on channel A",
        "wall_px": int(1 + 2 * WALL_HALF_PX),
        "background": background_params(um),
        "_note": (
            "um_per_px: pixel size used. sigma_min_px: Gaussian smoothing is never below "
            "this (px). ring_bg_pct: the local background is this percentile of the "
            "ring_um ring. refit_accept: a size-guard re-fit is accepted only within "
            "this slack of the allowed area range. min_overlap_prev: at least this "
            "fraction of a redrawn outline must lie inside the moved previous outline. "
            "shift_pad_px: the phase-correlation window is the anchor ROI box plus "
            "margin_px plus this. and_sigma_um: AND rule, Gaussian smoothing of channel B. "
            "norm_stride / norm_pct: the WITH / AND / IF normalisation (norm) uses every "
            "norm_stride-th pixel of the drawn frame, background and bright levels at "
            "these percentiles, noise = 1.4826 x MAD of the darker half. "
            "size_limits: HARD limits on the followed region, x the drawn pixel count "
            "(trimmed to the brightest connected pixels / grown by the brightest "
            "neighbouring pixels; equal limits = exactly the drawn count). rule_lock: every "
            "rule follows the cell as ONLY does on channel A; WITH / AND only trim the "
            "measured pixels inside that outline, IF only excludes cells. wall_px: boundary "
            "lines are drawn this many pixels thick. background: how the background region "
            "is measured at every timepoint (see the Background parameters)."
            + ("" if with_rules else " No tracking rules were given: each ROI was "
               "followed on the channel it was drawn on (V2.2 behaviour).")),
    }
    if boundaries:
        p["boundaries"] = {str(int(k) + 1): v for k, v in sorted(boundaries.items())}
    if norm is not None:
        p["norm"] = norm.to_dict(channels)
    return p


def _overlap_px(a: Roi, b: Roi) -> int:
    """How many pixels two ROIs (their outlines) share."""
    ay0, ax0, ay1, ax1 = a.bbox
    by0, bx0, by1, bx1 = b.bbox
    y0, x0, y1, x1 = max(ay0, by0), max(ax0, bx0), min(ay1, by1), min(ax1, bx1)
    if y1 <= y0 or x1 <= x0:
        return 0
    A = _shape(a)[y0 - ay0:y1 - ay0, x0 - ax0:x1 - ax0]
    B = _shape(b)[y0 - by0:y1 - by0, x0 - bx0:x1 - bx0]
    return int((A & B).sum())
