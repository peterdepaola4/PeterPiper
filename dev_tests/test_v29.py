"""
Developer test (not shipped): V3.0 look, checks and flow.

    MPLBACKEND=Agg QT_QPA_PLATFORM=offscreen python dev_tests/test_v29.py

A) themes: both apply, their tick / arrow icons are drawn, switching changes the
   image background and is remembered; saving settings keeps the last folders.
B) AUTO-DETECT: the built-in limits of every earlier version (old 'learned'
   settings ignored); 'Learn from my runs' is retired.
C) the ratio check (a channel below k x the noise of the ROI's mean at baseline:
   the cell's F/F0 / ratio / R/R0 left out; a ratio's points where the denominator
   collapses left out; k = 0 off; old results without noise untouched) on numbers
   with a known answer; mean ± SD the default, a saved SEM moved to SD once.
D) the main window: no automatic background (the next-step box and TRACK lead you
   to place it); the step bar starts on Rules, which shows the active rule when
   folded; a channel with no signal has its F/F0 left out with the reason; Save
   ROIs shows a fading note; an export with short names (workbook / methods keep
   the movie name), SD in the CSV and workbook, Noise sheets and MinSNR; the
   methods text; the long-path estimate.
E) smooth playback: the half-size display copy is the 2 x 2 block mean, shown
   while zoomed out and replaced by the full frame when zoomed in.
F) polish: loading bars (background work returns its result / error, the bar
   shows only for slow work, step-by-step bars); user profiles (the first user
   gets the data already here, later users start empty; settings, run list and
   results folders per user; each run records its user; 'Earlier analyses' and
   Compare list only the user's own runs, another user's run opened on purpose is
   marked); the Compare graph's dashed baseline line at time 0.
H) the shipped synthetic movie with known answers (16 nuclei; sensor cells' GFP
   F/F0 = 2.0; untransfected cells left out of F/F0 and R/R0); lab-only tests
   skipped without the lab's movies; a run with an automatic background flagged
   on load; portable profiles - export to a zip, import on 'another computer'
   (new user, then merged: settings kept, a differing template kept as
   '(imported)', run list not doubled), a pasted profile folder recognised, an
   unsafe zip refused; runs found again with 'My data is in...' and the new place
   remembered; missing runs kept in the list.
G) computer check: the long-path setting read from Windows (a command to copy
   when off, never run), the Python version, shown at the first start and again
   only when a result changes (or never, if switched off).
"""
from __future__ import annotations

import labdata  # noqa: E402  (lab file names: dev_tests/lab_paths.json, never uploaded)

import json
import os
import shutil
import sys
import time
from pathlib import Path

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                                  # noqa: BLE001
    pass
HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "app"))
sys.path.insert(0, str(HERE))
OUT = REPO / "_out" / "v29"
if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True)
os.environ["PETERPIPER_HOME"] = str(OUT / "home")
os.environ.setdefault("MPLCONFIGDIR", str(OUT / "home" / "mpl"))

from PySide6.QtCore import Qt                                       # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox   # noqa: E402

app = QApplication(sys.argv)
BOXES = []
for _n in ("information", "warning", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: (BOXES.append(a[1:3]),
                                                           QMessageBox.Ok)[1]))
QMessageBox.exec = lambda self: 0

from peterpiper import manual as MN                                     # noqa: E402
from peterpiper.config import Experiment, Settings, load_settings, save_settings  # noqa: E402
from peterpiper.gui import theme as TH                                  # noqa: E402
from peterpiper.nd2io import ImageSource                               # noqa: E402
from peterpiper.segment import Roi                                     # noqa: E402

FAILS: list = []
N = [0]


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


# ===================================================================== A
def part_a():
    for name in ("midnight", "daylight"):
        t = TH.apply(app, name, 10.0)
        ss = app.styleSheet()
        ok(f"A {name}: applied ({len(ss)} characters of style)", t.name == name and len(ss) > 2000)
        icons = list((OUT / "home" / "theme" / name).glob("*.png"))
        ok(f"A {name}: tick / arrow icons drawn", len(icons) >= 6, str(len(icons)))
    ok("A default theme is Midnight (dark)", TH.DEFAULT == "midnight"
       and Settings().ui_theme == "midnight")
    # last folders survive a settings save without an experiment
    s = Settings()
    save_settings(s, Experiment(nd2_path=str(OUT / "x" / "movie.nd2"), out_dir=str(OUT / "res")))
    s.ui_theme = "daylight"
    save_settings(s)
    got, extra = load_settings()
    ok("A saving settings keeps the last folders", extra.get("last_out") == str(OUT / "res")
       and got.ui_theme == "daylight", str(extra))


# ===================================================================== B
def part_b():
    p = MN.DetectParams()
    ok("B built-in limits = the fixed numbers before V2.9",
       (p.min_area_um2, p.max_area_um2, p.min_solidity, p.min_lift_noise, p.min_lift_top,
        p.dim_frac, p.circ_bright, p.circ_dim, p.dim_solidity, p.frag_frac)
       == (30.0, 1000.0, 0.80, 3.0, 0.015, 0.08, 0.60, 0.70, 0.88, 0.30))
    # a synthetic plane: nuclei of 3 sizes
    H = W = 400
    yy, xx = np.mgrid[0:H, 0:W]
    plane = np.full((H, W), 200.0)
    rng = np.random.default_rng(3)
    for i in range(5):
        for j in range(5):
            cy, cx, r = 40 + 80 * i, 40 + 80 * j, (6, 10, 16)[(i + j) % 3]
            plane += 1500 * ((yy - cy) ** 2 + (xx - cx) ** 2 < r * r)
    plane = (plane + rng.normal(0, 10, plane.shape)).astype(np.float32)
    s = Settings()
    s.__dict__.update(auto_params={"max_area_um2": 100.0}, use_learned_params=True)
    got = MN.auto_select(plane, "nucleus", 0.5, s, [], [], None)
    ok("B AUTO-DETECT: the built-in limits (old 'learned' settings are ignored)",
       len(got) == 25, str(len(got)))
    import importlib.util
    ok("B 'Learn from my runs' is retired", importlib.util.find_spec("peterpiper.learn") is None
       and importlib.util.find_spec("peterpiper.gui.learndlg") is None
       and not hasattr(Settings(), "use_keep_model"))


# ===================================================================== C
def part_c():
    """The ratio check (rule B: k x the noise of the ROI's mean), SD everywhere."""
    from peterpiper import measure as MS
    from peterpiper.measure import Measurements
    from peterpiper import graphstyle as GS
    T, Cn, Nn = 6, 2, 5
    mean = np.zeros((T, Cn, Nn))
    mean[:, 0, :] = 100 + np.array([200, 3, 200, 150, 80])[None, :] * np.linspace(1, 2, T)[:, None]
    mean[:, 1, :] = 100 + np.array([300, 300, 2, 300, 300])[None, :]
    mean[4:, 1, 3] = 100.5                  # cell 4: the denominator collapses at t5, t6
    M = Measurements(mean=mean, background=np.full((T, Cn), 100.0),
                     area_px=np.full((T, Nn), 400.0), n_saturated=np.zeros((T, Cn, Nn)),
                     quality=np.ones((T, Nn)), channels=["GFP", "Cy5"],
                     background_sd=np.full((T, Cn), 20.0))          # ROI-mean noise = 1
    ok("C noise of an ROI's mean = pixel SD / sqrt(pixels)",
       np.allclose(M.mean_noise(0), 1.0))
    ok("C default k = 5", MS.MIN_BASELINE_SNR == 5.0 and Settings().ratio_min_snr == 5.0)
    rr = M.rr0(0, 1, 0, 5)
    blank = [k + 1 for k in range(Nn) if not np.isfinite(rr[:, k]).any()]
    ok("C R/R0: cells with a channel below 5 x noise at baseline are left out",
       blank == [2, 3], str(blank))
    r = M.ratio_checked(0, 1, 0, 5)
    ok("C ratio: single points left out where the denominator collapses",
       list(np.where(~np.isfinite(r[:, 3]))[0] + 1) == [5, 6]
       and np.isfinite(r[:4, 3]).all())
    ok("C kept values are untouched", np.allclose(rr[:, 0], M.fold_change(M.ratio(0, 1), 0)[:, 0]))
    ok("C F/F0 GFP: only the dim cell left out",
       [k + 1 for k in range(Nn) if not np.isfinite(M.ff0(0, 0, 5)[:, k]).any()] == [2])
    ok("C k = 0 switches it off", np.isfinite(M.rr0(0, 1, 0, 0)[:4]).all())
    M2 = Measurements(mean=mean, background=np.full((T, Cn), 100.0),
                      area_px=np.full((T, Nn), 400.0), n_saturated=np.zeros((T, Cn, Nn)),
                      quality=np.ones((T, Nn)), channels=["GFP", "Cy5"])
    ok("C no noise recorded (old results): nothing left out", np.isfinite(
        M2.rr0(0, 1, 0, 5)[:, [0, 1, 2]]).sum() > 0 and M2.mean_noise(0) is None)
    # SD everywhere
    ok("C mean ± SD is the default error", GS.GraphStyle().error == "SD")
    from peterpiper.config import _settings_file
    raw = json.loads(_settings_file().read_text(encoding="utf-8"))
    raw["settings"]["graph_style"] = {"error": "SEM"}
    raw["settings"]["sd_v29"] = False
    _settings_file().write_text(json.dumps(raw), encoding="utf-8")
    got, _ = load_settings()
    ok("C a saved SEM (the old default) becomes SD once", got.graph_style.get("error") == "SD"
       and got.sd_v29)
    got.graph_style = {"error": "SEM"}
    save_settings(got)
    ok("C ... and SEM chosen afterwards stays", load_settings()[0].graph_style["error"] == "SEM")
    got.graph_style = {}
    save_settings(got)


# ===================================================================== D
class Synth(ImageSource):
    """3 timepoints, Cy5 nuclei (12 bright, 12 dim) and a GFP channel with no
    signal (flat) - its F/F0 and ratios must be left out; 0.5 um/px."""

    def __init__(self, T=3, H=480, W=480):
        self.channels, self.n_timepoints, self.height, self.width = ["Cy5", "GFP"], T, H, W
        rng = np.random.default_rng(11)
        yy, xx = np.mgrid[0:H, 0:W]
        A = np.full((H, W), 300.0)
        for n in range(24):
            cy, cx = 50 + 75 * (n // 6), 50 + 75 * (n % 6)
            amp = 3000 if n % 2 == 0 else 700
            A += amp * ((yy - cy) ** 2 + (xx - cx) ** 2 < 13 ** 2)
        self.frames = []
        for t in range(T):
            st = np.stack([A, np.full((H, W), 250.0)]) + rng.normal(0, 12, (2, H, W))
            self.frames.append(np.clip(st, 0, 65535).astype(np.uint16))

    def frame(self, t):
        return self.frames[int(t)]


def part_d():
    from peterpiper.gui.clickwin import ClickWindow
    from peterpiper.export import run_export
    from peterpiper.provenance import methods_text
    ClickWindow._ask_previous_run = lambda self, runs, menu=False: None
    TH.apply(app, "midnight", 10.0)
    src = Synth()
    exp = Experiment(nd2_path=str(OUT / "synthetic.nd2"), out_dir=str(OUT / "results"),
                     channels=list(src.channels), n_timepoints=3, width=480, height=480,
                     um_per_px=0.5, seconds_per_frame=30.0)
    exp.export_tiffs = False
    Path(exp.out_dir).mkdir(parents=True, exist_ok=True)
    w = ClickWindow(src, exp, Settings(baseline_timepoint=1))
    w.resize(1600, 960)
    w.show()
    t0 = time.time()
    while not w._offered and time.time() - t0 < 30:
        pump(0.1)
    pump(1.0)
    ok("D no automatic background region", w.background is None and not w._bg_auto)
    ok("D the next-step box asks you to pick a background spot",
       "BACKGROUND" in w.lbl_next.text())
    ok("D step bar: Rules is current until looked at", w._step_now == 0 and
       [b.property("step") for b in w._step_btns] == ["current", "todo", "todo", "todo", "todo"])
    ok("D steps 1-2 open, 3-5 folded", [bool(b.property("folded")) for b in w._step_boxes]
       == [False, False, True, True, True])
    ok("D the learning controls are gone", not hasattr(w, "chk_learned")
       and not hasattr(w, "btn_learn"))
    w._goto_step(0, user=True)
    pump(0.3)
    ok("D looking at the rules: ROIs becomes current", w._step_now == 1)
    w._auto_select()
    pump(0.3)
    while w._busy_now():
        pump(0.05)
    pump(0.5)
    ok("D AUTO-DETECT found all 24", sum(1 for c in w.cells if "nucleus" in c) == 24)
    title = w._step_boxes[0].title()
    ok("D folded Rules step shows the active rule (V3.0: in a few words, whole on hover)",
       "nucleus: Cy5" in title and "Auto-detect nucleus using Cy5" in w._step_boxes[0].toolTip(),
       title)
    w._track()
    pump(0.3)
    ok("D TRACK without a background: straight to placing it (no OK box)",
       w.comp == "background" and w.tool == "add" and w.track is None
       and "background spot" in w.lbl_status.text())
    w._place_background(400.0, 440.0)
    pump(0.2)
    ok("D a background spot placed by you", w.background is not None and not w._bg_auto)
    w.cmb_comp.setCurrentIndex(w.cmb_comp.findData("nucleus"))
    w._track()
    pump(0.3)
    while w._busy_now():
        pump(0.05)
    pump(0.5)
    ok("D tracked", w.track is not None)
    w.traces.cmb_what.setCurrentText("F/F0 - GFP")
    w.traces.refresh()
    pump(0.2)
    head = w.traces.header.text()
    ok("D GFP has no signal: its F/F0 is left out, and the panel says why",
       "have no value here" in head and "24 included" in head, head[-160:])
    ok("D the Check cells band follows the error choice (SD)", "shaded = SD" in head, head[:160])
    n_box = len(BOXES)
    w._save_rois(silent=False)
    pump(0.3)
    ok("D Save ROIs: a fading note, no OK box", len(BOXES) == n_box and
       getattr(w, "_toasts", [])[-1][0] == "ROIs saved", str(getattr(w, "_toasts", None)))
    tn = getattr(w, "_toast_now", None)
    ok("D the note has Open folder", tn is not None and tn.btn_action is not None
       and tn.btn_action.text() == "Open folder")
    # an export: short names inside OUTPUT, SD in the CSV, the methods text
    comps = w._export_data()
    keys = ["nucleus|csv", "nucleus|graph|dFF_Cy5", "nucleus|excel", "*|methods"]
    out = run_export(exp.out_dir, exp, w.settings, comps, keys, src=src,
                     background=w.background, t0=0, prefix="")
    names = [Path(f).name for f in out["files"]]
    ok("D export: graphs and CSV do not repeat the movie name",
       all(not n.startswith("synthetic_") for n in names if n.endswith((".csv", ".png")))
       and any(n == "F-F0 Cy5.png" or n.startswith("F-F0") for n in names), str(names[:6]))
    ok("D ... the workbook and methods text keep it",
       "synthetic_nucleus.xlsx" in names and "synthetic_methods.txt" in names, str(names))
    csvf = next(f for f in out["files"] if f.endswith(".csv"))
    ok("D CSV has an SD column", Path(csvf).read_text(encoding="utf-8").splitlines()[0]
       .endswith(",Mean,SEM,n,SD"))
    out2 = run_export(exp.out_dir, exp, w.settings, comps, ["nucleus|csv"], src=src, prefix="myname")
    ok("D a name you type is kept on every file",
       all(Path(f).name.startswith("myname_") for f in out2["files"]))
    import openpyxl
    wb = openpyxl.load_workbook(next(f for f in out["files"] if f.endswith(".xlsx")))
    ok("D workbook: Noise sheets, MinSNR and an SD column",
       "Noise_GFP" in wb.sheetnames and "MinSNR" in wb.defined_names
       and any(c.value == "SD (included)" for c in wb["dFF_Cy5"][1]))
    txt = methods_text(w.settings, exp, comps=["nucleus"])
    ok("D methods: mean ± SD and the ratio check", "mean ± SD of the included" in txt
       and "× the noise of the ROI's mean" in txt and "learned" not in txt)
    from peterpiper.export import longest_path
    deep = labdata.T("t21") + "x" * 150 + "/OUTPUT_movie/Peter"
    ok("D path estimate for the long-path warning",
       longest_path(deep, "D:/m/" + "m" * 40 + ".nd2", "", [("Nucleus", "nucleus")]) > 250
       and longest_path(str(OUT), "movie.nd2", "", [("Nucleus", "nucleus")]) < 250)
    w._dirty = False
    w.close()
    pump(0.3)


# ===================================================================== E
def part_e():
    from peterpiper.gui.frames import FrameStore
    from peterpiper.gui.imageview import ImageView

    class Big:
        def frame(self, t):
            rng = np.random.default_rng(t)
            return rng.integers(0, 4000, (1, 1800, 1800)).astype(np.uint16)
    fs = FrameStore(Big(), 2, 1800 * 1800 * 2, preview_f=2)
    a = fs.get_now(0)
    p = fs.get_preview(0)
    ref = (a[:, 0::2, 0::2].astype(np.int64) + a[:, 1::2, 0::2] + a[:, 0::2, 1::2]
           + a[:, 1::2, 1::2] + 2) // 4
    ok("E display copy = 2 x 2 block mean (rounded)", p is not None and p.shape == (1, 900, 900)
       and np.array_equal(p, ref))
    v = ImageView()
    v.resize(700, 700)
    v.show()
    pump(0.3)
    v.show_planes([a[0]], key=("ch", 0), autorange=True, preview=[p[0]], preview_f=2)
    pump(0.3)
    v.show_planes([a[0]], key=("ch", 0), preview=[p[0]], preview_f=2)
    pump(0.2)
    shown = v.img.image.shape
    r = v.img.mapRectToParent(v.img.boundingRect())
    ok("E zoomed out: the display copy, covering the whole frame",
       v._showing_preview and shown == (900, 900) and round(r.width()) == 1800, f"{shown} {r}")
    v.vb.setRange(xRange=(800, 1000), yRange=(800, 1000), padding=0)
    pump(0.3)
    ok("E zoomed in: the full frame", not v._showing_preview and v.img.image.shape == (1800, 1800))
    v.close()


# ===================================================================== F
def part_f():
    from peterpiper import users
    from peterpiper.gui import widgets as W
    from peterpiper.config import _settings_file
    # ---- loading bars
    seen = []

    def slow(progress):
        progress(0.5, "half way")
        time.sleep(0.8)
        seen.extend(w for w in QApplication.topLevelWidgets()
                    if isinstance(w, W.BusyPanel) and w.isVisible())
        return 42
    ok("F background work: result returned", W.run_with_progress(None, "Testing", slow) == 42)
    ok("F a loading bar shows for slow work", len(seen) == 1 and
       seen[0].lbl.text() == "half way" and seen[0].bar.value() == 500)
    seen.clear()

    def quick(progress):
        seen.extend(w for w in QApplication.topLevelWidgets()
                    if isinstance(w, W.BusyPanel) and w.isVisible())
        return 7
    ok("F no bar flashes for quick work", W.run_with_progress(None, "Quick", quick) == 7
       and not seen)
    try:
        W.run_with_progress(None, "Failing", lambda p: 1 / 0)
        raised = False
    except ZeroDivisionError:
        raised = True
    ok("F an error in the background reaches the window", raised)
    with W.busy(None, "Steps") as b:
        b.step(1, 4, "one of four")
        vis = b.panel.isVisible() and b.panel.bar.value() == 250
    ok("F step-by-step bar", vis and not b.panel.isVisible())
    # ---- user profiles
    base = users.base_dir()
    s0 = Settings()
    s0.gate_snr = 7.5
    save_settings(s0)                          # data from before profiles
    ok("F no users yet", users.list_users() == [] and users.current() is None)
    ok("F a name is needed", users.name_problem("  ") != "")
    users.add_user("Ana")
    ok("F duplicate names refused", users.name_problem(" ana ") != "")
    users.add_user("Ben")
    ok("F the first user gets the data already here", users.legacy_owner() == "Ana" and
       (base / "users" / "Ana" / "settings.json").exists())
    ok("F later users start empty", not (base / "users" / "Ben" / "settings.json").exists())
    users.activate("Ana")
    ok("F settings live in the user's folder", _settings_file().parent == base / "users" / "Ana"
       and load_settings()[0].gate_snr == 7.5)
    users.activate("Ben")
    ok("F ... and another user has their own", _settings_file().parent == base / "users" / "Ben"
       and load_settings()[0].gate_snr == Settings().gate_snr)
    movie = Path("D:/data/movie1.nd2")
    ok("F results next to the movie per user",
       Path(users.output_dir(movie)) == Path("D:/data/OUTPUT_movie1/Ben"))
    ok("F whose run: by the file, else by its folder",
       users.owner_of(Path("D:/data/OUTPUT_movie1/Ana/PD4nav_sessions/x.npz")) == "Ana"
       and users.owner_of(Path("D:/data/x.npz"), "Ben") == "Ben")
    old = Path("D:/data/OUTPUT_movie1/x.npz")
    ben_sees = users.is_mine(old)
    users.activate("Ana")
    ok("F a run from before profiles: only the first user's", not ben_sees and
       users.is_mine(old))
    ok("F last user remembered", users.last_user() == "Ana")
    # a tracked run made by Ana, in her folder next to the movie
    from peterpiper import history
    from peterpiper.gui.clickwin import ClickWindow
    from peterpiper.gui.comparewin import CompareWindow
    from peterpiper.roifile import read_summary
    ClickWindow._ask_previous_run = lambda self, runs, menu=False: None
    CompareWindow.ASK_UNKNOWN = False
    src = Synth()
    nd2 = OUT / "data" / "movie1.nd2"
    nd2.parent.mkdir(parents=True, exist_ok=True)
    nd2.write_bytes(b"not really an nd2")
    exp = Experiment(nd2_path=str(nd2), out_dir=users.output_dir(nd2),
                     channels=list(src.channels), n_timepoints=3, width=480, height=480,
                     um_per_px=0.5, seconds_per_frame=30.0)
    exp.export_tiffs = False
    Path(exp.out_dir).mkdir(parents=True, exist_ok=True)
    w = ClickWindow(src, exp, Settings(baseline_timepoint=1))
    w.resize(1400, 900)
    w.show()
    t0 = time.time()
    while not w._offered and time.time() - t0 < 30:
        pump(0.1)
    ok("F the window title names the user", "(Ana)" in w.windowTitle())
    w._auto_select()
    pump(0.3)
    while w._busy_now():
        pump(0.05)
    w._place_background(400.0, 440.0)             # you place it (V3.0)
    w.cmb_comp.setCurrentIndex(w.cmb_comp.findData("nucleus"))
    w._track()
    pump(0.3)
    while w._busy_now():
        pump(0.05)
    path = w._save_rois(silent=True)
    pump(0.3)
    sm = read_summary(path) if path else None
    ok("F the saved run records its user, in her folder",
       sm is not None and sm.get("user") == "Ana" and "OUTPUT_movie1" in str(path)
       and Path(str(path)).parent.name == "Ana" and sm["tracked"], str(path))
    w._dirty = False
    w.close()
    pump(0.3)
    mine = history.find_previous_runs(str(nd2), exp.out_dir, (480, 480), 3)
    ok("F Ana's earlier analyses: hers", any(Path(r.path) == Path(path) for r in mine),
       str([r.path for r in mine]))
    cw = CompareWindow()
    ok("F Ana's Compare list has her run", len(cw._paths) >= 1)
    cw.set_checked(list(cw._paths))
    cw.refresh()
    bl = getattr(cw, "_baseline_line", None)
    ok("F Compare graph: dashed baseline line at time 0", bl is not None
       and bl in cw.plot.getPlotItem().items and bl.value() == 0.0
       and bl.pen.style() == Qt.DashLine)
    cw.close()
    users.activate("Ben")
    theirs = history.find_previous_runs(str(nd2), str(nd2.parent / "OUTPUT_movie1" / "Ben"),
                                        (480, 480), 3)
    ok("F Ben does not see Ana's analyses", not theirs, str([r.path for r in theirs]))
    cw = CompareWindow()
    ok("F Ben's Compare list is empty", len(cw._paths) == 0)
    cw.add_run_file(path, quiet=True, check=False)
    lab = cw._labels.get(next(iter(cw._paths), ""), "")
    ok("F Ana's run opened on purpose is marked as hers", lab.endswith("(Ana's)"), lab)
    cw.close()
    # ---- find my runs in a folder (other computers / shared drives)
    users.activate("Ben")
    got = history.find_runs_in_folder(OUT / "data")
    ok("F Find my runs in a folder: Ben finds none, Ana's are not listed",
       not got["mine"] and got["others"] >= 1, str(got))
    users.activate("Ana")
    got = history.find_runs_in_folder(OUT / "data")
    ok("F ... Ana finds hers", any(Path(p) == Path(path) for p in got["mine"]), str(got))
    # ---- rename, remove, don't ask again
    users.rename_user("Ana", "Ana Lopez")
    ok("F rename: same folder, the old name still owns her runs",
       users.current() == "Ana Lopez" and users.home() == base / "users" / "Ana"
       and users.is_mine(path, "Ana") and users.legacy_owner() == "Ana Lopez"
       and Path(users.output_dir(nd2)).name == "Ana")
    ok("F rename: a taken name is refused", users.name_problem("ben", renaming="Ana Lopez") != "")
    users.remove_user("Ben")
    ok("F remove: off the list, nothing deleted",
       users.list_users() == ["Ana Lopez"] and (base / "users" / "Ben").exists()
       and "Ben" in users.all_users())
    ok("F adding a removed name brings the user back",
       users.add_user("ben") == "Ben" and "Ben" in users.list_users()
       and users.legacy_owner() == "Ana Lopez")
    users.activate("Ana Lopez")
    users.set_dont_ask(True)
    ok("F don't ask again: remembered with the last user", users.dont_ask()
       and users.last_user() == "Ana Lopez")
    users.set_dont_ask(False)
    from peterpiper.gui.userdlg import UserDialog
    d = UserDialog()
    ok("F Who is using: Continue is the default button (Enter)", d.btn_go.isDefault()
       and d._picked() == "Ana Lopez")
    d.close()
    users.deactivate()
    # ---- PeterPiper 1.0: PD4nav's profiles are NOT taken over (everyone starts empty)
    import pathlib
    fake = OUT / "fakehome"
    (fake / ".PD4navV2.9" / "users" / "Zoe").mkdir(parents=True)
    (fake / ".PD4navV2.9" / "users.json").write_text(
        json.dumps({"users": ["Zoe"], "legacy_owner": "Zoe", "last": "Zoe"}), encoding="utf-8")
    (fake / ".PD4navV2.9" / "users" / "Zoe" / "settings.json").write_text("{}", encoding="utf-8")
    old_home, old_env = pathlib.Path.home, os.environ.pop("PETERPIPER_HOME")
    pathlib.Path.home = classmethod(lambda cls: fake)
    try:
        moved = users.migrate_old_home()
        newb = users.base_dir()
        (fake / "PD4nav data" / "users" / "Ana").mkdir(parents=True)
        (fake / "PD4nav data" / "users.json").write_text(
            json.dumps({"users": ["Ana"], "legacy_owner": "Ana"}), encoding="utf-8")
        ok("F PeterPiper starts empty: nothing taken from PD4nav (V2.9 or 'PD4nav data'), "
           "which is left as it was",
           not moved and newb == fake / "PeterPiper data" and not (newb / "users.json").exists()
           and users.list_users() == [] and (fake / ".PD4navV2.9" / "users.json").exists()
           and (fake / "PD4nav data" / "users.json").exists())
    finally:
        pathlib.Path.home = old_home
        os.environ["PETERPIPER_HOME"] = old_env
    users.deactivate()


# ===================================================================== G
def part_g():
    from peterpiper import syscheck as SC
    from peterpiper.gui.syscheckdlg import ComputerCheckDialog
    items = SC.run_checks()
    if sys.platform != "win32":                # macOS: no long-path setting to check
        ok("G one check off Windows: Python", [i.key for i in items] == ["python"])
        ok("G Python: a tested version", items[0].status == "ok", items[0].found)
        return
    ok("G two checks: long paths and Python", [i.key for i in items] == ["long_paths", "python"])
    lp, py = items
    real = SC.long_paths_enabled()
    ok("G long-path setting read from Windows", real in (True, False)
       and lp.status == ("ok" if real else "warn"), f"{real} -> {lp.status}")
    ok("G when off: what to do and a command to copy (never run)",
       real or ("LongPathsEnabled" in lp.command and "administrator" in lp.advice))
    ok("G Python: this 64-bit 3.11-3.14 is a tested version", py.status == "ok", py.found)
    ok("G shown at the first start", SC.should_show(items))
    SC.remember(items)
    ok("G not again while nothing changes", not SC.should_show(items))
    changed = [SC.Item(i.key, i.title, "bad" if i.key == "python" else i.status, i.found)
               for i in items]
    ok("G again when a result changes", SC.should_show(changed))
    SC.remember(items, show_on_change=False)
    ok("G never again when switched off", not SC.should_show(changed))
    d = ComputerCheckDialog(None, items)
    d.show()
    pump(0.2)
    from PySide6.QtWidgets import QPushButton
    btns = [b for b in d.findChildren(QPushButton) if b.text() == "Copy command"]
    if btns:
        btns[0].click()
    ok("G Copy command puts it on the clipboard", real or
       QApplication.clipboard().text() == SC.LONG_PATH_COMMAND)
    d.chk_again.setChecked(True)
    d.accept()
    ok("G closing remembers the choice", SC._load_state().get("show_on_change") is True)


# ===================================================================== H
def part_h():
    """The shipped synthetic movie (known answers), lab-only skips, the automatic-
    background flag, portable profiles (export / import / merge / copied folder) and
    moved runs found again."""
    import subprocess
    import synthmovie as SM
    from peterpiper import users, history
    from peterpiper.gui.clickwin import ClickWindow
    from peterpiper.roifile import read_summary
    ClickWindow._ask_previous_run = lambda self, runs, menu=False: None
    users.deactivate()
    # ---- the shipped movie
    z = np.load(SM.FILE)
    ok("H shipped movie = synthmovie.make() (12 x 3 x 192 x 256)",
       z["frames"].shape == (12, 3, 192, 256) and np.array_equal(z["frames"], SM.make()))
    ok("H shipped movie is small", SM.FILE.stat().st_size < 2_000_000,
       f"{SM.FILE.stat().st_size / 1e6:.2f} MB")
    r = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, r'%s'); "
                        "from labdata import need; need('Z:/no/such/movie.nd2', what='x')"
                        % str(HERE)], capture_output=True, text=True)
    ok("H lab-only tests are skipped (exit 0) without the lab's movies",
       r.returncode == 0 and "SKIPPED - lab data only" in r.stdout, r.stdout[:80])
    users.add_user("Cara")
    users.activate("Cara")
    lab = OUT / "lab_pc"
    src, exp = SM.load(lab / "data" / "OUTPUT_synthetic_movie" / "Cara")
    exp.nd2_path = str(lab / "data" / "synthetic_movie.nd2")
    Path(exp.out_dir).mkdir(parents=True, exist_ok=True)
    Path(exp.nd2_path).write_bytes(b"stands in for the movie file (fingerprint)")
    w = ClickWindow(src, exp, Settings(baseline_timepoint=2))
    w.resize(1400, 900)
    w.show()
    t0 = time.time()
    while not w._offered and time.time() - t0 < 30:
        pump(0.1)
    w._goto_step(0, user=True)
    w._auto_select()
    pump(0.3)
    while w._busy_now():
        pump(0.05)
    n = sum(1 for c in w.cells if "nucleus" in c)
    ok("H shipped movie: AUTO-DETECT finds the 16 nuclei", n == 16, str(n))
    from peterpiper.manual import background_from_outline     # the empty strip on the right
    w.background = background_from_outline([(205, 20), (250, 20), (250, 170), (205, 170)],
                                           (src.height, src.width))
    w._bg_auto, w._bg_kind = True, "auto"        # as if placed automatically (Batch)
    pump(0.3)
    w.cmb_comp.setCurrentIndex(w.cmb_comp.findData("nucleus"))
    w._track()
    pump(0.3)
    while w._busy_now():
        pump(0.05)
    pump(0.3)
    M, _i = w._measured("nucleus")
    g, cy = M.channels.index("GFP"), M.channels.index("Cy5")
    ff = M.ff0(g, 1, 5)
    have = [k for k in range(M.n_cells) if np.isfinite(ff[:, k]).any()]
    later = np.nanmean(ff[5:, have], axis=0) if have else np.array([0.0])
    ok("H known answer: 8 sensor cells have GFP F/F0, the 8 untransfected none",
       len(have) == 8, str(len(have)))
    ok("H known answer: GFP F/F0 = 2.0 after timepoint 4 (600 -> 1200 counts)",
       have and np.all(np.abs(later - 2.0) < 0.05), str(np.round(later, 3)))
    rr = M.rr0(g, cy, 1, 5)
    ok("H R/R0 GFP/Cy5: the untransfected cells are left out",
       sum(np.isfinite(rr[:, k]).any() for k in range(M.n_cells)) == 8)
    path = w._save_rois(silent=True)
    pump(0.3)
    w._dirty = False
    w.close()
    pump(0.2)
    # ---- a run with an automatic background is flagged when loaded
    src2, exp2 = SM.load(exp.out_dir)
    exp2.nd2_path = exp.nd2_path
    w2 = ClickWindow(src2, exp2, Settings(baseline_timepoint=2))
    w2.show()
    t0 = time.time()
    while not w2._offered and time.time() - t0 < 30:
        pump(0.1)
    w2._load_roi_file(path)
    pump(0.3)
    ok("H loading a run with an automatic background: 'Check the background'",
       any(t[0] == "Check the background" for t in getattr(w2, "_toasts", []))
       and "placed automatically" in w2.lbl_status.text())
    w2._dirty = False
    w2.close()
    pump(0.2)
    # a template of hers, then her whole profile to a zip
    tpl = users.home() / "Prism style templates"
    tpl.mkdir(parents=True, exist_ok=True)
    (tpl / "my look.prism").write_bytes(b"lab pc look")
    s0, _ = load_settings()
    s0.gate_snr = 6.5
    save_settings(s0)
    zp = users.export_profile("Cara", OUT / "cara_profile.zip")
    import zipfile
    names = zipfile.ZipFile(zp).namelist()
    ok("H Export my profile: one zip with settings, run list, templates, profile.json",
       any(x.endswith("/settings.json") for x in names) and any(
           x.endswith("/run_history.json") for x in names) and any(
           x.endswith("/profile.json") for x in names) and any("my look.prism" in x for x in names),
       str(names[:6]))
    users.deactivate()
    # ---- the laptop: another data folder; her movie folder copied somewhere else, and
    # the lab PC's folder not there (renamed - this test has only one disk)
    gone = OUT / "lab_pc_not_here"
    lab.rename(gone)
    old_home = os.environ["PETERPIPER_HOME"]
    os.environ["PETERPIPER_HOME"] = str(OUT / "laptop_home")
    try:
        name, notes = users.import_profile(zp)
        ok("H Import a profile on another computer: a new user", name == "Cara"
           and "Cara" in users.list_users(), str(notes))
        users.activate("Cara")
        ok("H ... her settings and templates came with it", load_settings()[0].gate_snr == 6.5
           and (users.home() / "Prism style templates" / "my look.prism").read_bytes()
           == b"lab pc look")
        ok("H ... her run is in the list but not on this computer yet",
           len(history.missing_runs()) >= 1 and not history.indexed_runs())
        moved = OUT / "laptop_data" / "copied"
        shutil.copytree(gone / "data", moved / "data")
        got = history.relocate_runs(moved)
        found = history.indexed_runs()
        ok("H My data is in...: found again (same movie, file name, save time)",
           got["found"] >= 1 and got["still_missing"] == 0 and found
           and Path(found[0]["path"]).exists() and str(moved) in found[0]["path"], str(got))
        ok("H ... the new place is remembered", (users.home() / "moved_data.json").exists()
           and history.resolve(path) != path and Path(history.resolve(path)).exists())
        # import again: merged, nothing doubled, nothing overwritten
        (users.home() / "Prism style templates" / "my look.prism").write_bytes(b"laptop look")
        s1, _ = load_settings()
        s1.gate_snr = 9.0
        save_settings(s1)
        name2, notes2 = users.import_profile(zp)
        tl = sorted(x.name for x in (users.home() / "Prism style templates").iterdir())
        ok("H importing again merges: settings here kept, a differing template kept as "
           "'(imported)'", name2 == "Cara" and load_settings()[0].gate_snr == 9.0
           and "my look.prism" in tl and "my look (imported).prism" in tl
           and (users.home() / "Prism style templates" / "my look.prism").read_bytes()
           == b"laptop look", str(notes2) + str(tl))
        idx = json.loads((users.home() / "run_history.json").read_text(encoding="utf-8"))
        n_runs = sum(len(e.get("runs", [])) for e in idx.values())
        ok("H ... the run list is not doubled", n_runs == sum(
            len(e.get("runs", [])) for e in json.loads(zipfile.ZipFile(zp).read(
                next(x for x in names if x.endswith("/run_history.json")))).values()))
        users.deactivate()
        # a profile folder pasted in by hand
        pasted = users.base_dir() / "users" / "Dan"
        pasted.mkdir(parents=True)
        (pasted / "profile.json").write_text(json.dumps({"name": "Dan Lee"}), encoding="utf-8")
        (pasted / "settings.json").write_text("{}", encoding="utf-8")
        ok("H a profile folder copied in by hand is recognised",
           users.adopt_copied_profiles() == ["Dan Lee"] and "Dan Lee" in users.list_users())
        bad = OUT / "bad.zip"
        with zipfile.ZipFile(bad, "w") as zb:
            zb.writestr("../evil.txt", "x")
        try:
            users.import_profile(bad)
            refused = False
        except ValueError:
            refused = True
        ok("H a zip with unsafe paths is refused", refused and not (OUT / "evil.txt").exists())
    finally:
        users.deactivate()
        os.environ["PETERPIPER_HOME"] = old_home
    # missing runs are kept in the list when another run of that movie is recorded
    users.activate("Cara")
    keep = len(history.missing_runs()) + len(history.indexed_runs())
    history.record_run("", path, read_summary(path))
    ok("H runs missing on this computer are kept in the list",
       len(history.missing_runs()) + len(history.indexed_runs()) >= keep)
    users.deactivate()


def main() -> int:
    part_a()
    part_b()
    part_c()
    part_d()
    part_e()
    part_f()
    part_g()
    part_h()
    print(f"\n{N[0]} / {N[0] + len(FAILS)} checks passed")
    for f in FAILS:
        print("  FAILED:", f)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
