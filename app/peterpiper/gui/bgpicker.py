"""
PeterPiper 4.0: "Step 1: pick the background" - the first thing on the Draw page.

The window proposes a few empty, dark places (bgpropose.propose); they show on
the image as green squares 'BG 1'..'BG n'. This panel lets the user browse them
(slider or < >), see each one's mean per channel as coloured chips with a short
reason, and press '+ Use this background' (or the '+' on the image). 'Draw my
own' switches the window's lasso on instead; a region drawn by hand can be
shown here too (set_own) and used the same way.

    BgPicker()
      set_candidates(cands, channels=None, um_per_px=None)   bgpropose.Candidate list
      set_current(i) / current()                             0-based (no signal)
      set_own(cand)                                          the user's own region
      set_chosen(text)                                       'Background: BG 2' (or '' = none)
      show_all() / set_show_all(on)
    signals
      candidate_changed(int)     the user browsed to candidate i
      accepted(object)           int (candidate index) or Roi (the user's own region)
      draw_own()                 'Draw my own' (the window turns the lasso on)
      show_all_changed(bool)
"""
from __future__ import annotations

from typing import List, Optional, Sequence

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QPushButton, QSlider, QToolButton, QVBoxLayout, QWidget)

from . import widgets as W
from .tips import help_button, tip

WHY_TEXT = ("Every number PeterPiper gives is measured against the background: the light "
            "of the dish and medium that is there even where there is no cell. A cell "
            "showing <b>5.2x</b> is 5.2 times as bright as this background in that channel; "
            "<b>1.0x</b> means 'no brighter than the background'.<br><br>"
            "So pick a place that is dark, even and has no cells or bright specks in any "
            "channel. Pick it first: the cells you then draw show their 'N x background' "
            "straight away.")
WHY_PIC = "view_bg_why"


def _counts(v: float) -> str:
    if v is None or not np.isfinite(v):
        return "-"
    return f"{v:,.0f}" if abs(v) >= 100 else f"{v:.1f}"


class BgPicker(QWidget):
    candidate_changed = Signal(int)
    accepted = Signal(object)            # int (candidate index) or Roi (own region)
    draw_own = Signal()
    show_all_changed = Signal(bool)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._cands: list = []
        self._own = None
        self._channels: List[str] = []
        self._um = 1.0
        self._cur = 0

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(5)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        self.lbl_title = QLabel("Step 1: pick the background")
        self.lbl_title.setProperty("role", "title")
        head.addWidget(self.lbl_title)
        head.addStretch(1)
        self.btn_help = help_button(WHY_TEXT, "Why the background matters", WHY_PIC)
        head.addWidget(self.btn_help)
        lay.addLayout(head)
        tip(self.lbl_title, WHY_TEXT, "Why the background matters", WHY_PIC)

        self.lbl_hint = W.wrapped_label("Green squares on the image are empty, dark places. "
                                        "Browse them, then press + to use one.", muted=True)
        lay.addWidget(self.lbl_hint)

        # browse row:  <  slider  >  '2 of 6'
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        self.btn_prev = QToolButton()
        self.btn_prev.setText("<")
        self.btn_prev.setAutoRepeat(False)
        self.btn_prev.clicked.connect(lambda: self._browse(self._cur - 1))
        tip(self.btn_prev, "The previous proposed place.", "Previous")
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(1, 1)
        self.slider.setPageStep(1)
        self.slider.valueChanged.connect(lambda v: self._browse(int(v) - 1))
        tip(self.slider, "Browse the proposed background places, best first. The image "
                         "zooms to the one you pick; its numbers show below.",
            "Proposed places", WHY_PIC)
        self.btn_next = QToolButton()
        self.btn_next.setText(">")
        self.btn_next.clicked.connect(lambda: self._browse(self._cur + 1))
        tip(self.btn_next, "The next proposed place.", "Next")
        self.lbl_count = QLabel("")
        self.lbl_count.setProperty("muted", True)
        self.lbl_count.setMinimumWidth(48)
        for w_ in (self.btn_prev, self.slider, self.btn_next, self.lbl_count):
            row.addWidget(w_, 1 if w_ is self.slider else 0)
        lay.addLayout(row)

        # the card of the current candidate
        self.card = QFrame()
        self.card.setObjectName("bgCard")
        cl = QVBoxLayout(self.card)
        cl.setContentsMargins(8, 6, 8, 6)
        cl.setSpacing(3)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        self.lbl_name = QLabel("")
        self.lbl_name.setStyleSheet("font-weight: 700;")
        self.lbl_size = QLabel("")
        self.lbl_size.setProperty("muted", True)
        top.addWidget(self.lbl_name)
        top.addStretch(1)
        top.addWidget(self.lbl_size)
        cl.addLayout(top)
        self.lbl_reason = W.wrapped_label("", muted=True)
        cl.addWidget(self.lbl_reason)
        self.chips_box = QWidget()
        self.chips_box.setObjectName("bgChips")
        self.chips_box.setStyleSheet("QWidget#bgChips { background: transparent; }")
        self.chips_lay = QGridLayout(self.chips_box)       # 3 a row at most: never too wide
        self.chips_lay.setContentsMargins(0, 0, 0, 0)
        self.chips_lay.setHorizontalSpacing(4)
        self.chips_lay.setVerticalSpacing(3)
        self.chips: List[W.Chip] = []
        cl.addWidget(self.chips_box)
        tip(self.card, "The mean brightness of this place in each channel (raw counts, at "
                       "the timepoint shown). Lower and more even is better.",
            "This place")
        lay.addWidget(self.card)

        # actions
        act = QHBoxLayout()
        act.setContentsMargins(0, 0, 0, 0)
        self.btn_use = QPushButton("+ Use this background")
        self.btn_use.setProperty("primary", True)
        self.btn_use.clicked.connect(self._use)
        tip(self.btn_use, "Use this place as the background region. Every cell's numbers are "
                          "measured against it. You can change it later.",
            "Use this background", WHY_PIC)
        self.btn_draw = QPushButton("Draw my own")
        self.btn_draw.clicked.connect(self.draw_own.emit)
        tip(self.btn_draw, "Draw the background region yourself: hold the left mouse button "
                           "and draw around an empty place on the image.", "Draw my own")
        act.addWidget(self.btn_use, 1)
        act.addWidget(self.btn_draw)
        lay.addLayout(act)

        self.chk_all = QCheckBox("Show all")
        self.chk_all.setChecked(True)
        self.chk_all.toggled.connect(self.show_all_changed.emit)
        tip(self.chk_all, "On: every proposed place is outlined on the image. Off: only the "
                          "one picked here.", "Show all")
        self.lbl_chosen = QLabel("")
        self.lbl_chosen.setProperty("role", "ok")
        self.lbl_chosen.setVisible(False)
        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.addWidget(self.chk_all)
        bottom.addStretch(1)
        bottom.addWidget(self.lbl_chosen)
        lay.addLayout(bottom)
        self.bottom_row = bottom             # the window may add a button here
        self._restyle()
        self._show()

    # ------------------------------------------------------------ theme
    def changeEvent(self, e) -> None:                                # noqa: N802
        super().changeEvent(e)
        from PySide6.QtCore import QEvent
        if e.type() == QEvent.PaletteChange and not getattr(self, "_styling", False):
            self._restyle()

    def _restyle(self) -> None:
        from . import theme as TH
        if TH._current is None:
            css = "QFrame#bgCard { border: 1px solid #8888; border-radius: 6px; }"
        else:
            t = TH.current()
            css = (f"QFrame#bgCard {{ border: 1px solid {t.border}; border-radius: 6px; "
                   f"background: {t.surface}; }}")
        self._styling = True
        try:
            if self.card.styleSheet() != css:
                self.card.setStyleSheet(css)
        finally:
            self._styling = False

    # ------------------------------------------------------------ public
    def set_candidates(self, cands: Sequence, channels: Optional[Sequence[str]] = None,
                       um_per_px: Optional[float] = None) -> None:
        self._cands = list(cands or [])
        if channels:
            self._channels = [str(c) for c in channels]
        elif self._cands and getattr(self._cands[0], "channels", None):
            self._channels = list(self._cands[0].channels)
        if um_per_px:
            self._um = float(um_per_px)
        self._own = None
        n = len(self._cands)
        self.slider.blockSignals(True)
        self.slider.setRange(1, max(1, n))
        self.slider.blockSignals(False)
        self._cur = 0
        self._show()

    def candidates(self) -> list:
        return list(self._cands)

    def set_current(self, i: int) -> None:
        """Show candidate i (0-based) - no signal (the window calls this)."""
        if not self._cands:
            return
        self._own = None
        self._cur = int(np.clip(i, 0, len(self._cands) - 1))
        self._show()

    def current(self) -> int:
        return self._cur

    def set_own(self, cand) -> None:
        """Show the user's own region (bgpropose.measure_region) on the card;
        '+ Use this background' then emits accepted(its Roi). None: back to the
        proposals."""
        self._own = cand
        self._show()

    def set_chosen(self, text: str = "") -> None:
        """'Background: BG 2' under the panel once one is in use ('' hides it)."""
        self.lbl_chosen.setText(("✓ " + text) if text else "")
        self.lbl_chosen.setVisible(bool(text))

    def show_all(self) -> bool:
        return self.chk_all.isChecked()

    def set_show_all(self, on: bool) -> None:
        self.chk_all.setChecked(bool(on))

    # ------------------------------------------------------------ inside
    def _browse(self, i: int) -> None:
        if not self._cands:
            return
        i = int(np.clip(i, 0, len(self._cands) - 1))
        changed = i != self._cur or self._own is not None
        self._own = None
        self._cur = i
        self._show()
        if changed:
            self.candidate_changed.emit(i)

    def _use(self) -> None:
        if self._own is not None:
            self.accepted.emit(getattr(self._own, "roi", self._own))
        elif self._cands:
            self.accepted.emit(int(self._cur))

    def _set_chips(self, cand) -> None:
        mean = list(getattr(cand, "mean", []) if cand is not None else [])
        sd = list(getattr(cand, "sd", []) if cand is not None else [])
        names = list(getattr(cand, "channels", None) or self._channels) if cand is not None \
            else []
        per_row = 3 if len(mean) <= 3 else 2
        if getattr(self, "_per_row", None) != per_row or len(self.chips) < len(mean):
            while len(self.chips) < len(mean):
                self.chips.append(W.Chip())
            for c in self.chips:
                self.chips_lay.removeWidget(c)
            for i, c in enumerate(self.chips):
                self.chips_lay.addWidget(c, i // per_row, i % per_row, Qt.AlignLeft)
            self.chips_lay.setColumnStretch(per_row, 1)
            self._per_row = per_row
        for i, c in enumerate(self.chips):
            if i < len(mean):
                nm = names[i] if i < len(names) else f"Ch{i + 1}"
                s = sd[i] if i < len(sd) else float("nan")
                c.set(f"{nm} {_counts(mean[i])}", W.channel_colour(nm, i),
                      f"{nm}: mean {_counts(mean[i])} counts, SD {_counts(s)} (raw pixel "
                      f"values of this place at the timepoint shown).")
                c.setVisible(True)
            else:
                c.setVisible(False)

    def _show(self) -> None:
        n = len(self._cands)
        own = self._own
        cand = own if own is not None else (self._cands[self._cur] if n else None)
        browse = n > 1 and own is None
        for w_ in (self.btn_prev, self.slider, self.btn_next):
            w_.setEnabled(browse)
        self.btn_prev.setEnabled(browse and self._cur > 0)
        self.btn_next.setEnabled(browse and self._cur < n - 1)
        self.slider.blockSignals(True)
        self.slider.setValue(self._cur + 1)
        self.slider.blockSignals(False)
        self.lbl_count.setText(f"{self._cur + 1} of {n}" if n and own is None else
                               ("your own" if own is not None else ""))
        self.btn_use.setEnabled(cand is not None)
        if cand is None:
            self.lbl_name.setText("No empty place found")
            self.lbl_size.setText("")
            self.lbl_reason.setText("The image has no clear empty, dark place. "
                                    "Draw your own background region.")
            self._set_chips(None)
            return
        self.lbl_name.setText(getattr(cand, "label", "") or "Background")
        roi = getattr(cand, "roi", None)
        if roi is not None:
            y0, x0, y1, x1 = roi.bbox
            if own is not None:
                self.lbl_size.setText(f"{roi.area * self._um ** 2:,.0f} µm²")
            else:
                self.lbl_size.setText(f"{(x1 - x0) * self._um:.0f} x {(y1 - y0) * self._um:.0f} µm")
        reason = getattr(cand, "reason", "") or ""
        self.lbl_reason.setText(reason[:1].upper() + reason[1:] if reason else "")
        self._set_chips(cand)
