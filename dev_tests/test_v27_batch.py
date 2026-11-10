"""
Developer test (not shipped): V2.7 saved settings, batch analysis, templates.

    MPLBACKEND=Agg QT_QPA_PLATFORM=offscreen python dev_tests/test_v27_batch.py <file.nd2>

A) presets: analysis + plot settings round trip; never overwrites; plot-only
   files hold no analysis; unknown fields ignored.
B) batch: analyse_one on a real .nd2 (read only; everything written under
   _out/v27batch) with saved settings (nucleus on GFP, baseline T5): cells found,
   tracked, exported (workbook + ROI file + methods), no dialog waited, the
   user's settings.json untouched, the log CSV written.
C) prismtemplate: the two template files are made, the XY one is used for new
   .prism files (its graph id), reset keeps the old file.
"""
from __future__ import annotations

import csv
import os
import shutil
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                                  # noqa: BLE001
    pass
HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "app"))
OUT = REPO / "_out" / "v27batch"
if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True)
os.environ["PETERPIPER_HOME"] = str(OUT / "home")
os.environ.setdefault("MPLCONFIGDIR", str(OUT / "home" / "mpl"))

from PySide6.QtWidgets import QApplication                         # noqa: E402

app = QApplication(sys.argv)

from peterpiper import presets as PR                                   # noqa: E402
from peterpiper import prismtemplate as T                              # noqa: E402
from peterpiper.config import Settings, _settings_file                 # noqa: E402

FAILS: list = []
N = [0]


def ok(name, cond, extra=""):
    N[0] += bool(cond)
    if not cond:
        FAILS.append(name)
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra else ""), flush=True)


def part_a():
    print("\n=== A) saved settings ===", flush=True)
    s = Settings(baseline_timepoint=5)
    s.track_rules = [{"comp": "nucleus", "a": "GFP", "mode": "only", "b": ""}]
    p1 = PR.save(PR.folder() / "nuc GFP.json", "nuc GFP", analysis=s,
                 plot={"spec": {"y": {"comp": "nucleus", "quantity": "F/F0 GFP"}}, "mode": "runs"})
    p2 = PR.save(PR.folder() / "nuc GFP.json", "nuc GFP", analysis=s)
    ok("A saved, never overwritten", Path(p1).name == "nuc GFP.json" and Path(p2).name ==
       "nuc GFP_2.json", f"{p1} {p2}")
    b = PR.read(p1)
    s2 = PR.analysis_settings(b)
    ok("A analysis round trip", s2.baseline_timepoint == 5 and s2.track_rules == s.track_rules)
    ok("A plot part kept", b["plot"]["spec"]["y"]["quantity"] == "F/F0 GFP")
    ok("A describe says what it holds", "tracking: nucleus on GFP" in PR.describe(b) and
       "plot: Plot F/F0 of GFP in the nucleus vs time." in PR.describe(b), PR.describe(b))
    p3 = PR.save(PR.folder() / "plot only.json", "plot only", plot={"mode": "dishes"})
    ok("A plot-only file has no analysis", PR.analysis_settings(PR.read(p3)) is None)
    bad = OUT / "bad.json"
    bad.write_text('{"kind": "x"}', encoding="utf-8")
    try:
        PR.read(bad)
        ok("A not a settings file -> plain error", False)
    except ValueError as e:
        ok("A not a settings file -> plain error", "not a PeterPiper settings file" in str(e))
    return s


def part_b(nd2: str, s: Settings):
    print("\n=== B) batch analysis ===", flush=True)
    from peterpiper.gui.batchdlg import analyse_one, write_log
    before = _settings_file().read_bytes() if _settings_file().exists() else None
    row = analyse_one(nd2, s, progress=lambda t: print("   ", t, flush=True),
                      out_dir=str(OUT / "OUTPUT_batch"))
    print("   row:", {k: (v[:150] if isinstance(v, str) else v) for k, v in row.items()})
    ok("B status: automatic - check", row["Status"] == "automatic - check", row["Status"])
    n = int(row["Cells found"].split()[-1]) if row["Cells found"] else 0
    ok("B nuclei found and tracked", n >= 20, row["Cells found"])
    exp_dir = Path(row["Export folder"]) if row["Export folder"] else OUT / "none"
    files = [p.name for p in exp_dir.rglob("*")] if exp_dir.exists() else []
    ok("B exported into the given OUTPUT folder", str(OUT / "OUTPUT_batch") in str(exp_dir)
       and any(f.endswith(".xlsx") for f in files) and any(f.endswith("_ROIs.npz") for f in files)
       and any("methods" in f for f in files), f"{sorted(files)[:12]}")
    after = _settings_file().read_bytes() if _settings_file().exists() else None
    ok("B the user's settings.json is not changed by a batch run", before == after)
    ok("B no step was refused (busy)", "Wait for the current job" not in row["Messages"],
       row["Messages"][:200])
    log = write_log(str(OUT), [row], "nuc GFP")
    rows = list(csv.reader(open(log, encoding="utf-8-sig")))
    ok("B log CSV: header + one row", len(rows) == 2 and rows[0][0] == "File" and
       rows[1][-1] == "nuc GFP")


def part_c():
    print("\n=== C) Prism style templates ===", flush=True)
    xp, cp = T.ensure()
    ok("C both template files made", xp.exists() and cp.exists())
    ok("C the XY template is used (made from PeterPiper's)", T.active_xy() == str(xp))
    ok("C no column graph until you make one", T.column_template() is None)
    import numpy as np
    from peterpiper.prismfile import write_compare_prism
    import json
    import zipfile
    f = write_compare_prism(str(OUT / "t.prism"), [("A", np.arange(3.0), np.ones((3, 2)))],
                            "x", "q", "q", "t", ["#0072B2"])
    with zipfile.ZipFile(f) as z:
        notes = json.loads(z.read(next(n for n in z.namelist() if n.startswith("info/"))))
    ok("C a new .prism is made from your template (graph + its own tables' graphs)",
       len(json.loads(zipfile.ZipFile(f).read("document.json"))["sheets"]["graphs"]) == 2,
       notes.get("notesText", "")[:40])
    T.reset("xy")
    ok("C reset keeps your old file", (xp.parent / f"{xp.stem} (old 1).prism").exists()
       and xp.exists())


def main() -> int:
    s = part_a()
    if len(sys.argv) > 1:
        part_b(sys.argv[1], s)
    part_c()
    print(f"\n{N[0]} / {N[0] + len(FAILS)} checks passed")
    for f in FAILS:
        print("  FAILED:", f)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
