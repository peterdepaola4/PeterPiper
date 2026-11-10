"""
Measurement container and the derived quantities written to Excel.

`Measurements` holds the raw per-ROI means exactly as read off the images; every
derived quantity (background subtraction, channel ratios, normalisation) is a
pure function of those numbers, so the same arithmetic is used for the on-screen
traces and for the workbook formulas.

BLOCK: add a new derived quantity as a method here and it can be plotted and
exported without touching the measuring code.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import permutations
from typing import List, Optional, Sequence, Tuple

import numpy as np

# V3.0 ratio check: dividing by (almost) nothing gives meaningless numbers. A
# cell's F/F0, ratio and R/R0 are left out when a channel they use is, at the
# baseline timepoint, below k x the noise of that ROI's mean (background pixel SD
# / sqrt(ROI pixels)); a ratio's single timepoints are left out where its
# denominator drops below k x that noise (a cell fading or leaving). 0 = off.
# Settings.ratio_min_snr sets k (set_min_snr).
MIN_BASELINE_SNR = 5.0


def set_min_snr(k) -> None:
    global MIN_BASELINE_SNR
    try:
        MIN_BASELINE_SNR = max(0.0, float(k))
    except (TypeError, ValueError):
        pass


def min_snr(k=None) -> float:
    return MIN_BASELINE_SNR if k is None else max(0.0, float(k))


@dataclass
class Measurements:
    """Raw ROI readings. Axes are (timepoint, channel, cell)."""

    mean: np.ndarray                      # (T, C, N) mean counts inside each ROI
    background: np.ndarray                # (T, C)    mean counts in the background ROI
    area_px: np.ndarray                   # (T, N)    ROI area in pixels
    n_saturated: np.ndarray               # (T, C, N) saturated pixels in the ROI
    quality: np.ndarray                   # (T, N)    tracking match quality 0-1
    channels: List[str] = field(default_factory=list)
    background_sd: Optional[np.ndarray] = None   # (T, C) pixel SD inside the background ROI
    roi_mode: str = "nucleus"
    # V2.5: the raw numbers behind every mean, so mean = sum / area can be checked
    # (None in results tracked before V2.5)
    sum: Optional[np.ndarray] = None              # (T, C, N) sum of the ROI's raw pixels
    background_sum: Optional[np.ndarray] = None   # (T, C) sum of the background pixels used
    background_npx: Optional[np.ndarray] = None   # (T,)   background pixels used (after the
                                                  #        per-timepoint exclusions)

    # ------------------------------------------------------------- shape
    @property
    def n_timepoints(self) -> int:
        return self.mean.shape[0]

    @property
    def n_channels(self) -> int:
        return self.mean.shape[1]

    @property
    def n_cells(self) -> int:
        return self.mean.shape[2]

    # --------------------------------------------------------- quantities
    def bg_subtracted(self) -> np.ndarray:
        """(T, C, N) ROI mean minus the background ROI mean of the same channel."""
        return self.mean - self.background[:, :, None]

    def ratio(self, num: int, den: int) -> np.ndarray:
        """(T, N) background-subtracted channel ratio num/den."""
        b = self.bg_subtracted()
        with np.errstate(divide="ignore", invalid="ignore"):
            r = b[:, num, :] / b[:, den, :]
        return np.where(np.isfinite(r), r, np.nan)

    @staticmethod
    def fold_change(trace: np.ndarray, baseline_t: int) -> np.ndarray:
        """
        F/F0 with F0 taken at one timepoint (0-based).

        Baseline reads 1.0 by construction. A zero or missing (NaN) baseline
        gives NaN for that cell rather than a division by zero; a negative
        baseline (possible after background subtraction) is NOT blanked - the
        values are divided by it as they are.
        """
        t = int(np.clip(baseline_t, 0, trace.shape[0] - 1))
        f0 = trace[t, :].astype(float).copy()
        f0[~np.isfinite(f0)] = np.nan
        f0[f0 == 0] = np.nan
        with np.errstate(divide="ignore", invalid="ignore"):
            out = trace / f0[None, :]
        return np.where(np.isfinite(out), out, np.nan)

    # ------------------------------------------- V3.0: too little signal (ratio check)
    def mean_noise(self, c: int) -> Optional[np.ndarray]:
        """(T, N) the noise of each ROI's mean in channel c: the background region's
        pixel SD / sqrt(the ROI's pixels) at that timepoint. None when the pixel SD
        was not recorded (results tracked before V2.2)."""
        if self.background_sd is None:
            return None
        sd = np.asarray(self.background_sd[:, c], float)[:, None]
        return sd / np.sqrt(np.maximum(np.asarray(self.area_px, float), 1.0))

    def low_at_baseline(self, chans: Sequence[int], baseline_t: int, k=None) -> np.ndarray:
        """(N,) True for cells where any of these channels is, at the baseline
        timepoint, below k x the noise of the ROI's mean above background."""
        k = min_snr(k)
        out = np.zeros(self.n_cells, bool)
        if k <= 0:
            return out
        t = int(np.clip(baseline_t, 0, self.n_timepoints - 1))
        bs = self.bg_subtracted()
        for c in chans:
            nz = self.mean_noise(int(c))
            if nz is None:
                continue
            v, lim = bs[t, int(c), :], k * nz[t]
            out |= np.isfinite(v) & np.isfinite(lim) & (v < lim)
        return out

    def low_points(self, c: int, k=None) -> np.ndarray:
        """(T, N) True where channel c is below k x the noise of the ROI's mean."""
        k = min_snr(k)
        nz = self.mean_noise(int(c))
        if k <= 0 or nz is None:
            return np.zeros((self.n_timepoints, self.n_cells), bool)
        v = self.bg_subtracted()[:, int(c), :]
        lim = k * nz
        return np.isfinite(v) & np.isfinite(lim) & (v < lim)

    def _blank(self, data: np.ndarray, low: np.ndarray) -> np.ndarray:
        out = np.array(data, float, copy=True)
        if low.any():
            out[:, low] = np.nan
        return out

    def ff0(self, c: int, baseline_t: int, k=None) -> np.ndarray:
        """F/F0 of channel c; blank for cells too dim at baseline (V3.0)."""
        return self._blank(self.fold_change(self.bg_subtracted()[:, c, :], baseline_t),
                           self.low_at_baseline([c], baseline_t, k))

    def ratio_checked(self, num: int, den: int, baseline_t: int, k=None) -> np.ndarray:
        """ratio(num, den); blank for cells with either channel too dim at baseline,
        and at the timepoints where the denominator is too dim (V3.0)."""
        r = self._blank(self.ratio(num, den), self.low_at_baseline([num, den], baseline_t, k))
        r[self.low_points(den, k)] = np.nan
        return r

    def rr0(self, num: int, den: int, baseline_t: int, k=None) -> np.ndarray:
        """R/R0 of num/den from ratio_checked (V3.0)."""
        return self.fold_change(self.ratio_checked(num, den, baseline_t, k), baseline_t)

    def channel_pairs(self) -> List[Tuple[int, int]]:
        """Every ordered pair of channels, so both A/B and B/A are produced."""
        return list(permutations(range(self.n_channels), 2))

    # ------------------------------------------------------------- subsets
    def with_channels(self, idx: Sequence[int]) -> "Measurements":
        """Only these channels (in this order) - e.g. the ones you chose to
        measure in a compartment. Every other number is unchanged."""
        idx = list(idx)
        return Measurements(
            mean=self.mean[:, idx, :], background=self.background[:, idx],
            area_px=self.area_px, n_saturated=self.n_saturated[:, idx, :],
            quality=self.quality, channels=[self.channels[i] for i in idx],
            background_sd=None if self.background_sd is None else self.background_sd[:, idx],
            roi_mode=self.roi_mode,
            sum=None if self.sum is None else self.sum[:, idx, :],
            background_sum=None if self.background_sum is None else self.background_sum[:, idx],
            background_npx=self.background_npx)

    def select(self, cells: Sequence[int]) -> "Measurements":
        idx = np.asarray(list(cells), int)
        return Measurements(
            mean=self.mean[:, :, idx],
            background=self.background.copy(),
            area_px=self.area_px[:, idx],
            n_saturated=self.n_saturated[:, :, idx],
            quality=self.quality[:, idx],
            channels=list(self.channels),
            background_sd=None if self.background_sd is None else self.background_sd.copy(),
            roi_mode=self.roi_mode,
            sum=None if self.sum is None else self.sum[:, :, idx],
            background_sum=None if self.background_sum is None else self.background_sum.copy(),
            background_npx=None if self.background_npx is None else self.background_npx.copy(),
        )

    @staticmethod
    def concat(a: "Measurements", b: "Measurements") -> "Measurements":
        """a's cells followed by b's (same timepoints and channels)."""
        bsd = a.background_sd if a.background_sd is not None else b.background_sd
        return Measurements(
            mean=np.concatenate([a.mean, b.mean], axis=2),
            background=a.background.copy(),
            area_px=np.concatenate([a.area_px, b.area_px], axis=1),
            n_saturated=np.concatenate([a.n_saturated, b.n_saturated], axis=2),
            quality=np.concatenate([a.quality, b.quality], axis=1),
            channels=list(a.channels),
            background_sd=None if bsd is None else bsd.copy(),
            roi_mode=a.roi_mode,
            sum=None if a.sum is None or b.sum is None else np.concatenate([a.sum, b.sum], axis=2),
            background_sum=None if a.background_sum is None else a.background_sum.copy(),
            background_npx=None if a.background_npx is None else a.background_npx.copy(),
        )

    @staticmethod
    def empty(n_t: int, n_c: int, n_cells: int, channels: Sequence[str],
              roi_mode: str = "nucleus") -> "Measurements":
        return Measurements(
            mean=np.full((n_t, n_c, n_cells), np.nan),
            background=np.full((n_t, n_c), np.nan),
            area_px=np.zeros((n_t, n_cells), int),
            n_saturated=np.zeros((n_t, n_c, n_cells), int),
            quality=np.zeros((n_t, n_cells)),
            channels=list(channels),
            background_sd=np.full((n_t, n_c), np.nan),
            roi_mode=roi_mode,
            sum=np.full((n_t, n_c, n_cells), np.nan),
            background_sum=np.full((n_t, n_c), np.nan),
            background_npx=np.zeros(n_t, np.int64),
        )
