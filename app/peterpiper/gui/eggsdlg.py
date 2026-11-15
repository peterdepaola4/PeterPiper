"""
PeterPiper 1.1: 'Hidden extras' - a small window listing the hidden extras this
user has found (achievements.py) and how many are still hidden. Harmless fun:
it only reads achievements.json. The analysis window's Help menu offers it only
once something has been found:

    from .eggsdlg import show_achievements
    show_achievements(parent)
"""
from __future__ import annotations

import html
from datetime import datetime

from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QVBoxLayout

from .. import achievements
from . import widgets as W


def _when(iso: str) -> str:
    try:
        return datetime.fromisoformat(str(iso)).strftime("%d %b %Y")
    except ValueError:
        return ""


class AchievementsDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Hidden extras")
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        title = QLabel("Hidden extras you found")
        title.setProperty("role", "title")
        lay.addWidget(title)
        got = achievements.found()
        self.rows = []
        for key, text in achievements.CATALOGUE.items():
            if key not in got:
                continue
            when = _when(got[key])
            lab = QLabel(f"\u2605&nbsp;&nbsp;{html.escape(text)}"
                         + (f"<br><span>&nbsp;&nbsp;&nbsp;&nbsp;found {when}</span>"
                            if when else ""))
            lab.setWordWrap(True)
            lay.addWidget(lab)
            self.rows.append(key)
        if not self.rows:
            lay.addWidget(W.wrapped_label("None yet.", muted=True))
        n = achievements.hidden_count()
        self.hidden = n
        self.lbl_more = W.wrapped_label(
            "You found them all!" if n == 0 else
            f"{n} more {'is' if n == 1 else 'are'} hidden somewhere in PeterPiper.",
            muted=True)
        lay.addWidget(self.lbl_more)
        btns = QHBoxLayout()
        btns.addStretch(1)
        btns.addWidget(W.button("Close", self.accept, "Close this window.", strong=True))
        lay.addLayout(btns)


def show_achievements(parent=None) -> None:
    """Show the hidden extras found so far (a small modal window)."""
    AchievementsDialog(parent).exec()
