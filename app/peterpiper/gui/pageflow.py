"""
PeterPiper 4.0: the page header of the analysis window's 4-page flow.

    ◀ Back   ✓ 1 Start › 2 Draw › 3 Track & check › 4 Graphs & export   [Track 18 cells ▶]
             Pick the background first: browse the green squares, then press +.

- the current page is highlighted, finished pages carry a tick, pages that
  cannot be reached yet are greyed out (set_enabled);
- '◀ Back' is always there: the previous page (on page 2 it means "back to the
  start window" - the window decides, back() is only the request);
- 'Next ▶' carries a short state text ("Track 18 cells") and can be disabled;
- one quiet line under it says what to do now (set_hint).
Every page name has a hover explanation. Colours come from the theme.

    PageFlow(pages=None, tips=None)
      set_page(i) / page()   set_done(i, bool)   set_enabled(i, bool)
      set_next(text, enabled=True)   set_hint(text)
    signals: page_requested(int), back(), next()
"""
from __future__ import annotations

from typing import List, Optional, Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QSizePolicy, QToolButton,
                               QVBoxLayout, QWidget)

from . import widgets as W
from .tips import tip

PAGES = ["Start", "Draw", "Track & check", "Graphs & export"]
PAGE_TIPS = [
    "The start window: choose the movie (or a queue of movies), the lab server folder "
    "and the backup. Going here closes this movie (your work is saved first).",
    "First pick the background (a dark, empty place), then draw or auto-detect the cells "
    "and their compartments.",
    "Follow every cell through the movie, then check the traces: include or exclude "
    "cells, set the baseline timepoint, fix a cell that was followed wrongly.",
    "Build graphs of any quantity (per cell, per run, across runs) and save Excel, "
    "Prism or CSV files.",
]


class PageFlow(QWidget):
    page_requested = Signal(int)
    back = Signal()
    next = Signal()

    def __init__(self, pages: Optional[Sequence[str]] = None,
                 tips: Optional[Sequence[str]] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._pages = list(pages or PAGES)
        n = len(self._pages)
        self._tips = list(tips or (PAGE_TIPS if n == len(PAGE_TIPS) else [""] * n))
        self._cur = min(1, n - 1)
        self._done = [False] * n
        self._enabled = [i <= self._cur for i in range(n)]

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 2)
        lay.setSpacing(1)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        self.btn_back = QPushButton("◀  Back")
        self.btn_back.clicked.connect(self.back.emit)
        row.addWidget(self.btn_back)
        row.addSpacing(8)
        self.crumbs: List[QToolButton] = []
        self.seps: List[QLabel] = []
        for i, name in enumerate(self._pages):
            if i:
                s = QLabel("›")
                s.setProperty("muted", True)
                self.seps.append(s)
                row.addWidget(s)
            b = QToolButton()
            b.setObjectName("pageCrumb")
            b.setAutoRaise(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _c=False, i=i: self._crumb(i))
            tip(b, self._tips[i] if i < len(self._tips) else "", f"{i + 1}  {name}", "view_pages")
            self.crumbs.append(b)
            row.addWidget(b)
        row.addStretch(1)
        self.btn_next = QPushButton("Next  ▶")
        self.btn_next.setProperty("primary", True)
        self.btn_next.clicked.connect(self.next.emit)
        row.addWidget(self.btn_next)
        lay.addLayout(row)
        self.lbl_hint = W.ElidedLabel("", Qt.ElideRight)
        self.lbl_hint.setProperty("muted", True)
        self.lbl_hint.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        lay.addWidget(self.lbl_hint)
        self._next_text = ""
        self._update()

    # ------------------------------------------------------------ public
    def pages(self) -> List[str]:
        return list(self._pages)

    def set_page(self, i: int) -> None:
        self._cur = max(0, min(int(i), len(self._pages) - 1))
        self._enabled[self._cur] = True
        self._update()

    def page(self) -> int:
        return self._cur

    def set_done(self, i: int, done: bool = True) -> None:
        if 0 <= i < len(self._pages):
            self._done[i] = bool(done)
            self._update()

    def is_done(self, i: int) -> bool:
        return bool(self._done[i]) if 0 <= i < len(self._pages) else False

    def set_enabled(self, i: int, on: bool = True) -> None:
        """Whether page i can be reached now (the current page always can)."""
        if 0 <= i < len(self._pages):
            self._enabled[i] = bool(on)
            self._update()

    def is_enabled(self, i: int) -> bool:
        return 0 <= i < len(self._pages) and (self._enabled[i] or i == self._cur)

    def set_next(self, text: str = "", enabled: bool = True) -> None:
        """'Next ▶' with a short state text, e.g. set_next('Track 18 cells')."""
        self._next_text = str(text or "")
        txt = self._next_text.replace("&", "&&")          # '&' is not a shortcut mark
        self.btn_next.setText(f"{txt}  ▶" if txt else "Next  ▶")
        self.btn_next.setEnabled(bool(enabled))

    def set_next_tip(self, text: str) -> None:
        tip(self.btn_next, text, "Next")

    def set_hint(self, text: str) -> None:
        """The one 'what to do now' line under the bar."""
        self.lbl_hint.setText(str(text or ""))

    def hint(self) -> str:
        return self.lbl_hint.text()

    # ------------------------------------------------------------ inside
    def _crumb(self, i: int) -> None:
        if i != self._cur and self.is_enabled(i):
            self.page_requested.emit(int(i))

    def changeEvent(self, e) -> None:                                # noqa: N802
        super().changeEvent(e)
        from PySide6.QtCore import QEvent
        if e.type() == QEvent.PaletteChange and not getattr(self, "_styling", False):
            self._update()

    def crumb_text(self, i: int) -> str:
        return self.crumbs[i].text().replace("&&", "&")

    def _update(self) -> None:
        from . import theme as TH
        if TH._current is not None:
            t = TH.current()
            acc, on_acc, ok, muted = t.accent, t.accent_text, t.ok, t.muted
        else:
            acc, on_acc, ok, muted = "#3d7fd6", "white", "#2e8b57", "#888888"
        self._styling = True
        try:
            for i, b in enumerate(self.crumbs):
                cur = i == self._cur
                done = self._done[i] and not cur
                b.setText(("✓ " if done else "") + f"{i + 1} {self._pages[i]}".replace("&", "&&"))
                b.setEnabled(self.is_enabled(i))
                if cur:
                    css = (f"QToolButton#pageCrumb {{ background: {acc}; color: {on_acc}; "
                           f"font-weight: 700; border-radius: 4px; padding: 3px 8px; }}")
                elif done:
                    css = (f"QToolButton#pageCrumb {{ color: {ok}; padding: 3px 8px; }}"
                           f"QToolButton#pageCrumb:disabled {{ color: {muted}; }}")
                else:
                    css = (f"QToolButton#pageCrumb {{ padding: 3px 8px; }}"
                           f"QToolButton#pageCrumb:disabled {{ color: {muted}; }}")
                if b.styleSheet() != css:
                    b.setStyleSheet(css)
        finally:
            self._styling = False
        back_tip = ("Back to the start window (your work here is saved first)."
                    if self._cur <= 1 else
                    f"Back to page {self._cur}: {self._pages[self._cur - 1]}.")
        tip(self.btn_back, back_tip, "Back")
        self.btn_back.setEnabled(self._cur > 0)
