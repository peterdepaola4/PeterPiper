"""
Developer test (not shipped): tracking rules on REAL .nd2 data.

    PETERPIPER_HOME=<scratch>/_home MPLBACKEND=Agg python dev_tests/test_rules_track.py [--parts abcde]

  a  BIT-IDENTICAL: nuclei on Cy5 (u2os file, 12 timepoints, drawn at t0 = 0 and
     again at t0 = 5): V2.2's track_cells == rules=None == ONLY rule, every
     Measurements array and every per-frame ROI (bbox, mask, outline, channel)
  b  WITH: whole cells, mCherry WITH GFP (HeLa mRuby file, 10 timepoints)
  c  AND: mitochondria, GFP AND ExRai (MEF mito file, 10 timepoints): every
     measured mask is a subset of the ONLY run's at the same frame
  d  IF: nuclei on Cy5 IF GFP + one ROI over an empty area -> low SNR + QC reason
     d2 AND: the same nuclei, Cy5 AND GFP: pixels dark in GFP dropped; the empty-area
        ROI keeps no pixel -> NaN, quality 0.3; QC runs on it
  e  speed: ONLY vs V2.2 (same frames, preloaded so the disk does not count)

The V2.2 tracker is taken from git (commit --v22, default 8e31298 = V2.2 code)
into $PETERPIPER_HOME/v22_<rev>/roinav_v22. Test data are read-only (D:\\).
Exit code 0 = every check passed.
"""
from __future__ import annotations

import labdata  # noqa: E402  (lab file names: dev_tests/lab_paths.json, never uploaded)

import argparse
import copy
import importlib
import io
import os
import subprocess
import sys
import tarfile
import tempfile
import time
import warnings
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "app"))

from peterpiper import manual as MN                               # noqa: E402
from peterpiper import qc as QC                                   # noqa: E402
from peterpiper import rules as RL                                # noqa: E402
from peterpiper.config import Settings                            # noqa: E402
from peterpiper.nd2io import describe, open_source                # noqa: E402

NUC = labdata.T("t02")
RUBY = labdata.T("t08")
MITO = labdata.T("t20")
from labdata import need                                    # noqa: E402
need(NUC, RUBY, MITO, what="test_rules_track.py")   # V3.0: lab data only

checks = []
timings = {}


def ok(name, cond, extra=""):
    checks.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra else ""), flush=True)


def note(msg):
    print("     " + msg, flush=True)


class Cached:
    """The first n frames, read once (so timings measure the tracker, not the disk)."""

    def __init__(self, src, n):
        self.frames = [np.asarray(src.frame(t)) for t in range(n)]

    def frame(self, t):
        return self.frames[int(np.clip(t, 0, len(self.frames) - 1))]


def load_v22(rev):
    """V2.2's manual.py (from git) as package roinav_v22, for the bit-identity test."""
    dest = Path(os.environ.get("PETERPIPER_HOME") or tempfile.gettempdir()) / f"v22_{rev}"
    pkg = dest / "roinav_v22"
    if not (pkg / "manual.py").exists():
        import pd4nav_history                       # PD4nav's history (PeterPiper's earlier name)
        for rel, data in pd4nav_history.package_files(rev).items():
            out = pkg / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
    if str(dest) not in sys.path:
        sys.path.insert(0, str(dest))
    return importlib.import_module("roinav_v22.manual")


def _eq(a, b):
    a, b = np.asarray(a), np.asarray(b)
    return a.shape == b.shape and np.array_equal(a, b, equal_nan=a.dtype.kind == "f")


def diff_tracks(o1, o2):
    """Every difference between two track_cells results (empty list = identical).
    V2.5: against the V2.2 tracker (its results have no "background" record) the
    background is not compared - V2.5 measures it differently on purpose (cells
    included, per-timepoint exclusions); everything else must be identical."""
    probs = []
    if set(o1["meas"]) != set(o2["meas"]) or set(o1["rois"]) != set(o2["rois"]):
        return ["different compartments"]
    both_v25 = "background" in o1 and "background" in o2
    for c in o1["meas"]:
        M1, M2 = o1["meas"][c], o2["meas"][c]
        for f in ("mean", "background", "area_px", "n_saturated", "quality", "background_sd"):
            if f in ("background", "background_sd") and not both_v25:
                continue
            if not _eq(getattr(M1, f), getattr(M2, f)):
                probs.append(f"{c}.{f}")
        if M1.channels != M2.channels or M1.roi_mode != M2.roi_mode:
            probs.append(f"{c} channels/mode")
        for t, (row1, row2) in enumerate(zip(o1["rois"][c], o2["rois"][c])):
            for k, (r1, r2) in enumerate(zip(row1, row2)):
                o_1, o_2 = getattr(r1, "outline", None), getattr(r2, "outline", None)
                if (tuple(map(int, r1.bbox)) != tuple(map(int, r2.bbox)) or not _eq(r1.mask, r2.mask)
                        or (o_1 is None) != (o_2 is None) or (o_1 is not None and not _eq(o_1, o_2))
                        or getattr(r1, "channel", None) != getattr(r2, "channel", None)
                        or r1.include != r2.include):
                    probs.append(f"{c} roi t{t} cell{k}")
        if o1["redrawn"][c] != o2["redrawn"][c]:
            probs.append(f"{c} redrawn")
    return probs


def v22_agrees(o22, oN, comp, seeds, tol, t0):
    """
    V2.5 vs V2.2 (ONLY / no rules): V2.5 adds HARD size limits (V2.2 allowed a
    5 % re-fit slack) and gives up pixels another cell holds where a redraw fell
    back to the moved outline - so the two may differ from the first frame where
    V2.2's region left (1 -/+ tol) x the drawn area (first frame: the first-frame
    tolerance), in tracking order. Before it they must be identical: every ROI
    (bbox, mask, outline, channel) and every measurement except the background
    (measured differently on purpose). Returns (problems, first such frame or None).
    """
    T = len(o22["rois"][comp])
    order = list(range(t0, T)) + list(range(t0 - 1, -1, -1))
    first = None
    for i, t in enumerate(order):
        tl = min(MN.FIRST_FRAME_TOL, tol) if t == t0 else tol
        for k, r in enumerate(o22["rois"][comp][t]):
            lo, hi = MN.size_limits(MN._region(seeds[k]).area, tl)
            if not lo <= MN._region(r).area <= hi:
                first = i
                break
        if first is not None:
            break
    frames = order[:first] if first is not None else order
    probs = []
    M1, M2 = o22["meas"][comp], oN["meas"][comp]
    for t in frames:
        for f in ("mean", "area_px", "n_saturated", "quality"):
            if not _eq(getattr(M1, f)[t], getattr(M2, f)[t]):
                probs.append(f"{f} t{t}")
        for k, (r1, r2) in enumerate(zip(o22["rois"][comp][t], oN["rois"][comp][t])):
            o_1, o_2 = getattr(r1, "outline", None), getattr(r2, "outline", None)
            if (tuple(map(int, r1.bbox)) != tuple(map(int, r2.bbox)) or not _eq(r1.mask, r2.mask)
                    or (o_1 is None) != (o_2 is None) or (o_1 is not None and not _eq(o_1, o_2))
                    or getattr(r1, "channel", None) != getattr(r2, "channel", None)):
                probs.append(f"roi t{t} cell{k}")
    return probs, (order[first] if first is not None else None)


def sub_exp(src, n):
    e = describe(src)
    e.n_timepoints = min(n, e.n_timepoints)
    return e


def peaks_draw(comp, plane, um, s, n, ch, nuclei=()):
    """Up to n non-overlapping ROIs drawn at the brightest peaks (as clicks would)."""
    H, W = plane.shape
    edge = int(MN._px(2.0, um))
    out = []
    for (y, x) in MN._peaks(plane, um, 4.0, 12.0, 8.0)[:300]:
        if any(r.bbox[0] <= y < r.bbox[2] and r.bbox[1] <= x < r.bbox[3]
               and MN._shape(r)[y - r.bbox[0], x - r.bbox[1]] for r in out):
            continue
        r = MN.draw_at(comp, plane, y, x, um, s, nuclei)
        if r is None:
            continue
        y0, x0, y1, x1 = r.bbox
        a = MN._shape(r).sum() * um * um
        if not (60.0 <= a <= 8000.0) or y0 <= edge or x0 <= edge or y1 >= H - edge or x1 >= W - edge:
            continue
        r2, frac = MN.cut_overlaps(r, out)
        if r2 is None or frac < 0.7:
            continue
        r2.kind, r2.source, r2.channel = comp, "manual", ch
        out.append(r2)
        if len(out) >= n:
            break
    return out


def timed(fn, *a, **kw):
    t = time.perf_counter()
    out = fn(*a, **kw)
    return out, time.perf_counter() - t


def area_guard_ok(out, comp, seeds, tol):
    """Every tracked region inside the size guard's widest possible range
    (re-fit slack included) around the size drawn."""
    lo_f = MN.REFIT_ACCEPT[0] * (1 - tol)
    hi_f = MN.REFIT_ACCEPT[1] * (1 + tol)
    worst = (1.0, 1.0)
    bad = []
    for t, row in enumerate(out["rois"][comp]):
        for k, r in enumerate(row):
            ref = MN._region(seeds[k]).area
            a = MN._region(r).area
            f = a / ref
            worst = (min(worst[0], f), max(worst[1], f))
            if not (lo_f - 1e-9 <= f <= hi_f + 1e-9):
                bad.append((t, k, round(f, 3)))
    return bad, worst


# ==========================================================================
def part_a_d_e(v22, parts):
    print("\n=== a / d / e: nuclei, u2os file (Cy5 / GFP / ExRai) ===", flush=True)
    src = open_source(NUC)
    T = 12
    exp = sub_exp(src, T)
    cy5, gfp = exp.channels.index("Cy5"), exp.channels.index("GFP")
    um = exp.um_per_px
    t = time.perf_counter()
    cs = Cached(src, T)
    note(f"read {T} frames in {time.perf_counter() - t:.1f} s; {exp.width}x{exp.height}, {um} um/px")
    s = Settings()
    bg, msg = MN.auto_background([cs.frame(0), cs.frame(T // 2), cs.frame(T - 1)], um)
    ok("background region found", bg is not None, msg)

    def cluster(t0):
        nuc, dt = timed(MN.auto_select, cs.frame(t0)[cy5], "nucleus", um, s)
        cen = np.array([r.centroid for r in nuc])
        c0 = int(np.argmin(((cen - [exp.height / 2, exp.width / 2]) ** 2).sum(1)))
        pick = np.argsort(((cen - cen[c0]) ** 2).sum(1))[:6]   # 6 neighbouring nuclei
        out = []
        for i in pick:
            r = nuc[int(i)]
            r.channel, r.source, r.kind = cy5, "manual", "nucleus"
            out.append(r)
        note(f"auto-detected {len(nuc)} nuclei on Cy5 at t={t0} in {dt:.1f} s; tracking 6 neighbours "
             f"({', '.join(f'{r.area * um * um:.0f}' for r in out)} um2)")
        return out

    def run(fn, seeds, t0, **kw):
        cells = [{"nucleus": copy.deepcopy(r)} for r in seeds]
        return timed(fn, cs, exp, cells, bg, t0, 3.0, 3.0, exp.sat_level, ["nucleus"],
                     size_tol=0.25, **kw)

    only = {"nucleus": RL.TrackRule("nucleus", cy5, "only")}
    seeds0 = cluster(0)
    if "a" in parts or "e" in parts:
        o22, d22 = run(v22.track_cells, seeds0, 0)
        oN, dN = run(MN.track_cells, seeds0, 0)
        oO, dO = run(MN.track_cells, seeds0, 0, rules=only)
        if "a" in parts:
            (dif1, f1), (dif2, f2) = (v22_agrees(o22, oN, "nucleus", seeds0, 0.25, 0),
                                      v22_agrees(o22, oO, "nucleus", seeds0, 0.25, 0))
            dif0 = diff_tracks(oN, oO)
            ok("a) t0=0: rules=None is bit-identical to the ONLY rule (V2.5, every array)",
               not dif0, f"{len(dif0)} differences {dif0[:5]}")
            ok("a) t0=0: None / ONLY identical to V2.2 except the background and from the first "
               "frame V2.2 broke the hard size limit", not dif1 and not dif2,
               f"{len(dif1)} / {len(dif2)} differences; V2.2 over the limit first at t="
               f"{f1 if f1 is None else f1 + 1}")
            M = oO["meas"]["nucleus"]
            note(f"redrawn {oO['redrawn']['nucleus']:.0%}; areas t0 {M.area_px[0].tolist()} "
                 f"t{T - 1} {M.area_px[-1].tolist()} px")
            need = {"tracker", "max_move_um", "margin_px", "size_tol", "first_frame_tol", "area_step",
                    "sigma_um", "ring_um", "edge_level_clip", "phase_upsample", "mito_k", "gate_snr",
                    "overlap_k", "t0"}
            p = oO["params"]
            ok("a) params: contract keys, values as used", need <= set(p) and p["margin_px"] == int(max(3, round(3.0 / um)))
               and p["t0"] == 0 and p["tracker"] == MN.TRACKER and "norm" not in p
               and oO["rules"] == [{"comp": "nucleus", "a": "Cy5", "mode": "only", "b": ""}]
               and "rules" not in oN and "gate" not in oO,
               f"margin {p['margin_px']} px, rules {oO['rules']}")
            # QC: only the rule's channel decides 'at or below background' / 'too dim'
            s2 = Settings(seg_timepoint=1)
            seedsm = [copy.deepcopy(r) for r in seeds0]
            q_old = QC.run_qc(M, exp, s2, oO["rois"]["nucleus"], seedsm)
            q_new = QC.run_qc(M, exp, s2, oO["rois"]["nucleus"], seedsm, rule=only["nucleus"])
            note("QC reasons V2.2-style: " + str([q.reasons for q in q_old]))
            note("QC reasons with rule : " + str([q.reasons for q in q_new]))
            ok("a) QC with an ONLY Cy5 rule never blames GFP / ExRai",
               not any("GFP" in x or "ExRai" in x for q in q_new for x in q.reasons))
            # drawn later: t0 = 5 exercises the backward pass too
            seeds5 = cluster(5)
            a22, _ = run(v22.track_cells, seeds5, 5)
            aN, _ = run(MN.track_cells, seeds5, 5)
            aO, _ = run(MN.track_cells, seeds5, 5, rules=only)
            (d1, g1), (d2, _g2) = (v22_agrees(a22, aN, "nucleus", seeds5, 0.25, 5),
                                   v22_agrees(a22, aO, "nucleus", seeds5, 0.25, 5))
            ok("a) t0=5 (forwards + backwards): None and ONLY identical to V2.2 (same terms)",
               not d1 and not d2 and not diff_tracks(aN, aO),
               f"{len(d1)} / {len(d2)} differences; V2.2 over the limit first at t="
               f"{g1 if g1 is None else g1 + 1}")
        if "e" in parts:
            t22, tN, tO = [d22], [dN], [dO]
            for _ in range(3):
                t22.append(run(v22.track_cells, seeds0, 0)[1])
                tO.append(run(MN.track_cells, seeds0, 0, rules=only)[1])
                tN.append(run(MN.track_cells, seeds0, 0)[1])
            b22, bN, bO = min(t22), min(tN), min(tO)
            timings["nuclei 6 x 12 tp"] = dict(v22=b22, none=bN, only=bO)
            note(f"timings (s, best of {len(t22)}): V2.2 {b22:.3f}  None {bN:.3f}  ONLY {bO:.3f}  "
                 f"(all runs V2.2 {['%.2f' % x for x in t22]}, ONLY {['%.2f' % x for x in tO]})")
            # V2.5 measures the background at every timepoint from all of its
            # pixels (cells included, exclusions per frame) - its own time is allowed
            tb = []
            for _ in range(3):
                t = time.perf_counter()
                bm = MN.BackgroundMeter(bg, T, exp.n_channels, um)
                for tt in range(T):
                    bm.add(tt, cs.frame(tt))
                bm.finish()
                tb.append(time.perf_counter() - t)
            b_bg = min(tb)
            note(f"background meter alone: {b_bg:.3f} s for {T} frames ({bg.area} px region)")
            ok("e) ONLY not slower than V2.2 by more than 5 % + the background measurement",
               bO <= 1.05 * b22 + b_bg + 0.02,
               f"ONLY/V2.2 = {bO / b22:.3f}; None/V2.2 = {bN / b22:.3f}; background {b_bg:.2f} s")

    if "d" in parts:
        print("--- d) IF: nucleus using Cy5 IF intensity in GFP", flush=True)
        y0, x0, y1, x1 = bg.bbox
        cy, cx = (y0 + y1) // 2, (x0 + x1) // 2
        rad = int(MN._px(5.0, um))
        yy, xx = np.mgrid[-rad:rad + 1, -rad:rad + 1]
        fake = MN.Roi((cy - rad, cx - rad, cy + rad + 1, cx + rad + 1), yy * yy + xx * xx <= rad * rad,
                      "nucleus", source="manual")
        fake.channel = cy5
        seeds_if = list(seeds0) + [fake]
        f0 = cs.frame(0)
        note(f"empty ROI at ({cx}, {cy}): GFP mean {f0[gfp][fake.bbox[0]:fake.bbox[2], fake.bbox[1]:fake.bbox[3]][fake.mask].mean():.0f} "
             f"vs frame median {np.median(f0[gfp][::4, ::4]):.0f}")
        rif = {"nucleus": RL.TrackRule("nucleus", cy5, "if", gfp)}
        oI, dI = run(MN.track_cells, seeds_if, 0, rules=rif, gate_snr=5.0)
        oO7, _ = run(MN.track_cells, seeds_if, 0, rules=only)
        g = oI.get("gate", {}).get("nucleus", {})
        ok("d) gate SNR returned for every cell", sorted(g) == list(range(len(seeds_if)))
           and all(np.isfinite(v) for v in g.values()),
           "SNR " + ", ".join(f"{k + 1}: {v:.1f}" for k, v in sorted(g.items())))
        ok("d) the ROI over the empty area has a low GFP SNR", g.get(len(seeds_if) - 1, 99) < 5.0,
           f"{g.get(len(seeds_if) - 1)}")
        d_if = diff_tracks(oO7, oI)
        ok("d) IF does not change the outlines or measurements (followed on Cy5 as ONLY)", not d_if,
           f"{len(d_if)} differences")
        snr_direct = RL.gate_snr(f0, oI["rois"]["nucleus"][0][0], rif["nucleus"], um)
        ok("d) gate SNR = rules.gate_snr on the drawn frame (norm noise == plane noise)",
           abs(snr_direct - g[0]) < 1e-9, f"{snr_direct:.4f} vs {g[0]:.4f}")
        s3 = Settings(seg_timepoint=1, gate_snr=5.0)
        seedsm = [copy.deepcopy(r) for r in seeds_if]
        qi = QC.run_qc(oI["meas"]["nucleus"], exp, s3, oI["rois"]["nucleus"], seedsm,
                       rule=rif["nucleus"], gate=g)
        last = qi[-1]
        ok("d) QC excludes it with the IF-gate reason", (not last.passed) and last.reasons
           and last.reasons[0].startswith("no GFP signal (IF gate: SNR ") and last.reasons[0].endswith("< 5)"),
           f"{last.reasons}")
        failed = [k + 1 for k, q in enumerate(qi) if not q.passed]
        # AND with a channel that is dark in some ROIs: pixels dropped, empty -> NaN
        print("--- d2) AND: nucleus using Cy5 AND intensity in GFP (same ROIs)", flush=True)
        rand = {"nucleus": RL.TrackRule("nucleus", cy5, "and", gfp)}
        oA, dA = run(MN.track_cells, seeds_if, 0, rules=rand, overlap_k=3.0)
        MA = oA["meas"]["nucleus"]
        sub = all(not (a.mask & ~o.mask).any() and np.array_equal(a.outline, MN._shape(o))
                  for ra_, ro_ in zip(oA["rois"]["nucleus"], oO7["rois"]["nucleus"])
                  for a, o in zip(ra_, ro_))
        ok("d2) AND masks are subsets of ONLY's; outline = ONLY's region", sub)
        kept = MA.area_px.sum(0) / np.maximum(oO7["meas"]["nucleus"].area_px.sum(0), 1)
        note("kept fraction per cell: " + ", ".join(f"{v:.0%}" for v in kept))
        emp = [(t, k) for t in range(T) for k in range(len(seeds_if)) if MA.area_px[t, k] == 0]
        ok("d2) empty AND ROIs measure NaN on every channel with quality 0.3",
           all(np.isnan(MA.mean[t, :, k]).all() and MA.quality[t, k] == 0.3 for t, k in emp)
           and all(MA.area_px[:, len(seeds_if) - 1] == 0),
           f"{len(emp)} empty ROI-frames (the empty-area ROI at {int((MA.area_px[:, -1] == 0).sum())}/{T})")
        qa = QC.run_qc(MA, exp, s3, oA["rois"]["nucleus"], [copy.deepcopy(r) for r in seeds_if],
                       rule=rand["nucleus"])
        note(f"QC with the AND rule, empty-area ROI: {qa[-1].reasons}")
        ok("d2) QC runs on AND results and does not pass the empty ROI on its own",
           len(qa) == len(seeds_if) and any("background" in x or "dim" in x or "not re-detected" in x
                                            for x in qa[-1].reasons))
        note(f"AND run {dA:.2f} s")
        note(f"cells failing the gate (1-based): {failed}; summary: {QC.summarise(qi, range(len(qi)))}")
        note(f"IF run {dI:.2f} s")
    src.close()
    del cs


# ==========================================================================
def part_b(v22):
    print("\n=== b) WITH: whole cell, mCherry WITH GFP (HeLa mRuby file) ===", flush=True)
    src = open_source(RUBY)
    T = 10
    exp = sub_exp(src, T)
    mch, gfp = exp.channels.index("mCherry"), exp.channels.index("GFP")
    um = exp.um_per_px
    cs = Cached(src, T)
    s = Settings()
    f0 = cs.frame(0)
    rw = RL.TrackRule("cell", mch, "with", gfp)
    norm, dn = timed(RL.make_norm, f0)
    g, dg = timed(RL.guide_plane, f0, rw, norm)
    A = f0[mch]
    note(f"make_norm {dn * 1000:.0f} ms, guide_plane {dg * 1000:.0f} ms (2400x2400); "
         f"norm {norm.to_dict(exp.channels)}")
    gp = np.percentile(g, [0.1, 20, 50, 99.5, 99.9])
    ap = np.percentile(A, [0.1, 20, 50, 99.5, 99.9])
    note(f"guide percentiles 0.1/20/50/99.5/99.9: {np.round(gp).tolist()}  mCherry: {np.round(ap).tolist()}")
    span = norm.top[mch] - norm.bg[mch]
    ok("b) guide plane float32, finite, in mCherry's count range",
       g.dtype == np.float32 and np.isfinite(g).all() and abs(gp[1] - norm.bg[mch]) < 0.25 * span
       and norm.bg[mch] < gp[3] <= norm.top[mch] + 0.5 * span and gp[0] >= 0.5 * float(A.min()) - span,
       f"bg/top mCherry {norm.bg[mch]:.0f}/{norm.top[mch]:.0f}")
    seeds = peaks_draw("cell", g, um, s, 4, mch)
    note("drawn on the WITH image: " + ", ".join(f"{MN._shape(r).sum() * um * um:.0f}" for r in seeds) + " um2")
    ok("b) whole cells drawn on the WITH guide", len(seeds) >= 3, f"{len(seeds)}")
    bg, msg = MN.auto_background([cs.frame(0), cs.frame(T // 2), cs.frame(T - 1)], um)

    def run(fn, **kw):
        cells = [{"cell": copy.deepcopy(r)} for r in seeds]
        return timed(fn, cs, exp, cells, bg, 0, 3.0, 3.0, exp.sat_level, ["cell"], size_tol=0.25, **kw)

    try:
        oW, dW = run(MN.track_cells, rules={"cell": rw})
        err = ""
    except Exception as e:                                   # noqa: BLE001
        oW, dW, err = None, 0.0, repr(e)
    ok("b) WITH tracking runs", oW is not None, err)
    oO, dO = run(MN.track_cells, rules={"cell": RL.TrackRule("cell", mch)})
    oN, _ = run(MN.track_cells)
    o22, _ = run(v22.track_cells)
    (db1, fb), (db2, _fb2) = (v22_agrees(o22, oN, "cell", seeds, 0.25, 0),
                              v22_agrees(o22, oO, "cell", seeds, 0.25, 0))
    ok("b) whole cell: None == ONLY (V2.5); identical to V2.2 except the background and from the "
       "first frame V2.2 broke the hard size limit", not diff_tracks(oN, oO) and not db1 and not db2,
       f"V2.2 over the limit first at t={fb if fb is None else fb + 1}")
    if oW is None:
        return
    dW2 = run(MN.track_cells, rules={"cell": rw})[1]
    dO2 = run(MN.track_cells, rules={"cell": RL.TrackRule("cell", mch)})[1]
    dW, dO = min(dW, dW2), min(dO, dO2)
    timings["cells WITH 10 tp"] = dict(only=dO, with_=dW)
    bad, worst = area_guard_ok(oW, "cell", seeds, 0.25)
    ok("b) every WITH outline within the size guard", not bad,
       f"area / drawn from {worst[0]:.2f} to {worst[1]:.2f}; outside: {bad[:5]}")
    M = oW["meas"]["cell"]
    ok("b) WITH measurements finite (every channel, cell, timepoint)",
       np.isfinite(M.mean).all() and (M.area_px > 0).all())
    ok("b) WITH record: rule + norm in the result", oW["rules"] == [rw.to_dict(exp.channels)]
       and set(oW["params"]["norm"]) == set(exp.channels), f"{oW['rules']}")
    aW, aO = oW["meas"]["cell"].area_px.astype(float), oO["meas"]["cell"].area_px.astype(float)
    a_seed = np.array([r.area for r in seeds], float)
    note("area WITH / ONLY per cell (median over time): "
         + ", ".join(f"{v:.2f}" for v in np.median(aW / aO, axis=0)))
    note("area at t0 / drawn: WITH " + ", ".join(f"{v:.2f}" for v in aW[0] / a_seed)
         + "; ONLY " + ", ".join(f"{v:.2f}" for v in aO[0] / a_seed))
    # drawn and first-frame redraw on the SAME plane: the tracker's norm is the
    # one the cells were drawn with (make_norm of the drawn frame), so its guide
    # plane at t0 is bit-identical to the drawing plane
    ok("b) WITH: the tracker redraws t0 on exactly the plane drawn on (same norm)",
       oW["params"]["norm"] == norm.to_dict(exp.channels)
       and _eq(RL.guide_plane(cs.frame(0), rw, RL.make_norm(cs.frame(0))), g))
    step = np.abs(aW[1] / aW[0] - 1)
    seedsO = peaks_draw("cell", A, um, s, 4, mch)
    oO2 = MN.track_cells(cs, exp, [{"cell": copy.deepcopy(r)} for r in seedsO], bg, 0, 3.0, 3.0,
                         exp.sat_level, ["cell"], size_tol=0.25, rules={"cell": RL.TrackRule("cell", mch)})
    aO2 = oO2["meas"]["cell"].area_px.astype(float)
    stepO = np.abs(aO2[1] / aO2[0] - 1)
    note("area change t1->t2 per cell: WITH " + ", ".join(f"{v:.1%}" for v in step)
         + "; ONLY (cells drawn on mCherry) " + ", ".join(f"{v:.1%}" for v in stepO)
         + " - the first frame is held within 10 % of the size drawn, later frames within 25 %"
         " (V2.2 size guard), so a cell drawn smaller than the tracker sees it grows at t2")
    note("max area change per frame step, WITH: " + ", ".join(
        f"{np.abs(aW[i + 1] / aW[i] - 1).max():.0%}" for i in range(T - 1)))
    note(f"redrawn: WITH {oW['redrawn']['cell']:.0%}, ONLY {oO['redrawn']['cell']:.0%}")
    rG = M.mean[:, gfp, :] - M.background[:, gfp][:, None]
    rO = oO["meas"]["cell"].mean[:, gfp, :] - M.background[:, gfp][:, None]
    note("bg-subtracted GFP, WITH / ONLY (median): " + ", ".join(f"{v:.2f}" for v in np.median(rG / rO, axis=0)))
    note(f"timing (best of 2): ONLY {dO:.2f} s, WITH {dW:.2f} s -> WITH overhead {100 * (dW / dO - 1):+.0f} %"
         f" ({(dW - dO) / T * 1000:.0f} ms per timepoint)")
    src.close()


# ==========================================================================
def part_c(v22):
    print("\n=== c) AND: mitochondria, GFP AND ExRai (MEF mito file) ===", flush=True)
    src = open_source(MITO)
    T = 10
    exp = sub_exp(src, T)
    gfp, exr = exp.channels.index("GFP"), exp.channels.index("ExRai")
    um = exp.um_per_px
    cs = Cached(src, T)
    s = Settings()
    f0 = cs.frame(0)
    seeds = peaks_draw("mito", f0[gfp], um, s, 4, gfp)
    note("mito ROIs drawn on GFP: " + ", ".join(f"{r.area * um * um:.0f}" for r in seeds) + " um2 measured")
    ok("c) mito ROIs drawn", len(seeds) >= 3, f"{len(seeds)}")
    bg, msg = MN.auto_background([cs.frame(0), cs.frame(T // 2), cs.frame(T - 1)], um)
    ra = RL.TrackRule("mito", gfp, "and", exr)

    def run(fn, **kw):
        cells = [{"mito": copy.deepcopy(r)} for r in seeds]
        return timed(fn, cs, exp, cells, bg, 0, 3.0, 3.0, exp.sat_level, ["mito"], size_tol=0.25, **kw)

    oA, dA = run(MN.track_cells, rules={"mito": ra}, overlap_k=3.0)
    oO, dO = run(MN.track_cells, rules={"mito": RL.TrackRule("mito", gfp)})
    oN, _ = run(MN.track_cells)
    o22, _ = run(v22.track_cells)
    (dc1, fc), (dc2, _fc2) = (v22_agrees(o22, oN, "mito", seeds, 0.25, 0),
                              v22_agrees(o22, oO, "mito", seeds, 0.25, 0))
    ok("c) mito: None == ONLY (V2.5); identical to V2.2 except the background and from the "
       "first frame V2.2 broke the hard size limit", not diff_tracks(oN, oO) and not dc1 and not dc2,
       f"V2.2 over the limit first at t={fc if fc is None else fc + 1}; {dc1[:4]}")
    subset, same_geo, n_and, n_only = True, True, 0, 0
    per = np.zeros(len(seeds))
    per_o = np.zeros(len(seeds))
    empty = []
    for t in range(T):
        for k in range(len(seeds)):
            a, o = oA["rois"]["mito"][t][k], oO["rois"]["mito"][t][k]
            if a.bbox != o.bbox or a.mask.shape != o.mask.shape:
                subset = same_geo = False
                continue
            subset &= not (a.mask & ~o.mask).any()
            same_geo &= np.array_equal(a.outline, o.outline)
            n_and += int(a.mask.sum())
            n_only += int(o.mask.sum())
            per[k] += a.mask.sum()
            per_o[k] += o.mask.sum()
            if not a.mask.any():
                empty.append((t, k))
    ok("c) every AND measured mask is a subset of the ONLY mask at the same frame", subset)
    ok("c) AND follows the same region as ONLY (outline identical every frame)", same_geo)
    MA, MO = oA["meas"]["mito"], oO["meas"]["mito"]
    ok("c) AND area = kept pixels; ONLY areas unchanged elsewhere",
       int(MA.area_px.sum()) == n_and and int(MO.area_px.sum()) == n_only)
    emp_ok = all(np.isnan(MA.mean[t, :, k]).all() and MA.quality[t, k] == 0.3 for t, k in empty)
    ok("c) a frame with nothing kept measures NaN with quality 0.3", emp_ok, f"{len(empty)} empty ROI-frames")
    note(f"kept fraction (AND / ONLY pixels): overall {n_and / max(n_only, 1):.2%} ({n_only - n_and} px dropped); per cell "
         + ", ".join(f"{v:.0%}" for v in per / np.maximum(per_o, 1)))
    bA = MA.mean[:, exr, :] - MA.background[:, exr][:, None]
    bO = MO.mean[:, exr, :] - MO.background[:, exr][:, None]
    note("bg-subtracted ExRai, AND / ONLY (median per cell): "
         + ", ".join(f"{v:.2f}" for v in np.nanmedian(bA / bO, axis=0)))
    if n_and < n_only:
        ok("c) kept pixels are not dimmer in ExRai than the whole ROI (dropped = the dim ones)",
           np.nanmin(bA / bO) >= 1.0 - 1e-9, f"min ratio {np.nanmin(bA / bO):.5f}")
    else:
        note("every mitochondrial GFP pixel is also clearly bright in ExRai at k = 3 (both are "
             "mitochondrial in this file), so AND keeps everything here")
    # the test itself: a stricter k keeps fewer pixels (drawn frame)
    norm0 = RL.make_norm(f0)
    fr = []
    for kk in (3.0, 10.0, 30.0, 100.0, 300.0):
        kept = sum(int(RL.overlap_mask(f0, r, ra, norm0, um, kk).sum()) for r in seeds)
        fr.append(kept / max(sum(int(r.mask.sum()) for r in seeds), 1))
    note(f"ExRai noise {norm0.noise[exr]:.2f} counts; kept fraction at k = 3/10/30/100/300: "
         + ", ".join(f"{v:.0%}" for v in fr))
    ok("c) a stricter overlap_k keeps fewer (never more) pixels", all(b <= a for a, b in zip(fr, fr[1:]))
       and fr[-1] < fr[0])
    ok("c) AND record: rule + norm in params", oA["rules"] == [ra.to_dict(exp.channels)]
       and "norm" in oA["params"] and oA["params"]["overlap_k"] == 3.0)
    timings["mito AND 10 tp"] = dict(only=dO, and_=dA)
    note(f"timing: ONLY {dO:.2f} s, AND {dA:.2f} s")
    # the GUI helper on the drawn frame
    norm = RL.make_norm(f0)
    shown = RL.apply_and(seeds[0], f0, ra, norm, um, 3.0)
    ok("c) apply_and on the drawn frame: subset, outline kept", not (shown.mask & ~seeds[0].mask).any()
       and np.array_equal(shown.outline, MN._shape(seeds[0])) and shown.channel == gfp,
       f"kept {shown.mask.sum() / max(seeds[0].mask.sum(), 1):.0%}")
    src.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parts", default="abcde")
    ap.add_argument("--v22", default="8e31298")
    a = ap.parse_args()
    v22 = load_v22(a.v22)
    with warnings.catch_warnings(record=True) as wl:
        warnings.simplefilter("always")
        t = time.perf_counter()
        if set("ade") & set(a.parts):
            part_a_d_e(v22, a.parts)
        if "b" in a.parts:
            part_b(v22)
        if "c" in a.parts:
            part_c(v22)
    msgs = sorted({f"{w.category.__name__}: {w.message}" for w in wl})
    print(f"\nwarnings seen ({len(wl)}): {msgs[:8]}")
    print(f"timings: {timings}")
    bad = [n for n, c in checks if not c]
    print(f"{len(checks) - len(bad)}/{len(checks)} passed in {time.perf_counter() - t:.0f} s"
          + (f"; FAILED: {bad}" if bad else ""))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
