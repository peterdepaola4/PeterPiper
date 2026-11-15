"""
PeterPiper 1.1 'Storage & cloud' windows (peterpiper.cloud).

    open_storage_dialog(parent)                 where results go, where backups go,
                                                and the cloud / network folders found
    backup_dialog(parent, nd2_path, out_dir)    back up this analysis (with progress)
    pick_place(parent)                          a small menu of the places found +
                                                'Other folder...' -> a folder or None

PeterPiper only writes files into these folders; the service's own app (OneDrive,
Google Drive, Box, Dropbox ...) uploads them. Nothing is signed in here and
nothing here uses the network.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QDialog, QFileDialog, QGridLayout,
                               QGroupBox, QHBoxLayout, QLabel, QMenu, QMessageBox,
                               QProgressBar, QPushButton, QRadioButton, QVBoxLayout)

from .. import cloud as C
from ..safety import folder_problem, plain_path
from . import widgets as W

NOTE = ("PeterPiper only puts files into these folders. The service's own app "
        "(OneDrive, Google Drive, Box, Dropbox ...) uploads them - nothing is signed in "
        "from PeterPiper.")
NONE_FOUND = ("No cloud or network folders found. Install the OneDrive / Google Drive / "
              "Box / Dropbox app (free; you sign in there once), or choose any folder.")
MAX_SHOWN = 7


def _title(text: str) -> QLabel:
    t = QLabel(text)
    t.setProperty("role", "title")
    return t


def _bold(text: str) -> QLabel:
    lab = QLabel(text)
    f = lab.font()
    f.setBold(True)
    lab.setFont(f)
    return lab


class _PathLabel(QLabel):
    """A path in one line, shortened in the middle to fit (full path as tooltip)."""

    def __init__(self, path: str = "", empty: str = "") -> None:
        super().__init__()
        self._empty = empty
        self._path = ""
        self.setMinimumWidth(120)
        self.set_path(path)

    def set_path(self, path: str) -> None:
        self._path = plain_path(path) if path else ""
        self.setToolTip(self._path)
        self.setProperty("muted", not self._path)
        self.style().unpolish(self)
        self.style().polish(self)
        self._elide()

    def path(self) -> str:
        return self._path

    def _elide(self) -> None:
        text = self._path or self._empty
        w = max(60, self.width() - 4)
        super().setText(self.fontMetrics().elidedText(text, Qt.ElideMiddle, w))

    def resizeEvent(self, ev) -> None:                             # noqa: N802
        super().resizeEvent(ev)
        self._elide()

    def sizeHint(self):                                            # noqa: D401
        s = super().sizeHint()
        full = self.fontMetrics().horizontalAdvance(self._path or self._empty) + 8
        s.setWidth(min(full, 520))
        return s


def _check_folder(parent, path: str) -> bool:
    why = folder_problem(path)
    if why:
        QMessageBox.warning(parent, "PeterPiper",
                            f"PeterPiper cannot write in\n{plain_path(path)}\n\n{why[0].upper()}"
                            f"{why[1:]}.\nPlease choose another folder.")
        return False
    return True


# ------------------------------------------------------------------ pick a place
def place_menu(parent, places: Optional[List[C.Place]] = None, start: str = "",
               extra: Optional[List[tuple]] = None) -> QMenu:
    """The places as a menu (each action's data() is its folder) and 'Other
    folder...' (data 'other'). extra: [(text, data)] added at the end."""
    places = C.places() if places is None else places
    m = QMenu(parent)
    for p in places:
        a = m.addAction(f"{p.name}  -  {plain_path(p.path)}")
        a.setData(p.path)
        a.setToolTip(f"{p.service}: {plain_path(p.path)}")
    if places:
        m.addSeparator()
    a = m.addAction("Other folder...")
    a.setData("other")
    for text, data in (extra or []):
        m.addAction(text).setData(data)
    m.setProperty("start", start)
    return m


def _browse(parent, start: str = "") -> Optional[str]:
    d = QFileDialog.getExistingDirectory(parent, "PeterPiper - choose a folder", start or "")
    return d or None


def pick_place(parent=None, places: Optional[List[C.Place]] = None,
               start: str = "") -> Optional[str]:
    """A small menu of the cloud / network folders found, plus 'Other folder...'.
    Returns the folder chosen, or None. For other windows to start their file
    dialogs in a cloud folder."""
    places = C.places() if places is None else places
    m = place_menu(parent, places, start)
    a = m.exec(QCursor.pos())
    if a is None:
        return None
    if a.data() == "other":
        return _browse(parent, start)
    return str(a.data())


# ---------------------------------------------------------------- the settings
class StorageDialog(QDialog):
    """Where results go, where backups go, and the cloud folders found."""

    def __init__(self, parent=None, places: Optional[List[C.Place]] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("PeterPiper - storage & cloud")
        self.places = C.places() if places is None else places
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.addWidget(_title("Storage & cloud"))
        lay.addWidget(W.wrapped_label(NOTE, muted=True))

        # -- found
        box = QGroupBox("Found on this computer")
        g = QGridLayout(box)
        g.setContentsMargins(10, 8, 10, 8)
        g.setHorizontalSpacing(14)
        g.setVerticalSpacing(4)
        if not self.places:
            g.addWidget(W.wrapped_label(NONE_FOUND), 0, 0, 1, 2)
        for i, p in enumerate(self.places[:MAX_SHOWN]):
            g.addWidget(_bold(p.name), i, 0)
            g.addWidget(_PathLabel(p.path), i, 1)
        if len(self.places) > MAX_SHOWN:
            more = QLabel(f"and {len(self.places) - MAX_SHOWN} more (in the Choose... lists)")
            more.setProperty("muted", True)
            g.addWidget(more, MAX_SHOWN, 0, 1, 2)
        g.setColumnStretch(1, 1)
        lay.addWidget(box)

        # -- results
        box = QGroupBox("Results go")
        v = QVBoxLayout(box)
        v.setContentsMargins(10, 8, 10, 8)
        self.rb_next = QRadioButton("Next to each movie (default): OUTPUT_<movie> beside the .nd2")
        self.rb_folder = QRadioButton("In a folder:")
        grp = QButtonGroup(self)
        grp.addButton(self.rb_next)
        grp.addButton(self.rb_folder)
        self.lbl_results = _PathLabel("", "not chosen yet")
        self.btn_results = W.button("Choose...", self._choose_results,
                                    "Pick a cloud or network folder, or any folder.")
        r = QHBoxLayout()
        r.addWidget(self.rb_folder)
        r.addWidget(self.lbl_results, 1)
        r.addWidget(self.btn_results)
        v.addWidget(self.rb_next)
        v.addLayout(r)
        v.addWidget(W.wrapped_label("In a folder, each movie gets OUTPUT_<movie>/<your name> "
                                    "there. Movies are never moved or changed.", muted=True))
        root = C.results_root()
        self.lbl_results.set_path(root)
        (self.rb_folder if root else self.rb_next).setChecked(True)
        lay.addWidget(box)

        # -- backup
        box = QGroupBox("Back up to")
        v = QVBoxLayout(box)
        v.setContentsMargins(10, 8, 10, 8)
        self.lbl_backup = _PathLabel(C.backup_root(), "not chosen yet - asked at the first backup")
        self.btn_backup = W.button("Change...", self._choose_backup,
                                   "Pick a cloud or network folder, or any folder.")
        r = QHBoxLayout()
        r.addWidget(self.lbl_backup, 1)
        r.addWidget(self.btn_backup)
        v.addLayout(r)
        v.addWidget(W.wrapped_label(f"Back up an analysis from its window. It goes to <folder>/"
                                    f"{C.BACKUP_DIR}/<movie>; nothing there is ever "
                                    "overwritten.", muted=True))
        lay.addWidget(box)

        lay.addStretch(1)
        bl = QHBoxLayout()
        bl.addStretch(1)
        bl.addWidget(W.button("Cancel", self.reject, "Close without changes."))
        self.btn_save = W.button("Save", self._save, "Use these folders from now on.",
                                 strong=True)
        bl.addWidget(self.btn_save)
        lay.addLayout(bl)
        self.resize(660, self.sizeHint().height())

    # where a menu would choose (tests replace this)
    def _menu_choice(self, button: QPushButton, extra=None) -> Optional[str]:
        m = place_menu(self, self.places, extra=extra)
        a = m.exec(button.mapToGlobal(button.rect().bottomLeft()))
        return None if a is None else str(a.data())

    def _pick(self, button: QPushButton, for_results: bool, extra=None) -> Optional[str]:
        choice = self._menu_choice(button, extra)
        if choice is None or choice in ("none",):
            return choice
        if choice == "other":
            path = _browse(self)
        else:
            place = next((p for p in self.places if p.path == choice), None)
            path = C.suggested_results_folder(place) if (for_results and place) else choice
        if path and _check_folder(self, path):
            return path
        return None

    def _choose_results(self) -> None:
        path = self._pick(self.btn_results, True)
        if path:
            self.lbl_results.set_path(path)
            self.rb_folder.setChecked(True)

    def _choose_backup(self) -> None:
        path = self._pick(self.btn_backup, False,
                          extra=[("No backup folder (ask each time)", "none")])
        if path == "none":
            self.lbl_backup.set_path("")
        elif path:
            self.lbl_backup.set_path(path)

    def _save(self) -> None:
        res = self.lbl_results.path() if self.rb_folder.isChecked() else ""
        if self.rb_folder.isChecked() and not res:
            QMessageBox.information(self, "PeterPiper", "Choose the folder for results first.")
            return
        try:
            if res != C.results_root():
                C.set_results_root(res or None)
            bk = self.lbl_backup.path()
            if bk != C.backup_root():
                C.set_backup_root(bk or None)
        except ValueError as exc:
            QMessageBox.warning(self, "PeterPiper", str(exc))
            return
        self.accept()


def open_storage_dialog(parent=None) -> bool:
    """The 'Storage & cloud' window. True if the user saved changes."""
    return bool(StorageDialog(parent).exec())


# ------------------------------------------------------------------- the backup
class BackupDialog(QDialog):
    """Back up one analysis (results folder, optionally the movie) into a cloud /
    network folder, with a progress bar and Cancel."""

    def __init__(self, parent, nd2_path, out_dir,
                 places: Optional[List[C.Place]] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("PeterPiper - back up")
        self.nd2 = str(nd2_path)
        self.out_dir = str(out_dir) if out_dir else ""
        self.places = C.places() if places is None else places
        self.report: Optional[C.BackupReport] = None
        self._cancel = threading.Event()
        self._state: dict = {}
        self._thread: Optional[threading.Thread] = None

        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.addWidget(_title("Back up this analysis"))
        lay.addWidget(W.wrapped_label(NOTE, muted=True))

        box = QGroupBox("What")
        g = QGridLayout(box)
        g.setContentsMargins(10, 8, 10, 8)
        g.setHorizontalSpacing(14)
        g.addWidget(_bold("Movie"), 0, 0)
        g.addWidget(_PathLabel(self.nd2), 0, 1)
        g.addWidget(_bold("Results"), 1, 0)
        g.addWidget(_PathLabel(self.out_dir, "no results folder yet"), 1, 1)
        g.setColumnStretch(1, 1)
        size = self._movie_size()
        self.chk_movie = QCheckBox(f"Include the movie (.nd2, {C.human_size(size)})"
                                   if size is not None else "Include the movie (.nd2)")
        self.chk_movie.setToolTip("Copy the .nd2 too, so the backup can be opened anywhere.")
        self.chk_movie.setChecked(size is not None)
        self.chk_movie.setEnabled(size is not None)
        g.addWidget(self.chk_movie, 2, 0, 1, 2)
        warn = C.online_warning(self.nd2, found=self.places) if size is not None else ""
        self.lbl_online = W.wrapped_label(warn)
        self.lbl_online.setProperty("role", "warn")
        self.lbl_online.setVisible(bool(warn))
        g.addWidget(self.lbl_online, 3, 0, 1, 2)
        lay.addWidget(box)

        box = QGroupBox("Back up to")
        v = QVBoxLayout(box)
        v.setContentsMargins(10, 8, 10, 8)
        target = C.backup_root() or (self.places[0].path if self.places else "")
        self.lbl_target = _PathLabel(target, "choose a folder")
        self.btn_change = W.button("Change...", self._change,
                                   "Pick a cloud or network folder, or any folder.")
        r = QHBoxLayout()
        r.addWidget(self.lbl_target, 1)
        r.addWidget(self.btn_change)
        v.addLayout(r)
        v.addWidget(W.wrapped_label(f"Copied into <folder>/{C.BACKUP_DIR}/<movie>. Files already "
                                    "there are kept; nothing is overwritten.", muted=True))
        lay.addWidget(box)

        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setVisible(False)
        self.lbl_status = W.wrapped_label("")
        self.lbl_status.setVisible(False)
        lay.addWidget(self.bar)
        lay.addWidget(self.lbl_status)
        lay.addStretch(1)

        bl = QHBoxLayout()
        self.btn_open = W.button("Open backup folder", self._open,
                                 "Show the backup in Explorer / Finder.")
        self.btn_open.setVisible(False)
        bl.addWidget(self.btn_open)
        bl.addStretch(1)
        self.btn_cancel = W.button("Cancel", self._cancel_or_close, "Stop / close.")
        self.btn_go = W.button("Back up", self._start, "Start copying.", strong=True)
        bl.addWidget(self.btn_cancel)
        bl.addWidget(self.btn_go)
        lay.addLayout(bl)
        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._poll)
        self.resize(660, self.sizeHint().height())

    def _movie_size(self) -> Optional[int]:
        try:
            import os
            from ..safety import long_path
            return os.stat(long_path(self.nd2)).st_size
        except OSError:
            return None

    def _menu_choice(self) -> Optional[str]:                     # tests replace this
        m = place_menu(self, self.places)
        a = m.exec(self.btn_change.mapToGlobal(self.btn_change.rect().bottomLeft()))
        return None if a is None else str(a.data())

    def _change(self) -> None:
        choice = self._menu_choice()
        if choice is None:
            return
        path = _browse(self) if choice == "other" else choice
        if path and _check_folder(self, path):
            self.lbl_target.set_path(path)

    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _start(self) -> None:
        target = self.lbl_target.path()
        if not target:
            self._change()
            target = self.lbl_target.path()
            if not target:
                return
        if not _check_folder(self, target):
            return
        if target != C.backup_root():
            try:
                C.set_backup_root(target, check=False)
            except (OSError, ValueError):
                pass
        self._cancel.clear()
        self._state = {"done": 0, "total": 0, "name": "", "report": None, "error": None}
        include = self.chk_movie.isChecked()

        def progress(done, total, name):
            self._state.update(done=done, total=total, name=name)

        def work():
            try:
                self._state["report"] = C.backup(self.nd2, self.out_dir, target, include,
                                                 progress, self._cancel)
            except Exception as exc:                               # noqa: BLE001
                self._state["error"] = exc

        for w in (self.btn_go, self.btn_change, self.chk_movie):
            w.setEnabled(False)
        self.btn_open.setVisible(False)
        self.bar.setValue(0)
        self.bar.setVisible(True)
        self.lbl_status.setVisible(True)
        self.lbl_status.setText("Looking at what is already backed up...")
        self.btn_cancel.setText("Stop")
        self._thread = threading.Thread(target=work, daemon=True)
        self._thread.start()
        self._timer.start()

    def _poll(self) -> None:
        s = self._state
        if s.get("total"):
            self.bar.setValue(int(1000 * s["done"] / max(1, s["total"])))
            self.lbl_status.setText(f"Copying {s['name']} - {C.human_size(s['done'])} of "
                                    f"{C.human_size(s['total'])}")
        if self.running():
            return
        self._timer.stop()
        self._finish()

    def _finish(self) -> None:
        rep = self._state.get("report")
        err = self._state.get("error")
        self.report = rep
        self.btn_cancel.setText("Close")
        self.btn_go.setText("Back up again")
        for w in (self.btn_go, self.btn_change):
            w.setEnabled(True)
        self.chk_movie.setEnabled(self._movie_size() is not None)
        if err is not None or rep is None:
            self.lbl_status.setText(f"Not backed up: {err}")
            self.lbl_status.setProperty("role", "danger")
        else:
            text = rep.summary()
            if rep.failed:
                text += "\n" + "\n".join(f"- {Path(a).name}: {b}" for a, b in rep.failed[:3])
            self.lbl_status.setText(text)
            self.lbl_status.setProperty("role", "ok" if rep.ok else
                                        ("warn" if rep.cancelled else "danger"))
            self.bar.setValue(1000 if rep.ok else self.bar.value())
            self.btn_open.setVisible(bool(rep.folder) and not rep.problem)
        self.lbl_status.style().unpolish(self.lbl_status)
        self.lbl_status.style().polish(self.lbl_status)

    def _cancel_or_close(self) -> None:
        if self.running():
            self._cancel.set()
            self.lbl_status.setText("Stopping...")
            return
        self.reject()

    def reject(self) -> None:                                      # noqa: D401
        if self.running():                     # finish the file in progress, then close
            self._cancel.set()
            self._thread.join(timeout=30)
        super().reject()

    def _open(self) -> None:
        if self.report and self.report.folder:
            W.open_path(self.report.folder)


def backup_dialog(parent, nd2_path, out_dir) -> Optional[C.BackupReport]:
    """'Back up this analysis'. Returns the last backup's report (None if none ran)."""
    d = BackupDialog(parent, nd2_path, out_dir)
    d.exec()
    return d.report


__all__ = ["open_storage_dialog", "backup_dialog", "pick_place", "place_menu",
           "StorageDialog", "BackupDialog"]
