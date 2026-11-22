"""
Background workers.

Anything that takes more than a moment (reading the file, detecting, tracking,
writing TIFFs or the workbook) runs in a QThread so the window stays responsive
and the progress bar keeps moving. Each worker reports progress as
(fraction 0-1, message) and can be cancelled.

4.0: several jobs may run at once. A JobRunner is EXCLUSIVE by default (the
analysis window's own tracking / loading: the window greys its buttons while it
runs - unchanged); JobRunner(..., exclusive=False) or JobPool.start(...) runs a
BACKGROUND job beside it (a viewing copy, an export, an upload) that never
blocks the window. Every running runner is listed (running(),
exclusive_running()) and kept alive until it has finished, so nothing assumes a
single runner. Long FILE jobs with a visible list (uploads, copies) belong in
tasks.py's TaskCenter; this module only runs the threads.

BLOCK: new long jobs subclass Job and implement run_job().
"""
from __future__ import annotations

import threading
import time
import traceback
from typing import Any, Callable, List, Optional

from PySide6.QtCore import QObject, QThread, Signal

# 4.0: every runner whose thread was started and has not wrapped up yet (strong
# references: a running QThread must never be garbage-collected)
_ACTIVE: List["JobRunner"] = []
_LOCK = threading.Lock()


class Job(QObject):
    """A unit of slow work. Subclass and implement run_job()."""

    progressed = Signal(float, str)
    finished = Signal(object)
    failed = Signal(str, str)
    cancelled = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._cancel = False
        self.stopped = threading.Event()               # set when run() has returned

    # called from the GUI thread
    def cancel(self) -> None:
        self._cancel = True

    # available to run_job as the `progress` callback of the core functions.
    # 1.2: fraction None = not known (sent as -1: a moving bar and the time so far);
    # detail (or the part of message after a line break) names what is being
    # worked on - ProgressStrip.update shows it on the message line.
    def progress(self, fraction, message: str = "", detail=None) -> bool:
        f = -1.0 if fraction is None else float(fraction)
        msg = str(message or "")
        if detail:
            msg = f"{msg}\n{detail}"
        self.progressed.emit(f, msg)
        return not self._cancel

    def run_job(self) -> Any:
        raise NotImplementedError

    def run(self) -> None:
        try:
            self._run()
        finally:
            self.stopped.set()

    def _run(self) -> None:
        try:
            result = self.run_job()
        except Exception as exc:                       # noqa: BLE001
            # A job stopped by the user is not an error.
            if self._cancel or type(exc).__name__ == "Cancelled":
                self.cancelled.emit()
                return
            from ..safety import error_text
            self.failed.emit(error_text(exc), traceback.format_exc())
            return
        if self._cancel:
            self.cancelled.emit()
            return
        self.finished.emit(result)


class FuncJob(Job):
    """Wrap any function whose last keyword argument is `progress`."""

    def __init__(self, fn: Callable[..., Any], *args, **kwargs) -> None:
        super().__init__()
        self._fn, self._args, self._kwargs = fn, args, kwargs

    def run_job(self) -> Any:
        return self._fn(*self._args, progress=self.progress, **self._kwargs)


class JobRunner(QObject):
    """
    Keeps a job and its thread alive for the duration of the work.

    Usage:
        self.runner = JobRunner(job, on_done=..., on_fail=..., on_progress=...)
        self.runner.start()
    """

    def __init__(self, job: Job, on_done=None, on_fail=None, on_progress=None,
                 on_cancel=None, parent: QObject | None = None, exclusive: bool = True,
                 name: str = "") -> None:
        super().__init__(parent)
        self.job = job
        self.exclusive = bool(exclusive)       # 4.0: False = a background job beside others
        self.name = str(name or type(job).__name__)
        self._done = False
        self.thread = QThread()
        job.moveToThread(self.thread)
        self.thread.started.connect(job.run)
        self._cb = dict(done=on_done, fail=on_fail, progress=on_progress, cancel=on_cancel)
        # Bound methods of this object (which lives in the GUI thread): Qt queues
        # them, so every callback - lambdas included - runs in the GUI thread.
        job.progressed.connect(self._on_progress)
        job.finished.connect(self._on_finished)
        job.failed.connect(self._on_failed)
        job.cancelled.connect(self._on_cancelled)

    def _on_progress(self, f: float, m: str) -> None:
        if self._cb["progress"]:
            self._cb["progress"](f, m)

    def _on_finished(self, result: Any) -> None:
        self._wrap_up()
        if self._cb["done"]:
            self._cb["done"](result)

    def _on_failed(self, msg: str, detail: str) -> None:
        self._wrap_up()
        if self._cb["fail"]:
            self._cb["fail"](msg, detail)

    def _on_cancelled(self) -> None:
        self._wrap_up()
        if self._cb["cancel"]:
            self._cb["cancel"]()

    def start(self) -> None:
        with _LOCK:
            if self not in _ACTIVE:
                _ACTIVE.append(self)
        self.thread.start()

    def cancel(self) -> None:
        self.job.cancel()

    def is_running(self) -> bool:
        return self.thread.isRunning()

    def is_finished(self) -> bool:
        """True once the job's result / failure / cancel has been handled."""
        return self._done

    def stop_and_wait(self, timeout: float = 120.0, pump=None) -> bool:
        """Cancel the job and wait until its work has really stopped (closing the
        window: the .nd2 must not be closed under a running job). pump (e.g.
        QApplication.processEvents) keeps the window painted meanwhile.
        True when stopped."""
        self.job.cancel()
        end = time.monotonic() + timeout
        while not self.job.stopped.wait(0.05):
            if pump is not None:
                pump()
            if time.monotonic() > end:
                return False
        self.thread.quit()
        self.thread.wait(5000)
        self._forget()
        return True

    def _wrap_up(self, *_: Any) -> None:
        self.thread.quit()
        self.thread.wait(5000)
        self._done = True
        self._forget()

    def _forget(self) -> None:
        with _LOCK:
            if self in _ACTIVE:
                _ACTIVE.remove(self)


def running(exclusive: Optional[bool] = None) -> List[JobRunner]:
    """4.0: the runners started and not yet wrapped up (exclusive=True / False:
    only those kinds)."""
    with _LOCK:
        got = list(_ACTIVE)
    return [r for r in got if exclusive is None or r.exclusive == exclusive]


def exclusive_running() -> bool:
    """True while an exclusive job (the window's own tracking / loading) runs."""
    return any(r.is_running() for r in running(exclusive=True))


class JobPool(QObject):
    """
    4.0: several background (non-exclusive) jobs at once, each kept alive until
    it has finished. Usage:

        self.pool = JobPool(self)
        self.pool.start(FuncJob(fn, ...), on_done=..., name="viewing copy")
        self.pool.running()      # the jobs still going
        self.pool.stop_all(pump=QApplication.processEvents)   # closing the window
    """

    changed = Signal()                    # a job started or ended

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._runners: List[JobRunner] = []

    def start(self, job: Job, on_done=None, on_fail=None, on_progress=None, on_cancel=None,
              name: str = "") -> JobRunner:
        def wrap(cb):
            def call(*a):
                self._drop(runner)
                if cb:
                    cb(*a)
            return call
        runner = JobRunner(job, on_done=wrap(on_done), on_fail=wrap(on_fail),
                           on_progress=on_progress, on_cancel=wrap(on_cancel),
                           parent=self, exclusive=False, name=name)
        self._runners.append(runner)
        runner.start()
        self.changed.emit()
        return runner

    def _drop(self, runner: JobRunner) -> None:
        if runner in self._runners:
            self._runners.remove(runner)
            self.changed.emit()

    def running(self) -> List[JobRunner]:
        return [r for r in self._runners if not r.is_finished()]

    def count(self) -> int:
        return len(self.running())

    def cancel_all(self) -> None:
        for r in list(self._runners):
            r.cancel()

    def stop_all(self, timeout: float = 120.0, pump=None) -> bool:
        """Cancel every job and wait for each (closing the window). True when all stopped."""
        ok = True
        for r in list(self._runners):
            ok = r.stop_and_wait(timeout, pump) and ok
            self._drop(r)
        return ok
