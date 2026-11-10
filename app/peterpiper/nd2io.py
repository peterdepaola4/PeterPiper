"""
Reading ND2 files and exporting raw per-channel / per-timepoint TIFFs.

The rest of the program only ever talks to an ImageSource, so swapping in a
different file format later means writing one new class with the same three
methods (n_timepoints, n_channels, frame).

BLOCK: to support another format, subclass ImageSource and return it from open_source().
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional

import numpy as np

from .config import Experiment
from .safety import long_path, make_dirs, new_output_file, validate_filename_part

ProgressFn = Optional[Callable[[float, str], bool]]   # (fraction, message) -> keep_going


class ImageSource:
    """A 2D multi-channel time series."""

    channels: List[str]
    n_timepoints: int
    height: int
    width: int

    def frame(self, t: int) -> np.ndarray:
        """Return the (C, Y, X) stack for 0-based timepoint t."""
        raise NotImplementedError

    def plane(self, t: int, c: int) -> np.ndarray:
        return self.frame(t)[c]

    def close(self) -> None:
        pass


class ND2Source(ImageSource):
    """ND2 time series. Z stacks are max-projected; multi-point files use one point."""

    def __init__(self, path: str, position: int = 0):
        import nd2

        self.path = str(path)
        self._f = nd2.ND2File(long_path(self.path))
        sizes = dict(self._f.sizes)

        if "Y" not in sizes or "X" not in sizes:
            self._f.close()
            raise ValueError("This ND2 file has no XY image data.")

        self.height = int(sizes["Y"])
        self.width = int(sizes["X"])
        self.n_timepoints = int(sizes.get("T", 1))
        self._n_z = int(sizes.get("Z", 1))
        self._n_p = int(sizes.get("P", 1))
        self.position = min(position, self._n_p - 1)
        self._axes = [a for a in self._f.sizes if a not in ("Y", "X")]

        n_c = int(sizes.get("C", 1))
        names = []
        try:
            for ch in self._f.metadata.channels:
                nm = (ch.channel.name or "").strip()
                names.append(nm if nm else f"Ch{ch.channel.index + 1}")
        except Exception:
            names = []
        if len(names) != n_c:
            names = [f"Ch{i + 1}" for i in range(n_c)]
        # make names unique and safe for Excel sheet names
        seen: dict[str, int] = {}
        uniq = []
        for nm in names:
            nm = "".join(ch if ch.isalnum() or ch in "-_ " else "_" for ch in nm).strip() or "Ch"
            if nm in seen:
                seen[nm] += 1
                nm = f"{nm}_{seen[nm]}"
            else:
                seen[nm] = 1
            uniq.append(nm)
        self.channels = uniq

        # lazy dask view handles any axis order / Z / P without loading the file
        self._dask = self._f.to_dask()

    # ----------------------------------------------------------------- info
    @property
    def n_channels(self) -> int:
        return len(self.channels)

    @property
    def um_per_px(self) -> float:
        try:
            vs = self._f.voxel_size()
            v = float(vs.x)
            return v if v > 0 else 1.0
        except Exception:
            return 1.0

    @property
    def bit_depth(self) -> int:
        try:
            return int(self._f.attributes.bitsPerComponentSignificant or 16)
        except Exception:
            return 16

    @property
    def objective(self) -> str:
        try:
            return str(self._f.metadata.channels[0].microscope.objectiveName or "")
        except Exception:
            return ""

    @property
    def n_positions(self) -> int:
        return self._n_p

    def frame_times(self):
        """V3.0: every timepoint's time stamp in seconds (first frame = 0; the first
        channel's stamp, this position), or None if the file has none. ~0.2 ms per
        timepoint."""
        if getattr(self, "_times", None) is not None:
            return self._times
        try:
            out = []
            for t in range(self.n_timepoints):
                fm = self._f.frame_metadata((t * self._n_p + self.position) * self._n_z)
                out.append(float(fm.channels[0].time.relativeTimeMs) / 1000.0)
            a = np.asarray(out, dtype=float)
            if a.size and np.all(np.isfinite(a)):
                self._times = a - a[0]
                return self._times
        except Exception:
            pass
        return None

    def seconds_per_frame(self) -> float:
        """Median interval between timepoints, from the frame timestamps."""
        if self.n_timepoints < 2:
            return 0.0
        try:
            stamps = []
            step = max(1, self.n_timepoints // 12)
            idx = list(range(0, self.n_timepoints, step))
            for t in idx:
                fm = self._f.frame_metadata(t * self._n_z * self._n_p)
                stamps.append(float(fm.channels[0].time.relativeTimeMs))
            if len(stamps) >= 2:
                d = np.diff(stamps) / (1000.0 * step)
                v = float(np.median(d))
                if np.isfinite(v) and v > 0:
                    return round(v, 3)
        except Exception:
            pass
        try:  # fall back to the declared time-loop period
            for loop in self._f.experiment:
                if getattr(loop, "type", "") == "NETimeLoop":
                    per = loop.parameters.periods[0]
                    return round(float(per.periodMs) / 1000.0, 3)
        except Exception:
            pass
        return 0.0

    # ----------------------------------------------------------------- data
    def frame(self, t: int) -> np.ndarray:
        """(C, Y, X) uint16 for timepoint t, Z max-projected if needed."""
        t = int(np.clip(t, 0, self.n_timepoints - 1))
        sl: list = []
        for ax in self._axes:
            if ax == "T":
                sl.append(t)
            elif ax == "P":
                sl.append(self.position)
            elif ax == "Z":
                sl.append(slice(None))
            elif ax == "C":
                sl.append(slice(None))
            else:
                sl.append(0)
        arr = np.asarray(self._dask[tuple(sl)])

        # normalise to (C, Y, X)
        if "Z" in self._axes:
            zpos = [a for a in self._axes if a in ("Z", "C")].index("Z")
            arr = arr.max(axis=zpos)
        if "C" not in self._axes:
            arr = arr[np.newaxis]
        if arr.ndim == 2:
            arr = arr[np.newaxis]
        return np.ascontiguousarray(arr)

    def close(self) -> None:
        try:
            self._f.close()
        except Exception:
            pass


def open_source(path: str, position: int = 0) -> ImageSource:
    if str(path).lower().endswith(".nd2"):
        return ND2Source(path, position=position)
    raise ValueError(f"Unsupported file type: {Path(path).suffix}")


def describe(src: ND2Source, out_dir: str = "") -> Experiment:
    """Build an Experiment pre-filled from the file's own metadata (V3.0: with the
    uneven gaps between timepoints and the recorded span, from every time stamp)."""
    from .config import uneven_gaps
    times = src.frame_times() if hasattr(src, "frame_times") else None
    gaps = uneven_gaps(times) if times is not None else []
    span = float(times[-1] - times[0]) if times is not None and len(times) > 1 else 0.0
    return Experiment(
        frame_gaps=gaps, span_s=span,
        nd2_path=src.path,
        out_dir=out_dir,
        channels=list(src.channels),
        n_timepoints=src.n_timepoints,
        width=src.width,
        height=src.height,
        um_per_px=src.um_per_px,
        seconds_per_frame=src.seconds_per_frame(),
        bit_depth=src.bit_depth,
        objective=src.objective,
    )


# --------------------------------------------------------------------------
# TIFF export
# --------------------------------------------------------------------------
def display_ranges(stack: np.ndarray) -> List[tuple]:
    """Per channel (low, high) for SHOWING the image: the 0.5th / 99.7th percentile
    of one frame (every 4th pixel). Used for every timepoint so the brightness does
    not flicker."""
    out = []
    for plane in stack:
        sub = np.asarray(plane[::4, ::4], dtype=np.float64)
        lo, hi = (float(v) for v in np.percentile(sub, [0.5, 99.7]))
        out.append((lo, hi if hi > lo else lo + 1.0))
    return out


def _out_folder(exp: Experiment, sub: str) -> Path:
    base = Path(exp.out_dir).resolve()
    validate_filename_part(sub, "TIFF subfolder")
    folder = base / sub
    if folder.is_symlink() or folder.resolve().parent != base:
        raise ValueError("The TIFF subfolder must remain inside the results folder.")
    make_dirs(folder)
    stem = Path(exp.nd2_path).stem
    validate_filename_part(stem, "Image filename stem")
    for name in exp.channels:
        validate_filename_part(name, "Channel name")
    return folder


def export_tiffs(src: ImageSource, exp: Experiment, progress: ProgressFn = None) -> str:
    """
    Write one raw 16-bit TIFF per channel per timepoint into <out_dir>/<tiff_subdir>.

    Names are  <stem>_<Channel>_t###.tif  so they sort correctly and are easy to
    re-open in ImageJ/MATLAB. Pixel data is written unmodified. Each file is an
    ImageJ TIFF carrying a display range (the channel's 0.5-99.7 % brightness of
    the first frame) so Fiji / ImageJ open it visible - the camera only uses a
    small part of the 0-65535 range, so viewers that show the full range draw it
    almost black. The numbers in the file are the raw counts either way.
    """
    import tifffile

    folder = _out_folder(exp, exp.tiff_subdir)
    stem = Path(exp.nd2_path).stem
    total = exp.n_timepoints
    res = (1.0 / exp.um_per_px) if exp.um_per_px > 0 else None
    ranges = None

    for t in range(total):
        stack = src.frame(t)
        if ranges is None:
            ranges = display_ranges(stack)
        for c, name in enumerate(exp.channels):
            if c >= stack.shape[0]:
                break
            fn = folder / f"{stem}_{name}_t{t + 1:03d}.tif"
            lo, hi = ranges[c]
            meta = {"min": lo, "max": hi}
            kw = {}
            if res:
                meta["unit"] = "um"
                kw = dict(resolution=(res, res))
            with new_output_file(fn) as (_, stream):
                tifffile.imwrite(stream, np.ascontiguousarray(stack[c]), imagej=True,
                                 metadata=meta, **kw)
        if progress and not progress((t + 1) / total,
                                    f"Writing TIFFs - timepoint {t + 1} of {total}"):
            return str(folder)
    return str(folder)


def export_view_copies(src: ImageSource, exp: Experiment, subdir: str = "Viewing copies (PNG)",
                       progress: ProgressFn = None) -> str:
    """
    8-bit PNG copies of every channel and timepoint, contrast-stretched (same
    range for every timepoint of a channel) so they look right in Windows Photos,
    PowerPoint, email... FOR LOOKING ONLY: the numbers are not the raw counts -
    measure on the raw TIFFs or the .nd2.
    """
    from PIL import Image

    folder = _out_folder(exp, subdir)
    stem = Path(exp.nd2_path).stem
    total = exp.n_timepoints
    ranges = None
    for t in range(total):
        stack = src.frame(t)
        if ranges is None:
            ranges = display_ranges(stack)
        for c, name in enumerate(exp.channels):
            if c >= stack.shape[0]:
                break
            lo, hi = ranges[c]
            v = (stack[c].astype(np.float32) - lo) * (255.0 / (hi - lo))
            img = Image.fromarray(np.clip(v, 0, 255).astype(np.uint8))
            fn = folder / f"{stem}_{name}_t{t + 1:03d}_VIEW-ONLY.png"
            with new_output_file(fn) as (_, stream):
                img.save(stream, format="PNG")
        if progress and not progress((t + 1) / total,
                                    f"Writing viewing copies - timepoint {t + 1} of {total}"):
            return str(folder)
    return str(folder)
