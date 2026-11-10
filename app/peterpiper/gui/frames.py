"""
Frames for the image display, read in the background.

Reading one timepoint can take 0.02-0.3 s (compressed files are slow), so the
window never waits for the disk while you scrub or play: frames are read by two
background threads into a memory-limited cache, the ones around the current
timepoint (and ahead when playing) are read before you get there, and the
display always shows the newest frame you asked for.

V2.9: for large frames the readers also make a reduced display copy (block
mean, preview_f x preview_f pixels; get_preview), so the image on screen is
not shrunk in the window's own thread during playback. Display only.

V3.0: the frame you are on is read first. Dragging the slider across a movie
used to queue a read for every timepoint passed over, and the frame you stopped
on was read last (a 46 MB frame from a hard disk takes ~0.25 s, so up to
~15 s). Now the readers always take the waiting frame nearest the current one
(ahead before behind) and skip the ones left far behind. Closing waits for a
read in progress, so the .nd2 is never closed under a reader.
"""
from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Optional

import numpy as np
from PySide6.QtCore import QObject, Signal


# waiting reads this far from the current timepoint are dropped (asked again if needed)
KEEP_AHEAD = 16                              # play reads up to 12 ahead
KEEP_BEHIND = 4
N_READERS = 2


class FrameStore(QObject):
    ready = Signal(int)                      # timepoint t is now in memory

    def __init__(self, src, n_timepoints: int, frame_bytes: int,
                 budget_bytes: int = 1_500_000_000, preview_f: int = 1) -> None:
        super().__init__()
        self.src = src
        self.T = int(n_timepoints)
        self.preview_f = int(max(1, preview_f))
        per = frame_bytes * (1.0 + (1.0 / self.preview_f ** 2 if self.preview_f > 1 else 0.0))
        self.capacity = int(max(6, min(n_timepoints, budget_bytes // max(1, int(per)))))
        self._cache: "OrderedDict[int, np.ndarray]" = OrderedDict()
        self._prev: dict = {}
        self._pending: set = set()             # asked for, not being read yet
        self._reading: set = set()
        self._focus = 0                          # the timepoint on screen
        self._lock = threading.Lock()
        self._wake = threading.Condition(self._lock)
        self._closed = False
        self._threads = [threading.Thread(target=self._reader, daemon=True,
                                          name=f"PeterPiper frame reader {i + 1}")
                         for i in range(N_READERS)]
        for th in self._threads:
            th.start()

    def get(self, t: int) -> Optional[np.ndarray]:
        """The frame if it is in memory (and asks for it in the background if not).
        The timepoint asked for becomes the one read first (V3.0)."""
        with self._lock:
            self._focus = int(t)
            a = self._cache.get(t)
            if a is not None:
                self._cache.move_to_end(t)
                return a
        self.request(t)
        return None

    def get_preview(self, t: int) -> Optional[np.ndarray]:
        """The reduced display copy of frame t (None if not made / not in memory)."""
        with self._lock:
            return self._prev.get(t)

    def _make_preview(self, a: np.ndarray) -> Optional[np.ndarray]:
        f = self.preview_f
        if f < 2 or a.ndim != 3:
            return None
        c, h, w = a.shape[0], a.shape[1] // f * f, a.shape[2] // f * f
        b = a[:, :h, :w].reshape(c, h // f, f, w // f, f)
        if np.issubdtype(a.dtype, np.integer):
            return ((b.sum(axis=(2, 4), dtype=np.uint64) + f * f // 2) // (f * f)).astype(a.dtype)
        return b.mean(axis=(2, 4)).astype(a.dtype)

    def seed(self, t: int, a: np.ndarray) -> None:
        """V2.9: a frame already read (the start window reads the first one while
        it shows its loading bar)."""
        if 0 <= int(t) < self.T:
            self._put(int(t), np.asarray(a))

    def get_now(self, t: int) -> np.ndarray:
        """The frame, reading it right here if needed (for clicks / drawing)."""
        a = self.get(t)
        if a is not None:
            return a
        a = np.asarray(self.src.frame(int(t)))
        self._put(t, a)
        return a

    def request(self, t: int) -> None:
        if self._closed or not (0 <= t < self.T):
            return
        with self._lock:
            if t in self._cache or t in self._pending or t in self._reading:
                return
            self._pending.add(int(t))
            self._wake.notify()

    def prefetch(self, centre: int, ahead: int = 6, behind: int = 2, step: int = 1) -> None:
        for d in range(1, ahead + 1):
            self.request(centre + d * step)
        for d in range(1, behind + 1):
            self.request(centre - d * step)

    def _next(self) -> Optional[int]:
        """(lock held) The waiting frame to read next: the current one, then the
        nearest ahead, then behind; frames left far behind are dropped."""
        f = self._focus
        for t in [t for t in self._pending if not -KEEP_BEHIND <= t - f <= KEEP_AHEAD]:
            self._pending.discard(t)
        if not self._pending:
            return None
        t = min(self._pending, key=lambda u: (u - f) if u >= f else 2 * (f - u))
        self._pending.discard(t)
        return t

    def _reader(self) -> None:
        while True:
            with self._lock:
                t = self._next()
                while t is None and not self._closed:
                    self._wake.wait()
                    t = self._next()
                if self._closed:
                    return
                self._reading.add(t)
            try:
                a = np.asarray(self.src.frame(int(t)))
            except Exception:                                # noqa: BLE001
                a = None
            if a is not None:
                self._put(t, a)
            with self._lock:
                self._reading.discard(t)
                self._wake.notify_all()                  # close() may be waiting
            if a is not None and not self._closed:
                self.ready.emit(int(t))

    def _put(self, t: int, a: np.ndarray) -> None:
        try:
            pv = self._make_preview(a)
        except Exception:                                    # noqa: BLE001
            pv = None
        with self._lock:
            self._pending.discard(t)
            self._cache[t] = a
            self._cache.move_to_end(t)
            if pv is not None:
                self._prev[t] = pv
            while len(self._cache) > self.capacity:
                old, _ = self._cache.popitem(last=False)
                self._prev.pop(old, None)

    def close(self, wait_s: float = 10.0) -> None:
        """Stop reading. Waits (up to wait_s) for a read in progress, because the
        caller closes the .nd2 next (V3.0: closing it under a reader crashed)."""
        with self._lock:
            self._closed = True
            self._pending.clear()
            self._wake.notify_all()
        me = threading.current_thread()
        for th in self._threads:
            if th is not me:
                th.join(wait_s)
