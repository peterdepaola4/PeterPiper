"""
PeterPiper 4.0: hover explanations, with a small picture where a picture helps.

Every window uses these two helpers so the explanations look the same everywhere:

    tip(widget, "What this does, in one or two plain sentences.",
        title="Short name", pic="bg_first")         # pic: assets/tips/bg_first.png
    help_button("What this does ...", title=..., pic=...)   # a small (?) button:
                                                     # hover OR click shows the same

Pictures are PNG files in assets/tips/ (about 320 x 160 px, light background,
made by build/make_tips.py so they can be remade). A missing picture is simply
left out - the text still shows.
"""
from __future__ import annotations

import html
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QToolButton, QToolTip, QWidget

TIPS_DIR = Path(__file__).resolve().parents[1] / "assets" / "tips"
PIC_WIDTH = 320                  # px: the picture is shown at this width


def pic_path(name: Optional[str]) -> Optional[Path]:
    """The picture's file, or None when there is no such picture."""
    if not name:
        return None
    p = TIPS_DIR / (name if name.endswith(".png") else name + ".png")
    return p if p.is_file() else None


def tip_html(text: str, title: str = "", pic: Optional[str] = None) -> str:
    """Rich tooltip text: a bold title, the explanation, then the picture.
    'text' may hold simple HTML (<b>, <br>, <ul>); plain text is escaped only
    when it has no tags."""
    body = text if ("<" in text and ">" in text) else html.escape(text)
    parts = [f"<div style='max-width:{PIC_WIDTH + 20}px'>"]
    if title:
        parts.append(f"<b>{html.escape(title)}</b><br>")
    parts.append(body)
    p = pic_path(pic)
    if p is not None:
        parts.append(f"<br><img src='{p.as_posix()}' width='{PIC_WIDTH}'>")
    parts.append("</div>")
    return "".join(parts)


def tip(widget: QWidget, text: str, title: str = "", pic: Optional[str] = None) -> QWidget:
    """Give 'widget' a hover explanation (with an optional picture). Returns it."""
    widget.setToolTip(tip_html(text, title, pic))
    return widget


class HelpButton(QToolButton):
    """A small round (?) button: hover or click shows the explanation."""

    def __init__(self, text: str, title: str = "", pic: Optional[str] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setText("?")
        self.setObjectName("helpButton")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(20, 20)
        self.setStyleSheet("QToolButton#helpButton{border-radius:10px;font-weight:bold;"
                           "padding:0px;}")
        self._html = tip_html(text, title, pic)
        self.setToolTip(self._html)
        self.clicked.connect(self._show)

    def _show(self) -> None:
        QToolTip.showText(self.mapToGlobal(QPoint(self.width(), self.height())),
                          self._html, self)


def help_button(text: str, title: str = "", pic: Optional[str] = None,
                parent: Optional[QWidget] = None) -> HelpButton:
    return HelpButton(text, title, pic, parent)
