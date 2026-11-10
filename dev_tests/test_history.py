"""
Developer test for the v2.3 session memory (roifile.py + history.py).

Run from anywhere (uses the repo's app/ folder, writes only under <repo>/_work
and <repo>/_home; reads the lab's real files on D: READ-ONLY):

    set PETERPIPER_HOME=<repo>/_home   (optional; the script sets it if missing)
    python dev_tests/test_history.py

Sections a) round trip, b) read_summary, c) fingerprint, d) find_previous_runs
(synthetic tree + real read-only scans), e) run index, f) track_problem and
V2.2-reads-V2.3. Prints PASS / FAIL lines with timings; exit code 1 on failure.
"""
from __future__ import annotations

import labdata  # noqa: E402  (lab file names: dev_tests/lab_paths.json, never uploaded)

import gc
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
W = REPO / "_work" / "history_test"
os.environ.setdefault("PETERPIPER_HOME", str(REPO / "_home"))
os.environ.setdefault("MPLBACKEND", "Agg")
sys.path.insert(0, str(REPO / "app"))

import numpy as np                                                    # noqa: E402

import peterpiper                                                         # noqa: E402
from peterpiper import history, roifile                                   # noqa: E402
from peterpiper.roifile import (load_roi_file, load_roi_state, load_roi_track,   # noqa: E402
                            read_summary, save_roi_file, save_session_file, track_problem)
from peterpiper.safety import replace_own_file                            # noqa: E402

# ---- the lab's real files (READ ONLY) ----------------------------------------------
MITO_DIR = labdata.T("t09")
V22 = MITO_DIR + labdata.T("t40")
V22_ND2 = MITO_DIR + labdata.T("t41")
V21 = (labdata.T("t05"))
OLD16 = labdata.T("t10")
BIG_ND2 = labdata.T("t04")
SAM_DIR = labdata.T("t11")
SAM_ND2 = SAM_DIR + labdata.T("t42")
from labdata import need                                    # noqa: E402
need(V22, V22_ND2, V21, BIG_ND2, SAM_ND2, what="test_history.py")   # V3.0: lab data only

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  -- {detail}" if detail else ""), flush=True)
    return ok


def ms(t):
    return f"{(time.perf_counter() - t) * 1000:.1f} ms"


def sha(p):
    return hashlib.sha1(Path(p).read_bytes()).hexdigest()


def set_home(name):
    h = W / name
    h.mkdir(parents=True, exist_ok=True)
    os.environ["PETERPIPER_HOME"] = str(h)
    return h


def rewrite_npz(src, dst, state=None, image_shape=None, drop_state=False):
    """A copy of an ROI file with its state / image size changed (our own copies only)."""
    with np.load(src, allow_pickle=False) as z:
        d = {k: z[k] for k in z.files}
    if drop_state:
        d.pop("state_json", None)
    if state is not None:
        st = json.loads(str(d["state_json"]))
        st.update(state)
        d["state_json"] = np.asarray(json.dumps(st))
    if image_shape is not None:
        d["image_shape"] = np.asarray(list(image_shape))
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    with open(dst, "wb") as f:
        np.savez_compressed(f, **d)
    return Path(dst)


def fake_file(path, size, seed):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(np.random.default_rng(seed).integers(0, 256, size, dtype=np.uint8).tobytes())
    return path


def set_mtime(p, iso):
    t = datetime.fromisoformat(iso).timestamp()
    os.utime(p, (t, t))


def raw_arrays(p):
    with np.load(p, allow_pickle=False) as z:
        return {k: z[k] for k in z.files}


def same_roi(a, b):
    if tuple(a.bbox) != tuple(b.bbox) or a.mask.shape != b.mask.shape \
            or not np.array_equal(a.mask, b.mask):
        return False
    oa, ob = getattr(a, "outline", None), getattr(b, "outline", None)
    if (oa is None) != (ob is None):
        return False
    return oa is None or np.array_equal(oa, ob)


def same_track(t1, t2):
    if set(t1["rois"]) != set(t2["rois"]):
        return False, "comps differ"
    for c in t1["rois"]:
        g1, g2 = t1["rois"][c], t2["rois"][c]
        if len(g1) != len(g2):
            return False, f"T differs for {c}"
        for t in range(len(g1)):
            if len(g1[t]) != len(g2[t]):
                return False, f"N differs at t={t}"
            for k in range(len(g1[t])):
                if not same_roi(g1[t][k], g2[t][k]):
                    return False, f"ROI differs {c} t={t} k={k}"
        M1, M2 = t1["meas"][c], t2["meas"][c]
        for f in roifile.MEAS_FIELDS:
            a, b = getattr(M1, f), getattr(M2, f)
            if (a is None) != (b is None) or (a is not None and (
                    a.dtype != b.dtype or not np.array_equal(a, b, equal_nan=a.dtype.kind == "f"))):
                return False, f"meas {f} differs for {c}"
        if list(M1.channels) != list(M2.channels) or M1.roi_mode != M2.roi_mode:
            return False, "meas channels / mode differ"
    if t1["redrawn"] != t2["redrawn"]:
        return False, "redrawn differs"
    return True, ""


def snapshot(folder):
    out = {}
    for root, dirs, files in os.walk(folder):
        for f in files + dirs:
            p = os.path.join(root, f)
            try:
                st = os.stat(p)
                out[p] = (st.st_size, st.st_mtime_ns)
            except OSError:
                out[p] = None
    return out


def nd2_shape(path):
    import nd2
    with nd2.ND2File(path) as f:
        s = f.sizes
    return (int(s["Y"]), int(s["X"])), int(s.get("T", 1))


# =================================================================================
def section_a():
    print("\n=== a) round trip of the user's real V2.2 tracked file ===")
    d = W / "a"
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    src = d / "Export_2026-10-29_17-26-39" / Path(V22).name
    src.parent.mkdir()
    shutil.copy2(V22, src)
    check("a0 copy is identical to the original", sha(src) == sha(V22))

    t = time.perf_counter()
    anchors, bg, shape, seg = load_roi_file(src)
    state, comps = load_roi_state(src)
    track = load_roi_track(src)
    t_load = ms(t)
    gc.disable()                       # a leaked np.load handle would now stay open
    try:
        moved = src.with_name("moved.npz")
        os.replace(src, moved)
        os.replace(moved, src)
        check("a1 loaders close the file (rename right after loading works)", True, t_load)
    except OSError as exc:
        check("a1 loaders close the file (rename right after loading works)", False, repr(exc))
    finally:
        gc.enable()
    T, N = len(track["rois"]["mito"]), len(track["rois"]["mito"][0])
    check("a2 V2.2 file loads with tracking", track is not None and (T, N) == (61, 10)
          and track["rules"] is None and track["params"] == {} and track["gate"] == {}
          and track["skipped"] == [], f"T={T} N={N} cells={len(anchors)} shape={shape} seg={seg}")
    chans = {getattr(r, "channel", None) for row in track["rois"]["mito"] for r in row}
    check("a3 per-frame .channel restored from the state (cells: mito on channel 0)",
          chans == {0}, f"channels seen {chans}")
    tr2 = load_roi_track(src, channels=["mCherry", "GFP", "ExRai"])
    chans2 = {getattr(r, "channel", None) for row in tr2["rois"]["mito"] for r in row}
    check("a4 .channel matched by NAME to a movie with re-ordered channels (GFP -> 1)",
          chans2 == {1}, f"{chans2}")

    # --- plain re-save with save_roi_file: every array identical, never overwrites
    out1 = save_roi_file(d / "resave_ROIs.npz", anchors, bg, shape, seg, state, comps, track)
    orig, new = raw_arrays(src), raw_arrays(out1)

    def no_key(a):        # V2.5 adds state["content_key"] (a hash of the rest)
        st_ = json.loads(str(a))
        st_.pop("content_key", None)
        return st_
    diff = [k for k in orig if k not in new
            or (orig[k].dtype != new[k].dtype and k != "state_json")   # text length differs
            or not (np.array_equal(orig[k], new[k]) if k != "state_json"
                    else no_key(orig[k]) == no_key(new[k]))]
    check("a5 save_roi_file re-save: same keys, every array bit-identical (incl. state/track JSON)",
          set(orig) == set(new) and not diff, f"{len(orig)} keys; differing: {diff[:5]}")
    h1 = sha(out1)
    out2 = save_roi_file(d / "resave_ROIs.npz", anchors, bg, shape, seg, state, comps, track)
    check("a6 save_roi_file never overwrites (second save -> _2, first unchanged)",
          out2.name == "resave_ROIs_2.npz" and sha(out1) == h1, out2.name)

    # --- session file with the extra V2.3 keys, rules / params / gate
    extra = dict(version=peterpiper.__version__, app=peterpiper.APP_TITLE, saved="2026-10-29T18:00:00",
                 session_id="2026-10-29_18-00-00", nd2_path=V22_ND2,
                 fingerprint={"name": Path(V22_ND2).name, "size": 2109276160, "mtime": 1.5,
                              "quick": "abc"},
                 exp=dict(um_per_px=np.float64(0.1625), seconds_per_frame=60.0, n_timepoints=61,
                          width=2400, height=2400, channels=["GFP", "ExRai", "mCherry"],
                          bit_depth=np.int64(16)),
                 rules=[{"comp": "mito", "a": "GFP", "mode": "with", "b": "mCherry"}],
                 baseline=9, drift=[2, 9], track_params={"size_tol": 0.2},
                 graph_style={"error": "SEM", "show_cells": True}, kind="export")
    state3 = dict(state, **extra)
    params = {"tracker": "redraw-every-frame v2.3", "max_move_um": np.float64(3.0),
              "margin_px": np.int64(12), "size_tol": 0.2, "sigma_um": {"mito": 2.0},
              "area_step": [0.67, 1.5], "t0": 0}
    track3 = dict(track, rules=extra["rules"], params=params,
                  gate={"mito": {0: 7.5, 3: float("nan")}})
    sp = history.session_path(d, V22_ND2, "2026-10-29_18-00-00")
    t = time.perf_counter()
    got = save_session_file(sp, anchors, bg, shape, seg, state3, comps, track3)
    t_save = ms(t)
    check("a7 session file written at session_path (folder created)",
          got == sp and sp.exists() and sp.parent.name == "PeterPiper_sessions",
          f"{sp.name} {sp.stat().st_size / 1e6:.2f} MB in {t_save}")
    sess = raw_arrays(sp)
    diff = [k for k in orig if k not in ("state_json", "track_json")
            and (k not in sess or orig[k].dtype != sess[k].dtype
                 or not np.array_equal(orig[k], sess[k]))]
    check("a8 session file: every ROI / tracking / measurement array bit-identical",
          not diff and set(orig) == set(sess), f"differing: {diff[:5]}")
    st_back, comps_back = load_roi_state(sp)
    want = dict(state3, kind="session", comps=["mito"])
    want["exp"] = dict(want["exp"], um_per_px=0.1625, bit_depth=16)
    ck = st_back.pop("content_key", None)          # V2.5: the content hash is added
    check("a9 extra V2.3 state keys survive (kind forced to 'session'; V2.5 content key)",
          st_back == want and isinstance(ck, str) and len(ck) == 40,
          f"keys {sorted(set(st_back) - set(state))}")
    a2, bg2, shape2, seg2 = load_roi_file(sp)
    ok = (shape2 == shape and seg2 == seg and len(a2) == len(anchors)
          and all(same_roi(x, y) and x.include == y.include and x.source == y.source
                  for x, y in zip(a2, anchors))
          and same_roi(bg2, bg)
          and all(same_roi(x, y) for c in comps for x, y in zip(comps[c], comps_back[c])))
    check("a10 anchors, background and drawn ROIs identical after reload", ok)
    tr_back = load_roi_track(sp)
    same, why = same_track(track, tr_back)
    check("a11 every per-frame mask / bbox / outline and measurement identical", same, why)
    g = tr_back["gate"]["mito"]
    check("a12 rules / params / gate survive",
          tr_back["rules"] == extra["rules"]
          and tr_back["params"] == {**params, "max_move_um": 3.0, "margin_px": 12}
          and set(g) == {0, 3} and g[0] == 7.5 and np.isnan(g[3]),
          f"params={tr_back['params']}")
    # second save to the same path: replaced in place, no _2, no temp files left
    before = sha(sp)
    state4 = dict(state3, saved="2026-10-29T18:05:00")
    got2 = save_session_file(sp, anchors, bg, shape, seg, state4, comps, track3)
    files = sorted(p.name for p in sp.parent.iterdir())
    check("a13 saving the session twice replaces it (no _2, no temp file)",
          got2 == sp and files == [sp.name] and sha(sp) != before
          and read_summary(sp)["saved"] == "2026-10-29T18:05:00", f"folder: {files}")
    # refuses to replace a file that is not a session file
    victim = d / "resave_ROIs.npz"
    h = sha(victim)
    try:
        save_session_file(victim, anchors, bg, shape, seg, state3, comps, track3)
        refused = False
    except FileExistsError as exc:
        refused = True
        print("      message:", exc)
    check("a14 save_session_file refuses to replace a non-session ROI file",
          refused and sha(victim) == h)
    # a failed write leaves the old session file untouched
    h = sha(sp)
    try:
        with replace_own_file(sp) as stream:
            stream.write(b"half written")
            raise RuntimeError("simulated crash while writing")
    except RuntimeError:
        pass
    files = sorted(p.name for p in sp.parent.iterdir())
    check("a15 a crash while writing leaves the old session file intact, no temp left",
          sha(sp) == h and files == [sp.name], f"{files}")
    # a track with extras packed with numpy scalars etc. - V2.3 keys absent -> V2.2 identical
    return dict(anchors=anchors, bg=bg, shape=shape, seg=seg, state=state, comps=comps,
                track=track, sess=sp)


# =================================================================================
def section_b():
    print("\n=== b) read_summary (fast, no masks decoded) ===")
    d = W / "b"
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    v22 = d / "Export_2026-10-29_17-26-39" / Path(V22).name
    v22.parent.mkdir()
    shutil.copy2(V22, v22)
    v21 = d / Path(V21).name
    shutil.copy2(V21, v21)
    old = d / "ROInav_results" / Path(OLD16).name
    old.parent.mkdir()
    shutil.copy2(OLD16, old)
    garbage = fake_file(d / "garbage_ROIs.npz", 5000, 1)
    nozip = d / "notes_ROIs.npz"
    nozip.write_text("not an npz file", encoding="utf-8")
    other_npz = d / "other_ROIs.npz"
    np.savez_compressed(other_npz, x=np.arange(5))
    sess = W / "a" / "PeterPiper_sessions" / labdata.T("t12")

    opened = []
    real_open = zipfile.ZipFile.open
    real_unpack = np.unpackbits

    def spy_open(self, name, *a, **k):
        opened.append(name if isinstance(name, str) else name.filename)
        return real_open(self, name, *a, **k)

    def no_unpack(*a, **k):
        raise AssertionError("read_summary decoded a mask")

    zipfile.ZipFile.open, np.unpackbits = spy_open, no_unpack
    try:
        res = {}
        for label, p in [("V2.2", v22), ("V2.1(2.0)", v21), ("V1.6", old), ("garbage", garbage),
                         ("not-npz", nozip), ("npz w/o ROIs", other_npz), ("V2.3 session", sess)]:
            read_summary(p)                       # warm the OS cache once
            opened.clear()
            t = time.perf_counter()
            s = read_summary(p)
            res[label] = (s, ms(t), sorted(set(opened)))
    finally:
        zipfile.ZipFile.open, np.unpackbits = real_open, real_unpack

    for label, (s, tm, op) in res.items():
        brief = None if s is None else {k: s[k] for k in (
            "version", "saved", "nd2", "image_shape", "n_cells", "comps", "tracked",
            "n_timepoints", "rules", "kind", "t0", "prefix")}
        print(f"      {label:13s} {tm:>9s}  opened={op}\n        -> {brief}")
    s, tm, op = res["V2.2"]
    check("b1 V2.2 summary", s and s["version"] == "2.2"
          and s["nd2"] == labdata.T("t13")
          and s["image_shape"] == (2400, 2400) and s["n_cells"] == 10 and s["comps"] == ["mito"]
          and s["tracked"] and s["n_timepoints"] == 61 and s["kind"] == "export" and s["t0"] == 0
          and s["rules"] == ["Track mitochondria using GFP ONLY"]
          and s["track_shape"] == {"mito": (61, 10)}
          and s["prefix"] == labdata.T("t14"), tm)
    allowed = {"image_shape.npy", "n.npy", "seg_timepoint.npy", "state_json.npy"}
    check("b2 V2.2 summary reads only state / size / count / tracking-array headers",
          set(op) <= allowed | {"trk_mito_bbox.npy"}, f"{op}")
    s, tm, _ = res["V2.1(2.0)"]
    check("b3 V2.1-era (state version 2.0) summary", s and s["version"] == "2.0"
          and s["n_cells"] == 18 and s["comps"] == ["nucleus"] and not s["tracked"]
          and s["n_timepoints"] == 0 and s["t0"] == 18 and s["kind"] == "saved"
          and s["nd2"] == labdata.T("t15"), tm)
    s, tm, _ = res["V1.6"]
    check("b4 V1.6 (no state) summary", s and s["version"] == "" and s["n_cells"] == 69
          and s["comps"] == ["nucleus"] and not s["tracked"] and s["nd2"] == "" and s["t0"] == 3,
          tm)
    check("b5 garbage .npz / non-npz / npz without ROIs -> None",
          res["garbage"][0] is None and res["not-npz"][0] is None
          and res["npz w/o ROIs"][0] is None)
    s, tm, _ = res["V2.3 session"]
    check("b6 V2.3 session summary (saved time, rules text, kind)", s and s["kind"] == "session"
          and s["saved"] == "2026-10-29T18:05:00" and s["session_id"] == "2026-10-29_18-00-00"
          and s["version"] == peterpiper.__version__ and s["fingerprint"].get("quick") == "abc"
          and len(s["rules"]) == 1 and "GFP" in s["rules"][0] and "mCherry" in s["rules"][0],
          f"{tm} rules={s and s['rules']}")
    slow = [(k, v[1]) for k, v in res.items() if float(v[1].split()[0]) > 50]
    check("b7 every summary under 50 ms", not slow, f"{slow}")


# =================================================================================
def section_c():
    print("\n=== c) nd2_fingerprint / same_file ===")
    d = W / "c"
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    history._FP_CACHE.clear()
    t = time.perf_counter()
    fp1 = history.nd2_fingerprint(BIG_ND2)
    t_first = ms(t)
    history._FP_CACHE.clear()
    t = time.perf_counter()
    fp2 = history.nd2_fingerprint(BIG_ND2)
    t_warm = time.perf_counter() - t
    t = time.perf_counter()
    history.nd2_fingerprint(BIG_ND2)
    t_cached = ms(t)
    check("c1 4.2 GB .nd2 fingerprint well under 1 s warm",
          fp1 == fp2 and fp1["quick"] and fp1["size"] == os.path.getsize(BIG_ND2) and t_warm < 0.5,
          f"first {t_first}, warm (OS cache) {t_warm * 1000:.1f} ms, cached {t_cached}; {fp1}")
    small = fake_file(d / "small.nd2", 1000, 2)
    mid = fake_file(d / "mid.nd2", 6 * 2**20, 3)
    big = fake_file(d / "big.nd2", 20 * 2**20, 4)
    for p in (small, mid, big):
        cp = d / ("renamed_" + p.name)
        shutil.copy2(p, cp)
        check(f"c2 same_file true for a renamed copy ({p.name}, {p.stat().st_size} B)",
              history.same_file(history.nd2_fingerprint(p), history.nd2_fingerprint(cp)))
    other = fake_file(d / "other.nd2", 6 * 2**20, 5)
    check("c3 same_file false for a different file of the same size",
          not history.same_file(history.nd2_fingerprint(mid), history.nd2_fingerprint(other)))
    ed = d / "edited_head.nd2"
    b = bytearray(big.read_bytes())
    b[100] ^= 1
    ed.write_bytes(bytes(b))
    check("c4 one byte changed in the first 4 MiB -> different",
          not history.same_file(history.nd2_fingerprint(big), history.nd2_fingerprint(ed)))
    ed2 = d / "edited_tail.nd2"
    b = bytearray(big.read_bytes())
    b[-10] ^= 1
    ed2.write_bytes(bytes(b))
    check("c5 one byte changed in the last 4 MiB -> different",
          not history.same_file(history.nd2_fingerprint(big), history.nd2_fingerprint(ed2)))
    ed3 = d / "edited_middle.nd2"
    b = bytearray(big.read_bytes())
    b[10 * 2**20] ^= 1
    ed3.write_bytes(bytes(b))
    print("      (by design the quick hash does not read the middle of large files: a change "
          "at 10 MiB of 20 MiB is",
          "NOT seen)" if history.same_file(history.nd2_fingerprint(big),
                                          history.nd2_fingerprint(ed3)) else "seen)")
    missing = history.nd2_fingerprint(d / "nope.nd2")
    check("c6 missing file -> quick '' and never the same as anything",
          missing["quick"] == "" and not history.same_file(missing, missing), f"{missing}")
    check("c7 same_file tolerates None / junk", not history.same_file(None, fp1)
          and not history.same_file({"quick": 1}, "x") and not history.same_file({}, {}))


# =================================================================================
def section_d(a):
    print("\n=== d) find_previous_runs ===")
    set_home("home_d")
    d = W / "d" / "data"
    shutil.rmtree(W / "d", ignore_errors=True)
    d.mkdir(parents=True)
    nd2a = fake_file(d / "expA.nd2", 6 * 2**20, 10)
    nd2b = fake_file(d / "expB.nd2", 6 * 2**20, 11)
    fpa, fpb = history.nd2_fingerprint(nd2a), history.nd2_fingerprint(nd2b)
    out = d / "OUTPUT_expA"
    A = {"nd2": "expA.nd2"}
    f = {}
    f["export_tracked"] = rewrite_npz(V22, out / "Export_2026-10-29_17-26-39" / "expA_ROIs.npz", A)
    set_mtime(f["export_tracked"], "2026-10-29T17:26:39")
    f["saved_untracked_tie"] = rewrite_npz(V21, out / "expA_ROIs.npz", A)
    set_mtime(f["saved_untracked_tie"], "2026-10-29T17:26:39")
    f["export_v21"] = rewrite_npz(V21, out / "Export_2026-10-23_13-21-28" / "expA_ROIs.npz", A)
    set_mtime(f["export_v21"], "2026-10-23T13:21:28")
    sp = history.session_path(out, nd2a, "2026-10-30_09-00-00")
    st = dict(a["state"], nd2="expA.nd2", nd2_path=str(nd2a), fingerprint=fpa,
              saved="2026-10-30T09:00:00", session_id="2026-10-30_09-00-00",
              version=peterpiper.__version__, app=peterpiper.APP_TITLE)
    f["session"] = save_session_file(sp, a["anchors"], a["bg"], a["shape"], a["seg"], st,
                                     a["comps"], a["track"])
    f["renamed"] = rewrite_npz(V22, out / "Export_2026-10-28_10-00-00" / "oldname_ROIs.npz",
                               {"nd2": "oldname.nd2", "fingerprint": fpa})
    set_mtime(f["renamed"], "2026-10-28T10:00:00")
    f["changed"] = rewrite_npz(V22, out / "Export_2026-10-27_10-00-00" / "expA_ROIs.npz",
                               {"nd2": "expA.nd2", "fingerprint": fpb})
    set_mtime(f["changed"], "2026-10-27T10:00:00")
    f["legacy_v16"] = rewrite_npz(OLD16, d / "ROInav_results" / "expA_ROIs.npz")
    set_mtime(f["legacy_v16"], "2026-10-19T06:20:00")
    f["v19_results"] = rewrite_npz(V21, d / "PD4navV1.9_results" / "expA_ROIs.npz", A)
    set_mtime(f["v19_results"], "2026-10-20T06:20:00")
    f["deep_ok"] = rewrite_npz(V21, out / "x1" / "x2" / "x3" / "x4" / "expA_ROIs.npz", A)
    set_mtime(f["deep_ok"], "2026-10-21T00:00:00")
    # must NOT be found
    rewrite_npz(V22, out / "Export_2026-10-29_11-00-00" / "expB_ROIs.npz", {"nd2": "expB.nd2"})
    rewrite_npz(V22, out / "Export_2026-10-29_12-00-00" / "expA_ROIs.npz", A,
                image_shape=(1024, 1024))
    rewrite_npz(V21, out / "x1" / "x2" / "x3" / "x4" / "x5" / "expA_ROIs.npz", A)   # too deep
    fake_file(d / "expA_ROIs.npz", 3000, 12)                                       # garbage
    rewrite_npz(OLD16, d / "ROInav_results" / "expB_ROIs.npz")         # v1.6, other name
    rewrite_npz(OLD16, d / "ROInav_results" / "expA_2_ROIs.npz")       # v1.6 for 'expA_2.nd2'
    rewrite_npz(V21, d / "OUTPUT_expB" / "expA_ROIs.npz", A)             # other OUTPUT_ folder

    T = 61
    t = time.perf_counter()
    runs = history.find_previous_runs(nd2a, out, (2400, 2400), n_timepoints=T)
    tm = ms(t)
    for r in runs:
        print(f"      {r.label()}   [{r.match}] {Path(r.path).relative_to(d)}"
              + (f"  NOTE: {r.note}" if r.note else ""))
    want = ["session", "export_tracked", "saved_untracked_tie", "renamed", "changed",
            "export_v21", "deep_ok", "v19_results", "legacy_v16"]
    got = []
    for r in runs:
        k = next((k for k, p in f.items() if Path(p).resolve() == Path(r.path).resolve()), r.path)
        got.append(k)
    check("d1 synthetic tree: right files, newest first, tracked before untracked at a tie",
          got == want, f"{tm}\n        got  {got}\n        want {want}")
    by = dict(zip(got, runs))
    check("d2 match kinds: fingerprint -> 'same file' / 'renamed copy', name -> 'same name'",
          by["session"].match == "same file" and by["renamed"].match == "renamed copy"
          and by["export_tracked"].match == "same name" and by["changed"].match == "same name"
          and "changed" in by["changed"].note and by["legacy_v16"].match == "same name",
          f"{[(k, r.match) for k, r in by.items()]}")
    lab = by["export_tracked"].label()
    check("d3 label text", lab == "29 Oct 2026 17:26 · PD4nav 2.2 · 10 cells · mitochondria · "
                                  "tracked ✓ · export", lab)
    runs2 = history.find_previous_runs(nd2a, out, (2400, 2400), n_timepoints=60)
    n_note = sum(1 for r in runs2 if "61 timepoints" in r.note)
    check("d4 a tracking length that differs from the movie is kept with a note",
          len(runs2) == len(runs) and n_note == 4, f"{n_note} notes")
    # results folder elsewhere (custom out_dir) + the nd2 folder still scanned
    custom = W / "d" / "custom_results"
    set_mtime(rewrite_npz(V22, custom / "Export_2026-10-31_08-00-00" / "expA_ROIs.npz", A),
              "2026-10-31T08:00:00")
    runs3 = history.find_previous_runs(nd2a, custom, (2400, 2400), T)
    check("d5 custom results folder is scanned as well as OUTPUT_<name>",
          len(runs3) == len(runs) + 1 and "custom_results" in runs3[0].path,
          f"{len(runs3)} runs; first {runs3[0].path if runs3 else None}")
    runs4 = history.find_previous_runs(nd2b, d / "OUTPUT_expB", (2400, 2400), T)
    # expB's own folders hold only the v1.6 legacy file named after it (OUTPUT_expA is
    # not expB's results folder, and OUTPUT_expB holds a file saved for expA)
    check("d6 expB sees only its own files",
          [Path(r.path).relative_to(d).as_posix() for r in runs4]
          == ["ROInav_results/expB_ROIs.npz"],
          f"{[Path(r.path).relative_to(d).as_posix() + ' ' + r.match for r in runs4]}")
    try:
        bad = history.find_previous_runs(W / "d" / "missing.nd2", None, None)
        bad2 = history.find_previous_runs(None, None, None)
        check("d7 never raises (missing nd2, None arguments)", isinstance(bad, list)
              and isinstance(bad2, list), f"{len(bad)} / {len(bad2)}")
    except Exception as exc:                                       # noqa: BLE001
        check("d7 never raises (missing nd2, None arguments)", False, repr(exc))

    print("\n    -- real read-only scans on D: --")
    snaps = {SAM_DIR: snapshot(SAM_DIR), MITO_DIR: snapshot(MITO_DIR)}
    for nd2p in (SAM_ND2, V22_ND2):
        shape, T = nd2_shape(nd2p)
        outd = Path(nd2p).parent / f"OUTPUT_{Path(nd2p).stem}"
        history._FP_CACHE.clear()
        t = time.perf_counter()
        rr = history.find_previous_runs(nd2p, outd, shape, T)
        t1 = time.perf_counter() - t
        t = time.perf_counter()
        rr2 = history.find_previous_runs(nd2p, outd, shape, T)
        t2 = time.perf_counter() - t
        print(f"      {Path(nd2p).name}: image {shape}, T={T}: {len(rr)} run(s), "
              f"first call {t1 * 1000:.0f} ms, again {t2 * 1000:.0f} ms")
        for r in rr:
            print(f"        {r.label()}  [{r.match}]  {r.path}" + (f"  NOTE: {r.note}" if r.note else ""))
            print(f"          rules: {r.rules}")
        check(f"d8 real scan {Path(nd2p).name}: finds runs, under 1 s",
              len(rr) >= 1 and t1 < 1.0 and [x.path for x in rr] == [x.path for x in rr2],
              f"{len(rr)} runs in {t1 * 1000:.0f} ms")
        if nd2p == V22_ND2:
            # (newer sessions the user saved later on that movie may come first)
            v22 = [x for x in rr if Path(x.path) == Path(V22)]
            check("d9 the user's V2.2 tracked export is offered, tracked, newest first",
                  bool(v22) and v22[0].tracked and v22[0].n_timepoints == T
                  and [x.saved for x in rr] == sorted((x.saved for x in rr), reverse=True),
                  v22[0].label() if v22 else "")
    same = all(snapshot(k) == v for k, v in snaps.items())
    check("d10 nothing written under D: (folders identical before / after)", same)


# =================================================================================
def section_e(a):
    print("\n=== e) run index: moved / renamed .nd2, pruning, corruption ===")
    home = set_home("home_e")
    shutil.rmtree(home, ignore_errors=True)
    home.mkdir()
    shutil.rmtree(W / "e", ignore_errors=True)
    e = W / "e"
    nd2 = fake_file(e / "orig" / "movie1.nd2", 6 * 2**20, 20)
    fp = history.nd2_fingerprint(nd2)
    st = dict(a["state"], nd2="movie1.nd2", nd2_path=str(nd2), fingerprint=fp,
              saved="2026-10-29T10:00:00", version=peterpiper.__version__, app=peterpiper.APP_TITLE)
    r1 = save_session_file(history.session_path(e / "out1", nd2, "2026-10-29_10-00-00"),
                           a["anchors"], a["bg"], a["shape"], a["seg"], st, a["comps"], a["track"])
    t = time.perf_counter()
    history.record_run(nd2, r1)
    t_rec = ms(t)
    idx = json.loads((home / "run_history.json").read_text(encoding="utf-8"))
    check("e1 record_run writes run_history.json keyed by fingerprint",
          list(idx) == [fp["quick"]] and idx[fp["quick"]]["nd2_name"] == "movie1.nd2"
          and [Path(r["path"]).name for r in idx[fp["quick"]]["runs"]] == [r1.name], t_rec)
    moved = e / "elsewhere" / "renamed_movie.nd2"
    moved.parent.mkdir(parents=True)
    os.replace(nd2, moved)
    runs = history.find_previous_runs(moved, moved.parent / "OUTPUT_renamed_movie",
                                      (2400, 2400), 61)
    check("e2 moved + renamed .nd2: the earlier run is found through the index",
          len(runs) == 1 and Path(runs[0].path) == r1 and runs[0].match == "renamed copy"
          and runs[0].tracked, runs[0].label() if runs else "nothing found")
    st2 = dict(st, saved="2026-10-29T11:00:00", kind="export")
    r2 = save_roi_file(e / "out2" / "Export_2026-10-29_11-00-00" / "movie1_ROIs.npz",
                       a["anchors"], a["bg"], a["shape"], a["seg"], st2, a["comps"], a["track"])
    history.record_run(moved, r2)
    r1.unlink()                                       # the user deleted the first run
    st3 = dict(st, saved="2026-10-29T12:00:00", kind="saved")
    r3 = save_roi_file(e / "out3" / "movie1_ROIs.npz", a["anchors"], a["bg"], a["shape"],
                       a["seg"], st3, a["comps"], None)
    history.record_run(moved, r3)
    ent = json.loads((home / "run_history.json").read_text(encoding="utf-8"))[fp["quick"]]
    names = [Path(r["path"]).parent.name + "/" + Path(r["path"]).name for r in ent["runs"]]
    # V3.0 portable profiles: a run missing here is KEPT (it may be on another
    # computer) - never offered, listed as missing ('My data is in...' finds it)
    check("e3 a missing run is kept (not offered), both .nd2 paths remembered",
          names == ["PeterPiper_sessions/movie1_session_2026-10-29_10-00-00.npz",
                    "Export_2026-10-29_11-00-00/movie1_ROIs.npz", "out3/movie1_ROIs.npz"]
          and len(ent["paths"]) == 2
          and str(r1) not in [r["path"] for r in history.indexed_runs()]
          and any(Path(m["path"]).name == r1.name for m in history.missing_runs()),
          f"{names} paths={ent['paths']}")
    runs = history.find_previous_runs(moved, None, (2400, 2400), 61)
    check("e4 lookup after pruning: newest first, tracked flag right",
          [Path(r.path) for r in runs] == [r3, r2] and [r.tracked for r in runs] == [False, True],
          f"{[r.label() for r in runs]}")
    history.record_run(moved, r3)
    ent = json.loads((home / "run_history.json").read_text(encoding="utf-8"))[fp["quick"]]
    check("e5 recording the same file again does not duplicate it", len(ent["runs"]) == 3)
    # corruption
    (home / "run_history.json").write_text("{this is not json", encoding="utf-8")
    try:
        runs = history.find_previous_runs(moved, None, (2400, 2400), 61)
        ok = runs == []
    except Exception as exc:                                       # noqa: BLE001
        ok, runs = False, repr(exc)
    check("e6 corrupt run_history.json: no error, set aside as run_history.corrupt.json",
          ok and (home / "run_history.corrupt.json").exists(), f"{runs}")
    history.record_run(moved, r2)
    ent = json.loads((home / "run_history.json").read_text(encoding="utf-8"))
    check("e7 next record_run starts a fresh valid index", list(ent) == [fp["quick"]])
    (home / "run_history.json").write_text(json.dumps(
        {fp["quick"]: {"runs": "oops", "paths": 3}, "x": 5, "y": {"runs": [1, {"path": 2}]}}),
        encoding="utf-8")
    try:
        runs = history.find_previous_runs(moved, None, (2400, 2400), 61)
        history.record_run(moved, r2)
        ent = json.loads((home / "run_history.json").read_text(encoding="utf-8"))
        ok = runs == [] and [Path(r["path"]) for r in ent[fp["quick"]]["runs"]] == [r2]
    except Exception as exc:                                       # noqa: BLE001
        ok = False
        print("     ", repr(exc))
    check("e8 index with wrong-typed entries is tolerated and repaired", ok)
    try:
        history.record_run(moved, e / "missing.npz")
        history.record_run(None, r2)
        history.record_run(e / "gone.nd2", r2, {"fingerprint": fp})
        ok = True
    except Exception as exc:                                       # noqa: BLE001
        ok = False
        print("     ", repr(exc))
    check("e9 record_run never raises (missing run / nd2)", ok)
    # V2.4 (L4): an index that exists but cannot be read is never overwritten
    ip = home / "run_history.json"
    before = ip.read_bytes()
    real_read = Path.read_text

    def locked_read(self, *a, **k):
        if self.name == "run_history.json":
            raise PermissionError(13, "locked by another program")
        return real_read(self, *a, **k)
    Path.read_text = locked_read
    try:
        history.record_run(moved, r3)
    finally:
        Path.read_text = real_read
    check("e9b unreadable (not missing) index: record_run leaves it untouched (L4)",
          ip.read_bytes() == before and not (home / "run_history.lock").exists())
    # two PeterPiper windows / processes recording at once: no run is lost
    import threading
    extra = []
    for i in range(12):
        q = e / "par" / f"run{i:02d}_ROIs.npz"
        q.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(r2, q)
        extra.append(q)
    ths = [threading.Thread(target=lambda part=part: [history.record_run(moved, q) for q in part])
           for part in (extra[0::2], extra[1::2])]
    for th in ths:
        th.start()
    for th in ths:
        th.join()
    ent = json.loads(ip.read_text(encoding="utf-8"))[fp["quick"]]
    got = {Path(r["path"]).name for r in ent["runs"]}
    check("e9c two writers at once: every run kept (re-read + merge under a lock, L4)",
          all(q.name in got for q in extra) and not (home / "run_history.lock").exists(),
          f"{len(got)} runs")
    left = [p.name for p in home.iterdir() if p.suffix == ".tmp"]
    check("e10 no temporary files left in the settings folder", not left, f"{left}")
    from peterpiper.config import _settings_file
    check("e11 home_dir() == the config settings folder ($PETERPIPER_HOME here)",
          history.home_dir() == home == _settings_file().parent, str(history.home_dir()))


# =================================================================================
def section_f(a):
    print("\n=== f) track_problem + an unchanged V2.2 roifile reading a V2.3 session file ===")
    tr = a["track"]
    check("f1 V2.2 track fits its movie", track_problem(tr, 61, 10, ["mito"],
                                                        channels=["GFP", "ExRai", "mCherry"]) is None)
    msgs = {
        "no tracking, V2.0 file": track_problem(None, 61, 10, ["mito"], {"version": "2.0"}),
        "no tracking, V2.1 file": track_problem(None, 61, 10, None, {"version": "2.1"}),
        "no tracking, no state": track_problem(None, 61, 10),
        "no tracking, V2.2 saved early": track_problem(None, 61, 10, None, {"version": "2.2"}),
        "T differs": track_problem(tr, 60, 10, ["mito"]),
        "N differs": track_problem(tr, 61, 12, ["mito"]),
        "comp not followed": track_problem(tr, 61, 10, ["nucleus"]),
        "channel count": track_problem(tr, 61, 10, ["mito"], channels=["GFP", "ExRai"]),
        "empty": track_problem(dict(tr, rois={}, meas={}), 61, 10),
    }
    for k, v in msgs.items():
        print(f"      {k:30s}: {v}")
    check("f2 every mismatch gives a plain reason", all(msgs.values())
          and "V2.0" in msgs["no tracking, V2.0 file"]
          and "before tracking was saved" in msgs["no tracking, V2.1 file"]
          and "before TRACK & MEASURE" in msgs["no tracking, V2.2 saved early"]
          and "61 timepoints" in msgs["T differs"] and "12 cells" in msgs["N differs"]
          and "mitochondria" in msgs["comp not followed"] and "3 channels" in msgs["channel count"])
    # the V2.2 baseline roifile.py (unchanged code from git) reads a V2.3 session file
    import subprocess
    import pd4nav_history                           # PD4nav's history (PeterPiper's earlier name)
    old_src = pd4nav_history.show("8e31298", "roifile.py").decode("utf-8")
    old_path = W / "roifile_v22.py"
    old_path.write_text(old_src, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("peterpiper._roifile_v22", old_path)
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    sp = a["sess"]
    try:
        anchors, bg, shape, seg = old.load_roi_file(sp)
        state, comps = old.load_roi_state(sp)
        track = old.load_roi_track(sp)
        same, why = same_track(a["track"], track)
        ok = same and len(anchors) == len(a["anchors"]) and state["v2"] and "mito" in comps
    except Exception as exc:                                       # noqa: BLE001
        ok, why = False, repr(exc)
    check("f3 V2.2 code reads the V2.3 session file (ROIs + tracking identical)", ok, why)


# =================================================================================
def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # labels use · and ✓
    except (AttributeError, ValueError):
        pass
    W.mkdir(parents=True, exist_ok=True)
    print(f"python {sys.version.split()[0]}, numpy {np.__version__}, peterpiper {peterpiper.__version__}")
    print(f"work folder {W}")
    home0 = set_home("home_a")
    a = section_a()
    section_b()
    section_c()
    section_d(a)
    section_e(a)
    section_f(a)
    del home0
    n_fail = sum(1 for _, ok in RESULTS if not ok)
    print(f"\n{len(RESULTS) - n_fail}/{len(RESULTS)} PASS" + (f", {n_fail} FAIL" if n_fail else ""))
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
