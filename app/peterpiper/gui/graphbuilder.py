"""
PeterPiper 4.0 graph builder widget: "Y vs X (vs Z)", typed like a sentence or
picked from three compact rows, drawn at once (pyqtgraph, white plot).

    GraphBuilder(parent, multi_run=False)
        .set_runs([RunData, ...])            what to plot (graphbuilder.RunData)
        .set_spec(GraphSpec) / .spec()       the graph (the rows and the sentence follow)
        .set_sentence(text) / .sentence()
        .set_run_colours({name: colour})     Compare: colours of runs / conditions / groups
        .set_drift_window(a, b)              the drift add-on's frames (Settings.drift_*)
        .export_image(path) / .export_table(path)   .png / .svg ; .csv / .xlsx
        cell_clicked(run key, cell k)        a point / trace was clicked
        spec_changed(GraphSpec)

Embeddable: the analysis window's Graphs page (one run) and Compare's 'Graphs across
runs' (several runs; the split choice appears). Every control has a hover
explanation (tips.py; pictures in assets/tips/graphs_*.png). The plot always fits
itself again after every change and every resize.
"""
from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QStringListModel, Qt, QTimer, Signal
from PySide6.QtWidgets import (QComboBox, QCompleter, QDoubleSpinBox, QHBoxLayout, QLabel,
                               QLineEdit, QMenu, QSizePolicy, QSpinBox, QToolButton, QVBoxLayout,
                               QWidget, QWidgetAction)

from .. import graphbuilder as G
from .. import graphparse as P
from .tips import help_button, tip

MEASURE_SHORT = {"mean": "mean", "total": "summed", "ff0": "F/F0", "rr0": "R/R0",
                 "ratio": "ratio", "xbg": "× bg", "raw": "raw", "area": "area"}
TIME_SHORT = {"trace": "trace", "at": "at", "end": "at end", "mean": "mean of", "max": "max of",
              "min": "min of", "auc": "AUC of", "slope": "slope of"}
UNIT_SHORT = {"tp": "timepoints", "min": "min", "frame": "frame #"}
NO_T = -100000.0             # spin box minimum: 'start' / 'end' (= not set)
PX = 1.0


def _combo(items, tips=None, tiptext="") -> QComboBox:
    c = QComboBox()
    for key, text in items:
        c.addItem(text, key)
        if tips and key in tips:
            c.setItemData(c.count() - 1, tips[key], Qt.ToolTipRole)
    c.setSizeAdjustPolicy(QComboBox.AdjustToContents)
    if tiptext:
        tip(c, tiptext)
    return c


def _set(c: QComboBox, key) -> None:
    i = c.findData(key)
    if i >= 0:
        c.setCurrentIndex(i)


class QuantityRow(QWidget):
    """One row: [compartment] [channel] [/ channel B] [measure] [time] [t1] [t2] [unit]."""
    changed = Signal()

    def __init__(self, role: str, parent=None) -> None:
        super().__init__(parent)
        self.role = role
        self._busy = False
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        self.lbl = QLabel({"Y": "Y", "X": "vs X", "Z": "vs Z"}[role])
        self.lbl.setMinimumWidth(34)
        self.lbl.setStyleSheet("font-weight: bold;")
        lay.addWidget(self.lbl)
        self.cmb_comp = _combo([])
        self.cmb_a = _combo([])
        self.lbl_over = QLabel("/")
        self.cmb_b = _combo([])
        self.cmb_m = _combo([(k, MEASURE_SHORT[k]) for k in G.MEASURES], G.MEASURE_TIPS)
        self.cmb_t = _combo([(k, TIME_SHORT[k]) for k in G.TIMES], G.TIME_TIPS)
        self.sp1, self.sp2 = QDoubleSpinBox(), QDoubleSpinBox()
        for sp, special in ((self.sp1, "start"), (self.sp2, "end")):
            sp.setRange(NO_T, 100000)
            sp.setDecimals(1)
            sp.setSpecialValueText(special)
            sp.setKeyboardTracking(False)
            sp.setMaximumWidth(78)
            sp.valueChanged.connect(lambda _v: self._emit())
        self.lbl_to = QLabel("to")
        self.cmb_u = _combo([(k, UNIT_SHORT[k]) for k in G.UNITS],
                            {"tp": "T = timepoints from the baseline (T=0 is the baseline, as on "
                                   "the graph's time axis).",
                             "min": "Minutes from the baseline.",
                             "frame": "The movie's own frame number (1 = first frame)."})
        for w in (self.cmb_comp, self.cmb_a, self.lbl_over, self.cmb_b, self.cmb_m, self.cmb_t,
                  self.sp1, self.lbl_to, self.sp2, self.cmb_u):
            lay.addWidget(w)
        for c in (self.cmb_comp, self.cmb_a, self.cmb_b, self.cmb_m, self.cmb_t, self.cmb_u):
            c.currentIndexChanged.connect(lambda _i: self._update())
        self.extra = QHBoxLayout()
        self.extra.setSpacing(3)
        lay.addLayout(self.extra)
        lay.addStretch(1)
        what = {"Y": "the Y axis (up)", "X": "the X axis (across) - or Time",
                "Z": "the third thing: shown as colour or as bins (groups)"}[role]
        tip(self.cmb_comp, f"Where it is measured, for {what}. 'nuclear/cytoplasmic'-style "
                           "ratios: type them in the sentence box.", title="Compartment")
        tip(self.cmb_a, "The channel (for a ratio: channel A, the top of A/B).", title="Channel")
        tip(self.cmb_b, "Channel B (the bottom of the ratio A/B).", title="Channel B")
        tip(self.cmb_m, "What is measured - hover each entry for what it is.", title="Measure")
        tip(self.cmb_t, "Which time: the full trace, one time, or one number over a window "
                        "(mean / max / min / area under the curve / slope).", title="Time",
            pic="graphs_time")
        tip(self.sp1, "The time (or the window's start). T=0 is the baseline; 'start' = the "
                      "first frame.", title="From")
        tip(self.sp2, "The window's end; 'end' = the last frame.", title="To")
        self._apply_visibility()

    # ------------------------------------------------------------------ options
    def set_options(self, comps: Sequence[str], channels: Sequence[str]) -> None:
        cur = self.quantity()
        self._busy = True
        first = {"X": [("time", "Time")], "Z": [("", "none")]}.get(self.role, [])
        self.cmb_comp.clear()
        for k, t in first:
            self.cmb_comp.addItem(t, k)
        for c in comps:
            self.cmb_comp.addItem(G.COMP_ADJ.get(c, c), c)
        for cmb in (self.cmb_a, self.cmb_b):
            cmb.clear()
            for ch in channels:
                cmb.addItem(ch, ch)
        self._busy = False
        self.set_quantity(cur)

    def quantity(self) -> Optional[G.Quantity]:
        comp = self.cmb_comp.currentData()
        if not comp or comp == "time":
            return None
        m = self.cmb_m.currentData() or "mean"
        need = G.MEASURES.get(m, ("", 1))[1]
        a, b = self.cmb_a.currentData() or "", self.cmb_b.currentData() or ""
        chan = "" if need == 0 else (f"{a}/{b}" if need == 2 else a)
        t = self.cmb_t.currentData() or "trace"
        v1 = None if self.sp1.value() <= NO_T else float(self.sp1.value())
        v2 = None if self.sp2.value() <= NO_T else float(self.sp2.value())
        if t == "at" and v1 is None:
            v1 = 0.0
        if t in ("trace", "end"):
            v1 = v2 = None
        if t == "at":
            v2 = None
        return G.Quantity(comp=comp, chan=chan, measure=m, time=t, t1=v1, t2=v2,
                          unit=self.cmb_u.currentData() or "tp",
                          comp2=getattr(self, "_comp2", ""))

    def set_quantity(self, q: Optional[G.Quantity]) -> None:
        self._busy = True
        try:
            if q is None:
                self.cmb_comp.setCurrentIndex(0)
                self._comp2 = ""
            else:
                if self.cmb_comp.findData(q.comp) < 0 and q.comp:
                    self.cmb_comp.addItem(G.COMP_ADJ.get(q.comp, q.comp), q.comp)
                _set(self.cmb_comp, q.comp)
                self._comp2 = q.comp2
                chs = q.channels()
                for cmb, ch in zip((self.cmb_a, self.cmb_b), chs):
                    if cmb.findData(ch) < 0:
                        cmb.addItem(ch, ch)
                    _set(cmb, ch)
                if q.measure in ("ratio", "rr0") and len(chs) < 2 and self.cmb_b.count() > 1:
                    self.cmb_b.setCurrentIndex(1 if self.cmb_a.currentIndex() == 0 else 0)
                _set(self.cmb_m, q.measure)
                _set(self.cmb_t, q.time)
                _set(self.cmb_u, q.unit)
                self.sp1.setValue(NO_T if q.t1 is None else q.t1)
                self.sp2.setValue(NO_T if q.t2 is None else q.t2)
        finally:
            self._busy = False
        self._apply_visibility()

    def _apply_visibility(self) -> None:
        comp = self.cmb_comp.currentData()
        on = bool(comp) and comp != "time"
        m = self.cmb_m.currentData()
        need = G.MEASURES.get(m, ("", 1))[1]
        t = self.cmb_t.currentData()
        self.cmb_m.setVisible(on)
        self.cmb_t.setVisible(on)
        self.cmb_a.setVisible(on and need >= 1)
        self.lbl_over.setVisible(on and need == 2)
        self.cmb_b.setVisible(on and need == 2)
        self.sp1.setVisible(on and t not in ("trace", "end"))
        win = on and t in G.WINDOW_TIMES
        self.lbl_to.setVisible(win)
        self.sp2.setVisible(win)
        self.cmb_u.setVisible(on and t not in ("trace", "end"))
        if t == "at":
            self.sp1.setSpecialValueText("")
            self.sp1.setMinimum(-100000 + 1)
        else:
            self.sp1.setMinimum(NO_T)
            self.sp1.setSpecialValueText("start")

    def _update(self) -> None:
        if self._busy:
            return
        if self.cmb_comp.currentData() != getattr(self, "_last_comp", None):
            self._comp2 = ""
        self._last_comp = self.cmb_comp.currentData()
        self._apply_visibility()
        self._emit()

    def _emit(self) -> None:
        if not self._busy:
            self.changed.emit()


class Chip(QToolButton):
    """A removable condition: its text and a ✕ (click = remove)."""

    def __init__(self, text: str, on_remove, tiptext: str = "") -> None:
        super().__init__()
        self.setText(text + "  ✕")
        self.setAutoRaise(False)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("QToolButton{border:1px solid #8AA4C8;border-radius:10px;"
                           "padding:1px 8px;}")
        self.clicked.connect(on_remove)
        tip(self, tiptext or "A condition: only cells that meet it are plotted. Click to "
                             "remove it.", title="Condition", pic="graphs_filter")


class GraphBuilder(QWidget):
    cell_clicked = Signal(str, int)
    spec_changed = Signal(object)

    def __init__(self, parent=None, multi_run: bool = False) -> None:
        super().__init__(parent)
        self.multi_run = multi_run
        self._runs: List[G.RunData] = []
        self._spec: Optional[G.GraphSpec] = None
        self._result: Optional[G.Result] = None
        self._run_colours: Dict[str, str] = {}
        self._drift_window = G.DEFAULT_SLOPE
        self._busy = False
        self._pts = (np.zeros(0), np.zeros(0), [])
        self._raw = (np.zeros(0), np.zeros(0))
        self._bar = None
        self.last_draw_ms = 0.0
        self.last_compute_ms = 0.0
        pg.setConfigOption("background", "w")
        pg.setConfigOption("foreground", "k")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        # --- the sentence
        self.ed = QLineEdit()
        self.ed.setPlaceholderText("Type a graph, e.g.  F/F0 GFP vs time   or   R/R0 nuclear "
                                   "Cy5/GFP vs cytoplasmic mCherry binned by summed DAPI at T=0")
        self.ed.setClearButtonEnabled(True)
        tip(self.ed, "Type what to plot, like a sentence: <b>Y vs X</b> (X can be <i>time</i>), "
                     "and optionally <b>vs Z</b> (colour), <b>binned by Z</b> (groups) - at most "
                     "three things. Times: <b>T=30</b> = 30 timepoints after the baseline "
                     "(<b>T=0</b> is the baseline, as on the time axis), <b>at 30 min</b>, "
                     "<b>frame 12</b>, <b>max</b>, <b>mean over T=0..10</b>. Conditions: "
                     "<b>where</b> summed nuclear DAPI at T=0 &gt; 2e6. Options: per run, SEM, "
                     "log y, spearman, trajectories. Press Enter; the rows below follow.",
            title="Graph sentence", pic="graphs_binned")
        self._model = QStringListModel(self)
        self._completer = QCompleter(self._model, self)
        self._completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._completer.setCompletionMode(QCompleter.UnfilteredPopupCompletion)
        self._completer.setMaxVisibleItems(10)
        self.ed.setCompleter(self._completer)
        self.ed.textEdited.connect(self._typed)
        self.ed.returnPressed.connect(self._parse_now)
        self.btn_star = QToolButton()
        self.btn_star.setText("☆")
        self.btn_star.setCheckable(True)
        self.btn_star.clicked.connect(self._star)
        tip(self.btn_star, "Keep this graph as a favourite (★): it stays in the list on the "
                           "right and in 'Graphs ▾', for one-click switching.", title="Favourite")
        self.menu_graphs = QMenu(self)
        self.menu_graphs.aboutToShow.connect(self._fill_graphs_menu)
        self.btn_graphs = QToolButton()
        self.btn_graphs.setText("Graphs ▾")
        self.btn_graphs.setPopupMode(QToolButton.InstantPopup)
        self.btn_graphs.setMenu(self.menu_graphs)
        tip(self.btn_graphs, "Your favourite graphs (★) and the recent ones - click to show it "
                             "again.", title="Saved graphs")
        top = QHBoxLayout()
        top.setSpacing(4)
        top.addWidget(self.ed, 1)
        top.addWidget(self.btn_star)
        top.addWidget(self.btn_graphs)
        lay.addLayout(top)
        self.lbl_issue = QLabel("")
        self.lbl_issue.setWordWrap(True)
        self.lbl_issue.setTextFormat(Qt.RichText)
        self.lbl_issue.setVisible(False)
        lay.addWidget(self.lbl_issue)
        # --- recent strip
        self.recent_row = QHBoxLayout()
        self.recent_row.setSpacing(3)
        self.lbl_recent = QLabel("Recent:")
        self.lbl_recent.setProperty("role", "muted")
        self.recent_row.addWidget(self.lbl_recent)
        self._recent_btns: List[QToolButton] = []
        self.recent_row.addStretch(1)
        lay.addLayout(self.recent_row)
        # --- the three rows
        self.row_y, self.row_x, self.row_z = (QuantityRow(r) for r in ("Y", "X", "Z"))
        self.btn_swap_xy = self._small("⇅", "Swap X and Y.", lambda: self.swap("xy"))
        self.btn_swap_xz = self._small("⇅", "Swap X and Z.", lambda: self.swap("xz"))
        self.row_x.extra.addWidget(self.btn_swap_xy)
        self.cmb_xbins = _combo([("", "no bins"), ("count", "bins (equal n)"),
                                 ("width", "bins (equal width)")],
                                tiptext="X in bins: the cells are put into groups by their X "
                                        "value and the mean Y of each group is drawn (with the "
                                        "error you chose).")
        tip(self.cmb_xbins, "Mean Y per X bin: the cells are sorted by X into bins (equal number "
                            "of cells, or equal width), and each bin's mean Y ± error is drawn.",
            title="X in bins", pic="graphs_xbins")
        self.sp_xbins = QSpinBox()
        self.sp_xbins.setRange(2, 50)
        self.sp_xbins.setValue(5)
        self.sp_xbins.setSuffix(" bins")
        self.row_x.extra.addWidget(self.cmb_xbins)
        self.row_x.extra.addWidget(self.sp_xbins)
        self.row_z.extra.addWidget(self.btn_swap_xz)
        self.cmb_zmode = _combo([("colour", "as colour"), ("bins", "in bins")])
        tip(self.cmb_zmode, "As colour: every cell coloured by its Z value (a colour bar shows "
                            "the scale). In bins: the cells are split into groups by Z, each "
                            "group drawn as its mean ± error in its own colour.",
            title="Z: colour or bins", pic="graphs_colour")
        self.cmb_zkind = _combo([("count", "equal n"), ("width", "equal width"),
                                 ("custom", "my cut-offs")])
        tip(self.cmb_zkind, "Equal n: each bin holds the same number of cells (terciles, "
                            "quartiles ...). Equal width: the Z range cut into equal steps. My "
                            "cut-offs: type the values between the bins (e.g. 1e6, 2e6).",
            title="How to bin", pic="graphs_binned")
        self.sp_zn = QSpinBox()
        self.sp_zn.setRange(2, 20)
        self.sp_zn.setValue(3)
        self.sp_zn.setSuffix(" bins")
        self.ed_cuts = QLineEdit()
        self.ed_cuts.setPlaceholderText("e.g. 1e6, 2e6")
        self.ed_cuts.setMaximumWidth(120)
        tip(self.ed_cuts, "The values between the bins, separated by commas: '1e6, 2e6' makes "
                          "three bins: below 1e6, 1e6 to 2e6, above 2e6.", title="Cut-offs")
        for w in (self.cmb_zmode, self.cmb_zkind, self.sp_zn, self.ed_cuts):
            self.row_z.extra.addWidget(w)
        for r in (self.row_y, self.row_x, self.row_z):
            r.changed.connect(self._rows_changed)
            lay.addWidget(r)
        for c in (self.cmb_xbins, self.cmb_zmode, self.cmb_zkind):
            c.currentIndexChanged.connect(lambda _i: self._rows_changed())
        for s in (self.sp_xbins, self.sp_zn):
            s.valueChanged.connect(lambda _v: self._rows_changed())
        self.ed_cuts.editingFinished.connect(self._rows_changed)
        # --- conditions
        self.chips = QHBoxLayout()
        self.chips.setSpacing(4)
        self.lbl_cond = QLabel("Cells:")
        self.chips.addWidget(self.lbl_cond)
        self._chip_widgets: List[QWidget] = []
        self.btn_add_cond = QToolButton()
        self.btn_add_cond.setText("+ condition")
        self.btn_add_cond.setPopupMode(QToolButton.InstantPopup)
        self.menu_cond = QMenu(self)
        self.ed_cond = QLineEdit()
        self.ed_cond.setMinimumWidth(320)
        self.ed_cond.setPlaceholderText("e.g. summed nuclear DAPI at T=0 > 2e6")
        self.ed_cond.returnPressed.connect(self._add_condition_typed)
        wa = QWidgetAction(self.menu_cond)
        wa.setDefaultWidget(self.ed_cond)
        self.menu_cond.addAction(wa)
        self.menu_cond.aboutToShow.connect(lambda: QTimer.singleShot(0, self.ed_cond.setFocus))
        self.btn_add_cond.setMenu(self.menu_cond)
        tip(self.btn_add_cond, "Add a condition: only cells that meet it are plotted, e.g. "
                               "<b>summed nuclear DAPI at T=0 &gt; 2e6</b>, <b>nuclear GFP x "
                               "background at T=0 &gt; 3</b>, <b>F/F0 GFP max between 1.2 and "
                               "5</b>, <b>condition = U2OS</b>. Type it and press Enter.",
            title="Conditions", pic="graphs_filter")
        self.chips.addWidget(self.btn_add_cond)
        self.chips.addStretch(1)
        lay.addLayout(self.chips)
        # --- the plot
        self.plot = pg.PlotWidget(background="w")
        self.plot.setMenuEnabled(False)
        self.plot.showGrid(x=False, y=False)
        for ax in ("left", "bottom"):
            self.plot.getAxis(ax).enableAutoSIPrefix(False)
            _readable_ticks(self.plot.getAxis(ax))
            self.plot.getAxis(ax).setPen(pg.mkPen("k"))
            self.plot.getAxis(ax).setTextPen(pg.mkPen("k"))
        self.legend = self.plot.addLegend(offset=(-10, 10), brush=pg.mkBrush(255, 255, 255, 200))
        self.plot.setMinimumHeight(180)
        self.plot.scene().sigMouseMoved.connect(self._hover)
        self.plot.scene().sigMouseClicked.connect(self._clicked)
        lay.addWidget(self.plot, 1)
        # --- bottom line
        bot = QHBoxLayout()
        bot.setSpacing(6)
        self.lbl_read = QLabel("Hover a point for its cell and values; click it to show the "
                               "cell.")
        self.lbl_read.setProperty("role", "muted")
        self.lbl_read.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.lbl_info = QLabel("")
        self.lbl_info.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        bot.addWidget(self.lbl_read, 3)
        bot.addWidget(self.lbl_info, 2)
        self.menu_opts = QMenu(self)
        self.menu_opts.setToolTipsVisible(True)
        self._build_options()
        self.btn_opts = QToolButton()
        self.btn_opts.setText("Options ▾")
        self.btn_opts.setPopupMode(QToolButton.InstantPopup)
        self.btn_opts.setMenu(self.menu_opts)
        tip(self.btn_opts, "Error (SD / SEM / 95% CI), each cell shown or not, log axes, "
                           "correlation, how runs are split, and the drift-correction add-on.",
            title="Options")
        self.menu_export = QMenu(self)
        for text, ext in (("Picture (PNG)...", ".png"), ("Picture (SVG)...", ".svg"),
                          ("Table (CSV)...", ".csv"), ("Table (Excel)...", ".xlsx")):
            self.menu_export.addAction(text, lambda e=ext: self._export_ask(e))
        self.btn_export = QToolButton()
        self.btn_export.setText("Export ▾")
        self.btn_export.setPopupMode(QToolButton.InstantPopup)
        self.btn_export.setMenu(self.menu_export)
        tip(self.btn_export, "Save the plot as a picture (PNG / SVG) or the plotted numbers as "
                             "a table (CSV / Excel) - the sentence and the conditions are written "
                             "on top. Nothing is overwritten.", title="Export")
        bot.addWidget(self.btn_opts)
        bot.addWidget(self.btn_export)
        bot.addWidget(help_button(
            "<b>Y vs X</b>: X = Time draws each cell's trace and the mean. One number per cell "
            "(e.g. <i>at T=30</i>, <i>max</i>) on both axes: one dot per cell. Two full traces: "
            "every timepoint of every cell as a dot coloured by time (or each cell's "
            "trajectory). <b>vs Z</b>: colour by a third thing; <b>binned by Z</b>: groups by "
            "it, each with its mean ± error.", title="How graphs are made", pic="graphs_shapes"))
        lay.addLayout(bot)
        # timers: parse after typing pauses, draw after changes settle, remember recents
        self._parse_timer = QTimer(self)
        self._parse_timer.setSingleShot(True)
        self._parse_timer.setInterval(700)
        self._parse_timer.timeout.connect(lambda: self._parse_now(quiet=True))
        self._draw_timer = QTimer(self)
        self._draw_timer.setSingleShot(True)
        self._draw_timer.setInterval(25)
        self._draw_timer.timeout.connect(self.redraw)
        self._recent_timer = QTimer(self)
        self._recent_timer.setSingleShot(True)
        self._recent_timer.setInterval(1500)
        self._recent_timer.timeout.connect(self._remember_recent)
        self._fit_timer = QTimer(self)
        self._fit_timer.setSingleShot(True)
        self._fit_timer.setInterval(0)
        self._fit_timer.timeout.connect(self.fit)
        import threading
        threading.Thread(target=G.warm_up, daemon=True).start()
        self._refresh_recent()
        self._set_split_visible()

    # ================================================================== helpers
    def _small(self, text, tiptext, fn) -> QToolButton:
        b = QToolButton()
        b.setText(text)
        b.clicked.connect(fn)
        tip(b, tiptext)
        return b

    def _build_options(self) -> None:
        m = self.menu_opts
        m.clear()
        self._opt_actions = {}

        def radio(title, key, choices, tips=None):
            sub = m.addMenu(title)
            sub.setToolTipsVisible(True)
            acts = {}
            for val, text in choices:
                a = sub.addAction(text)
                a.setCheckable(True)
                if tips and val in tips:
                    a.setToolTip(tips[val])
                a.triggered.connect(lambda _c=False, k=key, v=val: self._set_opt(k, v))
                acts[val] = a
            self._opt_actions[key] = acts
            return sub

        radio("Error", "error", [("SD", "mean ± SD"), ("SEM", "mean ± SEM"),
                                 ("95% CI", "mean ± 95% CI"), ("none", "mean only")],
              {"SD": "The spread of the cells (SD, n - 1).",
               "SEM": "How sure the mean is: SD / sqrt(n).",
               "95% CI": "t(0.975, n - 1) x SEM."})
        for key, text, tiptext in (
                ("show_cells", "Show each cell", "Each cell's trace or dot (off: only the means)."),
                ("show_mean", "Show the means", "The mean ± error of each group / bin."),
                ("log_x", "Log X axis", "X on a log scale (values ≤ 0 are left out)."),
                ("log_y", "Log Y axis", "Y on a log scale (values ≤ 0 are left out)."),
                ("included_only", "Included cells only",
                 "Only the cells you included (untick to also plot the excluded ones).")):
            a = m.addAction(text)
            a.setCheckable(True)
            a.setToolTip(tiptext)
            a.triggered.connect(lambda c, k=key: self._set_opt(k, bool(c)))
            self._opt_actions[key] = a
        radio("Correlation", "corr", [("pearson", "Pearson r"), ("spearman", "Spearman rho"),
                                      ("none", "none")],
              {"pearson": "Straight-line correlation (-1 .. 1).",
               "spearman": "Rank correlation: any rising / falling relation (-1 .. 1)."})
        radio("Two traces", "pairs", [("points", "every timepoint, coloured by time"),
                                      ("trajectories", "each cell's trajectory")],
              {"points": "Every (cell, timepoint) as a dot, coloured by time.",
               "trajectories": "Each cell as a line through its timepoints, in time order."})
        self.menu_split = radio("Runs", "split", [("pool", "pooled (one colour)"),
                                                  ("run", "colour by run"),
                                                  ("condition", "colour by condition"),
                                                  ("group", "colour by group")],
                                {"pool": "Every run's cells together as one group.",
                                 "run": "Each run its own colour and mean.",
                                 "condition": "Runs of one condition (cell line) together.",
                                 "group": "Runs of one replicate group together."})
        m.addSeparator()
        a = m.addAction("Add-on: drift correction")
        a.setCheckable(True)
        a.setToolTip("Optional add-on (off by default): each cell's straight-line drift through "
                      "the drift frames (the Check page's 'drift slope' window) is taken out of "
                      "its trace before anything is plotted.")
        a.triggered.connect(lambda c: self._set_opt("drift", self._drift_window if c else None))
        self._opt_actions["drift"] = a

    def _set_split_visible(self) -> None:
        self.menu_split.menuAction().setVisible(self.multi_run or len(self._runs) > 1)

    def _sync_options(self) -> None:
        s = self._spec
        if s is None:
            return
        for key, acts in self._opt_actions.items():
            if isinstance(acts, dict):
                for v, a in acts.items():
                    a.setChecked(getattr(s, key) == v)
            elif key == "drift":
                acts.setChecked(bool(s.drift))
            else:
                acts.setChecked(bool(getattr(s, key)))

    def _set_opt(self, key, value) -> None:
        if self._spec is None:
            return
        self.set_spec(replace(self._spec, **{key: value}))

    # ================================================================== API
    def set_runs(self, runs: Sequence[G.RunData], keep_spec: bool = True) -> None:
        self._runs = [r for r in runs if r is not None]
        comps = [c for c in G.COMPS if any(c in r.meas for r in self._runs)]
        chans: List[str] = []
        for r in self._runs:
            chans += [c for c in r.channels if c not in chans]
        self._comps, self._chans = comps, chans
        for row in (self.row_y, self.row_x, self.row_z):
            row.set_options(comps, chans)
        self._set_split_visible()
        many = len(self._runs) > 1
        if self._spec is not None and keep_spec and many != getattr(self, "_many", many)                 and self._spec.x is None:
            # from one run to several (or back): per-cell lines only for a single run
            self._spec = replace(self._spec, show_cells=not many)
            self._sync_options()
        self._many = many
        if self._spec is None or not keep_spec:
            self.set_spec(default_spec(self._runs), record=False)
        else:
            self._apply_spec_to_rows()
            self._schedule_draw()

    def runs(self) -> List[G.RunData]:
        return list(self._runs)

    def spec(self) -> Optional[G.GraphSpec]:
        return self._spec

    def result(self) -> Optional[G.Result]:
        return self._result

    def sentence(self) -> str:
        return P.sentence(self._spec) if self._spec else ""

    def set_run_colours(self, colours: Dict[str, str]) -> None:
        self._run_colours = dict(colours or {})
        self._schedule_draw()

    def set_drift_window(self, a: int, b: int) -> None:
        self._drift_window = (int(min(a, b)), int(max(a, b)))
        if self._spec is not None and self._spec.drift:
            self.set_spec(replace(self._spec, drift=self._drift_window))

    def set_spec(self, spec: Optional[G.GraphSpec], record: bool = True,
                 keep_text: bool = False) -> None:
        if spec is None:
            return
        # 4.0 integration: the rows SHOW what is used - e.g. X taken 'at T=30' like Y
        # (the shape rules of graphbuilder.effective), never 'trace' with a footnote
        # saying otherwise
        try:
            y, x, z, _n = G.effective(spec)
            if (y, x, z) != (spec.y, spec.x, spec.z):
                spec = replace(spec, y=y, x=x, z=z)
        except Exception:                                          # noqa: BLE001
            pass
        self._spec = spec
        self._apply_spec_to_rows()
        if not keep_text:
            self.ed.setText(P.sentence(spec))
            self.lbl_issue.setVisible(False)
        self._sync_options()
        self._schedule_draw()
        self.spec_changed.emit(spec)
        if record:
            self._recent_timer.start()

    def set_sentence(self, text: str) -> P.Parsed:
        self.ed.setText(text)
        return self._parse_now()

    # ================================================================== typing
    def _typed(self, text: str) -> None:
        self._model.setStringList(P.complete(text, self._chans or [], self._comps or G.COMPS))
        self._parse_timer.start()

    def _parse_now(self, quiet: bool = False) -> P.Parsed:
        self._parse_timer.stop()
        text = self.ed.text()
        p = P.parse(text, self._chans or [], self._comps or G.COMPS, base=self._spec)
        shown = [i for i in p.issues if i.message]
        if shown:
            msgs = "<br>".join(i.message for i in shown[:3])
            self.lbl_issue.setText(P.highlight_html(text, p.issues) + "<br><span style="
                                   "'color:#666'>" + msgs + "</span>")
            self.lbl_issue.setVisible(True)
        else:
            self.lbl_issue.setVisible(False)
        if p.spec is not None and (p.ok or not quiet):
            self.set_spec(p.spec, keep_text=True)
        return p

    # ================================================================== rows
    def _apply_spec_to_rows(self) -> None:
        s = self._spec
        if s is None:
            return
        self._busy = True
        try:
            self.row_y.set_quantity(s.y)
            self.row_x.set_quantity(s.x)
            self.row_z.set_quantity(s.z)
            _set(self.cmb_xbins, s.x_bins.kind if s.x_bins else "")
            if s.x_bins:
                self.sp_xbins.setValue(max(2, s.x_bins.n))
            _set(self.cmb_zmode, s.z_mode)
            _set(self.cmb_zkind, s.z_bins.kind)
            self.sp_zn.setValue(max(2, s.z_bins.n))
            self.ed_cuts.setText(", ".join(f"{c:g}" for c in s.z_bins.cuts))
        finally:
            self._busy = False
        self._extras_visibility()
        self._rebuild_chips()

    def _extras_visibility(self) -> None:
        xq = self.row_x.quantity()
        zq = self.row_z.quantity()
        self.cmb_xbins.setVisible(xq is not None)
        self.sp_xbins.setVisible(xq is not None and bool(self.cmb_xbins.currentData()))
        self.btn_swap_xy.setVisible(xq is not None)
        self.btn_swap_xz.setVisible(zq is not None)
        on = zq is not None
        self.cmb_zmode.setVisible(on)
        bins = on and self.cmb_zmode.currentData() == "bins"
        self.cmb_zkind.setVisible(bins)
        self.sp_zn.setVisible(bins and self.cmb_zkind.currentData() != "custom")
        self.ed_cuts.setVisible(bins and self.cmb_zkind.currentData() == "custom")

    def _rows_changed(self) -> None:
        if self._busy or self._spec is None:
            return
        y = self.row_y.quantity()
        if y is None:
            return
        cuts = ()
        if self.cmb_zkind.currentData() == "custom":
            try:
                cuts = tuple(sorted(P._fnum(v) for v in self.ed_cuts.text().replace(";", ",")
                                    .split(",") if v.strip()))
            except ValueError:
                cuts = self._spec.z_bins.cuts
        zb = G.BinSpec(self.cmb_zkind.currentData() or "count",
                       len(cuts) + 1 if cuts else self.sp_zn.value(), cuts)
        xk = self.cmb_xbins.currentData()
        xb = G.BinSpec(xk, self.sp_xbins.value()) if xk else None
        sp = replace(self._spec, y=y, x=self.row_x.quantity(), z=self.row_z.quantity(),
                     z_mode=self.cmb_zmode.currentData() or "colour", z_bins=zb, x_bins=xb)
        self._extras_visibility()
        self.set_spec(sp)

    def swap(self, which: str) -> None:
        s = self._spec
        if s is None:
            return
        if which == "xy" and s.x is not None:
            self.set_spec(replace(s, x=s.y, y=s.x))
        elif which == "xz" and s.z is not None:
            if s.x is None:
                self.set_spec(replace(s, x=s.z, z=None))
            else:
                self.set_spec(replace(s, x=s.z, z=s.x))

    # ================================================================== chips
    def _rebuild_chips(self) -> None:
        for w in self._chip_widgets:
            self.chips.removeWidget(w)
            w.hide()
            w.deleteLater()
        self._chip_widgets = []
        s = self._spec
        if s is None:
            return
        pos = 1
        inc = Chip("included cells only" if s.included_only else "all cells (also excluded)",
                   lambda *_a: self._set_opt("included_only", not self._spec.included_only),
                   "Which cells: only the ones you included (default), or all of them. Click "
                   "to switch.")
        self.chips.insertWidget(pos, inc)
        self._chip_widgets.append(inc)
        for i, f in enumerate(s.filters):
            pos += 1
            c = Chip(P.filter_text(f), lambda _c=False, i=i: self.remove_filter(i))
            self.chips.insertWidget(pos, c)
            self._chip_widgets.append(c)

    def add_filter(self, f: G.Filter) -> None:
        if self._spec is not None:
            self.set_spec(replace(self._spec, filters=tuple(self._spec.filters) + (f,)))

    def remove_filter(self, i: int) -> None:
        if self._spec is not None and 0 <= i < len(self._spec.filters):
            fl = list(self._spec.filters)
            fl.pop(i)
            self.set_spec(replace(self._spec, filters=tuple(fl)))

    def _add_condition_typed(self) -> None:
        issues: List[P.Issue] = []
        f = P.parse_filter(self.ed_cond.text(), 0, self._chans, self._comps or G.COMPS, issues)
        errs = [i for i in issues if i.level == "error"]
        if f is None or errs:
            self.ed_cond.setToolTip("<br>".join(i.message for i in errs) or "Not understood.")
            self.ed_cond.setStyleSheet("QLineEdit{border:1px solid #C00000;}")
            return
        self.ed_cond.setStyleSheet("")
        self.ed_cond.clear()
        self.menu_cond.hide()
        self.add_filter(f)

    # ================================================================== recipes
    def _remember_recent(self) -> None:
        if self._spec is not None and self._result is not None and not self._result.error:
            G.add_recent(self.sentence(), self._spec)
            self._refresh_recent()

    def _refresh_recent(self) -> None:
        for b in self._recent_btns:
            self.recent_row.removeWidget(b)
            b.hide()
            b.deleteLater()
        self._recent_btns = []
        d = G.load_recipes()
        items = [("★ " + r.get("name", r.get("sentence", "")), r) for r in d["favourites"]]
        cur = self.sentence()
        items += [(r.get("sentence", ""), r) for r in d["recent"]
                  if r.get("sentence") != cur and
                  not any(f.get("sentence") == r.get("sentence") for f in d["favourites"])]
        for text, r in items[:6]:
            b = QToolButton()
            short = text if len(text) <= 34 else text[:32] + "…"
            b.setText(short)
            b.setAutoRaise(True)
            tip(b, r.get("sentence", ""), title="Show this graph again")
            b.clicked.connect(lambda _c=False, r=r: self.open_recipe(r))
            self.recent_row.insertWidget(1 + len(self._recent_btns), b)
            self._recent_btns.append(b)
        self.lbl_recent.setVisible(bool(self._recent_btns))
        self.btn_star.setChecked(G.is_favourite(cur) if cur else False)
        self.btn_star.setText("★" if self.btn_star.isChecked() else "☆")

    def open_recipe(self, r: dict) -> None:
        sp = G.GraphSpec.from_dict(r.get("spec"))
        if sp is not None:
            self.set_spec(sp)
        elif r.get("sentence"):
            self.set_sentence(r["sentence"])

    def _star(self) -> None:
        cur = self.sentence()
        if not cur or self._spec is None:
            return
        if G.is_favourite(cur):
            d = G.load_recipes()
            for r in d["favourites"]:
                if r.get("sentence") == cur:
                    G.remove_favourite(r.get("name", ""))
        else:
            G.save_favourite(cur, cur, self._spec)
        self._refresh_recent()

    def _fill_graphs_menu(self) -> None:
        m = self.menu_graphs
        m.clear()
        d = G.load_recipes()
        if d["favourites"]:
            m.addSection("Favourites")
            for r in d["favourites"]:
                m.addAction("★ " + r.get("name", ""), lambda r=r: self.open_recipe(r))
        if d["recent"]:
            m.addSection("Recent")
            for r in d["recent"]:
                m.addAction(r.get("sentence", ""), lambda r=r: self.open_recipe(r))
        if not d["favourites"] and not d["recent"]:
            a = m.addAction("(none yet - every graph you make is listed here)")
            a.setEnabled(False)

    # ================================================================== drawing
    def _schedule_draw(self) -> None:
        self._draw_timer.start()

    def resizeEvent(self, e) -> None:                               # noqa: N802
        super().resizeEvent(e)
        self._fit_timer.start()

    def fit(self) -> None:
        """Show everything (after every change and every resize)."""
        vb = self.plot.getPlotItem().getViewBox()
        vb.enableAutoRange(pg.ViewBox.XYAxes, True)
        vb.autoRange(padding=0.04)

    def redraw(self) -> None:
        self._draw_timer.stop()
        s = self._spec
        pi = self.plot.getPlotItem()
        t0 = time.perf_counter()
        if s is None:
            return
        res = G.compute(self._runs, s, run_colours=self._run_colours)
        t1 = time.perf_counter()
        self._result = res
        pi.clear()
        if self._bar is not None:
            try:
                pi.layout.removeItem(self._bar)
            except Exception:                                  # noqa: BLE001
                pass
            self._bar.hide()
            self._bar = None
        self._pts = (np.zeros(0), np.zeros(0), [])
        self._raw = (np.zeros(0), np.zeros(0))
        lx, ly = s.log_x, s.log_y
        fx = _log if lx else (lambda v: np.asarray(v, float))
        fy = _log if ly else (lambda v: np.asarray(v, float))
        for ax, on in (("bottom", lx), ("left", ly)):
            try:
                pi.getAxis(ax).setLogMode(on)
            except TypeError:
                pi.getAxis(ax).setLogMode(on, on)
        pi.setLabel("bottom", res.x_label)
        self.lbl_read.setText("Hover a point for its cell and values; click it to show the "
                              "cell.")
        pi.setLabel("left", res.y_label)
        if res.error:
            self.lbl_info.setText(res.error)
            self.lbl_info.setStyleSheet("color:#C00000;")
            self._after_draw(t0, t1)
            return
        self.lbl_info.setStyleSheet("")
        brushes: Dict[str, object] = {}

        def brush(c):
            b = brushes.get(c)
            if b is None:
                b = brushes[c] = pg.mkBrush(c)
            return b
        shape = res.shape
        if s.show_cells and res.cells:
            if shape in ("traces",) or (shape == "pairs" and s.pairs == "trajectories"):
                by_col: Dict[str, List] = {}
                for c in res.cells:
                    by_col.setdefault(c.colour, []).append(c)
                width = 1.0 if len(res.cells) > 40 else 1.4
                for col, cs in by_col.items():
                    xs = np.concatenate([np.append(fx(c.x), np.nan) for c in cs])
                    ys = np.concatenate([np.append(fy(c.y), np.nan) for c in cs])
                    pen = pg.mkPen(col, width=width)
                    if shape == "traces" and (s.show_mean and res.groups):
                        q = pg.mkColor(col)
                        q.setAlpha(110)
                        pen = pg.mkPen(q, width=width)
                    pi.addItem(pg.PlotDataItem(xs, ys, pen=pen, connect="finite"))
            else:
                xs = np.concatenate([fx(c.x) for c in res.cells])
                ys = np.concatenate([fy(c.y) for c in res.cells])
                cols: List[str] = []
                for c in res.cells:
                    cols += c.colours if c.colours is not None else [c.colour] * len(c.x)
                ok = np.isfinite(xs) & np.isfinite(ys)
                size = 7 if shape != "pairs" else 5
                pi.addItem(pg.ScatterPlotItem(xs[ok], ys[ok], size=size, pen=pg.mkPen(None),
                                              brush=[brush(cl) for cl, k in zip(cols, ok) if k]))
            px, py, meta = res.points()
            self._pts = (fx(px), fy(py), meta)
            self._raw = (px, py)
        if s.show_mean or not s.show_cells:
            for g in res.groups:
                gx, gy = fx(g.x), fy(g.y)
                lo, hi = fy(g.y - g.yerr), fy(g.y + g.yerr)
                if shape == "traces":
                    if s.error != "none" and len(g.x) > 1:
                        c1 = pg.PlotDataItem(gx, lo, pen=pg.mkPen(None), connect="finite")
                        c2 = pg.PlotDataItem(gx, hi, pen=pg.mkPen(None), connect="finite")
                        fc = pg.mkColor(g.colour)
                        fc.setAlpha(60)
                        pi.addItem(c1)
                        pi.addItem(c2)
                        pi.addItem(pg.FillBetweenItem(c1, c2, brush=pg.mkBrush(fc)))
                    pi.addItem(pg.PlotDataItem(gx, gy, pen=pg.mkPen(g.colour, width=3),
                                               name=g.label, connect="finite"))
                else:
                    if shape == "pairs":         # the mean trajectory: a line, no bars
                        pi.addItem(pg.PlotDataItem(gx, gy, pen=pg.mkPen(g.colour, width=3),
                                                   symbol="o", symbolSize=5,
                                                   symbolBrush=g.colour, symbolPen=None,
                                                   name=g.label, connect="finite"))
                        continue
                    sym = "s" if g.kind == "marker" else "o"
                    pen = pg.mkPen(g.colour, width=2.4) if g.kind == "line" else None
                    if s.error != "none":
                        ex = g.xerr if len(g.xerr) == len(g.x) else np.zeros(len(g.x))
                        okk = np.isfinite(gx) & np.isfinite(gy)
                        pi.addItem(pg.ErrorBarItem(
                            x=gx[okk], y=gy[okk], top=(hi - gy)[okk], bottom=(gy - lo)[okk],
                            left=(gx - fx(g.x - ex))[okk],
                            right=(fx(g.x + ex) - gx)[okk], beam=0,
                            pen=pg.mkPen(g.colour, width=1.6)))
                    pi.addItem(pg.PlotDataItem(gx, gy, pen=pen, symbol=sym, symbolSize=12,
                                               symbolBrush=g.colour,
                                               symbolPen=pg.mkPen("k", width=1),
                                               name=g.label, connect="finite"))
        if res.colour_range is not None:
            self._colour_bar(res)
        info, full = [], []
        for g, m, r, p, n in res.corr:
            if np.isfinite(r):
                sym = 'ρ' if m == 'spearman' else 'r'
                full.append(f"{sym} = {r:.2f} (n = {n}"
                            + (f", p = {p:.2g}" if np.isfinite(p) else "") + ")"
                            + ("" if g in ("All cells",) or len(res.corr) == 1 else f" {g}"))
                if not info:                       # one short line; per bin in the hover
                    info.append(f"{sym} = {r:.2f} (n = {n})")
        cells = f"{res.n_cells} cells" + (f", {res.n_runs} runs" if res.n_runs > 1 else "")
        info.append(cells)
        self.lbl_info.setText(" · ".join(info))
        self.lbl_info.setToolTip("<br>".join(full + [cells] + res.notes))
        if res.notes:
            self.lbl_read.setText(res.notes[0])
        self._after_draw(t0, t1)

    def _after_draw(self, t0: float, t1: float) -> None:
        self.fit()
        self.last_compute_ms = (t1 - t0) * 1000
        self.last_draw_ms = (time.perf_counter() - t0) * 1000

    def _colour_bar(self, res: G.Result) -> None:
        lo, hi = res.colour_range
        if not (np.isfinite(lo) and np.isfinite(hi)):
            return
        pos = np.array([p for p, _c in G._RAMP])
        cols = np.array([c for _p, c in G._RAMP], dtype=np.ubyte)
        cmap = pg.ColorMap(pos, cols)
        try:
            bar = pg.ColorBarItem(values=(lo, hi if hi > lo else lo + 1), colorMap=cmap,
                                  interactive=False, label=_short_label(res.z_label), width=12)
            self.plot.getPlotItem().layout.addItem(bar, 2, 5)
            self._bar = bar
        except Exception:                                      # noqa: BLE001
            self._bar = None

    # ================================================================== hover / click
    def _nearest(self, scene_pos, max_px: float = 9.0):
        xs, ys, meta = self._pts
        if not len(xs):
            return None
        vb = self.plot.getPlotItem().getViewBox()
        if not vb.sceneBoundingRect().contains(scene_pos):
            return None
        p = vb.mapSceneToView(scene_pos)
        pw, ph = vb.viewPixelSize()
        if pw <= 0 or ph <= 0:
            return None
        d = ((xs - p.x()) / pw) ** 2 + ((ys - p.y()) / ph) ** 2
        d = np.where(np.isfinite(d), d, np.inf)
        i = int(np.argmin(d))
        if d[i] > max_px ** 2:
            return None
        return i

    def _hover(self, pos) -> None:
        i = self._nearest(pos)
        if i is None or self._result is None:
            return
        res = self._result
        key, name, k, t = self._pts[2][i]
        x, y = self._raw[0][i], self._raw[1][i]
        tt = ""
        if np.isfinite(t) and res.shape in ("traces", "pairs"):
            run = next((r for r in self._runs if r.key == key), None)
            tt = f", at {t:g} {'min' if run is None or run.minutes else 'T'}"
        c = next((c for c in res.cells if c.run == key and c.k == k), None)
        zz = ""
        if res.z is not None and c is not None and len(c.z) == 1:
            zz = f", Z = {_fmt(c.z[0])}"
        self.lbl_read.setText(f"Cell {k + 1}" + (f" ({name})" if len(self._runs) > 1 else "") +
                              f": X = {_fmt(x)}, Y = {_fmt(y)}{zz}{tt}")

    def _clicked(self, ev) -> None:
        i = self._nearest(ev.scenePos())
        if i is None:
            return
        key, _name, k, _t = self._pts[2][i]
        self.cell_clicked.emit(str(key), int(k))

    # ================================================================== export
    def _export_ask(self, ext: str) -> None:
        from PySide6.QtWidgets import QFileDialog
        start = str(Path.home() / f"graph{ext}")
        path, _f = QFileDialog.getSaveFileName(self, "Export the graph", start, f"*{ext}")
        if path:
            path = path if path.lower().endswith(ext) else path + ext
            out = self.export_image(path) if ext in (".png", ".svg") else self.export_table(path)
            self.lbl_read.setText(f"Saved: {out}")

    def export_image(self, path) -> str:
        """.png: the plot as shown (2x pixels); .svg / .pdf: the same graph drawn by
        matplotlib with the text kept as text (pyqtgraph's own SVG export fails on
        these plots). Never overwrites (adds _2 ...)."""
        from ..safety import new_output_file
        import pyqtgraph.exporters as EX
        p = Path(path)
        if p.suffix.lower() in (".svg", ".pdf"):
            if self._result is None:
                self.redraw()
            return G.save_figure(p, self._result, self._spec, title=self.sentence())
        ex = EX.ImageExporter(self.plot.getPlotItem())
        ex.parameters()["width"] = int(max(800, self.plot.width() * 2))
        img = ex.export(toBytes=True)
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.WriteOnly)
        img.save(buf, "PNG")
        with new_output_file(p.with_suffix(".png")) as (used, stream):
            stream.write(bytes(ba))
        return str(used)

    def export_table(self, path) -> str:
        G.warm_up()                                  # p values in the header
        self.redraw()
        return G.save_table(path, self.sentence(), self._spec, self._result)


# ====================================================================== helpers
def _log(v) -> np.ndarray:
    v = np.asarray(v, float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(v > 0, np.log10(np.where(v > 0, v, 1.0)), np.nan)


def _fmt(v) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "?"
    if not np.isfinite(v):
        return "-"
    a = abs(v)
    return f"{v:.4g}" if a == 0 or 1e-3 <= a < 1e6 else f"{v:.3e}"


def _short_label(text: str) -> str:
    return text if len(text) <= 40 else text[:38] + "…"


def _readable_ticks(axis) -> None:
    """4.0 integration: tick labels as '101k', '2.8M' instead of '1.01e+05' (log axes
    keep pyqtgraph's own labels)."""
    orig = axis.tickStrings

    def strings(values, scale, spacing):
        if getattr(axis, "logMode", False):
            return orig(values, scale, spacing)
        vals = [v * scale for v in values]
        if vals and max(abs(v) for v in vals) < 1e4:
            return orig(values, scale, spacing)
        return [G.human(v) for v in vals]
    axis.tickStrings = strings


def default_spec(runs: Sequence[G.RunData]) -> G.GraphSpec:
    """F/F0 of the first channel in the first compartment vs Time (or R/R0 A/B when
    the runs know a key quantity - the caller can set_spec its own)."""
    comps = [c for c in G.COMPS if any(c in r.meas for r in runs)] or ["nucleus"]
    chans: List[str] = []
    for r in runs:
        chans += [c for c in r.channels if c not in chans]
    ch = chans[0] if chans else "GFP"
    # 4.0 integration: several runs against Time - hundreds of thin per-cell lines blur
    # into one colour, so the mean +- SD of each run is the default (per-cell lines:
    # Options); one run keeps its per-cell lines
    many = len(runs) > 1
    return G.GraphSpec(y=G.Quantity(comp=comps[0], chan=ch, measure="ff0"),
                       show_cells=not many, split="run" if many else "pool")
