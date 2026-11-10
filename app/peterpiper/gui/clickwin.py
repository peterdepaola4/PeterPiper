"""
The PeterPiper main window: you click, the app draws; every ROI is redrawn at every
timepoint when tracked. Nothing is detected automatically.

Left: the image - Play / Pause, the timepoint slider, which channel is shown,
outlines and numbers on / off, brightness.
Right, top to bottom (the blue box always says what to do next):
    1  Tracking rules       one rule per compartment:
                            'Track [Nucleus] using [Cy5]  [ONLY|WITH|AND|IF] intensity in [GFP]'
                            (every channel is measured in every ROI - always)
    2  Add ROIs             Compartment (drawn and followed on its rule's image);
                            on/off tools: Add, Remove, Draw by hand, Resize, Split,
                            Add to cell (click a tool again to turn it off).
                            Right-click an ROI to move it to another cell or make
                            it a cell of its own.
    3  Track and measure    every ROI redrawn at every timepoint
    4  Check                Play, and the trace panel (include / exclude lives there;
                            its 'As exported' view is the live graph: choose its look
                            there - the PNG export draws exactly that - and 'Save this
                            graph...' writes it as .prism / PNG / SVG)
    5  Export               your export list: only what you pick is written

V2.5: the background may be drawn by hand (Compartment 'Background' > Draw by
hand: a freehand outline) and includes cells; 'Tracker boundary' (step 3) draws
lines a cell's ROIs never cross; AUTO-DETECT shows a slider that keeps only the
brightest cells found; a session identical to the last one saved is not saved
again.

v2.3 session memory: your work (ROIs, tracking, include / exclude, baseline...)
is saved automatically into <results folder>/PeterPiper_sessions as you work (one
file per window session, replaced in one step - never anyone else's file), and
when an .nd2 analysed before is opened, the earlier runs are offered
(historydlg.PreviousRunsDialog; File > Earlier analyses of this file...).
"""
from __future__ import annotations

import copy
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QCursor, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDockWidget,
                               QFileDialog, QHBoxLayout, QInputDialog, QLabel, QMainWindow, QMenu,
                               QMessageBox, QPushButton, QScrollArea, QSlider, QSplitter,
                               QVBoxLayout, QWidget)

from .. import APP_NAME, APP_TITLE, __version__
from .. import graphstyle as GS
from .. import history
from ..config import Experiment, Settings, save_settings
from ..export import (catalog, clean_prefix, graph_file_name, run_export, save_graph_files,
                      standard)
from ..plots import preferred_sheets
from ..manual import (COMPS, FILE_NAMES, LABELS, _overlap_px, _region, extend_roi,
                      resize_roi, split_roi, auto_background, auto_select, background_at, cut_overlaps, draw_at,
                      from_outline, link_cell, track_cells, background_from_outline,
                      background_warning)
from ..nd2io import ImageSource, export_tiffs
from ..qc import gate_reason, run_qc
from ..roifile import (load_roi_file, load_roi_state, load_roi_track, read_summary, roi_path,
                       save_roi_file, session_blob, track_problem, write_session_blob)
from ..rules import (HELP, MODE_HELP, MODE_LABELS, MODES, TrackRule, apply_and, default_rules,
                     gate_snr, guide_key, guide_plane, make_norm)
from ..safety import error_text, exists, is_dir, plain_path
from ..segment import Roi
from . import widgets as W
from .exportdlg import ExportDialog, SaveGraphDialog
from .frames import FrameStore
from .historydlg import PreviousRunsDialog, when_text
from .imageview import ImageView
from .widgets import cell_colour

COMPARE_TIP = ("Compare saved runs (this file's and others'): one coloured mean ± SEM line per "
               "run, n = its included cells, saved as one Prism file + PNG / SVG / CSV. Save "
               "this run first (it is saved automatically) to include it.")
from .traces import TracePanel
from .workers import FuncJob, JobRunner

FOLLOW = ["nucleus", "cell", "cytoplasm", "mito"]
HINTS = {
    "nucleus": "Click the middle of each nucleus you can see on {ch}.",
    "cell": "Click inside each whole cell you can see on {ch}.",
    "cytoplasm": "Click in the cytoplasm of each cell on {ch}. The nucleus is cut out for "
                 "you (that cell's nucleus ROI if you drew one, otherwise the dark hole).",
    "mito": "Click on each cell's mitochondria on {ch}: the region holding them is outlined "
            "and the mitochondria inside it (strands / puncta) are found as many small "
            "pieces - only those pixels are measured, not the space between them.",
    "background": "ADD: click to put a 60 µm background square there. DRAW BY HAND: hold the "
                  "button and draw around the region you want. Cells in it are fine (their "
                  "autofluorescence is background). Every pixel of the region is used; after "
                  "tracking you are told if the background jumps or drifts, and can redraw it.",
}
TOOLS = {"add": ("Add", "#2e9e4f", "● ADDING"),
         "remove": ("Remove", "#c94040", "● REMOVING"),
         "draw": ("Draw by hand", "#d98a1f", "● DRAWING"),
         "resize": ("Resize", "#7b4fc9", "● RESIZING"),
         "split": ("Split", "#1f8a99", "● SPLITTING"),
         "extend": ("Add to cell", "#b0458f", "● ADDING TO CELL")}
ACTIVE = {"add": "ADDING {c} on {ch}: click each one. Click Add again (or Esc) to stop.",
          "remove": "REMOVING {c}: click the ones to delete. Click Remove again (or Esc) to stop.",
          "draw": "DRAWING {c} by hand: click around it, double-click to finish. Click again "
                  "(or Esc) to stop.",
          "resize": "RESIZING {c}: click a cell, then scroll up (bigger) or down (smaller) - "
                    "as far as you like. Click Resize again (or Esc) to stop.",
          "split": "SPLITTING {c}: hold the left button and draw a line through an ROI - it "
                   "becomes two cells. Click Split again (or Esc) to stop.",
          "extend": "ADDING TO A CELL ({c}): click the cell's ROI, then click each missed "
                    "part next to it. Click the tool again (or Esc) to stop."}
TOOL_HELP = {
    None: "No tool on: clicking the image selects a cell (its trace lights up). "
          "Turn on Add to add ROIs.",
    "add": "Click the image: an ROI of the chosen compartment is drawn around each click.",
    "remove": "Click an ROI of the chosen compartment to delete it.",
    "draw": "Click around the outline; double-click (or right-click) to finish each one.",
    "resize": "Click a cell, then scroll the mouse wheel: up = bigger, down = smaller "
              "(12 % per notch, no limit; redrawn from the image). 'Resize all cells "
              "together' does every cell at once.",
    "split": "Hold the left mouse button and draw a line across an ROI: it is cut along "
             "the line into two cells (the line's ends are continued, so roughly across "
             "is enough).",
    "extend": "Click an ROI to pick its cell, then click outside it where the cell continues: "
              "that part is outlined from the image and joined to the ROI.",
}


AUTOSAVE_MS = 2000          # autosave this long after the last change (milestones: at once)
_INDEX_LOCK = threading.Lock()   # run_history.json is written from several threads


def _blank() -> Roi:
    r = Roi((0, 0, 1, 1), np.zeros((1, 1), bool), "empty")
    r.include = False
    return r


def _same_path_key(p) -> str:
    return os.path.normcase(os.path.abspath(plain_path(str(p))))


def record_run(nd2_path, path) -> None:
    """Add an ROI / session file to this computer's list of runs (history.py);
    never raises. Any thread."""
    try:
        with _INDEX_LOCK:
            history.record_run(nd2_path, path, read_summary(path))
    except Exception:                                              # noqa: BLE001
        pass


class _SessionWriter(QObject):
    """Writes the session file in a background thread (packing is done before,
    in the window's thread, so what is written is a consistent snapshot).
    One write at a time; a newer snapshot of the same file replaces one still
    waiting (latest wins) - a snapshot for another file (a new session after
    loading a run) waits its turn. done(path, error, write ms) arrives in the
    window's thread."""

    done = Signal(str, str, float)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._lock = threading.Lock()
        self._jobs: Dict[str, tuple] = {}            # file -> newest snapshot (in order)
        self._thread: Optional[threading.Thread] = None

    def submit(self, path: Path, blob: dict, nd2_path: str) -> None:
        with self._lock:
            self._jobs[str(path)] = (Path(path), blob, str(nd2_path))
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, name="PeterPiper autosave",
                                                daemon=True)
                self._thread.start()

    def busy(self) -> bool:
        with self._lock:
            return self._thread is not None

    def _run(self) -> None:
        while True:
            with self._lock:
                job = self._jobs.pop(next(iter(self._jobs)), None) if self._jobs else None
                if job is None:
                    self._thread = None
                    return
            path, blob, nd2 = job
            t = time.perf_counter()
            err = ""
            try:
                write_session_blob(path, blob)
            except Exception as exc:                               # noqa: BLE001
                err = error_text(exc)
            ms = (time.perf_counter() - t) * 1000.0
            if not err:
                record_run(nd2, path)
            self.done.emit(str(path), err, ms)

    def flush(self, timeout: float = 60.0) -> None:
        """Wait until everything submitted is on disk (closing the window)."""
        end = time.perf_counter() + timeout
        while time.perf_counter() < end:
            with self._lock:
                t = self._thread
            if t is None:
                return
            t.join(0.05)


def _has_outline(r) -> bool:
    o = getattr(r, "outline", None)
    return o is not None and bool(np.any(o))


class ClickWindow(QMainWindow):

    def __init__(self, src: ImageSource, exp: Experiment, s: Settings) -> None:
        super().__init__()
        self.src, self.exp, self.settings = src, exp, s
        from .. import users
        self.setWindowTitle(f"{APP_NAME} {__version__}  -  {Path(exp.nd2_path).name}"
                            + (f"  ({users.current()})" if users.current() else ""))
        self.resize(1600, 960)
        self.cells: List[Dict[str, Roi]] = []        # [cell][compartment] -> ROI
        self.excl: Dict[str, set] = {c: set() for c in COMPS}
        self.background: Optional[Roi] = None
        self._bg_auto = False                        # V3.0: you place it (batch: automatic)
        self._bg_kind = "click"                      # "auto" | "click" | "hand" (V2.5)
        # V2.5 tracker boundary lines: {cell index: [line, ...]}, a line = [(x, y), ...]
        self.boundaries: Dict[int, List[List[tuple]]] = {}
        self._bound_on = False                       # 'Tracker boundary' is on
        self._bound_k: Optional[int] = None          # ... the cell whose lines are drawn
        self._auto_batch: Optional[dict] = None      # V2.5 AUTO-DETECT slider state
        self._auto_applying = False
        self._last_key: Optional[str] = None         # content key of the last session saved
        self.t0: Optional[int] = None                # the timepoint ROIs are drawn on
        self.track: Optional[dict] = None
        self.qc: Dict[str, list] = {}
        # v2.3 tracking rules, one per followed compartment, in order (the first one
        # leads: cells move with it). follow is derived from it: every followed
        # compartment measures every channel.
        self.rules: Dict[str, TrackRule] = {}
        self.follow: Dict[str, List[int]] = {}       # compartment -> measured channels (all)
        self._norm = None                            # (timepoint, rules.GuideNorm) cache
        self._guides: Dict[tuple, np.ndarray] = {}   # (t, guide key) -> guide plane (WITH)
        self._and_view: Dict[tuple, tuple] = {}      # AND rules: seed ROI -> kept-pixel copy
        self._gate_why: Dict[str, Dict[int, str]] = {c: {} for c in COMPS}   # IF exclusions
        self._quiet_rules = False                    # rebuilding rows (start-up / loading)
        self.comp = "nucleus"
        self.view_comp = "nucleus"
        self.tool: Optional[str] = None
        self.selected: Optional[int] = None
        self._link_from = None                       # (cell, compartment) being moved
        self._undo_stack: list = []
        self._runner: Optional[JobRunner] = None
        self.go_back = False
        self.cur_t = 0
        self._waiting: Optional[int] = None
        self._was_tracked = False
        self._stale_rules = False                    # tracking cleared by a rule change
        self._restoring_settings = False             # spin boxes set from a file
        self._exported: Optional[str] = None
        self._graph_formats: List[str] = ["prism", "png"]   # 'Save this graph...' choices
        self._graph_folder: Optional[str] = None
        # v2.3 session memory: this window's session file (written only once there is
        # something to keep), the .nd2 fingerprint (cached), autosave bookkeeping
        self.session_id = history.new_session_id()
        self._fingerprint: Optional[dict] = None
        self._session_file: Optional[Path] = None    # set by the first autosave
        self._based_on: Optional[str] = None          # the earlier run loaded, if any
        self._dirty = False                           # changed since the last autosave
        self._restoring = False                       # loading a file: not a change of yours
        self._offered = False                         # earlier runs offered (once)
        self._bg_tried = True                         # V3.0: no automatic background
        self._rules_seen = False                      # V3.0: step 1 looked at (step bar)
        self._save_log: List[dict] = []               # autosave timings (pack / write ms)
        self._writer = _SessionWriter(self)
        self._writer.done.connect(self._on_session_saved)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(AUTOSAVE_MS)
        self._save_timer.timeout.connect(self._autosave)
        frame_bytes = exp.n_channels * exp.height * exp.width * 2
        # V2.9: a half-size display copy for big frames (made by the readers)
        side = min(int(getattr(exp, "height", 0) or 0), int(getattr(exp, "width", 0) or 0))
        self.store = FrameStore(src, exp.n_timepoints, frame_bytes,
                                preview_f=2 if side >= 1600 else 1)
        self.store.ready.connect(self._frame_ready)
        from .. import measure                     # V3.0: the ratio baseline check
        measure.set_min_snr(getattr(self.settings, "ratio_min_snr", 5.0))
        first = getattr(src, "_pd4_first", None)            # V2.9: read by the start window
        if first is not None:
            self.store.seed(*first)
            src._pd4_first = None
        self._play = QTimer(self)
        self._play.timeout.connect(self._play_tick)
        self._rows: List[dict] = []
        self._build_ui()
        self._set_rules(self._start_rules(), quiet=True)
        self._show_frame(autorange=True)
        self._set_tool(None)
        self.set_status(f"Opened {Path(exp.nd2_path).name}: {exp.n_timepoints} timepoints, "
                        f"{exp.n_channels} channels ({', '.join(exp.channels)}), "
                        f"{exp.width} x {exp.height} px. Pick a background spot yourself: "
                        f"right-click an empty area > 'Put the background region here' (or "
                        f"Compartment 'Background', then Add / Draw by hand).")
        self.store.prefetch(0, ahead=6, behind=0)
        # V3.0: no automatic background region - it often sat on real cells; you
        # place it (batch analysis, with nobody to click, still places it itself)
        if exp.export_tiffs:
            QTimer.singleShot(600, self._export_tiffs)

    # ================================================================== UI
    def _build_ui(self) -> None:
        splitter = QSplitter(Qt.Horizontal)
        self.setCentralWidget(splitter)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(4, 4, 4, 4)
        ll.setSpacing(4)
        self.view = ImageView()
        self.view.point_clicked.connect(self._on_point)
        self.view.polygon_done.connect(self._on_polygon)
        self.view.stroke_done.connect(self._on_stroke)
        self.view.lasso_done.connect(self._on_lasso)
        self.view.polyline_done.connect(self._on_boundary_line)
        self._extend_k: Optional[int] = None          # Add to cell: the cell being added to
        self.view.context_requested.connect(self._on_context)
        self.view.escape_pressed.connect(self._on_escape)
        self.view.wheel_steps.connect(self._on_wheel)
        self._live_roi = None
        self.view.status.connect(self.set_status)
        ll.addWidget(self.view, 1)

        nav = QWidget()
        nl = QHBoxLayout(nav)
        nl.setContentsMargins(2, 0, 2, 0)
        nl.addWidget(QLabel("Timepoint"))
        nl.addWidget(W.button("◀", lambda: self._step(-1), "Previous timepoint"))
        self.btn_play = QPushButton("▶  Play")
        self.btn_play.setCheckable(True)
        self.btn_play.setToolTip("Play through time to watch the cells (and their ROIs) move.")
        self.btn_play.toggled.connect(self._play_toggled)
        nl.addWidget(self.btn_play)
        nl.addWidget(W.button("▶|", lambda: self._step(1), "Next timepoint"))
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(1, max(1, self.exp.n_timepoints))
        self.slider.setEnabled(self.exp.n_timepoints > 1)
        self.slider.valueChanged.connect(self._on_slider)
        nl.addWidget(self.slider, 1)
        self.lbl_t = QLabel("")
        self.lbl_t.setMinimumWidth(190)
        self.lbl_t.setAlignment(Qt.AlignCenter)
        nl.addWidget(self.lbl_t)
        self.cmb_fps = QComboBox()
        for f in (2, 4, 8, 15, 25):
            self.cmb_fps.addItem(f"{f} per s", f)
        i = self.cmb_fps.findData(int(self.settings.play_fps or 8))
        self.cmb_fps.setCurrentIndex(i if i >= 0 else 2)
        self.cmb_fps.setToolTip("Play speed (timepoints per second).")
        self.cmb_fps.currentIndexChanged.connect(self._fps_changed)
        nl.addWidget(self.cmb_fps)
        ll.addWidget(nav)

        disp = QWidget()
        dl = QHBoxLayout(disp)
        dl.setContentsMargins(2, 0, 2, 0)
        dl.addWidget(QLabel("Show"))
        self.cmb_view = QComboBox()
        self.cmb_view.setToolTip("What the image shows: one channel, two channels overlaid, "
                                 "or (for a rule with helper channels) the tracking image - "
                                 "the combined image the ROIs are drawn and followed on.")
        self._overlay_pairs = []
        for i in range(self.exp.n_channels):
            for j in range(i + 1, self.exp.n_channels):
                self._overlay_pairs.append((i, j))
        self._view_items: List[tuple] = []         # ("ch", i) / ("overlay", i, j) / ("guide", comp)
        self._fill_view_items()
        self.cmb_view.currentIndexChanged.connect(self._view_changed)
        dl.addWidget(self.cmb_view)
        dl.addWidget(W.button("Fit to window", self.view.fit))
        self.chk_outlines = QCheckBox("Outlines")
        self.chk_outlines.setChecked(True)
        self.chk_outlines.setToolTip("Show / hide every ROI outline (to look at the cells).")
        self.chk_outlines.toggled.connect(self.view.set_show_outlines)
        dl.addWidget(self.chk_outlines)
        self.chk_numbers = QCheckBox("Cell numbers")
        self.chk_numbers.setChecked(True)
        self.chk_numbers.toggled.connect(self.view.set_show_numbers)
        dl.addWidget(self.chk_numbers)
        dl.addStretch(1)
        ll.addWidget(disp)
        self.progress = W.ProgressStrip()
        ll.addWidget(self.progress)
        splitter.addWidget(left)

        scroll = QScrollArea()
        self._side_scroll = scroll
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(360)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)   # never hide anything
        panel = QWidget()
        self.side = QVBoxLayout(panel)
        self.side.setContentsMargins(6, 6, 6, 6)
        self.side.setSpacing(5)
        scroll.setWidget(panel)
        from PySide6.QtWidgets import QSizePolicy
        # never squeezed shorter than its contents (that cut off the last line of
        # some boxes): it scrolls instead
        panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        self._build_side()
        self.side.addStretch(1)
        splitter.addWidget(scroll)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([1060, 470])
        self._scaler = W.FontScaler(self, lambda: self.settings.ui_font_pt, (1600, 960))
        self._build_menu()
        # the live graph: its look is Settings.graph_style (the PNG export draws the
        # same); changing it is remembered and saved with the session
        self.traces = TracePanel(self.exp,
                                 style=dict(getattr(self.settings, "graph_style", None) or {}))
        self.traces.cell_selected.connect(self._select)
        self.traces.include_set.connect(lambda k, on: self._set_include(self.view_comp, k, on))
        self.traces.include_all.connect(self._include_all)
        self.traces.time_clicked.connect(lambda t: self.slider.setValue(int(t) + 1))
        self.traces.style_changed.connect(self._graph_style_changed)
        self.traces.export_requested.connect(self._export_graph)
        self._export_context()
        self._dock = QDockWidget("Traces  -  include / exclude cells here", self)
        self._dock.setObjectName("traces")
        self._dock.setWidget(self.traces)
        self._dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        self.addDockWidget(Qt.RightDockWidgetArea, self._dock)
        self.resizeDocks([self._dock], [int(self.width() * 0.33)], Qt.Horizontal)

    def _build_side(self) -> None:
        # V2.9 step bar: where you are; click a step to go there
        self._step_btns: List[QPushButton] = []
        self._step_boxes: List = []
        self._step_now = -1
        bar = QWidget()
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(0, 0, 0, 2)
        bl.setSpacing(4)
        for i, name in enumerate(("Rules", "ROIs", "Track", "Check", "Export")):
            b = QPushButton(f"{i + 1} {name}")
            b.setProperty("step", "todo")
            b.setToolTip(f"Step {i + 1}: go to '{name}' (and open it).")
            b.clicked.connect(lambda _c=False, k=i: self._goto_step(k, user=True))
            bl.addWidget(b, 1)
            self._step_btns.append(b)
        self.side.addWidget(bar)
        self.lbl_next = W.FitLabel("")
        self.lbl_next.setWordWrap(True)
        from . import theme as TH
        t_ = TH.current()
        self.lbl_next.setStyleSheet(f"QLabel {{ background: {t_.select}; color: {t_.text}; "
                                    f"font-weight: 600; padding: 10px 12px; border-radius: 10px; "
                                    f"border-left: 4px solid {t_.accent}; }}")
        self.side.addWidget(self.lbl_next)

        # ---- 1  tracking rules
        box, form = W.group("1   Tracking rules")
        self._step_boxes.append(box)
        intro = W.wrapped_label("How each kind of ROI is found and followed: on its main "
                                "channel, helped by any helper channels (they choose which "
                                "cells AUTO-DETECT picks and help follow them). Every channel "
                                "is measured in every ROI - always.", muted=True)
        intro.setToolTip(self._rules_tip())
        form.addRow(intro)
        self._rows_box = QWidget()
        self._rows_lay = QVBoxLayout(self._rows_box)
        self._rows_lay.setContentsMargins(0, 0, 0, 0)
        self._rows_lay.setSpacing(3)
        form.addRow(self._rows_box)
        self.btn_row = W.button("+  Add rule", lambda: self._add_row(self._next_free(),
                                                                     self._default_a()),
                                "Follow one more kind of ROI (e.g. cytoplasm), with its own "
                                "rule.")
        form.addRow(self.btn_row)
        self.lbl_rows = W.wrapped_label("", muted=True)
        form.addRow(self.lbl_rows)
        self.side.addWidget(box)

        # ---- 2  add ROIs
        box, form = W.group("2   Add ROIs")
        self._step_boxes.append(box)
        self.cmb_comp = QComboBox()
        self.cmb_comp.setToolTip("What Add / Remove / Draw act on. Also chooses which "
                                 "outlines are highlighted and which traces are shown.")
        self.cmb_comp.currentIndexChanged.connect(lambda _i: self._comp_changed())
        form.addRow("Compartment", self.cmb_comp)
        self.lbl_seen = W.wrapped_label("", muted=True)
        self.lbl_seen.setToolTip("The image this compartment's ROIs are drawn on (Add, "
                                 "Auto-detect, Draw by hand, Resize, Add to cell) and followed "
                                 "on while tracking - set by its rule in step 1. Every channel "
                                 "is still measured in every ROI.")
        form.addRow(self.lbl_seen)
        self.lbl_hint = W.wrapped_label("", muted=True)
        form.addRow(self.lbl_hint)
        from PySide6.QtWidgets import QGridLayout
        tools = QWidget()
        tl = QGridLayout(tools)                   # two rows of two: never too wide
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(4)
        self._tool_btn = {}
        for i, (key, (label, _col, _txt)) in enumerate(TOOLS.items()):
            b = QPushButton(label)
            b.setCheckable(True)
            b.setToolTip(TOOL_HELP[key] + "  Click again to turn it off.")
            b.clicked.connect(lambda _c=False, k=key: self._tool_clicked(k))
            self._tool_btn[key] = b
            tl.addWidget(b, i // 2, i % 2)
        form.addRow(tools)
        self.chk_resize_all = QCheckBox("Resize all cells together")
        self.chk_resize_all.setToolTip("Scrolling then redraws every ROI of this compartment "
                                       "at once (each from its own pixels).")
        self.chk_resize_all.toggled.connect(self._resize_all_toggled)
        self.chk_resize_all.hide()
        form.addRow(self.chk_resize_all)
        self.lbl_tool = W.FitLabel("")
        self.lbl_tool.setWordWrap(True)
        form.addRow(self.lbl_tool)
        self.btn_auto = W.button("AUTO-DETECT", self._auto_select,
                                 "Detects the well-defined (high-confidence) ROIs of the chosen "
                                 "compartment on its rule's image in a second or two (clearly "
                                 "above background, normal size and shape, separate). Under an "
                                 "IF rule, cells without signal in the second channel are "
                                 "skipped. Fix the rest by hand; Undo removes them all.",
                                 strong=True)
        self.btn_auto.setMinimumHeight(34)         # V2.9: a primary button of the theme
        form.addRow(self.btn_auto)
        # V3.0: your trained auto-detects (only those that fit this movie's channels)
        self.det_box = QWidget()
        self._det_lay = QVBoxLayout(self.det_box)
        self._det_lay.setContentsMargins(0, 0, 0, 0)
        self._det_lay.setSpacing(3)
        form.addRow(self.det_box)
        self.btn_train = W.button("Train auto-detect from my runs...", self._train_detector,
                                  "Teach AUTO-DETECT which cells you pick: choose saved runs "
                                  "you outlined by hand, watch it learn, answer a short "
                                  "keep / skip quiz, and save it as your own button here.")
        form.addRow(self.btn_train)
        self._detector_used = None                    # the trained auto-detect used (methods)
        self._auto_det = None
        QTimer.singleShot(0, self._fill_detectors)
        # V2.5: after AUTO-DETECT, keep only the N brightest of the cells found
        self.auto_row = QWidget()
        al = QVBoxLayout(self.auto_row)
        al.setContentsMargins(0, 0, 0, 0)
        al.setSpacing(2)
        self.lbl_auto = W.wrapped_label("", muted=False)
        self.sl_auto = QSlider(Qt.Horizontal)
        self.sl_auto.setToolTip("Fewer cells: the dimmest ones found are removed first (mean "
                                "intensity inside each ROI minus the background, on the image "
                                "they were detected on, at this timepoint).")
        self.sl_auto.valueChanged.connect(self._auto_keep)
        al.addWidget(self.lbl_auto)
        al.addWidget(self.sl_auto)
        self.auto_row.hide()
        form.addRow(self.auto_row)
        self.btn_undo = W.button("Undo  (Ctrl+Z)", self._undo, "Take back the last change.")
        self.btn_undo.setEnabled(False)
        form.addRow(self.btn_undo)
        self.btn_load = W.button("Load saved ROIs...", self._load_rois,
                                 "Open an ROI file saved earlier (..._ROIs.npz, or an "
                                 "autosaved ..._session_....npz) - with its tracking when it "
                                 "was saved. File > Earlier analyses of this file... lists the "
                                 "ones found for this .nd2.")
        form.addRow(self.btn_load)
        self.lbl_counts = QLabel("")             # short lines: no wrapping, always fully shown
        form.addRow(self.lbl_counts)
        self.side.addWidget(box)

        # ---- 3  track
        box, form = W.group("3   Track and measure")
        self._step_boxes.append(box)
        self.btn_track = W.button("TRACK && MEASURE", self._track,
                                  "Follows every cell through all timepoints, redrawing every "
                                  "ROI at every timepoint on its rule's image, and measures "
                                  "every channel in every ROI.",
                                  strong=True)
        self.btn_track.setMinimumHeight(34)
        form.addRow(self.btn_track)
        self.sp_tol = W.spin(form, "Size may change by  ± %",
                             int(round(100 * float(getattr(self.settings, "track_size_tol", 0.25)))),
                             0, 100, "Size guard: while tracking, each ROI's area stays within "
                             "this much of the size you drew - a hard limit: it never has more "
                             "or fewer pixels than that. A redraw outside it (e.g. a nucleus "
                             "spilling into its cytoplasm or a neighbour) is re-fitted / trimmed "
                             "to the allowed size. 0 % = redrawn at every timepoint but with "
                             "EXACTLY the number of pixels you drew (the brightest connected "
                             "pixels of the redrawn outline).", 5,
                             lambda v: self._track_setting_changed("track_size_tol", v / 100.0))
        self.sp_move = W.dspin(form, "Max movement between timepoints  µm",
                               float(getattr(self.settings, "max_move_um", 3.0)), 0.5, 50.0,
                               "How far a cell may move from one timepoint to the next: each "
                               "ROI is looked for only within this distance of where it was. "
                               "Raise it for fast-moving cells; lower it if outlines jump to a "
                               "neighbour.", 1, 0.5,
                               lambda v: self._track_setting_changed("max_move_um", v))
        self.sp_gate = W.dspin(form, "Helper signal needed  × noise",
                               float(getattr(self.settings, "gate_snr", 5.0)), 0.5, 100.0,
                               "Helper channels: AUTO-DETECT picks a cell only if every helper "
                               "channel is at least this many times its noise above the ring "
                               "around it (cells you click are kept). Older IF rules: cells "
                               "below it are excluded, with the reason shown.", 1, 0.5,
                               lambda v: self._track_setting_changed("gate_snr", v))
        self.sp_and = W.dspin(form, "AND rule: pixel threshold  × noise",
                              float(getattr(self.settings, "overlap_k", 3.0)), 0.5, 100.0,
                              "AND rule: inside the ROI, only pixels where the second channel "
                              "is above its background by more than this many times its noise "
                              "are measured.", 1, 0.5,
                              lambda v: self._track_setting_changed("overlap_k", v))
        brow = QWidget()
        bl = QHBoxLayout(brow)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(4)
        self.btn_bound = QPushButton("Tracker boundary")
        self.btn_bound.setCheckable(True)
        self.btn_bound.setToolTip("Lines a cell's ROIs may never cross (e.g. between two cells "
                                  "that touch): click the cell, then click the points of a line "
                                  "and double-click to finish it. Draw as many lines as you need; "
                                  "click the button again when done. The lines stay where you "
                                  "drew them in the image, belong to that cell only, are saved "
                                  "with your work and are listed in the methods.")
        self.btn_bound.toggled.connect(self._boundary_toggled)
        bl.addWidget(self.btn_bound, 2)
        self.btn_bound_rm = QPushButton("Remove lines")
        self.btn_bound_rm.setToolTip("Remove the tracker boundary lines of the selected cell "
                                     "(click the cell first).")
        self.btn_bound_rm.clicked.connect(lambda: self._remove_boundary(None))
        bl.addWidget(self.btn_bound_rm, 1)
        form.addRow(brow)
        self._track_form = form
        self._show_rule_settings()
        self.lbl_track = W.wrapped_label("Not tracked yet.", muted=True)
        form.addRow(self.lbl_track)
        self.btn_stop = W.button("Stop", self._cancel, "Stop the job that is running.")
        self.btn_stop.setEnabled(False)
        form.addRow(self.btn_stop)
        self.side.addWidget(box)

        # ---- 4  check
        box, form = W.group("4   Check")
        self._step_boxes.append(box)
        form.addRow(W.wrapped_label(
            "Press  ▶ Play  under the image to watch the outlines follow the cells. Include / "
            "exclude cells in the list beside the traces (tick boxes), or double-click a trace.",
            muted=True))
        # V3.0: ratios / F/F0 only where a channel is clearly above background at baseline
        self.sp_snr = W.dspin(form, "Ratios need baseline ≥  × noise",
                              float(getattr(self.settings, "ratio_min_snr", 5.0)), 0.0, 50.0,
                              decimals=1, step=0.5, tip=
                              "A cell's F/F0, ratio and R/R0 are left out (blank) when a channel "
                              "they use is, at the baseline timepoint, below this many times the "
                              "noise of the ROI's mean (background pixel SD / sqrt(pixels)); a "
                              "ratio's single timepoints are left out where its denominator drops "
                              "that low (a cell fading or leaving). Dividing by almost nothing "
                              "gives wild numbers. 0 = off. Used in the graphs, every export and "
                              "Compare.")
        self.sp_snr.valueChanged.connect(self._snr_changed)
        self.side.addWidget(box)

        # ---- 5  export
        box, form = W.group("5   Export")
        self._step_boxes.append(box)
        self.q_base = W.spin(form, "Baseline (time 0)",
                             self.settings.baseline_timepoint, 1, max(1, self.exp.n_timepoints),
                             "F/F0 = 1 and time = 0 here; earlier timepoints get negative times.")
        self.q_base.valueChanged.connect(self._baseline_changed)
        from PySide6.QtWidgets import QSpinBox
        T = max(1, self.exp.n_timepoints)
        self.sp_dfrom, self.sp_dto = QSpinBox(), QSpinBox()
        for sp, v in ((self.sp_dfrom, self.settings.drift_from), (self.sp_dto, self.settings.drift_to)):
            sp.setRange(1, T)
            sp.setValue(int(min(max(1, v), T)))
            sp.setToolTip("Baseline drift slope: a straight line is fitted through these "
                          "timepoints for every cell (an export-list item).")
            sp.valueChanged.connect(self._drift_changed)
        drow = QWidget()
        dl = QHBoxLayout(drow)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.addWidget(QLabel("T"))
        dl.addWidget(self.sp_dfrom)
        dl.addWidget(QLabel("to  T"))
        dl.addWidget(self.sp_dto)
        dl.addStretch(1)
        form.addRow("Drift slope", drow)
        self.btn_export = W.button("CHOOSE OUTPUTS\n&& EXPORT...", self._choose_outputs,
                                   "Pick what you want on your export list (Excel, Prism, "
                                   "graphs, ROI pictures, ...); only that is written.",
                                   strong=True)
        self.btn_export.setMinimumHeight(34)
        self.btn_export.setEnabled(False)
        form.addRow(self.btn_export)
        self.btn_compare = W.button("Compare / average runs...", self._compare_runs, COMPARE_TIP)
        form.addRow(self.btn_compare)
        out = Path(self.exp.out_dir)
        shown = (out.parent.name + os.sep + out.name                # V3.0: OUTPUT_<movie>/<user>
                 if out.parent.name.upper().startswith("OUTPUT_") else out.name)
        lbl = W.wrapped_label("Each export goes into a new folder inside " +
                              shown.replace("_", "_​") + " (next to the .nd2).",
                              muted=True)
        lbl.setToolTip(str(out))
        form.addRow(lbl)
        self.side.addWidget(box)

        for b in self._step_boxes:
            W.make_foldable(b)
        self._step_boxes[0]._on_open = self._rules_opened
        box, form = W.group("Status")
        self.lbl_status = W.wrapped_label("Ready.")
        form.addRow(self.lbl_status)
        self.lbl_saved = W.wrapped_label(self._saved_text(), muted=True)
        self.lbl_saved.setToolTip(str(history.session_dir(self.exp.out_dir)))
        form.addRow(self.lbl_saved)
        self.side.addWidget(box)

    def _compare_runs(self) -> None:
        """V2.4: the 'Compare runs' window (non-modal), in this window's graph look."""
        from .comparewin import CompareWindow
        e = self.exp
        if getattr(self, "_compare", None) is not None:
            try:
                self._compare.close()
            except RuntimeError:
                pass
        self._compare = CompareWindow(dict(getattr(self.settings, "graph_style", None) or {}),
                                      e.nd2_path, e.out_dir, (e.height, e.width),
                                      e.n_timepoints, self)
        self._compare.show()

    # ----------------------------------------------- V2.7 saved settings, batch
    def _save_analysis_settings(self) -> None:
        """Your analysis conditions now (tracking rules, detection, QC, baseline,
        export list, graph look) as a named settings file."""
        from .. import presets as PR
        self.settings.baseline_timepoint = int(self.q_base.value())
        name, ok = QInputDialog.getText(self, "Save analysis settings",
                                        "Name of these settings (e.g. 'U2OS NLS-met, nucleus "
                                        "on GFP'):")
        if not ok or not name.strip():
            return
        try:
            path = PR.save(PR.folder() / f"{PR.safe_name(name)}.json", name.strip(),
                           analysis=self.settings)
        except OSError as e:
            QMessageBox.warning(self, "Save analysis settings", error_text(e))
            return
        self.set_status(f"Analysis settings saved: {plain_path(path)}")

    def _load_analysis_settings(self) -> None:
        """Use a saved file's analysis conditions from now on (the ROIs and any
        tracking already made are not changed; the rules apply to the next TRACK)."""
        from .. import presets as PR
        path, _f = QFileDialog.getOpenFileName(self, "Load analysis settings",
                                               str(PR.folder()), "PeterPiper settings (*.json)")
        if not path:
            return
        try:
            s = PR.analysis_settings(PR.read(path), self.settings)
        except ValueError as e:
            QMessageBox.warning(self, "Load analysis settings", error_text(e))
            return
        if s is None:
            QMessageBox.information(self, "Load analysis settings",
                                    "This file holds plot settings only (use it in the Compare "
                                    "window).")
            return
        self.settings = s
        self._set_rules(self._start_rules())
        self.q_base.setValue(int(min(max(1, s.baseline_timepoint), self.exp.n_timepoints)))
        if hasattr(self, "traces"):
            self.traces.set_style(dict(s.graph_style or {}))
        save_settings(self.settings, self.exp)
        self.set_status(f"Analysis settings loaded from {Path(path).name}: tracking rules, "
                        f"detection, QC, baseline, export list and graph look. Press "
                        f"AUTO-DETECT / TRACK again to use them on this file.")

    def _saved_files(self) -> None:
        """V2.8: every file PeterPiper saved, newest first (peterpiper.outlog)."""
        from .outlogdlg import OutputsDialog
        OutputsDialog(self).exec()

    def _batch_analyse(self) -> None:
        from .batchdlg import BatchDialog
        BatchDialog(self.settings, self).exec()

    def _about(self) -> None:
        from .. import PROJECT_DOI, PROJECT_URL
        web = (f"<p>Project page: <a href='{PROJECT_URL}'>{PROJECT_URL}</a></p>"
               if PROJECT_URL else "")
        doi = (f"<p>DOI: <a href='https://doi.org/{PROJECT_DOI}'>{PROJECT_DOI}</a></p>"
               if PROJECT_DOI else "")
        QMessageBox.about(
            self, f"About {APP_NAME}",
            f"<h3>{APP_NAME}</h3><p>PeterPiper {__version__} - single-cell fluorescence time "
            f"courses from Nikon .nd2 movies.</p><p>Peter DePaola IV, Schmitt Lab, UCLA "
            f"(ORCID 0000-0003-4264-0375). MIT License.</p>{web}{doi}"
            f"<p>To cite: name this version (PeterPiper {__version__}) and keep the exported "
            f"methods text with your data - the manual (README.html, section 11.5) has the "
            f"reference.</p>")

    def _computer_check(self) -> None:
        from .syscheckdlg import ComputerCheckDialog
        ComputerCheckDialog(self).exec()

    def _set_theme(self, key: str) -> None:
        from . import theme as TH
        TH.switch(key, self.settings)
        for k, a in self._theme_acts.items():
            a.setChecked(k == key)

    def _prism_templates(self) -> None:
        """V2.7: your Prism style templates (open in Prism, take the look over)."""
        from .templatedlg import TemplateDialog

        def take(st: dict) -> None:
            new = GS.coerce(dict(self.settings.graph_style or {}, **st)).to_dict()
            self.traces.set_style(new)
            self._graph_style_changed(new)
        TemplateDialog(take, self).exec()

    def _build_menu(self) -> None:
        m = self.menuBar().addMenu("&File")
        for label, fn in (("Choose another file...", self._go_back), (None, None),
                          ("Earlier analyses of this file...", self._earlier_analyses),
                          ("Load saved ROIs...", self._load_rois),
                          ("Save ROIs now", lambda: self._save_rois(silent=False)),
                          ("Export raw TIFFs...", self._export_tiffs), (None, None),
                          ("Compare / average runs...", self._compare_runs),
                          ("Prism style templates...", self._prism_templates), (None, None),
                          ("Save analysis settings...", self._save_analysis_settings),
                          ("Load analysis settings...", self._load_analysis_settings),
                          ("Batch analyse .nd2 files...", self._batch_analyse),
                          ("Saved files...", self._saved_files), (None, None)):
            if label is None:
                m.addSeparator()
                continue
            a = QAction(label, self)
            a.triggered.connect(fn)
            m.addAction(a)
            if fn == self._compare_runs:
                a.setToolTip(COMPARE_TIP)
            if fn == self._earlier_analyses:
                a.setToolTip("The ROI files and autosaved sessions found for this .nd2 - "
                             "load one (with its tracking) to check or export it again.")
        self.act_autosave = QAction("Save my work automatically", self, checkable=True)
        self.act_autosave.setChecked(bool(getattr(self.settings, "autosave_sessions", True)))
        self.act_autosave.toggled.connect(self._autosave_toggled)
        self.act_ask = QAction("Offer earlier analyses when a file opens", self, checkable=True)
        self.act_ask.setChecked(bool(getattr(self.settings, "ask_previous_runs", True)))
        self.act_ask.toggled.connect(self._ask_toggled)
        m.addAction(self.act_autosave)
        m.addAction(self.act_ask)
        m.addSeparator()
        a = QAction("Close", self)
        a.triggered.connect(self.close)
        m.addAction(a)
        m.setToolTipsVisible(True)
        v = self.menuBar().addMenu("&View")
        from . import theme as TH                  # V2.9: dark / light
        tm = v.addMenu("Theme")
        self._theme_acts = {}
        for key, text in TH.LABELS.items():
            a = QAction(text, self, checkable=True)
            a.setChecked(TH.current().name == key)
            a.triggered.connect(lambda _c=False, k=key: self._set_theme(k))
            tm.addAction(a)
            self._theme_acts[key] = a
        a = QAction("Fold finished steps", self, checkable=True)
        a.setChecked(bool(getattr(self.settings, "ui_fold_steps", True)))
        a.setToolTip("The steps you are not on fold to their title (click the title or the "
                     "step bar to open one).")
        a.toggled.connect(self._fold_toggled)
        v.addAction(a)
        v.addSeparator()
        for label, keys, fn in (
                ("Larger text", ["Ctrl++", "Ctrl+="],
                 lambda: self._set_text_size((self.settings.ui_font_pt or W.base_font_pt()) + 1)),
                ("Smaller text", ["Ctrl+-"],
                 lambda: self._set_text_size((self.settings.ui_font_pt or W.base_font_pt()) - 1)),
                ("Normal text size", ["Ctrl+0"], lambda: self._set_text_size(0.0))):
            a = QAction(label, self)
            a.setShortcuts([QKeySequence(k) for k in keys])
            a.triggered.connect(fn)
            v.addAction(a)
        a = QAction("Undo", self)
        a.setShortcut(QKeySequence.Undo)
        a.triggered.connect(self._undo)
        v.addAction(a)
        a = QAction("Play / pause", self)
        a.setShortcut(QKeySequence(Qt.Key_Space))
        a.triggered.connect(lambda: self.btn_play.toggle())
        v.addAction(a)
        h = self.menuBar().addMenu("&Help")
        a = QAction("How to use this window", self)
        a.triggered.connect(self._help)
        h.addAction(a)
        a = QAction("About PeterPiper", self)                # V3.0: version, licence, how to cite
        a.triggered.connect(self._about)
        h.addAction(a)
        a = QAction("Computer check...", self)          # V2.9: long paths, Python
        a.setToolTip("Is this computer set up the way PeterPiper needs?")
        a.triggered.connect(self._computer_check)
        h.addAction(a)

    # ===================================================== tracking rules
    @staticmethod
    def _rules_tip() -> str:
        return ("Each rule: the main channel an ROI is drawn and followed on, and any "
                "helper channels. Helpers choose which cells AUTO-DETECT picks (they need "
                "the helper's signal) and help follow them: the follow image is the main "
                "channel + half of each helper (each scaled to its own brightness), and the "
                "outline stays within 1 um of the main channel's own outline. Rules from "
                "runs made before V3.0 (ONLY / WITH / AND / IF) load and are applied exactly "
                "as saved.\nWhatever the rule, every channel is measured in every ROI.")

    def _start_rules(self) -> List[TrackRule]:
        """Start-up rules: your last rules (if this file has those channels), else the
        older 'Follow' rows turned into rules, else 'Track nucleus using channel 1 ONLY'."""
        names = list(self.exp.channels)
        out = []
        for d in self.settings.track_rules or []:
            r = TrackRule.from_dict(d, names)
            if r is not None and r.comp in FOLLOW and r.comp not in {q.comp for q in out}:
                out.append(r)
        if not out:
            rows = [r for r in (self.settings.follow_rows or []) if r and r[0] in FOLLOW]
            out = default_rules(rows, [], names) if rows else []
        return out or [TrackRule("nucleus", 0)]

    def _default_a(self) -> int:
        """Channel A for a new rule: the channel on show (else the lead rule's)."""
        it = self._view_items[self.cmb_view.currentIndex()] \
            if 0 <= self.cmb_view.currentIndex() < len(self._view_items) else None
        if it and it[0] == "ch":
            return int(it[1])
        lead = next(iter(self.rules.values()), None)
        return int(lead.a) if lead is not None else 0

    def _next_free(self) -> str:
        used = {r["cmb"].currentData() for r in self._rows}
        return next((c for c in FOLLOW if c not in used), "cytoplasm")

    def _add_row(self, comp: str, a: int = 0, mode: str = "only", b: int = -1,
                 quiet: bool = False, helpers: Sequence[int] = ()) -> None:
        """V3.0: one rule, as
            Auto-detect [Nucleus] using [GFP]          x
                helped by [Cy5]                        x
                + helper channel
        An older rule (WITH / AND / IF, from a run made before V3.0) shows its second
        channel as a helper with a note, and is applied exactly as saved until you
        change the row."""
        from PySide6.QtWidgets import QSizePolicy
        chans = list(self.exp.channels)
        w = QWidget()
        vl = QVBoxLayout(w)
        vl.setContentsMargins(0, 2, 0, 4)
        vl.setSpacing(2)
        l1 = QHBoxLayout()
        l1.setContentsMargins(0, 0, 0, 0)
        l1.setSpacing(4)
        vl.addLayout(l1)
        l1.addWidget(QLabel("Auto-detect"))
        cmb = QComboBox()
        for c in FOLLOW:
            cmb.addItem(LABELS[c], c)
        cmb.setCurrentIndex(max(0, cmb.findData(comp)))
        cmb.setToolTip("The kind of ROI this rule is for.")
        l1.addWidget(cmb, 1)
        rm = self._x_button("Remove this rule (stop following this kind of ROI).")
        l1.addWidget(rm)
        l2 = QHBoxLayout()
        l2.setContentsMargins(16, 0, 0, 0)
        l2.setSpacing(4)
        vl.addLayout(l2)
        l2.addWidget(QLabel("using"))
        cmb_a = QComboBox()
        cmb_a.addItems(chans)
        cmb_a.setCurrentIndex(int(min(max(0, a), len(chans) - 1)))
        cmb_a.setToolTip("The main channel: this kind of ROI is drawn and followed on it.")
        l2.addWidget(cmb_a, 1)
        l2.addSpacing(rm.sizeHint().width() + 4)
        hbox = QWidget()
        hl = QVBoxLayout(hbox)
        hl.setContentsMargins(16, 0, 0, 0)
        hl.setSpacing(2)
        vl.addWidget(hbox)
        lbl_legacy = W.wrapped_label("", muted=True)
        lbl_legacy.hide()
        vl.addWidget(lbl_legacy)
        btn_help = QPushButton("+  helper channel")
        btn_help.setToolTip("Add a helper channel: it decides which cells AUTO-DETECT picks "
                            "(they need its signal) and helps follow them (the follow image "
                            "is the main channel + half of each helper; the outline stays "
                            "within 1 um of the main channel's own outline).")
        hb = QHBoxLayout()
        hb.setContentsMargins(16, 0, 0, 0)
        hb.addWidget(btn_help)
        hb.addStretch(1)
        vl.addLayout(hb)
        for c in (cmb, cmb_a):
            c.setMinimumWidth(60)
            c.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        m = str(mode or "only").lower()
        legacy = {"mode": m, "b": int(b)} if m in ("with", "and", "if") and int(b) >= 0 \
            and int(b) != int(a) else None
        row = dict(widget=w, cmb=cmb, a=cmb_a, helpers=[], hl=hl, legacy=legacy,
                   lbl_legacy=lbl_legacy, btn_help=btn_help, loading=True)
        self._rows.append(row)
        self._rows_lay.addWidget(w)
        for h in ([int(b)] if legacy else list(helpers)):
            self._add_helper(row, int(h), quiet=True)
        row["loading"] = False
        self._style_row(row)
        cmb.currentIndexChanged.connect(lambda _i: self._row_edited(row))
        cmb_a.currentIndexChanged.connect(lambda _i: self._row_edited(row))
        rm.clicked.connect(lambda: self._remove_row(row))
        btn_help.clicked.connect(lambda: self._add_helper(row, -1))
        if not quiet:
            self._rows_changed()

    def _add_helper(self, row: dict, ch: int = -1, quiet: bool = False) -> None:
        """One 'helped by [channel]  x' line under a rule."""
        chans = list(self.exp.channels)
        main = row["a"].currentIndex()
        used = {h["cmb"].currentIndex() for h in row["helpers"]}
        if ch < 0:                                 # the first channel not used yet
            ch = next((i for i in range(len(chans)) if i != main and i not in used), -1)
            if ch < 0:
                self.set_status("Every channel is already used by this rule.")
                return
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(QLabel("helped by"))
        c = QComboBox()
        c.addItems(chans)
        c.setCurrentIndex(int(min(max(0, ch), len(chans) - 1)))
        c.setToolTip("A helper channel (see '+ helper channel').")
        lay.addWidget(c, 1)
        x = self._x_button("Remove this helper channel.")
        lay.addWidget(x)
        h = dict(widget=w, cmb=c)
        row["helpers"].append(h)
        row["hl"].addWidget(w)
        c.currentIndexChanged.connect(lambda _i: self._row_edited(row))
        x.clicked.connect(lambda: self._remove_helper(row, h))
        if not quiet and not row.get("loading"):
            self._row_edited(row)

    @staticmethod
    def _x_button(tip: str) -> QPushButton:
        """A small remove button whose x always shows (the theme's padding is wide)."""
        b = QPushButton("×")
        b.setToolTip(tip)
        b.setFixedWidth(30)
        b.setStyleSheet("QPushButton { padding: 0px; }")
        return b

    def _remove_helper(self, row: dict, h: dict) -> None:
        row["helpers"].remove(h)
        h["widget"].setParent(None)
        h["widget"].deleteLater()
        self._row_edited(row)

    def _row_edited(self, row: dict) -> None:
        """You changed a row: an older rule becomes a V3.0 rule (main + helpers)."""
        if row.get("loading"):
            return
        row["legacy"] = None
        self._rows_changed()

    def _style_row(self, row: dict) -> None:
        names = list(self.exp.channels)
        lg = row.get("legacy")
        if lg:
            from ..rules import LEGACY_WORDS
            bn = names[lg["b"]] if 0 <= lg["b"] < len(names) else "?"
            row["lbl_legacy"].setText(
                f"From a run made before V3.0: {LEGACY_WORDS[lg['mode']].format(b=bn)} - "
                f"applied exactly as saved. Change this rule to use helper channels instead "
                f"(then track again).")
        row["lbl_legacy"].setVisible(bool(lg))
        row["widget"].setToolTip(
            "Main channel: drawn and followed on it. Helper channels: AUTO-DETECT picks only "
            "cells with their signal, and they help follow the cell (half weight; the outline "
            "stays within 1 um of the main channel's own outline).")

    def _row_rule(self, row: dict) -> TrackRule:
        c = row["cmb"].currentData()
        a = row["a"].currentIndex()
        lg = row.get("legacy")
        if lg:
            return TrackRule(c, int(a), lg["mode"], int(lg["b"]))
        hs = tuple(h["cmb"].currentIndex() for h in row["helpers"])
        r = TrackRule(c, int(a), HELP, -1, hs)
        return r if r.helper_list() else TrackRule(c, int(a))

    def _remove_row(self, row: dict) -> None:
        if len(self._rows) <= 1:
            self.set_status("Keep at least one rule - change it instead.")
            return
        self._rows.remove(row)
        row["widget"].setParent(None)
        row["widget"].deleteLater()
        self._rows_changed()

    def _set_rules(self, rules: List[TrackRule], quiet: bool = False) -> None:
        """Replace every rule row (start-up, loading a file)."""
        self._quiet_rules = quiet
        try:
            for r in list(self._rows):
                r["widget"].setParent(None)
                r["widget"].deleteLater()
            self._rows = []
            for r in rules:
                self._add_row(r.comp, int(r.a), r.mode, int(r.b), quiet=True,
                              helpers=r.helper_list() if r.effective_mode() == HELP else ())
            self._rows_changed()
        finally:
            self._quiet_rules = False

    def _rules_key(self) -> tuple:
        return tuple((c, int(r.a), r.effective_mode(), int(r.b) if r.effective_mode() in
                      ("with", "and", "if") else -1, tuple(r.helper_list()))
                     for c, r in self.rules.items())

    def _rows_changed(self) -> None:
        old = self._rules_key()
        rules: Dict[str, TrackRule] = {}
        dup, same = [], []
        for r in self._rows:
            self._style_row(r)
            c = r["cmb"].currentData()
            if c in rules:
                dup.append(LABELS[c])
                continue
            rr = self._row_rule(r)
            if any(h["cmb"].currentIndex() == r["a"].currentIndex() for h in r["helpers"]):
                same.append(LABELS[c])
            rules[c] = rr
        self.rules = rules
        names = list(self.exp.channels)
        all_ch = list(range(self.exp.n_channels))
        self.follow = {c: list(all_ch) for c in rules}       # every channel, always
        self.settings.track_rules = [r.to_dict(names) for r in rules.values()]
        # kept so an older PeterPiper can still open these settings
        self.settings.follow_rows = [[c, list(names)] for c in rules]
        self._and_view.clear()
        self._guides.clear()
        notes = []
        if dup:
            notes.append(f"{', '.join(dup)} is listed twice - only the first rule counts.")
        if same:
            notes.append(f"{', '.join(same)}: a helper is the same as the main channel - it "
                         f"does not count.")
        lead = next(iter(rules), None)
        if lead:
            notes.append(f"Cells move with their {LABELS[lead].lower()} (the first rule).")
        for c, rule in rules.items():                       # ROIs drawn on another image
            live = self._live(c)
            chs = {int(getattr(self.cells[k][c], "channel", rule.a)) for k in live}
            if live and chs != {int(rule.a)}:
                drawn = "/".join(names[i] for i in sorted(chs) if 0 <= i < len(names))
                notes.append(f"Your {LABELS[c].lower()} ROIs were drawn on {drawn}; they will "
                             f"be followed on {self._guide_name(c)}.")
        self.lbl_rows.setText("  ".join(notes))
        keep = self.comp
        self.cmb_comp.blockSignals(True)
        self.cmb_comp.clear()
        for c in rules:
            self.cmb_comp.addItem(LABELS[c], c)
        self.cmb_comp.addItem(LABELS["background"], "background")
        i = self.cmb_comp.findData(keep)
        self.cmb_comp.setCurrentIndex(i if i >= 0 else 0)
        self.cmb_comp.blockSignals(False)
        self.btn_row.setEnabled(len(rules) < len(FOLLOW))
        self._fill_view_items()
        self._show_rule_settings()
        changed = old != self._rules_key()
        if changed and not self._quiet_rules:
            self._mark_dirty()
        if changed and not self._quiet_rules and self.track is not None:
            self._structure_changed("The tracking rules changed - press TRACK & MEASURE "
                                    "again.")
            self.set_status("The tracking rules changed - press TRACK & MEASURE again.")
        self._comp_changed(switch_view=changed or self._quiet_rules)

    # spin box -> Settings attribute (the tracking settings shown in step 3)
    _TRACK_SPINS = (("sp_tol", "track_size_tol", 100.0), ("sp_move", "max_move_um", 1.0),
                    ("sp_gate", "gate_snr", 1.0), ("sp_and", "overlap_k", 1.0))

    def _show_rule_settings(self) -> None:
        """The IF / AND settings are shown only while a rule uses that mode."""
        form = getattr(self, "_track_form", None)
        if form is None:
            return
        modes = {r.effective_mode() for r in self.rules.values()}
        form.setRowVisible(self.sp_gate, bool(modes & {"if", HELP}))
        form.setRowVisible(self.sp_and, "and" in modes)

    def _track_setting_changed(self, attr: str, value: float) -> None:
        """A tracking setting changed: saved; earlier tracking no longer matches it."""
        if abs(float(getattr(self.settings, attr, 0.0)) - float(value)) < 1e-9:
            return
        setattr(self.settings, attr, float(value))
        if self._restoring_settings:
            return
        try:
            save_settings(self.settings, self.exp)
        except Exception:                                          # noqa: BLE001
            pass
        self._mark_dirty()
        if self.track is not None:
            msg = "A tracking setting changed - press TRACK & MEASURE again."
            self._structure_changed(msg)
            self.set_status(msg)

    def _track_settings(self) -> dict:
        s = self.settings
        return dict(track_size_tol=float(getattr(s, "track_size_tol", 0.25)),
                    max_move_um=float(getattr(s, "max_move_um", 3.0)),
                    gate_snr=float(getattr(s, "gate_snr", 5.0)),
                    overlap_k=float(getattr(s, "overlap_k", 3.0)))

    def _set_track_settings(self, vals: dict) -> None:
        """Put saved tracking settings into the spin boxes (loading a file: the
        loaded tracking stays valid)."""
        self._restoring_settings = True
        try:
            for name, attr, scale in self._TRACK_SPINS:
                v = vals.get(attr)
                if isinstance(v, (int, float)) and not isinstance(v, bool) and \
                        (v > 0 or (v == 0 and name == "sp_tol")):
                    w = getattr(self, name)
                    w.setValue(int(round(v * scale)) if name == "sp_tol" else float(v))
                    setattr(self.settings, attr, float(v))
        finally:
            self._restoring_settings = False

    def _rule(self, comp: str) -> TrackRule:
        """The rule of a compartment (a compartment without one: ONLY on channel 1)."""
        r = self.rules.get(comp)
        return r if r is not None else TrackRule(comp, 0)

    def _guide_name(self, comp: str, long: bool = True) -> str:
        """'Cy5' / 'mRuby + GFP (combined)' / 'GFP (only pixels also bright in ExRai)' /
        'mRuby (cells need GFP signal)' - what the ROIs are drawn and followed on."""
        r = self._rule(comp)
        names = list(self.exp.channels)
        C = len(names)
        a = names[min(max(0, int(r.a)), C - 1)]
        m = r.effective_mode()
        b = names[int(r.b)] if 0 <= int(r.b) < C else ""
        if m == HELP:
            hs = " + ".join(names[h] for h in r.helper_list() if h < C)
            return (f"{a} helped by {hs} (followed on {a} + half of {hs}; cells need "
                    f"{hs} signal)" if long else f"{a} + {hs}")
        if m == "with":
            return (f"{a} + {b} (combined; followed on {a} only)" if long
                    else f"{a} + {b}")
        if not long or m == "only":
            return a
        if m == "and":
            return f"{a} (only pixels also bright in {b})"
        return f"{a} (cells need {b} signal)"

    def _norm_now(self):
        """rules.GuideNorm of the frame the ROIs are drawn on (t0, or the frame on show
        before the first ROI) - frozen there, exactly as the tracker computes it."""
        t = int(self.t0 if self.t0 is not None else self.cur_t)
        if self._norm is None or self._norm[0] != t:
            self._norm = (t, make_norm(self._load_frame(t)))
        return self._norm[1]

    def _guide(self, comp: str, t: Optional[int] = None) -> np.ndarray:
        """The image compartment `comp` is drawn on at timepoint t: rules.guide_plane
        (channel A's raw plane for ONLY / AND / IF; A and B combined for WITH)."""
        t = self.cur_t if t is None else int(t)
        rule = self._rule(comp)
        stack = self._load_frame(t)
        if rule.effective_mode() not in ("with", HELP):
            return guide_plane(stack, rule, None)
        norm = self._norm_now()
        key = (t, guide_key(rule, stack.shape[0]), self._norm[0])
        g = self._guides.get(key)
        if g is None:
            if len(self._guides) > 4:              # a few frames: enough for the wheel
                self._guides.clear()
            g = self._guides[key] = guide_plane(stack, rule, norm)
        return g

    def _gate(self, comp: str, roi: Roi, t: Optional[int] = None) -> Optional[float]:
        """IF rule: the ROI's signal-to-noise in channel B; V3.0 helpers: the lowest
        signal-to-noise of its helper channels (None for other rules)."""
        rule = self._rule(comp)
        if rule.effective_mode() == HELP:
            from ..rules import helper_snr
            t = self.cur_t if t is None else int(t)
            v = helper_snr(self._load_frame(t), roi, rule, self.exp.um_per_px, self._norm_now())
            return float(min(v.values())) if v else None
        if rule.effective_mode() != "if":
            return None
        t = self.cur_t if t is None else int(t)
        return float(gate_snr(self._load_frame(t), roi, rule, self.exp.um_per_px,
                              self._norm_now()))

    def _gate_note(self, k: int, comp: str) -> str:
        """The IF warning for a cell just drawn ('' when it passes or no IF rule)."""
        roi = self.cells[k].get(comp)
        snr = self._gate(comp, roi) if roi is not None else None
        if snr is None:
            return ""
        need = float(getattr(self.settings, "gate_snr", 5.0))
        if np.isfinite(snr) and snr >= need:
            return ""
        shown = f"SNR {snr:.1f}" if np.isfinite(snr) else "not measurable"
        if self._rule(comp).effective_mode() == HELP:
            hs = self._helper_names(comp)
            return (f"Cell {k + 1} has little {hs} signal ({shown}; AUTO-DETECT needs {need:g}) "
                    f"- kept, because you picked it.")
        b = self.exp.channels[int(self._rule(comp).b)]
        return (f"Cell {k + 1} has no {b} signal ({shown}, needs {need:g}) - the IF rule "
                f"will exclude it; include it by hand if you want it.")

    def _helper_names(self, comp: str) -> str:
        names = list(self.exp.channels)
        return " / ".join(names[h] for h in self._rule(comp).helper_list() if h < len(names))

    def _and_seed(self, k: int, comp: str, seed: Roi) -> Roi:
        """AND rule, on the drawn timepoint: a copy of the drawn ROI keeping only the
        pixels also bright in channel B (what will be measured) - for display only;
        the cell list keeps the whole ROI (it is what the tracker follows)."""
        hit = self._and_view.get((comp, k))
        if hit is not None and hit[0] is seed:
            return hit[1]
        try:
            kept = apply_and(seed, self._load_frame(int(self.t0)), self._rule(comp),
                             self._norm_now(), self.exp.um_per_px,
                             float(getattr(self.settings, "overlap_k", 3.0)))
        except Exception:                                          # noqa: BLE001
            kept = seed
        self._and_view[(comp, k)] = (seed, kept)
        return kept

    # ============================================================ helpers
    @staticmethod
    def _breakable(text: str) -> str:
        """Long paths / file names may wrap after \\ / and _ (else they widen the panel)."""
        zw = "​"
        return text.replace("\\", "\\" + zw).replace("/", "/" + zw).replace("_", "_" + zw)

    def set_status(self, text: str) -> None:
        self.lbl_status.setText(self._breakable(text))

    def _busy_now(self) -> bool:
        return self._runner is not None and self._runner.is_running()

    def _set_text_size(self, pt: float) -> None:
        self.settings.ui_font_pt = 0.0 if not pt else float(min(max(pt, 7.0), 28.0))
        self._scaler._last = 0.0
        self._scaler.apply()
        save_settings(self.settings, self.exp)

    def _load_frame(self, t: int) -> np.ndarray:
        return self.store.get_now(int(t))

    def _show_frame(self, autorange: bool = False) -> None:
        stack = self._load_frame(self.cur_t) if autorange else self.store.get(self.cur_t)
        if stack is None:                         # being read - shown when it arrives
            self._waiting = self.cur_t
            self._update_time_label(loading=True)
            return
        self._waiting = None
        i = self.cmb_view.currentIndex()
        it = self._view_items[i] if 0 <= i < len(self._view_items) else ("ch", 0)
        last = stack.shape[0] - 1
        pv = self.store.get_preview(self.cur_t)            # V2.9: display copy
        pf = self.store.preview_f if pv is not None else 1
        if it[0] == "ch":
            self.view.show_planes([stack[min(it[1], last)]], key=it, autorange=autorange,
                                  preview=None if pv is None else [pv[min(it[1], last)]],
                                  preview_f=pf)
        elif it[0] == "overlay":
            self.view.show_planes([stack[min(it[1], last)], stack[min(it[2], last)]], key=it,
                                  autorange=autorange,
                                  preview=None if pv is None else [pv[min(it[1], last)],
                                                                   pv[min(it[2], last)]],
                                  preview_f=pf)
        else:                                     # a WITH rule's tracking image
            self.view.show_planes([self._guide(it[1])], key=("guide",) + self._rules_key(),
                                  autorange=autorange)
        self._update_time_label()

    def _fill_view_items(self) -> None:
        """The Show list: every channel, every overlay pair, and the tracking image of
        each WITH rule (what the tracker sees). Keeps the current choice if it is
        still there."""
        names = list(self.exp.channels)
        items = [("ch", i) for i in range(len(names))]
        items += [("overlay", a, b) for a, b in self._overlay_pairs]
        items += [("guide", c) for c, r in self.rules.items()
                  if r.effective_mode() in ("with", HELP)]
        i = self.cmb_view.currentIndex()
        cur = self._view_items[i] if 0 <= i < len(self._view_items) else None
        labels = []
        for it in items:
            if it[0] == "ch":
                labels.append(names[it[1]])
            elif it[0] == "overlay":
                labels.append(f"Overlay: {names[it[1]]} + {names[it[2]]}")
            else:
                labels.append(f"Tracking image: {self._guide_name(it[1], long=False)}"
                              + (f" ({LABELS[it[1]].lower()})" if len(
                                  [x for x in items if x[0] == "guide"]) > 1 else ""))
        self._view_items = items
        self.cmb_view.blockSignals(True)
        self.cmb_view.clear()
        self.cmb_view.addItems(labels)
        for j, it in enumerate(items):
            if it[0] == "guide":
                self.cmb_view.setItemData(
                    j, "The image this compartment is drawn and followed on: the channels "
                       "scaled to their own brightness and added (helper channels; an older "
                       "WITH rule adds two equally).", Qt.ToolTipRole)
        j = items.index(cur) if cur in items else 0
        self.cmb_view.setCurrentIndex(j)
        self.cmb_view.blockSignals(False)
        if cur is not None and cur not in items:
            self._show_frame()

    def _show_item(self, it: tuple) -> None:
        if it in self._view_items and self.cmb_view.currentIndex() != self._view_items.index(it):
            self.cmb_view.setCurrentIndex(self._view_items.index(it))

    def _frame_ready(self, t: int) -> None:
        if self._waiting is not None and t == self.cur_t:
            self._show_frame()

    def _update_time_label(self, loading: bool = False) -> None:
        b = int(min(max(1, self.q_base.value()), self.exp.n_timepoints)) - 1
        self.lbl_t.setText(f"{self.cur_t + 1} / {self.exp.n_timepoints}  "
                           f"({self.exp.time_label(self.cur_t, b)})" +
                           ("  loading..." if loading else ""))

    def _on_slider(self, v: int) -> None:
        self._end_live()
        self.cur_t = int(v) - 1
        self._show_frame()
        self._refresh()
        # V2.9: while playing, the graph's time line moves ~6 times a second (moving it
        # redraws every trace - the image itself stays at the full frame rate)
        now = time.monotonic()
        if not self._play.isActive() or now - getattr(self, "_t_line_at", 0.0) >= 0.16:
            self._t_line_at = now
            self.traces.set_time(self.cur_t)
        self.store.prefetch(self.cur_t, ahead=10 if self._play.isActive() else 3, behind=2)

    def _step(self, d: int) -> None:
        self.slider.setValue(int(np.clip(self.cur_t + 1 + d, 1, self.exp.n_timepoints)))

    def _drift_changed(self, _v: int) -> None:
        a, z = self.sp_dfrom.value(), self.sp_dto.value()
        self.settings.drift_from, self.settings.drift_to = int(min(a, z)), int(max(a, z))
        self._mark_dirty()

    def _snr_changed(self, v: float) -> None:
        from .. import measure
        self.settings.ratio_min_snr = float(v)
        measure.set_min_snr(v)
        save_settings(self.settings)
        self._mark_dirty()
        if self.track is not None:
            self._sync_traces(full=True)

    def _baseline_changed(self, v: int) -> None:
        self.settings.baseline_timepoint = int(v)
        self._mark_dirty()
        self._update_time_label()
        if self.track is not None:
            self.traces.set_baseline(int(v) - 1)

    # =============================================================== play
    def _play_toggled(self, on: bool) -> None:
        if on:
            self.btn_play.setText("⏸  Pause")
            from . import theme as TH                  # V2.9: the theme's warning colour
            col = TH.current().warn if TH._current is not None else "#d98a1f"
            self.btn_play.setStyleSheet(f"QPushButton {{ background: {col}; color: #101010; "
                                        f"font-weight: 600; border-color: {col}; }}")
            self.store.prefetch(self.cur_t, ahead=12, behind=0)
            self._play.start(int(1000 / max(1, self.cmb_fps.currentData() or 8)))
        else:
            self._play.stop()
            self.btn_play.setText("▶  Play")
            self.btn_play.setStyleSheet("")
            self.traces.set_time(self.cur_t)

    def _fps_changed(self, _i: int) -> None:
        self.settings.play_fps = float(self.cmb_fps.currentData() or 8)
        if self._play.isActive():
            self._play.start(int(1000 / max(1, self.settings.play_fps)))

    def _play_tick(self) -> None:
        nt = self.cur_t + 1
        if nt >= self.exp.n_timepoints:
            nt = 0                                     # loop
        if self.store.get(nt) is None:                 # not read yet: wait for it
            self.store.prefetch(nt - 1, ahead=12, behind=0)
            return
        self.slider.setValue(nt + 1)

    def _stop_play(self) -> None:
        if self.btn_play.isChecked():
            self.btn_play.setChecked(False)

    # ======================================================= compartments
    def _comp_changed(self, switch_view: bool = True) -> None:
        if hasattr(self, "_live_roi"):
            self._end_live()
        self.comp = self.cmb_comp.currentData() or "nucleus"
        if self.comp != "background":
            self.view_comp = self.comp
            if switch_view:                       # show what this compartment is drawn on
                rule = self._rule(self.comp)
                self._show_item(("guide", self.comp) if rule.effective_mode() in ("with", HELP)
                                else ("ch", int(rule.a)))
        if self.comp == "background" and self.tool in ("remove", "resize", "split", "extend"):
            self._set_tool(None)
        else:
            self._set_tool(self.tool)                 # relabel the active tool
        self._update_hint()
        self._refresh()
        self._sync_traces(full=True)

    def _view_changed(self, _i: int) -> None:
        self._show_frame()

    def _update_hint(self) -> None:
        if self.comp == "background":
            self.lbl_seen.setText("")
            self.lbl_seen.setVisible(False)
            ch = "the image"
        else:
            ch = self._guide_name(self.comp, long=False)
            self.lbl_seen.setText(f"Drawn and followed on: {self._guide_name(self.comp)}")
            self.lbl_seen.setVisible(True)
        self.lbl_hint.setText(HINTS[self.comp].format(ch=ch))
        if self.tool:                             # keep the active tool's line current
            self.lbl_tool.setText(ACTIVE[self.tool].format(c=LABELS[self.comp].lower(), ch=ch))
        if hasattr(self, "btn_auto"):
            bg = self.comp == "background"
            self.btn_auto.setEnabled(not bg and not self._busy_now())
            self.btn_auto.setText("AUTO-DETECT" if bg else
                                  f"AUTO-DETECT\n{LABELS[self.comp]} on {ch}")

    def _pick_background(self) -> None:
        """V3.0: Compartment 'Background' with Add on - the next click places it."""
        i = self.cmb_comp.findData("background")
        if i >= 0:
            self.cmb_comp.setCurrentIndex(i)
        self._set_tool("add")
        self._goto_step(1)

    def _redraw_background(self) -> None:
        """'Redraw background' in the not-steady note: go to the drawn timepoint
        with Background > Draw by hand on (TRACK & MEASURE again afterwards)."""
        i = self.cmb_comp.findData("background")
        if i >= 0:
            self.cmb_comp.setCurrentIndex(i)
        self._set_tool("draw")
        self.set_status("Draw the new background region (hold the button and draw around it), "
                        "then press TRACK & MEASURE again.")

    # ============================================================== tools
    def _tool_clicked(self, key: str) -> None:
        self._set_tool(None if self.tool == key else key)

    def _set_tool(self, key: Optional[str]) -> None:
        self._end_live()
        if key in ("remove", "resize", "split", "extend") and self.comp == "background":
            self.set_status("For the background: Add (click to put a square there) or Draw by "
                            "hand (draw around the region).")
            key = None
        if key is not None and getattr(self, "_bound_on", False):
            self.btn_bound.setChecked(False)          # one tool at a time
        if key in ("draw", "resize", "split", "extend") and self.t0 is not None \
                and self.cur_t != self.t0:
            self._stop_play()
            self.slider.setValue(self.t0 + 1)
        self.tool = key
        comp = LABELS[self.comp].upper()
        for k, b in self._tool_btn.items():
            label, col, active = TOOLS[k]
            on = k == key
            b.setChecked(on)
            b.setText(active if on else label)
            b.setStyleSheet(f"QPushButton {{ background: {col}; color: white; font-weight: 800; "
                            f"padding: 7px; border-radius: 4px; }}" if on else "")
        self._link_from = None
        self._extend_k = None
        if key == "draw" and self.comp == "background":
            self.view.start_lasso()                   # V2.5: a freehand background outline
        elif key == "draw":
            self.view.start_polygon()
        elif key == "split":
            self.view.start_freehand()
        elif self.view.mode != "view":
            self.view.cancel_draw()
        if hasattr(self, "chk_resize_all"):
            self.chk_resize_all.setVisible(key == "resize")
            if key == "resize" and self.chk_resize_all.isChecked():
                self._resize_all_toggled(True)
        if key:
            ch = self._guide_name(self.comp, long=False) if self.comp != "background" \
                else "the image"
            self.lbl_tool.setText(ACTIVE[key].format(c=LABELS[self.comp].lower(), ch=ch)
                                  if not (key == "draw" and self.comp == "background") else
                                  "DRAWING the background: hold the left button and draw around "
                                  "the region; release to finish. Click again (or Esc) to stop.")
            self.lbl_tool.setStyleSheet(f"color: {TOOLS[key][1]}; font-weight: 700;")
        else:
            self.lbl_tool.setText(TOOL_HELP[None])
            self.lbl_tool.setStyleSheet("")
            self.lbl_tool.setProperty("muted", True)
            self.lbl_tool.style().unpolish(self.lbl_tool)
            self.lbl_tool.style().polish(self.lbl_tool)

    def _resize_all_toggled(self, on: bool) -> None:
        if self.tool != "resize":
            return
        self._end_live()
        live = self._live(self.comp) if self.comp != "background" else []
        if on and live:
            self._push_undo()
            self._start_live(live, self.comp)
        elif not on:
            self.set_status("Resize one cell: click it, then scroll.")

    def _on_escape(self) -> None:
        if getattr(self, "_bound_on", False):
            self.btn_bound.setChecked(False)
            self.set_status("Tracker boundary: done.")
            return
        if getattr(self, "_live_roi", None) is not None:
            self._end_live()
            self.set_status("Done - that ROI keeps its size.")
            return
        if self._link_from is not None:
            self._link_from = None
            self.set_status("Move cancelled.")
            self._refresh()
        elif self.tool is not None:
            self._set_tool(None)
            self.set_status("Tool off.")

    # ========================================================= ROI lists
    def _rois(self, comp: str, t: Optional[int] = None) -> List[Optional[Roi]]:
        t = self.cur_t if t is None else t
        tracked = self.track["rois"].get(comp) if self.track is not None else None
        out = []
        for k, cell in enumerate(self.cells):
            if comp not in cell:
                out.append(None)
            elif tracked is not None and k < len(tracked[t]) and tracked[t][k] is not None \
                    and (tracked[t][k].area or _has_outline(tracked[t][k])):
                # an AND frame whose kept pixels are empty still shows where the
                # cell was followed (its outline), not the ROI as drawn
                out.append(tracked[t][k])
            else:
                out.append(cell[comp])
        return out

    def _roi_at(self, comp: str, x: float, y: float) -> Optional[int]:
        xi, yi = int(round(x)), int(round(y))
        best, best_a = None, None
        for k, r in enumerate(self._rois(comp)):
            if r is None:
                continue
            y0, x0, y1, x1 = r.bbox
            if not (y0 <= yi < y1 and x0 <= xi < x1):
                continue
            hit = r.outline if getattr(r, "outline", None) is not None else r.mask
            if hit[yi - y0, xi - x0] and (best_a is None or r.area < best_a):
                best, best_a = k, r.area
        return best

    def _cell_at(self, x: float, y: float, first: Optional[str] = None) -> Optional[int]:
        for c in ([first] if first else []) + list(COMPS):
            k = self._roi_at(c, x, y)
            if k is not None:
                return k
        return None

    def _live(self, comp: str) -> List[int]:
        return [k for k, cell in enumerate(self.cells) if comp in cell]

    # ============================================================ display
    def _refresh(self) -> None:
        comp = self.view_comp
        shown, colours = [], {}
        is_and = self._rule(comp).effective_mode() in ("and", "with")
        for k, r in enumerate(self._rois(comp)):
            if r is None:
                shown.append(_blank())
                continue
            if is_and:                       # AND: the kept (measured) pixels are shown too
                if r is self.cells[k].get(comp) and self.t0 is not None:
                    r = self._and_seed(k, comp, r)
                r.__dict__["show_kept"] = True
            r.include = k not in self.excl[comp]
            if r.include:
                colours[k] = cell_colour(k)
            shown.append(r)
        sel = self._link_from[0] if self._link_from is not None else self.selected
        self.view.set_rois(shown, self.background, sel, colours)
        # V2.5: tracker boundary lines (the selected cell's highlighted) and the
        # background pixels left out at this timepoint (none since V2.5: kept for old sessions)
        self.view.set_walls([ln for k in sorted(self.boundaries) for ln in self.boundaries[k]],
                            self.boundaries.get(sel, []) if isinstance(sel, int) else [])
        bgx = (self.track or {}).get("bg_excluded") or {}
        m = bgx.get(self.cur_t) if self.background is not None else None
        if m is not None and m.shape == self.background.mask.shape:
            ys, xs = np.nonzero(m)
            self.view.set_excluded_pixels(ys + self.background.bbox[0], xs + self.background.bbox[1])
        else:
            self.view.set_excluded_pixels(np.zeros(0), np.zeros(0))
        self.view.set_context([r for c in COMPS if c != comp for r in self._rois(c)
                               if r is not None])
        self._update_counts()
        self._update_next()

    def _update_counts(self) -> None:
        n_cells = sum(1 for c in self.cells if c)
        parts = []
        for c in COMPS:
            live = self._live(c)
            if not live:
                continue
            chs = sorted({self.exp.channels[int(getattr(self.cells[k][c], "channel", 0))]
                          for k in live})
            n_out = len(self.excl[c] & set(live))
            note = "" if c in self.follow else "<br>   (NOT followed - add a rule in step 1)"
            parts.append(f"{LABELS[c]}: {len(live)} (drawn on {'/'.join(chs)})"
                         + (f", {n_out} excluded" if n_out else "") + note)
        bg = ("automatic" if self._bg_auto else "drawn by you" if self._bg_kind == "hand"
              else "placed by you") if self.background is not None else "none yet"
        txt = f"<b>Cells: {n_cells}</b>"
        if parts:
            txt += "<br>" + "<br>".join(parts)
        txt += f"<br>Background region: {bg}"
        if self.t0 is not None:
            txt += f"<br>ROIs are drawn on timepoint {self.t0 + 1}"
        nb = [k for k in sorted(self.boundaries) if self.boundaries[k]]
        if nb:
            txt += ("<br>Tracker boundary lines: cell " + ", ".join(str(k + 1) for k in nb))
        self.lbl_counts.setText(txt)

    def _update_next(self) -> None:
        if self._busy_now():
            return
        n = sum(1 for c in self.cells if c)
        bg_todo = (" Also pick a BACKGROUND spot: right-click an empty area > 'Put the "
                   "background region here'." if self.background is None else "")
        if n == 0:
            msg = ("Step 1: check the tracking rules (what each kind of ROI is found and "
                   "followed on). Step 2: pick the Compartment, turn on ADD and click each "
                   "one on the image." + bg_todo)
        elif self.track is None and self._was_tracked:
            what = "the tracking rules or settings" if self._stale_rules else "the ROIs"
            msg = (f"You changed {what} - press TRACK & MEASURE again (about "
                   f"{self._eta_s(n)} s).")
        elif self.track is None:
            msg = (f"{n} cell(s) outlined. Keep adding (switch Compartment for the others). "
                   f"When done: TRACK & MEASURE (about {self._eta_s(n)} s)." + bg_todo)
        elif self._exported:
            msg = f"Exported to {Path(self._exported).name}. You can keep editing and export again."
        else:
            msg = ("Step 4: press ▶ Play to check the outlines follow the cells; include / "
                   "exclude cells in the list by the traces. Then CHOOSE OUTPUTS & EXPORT.")
        self.lbl_next.setText(self._breakable(msg))
        self._set_step((1 if self._rules_seen else 0) if n == 0 else
                       2 if self.track is None else 4 if self._exported else 3)

    def _rules_opened(self) -> None:
        """V3.0: the tracking rules were looked at - step 1 counts as done."""
        if not self._rules_seen:
            self._rules_seen = True
            QTimer.singleShot(0, self._update_next)

    def _rules_note(self) -> None:
        """V3.0: the active rules, shown after the folded step 1's title."""
        if getattr(self, "_step_boxes", None):
            ch = list(self.exp.channels)
            W.set_fold_note(self._step_boxes[0],
                            "; ".join(self._rule_short(r) for r in self.rules.values()),
                            "; ".join(r.display_text(ch) for r in self.rules.values()))

    def _rule_short(self, r: TrackRule) -> str:
        """'nucleus: GFP + Cy5' - a rule in a few words (the folded step 1 title)."""
        ch = list(self.exp.channels)
        nm = lambda i: ch[i] if 0 <= i < len(ch) else "?"          # noqa: E731
        m = r.effective_mode()
        what = LABELS.get(r.comp, r.comp).lower()
        if m == HELP:
            return f"{what}: {nm(int(r.a))} + " + " + ".join(nm(h) for h in r.helper_list())
        if m == "only":
            return f"{what}: {nm(int(r.a))}"
        return f"{what}: {nm(int(r.a))} {MODE_LABELS[m]} {nm(int(r.b))}"

    # V2.9 step bar + focus
    def _set_step(self, k: int) -> None:
        """The step you are on: lit in the bar; on a change of step it is opened (and,
        with View > Fold finished steps, the ones before it are folded)."""
        if not getattr(self, "_step_btns", None):
            return
        changed = k != self._step_now
        self._step_now = k
        for i, b in enumerate(self._step_btns):
            st = "current" if i == k else "done" if i < k else "todo"
            if b.property("step") != st:
                b.setProperty("step", st)
                b.style().unpolish(b)
                b.style().polish(b)
        for i, box in enumerate(self._step_boxes):
            act = i == k or (k >= 3 and i >= 3)          # check + export go together
            if box.property("active") != act:
                box.setProperty("active", act)
                box.style().unpolish(box)
                box.style().polish(box)
        if changed and getattr(self.settings, "ui_fold_steps", True):
            # rules stay open until there are cells; check and export are one stage
            for i, box in enumerate(self._step_boxes):
                W.set_folded(box, not (i == k or (k >= 3 and i >= 3) or (k <= 1 and i <= 1)
                                       or (k == 2 and i == 1)))
        self._rules_note()

    def _goto_step(self, k: int, user: bool = False) -> None:
        if not (0 <= k < len(self._step_boxes)):
            return
        if k == 0 and user:
            self._rules_opened()
        box = self._step_boxes[k]
        W.set_folded(box, False)
        QTimer.singleShot(0, lambda: self._side_scroll.ensureWidgetVisible(box, 0, 0))

    def _fold_toggled(self, on: bool) -> None:
        self.settings.ui_fold_steps = bool(on)
        save_settings(self.settings)
        if not on:
            for box in self._step_boxes:
                W.set_folded(box, False)

    def _eta_s(self, n: int) -> int:
        T = self.exp.n_timepoints
        n_roi = sum(len(c) for c in self.cells)
        n_mito = len(self._live("mito"))
        return int(np.ceil(T * (0.05 + 0.006 * n_roi + 0.025 * n_mito))) + 1

    # ============================================================= clicks
    def _on_point(self, x: float, y: float, shift: bool) -> None:
        if self._busy_now():
            self.set_status("Please wait - a job is running (see the bar under the image).")
            return
        self._end_live()                           # the previous one is settled
        if self._link_from is not None:
            k, comp = self._link_from
            self._link_from = None
            self._move(k, comp, self._cell_at(x, y))
            return
        if self._bound_on and self._bound_k is None:      # V2.5: which cell's boundary
            self._boundary_pick(x, y)
            return
        if self.tool == "draw":
            return
        if self.tool is None:
            k = self._cell_at(x, y, self.view_comp)
            if k is None:
                self.set_status("Nothing here. To add an ROI: turn on ADD (step 2).")
                return
            self._select(k)
            have = ", ".join(LABELS[c].lower() for c in COMPS if c in self.cells[k])
            self.set_status(f"Cell {k + 1} ({have}). Include / exclude it in the list beside "
                            f"the traces; right-click it for more.")
            return
        if self.comp == "background":
            self._place_background(x, y)
            return
        comp = self.comp
        k = self._roi_at(comp, x, y)
        if self.tool == "resize":
            if not self._ensure_t0():              # ROIs are drawn on one timepoint
                return
            if k is None:
                self.set_status(f"Click on a {LABELS[comp].lower()} ROI, then scroll to resize it.")
                return
            if self.chk_resize_all.isChecked():
                self._resize_all_toggled(True)
                return
            self._push_undo()
            self._select(k)
            self._start_live([k], comp)
            return
        if self.tool == "extend":
            if not self._ensure_t0():
                return
            if k is not None:                      # pick the cell to add to
                self._extend_k = k
                self._select(k)
                self.set_status(f"Adding to cell {k + 1}'s {LABELS[comp].lower()}: click where "
                                f"it continues (outside its outline).")
                return
            if self._extend_k is None or comp not in self.cells[self._extend_k]:
                self.set_status(f"First click the {LABELS[comp].lower()} ROI you want to add to.")
                return
            self._extend_click(self._extend_k, comp, x, y)
            return
        if self.tool == "add":
            if k is not None:
                self._select(k)
                self.set_status(f"That is cell {k + 1}'s {LABELS[comp].lower()} already. To "
                                f"redraw it, Remove it first.")
                return
            self._add_click(x, y)
        elif self.tool == "remove":
            if k is None:
                other = self._cell_at(x, y)
                self.set_status(f"No {LABELS[comp].lower()} there." +
                                (f" (That is part of cell {other + 1} - switch Compartment to "
                                 f"remove another kind of ROI.)" if other is not None else ""))
                return
            self._remove(k, comp)

    def _on_context(self, x: float, y: float, _k: int) -> None:
        if self._busy_now():
            return
        menu = QMenu(self)
        comp = self.view_comp
        k = self._roi_at(comp, x, y)
        if k is not None:
            lab = LABELS[comp].lower()
            menu.addAction(f"Cell {k + 1}: move this {lab} to another cell...",
                           lambda: self._start_move(k, comp))
            menu.addAction(f"Cell {k + 1}: make this {lab} a cell of its own",
                           lambda: self._move(k, comp, None))
            menu.addAction(f"Remove this {lab}", lambda: self._remove(k, comp))
            menu.addAction(f"Select cell {k + 1}", lambda: self._select(k))
        else:
            if self.comp != "background":
                menu.addAction(f"Add a {LABELS[self.comp].lower()} here",
                               lambda: self._add_click(x, y))
            menu.addAction("Put the background region here",
                           lambda: self._place_background(x, y))
        kb = self._cell_at(x, y) if k is None else k
        if kb is not None and self.boundaries.get(kb):
            menu.addAction(f"Remove cell {kb + 1}'s tracker boundary lines",
                           lambda: self._remove_boundary(kb))
        menu.exec(QCursor.pos())

    def _start_move(self, k: int, comp: str) -> None:
        self._link_from = (k, comp)
        self._refresh()
        self.set_status(f"Now click the cell this {LABELS[comp].lower()} belongs to - or an "
                        f"empty spot to make it a cell of its own. Esc cancels.")

    def _ensure_t0(self) -> bool:
        if self.t0 is not None and self.cur_t != self.t0:
            self._stop_play()
            self.slider.setValue(self.t0 + 1)
            self.set_status(f"ROIs are drawn on timepoint {self.t0 + 1}, so the image went "
                            f"back there. Click again.")
            return False
        return True

    def _add_click(self, x: float, y: float) -> None:
        if self.comp == "background" or not self._ensure_t0():
            return
        self._stop_play()
        comp = self.comp
        ch, seen = int(self._rule(comp).a), self._guide_name(comp, long=False)
        nuclei = [c["nucleus"] for c in self.cells if "nucleus" in c]
        expect = None
        if nuclei and comp == "nucleus":
            expect = float(np.median([r.area for r in nuclei])) * self.exp.um_per_px ** 2
        self.set_status(f"Drawing {LABELS[comp].lower()} on {seen}...")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            plane = self._guide(comp)              # the rule's image (channel A, or A + B)
            roi = draw_at(comp, plane, y, x, self.exp.um_per_px, self.settings, nuclei, expect)
        except Exception as exc:                                  # noqa: BLE001
            roi = None
            self.set_status(f"Could not draw there ({exc}).")
        finally:
            QApplication.restoreOverrideCursor()
        if roi is None:
            self.set_status(f"No clear {LABELS[comp].lower()} at that spot on {seen}. Click "
                            f"nearer its middle, check the tracking rule (step 1), or use "
                            f"Draw by hand.")
            return
        roi.channel = ch
        k = self._add_roi(roi, comp, "drawn at your click")
        if k is not None:
            note = self.lbl_status.text().replace(chr(0x200B), "")
            gate = self._gate_note(k, comp)
            self._start_live([k], comp, (gate + "  " + note) if gate else note)

    # ======================================================== auto-select
    def _auto_select(self) -> None:
        if self._busy_now() or self.comp == "background":
            return
        self._stop_play()
        if self.t0 is not None and self.cur_t != self.t0:
            self.slider.setValue(self.t0 + 1)              # ROIs live on one timepoint
        comp = self.comp
        nuclei = [c["nucleus"] for c in self.cells if "nucleus" in c]
        seeds = [c["nucleus"] for c in self.cells if "nucleus" in c and comp not in c]
        taken = [c[comp] for c in self.cells if comp in c]
        self._auto_ch, self._auto_t = int(self._rule(comp).a), self.cur_t
        self._auto_det = None
        self._start(FuncJob(auto_select, self._guide(comp), comp,
                            self.exp.um_per_px, self.settings, nuclei, taken, seeds),
                    self._on_auto_done,
                    f"Detecting {LABELS[comp].lower()} ROIs on "
                    f"{self._guide_name(comp, long=False)}...")

    # ============================================== V3.0 trained auto-detect
    def _fill_detectors(self) -> None:
        """One button per trained auto-detect of yours that fits this movie's channels."""
        from .. import detectors as DT
        while self._det_lay.count():
            it = self._det_lay.takeAt(0)
            w = it.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        try:
            dets = DT.listing(list(self.exp.channels))
        except Exception:                                          # noqa: BLE001
            dets = []
        for d in dets:
            tip = (f"{d.rule_text()}\n{d.score_text()}\nSets the {LABELS.get(d.comp, d.comp).lower()} "
                   f"rule to: using {d.main}" + (f", helped by {' + '.join(d.helpers)}"
                                                if d.helpers else "")
                   + f".\nTrained {d.created[:10]} on {len(d.trained_on)} of your movie(s).")
            b = W.button(f"★  {d.name}", lambda _c=False, d=d: self._use_detector(d),
                         f"AUTO-DETECT with your trained '{d.name}'\n{tip}")
            b.setStyleSheet("QPushButton { text-align: left; padding-left: 10px; }")
            from PySide6.QtWidgets import QSizePolicy
            b.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)   # never widens the panel
            b.setMinimumWidth(60)
            self._det_lay.addWidget(b)
        self.det_box.setVisible(bool(dets))

    def _use_detector(self, det) -> None:
        """A trained auto-detect: the full preset - its compartment's rule becomes its main
        channel + helpers, then it picks the cells with its learned rule."""
        if self._busy_now():
            return
        names = list(self.exp.channels)
        if not det.fits(names):
            self.set_status(f"'{det.name}' needs the channels {', '.join(det.channels())}.")
            return
        a = names.index(det.main)
        hs = tuple(names.index(h) for h in det.helpers if h in names)
        new = TrackRule(det.comp, a, HELP, -1, hs) if hs else TrackRule(det.comp, a)
        cur = list(self.rules.values())
        if any(r.comp == det.comp for r in cur):
            cur = [new if r.comp == det.comp else r for r in cur]
        else:
            cur = [new] + cur
        if self._rules_key() != tuple((r.comp, int(r.a), r.effective_mode(), -1,
                                       tuple(r.helper_list())) for r in cur):
            self._set_rules(cur)
        i = self.cmb_comp.findData(det.comp)
        if i >= 0:
            self.cmb_comp.setCurrentIndex(i)
        self._stop_play()
        if self.t0 is not None and self.cur_t != self.t0:
            self.slider.setValue(self.t0 + 1)
        comp = det.comp
        taken = [c[comp] for c in self.cells if comp in c]
        self._auto_ch, self._auto_t = a, self.cur_t
        self._auto_det = det
        from .. import detectors as DT
        self._start(FuncJob(DT.detect, self._load_frame(self.cur_t), names, det,
                            self.exp.um_per_px, taken),
                    self._on_auto_done, f"'{det.name}' is picking cells...")

    def _train_detector(self) -> None:
        """Open the training window (your runs -> a named auto-detect)."""
        if self._busy_now():
            return
        from .traindlg import TrainDialog
        r = self._rule("nucleus")
        names = list(self.exp.channels)
        hs = [names[h] for h in r.helper_list() if h < len(names)] if \
            r.effective_mode() == HELP else []
        d = TrainDialog(self, names, names[int(r.a)] if 0 <= int(r.a) < len(names) else names[0], hs)
        d.exec()
        self._fill_detectors()

    def _on_auto_done(self, rois) -> None:
        self._busy(False)
        self.progress.reset("Auto-detect finished.")
        comp = self.comp
        self._push_undo()
        gated = 0
        need = float(getattr(self.settings, "gate_snr", 5.0))
        det, self._auto_det = self._auto_det, None
        if det is not None:                             # V3.0: its own learned rule decides
            self._detector_used = det
        cands = []
        for r in rois:
            r.channel = self._auto_ch
            snr = None if det is not None else self._gate(comp, r, self._auto_t)
            if snr is not None and not (np.isfinite(snr) and snr >= need):
                gated += 1
                continue
            cands.append(r)
        skipped = ""
        if gated and self._rule(comp).effective_mode() == HELP:
            skipped = (f" Skipped {gated} without {self._helper_names(comp)} signal (helper "
                       f"channel: signal-to-noise below {need:g}) - click them by hand if you "
                       f"want them.")
        elif gated:
            b = self.exp.channels[int(self._rule(comp).b)]
            skipped = (f" Skipped {gated} without {b} signal (IF rule: signal-to-noise below "
                       f"{need:g}) - click them by hand if you want them.")
        # V2.5: brightest first (mean inside the ROI minus the background, on the image
        # they were detected on, at this timepoint) - the slider drops the dimmest
        bright = self._auto_brightness(comp, cands, self._auto_t)
        order = sorted(range(len(cands)), key=lambda i: -bright[i])
        self._auto_batch = dict(comp=comp, cands=[cands[i] for i in order],
                                bright=[bright[i] for i in order],
                                base=[dict(c) for c in self.cells], t0=self.t0,
                                skipped=skipped, placed=[])
        added = self._auto_apply(len(cands))
        if not added:
            self._auto_batch = None
            self.auto_row.hide()
            self._undo_stack.pop()
            self.btn_undo.setEnabled(bool(self._undo_stack))
            self.set_status((f"'{det.name}' picked no further cells here - "
                             if det is not None else
                             f"Auto-detect found no further well-defined {LABELS[comp].lower()} "
                             f"ROIs - ") + "add the rest by clicking." + skipped)
            self._refresh()
            return
        self.sl_auto.blockSignals(True)
        self.sl_auto.setRange(1, len(cands))
        self.sl_auto.setValue(len(cands))
        self.sl_auto.blockSignals(False)
        self.auto_row.show()
        self._auto_label()
        if det is not None:
            self.set_status(f"'{det.name}' picked {added} cells (its learned rule: "
                            f"{det.rule_text()}) Check them; move the slider under AUTO-DETECT to "
                            f"keep only the brightest; Undo takes all of them back.")
            return
        self.set_status(f"Auto-detect added {added} {LABELS[comp].lower()} ROIs (clearly "
                        f"above background, normal size and shape, separate). Move the slider "
                        f"under AUTO-DETECT to keep only the brightest; remove any you don't "
                        f"want, Add the ones it skipped; Undo takes all of them back."
                        + skipped)

    def _auto_brightness(self, comp: str, rois, t: int) -> List[float]:
        """Mean of the detection image inside each ROI minus the background region's
        mean on the same image, at timepoint t (the auto-detect slider's order)."""
        plane = self._guide(comp, t)
        bg = 0.0
        if self.background is not None:
            y0, x0, y1, x1 = self.background.bbox
            v = plane[y0:y1, x0:x1][self.background.mask]
            bg = float(v.astype(np.float64).mean()) if v.size else 0.0
        out = []
        for r in rois:
            y0, x0, y1, x1 = r.bbox
            v = plane[y0:y1, x0:x1][r.mask]
            out.append(float(v.astype(np.float64).sum() / v.size) - bg if v.size else -np.inf)
        return out

    def _auto_apply(self, n: int) -> int:
        """Put the n brightest auto-detected ROIs in (on top of the cells as they
        were before AUTO-DETECT). Returns how many were placed."""
        B = self._auto_batch
        if B is None:
            return 0
        self._auto_applying = True
        try:
            self.cells = [dict(c) for c in B["base"]]
            placed = []
            for r in B["cands"][:int(n)]:
                if self._place_roi(copy.copy(r), B["comp"]) is not None:
                    placed.append(r)
            B["placed"] = placed
            self.t0 = B["t0"] if B["t0"] is not None or not placed else self.cur_t
            self._structure_changed()
        finally:
            self._auto_applying = False
        return len(placed)

    def _auto_label(self) -> None:
        B = self._auto_batch
        if B is None:
            return
        n, m = self.sl_auto.value(), len(B["cands"])
        cut = B["bright"][n - 1] if 0 < n <= m else 0.0
        self.lbl_auto.setText(f"Keep the {n} brightest of the {m} found "
                              f"({len(B['placed'])} placed; dimmest kept: {cut:.0f} counts above "
                              f"background). Slide left to drop the dimmest.")

    def _auto_keep(self, n: int) -> None:
        if self._auto_batch is None or self._busy_now():
            return
        self._auto_apply(int(n))
        self._auto_label()
        self.set_status(f"Auto-detect: keeping the {int(n)} brightest of "
                        f"{len(self._auto_batch['cands'])} found.")

    def _place_roi(self, roi: Roi, comp: str):
        """Put an ROI in (trimmed off other cells, linked to its cell). (cell, kept) or None."""
        others = [c[comp] for c in self.cells if comp in c]
        ch = getattr(roi, "channel", 0)
        roi2, frac = cut_overlaps(roi, others)
        if roi2 is None or frac < 0.3:
            return None
        roi2.channel, roi2.kind = ch, comp
        roi2.source = getattr(roi, "source", "manual") or "manual"
        k = link_cell(self.cells, roi2, comp, self.exp.um_per_px)
        if k < 0:
            self.cells.append({comp: roi2})
            k = len(self.cells) - 1
        else:
            self.cells[k][comp] = roi2
        return k, frac

    def _add_roi(self, roi: Roi, comp: str, how: str) -> Optional[int]:
        others = [c[comp] for c in self.cells if comp in c]
        ch = getattr(roi, "channel", 0)
        roi2, frac = cut_overlaps(roi, others)
        if roi2 is None or frac < 0.3:
            k = self._roi_at(comp, *roi.centroid[::-1])
            who = f"cell {k + 1}'s" if k is not None else "another cell's"
            self.set_status(f"That spot is already covered by {who} {LABELS[comp].lower()}. "
                            f"Click a different cell, or Remove that one first.")
            return None
        roi2.channel, roi2.kind, roi2.source = ch, comp, "manual"
        k = link_cell(self.cells, roi2, comp, self.exp.um_per_px)
        self._push_undo()
        if k < 0:
            self.cells.append({comp: roi2})
            k = len(self.cells) - 1
            where = f"new cell {k + 1}"
        else:
            had = ", ".join(LABELS[c].lower() for c in COMPS if c in self.cells[k])
            self.cells[k][comp] = roi2
            where = f"cell {k + 1} (it sits on that cell's {had})"
        if self.t0 is None:
            self.t0 = self.cur_t
        self.selected = k
        self._structure_changed()
        trimmed = "" if frac > 0.98 else f" Trimmed where it touched other cells ({frac:.0%} kept)."
        self.set_status(f"{LABELS[comp]} added to {where}, {how}.{trimmed} Wrong cell? "
                        f"Right-click it. Wrong shape? Undo, then Draw by hand.")
        return k

    # ===================================================== scroll to resize
    def _start_live(self, ks: List[int], comp: str, note: str = "") -> None:
        """These cells' ROIs (one, or all of the compartment) are 'live': the mouse
        wheel redraws them bigger / smaller from the image (12 % of area per notch,
        no limit either way)."""
        entries = []
        for k in ks:
            base = self.cells[k].get(comp)
            if base is None:
                continue
            entries.append(dict(k=k, ch=int(self._rule(comp).a), base=base, steps=0))
        if not entries:
            return
        self._live_roi = dict(comp=comp, entries=entries, changed=False)
        self.view.wheel_adjust = True
        who = (f"cell {entries[0]['k'] + 1}'s {LABELS[comp].lower()}" if len(entries) == 1
               else f"all {len(entries)} {LABELS[comp].lower()} ROIs")
        self.set_status((note + "  " if note else "") +
                        f"SCROLL to make {who} bigger (up) or smaller (down) - as far as you "
                        f"like, redrawn from the image each step. Click on, or Esc, when it is "
                        f"right.")

    def _end_live(self) -> None:
        if getattr(self, "_live_roi", None) is not None:
            self._live_roi = None
            self.view.wheel_adjust = False

    def _on_wheel(self, steps: int) -> None:
        L = getattr(self, "_live_roi", None)
        if L is None or self._busy_now():
            self.view.wheel_adjust = False
            return
        comp = L["comp"]
        um, k_mito = self.exp.um_per_px, float(getattr(self.settings, "mito_k", 3.0))
        many = len(L["entries"]) > 1
        if many:
            QApplication.setOverrideCursor(Qt.WaitCursor)
        changed, total, base_total = 0, 0.0, 0.0
        try:
            for e in L["entries"]:
                k = e["k"]
                if comp not in self.cells[k]:
                    continue
                want = e["steps"] + int(steps)
                others = [c[comp] for j, c in enumerate(self.cells) if j != k and comp in c]
                nucleus = self.cells[k].get("nucleus") if comp != "nucleus" else None
                plane = self._guide(comp)          # the rule's image (cached per frame)
                new = resize_roi(plane, e["base"], comp, want, um, others, nucleus, k_mito)
                if new is None or not new.area:
                    continue
                new.channel, new.kind, new.source = e["ch"], comp, "manual"
                self.cells[k][comp] = new
                e["steps"] = want
                changed += 1
                total += _region(new).area * um * um
                base_total += _region(e["base"]).area * um * um
        finally:
            if many:
                QApplication.restoreOverrideCursor()
        if not changed:
            self.set_status("It cannot get any " + ("bigger" if steps > 0 else "smaller") +
                            " here.")
            return
        if not L["changed"]:
            L["changed"] = True
            self._structure_changed()              # tracked results no longer match
        self._mark_dirty()                         # saved a moment after the last notch
        self._refresh()
        x = total / max(base_total, 1e-9)
        if many:
            self.set_status(f"{changed} {LABELS[comp].lower()} ROIs redrawn (mean "
                            f"{total / changed:.0f} um2, x{x:.2f} of where you started). Keep "
                            f"scrolling, or click / Esc when they are right.")
        else:
            k = L["entries"][0]["k"]
            self.set_status(f"Cell {k + 1}'s {LABELS[comp].lower()}: {total:.0f} um2 (x{x:.2f} "
                            f"of where you started). Keep scrolling, or click on / Esc when it "
                            f"is right.")

    # ================================================ split / add to cell
    def _on_stroke(self, points) -> None:
        """Split: the line drawn cuts the ROI it crosses into two cells."""
        if self.tool != "split" or self.comp == "background" or self._busy_now():
            return
        if not self._ensure_t0():
            return
        comp = self.comp
        hits: Dict[int, int] = {}
        step = max(1, len(points) // 60)
        for x, y in points[::step]:
            k = self._roi_at(comp, x, y)
            if k is not None:
                hits[k] = hits.get(k, 0) + 1
        if not hits:
            self.set_status(f"That line does not cross a {LABELS[comp].lower()} ROI - draw it "
                            f"across the one to cut.")
            return
        k = max(hits, key=hits.get)
        parts = split_roi(self.cells[k][comp], points, self.exp.um_per_px)
        if parts is None:
            self.set_status(f"The line must cut cell {k + 1}'s {LABELS[comp].lower()} into two "
                            f"real pieces - draw it right across.")
            return
        self._push_undo()
        a, b = parts
        others = [r for c, r in self.cells[k].items() if c != comp]
        # the cell keeps the part that holds its other compartments (e.g. its nucleus)
        if sum(_overlap_px(b, r) for r in others) > sum(_overlap_px(a, r) for r in others):
            a, b = b, a
        self.cells[k][comp] = a
        self.cells.append({comp: b})
        nk = len(self.cells) - 1
        if k in self.excl[comp]:
            self.excl[comp].add(nk)
        self.selected = nk
        self._structure_changed()
        self.set_status(f"Cell {k + 1}'s {LABELS[comp].lower()} split in two: cell {k + 1} and "
                        f"new cell {nk + 1}. Draw another line to split more; Undo takes it back.")

    def _extend_click(self, k: int, comp: str, x: float, y: float) -> None:
        ch = int(self._rule(comp).a)
        plane = self._guide(comp)                   # the rule's image
        others = [c[comp] for j, c in enumerate(self.cells) if j != k and comp in c]
        nucleus = self.cells[k].get("nucleus") if comp != "nucleus" else None
        old = self.cells[k][comp]
        new = extend_roi(plane, old, comp, y, x, self.exp.um_per_px, others, nucleus,
                         float(getattr(self.settings, "mito_k", 3.0)))
        if new is None or _region(new).area <= _region(old).area:
            self.set_status("Nothing to add there (already inside, or another cell's). Click "
                            "just outside the outline where the cell continues.")
            return
        self._push_undo()
        new.channel, new.kind, new.source = ch, comp, "manual"
        self.cells[k][comp] = new
        um2 = self.exp.um_per_px ** 2
        self._structure_changed()
        self._select(k)
        self.set_status(f"Added {(_region(new).area - _region(old).area) * um2:.0f} um2 to cell "
                        f"{k + 1}'s {LABELS[comp].lower()} (now {_region(new).area * um2:.0f} "
                        f"um2). Click more parts, or Undo.")

    def _on_polygon(self, points) -> None:
        if self.tool != "draw":
            return
        comp = self.comp if self.comp != "background" else "nucleus"
        if not self._ensure_t0():
            QTimer.singleShot(0, self.view.start_polygon)
            return
        ch = int(self._rule(comp).a)
        nuclei = [c["nucleus"] for c in self.cells if "nucleus" in c]
        roi = from_outline(comp, points, (self.exp.height, self.exp.width),
                           self._guide(comp), self.exp.um_per_px, nuclei,
                           float(getattr(self.settings, "mito_k", 3.0)))
        gate = ""
        if roi is None:
            self.set_status("That outline was empty - nothing added.")
        else:
            roi.channel = ch
            k = self._add_roi(roi, comp, "drawn by hand")
            gate = self._gate_note(k, comp) if k is not None else ""
            if gate:
                gate = gate + "  " + self.lbl_status.text().replace(chr(0x200B), "")
                self.set_status(gate)
        if self.tool == "draw":
            def again() -> None:
                self.view.start_polygon()
                if gate:                          # the IF warning stays on show
                    self.set_status(gate)
            QTimer.singleShot(0, again)

    def _remove(self, k: int, comp: str) -> None:
        if comp not in self.cells[k]:
            return
        self._push_undo()
        self.cells[k].pop(comp, None)
        self.excl[comp].discard(k)
        if not any(self.cells):
            self.t0 = None
        self.selected = None
        self._structure_changed()
        self.set_status(f"Removed cell {k + 1}'s {LABELS[comp].lower()}. Undo brings it back.")

    def _move(self, k: int, comp: str, target: Optional[int]) -> None:
        if comp not in self.cells[k]:
            return
        if target == k:
            self.set_status("That is the same cell - nothing changed.")
            self._refresh()
            return
        if target is not None and comp in self.cells[target]:
            self.set_status(f"Cell {target + 1} already has a {LABELS[comp].lower()}. Remove "
                            f"it first if this one should replace it.")
            self._refresh()
            return
        self._push_undo()
        roi = self.cells[k].pop(comp)
        was_out = k in self.excl[comp]
        self.excl[comp].discard(k)
        gate_why = self._gate_why.setdefault(comp, {}).pop(k, None)   # IF exclusion moves too
        if target is None:
            self.cells.append({comp: roi})
            target = len(self.cells) - 1
            msg = f"is now a cell of its own (cell {target + 1})"
        else:
            self.cells[target][comp] = roi
            msg = f"now belongs to cell {target + 1}"
        if was_out:
            self.excl[comp].add(target)
            if gate_why:
                self._gate_why[comp][target] = gate_why
        self.selected = target
        self._structure_changed()
        self.set_status(f"The {LABELS[comp].lower()} {msg}. Undo takes it back.")

    def _set_include(self, comp: str, k: int, on: bool) -> None:
        if not (0 <= k < len(self.cells)) or comp not in self.cells[k]:
            return
        if on == (k not in self.excl[comp]):
            return
        self._push_undo()
        (self.excl[comp].discard if on else self.excl[comp].add)(k)
        self._gate_why.setdefault(comp, {}).pop(k, None)   # your choice now
        self.selected = k
        self._mark_dirty()
        self._refresh()
        self._sync_traces()
        self.set_status(f"Cell {k + 1}'s {LABELS[comp].lower()}: "
                        f"{'INCLUDED' if on else 'EXCLUDED'} (only this compartment).")

    def _include_all(self, on: bool) -> None:
        comp = self.view_comp
        live = self._live(comp)
        if not live:
            return
        self._push_undo()
        self.excl[comp] = set() if on else set(live)
        self._gate_why[comp] = {}
        self._mark_dirty()
        self._refresh()
        self._sync_traces()
        self.set_status(f"Every {LABELS[comp].lower()} {'included' if on else 'excluded'}.")

    def _select(self, k: int) -> None:
        self.selected = k
        self._refresh()
        self.traces.select(k)

    def _structure_changed(self, why: str = "") -> None:
        """ROIs added / removed / moved, or the tracking rules changed (why = the
        message): earlier tracking no longer matches."""
        if not self._auto_applying and self._auto_batch is not None:
            self._auto_batch = None                   # the auto-detected set is accepted
            self.auto_row.hide()
        if self.track is not None:
            self.track = None
            self._was_tracked = True
            self._stale_rules = bool(why)
            self.qc = {}
            self.traces.clear(why or "The ROIs changed - press TRACK & MEASURE again to "
                                     "update the traces.")
            self.lbl_track.setText(why or "ROIs changed since tracking - track again.")
        elif not why:
            self._stale_rules = False
        self._exported = None
        self.btn_export.setEnabled(False)
        self._mark_dirty()
        self._refresh()

    # ========================================================= background
    def _auto_background(self) -> None:
        if self.background is not None:
            self._bg_tried = True
            return
        self.progress.busy("Finding an empty background area...")
        QApplication.processEvents()
        try:
            T = self.exp.n_timepoints
            stacks = [self._load_frame(t) for t in sorted({0, T // 2, T - 1})]
            bg, _msg = auto_background(stacks, self.exp.um_per_px,
                                       float(getattr(self.settings, "background_max_um", 150)))
        except Exception as exc:                                   # noqa: BLE001
            bg = None
            self.set_status(f"No empty area found automatically ({exc}).")
        self.progress.unbusy()
        self.progress.reset("Ready.")
        self._bg_tried = True
        if self.background is not None:          # placed (or loaded) in the meantime
            self._refresh()
            return
        if bg is not None:
            self.background, self._bg_auto, self._bg_kind = bg, True, "auto"
            self.set_status("Background region placed automatically (green box; cells in it are "
                            "fine). To choose it yourself: Compartment 'Background', then Add "
                            "(a square) or Draw by hand.")
        else:
            self.set_status("No empty area found for the background - right-click an empty "
                            "area > 'Put the background region here'.")
        self._refresh()

    def _place_background(self, x: float, y: float) -> None:
        r = background_at(self._load_frame(self.cur_t), y, x, self.exp.um_per_px)
        if r is None:
            self.set_status("Too close to the edge - click further in.")
            return
        self._push_undo()
        self.background, self._bg_auto, self._bg_kind = r, False, "click"
        self._structure_changed()
        self.set_status("Background region moved here (green box). Cells in it are fine; every "
                        "pixel is used (you will be told after tracking if the background is "
                        "not steady).")

    def _on_lasso(self, points) -> None:
        """V2.5: the background drawn by hand (Background > Draw by hand)."""
        if self.tool != "draw" or self.comp != "background":
            return
        r = background_from_outline(points, (self.exp.height, self.exp.width))
        if r is None:
            self.set_status("That outline was too small - draw around a bigger region.")
            return
        self._push_undo()
        self.background, self._bg_auto, self._bg_kind = r, False, "hand"
        self._structure_changed()
        um2 = r.area * self.exp.um_per_px ** 2
        self.set_status(f"Background region drawn by hand ({um2:.0f} µm²). Cells in it are fine "
                        f"(their autofluorescence is background); every pixel is used - you will "
                        f"be told after tracking if the background jumps or drifts. Draw again "
                        f"to replace it.")

    def _replace_auto_background(self) -> None:
        """Before tracking: the AUTOMATIC background is placed again, now avoiding
        every ROI you drew (with a small margin)."""
        if not self._bg_auto or self.background is None:
            return
        rois = [r for cell in self.cells for r in cell.values() if r is not None]
        if not rois:
            return
        try:
            T = self.exp.n_timepoints
            stacks = [self._load_frame(t) for t in sorted({0, T // 2, T - 1})]
            bg, _msg = auto_background(stacks, self.exp.um_per_px,
                                       float(getattr(self.settings, "background_max_um", 150)),
                                       avoid=rois)
        except Exception:                                          # noqa: BLE001
            return
        if bg is not None and (bg.bbox != self.background.bbox
                               or not np.array_equal(bg.mask, self.background.mask)):
            self.background = bg
            self._refresh()

    # ===================================================== tracker boundary
    def _boundary_toggled(self, on: bool) -> None:
        """V2.5 'Tracker boundary': click a cell, then draw lines it never crosses."""
        self._bound_on = bool(on)
        self._bound_k = None
        if on:
            if self.tool is not None:
                self._set_tool(None)
            self._end_live()
            self.btn_bound.setStyleSheet("QPushButton { background: #ff5a28; color: white; "
                                         "font-weight: 800; }")
            self.set_status("TRACKER BOUNDARY: click the cell the lines are for.")
        else:
            self.btn_bound.setStyleSheet("")
            if self.view.mode == "polyline":
                self.view.cancel_draw()
            self._refresh()

    def _boundary_pick(self, x: float, y: float) -> None:
        k = self._cell_at(x, y, self.view_comp)
        if k is None:
            self.set_status("TRACKER BOUNDARY: click ON the cell (one of its ROIs) first.")
            return
        self._bound_k = k
        self._select(k)
        self.view.start_polyline()
        n = len(self.boundaries.get(k, []))
        self.set_status(f"TRACKER BOUNDARY for cell {k + 1}" + (f" (has {n} line(s))" if n else "")
                        + ": click the points of a line its ROIs must never cross; double-click "
                        "to finish it. Draw more lines, or click 'Tracker boundary' again (Esc) "
                        "when done.")

    def _on_boundary_line(self, points) -> None:
        k = self._bound_k
        if not self._bound_on or k is None or not (0 <= k < len(self.cells)):
            return
        line = [(float(px), float(py)) for px, py in points]
        self._push_undo()
        self.boundaries.setdefault(k, []).append(line)
        self._structure_changed(f"Cell {k + 1}'s tracker boundary changed - press TRACK & "
                                f"MEASURE again.")
        self.set_status(f"Line added to cell {k + 1}'s tracker boundary "
                        f"({len(self.boundaries[k])} line(s)). Draw another, or click 'Tracker "
                        f"boundary' again when done. Undo takes it back.")

    def _remove_boundary(self, k: Optional[int]) -> None:
        k = self.selected if k is None else k
        if k is None or not self.boundaries.get(k):
            self.set_status("Click a cell that has tracker boundary lines first (they are drawn "
                            "in orange), then 'Remove lines'.")
            return
        self._push_undo()
        n = len(self.boundaries.pop(k))
        self._structure_changed(f"Cell {k + 1}'s tracker boundary changed - press TRACK & "
                                f"MEASURE again.")
        self.set_status(f"Removed cell {k + 1}'s {n} tracker boundary line(s). Undo brings them "
                        f"back.")

    def _boundaries_state(self) -> Dict[str, list]:
        """The lines as saved: {cell index (text): [[[x, y], ...], ...]}."""
        return {str(int(k)): [[[float(px), float(py)] for px, py in ln] for ln in lines]
                for k, lines in sorted(self.boundaries.items()) if lines}

    @staticmethod
    def _boundaries_from(v, n_cells: int) -> Dict[int, List[List[tuple]]]:
        """Lines from a saved state (anything unreadable is skipped)."""
        out: Dict[int, List[List[tuple]]] = {}
        if not isinstance(v, dict):
            return out
        for key, lines in v.items():
            try:
                k = int(key)
                got = [[(float(q[0]), float(q[1])) for q in ln] for ln in lines]
            except (TypeError, ValueError, IndexError):
                continue
            got = [ln for ln in got if len(ln) >= 2]
            if 0 <= k < n_cells and got:
                out[k] = got
        return out

    # ============================================================== undo
    def _snapshot(self):
        return dict(cells=[dict(c) for c in self.cells],
                    excl={c: set(v) for c, v in self.excl.items()},
                    bg=self.background, bg_auto=self._bg_auto, bg_kind=self._bg_kind,
                    bounds={k: [list(ln) for ln in v] for k, v in self.boundaries.items()},
                    t0=self.t0,
                    track=self.track, qc=dict(self.qc), was=self._was_tracked,
                    gate_why={c: dict(v) for c, v in self._gate_why.items()},
                    rules=(self._rules_key(), tuple(sorted(self._track_settings().items()))))

    def _push_undo(self) -> None:
        self._undo_stack.append(self._snapshot())
        del self._undo_stack[:-60]
        self.btn_undo.setEnabled(True)

    def _undo(self) -> None:
        self._end_live()
        if self._busy_now() or not self._undo_stack:
            return
        s = self._undo_stack.pop()
        self.cells, self.excl = s["cells"], s["excl"]
        self.background, self._bg_auto, self.t0 = s["bg"], s["bg_auto"], s["t0"]
        self._bg_kind = s.get("bg_kind", "auto" if self._bg_auto else "click")
        self.boundaries = s.get("bounds", {})
        if self._auto_batch is not None:              # the auto-detected set is undone
            self._auto_batch = None
            self.auto_row.hide()
        self.track, self.qc, self._was_tracked = s["track"], s["qc"], s["was"]
        self._gate_why = s.get("gate_why") or {c: {} for c in COMPS}
        if self.track is not None and s.get("rules") != (
                self._rules_key(), tuple(sorted(self._track_settings().items()))):
            # that tracking was made with other rules: it does not come back
            self.track, self.qc, self._was_tracked = None, {}, True
            self._stale_rules = True
        self._link_from = None
        self._mark_dirty()
        self.btn_undo.setEnabled(bool(self._undo_stack))
        self.btn_export.setEnabled(self.track is not None)
        if self.track is None:
            self.traces.clear()
        self._refresh()
        self._sync_traces(full=True)
        self.set_status("Undone.")

    # ============================================================== jobs
    def _busy(self, on: bool) -> None:
        for w in (self.btn_track, self.btn_load, self.cmb_comp, self.btn_row, self._rows_box,
                  self.btn_auto, *self._tool_btn.values()):
            w.setEnabled(not on)
        self.btn_export.setEnabled(not on and self.track is not None)
        self.btn_undo.setEnabled(not on and bool(self._undo_stack))
        self.btn_stop.setEnabled(on)
        if not on:
            self._update_hint()
        if on:
            self.lbl_next.setText("Working... see the progress bar under the image "
                                  "(Stop cancels).")

    def _start(self, job, on_done, label: str) -> None:
        if self._busy_now():
            QMessageBox.information(self, "Still working", "Wait for the current job to "
                                                           "finish, or press Stop.")
            return
        self._busy(True)
        self.progress.reset(label)
        self._runner = JobRunner(job, on_done=on_done, on_fail=self._on_fail,
                                 on_progress=self.progress.update,
                                 on_cancel=self._on_cancelled, parent=self)
        self._runner.start()

    def _cancel(self) -> None:
        if self._runner is not None:
            self._runner.cancel()
            self.progress.msg.setText("Stopping...")

    def _on_cancelled(self) -> None:
        self._busy(False)
        self.progress.reset("Stopped by you.")
        self.set_status("Stopped. Nothing was changed.")
        self._update_next()

    def _on_fail(self, message: str, detail: str) -> None:
        self._busy(False)
        self.progress.reset("Stopped because of an error.")
        box = QMessageBox(QMessageBox.Critical, "Something went wrong", message, parent=self)
        box.setDetailedText(detail)
        box.exec()
        self._update_next()

    # ============================================================= track
    def _track(self) -> None:
        self._end_live()
        cells = [{c: r for c, r in cell.items() if c in self.follow} for cell in self.cells]
        n = sum(1 for c in cells if c)
        if n == 0:
            QMessageBox.information(self, "No ROIs yet",
                                    "Add ROIs of a compartment that has a tracking rule "
                                    "first (step 2).")
            return
        if self.background is None:                # V3.0: straight to placing it
            self._pick_background()
            self.set_status("First pick a background spot: click an empty area (no bright "
                            "cells) - Background > Add is on. Then press TRACK & MEASURE again.")
            return
        self._stop_play()
        self._replace_auto_background()            # V2.5: automatic region avoids your ROIs
        s = self.settings
        bounds = {k: v for k, v in self.boundaries.items() if v and 0 <= k < len(cells)}
        self._start(FuncJob(track_cells, self.src, self.exp, cells, self.background,
                            int(self.t0 or 0), float(getattr(s, "max_move_um", 3.0)),
                            float(getattr(s, "mito_k", 3.0)), int(self.exp.sat_level),
                            list(self.follow),
                            size_tol=float(getattr(s, "track_size_tol", 0.25)),
                            rules=dict(self.rules),
                            gate_snr=float(getattr(s, "gate_snr", 5.0)),
                            overlap_k=float(getattr(s, "overlap_k", 3.0)),
                            boundaries=bounds or None),
                    self._on_tracked,
                    f"Following and redrawing {n} cells through {self.exp.n_timepoints} "
                    f"timepoints (about {self._eta_s(n)} s)...")

    def _track_rule(self, comp: str, out: Optional[dict] = None):
        """The rule a tracking result was made with (its own record if it has one,
        else the current rule)."""
        names = list(self.exp.channels)
        for d in ((out or self.track or {}).get("rules") or []):
            if isinstance(d, dict) and d.get("comp") == comp:
                r = TrackRule.from_dict(d, names)
                if r is not None:
                    return r
        return self.rules.get(comp)

    def _on_tracked(self, out: dict, loaded: bool = False) -> None:
        """Tracking finished (or was loaded with an ROI file: loaded=True keeps your
        include / exclude choices as saved instead of applying the IF rule again)."""
        self._busy(False)
        self.track = out
        self._was_tracked = True
        self._stale_rules = False
        s = self.settings
        s.seg_timepoint = int(self.t0 or 0) + 1
        self.qc = {}
        gate = out.get("gate") or {}
        need = float(getattr(s, "gate_snr", 5.0))
        gated = {}
        for c, M in out["meas"].items():
            rule = self._track_rule(c, out)
            try:
                seeds = [cell.get(c) or _blank() for cell in self.cells]
                for r in seeds:
                    r.source = "manual"
                self.qc[c] = run_qc(M, self.exp, s, out["rois"][c], seeds, rule=rule,
                                    gate=gate.get(c))
            except Exception:                                      # noqa: BLE001
                self.qc[c] = []
            # IF rule: cells without signal in channel B are excluded, with the reason.
            # A new tracking first gives back the cells the LAST IF gate excluded (you
            # did not exclude them; _gate_why loses a cell once you include / exclude
            # it yourself): the gate below decides afresh, so a rule changed from IF
            # to another mode leaves no exclusion behind.
            if not loaded:
                for k in self._gate_why.get(c, {}):
                    self.excl[c].discard(k)
            self._gate_why[c] = {}
            if c in gate and rule is not None and 0 <= int(rule.b) < self.exp.n_channels:
                name_b = self.exp.channels[int(rule.b)]
                for k, snr in gate[c].items():
                    why = gate_reason(name_b, snr, need)
                    if why is None or not (0 <= int(k) < len(self.cells)) \
                            or c not in self.cells[int(k)]:
                        continue
                    k = int(k)
                    if loaded and k not in self.excl[c]:
                        continue                      # you included it again before saving
                    self.excl[c].add(k)
                    self._gate_why[c][k] = why
                    gated.setdefault(c, []).append(k)
        n = sum(1 for c in self.cells if any(k in self.follow for k in c))
        red = out.get("redrawn", {})
        pct = ", ".join(f"{LABELS[c].lower()} {v:.0%}" for c, v in red.items())
        gate_txt = "".join(
            f" IF rule: {len(ks)} {LABELS[c].lower()} ROI(s) excluded for no "
            f"{self.exp.channels[int(self._track_rule(c, out).b)]} signal (cell "
            f"{', '.join(str(k + 1) for k in sorted(ks))}) - tick them in the list to "
            f"include them anyway." for c, ks in gated.items() if not loaded)
        warn = "" if loaded else background_warning(out.get("background") or {},
                                                     channels=list(self.exp.channels))
        self.lbl_track.setText(f"Tracked {n} cells through {self.exp.n_timepoints} timepoints. "
                               f"ROIs redrawn at every timepoint ({pct}); where a redraw "
                               f"looked wrong the previous outline was moved with the cell "
                               f"instead (noted per cell in QC)." + gate_txt
                               + (f"<br><b style='color:#d04a00'>{warn}</b>" if warn else ""))
        self.progress.reset("Tracking finished.")
        self.btn_export.setEnabled(True)
        self._refresh()
        self._sync_traces(full=True)
        self._dock.show()
        self.set_status("Tracked. Press ▶ Play to watch the outlines follow the cells. "
                        "Switch Compartment to see each one's traces." + gate_txt)
        if warn:                          # V2.7: an object in the background region - redraw?
            self._bg_box = QMessageBox(QMessageBox.Warning, "Object in the background region", warn,
                                       parent=self)
            redraw = self._bg_box.addButton("Redraw background", QMessageBox.AcceptRole)
            self._bg_box.addButton("Keep it", QMessageBox.RejectRole)
            self._bg_box.setModal(False)
            self._bg_box.buttonClicked.connect(
                lambda b: self._redraw_background() if b is redraw else None)
            self._bg_box.show()
            self.set_status(warn)
        if not loaded:                    # a milestone: the tracking is saved right away
            self._mark_dirty()
            self._autosave()

    # ============================================================ traces
    def _why(self, comp: str) -> Dict[int, str]:
        out = {}
        notes = {q.index: "; ".join(q.reasons) for q in self.qc.get(comp, []) if not q.passed}
        gate = self._gate_why.get(comp, {})
        for k in self._live(comp):
            if k in self.excl[comp]:
                out[k] = f"excluded by the IF rule: {gate[k]}" if k in gate else \
                    "excluded by you"
            elif k in notes:
                out[k] = "QC note: " + notes[k]
            else:
                out[k] = "included"
        return out

    def _measured(self, comp: str):
        """(Measurements of EVERY channel - all channels are always measured in every
        ROI, so every channel and every ratio pair is shown and exported -, the
        channel indices)."""
        M = self.track["meas"][comp]
        return M, list(range(M.n_channels))

    def _prefer(self, comp: str, M) -> List[str]:
        """Trace quantities to open on, best first: your key quantities
        (Settings.resp_quantity, R/R0 first), then R/R0 of the rule's two channels,
        then F/F0 of its channel A."""
        prefer = sorted((q.strip() for q in str(self.settings.resp_quantity or "").split(";")
                         if q.strip()), key=lambda q: 0 if q.startswith("R/R0") else 1)
        rule = self._rule(comp)
        names = list(M.channels)
        a = self.exp.channels[int(rule.a)] if 0 <= int(rule.a) < self.exp.n_channels else ""
        bi = rule.helper_list()[0] if rule.effective_mode() == HELP else int(rule.b)
        b = self.exp.channels[bi] if rule.effective_mode() != "only" \
            and 0 <= bi < self.exp.n_channels else ""
        if a in names and b in names:
            prefer.append(f"R/R0 - {a}/{b}")
        if a in names:
            prefer.append(f"F/F0 - {a}")
        return prefer

    def _prefer_sheets(self, comp: str, M) -> List[str]:
        """Export graphs chosen by default: your key quantities, else the rule's
        R/R0 (A/B) and F/F0 (A) - as sheet names."""
        got = preferred_sheets(M, self.settings)
        if got:
            return got
        from ..excel import short_tags
        tags = dict(zip(M.channels, short_tags(M.channels)))
        out = []
        for q in self._prefer(comp, M):
            if q.startswith("R/R0 - "):
                a, b = q[7:].split("/", 1)
                if a in tags and b in tags:
                    out.append(f"dRR_{tags[a]}_over_{tags[b]}")
            elif q.startswith("F/F0 - ") and q[7:] in tags:
                out.append(f"dFF_{tags[q[7:]]}")
        return out

    def _sync_traces(self, full: bool = False) -> None:
        comp = self.view_comp
        if self.track is None or comp not in self.track["meas"]:
            if self.track is not None:
                self.traces.clear(f"No {LABELS[comp].lower()} ROIs were tracked - choose "
                                  f"another Compartment, or add some and track again.")
            return
        live = self._live(comp)
        inc = [k for k in live if k not in self.excl[comp]]
        if full:
            self._export_context()
            M, _idx = self._measured(comp)
            a = self.exp.channels[min(int(self._rule(comp).a), self.exp.n_channels - 1)]
            ref = M.channels.index(a) if a in M.channels else 0
            self.traces.set_data(M, live, inc, self._why(comp), LABELS[comp],
                                 int(self.q_base.value()) - 1, ref, self._prefer(comp, M))
            self.traces.set_time(self.cur_t)
        else:
            self.traces.set_included(inc, self._why(comp))

    # ============================================================ export
    def _export_data(self) -> Dict[str, dict]:
        comps = {}
        for c in self.follow:
            if c not in self.track["meas"] or not self._live(c):
                continue
            M, _idx = self._measured(c)             # every channel, every ratio pair
            live = self._live(c)
            wm = self._why(c)
            comps[c] = dict(label=LABELS[c], name=FILE_NAMES[c], M=M, cells=live,
                            include={k: int(k not in self.excl[c]) for k in live},
                            why={k: wm.get(k, "") for k in live}, qc=self.qc.get(c) or None,
                            seeds=[cell.get(c) or _blank() for cell in self.cells],
                            channel=int(self._rule(c).a), rois=self.track["rois"][c])
        return comps

    def _provenance(self, comps) -> dict:
        """What the exported files record about how they were made (provenance.py):
        the tracking rules, the tracker's own parameters, the .nd2 fingerprint."""
        names = list(self.exp.channels)
        trk = self.track or {}
        rules = [d for d in (trk.get("rules") or []) if isinstance(d, dict)] or \
            [r.to_dict(names) for c, r in self.rules.items() if c in comps]
        return dict(rules=rules, track_params=trk.get("params") or None,
                    fingerprint=self._fp(),
                    nd2_path=str(self.exp.nd2_path), comps=list(comps),
                    bg_auto=bool(self._bg_auto), redrawn=trk.get("redrawn") or None,
                    bg_kind=self._bg_kind, background=trk.get("background") or None,
                    bg_um2=(float(self.background.area) * self.exp.um_per_px ** 2
                            if self.background is not None else None),
                    session_id=str(getattr(self, "session_id", "") or ""),
                    detector=(self._detector_used.methods_text()
                              if getattr(self, "_detector_used", None) is not None else None))

    def _choose_outputs(self) -> None:
        if self.track is None:
            QMessageBox.information(self, "Track first", "Press TRACK & MEASURE first.")
            return
        comps = self._export_data()
        if not comps:
            QMessageBox.information(self, "Nothing to export", "No followed ROIs were measured.")
            return
        self.settings.baseline_timepoint = int(self.q_base.value())
        cat = catalog(comps, self.settings)
        std = standard(cat, {c: self._prefer_sheets(c, d["M"]) for c, d in comps.items()})
        keys_all = {it["key"] for it in cat}
        chosen = [k for k in (self.settings.export_list or []) if k in keys_all] or std
        # v2.2: a list remembered before the Prism graphs existed gets them with the .pzfx
        chosen += [k.replace("|prism", "|prismgraph") for k in chosen if k.endswith("|prism")
                   and k.replace("|prism", "|prismgraph") in keys_all
                   and k.replace("|prism", "|prismgraph") not in chosen
                   and k.replace("|prism", "|prismgraph") not in (self.settings.export_list or [])
                   and not getattr(self.settings, "seen_prismgraph", False)]
        self.settings.seen_prismgraph = True
        # v2.3: a list remembered before the Methods text existed gets it once
        if "*|methods" in keys_all and "*|methods" not in chosen \
                and not getattr(self.settings, "seen_methods", False):
            chosen.append("*|methods")
        self.settings.seen_methods = True
        dlg = ExportDialog(cat, chosen, std,
                           f"{Path(self.exp.out_dir).name} / Export_<date>_<time>", self,
                           template=self.settings.prism_template,
                           prefix=getattr(self, "prefix", "") or Path(self.exp.nd2_path).stem[:40],
                           graph_look=GS.style_summary(self.settings.graph_style),
                           graph_style=dict(self.settings.graph_style or {}))
        if dlg.exec() != QDialog.Accepted:
            return
        keys = dlg.keys()
        self.settings.prism_template = dlg.template
        if dlg.prefix() != getattr(self, "prefix", ""):
            self._mark_dirty()                  # the file name is part of the session
        self.prefix = dlg.prefix()
        self._export_context()                  # the graph title's {file}
        if dlg.chk_remember.isChecked():
            self.settings.export_list = keys
            save_settings(self.settings, self.exp)
        self._run_export(comps, keys)

    def _run_export(self, comps: Dict[str, dict], keys: List[str]) -> None:
        stem = clean_prefix(getattr(self, "prefix", "")) or Path(self.exp.nd2_path).stem[:40]
        if not self._paths_ok(stem, comps):
            return
        state, anchors, rois, bg, shape, t0 = self._roi_state("export")
        track = self.track                          # the tracking is saved with the ROIs
        prov = self._provenance(comps)              # rules, tracker parameters, fingerprint
        nd2 = str(self.exp.nd2_path)

        def roi_file(folder: Path) -> Path:         # runs in the export's thread
            used = save_roi_file(Path(folder) / f"{stem}_ROIs.npz", anchors, bg, shape,
                                 t0 + 1, state=state, comps=rois, track=track)
            record_run(nd2, used)                   # remembered as a run of this .nd2
            return used
        self._start(FuncJob(run_export, self.exp.out_dir, self.exp, self.settings, comps, keys,
                            src=self.src, background=self.background, t0=int(self.t0 or 0),
                            roi_file_fn=roi_file, prefix=stem, provenance=prov),
                    self._on_exported, f"Exporting {len(keys)} item(s)...")

    def _paths_ok(self, stem: str, comps: Dict[str, dict]) -> bool:
        """V3.0: with Windows' long paths off, warn before an export whose paths may
        be too long for Explorer / Excel (over ~250 characters)."""
        from ..export import longest_path
        from ..syscheck import long_paths_enabled
        if long_paths_enabled() is not False:
            return True
        n = longest_path(self.exp.out_dir, self.exp.nd2_path, stem,
                         [(d["label"], d["name"]) for d in comps.values()])
        if n <= 250:
            return True
        box = QMessageBox(QMessageBox.Warning, "Long file paths",
                          f"Some files of this export would have paths of about {n} characters. "
                          f"Windows' long paths are off on this computer (Help > Computer "
                          f"check...), so Explorer and Excel may not open them. Shorter: a "
                          f"shorter 'Name for the files' in the export list, a results folder "
                          f"higher up (start window), or shorter folder / movie names.",
                          parent=self)
        go = box.addButton("Export anyway", QMessageBox.AcceptRole)
        box.addButton(QMessageBox.Cancel)
        box.exec()
        return box.clickedButton() is go

    def _on_exported(self, out: dict) -> None:
        self._busy(False)
        self.progress.reset("Export finished.")
        self._exported = out["folder"]
        n = len(out["files"])
        from .. import outlog                    # V2.8: the log of every save
        outlog.record("export", Path(self.exp.nd2_path).name, out["files"],
                      f"Export of {Path(self.exp.nd2_path).name}")
        self._notify("Exported", f"{n} file(s) written to {out['folder']}", out["folder"])
        self.set_status(f"Exported {n} file(s) to {out['folder']}")
        self._autosave()                        # a milestone (if anything changed)
        self._update_next()

    # ======================================================== live graph
    def _export_stem(self) -> str:
        """Your name for the files (export dialog), else the .nd2 name (40 chars) -
        the same as the export uses."""
        return clean_prefix(getattr(self, "prefix", "")) or Path(self.exp.nd2_path).stem[:40]

    def _export_context(self) -> None:
        """The trace panel's graph title ({file}, {comp}) uses the export's names."""
        if hasattr(self, "traces"):
            self.traces.set_export_context(self._export_stem(), LABELS.get(self.view_comp, ""),
                                           str(Path(self.exp.out_dir) / "Graphs"))

    def _graph_style_changed(self, style: dict) -> None:
        """You changed the graph look ('As exported' view): the PNG export draws
        it, it is remembered for next time and kept with this session."""
        self.settings.graph_style = dict(style or {})
        save_settings(self.settings, self.exp)
        self._mark_dirty()

    def _prism_style_file(self) -> str:
        """Your own Prism style file (export dialog, 'Choose style...'), if usable."""
        tpl = str(getattr(self.settings, "prism_template", "") or "")
        return tpl if tpl.lower().endswith(".prism") and exists(tpl) else ""

    def _ask_save_graph(self, what: str, folder: str, name: str):
        """The 'Save this graph' dialog -> (folder, name, formats) or None (tests
        replace this)."""
        dlg = SaveGraphDialog(what, folder, name, self._graph_formats,
                              self._prism_style_file(), self,
                              graph_style=self.traces.style())
        if dlg.exec() != QDialog.Accepted:
            return None
        return dlg.folder(), dlg.name(), dlg.formats()

    def _export_graph(self, quantity: str) -> None:
        """'Save this graph...' in the trace panel: the quantity shown, included
        cells only, as .prism (data, titles and this look - the closest Prism
        look where Prism cannot draw it) / PNG / SVG (exactly as shown). Written in the background; nothing is replaced."""
        if self._busy_now():
            QMessageBox.information(self, "Still working", "Wait for the current job to "
                                                           "finish, or press Stop.")
            return
        comp = self.view_comp
        if self.track is None or comp not in self.track["meas"]:
            QMessageBox.information(self, "Nothing to save yet", "Press TRACK & MEASURE "
                                    "first: the graph is made from the tracked cells.")
            return
        x, y, names, xl, yl = self.traces.current_series()
        if y.ndim != 2 or y.shape[1] == 0:
            QMessageBox.information(self, "No cells included", "No cell is included in this "
                                    "graph - tick at least one cell in the list.")
            return
        style = self.traces.style()
        q = GS.quantity_title(quantity)
        n = int(y.shape[1])
        what = (f"{LABELS[comp]} - {q}: {n} included cell{'s' if n != 1 else ''}, "
                f"{GS.style_summary(style)}.")
        got = self._ask_save_graph(what, self._graph_folder or
                                   str(Path(self.exp.out_dir) / "Graphs"),
                                   graph_file_name(self._export_stem(), FILE_NAMES[comp], q))
        if not got:
            return
        folder, name, formats = got
        if not formats:
            return
        self._graph_folder, self._graph_formats = str(folder), list(formats)
        b = int(self.q_base.value())
        tpl = self._prism_style_file()
        from ..prismfile import template_takes_style
        shown = (GS.prism_summary(style) if template_takes_style(tpl)
                 else "the look of your own Prism template")
        notes = (f"{LABELS[comp]} - {Path(self.exp.nd2_path).name}. {n} included cells; X = "
                 f"time from the baseline (timepoint {b} = 0). Values are background-"
                 f"subtracted. The graph shows {shown} of the included cells (SEM = SD / "
                 f"sqrt(n), SD with n - 1). Saved from the trace panel by {APP_NAME} "
                 f"{__version__}.").replace("±", "+/-")
        self._start(FuncJob(save_graph_files, folder, name, formats, x, y, names, style, xl, yl,
                            self.traces.current_title(), q, notes=notes,
                            nd2_name=Path(self.exp.nd2_path).stem,
                            template=tpl or None),
                    self._on_graph_saved, "Saving the graph...")

    def _on_graph_saved(self, files) -> None:
        self._busy(False)
        files = [plain_path(f) for f in (files or [])]
        self._graph_saved = files
        from .. import outlog
        outlog.record("graph", Path(self.exp.nd2_path).name, files, "Save graph")
        self.progress.reset("Graph saved.")
        folder = str(Path(files[0]).parent) if files else ""
        self._notify("Graph saved", "; ".join(files), folder)
        self.set_status(f"Graph saved: {', '.join(Path(f).name for f in files)} in {folder}")
        self._update_next()

    # ========================================================= ROI files
    def _roi_state(self, kind: str = "saved"):
        """Everything an ROI file records (DESIGN_V23 Contract 2): the V2.2 keys
        (an older PeterPiper still reads the ROIs) plus where / when / with what it
        was made. kind: "session" (autosave) | "export" | "saved" (Save ROIs now)."""
        comps = {c: [cell.get(c) or _blank() for cell in self.cells] for c in COMPS
                 if self._live(c)}
        anchors = [next((cell[c] for c in COMPS if c in cell), _blank()) for cell in self.cells]
        e = self.exp
        names = list(e.channels)
        from .. import users                       # V2.9: whose analysis this is
        det = getattr(self, "_detector_used", None)
        state = dict(v2=True, version=__version__, app=APP_TITLE, user=users.current() or "",
                     detector=(det.to_dict() if det is not None else None),
                     nd2=Path(e.nd2_path).name, t0=self.t0,
                     bg_auto=self._bg_auto, bg_kind=self._bg_kind,
                     boundaries=self._boundaries_state(),
                     cells=[{c: int(getattr(r, "channel", 0)) for c, r in cell.items()}
                            for cell in self.cells],
                     excl={c: sorted(int(k) for k in v) for c, v in self.excl.items()},
                     channels=names, prefix=getattr(self, "prefix", ""),
                     follow=[[c, [e.channels[i] for i in v]] for c, v in self.follow.items()],
                     rules=[r.to_dict(names) for r in self.rules.values()],
                     # v2.3 (Contract 2)
                     saved=datetime.now().isoformat(timespec="seconds"),
                     session_id=self.session_id, nd2_path=str(e.nd2_path),
                     fingerprint=self._fp(),
                     exp=dict(um_per_px=float(e.um_per_px),
                              seconds_per_frame=float(e.seconds_per_frame),
                              n_timepoints=int(e.n_timepoints), width=int(e.width),
                              height=int(e.height), channels=names,
                              bit_depth=int(e.bit_depth)),
                     baseline=int(self.q_base.value()),
                     # as shown (within this movie's timepoints), so a reloaded
                     # session packs identically (V2.5 content key)
                     drift=[int(min(self.sp_dfrom.value(), self.sp_dto.value())),
                            int(max(self.sp_dfrom.value(), self.sp_dto.value()))],
                     track_params=(self.track or {}).get("params") or None,
                     track_settings=self._track_settings(),
                     graph_style=dict(getattr(self.settings, "graph_style", None) or {}),
                     kind=kind)
        if self._based_on:
            state["based_on"] = str(self._based_on)      # the earlier run you loaded
        return state, anchors, comps, self.background, (e.height, e.width), \
            int(self.t0 or 0)

    def _save_rois(self, silent: bool = False):
        if not any(self.cells):
            if not silent:
                QMessageBox.information(self, "No ROIs", "There are no ROIs to save yet.")
            return None
        state, anchors, comps, bg, shape, t0 = self._roi_state("saved")
        try:
            path = save_roi_file(roi_path(self.exp.out_dir, self.exp.nd2_path), anchors, bg,
                                 shape, t0 + 1, state=state, comps=comps, track=self.track)
        except Exception as exc:                                   # noqa: BLE001
            QMessageBox.critical(self, "Could not save the ROIs", error_text(exc))
            return None
        record_run(self.exp.nd2_path, path)
        if not silent:
            what = ("with their tracking (every ROI at every timepoint)" if self.track is not None
                    else "without tracking (press TRACK & MEASURE, then save again to keep it)")
            self._notify("ROIs saved", f"Saved {what}: {path} - reload it with 'Load saved "
                                       f"ROIs...' or File > Earlier analyses of this file.",
                         str(Path(path).parent))
        return path

    def _load_rois(self) -> None:
        if self._busy_now():
            return
        start = self.exp.out_dir if is_dir(self.exp.out_dir) else \
            str(Path(self.exp.nd2_path).parent)
        path, _ = QFileDialog.getOpenFileName(
            self, "Load saved ROIs", start,
            "PeterPiper ROI files (*_ROIs*.npz *_session_*.npz);;All .npz (*.npz)")
        if path:
            self._autosave()                    # what you have now is kept first
            self._load_roi_file(path)

    def _load_roi_file(self, path) -> None:
        try:
            anchors, bg, (h, w), seg = load_roi_file(path)
            state, comps = load_roi_state(path)
            track = load_roi_track(path, channels=list(self.exp.channels))
        except Exception as exc:                                   # noqa: BLE001
            QMessageBox.critical(self, "Could not read that ROI file", error_text(exc))
            return
        self._restoring = True                  # loading is not a change of yours
        try:
            problem = self._load_roi_parts(path, anchors, bg, (h, w), seg, state, comps, track)
        finally:
            self._restoring = False
        self._export_context()                  # its file name (graph title)
        if problem:                             # no usable tracking: offer to track now
            n = sum(1 for c in self.cells if any(k in self.follow for k in c))
            keep = ("It is then saved automatically with this run (in the PeterPiper_sessions "
                    "folder), so next time it loads with its tracking." if
                    getattr(self.settings, "autosave_sessions", True) else
                    "Use File > Save ROIs now (or export) afterwards to keep it.")
            ans = QMessageBox.question(
                self, "No tracking to show",
                f"{problem}\n\nUntil it is tracked, the outlines stay where they were drawn "
                f"at every timepoint.\n\nTrack now? It takes about {self._eta_s(n)} s. {keep}",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if ans == QMessageBox.Yes:
                self._track()

    def _load_roi_parts(self, path, anchors, bg, hw, seg, state, comps, track) -> Optional[str]:
        """Puts a loaded ROI file into the window; returns why its tracking
        cannot be used (None = used, or nothing to track)."""
        h, w = hw
        if (h, w) != (self.exp.height, self.exp.width):
            QMessageBox.warning(self, "Different image size",
                                f"That ROI file was made for a {w} x {h} image; this one is "
                                f"{self.exp.width} x {self.exp.height}.")
            return
        names = list(self.exp.channels)

        def chan(v, saved) -> int:
            if isinstance(v, str) and v in names:
                return names.index(v)
            i = int(v) if not isinstance(v, str) else 0
            if saved and i < len(saved) and saved[i] in names:
                return names.index(saved[i])
            return min(max(0, i), len(names) - 1)

        cells: List[Dict[str, Roi]] = []
        excl = {c: set() for c in COMPS}
        st = state or {}
        if st.get("v2"):
            saved = st.get("channels", [])
            for k, chmap in enumerate(st.get("cells", [])):
                cell = {}
                for c, chi in chmap.items():
                    if c in comps and k < len(comps[c]) and comps[c][k].area:
                        r = comps[c][k]
                        r.kind, r.source, r.channel = c, "manual", chan(chi, saved)
                        cell[c] = r
                cells.append(cell)
            for c, v in st.get("excl", {}).items():
                excl[c] = set(int(k) for k in v)
            t0 = st.get("t0")
            rows = st.get("follow")
            if st.get("prefix"):
                self.prefix = str(st["prefix"])          # the name you chose for the files
        else:                                              # v1.x files
            rws = st.get("rows", [])
            what = {"Nuclei": "nucleus", "Whole cell": "cell", "Cytoplasm": "cytoplasm",
                    "Mitochondria": "mito"}
            prim = what.get(rws[0][0], "nucleus") if rws else "nucleus"
            prim_ch = chan(rws[0][2], None) if rws else 0
            row_ch = {what.get(r[0]): chan(r[2], None) for r in rws}
            deleted = set(int(k) for k in st.get("deleted", []))
            for k, r in enumerate(anchors):
                cell = {}
                if k not in deleted and r.area:
                    r.kind, r.source, r.channel = prim, "manual", prim_ch
                    cell[prim] = r
                    for c, lst in comps.items():
                        if c in COMPS and c != prim and k < len(lst) and lst[k].area:
                            lst[k].kind, lst[k].source = c, "manual"
                            lst[k].channel = row_ch.get(c, prim_ch)
                            cell[c] = lst[k]
                cells.append(cell)
            t0 = st.get("test_t", (seg or 1) - 1)
            rows = None
        self._push_undo()
        # the earlier tracking goes first: rebuilding the rules redraws the view
        self.track, self.qc, self._was_tracked = None, {}, False
        self._stale_rules = False
        self._gate_why = {c: {} for c in COMPS}
        self.traces.clear()
        self.btn_export.setEnabled(False)
        self.cells, self.excl = cells, excl
        self.t0 = None if t0 is None or not any(cells) else int(min(max(0, t0),
                                                                    self.exp.n_timepoints - 1))
        if bg is not None:
            self.background, self._bg_auto = bg, bool(st.get("bg_auto", False))
            from .. import detectors as DT              # V3.0: the trained auto-detect used
            dd = st.get("detector")
            self._detector_used = DT.Detector.from_dict(dd) if isinstance(dd, dict) else None
            k = str(st.get("bg_kind") or "")
            self._bg_kind = k if k in ("auto", "click", "hand") else \
                ("auto" if self._bg_auto else "click")
        # V2.5 tracker boundary lines (older files have none)
        self.boundaries = self._boundaries_from(st.get("boundaries"), len(cells))
        self._auto_batch = None
        self.auto_row.hide()
        present = [c for c in COMPS if any(c in cell for cell in cells)]
        # v2.3 files keep their rules; older files: one ONLY rule per followed
        # compartment, on the channel most of its ROIs were drawn on
        rules: List[TrackRule] = []
        for d in (st.get("rules") if isinstance(st.get("rules"), list) else []):
            r = TrackRule.from_dict(d, names)
            if r is not None and r.comp in FOLLOW and r.comp not in {q.comp for q in rules}:
                rules.append(r)
        saved_rules = bool(rules)
        if not rules:
            follow = [[c, ch] for c, ch in rows if c in FOLLOW] if rows else \
                [[c, []] for c in present]
            rules = default_rules(follow, cells, names)
        mixed = []
        for r in rules:                     # one kind of ROI drawn on several channels
            chs = [int(getattr(cell[r.comp], "channel", r.a)) for cell in cells if r.comp in cell]
            if len(set(chs)) > 1:
                count = ", ".join(f"{names[i]} for {chs.count(i)}" for i in sorted(set(chs))
                                  if 0 <= i < len(names))
                mixed.append(f"Your {LABELS[r.comp].lower()} ROIs were drawn on different "
                             f"channels ({count}). This version draws and follows each kind of "
                             f"ROI on one image: they will be followed on {names[int(r.a)]} "
                             + ("(their saved tracking rule)" if saved_rules else
                                "(the channel most were drawn on)")
                             + " - change the rule in step 1 if that is wrong.")
        if rules:
            self._set_rules(rules, quiet=True)
        self._restore_view_state(st)            # baseline, drift window, graph look
        if self.t0 is not None:
            self.slider.setValue(self.t0 + 1)
        self._refresh()
        n = sum(1 for c in self.cells if c)
        other = st.get("nd2") and st.get("nd2") != Path(self.exp.nd2_path).name
        # the saved tracking is used when it fits this movie and these cells;
        # otherwise say exactly why (roifile.track_problem)
        problem = track_problem(track, self.exp.n_timepoints, len(self.cells),
                                list(self.follow), st, list(self.exp.channels)) if n else None
        if n and problem is None and track is not None:
            problem = self._other_movie(st)     # measured on other pixels: not used here
        ok_track = n > 0 and problem is None
        if ok_track:                                   # the saved tracking: no need to re-track
            self._on_tracked(track, loaded=True)
        if self._session_file is not None:
            # this window already saved a session file (the work you had before
            # loading): your changes to the run just loaded go into a NEW one, so
            # that earlier work is never replaced
            old = self.session_id
            self.session_id = history.new_session_id()
            if self.session_id == old:
                self.session_id = f"{old}_2"
            self._session_file = None
        self._based_on = str(path)
        self._dirty = False                            # nothing of yours to save yet
        try:                                           # V2.5: saved again only if it changes
            self._last_key = (read_summary(path) or {}).get("content_key") or None
        except Exception:                                          # noqa: BLE001
            self._last_key = None
        self._save_timer.stop()
        self.set_status(f"Loaded {n} cells from {Path(path).name}"
                        + (f" (saved for {st['nd2']})" if other else "")
                        + (" WITH their tracking - scrub or Play to check the outlines, then "
                           "export (track again only if you change ROIs)." if ok_track else
                           (". " + problem if problem else ". Check them, then TRACK & MEASURE."))
                        + "".join("  " + m for m in mixed))
        if problem and n:
            self.lbl_track.setText(problem)
        if n and self.background is not None and self._bg_auto:
            self._flag_auto_background()
        return problem if n else None

    def _flag_auto_background(self) -> None:
        """V3.0: a run whose background region was placed automatically (before V3.0,
        or by Batch analysis) - say so and offer to place it again by hand."""
        msg = ("The background region of this run was placed automatically - check it (green "
               "box): it may sit on cells. If it does, place it again (Background > Add / Draw "
               "by hand, or right-click an empty area) and TRACK & MEASURE again.")
        self.set_status(self.lbl_status.text() + "  " + msg)
        W.Toast(self, "Check the background", msg, ("Place it again", self._pick_background),
                ms=15000)

    def _other_movie(self, st: dict) -> Optional[str]:
        """Why an ROI file's saved tracking belongs to ANOTHER movie (None = this
        one): its outlines and measurements were made on that movie's pixels, so
        they must not be shown or exported as this movie's. Decided by the .nd2
        fingerprint when the file has one (a renamed or moved copy of the same
        movie is fine), else by the .nd2 name (files before v2.3)."""
        saved_fp = st.get("fingerprint") if isinstance(st.get("fingerprint"), dict) else {}
        mine = self._fp()
        if saved_fp.get("quick") and mine.get("quick"):
            if history.same_file(saved_fp, mine):
                return None
        elif not (st.get("nd2") and st.get("nd2") != Path(self.exp.nd2_path).name):
            return None
        what = f"another movie ({st['nd2']})" if st.get("nd2") and \
            st.get("nd2") != Path(self.exp.nd2_path).name else \
            "a different version of this movie (same name, different contents)"
        return (f"The tracking saved in this file was made on {what}: its outlines and "
                f"measurements belong to that movie, so they are not used here. The ROIs "
                f"are loaded - press TRACK & MEASURE to measure them on this movie.")

    def _restore_view_state(self, st: dict) -> None:
        """v2.3 files: the baseline, drift window and graph look they were saved with."""
        T = max(1, self.exp.n_timepoints)
        b = st.get("baseline")
        if isinstance(b, (int, float)) and not isinstance(b, bool):
            b = int(min(max(1, int(b)), T))
            self.q_base.setValue(b)
            self.settings.baseline_timepoint = b
        d = st.get("drift")
        if isinstance(d, (list, tuple)) and len(d) == 2:
            try:
                a, z = (int(min(max(1, int(v)), T)) for v in d)
                self.sp_dfrom.setValue(a)
                self.sp_dto.setValue(z)
                self.settings.drift_from, self.settings.drift_to = min(a, z), max(a, z)
            except (TypeError, ValueError):
                pass
        ts = st.get("track_settings")
        if not isinstance(ts, dict):              # older files: what their tracking used
            tp = st.get("track_params") if isinstance(st.get("track_params"), dict) else {}
            ts = {k: tp.get(k) for k in ("max_move_um", "gate_snr", "overlap_k")}
            ts["track_size_tol"] = tp.get("size_tol")
        self._set_track_settings(ts)
        gs = st.get("graph_style")
        if isinstance(gs, dict) and gs:
            self.settings.graph_style = dict(gs)
            if hasattr(self.traces, "set_style"):
                self.traces.set_style(dict(gs))

    # ===================================================== session memory
    def _fp(self) -> dict:
        """The .nd2's fingerprint (history.nd2_fingerprint), worked out once."""
        if not self._fingerprint or not self._fingerprint.get("quick"):
            self._fingerprint = history.nd2_fingerprint(self.exp.nd2_path)
        return dict(self._fingerprint)

    def _mark_dirty(self) -> None:
        """Something of yours changed: autosave a moment after the last change
        (so not on every wheel notch). Loading a file is not a change."""
        if self._restoring:
            return
        self._dirty = True
        if getattr(self.settings, "autosave_sessions", True):
            self._save_timer.start()                  # restarts: debounced

    def _autosave(self, even_if_busy: bool = False) -> bool:
        """Save this window's session file now if anything changed (packed here,
        written in the background). True if a save was started."""
        if not getattr(self.settings, "autosave_sessions", True) or not self._dirty:
            return False
        if self._busy_now() and not even_if_busy:
            self._save_timer.start()                  # after the running job
            return False
        if not any(self.cells):
            return False                              # nothing to keep
        t = time.perf_counter()
        try:
            if self._session_file is None:            # first save: a name of our own
                base, i = self.session_id, 2
                path = history.session_path(self.exp.out_dir, self.exp.nd2_path, self.session_id)
                while exists(path):
                    self.session_id = f"{base}_{i}"
                    i += 1
                    path = history.session_path(self.exp.out_dir, self.exp.nd2_path,
                                                self.session_id)
                self._session_file = path
            state, anchors, comps, bg, shape, t0 = self._roi_state("session")
            blob = session_blob(anchors, bg, shape, t0 + 1, state=state, comps=comps,
                                track=self.track)
            import json as _json
            key = str(_json.loads(str(blob["state_json"])).get("content_key") or "")
        except Exception as exc:                                   # noqa: BLE001
            self.lbl_saved.setText(f"Could not save your work automatically: {error_text(exc)}")
            return False
        self._dirty = False
        self._save_timer.stop()
        if key and key == self._last_key:
            return False          # V2.5: exactly what was saved last (or loaded): no new file
        self._last_key = key or None
        self._save_log.append(dict(pack_ms=(time.perf_counter() - t) * 1000.0,
                                   tracked=self.track is not None, n=len(self.cells)))
        self._writer.submit(self._session_file, blob, self.exp.nd2_path)
        return True

    def _on_session_saved(self, path: str, err: str, ms: float) -> None:
        for d in reversed(self._save_log):
            if "write_ms" not in d:
                d["write_ms"] = ms
                break
        if err:
            self.lbl_saved.setText(f"Could not save your work automatically ({err}). Use "
                                   f"File > Save ROIs now.")
            return
        with_trk = "with the tracking" if self._save_log and self._save_log[-1].get("tracked") \
            else "ROIs only - not tracked yet"
        self.lbl_saved.setText(f"Your work was saved automatically at "
                               f"{datetime.now():%H:%M:%S} ({with_trk}).")
        self.lbl_saved.setToolTip(path)

    def _saved_text(self) -> str:
        if getattr(self.settings, "autosave_sessions", True):
            return ("Your work is saved automatically as you go (PeterPiper_sessions in the "
                    "results folder) - File > Earlier analyses of this file... brings it back.")
        return ("Automatic saving is off (File > Save my work automatically). Export, or "
                "File > Save ROIs now, keeps your ROIs and tracking.")

    def _autosave_toggled(self, on: bool) -> None:
        self.settings.autosave_sessions = bool(on)
        save_settings(self.settings, self.exp)
        self.lbl_saved.setText(self._saved_text())
        if on:
            self._dirty = self._dirty or bool(any(self.cells))
            self._mark_dirty()

    def _ask_toggled(self, on: bool) -> None:
        self.settings.ask_previous_runs = bool(on)
        save_settings(self.settings, self.exp)

    def showEvent(self, ev) -> None:                               # noqa: N802
        super().showEvent(ev)
        if not self._offered:
            QTimer.singleShot(300, self._offer_previous_runs)

    def _offer_previous_runs(self) -> None:
        """Once, right after the window opens: if this .nd2 was analysed before,
        offer the earlier runs (or a fresh start)."""
        if self._offered:
            return
        if not self._bg_tried or self._busy_now():
            QTimer.singleShot(300, self._offer_previous_runs)     # after the background
            return
        self._offered = True
        if not getattr(self.settings, "ask_previous_runs", True) or any(self.cells):
            return
        runs = self._previous_runs()
        if not runs:
            return
        path = self._ask_previous_run(runs)
        if path:
            self._load_roi_file(path)
        else:
            self.set_status(f"Fresh analysis of {Path(self.exp.nd2_path).name} - the earlier "
                            f"runs stay as they were (File > Earlier analyses of this file... "
                            f"lists them).")

    def _previous_runs(self) -> List["history.RunInfo"]:
        """Earlier runs of this .nd2 (history.find_previous_runs), without this
        window's own session file."""
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.progress.busy("Looking for earlier analyses of this file...")
        QApplication.processEvents()
        try:
            runs = W.run_with_progress(            # V2.9: a bar, not a frozen window
                self, "Looking for earlier analyses of this file",
                lambda _p: history.find_previous_runs(self.exp.nd2_path, self.exp.out_dir,
                                                      (self.exp.height, self.exp.width),
                                                      self.exp.n_timepoints))
            self._fp()                                # cached by now: costs nothing
        finally:
            self.progress.unbusy()
            self.progress.reset("Ready.")
            QApplication.restoreOverrideCursor()
        own = _same_path_key(self._session_file) if self._session_file else None
        return [r for r in runs if own is None or _same_path_key(r.path) != own]

    def _ask_previous_run(self, runs, menu: bool = False) -> Optional[str]:
        """The 'analysed before' list; returns the ROI / session file to load
        (None = start fresh / keep what you have). Tests replace this."""
        dlg = PreviousRunsDialog(runs, Path(self.exp.nd2_path).name, self, menu=menu)
        ok = dlg.exec() == QDialog.Accepted
        if dlg.dont_ask():
            self.settings.ask_previous_runs = False
            self.act_ask.setChecked(False)            # also saves the settings
        return dlg.selected_path() if ok else None

    def _earlier_analyses(self) -> None:
        """File > Earlier analyses of this file..."""
        if self._busy_now():
            return
        runs = self._previous_runs()
        if not runs:
            QMessageBox.information(
                self, "No earlier analyses found",
                f"No earlier ROI files or autosaved sessions were found for "
                f"{Path(self.exp.nd2_path).name}.\n\nLooked in the results folder "
                f"({self.exp.out_dir}), next to the .nd2 (OUTPUT_ folders and older results "
                f"folders) and in this computer's list of earlier runs. A file somewhere "
                f"else can still be opened with 'Load saved ROIs...'.")
            return
        path = self._ask_previous_run(runs, menu=True)
        if path:
            self._autosave()                          # what you have now is kept first
            self._load_roi_file(path)

    # ============================================================== misc
    def _export_tiffs(self) -> None:
        n = self.exp.n_timepoints * self.exp.n_channels
        self._start(FuncJob(export_tiffs, self.src, self.exp), self._on_tiffs_done,
                    f"Writing {n} TIFF files...")

    def _on_tiffs_done(self, folder) -> None:
        self._busy(False)
        self.progress.reset("TIFF export finished.")
        self.set_status(f"Raw TIFFs written to {folder}")
        self._update_next()

    def _notify(self, title: str, text: str, folder: str = "") -> None:
        """V2.9: a quiet banner that fades away (with Open folder), not an OK box."""
        act = None
        if folder:
            act = ("Open folder", lambda f=folder: QDesktopServices.openUrl(QUrl.fromLocalFile(f)))
        W.Toast(self, title, text, act)

    def _go_back(self) -> None:
        self.go_back = True
        self.close()
        if self.isVisible():
            self.go_back = False

    def _help(self) -> None:
        QMessageBox.information(
            self, "How to use this window",
            "1  TRACKING RULES - one rule per kind of ROI: 'Auto-detect [Nucleus] using "
            "[GFP]' (the main channel), with optional helper channels ('+ helper channel', "
            "e.g. 'helped by Cy5'):\n"
            "    A helper CHOOSES the cells: AUTO-DETECT picks only cells with real signal "
            "in every helper (at least 'Helper signal needed' x its noise; cells you click "
            "yourself are always kept, with a note).\n"
            "    A helper HELPS FOLLOW the cell: the outline is drawn on the main channel "
            "plus the helpers (the main channel counts twice as much as each helper), and "
            "it never reaches more than 1 µm past what the main channel alone would draw "
            "(Show > 'Tracking image' shows that combined image).\n"
            "    Runs made before V3.0 with ONLY / WITH / AND / IF load and are applied "
            "exactly; a note says what the older rule did. Changing it turns it into the "
            "new form (track again).\n"
            "    'Train auto-detect from my runs...' (under AUTO-DETECT) learns from runs "
            "whose ROIs you drew yourself which cells you pick, and saves a button.\n"
            "Cells move with the first rule's compartment. Whatever the rules, EVERY channel "
            "is measured in EVERY ROI (all ratios are available). Changing a rule after "
            "tracking means tracking again.\n\n"
            "2  ADD ROIs - pick the Compartment (the line under it says which image it is "
            "drawn and followed on), turn on ADD "
            "(it turns green; click it again to stop) and click each one: the ROI is drawn "
            "around your click (scroll right after to make it bigger / smaller). REMOVE (red) "
            "deletes ROIs; DRAW BY HAND (orange) for awkward shapes; RESIZE (purple) any cell "
            "with the wheel, no limit; SPLIT (teal) - drag a line across an ROI to cut it into "
            "two cells; ADD TO CELL (pink) - click a cell, then its missed parts. ROIs on the "
            "same cell share one number; right-click an ROI to "
            "move it to another cell. Undo (Ctrl+Z) takes anything back.\n\n"
            "3  TRACK & MEASURE - every ROI is redrawn at every timepoint from that frame's "
            "pixels (on its rule's first channel) and every channel is measured in it (mean = "
            "sum of its pixels / its pixel count); its size never leaves the 'Size may change "
            "by' limit of what you drew (0 % = exactly the pixel count you drew), and two "
            "cells' ROIs never overlap. TRACKER BOUNDARY: click a cell, then click the points "
            "of a line and double-click - that cell's ROIs never cross it (orange; right-click "
            "the cell or 'Remove lines' to delete them).\n"
            "    BACKGROUND - you place it: choose Compartment 'Background' and Add (a "
            "60 µm square where you click) or Draw by hand (draw around a region). Cells inside are fine (their autofluorescence is "
            "background). Every pixel of the region is used at every timepoint; after "
            "tracking you are told if the background jumps (e.g. a bright or dead cell passing "
            "through) or drifts, or if measured cells lie in it, and can redraw it.\n\n"
            "4  CHECK - Play (space bar) to watch the outlines follow the cells; tick / "
            "untick cells in the list beside the traces. Scroll on the plot to zoom.\n"
            "    The Traces panel has two views. 'Check cells': every cell in its own "
            "colour, excluded ones grey - for deciding which cells to keep. 'As exported': "
            "the LIVE GRAPH - only the included cells, exactly as the PNG graphs will look. "
            "Choose the look there (Look, error SEM / SD / 95% CI, bars or shaded band, each "
            "cell, mean colour; More style... for titles, axis titles, axis ranges, font "
            "size); it is remembered. 'Save this graph...' saves the graph shown as a Prism "
            "file (.prism), a 300 dpi PNG and / or an SVG. The Prism files get the same "
            "look (error type, colours, lines, symbols, each cell, titles, axis ranges, "
            "font size). The few things Prism cannot draw (shaded band, hidden mean, dashed "
            "line at time 0) are marked *: the .prism file then uses the closest Prism look "
            "(e.g. error bars instead of a band) and a note under the controls says so.\n\n"
            "5  EXPORT - put what you want on your export list; only that is written, into "
            "a new folder inside OUTPUT_<file name>. Time 0 = the baseline timepoint. "
            "'Methods (text file)' writes a ready-to-edit methods paragraph with every "
            "setting used.\n\n"
            "YOUR WORK IS KEPT - the ROIs, the tracking (every ROI at every timepoint), "
            "include / exclude, baseline and graph look are saved automatically as you work "
            "(a file in PeterPiper_sessions inside the results folder; File > Save my work "
            "automatically turns this off). When you open an .nd2 that was analysed before, "
            "the earlier runs are listed: load one to check its tracking again (scrub or Play "
            "- the outlines follow the cells as they were tracked) or start fresh. File > "
            "Earlier analyses of this file... lists them at any time. ROI files from before "
            "V2.2 hold no tracking: you are asked whether to track them now.")

    def closeEvent(self, ev) -> None:                              # noqa: N802
        if self._busy_now():
            ans = QMessageBox.question(self, "A job is still running", "Stop it and close?")
            if ans != QMessageBox.Yes:
                ev.ignore()
                return
            # cancel, and wait until the job has really stopped: it reads the
            # .nd2, which is closed below
            self.set_status("Stopping the running job before closing ...")
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                stopped = self._runner.stop_and_wait(120.0, QApplication.processEvents)
            finally:
                QApplication.restoreOverrideCursor()
            if not stopped:
                QMessageBox.warning(self, "Still stopping",
                                    "The running job has not stopped yet. Wait a moment and "
                                    "close the window again.")
                ev.ignore()
                return
        self._play.stop()
        self._save_timer.stop()
        self._autosave(even_if_busy=True)          # the last changes (if any)...
        self._writer.flush()                       # ...are on disk before the window goes
        try:
            save_settings(self.settings, self.exp)
        except Exception:                                          # noqa: BLE001
            pass
        self.store.close()
        self.src.close()
        super().closeEvent(ev)
