"""
GraphPad Prism 10+ project files (.prism) WITH THE GRAPH ALREADY MADE.

A .prism file is a zip of open JSON / CSV (the data tables) plus one binary
block per graph (its look). PeterPiper ships a graph TEMPLATE made in Prism
(templates/PeterPiper_timecourse.prism). V2.5: the template is a graph the lab
styled in GraphPad Prism 11 (plain 18 pt title and axis titles, large tick
labels, a dotted line at X = 0, 0.59 pt lines with 4.32 pt symbols, capped
error bars, open frame): dev_tests/make_prism_template.py copied its graph block
with only its first plot and nothing of its data; templates/PeterPiper_look.json
keeps the symbol of each further data set (circle, square, triangle, triangle
down ...) for compare / average graphs (series_symbols). Every .prism PeterPiper
writes - single runs, compare, replicate averages - starts from it; the graph
title, axis titles, data, legend and n always come from the actual runs, and
the template's own look stays wherever the style is GraphStyle's default (the
template's look; prismstyle.apply_style leaves those bytes as they are). For
every quantity it writes a copy of that template with

  * the graph's own data table replaced by this experiment's included cells
    (each cell one replicate, X = time from the baseline) - Prism draws the
    mean +/- SEM from it, so the graph IS the data;
  * the graph title (file + compartment + n) and the axis titles set;
  * extra tables: '<quantity> - mean, SEM, n' (the numbers), '<quantity> - each
    cell' (Cell_3, Cell_7 ... as named columns) and, if chosen, the baseline drift
    slope per cell (a column table, one row per cell);
  * the chosen graph style (prismstyle.py: error SEM / SD / 95% CI / none,
    colours, line widths, symbols, axis ranges, font size and, if chosen, each
    cell as a thin line drawn from the 'each cell' table) - only what was
    checked in GraphPad Prism 11 (prismstyle.SUPPORT).

The template graph had a fixed -5..55 min X axis and showed SD; PeterPiper writes
the error the style asks for (default SEM, written into the data set titles)
with automatic axes unless ranges are set.

Only Prism 10 or newer opens .prism files; the .pzfx (all tables) stays for
older Prism.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import struct
import uuid
import zipfile
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import numpy as np

from . import prismstyle
from .safety import long_path, new_output_file

TEMPLATE = Path(__file__).resolve().parent / "templates" / "PeterPiper_timecourse.prism"


def _uid() -> str:
    return str(uuid.uuid4()).upper()


def _num(v) -> str:
    return "" if v is None or not np.isfinite(v) else f"{float(v):.7g}"


def _rep(T: int, decimals: int = 4, attrs=("NUMERIC",), value="real") -> dict:
    return {"@class": "DriverReplicate", "valueType": value, "commonAttributes": list(attrs),
            "decimalsLength": decimals, "significantDigitsCount": 7,
            "lastRow": T - 1, "firstRow": 0}


def _dataset(uid: str, fen: int, fmt: str, title: Optional[str], attr: str, reps) -> dict:
    d = {"@class": "DataSet", "$id": "sheets/data_sheet/data_table/data_set.schema.json",
         "uid": uid, "fenID": fen, "format": fmt}
    if title is not None:
        d["title"] = title
    d["attributes"] = [attr]
    d.update(reps)
    return d


def _sheet(uid: str, fen: int, title: str, table: dict) -> dict:
    return {"@class": "DataSheet", "$id": "sheets/data_sheet/data_sheet.schema.json",
            "uid": uid, "fenID": fen, "title": title, "isCustomTitle": True, "table": table,
            "font": {"family": "Arial", "size": 10.0}, "titleWidth": 160, "xSubColWidth": 120,
            "maxDataSets": 2048, "maxRow": 500000,
            "selectionRange": {"startCell": {"row": 0, "column": -1, "subcolumn": 0},
                               "endCell": {"row": 0, "column": -1, "subcolumn": 0}},
            "anchorRow": 0, "anchorColumn": 0, "firstSubColumn": 0, "rowTitlesWidth": 90,
            "subColumnTitleType": "default"}


def _content(cols: int, rows: int) -> bytes:
    return json.dumps({"$id": "sheets/data_sheet/data_table/data_table_storage.schema.json",
                       "numberOfColumns": cols, "numberOfRows": rows, "version": 1},
                      indent=4).encode()


def _csv(rows: Sequence[Sequence[str]]) -> bytes:
    return ("\n".join(",".join(r) for r in rows) + "\n").encode()


class _Ids:
    def __init__(self) -> None:
        self.fen = 10000
        self.obj = 20000          # V2.7: graph object ids of the tables' own graphs

    def next(self) -> int:
        self.fen += 1
        return self.fen


# ------------------------------------------------------------- graph texts
def _set_text(b: bytes, role: str, text: str) -> bytes:
    """Replace the text of the graph title / X / Y axis title in a graph block
    (see prismstyle.set_text: UTF-8 or cp1252 as the template stores it).
    Unchanged if not found."""
    return prismstyle.set_text(b, role, text)


# ------------------------------------------------------------------ tables
def _xy_extra(ids: _Ids, title: str, x, xlabel: str, kind: str, y, names, files: dict,
              ytitle: str = "") -> str:
    """An extra XY data sheet: kind 'sen' (y = (mean, sem, n)) or 'each' (y = T x n,
    one named data set per cell). Returns its sheet uid."""
    T = len(x)
    xu, tu, su = _uid(), _uid(), _uid()
    files[f"data/sets/{xu}.json"] = _dataset(xu, ids.next(), "y_single", xlabel, "DS_ATTR_X",
                                             {"replicates": [_rep(T, 2, ("NUMERIC", "NOTCONV"))]})
    if kind == "sen":
        mean, sem, n = y
        du = _uid()
        files[f"data/sets/{du}.json"] = _dataset(du, ids.next(), "y_se_n", ytitle or title,
                                                 "DS_ATTR_Y", {"replicates": [
                                                     _rep(T), _rep(T, 4, ("POSITIVE", "NUMERIC")),
                                                     _rep(T, 0, ("INTEGER", "POSITIVE", "NUMERIC"))]})
        sets, fmt = [du], "y_se_n"
        rows = [[_num(x[t]), _num(mean[t]), _num(sem[t]), _num(n[t])] for t in range(T)]
        cols = 4
    else:
        sets, fmt = [], "y_single"
        for j, nm in enumerate(names):
            du = _uid()
            files[f"data/sets/{du}.json"] = _dataset(du, ids.next(), "y_single", nm, "DS_ATTR_Y",
                                                     {"replicates": [_rep(T)]})
            sets.append(du)
        rows = [[_num(x[t])] + [_num(y[t, j]) for j in range(y.shape[1])] for t in range(T)]
        cols = 1 + y.shape[1]
    table = {"@class": "XYDataTable", "$id": "sheets/data_sheet/data_table/data_table.schema.json",
             "uid": tu, "format": "xy", "dataFormat": fmt, "dataSets": sets,
             "xDataSetFormat": "y_single", "xDataSet": xu}
    files[f"data/sheets/{su}/sheet.json"] = _sheet(su, ids.next(), title, table)
    files[f"data/tables/{tu}/data.csv"] = _csv(rows)
    files[f"data/tables/{tu}/content.json"] = _content(cols, T)
    return su


def _column_extra(ids: _Ids, title: str, ytitle: str, values, rownames, files: dict) -> str:
    """A column table (one value per cell, cell names as row titles): Prism graphs
    it as a scatter dot plot with mean +/- SEM."""
    n = len(values)
    ru, du, tu, su = _uid(), _uid(), _uid(), _uid()
    files[f"data/sets/{ru}.json"] = _dataset(ru, ids.next(), "text", None, "DS_ATTR_RT",
                                             {"replicates": [_rep(n, 15, ("NUMERIC",), "string")]})
    files[f"data/sets/{du}.json"] = _dataset(du, ids.next(), "y_single", ytitle, "DS_ATTR_Y",
                                             {"replicates": [_rep(n, 6)]})
    table = {"@class": "DataTable", "$id": "sheets/data_sheet/data_table/data_table.schema.json",
             "uid": tu, "format": "column", "dataFormat": "y_single", "rowTitlesDataSet": ru,
             "dataSets": [du]}
    files[f"data/sheets/{su}/sheet.json"] = _sheet(su, ids.next(), title, table)
    files[f"data/tables/{tu}/data.csv"] = _csv([[str(r).replace(",", " "), _num(v)]
                                                for r, v in zip(rownames, values)])
    files[f"data/tables/{tu}/content.json"] = _content(2, n)
    return su


def _columns_extra(ids: _Ids, title: str, ytitle: str, cols, files: dict) -> str:
    """V2.6 kinetics: a column table with one column per group (cols = [(name,
    values, value names)]); row k holds each group's k-th value (row titles: the
    value names of the group(s), '; '-joined where they differ). Prism graphs
    it as a scatter dot plot / bar with mean +/- SEM."""
    n = max([len(v) for _n, v, _r in cols] or [0])
    ru, tu, su = _uid(), _uid(), _uid()
    files[f"data/sets/{ru}.json"] = _dataset(ru, ids.next(), "text", None, "DS_ATTR_RT",
                                             {"replicates": [_rep(n, 15, ("NUMERIC",), "string")]})
    dus = []
    for name, _v, _r in cols:
        du = _uid()
        files[f"data/sets/{du}.json"] = _dataset(du, ids.next(), "y_single", str(name),
                                                 "DS_ATTR_Y", {"replicates": [_rep(n, 6)]})
        dus.append(du)
    table = {"@class": "DataTable", "$id": "sheets/data_sheet/data_table/data_table.schema.json",
             "uid": tu, "format": "column", "dataFormat": "y_single", "rowTitlesDataSet": ru,
             "dataSets": dus}
    files[f"data/sheets/{su}/sheet.json"] = _sheet(su, ids.next(), title, table)
    rows = []
    for k in range(n):
        names = []
        for _n, _v, r in cols:
            if k < len(r) and str(r[k]) not in names:
                names.append(str(r[k]))
        rows.append(["; ".join(names).replace(",", " ")] +
                    [_num(v[k]) if k < len(v) else "" for _n, v, _r in cols])
    files[f"data/tables/{tu}/data.csv"] = _csv(rows)
    files[f"data/tables/{tu}/content.json"] = _content(1 + len(cols), n)
    return su


def _drop_leftovers(out: dict, doc: dict) -> None:
    """Remove template files nothing refers to any more: data sets and tables of
    sheets that were left out, and the template's old analysis results in misc/
    (used_fonts.bin stays)."""
    sets, tables = set(), set()
    for su in doc["sheets"].get("data", []):
        sh = out.get(f"data/sheets/{su}/sheet.json")
        if sh is None:
            continue
        tab = (json.loads(sh) if isinstance(sh, bytes) else sh).get("table", {})
        tables.add(tab.get("uid"))
        sets.update(tab.get("dataSets", []))
        for k in ("xDataSet", "rowTitlesDataSet"):
            if tab.get(k):
                sets.add(tab[k])
    for k in list(out):
        parts = k.split("/")
        if k.startswith("data/sets/") and k.endswith(".json") and parts[2][:-5] not in sets:
            del out[k]
        elif k.startswith("data/tables/") and len(parts) >= 3 and parts[2] and parts[2] not in tables:
            del out[k]
        elif k.startswith("misc/") and k.endswith(".bin") and parts[-1] != "used_fonts.bin":
            del out[k]


# ------------------------------------------------- a graph for every table (V2.7)
EXTRA_PALETTE = ("#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#000000",
                 "#999999")


def _table_ranges(files: dict, tab: dict):
    """((x min, x max), (y min, y max)) of an XY table written here (its CSV);
    mean +/- SEM for 'mean, SEM, n' tables."""
    raw = files.get(f"data/tables/{tab['uid']}/data.csv", b"")
    xs, ys = [], []
    for line in raw.decode("utf-8", "replace").splitlines():
        v = [float(c) if c.strip() else np.nan for c in line.split(",")]
        if not v:
            continue
        xs.append(v[0])
        if tab.get("dataFormat") == "y_se_n" and len(v) >= 3:
            ys += [v[1] - (v[2] if np.isfinite(v[2]) else 0), v[1] + (v[2] if np.isfinite(v[2])
                                                                    else 0)]
        else:
            ys += v[1:]
    xs, ys = np.asarray(xs, float), np.asarray(ys, float)
    xs, ys = xs[np.isfinite(xs)], ys[np.isfinite(ys)]
    return ((float(xs.min()), float(xs.max())) if xs.size else (0.0, 1.0),
            (float(ys.min()), float(ys.max())) if ys.size else (0.0, 1.0))


def _table_graph(files: dict, ids: _Ids, tpl_gb: bytes, tpl_gs: dict, proto_fen: int,
                 su: str, title: str, style: Optional[dict], err: str) -> Optional[str]:
    """V2.7: a graph of the XY data sheet su (already in files), made from the
    template's graph block: its first data set takes the template plot, every
    other data set a copy in its own colour ('each' tables: thin lines, no
    symbols, no legend beyond 12 data sets). Returns the new graph uid (None
    when the table cannot be drawn this way)."""
    sh = files.get(f"data/sheets/{su}/sheet.json")
    if not isinstance(sh, dict):
        return None
    tab = sh.get("table", {})
    column = tab.get("format") == "column"
    if column:                      # from your column graph template (prismtemplate)
        from .prismtemplate import column_template
        ct = column_template()
        if ct is None:
            return None
        tpl_gb, tpl_gs, proto_fen = ct["gb"], ct["gs"], ct["fen"]
    elif tab.get("format") != "xy":
        return None
    sets = list(tab.get("dataSets") or [])
    if not sets:
        return None
    fens = [int(files[f"data/sets/{u}.json"]["fenID"]) for u in sets]
    names = [str(files[f"data/sets/{u}.json"].get("title", "")) for u in sets]
    gb = prismstyle.repoint(tpl_gb, proto_fen, fens[0])
    gb = _set_text(gb, "title", title)
    if column:
        yt = names[0] if len(names) == 1 else str(files[f"data/sets/{sets[0]}.json"].get(
            "title", ""))
        yt = sh["title"].split(" - ")[0] if len(names) > 1 else yt
        gb = _set_text(gb, "y", yt)
        style = None                    # the column graph keeps your template's look,
        b_ = bytearray(gb)              # with an automatic Y axis (the values change with
        prismstyle._set_axis(b_, prismstyle.records(gb), 1, None, None, 0.0, 1.0)  # quantity)
        gb = bytes(b_)
    else:
        xt = str(files[f"data/sets/{tab['xDataSet']}.json"].get("title", ""))
        gb = _set_text(gb, "x", xt)
        gb = _set_text(gb, "y", names[0] if len(names) == 1 else (sh["title"].split(" - ")[-1]))
        gb = _set_text(gb, "y2", "")
        gb = prismstyle.fix_template(gb, fens[0],
                                     err if err in ("SEM", "SD", "95% CI") else "SEM")
    if style:
        xr, yr = _table_ranges(files, tab)
        try:
            gb, _a, _n = prismstyle.apply_style(gb, dict(style, show_cells=False),
                                                data_fen=fens[0], y_range=yr, x_range=xr)
        except (ValueError, KeyError, struct.error):
            pass
    many = len(fens) > 12
    cols = [EXTRA_PALETTE[i % len(EXTRA_PALETTE)] for i in range(len(fens))]
    if len(fens) > 1:
        if many and not column:
            gb = prismstyle.add_cell_plots(gb, fens[0], fens[1:][::-1], "#808080", 0.5)
        elif column:                    # the groups along X in table order
            gb = prismstyle.add_dataset_plots(gb, fens[0], fens[1:], cols[1:])
        else:
            gb = prismstyle.add_dataset_plots(gb, fens[0], fens[1:][::-1], cols[1:][::-1])
    if column:
        gb = prismstyle.set_legend(gb, False, fens)    # the X axis names the groups
    elif not many:
        gb = prismstyle.style_series(gb, fens[0], colour=cols[0])
        for fen, sym in zip(fens, series_symbols(style, len(fens))):
            gb = prismstyle.style_series(gb, fen, symbol=sym)
    if not column:
        gb = prismstyle.set_legend(gb, len(fens) > 1 and not many, fens)
    gid, gfen = _uid(), ids.next()
    gb, ids.obj = prismstyle.clone_graph(gb, gfen, int(sh["fenID"]), ids.obj)
    gb = prismstyle.set_identity(gb, gfen, sh["title"][:60], str(uuid.uuid4()))
    gs = {k: v for k, v in tpl_gs.items() if k not in ("floatingNotes", "inputDataSets",
                                                        "mediaCollection")}
    gs.update(uid=gid, fenID=gfen, title=sh["title"], inputDataSets=list(sets))
    files[f"graphs/{gid}/data.bin"] = gb
    files[f"graphs/{gid}/sheet.json"] = gs
    return gid


def _all_graphs(files: dict, ids: _Ids, tpl_gb: bytes, tpl_gs: dict, proto_fen: int,
                sheets: Sequence[str], style: Optional[dict], err: str) -> List[str]:
    out = []
    for su in sheets:
        sh = files.get(f"data/sheets/{su}/sheet.json")
        g = _table_graph(files, ids, tpl_gb, tpl_gs, proto_fen, su,
                         sh["title"] if isinstance(sh, dict) else "", style, err)
        if g:
            out.append(g)
    return out


# ------------------------------------------------------------------- write
def template_takes_style(template) -> bool:
    """True when a .prism template gets the live graph's look: the built-in
    one (None / "") or one made from it (changed and saved in Prism - its graph
    keeps prismstyle.TEMPLATE_GRAPH_UID). Any other Prism graph keeps its own
    look; only the data and the texts are set."""
    if not template:
        return True
    try:
        with zipfile.ZipFile(long_path(Path(template))) as z:
            doc = json.loads(z.read("document.json"))
        return (list(doc["sheets"].get("graphs", [])) or [""])[0] == prismstyle.TEMPLATE_GRAPH_UID
    except (OSError, KeyError, ValueError, zipfile.BadZipFile):
        return False


def write_prism(path: str, x: np.ndarray, xlabel: str, quantity: str, ylabel: str,
                y: np.ndarray, names: Sequence[str], title: str, notes: str = "",
                drift: Optional[Tuple[str, str, np.ndarray]] = None,
                template: Optional[str] = None, name: str = "",
                style: Optional[dict] = None, report: Optional[dict] = None) -> str:
    """
    One .prism file for one quantity. y: T x n of the included cells (names
    'Cell_3', ...). drift: (table title, y title, slope per cell). name: what the
    graph and its tables are called in Prism's navigator (the .nd2 file name), so
    every sheet says which experiment it is. style: GraphStyle.to_dict() - the
    graph look; every field checked in GraphPad Prism 11 (prismstyle.SUPPORT)
    is applied, None = the template's own look (mean +/- SEM). Looks Prism
    cannot draw get the closest Prism look (graphstyle.prism_look: shaded band
    -> error bars, hidden mean -> hairline ...). report: if a dict, it receives
    {"applied": [...], "not_applied": [...], "template": ..., "closest": [the
    plain-language warnings]}.
    Never overwrites (adds _2, _3...). Returns the path written.
    """
    if not template:                          # V2.7: your Prism style template, if made
        from .prismtemplate import active_xy
        template = active_xy()
    builtin = not template
    closest: List[str] = []
    if style:
        from .graphstyle import prism_look
        style, closest = prism_look(style)
    tpl = Path(template) if template else TEMPLATE
    err = str((style or {}).get("error", "SEM"))
    if err not in ("SEM", "SD", "95% CI", "none"):
        err = "SEM"
    with zipfile.ZipFile(long_path(tpl)) as z:
        raw = {i.filename: z.read(i.filename) for i in z.infolist()}
        order = [i.filename for i in z.infolist()]
    files: dict = {}
    doc = json.loads(raw["document.json"])
    data_ids = list(doc["sheets"]["data"])
    graph_ids = list(doc["sheets"].get("graphs", []))
    if not data_ids or not graph_ids:
        raise ValueError("The Prism template has no data table or no graph.")
    y = np.asarray(y, float)
    T = len(x)
    n = max(1, y.shape[1])
    if y.shape[1] == 0:
        y = np.full((T, 1), np.nan)

    # ---- the graph's own table: every data set gets the cells as replicates
    gsid = data_ids[0]
    sheet = json.loads(raw[f"data/sheets/{gsid}/sheet.json"])
    tab = sheet["table"]
    if tab.get("dataFormat") != "y_replicates" or not tab.get("dataSets"):
        raise ValueError("This Prism template cannot be used: the table its graph shows must be "
                         "an XY table with replicate values (side-by-side subcolumns). Use "
                         "PeterPiper's own .prism file (changed and saved in Prism) as the style.")
    keep = [tab["dataSets"][0]]
    for u in tab["dataSets"][1:]:                  # a second set ('Each cell') is drawn as
        d = json.loads(raw[f"data/sets/{u}.json"])  # the grey per-cell lines
        if "each" in str(d.get("title", "")).lower() and len(keep) < 2:
            keep.append(u)
    gone = []
    for u in tab["dataSets"]:
        if u not in keep:
            d0 = raw.pop(f"data/sets/{u}.json", None)
            if d0:
                gone.append(int(json.loads(d0).get("fenID", -1)))
    tab["dataSets"] = keep
    tab["replicatesCount"] = n
    label = name or quantity                       # navigator names: the .nd2 file
    sheet["title"] = label if name else f"{quantity} - cells as replicates"
    n_real = y.shape[1] if np.isfinite(y).any() else 0
    titles = [f"{quantity}  (mean, n = {n_real})" if err == "none" else
              f"{quantity}  (mean +/- {err}, n = {n_real})",
              "Each cell"]
    for i, u in enumerate(keep):
        d = json.loads(raw[f"data/sets/{u}.json"])
        r = dict(d["replicate ranges"][0]["replicate"])
        r.update(firstRow=0, lastRow=T - 1, commonAttributes=["NUMERIC", "USER"], decimalsLength=4)
        d["replicate ranges"] = [{"range": f"0~{n - 1}" if n > 1 else "0", "replicate": r}]
        d["title"] = titles[i]
        files[f"data/sets/{u}.json"] = d
    xd = json.loads(raw[f"data/sets/{tab['xDataSet']}.json"])
    xd["title"] = xlabel
    xd["replicates"][0].update(firstRow=0, lastRow=T - 1, decimalsLength=2)
    files[f"data/sets/{tab['xDataSet']}.json"] = xd
    tid = tab["uid"]
    rows = [[_num(x[t])] + [_num(v) for v in y[t]] * len(keep) for t in range(T)]
    files[f"data/tables/{tid}/data.csv"] = _csv(rows)
    files[f"data/tables/{tid}/content.json"] = _content(1 + n * len(keep), T)
    raw.pop(f"data/tables/{tid}/data.dt", None)
    files[f"data/sheets/{gsid}/sheet.json"] = sheet
    # template-only extras (other data sheets, unused leftovers) are left out
    for k in [k for k in raw if k.startswith("data/sheets/") and k.count("/") >= 3
              and k.split("/")[2] != gsid]:
        raw.pop(k)
    data_ids = [gsid]

    # ---- the graph: title, axis titles; no stale notes
    gid = graph_ids[0]
    for k in [k for k in raw if k.startswith("graphs/") and not k.startswith(f"graphs/{gid}/")]:
        raw.pop(k)
    gb = raw[f"graphs/{gid}/data.bin"]
    if gone:                     # V2.7: a template with more data sets (your edited one)
        gb = prismstyle.remove_plots(gb, gone)
    tpl_gb = gb                                          # V2.7: for the tables' own graphs
    tpl_gs = json.loads(raw[f"graphs/{gid}/sheet.json"])
    gb = _set_text(gb, "title", title)
    gb = _set_text(gb, "y", ylabel)
    gb = _set_text(gb, "x", xlabel)
    data_fen = int(files[f"data/sets/{keep[0]}.json"].get("fenID", -1))
    fin = np.isfinite(y)
    yr = (float(np.nanmin(y)), float(np.nanmax(y))) if fin.any() else (0.0, 1.0)
    xr = (float(np.nanmin(x)), float(np.nanmax(x))) if np.isfinite(x).any() else (0.0, 1.0)
    # the style is applied to the built-in template and to templates made from it
    # (changed and saved in Prism: same graph); other Prism graphs are only given
    # the data and the texts, because their layout was never checked in Prism.
    styled = builtin or gid == prismstyle.TEMPLATE_GRAPH_UID
    rep: dict = {"applied": [], "not_applied": [], "template": "built-in" if builtin else
                 (f"made from PeterPiper's template: {tpl.name}" if styled else
                  f"other Prism file (style not applied): {tpl.name}"),
                 "closest": closest if styled else []}
    if builtin:
        # the bundled template's own defects: it drew mean +/- SD (titled SEM), its
        # X axis was fixed at -5..55 (later timepoints were cut off) and its
        # hidden right-axis title said "Y1Title".
        gb = prismstyle.fix_template(gb, data_fen, err if style is None else "SEM")
        gb = _set_text(gb, "y2", "")
    if style and not styled:
        rep["not_applied"] = sorted(f for f in prismstyle.SUPPORT
                                    if f not in ("title", "x_title", "y_title"))
    if style and styled:
        gb, rep["applied"], rep["not_applied"] = prismstyle.apply_style(
            gb, style, data_fen=data_fen, y_range=yr, x_range=xr)
    if report is not None:
        report.update(rep)
    files[f"graphs/{gid}/data.bin"] = gb
    gs = json.loads(raw[f"graphs/{gid}/sheet.json"])
    for nid in gs.pop("floatingNotes", []) or []:
        raw.pop(f"graphs/{gid}/floating_notes/{nid}.json", None)
    gs["title"] = label
    files[f"graphs/{gid}/sheet.json"] = gs

    # ---- extra tables: the numbers
    ids = _Ids()
    with np.errstate(invalid="ignore", divide="ignore"):
        cnt = np.sum(np.isfinite(y), axis=1).astype(float)
        mean = np.where(cnt > 0, np.nansum(y, axis=1) / np.maximum(cnt, 1), np.nan)
        sd = np.array([np.nanstd(r[np.isfinite(r)], ddof=1) if np.isfinite(r).sum() > 1 else np.nan
                       for r in y])
        sem = sd / np.sqrt(np.maximum(cnt, 1))
    extra = [_xy_extra(ids, f"{label} - {quantity} mean, SEM, n" if name else
                       f"{quantity} - mean, SEM, n", x, xlabel, "sen", (mean, sem, cnt), None,
                       files, quantity),
             _xy_extra(ids, f"{label} - {quantity} each cell" if name else
                       f"{quantity} - each cell", x, xlabel, "each", y, list(names), files)]
    if drift is not None:
        dtitle, ytitle, vals = drift
        extra.append(_column_extra(ids, f"{label} - {dtitle}" if name else dtitle, ytitle,
                                   list(vals), list(names), files))
    # ---- each cell as a thin line: one more plot per cell, drawing the cell's
    # data set of the 'each cell' table (behind the mean)
    if style and styled and style.get("show_cells") and prismstyle.SUPPORT.get("show_cells") == "yes" \
            and np.isfinite(y).any():
        tab_each = files[f"data/sheets/{extra[1]}/sheet.json"]["table"]
        fens = [files[f"data/sets/{u}.json"]["fenID"] for u in tab_each["dataSets"]]
        key = f"graphs/{gid}/data.bin"
        try:
            files[key] = prismstyle.add_cell_plots(
                files[key], data_fen, fens, style.get("cell_colour", "#C0C0C0"),
                style.get("cell_width", 0.5))
            rep["applied"] = sorted(set(rep["applied"]) | {"show_cells", "cell_colour", "cell_width"})
            rep["not_applied"] = [f for f in rep["not_applied"]
                                  if f not in ("show_cells", "cell_colour", "cell_width")]
        except ValueError:                           # template without a usable plot
            rep["not_applied"] = sorted(set(rep["not_applied"]) |
                                        {"show_cells", "cell_colour", "cell_width"})
        if report is not None:
            report.update(rep)

    # ---- V2.7: every other table gets its own graph (made from the same template;
    # only templates the look applies to - other Prism graphs were never checked)
    ids.obj = max(prismstyle.object_ids(files[f"graphs/{gid}/data.bin"]) + [0]) + 1
    more_graphs = _all_graphs(files, ids, tpl_gb, tpl_gs, data_fen, extra,
                              style if styled else None, err) if styled else []
    # ---- project info + document
    info_ids = list(doc["sheets"].get("info", []))
    if info_ids:
        key = f"info/{info_ids[0]}/sheet.json"
        info = json.loads(raw[key])
        info["notesText"] = notes
        info["experimentDate"] = dt.date.today().isoformat()
        for c in info.get("constants", []):
            if c.get("name") == "Experiment Date":
                c["value"] = dt.date.today().strftime("%m/%d/%Y")
            elif c.get("name") == "Experiment ID":
                c["value"] = title
        files[key] = info
    doc["sheets"] = {k: v for k, v in doc["sheets"].items() if k not in ("data", "graphs")}
    doc["sheets"]["data"] = data_ids + extra
    doc["sheets"]["graphs"] = [gid] + more_graphs
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    doc["creationDate"] = doc["modificationDate"] = stamp
    for who in ("createdBy", "modifiedBy"):
        if isinstance(doc.get(who), dict):
            doc[who]["user"] = ""
    ui = doc.setdefault("uiSettings", {})
    ui["currentSheetType"] = "Graph"
    ui["currentSheets"] = {"data": gsid, "graph": gid, **({"info": info_ids[0]} if info_ids else {})}
    ui["nextDataSheetNumber"] = len(data_ids) + len(extra) + 1
    attrs = {gsid: {"title": sheet["title"]}, gid: {"title": label}}
    for g2 in more_graphs:
        attrs[g2] = {"title": files[f"graphs/{g2}/sheet.json"]["title"]}
    for su in extra:
        attrs[su] = {"title": files[f"data/sheets/{su}/sheet.json"]["title"]}
    for iid in info_ids:
        attrs[iid] = doc.get("sheetAttributesMap", {}).get(iid, {"title": "Project info 1"})
    doc["sheetAttributesMap"] = attrs
    files["document.json"] = doc

    out = {}
    for k in order:
        if k in raw or k in files:
            out[k] = files.get(k, raw.get(k))
    for k, v in files.items():
        out.setdefault(k, v)
    _drop_leftovers(out, doc)
    with new_output_file(Path(path)) as (used, stream):
        with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as zo:
            for k, v in out.items():
                if isinstance(v, (dict, list)):
                    v = json.dumps(v, indent="\t").encode()
                zo.writestr(k, v)
    return str(used)


# ------------------------------------------------------------ compare runs (V2.4)
def write_compare_prism(path: str, runs: Sequence[Tuple[str, np.ndarray, np.ndarray]],
                        xlabel: str, quantity: str, ylabel: str, title: str,
                        colours: Sequence[str], style: Optional[dict] = None,
                        notes: str = "", legend: bool = True,
                        symbols: Optional[Sequence[str]] = None,
                        sheet_title: Optional[str] = None,
                        sen_titles: Optional[Sequence[str]] = None,
                        extra: Sequence[tuple] = (),
                        columns_extra: Sequence[tuple] = (),
                        stacked: bool = False, table_graphs: bool = True) -> str:
    """
    'Compare runs' / V2.5 'Compare / average': ONE .prism made from the built-in
    template with one data set per line (runs = [(legend title, x, y T x n)]; the
    columns of y are the replicates: a run's included cells, or - for a group
    average - one column per dish holding that dish's mean), so Prism itself
    draws mean +/- error of the replicates per line, with a legend (legend=True).
    X = the union of the lines' times (each line's values sit on its own rows).
    The live look (prismstyle) is applied to the first line's plot; every other
    line gets a copy of that plot in its own colour (prismstyle.add_dataset_plots)
    and the template's symbol for that data set (symbols: one SYMBOL_CODES key per
    line; None = series_symbols(style)). Also one 'mean, SEM, n' table per line
    (sen_titles: their titles) and `extra` tables: (title, x, 'sen' | 'each', y,
    names, y title) as _xy_extra; columns_extra: (title, y title, [(name, values,
    value names)]) as _columns_extra (V2.6 kinetics). V2.7: an extra table may
    have a 7th element, its own X title. stacked: each line gets its own block of
    rows in its own order (V2.7 plot builder: X is a measure, so the rows keep
    the time order of a trajectory) instead of rows shared by equal X.
    Never overwrites. Returns the path.
    """
    from .graphstyle import prism_look
    if not runs:
        raise ValueError("No runs to compare.")
    st = dict(prism_look(style or {})[0], show_cells=False)
    if symbols is None:
        symbols = series_symbols(style, len(runs))
    err = str(st.get("error", "SEM"))
    from .prismtemplate import active_xy
    with zipfile.ZipFile(long_path(active_xy() or TEMPLATE)) as z:     # V2.7: yours, if made
        raw = {i.filename: z.read(i.filename) for i in z.infolist()}
        order = [i.filename for i in z.infolist()]
    files: dict = {}
    doc = json.loads(raw["document.json"])
    gsid = list(doc["sheets"]["data"])[0]
    gid = list(doc["sheets"]["graphs"])[0]
    sheet = json.loads(raw[f"data/sheets/{gsid}/sheet.json"])
    tab = sheet["table"]
    proto_uid = tab["dataSets"][0]
    proto = json.loads(raw[f"data/sets/{proto_uid}.json"])
    gone = []
    for u in tab["dataSets"]:
        d0 = raw.pop(f"data/sets/{u}.json", None)
        if d0 and u != proto_uid:
            gone.append(int(json.loads(d0).get("fenID", -1)))
    # rows: every time of every run (rounded so equal times share a row); stacked:
    # one block of rows per line, in its own order
    if stacked:
        xs, blocks = [], []
        for _l, x, _y in runs:
            blocks.append(len(xs))
            xs += [float(v) for v in np.asarray(x, float)]
        row_of = {}
    else:
        xs = sorted({round(float(v), 9) for _l, x, _y in runs for v in np.asarray(x, float)
                     if np.isfinite(v)})
        row_of = {v: i for i, v in enumerate(xs)}
    T = len(xs)
    n_rep = max(1, max(np.asarray(y).shape[1] for _l, _x, y in runs))
    ids = _Ids()
    uids, fens = [], []
    grid = []
    for i, (label, x, y) in enumerate(runs):
        y = np.asarray(y, float)
        uid = proto_uid if i == 0 else _uid()
        fen = int(proto["fenID"]) if i == 0 else ids.next()
        d = copy.deepcopy(proto)
        d.update(uid=uid, fenID=fen)
        r = dict(d["replicate ranges"][0]["replicate"])
        r.update(firstRow=0, lastRow=T - 1, commonAttributes=["NUMERIC", "USER"],
                 decimalsLength=4)
        d["replicate ranges"] = [{"range": f"0~{n_rep - 1}" if n_rep > 1 else "0",
                                  "replicate": r}]
        d["title"] = str(label)
        files[f"data/sets/{uid}.json"] = d
        uids.append(uid)
        fens.append(fen)
        g = np.full((T, n_rep), np.nan)
        for t, xv in enumerate(np.asarray(x, float)):
            if stacked:
                g[blocks[i] + t, :y.shape[1]] = y[t]
            elif np.isfinite(xv):
                g[row_of[round(float(xv), 9)], :y.shape[1]] = y[t]
        grid.append(g)
    tab["dataSets"] = uids
    tab["replicatesCount"] = n_rep
    name = sheet_title or f"Compare - {quantity}"
    sheet["title"] = name
    xd = json.loads(raw[f"data/sets/{tab['xDataSet']}.json"])
    xd["title"] = xlabel
    xd["replicates"][0].update(firstRow=0, lastRow=T - 1, decimalsLength=2)
    files[f"data/sets/{tab['xDataSet']}.json"] = xd
    tid = tab["uid"]
    files[f"data/tables/{tid}/data.csv"] = _csv(
        [[_num(xs[t])] + [_num(v) for g in grid for v in g[t]] for t in range(T)])
    files[f"data/tables/{tid}/content.json"] = _content(1 + n_rep * len(runs), T)
    raw.pop(f"data/tables/{tid}/data.dt", None)
    files[f"data/sheets/{gsid}/sheet.json"] = sheet

    gb = raw[f"graphs/{gid}/data.bin"]
    if gone:                     # V2.7: a template with more data sets (your edited one)
        gb = prismstyle.remove_plots(gb, gone)
    tpl_gb, proto_fen = gb, int(proto["fenID"])          # V2.7: for the tables' own graphs
    tpl_gs = json.loads(raw[f"graphs/{gid}/sheet.json"])
    gb = _set_text(gb, "title", title)
    gb = _set_text(gb, "y", ylabel)
    gb = _set_text(gb, "x", xlabel)
    data_fen = fens[0]
    allv = np.concatenate([np.asarray(y, float).ravel() for _l, _x, y in runs])
    fin = allv[np.isfinite(allv)]
    yr = (float(fin.min()), float(fin.max())) if fin.size else (0.0, 1.0)
    fx = [v for v in xs if np.isfinite(v)]
    xr = (min(fx), max(fx)) if fx else (0.0, 1.0)
    gb = prismstyle.fix_template(gb, data_fen, err if err in ("SEM", "SD", "95% CI") else "SEM")
    gb = _set_text(gb, "y2", "")
    st["mean_colour"] = colours[0]
    gb, _applied, _skipped = prismstyle.apply_style(gb, st, data_fen=data_fen, y_range=yr,
                                                    x_range=xr)
    if len(runs) > 1:
        # added in reverse: Prism's legend then lists the lines in table order
        # (checked in Prism 11: first line, then the added plots last-added first)
        gb = prismstyle.add_dataset_plots(gb, data_fen, fens[1:][::-1],
                                          list(colours[1:len(runs)])[::-1])
    for fen, sym in zip(fens, symbols or []):          # the template's symbol per data set
        if sym:
            gb = prismstyle.style_series(gb, fen, symbol=sym)
    gb = prismstyle.set_legend(gb, bool(legend), fens)
    files[f"graphs/{gid}/data.bin"] = gb
    gs = json.loads(raw[f"graphs/{gid}/sheet.json"])
    for nid in gs.pop("floatingNotes", []) or []:
        raw.pop(f"graphs/{gid}/floating_notes/{nid}.json", None)
    gs["title"] = name
    if "inputDataSets" in gs:
        gs["inputDataSets"] = list(uids)
    files[f"graphs/{gid}/sheet.json"] = gs

    extra_ids = []
    for i, (label, x, y) in enumerate(runs):
        y = np.asarray(y, float)
        sm = _describe(y)
        t_ = sen_titles[i] if sen_titles and i < len(sen_titles) else             f"{label} - {quantity} mean, SEM, n"
        extra_ids.append(_xy_extra(ids, t_, np.asarray(x, float), xlabel, "sen",
                                   (sm.mean, sm.sem, sm.n.astype(float)), None, files, quantity))
    for et in extra:
        e_title, e_x, e_kind, e_y, e_names, e_yt = et[:6]
        e_xl = et[6] if len(et) > 6 else xlabel
        extra_ids.append(_xy_extra(ids, e_title, np.asarray(e_x, float), e_xl, e_kind, e_y,
                                   e_names, files, e_yt))
    for c_title, c_yt, c_cols in columns_extra:
        extra_ids.append(_columns_extra(ids, c_title, c_yt, c_cols, files))
    extra = extra_ids
    ids.obj = max(prismstyle.object_ids(gb) + [0]) + 1
    more_graphs = _all_graphs(files, ids, tpl_gb, tpl_gs, proto_fen, extra, st, err)         if table_graphs else []
    for k in [k for k in raw if k.startswith("data/sheets/") and k.count("/") >= 3
              and k.split("/")[2] != gsid]:
        raw.pop(k)
    for k in [k for k in raw if k.startswith("graphs/") and not k.startswith(f"graphs/{gid}/")]:
        raw.pop(k)

    info_ids = list(doc["sheets"].get("info", []))
    if info_ids:
        key = f"info/{info_ids[0]}/sheet.json"
        info = json.loads(raw[key])
        info["notesText"] = notes
        info["experimentDate"] = dt.date.today().isoformat()
        for c in info.get("constants", []):
            if c.get("name") == "Experiment Date":
                c["value"] = dt.date.today().strftime("%m/%d/%Y")
            elif c.get("name") == "Experiment ID":
                c["value"] = title
        files[key] = info
    doc["sheets"] = {k: v for k, v in doc["sheets"].items() if k not in ("data", "graphs")}
    doc["sheets"]["data"] = [gsid] + extra
    doc["sheets"]["graphs"] = [gid] + more_graphs
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    doc["creationDate"] = doc["modificationDate"] = stamp
    for who in ("createdBy", "modifiedBy"):
        if isinstance(doc.get(who), dict):
            doc[who]["user"] = ""
    ui = doc.setdefault("uiSettings", {})
    ui["currentSheetType"] = "Graph"
    ui["currentSheets"] = {"data": gsid, "graph": gid, **({"info": info_ids[0]} if info_ids else {})}
    ui["nextDataSheetNumber"] = len(extra) + 2
    attrs = {gsid: {"title": sheet["title"]}, gid: {"title": gs["title"]}}
    for g2 in more_graphs:
        attrs[g2] = {"title": files[f"graphs/{g2}/sheet.json"]["title"]}
    for su in extra:
        attrs[su] = {"title": files[f"data/sheets/{su}/sheet.json"]["title"]}
    for iid in info_ids:
        attrs[iid] = doc.get("sheetAttributesMap", {}).get(iid, {"title": "Project info 1"})
    doc["sheetAttributesMap"] = attrs
    files["document.json"] = doc
    out = {}
    for k in order:
        if k in raw or k in files:
            out[k] = files.get(k, raw.get(k))
    for k, v in files.items():
        out.setdefault(k, v)
    _drop_leftovers(out, doc)
    with new_output_file(Path(path)) as (used, stream):
        with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as zo:
            for k, v in out.items():
                if isinstance(v, (dict, list)):
                    v = json.dumps(v, indent="\t").encode()
                zo.writestr(k, v)
    return str(used)


LOOK_FILE = Path(__file__).resolve().parent / "templates" / "PeterPiper_look.json"
_LOOK: Optional[dict] = None


def template_look() -> dict:
    """The look of the bundled template (templates/PeterPiper_look.json, made by
    dev_tests/make_prism_template.py from a graph styled in Prism): font size and,
    per data set in turn, symbol and colours. {} when the file is missing."""
    global _LOOK
    if _LOOK is None:
        try:
            _LOOK = json.loads(LOOK_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _LOOK = {}
    return _LOOK


def series_symbols(style: Optional[dict], n: int) -> List[str]:
    """The symbol of each of n data sets: the template's sequence (circle, square,
    triangle, triangle down, then diamond and the open shapes) when the style's
    symbol is the default one; the style's own symbol for every line otherwise
    ('none' = no symbols)."""
    from .graphstyle import GraphStyle
    sym = str((style or {}).get("symbol", GraphStyle().symbol))
    if sym != GraphStyle().symbol:
        return [sym] * n
    seq = [s.get("symbol", "circle") for s in template_look().get("series", [])] or ["circle"]
    for more in ("diamond", "open_circle", "open_square", "open_triangle", "open_diamond",
                 "open_triangle_down"):
        if more not in seq:
            seq.append(more)
    return [seq[i % len(seq)] for i in range(n)]


def _describe(y):
    from .graphstyle import describe
    return describe(y)
