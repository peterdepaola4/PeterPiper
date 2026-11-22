"""
PeterPiper 4.0: the "ROI troubleshooter" window.

One problem cell, one compartment: the cell tracked several logical ways
(trouble.alternatives / run_candidates), side by side in a calm grid of tiles -
the tracking as it is now first ("now"), then each idea as soon as it is done.
Each tile shows the cell at the start, 25 %, 50 %, 75 % and the end of the
movie with its outline in the cell's own colour, a larger picture at the
time the slider under the grid points to (one slider moves every tile), a
small trace of its main channel and a badge (good / ok / poor - the reasons on
hover). Click a tile, then "Use this for cell k". "Try more options" runs the
next ideas; "Quit troubleshooter" keeps the tracking as it is.

    dlg = TroubleDialog(src, exp, cells, background, t0, previous_out, k, comp,
                        track_kw, overrides=..., parent=...)
    if dlg.exec() == QDialog.Accepted:
        cand, res = dlg.chosen, dlg.chosen_result   # trouble.Candidate / CandidateResult
        overrides = dlg.new_overrides()              # pass to retrack_cells

Demo (screenshots):  python -m peterpiper.gui.troubledlg  [--shot out.png]
"""
from __future__ import annotations

import sys
import threading
from typing import List, Optional

import numpy as np
from PySide6.QtCore import QObject, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QProgressBar, QPushButton, QSizePolicy, QSlider, QVBoxLayout,
                               QWidget)

from .. import trouble as TB
from .. import retrack as RT
from . import theme as TH
from .tips import help_button, tip
from .widgets import cell_colour

TILE_W, TILE_H = 404, 160
BIG, SMALL = 104, 54
PER_PAGE = 9                     # tiles on one page (3 x 3, no scroll bars at 1366 x 768)
GRADE_COLOURS = {"good": "#2E8B57", "ok": "#C9A227", "poor": "#B0413E"}


def _grey(a: np.ndarray, lo: float, hi: float) -> QImage:
    v = np.clip((np.asarray(a, np.float32) - lo) * (255.0 / max(hi - lo, 1e-6)), 0, 255)
    v = np.ascontiguousarray(v.astype(np.uint8))
    img = QImage(v.data, v.shape[1], v.shape[0], v.strides[0], QImage.Format_Grayscale8)
    return img.copy()


class Thumb(QWidget):
    """The cell's crop at one timepoint with its outline (cell colour)."""

    def __init__(self, size: int, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.img: Optional[QImage] = None
        self.paths: List[QPainterPath] = []
        self.colour = QColor("#2299CC")
        self.mark = False
        self.caption = ""

    def set(self, img: Optional[QImage], paths, colour: str, caption: str = "",
            mark: bool = False) -> None:
        self.img, self.paths, self.colour = img, list(paths or []), QColor(colour)
        self.caption, self.mark = caption, mark
        self.update()

    def paintEvent(self, _e) -> None:                                  # noqa: N802
        t = TH.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(0, 0, self.width(), self.height())
        p.fillRect(r, QColor("#000000"))
        if self.img is not None:
            p.drawImage(r, self.img)
            sx = self.width() / max(self.img.width(), 1)
            sy = self.height() / max(self.img.height(), 1)
            p.save()
            p.scale(sx, sy)
            pen = QPen(self.colour, 1.6 / max(sx, 1e-6))
            p.setPen(pen)
            for path in self.paths:
                p.drawPath(path)
            p.restore()
        if self.caption:
            p.setPen(QColor("#FFFFFF"))
            f = p.font()
            f.setPointSizeF(max(6.5, f.pointSizeF() - 2))
            p.setFont(f)
            p.drawText(r.adjusted(3, 0, -3, -2), Qt.AlignBottom | Qt.AlignLeft, self.caption)
        if self.mark:
            p.setPen(QPen(QColor(t.accent), 2))
            p.drawRect(r.adjusted(1, 1, -1, -1))
        p.end()


class Spark(QWidget):
    """A tiny trace of the cell's main channel, with the slider's timepoint."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(26)
        self.y: Optional[np.ndarray] = None
        self.t = 0
        self.colour = QColor("#2299CC")

    def set(self, y, colour: str) -> None:
        self.y = None if y is None else np.asarray(y, float)
        self.colour = QColor(colour)
        self.update()

    def set_t(self, t: int) -> None:
        self.t = int(t)
        self.update()

    def paintEvent(self, _e) -> None:                                  # noqa: N802
        t = TH.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(QPen(QColor(t.border), 1))
        p.drawLine(0, h - 1, w, h - 1)
        y = self.y
        if y is not None and y.size > 1 and np.isfinite(y).any():
            lo, hi = np.nanmin(y), np.nanmax(y)
            span = hi - lo if hi > lo else 1.0
            path = QPainterPath()
            started = False
            for i, v in enumerate(y):
                if not np.isfinite(v):
                    started = False
                    continue
                pt = QPointF(i * (w - 2) / (y.size - 1) + 1, h - 3 - (v - lo) / span * (h - 6))
                if started:
                    path.lineTo(pt)
                else:
                    path.moveTo(pt)
                    started = True
            p.setPen(QPen(self.colour, 1.5))
            p.drawPath(path)
            x = self.t * (w - 2) / (y.size - 1) + 1
            p.setPen(QPen(QColor(t.muted), 1, Qt.DashLine))
            p.drawLine(QPointF(x, 0), QPointF(x, h))
        p.end()


class Tile(QFrame):
    """One way of tracking the cell."""

    def __init__(self, dlg: "TroubleDialog", res: TB.CandidateResult) -> None:
        super().__init__()
        self.dlg, self.res = dlg, res
        self.setObjectName("troubleTile")
        self.setFixedSize(TILE_W, TILE_H)
        self.setCursor(Qt.PointingHandCursor)
        c = res.candidate
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(4)
        head = QHBoxLayout()
        name = QLabel(("<b>Now</b> - as tracked" if c.current else f"<b>{c.label}</b>"))
        name.setTextFormat(Qt.RichText)
        head.addWidget(name, 1)
        self.badge = QLabel(res.grade)
        self.badge.setAlignment(Qt.AlignCenter)
        self.badge.setFixedSize(46, 20)
        col = GRADE_COLOURS.get(res.grade, "#888888")
        self.badge.setStyleSheet(f"QLabel{{background:{col};color:#FFFFFF;border-radius:8px;"
                                 f"padding:1px 4px;font-weight:bold;}}")
        tip(self.badge, "<br>".join(["Score " + f"{res.score:.0f} / 100"] + res.reasons)
            + ("<br><i>" + res.error + "</i>" if res.error else ""),
            title=f"Why '{res.grade}'")
        head.addWidget(self.badge)
        lay.addLayout(head)
        row = QHBoxLayout()
        row.setSpacing(6)
        self.big = Thumb(BIG)
        row.addWidget(self.big)
        right = QVBoxLayout()
        right.setSpacing(3)
        thumbs = QHBoxLayout()
        thumbs.setSpacing(3)
        self.small = [Thumb(SMALL) for _ in range(5)]
        for th in self.small:
            thumbs.addWidget(th)
        right.addLayout(thumbs)
        self.spark = Spark()
        right.addWidget(self.spark)
        row.addLayout(right, 1)
        lay.addLayout(row)
        tip(self, (c.why or "") + "<br>Click to choose this one.", title=c.label if not c.current
            else "The tracking as it is now")
        self.spark.set(res.mean[:, dlg.show_ch] if res.mean.size else None, dlg.colour)
        self.selected = False
        self._style()
        self.refresh_static()

    def _style(self) -> None:
        t = TH.current()
        bd = t.accent if self.selected else t.border
        w = 3 if self.selected else 1
        self.setStyleSheet(f"QFrame#troubleTile{{background:{t.surface};border:{w}px solid {bd};"
                           f"border-radius:8px;}}")

    def set_selected(self, on: bool) -> None:
        self.selected = bool(on)
        self._style()

    def refresh_static(self) -> None:
        T = self.dlg.T
        for th, t in zip(self.small, self.dlg.five):
            th.set(*self.dlg.picture(self.res, t, small=True), caption=f"{t + 1}")

    def show_t(self, t: int) -> None:
        img, paths, col = self.dlg.picture(self.res, t)
        self.big.set(img, paths, col, caption=f"t {t + 1}")
        self.spark.set_t(t)

    def mousePressEvent(self, e) -> None:                              # noqa: N802
        self.dlg.pick(self)


class _Bridge(QObject):
    result = Signal(object)
    progress = Signal(float, str)
    finished = Signal()


class TroubleDialog(QDialog):
    def __init__(self, src, exp, cells, background, t0: int, previous_out: dict, k: int,
                 comp: str, track_kw: dict, overrides: Optional[dict] = None,
                 settings: Optional[dict] = None, frame_t0: Optional[np.ndarray] = None,
                 parent=None) -> None:
        super().__init__(parent)
        from ..manual import LABELS
        self.src, self.exp, self.cells, self.background = src, exp, cells, background
        self.t0, self.prev, self.k, self.comp = int(t0), previous_out, int(k), comp
        self.track_kw, self.overrides = dict(track_kw), dict(overrides or {})
        self.T = int(exp.n_timepoints)
        self.five = sorted({0, (self.T - 1) // 4, (self.T - 1) // 2, 3 * (self.T - 1) // 4,
                            self.T - 1})
        while len(self.five) < 5:
            self.five.append(self.T - 1)
        self.colour = cell_colour(self.k)
        rule = (self.track_kw.get("rules") or {}).get(comp)
        own = self.overrides.get((comp, self.k)) or {}
        cur = own.get("rule") or rule
        st = dict(settings or {"size_tol": self.track_kw.get("size_tol", 0.25),
                               "max_move_um": self.track_kw.get("max_move_um", 3.0)})
        st.update(own.get("settings") or {})
        self.main = int(getattr(cur, "a", getattr(cells[self.k][comp], "channel", 0)) or 0)
        um = float(exp.um_per_px)
        self.box = TB.neighbourhood(previous_out, self.k, comp, cells, um, exp.height, exp.width)
        self.cache = RT.CropCache(src, self.box, self.T)
        first = np.asarray(src.frame(self.t0) if frame_t0 is None else frame_t0)
        snr = TB.channel_snr(first, cells[self.k][comp], um)
        self.cands = TB.alternatives(self.k, comp, cur, exp, cells, first, st,
                                     float(self.track_kw.get("gate_snr", 5.0)), snr=snr)
        self.trace_ch = self.main                    # the trace: the main channel
        self.show_ch = int(np.argmax(snr))           # the picture: where the cell shows best
        # what is shown: the main channel, around the cell (same box every timepoint)
        self.view = self._view_box(um)
        y0, x0, y1, x1 = self.view
        ref = first[self.show_ch, y0:y1, x0:x1].astype(np.float32)
        self.lo, self.hi = (float(v) for v in np.percentile(ref, [1, 99.7]))
        self.results: List[TB.CandidateResult] = []
        self.tiles: List[Tile] = []
        self.page = 0
        self.chosen: Optional[TB.Candidate] = None
        self.chosen_result: Optional[TB.CandidateResult] = None
        self._cancel = threading.Event()
        self._running = False
        self._ran = 0                                    # candidates started so far
        self.setWindowTitle(f"ROI troubleshooter - cell {self.k + 1}, "
                            f"{LABELS.get(comp, comp).lower()}")
        self._build(LABELS.get(comp, comp).lower())
        self.slider.setValue(self.t0)
        self._run(self._next_batch())

    # --------------------------------------------------------------- layout
    def _build(self, what: str) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)
        top = QHBoxLayout()
        title = QLabel(f"<b>Cell {self.k + 1}'s {what}</b> - tracked several ways. "
                       f"Pick the one that follows it best.")
        title.setTextFormat(Qt.RichText)
        top.addWidget(title, 1)
        top.addWidget(help_button(
            "Each tile is this one cell tracked a different way: on another channel, with a "
            "second channel helping, or with looser / tighter size and move limits. Only "
            "channels that show this cell are tried. The other cells are not changed.<br>"
            "<b>good / ok / poor</b>: how steady the outline is - redrawn at every timepoint, "
            "steady size, no jumps, close to what you drew (hover a badge for the reasons).",
            title="ROI troubleshooter", pic="trackx_troubleshooter"))
        lay.addLayout(top)
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(8)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.grid_host.setFixedSize(3 * TILE_W + 2 * 8, 3 * TILE_H + 2 * 8)
        lay.addWidget(self.grid_host, 0, Qt.AlignHCenter)
        srow = QHBoxLayout()
        srow.addWidget(QLabel("Timepoint"))
        shown = QLabel(f"(showing {self.exp.channels[self.show_ch]})")
        tip(shown, "The pictures show the channel in which this cell is brightest; the small "
                   "trace under them is its mean in that channel.", title="Channel shown")
        srow.addWidget(shown)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, self.T - 1)
        self.slider.valueChanged.connect(self._scrub)
        tip(self.slider, "Moves every tile's large picture to this timepoint together.",
            title="Timepoint")
        srow.addWidget(self.slider, 1)
        self.lbl_t = QLabel("")
        self.lbl_t.setMinimumWidth(70)
        srow.addWidget(self.lbl_t)
        self.btn_prev = QPushButton("◀")
        self.btn_next = QPushButton("▶")
        for b, d, txt in ((self.btn_prev, -1, "Earlier ideas"), (self.btn_next, 1, "Later ideas")):
            b.setFixedWidth(34)
            b.clicked.connect(lambda _=False, dd=d: self._turn(dd))
            tip(b, f"{txt} (the tiles of the other page).", title=txt)
            srow.addWidget(b)
        lay.addLayout(srow)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        lay.addWidget(self.bar)
        self.lbl_status = QLabel("")
        lay.addWidget(self.lbl_status)
        brow = QHBoxLayout()
        self.btn_use = QPushButton(f"Use this for cell {self.k + 1}")
        self.btn_use.setProperty("primary", True)
        self.btn_use.setMinimumHeight(36)
        self.btn_use.setEnabled(False)
        self.btn_use.clicked.connect(self._use)
        tip(self.btn_use, "Track this cell's compartment the chosen way from now on (saved with "
                          "the ROIs and written in the methods). Only this cell is re-tracked.",
            title="Use this")
        self.btn_more = QPushButton("Try more options")
        self.btn_more.clicked.connect(self._more)
        tip(self.btn_more, "Run the next ideas (other channel pairs, AND / WITH, other limits).",
            title="Try more options")
        self.btn_quit = QPushButton("Quit troubleshooter")
        self.btn_quit.clicked.connect(self.reject)
        tip(self.btn_quit, "Close and keep the tracking as it is now.", title="Quit")
        brow.addWidget(self.btn_use, 2)
        brow.addWidget(self.btn_more, 1)
        brow.addWidget(self.btn_quit, 1)
        lay.addLayout(brow)
        self._update_buttons()

    def _view_box(self, um: float) -> tuple:
        rs = [self.cells[self.k][c] for c in self.cells[self.k]]
        g = (self.prev.get("rois") or {}).get(self.comp)
        if g is not None:
            rs += [g[t][self.k] for t in range(len(g)) if g[t][self.k].area]
        b = np.array([r.bbox for r in rs])
        pad = int(4.0 / max(um, 1e-6))
        y0, x0, y1, x1 = b[:, 0].min() - pad, b[:, 1].min() - pad, b[:, 2].max() + pad, \
            b[:, 3].max() + pad
        side = max(y1 - y0, x1 - x0)
        cy, cx = (y0 + y1) // 2, (x0 + x1) // 2
        by0, bx0, by1, bx1 = self.box
        y0 = int(np.clip(cy - side // 2, by0, max(by0, by1 - side)))
        x0 = int(np.clip(cx - side // 2, bx0, max(bx0, bx1 - side)))
        return y0, x0, min(by1, y0 + side), min(bx1, x0 + side)

    # --------------------------------------------------------------- pictures
    def picture(self, res: TB.CandidateResult, t: int, small: bool = False):
        y0, x0, y1, x1 = self.view
        try:
            a = self.cache.crop(int(t), y0, y1, x0, x1)[self.show_ch]
        except Exception:                                          # noqa: BLE001
            return None, [], self.colour
        img = _grey(a, self.lo, self.hi)
        paths = []
        if res.rois and 0 <= t < len(res.rois):
            r = res.rois[t]
            for pts in r.contours():
                path = QPainterPath()
                path.moveTo(pts[0][0] - x0 + 0.5, pts[0][1] - y0 + 0.5)
                for px, py in pts[1:]:
                    path.lineTo(px - x0 + 0.5, py - y0 + 0.5)
                path.closeSubpath()
                paths.append(path)
        return img, paths, self.colour

    # --------------------------------------------------------------- running
    def _next_batch(self) -> list:
        rest = [c for c in self.cands if not c.current][self._ran:]
        n = PER_PAGE - 1
        batch = rest[:n]
        if self._ran == 0:
            batch = [self.cands[0]] + batch
        self._ran += len([c for c in batch if not c.current])
        return batch

    def _run(self, batch: list) -> None:
        if not batch:
            self.lbl_status.setText("Every idea for this cell has been tried.")
            return
        self._cancel = threading.Event()
        self._running = True
        self._update_buttons()
        br = _Bridge()
        self._bridge = br
        br.result.connect(self._on_result)
        br.progress.connect(self._on_progress)
        br.finished.connect(self._on_done)
        n = len([c for c in batch if not c.current])
        self.lbl_status.setText(f"Trying {n} ways for cell {self.k + 1} - the tiles appear as "
                                f"each one is done.")

        def work() -> None:
            try:
                self.cache.fill(lambda f, m: (br.progress.emit(0.2 * float(f), str(m)),
                                              not self._cancel.is_set())[1])
                for r in TB.run_candidates(
                        self.src, self.exp, self.cells, self.background, self.t0, self.prev,
                        self.k, self.comp, batch, self.track_kw, self.overrides,
                        progress=lambda f, m: (br.progress.emit(float(f), str(m)),
                                               not self._cancel.is_set())[1],
                        cancel=self._cancel, cache=self.cache):
                    br.result.emit(r)
            except Exception as exc:                                # noqa: BLE001
                br.progress.emit(-1.0, f"Stopped: {exc}")
            finally:
                br.finished.emit()

        self._thread = threading.Thread(target=work, daemon=True)
        self._thread.start()

    def _on_progress(self, f: float, msg: str) -> None:
        if f >= 0:
            self.bar.setValue(int(1000 * f))
        else:
            self.lbl_status.setText(msg)

    def _on_result(self, r: TB.CandidateResult) -> None:
        self.results.append(r)
        if r.candidate.current or self._page_of(r) == self.page:
            self._show_page(self.page)

    def _on_done(self) -> None:
        self._running = False
        self.bar.setValue(1000)
        best = TB.ranked(self.results)[0] if self.results else None
        if best is not None and not best.candidate.current:
            self.lbl_status.setText(f"Done. Steadiest: \"{best.candidate.label}\" "
                                    f"({best.grade}). Look at them all before you choose.")
        elif best is not None:
            self.lbl_status.setText("Done. None of the ideas looks steadier than now - "
                                    "keeping it is fine.")
        self._update_buttons()

    def _page_of(self, r: TB.CandidateResult) -> int:
        others = [x for x in self.results if not x.candidate.current]
        if r.candidate.current:
            return self.page
        return others.index(r) // (PER_PAGE - 1)

    def _page_results(self, page: int) -> list:
        now = [x for x in self.results if x.candidate.current]
        others = [x for x in self.results if not x.candidate.current]
        return now + others[page * (PER_PAGE - 1):(page + 1) * (PER_PAGE - 1)]

    def _show_page(self, page: int) -> None:
        sel = next((t.res for t in self.tiles if t.selected), None)
        self.page = max(0, int(page))
        for t in self.tiles:
            t.setParent(None)
            t.deleteLater()
        self.tiles = []
        for i, r in enumerate(self._page_results(self.page)):
            tile = Tile(self, r)
            tile.set_selected(r is sel)
            tile.show_t(self.slider.value())
            self.grid.addWidget(tile, i // 3, i % 3)
            self.tiles.append(tile)
        self._update_buttons()

    def _turn(self, d: int) -> None:
        n_pages = max(1, -(-len([x for x in self.results if not x.candidate.current])
                           // (PER_PAGE - 1)))
        self._show_page(int(np.clip(self.page + d, 0, n_pages - 1)))

    def _scrub(self, t: int) -> None:
        self.lbl_t.setText(f"{t + 1} of {self.T}")
        for tile in self.tiles:
            tile.show_t(t)

    def pick(self, tile: Tile) -> None:
        for t in self.tiles:
            t.set_selected(t is tile)
        self.chosen_result = tile.res
        self.chosen = tile.res.candidate
        self._update_buttons()

    def _more(self) -> None:
        batch = self._next_batch()
        if batch:
            self._show_page(self._page_of_next())
        self._run(batch)

    def _page_of_next(self) -> int:
        return len([x for x in self.results if not x.candidate.current]) // (PER_PAGE - 1)

    def _use(self) -> None:
        if self.chosen is None:
            return
        self._cancel.set()
        self.accept()

    def reject(self) -> None:
        self._cancel.set()
        self.chosen, self.chosen_result = None, None
        super().reject()

    def _update_buttons(self) -> None:
        left = len([c for c in self.cands if not c.current]) - self._ran
        self.btn_use.setEnabled(self.chosen is not None and not self.chosen.current)
        if self.chosen is not None and self.chosen.current:
            self.btn_use.setText("This is how it is tracked now")
        elif self.chosen is not None:
            self.btn_use.setText(f"Use \"{self.chosen.label}\" for cell {self.k + 1}")
        else:
            self.btn_use.setText(f"Use this for cell {self.k + 1}")
        self.btn_more.setEnabled(not self._running and left > 0)
        n_pages = max(1, -(-len([x for x in self.results if not x.candidate.current])
                           // (PER_PAGE - 1)))
        self.btn_prev.setEnabled(self.page > 0)
        self.btn_next.setEnabled(self.page < n_pages - 1)

    def new_overrides(self) -> dict:
        """The per-cell overrides with the chosen idea (unchanged when none / "now")."""
        if self.chosen is None:
            return dict(self.overrides)
        return TB.choice_overrides(self.overrides, self.k, self.comp, self.chosen)

    def wait(self, timeout: float = 60.0) -> bool:
        """Tests / demo: wait for the running ideas (processing events)."""
        import time
        from PySide6.QtWidgets import QApplication
        end = time.time() + timeout
        while (self._running or (getattr(self, "_thread", None) is not None
                                 and self._thread.is_alive())) and time.time() < end:
            QApplication.processEvents()
            time.sleep(0.02)
        QApplication.processEvents()
        return not self._running


# ==========================================================================
#  Standalone demo on a synthetic movie (screenshots)
# ==========================================================================
def demo(shot: Optional[str] = None, more: bool = False) -> int:
    from pathlib import Path
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    TH.apply(app)
    here = Path(__file__).resolve().parents[3] / "dev_tests"
    sys.path.insert(0, str(here))
    import synth_trackx as S                                       # noqa: E402
    from ..manual import track_cells
    from ..rules import TrackRule
    frames, truth = S.make(T=16)
    T, C, H, W = frames.shape
    exp = S.Exp(T, C, H, W)
    src = S.Src(frames)
    bg = S.background(H, W)
    t0 = 4
    cells = S.seeds(frames, truth, t0)
    rules = {"nucleus": TrackRule("nucleus", 0), "cytoplasm": TrackRule("cytoplasm", 1)}
    prev = track_cells(src, exp, cells, bg, t0, rules=rules)
    dlg = TroubleDialog(src, exp, cells, bg, t0, prev, S.PROBLEM, "nucleus", dict(rules=rules))
    dlg.resize(dlg.sizeHint())
    dlg.show()
    dlg.wait()
    if dlg.tiles:
        best = TB.ranked([t.res for t in dlg.tiles])[0]
        dlg.pick(next(t for t in dlg.tiles if t.res is best))
    dlg.slider.setValue(T // 2)
    if more:
        dlg._more()
        dlg.wait()
    app.processEvents()
    if shot:
        dlg.grab().save(shot)
        print(f"saved {shot} ({dlg.width()} x {dlg.height()})")
        return 0
    return app.exec()


if __name__ == "__main__":
    args = sys.argv[1:]
    out = args[args.index("--shot") + 1] if "--shot" in args else None
    sys.exit(demo(out, "--more" in args))
