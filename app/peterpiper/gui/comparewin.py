"""
'Compare / average runs' window (V2.4 compare, V2.5 groups of replicate dishes).

Opened from the start window (no .nd2 needed), and from the main window (File >
Compare runs..., the button under the export button). The numbers come from
peterpiper.compare (the export's own arithmetic); this window only lets you pick the
runs, put them into groups, choose the compartment, quantity and baseline, shows
the live graph and saves it (never overwriting).

    Show   'Each run'                   one line per run: mean of its included
                                        cells (n = cells) - the V2.4 comparison
           'Groups - mean of dishes'    one line per group: mean +/- error of the
                                        dish means (n = dishes; compare.group_line)
           'Groups - pooled cells'      one line per group: all its cells pooled
                                        (n = cells; for reference)

Group: type a name in the Group column (or select rows and 'Put in group...',
or 'Group by cell line'). A run without a group is a group of its own.

Colours (peterpiper.celllines): the cell line is read from the run / group name;
runs (or groups) of one cell line get ordered shades of that line's colour
family (U2OS reds, IHH greens, HepG2 blues, HEK293 purples, HeLa oranges ...).
Unknown cell line: the window asks for a colour once and remembers it for that
name (compare_colours.json next to the settings). Double-click a colour to
change it (also remembered).

V2.5 list:
  * Cell line column = a dropdown per run ('Unknown', every known cell line, or
    type a new name). The choice wins over the name match, re-colours the run
    (that family's shades; a new name: its colour is asked once) and is
    remembered per .nd2 (its content fingerprint; no fingerprint: the run file's
    path) in compare_window.json next to the settings. 'Group by cell line' uses it.
  * Click a column title to sort (dates by date, numbers as numbers, names
    naturally: dish 2 before dish 10); drag a title to move the column. Order,
    sort and widths are remembered (compare_window.json). Every row's state is
    kept by run, never by row number.
  * Runs made from the same .nd2 (compare.same_nd2: same fingerprint, else the
    same .nd2 path, else the same file name and size) are marked in 'Same .nd2
    as' (orange). Two ticked runs of one .nd2: a red warning in the window, and
    Save... asks first - one dish must not be counted twice.
V2.6:
  * One row per analysis: files with the same content key (roifile.content_key -
    an export's ROI file and the session autosaved with it) are one row (the
    file the user saved; autosaved sessions in self._copies and the tooltip).
  * Every set of runs from one .nd2 gets its own colour (in '.nd2 file', 'Same
    .nd2 as' and 'Version'); 'Version' says which analysis is the newest and
    which are older ('newest (3 of 3)', 'older (2 of 3)' ...), by the date each
    run was saved. Sorting by 'Version' (the default) puts the newest analyses
    on top with the older analyses of the same .nd2 right under them.
  * Remembered for next time (compare_window.json): each run's group, its name
    in the graph, which runs were ticked, what is shown and the kinetics choices.
    A group is remembered for the run file and for its .nd2 (fingerprint), so a
    new analysis of a dish already in a group joins that group.
  * Graph: the time course, or one kinetics parameter (peterpiper.kinetics: t½ max,
    initial rise slope, maximum rate, time to max, amplitude, 10-90% rise time)
    as a dot plot - each dish a dot, the group mean with the chosen error across
    the dishes. Save writes the ticked kinetics graphs (every ticked picture
    format and .prism, the graph made) and the kinetics tables.
"""
from __future__ import annotations

import html
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QStringListModel, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QPalette
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QColorDialog, QComboBox, QDialog,
                               QFileDialog, QGridLayout, QHeaderView, QInputDialog, QLabel,
                               QLineEdit, QMenu, QMessageBox, QPushButton, QSpinBox, QSplitter,
                               QScrollArea, QStyledItemDelegate, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from .. import celllines as CL
from .. import compare as C
from .. import graphstyle as GS
from .. import history
from .. import xyplot as XP
from ..safety import error_text, plain_path
from . import widgets as W
from .measurerow import MeasureRow

PX = GS.PX_PER_PT
(COL_USE, COL_COLOUR, COL_LABEL, COL_VER, COL_SAVED, COL_GROUP, COL_LINE, COL_FILE, COL_SAME,
 COL_CELLS, COL_BASE, COL_INT) = range(12)
HEADERS = ["Use", "Colour", "Name in the graph", "Version", "Saved", "Group (replicate dishes)",
           "Cell line", ".nd2 file", "Movie folder", "Cells", "Baseline", "Frame interval"]
COL_DIR = COL_SAME            # V2.8: the .nd2's folder (the tree shows which runs are one movie)
FOLDER_ROLE = int(Qt.UserRole) + 3        # a movie folder row: its key
GROUP_ROLE = int(Qt.UserRole) + 4         # a group folder row: the group name ('' = none)
NO_GROUP = "No group"
PATH_ROLE = int(Qt.UserRole) + 1          # every item of a row knows its run (path)
SORT_ROLE = int(Qt.UserRole) + 2          # number / ISO date to sort by (else the text)
UNKNOWN = "Unknown"
DUP_BG = "#FFD08A"                        # 'same .nd2 as another run' (first set: orange)
# one light colour per set of runs from one .nd2 (dark text on them)
DUP_COLOURS = ("#FFD08A", "#A8E6CF", "#AFCBFF", "#F7B2D9", "#FFF3A0", "#C9B6FF", "#9EE7F0",
               "#FFB3A7", "#D4E8A0", "#E0C8A8", "#B8D8D8", "#F0C0F0")
GRAPH_TIME = "time"
FORMATS = (("prism", "Prism (.prism)", True), ("png", "PNG (300 dpi)", True),
           ("jpeg", "JPEG", False), ("svg", "SVG", True), ("tiff", "TIFF", False),
           ("pdf", "PDF", False), ("csv", "CSV", True), ("xlsx", "Excel (.xlsx)", True))
MODES = (("runs", "Each run - mean of its cells (n = cells)"),
         ("dishes", "Groups - mean of dish means (n = dishes)"),
         ("pooled", "Groups - all cells pooled (n = cells)"))
# V2.8: hover explanations (for anyone new to the analysis)
MODE_TIPS = {
    "runs": "One line per dish (run): the mean of its own cells, error across its cells "
            "(n = cells). Use it to look at each dish and spot an odd one before averaging.",
    "dishes": "One line per GROUP of replicate dishes: each dish is first averaged over its "
              "cells, then the dishes are averaged (n = dishes). This is the number to report: "
              "dishes are the independent replicates, cells of one dish are not.",
    "pooled": "One line per group with every cell of all its dishes thrown together (n = cells). "
              "For a look only - the error bars are too small, because cells of one dish are "
              "not independent replicates.",
}
ERROR_TIPS = {
    "SEM": "Standard error of the mean = SD / √n: how precisely the mean is known. The usual "
           "choice for comparing means; shrinks as n grows.",
    "SD": "Standard deviation: how spread out the individual values (cells or dishes) are. "
          "Use it to show variability between cells, not the precision of the mean.",
    "95% CI": "95% confidence interval of the mean (t-based): the range that would contain the "
              "true mean in 95% of repeated experiments. Non-overlapping CIs suggest a real "
              "difference.",
    "none": "The mean only, no error bars.",
}
KIN_TIPS = {
    "t_half": "Time from the baseline until the response is half-way to its maximum - how fast "
              "the response develops. Smaller = faster.",
    "slope": "The initial rate of rise: a straight line fitted from the baseline to the first "
             "frame past half-max. Bigger = faster start.",
    "max_rate": "The steepest frame-to-frame change before the peak: the fastest moment of the "
                "response.",
    "t_max": "Time from the baseline to the peak (largest change).",
    "amp": "The size of the response: peak minus baseline level. How much it changed, not how "
           "fast.",
    "rise": "10-90% rise time: from 10% to 90% of the way to the peak - a steepness measure that "
            "ignores the slow start and the slow end.",
}
PG_SYM = {"circle": "o", "square": "s", "triangle": "t1", "triangle_down": "t",
          "diamond": "d", "open_circle": "o", "open_square": "s", "open_triangle": "t1",
          "open_triangle_down": "t", "open_diamond": "d", "none": None}


def _colour_file() -> Path:
    from ..config import _settings_file
    return _settings_file().parent / "compare_colours.json"


def load_remembered() -> Dict[str, str]:
    """{name lower case: '#RRGGBB'} - colours chosen for cell lines / groups / runs."""
    try:
        d = json.loads(_colour_file().read_text(encoding="utf-8"))
        return {str(k).lower(): str(v) for k, v in (d.get("names") or {}).items()}
    except (OSError, ValueError, AttributeError):
        return {}


def _write_remembered(d: Dict[str, str]) -> None:
    try:
        _colour_file().write_text(json.dumps({"names": d}, indent=1), encoding="utf-8")
    except OSError:
        pass


def remember(name: str, colour: str) -> None:
    d = load_remembered()
    d[str(name).strip().lower()] = colour
    _write_remembered(d)


def forget(name: str) -> None:
    """Drop the colour remembered for this name (its cell line was changed)."""
    d = load_remembered()
    if d.pop(str(name).strip().lower(), None) is not None:
        _write_remembered(d)


# ------------------------------------------------- window prefs (V2.5)
def _prefs_file() -> Path:
    return _colour_file().parent / "compare_window.json"


def load_prefs() -> dict:
    """{'cell_lines': {run key: cell line}, 'table': {order, sort, widths}}."""
    try:
        d = json.loads(_prefs_file().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def update_prefs(**parts) -> None:
    """Read, merge these top-level parts, write (another window may have written)."""
    d = load_prefs()
    d.update(parts)
    try:
        _prefs_file().parent.mkdir(parents=True, exist_ok=True)
        _prefs_file().write_text(json.dumps(d, indent=1), encoding="utf-8")
    except OSError:
        pass


def _natural(text: str) -> tuple:
    """'dish 10' after 'dish 2'."""
    parts = re.split(r"(\d+(?:\.\d+)?)", str(text).lower())
    return tuple((0, float(p), "") if i % 2 else (1, 0.0, p) for i, p in enumerate(parts))


class _RunItem(QTreeWidgetItem):
    """V2.8: a row of the run tree (one analysis, or a movie folder holding the
    analyses of one .nd2). Sorts sensibly: by SORT_ROLE (a number or an ISO
    date) when it has one, the tick for 'Use', else the text in natural order;
    empty cells last; a folder sorts by its newest analysis."""

    def _key(self, col: int):
        it = self
        if self.data(0, FOLDER_ROLE) and self.childCount():
            it = self.child(0)
        if col == COL_USE:
            return (0, (0, 1.0 if it.checkState(COL_USE) == Qt.Checked else 0.0, ""))
        k = it.data(col, SORT_ROLE)
        if isinstance(k, (int, float)) and not isinstance(k, bool):
            return (0, (0, float(k), ""))
        t = str(k) if k not in (None, "") else it.text(col)
        return (0, _natural(t)) if t.strip() else (1, ())

    def __lt__(self, other):
        col = self.treeWidget().sortColumn() if self.treeWidget() else 0
        if self.data(0, GROUP_ROLE) is not None and other.data(0, GROUP_ROLE) is not None:
            a, b = self.data(0, SORT_ROLE) or 0, other.data(0, SORT_ROLE) or 0
            desc = self.treeWidget() is not None and \
                self.treeWidget().header().sortIndicatorOrder() == Qt.DescendingOrder
            return (a > b) if desc else (a < b)          # groups stay in their own order
        try:
            return self._key(col) < other._key(col)
        except (TypeError, AttributeError):
            return self.text(col) < other.text(col)


class _Cell:
    """One cell (row item + column) of the run tree, with the calls the list code
    makes on a table cell (V2.8: the list became a tree)."""
    __slots__ = ("it", "col")

    def __init__(self, it: QTreeWidgetItem, col: int) -> None:
        self.it, self.col = it, col

    def text(self) -> str:
        return self.it.text(self.col)

    def setText(self, t: str) -> None:                             # noqa: N802
        self.it.setText(self.col, t)

    def data(self, role):
        return self.it.data(self.col, role)

    def setData(self, role, v) -> None:                            # noqa: N802
        self.it.setData(self.col, role, v)

    def checkState(self):                                          # noqa: N802
        return self.it.checkState(self.col)

    def setCheckState(self, st) -> None:                           # noqa: N802
        self.it.setCheckState(self.col, st)

    def background(self):
        return self.it.background(self.col)

    def setBackground(self, b) -> None:                            # noqa: N802
        self.it.setBackground(self.col, b if isinstance(b, QBrush) else QBrush(b))

    def setForeground(self, b) -> None:                            # noqa: N802
        self.it.setForeground(self.col, b)

    def font(self):
        return self.it.font(self.col)

    def setFont(self, f) -> None:                                  # noqa: N802
        self.it.setFont(self.col, f)

    def toolTip(self) -> str:                                      # noqa: N802
        return self.it.toolTip(self.col)

    def setToolTip(self, t: str) -> None:                          # noqa: N802
        self.it.setToolTip(self.col, t)

    def column(self) -> int:
        return self.col


class _RunTree(QTreeWidget):
    """V2.8: the run list - a folder per group, the group's movies in it (a movie
    analysed more than once: a sub-folder of its analyses). Drag runs onto a
    group folder (or any row in it) to move them into that group."""

    def __init__(self, owner) -> None:
        super().__init__()
        self.owner = owner
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)

    def dragEnterEvent(self, e):                                   # noqa: N802
        e.acceptProposedAction() if e.source() is self else e.ignore()

    def dragMoveEvent(self, e):                                    # noqa: N802
        e.acceptProposedAction() if e.source() is self else e.ignore()

    def dropEvent(self, e):                                        # noqa: N802
        it = self.itemAt(e.position().toPoint())
        while it is not None and it.data(0, GROUP_ROLE) is None:
            it = it.parent()
        e.setDropAction(Qt.IgnoreAction)        # the tree is rebuilt, never moved by Qt
        e.accept()
        if it is not None:
            self.owner.put_selected_in(str(it.data(0, GROUP_ROLE)))


class _LineCombo(QComboBox):
    """The Cell line dropdown: no accidental change by scrolling the list."""

    def wheelEvent(self, e):                                       # noqa: N802
        if self.hasFocus():
            super().wheelEvent(e)
        else:
            e.ignore()


class _TickDelegate(QStyledItemDelegate):
    """The Use column: a light tick box with a dark tick, seen on dark and light
    lists alike."""

    def initStyleOption(self, opt, index):                         # noqa: N802
        super().initStyleOption(opt, index)
        opt.palette.setColor(QPalette.Base, QColor("#F2F2F2"))
        opt.palette.setColor(QPalette.Text, QColor("#000000"))
        opt.palette.setColor(QPalette.Window, QColor("#808080"))


def _first_number(text: str) -> Optional[float]:
    m = re.search(r"\d+(?:\.\d+)?", str(text))
    return float(m.group(0)) if m else None


class CompareWindow(QDialog):
    ASK_UNKNOWN = True          # ask for a colour of an unknown cell line (tests: False)

    def __init__(self, style: Optional[dict] = None, nd2_path: str = "", out_dir: str = "",
                 image_shape=None, n_timepoints: Optional[int] = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Compare / average runs")
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        self.resize(1400, 820)
        self.style = GS.coerce(style)
        self.out_dir = out_dir
        self._cells: Dict[str, Dict[int, _Cell]] = {}      # run path -> its cells
        self._items: Dict[str, _RunItem] = {}              # run path -> its tree row
        self._app_ver: Dict[str, str] = {}                 # run path -> 'PD4navV2.7' / 'PeterPiperV1.0' ...
        self._folders: Dict[str, _RunItem] = {}            # movie key -> its folder row
        self._gfolders: Dict[str, _RunItem] = {}           # group name -> its folder row
        self._group_names: List[str] = [str(g) for g in (load_prefs().get("group_names") or [])
                                        if str(g).strip()]
        self._hover_pts: list = []                         # (name, x, y, err text) per line
        self._combos: Dict[str, QComboBox] = {}     # run path -> its Cell line dropdown
        self._runs: Dict[str, C.Run] = {}           # loaded runs (by path)
        self._colours: Dict[str, str] = {}          # colours chosen here (by run path)
        self._group_colours: Dict[str, str] = {}    # ... and by group name
        self._labels: Dict[str, str] = {}
        self._groups: Dict[str, str] = {}
        self._nd2: Dict[str, str] = {}              # run path -> its .nd2 file name
        self._ident: Dict[str, dict] = {}           # run path -> what identifies its .nd2
        self._line_override: Dict[str, str] = {}    # run path -> cell line chosen (dropdown)
        self._dups: Dict[str, List[Tuple[str, str]]] = {}   # run path -> [(twin, reason)]
        self._index_fp: Optional[Dict[str, Tuple[str, int]]] = None
        self._remembered = load_remembered()
        prefs = load_prefs()
        cl = prefs.get("cell_lines")
        self._saved_lines: Dict[str, str] = dict(cl) if isinstance(cl, dict) else {}
        tb = prefs.get("table")
        self._table_prefs: dict = dict(tb) if isinstance(tb, dict) else {}
        gp = prefs.get("groups")
        self._saved_groups: Dict[str, str] = dict(gp) if isinstance(gp, dict) else {}
        self._preloaded: Dict[str, object] = {}   # V2.9: runs read in the background
        self._bulk, self._bulk_dirty = 0, False
        lb = prefs.get("labels")
        self._saved_labels: Dict[str, str] = dict(lb) if isinstance(lb, dict) else {}
        vw = prefs.get("view")
        self._view_prefs: dict = dict(vw) if isinstance(vw, dict) else {}
        self._sort_v25b = bool(prefs.get("sort_v25b"))
        self._order_v26 = bool(prefs.get("order_v26"))
        self._ckey: Dict[str, str] = {}             # run path -> its content key
        self._copies: Dict[str, List[str]] = {}     # run path -> identical files (not rows)
        self._saved_at: Dict[str, str] = {}         # run path -> ISO time it was saved
        self._dup_sets: List[List[str]] = []        # every set of runs from one .nd2
        self._asked: set = set()
        self._unknown: list = []
        self._unknown_custom: Dict[str, str] = {}
        self._busy = False
        self._restoring = False
        self._widths_touched: set = set()
        self.saved: List[str] = []

        lay = QVBoxLayout(self)
        lay.addWidget(W.wrapped_label(
            "1. Tick the runs to plot (each run = one dish; ticked = bold = plotted). The list "
            "is in folders by group; a ▸ sub-folder holds the analyses of one .nd2 - tick one. "
            "2. For replicates: '+ New group', then drag runs onto its folder (or select them "
            "and 'Put selected runs in'); Show 'Groups - mean of dish means'. 3. Say what to "
            "plot below. Drag the dividers to resize. Hover anything for help.",
            muted=True))
        self.lbl_dup = QLabel("")
        self.lbl_dup.setWordWrap(True)
        self.lbl_dup.setStyleSheet("QLabel { color: #FFFFFF; background: #B00020; "
                                   "font-weight: bold; padding: 6px; border-radius: 3px; }")
        self.lbl_dup.setVisible(False)
        lay.addWidget(self.lbl_dup)
        self.lbl_missing = QLabel("")             # V3.0: runs not on this computer
        self.lbl_missing.setWordWrap(True)
        self.lbl_missing.setProperty("role", "warn")
        self.lbl_missing.setVisible(False)
        lay.addWidget(self.lbl_missing)
        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)
        self.hsplit = split
        lay.addWidget(split, 1)


        # V2.8: the list (top) and the plot settings (bottom, scrollable) with a
        # divider you can drag; neither part can be dragged away to nothing
        self.vsplit = QSplitter(Qt.Vertical)
        self.vsplit.setChildrenCollapsible(False)
        top_w = QWidget()
        ll = QVBoxLayout(top_w)
        ll.setContentsMargins(0, 0, 0, 0)
        bot_w = QWidget()
        bl = QVBoxLayout(bot_w)
        bl.setContentsMargins(0, 0, 0, 0)
        ll.setContentsMargins(0, 0, 0, 0)
        # V2.8: the runs as a tree - a movie folder per .nd2 analysed more than once
        self.tree = _RunTree(self)
        self.tree.setColumnCount(len(HEADERS))
        self.tree.setHeaderLabels(HEADERS)
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tree.setRootIsDecorated(True)
        self.tree.setToolTip("Tick the runs to plot (ticked = bold = plotted). Each folder is a "
                             "group of replicate dishes; drag runs onto another group's folder "
                             "to move them. A ▸ sub-folder is one .nd2 analysed more than once - "
                             "tick one analysis. Double-click a name to rename it, a colour to "
                             "change it, a group's name to rename the group.")
        hdr = self.tree.header()
        hdr.setSectionResizeMode(QHeaderView.Interactive)
        hdr.setSectionsMovable(True)
        hdr.setSectionsClickable(True)
        hdr.setSortIndicatorShown(True)
        hdr.setSortIndicator(-1, Qt.AscendingOrder)                # list order until clicked
        hdr.setToolTip("Click a title to sort by it (again: the other way round); drag a "
                       "title to move the column. Remembered for next time.")
        # tick boxes that can be seen on a dark list (a delegate, not a style sheet:
        # a style sheet on the table would also restyle the Cell line dropdowns)
        self.tree.setItemDelegateForColumn(COL_USE, _TickDelegate(self.tree))
        self.tree.itemChanged.connect(self._item_changed)
        self.tree.itemDoubleClicked.connect(self._cell_double)
        ll.addWidget(self.tree, 1)
        # groups (V2.8): the list's folders - make them, drag runs in, no typing per run
        self.btn_put = W.button("Put selected runs in ▾", self._put_menu,
                                "Select runs in the list (Ctrl / Shift-click), then pick the "
                                "group - or drag them onto the group's folder.")
        ll.addWidget(W.row(
            QLabel("<b>Groups:</b>"),
            W.button("+ New group", self._new_group, "Make an empty group folder, then drag "
                     "runs into it."),
            self.btn_put,
            W.button("Take out of group", self._ungroup_selected)))
        ll.addWidget(W.row(                       # V3.0: two rows, nothing cut off
            W.button("Rename group", self._rename_group, "Click a group's folder first."),
            W.button("Delete group", self._delete_group, "Its runs stay, in 'No group'."),
            W.button("Group by cell line", self._group_by_line,
                     "Every ticked run without a group goes into the group of its cell line "
                     "(the Cell line column: read from the name or chosen by you).")))
        self._line_model = QStringListModel(self)
        known = CL.names()
        low = {n.lower() for n in known}
        custom = sorted({str(v) for v in self._saved_lines.values()
                         if str(v).lower() not in low and str(v) != UNKNOWN},
                        key=str.lower)
        self._line_model.setStringList([UNKNOWN] + sorted(known + custom, key=str.lower))
        ll.addWidget(W.row(
            W.button("Add run file...", self._add_clicked,
                     "A PeterPiper ROI or session file (.npz) saved with tracking."),
            W.button("My data is in...", self._my_data_is_in,
                     "Your runs that are not where they were saved (e.g. a profile brought from "
                     "another computer, or a moved data folder): point to the folder that holds "
                     "them now - each is matched exactly (same movie, file name and save time) "
                     "and the new place is remembered."),
            W.button("Find my runs in a folder...", self._find_in_folder,
                     "Look through a folder (and its subfolders, e.g. the lab's shared drive) "
                     "for your tracked runs - also ones made on another computer - and add "
                     "them to your list."),
            ))
        ll.addWidget(W.row(                       # V3.0: two rows, nothing cut off
            W.button("Remove from list", self._remove_clicked, "Only from this list; the "
                     "file is not touched."),
            W.button("Untick all", lambda: self.set_checked([])),
            W.button("Open all folders", self.tree.expandAll),
            W.button("Close all folders", self.tree.collapseAll)))

        box, f = W.group("What to show")
        self.cmb_mode = QComboBox()
        for key, text in MODES:
            self.cmb_mode.addItem(text, key)
            self.cmb_mode.setItemData(self.cmb_mode.count() - 1, MODE_TIPS[key], Qt.ToolTipRole)
        self.cmb_mode.setToolTip(
            "Each run: one line per dish (its cells). Groups - mean of dish means: the "
            "replicate statistic (each dish counts once; n = dishes). Groups - pooled cells: "
            "every cell of the group as one sample (n = cells) - for reference only, cells of "
            "one dish are not independent replicates.")
        self.cmb_mode.currentIndexChanged.connect(lambda _i: self._mode_changed())
        f.addRow("Show", self.cmb_mode)
        # V2.7: the plot builder - Y measure vs Time or vs another measure, an
        # optional right Y axis. The Y measure is kept in cmb_comp / cmb_q (not
        # shown), which every time-course path below reads.
        self.cmb_comp = QComboBox()
        self.cmb_comp.currentIndexChanged.connect(lambda _i: self._fill_quantities())
        self.cmb_q = QComboBox()
        self.cmb_q.currentIndexChanged.connect(lambda _i: self.refresh())
        self.cmb_comp.hide()
        self.cmb_q.hide()
        self.row_y = MeasureRow(None)
        self.row_y.setToolTip("What goes on the Y axis.")
        self.row_y.changed.connect(self._y_changed)
        f.addRow("Plot", self.row_y)
        self.row_x = MeasureRow([("Time", XP.TIME), ("Timepoint", XP.TIMEPOINT)])
        self.row_x.setToolTip("vs = what goes on the X axis: Time (the usual time course), "
                              "Timepoint (frame numbers), or another measure of the same cells.")
        self.row_x.changed.connect(self._spec_changed)
        f.addRow("vs", self.row_x)
        self.row_y2 = MeasureRow([("none", "")])
        self.row_y2.setToolTip("Optional: a second measure on a right Y axis (dashed lines), "
                               "against the same X - for two measures with different units.")
        self.row_y2.changed.connect(self._spec_changed)
        self.lbl_y2 = QLabel("Right Y axis")
        f.addRow(self.lbl_y2, self.row_y2)
        self.cmb_points = QComboBox()
        for key, text in XP.POINTS:
            self.cmb_points.addItem(text, key)
            self.cmb_points.setItemData(self.cmb_points.count() - 1, XP.POINTS_EXPLAIN[key],
                                        Qt.ToolTipRole)
        self.cmb_points.setToolTip("Trajectory: one point per timepoint (mean of the cells, "
                                   "error bars on X and Y), joined in time order. Each cell: "
                                   "one dot per cell (per dish for 'mean of dish means').")
        self.cmb_points.currentIndexChanged.connect(lambda _i: self._spec_changed())
        self.sp_at = QSpinBox()
        self.sp_at.setRange(-100000, 100000)
        self.sp_at.setPrefix("frame ")
        self.sp_at.setToolTip("Frames after each run's baseline (0 = the baseline timepoint).")
        self.sp_to = QSpinBox()
        self.sp_to.setRange(-100000, 100000)
        self.sp_to.setPrefix("to ")
        for sp in (self.sp_at, self.sp_to):
            sp.valueChanged.connect(lambda _v: self._spec_changed())
        self.lbl_points = QLabel("Points")
        self.wid_points = W.row(self.cmb_points, self.sp_at, self.sp_to)
        f.addRow(self.lbl_points, self.wid_points)
        self.lbl_sentence = W.wrapped_label("")
        self.lbl_sentence.setStyleSheet("font-weight: bold;")
        f.addRow(self.lbl_sentence)
        self.lbl_problem = W.wrapped_label("")           # V2.8: plots that make no sense
        self.lbl_problem.setProperty("role", "danger")
        self.lbl_problem.setVisible(False)
        f.addRow(self.lbl_problem)
        self.chk_own_base = QCheckBox("Each run's own saved baseline")
        self.chk_own_base.setChecked(True)
        self.chk_own_base.setToolTip("Untick to use the same baseline timepoint for every run.")
        self.chk_own_base.toggled.connect(self._base_toggled)
        self.sp_base = QSpinBox()
        self.sp_base.setRange(1, 100000)
        self.sp_base.setPrefix("T")
        self.sp_base.setEnabled(False)
        self.sp_base.valueChanged.connect(lambda _v: self.refresh())
        f.addRow("Baseline", W.row(self.chk_own_base, self.sp_base))
        self.cmb_err = QComboBox()
        for v in GS.ERRORS:
            self.cmb_err.addItem({"SEM": "mean ± SEM", "SD": "mean ± SD", "95% CI":
                                  "mean ± 95% CI", "none": "mean only"}[v], v)
        for i, v in enumerate(GS.ERRORS):
            self.cmb_err.setItemData(i, ERROR_TIPS.get(v, ""), Qt.ToolTipRole)
        self.cmb_err.setCurrentIndex(max(0, self.cmb_err.findData(self.style.error)))
        self.cmb_err.setToolTip("SEM = SD / sqrt(n), SD with n - 1; n = cells (each run, "
                                "pooled) or dishes (mean of dish means) with a value at "
                                "that time.")
        # V3.0: one error choice everywhere - your graph look's (mean ± SD by default),
        # shared with the main window, the exports and the Prism files
        self.cmb_err.setCurrentIndex(max(0, self.cmb_err.findData(self.style.error)))
        self.cmb_err.currentIndexChanged.connect(self._err_changed)
        f.addRow("Error", self.cmb_err)
        self.ed_title = QLineEdit()
        self.ed_title.setPlaceholderText("automatic: <quantity> - <compartment>")
        self.ed_title.textChanged.connect(lambda _t: self.refresh())
        f.addRow("Title", self.ed_title)
        from .. import kinetics as K
        self.cmb_graph = QComboBox()
        self.cmb_graph.addItem("Time course", GRAPH_TIME)
        self.cmb_graph.setItemData(0, "The measure (Y) against the X you chose - lines, one per "
                                      "run or group.", Qt.ToolTipRole)
        for key, name, _u in K.PARAMS:
            self.cmb_graph.addItem(f"Kinetics: {name}", key)
            self.cmb_graph.setItemData(self.cmb_graph.count() - 1,
                                       KIN_TIPS.get(key, "") + " Each dish is a dot; groups show "
                                       "the mean ± the chosen error across dishes. Needs X = Time.",
                                       Qt.ToolTipRole)
        self.cmb_graph.setToolTip(
            "Time course, or how fast each dish responds after its baseline (from the dish "
            "mean curve, nothing fitted): t½ max = first time the curve is half-way from the "
            "baseline level to its maximum; initial rise slope = straight line from the "
            "baseline to the first frame past half-max; maximum rate = steepest frame-to-frame "
            "step. Each dish is a dot; groups show the mean ± the chosen error across dishes.")
        self.cmb_graph.currentIndexChanged.connect(lambda _i: self._view_changed())
        f.addRow("Graph", self.cmb_graph)
        self.chk_window = QCheckBox("Kinetics: the same time window for every dish "
                                    "(to the end of the shortest one)")
        self.chk_window.setChecked(True)
        self.chk_window.setToolTip(
            "On (recommended): every dish is measured from its baseline to the same time - "
            "the end of the shortest dish shown - so a movie that simply ran longer does not "
            "get a bigger maximum and a later t½. Off: each dish to its own last frame.")
        self.chk_window.toggled.connect(lambda _on: self._view_changed())
        f.addRow("", self.chk_window)
        bl.addWidget(box)

        # V2.8: the file types and kinetics graphs live in the Save dialog
        self._save_opts = QDialog(self)
        self._save_opts.setWindowTitle("Save")
        sl = QVBoxLayout(self._save_opts)
        sl.addWidget(W.wrapped_label("Save what is shown as these files (nothing is "
                                     "overwritten; a log of every save: 'Saved files...')."))
        self.chk_fmt: Dict[str, QCheckBox] = {}
        fr = QWidget()
        fl = QGridLayout(fr)
        fl.setContentsMargins(0, 0, 0, 0)
        for i, (key, text, on) in enumerate(FORMATS):
            cb = QCheckBox(text)
            cb.setChecked(on)
            self.chk_fmt[key] = cb
            cb.toggled.connect(lambda _on: self._save_view_prefs())
            fl.addWidget(cb, i // 4, i % 4)
        sl.addWidget(fr)
        self.chk_kin: Dict[str, QCheckBox] = {}
        kr = QWidget()
        kl = QGridLayout(kr)
        kl.setContentsMargins(0, 0, 0, 0)
        kl.addWidget(QLabel("Kinetics graphs:"), 0, 0)
        for i, (key, name, _u) in enumerate(K.PARAMS):
            cb = QCheckBox(name)
            cb.setChecked(key in K.DEFAULT_SAVE)
            cb.setToolTip("Also save this kinetics graph (each dish a dot, mean ± error across "
                          "dishes) in every ticked picture format and as a .prism with the graph "
                          "made; the kinetics tables go into the CSV / Excel files.")
            cb.toggled.connect(lambda _on: self._save_view_prefs())
            self.chk_kin[key] = cb
            kl.addWidget(cb, 1 + i // 3, i % 3)
        sl.addWidget(kr)
        sl.addWidget(W.row(W.button("Choose name and folder...", self._save_opts.accept,
                                    strong=True),
                           W.button("Cancel", self._save_opts.reject)))
        box, f = W.group("Save")
        self.btn_save = W.button(
            "Save...", self._save_clicked,
            "One .prism in the PeterPiper template look (one data set per line, legend; for groups "
            "the dish means are the replicates, so Prism computes mean ± SEM across dishes), "
            "the picture as shown (PNG / JPEG / SVG / TIFF / PDF) and the tables (CSV / Excel: "
            "the plotted numbers; for groups also each dish's mean and the pooled cells). "
            "Existing files are never replaced.", strong=True)
        f.addRow(W.row(self.btn_save, W.button(
            "Saved files...", self._saved_files,
            "Every file PeterPiper saved (exports, comparisons, batch runs), newest first - "
            "click to open it or its folder."), W.button(
            "Prism style templates...", self._templates,
            "Your two Prism template files: change the look in Prism once, every .prism "
            "uses it from then on.")))
        f.addRow(W.row(
            W.button("Save plot settings...", self._save_plot_settings,
                     "This plot (what is plotted against what, what is shown, error, baseline, "
                     "title, file types, kinetics graphs) as a named settings file."),
            W.button("Load plot settings...", self._load_plot_settings,
                     "Plot the ticked runs the way a saved settings file says."),
            W.button("Batch save...", self._batch_save,
                     "Pick several saved plot settings: each is plotted for the ticked runs and "
                     "saved (every ticked file type) into one folder.")))
        bl.addWidget(box)
        bl.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(bot_w)
        scroll.setMinimumHeight(160)
        top_w.setMinimumHeight(160)
        self.vsplit.addWidget(top_w)
        self.vsplit.addWidget(scroll)
        self.vsplit.setSizes([520, 480])
        left = self.vsplit
        left.setMinimumWidth(420)
        split.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        pg.setConfigOption("background", "w")
        pg.setConfigOption("foreground", "k")
        # V2.8: what the graph shows - toggles, reset, the hover readout
        self.chk_yerr = QCheckBox("Y error bars")
        self.chk_yerr.setChecked(True)
        self.chk_yerr.setToolTip("Error bars (or the band) on the Y values: the error chosen "
                                 "under 'Error'.")
        self.chk_xerr = QCheckBox("X error bars")
        self.chk_xerr.setToolTip("When X is a measure: error bars on the X values too (off by "
                                 "default - with many cells they are wide and hide the curve).")
        self.chk_cells = QCheckBox("Each cell")
        self.chk_cells.setToolTip("Draw every cell (each run, pooled) or every dish (mean of dish "
                                  "means) faintly behind its mean, to see the spread and any "
                                  "odd cell.")
        for cb in (self.chk_yerr, self.chk_xerr, self.chk_cells):
            cb.toggled.connect(lambda _on: self.refresh())
        self.btn_reset = W.button("Reset zoom", self._reset_zoom,
                                  "Drag with the left mouse button to move, scroll to zoom; "
                                  "this shows everything again.")
        rl.addWidget(W.row(self.chk_yerr, self.chk_xerr, self.chk_cells, self.btn_reset))
        self.plot = pg.PlotWidget()
        self.plot.setMenuEnabled(False)
        self.legend = self.plot.addLegend(offset=(10, 10))
        for ax in ("left", "bottom", "right"):     # the values as they are (no 'x0.001')
            self.plot.getAxis(ax).enableAutoSIPrefix(False)
        self.legend.setToolTip("Click a legend entry to hide / show that line.")
        rl.addWidget(self.plot, 1)
        self.lbl_hover = W.wrapped_label("Hover a point to read its values. Click a legend "
                                         "entry to hide that line.", muted=True)
        rl.addWidget(self.lbl_hover)
        self.plot.scene().sigMouseMoved.connect(self._hover)
        self.lbl_info = W.wrapped_label("", muted=True)
        rl.addWidget(self.lbl_info)
        self.lbl_warn = W.wrapped_label("")
        self.lbl_warn.setProperty("role", "warn")
        self.lbl_warn.setVisible(False)
        rl.addWidget(self.lbl_warn)
        right.setMinimumWidth(360)
        split.addWidget(right)
        split.setSizes([700, 700])
        self.setMinimumSize(900, 560)

        self._width_timer = QTimer(self)
        self._width_timer.setSingleShot(True)
        self._width_timer.setInterval(400)
        self._width_timer.timeout.connect(self._save_table_state)
        self._restore_table_layout()
        self._fill_default_list(nd2_path, out_dir, image_shape, n_timepoints)
        self._missing_note()
        self._fit_columns()
        self._restore_sort()
        self._restore_view()
        sp_ = self._table_prefs.get("splits")
        if isinstance(sp_, list) and len(sp_) == 2:
            for w, sz in ((self.hsplit, sp_[0]), (self.vsplit, sp_[1])):
                if isinstance(sz, list) and len(sz) == 2 and all(int(v) > 100 for v in sz):
                    w.setSizes([int(v) for v in sz])
        for w in (self.hsplit, self.vsplit):
            w.splitterMoved.connect(lambda *_a: self._width_timer.start())
        hdr.sectionMoved.connect(lambda *_a: self._save_table_state())
        hdr.sortIndicatorChanged.connect(lambda *_a: self._save_table_state())
        hdr.sectionResized.connect(self._section_resized)
        self.refresh()

    # ------------------------------------------------------ list layout
    def _restore_table_layout(self) -> None:
        """Column order and widths from last time (by column title)."""
        hdr = self.tree.header()
        st = self._table_prefs
        self._restoring = True
        try:
            order = [HEADERS.index(n) for n in (st.get("order") or []) if n in HEADERS]
            if not self._order_v26:
                # V2.6 (once): Version and Saved right after the name, where they are seen
                order = [c for c in order if c not in (COL_VER, COL_SAVED)]
                at = order.index(COL_LABEL) + 1 if COL_LABEL in order else len(order)
                order[at:at] = [COL_VER, COL_SAVED]
                self._order_v26 = True
                update_prefs(order_v26=True)
            for vis, logical in enumerate(order):
                hdr.moveSection(hdr.visualIndex(logical), vis)
            for n, w in (st.get("widths") or {}).items():
                try:
                    if n in HEADERS and int(w) >= 16:
                        self.tree.setColumnWidth(HEADERS.index(n), int(w))
                except (TypeError, ValueError):
                    pass
        finally:
            self._restoring = False

    def _fit_columns(self) -> None:
        """Columns without a remembered width: fitted to their contents."""
        saved = {n for n in (self._table_prefs.get("widths") or {}) if n in HEADERS}
        self._restoring = True
        try:
            for c, n in enumerate(HEADERS):
                if n in saved:
                    continue
                self.tree.resizeColumnToContents(c)
                w = self.tree.columnWidth(c)
                lo, hi = {COL_LINE: (150, 220), COL_LABEL: (140, 280), COL_FILE: (120, 280),
                          COL_SAME: (110, 240), COL_GROUP: (150, 240)}.get(c, (30, 260))
                self.tree.setColumnWidth(c, max(lo, min(hi, w)))
        finally:
            self._restoring = False

    def _restore_sort(self) -> None:
        """Sort as last time (or keep the list order), then sort on every click."""
        hdr = self.tree.header()
        sort = self._table_prefs.get("sort")
        self._restoring = True
        try:
            if not self._sort_v25b or not (isinstance(sort, (list, tuple)) and len(sort) == 2
                                           and sort[0] in HEADERS):
                sort = ["Version", "desc"]          # newest analyses on top (V2.6 default)
                self._sort_v25b = True
                update_prefs(sort_v25b=True)
            if isinstance(sort, (list, tuple)) and len(sort) == 2 and sort[0] in HEADERS:
                hdr.setSortIndicator(HEADERS.index(sort[0]), Qt.DescendingOrder
                                     if sort[1] == "desc" else Qt.AscendingOrder)
            self.tree.setSortingEnabled(True)
        finally:
            self._restoring = False

    def _section_resized(self, logical: int, _old: int, _new: int) -> None:
        if self._restoring or self._busy:
            return
        self._widths_touched.add(logical)
        self._width_timer.start()

    def _save_table_state(self) -> None:
        """Column order, sort and the widths the user set -> compare_window.json."""
        if self._restoring:
            return
        hdr = self.tree.header()
        order = [HEADERS[hdr.logicalIndex(v)] for v in range(hdr.count())]
        sec = hdr.sortIndicatorSection()
        sort = [HEADERS[sec], "desc" if hdr.sortIndicatorOrder() == Qt.DescendingOrder
                else "asc"] if 0 <= sec < len(HEADERS) else None
        widths = dict(self._table_prefs.get("widths") or {})
        for c in self._widths_touched:
            widths[HEADERS[c]] = int(self.tree.columnWidth(c))
        self._table_prefs = dict(order=order, sort=sort, widths=widths,
                                 splits=[list(self.hsplit.sizes()), list(self.vsplit.sizes())])
        update_prefs(table=self._table_prefs)

    def done(self, r: int) -> None:                                # noqa: D401
        self._flush_state()
        super().done(r)

    def closeEvent(self, e) -> None:                               # noqa: N802
        self._flush_state()
        super().closeEvent(e)

    def _flush_state(self) -> None:
        if self._width_timer.isActive():
            self._width_timer.stop()
        self._save_table_state()
        self._save_view_prefs()

    # ------------------------------------------- remembered choices (V2.6)
    def _group_keys(self, path: str) -> List[str]:
        """Where a run's group is remembered: its file, then its .nd2."""
        q = (self._ident.get(path) or {}).get("quick")
        return [f"path:{self._norm(path)}"] + ([f"fp:{q}"] if q else [])

    def _remember_group(self, path: str) -> None:
        g = self._groups.get(path, "").strip()
        for k in self._group_keys(path):
            if g:
                self._saved_groups[k] = g
            else:
                self._saved_groups.pop(k, None)
        d = load_prefs().get("groups")
        d = dict(d) if isinstance(d, dict) else {}
        for k in self._group_keys(path):
            if g:
                d[k] = g
            else:
                d.pop(k, None)
        update_prefs(groups=d)

    def _remember_label(self, path: str) -> None:
        k = f"path:{self._norm(path)}"
        lab = self._labels.get(path, "")
        d = load_prefs().get("labels")
        d = dict(d) if isinstance(d, dict) else {}
        if lab and lab != Path(self._nd2.get(path, path)).stem:
            d[k] = lab
        else:
            d.pop(k, None)
        self._saved_labels = d
        update_prefs(labels=d)

    def _save_view_prefs(self) -> None:
        """Ticked runs, what is shown and the kinetics choices -> compare_window.json."""
        if self._restoring or not hasattr(self, "chk_kin"):
            return
        self._view_prefs = dict(
            ticked=[f"path:{self._norm(p)}" for p in self._paths if self._is_on(p)],
            mode=self.mode(), comp=self.cmb_comp.currentData() or "",
            quantity=self.cmb_q.currentText(), graph=self.graph(),
            spec=(self.spec().to_dict() if self.spec() else None),
            kinetics=[k for k, cb in self.chk_kin.items() if cb.isChecked()],
            same_window=self.chk_window.isChecked(), error=self.style.error)
        update_prefs(view=self._view_prefs)

    def _restore_view(self) -> None:
        """Tick the runs ticked last time and show what was shown."""
        v = self._view_prefs
        if not v:
            return
        self._restoring = True
        try:
            kin = v.get("kinetics")
            if isinstance(kin, list):
                for k, cb in self.chk_kin.items():
                    cb.setChecked(k in kin)
            if isinstance(v.get("same_window"), bool):
                self.chk_window.setChecked(v["same_window"])
            i = self.cmb_graph.findData(v.get("graph") or GRAPH_TIME)
            self.cmb_graph.setCurrentIndex(max(0, i))
            i = self.cmb_mode.findData(v.get("mode") or "runs")
            self.cmb_mode.setCurrentIndex(max(0, i))
            want = set(v.get("ticked") or [])
            for p in self._paths:
                if any(f"path:{self._norm(q)}" in want for q in [p] + self._copies.get(p, [])):
                    self._use(p).setCheckState(Qt.Checked)          # loads the run
            i = self.cmb_comp.findData(v.get("comp"))
            if i >= 0:
                self.cmb_comp.setCurrentIndex(i)
            i = self.cmb_q.findText(str(v.get("quantity") or ""))
            if i >= 0:
                self.cmb_q.setCurrentIndex(i)
            self._sync_y_row()
            sp = XP.Spec.from_dict(v.get("spec"))
            if sp is not None:
                self.set_spec(sp)
        finally:
            self._restoring = False

    # ------------------------------------------------------------ the list
    @property
    def _paths(self) -> List[str]:
        """The runs in the list, in the order shown (top to bottom, through the
        group folders and movie sub-folders)."""
        out = []

        def walk(it):
            p = it.data(0, PATH_ROLE)
            if p and it.data(0, FOLDER_ROLE) is None and it.data(0, GROUP_ROLE) is None:
                out.append(str(p))
            for j in range(it.childCount()):
                walk(it.child(j))
        for i in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(i))
        return out

    def _use(self, path: str) -> _Cell:
        return self._cells[path][COL_USE]

    def _is_on(self, path: str) -> bool:
        return path in self._cells and self._use(path).checkState() == Qt.Checked

    def _fill_default_list(self, nd2_path, out_dir, image_shape, n_timepoints) -> None:
        from ..roifile import read_summary

        def read_all(progress):                     # V2.9: in the background, with a bar
            paths = []
            if nd2_path:
                progress(None, "Looking for earlier analyses of this movie...")
                try:
                    prev = [r for r in history.find_previous_runs(
                        nd2_path, out_dir, image_shape, n_timepoints) if r.tracked]
                    paths += [r.path for r in sorted(prev, key=lambda r: r.kind == "session")]
                except Exception:                                  # noqa: BLE001
                    pass
            # files you saved (export ROI files, Save ROIs now) first: an autosaved
            # session with the same contents then joins that file's row (one analysis
            # = one row)
            idx = history.indexed_runs()
            paths += [r["path"] for r in idx if r.get("kind") != "session"]
            paths += [r["path"] for r in idx if r.get("kind") == "session"]
            for i, p in enumerate(paths):           # each file read once (remembered)
                progress(i / max(1, len(paths)), f"Run {i + 1} of {len(paths)}: {Path(p).name}")
                read_summary(p)
            return paths
        paths = W.run_with_progress(self.parent(), "Reading your saved runs", read_all)
        for p in paths:
            self.add_run_file(p, quiet=True, check=False)

    def _norm(self, p: str) -> str:
        return os.path.normcase(os.path.abspath(plain_path(str(p))))

    def add_run_file(self, path: str, quiet: bool = False, check: bool = True) -> bool:
        """Add a run to the list (ticked when check). False + a plain message
        (unless quiet) when it is not a tracked PeterPiper run."""
        from ..roifile import read_summary
        key = self._norm(path)
        for p in self._cells:
            if key in [self._norm(q) for q in [p] + self._copies.get(p, [])]:
                if check:
                    self._use(p).setCheckState(Qt.Checked)
                return True
        s = read_summary(path)
        if s is None or not s.get("tracked"):
            if not quiet:
                QMessageBox.warning(self, "Compare runs", (
                    f"{Path(path).name} is not a PeterPiper ROI / session file with tracking. "
                    "Save one from the main window after TRACK (File > Save ROIs now) - the "
                    "autosaved sessions in PeterPiper_sessions work too."))
            return False
        path = str(s["path"])
        ck = str(s.get("content_key") or "")
        same = next((p for p, k in self._ckey.items() if ck and k == ck), None)
        if same is not None:
            # the same analysis saved twice (export ROI file + autosaved session, or a
            # copy): identical ROIs, tracking, measurements and settings - one row
            self._copies.setdefault(same, []).append(path)
            self._show_files(same)
            if check:
                self._use(same).setCheckState(Qt.Checked)
            return True
        self._ckey[path] = ck
        self._insert_row(path, s)
        self._show_files(path)
        self._mark_duplicates()
        if check:
            self._use(path).setCheckState(Qt.Checked)               # loads + refreshes
        return True

    # ...................................................... one row
    def _index_info(self) -> Dict[str, Tuple[str, int]]:
        """{normalised run path: (.nd2 fingerprint, .nd2 size)} from this
        computer's index of runs (for files that do not hold a fingerprint)."""
        if self._index_fp is None:
            self._index_fp = {}
            try:
                for key, ent in history._load_index().items():     # noqa: SLF001 (read only)
                    for r in ent.get("runs", []):
                        self._index_fp[self._norm(r["path"])] = (str(key),
                                                                  int(ent.get("size") or 0))
            except Exception:                                      # noqa: BLE001
                pass
        return self._index_fp

    def _identify(self, path: str, s: dict) -> dict:
        """What says which .nd2 this run was made from (compare.same_nd2)."""
        fp = s.get("fingerprint") if isinstance(s.get("fingerprint"), dict) else {}
        quick = str(fp.get("quick") or "")
        try:
            size = int(fp.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        if not quick:
            q2, s2 = self._index_info().get(self._norm(path), ("", 0))
            quick, size = q2, size or s2
        nd2p = str(s.get("nd2_path") or "")
        return dict(key=path, quick=quick, size=size,
                    nd2_path=self._norm(nd2p) if nd2p else "",
                    nd2_name=Path(str(s.get("nd2") or "")).name.lower())

    def run_key(self, path: str) -> str:
        """The key the chosen cell line is remembered under: the .nd2's
        fingerprint (so every analysis of that movie shares it), else the run
        file's normalised path."""
        q = (self._ident.get(path) or {}).get("quick")
        return f"fp:{q}" if q else f"path:{self._norm(path)}"

    def _insert_row(self, path: str, s: dict) -> None:
        """A row for this run (s: roifile.read_summary(), any key may be missing)."""
        from .historydlg import when_text
        nd2 = str(s.get("nd2") or "") or Path(path).name
        self._nd2[path] = nd2
        self._ident[path] = self._identify(path, s)
        lab = self._saved_labels.get(f"path:{self._norm(path)}")
        from .. import users                       # V2.9: another user's run, opened on
        who = users.owner_of(path, s.get("user"))  # purpose, says whose it is
        theirs = f" ({who}'s)" if who and users.current() and             who.lower() != users.current().lower() else ""
        self._labels.setdefault(path, (str(lab) if lab else Path(nd2).stem) + theirs)
        g = next((self._saved_groups[k] for k in self._group_keys(path)
                  if self._saved_groups.get(k)), "")
        self._groups.setdefault(path, str(g))
        saved = str(s.get("saved") or "")
        if not saved:
            try:
                from datetime import datetime
                saved = datetime.fromtimestamp(os.path.getmtime(path)).isoformat(
                    timespec="seconds")
            except OSError:
                saved = ""
        self._saved_at[path] = saved
        av = str(s.get("version") or "")
        app = str(s.get("app") or "PD4nav")           # PeterPiper 1.0: files name the app
        self._app_ver[path] = f"{app}V{'.'.join(av.split('.')[:2])}" if av else ""
        ov = self._saved_lines.get(self.run_key(path))
        if ov:
            self._line_override[path] = str(ov)
        was = self.tree.isSortingEnabled()
        self.tree.setSortingEnabled(False)           # rows must not move while being made
        self._busy = True
        try:
            row = _RunItem()
            row.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable |
                         Qt.ItemIsEditable | Qt.ItemIsDragEnabled)
            items: Dict[int, _Cell] = {}
            for c in range(len(HEADERS)):
                row.setData(c, PATH_ROLE, path)
                row.setToolTip(c, path)
                items[c] = _Cell(row, c)
            items[COL_USE].setCheckState(Qt.Unchecked)
            items[COL_USE].setToolTip("Tick to plot this run.")
            items[COL_COLOUR].setToolTip("Double-click to choose the colour (remembered for "
                                         "this name).")
            items[COL_LABEL].setText(self._labels[path])
            items[COL_LABEL].setToolTip("The name in the graph's legend - double-click to "
                                        "change it.")
            items[COL_GROUP].setText(self._groups[path])
            items[COL_GROUP].setToolTip("Its group of replicate dishes - set in the Groups "
                                        "panel on the right (drag the run onto a group).")
            items[COL_FILE].setText(nd2)
            items[COL_VER].setToolTip("The app and version that saved this analysis (PD4nav, or PeterPiper from 1.0 on); for a movie "
                                      "analysed more than once also which analysis it is (by "
                                      "the date saved).")
            nd2p = str(s.get("nd2_path") or "")
            items[COL_DIR].setText(Path(nd2p).parent.name if nd2p else "")
            items[COL_DIR].setToolTip(f"The folder of the .nd2 movie:\n{nd2p}" if nd2p else
                                      "The .nd2's folder is not recorded in this run file.")
            items[COL_VER].setToolTip("Which analysis of this .nd2 this is, by the date it was "
                                      "saved (newest = the latest analysis).")
            n = s.get("n_cells")
            items[COL_CELLS].setText(str(n) if n not in (None, "") else "")
            if isinstance(n, (int, float)):
                items[COL_CELLS].setData(SORT_ROLE, float(n))
            if s.get("baseline"):
                items[COL_BASE].setText(f"T{s['baseline']}")
                v = _first_number(str(s["baseline"]))
                if v is not None:
                    items[COL_BASE].setData(SORT_ROLE, v)
            saved = str(s.get("saved") or "")
            items[COL_SAVED].setText(when_text(saved) if saved else "")
            if saved:
                items[COL_SAVED].setData(SORT_ROLE, saved)          # ISO: sorts by date
            self._cells[path] = items
            self._items[path] = row
            gf = getattr(self, "_gfolders", {}).get(self._groups[path].strip() or "")
            if gf is not None:
                gf.addChild(row)
            else:
                self.tree.addTopLevelItem(row)
            self._attach_combo(path)
        finally:
            self._busy = False
            self.tree.setSortingEnabled(was)
        self._show_line(path)

    def _attach_combo(self, path: str) -> None:
        """The Cell line dropdown of a row (made again when the row moves into or
        out of a movie folder: Qt deletes a row's widgets when it is moved)."""
        cb = _LineCombo()
        cb.setEditable(True)
        cb.setInsertPolicy(QComboBox.NoInsert)
        cb.setModel(self._line_model)
        cb.setFocusPolicy(Qt.StrongFocus)
        cb.setMaxVisibleItems(20)
        cb.textActivated.connect(lambda t, p=path: self._line_chosen(p, t, True))
        cb.lineEdit().editingFinished.connect(
            lambda p=path, w=cb: self._line_chosen(p, w.currentText(), False))
        self._combos[path] = cb
        self.tree.setItemWidget(self._items[path], COL_LINE, cb)

    def _show_files(self, path: str) -> None:
        """The '.nd2 file' cell's tooltip: the run file and any identical copies."""
        if path not in self._cells:
            return
        cp = self._copies.get(path, [])
        tip = f"Run file:\n{plain_path(path)}"
        if cp:
            tip += ("\n\nThe same analysis was also saved as (identical ROIs, tracking, "
                    "measurements and settings - listed once):\n" +
                    "\n".join(plain_path(q) for q in cp))
        self._cells[path][COL_FILE].setToolTip(tip)

    def _add_clicked(self) -> None:
        paths = self._paths
        folder = self.out_dir or (str(Path(paths[-1]).parent) if paths else "")
        paths, _f = QFileDialog.getOpenFileNames(self, "Add run file", folder,
                                                 "PeterPiper ROI / session files (*.npz)")
        for p in paths:
            self.add_run_file(p)

    def _my_data_is_in(self) -> None:
        """V3.0 portable profiles: runs in your list whose files are elsewhere on this
        computer are found again under a folder you point to (history.relocate_runs)."""
        n_missing = len(history.missing_runs())
        if not n_missing:
            QMessageBox.information(self, "My data is in...", "Every run in your list is where "
                                    "it was saved - nothing to find.")
            return
        folder = QFileDialog.getExistingDirectory(
            self, f"Where are your runs now? ({n_missing} not found on this computer)",
            self.out_dir or "")
        if not folder:
            return
        got = W.run_with_progress(self, f"Looking for your runs in {Path(folder).name}",
                                  lambda p: history.relocate_runs(folder, p))
        before = set(self._paths)
        for r in history.indexed_runs():
            if r["path"] not in before:
                self.add_run_file(r["path"], quiet=True, check=False)
        QMessageBox.information(
            self, "My data is in...",
            f"Found {got['found']} of your runs under {folder}; their new place is remembered."
            + (f" {got['still_missing']} are still not on this computer (another folder? Try "
               f"again)." if got["still_missing"] else ""))
        self._missing_note()

    def _missing_note(self) -> None:
        """V3.0: how many of your runs are not on this computer (a profile from
        another computer) - with what to do."""
        n = len(history.missing_runs())
        if hasattr(self, "lbl_missing"):
            self.lbl_missing.setText(f"{n} of your runs are not on this computer (saved "
                                     f"elsewhere, or moved) - 'My data is in...' finds them."
                                     if n else "")
            self.lbl_missing.setVisible(bool(n))

    def _find_in_folder(self) -> None:
        """V3.0: your runs anywhere under a folder (other computers, shared drives)."""
        start = self.out_dir or (str(Path(self._paths[-1]).parent) if self._paths else "")
        folder = QFileDialog.getExistingDirectory(self, "Find my runs in a folder", start)
        if not folder:
            return
        before = set(self._paths)

        def find(progress):                         # in the background, with a bar
            from ..roifile import read_summary
            got = history.find_runs_in_folder(folder, progress)
            for i, p in enumerate(got["mine"]):     # remembered in your list of runs
                progress((i + 1) / max(1, len(got["mine"])), f"Adding {Path(p).name}")
                s = read_summary(p) or {}
                nd2 = str(s.get("nd2_path") or "")
                history.record_run(nd2 if nd2 and Path(nd2).exists() else "", p, s)
            return got
        got = W.run_with_progress(self, f"Looking for your runs in {Path(folder).name}", find)
        for p in got["mine"]:
            if p not in before:
                self.add_run_file(p, quiet=True, check=False)
        added = len([p for p in self._paths if p not in before])
        msg = (f"Found {len(got['mine'])} of your tracked runs in {folder}: {added} added to "
               f"your list (the rest were already there or are the same analysis)."
               + (f" {got['others']} other users' runs were not listed." if got["others"]
                  else "")
               + (f" {got['untracked']} files without tracking were skipped." if
                  got["untracked"] else ""))
        QMessageBox.information(self, "Find my runs in a folder", msg)

    def _remove_clicked(self) -> None:
        for p in self._selected_paths():
            self.remove_run(p)
        self._mark_duplicates()
        self._recompute()

    def remove_run(self, path: str) -> None:
        """Take a run off the list (its file is not touched)."""
        if path not in self._cells:
            return
        it = self._items[path]
        par = it.parent()
        if par is not None:
            par.removeChild(it)
        else:
            self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(it))
        if hasattr(self, "_gfolders"):
            self._items.pop(path, None)
            self._rebuild_tree()
        for d in (self._cells, self._combos, self._runs, self._ident, self._saved_at,
                  self._ckey, self._copies, self._items):
            d.pop(path, None)

    def _selected_paths(self) -> List[str]:
        """The selected runs (a selected group or movie folder: every run in it)."""
        out = []

        def walk(it):
            if it.data(0, FOLDER_ROLE) is None and it.data(0, GROUP_ROLE) is None:
                out.append(str(it.data(0, PATH_ROLE)))
            for j in range(it.childCount()):
                walk(it.child(j))
        for it in self.tree.selectedItems():
            walk(it)
        return [q for q in dict.fromkeys(out) if q in self._cells]

    def _all_groups(self) -> List[str]:
        names = list(self._group_names)
        for p in list(self._items):             # every run (also while the tree is rebuilt)
            g = self._groups.get(p, "").strip()
            if g and g not in names:
                names.append(g)
        return names

    def _save_group_names(self) -> None:
        self._group_names = self._all_groups()
        update_prefs(group_names=self._group_names)

    def _new_group(self) -> Optional[str]:
        name, ok = QInputDialog.getText(self, "New group", "Name of the group (e.g. "
                                        "'U2OS NLS-met'):")
        name = name.strip() if ok else ""
        if not name:
            return None
        if name not in self._group_names:
            self._group_names.append(name)
            self._save_group_names()
        self._rebuild_tree()
        return name

    def _rename_group(self) -> None:
        g = self._panel_group()
        if not g:
            QMessageBox.information(self, "Groups", "Click a group in the Groups panel first.")
            return
        name, ok = QInputDialog.getText(self, "Rename group", "New name:", text=g)
        name = name.strip() if ok else ""
        if not name or name == g:
            return
        self._group_names = [name if x == g else x for x in self._group_names]
        self.set_groups({p: name for p in self._paths if self._groups.get(p) == g}, ask=False)
        self._save_group_names()
        self._rebuild_tree()
        self.refresh()

    def _delete_group(self) -> None:
        g = self._panel_group()
        if not g:
            QMessageBox.information(self, "Groups", "Click a group in the Groups panel first.")
            return
        self._group_names = [x for x in self._group_names if x != g]
        self.set_groups({p: "" for p in self._paths if self._groups.get(p) == g}, ask=False)
        self._save_group_names()
        self._rebuild_tree()
        self.refresh()

    def _panel_group(self) -> str:
        """The group of the selected row (its folder), '' for none."""
        it = self.tree.currentItem()
        while it is not None and it.data(0, GROUP_ROLE) is None:
            it = it.parent()
        return str(it.data(0, GROUP_ROLE) or "") if it is not None else ""

    def _put_menu(self) -> None:
        m = QMenu(self)
        for g in self._all_groups():
            m.addAction(g, lambda g=g: self.put_selected_in(g))
        if m.actions():
            m.addSeparator()
        m.addAction("New group...", lambda: (lambda n: n and self.put_selected_in(n))(
            self._new_group()))
        m.exec(self.btn_put.mapToGlobal(self.btn_put.rect().bottomLeft()))

    def put_selected_in(self, group: str) -> None:
        """The selected runs go into this group (and are ticked: grouping them
        means you want to plot them)."""
        paths = self._selected_paths()
        if not paths:
            QMessageBox.information(self, "Groups", "Select runs in the list first (click; "
                                    "Ctrl / Shift-click for more), then pick the group.")
            return
        ticked = list(paths)
        for ps in getattr(self, "_dup_sets_all", []):     # a movie's analyses move together
            if any(q in ps for q in paths):
                paths = list(dict.fromkeys(paths + ps))
        self.set_groups({q: group for q in paths}, ask=False)
        for q in ticked:
            if not self._is_on(q):
                self._use(q).setCheckState(Qt.Checked)
        self._save_group_names()
        self._ask_unknown()
        if self.mode() == "runs":
            self.set_mode("dishes")
        self.refresh()

    def _ungroup_selected(self) -> None:
        self.set_groups({q: "" for q in self._selected_paths()}, ask=False)
        self.refresh()

    def _group_double(self, g: str, col: int) -> None:
        """Double-click on a group folder: its colour (Colour column) or its name."""
        if col == COL_COLOUR:
            cur = self._current_colour_map().get(g, "#000000") if self.mode() != "runs" else \
                "#000000"
            c = QColorDialog.getColor(QColor(cur), self, f"Colour of group {g}")
            if c.isValid():
                self.set_group_colour(g, c.name().upper())
        else:
            self._rename_group()

    def _refresh_groups_panel(self) -> None:
        """The group folders' own rows: how many of their dishes are plotted, their
        colour, their tick (all / some / none plotted)."""
        cmap = self._current_colour_map() if self.mode() != "runs" else {}
        self._busy = True
        try:
            for g, it in self._gfolders.items():
                ms = [q for q in self._paths if (self._groups.get(q, "").strip() or "") == g]
                on = [q for q in ms if self._is_on(q)]
                # dishes: a movie with several analyses is one dish
                dish = {id(self.folder_of(q)) if self.folder_of(q) is not None else q for q in ms}
                dish_on = {id(self.folder_of(q)) if self.folder_of(q) is not None else q
                           for q in on}
                it.setText(COL_VER, f"{len(dish_on)} of {len(dish)} dishes plotted")
                it.setCheckState(COL_USE, Qt.Checked if on and len(dish_on) == len(dish)
                                 else Qt.PartiallyChecked if on else Qt.Unchecked)
                c = cmap.get(g) if on else None
                it.setBackground(COL_COLOUR, QBrush(QColor(c)) if c else QBrush())
                f = it.font(COL_LABEL)
                f.setBold(True)
                it.setFont(COL_LABEL, f)
        finally:
            self._busy = False

    def _group_by_line(self) -> None:
        todo = []
        for p in self._paths:
            if self._is_on(p) and not self._groups.get(p):
                name, _cl, _chosen = self.cell_line_of(p)
                if name != UNKNOWN:
                    todo.append((p, name))
        self.set_groups({p: nm for p, nm in todo}, ask=False)
        if todo and self.mode() == "runs":
            self.set_mode("dishes")
        self.refresh()

    def set_groups(self, by_path: Dict[str, str], ask: bool = True) -> None:
        """Put these runs (by path) into these groups ('' = no group); the list's
        group folders follow."""
        self._busy = True
        try:
            for p, name in by_path.items():
                if p in self._cells:
                    self._groups[p] = name.strip()
                    self._cells[p][COL_GROUP].setText(name.strip())
                    self._remember_group(p)
        finally:
            self._busy = False
        if hasattr(self, "_gfolders"):
            self._rebuild_tree()
        if ask:
            self._ask_unknown()

    def set_group(self, paths: Sequence[str], name: str) -> None:
        """Put these runs into group `name` ('' = no group)."""
        self.set_groups({q: name for q in paths})
        self.refresh()

    def _cell_double(self, item, col: int) -> None:
        if item.data(0, GROUP_ROLE) is not None:
            if item.data(0, GROUP_ROLE):
                self.tree.setCurrentItem(item)
                self._group_double(str(item.data(0, GROUP_ROLE)), col)
            return
        p = str(item.data(0, PATH_ROLE) or "")
        if not p or item.data(0, FOLDER_ROLE) is not None:
            return
        if col == COL_LABEL:
            self.tree.editItem(item, COL_LABEL)
        elif col == COL_COLOUR:
            key = self._group_of(p) if self.mode() != "runs" else None
            cur = self._current_colour_map().get(key or p, "#000000")
            c = QColorDialog.getColor(QColor(cur), self,
                                      f"Colour of {'group ' + key if key else 'this run'}")
            if c.isValid():
                if key:
                    self.set_group_colour(key, c.name().upper())
                else:
                    self.set_colour(p, c.name().upper())

    def set_colour(self, p: str, colour: str) -> None:
        """This run's colour (remembered for its name)."""
        self._colours[p] = colour
        remember(self._labels.get(p, ""), colour)
        self._remembered = load_remembered()
        self.refresh()

    def set_group_colour(self, group: str, colour: str) -> None:
        """This group's colour (remembered for its name)."""
        self._group_colours[group] = colour
        remember(group, colour)
        self._remembered = load_remembered()
        self.refresh()

    def set_label(self, p: str, text: str) -> None:
        self._cells[p][COL_LABEL].setText(text)

    def _item_changed(self, item, col: int) -> None:
        if self._busy:
            return
        if item.data(0, GROUP_ROLE) is not None:      # a group folder: all its dishes
            if col == COL_USE:
                self._group_ticked(item)
            return
        if item.data(0, FOLDER_ROLE):                 # a movie folder: tick its analysis
            if col == COL_USE:
                self._folder_ticked(item)
            return
        p = str(item.data(0, PATH_ROLE) or "")
        if p not in self._cells:
            return
        if col == COL_LABEL:
            self._labels[p] = item.text(COL_LABEL).strip() or Path(self._nd2.get(p, p)).stem
            if p in self._runs:
                self._runs[p].label = self._labels[p]
            self._remember_label(p)
            self._show_line(p)
            self._mark_duplicates()
            self.refresh()
        elif col == COL_USE:
            if item.checkState(COL_USE) == Qt.Checked:
                self._one_per_movie(p)
            if item.checkState(COL_USE) == Qt.Checked and p not in self._runs:
                try:
                    run = self._preloaded.pop(p, None)      # V2.9: read in the background
                    if isinstance(run, Exception):
                        raise run
                    if run is None:
                        run = C.load_run(p)
                except ValueError as e:
                    QMessageBox.warning(self, "Compare runs", str(e))
                    self._busy = True
                    item.setCheckState(COL_USE, Qt.Unchecked)
                    self._busy = False
                    return
                run.label = self._labels[p]
                self._runs[p] = run
                its = self._cells[p]                  # items, not rows: rows may re-sort
                self._busy = True
                try:
                    its[COL_INT].setText(run.interval_text())
                    its[COL_INT].setData(SORT_ROLE, float(run.seconds_per_frame)
                                         if run.seconds_per_frame > 0 else None)
                    its[COL_BASE].setText(f"T{run.baseline}")
                    its[COL_BASE].setData(SORT_ROLE, float(run.baseline))
                    its[COL_CELLS].setText(
                        ", ".join(f"{C.COMP_LABELS.get(c, c)} {len(run.included[c])} included"
                                  for c in run.comps()))
                    its[COL_CELLS].setData(SORT_ROLE, float(max(
                        [len(run.included[c]) for c in run.comps()] or [0])))
                finally:
                    self._busy = False
            if self._bulk:                            # V2.9: once, when all are ticked
                self._bulk_dirty = True
                return
            self._recompute()
            self._save_view_prefs()

    def _one_per_movie(self, p: str) -> None:
        """Groups modes: ticking an analysis of a movie unticks the movie's other
        analyses (one dish must not be counted twice). 'Each run' may show
        several analyses of one movie side by side (to compare the analyses;
        the red note says so)."""
        par = self.folder_of(p)
        if par is None:
            return
        self._busy = True
        try:
            if self.mode() == "runs":
                par.setCheckState(COL_USE, Qt.Checked)
                return
            for j in range(par.childCount()):
                q = str(par.child(j).data(0, PATH_ROLE) or "")
                if q and q != p and self._is_on(q):
                    self._use(q).setCheckState(Qt.Unchecked)
            par.setCheckState(COL_USE, Qt.Checked)
        finally:
            self._busy = False

    def _group_ticked(self, gf) -> None:
        """A group folder's tick: on = every dish of the group (the newest analysis
        of a movie with several), off = none."""
        on = gf.checkState(COL_USE) != Qt.Unchecked
        kids = []
        for j in range(gf.childCount()):
            it = gf.child(j)
            if it.data(0, FOLDER_ROLE) is not None:
                kids += [str(it.child(k).data(0, PATH_ROLE)) for k in range(it.childCount())]
            else:
                kids.append(str(it.data(0, PATH_ROLE)))
        with self._ticking(kids if on else []):
            for j in range(gf.childCount()):
                it = gf.child(j)
                if it.data(0, FOLDER_ROLE) is not None:
                    it.setCheckState(COL_USE, Qt.Checked if on else Qt.Unchecked)
                else:
                    self._use(str(it.data(0, PATH_ROLE))).setCheckState(
                        Qt.Checked if on else Qt.Unchecked)

    def _ticking(self, load: Sequence[str]):
        """V2.9: tick many runs at once - the ones not read yet are read in the
        background first (a bar), and the lists / graph are redone once at the end
        instead of after every run."""
        from contextlib import contextmanager
        need = [p for p in load if p in self._cells and p not in self._runs
                and p not in self._preloaded]

        def read(progress):
            got = {}
            for i, p in enumerate(need):
                progress(i / max(1, len(need)), f"Run {i + 1} of {len(need)}: "
                                                f"{self._labels.get(p, Path(p).stem)}")
                try:
                    got[p] = C.load_run(p)
                except ValueError as e:
                    got[p] = e
            return got
        if need:
            self._preloaded.update(W.run_with_progress(self, f"Loading {len(need)} run"
                                                             f"{'' if len(need) == 1 else 's'}",
                                                       read))

        @contextmanager
        def bulk():
            self._bulk += 1
            try:
                yield
            finally:
                self._bulk -= 1
                if not self._bulk and self._bulk_dirty:
                    self._bulk_dirty = False
                    self._recompute()
                    self._save_view_prefs()
        return bulk()

    def _folder_ticked(self, folder) -> None:
        """A movie folder's tick: on = its newest analysis (or the one already
        ticked), off = none of its analyses."""
        kids = [str(folder.child(j).data(0, PATH_ROLE)) for j in range(folder.childCount())]
        if folder.checkState(COL_USE) == Qt.Checked:
            if not any(self._is_on(q) for q in kids) and kids:
                newest = max(kids, key=lambda q: self._saved_at.get(q, ""))
                self._use(newest).setCheckState(Qt.Checked)
        else:
            for q in kids:
                if self._is_on(q):
                    self._use(q).setCheckState(Qt.Unchecked)

    def set_checked(self, paths: Sequence[str]) -> None:
        """Tick exactly these runs (tests and 'open with these')."""
        want = {self._norm(p) for p in paths}
        with self._ticking([p for p in self._paths if self._norm(p) in want]):
            for p in self._paths:
                self._use(p).setCheckState(Qt.Checked if self._norm(p) in want
                                           else Qt.Unchecked)

    def chosen(self) -> List[C.Run]:
        return [self._runs[p] for p in self._paths if self._is_on(p) and p in self._runs]

    def mode(self) -> str:
        return self.cmb_mode.currentData() or "runs"

    def set_mode(self, mode: str) -> None:
        self.cmb_mode.setCurrentIndex(max(0, self.cmb_mode.findData(mode)))

    def graph(self) -> str:
        """'time' (the time course) or a kinetics parameter key."""
        return self.cmb_graph.currentData() or GRAPH_TIME

    def set_graph(self, key: str) -> None:
        self.cmb_graph.setCurrentIndex(max(0, self.cmb_graph.findData(key)))

    def _view_changed(self) -> None:
        self._save_view_prefs()
        self.refresh()

    def _group_of(self, path: str) -> str:
        return self._groups.get(path, "").strip() or self._labels.get(path, Path(path).stem)

    def groups(self) -> List[tuple]:
        """[(group name, [runs])] of the ticked runs, in list order."""
        out: Dict[str, List[C.Run]] = {}
        for r in self.chosen():
            out.setdefault(self._group_of(r.path), []).append(r)
        return list(out.items())

    # --------------------------------------------------------- cell line
    def _auto_line(self, path: str) -> Optional[CL.CellLine]:
        return (CL.match(self._labels.get(path, "")) or CL.match(self._nd2.get(path, "")) or
                CL.match(Path(path).name))

    def cell_line_of(self, path: str) -> Tuple[str, Optional[CL.CellLine], bool]:
        """(name shown in the Cell line column, the known cell line or None,
        chosen by the user?). Name 'Unknown' = no cell line."""
        ov = self._line_override.get(path)
        if ov:
            if ov.strip().lower() == UNKNOWN.lower():
                return UNKNOWN, None, True
            cl = CL.by_name(ov)
            return (cl.name if cl else ov), cl, True
        cl = self._auto_line(path)
        return (cl.name if cl else UNKNOWN), cl, False

    def _colour_line(self, path: str):
        """For celllines.assign_colours(lines=...): CellLine, a typed name (str),
        '' (Unknown on purpose) or None (read it from the name)."""
        name, cl, chosen = self.cell_line_of(path)
        if cl is not None:
            return cl
        if chosen:
            return "" if name == UNKNOWN else name
        return None

    def _ensure_line_name(self, name: str) -> None:
        """A typed cell line name joins the dropdown lists (sorted)."""
        lst = self._line_model.stringList()
        if any(s.lower() == name.lower() for s in lst):
            return
        pos = 1
        while pos < len(lst) and lst[pos].lower() < name.lower():
            pos += 1
        self._line_model.insertRows(pos, 1)
        self._line_model.setData(self._line_model.index(pos, 0), name)

    def _show_line(self, path: str) -> None:
        """The dropdown and the (sort) text of this run's Cell line cell."""
        if path not in self._cells:
            return
        name, cl, chosen = self.cell_line_of(path)
        self._ensure_line_name(name)
        cb = self._combos.get(path)
        self._busy = True
        try:
            self._cells[path][COL_LINE].setText(name)
            if cb is not None:
                cb.blockSignals(True)
                i = cb.findText(name, Qt.MatchFixedString)
                cb.setCurrentIndex(i)
                cb.setEditText(name)
                cb.blockSignals(False)
                cb.setToolTip(
                    ("Chosen by you - remembered for this .nd2. " if chosen else
                     "Read from the file / run name. " if cl else
                     "Not a known cell line - you choose its colour. ") +
                    "Pick another cell line from the list, or type a new name, if it is wrong "
                    "(the colour family follows).")
        finally:
            self._busy = False

    def _line_chosen(self, path: str, text: str, explicit: bool = True) -> None:
        """The user picked (explicit) / typed (Enter or leaving the field) a cell
        line for this run. Leaving the field unchanged changes nothing."""
        if self._busy or path not in self._cells:
            return
        t = str(text or "").strip()
        if not t or t.lower() in (UNKNOWN.lower(), "?"):
            name = UNKNOWN
        else:
            cl = CL.by_name(t)
            name = cl.name if cl else next(           # a typed name: its first spelling
                (s for s in self._line_model.stringList() if s.lower() == t.lower()), t)
        if self._line_override.get(path) == name or \
                (not explicit and name == self.cell_line_of(path)[0]):
            self._show_line(path)
            return
        self.set_cell_line(path, name)

    def set_cell_line(self, path: str, name: str) -> None:
        """This run's cell line (as if chosen in the dropdown): wins over the
        name match, re-colours the run, remembered for its .nd2."""
        if path not in self._cells:
            return
        self._line_override[path] = name
        self._saved_lines[self.run_key(path)] = name
        update_prefs(cell_lines=self._merged_lines())
        self._colours.pop(path, None)                       # re-colour from the new family
        forget(self._labels.get(path, ""))
        self._remembered = load_remembered()
        self._show_line(path)
        self._ask_unknown()
        self.refresh()

    def _merged_lines(self) -> Dict[str, str]:
        cl = load_prefs().get("cell_lines")
        d = dict(cl) if isinstance(cl, dict) else {}
        d.update(self._saved_lines)
        return d

    # ------------------------------------------------------ same .nd2
    def _mark_duplicates(self) -> None:
        """'Same .nd2 as' column + orange cells for runs made from one .nd2."""
        self._dups = C.same_nd2([self._ident[p] for p in self._paths if p in self._ident])
        sets = self._sets_of(list(self._cells))
        # newest analysis first inside a set; sets ordered by their newest analysis
        for ps in sets:
            ps.sort(key=lambda q: self._saved_at.get(q, ""), reverse=True)
        sets.sort(key=lambda ps: self._saved_at.get(ps[0], ""), reverse=True)
        self._dup_sets = [ps for ps in sets if len(ps) > 1]
        colour_of, ver_of, key_of = {}, {}, {}
        for k, ps in enumerate(self._dup_sets):
            for j, q in enumerate(ps):
                colour_of[q] = DUP_COLOURS[k % len(DUP_COLOURS)]
                n = len(ps)
                ver_of[q] = (f"newest ({n} of {n})" if j == 0 else
                             f"oldest (1 of {n})" if j == n - 1 else f"older ({n - j} of {n})")
        for ps in sets:
            for q in ps:
                key_of[q] = f"{self._saved_at.get(ps[0], '')}|{self._saved_at.get(q, '')}"
        self._make_folders(self._dup_sets)
        self._busy = True
        try:
            for p in list(self._cells):
                its = self._cells[p]
                pv = self._app_ver.get(p, "")
                v = ver_of.get(p, "")
                its[COL_VER].setText(", ".join(t for t in (pv, v.split(" (")[0] + (
                    f" of {len(next(ps for ps in self._dup_sets if p in ps))}" if v else ""))
                    if t) or "")
                its[COL_VER].setData(SORT_ROLE, key_of.get(p, ""))
                f = its[COL_LABEL].font()
                f.setItalic(p in ver_of and not ver_of[p].startswith("newest"))
                its[COL_LABEL].setFont(f)
                twins = self._dups.get(p, [])
                its[COL_VER].setToolTip(
                    ("Another analysis of the same .nd2 movie (one dish) - in its folder: " +
                     "; ".join(f"{self._twin_text(q)} ({C.SAME_REASONS[w]})" for q, w in twins) +
                     ". Tick one analysis per movie.") if twins else
                    "The only analysis of this .nd2 in the list.")
                col = colour_of.get(p)
                for c in (COL_FILE, COL_VER):
                    its[c].setBackground(QBrush(QColor(col)) if col else QBrush())
                    its[c].setForeground(QBrush(QColor("#000000")) if col else QBrush())
        finally:
            self._busy = False

    def _make_folders(self, sets: List[List[str]]) -> None:
        """V2.8: the list as folders - one per group (in the order the groups were
        made; 'No group' last), its runs in it; a .nd2 with more than one analysis
        in the list is a movie sub-folder of its analyses (newest first). Rows keep
        their tick, name and group; their Cell line dropdowns are made again."""
        self._dup_sets_all = [ps for ps in sets if len(ps) > 1]
        self._rebuild_tree()

    def _rebuild_tree(self) -> None:
        if not hasattr(self, "_gfolders"):
            self._gfolders: Dict[str, _RunItem] = {}
        was_open = {g: it.isExpanded() for g, it in self._gfolders.items()}
        was = self.tree.isSortingEnabled()
        self.tree.setSortingEnabled(False)
        self._busy = True
        try:
            for i in reversed(range(self.tree.topLevelItemCount())):    # take everything out
                top = self.tree.takeTopLevelItem(i)
                stack = [top]
                while stack:
                    it = stack.pop()
                    for j in reversed(range(it.childCount())):
                        stack.append(it.takeChild(j))
            self._folders, self._gfolders = {}, {}
            order = [g for g in self._all_groups()] + [""]
            set_of = {}
            for ps in getattr(self, "_dup_sets_all", []):
                for q in ps:
                    set_of[q] = ps
            for gi, g in enumerate(order):
                runs = [q for q in self._items if (self._groups.get(q, "").strip() or "") == g]
                if not runs and not g:
                    continue
                gf = _RunItem()
                gf.setData(0, GROUP_ROLE, g)
                gf.setData(0, SORT_ROLE, gi)
                gf.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable |
                            Qt.ItemIsDropEnabled)
                gf.setCheckState(COL_USE, Qt.Unchecked)
                gf.setText(COL_LABEL, (g or NO_GROUP))
                gf.setToolTip(COL_LABEL, "A group of replicate dishes (one condition). Tick it to "
                              "plot all its dishes; drag runs here to add them; double-click to "
                              "rename it." if g else "Runs not in a group yet - drag them onto "
                              "a group, or select them and use 'Put selected runs in'.")
                gf.setToolTip(COL_COLOUR, "The group's colour - double-click to change it.")
                self.tree.addTopLevelItem(gf)
                self._gfolders[g] = gf
                done = set()
                for q in sorted(runs, key=lambda x: self._labels.get(x, "").lower()):
                    if q in done:
                        continue
                    ps = [x for x in set_of.get(q, [q]) if x in runs]
                    if len(ps) > 1:
                        ps.sort(key=lambda x: self._saved_at.get(x, ""), reverse=True)
                        key = ps[-1]
                        fo = _RunItem()
                        fo.setData(0, FOLDER_ROLE, key)
                        fo.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable |
                                    Qt.ItemIsUserCheckable | Qt.ItemIsDragEnabled)
                        f = fo.font(COL_LABEL)
                        f.setBold(True)
                        fo.setFont(COL_LABEL, f)
                        nd2 = self._nd2.get(ps[0], "")
                        fo.setText(COL_LABEL, f"▸ {Path(nd2).stem or nd2} - {len(ps)} analyses")
                        fo.setText(COL_VER, f"{len(ps)} analyses")
                        fo.setText(COL_FILE, nd2)
                        fo.setText(COL_SAVED, self._cells[ps[0]][COL_SAVED].text())
                        fo.setData(COL_SAVED, SORT_ROLE, self._saved_at.get(ps[0], ""))
                        fo.setToolTip(COL_LABEL, "One .nd2 movie (one dish) analysed more than "
                                      "once. Tick the analysis to plot - one per movie in the "
                                      "Groups modes.")
                        fo.setCheckState(COL_USE, Qt.Checked if any(self._is_on(x) for x in ps)
                                         else Qt.Unchecked)
                        for x in ps:
                            fo.addChild(self._items[x])
                            done.add(x)
                        gf.addChild(fo)
                        fo.setExpanded(True)
                        self._folders[key] = fo
                    else:
                        gf.addChild(self._items[q])
                        done.add(q)
                gf.setExpanded(was_open.get(g, True))
        finally:
            self._busy = False
            self.tree.setSortingEnabled(was)
        for q in list(self._items):
            self._attach_combo(q)
            self._show_line(q)
        self._refresh_groups_panel()

    def duplicate_sets(self) -> List[List[str]]:
        """Ticked runs that are analyses of one .nd2: [[path, path, ...], ...]."""
        return [ps for ps in self._sets_of([r.path for r in self.chosen()]) if len(ps) > 1]

    def _sets_of(self, on: List[str]) -> List[List[str]]:
        """These runs split into sets made from one .nd2 (singletons included)."""
        onset = set(on)
        parent = {p: p for p in on}

        def root(p):
            while parent[p] != p:
                parent[p] = parent[parent[p]]
                p = parent[p]
            return p
        for p in on:
            for q, _w in self._dups.get(p, []):
                if q in onset:
                    parent[root(p)] = root(q)
        sets: Dict[str, List[str]] = {}
        for p in on:
            sets.setdefault(root(p), []).append(p)
        return list(sets.values())

    def folder_of(self, path: str) -> Optional[_RunItem]:
        """The movie folder a run is in (None: a run of its own)."""
        it = self._items.get(path)
        par = it.parent() if it is not None else None
        return par if par is not None and par.data(0, FOLDER_ROLE) is not None else None

    def version_of(self, path: str) -> str:
        """The Version column's text of a run."""
        return self._cells[path][COL_VER].text() if path in self._cells else ""

    def _twin_text(self, path: str) -> str:
        """'movie1 (saved 1 Nov 2026 21:52)' - which other analysis it is."""
        from .historydlg import when_text
        saved = self._saved_at.get(path, "")
        lab = self._labels.get(path, Path(path).stem)
        return f"{lab} (saved {when_text(saved)})" if saved else lab

    def duplicate_warning(self) -> str:
        """'' or the plain warning about ticked runs made from one .nd2."""
        out = []
        for ps in self.duplicate_sets():
            names = [f"'{self._twin_text(p)}'" for p in ps]
            who = (", ".join(names[:-1]) + " and " + names[-1]) if len(names) > 1 else names[0]
            nd2 = self._nd2.get(ps[0], "")
            txt = (f"Runs {who} are analyses of the same .nd2 file ({nd2}): averaging them "
                   f"would count one dish twice.")
            if self.mode() != "runs":
                gs = sorted({self._group_of(p) for p in ps})
                txt += (f" They are in one group ({gs[0]})." if len(gs) == 1 else
                        " They are in different groups (" + ", ".join(gs) + "): the same "
                        "dish would be in more than one group.")
            out.append(txt)
        if out:
            out.append("Untick all but one of them (or remove the extra ones from the list).")
        return " ".join(out)

    def _confirm_duplicates(self, text: str) -> bool:
        r = QMessageBox.question(self, "The same .nd2 twice", text + "\n\nSave anyway?",
                                 QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        return r == QMessageBox.Yes

    # ------------------------------------------------------------ colours
    def _current_colour_map(self) -> Dict[str, str]:
        """{run path or group name: colour} for what is shown now. Unknown cell
        lines without a chosen colour get a palette colour (and are listed in
        self._unknown, so the window can ask)."""
        self._unknown_custom = {}
        if self.mode() == "runs":
            runs = self.chosen()
            keys = [r.path for r in runs]
            # the run's cell line: from its (edited) name, else from its .nd2 name
            names = [self._labels.get(r.path, "") if CL.match(self._labels.get(r.path, ""))
                     or self._labels.get(r.path, "").lower() in self._remembered
                     or r.path in self._line_override
                     else r.nd2 for r in runs]
            lines = [self._colour_line(r.path) for r in runs]
            mine = self._colours
        else:
            gs = self.groups()
            keys = [g for g, _r in gs]
            # the group's cell line: from its name, else from its first dish
            names = [g if CL.match(g) else (runs[0].nd2 if runs else g) for g, runs in gs]
            lines = [self._group_line(g, runs) for g, runs in gs]
            mine = self._group_colours
        rem = dict(self._remembered)
        if self.mode() != "runs":         # a remembered group colour is under the group name
            for k, nm in zip(keys, names):
                if k.lower() in rem:
                    rem[nm.lower()] = rem[k.lower()]
        auto = CL.assign_colours(names, rem, lines)
        out = {}
        for i, (k, c) in enumerate(zip(keys, auto)):
            out[k] = mine.get(k) or c or C.PALETTE[i % len(C.PALETTE)]
        self._unknown = [k for k, c in zip(keys, auto) if c is None and k not in mine]
        for k, ln in zip(keys, lines):
            if isinstance(ln, str) and ln.strip():
                self._unknown_custom[k] = ln.strip()
        return out

    def _group_line(self, group: str, runs: Sequence[C.Run]):
        """A group's cell line for its colour: the one chosen for all its dishes
        (if they agree), else the one in the group name, else its first dish's."""
        chosen = [self.cell_line_of(r.path) for r in runs]
        if chosen and all(c[2] for c in chosen) and len({c[0] for c in chosen}) == 1:
            return self._colour_line(runs[0].path)
        if CL.match(group):
            return None
        return self._colour_line(runs[0].path) if runs else None

    def _ask_unknown(self) -> None:
        """Ask once per name for the colour of a run / group whose cell line is
        not known (the answer is remembered). A cell line name the user typed:
        asked once for that name (its runs get shades of it)."""
        if not self.ASK_UNKNOWN:
            return
        self._current_colour_map()
        for key in list(self._unknown):
            label = self._unknown_custom.get(key) or (
                key if self.mode() != "runs" else self._labels.get(key, key))
            if label.lower() in self._asked:
                continue
            self._asked.add(label.lower())
            what = ("cell line" if key in self._unknown_custom else "cell line not recognised")
            c = QColorDialog.getColor(QColor(C.PALETTE[len(self._asked) % len(C.PALETTE)]),
                                      self, f"Colour for '{label}' ({what})")
            if c.isValid():
                remember(label, c.name().upper())
                self._remembered = load_remembered()

    def chosen_colours(self) -> List[str]:
        cmap = self._current_colour_map()
        if self.mode() == "runs":
            return [cmap[r.path] for r in self.chosen()]
        return [cmap[g] for g, _r in self.groups()]

    def _paint_rows(self) -> None:
        """The colour swatch of every plotted run; plotted runs in bold, the others
        dimmed (V2.8: what is graphed is what is bold)."""
        cmap = self._current_colour_map()
        dim = QBrush(QColor("#8A8A8A"))
        self._busy = True
        try:
            for p in list(self._cells):
                it = self._cells[p][COL_COLOUR]
                on = self._is_on(p) and p in self._runs
                key = p if self.mode() == "runs" else self._group_of(p)
                c = cmap.get(key) if on else None
                it.setBackground(QColor(c) if c else QColor(0, 0, 0, 0))
                it.setText(" " if c else "")
                it.setData(SORT_ROLE, c or "")
                row = self._items.get(p)
                if row is not None:
                    for col in (COL_LABEL, COL_GROUP, COL_CELLS, COL_SAVED):
                        f = row.font(col)
                        f.setBold(on)
                        row.setFont(col, f)
                        row.setForeground(col, QBrush() if on else dim)
            for fo in self._folders.values():
                kids = [str(fo.child(j).data(0, PATH_ROLE)) for j in range(fo.childCount())]
                fo.setCheckState(COL_USE, Qt.Checked if any(self._is_on(q) for q in kids)
                                 else Qt.Unchecked)
        finally:
            self._busy = False
        self._refresh_groups_panel()

    # ----------------------------------------------------------- choices
    def _recompute(self) -> None:
        runs = self.chosen()
        comps = C.common_comps(runs)
        cur = self.cmb_comp.currentData()
        self.cmb_comp.blockSignals(True)
        self.cmb_comp.clear()
        for c in comps:
            self.cmb_comp.addItem(C.COMP_LABELS.get(c, c), c)
        if cur in comps:
            self.cmb_comp.setCurrentIndex(comps.index(cur))
        self.cmb_comp.blockSignals(False)
        self.sp_base.setMaximum(max([1] + [r.n_timepoints for r in runs]))
        self._ask_unknown()
        opts = XP.options(runs)
        self._busy_rows = True
        try:
            for row in (self.row_y, self.row_x, self.row_y2):
                row.set_options(opts)
        finally:
            self._busy_rows = False
        self._fill_quantities()
        self._sync_y_row()

    def _fill_quantities(self) -> None:
        runs = self.chosen()
        comp = self.cmb_comp.currentData()
        qs = C.common_quantities(runs, comp) if comp else []
        cur = self.cmb_q.currentText()
        self.cmb_q.blockSignals(True)
        self.cmb_q.clear()
        self.cmb_q.addItems(qs)
        if cur in qs:
            self.cmb_q.setCurrentIndex(qs.index(cur))
        self.cmb_q.blockSignals(False)
        self.refresh()

    # ---------------------------------------------------- V2.7 plot builder
    def _sync_y_row(self) -> None:
        """Show the Y measure held in cmb_comp / cmb_q in the Plot row."""
        comp, q = self.cmb_comp.currentData(), self.cmb_q.currentText()
        if comp and q:
            self._busy_rows = True
            try:
                self.row_y.set_measure(XP.Measure(comp, q))
            finally:
                self._busy_rows = False
        self._spec_changed()

    def _y_changed(self) -> None:
        """The Plot row changed: put its measure into cmb_comp / cmb_q."""
        if getattr(self, "_busy_rows", False):
            return
        m = self.row_y.measure()
        if m is None:
            return
        self.cmb_comp.blockSignals(True)
        i = self.cmb_comp.findData(m.comp)
        if i >= 0:
            self.cmb_comp.setCurrentIndex(i)
        self.cmb_comp.blockSignals(False)
        runs = self.chosen()
        qs = C.common_quantities(runs, m.comp) if runs else []
        self.cmb_q.blockSignals(True)
        self.cmb_q.clear()
        self.cmb_q.addItems(qs)
        self.cmb_q.setCurrentIndex(max(0, self.cmb_q.findText(m.quantity)))
        self.cmb_q.blockSignals(False)
        self._spec_changed()

    def spec(self) -> Optional[XP.Spec]:
        """What the builder says now (None: nothing to plot)."""
        comp, q = self.cmb_comp.currentData(), self.cmb_q.currentText()
        if not comp or not q:
            return None
        x = self.row_x.measure()
        pts = self.cmb_points.currentData() or "trajectory"
        return XP.Spec(y=XP.Measure(comp, q), x=x, y2=self.row_y2.measure(),
                       points=pts, at=int(self.sp_at.value()),
                       win=(int(self.sp_at.value()), int(self.sp_to.value())),
                       x_axis=self.row_x.first_choice() or XP.TIME)

    def set_spec(self, spec: XP.Spec) -> None:
        """Choose this plot (measures the ticked runs do not have are left as they are)."""
        self.row_y.set_measure(spec.y)
        self.row_x.set_measure(spec.x, first=spec.x_axis)
        self.row_y2.set_measure(spec.y2)
        self.cmb_points.setCurrentIndex(max(0, self.cmb_points.findData(spec.points)))
        self.sp_at.setValue(int(spec.win[0] if spec.points == "cells_window" else spec.at))
        self.sp_to.setValue(int(spec.win[1]))
        self._spec_changed()

    def _spec_changed(self) -> None:
        if getattr(self, "_busy_rows", False):
            return
        vs_time = self.row_x.measure() is None
        self.chk_xerr.setEnabled(not vs_time)
        for w in (self.lbl_points, self.wid_points):
            w.setVisible(not vs_time)
        self.sp_to.setVisible(self.cmb_points.currentData() == "cells_window")
        self.sp_at.setPrefix("frames " if self.cmb_points.currentData() == "cells_window"
                             else "frame ")
        self.cmb_graph.setEnabled(vs_time)
        self.cmb_graph.setToolTip("Time course, or a kinetics dot plot (hover each entry). " + (
            "" if vs_time else "Kinetics need X = Time - choose Time under 'vs' to use them."))
        if not vs_time and self.graph() != GRAPH_TIME:
            self.cmb_graph.setCurrentIndex(0)
        sp = self.spec()
        self.lbl_sentence.setText(html.escape(sp.sentence()) if sp else "")
        self._save_view_prefs()
        self.refresh()

    def _mode_changed(self) -> None:
        if self.mode() != "runs":            # groups: one analysis per movie (one dish)
            kept = []
            for fo in list(self._folders.values()):
                on = [str(fo.child(j).data(0, PATH_ROLE)) for j in range(fo.childCount())
                      if self._is_on(str(fo.child(j).data(0, PATH_ROLE)))]
                if len(on) > 1:
                    keep = max(on, key=lambda q: self._saved_at.get(q, ""))
                    for q in on:
                        if q != keep:
                            self._use(q).setCheckState(Qt.Unchecked)
                    kept.append(self._twin_text(keep))
            if kept:
                QMessageBox.information(
                    self, "One analysis per movie",
                    "Groups count each dish once, so only the newest analysis of each movie is "
                    "kept ticked: " + "; ".join(kept) + ". Open its folder to tick another "
                    "analysis instead.")
        self._ask_unknown()
        self._save_view_prefs()
        self.refresh()

    def _base_toggled(self, own: bool) -> None:
        self.sp_base.setEnabled(not own)
        self.refresh()

    def _err_changed(self, _i: int) -> None:
        self.style = self.style.copy(error=self.cmb_err.currentData())
        self._save_view_prefs()
        try:                                       # V3.0: the same choice everywhere
            from ..config import load_settings, save_settings
            owner = self.parent()                  # the main / start window, if open
            s = getattr(owner, "settings", None) or load_settings()[0]
            s.graph_style = dict(s.graph_style or {}, error=self.style.error)
            save_settings(s)
            tr = getattr(owner, "traces", None)
            if tr is not None:                     # the main window's graph follows
                tr.set_style(dict(s.graph_style))
        except Exception:                                          # noqa: BLE001
            pass
        self.refresh()

    def set_style(self, style: Optional[dict]) -> None:
        self.style = GS.coerce(style)
        self.cmb_err.setCurrentIndex(max(0, self.cmb_err.findData(self.style.error)))
        self.refresh()

    # ------------------------------------------------------------- series
    def current(self):
        """(lines, colours, compartment, quantity, warning). lines: one
        compare.Series per run ('Each run') or one compare.GroupLine per group."""
        comp, q = self.cmb_comp.currentData(), self.cmb_q.currentText()
        lines, warn = self._lines_for(comp, q)
        return lines, self.chosen_colours(), comp, q, warn

    def _lines_for(self, comp: str, q: str):
        """(lines, warning) of one measure against time - see current()."""
        runs = self.chosen()
        if not runs or not comp or not q:
            return [], ""
        minutes, warn = C.time_units(runs)
        sp = self.spec() if hasattr(self, "row_x") else None
        if sp is not None and sp.x is None and sp.x_axis == XP.TIMEPOINT:
            minutes, warn = False, ""               # V2.8: timepoints from the baseline
        base = None if self.chk_own_base.isChecked() else int(self.sp_base.value())
        try:
            series = {r.path: C.series(r, comp, q, base, minutes) for r in runs}
        except KeyError as e:
            return [], f"Not every ticked run has {e} - untick the runs without it."
        empty = [s.label for s in series.values() if s.n == 0]
        if empty:
            warn = (warn + " " if warn else "") + ("No included cells in " + ", ".join(empty) +
                                                   " for this compartment.")
        if self.mode() == "runs":
            return [series[r.path] for r in runs], warn
        warn = warn.replace(" Each line uses its own interval, so the time points do not "
                            "line up.", "")
        lines = []
        for g, rs in self.groups():
            gl = C.group_line(g, [series[r.path] for r in rs], self.mode())
            lines.append(gl)
            if gl.note:
                warn = (warn + " " if warn else "") + f"{g}: {gl.note}"
        single = [g.label for g in lines if g.n_dishes == 1]
        if single and self.mode() == "dishes":
            warn = (warn + " " if warn else "") + (
                "Only one dish in " + ", ".join(single) + ": its line is that dish's mean and "
                "has no error bar (an SEM across dishes needs at least 2 dishes).")
        return lines, warn

    def pair_lines(self):
        """V2.7: (lines, colours, spec, warning) when X is a measure, else None."""
        sp = self.spec()
        if sp is None or sp.x is None:
            return None
        return self._pairs_for(sp)

    def _pairs_for(self, sp):
        runs = self.chosen()
        if not runs:
            return [], [], sp, ""
        minutes, warn = C.time_units(runs)
        base = None if self.chk_own_base.isChecked() else int(self.sp_base.value())
        groups = [(r.label, [r]) for r in runs] if self.mode() == "runs" else \
            [(g, list(rs)) for g, rs in self.groups()]
        try:
            lines, w2 = XP.pair_lines(sp, groups, self.mode(), base, minutes)
        except KeyError as e:
            return [], [], sp, f"Not every ticked run has {e}."
        warn = " ".join(t for t in (warn, w2) if t)
        return lines, self.chosen_colours()[:len(lines)], sp, warn

    def title_text(self, comp: str, q: str) -> str:
        t = self.ed_title.text().strip()
        return t or f"{q} - {C.COMP_LABELS.get(comp, comp)}"

    def _clear_right(self) -> None:
        vb2 = getattr(self, "_vb2", None)
        if vb2 is not None:
            vb2.clear()
        self.plot.hideAxis("right")

    def _right_axis(self):
        """The right Y axis' own view (made once, follows the main view's X)."""
        if getattr(self, "_vb2", None) is None:
            self._vb2 = pg.ViewBox()
            self.plot.scene().addItem(self._vb2)
            self.plot.getAxis("right").linkToView(self._vb2)
            self._vb2.setXLink(self.plot.getViewBox())
            main = self.plot.getViewBox()
            main.sigResized.connect(lambda *_a: self._vb2.setGeometry(main.sceneBoundingRect()))
            self._vb2.setGeometry(main.sceneBoundingRect())
        self.plot.showAxis("right")
        return self._vb2

    # ------------------------------------------------ drawing one line (V2.8)
    def _draw_line(self, name: str, x, m, lo, hi, colour: str, sym: str, *,
                   xlo=None, xhi=None, cells=None, joined: bool = True, vb=None,
                   dashed: bool = False, small: bool = False, x_name: str = "x",
                   y_name: str = "y") -> None:
        """One line: its mean (symbols, joined), the error bars the toggles ask
        for (Y: lo / hi, X: xlo / xhi), each cell / dish behind it (cells: list
        of (x, y) arrays, when 'Each cell' is ticked), in its legend entry - a
        click on the entry hides the line with its bars and cells - and in the
        hover readout."""
        st = self.style
        qc = QColor(colour)
        add = (vb.addItem if vb is not None else self.plot.addItem)
        x, m = np.asarray(x, float), np.asarray(m, float)
        ok = np.isfinite(x) & np.isfinite(m)
        linked = []
        if cells and self.chk_cells.isChecked():
            faint = QColor(qc)
            faint.setAlphaF(0.25)
            for cx, cy in cells:
                it = pg.PlotDataItem(np.asarray(cx, float), np.asarray(cy, float),
                                     pen=pg.mkPen(faint, width=1) if joined else None,
                                     symbol=None if joined else "o", symbolSize=4,
                                     symbolBrush=faint, symbolPen=None, connect="finite")
                add(it)
                linked.append(it)
        pen = pg.mkPen(qc, width=max(st.mean_width, 0.5) * PX)
        if self.chk_yerr.isChecked() and lo is not None and st.error != "none":
            lo, hi = np.asarray(lo, float), np.asarray(hi, float)
            okb = ok & np.isfinite(lo) & np.isfinite(hi)
            if okb.any():
                if st.error_style == "band" and joined and xlo is None:
                    fill = QColor(qc)
                    fill.setAlphaF(GS.BAND_ALPHA)
                    a = pg.PlotDataItem(x, lo, pen=pg.mkPen(None), connect="finite")
                    b = pg.PlotDataItem(x, hi, pen=pg.mkPen(None), connect="finite")
                    band = pg.FillBetweenItem(a, b, brush=pg.mkBrush(fill))
                    for it in (a, b, band):
                        add(it)
                        linked.append(it)
                else:
                    it = pg.ErrorBarItem(x=x[okb], y=m[okb], top=(hi - m)[okb],
                                         bottom=(m - lo)[okb], pen=pen)
                    add(it)
                    linked.append(it)
        if self.chk_xerr.isChecked() and xlo is not None and st.error != "none":
            xlo, xhi = np.asarray(xlo, float), np.asarray(xhi, float)
            okb = ok & np.isfinite(xlo) & np.isfinite(xhi)
            if okb.any():
                it = pg.ErrorBarItem(x=x[okb], y=m[okb], left=(x - xlo)[okb],
                                     right=(xhi - x)[okb], pen=pen)
                add(it)
                linked.append(it)
        open_ = sym.startswith("open_")
        main = pg.PlotDataItem(
            x[ok] if not joined else x, m[ok] if not joined else m,
            pen=(pg.mkPen(qc, width=max(st.mean_width, 0.5) * PX,
                          style=Qt.DashLine if dashed else Qt.SolidLine)
                 if joined and (st.mean_width > 0 or dashed) else None),
            symbol=None if dashed else (PG_SYM.get(sym, "o") or "o"),
            symbolSize=st.symbol_size * PX * (1.1 if small else 1.4),
            symbolBrush=None if open_ else qc, symbolPen=pg.mkPen(qc) if open_ else None,
            connect="finite", name=html.escape(name))
        add(main)
        if vb is not None:
            self.legend.addItem(main, html.escape(name))
        for it in linked:
            main.visibleChanged.connect(lambda it=it, mm=main: it.setVisible(mm.isVisible()))
        if vb is None:
            err = st.error if st.error != "none" else ""
            self._hover_pts.append((name, x, m, lo, hi, xlo, xhi, err, x_name, y_name, main))

    def _hover(self, pos) -> None:
        """The values of the point under the mouse (main Y axis), in the line
        under the graph."""
        vb = self.plot.getViewBox()
        if not self._hover_pts or not vb.sceneBoundingRect().contains(pos):
            return
        pt = vb.mapSceneToView(pos)
        dx, dy = vb.viewPixelSize()
        best = None
        for name, x, m, lo, hi, xlo, xhi, err, xn, yn, item in self._hover_pts:
            if not item.isVisible() or not len(x):
                continue
            with np.errstate(invalid="ignore"):
                d = ((x - pt.x()) / max(dx, 1e-12)) ** 2 + ((m - pt.y()) / max(dy, 1e-12)) ** 2
            if not np.isfinite(d).any():
                continue
            i = int(np.nanargmin(d))
            if best is None or d[i] < best[0]:
                best = (float(d[i]), name, x, m, lo, hi, xlo, xhi, err, xn, yn, i)
        if best is None or best[0] > 14 ** 2:
            self.lbl_hover.setText("Hover a point to read its values.")
            return
        _d, name, x, m, lo, hi, xlo, xhi, err, xn, yn, i = best

        def pm(v, a, b):
            if a is None or not err or not (np.isfinite(a[i]) and np.isfinite(b[i])):
                return f"{v:.4g}"
            return f"{v:.4g} ± {(b[i] - a[i]) / 2:.3g} ({err})"
        self.lbl_hover.setText(f"{name}:  {xn} = {pm(x[i], xlo, xhi)};  {yn} = {pm(m[i], lo, hi)}")

    def _reset_zoom(self) -> None:
        self.plot.getViewBox().enableAutoRange()
        vb2 = getattr(self, "_vb2", None)
        if vb2 is not None:
            vb2.enableAutoRange()

    # ------------------------------------------------------------ Y vs X
    def _draw_pairs(self, lines, colours, sp, warn, right=None) -> None:
        """Y against another measure (xyplot.PairLine); right: (lines, spec) of a
        second Y measure against the same X on the right axis (V2.8)."""
        st = self.style
        self.lbl_warn.setText(warn)
        self.lbl_warn.setVisible(bool(warn))
        self.btn_save.setEnabled(bool(lines))
        self.lbl_info.setText("Plotted: " + "; ".join(
            f"{p.label} ({p.n_dishes} run{'s' if p.n_dishes != 1 else ''}, {p.n_cells} cells"
            f"{' in both compartments' if p.points != 'trajectory' or True else ''})"
            for p in lines) if lines else "")
        css = {"font-size": f"{st.font_pt:g}pt", "font-family": "Arial", "color": "#000000"}
        self.plot.getAxis("bottom").setTicks(None)
        self.plot.setLabel("bottom", html.escape(st.x_title.strip() or sp.x.short()), **css)
        self.plot.setLabel("left", html.escape(st.y_title.strip() or sp.y.short()), **css)
        self.plot.setTitle(html.escape(self.ed_title.text().strip() or
                                       f"{sp.y.short()} vs {sp.x.short()}"),
                           size=f"{st.font_pt:g}pt")
        if not lines:
            return
        from ..prismfile import series_symbols
        syms = series_symbols(st.to_dict(), len(lines))
        for p, col, sym in zip(lines, colours, syms):
            xm, xl, xh, ym, yl, yh = XP.point_stats(p, st.error)
            traj = p.points == "trajectory"
            cells = None
            if traj and p.x.shape[1] == p.y.shape[1]:
                cells = [(p.x[:, j], p.y[:, j]) for j in range(p.y.shape[1])]
            self._draw_line(XP.legend_label(p), xm, ym, yl if traj else None,
                            yh if traj else None, col, sym, xlo=xl if traj else None,
                            xhi=xh if traj else None, cells=cells, joined=traj,
                            small=False, x_name=sp.x.quantity, y_name=sp.y.quantity)
            qc = QColor(col)
            ok = np.isfinite(xm) & np.isfinite(ym)
            if traj and ok.any():            # V2.8: where the trajectory starts and ends
                i0 = int(np.argmin(np.abs(np.where(np.isfinite(p.t), p.t, np.inf))))
                i0 = i0 if ok[i0] else int(np.nonzero(ok)[0][0])
                i1 = int(np.nonzero(ok)[0][-1])
                start = pg.ScatterPlotItem([xm[i0]], [ym[i0]], symbol="o",
                                           size=self.style.symbol_size * PX * 3.2,
                                           brush=pg.mkBrush(None), pen=pg.mkPen(qc, width=2))
                end = pg.ScatterPlotItem([xm[i1]], [ym[i1]], symbol="t1",
                                         size=self.style.symbol_size * PX * 3.2,
                                         brush=pg.mkBrush(qc), pen=pg.mkPen("#000000"))
                for it in (start, end):
                    self.plot.addItem(it)
                main = self._hover_pts[-1][-1]
                for it in (start, end):
                    main.visibleChanged.connect(lambda it=it, mm=main: it.setVisible(mm.isVisible()))
            if not traj and ok.any():        # V2.8: the group's mean ± error as a cross
                ex = GS.stats(xm[ok][:, None].T, self.style.error)
                ey = GS.stats(ym[ok][:, None].T, self.style.error)
                mx, mxl, mxh = ex[0][0], ex[1][0], ex[2][0]
                my, myl, myh = ey[0][0], ey[1][0], ey[2][0]
                pen = pg.mkPen(qc, width=2.5)
                cross = pg.ErrorBarItem(x=np.array([mx]), y=np.array([my]),
                                        left=np.array([mx - mxl if np.isfinite(mxl) else 0]),
                                        right=np.array([mxh - mx if np.isfinite(mxh) else 0]),
                                        top=np.array([myh - my if np.isfinite(myh) else 0]),
                                        bottom=np.array([my - myl if np.isfinite(myl) else 0]),
                                        pen=pen, beam=0)
                centre = pg.ScatterPlotItem([mx], [my], symbol="+",
                                            size=self.style.symbol_size * PX * 4, pen=pen)
                main = self._hover_pts[-1][-1]
                for it in (cross, centre):
                    self.plot.addItem(it)
                    main.visibleChanged.connect(lambda it=it, mm=main: it.setVisible(mm.isVisible()))
        if lines and lines[0].points == "trajectory":
            self.lbl_hover.setText("○ = start (baseline)   ▲ = last timepoint.   Hover a point to "
                                   "read its values; click a legend entry to hide that line.")
        elif lines:
            self.lbl_hover.setText("Each dot = one cell (one dish for 'mean of dish means'); the "
                                   "cross = the mean ± " + (self.style.error if self.style.error
                                                            != "none" else "-") +
                                   " of the dots. Hover a dot to read its values.")
        if right:
            lines2, sp2 = right
            vb2 = self._right_axis()
            self.plot.setLabel("right", html.escape(sp2.y.short()), **css)
            for p, col in zip(lines2, colours):
                xm, xl, xh, ym, yl, yh = XP.point_stats(p, st.error)
                self._draw_line(f"{XP.legend_label(p)} - {sp2.y.quantity} (right)", xm, ym, None,
                                None, col, "none", joined=p.points == "trajectory", vb=vb2,
                                dashed=True)
            vb2.enableAutoRange()
        self.plot.getViewBox().enableAutoRange()

    def refresh(self) -> None:
        self.plot.clear()
        self.legend.clear()
        self._clear_right()
        self._hover_pts = []
        self._paint_rows()
        sp = self.spec() if hasattr(self, "row_y2") else None
        probs = sp.problems() if sp is not None else []
        if hasattr(self, "lbl_problem"):
            self.lbl_problem.setText(" ".join(probs))
            self.lbl_problem.setVisible(bool(probs))
        pl = self.pair_lines() if hasattr(self, "row_x") else None
        if pl is not None:
            dup = self.duplicate_warning()
            self.lbl_dup.setText(("⚠ " + dup) if dup else "")
            self.lbl_dup.setVisible(bool(dup))
            right = None
            if sp is not None and sp.y2 is not None and pl[0]:
                sp2 = XP.Spec(sp.y2, sp.x, None, sp.points, sp.at, sp.win, sp.x_axis)
                r2 = self._pairs_for(sp2)
                right = (r2[0], sp2) if r2 and r2[0] else None
            self._draw_pairs(*pl, right=right)
            return
        lines, colours, comp, q, warn = self.current()
        self.lbl_warn.setText(warn)
        self.lbl_warn.setVisible(bool(warn))
        dup = self.duplicate_warning()
        self.lbl_dup.setText(("⚠ " + dup) if dup else "")
        self.lbl_dup.setVisible(bool(dup))
        self.btn_save.setEnabled(bool(lines))
        self.lbl_info.setText(self._info_text(lines))
        if not lines:
            self.plot.setTitle(html.escape("Tick the runs to compare" if not self.chosen() else
                                           "These runs have no compartment / quantity in "
                                           "common" if not q else ""))
            runs = self.chosen()
            if runs and not q:                # V2.8: say which runs have what
                by: Dict[str, List[str]] = {}
                for r in runs:
                    key = (", ".join(C.COMP_LABELS.get(c, c) for c in r.comps()) or "nothing") + \
                        " with " + "/".join(sorted(r.channels))
                    by.setdefault(key, []).append(r.label)
                self.lbl_warn.setText(
                    "Nothing can be plotted for all the ticked runs together - they were "
                    "measured in different compartments or channels: " + "; ".join(
                        f"{k}: {', '.join(v[:4])}{' …' if len(v) > 4 else ''}"
                        for k, v in by.items()) + ". Tick runs measured the same way.")
                self.lbl_warn.setVisible(True)
            return
        if self.graph() != GRAPH_TIME:
            self._draw_kinetics(lines, colours, comp, q)
            return
        self.plot.getAxis("bottom").setTicks(None)
        from ..prismfile import series_symbols
        st = self.style
        syms = series_symbols(st.to_dict(), len(lines))
        css = {"font-size": f"{st.font_pt:g}pt", "font-family": "Arial", "color": "#000000"}
        xt, yt = GS.axis_titles(st, lines[0].x_label, q)
        self.plot.setLabel("bottom", html.escape(xt), **css)
        self.plot.setLabel("left", html.escape(yt), **css)
        self.plot.setTitle(html.escape(self.title_text(comp, q)), size=f"{st.font_pt:g}pt")
        for s, col, sym in zip(lines, colours, syms):
            m, lo, hi, _n = GS.stats(s.y, st.error)
            reps = s.y if not isinstance(s, C.GroupLine) or s.kind == "pooled" else s.dish_mean
            cells = [(s.x, reps[:, j]) for j in range(reps.shape[1])]
            self._draw_line(C.legend_label(s), s.x, m, lo, hi, col, sym, cells=cells,
                            x_name="time" if "min" in s.x_label else "timepoint", y_name=q)
        # the baseline: a dashed line at time 0 (every run is aligned on its baseline)
        self._baseline_line = pg.InfiniteLine(
            pos=0.0, angle=90, movable=False,
            pen=pg.mkPen(QColor(GS.BASELINE_COLOUR), width=1.2 * PX, style=Qt.DashLine))
        self._baseline_line.setZValue(-5)
        self.plot.addItem(self._baseline_line, ignoreBounds=True)
        if sp is not None and sp.y2 is not None:            # the right Y axis
            lines2, w2 = self._lines_for(sp.y2.comp, sp.y2.quantity)
            if w2 and w2 != warn:
                self.lbl_warn.setText((warn + " " if warn else "") + "Right axis: " + w2)
                self.lbl_warn.setVisible(True)
            vb2 = self._right_axis()
            self.plot.setLabel("right", html.escape(sp.y2.short()), **css)
            for s, col in zip(lines2, colours):
                m, _lo, _hi, _n = GS.stats(s.y, st.error)
                self._draw_line(f"{C.legend_label(s)} - {sp.y2.quantity} (right)", s.x, m, None,
                                None, col, "none", vb=vb2, dashed=True)
            vb2.enableAutoRange()
        vb = self.plot.getViewBox()
        vb.enableAutoRange()
        if st.x_min is not None or st.x_max is not None or st.y_min is not None \
                or st.y_max is not None:
            (x0, x1), (y0, y1) = vb.viewRange()
            vb.setRange(xRange=(st.x_min if st.x_min is not None else x0,
                                st.x_max if st.x_max is not None else x1),
                        yRange=(st.y_min if st.y_min is not None else y0,
                                st.y_max if st.y_max is not None else y1), padding=0)

    def kinetics_items(self, lines=None):
        from .. import kinetics as K
        if lines is None:
            lines = self.current()[0]
        return K.items_for(lines, self.chk_window.isChecked())

    def _draw_kinetics(self, lines, colours, comp, q) -> None:
        """Dot plot of one kinetics parameter: each dish a dot, the mean as a bar
        with the chosen error across the dishes (kinetics.draw, live)."""
        from .. import kinetics as K
        key = self.graph()
        st = self.style
        items = K.items_for(lines, self.chk_window.isChecked())
        css = {"font-size": f"{st.font_pt:g}pt", "font-family": "Arial", "color": "#000000"}
        self.plot.setLabel("bottom", "Group" if self.mode() != "runs" else "Run", **css)
        self.plot.setLabel("left", html.escape(K.axis_title(key, lines[0].x_label, q)), **css)
        self.plot.setTitle(html.escape(f"{K.PARAM_NAMES[key]} - {self.title_text(comp, q)}"),
                           size=f"{st.font_pt:g}pt")
        ticks = []
        for i, (it, col) in enumerate(zip(items, colours)):
            pos = i + 1
            v = it.values(key)
            fin = np.isfinite(v)
            qc = QColor(col)
            sm = K.summary(it, key)
            ticks.append((pos, f"{it.label} (n = {int(sm.n[0])})"))
            if fin.any():
                self.plot.plot((pos + K._offsets(len(v)))[fin], v[fin], pen=None, symbol="o",
                               symbolSize=max(6.0, st.symbol_size * PX * 1.6), symbolBrush=qc,
                               symbolPen=None, name=html.escape(it.label))
            m = sm.mean[0]
            if np.isfinite(m):
                self.plot.plot([pos - 0.28, pos + 0.28], [m, m],
                               pen=pg.mkPen(qc, width=max(1.0, st.mean_width * 2) * PX))
                err = {"SEM": sm.sem, "SD": sm.sd, "95% CI": sm.ci95}.get(st.error)
                if err is not None and np.isfinite(err[0]):
                    self.plot.addItem(pg.ErrorBarItem(
                        x=np.array([pos]), y=np.array([m]), height=np.array([2 * err[0]]),
                        beam=0.15, pen=pg.mkPen(qc, width=max(1.0, st.mean_width * 1.5) * PX)))
        self.plot.getAxis("bottom").setTicks([ticks])
        vb = self.plot.getViewBox()
        vb.enableAutoRange()
        vb.setXRange(0.4, len(items) + 0.6, padding=0)
        self.lbl_info.setText(self._kin_text(items, key, lines[0].x_label, q))

    def _kin_text(self, items, key: str, x_label: str, q: str) -> str:
        from .. import kinetics as K
        u = K.units(key, x_label, q)
        parts, flags = [], []
        for it in items:
            sm = K.summary(it, key)
            m, n = sm.mean[0], int(sm.n[0])
            e = {"SEM": sm.sem, "SD": sm.sd, "95% CI": sm.ci95}.get(self.style.error)
            txt = f"{it.label}: " + (f"{m:.4g}" if np.isfinite(m) else "-")
            if e is not None and np.isfinite(e[0]):
                txt += f" ± {e[0]:.3g} {GS.error_label(self.style.error)}"
            txt += f" {u}" + (f" (n = {n} dishes)" if it.mean_kin is not None else "")
            parts.append(txt)
            for nm, k in zip(it.names, it.kin):
                if k.flags:
                    flags.append(f"{nm}: {'; '.join(k.flags)}")
        out = (f"{K.PARAM_NAMES[key]}: " + "; ".join(parts) + ". " +
               K.window_text(items, x_label, self.chk_window.isChecked()))
        if flags:
            out += " Check: " + " | ".join(flags) + "."
        return out

    def _info_text(self, lines) -> str:
        if not lines or not isinstance(lines[0], C.GroupLine):
            return ""
        parts = []
        for g in lines:
            parts.append(f"{g.label}: {g.n_dishes} dish{'es' if g.n_dishes != 1 else ''} "
                         f"({', '.join(str(s.n) for s in g.dishes)} cells), "
                         f"{len(g.x)} common times")
        return "; ".join(parts) + "."

    # --------------------------------------------------------------- save
    def _default_folder(self) -> str:
        if self.out_dir:
            return str(Path(self.out_dir) / "Comparisons")
        runs = self.chosen()
        return str(Path(runs[0].path).parent / "Comparisons") if runs else str(Path.home())

    def _ask_save_path(self, folder: str, name: str) -> str:
        from ..safety import make_dirs
        try:
            make_dirs(folder)
        except OSError:
            folder = str(Path.home())
        path, _f = QFileDialog.getSaveFileName(
            self, "Save (the name is used for every file)",
            str(Path(folder) / f"{name}.prism"), "Prism project (*.prism)",
            options=QFileDialog.DontConfirmOverwrite)
        return path

    def default_name(self, lines, q: str) -> str:
        head = "Average_" if lines and isinstance(lines[0], C.GroupLine) else "Compare_"
        sp = self.spec() if hasattr(self, "row_x") else None
        if sp is not None and sp.x is not None:
            q = f"{q} vs {sp.x.quantity}"
        name = head + "_".join(s.label[:20] for s in lines[:3]) + "_" + \
            q.replace("/", "-").replace(" ", "_")
        return "".join(ch if ch.isalnum() or ch in "-_. ()" else "-" for ch in name)

    def _saved_files(self) -> None:
        from .outlogdlg import OutputsDialog
        OutputsDialog(self).exec()

    def _save_clicked(self) -> None:
        lines, _c, comp, q, _w = self.current()
        if not lines:
            return
        dup = self.duplicate_warning()
        if dup and not self._confirm_duplicates(dup):
            return
        if self._save_opts.exec() != QDialog.Accepted:       # file types, kinetics graphs
            return
        path = self._ask_save_path(self._default_folder(), self.default_name(lines, q))
        if not path:
            return
        p = Path(path)
        stem = p.stem if p.suffix.lower() in (".prism", ".png", ".svg", ".csv", ".xlsx",
                                              ".pdf", ".jpg", ".tif") else p.name
        files = self.save_to(str(p.parent), stem)
        if files:
            QMessageBox.information(self, "Compare runs", "Saved:\n" + "\n".join(
                plain_path(f) for f in files))

    # ------------------------------------------------- V2.7 saved plot settings
    def plot_settings(self) -> dict:
        sp = self.spec()
        return dict(spec=sp.to_dict() if sp else None, mode=self.mode(),
                    error=self.style.error, own_base=self.chk_own_base.isChecked(),
                    base=int(self.sp_base.value()), title=self.ed_title.text(),
                    formats=[k for k, cb in self.chk_fmt.items() if cb.isChecked()],
                    kinetics=[k for k, cb in self.chk_kin.items() if cb.isChecked()],
                    same_window=self.chk_window.isChecked(), graph=self.graph())

    def apply_plot_settings(self, p: dict) -> str:
        """Show the ticked runs the way p says. Returns a plain note ('' = all
        applied) - e.g. a measure the ticked runs do not have."""
        if not isinstance(p, dict):
            return "This file has no plot settings."
        self.set_mode(str(p.get("mode") or "runs"))
        if p.get("error") in GS.ERRORS:
            self.cmb_err.setCurrentIndex(max(0, self.cmb_err.findData(p["error"])))
        self.chk_own_base.setChecked(bool(p.get("own_base", True)))
        self.sp_base.setValue(int(p.get("base") or 1))
        self.ed_title.setText(str(p.get("title") or ""))
        for k, cb in self.chk_fmt.items():
            if isinstance(p.get("formats"), list):
                cb.setChecked(k in p["formats"])
        for k, cb in self.chk_kin.items():
            if isinstance(p.get("kinetics"), list):
                cb.setChecked(k in p["kinetics"])
        self.chk_window.setChecked(bool(p.get("same_window", True)))
        sp = XP.Spec.from_dict(p.get("spec"))
        note = ""
        if sp is not None:
            self.set_spec(sp)
            got = self.spec()
            miss = [m.text() for m, g in ((sp.y, got.y if got else None),
                                          (sp.x, got.x if got else None),
                                          (sp.y2, got.y2 if got else None))
                    if m is not None and m != g]
            if miss:
                note = ("The ticked runs do not all have: " + "; ".join(miss) +
                        ". The closest available measure is shown instead.")
        i = self.cmb_graph.findData(p.get("graph") or GRAPH_TIME)
        if i >= 0 and self.cmb_graph.isEnabled():
            self.cmb_graph.setCurrentIndex(i)
        self.refresh()
        return note

    def _save_plot_settings(self) -> None:
        from .. import presets as PR
        name, ok = QInputDialog.getText(self, "Save plot settings", "Name of these settings:",
                                        text=(self.spec().sentence()[5:60] if self.spec()
                                              else "my plot"))
        if not ok or not name.strip():
            return
        try:
            path = PR.save(PR.folder() / f"{PR.safe_name(name)}.json", name.strip(),
                           plot=self.plot_settings())
        except OSError as e:
            QMessageBox.warning(self, "Save plot settings", error_text(e))
            return
        QMessageBox.information(self, "Save plot settings", f"Saved:\n{plain_path(path)}")

    def _pick_settings(self, many: bool = False) -> List[str]:
        from .. import presets as PR
        start = str(PR.folder())
        if many:
            paths, _f = QFileDialog.getOpenFileNames(self, "Saved settings", start,
                                                     "PeterPiper settings (*.json)")
            return list(paths)
        path, _f = QFileDialog.getOpenFileName(self, "Saved settings", start,
                                               "PeterPiper settings (*.json)")
        return [path] if path else []

    def _load_plot_settings(self) -> None:
        from .. import presets as PR
        for path in self._pick_settings():
            try:
                note = self.apply_plot_settings(PR.read(path).get("plot"))
            except ValueError as e:
                QMessageBox.warning(self, "Load plot settings", error_text(e))
                return
            if note:
                QMessageBox.information(self, "Load plot settings", note)

    def batch_save(self, settings_paths: Sequence[str], folder: str) -> List[Tuple[str, str]]:
        """Each saved plot setting, plotted for the ticked runs and saved into
        folder as '<settings name>.<ext>'. Returns [(settings name, note or
        'saved n files')]."""
        from .. import presets as PR
        keep = self.plot_settings()
        out = []
        try:
            for path in settings_paths:
                try:
                    blob = PR.read(path)
                    note = self.apply_plot_settings(blob.get("plot"))
                    files = self.save_to(folder, PR.safe_name(blob.get("name") or Path(path).stem),
                                         quiet=True)
                    out.append((str(blob.get("name")), (note + " " if note else "") +
                                f"saved {len(files)} file(s)"))
                except ValueError as e:
                    out.append((Path(path).stem, error_text(e)))
        finally:
            self.apply_plot_settings(keep)
        return out

    def _batch_save(self) -> None:
        if not self.chosen():
            QMessageBox.information(self, "Batch save", "Tick the runs first.")
            return
        paths = self._pick_settings(many=True)
        if not paths:
            return
        folder = QFileDialog.getExistingDirectory(self, "Save into this folder",
                                                  self._default_folder())
        if not folder:
            return
        res = self.batch_save(paths, folder)
        QMessageBox.information(self, "Batch save", "\n".join(f"{n}: {t}" for n, t in res))

    def _templates(self) -> None:
        from .templatedlg import TemplateDialog
        TemplateDialog(lambda st: self.set_style(dict(self.style.to_dict(), **st)), self).exec()

    def kinetics_to_save(self) -> List[str]:
        """The ticked kinetics graphs (plus the one shown, if a kinetics one)."""
        out = [k for k, cb in self.chk_kin.items() if cb.isChecked()]
        if self.graph() != GRAPH_TIME and self.graph() not in out:
            out.append(self.graph())
        return out

    def save_to(self, folder: str, name: str, formats: Optional[Sequence[str]] = None,
                quiet: bool = False, kinetics: Optional[Sequence[str]] = None) -> List[str]:
        """Write what is shown now (formats default: the ticked ones; kinetics
        default: the ticked kinetics graphs)."""
        formats = list(formats) if formats is not None else \
            [k for k, cb in self.chk_fmt.items() if cb.isChecked()]
        pl = self.pair_lines()
        lines, colours, comp, q, _w = self.current()
        if not lines or (pl is not None and not pl[0]):
            return []
        if not formats:
            if not quiet:
                QMessageBox.information(self, "Compare runs", "Tick at least one file type.")
            return []
        try:
            if pl is not None:                          # V2.7: Y vs another measure
                plines, pcols, sp, _w = pl
                title = self.ed_title.text().strip() or f"{sp.y.short()} vs {sp.x.short()}"
                right = None
                if sp.y2 is not None:
                    sp2 = XP.Spec(sp.y2, sp.x, None, sp.points, sp.at, sp.win, sp.x_axis)
                    r2 = self._pairs_for(sp2)
                    right = (r2[0], sp2) if r2 and r2[0] else None
                notes = XP.notes_text(plines, sp, self.style)
                files = W.run_with_progress(           # V2.9: a bar while writing
                    self, f"Saving '{name}'",
                    lambda _p: XP.save(folder, name, formats, plines, pcols, self.style, sp,
                                       title, notes, right=right))
            else:
                sp = self.spec()
                right = None
                if sp is not None and sp.y2 is not None:
                    right = (self._lines_for(sp.y2.comp, sp.y2.quantity)[0], sp.y2.comp,
                             sp.y2.quantity)
                title = self.title_text(comp, q)
                notes = C.notes_text(lines, comp, q, self.style)
                kin = self.kinetics_to_save() if kinetics is None else kinetics
                same = self.chk_window.isChecked()
                files = W.run_with_progress(           # V2.9: a bar while writing
                    self, f"Saving '{name}'",
                    lambda _p: C.save(folder, name, formats, lines, colours, self.style, comp,
                                      q, title, notes, kinetics=kin,
                                      kinetics_same_window=same, right=right))
        except (OSError, ValueError) as e:
            if not quiet:
                QMessageBox.warning(self, "Compare runs", "The comparison could not be "
                                                          f"saved:\n{error_text(e)}")
            return []
        self.saved = files
        from .. import outlog                    # V2.8: the log of every save
        sp = self.spec()
        outlog.record("compare", name, files, sp.sentence() if sp else "")
        return files
