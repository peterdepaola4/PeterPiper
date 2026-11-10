"""
The quantities of the results workbook as graphs and Prism files.

    _panels()               every plottable quantity of one compartment, named as
                            its Excel sheet: BgSub_<ch> (background-subtracted),
                            dFF_<ch> (F/F0), R_<a>_over_<b> (ratio), dRR_<a>_over_<b>
                            (R/R0)
    export_prism()          the numbers as a Prism .pzfx (any Prism version)
    export_prism_graphs()   Prism 10+ projects with the graph made (prismfile.py)
    export_roi_images()     the ROI pictures (outlines on the image, numbered as in
                            Excel)

The time-course PNG graphs are drawn by graphstyle.save_figure (export._graph).
Uses matplotlib's object API (no pyplot), so it is safe to call from a worker
thread.

BLOCK: a new sheet type = one more entry in _panels().
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

import numpy as np

from .config import Experiment, Settings
from .excel import _sheet, short_tags
from .measure import Measurements
from .safety import new_output_file

ProgressFn = Optional[Callable[[float, str], bool]]


def _panels(M: Measurements, s: Settings) -> List[Tuple[str, np.ndarray, str, bool, Optional[np.ndarray]]]:
    """(sheet name, T x N data, y label, is_fold_change, extra line) per sheet."""
    tags = short_tags(M.channels)
    b = int(np.clip(s.baseline_timepoint - 1, 0, M.n_timepoints - 1))
    k = float(getattr(s, "ratio_min_snr", 5.0))      # V3.0: too dim at baseline = blank
    bs = M.bg_subtracted()
    out = []
    # Every graph is background-subtracted; the raw numbers stay in the Raw_ sheets.
    for c, (ch, tg) in enumerate(zip(M.channels, tags)):
        out.append((_sheet("BgSub_", tg), bs[:, c, :], f"{ch} - background (counts)",
                    False, None))
    for c, (ch, tg) in enumerate(zip(M.channels, tags)):
        out.append((_sheet("dFF_", tg), M.ff0(c, b, k), f"{ch} F/F0", True, None))
    if s.write_ratio_sheets:
        for a, c in M.channel_pairs():
            na, nc = M.channels[a], M.channels[c]
            out.append((_sheet("R_", tags[a], "over", tags[c]), M.ratio_checked(a, c, b, k),
                        f"{na}/{nc}", False, None))
            out.append((_sheet("dRR_", tags[a], "over", tags[c]), M.rr0(a, c, b, k),
                        f"{na}/{nc} R/R0", True, None))
    return out


def preferred_sheets(M: Measurements, s: Settings) -> List[str]:
    """Your key quantities (Settings.resp_quantity, e.g. 'F/F0 - GFP; R/R0 - GFP/Cy5')
    as sheet names, R/R0 first: ['dRR_GFP_over_Cy5', 'dFF_GFP']."""
    tags = dict(zip(M.channels, short_tags(M.channels)))
    out = []
    for q in str(getattr(s, "resp_quantity", "") or "").split(";"):
        q = q.strip()
        if q.startswith("R/R0 - ") and "/" in q[7:]:
            a, b = q[7:].split("/", 1)
            if a.strip() in tags and b.strip() in tags:
                out.append(f"dRR_{tags[a.strip()]}_over_{tags[b.strip()]}")
        elif q.startswith("F/F0 - ") and q[7:].strip() in tags:
            out.append(f"dFF_{tags[q[7:].strip()]}")
    return sorted(out, key=lambda n: 0 if n.startswith("dRR_") else 1)


def drift_slopes(data: np.ndarray, x: np.ndarray, t_from: int, t_to: int) -> np.ndarray:
    """
    Baseline drift: per cell (column of data, T x N), the slope of the least-
    squares straight line through timepoints t_from..t_to (1-based, inclusive)
    against x (minutes, or timepoints when the interval is unknown). Needs at
    least 3 valid points; otherwise NaN.
    """
    a, b = int(t_from) - 1, int(t_to)
    xs = np.asarray(x, float)[a:b]
    out = np.full(data.shape[1], np.nan)
    for k in range(data.shape[1]):
        y = np.asarray(data[a:b, k], float)
        ok = np.isfinite(y) & np.isfinite(xs)
        if ok.sum() >= 3 and np.ptp(xs[ok]) > 0:
            out[k] = float(np.polyfit(xs[ok], y[ok], 1)[0])
    return out


def nice_name(sheet: str) -> str:
    """'dRR_GFP_over_Cy5' -> 'R/R0 GFP/Cy5'."""
    for p, lab in (("dRR_", "R/R0"), ("dFF_", "F/F0"), ("R_", "Ratio"), ("BgSub_", "Intensity")):
        if sheet.startswith(p):
            return f"{lab} {sheet[len(p):].replace('_over_', '/')}"
    return sheet


def export_prism(path: str, exp: Experiment, s: Settings, M: Measurements,
                 cells: Sequence[int], label: str = "", quantities=None,
                 template: Optional[str] = None, drift: Optional[tuple] = None,
                 time_courses: bool = True,
                 provenance: Optional[dict] = None) -> List[str]:
    """The graphs' numbers (included cells, 0 = baseline) as a Prism .pzfx file -
    only `quantities` (sheet names) if given, your key quantity first; plus a
    '_with_graphs' copy when a Prism template is given. drift = (from, to):
    also one dot-plot table per quantity of each cell's baseline drift slope.
    time_courses=False writes only those. provenance (v2.3: rules, baseline,
    fingerprint) adds one line to the Prism notes. Returns the paths."""
    from .prism import write_pzfx
    T = M.n_timepoints
    b = int(np.clip(s.baseline_timepoint - 1, 0, T - 1))
    x, xlabel = exp.time_axis(T, b)
    cells = list(cells)
    names = [f"Cell_{k + 1}" for k in cells]
    rank = {"dRR_": 0, "dFF_": 1, "R_": 2, "BgSub_": 3}
    pref = preferred_sheets(M, s)                 # your key quantity first (R/R0 GFP/Cy5)
    panels = sorted(_panels(M, s), key=lambda p: (
        pref.index(p[0]) if p[0] in pref else len(pref),
        next((v for k, v in rank.items() if p[0].startswith(k)), 9)))
    if quantities:
        panels = [p for p in panels if p[0] in set(quantities)] or panels
    data = [(nice_name(name), ylabel, d[:, cells] if cells else np.zeros((T, 0)), names)
            for name, d, ylabel, _f, _e in panels]
    cols = []
    if drift:
        a, z = drift
        unit = "per min" if exp.seconds_per_frame > 0 else "per timepoint"
        for name, d, ylabel, _f, _e in panels:
            sl = drift_slopes(d[:, cells] if cells else np.zeros((T, 0)), x, a, z)
            cols.append((f"Baseline drift slope T{a}-T{z} - {nice_name(name)}",
                         f"{nice_name(name)} slope ({unit})", sl, names))
    return write_pzfx(path, x, xlabel, data if time_courses else [],
                      notes=f"{label} - {Path(exp.nd2_path).name}. Included cells only; "
                            f"X = time from the baseline (timepoint {b + 1} = 0)."
                            + (f" Baseline drift = slope of a straight-line fit through "
                               f"timepoints {drift[0]}-{drift[1]}." if drift else ""),
                      template=template, columns=cols, provenance=provenance)


def export_prism_graphs(folder: str, stem: str, exp: Experiment, s: Settings, M: Measurements,
                        cells: Sequence[int], label: str = "", quantities=None,
                        drift: Optional[tuple] = None,
                        template: Optional[str] = None, style: Optional[dict] = None,
                        file: str = "") -> List[str]:
    """
    One Prism 10+ project (.prism) per quantity WITH THE GRAPH MADE from the
    included cells, plus the tables 'mean, SEM, n', 'each cell' and (drift =
    (from, to)) the baseline drift slopes. Returns the paths.
    style (Settings.graph_style, the live graph's look): written into the
    .prism graph - error type, colours, line widths, symbols, each cell, axis
    ranges, font size, title template and axis titles (prismstyle.SUPPORT);
    looks Prism cannot draw get the closest Prism look (graphstyle.prism_look).
    {file} in the title = file - the same text as the PNG. None = the
    template's own look (built-in: mean +/- SEM) with the title
    file - compartment (n). A `template` of your own that was not made from
    PeterPiper's .prism keeps its own look (only the data and texts are set).
    """
    from .prismfile import write_prism
    from .graphstyle import axis_titles, coerce, prism_summary, title_text
    T = M.n_timepoints
    b = int(np.clip(s.baseline_timepoint - 1, 0, T - 1))
    x, xlabel = exp.time_axis(T, b)
    cells = list(cells)
    names = [f"Cell_{k + 1}" for k in cells]
    panels = {p[0]: p for p in _panels(M, s)}
    qs = [q for q in (quantities or preferred_sheets(M, s)) if q in panels] or         [p for p in panels if p.startswith("dRR_")][:1] or list(panels)[:1]
    out = []
    unit = "per min" if exp.seconds_per_frame > 0 else "per timepoint"
    st = coerce(style) if style is not None else None
    for q in qs:
        _n, d, _yl, _f, _e = panels[q]
        y = d[:, cells] if cells else np.zeros((T, 0))
        nm = nice_name(q)
        dr = None
        if drift:
            a, z = drift
            dr = (f"Baseline drift slope T{a}-T{z} - {nm}", f"{nm} slope ({unit})",
                  drift_slopes(y, x, a, z))
        if st is None:
            shown = "mean +/- SEM (error bars)"
        else:
            shown = prism_summary(st)
            if template and not _takes_style(template):
                shown = "the look of your own Prism template"
        notes = (f"{label} - {Path(exp.nd2_path).name}. {len(cells)} included cells; X = time "
                 f"from the baseline (timepoint {b + 1} = 0). Values are background-subtracted. "
                 f"The graph shows {shown} of the included cells (SEM = SD / sqrt(n), "
                 f"SD with n - 1). The 'mean, SEM, n' table always gives the SEM.")
        notes = notes.replace("±", "+/-")
        fn = Path(folder) / f"{stem}_{nm.replace('/', '-').replace(' ', '_')}.prism"
        if st is None:
            title = f"{Path(exp.nd2_path).stem[:60]} - {label} (n = {len(cells)})"
            xt, yt = xlabel, nm
        else:
            title = title_text(st, file or Path(exp.nd2_path).stem[:40], label, nm, len(cells))
            xt, yt = axis_titles(st, xlabel, nm)
        out.append(write_prism(str(fn), x, xt, nm, yt, y, names, title or " ",
                               notes, drift=dr, template=template,
                               name=Path(exp.nd2_path).stem,
                               style=None if st is None else st.to_dict()))
    return out


def _takes_style(template) -> bool:
    from .prismfile import template_takes_style
    return template_takes_style(template)


def export_roi_images(out_dir: str, stem: str, stamp: str, exp: Experiment, src,
                      name: str, label: str, channel: int, frames, include,
                      background=None) -> List[str]:
    """
    One PNG per (timepoint, ROIs) in `frames`: that frame of the ROI type's own
    channel with every ROI drawn on it - included ones in their cell colour
    (the same as in the app and the traces) with the cell number, excluded ones
    grey dashed, the background region green.
    """
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    palette = ["#3fa9ff", "#ff4b4b", "#2ecc40", "#ffa31a", "#d65cff", "#00c8c8",
               "#ff5fb0", "#b8b800", "#ff7f50", "#8c8cff"]      # same colours as the app
    out = []
    H, W = exp.height, exp.width
    scale = 1.0                          # full resolution: one image pixel per pixel
    for t, rois, tag in frames:
        plane = np.asarray(src.frame(int(t))[min(channel, exp.n_channels - 1)], float)
        lo, hi = np.percentile(plane[::2, ::2], (1.0, 99.7))
        hs, ws_, top = H * scale, W * scale, 30.0          # pixels; a title strip on top
        fig = Figure(figsize=(ws_ / 100, (hs + top) / 100), dpi=100)
        FigureCanvasAgg(fig)
        ax = fig.add_axes([0, 0, 1, hs / (hs + top)])
        ax.imshow(plane, cmap="gray", vmin=lo, vmax=max(hi, lo + 1), interpolation="nearest")
        n_in = 0
        for k, r in enumerate(rois):
            if r is None or not r.area:
                continue
            on = bool(include.get(k, 0)) if include is not None else bool(r.include)
            n_in += on
            col = palette[k % len(palette)] if on else "#b4b4b4"
            pts = r.contours()
            for p in pts:
                ax.plot(np.r_[p[:, 0], p[:1, 0]], np.r_[p[:, 1], p[:1, 1]], color=col,
                        lw=1.4 if on else 0.8, ls="-" if on else (0, (3, 2)))
            if pts:                        # the number just outside the outline
                y0, x0, y1, x1 = r.bbox
                above = y0 - 3 > 0.04 * H
                ax.text((x0 + x1) / 2, y0 - 3 if above else y1 + 3, str(k + 1),
                        color=col if on else "#d0d0d0", fontsize=8, ha="center",
                        va="bottom" if above else "top", fontweight="bold")
        if background is not None:
            for p in background.contours():
                ax.plot(np.r_[p[:, 0], p[:1, 0]], np.r_[p[:, 1], p[:1, 1]], color="#22dd22",
                        lw=1.2)
        ax.set_xlim(-0.5, W - 0.5)
        ax.set_ylim(H - 0.5, -0.5)
        ax.axis("off")
        fig.suptitle(f"{label} - timepoint {t + 1} ({tag}) - {n_in} included in colour, "
                     f"excluded grey dashed, background green  -  {Path(exp.nd2_path).stem[:40]}",
                     fontsize=8, y=1 - 4 / (hs + top), va="top")
        path = Path(out_dir) / ("_".join(p for p in (stem, name) if p) + f"_ROIs_t{t + 1}_{tag}" +
                                (f"_{stamp}" if stamp else "") + ".png")
        with new_output_file(path) as (used, stream):
            fig.savefig(stream, format="png", facecolor="white")
        out.append(str(used))
    return out

