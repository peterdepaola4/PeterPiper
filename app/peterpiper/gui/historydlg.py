"""
'This file has been analysed before': the earlier ROI / session files found for
the .nd2 just opened (history.find_previous_runs), newest first. Load one - with
its tracking, if it was saved, so every ROI is shown at every timepoint - or
start a fresh analysis. Nothing is changed on disk by looking or loading.
V2.5: identical saves (same ROIs, tracking and settings - history.dedupe_runs)
are listed once, the newest of them.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List, Optional, Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QDialog, QHBoxLayout, QLabel,
                               QPushButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout)

from ..history import KIND_WORDS, RunInfo, dedupe_runs
from ..roifile import COMP_WORDS
from . import widgets as W

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
COLUMNS = ("Saved", "Version", "Cells", "Compartments", "Tracking", "Kind", "Folder")
MATCH_WORDS = {
    "same file": "this same .nd2 (its contents match the fingerprint saved with the run)",
    "same name": "an .nd2 with the same name and image size (the run did not record the "
                 "file's fingerprint, or it differs)",
    "renamed copy": "this same .nd2 (contents match), saved under another name: {name}",
}


def when_text(saved: str) -> str:
    """'29 Oct 2026 17:26' for an ISO time (the text itself if it is not one)."""
    try:
        d = datetime.fromisoformat(str(saved))
    except (TypeError, ValueError):
        return str(saved or "?")
    return f"{d.day} {_MONTHS[d.month - 1]} {d.year} {d:%H:%M}"


def version_text(v: str) -> str:
    v = str(v or "")
    if v.endswith(".0") and v.count(".") >= 2:
        v = v[:-2]
    return f"V{v}" if v else "older"


def comps_text(comps: Sequence[str]) -> str:
    return " + ".join(COMP_WORDS.get(c, c) for c in comps) or "no ROIs"


class PreviousRunsDialog(QDialog):
    """
    runs: history.RunInfo list, newest first. After exec():
      selected_path() - the run to load (None = start fresh / keep what you have)
      dont_ask()      - the 'Don't ask again' box was ticked
    menu=True: opened from File > Earlier analyses... (the other button then
    keeps the current work, and the 'don't ask' box is not shown).
    """

    def __init__(self, runs: List[RunInfo], nd2_name: str, parent=None,
                 menu: bool = False) -> None:
        super().__init__(parent)
        self.runs = dedupe_runs(list(runs))      # one entry per identical analysis
        self._menu = bool(menu)
        self._choice: Optional[str] = None
        self.setWindowTitle("This file has been analysed before" if not menu else
                            "Earlier analyses of this file")
        self.resize(980, 560)
        lay = QVBoxLayout(self)
        n = len(self.runs)
        n_trk = sum(1 for r in self.runs if r.tracked)
        lay.addWidget(W.wrapped_label(
            f"<b>{nd2_name}</b> has {n} earlier analys{'is' if n == 1 else 'es'} saved "
            f"({n_trk} with the tracking). Load one to see its ROIs again - when its tracking "
            f"was saved, the outlines follow the cells at every timepoint, exactly as they "
            f"were tracked, and you can export again without re-tracking. Or start a fresh "
            f"analysis. Loading changes nothing on disk."))

        self.tree = QTreeWidget()
        self.tree.setColumnCount(len(COLUMNS))
        self.tree.setHeaderLabels(list(COLUMNS))
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.setToolTip("Newest first. Double-click a run to load it.")
        first, first_trk = None, None
        for i, r in enumerate(self.runs):
            folder = Path(r.path).parent
            it = QTreeWidgetItem([
                when_text(r.saved), f"{getattr(r, 'app', 'PD4nav')} {version_text(r.version)}",
                str(r.n_cells),
                comps_text(r.comps), "saved ✓" if r.tracked else "not saved",
                KIND_WORDS.get(r.kind, r.kind or "saved"), folder.name])
            it.setData(0, Qt.UserRole, i)
            it.setToolTip(6, str(r.path))
            for col in range(len(COLUMNS)):
                if col != 6:
                    it.setToolTip(col, r.label())
            if r.tracked:
                it.setForeground(4, QBrush(QColor("#2e9e4f")))
            if r.note:
                it.setForeground(0, QBrush(QColor("#c07000")))
            self.tree.addTopLevelItem(it)
            first = first or it
            if r.tracked and first_trk is None:
                first_trk = it
        for col in range(len(COLUMNS) - 1):
            self.tree.resizeColumnToContents(col)
        lay.addWidget(self.tree, 3)

        self.lbl_details = QLabel("")
        self.lbl_details.setWordWrap(True)
        self.lbl_details.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.lbl_details.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        from . import theme as TH
        self.lbl_details.setStyleSheet(f"QLabel {{ padding: 10px; border: 1px solid "
                                       f"{TH.current().border}; border-radius: 10px; }}")
        self.lbl_details.setMinimumHeight(120)
        lay.addWidget(self.lbl_details, 2)

        self.chk_dont_ask = QCheckBox("Don't ask again for any file  (File > Earlier analyses "
                                      "of this file... still works)")
        self.chk_dont_ask.setVisible(not menu)
        lay.addWidget(self.chk_dont_ask)

        row = QHBoxLayout()
        row.addStretch(1)
        self.btn_load = QPushButton("Load this run")
        self.btn_load.setDefault(True)
        self.btn_load.setProperty("primary", True)
        self.btn_load.clicked.connect(self._load)
        self.btn_fresh = QPushButton("Keep what I have" if menu else "Start a fresh analysis")
        self.btn_fresh.setToolTip("Close this list without loading anything." if menu else
                                  "Open the image with no ROIs; the earlier runs stay as they "
                                  "are (File > Earlier analyses of this file... lists them "
                                  "again).")
        self.btn_fresh.clicked.connect(self.reject)
        row.addWidget(self.btn_fresh)
        row.addWidget(self.btn_load)
        lay.addLayout(row)

        self.tree.currentItemChanged.connect(self._show_details)
        self.tree.itemDoubleClicked.connect(lambda *_: self._load())
        pick = first                      # the newest run (the list is newest first)
        if pick is not None:
            self.tree.setCurrentItem(pick)
        self.btn_load.setEnabled(pick is not None)

    # ------------------------------------------------------------------
    def current_run(self) -> Optional[RunInfo]:
        it = self.tree.currentItem()
        if it is None:
            return None
        i = it.data(0, Qt.UserRole)
        return self.runs[int(i)] if i is not None and 0 <= int(i) < len(self.runs) else None

    def _show_details(self, *_a) -> None:
        r = self.current_run()
        self.btn_load.setEnabled(r is not None)
        self.lbl_details.setText(details_html(r) + self._newer_note(r) if r is not None
                                 else "")

    def _newer_note(self, r: RunInfo) -> str:
        """V2.4: say when the list holds a newer run without tracking (your latest
        ROIs), or an older one with tracking (no need to track again)."""
        i = self.runs.index(r)
        newer = [q for q in self.runs[:i] if not q.tracked]
        older = [q for q in self.runs[i + 1:] if q.tracked]
        out = []
        if newer:
            out.append(f"A newer run, saved {when_text(newer[0].saved)}, has no tracking saved - "
                       f"it holds your latest ROIs; pick it above if those are the ones you "
                       f"want.")
        if not r.tracked and older:
            out.append(f"An older run, saved {when_text(older[0].saved)}, has its tracking "
                       f"saved - pick it above to see the tracked outlines without tracking "
                       f"again.")
        return "".join(f"<br><span style='color:#2f6fb3'><b>Also:</b> {t}</span>" for t in out)

    def _load(self) -> None:
        r = self.current_run()
        if r is None:
            return
        self._choice = str(r.path)
        self.accept()

    def selected_path(self) -> Optional[str]:
        return self._choice if self.result() == QDialog.Accepted else None

    def dont_ask(self) -> bool:
        return not self._menu and self.chk_dont_ask.isChecked()


def details_html(r: RunInfo) -> str:
    """Everything known about one run, in plain words (the box under the list)."""
    s = r.summary or {}
    kind = {"session": "saved automatically while working (autosave)",
            "export": "written with an export",
            "saved": "saved with File > Save ROIs now"}.get(r.kind, "an ROI file")
    lines = [f"<b>Saved {when_text(r.saved)}</b> with {getattr(r, 'app', 'PD4nav')} "
             f"{version_text(r.version)} - "
             f"{kind}."]
    if r.tracked:
        lines.append(f"<b>Tracking: saved</b> - every ROI at every one of the "
                     f"{r.n_timepoints or '?'} timepoints, with the measurements. Scrubbing "
                     f"or Play shows the tracked outlines; export works without re-tracking.")
    else:
        lines.append("<b>Tracking: not saved</b> - only the ROIs as drawn are in this file "
                     "(it was made before tracking was saved in ROI files, or before TRACK & "
                     "MEASURE was run). After loading, press TRACK & MEASURE (you will be "
                     "asked).")
    lines.append(f"{r.n_cells} cell{'' if r.n_cells == 1 else 's'}: {comps_text(r.comps)}.")
    if r.rules:
        lines.append("Tracking rules: " + "; ".join(r.rules) + ".")
    extra = []
    if r.t0 is not None:
        extra.append(f"ROIs drawn on timepoint {int(r.t0) + 1}")
    if s.get("baseline"):
        extra.append(f"baseline timepoint {s['baseline']}")
    if r.prefix:
        extra.append(f"file name '{r.prefix}'")
    if extra:
        lines.append(", ".join(extra).capitalize() + ".")
    lines.append("Saved for: " + MATCH_WORDS.get(r.match, r.match).format(name=r.nd2_name) + ".")
    if r.note:
        lines.append(f"<span style='color:#c07000'><b>Note:</b> {r.note}</span>")
    lines.append(f"<span style='color:#888'>File: {r.path}</span>")
    same = list(getattr(r, "same_as", []) or [])
    if same:
        lines.append(f"<span style='color:#888'>{len(same)} older identical save"
                     f"{'' if len(same) == 1 else 's'} (same ROIs, tracking and settings) "
                     f"not listed: " + "; ".join(Path(p).name for p in same[:5])
                     + (" ..." if len(same) > 5 else "") + "</span>")
    return "<br>".join(lines)
