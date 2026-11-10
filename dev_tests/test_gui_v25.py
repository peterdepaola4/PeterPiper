"""
Developer test (not shipped): the V2.5 main-window features, offscreen, on a
synthetic movie (nuclei of graded brightness, 2 channels) - or with --real on
the u2os .nd2 (first 6 timepoints, read-only on D:).

    PETERPIPER_HOME=<ws>/_home MPLBACKEND=Agg QT_QPA_PLATFORM=offscreen \\
        python dev_tests/test_gui_v25.py [--out <folder>] [--real]

  1  'Size may change by' accepts 0 %; the automatic background is placed
  2  AUTO-DETECT slider: N brightest kept (rank order of mean - background on the
     detection image), live cell count, all back at the right end; a later
     change accepts the set (slider hidden); Undo removes the whole set
  3  background drawn by hand (lasso) -> 'hand' region; Add puts a square
  4  tracker boundary: pick a cell, draw a line, tracking cleared, TRACK passes
     the lines (params), no ROI of that cell ever on the line or beyond it
  5  size 0 %: every tracked ROI has exactly the drawn pixel count
  6  sessions: the boundary lines, background kind and sums are saved; reloading
     restores them; an unchanged session is not saved again (no new file)
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

ap = argparse.ArgumentParser()
ap.add_argument("--out", default=str(REPO / "_out" / "gui_v25"))
ap.add_argument("--real", action="store_true")
args = ap.parse_args()
OUT = Path(args.out).resolve()
if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True, exist_ok=True)
os.environ["PETERPIPER_HOME"] = str(OUT / "home")
os.environ.setdefault("MPLCONFIGDIR", str(OUT / "home" / "mpl"))

errors, dialogs = [], []
sys.excepthook = lambda k, v, tb: errors.append("".join(traceback.format_exception(k, v, tb)))
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

app = QApplication(sys.argv)
for _n in ("information", "warning", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: dialogs.append(a[1:3]) or QMessageBox.Ok))
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)
QMessageBox.exec = lambda self: dialogs.append((self.windowTitle(), self.text())) or 0

from peterpiper import history as H                                    # noqa: E402
from peterpiper import manual as MN                                    # noqa: E402
from peterpiper.config import Settings                                 # noqa: E402
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
from peterpiper.config import Experiment                               # noqa: E402
from peterpiper.nd2io import ImageSource, describe, open_source        # noqa: E402
from peterpiper.roifile import load_roi_track, read_summary            # noqa: E402

ClickWindow._ask_previous_run = lambda self, runs, menu=False: None
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


class Synth(ImageSource):
    """6 timepoints, channels Cy5 (nuclei, graded brightness) and GFP, 480 x 480 px
    at 0.5 um/px; a little drift; noise."""

    def __init__(self, T=6, H=480, W=480):
        self.channels, self.n_timepoints, self.height, self.width = ["Cy5", "GFP"], T, H, W
        rng = np.random.default_rng(7)
        yy, xx = np.mgrid[0:H, 0:W]
        self.frames = []
        cents = [(60 + 70 * i, 60 + 70 * j) for i in range(6) for j in range(6)]
        for t in range(T):
            A = np.full((H, W), 300.0)
            B = np.full((H, W), 250.0)
            for n, (cy, cx) in enumerate(cents):
                d2 = (yy - cy - 0.6 * t) ** 2 + (xx - cx - 0.4 * t) ** 2
                A += (600 + 120 * n) * np.exp(-d2 / (2 * 9.0 ** 2)) * (d2 < 15 ** 2)
                B += (300 + 50 * (n % 5)) * (d2 < 11 ** 2)
            st = np.stack([A, B]) + rng.normal(0, 12, (2, H, W))
            self.frames.append(np.clip(st, 0, 65535).astype(np.uint16))

    def frame(self, t):
        return self.frames[int(t)]


def open_window(T=6):
    if args.real:
        src = open_source(NUC)
        exp = describe(src, out_dir=str(OUT / "results"))
    else:
        src = Synth(T)
        exp = Experiment(nd2_path=str(OUT / "synthetic_movie.nd2"), out_dir=str(OUT / "results"),
                         channels=list(src.channels), n_timepoints=T, width=src.width,
                         height=src.height, um_per_px=0.5, seconds_per_frame=30.0)
    exp.n_timepoints = T
    exp.export_tiffs = False
    Path(exp.out_dir).mkdir(parents=True, exist_ok=True)
    s = Settings()
    w = ClickWindow(src, exp, s)
    w.resize(1600, 960)
    w.show()
    t = time.time()
    while not w._offered and time.time() - t < 30:
        pump(0.1)
    wait(w)
    return w


def sessions():
    d = H.session_dir(str(OUT / "results"))
    return sorted(d.glob("*_session_*.npz")) if d.exists() else []


def main():
    if args.real and not Path(NUC).exists():
        print("test file not found - skipped")
        return 0
    w = open_window()
    cy5 = w.exp.channels.index("Cy5")
    # ---- 1
    w.sp_tol.setValue(0)
    ok("1) size spin accepts 0 %", w.sp_tol.value() == 0 and w.settings.track_size_tol == 0.0)
    ok("1) automatic background placed", w.background is not None and w._bg_kind == "auto",
       f"{w.background.bbox if w.background is not None else None}")
    # ---- 2
    w._set_rules([MN_rule("nucleus", cy5)], quiet=True)
    w.cmb_comp.setCurrentIndex(w.cmb_comp.findData("nucleus"))
    w._auto_select()
    wait(w)
    B = w._auto_batch
    n_all = len(B["cands"]) if B else 0
    ok("2) AUTO-DETECT: candidates found, slider shown", n_all >= 6 and w.auto_row.isVisibleTo(w),
       f"{n_all} found")
    br = B["bright"]
    ok("2) candidates in brightness order (brightest first)", all(br[i] >= br[i + 1]
                                                                  for i in range(len(br) - 1)))
    half = max(1, n_all // 2)
    w.sl_auto.setValue(half)
    pump(0.2)
    n_cells = sum(1 for c in w.cells if "nucleus" in c)
    ok("2) slider: only the N brightest kept, live", n_cells == len(B["placed"]) <= half
       and str(half) in w.lbl_auto.text(), f"{n_cells} cells, slider {half}")
    kept = {id(r) for r in B["placed"]}
    ok("2) the ones kept are the brightest ones", all(id(r) in kept or i >= half
                                                     for i, r in enumerate(B["cands"][:half]))
       and not any(id(r) in kept for r in B["cands"][half:]))
    w.sl_auto.setValue(n_all)
    pump(0.2)
    n_back = sum(1 for c in w.cells if "nucleus" in c)
    ok("2) right end: all of them back", n_back == len(B["placed"]) and n_back >= n_cells)
    w.sl_auto.setValue(8 if n_all > 8 else n_all)
    pump(0.2)
    kept8 = sum(1 for c in w.cells if "nucleus" in c)
    w._undo()
    ok("2) Undo removes the whole auto-detected set", sum(1 for c in w.cells if c) == 0
       and not w.auto_row.isVisibleTo(w))
    w._auto_select()
    wait(w)
    w.sl_auto.setValue(8 if len(w._auto_batch["cands"]) > 8 else len(w._auto_batch["cands"]))
    pump(0.2)
    kept8 = sum(1 for c in w.cells if "nucleus" in c)
    # ---- 3 background by hand
    w.cmb_comp.setCurrentIndex(w.cmb_comp.findData("background"))
    w._set_tool("draw")
    ok("3) Background > Draw by hand starts the freehand outline", w.view.mode == "lasso")
    H_, W_ = w.exp.height, w.exp.width
    cx, cy = W_ * 0.15, H_ * 0.15
    ang = np.linspace(0, 2 * np.pi, 80)
    pts = [(cx + 120 * np.cos(a), cy + 90 * np.sin(a)) for a in ang]
    w._on_lasso(pts)
    ok("3) freehand background region kept, kind 'hand'", w._bg_kind == "hand"
       and w.background is not None and not w._bg_auto and w.background.area > 25000,
       f"{w.background.area if w.background is not None else 0} px")
    ok("3) adding ROIs afterwards accepted the auto-detected set (slider hidden)",
       not w.auto_row.isVisibleTo(w) and w._auto_batch is None)
    w._set_tool(None)
    w.cmb_comp.setCurrentIndex(w.cmb_comp.findData("nucleus"))
    # ---- 4 boundary
    k = next(i for i, c in enumerate(w.cells) if "nucleus" in c)
    r = w.cells[k]["nucleus"]
    y0, x0, y1, x1 = r.bbox
    w.btn_bound.setChecked(True)
    cyy, cxx = r.centroid
    w._on_point(cxx, cyy, False)
    ok("4) boundary: the clicked cell is picked, line drawing on", w._bound_k == k
       and w.view.mode == "polyline")
    xl = (x0 + x1) / 2.0                          # a vertical line through the nucleus
    line = [(xl, y0 - 40.0), (xl, y1 + 40.0)]
    w._on_boundary_line(line)
    w.btn_bound.setChecked(False)
    ok("4) line stored for that cell", w.boundaries.get(k) == [line])
    # ---- 5 + 4 track (size 0)
    drawn = {j: MN._region(c["nucleus"]).area for j, c in enumerate(w.cells) if "nucleus" in c}
    w._track()
    wait(w)
    ok("5) tracked", w.track is not None, f"{len(errors)} errors")
    p = (w.track or {}).get("params", {})
    ok("4) params carry the boundary (1-based cell)", str(k + 1) in (p.get("boundaries") or {}))
    side = MN.boundary_side([line], (H_, W_), w.cells[k]["nucleus"])
    bad = []
    for t in range(w.exp.n_timepoints):
        rr = w.track["rois"]["nucleus"][t][k]
        m = np.zeros((H_, W_), bool)
        a0, b0, a1, b1 = rr.bbox
        m[a0:a1, b0:b1] = MN._shape(rr)
        if (m & ~side).any():
            bad.append(t)
    ok("4) the cell's ROI never touches / crosses its line", not bad, f"{bad}")
    M = w.track["meas"]["nucleus"]
    exact = all(int(M.area_px[t, j]) == a for j, a in drawn.items()
                for t in range(w.exp.n_timepoints))
    off = [(t, j, int(M.area_px[t, j]), a) for j, a in drawn.items()
           for t in range(w.exp.n_timepoints) if int(M.area_px[t, j]) != a]
    ok("5) size 0 %: every ROI-timepoint has exactly the drawn pixel count", exact,
       f"boundary cell {k}; off: {off[:6]}")
    ok("5) sums recorded; mean = sum / area", M.sum is not None
       and np.array_equal(M.mean, M.sum / np.where(M.area_px > 0, M.area_px, 1)[:, None, :],
                          equal_nan=True))
    # ---- 6 sessions
    w._writer.flush()
    pump(0.3)
    files = sessions()
    ok("6) session saved after tracking", len(files) == 1, f"{[f.name for f in files]}")
    s = read_summary(files[0]) if files else {}
    tr = load_roi_track(files[0]) if files else None
    ok("6) saved: content key, sums", bool(s.get("content_key")) and tr is not None
       and tr["meas"]["nucleus"].sum is not None)
    mtime = files[0].stat().st_mtime if files else 0
    w._dirty = True
    started = w._autosave()
    w._writer.flush()
    pump(0.2)
    ok("6) unchanged session: not saved again", started is False and len(sessions()) == 1
       and files[0].stat().st_mtime == mtime)
    w.q_base.setValue(2)                          # a real change
    started = w._autosave()
    w._writer.flush()
    pump(0.2)
    ok("6) a change is saved (same file, replaced)", started is True and len(sessions()) == 1)
    path = str(sessions()[0])
    w.close()
    pump(0.5)
    # reload in a fresh window
    w2 = open_window()
    w2._load_roi_file(path)
    wait(w2)
    ok("6) reload: boundary lines, hand background and tracking restored",
       w2.boundaries.get(k) == [[tuple(q) for q in line]] and w2._bg_kind == "hand"
       and w2.track is not None, f"{w2.boundaries}")
    n0 = len(sessions())
    import json as _json
    from peterpiper.roifile import session_blob, _norm_state
    st, an, cp, bgr, shp, t0 = w2._roi_state("session")
    blob = session_blob(an, bgr, shp, t0 + 1, state=st, comps=cp, track=w2.track)
    with np.load(path) as z:
        old = {kk: z[kk] for kk in z.files}
    dif = [kk for kk in set(old) | set(blob) if kk != "state_json" and (
        kk not in old or kk not in blob or np.asarray(old[kk]).dtype != np.asarray(blob[kk]).dtype
        or not np.array_equal(np.asarray(old[kk]), np.asarray(blob[kk])))]
    s_old = _json.loads(_norm_state(_json.loads(str(old["state_json"]))))
    s_new = _json.loads(_norm_state(_json.loads(str(blob["state_json"]))))
    print("     differing arrays:", dif[:10], "state keys:",
          [kk for kk in set(s_old) | set(s_new) if s_old.get(kk) != s_new.get(kk)])
    w2._dirty = True
    w2._autosave()
    w2._writer.flush()
    pump(0.2)
    ok("6) a loaded run that is not changed is not saved again", len(sessions()) == n0,
       f"{n0} -> {len(sessions())}")
    w2.close()
    pump(0.3)
    ok("no exceptions in the GUI", not errors, errors[0][-400:] if errors else "")
    n_bad = sum(1 for _n, c in checks if not c)
    print(f"\n{len(checks) - n_bad} / {len(checks)} checks passed")
    return 1 if n_bad else 0


def MN_rule(comp, a):
    from peterpiper.rules import TrackRule
    return TrackRule(comp, a)


if __name__ == "__main__":
    sys.exit(main())
