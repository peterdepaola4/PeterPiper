"""
The start-up window: pick the file and the results folder, and check the two
numbers the analysis depends on (pixel size, frame interval).

Everything about WHAT to find and measure (channels, timepoints, baseline,
compartments, TIFF export) is set in the main window, next to the image, where
its effect can be seen - so it is not asked here.

Nothing here is typed as a path - both locations are chosen with a browser.

BLOCK: another acquisition parameter belongs in _build_info_group(); add the
matching field to Experiment first.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

import numpy as np

from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog, QLabel, QLineEdit,
                               QMessageBox, QScrollArea, QVBoxLayout, QWidget)

from .. import APP_NAME, __version__
from ..config import Experiment, Settings, load_settings, save_settings
from ..nd2io import ND2Source, describe, open_source
from ..safety import error_text, long_path, validate_filename_part
from . import widgets as W


class SetupDialog(QDialog):
    """Returns (source, experiment, settings) via .result_tuple after accept()."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        from .. import users
        who = users.current()
        self.setWindowTitle(f"{APP_NAME} {__version__} - choose an image file"
                            + (f"  ({who})" if who else ""))
        self.switch_user = False                   # V2.9: 'Switch user' pressed
        self.setMinimumWidth(520)
        self.resize(680, 600)
        self.setSizeGripEnabled(True)
        # text grows / shrinks with this window (on top of A- / A+)
        self._scaler = W.FontScaler(self, lambda: self.settings.ui_font_pt, (680, 600))

        self.source: Optional[ND2Source] = None
        self.experiment: Optional[Experiment] = None
        self.settings, extras = load_settings()
        self._last_dir = extras.get("last_dir", "")
        self._channel_edits: List[QLineEdit] = []

        outer = QVBoxLayout(self)
        outer.setSpacing(8)
        outer.addWidget(W.LogoLabel(78))           # PeterPiper 1.0: the logo
        if who:                                    # V2.9: whose data this is
            lbl_who = QLabel(f"User: <b>{who}</b> - only your runs and settings "
                             f"are used.")
            lbl_who.setProperty("muted", True)
            btn_sw = W.button("Switch user...", self._switch_user,
                              "Back to 'Who is using PeterPiper?'.")
            from .userdlg import export_profile_dialog, import_profile_dialog
            btn_ex = W.button("Export my profile...", lambda: export_profile_dialog(self),
                              "Your settings, run list, groups and templates in one zip - to "
                              "use PeterPiper the same way on another computer.")
            btn_im = W.button("Import a profile...", lambda: import_profile_dialog(self),
                              "A profile exported on another computer: added as a user, or "
                              "merged into yours if it has your name (nothing is overwritten).")
            row_w = W.row(lbl_who, btn_ex, btn_im, btn_sw)
            row_w.layout().insertStretch(1, 1)
            outer.addWidget(row_w)
        outer.addWidget(W.wrapped_label(
            "Choose the .nd2 file and where the results go. Channels, timepoints and "
            "what to find are set in the next window, next to the image."))
        from . import theme as TH                  # V2.9: text size + theme in one row
        self.cmb_theme = QComboBox()
        for key, text in TH.LABELS.items():
            self.cmb_theme.addItem(text, key)
        self.cmb_theme.setCurrentIndex(max(0, self.cmb_theme.findData(TH.current().name)))
        self.cmb_theme.setToolTip("The look of every window - remembered.")
        self.cmb_theme.currentIndexChanged.connect(
            lambda _i: TH.switch(self.cmb_theme.currentData(), self.settings))
        outer.addWidget(W.row(W.text_size_row(lambda: self.settings.ui_font_pt,
                                              self._set_text_size), QLabel("Theme"),
                              self.cmb_theme))

        # V2.5: comparing / averaging saved runs needs no image - offered first
        box, form = W.group("Compare / average saved runs (no image needed)")
        self.btn_compare = W.button(
            "Compare / average runs...", self._compare_runs,
            "Runs you saved before (ROI / session files with tracking): one line per run, or "
            "replicate dishes grouped and averaged - mean of the dish means ± SEM (n = "
            "dishes), plus the pooled cells and a per-dish table. Saved as Prism (.prism), "
            "PNG / JPEG / SVG / TIFF / PDF, CSV and Excel.", strong=True)
        form.addRow(self.btn_compare)
        # V2.7: batch analysis with saved settings, and the Prism style templates
        form.addRow(W.row(
            W.button("Batch analyse .nd2 files...", self._batch,
                     "Analyse many .nd2 files without clicking, with saved analysis settings "
                     "(File > Save analysis settings... in the main window). Each file is "
                     "flagged for you to check."),
            W.button("Prism style templates...", self._templates,
                     "Change the look of every .prism PeterPiper writes, once, in Prism."),
            W.button("Saved files...", self._saved_files,
                     "Every file PeterPiper saved (exports, comparisons, batch runs), newest first "
                     "- click to open it or its folder.")))
        form.addRow(W.wrapped_label("Or open an .nd2 file below to analyse a new movie.",
                                    muted=True))
        outer.addWidget(box)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        inner = QWidget()
        self._stack = QVBoxLayout(inner)
        self._stack.setSpacing(6)
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

        self._build_file_group()
        self._build_info_group()
        self._build_channel_group()
        self._stack.addStretch(1)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText("Open image")
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(False)
        self.buttons.accepted.connect(self._accept)
        self.buttons.rejected.connect(self.reject)
        outer.addWidget(self.buttons)
        self._set_enabled(False)

    def _set_text_size(self, pt: float) -> None:
        self.settings.ui_font_pt = 0.0 if not pt else float(min(max(pt, 7.0), 28.0))
        save_settings(self.settings)
        self._scaler._last = 0.0
        self._scaler.apply()                     # your size x the window-size factor
        self.resize(max(self.width(), int(self.sizeHint().width())),
                    max(self.height(), int(self.sizeHint().height())))

    def _saved_files(self) -> None:
        from .outlogdlg import OutputsDialog
        OutputsDialog(self).exec()

    def _batch(self) -> None:
        from .batchdlg import BatchDialog
        BatchDialog(self.settings, self).exec()

    def _templates(self) -> None:
        from .templatedlg import TemplateDialog

        def take(st: dict) -> None:
            from .. import graphstyle as GS
            self.settings.graph_style = GS.coerce(dict(self.settings.graph_style or {},
                                                       **st)).to_dict()
        TemplateDialog(take, self).exec()

    # ------------------------------------------------------------ layout
    def _build_file_group(self) -> None:
        box, form = W.group("1   Files")
        form.addRow(W.button("Browse for .nd2 file...", self._pick_file,
                             "Opens a file browser. Nothing has to be typed.", strong=True))
        self.lbl_file = W.wrapped_label("No file chosen yet.", muted=True)
        form.addRow("Image file", self.lbl_file)
        form.addRow(W.button("Browse for results folder...", self._pick_out,
                             "Where the workbooks, graphs, ROI file and TIFFs are written."))
        self.lbl_out = W.wrapped_label(
            "Defaults to a folder named OUTPUT_<file name> next to the image.", muted=True)
        form.addRow("Results folder", self.lbl_out)
        # v2.3: has this .nd2 been analysed before? (the main window offers the runs)
        self.lbl_before = W.wrapped_label("", muted=True)
        form.addRow("Analysed before", self.lbl_before)
        form.setRowVisible(self.lbl_before, False)
        self._form_files = form
        self._stack.addWidget(box)

    def _build_info_group(self) -> None:
        box, form = W.group("2   Check the file")
        self._info_form = form
        self.lbl_info = W.wrapped_label("-")
        form.addRow(self.lbl_info)
        self.lbl_gaps = W.wrapped_label("")               # V3.0: uneven gaps
        self.lbl_gaps.setProperty("role", "warn")
        self.lbl_gaps.setVisible(False)
        form.addRow(self.lbl_gaps)
        self.sp_um = W.dspin(form, "Pixel size (um/px)", 1.0, 0.0001, 100.0,
                             "Read from the file. Every size and distance depends on it, "
                             "so check it.", decimals=4, step=0.01)
        self.sp_int = W.dspin(form, "Frame interval (s)", 0.0, 0.0, 100000.0,
                              "Seconds between timepoints (sets the Time_min column). "
                              "0 means unknown.", decimals=2, step=1.0)
        self.cmb_pos = W.combo(form, "Stage position", ["1"], 0,
                               "Multi-position files only: which position to analyse.")
        form.setRowVisible(self.cmb_pos, False)           # shown for multi-position files
        self._stack.addWidget(box)

    def _build_channel_group(self) -> None:
        self.box_ch, self.form_ch = W.group("3   Channel names (optional)")
        self.chk_rename = W.check(self.form_ch, "Rename the channels",
                                  False, "The names become the Excel sheet names. The "
                                         "microscope's names are used if you leave this off.")
        self.chk_rename.toggled.connect(self._show_names)
        self._stack.addWidget(self.box_ch)

    def _show_names(self, on: bool) -> None:
        for e in self._channel_edits:
            self.form_ch.setRowVisible(e, bool(on))

    def _set_enabled(self, on: bool) -> None:
        for w in (self.sp_um, self.sp_int, self.box_ch):
            w.setEnabled(on)

    # ----------------------------------------------------------- browsing
    def _pick_file(self) -> None:
        start = self._last_dir or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self, "Select the ND2 file", start, "Nikon ND2 images (*.nd2);;All files (*)")
        if path:
            self._load(path)

    def _pick_out(self) -> None:
        start = self.experiment.out_dir if self.experiment else (self._last_dir or str(Path.home()))
        folder = QFileDialog.getExistingDirectory(self, "Select the results folder", start)
        if not folder:
            return
        if self.experiment:
            self.experiment.out_dir = folder
        self.lbl_out.setText(folder)
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
                   f"evenly at the frame interval below, so times next to these gaps are "
                   f"not the real ones; the Methods say so.")
        self.lbl_gaps.setText(txt)
        self.lbl_gaps.setVisible(bool(txt))

    # ------------------------------------------------------------ loading
    def _load(self, path: str) -> None:
        if self.source is not None:
            self.source.close()
            self.source = None
        from PySide6.QtCore import Qt as _Qt
        from PySide6.QtWidgets import QApplication
        size_gb = os.stat(long_path(path)).st_size / 1e9
        self.lbl_info.setText(f"Opening {Path(path).name} ({size_gb:.1f} GB) - please wait, "
                              f"large files take a few seconds...")
        def opening(progress):                     # V2.9: in the background, with a bar
            progress(None, f"{Path(path).name} ({size_gb:.1f} GB): reading the file header...")
            s_ = open_source(path)
            progress(None, "Reading the first frame...")
            try:                                   # the main window shows it at once
                s_._pd4_first = (0, np.asarray(s_.frame(0)))
            except Exception:                                      # noqa: BLE001
                pass
            return s_
        try:
            src = W.run_with_progress(self, f"Opening {Path(path).name}", opening, delay_ms=150)
        except Exception as exc:                                   # noqa: BLE001
            self.lbl_info.setText("")
            QMessageBox.critical(self, "Could not open the file",
                                 f"{Path(path).name} could not be read.\n\n{error_text(exc)}")
            return
        if src.n_timepoints < 1 or not src.channels:
            QMessageBox.critical(self, "Nothing to analyse",
                                 "This file has no channels or timepoints.")
            src.close()
            return

        self.source = src
        from .. import users                       # V2.9: OUTPUT_<movie>/<user>
        default_out = users.output_dir(path)
        self.experiment = describe(src, out_dir=default_out)
        self._last_dir = str(Path(path).parent)

        self.lbl_file.setText(f"{Path(path).name}\n{Path(path).parent}")
        self.lbl_out.setText(default_out)
        size_gb = os.stat(long_path(path)).st_size / 1e9
        mins = self.experiment.recorded_minutes()       # V3.0: as recorded
        self._show_gaps()
        self.lbl_info.setText(
            f"{src.n_timepoints} timepoints x {len(src.channels)} channels "
            f"({', '.join(src.channels)}), {src.width} x {src.height} px, "
            f"{src.bit_depth}-bit, {size_gb:.2f} GB"
            + (f", {mins:.0f} min total" if mins else "")
            + (f"\nObjective: {src.objective}" if src.objective else ""))
        self.sp_um.setValue(src.um_per_px)
        self.sp_int.setValue(self.experiment.seconds_per_frame)

        self.cmb_pos.clear()
        self.cmb_pos.addItems([str(i + 1) for i in range(max(1, src.n_positions))])
        self._info_form.setRowVisible(self.cmb_pos, src.n_positions > 1)

        for e in self._channel_edits:
            self.form_ch.removeRow(e)
        self._channel_edits = []
        for i, name in enumerate(src.channels):
            e = QLineEdit(name)
            e.setToolTip("Used as the Excel sheet suffix for this channel.")
            self.form_ch.addRow(f"Channel {i + 1}", e)
            self._channel_edits.append(e)
        self._show_names(self.chk_rename.isChecked())

        self._set_enabled(True)
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(True)
        self._show_history()

    def _switch_user(self) -> None:
        self.switch_user = True
        self.reject()

    def _compare_runs(self) -> None:
        from .comparewin import CompareWindow
        e = self.experiment
        dlg = CompareWindow(dict(getattr(self.settings, "graph_style", None) or {}),
                            e.nd2_path if e else "", e.out_dir if e else "",
                            (e.height, e.width) if e else None, e.n_timepoints if e else None,
                            self)
        dlg.exec()

    def _show_history(self) -> None:
        """'Analysed before: 3 earlier runs (newest 29 Oct 2026 17:26, tracking saved)'
        - a quick look (file summaries only); the main window offers to load one."""
        e = self.experiment
        if e is None:
            return
        try:
            from ..history import find_previous_runs
            from .historydlg import when_text
            runs = W.run_with_progress(            # V2.9: a bar, not a frozen window
                self, "Looking for earlier analyses of this file",
                lambda _p: find_previous_runs(e.nd2_path, e.out_dir, (e.height, e.width),
                                              e.n_timepoints))
        except Exception:                                          # noqa: BLE001
            runs = []
        if runs:
            n, new = len(runs), runs[0]
            n_trk = sum(1 for r in runs if r.tracked)
            txt = (f"{n} earlier run{'' if n == 1 else 's'} (newest {when_text(new.saved)}, "
                   f"tracking {'saved' if new.tracked else 'not saved'}")
            if n_trk and not new.tracked:
                txt += f"; {n_trk} with tracking"
            txt += "). You can load one when the image opens."
        else:
            txt = "No earlier analyses found - this will be a fresh analysis."
        self.lbl_before.setText(txt)
        self._form_files.setRowVisible(self.lbl_before, True)

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

        e = self.experiment
        e.channels = names
        e.um_per_px = float(self.sp_um.value())
        e.seconds_per_frame = float(self.sp_int.value())
        e.export_tiffs = False                      # chosen next to Save instead

        # everything else is chosen in the main window (the tracking rules decide
        # the compartments and channels); keep the saved values, made valid for
        # THIS file
        s = self.settings
        T, C = e.n_timepoints, len(names)
        s.seg_timepoint = int(min(max(1, s.seg_timepoint), T))
        s.baseline_timepoint = int(min(max(1, s.baseline_timepoint), T))
        s.ref_channel = int(min(max(0, s.ref_channel), C - 1))
        save_settings(s, e)
        self.accept()

    @property
    def result_tuple(self):
        return self.source, self.experiment, self.settings

    def reject(self) -> None:
        if self.source is not None:
            self.source.close()
            self.source = None
        super().reject()
