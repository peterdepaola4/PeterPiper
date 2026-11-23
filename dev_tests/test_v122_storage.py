"""
Developer test (not shipped): PeterPiper 1.2.2 - a second copy of the results
('Also keep a copy in', cloud.keep_copy), the Saved files window (gui/outlogdlg.py)
and the start screen's 'Storage & cloud' label.

    MPLBACKEND=Agg QT_QPA_PLATFORM=offscreen python dev_tests/test_v122_storage.py

A) keep_copy on made-up folders: every result file copied to <copy>/OUTPUT_<movie>/<user>;
   a second run copies nothing; an autosave written again replaces OUR earlier copy (no _2);
   a copy someone changed by hand is kept and the new one gets _2; an export saved
   outside the results folder is copied in as <copy>/.../<its name>; the movie is never
   copied; no folder set / the results folder itself / an unwritable folder: refused
   plainly; nothing in the source is changed.
B) the Storage & cloud window: the 'Also keep a copy in' box, choosing a folder, Save,
   Off again, the same folder as the results refused.
C) the analysis window (built synthetic movie): with a second folder set, an autosave,
   SAVE and an export (also one saved in another folder) are copied there in the
   background, the window says so on hover, nothing is copied when it is off.
D) Saved files: SAVE is logged; runs from the run list (autosaves) are listed even when
   the log is empty; the buttons are greyed out with nothing to open and work with a
   save picked (Open file opens the save's first file when no file is picked).
E) the start screen's button reads 'Storage & cloud' (the & shown, not underlined).
"""
from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "app"))
sys.path.insert(0, str(HERE))
from peterpiper.safety import long_path                               # noqa: E402

OUT = REPO / "_out" / "v122_storage"
if OUT.exists():
    shutil.rmtree(long_path(OUT))
OUT.mkdir(parents=True)
os.environ["PETERPIPER_HOME"] = str(OUT / "home")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault("MPLCONFIGDIR", str(OUT / "home" / "mpl"))

from PySide6.QtWidgets import QApplication, QMessageBox              # noqa: E402

app = QApplication(sys.argv)
BOXES = []
for _n in ("information", "warning", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: (BOXES.append(a[1:3]),
                                                           QMessageBox.Ok)[1]))
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)

from peterpiper import cloud as C                                     # noqa: E402
from peterpiper import users                                          # noqa: E402

N = [0]
FAILS = []


def ok(name, cond, extra=""):
    N[0] += bool(cond)
    if not cond:
        FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra else ""), flush=True)


def pump(sec=0.3):
    t = time.time()
    while time.time() - t < sec:
        app.processEvents()
        time.sleep(0.005)


def files_in(folder) -> dict:
    folder = Path(folder)
    if not folder.exists():
        return {}
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*")
            if p.is_file()}


def write(p: Path, data: bytes, t: float = None) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    if t is not None:
        os.utime(p, (t, t))


# ===================================================================== A
def part_a():
    movie_dir = OUT / "a" / "data"
    nd2 = movie_dir / "dish 1.nd2"
    write(nd2, b"movie bytes")
    res = movie_dir / "OUTPUT_dish 1" / "Ana"
    write(res / "PeterPiper_sessions" / "dish 1_session.npz", b"auto 1", 1_700_000_000)
    write(res / "dish 1_ROIs.npz", b"saved", 1_700_000_100)
    write(res / "Export_2026-11-17_10-00-00" / "dish 1_nucleus.xlsx", b"xlsx", 1_700_000_200)
    other_export = OUT / "a" / "elsewhere" / "Export_2026-11-17_11-00-00"
    write(other_export / "dish 1_nucleus.csv", b"csv", 1_700_000_300)
    copy = OUT / "a" / "my drive"
    before = files_in(movie_dir)

    r = C.keep_copy(nd2, res, copy, extra=[other_export])
    dst = copy / "OUTPUT_dish 1" / "Ana"
    got = files_in(dst)
    ok("A every result file copied to <copy>/OUTPUT_<movie>/<user>",
       r.ok and got.get("PeterPiper_sessions/dish 1_session.npz") == b"auto 1"
       and got.get("dish 1_ROIs.npz") == b"saved"
       and got.get("Export_2026-11-17_10-00-00/dish 1_nucleus.xlsx") == b"xlsx", r.summary())
    ok("A an export saved elsewhere copied in under its own name",
       got.get("Export_2026-11-17_11-00-00/dish 1_nucleus.csv") == b"csv", sorted(got))
    ok("A the movie is never copied", not any(k.endswith(".nd2") for k in files_in(copy)))
    ok("A nothing in the source changed", files_in(movie_dir) == before)
    r2 = C.keep_copy(nd2, res, copy, extra=[other_export])
    ok("A a second run copies nothing", r2.ok and not r2.copied and len(r2.skipped) == 4,
       r2.summary())
    write(res / "PeterPiper_sessions" / "dish 1_session.npz", b"auto 2 - longer", 1_700_000_500)
    r3 = C.keep_copy(nd2, res, copy)
    got = files_in(dst)
    ok("A an autosave written again replaces our earlier copy (no _2)",
       got.get("PeterPiper_sessions/dish 1_session.npz") == b"auto 2 - longer"
       and "PeterPiper_sessions/dish 1_session_2.npz" not in got and len(r3.copied) == 1,
       r3.summary())
    write(dst / "dish 1_ROIs.npz", b"changed by hand", 1_700_000_600)
    write(res / "dish 1_ROIs.npz", b"saved again", 1_700_000_700)
    C.keep_copy(nd2, res, copy)
    got = files_in(dst)
    ok("A a copy changed by hand is kept; the new one gets _2",
       got.get("dish 1_ROIs.npz") == b"changed by hand"
       and got.get("dish 1_ROIs_2.npz") == b"saved again", sorted(got))
    ok("A no folder set: refused plainly", "no folder" in C.keep_copy(nd2, res, "").problem)
    same = C.keep_copy(nd2, res, movie_dir)
    ok("A the results folder itself: refused", "itself" in same.problem, same.problem)
    bad = OUT / "a" / "a file.txt"
    write(bad, b"x")
    r4 = C.keep_copy(nd2, res, bad)
    ok("A an unwritable folder: refused with the reason", "cannot write" in r4.problem,
       r4.problem)
    ok("A the copy manifest is ours and hidden from the copy itself",
       (dst / C.COPY_MANIFEST).is_file()
       and not (dst / "Export_2026-11-17_11-00-00" / C.COPY_MANIFEST).exists())


# ===================================================================== B
def part_b():
    from peterpiper.gui import storagedlg as SD
    d = SD.StorageDialog(places=[])
    ok("B the window has 'Also keep a copy in', off at first",
       d.rb_copy_off.isChecked() and hasattr(d, "btn_copy"))
    mine = OUT / "b" / "my drive"
    mine.mkdir(parents=True)
    d._pick = lambda *a, **k: str(mine)
    d._choose_copy()
    d._save()
    ok("B choosing a folder and Save keeps it", C.copy_root() == os.path.abspath(str(mine)),
       C.copy_root())
    d = SD.StorageDialog(places=[])
    ok("B shown again as chosen", d.rb_copy_on.isChecked() and d.lbl_copy.path() == C.copy_root())
    d.rb_copy_off.setChecked(True)
    d._save()
    ok("B Off clears it", C.copy_root() == "")
    d = SD.StorageDialog(places=[])
    d.rb_folder.setChecked(True)
    d.lbl_results.set_path(str(mine))
    d.rb_copy_on.setChecked(True)
    d.lbl_copy.set_path(str(mine))
    n = len(BOXES)
    d._save()
    ok("B the same folder as the results is refused",
       len(BOXES) > n and "different" in str(BOXES[-1]) and C.copy_root() == "")
    C.set_results_root(None)


# ===================================================================== C
def make_window(name):
    import synthmovie as SM
    from peterpiper.config import Settings
    from peterpiper.gui.clickwin import ClickWindow
    ClickWindow._ask_previous_run = lambda self, runs, **k: None
    src, exp = SM.load(OUT / name)
    Path(exp.out_dir).mkdir(parents=True, exist_ok=True)
    w = ClickWindow(src, exp, Settings(baseline_timepoint=2))
    w.resize(1366, 768)
    w.show()
    t = time.time()
    while not w._offered and time.time() - t < 30:
        pump(0.1)
    pump(0.3)
    return w


def wait(w, limit=120):
    t = time.time()
    while (w._busy_now() or w.bg_busy() or w.retracking()) and time.time() - t < limit:
        pump(0.05)
    pump(0.3)


def copies_done(w, limit=30):
    t = time.time()
    while time.time() - t < limit:
        st = getattr(w, "_copy_state", None)
        if st is None or st["thread"] is None:
            break
        pump(0.05)
    pump(0.2)


def part_c():
    import synthmovie as SM
    if not SM.FILE.exists():
        SM.save()
    users.add_user("Ana")
    users.activate("Ana")
    copy = OUT / "c" / "my drive"
    copy.mkdir(parents=True)
    C.set_copy_root(copy)
    w = make_window("c_movie")
    w._auto_select()
    wait(w)
    ok("C cells found on the built movie", any(w.cells))
    w._dirty = True
    w._autosave(even_if_busy=True)
    t = time.time()
    while "Autosaved" not in w.lbl_saved.text() and time.time() - t < 20:
        pump(0.1)
    copies_done(w)
    dst = C.copy_target(w.exp.nd2_path, w.exp.out_dir, copy)
    got = files_in(dst)
    ok("C an autosave is copied to the second folder",
       any("session" in k for k in got), sorted(got))
    ok("C the window says so on hover", "Copy kept in" in w.lbl_saved.toolTip()
       and "Copy kept in" in getattr(w, "_last_copy", ""), getattr(w, "_last_copy", ""))
    w._place_background(225.0, 96.0)
    pump(0.2)
    w.cmb_comp.setCurrentIndex(w.cmb_comp.findData("nucleus"))
    w._track()
    wait(w)
    ok("C tracked", w.track is not None)
    w.ed_note.setText("first look")
    w._save_clicked()
    copies_done(w)
    got = files_in(dst)
    ok("C SAVE is copied too", any(k.endswith(".npz") and "ROIs" in k for k in got), sorted(got))
    other = OUT / "c" / "exports elsewhere"
    other.mkdir(parents=True)
    w._export_root = str(other)
    w._auto_shorten = True
    w._run_export(w._export_data(), ["*|methods", "*|roifile"])
    wait(w)
    copies_done(w)
    got = files_in(dst)
    ok("C an export saved in another folder is copied in as well",
       any(k.startswith("Export_") and k.endswith(".txt") for k in got), sorted(got))
    ok("C the movie is never copied", not any(k.endswith(".nd2") for k in files_in(copy)))
    from peterpiper import outlog
    ok("D SAVE is in the saved-files log",
       any(e.get("kind") == "saved" for e in outlog.entries()))
    C.set_copy_root(None)
    before = files_in(copy)
    w._dirty = True
    w.cells[0] = dict(w.cells[0])
    w._autosave(even_if_busy=True)
    pump(1.5)
    copies_done(w)
    ok("C nothing copied when it is off", files_in(copy) == before)
    w.close()
    pump(0.3)


# ===================================================================== D
def part_d():
    from peterpiper import outlog
    from peterpiper.gui import outlogdlg as OD
    try:
        outlog.log_path().unlink()
    except OSError:
        pass
    opened = []
    OD._open = lambda p: opened.append(p)
    from peterpiper import history as H           # the built movie is not a real file, so
    saved = next((OUT / "c_movie").rglob("*.npz"))  # it is not in the run list: put the
    real = H._load_index                            # run SAVE wrote there, as an autosave
    H._load_index = lambda *a, **k: {"k": {"nd2_name": "synthetic_movie.nd2", "runs": [
        {"path": str(saved), "saved": "2026-11-17T10:00:00", "kind": "session",
         "n_cells": 3}]}}
    d = OD.OutputsDialog()
    ok("D with an empty log, the analyses from the run list are listed",
       d.table.rowCount() >= 1 and any(r.get("kind") in ("session", "saved", "export")
                                       for r in d._rows), d.table.rowCount())
    ok("D a save is picked and the buttons work", d.btn_folder.isEnabled()
       and d.btn_file.isEnabled())
    d.files.setCurrentRow(-1)
    d._open_file()
    ok("D Open file with no file picked opens the save's first file",
       opened and Path(opened[-1]).exists(), opened[-1:])
    d._open_folder()
    ok("D Open folder opens the save's folder", Path(opened[-1]).is_dir(), opened[-1:])
    d.ed.setText("no such thing at all")
    ok("D nothing matching: the buttons are greyed out",
       not d.btn_folder.isEnabled() and not d.btn_file.isEnabled())
    d.close()
    H._load_index = real


# ===================================================================== E
def part_e():
    from peterpiper.gui import setup as SU
    d = SU.SetupDialog()
    b = getattr(d, "btn_storage", None)
    ok("E the start screen's button reads 'Storage & cloud'",
       b is not None and b.text() == "Storage && cloud", b.text() if b else None)
    d.close()


def main():
    for part in (part_a, part_b, part_c, part_d, part_e):
        try:
            part()
        except Exception as exc:                                   # noqa: BLE001
            import traceback
            traceback.print_exc()
            ok(f"{part.__name__} ran without an error", False, repr(exc))
    print(f"\n{N[0]} / {N[0] + len(FAILS)} checks passed")
    for f in FAILS:
        print("  FAILED:", f)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
