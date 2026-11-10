"""
Developer test for v2.3 provenance (provenance.py, excel.py Settings + Methods
sheets, prism.py Info notes).

Run from anywhere (uses the repo's app/ folder, writes only under <repo>/_home;
reads the lab's real files on D: READ-ONLY, after copying the ROI file):

    python dev_tests/test_provenance.py            # synthetic + real data
    python dev_tests/test_provenance.py --no-real  # synthetic only

Sections
  a) provenance.py: software_versions, PARAM_DOCS coverage, parameter_table,
     methods_text mentions every value it is given
  b) workbook (synthetic, with and without provenance): every reference to the
     Settings sheet (formulas, named cells, the dropdown list) points at a cell
     holding the right value; the Methods sheet is complete; no text that begins
     with "=" became a formula; every sheet except the record part of Settings and
     the new Methods sheet is identical to the V2.2 code's workbook (excel.py of
     commit 8e31298, run side by side)
  c) .pzfx: parses with xml.etree, same tables as the V2.2 code, provenance note
  d) real data: the user's V2.2 mito run (ROI file with tracking, copied) and
     the .nd2's real metadata -> workbook + .pzfx, same checks
Prints PASS / FAIL lines; exit code 1 on failure.
"""
from __future__ import annotations

import labdata  # noqa: E402  (lab file names: dev_tests/lab_paths.json, never uploaded)

import hashlib
import os
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
W = REPO / "_home" / "provenance_test"
os.environ.setdefault("PETERPIPER_HOME", str(REPO / "_home"))
os.environ.setdefault("MPLBACKEND", "Agg")
sys.path.insert(0, str(REPO / "app"))
try:
    sys.stdout.reconfigure(encoding="utf-8")       # µ, σ, × in the printed methods text
except Exception:                                  # noqa: BLE001
    pass

import numpy as np                                                    # noqa: E402

import peterpiper                                                         # noqa: E402
from peterpiper import provenance as P                                    # noqa: E402
from peterpiper.config import Experiment, Settings                        # noqa: E402
from peterpiper.excel import write_workbook, build_roi_info               # noqa: E402
from peterpiper.measure import Measurements                               # noqa: E402
from peterpiper.prism import write_pzfx                                   # noqa: E402
from peterpiper.qc import CellQC                                          # noqa: E402

BASE_COMMIT = "8e31298"
REAL_ND2 = Path(labdata.T("t06"))
REAL_ROI = (REAL_ND2.parent / labdata.T("t18") /
            "Export_2026-10-29_17-26-39" / labdata.T("t19"))

RESULTS = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, bool(ok)))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  - {detail}" if detail else ""))
    return bool(ok)


# --------------------------------------------------------------------------
#  The V2.2 code (excel.py, prism.py of the baseline commit), side by side
# --------------------------------------------------------------------------
def v22_package():
    """roinav_v22: a copy of app/peterpiper with excel.py and prism.py from the
    baseline commit. None if git cannot give them."""
    dst = W / "v22" / "roinav_v22"
    shutil.copytree(REPO / "app" / "peterpiper", dst,
                    ignore=shutil.ignore_patterns("__pycache__", "gui", "templates"))
    shutil.copytree(REPO / "app" / "peterpiper" / "templates", dst / "templates")
    import pd4nav_history                           # PD4nav's history (PeterPiper's earlier name)
    for f in ("excel.py", "prism.py"):
        try:
            (dst / f).write_bytes(pd4nav_history.show(BASE_COMMIT, f))
        except Exception:                                          # noqa: BLE001
            return None
    sys.path.insert(0, str(W / "v22"))
    import roinav_v22.excel as ex22                                   # noqa: E402
    import roinav_v22.prism as pr22                                   # noqa: E402
    return ex22, pr22


# --------------------------------------------------------------------------
#  Synthetic inputs (with text that begins with "=" wherever text goes)
# --------------------------------------------------------------------------
CHANNELS = ["GFP", "ExRai", "mCherry"]
TRACK_PARAMS = {
    "tracker": "redraw-every-frame v2.3", "t0": 1, "max_move_um": 4.5, "margin_px": 28,
    "size_tol": 0.3, "first_frame_tol": 0.1, "area_step": [0.6, 1.6],
    "sigma_um": {"cell": 1.1, "mito": 1.7}, "ring_um": 5.0, "edge_level_clip": [0.11, 0.85],
    "phase_upsample": 20, "mito_k": 2.5, "gate_snr": 6.5, "overlap_k": 2.75,
    "norm": {"mCherry": {"bg": 101.0, "top": 2301.5, "noise": 7.25},
             "GFP": {"bg": 88.0, "top": 1500.0, "noise": 5.5}},
    "redraw_every": 1, "_note": {"redraw_every": "Redraw every this many timepoints."},
}
RULES = [{"comp": "cell", "a": "mCherry", "mode": "with", "b": "GFP"},
         {"comp": "mito", "a": "GFP", "mode": "and", "b": "ExRai"},
         {"comp": "nucleus", "a": "GFP", "mode": "if", "b": "ExRai"}]
FINGERPRINT = {"name": "=evil movie.nd2", "size": 2109276160, "mtime": 1761600000.0,
               "quick": "=SUM(9)deadbeef0123456789"}


def synthetic(T: int = 12, N: int = 5, seed: int = 1):
    rng = np.random.default_rng(seed)
    C = len(CHANNELS)
    exp = Experiment(nd2_path="C:/data/=evil movie.nd2", out_dir=str(W), channels=list(CHANNELS),
                     n_timepoints=T, width=512, height=512, um_per_px=0.1625,
                     seconds_per_frame=30.0, bit_depth=16, objective="=1+1")
    s = Settings()
    s.baseline_timepoint = 3
    s.seg_timepoint = 2
    s.roi_mode = "mito"
    s.resp_quantity = "F/F0 - GFP; R/R0 - GFP/ExRai"
    mean = 500 + 200 * rng.random((T, C, N))
    bg = 100 + rng.random((T, C))
    M = Measurements(mean=mean, background=bg, area_px=np.full((T, N), 400.0),
                     n_saturated=np.zeros((T, C, N)), quality=np.ones((T, N)),
                     channels=list(CHANNELS), background_sd=np.full((T, C), 5.0), roi_mode="mito")
    qc = [CellQC(index=k, passed=(k != 1), reasons=(["=SUM(1,1)"] if k == 1 else []))
          for k in range(N)]
    include = {k: (0 if k == 2 else 1) for k in range(N)}
    why = {2: "=cmd|' /C calc'!A0"}
    return exp, s, M, qc, include, why


class _Seed:
    def __init__(self, cy, cx):
        self.centroid = (cy, cx)
        self.source = "manual"


# --------------------------------------------------------------------------
#  Workbook checks
# --------------------------------------------------------------------------
REF_RE = re.compile(r"Settings!\$?([A-Z]{1,3})\$?(\d+)(?::\$?([A-Z]{1,3})\$?(\d+))?")


def _formula(c):
    v = c.value
    if c.data_type == "f":
        return v.text if hasattr(v, "text") else str(v)
    return None


def settings_refs(wb):
    """{(col, row)} of every Settings cell referred to by a formula, a named
    cell or a data-validation list; plus the formulas that do so (for counts)."""
    refs, n = set(), 0

    def add(text):
        nonlocal n
        for m in REF_RE.finditer(text):
            n += 1
            c0, r0, c1, r1 = m.group(1), int(m.group(2)), m.group(3), m.group(4)
            if c1 is None:
                refs.add((c0, r0))
            else:
                assert c0 == c1, text
                for r in range(r0, int(r1) + 1):
                    refs.add((c0, r))
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                f = _formula(c)
                if f and "Settings!" in f:
                    add(f)
        for dv in ws.data_validations.dataValidation:
            add(str(dv.formula1 or ""))
    names = {}
    for name, dn in wb.defined_names.items():
        names[name] = dn.attr_text
        add(dn.attr_text)
    return refs, n, names


def check_workbook(tag: str, path: str, s: Settings, T: int, prov, versions, ref_wb=None,
                   expect_text=()):
    from openpyxl import load_workbook
    wb = load_workbook(path)
    st = wb["Settings"]
    b = int(s.baseline_timepoint)

    # 1) every reference to the Settings sheet points at the right value
    refs, n, names = settings_refs(wb)
    ok = True
    bad = []
    for col, row in sorted(refs):
        c = st[f"{col}{row}"]
        if (col, row) == ("B", 4):
            good = c.value == b and c.data_type == "n"
        elif (col, row) == ("B", 5):
            good = c.value == "=B4+1"
        elif (col, row) == ("B", 6):
            good = isinstance(c.value, str) and c.value.startswith("=(B4-1)*")
        elif col == "E" and 2 <= row <= T + 1:
            good = c.value == row - 1
        elif (col, row) == ("D", 4):              # V3.0: MinSNR (the ratio check)
            good = c.data_type == "n" and c.value == float(getattr(s, "ratio_min_snr", 5.0))
        else:
            good = False
        if not good:
            ok = False
            bad.append(f"{col}{row}={c.value!r}")
    ok = ok and names.get("BaselineTP") == "Settings!$B$4" \
        and names.get("BaselineRow") == "Settings!$B$5" and ("B", 4) in refs \
        and names.get("MinSNR") == "Settings!$D$4"
    check(f"{tag}: {n} references to Settings point at the right cells "
          f"({len(refs)} cells: B4 baseline={b}, B5, B6, E2:E{T + 1})", ok, "; ".join(bad[:5]))
    check(f"{tag}: Settings labels for the dropdown cells unchanged",
          str(st["A4"].value).startswith("Baseline timepoint") and "row" in str(st["A5"].value)
          and "time" in str(st["A6"].value))

    # 2) no literal text became a formula: formulas only where the code puts them
    stray = []
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                f = _formula(c)
                if f is None:
                    continue
                if ws.title in ("Methods", "ROI_info") or (
                        ws.title == "Settings" and c.coordinate not in ("B5", "B6")):
                    stray.append(f"{ws.title}!{c.coordinate}")
                elif any(x in f for x in ("evil", "1+1", "SUM(9)", "SUM(1,1)", "calc", "1+2")):
                    stray.append(f"{ws.title}!{c.coordinate}")
    check(f"{tag}: no text starting with '=' became a formula", not stray, ", ".join(stray[:5]))
    lit = {str(c.value) for ws in wb.worksheets for row in ws.iter_rows() for c in row
           if c.data_type == "s" and isinstance(c.value, str) and c.value.startswith("=")}
    for t in expect_text:
        check(f"{tag}: '{t}' kept as literal text", t in lit)

    # 3) Settings: values actually used, no legacy click-workflow-ignored fields
    a = {str(st.cell(row=r, column=1).value): st.cell(row=r, column=2).value
         for r in range(7, st.max_row + 1) if st.cell(row=r, column=1).value}
    legacy = [k for k in a if any(w in k for w in (
        "Reference channel (segmented)", "Threshold factor", "Core fraction", "Split touching",
        "Min solidity", "Auto-tune", "Tracking mode", "Min overlap to match", "Ring width",
        "Max movement per timepoint (px)", "Background box (um)"))]
    check(f"{tag}: Settings lists no legacy fields the click workflow ignores", not legacy,
          ", ".join(legacy))
    tp = P.track_parameters(s, None, (prov or {}).get("track_params"))[0]
    want = {"Baseline timepoint (F0, R0) (1-based)": b,
            "Largest movement between two timepoints (µm)": tp["max_move_um"],
            "Size may change by (± fraction of the drawn area)": tp["size_tol"],
            "Parameters recorded by the tracker": "yes" if prov and prov.get("track_params")
            else "no"}
    miss = [f"{k}: {a.get(k)!r} != {v!r}" for k, v in want.items() if a.get(k) != v]
    check(f"{tag}: Settings record holds the values used", not miss, "; ".join(miss))

    # 4) Methods sheet complete
    ok_m = "Methods" in wb.sheetnames
    if ok_m:
        ms = wb["Methods"]
        cells = [str(c.value) for row in ms.iter_rows() for c in row if c.value is not None]
        blob = "\n".join(cells)
        heads = ["METHODS TEXT", "REFERENCES", "PARAMETERS", "SOFTWARE", "DATA FILE AND ANALYSIS"]
        need = heads + ["Harris", "Virtanen", "van der Walt", "Hunter", "tlambert03",
                        "GraphPad", versions["numpy"], versions["openpyxl"], peterpiper.__version__,
                        "Analysis date", ".nd2 full path", "Quick fingerprint"]
        if prov and prov.get("fingerprint"):
            need.append(str(prov["fingerprint"]["quick"]))
        missing = [x for x in need if x not in blob]
        table = P.parameter_table(s, ref_wb["exp"], (prov or {}).get("track_params"), None,
                                  ref_wb["prov"])
        names_m = set(cells)
        miss_rows = [r[1] for r in table if r[1] not in names_m]
        ok_m = not missing and not miss_rows and wb.sheetnames[-1] == "Methods"
        check(f"{tag}: Methods sheet complete ({len(table)} parameters, {len(cells)} cells)",
              ok_m, f"missing {missing[:6]} rows {miss_rows[:4]}")
    else:
        check(f"{tag}: Methods sheet present", False)

    # 5) every other sheet identical to the V2.2 code's workbook
    if ref_wb and ref_wb.get("v22"):
        w22 = load_workbook(ref_wb["v22"])
        diffs, fixed, wrapped = [], [], [0]
        v25 = ("Area_px", "Area_um2")             # V2.5 adds these and Sum_<channel>
        if [x for x in w22.sheetnames] != [x for x in wb.sheetnames if x != "Methods"
                                           and x not in v25 and not x.startswith("Sum_")
                                           and not x.startswith("Noise_")]:   # V3.0
            diffs.append(f"sheets {w22.sheetnames} vs {wb.sheetnames}")
        for ws22 in w22.worksheets:
            if ws22.title not in wb.sheetnames:
                continue
            ws = wb[ws22.title]
            R = max(ws.max_row, ws22.max_row)
            Cn = max(ws.max_column, ws22.max_column)
            sd_cols = {c.column for c in ws[1] if c.value == "SD (included)"}   # V3.0
            for r in range(1, R + 1):
                for cidx in range(1, Cn + 1):
                    if ws.title == "Settings" and r >= 7 and cidx <= 4:
                        continue                 # the record part, rewritten on purpose
                    if ws.title == "Settings" and r == 4 and cidx in (3, 4):
                        continue                 # V3.0: MinSNR, the ratio check
                    if cidx in sd_cols:
                        continue                 # V3.0: the SD column
                    x0, y0 = ws.cell(row=r, column=cidx), ws22.cell(row=r, column=cidx)
                    fx, fy = _formula(x0), _formula(y0)
                    if (ws.title.startswith(("dFF_", "R_")) and isinstance(fx, str)
                            and isinstance(fy, str) and fx.startswith("=IF(")
                            and ',"",' in fx):
                        inner = "=" + fx.split(',"",', 1)[1][:-1]   # IF(check,"",<V2.2>)
                        if inner != fy:
                            diffs.append(f"{ws.title}!{x0.coordinate}: {fx!r} vs {fy!r}")
                        else:
                            wrapped[0] += 1
                        continue
                    x, y = ws.cell(row=r, column=cidx), ws22.cell(row=r, column=cidx)
                    if (ws.title.startswith(("dFF_", "R_")) and isinstance(x.value, str)
                            and isinstance(y.value, str) and x.value != y.value
                            and x.value.startswith(y.value) and "too dim" in x.value):
                        continue                 # V3.0: the sheet note says what blank means
                    if (ws.title == "ROI_info" and y.data_type == "f" and x.data_type == "s"
                            and x.value == y.value):
                        fixed.append(f"{ws.title}!{x.coordinate}")
                        continue                 # V2.2 bug, fixed: text that began with "="
                    if (_formula(x) or x.value) != (_formula(y) or y.value) \
                            or (x.value is not None and x.data_type != y.data_type):
                        diffs.append(f"{ws.title}!{x.coordinate}: {x.value!r} vs {y.value!r}")
            if ws.title == "Settings":
                dv = [(d.formula1, str(d.sqref)) for d in ws.data_validations.dataValidation]
                dv22 = [(d.formula1, str(d.sqref)) for d in ws22.data_validations.dataValidation]
                if dv != dv22:
                    diffs.append(f"dropdown {dv} vs {dv22}")
        n22 = {k: v.attr_text for k, v in w22.defined_names.items()}
        if n22 != {k: v for k, v in names.items() if k != "MinSNR"}:
            diffs.append(f"names {names} vs {n22}")
        check(f"{tag}: all sheets but the Settings record and Methods identical to V2.2 "
              f"({len(w22.sheetnames)} sheets; V3.0: {wrapped[0]} F/F0 and ratio formulas "
              f"= the V2.2 formula inside the ratio check)", not diffs and wrapped[0] > 0,
              "; ".join(diffs[:5]))
        if fixed:
            print(f"      (V2.2 turned ROI_info text beginning with '=' into a formula at "
                  f"{', '.join(fixed)}; now literal text)")
    return wb


def section_a(versions):
    print("\n--- a) provenance.py")
    pk = ["numpy", "scipy", "scikit-image", "nd2", "PySide6-Essentials", "pyqtgraph",
          "matplotlib", "openpyxl", "tifffile", "imagecodecs", "dask"]
    check("software_versions: Python, OS, PeterPiper and every library listed",
          all(k in versions for k in ["Python", "Operating system", "PeterPiper"] + pk)
          and versions["PeterPiper"].startswith(peterpiper.__version__),
          ", ".join(f"{k} {versions.get(k)}" for k in ["Python", "numpy", "imagecodecs"]))
    contract = ["tracker", "max_move_um", "margin_px", "size_tol", "first_frame_tol",
                "area_step", "sigma_um", "ring_um", "edge_level_clip", "phase_upsample",
                "mito_k", "gate_snr", "overlap_k", "t0", "norm"]
    sett = ["baseline_timepoint", "drift_from", "drift_to", "track_size_tol",
            "background_box_um", "background_max_um", "qc_max_area_jump", "qc_min_snr",
            "qc_max_saturated_frac", "qc_spike_sigma", "qc_min_area_frac", "qc_max_lost_frac"]
    miss = [k for k in contract + sett if k not in P.PARAM_DOCS]
    shape = all(isinstance(v, tuple) and len(v) == 3 and v[2] for v in P.PARAM_DOCS.values())
    check(f"PARAM_DOCS documents every Contract-1 key and the number-changing settings "
          f"({len(P.PARAM_DOCS)} entries)", not miss and shape, ", ".join(miss))
    s = Settings()
    s.baseline_timepoint = 3
    exp = synthetic()[0]
    tab = P.parameter_table(s, exp, TRACK_PARAMS, [r for r in []], {"rules": RULES,
                                                                    "comps": ["cell", "mito"]})
    check("parameter_table rows are (section, parameter, value, meaning)",
          all(len(r) == 4 for r in tab) and len(tab) > 30, f"{len(tab)} rows")
    d = {r[1]: r[2] for r in tab}
    check("parameter_table: tracker values, rules and extra keys",
          d.get("Largest movement between two timepoints (µm)") == 4.5
          and d.get("Search margin (px)") == 28 and d.get("ROIs drawn on timepoint (1-based)") == 2
          and d.get("Tracking rule 2") == "Track mitochondria using GFP AND intensity in ExRai"
          and d.get("redraw_every") == 1 and "mCherry: bg 101" in str(
              d.get("Channel scaling for WITH / AND rules (counts)")),
          str({k: d.get(k) for k in ("Search margin (px)", "redraw_every")}))
    txt = P.methods_text(s, exp, TRACK_PARAMS, None, ["cell", "mito"], versions, {"rules": RULES})
    want = ["4.5 µm", "28 px", "±30%", "0.6–1.6", "0.11–0.85", "upsampling factor 20",
            "σ = 1.1 µm", "1.7 µm", "5 µm ring", "2.5 × the background noise", "2.75 ×",
            "6.5", "timepoint 3", "timepoint 2", "Track whole cell using mCherry WITH intensity in GFP",
            "0.1625 µm per pixel", "every 30 s", "Harris", "Virtanen", "van der Walt",
            versions["numpy"], versions["scipy"], "mean ± SD"]         # V3.0: SD default
    miss = [w for w in want if w not in txt]
    check("methods_text mentions every value it was given", not miss, f"missing {miss}")
    no_rec = P.methods_text(Settings(), exp, None, None, ["mito"], versions)
    check("methods_text without tracker params says so",
          "did not record its own parameters" in no_rec and "3 µm" in no_rec)
    return txt


def section_b(versions, v22):
    print("\n--- b) workbook (synthetic)")
    from peterpiper.safety import new_output_file                         # noqa: F401
    exp, s, M, qc, include, why = synthetic()
    T, N = M.n_timepoints, M.n_cells
    cells = list(range(N))
    seeds = [_Seed(100 + 20 * k, 100) for k in range(N)]
    info = build_roi_info(exp, s, M, cells, seeds, s.seg_timepoint - 1, qc)
    prov = {"rules": RULES, "track_params": TRACK_PARAMS, "fingerprint": FINGERPRINT,
            "nd2_path": "C:/data/=evil movie.nd2", "comps": ["cell", "mito", "nucleus"],
            "bg_auto": True, "session_id": "=1+2"}
    ref = {"exp": exp}
    if v22:
        ref["v22"] = v22[0].write_workbook(str(W / "v22_synthetic.xlsx"), exp, s, M, cells, info,
                                           qc=qc, include=include, why=why)
    t = time.time()
    p0 = write_workbook(str(W / "no_provenance.xlsx"), exp, s, M, cells, info, qc=qc,
                        include=include, why=why)
    t0 = time.time() - t
    p1 = write_workbook(str(W / "with_provenance.xlsx"), exp, s, M, cells, info, qc=qc,
                        include=include, why=why, provenance=prov)
    print(f"      written in {t0:.2f} s: {Path(p0).name}, {Path(p1).name}")
    check_workbook("no provenance", p0, s, T, None, versions, dict(ref, prov={}),
                   expect_text=["=evil movie.nd2", "=1+1"])
    check_workbook("with provenance", p1, s, T, prov, versions, dict(ref, prov=prov),
                   expect_text=["=evil movie.nd2", "=1+1", "=1+2", FINGERPRINT["quick"]])
    # a different baseline must move B4 and nothing else
    s2 = Settings()
    s2.__dict__.update(s.__dict__)
    s2.baseline_timepoint = 7
    p2 = write_workbook(str(W / "baseline7.xlsx"), exp, s2, M, cells, info, qc=qc,
                        include=include, why=why, provenance=prov)
    check_workbook("baseline 7", p2, s2, T, prov, versions, dict(ref, prov=prov, v22=None))


def section_c(v22):
    print("\n--- c) .pzfx")
    T = 12
    x = np.arange(T, dtype=float) * 0.5 - 1.0
    rng = np.random.default_rng(3)
    panels = [("R/R0 GFP/ExRai", "R/R0", rng.random((T, 3)), ["Cell_1", "Cell_2", "Cell_4"]),
              ("F/F0 GFP", "F/F0", rng.random((T, 3)), ["Cell_1", "Cell_2", "Cell_4"])]
    cols = [("Baseline drift slope T2-T9 - F/F0 GFP", "slope", rng.random(3),
             ["Cell_1", "Cell_2", "Cell_4"])]
    notes = "Mito - movie.nd2. Included cells only; X = time from the baseline (timepoint 3 = 0)."
    prov = {"rules": RULES, "baseline": 3, "fingerprint": FINGERPRINT}
    a = write_pzfx(str(W / "with_prov.pzfx"), x, "Time (min)", panels, notes=notes,
                   columns=cols, provenance=prov)
    b = write_pzfx(str(W / "no_prov.pzfx"), x, "Time (min)", panels, notes=notes, columns=cols)
    trees = {k: ET.parse(v[0]).getroot() for k, v in (("with", a), ("without", b))}
    check(".pzfx with and without provenance parse with xml.etree", all(
        t is not None for t in trees.values()))

    def tables(root):
        return [ET.tostring(e) for e in root.iter() if e.tag.split("}")[-1] == "Table"]

    def notes_of(root):
        return [e.text or "" for e in root.iter() if e.tag.split("}")[-1] == "Notes"]
    tw, tn = tables(trees["with"]), tables(trees["without"])
    check(f".pzfx: same tables with and without provenance ({len(tw)} tables)",
          tw == tn and len(tw) == 7)        # 2 quantities x (mean/SEM/n, each cell) + 1 drift
    if v22:
        c = v22[1].write_pzfx(str(W / "v22.pzfx"), x, "Time (min)", panels, notes=notes,
                              columns=cols)
        t22 = ET.parse(c[0]).getroot()
        check(".pzfx: tables identical to the V2.2 code's", tables(t22) == tw)
        n22 = notes_of(t22)[0]
        check(".pzfx: V2.2 notes kept, provenance appended",
              notes_of(trees["with"])[0].startswith(n22) and n22 == notes)
    nw = notes_of(trees["with"])[0]
    nn = notes_of(trees["without"])[0]
    print(f"      Info notes: {nw}")
    check(".pzfx notes: version, date, rules, baseline, fingerprint",
          f"{peterpiper.APP_NAME} ({peterpiper.__version__})" in nw and re.search(r"\d{4}-\d\d-\d\d", nw)
          and "Track mitochondria using GFP AND intensity in ExRai" in nw
          and "timepoint 3" in nw and "=SUM(9)dead" in nw)
    check(".pzfx notes without provenance: version and date", peterpiper.__version__ in nn
          and "Tracking rules" not in nn)


def quick_fingerprint(path: Path) -> dict:
    """The same idea as history.nd2_fingerprint (size + first and last 4 MiB)."""
    st = path.stat()
    h = hashlib.sha1(str(st.st_size).encode())
    with open(path, "rb") as f:
        h.update(f.read(4 << 20))
        f.seek(max(0, st.st_size - (4 << 20)))
        h.update(f.read(4 << 20))
    return {"name": path.name, "size": st.st_size, "mtime": st.st_mtime, "quick": h.hexdigest()}


def section_d(versions, v22):
    print("\n--- d) real data (V2.2 mito run, read-only source)")
    if not (REAL_ND2.exists() and REAL_ROI.exists()):
        check("real data present", False, "test files not found")
        return None
    from peterpiper import nd2io, roifile
    roi = W / "real" / REAL_ROI.name
    roi.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REAL_ROI, roi)
    src = nd2io.open_source(str(REAL_ND2))
    try:
        exp = nd2io.describe(src, str(W / "real"))
    finally:
        try:
            src.close()
        except Exception:                                             # noqa: BLE001
            pass
    state, _comps = roifile.load_roi_state(roi)
    track = roifile.load_roi_track(roi)
    comp = next(iter(track["meas"]))
    M = track["meas"][comp]
    s = Settings()
    s.baseline_timepoint = int(state.get("baseline", 1) or 1) if state else 1
    s.seg_timepoint = int(state.get("t0", 1) or 1) if state else 1
    s.roi_mode = comp
    exp.channels = list(M.channels)
    print(f"      {REAL_ND2.name}: T={exp.n_timepoints}, channels {exp.channels}, "
          f"{exp.um_per_px} µm/px, {exp.seconds_per_frame} s/frame; {comp}: {M.n_cells} cells")
    cells = list(range(M.n_cells))
    excl = set((state or {}).get("excl", {}).get(comp, []))
    include = {k: 0 if k in excl else 1 for k in cells}
    seeds = [_Seed(0, 0) for _ in cells]
    info = build_roi_info(exp, s, M, cells, seeds, s.seg_timepoint - 1, None)
    fp = quick_fingerprint(REAL_ND2)
    prov = {"rules": (state or {}).get("rules") or [], "track_params": track.get("params") or None,
            "fingerprint": fp, "nd2_path": str(REAL_ND2), "comps": list(track["meas"]),
            "bg_auto": (state or {}).get("bg_auto")}
    ref = {"exp": exp, "prov": prov}
    if v22:
        ref["v22"] = v22[0].write_workbook(str(W / "real" / "v22.xlsx"), exp, s, M, cells, info,
                                           include=include)
    p = write_workbook(str(W / "real" / "real.xlsx"), exp, s, M, cells, info, include=include,
                       provenance=prov)
    check_workbook("real data", p, s, M.n_timepoints, prov, versions, ref)
    txt = P.methods_text(s, exp, prov["track_params"], None, prov["comps"], versions, prov)
    check("real data: methods text names the file's real metadata",
          f"{exp.n_timepoints} timepoints" in txt and f"{exp.um_per_px:g} µm per pixel" in txt
          and REAL_ND2.name in txt)
    return txt


def main() -> int:
    if W.exists():
        shutil.rmtree(W, ignore_errors=True)
    W.mkdir(parents=True, exist_ok=True)
    versions = P.software_versions()
    try:
        v22 = v22_package()
    except Exception as e:                                            # noqa: BLE001
        print(f"(V2.2 comparison unavailable: {e})")
        v22 = None
    check("V2.2 code (excel.py, prism.py of the baseline commit) loaded for comparison",
          v22 is not None)
    txt = section_a(versions)
    section_b(versions, v22)
    section_c(v22)
    real = None if "--no-real" in sys.argv else section_d(versions, v22)
    out = W / "methods_text.txt"
    out.write_text(txt + ("\n\n==== real data ====\n\n" + real if real else ""), encoding="utf-8")
    print(f"\nmethods texts written to {out}")
    bad = [n for n, ok in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(bad)} passed, {len(bad)} failed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
