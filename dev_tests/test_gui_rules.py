"""
Developer test (not shipped): the V2.3 tracking rules in the main window
(gui/clickwin.py), driven directly on REAL .nd2 data, offscreen.

    PETERPIPER_HOME=<ws>/_home MPLBACKEND=Agg QT_QPA_PLATFORM=offscreen \\
        python dev_tests/test_gui_rules.py [--parts abcd] [--out <folder>]

  a  nucleus file (Cy5/GFP/ExRai, T=48): rule 'Track nucleus using Cy5 ONLY',
     AUTO-DETECT, TRACK; the same cells tracked by manual.track_cells(...,
     rules=None) (the V2.2 code path) give IDENTICAL Measurements and ROIs; every
     channel and every ratio pair reaches the export data; a real export with
     the standard list writes a Methods sheet, <stem>_methods.txt (quoting the
     rule) and the Prism note; changing the rule afterwards clears the tracking
     and says so
  b  start-up from Settings.track_rules (nucleus Cy5 IF GFP): AUTO-DETECT skips
     the nuclei without GFP signal and says how many
  c  HeLa mRuby file (GFP/ExRai/mCherry, T=61): 'Track whole cell using mCherry
     WITH intensity in GFP' - the Show list gets 'Tracking image: mCherry + GFP'
     and shows the guide plane; 3 cells clicked at bright spots are drawn on the
     guide plane; tracked (61 frames); trace opens on R/R0 mCherry/GFP; AND shows
     the kept pixels; IF: a cell drawn by hand on an empty area is flagged at
     once and excluded after tracking with the IF-gate reason (re-include works);
     rule changes after tracking clear it with the message
  d  the user's V2.2 mito ROI file WITH tracking (copied first): loaded with
     default (ONLY) rules from its follow rows + drawn channels, tracking kept

Test data are read-only (D:\\); everything is written under --out.
Exit code 0 = every check passed.
"""
from __future__ import annotations

import labdata  # noqa: E402  (lab file names: dev_tests/lab_paths.json, never uploaded)

import argparse
import os
import shutil
import sys
import time
import traceback
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "app"))

NUC = labdata.T("t02")
RUBY = labdata.T("t08")
V22_ND2 = (labdata.T("t06"))
V22_NPZ = (labdata.T("t07"))
from labdata import need                                    # noqa: E402
need(NUC, RUBY, V22_ND2, V22_NPZ, what="test_gui_rules.py")   # V3.0: lab data only

ap = argparse.ArgumentParser()
ap.add_argument("--parts", default="abcd")
ap.add_argument("--out", default=str(REPO / "_out" / "gui_rules"))
args = ap.parse_args()
OUT = Path(args.out).resolve()
if os.name == "nt" and not str(OUT).startswith("\\\\?\\"):
    # the scratch folder is deep: Windows' extended-length form lets the export's
    # long file names (Prism graphs/...) exceed 260 characters
    OUT = Path("\\\\?\\" + str(OUT))
OUT.mkdir(parents=True, exist_ok=True)

errors, dialogs = [], []
sys.excepthook = lambda k, v, tb: errors.append("".join(traceback.format_exception(k, v, tb)))
from PySide6.QtWidgets import QApplication, QMessageBox             # noqa: E402

app = QApplication(sys.argv)
app.setStyle("Fusion")
for _n in ("information", "warning", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: dialogs.append(a[1:3]) or QMessageBox.Ok))
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)
QMessageBox.exec = lambda self: dialogs.append((self.windowTitle(), self.text())) or 0

from peterpiper import manual as MN                                     # noqa: E402
from peterpiper import rules as RL                                      # noqa: E402
from peterpiper.config import Settings                                  # noqa: E402
from peterpiper.export import catalog, standard                         # noqa: E402
from peterpiper.gui.clickwin import ClickWindow                         # noqa: E402

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
# v2.3 pass B: the 'analysed before' list would wait for a click - answer 'fresh'
ClickWindow._ask_previous_run = lambda self, runs, **k: None
from peterpiper.nd2io import describe, open_source                      # noqa: E402

checks = []


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


def set_rule(w, i, comp=None, a=None, mode=None, b=None):
    row = w._rows[i]
    names = list(w.exp.channels)
    if comp is not None:
        row["cmb"].setCurrentIndex(row["cmb"].findData(comp))
    if a is not None:
        row["a"].setCurrentIndex(names.index(a))
    # V3.0: the rows have a main channel + helper channels; the older ONLY / WITH /
    # AND / IF rules (what this test checks, exactly as before) are set as the rule a
    # loaded pre-V3.0 run brings (row["legacy"]), which is applied exactly as saved
    lg = row.get("legacy")
    cur_b = lg["b"] if lg else -1
    m = mode if mode is not None else (lg["mode"] if lg else "only")
    bi = names.index(b) if b is not None else cur_b
    for h in list(row["helpers"]):
        h["widget"].setParent(None)
        row["helpers"].remove(h)
    if m == "only" or bi < 0:
        row["legacy"] = None
    else:
        row["legacy"] = {"mode": m, "b": bi}
        row["loading"] = True
        w._add_helper(row, bi, quiet=True)
        row["loading"] = False
    w._rows_changed()
    pump(0.05)


def same_meas(A, B):
    return all(np.array_equal(getattr(A, f), getattr(B, f), equal_nan=True)
               for f in ("mean", "background", "area_px", "n_saturated", "quality",
                         "background_sd")) and list(A.channels) == list(B.channels)


def same_rois(ga, gb):
    for ra, rb in zip(ga, gb):
        for a, b in zip(ra, rb):
            if (a is None) != (b is None):
                return False
            if a is None:
                continue
            if tuple(a.bbox) != tuple(b.bbox) or not np.array_equal(a.mask, b.mask):
                return False
    return True


def view_items(w):
    return [w.cmb_view.itemText(i) for i in range(w.cmb_view.count())]


# =============================================================================
def part_a():
    print("\n--- a: nucleus file, Cy5 ONLY = V2.2 path; all channels; export with provenance")
    src = open_source(NUC)
    exp = describe(src, out_dir=str(OUT / "a" / f"OUTPUT_{Path(NUC).stem}"))
    exp.export_tiffs = False
    names = list(exp.channels)
    w = ClickWindow(src, exp, Settings(baseline_timepoint=1, ui_fold_steps=False))
    w.resize(1700, 1000)
    w.show()
    pump(1.0)
    w._fold_toggled(False)       # V2.9: steps fold; these checks look inside every step
    ok("start-up: one rule, nucleus", list(w.rules) == ["nucleus"] and len(w._rows) == 1)
    set_rule(w, 0, comp="nucleus", a="Cy5", mode="only")
    r = w.rules["nucleus"]
    ok("rule = Track nucleus using Cy5 ONLY", r.text(names) == "Track nucleus using Cy5 ONLY",
       r.text(names))
    ok("no helper channel lines for ONLY", not w._rows[0]["helpers"])
    ok("step 2 line: Drawn and followed on: Cy5",
       w.lbl_seen.text() == "Drawn and followed on: Cy5", w.lbl_seen.text())
    ok("Settings.track_rules + follow_rows (all channels) kept",
       w.settings.track_rules == [{"comp": "nucleus", "a": "Cy5", "mode": "only", "b": ""}]
       and w.settings.follow_rows == [["nucleus", names]], str(w.settings.track_rules))
    ok("follow = every channel", w.follow == {"nucleus": list(range(len(names)))})
    ok("view switched to Cy5", w.cmb_view.currentText() == "Cy5", w.cmb_view.currentText())
    ok("no 'Tracking image' entry for ONLY", not any("Tracking image" in t for t in view_items(w)))
    ok("background placed", w.background is not None)
    t = time.time()
    w._auto_select()
    wait(w)
    live = w._live("nucleus")
    ok("AUTO-DETECT nuclei on Cy5", len(live) >= 10, f"{len(live)} in {time.time() - t:.1f} s")
    ok("every auto ROI .channel = Cy5", all(int(w.cells[k]["nucleus"].channel) == names.index("Cy5")
                                             for k in live))
    t = time.time()
    w._track()
    wait(w)
    t_gui = time.time() - t
    ok("tracked (GUI, with rules)", w.track is not None, f"{len(live)} nuclei x "
       f"{exp.n_timepoints} in {t_gui:.0f} s")
    ok("track records rules + params", w.track.get("rules") == [
        {"comp": "nucleus", "a": "Cy5", "mode": "only", "b": ""}] and
        w.track.get("params", {}).get("tracker") == MN.TRACKER, str(w.track.get("rules")))
    # ---- the same cells through the V2.2 code path (rules=None)
    s = w.settings
    cells = [{c: r for c, r in cell.items() if c in w.follow} for cell in w.cells]
    t = time.time()
    ref = MN.track_cells(src, exp, cells, w.background, int(w.t0 or 0),
                         float(s.max_move_um), float(s.mito_k), int(exp.sat_level),
                         list(w.follow), size_tol=float(s.track_size_tol), rules=None)
    ok("ONLY via the GUI == V2.2 path (rules=None): every Measurements array identical",
       same_meas(w.track["meas"]["nucleus"], ref["meas"]["nucleus"]),
       f"V2.2 path {time.time() - t:.0f} s")
    ok("... and every ROI at every timepoint identical",
       same_rois(w.track["rois"]["nucleus"], ref["rois"]["nucleus"]))
    # ---- every channel, every ratio pair
    comps = w._export_data()
    M = comps["nucleus"]["M"]
    ok("export data: every channel", list(M.channels) == names and M.mean.shape[1] == len(names),
       f"{M.channels}")
    cat = catalog(comps, w.settings)
    drr = [it["key"] for it in cat if "|graph|dRR_" in it["key"]]
    ok("every ratio pair offered (both directions)", len(drr) == len(names) * (len(names) - 1),
       f"{len(drr)} R/R0 graphs")
    ok("trace opens on your key quantity (R/R0 GFP/Cy5)",
       w.traces.current_quantity() == "R/R0 - GFP/Cy5", w.traces.current_quantity())
    keys = standard(cat, {c: w._prefer_sheets(c, d["M"]) for c, d in comps.items()})
    ok("standard list has the Methods text", "*|methods" in keys)
    t = time.time()
    w._run_export(comps, keys)
    wait(w)
    folder = Path(w._exported or "")
    ok("export finished", w._exported is not None and folder.exists(), f"{time.time() - t:.0f} s")
    stem = Path(NUC).stem[:40]
    mt = folder / f"{stem}_methods.txt"
    txt = mt.read_text(encoding="utf-8") if mt.exists() else ""
    ok("methods.txt written, quotes the rule", '"Track nucleus using Cy5 ONLY"' in txt,
       f"{len(txt)} chars")
    ok("methods.txt uses the tracker's recorded parameters",
       "did not record its own parameters" not in txt and len(txt) > 2000)
    from openpyxl import load_workbook
    xl = [p for p in folder.rglob("*.xlsx") if "baseline_drift" not in p.name]
    wb = load_workbook(xl[0], read_only=True) if xl else None
    sheets = wb.sheetnames if wb else []
    ok("workbook has a Methods sheet (last)", bool(sheets) and sheets[-1] == "Methods",
       f"{xl[0].name if xl else '-'}: {sheets[-3:]}")
    meth = " ".join(str(c) for row in wb["Methods"].iter_rows(values_only=True) for c in row
                    if c is not None) if wb else ""
    from peterpiper.history import nd2_fingerprint
    quick = nd2_fingerprint(NUC).get("quick", "")
    ok("Methods sheet: rule + .nd2 name + its fingerprint",
       "Track nucleus using Cy5 ONLY" in meth and Path(NUC).name in meth
       and bool(quick) and quick[:12] in meth, f"{len(meth)} chars")
    raw = [sh for sh in sheets if sh.startswith("Raw_")]
    ok("workbook: a Raw sheet per channel", len(raw) >= len(names), str(raw))
    if wb:
        wb.close()
    pz = list(folder.rglob("*.pzfx"))
    pzt = pz[0].read_text(encoding="utf-8", errors="replace") if pz else ""
    ok("Prism .pzfx notes carry the rule", "Cy5 ONLY" in pzt, pz[0].name if pz else "-")
    # ---- V2.4: the tracking settings in step 3 (each change clears the tracking)
    ok("V2.4 settings: movement spin shown; IF / AND hidden under ONLY",
       w.sp_move.isVisibleTo(w) and not w.sp_gate.isVisibleTo(w) and not w.sp_and.isVisibleTo(w))
    kept = w.track
    for sp, attr, new_v in ((w.sp_tol, "track_size_tol", 0.30), (w.sp_move, "max_move_um", 4.0),
                            (w.sp_gate, "gate_snr", 6.0), (w.sp_and, "overlap_k", 4.0)):
        old_v = sp.value()
        w.track = kept
        sp.setValue(int(new_v * 100) if sp is w.sp_tol else new_v)
        pump(0.05)
        ok(f"V2.4: changing {attr} after tracking clears it, with the message",
           w.track is None and abs(getattr(w.settings, attr) - new_v) < 1e-9
           and "setting changed" in w.lbl_track.text()
           and "rules or settings" in w.lbl_next.text(), w.lbl_track.text())
        st = w._roi_state("saved")[0]
        ok(f"V2.4: {attr} in the session state", abs(st["track_settings"][attr] - new_v) < 1e-9)
        sp.setValue(old_v)
    w._set_track_settings({"max_move_um": 7.5, "track_size_tol": 0.4})
    ok("V2.4: loading saved settings fills the spin boxes",
       w.sp_move.value() == 7.5 and w.sp_tol.value() == 40 and w.settings.max_move_um == 7.5)
    w._set_track_settings({"max_move_um": 3.0, "track_size_tol": 0.25})
    w.track = kept
    # ---- a rule change after tracking clears it and says so
    set_rule(w, 0, mode="with", b="GFP")
    ok("rule change -> tracking cleared", w.track is None and not w.btn_export.isEnabled())
    ok("... and says so", "tracking rules changed" in w.lbl_track.text()
       and "tracking rules" in w.lbl_next.text(), w.lbl_track.text())
    ok("WITH adds 'Tracking image: Cy5 + GFP' to Show",
       "Tracking image: Cy5 + GFP" in view_items(w), str(view_items(w)[-2:]))
    ok("... and step 2 says combined",
       w.lbl_seen.text() == "Drawn and followed on: Cy5 + GFP (combined; followed on Cy5 only)", w.lbl_seen.text())
    w._undo()
    pump(0.1)
    ok("Undo does not bring back tracking made with other rules", w.track is None)
    set_rule(w, 0, mode="if", b="GFP")
    ok("V2.4: IF rule shows the needed-signal setting only",
       w.sp_gate.isVisibleTo(w) and not w.sp_and.isVisibleTo(w))
    set_rule(w, 0, mode="and", b="GFP")
    ok("V2.4: AND rule shows the pixel-threshold setting only",
       w.sp_and.isVisibleTo(w) and not w.sp_gate.isVisibleTo(w))
    set_rule(w, 0, mode="only")
    ok("back to ONLY: no tracking image entry", not any("Tracking image" in t
                                                         for t in view_items(w)))
    # V2.4 (L11): closing the window while tracking cancels the job and waits for
    # the worker to stop BEFORE the .nd2 is closed
    if not any(w.cells):                       # (the Undo above took the cells back)
        w._auto_select()
        wait(w)
    w._track()
    busy = w._busy_now()                       # closed at once, while it runs
    seen = {}
    real_close = w.src.close

    def spy_close():
        seen["job_stopped"] = w._runner.job.stopped.is_set()
        real_close()
    w.src.close = spy_close
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    t = time.time()
    try:
        w.close()
    finally:
        QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)
    pump(0.3)
    ok("V2.4 (L11): close while tracking -> job cancelled and stopped before the .nd2 closed",
       busy and seen.get("job_stopped") is True and not w.isVisible()
       and not w._runner.thread.isRunning(), f"{seen} busy={busy} vis={w.isVisible()} "
       f"thr={w._runner.thread.isRunning()} in {time.time() - t:.1f} s")
    return len(live)


def part_b(n_only):
    print("\n--- b: start-up from Settings.track_rules (Cy5 IF GFP); AUTO-DETECT skips")
    src = open_source(NUC)
    exp = describe(src, out_dir=str(OUT / "b" / f"OUTPUT_{Path(NUC).stem}"))
    exp.export_tiffs = False
    s = Settings(track_rules=[{"comp": "nucleus", "a": "Cy5", "mode": "if", "b": "GFP"}])
    w = ClickWindow(src, exp, s)
    w.resize(1700, 1000)
    w.show()
    pump(1.0)
    r = w.rules.get("nucleus")
    ok("rule restored from Settings.track_rules",
       r is not None and r.text(exp.channels) == "Track nucleus using Cy5 IF intensity in GFP")
    ok("step 2 line names the gate",
       w.lbl_seen.text() == "Drawn and followed on: Cy5 (cells need GFP signal)", w.lbl_seen.text())
    w._auto_select()
    wait(w)
    n = len(w._live("nucleus"))
    st = w.lbl_status.text().replace(chr(0x200B), "")
    import re
    m = re.search(r"Skipped (\d+) without GFP signal", st)
    skipped = int(m.group(1)) if m else 0
    ok("AUTO-DETECT skipped the nuclei without GFP signal and said so",
       skipped > 0 and n + skipped == n_only if n_only else skipped > 0,
       f"added {n}, skipped {skipped}, ONLY run found {n_only}")
    snr = [w._gate("nucleus", w.cells[k]["nucleus"]) for k in w._live("nucleus")]
    ok("every nucleus kept passes the gate", all(np.isfinite(v) and v >= 5 for v in snr),
       f"min SNR {min(snr):.1f}" if snr else "")
    w.close()
    pump(0.3)


def bright_spots(plane, um, n=3, sep_um=40.0):
    from scipy import ndimage as ndi
    from skimage.feature import peak_local_max
    f = 4
    sm = ndi.gaussian_filter(plane[::f, ::f].astype(np.float32), 2.0 / um / f)
    edge = int(30 / um / f)
    pk = peak_local_max(sm, min_distance=int(sep_um / um / f), exclude_border=edge, num_peaks=40)
    pk = sorted(pk, key=lambda p: -sm[p[0], p[1]])
    return [(int(p[1] * f), int(p[0] * f)) for p in pk[:n]]   # (x, y)


def part_c():
    print("\n--- c: HeLa mRuby file: WITH / AND / IF in the window")
    src = open_source(RUBY)
    exp = describe(src, out_dir=str(OUT / "c" / f"OUTPUT_{Path(RUBY).stem}"))
    exp.export_tiffs = False
    names = list(exp.channels)
    um = exp.um_per_px
    w = ClickWindow(src, exp, Settings(baseline_timepoint=1, resp_quantity=""))
    w.resize(1700, 1000)
    w.show()
    pump(1.0)
    set_rule(w, 0, comp="cell", a="mCherry", mode="with", b="GFP")
    rule = w.rules.get("cell")
    ok("rule = Track whole cell using mCherry WITH intensity in GFP",
       rule is not None and rule.text(names) == "Track whole cell using mCherry WITH intensity in GFP")
    ok("step 2 line: mCherry + GFP (combined)",
       w.lbl_seen.text() == "Drawn and followed on: mCherry + GFP (combined; followed on mCherry only)", w.lbl_seen.text())
    items = view_items(w)
    ok("Show list has 'Tracking image: mCherry + GFP'", "Tracking image: mCherry + GFP" in items,
       str(items[-1:]))
    ok("selecting the compartment switched the view to the tracking image",
       w.cmb_view.currentText() == "Tracking image: mCherry + GFP", w.cmb_view.currentText())
    stack0 = np.asarray(src.frame(0))
    norm = RL.make_norm(stack0)
    guide = RL.guide_plane(stack0, rule, norm)
    shown = w.view._planes[0] if w.view._planes else None
    ok("... and shows the guide plane (float32, = rules.guide_plane)",
       shown is not None and shown.dtype == np.float32 and np.array_equal(shown, guide))
    # ---- click 3 cells at bright spots of the guide plane
    w._tool_clicked("add")
    spots = bright_spots(guide, um)
    first = None
    for x, y in spots:
        if first is None:
            first = MN.draw_at("cell", guide, y, x, um, w.settings, [], None)
        w._on_point(float(x), float(y), False)
        pump(0.1)
    w._tool_clicked("add")
    live = w._live("cell")
    ok("3 cells clicked at bright spots", len(live) == 3, f"spots {spots}")
    r0 = w.cells[live[0]]["cell"] if live else None
    ok("the first is drawn on the guide plane (= draw_at on rules.guide_plane)",
       r0 is not None and first is not None and tuple(r0.bbox) == tuple(first.bbox)
       and np.array_equal(r0.mask, first.mask))
    ok("ROI .channel = rule's channel A (mCherry)",
       all(int(w.cells[k]["cell"].channel) == names.index("mCherry") for k in live))
    ok("norm cached on the drawn frame", w._norm is not None and w._norm[0] == w.t0 == 0)
    t = time.time()
    w._track()
    wait(w)
    ok("tracked WITH (3 cells x 61)", w.track is not None, f"{time.time() - t:.0f} s")
    tr = w.track or {}
    ok("track rules / params recorded (norm included)",
       tr.get("rules") == [{"comp": "cell", "a": "mCherry", "mode": "with", "b": "GFP"}]
       and "norm" in (tr.get("params") or {}), str(tr.get("rules")))
    M = tr["meas"]["cell"] if tr else None
    ok("all measurements finite for the 3 cells",
       M is not None and np.isfinite(M.mean[:, :, live]).all())
    ok("trace opens on R/R0 of the rule's channels (no key quantity set)",
       w.traces.current_quantity() == "R/R0 - mCherry/GFP", w.traces.current_quantity())
    ok("export data has every channel",
       list(w._export_data()["cell"]["M"].channels) == names)
    w.slider.setValue(30)
    pump(0.5)
    shown = w.view._planes[0] if w.view._planes else None
    g30 = RL.guide_plane(np.asarray(src.frame(29)), rule, norm)
    ok("scrubbing shows the tracking image of that timepoint (same frozen norm)",
       shown is not None and np.array_equal(shown, g30))
    w.slider.setValue(1)
    pump(0.3)
    # ---- AND: the kept pixels are shown at once
    set_rule(w, 0, mode="and", b="GFP")
    ok("rule change -> tracking cleared, with the message",
       w.track is None and "tracking rules changed" in w.lbl_track.text(), w.lbl_track.text())
    ok("AND: tracking image entry gone", not any("Tracking image" in t for t in view_items(w)))
    shown_rois = w.view._rois
    seeds = [w.cells[k]["cell"] for k in live]
    kept = [shown_rois[k] for k in live]
    ok("AND: the shown ROI keeps only pixels bright in GFP (subset of the drawn ROI), "
       "drawn ROI unchanged",
       all(getattr(r, "show_kept", False) and r.outline is not None
           and not (r.mask & ~s_.mask).any() for r, s_ in zip(kept, seeds))
       and all(getattr(s_, "outline", None) is None for s_ in seeds),
       "kept " + ", ".join(f"{r.area / max(1, s_.area):.0%}" for r, s_ in zip(kept, seeds)))
    # ---- IF: a cell drawn by hand on an empty area
    set_rule(w, 0, mode="if", b="GFP")
    y0, x0, y1, x1 = w.background.bbox
    cy, cx, h = (y0 + y1) / 2, (x0 + x1) / 2, min(y1 - y0, x1 - x0, int(25 / um)) / 3
    poly = [(cx - h, cy - h), (cx + h, cy - h), (cx + h, cy + h), (cx - h, cy + h)]
    w._tool_clicked("draw")
    w.view.polygon_done.emit(poly)
    pump(0.2)
    st = w.lbl_status.text().replace(chr(0x200B), "")      # (the draw tool is re-armed)
    w._tool_clicked("draw")
    live2 = w._live("cell")
    dim = [k for k in live2 if k not in live]
    ok("hand-drawn cell on an empty area added", len(dim) == 1, f"{len(live2)} cells")
    ok("IF warning at once ('has no GFP signal ... the IF rule will exclude it')",
       "has no GFP signal" in st and "IF rule will exclude it" in st, st[:160])
    t = time.time()
    w._track()
    wait(w)
    gate = (w.track or {}).get("gate", {}).get("cell", {})
    ok("tracked with IF; gate SNR per cell", w.track is not None and len(gate) == 4,
       ", ".join(f"{k + 1}: {v:.1f}" for k, v in sorted(gate.items())) + f"; {time.time() - t:.0f} s")
    why = w._why("cell")
    k = dim[0] if dim else -1
    ok("the empty-area cell is excluded by the IF rule, with the reason",
       k in w.excl["cell"] and why.get(k, "").startswith("excluded by the IF rule: no GFP signal "
                                                         "(IF gate: SNR"), why.get(k))
    ok("the bright cells pass the gate and stay included",
       all(j not in w.excl["cell"] for j in live), str(sorted(w.excl["cell"])))
    ok("tracking line reports the IF exclusion", "IF rule: 1 whole cell ROI(s) excluded"
       in w.lbl_track.text(), w.lbl_track.text()[-140:])
    # review: the IF rule is replaced -> the exclusion it made goes with it (it must
    # not stay behind as 'excluded by you' and silently leave the means)
    set_rule(w, 0, mode="only")
    w._track()
    wait(w)
    why = w._why("cell")
    ok("IF -> ONLY, tracked again: the cell the IF rule excluded is included again",
       w.track is not None and k not in w.excl["cell"]
       and not why.get(k, "").startswith("excluded"), why.get(k))
    set_rule(w, 0, mode="if", b="GFP")
    w._track()
    wait(w)
    why = w._why("cell")
    ok("... back to IF, tracked again: excluded by the IF rule again",
       k in w.excl["cell"] and why.get(k, "").startswith("excluded by the IF rule"), why.get(k))
    w._set_include("cell", k, True)
    why = w._why("cell")
    ok("re-including it by hand works (QC note keeps the reason)",
       k not in w.excl["cell"] and "no GFP signal" in why.get(k, ""), why.get(k))
    # export data carry the reason
    w._set_include("cell", k, False)
    ok("excluded again by you", w._why("cell").get(k) == "excluded by you")
    set_rule(w, 0, mode="only")
    w._track()
    wait(w)
    ok("... YOUR exclusion stays after a rule change and tracking again",
       k in w.excl["cell"] and w._why("cell").get(k) == "excluded by you", w._why("cell").get(k))
    w.close()
    pump(0.3)


def part_d():
    print("\n--- d: V2.2 ROI file with tracking -> default rules, tracking kept")
    if not (Path(V22_ND2).exists() and Path(V22_NPZ).exists()):
        ok("(V2.2 test data present)", False)
        return
    dst = OUT / "d" / Path(V22_NPZ).name
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists():
        shutil.copy2(V22_NPZ, dst)
    src = open_source(V22_ND2)
    exp = describe(src, out_dir=str(OUT / "d" / "OUTPUT"))
    exp.export_tiffs = False
    names = list(exp.channels)
    w = ClickWindow(src, exp, Settings())
    w.resize(1700, 1000)
    w.show()
    pump(1.0)
    t = time.time()
    w._load_roi_file(str(dst))
    pump(0.5)
    from peterpiper.roifile import load_roi_state
    st, _c = load_roi_state(str(dst))
    rows = st.get("follow") or []
    want = RL.default_rules(rows, w.cells, names)
    ok("rules = default_rules(follow rows, drawn channels)",
       [r.to_dict(names) for r in w.rules.values()] == [r.to_dict(names) for r in want],
       "; ".join(r.text(names) for r in w.rules.values()))
    ok("loaded WITH its tracking (export enabled)", w.track is not None and w.btn_export.isEnabled(),
       f"{time.time() - t:.1f} s")
    ok("include / exclude as saved", w.excl.get("mito") == set(st.get("excl", {}).get("mito", [])),
       str(sorted(w.excl.get("mito", []))))
    comps = w._export_data()
    ok("export data: every channel", all(list(d["M"].channels) == names for d in comps.values()))
    prov = w._provenance(comps)
    ok("provenance: rules from the current (default) rules, params not recorded",
       prov["rules"] and prov["track_params"] in (None, {}) and prov["fingerprint"].get("quick"),
       str(prov["rules"]))
    w.close()
    pump(0.3)


def part_l7():
    """V2.4 (L7): an AND frame whose kept pixels are empty shows the followed
    outline, not the drawn ROI (stub window, no data needed)."""
    from types import SimpleNamespace
    from peterpiper.segment import Roi
    drawn = Roi((0, 0, 4, 4), np.ones((4, 4), bool), "nucleus", True, "manual", 1.0)
    followed = Roi((10, 10, 14, 14), np.zeros((4, 4), bool), "nucleus", True, "manual", 0.3)
    followed.outline = np.ones((4, 4), bool)
    gone = Roi((20, 20, 24, 24), np.zeros((4, 4), bool), "nucleus", True, "manual", 0.0)
    fake = SimpleNamespace(cur_t=0, cells=[{"nucleus": drawn}, {"nucleus": drawn}],
                           track={"rois": {"nucleus": [[followed, gone]]}})
    got = ClickWindow._rois(fake, "nucleus")
    ok("V2.4 (L7): AND frame with no kept pixels shows the followed outline; an empty ROI "
       "without outline falls back to the drawn one", got[0] is followed and got[1] is drawn)


t_all = time.time()
n_only = 0
part_l7()
if "a" in args.parts:
    n_only = part_a()
if "b" in args.parts:
    part_b(n_only)
if "c" in args.parts:
    part_c()
if "d" in args.parts:
    part_d()
print()
n_pass = sum(c for _n, c in checks)
print(f"{n_pass} of {len(checks)} checks passed; errors: {len(errors)}; "
      f"{time.time() - t_all:.0f} s")
for e in errors[:5]:
    print(str(e)[-2000:])
crit = [d for d in dialogs if d and "wrong" in str(d[0]).lower()]
for d in crit[:3]:
    print("ERROR DIALOG:", str(d)[:1500])
sys.exit(0 if n_pass == len(checks) and not errors and not crit else 1)
