"""
Developer test (not shipped): peterpiper.rules and the qc.py rule helpers on
synthetic images - fast, no .nd2 needed.

    PETERPIPER_HOME=<scratch>/_home MPLBACKEND=Agg python dev_tests/test_rules_unit.py
Exit code 0 = every check passed.
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from peterpiper import manual as MN                               # noqa: E402
from peterpiper import qc as QC                                   # noqa: E402
from peterpiper import rules as RL                                # noqa: E402
from peterpiper.config import Experiment, Settings                # noqa: E402
from peterpiper.measure import Measurements                       # noqa: E402
from peterpiper.segment import Roi                                # noqa: E402

checks = []


def ok(name, cond, extra=""):
    checks.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra else ""), flush=True)


CH = ["GFP", "ExRai", "mCherry"]

# ---------------------------------------------------------------- TrackRule
r = RL.TrackRule("cell", 2, "with", 0)
ok("text WITH", r.text(CH) == "Track whole cell using mCherry WITH intensity in GFP", r.text(CH))
ok("text ONLY", RL.TrackRule("nucleus", 0).text(CH) == "Track nucleus using GFP ONLY")
ok("text AND / IF", RL.TrackRule("mito", 0, "and", 1).text(CH).endswith("GFP AND intensity in ExRai")
   and RL.TrackRule("mito", 0, "if", 1).text(CH).endswith("GFP IF intensity in ExRai"))
ok("effective_mode: B missing or B == A -> only",
   RL.TrackRule("cell", 1, "with").effective_mode() == "only"
   and RL.TrackRule("cell", 1, "and", 1).effective_mode() == "only"
   and RL.TrackRule("cell", 1, "IF", 0).effective_mode() == "if"
   and RL.TrackRule("cell", 1, "bogus", 0).effective_mode() == "only")
d = r.to_dict(CH)
ok("to_dict uses names", d == {"comp": "cell", "a": "mCherry", "mode": "with", "b": "GFP"}, d)
ok("to_dict ONLY has b ''", RL.TrackRule("nucleus", 1, "with", 1).to_dict(CH)
   == {"comp": "nucleus", "a": "ExRai", "mode": "only", "b": ""})
ok("json round trip", RL.TrackRule.from_dict(json.loads(json.dumps(d)), CH) == r)
ok("from_dict: other channel order keeps the meaning",
   RL.TrackRule.from_dict(d, ["mCherry", "GFP", "ExRai"]) == RL.TrackRule("cell", 0, "with", 1))
ok("from_dict: ints, case-insensitive names, upper-case mode",
   RL.TrackRule.from_dict({"comp": "mito", "a": 0, "mode": "AND", "b": "exrai"}, CH)
   == RL.TrackRule("mito", 0, "and", 1))
ok("from_dict invalid -> None",
   RL.TrackRule.from_dict({"comp": "x", "a": "GFP"}, CH) is None
   and RL.TrackRule.from_dict({"comp": "cell", "a": "Cy5"}, CH) is None
   and RL.TrackRule.from_dict({"comp": "cell", "a": 7}, CH) is None
   and RL.TrackRule.from_dict({"comp": "cell", "a": "GFP", "mode": "or"}, CH) is None
   and RL.TrackRule.from_dict({"comp": "cell", "a": "GFP", "mode": "with", "b": "Cy5"}, CH) is None
   and RL.TrackRule.from_dict("nonsense", CH) is None)
ok("from_dict: mode WITH without B is valid (applied as ONLY)",
   RL.TrackRule.from_dict({"comp": "cell", "a": "GFP", "mode": "with", "b": ""}, CH).effective_mode()
   == "only")
ok("MODES / labels / help complete", set(RL.MODES) == set(RL.MODE_LABELS) == set(RL.MODE_HELP))

# ---------------------------------------------------------------- default_rules


def roi(ch):
    x = Roi((0, 0, 2, 2), np.ones((2, 2), bool), "nucleus")
    if ch is not None:
        x.channel = ch
    return x


cells = [{"nucleus": roi(2), "mito": roi(0)}, {"nucleus": roi(2)}, {"nucleus": roi(1), "mito": roi(None)}]
rows = [["mito", ["ExRai", "GFP"]], ["nucleus", ["GFP"]], ["cell", "mCherry; GFP"], ["mito", ["GFP"]]]
dr = RL.default_rules(rows, cells, CH)
ok("default_rules: row order, most common channel, first follow channel, dedupe",
   [(x.comp, x.a, x.effective_mode()) for x in dr] == [("mito", 0, "only"), ("nucleus", 2, "only"),
                                                         ("cell", 2, "only")],
   [(x.comp, x.a) for x in dr])
tie = RL.default_rules([["nucleus", []]], [{"nucleus": roi(2)}, {"nucleus": roi(1)}], CH)
ok("default_rules: ties -> lower channel; no rows -> drawn compartments",
   tie[0].a == 1 and [x.comp for x in RL.default_rules([], cells, CH)] == ["nucleus", "mito"])
cr = RL.complete_rules({"nucleus": {"comp": "nucleus", "a": "ExRai", "mode": "if", "b": "GFP"},
                        "mito": RL.TrackRule("mito", 9)}, cells, ["nucleus", "mito"], CH)
ok("complete_rules: dict accepted, out-of-range rule replaced by default",
   cr["nucleus"] == RL.TrackRule("nucleus", 1, "if", 0) and cr["mito"] == RL.TrackRule("mito", 0))

# ---------------------------------------------------------------- norm / guide
rng = np.random.default_rng(1)
H = W = 256
yy, xx = np.mgrid[:H, :W]
blob = ((yy - 128) ** 2 + (xx - 100) ** 2 < 30 ** 2)
A = (100 + rng.normal(0, 5, (H, W)) + 900 * blob).clip(0).astype(np.uint16)
B = (300 + rng.normal(0, 20, (H, W)) + 4000 * ((yy - 128) ** 2 + (xx - 160) ** 2 < 12 ** 2)).clip(0).astype(np.uint16)
stack = np.stack([A, B])
norm = RL.make_norm(stack)
ok("make_norm noise == manual._plane_noise",
   all(abs(norm.noise[c] - MN._plane_noise(stack[c])) < 1e-9 for c in range(2)),
   f"{norm.noise} vs {[MN._plane_noise(stack[c]) for c in range(2)]}")
ok("make_norm bg / top sensible (20th / 99.5th percentile)", 93 < norm.bg[0] < 100 and 900 < norm.top[0] < 1100
   and 275 < norm.bg[1] < 295 and norm.top[1] > 3000, f"bg {norm.bg} top {norm.top}")
flat = RL.make_norm(np.full((1, 64, 64), 7, np.uint16))
ok("make_norm guard: flat channel top > bg", flat.top[0] > flat.bg[0], f"{flat.bg} {flat.top}")
g_only = RL.guide_plane(stack, RL.TrackRule("cell", 0), norm)
ok("ONLY guide is the raw plane itself", g_only.dtype == np.uint16 and np.shares_memory(g_only, stack)
   and np.array_equal(g_only, A))
ok("AND / IF guide is the raw plane A", np.array_equal(RL.guide_plane(stack, RL.TrackRule("cell", 0, "and", 1), norm), A)
   and np.array_equal(RL.guide_plane(stack, RL.TrackRule("cell", 0, "if", 1), norm), A))
rw = RL.TrackRule("cell", 0, "with", 1)
g = RL.guide_plane(stack, rw, norm)
za = (A.astype(np.float64) - norm.bg[0]) / (norm.top[0] - norm.bg[0])
zb = (B.astype(np.float64) - norm.bg[1]) / (norm.top[1] - norm.bg[1])
ref = norm.bg[0] + (norm.top[0] - norm.bg[0]) * (za + zb) / 2
ok("WITH guide = contract formula, float32", g.dtype == np.float32 and np.allclose(g, ref, rtol=1e-5, atol=1e-2),
   f"max |diff| {np.abs(g - ref).max():.4f}")
ok("WITH guide: both blobs visible, background at bgA",
   g[128, 100] > norm.bg[0] + 300 and g[128, 160] > norm.bg[0] + 300 and abs(np.median(g) - norm.bg[0]) < 20,
   f"A blob {g[128, 100]:.0f} B blob {g[128, 160]:.0f} median {np.median(g):.0f}")
box = (100, 80, 150, 190)
ok("guide box crop", np.array_equal(RL.guide_plane(stack, rw, norm, box), g[100:150, 80:190]))
ok("guide_key shares raw planes", RL.guide_key(RL.TrackRule("cell", 0), 2) == RL.guide_key(RL.TrackRule("mito", 0, "and", 1), 2)
   != RL.guide_key(rw, 2))

# ---------------------------------------------------------------- AND / IF
cell = Roi((90, 60, 167, 200), np.ones((77, 140), bool), "cell")      # covers both blobs
ra = RL.TrackRule("cell", 0, "and", 1)
keep = RL.overlap_mask(stack, cell, ra, norm, 0.325, 3.0)
ok("overlap_mask: bbox-local, subset, keeps the B blob only",
   keep.shape == cell.mask.shape and not (keep & ~cell.mask).any()
   and keep[128 - 90, 160 - 60] and not keep[128 - 90, 100 - 60], f"kept {keep.mean():.2f}")
cell.channel = 0
ad = RL.apply_and(cell, stack, ra, norm, 0.325, 3.0)
ok("apply_and: mask = kept pixels, outline = region, channel kept, original untouched",
   np.array_equal(ad.mask, keep) and np.array_equal(ad.outline, cell.mask) and ad.channel == 0
   and cell.mask.all() and ad.bbox == cell.bbox)
ok("apply_and with a non-AND rule returns the ROI", RL.apply_and(cell, stack, rw, norm, 0.325, 3.0) is cell)
ri = RL.TrackRule("nucleus", 0, "if", 1)
on_b = Roi((113, 145, 143, 175), (((np.mgrid[:30, :30] - 15) ** 2).sum(0) < 100), "nucleus")
off_b = Roi((113, 85, 143, 115), on_b.mask.copy(), "nucleus")
s_on, s_off = RL.gate_snr(stack, on_b, ri, 0.325, norm), RL.gate_snr(stack, off_b, ri, 0.325)
ok("gate_snr: high on B signal, low off it; = manual._snr", s_on > 50 and s_off < 5
   and abs(s_off - MN._snr(B, off_b, 0.325)) < 1e-9, f"on {s_on:.1f} off {s_off:.2f}")
ok("gate_snr without B -> NaN", np.isnan(RL.gate_snr(stack, on_b, RL.TrackRule("nucleus", 0), 0.325)))

# ---------------------------------------------------------------- qc helpers
ok("gate_reason text", QC.gate_reason("GFP", 1.234, 5.0) == "no GFP signal (IF gate: SNR 1.2 < 5)"
   and QC.gate_reason("GFP", 7.0, 5.0) is None
   and QC.gate_reason("GFP", float("nan"), 5.0) == "no GFP signal (IF gate: SNR not measurable < 5)")
T, N = 8, 3
mean = np.zeros((T, 3, N))
mean[:, 0, :] = 500.0                   # channel 0 (tracked) bright
mean[:, 1, :] = 90.0                    # channel 1 at background everywhere
mean[:, 2, :] = 300.0
mean[:, :, 2] = np.nan                  # cell 2: never measured (all-NaN)
M = Measurements(mean=mean, background=np.full((T, 3), 100.0), area_px=np.full((T, N), 50),
                 n_saturated=np.zeros((T, 3, N), int), quality=np.ones((T, N)), channels=CH,
                 background_sd=np.full((T, 3), 5.0))
M.area_px[:, 2] = 0
exp = Experiment(channels=CH, n_timepoints=T, width=100, height=100)
s = Settings()
seeds = [Roi((0, 0, 1, 1), np.ones((1, 1), bool), "nucleus", source="manual") for _ in range(N)]
with warnings.catch_warnings(record=True) as wl:
    warnings.simplefilter("always")
    old = QC.run_qc(M, exp, s, None, seeds)
    new = QC.run_qc(M, exp, s, None, seeds, rule=RL.TrackRule("nucleus", 0))
    newd = QC.run_qc(M, exp, s, None, seeds, rule={"comp": "nucleus", "a": "GFP", "mode": "only", "b": ""})
    gated = QC.run_qc(M, exp, s, None, seeds, rule=RL.TrackRule("nucleus", 0, "if", 2),
                      gate={0: 12.0, 1: 0.4})
nanw = [str(w.message) for w in wl if "All-NaN" in str(w.message) or "empty slice" in str(w.message)]
ok("no 'All-NaN slice' warnings from QC", not nanw, f"{len(nanw)} warnings")
ok("old behaviour: every channel tested (ExRai at background is a reason)",
   any("at or below background in ExRai" in x for x in old[0].reasons), old[0].reasons)
ok("with a rule: only the rule's channels (no ExRai reason)", new[0].reasons == [] and newd[0].reasons == [],
   f"{new[0].reasons} / {newd[0].reasons}")
ok("IF gate: failing cell excluded with the text, even though drawn by hand",
   (not gated[1].passed) and gated[1].reasons[0] == "no mCherry signal (IF gate: SNR 0.4 < 5)"
   and "drawn by hand, so kept" not in gated[1].reasons and gated[0].passed,
   f"{gated[1].reasons}")
ok("IF rule checks A and B at background (B = mCherry fine here)", gated[0].reasons == [], gated[0].reasons)
ok("summarise counts the gate reason", "no mCherry signal" in QC.summarise(gated, [0, 1]),
   QC.summarise(gated, [0, 1]))

# ---------------------------------------------------------------- params
p = MN.track_params(["nucleus", "mito"], 0.325, 3.0, 9, 0.25, 3.0, 5.0, 3.0, 4, norm, ["A", "B"])
need = {"tracker", "max_move_um", "margin_px", "size_tol", "first_frame_tol", "area_step", "sigma_um",
        "ring_um", "edge_level_clip", "phase_upsample", "mito_k", "gate_snr", "overlap_k", "t0", "norm"}
ok("track_params has every contract key, JSON-ready", need <= set(p) and "_note" in p
   and json.loads(json.dumps(p)) == p and p["first_frame_tol"] == 0.10 and p["area_step"] == [0.67, 1.5]
   and p["edge_level_clip"] == [0.12, 0.8] and p["phase_upsample"] == 10 and p["ring_um"] == 4.0
   and p["sigma_um"] == {"nucleus": 0.6, "mito": 2.0} and set(p["norm"]) == {"A", "B"},
   sorted(set(p) - need))

bad = [n for n, c in checks if not c]
print(f"\n{len(checks) - len(bad)}/{len(checks)} passed" + (f"; FAILED: {bad}" if bad else ""))
sys.exit(1 if bad else 0)
