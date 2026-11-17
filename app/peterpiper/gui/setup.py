"""
The start screen (PeterPiper 1.1): a few big choices -

    Analyse movies            one .nd2, or several at once (they become your queue)
    Continue your queue       the next movie still to do (only when there is one)
    Compare / average runs    runs you saved, no image needed

- then the chosen movie with the two numbers every size and time depends on
(pixel size, frame interval), its stage position and channel names and where
the results go; your recent analyses (open one again in the analysis window, or
its results folder) and the queue; and a row of small links (Saved files,
Storage & cloud, More, text size, theme). It fits a 1366 x 768 screen without
scroll bars and opens maximized (app.py).

Everything about WHAT to find and measure is set in the analysis window, next
to the image, where its effect can be seen - so it is not asked here. Nothing
is typed as a path - files and folders are chosen with a browser.

prepare(nd2) does what 'Open' does here, without the window: app.py uses it to
open the next movie of the queue, or a run chosen elsewhere, directly - unless
the movie needs a look first (NeedsCheck: pixel size or frame interval missing,
uneven gaps, several stage positions ...); then this window opens with it.

Hand-over after accept(): either open_request = {"nd2": path, "run": file or
None} (app.py opens that movie with prepare() and loads that run), or
result_tuple = (source, experiment, settings) plus open_run (a run to load).

BLOCK: another acquisition parameter belongs in _build_movie_box(); add the
matching field to Experiment first.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, List, Optional

import numpy as np

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QFont, QPainter
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDoubleSpinBox,
                               QFileDialog, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QMenu, QMessageBox, QPushButton, QSizePolicy,
                               QTabWidget, QToolButton, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from .. import APP_NAME, __version__
from .. import batchqueue
from ..config import Experiment, Settings, load_settings, save_settings
from ..nd2io import ND2Source, describe, open_source
from ..safety import (error_text, folder_problem, long_path, looks_read_only,
                      validate_filename_part)
from . import widgets as W

RECENT_N = 8                     # recent analyses listed
STATUS_WORDS = {"todo": "to do", "saved": "saved", "exported": "exported ✓",
                "skipped": "skipped"}
KIND_WORDS = {"saved": "Saved", "session": "Autosave", "export": "Export"}


# =========================================================== opening a movie
class NeedsCheck(Exception):
    """prepare(): the movie can be opened, but something about it needs a look
    first (reasons: short sentences) - the start screen opens with it."""

    def __init__(self, nd2: str, reasons: List[str], run: Optional[str] = None) -> None:
        super().__init__(" ".join(reasons))
        self.nd2, self.reasons, self.run = str(nd2), list(reasons), run

    @property
    def text(self) -> str:
        return " ".join(self.reasons)


def open_movie(path: str, parent: Optional[QWidget] = None):
    """Open an .nd2 in the background (a bar for big files) and read its first
    frame for the analysis window. Raises when it cannot be read or is empty."""
    name = Path(path).name
    size_gb = os.stat(long_path(path)).st_size / 1e9

    def opening(progress):                         # V2.9: in the background, with a bar
        progress(None, "Reading the file header...", detail=f"{path} ({size_gb:.1f} GB)")
        s_ = open_source(path)
        progress(None, "Reading the first frame...", detail=f"{path} ({size_gb:.1f} GB)")
        try:                                       # the analysis window shows it at once
            s_._pd4_first = (0, np.asarray(s_.frame(0)))
        except Exception:                                          # noqa: BLE001
            pass
        return s_
    src = W.run_with_progress(parent, f"Opening {name}", opening, delay_ms=150)
    if src.n_timepoints < 1 or not src.channels:
        src.close()
        raise ValueError("This file has no channels or timepoints.")
    return src


def default_results_folder(nd2_path: str) -> tuple:
    """(folder, moved): OUTPUT_<movie>/<user>, or - 1.0.3, when the movie's drive
    is read-only - the same under the PeterPiper results folder (moved=True)."""
    from .. import users
    out = users.output_dir(nd2_path)
    if looks_read_only(out):
        return users.fallback_output_dir(nd2_path), True
    return out, False


def channel_name_problem(names) -> str:
    """'' if the names can be Excel sheet / file names; else why not."""
    try:
        for n in names:
            validate_filename_part(n, "Channel name")
    except ValueError as exc:
        return str(exc)
    if len(set(n.lower() for n in names)) != len(names):
        return ("Two channels have the same name - give every channel a different name "
                "(they become the names of the Excel sheets).")
    return ""


def metadata_problems(src, exp: Experiment) -> List[str]:
    """What should be looked at before this movie is analysed ([] = nothing):
    the pixel size or frame interval missing from the file, uneven gaps between
    timepoints, several stage positions, channel names that cannot be used."""
    out = []
    um = float(getattr(exp, "um_per_px", 0) or 0)
    if um <= 0 or abs(um - 1.0) < 1e-9:
        out.append("The pixel size was not found in the file (1.0 µm/px is only a "
                   "stand-in) - every size and area depends on it.")
    if int(exp.n_timepoints or 0) > 1 and float(exp.seconds_per_frame or 0) <= 0:
        out.append("The frame interval was not found in the file - every time depends on it.")
    gaps = exp.gaps_text()
    if gaps:
        out.append(f"The gaps between timepoints are uneven ({gaps}).")
    n_pos = int(getattr(src, "n_positions", 1) or 1)
    if n_pos > 1:
        out.append(f"The file holds {n_pos} stage positions - choose which one to analyse.")
    why = channel_name_problem(list(src.channels))
    if why:
        out.append(why)
    return out


def fit_settings(s: Settings, e: Experiment) -> Settings:
    """The saved settings, made valid for THIS movie (everything else is chosen in
    the analysis window)."""
    T, C = max(1, int(e.n_timepoints)), max(1, len(e.channels))
    s.seg_timepoint = int(min(max(1, s.seg_timepoint), T))
    s.baseline_timepoint = int(min(max(1, s.baseline_timepoint), T))
    s.ref_channel = int(min(max(0, s.ref_channel), C - 1))
    return s


# 1.0.3: a results folder that cannot be written (e.g. a Windows-formatted drive
# on a Mac) - say why and offer another place, instead of an error later
def ask_results_folder(parent, folder: str, why: str, alt: str) -> str:
    """'alt', 'pick' or '' (cancel)."""
    same = os.path.normcase(os.path.abspath(folder)) == os.path.normcase(os.path.abspath(alt))
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Warning)
    box.setWindowTitle("The results cannot be saved there")
    box.setText(f"PeterPiper cannot write the results in\n{folder}\n\nbecause {why}.")
    box.setInformativeText(
        "The movie is only read, so it can stay where it is - only the results need "
        "a folder that can be written."
        + ("" if same else f"\n\nSuggested: {alt}"))
    b_alt = None if same else box.addButton("Save the results there", QMessageBox.AcceptRole)
    b_pick = box.addButton("Choose another folder...", QMessageBox.ActionRole)
    box.addButton(QMessageBox.Cancel)
    box.setDefaultButton(b_alt or b_pick)
    box.exec()
    hit = box.clickedButton()
    return "alt" if (b_alt is not None and hit is b_alt) else "pick" if hit is b_pick else ""


def results_folder_ok(e, ask: Callable[[str, str, str], str], parent=None,
                      on_change: Optional[Callable[[str], None]] = None) -> bool:
    """True once e.out_dir can be written (asking with ask(folder, why, alt) when it
    cannot); False when the user cancels."""
    from .. import users
    while True:
        why = folder_problem(e.out_dir)
        if why is None:
            return True
        alt = users.fallback_output_dir(e.nd2_path)
        choice = ask(e.out_dir, why, alt)
        if choice == "alt":
            folder = alt
        elif choice == "pick":
            folder = QFileDialog.getExistingDirectory(
                parent, "Select the results folder", str(users.results_home().parent))
            if not folder:
                continue
        else:
            return False
        e.out_dir = folder
        if on_change is not None:
            on_change(folder)


def prepare(nd2_path: str, parent: Optional[QWidget] = None,
            ask: Optional[Callable[[str, str, str], str]] = None, run: Optional[str] = None):
    """
    Open a movie the way 'Open' on the start screen does, without the window:
    the file, its metadata, the results folder (OUTPUT_<movie>/<user>; the
    writability check with the same question as the start screen), stage
    position 1, the channel names from the file and the saved settings made
    valid for it. Returns (source, experiment, settings).
    Raises NeedsCheck (the file is closed again) when the metadata needs a look
    or no writable results folder was chosen, and the reading error when the
    file cannot be opened.
    """
    path = str(nd2_path)
    if not os.path.exists(long_path(path)):
        raise FileNotFoundError(f"The movie is not there (moved, renamed, or its drive is "
                                f"not plugged in):\n{path}")
    src = open_movie(path, parent)
    try:
        out, _moved = default_results_folder(path)
        exp = describe(src, out_dir=out)
        why = metadata_problems(src, exp)
        if why:
            raise NeedsCheck(path, why, run)
        if getattr(src, "position", 0):
            src.position = 0
        exp.channels = list(src.channels)
        exp.export_tiffs = False                  # chosen next to Save instead
        s, _extras = load_settings()
        fit_settings(s, exp)
        asker = ask or (lambda f, w, a: ask_results_folder(parent, f, w, a))
        if not results_folder_ok(exp, asker, parent):
            raise NeedsCheck(path, ["The results folder cannot be written - choose "
                                    "another one."], run)
        save_settings(s, exp)
        return src, exp, s
    except BaseException:
        src.close()
        raise


# ========================================================== recent analyses
def recent_analyses(limit: int = RECENT_N, scan: int = 300, progress=None) -> List[dict]:
    """The newest analyses of this user, one per movie, newest first, from the run
    list (history's index; only read): [{nd2, nd2_name, run, saved, kind, n_cells,
    tracked, note, folder, movie_here}]. At most `scan` run files are looked at.
    Never raises."""
    from .. import history as H
    from .. import users
    try:
        idx = H._load_index()
    except Exception:                                              # noqa: BLE001
        return []
    cands = []
    for key, ent in idx.items():
        for r in ent.get("runs", []):
            cands.append((str(r.get("saved") or r.get("recorded") or ""), key, r))
    cands.sort(key=lambda c: c[0], reverse=True)
    out, seen = [], set()
    look = cands[:max(scan, limit)]
    for i, (saved, key, r) in enumerate(look):
        if key in seen:
            continue
        if progress is not None:                   # 1.2: what is being looked at
            progress(i / max(1, len(look)), "Finding your recent analyses",
                     detail=f"run {i + 1} of {len(look)} - {r.get('path', '')}")
        try:
            rp = H.resolve(r["path"])
            if not os.path.exists(long_path(rp)):
                continue
            try:
                from ..roifile import read_summary
                summ = read_summary(rp) or {}
            except Exception:                                      # noqa: BLE001
                summ = {}
            # whose: the user saved in the file, else its OUTPUT_<movie>/<user> folder
            if not users.is_mine(rp, summ.get("user") or None):
                continue
            ent = idx[key]
            paths = [str(p) for p in ent.get("paths", []) if isinstance(p, str)]
            here = [p for p in reversed(paths) if os.path.exists(long_path(p))]
            nd2 = here[0] if here else (paths[-1] if paths else str(summ.get("nd2_path") or ""))
            note = str(summ.get("note") or "")
        except Exception:                                          # noqa: BLE001
            continue
        seen.add(key)
        out.append(dict(nd2=nd2, nd2_name=str(ent.get("nd2_name") or Path(nd2).name),
                        run=str(rp), saved=saved, kind=str(r.get("kind") or ""),
                        n_cells=int(r.get("n_cells") or 0), tracked=bool(r.get("tracked")),
                        note=note, folder=str(Path(rp).parent),
                        movie_here=bool(nd2) and os.path.exists(long_path(nd2))))
        if len(out) >= limit:
            break
    return out


# ================================================================== widgets
class ElideLabel(QLabel):
    """One line of plain text, shortened with '...' when there is no room (file
    names, folders) - it never makes the window wider. text() and the tooltip
    are the whole text."""

    def __init__(self, text: str = "", muted: bool = False,
                 mode: Qt.TextElideMode = Qt.ElideMiddle) -> None:
        super().__init__()
        self._mode = mode
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        if muted:
            self.setProperty("muted", True)
        self.setText(text)

    def setText(self, text: str) -> None:                     # noqa: N802
        super().setText(str(text))
        self.setToolTip(str(text))

    def minimumSizeHint(self) -> QSize:                       # noqa: N802
        return QSize(30, self.fontMetrics().height())

    def sizeHint(self) -> QSize:                              # noqa: N802
        return QSize(min(400, self.fontMetrics().horizontalAdvance(self.text()) + 4),
                     self.fontMetrics().height())

    def paintEvent(self, ev) -> None:                         # noqa: N802
        p = QPainter(self)
        r = self.contentsRect()
        txt = self.fontMetrics().elidedText(self.text().replace("\n", "  "), self._mode,
                                            r.width())
        self.style().drawItemText(p, r, int(Qt.AlignLeft | Qt.AlignVCenter), self.palette(),
                                  self.isEnabled(), txt, self.foregroundRole())


class BigChoice(QPushButton):
    """A big button with a title and a short line under it (the start screen's
    main choices). text() is the title."""

    def __init__(self, title: str, sub: str, on_click: Callable, tip: str = "") -> None:
        super().__init__()
        self._title = QLabel(title)
        self._title.setProperty("role", "title")
        self._sub = ElideLabel(sub, muted=True, mode=Qt.ElideRight)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 10, 18, 10)
        lay.setSpacing(2)
        for lab in (self._title, self._sub):
            lab.setAttribute(Qt.WA_TransparentForMouseEvents)
            lay.addWidget(lab)
        self.setToolTip(tip)
        self.setAccessibleName(title)
        self.setAutoDefault(False)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.clicked.connect(lambda _=False: on_click())

    def text(self) -> str:                                    # noqa: D401
        return self._title.text()

    def sub_text(self) -> str:
        return self._sub.text()

    def set_texts(self, title: Optional[str] = None, sub: Optional[str] = None) -> None:
        if title is not None:
            self._title.setText(title)
            self.setAccessibleName(title)
        if sub is not None:
            self._sub.setText(sub)

    def sizeHint(self) -> QSize:                              # noqa: N802
        h = self.layout().sizeHint()
        return QSize(max(220, h.width()), h.height() + 4)

    def minimumSizeHint(self) -> QSize:                       # noqa: N802
        return QSize(160, self.sizeHint().height())


class ThemeCombo(QComboBox):
    """The theme list, built from theme.available_names() every time it is shown
    or opened (a palette found while the app runs appears at once)."""

    def __init__(self, settings_fn: Callable[[], Settings]) -> None:
        super().__init__()
        self._settings = settings_fn
        self.setToolTip("The look of every window - remembered.")
        self.refill()
        self.currentIndexChanged.connect(self._chosen)

    def refill(self) -> None:
        from . import theme as TH
        self.blockSignals(True)
        try:
            self.clear()
            for key in TH.available_names():
                self.addItem(TH.label(key), key)
            self.setCurrentIndex(max(0, self.findData(TH.current().name)))
        finally:
            self.blockSignals(False)

    def _chosen(self, _i: int) -> None:
        from . import theme as TH
        if self.currentData():
            TH.switch(self.currentData(), self._settings())

    def showEvent(self, ev) -> None:                          # noqa: N802
        self.refill()
        super().showEvent(ev)

    def showPopup(self) -> None:                              # noqa: N802
        self.refill()
        super().showPopup()


def _tree(headers: List[str], stretch: int) -> QTreeWidget:
    t = QTreeWidget()
    t.setColumnCount(len(headers))
    t.setHeaderLabels(headers)
    t.setRootIsDecorated(False)
    t.setUniformRowHeights(True)
    t.setAlternatingRowColors(True)
    t.setSelectionMode(QAbstractItemView.SingleSelection)
    t.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    t.setTextElideMode(Qt.ElideMiddle)
    hdr = t.header()
    hdr.setStretchLastSection(False)
    for c in range(len(headers)):
        hdr.setSectionResizeMode(c, QHeaderView.Stretch if c == stretch
                                 else QHeaderView.ResizeToContents)
    return t


# =============================================================== the window
class SetupDialog(QDialog):
    """The start screen. After accept(): open_request ({"nd2", "run"}) or
    result_tuple (source, experiment, settings) + open_run."""

    def __init__(self, parent: Optional[QWidget] = None, preload: Optional[str] = None,
                 note: str = "", run: Optional[str] = None) -> None:
        super().__init__(parent)
        from .. import users
        who = users.current()
        self.setWindowTitle(f"{APP_NAME} {__version__}" + (f"  ({who})" if who else ""))
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        self.setWindowFlag(Qt.WindowMinimizeButtonHint, True)
        self.switch_user = False                   # V2.9: 'Switch user' pressed
        self.open_request: Optional[dict] = None   # 1.1: open this movie (+ run) directly
        self.open_run: Optional[str] = run         # 1.1: a run to load into the movie opened
        self._preload, self._note = preload, str(note or "")
        self._preload_done = False
        self.setMinimumSize(820, 540)
        self._fit_to_screen()
        # text grows / shrinks with this window (on top of A- / A+); a 1366 x 740
        # window is the reference, so a laptop screen keeps the chosen size
        self._scaler = W.FontScaler(self, lambda: self.settings.ui_font_pt, (1366, 740))

        self.source: Optional[ND2Source] = None
        self.experiment: Optional[Experiment] = None
        self.settings, extras = load_settings()
        self._last_dir = extras.get("last_dir", "")
        self._channel_edits: List[QLineEdit] = []
        self._recent: List[dict] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 10, 16, 10)
        outer.setSpacing(10)
        outer.addWidget(self._build_header(who))
        outer.addWidget(self._build_choices())
        body = QHBoxLayout()
        body.setSpacing(14)
        body.addWidget(self._build_movie_box(), 3)
        body.addWidget(self._build_side(), 2)
        outer.addLayout(body, 1)
        outer.addWidget(self._build_footer())
        self._show_movie(False)
        self._refresh_queue()
        self._fill_recent()

    def _fit_to_screen(self) -> None:
        """Large: the whole screen at most (app.py also maximizes it)."""
        from PySide6.QtWidgets import QApplication
        scr = QApplication.primaryScreen()
        if scr is not None:
            g = scr.availableGeometry()
            self.resize(max(820, min(1366, g.width())), max(540, min(768, g.height() - 30)))
        else:
            self.resize(1280, 720)

    # ------------------------------------------------------------ layout
    def _build_header(self, who: Optional[str]) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)
        lay.addWidget(W.LogoLabel(64))             # PeterPiper 1.0: the logo
        tag = ElideLabel("View your movies, measure the cells, average and export.",
                         mode=Qt.ElideRight)
        tag.setProperty("role", "subtitle")
        lay.addWidget(tag, 1)
        lay.addStretch(1)
        # 1.1: Smart auto-select (smartselect.py) - shown only when that part is there
        self.smart_box = QWidget()
        sl = QHBoxLayout(self.smart_box)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(4)
        self.lbl_smart = ElideLabel("", mode=Qt.ElideRight)
        self.lbl_smart.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.btn_smart_how = QToolButton()
        self.btn_smart_how.setText("?")
        self.btn_smart_how.setAutoRaise(True)
        self.btn_smart_how.setStyleSheet("padding: 2px 8px; border-radius: 11px;")
        self.btn_smart_how.clicked.connect(self._smart_how)
        sl.addWidget(self.lbl_smart)
        sl.addWidget(self.btn_smart_how)
        lay.addWidget(self.smart_box)
        lay.addSpacing(10)
        self._smart = None
        self._refresh_smart()
        if who:                                    # V2.9: whose data this is
            lbl_who = QLabel(f"User: <b>{who}</b>")
            lbl_who.setToolTip("Only your runs and settings are used.")
            lay.addWidget(lbl_who)
            self.btn_switch = W.button("Switch user", self._switch_user,
                                       "Back to 'Who is using PeterPiper?'.")
            self.btn_switch.setAutoDefault(False)
            lay.addWidget(self.btn_switch)
        return w

    def _build_choices(self) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)
        self.btn_analyse = BigChoice(
            "Analyse movies", "Choose one .nd2 file - or several at once for a queue",
            self._pick_files,
            "Choose one movie, or several at once (Ctrl / Shift + click): they become your "
            "queue, analysed one after another - draw or check the ROIs, SAVE, export, "
            "then Next movie.")
        self.btn_queue = BigChoice("Continue your queue", "", self._continue_queue,
                                   "Open the next movie of your queue that is still to do.")
        self.btn_compare = BigChoice(
            "Compare / average saved runs", "Runs you saved before - no image needed",
            self._compare_runs,
            "Runs you saved before (ROI / session files with tracking): one line per run, or "
            "replicate dishes grouped and averaged - mean of the dish means ± SEM (n = "
            "dishes), plus the pooled cells and a per-dish table. Saved as Prism (.prism), "
            "PNG / JPEG / SVG / TIFF / PDF, CSV and Excel.")
        for b in (self.btn_analyse, self.btn_queue, self.btn_compare):
            lay.addWidget(b, 1)
        return w

    def _build_movie_box(self) -> QGroupBox:
        box = QGroupBox("Movie")
        self.box_movie = box
        lay = QVBoxLayout(box)
        lay.setSpacing(7)
        self.lbl_hint = W.wrapped_label(
            "No movie chosen yet.\n\n"
            "1   Analyse movies: choose one .nd2 - or several at once, analysed one after "
            "another (your queue).\n"
            "2   Check it here: the pixel size and the frame interval - every size and time "
            "depends on them.\n"
            "3   Open it: draw or detect the cells, track, SAVE, export.\n\n"
            "Or open one of your recent analyses again (on the right), or compare and "
            "average runs you saved.", muted=True)
        lay.addWidget(self.lbl_hint)
        self.lbl_check = W.wrapped_label("")       # 1.1: why this movie needs a look
        self.lbl_check.setProperty("role", "warn")
        self.lbl_check.setVisible(False)
        lay.addWidget(self.lbl_check)

        self.movie_panel = QWidget()
        mp = QVBoxLayout(self.movie_panel)
        mp.setContentsMargins(0, 0, 0, 0)
        mp.setSpacing(7)
        self.lbl_file = ElideLabel("No file chosen yet.")
        f = QFont(self.lbl_file.font())
        f.setBold(True)
        self.lbl_file.setFont(f)
        self.lbl_where = ElideLabel("", muted=True)
        mp.addWidget(self.lbl_file)
        mp.addWidget(self.lbl_where)
        self.lbl_info = W.wrapped_label("-")
        mp.addWidget(self.lbl_info)
        self.lbl_gaps = W.wrapped_label("")               # V3.0: uneven gaps
        self.lbl_gaps.setProperty("role", "warn")
        self.lbl_gaps.setVisible(False)
        mp.addWidget(self.lbl_gaps)

        nums = QHBoxLayout()
        nums.setSpacing(8)
        self.sp_um = self._dspin(1.0, 0.0001, 100.0, 4, 0.01,
                                 "Read from the file. Every size and distance depends on it, "
                                 "so check it.")
        self.sp_int = self._dspin(0.0, 0.0, 100000.0, 2, 1.0,
                                  "Seconds between timepoints (sets the Time_min column). "
                                  "0 means unknown.")
        self.cmb_pos = QComboBox()
        self.cmb_pos.addItem("1")
        self.cmb_pos.setToolTip("Multi-position files only: which position to analyse.")
        self.lbl_pos = QLabel("Stage position")
        for lab, wid in (("Pixel size (µm/px)", self.sp_um),
                         ("Frame interval (s)", self.sp_int), (self.lbl_pos, self.cmb_pos)):
            ql = lab if isinstance(lab, QLabel) else QLabel(lab)
            ql.setToolTip(wid.toolTip())
            nums.addWidget(ql)
            nums.addWidget(wid)
            nums.addSpacing(10)
        nums.addStretch(1)
        mp.addLayout(nums)

        self._ch_row = QHBoxLayout()
        self._ch_row.setSpacing(6)
        lab = QLabel("Channel names")
        lab.setToolTip("The names become the Excel sheet names - the microscope's names "
                       "unless you change them here.")
        self._ch_row.addWidget(lab)
        self._ch_row.addStretch(1)
        mp.addLayout(self._ch_row)

        outrow = QHBoxLayout()
        outrow.setSpacing(6)
        outrow.addWidget(QLabel("Results folder"))
        self.lbl_out = ElideLabel("", muted=False)
        outrow.addWidget(self.lbl_out, 1)
        self.btn_out = W.button("Change...", self._pick_out,
                                "Where the workbooks, graphs, ROI file and TIFFs are written.")
        self.btn_open_out = W.button("Open results folder", self._open_results,
                                     "Open this movie's results folder (Explorer / Finder).")
        for b in (self.btn_out, self.btn_open_out):
            b.setAutoDefault(False)
            outrow.addWidget(b)
        mp.addLayout(outrow)
        self.lbl_out_note = W.wrapped_label("", muted=True)    # 1.0.3: read-only drive
        self.lbl_out_note.setVisible(False)
        mp.addWidget(self.lbl_out_note)
        # v2.3: has this .nd2 been analysed before? (the analysis window offers the runs)
        self.lbl_before = W.wrapped_label("", muted=True)
        self.lbl_before.setVisible(False)
        mp.addWidget(self.lbl_before)
        lay.addWidget(self.movie_panel)
        lay.addStretch(1)

        self.btn_open = W.button("Open in the analysis window", self._accept,
                                 "Open this movie to draw / detect, track, measure and export.",
                                 strong=True)
        self.btn_open.setDefault(True)
        lay.addWidget(W.row(QWidget(), self.btn_open))
        self.btn_open.parentWidget().layout().setStretch(0, 1)
        return box

    def _dspin(self, value, lo, hi, decimals, step, tip) -> QDoubleSpinBox:
        w = QDoubleSpinBox()
        w.setRange(lo, hi)
        w.setDecimals(decimals)
        w.setSingleStep(step)
        w.setValue(float(value))
        w.setToolTip(tip)
        w.setMinimumWidth(90)
        return w

    def _build_side(self) -> QTabWidget:
        self.tabs = QTabWidget()
        # recent analyses
        rec = QWidget()
        rl = QVBoxLayout(rec)
        rl.setContentsMargins(8, 8, 8, 8)
        rl.setSpacing(6)
        self.tree_recent = _tree(["Movie", "Saved", "Cells", ""], 0)
        self.tree_recent.setToolTip("Your newest analyses, one per movie. Double-click to "
                                    "open it again in the analysis window.")
        self.tree_recent.itemDoubleClicked.connect(lambda *_: self._open_recent())
        self.tree_recent.currentItemChanged.connect(lambda *_: self._recent_buttons())
        rl.addWidget(self.tree_recent, 1)
        self.btn_recent_open = W.button(
            "Open in analysis window", self._open_recent,
            "The movie opens with this run loaded - its ROIs and tracking as saved.")
        self.btn_recent_folder = W.button("Results folder", self._open_recent_folder,
                                          "Open the folder this run was saved in.")
        for b in (self.btn_recent_open, self.btn_recent_folder):
            b.setAutoDefault(False)
        rl.addWidget(W.row(self.btn_recent_open, self.btn_recent_folder))
        self.tabs.addTab(rec, "Recent analyses")
        # the queue
        q = QWidget()
        ql = QVBoxLayout(q)
        ql.setContentsMargins(8, 8, 8, 8)
        ql.setSpacing(6)
        self.tree_queue = _tree(["#", "Movie", "Status"], 1)
        self.tree_queue.setToolTip("Movies chosen together, analysed one after another. "
                                   "Double-click one to open it.")
        self.tree_queue.itemDoubleClicked.connect(lambda *_: self._open_queued())
        ql.addWidget(self.tree_queue, 1)
        ql.addWidget(W.wrapped_label(
            "One after another: draw or check the ROIs, SAVE, export, then ‘Next "
            "movie’ in the analysis window.", muted=True))
        self.btn_q_open = W.button("Open", self._open_queued, "Open the selected movie.")
        self.btn_q_remove = W.button("Remove", self._remove_queued,
                                     "Take the selected movie out of the queue (the file "
                                     "is not touched).")
        self.btn_q_clear = W.button("Clear queue", self._clear_queue,
                                    "Empty the queue (no file is touched).")
        for b in (self.btn_q_open, self.btn_q_remove, self.btn_q_clear):
            b.setAutoDefault(False)
        ql.addWidget(W.row(self.btn_q_open, self.btn_q_remove, self.btn_q_clear))
        self.tabs.addTab(q, "Queue")
        return self.tabs

    def _build_footer(self) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.btn_saved = W.button("Saved files", self._saved_files,
                                  "Every file PeterPiper saved (exports, comparisons, batch "
                                  "runs), newest first - click to open it or its folder.")
        lay.addWidget(self.btn_saved)
        self.btn_storage = None
        opener = _storage_opener()
        if opener is not None:                       # 1.1: only when the part is there
            self.btn_storage = W.button("Storage & cloud", lambda: opener(self),
                                        "Where results are kept, and back-ups.")
            lay.addWidget(self.btn_storage)
        self.btn_update = W.button(                  # 1.1: the only network use, on request
            "Check for updates", self._check_updates,
            "Asks GitHub whether a newer PeterPiper exists (only when you press this; nothing "
            "of yours is sent). Your profiles, saved runs, logs and results are never touched.")
        lay.addWidget(self.btn_update)
        self.btn_more = QToolButton()
        self.btn_more.setText("More")
        self.btn_more.setPopupMode(QToolButton.InstantPopup)
        self.btn_more.setToolTip("Things used now and then.")
        menu = QMenu(self.btn_more)
        self._more_actions = {}
        for key, text, fn in (
                ("batch", "Batch analyse automatically (no clicking)...", self._batch),
                ("templates", "Prism style templates...", self._templates),
                (None, None, None),
                ("export_profile", "Export my profile...", self._export_profile),
                ("import_profile", "Import a profile...", self._import_profile)):
            if key is None:
                menu.addSeparator()
                continue
            self._more_actions[key] = menu.addAction(text, fn)
        self._more_actions["batch"].setToolTip(
            "Analyse many .nd2 files without clicking, with saved analysis settings. Each "
            "file is flagged for you to check.")
        menu.setToolTipsVisible(True)
        self.btn_more.setMenu(menu)
        lay.addWidget(self.btn_more)
        lay.addStretch(1)
        lay.addWidget(W.text_size_row(lambda: self.settings.ui_font_pt, self._set_text_size))
        lay.addWidget(QLabel("Theme"))
        self.cmb_theme = ThemeCombo(lambda: self.settings)
        lay.addWidget(self.cmb_theme)
        return w

    # ------------------------------------------------------------- state
    def _show_movie(self, on: bool) -> None:
        self.movie_panel.setVisible(on)
        self.lbl_hint.setVisible(not on)
        self.btn_open.setEnabled(on)
        self.btn_open.setVisible(on)
        self._set_enabled(on)

    def _set_enabled(self, on: bool) -> None:
        for w in (self.sp_um, self.sp_int, self.cmb_pos, self.btn_out):
            w.setEnabled(on)
        for e in self._channel_edits:
            e.setEnabled(on)

    def _set_out_label(self, folder: str) -> None:
        self.lbl_out.setText(folder)
        self.btn_open_out.setEnabled(True)

    def showEvent(self, ev) -> None:                          # noqa: N802
        super().showEvent(ev)
        self.cmb_theme.refill()
        self._refresh_smart()
        if self._preload and not self._preload_done:
            self._preload_done = True
            QTimer.singleShot(0, self._do_preload)
        if not getattr(self, "_absorb_asked", False):  # 1.2: older versions to take in
            self._absorb_asked = True
            QTimer.singleShot(500, self._offer_absorb)

    def _offer_absorb(self) -> None:
        """1.2: once per program start, if older PeterPiper versions can be taken in,
        a window offers it (not blocking this one). Never raises."""
        try:
            from .absorbdlg import offer_on_start
            self.absorb_dlg = offer_on_start(self)
        except Exception:                                          # noqa: BLE001
            self.absorb_dlg = None

    def _refresh_smart(self) -> None:
        """The Smart auto-select line: its state in one line, the directions as the
        tooltip and behind (?); hidden when smartselect.py is not there."""
        st = smart_status()
        self._smart = st
        if not st or not st.get("text"):
            self.smart_box.setVisible(False)
            return
        how = str(st.get("how") or "")
        self.lbl_smart.setText(("✨ " if st.get("unlocked") else "\U0001f512 ")
                               + str(st["text"]))
        self.lbl_smart.setProperty("role", "ok" if st.get("unlocked") else "")
        self.lbl_smart.setProperty("muted", not st.get("unlocked"))
        self.lbl_smart.style().unpolish(self.lbl_smart)
        self.lbl_smart.style().polish(self.lbl_smart)
        for w in (self.lbl_smart, self.btn_smart_how, self.smart_box):
            w.setToolTip(how)
        self.btn_smart_how.setVisible(bool(how))
        self.smart_box.setVisible(True)

    def _smart_how(self) -> None:
        st = self._smart or {}
        QMessageBox.information(self, "Smart auto-select",
                                f"{st.get('text', '')}\n\n{st.get('how', '')}".strip())

    def _do_preload(self) -> None:
        path, note = self._preload, self._note
        self._load(path)
        if self.experiment is not None and note:
            self._set_check_note(note)

    def _set_check_note(self, note: str) -> None:
        self.lbl_check.setText(f"Please check before opening: {note}" if note else "")
        self.lbl_check.setVisible(bool(note))

    def _set_text_size(self, pt: float) -> None:
        self.settings.ui_font_pt = 0.0 if not pt else float(min(max(pt, 7.0), 28.0))
        save_settings(self.settings)
        self._scaler._last = 0.0
        self._scaler.apply()                     # your size x the window-size factor

    # -------------------------------------------------------- secondary
    def _saved_files(self) -> None:
        from .outlogdlg import OutputsDialog
        OutputsDialog(self).exec()

    def _check_updates(self) -> None:
        from .updatedlg import check_for_updates
        check_for_updates(self)

    def _batch(self) -> None:
        from .batchdlg import BatchDialog
        todo = [it["nd2"] for it in batchqueue.items() if it["status"] == "todo"]
        BatchDialog(self.settings, self, paths=todo).exec()

    def _templates(self) -> None:
        from .templatedlg import TemplateDialog

        def take(st: dict) -> None:
            from .. import graphstyle as GS
            self.settings.graph_style = GS.coerce(dict(self.settings.graph_style or {},
                                                       **st)).to_dict()
        TemplateDialog(take, self).exec()

    def _export_profile(self) -> None:
        from .userdlg import export_profile_dialog
        export_profile_dialog(self)

    def _import_profile(self) -> None:
        from .userdlg import import_profile_dialog
        import_profile_dialog(self)

    def _switch_user(self) -> None:
        self.switch_user = True
        self.reject()

    # ----------------------------------------------------------- choosing
    def _pick_files(self) -> None:
        start = self._last_dir or str(Path.home())
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Choose one or several .nd2 movies", start,
            "Nikon ND2 images (*.nd2);;All files (*)")
        if paths:
            self.choose_movies(paths)

    _pick_file = _pick_files                       # the name before 1.1

    def choose_movies(self, paths: List[str]) -> None:
        """One movie: shown here to check and open. Several: they become the queue
        (or are added to it), and the first still to do is shown here."""
        paths = [str(p) for p in paths if p]
        if not paths:
            return
        if len(paths) == 1:
            self._load(paths[0])
            return
        todo = [it for it in batchqueue.items() if it["status"] == "todo"]
        if todo:
            how = self._ask_queue(len(todo), len(paths))
            if how == "add":
                batchqueue.add(paths)
            elif how == "new":
                batchqueue.set_items(paths)
            else:
                return
        else:
            batchqueue.set_items(paths)
        self._refresh_queue()
        self.tabs.setCurrentIndex(1)
        status = {os.path.normcase(os.path.abspath(it["nd2"])): it["status"]
                  for it in batchqueue.items()}
        first = next((p for p in paths
                      if status.get(os.path.normcase(os.path.abspath(p))) == "todo"), paths[0])
        self._load(first)

    def _ask_queue(self, n_todo: int, n_new: int) -> str:
        """'add', 'new' or '' (cancel). Tests replace this."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle("Your queue")
        box.setText(f"Your queue still has {n_todo} movie{'' if n_todo == 1 else 's'} to do. "
                    f"Add the {n_new} new ones to it, or start a new queue with them?")
        b_add = box.addButton("Add to the queue", QMessageBox.AcceptRole)
        b_new = box.addButton("Start a new queue", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Cancel)
        box.setDefaultButton(b_add)
        box.exec()
        hit = box.clickedButton()
        return "add" if hit is b_add else "new" if hit is b_new else ""

    def _request(self, nd2: str, run: Optional[str] = None) -> None:
        """Close and let app.py open this movie (and load this run) directly."""
        self.open_request = {"nd2": str(nd2), "run": str(run) if run else None}
        self._close_source()
        self.accept()

    # ------------------------------------------------------------ queue
    def _refresh_queue(self) -> None:
        its = batchqueue.items()
        todo = [it for it in its if it["status"] == "todo"]
        self.tree_queue.clear()
        cur = os.path.normcase(os.path.abspath(self.experiment.nd2_path)) if (
            self.experiment is not None and self.experiment.nd2_path) else None
        for i, it in enumerate(its):
            row = QTreeWidgetItem([str(i + 1), Path(it["nd2"]).name,
                                   STATUS_WORDS.get(it["status"], it["status"])])
            row.setData(0, Qt.UserRole, it["nd2"])
            row.setToolTip(1, it["nd2"])
            if cur and os.path.normcase(os.path.abspath(it["nd2"])) == cur:
                fb = QFont(row.font(1))
                fb.setBold(True)
                row.setFont(1, fb)
            self.tree_queue.addTopLevelItem(row)
        if its:
            self.tree_queue.setCurrentItem(self.tree_queue.topLevelItem(0))
        self.tabs.setTabText(1, f"Queue ({len(todo)} left)" if todo else
                             "Queue (all done)" if its else "Queue")
        for b in (self.btn_q_open, self.btn_q_remove, self.btn_q_clear):
            b.setEnabled(bool(its))
        nxt = batchqueue.next_after(None)
        self.btn_queue.setVisible(bool(todo) and nxt is not None)
        if todo and nxt:
            self.btn_queue.set_texts(f"Continue your queue ({len(todo)} left)",
                                     f"Next: {Path(nxt).name}")

    def _continue_queue(self) -> None:
        nxt = batchqueue.next_after(None)
        if nxt:
            self._request(nxt, None)

    def _queued_path(self) -> Optional[str]:
        it = self.tree_queue.currentItem()
        return it.data(0, Qt.UserRole) if it is not None else None

    def _open_queued(self) -> None:
        p = self._queued_path()
        if p:
            self._request(p, None)

    def _remove_queued(self) -> None:
        p = self._queued_path()
        if p:
            batchqueue.remove(p)
            self._refresh_queue()

    def _clear_queue(self) -> None:
        batchqueue.clear()
        self._refresh_queue()
        self.tabs.setCurrentIndex(0)

    # ---------------------------------------------------- recent analyses
    def _fill_recent(self) -> None:
        from .historydlg import when_text
        self._recent = W.run_with_progress(       # 1.2: a bar when the drives are slow
            self, "Finding your recent analyses",
            lambda _p: recent_analyses(RECENT_N, progress=_p))
        self.tree_recent.clear()
        for i, r in enumerate(self._recent):
            kind = KIND_WORDS.get(r["kind"], r["kind"] or "Saved")
            if r.get("note"):
                kind += f": {r['note']}"
            row = QTreeWidgetItem([r["nd2_name"] or Path(r["nd2"]).name, when_text(r["saved"]),
                                   str(r["n_cells"]), kind])
            row.setData(0, Qt.UserRole, i)
            tip = (f"{r['nd2'] or r['nd2_name']}\nRun: {r['run']}"
                   + ("" if r["movie_here"] else "\nThe movie is not here (moved, or its "
                                                 "drive is not plugged in)."))
            for c in range(4):
                row.setToolTip(c, tip)
            if not r["movie_here"]:
                row.setText(0, row.text(0) + "  (movie not here)")
            self.tree_recent.addTopLevelItem(row)
        if not self._recent:
            row = QTreeWidgetItem(["No analyses yet - they appear here once you save or "
                                   "export one.", "", "", ""])
            row.setFlags(Qt.NoItemFlags)
            self.tree_recent.addTopLevelItem(row)
        else:                                      # the newest one that can be opened
            first = next((i for i, r in enumerate(self._recent) if r["movie_here"]), 0)
            self.tree_recent.setCurrentItem(self.tree_recent.topLevelItem(first))
        self._recent_buttons()

    def current_recent(self) -> Optional[dict]:
        it = self.tree_recent.currentItem()
        if it is None or it.data(0, Qt.UserRole) is None:
            return None
        i = int(it.data(0, Qt.UserRole))
        return self._recent[i] if 0 <= i < len(self._recent) else None

    def _recent_buttons(self) -> None:
        r = self.current_recent()
        self.btn_recent_open.setEnabled(bool(r and r["movie_here"]))
        self.btn_recent_folder.setEnabled(bool(r and os.path.isdir(long_path(r["folder"]))))

    def _open_recent(self) -> None:
        r = self.current_recent()
        if r is None:
            return
        if not r["movie_here"]:
            QMessageBox.information(self, "The movie is not here",
                                    f"{r['nd2_name']} was not found (moved, or its drive is "
                                    f"not plugged in):\n{r['nd2']}")
            return
        self._request(r["nd2"], r["run"])

    def _open_recent_folder(self) -> None:
        r = self.current_recent()
        if r is not None:
            W.open_path(r["folder"])

    def _open_results(self) -> None:
        e = self.experiment
        if e is None:
            return
        folder = Path(e.out_dir)
        while not folder.is_dir() and folder.parent != folder:     # not made yet:
            folder = folder.parent                                 # the nearest one
        W.open_path(str(folder))

    # ----------------------------------------------------------- browsing
    def _pick_out(self) -> None:
        start = self.experiment.out_dir if self.experiment else (self._last_dir or str(Path.home()))
        folder = QFileDialog.getExistingDirectory(self, "Select the results folder", start)
        if not folder:
            return
        if self.experiment:
            self.experiment.out_dir = folder
        self._set_out_label(folder)
        self.lbl_out_note.setVisible(False)
        self._show_history()

    def _show_gaps(self) -> None:
        """V3.0: say when the gaps between timepoints were not even (the results
        still space the timepoints evenly, at the frame interval below)."""
        e = self.experiment
        txt = e.gaps_text() if e is not None else ""
        if txt:
            from ..config import duration_text
            spf = float(e.seconds_per_frame or 0)
            txt = (f"Uneven gaps between timepoints: {txt} (the others "
                   f"{duration_text(spf)}). Graphs and results space the timepoints "
                   f"evenly at the frame interval, so times next to these gaps are "
                   f"not the real ones; the Methods say so.")
        self.lbl_gaps.setText(txt)
        self.lbl_gaps.setVisible(bool(txt))

    # ------------------------------------------------------------ loading
    def _close_source(self) -> None:
        if self.source is not None:
            self.source.close()
            self.source = None

    def _load(self, path: str) -> None:
        self._close_source()
        if self._preload and os.path.normcase(os.path.abspath(str(path))) != \
                os.path.normcase(os.path.abspath(str(self._preload))):
            self.open_run = None                   # another movie: not that run
            self._set_check_note("")
        try:
            size_gb = os.stat(long_path(path)).st_size / 1e9
            src = open_movie(path, self)
        except Exception as exc:                                   # noqa: BLE001
            QMessageBox.critical(self, "Could not open the file",
                                 f"{Path(path).name} could not be read.\n\n{error_text(exc)}")
            return

        self.source = src
        from .. import users                       # V2.9: OUTPUT_<movie>/<user>
        default_out, moved = default_results_folder(path)
        self.experiment = describe(src, out_dir=default_out)
        self._last_dir = str(Path(path).parent)

        pos = batchqueue.position(path)
        self.lbl_file.setText(Path(path).name + (f"   (movie {pos[0]} of {pos[1]} in your "
                                                 f"queue)" if pos else ""))
        self.lbl_where.setText(str(Path(path).parent))
        self._set_out_label(default_out)
        self.lbl_out_note.setText(
            "The movie's drive is read-only here, so the results go to your "
            f"{users.RESULTS_DIR_NAME} folder; the movie is only read." if moved else "")
        self.lbl_out_note.setVisible(moved)
        mins = self.experiment.recorded_minutes()       # V3.0: as recorded
        self._show_gaps()
        self.lbl_info.setText(
            f"{src.n_timepoints} timepoints x {len(src.channels)} channels "
            f"({', '.join(src.channels)}), {src.width} x {src.height} px, "
            f"{src.bit_depth}-bit, {size_gb:.2f} GB"
            + (f", {mins:.0f} min total" if mins else "")
            + (f". Objective: {src.objective}" if src.objective else ""))
        self.sp_um.setValue(src.um_per_px)
        self.sp_int.setValue(self.experiment.seconds_per_frame)

        n_pos = max(1, int(getattr(src, "n_positions", 1) or 1))
        self.cmb_pos.clear()
        self.cmb_pos.addItems([str(i + 1) for i in range(n_pos)])
        self.cmb_pos.setVisible(n_pos > 1)
        self.lbl_pos.setVisible(n_pos > 1)

        for e in self._channel_edits:
            self._ch_row.removeWidget(e)
            e.deleteLater()
        self._channel_edits = []
        for i, name in enumerate(src.channels):
            e = QLineEdit(name)
            e.setToolTip(f"Channel {i + 1}: used as the Excel sheet suffix for this channel.")
            e.setMinimumWidth(60)
            e.setMaximumWidth(160)
            self._ch_row.insertWidget(1 + i, e)
            self._channel_edits.append(e)

        self._show_movie(True)
        self._refresh_queue()
        self._show_history()

    def _show_history(self) -> None:
        """'Analysed before: 3 earlier runs (newest 29 Oct 2026 17:26, tracking saved)'
        - a quick look (file summaries only); the analysis window offers to load one."""
        e = self.experiment
        if e is None:
            return
        try:
            from ..history import find_previous_runs
            from .historydlg import when_text
            runs = W.run_with_progress(            # V2.9: a bar, not a frozen window
                self, "Looking for earlier analyses of this file",
                lambda _p: find_previous_runs(e.nd2_path, e.out_dir, (e.height, e.width),
                                              e.n_timepoints, progress=_p))
        except Exception:                                          # noqa: BLE001
            runs = []
        if runs:
            n, new = len(runs), runs[0]
            n_trk = sum(1 for r in runs if r.tracked)
            txt = (f"Analysed before: {n} earlier run{'' if n == 1 else 's'} (newest "
                   f"{when_text(new.saved)}, tracking {'saved' if new.tracked else 'not saved'}")
            if n_trk and not new.tracked:
                txt += f"; {n_trk} with tracking"
            txt += "). You can load one when the movie opens."
        else:
            txt = "Not analysed before - this will be a fresh analysis."
        self.lbl_before.setText(txt)
        self.lbl_before.setVisible(True)

    # ------------------------------------------------------------- accept
    def _accept(self) -> None:
        if self.source is None or self.experiment is None:
            return
        names = [e.text().strip() or f"Ch{i + 1}" for i, e in enumerate(self._channel_edits)]
        try:
            for name in names:
                validate_filename_part(name, "Channel name")
        except ValueError as exc:
            QMessageBox.warning(self, "Unsafe channel name", str(exc))
            return
        if len(set(n.lower() for n in names)) != len(names):
            QMessageBox.warning(self, "Channel names repeat",
                                "Give every channel a different name - they become "
                                "the names of the Excel sheets.")
            return

        pos = max(0, self.cmb_pos.currentIndex())
        if pos != getattr(self.source, "position", 0):
            self.source.position = pos
            self.source._pd4_first = None          # that first frame was position 1's

        e = self.experiment
        e.channels = names
        e.um_per_px = float(self.sp_um.value())
        e.seconds_per_frame = float(self.sp_int.value())
        e.export_tiffs = False                      # chosen next to Save instead
        fit_settings(self.settings, e)
        if not self._results_folder_ok():
            return
        save_settings(self.settings, e)
        self.accept()

    # 1.0.3: a results folder that cannot be written (e.g. a Windows-formatted
    # drive on a Mac) - say why and offer another place, instead of an error
    # after Start
    def _results_folder_ok(self) -> bool:
        return results_folder_ok(self.experiment, self._ask_results_folder, self,
                                 self._set_out_label)

    def _ask_results_folder(self, folder: str, why: str, alt: str) -> str:
        """'alt', 'pick' or '' (cancel)."""
        return ask_results_folder(self, folder, why, alt)

    # ------------------------------------------------------------ compare
    def _compare_runs(self) -> None:
        from .comparewin import CompareWindow
        e = self.experiment
        dlg = CompareWindow(dict(getattr(self.settings, "graph_style", None) or {}),
                            e.nd2_path if e else "", e.out_dir if e else "",
                            (e.height, e.width) if e else None, e.n_timepoints if e else None,
                            self)
        dlg.exec()
        req = getattr(dlg, "open_request", None)   # 1.1: 'Open in analysis' on a run
        if isinstance(req, dict) and req.get("nd2"):
            self._request(req["nd2"], req.get("run"))
        else:
            self._fill_recent()                    # runs may have been saved there

    @property
    def result_tuple(self):
        return self.source, self.experiment, self.settings

    def reject(self) -> None:
        self._close_source()
        super().reject()

    def done(self, r: int) -> None:
        self._scaler._timer.stop()                 # closed: no late text-size change
        super().done(r)

    def hideEvent(self, ev) -> None:                          # noqa: N802
        self._scaler._timer.stop()
        super().hideEvent(ev)


def smart_status() -> Optional[dict]:
    """smartselect.status() ({"unlocked", "text", "how"}), or None when the module
    is not there or fails."""
    try:
        from ..smartselect import status
        st = status()
        return dict(st) if isinstance(st, dict) else None
    except Exception:                                              # noqa: BLE001
        return None


def _storage_opener():
    """open_storage_dialog(parent) from gui/storagedlg.py, or None (not there)."""
    try:
        from .storagedlg import open_storage_dialog
        return open_storage_dialog
    except Exception:                                              # noqa: BLE001
        return None
