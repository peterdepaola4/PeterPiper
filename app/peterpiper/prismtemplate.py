"""
V2.7: your Prism style templates - edit the look once in GraphPad Prism, every
.prism PeterPiper writes from then on uses it, and it is remembered.

They live in a folder next to PeterPiper's settings ("Prism style templates" in
your profile folder under %USERPROFILE%\\PeterPiper data), as two .prism files PeterPiper makes for you:

  PeterPiper graph style.prism         an example time course (graph 1). Change
                                   anything on graph 1 in Prism (fonts, sizes,
                                   colours, symbols, line widths, axes, frame,
                                   legend) and save it under the same name.
                                   Every XY graph PeterPiper writes is a copy of it
                                   (its data and texts replaced) - the main
                                   graph and the graph of every other table.
  PeterPiper column graph style.prism  an example kinetics table WITHOUT a graph.
                                   In Prism: select the table 'Example groups',
                                   New graph > Column > scatter dot plot (or
                                   bars), mean +/- SEM, style it, save. Every
                                   column table PeterPiper writes (kinetics, drift
                                   per cell) then gets a graph made from it.
                                   Until then column tables have no graph.

A file left unchanged is still used (it is PeterPiper's own look). 'Reset' moves
your file aside (never deletes it) and writes a fresh one. To make your look
the built-in default of a later PeterPiper version, send the developer these two
files: dev_tests/make_prism_template.py builds the bundled template from them.

Only the graph's LOOK is taken from these files; the data, titles, axis titles,
legend text and n always come from your runs.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Optional, Tuple

import numpy as np

from . import prismstyle
from .safety import long_path

XY_NAME = "PeterPiper graph style.prism"
COLUMN_NAME = "PeterPiper column graph style.prism"
COLUMN_TABLE = "Example groups"


def folder() -> Path:
    from .config import _settings_file
    d = _settings_file().parent / "Prism style templates"
    d.mkdir(parents=True, exist_ok=True)
    return d


def xy_path() -> Path:
    return folder() / XY_NAME


def column_path() -> Path:
    return folder() / COLUMN_NAME


def _example_xy(path: Path) -> None:
    from .prismfile import write_compare_prism
    rng = np.random.default_rng(7)
    x = np.arange(-2, 11, dtype=float)
    lines = []
    for k, (lab, rise) in enumerate((("Example A", 0.5), ("Example B", 0.25))):
        y = 1 + rise * np.clip(x, 0, None)[:, None] / 10 + rng.normal(0, 0.03, (len(x), 6))
        lines.append((f"{lab} (n = 6)", x, y))
    write_compare_prism(str(path), lines, "Time from baseline (min)", "R/R0", "R/R0",
                        "Example - edit graph 1 and save", ["#0072B2", "#D55E00"],
                        notes="PeterPiper graph style template. Change the look of graph 1 in "
                              "Prism and save under the same name; PeterPiper copies its look.",
                        table_graphs=False)


def _example_column(path: Path) -> None:
    from .prismfile import write_compare_prism
    rng = np.random.default_rng(8)
    x = np.arange(0, 5, dtype=float)
    cols = [(g, list(rng.normal(m, 0.8, 4)), [f"dish {k + 1}" for k in range(4)])
            for g, m in (("Group 1", 6.0), ("Group 2", 9.0), ("Group 3", 7.5))]
    write_compare_prism(str(path), [("ignore", x, np.ones((5, 1)))], "X", "t½ max (min)",
                        "t½ max (min)", "ignore", ["#000000"],
                        notes="PeterPiper column graph style template. Select the table "
                              f"'{COLUMN_TABLE}', make a New graph (Column: scatter dot plot "
                              "with mean +/- SEM, or bars), style it and save under the same "
                              "name.",
                        table_graphs=False,
                        columns_extra=[(COLUMN_TABLE, "t½ max (min)", cols)])


def ensure() -> Tuple[Path, Path]:
    """Make the two template files if they are missing (never overwrites)."""
    xp, cp = xy_path(), column_path()
    if not xp.exists():
        _example_xy(xp)
    if not cp.exists():
        _example_column(cp)
    return xp, cp


def reset(which: str = "xy") -> Path:
    """Move your file aside ('... (old 1).prism', never deleted) and write a
    fresh one."""
    p = xy_path() if which == "xy" else column_path()
    if p.exists():
        k = 1
        while (p.parent / f"{p.stem} (old {k}).prism").exists():
            k += 1
        p.rename(p.parent / f"{p.stem} (old {k}).prism")
    (_example_xy if which == "xy" else _example_column)(p)
    return p


def active_xy() -> Optional[str]:
    """Your XY template when it exists and was made from PeterPiper's (its look is
    applied), else None (the built-in one)."""
    try:
        p = xy_path()
    except OSError:
        return None
    from .prismfile import template_takes_style
    return str(p) if p.exists() and template_takes_style(str(p)) else None


def column_template() -> Optional[dict]:
    """The column graph you made in your column template: {'gb': graph block
    with only its first plot, 'gs': its sheet.json, 'fen': the data set fen the
    plot draws}; None when there is none (yet)."""
    try:
        p = column_path()
        if not p.exists():
            return None
        with zipfile.ZipFile(long_path(p)) as z:
            doc = json.loads(z.read("document.json"))
            sheet_fen = {}
            for su in doc["sheets"].get("data", []):
                sh = json.loads(z.read(f"data/sheets/{su}/sheet.json"))
                if sh.get("table", {}).get("format") == "column":
                    sheet_fen[int(sh.get("fenID", -1))] = sh
            for gid in doc["sheets"].get("graphs", []):
                gb = z.read(f"graphs/{gid}/data.bin")
                fen = _graph_table_fen(gb)
                if fen in sheet_fen:
                    pls = prismstyle.plots(gb)
                    if not pls:
                        continue
                    first = pls[-1]["fen"] if len(pls) == 1 else _first_plot_fen(gb, z, sheet_fen[fen])
                    drop = [q["fen"] for q in pls if q["fen"] != first]
                    if drop:
                        gb = prismstyle.remove_plots(gb, drop)
                    gb = _normalise_plots(gb)
                    gs = json.loads(z.read(f"graphs/{gid}/sheet.json"))
                    return {"gb": gb, "gs": gs, "fen": first}
    except (OSError, KeyError, ValueError, zipfile.BadZipFile):
        return None
    return None


def _graph_table_fen(gb: bytes) -> int:
    """The fenID of the data table a graph belongs to (record 0x0014 @4)."""
    import struct
    for off, tag, n in prismstyle.records(gb):
        if tag == 0x0014 and n >= 8:
            return int(struct.unpack_from("<I", gb, off + 6 + 4)[0])
    return -1


def _first_plot_fen(gb: bytes, z, sheet: dict) -> int:
    """The plot of the table's first data set (else the graph's first plot)."""
    sets = sheet.get("table", {}).get("dataSets") or []
    fens = [p["fen"] for p in prismstyle.plots(gb)]
    for u in sets:
        try:
            f = int(json.loads(z.read(f"data/sets/{u}.json"))["fenID"])
        except (KeyError, ValueError):
            continue
        if f in fens:
            return f
    return fens[-1]


def _normalise_plots(gb: bytes) -> bytes:
    """Plot ids 1000, 1001 ... and a plot list (0x0015) of exactly those. Prism's
    column graphs number their plots 65536, 65537 ... and list only the low 16
    bits (0, 1 ...); PeterPiper's XY template lists the full ids - this makes a
    column template work like the XY one."""
    import struct
    b = bytearray(gb)
    R = prismstyle.records(gb)
    pls = prismstyle.plots(gb, R)
    new = []
    for k, p in enumerate(pls):
        nid = 1000 + k
        new.append(nid)
        struct.pack_into("<I", b, R[p["idb"]][0] + 6 + 158, nid)
        struct.pack_into("<I", b, R[p["i8028"]][0] + 6, nid)
    for off, tag, n in R:
        if tag == prismstyle.TAG_PLOTLIST:
            body = struct.pack(f"<I{len(new)}I", len(new), *new)
            return bytes(b[:off]) + struct.pack("<HI", tag, len(body)) + body + bytes(b[off + 6 + n:])
    return bytes(b)
