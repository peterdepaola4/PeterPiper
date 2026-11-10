"""PeterPiperV2.2 regression, adapted to V2.3 (developer test, not shipped):
unlimited resize, split, add to cell, size guard, saved tracking, TIFFs, export.

    PETERPIPER_HOME=<ws>/_home MPLBACKEND=Agg QT_QPA_PLATFORM=offscreen \\
        python dev_tests/test_regress_v22.py <ws>/app <ws>/_out/v22 <file.nd2>

Copied from the V2.2 developer tools. V2.3 changes: the 'Seen on channel'
combo is gone - the nucleus rule's channel A is set instead (step 1); the
settings stay in $PETERPIPER_HOME (nothing is written under D:\\).
"""
import os as _os, pathlib as _pl
_H = _pl.Path(_os.environ.get("PETERPIPER_HOME") or (_pl.Path(__file__).resolve().parents[1] / "_home"))
_H.mkdir(parents=True, exist_ok=True)
_os.environ["MPLCONFIGDIR"] = str(_H / "mpl")
import sys, time, traceback
from pathlib import Path
import numpy as np
sys.path.insert(0, sys.argv[1])
OUT = Path(sys.argv[2]).resolve()
if _os.name == "nt" and not str(OUT).startswith("\\\\?\\"):
    OUT = Path("\\\\?\\" + str(OUT))     # v2.3 test: deep scratch folder, paths > 260 chars
OUT.mkdir(parents=True, exist_ok=True)
errors, dialogs = [], []
sys.excepthook = lambda k, v, tb: errors.append("".join(traceback.format_exception(k, v, tb)))
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QMessageBox
app = QApplication(sys.argv); app.setStyle("Fusion")
for n in ("information", "warning", "critical"):
    setattr(QMessageBox, n, staticmethod(lambda *a, **k: dialogs.append(a[1:3]) or QMessageBox.Ok))
QMessageBox.exec = lambda self: dialogs.append((self.windowTitle(), self.text())) or 0
from peterpiper.config import Settings
from peterpiper.nd2io import open_source, describe
from peterpiper.gui.clickwin import ClickWindow

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
from peterpiper.export import catalog, standard
from peterpiper.plots import preferred_sheets

checks = []


def ok(name, cond, extra=""):
    checks.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra else ""), flush=True)


def pump(sec=0.3):
    t = time.time()
    while time.time() - t < sec:
        app.processEvents(); time.sleep(0.005)


def wait(w):
    pump(0.3)
    while w._busy_now():
        app.processEvents(); time.sleep(0.02)
    pump(0.3)


def wheel(w, notches):
    vp = w.view.glw.viewport()
    c = QPointF(vp.width() / 2, vp.height() / 2)
    ev = QWheelEvent(c, vp.mapToGlobal(c), QPoint(0, 0), QPoint(0, 120 * notches),
                     Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
    QApplication.sendEvent(vp, ev)
    pump(0.1)




from peterpiper import manual as MN
from peterpiper.nd2io import export_tiffs, export_view_copies
import copy, tifffile
path = sys.argv[3]
src = open_source(path)
exp = describe(src, out_dir=str(OUT / f"OUTPUT_{Path(path).stem}")); exp.export_tiffs = False
ch = {n: i for i, n in enumerate(exp.channels)}
T, um = exp.n_timepoints, exp.um_per_px
w = ClickWindow(src, exp, Settings(baseline_timepoint=5)); w.resize(1700, 1000); w.show(); pump(1.0)
w._rows[0]["a"].setCurrentIndex(ch["GFP"]); pump(0.1)     # v2.3: 'Track nucleus using GFP ONLY'
ok("v2.3: nucleus rule on GFP", w.rules["nucleus"].text(exp.channels) == "Track nucleus using GFP ONLY")

# ---- 2  TIFFs: raw counts kept + Fiji display range; viewing copies visible
e2 = copy.copy(exp); e2.out_dir = str(OUT); e2.n_timepoints = 2; e2.tiff_subdir = "Raw TIFFs"
f = export_tiffs(src, e2)
fn = sorted(Path(f).glob("*GFP_t001.tif"))[0]
with tifffile.TiffFile(fn) as tf:
    a = tf.asarray(); ij = tf.imagej_metadata or {}
raw = np.asarray(src.frame(0))[ch["GFP"]]
ok("raw TIFF = the raw counts, unchanged", a.dtype == raw.dtype and np.array_equal(a, raw), f"{a.dtype} max {a.max()}")
ok("raw TIFF carries a display range for Fiji", "min" in ij and "max" in ij and ij["max"] > ij["min"] and ij["max"] < 0.5 * 65535,
   f"min {ij.get('min')}, max {ij.get('max')}")
v = export_view_copies(src, e2)
from PIL import Image
im = np.asarray(Image.open(sorted(Path(v).glob("*GFP_t001*.png"))[0]))
ok("viewing copy is visible (not black)", im.dtype == np.uint8 and np.percentile(im, 99.5) > 120 and im.max() == 255, f"cells at {np.percentile(im, 99.5):.0f}/255, background {np.median(im):.0f}")

# ---- auto-detect
w._auto_select(); wait(w)
live = w._live("nucleus")
ok("auto-detect nuclei", len(live) >= 40, f"{len(live)}")

# ---- 3  scroll: no limit, every notch changes it
w._tool_clicked("resize")
nuc = {k: w.cells[k]["nucleus"] for k in live}
k1 = sorted(live, key=lambda k: -nuc[k].area)[len(live) // 2]
cy, cx = nuc[k1].centroid
a0 = nuc[k1].area
w._on_point(float(cx), float(cy), False); pump(0.1)
ups = []
for i in range(14):
    wheel(w, +1); ups.append(w.cells[k1]["nucleus"].area)
downs = []
for i in range(30):
    wheel(w, -1); downs.append(w.cells[k1]["nucleus"].area)
ok("scroll up 14 notches: bigger every notch, far past the old limit",
   all(b > a for a, b in zip([a0] + ups, ups)) and ups[-1] > 3 * a0,
   f"{a0 * um * um:.0f} -> {ups[-1] * um * um:.0f} um2 (x{ups[-1] / a0:.1f})")
ok("then scroll down 30: smaller every notch until tiny",
   all(b < a for a, b in zip(downs[:20], downs[1:21])) and downs[-1] < 0.2 * a0,
   f"-> {downs[-1] * um * um:.1f} um2 (x{downs[-1] / a0:.2f})")
ok("resized ROI never overlaps another cell",
   all(MN._overlap_px(w.cells[k1]["nucleus"], w.cells[j]["nucleus"]) == 0 for j in live if j != k1))
w._undo(); pump(0.1)
ok("undo restores it", w.cells[k1]["nucleus"].area == a0)
w._tool_clicked("resize")

# ---- 4a  Split along a freehand line
n_before = len(w.cells)
r = w.cells[k1]["nucleus"]; y0, x0, y1, x1 = r.bbox
cy, cx = r.centroid
pts = [(x0 + (x1 - x0) * f, cy + 1.5 * np.sin(6 * f)) for f in np.linspace(0.25, 0.75, 25)]   # only partly across
w._tool_clicked("split")
ok("Split tool on (freehand mode)", w.tool == "split" and w.view.mode == "freehand")
w.view.stroke_done.emit(pts); pump(0.1)
new_k = len(w.cells) - 1
ok("a line through a nucleus splits it into two cells", len(w.cells) == n_before + 1 and "nucleus" in w.cells[new_k],
   f"{w.cells[k1]['nucleus'].area} + {w.cells[new_k].get('nucleus', MN.Roi((0,0,1,1), np.zeros((1,1),bool))).area} px of {a0}")
if len(w.cells) == n_before + 1:
    tot = w.cells[k1]["nucleus"].area + w.cells[new_k]["nucleus"].area
    ok("the two halves cover the original", 0.97 * a0 <= tot <= a0 and
       MN._overlap_px(w.cells[k1]["nucleus"], w.cells[new_k]["nucleus"]) == 0, f"{tot} of {a0}")
    ya, yb_ = w.cells[k1]["nucleus"].centroid[0], w.cells[new_k]["nucleus"].centroid[0]
    ok("upper / lower halves (the cut follows the line)", min(ya, yb_) < cy - 2 and max(ya, yb_) > cy + 2,
       f"{ya:.0f} / {yb_:.0f} around {cy:.0f}")
    w._undo(); pump(0.1)
ok("undo joins it again", len(w.cells) == n_before and w.cells[k1]["nucleus"].area == a0)
w._tool_clicked("split")

# ---- 4b  Add to cell
w._tool_clicked("resize"); w._on_point(float(cx), float(cy), False); pump(0.1)
wheel(w, -6); pump(0.1)
small = w.cells[k1]["nucleus"]; a_small = small.area
w.view.escape_pressed.emit(); w._tool_clicked("resize")
w._tool_clicked("extend")
ok("Add-to-cell tool on", w.tool == "extend")
w._on_point(float(cx), float(cy), False); pump(0.1)            # pick the cell
ok("clicking the ROI picks the cell", w._extend_k == k1)
yb, xb = small.bbox[0], small.bbox[1]
tgt = None
for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):                 # just outside the shrunk ROI,
    yy, xx = int(cy), int(cx)                                     # still inside the real nucleus
    while 0 <= yy - yb < small.mask.shape[0] and 0 <= xx - xb < small.mask.shape[1] and small.mask[yy - yb, xx - xb]:
        yy += dy; xx += dx
    yy += dy * int(1.0 / um); xx += dx * int(1.0 / um)
    n0 = nuc[k1]
    if n0.bbox[0] <= yy < n0.bbox[2] and n0.bbox[1] <= xx < n0.bbox[3] and n0.mask[yy - n0.bbox[0], xx - n0.bbox[1]]:
        tgt = (xx, yy); break
ok("(found a test point in the missed part)", tgt is not None)
w._on_point(float(tgt[0]), float(tgt[1]), False); pump(0.1)
a_after = w.cells[k1]["nucleus"].area
ok("clicking a missed part next to it adds it to that cell", a_after > a_small * 1.05 and len(w.cells) == n_before,
   f"{a_small * um * um:.0f} -> {a_after * um * um:.0f} um2")
ok("still one connected ROI, no other cell touched", MN.ndi.label(w.cells[k1]["nucleus"].mask)[1] == 1 and
   all(MN._overlap_px(w.cells[k1]["nucleus"], w.cells[j]["nucleus"]) == 0 for j in live if j != k1))
w._tool_clicked("extend")
for _ in range(2):
    w._undo(); pump(0.05)
ok("undo back to the auto-detected nucleus", w.cells[k1]["nucleus"].area == a0, f"{w.cells[k1]['nucleus'].area} vs {a0}")

# ---- 6  size guard while tracking
t = time.time(); w._track(); wait(w)
ok("tracked", w.track is not None, f"{len(w._live('nucleus'))} nuclei x {T} in {time.time() - t:.0f} s, redrawn {w.track['redrawn']}")
M = w.track["meas"]["nucleus"]
drawn = np.array([w.cells[k]["nucleus"].area if "nucleus" in w.cells[k] else np.nan for k in range(len(w.cells))], float)
ratio = (M.area_px / drawn[None, :])[:, np.isfinite(drawn)]
ok("size guard: every tracked nucleus within +/-25 % (+fit slack) of its drawn size at every timepoint",
   np.nanmin(ratio) >= 0.70 and np.nanmax(ratio) <= 1.30,
   f"area/drawn: min {np.nanmin(ratio):.2f}, 1st pct {np.nanpercentile(ratio, 1):.2f}, "
   f"99th {np.nanpercentile(ratio, 99):.2f}, max {np.nanmax(ratio):.2f}")
q = M.quality[:, np.isfinite(drawn)]
ok("most frames still truly redrawn (not just moved)", np.mean(q >= 0.9) >= 0.85, f"{np.mean(q >= 0.9):.0%}")

# ---- 6b  ROI file keeps the tracking; reload needs no re-tracking
p = w._save_rois(silent=True)
ok("ROI file saved", p is not None and Path(p).exists(), f"{Path(p).stat().st_size / 1e6:.1f} MB")
w2 = ClickWindow(src, exp, Settings(baseline_timepoint=5)); w2.show(); pump(0.5)
t = time.time(); w2._load_roi_file(p); pump(0.3)
ok("reloaded WITH tracking (export enabled, no re-track)", w2.track is not None and w2.btn_export.isEnabled(),
   f"{time.time() - t:.1f} s")
M2 = w2.track["meas"]["nucleus"]
ok("reloaded measurements identical", np.allclose(M2.mean, M.mean, equal_nan=True) and np.array_equal(M2.area_px, M.area_px))
ok("reloaded ROIs identical at the last timepoint", all(np.array_equal(a.mask, b.mask) and a.bbox == b.bbox
   for a, b in zip(w.track["rois"]["nucleus"][T - 1], w2.track["rois"]["nucleus"][T - 1])))
ok("reloaded include / exclude identical", w2.excl == w.excl)
ok("v2.3: reloaded tracking rules identical", w2._rules_key() == w._rules_key(),
   "; ".join(r.text(exp.channels) for r in w2.rules.values()))
w2.slider.setValue(T); pump(0.3)
comps = w2._export_data(); cat = catalog(comps, w2.settings)
keys = standard(cat, {c: preferred_sheets(d["M"], w2.settings) for c, d in comps.items()})
w2._run_export(comps, keys); wait(w2)
files = [q.name for q in Path(w2._exported).rglob("*") if q.is_file()]
ok("export from the reloaded session", any(f.endswith(".xlsx") for f in files), f"{len(files)} files")
ok("v2.3: the export has the Methods text", any(f.endswith("_methods.txt") for f in files))
w2.close(); pump()
print()
print(f"{sum(c for _n, c in checks)} of {len(checks)} checks passed; errors: {len(errors)}")
for e in errors[:5]:
    print(str(e)[-1500:])
w.close(); pump()
sys.exit(0 if all(c for _n, c in checks) and not errors else 1)
