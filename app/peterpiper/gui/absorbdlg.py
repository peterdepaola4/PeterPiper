"""
PeterPiper 1.2: the "Older PeterPiper versions found" window (peterpiper.absorb).

offer_on_start(parent) is called by the start screen once it shows: once per
program start, it looks (quickly) for older PeterPiper versions that can be
taken in and, if there are any not set to "Don't ask again", opens this window
WITHOUT blocking (the start screen stays usable). The sizes are counted in the
background after the window shows. Buttons: Absorb / Not now / Don't ask again
for these. After Absorb the window says, per version, what was copied, which
shortcuts now start this version, what went to the Recycle Bin (restorable) and
what was kept, and where.
"""
from __future__ import annotations

import os
import sys
import threading
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel, QVBoxLayout,
                               QWidget)

from .. import absorb as A
from . import widgets as W

_offered = False                         # once per program start


def offer_on_start(parent: Optional[QWidget] = None,
                   places: Optional[A.Places] = None) -> Optional["AbsorbDialog"]:
    """Open the window (not blocking) when there is something to take in; the
    first call per program start only. Never raises; returns the window or None."""
    global _offered
    if _offered or os.environ.get("PETERPIPER_NO_ABSORB"):
        return None
    _offered = True
    try:
        pl = places if places is not None else A.default_places()
        found = A.to_offer(pl)
        if not found:
            return None
        dlg = AbsorbDialog(found, parent, pl)
        dlg.show()
        dlg.raise_()
        return dlg
    except Exception:                                              # noqa: BLE001
        return None


def _bin() -> str:
    return "Trash" if sys.platform == "darwin" else "Recycle Bin"


class AbsorbDialog(QDialog):
    def __init__(self, found: List[A.Found], parent: Optional[QWidget] = None,
                 places: Optional[A.Places] = None) -> None:
        super().__init__(parent)
        self.setWindowFlag(Qt.Window, True)
        self.setWindowModality(Qt.NonModal)
        self.setWindowTitle("PeterPiper - older versions found")
        self.found = list(found)
        self.places = places if places is not None else A.default_places()
        self.outcomes: List[A.Outcome] = []
        self.choice = ""                    # "absorb" | "later" | "dont_ask"
        self._sizes: Dict[int, dict] = {}
        self.setMinimumWidth(760)

        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        t = QLabel("Older PeterPiper versions are on this computer")
        t.setProperty("role", "title")
        lay.addWidget(t)
        running = self.found[0].running_label if self.found else "This version"
        self._intro = [W.wrapped_label(
            f"Your profiles, settings and run lists are already shared by every PeterPiper "
            f"version (in {self.places.data}), so {running} has them. Absorbing an older "
            f"version tidies up what is left of it:"), W.wrapped_label(
            f"•  anything it kept for itself is copied to PeterPiper data (nothing there is "
            f"overwritten)\n"
            f"•  the PeterPiper shortcuts (Desktop, Start menu) start {running}\n"
            f"•  its program files and its private Python go to the {_bin()} - you can "
            f"restore them from there\n"
            f"•  your own files in its folder (results, notes, movies ...) stay where they are",
            muted=True)]
        for lab in self._intro:
            lay.addWidget(lab)
        self._cards = QVBoxLayout()
        self._cards.setSpacing(8)
        self.checks: List[QCheckBox] = []
        self.details: List[QLabel] = []
        self.cards: List[QWidget] = []
        for i, f in enumerate(self.found):
            self.cards.append(self._card(i, f))
            self._cards.addWidget(self.cards[-1])
        lay.addLayout(self._cards)
        self.lbl_result = W.wrapped_label("")
        self.lbl_result.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.lbl_result.setVisible(False)
        lay.addWidget(self.lbl_result)
        lay.addStretch(1)

        self.btn_absorb = W.button("Absorb", self._absorb, "Take the ticked versions in now.",
                                   strong=True)
        self.btn_later = W.button("Not now", self._later, "Ask again at the next start.")
        self.btn_never = W.button("Don't ask again for these", self._dont_ask,
                                  "Do not offer these folders again on this computer.")
        self.btn_close = W.button("Close", self.accept, "Close this window.", strong=True)
        self.btn_close.setVisible(False)
        bl = QHBoxLayout()
        bl.addWidget(self.btn_never)
        bl.addStretch(1)
        bl.addWidget(self.btn_later)
        bl.addWidget(self.btn_absorb)
        bl.addWidget(self.btn_close)
        lay.addLayout(bl)
        self.adjustSize()

        # sizes: counted in the background once the window is there
        self._timer = QTimer(self)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._show_sizes)
        self._timer.start()
        threading.Thread(target=self._count, daemon=True).start()

    # ------------------------------------------------------------ layout
    def _card(self, i: int, f: A.Found) -> QWidget:
        card = QFrame()
        card.setObjectName("card")
        card.setFrameShape(QFrame.StyledPanel)
        try:
            from . import theme as TH
            if TH._current is not None:
                t_ = TH.current()
                card.setStyleSheet(f"QFrame#card {{ background: {t_.surface}; border: 1px solid "
                                   f"{t_.border}; border-radius: 10px; }}")
        except Exception:                                          # noqa: BLE001
            pass
        cl = QVBoxLayout(card)
        cl.setContentsMargins(12, 8, 12, 8)
        cb = QCheckBox(f.label)
        cb.setChecked(True)
        fnt = cb.font()
        fnt.setBold(True)
        cb.setFont(fnt)
        self.checks.append(cb)
        cl.addWidget(cb)
        lab = W.wrapped_label(self._detail_text(f, None), muted=True)
        lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.details.append(lab)
        cl.addWidget(lab)
        return card

    @staticmethod
    def _detail_text(f: A.Found, s: Optional[dict]) -> str:
        def size(key: str) -> str:
            if s is None:
                return " (counting ...)"
            return f" ({A.nice_size(s.get(key, 0))})"
        lines = []
        for p in f.programs:
            lines.append(f"Program folder: {p}" + size("program"))
        if f.home is not None:
            if f.keep_home:
                lines.append(f"Private Python: {f.home} - {f.keep_home}")
            else:
                lines.append(f"Private Python: {f.home}" + size("python"))
        for d in f.dev_copies:
            lines.append(f"Developer copy: {d} - left as it is")
        if s is not None and s.get("kept"):
            lines.append(f"Your own files in its folder stay where they are "
                         f"({A.nice_size(s['kept'])})")
        return "\n".join(lines)

    def _count(self) -> None:
        for i, f in enumerate(self.found):
            try:
                self._sizes[i] = A.sizes(f)
            except Exception:                                      # noqa: BLE001
                self._sizes[i] = {}

    def _show_sizes(self) -> None:
        for i, f in enumerate(self.found):
            if i in self._sizes and i < len(self.details):
                self.details[i].setText(self._detail_text(f, self._sizes[i]))
        if len(self._sizes) >= len(self.found):
            self._timer.stop()

    # ------------------------------------------------------------ actions
    def chosen(self) -> List[A.Found]:
        return [f for f, cb in zip(self.found, self.checks) if cb.isChecked()]

    def _later(self) -> None:
        self.choice = "later"
        self.reject()

    def _dont_ask(self) -> None:
        self.choice = "dont_ask"
        A.set_dont_ask(self.found, self.places.data)
        self.reject()

    def _absorb(self) -> None:
        todo = self.chosen()
        if not todo:
            return
        self.choice = "absorb"
        pl = self.places

        def work(progress):
            return [A.absorb(f, pl, progress=progress) for f in todo]
        try:
            self.outcomes = W.run_with_progress(self, "Absorbing older PeterPiper versions ...",
                                                work)
        except Exception as exc:                                   # noqa: BLE001
            self.outcomes = []
            self.lbl_result.setText(f"Something went wrong: {exc}. Nothing more was changed.")
        else:
            self.lbl_result.setText(self.result_text())
        for w in self._intro + self.cards:          # the result says it all
            w.setVisible(False)
        self.lbl_result.setVisible(True)
        for b in (self.btn_absorb, self.btn_later, self.btn_never):
            b.setVisible(False)
        self.btn_close.setVisible(True)
        self.adjustSize()

    def result_text(self) -> str:
        bad = [o for o in self.outcomes if o.problem]
        head = ("Done." if not bad else
                "Not everything could be done - see below; what was not moved is kept.")
        body = "\n".join("\n".join(o.lines()) for o in self.outcomes)
        return f"{head}\n{body}"
