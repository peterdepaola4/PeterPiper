"""
PeterPiper 1.2: how long the file paths of an export will be, and shorter names
that make every path fit. Pure functions - nothing here reads or writes a file.

Why: with Windows' long paths off (the Windows default) Explorer and many
programs have trouble with a path over 259 characters, and Excel never opens a
workbook whose full path is over 218 characters (whatever the setting). An
export goes deep:

    <results folder>/Export_<date>_<time>/<Compartment>/Prism graphs/<name>_<quantity>.prism

'Shorten names for me' (the long-path warning; batch runs do it by themselves)
shortens the part you can choose - the 'Name for the files' - by cutting its
MIDDLE (the start and the end stay, and the end usually tells files apart:
_dish3, _10uM), and only if that is not enough the export folder's name
(Export_2026-11-16_14-30-05 -> Export_261116-1430). The parts that tell the files
of one export apart (compartment, quantity, timepoint) are never touched, so the
names stay unique. Aim: every path <= 218 characters; if that cannot be reached,
<= 259.
"""
from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

EXCEL_MAX = 218          # Excel: the longest full path of a workbook it opens
WINDOWS_MAX = 259        # Explorer & co. with long paths off (MAX_PATH 260 incl. the end)
EXCEL_ENDINGS = (".xlsx", ".csv")      # opened in Excel
MIN_NAME = 8             # 'Name for the files' is never cut shorter than this
READABLE_NAME = 16       # ... and not below this before the export folder gets its short name
CUT = "..."              # marks where the middle of a name was cut


def export_folder_name(when: Optional[dt.datetime] = None, short: bool = False) -> str:
    """'Export_2026-11-16_14-30-05' (as always), or short: 'Export_261116-1430'."""
    when = when or dt.datetime.now()
    return f"Export_{when:%y%m%d-%H%M}" if short else f"Export_{when:%Y-%m-%d_%H-%M-%S}"


def is_short_folder(name: str) -> bool:
    """True for the short export folder name ('Export_261116-1430')."""
    return str(name).startswith("Export_") and "_" not in str(name)[7:]


def file_tag(stem: str, movie: str) -> str:
    """The name put on the files INSIDE the compartment folders (graphs, CSV,
    Prism graphs, ROI pictures): none when it is just the movie's name (the
    folder OUTPUT_<movie> says it already), else the name you typed."""
    from .export import clean_prefix
    return "" if stem in (movie[:40], clean_prefix(movie), clean_prefix(movie)[:40]) else stem


def cut_middle(name: str, n: int) -> str:
    """`name` in at most n characters: the middle replaced by '...', the start
    and the END kept (more of the end - it usually tells files apart).
    'experiment_long_name_dish3', 14 -> 'exper..._dish3'."""
    name = str(name or "")
    if len(name) <= n:
        return name
    if n <= len(CUT) + 2:
        return name[-n:] if n > 0 else ""
    keep = n - len(CUT)
    tail = (keep + 1) // 2
    head = keep - tail
    a = name[:head].rstrip(" ")
    b = name[len(name) - tail:].lstrip(" ")
    return f"{a}{CUT}{b}"


def _safe(name: str) -> str:
    from .export import _safe as safe
    return safe(name)


def _nice(sheet: str) -> str:
    from .export import nice
    return nice(sheet)


def relative_paths(keys: Sequence[str], comps: Dict[str, dict], stem: str, tag: str,
                   movie: str = "", channels: Sequence[str] = (), n_timepoints: int = 1,
                   t0: int = 0, drift: Optional[Tuple[int, int]] = None,
                   pzfx_graphs: bool = False) -> List[str]:
    """
    The files an export of `keys` writes, relative to its Export_ folder ('/'
    between folders), named exactly as export.run_export names them.
    comps[c] = dict(label, name, sheets [every quantity's sheet name],
                    prism [the sheets that get a .prism graph]).
    stem = the name for the files (workbooks, .pzfx, ROI file, methods text);
    tag = the name on the inner files ('' = none). drift = (from, to) when the
    drift slopes are written; pzfx_graphs = a .pzfx template is used (each .pzfx
    also comes as ..._with_graphs.pzfx). Raw TIFFs / viewing copies: one file per
    channel stands for all (the last timepoint has the longest name).
    """
    keys = list(keys)
    out: List[str] = []
    pre = f"{tag}_" if tag else ""
    for c, d in comps.items():
        mine = [k.split("|", 1)[1] for k in keys if k.split("|", 1)[0] == c]
        if not mine:
            continue
        cdir = _safe(d["label"])
        name = d["name"]
        base = f"{stem}_{name}"
        if "excel" in mine:
            out.append(f"{cdir}/{base}.xlsx")
        if "prism" in mine or ("drift" in mine and drift):
            pz = f"{base}.pzfx" if "prism" in mine else f"{base}_baseline_drift.pzfx"
            out.append(f"{cdir}/{pz}")
            if pzfx_graphs:
                out.append(f"{cdir}/{pz[:-5]}_with_graphs.pzfx")
        if "prismgraph" in mine:
            for q in d.get("prism") or []:
                nm = _nice(q).replace("/", "-").replace(" ", "_")
                out.append(f"{cdir}/Prism graphs/{pre}{name}_{nm}.prism")
        if "drift" in mine and drift:
            out.append(f"{cdir}/{base}_baseline_drift_T{drift[0]}-T{drift[1]}.xlsx")
        if "csv" in mine:
            for q in d.get("sheets") or []:
                out.append(f"{cdir}/CSV/{pre}{_safe(_nice(q).replace('/', '-'))}.csv")
        for k in mine:
            if k.startswith("graph|") and k.split("|", 1)[1] in (d.get("sheets") or []):
                q = k.split("|", 1)[1]
                out.append(f"{cdir}/Graphs/{pre}{_safe(_nice(q).replace('/', '-'))}.png")
        frames = []
        T = max(1, int(n_timepoints))
        if "roi_drawn" in mine:
            frames.append((t0, "drawn"))
        if "roi_last" in mine and T - 1 != t0:
            frames.append((T - 1, "last"))
        if "roi_every" in mine:
            frames += [(t, "check") for t in range(0, T, 10) if (t, "drawn") not in frames]
        for t, kind in frames:
            out.append(f"{cdir}/ROI pictures/"
                       + "_".join(p for p in (tag, name) if p) + f"_ROIs_t{t + 1}_{kind}.png")
    if "*|roifile" in keys:
        out.append(f"{stem}_ROIs.npz")
    if "*|methods" in keys:
        out.append(f"{stem}_methods.txt")
    T = max(1, int(n_timepoints))
    if "*|tiffs" in keys:
        out += [f"Raw TIFFs/{movie}_{ch}_t{T:03d}.tif" for ch in channels]
    if "*|views" in keys:
        out += [f"Viewing copies (PNG)/{movie}_{ch}_t{T:03d}_VIEW-ONLY.png" for ch in channels]
    return out


def full_paths(out_root, folder_name: str, rel: Sequence[str]) -> List[str]:
    """The full paths (this computer's separators) of `rel` inside
    <out_root>/<folder_name>."""
    sep = os.sep
    root = os.path.normpath(str(out_root)).rstrip("\\/")
    return [sep.join((root, folder_name, r.replace("/", sep))) for r in rel]


def too_long(paths: Sequence[str], excel: int = EXCEL_MAX,
             limit: int = WINDOWS_MAX) -> List[str]:
    """The paths Explorer (over `limit`) or Excel (a workbook / CSV over `excel`)
    may not open."""
    return [p for p in paths
            if len(p) > limit or (p.lower().endswith(EXCEL_ENDINGS) and len(p) > excel)]


def longest(paths: Sequence[str]) -> Tuple[int, str]:
    """(length, path) of the longest path ((0, '') for none)."""
    if not paths:
        return 0, ""
    p = max(paths, key=len)
    return len(p), p


@dataclass
class Fit:
    """Names for an export (shorter ones if needed) and what they give."""
    stem: str              # the name for the files
    tag: str               # the name on the inner files ('' = none)
    folder_name: str       # the Export_ folder's name
    longest: int           # the longest full path with these names
    longest_path: str
    limit: int             # the limit reached (218 or 259), 0 if none
    ok: bool               # every path within `limit`
    changed: bool          # any name differs from what was asked
    before: int            # the longest path with the names asked for
    excel_ok: bool = True  # every workbook / CSV within Excel's 218


def shorter_names(out_root, rel_fn: Callable[[str, str], List[str]], stem: str, tag: str,
                  when: Optional[dt.datetime] = None, min_name: int = MIN_NAME) -> Fit:
    """
    The longest names (stem / tag cut in the middle down to READABLE_NAME, then
    the short folder name with the name down to MIN_NAME) whose paths all fit: first every path <= 218; else every workbook / CSV
    <= 218 (Excel) and every other path <= 259; else every path <= 259.
    rel_fn(stem, tag) -> the export's relative paths (relative_paths). If even
    the shortest names do not fit, the shortest are returned with ok=False.
    """
    when = when or dt.datetime.now()
    folders = (export_folder_name(when), export_folder_name(when, short=True))
    before, _p = longest(full_paths(out_root, folders[0], rel_fn(stem, tag)))
    floor = min(len(stem), min_name)

    def names(n: int) -> Tuple[str, str]:
        return cut_middle(stem, n), (cut_middle(tag, n) if tag else "")

    # every path <= 218; else Excel's files <= 218 and the rest <= 259; else all <= 259
    # the name first (down to a still readable length), then the short folder name
    # with the name down to its minimum
    steps = ((folders[0], min(len(stem), max(floor, READABLE_NAME))), (folders[1], floor))
    for excel, limit in ((EXCEL_MAX, EXCEL_MAX), (EXCEL_MAX, WINDOWS_MAX),
                         (WINDOWS_MAX, WINDOWS_MAX)):
        for fn, low in steps:
            for n in range(len(stem), low - 1, -1):
                st, tg = names(n)
                paths = full_paths(out_root, fn, rel_fn(st, tg))
                if not too_long(paths, excel, limit):
                    n_long, p = longest(paths)
                    return Fit(st, tg, fn, n_long, p, limit, True,
                               (st, tg, fn) != (stem, tag, folders[0]), before,
                               excel <= EXCEL_MAX)
    st, tg = names(floor)
    paths = full_paths(out_root, folders[1], rel_fn(st, tg))
    n_long, p = longest(paths)
    return Fit(st, tg, folders[1], n_long, p, 0, False, True, before,
               not too_long(paths, EXCEL_MAX, 10 ** 6))


def tail(path: str, n: int = 90) -> str:
    """The end of a long path for a message: '...\\Prism graphs\\name.prism'."""
    path = str(path)
    return path if len(path) <= n else "..." + path[-(n - 3):]
