"""
Developer test (not shipped): V2.3 session memory in the main window
(gui/clickwin.py, gui/historydlg.py, gui/setup.py), driven directly on REAL
.nd2 data, offscreen.

    MPLBACKEND=Agg QT_QPA_PLATFORM=offscreen \\
        python dev_tests/test_gui_history.py [--parts 123456] [--out <folder>]

(PETERPIPER_HOME is set to <out>/home by the test, so the run index starts empty.)

  1  nucleus file (T=48): fresh analysis, AUTO-DETECT, TRACK -> a session file
     with the tracking appears in out_dir/PD4nav_sessions and is in the run
     index; debounced autosave; timings of pack (window thread) and write
     (background thread); the state has every Contract-2 key
  2  a new window on the same .nd2: the 'analysed before' hook is called with
     that session (tracked, date, cells); choosing it restores the tracking
     (export on, the outlines at t = 0, T/2, T-1 equal the tracked ones and move),
     baseline and graph look; no new session file is made by just loading
  3  again, choosing a fresh analysis: no cells; editing makes a NEW session
     file and the earlier one is byte-identical
  4  the V2.1 ROI file (no tracking) copied into a fake results folder of its
     4 GB .nd2 (T=121): listed as 'not saved', the plain 'made before tracking
     was saved' message, 'Track now?' -> Yes tracks, then a session WITH tracking
  5  the user's real V2.2 tracked mito file (copied): listed as tracked, loads
     with its tracking, no question asked
  6  ask_previous_runs=False: no prompt; File > Earlier analyses... still works;
     the menu switches save the settings; Load saved ROIs... and Save ROIs now
     still work; the start dialog's 'Analysed before' line

Test data are read-only (D:\\); everything is written under --out.
Exit code 0 = every check passed.
"""
from __future__ import annotations

import labdata  # noqa: E402  (lab file names: dev_tests/lab_paths.json, never uploaded)

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
import traceback
from pathlib import Path

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                                  # noqa: BLE001
    pass
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "app"))

NUC = labdata.T("t02")
V21_ND2 = labdata.T("t04")
V21_NPZ = (labdata.T("t05"))
V22_ND2 = (labdata.T("t06"))
V22_NPZ = (labdata.T("t07"))

from labdata import need                                    # noqa: E402
need(NUC, V21_ND2, V21_NPZ, V22_ND2, V22_NPZ, what="test_gui_history.py")   # V3.0: lab data only

ap = argparse.ArgumentParser()

ap.add_argument("--parts", default="123456")
ap.add_argument("--out", default=str(REPO / "_out" / "gui_history"))
args = ap.parse_args()
OUT = Path(args.out).resolve()
if os.name == "nt" and not str(OUT).startswith("\\\\?\\"):
    OUT = Path("\\\\?\\" + str(OUT))           # deep scratch folder: long paths
if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True, exist_ok=True)
os.environ["PETERPIPER_HOME"] = str(OUT / "home")   # a fresh run index for this test
os.environ.setdefault("MPLCONFIGDIR", str(OUT / "home" / "mpl"))

errors, dialogs, questions = [], [], []
sys.excepthook = lambda k, v, tb: errors.append("".join(traceback.format_exception(k, v, tb)))
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox  # noqa: E402

app = QApplication(sys.argv)
app.setStyle("Fusion")
for _n in ("information", "warning", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: dialogs.append(a[1:3]) or QMessageBox.Ok))
ANSWER = {"q": QMessageBox.No}


def _question(*a, **k):
    questions.append(tuple(a[1:3]))
    return ANSWER["q"]


QMessageBox.question = staticmethod(_question)
QMessageBox.exec = lambda self: dialogs.append((self.windowTitle(), self.text())) or 0

from peterpiper import history as H                                    # noqa: E402
from peterpiper.config import Settings, load_settings                  # noqa: E402
from peterpiper.gui import clickwin as CW                              # noqa: E402
from peterpiper.gui.clickwin import ClickWindow                        # noqa: E402

# V3.0: the main window no longer places the background region by itself (you
# pick a spot); this test was written for the automatic one - placed as before
def _v29_auto_bg(cls):
    orig = cls.__init__

    def init(self, *a, **k):
        orig(self, *a, **k)
        from PySide6.QtCore import QTimer as _QT
        _QT.singleShot(150, self._auto_background)
    cls.__init__ = init


_v29_auto_bg(ClickWindow)
from peterpiper.gui.historydlg import PreviousRunsDialog               # noqa: E402
from peterpiper.nd2io import describe, open_source                     # noqa: E402
from peterpiper.roifile import (load_roi_state, read_summary, save_session_file,  # noqa: E402
                            load_roi_file, load_roi_track)

# the 'analysed before' hook: record each call, answer what the part wants
ASK = {"answer": None, "calls": []}


def _fake_ask(self, runs, menu=False):
    ASK["calls"].append(dict(runs=list(runs), menu=menu))
    a = ASK["answer"]
    return a(runs) if callable(a) else a


ClickWindow._ask_previous_run = _fake_ask
checks = []
TIMES = {}


def ok(name, cond, extra=""):
    checks.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra else ""), flush=True)


def pump(sec=0.3):
    t = time.time()
    while time.time() - t < sec:
        app.processEvents()
        time.sleep(0.005)


def wait(w):
    pump(0.3)
    while w._busy_now():
        app.processEvents()
        time.sleep(0.02)
    pump(0.3)


def flushed(w):
    w._writer.flush()
    pump(0.2)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def sessions(out_dir):
    d = H.session_dir(out_dir)
    return sorted(d.glob("*_session_*.npz")) if d.exists() else []


def same_key(p):
    return os.path.normcase(os.path.abspath(str(p))).replace("\\\\?\\", "")


def index_paths(nd2):
    p = Path(os.environ["PETERPIPER_HOME"]) / "run_history.json"
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    ent = data.get(H.nd2_fingerprint(nd2).get("quick", ""), {})
    return [same_key(r["path"]) for r in ent.get("runs", [])]


def open_window(nd2, out_dir, settings=None, answer=None):
    ASK["answer"] = answer
    ASK["calls"].clear()
    src = open_source(nd2)
    exp = describe(src, out_dir=str(out_dir))
    exp.export_tiffs = False
    Path(exp.out_dir).mkdir(parents=True, exist_ok=True)
    w = ClickWindow(src, exp, settings or Settings())
    w.resize(1700, 1000)
    w.show()
    t = time.time()
    while not w._offered and time.time() - t < 30:
        pump(0.1)
    pump(0.5)
    wait(w)
    return w


def snap_rois(w, comp, ts):
    return {t: [(tuple(r.bbox), r.mask.copy()) for r in w._rois(comp, t)] for t in ts}


def same_snap(a, b):
    return all(len(a[t]) == len(b[t]) and all(x[0] == y[0] and np.array_equal(x[1], y[1])
                                              for x, y in zip(a[t], b[t])) for t in a)


OUT_A = OUT / "a" / f"OUTPUT_{Path(NUC).stem}"
STATE = {}


# =============================================================================
def part_1():
    print("\n--- 1: fresh analysis -> session file with tracking + index entry")
    w = open_window(NUC, OUT_A, Settings(baseline_timepoint=1))
    T = w.exp.n_timepoints
    ok("start: no session file yet", not sessions(OUT_A))
    ok("session_id set, fingerprint cached and used", bool(w.session_id) and
       w._fp().get("quick") == H.nd2_fingerprint(NUC)["quick"], w.session_id)
    w._auto_select()
    wait(w)
    live = w._live("nucleus")
    ok("AUTO-DETECT", len(live) >= 40, f"{len(live)} nuclei")
    n_log = len(w._save_log)
    for _ in range(5):                       # 5 quick changes -> one save
        w._mark_dirty()
        pump(0.1)
    pump(AUTOSAVE_S + 0.8)
    flushed(w)
    ok("debounced autosave: several quick changes, one save, ~2 s after the last",
       len(w._save_log) == n_log + 1 and len(sessions(OUT_A)) == 1,
       f"{len(w._save_log) - n_log} save(s)")
    s0 = read_summary(sessions(OUT_A)[0]) if sessions(OUT_A) else {}
    ok("... ROIs only so far (not tracked)", s0 and not s0["tracked"] and s0["n_cells"] == len(live))
    t = time.time()
    w._track()
    wait(w)
    flushed(w)
    ok("tracked", w.track is not None, f"{len(live)} x {T} in {time.time() - t:.0f} s")
    ss = sessions(OUT_A)
    ok("one session file in out_dir/PeterPiper_sessions", len(ss) == 1 and
       ss[0].parent.name == "PeterPiper_sessions", str([p.name for p in ss]))
    p1 = ss[0] if ss else None
    s1 = read_summary(p1) if p1 else {}
    ok("session file holds the tracking", s1 and s1["tracked"] and s1["n_timepoints"] == T
       and s1["kind"] == "session" and s1["n_cells"] == len(w.cells),
       f"tracked={s1.get('tracked')}, T={s1.get('n_timepoints')}, {s1.get('n_cells')} cells")
    ok("autosaved right after tracking (milestone, not after a delay)",
       w._save_log and w._save_log[-1].get("tracked"), str(w._save_log[-1:]))
    ok("recorded in the run index", same_key(p1) in index_paths(NUC), str(index_paths(NUC)))
    st, _c = load_roi_state(p1)
    keys = ["version", "saved", "session_id", "nd2_path", "fingerprint", "exp", "rules",
            "baseline", "drift", "track_params", "graph_style", "kind",
            "v2", "nd2", "t0", "bg_auto", "cells", "excl", "channels", "prefix", "follow", "comps"]
    ok("state has every Contract-2 key (+ the V2.2 ones)", all(k in st for k in keys),
       str([k for k in keys if k not in st]))
    ok("state: exp + fingerprint + params", st["exp"]["n_timepoints"] == T
       and st["fingerprint"]["quick"] == H.nd2_fingerprint(NUC)["quick"]
       and (st["track_params"] or {}).get("tracker"), str(st["exp"]))
    # ---- timings: pack (window thread) and write (background thread)
    lg = w._save_log[-1]
    TIMES["autosave pack (GUI thread) ms"] = round(lg.get("pack_ms", -1), 1)
    TIMES["autosave write (background) ms"] = round(lg.get("write_ms", -1), 1)
    TIMES["session file MB"] = round(p1.stat().st_size / 1e6, 2)
    stt, anchors, comps, bg, shape, t0 = w._roi_state("session")
    tt = time.perf_counter()
    save_session_file(OUT / "timing_session.npz", anchors, bg, shape, t0 + 1, stt, comps, w.track)
    TIMES["whole save in one thread ms"] = round((time.perf_counter() - tt) * 1000, 1)
    print("     timings:", TIMES)
    ok("window thread only packs (fast): < 150 ms", lg.get("pack_ms", 1e9) < 150,
       f"pack {lg.get('pack_ms', -1):.0f} ms, write {lg.get('write_ms', -1):.0f} ms")
    # ---- the GUI stays responsive while the background thread writes
    w._mark_dirty()
    t = time.perf_counter()
    w._autosave()
    gui_ms = (time.perf_counter() - t) * 1000
    busy = w._writer.busy()
    flushed(w)
    ok("autosave call returns at once (write continues in the background)", gui_ms < 150,
       f"{gui_ms:.0f} ms in the window thread; writer busy afterwards: {busy}")
    # ---- what part 2 should get back
    STATE["T"] = T
    STATE["ts"] = sorted({0, T // 2, T - 1})
    STATE["rois"] = snap_rois(w, "nucleus", STATE["ts"])
    STATE["n"] = len(w.cells)
    w.q_base.setValue(5)                    # changes after tracking: saved on close
    w.settings.graph_style = {"error": "SD", "show_cells": True}
    w._mark_dirty()
    w.close()
    pump(0.3)
    ss = sessions(OUT_A)
    st, _c = load_roi_state(ss[0]) if ss else ({}, {})
    ok("closing saves the last changes into the same session file",
       len(ss) == 1 and st.get("baseline") == 5 and st.get("graph_style", {}).get("error") == "SD",
       f"baseline {st.get('baseline')}, graph {st.get('graph_style')}")
    STATE["p1"] = ss[0] if ss else None
    STATE["sha1"] = sha(ss[0]) if ss else ""
    STATE["n_live"] = len(live)


def part_2():
    print("\n--- 2: reopen -> offered -> load with tracking (no new file)")
    p1 = STATE.get("p1")
    if p1 is None:
        ok("(part 1 made a session)", False)
        return
    before = [p.name for p in sessions(OUT_A)]
    t = time.time()
    w = open_window(NUC, OUT_A, Settings(baseline_timepoint=1), answer=str(p1))
    ok("_ask_previous_run called once at start", len(ASK["calls"]) == 1 and
       not ASK["calls"][0]["menu"], f"{len(ASK['calls'])} call(s), opened in {time.time() - t:.1f} s")
    runs = ASK["calls"][0]["runs"] if ASK["calls"] else []
    me = [r for r in runs if same_key(r.path) == same_key(p1)]
    r = me[0] if me else None
    ok("the runs list that session: tracked, date, cells, kind",
       r is not None and r.tracked and r.saved and r.n_cells == STATE["n"] and r.kind == "session"
       and r.n_timepoints == STATE["T"], r.label() if r else f"{len(runs)} runs")
    ok("... and it is the newest (listed first)", bool(runs) and same_key(runs[0].path) == same_key(p1))
    ok("tracking restored, export enabled", w.track is not None and w.btn_export.isEnabled())
    got = snap_rois(w, "nucleus", STATE["ts"])
    ok("w._rois('nucleus', t) == the tracked ROIs at t = " + str([t + 1 for t in STATE["ts"]]),
       same_snap(got, STATE["rois"]))
    t0, tl = STATE["ts"][0], STATE["ts"][-1]
    moved = sum(1 for a, b in zip(got[t0], got[tl]) if a[0] != b[0] or not np.array_equal(a[1], b[1]))
    ok("the outlines differ between the first and last timepoint (they move)", moved > 0,
       f"{moved} of {len(got[t0])} ROIs differ")
    ok("baseline and graph look restored", w.q_base.value() == 5
       and w.settings.baseline_timepoint == 5 and w.settings.graph_style.get("error") == "SD",
       f"baseline {w.q_base.value()}, {w.settings.graph_style}")
    ok("no 'Track now?' question for a tracked run", not questions, str(questions))
    n_err = len(errors)
    for v in (STATE["T"], 1, STATE["T"] // 2):
        w.slider.setValue(v)
        pump(0.4)
    ok("scrubbing (slider to T, 1, T/2) refreshes without error", len(errors) == n_err
       and w.cur_t == STATE["T"] // 2 - 1)
    ok("nothing to save after only looking", not w._dirty)
    w.close()
    pump(0.3)
    ok("no new session file made by just loading", [p.name for p in sessions(OUT_A)] == before,
       str([p.name for p in sessions(OUT_A)]))
    ok("the loaded session file is unchanged", sha(p1) == STATE["sha1"])


def part_3():
    print("\n--- 3: reopen -> fresh analysis; editing makes a NEW session file")
    p1 = STATE.get("p1")
    w = open_window(NUC, OUT_A, Settings(), answer=None)
    ok("asked, answered 'fresh'", len(ASK["calls"]) == 1)
    ok("fresh: no cells, not tracked", not any(w.cells) and w.track is None)
    ok("fresh: no file written yet", len(sessions(OUT_A)) == 1)
    w._auto_select()
    wait(w)
    pump(AUTOSAVE_S + 0.8)
    flushed(w)
    ss = sessions(OUT_A)
    new = [p for p in ss if p1 is None or same_key(p) != same_key(p1)]
    ok("editing made a NEW session file", len(ss) == 2 and len(new) == 1,
       str([p.name for p in ss]))
    ok("the earlier session file is byte-identical", p1 is not None and sha(p1) == STATE["sha1"])
    w.close()
    pump(0.3)


def part_4():
    print("\n--- 4: V2.1 file without tracking -> plain message, 'Track now?' -> Yes")
    if not (Path(V21_ND2).exists() and Path(V21_NPZ).exists()):
        ok("(V2.1 test data present)", False)
        return
    out = OUT / "e" / f"OUTPUT_{Path(V21_ND2).stem}"
    out.mkdir(parents=True, exist_ok=True)
    dst = out / Path(V21_NPZ).name
    shutil.copy2(V21_NPZ, dst)
    questions.clear()
    ANSWER["q"] = QMessageBox.Yes
    t = time.time()
    w = open_window(V21_ND2, out, Settings(), answer=lambda runs: str(dst))
    wait(w)                                          # the tracking it started
    ANSWER["q"] = QMessageBox.No
    runs = ASK["calls"][0]["runs"] if ASK["calls"] else []
    me = [r for r in runs if same_key(r.path) == same_key(dst)]
    ok("the V2.1 copy is listed, tracking not saved", bool(me) and not me[0].tracked,
       me[0].label() if me else f"{len(runs)} runs: {[r.path for r in runs]}")
    q = [x for x in questions if x and "tracking" in str(x[0]).lower()]
    txt = str(q[0][1]) if q else ""
    ok("plain message: made before tracking was saved", "before tracking was saved" in txt,
       txt[:160].replace("\n", " "))
    ok("... and asks 'Track now?' with the time it takes", "Track now?" in txt and " s." in txt)
    ok("Yes -> tracked", w.track is not None, f"{len(w._live('nucleus'))} cells x "
       f"{w.exp.n_timepoints} in {time.time() - t:.0f} s (whole part)")
    flushed(w)
    ss = sessions(out)
    s = read_summary(ss[0]) if ss else {}
    ok("then a session file WITH tracking exists", len(ss) == 1 and s.get("tracked")
       and s.get("n_timepoints") == w.exp.n_timepoints, f"{[p.name for p in ss]}")
    st, _c = load_roi_state(ss[0]) if ss else ({}, {})
    ok("... which records the file it came from", same_key(st.get("based_on", "")) == same_key(dst))
    ok("the V2.1 copy itself is unchanged", sha(dst) == sha(V21_NPZ))
    w.close()
    pump(0.3)


def part_5():
    print("\n--- 5: the user's V2.2 tracked file -> listed as tracked, loads with tracking")
    if not (Path(V22_ND2).exists() and Path(V22_NPZ).exists()):
        ok("(V2.2 test data present)", False)
        return
    out = OUT / "f" / "OUTPUT"
    out.mkdir(parents=True, exist_ok=True)
    dst = out / Path(V22_NPZ).name
    shutil.copy2(V22_NPZ, dst)
    questions.clear()
    w = open_window(V22_ND2, out, Settings(), answer=lambda runs: str(dst))
    runs = ASK["calls"][0]["runs"] if ASK["calls"] else []
    me = [r for r in runs if same_key(r.path) == same_key(dst)]
    ok("listed as tracked (V2.2, 10 cells, 61 timepoints)", bool(me) and me[0].tracked
       and me[0].n_cells == 10 and me[0].n_timepoints == 61, me[0].label() if me else "-")
    ok("loads WITH its tracking (export on, no question)", w.track is not None
       and w.btn_export.isEnabled() and not questions, str(questions))
    a, b = w._rois("mito", 0), w._rois("mito", 60)
    ok("outlines move between timepoint 1 and 61",
       any(x.bbox != y.bbox for x, y in zip(a, b)))
    stt, anchors, comps, bg, shape, t0 = w._roi_state("session")
    tt = time.perf_counter()
    save_session_file(OUT / "timing_mito_session.npz", anchors, bg, shape, t0 + 1, stt, comps,
                      w.track)
    TIMES["mito 10 cells x 61: whole save in one thread ms"] = round(
        (time.perf_counter() - tt) * 1000, 1)
    tt = time.perf_counter()
    from peterpiper.roifile import session_blob
    session_blob(anchors, bg, shape, t0 + 1, stt, comps, w.track)
    TIMES["mito 10 cells x 61: pack only ms"] = round((time.perf_counter() - tt) * 1000, 1)
    # the dialog itself, on these real runs
    dlg = PreviousRunsDialog(runs, Path(V22_ND2).name, w)
    cur = dlg.current_run()
    ok("dialog: lists every run, the NEWEST run preselected, details in plain words (L5)",
       dlg.tree.topLevelItemCount() == len(dlg.runs) and cur is runs[0]
       and "Tracking: " in dlg.lbl_details.text(),
       f"{len(runs)} runs, {len(dlg.runs)} rows after V2.5 de-duplication")
    # V2.4 (L5): a newer untracked run is pointed out in an older tracked run's details
    from peterpiper.history import RunInfo
    mk = lambda saved, trk: RunInfo(path=f"C:/x/{saved[:10]}_ROIs.npz", saved=saved,
                                    version="2.4.0", kind="saved", n_cells=3,
                                    comps=["nucleus"], tracked=trk, n_timepoints=5, rules=[],
                                    nd2_name="a.nd2", match="same file")
    fake = [mk("2026-10-31T10:00:00", False), mk("2026-10-30T10:00:00", True)]
    d2 = PreviousRunsDialog(fake, "a.nd2", w)
    t_new = d2.lbl_details.text()
    d2.tree.setCurrentItem(d2.tree.topLevelItem(1))
    t_old = d2.lbl_details.text()
    ok("dialog: newest (untracked) preselected; says an older run has tracking; the older "
       "tracked run says a newer untracked run exists (L5)",
       d2.current_run() is fake[1] and "older run" in t_new and "newer run" in t_old)
    d2.reject()
    dlg.chk_dont_ask.setChecked(True)
    ok("dialog: 'don't ask again' box", dlg.dont_ask())
    dlg.reject()
    w.close()
    pump(0.3)
    ok("nothing written by loading it", not sessions(out))


def part_6():
    print("\n--- 6: ask_previous_runs=False; menu; Load saved ROIs; Save ROIs now; setup line")
    p1 = STATE.get("p1")
    w = open_window(NUC, OUT_A, Settings(ask_previous_runs=False), answer=None)
    ok("no prompt when ask_previous_runs is off", not ASK["calls"] and not any(w.cells))
    ASK["answer"] = str(p1)
    w._earlier_analyses()
    pump(0.3)
    ok("File > Earlier analyses...: asked (menu mode) and loaded with tracking",
       len(ASK["calls"]) == 1 and ASK["calls"][0]["menu"] and w.track is not None)
    w.act_ask.setChecked(True)
    s, _x = load_settings()
    ok("menu switch 'Offer earlier analyses' saves the setting", s.ask_previous_runs is True)
    w.act_ask.setChecked(False)
    w.act_autosave.setChecked(False)
    s, _x = load_settings()
    ok("... both switches off saved", not s.ask_previous_runs and not s.autosave_sessions)
    w._mark_dirty()
    ok("autosave off: nothing is saved", not w._autosave())
    w.act_autosave.setChecked(True)
    # review: this window's own session file (your work so far) must survive
    # loading another run and editing that
    live = w._live("nucleus")
    w._set_include("nucleus", live[0], False)
    w._autosave()
    flushed(w)
    own = w._session_file
    h_own = sha(own) if own and own.exists() else None
    n_before = len(sessions(OUT_A))
    orig = QFileDialog.getOpenFileName
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (str(p1), ""))
    w._load_rois()
    QFileDialog.getOpenFileName = orig
    pump(0.3)
    ok("Load saved ROIs... loads a session file with tracking", w.track is not None
       and w._based_on and same_key(w._based_on) == same_key(p1))
    w._set_include("nucleus", live[1], False)
    w._autosave()
    flushed(w)
    ok("an edit after loading another run goes to a NEW session file; this window's "
       "earlier session file is left as it was",
       h_own is not None and sha(own) == h_own and w._session_file is not None
       and same_key(w._session_file) != same_key(own) and len(sessions(OUT_A)) == n_before + 1,
       f"{n_before} -> {len(sessions(OUT_A))} session files")
    path = w._save_rois(silent=True)
    st, _c = load_roi_state(path) if path else ({}, {})
    ok("Save ROIs now: full state, kind 'saved', tracking kept, in the index",
       path is not None and st.get("kind") == "saved" and st.get("fingerprint", {}).get("quick")
       and load_roi_track(path) is not None and same_key(path) in index_paths(NUC),
       Path(path).name if path else "-")
    # review: an ROI file whose tracking was made on ANOTHER movie (same image size and
    # length) - its outlines / measurements must not become this movie's numbers
    for tag, change in (("other", dict(nd2="other_movie.nd2", fingerprint=dict(
            name="other_movie.nd2", size=123, mtime=0.0, quick="0" * 40))),
            ("changed", dict(fingerprint=dict(name=Path(NUC).name, size=123, mtime=0.0,
                                              quick="1" * 40)))):
        with np.load(str(p1), allow_pickle=False) as z:
            arrs = {k: z[k] for k in z.files}
        st = json.loads(str(arrs["state_json"]))
        st.update(change, kind="saved")
        arrs["state_json"] = np.asarray(json.dumps(st))
        fake = OUT / f"{tag}_movie_ROIs.npz"
        np.savez(str(fake), **arrs)
        questions.clear()
        w._load_roi_file(str(fake))
        pump(0.3)
        ok(f"ROI file tracked on {tag} movie: ROIs loaded, its tracking NOT used, says why "
           f"and offers to track", w.track is None and len(w._live("nucleus")) == len(live)
           and questions and "not used here" in questions[-1][1],
           (questions[-1][1][:120] if questions else "no question"))
    w.close()
    pump(0.3)
    # the start dialog's line
    from peterpiper.gui.setup import SetupDialog
    d = SetupDialog()
    t = time.time()
    d._load(NUC)
    dt = time.time() - t
    d.experiment.out_dir = str(OUT_A)
    t = time.time()
    d._show_history()
    dt2 = time.time() - t
    txt = d.lbl_before.text()
    ok("start dialog: 'Analysed before: N earlier runs (newest ..., tracking saved)'",
       "earlier run" in txt and "tracking saved" in txt, f"{txt}  (look-up {dt2 * 1000:.0f} ms; "
                                                         f"file opened in {dt:.1f} s)")
    TIMES["start dialog look-up ms"] = round(dt2 * 1000)
    d.reject()


AUTOSAVE_S = CW.AUTOSAVE_MS / 1000.0
t_all = time.time()
for key, fn in (("1", part_1), ("2", part_2), ("3", part_3), ("4", part_4), ("5", part_5),
                ("6", part_6)):
    if key in args.parts:
        try:
            fn()
        except Exception:                                          # noqa: BLE001
            errors.append(traceback.format_exc())
            ok(f"part {key} ran to the end", False)
print()
print("timings:", TIMES)
n_pass = sum(c for _n, c in checks)
print(f"{n_pass} of {len(checks)} checks passed; errors: {len(errors)}; "
      f"{time.time() - t_all:.0f} s")
for e in errors[:5]:
    print(str(e)[-2500:])
crit = [d for d in dialogs if d and "wrong" in str(d[0]).lower()]
for d in crit[:3]:
    print("ERROR DIALOG:", str(d)[:1500])
sys.exit(0 if n_pass == len(checks) and not errors and not crit else 1)
