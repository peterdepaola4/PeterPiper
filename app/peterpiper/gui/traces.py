"""
The trace panel beside the image - the place to include / exclude cells, and
to choose how the graph will look when it is exported.

    View          'Check cells' = every cell in its own colour (the same as its
                  outline in the image), excluded ones light grey, blue = mean of
                  the included, shaded = SEM - for deciding which cells to keep.
                  'As exported' = the graph exactly as the PNG / SVG will look:
                  the INCLUDED cells only, in your graph style (Look, error type,
                  colours, titles, axis ranges, font size). A Prism (.prism) file
                  gets the same data, titles and look; choices marked * are things
                  Prism cannot draw (the .prism file gets the closest Prism look,
                  graphstyle.prism_look) and a note under the controls says so
                  whenever the look shown has one. 'Save this graph...' writes it
                  as files.
    Cell list     tick / untick 'Include' for each cell; click a row to find the
                  cell (its trace turns orange, its outline is highlighted)
    Plot          scroll = zoom, drag = move, 'Zoom box' = drag a rectangle,
                  'Reset zoom' = fit everything (or your fixed axis ranges);
                  hover a line to read its value; click a line to select its
                  cell, double-click to include / exclude it; click anywhere
                  else to jump the image to that time
    Orange line   the timepoint shown in the image (follows the slider / Play)

Every value is background-subtracted. Means, SEM, SD and 95% CI come from
graphstyle.stats - the same numbers as the exported graphs and tables.
"""
from __future__ import annotations

import html
import textwrap
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QMetaMethod, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QFontDatabase
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QColorDialog,
                               QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QMessageBox, QPushButton, QSizePolicy, QSplitter,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .. import graphstyle as GS
from ..config import Experiment
from ..graphstyle import GraphStyle
from ..measure import Measurements
from . import widgets as W
from .widgets import cell_colour

EXCLUDED = QColor(200, 200, 200, 150)
HILITE = QColor(255, 140, 0)
MEAN = QColor(0, 90, 220)

VIEW_CHECK = "check"
VIEW_EXPORTED = "exported"
VIEW_TEXT = {VIEW_CHECK: "Check cells", VIEW_EXPORTED: "As exported"}
CUSTOM = "Custom (your own look)"
PRISM_ITEM = "Load look from a Prism file..."
ERROR_TEXT = {"SEM": "SEM", "SD": "SD", "95% CI": "95% CI", "none": "None"}
ERROR_STYLE_TEXT = {"bars": "error bars", "band": "shaded band"}
SYMBOL_TEXT = {"circle": "Circle", "square": "Square", "triangle": "Triangle",
               "diamond": "Diamond", "none": "None (line only)"}
RANGE_FIELDS = ("x_min", "x_max", "y_min", "y_max", "font_pt", "show_cells", "show_mean",
                "error", "error_style")
PX = GS.PX_PER_PT


def _qt_family() -> str:
    """Arial when installed (as in the PNG / Prism), else the app's own font."""
    try:
        if GS.FONT_FAMILY in QFontDatabase.families():
            return GS.FONT_FAMILY
    except Exception:                               # noqa: BLE001
        pass
    return QFont().family()


def prism_mark(fields: Sequence[str], tip: str) -> Tuple[str, str]:
    """(' *' or '', tooltip) - says honestly whether Prism gets this choice."""
    sup = [GS.prism_support(f) for f in fields]
    if any(s == "no" for s in sup):
        notes = [GS.PRISM_FIELD_NOTE.get(f, "Not in the .prism file") for f in fields
                 if GS.prism_support(f) == "no"]
        return " *", f"{tip}\n\n* " + ". ".join(dict.fromkeys(notes)) + "."
    if any(s == "template" for s in sup):
        return "", f"{tip}\n\nPrism: comes from the matching Prism template."
    return "", f"{tip}\n\nPrism: written into the .prism file too."


# ---- "Load look from a Prism file..." (V2.4)
_KEPT_WORDS = {"show_mean": "show the mean", "baseline_line": "dashed line at time 0",
               "legend": "key", "width_in": "saved width", "height_in": "saved height"}
PRISM_LOOK_TIP = ("Open a .prism file you styled in GraphPad Prism (best: one PeterPiper wrote, "
                  "changed in Prism and saved) - the live graph takes on its look: error type, "
                  "colours, line widths, symbol, each-cell lines, axis ranges, font size and "
                  "titles. Every later export uses it too.")


def ask_prism_file(parent, folder: str = "") -> str:
    """File dialog for a .prism file ('' = cancelled)."""
    path, _f = QFileDialog.getOpenFileName(parent, "Load look from a Prism file", folder,
                                           "Prism project (*.prism)")
    return path or ""


def prism_look_from_file(path: str, current) -> Tuple[GraphStyle, str]:
    """(current look with every field the Prism file's graph gives, a plain
    message saying what was taken and what was kept). ValueError (plain text)
    when the file has no usable graph."""
    from ..prismstyle import read_style
    got, notes = read_style(path)
    cur = GS.coerce(current)
    d = cur.to_dict()
    d.update(got)
    if not cur.show_mean and not (float(got.get("mean_width", 1)) <= 0.12 + 1e-6
                                  and got.get("symbol") == "none" and got.get("error") == "none"):
        d["show_mean"] = True                     # the Prism graph shows the mean
    new = GS.GraphStyle.from_dict(d)
    kept = [w for f, w in _KEPT_WORDS.items() if f not in got]
    msg = [f"The live graph now has the look of {Path(path).name}. Every export uses it too."]
    if notes:
        msg.append("\n".join("- " + n for n in notes))
    msg.append("Kept as you had them (a .prism file does not hold them): " + ", ".join(kept) + ".")
    return new, "\n\n".join(msg)


def _colour_button(colour: str, on_click: Callable) -> QPushButton:
    b = QPushButton("")
    b.setFixedSize(34, 20)
    b.clicked.connect(on_click)
    _paint_button(b, colour)
    return b


def _paint_button(b: QPushButton, colour: str) -> None:
    b.setStyleSheet(f"QPushButton {{ background: {colour}; border: 1px solid #666; "
                    f"border-radius: 3px; }}")


class TracePanel(QWidget):
    cell_selected = Signal(int)
    include_set = Signal(int, bool)          # (cell, include?)
    include_all = Signal(bool)
    time_clicked = Signal(int)               # 0-based timepoint
    style_changed = Signal(dict)             # GraphStyle.to_dict() after you changed the look
    export_requested = Signal(str)           # 'Save graph...': the quantity shown
    view_changed = Signal(str)               # VIEW_CHECK | VIEW_EXPORTED

    def __init__(self, exp: Experiment, parent=None, style: Optional[dict] = None) -> None:
        super().__init__(parent)
        self.exp = exp
        self._M: Optional[Measurements] = None
        self._cells: List[int] = []
        self._inc: set = set()
        self._why: Dict[int, str] = {}
        self._sel: Optional[int] = None
        self._base = 0
        self._t = 0
        self._ref_ch = 0
        self._curves: List[Tuple[pg.PlotDataItem, int]] = []
        self._full: Optional[np.ndarray] = None
        self._x = np.zeros(0)
        self._xlabel = ""
        self._picked = False
        self._label = ""
        self._style = GS.coerce(style)
        self._view = VIEW_CHECK
        self._file = ""                      # export context: your name for the files
        self._comp = ""                      #   and the compartment label
        self._save_dir = ""
        self._title = ""
        self._errbar: Optional[pg.ErrorBarItem] = None
        self._exp_stats: Optional[Tuple[np.ndarray, ...]] = None
        self._mean = self._lo = self._hi = self._band = None
        self._family = _qt_family()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)
        self.header = W.wrapped_label("The traces of every cell appear here after "
                                      "Track & measure.")
        self.header.setStyleSheet("font-weight: 600;")
        lay.addWidget(self.header)

        # ---- view switch
        from . import theme as TH                  # V2.9: the theme's accent; not bold
        _acc = (TH.current().accent, TH.current().accent_text) if TH._current is not None             else ("#3d7fd6", "white")                  # (bold text was cut off)
        on_style = (f"QPushButton:checked {{ background: {_acc[0]}; color: {_acc[1]}; "
                    f"border-color: {_acc[0]}; }}")
        vrow = QWidget()
        vl = QHBoxLayout(vrow)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.addWidget(QLabel("View"))
        self._view_group = QButtonGroup(self)
        self._view_group.setExclusive(True)
        self.btn_view: Dict[str, QPushButton] = {}
        tips = {VIEW_CHECK: "Every cell in its own colour (as its outline), excluded cells "
                            "grey: for deciding which cells to keep.",
                VIEW_EXPORTED: "The graph as it will be exported: only the included cells, "
                               "in the style you choose here. The PNG / SVG look exactly "
                               "like this, and so does a Prism file, except for the few "
                               "things Prism cannot draw (marked *; a note says what the "
                               "Prism file shows instead)."}
        for v in (VIEW_CHECK, VIEW_EXPORTED):
            b = QPushButton(VIEW_TEXT[v])
            b.setCheckable(True)
            b.setStyleSheet(on_style)
            b.setToolTip(tips[v])
            b.clicked.connect(lambda _c=False, v=v: self._view_clicked(v))
            self._view_group.addButton(b)
            self.btn_view[v] = b
            vl.addWidget(b)
        self.btn_view[VIEW_CHECK].setChecked(True)
        vl.addStretch(1)
        lay.addWidget(vrow)

        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(QLabel("Show"))
        self.cmb_what = QComboBox()
        self.cmb_what.setMinimumWidth(160)
        self.cmb_what.currentIndexChanged.connect(lambda _i: self.refresh())
        rl.addWidget(self.cmb_what, 1)
        self.chk_hide = QCheckBox("Hide excluded")
        self.chk_hide.toggled.connect(lambda _v: self.refresh())
        rl.addWidget(self.chk_hide)
        self.chk_mean = QCheckBox("Mean only")
        self.chk_mean.toggled.connect(lambda _v: self.refresh())
        rl.addWidget(self.chk_mean)
        lay.addWidget(row)

        self.style_box = self._build_style_box()
        lay.addWidget(self.style_box)

        tools = QWidget()
        tl = QHBoxLayout(tools)
        tl.setContentsMargins(0, 0, 0, 0)
        self.btn_box = QPushButton("Zoom box")
        self.btn_box.setCheckable(True)
        self.btn_box.setToolTip("On: drag a rectangle on the plot to zoom into it. "
                                "Off: drag moves the plot. The mouse wheel always zooms.")
        self.btn_box.setStyleSheet(on_style)
        self.btn_box.toggled.connect(self._box_mode)
        tl.addWidget(self.btn_box)
        tl.addWidget(W.button("Reset zoom", self.reset_zoom,
                              "Show everything again (As exported: your fixed axis ranges, "
                              "if you set any in More style...)."))
        self.lbl_hover = QLabel("")
        self.lbl_hover.setProperty("muted", True)
        # a long readout is cut at the panel's edge (full text in the tooltip): it
        # must never make the panel - or its dock - wider while you hover
        self.lbl_hover.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.lbl_hover.setMinimumWidth(10)
        tl.addWidget(self.lbl_hover, 1)
        lay.addWidget(tools)

        pg.setConfigOption("background", "w")
        pg.setConfigOption("foreground", "k")
        self.plot = pg.PlotWidget()
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        self.plot.setMenuEnabled(False)
        self.plot.setMouseEnabled(True, True)
        self.vb = self.plot.getViewBox()
        self._hover_proxy = pg.SignalProxy(self.plot.scene().sigMouseMoved, rateLimit=30,
                                           slot=self._hover)
        self.plot.scene().sigMouseClicked.connect(self._scene_click)
        self.vb.sigXRangeChanged.connect(lambda *_a: self._update_beam())
        self.vb.sigResized.connect(lambda *_a: self._update_beam())

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Include", "Cell", "Note"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.itemChanged.connect(self._item_changed)
        self.table.itemSelectionChanged.connect(self._row_selected)
        self.table.setToolTip("Tick = included in the means, graphs and files. Click a row "
                              "to find the cell in the image.")

        lower = QWidget()
        ll = QVBoxLayout(lower)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(self.table, 1)
        ll.addWidget(W.row(W.button("Include all", lambda: self.include_all.emit(True)),
                           W.button("Exclude all", lambda: self.include_all.emit(False))))
        split = QSplitter(Qt.Vertical)
        split.addWidget(self.plot)
        split.addWidget(lower)
        split.setSizes([600, 320])
        lay.addWidget(split, 1)
        self._cursor = None
        self._baseline_line = None
        self._sync_controls()
        self._show_view_controls()

    # ======================================================== style controls
    def _build_style_box(self) -> QWidget:
        box = QWidget()
        bl = QVBoxLayout(box)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(3)

        # three short rows (and combo boxes that may shrink), so showing these
        # controls never makes the panel - or its dock - wider than 'Check cells'
        r1 = QHBoxLayout()
        r1.setContentsMargins(0, 0, 0, 0)
        mark, tip = prism_mark(GS.LOOK_FIELDS, "A ready-made look for the graph. Your titles, "
                                               "axis ranges and font size are kept.")
        lab = QLabel("Look" + mark)
        lab.setToolTip(tip)
        r1.addWidget(lab)
        self.cmb_look = QComboBox()
        self.cmb_look.addItems(list(GS.PRESETS) + [CUSTOM])
        # V2.4: last entry = 'Load look from a Prism file...' (an action, never kept)
        self.cmb_look.insertSeparator(self.cmb_look.count())
        self.cmb_look.addItem(PRISM_ITEM)
        self.cmb_look.setItemData(self.cmb_look.count() - 1, PRISM_LOOK_TIP, Qt.ToolTipRole)
        self.cmb_look.setToolTip(tip + "\n\nLast entry: " + PRISM_ITEM)
        self.cmb_look.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.cmb_look.setMinimumContentsLength(12)
        self.cmb_look.currentIndexChanged.connect(self._look_chosen)
        r1.addWidget(self.cmb_look, 1)
        self.btn_more = W.button("More style...", self._more_style,
                                 "Every choice: line widths, symbols, colours, titles, axis "
                                 "titles, axis ranges, font size, dashed line at time 0.")
        r1.addWidget(self.btn_more)
        bl.addLayout(r1)

        r2 = QHBoxLayout()
        r2.setContentsMargins(0, 0, 0, 0)
        mark, tip = prism_mark(["error"], "What the error bars / band show: SEM = SD / "
                                          "sqrt(n); SD = standard deviation (n - 1); 95% CI = "
                                          "mean ± t(0.975, n - 1) x SEM. n = included cells "
                                          "with a value at that time.")
        lab = QLabel("Error" + mark)
        lab.setToolTip(tip)
        r2.addWidget(lab)
        self.cmb_err = QComboBox()
        for v in GS.ERRORS:
            self.cmb_err.addItem(ERROR_TEXT[v], v)
        self.cmb_err.setToolTip(tip)
        self.cmb_err.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.cmb_err.setMinimumContentsLength(4)
        self.cmb_err.currentIndexChanged.connect(
            lambda _i: self._set_field("error", self.cmb_err.currentData()))
        r2.addWidget(self.cmb_err)
        mark, tip = prism_mark(["error_style"], "Error bars at every timepoint, or a shaded "
                                                "band around the mean.")
        self.cmb_errstyle = QComboBox()
        for v in GS.ERROR_STYLES:
            self.cmb_errstyle.addItem(ERROR_STYLE_TEXT[v] + mark, v)
        self.cmb_errstyle.setToolTip(tip)
        self.cmb_errstyle.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.cmb_errstyle.setMinimumContentsLength(7)
        self.cmb_errstyle.currentIndexChanged.connect(
            lambda _i: self._set_field("error_style", self.cmb_errstyle.currentData()))
        r2.addWidget(self.cmb_errstyle)
        mark, tip = prism_mark(["show_cells"], "Also draw each included cell as a thin line "
                                               "behind the mean.")
        self.chk_cells = QCheckBox("Each cell" + mark)
        self.chk_cells.setToolTip(tip)
        self.chk_cells.toggled.connect(lambda v: self._set_field("show_cells", bool(v)))
        mark, tip = prism_mark(["mean_colour"], "Colour of the mean line, symbols and error.")
        lab = QLabel("Mean" + mark)
        lab.setToolTip(tip)
        r2.addWidget(lab)
        self.btn_colour = _colour_button(self._style.mean_colour,
                                         lambda: self._pick_colour("mean_colour"))
        self.btn_colour.setToolTip(tip)
        r2.addWidget(self.btn_colour)
        r2.addStretch(1)
        bl.addLayout(r2)

        r3 = QHBoxLayout()
        r3.setContentsMargins(0, 0, 0, 0)
        r3.addWidget(self.chk_cells)
        r3.addStretch(1)
        self.btn_save = W.button("Save this graph...", self._save_clicked,
                                 "Save this graph (the quantity shown, included cells only): "
                                 "as a 300 dpi PNG and / or an SVG exactly as shown here, and "
                                 "as a Prism file (.prism) with the same data, titles and "
                                 "look. "
                                 "Existing files are never replaced.")
        r3.addWidget(self.btn_save)
        bl.addLayout(r3)

        # what the .prism file shows instead, whenever this look has something
        # Prism cannot draw (shaded band, hidden mean, dashed line at time 0 ...)
        self.lbl_prism = W.wrapped_label("")
        self.lbl_prism.setProperty("role", "warn")
        self.lbl_prism.setToolTip("What GraphPad Prism shows differently. Everything else "
                                  "(error type, colours, lines, symbols, each cell, titles, "
                                  "axis ranges, font size) is the same in the .prism file.")
        self.lbl_prism.setVisible(False)
        bl.addWidget(self.lbl_prism)
        return box

    def prism_warnings(self) -> List[str]:
        """Plain-language notes on what the .prism file shows differently from the
        look shown now (graphstyle.prism_look); [] = Prism draws the same."""
        return GS.prism_look(self._style)[1]

    def _sync_prism_note(self) -> None:
        warn = self.prism_warnings()
        self.lbl_prism.setText(("Prism file: " + " ".join(warn)) if warn else "")
        self.lbl_prism.setVisible(bool(warn))

    def _sync_controls(self) -> None:
        """Show the current style in the compact controls (no signals)."""
        st = self._style
        ws = (self.cmb_look, self.cmb_err, self.cmb_errstyle, self.chk_cells)
        for w in ws:
            w.blockSignals(True)
        name = GS.preset_name(st) or CUSTOM
        self.cmb_look.setCurrentIndex(max(0, self.cmb_look.findText(name)))
        self.cmb_err.setCurrentIndex(max(0, self.cmb_err.findData(st.error)))
        self.cmb_errstyle.setCurrentIndex(max(0, self.cmb_errstyle.findData(st.error_style)))
        self.cmb_errstyle.setEnabled(st.error != "none" and st.show_mean)
        self.cmb_err.setEnabled(st.show_mean)
        self.chk_cells.setChecked(st.show_cells)
        for w in ws:
            w.blockSignals(False)
        _paint_button(self.btn_colour, st.mean_colour)
        self._sync_prism_note()

    def _show_view_controls(self) -> None:
        ex = self._view == VIEW_EXPORTED
        self.style_box.setVisible(ex)
        self.chk_hide.setVisible(not ex)
        self.chk_mean.setVisible(not ex)

    def _look_chosen(self, _i: int) -> None:
        name = self.cmb_look.currentText()
        if name == PRISM_ITEM:
            self._sync_controls()                 # back to the look shown now
            QTimer.singleShot(0, self._prism_look_clicked)
            return
        if name in GS.PRESETS:
            self._change_style(GS.apply_preset(self._style, name))

    def _set_field(self, name: str, value) -> None:
        if getattr(self._style, name) == value:
            return
        self._change_style(GS.GraphStyle.from_dict({**self._style.to_dict(), name: value}))

    def _pick_colour(self, name: str) -> None:
        c = QColorDialog.getColor(QColor(getattr(self._style, name)), self,
                                  "Mean colour" if name == "mean_colour" else "Cell colour")
        if c.isValid():
            self._set_field(name, c.name().upper())

    def _change_style(self, new: GraphStyle, emit: bool = True) -> None:
        old, self._style = self._style, GS.coerce(new)
        self._sync_controls()
        if self._view == VIEW_EXPORTED:
            self.refresh(reset=any(getattr(old, f) != getattr(self._style, f)
                                   for f in RANGE_FIELDS))
        if emit and old != self._style:
            self.style_changed.emit(self._style.to_dict())

    def _more_style(self) -> None:
        old = self._style
        dlg = StyleDialog(self._style, self._xlabel or "Time from baseline (min)",
                          GS.quantity_title(self.current_quantity()) or "the quantity", self)
        dlg.changed.connect(lambda d: self._change_style(GraphStyle.from_dict(d), emit=False))
        if dlg.exec() == QDialog.Accepted:
            self._style = old                     # so the change is seen and announced
            self._change_style(dlg.result_style())
        else:
            self._change_style(old, emit=False)

    def _prism_look_clicked(self) -> None:
        folder = self._save_dir or self.exp.out_dir or str(Path(self.exp.nd2_path or ".").parent)
        path = ask_prism_file(self, folder)
        if path:
            self.load_prism_look(path)

    def load_prism_look(self, path: str, quiet: bool = False) -> bool:
        """Read the look of a .prism file into the live graph (set_style +
        style_changed, so the settings and the autosave follow). False and a
        plain message when the file cannot be used."""
        try:
            new, msg = prism_look_from_file(path, self._style)
        except ValueError as e:
            if not quiet:
                QMessageBox.warning(self, "Load look from a Prism file", str(e))
            return False
        self._change_style(new)
        if not quiet:
            QMessageBox.information(self, "Load look from a Prism file", msg)
        return True

    def _save_clicked(self) -> None:
        q = self.current_quantity()
        if self.isSignalConnected(QMetaMethod.fromSignal(self.export_requested)):
            self.export_requested.emit(q)
            return
        if self._full is None:
            return
        base = "_".join(p for p in (self._file, self._comp or self._label,
                                    GS.quantity_title(q)) if p)
        name = "".join(ch if ch.isalnum() or ch in "-_. ()" else "-" for ch in base) or "graph"
        folder = self._save_dir or self.exp.out_dir or str(Path(self.exp.nd2_path or ".").parent)
        path, _f = QFileDialog.getSaveFileName(
            self, "Save graph", str(Path(folder) / f"{name}.png"),
            "PNG image, 300 dpi (*.png);;SVG drawing (*.svg);;PDF (*.pdf)",
            options=QFileDialog.DontConfirmOverwrite)
        if not path:
            return
        try:
            used = self.save_graph(path)
        except (OSError, ValueError) as e:
            from ..safety import error_text
            QMessageBox.warning(self, "Save graph", f"The graph could not be saved:\n"
                                                    f"{error_text(e)}")
            return
        QMessageBox.information(self, "Save graph", f"Saved:\n{used}")

    # ================================================================ public
    def view(self) -> str:
        return self._view

    def set_view(self, view: str) -> None:
        view = VIEW_EXPORTED if view == VIEW_EXPORTED else VIEW_CHECK
        self.btn_view[view].setChecked(True)
        if view == self._view:
            return
        self._view = view
        self._show_view_controls()
        self.refresh(reset=True)

    def _view_clicked(self, view: str) -> None:
        if view != self._view:
            self.set_view(view)
            self.view_changed.emit(view)

    def set_style(self, style: Optional[dict]) -> None:
        """Use this graph style (a GraphStyle dict; {} / None = the defaults)."""
        self._change_style(GS.coerce(style).copy(), emit=False)

    def style(self) -> dict:
        return self._style.to_dict()

    def set_export_context(self, file_stem: str, comp_label: str, folder: str = "") -> None:
        """The names the export will use ({file} and {comp} in the title), and
        where 'Save graph...' starts."""
        self._file, self._comp = str(file_stem or ""), str(comp_label or "")
        if folder:
            self._save_dir = str(folder)
        if self._view == VIEW_EXPORTED:
            self.refresh()

    def current_quantity(self) -> str:
        """The quantity shown, e.g. 'R/R0 - GFP/Cy5'."""
        return self.cmb_what.currentText()

    def _included(self) -> List[int]:
        return [k for k in self._cells if k in self._inc]

    def current_series(self) -> Tuple[np.ndarray, np.ndarray, List[str], str, str]:
        """(x, y of the INCLUDED cells (T x n), cell names, automatic x title,
        automatic y title) - exactly what 'As exported' and the PNG draw."""
        if self._full is None:
            return np.zeros(0), np.zeros((0, 0)), [], "", ""
        inc = self._included()
        return (self._x.copy(), self._full[:, inc].copy(), [f"Cell_{k + 1}" for k in inc],
                self._xlabel, GS.quantity_title(self.current_quantity()))

    def current_title(self) -> str:
        return GS.title_text(self._style, self._file, self._comp or self._label,
                             GS.quantity_title(self.current_quantity()), len(self._included()))

    def save_graph(self, path, fmt: Optional[str] = None) -> str:
        """Write the 'As exported' graph (PNG 300 dpi / SVG / PDF). Never
        overwrites; returns the path written."""
        x, y, names, xl, yl = self.current_series()
        return GS.save_figure(path, x, y, names, self._style, xl, yl, self.current_title(),
                              fmt=fmt)

    # ================================================================ data
    def set_data(self, M: Measurements, cells: Sequence[int], included: Sequence[int],
                 why: Dict[int, str], label: str, base: int, ref_channel: int,
                 prefer: Sequence[str] = ()) -> None:
        self._M = M
        self._cells = list(cells)
        self._inc = set(included)
        self._why = dict(why)
        self._base = int(base)
        self._ref_ch = int(ref_channel)
        self._label = label
        keep = self.cmb_what.currentText()
        names = list(self._quantities().keys())
        if not keep or keep not in names:      # open on your key quantity (R/R0 GFP/Cy5)
            keep = next((n for n in prefer if n in names), None) or next(
                (n for n in names if n.startswith("F/F0") and
                 n.endswith(M.channels[min(self._ref_ch, M.n_channels - 1)])), names[0])
        self.cmb_what.blockSignals(True)
        self.cmb_what.clear()
        self.cmb_what.addItems(names)
        self.cmb_what.setCurrentIndex(max(0, self.cmb_what.findText(keep)))
        self.cmb_what.blockSignals(False)
        self._fill_table()
        self.refresh(reset=True)

    def set_included(self, included: Sequence[int], why: Dict[int, str]) -> None:
        self._inc = set(included)
        self._why = dict(why)
        self._fill_table()
        if self.chk_hide.isChecked() or self._view == VIEW_EXPORTED:
            QTimer.singleShot(0, self.refresh)
            return
        self._restyle()
        self._update_mean()
        self._update_header()

    def set_baseline(self, base: int) -> None:
        self._base = int(base)
        self.refresh()

    def set_time(self, t: int) -> None:
        self._t = int(t)
        if self._cursor is not None and self._x.size:
            self._cursor.setPos(float(self._x[min(self._t, self._x.size - 1)]))

    def select(self, k: Optional[int]) -> None:
        self._sel = k
        self._restyle()
        if k is not None and k in self._cells:
            row = self._cells.index(k)
            self.table.blockSignals(True)
            self.table.selectRow(row)
            self.table.blockSignals(False)
            self.table.scrollToItem(self.table.item(row, 0))

    def clear(self, text: str = "") -> None:
        self._M, self._cells, self._inc, self._curves = None, [], set(), []
        self._full = None
        self._errbar = self._exp_stats = None
        self._mean = self._lo = self._hi = self._band = None
        self.plot.clear()
        self._cursor = self._baseline_line = None
        self.plot.setTitle("")
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        self.table.blockSignals(False)
        self._set_header(text or "The traces of every cell appear here after "
                                    "Track & measure.")
        self.lbl_hover.setText("")

    def _quantities(self) -> Dict[str, Callable[[int], Tuple[np.ndarray, str]]]:
        M = self._M
        out: Dict[str, Callable] = {}
        if M is None:
            return out
        bs = M.bg_subtracted()
        for c, ch in enumerate(M.channels):
            out[f"F/F0 - {ch}"] = lambda b, c=c, ch=ch: (M.ff0(c, b), f"{ch} F/F0")
        for a, b_ in M.channel_pairs():
            na, nb = M.channels[a], M.channels[b_]
            out[f"R/R0 - {na}/{nb}"] = lambda b, a=a, b_=b_, na=na, nb=nb: (
                M.rr0(a, b_, b), f"{na}/{nb} R/R0")
        for a, b_ in M.channel_pairs():
            na, nb = M.channels[a], M.channels[b_]
            out[f"Ratio - {na}/{nb}"] = lambda b, a=a, b_=b_, na=na, nb=nb: (
                M.ratio_checked(a, b_, b), f"{na}/{nb}")
        for c, ch in enumerate(M.channels):
            out[f"Intensity - {ch}"] = lambda b, c=c, ch=ch: (bs[:, c, :], f"{ch} (counts - background)")
        return out

    # ============================================================== drawing
    def refresh(self, reset: bool = False) -> None:
        if self._M is None:
            return
        q = self._quantities()
        name = self.cmb_what.currentText() or next(iter(q))
        if name not in q:
            return
        T = self._M.n_timepoints
        b = int(np.clip(self._base, 0, T - 1))
        self._full, ylabel = q[name](b)
        self._x, xlabel = self.exp.time_axis(T, b)
        self._xlabel = xlabel
        keep_range = None if reset else self.vb.viewRange()
        self.plot.clear()
        self._curves = []
        self._errbar = self._exp_stats = None
        self._mean = self._lo = self._hi = self._band = None
        self._baseline_line = None
        if self._view == VIEW_EXPORTED:
            self._draw_exported(name)
        else:
            self._draw_check(name, xlabel, ylabel)
        self._cursor = pg.InfiniteLine(pos=float(self._x[min(self._t, T - 1)]), angle=90,
                                       pen=pg.mkPen(HILITE, width=1.6, style=Qt.DotLine))
        self._cursor.setZValue(20)
        self.plot.addItem(self._cursor)
        self._update_header()
        if keep_range is None:
            self.reset_zoom()
        else:
            self.vb.setRange(xRange=keep_range[0], yRange=keep_range[1], padding=0)
        self._update_beam()

    def _axes_plain(self) -> None:
        """Check cells: pyqtgraph's own look (grid, default fonts)."""
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        for side in ("left", "bottom"):
            ax = self.plot.getAxis(side)
            ax.labelStyle = {}
            ax.setTickFont(None)
            ax.setPen()
            ax.setTextPen()
            ax.setStyle(tickLength=-5)
            # pyqtgraph only lets the tick-label space grow (or shrink by > 10 px):
            # start it afresh, so the bigger 'As exported' labels do not leave the
            # axis wider (and the plot shifted) when you come back
            ax.textWidth, ax.textHeight = 30, 18
            ax._updateWidth() if side == "left" else ax._updateHeight()
        self.plot.getPlotItem().titleLabel.opts.pop("family", None)

    def _axes_styled(self) -> None:
        """As exported: Prism-like axes (no grid, ticks outward, your font size)."""
        st = self._style
        self.plot.showGrid(x=False, y=False)
        tick = QFont(self._family)
        tick.setPointSizeF(max(4.0, st.font_pt * GS.TICK_SCALE))
        for side in ("left", "bottom"):
            ax = self.plot.getAxis(side)
            ax.setTickFont(tick)
            ax.setPen(pg.mkPen("k", width=1.0 * PX))
            ax.setTextPen(pg.mkPen("k"))
            ax.setStyle(tickLength=5)

    def _draw_check(self, name: str, xlabel: str, ylabel: str) -> None:
        T = self._M.n_timepoints
        self._axes_plain()
        self.plot.setTitle(html.escape(f"{self._label}: {name}"), size="10pt", bold=False)
        self.plot.getPlotItem().layout.setRowFixedHeight(0, 30)
        self.plot.setLabel("bottom", html.escape(xlabel))
        self.plot.setLabel("left", html.escape(ylabel))
        if not self.chk_mean.isChecked():
            for k in self._cells:
                if self.chk_hide.isChecked() and k not in self._inc:
                    continue
                self._add_curve(k)
        self._lo = self.plot.plot(self._x, np.full(T, np.nan), pen=pg.mkPen(None))
        self._hi = self.plot.plot(self._x, np.full(T, np.nan), pen=pg.mkPen(None))
        self._band = pg.FillBetweenItem(self._lo, self._hi, brush=pg.mkBrush(0, 90, 220, 50))
        self._band.setZValue(9)
        self.plot.addItem(self._band)
        self._mean = self.plot.plot(self._x, np.full(T, np.nan), pen=pg.mkPen(MEAN, width=3.2))
        self._mean.setZValue(10)
        self._baseline_line = pg.InfiniteLine(pos=0.0, angle=90, pen=pg.mkPen(
            QColor(0, 115, 230), width=1.2, style=Qt.DashLine))
        self.plot.addItem(self._baseline_line)
        self._update_mean()

    def _draw_exported(self, name: str) -> None:
        st = self._style
        self._axes_styled()
        inc = self._included()
        xt, yt = GS.axis_titles(st, self._xlabel, GS.quantity_title(name))
        css = {"font-size": f"{st.font_pt:g}pt", "font-family": self._family, "color": "#000000"}
        self.plot.setLabel("bottom", html.escape(xt), **css)
        self.plot.setLabel("left", html.escape(yt), **css)
        self._title = self.current_title()
        self._apply_title()
        if st.show_cells:
            for k in inc:
                self._add_curve(k)
        if st.show_mean and inc:
            m, lo, hi, n = GS.stats(self._full[:, inc], st.error)
            self._exp_stats = (m, lo, hi, n)
            col = QColor(st.mean_colour)
            if st.error != "none":
                if st.error_style == "band":
                    self._lo = self.plot.plot(self._x, lo, pen=pg.mkPen(None), connect="finite")
                    self._hi = self.plot.plot(self._x, hi, pen=pg.mkPen(None), connect="finite")
                    fill = QColor(col)
                    fill.setAlphaF(GS.BAND_ALPHA)
                    self._band = pg.FillBetweenItem(self._lo, self._hi, brush=pg.mkBrush(fill))
                    self._band.setZValue(9)
                    self.plot.addItem(self._band)
                else:
                    ok = np.isfinite(m) & np.isfinite(lo) & np.isfinite(hi)
                    if ok.any():
                        self._errbar = pg.ErrorBarItem(
                            x=self._x[ok], y=m[ok], top=(hi - m)[ok], bottom=(m - lo)[ok],
                            pen=pg.mkPen(col, width=max(st.mean_width, 0.5) * PX))
                        self._errbar.setZValue(9)
                        self.plot.addItem(self._errbar)
            sym = GS.PG_SYMBOL.get(st.symbol)
            self._mean = self.plot.plot(
                self._x, m, pen=pg.mkPen(col, width=st.mean_width * PX) if st.mean_width > 0
                else None, symbol=sym, symbolSize=st.symbol_size * PX, symbolBrush=col,
                symbolPen=None, connect="finite")
            self._mean.setZValue(10)
        if st.baseline_line:
            self._baseline_line = pg.InfiniteLine(pos=0.0, angle=90, pen=pg.mkPen(
                QColor(GS.BASELINE_COLOUR), width=0.75 * PX, style=Qt.DashLine))
            self.plot.addItem(self._baseline_line)

    def _apply_title(self) -> None:
        """The title, broken into lines that fit the plot (as the PNG does)."""
        pi = self.plot.getPlotItem()
        if self._view != VIEW_EXPORTED:
            return
        st = self._style
        if not self._title:
            self.plot.setTitle(None)
            return
        px = st.font_pt * PX
        per_line = max(20, int(max(self.plot.width(), 200) / (0.55 * px)))
        lines = textwrap.wrap(self._title, per_line) or [self._title]
        self.plot.setTitle("<br>".join(html.escape(s) for s in lines),
                           size=f"{st.font_pt:g}pt", bold=True, family=self._family)
        h = int(len(lines) * px * 1.35 + 10)
        pi.titleLabel.setMaximumHeight(h)
        pi.layout.setRowFixedHeight(0, h)

    def resizeEvent(self, ev) -> None:                        # noqa: N802
        super().resizeEvent(ev)
        if self._view == VIEW_EXPORTED and self._title:
            self._apply_title()

    def _add_curve(self, k: int) -> None:
        item = self.plot.plot(self._x, self._full[:, k], pen=self._pen(k))
        item.setZValue(self._z(k))
        item.curve.setClickable(True, width=8)
        item.sigClicked.connect(lambda _it, ev=None, kk=k: self._pick(kk, ev))
        self._curves.append((item, k))

    def _update_beam(self) -> None:
        """Error-bar caps: a fixed size on screen (as in the PNG), whatever the zoom."""
        if self._errbar is None:
            return
        (x0, x1), w = self.vb.viewRange()[0], self.vb.width()
        if x1 > x0 and w > 0:
            self._errbar.setData(beam=2.0 * GS.cap_pt(self._style) * PX * (x1 - x0) / w)

    def _update_mean(self) -> None:
        if self._full is None or self._mean is None or self._view != VIEW_CHECK:
            return
        inc = self._included()
        if inc:
            m, lo, hi, _n = GS.stats(self._full[:, inc], self._err())
        else:
            m = lo = hi = np.full(self._full.shape[0], np.nan)
        self._mean.setData(self._x, m, connect="finite")
        self._lo.setData(self._x, lo, connect="finite")
        self._hi.setData(self._x, hi, connect="finite")

    def reset_zoom(self) -> None:
        if self._full is None:
            return
        if self._view == VIEW_EXPORTED:
            self._reset_zoom_exported()
            return
        inc = self._included() or list(self._cells)
        v = self._full[:, inc] if inc else np.zeros((0,))
        v = v[np.isfinite(v)]
        x0, x1 = float(self._x[0]), float(self._x[-1])
        if v.size >= 2:
            lo, hi = np.percentile(v, [0.5, 99.5])
            pad = 0.08 * max(hi - lo, abs(hi) * 0.05, 1e-6)
            self.vb.setRange(xRange=(x0, x1), yRange=(float(lo - pad), float(hi + pad)),
                             padding=0.02)
        else:
            self.vb.autoRange()

    def _reset_zoom_exported(self) -> None:
        """Everything drawn + 5 % margins (matplotlib's automatic range), then
        your fixed axis limits."""
        st = self._style
        parts = []
        if st.show_cells:
            parts.append(self._full[:, self._included()].ravel())
        if self._exp_stats is not None:
            parts += [np.asarray(a, float) for a in self._exp_stats[:3]]
        v = np.concatenate(parts) if parts else np.zeros(0)
        v = v[np.isfinite(v)]
        x0, x1 = float(self._x[0]), float(self._x[-1])
        dx = 0.05 * (x1 - x0) if x1 > x0 else 0.5
        if v.size:
            y0, y1 = float(v.min()), float(v.max())
        else:
            y0, y1 = 0.0, 1.0
        dy = 0.05 * (y1 - y0) if y1 > y0 else max(abs(y0) * 0.05, 0.5)
        xr = [x0 - dx, x1 + dx]
        yr = [y0 - dy, y1 + dy]
        if st.x_min is not None:
            xr[0] = st.x_min
        if st.x_max is not None:
            xr[1] = st.x_max
        if st.y_min is not None:
            yr[0] = st.y_min
        if st.y_max is not None:
            yr[1] = st.y_max
        if xr[1] <= xr[0]:
            xr[1] = xr[0] + 1.0
        if yr[1] <= yr[0]:
            yr[1] = yr[0] + 1.0
        self.vb.setRange(xRange=tuple(xr), yRange=tuple(yr), padding=0)
        self._update_beam()

    def _box_mode(self, on: bool) -> None:
        self.vb.setMouseMode(pg.ViewBox.RectMode if on else pg.ViewBox.PanMode)

    def _pen(self, k: int):
        if k == self._sel:
            return pg.mkPen(HILITE, width=3.0)
        if self._view == VIEW_EXPORTED:
            return pg.mkPen(QColor(self._style.cell_colour),
                            width=max(self._style.cell_width * PX, 0.5))
        if k in self._inc:
            return pg.mkPen(QColor(cell_colour(k)), width=1.6)
        return pg.mkPen(EXCLUDED, width=1.0)

    def _z(self, k: int) -> int:
        if self._view == VIEW_EXPORTED:
            return 11 if k == self._sel else 1
        return 8 if k == self._sel else (3 if k in self._inc else 1)

    def _restyle(self) -> None:
        for item, k in self._curves:
            item.setPen(self._pen(k))
            item.setZValue(self._z(k))

    def _update_header(self) -> None:
        n_in = sum(1 for k in self._cells if k in self._inc)
        if self._view == VIEW_EXPORTED:
            self._set_header(f"{self._label}: {n_in} of {len(self._cells)} cells included "
                                f"(ticked below). As exported: "
                                f"{GS.style_summary(self._style)} of the included cells. "
                                f"All values background-subtracted." + self._blank_note())
            return
        err = self._err()
        shade = "" if err == "none" else f", shaded = {ERROR_TEXT.get(err, err)}"
        self._set_header(f"{self._label}: {n_in} of {len(self._cells)} cells included "
                            f"(ticked below). Blue = mean of the included{shade}. "
                            f"All values background-subtracted." + self._blank_note())

    def _err(self) -> str:
        """V3.0: the error of your graph look (one choice everywhere; SD default)."""
        return GS.coerce(self._style or {}).error

    def _blank_note(self) -> str:
        """V3.0: included cells this quantity leaves out (a channel too dim at baseline)."""
        full = getattr(self, "_full", None)
        if full is None or self._M is None:
            return ""
        blank = [k for k in self._cells if k in self._inc and k < full.shape[1]
                 and not np.isfinite(full[:, k]).any()]
        if not blank:
            return ""
        from ..measure import min_snr
        return (f" {len(blank)} included cell{'' if len(blank) == 1 else 's'} "
                f"{'has' if len(blank) == 1 else 'have'} no value here: a channel of this "
                f"quantity is below {min_snr():g} x the noise of the ROI mean at the baseline "
                f"(dividing by almost nothing; step 4 sets this).")

    def _set_header(self, text: str) -> None:
        # FitLabel only ever grows (its minimum height also floors heightForWidth),
        # so a shorter text after a longer one (As exported -> Check cells) would
        # keep an empty second line and shrink the plot: start from 0 each time.
        self.header.setMinimumHeight(0)
        self.header.setText(text)

    # ================================================================ table
    def _fill_table(self) -> None:
        t = self.table
        t.blockSignals(True)
        t.setRowCount(len(self._cells))
        bold = QFont()
        bold.setBold(True)
        for row, k in enumerate(self._cells):
            chk = QTableWidgetItem("")
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            chk.setCheckState(Qt.Checked if k in self._inc else Qt.Unchecked)
            chk.setData(Qt.UserRole, k)
            t.setItem(row, 0, chk)
            name = QTableWidgetItem(f"Cell {k + 1}")
            name.setForeground(QBrush(QColor(cell_colour(k)) if k in self._inc
                                      else QColor(150, 150, 150)))
            name.setFont(bold)
            t.setItem(row, 1, name)
            note = self._why.get(k, "")
            t.setItem(row, 2, QTableWidgetItem("" if note == "included" else note))
        t.blockSignals(False)
        if self._sel is not None and self._sel in self._cells:
            t.blockSignals(True)
            t.selectRow(self._cells.index(self._sel))
            t.blockSignals(False)

    def _item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != 0:
            return
        k = item.data(Qt.UserRole)
        if k is None:
            return
        on = item.checkState() == Qt.Checked
        if on != (k in self._inc):
            QTimer.singleShot(0, lambda: self.include_set.emit(int(k), bool(on)))

    def _row_selected(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        k = self._cells[rows[0].row()]
        self._sel = k
        self._restyle()
        self.cell_selected.emit(int(k))

    # ================================================================ mouse
    def _pick(self, k: int, ev=None) -> None:
        # inside pyqtgraph's own click handling: restyle only, act afterwards
        self._picked = True
        double = bool(ev is not None and hasattr(ev, "double") and ev.double())
        self._sel = k
        self._restyle()
        QTimer.singleShot(0, lambda: self.select(k))
        QTimer.singleShot(0, lambda: self.cell_selected.emit(int(k)))
        if double:
            QTimer.singleShot(0, lambda: self.include_set.emit(int(k), k not in self._inc))

    def _scene_click(self, ev) -> None:
        if ev.button() != Qt.LeftButton or ev.double() or self._M is None:
            return
        pos = ev.scenePos()
        if not self.vb.sceneBoundingRect().contains(pos):
            return
        x = self.vb.mapSceneToView(pos).x()

        def later():
            if self._picked:
                self._picked = False
                return
            if self._x.size:
                self.time_clicked.emit(int(np.argmin(np.abs(self._x - x))))
        QTimer.singleShot(0, later)

    def _hover(self, evt) -> None:
        if self._full is None or not self._x.size:
            return
        pos = evt[0]
        if not self.vb.sceneBoundingRect().contains(pos):
            self.lbl_hover.setText("")
            return
        p = self.vb.mapSceneToView(pos)
        i = int(np.argmin(np.abs(self._x - p.x())))
        unit = "min" if self.exp.seconds_per_frame > 0 else "timepoints"
        txt = f"t = {self._x[i]:+.4g} {unit} (timepoint {i + 1})"
        shown = [k for _it, k in self._curves]
        if self._exp_stats is not None:              # As exported: the mean there
            m, lo, hi, n = self._exp_stats
            if np.isfinite(m[i]):
                e = GS.error_label(self._style.error)
                err = (f" ± {hi[i] - m[i]:.3g} {e}" if e and np.isfinite(hi[i]) else "")
                txt = f"Mean {m[i]:.4g}{err} (n = {int(n[i])})  at  " + txt
        if shown:
            vals = self._full[i, shown]
            ok = np.isfinite(vals)
            if ok.any():
                (y0, y1) = self.vb.viewRange()[1]
                d = np.abs(vals - p.y())
                d[~ok] = np.inf
                j = int(np.argmin(d))
                if d[j] < 0.03 * (y1 - y0):
                    txt = f"Cell {shown[j] + 1}:  {vals[j]:.4g}  at  " + txt.split("  at  ")[-1]
        self.lbl_hover.setText(txt)
        self.lbl_hover.setToolTip(txt)


# ==========================================================================
#  'More style...' - every GraphStyle choice; the graph updates as you edit
# ==========================================================================
class StyleDialog(QDialog):
    changed = Signal(dict)

    def __init__(self, style: GraphStyle, auto_x: str, auto_y: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Graph style")
        self._st = GS.coerce(style).copy()
        self._busy = False
        lay = QVBoxLayout(self)
        intro = W.wrapped_label("Changes show in the graph straight away (As exported view). "
                                "OK keeps them, Cancel goes back. The PNG export, 'Save this "
                                "graph...' and the Prism files use this look; choices marked * "
                                "are things Prism cannot draw (the tooltip says what the Prism "
                                "file shows instead).", muted=True)
        lay.addWidget(intro)
        cols = QHBoxLayout()
        left, right = QVBoxLayout(), QVBoxLayout()
        cols.addLayout(left)
        cols.addLayout(right)
        lay.addLayout(cols)
        self.w: Dict[str, QWidget] = {}

        box, f = W.group("Mean of the included cells")
        self._check(f, "show_mean", "Show the mean", "The mean line with its symbols and error.")
        self._colour(f, "mean_colour", "Colour", "Colour of the mean line, symbols and error.")
        self._num(f, "mean_width", "Line width (pt)", 0, 20, 0.25,
                  "0 = symbols only, no connecting line (Prism always joins the symbols: "
                  "its file gets a 0.12 pt line).")
        self._choice(f, "symbol", "Symbol", SYMBOL_TEXT, "The marker at every timepoint.")
        self._num(f, "symbol_size", "Symbol size (pt)", 0, 40, 0.5, "Diameter of the symbol.")
        left.addWidget(box)

        box, f = W.group("Error")
        self._choice(f, "error", "Show", {v: ERROR_TEXT[v] for v in GS.ERRORS},
                     "SEM = SD / sqrt(n); SD = standard deviation (n - 1); 95% CI = mean ± "
                     "t(0.975, n - 1) x SEM; n = included cells with a value at that time.")
        self._choice(f, "error_style", "As", ERROR_STYLE_TEXT,
                     "Error bars at every timepoint, or a shaded band around the mean.")
        left.addWidget(box)

        box, f = W.group("Each included cell")
        self._check(f, "show_cells", "Show each cell as a thin line", "Behind the mean.")
        self._colour(f, "cell_colour", "Colour", "One colour for every cell line.")
        self._num(f, "cell_width", "Line width (pt)", 0, 20, 0.25, "")
        left.addWidget(box)
        left.addStretch(1)

        box, f = W.group("Titles")
        self._text(f, "title", "Graph title", "{file} - {comp} (n = {n})",
                   "Use {file} (your name for the files), {comp} (compartment), {n} (number "
                   "of included cells) and {quantity} (e.g. R/R0 GFP/Cy5). Empty = no title.",
                   allow_placeholder=False)
        self._text(f, "x_title", "X axis title", f"automatic: {auto_x}",
                   "Leave empty for the automatic title.")
        self._text(f, "y_title", "Y axis title", f"automatic: {auto_y}",
                   "Leave empty for the automatic title.")
        right.addWidget(box)

        box, f = W.group("Axis ranges (empty = automatic)")
        for name, lab in (("x_min", "X from"), ("x_max", "X to"), ("y_min", "Y from"),
                          ("y_max", "Y to")):
            self._limit(f, name, lab)
        right.addWidget(box)

        box, f = W.group("Text, lines and size")
        self._num(f, "font_pt", "Axis title size (pt)", 4, 72, 1,
                  "Tick labels are 0.9 x this size; the title is this size, bold.")
        self._check(f, "baseline_line", "Dashed line at time 0 (the baseline)", "")
        self._check(f, "legend", "Key (e.g. 'Mean ± SEM (n = 8)')", "")
        self._num(f, "width_in", "Saved width (inches)", 1, 30, 0.5,
                  "Size of the saved PNG / SVG / PDF (300 dpi). The live view fills the panel.")
        self._num(f, "height_in", "Saved height (inches)", 1, 30, 0.5, "")
        right.addWidget(box)
        right.addStretch(1)

        if any(GS.prism_support(n) == "no" for n in self.w):
            lay.addWidget(W.wrapped_label("* Prism cannot draw this exactly; the .prism file "
                                          "gets the closest Prism look (see the tooltip). "
                                          + GS.PRISM_NOTE + ".", muted=True))
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        reset = bb.addButton("Prism default", QDialogButtonBox.ResetRole)
        reset.setToolTip("Every choice back to the default look (as the Prism template).")
        reset.clicked.connect(lambda: self._load(GraphStyle()))
        prism = bb.addButton("Load look from a Prism file...", QDialogButtonBox.ActionRole)
        prism.setToolTip(PRISM_LOOK_TIP)
        prism.clicked.connect(self._load_prism)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._load(self._st, emit=False)

    # ---- builders (each row says whether Prism gets it)
    def _label(self, name: str, text: str, tip: str) -> Tuple[QLabel, str]:
        mark, tip = prism_mark([name], tip)
        lab = QLabel(text + mark)
        lab.setToolTip(tip)
        return lab, tip

    def _check(self, f: QFormLayout, name: str, text: str, tip: str) -> None:
        mark, tip = prism_mark([name], tip)
        w = QCheckBox(text + mark)
        w.setToolTip(tip)
        w.toggled.connect(lambda v: self._set(name, bool(v)))
        f.addRow(w)
        self.w[name] = w

    def _num(self, f, name, text, lo, hi, step, tip) -> None:
        lab, tip = self._label(name, text, tip)
        w = QDoubleSpinBox()
        w.setRange(lo, hi)
        w.setSingleStep(step)
        w.setDecimals(2)
        w.setToolTip(tip)
        w.valueChanged.connect(lambda v: self._set(name, float(v)))
        f.addRow(lab, w)
        self.w[name] = w

    def _choice(self, f, name, text, items: Dict[str, str], tip) -> None:
        lab, tip = self._label(name, text, tip)
        w = QComboBox()
        for v, t in items.items():
            w.addItem(t, v)
        w.setToolTip(tip)
        w.currentIndexChanged.connect(lambda _i: self._set(name, w.currentData()))
        f.addRow(lab, w)
        self.w[name] = w

    def _colour(self, f, name, text, tip) -> None:
        lab, tip = self._label(name, text, tip)
        w = _colour_button("#000000", lambda: self._pick(name))
        w.setToolTip(tip)
        f.addRow(lab, w)
        self.w[name] = w

    def _text(self, f, name, text, placeholder, tip, allow_placeholder=True) -> None:
        lab, tip = self._label(name, text, tip)
        w = QLineEdit()
        w.setPlaceholderText(placeholder if allow_placeholder else "(no title)")
        w.setToolTip(tip)
        w.setMinimumWidth(240)
        w.textChanged.connect(lambda v: self._set(name, v))
        f.addRow(lab, w)
        self.w[name] = w

    def _limit(self, f, name, text) -> None:
        lab, tip = self._label(name, text, "A number, or empty for automatic. You can still "
                                           "zoom in the live view; Reset zoom comes back here.")
        w = QLineEdit()
        w.setPlaceholderText("auto")
        w.setToolTip(tip)
        w.textChanged.connect(lambda v: self._set_limit(name, v))
        f.addRow(lab, w)
        self.w[name] = w

    # ---- values
    def _pick(self, name: str) -> None:
        c = QColorDialog.getColor(QColor(getattr(self._st, name)), self, "Colour")
        if c.isValid():
            self._set(name, c.name().upper())
            _paint_button(self.w[name], getattr(self._st, name))

    def _set_limit(self, name: str, text: str) -> None:
        t = text.strip()
        ok, v = GS._coerce(name, t, None)
        self.w[name].setStyleSheet("" if ok else "QLineEdit { background: #ffd6d6; }")
        self._set(name, v if ok else None)

    def _set(self, name: str, value) -> None:
        if self._busy:
            return
        self._st = GraphStyle.from_dict({**self._st.to_dict(), name: value})
        self._enable()
        self.changed.emit(self._st.to_dict())

    def _enable(self) -> None:
        st = self._st
        for n in ("mean_colour", "mean_width", "symbol", "symbol_size", "error", "error_style"):
            self.w[n].setEnabled(st.show_mean)
        self.w["error_style"].setEnabled(st.show_mean and st.error != "none")
        for n in ("cell_colour", "cell_width"):
            self.w[n].setEnabled(st.show_cells)

    def _load(self, st: GraphStyle, emit: bool = True) -> None:
        self._busy = True
        try:
            for name, w in self.w.items():
                v = getattr(st, name)
                if isinstance(w, QCheckBox):
                    w.setChecked(bool(v))
                elif isinstance(w, QDoubleSpinBox):
                    w.setValue(float(v))
                elif isinstance(w, QComboBox):
                    w.setCurrentIndex(max(0, w.findData(v)))
                elif isinstance(w, QLineEdit):
                    w.setText("" if v is None else (f"{v:g}" if isinstance(v, float) else str(v)))
                    w.setStyleSheet("")
                elif isinstance(w, QPushButton):
                    _paint_button(w, v)
        finally:
            self._busy = False
        self._st = GS.coerce(st).copy()
        self._enable()
        if emit:
            self.changed.emit(self._st.to_dict())

    def _load_prism(self) -> None:
        path = ask_prism_file(self)
        if path:
            self.load_prism_file(path)

    def load_prism_file(self, path: str, quiet: bool = False) -> bool:
        """The look of a .prism file into this dialog (the live graph follows;
        OK keeps it, Cancel goes back)."""
        try:
            new, msg = prism_look_from_file(path, self._st)
        except ValueError as e:
            if not quiet:
                QMessageBox.warning(self, "Load look from a Prism file", str(e))
            return False
        self._load(new)
        if not quiet:
            QMessageBox.information(self, "Load look from a Prism file",
                                    msg.replace("Every export uses it too.",
                                                "OK keeps it, Cancel goes back."))
        return True

    def result_style(self) -> GraphStyle:
        return self._st.copy()
