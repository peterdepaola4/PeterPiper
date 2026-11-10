"""
Developer test (not shipped): the V2.5 tracking / background / session changes.

    PETERPIPER_HOME=<scratch>/_home MPLBACKEND=Agg python dev_tests/test_v25_track.py [--real]

  a  rule lock: WITH / AND / IF ROIs are subsets of the ONLY ROI of the same cell
     at every frame and within the hard size cap (synthetic movie; --real: also
     the u2os file, nuclei on Cy5, B = GFP)
  b  size 0 %: every frame has EXACTLY the drawn pixel count
  c  boundary lines: no ROI pixel ever on the far side of / on the line
  d  background: cells included, a dead (very bright) object and a fast-moving
     object left out only at their frames; mean = sum / pixels; ROI mean = sum / area
  e  no two cells' ROIs overlap in a frame
  f  content key: identical saves -> same key; volatile state ignored; dedupe_runs
  g  Excel: Sum_ / Area_px / Area_um2 sheets; Raw = Sum / Area_px
  h  old files: a track without the V2.5 fields still loads (roifile round trip)
Exit code 0 = every check passed.
"""
from __future__ import annotations

import labdata  # noqa: E402  (lab file names: dev_tests/lab_paths.json, never uploaded)

import argparse
import copy
import os
import sys
import tempfile
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "app"))
os.environ.setdefault("PETERPIPER_HOME", tempfile.mkdtemp(prefix="pd4v25_"))

from peterpiper import manual as MN                               # noqa: E402
from peterpiper import rules as RL                                # noqa: E402
from peterpiper import roifile as RF                              # noqa: E402
from peterpiper import history as HI                              # noqa: E402
from peterpiper.segment import Roi                                # noqa: E402

checks = []


def ok(name, cond, extra=""):
    checks.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra else ""), flush=True)


class Exp:
    def __init__(self, T, C, H, W, um=0.5, names=("A", "B")):
        self.n_timepoints, self.n_channels, self.height, self.width = T, C, H, W
        self.um_per_px = um
        self.channels = list(names)[:C]
        self.nd2_path = "synthetic.nd2"
        self.seconds_per_frame = 10.0
        self.bit_depth = 16
        self.sat_level = 65535
        self.out_dir = tempfile.gettempdir()
        self.objective = ""

    def time_axis(self, T, b):
        x = (np.arange(T) - b) * self.seconds_per_frame / 60.0
        return x, "Time (min)"


class Src:
    def __init__(self, frames):
        self.frames = frames

    def frame(self, t):
        return self.frames[int(t)]


def disc(H, W, cy, cx, r):
    yy, xx = np.mgrid[0:H, 0:W]
    return (yy - cy) ** 2 + (xx - cx) ** 2 <= r * r


def synth(T=8, H=220, W=260, seed=1, dead_at=(), mover=()):
    """Two touching cells (A bright, B bright only in one half of cell 1), a
    third cell, a background with dim 'non-transfected' cells; optional dead
    object (frames dead_at) and a fast mover (frames mover) in the background."""
    rng = np.random.default_rng(seed)
    frames = []
    for t in range(T):
        A = np.full((H, W), 200.0)
        B = np.full((H, W), 150.0)
        c1 = disc(H, W, 70 + t, 70 + t * 0.5, 22)
        c2 = disc(H, W, 70 + t, 112 + t * 0.5, 20)          # touches cell 1
        c3 = disc(H, W, 160, 80, 18)
        for m, a in ((c1, 1800), (c2, 1500), (c3, 1200)):
            A[m] += a
        half = c1 & (np.mgrid[0:H, 0:W][1] < 70 + t * 0.5)
        B[half] += 1400
        B[c2] += 900
        # dim non-transfected cells in the background area (right half)
        for cy, cx in ((60, 200), (150, 210), (190, 170)):
            m = disc(H, W, cy, cx, 14)
            A[m] += 120
            B[m] += 90
        if t in dead_at:
            m = disc(H, W, 100, 215, 5)
            A[m] += 20000
            B[m] += 15000
        if t in mover:
            m = disc(H, W, 40 + 30 * (t % 3), 180, 4)
            A[m] += 6000
            B[m] += 4000
        st = np.stack([A, B])
        st += rng.normal(0, 15, st.shape)
        frames.append(np.clip(st, 0, 65535).astype(np.uint16))
    return frames


def draw_cells(frames, um):
    """The three cells as drawn by hand (their true outlines at t0, 1 px inside)."""
    H, W = frames[0].shape[1:]
    out = []
    for (y, x, r) in ((70, 70, 21), (70, 112, 19), (160, 80, 17)):
        m = disc(H, W, y, x, r)
        ys, xs = np.nonzero(m)
        y0, x0, y1, x1 = ys.min(), xs.min(), ys.max() + 1, xs.max() + 1
        roi = Roi((int(y0), int(x0), int(y1), int(x1)), m[y0:y1, x0:x1].copy(), "cell")
        roi.source, roi.channel = "manual", 0
        out.append(roi)
    return out


def bg_region(H, W):
    return Roi((20, 150, 210, 250), np.ones((190, 100), bool), "background")


def run(frames, exp, seeds, rules=None, tol=0.25, boundaries=None, bg=None, t0=0):
    cells = [{"cell": copy.deepcopy(r)} for r in seeds]
    return MN.track_cells(Src(frames), exp, cells, bg or bg_region(exp.height, exp.width), t0,
                          3.0, 3.0, 65535, ["cell"], size_tol=tol, rules=rules, overlap_k=3.0,
                          boundaries=boundaries)


def full(r: Roi, shape, outline=True):
    m = np.zeros(shape, bool)
    y0, x0, y1, x1 = r.bbox
    m[y0:y1, x0:x1] = MN._shape(r) if outline else r.mask
    return m


def subset_and_cap(o_rule, o_only, seeds, tol, shape):
    bad_sub, bad_cap = [], []
    for t, (row_r, row_o) in enumerate(zip(o_rule["rois"]["cell"], o_only["rois"]["cell"])):
        for k, (a, o) in enumerate(zip(row_r, row_o)):
            fa, fo = full(a, shape, False), full(o, shape, False)
            if (fa & ~fo).any():
                bad_sub.append((t, k))
            lo, hi = MN.size_limits(MN._region(seeds[k]).area, tol)
            if not (lo <= MN._region(o).area <= hi) or MN._region(a).area > hi:
                bad_cap.append((t, k, MN._region(o).area, lo, hi))
    return bad_sub, bad_cap


def part_a_b_c_e():
    print("\n=== a / b / c / e: synthetic movie ===", flush=True)
    T, H, W = 8, 220, 260
    exp = Exp(T, 2, H, W)
    frames = synth(T, H, W)
    um = exp.um_per_px
    seeds = draw_cells(frames, um)
    ok("three cells drawn", len(seeds) == 3, ", ".join(str(r.area) for r in seeds))
    only = {"cell": RL.TrackRule("cell", 0, "only")}
    oO = run(frames, exp, seeds, only)
    for mode in ("with", "and", "if"):
        rr = {"cell": RL.TrackRule("cell", 0, mode, 1)}
        o = run(frames, exp, seeds, rr)
        sub, cap = subset_and_cap(o, oO, seeds, 0.25, (H, W))
        ok(f"a) {mode.upper()}: every measured ROI is a subset of the ONLY ROI (same cell, frame)",
           not sub, f"{len(sub)} bad {sub[:4]}")
        ok(f"a) {mode.upper()}: within the hard size cap (+/-25 % of drawn)", not cap, f"{cap[:3]}")
        same_outline = all(np.array_equal(full(a, (H, W)), full(b, (H, W)))
                           for ra, rb in zip(o["rois"]["cell"], oO["rois"]["cell"])
                           for a, b in zip(ra, rb))
        ok(f"a) {mode.upper()}: followed outline identical to ONLY's at every frame", same_outline)
        if mode == "and":
            kept = o["meas"]["cell"].area_px[:, 0] / oO["meas"]["cell"].area_px[:, 0]
            ok("a) AND trims cell 1 to its B-bright half", np.all((kept > 0.2) & (kept < 0.85)),
               ", ".join(f"{v:.2f}" for v in kept))
        if mode == "with":
            kept = o["meas"]["cell"].area_px.sum() / oO["meas"]["cell"].area_px.sum()
            ok("a) WITH keeps part of the ONLY pixels (never more)", 0 < kept <= 1, f"{kept:.2f}")
    # e) no overlap
    over = []
    for t in range(T):
        ms = [full(r, (H, W)) for r in oO["rois"]["cell"][t]]
        for i in range(len(ms)):
            for j in range(i + 1, len(ms)):
                if (ms[i] & ms[j]).any():
                    over.append((t, i, j))
    ok("e) no two cells' ROIs overlap in any frame (touching cells 1 / 2)", not over, f"{over[:3]}")
    # b) size 0
    o0 = run(frames, exp, seeds, only, tol=0.0)
    want = [MN._region(r).area for r in seeds]
    got = o0["meas"]["cell"].area_px
    exact = all(int(got[t, k]) == want[k] for t in range(T) for k in range(len(seeds)))
    ok("b) size 0 %: every frame has exactly the drawn pixel count", exact,
       f"drawn {want}; t{T - 1} {got[-1].tolist()}")
    conn = all(MN.ndi.label(MN._region(r).mask)[1] == 1 for row in o0["rois"]["cell"] for r in row)
    ok("b) size 0 %: every ROI is one connected piece", conn)
    ok("b) size 0 %: params record equal size limits", o0["params"]["size_limits"] == [1.0, 1.0])
    # c) boundary line between cell 1 and cell 2 (vertical, through their contact)
    xline = 91.0
    lines = {0: [[(xline, -5.0), (xline, H + 5.0)]], 1: [[(xline, -5.0), (xline, H + 5.0)]]}
    # cell 1 drawn so it is generous (50 % size) - it must still never cross
    oB = run(frames, exp, seeds, only, tol=0.5, boundaries=lines)
    wall = MN.wall_mask(lines[0], (H, W))
    lab = MN.ndi.label(~wall)[0]
    s1 = lab == lab[70, 60]
    s2 = lab == lab[70, 120]
    cross = []
    for t in range(T):
        r1, r2 = oB["rois"]["cell"][t][0], oB["rois"]["cell"][t][1]
        if (full(r1, (H, W)) & ~s1).any():
            cross.append((t, 1))
        if (full(r2, (H, W)) & ~s2).any():
            cross.append((t, 2))
    ok("c) boundary: cells 1 and 2 never cross / touch their line", not cross and s1.sum() != s2.sum(),
       f"{cross[:4]}")
    ok("c) boundary recorded in params (1-based cell numbers)",
       sorted(oB["params"].get("boundaries", {})) == ["1", "2"] and oB["params"]["wall_px"] == 3)
    # an open line that reaches no edge: the component = everything but the line
    side = MN.boundary_side([[(10.0, 10.0), (30.0, 30.0)]], (H, W), seeds[0])
    ok("c) an open line only removes its own pixels", side is not None
       and (~side).sum() == MN.wall_mask([[(10.0, 10.0), (30.0, 30.0)]], (H, W)).sum())
    # _exact_area unit check
    sm = np.random.default_rng(3).random((40, 40)).astype(np.float32)
    m = disc(40, 40, 20, 20, 12)
    for n in (50, 200, int(m.sum()), 600):
        e = MN._exact_area(m, sm, np.ones_like(m), n)
        ok(f"_exact_area -> {n} px, connected", int(e.sum()) == n
           and MN.ndi.label(e)[1] == 1 and (n > m.sum() or not (e & ~m).any()))


def part_d():
    print("\n=== d) background: cells included, dead / moving objects left out ===", flush=True)
    T, H, W = 9, 220, 260
    exp = Exp(T, 2, H, W)
    dead, mover = (3, 4), (6,)
    frames = synth(T, H, W, dead_at=dead, mover=mover)
    seeds = draw_cells(frames, exp.um_per_px)
    bg = bg_region(H, W)
    o = run(frames, exp, seeds, {"cell": RL.TrackRule("cell", 0)}, bg=bg)
    M = o["meas"]["cell"]
    info = o["background"]
    y0, x0, y1, x1 = bg.bbox
    plain_sum = np.array([frames[t][:, y0:y1, x0:x1][:, bg.mask].astype(np.float64).sum(axis=1)
                          for t in range(T)])
    ok("d) nothing left out: background sum = sum of EVERY region pixel (exactly)",
       np.array_equal(plain_sum, M.background_sum) and not o["bg_excluded"])
    ok("d) background pixel count = the whole region at every timepoint",
       all(int(M.background_npx[t]) == int(bg.mask.sum()) for t in range(T)))
    ok("d) background mean = sum / pixels (exactly)",
       np.array_equal(M.background, M.background_sum / M.background_npx[:, None]))
    jumps = sorted(set(t for f in info["fluct"] for t in f["jump_frames"]))
    ok("d) the dead / passing objects are reported as background jumps (1-based)",
       set(t + 1 for t in dead + mover) <= set(jumps), f"{jumps}")
    ok("d) ROI mean = sum / area (exactly, every channel, cell, frame)",
       np.array_equal(M.mean, M.sum / M.area_px[:, None, :]))
    w = MN.background_warning(info, channels=["A", "B"])
    ok("d) V2.7: the dead / passing objects are found by the object check (1-based)",
       set(t + 1 for t in dead + mover) <= set(info["obj_frames"]), f"{info['obj_frames']}")
    ok("d) the note names the object's timepoints and says every pixel was used",
       "object" in w and "timepoint(s) 4-" in w and "Every pixel" in w, w[:200])
    rng = np.random.default_rng(1)
    steady = MN.background_fluctuation(np.column_stack([100 + rng.normal(0, 1, 40),
                                                        50 + rng.normal(0, 0.5, 40)]))
    steady.update(MN.background_objects(np.zeros((40, 2))))
    ok("d) a steady background gives no note",
       MN.background_warning(dict(steady, roi_frac=[0.0] * 40), channels=["A", "B"]) == "",
       str(steady["fluct"]))
    # V2.7: lamp flicker (the whole region 8 % brighter at one timepoint), bleaching
    # (-40 % over the movie) and a few cell pixels in the region are NOT warned about
    reg_px = rng.normal(100, 5, (40, 2, 2000)).clip(1)
    reg_px[17] *= 1.08
    reg_px *= np.linspace(1.0, 0.6, 40)[:, None, None]
    m = MN.BackgroundMeter(type("R", (), {"bbox": (0, 0, 40, 50), "mask": np.ones((40, 50), bool)})(),
                           40, 2, 0.3)
    for t in range(40):
        m.add(t, reg_px[t].reshape(2, 40, 50))
    m.n_rois[5] = 30                              # 1.5 % of the region
    s = m.summary()
    ok("d) V2.7: flicker + bleaching + 1.5 % cell overlap -> jump/drift recorded, no note",
       s["fluct"][0]["jump_frames"] and s["fluct"][0]["drift_rel"] > 0.2
       and MN.background_warning(s) == "", f"{s['fluct'][0]} {s['obj_frames']}")
    reg_px[25, 0, :40] = 3000                     # a bright cell floats in (2 % of the px)
    m2 = MN.BackgroundMeter(m.region, 40, 2, 0.3)
    for t in range(40):
        m2.add(t, reg_px[t].reshape(2, 40, 50))
    s2 = m2.summary()
    ok("d) V2.7: a bright cell floating in at one timepoint is warned about",
       s2["obj_frames"] == [26] and "timepoint(s) 26" in MN.background_warning(s2, channels=["GFP"]),
       f"{s2['obj_frames']} {s2['obj_rel_max']}")
    m.n_rois[5] = 300                             # 15 % of the region
    ok("d) V2.7: measured cells covering 15 % of the region are warned about",
       "cover" in MN.background_warning(m.summary()))
    # automatic placement: avoids the drawn ROIs, may hold the dim cells
    reg, msg = MN.auto_background([frames[0], frames[T // 2], frames[-1]], exp.um_per_px,
                                  max_um=60.0, avoid=seeds)
    clash = reg is not None and any((full(reg, (H, W)) & full(r, (H, W))).any() for r in seeds)
    ok("d) automatic region placed, avoiding the measured ROIs", reg is not None and not clash, msg)
    return o, exp, frames, seeds


def part_f(o, exp, seeds):
    print("\n=== f) content key / identical sessions ===", flush=True)
    d = Path(tempfile.mkdtemp(prefix="v25ck_"))
    st = dict(v2=True, version="2.5.0", saved="2026-11-02T10:00:00", session_id="s1",
              cells=[{"cell": 0} for _ in seeds], channels=exp.channels, kind="session",
              fingerprint={"quick": "abc", "size": 10, "mtime": 1.0, "name": "x.nd2"})
    comps = {"cell": list(seeds)}
    b1 = RF.session_blob(seeds, bg_region(exp.height, exp.width), (exp.height, exp.width), 1,
                         state=st, comps=comps, track=o)
    st2 = dict(st, saved="2026-11-02T11:11:11", session_id="s2", version="2.5.1",
               fingerprint=dict(st["fingerprint"], mtime=99.0, name="moved.nd2"))
    b2 = RF.session_blob(seeds, bg_region(exp.height, exp.width), (exp.height, exp.width), 1,
                         state=st2, comps=comps, track=o)
    k1 = RF.json.loads(str(b1["state_json"]))["content_key"]
    k2 = RF.json.loads(str(b2["state_json"]))["content_key"]
    ok("f) same content, other save time / session / version -> same key", k1 == k2, k1[:12])
    st3 = dict(st, baseline=5)
    b3 = RF.session_blob(seeds, bg_region(exp.height, exp.width), (exp.height, exp.width), 1,
                         state=st3, comps=comps, track=o)
    k3 = RF.json.loads(str(b3["state_json"]))["content_key"]
    ok("f) a changed setting -> another key", k3 != k1)
    p1 = RF.write_session_blob(d / "x_session_s1.npz", b1)
    p2 = RF.write_session_blob(d / "x_session_s2.npz", b2)
    p3 = RF.write_session_blob(d / "x_session_s3.npz", b3)
    sums = [RF.read_summary(p) for p in (p1, p2, p3)]
    ok("f) read_summary returns the stored key", [s["content_key"] for s in sums] == [k1, k2, k3])
    runs = [HI.RunInfo(path=s["path"], saved=s["saved"], version=s["version"], kind=s["kind"],
                       n_cells=s["n_cells"], comps=s["comps"], tracked=s["tracked"],
                       n_timepoints=s["n_timepoints"], rules=s["rules"], nd2_name="x.nd2",
                       match="same file", summary=s) for s in sums]
    runs.sort(key=lambda r: r.saved, reverse=True)
    dd = HI.dedupe_runs(runs)
    ok("f) dedupe_runs: one entry per identical content, newest kept",
       len(dd) == 2 and any(len(r.same_as) == 1 for r in dd) and all(Path(p).exists() for p in (p1, p2, p3)),
       f"{[(Path(r.path).name, len(r.same_as)) for r in dd]}")
    # old file without content_key: zip-CRC key, identical copies agree
    old = dict(b1)
    stj = RF.json.loads(str(old["state_json"]))
    stj.pop("content_key")
    old["state_json"] = np.asarray(RF._dumps(stj))
    q1 = d / "old_ROIs.npz"
    q2 = d / "old_ROIs_2.npz"
    np.savez_compressed(q1, **old)
    stj["saved"] = "2020-01-01T00:00:00"
    old["state_json"] = np.asarray(RF._dumps(stj))
    np.savez_compressed(q2, **old)
    s1, s2 = RF.read_summary(q1), RF.read_summary(q2)
    ok("f) files before V2.5: identical content -> same (zip CRC) key",
       s1["content_key"] == s2["content_key"] and s1["content_key"] != k1)
    # h) round trip: new fields come back; a track without them loads
    with np.load(p1) as z:
        tr = RF.unpack_track(z)
    M0, M1 = o["meas"]["cell"], tr["meas"]["cell"]
    ok("h) round trip: sums, background sums / pixels, exclusions, background summary",
       np.array_equal(M0.sum, M1.sum, equal_nan=True)
       and np.array_equal(M0.background_npx, M1.background_npx)
       and sorted(tr.get("bg_excluded", {})) == sorted(o["bg_excluded"])
       and tr.get("background", {}).get("frames_with_objects") == o["background"]["frames_with_objects"])
    old2 = {k: v for k, v in b1.items() if not k.startswith("trk_bgx")
            and not k.endswith(("_m_sum", "_m_background_sum", "_m_background_npx"))}
    q3 = d / "pre25_ROIs.npz"
    np.savez_compressed(q3, **old2)
    tr2 = RF.load_roi_track(q3)
    ok("h) a track saved without the V2.5 fields loads (sum None)",
       tr2 is not None and tr2["meas"]["cell"].sum is None and "bg_excluded" not in tr2)
    return tr


def part_g(o, exp, seeds):
    print("\n=== g) Excel: Sum / Area sheets ===", flush=True)
    from openpyxl import load_workbook
    from peterpiper.config import Settings
    from peterpiper.excel import build_roi_info, write_workbook
    M = o["meas"]["cell"]
    s = Settings()
    cells = list(range(M.n_cells))
    info = build_roi_info(exp, s, M, cells, seeds, 0)
    d = Path(tempfile.mkdtemp(prefix="v25xl_"))
    path = write_workbook(str(d / "t.xlsx"), exp, s, M, cells, info,
                          provenance=dict(track_params=o["params"], comps=["cell"], bg_auto=False,
                                          bg_kind="hand", background=o["background"]))
    wb = load_workbook(path)
    names = wb.sheetnames
    ok("g) Sum_A, Sum_B, Area_px, Area_um2 written", all(n in names for n in
                                                         ("Sum_A", "Sum_B", "Area_px", "Area_um2")))
    ws_s, ws_a, ws_r = wb["Sum_A"], wb["Area_px"], wb["Raw_A"]
    good = True
    for t in range(M.n_timepoints):
        for j in range(M.n_cells):
            sm = ws_s.cell(row=t + 2, column=3 + j).value
            ar = ws_a.cell(row=t + 2, column=3 + j).value
            raw = ws_r.cell(row=t + 2, column=3 + j).value
            if sm is None or ar is None or abs(sm / ar - raw) > 5e-4 or sm != M.sum[t, 0, j]:
                good = False
        bsum, bn = ws_s.cell(row=t + 2, column=2).value, ws_a.cell(row=t + 2, column=2).value
        if abs(bsum / bn - ws_r.cell(row=t + 2, column=2).value) > 5e-4:
            good = False
    ok("g) Raw = Sum / Area_px for every cell, timepoint and the background", good)
    um2 = wb["Area_um2"].cell(row=2, column=3).value
    ok("g) Area_um2 = px x um^2", abs(um2 - M.area_px[0, 0] * exp.um_per_px ** 2) < 1e-9)
    meth = "\n".join(str(c.value) for c in wb["Methods"]["A"] if c.value)
    ok("g) Methods text: background paragraph (cells included, per timepoint), hard limits",
       "non-transfected cells" in meth and "hard" in meth and "pixel sum" in meth)


def part_real():
    print("\n=== a (real) u2os nuclei, Cy5 ONLY vs WITH / AND / IF GFP ===", flush=True)
    from peterpiper.config import Settings
    from peterpiper.nd2io import describe, open_source
    nuc = labdata.T("t02")
    if not Path(nuc).exists():
        print("     (file not found - skipped)")
        return
    src = open_source(nuc)
    T = 8
    exp = describe(src)
    exp.n_timepoints = T
    frames = [np.asarray(src.frame(t)) for t in range(T)]
    cy5, gfp = exp.channels.index("Cy5"), exp.channels.index("GFP")
    um = exp.um_per_px
    nuc_rois = MN.auto_select(frames[0][cy5], "nucleus", um, Settings())
    cen = np.array([r.centroid for r in nuc_rois])
    c0 = int(np.argmin(((cen - [exp.height / 2, exp.width / 2]) ** 2).sum(1)))
    pick = np.argsort(((cen - cen[c0]) ** 2).sum(1))[:8]
    seeds = []
    for i in pick:
        r = nuc_rois[int(i)]
        r.channel, r.source, r.kind = cy5, "manual", "nucleus"
        seeds.append(r)
    bg, msg = MN.auto_background([frames[0], frames[T // 2], frames[-1]], um, 150.0, avoid=seeds)
    ok("real: automatic background placed (150 um, avoiding ROIs)", bg is not None, msg)

    def go(rule, tol=0.25):
        cells = [{"nucleus": copy.deepcopy(r)} for r in seeds]
        return MN.track_cells(Src(frames), exp, cells, bg, 0, 3.0, 3.0, exp.sat_level,
                              ["nucleus"], size_tol=tol, rules={"nucleus": rule}, overlap_k=3.0)
    oO = go(RL.TrackRule("nucleus", cy5))
    for mode in ("with", "and", "if"):
        o = go(RL.TrackRule("nucleus", cy5, mode, gfp))
        bad, cap = [], []
        for t in range(T):
            for k in range(len(seeds)):
                a, b = o["rois"]["nucleus"][t][k], oO["rois"]["nucleus"][t][k]
                fa = full(a, (exp.height, exp.width), False)
                fb = full(b, (exp.height, exp.width), False)
                if (fa & ~fb).any():
                    bad.append((t, k))
                lo, hi = MN.size_limits(MN._region(seeds[k]).area, 0.25)
                if MN._region(a).area > hi or not (lo <= MN._region(b).area <= hi):
                    cap.append((t, k))
        ok(f"real a) {mode.upper()}: subset of ONLY at every frame and within the cap",
           not bad and not cap, f"{len(bad)} not subset, {len(cap)} outside cap")
    o0 = go(RL.TrackRule("nucleus", cy5), 0.0)
    want = [MN._region(r).area for r in seeds]
    ok("real b) size 0 %: exactly the drawn pixel count at every frame",
       all(int(o0["meas"]["nucleus"].area_px[t, k]) == want[k] for t in range(T)
           for k in range(len(seeds))))
    src.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--real", action="store_true", help="also the u2os .nd2 (read-only, D:)")
    a = ap.parse_args()
    part_a_b_c_e()
    o, exp, frames, seeds = part_d()
    part_f(o, exp, seeds)
    part_g(o, exp, seeds)
    if a.real:
        part_real()
    n_bad = sum(1 for _n, c in checks if not c)
    print(f"\n{len(checks) - n_bad} / {len(checks)} checks passed")
    sys.exit(1 if n_bad else 0)


if __name__ == "__main__":
    main()
