"""
Small form helpers so that the settings panels stay short and consistent.

Every control carries a tooltip; the tooltip text is the documentation the user
actually reads, so it is written in full sentences.

BLOCK: add a new control type here and use it in the window that needs it.
"""
from __future__ import annotations

import sys
from typing import Callable, Iterable, Optional, Tuple

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout,
                               QFrame, QGroupBox, QHBoxLayout, QLabel, QMenu,
                               QProgressBar, QPushButton, QSpinBox, QToolButton,
                               QVBoxLayout, QWidget)

# one colour per cell, shared by the image outlines and the trace lines, so a
# trace and its cell are easy to match (bright on black, readable on white)
PALETTE = ["#3fa9ff", "#ff4b4b", "#2ecc40", "#ffa31a", "#d65cff", "#00c8c8",
           "#ff5fb0", "#b8b800", "#ff7f50", "#8c8cff"]


def cell_colour(k: int) -> str:
    """The colour of cell k (0-based) - outline and trace."""
    return PALETTE[k % len(PALETTE)]


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
    GraphPad Prism ...), on Windows and macOS. False if that failed."""
    import os
    import subprocess
    p = str(path)
    try:
        if sys.platform == "win32":
            from ..safety import plain_path
            os.startfile(plain_path(p))                    # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", p])                  # noqa: S603, S607
        else:
            subprocess.Popen(["xdg-open", p])              # noqa: S603, S607
        return True
    except OSError:
        return False


def app_icon():
    """The PeterPiper icon (the piper in a square) for windows and the taskbar."""
    from PySide6.QtGui import QIcon
    return QIcon(str(ASSETS / "PeterPiper.ico"))


class LogoLabel(QLabel):
    """The PeterPiper logo, black on a light theme and white on a dark one (it
    follows a theme change), at most `height` pixels high."""

    def __init__(self, height: int = 90, parent=None) -> None:
        super().__init__(parent)
        self._h = int(height)
        self.setAlignment(Qt.AlignCenter)
        self.setAccessibleName("PeterPiper")
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


class ProgressStrip(QWidget):
    """A progress bar plus a message line, used at the bottom of the window."""

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
        self.msg = QLabel("Ready.")
        self.msg.setProperty("muted", True)
        lay.addWidget(self.bar)
        lay.addWidget(self.msg)
        self.reset()

    def reset(self, message: str = "Ready.") -> None:
        self.bar.setValue(0)
        self.bar.setFormat("%p%")
        self.msg.setText(message)

    def update(self, fraction: float, message: str) -> None:
        self.bar.setValue(int(max(0.0, min(1.0, fraction)) * 1000))
        self.msg.setText(message)

    def busy(self, message: str) -> None:
        self.bar.setRange(0, 0)
        self.msg.setText(message)

    def unbusy(self) -> None:
        self.bar.setRange(0, 1000)


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
    busy() (work that must stay in this thread, done in steps)."""

    def __init__(self, parent: Optional[QWidget], title: str) -> None:
        super().__init__(parent, Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint)
        self.setWindowTitle("PeterPiper - working")
        self.setWindowModality(Qt.ApplicationModal)      # no clicks meanwhile
        self.setObjectName("busy")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(8)
        self.lbl_title = QLabel(title)
        f = self.lbl_title.font()
        f.setBold(True)
        self.lbl_title.setFont(f)
        self.lbl = QLabel("")
        self.lbl.setProperty("muted", True)
        self.lbl.setWordWrap(True)
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)                          # moving until a fraction is known
        self.bar.setTextVisible(False)
        self.bar.setMinimumWidth(380)
        lay.addWidget(self.lbl_title)
        lay.addWidget(self.bar)
        lay.addWidget(self.lbl)
        self.setMinimumWidth(440)
        self._shown = False

    def update_progress(self, fraction: Optional[float], text: str = "") -> None:
        if fraction is None:
            if self.bar.maximum() != 0:
                self.bar.setRange(0, 0)
        else:
            if self.bar.maximum() != 1000:
                self.bar.setRange(0, 1000)
            self.bar.setValue(int(1000 * max(0.0, min(1.0, float(fraction)))))
        if text:
            self.lbl.setText(text)

    def appear(self) -> None:
        if self._shown:
            return
        self._shown = True
        p = self.parentWidget()
        self.adjustSize()
        if p is not None and p.isVisible():
            g = p.frameGeometry()
            self.move(g.center().x() - self.width() // 2, g.center().y() - self.height() // 2)
        self.show()
        self.raise_()


def run_with_progress(parent: Optional[QWidget], title: str, fn: Callable, delay_ms: int = 350):
    """V2.9: run fn(progress) in a background thread; while it runs a BusyPanel
    says `title` (shown only if it takes longer than delay_ms). progress(fraction
    or None, text) may be called from fn. The windows keep painting but take no
    clicks. Returns fn's result; re-raises its exception. fn must not touch
    widgets."""
    import threading
    from PySide6.QtCore import QEventLoop
    from PySide6.QtWidgets import QApplication
    if QApplication.instance() is None:
        return fn(lambda *a, **k: True)
    state = {"done": False, "result": None, "error": None, "prog": None}

    def progress(fraction=None, text=""):
        state["prog"] = (fraction, text)
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
        QApplication.restoreOverrideCursor()
        panel.close()
        panel.deleteLater()
    if state["error"] is not None:
        raise state["error"]
    return state["result"]


class busy:
    """V2.9: `with busy(parent, title) as b: ... b.step(i, n, text) ...` - for
    slow work that must run in the window's own thread: a BusyPanel shows at
    once and is repainted at every step (the work itself is not interrupted)."""

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

    def step(self, i: Optional[float] = None, n: Optional[float] = None, text: str = "") -> None:
        self.panel.update_progress(None if i is None or not n else i / n, text)
        self._pump()

    def __exit__(self, *exc) -> bool:
        from PySide6.QtWidgets import QApplication
        QApplication.restoreOverrideCursor()
        self.panel.close()
        self.panel.deleteLater()
        return False
