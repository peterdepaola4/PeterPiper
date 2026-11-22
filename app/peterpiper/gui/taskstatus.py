"""
PeterPiper 4.0: what runs in the background, for any window's corner.

    TaskStatusButton(parent)      a compact line - '↑ 2 uploading · ↓ 1 fetching ·
                                  1 export' - that opens the list on click
    TaskListPopup(parent)         the tasks with a bar each, time left, and Cancel /
                                  Retry / Open folder
    wait_for_movie(parent, nd2, on_ready, on_cancel=None) -> MovieWait
                                  'Next movie' while the movie is still being fetched:
                                  a small window with a bar - never blocks the program;
                                  on_ready(local path) once it is here

Everything follows tasks.center() through tasks.qt_bridge() (signals in the window
thread); nothing here reads or writes files.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, Optional

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel, QProgressBar,
                               QPushButton, QSizePolicy, QToolButton, QVBoxLayout, QWidget)

from .. import tasks as T
from . import widgets as W
from .tips import tip

MAX_ROWS = 10
IDLE = "No background tasks"


def _bridge():
    return T.qt_bridge()


def _style(label: QLabel, role: str = "", muted: bool = False) -> None:
    label.setProperty("role", role)
    label.setProperty("muted", muted)
    label.style().unpolish(label)
    label.style().polish(label)


# ================================================================= the line
class TaskStatusButton(QToolButton):
    """The compact status. Text: what runs ('↑ 2 uploading · 1 export'), a failure
    ('⚠ 1 upload failed - click'), or 'No background tasks'. Click: the list."""

    def __init__(self, parent: Optional[QWidget] = None,
                 center: Optional[T.TaskCenter] = None, hide_when_idle: bool = False) -> None:
        super().__init__(parent)
        self.center = center or T.center()
        self.hide_when_idle = hide_when_idle
        self.setAutoRaise(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        tip(self, "Copies, uploads, exports and movie fetches run in the background while "
                  "you work - Next movie never waits for them. Click to see each one, "
                  "with its time left, Cancel, Retry and Open folder.",
            title="Background tasks")
        self.popup: Optional[TaskListPopup] = None
        b = _bridge()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self.refresh)
        for sig in (b.added, b.changed, b.finished):
            sig.connect(self._soon)
        b.cleared.connect(self._soon)
        self.clicked.connect(self.open_list)
        self.refresh()

    def _soon(self, *_a) -> None:
        if not self._timer.isActive():
            self._timer.start()

    def text_now(self) -> str:
        s = self.center.status_text()
        if s:
            return s
        failed = [t for t in self.center.failed()]
        if failed:
            n = len(failed)
            return f"⚠ {n} task{'s' if n != 1 else ''} failed - click"
        return IDLE

    def refresh(self) -> None:
        txt = self.text_now()
        self.setText(txt)
        self.setVisible(not (self.hide_when_idle and txt == IDLE))

    def open_list(self) -> "TaskListPopup":
        if self.popup is None:
            self.popup = TaskListPopup(self, self.center)
        self.popup.refill()
        self.popup.adjustSize()
        pos = self.mapToGlobal(QPoint(0, 0))
        self.popup.move(max(0, pos.x() + self.width() - self.popup.width()),
                        max(0, pos.y() - self.popup.height() - 4))
        self.popup.show()
        self.popup.raise_()
        return self.popup


# ================================================================ the list
class TaskRow(QFrame):
    def __init__(self, task: T.Task, parent: "TaskListPopup") -> None:
        super().__init__(parent)
        self.task, self.owner = task, parent
        self.setFrameShape(QFrame.NoFrame)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 4, 2, 4)
        lay.setSpacing(2)
        top = QHBoxLayout()
        self.lbl_title = QLabel(task.title)
        self.lbl_title.setToolTip(task.title + (f"\n{task.data.get('path')}"
                                                if task.data.get("path") else ""))
        top.addWidget(self.lbl_title, 1)
        self.btn_cancel = W.button("Cancel", self._cancel, "Stop this task (what is half-"
                                   "copied is removed; nothing else changes).")
        self.btn_retry = W.button("Retry", self._retry, "Try this task again.")
        self.btn_open = W.button("Open folder", self._open, "Show where it went "
                                 "(Explorer / Finder).")
        for b in (self.btn_cancel, self.btn_retry, self.btn_open):
            b.setAutoDefault(False)
            top.addWidget(b)
        lay.addLayout(top)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        lay.addWidget(self.bar)
        self.lbl_state = QLabel("")
        _style(self.lbl_state, muted=True)
        lay.addWidget(self.lbl_state)
        self.update_row()

    def update_row(self) -> None:
        t = self.task
        running = t.state in (T.QUEUED, T.RUNNING)
        if t.progress is None and t.state == T.RUNNING:
            self.bar.setRange(0, 0)                    # moving: not known yet
        else:
            self.bar.setRange(0, 1000)
            self.bar.setValue(int(1000 * (t.progress or 0.0)) if t.state != T.DONE else 1000)
        self.lbl_state.setText(t.summary())
        _style(self.lbl_state, "danger" if t.state == T.FAILED else
               "ok" if t.state == T.DONE else "", muted=t.state not in (T.FAILED, T.DONE))
        if t.state == T.FAILED:
            self.lbl_state.setToolTip(t.error)
        self.btn_cancel.setVisible(running)
        self.btn_retry.setVisible(t.state in (T.FAILED, T.CANCELLED))
        self.btn_open.setVisible(bool(t.data.get("folder")) and t.state == T.DONE)

    def _cancel(self) -> None:
        self.task.cancel()
        self.update_row()

    def _retry(self) -> None:
        self.owner.center.retry(self.task)
        self.owner.refill()

    def _open(self) -> None:
        W.open_path(self.task.data.get("folder") or "")


class TaskListPopup(QDialog):
    """The background tasks, newest first: running and waiting ones, then the last
    finished ones."""

    def __init__(self, parent: Optional[QWidget] = None,
                 center: Optional[T.TaskCenter] = None) -> None:
        super().__init__(parent, Qt.Tool)
        self.center = center or T.center()
        self.setWindowTitle("Background tasks")
        self.setMinimumWidth(440)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(4)
        head = QLabel("Background tasks")
        head.setProperty("role", "subtitle")
        lay.addWidget(head)
        self.box = QVBoxLayout()
        self.box.setSpacing(2)
        lay.addLayout(self.box)
        self.lbl_none = QLabel("Nothing runs in the background now.")
        _style(self.lbl_none, muted=True)
        lay.addWidget(self.lbl_none)
        bl = QHBoxLayout()
        bl.addStretch(1)
        self.btn_clear = W.button("Clear finished", self._clear, "Take the finished tasks "
                                  "off this list.")
        self.btn_close = W.button("Close", self.hide, "")
        for b in (self.btn_clear, self.btn_close):
            b.setAutoDefault(False)
            bl.addWidget(b)
        lay.addLayout(bl)
        self.rows: Dict[int, TaskRow] = {}
        b = _bridge()
        b.added.connect(self._added)
        b.changed.connect(self._changed)
        b.finished.connect(self._changed)

    def _visible_tasks(self):
        ts = [t for t in self.center.tasks() if not t.data.get("quiet")]
        act = [t for t in ts if not t.finished]
        ended = sorted((t for t in ts if t.finished), key=lambda t: -t.ended)
        return (sorted(act, key=lambda t: (t.state != T.RUNNING, t.priority, t.id))
                + ended)[:MAX_ROWS]

    def refill(self) -> None:
        for r in self.rows.values():
            self.box.removeWidget(r)
            r.deleteLater()
        self.rows = {}
        for t in self._visible_tasks():
            r = TaskRow(t, self)
            self.rows[t.id] = r
            self.box.addWidget(r)
        self.lbl_none.setVisible(not self.rows)
        self.btn_clear.setEnabled(any(t.finished for t in self.center.tasks()))
        self.adjustSize()

    def _added(self, _task) -> None:
        if self.isVisible():
            self.refill()

    def _changed(self, task) -> None:
        if not self.isVisible() or task is None:
            return
        r = self.rows.get(task.id)
        if r is None:
            self.refill()
        else:
            r.update_row()
            self.btn_clear.setEnabled(any(t.finished for t in self.center.tasks()))

    def _clear(self) -> None:
        self.center.clear_ended()
        self.refill()


# ======================================================== waiting for a movie
class MovieWait(QDialog):
    """'Next movie' while the movie is still being copied here: a bar, the time
    left, Cancel. Not modal - the rest of the program keeps working."""

    def __init__(self, parent: Optional[QWidget], task: T.Task,
                 on_ready: Callable[[str], None],
                 on_cancel: Optional[Callable[[], None]] = None) -> None:
        super().__init__(parent)
        self.task, self.on_ready, self.on_cancel = task, on_ready, on_cancel
        self.setWindowTitle("Getting the movie")
        self.setModal(False)
        lay = QVBoxLayout(self)
        name = Path(str(task.data.get("path") or task.title)).name
        self.lbl = QLabel(f"Copying {name} from the lab folder to this computer...")
        lay.addWidget(self.lbl)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        lay.addWidget(self.bar)
        self.lbl_left = QLabel("")
        _style(self.lbl_left, muted=True)
        lay.addWidget(self.lbl_left)
        note = QLabel("Big movies are copied here first so they open and scroll fast. "
                      "You can keep working meanwhile.")
        note.setWordWrap(True)
        _style(note, muted=True)
        lay.addWidget(note)
        bl = QHBoxLayout()
        bl.addStretch(1)
        self.btn_retry = W.button("Retry", self._retry, "Try copying it again.")
        self.btn_retry.setVisible(False)
        self.btn_cancel = W.button("Cancel", self._cancel, "Do not open it now (the copy "
                                   "stops; you can open it later).")
        for b in (self.btn_retry, self.btn_cancel):
            b.setAutoDefault(False)
            bl.addWidget(b)
        lay.addLayout(bl)
        self.resize(460, self.sizeHint().height())
        self._done = False
        b = _bridge()
        b.changed.connect(self._changed)
        b.finished.connect(self._changed)
        self._changed(task)

    def _changed(self, t) -> None:
        if t is not self.task or self._done:
            return
        if t.state == T.DONE:
            self._done = True
            self.bar.setValue(1000)
            self.accept()
            self.on_ready(str(t.result))
            return
        if t.state == T.FAILED:
            self.lbl_left.setText("Could not copy it: " + t.error)
            _style(self.lbl_left, "danger")
            self.btn_retry.setVisible(True)
            return
        if t.state == T.CANCELLED:
            self._done = True
            self.reject()
            return
        self.bar.setValue(int(1000 * (t.progress or 0.0)))
        self.lbl_left.setText("waiting for another copy to finish..." if t.state == T.QUEUED
                              else t.summary())

    def _retry(self) -> None:
        self.task = self.task.center.retry(self.task)
        self.task.center.bump(self.task, 0)
        self.btn_retry.setVisible(False)
        _style(self.lbl_left, muted=True)
        self._changed(self.task)

    def _cancel(self) -> None:
        if not self.task.finished:
            self.task.cancel()
        self._done = True
        self.reject()
        if self.on_cancel is not None:
            self.on_cancel()


def wait_for_movie(parent: Optional[QWidget], nd2: str, on_ready: Callable[[str], None],
                   on_cancel: Optional[Callable[[], None]] = None,
                   center: Optional[T.TaskCenter] = None) -> Optional[MovieWait]:
    """Open `nd2` as soon as it is on this computer: fetch it first when it is in the
    lab folder (online-only / network) - a small window with a bar meanwhile. When
    it is here already (or cached), on_ready(path) is called at once (well, on the
    next turn of the event loop) and None is returned. Never blocks."""
    from .. import transfers
    _bridge()
    t = transfers.fetch_movie(nd2, center=center, priority=0)
    try:
        from .. import batchqueue
        batchqueue.prefetch_next(nd2, 1)
    except Exception:                                              # noqa: BLE001
        pass
    if t.finished and t.state == T.DONE:
        QTimer.singleShot(0, lambda: on_ready(str(t.result)))
        return None
    w = MovieWait(parent, t, on_ready, on_cancel)
    # a quick one (on this computer, or cached): no window flashes up
    QTimer.singleShot(400, lambda: (w.show() if not w._done else None))
    return w
