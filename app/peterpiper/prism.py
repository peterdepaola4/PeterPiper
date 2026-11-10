"""
GraphPad Prism file (.pzfx) of the included cells - the same numbers as the graphs.

Per quantity (your key one first, e.g. R/R0 GFP/Cy5), three XY tables with
X = time from the baseline (0 = baseline, earlier timepoints negative):

    <quantity> - cells as replicates   ONE data set, each included cell is a
                                       replicate: Prism graphs it as mean +/- SEM
                                       (or every cell) and computes n itself
    <quantity> - mean, SEM, n          the same mean / SEM / n as numbers
    <quantity> - each cell             one named data set per cell (Cell_3, ...)

The project notes (Info) say what made the file: PeterPiper version and date, and
- when the export passes them - the tracking rules and the baseline timepoint.

Graphs: Prism keeps graphs in a private binary block that only Prism can make.
If you give a Prism TEMPLATE (any of these files, opened in Prism, with the
graphs you like made and saved as .pzfx), every export also writes
'..._with_graphs.pzfx': your template's graphs, filled with this experiment's
tables (matched by table title, in the template's order).
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import List, Optional, Sequence, Tuple
from xml.sax.saxutils import escape, unescape

import numpy as np

from . import __version__
from .safety import long_path, new_output_file


def _num(v: float) -> str:
    return "<d/>" if not np.isfinite(v) else f"<d>{float(v):.6g}</d>"


def _column(tag: str, title: str, cols: Sequence[np.ndarray], decimals: int) -> str:
    subs = "".join("<Subcolumn>" + "".join(_num(v) for v in c) + "</Subcolumn>" for c in cols)
    return (f'<{tag} Width="90" Decimals="{decimals}" Subcolumns="{len(cols)}">'
            f"<Title>{escape(title)}</Title>{subs}</{tag}>")


def _table(tid: str, title: str, x: np.ndarray, xlabel: str, ycols: List[str],
           yformat: str, replicates: int) -> str:
    rep = f' Replicates="{replicates}"' if yformat == "replicates" else ""
    return (f'<Table ID="{tid}" XFormat="numbers" YFormat="{yformat}"{rep} '
            f'TableType="XY" EVFormat="AsteriskAfterNumber">'
            f"<Title>{escape(title)}</Title>"
            + _column("XColumn", xlabel, [x], 2) + "".join(ycols) + "</Table>")


def _tables(x, xlabel, panels) -> List[Tuple[str, str, str]]:
    """[(title, yformat, xml with ID placeholder '@ID@')]"""
    out = []
    for name, ylabel, y, names in panels:
        y = np.asarray(y, float)
        T = len(x)
        with np.errstate(invalid="ignore", divide="ignore"):
            n = np.sum(np.isfinite(y), axis=1).astype(float)
            mean = np.nanmean(y, axis=1) if y.shape[1] else np.full(T, np.nan)
            sd = np.nanstd(y, axis=1, ddof=1) if y.shape[1] > 1 else np.full(T, np.nan)
            sem = sd / np.sqrt(np.maximum(n, 1))
        mean[n == 0] = np.nan
        reps = [y[:, j] for j in range(y.shape[1])] or [np.full(T, np.nan)]
        out.append((f"{name} - cells as replicates", "replicates",
                    _table("@ID@", f"{name} - cells as replicates", x, xlabel,
                           [_column("YColumn", ylabel, reps, 4)], "replicates", len(reps))))
        out.append((f"{name} - mean, SEM, n", "SEN",
                    _table("@ID@", f"{name} - mean, SEM, n", x, xlabel,
                           [_column("YColumn", ylabel, [mean, sem, n], 4)], "SEN", 1)))
        out.append((f"{name} - each cell", "replicates",
                    _table("@ID@", f"{name} - each cell", x, xlabel,
                           [_column("YColumn", nm, [y[:, j]], 4) for j, nm in enumerate(names)],
                           "replicates", 1)))
    return out


def column_tables(groups) -> List[Tuple[str, str, str]]:
    """
    Column tables (one value per cell, cell names as row titles) - Prism graphs
    them as a scatter dot plot with mean +/- SEM. groups: (title, y title,
    values, row titles). Same form as _tables().
    """
    out = []
    for title, ytitle, vals, rows in groups:
        rt = ("<RowTitlesColumn Width=\"90\"><Subcolumn>" +
              "".join(f"<d>{escape(r)}</d>" for r in rows) + "</Subcolumn></RowTitlesColumn>")
        xml = (f'<Table ID="@ID@" XFormat="none" TableType="OneWay" EVFormat="AsteriskAfterNumber">'
               f"<Title>{escape(title)}</Title>" + rt +
               _column("YColumn", ytitle, [np.asarray(vals, float)], 6) + "</Table>")
        out.append((title, "column", xml))
    return out


def _document(tables: List[Tuple[str, str]], notes: str, template_block: str = "") -> str:
    """tables: [(ID, xml)] in navigator order."""
    sel = ' Selected="1"'
    refs = "".join(f'<Ref ID="{tid}"{sel if i == 0 else ""}/>' for i, (tid, _x) in enumerate(tables))
    stamp = dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<GraphPadPrismFile xmlns="http://graphpad.com/prism/Prism.htm" PrismXMLVersion="5.00">'
            f'<Created><OriginalVersion CreatedByProgram="PeterPiper" CreatedByVersion="{__version__}" '
            f'Login="" DateTime="{stamp}"/></Created>'
            '<InfoSequence><Ref ID="Info0" Selected="1"/></InfoSequence>'
            f'<Info ID="Info0"><Title>Project info 1</Title><Notes>{escape(notes)}</Notes></Info>'
            f"<TableSequence>{refs}</TableSequence>" + "".join(x for _t, x in tables) +
            template_block + "</GraphPadPrismFile>\n")


def _write(path: Path, xml: str) -> str:
    with new_output_file(Path(path)) as (used, stream):
        stream.write(xml.encode("utf-8"))
    return str(used)


def read_template(path: str):
    """(table IDs in order, {ID: (title, yformat)}, graph block) of a Prism-saved .pzfx."""
    with open(long_path(path), "rb") as f:
        t = f.read().decode("utf-8", errors="replace")
    block = re.search(r"(<!--[^>]*?compressed binary.*?-->\s*)?<Template\b.*?</Template>", t, re.S)
    if block is None:
        raise ValueError("That file has no graphs (it was not saved by Prism with graphs).")
    seq = re.search(r"<TableSequence[^>]*>(.*?)</TableSequence>", t, re.S)
    ids = re.findall(r'<Ref\s+ID="([^"]+)"', seq.group(1)) if seq else []
    info = {}
    for m in re.finditer(r'<Table\s+ID="([^"]+)"([^>]*)>(.*?)</Table>', t, re.S):
        title = re.search(r"<Title>(.*?)</Title>", m.group(3), re.S)
        fmt = re.search(r'YFormat="([^"]+)"', m.group(2))
        info[m.group(1)] = (unescape(title.group(1).strip()) if title else "",
                            fmt.group(1) if fmt else "")
    return [i for i in ids if i in info], info, block.group(0)


def write_pzfx(path: str, x: np.ndarray, xlabel: str,
               panels: Sequence[Tuple[str, str, np.ndarray, Sequence[str]]],
               notes: str = "", template: Optional[str] = None, columns=(),
               provenance: Optional[dict] = None) -> List[str]:
    """
    panels: (quantity name, y label, T x n data of the included cells, cell names).
    columns: extra one-value-per-cell tables (e.g. baseline drift slopes), see
    column_tables(). Writes the plain file, and with a template also
    '<name>_with_graphs.pzfx'. Returns the paths written (never overwrites).
    The project notes (Info sheet) end with a provenance line: PeterPiper version
    and date, plus - from `provenance` (optional: rules, baseline, fingerprint) -
    the tracking rules, the baseline timepoint and the .nd2 fingerprint.
    """
    from .provenance import provenance_note
    notes = " ".join(t for t in (str(notes or "").strip(), provenance_note(provenance)) if t)
    ours = _tables(x, xlabel, panels) + column_tables(columns)
    plain = [(f"Table{i}", xml.replace("@ID@", f"Table{i}")) for i, (_t, _f, xml) in enumerate(ours)]
    paths = [_write(Path(path), _document(plain, notes))]
    if template:
        ids, info, block = read_template(template)
        free = list(range(len(ours)))
        placed = []
        for tid in ids:                         # the template's tables, in its order
            title, fmt = info[tid]
            j = next((j for j in free if ours[j][0] == title), None)
            if j is None:                       # same position among tables of that format
                j = next((j for j in free if ours[j][1] == fmt), None)
            if j is None:
                continue
            free.remove(j)
            placed.append((tid, ours[j][2].replace("@ID@", tid)))
        for n, j in enumerate(free):
            tid = f"PD4Table{n}"
            placed.append((tid, ours[j][2].replace("@ID@", tid)))
        p = Path(path)
        paths.append(_write(p.with_name(p.stem + "_with_graphs.pzfx"),
                            _document(placed, notes, block)))
    return paths
