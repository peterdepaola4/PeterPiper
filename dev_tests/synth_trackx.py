"""
A small synthetic movie for the 4.0 re-track / troubleshooter tests
(test_v40_trackx.py): made from a fixed seed in memory, nothing on disk.

    3 channels: "Cy5" (nuclear marker), "GFP" (sensor, nucleus + dimmer
    cytoplasm), "DAPI" (nuclear, weak); 0.5 um / px; T timepoints.
    A 3 x 3 grid of cells whose WHOLE cells touch their neighbours (the
    tracker has to share pixels between them), drifting slowly and jittering a
    little each on its own; an empty strip on the right for the background.
    Cell index 4 (the middle one, "cell 5") is the PROBLEM cell: almost no Cy5
    (its nucleus is hard to follow on Cy5) but a bright GFP nucleus - the ROI
    troubleshooter should find "GFP" better than the current "Cy5" rule.

make() -> (frames (T, C, H, W) uint16, truth dict); Src / Exp are the minimal
image source and experiment the tracker needs; seeds() gives the cells as
drawn at t0 (their true outlines, 1 px inside).
"""
from __future__ import annotations

import numpy as np

CHANNELS = ["Cy5", "GFP", "DAPI"]
UM = 0.5
PROBLEM = 4


class Exp:
    def __init__(self, T, C, H, W, um=UM, names=CHANNELS):
        self.n_timepoints, self.n_channels, self.height, self.width = T, C, H, W
        self.um_per_px = um
        self.channels = list(names)[:C]
        self.nd2_path = "synthetic_trackx.nd2"
        self.seconds_per_frame = 10.0
        self.bit_depth = 16
        self.sat_level = 65535
        self.out_dir = "."
        self.objective = ""
        self.span_s = 0.0
        self.frame_gaps = []

    def time_axis(self, T, b):
        x = (np.arange(T) - b) * self.seconds_per_frame / 60.0
        return x, "Time (min)"


class Src:
    """In-memory image source with the 4.0 crop read; counts every pixel read."""

    def __init__(self, frames):
        self.frames = np.asarray(frames)
        self.n_timepoints = self.frames.shape[0]
        self.height, self.width = self.frames.shape[2:]
        self.channels = list(CHANNELS)[:self.frames.shape[1]]
        self.px_read = 0
        self.reads = 0

    def frame(self, t):
        self.px_read += self.frames[0].size
        self.reads += 1
        return self.frames[int(t)]

    def crop(self, t, y0, y1, x0, x1):
        a = self.frames[int(t), :, y0:y1, x0:x1]
        self.px_read += a.size
        self.reads += 1
        return np.array(a)


def centres(T, n_side=3, spacing=31, origin=(40, 40), seed=3):
    """(T, N, 2) cell centres: a grid drifting 0.6 px / frame down and 0.4 right,
    each cell jittering up to ~1 px on its own."""
    rng = np.random.default_rng(seed)
    N = n_side * n_side
    base = np.array([(origin[0] + spacing * (n // n_side), origin[1] + spacing * (n % n_side))
                     for n in range(N)], float)
    jit = np.cumsum(rng.normal(0, 0.35, (T, N, 2)), axis=0)
    drift = np.arange(T)[:, None, None] * np.array([0.6, 0.4])[None, None, :]
    return base[None] + drift + jit


def make(T=12, H=180, W=230, seed=5, n_side=3):
    rng = np.random.default_rng(seed)
    cen = centres(T, n_side)
    N = cen.shape[1]
    r_nuc = 7.0 + (np.arange(N) % 3) * 0.8
    r_cell = 17.0 + (np.arange(N) % 2) * 1.5
    yy, xx = np.mgrid[0:H, 0:W]
    out = np.zeros((T, 3, H, W), np.uint16)
    for t in range(T):
        st = np.zeros((3, H, W))
        st[0] += 200.0
        st[1] += 150.0
        st[2] += 120.0
        # whole cells first (GFP cytoplasm), nearest centre owns a pixel
        d = np.stack([np.hypot(yy - cen[t, n, 0], xx - cen[t, n, 1]) for n in range(N)])
        own = np.argmin(d, axis=0)
        dmin = np.min(d, axis=0)
        for n in range(N):
            cell = (own == n) & (dmin < r_cell[n])
            nuc = d[n] < r_nuc[n]
            st[1][cell] += 250 + 20 * n
            st[0][nuc] += 0 if n == PROBLEM else 1400 + 50 * n
            st[1][nuc] += 1700 if n == PROBLEM else 500 + 30 * n
            st[2][nuc] += 300
        st[0] += rng.normal(0, 12, (H, W))
        st[1] += rng.normal(0, 12, (H, W))
        st[2] += rng.normal(0, 25, (H, W))
        out[t] = np.clip(np.round(st), 0, 65535).astype(np.uint16)
    return out, dict(centres=cen, r_nuc=r_nuc, r_cell=r_cell)


def _disc(H, W, cy, cx, r):
    yy, xx = np.mgrid[0:H, 0:W]
    return (yy - cy) ** 2 + (xx - cx) ** 2 <= r * r


def seeds(frames, truth, t0, comps=("nucleus", "cytoplasm"), channel=None):
    """The cells as drawn at t0: nucleus = true disc 1 px in; whole cell / cytoplasm
    = the cell's own share of the touching discs 1 px in (cytoplasm: minus the
    nucleus widened 1 px, outline = the whole cell)."""
    from peterpiper.segment import Roi
    T, C, H, W = np.asarray(frames).shape
    cen = truth["centres"][t0]
    N = cen.shape[0]
    yy, xx = np.mgrid[0:H, 0:W]
    d = np.stack([np.hypot(yy - cen[n, 0], xx - cen[n, 1]) for n in range(N)])
    own = np.argmin(d, axis=0)
    dmin = np.min(d, axis=0)
    cells = []

    def roi(m, kind, outline=None):
        ys, xs = np.nonzero(m if outline is None else outline)
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        r = Roi((int(y0), int(x0), int(y1), int(x1)), m[y0:y1, x0:x1].copy(), kind, True, "manual")
        if outline is not None:
            r.outline = outline[y0:y1, x0:x1].copy()
        r.channel = 0 if channel is None else channel
        return r

    from scipy import ndimage as ndi
    for n in range(N):
        cell = {}
        nuc = d[n] < truth["r_nuc"][n] - 1
        whole = ndi.binary_erosion((own == n) & (dmin < truth["r_cell"][n]), iterations=1)
        if "nucleus" in comps:
            cell["nucleus"] = roi(nuc, "nucleus")
        if "cell" in comps:
            cell["cell"] = roi(whole, "cell")
            cell["cell"].channel = 1
        if "cytoplasm" in comps:
            cyto = whole & ~ndi.binary_dilation(nuc, iterations=1)
            cell["cytoplasm"] = roi(cyto, "cytoplasm", outline=whole)
            cell["cytoplasm"].channel = 1
        cells.append(cell)
    return cells


def background(H, W):
    from peterpiper.segment import Roi
    y0, y1, x0, x1 = 10, H - 10, W - 22, W - 4
    return Roi((y0, x0, y1, x1), np.ones((y1 - y0, x1 - x0), bool), "background")
