"""
The plot builder: one measure as a sentence of dropdowns (V2.7; V2.8: every
measure kind, compartment ratios, explanations on hover),

    [R/R0 ▼] of [GFP ▼] over [Cy5 ▼] in the [Nucleus ▼]
    [Compartment ratio ▼] of [GFP ▼] in the [Nucleus ▼] over the [Cytoplasm ▼]
    [Area ▼] of the [Nucleus ▼]

('over' only for the two-channel ratios). The lists only offer what every
ticked run has (xyplot.options), so a choice can always be plotted. Optional
first entries ('Time' / 'Timepoint' for X, 'none' for the right Y axis) stand
for 'no measure'. Hover a kind for what it is and what it is good for.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QWidget

from .. import compare as C
from .. import xyplot as X

FIRST_TIPS = {
    X.TIME: "Time from each run's own baseline, in minutes (timepoints when the frame "
            "interval is not known). The usual time course: how the measure changes after "
            "your treatment.",
    X.TIMEPOINT: "Timepoint numbers from each run's own baseline (0 = the baseline). Use it "
                 "when runs were imaged at different intervals and you want frame by frame.",
    "": "No second measure.",
}


class MeasureRow(QWidget):
    changed = Signal()

    def __init__(self, first: Sequence[Tuple[str, str]] = (), parent=None) -> None:
        """first: entries before the measures, [(text, data)] - e.g.
        [('Time', TIME), ('Timepoint', TIMEPOINT)] or [('none', '')]."""
        super().__init__(parent)
        if isinstance(first, str):                     # V2.7 call: 'Time' / 'none'
            first = [(first, X.TIME if first == "Time" else "")]
        self.first = list(first or [])
        self._opts: Dict[str, List[str]] = {}
        self._busy = False
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.cmb_kind, self.cmb_a, self.cmb_b, self.cmb_comp, self.cmb_other = (
            QComboBox() for _ in range(5))
        self.lbl_of, self.lbl_over, self.lbl_in, self.lbl_over2 = (
            QLabel("of"), QLabel("over"), QLabel("in the"), QLabel("over the"))
        for w in (self.cmb_kind, self.lbl_of, self.cmb_a, self.lbl_over, self.cmb_b,
                  self.lbl_in, self.cmb_comp, self.lbl_over2, self.cmb_other):
            lay.addWidget(w)
            if isinstance(w, QComboBox):           # every entry readable, never cut off
                w.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        lay.addStretch(1)
        self.cmb_kind.setToolTip("What to measure - hover each entry of the list for what it "
                                 "is and what it tells you.")
        self.cmb_kind.currentIndexChanged.connect(lambda _i: self._update(0))
        self.cmb_a.currentIndexChanged.connect(lambda _i: self._update(1))
        self.cmb_b.currentIndexChanged.connect(lambda _i: self._update(2))
        self.cmb_comp.currentIndexChanged.connect(lambda _i: self._update(3))
        self.cmb_other.currentIndexChanged.connect(lambda _i: self._update(4))

    # -------------------------------------------------------------- options
    def _parts(self) -> List[tuple]:
        """(kind, channel A, channel B, compartment, other compartment) of every
        quantity on offer."""
        out = []
        for comp, qs in self._opts.items():
            for q in qs:
                k, a, b, other = C.split_name(q)
                out.append((k, a, b, comp, other))
        return out

    @staticmethod
    def _fill(cmb: QComboBox, items: List[tuple], keep, tips: Optional[dict] = None) -> None:
        cmb.blockSignals(True)
        cmb.clear()
        for text, data in items:
            cmb.addItem(text, data)
            if tips and data in tips:
                cmb.setItemData(cmb.count() - 1, tips[data], Qt.ToolTipRole)
        i = cmb.findData(keep)
        cmb.setCurrentIndex(i if i >= 0 else (0 if items else -1))
        cmb.blockSignals(False)

    def set_options(self, opts: Dict[str, List[str]]) -> None:
        """opts: {compartment: quantities} (xyplot.options of the ticked runs)."""
        keep = self.measure()
        first = self.first_choice()
        self._opts = dict(opts)
        self._update(-1, keep)
        if keep is None and first is not None:
            self.cmb_kind.setCurrentIndex(max(0, self.cmb_kind.findData(first)))

    def _update(self, level: int, keep: Optional[X.Measure] = None) -> None:
        if self._busy:
            return
        self._busy = True
        try:
            if keep is not None:
                kind, a, b, other = C.split_name(keep.quantity)
                comp = keep.comp
            elif level > -1:
                kind, a, b, comp, other = (self.cmb_kind.currentData(),
                                           self.cmb_a.currentData(), self.cmb_b.currentData(),
                                           self.cmb_comp.currentData(),
                                           self.cmb_other.currentData())
            else:
                kind = self.cmb_kind.currentData() or ""
                a = b = comp = other = None
            parts = self._parts()
            if level <= 0:
                kinds = [(t, k) for k, t in X.KINDS if any(p[0] == k for p in parts)]
                tips = dict(X.EXPLAIN)
                tips.update(FIRST_TIPS)
                self._fill(self.cmb_kind, list(self.first) + kinds, kind, tips)
            kind = self.cmb_kind.currentData()
            on = kind not in (None, "", X.TIME, X.TIMEPOINT)
            ratio = kind in X.RATIO_KINDS
            cratio = kind in X.COMP_RATIO_KINDS
            area = kind == "Area"
            self.lbl_of.setText("of the" if area else "of")
            self.lbl_of.setVisible(on)
            self.cmb_comp.setVisible(on)
            self.lbl_in.setVisible(on and not area)
            self.cmb_a.setVisible(on and not area)
            for w in (self.lbl_over, self.cmb_b):
                w.setVisible(on and ratio)
            for w in (self.lbl_over2, self.cmb_other):
                w.setVisible(on and cratio)
            self.cmb_kind.setToolTip(X.EXPLAIN.get(kind) or FIRST_TIPS.get(kind or "", ""))
            if not on:
                return
            mine = [p for p in parts if p[0] == kind]
            if level <= 1:
                self._fill(self.cmb_a, [(v, v) for v in dict.fromkeys(p[1] for p in mine)], a)
            a = "" if area else self.cmb_a.currentData()
            mine = [p for p in mine if p[1] == (a or "")]
            if level <= 2:
                self._fill(self.cmb_b, [(v, v) for v in dict.fromkeys(p[2] for p in mine if p[2])],
                           b)
            b = self.cmb_b.currentData() if ratio else ""
            mine = [p for p in mine if p[2] == (b or "")]
            if level <= 3:
                comps = [c for c in C.COMPS if any(p[3] == c for p in mine)]
                self._fill(self.cmb_comp, [(C.COMP_LABELS.get(c, c), c) for c in comps], comp)
            comp = self.cmb_comp.currentData()
            mine = [p for p in mine if p[3] == comp]
            if level <= 4:
                others = [c for c in C.COMPS if any(p[4] == c for p in mine)]
                self._fill(self.cmb_other, [(C.COMP_LABELS.get(c, c), c) for c in others], other)
        finally:
            self._busy = False
        self.changed.emit()

    # ---------------------------------------------------------------- value
    def first_choice(self) -> Optional[str]:
        """The data of the first entry chosen (TIME / TIMEPOINT / ''), else None."""
        if self.cmb_kind.currentIndex() < 0:
            return None
        k = self.cmb_kind.currentData()
        return k if k in [d for _t, d in self.first] else None

    def measure(self) -> Optional[X.Measure]:
        kind = self.cmb_kind.currentData()
        comp = self.cmb_comp.currentData()
        if kind in (None, "", X.TIME, X.TIMEPOINT) or not comp:
            return None
        if kind in X.COMP_RATIO_KINDS:
            q = X.join_quantity(kind, self.cmb_a.currentData() or "",
                                self.cmb_other.currentData() or "")
        elif kind == "Area":
            q = "Area"
        else:
            b = self.cmb_b.currentData() if kind in X.RATIO_KINDS else ""
            q = X.join_quantity(kind, self.cmb_a.currentData() or "", b or "")
        return X.Measure(comp, q) if q in self._opts.get(comp, []) else None

    def set_measure(self, m: Optional[X.Measure], first: Optional[str] = None) -> None:
        """Choose this measure (None: a first entry - `first`, else the first one)."""
        if m is None:
            if self.first:
                i = self.cmb_kind.findData(first) if first is not None else 0
                self.cmb_kind.setCurrentIndex(max(0, i))
            return
        self._update(-1, m)
