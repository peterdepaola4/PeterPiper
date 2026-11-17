"""
Merge two ROIs that are really one cell (PeterPiper 1.2, the Merge tool).

    merge_rois(a, b, um, shape, others, avoid)  two ROIs of one compartment -> one
    merge_cells(c1, c2, comp, um, shape, third) two cells -> one cell ({comp: Roi})

How two ROIs are joined: the union of the two, plus the smallest bridge that makes
them one connected piece - a closing (dilate, then erode) with a growing radius
(1, 2, 3 ... px), whose new pixels are kept only in the region between the two ROIs
(pixels p with dist(p, a) + dist(p, b) <= the gap + 2 x the radius), never on a
third cell's pixels. Holes the join closed in are filled (an ROI's own holes, e.g.
the nucleus inside a cytoplasm outline, stay holes). Two ROIs further apart than
MAX_GAP_UM are not 'next to each other' and are refused.

ROIs with an outline (cytoplasm: the whole cell, measured without its nucleus;
mitochondria: the region holding them) are joined by their outlines; the measured
pixels are both ROIs' measured pixels plus - for cytoplasm - the bridge outside
any nucleus (mitochondria: the bridge is not mitochondria, so only the pieces).

The data model holds one ROI per compartment per cell, so when the two cells both
have another compartment (e.g. both a nucleus and a cytoplasm) that is merged the
same way; if those are not next to each other the merge is refused (one cell
cannot hold two separate nuclei). A compartment only one of the two has is kept.

Pure numpy / scikit-image (and scipy.ndimage, which scikit-image is built on); no Qt.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy import ndimage as ndi
from skimage.measure import label
from skimage.morphology import isotropic_closing

from .segment import Roi

MAX_GAP_UM = 3.0            # further apart than this (empty pixels between): not next to each other
MIN_GAP_PX = 3              # at any pixel size, a gap of up to 3 px is bridged
ORDER = ("nucleus", "cell", "mito", "cytoplasm")   # cytoplasm last: it avoids the nucleus

# reasons merge_rois / merge_cells give for a refusal
FAR, BLOCKED, EMPTY = "far", "blocked", "empty"


def _shape(r: Roi) -> np.ndarray:
    """The ROI's filled shape (its outline if it has one, else its mask)."""
    return r.outline if getattr(r, "outline", None) is not None else r.mask


def _paint(masks_boxes, box) -> np.ndarray:
    """Paint (mask, bbox) pairs into the box (y0, x0, y1, x1)."""
    by0, bx0, by1, bx1 = box
    out = np.zeros((by1 - by0, bx1 - bx0), bool)
    for m, bb in masks_boxes:
        y0, x0, y1, x1 = bb
        a0, b0, a1, b1 = max(y0, by0), max(x0, bx0), min(y1, by1), min(x1, bx1)
        if a1 <= a0 or b1 <= b0:
            continue
        out[a0 - by0:a1 - by0, b0 - bx0:b1 - bx0] |= m[a0 - y0:a1 - y0, b0 - x0:b1 - x0]
    return out


def max_gap_px(um: float, max_gap_um: float = MAX_GAP_UM) -> int:
    return int(max(MIN_GAP_PX, math.ceil(max_gap_um / max(float(um), 1e-6))))


def gap_px(a: Roi, b: Roi) -> float:
    """Empty pixels between the two ROIs' shapes (0 when they touch or overlap)."""
    box = (min(a.bbox[0], b.bbox[0]), min(a.bbox[1], b.bbox[1]),
           max(a.bbox[2], b.bbox[2]), max(a.bbox[3], b.bbox[3]))
    A = _paint([(_shape(a), a.bbox)], box)
    B = _paint([(_shape(b), b.bbox)], box)
    if not A.any() or not B.any():
        return float("inf")
    d = ndi.distance_transform_edt(~A)
    return max(0.0, float(d[B].min()) - 1.0)


def _fill_holes(m: np.ndarray) -> np.ndarray:
    return ndi.binary_fill_holes(m)


def _joined(M: np.ndarray, A: np.ndarray, B: np.ndarray) -> bool:
    """One 4-connected piece of M holds pixels of both A and B."""
    lab = label(M, connectivity=1)
    la, lb = set(np.unique(lab[A & M])) - {0}, set(np.unique(lab[B & M])) - {0}
    return bool(la & lb)


def _bridge(A: np.ndarray, B: np.ndarray, taken: np.ndarray,
            max_gap: int) -> Tuple[Optional[np.ndarray], str]:
    """(merged shape, '') or (None, reason) for two shapes in one (padded) box."""
    U = A | B
    dA = ndi.distance_transform_edt(~A)
    dB = ndi.distance_transform_edt(~B)
    gap = max(0.0, float(dA[B].min()) - 1.0)          # empty pixels between them
    if gap > max_gap:
        return None, FAR
    r_max = int(math.ceil(max_gap / 2.0)) + 2
    for r in range(1, r_max + 1):
        closed = isotropic_closing(U, r)
        between = (dA + dB) <= gap + 1.0 + 2.0 * r
        M = U | (closed & between & ~taken)
        if _joined(M, A, B):
            break
    else:
        return None, BLOCKED
    # holes the join closed in are filled; each ROI's own holes stay holes
    own = (_fill_holes(A) & ~A) | (_fill_holes(B) & ~B)
    M |= _fill_holes(M) & ~M & ~own & ~taken
    return M, ""


def merge_rois(a: Roi, b: Roi, um: float, shape: Tuple[int, int],
               others: Sequence[Roi] = (), avoid: Sequence[Roi] = (),
               max_gap_um: float = MAX_GAP_UM) -> Tuple[Optional[Roi], str]:
    """
    One ROI from a and b (same compartment): (merged, '') or (None, reason) with
    reason FAR (not next to each other), BLOCKED (only a third cell's pixels lie
    between them) or EMPTY. `others`: every ROI of the other cells - none of
    their pixels is taken. `avoid`: pixels the measured part must leave out
    (a cytoplasm's nucleus). The merged ROI keeps a's kind and channel.
    """
    H, W = int(shape[0]), int(shape[1])
    mg = max_gap_px(um, max_gap_um)
    pad = int(math.ceil(mg / 2.0)) + 4
    y0 = max(0, min(a.bbox[0], b.bbox[0]) - pad)
    x0 = max(0, min(a.bbox[1], b.bbox[1]) - pad)
    y1 = min(H, max(a.bbox[2], b.bbox[2]) + pad)
    x1 = min(W, max(a.bbox[3], b.bbox[3]) + pad)
    box = (y0, x0, y1, x1)
    A = _paint([(_shape(a), a.bbox)], box)
    B = _paint([(_shape(b), b.bbox)], box)
    if not A.any() or not B.any():
        return None, EMPTY
    taken = _paint([(_shape(o), o.bbox) for o in others if o is not None and o.area], box)
    # computed in a box padded beyond the image, so the image edge is not a wall
    P = pad
    Ap, Bp = (np.pad(m, P) for m in (A, B))
    tp = np.pad(taken, P)
    Mp, why = _bridge(Ap, Bp, tp, mg)
    if Mp is None:
        return None, why
    M = Mp[P:-P, P:-P]
    added = M & ~(A | B)
    has_outline = getattr(a, "outline", None) is not None or getattr(b, "outline", None) is not None
    if has_outline:
        ma = _paint([(a.mask, a.bbox)], box)
        mb = _paint([(b.mask, b.bbox)], box)
        meas = ma | mb
        if a.kind != "mito":
            meas |= added & ~_paint([(_shape(n), n.bbox) for n in avoid if n is not None], box)
        if not meas.any():
            meas = M.copy()
    else:
        meas = M
    ys, xs = np.nonzero(M)
    a0, a1, b0, b1 = int(ys.min()), int(ys.max()) + 1, int(xs.min()), int(xs.max()) + 1
    out = Roi((y0 + a0, x0 + b0, y0 + a1, x0 + b1), meas[a0:a1, b0:b1].copy(), a.kind,
              True, "manual")
    if has_outline:
        out.outline = M[a0:a1, b0:b1].copy()
    out.channel = getattr(a, "channel", 0)
    return out, ""


def merge_cells(c1: Dict[str, Roi], c2: Dict[str, Roi], comp: str, um: float,
                shape: Tuple[int, int], third: Sequence[Dict[str, Roi]] = (),
                max_gap_um: float = MAX_GAP_UM
                ) -> Tuple[Optional[Dict[str, Roi]], Optional[Tuple[str, str]], dict]:
    """
    Two cells -> one: (new cell, None, info) or (None, (reason, compartment), {}).
    comp = the compartment clicked (both cells must have it). Every compartment
    both cells have is merged (refused if it cannot be); one only the second
    cell has comes along. info: merged / moved compartments, pixels added.
    The cells passed in are not changed.
    """
    if comp not in c1 or comp not in c2:
        return None, (EMPTY, comp), {}
    others = [r for cell in third for r in cell.values() if r is not None]
    new: Dict[str, Roi] = {}
    info = dict(merged=[], moved=[], added_px={})
    if gap_px(c1[comp], c2[comp]) > max_gap_px(um, max_gap_um):   # the clicked ones first
        return None, (FAR, comp), {}
    for c in [c for c in ORDER if c in c1 and c in c2]:
        avoid = []
        if c == "cytoplasm":
            nuc = new.get("nucleus") or c1.get("nucleus") or c2.get("nucleus")
            avoid = [n for n in (nuc,) if n is not None]
        r, why = merge_rois(c1[c], c2[c], um, shape, others, avoid, max_gap_um)
        if r is None:
            return None, (why, c), {}
        r.kind = c1[c].kind
        new[c] = r
        info["merged"].append(c)
        info["added_px"][c] = int(_shape(r).sum() - _shape(c1[c]).sum() - _shape(c2[c]).sum())
    for c in ORDER:
        if c in new:
            continue
        if c in c1:
            new[c] = c1[c]
        elif c in c2:
            new[c] = c2[c]
            info["moved"].append(c)
    # the cytoplasm's measured pixels leave out the (now bigger) nucleus
    cy, nu = new.get("cytoplasm"), new.get("nucleus")
    if cy is not None and nu is not None and "nucleus" in info["merged"]:
        keep = cy.mask & ~_paint([(_shape(nu), nu.bbox)], cy.bbox)
        if keep.any() and not np.array_equal(keep, cy.mask):
            r = Roi(cy.bbox, keep, cy.kind, cy.include, cy.source)
            r.outline = cy.outline.copy() if getattr(cy, "outline", None) is not None else None
            r.channel = getattr(cy, "channel", 0)
            new["cytoplasm"] = r
    return new, None, info
