"""
PeterPiper's self-test: does this installation work, start to finish?

    PeterPiper --selftest [folder [movie.nd2]]                 (the Mac / Windows app)
    python app/PeterPiper.py --selftest [folder [movie.nd2]]   (from the code)

Made for the packaged app (one file that carries its own Python), where a
missing piece shows up only when it is used: it imports every part of
PeterPiper and of the libraries it reads movies with, then runs a whole
analysis on a small synthetic movie made here (16 nuclei, 3 channels, a GFP
sensor that doubles in the odd-numbered cells) in the real main window without
showing it: AUTO-DETECT, a background region, TRACK & MEASURE, and an export
of every file type. It checks the numbers against the known answers and
writes the files into `folder` (default: a new temporary folder). With a real
.nd2 movie it also opens that (read only): its channels, size, frame interval
and the first and last frames. Nothing of yours is changed: it uses its own
settings folder.

Prints one line per check and ends with 'SELF-TEST PASSED' (exit code 0) or
'SELF-TEST FAILED' (exit code 1).
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

RESULTS = []


def ok(name: str, cond: bool, extra: str = "") -> None:
    RESULTS.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra else ""), flush=True)


def _synthetic():
    """(source, experiment-ready dimensions): 6 timepoints, Cy5 / GFP / mCherry,
    16 nuclei on a 4 x 4 grid drifting slowly, GFP doubling after timepoint 3 in
    the odd-numbered cells, an empty strip on the right for the background."""
    import numpy as np
    from .nd2io import ImageSource
    T, H, W, n_cells = 6, 192, 256, 16
    rng = np.random.default_rng(7)
    yy, xx = np.mgrid[0:H, 0:W]
    frames = np.zeros((T, 3, H, W), np.uint16)
    for t in range(T):
        st = np.full((3, H, W), 200.0)
        for n in range(n_cells):
            cy, cx = 30 + 44 * (n // 4) + 0.5 * t, 30 + 44 * (n % 4) + 0.3 * t
            inside = (yy - cy) ** 2 + (xx - cx) ** 2 < 9 ** 2
            st[0][inside] += 1500 + 60 * n
            if n % 2 == 0:
                st[1][inside] += 600 if t < 3 else 1200
            st[2][inside] += 400
        st += rng.normal(0, 8, st.shape)
        frames[t] = np.clip(np.round(st), 0, 65535).astype(np.uint16)

    class Movie(ImageSource):
        def __init__(self):
            self.channels = ["Cy5", "GFP", "mCherry"]
            self.n_timepoints, self.height, self.width = T, H, W

        def frame(self, t):
            return frames[int(t)]

        def close(self):
            pass
    return Movie()


def _import_everything() -> None:
    """Every module of PeterPiper and of the movie reader (a packaged app only
    holds what was found when it was built)."""
    import importlib
    import pkgutil
    import peterpiper
    bad = []
    for m in pkgutil.walk_packages(peterpiper.__path__, "peterpiper."):
        if m.name.endswith("__main__"):           # starts the app itself
            continue
        try:
            importlib.import_module(m.name)
        except Exception as exc:                                   # noqa: BLE001
            bad.append(f"{m.name}: {exc!r}")
    ok("every part of PeterPiper loads", not bad, "; ".join(bad[:3]))
    libs = ["numpy", "scipy.ndimage", "scipy.optimize", "skimage.registration",
            "skimage.segmentation", "skimage.measure", "skimage.morphology", "skimage.filters",
            "tifffile", "imagecodecs", "nd2", "dask.array", "openpyxl", "PIL.Image",
            "matplotlib", "pyqtgraph", "PySide6.QtWidgets", "PySide6.QtSvg"]
    bad = []
    for name in libs:
        try:
            importlib.import_module(name)
        except Exception as exc:                                   # noqa: BLE001
            bad.append(f"{name}: {exc!r}")
    ok("every library loads", not bad, "; ".join(bad[:3]))
    # the .nd2 reader in full: its submodules are loaded lazily, when a file is opened
    import nd2
    bad = []
    for m in pkgutil.walk_packages(nd2.__path__, "nd2."):
        try:
            importlib.import_module(m.name)
        except ImportError as exc:                 # an optional extra PeterPiper does not use
            if not any(w in str(exc).lower() for w in ("optional", "pip install")):
                bad.append(f"{m.name}: {exc!r}")
        except Exception:                                          # noqa: BLE001
            pass                                                   # optional extras
    ok("the .nd2 reader is complete", not bad, "; ".join(bad[:3]))


def _real_movie(path: str) -> None:
    """Open a real .nd2 (read only): metadata and two frames."""
    from .nd2io import describe, open_source
    t = time.time()
    try:
        src = open_source(path)
        exp = describe(src)
        a, b = src.frame(0), src.frame(src.n_timepoints - 1)
        src.close()
        good = (a.ndim == 3 and a.shape == b.shape and a.shape[0] == len(exp.channels)
                and exp.n_timepoints > 0 and exp.um_per_px > 0)
        info = (f"{Path(path).name}: {exp.n_timepoints} timepoints x {len(exp.channels)} "
                f"channels ({', '.join(exp.channels)}), {exp.width} x {exp.height} px, "
                f"{exp.um_per_px:g} um/px, {exp.seconds_per_frame:g} s per frame, "
                f"read in {time.time() - t:.1f} s")
    except Exception as exc:                                       # noqa: BLE001
        good, info = False, repr(exc)
    ok("a real .nd2 movie opens (metadata, first and last frame)", good, info)


def run(folder: Path, movie: str = "") -> int:
    from PySide6.QtWidgets import QApplication, QMessageBox
    app = QApplication.instance() or QApplication(sys.argv[:1])
    for n in ("information", "warning", "critical"):              # nobody to click OK
        setattr(QMessageBox, n, staticmethod(lambda *a, **k: QMessageBox.Ok))
    t_start = time.time()
    import peterpiper
    print(f"PeterPiper {peterpiper.__version__} ({peterpiper.APP_NAME}) self-test - "
          f"Python {sys.version.split()[0]} on {sys.platform}"
          f"{' (packaged app)' if getattr(sys, 'frozen', False) else ''}", flush=True)
    _import_everything()
    if movie:
        _real_movie(movie)

    from .config import Experiment, Settings
    from .export import run_export
    from .gui import theme as TH
    from .gui import widgets as W
    from .gui.clickwin import ClickWindow
    from .manual import background_from_outline
    TH.apply(app, "midnight", 11.0)
    ok("the logo and icon are inside the app",
       (W.ASSETS / "logo_white.png").exists() and not W.app_icon().isNull())

    def pump(sec=0.2):
        t = time.time()
        while time.time() - t < sec:
            app.processEvents()
            time.sleep(0.005)

    def wait(w, limit=300.0):
        t = time.time()
        pump(0.2)
        while w._busy_now() and time.time() - t < limit:
            pump(0.05)
        pump(0.3)

    src = _synthetic()
    folder.mkdir(parents=True, exist_ok=True)
    exp = Experiment(nd2_path=str(folder / "selftest_movie.nd2"), out_dir=str(folder / "results"),
                     channels=list(src.channels), n_timepoints=src.n_timepoints,
                     width=src.width, height=src.height, um_per_px=0.5, seconds_per_frame=30.0)
    exp.export_tiffs = False
    Path(exp.out_dir).mkdir(parents=True, exist_ok=True)
    ClickWindow._ask_previous_run = lambda self, runs, menu=False: None
    w = ClickWindow(src, exp, Settings(baseline_timepoint=1))
    w._paths_ok = lambda *a, **k: True
    w.resize(1400, 900)
    w.show()
    t0 = time.time()
    while not getattr(w, "_offered", True) and time.time() - t0 < 30:
        pump(0.1)
    w._goto_step(0, user=True)
    w._auto_select()
    wait(w)
    n = sum(1 for c in w.cells if "nucleus" in c)
    ok("AUTO-DETECT finds the 16 nuclei", n == 16, f"{n} found")
    w.background = background_from_outline([(205, 20), (250, 20), (250, 170), (205, 170)],
                                           (src.height, src.width))
    w._bg_auto, w._bg_kind = False, "manual"
    w.cmb_comp.setCurrentIndex(w.cmb_comp.findData("nucleus"))
    w._track()
    wait(w)
    ok("TRACK & MEASURE: every cell followed through every timepoint", w.track is not None)
    M, _inc = w._measured("nucleus")
    g = M.channels.index("GFP")
    ff = M.ff0(g, 0, 5.0)                       # F/F0 of GFP, baseline timepoint 1
    import numpy as np
    sensor = [k for k in range(M.n_cells) if np.isfinite(ff[-1, k])]
    late = float(np.nanmean(ff[-1, sensor])) if sensor else float("nan")
    ok("the sensor cells' GFP doubles (F/F0 = 2.0 +- 0.1 at the end)",
       len(sensor) == 8 and abs(late - 2.0) < 0.1, f"{len(sensor)} cells, F/F0 {late:.3f}")
    ok("the cells without the sensor are left out of GFP F/F0 (ratio check)",
       sum(1 for k in range(M.n_cells) if not np.isfinite(ff[-1, k])) == 8)
    comps = w._export_data()
    keys = ["nucleus|csv", "nucleus|excel", "nucleus|prism", "nucleus|prismgraph",
            "nucleus|graph|dFF_GFP", "nucleus|roi_drawn", "*|methods"]
    out = run_export(exp.out_dir, exp, w.settings, comps, keys, src=src,
                     background=w.background, t0=0, prefix="")
    files = [Path(f) for f in out["files"]]
    kinds = {f.suffix.lower() for f in files if f.exists() and f.stat().st_size > 0}
    ok("export: Excel, Prism, CSV, graph, ROI picture and methods text written",
       {".xlsx", ".pzfx", ".prism", ".csv", ".png", ".txt"} <= kinds, str(sorted(kinds)))
    try:
        from openpyxl import load_workbook
        wb = load_workbook(next(f for f in files if f.suffix == ".xlsx"))
        good = len(wb.sheetnames) > 3
    except Exception as exc:                                       # noqa: BLE001
        good = False
        print("   ", repr(exc))
    ok("the workbook opens again", good)
    w._dirty = False
    w.close()
    pump(0.3)
    failed = [n for n, c in RESULTS if not c]
    print(f"\n{len(RESULTS) - len(failed)} / {len(RESULTS)} checks passed in "
          f"{time.time() - t_start:.0f} s; files in {folder}", flush=True)
    print("SELF-TEST FAILED" if failed else "SELF-TEST PASSED", flush=True)
    return 1 if failed else 0


def main(argv) -> int:
    folder = Path(argv[0]) if argv else Path(tempfile.mkdtemp(prefix="PeterPiper selftest "))
    folder.mkdir(parents=True, exist_ok=True)
    if sys.stdout is None or sys.stderr is None:      # a window app (no console): into a file
        sys.stdout = sys.stderr = open(folder / "selftest.txt", "w", encoding="utf-8",
                                       buffering=1)
    # its own settings, never yours; no screen needed
    os.environ["PETERPIPER_HOME"] = str(folder / "settings")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("MPLBACKEND", "Agg")
    try:
        return run(folder, argv[1] if len(argv) > 1 else "")
    except Exception:                                              # noqa: BLE001
        traceback.print_exc()
        print("SELF-TEST FAILED", flush=True)
        return 1
