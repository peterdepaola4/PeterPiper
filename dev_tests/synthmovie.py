"""
The small synthetic test movie shipped with the code (dev_tests/data/
synthetic_movie.npz), so anyone can run the tests without the lab's own .nd2 files.

    12 timepoints, 3 channels (Cy5 = nuclear marker, GFP = sensor, mCherry),
    192 x 256 px at 0.5 um/px, 30 s per frame; 16 nuclei (radius 9 px = 64 um2)
    drifting slowly, and an empty strip on the right (x 200 - 250) for the
    background region. Cells 1, 3, 5, ... (odd numbers) carry the GFP sensor: GFP
    rises from 600 to 1200 counts above background after timepoint 4; the even
    ones are untransfected (GFP = background only) - their F/F0 and ratios are
    what the ratio check leaves out. Background 200 counts, Gaussian noise SD 8.

make() builds it from a fixed seed (the file is exactly make(), checked by the
tests); load() returns (SyntheticMovie, Experiment) ready for the main window.
Regenerate the file:  python dev_tests/synthmovie.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FILE = HERE / "data" / "synthetic_movie.npz"
sys.path.insert(0, str(HERE.parent / "app"))

T, H, W = 12, 192, 256
CHANNELS = ["Cy5", "GFP", "mCherry"]
UM_PER_PX, SECONDS_PER_FRAME = 0.5, 30.0
N_CELLS = 16


def centres(t: int):
    """(y, x) of every nucleus at timepoint t (0-based): a 4 x 4 grid, drifting."""
    out = []
    for n in range(N_CELLS):
        cy, cx = 30 + 44 * (n // 4), 30 + 44 * (n % 4)
        out.append((cy + 0.5 * t, cx + 0.3 * t))
    return out


def make() -> np.ndarray:
    """(T, C, H, W) uint16, from a fixed seed."""
    rng = np.random.default_rng(29)
    yy, xx = np.mgrid[0:H, 0:W]
    out = np.zeros((T, len(CHANNELS), H, W), np.uint16)
    for t in range(T):
        st = np.full((len(CHANNELS), H, W), 200.0)
        for n, (cy, cx) in enumerate(centres(t)):
            inside = (yy - cy) ** 2 + (xx - cx) ** 2 < 9 ** 2
            st[0][inside] += 1500 + 60 * n                 # Cy5 nuclear marker
            if n % 2 == 0:                                  # cells 1, 3, 5, ... (1-based)
                st[1][inside] += 600 if t < 4 else 1200     # GFP sensor responds
            st[2][inside] += 400                            # mCherry
        st += rng.normal(0, 8, st.shape)
        out[t] = np.clip(np.round(st), 0, 65535).astype(np.uint16)
    return out


def save() -> Path:
    FILE.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(FILE, frames=make(), channels=np.array(CHANNELS),
                        um_per_px=UM_PER_PX, seconds_per_frame=SECONDS_PER_FRAME)
    return FILE


def load(out_dir) -> tuple:
    """(source, experiment) for the shipped movie; results go to out_dir."""
    from peterpiper.config import Experiment
    from peterpiper.nd2io import ImageSource

    z = np.load(FILE)
    frames = z["frames"]

    class SyntheticMovie(ImageSource):
        def __init__(self):
            self.channels = [str(c) for c in z["channels"]]
            self.n_timepoints, self.height, self.width = frames.shape[0], H, W

        def frame(self, t):
            return frames[int(t)]

    src = SyntheticMovie()
    exp = Experiment(nd2_path=str(Path(out_dir) / "synthetic_movie.nd2"), out_dir=str(out_dir),
                     channels=list(src.channels), n_timepoints=src.n_timepoints, width=W,
                     height=H, um_per_px=float(z["um_per_px"]),
                     seconds_per_frame=float(z["seconds_per_frame"]))
    exp.export_tiffs = False
    return src, exp


if __name__ == "__main__":
    print(save(), f"{FILE.stat().st_size / 1e6:.2f} MB")
