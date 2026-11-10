"""
The image canvas: one timepoint, one or two channels, with ROI outlines on top,
and the brightness scale bar underneath.

Interaction
    scroll / drag        zoom and pan (pyqtgraph defaults)
    left click on an ROI include / exclude it; shift-click only selects it
    Draw ROI mode        left click adds a vertex, double-click or right click
                         closes the polygon, Esc cancels
    Draw box mode        two left clicks set opposite corners of the background box
    Lasso mode (V2.5)    press, draw around a region, release: a freehand outline
                         (the background drawn by hand)
    Polyline mode (V2.5) clicks add points of a line, double-click / right-click /
                         Enter finishes it (tracker boundary lines)

Brightness
    One horizontal scale bar with a single handle: the handle is the white
    point. Everything right of it displays as white, and the bar itself shows
    the grey ramp and a faint histogram of the frame, so you can see what you
    are clipping. Drag it, scroll on it, or double-click it for auto. The
    black point is set automatically from the image background. The setting
    is kept when you step through time (so brightness changes you see are
    real), and remembered per channel.

All outlines are drawn as a few long polylines with NaN breaks rather than one
item per ROI, which keeps redrawing instant even with hundreds of cells.

BLOCK: new overlay colours / layers go in _rebuild_overlay().
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QLinearGradient, QPainter,
                           QPainterPath, QPen)
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QSizePolicy,
                               QVBoxLayout, QWidget)

from ..segment import Roi

pg.setConfigOptions(imageAxisOrder="row-major", antialias=False)

COL_INCLUDE = (255, 212, 0)
COL_EXCLUDE = (175, 175, 175)          # excluded: grey dotted (as in the trace panel)
COL_SELECT = (0, 229, 255)
COL_BACK = (60, 255, 60)
COL_DRAW = (0, 229, 255)
COL_WALL = (255, 90, 40)               # tracker boundary lines
ACCENT = QColor(0, 200, 255)

# overlay colours: first channel magenta, second green (colour-blind safe;
# overlap shows as white)
OVERLAY_COLOURS = ((1.0, 0.0, 1.0), (0.0, 1.0, 0.0))


def _poly_arrays(rois: Sequence[Roi]) -> tuple[np.ndarray, np.ndarray]:
    """Concatenate ROI outlines into one x/y pair with NaN separators."""
    xs: List[np.ndarray] = []
    ys: List[np.ndarray] = []
    nan = np.array([np.nan])
    for r in rois:
        for c in r.contours():
            xs.append(np.append(np.append(c[:, 0], c[0, 0]), nan))
            ys.append(np.append(np.append(c[:, 1], c[0, 1]), nan))
    if not xs:
        return np.array([]), np.array([])
    return np.concatenate(xs), np.concatenate(ys)


def _nice_ticks(lo: float, hi: float) -> List[float]:
    """1-2-5 ticks between lo and hi (both > 0) on a log axis."""
    out = []
    if hi <= lo or hi <= 0:
        return out
    e0 = int(math.floor(math.log10(max(lo, 1e-9))))
    e1 = int(math.ceil(math.log10(hi)))
    for e in range(e0, e1 + 1):
        for m in (1, 2, 5):
            v = m * 10 ** e
            if lo <= v <= hi:
                out.append(float(v))
    return out


def _fmt(v: float) -> str:
    if v >= 10000:
        return f"{v / 1000:.0f}k"
    if v >= 1000:
        return f"{v / 1000:.1f}k".replace(".0k", "k")
    if v >= 1:
        return f"{v:.0f}"
    return f"{v:g}"


# ==========================================================================
#  The scale bar
# ==========================================================================
class ScaleBar(QWidget):
    """
    A log-scaled intensity bar with one draggable white-point handle.

    Absolute mode (one channel): the axis is in counts, from the black point
    to the brightest pixel. Relative mode (overlays): the axis is a multiple
    of each channel's automatic white point (x1 = auto).
    """

    changed = Signal(float)          # new white point (counts, or relative)
    auto_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._fit_height()
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.SizeHorCursor)
        self.setToolTip("Brightness: drag the handle to set the white point "
                        "(left = brighter). Scroll to nudge, double-click for auto.\n"
                        "Display only - measurements are never affected.")
        self._lo, self._hi = 1.0, 1000.0     # axis range (log)
        self._white = 500.0
        self._relative = False
        self._hist: Optional[np.ndarray] = None
        self._drag = False

    def _fit_height(self) -> None:
        """Bar + tick labels, sized from the current text size."""
        self.setFixedHeight(int(28 + self.fontMetrics().height() * 1.3))

    def changeEvent(self, ev) -> None:                       # noqa: N802
        from PySide6.QtCore import QEvent
        if ev.type() == QEvent.FontChange:
            self._fit_height()
        super().changeEvent(ev)

    # ------------------------------------------------------------ public
    def set_axis(self, lo: float, hi: float, white: float, relative: bool,
                 hist: Optional[np.ndarray] = None) -> None:
        self._lo = max(1e-6, float(lo))
        self._hi = max(self._lo * 1.5, float(hi))
        self._white = float(np.clip(white, self._lo, self._hi))
        self._relative = relative
        self._hist = hist
        self.update()

    @property
    def white(self) -> float:
        return self._white

    # ----------------------------------------------------------- mapping
    def _track(self) -> QRectF:
        return QRectF(10, 6, max(10, self.width() - 20), 16)

    def _x_of(self, v: float) -> float:
        r = self._track()
        f = (math.log(max(v, self._lo)) - math.log(self._lo)) / \
            (math.log(self._hi) - math.log(self._lo))
        return r.left() + float(np.clip(f, 0, 1)) * r.width()

    def _v_of(self, x: float) -> float:
        r = self._track()
        f = float(np.clip((x - r.left()) / r.width(), 0, 1))
        return math.exp(math.log(self._lo) + f * (math.log(self._hi) - math.log(self._lo)))

    # ------------------------------------------------------------ paint
    def paintEvent(self, _ev) -> None:                       # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pal = self.palette()
        text = pal.color(pal.ColorRole.WindowText)
        r = self._track()
        xw = self._x_of(self._white)

        # grey ramp up to the white point, white beyond it
        path = QPainterPath()
        path.addRoundedRect(r, 5, 5)
        p.setClipPath(path)
        g = QLinearGradient(r.left(), 0, max(r.left() + 1, xw), 0)
        g.setColorAt(0.0, QColor(0, 0, 0))
        g.setColorAt(1.0, QColor(255, 255, 255))
        p.fillRect(QRectF(r.left(), r.top(), xw - r.left(), r.height()), QBrush(g))
        p.fillRect(QRectF(xw, r.top(), r.right() - xw, r.height()), QColor(255, 255, 255))
        # clipped zone: faint accent hatch so it reads as "saturated on screen"
        clip = QColor(ACCENT)
        clip.setAlpha(55)
        p.fillRect(QRectF(xw, r.top(), r.right() - xw, r.height()),
                   QBrush(clip, Qt.BDiagPattern))

        # histogram silhouette
        if self._hist is not None and self._hist.size and self._hist.max() > 0:
            h = self._hist.astype(float)
            h = np.log1p(h) / np.log1p(h.max())
            n = h.size
            poly = QPainterPath(QPointF(r.left(), r.bottom()))
            for i, v in enumerate(h):
                x = r.left() + (i + 0.5) / n * r.width()
                poly.lineTo(QPointF(x, r.bottom() - v * (r.height() - 2)))
            poly.lineTo(QPointF(r.right(), r.bottom()))
            poly.closeSubpath()
            fill = QColor(ACCENT)
            fill.setAlpha(90)
            p.setPen(Qt.NoPen)
            p.setBrush(fill)
            p.drawPath(poly)
        p.setClipping(False)

        # frame
        frame = QColor(text)
        frame.setAlpha(90)
        p.setPen(QPen(frame, 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r, 5, 5)

        # ticks
        f = QFont(self.font())
        f.setPointSizeF(max(7.0, f.pointSizeF() - 1.5))
        p.setFont(f)
        tc = QColor(text)
        tc.setAlpha(170)
        p.setPen(QPen(tc, 1))
        ticks = ([0.1, 0.2, 0.5, 1, 2, 5, 10] if self._relative
                 else _nice_ticks(self._lo, self._hi))
        last_x = -1e9
        for v in ticks:
            if not (self._lo <= v <= self._hi):
                continue
            x = self._x_of(v)
            p.drawLine(QPointF(x, r.bottom()), QPointF(x, r.bottom() + 3))
            label = (f"x{v:g}" if self._relative else _fmt(v))
            tw = p.fontMetrics().horizontalAdvance(label) + 6
            if x - last_x > tw + 6:
                p.drawText(QRectF(x - tw / 2, r.bottom() + 3, tw, p.fontMetrics().height() + 2),
                           Qt.AlignHCenter, label)
                last_x = x

        # handle
        p.setPen(QPen(ACCENT, 2))
        p.drawLine(QPointF(xw, r.top() - 3), QPointF(xw, r.bottom() + 1))
        p.setBrush(ACCENT)
        p.setPen(QPen(QColor(20, 20, 20), 1))
        p.drawEllipse(QPointF(xw, r.top() + r.height() / 2), 6.5, 6.5)
        p.end()

    # ------------------------------------------------------------ mouse
    def mousePressEvent(self, ev) -> None:                   # noqa: N802
        if ev.button() == Qt.LeftButton:
            self._drag = True
            self._set_from_x(ev.position().x())

    def mouseMoveEvent(self, ev) -> None:                    # noqa: N802
        if self._drag:
            self._set_from_x(ev.position().x())

    def mouseReleaseEvent(self, _ev) -> None:                # noqa: N802
        self._drag = False

    def mouseDoubleClickEvent(self, _ev) -> None:            # noqa: N802
        self.auto_requested.emit()

    def wheelEvent(self, ev) -> None:                        # noqa: N802
        step = 1.0 if ev.angleDelta().y() > 0 else -1.0
        x = self._x_of(self._white) - step * self._track().width() * 0.03
        self._set_from_x(x)
        ev.accept()

    def _set_from_x(self, x: float) -> None:
        self._white = self._v_of(x)
        self.update()
        self.changed.emit(self._white)


# ==========================================================================
#  The canvas
# ==========================================================================
class ImageView(QWidget):
    """Image + ROI overlay with click selection, manual drawing and the scale bar."""

    roi_clicked = Signal(int, bool)        # (roi index, toggle_include)
    polygon_done = Signal(object)          # list of (x, y)
    rect_done = Signal(object)             # (x, y, w, h)
    empty_clicked = Signal(float, float)   # (x, y): a click where there is no ROI
    context_requested = Signal(float, float, int)   # right-click: (x, y, roi index or -1)
    line_done = Signal(object)             # ((x0, y0), (x1, y1)): a cut line (Split tool)
    point_clicked = Signal(float, float, bool)   # v2.0: every left click (x, y, shift held)
    escape_pressed = Signal()                     # v2.1: Esc (the window turns its tool off)
    wheel_steps = Signal(int)                     # v2.1: wheel while an ROI is being sized
    stroke_done = Signal(object)                  # v2.2: a freehand line [(x, y), ...] (Split)
    lasso_done = Signal(object)                   # v2.5: a freehand outline [(x, y), ...]
    polyline_done = Signal(object)                # v2.5: a line of clicked points [(x, y), ...]
    status = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)

        self.glw = pg.GraphicsLayoutWidget()
        from . import theme as TH                  # V2.9: the image sits on the window's colour
        self.glw.setBackground(TH.current().bg if TH._current is not None else "k")
        self.glw._pd4_bg = True                    # follows a theme change
        lay.addWidget(self.glw, 1)
        self.wheel_adjust = False                 # True: the wheel sizes an ROI, not zoom
        self.glw.viewport().installEventFilter(self)
        self.vb = self.glw.addViewBox(row=0, col=0, lockAspect=True, invertY=True)
        self.vb.setMenuEnabled(False)
        self.img = pg.ImageItem(axisOrder="row-major")
        # display only: when zoomed out the picture is drawn at screen resolution
        # (smooth scrubbing); zoomed in, every pixel is shown. Measurements always
        # use the raw full-resolution pixels.
        self.img.setAutoDownsample(True)
        self.vb.addItem(self.img)
        self._preview, self._preview_f, self._showing_preview = None, 1, False
        self.vb.sigRangeChanged.connect(self._range_changed)

        # ---- the one brightness control -----------------------------------
        bar_row = QWidget()
        bl = QHBoxLayout(bar_row)
        bl.setContentsMargins(4, 0, 4, 0)
        bl.setSpacing(8)
        lab = QLabel("Brightness")
        lab.setToolTip("Display only - the measurements are never affected.")
        bl.addWidget(lab)
        self.bar = ScaleBar()
        self.bar.changed.connect(self._on_white)
        self.bar.auto_requested.connect(self.auto_contrast)
        bl.addWidget(self.bar, 1)
        self.lbl_levels = QLabel("")
        self.lbl_levels.setProperty("muted", True)
        self.lbl_levels.hide()          # its text is the bar's tooltip, so the bar keeps its room
        self.btn_auto = QPushButton("Auto")
        self.btn_auto.setToolTip("Black point at the background, white point near "
                                 "the brightest cells of this frame.")
        self.btn_auto.clicked.connect(self.auto_contrast)
        bl.addWidget(self.btn_auto)
        lay.addWidget(bar_row)

        def curve(color, width, dash=False):
            pen = pg.mkPen(QColor(*color), width=width)
            if dash:
                pen.setStyle(Qt.DotLine)
            c = pg.PlotCurveItem(pen=pen, connect="finite")
            c.setZValue(10)
            self.vb.addItem(c)
            return c

        self._c_inc = curve(COL_INCLUDE, 1.4)
        self._c_exc = curve(COL_EXCLUDE, 1.2, dash=True)
        self._c_sel = curve(COL_SELECT, 2.6)
        self._c_bak = curve(COL_BACK, 2.0)
        self._c_draw = curve(COL_DRAW, 1.6)
        self._c_ctx = curve((170, 170, 170), 0.9, dash=True)   # other compartments, faint
        self._c_ctx.setZValue(8)
        self._c_wall = curve(COL_WALL, 2.2)                     # tracker boundary lines
        self._c_wall.setZValue(12)
        self._c_wall_sel = curve((255, 255, 255), 3.4)          # ... of the selected cell
        self._c_wall_sel.setZValue(11)
        self._c_bgx = pg.ScatterPlotItem(size=2, pen=None, brush=pg.mkBrush(255, 60, 60, 160),
                                         pxMode=True)            # background pixels left out
        self._c_bgx.setZValue(9)
        self.vb.addItem(self._c_bgx)

        self._labels: List[pg.TextItem] = []
        self._rois: List[Roi] = []
        self._background: Optional[Roi] = None
        self._selected: Optional[int] = None
        self._show_numbers = True
        self._show_outlines = True
        self._ctx_rois: List[Roi] = []
        self._shape = (1, 1)

        # display state: per view key, the black / auto-white per plane and the
        # user's white point (absolute counts for 1 plane, relative for 2)
        self._planes: List[np.ndarray] = []
        self._key = None
        self._ranges: Dict[object, dict] = {}

        self._mode = "view"              # "view" | "polygon" | "rect"
        self._points: List[tuple] = []

        self.glw.scene().sigMouseClicked.connect(self._on_click)
        self.glw.scene().sigMouseMoved.connect(self._on_move)

    # ------------------------------------------------------------- image
    @staticmethod
    def _auto_range(plane: np.ndarray) -> Tuple[float, float]:
        sub = plane[::4, ::4]
        lo, hi = np.percentile(sub, [0.5, 99.8])
        if hi <= lo:
            hi = lo + 1
        return float(lo), float(hi)

    def show_planes(self, planes: Sequence[np.ndarray], key=None,
                    autorange: bool = False, preview=None, preview_f: int = 1) -> None:
        """
        Show one plane (grey) or two (magenta + green overlay).

        `key` identifies what is being viewed (e.g. the channel or overlay);
        brightness is remembered per key and kept while stepping through time.
        """
        self._planes = [np.asarray(p) for p in planes]
        # V2.9: a reduced display copy (preview_f x smaller), shown while the image is
        # on screen at less than one screen pixel per copy pixel
        self._preview = [np.asarray(p) for p in preview] if preview is not None else None
        self._preview_f = int(preview_f)
        self._key = key
        st = self._ranges.get(key)
        if st is None or len(st["auto"]) != len(self._planes):
            st = {"auto": [self._auto_range(p) for p in self._planes]}
            st["white"] = st["auto"][0][1] if len(self._planes) == 1 else 1.0
            self._ranges[key] = st
        self._render()
        shape = self._planes[0].shape[:2]
        if shape != self._shape:
            self._shape = shape
            autorange = True
        if autorange:
            self.vb.autoRange(padding=0.01)

    def _use_preview(self) -> bool:
        if getattr(self, "_preview", None) is None or self._preview_f < 2:
            return False
        try:
            px = self.vb.viewPixelSize()               # data pixels per screen pixel
            dpr = max(1.0, float(self.glw.devicePixelRatioF()))
        except Exception:                                          # noqa: BLE001
            return False
        return min(px) * dpr >= self._preview_f

    def _shown(self) -> list:
        """What setImage gets: the display copy (when small enough on screen) or the
        frame; the image rectangle always covers the full frame's pixels."""
        self._showing_preview = self._use_preview()
        return self._preview if self._showing_preview else self._planes

    def _place_image(self) -> None:
        from PySide6.QtCore import QRectF
        if getattr(self, "_showing_preview", False):  # block f x f = f x f data pixels
            h, w = (n * self._preview_f for n in self._preview[0].shape[:2])
        else:
            h, w = self._planes[0].shape[:2]
        self.img.setRect(QRectF(0, 0, w, h))

    def _range_changed(self, *_a) -> None:
        """Zoomed in past the display copy's resolution: show the full frame."""
        if getattr(self, "_showing_preview", False) and not self._use_preview():
            self._render()

    def _render(self) -> None:
        if not self._planes:
            return
        st = self._ranges[self._key]
        shown = self._shown()
        if len(self._planes) == 1:
            plane = self._planes[0]
            lo = st["auto"][0][0]
            white = max(st["white"], lo + 1)
            self.img.setImage(shown[0], autoLevels=False, levels=(lo, white))
            self._place_image()
            sub = plane[::8, ::8]                  # the histogram is only a guide
            top = float(max(sub.max(), white * 1.05, lo + 2))
            span_lo = max(1.0, lo)
            edges = np.geomspace(span_lo, top, 65)
            hist = np.histogram(sub, bins=edges)[0]
            self.bar.set_axis(span_lo, top, white, relative=False, hist=hist)
            self._set_levels(f"{lo:.0f} - {white:.0f} counts")
        else:
            g = st["white"]
            rgb = np.zeros(shown[0].shape + (3,), np.float32)
            for p, (lo, hi), col in zip(shown, st["auto"], OVERLAY_COLOURS):
                v = np.clip((p.astype(np.float32) - lo) / max((hi - lo) * g, 1e-6), 0, 1)
                for i in range(3):
                    if col[i]:
                        rgb[..., i] = np.maximum(rgb[..., i], v * col[i])
            self.img.setImage((rgb * 255).astype(np.uint8), autoLevels=False,
                              levels=(0, 255))
            self._place_image()
            self.bar.set_axis(0.1, 10.0, g, relative=True)
            self._set_levels(f"white point x{g:.2f} of auto")

    def _set_levels(self, text: str) -> None:
        self.lbl_levels.setText(text)
        self.bar.setToolTip(f"Display {text}. Drag the handle to set the white point "
                            "(left = brighter); scroll to nudge; double-click for auto.")

    def _on_white(self, v: float) -> None:
        st = self._ranges.get(self._key)
        if st is None:
            return
        st["white"] = float(v)
        if len(self._planes) == 1:          # levels only - no re-upload while dragging
            lo = st["auto"][0][0]
            white = max(st["white"], lo + 1)
            self.img.setLevels((lo, white))
            self._set_levels(f"{lo:.0f} - {white:.0f} counts")
        else:
            self._render()

    def auto_contrast(self) -> None:
        if not self._planes:
            return
        self._ranges.pop(self._key, None)
        self.show_planes(self._planes, self._key)

    def fit(self) -> None:
        self.vb.autoRange(padding=0.01)

    # -------------------------------------------------------------- ROIs
    def set_rois(self, rois: Sequence[Roi], background: Optional[Roi] = None,
                 selected: Optional[int] = None,
                 colours: Optional[Dict[int, str]] = None) -> None:
        """colours: {roi index: '#rrggbb'} for included cells - the same colour as
        the cell's trace in the trace panel (others: yellow included / red dotted)."""
        self._rois = list(rois)
        self._background = background
        self._selected = selected
        self._colours = dict(colours or {})
        self._rebuild_overlay()

    def eventFilter(self, obj, ev) -> bool:                   # noqa: N802
        from PySide6.QtCore import QEvent
        if self._mode in ("freehand", "lasso") and ev.type() in (
                QEvent.MouseButtonPress, QEvent.MouseMove, QEvent.MouseButtonRelease,
                QEvent.MouseButtonDblClick):
            return self._freehand_event(ev)
        if self.wheel_adjust and ev.type() == QEvent.Wheel:
            dy = ev.angleDelta().y()
            if dy:
                self.wheel_steps.emit(int(round(dy / 120.0)) or (1 if dy > 0 else -1))
            return True
        return super().eventFilter(obj, ev)

    def set_walls(self, lines: Sequence[Sequence[tuple]], selected: Sequence[Sequence[tuple]] = ()
                  ) -> None:
        """V2.5: tracker boundary lines (lists of image (x, y) points); `selected`
        (the selected cell's lines) are drawn with a white halo."""
        def arrays(ls):
            xs, ys = [], []
            for ln in ls:
                if len(ln) >= 1:
                    pts = list(ln) if len(ln) > 1 else [ln[0], ln[0]]
                    xs += [float(q[0]) for q in pts] + [np.nan]
                    ys += [float(q[1]) for q in pts] + [np.nan]
            return np.asarray(xs, float), np.asarray(ys, float)
        self._walls = [list(ln) for ln in lines]
        self._c_wall.setData(*arrays(self._walls))
        self._c_wall_sel.setData(*arrays([list(ln) for ln in selected]))

    def set_excluded_pixels(self, ys: np.ndarray, xs: np.ndarray) -> None:
        """V2.5: the background pixels left out at this timepoint (bright / moving
        objects), as small red dots (display only); empty arrays clear them."""
        if len(xs) > 200000:                       # display only: every k-th pixel
            k = int(np.ceil(len(xs) / 200000))
            ys, xs = ys[::k], xs[::k]
        self._c_bgx.setData(x=np.asarray(xs, float) + 0.5, y=np.asarray(ys, float) + 0.5)

    def set_context(self, rois: Sequence[Roi]) -> None:
        """Faint dotted outlines (e.g. the other compartments) - not clickable."""
        self._ctx_rois = [r for r in rois if r is not None and r.area]
        if self._show_outlines:
            x, y = _poly_arrays(self._ctx_rois)
            self._c_ctx.setData(x, y)

    def set_show_outlines(self, on: bool) -> None:
        """Outlines (and their numbers) on / off - to look at the cells themselves."""
        self._show_outlines = bool(on)
        x, y = _poly_arrays(self._ctx_rois) if on else (np.array([]), np.array([]))
        self._c_ctx.setData(x, y)
        self._rebuild_overlay()

    def set_show_numbers(self, on: bool) -> None:
        self._show_numbers = bool(on)
        self._rebuild_overlay()

    def _rebuild_overlay(self) -> None:
        colours = getattr(self, "_colours", {})
        if not self._show_outlines:
            for c in (self._c_inc, self._c_exc, self._c_sel):
                c.setData([], [])
            for item in getattr(self, "_c_col", {}).values():
                item.setData([], [])
            for t in self._labels:
                t.setVisible(False)
            if self._background is not None:
                x, y = _poly_arrays([self._background])
                self._c_bak.setData(x, y)
            return
        inc = [r for k, r in enumerate(self._rois) if r.include and k not in colours]
        exc = [r for r in self._rois if not r.include]
        x, y = _poly_arrays(inc)
        self._c_inc.setData(x, y)
        # one polyline per colour (a handful of items, however many cells)
        groups: Dict[str, List[Roi]] = {}
        for k, r in enumerate(self._rois):
            if r.include and k in colours:
                groups.setdefault(colours[k], []).append(r)
        if not hasattr(self, "_c_col"):
            self._c_col = {}
        for col, item in list(self._c_col.items()):
            if col not in groups:
                item.setData([], [])
        for col, rs in groups.items():
            item = self._c_col.get(col)
            if item is None:
                item = pg.PlotCurveItem(pen=pg.mkPen(QColor(col), width=2.4), connect="finite")
                item.setZValue(11)
                self.vb.addItem(item)
                self._c_col[col] = item
            x, y = _poly_arrays(rs)
            item.setData(x, y)
        x, y = _poly_arrays(exc)
        self._c_exc.setData(x, y)

        sel = self._selected
        sel = [sel] if isinstance(sel, int) else list(sel or [])
        sel = [k for k in sel if 0 <= k < len(self._rois)]
        if sel:
            x, y = _poly_arrays([self._rois[k] for k in sel])
            self._c_sel.setData(x, y)
        else:
            self._c_sel.setData([], [])

        if self._background is not None:
            x, y = _poly_arrays([self._background])
            self._c_bak.setData(x, y)
        else:
            self._c_bak.setData([], [])

        # The number is the cell's ID everywhere: Cell_<n> in the trace panel and
        # the files. Text items are reused (creating them is what made scrubbing slow).
        # Numbers sit just OUTSIDE each outline (above it; below it at the top
        # edge of the image), so they never hide the cell.
        used = 0
        if self._show_numbers:
            H = self._shape[0] if self._shape else 0
            gap = 3
            for k, r in enumerate(self._rois):
                if not r.area:
                    continue
                y0, x0, y1, x1 = r.bbox
                if r.include and k in colours:
                    qc = QColor(colours[k]).lighter(115)
                else:
                    qc = QColor(*(COL_INCLUDE if r.include else COL_EXCLUDE))
                if used == len(self._labels):
                    t = pg.TextItem("", anchor=(0.5, 1.0))
                    f = t.textItem.font()
                    f.setBold(True)
                    t.setFont(f)
                    t.setZValue(20)
                    self.vb.addItem(t)
                    self._labels.append(t)
                t = self._labels[used]
                t.setText(str(k + 1), color=qc)
                above = y0 - gap > 0.04 * max(H, 1)
                t.setAnchor((0.5, 1.0) if above else (0.5, 0.0))
                t.setPos((x0 + x1) / 2.0, y0 - gap if above else y1 + gap)
                t.setVisible(True)
                used += 1
        for t in self._labels[used:]:
            t.setVisible(False)

    # ------------------------------------------------------------- modes
    def start_polygon(self) -> None:
        self._set_mode("polygon")
        self.status.emit("Click around the region; double-click or right-click to "
                         "close it, Esc to cancel.")

    def start_rect(self) -> None:
        self._set_mode("rect")
        self.status.emit("Click two opposite corners of the background box, "
                         "Esc to cancel.")

    def start_line(self) -> None:
        self._set_mode("line")
        self.status.emit("Split: click on one side of the cell, then on the other side - "
                         "the line between the clicks cuts it in two. Esc to stop.")

    def start_freehand(self) -> None:
        """Press, drag a line through an ROI, release: stroke_done(points)."""
        self._set_mode("freehand")
        self._drag = False

    def start_lasso(self) -> None:
        """V2.5: press, draw around a region, release: lasso_done(points) (the
        outline is closed between the last and the first point)."""
        self._set_mode("lasso")
        self._drag = False
        self.status.emit("Hold the left mouse button and draw around the region; release to "
                         "close it. Esc to cancel.")

    def start_polyline(self) -> None:
        """V2.5: click the points of a line; double-click, right-click or Enter
        finishes it: polyline_done(points)."""
        self._set_mode("polyline")
        self.status.emit("Click the points of the line; double-click (or right-click / Enter) "
                         "to finish it. Esc to cancel.")

    def _freehand_event(self, ev) -> bool:
        from PySide6.QtCore import QEvent
        t = ev.type()
        pos = self.glw.mapToScene(ev.position().toPoint())
        if t in (QEvent.MouseButtonPress, QEvent.MouseButtonDblClick):
            if ev.button() == Qt.RightButton:
                self._drag = False
                self._points = []
                self._c_draw.setData([], [])
                return True
            if ev.button() == Qt.LeftButton:
                self._drag = True
                self._points = [self._scene_to_image(pos)]
            return True
        if t == QEvent.MouseMove:
            if getattr(self, "_drag", False):
                self._points.append(self._scene_to_image(pos))
                pts = self._points + (self._points[:1] if self._mode == "lasso" else [])
                self._c_draw.setData([q[0] for q in pts], [q[1] for q in pts])
            return True
        if t == QEvent.MouseButtonRelease and getattr(self, "_drag", False):
            self._drag = False
            pts = list(self._points)
            self._points = []
            self._c_draw.setData([], [])
            if self._mode == "lasso":
                if len(pts) >= 3:
                    self.lasso_done.emit(pts)        # stays in lasso mode: draw again
                else:
                    self.status.emit("Hold the button down while you draw around the region.")
            elif len(pts) >= 2:
                self.stroke_done.emit(pts)           # stays in freehand mode for the next cut
            return True
        return True

    def start_circle(self) -> None:
        self._set_mode("circle")
        self.status.emit("Click the centre of the cell, then a point on its edge. "
                         "Esc to cancel.")

    def cancel_draw(self) -> None:
        if self._mode != "view":
            self._set_mode("view")
            self.status.emit("Drawing cancelled.")

    def _set_mode(self, mode: str) -> None:
        self._mode = mode
        self._points = []
        self._c_draw.setData([], [])
        drawing = mode != "view"
        self.vb.setMouseEnabled(not drawing, not drawing)
        self.setCursor(Qt.CrossCursor if drawing else Qt.ArrowCursor)

    @property
    def mode(self) -> str:
        return self._mode

    # ------------------------------------------------------------ events
    def _scene_to_image(self, pos) -> tuple[float, float]:
        pt = self.vb.mapSceneToView(pos)
        return float(pt.x()), float(pt.y())

    def _on_move(self, pos) -> None:
        if self._mode in ("view", "freehand", "lasso") or not self._points:
            return
        if not self.vb.sceneBoundingRect().contains(pos):
            return
        x, y = self._scene_to_image(pos)
        pts = self._points + [(x, y)]
        if self._mode == "polygon":
            px = [p[0] for p in pts] + [pts[0][0]]
            py = [p[1] for p in pts] + [pts[0][1]]
        elif self._mode == "line":
            (x0, y0) = self._points[0]
            px, py = [x0, x], [y0, y]
        elif self._mode == "polyline":
            px = [q[0] for q in pts]
            py = [q[1] for q in pts]
        elif self._mode == "circle":
            (cx, cy) = self._points[0]
            rad = float(np.hypot(x - cx, y - cy))
            a = np.linspace(0, 2 * np.pi, 64)
            px, py = cx + rad * np.cos(a), cy + rad * np.sin(a)
        else:
            (x0, y0) = self._points[0]
            px = [x0, x, x, x0, x0]
            py = [y0, y0, y, y, y0]
        self._c_draw.setData(px, py)

    def _on_click(self, ev) -> None:
        if not self.vb.sceneBoundingRect().contains(ev.scenePos()):
            return
        x, y = self._scene_to_image(ev.scenePos())

        if self._mode == "polygon":
            if ev.button() == Qt.RightButton or ev.double():
                self._finish_polygon()
            else:
                self._points.append((x, y))
                px = [p[0] for p in self._points]
                py = [p[1] for p in self._points]
                self._c_draw.setData(px, py)
            ev.accept()
            return

        if self._mode == "polyline":
            if ev.button() == Qt.RightButton or ev.double():
                self._finish_polyline()
            else:
                self._points.append((x, y))
                self._c_draw.setData([q[0] for q in self._points], [q[1] for q in self._points])
            ev.accept()
            return

        if self._mode == "line":
            if ev.button() == Qt.RightButton:
                self.cancel_draw()
                ev.accept()
                return
            self._points.append((x, y))
            if len(self._points) == 2:
                p0, p1 = self._points
                self._points = []
                self._c_draw.setData([], [])
                self.line_done.emit((p0, p1))     # stays in line mode for the next cut
            ev.accept()
            return

        if self._mode == "circle":
            if ev.button() == Qt.RightButton:
                self.cancel_draw()
                ev.accept()
                return
            self._points.append((x, y))
            if len(self._points) == 2:
                (cx, cy), (ex, ey) = self._points
                rad = max(2.0, float(np.hypot(ex - cx, ey - cy)))
                a = np.linspace(0, 2 * np.pi, 64, endpoint=False)
                pts = list(zip(cx + rad * np.cos(a), cy + rad * np.sin(a)))
                self._set_mode("view")
                self.polygon_done.emit(pts)
            ev.accept()
            return

        if self._mode == "rect":
            if ev.button() == Qt.RightButton:
                self.cancel_draw()
                ev.accept()
                return
            self._points.append((x, y))
            if len(self._points) == 2:
                (x0, y0), (x1, y1) = self._points
                self._set_mode("view")
                self.rect_done.emit((min(x0, x1), min(y0, y1),
                                     abs(x1 - x0), abs(y1 - y0)))
            ev.accept()
            return

        if ev.button() == Qt.RightButton:
            k = self.roi_at(x, y)
            self.context_requested.emit(x, y, -1 if k is None else int(k))
            ev.accept()
            return
        if ev.button() != Qt.LeftButton:
            return
        if not ev.double():
            self.point_clicked.emit(x, y, bool(ev.modifiers() & Qt.ShiftModifier))
        k = self.roi_at(x, y)
        if k is not None:
            # plain click = include / exclude; shift-click = only select it
            toggle = not bool(ev.modifiers() & Qt.ShiftModifier)
            self.roi_clicked.emit(k, toggle)
            ev.accept()
        elif not ev.double() and not (ev.modifiers() & Qt.ShiftModifier):
            self.empty_clicked.emit(x, y)      # "there should be a cell here"
            ev.accept()

    def _finish_polygon(self) -> None:
        pts = list(self._points)
        self._set_mode("view")
        if len(pts) >= 3:
            self.polygon_done.emit(pts)
        else:
            self.status.emit("Need at least three points - nothing added.")

    def _finish_polyline(self) -> None:
        pts = []
        for q in self._points:                     # a double-click adds its point twice
            if not pts or abs(q[0] - pts[-1][0]) + abs(q[1] - pts[-1][1]) > 0.5:
                pts.append(q)
        self._points = []
        self._c_draw.setData([], [])
        if len(pts) >= 2:
            self.polyline_done.emit(pts)           # stays in polyline mode for the next line
        else:
            self.status.emit("A line needs at least two points - click them, then double-click.")

    def keyPressEvent(self, ev) -> None:          # noqa: N802 (Qt naming)
        if ev.key() == Qt.Key_Escape:
            self.cancel_draw()
            self.escape_pressed.emit()
            ev.accept()
            return
        if ev.key() in (Qt.Key_Return, Qt.Key_Enter) and self._mode == "polygon":
            self._finish_polygon()
            ev.accept()
            return
        if ev.key() in (Qt.Key_Return, Qt.Key_Enter) and self._mode == "polyline":
            self._finish_polyline()
            ev.accept()
            return
        super().keyPressEvent(ev)

    # ------------------------------------------------------------ lookups
    def roi_at(self, x: float, y: float) -> Optional[int]:
        """Index of the smallest ROI whose mask covers (x, y), or None."""
        xi, yi = int(round(x)), int(round(y))
        best, best_area = None, None
        for k, r in enumerate(self._rois):
            y0, x0, y1, x1 = r.bbox
            if not (y0 <= yi < y1 and x0 <= xi < x1):
                continue
            hit = r.outline if r.outline is not None else r.mask
            if not hit[yi - y0, xi - x0]:
                continue
            if best_area is None or r.area < best_area:
                best, best_area = k, r.area
        return best
