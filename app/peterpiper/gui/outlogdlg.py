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
         "batch": "Batch analysis", "kinetics": "Kinetics"}


def _open(path: str) -> None:
    try:
        os.startfile(plain_path(path))                     # noqa: S606 (Windows)
    except OSError:
        pass


class OutputsDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Saved files - everything PeterPiper saved")
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        self.resize(1200, 700)
        self.setMinimumSize(640, 360)
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
        lay.addWidget(W.row(W.button("Open folder", self._open_folder),
                            W.button("Open file", self._open_file),
                            W.button("Close", self.accept)))
        self._rows = []
        self._fill()

    def _fill(self) -> None:
        q = self.ed.text().strip().lower()
        self._rows = [e for e in outlog.entries() if not q or q in " ".join(
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
        if it is not None and it.data(Qt.UserRole):
            _open(it.data(Qt.UserRole))
