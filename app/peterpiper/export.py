"""
The export list ('cart'): pick exactly the outputs you want; each export goes
into its own tidy folder:

    OUTPUT_<file>/Export_<date>_<time>/
        <Compartment>/
            <file>_<compartment>.xlsx         every cell's values (Raw, background-
                                              subtracted, F/F0, ratio, R/R0), Include
                                              sheet, Graphs sheet, QC, settings
            <file>_<compartment>.pzfx         GraphPad Prism tables: mean/SEM/n + each cell
            Prism graphs/<file>_<q>.prism     Prism 10+: the graph already made in your
                                              graph style (as the live graph; closest
                                              Prism look where Prism cannot draw it)
                                              + its tables
            Graphs/<quantity>.png             300 dpi, in your graph style (as the
                                              trace panel's 'As exported' view)
            CSV/<quantity>.csv                included cells + mean, SEM, n
            ROI pictures/...png               full resolution, numbered as in Excel
        <file>_ROIs.npz                       the ROI file (Load saved ROIs...)
        <file>_methods.txt                    a ready-to-edit methods section with
                                              every setting and rule used (+ references)
        Raw TIFFs/                            every timepoint and channel (raw counts;
                                              open visible in Fiji / ImageJ)
        Viewing copies (PNG)/                 8-bit, contrast-stretched - for looking only

All numbers are computed from the raw, full-resolution pixels under each ROI,
minus the background region of the same frame and channel; time 0 = baseline.
"""
from __future__ import annotations

import copy
import csv
import datetime as dt
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

import numpy as np

from .config import Experiment, Settings
from .excel import build_roi_info, write_workbook
from .graphstyle import describe
from .measure import Measurements
from .plots import _panels, export_prism, export_roi_images, preferred_sheets
from .safety import exists, make_dirs, new_output_file

ProgressFn = Optional[Callable[[float, str], bool]]

PREFIX = [("dRR_", "R/R0"), ("dFF_", "F/F0"), ("R_", "Ratio"), ("BgSub_", "Intensity")]


def nice(sheet: str) -> str:
    """'dRR_GFP_over_Cy5' -> 'R/R0 GFP/Cy5' (labels for the list)."""
    for p, lab in PREFIX:
        if sheet.startswith(p):
            return f"{lab} {sheet[len(p):].replace('_over_', '/')}"
    return sheet


def _rank(sheet: str) -> int:
    """R/R0 first, then F/F0, ratio, intensity."""
    for i, (p, _lab) in enumerate(PREFIX):
        if sheet.startswith(p):
            return i
    return len(PREFIX)


def catalog(comps: Dict[str, dict], s: Settings) -> List[dict]:
    """
    Every output that can be made. comps: {comp key: dict(label, M, ...)}.
    Item: dict(key, group, section, label).
    """
    out = []
    for c, d in comps.items():
        g = d["label"]
        out += [dict(key=f"{c}|excel", group=g, section="Data",
                     label="Excel workbook (every cell's values)"),
                dict(key=f"{c}|prismgraph", group=g, section="Data",
                     label="Prism graphs (.prism, Prism 10+): graph made from the included "
                           "cells in your graph style (as the live graph), + mean/SEM/n and "
                           "each-cell tables"),
                dict(key=f"{c}|prism", group=g, section="Data",
                     label="Prism tables (.pzfx, any Prism version)"),
                dict(key=f"{c}|csv", group=g, section="Data",
                     label="CSV tables (one per quantity)"),
                dict(key=f"{c}|drift", group=g, section="Data",
                     label=f"Baseline drift slope T{getattr(s, 'drift_from', 2)}-"
                           f"T{getattr(s, 'drift_to', 9)} per cell (Excel + Prism dot plot)")]
        for name, *_ in sorted(_panels(d["M"], s), key=lambda p: _rank(p[0])):
            out.append(dict(key=f"{c}|graph|{name}", group=g, section="Graphs (PNG, 300 dpi)",
                            label=f"Graph: {nice(name)}"))
        out += [dict(key=f"{c}|roi_drawn", group=g, section="ROI pictures",
                     label="ROIs on the timepoint you drew them"),
                dict(key=f"{c}|roi_last", group=g, section="ROI pictures",
                     label="ROIs on the last timepoint"),
                dict(key=f"{c}|roi_every", group=g, section="ROI pictures",
                     label="ROIs on every 10th timepoint (tracking check)")]
    out += [dict(key="*|roifile", group="Whole experiment", section="",
                 label="ROI file (.npz) - to reload later"),
            dict(key="*|methods", group="Whole experiment", section="",
                 label="Methods (text file) - a ready-to-edit methods section with the "
                       "rules and every setting used"),
            dict(key="*|tiffs", group="Whole experiment", section="",
                 label="Raw TIFFs (every timepoint and channel, 16-bit raw counts)"),
            dict(key="*|views", group="Whole experiment", section="",
                 label="Viewing copies (8-bit PNG, contrast-stretched - for looking, "
                       "not for measuring)")]
    return out


def standard(cat: Sequence[dict], prefer: Optional[Dict[str, List[str]]] = None) -> List[str]:
    """
    The usual set: Excel, Prism, ROI picture, ROI file, Methods text, and the graphs of your key
    quantities (prefer[comp], e.g. R/R0 GFP/Cy5 and F/F0 GFP) - or every F/F0 and
    R/R0 graph of a compartment that has none of them.
    """
    keys = [it["key"] for it in cat if it["key"].endswith(("|excel", "|prism", "|prismgraph",
                                                             "|roi_drawn", "|drift"))
            or it["key"] in ("*|roifile", "*|methods")]
    by_comp: Dict[str, List[str]] = {}
    for it in cat:
        if "|graph|" in it["key"]:
            by_comp.setdefault(it["key"].split("|", 1)[0], []).append(it["key"])
    for c, gs in by_comp.items():
        want = [g for g in gs if g.split("|", 2)[2] in (prefer or {}).get(c, [])]
        keys += want or [g for g in gs if "|graph|dFF_" in g or "|graph|dRR_" in g]
    return keys


def clean_prefix(text: str, limit: int = 60) -> str:
    """The name you typed for the files, made safe for Windows file names
    (at most `limit` characters)."""
    out = "".join(ch if ch.isalnum() or ch in "-_. ()" else "_" for ch in str(text or ""))
    return out.strip(" ._")[:limit].strip(" ._")


def _safe(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_. " else "_" for ch in name).strip()


def _drift_workbook(path: Path, exp: Experiment, M: Measurements, s: Settings, cells,
                    include, quantities, a: int, z: int, x) -> str:
    """Each cell's baseline drift slope (straight-line fit through timepoints a..z)
    per quantity, with mean / SEM / n of the included cells."""
    from openpyxl import Workbook
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter
    from .plots import drift_slopes, nice_name
    panels = {p[0]: p for p in _panels(M, s)}
    qs = [q for q in quantities if q in panels]
    unit = "per min" if exp.seconds_per_frame > 0 else "per timepoint"
    slopes = {q: drift_slopes(panels[q][1][:, list(cells)], x, a, z) for q in qs}
    wb = Workbook()
    ws = wb.active
    ws.title = "Baseline drift"
    ws.append([f"Baseline drift: slope of the least-squares straight line through timepoints "
               f"{a}-{z} (background-subtracted values; time in "
               f"{'minutes' if exp.seconds_per_frame > 0 else 'timepoints'}). Mean / SEM / n "
               f"use the included cells only."])
    ws.append([])
    ws.append(["Cell", "Include (1/0)"] + [f"{nice_name(q)} slope ({unit})" for q in qs])
    for c in ws[3]:
        c.font = Font(bold=True)
    for j, k in enumerate(cells):
        ws.append([f"Cell_{k + 1}", int(include.get(k, 1))] +
                  [None if not np.isfinite(slopes[q][j]) else float(slopes[q][j]) for q in qs])
    on = [j for j, k in enumerate(cells) if include.get(k, 1)]
    ws.append([])
    for lab, fn in (("Mean (included)", lambda v: np.nanmean(v)),
                    ("SEM (included)", lambda v: np.nanstd(v, ddof=1) / np.sqrt(np.sum(np.isfinite(v)))
                     if np.sum(np.isfinite(v)) > 1 else np.nan),
                    ("n (included)", lambda v: float(np.sum(np.isfinite(v))))):
        row = [lab, ""]
        for q in qs:
            v = slopes[q][on] if on else np.zeros(0)
            with np.errstate(invalid="ignore"):
                r = fn(v) if v.size else np.nan
            row.append(None if not np.isfinite(r) else float(r))
        ws.append(row)
        ws.cell(row=ws.max_row, column=1).font = Font(bold=True)
    ws.column_dimensions["A"].width = 18
    for i in range(len(qs)):          # V3.0: AA, AB ... past Z (4 channels = 32 columns)
        ws.column_dimensions[get_column_letter(3 + i)].width = 28
    with new_output_file(path) as (used, stream):
        wb.save(stream)
    return str(used)


def _graph(path: Path, x, xlabel, y, quantity, style, file, comp, names) -> str:
    """The 300 dpi PNG of one quantity, drawn in your graph style
    (Settings.graph_style - the same look as the trace panel's 'As exported'
    view): y = the included cells (T x n). Returns the path written."""
    from .graphstyle import coerce, save_figure, title_text
    st = coerce(style)
    return save_figure(path, x, y, names, st, xlabel, quantity,
                       title_text(st, file, comp, quantity, y.shape[1]), fmt="png")


def run_export(out_root: str, exp: Experiment, s: Settings, comps: Dict[str, dict],
               keys: Sequence[str], src=None, background=None, t0: int = 0,
               roi_file_fn: Optional[Callable[[Path], Path]] = None,
               prefix: str = "", progress: ProgressFn = None,
               provenance: Optional[dict] = None) -> dict:
    """
    comps[c] = dict(label, name (for file names), M (every channel), cells,
               include {k: 0/1}, why {k: str}, qc, seeds, channel, rois [t][k]).
    provenance (v2.3): how the numbers were made - rules, track_params,
    fingerprint, nd2_path, comps, bg_auto, session_id (see provenance.py); it goes
    into each workbook's Settings / Methods sheets, the Prism notes and the
    Methods text file.
    Returns dict(folder, files).
    """
    keys = list(keys)
    movie = Path(exp.nd2_path).stem
    stem = clean_prefix(prefix) or movie[:40]     # your name for the files
    # V3.0 shorter paths: inside OUTPUT_<movie> the graphs, CSV, Prism graphs and ROI
    # pictures do not repeat the movie's name (the workbook, .pzfx and methods text
    # keep it, so a file copied elsewhere still says which movie); a name you typed
    # yourself is kept on every file
    short = "" if stem in (movie[:40], clean_prefix(movie), clean_prefix(movie)[:40]) else stem
    fpre = f"{short}_" if short else ""
    folder = Path(out_root) / f"Export_{dt.datetime.now():%Y-%m-%d_%H-%M-%S}"
    make_dirs(folder)
    files: List[str] = []
    T = exp.n_timepoints
    b = int(np.clip(s.baseline_timepoint - 1, 0, T - 1))
    x, xlabel = exp.time_axis(T, b)
    total = max(1, len(keys))
    done = [0]
    prov = dict(provenance or {})
    prov.setdefault("comps", [c for c in comps])
    prov_prism = dict(prov, baseline=int(s.baseline_timepoint))

    def tick(msg: str) -> None:
        done[0] += 1
        if progress and not progress(min(0.99, done[0] / total), msg):
            from .manual import Cancelled
            raise Cancelled()

    for c, d in comps.items():
        mine = [k.split("|", 1)[1] for k in keys if k.split("|", 1)[0] == c]
        if not mine:
            continue
        cdir = folder / _safe(d["label"])
        make_dirs(cdir)
        M: Measurements = d["M"]
        s2 = copy.copy(s)
        s2.roi_mode = d["name"]
        cells = list(d["cells"])
        on = [k for k in cells if d["include"].get(k, 1)]
        base = f"{stem}_{d['name']}"
        panels = {p[0]: p for p in _panels(M, s2)}
        if "excel" in mine:
            info = build_roi_info(exp, s2, M, cells, d["seeds"], t0, d.get("qc"))
            files.append(write_workbook(str(cdir / f"{base}.xlsx"), exp, s2, M, cells, info,
                                        qc=d.get("qc"), include=d["include"], why=d["why"],
                                        provenance=prov))
            tick(f"{d['label']}: Excel workbook written")
        chosen = [k.split("|", 1)[1] for k in mine if k.startswith("graph|")]
        qs = chosen or preferred_sheets(M, s2)
        a, z = int(getattr(s, "drift_from", 2)), int(getattr(s, "drift_to", 9))
        a, z = max(1, min(a, T)), max(1, min(z, T))
        drift = (a, z) if "drift" in mine and z - a >= 2 else None
        if "prism" in mine or drift:
            tpl = getattr(s, "prism_template", "") or None
            if tpl and (not exists(tpl) or not tpl.lower().endswith(".pzfx")):
                tpl = None
            # time courses (+ drift dot plots) in one file; drift alone gets its own file
            pz = cdir / (f"{base}.pzfx" if "prism" in mine else f"{base}_baseline_drift.pzfx")
            kw = dict(quantities=qs, drift=drift, time_courses="prism" in mine,
                      provenance=prov_prism)
            try:
                files += export_prism(str(pz), exp, s2, M, on, d["label"], template=tpl, **kw)
            except ValueError:                  # not a usable template: plain file only
                files += export_prism(str(pz), exp, s2, M, on, d["label"], **kw)
            tick(f"{d['label']}: Prism file written")
        if "prismgraph" in mine:
            from .plots import export_prism_graphs
            style = getattr(s, "prism_template", "") or None
            if style and (not exists(style) or not style.lower().endswith(".prism")):
                style = None
            files += export_prism_graphs(str(cdir / "Prism graphs"),
                                         f"{fpre}{d['name']}", exp, s2, M, on,
                                         d["label"], quantities=qs, drift=drift, template=style,
                                         style=getattr(s, "graph_style", None) or {}, file=stem)
            tick(f"{d['label']}: Prism graphs written")
        if drift:
            files.append(_drift_workbook(cdir / f"{base}_baseline_drift_T{a}-T{z}.xlsx",
                                         exp, M, s2, cells, d["include"], qs, a, z, x))
            tick(f"{d['label']}: baseline drift slopes written")
        if "csv" in mine:
            sub = cdir / "CSV"
            make_dirs(sub)
            for name, data, ylabel, _f, _e in panels.values():
                y = data[:, on] if on else np.zeros((T, 0))
                sm = describe(y)            # mean / SEM (SD/sqrt(n), n-1) / n per timepoint
                n, m, sem = sm.n, sm.mean, sm.sem
                sd = sm.sd
                with new_output_file(sub / f"{fpre}{_safe(nice(name).replace('/', '-'))}.csv") as (u, st):
                    rows = [[xlabel, "Timepoint"] + [f"Cell_{k + 1}" for k in on] +
                            ["Mean", "SEM", "n", "SD"]]
                    for t in range(T):
                        rows.append([f"{x[t]:.6g}", t + 1] +
                                    [("" if not np.isfinite(v) else f"{v:.6g}") for v in y[t]] +
                                    [("" if not np.isfinite(m[t]) else f"{m[t]:.6g}"),
                                     ("" if not np.isfinite(sem[t]) else f"{sem[t]:.6g}"), int(n[t]),
                                     ("" if not np.isfinite(sd[t]) else f"{sd[t]:.6g}")])
                    import io
                    buf = io.StringIO()
                    csv.writer(buf, lineterminator="\n").writerows(rows)
                    st.write(buf.getvalue().encode("utf-8"))
                files.append(str(u))
            tick(f"{d['label']}: CSV tables written")
        graphs = [k.split("|", 1)[1] for k in mine if k.startswith("graph|")]
        if graphs:
            sub = cdir / "Graphs"
            make_dirs(sub)
            for name in graphs:
                if name not in panels:
                    continue
                _n, data, ylabel, _f, _e = panels[name]
                y = data[:, on] if on else np.zeros((T, 0))
                p = sub / f"{fpre}{_safe(nice(name).replace('/', '-'))}.png"
                files.append(_graph(p, x, xlabel, y, nice(name),
                                    getattr(s, "graph_style", None) or {}, stem, d["label"],
                                    [f"Cell_{k + 1}" for k in on]))
                tick(f"{d['label']}: graph {nice(name)}")
        pics = [k for k in ("roi_drawn", "roi_last", "roi_every") if k in mine]
        if pics and src is not None:
            frames = []
            if "roi_drawn" in pics:
                frames.append((t0, "drawn"))
            if "roi_last" in pics and T - 1 != t0:
                frames.append((T - 1, "last"))
            if "roi_every" in pics:
                frames += [(t, "check") for t in range(0, T, 10) if (t, "drawn") not in frames]
            sub = cdir / "ROI pictures"
            make_dirs(sub)
            live = set(cells)
            fr = [(t, [r if k in live else None for k, r in enumerate(d["rois"][t])], tag)
                  for t, tag in frames]
            files += export_roi_images(str(sub), short, "", exp, src, d["name"], d["label"],
                                       d["channel"], fr, d["include"], background)
            tick(f"{d['label']}: ROI pictures")
    if "*|roifile" in keys and roi_file_fn is not None:
        files.append(str(roi_file_fn(folder)))
        tick("ROI file written")
    if "*|methods" in keys:
        from .provenance import methods_text
        text = methods_text(s, exp, prov.get("track_params") or None, None,
                            list(prov.get("comps") or comps), None, prov)
        with new_output_file(folder / f"{stem}_methods.txt") as (used, stream):
            stream.write(text.replace("\n", "\r\n").encode("utf-8"))   # Notepad-friendly
        files.append(str(used))
        tick("Methods text written")
    if "*|tiffs" in keys and src is not None:
        from .nd2io import export_tiffs
        e2 = copy.copy(exp)
        e2.out_dir = str(folder)
        e2.tiff_subdir = "Raw TIFFs"
        files.append(str(export_tiffs(src, e2, progress=lambda f, m: progress(
            min(0.99, (done[0] + f) / total), m) if progress else True)))
        tick("Raw TIFFs written")
    if "*|views" in keys and src is not None:
        from .nd2io import export_view_copies
        e2 = copy.copy(exp)
        e2.out_dir = str(folder)
        files.append(str(export_view_copies(src, e2, progress=lambda f, m: progress(
            min(0.99, (done[0] + f) / total), m) if progress else True)))
        tick("Viewing copies written")
    return dict(folder=str(folder), files=files)


GRAPH_FORMATS = ("prism", "png", "svg")


def longest_path(out_root, nd2_path, prefix: str, comps: Sequence[tuple]) -> int:
    """V3.0: about how long the longest path of an export into out_root will be
    (comps: (label, file name) per compartment) - to warn before writing files
    Windows Explorer / Excel may not open (over 260 characters with long paths
    off)."""
    movie = Path(str(nd2_path)).stem
    stem = clean_prefix(prefix) or movie[:40]
    short = "" if stem in (movie[:40], clean_prefix(movie), clean_prefix(movie)[:40]) else stem
    pre = short + "_" if short else ""             # (one character per path separator)
    root = len(str(Path(out_root))) + len("/Export_2026-01-01_00-00-00")
    worst = 0
    for label, name in comps or [("Nucleus", "nucleus")]:
        cdir = root + 1 + len(_safe(label))
        workbook = len(f"/{stem}_{name}_baseline_drift_T10-T10.xlsx")
        graph = len(f"/Prism graphs/{pre}{name}_R-R0_mCherry-mCherry.prism")
        pics = len(f"/ROI pictures/{pre}{name}_ROIs_t100_check.png")
        worst = max(worst, cdir + max(workbook, graph, pics))
    return worst


def graph_file_name(stem: str, comp_name: str, quantity: str) -> str:
    """'<file>_<compartment>_<quantity>' as the export names it, e.g.
    'cells_nucleus_R-R0_GFP-Cy5' for 'R/R0 - GFP/Cy5' (or 'R/R0 GFP/Cy5')."""
    q = str(quantity).replace(" - ", " ", 1).replace("/", "-").replace(" ", "_")
    return clean_prefix("_".join(p for p in (stem, comp_name, q) if p), 150) or "graph"


def save_graph_files(folder, name: str, formats: Sequence[str], x, y, names: Sequence[str],
                     style, x_label: str, y_label: str, title: str, quantity: str,
                     notes: str = "", nd2_name: str = "", template: Optional[str] = None,
                     progress: ProgressFn = None) -> List[str]:
    """
    'Save this graph' (trace panel, 'As exported' view): ONE quantity of one
    compartment, the included cells only (y = T x n, names 'Cell_k').
      png / svg  drawn by graphstyle.save_figure in `style` - exactly the live
                 view (PNG at 300 dpi; SVG keeps the text as text)
      prism      a Prism 10+ project made from the Prism template (built-in, or
                 your own .prism `template`): the same data, titles and graph
                 style (graphstyle.PRISM_SUPPORT; looks Prism cannot draw get
                 the closest Prism look, graphstyle.prism_look). A template of
                 your own not made from PeterPiper's keeps its own look.
    x_label / y_label are the automatic axis titles (the style may replace
    them). Never overwrites (adds _2, _3 ...). Returns the paths written.
    """
    from .graphstyle import axis_titles, coerce, save_figure
    from .safety import make_dirs
    st = coerce(style)
    folder = Path(folder)
    make_dirs(folder)
    name = clean_prefix(name, 150) or "graph"
    y = np.asarray(y, float)
    want = [f for f in GRAPH_FORMATS if f in set(formats)]
    out: List[str] = []
    for i, f in enumerate(want):
        if progress and not progress(i / max(1, len(want)), f"Saving the graph ({f.upper()})"):
            from .manual import Cancelled
            raise Cancelled()
        if f == "prism":
            from .prismfile import write_prism
            tpl = template if template and str(template).lower().endswith(".prism") \
                and exists(template) else None
            xt, yt = axis_titles(st, x_label, y_label)
            out.append(write_prism(str(folder / f"{name}.prism"), np.asarray(x, float), xt,
                                   quantity, yt, y, list(names), title or " ", notes,
                                   template=tpl, name=nd2_name, style=st.to_dict()))
        else:
            out.append(save_figure(folder / f"{name}.{f}", x, y, list(names), st, x_label,
                                   y_label, title, fmt=f))
    return out
