"""
V2.9 'Computer check' window (peterpiper.syscheck): the long-path setting and the
Python version, each with what was found and what to do. Nothing is changed by
PeterPiper unless you press a button that says so - a command to copy is offered
where it helps, and (1.2) 'Turn on Windows long paths' runs it for you after
Windows' own administrator approval.
"""
from __future__ import annotations

import sys
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel,
                               QVBoxLayout, QWidget)

from .. import syscheck as SC
from . import widgets as W

MARK = {"ok": ("✓", "ok"), "warn": ("!", "warn"), "bad": ("✗", "danger"),
        "unknown": ("?", "warn")}


class ComputerCheckDialog(QDialog):
    def __init__(self, parent=None, items: Optional[List[SC.Item]] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("PeterPiper - computer check")
        self.resize(640, 420)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        t = QLabel("Computer check")
        t.setProperty("role", "title")
        lay.addWidget(t)
        lay.addWidget(W.wrapped_label(
            "Is this computer set up the way PeterPiper needs? PeterPiper only looks - it changes "
            "nothing unless you press a button that says so. This window comes back by itself only if something here changes; it is "
            "always under Help > Computer check...", muted=True))
        self._box = QVBoxLayout()
        lay.addLayout(self._box)
        lay.addStretch(1)
        self.chk_again = QCheckBox("Show this again when something changes")
        self.chk_again.setChecked(bool(SC._load_state().get("show_on_change", True)))
        btn_re = W.button("Check again", lambda: self._fill(SC.run_checks()),
                          "Look again (e.g. after changing the setting and restarting).")
        btn_ok = W.button("OK", self.accept, "Close.", strong=True)
        bl = QHBoxLayout()
        bl.addWidget(self.chk_again)
        bl.addStretch(1)
        bl.addWidget(btn_re)
        bl.addWidget(btn_ok)
        lay.addLayout(bl)
        self._fill(items if items is not None else SC.run_checks())

    def _fill(self, items: List[SC.Item]) -> None:
        self.items = items
        while self._box.count():
            w = self._box.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        for it in items:
            self._box.addWidget(self._card(it))

    def _card(self, it: SC.Item) -> QWidget:
        card = QFrame()
        card.setObjectName("card")
        card.setFrameShape(QFrame.StyledPanel)
        cl = QHBoxLayout(card)
        cl.setContentsMargins(12, 10, 12, 10)
        sym, role = MARK.get(it.status, ("?", "warn"))
        from . import theme as TH
        t_ = TH.current() if TH._current is not None else None
        colour = {"ok": t_.ok, "warn": t_.warn, "danger": t_.danger}[role] if t_ else ""
        mark = QLabel(sym)
        mark.setStyleSheet(f"font-size: 20pt; font-weight: 700; color: {colour};")
        mark.setFixedWidth(32)
        if t_ is not None:
            card.setStyleSheet(f"QFrame#card {{ background: {t_.surface}; border: 1px solid "
                               f"{t_.border}; border-radius: 10px; }}")
        cl.addWidget(mark)
        col = QVBoxLayout()
        head = QLabel(it.title)
        hf = head.font()
        hf.setBold(True)
        head.setFont(hf)
        col.addWidget(head)
        col.addWidget(W.wrapped_label(it.found))
        if it.advice:
            col.addWidget(W.wrapped_label(it.advice, muted=True))
        if it.command:
            cmd = QLabel(it.command)
            cmd.setWordWrap(True)
            cmd.setTextInteractionFlags(Qt.TextSelectableByMouse)
            cmd.setStyleSheet("font-family: Consolas, monospace;")
            btn = W.button("Copy command", lambda _c=False, c=it.command:
                           QApplication.clipboard().setText(c),
                           "Copy it, open PowerShell with 'Run as administrator', paste, "
                           "press Enter, restart Windows.")
            col.addWidget(cmd)
            if it.key == "long_paths" and sys.platform == "win32":     # 1.2
                self.btn_turn_on = W.button(
                    "Turn on Windows long paths", self._turn_on,
                    "Runs the command for you: Windows asks for administrator approval. "
                    "Explorer and Excel may still not open very long paths even then.")
                r = W.row(self.btn_turn_on, btn)
            else:
                r = W.row(btn)
            r.layout().addStretch(1)
            r.setStyleSheet("background: transparent;")
            col.addWidget(r)
        cl.addLayout(col, 1)
        return card

    def _turn_on(self) -> None:
        """1.2: 'Turn on Windows long paths' - then look again."""
        turn_on_long_paths(self)
        self._fill(SC.run_checks())

    def done(self, r: int) -> None:                               # noqa: D401
        SC.remember(self.items, self.chk_again.isChecked())
        super().done(r)


def turn_on_long_paths(parent=None) -> Optional[bool]:
    """1.2: turn on Windows' long paths (Windows asks for administrator approval;
    syscheck.turn_on_long_paths) and say plainly what happened. Used by the
    computer check and the long-path warning of an export. True = on now."""
    from PySide6.QtWidgets import QMessageBox
    on, text = SC.turn_on_long_paths(poll=QApplication.processEvents)
    if on is True:
        QMessageBox.information(parent, "Windows long paths", text)
    else:
        QMessageBox.warning(parent, "Windows long paths", text)
    return on


def maybe_show(parent=None) -> None:
    """At start: the check window if this is the computer's first start or a
    result changed since; otherwise only remembered silently."""
    items = SC.run_checks()
    if SC.should_show(items):
        ComputerCheckDialog(parent, items).exec()
