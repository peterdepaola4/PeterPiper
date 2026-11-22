"""
Small form helpers so that the settings panels stay short and consistent.

Every control carries a tooltip; the tooltip text is the documentation the user
actually reads, so it is written in full sentences.

BLOCK: add a new control type here and use it in the window that needs it.
"""
from __future__ import annotations

import sys
from typing import Callable, Iterable, Optional, Tuple

from PySide6.QtCore import QEvent, QObject, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout,
                               QFrame, QGroupBox, QHBoxLayout, QLabel, QMenu,
                               QProgressBar, QPushButton, QSpinBox, QToolButton,
                               QVBoxLayout, QWidget)

# ---------------------------------------------------------------- cell colours
# PeterPiper 1.1: one colour per cell, shared by the outlines on the image, the
# trace lines and the swatches in the cell list, so a trace and its cell are easy
# to match. FIXED: the same in every theme / palette (nothing here reads the theme).
#
# How the six were chosen (dev_tests/test_v11_looks.py checks every point):
#  - the hue set of Okabe & Ito's colour-blind-safe palette (sky blue, vermillion,
#    blue, orange, reddish purple, bluish green - Okabe & Ito 2008; cf. Paul Tol's
#    'bright' scheme), each moved into a mid-luminance window (WCAG relative
#    luminance 0.11 - 0.28) and then fine-tuned by a search that maximised the
#    smallest CIEDE2000 distance between any two of them;
#  - mid luminance makes every colour >= 3:1 (WCAG 2 contrast) against BOTH the
#    white trace plot (PLOT_BG, white in every theme) and black (the dark image
#    behind the outlines) - and so also against bright cells;
#  - distinct for everyone: with normal vision and with protanopia, deuteranopia
#    and tritanopia simulated (Machado, Oliveira & Fernandes 2009, severity 1.0),
#    every PAIR of the six is >= CELL_MIN_DE2000 CIEDE2000 apart (measured 14.4;
#    neighbours in the list 16.8; normal vision 30.9); a difference of about 10
#    is clearly seen side by side;
#  - kept clear of the selected-trace orange and the blue mean line.
# After six cells the colours repeat with another line style (cell_pen_style):
# solid, dashed, dotted, dash-dot - 24 different looks before any repeats; the
# cells' numbers on the image tell repeated outline colours apart.
PALETTE = ["#2299CC",      # sky blue
           "#BB2200",      # vermillion red
           "#5533FF",      # blue violet
           "#AA8844",      # ochre
           "#EE3388",      # reddish purple (pink)
           "#007755"]      # bluish green
CELL_MIN_DE2000 = 12.0     # the smallest allowed CIEDE2000 distance (tested)
CELL_MIN_CONTRAST = 3.0    # vs the white plot and vs black (tested)
PLOT_BG = "#FFFFFF"        # the trace plot's background - white in every theme


def cell_colour(k: int) -> str:
    """The colour of cell k (0-based) - outline, trace and list swatch. The same
    whatever theme is in use."""
    return PALETTE[int(k) % len(PALETTE)]


_PEN_STYLES = (Qt.SolidLine, Qt.DashLine, Qt.DotLine, Qt.DashDotLine)


def cell_pen_style(k: int):
    """The line style of cell k's trace: solid for the first len(PALETTE) cells,
    then dashed, dotted, dash-dot (so cells whose colour repeats still differ)."""
    return _PEN_STYLES[(int(k) // len(PALETTE)) % len(_PEN_STYLES)]


_SWATCHES: dict = {}
SWATCH_SIZE = QSize(40, 14)           # the cell list's icon size for cell_swatch()


def cell_swatch(k: int, included: bool = True):
    """A small picture for the cell list: a square of the cell's colour and a
    short line in its line style (an excluded cell: a light grey outline only).
    The cell's name next to it keeps the normal text colour."""
    from PySide6.QtCore import QPointF, QRectF
    from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
    key = (cell_colour(k), int(cell_pen_style(k).value), bool(included))
    if key in _SWATCHES:
        return _SWATCHES[key]
    ratio = 2
    pm = QPixmap(40 * ratio, 14 * ratio)
    pm.fill(Qt.transparent)
    g = QPainter(pm)
    g.setRenderHint(QPainter.Antialiasing)
    g.scale(ratio, ratio)
    col = QColor(cell_colour(k)) if included else QColor(170, 170, 170)
    if included:
        g.setPen(QPen(QColor(0, 0, 0, 90), 0.8))
        g.setBrush(col)
    else:
        g.setPen(QPen(col, 1.2))
        g.setBrush(Qt.NoBrush)
    g.drawRoundedRect(QRectF(1, 1, 12, 12), 2.5, 2.5)
    pen = QPen(col, 2.2)
    pen.setStyle(cell_pen_style(k))
    pen.setCapStyle(Qt.FlatCap)
    g.setPen(pen)
    g.drawLine(QPointF(17, 7), QPointF(39, 7))
    g.end()
    pm.setDevicePixelRatio(ratio)
    icon = QIcon(pm)
    _SWATCHES[key] = icon
    return icon


def group(title: str) -> tuple[QGroupBox, QFormLayout]:
    box = QGroupBox(title)                 # V2.9: drawn as a card by the theme
    form = QFormLayout(box)
    form.setHorizontalSpacing(12)
    form.setVerticalSpacing(8)
    form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
    form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
    # with large text, labels move above their field instead of being cut off
    form.setRowWrapPolicy(QFormLayout.WrapLongRows)
    form.setContentsMargins(8, 6, 8, 8)
    form.setVerticalSpacing(5)
    return box, form


def spin(form: QFormLayout, label: str, value: int, lo: int, hi: int,
         tip: str = "", step: int = 1, on_change: Optional[Callable] = None) -> QSpinBox:
    w = QSpinBox()
    w.setRange(lo, hi)
    w.setSingleStep(step)
    w.setValue(int(value))
    w.setToolTip(tip)
    w.setMinimumWidth(70)
    if on_change:
        w.valueChanged.connect(on_change)
    lab = QLabel(label)
    lab.setToolTip(tip)
    form.addRow(lab, w)
    return w


def dspin(form: QFormLayout, label: str, value: float, lo: float, hi: float,
          tip: str = "", decimals: int = 2, step: float = 0.1,
          on_change: Optional[Callable] = None) -> QDoubleSpinBox:
    w = QDoubleSpinBox()
    w.setRange(lo, hi)
    w.setDecimals(decimals)
    w.setSingleStep(step)
    w.setValue(float(value))
    w.setToolTip(tip)
    w.setMinimumWidth(70)
    if on_change:
        w.valueChanged.connect(on_change)
    lab = QLabel(label)
    lab.setToolTip(tip)
    form.addRow(lab, w)
    return w


def combo(form: QFormLayout, label: str, items: Iterable[str], current: int = 0,
          tip: str = "", on_change: Optional[Callable] = None) -> QComboBox:
    w = QComboBox()
    w.addItems(list(items))
    if 0 <= current < w.count():
        w.setCurrentIndex(current)
    w.setToolTip(tip)
    if on_change:
        w.currentIndexChanged.connect(on_change)
    lab = QLabel(label)
    lab.setToolTip(tip)
    form.addRow(lab, w)
    return w


def check(form: QFormLayout, label: str, value: bool, tip: str = "",
          on_change: Optional[Callable] = None) -> QCheckBox:
    w = QCheckBox(label)
    w.setChecked(bool(value))
    w.setToolTip(tip)
    if on_change:
        w.toggled.connect(on_change)
    form.addRow(w)
    return w


def button(text: str, on_click: Callable, tip: str = "", strong: bool = False) -> QPushButton:
    b = QPushButton(text)
    b.clicked.connect(on_click)
    b.setToolTip(tip)
    if strong:                       # V2.9: the window's main action, in the accent colour
        b.setProperty("primary", True)
    return b


def row(*widgets: QWidget) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(6)
    for x in widgets:
        lay.addWidget(x)
    return w


# PeterPiper 1.0: the logo (assets/: the lockup in black and in white, the icon)
ASSETS = __import__("pathlib").Path(__file__).resolve().parents[1] / "assets"


def open_path(path) -> bool:
    """Open a file or folder with its own program (Explorer / Finder, Excel,
    GraphPad Prism ...), on Windows and macOS. False if that failed.
    4.0: platforms.open_path does it (one place for Windows and macOS)."""
    from ..platforms import open_path as _o
    return _o(path)


def reveal(path) -> bool:
    """4.0: show a file selected in its folder (Explorer / Finder)."""
    from ..platforms import reveal_in_file_manager
    return reveal_in_file_manager(path)


def app_icon():
    """The PeterPiper icon (the piper in a square) for windows and the taskbar."""
    from PySide6.QtGui import QIcon
    return QIcon(str(ASSETS / "PeterPiper.ico"))


class ClickStreak:
    """Counts clicks that follow each other closely: click() returns how many
    clicks in a row this one is, each within `gap` seconds of the one before (a
    longer pause starts counting again at 1). After `top` it starts again."""

    def __init__(self, gap: float = 1.5, top: int = 100) -> None:
        self.gap, self.top = float(gap), int(top)
        self.count = 0
        self._last: Optional[float] = None

    def click(self, now: Optional[float] = None) -> int:
        import time
        now = time.monotonic() if now is None else float(now)
        if self._last is None or now - self._last > self.gap or self.count >= self.top:
            self.count = 0
        self._last = now
        self.count += 1
        return self.count


# ------------------------------------------------------------ hidden extras
# Harmless fun (PeterPiper 1.1), for anyone reading the code: the logo counts
# clicks in a row and a few typed letters are watched for one word. The only
# effect is a line in the user's achievements.json (achievements.py) - which
# shows more themes in the theme lists, or a crown before the user's name in
# "Who is using PeterPiper?". No setting, data, measurement or number changes,
# no key is ever taken away from the window it was meant for, no network.
PALETTE_CLICKS = 20          # clicks in a row: the colour palettes
CROWN_CLICKS = 100           # clicks in a row: a crown before your name
CROWN_WORD = "peter"         # ... or this word typed (anywhere) after 20 clicks in a row
CLICK_GAP_S = 1.5            # at most this long between two clicks of a streak
_EXTRAS = {"streak20": False}          # this session: 20 clicks in a row reached
_LOGOS: list = []                      # weak references to the logos shown (for a reveal)

REVEAL_TEXT = {
    ("palettes", True): "You found the colour palettes! Choose one under Theme - it is "
                        "saved in your profile.",
    ("palettes", False): "The colour palettes are yours already - choose one under Theme.",
    ("crown", True): "A crown for you - it now sits before your name.",
    ("crown", False): "You have your crown already - it sits before your name.",
}


def found_extra(key: str, logo: Optional["LogoLabel"] = None) -> bool:
    """Unlock a hidden extra (achievements.unlock) and say so with a small note
    (under `logo`, else under the newest logo still on screen, else at the top of
    the active window). True when it is new."""
    new = True
    try:
        from .. import achievements
        new = achievements.unlock(key)
    except Exception:                                              # noqa: BLE001
        pass
    if logo is None:
        for ref in reversed(_LOGOS):
            lg = ref()
            try:
                if lg is not None and lg.isVisible():
                    logo = lg
                    break
            except RuntimeError:
                continue
    try:
        if logo is not None:
            logo.show_reveal(key, new)
        else:
            from PySide6.QtWidgets import QApplication
            win = QApplication.activeWindow()
            if win is not None:
                _Reveal(win, None, REVEAL_TEXT[(key, bool(new))])
    except RuntimeError:
        pass
    return bool(new)


class _WordWatch(QObject):
    """Watches the letters typed anywhere in the app for CROWN_WORD (it only
    looks: every key still goes where it was going). Counts a key once - when it
    reaches the focused widget (or the window, with nothing focused)."""

    def __init__(self) -> None:
        super().__init__()
        self._typed = ""

    def eventFilter(self, obj, ev) -> bool:                       # noqa: N802
        if ev.type() != QEvent.KeyPress:
            return False
        try:
            from PySide6.QtWidgets import QApplication
            if not isinstance(obj, QWidget) or ev.isAutoRepeat():
                return False
            focus = QApplication.focusWidget()
            if obj is not focus and not (focus is None and obj.isWindow()):
                return False
            ch = ev.text()
            if not ch:
                return False
            self._typed = (self._typed + ch.lower())[-len(CROWN_WORD):]
            if self._typed == CROWN_WORD:
                self._typed = ""
                if self.allowed():
                    QTimer.singleShot(0, lambda: found_extra("crown"))
        except Exception:                                          # noqa: BLE001
            pass
        return False                                   # never takes the key

    @staticmethod
    def allowed() -> bool:
        """The word counts after 20 clicks in a row on the logo (this session) or
        once the palettes were found."""
        if _EXTRAS["streak20"]:
            return True
        try:
            from .. import achievements
            return achievements.unlocked("palettes")
        except Exception:                                          # noqa: BLE001
            return False


_WATCH: list = []


def install_word_watch() -> bool:
    """Start watching for CROWN_WORD (once per app; True if it is installed).
    Done only when the word can count (see _maybe_watch): most people never get
    the small cost of an app-wide event filter."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        return False
    if _WATCH and _WATCH[0][1] is app:
        return True
    w = _WordWatch()
    app.installEventFilter(w)
    _WATCH[:] = [(w, app)]
    return True


def _maybe_watch() -> None:
    """Watch for the word only while it can still give a crown."""
    try:
        from .. import achievements
        if _WordWatch.allowed() and not achievements.unlocked("crown"):
            install_word_watch()
    except Exception:                                              # noqa: BLE001
        pass


class LogoLabel(QLabel):
    """The PeterPiper logo, black on a light theme and white on a dark one (it
    follows a theme change), at most `height` pixels high.

    Hidden extras, harmless (PeterPiper 1.1 - see 'hidden extras' above): clicking
    the logo 20 times in a row (each click within 1.5 s of the one before) reveals
    the extra colour palettes for this user (achievements.unlock("palettes");
    theme.available_names() then offers every theme); 100 in a row - or 20 and
    then typing "peter" - gives a crown before the user's name. Each stores one
    fact in the user's achievements.json; nothing at all is shown before the 20th
    click."""

    CLICKS = PALETTE_CLICKS
    GAP_S = CLICK_GAP_S
    found_palettes = Signal(bool)          # True: newly found, False: found before
    found_crown = Signal(bool)

    def __init__(self, height: int = 90, parent=None) -> None:
        super().__init__(parent)
        self._h = int(height)
        self.setAlignment(Qt.AlignCenter)
        self.setAccessibleName("PeterPiper")
        self._streak = ClickStreak(CLICK_GAP_S, CROWN_CLICKS)
        self._sparkle_left = 0                 # frames of the little sparkle still to draw
        self._sparkle_timer: Optional[QTimer] = None
        self.reveal: Optional[QFrame] = None   # the note shown when an extra is found
        import weakref
        _LOGOS[:] = [r for r in _LOGOS if r() is not None][-7:] + [weakref.ref(self)]
        _maybe_watch()
        self._load()

    def _load(self) -> None:
        from PySide6.QtGui import QPixmap
        from . import theme as TH
        dark = TH.current().dark
        pm = QPixmap(str(ASSETS / ("logo_white.png" if dark else "logo_black.png")))
        if pm.isNull():
            self.setText("PeterPiper")
            return
        ratio = max(1.0, self.devicePixelRatioF())
        pm = pm.scaledToHeight(int(self._h * ratio), Qt.SmoothTransformation)
        pm.setDevicePixelRatio(ratio)
        self.setPixmap(pm)
        self.setMinimumHeight(self._h)

    def event(self, ev) -> bool:                                 # noqa: N802
        # View > Theme: the application's style sheet / palette change
        if ev.type() in (QEvent.StyleChange, QEvent.PaletteChange,
                         QEvent.ApplicationPaletteChange):
            QTimer.singleShot(0, self._load)
        return super().event(ev)

    # ---- the hidden extra (see the class text)
    def mouseReleaseEvent(self, ev) -> None:                     # noqa: N802
        if ev.button() == Qt.LeftButton and self.rect().contains(ev.position().toPoint()):
            self.logo_clicked()
        super().mouseReleaseEvent(ev)

    def logo_clicked(self, now: Optional[float] = None) -> str:
        """One click on the logo (now: a time in seconds, for tests). Returns the
        extra this click completed ("palettes" on the 20th in a row, "crown" on
        the 100th) or ""."""
        n = self._streak.click(now)
        if n >= PALETTE_CLICKS and not _EXTRAS["streak20"]:
            _EXTRAS["streak20"] = True             # "peter" may now be typed
            _maybe_watch()
        if n == PALETTE_CLICKS:
            self.found_palettes.emit(found_extra("palettes", self))
            return "palettes"
        if n == CROWN_CLICKS:
            self.found_crown.emit(found_extra("crown", self))
            return "crown"
        return ""

    def show_reveal(self, key: str, new: bool) -> None:
        """The small note under the logo (and a little sparkle on it)."""
        text = REVEAL_TEXT.get((key, bool(new)), "")
        if self.reveal is not None:
            try:
                self.reveal.close()
            except RuntimeError:
                pass
        self.reveal = _Reveal(self.window(), self, text)
        self._sparkle_left = SPARKLE_FRAMES
        if self._sparkle_timer is None:
            self._sparkle_timer = QTimer(self)
            self._sparkle_timer.setInterval(33)
            self._sparkle_timer.timeout.connect(self._sparkle_step)
        self._sparkle_timer.start()
        self.update()

    def _sparkle_step(self) -> None:
        self._sparkle_left -= 1
        if self._sparkle_left <= 0 and self._sparkle_timer is not None:
            self._sparkle_timer.stop()
        self.update()

    def paintEvent(self, ev) -> None:                             # noqa: N802
        super().paintEvent(ev)
        if self._sparkle_left > 0:
            _paint_sparkle(self, SPARKLE_FRAMES - self._sparkle_left)


SPARKLE_FRAMES = 48                        # about 1.6 s at 30 frames a second


def _paint_sparkle(logo: QLabel, age: int) -> None:
    """A few little four-point stars twinkling over the logo (age: frames since
    the 20th click)."""
    import math
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QColor, QPainter, QPainterPath
    from . import theme as TH
    t = TH.current()
    g = QPainter(logo)
    g.setRenderHint(QPainter.Antialiasing)
    g.setPen(Qt.NoPen)
    w, h = logo.width(), logo.height()
    pm = logo.pixmap()
    pw = (pm.width() / max(1.0, pm.devicePixelRatio())) if pm is not None and not pm.isNull() \
        else w * 0.5
    x0 = (w - pw) / 2
    for i in range(9):
        cx = x0 + pw * ((i * 0.37 + 0.08) % 1.0)
        cy = h * (0.18 + 0.64 * ((i * 0.61 + 0.2) % 1.0))
        phase = (age - i * 3) / 18.0
        if not 0.0 < phase < 1.0:
            continue
        s = math.sin(math.pi * phase)
        r = 3.0 + 6.0 * s
        col = QColor(t.accent if i % 2 else t.warn)
        col.setAlphaF(max(0.0, min(1.0, s)))
        g.setBrush(col)
        path = QPainterPath()
        for j in range(8):
            rr = r if j % 2 == 0 else r * 0.28
            a = math.pi / 4 * j
            pt = QPointF(cx + rr * math.cos(a), cy + rr * math.sin(a))
            if j == 0:
                path.moveTo(pt)
            else:
                path.lineTo(pt)
        path.closeSubpath()
        g.drawPath(path)
    g.end()


class _Reveal(QFrame):
    """The small friendly note shown under the logo on the 20th click; it goes
    away by itself (or with its x)."""

    def __init__(self, win: QWidget, logo: Optional[QWidget], text: str,
                 ms: int = 12000) -> None:
        super().__init__(win)
        from . import theme as TH
        t = TH.current()
        self.setObjectName("reveal")
        self.setStyleSheet(
            f"QFrame#reveal {{ background: {t.surface2}; border: 1px solid {t.accent}; "
            f"border-radius: 12px; }} QFrame#reveal QLabel {{ background: transparent; "
            f"color: {t.text}; }}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 8, 10)
        lay.setSpacing(10)
        star = QLabel("★")                        # a star, in the accent colour
        star.setStyleSheet(f"QLabel {{ color: {t.accent}; font-size: 16pt; }}")
        lay.addWidget(star)
        self.label = QLabel(text)
        self.label.setWordWrap(True)
        lay.addWidget(self.label, 1)
        x = QToolButton()
        x.setText("✕")
        x.setAutoRaise(True)
        x.setToolTip("Close")
        x.clicked.connect(self.close)
        lay.addWidget(x)
        self._logo = logo
        win.installEventFilter(self)
        self._place()
        self.show()
        self.raise_()
        QTimer.singleShot(int(ms), self.close)

    def _place(self) -> None:
        win = self.parentWidget()
        if win is None:
            return
        w = int(min(520, max(280, win.width() - 40)))
        self.setFixedWidth(w)
        self.adjustSize()
        try:
            y = (self._logo.mapTo(win, self._logo.rect().bottomLeft()).y() + 4
                 if self._logo is not None else 8)
        except RuntimeError:
            y = 8
        self.move(max(8, (win.width() - w) // 2),
                  max(4, min(y, win.height() - self.height() - 4)))

    def eventFilter(self, obj, ev) -> bool:                       # noqa: N802
        if obj is self.parentWidget() and ev.type() == QEvent.Resize:
            self._place()
        return False


class FitLabel(QLabel):
    """A word-wrapped label that always gets the height for ALL its lines (Qt
    otherwise keeps the height it had before the text grew, hiding the end)."""

    def __init__(self, text: str = "") -> None:
        super().__init__(text)
        self.setWordWrap(True)

    def setText(self, text: str) -> None:                     # noqa: N802
        super().setText(text)
        self._fit()

    def resizeEvent(self, ev) -> None:                        # noqa: N802
        super().resizeEvent(ev)
        self._fit()

    def _fit(self) -> None:
        w = self.width() if self.width() > 60 else 300
        # heightForWidth never returns less than the minimum height: reset it first,
        # so the label can also shrink when its text gets shorter
        self.setMinimumHeight(0)
        h = self.heightForWidth(w)
        if h > 0:
            self.setMinimumHeight(h)


def wrapped_label(text: str, muted: bool = False) -> QLabel:
    lab = FitLabel(text)
    if muted:                        # V2.9: the theme's quiet text colour
        lab.setProperty("muted", True)
    return lab


def make_foldable(box: QGroupBox) -> None:
    """V2.9: a box that folds to its title (set_folded); clicking the title
    folds / opens it. Its contents move into one inner widget (same layout)."""
    lay = box.layout()
    body = QWidget()
    body.setLayout(lay)                     # takes the layout (and its widgets) over
    outer = QVBoxLayout(box)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.addWidget(body)
    box._body = body
    box._title = box.title()
    box.setProperty("folded", False)
    box.installEventFilter(_FOLD_FILTER)
    box.setToolTip("")


def set_folded(box: QGroupBox, folded: bool) -> None:
    body = getattr(box, "_body", None)
    if body is None or bool(box.property("folded")) == bool(folded):
        return
    body.setVisible(not folded)
    box.setProperty("folded", bool(folded))
    _fold_title(box)
    box.style().unpolish(box)
    box.style().polish(box)
    if not folded and callable(getattr(box, "_on_open", None)):
        box._on_open()


FOLD_NOTE_CHARS = 34          # a title cannot wrap: a longer note would widen the panel


def _fold_title(box: QGroupBox) -> None:
    folded = bool(box.property("folded"))
    note = getattr(box, "_note", "")
    short = note if len(note) <= FOLD_NOTE_CHARS else note[:FOLD_NOTE_CHARS - 1].rstrip() + "…"
    box.setTitle(("▸  " if folded else "") + box._title + (f"  -  {short}" if folded and note
                                                          else ""))
    box.setToolTip(getattr(box, "_note_tip", "") or note if folded and note else "")


def set_fold_note(box: QGroupBox, note: str, tip: str = "") -> None:
    """V3.0: a one-line summary shown after a folded box's title (shortened to
    FOLD_NOTE_CHARS; tip, or the whole note, on hover)."""
    box._note = str(note or "")
    box._note_tip = str(tip or "")
    if getattr(box, "_body", None) is not None:
        _fold_title(box)


class _FoldFilter(QObject):
    def eventFilter(self, obj, ev) -> bool:                       # noqa: N802
        if ev.type() == QEvent.MouseButtonRelease and ev.position().y() < 30:
            set_folded(obj, not bool(obj.property("folded")))
            return True
        return False


_FOLD_FILTER = _FoldFilter()


def hline() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setFrameShadow(QFrame.Sunken)
    return f


_BASE_PT = None


def base_font_pt() -> float:
    from PySide6.QtWidgets import QApplication
    global _BASE_PT
    if _BASE_PT is None:
        _BASE_PT = float(QApplication.font().pointSizeF() or 9.0)
    return _BASE_PT


def apply_font_pt(pt: float) -> float:
    """Set the whole application's text size (0 = default). Returns the size used."""
    from PySide6.QtWidgets import QApplication
    base = base_font_pt()
    pt = base if not pt else float(min(max(pt, 7.0), 28.0))
    from . import theme
    if theme._current is not None:   # V2.9: one style sheet sets every text size at once
        app = QApplication.instance()
        if abs(app.font().pointSizeF() - pt) > 0.05:
            theme.apply(app, theme.current().name, pt)
        return pt
    f = QApplication.font()
    f.setPointSizeF(pt)
    QApplication.setFont(f)
    for w in QApplication.allWidgets():          # widgets that already exist
        wf = w.font()
        wf.setPointSizeF(pt)
        w.setFont(wf)
    return pt


class FontScaler(QObject):
    """
    Scales the whole app's text with the size of a window: make the window
    bigger and everything grows with it (on top of the user's A-/A+ choice).
    `ref` is the window size at which the user's size is used as-is.
    """

    def __init__(self, window: QWidget, get_user_pt: Callable[[], float],
                 ref: Tuple[int, int]) -> None:
        super().__init__(window)
        self._w, self._get, self._ref = window, get_user_pt, ref
        self._last = 0.0
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(150)          # wait until the user stops dragging
        self._timer.timeout.connect(self.apply)
        window.installEventFilter(self)

    def eventFilter(self, obj, ev) -> bool:   # noqa: N802
        if obj is self._w and ev.type() in (QEvent.Resize, QEvent.Show):
            self._timer.start()
        return False

    def apply(self) -> None:
        w, h = self._w.width(), self._w.height()
        f = min(w / self._ref[0], h / self._ref[1])
        f = float(min(max(f, 0.85), 1.8))
        pt = (self._get() or base_font_pt()) * f
        if abs(pt - self._last) >= 0.3:
            self._last = pt
            apply_font_pt(pt)


def text_size_row(get_pt: Callable[[], float], set_pt: Callable[[float], None]) -> QWidget:
    """'Text size  [A-] [A+] [Reset]' - bigger / smaller text for the whole app."""
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addWidget(QLabel("Text size"))
    for label, step in (("A-", -1.0), ("A+", 1.0), ("Reset", 0.0)):
        b = QPushButton(label)
        b.setToolTip("Make all text smaller / larger. Remembered for next time.")
        b.clicked.connect(lambda _=False, st=step: set_pt(
            0.0 if st == 0 else (get_pt() or base_font_pt()) + st))
        lay.addWidget(b)
    lay.addStretch(1)
    return w


class _StayOpenMenu(QMenu):
    """A tick-list that stays open while you tick several items."""

    def mouseReleaseEvent(self, e):                      # noqa: N802
        a = self.activeAction()
        if a is not None and a.isEnabled() and a.isCheckable():
            a.setChecked(not a.isChecked())
            return
        super().mouseReleaseEvent(e)


class MultiPick(QToolButton):
    """
    A button that opens a tick-list: pick one or several items. The text
    shows what is picked; `changed` fires with the '; '-joined selection.
    An item named 'any channel' is exclusive (ticking it clears the others).
    """

    changed = Signal(str)

    def __init__(self, items: Iterable[str] = (), selected: str = "") -> None:
        super().__init__()
        self.setPopupMode(QToolButton.InstantPopup)
        self.setMinimumWidth(200)
        self.setSizePolicy(self.sizePolicy().horizontalPolicy(),
                           self.sizePolicy().verticalPolicy())
        self._menu = _StayOpenMenu(self)
        self.setMenu(self._menu)
        self._actions = []
        self.set_items(items, selected)

    def set_items(self, items: Iterable[str], selected: str = "") -> None:
        self._menu.clear()
        self._actions = []
        want = {x.strip() for x in str(selected).split(";") if x.strip()}
        for it in items:
            a = QAction(it, self._menu)
            a.setCheckable(True)
            a.setChecked(it in want)
            a.toggled.connect(lambda on, a=a: self._toggled(a, on))
            self._menu.addAction(a)
            self._actions.append(a)
        if not any(a.isChecked() for a in self._actions) and self._actions:
            self._actions[0].setChecked(True)
        self._update_text()

    def _toggled(self, act, on: bool) -> None:
        for a in self._actions:
            a.blockSignals(True)
        if on and act.text() == "any channel":
            for a in self._actions:
                a.setChecked(a is act)
        elif on:
            for a in self._actions:
                if a.text() == "any channel":
                    a.setChecked(False)
        if not any(a.isChecked() for a in self._actions):
            act.setChecked(True)                    # never empty
        for a in self._actions:
            a.blockSignals(False)
        self._update_text()
        self.changed.emit(self.text_value())

    def text_value(self) -> str:
        return "; ".join(a.text() for a in self._actions if a.isChecked())

    def _update_text(self) -> None:
        v = self.text_value()
        self.setText((v if len(v) < 40 else v[:37] + "...") + "  ▾")
        self.setToolTip(v.replace("; ", "\n"))


# ---------------------------------------------------------------- 1.2 progress helpers
# Every loading bar (the 'working' window, the strip under the image) shows: the
# percent when a fraction is known, the time left (estimated from the time so far
# and the fraction, smoothed), or the time so far when no fraction is known, and a
# detail line naming what is being looked at (a file, a folder, "file 12 of 80").
#
# Progress callbacks keep their two-argument form progress(fraction, text). The
# richer forms, understood everywhere (BusyPanel.update_progress, the progress
# function run_with_progress hands to fn, busy.step, ProgressStrip.update,
# workers.Job.progress):
#   progress(fraction, "Reading your runs", detail="run 3 of 12 - D:/x/a.npz")
#   progress(fraction, "Reading your runs\nrun 3 of 12 - D:/x/a.npz")   (core code:
#       the part after the first line break is the detail - no Qt import needed)
# fraction None (or below 0) = not known: a moving bar and "12 s so far".
from PySide6.QtWidgets import QSizePolicy                       # noqa: E402

DETAIL_SEP = "\n"


def place_name(path) -> str:
    """A file's or folder's name for a title - never empty: a drive root (D:\\)
    or a share root has no name, so the whole path is used then."""
    from pathlib import Path
    s = str(path or "").strip()
    if not s:
        return "(no folder)"
    name = Path(s).name
    return name if name.strip() else s


def split_progress(text, detail=None):
    """(headline, detail) from a progress text: the detail is `detail` if given,
    else the part after the first line break of `text` (None when neither)."""
    text = "" if text is None else str(text)
    if detail is None and DETAIL_SEP in text:
        text, detail = text.split(DETAIL_SEP, 1)
    return text.strip(), (None if detail is None else " ".join(str(detail).split()))


def count_detail(i, n, what: str = "file", name="") -> str:
    """'file 3 of 12 - name' (i 1-based); 'file 3 - name' when n is not known."""
    head = f"{what} {int(i)} of {int(n)}" if n else f"{what} {int(i)}"
    return f"{head} - {name}" if str(name or "") else head


def fmt_duration(s: float) -> str:
    """12 s, 1 min 20 s, 1 h 5 min."""
    s = max(0, int(round(float(s))))
    if s < 60:
        return f"{s} s"
    if s < 3600:
        m, r = divmod(s, 60)
        return f"{m} min {r} s" if r else f"{m} min"
    h, r = divmod(s, 3600)
    m = r // 60
    return f"{h} h {m} min" if m else f"{h} h"


def _round_left(s: float) -> float:
    """Rounded so the shown time left does not flicker: whole seconds under 10 s,
    5 s under a minute, 10 s under 10 min, whole minutes above."""
    import math
    if s < 10:
        return math.ceil(s)
    for limit, step in ((60, 5), (600, 10), (3600, 60)):
        if s < limit:
            return step * round(s / step)
    return 300 * round(s / 300)


class TimeLeft:
    """Time-left estimate from the elapsed time and the fraction done (no Qt).
    feed(fraction or None) at every progress report; text() says "about 1 min 20 s
    left", "estimating time left..." (too little progress yet), "almost done", or
    "12 s so far" when no fraction is known. The estimate is smoothed (its error
    is reduced with a ~3 s time constant) and counts down between reports, so it
    does not jump. A fraction going back (a new part of the work) restarts the
    estimate; the time so far keeps counting."""

    WARMUP_S = 1.5        # seconds of progress before the first estimate
    WARMUP_F = 0.02       # ... and at least this much of the work
    TAU_S = 3.0           # smoothing time constant

    def __init__(self, clock: Optional[Callable[[], float]] = None) -> None:
        import time
        self._clock = clock or time.monotonic
        self.restart()

    def restart(self) -> None:
        self.t_start = self._clock()
        self._base = None                 # (time, fraction) the rate is measured from
        self._est = None                  # smoothed seconds left at self._t_est
        self._t_est = 0.0
        self._f: Optional[float] = None
        self.known = False

    def feed(self, fraction) -> None:
        import math
        now = self._clock()
        if fraction is None or float(fraction) < 0:
            self.known = False
            return
        f = max(0.0, min(1.0, float(fraction)))
        self.known = True
        if self._base is None or (self._f is not None and f < self._f - 0.01):
            first = self._base is None
            self._base = (self.t_start, 0.0) if first and f <= 0.05 else (now, f)
            self._est = None
        self._f = f
        t0, f0 = self._base
        dt, df = now - t0, f - f0
        if dt < self.WARMUP_S or df < self.WARMUP_F:
            return
        raw = dt * (1.0 - f) / df
        if self._est is None:
            self._est, self._t_est = raw, now
            return
        pred = max(0.0, self._est - (now - self._t_est))
        a = 1.0 - math.exp(-max(0.0, now - self._t_est) / self.TAU_S)
        self._est, self._t_est = pred + a * (raw - pred), now

    def elapsed(self) -> float:
        return max(0.0, self._clock() - self.t_start)

    def seconds_left(self) -> Optional[float]:
        if not self.known or self._est is None:
            return None
        return max(0.0, self._est - (self._clock() - self._t_est))

    def text(self) -> str:
        if not self.known:
            e = self.elapsed()
            return f"{fmt_duration(e)} so far" if e >= 1.0 else ""
        if self._f is not None and self._f >= 0.999:
            return "almost done"
        left = self.seconds_left()
        if left is None:
            return "estimating time left..."
        if left < 2:
            return "almost done"
        return f"about {fmt_duration(_round_left(left))} left"


class ElidedLabel(QLabel):
    """A one-line label that never widens its window: text too long for the space
    is shortened with '...' (in the middle by default, so a path keeps its drive
    and its file name); the whole text is then in the tooltip. text() is the whole
    text; shown_text() what is drawn."""

    def __init__(self, text: str = "", mode=Qt.ElideMiddle,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._mode = mode
        self.setTextFormat(Qt.PlainText)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.setText(text)

    def setText(self, text) -> None:                                # noqa: N802
        super().setText(" ".join(str(text or "").split()))
        self._tip()

    def shown_text(self) -> str:
        w = max(0, self.contentsRect().width())
        return self.fontMetrics().elidedText(self.text(), self._mode, w)

    def is_elided(self) -> bool:
        return bool(self.text()) and self.shown_text() != self.text()

    def _tip(self) -> None:
        self.setToolTip(self.text() if self.is_elided() else "")

    def sizeHint(self) -> QSize:                                    # noqa: N802
        h = super().sizeHint().height()
        return QSize(min(1200, self.fontMetrics().horizontalAdvance(self.text()) + 4), h)

    def minimumSizeHint(self) -> QSize:                             # noqa: N802
        return QSize(16, super().minimumSizeHint().height())

    def resizeEvent(self, ev) -> None:                              # noqa: N802
        super().resizeEvent(ev)
        self._tip()

    def paintEvent(self, ev) -> None:                               # noqa: N802
        from PySide6.QtGui import QPainter
        p = QPainter(self)
        self.style().drawItemText(p, self.contentsRect(), int(self.alignment()),
                                  self.palette(), self.isEnabled(), self.shown_text(),
                                  self.foregroundRole())
        p.end()


class ProgressStrip(QWidget):
    """A progress bar plus a message line, used at the bottom of the window.
    1.2: the line also shows a detail (what is being worked on, shortened in the
    middle when long) and the time left / time so far; the bar shows the percent
    when a fraction is known and moves when it is not.
      update(fraction, message, detail=None)  fraction None or < 0 = not known;
          message may carry the detail after a line break ("Tracking\\nframe 3 of 9")
      busy(message, detail=None)  a moving bar;  unbusy()  back to a percent bar
      reset(message)  ready for the next job (time and detail cleared)."""

    def __init__(self) -> None:
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setValue(0)
        self.bar.setTextVisible(True)
        self.bar.setFormat("%p%")
        self.bar.setMinimumHeight(22)
        self.msg = ElidedLabel("Ready.", Qt.ElideRight)
        self.msg.setProperty("muted", True)
        self.detail = ElidedLabel("", Qt.ElideMiddle)
        self.detail.setProperty("muted", True)
        self.lbl_time = QLabel("")
        self.lbl_time.setProperty("muted", True)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(14)
        row.addWidget(self.msg, 1)
        row.addWidget(self.lbl_time)
        lay.addWidget(self.bar)
        lay.addLayout(row)
        lay.addWidget(self.detail)             # its own line: long paths keep their ends
        self.eta = TimeLeft()
        self._tick = QTimer(self)
        self._tick.setInterval(500)
        self._tick.timeout.connect(self._show_time)
        self.reset()

    def reset(self, message: str = "Ready.") -> None:
        self._tick.stop()
        if self.bar.maximum() != 1000:
            self.bar.setRange(0, 1000)
        self.bar.setValue(0)
        self.bar.setFormat("%p%")
        self.msg.setText(message)
        self.detail.setText("")
        self.lbl_time.setText("")
        self.eta.restart()

    def update(self, fraction: Optional[float], message: str = "",
               detail: Optional[str] = None) -> None:
        if fraction is None or float(fraction) < 0:
            if self.bar.maximum() != 0:
                self.bar.setRange(0, 0)
        else:
            if self.bar.maximum() != 1000:
                self.bar.setRange(0, 1000)
            self.bar.setValue(int(max(0.0, min(1.0, float(fraction))) * 1000))
        head, det = split_progress(message, detail)
        if head:
            self.msg.setText(head)
            self.detail.setText(det or "")
        elif det is not None:
            self.detail.setText(det)
        self.eta.feed(fraction)
        self._show_time()
        if not self._tick.isActive():
            self._tick.start()

    def busy(self, message: str, detail: Optional[str] = None) -> None:
        self.update(None, message, detail)

    def unbusy(self) -> None:
        self.bar.setRange(0, 1000)

    def finish(self, message: str) -> None:
        """A full bar, `message` and how long it took (the clock stops)."""
        self._tick.stop()
        took = self.eta.elapsed()
        self.update(1.0, message, "")
        self._tick.stop()
        self.lbl_time.setText(f"took {fmt_duration(took)}" if took >= 1 else "")

    def _show_time(self) -> None:
        self.lbl_time.setText(self.eta.text())


class Toast(QFrame):
    """V2.9 quiet notification: a banner at the bottom of a window that fades
    away by itself (stays while the mouse is on it) instead of an OK box. The
    last ones are in parent._toasts as (title, text) - and in the status line."""

    def __init__(self, parent: QWidget, title: str, text: str,
                 action: Optional[Tuple[str, Callable]] = None, ms: int = 7000) -> None:
        super().__init__(parent)
        from PySide6.QtCore import QPropertyAnimation
        from PySide6.QtWidgets import QGraphicsOpacityEffect
        self.setObjectName("toast")
        from . import theme as TH
        t = TH.current() if TH._current is not None else None
        if t is not None:
            self.setStyleSheet(
                f"QFrame#toast {{ background: {t.surface2}; border: 1px solid {t.border}; "
                f"border-left: 4px solid {t.ok}; border-radius: 10px; }}"
                f"QFrame#toast QLabel {{ background: transparent; }}")
        else:
            self.setFrameShape(QFrame.StyledPanel)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 8, 8, 8)
        lay.setSpacing(10)
        import html
        lab = QLabel(f"<b>{html.escape(title)}</b>&nbsp;&nbsp;{html.escape(text)}")
        lab.setTextFormat(Qt.RichText)
        lab.setWordWrap(True)
        lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(lab, 1)
        self.btn_action = None
        if action is not None:
            self.btn_action = QPushButton(action[0])
            self.btn_action.clicked.connect(lambda: (action[1](), self._fade()))
            lay.addWidget(self.btn_action)
        x = QToolButton()
        x.setText("✕")
        x.setAutoRaise(True)
        x.setToolTip("Close")
        x.clicked.connect(self._fade)
        lay.addWidget(x)
        self._eff = QGraphicsOpacityEffect(self)
        self._eff.setOpacity(0.0)
        self.setGraphicsEffect(self._eff)
        self._anim = QPropertyAnimation(self._eff, b"opacity", self)
        self._anim.setDuration(220)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._maybe_fade)
        log = getattr(parent, "_toasts", None)
        if log is None:
            log = []
            try:
                parent._toasts = log
            except Exception:                                      # noqa: BLE001
                pass
        log.append((title, text))
        old = getattr(parent, "_toast_now", None)
        if old is not None:
            try:
                old.close()
            except RuntimeError:
                pass
        try:
            parent._toast_now = self
        except Exception:                                          # noqa: BLE001
            pass
        parent.installEventFilter(self)
        self._place()
        self.show()
        self.raise_()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()
        self._timer.start(int(ms))

    def _place(self) -> None:
        p = self.parentWidget()
        if p is None:
            return
        w = int(min(720, max(320, p.width() * 0.45)))
        self.setFixedWidth(w)
        self.adjustSize()
        top = 8
        mb = getattr(p, "menuBar", None)                # under the menu bar
        if callable(mb):
            try:
                top += mb().height()
            except Exception:                                      # noqa: BLE001
                pass
        self.move(16, top)                          # top left: over the image, not the steps

    def eventFilter(self, obj, ev) -> bool:                       # noqa: N802
        if obj is self.parentWidget() and ev.type() == QEvent.Resize:
            self._place()
        return False

    def _maybe_fade(self) -> None:
        if self.underMouse():
            self._timer.start(1500)
            return
        self._fade()

    def _fade(self) -> None:
        self._timer.stop()
        self._anim.stop()
        self._anim.setStartValue(self._eff.opacity())
        self._anim.setEndValue(0.0)
        try:
            self._anim.finished.disconnect()
        except (RuntimeError, TypeError):
            pass
        self._anim.finished.connect(self.close)
        self._anim.start()


# ---------------------------------------------------------------- V2.9 loading bars
class BusyPanel(QWidget):
    """A small window with what is happening and a progress bar, shown while
    something slow runs, so the program never looks frozen. Moving (busy) bar
    until a fraction is known. Use run_with_progress (work in the background) or
    busy() (work that must stay in this thread, done in steps).
    1.2: the bar shows the percent when a fraction is known; under it the time
    left (or the time so far), what is happening, and a detail line naming the
    file / folder being looked at (shortened in the middle, never widening the
    window). The title is never empty and is shortened in the middle too.
    update_progress(fraction or None, text="", detail=None): the detail may also
    come after a line break in text; a new text without a detail clears it."""

    WIDTH = 560

    def __init__(self, parent: Optional[QWidget], title: str) -> None:
        super().__init__(parent, Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint)
        self.setWindowTitle("PeterPiper - working")
        self.setWindowModality(Qt.ApplicationModal)      # no clicks meanwhile
        self.setObjectName("busy")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(6)
        title = " ".join(str(title or "").split()) or "Working..."
        self.lbl_title = ElidedLabel(title, Qt.ElideMiddle)
        f = self.lbl_title.font()
        f.setBold(True)
        self.lbl_title.setFont(f)
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)                          # moving until a fraction is known
        self.bar.setTextVisible(False)
        self.bar.setFormat("%p%")
        self.bar.setMinimumWidth(300)
        self.lbl_time = QLabel("")
        self.lbl_time.setProperty("muted", True)
        self.lbl = ElidedLabel("", Qt.ElideRight)        # what is happening
        self.lbl_detail = ElidedLabel("", Qt.ElideMiddle)  # the file / folder / count
        self.lbl_detail.setProperty("muted", True)
        lay.addWidget(self.lbl_title)
        lay.addWidget(self.bar)
        lay.addWidget(self.lbl_time)
        lay.addWidget(self.lbl)
        lay.addWidget(self.lbl_detail)
        self.setFixedWidth(self._width(parent))
        self.eta = TimeLeft()
        self._tick = QTimer(self)
        self._tick.setInterval(500)
        self._tick.timeout.connect(self._show_time)
        self._shown = False

    def _width(self, parent) -> int:
        """WIDTH, but never wider than the screen."""
        from PySide6.QtGui import QGuiApplication
        scr = None
        try:
            scr = parent.screen() if parent is not None else None
        except Exception:                                          # noqa: BLE001
            scr = None
        scr = scr or QGuiApplication.primaryScreen()
        avail = scr.availableGeometry().width() if scr is not None else self.WIDTH + 40
        return int(max(260, min(self.WIDTH, avail - 40)))

    def update_progress(self, fraction: Optional[float], text: str = "",
                        detail: Optional[str] = None) -> None:
        if fraction is None or float(fraction) < 0:
            if self.bar.maximum() != 0:
                self.bar.setRange(0, 0)
                self.bar.setTextVisible(False)
        else:
            if self.bar.maximum() != 1000:
                self.bar.setRange(0, 1000)
                self.bar.setTextVisible(True)
            self.bar.setValue(int(1000 * max(0.0, min(1.0, float(fraction)))))
        head, det = split_progress(text, detail)
        if head:
            self.lbl.setText(head)
            self.lbl_detail.setText(det or "")
        elif det is not None:
            self.lbl_detail.setText(det)
        self.eta.feed(fraction)
        self._show_time()

    def _show_time(self) -> None:
        self.lbl_time.setText(self.eta.text())

    def appear(self) -> None:
        if self._shown:
            return
        self._shown = True
        p = self.parentWidget()
        self.adjustSize()
        if p is not None and p.isVisible():
            g = p.frameGeometry()
            self.move(g.center().x() - self.width() // 2, g.center().y() - self.height() // 2)
        self._show_time()
        self._tick.start()
        self.show()
        self.raise_()

    def closeEvent(self, ev) -> None:                               # noqa: N802
        self._tick.stop()
        super().closeEvent(ev)


def run_with_progress(parent: Optional[QWidget], title: str, fn: Callable, delay_ms: int = 350):
    """V2.9: run fn(progress) in a background thread; while it runs a BusyPanel
    says `title` (shown only if it takes longer than delay_ms). progress(fraction
    or None, text) may be called from fn. The windows keep painting but take no
    clicks. Returns fn's result; re-raises its exception. fn must not touch
    widgets.
    1.2: progress(fraction, text, detail=None) - the detail (the file / folder
    being looked at, 'file 3 of 12 - name') shows on its own line; it may also
    follow a line break in text. A call with only a fraction keeps the text.
    Name folders in titles with place_name(folder) (never empty for D:\\)."""
    import threading
    from PySide6.QtCore import QEventLoop
    from PySide6.QtWidgets import QApplication
    if QApplication.instance() is None:
        return fn(lambda *a, **k: True)
    state = {"done": False, "result": None, "error": None, "prog": None}

    def progress(fraction=None, text="", detail=None):
        old = state["prog"]                 # not shown yet: keep its text
        if old is not None and not text and detail is None:
            text, detail = old[1], old[2]
        state["prog"] = (fraction, text, detail)
        return True

    def work():
        try:
            state["result"] = fn(progress)
        except BaseException as exc:                               # noqa: BLE001
            state["error"] = exc
        finally:
            state["done"] = True

    panel = BusyPanel(parent, title)
    loop = QEventLoop()
    t0 = QTimer()
    t0.setInterval(40)

    def poll():
        if state["prog"] is not None:
            panel.update_progress(*state["prog"])
            state["prog"] = None
        if state["done"]:
            t0.stop()
            loop.quit()
    t0.timeout.connect(poll)
    QTimer.singleShot(int(delay_ms), lambda: (not state["done"]) and panel.appear())
    th = threading.Thread(target=work, daemon=True)
    QApplication.setOverrideCursor(Qt.BusyCursor)
    try:
        th.start()
        t0.start()
        if not state["done"]:                       # clicks wait until it is done
            loop.exec(QEventLoop.ExcludeUserInputEvents)
        th.join()
    finally:
        t0.stop()                                   # also when the work ended before the first poll
        QApplication.restoreOverrideCursor()
        panel.close()
        panel.deleteLater()
    if state["error"] is not None:
        raise state["error"]
    return state["result"]


class busy:
    """V2.9: `with busy(parent, title) as b: ... b.step(i, n, text) ...` - for
    slow work that must run in the window's own thread: a BusyPanel shows at
    once and is repainted at every step (the work itself is not interrupted).
    1.2: b.step(i, n, text, detail=None) - i of n done (a fraction when n is
    known), the detail names what is being worked on (or follows a line break
    in text)."""

    def __init__(self, parent: Optional[QWidget], title: str) -> None:
        self.parent, self.title = parent, title

    def __enter__(self) -> "busy":
        from PySide6.QtWidgets import QApplication
        self.panel = BusyPanel(self.parent, self.title)
        self.panel.appear()
        QApplication.setOverrideCursor(Qt.BusyCursor)
        self._pump()
        return self

    def _pump(self) -> None:
        from PySide6.QtCore import QEventLoop
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents(QEventLoop.ExcludeUserInputEvents)

    def step(self, i: Optional[float] = None, n: Optional[float] = None, text: str = "",
             detail: Optional[str] = None) -> None:
        self.panel.update_progress(None if i is None or not n else i / n, text, detail)
        self._pump()

    def __exit__(self, *exc) -> bool:
        from PySide6.QtWidgets import QApplication
        QApplication.restoreOverrideCursor()
        self.panel.close()
        self.panel.deleteLater()
        return False


# ---------------------------------------------------------------- 4.0: chips
# A small rounded "chip": a coloured dot + short text (e.g. a channel and its
# mean, "GFP 212"). The dot / border carry the colour; the text keeps the
# theme's own text colour, so it is readable in every theme.
_CHANNEL_HUES = (("dapi", "#4C7DFF"), ("hoechst", "#4C7DFF"), ("bfp", "#4C7DFF"),
                 ("cfp", "#2FB8D8"), ("gfp", "#2EB84F"), ("fitc", "#2EB84F"),
                 ("488", "#2EB84F"), ("yfp", "#C9B400"), ("venus", "#C9B400"),
                 ("mcherry", "#E5483F"), ("rfp", "#E5483F"), ("tritc", "#E5483F"),
                 ("cy3", "#E5683F"), ("561", "#E5483F"), ("tomato", "#E5483F"),
                 ("cy5", "#C24CC2"), ("647", "#C24CC2"), ("far", "#C24CC2"),
                 ("cy7", "#8A5CD6"))
_CHANNEL_OTHER = ("#8C8C8C", "#2299CC", "#AA8844", "#EE3388")


def channel_colour(name: str, index: int = 0) -> str:
    """A recognisable colour for a channel name (DAPI blue, GFP green, mCherry
    red, Cy5 magenta ...); unknown names get a neutral colour by position.
    Display only (chips); the image itself is shown in grey / magenta-green."""
    low = str(name or "").lower()
    for key, col in _CHANNEL_HUES:
        if key in low:
            return col
    return _CHANNEL_OTHER[int(index) % len(_CHANNEL_OTHER)]


class Chip(QWidget):
    """A rounded chip: coloured dot + text in the theme's text colour."""

    def __init__(self, text: str = "", colour: str = "#888888", tip: str = "",
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._text, self._colour = str(text), str(colour)
        if tip:
            self.setToolTip(tip)
        from PySide6.QtWidgets import QSizePolicy
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def set(self, text: str, colour: Optional[str] = None, tip: Optional[str] = None) -> None:
        self._text = str(text)
        if colour:
            self._colour = str(colour)
        if tip is not None:
            self.setToolTip(tip)
        self.updateGeometry()
        self.update()

    def text(self) -> str:
        return self._text

    def colour(self) -> str:
        return self._colour

    def sizeHint(self) -> QSize:                                    # noqa: N802
        fm = self.fontMetrics()
        h = fm.height() + 6
        return QSize(int(fm.horizontalAdvance(self._text) + h + 10), int(h))

    def minimumSizeHint(self) -> QSize:                             # noqa: N802
        return self.sizeHint()

    def paintEvent(self, _ev) -> None:                              # noqa: N802
        from PySide6.QtCore import QPointF, QRectF
        from PySide6.QtGui import QColor, QPainter, QPen
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pal = self.palette()
        col = QColor(self._colour)
        r = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        fill = QColor(col)
        fill.setAlpha(38)
        p.setPen(QPen(col, 1.2))
        p.setBrush(fill)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d = r.height() * 0.42
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawEllipse(QPointF(r.left() + r.height() / 2, r.center().y()), d / 2, d / 2)
        p.setPen(pal.color(pal.ColorRole.WindowText))
        p.drawText(QRectF(r.left() + r.height() - 1, r.top(), r.width() - r.height(), r.height()),
                   Qt.AlignVCenter | Qt.AlignLeft, self._text)
        p.end()


def chip_row(items: Iterable[Tuple[str, str, str]]) -> QWidget:
    """A row of chips from (text, colour, tooltip) items (wraps nothing: keep it short)."""
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(4)
    for text, colour, tip in items:
        lay.addWidget(Chip(text, colour, tip))
    lay.addStretch(1)
    return w
