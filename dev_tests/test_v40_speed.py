"""
Developer test (not shipped): PeterPiper 4.0 "speed" - the faster tracker gives
BIT-IDENTICAL results to the tracker as it was before the speed work.

    PYTHONIOENCODING=utf-8 python dev_tests/test_v40_speed.py [--real] [--lab-only]

How: the tracker of REF_COMMIT (before the speed work) is unpacked from git
into _out/v40_speed/ref_<commit>/ and run in a second Python process on the
same cases; its results are pickled once (kept for the next run) and every
result of the current code is compared with them field by field:
np.array_equal (dtype, shape, every value, NaN at the same places) for every
array, == for everything else, every ROI's bbox / mask / outline / kind /
channel / source / fit level / contours, at every timepoint.

S) synthetic movie of touching cells (synth_trackx.py), 25 cells, 10 timepoints:
   no rules, ONLY, AND, HELP + WITH, IF + AND, boundary lines, per-cell overrides,
   whole cell (size 0 %), mitochondria (AND), first / last timepoint drawn,
   a different 'Follow' row, a re-track of one changed cell (retrack.update)
   and the ROI troubleshooter (trouble.run_candidates).
--real: the lab movie T("t50"), its first 12 timepoints (read once into
   _out/v40_speed/lab12.npy, then from memory): ONLY on DAPI and DAPI AND GFP,
   about 580 nuclei; compute-only timings before / after.
Exit code 0 = every check passed.
"""
from __future__ import annotations

import os
import pickle
import subprocess
import sys
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
REF_COMMIT = "ba82bb3"                 # 4.0 trackx: the tracker before the speed work
OUT = REPO / "_out" / "v40_speed"
OUT.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("PETERPIPER_HOME", str(OUT / "home"))
APP = os.environ.get("PP_SPEED_APP") or str(REPO / "app")
sys.path.insert(0, APP)
sys.path.insert(0, str(HERE))

import numpy as np                                                   # noqa: E402

import synth_trackx as S                                             # noqa: E402
from peterpiper import manual as MN                                  # noqa: E402
from peterpiper import retrack as RT                                 # noqa: E402
from peterpiper import trouble as TB                                 # noqa: E402
from peterpiper.rules import TrackRule                               # noqa: E402
from peterpiper.segment import Roi                                   # noqa: E402

checks = []
MAKE_REF = "--make-ref" in sys.argv
REAL = "--real" in sys.argv or "--lab-only" in sys.argv
LAB_ONLY = "--lab-only" in sys.argv


def ok(name, cond, extra=""):
    checks.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra else ""), flush=True)


# ==========================================================================
#  Comparing two results exactly
# ==========================================================================
SKIP_KEYS = {"seconds"}                # wall-clock times inside a result


def diff(a, b, path="", out=None, limit=12):
    """Every place two results differ (empty list = bit-identical)."""
    out = [] if out is None else out
    if len(out) >= limit:
        return out
    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        a2, b2 = np.asarray(a), np.asarray(b)
        if a2.dtype != b2.dtype or a2.shape != b2.shape:
            out.append(f"{path}: {a2.dtype}{a2.shape} vs {b2.dtype}{b2.shape}")
        elif a2.dtype.kind in "fc":
            if not np.array_equal(a2, b2, equal_nan=True):
                out.append(f"{path}: values")
        elif a2.dtype == object:
            for i, (x, y) in enumerate(zip(a2.ravel(), b2.ravel())):
                diff(x, y, f"{path}[{i}]", out, limit)
        elif not np.array_equal(a2, b2):
            out.append(f"{path}: values")
        return out
    if isinstance(a, dict) and isinstance(b, dict):
        ka, kb = set(a) - SKIP_KEYS, set(b) - SKIP_KEYS
        if ka != kb:
            out.append(f"{path}: keys {sorted(map(str, ka ^ kb))}")
        for k in sorted(ka & kb, key=str):
            if k == "_contour_cache":                    # (ids of the masks, contours)
                diff(a[k][1], b[k][1], f"{path}.contours", out, limit)
            else:
                diff(a[k], b[k], f"{path}.{k}", out, limit)
        return out
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        if type(a) is not type(b) or len(a) != len(b):
            out.append(f"{path}: {type(a).__name__}[{len(a)}] vs {type(b).__name__}[{len(b)}]")
            return out
        for i, (x, y) in enumerate(zip(a, b)):
            diff(x, y, f"{path}[{i}]", out, limit)
        return out
    if isinstance(a, (set, frozenset)) or isinstance(b, (set, frozenset)):
        if a != b:
            out.append(f"{path}: {a} vs {b}")
        return out
    if hasattr(a, "__dict__") and hasattr(b, "__dict__") and not isinstance(a, type):
        if type(a).__name__ != type(b).__name__:
            out.append(f"{path}: {type(a).__name__} vs {type(b).__name__}")
            return out
        return diff(dict(vars(a)), dict(vars(b)), path, out, limit)
    if isinstance(a, float) and isinstance(b, float):
        if not (a == b or (a != a and b != b)):
            out.append(f"{path}: {a!r} vs {b!r}")
        return out
    if type(a) is not type(b) and not (isinstance(a, (int, float, np.number))
                                       and isinstance(b, (int, float, np.number))):
        out.append(f"{path}: {type(a).__name__} vs {type(b).__name__}")
        return out
    try:
        same = bool(a == b) or (a != a and b != b)
    except Exception:                                    # noqa: BLE001
        same = repr(a) == repr(b)
    if not same:
        out.append(f"{path}: {a!r} vs {b!r}")
    return out


# ==========================================================================
#  The cases
# ==========================================================================
class MemSrc:
    """In-memory image source (frame + crop), like ND2Source."""

    def __init__(self, frames):
        self.frames = frames
        self.n_timepoints = frames.shape[0]
        self.height, self.width = frames.shape[2:]

    def frame(self, t):
        return self.frames[int(t)]

    def crop(self, t, y0, y1, x0, x1):
        return np.array(self.frames[int(t), :, y0:y1, x0:x1])


def _synth():
    frames, truth = S.make(T=10, H=215, W=262, n_side=5)
    T, C, H, W = frames.shape
    exp = S.Exp(T, C, H, W)
    # mitochondria-like puncta on GFP (a fixed seed)
    from scipy import ndimage as ndi
    rng = np.random.default_rng(11)
    pts = np.zeros((H, W))
    pts[rng.integers(0, H, 900), rng.integers(0, W, 900)] = 4000.0
    pun = ndi.gaussian_filter(pts, 1.0)
    fm = frames.copy()
    fm[:, 1] = np.clip(frames[:, 1] + pun[None], 0, 65535).astype(np.uint16)
    return frames, truth, fm, exp


def synth_cases():
    frames, truth, fm, exp = _synth()
    T, C, H, W = frames.shape
    bg = S.background(H, W)
    t0 = 4
    nc = S.seeds(frames, truth, t0)
    ncell = S.seeds(frames, truth, t0, comps=("nucleus", "cell"))
    mito = []
    for c in S.seeds(fm, truth, t0):
        r = c["cytoplasm"]
        m = Roi(r.bbox, r.mask.copy(), "mito", True, "manual")
        m.outline = r.outline.copy()
        m.channel = 1
        mito.append({"nucleus": c["nucleus"], "mito": m})
    TR = TrackRule
    R_ONLY = {"nucleus": TR("nucleus", 0), "cytoplasm": TR("cytoplasm", 1)}
    R_AND = {"nucleus": TR("nucleus", 0, "and", 1), "cytoplasm": TR("cytoplasm", 1)}
    R_HW = {"nucleus": TR("nucleus", 0, "help", -1, (2,)),
            "cytoplasm": TR("cytoplasm", 1, "with", 0)}
    R_IF = {"nucleus": TR("nucleus", 0, "if", 1), "cytoplasm": TR("cytoplasm", 1, "and", 0)}
    BND = {6: [[(60.0, 50.0), (60.0, 120.0)]], 18: [[(150.0, 140.0), (200.0, 150.0)]]}
    OV = {("nucleus", 4): {"rule": TR("nucleus", 1)},
          ("cytoplasm", 7): {"settings": {"size_tol": 0.0, "max_move_um": 5.0}},
          ("cytoplasm", 12): {"rule": TR("cytoplasm", 1, "and", 2),
                              "settings": {"size_tol": 0.4}}}

    def cp(cl):
        return [dict(c) for c in cl]

    def tr(cl, t=t0, fr=frames, **kw):
        return MN.track_cells(MemSrc(fr), exp, cp(cl), bg, t, **kw)

    yield "S01 no rules", lambda: tr(nc)
    yield "S02 ONLY", lambda: tr(nc, rules=R_ONLY)
    yield "S03 AND", lambda: tr(nc, rules=R_AND)
    yield "S04 HELP + WITH", lambda: tr(nc, rules=R_HW)
    yield "S05 IF + AND", lambda: tr(nc, rules=R_IF, gate_snr=5.0)
    yield "S06 boundaries", lambda: tr(nc, rules=R_ONLY, boundaries=BND)
    yield "S07 overrides", lambda: tr(nc, rules=R_ONLY, overrides=OV)
    yield "S08 whole cell WITH, size 0 %", lambda: tr(
        ncell, rules={"nucleus": TR("nucleus", 0), "cell": TR("cell", 1, "with", 0)},
        size_tol=0.0)
    yield "S09 mito AND", lambda: tr(
        mito, fr=fm, rules={"nucleus": TR("nucleus", 0), "mito": TR("mito", 1, "and", 2)})
    yield "S10 first timepoint drawn", lambda: tr(nc, t=0, rules=R_ONLY)
    yield "S11 last timepoint drawn, AND", lambda: tr(nc, t=T - 1, rules=R_AND)
    yield "S12 Follow cytoplasm, no rules, 5 um", lambda: tr(nc, lead=("cytoplasm",),
                                                           max_move_um=5.0)
    yield "S13 HELP + WITH + boundaries + overrides", lambda: tr(
        nc, rules=R_HW, boundaries=BND, overrides=OV, size_tol=0.4)

    def retrack():
        prev = tr(nc, rules=R_ONLY)
        new = cp(nc)
        r = nc[7]["cytoplasm"]
        n = r.shifted(1, 0, (H, W))
        n.channel = 1
        n.outline = Roi(r.bbox, r.outline, r.kind).shifted(1, 0, (H, W)).mask
        new[7]["cytoplasm"] = n

        def snap(cl):
            return RT.snapshot(cl, R_ONLY, bg, t0, exp.channels,
                               dict(max_move_um=3.0, mito_k=3.0, size_tol=0.25, overlap_k=3.0,
                                    sat_level=65535), None, None, n_timepoints=T)
        return RT.update(MemSrc(frames), exp, new, bg, t0, prev, snap(nc), snap(new),
                         rules=R_ONLY)
    yield "S14 re-track one changed ROI", retrack

    def trouble():
        k = S.PROBLEM
        prev = tr(nc, rules=R_ONLY)
        cands = TB.alternatives(k, "nucleus", R_ONLY["nucleus"], exp, nc, frames[t0],
                                {"size_tol": 0.25, "max_move_um": 3.0})
        first = [c for c in cands if c.ring <= 1]
        got = list(TB.run_candidates(MemSrc(frames), exp, cp(nc), bg, t0, prev, k, "nucleus",
                                     first, dict(rules=R_ONLY)))
        got.sort(key=lambda r: r.candidate.label)
        return [(r.candidate.label, r.rois, r.mean, r.quality, r.area, r.score, r.grade,
                 r.reasons, r.out, r.error) for r in got]
    yield "S15 ROI troubleshooter", trouble


LAB_NPY = OUT / "lab12.npy"
LAB_PKL = OUT / "lab12_setup.pkl"


def lab_setup():
    """The first 12 timepoints of T("t50") (read from the drive once), the nuclei
    found at t = 4 on DAPI and the automatic background region."""
    if not LAB_NPY.exists() or not LAB_PKL.exists():
        from labdata import T as LT, missing
        path = LT("t50")
        if missing(path):
            return None
        from peterpiper.nd2io import ND2Source, describe
        src = ND2Source(path)
        ex = describe(src, "")
        fr = np.zeros((12, ex.n_channels, ex.height, ex.width), np.uint16)
        for t in range(12):
            fr[t] = src.frame(t)
        src.close()
        np.save(LAB_NPY, fr)
        nuc = list(MN.auto_select(fr[3][2], "nucleus", ex.um_per_px, None))
        for r in nuc:
            r.channel = 2
        bgl, _m = MN.auto_background([fr[3]], ex.um_per_px, avoid=nuc)
        with open(LAB_PKL, "wb") as f:
            pickle.dump(dict(exp=ex, nuc=nuc, bg=bgl), f)
    fr = np.load(LAB_NPY)
    with open(LAB_PKL, "rb") as f:
        d = pickle.load(f)
    d["exp"].n_timepoints = fr.shape[0]
    return fr, d


def lab_cases():
    got = lab_setup()
    if got is None:
        return
    fr, d = got
    ex, nuc, bg = d["exp"], d["nuc"], d["bg"]
    TR = TrackRule

    def tr(rules):
        return MN.track_cells(MemSrc(fr), ex, [{"nucleus": r} for r in nuc], bg, 3, rules=rules)
    yield f"L1 lab ONLY DAPI ({len(nuc)} nuclei, 12 t)", lambda: tr({"nucleus": TR("nucleus", 2)})
    yield "L2 lab DAPI AND GFP", lambda: tr({"nucleus": TR("nucleus", 2, "and", 1)})


def all_cases():
    if not LAB_ONLY:
        yield from synth_cases()
    if REAL:
        yield from lab_cases()


def run_cases():
    res = {}
    for name, fn in all_cases():
        ts = time.perf_counter()
        r = fn()
        res[name] = (r, time.perf_counter() - ts)
        print(f"    {name}: {res[name][1]:.2f} s", flush=True)
    return res


# ==========================================================================
#  The reference (the tracker of REF_COMMIT, in its own process)
# ==========================================================================
def ref_tree() -> Path:
    d = OUT / f"ref_{REF_COMMIT}"
    if not (d / "app" / "peterpiper" / "manual.py").exists():
        z = OUT / f"ref_{REF_COMMIT}.zip"
        subprocess.run(["git", "-C", str(REPO), "archive", "--format=zip", "-o", str(z),
                        REF_COMMIT, "app/peterpiper"], check=True)
        with zipfile.ZipFile(z) as zf:
            zf.extractall(d)
        z.unlink()
    return d


def reference(names) -> dict:
    """{case: (result, seconds)} of the old tracker (made once, then kept)."""
    ref = {}
    for part in ("synth", "lab"):
        f = OUT / f"ref_{REF_COMMIT}_{part}.pkl"
        want = [n for n in names if n.startswith("S" if part == "synth" else "L")]
        if not want:
            continue
        if f.exists():
            with open(f, "rb") as fh:
                got = pickle.load(fh)
            if all(n in got for n in want):
                ref.update(got)
                continue
        print(f"--- making the reference ({part}) with the tracker of {REF_COMMIT}", flush=True)
        env = dict(os.environ, PP_SPEED_APP=str(ref_tree() / "app"))
        args = [sys.executable, str(Path(__file__).resolve()), "--make-ref", str(f)]
        args += ["--lab-only"] if part == "lab" else []
        subprocess.run(args, env=env, check=True)
        with open(f, "rb") as fh:
            ref.update(pickle.load(fh))
    return ref


if __name__ == "__main__":
    if MAKE_REF:
        dest = Path(sys.argv[sys.argv.index("--make-ref") + 1])
        print(f"    (tracker from {MN.__file__})", flush=True)
        res = run_cases()
        with open(dest, "wb") as fh:
            pickle.dump(res, fh, protocol=pickle.HIGHEST_PROTOCOL)
        sys.exit(0)
    names = [n for n, _f in all_cases()]
    ref = reference(names)
    # the comparer itself: it must see one changed pixel / last bit / NaN
    import copy
    r0 = ref[names[0]][0]
    c0 = next(iter(r0["meas"]))
    bad = copy.deepcopy(r0)
    m = bad["rois"][c0][1][0].mask
    m.flat[0] = not m.flat[0]
    bad2 = copy.deepcopy(r0)
    v = bad2["meas"][c0].mean
    v[1, 0, 0] = np.nextafter(v[1, 0, 0], np.inf)
    bad3 = copy.deepcopy(r0)
    bad3["meas"][c0].mean[1, 0, 0] = np.nan
    ok("C1 the comparer finds one changed mask pixel, the last bit of a mean, a NaN",
       diff(r0, bad) and diff(r0, bad2) and diff(r0, bad3) and not diff(r0, copy.deepcopy(r0)))
    timing = {}
    for label, procs, least in (("one by one", 1, 10 ** 9), ("worker processes", 4, 1)):
        MN.TRACK_PROCS, MN.PROC_MIN_CELLS = procs, least
        print(f"--- current tracker, {label}", flush=True)
        now = run_cases()
        if procs > 1:
            ok("W1 the worker processes ran", MN._PROCS is not None and not MN._PROCS_FAILED)
        print(f"--- bit-identical to the tracker before the speed work ({label})")
        for n in names:
            d = diff(ref[n][0], now[n][0], n.split()[0])
            ok(f"{n} [{label}]: identical", not d, "; ".join(d) if d else
               f"before {ref[n][1]:.2f} s, now {now[n][1]:.2f} s")
        timing[label] = now
    print("--- timings (s): before (when the reference was made) -> one by one -> "
          "4 worker processes")
    for n in names:
        a, b, c = ref[n][1], timing["one by one"][n][1], timing["worker processes"][n][1]
        print(f"    {n}: {a:.2f} -> {b:.2f} -> {c:.2f}")
    print("    all: " + " -> ".join(f"{v:.2f}" for v in (
        sum(ref[n][1] for n in names), sum(timing["one by one"][n][1] for n in names),
        sum(timing["worker processes"][n][1] for n in names))))
    n_ok = sum(1 for _n, c in checks if c)
    print(f"{n_ok} / {len(checks)} checks passed")
    sys.exit(0 if n_ok == len(checks) else 1)
