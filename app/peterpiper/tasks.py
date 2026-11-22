"""
PeterPiper 4.0: the background task center - long jobs (uploads, fetching a movie
from the lab folder, exports, writing viewing copies, autosaves, copies, backups)
run in their own threads, never in the window's thread, so 'Next movie' is never
blocked by them. One center for the whole program (center()); a task holds its own
data, so it carries on when the analysis window closes or the next movie opens.

    c = center()
    t = c.submit("export", "Excel for movie 3", fn, on_done=None)
        fn(progress, cancelled) -> result
            progress(fraction=None, done=None, total=None, detail=None) -> bool
                (fraction 0-1, or bytes done / total; returns False once cancelled)
            cancelled() -> True once the user pressed Cancel (stop soon; raising
                tasks.Cancelled or returning both end the task as 'cancelled')
    t.state            queued / running / done / failed / cancelled
    t.progress         0-1 (None: not known yet), t.bytes_done / t.bytes_total,
    t.speed            bytes per second, t.time_left seconds (None: not known)
    t.cancel(), c.retry(t) -> a new task doing the same again, t.wait(timeout)
    c.status_text()    '↑ 2 uploading · ↓ 1 fetching · 1 export'

At most MAX_HEAVY disk-heavy tasks run at once (copies, exports, viewing copies,
fetches) and MAX_LIGHT light ones (autosaves, small notes); the others wait in
the queue, lower `priority` first (0: the movie the user is waiting for).
`key`: a task with the same key still waiting in the queue is reused instead of
adding another (e.g. two uploads of the same results folder).

on_done(task) is called once the task ended (any state). Without the Qt bridge it
runs in the task's thread; once qt_bridge() was made (gui/taskstatus.py makes it)
it runs in the window thread, and the bridge's signals (added, changed, finished)
tell windows about every task - changed at most ~10 times a second per task.

This module has no Qt in its core and no network code.
"""
from __future__ import annotations

import itertools
import threading
import time
import traceback
from typing import Callable, Dict, List, Optional

QUEUED, RUNNING, DONE, FAILED, CANCELLED = "queued", "running", "done", "failed", "cancelled"
ENDED = (DONE, FAILED, CANCELLED)
MAX_HEAVY = 2
MAX_LIGHT = 3
KEEP_ENDED = 40                     # ended tasks kept in the list (newest)
HEAVY_KINDS = {"upload", "fetch", "prefetch", "export", "viewing", "copy", "backup"}
# kind: (arrow, words for one, words for several) for the status line
KIND_WORDS = {"upload": ("↑", "uploading", "uploading"),
              "fetch": ("↓", "fetching", "fetching"),
              "prefetch": ("↓", "fetching", "fetching"),
              "export": ("", "export", "exports"),
              "viewing": ("", "viewing copy", "viewing copies"),
              "autosave": ("", "autosave", "autosaves"),
              "copy": ("", "copy", "copies"),
              "backup": ("", "backup", "backups")}
_ORDER = ("upload", "fetch", "prefetch", "export", "viewing", "copy", "backup", "autosave")


class Cancelled(Exception):
    """Raised inside a task to stop because the user cancelled."""


_ids = itertools.count(1)


class Task:
    def __init__(self, center: "TaskCenter", kind: str, title: str, fn: Callable,
                 on_done: Optional[Callable] = None, heavy: Optional[bool] = None,
                 priority: int = 5, data: Optional[dict] = None,
                 key: Optional[str] = None) -> None:
        self.id = next(_ids)
        self.center = center
        self.kind, self.title, self.fn, self.on_done = str(kind), str(title), fn, on_done
        self.heavy = (kind in HEAVY_KINDS) if heavy is None else bool(heavy)
        self.priority = int(priority)
        # e.g. {"folder": ..., "path": ...}; the job may add to it while it runs
        self.data: dict = data if isinstance(data, dict) else {}
        self.key = key
        self.state = QUEUED
        self.progress: Optional[float] = None
        self.bytes_done = 0
        self.bytes_total = 0
        self.detail = ""
        self.result = None
        self.error = ""
        self.trace = ""
        self.created = time.time()
        self.started = 0.0
        self.ended = 0.0
        self._cancel = threading.Event()
        self._ended = threading.Event()
        self._samples: List[tuple] = []             # (monotonic time, fraction, bytes)
        self._last_emit = 0.0

    # ------------------------------------------------------------ for the job
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def report(self, fraction=None, done=None, total=None, detail=None) -> bool:
        if done is not None:
            self.bytes_done = int(done)
        if total is not None:
            self.bytes_total = int(total)
        if fraction is None and done is not None and self.bytes_total > 0:
            fraction = self.bytes_done / self.bytes_total
        if fraction is not None:
            self.progress = float(min(1.0, max(0.0, fraction)))
        if detail is not None:
            self.detail = str(detail)
        now = time.monotonic()
        self._samples.append((now, self.progress, self.bytes_done))
        while len(self._samples) > 2 and now - self._samples[0][0] > 12.0:
            self._samples.pop(0)
        self.center._changed(self)
        return not self._cancel.is_set()

    # ------------------------------------------------------------ for windows
    def cancel(self) -> None:
        self.center.cancel(self)

    def wait(self, timeout: Optional[float] = None) -> bool:
        return self._ended.wait(timeout)

    @property
    def finished(self) -> bool:
        return self.state in ENDED

    @property
    def speed(self) -> Optional[float]:
        """Bytes per second over the last few seconds (None: not known)."""
        s = [x for x in self._samples if x[2]]
        if len(s) < 2 or s[-1][0] - s[0][0] < 0.3:
            return None
        return max(0.0, (s[-1][2] - s[0][2]) / (s[-1][0] - s[0][0]))

    @property
    def time_left(self) -> Optional[float]:
        """Seconds left (None: not known yet)."""
        if self.state != RUNNING:
            return 0.0 if self.state == DONE else None
        if self.bytes_total > 0 and self.speed:
            return max(0.0, (self.bytes_total - self.bytes_done) / self.speed)
        s = [x for x in self._samples if x[1] is not None]
        if len(s) < 2 or s[-1][1] <= 0:
            return None
        dt, df = s[-1][0] - s[0][0], s[-1][1] - s[0][1]
        if dt < 0.5 or df <= 0:
            el = time.monotonic() - (self._t0 if hasattr(self, "_t0") else s[0][0])
            return el * (1 - s[-1][1]) / s[-1][1] if s[-1][1] > 0.02 and el > 1 else None
        return max(0.0, (1.0 - s[-1][1]) * dt / df)

    def summary(self) -> str:
        """'45% · 12 MB/s · about 2 min left' / 'waiting' / 'done' ..."""
        if self.state == QUEUED:
            return "waiting"
        if self.state == DONE:
            return "done"
        if self.state == CANCELLED:
            return "cancelled"
        if self.state == FAILED:
            return "failed: " + (self.error or "unknown error")
        parts = []
        if self.progress is not None:
            parts.append(f"{100 * self.progress:.0f}%")
        sp = self.speed
        if sp:
            parts.append(f"{human_bytes(sp)}/s")
        left = self.time_left
        if left is not None and left > 1:
            parts.append(f"about {fmt_seconds(left)} left")
        return " · ".join(parts) or "working..."

    def __repr__(self) -> str:
        return f"<Task {self.id} {self.kind} {self.state} {self.title!r}>"


def human_bytes(n: float) -> str:
    n = float(n)
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1000 or unit == "GB":
            return f"{int(n)} bytes" if unit == "bytes" else (
                f"{n:.1f} {unit}" if n < 100 else f"{n:.0f} {unit}")
        n /= 1000.0
    return f"{n:.1f} TB"


def fmt_seconds(s: float) -> str:
    s = max(0.0, float(s))
    if s < 60:
        return f"{max(1, int(round(s)))} s" if s < 10 else f"{int(round(s / 5.0) * 5)} s"
    if s < 3600:
        return f"{int(round(s / 60.0))} min"
    return f"{s / 3600:.1f} h"


class TaskCenter:
    """See the top of the module."""

    def __init__(self, max_heavy: int = MAX_HEAVY, max_light: int = MAX_LIGHT) -> None:
        self.max_heavy, self.max_light = int(max_heavy), int(max_light)
        self._lock = threading.RLock()
        self._tasks: List[Task] = []
        self._listeners: List[Callable] = []
        self.ui_call: Optional[Callable[[Callable], None]] = None   # set by the Qt bridge
        self._closed = False

    # ------------------------------------------------------------- adding
    def submit(self, kind: str, title: str, fn: Callable, on_done: Optional[Callable] = None,
               heavy: Optional[bool] = None, priority: int = 5, data: Optional[dict] = None,
               key: Optional[str] = None) -> Task:
        with self._lock:
            if key is not None:
                for t in self._tasks:
                    if t.key == key and t.state == QUEUED:
                        if on_done is not None and t.on_done is None:
                            t.on_done = on_done
                        t.priority = min(t.priority, int(priority))
                        return t
            t = Task(self, kind, title, fn, on_done, heavy, priority, data, key)
            self._tasks.append(t)
            self._trim()
        self._notify(t, "added")
        self._pump()
        return t

    def retry(self, task: Task) -> Task:
        """The same job again, as a new task (for a failed or cancelled one)."""
        return self.submit(task.kind, task.title, task.fn, task.on_done, task.heavy,
                           task.priority, task.data, task.key)

    def bump(self, task: Task, priority: int = 0) -> None:
        """Run this waiting task next (e.g. the movie the user now waits for)."""
        with self._lock:
            task.priority = min(task.priority, int(priority))
        self._pump()

    def cancel(self, task: Task) -> None:
        task._cancel.set()
        with self._lock:
            if task.state == QUEUED:
                task.state = CANCELLED
                task.ended = time.time()
            else:
                task = None
        if task is not None:
            self._end(task)

    def cancel_all(self) -> None:
        for t in self.active():
            self.cancel(t)

    # ------------------------------------------------------------ looking
    def tasks(self, include_ended: bool = True) -> List[Task]:
        with self._lock:
            return [t for t in self._tasks if include_ended or t.state not in ENDED]

    def active(self) -> List[Task]:
        return self.tasks(include_ended=False)

    def find(self, key: str, include_ended: bool = False) -> Optional[Task]:
        """The newest task with this key (unfinished only, unless include_ended)."""
        with self._lock:
            for t in reversed(self._tasks):
                if t.key == key and (include_ended or t.state not in ENDED):
                    return t
        return None

    def counts(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for t in self.active():
            k = "fetch" if t.kind == "prefetch" else t.kind
            out[k] = out.get(k, 0) + 1
        return out

    def status_text(self) -> str:
        """'↑ 2 uploading · ↓ 1 fetching · 1 export' ('' when nothing runs)."""
        c = self.counts()
        parts = []
        for k in sorted(c, key=lambda k: (_ORDER.index(k) if k in _ORDER else 99, k)):
            arrow, one, many = KIND_WORDS.get(k, ("", k, k))
            parts.append(f"{arrow + ' ' if arrow else ''}{c[k]} {one if c[k] == 1 else many}")
        return " · ".join(parts)

    def failed(self) -> List[Task]:
        return [t for t in self.tasks() if t.state == FAILED]

    def wait_all(self, timeout: Optional[float] = None) -> bool:
        end = None if timeout is None else time.monotonic() + timeout
        while True:
            act = self.active()
            if not act:
                return True
            left = None if end is None else end - time.monotonic()
            if left is not None and left <= 0:
                return False
            act[0].wait(0.05 if left is None else min(0.05, left))

    def clear_ended(self) -> None:
        with self._lock:
            self._tasks = [t for t in self._tasks if t.state not in ENDED]
        self._notify(None, "cleared")

    def shutdown(self, timeout: float = 5.0) -> bool:
        """At program end: nothing new starts; wait up to `timeout` s for the running
        ones. True when all ended."""
        with self._lock:
            self._closed = True
        return self.wait_all(timeout)

    # ------------------------------------------------------------ listeners
    def add_listener(self, fn: Callable[[Optional[Task], str], None]) -> None:
        """fn(task, what): what = 'added' | 'changed' | 'state' | 'cleared'. Called in
        the thread where it happened - the Qt bridge passes it to the window thread."""
        with self._lock:
            self._listeners.append(fn)

    def remove_listener(self, fn) -> None:
        with self._lock:
            if fn in self._listeners:
                self._listeners.remove(fn)

    def _notify(self, task: Optional[Task], what: str) -> None:
        for fn in list(self._listeners):
            try:
                fn(task, what)
            except Exception:                                      # noqa: BLE001
                pass

    def _changed(self, task: Task) -> None:
        now = time.monotonic()
        if now - task._last_emit >= 0.1:
            task._last_emit = now
            self._notify(task, "changed")

    # ------------------------------------------------------------ running
    def _trim(self) -> None:
        ended = [t for t in self._tasks if t.state in ENDED]
        if len(ended) > KEEP_ENDED:
            drop = set(id(t) for t in ended[:len(ended) - KEEP_ENDED])
            self._tasks = [t for t in self._tasks if id(t) not in drop]

    def _pump(self) -> None:
        start = []
        with self._lock:
            if self._closed:
                return
            run_h = sum(1 for t in self._tasks if t.state == RUNNING and t.heavy)
            run_l = sum(1 for t in self._tasks if t.state == RUNNING and not t.heavy)
            for t in sorted((t for t in self._tasks if t.state == QUEUED),
                            key=lambda t: (t.priority, t.id)):
                if t.heavy and run_h < self.max_heavy:
                    run_h += 1
                elif not t.heavy and run_l < self.max_light:
                    run_l += 1
                else:
                    continue
                t.state = RUNNING
                t.started = time.time()
                t._t0 = time.monotonic()
                start.append(t)
        for t in start:
            self._notify(t, "state")
            th = threading.Thread(target=self._run, args=(t,), daemon=True,
                                  name=f"PeterPiper task {t.id} {t.kind}")
            th.start()

    def _run(self, t: Task) -> None:
        try:
            res = t.fn(t.report, t.cancelled)
            t.result = res
            t.state = CANCELLED if t.cancelled() else DONE
            if t.state == DONE:
                t.progress = 1.0
                if t.bytes_total:
                    t.bytes_done = t.bytes_total
        except Cancelled:
            t.state = CANCELLED
        except BaseException as exc:                               # noqa: BLE001
            if t.cancelled():
                t.state = CANCELLED
            else:
                t.state = FAILED
                t.error = _error_text(exc)
                t.trace = traceback.format_exc()
        t.ended = time.time()
        self._end(t)
        self._pump()

    def _end(self, t: Task) -> None:
        t._ended.set()
        self._notify(t, "state")
        if t.on_done is not None:
            cb = t.on_done

            def call(cb=cb, t=t):
                try:
                    cb(t)
                except Exception:                                  # noqa: BLE001
                    traceback.print_exc()
            if self.ui_call is not None:
                self.ui_call(call)
            else:
                call()


def _error_text(exc: BaseException) -> str:
    if isinstance(exc, OSError) and not exc.filename and exc.strerror:
        return str(exc.strerror)                   # without '[Errno 28]'
    try:
        from .safety import error_text
        return error_text(exc)
    except Exception:                                              # noqa: BLE001
        return str(exc) or type(exc).__name__


_center: Optional[TaskCenter] = None
_center_lock = threading.Lock()


def center() -> TaskCenter:
    """The program's one task center."""
    global _center
    with _center_lock:
        if _center is None:
            _center = TaskCenter()
        return _center


# ============================================================== the Qt bridge
_bridge = None


def qt_bridge(c: Optional[TaskCenter] = None):
    """The center's Qt side (made once, in the window thread): signals added(task),
    changed(task), finished(task) arrive in the window thread; on_done callbacks run
    there too from now on. Needs a QApplication."""
    global _bridge
    if _bridge is not None:
        return _bridge
    from PySide6.QtCore import QCoreApplication, QObject, Qt, Signal

    class TaskBridge(QObject):
        added = Signal(object)
        changed = Signal(object)
        finished = Signal(object)
        cleared = Signal()
        _call = Signal(object)

        def __init__(self, cen: TaskCenter) -> None:
            super().__init__()
            app = QCoreApplication.instance()
            if app is not None and self.thread() is not app.thread():
                self.moveToThread(app.thread())
            self.center = cen
            self._call.connect(self._do, Qt.QueuedConnection)
            cen.ui_call = self._call.emit
            cen.add_listener(self._heard)

        def _do(self, fn) -> None:
            fn()

        def _heard(self, task, what: str) -> None:
            if what == "added":
                self.added.emit(task)
            elif what == "cleared":
                self.cleared.emit()
            elif what == "state" and task is not None and task.finished:
                self.changed.emit(task)
                self.finished.emit(task)
            else:
                self.changed.emit(task)

    _bridge = TaskBridge(c or center())
    return _bridge
