"""
V2.8 'Saved files...': every save PeterPiper made (peterpiper.outlog), newest first.
Pick a save on the left to see its files; double-click a save or a file to open
it (a folder opens in Explorer, a file in its program). Missing files are
marked - they were moved or deleted since.
"""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QLineEdit, QListWidget, QListWidgetItem, QSplitter,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QHeaderView,
                               QAbstractItemView)

from .. import outlog
from ..safety import plain_path
from . import widgets as W

KINDS = {"export": "Export", "compare": "Compare / average", "graph": "Graph",
         "batch": "Batch analysis", "kinetics": "Kinetics", "saved": "SAVE",
         "session": "Autosave", "run": "Saved run"}


def run_entries(seen=()) -> list:
    """1.2.2: this user's saved runs from the run list (autosaves, SAVEs, exports'
    ROI files) as log-like entries, for files the log does not list yet - so the
    window shows every analysis, also those saved before SAVE was logged. Reads
    only the run list (no file is opened). Never raises."""
    out = []
    try:
        from .. import history as H
        idx = H._load_index()
    except Exception:                                              # noqa: BLE001
        return out
    seen = {os.path.normcase(plain_path(str(s))) for s in seen}
    for ent in idx.values():
        for r in ent.get("runs", []):
            f = str(r.get("path") or "")
            if not f or os.path.normcase(plain_path(f)) in seen:
                continue
            kind = {"session": "session", "saved": "saved", "export": "export"}.get(
                str(r.get("kind") or ""), "run")
            n = r.get("n_cells")
            out.append(dict(when=str(r.get("saved") or r.get("recorded") or ""), kind=kind,
                            name=str(ent.get("nd2_name") or Path(f).name),
                            folder=str(Path(f).parent), files=[f],
                            detail=f"{KINDS.get(kind, kind)} of {ent.get('nd2_name', '')}"
                                   + (f" - {n} cells" if n else "")))
    return out


def _open(path: str) -> None:
    W.open_path(path)                                       # Windows and macOS


class OutputsDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Saved files - everything PeterPiper saved")
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        self.resize(1200, 700)
        self.setMinimumSize(640, 360)
        from PySide6.QtWidgets import QApplication
        scr = QApplication.primaryScreen()         # 1.1: never taller than the screen
        if scr is not None:
            g = scr.availableGeometry()
            self.resize(min(1200, max(640, g.width() - 40)), min(700, max(360, g.height() - 60)))
        lay = QVBoxLayout(self)
        lay.addWidget(W.wrapped_label(
            "Every save, newest first. Click a save to see its files; double-click a save to "
            "open its folder, or a file to open it. Type to filter by name, folder or kind. "
            f"The log itself: {plain_path(str(outlog.log_path()))}", muted=True))
        self.ed = QLineEdit()
        self.ed.setPlaceholderText("Filter (name, folder, kind ...)")
        self.ed.textChanged.connect(lambda _t: self._fill())
        lay.addWidget(self.ed)
        split = QSplitter(Qt.Vertical)
        split.setChildrenCollapsible(False)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["When", "What", "Name", "Files", "Folder"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.itemSelectionChanged.connect(self._show_files)
        self.table.cellDoubleClicked.connect(
            lambda r, _c: _open(self._rows[r]["folder"]) if r < len(self._rows) else None)
        self.files = QListWidget()
        self.files.itemDoubleClicked.connect(lambda it: _open(it.data(Qt.UserRole)))
        split.addWidget(self.table)
        split.addWidget(self.files)
        split.setSizes([420, 220])
        lay.addWidget(split, 1)
        self.files.currentItemChanged.connect(lambda *_a: self._buttons())
        self.btn_folder = W.button("Open folder", self._open_folder,
                                   "Open the folder of the save picked above.")
        self.btn_file = W.button("Open file", self._open_file,
                                 "Open the file picked below (or the save's first file).")
        lay.addWidget(W.row(self.btn_folder, self.btn_file, W.button("Close", self.accept)))
        self.table.itemSelectionChanged.connect(self._buttons)
        self._rows = []
        self._fill()

    def _fill(self) -> None:
        q = self.ed.text().strip().lower()
        logged = outlog.entries()
        seen = [f for e in logged for f in (e.get("files") or [])]
        every = sorted(logged + run_entries(seen),          # 1.2.2: the run list too
                       key=lambda d: str(d.get("when", "")), reverse=True)
        self._rows = [e for e in every if not q or q in " ".join(
            str(e.get(k, "")) for k in ("name", "folder", "kind", "detail")).lower()]
        self.table.setRowCount(0)
        from .historydlg import when_text
        for e in self._rows:
            i = self.table.rowCount()
            self.table.insertRow(i)
            for c, v in enumerate((when_text(str(e.get("when", ""))),
                                   KINDS.get(e.get("kind"), str(e.get("kind", ""))),
                                   str(e.get("name", "")), str(len(e.get("files") or [])),
                                   plain_path(str(e.get("folder", ""))))):
                it = QTableWidgetItem(v)
                it.setToolTip(str(e.get("detail") or v))
                self.table.setItem(i, c, it)
        self.table.resizeColumnsToContents()
        if self._rows:
            self.table.selectRow(0)
        else:
            self.files.clear()
            self.files.addItem("Nothing saved yet (or nothing matches the filter).")
        self._buttons()

    def _buttons(self) -> None:
        """1.2.2: the buttons are usable only when there is something to open."""
        has = 0 <= self.table.currentRow() < len(self._rows)
        self.btn_folder.setEnabled(has)
        self.btn_file.setEnabled(has)

    def _show_files(self) -> None:
        self.files.clear()
        r = self.table.currentRow()
        if not 0 <= r < len(self._rows):
            return
        for f in self._rows[r].get("files") or []:
            ok = os.path.exists(plain_path(f))
            it = QListWidgetItem(plain_path(f) + ("" if ok else "   (moved or deleted)"))
            it.setData(Qt.UserRole, f)
            if not ok:
                it.setForeground(Qt.gray)
            self.files.addItem(it)

    def _open_folder(self) -> None:
        r = self.table.currentRow()
        if 0 <= r < len(self._rows):
            _open(self._rows[r]["folder"])

    def _open_file(self) -> None:
        it = self.files.currentItem()
        if it is None or not it.data(Qt.UserRole):          # 1.2.2: the save's first file
            it = next((self.files.item(i) for i in range(self.files.count())
                       if self.files.item(i).data(Qt.UserRole)
                       and os.path.exists(plain_path(self.files.item(i).data(Qt.UserRole)))),
                      None)
        if it is not None and it.data(Qt.UserRole):
            _open(it.data(Qt.UserRole))
