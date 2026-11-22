"""
Developer test (not shipped): PeterPiper 4.0 "trackx" - re-tracking single cells
(retrack.py), per-cell overrides (rules / roifile / provenance), the ROI
troubleshooter (trouble.py, gui/troubledlg.py).

    PYTHONIOENCODING=utf-8 MPLBACKEND=Agg QT_QPA_PLATFORM=offscreen \
        python dev_tests/test_v40_trackx.py [--real]

A) plan(): moved / added / removed ROI, a cell's boundary, a rule, an override,
   the background, t0 / settings (full), nothing changed.
B) BIT-IDENTICAL: retrack_cells after a change == a full track_cells with the same
   inputs (every measurement, every ROI at every timepoint, background record,
   params, gate, helper SNR, moves), on a synthetic movie of touching cells, with
   ONLY / AND / WITH / IF / helper rules and boundary lines; changes: ROI moved,
   cell added, compartment removed, cell dropped, rule changed, override added.
C) dropped cell: its columns are empty, as a full track leaves them.
D) background only: remeasure_background == full track; reads only the region.
E) speed: a one-cell re-track reads far fewer pixels than the whole movie.
F) overrides: complete / to_list round trip; ROI file round trip (overrides, moves,
   qualities); a 3.x-style track (no 4.0 parts) still loads and is re-tracked in
   full (identical); the methods text names the cell's own rule.
G) troubleshooter: ideas only on channels that show the cell, no duplicate of
   "now", first ring <= 9 tiles; the problem cell's best idea (GFP) ranks above
   "now"; choice_overrides.
H) the window: opens, tiles appear, fits 1366 x 768, pick + overrides, Try more;
   screenshots in _out/shots/.
--real: the lab movie T("t50"): crop() == frame() slice; first 12 timepoints:
   one-cell re-track and background-only identical to full tracks, timings.
Exit code 0 = every check passed.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
OUT = REPO / "_out" / "v40_trackx"
OUT.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("PETERPIPER_HOME", str(OUT / "home"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")
sys.path.insert(0, str(REPO / "app"))
sys.path.insert(0, str(HERE))

import numpy as np                                                   # noqa: E402

import synth_trackx as S                                             # noqa: E402
from peterpiper import manual as MN                                  # noqa: E402
from peterpiper import provenance as PV                              # noqa: E402
from peterpiper import retrack as RT                                 # noqa: E402
from peterpiper import roifile as RF                                 # noqa: E402
from peterpiper import rules as RL                                   # noqa: E402
from peterpiper import trouble as TB                                 # noqa: E402
from peterpiper.rules import TrackRule                               # noqa: E402
from peterpiper.segment import Roi                                   # noqa: E402

checks = []
REAL = "--real" in sys.argv


def ok(name, cond, extra=""):
    checks.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra else ""), flush=True)


def same_out(a, b):
    """[] when two tracking results are bit-identical, else what differs."""
    bad = []
    if set(a["meas"]) != set(b["meas"]):
        return [f"comps {sorted(a['meas'])} vs {sorted(b['meas'])}"]
    for c in a["meas"]:
        for f in ("mean", "background", "area_px", "n_saturated", "quality", "sum",
                  "background_sum", "background_sd", "background_npx"):
            x, y = getattr(a["meas"][c], f), getattr(b["meas"][c], f)
            if not np.array_equal(np.asarray(x), np.asarray(y), equal_nan=True):
                bad.append(f"{c}.{f}")
        for t in range(len(a["rois"][c])):
            if any(not RT._same(a["rois"][c][t][k], b["rois"][c][t][k])
                   for k in range(len(a["rois"][c][t]))):
                bad.append(f"{c}.rois t{t}")
                break
        for key in ("track_q", "trimmed"):
            if not np.array_equal(a[key][c], b[key][c]):
                bad.append(f"{c}.{key}")
    for key in ("redrawn", "gate", "helper_snr", "rules", "params", "background",
                "overrides", "bg_excluded"):
        if a.get(key) != b.get(key):
            bad.append(key)
    if not np.array_equal(a["shifts"], b["shifts"]):
        bad.append("shifts")
    return bad


def shifted(r, dy, dx, H, W):
    n = r.shifted(dy, dx, (H, W))
    n.channel = getattr(r, "channel", 0)
    if getattr(r, "outline", None) is not None:
        n.outline = Roi(r.bbox, r.outline, r.kind).shifted(dy, dx, (H, W)).mask
    return n


# ==========================================================================
frames, truth = S.make(T=10, H=215, W=262, n_side=5)
T, C, H, W = frames.shape
exp = S.Exp(T, C, H, W)
bg = S.background(H, W)
t0 = 4
cells = S.seeds(frames, truth, t0)
R_ONLY = {"nucleus": TrackRule("nucleus", 0), "cytoplasm": TrackRule("cytoplasm", 1)}
SET = dict(max_move_um=3.0, mito_k=3.0, size_tol=0.25, overlap_k=3.0, sat_level=65535)


def snap(cl, rules, b=bg, t=t0, bounds=None, ov=None, settings=SET):
    return RT.snapshot(cl, rules, b, t, exp.channels, settings, bounds, ov, n_timepoints=T)


# ---------------------------------------------------------------- A plan()
print("--- A plan()")
base = snap(cells, R_ONLY)
c_mv = [dict(c) for c in cells]
c_mv[7]["cytoplasm"] = shifted(cells[7]["cytoplasm"], 1, 0, H, W)
p = RT.plan(base, snap(c_mv, R_ONLY))
ok("A1 moved cytoplasm of cell 8 -> that ROI only", p["retrack"] == {"cytoplasm": [7]}
   and not p["full"], p["retrack"])
c_n = [dict(c) for c in cells]
c_n[3]["nucleus"] = shifted(cells[3]["nucleus"], 2, 0, H, W)
p = RT.plan(base, snap(c_n, R_ONLY))
ok("A2 moved nucleus (the cell's 'Follow' ROI) -> all of cell 4",
   p["retrack"] == {"nucleus": [3], "cytoplasm": [3]}, p["retrack"])
c_add = [dict(c) for c in cells] + [{"nucleus": shifted(cells[0]["nucleus"], 0, 0, H, W)}]
p = RT.plan(base, snap(c_add, R_ONLY))
ok("A3 new cell -> its ROIs", p["retrack"] == {"nucleus": [25]}, p["retrack"])
c_rm = [dict(c) for c in cells]
c_rm[12].pop("cytoplasm")
p = RT.plan(base, snap(c_rm, R_ONLY))
ok("A4 removed cytoplasm -> drop_pairs, nothing re-tracked directly",
   p["drop_pairs"] == {"cytoplasm": [12]} and p["retrack"] == {} and p["drop"] == [],
   (p["drop_pairs"], p["retrack"]))
c_dr = [dict(c) for c in cells]
c_dr[3] = {}
p = RT.plan(base, snap(c_dr, R_ONLY))
ok("A5 cell emptied -> drop [3] (numbers stay)", p["drop"] == [3]
   and p["drop_pairs"] == {"nucleus": [3], "cytoplasm": [3]}, p)
R_W = {"nucleus": TrackRule("nucleus", 0), "cytoplasm": TrackRule("cytoplasm", 1, "with", 0)}
p = RT.plan(base, snap(cells, R_W))
ok("A6 cytoplasm rule changed -> cytoplasm of every cell, not the nucleus",
   p["retrack"] == {"cytoplasm": list(range(25))}, p["retrack"])
p = RT.plan(base, snap(cells, R_ONLY, bounds={6: [[(60.0, 50.0), (60.0, 120.0)]]}))
ok("A7 boundary of cell 7 -> all of cell 7", p["retrack"] == {"nucleus": [6], "cytoplasm": [6]},
   p["retrack"])
p = RT.plan(base, snap(cells, R_ONLY, ov={("nucleus", 4): {"rule": TrackRule("nucleus", 1)}}))
ok("A8 override for cell 5's nucleus -> all of cell 5 (its moves are measured on it)",
   p["retrack"] == {"nucleus": [4], "cytoplasm": [4]}, p["retrack"])
bg2 = Roi((bg.bbox[0] + 5, bg.bbox[1], bg.bbox[2], bg.bbox[3]),
          np.ones((bg.bbox[2] - bg.bbox[0] - 5, bg.bbox[3] - bg.bbox[1]), bool), "background")
p = RT.plan(base, snap(cells, R_ONLY, b=bg2))
ok("A9 background moved -> background only", p["background"] and not p["retrack"]
   and not p["full"])
ok("A10 t0 changed -> full", RT.plan(base, snap(cells, R_ONLY, t=5))["full"])
ok("A11 a tracking setting changed -> full",
   RT.plan(base, snap(cells, R_ONLY, settings=dict(SET, size_tol=0.4)))["full"])
ok("A12 nothing changed -> nothing to do", RT.nothing_to_do(RT.plan(base, snap(cells, R_ONLY))))
ok("A13 gate_snr alone -> regate only", RT.plan(base, snap(cells, R_ONLY,
                                                          settings=dict(SET, gate_snr=8)))
   ["regate"] and RT.nothing_to_do(RT.plan(base, snap(cells, R_ONLY,
                                                      settings=dict(SET, gate_snr=8)))))
ok("A14 no earlier result -> full", RT.plan(None, base)["full"])

# ---------------------------------------------------------------- B identical
print("--- B re-track == full track (bit for bit)")
R_AND = {"nucleus": TrackRule("nucleus", 0, "and", 1), "cytoplasm": TrackRule("cytoplasm", 1)}
R_HW = {"nucleus": TrackRule("nucleus", 0, "help", -1, (2,)),
        "cytoplasm": TrackRule("cytoplasm", 1, "with", 0)}
R_IF = {"nucleus": TrackRule("nucleus", 0, "if", 1), "cytoplasm": TrackRule("cytoplasm", 1,
                                                                             "and", 0)}
BND = {6: [[(60.0, 50.0), (60.0, 120.0)]], 18: [[(150.0, 140.0), (200.0, 150.0)]]}
timing = {}


def case(name, rules, cl_old, cl_new, rules_new=None, b_old=None, b_new=None, ov_old=None,
         ov_new=None, kw=None):
    rules_new = rules if rules_new is None else rules_new
    kw = dict(kw or {})
    prev = MN.track_cells(S.Src(frames), exp, cl_old, bg, t0, rules=rules, boundaries=b_old,
                          overrides=ov_old, **kw)
    pl = RT.plan(snap(cl_old, rules, bounds=b_old, ov=ov_old),
                 snap(cl_new, rules_new, bounds=b_new, ov=ov_new))
    ts = time.time()
    ref = MN.track_cells(S.Src(frames), exp, cl_new, bg, t0, rules=rules_new, boundaries=b_new,
                         overrides=ov_new, **kw)
    t_full = time.time() - ts
    src = S.Src(frames)
    ts = time.time()
    out = RT.retrack_cells(src, exp, cl_new, bg, t0, prev, pl["retrack"], rules=rules_new,
                           boundaries=b_new, overrides=ov_new, **kw)
    t_re = time.time() - ts
    diff = same_out(ref, out)
    ok(f"B {name}: identical", not diff, f"{diff[:4]}; re-tracked {len(out['retrack']['pairs'])} "
                                        f"ROI(s) in {out['retrack']['passes']} pass(es)")
    timing[name] = (round(t_full, 2), round(t_re, 2), src.px_read, frames.size)
    return prev, ref, out, pl


case("ONLY, nucleus moved (corner)", R_ONLY, cells,
     [dict(c, nucleus=shifted(c["nucleus"], 2, 1, H, W)) if k == 0 else dict(c)
      for k, c in enumerate(cells)])
case("ONLY, cytoplasm moved (middle)", R_ONLY, cells, c_mv)
case("AND, cell added", R_AND, cells, c_add)
case("helper + WITH, nucleus moved", R_HW, cells, c_n)
case("IF + AND, cytoplasm removed", R_IF, cells, c_rm)
_p, ref_dr, out_dr, _pl = case("ONLY + boundaries, cell dropped", R_ONLY, cells, c_dr,
                               b_old=BND, b_new=BND)
case("rule changed (cytoplasm -> WITH)", R_ONLY, cells, cells, rules_new=R_W)
case("rule changed (nucleus -> AND)", R_ONLY, cells, cells, rules_new=R_AND)
case("boundary added", R_ONLY, cells, cells, b_new=BND)
case("override: cell 5 nucleus on GFP", R_ONLY, cells, cells,
     ov_new={("nucleus", 4): {"rule": TrackRule("nucleus", 1)}})
case("override: helper + own size / move limits", R_IF, cells, cells,
     ov_new={("nucleus", 7): {"rule": TrackRule("nucleus", 0, "help", -1, (1,)),
                              "settings": {"size_tol": 0.15, "max_move_um": 5.0}}})
case("override removed again", R_ONLY, cells, cells,
     ov_old={("nucleus", 4): {"rule": TrackRule("nucleus", 1)}})
case("no rules (V2.2), nucleus moved", None, cells, c_n)

# ---------------------------------------------------------------- C dropped
print("--- C dropped cell")
ok("C1 dropped cell's columns empty (NaN, area 0, outline blank)",
   all(np.isnan(out_dr["meas"][c].mean[:, :, 3]).all() and not out_dr["meas"][c].area_px[:, 3].any()
       and all(not out_dr["rois"][c][t][3].include for t in range(T)) for c in out_dr["meas"]))

# ---------------------------------------------------------------- D background
print("--- D background only")
prev = MN.track_cells(S.Src(frames), exp, cells, bg, t0, rules=R_ONLY)
ref_b = MN.track_cells(S.Src(frames), exp, cells, bg2, t0, rules=R_ONLY)
srcb = S.Src(frames)
out_b = RT.remeasure_background(srcb, exp, prev, bg2)
d = same_out(ref_b, out_b)
ok("D1 background re-measured == full track", not d, d)
ok("D2 only the region's box was read", srcb.px_read == T * C * bg2.mask.size,
   f"{srcb.px_read} px")
out_b2 = RT.retrack_cells(S.Src(frames), exp, c_mv, bg2, t0, prev,
                          RT.plan(snap(cells, R_ONLY), snap(c_mv, R_ONLY, b=bg2))["retrack"],
                          rules=R_ONLY, background_changed=True)
ref_b2 = MN.track_cells(S.Src(frames), exp, c_mv, bg2, t0, rules=R_ONLY)
d = same_out(ref_b2, out_b2)
ok("D3 ROI moved AND background moved, in one go == full track", not d, d)

u = RT.update(S.Src(frames), exp, c_mv, bg2, t0, prev, snap(cells, R_ONLY), snap(c_mv, R_ONLY, b=bg2),
              rules=R_ONLY)
ok("D4 update(): ROI + background in one call == full track", not same_out(ref_b2, u)
   and u["retrack"]["plan"]["background"])
u0 = RT.update(S.Src(frames), exp, cells, bg, t0, prev, snap(cells, R_ONLY), snap(cells, R_ONLY),
               rules=R_ONLY)
ok("D5 update(): nothing changed -> the same result, nothing read", u0["meas"] is prev["meas"])

# ---------------------------------------------------------------- E speed
print("--- E speed (pixels read)")
fr2, tr2 = S.make(T=10, H=330, W=400, n_side=8)
T2, C2, H2, W2 = fr2.shape
exp2 = S.Exp(T2, C2, H2, W2)
cells2 = S.seeds(fr2, tr2, 4, comps=("nucleus",))
bgr = S.background(H2, W2)
prev2 = MN.track_cells(S.Src(fr2), exp2, cells2, bgr, 4, rules={"nucleus": TrackRule("nucleus", 0)})
cl = [dict(c) for c in cells2]
cl[0]["nucleus"] = shifted(cells2[0]["nucleus"], 1, 1, H2, W2)
s2 = S.Src(fr2)
ts = time.time()
o2 = RT.retrack_cells(s2, exp2, cl, bgr, 4, prev2, {"nucleus": [0]},
                      rules={"nucleus": TrackRule("nucleus", 0)})
t_re = time.time() - ts
ts = time.time()
r2 = MN.track_cells(S.Src(fr2), exp2, cl, bgr, 4, rules={"nucleus": TrackRule("nucleus", 0)})
t_full = time.time() - ts
ok("E1 one corner cell of 64: identical", not same_out(r2, o2))
ok("E2 ... and reads < 15 % of the movie's pixels", s2.px_read < 0.15 * fr2.size,
   f"{s2.px_read / fr2.size:.1%}; {len(o2['retrack']['pairs'])} ROI(s); full {t_full:.2f} s, "
   f"re-track {t_re:.2f} s")
timing["64 cells, one corner cell"] = (round(t_full, 2), round(t_re, 2), s2.px_read, fr2.size)

# ---------------------------------------------------------------- F overrides / files
print("--- F overrides, files, methods")
ov = {("nucleus", 4): {"rule": TrackRule("nucleus", 1), "settings": {"size_tol": 0.15},
                       "why": ""}}
lst = RL.overrides_to_list(ov, exp.channels)
back = RL.complete_overrides(lst, exp.channels)
ok("F1 overrides list round trip", lst == [{"comp": "nucleus", "cell": 5, "rule":
                                           {"comp": "nucleus", "a": "GFP", "mode": "only", "b": ""},
                                           "settings": {"size_tol": 0.15}, "why": ""}]
   and back[("nucleus", 4)]["rule"] == TrackRule("nucleus", 1), lst)
ok("F2 a rule naming a missing channel is dropped (never changed)",
   RL.complete_overrides([{"comp": "nucleus", "cell": 1, "rule": {"a": "mCherry"}}],
                         exp.channels) == {})
st = {"v2": True, "overrides": RF.overrides_state(ov, exp.channels)}
ok("F3 session state round trip", RF.overrides_from_state(st, exp.channels, 25)[("nucleus", 4)]
   ["settings"] == {"size_tol": 0.15})
ok("F4 a state without overrides (files before 4.0) -> {}",
   RF.overrides_from_state({"v2": True}, exp.channels) == {})
trk = MN.track_cells(S.Src(frames), exp, cells, bg, t0, rules=R_ONLY, overrides=ov)
blob = RF.pack_track(trk)
fn = OUT / "trk.npz"
np.savez(fn, **blob)
loaded = RF.load_roi_track(fn, exp.channels)
ok("F5 ROI file keeps the overrides and the 4.0 re-track parts",
   loaded.get("overrides") == trk["overrides"] and np.array_equal(loaded["shifts"], trk["shifts"])
   and all(np.array_equal(loaded["track_q"][c], trk["track_q"][c])
           and np.array_equal(loaded["trimmed"][c], trk["trimmed"][c]) for c in trk["rois"]))
ok("F6 a re-track from the loaded file == full track",
   not same_out(MN.track_cells(S.Src(frames), exp, c_mv, bg, t0, rules=R_ONLY, overrides=ov),
                RT.retrack_cells(S.Src(frames), exp, c_mv, bg, t0, loaded, {"cytoplasm": [7]},
                                 rules=R_ONLY, overrides=ov)))
old = {k: v for k, v in blob.items() if k != "trk_shifts" and not k.endswith("_tq")
       and not k.endswith("_trim")}
np.savez(OUT / "old.npz", **old)
lo = RF.load_roi_track(OUT / "old.npz", exp.channels)
ok("F7 a file without the 4.0 parts loads (as before)", lo is not None and "shifts" not in lo
   and set(lo["rois"]) == set(trk["rois"]))
o7 = RT.retrack_cells(S.Src(frames), exp, c_mv, bg, t0, lo, {"cytoplasm": [7]}, rules=R_ONLY,
                      overrides=ov)
ok("F8 ... and the next change is tracked in full (same numbers)", o7["retrack"]["full"]
   and not same_out(MN.track_cells(S.Src(frames), exp, c_mv, bg, t0, rules=R_ONLY,
                                   overrides=ov), o7))
from peterpiper.config import Settings                             # noqa: E402
meth = PV.methods_text(Settings(), exp, trk["params"], rules_text=[r for r in trk["rules"]],
                       comps=list(trk["rois"]))
ok("F9 methods text names the cell's own rule",
   "Cell 5 nucleus: followed on GFP ONLY; size within 15% of the drawn size (chosen in the ROI "
   "troubleshooter)" in meth, meth[meth.find("Single cells"):][:220])
rows = PV.parameter_table(Settings(), exp, trk["params"], rules_text=trk["rules"])
ok("F10 parameter table has a row for it", any("Cell 5 nucleus" in str(r) for r in rows))
ok("F11 a full track without overrides has no 'overrides' (old output unchanged)",
   "overrides" not in prev and "overrides" not in prev["params"])

# ---------------------------------------------------------------- G troubleshooter
print("--- G troubleshooter engine")
fr3, tr3 = S.make(T=12)
T3, C3, H3, W3 = fr3.shape
exp3 = S.Exp(T3, C3, H3, W3)
bg3 = S.background(H3, W3)
cells3 = S.seeds(fr3, tr3, 4)
k = S.PROBLEM
src3 = S.Src(fr3)
prev3 = MN.track_cells(src3, exp3, cells3, bg3, 4, rules=R_ONLY)
snr = TB.channel_snr(fr3[4], cells3[k]["nucleus"], exp3.um_per_px)
cands = TB.alternatives(k, "nucleus", R_ONLY["nucleus"], exp3, cells3, fr3[4],
                        {"size_tol": 0.25, "max_move_um": 3.0})
first = [c for c in cands if c.ring <= 1]
ok("G1 Cy5 does not show the problem cell, GFP does", snr[0] < 5 <= snr[1],
   [round(v, 1) for v in snr])
ok("G2 no idea follows it on Cy5 (only channels with signal)",
   all(c.rule is None or c.rule.a != 0 for c in cands if not c.current))
ok("G3 'now' first, at most 9 tiles in the first ring, a 'Try more' ring",
   cands[0].current and len(first) <= 9 and any(c.ring == 2 for c in cands), len(first))
keys = [c.key(exp3.channels) for c in cands[1:]]
now_key = TB.Candidate("", R_ONLY["nucleus"]).key(exp3.channels)
ok("G4 no duplicates, none equal to 'now'", len(keys) == len(set(keys)) and now_key not in keys)
labels = [c.label for c in first]
ok("G5 plain labels ('GFP only', '... helping', size / move limits)",
   "GFP only" in labels and any("helping" in s for s in labels)
   and any("size" in s or "moves" in s for s in [c.label for c in cands]), labels)
ts = time.time()
got, order = [], []
for r in TB.run_candidates(src3, exp3, cells3, bg3, 4, prev3, k, "nucleus", first,
                           dict(rules=R_ONLY)):
    got.append(r)
    order.append(r.candidate.label)
t_tb = time.time() - ts
best = TB.ranked(got)[0]
now = next(r for r in got if r.candidate.current)
ok("G6 every idea ran ('now' first, as they finish)", len(got) == len(first)
   and got[0].candidate.current and not any(r.error for r in got), f"{t_tb:.2f} s")
ok("G7 the best idea is not 'now' and scores higher", not best.candidate.current
   and best.score > now.score + 5, f"best {best.candidate.label} {best.score:.0f} ({best.grade}) "
                                   f"vs now {now.score:.0f} ({now.grade}): {now.reasons}")
ok("G8 the best idea uses GFP", best.candidate.rule is not None and best.candidate.rule.a == 1,
   best.candidate.label)
ok("G9 reasons in plain words", any("redrawn" in s for s in best.reasons) and best.grade == "good")
gfp = next(r for r in got if r.candidate.label == "GFP only")
ov3 = TB.choice_overrides({}, k, "nucleus", gfp.candidate)
o3 = RT.retrack_cells(S.Src(fr3), exp3, cells3, bg3, 4, prev3,
                      RT.plan(RT.snapshot(cells3, R_ONLY, bg3, 4, exp3.channels),
                              RT.snapshot(cells3, R_ONLY, bg3, 4, exp3.channels,
                                          overrides=ov3))["retrack"],
                      rules=R_ONLY, overrides=ov3)
f3 = MN.track_cells(S.Src(fr3), exp3, cells3, bg3, 4, rules=R_ONLY, overrides=ov3)
ok("G10 the chosen idea, spliced in by retrack_cells == full track with the override",
   not same_out(f3, o3))
ok("G11 ... and the preview's ROIs of that cell are the same as the final ones",
   all(RT._same(gfp.rois[t], f3["rois"]["nucleus"][t][k]) for t in range(T3)))
ok("G12 choice 'now' leaves the overrides unchanged",
   TB.choice_overrides({}, k, "nucleus", cands[0]) == {})

# ---------------------------------------------------------------- H window
print("--- H the window")
try:
    from PySide6.QtWidgets import QApplication
    from peterpiper.gui import theme as TH
    from peterpiper.gui.troubledlg import TroubleDialog
    app = QApplication.instance() or QApplication(sys.argv)
    TH.apply(app)
    shots = REPO / "_out" / "shots"
    shots.mkdir(parents=True, exist_ok=True)
    dlg = TroubleDialog(src3, exp3, cells3, bg3, 4, prev3, k, "nucleus", dict(rules=R_ONLY))
    dlg.show()
    dlg.wait(120)
    ok("H1 tiles appear ('now' + 8 ideas, first ring first)", len(dlg.tiles) == 9 and
       dlg.tiles[0].res.candidate.current and
       {t.res.candidate.label for t in dlg.tiles} >= {c.label for c in first}, len(dlg.tiles))
    sz = dlg.size()
    ok("H2 fits 1366 x 768 (no scroll bars)", sz.width() <= 1366 and sz.height() <= 728,
       f"{sz.width()} x {sz.height()}")
    tile = next(t for t in dlg.tiles if t.res.candidate.label == "GFP only")
    dlg.pick(tile)
    dlg.slider.setValue(7)
    app.processEvents()
    ok("H3 pick -> 'Use this for cell 5' on, overrides as chosen",
       dlg.btn_use.isEnabled() and "for cell 5" in dlg.btn_use.text()
       and dlg.new_overrides()[("nucleus", k)]["rule"] == TrackRule("nucleus", 1))
    dlg.grab().save(str(shots / "trackx_troubleshooter_test.png"))
    dlg._more()
    dlg.wait(120)
    ok("H4 Try more options -> the next ideas on page 2",
       dlg.page == 1 and len(dlg.tiles) > 1 and not any(t.res.candidate.ring == 1
                                                         for t in dlg.tiles
                                                         if not t.res.candidate.current))
    dlg.grab().save(str(shots / "trackx_troubleshooter_more.png"))
    dlg._use()
    ok("H5 Use this -> accepted with the chosen idea", dlg.result() == 1
       and dlg.chosen.label == "GFP only" and dlg.chosen_result is not None)
    dlg2 = TroubleDialog(src3, exp3, cells3, bg3, 4, prev3, k, "nucleus", dict(rules=R_ONLY))
    dlg2.wait(120)
    dlg2.reject()
    ok("H6 Quit keeps the tracking (nothing chosen)", dlg2.chosen is None
       and dlg2.new_overrides() == {})
except Exception as exc:                                            # noqa: BLE001
    import traceback
    traceback.print_exc()
    ok("H window ran without an error", False, repr(exc))

# ---------------------------------------------------------------- real movie
if REAL:
    print("--- real movie (t50, first 12 timepoints)")
    from labdata import T as LT, missing
    path = LT("t50")
    if missing(path):
        print("SKIPPED - lab data only: t50")
    else:
        from peterpiper.nd2io import ND2Source, describe
        src = ND2Source(path)
        full = np.asarray(src.frame(7))
        ok("R1 crop() == frame() slice", np.array_equal(src.crop(7, 1000, 1170, 900, 1111),
                                                        full[:, 1000:1170, 900:1111]))
        ex = describe(src, "")
        ex.n_timepoints = 12
        um = ex.um_per_px
        f0 = np.asarray(src.frame(3))
        ys, xs = slice(700, 1700), slice(700, 1700)
        nuc = [r for r in MN.auto_select(f0[2], "nucleus", um, None)]
        for r in nuc:
            r.channel = 2
        cl = [{"nucleus": r} for r in nuc]
        bgl, _m = MN.auto_background([f0], um, avoid=nuc)
        rl = {"nucleus": TrackRule("nucleus", 2)}
        ts = time.time()
        pv = MN.track_cells(src, ex, cl, bgl, 3, rules=rl)
        tf = time.time() - ts
        kk = int(np.argmin([np.hypot(r.centroid[0] - 1200, r.centroid[1] - 1200) for r in nuc]))
        cl2 = [dict(c) for c in cl]
        cl2[kk]["nucleus"] = shifted(cl[kk]["nucleus"], 2, 1, ex.height, ex.width)
        ts = time.time()
        orl = RT.retrack_cells(src, ex, cl2, bgl, 3, pv, {"nucleus": [kk]}, rules=rl)
        tr = time.time() - ts
        rf = MN.track_cells(src, ex, cl2, bgl, 3, rules=rl)
        ok("R2 one cell re-tracked == full track (lab movie)", not same_out(rf, orl),
           f"{len(nuc)} cells; full {tf:.1f} s, re-track {tr:.1f} s, "
           f"{orl['retrack']['px_read'] / (ex.n_channels * ex.height * ex.width * 12):.2%} "
           f"of the pixels read")
        y0, x0, y1, x1 = bgl.bbox
        bgm = Roi((y0 + 30, x0, y1, x1), np.ones((y1 - y0 - 30, x1 - x0), bool), "background")
        ts = time.time()
        ob = RT.remeasure_background(src, ex, rf, bgm)
        tb = time.time() - ts
        ok("R3 background only == full track (lab movie)",
           not same_out(MN.track_cells(src, ex, cl2, bgm, 3, rules=rl), ob), f"{tb:.1f} s")
        src.close()

print("--- timings (full track s, re-track s, pixels read by the re-track, movie pixels)")
for k_, v in timing.items():
    print(f"    {k_}: {v}")
n_ok = sum(1 for _n, c in checks if c)
print(f"{n_ok} / {len(checks)} checks passed")
sys.exit(0 if n_ok == len(checks) else 1)
