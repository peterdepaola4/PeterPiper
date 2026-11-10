"""
Background workers.

Anything that takes more than a moment (reading the file, detecting, tracking,
writing TIFFs or the workbook) runs in a QThread so the window stays responsive
and the progress bar keeps moving. Each worker reports progress as
(fraction 0-1, message) and can be cancelled.

BLOCK: new long jobs subclass Job and implement run_job().
"""
from __future__ import annotations

import threading
import time
import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QThread, Signal


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

    # available to run_job as the `progress` callback of the core functions
    def progress(self, fraction: float, message: str) -> bool:
        self.progressed.emit(float(fraction), str(message))
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
                 on_cancel=None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.job = job
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
        self.thread.start()

    def cancel(self) -> None:
        self.job.cancel()

    def is_running(self) -> bool:
        return self.thread.isRunning()

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
        return True

    def _wrap_up(self, *_: Any) -> None:
        self.thread.quit()
        self.thread.wait(5000)
