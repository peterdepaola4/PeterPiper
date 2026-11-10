"""
Developer test on REAL measurements: the graph style, the trace panel's
'As exported' view and the export's PNG / CSV, using the per-timepoint
measurements stored in a V2.2 ROI file with tracking (no .nd2 reading needed).

    python dev_tests/test_graph_real.py <ROI file .npz> [output folder]

The ROI file is COPIED into the output folder first (the original is only read).
Run offscreen: PETERPIPER_HOME=<scratch>/_home MPLBACKEND=Agg QT_QPA_PLATFORM=offscreen
Exits with 1 if any check fails. Not shipped (developer folder).
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
os.environ.setdefault("MPLBACKEND", "Agg")
if len(sys.argv) < 2:
    print(__doc__)
    sys.exit(2)
SRC = Path(sys.argv[1])
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(
    os.environ.get("PETERPIPER_HOME", tempfile.gettempdir())) / "out" / "graph_real"
OUT.mkdir(parents=True, exist_ok=True)

from peterpiper import graphstyle as GS                         # noqa: E402
from peterpiper.config import Experiment, Settings              # noqa: E402
from peterpiper.manual import LABELS                            # noqa: E402
from peterpiper.measure import Measurements                     # noqa: E402

checks: list = []


def ok(name: str, cond, extra: str = "") -> None:
    checks.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra else ""), flush=True)


def close(a, b, tol=1e-12) -> bool:
    a, b = np.asarray(a, float), np.asarray(b, float)
    return a.shape == b.shape and bool(np.all((np.isnan(a) & np.isnan(b)) |
                                              (np.abs(a - b) <= tol * (1 + np.abs(b)))))


def load_real():
    """(Measurements, comp, excluded cells, nd2 name) from the copied ROI file."""
    local = OUT / SRC.name
    if not local.exists():
        shutil.copy2(SRC, local)
    with np.load(local, allow_pickle=False) as z:
        state = json.loads(str(z["state_json"]))
        comp = state["comps"][0]
        p = f"trk_{comp}_m_"
        M = Measurements(mean=z[p + "mean"].astype(float), background=z[p + "background"],
                         area_px=z[p + "area_px"], n_saturated=z[p + "n_saturated"],
                         quality=z[p + "quality"], channels=list(state["channels"]),
                         background_sd=z[p + "background_sd"] if p + "background_sd" in z
                         else None, roi_mode=comp)
    excl = set(state.get("excl", {}).get(comp, []))
    return M, comp, excl, state.get("nd2", SRC.stem)


def v22_export_module():
    import pd4nav_history                           # PD4nav's history (PeterPiper's earlier name)
    src = pd4nav_history.show("8e31298", "export.py")
    p = OUT / "export_v22.py"
    p.write_bytes(src)
    spec = importlib.util.spec_from_file_location("peterpiper._export_v22", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from peterpiper import export as new
    from peterpiper.gui.traces import TracePanel, VIEW_EXPORTED
    from peterpiper.plots import _panels

    M, comp, excl, nd2 = load_real()
    T, N = M.n_timepoints, M.n_cells
    live = list(range(N))
    inc = [k for k in live if k not in excl]
    print(f"real data: {nd2}  comp={comp}  T={T}  C={M.n_channels} {M.channels}  N={N}  "
          f"excluded={sorted(excl)}")
    exp = Experiment(nd2_path=str(OUT / nd2), channels=list(M.channels), n_timepoints=T,
                     seconds_per_frame=60.0, out_dir=str(OUT))
    s = Settings()
    s.baseline_timepoint = 3
    s.ratio_min_snr = 0.0          # V3.0: the ratio check off - V2.2 had none
    from peterpiper import measure as _MS
    _MS.set_min_snr(s.ratio_min_snr)   # ... for the trace panel too (as the main window does)
    panels = {p[0]: p for p in _panels(M, s)}
    sheet = next(k for k in panels if k.startswith("dRR_"))
    comps_arg = lambda: {comp: dict(label=LABELS[comp], name=comp, M=M, cells=live,  # noqa: E731
                                    include={k: int(k in inc) for k in live}, why={}, qc=None,
                                    seeds=None, channel=0, rois=None)}
    keys = [f"{comp}|csv", f"{comp}|graph|{sheet}"]

    # ---- CSV: byte-identical to V2.2 on real numbers
    old = v22_export_module()
    r_old = old.run_export(str(OUT / "v22"), exp, s, comps_arg(), keys)
    time.sleep(1.1)
    style = GS.apply_preset({}, "Mean ± SEM + each cell").to_dict()
    style["baseline_line"] = True
    s.graph_style = style
    r_new = new.run_export(str(OUT / "v23"), exp, s, comps_arg(), keys)
    a = sorted(f for f in r_old["files"] if f.endswith(".csv"))
    b = sorted(f for f in r_new["files"] if f.endswith(".csv"))
    def no_sd(path):                # V3.0 adds an SD column at the end of every row
        rows = Path(path).read_bytes().decode("utf-8").split(chr(10))
        return chr(10).join(r.rsplit(",", 1)[0] if r else r for r in rows).encode("utf-8")
    diff = [Path(x).name for x, y in zip(a, b) if Path(x).read_bytes() != no_sd(y)]
    ok("real data: every CSV byte-identical to V2.2 (ratio check off, without the V3.0 SD "
       "column)", len(a) == len(b) > 0 and not diff, f"{len(a)} files, differing: {diff[:3]}")
    hdr = Path(b[0]).read_text(encoding="utf-8").splitlines()[0]
    ok("real data: the CSV's SD column", hdr.endswith(",Mean,SEM,n,SD"), hdr[-30:])
    png = [f for f in r_new["files"] if f.endswith(".png")]
    ok("real data: export PNG written", len(png) == 1, str(png))

    # ---- the trace panel, as ClickWindow._sync_traces drives it
    w = TracePanel(exp)
    w.resize(620, 900)
    w.show()
    app.processEvents()
    q = sheet.replace("dRR_", "R/R0 - ").replace("_over_", "/")
    w.set_data(M, live, inc, {}, LABELS[comp], s.baseline_timepoint - 1, 0, [q])
    w.set_export_context(Path(exp.nd2_path).stem[:40], LABELS[comp])   # = the export's stem
    w.set_style(style)
    w.set_view(VIEW_EXPORTED)
    for _ in range(20):
        app.processEvents()
        time.sleep(0.01)
    ok("panel: shows the exported quantity", w.current_quantity() == q, w.current_quantity())
    x, y, names, xl, yl = w.current_series()
    data = panels[sheet][1]
    ok("panel: current_series = the export's numbers (included cells only)",
       close(y, data[:, inc]) and names == [f"Cell_{k + 1}" for k in inc], f"{y.shape}")
    m, lo, hi, n = GS.stats(data[:, inc], "SEM")
    ok("panel As exported: mean = stats() of the included", close(w._mean.getData()[1], m))
    fin = np.isfinite(m) & np.isfinite(lo) & np.isfinite(hi)
    ok("panel As exported: error bars = SEM", close(w._errbar.opts["top"], (hi - m)[fin]))
    ok("panel As exported: title n", w._title.endswith(f"(n = {len(inc)})"), w._title)
    w.grab().save(str(OUT / "panel_real_as_exported.png"))
    # the panel's own 'Save graph' PNG must be the export's PNG, byte for byte
    mine = OUT / "panel_real_save_graph.png"
    if mine.exists():
        mine.unlink()
    used = w.save_graph(mine)
    ok("real data: the panel's PNG = the export's PNG (same bytes)",
       Path(used).read_bytes() == Path(png[0]).read_bytes(),
       f"{Path(used).stat().st_size} vs {Path(png[0]).stat().st_size}")
    shutil.copy2(png[0], OUT / "export_real.png")
    n_ok = sum(c for _n, c in checks)
    print(f"\n{n_ok} / {len(checks)} checks passed")
    return 0 if n_ok == len(checks) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:                                      # noqa: BLE001
        traceback.print_exc()
        sys.exit(1)
