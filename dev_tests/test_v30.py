"""
Developer test (not shipped): V3.0 helper channels and trained auto-detect.

    MPLBACKEND=Agg QT_QPA_PLATFORM=offscreen python dev_tests/test_v30.py

A) the rule model: 'Auto-detect nucleus using GFP, helped by Cy5' saved by channel
   NAMES (other channel order, a missing helper refused, a helper equal to the main
   channel ignored); the older ONLY / WITH / AND / IF rules unchanged (same dict,
   same wording, shown in V3.0 words as 'kept exactly').
B) the helper image is exactly main + 0.5 x each helper (each scaled to its own
   background / bright level, frozen at the drawn timepoint), in the main
   channel's counts; the 1 um guard: a helper-followed outline never reaches
   more than 1 um beyond the main channel's own outline (a built movie whose
   helper blob is twice as wide), on every timepoint.
C) tracking with a helper rule on the shipped synthetic movie: the same outlines
   and numbers as the plain rule there (round nuclei in both channels), helper
   weight and guard recorded, the helper's signal at the drawn timepoint
   separates transfected (sensor) from untransfected cells.
D) the main window: rule rows (main + '+ helper channel'), AUTO-DETECT with GFP as
   helper picks exactly the 8 sensor cells, a cell you click without helper signal
   is kept with a note, an older rule loads with its note and is applied exactly,
   editing it makes it a V3.0 rule; the helper-signal setting is shown.
E) trained auto-detect (peterpiper.detectors) on known answers: candidates, the rule
   learned, the held-out score, a limit that makes no difference stays off, quiz
   answers (keep / skip / not sure) and the score's 'your cells', the quiz never
   asks twice, saving / listing / fitting channels / refusing to overwrite,
   detect() avoids cells already there.
F) the training window and the AUTO-DETECT button: learn, scoreboard, picture,
   quiz, save; the button sets the rule (full preset) and picks the 8; the
   detector is kept in the ROI file, restored on loading, and named with its
   rule and score in the methods text, with the helper-rule sentence.
G) frame reading while you scrub: after dragging across 60 frames that are not
   in memory, the frame you stopped on is read first (not after every frame
   passed over), frames far behind are skipped, and closing waits for a read in
   progress (closing the .nd2 under a reader crashed the app).
H) the baseline-drift workbook of a 4-channel run (32 quantities, columns past Z):
   written, one slope column per quantity, each slope = the least-squares line.
I) uneven gaps between timepoints (from every frame's time stamp): found on known
   stamps (20% of the median), in words, in the Methods and the Settings sheet with
   the recorded total; even spacing gives the same Methods text as before; the time
   axis is unchanged (even); lab data: the start window warns on the movie whose
   first frame came 3 h 17 min early, and not on an even one.
L) lab data only: trained on the lab's own hand-analysed biosensor runs (8 movies;
   each scored by a rule learned from the other 7) it beats plain AUTO-DETECT.
"""
from __future__ import annotations

import labdata  # noqa: E402  (lab file names: dev_tests/lab_paths.json, never uploaded)

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
OUT = REPO / "_out" / "v30"
if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True)
os.environ["PETERPIPER_HOME"] = str(OUT / "home")
os.environ.setdefault("MPLCONFIGDIR", str(OUT / "home" / "mpl"))

from PySide6.QtWidgets import QApplication, QMessageBox             # noqa: E402

app = QApplication(sys.argv)
BOXES = []
for _n in ("information", "warning", "critical"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: (BOXES.append(a[1:3]),
                                                           QMessageBox.Ok)[1]))
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)

import synthmovie as SM                                             # noqa: E402
from peterpiper import detectors as DT                                  # noqa: E402
from peterpiper import manual as MN                                     # noqa: E402
from peterpiper import rules as R                                       # noqa: E402
from peterpiper.config import Experiment, Settings                      # noqa: E402
from peterpiper.manual import background_from_outline                   # noqa: E402
from peterpiper.nd2io import ImageSource                                # noqa: E402
from peterpiper.segment import Roi                                      # noqa: E402

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


def wait(w):
    pump(0.2)
    while w._busy_now():
        app.processEvents()
        time.sleep(0.02)
    pump(0.2)


def disc(H, W, cy, cx, r):
    yy, xx = np.mgrid[:H, :W]
    return (yy - cy) ** 2 + (xx - cx) ** 2 <= r * r


def full(r, H, W):
    m = np.zeros((H, W), bool)
    y0, x0, y1, x1 = r.bbox
    m[y0:y1, x0:x1] = r.mask
    return m


SRC, EXP = SM.load(OUT / "synth")
ST = np.asarray(SRC.frame(2))
UM = EXP.um_per_px
NAMES = list(EXP.channels)                  # Cy5, GFP, mCherry
HELP_RULE = R.TrackRule("nucleus", 0, R.HELP, -1, (1,))


def sensor_cells(rois):
    """The cells with GFP (the synthetic sensor cells), by their GFP signal."""
    return [r for r in rois if R.helper_snr(ST, r, HELP_RULE, UM)[1] > 20]


# ===================================================================== A
def part_a():
    r = R.TrackRule("nucleus", 1, R.HELP, -1, (0,))
    d = r.to_dict(["Cy5", "GFP"])
    ok("A helper rule saved by names", d == {"comp": "nucleus", "a": "GFP", "mode": "help",
                                             "b": "", "helpers": ["Cy5"]}, str(d))
    back = R.TrackRule.from_dict(d, ["GFP", "mCherry", "Cy5"])
    ok("A read back with another channel order", back is not None and back.a == 0
       and back.helper_list() == [2] and back.effective_mode() == "help", str(back))
    ok("A a missing helper channel refuses the rule (never changed silently)",
       R.TrackRule.from_dict(d, ["GFP", "mCherry"]) is None)
    same = R.TrackRule("nucleus", 1, R.HELP, -1, (1,))
    ok("A a helper equal to the main channel does not count (= plain rule)",
       same.effective_mode() == "only" and same.helper_list() == [])
    ok("A wording: methods and window",
       r.text(["Cy5", "GFP"]) == "Track nucleus using GFP, helped by Cy5"
       and r.display_text(["Cy5", "GFP"]) == "Auto-detect nucleus using GFP, helped by Cy5",
       r.text(["Cy5", "GFP"]))
    old = R.TrackRule("nucleus", 0, "with", 1)
    ok("A older rules: the same dict and wording as before",
       old.to_dict(["Cy5", "GFP"]) == {"comp": "nucleus", "a": "Cy5", "mode": "with", "b": "GFP"}
       and old.text(["Cy5", "GFP"]) == "Track nucleus using Cy5 WITH intensity in GFP")
    ok("A older rules in V3.0 words, 'kept exactly'",
       "kept exactly" in old.display_text(["Cy5", "GFP"])
       and "GFP trims the outline" in old.display_text(["Cy5", "GFP"]))
    cr = R.complete_rules({"nucleus": r}, [], ["nucleus"], ["Cy5", "GFP"])
    ok("A complete_rules keeps the helpers", cr["nucleus"].helper_list() == [0]
       and cr["nucleus"].effective_mode() == "help")


# ===================================================================== B
class Built(ImageSource):
    """6 frames: main channel a small disc (r 6 px), helper a disc twice as wide
    (r 12 px) around it, both drifting 1 px per frame; noise SD 5."""

    def __init__(self):
        self.channels = ["main", "helper"]
        self.n_timepoints, self.height, self.width = 6, 96, 96
        rng = np.random.default_rng(7)
        self.frames = []
        for t in range(6):
            cy, cx = 48 + t, 40 + t
            a = 200 + 800 * disc(96, 96, cy, cx, 6)
            b = 200 + 800 * disc(96, 96, cy, cx, 12)
            st = np.stack([a, b]).astype(np.float32) + rng.normal(0, 5, (2, 96, 96))
            self.frames.append(np.clip(st, 0, 65535).astype(np.uint16))

    def frame(self, t):
        return self.frames[int(t)]


def part_b():
    st = ST.astype(np.float32)
    norm = R.make_norm(ST)
    g = R.guide_plane(ST, HELP_RULE, norm)
    za = (st[0] - norm.bg[0]) / (norm.top[0] - norm.bg[0])
    zb = (st[1] - norm.bg[1]) / (norm.top[1] - norm.bg[1])
    ref = norm.bg[0] + (norm.top[0] - norm.bg[0]) * (za + 0.5 * zb) / 1.5
    ok("B helper image = main + 0.5 x helper (each scaled), in main counts",
       float(np.max(np.abs(g - ref))) < 0.05, f"max diff {float(np.max(np.abs(g - ref))):.4f}")
    two = R.TrackRule("nucleus", 0, R.HELP, -1, (1, 2))
    g2 = R.guide_plane(ST, two, norm)
    zc = (st[2] - norm.bg[2]) / (norm.top[2] - norm.bg[2])
    ref2 = norm.bg[0] + (norm.top[0] - norm.bg[0]) * (za + 0.5 * zb + 0.5 * zc) / 2.0
    ok("B two helpers: each 0.5, divided by the total weight 2",
       float(np.max(np.abs(g2 - ref2))) < 0.05)
    # the guard on its own
    big = Roi((10, 10, 50, 50), disc(40, 40, 20, 20, 15))
    small = Roi((20, 20, 40, 40), disc(20, 20, 10, 10, 5))
    out = R.help_guard(big, small, 0.5)
    grown = MN_dilate(full(small, 64, 64), 2)
    ok("B guard: the outline is cut to within 1 um (2 px) of the main outline",
       not (full(out, 64, 64) & ~grown).any() and (full(out, 64, 64) & full(small, 64, 64)).sum()
       == full(small, 64, 64).sum())
    # tracked: every frame
    src = Built()
    exp = Experiment(nd2_path=str(OUT / "built.nd2"), out_dir=str(OUT / "built"),
                     channels=["main", "helper"], n_timepoints=6, width=96, height=96,
                     um_per_px=0.5, seconds_per_frame=10.0)
    first = src.frame(0)
    nuc = MN.draw_at("nucleus", first[0], 48, 40, 0.5, Settings(), [])
    bg = background_from_outline([(70, 70), (94, 70), (94, 94), (70, 94)], (96, 96))
    plain = MN.track_cells(src, exp, [{"nucleus": nuc}], bg, 0, rules={"nucleus": R.TrackRule("nucleus", 0)})
    helped = MN.track_cells(src, exp, [{"nucleus": nuc}], bg, 0,
                            rules={"nucleus": R.TrackRule("nucleus", 0, R.HELP, -1, (1,))})
    inside = []
    for t in range(6):
        a = full(plain["rois"]["nucleus"][t][0], 96, 96)
        b = full(helped["rois"]["nucleus"][t][0], 96, 96)
        inside.append(not (b & ~MN_dilate(a, 2)).any())
    ok("B tracked with a helper twice as wide: every frame's outline within 1 um of "
       "the main channel's own outline", all(inside), str(inside))
    ok("B ... and the helper rule is recorded", helped["params"].get("help_weight") == 0.5
       and helped["params"].get("help_guard_um") == 1.0
       and helped["rules"][0]["helpers"] == ["helper"])


def MN_dilate(m, px):
    from scipy import ndimage as ndi
    return ndi.binary_dilation(m, structure=ndi.generate_binary_structure(2, 1), iterations=px)


# ===================================================================== C
def part_c():
    nuc = MN.auto_select(ST[0], "nucleus", UM, None)
    cells = [{"nucleus": r} for r in nuc]
    bg = background_from_outline([(205, 20), (250, 20), (250, 170), (205, 170)], (192, 256))
    a = MN.track_cells(SRC, EXP, cells, bg, 2, rules={"nucleus": R.TrackRule("nucleus", 0)})
    b = MN.track_cells(SRC, EXP, cells, bg, 2, rules={"nucleus": HELP_RULE})
    A, B = a["meas"]["nucleus"], b["meas"]["nucleus"]
    ok("C synthetic movie: 16 nuclei tracked with the helper rule", B.mean.shape == (12, 3, 16))
    ok("C ... the same outlines and numbers as the plain rule (round nuclei in both)",
       np.array_equal(A.area_px, B.area_px) and np.allclose(A.mean, B.mean, equal_nan=True))
    hs = b.get("helper_snr", {}).get("nucleus", {})
    gfp = [hs[k]["GFP"] for k in sorted(hs)]
    sens = {id(r) for r in sensor_cells(nuc)}
    lo = [v for k, v in zip(sorted(hs), gfp) if id(nuc[k]) not in sens]
    hi = [v for k, v in zip(sorted(hs), gfp) if id(nuc[k]) in sens]
    ok("C helper signal at the drawn timepoint: sensor cells > 50 x noise, others < 5",
       len(hi) == 8 and len(lo) == 8 and min(hi) > 50 and max(lo) < 5,
       f"sensor min {min(hi):.0f}, others max {max(lo):.1f}")


# ===================================================================== D
def make_window():
    from peterpiper.gui.clickwin import ClickWindow
    ClickWindow._ask_previous_run = lambda self, runs, **k: None
    src, exp = SM.load(OUT / "win")
    Path(exp.out_dir).mkdir(parents=True, exist_ok=True)
    w = ClickWindow(src, exp, Settings(baseline_timepoint=2))
    w._paths_ok = lambda *a, **k: True
    w.resize(1500, 950)
    w.show()
    pump(0.5)
    return w


def part_d():
    w = make_window()
    row = w._rows[0]
    row["a"].setCurrentIndex(0)
    ok("D a rule row: Auto-detect [Nucleus] using [Cy5], no helpers yet",
       w.rules["nucleus"].effective_mode() == "only" and not row["helpers"])
    w._add_helper(row, 1)
    pump(0.1)
    ok("D '+ helper channel' -> helped by GFP",
       w.rules["nucleus"].effective_mode() == "help" and w.rules["nucleus"].helper_list() == [1])
    ok("D the step 2 line says what the ROIs are drawn and followed on",
       "Cy5 helped by GFP" in w.lbl_seen.text(), w.lbl_seen.text())
    ok("D the helper-signal setting is shown", w._track_form.isRowVisible(w.sp_gate)
       if hasattr(w._track_form, "isRowVisible") else True)
    ok("D settings remember the helper rule", w.settings.track_rules[0].get("helpers") == ["GFP"])
    w._auto_select()
    wait(w)
    picked = [c["nucleus"] for c in w.cells]
    ok("D AUTO-DETECT with GFP as helper: exactly the 8 sensor cells",
       len(picked) == 8 and len(sensor_cells(picked)) == 8, str(len(picked)))
    # a click on an untransfected cell: kept, with a note
    allc = MN.auto_select(ST[0], "nucleus", UM, None)
    plain = [r for r in allc if r not in sensor_cells(allc)]
    cy, cx = (int(v) for v in plain[0].centroid)
    n0 = len(w.cells)
    w._set_tool("add")
    w._on_point(float(cx), float(cy), False)
    pump(0.3)
    note = w._gate_note(len(w.cells) - 1, "nucleus") if len(w.cells) > n0 else ""
    ok("D a clicked cell without helper signal is kept, with a note",
       len(w.cells) == n0 + 1 and "kept, because you picked it" in note, note[:80])
    w._set_tool(None)
    # an older rule
    w._set_rules([R.TrackRule("nucleus", 0, "if", 1)], quiet=True)
    pump(0.1)
    r = w.rules["nucleus"]
    ok("D an older IF rule loads and is applied exactly",
       r.mode == "if" and r.b == 1 and w._rows[0]["legacy"] is not None)
    ok("D ... with its note", "cells need GFP signal" in w._rows[0]["lbl_legacy"].text()
       and not w._rows[0]["lbl_legacy"].isHidden())
    w._rows[0]["a"].setCurrentIndex(2)
    pump(0.1)
    r = w.rules["nucleus"]
    ok("D editing it makes it a V3.0 rule (main mCherry helped by GFP)",
       r.effective_mode() == "help" and r.a == 2 and r.helper_list() == [1]
       and w._rows[0]["legacy"] is None)
    w._dirty = False
    w.close()


# ===================================================================== E
def movies_known():
    allc = MN.auto_select(ST[0], "nucleus", UM, None)
    yours = sensor_cells(allc)
    return [DT.movie_from_frame(ST, NAMES, UM, yours, "Cy5", ["GFP"], name=f"synthetic {k}")
            for k in (1, 2)], yours


def part_e():
    mv, yours = movies_known()
    m = mv[0]
    ok("E candidates: every nucleus of the movie, each of yours matched once",
       len(m.rois) >= 16 and int(m.yours.sum()) == 8 and m.n_yours == 8,
       f"{len(m.rois)} candidates, {int(m.yours.sum())} matched")
    ok("E features: area, circularity, signal-to-noise and relative brightness per channel",
       all(k in m.feat for k in ("area", "circ", "snr_Cy5", "rel_Cy5", "snr_GFP", "rel_GFP")))
    ch = ["Cy5", "GFP"]
    L = DT.fit(mv, ch)
    keep = DT.select(m.feat, L, ch)
    ok("E the rule learned picks exactly your 8", int((keep & m.yours).sum()) == 8
       and int((keep & ~m.yours).sum()) == 0, str(L))
    ok("E a limit that makes no difference stays off (Cy5 is bright in every nucleus)",
       L["snr"]["Cy5"] == 0.0 and L["rel"]["Cy5"] == 0.0, str(L))
    ok("E ... and the deciding limit sits inside the working range, not at its edge",
       L["snr"]["GFP"] > 3 or L["rel"]["GFP"] > 0.1, str(L))
    ho = DT.held_out(mv, ch)
    ok("E held-out score: each movie scored by the rule from the other",
       len(ho) == 2 and all(h["f1"] == 1.0 for h in ho), str(ho))
    det = DT.Detector(name="Nuclear Cy5 plus GFP (test)", main="Cy5", helpers=["GFP"],
                      limits=L, held_out=ho, trained_on=[DT.score(x, DT.select(x.feat, L, ch))
                                                         for x in mv])
    ok("E the rule in plain words", "GFP: at least" in det.rule_text()
       and "Cy5: any" in det.rule_text(), det.rule_text())
    ok("E the score in plain words", "16 of your 16 cells found, 0 extra" in det.score_text(),
       det.score_text())
    # quiz answers
    mv2, _ = movies_known()
    q = DT.uncertain(mv2, L, ch, 6)
    ok("E quiz: up to 6 blobs nearest the limits, none twice", 0 < len(q) <= 6
       and len(set(q)) == len(q))
    m2 = mv2[0]
    ys = [i for i in range(len(m2.rois)) if m2.yours[i]]
    ns = [i for i in range(len(m2.rois)) if not m2.yours[i]]
    pt = lambda i: dict(zip(("y", "x"), (int(v) for v in m2.rois[i].centroid)))  # noqa: E731
    ans = [dict(movie=m2.name, answer="skip", **pt(ys[0])),
           dict(movie=m2.name, answer="keep", **pt(ns[0])),
           dict(movie=m2.name, answer="unsure", **pt(ns[1]))]
    DT.apply_quiz(mv2, ans)
    sc = DT.score(m2, np.ones(len(m2.rois), bool))
    ok("E quiz answers: skip -> not yours, keep -> yours, not sure -> left out",
       not m2.yours[ys[0]] and m2.yours[ns[0]] and not m2.use[ns[1]])
    ok("E ... 'your cells' = 8 - 1 skipped + 1 kept", sc["yours"] == 8, str(sc))
    asked = DT.uncertain(mv2, L, ch, 40, ans)
    ok("E the quiz never asks about an answered blob again",
       not any((mv2[mi].name, tuple(int(v) for v in mv2[mi].rois[ci].centroid)) in
               {(a["movie"], (a["y"], a["x"])) for a in ans} for mi, ci in asked))
    # saving
    p = DT.save(det)
    ok("E saved into the profile's Auto-detect folder", p.exists() and p.parent.name == "Auto-detect")
    try:
        DT.save(det)
        refused = False
    except FileExistsError:
        refused = True
    ok("E a second detector with the same name is not overwritten without asking", refused)
    ok("E listed for movies with its channels only",
       [d.name for d in DT.listing(NAMES)] == [det.name] and DT.listing(["GFP", "mCherry"]) == [])
    got = DT.detect(ST, NAMES, DT.listing(NAMES)[0], UM)
    ok("E detect(): the 8 sensor cells", len(got) == 8 and len(sensor_cells(got)) == 8)
    got2 = DT.detect(ST, NAMES, det, UM, taken=got[:3])
    ok("E detect() leaves out cells already there", len(got2) == 5)


# ===================================================================== F
def part_f():
    from peterpiper import provenance as PV, roifile
    from peterpiper.gui.traindlg import TrainDialog
    for p in DT.folder().glob("*.json"):
        p.unlink()
    w = make_window()
    d = TrainDialog(w, NAMES, "Cy5", ["GFP"])
    ok("F the training window starts with your main channel and helpers",
       d.main() == "Cy5" and d.helpers() == ["GFP"] and d.chans() == ["Cy5", "GFP"])
    mv, _ = movies_known()
    d.movies = mv
    d.held = DT.held_out(mv, d.chans())
    d.limits = DT.fit(mv, d.chans())
    d._show_results()
    pump(0.2)
    ok("F scoreboard: one row per movie, the honest score",
       d.tbl_score.rowCount() == 2 and d.tbl_score.item(0, 5).text() == "1.00"
       and "16 of your 16" in d.lbl_score.text())
    pix = d.movie_picture(0)
    ok("F the picture is drawn", not pix.isNull() and pix.width() > 100)
    d.start_quiz()
    n = len(d.quiz)
    for _ in range(n):
        mi, ci = d.quiz[d.qi]
        d.answer("keep" if d.movies[mi].yours[ci] else "skip")
    pump(0.2)
    ok("F quiz answered -> learned again, answers kept", n > 0 and len(d.answers) == n
       and d.btn_quiz.isEnabled() and "learning again" in d.lbl_q.text())
    path = d.save("Autodetect - Nuclear Cy5 plus GFP (sensor test)")
    ok("F saved with your name", path is not None and path.exists())
    det = DT.listing(NAMES)[0]
    ok("F ... with the training record (movies, held-out, quiz)",
       len(det.trained_on) == 2 and len(det.held_out) == 2 and len(det.quiz) == n)
    w._fill_detectors()
    pump(0.1)
    ok("F a button under AUTO-DETECT", w._det_lay.count() == 1 and w.det_box.isVisibleTo(w))
    ok("F ... that never widens the panel", w._det_lay.itemAt(0).widget().sizePolicy()
       .horizontalPolicy().name == "Ignored")
    w._use_detector(det)
    wait(w)
    r = w.rules["nucleus"]
    ok("F the button sets the rule (full preset): Cy5 helped by GFP",
       r.a == 0 and r.helper_list() == [1])
    picked = [c["nucleus"] for c in w.cells]
    ok("F ... and picks the 8 sensor cells", len(picked) == 8 and len(sensor_cells(picked)) == 8)
    shown = w.lbl_status.text().replace(chr(8203), "")
    ok("F ... and says it in words (its name and learned rule)",
       det.name in shown and "GFP: at least" in shown, shown[:120])
    w.background = background_from_outline([(205, 20), (250, 20), (250, 170), (205, 170)],
                                           (192, 256))
    w._bg_auto, w._bg_kind = False, "hand"
    path = w._save_rois(silent=True)
    st, _c = roifile.load_roi_state(path)
    ok("F the ROI file records the detector used", (st.get("detector") or {}).get("name") == det.name)
    w._detector_used = None
    w._load_roi_file(path)
    pump(0.3)
    ok("F ... restored when the file is loaded", w._detector_used is not None
       and w._detector_used.name == det.name)
    prov = w._provenance(["nucleus"]) if hasattr(w, "_provenance") else None
    if prov is None:
        import inspect
        fn = [m for m in dir(w) if "prov" in m.lower()]
        prov = {}
        for m in fn:
            f = getattr(w, m)
            if callable(f) and not inspect.signature(f).parameters:
                try:
                    v = f()
                    if isinstance(v, dict) and "rules" in v:
                        prov = v
                except Exception:                                  # noqa: BLE001
                    pass
    text = PV.methods_text(w.settings, w.exp, None, None, ["nucleus"], provenance=prov)
    ok("F methods: the trained auto-detect named with its rule and score",
       det.name in text and "On movies it had not seen" in text)
    ok("F methods: the helper-rule sentence (weight 0.5, guard 1 um)",
       "helper image" in text and "0.5 × each helper channel" in text and "1 µm" in text)
    w._dirty = False
    w.close()


# ===================================================================== G
def part_g():
    import threading
    from peterpiper.gui.frames import FrameStore

    class Slow:
        """0.05 s per frame; records the order frames are read and whether a read
        was still running when the file was closed."""
        def __init__(self):
            self.order, self.closed, self.busy, self.bad = [], False, 0, False
            self.lock = threading.Lock()

        def frame(self, t):
            with self.lock:
                self.busy += 1
            time.sleep(0.05)
            with self.lock:
                self.order.append(int(t))
                self.busy -= 1
                if self.closed:
                    self.bad = True
            return np.full((1, 8, 8), t, np.uint16)

    src = Slow()
    fs = FrameStore(src, 100, 128)
    for t in range(0, 61):                         # a quick drag from 1 to 61
        fs.get(t)
    t0 = time.time()
    while fs.get_preview(60) is None and 60 not in src.order and time.time() - t0 < 10:
        time.sleep(0.01)
    took = time.time() - t0
    pos = src.order.index(60) if 60 in src.order else 99
    ok("G scrubbing: the frame you stopped on is among the first 3 read",
       pos <= 2, f"position {pos}, order {src.order[:8]}")
    time.sleep(0.6)
    far = [t for t in src.order if t < 60 - 4]
    ok("G ... frames passed over far behind it are skipped",
       len(far) <= 2, f"read {far}")
    ok("G ... and the frame arrives in about one read time", took < 0.5, f"{took:.2f} s")
    for t in range(61, 75):
        fs.request(t)
    time.sleep(0.07)
    fs.close()
    src.closed = True
    time.sleep(0.2)
    ok("G closing waits for a read in progress (nothing read after the file closes)",
       not src.bad and src.busy == 0)
    fs2 = FrameStore(Slow(), 5, 128)
    a = fs2.get_now(3)
    ok("G a frame read on demand is kept", fs2.get(3) is a)
    fs2.close()


# ===================================================================== H
def part_h():
    from openpyxl import load_workbook
    from peterpiper import export as EX
    from peterpiper.measure import Measurements
    T, C, N = 20, 4, 3
    t = np.arange(T, dtype=float)
    mean = np.empty((T, C, N))
    for c in range(C):
        for k in range(N):
            mean[:, c, k] = 1000.0 * (c + 1) + 50.0 * k + (2.0 + c + k) * t
    M = Measurements(mean=mean, background=np.full((T, C), 100.0), area_px=np.full((T, N), 400.0),
                     n_saturated=np.zeros((T, C, N)), quality=np.ones((T, N)),
                     channels=["DAPI", "GFP", "Cy5", "mCherry"],
                     background_sd=np.full((T, C), 5.0))
    s = Settings(baseline_timepoint=1)
    s.write_ratio_sheets = True
    from peterpiper.plots import _panels
    qs = [p[0] for p in _panels(M, s)]
    exp = Experiment(nd2_path="m.nd2", out_dir=str(OUT), channels=M.channels, n_timepoints=T,
                     height=8, width=8, um_per_px=1.0, seconds_per_frame=60.0)
    path = OUT / "h_drift.xlsx"
    try:
        used = EX._drift_workbook(path, exp, M, s, list(range(N)), {0: 1, 1: 1, 2: 0}, qs, 1, 10, t)
        err = ""
    except Exception as exc:                                   # noqa: BLE001
        used, err = None, repr(exc)
    ok("H 4-channel run: the drift workbook is written (32 quantities, columns to AH)",
       used is not None and len(qs) == 32, err or f"{len(qs)} quantities")
    if used is None:
        return
    ws = load_workbook(used).active
    head = [c.value for c in ws[3]]
    ok("H ... one slope column per quantity", len(head) == 2 + 32 and head[-1].endswith("(per min)"),
       str(len(head)))
    col = 2 + qs.index("BgSub_GFP")            # GFP (channel 1), cell 2 (k = 1): slope 2 + 1 + 1
    ok("H ... a slope = its least-squares line (GFP, cell 2: 4.0 per min)",
       abs(ws.cell(row=5, column=col + 1).value - 4.0) < 1e-9, str(ws.cell(row=5, column=col + 1).value))
    ok("H ... wide columns past Z too", ws.column_dimensions["AH"].width == 28)


# ===================================================================== I
def part_i():
    from peterpiper import provenance as PV
    from peterpiper.config import duration_text, uneven_gaps
    ts = np.r_[0.0, 11840.31 + np.cumsum(np.r_[0.0, [32.0] * 6, 41.0, [32.0] * 4])]
    g = uneven_gaps(ts)
    ok("I gaps 20% off the median found (1 -> 2: 11840 s; 8 -> 9: 41 s), not the 32 s ones",
       g == [(1, 11840.31), (8, 41.0)], str(g))
    ok("I none on even stamps, none for 2 stamps",
       uneven_gaps(np.arange(10) * 30.0) == [] and uneven_gaps([0.0, 5.0]) == [])
    ok("I durations in words", (duration_text(54.5), duration_text(250), duration_text(11840.31))
       == ("54.5 s", "4 min 10 s", "3 h 17 min"))
    e = Experiment(nd2_path="null.nd2", channels=["GFP", "Cy5"], n_timepoints=13,
                   seconds_per_frame=32.0, frame_gaps=g, span_s=float(ts[-1] - ts[0]))
    ok("I in words", e.gaps_text() == "timepoints 1 \u2192 2: 3 h 17 min; 8 \u2192 9: 41 s",
       e.gaps_text())
    s = Settings(baseline_timepoint=2)
    m = PV.methods_text(s, e)
    ok("I Methods: the recorded total and the uneven spacing, times approximate",
       f"{(ts[-1] - ts[0]) / 60:.4g} min in total" in m and "The spacing was uneven (timepoints 1"
       in m and "times next to these gaps are approximate" in m)
    rows = {r[1]: r[2] for r in PV.parameter_table(s, e)}
    ok("I Settings sheet: total from the stamps, the gaps listed",
       rows.get("Total duration (min)") == round((ts[-1] - ts[0]) / 60, 2)
       and "3 h 17 min" in str(rows.get("Uneven gaps")))
    x, _lab = e.time_axis(13, 1)
    ok("I the time axis stays even (32 s steps)", np.allclose(np.diff(x), 32.0 / 60))
    e2 = Experiment(nd2_path="even.nd2", channels=["GFP", "Cy5"], n_timepoints=13,
                    seconds_per_frame=30.0)
    e3 = Experiment(nd2_path="even.nd2", channels=["GFP", "Cy5"], n_timepoints=13,
                    seconds_per_frame=30.0, span_s=360.0)
    ok("I even spacing: the Methods text as before (no gap sentence)",
       PV.methods_text(s, e2) == PV.methods_text(s, e3) and "uneven" not in PV.methods_text(s, e2)
       and "Uneven gaps" not in {r[1] for r in PV.parameter_table(s, e2)})
    null = Path(labdata.T("t22"))
    even = Path(labdata.T("t23"))
    if not (null.exists() and even.exists()):
        print("     (I start window: lab movies not here - skipped)")
        return
    from peterpiper.gui.setup import SetupDialog
    d = SetupDialog()
    d.show()
    d._load(str(null))
    pump(0.3)
    txt = d.lbl_gaps.text()
    ok("I start window: the null movie's 3 h 17 min first gap is warned about, 261 min total",
       d.lbl_gaps.isVisible() and "1 \u2192 2: 3 h 17 min" in txt and "261 min total"
       in d.lbl_info.text(), txt[:90])
    d.grab().save(str(OUT / "i_start_window_gap.png"))
    d._load(str(even))
    pump(0.3)
    ok("I ... an even movie's one 54.5 s gap (treatment) is shown too, 60 min total",
       "10 \u2192 11: 54.5 s" in d.lbl_gaps.text() and "60 min total" in d.lbl_info.text())
    if d.source is not None:
        d.source.close()
        d.source = None
    d.close()


# ===================================================================== L
LAB = [
    (labdata.T("t24"),
     labdata.T("t25")),
    (labdata.T("t26"),
     labdata.T("t27")),
    (labdata.T("t28"),
     labdata.T("t29")),
    (labdata.T("t30"),
     labdata.T("t31")),
    (labdata.T("t32"),
     labdata.T("t33")),
    (labdata.T("t34"),
     labdata.T("t35")),
    (labdata.T("t36"),
     labdata.T("t37")),
    (labdata.T("t38"),
     labdata.T("t39")),
]


def part_l():
    from labdata import missing
    gone = missing(*[p for pair in LAB for p in pair])
    if gone:
        print(f"SKIPPED - lab data only: part L needs {len(gone)} lab files")
        return
    from peterpiper.nd2io import open_source
    mv, plain_f1 = [], []
    for run, nd2 in LAB:
        m = DT.load_movie(run, nd2, "GFP", ["Cy5"])
        mv.append(m)
        src = open_source(nd2)
        ch = list(src.channels)
        picks = MN.auto_select(m.frame[ch.index("GFP")], "nucleus", m.um, None)
        right = sum(1 for h in m.hand if any(DT._iou(h, p) >= DT.MATCH_IOU for p in picks))
        plain_f1.append(2 * right / max(1, len(picks) + len(m.hand)))
        m.frame = None
    ho = DT.held_out(mv, ["GFP", "Cy5"])
    f1 = float(np.mean([h["f1"] for h in ho]))
    extra = sum(h["extra"] for h in ho)
    right = sum(h["right"] for h in ho)
    yours = sum(h["yours"] for h in ho)
    print(f"     trained (each movie unseen): F1 {f1:.2f}, {right} of {yours} found, {extra} extra;"
          f" plain AUTO-DETECT F1 {np.mean(plain_f1):.2f}")
    ok("L 8 lab movies read, your cells matched by the candidates",
       len(mv) == 8 and sum(int(m.yours.sum()) for m in mv) >= 0.95 * sum(m.n_yours for m in mv))
    ok("L trained on your runs it beats plain AUTO-DETECT on movies it had not seen",
       f1 > float(np.mean(plain_f1)) + 0.1, f"{f1:.2f} vs {np.mean(plain_f1):.2f}")
    ok("L ... at about two in three of your picks (mean F1 >= 0.6)", f1 >= 0.6, f"{f1:.2f}")


def main():
    for part in (part_a, part_b, part_c, part_d, part_e, part_f, part_g, part_h, part_i,
                 part_l):
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
