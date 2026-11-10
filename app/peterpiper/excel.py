"""
Writing the results workbook.

Layout (one sheet each unless stated):

    Raw_<channel>        numbers, as measured:
                           A Timepoint | B Background | C.. one column per cell
                           last column: Time_min
    BgSub_<channel>      = Raw cell - Raw background of the same channel
    dFF_<channel>        = BgSub / BgSub at the baseline timepoint   (F/F0)
    R_<a>_over_<b>       = BgSub_a / BgSub_b, for every ordered pair of channels
    dRR_<a>_over_<b>     = R / R at the baseline timepoint           (R/R0)
    Sum_<channel>        V2.5: the raw sum of every pixel of each ROI (and of the
                         background pixels used) per timepoint - the numbers behind
                         Raw: Raw = Sum / Area_px of the same cell and timepoint
    Area_px, Area_um2    V2.5: each ROI's area (its mask at that timepoint) and the
                         background pixels used (after that timepoint's exclusions)
    ROI_info             one row per cell: size, tracking quality, saturation
    Settings             the baseline-timepoint dropdown plus every acquisition and
                         analysis value actually used (provenance.parameter_table)
    Methods              LAST sheet: a ready-to-edit methods text with references,
                         every parameter with its meaning, the software versions
                         and which .nd2 file it was (provenance.py)

Only the Raw sheets contain numbers. Everything else is a live Excel formula
pointing at the named cell `BaselineTP`, so changing the dropdown on the
Settings sheet re-normalises every dFF and dRR sheet instantly. The dropdown and
its helper cells keep fixed addresses (Settings!B4, B5, B6 and the hidden
E2:E<T+1>) - every formula refers to them.

BLOCK: to add a new derived sheet, write one more _write_derived(...) call in
write_workbook() - the dropdown wiring comes for free.
"""
from __future__ import annotations

import datetime as _dt
import re
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

import numpy as np

from . import APP_NAME, __version__
from .config import Experiment, Settings
from .measure import Measurements
from .safety import new_output_file

ProgressFn = Optional[Callable[[float, str], bool]]

# Also replace apostrophes so user labels cannot break quoted formula references.
_BAD_SHEET = re.compile(r"[:\\/?*\[\]']")


# --------------------------------------------------------------------------
#  Sheet-name helpers (Excel allows 31 characters and forbids : \ / ? * [ ])
# --------------------------------------------------------------------------
def _clean(name: str) -> str:
    return _BAD_SHEET.sub("_", str(name)).strip() or "Ch"


def short_tags(channels: Sequence[str], width: int = 7) -> List[str]:
    """Short, unique, Excel-safe abbreviations for the channel names."""
    tags: List[str] = []
    for nm in channels:
        t = _clean(nm).replace(" ", "")[:width] or "Ch"
        base, n = t, 2
        while t in tags:
            t = f"{base[:width - 1]}{n}"
            n += 1
        tags.append(t)
    return tags


def _sheet(prefix: str, *parts: str) -> str:
    return _clean(prefix + "_".join(parts))[:31]


# --------------------------------------------------------------------------
#  Main writer
# --------------------------------------------------------------------------
def write_workbook(path: str, exp: Experiment, s: Settings, M: Measurements,
                   cells: Sequence[int], roi_info: Sequence[Dict],
                   progress: ProgressFn = None, qc=None,
                   include: Optional[Dict[int, int]] = None,
                   why: Optional[Dict[int, str]] = None,
                   provenance: Optional[dict] = None) -> str:
    """
    Write the results workbook. `cells` are the ROIs exported; `include` maps
    each to 1 (counted) or 0 (exported but switched off) - the user can flip
    these on the Include sheet and every mean, SEM, n and chart follows.

    provenance (optional) - what the Settings and Methods sheets record:
        rules         the tracking rules (texts or rule dicts)
        track_params  manual.track_cells out["params"]
        fingerprint   history.nd2_fingerprint() of the .nd2
        nd2_path      full path of the .nd2 (default: exp.nd2_path)
      and, if known: comps (every compartment analysed), bg_auto (bool),
      redrawn ({comp: fraction}), session_id. None = the settings and the code's
      fixed values are shown, and the sheets say the tracker did not record them.

    Returns the path actually written.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation
    from openpyxl.worksheet.formula import ArrayFormula

    T = M.n_timepoints
    idx = list(cells)
    N = len(idx)
    tags = short_tags(M.channels)
    head_font = Font(bold=True)
    head_fill = PatternFill("solid", fgColor="DDE6F0")
    note_font = Font(italic=True, color="555555")

    wb = Workbook()
    wb.remove(wb.active)

    first_cell_col = 3                      # A timepoint, B background, C.. cells
    time_col = first_cell_col + N           # Time_min goes after the last cell
    cell_names = [f"Cell_{k + 1}" for k in idx]
    include = {k: int(include.get(k, 1)) for k in idx} if include else {k: 1 for k in idx}
    why = why or {}
    INC_ROW = T + 3                         # per sheet: row of 1/0 include switches
    mean_col, sem_col, n_col = time_col + 1, time_col + 2, time_col + 3
    sd_col = time_col + 4                   # V3.0: SD as well (the default error)
    plot_col0 = time_col + 5                # hidden chart columns start here
    last_cell = get_column_letter(first_cell_col + max(N, 1) - 1)
    first_cell = get_column_letter(first_cell_col)
    charts: List[tuple] = []                # (sheet title, y label) for the Graphs sheet

    # ------------------------------------------------------------- Include
    inc_ws = wb.create_sheet("Include")
    inc_ws.cell(row=1, column=1, value="Cell").font = head_font
    inc_ws.cell(row=1, column=2, value="Include (1 = yes, 0 = no)").font = head_font
    inc_ws.cell(row=1, column=3, value="Why (the app's decision)").font = head_font
    for c in range(1, 4):
        inc_ws.cell(row=1, column=c).fill = head_fill
    yellow = PatternFill("solid", fgColor="FFF2CC")
    for j, k in enumerate(idx):
        inc_ws.cell(row=j + 2, column=1, value=cell_names[j])
        b = inc_ws.cell(row=j + 2, column=2, value=include[k])
        b.fill = yellow
        b.font = Font(bold=True, color="0B5394")
        b.alignment = Alignment(horizontal="center")
        w = inc_ws.cell(row=j + 2, column=3, value=why.get(k, "kept" if include[k] else ""))
        w.data_type = "s"
    if N:
        dv_inc = DataValidation(type="list", formula1='"1,0"', allow_blank=False)
        dv_inc.error = "Type 1 to include the cell or 0 to leave it out."
        dv_inc.prompt = "1 = counted in the means and charts, 0 = left out."
        inc_ws.add_data_validation(dv_inc)
        dv_inc.add(f"B2:B{N + 1}")
    inc_ws.column_dimensions["A"].width = 12
    inc_ws.column_dimensions["B"].width = 24
    inc_ws.column_dimensions["C"].width = 70
    inc_ws.freeze_panes = "A2"
    inc_ws.cell(row=N + 3, column=1,
                value="Change a 1 to 0 (or 0 to 1) to drop / restore a cell. Every "
                      "'Mean (included)', 'SEM', 'n' column and every chart on the "
                      "Graphs sheet updates. The per-cell numbers never change.").font = note_font

    def header(ws, bg_label: str) -> None:
        ws.cell(row=1, column=1, value="Timepoint")
        ws.cell(row=1, column=2, value=bg_label)
        for j, nm in enumerate(cell_names):
            ws.cell(row=1, column=first_cell_col + j, value=nm)
        ws.cell(row=1, column=time_col,
                value="Time_min (0 = baseline)" if exp.seconds_per_frame > 0
                else "Timepoints from baseline")
        for c in range(1, time_col + 1):
            h = ws.cell(row=1, column=c)
            h.font = head_font
            h.fill = head_fill
            h.alignment = Alignment(horizontal="center")
        ws.freeze_panes = "C2"
        ws.column_dimensions["A"].width = 11
        ws.column_dimensions["B"].width = 13

    def time_column(ws) -> None:
        # 0 at the baseline chosen on the Settings sheet, negative before it -
        # follows the baseline dropdown like every dFF / dRR value
        f = exp.seconds_per_frame / 60.0 if exp.seconds_per_frame > 0 else 1.0
        for t in range(T):
            ws.cell(row=t + 2, column=time_col,
                    value=f"=ROUND(($A{t + 2}-Settings!$B$4)*{f!r},4)")
        finish(ws)

    def finish(ws) -> None:
        """Include switches, included-only Mean / SEM / n, hidden chart columns."""
        if not N:
            return
        ws.cell(row=INC_ROW, column=1, value="Include").font = head_font
        ws.cell(row=INC_ROW, column=2, value="(Include sheet)").font = note_font
        for j in range(N):
            ws.cell(row=INC_ROW, column=first_cell_col + j, value=f"=Include!$B${j + 2}")
        for col, label in ((mean_col, "Mean (included)"), (sem_col, "SEM (included)"),
                           (n_col, "n (included)"), (sd_col, "SD (included)")):
            h = ws.cell(row=1, column=col, value=label)
            h.font, h.fill = head_font, head_fill
            ws.column_dimensions[get_column_letter(col)].width = 15
        inc = f"${first_cell}${INC_ROW}:${last_cell}${INC_ROW}"
        for t in range(T):
            r = t + 2
            rng = f"{first_cell}{r}:{last_cell}{r}"
            ncell = f"{get_column_letter(n_col)}{r}"
            ws.cell(row=r, column=mean_col, value=f'=IFERROR(AVERAGEIFS({rng},{inc},1),"")')
            ws.cell(row=r, column=n_col, value=f"=SUMPRODUCT(({inc}=1)*ISNUMBER({rng}))")
            ref = f"{get_column_letter(sem_col)}{r}"
            ws[ref] = ArrayFormula(ref, f'=IFERROR(STDEV(IF(({inc}=1)*ISNUMBER({rng}),'
                                        f'{rng}))/SQRT({ncell}),"")')
            ref = f"{get_column_letter(sd_col)}{r}"
            ws[ref] = ArrayFormula(ref, f'=IFERROR(STDEV(IF(({inc}=1)*ISNUMBER({rng}),'
                                        f'{rng})),"")')
        # chart copies: the value if included, #N/A (a gap in the chart) if not
        for j in range(N):
            src = get_column_letter(first_cell_col + j)
            col = plot_col0 + j
            ws.cell(row=1, column=col, value=cell_names[j])
            for t in range(T):
                r = t + 2
                ws.cell(row=r, column=col,
                        value=f"=IF(AND({src}${INC_ROW}=1,ISNUMBER({src}{r})),{src}{r},NA())")
            ws.column_dimensions[get_column_letter(col)].hidden = True

    steps = max(1, 2 * M.n_channels + (2 * len(M.channel_pairs()) if s.write_ratio_sheets else 0) + 4)
    done = 0

    def tick(msg: str) -> None:
        nonlocal done
        done += 1
        if progress:
            progress(min(0.99, done / steps), msg)

    # ---------------------------------------------------------------- Raw
    bgsub_names: List[str] = []
    for c, (ch, tag) in enumerate(zip(M.channels, tags)):
        ws = wb.create_sheet(_sheet("Raw_", tag))
        header(ws, "Background")
        for t in range(T):
            ws.cell(row=t + 2, column=1, value=t + 1)
            bg = M.background[t, c]
            ws.cell(row=t + 2, column=2,
                    value=None if not np.isfinite(bg) else round(float(bg), 3))
            for j, k in enumerate(idx):
                v = M.mean[t, c, k]
                ws.cell(row=t + 2, column=first_cell_col + j,
                        value=None if not np.isfinite(v) else round(float(v), 3))
        time_column(ws)
        tick(f"Writing raw intensities - {ch}")

    # ------------------------------------------------------- Background-sub
    for c, (ch, tag) in enumerate(zip(M.channels, tags)):
        raw = _sheet("Raw_", tag)
        ws = wb.create_sheet(_sheet("BgSub_", tag))
        bgsub_names.append(ws.title)
        header(ws, "Background")
        ws.cell(row=T + 5, column=1,
                value="Each cell = its raw mean minus the background ROI mean of this channel.").font = note_font
        for t in range(T):
            r = t + 2
            ws.cell(row=r, column=1, value=t + 1)
            ws.cell(row=r, column=2, value=f"='{raw}'!B{r}")
            for j in range(N):
                col = get_column_letter(first_cell_col + j)
                ws.cell(row=r, column=first_cell_col + j,
                        value=f"=IFERROR('{raw}'!{col}{r}-'{raw}'!$B{r},\"\")")
        time_column(ws)
        tick(f"Writing background-subtracted values - {ch}")

    # ------------------------------------------------ V3.0 ratio check: noise
    # the noise of each ROI's mean (background pixel SD / sqrt(ROI pixels)); a cell's
    # F/F0, ratio and R/R0 are blank when a channel they use is below MinSNR (Settings
    # sheet) x this at the baseline, and a ratio's points where its denominator is
    noise_names: List[str] = []
    for c, (ch, tag) in enumerate(zip(M.channels, tags)):
        nz = M.mean_noise(c)
        ws = wb.create_sheet(_sheet("Noise_", tag))
        noise_names.append(ws.title)
        header(ws, "Background SD")
        ws.cell(row=T + 5, column=1, value=(
            f"Noise of each ROI's mean in {ch}: the background region's pixel SD (column B) "
            f"/ sqrt(the ROI's pixels). With MinSNR on the Settings sheet it decides which "
            f"F/F0, ratio and R/R0 values are left out (dividing by almost nothing)."
            if nz is not None else "Not recorded for this analysis (tracked before V2.2): "
                                   "nothing is left out.")).font = note_font
        for t in range(T):
            ws.cell(row=t + 2, column=1, value=t + 1)
            if nz is None:
                continue
            sd = M.background_sd[t, c]
            ws.cell(row=t + 2, column=2,
                    value=None if not np.isfinite(sd) else round(float(sd), 4))
            for j, kk in enumerate(idx):
                v = nz[t, kk]
                ws.cell(row=t + 2, column=first_cell_col + j,
                        value=None if not np.isfinite(v) else round(float(v), 4))
        time_column(ws)

    def dim(sheet: str, noise: str, col: str, row) -> str:
        """Excel test: this channel too dim at that row (V3.0 ratio check)."""
        return (f"AND(MinSNR>0,ISNUMBER('{noise}'!{col}{row}),ISNUMBER('{sheet}'!{col}{row}),"
                f"'{sheet}'!{col}{row}<MinSNR*'{noise}'!{col}{row})")

    def dim_base(sheet: str, noise: str, col: str) -> str:
        """... at the baseline row (the Settings dropdown)."""
        return (f"AND(MinSNR>0,ISNUMBER(INDEX('{noise}'!{col}:{col},BaselineRow)),"
                f"ISNUMBER(INDEX('{sheet}'!{col}:{col},BaselineRow)),"
                f"INDEX('{sheet}'!{col}:{col},BaselineRow)"
                f"<MinSNR*INDEX('{noise}'!{col}:{col},BaselineRow))")

    # ------------------------------------------------------------ helpers
    def write_derived(title: str, formula_for, note: str) -> str:
        ws = wb.create_sheet(title)
        header(ws, "Background")
        ws.cell(row=T + 5, column=1, value=note).font = note_font
        for t in range(T):
            r = t + 2
            ws.cell(row=r, column=1, value=t + 1)
            for j in range(N):
                col = get_column_letter(first_cell_col + j)
                ws.cell(row=r, column=first_cell_col + j, value=formula_for(col, r))
        time_column(ws)
        return ws.title

    # ------------------------------------------------------------- dF/F
    for c, (ch, tag) in enumerate(zip(M.channels, tags)):
        bs, nzs = bgsub_names[c], noise_names[c]
        charts.append((_sheet("dFF_", tag), f"{ch} F/F0", f"F/F0 - {ch}"))
        write_derived(
            _sheet("dFF_", tag),
            lambda col, r, bs=bs, nzs=nzs: (f"=IF({dim_base(bs, nzs, col)},\"\","
                                            f"IFERROR('{bs}'!{col}{r}"
                                            f"/INDEX('{bs}'!{col}:{col},BaselineRow),\"\"))"),
            f"F/F0 fold change for {ch}: background-subtracted intensity divided by its "
            f"value at the baseline timepoint set on the Settings sheet. Baseline reads 1.0. "
            f"Blank = {ch} too dim at the baseline (MinSNR x its Noise_ sheet).")
        tick(f"Writing F/F0 - {ch}")

    # ------------------------------------------------- ratios and dR/R
    if s.write_ratio_sheets:
        for a, b in M.channel_pairs():
            ta, tb = tags[a], tags[b]
            sa, sb = bgsub_names[a], bgsub_names[b]
            na_, nb_ = noise_names[a], noise_names[b]
            rname = write_derived(
                _sheet("R_", ta, "over", tb),
                lambda col, r, sa=sa, sb=sb, na_=na_, nb_=nb_: (
                    f"=IF(OR({dim_base(sa, na_, col)},{dim_base(sb, nb_, col)},"
                    f"{dim(sb, nb_, col, r)}),\"\","
                    f"IFERROR('{sa}'!{col}{r}/'{sb}'!{col}{r},\"\"))"),
                f"Ratio of background-subtracted {M.channels[a]} to {M.channels[b]}. Blank = "
                f"either channel too dim at the baseline, or {M.channels[b]} too dim at that "
                f"timepoint (MinSNR x the Noise_ sheets).")
            charts.append((_sheet("dRR_", ta, "over", tb),
                           f"{M.channels[a]}/{M.channels[b]} R/R0",
                           f"R/R0 - {M.channels[a]}/{M.channels[b]}"))
            write_derived(
                _sheet("dRR_", ta, "over", tb),
                lambda col, r, rname=rname: (f"=IFERROR('{rname}'!{col}{r}"
                                             f"/INDEX('{rname}'!{col}:{col},BaselineRow),\"\")"),
                f"R/R0 fold change of the {M.channels[a]}/{M.channels[b]} ratio, "
                f"normalised to the baseline timepoint. Baseline reads 1.0.")
            tick(f"Writing ratios - {M.channels[a]}/{M.channels[b]}")

    # ------------------------------------------- Sum and Area (V2.5)
    # the raw numbers behind every mean: Raw = Sum / Area_px, cell by cell and
    # timepoint by timepoint (background: its sum / the pixels used that timepoint)
    a_um2 = float(exp.um_per_px) ** 2

    def exact(v):
        """A measured number as written: whole numbers as integers (exact)."""
        if v is None or not np.isfinite(v):
            return None
        f = float(v)
        return int(f) if f.is_integer() and abs(f) < 2 ** 53 else f

    bg_npx = getattr(M, "background_npx", None)
    for label, scale in (("Area_px", None), ("Area_um2", a_um2)):
        ws = wb.create_sheet(label)
        header(ws, "Background (px used)" if scale is None else "Background (um2 used)")
        for t in range(T):
            ws.cell(row=t + 2, column=1, value=t + 1)
            if bg_npx is not None:
                n = int(bg_npx[t])
                ws.cell(row=t + 2, column=2, value=n if scale is None else n * scale)
            for j, k in enumerate(idx):
                a = int(M.area_px[t, k])
                ws.cell(row=t + 2, column=first_cell_col + j, value=a if scale is None else a * scale)
        note = ("Each ROI's area at each timepoint: the pixels of its mask in that frame (the "
                "pixels whose values were measured)" + ("" if scale is None else
                f", x {a_um2:.6g} um2 per pixel ({exp.um_per_px:g} um/px)") + ". "
                "Background: the pixels of the background region used at that timepoint, "
                "after leaving out very bright / fast-moving objects and the measured ROIs.")
        if bg_npx is None:
            note += (" The background pixel count was not recorded (tracked before V2.5 - "
                     "track again to get it).")
        ws.cell(row=T + 3, column=1, value=note).font = note_font
        ws.freeze_panes = "C2"
    tot = getattr(M, "sum", None)
    bg_tot = getattr(M, "background_sum", None)
    for c, (ch, tag) in enumerate(zip(M.channels, tags)):
        ws = wb.create_sheet(_sheet("Sum_", tag))
        header(ws, "Background sum")
        for t in range(T):
            ws.cell(row=t + 2, column=1, value=t + 1)
            if bg_tot is not None:
                ws.cell(row=t + 2, column=2, value=exact(bg_tot[t, c]))
            if tot is not None:
                for j, k in enumerate(idx):
                    ws.cell(row=t + 2, column=first_cell_col + j, value=exact(tot[t, c, k]))
        ws.cell(row=T + 3, column=1,
                value=(f"Sum of the raw {ch} values of every pixel of each ROI at each timepoint "
                       f"(counts). Raw_{tag} = this / Area_px (same cell, same timepoint; Raw is "
                       f"rounded to 3 decimals). Background sum / background pixels used = the "
                       f"Background column of Raw_{tag}.") if tot is not None else
                ("The sums were not recorded for this tracking (made before V2.5) - track "
                 "again to get them.")).font = note_font
        ws.freeze_panes = "C2"
    tick("Writing sums and areas")

    # ----------------------------------------------------------- Graphs
    if N and charts:
        from openpyxl.chart import LineChart, Reference

        gws = wb.create_sheet("Graphs", 1)          # right after Include
        gws.cell(row=1, column=1,
                 value="Black = included cells, blue = their mean. Set a cell to 0 on "
                       "the Include sheet and it disappears from every chart (Excel "
                       "recalculates on open).").font = note_font
        wanted = [q.strip() for q in str(getattr(s, "resp_quantity", "")).split(";")]
        order = sorted(range(len(charts)), key=lambda i: (charts[i][2] not in wanted, i))
        for i, (title, ylabel, _q) in enumerate(charts[i] for i in order):
            src = wb[title]
            ch = LineChart()
            ch.title = title
            ch.y_axis.title = ylabel
            ch.x_axis.title = ("Time from baseline (min)" if exp.seconds_per_frame > 0
                               else "Timepoints from baseline")
            ch.height, ch.width = 9, 22
            ch.legend = None
            ch.visible_cells_only = False          # the per-cell copies are hidden columns
            ch.display_blanks = "gap"
            data = Reference(src, min_col=plot_col0, max_col=plot_col0 + N - 1,
                             min_row=1, max_row=T + 1)
            ch.add_data(data, titles_from_data=True)
            ch.add_data(Reference(src, min_col=mean_col, max_col=mean_col,
                                  min_row=1, max_row=T + 1), titles_from_data=True)
            cats_col = time_col                    # 0 = baseline
            ch.set_categories(Reference(src, min_col=cats_col, max_col=cats_col,
                                        min_row=2, max_row=T + 1))
            for k, ser in enumerate(ch.series):
                ser.smooth = False
                ser.marker.symbol = "none"
                if k < N:
                    ser.graphicalProperties.line.solidFill = "404040"
                    ser.graphicalProperties.line.width = 9525        # 0.75 pt
                else:
                    ser.graphicalProperties.line.solidFill = "1F6FE0"
                    ser.graphicalProperties.line.width = 38100       # 3 pt
            gws.add_chart(ch, f"A{3 + i * 19}")

    # --------------------------------------------------------- ROI_info
    ws = wb.create_sheet("ROI_info")
    cols = ["Cell", "ROI type", "Source", "Seed area (um2)", "Mean area (um2)",
            "Centroid X (px)", "Centroid Y (px)",
            "Timepoints re-detected", "Timepoints shifted (not matched)",
            "Min tracking quality"] + [f"Saturated timepoints ({c})" for c in M.channels]         + (["QC score", "QC result"] if qc else [])
    for j, h in enumerate(cols, start=1):
        cc = ws.cell(row=1, column=j, value=h)
        cc.font = head_font
        cc.fill = head_fill
    for i, info in enumerate(roi_info):
        for j, h in enumerate(cols, start=1):
            cc = ws.cell(row=i + 2, column=j, value=info.get(h))
            if isinstance(cc.value, str):
                cc.data_type = "s"                 # text stays text, even if it begins with "="
    ws.freeze_panes = "B2"
    for j, h in enumerate(cols, start=1):
        ws.column_dimensions[get_column_letter(j)].width = max(12, min(30, len(h) + 2))
    tick("Writing ROI information")

    # --------------------------------------------------------- QC_report
    if qc:
        ws = wb.create_sheet("QC_report")
        qcols = ["Cell", "Exported", "QC passed", "QC score", "Reasons",
                 "Lost fraction", "Max area jump", "Signal/noise",
                 "Max saturated fraction", "One-frame artefacts", "Max response",
                 "Area vs median"]
        for j, h in enumerate(qcols, start=1):
            cc = ws.cell(row=1, column=j, value=h)
            cc.font = head_font
            cc.fill = head_fill
        exported = set(idx)
        shown = [c for c in qc if c.index in exported]       # only this workbook's cells
        for i, c in enumerate(shown):
            m = c.metrics
            vals = [f"Cell_{c.index + 1}", "yes" if c.index in exported else "no",
                    "yes" if c.passed else "no", round(c.score, 3),
                    "; ".join(c.reasons) or "",
                    m.get("lost_frac"), m.get("max_area_jump"), m.get("snr"),
                    m.get("saturated_frac"), m.get("spikes"), m.get("max_response"),
                    m.get("area_vs_median")]
            for j, v in enumerate(vals, start=1):
                if isinstance(v, float):
                    v = round(v, 3) if np.isfinite(v) else None
                cell = ws.cell(row=i + 2, column=j, value=v)
                if isinstance(v, str):
                    cell.data_type = "s"
        ws.cell(row=len(shown) + 3, column=1,
                value="QC: tracking, outline stability, signal/noise, saturation, image "
                      "edge, one-frame segmentation artefacts, specks, and (if switched on) "
                      "non-responders - cells whose smoothed F/F0 never left +/- the "
                      "cut-off of baseline. 'Max response' is that largest change; the "
                      "cut-off and baseline used are on the Settings sheet.").font = note_font
        ws.freeze_panes = "B2"
        ws.column_dimensions["E"].width = 70
        for col in "ABCDFGHIJ":
            ws.column_dimensions[col].width = 14

    # --------------------------------------------------------- Settings
    ws = wb.create_sheet("Settings")
    ws.column_dimensions["A"].width = 40
    ws.column_dimensions["B"].width = 34
    ws.column_dimensions["D"].width = 3
    ws.column_dimensions["E"].width = 12

    ws.cell(row=1, column=1, value=f"{APP_NAME} - analysis settings").font = Font(bold=True, size=13)
    ws.cell(row=2, column=1,
            value="Pick the baseline timepoint below; every dFF and dRR sheet "
                  "recalculates from it.").font = note_font

    BASE_ROW = 4
    ws.cell(row=BASE_ROW, column=1, value="Baseline timepoint (dropdown)").font = Font(bold=True)
    bcell = ws.cell(row=BASE_ROW, column=2,
                    value=int(np.clip(s.baseline_timepoint, 1, T)))
    bcell.font = Font(bold=True, color="0B5394")
    bcell.fill = PatternFill("solid", fgColor="FFF2CC")
    ws.cell(row=BASE_ROW + 1, column=1, value="   -> spreadsheet row it refers to")
    ws.cell(row=BASE_ROW + 1, column=2, value=f"=B{BASE_ROW}+1")
    ws.cell(row=BASE_ROW + 2, column=1, value="   -> time of that baseline (min)")
    ws.cell(row=BASE_ROW + 2, column=2, value=f"=(B{BASE_ROW}-1)*{exp.seconds_per_frame}/60")
    # V3.0 ratio check (MinSNR): change it here and every dFF / R / dRR sheet follows
    ws.cell(row=BASE_ROW, column=3,
            value="Ratio check (x noise of the ROI mean; 0 = off)").font = Font(bold=True)
    kcell = ws.cell(row=BASE_ROW, column=4, value=float(getattr(s, "ratio_min_snr", 5.0)))
    kcell.font = Font(bold=True, color="0B5394")
    kcell.fill = PatternFill("solid", fgColor="FFF2CC")

    # the list the dropdown offers, parked in a narrow helper column
    ws.cell(row=1, column=5, value="Timepoints").font = note_font
    for t in range(T):
        ws.cell(row=t + 2, column=5, value=t + 1)
    ws.column_dimensions["E"].hidden = True

    dv = DataValidation(type="list", formula1=f"=Settings!$E$2:$E${T + 1}",
                        allow_blank=False, showDropDown=False)
    dv.error = f"Choose a timepoint between 1 and {T}."
    dv.prompt = "Baseline timepoint used by every dFF and dRR sheet."
    ws.add_data_validation(dv)
    dv.add(bcell)

    # Everything below row BASE_ROW + 3 is a record of what was used; nothing
    # refers to it, so its rows may change between versions.
    from .provenance import (comp_key, comp_label, file_rows, methods_text,
                             parameter_table, software_versions)
    prov = dict(provenance or {})
    comp = comp_key(M.roi_mode or s.roi_mode)
    comps_all = list(prov.get("comps") or []) or [comp]
    prov["comps"] = comps_all
    track_params = prov.get("track_params") or None
    table = parameter_table(s, exp, track_params, None, prov)

    def text_cell(sheet, row: int, col: int, value):
        """A literal value: text stays text even if it begins with '='."""
        c = sheet.cell(row=row, column=col, value=value)
        if isinstance(value, str):
            c.data_type = "s"
        return c

    def section(sheet, row: int, title: str, ncols: int = 1) -> None:
        for col in range(1, ncols + 1):
            cc = sheet.cell(row=row, column=col)
            cc.font, cc.fill = head_font, head_fill
        text_cell(sheet, row, 1, title)

    ws.column_dimensions["A"].width = 52
    ws.column_dimensions["B"].width = 44
    r = BASE_ROW + 4
    ws.cell(row=BASE_ROW + 3, column=1,
            value="What each value means, the methods text and the software versions: "
                  "see the Methods sheet.").font = note_font
    last = None
    for sec, name, value, _meaning in table:
        if sec != last:
            if last is not None:
                r += 1
            section(ws, r, sec.upper())
            r += 1
            last = sec
        text_cell(ws, r, 1, name)
        vc = text_cell(ws, r, 2, value)
        vc.alignment = Alignment(wrap_text=True, vertical="top")
        r += 1
        if name == ".nd2 file":
            text_cell(ws, r, 1, "Folder")
            text_cell(ws, r, 2, str(Path(exp.nd2_path).parent)).alignment = \
                Alignment(wrap_text=True, vertical="top")
            r += 1
    r += 1
    section(ws, r, "THIS WORKBOOK")
    r += 1
    n_on = sum(1 for k in idx if include.get(k, 1))
    for name, value in (("Compartment", comp_label(comp).capitalize()),
                        ("Channels in this workbook", ", ".join(M.channels)),
                        ("Cells exported", N),
                        ("Cells included (Include sheet, when written)", n_on),
                        ("Ratio sheets", "yes" if s.write_ratio_sheets else "no"),
                        ("Written", _dt.datetime.now().strftime("%Y-%m-%d %H:%M")),
                        (f"{APP_NAME} version", __version__)):
        text_cell(ws, r, 1, name)
        text_cell(ws, r, 2, value).alignment = Alignment(wrap_text=True, vertical="top")
        r += 1
    r += 1
    section(ws, r, "NOTE")
    text_cell(ws, r, 2, "Raw_*, Sum_* and Area_* sheets hold measured numbers (Raw = Sum / "
                        "Area_px). All other sheets are live "
                        "Excel formulas, so open this file in Excel or LibreOffice; a "
                        "plain CSV reader will see the formulas, not the values."
              ).alignment = Alignment(wrap_text=True, vertical="top")

    # ---------------------------------------------------------- Methods
    versions = software_versions()
    ms = wb.create_sheet("Methods")
    widths = {"A": 30, "B": 50, "C": 34, "D": 90}
    for col, w in widths.items():
        ms.column_dimensions[col].width = w
    per_line = sum(widths.values())                 # characters per merged line, roughly

    def paragraph(row: int, text: str, font=None) -> None:
        """One paragraph across A:D, wrapped, tall enough to show it all."""
        c = text_cell(ms, row, 1, text)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        if font is not None:
            c.font = font
        ms.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
        lines = sum(max(1, -(-len(part) // per_line)) for part in text.split("\n"))
        ms.row_dimensions[row].height = min(409, 15 * lines + 3)

    text_cell(ms, 1, 1, f"{APP_NAME} - methods: what was done, with which numbers and "
                        f"software").font = Font(bold=True, size=13)
    text_cell(ms, 2, 1, "Copy the text below into your methods section and edit it (words in "
                        "[square brackets] are for you to check or fill in). Every number in "
                        "it is the value used for this workbook; the tables below list them "
                        "all.").font = note_font
    full = methods_text(s, exp, track_params, None, comps_all, versions, prov)
    body, _sep, refs = full.partition("\n\nReferences\n")
    r = 4
    section(ms, r, "METHODS TEXT", 4)
    r += 1
    for para in body.split("\n\n"):
        paragraph(r, para)
        r += 1
    r += 1
    section(ms, r, "REFERENCES", 4)
    r += 1
    for line in refs.splitlines():
        paragraph(r, line)
        r += 1
    r += 1
    section(ms, r, "PARAMETERS", 4)
    r += 1
    for col, h in enumerate(("Section", "Parameter", "Value", "What it means"), start=1):
        text_cell(ms, r, col, h).font = Font(bold=True)
    r += 1
    for sec, name, value, meaning in table:
        for col, v in enumerate((sec, name, value, meaning), start=1):
            text_cell(ms, r, col, v).alignment = Alignment(wrap_text=True, vertical="top")
        r += 1
    r += 1
    section(ms, r, "SOFTWARE", 4)
    r += 1
    for name, v in versions.items():
        text_cell(ms, r, 2, name)
        text_cell(ms, r, 3, v)
        r += 1
    r += 1
    section(ms, r, "DATA FILE AND ANALYSIS", 4)
    r += 1
    nd2_path = str(prov.get("nd2_path") or exp.nd2_path or "")
    rows_f = file_rows(nd2_path, prov.get("fingerprint"))
    if prov.get("session_id"):
        rows_f.append(("Session", str(prov["session_id"])))
    rows_f.append(("Analysis date (this workbook written)",
                   _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    rows_f.append(("Written by", f"{APP_NAME} {__version__}"))
    for name, v in rows_f:
        text_cell(ms, r, 2, name)
        text_cell(ms, r, 3, v).alignment = Alignment(wrap_text=True, vertical="top")
        r += 1
    ms.sheet_view.zoomScale = 90
    tick("Writing methods")

    # named cells used by every derived sheet
    _add_name(wb, "BaselineTP", f"Settings!$B${BASE_ROW}")
    _add_name(wb, "BaselineRow", f"Settings!$B${BASE_ROW + 1}")
    _add_name(wb, "MinSNR", f"Settings!$D${BASE_ROW}")

    wb.calculation.fullCalcOnLoad = True
    out = Path(path)
    with new_output_file(out) as (out, stream):
        wb.save(stream)
    if progress:
        progress(1.0, f"Saved {out.name}")
    return str(out)


def _add_name(wb, name: str, ref: str) -> None:
    """Define a workbook-level name (the openpyxl API changed in 3.1)."""
    from openpyxl.workbook.defined_name import DefinedName

    dn = DefinedName(name, attr_text=ref)
    try:
        wb.defined_names[name] = dn
    except TypeError:
        try:
            wb.defined_names.add(dn)
        except AttributeError:
            wb.defined_names.append(dn)


# --------------------------------------------------------------------------
#  ROI_info rows
# --------------------------------------------------------------------------
def build_roi_info(exp: Experiment, s: Settings, M: Measurements,
                   cells: Sequence[int], seed_rois, seed_t: int,
                   qc=None) -> List[Dict]:
    """One dictionary per exported cell, matching the ROI_info column headers."""
    a_um2 = exp.um_per_px ** 2
    out: List[Dict] = []
    for k in cells:
        q = M.quality[:, k]
        areas = M.area_px[:, k].astype(float)
        row = {
            "Cell": f"Cell_{k + 1}",
            "ROI type": M.roi_mode,
            "Source": getattr(seed_rois[k], "source", "auto") if k < len(seed_rois) else "auto",
            "Seed area (um2)": round(float(M.area_px[seed_t, k]) * a_um2, 1),
            "Mean area (um2)": round(float(np.nanmean(areas)) * a_um2, 1),
            "Timepoints re-detected": int(np.sum(q >= 0.9)),
            "Timepoints shifted (not matched)": int(np.sum(q < 0.4)),
            "Min tracking quality": round(float(np.min(q)), 2),
        }
        if k < len(seed_rois):
            cy, cx = seed_rois[k].centroid
            row["Centroid X (px)"] = round(cx, 1)
            row["Centroid Y (px)"] = round(cy, 1)
        for c, ch in enumerate(M.channels):
            row[f"Saturated timepoints ({ch})"] = int(np.sum(M.n_saturated[:, c, k] > 0))
        if qc and k < len(qc):
            row["QC score"] = round(qc[k].score, 3)
            row["QC result"] = qc[k].summary
        out.append(row)
    return out
