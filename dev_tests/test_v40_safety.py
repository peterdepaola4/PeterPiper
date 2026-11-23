"""
Developer test (not shipped): PeterPiper 4.0 - the background-work safety fixes found in
review (integration). Synthetic movie only (dev_tests/synthmovie.py); made-up names.

Checks
  A  two analysis windows in a row in one process (as app.run_loop: app.exec() per
     window, so aboutToQuit comes after each): the task center stays open, the quit
     backup does not run then; in the SECOND window autosave writes its session and
     a background export finishes; a task submitted to a closed center still runs
  B  the real end with jobs running (app.finish_background): 'wait' waits for them,
     'cancel' cancels them; an export cut off is marked: 'EXPORT NOT FINISHED.txt'
     while it runs, folder renamed ..._INCOMPLETE when it stops on an error
  C  SAVE while an automatic re-track is pending: the update finishes first (the file
     has the current tracking); when it cannot (a setting changed: everything must be
     tracked again) the earlier tracking is saved, marked stale, and comes back on
     reload as the earlier tracking waiting for its update - never 'no tracking'
  D  two tasks with the same key never run at the same time (the second waits)
  E  the movie-cache pin is counted (an export's reader keeps the copy after the
     window closed)
  F  closing while a job that reads the movie has not stopped: the reader is closed
     only once the job has really stopped
"""
from __future__ import annotations

import os
import shutil
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
OUT = REPO / "_out" / "v40_safety"
shutil.rmtree(OUT, ignore_errors=True)
OUT.mkdir(parents=True)
os.environ["PETERPIPER_HOME"] = str(OUT / "home")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")
sys.path.insert(0, str(REPO / "app"))
sys.path.insert(0, str(HERE))

from PySide6.QtCore import QThread                                     # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox                # noqa: E402

APP = QApplication.instance() or QApplication([])

import synthmovie as SM                                                # noqa: E402
from peterpiper import tasks as TK                                     # noqa: E402
from peterpiper import transfers                                       # noqa: E402
from peterpiper.config import Settings                                 # noqa: E402
from peterpiper.gui import theme as TH                                 # noqa: E402

RESULTS = []
QMessageBox.exec = lambda self: 0
for _n in ("information", "warning", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: QMessageBox.Ok))
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)
TH.apply(APP, "midnight", 11.0)


def ok(name, cond, extra=""):
    RESULTS.append((name, bool(cond)))
    print(f"{'PASS' if cond else 'FAIL'} {name}" + (f"  [{extra}]" if extra != "" else ""),
          flush=True)


def pump(sec=0.2):
    t = time.time()
    while time.time() - t < sec:
        APP.processEvents()
        time.sleep(0.005)


def wait(w, limit=120):
    t = time.time()
    pump(0.2)
    while (w._busy_now() or w.bg_busy() or w.retracking() or w._retrack_timer.isActive()) \
            and time.time() - t < limit:
        pump(0.05)
    pump(0.3)


def window(name):
    from peterpiper.gui.clickwin import ClickWindow
    ClickWindow._ask_previous_run = lambda self, runs, **k: None
    d = OUT / "data"
    d.mkdir(parents=True, exist_ok=True)
    src, exp = SM.load(d / f"OUTPUT_{name}" / "results")
    exp.nd2_path = str(d / f"{name}.nd2")
    Path(exp.out_dir).mkdir(parents=True, exist_ok=True)
    Path(exp.nd2_path).write_bytes(b"stands in " * 40)
    w = ClickWindow(src, exp, Settings(baseline_timepoint=1))
    w._paths_ok = lambda *a, **k: True
    w.resize(1366, 728)
    w.show()
    t0 = time.time()
    while (not w._offered or not w._bg_cands) and time.time() - t0 < 30:
        pump(0.1)
    return w


def tracked(name):
    w = window(name)
    w._accept_background(0)
    w._auto_select()
    wait(w)
    w._track()
    wait(w)
    return w


def sessions(w):
    from peterpiper import history
    d = Path(history.session_dir(w.exp.out_dir))
    return sorted(d.glob("*.npz")) if d.exists() else []


def part_a():
    backups = []
    real = transfers.backup_profile
    transfers.backup_profile = lambda *a, **k: backups.append(1)
    transfers.install_quit_backup()
    w1 = tracked("movie_one")
    w1._dirty = False
    w1.close()
    pump(0.2)
    APP.aboutToQuit.emit()                         # what app.exec() ending does
    pump(0.2)
    ok("A aboutToQuit after a window (Next movie): the task center stays open, no backup",
       not TK.center().closed() and not backups)
    w2 = tracked("movie_two")
    w2._mark_dirty()
    w2._autosave()
    w2._writer.flush(20)
    pump(0.3)
    ok("A second window: autosave writes its session", len(sessions(w2)) >= 1,
       [p.name for p in sessions(w2)])
    w2._run_export(w2._export_data(), ["nucleus|csv", "*|methods"])
    wait(w2)
    ok("A second window: a background export finishes", w2._exported is not None
       and any(Path(w2._exported).rglob("*.csv")) if w2._exported else False, w2._exported)
    w2._dirty = False
    w2.close()
    pump(0.2)
    c = TK.TaskCenter()
    c.shutdown(0)
    ran = []
    t = c.submit("copy", "after the end", lambda p, cc: ran.append(1) or "done")
    ok("A a task given to a closed center still runs (never silently dropped)",
       ran == [1] and t.state == TK.DONE)
    transfers.backup_profile = real


def part_b():
    from peterpiper import app as A
    from peterpiper.gui import clickwin as CW
    gate = threading.Event()
    t1 = TK.center().submit("export", "slow export", lambda p, c: gate.wait(5) or "ok")
    t2 = TK.center().submit("upload", "slow upload", lambda p, c: gate.wait(5) or "ok")
    seen = []
    threading.Timer(0.5, gate.set).start()
    got = A.finish_background(ask=lambda active: (seen.append(len(active)), "wait")[1],
                              pump=APP.processEvents)
    ok("B the real end with jobs running: asked, 'wait' waits for them",
       got == "wait" and seen == [2] and t1.state == TK.DONE and t2.state == TK.DONE)
    stop = threading.Event()

    def long(p, c):
        while not c():
            time.sleep(0.02)
        return "stopped"
    t3 = TK.center().submit("export", "long export", long)
    pump(0.1)
    got = A.finish_background(ask=lambda active: "cancel", pump=APP.processEvents)
    ok("B ... 'cancel' cancels them", got == "cancel" and t3.state == TK.CANCELLED, t3.state)
    del stop
    # an export cut off: marked while it runs, renamed when it stops on an error
    w = tracked("movie_cut")
    real = CW.run_export
    seen_marker = {}

    def failing(root, exp, s, comps, keys, **kw):
        folder = Path(root) / kw["folder_name"]
        folder.mkdir(parents=True)
        kw["progress"](0.3, "writing")
        seen_marker["mid"] = (folder / CW.EXPORT_MARKER).exists()
        raise OSError("the disk is full")
    CW.run_export = failing
    w._run_export(w._export_data(), ["nucleus|csv"])
    wait(w)
    CW.run_export = real
    root = Path(w._export_folder())
    cut = [p.name for p in root.glob("Export_*")]
    ok("B a cut-off export: marked while it runs, renamed ..._INCOMPLETE when it stopped",
       seen_marker.get("mid") is True and cut and all(n.endswith("_INCOMPLETE") for n in cut),
       cut)
    w._run_export(w._export_data(), ["nucleus|csv"])
    wait(w)
    fin = Path(w._exported) if w._exported else None
    ok("B a finished export has no marker", fin is not None and fin.exists()
       and not (fin / CW.EXPORT_MARKER).exists())
    w._dirty = False
    w.close()
    pump(0.2)


def part_c():
    from peterpiper.roifile import load_roi_state, load_roi_track
    w = tracked("movie_save")
    w._remove(4, "nucleus")                        # an update is now pending
    ok("C after a change the update is pending", w.track is None and w._prev_track is not None)
    path = w._save_rois(silent=True)
    pump(0.2)
    tr = load_roi_track(path)
    st, _c = load_roi_state(path)
    ok("C SAVE while it is pending: the update finishes first, the file has the tracking",
       w.track is not None and tr is not None and not (st or {}).get("track_stale"))
    # a change that needs everything tracked again: the earlier tracking, marked stale
    w.sp_tol.setValue(w.sp_tol.value() + 10)
    pump(0.1)
    ok("C a tracking setting changed: pending, cannot be updated by itself",
       w.track is None and w._prev_track is not None)
    path2 = w._save_rois(silent=True)
    pump(0.2)
    tr2 = load_roi_track(path2)
    st2, _c2 = load_roi_state(path2)
    ok("C ... SAVE keeps the earlier tracking, marked stale (never 'no tracking')",
       tr2 is not None and (st2 or {}).get("track_stale") is True
       and isinstance((st2 or {}).get("track_snap"), dict))
    w._dirty = False
    w.close()
    pump(0.2)
    w2 = window("movie_save")
    w2.load_run_file(str(path2))
    pump(0.5)
    ok("C reloaded: the earlier tracking waits for its update (not 'no tracking')",
       w2._prev_track is not None and w2._was_tracked)
    w2._dirty = False
    w2.close()
    pump(0.2)


def part_d():
    c = TK.TaskCenter(max_heavy=4)
    live, worst = [0], [0]
    lock = threading.Lock()

    def job(p, cc):
        with lock:
            live[0] += 1
            worst[0] = max(worst[0], live[0])
        time.sleep(0.3)
        with lock:
            live[0] -= 1
        return "ok"
    a = c.submit("copy", "copy 1", job, key="copy:same")
    time.sleep(0.05)
    b = c.submit("copy", "copy 2", job, key="copy:same")
    st_b = b.state
    c.wait_all(5)
    ok("D same key: the second waits while the first runs (never both at once)",
       a is not b and st_b == TK.QUEUED and worst[0] == 1 and b.state == TK.DONE,
       f"{st_b}, at once {worst[0]}")


def part_e():
    p = str(OUT / "cached.nd2")
    transfers.pin(p)
    transfers.pin(p)
    transfers.unpin(p)
    k = transfers._key(p)
    ok("E the cache pin is counted: still pinned after one of two releases",
       transfers._pinned.get(k) == 1)
    transfers.unpin(p)
    ok("E ... released after the second", k not in transfers._pinned)
    # an export / TIFF job cancelled before it started: its pin is released too
    from peterpiper.nd2io import ND2Source
    w = window("movie_pin")
    real_src = w.src
    fake = ND2Source.__new__(ND2Source)
    fake.position = 0
    w.src = fake
    w._local_movie = str(OUT / "pinned_movie.nd2")
    kk = transfers._key(w._local_movie)
    reader = w._reader_factory()
    pinned = transfers._pinned.get(kk, 0)
    reader.release()
    ok("E a job cancelled before it opened its reader releases its pin",
       pinned == 1 and kk not in transfers._pinned, pinned)
    w.src = real_src
    w._dirty = False
    w.close()
    pump(0.2)


def part_f():
    w = window("movie_close")

    class Spy:
        def __init__(self, s):
            self.s, self.closed_at = s, None

        def __getattr__(self, n):
            return getattr(self.s, n)

        def close(self):
            self.closed_at = time.time()
            self.s.close()

    class Slow(QThread):
        def run(self):
            time.sleep(1.5)

    class Stuck:
        def __init__(self):
            self.thread = Slow()
            self.thread.start()

        def is_finished(self):
            return not self.thread.isRunning()

        def stop_and_wait(self, *_a):
            return False

        def cancel(self):
            pass
    spy = Spy(w.src)
    w.src = spy
    w._retrack_runner = Stuck()
    t = time.time()
    w._dirty = False
    w.close()
    early = spy.closed_at
    while spy.closed_at is None and time.time() - t < 5:
        pump(0.05)
    ok("F a job that has not stopped: the reader is closed only after it stopped",
       early is None and spy.closed_at is not None and spy.closed_at - t >= 1.2,
       f"closed after {(spy.closed_at or 0) - t:.1f} s")


def main():
    t0 = time.time()
    part_a()
    part_b()
    part_c()
    part_d()
    part_e()
    part_f()
    TK.center().wait_all(20)
    failed = [n for n, c in RESULTS if not c]
    print(f"\n{len(RESULTS) - len(failed)} / {len(RESULTS)} checks passed "
          f"({time.time() - t0:.0f} s)", flush=True)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
